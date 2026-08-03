# Faz 6 — tarayıcıda mühendis gözüyle denetim

**Tarih:** 3 Ağustos 2026 · **Sürüm:** 2.6.26 · **Taban commit:** `7c8a50f`

Dört salt-okunur denetçi ajanı, her biri kendi portunda kendi uygulama
örneğiyle, tarayıcıda gerçek kullanıcı akışlarını koşturdu. Kaynak koda
dokunulmadı; bu belge **av** çıktısıdır, düzeltme ayrı iştir.

## Kapsam (ölçülen, beyan değil)

| Sayfa | Düğme denendi | Analiz koşturuldu | Grafik denetlendi | Bulgu |
|---|---:|---:|---:|---:|
| `/liquid` | 45 | 21 | 18 | 23 |
| `yardımcı` | 24 | 6 | 15 | 14 |
| `/hybrid` | 42 | 18 | 19 | 17 |
| `/solid` | 53 | 62 | 16 | 22 |
| **toplam** | **164** | **107** | **68** | **76** |

Ekran görüntüsü: 166 adet, `scratchpad/faz6/<sayfa>/` altında.
Ajan raporlarının uzun hâli: `scratchpad/faz6/rapor_<sayfa>.md`.

## Şiddet ve hüküm dağılımı

| Şiddet | Adet |    | Hüküm | Adet |
|---|---:|---|---|---:|
| **KRİTİK** | 8 |  | yanıltıcı | 32 |
| **CİDDİ** | 22 |  | eksik | 12 |
| **ORTA** | 25 |  | fiziksel imkânsız | 8 |
| **DÜŞÜK** | 21 |  | anlamsız | 8 |
|  |  |  | birim/ölçek yanlış | 6 |
|  |  |  | dil | 6 |
|  |  |  | sahte gösterge | 3 |
|  |  |  | ağ hatası | 1 |

## Ana modelin bağımsız doğrulaması

Ajan raporu kanıt sayılmaz. Sekiz KRİTİK'in tamamı ana model tarafından
yeniden üretildi veya koddan teyit edildi:

| # | Bulgu | Nasıl doğrulandı | Sonuç |
|---|---|---|---|
| T01 | PDF `0.0` basıyor | İndirilen PDF açıldı, s.2 okundu | ✅ birebir |
| T02 | 6-DOF 3,25× ihlal | Panel tarayıcıda koşturuldu, giden istek yakalandı | ✅ birebir |
| T03 | `Fly this site` ölü | Düğme tıklandı, istek gövdesi yakalandı: `"dry_mass":"--7"` | ✅ birebir |
| T04 | Yakıt kütlesi 3× | `solid.html:2697` + `solid_rocket_engine.py:7052` okundu, elle hesap | ✅ birebir |
| T05 | c\* üssü ters | `solid.html:2641` okundu, `1,125^9 = 2,8865` elle hesaplandı | ✅ birebir |
| T06 | Kesit girdilerden bağımsız | `visualization.py:3398-3412` okundu, `r_go = 0,96·rc` türetildi | ✅ mekanizma |
| T07 | `Final port` yer tutucu | `visualization.py:3411` kıstırma satırı okundu | ✅ mekanizma |
| T08 | Yörünge 19,8 kg yakıyor | T04'ün doğrudan sonucu | ✅ türetilmiş |

## Bulgu listesi

| # | Sayfa | Şiddet | Hüküm | Başlık |
|---|---|---|---|---|
| T01 | `/liquid` | KRİTİK | yanıltıcı | PDF raporunun yönetici özeti itki, Isp ve yanma süresini 0.0 basıyor |
| T02 | `/liquid` | KRİTİK | fiziksel imkânsız | 6-DOF uçuş paneli roket denklemini 3,25x ihlal eden bir tepe yüksekliği raporluyor |
| T03 | `/solid` | KRİTİK | yanıltıcı | Form kütle bloğu çözücünün tam 3 katı yakıt gösteriyor |
| T04 | `/solid` | KRİTİK | fiziksel imkânsız | c* yardımcı düğmesi fiziksel olarak imkânsız 508,7 m/s üretiyor (üs tersine alınmış) |
| T05 | `/solid` | KRİTİK | fiziksel imkânsız | Yörünge, motorun taşımadığı 19,8 kg yakıtı yakıyor (örtük Isp 66 s) |
| T06 | `/solid` | KRİTİK | birim/ölçek yanlış | Motor kesitinin radyal ölçüleri girdilerden tamamen bağımsız (grain Ø60 -> Ø96 çiziliyor) |
| T07 | `/solid` | KRİTİK | sahte gösterge | 'Final port Ø99,8 mm' etiketi hesap değil yer tutucu; çözücünün gerçek son portu ≈65 mm |
| T08 | `yardımcı` | KRİTİK | eksik | "Fly this site" düğmesi hiçbir koşulda çalışmıyor: iki çakışan num() bildirimi yüzünden 8 alan "--" dizgesi olarak gidiyor, sunucu 422 dönüyor |
| T09 | `/hybrid` | CİDDİ | birim/ölçek yanlış | Toplam impuls İngilizce arayüzde 1000 kat yanlış okunacak biçimde yazılıyor |
| T10 | `/hybrid` | CİDDİ | yanıltıcı | Tane boyu 2B kesitte ve 3B modelde sessizce %8 kırpılıyor (imalat kontrolü için önerilen çizimde) |
| T11 | `/hybrid` | CİDDİ | yanıltıcı | 'Tank' basınç çubuğu kullanıcının girdiği tank basıncını hiç göstermiyor (düzeltme ölü kod) |
| T12 | `/hybrid` | CİDDİ | fiziksel imkânsız | Trajectory Analysis, motorun kendi özgül itkisini 4,5 kat ihlal eden bir uçuş simüle ediyor |
| T13 | `/liquid` | CİDDİ | birim/ölçek yanlış | 3B tank görünümünde girdap önleyici düzenek 1000x küçük çiziliyor (0,26 mm) |
| T14 | `/liquid` | CİDDİ | fiziksel imkânsız | Sıvı oksijenin yoğunluğu gaz fazı değeriyle (1,31 kg/m³) 'gerçek zamanlı NIST verisi' olarak gösteriliyor |
| T15 | `/liquid` | CİDDİ | yanıltıcı | İrtifa grafiğinde 'Isp vs Altitude' eğrisi tümüyle görünmez (itki eğrisi %100 örtüyor) |
| T16 | `/liquid` | CİDDİ | yanıltıcı | İmalat çizimi, emniyet marjı negatif olan cidarı 'basınç yüküne karşı doğrulandı' diye damgalıyor |
| T17 | `/liquid` | CİDDİ | ağ hatası | Belirsizlik (UQ) paneli /liquid sayfasından hiç çalışmıyor: motor_type gönderilmiyor |
| T18 | `/liquid` | CİDDİ | yanıltıcı | 3B performans haritası N2O/HTPB yüzeyi çiziyor, üstüne RP-1/LOX tasarım noktasını basıyor |
| T19 | `/solid` | CİDDİ | sahte gösterge | Monte Carlo 'Peak Pressure' istatistiği 300 koşuda sıfır sapmalı (yapısal olarak sabit) |
| T20 | `/solid` | CİDDİ | yanıltıcı | 'Specific Impulse vs Altitude' grafiği 2 piksellik alana sıkışıyor, eksen etiketleri çakışıyor |
| T21 | `/solid` | CİDDİ | eksik | '3D CAD Design' panelinin grafiği hesap bittikten sonra da 'NO DATA' gösteriyor |
| T22 | `/solid` | CİDDİ | yanıltıcı | 'Case Inner Diameter' satırı grain dış çapını gösteriyor; sayfada 3 farklı kasa çapı dolaşıyor |
| T23 | `/solid` | CİDDİ | yanıltıcı | 6-DOF paneli ön-dolmuyor; rıhtım başlığı 'sonuçlardan ön-dolar' diyor |
| T24 | `/solid` | CİDDİ | anlamsız | 'Web Thickness' girdisi ölü; tabloda raporlanan web gerçekte tükenenin 2 katı |
| T25 | `/solid` | CİDDİ | yanıltıcı | 'Grain Length' ipucu tek grain diyor, çözücü toplam yığın sayıyor |
| T26 | `yardımcı` | CİDDİ | fiziksel imkânsız | Formül sayfası §1.3 itki katsayısı: karekök kapsamı yanlış, fiziksel olarak imkânsız C_F=0,974 üretiyor (sayfanın kendi tablosu 1,2-2,0 diyor) |
| T27 | `yardımcı` | CİDDİ | birim/ölçek yanlış | Formül sayfası §1.2: aynı bölümün iki c* kutusu √γ kadar (%9,5) çelişiyor — birinci kutuda γ pay ve paydada sadeleşiyor |
| T28 | `yardımcı` | CİDDİ | fiziksel imkânsız | Formül sayfası §6.2 hibrit port yarıçapı r(t): üs 2n+1 yerine 2(1−n) yazılmış — n=0,8'de %38 sapma, n=1'de sıfıra bölme |
| T29 | `yardımcı` | CİDDİ | fiziksel imkânsız | Formül sayfası §3.4: ikinci yanma verimi tanımı her gerçekçi girdide %160-183 veriyor (verim >1 imkânsız), üstündeki doğru tanımla çelişiyor |
| T30 | `yardımcı` | CİDDİ | yanıltıcı | Kayıtlı proje seçilince kilitli İtki ve Motor atıl kütlesi alanları BOŞ kalıyor, rozet "example, not calculated" yalanı söylüyor ve çözücüye sessizce örnek aracın 6500 N'u gidiyor |
| T31 | `/hybrid` | ORTA | anlamsız | Uyarılar panelinde 'VALIDATION STATUS: [OBJECT OBJECT]' — doğrulama durumu kullanıcıya hiç ulaşmıyor |
| T32 | `/hybrid` | ORTA | yanıltıcı | 'Impulse Efficiency' %110'a çıkıyor ve kendi açıklama metniyle çelişiyor |
| T33 | `/hybrid` | ORTA | yanıltıcı | Aynı sayfada iki farklı deniz seviyesi itkisi (1000 N ve 1034 N) ve manşetten %3,4 sapan Isp |
| T34 | `/hybrid` | ORTA | yanıltıcı | 6-DOF hücum açısı grafiği fırlatma artefaktı yüzünden okunamaz; rozetle 31 kat çelişiyor |
| T35 | `/hybrid` | ORTA | yanıltıcı | İki zaman-marşı çözümü aynı motor için sistematik %2 farklı itki ve oda basıncı veriyor |
| T36 | `/hybrid` | ORTA | eksik | Enjektör şemasında 'Total Flow: not reported' yer tutucusu — veri sayfada mevcut |
| T37 | `/hybrid` | ORTA | yanıltıcı | Isp/(O/F) optimizasyon taraması optimumu içeremiyor; 'Sweep maximum' ızgaranın ucunda |
| T38 | `/liquid` | ORTA | yanıltıcı | Enjektör tasarım paneli, aynı sayfada hesaplanan motorun debilerini almıyor (%33 sapma) |
| T39 | `/liquid` | ORTA | yanıltıcı | Ekrandaki motor kesitinde oda cidarı 3,0 mm, imalat çıktılarında 5,00 mm |
| T40 | `/liquid` | ORTA | yanıltıcı | Kayıp pastası, kendi başlığındaki verime dahil OLMAYAN bir kalemi %29,9'luk dilim gösteriyor |
| T41 | `/liquid` | ORTA | anlamsız | Kayıp pastası etiketlerinde ham veri anahtarı sızıyor (HEAT TRANSFER_LOSS) |
| T42 | `/liquid` | ORTA | yanıltıcı | Aynı sayfada iki farklı deniz seviyesi Isp: 244,9 s ve 249,9 s |
| T43 | `/liquid` | ORTA | anlamsız | Enjektör göstergesi hangi büyüklüğü gösterdiğini söylemiyor; yakıt devresi hiç gösterilmiyor |
| T44 | `/liquid` | ORTA | yanıltıcı | Geometrik olarak sığmayan 80 soğutma kanalı Excel'e uyarısız aktarılıyor |
| T45 | `/liquid` | ORTA | anlamsız | Anlamsız hassasiyet: 17 anlamlı basamak (3707.0404366159974 K) |
| T46 | `/liquid` | ORTA | eksik | 3B tank grafiğinde 19 adlandırılmış iz var ama efsane hiç çizilmiyor |
| T47 | `/liquid` | ORTA | dil | İngilizce modda Türkçe metin çıkıyor (enjektör paneli) |
| T48 | `/liquid` | ORTA | yanıltıcı | 6-DOF, kendi beyan ettiği geçerlilik sınırının 6 katı hücum açısında koşmaya devam ediyor |
| T49 | `/solid` | ORTA | yanıltıcı | Varsayılan inhibitör düzeni sayfanın kendi 'BATES (neutral)' yardımıyla çelişiyor |
| T50 | `/solid` | ORTA | sahte gösterge | 'Computing trajectory...' metni iş bittikten 25 saniye sonra da ekranda |
| T51 | `/solid` | ORTA | anlamsız | c* girdisi kabul ediliyor ama değeri hiç kullanılmıyor (5,9 kat aralık, sıfır etki) |
| T52 | `/solid` | ORTA | eksik | Performans panosundaki çift eksenli iki alt grafikte efsane (legend) yok |
| T53 | `yardımcı` | ORTA | eksik | "Resolve site" düğmesinin %68'i ölçek çubuğunun altında kalıyor, fare ile tıklanamıyor |
| T54 | `yardımcı` | ORTA | yanıltıcı | Karo önbelleği göstergesi 25 karo indirildikten sonra hâlâ "0 MB · 0 tile" diyor ve NASA GIBS atfı hiç görünmüyor (refreshTileUsage yalnız açılışta çağrılıyor) |
| T55 | `yardımcı` | ORTA | birim/ölçek yanlış | Formül sayfası §1.5: iki kütle debisi ifadesi boyutsal olarak tutarsız (kg/m ve kg^0,5·m^0,5 çıkıyor, kg/s değil) |
| T56 | `/hybrid` | DÜŞÜK | eksik | Çalışma noktası panosunun üç zaman grafiğinde hiç eksen başlığı ve birim yok |
| T57 | `/hybrid` | DÜŞÜK | dil | Türkçe modda beş metin İngilizce kalıyor (karışık dil) |
| T58 | `/hybrid` | DÜŞÜK | anlamsız | Parametrik duyarlılık taramasında 'Thrust' alt grafiği tanımı gereği sabit — bilgi taşımıyor |
| T59 | `/hybrid` | DÜŞÜK | eksik | Find Optimum sırasında Cantera geçerlilik aralığı aşılıyor, arayüzde hiçbir iz yok |
| T60 | `/hybrid` | DÜŞÜK | yanıltıcı | Toplam motor boyu tabloda ve çizimlerde farklı (1661,6 mm ↔ 1676 mm) |
| T61 | `/hybrid` | DÜŞÜK | yanıltıcı | Statik hesap sonrası panoya 'Real-Time' başlığı — bölüm başlığıyla ve verinin doğasıyla çelişiyor |
| T62 | `/liquid` | DÜŞÜK | yanıltıcı | 'Total Impulse' alt sekmesi toplam impulsle ilgisiz beş grafik barındırıyor |
| T63 | `/liquid` | DÜŞÜK | anlamsız | Aynı irtifa eğrisi iki ayrı grafikte, farklı çözünürlükte çiziliyor |
| T64 | `/liquid` | DÜŞÜK | dil | Türkçe modda karışık dil: 'Çarpışmalı çiftler (angle not reported)' |
| T65 | `/liquid` | DÜŞÜK | eksik | Boş eksen başlığı ve niteliksiz iki farklı 'Overall' verim |
| T66 | `/solid` | DÜŞÜK | yanıltıcı | Rıhtım sayı alanlarında 17 basamaklı ham kayan nokta artığı |
| T67 | `/solid` | DÜŞÜK | yanıltıcı | Yörünge panosunda gösterge başlığı çakışması ve figürde adsız boş iz |
| T68 | `/solid` | DÜŞÜK | yanıltıcı | Yörüngede açıklanmayan paraşüt varsayımı: 4,11 km'lik iniş 750 saniye sürüyor |
| T69 | `/solid` | DÜŞÜK | yanıltıcı | End-burner itki ekseninde sıfır bastırılmış: %0,4 değişim dik düşüş gibi görünüyor |
| T70 | `/solid` | DÜŞÜK | eksik | Kesitte BATES segment boşlukları çizilmiyor, grain tek blok görünüyor |
| T71 | `/solid` | DÜŞÜK | dil | TR çeviri hatası: 'Web Thickness' -> 'Ağ Kalınlığı' |
| T72 | `yardımcı` | DÜŞÜK | eksik | "User Guide" düğmesi üç sayfadan ikisinde hiç görünmüyor; /launch-site üç kabuk betiğini de boşuna indiriyor |
| T73 | `yardımcı` | DÜŞÜK | dil | İngilizce arayüzde Türkçe metin: hazır saha listesinde "Mount Everest (yüksek arazi)" |
| T74 | `yardımcı` | DÜŞÜK | dil | /launch-site TR modunda dört dizge İngilizce kalıyor (araç rozeti, araç notu, karo göstergesi, saha listesi) |
| T75 | `yardımcı` | DÜŞÜK | birim/ölçek yanlış | Ana sayfa "Recent Projects" şeridinde CSS text-transform SI birim simgelerini büyütüyor: "ISP 207.1 S · IT 13428 N·S" (S = siemens, saniye değil) |
| T76 | `yardımcı` | DÜŞÜK | eksik | /formulas sayfasında dil seçici hiç yok (diğer iki sayfada var) ve künye başka marka taşıyor: "UZAYTEK" |

---

## Bulgu ayrıntıları

### T01 — KRİTİK — PDF raporunun yönetici özeti itki, Isp ve yanma süresini 0.0 basıyor

**Sayfa:** `/liquid` · **Bileşen:** PDF Summary Report / PDF Complete Report — Executive Summary sayfası · **Hüküm:** yanıltıcı

**Kanıt:** Ekran: itki 10000 N, deniz sev. Isp 244,9 s, vakum Isp 337,4 s, yanma 400 s. Aynı sonuçtan üretilen PDF s.2: 'Maximum Thrust: 0.0 N  Specific Impulse: 0.0 s  Burn Time: 0.0 s  Total Impulse: 0.0 N·s'. Aynı PDF s.4 tablosu ise aynı satırlara 'N/A' yazıyor (belge içi çelişki). Aynı koşudaki Excel doğru: 10000,0 N / 244,86 s / 337,36 s → hata yalnız PDF performans yolunda. s.3'te ayrıca 'Propellant Type: N/A (not reported by solver)' derken alt satırlar 'Oxidizer: lox / Fuel: rp1' diyor. Ekran görüntüsü: scratchpad/faz6/sivi/16_export_sonrasi.png ; dosyalar: sivi/indirilen/liquid_motor_summary_1785755111612.pdf (s.2, s.4), sivi/indirilen/liquid_motor_complete_1785755113869.pdf (s.2), sivi/indirilen/UZAYTEK_LIQUID_analysis_2026-08-03.xlsx

**Tekrar üret:** /liquid → 'Calculate Engine Performance' → sonuç gelince 'PDF Summary Report' düğmesi → inen PDF'in 2. sayfasını aç.

**Dosya ipucu:** hrma/templates/liquid.html:4393 exportPDF() → analysisResults=window.currentResults; rapor üreticisi max_thrust/specific_impulse/burn_time anahtarlarını bulamıyor (yanıtta thrust / isp_sea_level / burn_time var)

### T02 — KRİTİK — 6-DOF uçuş paneli roket denklemini 3,25x ihlal eden bir tepe yüksekliği raporluyor

**Sayfa:** `/liquid` · **Bileşen:** FLIGHT DYNAMICS — 6-DOF STABILITY paneli, 'Run 6-DOF' (#sd_run) · **Hüküm:** fiziksel imkânsız

**Kanıt:** Panel girdileri: kuru 8 kg + itici 4 kg = 12 kg, Thrust 1200 N, Burn 6 s, 'use computed thrust curve' açık. Motor Isp(SL)=244,86 s. Tsiolkovsky üst sınırı (yerçekimi ve sürüklenme SIFIR kabul): dv = 244,86*9,80665*ln(12/8) = 973,6 m/s → Mach ~3,25, balistik tepe 48,3 km. Panel RAPORLUYOR: 'APOGEE 157.32 km @ 180.7 s', 'MAX MACH 10.00' (ölçülen iz: irtifa 0…157321,7 m; Mach 0,0147…9,963). Aşım: yükseklik 3,25x, hız 3,07x. Ters hesap: 12 kg aracı Mach 9,96'ya (2989 m/s) çıkarmak ~29900 N·s ister; 4 kg iticiden bu Isp=762 s demektir (kimyasal üst sınır ~465 s). Grafikte Mach tepesi t≈6 s'te, yani form yanma süresinde; ama itki 1200 N değil motorun 10000 N'u (1200 N×6 s=7200 N·s yalnız 720 m/s → Mach 2,4 / 26 km verirdi). 10000 N×6 s=60000 N·s'yi 4 kg'dan almak Isp=1530 s demek. Ek olarak Body Diameter 0,1 m girili, motorun nozul çıkışı 217,87 mm (nozul gövdeden 2x geniş) — işaretlenmiyor. Ekran görüntüsü: scratchpad/faz6/sivi/26_6dof_irtifa.png ; ölçüm: sivi/sixdof.json

**Tekrar üret:** /liquid → 'Calculate Engine Performance' → sayfada aşağı in → 'FLIGHT DYNAMICS — 6-DOF STABILITY' panelini aç → girdilere DOKUNMADAN 'Run 6-DOF'.

### T03 — KRİTİK — Form kütle bloğu çözücünün tam 3 katı yakıt gösteriyor

**Sayfa:** `/solid` · **Bileşen:** #propellant_mass / #dry_mass / #wet_mass (Form bölüm 7 "Mass & Weight Breakdown") · **Hüküm:** yanıltıcı

**Kanıt:** Tek koşuda ekranda aynı anda: yakıt 19,833 kg (form) vs 6,611 kg (çözücü, oran tam 3,000); kuru 4,300 vs 20,409 kg; ıslak 24,133 vs 27,020 kg. 6,611/27,020 değeri motor tablosu, Excel, .eng ve CAD sekmesinde de aynı — tek aykırı yer form. Tüm geometrilerde aynı yönde: star 3,36x, finocyl 3,39x, slotted 3,93x, wagon_wheel 3,24x, end_burner 2,73x. Ekran görüntüsü: scratchpad/faz6/kati/b1_kutle_blogu_19kg.png ; ham veri: kati/cstar_kutle.json, kati/yardimci.json

**Tekrar üret:** /solid aç -> Calculate Motor Performance -> bölüm 7 'Propellant Mass' (19,833 kg) ile Motor Specifications 'Propellant Mass' (6,611 kg) satırını karşılaştır.

**Dosya ipucu:** hrma/templates/solid.html:2646-2700 (calculatePropellantMass; `const totalVolume = grainVolume * grainCount;`)

### T04 — KRİTİK — c* yardımcı düğmesi fiziksel olarak imkânsız 508,7 m/s üretiyor (üs tersine alınmış)

**Sayfa:** `/solid` · **Bileşen:** Bölüm 1 'Characteristic Velocity (m/s)' altındaki Calculate düğmesi · **Hüküm:** fiziksel imkânsız

**Kanıt:** Düğme alanı 1550 -> 508,7 m/s yapıyor. Aynı sayfada çözücü ve yakıt kataloğu c*=1472,5 m/s. APCP için 509 m/s imkânsız (1400-1600 m/s bandı). Kodda ((γ+1)/2)^exp kullanılmış, doğrusu (2/(γ+1))^exp: γ=1,25 için 1,6989 vs 0,58862, oran 2,886; 508,7 x 2,886 = 1468 m/s (katalogla %0,3 uyumlu). Ekran görüntüsü: scratchpad/faz6/kati/b2_cstar_508.png ; ham veri: kati/yardimci.json

**Tekrar üret:** /solid -> bölüm 1 -> 'Characteristic Velocity' alanının altındaki Calculate düğmesine bas -> alan 508,7 oluyor.

**Dosya ipucu:** hrma/templates/solid.html:2631-2644 (calculateCharVelocity, `Math.pow((gamma + 1) / 2, exponent)`)

### T05 — KRİTİK — Yörünge, motorun taşımadığı 19,8 kg yakıtı yakıyor (örtük Isp 66 s)

**Sayfa:** `/solid` · **Bileşen:** Trajectory Analysis paneli — #traj_initial_mass / #traj_final_mass ön-dolumu · **Hüküm:** fiziksel imkânsız

**Kanıt:** Hesap sonrası ön-dolan değerler: Initial (Wet) 24,133 kg, Final (Dry) 4,300 kg (yani B1'in hatalı form kütleleri). Çözücünün gerçek değerleri 27,020 / 20,409 kg. Yörünge 19,833 kg yakıt harcıyor, motorda 6,611 kg var. Örtük Isp = 12909,3 N·s / (19,833 kg x 9,81) = 66 s; sayfanın aynı koşuda gösterdiği Isp 199,1 s (3 kat çelişki). Panel yine de apoje 4,11 km ilan ediyor. Ekran görüntüleri: kati/yorunge.png, kati/yorunge_paneli_tam.png ; ham veri: kati/son_kontroller.json

**Tekrar üret:** /solid -> Calculate -> Trajectory Analysis paneline in -> Initial (Wet) Mass 24,133 ve Final (Dry) Mass 4,300 -> fark 19,833 kg, oysa Motor Specifications yakıt kütlesi 6,611 kg.

**Dosya ipucu:** hrma/templates/solid.html — yörünge ön-dolumu #wet_mass/#dry_mass form alanlarından okuyor (kaynak hata: calculatePropellantMass, satır 2646-2700)

### T06 — KRİTİK — Motor kesitinin radyal ölçüleri girdilerden tamamen bağımsız (grain Ø60 -> Ø96 çiziliyor)

**Sayfa:** `/solid` · **Bileşen:** #solid_motor_kesit — 'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY', y ekseni 'Radius (mm)' · **Hüküm:** birim/ölçek yanlış

**Kanıt:** İz y değerleri ölçüldü (mm): grain dış çapı 60 mm girildiğinde çizim Ø96,0 (%60 hata). Yalıtım 0,5/3/20 mm -> çizilen 1,82/1,92/2,60 mm. Kasa cidarı 1/8/30 mm -> hepsinde 4,77 mm. Astar 2/15 mm -> ikisinde de 1,92 mm. Örüntü sabit kesir: grain_dış=0,96·R_delik, astar_dış=0,996·R_delik, kasa_dış=1,09·R_delik. Aynı koşuda .eng ve CAD sekmesi kasa dış çapını 122 mm derken çizim 115,54 mm çiziyor. Kıyas: indirilen DXF doğru ($INSUNITS=4 mm; 53,0 ve 61,0 yarıçapları). Ekran görüntüleri: kati/b3_kesit_grainOD60.png, kati/bates_kesit.png ; ham veri: kati/kesit_olcek.json, kati/kesit_inhibitor.json

**Tekrar üret:** /solid -> 'Outer Diameter' 100 -> 60 -> Calculate -> kesitte grain hâlâ kasayı dolduruyor, y ekseninden 48 mm yarıçap ölçülüyor. Ardından 'Case Wall Thickness' 8 -> 30 -> Calculate -> çizilen cidar 4,77 mm'de kalıyor.

**Dosya ipucu:** hrma/visualization/visualization.py:3398-3401 (`wall_case = ... 0.045 * D_ch`, `liner_t = min(max(0.02 * D_ch, 1.5), 5.0)`) ve :3466 (`grain_r = [r_p0, r_go, ...]`, `r_go = rc - liner_t`)

### T07 — KRİTİK — 'Final port Ø99,8 mm' etiketi hesap değil yer tutucu; çözücünün gerçek son portu ≈65 mm

**Sayfa:** `/solid` · **Bileşen:** #solid_motor_kesit — kırmızı kesikli 'Final port' izi ve efsane girdisi · **Hüküm:** sahte gösterge

**Kanıt:** Etiket değeri = (çizilen grain yarıçapı − 1 mm): 50,88−1=49,88 -> Ø99,76 ≈ 99,8. Varsayılan yapılandırmada dış yüzey de yandığı için tükenme koşulu 15+w = 50−w -> w=17,5 mm -> gerçek son port 65 mm. Üç bağımsız doğrulama: (1) tb=1,0244 s x ort. yanma hızı ~17 mm/s = 17,4 mm web; (2) uygulamanın kendi uyarısı '18,36 mm/s at 40 bar'; (3) çözücünün son yanma alanı 1761,9 cm², iki cepheli modelin kapalı formu 1756 cm² (%0,3 sapma; tek cepheli senaryo 4066 cm² verirdi). Etiket inhibitör kutusu değiştirilse de 'Ø99,8 mm' kalıyor (iki senaryonun gerçek son portu 65 ve 100 mm). Ekran görüntüsü: kati/bates_kesit.png ; ham veri: kati/kesit_inhibitor.json

**Tekrar üret:** /solid -> Calculate -> kesit efsanesinde 'Final port Ø99.8 mm' -> 'Inhibitor Coating / Outer Surface' kutusunu işaretle -> Calculate -> etiket değişmiyor.

**Dosya ipucu:** hrma/visualization/visualization.py:3411 (`r_pf = min(r_pf, r_go - 1.0)`) ve :3489-3494 (efsane adı)

### T08 — KRİTİK — "Fly this site" düğmesi hiçbir koşulda çalışmıyor: iki çakışan num() bildirimi yüzünden 8 alan "--" dizgesi olarak gidiyor, sunucu 422 dönüyor

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → #ls-fly (Fly this site) · **Hüküm:** eksik

**Kanıt:** Ölçüldü: POST /api/six-dof-analysis her denemede HTTP 422. Giden gövde: {"body_diameter":"--","body_length":"--","dry_mass":"--7","cd0":"--","fin_count":"--","fin_span":"--","launch_elevation_deg":"--","launch_azimuth_deg":"--",...}. Sunucu: invalid_six_dof_input, 8 alan "not_a_number". DOM'daki girdi değerleri ise DOĞRU: 0.15 / 3.0 / 18 / 0.45 / 4 / 0.11 / 84 / 90. Kök neden: aynı IIFE kapsamında iki `function num` bildirimi — launch_site.html:444 okuyucu `num(id, fb)`, launch_site.html:792 biçimlendirici `num(v, d)`; hoisting'de sonuncu kazanıyor, `num('ls-a-bodydia',0.15)` → isFinite('ls-a-bodydia')=false → '--'. "dry_mass":"--7" imzası ('--' + engine_inert 7) kök nedeni tek başına kanıtlıyor. Aynı yük doğru tiplerle curl ile gönderildiğinde çözücü 0,31 s'de status:success, apoje 15722,7 m döndü — yani sorun tamamen istemcide. Ekran görüntüleri: scratchpad/faz6/yardimci/ls_fly_hata.png, ls_ucus_sonrasi.png

**Tekrar üret:** http://127.0.0.1:8084/launch-site aç → hiçbir alana dokunma → "Fly this site" düğmesine bas. Ağ sekmesinde POST /api/six-dof-analysis → 422. Panelde "The flight solver returned an error." yazar, oynatım kapalı kalır.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/launch_site.html:444 ve :792 (ayrıca tüketiciler :676-691)

### T09 — CİDDİ — Toplam impuls İngilizce arayüzde 1000 kat yanlış okunacak biçimde yazılıyor

**Sayfa:** `/hybrid` · **Bileşen:** Girdi paneli — #calculated_impulse (Calculated Total Impulse) · **Hüküm:** birim/ölçek yanlış

**Kanıt:** Üç motor tanımıyla ölçüldü: 1000 N × 10 s = 10.000 N·s gerçek değer → ekranda '10.000 N⋅s'; 5000 N × 30 s = 150.000 N·s → ekranda '150.000 N⋅s'. Sayfa dili document.documentElement.lang='en', tarayıcı yereli navigator.language='tr-TR', (150000).toLocaleString()='150.000' olarak ölçüldü. Aynı sayfanın tasarım raporu doğru biçimi kullanıyor: 'Total Impulse 10000 N·s'. Ekran görüntüsü: scratchpad/faz6/hibrit/hibrit_toplam_impuls_girdi.png

**Tekrar üret:** /hybrid aç → İtki alanına 5000, Burn Time alanına 30 yaz → BASIC PARAMETERS altındaki 'Calculated Total Impulse:' satırını oku. Noktayı binlik ayırıcı kullanan her işletim sistemi yerelinde (tr, de, es, it, nl, pt) yeniden üretilir.

**Dosya ipucu:** hrma/templates/advanced.html:2397

### T10 — CİDDİ — Tane boyu 2B kesitte ve 3B modelde sessizce %8 kırpılıyor (imalat kontrolü için önerilen çizimde)

**Sayfa:** `/hybrid` · **Bileşen:** motor_plot (MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY) + 3B parametrik deck · **Hüküm:** yanıltıcı

**Kanıt:** Aynı sayfa yüklemesinde: tasarım raporu 'Grain Length 1512.8 mm', 2B kesit etiketi 'Grain = 1451 mm' (ölçülen iz uzunluğu 1450,59 mm), 3B deck 'GRAIN 1451 mm'. Fark 61,8 mm (%4,1). Hangisinin doğru olduğunu yakıt kütlesiyle çapraz doğruladım (port 37,785→53,246 mm, ρ=920 kg/m³): L=1512,8 mm → 1,539 kg, L=1450,6 mm → 1,475 kg; raporun kendi yazdığı yakıt kütlesi 1,54 kg. Yani 1512,8 mm doğru, çizimler kısa. Kırpma sabiti doğrulandı: 0,92 × 1576,7 mm (oda boyu) = 1450,6 mm = ölçülen değer. Ekran görüntüleri: .../faz6/hibrit/hibrit_kesit_tane_boyu.png ve .../faz6/hibrit/I_3b_deck.png

**Tekrar üret:** /hybrid → Calculate → kesit çizimindeki 'Grain = …' etiketini Grain Design tablosundaki 'Grain Length' satırıyla karşılaştır. Grafiğin alt yazısı kullanıcıyı bu çizimle imalat öncesi kontrol yapmaya yönlendiriyor.

**Dosya ipucu:** hrma/visualization/visualization.py:3406 (L_g = min(L_g, 0.92 * L)) ve hrma/static/js/motor_viz3d.js:412 (Lg = Math.min(Lg, 0.92 * Lch))

### T11 — CİDDİ — 'Tank' basınç çubuğu kullanıcının girdiği tank basıncını hiç göstermiyor (düzeltme ölü kod)

**Sayfa:** `/hybrid` · **Bileşen:** performance_plots — Pressure Distribution alt paneli · **Hüküm:** yanıltıcı

**Kanıt:** Tank basıncı 30 / 50 / 90 bar girilerek üç kez ölçüldü; çubuk üçünde de sabit 24,0 bar (= oda 20 + enjektör ΔP 4). 30 bar girildiğinde 24 bar göstermesi etiketin yanlış olduğunu tek başına kanıtlar. Çözücü değeri biliyor: aynı sayfadaki kavitasyon uyarısı K_c=-0,01 (P_v=50,4 bar) diyor, bu ancak P1=50 bar ile çıkar. /calculate API yanıtı tank=30 ve tank=90 ile çağrıldı: motor sözlüğünde 'tank' içeren anahtar YOK ([]), bu yüzden visualization.py'deki 'tank is None' geri-düşüşü %100 çalışıyor. Ekran görüntüsü: .../faz6/hibrit/hibrit_basinc_dagilimi.png

**Tekrar üret:** Tank Pressure alanına 90 yaz → Calculate → PERFORMANCE ANALYSIS DASHBOARD → 'Pressure Distribution' panelindeki 'Tank' çubuğunu oku (24,0 bar çıkar).

**Dosya ipucu:** hrma/visualization/visualization.py:1174-1182 (düzeltme mevcut ama motor_data'da tank_pressure anahtarı yok); bekçi testi tests/test_viz_parity.py:142 yalnız etiketleri doğruluyor, değerleri değil

### T12 — CİDDİ — Trajectory Analysis, motorun kendi özgül itkisini 4,5 kat ihlal eden bir uçuş simüle ediyor

**Sayfa:** `/hybrid` · **Bileşen:** trajectory_plot — Trajectory Analysis paneli · **Hüküm:** fiziksel imkânsız

**Kanıt:** Calculate'ten önce ve SONRA girdi alanları okundu, hiçbiri motor sonucuyla eşitlenmiyor: initial_mass 50 kg, final_mass 25 kg (değişmedi). Bu 25 kg itici demek; motorun raporladığı itici kütlesi 5,46 kg. 25 kg / 10 s / 1000 N ⇒ ima edilen Isp = 1000/(2,5×9,80665) = 40,8 s; motorun ilan ettiği Isp 185,6 s (4,5 kat ihlal). Referans alan varsayılanı 100.000 mm² = Ø357 mm gövde, motorun oda çapı ise 79,9 mm; alanın kendi yardım metni '17671 mm² equals a 150 mm diameter body' diyor. Görünür sonuç: aynı sayfada Trajectory apoje 1,09 km / 127,4 m/s, 6-DOF apoje 8,31 km / Mach 1,76 (7,6 kat fark). Ayrıca 'Flight Path' X ekseni 'Range (km)' ama veri 0–1,59e-16 km (özdeş sıfır). Ekran görüntüsü: .../faz6/hibrit/J_yorunge.png

**Tekrar üret:** Calculate → Analysis Type: Trajectory Analysis → Calculate Trajectory Performance → Initial/Final Mass alanlarını motorun Total/Dry Mass değerleriyle, apojeyi de Run 6-DOF apojesiyle karşılaştır.

**Dosya ipucu:** hrma/templates/advanced.html:1508 (initial_mass value=50), :1518 (final_mass value=25), :1541 (reference_area value=100000)

### T13 — CİDDİ — 3B tank görünümünde girdap önleyici düzenek 1000x küçük çiziliyor (0,26 mm)

**Sayfa:** `/liquid` · **Bileşen:** tankVisualization — 'Propellant Tank System - 3D CAD View' · **Hüküm:** birim/ölçek yanlış

**Kanıt:** Çözücü çapı METRE yayınlıyor (liquid_rocket_engine.py:5641,5652 'av_diameter = diameter * TANK_ANTIVORTEX_D_RATIO  # m'); şablon MİLİMETRE varsayıp 2000'e bölüyor (liquid.html:3168 'antiVortex.diameter / 2000'). Ölçülen mesh3d uzanımı: 'Anti-Vortex Device' x = ±0,00012943 m → 0,259 mm; aynı grafikteki 'Oxidizer Tank' x = ±0,43145 m → 862,9 mm (doğru). Olması gereken 0,3×862,9 = 258,87 mm; çizilen 0,259 mm → tam 1/1000. Aynı sözlükte vane_radial_length_mm=129,43 ve vane_thickness=3 mm doğru birimde, yalnız diameter/height metre. Sonuç: efsanede adı geçen cisim görselde hiç yok. Ekran görüntüleri: scratchpad/faz6/sivi/11_tank_3d.png ve sivi/24_girdap_onleyici_yakin.png (yakınlaştırma: tank dibinde yalnız çıkış borusu var) ; ölçüm: sivi/final.json→tank_efsane.av_iz, sivi/ham.json→tank

**Tekrar üret:** 'Calculate Engine Performance' → 'Total Impulse' alt sekmesi → sayfa altındaki 'Propellant Tank System - 3D CAD View' grafiği.

**Dosya ipucu:** hrma/templates/liquid.html:3167-3169 ↔ hrma/engines/liquid_rocket_engine.py:5651-5653 (aynı yanlış varsayım hrma/export/cad_export.py:247-248'de de var: "diameter = av_config['diameter']  # mm")

### T14 — CİDDİ — Sıvı oksijenin yoğunluğu gaz fazı değeriyle (1,31 kg/m³) 'gerçek zamanlı NIST verisi' olarak gösteriliyor

**Sayfa:** `/liquid` · **Bileşen:** Panel 1 PROPELLANT DATA — 'Oxidizer Density ρox (kg/m³)' alanı + 'Real-time Data' kartı · **Hüküm:** fiziksel imkânsız

**Kanıt:** Sayfa açılışında /api/get-propellant-properties dönüyor: density=1.3087864284209203, viscosity=2.0550207325996687e-05, cryogenic=true, formula=O2, data_source='CoolProp (NIST REFPROP-based)'. 1,309 kg/m³ 25°C/1 atm'deki GAZ oksijendir (PM/RT=1,308); 90,2 K'deki LOX 1141 kg/m³'tür. Bu değer form alanına YAZILIYOR (liquid.html:2069-2081). Ölçülen: form alanı 1,3087864284209203 kg/m³ ↔ çözücünün gerçekte kullandığı currentResults.oxidizer_density = 1141,7 kg/m³ → 872x fark. Sayfanın kendi resetForm() öntanımlısı 1141 (doğru) — yükleme anında yanlışla eziliyor. Doğrulama: tank hacimleri 1141,7 ile tutarlı (ox 1261,6 L / yakıt 720,2 L). Hesaptan SONRA uyarı paneli dürüstçe 'value ... is outside the accepted range 20-2500 kg/m3 and was ignored' diyor; hesap öncesi HİÇBİR uyarı yok, üstelik yeşil 'Real-time Data' ve 'NIST WEBBOOK CONNECTED' rozetleriyle sunuluyor. Viskozite de gaz fazı (2,06e-5 vs LOX ~1,9e-4 Pa·s). Ekran görüntüsü: scratchpad/faz6/sivi/acilis.png (Panel 1) ; ölçüm: sivi/panel.json→ox_rho_cozucu

**Tekrar üret:** /liquid sayfasını aç, hiçbir şeye dokunma; Panel 1'deki 'Oxidizer Density ρox (kg/m³)' alanına ve altındaki yeşil 'Real-time Data' kartına bak.

**Dosya ipucu:** hrma/templates/liquid.html:2069-2081 (props.density'yi form alanına yazan blok); hrma/app.py:5408 get_propellant_properties

### T15 — CİDDİ — İrtifa grafiğinde 'Isp vs Altitude' eğrisi tümüyle görünmez (itki eğrisi %100 örtüyor)

**Sayfa:** `/liquid` · **Bileşen:** altitude_plot — 'Engine Performance vs Altitude' · **Hüküm:** yanıltıcı

**Kanıt:** Efsane iki seri vaat ediyor (camgöbeği 'Isp vs Altitude' sol eksende, turuncu 'Thrust vs Altitude' sağ eksende) ama grafikte tek turuncu eğri var. Sebep ölçüldü: sabit ṁ'de Isp=F/(ṁg0) olduğundan iki seri birebir orantılı — Isp/Thrust = 24,486335 sekiz noktanın HEPSİNDE aynı. İki y ekseni ayrı otomatik ölçeklendiği için her nokta aynı piksele düşüyor. Eksen kesirleri: 0 km → sol 0,065625000 / sağ 0,065625000 (fark 1,3e-16); 10 km → 0,707167781 / 0,707167781 (2,2e-16); 100 km → 0,934375000 / 0,934375000 (1,1e-16). Maksimum fark 4,4e-16 (kayan nokta gürültüsü). Ekran görüntüsü: scratchpad/faz6/sivi/05_irtifa_grafigi.png ; ham veri: sivi/ham.json→irtifa.altitude_plot

**Tekrar üret:** 'Calculate Engine Performance' → 'ALTITUDE PERFORMANCE ANALYSIS' panelindeki grafiğe bak; efsanede iki seri, çizimde bir eğri.

### T16 — CİDDİ — İmalat çizimi, emniyet marjı negatif olan cidarı 'basınç yüküne karşı doğrulandı' diye damgalıyor

**Sayfa:** `/liquid` · **Bileşen:** DXF Drawing ve Technical Drawings PDF dışa aktarımları · **Hüküm:** yanıltıcı

**Kanıt:** DXF TEXT varlığı: 'WALL THICKNESS = 5.00 mm [structural analysis (as-designed wall thickness, verified against the pressure load) [chamber_structure]]'. Aynı koşunun yapısal sonucu: hoop_stress 61,62 MPa > allowable_stress 46,15 MPa; required_wall_thickness 6,677 mm > tasarlanan 5 mm; stress_margin = -33,54. Uygulamanın KENDİ uyarı paneli doğru söylüyor: 'Chamber wall thickness 5 mm is below the 6.68 mm required for Stainless steel 304 (annealed) at safety factor 2.5; the reported stress margin is negative.' Aynı ibare Technical Drawings PDF s.3'te de var. Atölyeye giden çizim, uygulamanın kendi uyarısıyla çelişiyor. Dosyalar: scratchpad/faz6/sivi/indirilen/UZAYTEK_LIQUID_profile.dxf, sivi/indirilen/UZAYTEK_LIQUID_technical_drawings.pdf ; ölçüm: sivi/son.json→duvar.cr_req.chamber_structure

**Tekrar üret:** 'Calculate Engine Performance' → 'DXF Drawing' → inen dosyada 'WALL THICKNESS' metnini ara (ezdxf ile TEXT varlıkları) → sonuç sayfasındaki uyarı paneliyle karşılaştır.

### T17 — CİDDİ — Belirsizlik (UQ) paneli /liquid sayfasından hiç çalışmıyor: motor_type gönderilmiyor

**Sayfa:** `/liquid` · **Bileşen:** UNCERTAINTY sekmesi → 'Run Uncertainty Analysis' (#ad_run_uncertainty / #uq_run) · **Hüküm:** ağ hatası

**Kanıt:** Başarılı bir hesaptan SONRA bile: POST /api/uncertainty-analysis → 400, gövde: {"error":"motor_type must be one of ['hybrid', 'solid', 'liquid']; got None.","status":"error"}. Sunucu 'liquid' değerini kabul ediyor (hata mesajı bunu listeliyor); istemci alanı hiç koymuyor. Monte Carlo belirsizlik kestirimi bu sayfadan HİÇBİR koşulda koşturulamıyor. Konsolda 'Failed to load resource: 400 (BAD REQUEST)' düşüyor. Karşılaştırma: aynı türden diğer iki 400 MEŞRU kapıdır ve panelde düzgün açıklanıyor (validation/upload-csv → 'No CSV content provided'; comparative-analysis → 'At least 2 motor configurations are required') — onlar bulgu değil. Ölçüm: scratchpad/faz6/sivi/e400.json→ag ; sivi/son.log konsol hataları

**Tekrar üret:** 'Calculate Engine Performance' → 'UNCERTAINTY' sekmesi → 'Run Uncertainty Analysis' → panelde 'ERROR: motor_type must be one of ...' beliriyor.

### T18 — CİDDİ — 3B performans haritası N2O/HTPB yüzeyi çiziyor, üstüne RP-1/LOX tasarım noktasını basıyor

**Sayfa:** `/liquid` · **Bileşen:** PERFORMANCE sekmesi → '3D Performance Map: Chamber Pressure vs O/F vs Isp' · **Hüküm:** yanıltıcı

**Kanıt:** Sayfa RP-1/LOX çift iticili sıvı motor tasarlıyor. Grafiğin alt başlığı: 'Chemical-equilibrium sweep, 49/49 nodes solved | N2O / HTPB (reference pair — propellant identity not supplied)'. N2O/HTPB bir HİBRİT çifttir. Buna rağmen aynı grafikte kırmızı 'Design point (motor result)' izi Pc=100 bar, O/F=2,5 noktasına — yani RP-1/LOX motorun tasarım noktasına — basılıyor. 'Sweep maximum' O/F=6'da (N2O/HTPB için makul, bu motorun optimumu 2,807). İki farklı itici sisteminin sayıları tek 3B grafikte üst üste; tasarım noktasının yüzeye göre konumu hiçbir şey ifade etmiyor. Ölçüm: scratchpad/faz6/sivi/final.json→n2o (başlık + üç izin adı ve koordinatı); sivi/panel.json→PERFORMANCE satırı

**Tekrar üret:** 'Calculate Engine Performance' → 'PERFORMANCE' sekmesi → 'Run Analysis' → 3B grafiğin alt başlığını oku.

**Dosya ipucu:** hrma/visualization/visualization.py:2618-2622 (prop_supplied yanlışsa 'reference pair' etiketi ekleniyor ama tasarım noktası yine çiziliyor)

### T19 — CİDDİ — Monte Carlo 'Peak Pressure' istatistiği 300 koşuda sıfır sapmalı (yapısal olarak sabit)

**Sayfa:** `/solid` · **Bileşen:** Monte Carlo Analysis paneli — 'Peak Pressure' kutusu ve kabul ölçütü · **Hüküm:** sahte gösterge

**Kanıt:** 300 örneklem (a ±%3, n ±0,005, ρ ±%1, C* ±%1): İtki 12591±513 N (CV %4,1), Isp 199,1±2,0 s, yanma süresi 1,03±0,04 s, ama Tepe Basınç 40,0 ± 0,0 bar, CV %0,0, [p5,p95]=[40,0 , 40,0]. Sebep ölçüldü: basınç eğrisi her zaman tam girdi Pc'den başlıyor ve monoton azalıyor — girdi 40 -> ilk nokta 40,000000 (fark 7,1e-15); 70 -> 70,000000 (1,4e-14); 12 -> 12,000000 (0,0). Dolayısıyla 'tepe basıncı ≤ nominal x1,2' kabul ölçütü hiç başarısız olamaz ama %98,3 başarı oranına dahil ediliyor. Ekran görüntüsü: kati/monte_carlo.png ; ham veri: kati/analiz_docku.json, faz6/son_cikti.txt

**Tekrar üret:** /solid -> Calculate -> Analysis Dock -> Monte Carlo -> Run Analysis -> 'Peak Pressure' kutusunda σ=0,0 bar. Sonra 'Chamber Pressure' 40 -> 70 yap, Calculate, basınç grafiğinin ilk noktası tam 70,000000.

**Dosya ipucu:** hrma/engines/solid_rocket_engine.py:3937 civarı (`nom_pmax = float(np.max(nominal['thrust_curve']['pressure']))`) — basınç eğrisinin t=0 değerinin tasarım Pc'sine sabitlenmesi kök neden

### T20 — CİDDİ — 'Specific Impulse vs Altitude' grafiği 2 piksellik alana sıkışıyor, eksen etiketleri çakışıyor

**Sayfa:** `/solid` · **Bileşen:** #altitude_plot ('Altitude Performance' paneli) · **Hüküm:** yanıltıcı

**Kanıt:** Hesap sonrası ölçüldü: kap yüksekliği 422 px, Plotly SVG 140 px, çizim alanı (.bg) 2 px. Eğri (Isp 214,2 -> 287,3 s, 0-100 km) düz çizgiye iniyor, y ekseni etiketleri üst üste basılıyor, kabın 280 pikseli boş. Rıhtım sekmesi değiştirilse de düzelmiyor (THERMAL/VALIDATION denendi, hâlâ 2 px). Yalnız pencere yeniden boyutlandırılınca düzeliyor (viewport 1500->1200: SVG 422 px, çizim alanı 242 px). Ekran görüntüsü: kati/irtifa_once.png, kati/dock_VALIDATION.png ; ham veri: kati/irtifa_relayout.json

**Tekrar üret:** /solid -> Calculate -> 'Altitude Performance' paneline in -> grafik düz çizgi ve çakışık etiketler; pencereyi yeniden boyutlandır -> düzeliyor.

### T21 — CİDDİ — '3D CAD Design' panelinin grafiği hesap bittikten sonra da 'NO DATA' gösteriyor

**Sayfa:** `/solid` · **Bileşen:** #cad_visualization ('3D CAD Design' paneli) · **Hüküm:** eksik

**Kanıt:** Başarılı hesaptan ve '3D Visualization' düğmesine basıldıktan 60 s sonra bile: innerHTML.length = 0, canvas = 0, görünür yükseklik 140 px, içinde 'NO DATA — RUN ANALYSIS TO GENERATE THIS PLOT' yer tutucusu; konsol hatası ve 4xx/5xx yok. 3B model aslında aşağıdaki 'Motor Specifications -> CAD Design' sekmesindeki #cad_3d_view kabına çiziliyor (ölçüldü: 1 canvas, 817 px, 'SOLID MOTOR SIMULATION'). Panel ise 6 maddelik 'Interactive 3D CAD model / Rotate (drag), zoom (scroll)' açıklaması sunuyor. Ekran görüntüleri: kati/bos_cad_paneli.png, kati/ucbo_guverte.png ; ham veri: kati/ucbo.json

**Tekrar üret:** /solid -> Calculate -> '3D CAD Design' paneline in -> 'NO DATA' yazısı -> '3D Visualization' düğmesine bas -> panel hâlâ boş.

**Dosya ipucu:** hrma/templates/solid.html:1672 (`<div id="cad_visualization">` hiçbir yerde doldurulmuyor) ve :4152 (show3DVisualization -> cad_3d_view)

### T22 — CİDDİ — 'Case Inner Diameter' satırı grain dış çapını gösteriyor; sayfada 3 farklı kasa çapı dolaşıyor

**Sayfa:** `/solid` · **Bileşen:** #solid_motor_table 'Case Inner Diameter' + Motor Specifications 'Chamber Diameter' + Excel Geometry sayfası · **Hüküm:** yanıltıcı

**Kanıt:** Grain Ø60 / kasa girdisi 100 / yalıtım 3 koşusunda: tablo 'Case Inner Diameter' = 60,0 mm, Motor Specifications 'Chamber Diameter' = 60,0 mm, Excel = 60, ama kesit anotasyonu Ø_c = 100,0 mm. Varsayılan koşuda: tablo/Excel 100,0 mm; kesit 106,0 mm; CAD sekmesi 'Inner Diameter 106 mm'; cıvata analizi 'Seal Ø 106,00000000000001'; termal/yapısal rıhtım girdisi 0,106 m. Yalıtım 3->20 yapılınca kesit 140,0 derken tablo 100,0'da kalıyor; kasa girdisi 160 yapılınca kesit 160,0 derken tablo yine 100,0. Ekran görüntüleri: kati/b5_tablo_kasa_capi.png, kati/bos_cad_paneli.png, kati/dock_STRUCTURAL.png ; ham veri: kati/dock_ondolum.json, kati/dil.json

**Tekrar üret:** /solid -> 'Insulation Thickness' 3 -> 20 -> Calculate -> tabloda 'Case Inner Diameter' 100,0 kalıyor, kesitte Ø_c = 140,0 mm yazıyor.

### T23 — CİDDİ — 6-DOF paneli ön-dolmuyor; rıhtım başlığı 'sonuçlardan ön-dolar' diyor

**Sayfa:** `/solid` · **Bileşen:** Analysis Dock -> 6-DOF paneli (sd_thrust, sd_burn, sd_dry_m, sd_prop_m) · **Hüküm:** yanıltıcı

**Kanıt:** Rıhtım başlığı: 'Inputs are pre-filled from the latest calculation results'. Ölçülen sd_* değerleri vs motorun gerçek değerleri: Thrust 1200 N vs 12602,1 (10,5x), Burn Time 6 s vs 1,024 (5,9x), Dry Mass 8 kg vs 20,409 (2,6x), Propellant Mass 4 kg vs 6,611 (1,7x). Aynı anda ad_* panelleri düzgün ön-doluyor (ad_f_structural_thrust=12602,13; ad_f_safety_propellant_mass=6,611; ad_f_thermal_burn_time=1,0244). Kütle alanları 'computed thrust curve' seçeneğiyle geçersiz kılınmıyor. Ekran görüntüsü: kati/dock_FEEDSYSTEM.png ; ham veri: kati/dock_ondolum.json

**Tekrar üret:** /solid -> Calculate -> Analysis Dock -> herhangi bir sekme -> 6-DOF bölümüne in -> Thrust 1200 / Burn Time 6 / Dry Mass 8 / Propellant Mass 4.

### T24 — CİDDİ — 'Web Thickness' girdisi ölü; tabloda raporlanan web gerçekte tükenenin 2 katı

**Sayfa:** `/solid` · **Bileşen:** #web_thickness girdisi + #solid_motor_table 'Web Thickness' satırı · **Hüküm:** anlamsız

**Kanıt:** 25 -> 5 mm değişiminde burn_time 1,024 s, ort. itki 12602 N, yakıt 6,611 kg birebir aynı kalıyor; tabloda her iki durumda 35,0 mm yazıyor. Uygulama warn.solid.web_thickness_inconsistent uyarısı veriyor (doğru), ama alan hâlâ düzenlenebilir ve ipucu 'Determines burn time and structural integrity' diyor. Ayrıca 35 mm tek cepheli geometrik web; varsayılanda dış yüzey de yandığı için gerçek tükenen web 17,5 mm (son yanma alanı 1761,9 cm² ile doğrulandı). Ham veri: kati/duyarlilik.json, kati/panel_rapor.json ; ekran görüntüsü: kati/b5_tablo_kasa_capi.png

**Tekrar üret:** /solid -> 'Web Thickness' 25 -> 5 -> Calculate -> hiçbir sonuç sayısı değişmiyor, tablo 35,0 mm gösteriyor.

### T25 — CİDDİ — 'Grain Length' ipucu tek grain diyor, çözücü toplam yığın sayıyor

**Sayfa:** `/solid` · **Bileşen:** #grain_length etiketi/ipucu + #grain_count · **Hüküm:** yanıltıcı

**Kanıt:** İpucu birebir: 'Axial length of individual propellant grain.' Ölçüm: grain_design.grain_length_mm=500, number_of_segments=3, segment_length_mm=166,67. grain_count 3 -> 1 yapıldığında yakıt kütlesi 6,611 kg'da sabit kalıyor (yalnız tb 1,024 -> 0,952 s, ort. itki 12602 -> 13855 N). Kütle doğrulaması: π/4·(0,1²−0,03²)·0,5 m·1850 = 6,611 kg (toplam yorumu doğru), x3 = 19,83 kg (tek-grain yorumu = B1'deki hatalı form değeri). Ham veri: kati/duyarlilik.json, kati/yardimci.json

**Tekrar üret:** /solid -> 'Number of Grains N' 3 -> 1 -> Calculate -> Motor Specifications 'Propellant Mass' 6,611 kg'da kalıyor.

### T26 — CİDDİ — Formül sayfası §1.3 itki katsayısı: karekök kapsamı yanlış, fiziksel olarak imkânsız C_F=0,974 üretiyor (sayfanın kendi tablosu 1,2-2,0 diyor)

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → §1.3 Thrust Coefficient, 1. formula-box · **Hüküm:** fiziksel imkânsız

**Kanıt:** Sayfada basılan: C_F = √(2γ²/(γ−1)) · (2/(γ+1))^((γ+1)/(γ−1)) · √(1−(p_e/p_c)^((γ−1)/γ)) + ... — (2/(γ+1))^… çarpanı karekökün DIŞINDA. Sutton & Biblarz Eq. 3-30'da karekök çarpımın tamamını kapsar. Ölçüldü (γ=1,2, p_e/p_c=0,01): sayfadaki yazım C_F=0,9736; doğru C_F=1,6445. C_F yakınsak-ıraksak lülede 1'in altına inemez ve sayfanın hemen altındaki değişken tablosu "Typical Values: 1,2-2,0" yazıyor. Kod DOĞRU: /Users/apple/HRMA/hrma/analysis/nozzle_flow_1d.py:164 ideal_thrust_coefficient() tüm çarpımı np.sqrt() içine alıyor. Ekran görüntüsü: scratchpad/faz6/yardimci/formul_1_3_CF.png

**Tekrar üret:** http://127.0.0.1:8084/formulas aç → "1.3 Thrust Coefficient" başlığına git → birinci formül kutusunda karekökün yalnız 2γ²/(γ−1) kesrini kapsadığını gör, altındaki tabloyla karşılaştır.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html — §1.3 (id="fundamental-performance") 1. formula-box

### T27 — CİDDİ — Formül sayfası §1.2: aynı bölümün iki c* kutusu √γ kadar (%9,5) çelişiyor — birinci kutuda γ pay ve paydada sadeleşiyor

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → §1.2 Characteristic Velocity, 1. formula-box · **Hüküm:** birim/ölçek yanlış

**Kanıt:** 1. kutu: c* = √(γ R T_c / γ)·((γ+1)/2)^((γ+1)/(2(γ−1))) — γ sadeleşiyor, geriye √(R T_c) kalıyor. 2. kutu: c* = √(R T_c)/Γ, Γ=√γ(2/(γ+1))^((γ+1)/(2(γ−1))). Doğrusu √(R T_c/γ), yani γ PAYDADA olmalı. Ölçüldü (γ=1,2, R=350 J/kg·K, T_c=3000 K): 1. kutu 1730,8 m/s; 2. kutu 1580,0 m/s; oran 1,0954 = √γ → %9,5 fazla. Aynı büyüklüğü tanımlayan iki kutu farklı sonuç veriyor. Kod 2. kutuyla birebir aynı: /Users/apple/HRMA/hrma/analysis/heat_transfer_analysis.py:474-476 (num=√(γRT_c), den=γ·√((2/(γ+1))^((γ+1)/(γ−1)))) → 1580,0. Yani 1. kutu yanlış. Ekran görüntüsü: scratchpad/faz6/yardimci/formul_1_2_cstar.png

**Tekrar üret:** http://127.0.0.1:8084/formulas → "1.2 Characteristic Velocity" → iki formül kutusunu karşılaştır; birincide √(γRT_c/γ) kesrinde γ'nin sadeleştiği çıplak gözle görünüyor.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html — §1.2 1. formula-box

### T28 — CİDDİ — Formül sayfası §6.2 hibrit port yarıçapı r(t): üs 2n+1 yerine 2(1−n) yazılmış — n=0,8'de %38 sapma, n=1'de sıfıra bölme

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → §6.2 Port Diameter Evolution · **Hüküm:** fiziksel imkânsız

**Kanıt:** Sayfa: r(t) = [r₀^(2(1−n)) + 2a(1−n)ṁ_ox^n/π^n·t]^(1/(2(1−n))). ṙ = a(ṁ_ox/(πr²))^n integrali doğru olarak r(t) = [r₀^(2n+1) + (2n+1)a(ṁ_ox/π)^n·t]^(1/(2n+1)) verir. Ölçüldü (a=1e-4, ṁ_ox=1 kg/s, r₀=0,05 m): n=0,3 t=20s doğru 0,05817 m / sayfa 0,05462 m (−6,1%); n=0,5 t=10s doğru 0,06024 / sayfa 0,05056 (−16,1%); n=0,5 t=20s (−25,9%); n=0,8 t=10s doğru 0,08105 / sayfa 0,05007 (−38,2%); n=0,8 t=20s (−49,7%). n=1'de sayfanın üssü 1/(2·(1−1)) → SIFIRA BÖLME, ifade tanımsız (doğrusunda üs 1/3). Marxman n katsayısı çoğu yakıtta 0,5-0,8 bandındadır, yani hata tam kullanım bandında. Aynı bölümdeki ṙ_avg kutusu da aynı (1−n) kalıbını taşıyor. Ekran görüntüsü: scratchpad/faz6/yardimci/formul_6_port.png

**Tekrar üret:** http://127.0.0.1:8084/formulas → "6. Hybrid Motors" → "6.2 Port Diameter Evolution" → üsteki 2(1−n) ifadesine bak; n=1 koy, payda sıfırlanır.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html — id="hybrid-motors" §6.2 formula-box

### T29 — CİDDİ — Formül sayfası §3.4: ikinci yanma verimi tanımı her gerçekçi girdide %160-183 veriyor (verim >1 imkânsız), üstündeki doğru tanımla çelişiyor

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → §3.4 Combustion Efficiency, 2. formula-box · **Hüküm:** fiziksel imkânsız

**Kanıt:** Aynı başlık altında iki kutu, ikisi de η_c etiketli: 1. kutu η_c = c*_actual/c*_theoretical (doğru), 2. kutu η_c = 1 − (T_wall − T_gas)/T_adiabatic. Roket odasında T_wall < T_gas olduğu için pay negatif, ifade 1'in üstüne çıkıyor. Ölçüldü: (T_w=800, T_g=3000, T_ad=3200) → η_c=1,688 (%169); (1000, 2800, 3000) → 1,600 (%160); (500, 3400, 3500) → 1,829 (%183). Verim tanım gereği ≤1 olmalıdır. Ekran görüntüsü: scratchpad/faz6/yardimci/formul_3_4_etac.png

**Tekrar üret:** http://127.0.0.1:8084/formulas → "3. Combustion Analysis" → "3.4 Combustion Efficiency" → iki kutuyu karşılaştır, ikinciye tipik roket sıcaklıkları koy.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html — id="combustion-analysis" §3.4 2. formula-box

### T30 — CİDDİ — Kayıtlı proje seçilince kilitli İtki ve Motor atıl kütlesi alanları BOŞ kalıyor, rozet "example, not calculated" yalanı söylüyor ve çözücüye sessizce örnek aracın 6500 N'u gidiyor

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → Araç kaynağı "Saved project (.hrma)" + /api/flight-vehicle · **Hüküm:** yanıltıcı

**Kanıt:** Ölçülen ekran durumu (proje: UI-Denetim-Test): Vehicle = "-- (example, not calculated)", hemen altındaki not = "Recomputed from the saved project." (iki etiket birbirini yalanlıyor); Thrust (N) = BOŞ; Engine inert (kg) = BOŞ; Burn time = 1,02; Propellant = 6,61. Uç doğrulaması: POST /api/flight-vehicle {"source":"project","name":"UI-Denetim-Test"} → 200, ama vehicle nesnesi NORMALİZE ŞEMA DEĞİL, 50 anahtarlı HAM motor sonucu (advanced_performance, altitude_performance, grain_design, ...). thrust=None, engine_inert_mass=None, motor_name=None, source=None; onun yerine max_thrust/average_thrust var. Şablon uçuş yükünde `thrust: num_(veh.thrust) || 6500` yazdığı için kullanıcı kendi projesini seçtiğinde çözücüye ÖRNEK aracın 6500 N'u gider (projenin gerçek tepe itkisi 8262 N). thrust_curve ise projeden geldiği için karışık kökenli araç oluşur. Şablondaki yorum (launch_site.html:202) bu ucun "tek şemaya çevirtip" dönmesi gerektiğini söylüyor. Ekran görüntüleri: scratchpad/faz6/yardimci/ls_proje_celiskili.png, ls_proje_kaynagi.png

**Tekrar üret:** http://127.0.0.1:8084/launch-site → Source açılır listesinden "Saved project (.hrma)" seç → beliren proje listesinden bir proje seç → Vehicle rozetine ve Thrust (N) alanına bak.

**Dosya ipucu:** /Users/apple/HRMA/hrma/app.py — /api/flight-vehicle source='project' kolu; tüketici /Users/apple/HRMA/hrma/templates/launch_site.html:520-534 ve :683

### T31 — ORTA — Uyarılar panelinde 'VALIDATION STATUS: [OBJECT OBJECT]' — doğrulama durumu kullanıcıya hiç ulaşmıyor

**Sayfa:** `/hybrid` · **Bileşen:** WARNINGS paneli — VALIDATION STATUS satırı · **Hüküm:** anlamsız

**Kanıt:** Üç ayrı motor tanımıyla (tank 50/90/30, itki 1000/5000, süre 10/30) her hesapta aynı çıktı: 'VALIDATION STATUS: [OBJECT OBJECT]'. Türkçe modda da aynı: 'DOĞRULAMA DURUMU: [OBJECT OBJECT]' (E_tr_metin.txt satır 122). Bir JS nesnesi metne çevrilmiş. Ekran görüntüsü: .../faz6/hibrit/hibrit_dogrulama_durumu.png

**Tekrar üret:** /hybrid → Calculate → WARNINGS bölümünün ilk satırını oku.

### T32 — ORTA — 'Impulse Efficiency' %110'a çıkıyor ve kendi açıklama metniyle çelişiyor

**Sayfa:** `/hybrid` · **Bileşen:** thrust_altitude_plot — Impulse Efficiency vs Altitude alt grafiği · **Hüküm:** yanıltıcı

**Kanıt:** Ölçülen seri: 0 km %100,00 → 20 km %110,33 (ara: 1 km 101,23; 5 km 105,10; 10 km 108,07; 15 km 109,62). Y ekseni başlığı 'Efficiency (%)'. Panelin kendi açıklaması (advanced.html:1767): 'Percentage of the vacuum impulse actually delivered' — vakum impulsünün yüzdesi olsaydı deniz seviyesi en düşük olur ve %100 aşılamazdı. Gerçekte metrik deniz seviyesine normalize edilmiş (thrust_alt/base_thrust), bu yüzden %100'ü aşıyor. Bir verim göstergesinin %100'ü aşması fiziksel olarak anlamsız. Ekran görüntüsü: .../faz6/hibrit/hibrit_toplam_impuls_irtifa.png

**Tekrar üret:** Calculate → 'TOTAL IMPULSE VS ALTITUDE' paneli → üçüncü alt grafiğin 20 km değerini oku.

**Dosya ipucu:** hrma/engines/combustion_analysis.py:1819 ('impulse_efficiency': effective_total_impulse / total_impulse — total_impulse deniz seviyesi tasarım impulsü)

### T33 — ORTA — Aynı sayfada iki farklı deniz seviyesi itkisi (1000 N ve 1034 N) ve manşetten %3,4 sapan Isp

**Sayfa:** `/hybrid` · **Bileşen:** altitude_performance_plot ve thrust_altitude_plot — 'Thrust vs Altitude' alt grafikleri · **Hüküm:** yanıltıcı

**Kanıt:** İkisi de aynı irtifa ızgarasını (0,1,5,10,15,20 km) kullanıyor. Deniz seviyesinde: altitude_performance_plot 1034,386 N, thrust_altitude_plot 1000,000 N (%3,44 fark). Isp ikisinde de 191,9757 s, manşet PERFORMANCE SUMMARY ise 185,6 s (%3,44 fark; manşet CF=1,374 kayıplı, grafikler CF=1,4209 ideal). thrust_altitude_plot kendi içinde tutarsız: 1000 N + 191,98 s ⇒ mdot=0,5312 kg/s, oysa çözücünün ve sayfanın her yerindeki mdot 0,5494 kg/s. Ekran görüntüleri: .../faz6/hibrit/hibrit_irtifa_performans.png ve .../faz6/hibrit/hibrit_toplam_impuls_irtifa.png

**Tekrar üret:** Calculate → 'ALTITUDE PERFORMANCE' panelindeki 'Thrust vs Altitude' alt grafiğinin 0 km değeriyle 'TOTAL IMPULSE VS ALTITUDE' panelindeki aynı adlı alt grafiğin 0 km değerini karşılaştır.

**Dosya ipucu:** hrma/engines/combustion_analysis.py:1441 (mdot = motor_data.get('mdot_total')) ve :1783 (base_mdot = base_thrust/(base_isp*G_0)) — ikisi de manşetin lüle kayıplarını uygulamıyor

### T34 — ORTA — 6-DOF hücum açısı grafiği fırlatma artefaktı yüzünden okunamaz; rozetle 31 kat çelişiyor

**Sayfa:** `/hybrid` · **Bileşen:** sd_plot_alpha — Angle of Attack (weathercock response) · **Hüküm:** yanıltıcı

**Kanıt:** Ölçülen seri: α maksimum = 90,000° (t≈0'da), minimum 1,88e-6°, Y ekseni otomatik ölçek [0 , 94,74]. Yanındaki rozet 'MAX alpha 2.9 deg' diyor (31 kat fark). Ekran görüntüsünde eğri t=0'da 90°'den başlayıp ~1 s'de sönüyor, kalan 37 s sıfıra yapışık düz çizgi — grafiğin bütün bilgisi (gerçek uçuşta α≈3°) eziliyor. Artefaktın sebebi: rampada v≈0 iken u=v-w_rüzgâr neredeyse yatay, gövde ekseni dikey → α≈90°; rampada kısıtlı araç için α tanımsız. Arka uç bunu biliyor ve max_alpha'yı t>1 s + hız>%10 maskesiyle ölçüyor, grafik ise maskesiz ham diziyi çiziyor. Grafiğin alt yazısı 'sustained large values indicate weathercocking or instability' diyor, panelin geçerlilik notu ise 'alpha < 15 deg'. Ekran görüntüsü: .../faz6/hibrit/G_6dof_alpha.png

**Tekrar üret:** Calculate → Run 6-DOF → 'Angle of Attack (weathercock response)' grafiğinin Y ekseni tavanını rozetteki 'MAX alpha' değeriyle karşılaştır.

**Dosya ipucu:** hrma/static/js/sixdof_panel.js:1367 (maskesiz ser.alpha_deg çiziliyor) ↔ hrma/analysis/six_dof_trajectory.py:1073-1077 (burn_mask ile maskelenmiş max_alpha)

### T35 — ORTA — İki zaman-marşı çözümü aynı motor için sistematik %2 farklı itki ve oda basıncı veriyor

**Sayfa:** `/hybrid` · **Bileşen:** tp_plot (Transient Analysis) ↔ hybrid_thrust_plot (Thrust and Chamber Pressure vs Time) · **Hüküm:** yanıltıcı

**Kanıt:** Aynı motor, aynı 0-10 s yanma. hybrid_thrust_plot: itki 997,209–1004,145 N, oda basıncı 19,545–19,681 bar. tp_plot: itki 1017,165–1025,176 N, oda basıncı 19,944–20,083 bar. Sistematik fark itkide ~%2,0, basınçta ~%2,0. İki panel de kendini zaman-marşı çözümü olarak tanıtıyor ('taken from the time-marching solution' / 'quasi-steady internal-ballistics march'), hangisinin bağlayıcı olduğu yazmıyor. Ekran görüntüleri: .../faz6/hibrit/hibrit_itki_egrisi.png ve .../faz6/hibrit/J_transient.png

**Tekrar üret:** Calculate → itki eğrisinin Y aralığını not et → Run Transient → tp_plot'un Y aralığıyla karşılaştır.

### T36 — ORTA — Enjektör şemasında 'Total Flow: not reported' yer tutucusu — veri sayfada mevcut

**Sayfa:** `/hybrid` · **Bileşen:** injector_plot — SHOWERHEAD INJECTOR bilgi kutusu · **Hüküm:** eksik

**Kanıt:** Bilgi kutusu: '32 Holes x dia 0.90 mm / Total Area: 20.3 mm2 / Pressure Drop: 4.0 bar / Total Flow: not reported'. Oysa aynı sayfa debiyi üç yerde yazıyor: 'Oxidizer Mass Flow Rate 0.392 kg/s', 'Total Mass Flow Rate 0.549 kg/s' ve performans panosunda 0.392 kg/s çubuğu. Türkçe modda da İngilizce 'not reported' olarak kalıyor. Ekran görüntüsü: .../faz6/hibrit/hibrit_enjektor_sema.png

**Tekrar üret:** Calculate → 'INJECTOR DESIGN SCHEMATIC' panelindeki bilgi kutusunun son satırını oku.

### T37 — ORTA — Isp/(O/F) optimizasyon taraması optimumu içeremiyor; 'Sweep maximum' ızgaranın ucunda

**Sayfa:** `/hybrid` · **Bileşen:** combustion_analysis_plot — Isp vs O/F (equilibrium sweep) alt grafiği · **Hüküm:** yanıltıcı

**Kanıt:** Tarama aralığı O/F 1,0–6,0 (9 nokta); 'Sweep maximum' işareti tam sağ uçta x=6,0, Isp 231,699 s. Aynı sayfadaki Find Optimum düğmesine basıldığında sonuç: 'Optimum: 6.84 (Max Isp: 232.7 s)' — gerçek optimum taramanın DIŞINDA. 'O/F Ratio Optimization: Performance sensitivity around the selected mixture ratio' başlıklı panel uygulamanın kendi bildiği optimumu gösteremiyor, kenar noktasını maksimum diye işaretliyor. Ekran görüntüsü: .../faz6/hibrit/hibrit_yanma_of_taramasi.png

**Tekrar üret:** Calculate → 'COMBUSTION ANALYSIS' panelinde 'Sweep maximum' işaretinin x konumunu oku → Find Optimum'a bas → O/F alanının yeni değeriyle (6,84) karşılaştır.

**Dosya ipucu:** Aynı kalıp max_thrust_altitude için combustion_analysis.py:1828 civarında yorumla belgelenmiş ('tarama ızgarasının ucudur'); Isp taraması için aynı düzeltme yapılmamış

### T38 — ORTA — Enjektör tasarım paneli, aynı sayfada hesaplanan motorun debilerini almıyor (%33 sapma)

**Sayfa:** `/liquid` · **Bileşen:** INJECTOR DESIGN — LIQUID (BIPROPELLANT) paneli, 'Design injector' (#inj_run) · **Hüküm:** yanıltıcı

**Kanıt:** Başarılı hesaptan SONRA ölçülen panel girdileri: inj_mdot_ox=2 kg/s (çözücü 2,9746 → -32,8%), inj_mdot_fuel=0,8 kg/s (çözücü 1,1898 → -32,8%), inj_rho_fuel=810 (çözücü 800), inj_pc=100 ✓. Panel bu yüzden üçte bir küçük bir motor için boyutlandırıyor ve çıktısı ana sonuçlarla çelişiyor: eleman/delik sayısı 100 eleman ↔ 4 çift (8 oks. + 4 yakıt deliği); oks. delik çapı 0,895 mm ↔ 2,46 mm; yakıt delik çapı 0,619 mm ↔ 2,39 mm; oks. enjeksiyon hızı 41,43 ↔ 46,2 m/s; yakıt hızı 49,50 ↔ 54,8 m/s. Sayfada aynı motor için iki farklı enjektör tasarımı yan yana duruyor, hangisinin geçerli olduğu yazmıyor. Ölçüm: scratchpad/faz6/sivi/inj.log ; sivi/e400.json→inj_run çıktı tablosu ; sivi/indirilen/UZAYTEK_LIQUID_analysis_2026-08-03.xlsx 'Injector' sayfası

**Tekrar üret:** 'Calculate Engine Performance' → enjektör paneline in → 'Oxidizer mdot (kg/s)' alanının değerine bak (2, oysa sonuç 2,9746) → 'Design injector'.

### T39 — ORTA — Ekrandaki motor kesitinde oda cidarı 3,0 mm, imalat çıktılarında 5,00 mm

**Sayfa:** `/liquid` · **Bileşen:** liquid_motor_kesit — 'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY' · **Hüküm:** yanıltıcı

**Kanıt:** Kesit çizimi cidarı struct['chamber_analysis']['recommended_thickness'] yolundan okuyor; sıvı çözücü ise bloğu 'chamber_structure' adıyla ve kalınlığı 'required_wall_thickness' adıyla yayınlıyor (liquid_rocket_engine.py:7532) → anahtar hiç tutmuyor, yedek değere düşülüyor: 0,045*61,6228 = 2,773 → alt sınır 3,0 ile kırpılıyor → 3,0 mm. Ölçülen: kesitteki 'Chamber wall' izi y_maks 33,8114 mm − oda yarıçapı 30,8114 mm = 3,000 mm. Karşılaştırma: kullanıcı girdisi 5 mm; DXF metni 5,00 mm; STEP kamara katısı Y 0…35,811 mm → 5,000 mm; teknik çizim PDF'i 5,00 mm; yapısal analizin gerektirdiği 6,677 mm. Ekranda görülen kesit imalata giden çizimden %40 ince. Ekran görüntüsü: scratchpad/faz6/sivi/03_motor_kesiti.png ; ölçüm: sivi/ham.json→kesit.izler[0] ; sivi/indirilen/step_x/UZAYTEK_LIQUID_chamber.step

**Tekrar üret:** 'Calculate Engine Performance' → 'MOTOR CROSS SECTION' grafiğinde 'Chamber wall' izinin en büyük yarıçapını oku (33,81 mm) ve tablodaki oda çapı 61,62 mm (yarıçap 30,81) ile farkını al → 3,0 mm; sonra DXF'i indirip 'WALL THICKNESS' metnini oku → 5,00 mm.

**Dosya ipucu:** hrma/visualization/visualization.py:3398-3400

### T40 — ORTA — Kayıp pastası, kendi başlığındaki verime dahil OLMAYAN bir kalemi %29,9'luk dilim gösteriyor

**Sayfa:** `/liquid` · **Bileşen:** efficiencyChart — 'Performance Losses (Overall Efficiency: 82.4%)' · **Hüküm:** yanıltıcı

**Kanıt:** Pastanın ikinci büyük dilimi NOZZLE LENGTH_LOSS = %29,9 (8,028 puan / 26,848 toplam). Çözücünün kendi loss_sources açıklaması bu kalem için: 'vacuum CF at epsilon=50.0 against the practical limit epsilon=500 - design comparison only, NOT part of the overall efficiency product'. Doğrulandı: başlıktaki %82,4 diğer ALTI çarpanın çarpımı — 0,99832*0,97*0,98296*0,91650*0,99624*0,94778 = 0,8237 → %82,4 ✓ (nozzle_length_loss bu çarpımda yok). Yani pastanın üçte biri, başlığın söz ettiği verim bütçesine ait değil. Ekran görüntüsü: scratchpad/faz6/sivi/10_kayip_pastasi.png ; ölçüm: sivi/ham.json→verim.pie ve verim.eff.loss_sources.nozzle_length_loss

**Tekrar üret:** 'Calculate Engine Performance' → 'Total Impulse' alt sekmesi → 'Performance Losses' pasta grafiği; NOZZLE LENGTH_LOSS diliminin yüzdesini oku.

### T41 — ORTA — Kayıp pastası etiketlerinde ham veri anahtarı sızıyor (HEAT TRANSFER_LOSS)

**Sayfa:** `/liquid` · **Bileşen:** efficiencyChart dilim etiketleri ve efsanesi · **Hüküm:** anlamsız

**Kanıt:** Etiketlerde yalnız İLK alt çizgi boşluğa çevrilmiş, kalanı ekranda duruyor: 'HEAT TRANSFER_LOSS', 'NOZZLE LENGTH_LOSS', 'BOUNDARY LAYER_LOSS'. Tek kelimelik anahtarlar (MIXING LOSS, KINETIC LOSS, DIVERGENCE LOSS, COMBUSTION INCOMPLETE) doğru göründüğü için hata yalnız iki kelimeli anahtarlarda belirginleşiyor. Hem dilim etiketlerinde hem sağdaki efsanede görünüyor. Ekran görüntüsü: scratchpad/faz6/sivi/10_kayip_pastasi.png ; ham etiket dizisi: sivi/ham.json→verim.pie[0].labels

**Tekrar üret:** 'Calculate Engine Performance' → 'Total Impulse' alt sekmesi → 'Performance Losses' pastasının etiketlerini oku.

### T42 — ORTA — Aynı sayfada iki farklı deniz seviyesi Isp: 244,9 s ve 249,9 s

**Sayfa:** `/liquid` · **Bileşen:** HUD metrik kartı 'SEA LEVEL ISP' ↔ altitude_plot 0 km noktası · **Hüküm:** yanıltıcı

**Kanıt:** HUD kartı: 244,9 s (isp_sea_level = 244,86335), hedef itki 10000 N. İrtifa grafiği 0 km: 249,924 s ve 10,2067 kN = 10206,7 N. Fark 5,06 s (%2,07); itkideki fark aynı oranda (10206,7/10000 = 1,0207). İki sayı aynı ekranda, aynı işletme noktası için, farkın sebebi hiçbir yerde yazmadan sunuluyor. Çözücünün 0 km kaydı sebebi biliyor: isp_anchor_basis = 'delivered Isp anchored at the vacuum reference; the sea-level anchor is invalid because this nozzle is separated at sea level (Summerfield criterion, Pe < 0.40 * Pa)' ve pressure_thrust = -3076,5 N (aşırı genişleme). Yani ε=50 nozul deniz seviyesinde akış ayrılmasında ve 0 km noktası fiziksel olarak geçerli değil; grafik yine de o noktayı normal veri gibi çiziyor (ayrılma bölgesi işaretlenmiyor, eğri kesilmiyor). Uyarı paneli ayrılmayı bildiriyor ama iki Isp farkını açıklamıyor. Ekran görüntüsü: scratchpad/faz6/sivi/05_irtifa_grafigi.png ; ölçüm: sivi/derin.json→metrikler, sivi/ham.json→irtifa.cr_alt[0]

**Tekrar üret:** 'Calculate Engine Performance' → HUD kartındaki 'SEA LEVEL ISP' değerini (244,9 s) oku → aynı sayfadaki irtifa grafiğinde 0 km noktasının üzerine gel (249,9 s).

### T43 — ORTA — Enjektör göstergesi hangi büyüklüğü gösterdiğini söylemiyor; yakıt devresi hiç gösterilmiyor

**Sayfa:** `/liquid` · **Bileşen:** liquid_performance_plots içindeki 'Injector Performance' gauge göstergesi · **Hüküm:** anlamsız

**Kanıt:** Gösterge '41.4 m/s' yazıyor; 0-100 skalası, 20-50 yeşil, 50-100 KIRMIZI, 50'de kırmızı eşik. Hangi hız olduğu yazmıyor. Excel çıktısıyla eşleştirilerek belirlendi: bu OKSİTLEYİCİ enjeksiyon hızı (Excel 'Injector' sayfası: Oxidizer injection velocity 41.43 m/s). YAKIT enjeksiyon hızı (49,50 m/s) hiçbir yerde gösterilmiyor — üstelik kırmızı bandın hemen dibinde. Kırmızı/yeşil bandın dayanağı yazılı değil; sayfanın kendi öntanımlı girdileri yakıt 25 / oksitleyici 40 m/s. Kullanıcı 'enjektörüm yeşil bölgede' sonucu çıkarır; gösterilmeyen yakıt devresi kırmızıya bir adım uzaktadır. Ekran görüntüsü: scratchpad/faz6/sivi/04_performans_panosu.png (sağ alt) ; ölçüm: sivi/ham.json→gosterge ; sivi/indirilen/UZAYTEK_LIQUID_analysis_2026-08-03.xlsx

**Tekrar üret:** 'Calculate Engine Performance' → 'PERFORMANCE ANALYSIS DASHBOARD' → sağ alttaki 'Injector Performance' göstergesine bak; hangi akışkanın hızı olduğunu gösteren hiçbir etiket yok.

**Dosya ipucu:** hrma/visualization/visualization.py:1190-1191 (_perf_gauge_panel('Injector Performance', injector_data.get('exit_velocity')))

### T44 — ORTA — Geometrik olarak sığmayan 80 soğutma kanalı Excel'e uyarısız aktarılıyor

**Sayfa:** `/liquid` · **Bileşen:** Excel Workbook dışa aktarımı — 'Geometry' sayfası · **Hüküm:** yanıltıcı

**Kanıt:** Excel 'Geometry' sayfasında 'Cooling channels | 80' satırı var. Uygulamanın kendi uyarı paneli aynı koşuda: '80 cooling channels of 3 mm width do not fit around the 30.8 mm throat circumference; 21 channels is the geometric maximum at constant channel width.' Ekranda 'bu sayı imkânsız' denen değer mühendislik teslimatına hiçbir not düşülmeden geçiyor. (Aynı dosyadaki diğer bütün sayılar ekranla birebir tutuyor — sorun yalnız bu alanın uyarısız taşınması.) Dosya: scratchpad/faz6/sivi/indirilen/UZAYTEK_LIQUID_analysis_2026-08-03.xlsx ; uyarı metni: sivi/son.json→uyari.metin

**Tekrar üret:** 'Calculate Engine Performance' → uyarı panelindeki soğutma kanalı uyarısını oku → 'Excel Workbook' indir → 'Geometry' sayfasında 'Cooling channels' satırına bak.

### T45 — ORTA — Anlamsız hassasiyet: 17 anlamlı basamak (3707.0404366159974 K)

**Sayfa:** `/liquid` · **Bileşen:** 'Engine Specifications' künyesi ve Panel 1 girdi alanları · **Hüküm:** anlamsız

**Kanıt:** Ekranda basılan değerler: 'Mixture Ratio: 2.5 (Optimal: 2.806883164944784)' — sayısal taramayla bulunan optimum için 16 anlamlı basamak; 'Chamber Temperature: 3707.0404366159974 K' — denge sıcaklığı için 17 basamak (CEA belirsizliği onlarca K düzeyinde); form alanı 'Oxidizer Density: 1,3087864284209203'; form alanı 'Oxidizer Viscosity: 0,000020550207325996687'. Sonuç tablosu doğru yuvarlanmış (30,81 / 217,87 / 1754,6) — sorun bu iki panelde: ham float değerler biçimlendirilmeden ekrana basılıyor ve olmayan bir kesinlik hissi veriyor. Ekran görüntüleri: scratchpad/faz6/sivi/21_motor_kunyesi.png ve sivi/acilis.png

**Tekrar üret:** 'Calculate Engine Performance' → 'ALTITUDE PERFORMANCE ANALYSIS' altındaki 'Engine Specifications' künyesine bak.

### T46 — ORTA — 3B tank grafiğinde 19 adlandırılmış iz var ama efsane hiç çizilmiyor

**Sayfa:** `/liquid` · **Bileşen:** tankVisualization · **Hüküm:** eksik

**Kanıt:** Grafik showlegend:true ile kuruluyor ve 19 izin hepsinin adı var (Oxidizer Tank, Fuel Tank, Anti-Vortex Device, Inlet Pipe, Outlet Pipe, Baffle 1, Baffle 1 Hole 1…6, Baffle 2, Baffle 2 Hole 1…6). Tarayıcıda ölçülen: efsane_var=false, efsane_kutu=0 px, grafik genişliği 1224 px. Kullanıcı 19 renkli cismi hangisinin ne olduğunu bilmeden görüyor. Ayrıca 1224x400 px alanın yalnız orta ~%25'i kullanılıyor. Ekran görüntüsü: scratchpad/faz6/sivi/11_tank_3d.png ; ölçüm: sivi/final.json→tank_efsane

**Tekrar üret:** 'Calculate Engine Performance' → 'Total Impulse' alt sekmesi → 3B tank grafiğinin sağında efsane olup olmadığına bak.

### T47 — ORTA — İngilizce modda Türkçe metin çıkıyor (enjektör paneli)

**Sayfa:** `/liquid` · **Bileşen:** INJECTOR DESIGN paneli çıktısı (#inj_run sonucu), dil seçici 'English' · **Hüküm:** dil

**Kanıt:** Sayfa İngilizce modundayken panel şunları basıyor: '4 çift unlike doublet, 2θ=60°, serbest jet 6·d_j' ve 'References: NASA SP-8089 (1976) … Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 8-9 · Huzel & Huang, Böl. 4 (manifold pratiği) … Nurick, ASME J. Fluids Eng. 1976 (kavitasyon/flip) · Rupe, JPL 20-195 (1953) — karışım kriteri'. 'çift', 'serbest jet', 'baskı', 'Böl.', 'manifold pratiği', 'kavitasyon/flip', 'karışım kriteri' Türkçe. Ölçüm: scratchpad/faz6/sivi/e400.json→inj_run (bu koşu İngilizce modda yapıldı; dil seçicisine dokunulmadı)

**Tekrar üret:** /liquid (dil: English) → 'Calculate Engine Performance' → enjektör paneline in → 'Design injector' → çıkan metni oku.

### T48 — ORTA — 6-DOF, kendi beyan ettiği geçerlilik sınırının 6 katı hücum açısında koşmaya devam ediyor

**Sayfa:** `/liquid` · **Bileşen:** sd_plot_alpha — 'α [deg]' grafiği · **Hüküm:** yanıltıcı

**Kanıt:** Panelin kendi açıklaması: 'Linear small-alpha aerodynamics (alpha < 15 deg) — use for stability screening, not tumbling flight.' Ölçülen α izi: 3,06e-07 … 90,0 derece. Model beyan edilen 15° sınırının 6 katına çıkıyor; eğri hiçbir yerde kesilmiyor, 15° sınırı grafikte işaretlenmiyor, sonuçlar normal veri gibi sunuluyor. B2'deki fiziksel imkânsız uçuşun bir parçası. Ölçüm: scratchpad/faz6/sivi/sixdof.json→6dof_plot[1] ; ekran görüntüsü: sivi/23_6dof_enjektor.png

**Tekrar üret:** 'Calculate Engine Performance' → 6-DOF panelinde 'Run 6-DOF' → α grafiğinin y ekseni tepesine bak (90°).

### T49 — ORTA — Varsayılan inhibitör düzeni sayfanın kendi 'BATES (neutral)' yardımıyla çelişiyor

**Sayfa:** `/solid` · **Bileşen:** #inhibit_outer onay kutusu + 'Thrust Curve' panel açıklaması · **Hüküm:** yanıltıcı

**Kanıt:** Panel metni 'Burn profile: BATES (neutral), Star (progressive), End-burner (regressive)'. Varsayılanda 'Outer Surface' kutusu işaretsiz -> profil regressive: yanma alanı 2328 -> 1762 cm², itki 15845 -> 9727 N (-%39), tb 1,024 s. Kutu işaretlenince progressive: 757 -> 1132 cm², itki 5142 -> 9920 N (+%93), tb 1,633 s. Ayrıca kesit çizimi grain dışına astar ve kasa çiziyor; dış yüzeyin yandığı yapılandırmada bunlar t=0'dan itibaren aleve maruz. Alanın kendi ipucu metni 'Usually inhibited for core-burning grains' diyerek varsayılanın tersini öneriyor. Ekran görüntüleri: kati/itki_inhibit_outer_False.png, kati/itki_inhibit_outer_True.png ; ham veri: kati/kesit_inhibitor.json

**Tekrar üret:** /solid -> Calculate -> itki eğrisi düşüyor -> 'Outer Surface' kutusunu işaretle -> Calculate -> eğri yükselen hâle geliyor.

**Dosya ipucu:** hrma/templates/solid.html:812 (`<input type="checkbox" id="inhibit_outer">` — checked yok; inhibit_front/inhibit_rear checked)

### T50 — ORTA — 'Computing trajectory...' metni iş bittikten 25 saniye sonra da ekranda

**Sayfa:** `/solid` · **Bileşen:** Trajectory Analysis paneli durum satırı · **Hüküm:** sahte gösterge

**Kanıt:** Yörünge hesabı 0,2 s sürüyor ve 9 iz çiziliyor; buna rağmen 'Computing trajectory...' metni 2., 10. ve 25. saniye ölçümlerinin üçünde de (computing=True, iz=9) ekranda duruyor. Ekran görüntüleri: kati/yorunge.png (alt satır), kati/yorunge_paneli_tam.png ; ham veri: faz6/son_cikti.txt

**Tekrar üret:** /solid -> Calculate -> Compute Trajectory -> grafikler çizildikten sonra panelin altına bak.

### T51 — ORTA — c* girdisi kabul ediliyor ama değeri hiç kullanılmıyor (5,9 kat aralık, sıfır etki)

**Sayfa:** `/solid` · **Bileşen:** #char_velocity girdisi · **Hüküm:** anlamsız

**Kanıt:** Forma 1550 girildiğinde çözücü c*=1472,5 m/s, ort. itki 12602 N, Isp 199,1 s. Forma 508,7 girildiğinde çözücü 1518,3 m/s / 12994 N / 205,3 s. Forma 3000 girildiğinde yine tam olarak 1518,3 m/s / 12994 N / 205,3 s. 508,7 ile 3000 arası 5,9 kat, sonuç birebir aynı; bu duruma özel uyarı da gösterilmiyor. Ham veri: kati/cstar_kutle.json, faz6/cstar_cikti.txt

**Tekrar üret:** /solid -> 'Characteristic Velocity' alanına 3000 yaz -> Calculate -> Motor Specifications 'C* Velocity: 1518 m/s'. Sonra 508,7 yaz -> yine 1518 m/s.

### T52 — ORTA — Performans panosundaki çift eksenli iki alt grafikte efsane (legend) yok

**Sayfa:** `/solid` · **Bileşen:** #solid_performance_plots alt grafik 3 ('Thrust & Chamber Pressure vs Time') ve 4 ('Burn Area & Kn vs Time') · **Hüküm:** eksik

**Kanıt:** Her iki alt grafik iki seriyi çift y-ekseninde çiziyor (yaxis3/yaxis4 ve yaxis5/yaxis6, plotly_bates.json'da 6 iz) ama efsane gösterilmiyor. İtki ile basınç orantılı olduğu için eğriler üst üste biniyor ve ekranda tek çizgi görünüyor; hangi rengin hangi eksene ait olduğu okunamıyor. Ekran görüntüsü: kati/bates_performans.png ; ham veri: kati/plotly_bates.json

**Tekrar üret:** /solid -> Calculate -> 'Performance Analysis Dashboard' panelindeki alt sıradaki iki grafiğe bak.

### T53 — ORTA — "Resolve site" düğmesinin %68'i ölçek çubuğunun altında kalıyor, fare ile tıklanamıyor

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → #ls-resolve / #ls-scalebar · **Hüküm:** eksik

**Kanıt:** 1600×1000 görünümde ölçülen kutular: #ls-resolve x=30 y=929 w=256 h=35; #ls-scalebar x=14 y=928 w=189 h=58. Örtüşme 173×35 px = 6055 px² = düğmenin görünür alanının ~%68'i. document.elementFromPoint(düğme merkezi) → "ls-scalebar". Playwright otomatik tıklaması: "ls-resolve → TIKLANAMADI (üstünde: ls-scalebar)" (4 s zaman aşımı). Aynı taramada diğer 5 etkin düğme (ls-apply, ls-fly, ls-view-site, ls-view-globe, ls-clear-tiles) sorunsuz tıklandı. Uç sağlam: JS ile tetiklendiğinde 0,07 s'de doğru fizik döndü (g=9,79217 m/s² — WGS84 Somigliana ile elle hesabım 9,79218; g₀=9,80665; T=288,1 K; p=101,33 kPa; v_rot=408,6 m/s). Yani işlev çalışıyor ama kullanıcı ona ulaşamıyor. Ekran görüntüsü: scratchpad/faz6/yardimci/ls_cakisma_resolve.png

**Tekrar üret:** http://127.0.0.1:8084/launch-site aç (1600×1000) → sol panelin en altındaki "Resolve site" düğmesinin ortasına tıkla → tık ölçek çubuğuna gider, çözümleme çalışmaz.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/launch_site.html — #ls-scalebar ve #ls-resolve yerleşim/z-index kuralları

### T54 — ORTA — Karo önbelleği göstergesi 25 karo indirildikten sonra hâlâ "0 MB · 0 tile" diyor ve NASA GIBS atfı hiç görünmüyor (refreshTileUsage yalnız açılışta çağrılıyor)

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → #ls-tile-usage, #ls-tile-attr · **Hüküm:** yanıltıcı

**Kanıt:** Ölçüldü: kamerayı 245 km'ye indirdim (karo eşiği TEXTURE_NOTE_ALT_M = 400 km), 25 adet /api/tile/... isteği yapıldı (ilkler: bluemarble/7/42/25, /43/25, /44/25, /45/25). Gerçek durum: GET /api/tile/cache/status → {"bytes":150312,"tiles":6}. Ekranda yazan: "0 MB · 0 tile". #ls-tile-attr computed display = "none" (NASA GIBS atfı hiç görünmüyor). Kök neden: refreshTileUsage() yalnız iki yerde çağrılıyor — sayfa açılışında (launch_site.html:596) ve "Clear map cache" sonrasında (:592); karolar indikten sonra hiç yenilenmiyor. Kaynak yorumu (launch_site.html:369-371) "kullanıcı hem kaynağı hem disk kullanımını görebilmeli" diyor; ikisi de görünmüyor. (Doku uyarısı #ls-texnote ise doğru çalışıyor: 400 km altında display:block oluyor.) Ekran görüntüleri: scratchpad/faz6/yardimci/ls_karo_yakin.png, ls_yakinlasma.png

**Tekrar üret:** http://127.0.0.1:8084/launch-site → "Zoom to site" → fare tekerleğiyle kamera yüksekliği 400 km'nin altına inene kadar yakınlaş → sağ alttaki "0 MB · 0 tile" yazısını `curl http://127.0.0.1:8084/api/tile/cache/status` çıktısıyla karşılaştır.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/launch_site.html:576-596 (refreshTileUsage tanımı ve tek çağrı noktaları)

### T55 — ORTA — Formül sayfası §1.5: iki kütle debisi ifadesi boyutsal olarak tutarsız (kg/m ve kg^0,5·m^0,5 çıkıyor, kg/s değil)

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → §1.5 Mass Flow Rate Relations, 1. ve 3. formula-box · **Hüküm:** birim/ölçek yanlış

**Kanıt:** 1. kutu: ṁ = ρ* A_t √γ (2/(γ+1))^((γ+1)/(2(γ−1))) → birim kg/m³·m²·(boyutsuz) = kg/m; hız çarpanı √(R T_c) eksik. 3. kutu: ṁ = C_d A_t √(2γ p_c/(γ+1))·((γ+1)/(R T_c))^(1/2) → birim m²·√Pa·(s/m) = kg^0,5·m^0,5; p_c karekök içinde kalmış, doğrusunda doğrusaldır. Doğru biçim (Sutton 3-24): ṁ = C_d A_t p_c √(γ/(R T_c))·(2/(γ+1))^((γ+1)/(2(γ−1))). Ölçüldü (A_t=0,002 m², p_c=4 MPa, γ=1,2, R=350, T_c=3000, C_d=0,97): doğru 4,911 kg/s; 1. kutu yazımı 0,00307; 3. kutu yazımı 0,00587 (birimler uyuşmadığı için sayılar zaten kıyaslanamaz — boyutsal tutarsızlık başlı başına kusur). Ekran görüntüsü: scratchpad/faz6/yardimci/formul_1_5_debi.png

**Tekrar üret:** http://127.0.0.1:8084/formulas → "1.5 Mass Flow Rate Relations" → 1. ve 3. kutuların birimlerini altındaki değişken tablosuyla (ṁ: kg/s) karşılaştır.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html — §1.5 1. ve 3. formula-box

### T56 — DÜŞÜK — Çalışma noktası panosunun üç zaman grafiğinde hiç eksen başlığı ve birim yok

**Sayfa:** `/hybrid` · **Bileşen:** realtime_dashboard_plot — Propellant Mass / Burn Rate / Port Diameter alt grafikleri · **Hüküm:** eksik

**Kanıt:** Ölçülen layout: xaxis='', yaxis='', xaxis2='', yaxis2='', xaxis3='', yaxis3='' — altı eksenin de başlığı tamamen boş. Alt grafik başlıkları var (Propellant Mass, Burn Rate, Port Diameter) ama kütle kg mı, hız mm/s mi, çap mm mi, zaman s mi grafikten okunamıyor. Sayfadaki diğer bütün grafikler eksen başlığı + birim taşıyor (ör. 'Time (s)', 'Port Diameter (mm)', 'r (mm/s)'). Ekran görüntüsü: .../faz6/hibrit/hibrit_calisma_noktasi_panosu.png

**Tekrar üret:** Calculate → 'OPERATING POINT DASHBOARD' panelinin alt sıra grafiklerinin eksenlerine bak.

### T57 — DÜŞÜK — Türkçe modda beş metin İngilizce kalıyor (karışık dil)

**Sayfa:** `/hybrid` · **Bileşen:** hybrid_thrust_plot başlığı, combustion_analysis_plot efsanesi, istasyon etiketleri, enjektör kutusu · **Hüküm:** dil

**Kanıt:** TR/EN metinleri ayrı ayrı çıkarılıp karşılaştırıldı (E_plot_dil.json). i18n anahtar sızması 0 (her iki dilde). 8 grafik başlığından 7'si çevrilmiş, çevrilmeyenler: hybrid_thrust_plot başlığı 'Thrust and Chamber Pressure vs Time'; efsane 'Mole fraction' ve 'Sweep maximum'; x ekseni kategori etiketleri 'Chamber' (×5), 'Throat' (×2), 'Exit' (×2); enjektör kutusu 'Total Flow: not reported'. Kimyasal formüller (CO, N2, CH4, HCN) çevrilmemiş — doğru davranış, bulgu değil. Ekran görüntüsü: .../faz6/hibrit/E_tr_sayfa.png

**Tekrar üret:** Sağ üst dil seçicisinden 'Türkçe' seç → Calculate → yukarıdaki metinleri sayfada ara.

### T58 — DÜŞÜK — Parametrik duyarlılık taramasında 'Thrust' alt grafiği tanımı gereği sabit — bilgi taşımıyor

**Sayfa:** `/hybrid` · **Bileşen:** parametric_plot — Thrust vs O/F alt grafiği · **Hüküm:** anlamsız

**Kanıt:** O/F 1,5→4,0 (10 nokta) taramasında ölçülen seriler: Specific Impulse 162,294–217,049 s (değişiyor), Propellant Mass 4,679–6,232 kg (değişiyor), Throat Diameter 21,567–21,817 mm (değişiyor), Thrust 1000–1000 N (tam sabit). İtki tasarım girdisi olduğu için çözücü motoru her O/F'de 1000 N'a boyutlandırıyor; dolayısıyla bu alt panel yapı gereği hiçbir zaman değişemez. Dört panelin biri bilgi taşımıyor. Ekran görüntüsü: .../faz6/hibrit/J_parametrik.png

**Tekrar üret:** Analysis Type: Parametric Analysis → Run Parametric Analysis → sağ üst alt grafiğe bak (düz çizgi).

### T59 — DÜŞÜK — Find Optimum sırasında Cantera geçerlilik aralığı aşılıyor, arayüzde hiçbir iz yok

**Sayfa:** `/hybrid` · **Bileşen:** Find Optimum düğmesi / /api/find-optimum-of · **Hüküm:** eksik

**Kanıt:** Sunucu günlüğü (faz6/app_8081.log): 'CanteraWarning: ChemEquil::equilibrate: Temperature (3007.241555831928 K) outside valid range of 300 K to 3000 K' hemen ardından 'POST /api/find-optimum-of HTTP/1.1 200'. Arayüzde görünen tek şey: 'Optimum: 6.84 (Max Isp: 232.7 s)'. Denge çözücüsünün geçerlilik aralığı dışına çıkıp ekstrapolasyon yaptığı kullanıcıya iletilmiyor, öneri koşulsuz doğruymuş gibi sunuluyor.

**Tekrar üret:** Calculate → Find Optimum → sunucu günlüğündeki CanteraWarning satırını arayüzdeki sonuç metniyle karşılaştır.

### T60 — DÜŞÜK — Toplam motor boyu tabloda ve çizimlerde farklı (1661,6 mm ↔ 1676 mm)

**Sayfa:** `/hybrid` · **Bileşen:** Design Summary tablosu ↔ motor_plot ve 3B deck boyut etiketleri · **Hüküm:** yanıltıcı

**Kanıt:** Design Summary → 'Total Motor Length 1661.6 mm'; 2B kesit etiketi 'L_total = 1676 mm'; 3B deck 'L 1676 mm'. Fark 14,4 mm (%0,9). Kesitin ölçülen x aralığı -14,265 … +1662,127 mm, yani çizimler x=0'ın solundaki 14,3 mm'lik ön kapağı sayıyor, tablo saymıyor. Oda boyu ikisinde de tutarlı (tablo 1576,7 mm, çizim 1577 mm). Ekran görüntüleri: .../faz6/hibrit/hibrit_kesit_tane_boyu.png ve .../faz6/hibrit/I_3b_deck.png

**Tekrar üret:** Calculate → Design Summary'deki 'Total Motor Length' ile kesit çizimindeki 'L_total' etiketini karşılaştır.

### T61 — DÜŞÜK — Statik hesap sonrası panoya 'Real-Time' başlığı — bölüm başlığıyla ve verinin doğasıyla çelişiyor

**Sayfa:** `/hybrid` · **Bileşen:** realtime_dashboard_plot başlığı · **Hüküm:** yanıltıcı

**Kanıt:** Bölüm başlığı 'OPERATING POINT DASHBOARD', grafik başlığı 'Real-Time Motor Performance Dashboard' (TR: 'Gerçek Zamanlı Motor Performans Panosu'). Panelin kendi açıklaması ise 'Data source: Time histories come from the transient port-regression solution, not from a placeholder curve' diyor. Veri gerçek ve çözücüden geliyor (sahte gösterge DEĞİL), ama gerçek zamanlı değil — hesap sonrası statik görüntü. Ekran görüntüsü: .../faz6/hibrit/hibrit_calisma_noktasi_panosu.png

**Tekrar üret:** Calculate → 'OPERATING POINT DASHBOARD' bölüm başlığı ile içindeki grafiğin başlığını karşılaştır.

### T62 — DÜŞÜK — 'Total Impulse' alt sekmesi toplam impulsle ilgisiz beş grafik barındırıyor

**Sayfa:** `/liquid` · **Bileşen:** Single Point Analysis → 'Total Impulse' alt sekmesi (#total_impulse_content) · **Hüküm:** yanıltıcı

**Kanıt:** Bu sekmenin altında beliren grafikler: (1) Performance vs Mixture Ratio, (2) Engine Performance vs Altitude, (3) Combustion Efficiency Breakdown, (4) Performance Losses pastası, (5) Propellant Tank System — 3D CAD View. Hiçbiri toplam impuls değil; toplam impuls sekmede hiç gösterilmiyor. Grafikler createChartDiv ile #subsystemsGrid'e ekleniyor, o da bu sekmenin içinde. Ölçülen: sekme kapalıyken 0x0, açılınca 1224x400 — Plotly yeniden boyutlandırması DOĞRU çalışıyor, sorun yalnız sekme adlandırması. Ekran görüntüsü: scratchpad/faz6/sivi/06_total_impulse_sekmesi.png ; ölçüm: sivi/sekme.json (gizleyen: ['total_impulse_content:none'])

**Tekrar üret:** 'Calculate Engine Performance' → 'ANALYSIS RESULTS' → 'Total Impulse' alt sekmesine tıkla → içindeki beş grafiğin başlıklarını oku.

### T63 — DÜŞÜK — Aynı irtifa eğrisi iki ayrı grafikte, farklı çözünürlükte çiziliyor

**Sayfa:** `/liquid` · **Bileşen:** altitude_plot ve altChart (ikisi de 'Engine Performance vs Altitude') · **Hüküm:** anlamsız

**Kanıt:** İkisinin de başlığı aynı, ikisi de aynı fiziği çiziyor. altitude_plot: 8 nokta (0, 1, 5, 10, 20, 50, 80, 100 km). altChart: 13 eşit aralıklı nokta (0, 8,33, 16,67 … 100 km). Uç değerler birebir aynı (0 km 249,924 s; 100 km 337,359 s). altChart eşit aralıklı örneklediği için deniz seviyesindeki hızlı değişimi (0→8,33 km) düz bir çizgiye indirgiyor; altitude_plot'un 0/1/5/10 km örneklemesi aynı bölgeyi doğru gösteriyor. Ekran görüntüleri: scratchpad/faz6/sivi/05_irtifa_grafigi.png ve sivi/08_irtifa_haritasi_kopya.png ; ham veri: sivi/ham.json→irtifa

**Tekrar üret:** 'Calculate Engine Performance' → ALTITUDE PERFORMANCE panelindeki grafiği not al → 'Total Impulse' alt sekmesindeki 'Engine Performance vs Altitude' grafiğiyle karşılaştır.

### T64 — DÜŞÜK — Türkçe modda karışık dil: 'Çarpışmalı çiftler (angle not reported)'

**Sayfa:** `/liquid` · **Bileşen:** liquid_motor_kesit efsanesi, dil = Türkçe · **Hüküm:** dil

**Kanıt:** Türkçe modda kesit efsanesinde iz adı: 'Çarpışmalı çiftler (angle not reported)' — Türkçe ad çevrilmiş, parantez içindeki nitelik İngilizce kalmış. Aynı grafikteki diğer adlar düzgün çevrilmiş: 'Oda cidarı', 'Enjektör plakası', eksenler 'Eksenel konum (mm)' / 'Yarıçap (mm)', başlık 'MOTOR EKSENEL KESİTİ — ÇÖZÜCÜ GEOMETRİSİ'. Ölçüm: scratchpad/faz6/sivi/tr.json→grafik_tr[0].iz ; ekran görüntüsü: sivi/20_turkce_sonuc.png

**Tekrar üret:** /liquid → dil seçicisinden 'Türkçe' → 'Motor Performansını Hesapla' → motor kesiti grafiğinin efsanesini oku.

### T65 — DÜŞÜK — Boş eksen başlığı ve niteliksiz iki farklı 'Overall' verim

**Sayfa:** `/liquid` · **Bileşen:** combustionChart ve termal panelin 'Wall Temperatures vs Material Limits' grafiği · **Hüküm:** eksik

**Kanıt:** combustionChart ('Combustion Efficiency Breakdown'): x ekseni başlığı null (TR modda da ['Verim (%)', null]). Termal panelin duvar sıcaklığı grafiğinde bir eksen başlığı boş dize: {"text": "", "font": {...}, "standoff": 8} — başlık nesnesi var, metni yok. Ayrıca combustionChart 'Overall = %91,94' yazıyor (yanma verimi çarpımı: 0,9478*0,97), hemen yanındaki kayıp pastasının başlığı ise 'Overall Efficiency: 82.4%' (motor genel verimi, altı çarpanın çarpımı). İki farklı büyüklük, ikisi de niteliksiz 'Overall' etiketiyle, aynı sekmede yan yana. Ekran görüntüsü: scratchpad/faz6/sivi/09_yanma_verimi.png ; ölçüm: sivi/panel.json (THERMAL satırları), sivi/tr.json→grafik_tr[5].eksen

**Tekrar üret:** 'Calculate Engine Performance' → 'Total Impulse' alt sekmesi → 'Combustion Efficiency Breakdown' grafiğinin x eksenine bak; sonra THERMAL sekmesi → 'Run Analysis' → duvar sıcaklığı grafiğinin eksen başlığına bak.

### T66 — DÜŞÜK — Rıhtım sayı alanlarında 17 basamaklı ham kayan nokta artığı

**Sayfa:** `/solid` · **Bileşen:** ad_f_joint_seal_diameter_mm, ad_f_thermal_chamber_diameter, ad_f_structural_chamber_diameter, ad_f_safety_chamber_diameter · **Hüküm:** yanıltıcı

**Kanıt:** Alanlarda '106,00000000000001' ve '0,10600000000000001' yazıyor — 14-17 anlamlı basamak ve type="number" girdisinin içinde virgül ondalık ayracı. Değer doğru (106 mm kasa deliği), sunum bozuk. Ekran görüntüsü: kati/dock_STRUCTURAL.png ; ham veri: kati/dock_ondolum.json

**Tekrar üret:** /solid -> Calculate -> Analysis Dock -> STRUCTURAL -> 'Bolted Joint' bölümündeki 'Seal / Effective Diameter (mm)' alanına bak.

### T67 — DÜŞÜK — Yörünge panosunda gösterge başlığı çakışması ve figürde adsız boş iz

**Sayfa:** `/solid` · **Bileşen:** #trajectory_plots — 'Performance Summary' alt grafiği / 'Maximum Altitude (km)' göstergesi · **Hüküm:** yanıltıcı

**Kanıt:** 'Maximum Altitude (km)' gösterge başlığı 'Performance Summary' alt-grafik başlığının üzerine biniyor (iki satır iç içe). Göstergenin altında değeri olmayan bir delta işareti ('-') duruyor. Figürde 9. iz: name=null, 0 nokta. Ekran görüntüsü: kati/yorunge.png ; ham veri: kati/analiz_docku.json (yorunge.izler)

**Tekrar üret:** /solid -> Calculate -> Compute Trajectory -> sağ alttaki gösterge kutusuna bak.

### T68 — DÜŞÜK — Yörüngede açıklanmayan paraşüt varsayımı: 4,11 km'lik iniş 750 saniye sürüyor

**Sayfa:** `/solid` · **Bileşen:** Trajectory Analysis paneli / iniş fazı · **Hüküm:** yanıltıcı

**Kanıt:** Ölçülen: apoje 4,11 km (t≈20 s), toplam uçuş 770,4 s, iniş ~750 s (~5,4 m/s), net ivme min 0,00012 g. Panelde girilen Cd=0,5 / A=0,008 m² ile balistik iniş bunu veremez (terminal hız ≈141 m/s, iniş ~30 s). Kaynakta paraşüt modeli var (hrma/analysis/trajectory_analysis.py:166-208, varsayılan Cd 1,4), yani sonuç tutarlı — ama panelde paraşüt girdisi, grafik etiketlerinde 'recovery/parachute' ibaresi ve panel metninde açıklama yok. Ham veri: kati/son_kontroller.json ; ekran görüntüsü: kati/yorunge.png

**Tekrar üret:** /solid -> Calculate -> Compute Trajectory -> 'Altitude vs Time' alt grafiğinde inişin 750 saniye sürdüğünü ölç.

**Dosya ipucu:** hrma/analysis/trajectory_analysis.py:166-208 (set_recovery_parameters, DEFAULT_PARACHUTE_CD)

### T69 — DÜŞÜK — End-burner itki ekseninde sıfır bastırılmış: %0,4 değişim dik düşüş gibi görünüyor

**Sayfa:** `/solid` · **Bileşen:** #thrust_plot (grain_type = end_burner) · **Hüküm:** yanıltıcı

**Kanıt:** Eğri 532,6 -> 530,4 N (%0,4 değişim) ama y ekseni tam bu bandı kaplıyor (530,4-532,6). Grafik ilk bakışta dik bir düşüş gibi okunuyor; 'eksen sıfırdan başlamıyor' işareti yok. Bunun bilinçli tasarım kararı olduğu kodda yazılı. Ekran görüntüsü: kati/itki_end_burner.png ; ham veri: kati/geometri_taramasi.json

**Tekrar üret:** /solid -> Grain Type = End Burner -> Calculate -> Thrust Curve grafiğine bak.

**Dosya ipucu:** hrma/templates/solid.html:1808-1818 (hrmaAxisRange)

### T70 — DÜŞÜK — Kesitte BATES segment boşlukları çizilmiyor, grain tek blok görünüyor

**Sayfa:** `/solid` · **Bileşen:** #solid_motor_kesit — 'Fuel grain' izi · **Hüküm:** eksik

**Kanıt:** number_of_segments = 3 ve grain_gap = 2 mm olmasına rağmen 'Fuel grain' izi tek dörtgen: x = 36,4 -> 536,4 mm kesintisiz. Kasa boyu hesabında boşluklar dikkate alınıyor (604 = 500 + 2x2 + 100) ama çizimde görünmüyor. Ekran görüntüsü: kati/bates_kesit.png ; ham veri: kati/plotly_bates.json

**Tekrar üret:** /solid -> Calculate -> Motor Cross-Section grafiğinde grain bloğunu incele (3 segment yerine tek blok).

### T71 — DÜŞÜK — TR çeviri hatası: 'Web Thickness' -> 'Ağ Kalınlığı'

**Sayfa:** `/solid` · **Bileşen:** i18n — #solid_motor_table satır başlığı (TR) · **Hüküm:** dil

**Kanıt:** TR'ye geçildiğinde tablo başlığı 'Ağ Kalınlığı' oluyor. Katı yakıt terminolojisinde 'web' yanma eti demektir; 'ağ' (network) yanlış anlam taşıyor. Doğrusu 'Web Kalınlığı' veya 'Et Kalınlığı'. Diğer tüm çeviriler doğru ve eksiksiz (anahtar sızıntısı 0). Ekran görüntüsü: kati/dil_tr_tablo.png ; ham veri: kati/dil.json (tablo_basliklari)

**Tekrar üret:** /solid -> sağ üstteki dil seçicisinden Türkçe -> Calculate -> motor tablosundaki 9. satır.

**Dosya ipucu:** hrma/static/js/i18n_pages.js (TR sözlüğü, solid.ui.web_thickness)

### T72 — DÜŞÜK — "User Guide" düğmesi üç sayfadan ikisinde hiç görünmüyor; /launch-site üç kabuk betiğini de boşuna indiriyor

**Sayfa:** `yardımcı` · **Bileşen:** index + launch-site → kabuk düğmeleri (release_notes.js / user_guide.js / settings_panel.js) · **Hüküm:** eksik

**Kanıt:** Ölçülen düğme mevcudiyeti — /: Release Notes ✔ (modal açıldı: "RELEASE NOTES / v2.6.26"), User Guide ✘ YOK, Settings ✔ (modal açıldı); /formulas: üçü de ✔ (User Guide PDF'i açtı); /launch-site: üçü de ✘ YOK. Kök neden: üç betik de düğmeyi `.nav-links` kabına enjekte ediyor (user_guide.js:39, release_notes.js:220, settings_panel.js:332). index.html'de `.nav-links` yok ve yalnız #releaseNotesLink + #settingsLink açık bağlantıları var, #userGuideLink yok. launch_site.html'de ne `.nav-links` ne de üç açık id var — ölçüldü: navLinks=false, releaseLink=false, guideLink=false, settingsLink=false, window.HRMAReleaseNotes/HRMAUserGuide/HRMASettings = undefined. Kılavuzun kendisi sağlam: POST /api/user-guide/open?lang=en → {"opened":true,"path":".../HRMA-User-Guide-EN.pdf"}; iki dilde PDF paket içinde. Ekran görüntüleri: scratchpad/faz6/yardimci/index_en.png, ls_acilis_en.png

**Tekrar üret:** http://127.0.0.1:8084/ aç → alt bağlantı şeridinde Formula Reference / Launch Site / Release Notes / Settings var, User Guide yok. http://127.0.0.1:8084/launch-site aç → üst şeritte yalnız EN / TR / Back to app var.

**Dosya ipucu:** /Users/apple/HRMA/hrma/static/js/user_guide.js:39 (injectNavLink → .nav-links); /Users/apple/HRMA/hrma/templates/index.html:451-452; /Users/apple/HRMA/hrma/templates/launch_site.html:9-11

### T73 — DÜŞÜK — İngilizce arayüzde Türkçe metin: hazır saha listesinde "Mount Everest (yüksek arazi)"

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → #ls-presets · **Hüküm:** dil

**Kanıt:** locale=en-US tarayıcı bağlamında ölçülen seçenek listesi: ["—", "Kennedy Space Center LC-39A", "Baikonur 1/5 (Gagarin Start)", "Kourou ELA-3", "Rocket Lab LC-1 (Mahia)", "Esrange (Kiruna)", "Mount Everest (yüksek arazi)", "Sinop (TR)"] — yedi girdiden altısı İngilizce, biri Türkçe. Liste launch_site.html:605-612'de sabit kodlanmış ve i18n'den geçmiyor (TR modunda da aynı liste görünüyor). Koordinatlar doğru: KSC 28,6084/−80,6043; Baykonur 45,92/63,3422; Kourou 5,239/−52,7683; Mahia −39,2617/177,865; Esrange 67,8931/21,1043; Everest 27,9881/86,925; Sinop 42,0231/35,1531 — hepsini tek tek doğruladım ve küre üzerinde Sinop'un Karadeniz kıyısına, Mahia'nın Yeni Zelanda Kuzey Adası doğu kıyısına düştüğünü ekran görüntüsüyle teyit ettim.

**Tekrar üret:** http://127.0.0.1:8084/launch-site → dil EN → sol paneldeki "Shortcuts (not a limit — any point is selectable)" açılır listesini aç.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/launch_site.html:611

### T74 — DÜŞÜK — /launch-site TR modunda dört dizge İngilizce kalıyor (araç rozeti, araç notu, karo göstergesi, saha listesi)

**Sayfa:** `yardımcı` · **Bileşen:** /launch-site → i18n (i18n_launch_site.js) · **Hüküm:** dil

**Kanıt:** TR'ye geçildikten sonra ölçülen çevrilmemiş dizgeler: (1) araç adı rozeti "Example vehicle (example, not calculated)" — site.src.example anahtarı yok, t() geri düşüşle ham kaynak adını basıyor; (2) araç notu "No motor calculated in this session yet — showing the example vehicle."; (3) karo göstergesi "0 MB · 0 tile"; (4) hazır saha listesinin 7 girdisi. Sayfanın geri kalanı düzgün çevrilmiş ("Fırlatma Sahası ve Uçuş Yolu", "UÇURULAN ARAÇ", "Yer izi — Dünya dönüşü MODELLENMEDİ" vb.). Ham i18n anahtarı sızıntısı YOK: /(site|common|proj|fx|hero|card)\.[a-zA-Z_.]+/ kalıbını gövde metninde arattım, 0 eşleşme. index ve formulas TR çevirileri eksiksiz. Ekran görüntüsü: scratchpad/faz6/yardimci/ls_tr.png

**Tekrar üret:** http://127.0.0.1:8084/launch-site → üst sağdaki "TR" düğmesine bas → "UÇURULAN ARAÇ" bölümündeki araç adına, altındaki nota ve sağ alttaki karo göstergesine bak.

**Dosya ipucu:** /Users/apple/HRMA/hrma/static/js/i18n_launch_site.js (site.src.* ve site.noSessionVehicle anahtarları); /Users/apple/HRMA/hrma/templates/launch_site.html:605-612

### T75 — DÜŞÜK — Ana sayfa "Recent Projects" şeridinde CSS text-transform SI birim simgelerini büyütüyor: "ISP 207.1 S · IT 13428 N·S" (S = siemens, saniye değil)

**Sayfa:** `yardımcı` · **Bileşen:** / → #hrmaRecentProjects .aux-link · **Hüküm:** birim/ölçek yanlış

**Kanıt:** Ölçüldü — DOM metni: "UI-Denetim-Test [SOLID] — Fpk 8262 N · Isp 207.1 s · It 13428 N·s"; ekranda görünen: "UI-DENETIM-TEST [SOLID] — FPK 8262 N · ISP 207.1 S · IT 13428 N·S"; getComputedStyle(...).textTransform = "uppercase". project_bar.js:690 ve :693 birimleri doğru üretiyor ('s', 'N·s') ama şerit .aux-link sınıfını kullandığı için index.html'deki `.aux-link { text-transform: uppercase }` kuralı hepsini büyütüyor. SI'da saniyenin simgesi küçük 's'tir; büyük 'S' siemens'tir — ekranda özgül impuls "207,1 siemens", toplam impuls "13428 newton-siemens" yazıyor. Ekran görüntüsü: scratchpad/faz6/yardimci/index_birim_buyukharf.png

**Tekrar üret:** En az bir kayıtlı proje varken http://127.0.0.1:8084/ aç → "RECENT PROJECTS" şeridindeki karta bak.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/index.html — .aux-link kuralı (text-transform: uppercase, ~satır 294); üretici /Users/apple/HRMA/hrma/static/js/project_bar.js:680-694 ve :941-944

### T76 — DÜŞÜK — /formulas sayfasında dil seçici hiç yok (diğer iki sayfada var) ve künye başka marka taşıyor: "UZAYTEK"

**Sayfa:** `yardımcı` · **Bileşen:** /formulas → üst şerit + <title> · **Hüküm:** eksik

**Kanıt:** Ölçüldü: /formulas'ta #langSelect yok (langSel=false) ve [data-lang] düğmesi yok (langBtns=[]); dil ancak Settings modalından değiştirilebiliyor. Karşılaştırma: / sayfasında açılır #langSelect var, /launch-site sayfasında EN/TR düğmeleri var — üç sayfada üç farklı (birinde hiç) dil denetimi. Ayrıca document.title = "Rocket Motor Formulas - UZAYTEK" (TR'de "Roket Motoru Formülleri - UZAYTEK"), gezinme başlığı "MOTOR ANALYSIS - Formulas"; uygulamanın geri kalanı HRMA markası taşıyor (/ başlığı "HRMA — Rocket Motor Analysis Suite"). <title> etiketinde data-i18n niteliği de yok. Ekran görüntüleri: scratchpad/faz6/yardimci/formulas_en.png, formulas_tr.png

**Tekrar üret:** http://127.0.0.1:8084/formulas aç → tarayıcı sekmesi başlığına ve üst gezinme şeridine bak; dil değiştirecek bir denetim ara.

**Dosya ipucu:** /Users/apple/HRMA/hrma/templates/formulas.html:6 (<title>) ve navbar bölümü

