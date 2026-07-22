# Sıvı motor doğrulama çapaları — kaynak künyeleri ve çelişki notları

`liquid_engines.json` içindeki her `source_id`'nin tam referansı. Derleme tarihi ve
tüm URL erişim tarihi: **2026-07-22**. Kaynak hiyerarşisi CLAUDE.md kuralı 14'e göre:
birincil (üretici/NASA/AIAA/Sutton) > ikincil (Astronautix, aerospaceguide) >
Wikipedia (yalnız üretici/kurum atıflı infobox değerleri için, kaynak zinciri takibiyle).

Her motor için en az iki bağımsız kaynak kullanıldı; JSON'a birincil/en güvenilir
değer kondu, çelişen ikincil değerler bu dosyada listelendi.

## Güven sınıfı dağılımı (özet)

- `published`: NASA/üretici factsheet veya standart NASA/AIAA/Sutton tablo değeri.
- `reported`: basın/açıklama/ikincil derleme (SpaceX/Musk beyanı, Energomash spec'i
  Wikipedia infobox üzerinden, aggregator). Birincil belge bu oturumda dolaylı görüldü.
- `estimate`: resmî detay az; ikincil/türetilmiş (BE-4 iç değerleri, RL10B-2 T/W türetmesi).

Not (BE-4 / Raptor 2 uyarısı, görev direktifi): Bu iki motorda üreticinin resmî
ayrıntılı spec'i yok. BE-4 iç değerleri (Isp, Pc, kuru kütle) ikincil/tahmini olduğu
için `estimate`; Raptor 2 sayıları Musk/SpaceX kamuya açık beyanlarına dayandığı için
`reported`. Kalibrasyon ajanı bunlara düşük ağırlık vermelidir.

---

## Kaynak künyeleri

### wiki_f1
Wikipedia, "Rocketdyne F-1", https://en.wikipedia.org/wiki/Rocketdyne_F-1
(infobox üretici/NASA atıflı). Uprated Saturn V değerleri: SL 6,770 kN, vak 7,770 kN,
Isp 263/304 s, Pc 70 bar, MR 2.27, ε=16, kuru 8,400 kg, T/W 94.1, yakma 150-163 s,
turbopompa 41 MW.

### nasa_saturnv_f1_factsheet
Saturn V News Reference, F-1 Engine Fact Sheet, Aralık 1968 (kamu malı). HRMA'nın
mevcut `validation_records/liquid/liq-f1-sa503-1968-spec.json` kaydının kaynağıdır.
SA-503 dönemi çapası: SL itki 1,500,000 lbf (6,672 kN), "Isp minimum 260 s (SL)",
Pc 965 psia, MR 2.27.

### nasa_saturnv_j2_factsheet
Saturn V News Reference, J-2 Engine Fact Sheet, Aralık 1968 (kamu malı). HRMA mevcut
`liq-j2-sa503-1968-mr50/mr55-spec.json` kayıtları. Isp 427 s @ MR 5.0; 424 s @ MR 5.5;
Pc 763 psia; lüle çıkış ~6 ft 5 in.

### wiki_j2
Wikipedia, "Rocketdyne J-2", https://en.wikipedia.org/wiki/Rocketdyne_J-2
(SA-208/SA-504 versiyonu). Vak 1,033.1 kN, SL 486.2 kN, Isp vak 421 s / SL 200 s,
Pc 5,260 kPa (52.6 bar), MR 5.5, ε=27.5, kuru 1,788 kg, T/W 73.18, yakma 500 s.

### l3harris_rs25_spec
L3Harris RS-25 engine spec sheet (07/2024, belge no L26301) + NASA fact sheet
FS-2015-07-064-MSFC. HRMA mevcut `liq-rs25-109pct-spec.json` kaynağı (vendor datasheet).
%109 RPL: SL 418,000 lbf, vak 512,300 lbf, Isp vak 452.3 s, Pc 2,994 psia, MR 6.03,
ε=69, kuru 7,774 lb (3,526 kg).

### wiki_rs25
Wikipedia, "RS-25", https://en.wikipedia.org/wiki/RS-25 (Aerojet Rocketdyne / Astronautix
atıflı). SL 1,860 kN, vak 2,279 kN, Isp 366/452.3 s, Pc 20.64 MPa, MR 6.03,
kısılma %67-109, çevrim "fuel-rich dual-shaft staged combustion", ilk uçuş STS-1 1981.

### wiki_rd180
Wikipedia, "RD-180", https://en.wikipedia.org/wiki/RD-180 (RD AMROSS / NPO Energomash
üretici verisi atıflı infobox). SL 3,830 kN, vak 4,150 kN, Isp 311/338 s, Pc 26.7 MPa,
MR 2.72, ε=36.87, kısılma %47-100, kuru 5,480 kg, T/W 78.44, yakma 270 s,
kütle debisi 1,250 kg/s.

### aerospaceguide_rd180
AeroSpaceGuide.net, "RD-180", https://www.aerospaceguide.net/rocketengines/rd-180.html
(ikincil çapraz kontrol). wiki_rd180 ile aynı çekirdek değerleri verir (SL 3,830 kN,
Isp 311/338 s, Pc 3,870 psi, MR 2.72).

### wiki_rd170
Wikipedia, "RD-170", https://en.wikipedia.org/wiki/RD-170 (NPO Energomash atıflı).
SL 7,250 kN, vak 7,900 kN, Isp 309/337 s, Pc 24.52 MPa, MR 2.63, ε=36.9,
kısılma %40-100, kuru 9,750 kg, T/W 82, yakma 150 s, turbopompa 170 MW (tek mil),
propelan LOX/RG-1, ilk uçuş 13 Nisan 1985.

### spacex_falcon9
SpaceX, Falcon 9 resmî araç sayfası (spacex.com/vehicles/falcon-9). Merlin 1D
resmî itki çapası: SL 845 kN (190,000 lbf), motor başına. HRMA mevcut
`liq-merlin1d-thrust-spec.json` bu kaynağı Wayback 2025-01-01 anlık görüntüsüyle kullanır.
Not: SpaceX yalnız itkiyi resmî yayınlar; Isp/Pc/MR/ε resmî DEĞİLDİR.

### wiki_merlin
Wikipedia, "Merlin (rocket engine family)",
https://en.wikipedia.org/wiki/Merlin_(rocket_engine_family). Full Thrust: SL 845 kN,
vak 981 kN, Isp 282/311 s, Pc 9.7 MPa, T/W 184, kuru 470 kg, kısılma %40-100,
çevrim gaz jeneratörü. Bu ikincil değerlerin çoğu SpaceX tarafından resmî beyan
edilmemiştir → JSON'da `reported`.

### wiki_rl10
Wikipedia, "RL10", https://en.wikipedia.org/wiki/RL10 (versiyon tablosu). RL10B-2:
vak 110.1 kN (24,750 lbf), Isp vak 465.5 s, MR 5.88, ε=280, kuru 301 kg,
genişleyebilen karbon-karbon lüle, ilk uçuş 1998.

### aerospaceguide_rl10b2
AeroSpaceGuide.net, "RL10B-2",
https://www.aerospaceguide.net/rocketengines/RL10B-2.html (ikincil çapraz kontrol).
Vak 24,750 lbf, Isp 465.5 s, MR 5.88:1, ε=280:1, kuru 664 lb, lüle depolu 86.5 in /
açık 163.5 in. **Pc vermiyor.**

### autoevolution_rl10
autoevolution, "Aerojet Rocketdyne RL10",
https://www.autoevolution.com/news/aerojet-rocketdyne-rl10-... (RL10B-2 için Pc ~4.36 MPa
≈ 43.6 bar). Yalnız Pc için ikincil kaynak (birincil datasheet Pc bu oturumda
görülemedi). Karşılaştırma: enginehistory.org RPE 8.21 jenerik RL10 (RL10A-3) için
475 psia (32.7 bar) verir — bu erken varyant içindir, RL10B-2 değil.

### wiki_vulcain
Wikipedia, "Vulcain (rocket engine)",
https://en.wikipedia.org/wiki/Vulcain_(rocket_engine) (ArianeGroup/Snecma atıflı).
Vulcain 2: vak 1,359 kN, Isp vak 429 s, Pc 117.3 bar, MR 6.1, ε=58.2, kuru 1,800 kg,
yakma 600 s, iki ayrı turbopompa (O2: Avio ~3 MW @ 13,600 rpm; H2: Snecma ~12 MW
@ 34,000 rpm), ilk (başarısız) uçuş V157 11 Aralık 2002.

### blueorigin_be4
Blue Origin resmî BE-4 beyanı: 550,000 lbf (2,400 kN) SL itki, LOX/LNG (metan),
ox-zengin kademeli yanma. Blue Origin ayrıntılı Isp/Pc/MR/ε RESMÎ YAYINLAMADI.

### wiki_be4
Wikipedia, "BE-4", https://en.wikipedia.org/wiki/BE-4. SL 2,460 kN (orijinal) →
2,847 kN (iyileştirilmiş, Kasım 2025 listesi), Isp 340 s (SL), Pc 140 bar,
kısılma %40-100, kuru 5,400 kg, gimbal ±5°, tek ox-zengin ön yakıcı + tek turbin
iki pompayı sürer, hidrostatik yataklar, ilk uçuş Vulcan Centaur 8 Ocak 2024,
Vulcan yakma 299 s / New Glenn 191 s.

### wiki_raptor
Wikipedia, "SpaceX Raptor", https://en.wikipedia.org/wiki/SpaceX_Raptor. Raptor 2:
SL 2,256 kN (230 tf), vak 2,530 kN (258 tf), Isp SL 347 s, Pc ~300 bar, MR 3.6,
ε=34.34 (SL), kısılma %40-100, kuru 1,630 kg, T/W 141.1, FFSC çift turbopompa,
seri üretim 18 Aralık 2021, ilk uçuş IFT-1 20 Nisan 2023.

### spacex_musk_raptor
SpaceX / Elon Musk kamuya açık beyanları (Twitter/X ve basın toplantıları,
2019-2024). Raptor 2 SL itki 230 tf, SL Isp 347 s (Ağustos 2024 beyanı). `reported`
sınıfı — resmî mühendislik datasheet değil.

### faa_starship
FAA Starship/Super Heavy çevresel değerlendirme belgeleri (metalox karışım oranı
3.6:1 = 78% O2 / 22% CH4 kaynağı).

### aerospaceguide_rd170
AeroSpaceGuide.net, "RD-170",
https://www.aerospaceguide.net/rocketengines/rd-170.html (ikincil çapraz kontrol).
Vak itki 7,903 kN, Isp vak 336 s, uzunluk 3.56 m, çap 4.0 m, kütle 8,755 kg.
Not: kütle wiki_rd170'in 9,750 kg'ından ~%10 düşük (farklı donanım kapsamı olası).

### wiki_ariane5
Wikipedia, "Ariane 5", https://en.wikipedia.org/wiki/Ariane_5 (EPC H173 birinci
kademe bölümü, Vulcain 2 için ikincil çapraz kontrol). SL 960 kN, vak 1,390 kN,
Isp SL 310 s / vak 432 s. Vulcain 2'nin SL itki ve SL Isp değerleri buradan alındı
(wiki_vulcain bunları vermiyordu). Vak itki wiki_vulcain 1,359 kN'den ~%2 farklı.

### wiki_h2a
Wikipedia, "H-IIA", https://en.wikipedia.org/wiki/H-IIA (birinci kademe bölümü,
LE-7A için ikincil çapraz kontrol). LE-7A maks itki 1,098 kN, Isp 440 s, yakma 390 s.
LE-7A yakma süresi (390 s) buradan alındı.

### wiki_le7
Wikipedia, "LE-7", https://en.wikipedia.org/wiki/LE-7 (JAXA/MHI atıflı). LE-7A uzun lüle:
SL 870 kN, vak 1,098 kN, Isp SL 338 s / vak 440 s, Pc 12.0 MPa, MR 5.9, ε=51.9,
kuru 1,800 kg, T/W 65.9, fuel-rich kademeli yanma, ilk uçuş H-IIA 29 Ağustos 2001.

### sutton_rpe
G. P. Sutton & O. Biblarz, "Rocket Propulsion Elements", 9. baskı, Wiley 2017.
Genel referans (çevrim türleri, mertebe kontrolleri). JSON'da doğrudan sayı için
source_id olarak kullanılmadı; iç-tutarlılık ve çevrim sınıflandırma referansı.

---

## Çelişki ve karar notları

1. **F-1 itki/Isp (uprated vs 1968 factsheet).** JSON uprated Saturn V değerlerini
   (6,770 kN SL, Isp 263/304 s, wiki_f1) `published`/`reported` olarak koyar. HRMA'nın
   mevcut curated kaydı (nasa_saturnv_f1_factsheet) SA-503 1968 çapasını kullanır:
   1,500,000 lbf (6,672 kN) ve "Isp minimum 260 s" — ve 265.4 s SL / 304.1 s vak
   değerlerini "teyitsiz" işaretler. Fark ~%1.5 itki, ~1-3 s Isp. Kalibrasyon ajanı
   hangi konfigürasyonu çözdüğünü seçmeli; bu dosyada uprated set, HRMA kaydında
   1968 set var.

2. **RS-25 genişleme oranı: 69 mu 78 mi?** L3Harris vendor datasheet (l3harris_rs25_spec)
   **69:1** verir; Wikipedia infobox (wiki_rs25) **78:1** verir. Vendor datasheet
   birincil kabul edildi → JSON'da 69. SSME nozül alan oranı literatürde en yaygın
   69:1'dir; 77.5/78 bazı NASA belgelerinde geçer (farklı referans düzlemi/uzatma).

3. **RS-25 kuru kütle: 3,526 kg mı 3,177 kg mı?** L3Harris (7,774 lb = 3,526 kg)
   birincil alındı. Wikipedia 3,177 kg (7,004 lb) verir (muhtemelen farklı Block/
   konfigürasyon veya donanım kapsamı). ~%10 fark; T/W hesabını etkiler.

4. **RD-180 vakum itkisi.** wiki_rd180 4,150 kN; bazı Energomash kaynakları 4,152 kN.
   İhmal edilebilir fark, 4,150 kondu.

5. **BE-4 oda basıncı: 134 mü 140 mı?** wiki_be4 140 bar; Blue Origin'in erken
   sunumlarında ~134 bar (~1,950 psi) geçti. İkisi de resmî tam datasheet değil →
   `estimate`. JSON'da 140 (fetch edilen wiki değeri), not düşüldü.

6. **BE-4 SL itki: 2,400 mü 2,847 mi?** Orijinal Blue Origin beyanı 550,000 lbf
   (2,400 kN); Kasım 2025 wiki listesi iyileştirilmiş 640,000 lbf (2,847 kN). JSON
   orijinal 2,400 kN'yi `published` (blueorigin_be4) koyar, iyileştirilmiş değeri
   not olarak taşır — Vulcan/New Glenn ilk uçuşları orijinal itki sınıfındaydı.

7. **Vulcain 2 vs 2.1.** Bu dosya **Vulcain 2** (Ariane 5 ECA): vak 1,359 kN, Pc 117.3 bar.
   HRMA'nın mevcut `liq-vulcain21-2020-spec.json` kaydı **Vulcain 2.1** (Ariane 6):
   vak 1,371 kN, Pc 118.8 bar — farklı varyant, karıştırılmamalı.

8. **RL10B-2 oda basıncı.** Birincil datasheet Pc bu oturumda görülemedi; ~4.36 MPa
   (43.6 bar) yalnız ikincil kaynaktan (autoevolution_rl10) → `reported`. HRMA'nın
   mevcut RL10 kayıtları farklı varyanttır (RL10A-3-3A, Pc 475 psia = 32.7 bar) —
   RL10B-2 ile karıştırılmamalı.

9. **Merlin 1D karışım oranı.** SpaceX resmî yayınlamadı. LOX/RP-1 için ~2.34 tipik
   optimum literatürde geçer ama teyitli spec değil → JSON'da `null` (uydurma
   önlendi). Kalibrasyon ajanı MR'yi kendi optimum taramasından türetmeli.

10. **Raptor 2 vakum Isp'si.** SL varyantı için açıkça beyan edilmedi (~350 s mertebe;
    ayrı RVac varyantı ~363 s). `null` bırakıldı.

## İç tutarlılık denetimi (geçti)

- Aynı fazın ölçüldüğü her motorda `thrust_vac_kn >= thrust_sl_kn` ve
  `isp_vac_s >= isp_sl_s` sağlandı.
- Kaba c* mertebe kontrolü (g0·Isp_vak / CF, CF~1.6-1.9): tüm motorlarda LOX/kerosen
  için c*~1,800 m/s, LOX/LH2 için c*~2,300-2,400 m/s, LOX/metan için c*~1,900 m/s
  beklenen mertebede; saçma değer yok.
- Doğrulama betiği: şema tamlığı + tip + tutarlılık; `python3` ile çalıştırıldı,
  hata yok (rapor final metninde).
