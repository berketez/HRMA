# Doğrulama Kayıt Şeması (schema_version 1.0)

HRMA v2.5.0 "Güven Sürümü" gerçek-deney doğrulama veritabanının kayıt biçimi.
Her kayıt tek bir JSON dosyasıdır ve `hrma/data/validation_records/{hybrid,solid,liquid}/`
altında, git ile izlenerek yaşar. Şemanın tek makine denetçisi
`hrma/validation/experiment_db.py` içindeki elle yazılmış doğrulayıcıdır
(`validate_record` / `ensure_valid_record`); `jsonschema` paketi bilinçli olarak
KULLANILMAZ (yeni bağımlılık yasağı — paket bundle'ında yok).

## Tasarım ilkeleri

1. **`inputs` / `measured` ayrımı yapısal döngüsellik bekçisidir.** Bir anahtar
   iki blokta birden GÖRÜNEMEZ; doğrulayıcı böyle kaydı reddeder. `inputs`
   HRMA'ya girdi olarak verilebilecek, deneyde AYARLANAN büyüklüklerdir;
   `measured` deneyde ÖLÇÜLEN sonuçlardır. Korelasyon koşucusu (G2) yalnız
   `measured` anahtarlarını skorlayabilir; `inputs`'ta görünen büyüklük tahmin
   sayılmaz (aksi döngüsel doğrulamadır — hata tanım gereği sıfıra yakın çıkar).
2. **Belirsizlik asla uydurulmaz.** Kaynak belirsizlik vermiyorsa
   `measurement_uncertainty` alanı hiç yazılmaz; kapsam katsayısı (k)
   bildirilmemişse `coverage_k: null` bırakılır.
3. **Sentetik kayıt üretim ağacına giremez.** `synthetic: true` kayıtlar yalnız
   `tests/fixtures/` altında yaşar; `experiment_db.load_records` üretim
   ağacında sentetik kayıt bulursa yükleme HATA ile durur.
4. **Telif:** yalnız SAYISAL veri + tam künye saklanır; makale metni/figür
   görüntüsü repoya girmez.
5. **Sayılar orijinal birimleriyle, birim ekli anahtar adlarıyla saklanır**
   (ör. `thrust_kgf`, `chamber_pressure_psia`). Birim dönüşümü kayıt girerken
   DEĞİL, korelasyon adaptöründe (G2) yapılır; böylece kaynaktaki sayı
   diff'lenebilir kalır. `units_original` alanı kaynağın birim sistemini
   serbest metinle özetler.

## Üst düzey alanlar

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `schema_version` | str | hayır | Verilirse `"1.0"` olmalı |
| `test_id` | str | evet | Benzersiz kimlik; `[a-z0-9][a-z0-9_.-]{2,63}` (büyük/küçük duyarsız). Öneri: `<tip>-<kaynak><yıl>-<etiket>` (ör. `hyb-rezaei2018-t26`) |
| `record_type` | str | hayır | Verilmezse `static_fire`. Geçerli değerler ve anlamları aşağıdaki "`record_type` değerleri" bölümünde |
| `motor_type` | str | evet | `hybrid` / `solid` / `liquid`; dosyanın bulunduğu alt klasörle uyuşmalı |
| `source` | obje | evet | Künye bloğu (aşağıda) |
| `propellants` | obje | evet | Boş olmayan sözlük; değerler str/sayı/null (ör. `oxidizer`, `fuel`, `fuel_density_kgpm3`, `hrma_fuel_key`) |
| `geometry` | obje | evet | Motor/test geometrisi; değerler str/sayı/bool/null. Skorlanmaz, adaptör girdisidir |
| `inputs` | obje | evet | Boş olmayan sözlük; değerler SONLU sayı. Deneyde ayarlanan büyüklükler |
| `measured` | obje | evet | Boş olmayan sözlük; değerler sonlu sayı, `null` (ölçülmemiş) veya eğri objesi (aşağıda) |
| `measurement_uncertainty` | obje | hayır | Anahtarları `inputs` VEYA `measured` içinde tanımlı olmalı (girdi belirsizlikleri UQ için saklanabilir) |
| `anomaly` | obje | hayır | `{"flag": bool, "note": str}`; `flag: true` ise `note` zorunlu |
| `units_original` | str | evet | Kaynağın orijinal birimlerinin serbest metin özeti |
| `digitized` | bool | evet | Sayılar grafik sayısallaştırmasından mı geldi (WebPlotDigitizer vb.) |
| `synthetic` | bool | hayır | Varsayılan `false`. `true` yalnız test fikstürlerinde |
| `tags` | liste[str] | hayır | Serbest etiketler (`lab_scale`, `flight_heritage`, ...) |
| `notes` | str | hayır | Serbest metin: test standı, bilinen anormallikler, taşıma notları |

Bilinmeyen üst düzey alan REDDEDİLİR (yazım hatası koruması).

## `record_type` değerleri

Geçerli değerler `hrma/validation/experiment_db.py` içindeki `RECORD_TYPES`
kümesiyle birebir eşleşir (tek doğruluk kaynağı). Bilinmeyen bir değer
REDDEDİLİR. İlk üç tür başlangıç şemasından; son dört tür v2.5.0 "Güven Sürümü"
G3 küratörlük dalgasında birinci sınıf tür olarak eklendi (daha önce yalnız
`tags`/`notes` ile işaretleniyorlardı).

| Değer | Anlamı |
|---|---|
| `static_fire` | **Varsayılan** (`record_type` verilmezse bu kabul edilir). Tek bir yer ateşlemesinin motor-düzeyi ölçüm noktası: itki, oda basıncı, Isp, c\*, O/F, regresyon hızı gibi ölçülen büyüklükler. Korelasyon koşucusunun ana istatistik gövdesini bu tür oluşturur. |
| `flight` | Gerçek uçuştan geri-hesaplanan performans ölçümü (yer static fire yerine uçuş verisi). Şemada tanımlıdır; şu an veritabanında bu türde kayıt yoktur. |
| `engine_spec` | Yayımlanmış motor künyesi / spec-sheet çıpası (ör. RS-25, Vulcain 2.1, J-2). Ham bir ateşleme değil, üretici/kurum anma değerleridir; bağımsız nokta-kıyas çıpası olarak kullanılır. |
| `strand_burn_rate` | Crawford/strand yakıcıda ölçülen tek bir yanma-hızı - basınç (r(P)) noktası; motor koşusu yoktur. Saint-Robert a·P^n güç-yasasının noktasal doğrulaması için kullanılır (ağırlıklı katı KN-şeker verisi). |
| `campaign_statistics` | Çok-yakmalı bir kampanyanın istatistik özeti: ortalama/standart sapma/%95 güven aralığı seti. Tek bir static fire değildir; korelasyon koşucusunun v1 sürümünde `not_supported` sayılır (nokta-kıyasa girmez). |
| `regression_correlation` | Kaynağın kendi verisinden türettiği regresyon-hızı korelasyonu (ör. rdot = a·G_ox^n güç-yasası katsayıları). Bir yakma serisinden türer, tek static fire değildir; v1 koşucusunda `not_supported`. |
| `engine_test_point` | Motor testi nokta ölçümü (ör. ölçülmüş c\*). `engine_spec` kıyas yolundan HRMA tahmini ile noktasal karşılaştırmaya sokulur; `engine_spec` yayımlanmış anma değeriyken bu gerçek bir ölçüm noktasıdır. |

## `source` bloğu

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `citation` | str | evet | Tam künye (yazar, başlık, dergi/kurum, cilt, sayfa, yıl) |
| `doi` | str/null | hayır | Bilinmiyorsa yazılmaz veya `null`; ASLA tahmin edilmez |
| `url` | str | hayır | Erişim adresi |
| `access` | str | evet | `open` / `paywalled` / `public_domain` / `webpage` / `vendor_datasheet` / `book` / `synthetic` |
| `confidence` | str | evet | `high` (kaynak tablo/metinden doğrudan okundu) / `medium` (özet düzeyi, şekilden sayısallaştırma, kurumsal rapor) / `low` (ikincil aktarım, amatör kaynak, sentetik) |
| `date_checked` | str | evet | `YYYY-AA-GG` — sayının kaynaktan doğrulandığı tarih |
| `erratum` | str/null | hayır | Bilinen yayın düzeltmesi notu |
| `data_extraction` | str | hayır | `table` / `text` / `figure_digitized` / `vendor_datasheet` |
| `extraction_note` | str | hayır | Sayısallaştırma yöntemi/belirsizliği vb. |

## Eğri (zaman serisi) değeri

`measured` altında bir anahtarın değeri şu obje olabilir:

```json
{"time_s": [0.0, 0.5, 1.0], "value": [24.1, 25.9, 26.3]}
```

Kurallar: iki liste de sonlu sayılardan oluşur, uzunlukları eşit ve >= 2,
`time_s` kesin artan. Sayısallaştırılmış eğri kullanılıyorsa üst düzey
`digitized: true` ve `source.extraction_note` doldurulur.

## `measurement_uncertainty` bloğu

Anahtar başına obje:

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `value` | sayı > 0 | evet | Belirsizlik büyüklüğü |
| `type` | str | hayır | `relative` (varsayılan; kesir, ör. 0.0014 = %0.14) / `absolute` |
| `coverage_k` | sayı/str/null | hayır | Kapsam katsayısı (1, 2, ...) veya `"stated"`; kaynak belirtmemişse `null` |
| `source` | str | hayır | Kaynaktaki yeri (ör. "Tablo 1") |

## Asgari geçerli kayıt örneği

```json
{
  "schema_version": "1.0",
  "test_id": "hyb-ornek2020-t01",
  "motor_type": "hybrid",
  "source": {
    "citation": "Yazar, 'Başlık', Dergi, 1(1), 1-10, 2020",
    "access": "open",
    "confidence": "high",
    "date_checked": "2026-07-17"
  },
  "propellants": {"oxidizer": "n2o", "fuel": "htpb"},
  "geometry": {"throat_diameter_mm": 8.9},
  "inputs": {"mdot_ox_gps": 95.77, "burn_time_s": 6.55},
  "measured": {"c_star_mps": 1514, "isp_s": 204.6},
  "units_original": "g/s, s, m/s (kaynak tablosu)",
  "digitized": false
}
```
