# `data/validation/` — 2.6.27+ modülleri için doğrulama veri kümesi

**Oluşturma:** 3 Ağustos 2026 · **Son ekleme:** 18 Ağustos 2026 (CFD viskoz kayıtları, parti 39)

Yol haritasının değişmez kuralı: *"Yeni fizik modülü doğrulama kümesiyle gelir.
Doğrulaması olmayan modül yayımlanmaz."* Bu dizin, yazılmakta olan dört modülün
(eksenel simetrik yapısal/termal FEA, yarı-1B lüle akışı, turbopompa
boyutlandırma, akustik kararlılık) karşılaştırılacağı **yayımlanmış** veriyi
tutar. Kaynak künyelerinin tam listesi: `docs/VALIDATION_SOURCES.md`.

## Kayıt biçimi

Her dosya bir vakadır ve şu alanları taşır:

| Alan | Anlamı |
|---|---|
| `case` | Vaka kimliği; **dosya adıyla birebir aynı olmalı** (bekçi sınar) |
| `description_tr` | Vakanın ne sınadığı ve neden burada olduğu |
| `inputs` | Modele verilecek girdiler |
| `expected_outputs` | Karşılaştırılacak değerler |
| `source` | `title`, `author`, `year`, `url_or_doi` |
| `retrieved` | Verinin çekildiği tarih |
| `confidence` | `high` / `medium` / `low` / `not_applicable` |

Ek alanlar: `reference_formulas`, `tolerance_pct`, `units`,
`verification_note_tr`, `derived_cross_checks`, `tags`. CFD kayıtlarında
ayrıca: `definitions` (St/h hangi ρ, u, c_p, ΔT ile tanımlı — bunlar olmadan
karşılaştırma anlamsız), `uncertainty` (kaynağın KENDİ hata beyanı),
`consistency_checks` (bizim çapraz sağlamalarımız), `source_type`
(yayımlanmış CFD kayıtlarında: `code_ansys_published` vb.),
`extraction_method_tr` (elle çıkarım yöntemi).

## Değerin cinsi — en önemli ayrım

Bir sayının nereden geldiği, ne olduğundan daha önemlidir. Kayıtlar bunu
`_status` etiketleriyle beyan eder:

| Etiket | Anlamı | Capa olarak kullanılır mı |
|---|---|---|
| `PUBLISHED_MEASUREMENT` | Yayımlanmış ölçüm | **Evet** |
| `PUBLISHED_HARDWARE` | Yayımlanmış donanım geometrisi | **Evet** |
| `DERIVED_ANALYTICALLY_EXACT` | Kapalı formdan tam türetme | **Evet** |
| `design_point_prediction` | Tasarım noktası tahmini (ölçüm değil) | Dikkatle |
| `MODEL_PREDICTION_NOT_MEASUREMENT` | Kaynağın kendi modelinin çıktısı | **Hayır** |
| `DERIVED_BY_US_NOT_PUBLISHED` | Bizim türettiğimiz kontrol büyüklüğü | **Hayır** |
| `NOT_MODELLED` / `NOT_PUBLISHED` | Veri yok, beyan var | — |

`MODEL_PREDICTION_NOT_MEASUREMENT` ayrımı özellikle önemli: NASA TM-107318'in
turbopompa tablosu bir *modelin* öngördüğü çalışma noktasıdır. O sayılarla
kıyaslama yapmak, HRMA'yı gerçeğe değil başka bir modele benzetmek olur.

## Bekçi

```bash
python3 data/validation/selfcheck.py
```

İki şey yapar:

1. **Şema denetimi** — zorunlu alanlar, künye tamlığı, `confidence` geçerliliği,
   `case` ile dosya adının uyumu.
2. **Yeniden türetme** — analitik kayıtlardaki **her sayı**, kaydın kendi
   `reference_formulas` alanındaki bağıntıdan yeniden hesaplanır ve dosyadaki
   değerle karşılaştırılır. 20 kaydın 14'ü böyle denetlenir; kalan 6'sı ölçüme
   ya da belgelemeye dayandığı için yeniden türetilemez (`MEASUREMENT_ONLY`) —
   onlar için uydurma bir "beklenen değer" üretilmez, yalnız şema ve iç
   tutarlılık sınanır. Ölçüm kayıtlarının en büyüğü (Back-Massier-Gier) yine de
   **iç tutarlılık** düzeyinde türetilir: boğulmuş debi çaprazı,
   h = q_w/(T_aw−T_w) yeniden hesabı, St↔h/(ρu·c_p) bandı — ve kaynağın İKİ
   belgeli anomalisi (test 275 debisi, test 268 dizgi hücresi) bekçide
   **anomali olarak kilitlidir**: biri sessizce "düzeltirse" bekçi kırmızıya
   döner, çünkü kayıt kaynağı yansıtmak zorundadır, akla yatkınlığı değil.

Beklenen değerler burada *kaynak* değil *tanık* muamelesi görür. Bir doğrulama
kümesinin en sinsi çürüme biçimi, içindeki sayının sessizce yanlış olmasıdır:
kimse fark etmez, çünkü "beklenen değer" tanım gereği doğru sayılır.

**Bekçinin ısırdığı ölçüldü.** Toleranslar bilerek dardır (alan-Mach için
5·10⁻⁷): gevşek toleransla (10⁻⁵) `2.197198050 → 2.1972` kırpması
yakalanmıyordu. Tolerans daraltılınca bekçi kendi veri kümemizde bir hassasiyet
eksiği buldu (A/A\*=4 ses altı kökü 6 hane yetersizdi) — değerler 9 haneye
çıkarıldı. Bu, bekçinin çalıştığının kanıtıdır.

## Kayıtlar

### Yapısal (FEA — D1/D3)
| Dosya | Ne sınar | Güven |
|---|---|---|
| `structural_ansys_vm25_internal_pressure.json` | Lamé kalın cidar, iç basınç | high |
| `structural_ansys_vm25_rotation.json` | Merkezkaç yükleme (turbopompa çarkı) | high |
| `structural_lame_thick_cylinder_si.json` | Aynı fizik, SI birimlerinde (birim bekçisi) | high |

### Termal (D2/D3)
| Dosya | Ne sınar | Güven |
|---|---|---|
| `thermal_semiinf_step_temperature.json` | Geçici iletim, Dirichlet basamak | high |
| `thermal_semiinf_constant_flux.json` | Geçici iletim, Neumann sabit akı | high |
| `thermal_bartz_accuracy_band.json` | Bartz'ın yayımlanmış **hata bandı** | high |

### Turbopompa (C1)
| Dosya | Ne sınar | Güven |
|---|---|---|
| `turbopump_rl10a33_design_point.json` | Küçük ölçek, 30 250 rpm, LH2 | high |
| `turbopump_rl10a33a_geometry.json` | Çark çapı, kanat yüksekliği (donanım) | high |
| `turbopump_f1_saturnv.json` | Büyük ölçek, 5 500 rpm, RP-1 | high |
| `turbopump_merlin_rd180_unavailable.json` | **Olumsuz kayıt** — veri yok beyanı | n/a |

### Lüle akışı (yarı-1B)
| Dosya | Ne sınar | Güven |
|---|---|---|
| `nozzle_isentropic_area_mach.json` | Alan-Mach, iki kök | high |
| `nozzle_normal_shock_divergent.json` | Iraksak kesitte normal şok | high |
| `nozzle_separation_criteria.json` | Beş ayrılma kriteri, künyeleriyle | high |

### Akustik
| Dosya | Ne sınar | Güven |
|---|---|---|
| `acoustic_cylindrical_chamber_modes.json` | Bessel kökleri, mod frekansları | high |
| `acoustic_f1_first_tangential.json` | F-1 ölçülen 1T frekansları + **model açığı** | high |

### İki-faz
| Dosya | Ne sınar | Güven |
|---|---|---|
| `twophase_particle_loading_loss.json` | Denge limiti (gecikme kaybı **eksik**) | **low** |

### CFD viskoz — lüle duvar ısı transferi (V3+, parti 39)
| Dosya | Ne sınar | Güven |
|---|---|---|
| `nozzle_back_massier_gier_1964.json` | **BİRİNCİL capa**: JPL TR 32-415 (Rev.1, 1965; IJHMT 1964) soğutulmuş 30°-15° konik lüle. 6 koşumun tam B-3 tablosu (q_w, T_w, T_e, h, ρu, Re/in, St; 22 istasyon) + 4 koşumun B-2 duvar basıncı (32 tap) + 32 tap ve 22 tapa istasyonuyla as-built geometri. Elle, sayfa görüntüsünden. NTRS 19650010083 (PUBLIC), DOI 10.1016/0017-9310(64)90052-3 | high |
| `nozzle_boldman_conical_1968.json` | **Çapraz teyit**: NASA Lewis TN D-4788 (1968), 30° ve 60° konik lüleler, bağımsız teknik (Inconel ısı akısı ölçer), temiz gaz. Geometri TABLOLU; dağılımlar kaynakta yalnız şekil — eğri okunmadı, metin bulguları kayıtlı. NTRS 19680024170 (PUBLIC) | high |
| `nozzle_ansys_published_wang_2021.json` | **Yayımlanmış ANSYS sonucu** (üçlü kıyas: deney ↔ ANSYS ↔ HRMA): Fluent 18.2 + SST k-ω, eşlenik, test 262 koşulları; iç duvar T eğrisi Şekil 3b'den piksel kalibrasyonlu sayısallaştırma (±2 K) — kalibrasyon, deney noktalarının tam 25°F izoterm katlarına oturmasıyla kendiliğinden doğrulandı. GPPS-TC-2021-0105, CC BY 4.0 | medium |
| `nozzle_ansys_published_ansys_vmfl044.json` | **Belgeleme**: ANSYS'in KENDİ resmi doğrulama vakası VMFL044 aynı deneyi (test 268 koşulları, SST, Fluent+CFX) duvar basıncıyla sınar — sayısal tablo yayımlanmamış, kayıt künye+kurulum düzeyinde | medium |

## Bilinen boşluklar

Bunlar sessizce doldurulmamalıdır:

- **Turbopompa NPSH:** RL10 ve F-1 kaynaklarının **hiçbirinde** NPSH yok.
  C1'in "NPSH marjı" çıktısı bu kümeyle doğrulanamaz.
- **Merlin 1D / RD-180:** birincil kaynakta devir/çark çapı bulunamadı.
  İkincil derlemelerdeki sayılar capa değildir.
- **İki-faz gecikme kaybı:** görgül bağıntı alınamadı; kayıt `NOT_MODELLED`.
- **F-1 oda yarıçapı:** kullanılan kaynakta yayımlanmamış; akustik karşılaştırma
  bu yüzden mertebe göstergesidir, capa değildir.
- **BMG 44 testin 38'i:** Tablo B-1'deki tam matris kayıtlıdır ama yalnız 6
  koşum tam çıkarıldı (288/266/262/268/278/275). Gerekirse aynı yöntemle
  (kaynak PDF `sources/` altında, sha256 MANIFEST'te) genişletilebilir.
- **BMG giriş bölgesi (z/L < 0.107):** tap verisi yok; kontur orada analitik
  kurguya kalır (kayıttaki `geometry_inconsistency_note_tr`).
- **Boldman St dağılımları:** yalnız log-log şekil; okunmadı. Metin bulguları
  (boğazda türbülanslı korelasyonun ~%50'si vb.) kayıtta.
- **Back-Cuffel-Massier 1970 (ASME J. Heat Transfer, laminerleşme):** telifli,
  bu turda **açılmadı**; künye Boldman kaydının çapraz atıflarında.
