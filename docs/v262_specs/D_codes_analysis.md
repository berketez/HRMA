# D-track — Analiz backend uyarı/öneri kod kataloğu

**Üreten:** DEV-D-analysis ajanı (v2.6.2). **Kapsam:** `hrma/analysis/` altındaki
4 analiz modülünün kullanıcıya görünen uyarı/öneri metinleri artık sabit string
DEĞİL; `{code, params, severity}` kaydı döner. Frontend `TF(code, params)` ile
metni kurar (dil tamamen frontend'e taşındı).

**Şema (D-engines ajanıyla AYNI sözleşme):**
```python
{"code": "warn.<subsystem>.<slug>", "params": {...}, "severity": "critical|warning|info"}
```
- `<subsystem>`: `safety`, `thermal`, `structural`, `kinetic`.
- `severity`: metnin ciddiyeti (frontend renklendirmek için kullanabilir; render zorunluluğu yok).
- `params`: metne gömülü tüm değişkenler; i18n metni `{yer_tutucu}` ile aynı değeri gösterir.

**Yardımcı:** Her dosyada dosya-yerel `_mk_warning(code, severity='info', **params)`
tanımlı (parallel-write çakışması olmasın diye ortak modül YOK; şema birebir aynı).

**i18n-dicts + D-frontend için:** Aşağıdaki `code`'ların TR + EN karşılıkları
`i18n_common.js` (veya uygun sözlük) içine eklenmeli. `{yer_tutucu}` isimleri
`params` anahtarlarıyla birebir eşleşmeli.

---

## Etkilenen paneller / render noktaları (D-frontend'e handoff)

| Panel dosyası | Alan | Kaynak (backend) | Not |
|---|---|---|---|
| `safety_panel.js:300-301` | `s.recommendations` | `safety_analysis._generate_safety_recommendations` | listBlock → `TF()` ile render |
| `safety_panel.js:218-220` | `press.safety_devices_required` | `safety_analysis._determine_pressure_safety_devices` | **DİKKAT: `.join(' · ')` artık dict listesi → `TF()` ile map edilmeli** |
| `thermal_panel.js:422` | `safe.warnings` + `gsa.warnings` | `heat_transfer_analysis` (thermal-safety + gas-side + wall-clamp) | listBlock 'warn' |
| `thermal_panel.js:423-424` | `safe.recommendations` + `cool.recommendations` | `heat_transfer_analysis` (_get_safety/_get_cooling_recommendations) | listBlock 'info' |
| `structural_panel.js:269-270` | `sf.recommendations` | `structural_analysis` recommendations | listBlock 'info' |
| (kinetic panel YOK) | `detailed_results.kinetic.recommendations`, `design_recommendations.*` | `kinetic_analysis` | UI'da panel yok; kod+i18n hazır, ileride görünürse iki-dilli |

> Not: `safety_analysis` içindeki storage/transport/explosive/fire/PPE detay
> listeleri **hiçbir panelde/PDF'te render EDİLMİYOR** ve iç mantıkta substring
> kontrolüyle kullanılıyor (`'Class B' in fire_class`). Bunlar kasıtlı olarak
> string bırakıldı (sızmıyor + dönüştürmek iç mantığı kırardı). Bkz. rapor.

---

## safety (12 kod)

| code | severity | params | EN | TR |
|---|---|---|---|---|
| `warn.safety.do_not_proceed` | critical | — | CRITICAL: Do not proceed — unacceptable risk level | KRİTİK: Devam etmeyin — kabul edilemez risk seviyesi |
| `warn.safety.redesign_required` | critical | — | Redesign required to reduce fundamental hazards | Temel tehlikeleri azaltmak için yeniden tasarım gerekli |
| `warn.safety.increase_structural_sf` | warning | — | Increase structural safety factors | Yapısal emniyet faktörlerini artırın |
| `warn.safety.higher_strength_materials` | warning | — | Consider higher strength materials | Daha yüksek mukavemetli malzemeler değerlendirin |
| `warn.safety.blast_resistant_design` | warning | — | Implement blast-resistant design | Patlamaya dayanıklı tasarım uygulayın |
| `warn.safety.increase_safety_distances` | warning | — | Increase safety distances | Emniyet mesafelerini artırın |
| `warn.safety.toxic_gas_detection` | warning | — | Implement toxic gas detection systems | Toksik gaz algılama sistemleri kurun |
| `warn.safety.ppe_and_training` | info | — | Provide appropriate PPE and training | Uygun KKD (kişisel koruyucu donanım) ve eğitim sağlayın |
| `warn.safety.relief_valve_full_flow` | info | — | Pressure relief valve sized for full flow | Tam debiye göre boyutlandırılmış basınç tahliye valfi |
| `warn.safety.burst_disc_secondary` | info | — | Burst disc (secondary relief) | Patlama diski (ikincil tahliye) |
| `warn.safety.remote_pressure_abort` | info | — | Remote pressure monitoring with automatic abort | Otomatik durdurmalı uzaktan basınç izleme |
| `warn.safety.redundant_transducers` | info | — | Redundant transducers (2oo3 voting) and hard-wired cutoff | Yedekli dönüştürücüler (2oo3 oylama) ve donanımsal kesme |

## thermal (19 kod)

| code | severity | params | EN | TR |
|---|---|---|---|---|
| `warn.thermal.wall_exceeds_service` | critical | `T_wall, material, limit, q_MW` | UNSAFE: equilibrium wall temperature {T_wall} K exceeds {material} service limit {limit} K with the specified cooling — burn-through likely. Required cooling load q={q_MW} MW/m² at the throat. | GÜVENSİZ: denge cidar sıcaklığı {T_wall} K, belirtilen soğutmayla {material} servis sınırı {limit} K değerini aşıyor — cidar delinmesi olası. Boğazda gerekli soğutma yükü q={q_MW} MW/m². |
| `warn.thermal.wall_exceeds_allowable` | warning | `T_wall, material, allowable` | WARNING: equilibrium wall temperature {T_wall} K exceeds {material} allowable {allowable} K — strength margin lost. | UYARI: denge cidar sıcaklığı {T_wall} K, {material} izin verilen {allowable} K değerini aşıyor — mukavemet marjı kayboldu. |
| `warn.thermal.wall_nonphysical` | critical | `T_wall` | Wall temperature {T_wall} K is non-physical for any solid liner (>3500 K). Regenerative/film cooling or ablative liner required. | Cidar sıcaklığı {T_wall} K herhangi bir katı astar için fiziksel değil (>3500 K). Rejeneratif/film soğutma veya ablatif astar gerekli. |
| `warn.thermal.wall_pinned_adiabatic` | critical | — | Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient. | Denge cidar sıcaklığı adyabatik-cidar sıcaklığına yapıştı: modellenen soğutma büsbütün yetersiz. |
| `warn.thermal.outer_wall_clamped` | warning | `T_outer_raw, lower, upper, T_outer` | Outer wall temperature {T_outer_raw} K was outside the physical range [{lower} K, {upper} K] and was clamped to {T_outer} K — check wall thickness, conductivity and cooling inputs. | Dış cidar sıcaklığı {T_outer_raw} K fiziksel aralık [{lower} K, {upper} K] dışındaydı ve {T_outer} K değerine kırpıldı — cidar kalınlığı, iletkenlik ve soğutma girdilerini kontrol edin. |
| `warn.thermal.temp_exceeds_allowable` | critical | — | Wall temperature exceeds allowable limit | Cidar sıcaklığı izin verilen sınırı aşıyor |
| `warn.thermal.approaches_melting` | warning | — | Wall temperature approaches melting point | Cidar sıcaklığı erime noktasına yaklaşıyor |
| `warn.thermal.high_thermal_stress` | warning | — | High thermal stress — consider thicker walls | Yüksek termal gerilme — daha kalın cidar değerlendirin |
| `warn.thermal.high_heat_load_regen` | warning | — | High heat load — consider regenerative cooling | Yüksek ısı yükü — rejeneratif soğutma değerlendirin |
| `warn.thermal.high_conductivity_material` | info | — | Use high thermal conductivity materials | Yüksek termal iletkenlikli malzemeler kullanın |
| `warn.thermal.natural_insufficient` | warning | — | Natural cooling insufficient — use forced cooling | Doğal soğutma yetersiz — zorlanmış (forced) soğutma kullanın |
| `warn.thermal.heat_sink_short_burns` | info | — | Consider heat sink or thermal mass for short burns | Kısa yanmalar için ısı emici (heat sink) veya termal kütle değerlendirin |
| `warn.thermal.monitor_wall_temp` | info | — | Monitor wall temperature during operation | Çalışma sırasında cidar sıcaklığını izleyin |
| `warn.thermal.increase_wall_thickness` | warning | — | Increase wall thickness | Cidar kalınlığını artırın |
| `warn.thermal.improve_cooling` | warning | — | Improve cooling system | Soğutma sistemini iyileştirin |
| `warn.thermal.higher_temp_material` | warning | — | Use higher temperature material | Daha yüksek sıcaklığa dayanıklı malzeme kullanın |
| `warn.thermal.min_wall_thickness_3mm` | info | — | Minimum wall thickness should be 3mm | Minimum cidar kalınlığı 3 mm olmalı |
| `warn.thermal.thermal_barrier_coating` | info | — | Consider thermal barrier coating | Termal bariyer kaplama değerlendirin |
| `warn.thermal.implement_temp_monitoring` | info | — | Implement temperature monitoring | Sıcaklık izleme uygulayın |

## structural (9 kod)

| code | severity | params | EN | TR |
|---|---|---|---|---|
| `warn.structural.increase_wall_thickness` | warning | — | Increase wall thickness | Cidar kalınlığını artırın |
| `warn.structural.higher_strength_material` | warning | — | Consider higher strength material | Daha yüksek mukavemetli malzeme değerlendirin |
| `warn.structural.increase_chamber_wall` | warning | — | Increase chamber wall thickness | Hazne cidar kalınlığını artırın |
| `warn.structural.increase_nozzle_throat` | warning | — | Increase nozzle throat thickness | Lüle boğaz kalınlığını artırın |
| `warn.structural.thermal_stress_dominates` | warning | — | Thermal stress dominates: add cooling or thermal barrier | Termal gerilme baskın: soğutma veya termal bariyer ekleyin |
| `warn.structural.thin_wall_invalid` | warning | — | Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis | İnce-cidar varsayımı geçersiz (t/r>=0.1): kalın-cidar (Lamé) analizi kullanın |
| `warn.structural.axial_buckling_risk` | warning | — | Axial buckling risk (NASA SP-8007): stiffen or thicken wall | Eksenel burkulma riski (NASA SP-8007): cidarı güçlendirin veya kalınlaştırın |
| `warn.structural.severe_derating` | warning | — | Severe temperature derating (>30% yield loss): cool wall or change material | Şiddetli sıcaklık derating'i (>%30 akma kaybı): cidarı soğutun veya malzeme değiştirin |
| `warn.structural.thermal_margin_service_limit` | warning | — | Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material | Cidar sıcaklığı malzeme servis sınırının %15 içinde: soğutma ekleyin, yalıtın veya daha yüksek sıcaklığa dayanıklı malzeme seçin |

## kinetic (15 kod)

| code | severity | params | EN | TR |
|---|---|---|---|---|
| `warn.kinetic.significant_losses` | warning | — | Significant kinetic losses detected — consider nozzle design optimization | Önemli kinetik kayıplar tespit edildi — lüle tasarımı optimizasyonu değerlendirin |
| `warn.kinetic.low_completeness` | warning | — | Low reaction completeness — increase residence time or chamber temperature | Düşük reaksiyon tamamlanması — kalış süresini veya hazne sıcaklığını artırın |
| `warn.kinetic.severe_losses` | critical | — | CRITICAL: Severe kinetic losses — redesign required | KRİTİK: Şiddetli kinetik kayıplar — yeniden tasarım gerekli |
| `warn.kinetic.good_completeness` | info | — | Good reaction completeness — kinetic effects minimal | İyi reaksiyon tamamlanması — kinetik etkiler minimal |
| `warn.kinetic.acceptable_performance` | info | — | Kinetic analysis shows acceptable performance | Kinetik analiz kabul edilebilir performans gösteriyor |
| `warn.kinetic.longer_nozzle` | info | — | Consider longer nozzle for increased residence time | Artan kalış süresi için daha uzun lüle değerlendirin |
| `warn.kinetic.area_distribution` | info | — | Evaluate area distribution for better kinetic performance | Daha iyi kinetik performans için alan dağılımını değerlendirin |
| `warn.kinetic.increase_chamber_length` | info | — | Increase chamber length for better mixing | Daha iyi karışım için hazne uzunluğunu artırın |
| `warn.kinetic.staged_combustion` | info | — | Consider staged combustion for more complete reactions | Daha tam reaksiyonlar için kademeli yanma (staged combustion) değerlendirin |
| `warn.kinetic.nozzle_adequate` | info | — | Current nozzle design appears adequate | Mevcut lüle tasarımı yeterli görünüyor |
| `warn.kinetic.increase_chamber_temperature` | warning | — | Increase chamber temperature to accelerate reactions | Reaksiyonları hızlandırmak için hazne sıcaklığını artırın |
| `warn.kinetic.higher_chamber_pressure` | info | — | Consider higher chamber pressure for better kinetics | Daha iyi kinetik için daha yüksek hazne basıncı değerlendirin |
| `warn.kinetic.operating_suitable` | info | — | Operating conditions appear suitable | Çalışma koşulları uygun görünüyor |
| `warn.kinetic.high_species_exit` | warning | `species` | High {species} concentration at exit — consider mixture ratio adjustment | Çıkışta yüksek {species} derişimi — karışım oranı ayarını değerlendirin |
| `warn.kinetic.propellant_good` | info | — | Propellant utilization appears good | İtici kullanımı iyi görünüyor |

---

**Toplam: 55 kod** (safety 12 · thermal 19 · structural 9 · kinetic 15).
Tümü `hrma/analysis/{safety,heat_transfer,structural,kinetic}_analysis.py` içinde
`_mk_warning(...)` ile üretiliyor.
