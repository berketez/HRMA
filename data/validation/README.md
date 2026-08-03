# `data/validation/` — 2.6.27+ modülleri için doğrulama veri kümesi

**Oluşturma:** 3 Ağustos 2026

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
`verification_note_tr`, `derived_cross_checks`, `tags`.

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
   değerle karşılaştırılır. 16 kaydın 11'i böyle denetlenir; kalan 5'i ölçüme
   dayandığı için yeniden türetilemez (`MEASUREMENT_ONLY`) — onlar için uydurma
   bir "beklenen değer" üretilmez, yalnız şema ve iç tutarlılık sınanır.

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

## Bilinen boşluklar

Bunlar sessizce doldurulmamalıdır:

- **Turbopompa NPSH:** RL10 ve F-1 kaynaklarının **hiçbirinde** NPSH yok.
  C1'in "NPSH marjı" çıktısı bu kümeyle doğrulanamaz.
- **Merlin 1D / RD-180:** birincil kaynakta devir/çark çapı bulunamadı.
  İkincil derlemelerdeki sayılar capa değildir.
- **İki-faz gecikme kaybı:** görgül bağıntı alınamadı; kayıt `NOT_MODELLED`.
- **F-1 oda yarıçapı:** kullanılan kaynakta yayımlanmamış; akustik karşılaştırma
  bu yüzden mertebe göstergesidir, capa değildir.
