# Çevrimdışı Sayısal Yükseklik Modeli (DEM) — köken, lisans, hata payı

Bu klasördeki grid, HRMA'nın "istediğin yerden fırlatma" özelliğinin
**çevrimdışı** rakım kaynağıdır. İnternet olmadan da tam çalışır.

| Alan | Değer |
|---|---|
| Dosya | `etopo2022_5min_int16.bin.gz` (+ `etopo2022_5min_meta.json`) |
| Boyut | 8.59 MB (gzip) / 18.66 MB (ham, bellekte) |
| Grid | 4320 x 2160, 5 ark-dakika (1/12°) |
| Tip | `int16` little-endian, satır-öncelikli, metre |
| Satır sırası | güneyden kuzeye (`lat0 = -89.958333°`, adım `+1/12°`) |
| Sütun sırası | batıdan doğuya (`lon0 = -179.958333°`, adım `+1/12°`) |
| Değerler | hücre **merkezi** örnekleri |

## Kaynak

* **Veri seti:** ETOPO 2022 v1, 60 ark-saniye, *ice surface* (buz yüzeyi)
* **Kurum:** NOAA National Centers for Environmental Information (NCEI)
* **DOI:** [10.25921/fd45-gt74](https://doi.org/10.25921/fd45-gt74)
* **Ürün sayfası:** <https://www.ncei.noaa.gov/products/etopo-global-relief-model>
* **Erişim uç noktası (OPeNDAP/DAP2):**
  `https://www.ngdc.noaa.gov/thredds/dodsC/global/ETOPO2022/60s/60s_surface_elev_netcdf/ETOPO_2022_v1_60s_N90W180_surface.nc`
* **İndirme tarihi:** `etopo2022_5min_meta.json` içindeki `retrieved_utc` alanı
* **Dikey datum:** EGM2008 geoidi · **Yatay:** WGS84 coğrafi (EPSG:4326)

## Lisans

ETOPO 2022 bir **ABD federal hükûmet ürünüdür**; 17 U.S.C. §105 uyarınca ABD
içinde telif hakkı korumasına konu değildir — fiilen **kamu malı**. NOAA/NCEI
ürün sayfası veriyi serbestçe kullanıma açar. Atıf zorunlu değildir ancak
uygulama arayüzünde yine de gösterilir (`ATTRIBUTION_LINES['dem_offline']`).

## Yeniden üretim

```bash
python3 tools/build_launch_site_dem.py            # tam üretim (~5 dk)
python3 tools/build_launch_site_dem.py --rows 120 # duman testi
python3 tools/build_launch_site_dem.py --requantize  # indirmeden yeniden sıkıştır
```

Script tam 933 MB'lık kaynak dosyayı **indirmez**; THREDDS OPeNDAP arayüzünden
adımlı (strided) alt küme ister: `z[2:5:10797][2:5:21599]`.

## Çözünürlük kaybı — açık beyan

**Yöntem: DECIMATION (nokta örnekleme), blok ortalaması DEĞİL.**
`stride=5, offset=2` her 5x5 kaynak bloğunun **merkez** hücresini alır.
Blok ortalaması, kaynak dosyanın tamamının indirilmesini gerektirir
(933 MB); bu depoda ölçülen bağlantı hızıyla (~150 kB/s) saatler sürerdi.

Sonuçları:

1. **Hücre boyu ~9.3 km (ekvatorda).** Bir hücre içindeki tüm arazi
   değişimi tek bir sayıya iner.
2. **Keskin tepeler sistematik olarak eksik görünür.** Everest zirvesi
   (gerçek 8849 m) bu gridde ~6529 m okunur (−2320 m). Bu bir hata değil,
   çözünürlüğün doğrudan sonucudur: 9 km'lik hücre zirveyi temsil edemez.
3. **Düz sahalarda hata küçüktür.** Ölçülen örnekler:

   | Saha | Grid | Yayımlanan | Fark |
   |---|---|---|---|
   | Kennedy Space Center LC-39A | −2.3 m | ~3 m | −5 m |
   | Cape Canaveral SLC-40 | −5.1 m | ~3 m | −8 m |
   | Baykonur 1/5 | 99.6 m | ~90 m | +10 m |
   | Kourou ELA-3 | 5.2 m | ~10 m | −5 m |
   | Esrange | 356 m | ~341 m | +15 m |
   | Denver (yüksek düzlük) | 1615 m | 1609 m | +6 m |
   | Ölü Deniz kıyısı | −427 m | ~−430 m | +3 m |
   | La Paz (dağlık) | 3959 m | ~3640 m | +319 m |
   | Everest zirvesi | 6529 m | 8849 m | **−2320 m** |

4. **Bu yüzden kod, tek bir "rakım" sayısı sunmakla yetinmez:** çevredeki
   3x3 hücrenin en düşük/en yüksek değerini de döndürür
   (`terrain_relief_min_m` / `terrain_relief_max_m`). Düz sahada bu bant
   dardır (KSC ~22 m), dağlık sahada geniştir (Everest ~2426 m, La Paz
   ~1670 m). Bant genişledikçe arayüz kullanıcıyı **elle rakım girmeye**
   yönlendirir.

   Kıyı sahalarında hücre karayı ve denizi birlikte örnekleyebilir; bu
   yüzden KSC gibi deniz seviyesine yakın sahalarda grid değeri hafifçe
   negatif çıkabilir (−2.3 m). Kod bu durumda fırlatma yüzeyini 0 m alır
   ve `below_sea_level` uyarısını görünür kılar — sessiz düzeltme yapmaz.
5. **Basınca etkisi:** deniz seviyesinde `|dP/dh| = ρ·g ≈ 12.0 Pa/m`.
   ±50 m → ±0.6 kPa (±%0.6); ±100 m → ±1.2 kPa (±%1.2). Karşılaştırma:
   ISA "standart gün" varsayımının gerçek güne göre yoğunluk sapması
   tipik olarak %5–15'tir. Yani **sınırlayıcı belirsizlik DEM değil,
   ISA varsayımının kendisidir.**

## Derin deniz nicemlemesi (yalnız dosya boyutu)

−500 m'den **derin** hücreler 100 m adımlara yuvarlanmıştır. Dünya'nın en
alçak açık kara noktası Ölü Deniz kıyısıdır (≈ −430 m); bu eşiğin altı tanım
gereği deniz/göl tabanıdır ve fırlatma sahası olamaz (deniz üstü fırlatmada
yüzey zaten 0 m alınır). **Kara ve kıyı değerleri hiç dokunulmadan kalır.**
Kazanç: 14.63 MB → 8.59 MB gzip. İşlem idempotenttir.

## Çevrimiçi alternatif (opsiyonel)

Kullanıcı çevrimiçi modu açarsa rakım Open-Meteo Elevation API'sinden
(Copernicus DEM GLO-90, 90 m, anahtarsız) istenir; başarısızlıkta **sessizce**
bu çevrimdışı gride düşülür ve arayüzdeki kaynak etiketi buna göre değişir.
Copernicus/Open-Meteo atıfı lisans gereği görünür tutulur.
