# HRMA "İstediğin Yerden Fırlatma" Özelliği — Araştırma ve Öneri Raporu

Tarih: 2026-07-22 · Kapsam: salt araştırma (kod değiştirilmedi) · Hedef: dünyanın herhangi bir noktasını fırlatma sahası seçip rakım + atmosfer + konum-fiziğini performans grafiklerine ve 6-DOF simülasyonuna beslemek.

---

## 1. Yönetici Özeti (10 satır)

1. HRMA'nın atmosfer altyapısı zaten hazır: `constants.py` içinde merkezî USSA 1976 tablosu (`ISA_LAYERS`), hem düzlemsel (`trajectory_analysis.py`) hem 6-DOF (`six_dof_trajectory.py`) atmosferi mutlak irtifanın fonksiyonu olarak çözüyor. Fırlatma sahası eklemek yeni bir fizik motoru değil, mevcut `launch_altitude` girişini bir **konum→rakım→atmosfer** zincirinden beslemek demek.
2. `app.py`'de `launch_latitude=40.0` ve `launch_longitude=0.0` **zaten varsayılan olarak duruyor** ama hiçbir fiziğe bağlı değil — iskele hazır, kablolama yok.
3. Önerilen UX: **kademeli** — (Tier 0) hazır saha ön-ayarları + elle enlem/boylam + elle rakım (her zaman, çevrimdışı); (Tier 1) çevrimdışı statik dünya rölyef görseli üzerinden tıkla-seç; (Tier 2) çevrimiçi Leaflet+OSM + yer adı arama. Harita bir kolaylık, fizik için zorunlu değil.
4. Rakım kaynağı çevrimdışı: bundle'a **~18.7 MB**'lık 5 ark-dakika (≈9 km) küresel int16 DEM konur (ETOPO 2022 veya GMTED2010'dan yeniden örneklenir, ikisi de kamu malı). Bu, verilen 10-30 MB bütçesine tam oturur; ham 5' grid = 4320×2160×2 bayt = 18.66 MB (hesap teyitli).
5. Rakım kaynağı çevrimiçi (isteğe bağlı zenginleştirme): Open-Meteo Elevation (Copernicus GLO-90, 90 m, anahtarsız). Çevrimdışı DEM zaten birincil; çevrimiçi yalnızca hassasiyet rötuşu.
6. Kaba DEM'in rakım hatası (~±100 m) basınçta yalnızca **±1.2 kPa (±%1.2)** oynatır — ISA'nın gerçek güne göre yoğunluk hatası (%5-15) yanında **ihmal edilebilir**. Yani sınırlayıcı hata DEM değil, ISA varsayımının kendisi.
7. Atmosfer: taban ISA (saha rakımında) + **elle yüzey T/P override** (OpenRocket mantığı) + çevrimiçi Open-Meteo anlık hava ile otomatik doldurma. Her modun geçerlilik etiketi ve hata payı ekranda gösterilir.
8. Konum-fiziği: **enleme bağlı yerçekimi (Somigliana/WGS84)** eklenmeli — ucuz (tek formül, sıfır veri), doğru ve sistematik ~%0.5 sapmayı kaldırır. Isp tanımı standart g0=9.80665'te kalır; yerel g yalnızca ağırlık/yörünge/T-W'ye girer.
9. Coriolis ve Dünya-dönüşü (yörüngesel doğu-atış +465·cos(enlem) m/s bonusu) gerçek ama v1 için **erteleme** önerilir: performansı (apoje, delta-v) değil vuruş noktasını/yörünge bütçesini etkiler; şeffaf "modellenmedi" beyanıyla bırak, sonra opsiyonel toggle.
10. Toplam efor: önerilen v1 = **S+M** (birkaç gün). Tek anlamlı veri eklentisi ~10-20 MB DEM. Çevrimdışı-öncelik korunur; çevrimiçi her özellik saf fallback'e sahip.

---

## 2. Mevcut Durum (kod gerçeği — doğrulanmış)

Fizik motoru zaten konum-hazır; eksik olan tek şey konumu rakma/atmosfere çeviren katman.

| Bileşen | Dosya:satır | Durum |
|---|---|---|
| USSA 1976 tablosu | `hrma/constants.py:49` `ISA_LAYERS` (7 katman) + `isa_temperature()`, `isa_pressure()` | Var, merkezî, tek kaynak |
| Düzlemsel yörünge atmosferi | `hrma/analysis/trajectory_analysis.py:659` `_get_atmospheric_properties(altitude)` | Var; mutlak irtifa fonksiyonu |
| 6-DOF atmosferi | `hrma/analysis/six_dof_trajectory.py:49` `_atmosphere(h)` | Var; `ISA_LAYERS`'tan ρ + ses hızı |
| Fırlatma rakımı girişi | `app.py:565`, `1861`, `3313` `launch_altitude` | Var (elle giriş zaten mümkün) |
| Enlem/boylam varsayılanı | `app.py:3314-3315` `launch_latitude=40.0`, `launch_longitude=0.0` | Var ama **hiçbir fiziğe bağlı değil** |
| Yerçekimi (6-DOF) | `six_dof_trajectory.py:379` `g = G0*(R/(R+h))**2` | Ters-kare irtifa; **enlem yok** |
| Yerçekimi (düzlemsel) | `trajectory_analysis.py:68` `self.g0 = G_0` | Sabit; enlem yok |
| Rüzgâr | ikisinde de `wind_speed`, `wind_direction` | Var (elle 2B rüzgâr vektörü) |
| Fırlatma açısı/azimutu | `six_dof:230` `launch_elevation_deg`, `launch_azimuth_deg` | Var |
| Coriolis | `six_dof_trajectory.py:27` (docstring) | **Bilinçli olarak yok** ("sounding menzilinde ihmal") |
| Harita / geocoding / DEM altyapısı | — | **Hiç yok** (grep temiz; sıfırdan eklenecek) |

Sonuç: Bu bir "yeni motor" değil, bir **giriş kablolama** işi. Atmosfer zaten irtifayla değişiyor; DEM sadece `launch_altitude`'u besleyecek, Somigliana sadece `g0`'ı enlemle değiştirecek, T/P override sadece ISA datumunu yeniden çapalayacak.

---

## 3. Başlık Başlık Bulgular

### 3.1 Konum Seçimi UX'i

Dört yöntem ve önerilen kombinasyon:

**(a) Yer adı arama (geocoding) — çevrimiçi, opsiyonel.**
- Birincil öneri: **Open-Meteo Geocoding** (`https://geocoding-api.open-meteo.com/v1/search`). Anahtarsız, GeoNames tabanlı (300k+ şehir), sonuçta lat/lon **ve elevation ve timezone** döner — tek çağrıda konum+rakım.
- İkincil: **Nominatim (OSM)**. Anahtarsız ama katı kurallı: **maks 1 istek/sn**, geçerli `User-Agent`/`Referer` **zorunlu** (kütüphane varsayılanı yasak), sonuçlar **istemci tarafında önbeklenmeli**, tekrarlı aynı sorgu bloklanır. OSMF politikası ayrıca "LLM'ler bu servisi ancak politikaya belirgin şekilde işaret ederek önerebilir" diyor — bu yüzden Nominatim'i **ikincil** tutuyorum; Open-Meteo geocoding hem daha az kısıtlı hem rakımı da veriyor.
- Çevrimdışı fallback: arama kutusu pasifleşir; yerine **hazır saha ön-ayar açılır listesi** (aşağıda).

**(b) Enlem/boylam elle giriş — her zaman, çevrimdışı.** İki sayı kutusu (ondalık derece), anında DEM'den rakım. En sağlam taban; internetsiz tam çalışır.

**(c) Harita üzerinden tıklama.**
- Çevrimdışı sorunu gerçek: Leaflet tile'ları ya devasa (tüm dünya z0-z6 bile yüzlerce MB) ya boş kalır. Leaflet-offline pre-caching gerektirir → çevrimdışı-öncelik için uygun değil.
- **Önerilen çözüm: çevrimdışı = bundle'lanmış statik ekvirektangüler dünya rölyef görseli üzerinde tıkla-seç.** ~300 KB-1 MB koyu-tema PNG/WebP; piksel→coğrafi dönüşüm birebir doğrusal: `lon = px/W·360−180`, `lat = 90−py/H·180`. Slippy map, tile sunucusu, harici bağımlılık yok. Tıklama → lat/lon → DEM. Koyu temaya uygun rölyef görseli seçilir.
- Çevrimiçi = isteğe bağlı **Leaflet + OSM raster tile** yükseltmesi (pan/zoom/detay). OSM tile kullanım politikasına dikkat (düşük hacim, attribution zorunlu).

**(d) Düz rakım elle giriş — en basit fallback, her zaman açık.** Kullanıcı sahayı bilmiyorsa/istemtiyorsa tek kutuya metre girer. Mevcut `launch_altitude` alanı zaten bu.

**Önerilen kombinasyon:** Tier 0 (b)+(d)+**ön-ayar listesi** her zaman; Tier 1 (c) çevrimdışı statik görsel; Tier 2 (a)+(c-Leaflet) çevrimiçi. Ön-ayar listesi (Cape Canaveral, Kourou, Baikonur, Esrange/Kiruna, Vandenberg, Mahia, + Türkiye sahaları: Sinop, İncehisar/roketsan test aralığı, İTÜ/ODTÜ öğrenci sahaları) ~1 KB gömülü tablo — haritasız %90 gerçek kullanımı karşılar, en yüksek fayda/efor.

### 3.2 Konum → Rakım

**Çevrimdışı DEM — boyut hesabı (kendi aritmetiğim, teyitli):**

| Çözünürlük | ≈km (ekvator) | Grid | int16 ham boyut |
|---|---|---|---|
| 1' (60 ark-sn) | 1.9 | 21600×10800 | **466.6 MB** (kabul edilemez) |
| 2' | 3.7 | 10800×5400 | 116.6 MB |
| 3' | 5.6 | 7200×3600 | 51.8 MB |
| **4'** | 7.4 | 5400×2700 | **29.2 MB** (bütçe üst sınırı) |
| **5'** | 9.3 | 4320×2160 | **18.7 MB** (önerilen) |
| 6' (0.1°) | 11.1 | 3600×1800 | 13.0 MB |
| 10' | 18.5 | 2160×1080 | 4.7 MB |

**Öneri: 5 ark-dakika, 18.66 MB ham int16.** Görevdeki örnek hesapla birebir (4320×2160×2 = 18.7 MB). Terrain uzamsal korelasyonlu + okyanus geniş düz-sıfır bölge olduğundan gzip ~%40-60 sıkıştırır → diskte ~8-11 MB, ilk kullanımda RAM'e açılır (18.7 MB bellek önemsiz). İstenirse 6'/0.1° (13 MB) daha da güvenli; 4' (29 MB) daha hassas ama bütçe kenarında.

**Veri kaynağı ve lisans (kamu malı):**
- **ETOPO 2022** (NOAA NCEI): 15/30/60 ark-sn sürümleri, netCDF/GeoTIFF, Ice-Surface + Bedrock. ABD federal ürünü → fiilen kamu malı. Fırlatma için "Ice Surface" (kara yüzeyi) uygun. 60 ark-sn dosyayı indirip 5'e **downsample** ederiz (native dosyayı bundle'a KOYMAYIZ).
- **GMTED2010** (USGS/NGA): 30/15/7.5 ark-sn, kara-only (84°N-56°S), kamu malı. Kara odaklı fırlatma için ideal; "mean" katmanından 5'e örnekleme.
- İki kaynaktan biri yeter; ETOPO tam küresel kapsam (kutuplar dâhil), GMTED daha temiz kara. Öneri: **ETOPO 2022 60s → 5' mean-aggregate**; kaynak ETOPO ise deniz hücreleri 0'a kırpılır.

**Çevrimiçi DEM (opsiyonel):**
- **Open-Meteo Elevation** — Copernicus DEM GLO-90 (90 m), anahtarsız (ticari-dışı), tek çağrıda 100 koordinat, JSON. **Attribution zorunlu**: Copernicus + Open-Meteo + DOI. Birincil çevrimiçi seçenek (hava + geocoding ile aynı sağlayıcı → tek attribution).
- **Open-Elevation / OpenTopoData (public)** — anahtarsız ama public sunucu hız-limitli (OpenTopoData public: ~1 çağrı/sn, 1000/gün) ve güvenilirlik düşük; self-host çevrimdışı-öncelik için gereksiz karmaşa. **Elenir** (çevrimdışı DEM zaten birincil).

**Rakım hatasının basınca etkisi (teyitli sayı):** ISA deniz seviyesinde `dP/dh = −ρg ≈ −12.0 Pa/m`.
- ±50 m → ±0.60 kPa (±%0.59)
- ±100 m → ±1.20 kPa (±%1.19)
- ±200 m → ±2.40 kPa (±%2.37)

Kaba DEM tipik hata bandı (~±50-100 m, dağlık arazide daha fazla — çünkü 9 km hücre büyük rölyefi ortalar; ama fırlatma sahaları genelde düz) → basınçta **≤±%1.2**. Bu, ISA'nın gerçek atmosfere göre günlük yoğunluk sapmasının (%5-15) çok altında. **Sonuç: DEM kabalığı sınırlayıcı hata değil; kabul edilebilir.** Dürüst beyan: rakım ±(hücre hata payı) olarak gösterilir; dağlık sahada kullanıcı elle override'a yönlendirilir.

### 3.3 Konum + Rakım → Atmosfer Koşulları

**Taban (her zaman, çevrimdışı): ISA @ saha rakımı.** Mevcut `ISA_LAYERS` mutlak (MSL) irtifanın fonksiyonu; roket saha rakımı h0'dan başlar, atmosferi h0'dan itibaren örnekler. Bu zaten fizik olarak doğru ve mevcut kodda destekli — DEM sadece h0'ı verir.

**Elle yüzey override (OpenRocket paritesi):**
- Yüzey sıcaklığı override (°C/K): tüm troposfer T-profili ΔT kadar kaydırılır ("sıcak gün/soğuk gün" — non-standart gün atmosferi, MIL-STD-210 mantığı), yoğunluk yeniden hesaplanır.
- Yüzey basıncı override (hPa/QNH): basınç datumu ölçülen değere yeniden çapalanır.
- Bu iki alan mevsimsel gerçekçilik ihtiyacını karşılar; "ISA standart gün" varsayılan, override edilince etiket "elle/ölçülen" olur.

**Çevrimiçi zenginleştirme (opsiyonel): Open-Meteo Forecast.** `temperature_2m` + `surface_pressure` (+ istenirse `wind_speed_10m`, `wind_direction_10m`) anlık değerleri "Şu anki hava" butonuyla override alanlarını doldurur, zaman damgası + kaynak etiketiyle. **CC-BY 4.0 attribution zorunlu** ("Weather data by Open-Meteo.com" görünür olmalı), ticari-dışı 10.000 çağrı/gün ücretsiz. **Değer katıyor mu?** Evet ama sınırlı: yüzey T/P performansta ~%1-2 oynatır (basınç-itki terimi + yoğunluk). Karmaşıklık düşük (tek GET), fallback saf (ISA). **Öneri: ekle ama opsiyonel/ikincil tut** — ana hikâye ISA + override.

**RocketPy Environment referansı (hangi fikir alınır):** RocketPy `standard_atmosphere` (ISO 2533 ISA, varsayılan), `custom_atmosphere`, `wyoming_sounding`, `Forecast` (GFS/GEM/NAM/RAP), `Reanalysis` (ERA5), `Ensemble` sunar; lat/lon/elevation alır. **Alınacak:** ISA taban + isteğe bağlı gerçek-veri katmanı fikri, lat/lon/elevation'ın Environment'a girmesi. **Kapsam dışı (aşırı):** Wyoming sounding, GFS/ERA5 netCDF/OPeNDAP indirme — bunlar anahtarsız olsa da büyük dosya + bağımlılık; HRMA'nın çevrimdışı-öncelik + küçük-bundle kısıtına aykırı. Open-Meteo tek-GET bunların hafif muadili.

**OpenRocket / RASAero karşılaştırması:**
- **OpenRocket**: Fırlatma sahasında Latitude/Longitude/Altitude + atmosferik koşullar (barometrik basınç, sıcaklık, nem); ISA modeli; "simüle edilen Dünya şekli" seçeneği (flat/spherical/WGS84 benzeri); **Coriolis ivmesi dışa aktarılabilir değişken** (yani modellenir); çok-katmanlı rüzgâr. → HRMA için birebir UX şablonu: lat/lon/alt + taban T/P + ISA. HRMA zaten fırlatma açısı/azimut/rüzgâr'a sahip.
- **RASAero II**: Fırlatma sahası rakımına göre barometrik basıncı standart atmosfer varyasyonuyla düzeltir; kullanıcı hava istasyonu/havaalanı barometrik basıncını girebilir; rüzgârsız 2-DOF, rüzgârlı çok modlu. → HRMA'nın "rakım→ISA + elle basınç override" yaklaşımı tam olarak RASAero mantığı.

Her ikisi de HRMA'nın önerdiği modeli doğruluyor: **rakım→ISA taban + elle/ölçülen yüzey T-P override**. Fazlası (sounding, reanalysis) HRMA kapsamı için gereksiz.

### 3.4 Konumun Diğer Fizik Etkileri

**Enleme bağlı yerçekimi (Somigliana/WGS84) — EKLE (S efor, yüksek değer/maliyet).**
Somigliana kapalı formu: `γ(φ) = 9.780327·(1 + 0.0053024·sin²φ − 0.0000058·sin²2φ)` m/s². WGS84 uçları: ekvator 9.7803253359, kutup 9.83218493786.
Hesaplanan (teyitli):

| Enlem | g [m/s²] | g0'a göre |
|---|---|---|
| 0° | 9.78033 | −0.268% |
| 28.5° (Cape) | 9.79209 | −0.148% |
| 40° | 9.80170 | −0.050% |
| 60° | 9.81918 | +0.128% |
| 90° | 9.83219 | +0.260% |

Tam aralık %0.53. **Neden ekle:** tek satır formül, sıfır veri, doğru, sistematik biası kaldırır (yüksek enlem = yüksek g = düşük T/W = zorlaşan kalkış). **Kritik dürüstlük notu:** Yerel g **yalnızca ağırlık/yörünge/T-W'ye** girer; **Isp tanımı sözleşme gereği standart g0=9.80665'te kalır** (aksi Isp'yi bozardı) ve **ideal delta-v = Isp·g0·ln(MR)** de g0 kullanır — enlem yalnızca **yerçekimi kayıplarına** (~%0.5) dokunur. Kod bağlama: `six_dof:379` ve `trajectory:68`'de G0→g0_local(lat); irtifa ters-kare çarpanı korunur.

**Coriolis (6-DOF) — v1'de ERTELE, opsiyonel toggle olarak sonra.**
`a_cor = 2Ω×v`, Ω=7.292e-5 rad/s. v=1000 m/s → a_cor≈0.146 m/s²; 60 s'de ~260 m yanal kayma. **Apoje/delta-v'yi (performans) etkilemez, vuruş noktasını/menzil emniyetini etkiler.** Mevcut docstring bunu zaten dürüstçe "yok" beyan ediyor. Öneri: beyanı koru, enlem parametresi geldiğinde ileride opsiyonel açılabilir (M efor).

**Dünya-dönüşü yörünge bonusu — bilgilendirici göster, tam bağlama ERTELE.**
Doğuya ekvator atışında serbest hız `Ω·R·cos(φ) = 465.1·cos(enlem)` m/s (ekvator 465, 45° ~329, kutup 0). Yörüngesel araçlarda delta-v bütçesi için **büyük** etki ve enlem+azimut bağımlı. Ama mevcut sim düz-Dünya atış-yeri çerçevesinde; tam bağlama atalet/Dünya-sabit çerçeve ayrımı ister (M efor). **Öneri v1:** saha panelinde bilgilendirici satır olarak göster ("Doğu-ekvator atış bonusu: +XXX m/s @ bu enlem") ama 6-DOF'a coupling'i ertele; net etiketle.

**Rüzgâr iklimolojisi — KAPSAM DIŞI (v1).**
Mevcut elle rüzgâr vektörü (`wind_speed`/`wind_direction`) yeterli taban. Çevrimiçi Open-Meteo anlık rüzgâr override edebilir (yukarıda). Saha-başına rüzgâr gülü/iklim verisi büyük veri yükü + belirsizlik → **atla.** İleride çok-katmanlı rüzgâr (OpenRocket gibi) ayrı bir iş.

---

## 4. Önerilen Mimari

### 4.1 Veri Akışı

```
[UI: Fırlatma Sahası Paneli]
   yöntem ∈ {önayar | arama(çevrimiçi) | lat/lon | harita-tıkla | elle-rakım}
   çıktı: {lat, lon, elevation_source, elevation_m?, T0_override?, P0_override?, use_online}
        │  POST
        ▼
[YENİ endpoint: /api/launch-site/resolve]  (app.py)
        │
        ▼
[YENİ modül: hrma/analysis/launch_site.py]
   1) rakım:
        use_online → Open-Meteo Elevation (GLO-90 90m)   [fallback ↓]
        çevrimdışı → bundled 5' DEM bilinear lookup (±hücre hata payı)
        elle       → kullanıcı değeri
   2) atmosfer datumu:
        T0 = override ?? ISA_temperature(elev)   (constants.py)
        P0 = override ?? ISA_pressure(elev)
        use_online → Open-Meteo Forecast(T2m, surface_pressure) ile doldur
   3) yerel yerçekimi:
        g0_local = somigliana(lat)               (yeni, veri yok)
   4) döndür: {elevation_m, elev_err_m, g0_local, T0, P0, rho0,
               source_flags, warnings[]}
        │
        ▼
[Oturum/proje durumu: launch_site]  → performans + yörünge çağrılarına enjekte
        │                                   │
        ▼                                   ▼
[trajectory_analysis]                  [six_dof_trajectory]
   launch_altitude = elevation_m          launch_altitude = elevation_m
   g0 = g0_local                          G0 → g0_local (satır 379)
   ISA datum: T0/P0 re-anchor             _atmosphere: T0/P0 re-anchor
        │                                   │
        ▼                                   ▼
[Performans grafikleri: itki/Isp vs irtifa, T/W]   [6-DOF uçuş + hata çubukları]
```

Atmosfer datum re-anchor: `ISA_LAYERS` tabanındaki (0 m) `T_base=288.15`, `P_base=101325` yerine, override varsa profili ΔT kaydır / P'yi ölçülen yüzeyden hidrostatik yeniden çapala. Merkezî tek fonksiyon (`constants.py`'ye `isa_profile(alt, T0=None, P0=None)` gibi) — magic number kuralına uygun, iki motor da aynı kaynağı çağırır.

### 4.2 Çevrimdışı / Çevrimiçi Davranış Matrisi

| Özellik | Çevrimdışı (varsayılan, garanti) | Çevrimiçi (opt-in, zenginleştirme) |
|---|---|---|
| Yer adı arama | Pasif; yerine ön-ayar listesi | Open-Meteo Geocoding (anahtarsız) / Nominatim (ikincil, politika uyarılı) |
| Harita | Bundled statik dünya rölyef görseli, tıkla-seç | Leaflet + OSM raster tile (attribution) |
| Rakım | Bundled 5' DEM (±hücre hatası) | Open-Meteo Elevation GLO-90 90m |
| Yüzey T/P | ISA @ rakım (+ elle override) | Open-Meteo Forecast anlık, zaman damgalı |
| Yerçekimi | Somigliana(lat) — daima çevrimdışı | aynı |
| Rüzgâr | Elle vektör | Open-Meteo anlık rüzgâr (opsiyonel) |

Kural: Her çevrimiçi çağrı zaman aşımı + hata durumunda **sessizce çevrimdışı fallback'e düşer**, kaynak etiketi UI'da değişir ("çevrimdışı DEM" / "Open-Meteo, 14:32"). Çevrimiçi hiçbir zaman blocking değil.

### 4.3 Bundle'a Eklenecek Veri

| Öğe | Ne | Boyut | Kaynak | Lisans |
|---|---|---|---|---|
| Küresel DEM | 5' int16 küresel grid (4320×2160), gzip'li | ~9-11 MB disk (18.7 MB RAM) | ETOPO 2022 60s → 5' aggregate (veya GMTED2010) | Kamu malı (ABD Gov) |
| Çevrimdışı harita görseli | Ekvirektangüler koyu rölyef PNG/WebP | ~0.3-1 MB | Aynı DEM'den hillshade veya Natural Earth | Kamu malı / CC0 |
| Saha ön-ayarları | lat/lon/elev/isim tablosu (JSON) | ~1-5 KB | Elle derlenmiş | — |
| **Toplam** | | **~10-12 MB** | | Bütçe içinde |

Elenen alternatifler: native ETOPO 60s (466 MB) — bütçe; Leaflet çevrimdışı tile cache (yüzlerce MB veya boş) — bütçe/UX; sadece-çevrimiçi rakım — çevrimdışı-öncelik ihlali.

### 4.4 Hata Çubukları / Dürüstlük Beyanı (UI'da göster)

- Rakım: "±(DEM hücre hata payı) m; dağlık sahada elle giriş önerilir."
- Basınç: rakım hatasından türeyen ±%1.2 bandı; ISA-vs-gerçek-gün için "±%5-15 yoğunluk (standart gün varsayımı)" ayrı not.
- Yerçekimi: "WGS84 elipsoid normal g; gerçek yerel g ±birkaç mGal (ihmal)."
- Coriolis/Dünya-dönüşü: "Modellenmedi (v1) — vuruş noktası/yörünge bütçesi etkilenir, performans metrikleri etkilenmez."

### 4.5 Efor Tahmini

| İş | Efor |
|---|---|
| lat/lon + elle rakım alanları + saha ön-ayar listesi | S |
| Somigliana g + trajectory/6-DOF'a kablolama (Isp'yi g0'da tut) | S |
| ISA datum re-anchor (T0/P0 override, merkezî fonksiyon) | S-M |
| Çevrimdışı 5' DEM: veri hazırlama (downsample) + bilinear lookup modülü | M |
| Çevrimdışı statik dünya-görseli tıkla-seç | M |
| Open-Meteo çevrimiçi (elevation + weather + geocoding) + fallback | M |
| Leaflet + OSM çevrimiçi harita | M (ertelenebilir) |
| Coriolis / Dünya-dönüşü coupling | M-L (ertele) |
| **Önerilen v1 toplamı** | **S+M (birkaç gün)** |

**Öneri v1 kapsamı:** Tier 0 UX (önayar+lat/lon+elle rakım) + çevrimdışı 5' DEM + Somigliana g + ISA T/P override + Open-Meteo çevrimiçi (elevation/weather/geocoding) + çevrimdışı statik-görsel tıkla-seç. Leaflet, Coriolis, Dünya-dönüşü, iklim rüzgârı → v2.

---

## 5. Riskler / Açık Sorular

1. **DEM çözünürlük seçimi:** 5' (18.7 MB, ~9 km) mü 4' (29 MB, ~7 km) mü? Dağlık sahalarda 9 km hücre büyük hata verebilir — ama fizik etkisi ≤%1.2 basınç, ihmal. Öneri 5' + elle override kaçış valfi. Berke onayı gerekir.
2. **Isp ve g:** Ekipteki bazı formüller yerel g ile Isp'yi karıştırma riskini taşır. Kesin kural: Isp ve ideal delta-v **standart g0=9.80665**; yerel g yalnız ağırlık/yörünge kaybı/T-W. Kablolama sırasında `constants.py:G_0` ile `g0_local` ayrımı net yapılmalı.
3. **Open-Meteo lisans/attribution:** Elevation (Copernicus GLO-90) ve Forecast (CC-BY 4.0) **görünür attribution zorunlu**. UI'da "Rakım: Copernicus GLO-90 / Open-Meteo", "Hava: Open-Meteo.com" satırı şart, yoksa lisans ihlali. Ticari-dışı sınır: uygulama ücretsiz/ticari-dışı olduğu sürece sorun yok; ileride ticari sürüm olursa yeniden değerlendir.
4. **Nominatim politikası:** Önerilirse UI'da politikaya işaret + User-Agent + istemci önbellek zorunlu (OSMF kuralı). Bu yükten kaçınmak için birincil geocoding Open-Meteo.
5. **ETOPO vs GMTED seçimi:** ETOPO tam küresel (kutuplar), GMTED kara-temiz (84°N-56°S). Fırlatma sahaları için GMTED yeterli ama Antarktika/yüksek-enlem için ETOPO. Downsample script'i hangi kaynağı baz alacak — netleşmeli (öneri: ETOPO 2022 ice-surface).
6. **Çevrimdışı harita görseli tema uyumu:** Koyu tema için rölyef görseli ya hazır koyu-palet Natural Earth ya DEM'den üretilen koyu hillshade. Üretim script'i mi hazır asset mi — küçük tasarım kararı.
7. **DEM boyutu ölçümü belirsizliği:** ETOPO 60s native dosya boyutunu resmi sayfa vermedi; ama bizim eklediğimiz **downsample edilmiş 5' grid** boyutu aritmetikle kesin (18.66 MB ham). Native dosyayı bundle'a koymadığımız için native boyut belirsizliği risksiz.
8. **6-DOF çerçeve genişletmesi:** Coriolis/Dünya-dönüşü ileride eklenirse mevcut "düz-Dünya atış-yeri ataleti" çerçevesi atalet-vs-Dünya-sabit ayrımı ister; erken tasarımda enlem parametresini constructor'a koymak (kullanmasa bile) sonraki genişlemeyi kolaylaştırır.

---

## 6. Kaynaklar (değişken bilgiler için Claim / Evidence / Confidence / Date)

Tarih (hepsi): 2026-07-22.

**C1 — ETOPO 2022 çözünürlükleri ve lisansı.** Claim: 15/30/60 ark-sn, netCDF+GeoTIFF, Ice-Surface+Bedrock, kamu malı (ABD Gov), DOI 10.25921/fd45-gt74. Evidence: NOAA NCEI ürün sayfası (https://www.ncei.noaa.gov/products/etopo-global-relief-model), ESSD 2025 makalesi (https://essd.copernicus.org/articles/17/1835/2025/essd-17-1835-2025.html). Confidence: **high** (resmi + hakemli).

**C2 — DEM grid boyutları.** Claim: 5' küresel int16 = 4320×2160×2 = 18.66 MB; 4' = 29.16 MB; 6' = 12.96 MB. Evidence: kendi aritmetiğim (Python, teyitli). Confidence: **high** (deterministik).

**C3 — ISA basınç gradyanı / rakım hatası.** Claim: dP/dh≈−12.0 Pa/m; ±100 m → ±1.2 kPa (±%1.19). Evidence: ρg=1.225·9.80665, kendi hesabım; USSA 1976 (constants.py ISA_LAYERS ile tutarlı). Confidence: **high**.

**C4 — Open-Meteo Elevation.** Claim: Copernicus GLO-90 (90 m), anahtarsız (ticari-dışı), 100 koord/çağrı, attribution zorunlu (Copernicus+Open-Meteo, DOI 10.5270/ESA-c5d3d65). Evidence: https://open-meteo.com/en/docs/elevation-api. Confidence: **high** (resmi, tek sağlayıcı sayfası).

**C5 — Open-Meteo Forecast lisans.** Claim: CC-BY 4.0 veri, anahtarsız, ticari-dışı 10.000 çağrı/gün ücretsiz, `temperature_2m`/`surface_pressure` mevcut, attribution zorunlu. Evidence: https://open-meteo.com/en/licence, https://open-meteo.com/en/docs. Confidence: **high**.

**C6 — Open-Meteo Geocoding.** Claim: anahtarsız, GeoNames (300k+ şehir), lat/lon+elevation+timezone döner. Evidence: https://open-meteo.com/en/docs/geocoding-api, https://github.com/open-meteo/geocoding-api. Confidence: **high**.

**C7 — Nominatim kullanım politikası.** Claim: maks 1 istek/sn, User-Agent/Referer zorunlu, istemci önbellek zorunlu, tekrarlı sorgu bloklanır, LLM önerirse politikaya işaret şartı. Evidence: https://operations.osmfoundation.org/policies/nominatim/. Confidence: **high** (resmi OSMF).

**C8 — WGS84 normal yerçekimi.** Claim: Somigliana γ(φ)=γe(1+k·sin²φ)/√(1−e²sin²φ); ekvator 9.7803253359, kutup 9.83218493786; aralık %0.53. Evidence: MathWorks gravitywgs84 (https://www.mathworks.com/help/aerotbx/ug/gravitywgs84.html), NIMA TR8350.2 (WGS84). Confidence: **high** (standart).

**C9 — OpenRocket saha/Coriolis/Dünya modeli.** Claim: Latitude/Longitude/Altitude + atmosferik koşullar; simüle Dünya şekli seçeneği; Coriolis modellenir (dışa aktarılabilir); çok-katmanlı rüzgâr. Evidence: https://openrocket.readthedocs.io/en/latest/user_guide/advanced_flight_simulation.html, https://wiki.openrocket.info/Advanced_Flight_Simulation. Confidence: **medium-high** (readthedocs 429 verdi, wiki+search ile teyit; tam Dünya-şekli seçenek adları doğrulanamadı — **açık**).

**C10 — RASAero II atmosfer.** Claim: saha rakımına göre standart-atmosfer basınç düzeltmesi + elle barometrik basınç girişi; rüzgârsız 2-DOF. Evidence: RASAero II kullanıcı kılavuzu (studylib/scribd kopyaları). Confidence: **medium** (birincil PDF resmi site dışı kopya — **tek-kaynak riski işaretli**).

**C11 — RocketPy Environment.** Claim: standard_atmosphere (ISO 2533 ISA varsayılan), custom, wyoming_sounding, Forecast (GFS/GEM/NAM/RAP), Reanalysis (ERA5), Ensemble; lat/lon/elevation. Evidence: https://docs.rocketpy.org/en/latest/reference/classes/Environment.html, .../standard_atmosphere.html. Confidence: **high** (resmi doküman).

**C12 — GMTED2010.** Claim: 30/15/7.5 ark-sn, kara-only 84°N-56°S, kamu malı (USGS/NGA), GTOPO30 halefi. Evidence: https://www.usgs.gov/centers/eros/... GMTED2010, https://catalog.data.gov/dataset/global-multi-resolution-terrain-elevation-data-2010-gmted2010. Confidence: **high**.

**C13 — OpenTopoData.** Claim: self-host anahtarsız; public sunucu hız-limitli (~1/sn, 1000/gün); ETOPO1 kara=SRTM30, batimetri=GEBCO. Evidence: https://www.opentopodata.org/, https://github.com/ajnisbet/opentopodata. Confidence: **medium-high**.

**C14 — Mevcut HRMA kod gerçeği.** Claim: bölüm 2'deki tablo. Evidence: doğrudan dosya okuması (constants.py, trajectory_analysis.py, six_dof_trajectory.py, app.py). Confidence: **high** (birincil kaynak = kod).
