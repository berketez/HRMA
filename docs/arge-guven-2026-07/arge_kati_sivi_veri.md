# ARGE Raporu: Katı ve Sıvı Motor Doğrulama Verisi (v2.5.0 "Güven Sürümü")

Tarih: 2026-07-17
Kapsam: Açık literatürden GERÇEK katı motor yanma hızı / static-fire verisi ve sıvı motor performans çapaları.
Yöntem: Her sayı birincil belgeden DOĞRUDAN okundu (PDF/sayfa indirilip incelendi); okunamayan sayı yazılmadı. Okunamayan kaynaklar "erişim durumu" ile listelendi.
İndirilen belgelerin yerel kopyaları: bu scratchpad dizininde (nakka_ds_burn.pdf, rl10_model_cr190786.pdf, rl10_tm107318.pdf, rs25_l3harris.pdf, rs25_fact_sheet.pdf, f1_news_reference.pdf, j2_news_reference.pdf, vulcain21_spec.pdf, ariane_orbital_prop.pdf, akron_bates_3292.pdf, spacex_f9_archive.html, dlr_p42.html).

Confidence tanımları:
- high: birincil belge (üretici/NASA/deney raporu) doğrudan okundu, sayı belgeden aynen alındı.
- medium: resmi/titiz kaynak ama tek kaynak, koşul belirsizliği var veya amatör-titiz deney.
- low / "yön gösterici, teyit gerekli": ikincil derleme (Wikipedia, astronautix, satnow vb.) — çapa olarak KULLANILMAZ, sadece yön gösterir.

---

## BÖLÜM 1 — KATI MOTOR VERİSİ

### 1.1 KN-Dekstroz (KNDX) ve KN-Sorbitol (KNSB) strand-burner yanma hızı verisi — R. Nakka (1999)

Künye: R. Nakka, "Effect of Chamber Pressure on Burning Rate for the Potassium Nitrate - Dextrose and Potassium Nitrate - Sorbitol Rocket Propellants", Haziran 1999, Issue 1. PDF: https://www.nakka-rocketry.net/soft/ds_burn.pdf (erişildi ve tamamı okundu). Özet sayfası: https://www.nakka-rocketry.net/bntest.html
Date checked: 2026-07-17. Confidence: medium (amatör ama belgeli, ölçüm belirsizlikleri raporlanmış — aşağıda artı/eksi listesi).

Deney disiplini (rapordan): Crawford tipi strand burner, N2 basınçlandırma, çift termokupl gate ölçümü, 0-5000 psi %0.25 doğruluklu Bourdon manometre, hidrostatik test 2500 psi. Toplam 37 yakma; KNDX 18 testten 14 geçerli (0-1610 psig), KNSB 19 testten 13 geçerli (0-1533 psig). O/F = 65/35 sabit. Geçersiz testlerin ret gerekçeleri raporlanmış (drooling/yan tutuşma).

HAM VERİ — KNDX (Tablo 2, rapor s.11; basınç mutlak):

| P (psia) | P (MPa) | r (cm/s) | r (in/s) |
|---|---|---|---|
| 14.7 | 0.101 | 0.215 | 0.085 |
| 113 | 0.777 | 0.759 | 0.299 |
| 162 | 1.12 | 0.751 | 0.296 |
| 238 | 1.64 | 0.754 | 0.297 |
| 340 | 2.34 | 0.798 | 0.314 |
| 440 | 3.03 | 0.830 | 0.327 |
| 537 | 3.70 | 0.932 | 0.367 |
| 666 | 4.59 | 1.100 | 0.433 |
| 860 | 5.93 | 1.308 | 0.515 |
| 968 | 6.67 | 1.314 | 0.517 |
| 1159 | 7.99 | 1.285 | 0.506 |
| 1233 | 8.50 | 1.232 | 0.485 |
| 1420 | 9.79 | 1.300 | 0.512 |
| 1625 | 11.20 | 1.392 | 0.548 |

HAM VERİ — KNSB (Tablo 3, rapor s.11):

| P (psia) | P (MPa) | r (cm/s) | r (in/s) |
|---|---|---|---|
| 14.7 | 0.101 | 0.256 | 0.101 |
| 110 | 0.756 | 0.898 | 0.354 |
| 117 | 0.808 | 0.937 | 0.369 |
| 207 | 1.43 | 0.784 | 0.309 |
| 218 | 1.50 | 0.781 | 0.307 |
| 316 | 2.18 | 0.765 | 0.301 |
| 416 | 2.87 | 0.792 | 0.312 |
| 549 | 3.79 | 0.765 | 0.301 |
| 674 | 4.65 | 0.952 | 0.375 |
| 845 | 5.83 | 0.977 | 0.385 |
| 1020 | 7.03 | 1.102 | 0.434 |
| 1209 | 8.33 | 1.091 | 0.430 |
| 1548 | 10.67 | 1.129 | 0.444 |

REJİM BAZLI a-n KATSAYILARI (r = a·P^n; rapor Tablo 4-5, s.17; SI: r mm/s, P MPa mutlak):

KNDX (plato davranışı, 5 rejim):

| P aralığı (MPa) | a (mm/s·MPa^-n) | n |
|---|---|---|
| 0.103 - 0.779 | 8.88 | 0.619 |
| 0.779 - 2.57 | 7.55 | -0.009 |
| 2.57 - 5.93 | 3.84 | 0.688 |
| 5.93 - 8.50 | 17.2 | -0.148 |
| 8.50 - 11.20 | 4.78 | 0.442 |

KNSB (mesa davranışı, 5 rejim):

| P aralığı (MPa) | a (mm/s·MPa^-n) | n |
|---|---|---|
| 0.103 - 0.807 | 10.71 | 0.625 |
| 0.807 - 1.50 | 8.763 | -0.314 |
| 1.50 - 3.79 | 7.852 | -0.013 |
| 3.79 - 7.03 | 3.907 | 0.535 |
| 7.03 - 10.67 | 9.653 | 0.064 |

Ek (aynı kaynak ailesi, https://www.nakka-rocketry.net/burnrate.html, okundu):
- KNSU (KN-sükroz 65/35) klasik tek-fit de Saint Robert davranışı gösterir (tam a-n tablosu bu sayfada metin olarak değil grafik olarak var; ham karşılaştırma eğrisi ds_burn.pdf Şekil 11'de).
- KNSU ölçülmüş c*: 850 m/s ("as obtained" iri oksitleyici tanesi) ve 911 m/s ("fine" öğütülmüş) — HRMA c* tahmini için küçük ama gerçek bir çapa (teorik c* ~ 950 m/s civarına karşı verim kıyası). Confidence: medium.
- KNSU ortam basıncında r = 3.8 mm/s; 68 atm'de ~15 mm/s (aynı sayfa).

Nakka verisi dahil edilmeli mi? (Berke kararına bırakılan artı/eksi):
- ARTI: Ham veri noktaları tek tek yayınlanmış (nadir); yöntem, cihaz, hata kaynakları, ret edilen testler belgeli; bağımsız motor testiyle çapraz doğrulanmış (aşağıda 1.3); KN-şeker HRMA katı modülünün amatör/eğitim kullanıcı kitlesinin ana yakıtı; 20+ yıldır topluluk tarafından kullanılıp pratikte doğrulanmış.
- EKSİ: Hakemli değil; tek deneyci; sıcaklık duyarlılığı "tentatif"; strand yoğunluğu döküm kalitesine bağlı (motor graini ile fark olabilir); 1999 cihaz hassasiyeti; mesa/plato rejim sınırları öznel çizilmiş (log-log elle kırılım).
- Öneri: "medium confidence, amatör-titiz" etiketiyle dahil et; UI'da kaynak rozeti göster. Karar: Berke.

### 1.2 KNSB rejim setinin bağımsız motor doğrulaması — Danish Space Challenge (DSC) statik testleri

Künye: ds_burn özet sayfası https://www.nakka-rocketry.net/bntest.html "Comparison with Actual Motor Burn rate Data" bölümü (okundu). Date checked: 2026-07-17. Confidence: medium.
- Motor: çap 102 mm, et 2 mm, uzunluk 300 mm; dikdörtgen kesitli grain 40 x 90 x 300 mm, yalnız 90 mm yüzeyler yanıyor; 6 statik test (test 1-2 boğaz 18 mm, test 3-6 boğaz 14 mm); yakıt 65/35 KNSB.
- Sonuç: Strand a-n seti ile hesaplanan toplam web tüketimi gerçekle Grain 1 için +%1.5, Grain 3 için -%6 farkla uyuştu.
- HRMA kullanımı: Geometri tam verilmiş; basınç-zaman eğrileri sayfada YALNIZ grafik (Şekil 8) — sayısallaştırma gerekir (WebPlotDigitizer). Sayısallaştırılırsa HRMA katı modülü için uçtan uca test olur: girdi (geometri + KNSB a-n) -> çıktı (Pc(t), yanma süresi) karşılaştırması.

### 1.3 APCP (AP/HTPB) yanma hızı — erişim durumu ve kullanılabilir parçalar

(a) Texas A&M (Petersen grubu) tezleri — OAKTrust açık arşiv:
- "High-Pressure Exponent Break of AP/HTPB-Composite Propellants" (doktora tezi): https://oaktrust.library.tamu.edu/items/8335861b-2f5a-4476-a7bc-f1861fa328ae
- "The Effects of Density on Burning Rates of AP/HTPB Composite Solid Propellants" (tez)
Erişim durumu: PDF indirme Cloudflare insan doğrulaması arkasında — bu oturumda otomatik indirilemedi, TARAYICI ile indirilebilir. İçerik (arama özetlerinden): 80/20 AP/HTPB temel formülasyonlar, strand burner ile 0.41-24.13 MPa aralığı, üs kırılması (exponent break) 20.7-34.5 MPa'da. SAYISAL a-n değerleri okunamadığı için buraya YAZILMADI — tarayıcı ile indirilip tablo çıkarılmalı. Confidence (erişilince): high beklenir.
- AIAA J. Propulsion & Power makaleleri (ör. doi:10.2514/1.B38173 "Very-High-Pressure Burning Rates of Aluminized and Nonaluminized AP/HTPB-Composite Propellants") paywall'lı.
- MIT açık arşiv "Slow-Burn Ammonium Perchlorate Propellants" (dspace 1721.1/130944): AWS WAF bot koruması — otomatik indirilemedi, tarayıcı ile mümkün.

(b) Sutton & Biblarz, Rocket Propulsion Elements — Bölüm 12 yakıt karakteristik tabloları (kitap): Klasik APCP a-n ve r aralıkları burada; kitap fiziksel/e-kopya olarak Berke'nin kütüphanesinden doğrulanmalı. Bu rapor kitaptan sayı AKTARMAZ (okunmadı). Yapılacak: tablodan 1-2 temsili APCP formülasyonu (a, n, geçerli P aralığı, yoğunluk) alınıp HRMA "literatür yakıtı" olarak eklenmeli, künyesi "Sutton & Biblarz, N. baskı, Tablo no" biçiminde girilmeli.

(c) University of Akron "Angry Listerine" APCP raporu (açık PDF, okundu):
Künye: Bettes J., Fuller A., "Design of an Experimental Solid Rocket Motor", Univ. of Akron Williams Honors College, Honors Research Project No. 3292, 22 Nisan 2024. https://ideaexchange.uakron.edu/honors_research_projects/1877 (PDF indirildi, okundu). Date checked: 2026-07-17.
- Formülasyon: APCP — AP + granül Al + CuO (katalizör) + R45-HTPB + IDP + MDI (yüzdeler raporda YOK; güvenlik nedeniyle verilmemiş olabilir).
- OpenMotor'a girilen özellikler (raporda Figür 1'den aynen): yoğunluk 0.05775 lb/in^3; a = 0.065214 in/(s·psi^n); n = 0.228085; geçerli aralık 400-900 psi; Tc 2600 K; egzoz molar kütlesi 23.411 g/mol; c* 4827 ft/s.
- DİKKAT: Bu a-n değerleri ProPEP TAHMİNİ + takım karakterizasyonu karışımı; raporda strand ölçümü yok. Confidence: low-medium.
- Gerçek veri: 54 mm BATES/moon-burner/finocyl statik ateşlemeleri (8 Ekim 2023) — thrust (load cell) + Pc (transducer) eğrileri Figür 5'te; ama (i) transducer kalibrasyon sorunu (negatif basınç ofseti), (ii) finocyl sayısal verisi bozulmuş, (iii) formülasyon yüzdeleri gizli. HRMA doğrulaması için SINIRLI değerli — "gösterim" düzeyi, çapa düzeyi değil.

(d) ThrustCurve.org (NAR/TRA sertifika test eğrileri): Ticari motorların (Cesaroni, AeroTech) sertifikasyon statik test itki eğrileri (.eng/.rse) kamuya açık ve veri disiplinli. EKSİ: formülasyon ve a-n gizli, grain geometrisi kısmi -> HRMA ilk-ilkelerden simüle EDEMEZ. Kullanım: yalnızca toplam impuls / yanma süresi sınıf doğrulaması (zayıf çapa). Not olarak tut.

### 1.4 Katı bölüm özet değerlendirme

Bugün itibarıyla "künyesi tam + sayısı doğrudan okunmuş" katı veri seti: KNDX (14 nokta + 5 rejim a-n), KNSB (13 nokta + 5 rejim a-n), KNSU (c* 850/911 m/s + 1 atm r), DSC KNSB motor geometrisi + %1.5/-6 uyum sonucu. APCP için en güçlü adaylar (TAMU tezleri, MIT makalesi) tarayıcı-erişimli; Sutton tabloları kitaptan alınacak. Bu ikisi tamamlanmadan APCP çapası "beklemede" sayılmalı.

---

## BÖLÜM 2 — SIVI MOTOR PERFORMANS ÇAPALARI

### 2.1 Çapa tablosu (tümü birincil belgeden okundu)

| Motor | Yakıt | İtki | Isp | Pc | MR (O/F) | Genişleme oranı | Geometri | Kaynak / Confidence |
|---|---|---|---|---|---|---|---|---|
| RL10A-3-3A (nominal) | LOX/LH2 | 16,500 lbf (73,400 N) vak | ~445 s (CR-190786 metni) | 475 psia | 5.0 | 61.0 | boğaz çapı 2.47 in; oda çapı 5.13 in | NASA CR-190786 s.2 + NASA TM-107318 s.2 ve Tablo 2.5.1; high |
| RL10A-3-3A (model tipik çalışma noktası) | LOX/LH2 | 16,452 lbf (gross) | 440.3 s | 482.0 psia (enjektör yüzü statik) | 5.26 | 61.0 | ṁ 37.36 lbm/s; Tc 5888 R; c* verimi 0.9892 | NASA TM-107318 Tablo 2.5.1; high (model değeri, P&W verisine dayalı) |
| RS-25 (%109 güç) | LOX/LH2 | 418,000 lbf SL / 512,300 lbf vak | 452.3 s vak | 2,994 psia | 6.03 | 69:1 | kuru kütle 7,774 lb; 168 x 96 in; gaz jeneratörü değil, kademeli yanma | L3Harris RS-25 spec sheet (07/2024, L26301) + NASA FS-2015-07-064-MSFC; high |
| F-1 (S-IC, SA-503 dönemi) | LOX/RP-1 | 1,500,000 lb SL (504'ten itibaren 1,522,000 lb) | 260 s (minimum, SL) | 965 psia | 2.27 | 16:1 (uzatmalı), 10:1 (uzatmasız) | ṁ_ox 3,945 lb/s, ṁ_f 1,738 lb/s; çıkış çapı 11 ft 7 in; Tc 5,970 F | Saturn V News Reference, F-1 Engine Fact Sheet (Aralık 1968 değişiklikli); high |
| J-2 (S-II/S-IVB) | LOX/LH2 | 230,000 lb (irtifa; 503 aracı 2. kademe 225,000 lb) | 424 s (427 s @ MR 5:1) | 763 psia | 5.5 | 27.5:1 | ṁ_ox 449 lb/s, ṁ_f 81.7 lb/s; çıkış çapı 6 ft 5 in; kuru 3,480 lb; Tc 5,750 F | Saturn V News Reference, J-2 Engine Fact Sheet (Aralık 1968); high |
| Vulcain 2.1 (Ariane 6 ana kademe) | LOX/LH2 | 1,371 kN vak | 432 s | 118.8 bar | 6.03 | (verilmedi) | ṁ 326 kg/s; lüle çıkış çapı 2.1 m; yükseklik 3.6 m; gaz jeneratörü çevrimi | ArianeGroup Vulcain 2.1 spec sheet (2020, arşiv kopyası); high |
| Merlin 1D (Falcon 9 1. kademe) | LOX/RP-1 | 845 kN / 190,000 lbf (motor başına); 9 motor SL toplam 7,607 kN / 1,710,000 lbf; vak toplam 8,227 kN | resmi sayfada YOK | resmi YOK | resmi YOK | resmi YOK | gaz jeneratörü çevrimi | spacex.com/vehicles/falcon-9 (Wayback 2025-01-01 anlık görüntüsü); high (itki), diğerleri resmi yayınlanmamış |
| Merlin Vacuum (MVac) | LOX/RP-1 | 981 kN / 220,500 lbf | resmi YOK | resmi YOK | resmi YOK | resmi YOK | yanma odası rejeneratif, uzatma radyatif soğutmalı | aynı kaynak; high (itki) |
| Aestus (Ariane 5 EPS) | N2O4/MMH | ~27.5 kN | resmi kaynakta YOK | resmi YOK | ṁ'den ~2.17 (6.3/2.9) | resmi YOK | ṁ_MMH 2.9 kg/s, ṁ_NTO 6.3 kg/s; basınç beslemeli | DLR Lampoldshausen P4.2 test sayfası; medium (tek resmi kaynak, "around 27.5 kN") |
| S400-15 apoje motoru (kıyas, küçük hipergolik) | N2O4-MON/MMH | 425 N | 321 s | (verilmedi) | (verilmedi) | (verilmedi) | basınç beslemeli; S400-12 varyantı: 420 N, 318 s | ArianeGroup "Spacecraft Propulsion" broşürü (Mayıs 2019), s.6; high |

Yön gösterici (teyit gerekli, ÇAPA DEĞİL): Aestus için ikincil kaynaklarda (Wikipedia/astronautix/satnow) vakum itkisi 29.6 kN, Isp_vak 324 s dolaşıyor; DLR'nin 27.5 kN'i ile fark mevcut — motorun nominal/geliştirilmiş sürümleri arasındaki fark olabilir, ESA Bulletin arşivinden teyit edilmeli. F-1 için ikincil kaynaklarda 1,522,000 lbf SL + Isp 265.4 s SL / 304.1 s vak görülür; fact sheet "minimum 260 s" der — HRMA karşılaştırmasında "260 s minimum, ~265 s tipik (teyitli değil)" diye ele alınmalı.

### 2.2 RL10A-3-3A ölçülmüş test noktaları (nokta-doğrulama altın seti)

Künye: M. Binder, "An RL10A-3-3A Rocket Engine Model Using ROCETS", NASA CR-190786, Temmuz 1993 — Tablo 1-5 (P&W test standı verisi; okundu). Date checked: 2026-07-17. Confidence: high.

| Test noktası | İtki (lbf) | MR (O/F) | Ölçülen Pc (enjektör yüzü statik, psia) | Ölçülen LOX pompa çıkış P (psia) | Ölçülen yakıt pompa çıkış P (psia) |
|---|---|---|---|---|---|
| 1 | 16,603 | 5.63 | 472.35 | 613.80 | 1,061.40 |
| 2 | 16,588 | 5.55 | 472.96 | 619.10 | 1,068.90 |
| 3 | 16,458 | 4.99 | 475.48 | 647.70 | 1,112.50 |
| 4 | 16,376 | 4.67 | 476.80 | 665.90 | 1,143.10 |
| 5 | 16,555 | 5.42 | 473.03 | 624.50 | 1,076.90 |

Not: ROCETS modeli bu 5 noktada tüm ölçülen parametrelerde %4 içinde, çoğunlukta %1 içinde kalmış — HRMA için "iyi bir sistem modeli bu banda girer" ölçütü olarak da kullanılabilir.

### 2.3 Ek geometri/çevrim verisi (HRMA girdi dosyaları için)

RL10A-3-3A (TM-107318 Tablolar 2.2.1-2.6.1, okundu): yakıt pompası 2 kademe (çark çapı 7.07 in), LOX pompa çark çapı 4.20 in; soğutma ceketi pass-and-a-half, 180 kısa + 180 uzun boru, sıcak duvar 0.013 in, ceket basınç düşümü 242.1 psid, ısı aktarımı 7994 Btu/s; enjektör 216 koaksiyel eleman; expander çevrim. Bunlar HRMA rejeneratif soğutma ve besleme panellerinin gerçekçi girdi örnekleri.

---

## BÖLÜM 3 — HRMA'DA SİMÜLE EDİLEBİLİRLİK DEĞERLENDİRMESİ

### Katı modül

| Veri seti | HRMA girdisi | HRMA çıktısı vs gerçek | Uygulanabilirlik |
|---|---|---|---|
| KNDX/KNSB rejim a-n | çok-rejimli r=aP^n (HRMA'nın yakıt DB'sine rejim tablosu olarak) | strand r(P) eğrisinin yeniden üretimi (triviale yakın) + motor simülasyonu | Doğrudan: HRMA yakıt kütüphanesindeki KN-şeker katsayıları bu tabloya sabitlenmeli, künye UI'da gösterilmeli |
| DSC KNSB motoru | grain 40x90x300 mm dikdörtgen (slab), boğaz 14/18 mm, KNSB a-n | Pc(t) eğrisi, yanma süresi, web tüketimi | Orta: basınç eğrileri sayısallaştırılmalı; HRMA'da dikdörtgen/slab grain desteği kontrol edilmeli (yoksa 2D yüzey gerilemesi eşdeğeri) |
| KNSU c* = 850/911 m/s | KNSU formülasyonu 65/35 | HRMA termokimya c* tahmini ve verim | Doğrudan: tek satırlık karşılaştırma, rapora "c* verim çapası" olarak girer |
| Akron 54 mm BATES | BATES grain + a=0.0652, n=0.228 (400-900 psi) | itki/Pc eğri biçimi | Zayıf: formülasyon yüzdesiz, transducer sorunlu — yalnız nitel |
| TAMU/MIT APCP (erişilince) | AP/HTPB a-n + yoğunluk | strand r(P), üs kırılması bölgesi | Güçlü aday: yüksek basınçta n kırılması HRMA'nın geçerlilik sınırı uyarısına dönüştürülebilir |

### Sıvı modül (nokta-doğrulama şablonu)

Her motor için HRMA'ya girilen: yakıt çifti, Pc, MR, genişleme oranı (+ biliniyorsa boğaz çapı). HRMA'nın ürettiği: Isp (SL/vak), c*, Tc, itki. Gerçekle kıyas:

| Motor | Kıyaslanacak HRMA çıktıları | Beklenen kullanım |
|---|---|---|
| RL10A-3-3A | Isp_vak (445/440.3 s), itki (16.5k lbf), c* (verim 0.9892 üzerinden), 5 test noktasında Pc-MR-itki tutarlılığı | BİRİNCİL çapa: tam geometri + ölçülmüş test noktaları var |
| RS-25 | Isp_vak 452.3 s, SL/vak itki oranı (418k/512.3k), Pc 2994 psia, e=69 | yüksek Pc kademeli yanma ucu; SL/vak itki oranı lüle modeli testi |
| F-1 | Isp_SL >= 260 s, itki 1.5M lb, Pc 965 psia, e=16, ṁ toplam 5,683 lb/s | LOX/RP-1 gaz jeneratörü; büyük ölçek; ṁ = F/(Isp·g) tutarlılık kontrolü |
| J-2 | Isp_vak 424 s (427 @ MR 5.0 — MR duyarlılık testi!), Pc 763 psia, e=27.5 | MR taraması doğrulaması: HRMA'nın Isp(MR) eğrisi 5.5->5.0'da +3 s vermeli |
| Vulcain 2.1 | Isp_vak 432 s, itki 1371 kN, Pc 118.8 bar, MR 6.03, ṁ 326 kg/s | Avrupa çapası; ṁ tutarlılığı (1371 kN / 432 s / 9.81 = 323.9 kg/s ~ 326 kg/s, %0.6) |
| Merlin 1D | yalnız itki (845 kN SL) | zayıf çapa: Isp/Pc resmi yok; "resmi sayı yalnız itki" notuyla listede tutulmalı |
| Aestus | itki ~27.5 kN, MR ~2.17 (ṁ'lerden) | hipergolik basınç-beslemeli örnek; Isp/Pc/e ESA Bulletin'den tamamlanınca çapa olur |
| S400-15 | Isp_vak 321 s, itki 425 N | küçük itki ucu: HRMA'nın küçük motor/enjektör modülüyle kesişim |

---

## BÖLÜM 4 — ÖNERİLEN ÇAPA SETİ

### Katı (4 seri + 1 beklemede)
1. KNSB rejim a-n seti (0.1-10.7 MPa) + DSC motor testi çapraz doğrulaması — ana katı çapası.
2. KNDX rejim a-n seti (0.1-11.2 MPa) + 14 ham nokta — ikinci yakıt, plato davranışı HRMA çok-rejim desteğini test eder.
3. KNSU c* çapası (850/911 m/s ölçüm) + 1 atm yanma hızı 3.8 mm/s — termokimya/verim kıyası.
4. Akron 54 mm BATES statik ateşleme (yalnız nitel eğri biçimi; düşük ağırlıklı).
5. BEKLEMEDE: APCP a-n — TAMU tezi (tarayıcıyla indir) veya Sutton & Biblarz tablosu (kitaptan) girilince aktifleşir. v2.5.0 raporunda "APCP çapası kaynağı" bölümü bu iki adımdan biri kapanmadan işaretlenmemeli.

### Sıvı (6 motor)
1. RL10A-3-3A — birincil (nominal + tipik nokta + 5 ölçülmüş test noktası + tam geometri).
2. RS-25 (%109) — yüksek basınç LOX/LH2.
3. J-2 — MR duyarlılığı dahil LOX/LH2 orta basınç.
4. F-1 — LOX/RP-1 büyük ölçek, düşük genişleme.
5. Vulcain 2.1 — bağımsız Avrupa verisi, ṁ tutarlılık çapası.
6. Merlin 1D — yalnız-itki çapası (resmi sınır açıkça belirtilerek); Aestus ve S400 yedek/ek olarak.

### Korelasyon raporu için önerilen metrikler
- Isp hata yüzdesi (motor başına, vak ve varsa SL), c* hata yüzdesi (RL10, KNSU), ṁ tutarlılığı, SL/vak itki oranı hatası (RS-25), MR-duyarlılık eğimi hatası (J-2 424->427 s).
- Kabul bandı önerisi: sıvı Isp tahmini ±%2 (ideal), ±%4 (kabul — ROCETS'in kendi bandı); katı r(P) rejim içi ±%10.

## Açık riskler
1. APCP çapası hâlâ kapanmadı — TAMU/MIT indirmeleri tarayıcı gerektiriyor; Sutton kitap doğrulaması Berke'de.
2. DSC basınç eğrileri yalnız grafik; sayısallaştırma hatası eklenir.
3. TM-107318'deki c* "7824 in/sec" birimi baskı hatası görünümlü (ft/s olmalı; 7824 ft/s = 2385 m/s LOX/LH2 için tutarlı) — HRMA kıyasında ft/s varsayılıp not düşülmeli.
4. F-1/J-2 fact sheet değerleri 1968 konfigürasyonu; uçuşlar arası küçük farklar var (503 vs 504) — hangi konfigürasyonun çapa alındığı raporda sabitlenmeli.
5. Merlin için Isp/Pc/MR resmi yayınlanmamış; ikincil sayı kullanmak "güven sürümü" ilkesiyle çelişir — yalnız itki ile sınırlı kalınmalı.
