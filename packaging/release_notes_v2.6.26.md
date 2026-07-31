<!--HRMA-LANG:en-->
# HRMA v2.6.26 — Quality release

No new engineering features.

## Hybrid motor

- Safety factor, chamber length override, nozzle material, injector material,
  swirl chamber diameter and swirl angle were connected to the solver.
- Nozzle contour and injection velocity were removed; the fields they
  duplicated are Nozzle Type and Target Velocity.
- Parabolic was added to the nozzle type list.
- Thrust and chamber pressure over time is now plotted.
- A crash on the impingement injector was fixed.
- The fabricated hole plan produced when the injector circuit model cannot
  size an injector was removed.
- The injector shown on screen and the one drawn in CAD were unified.
- The combustion analysis chart now follows the selected oxidiser.
- The heat transfer analysis now uses the motor's own throat diameter,
  characteristic velocity and gas properties.
- Dry mass is now derived from geometry and material.
- Altitude performance now follows the expansion ratio.
- Chamber volume and chamber length source labels were corrected.

## Analysis deck

- Length unit conversion was corrected across nine panels.
- Fields the panels could not read were connected.

## Exports and interface

- Motor name and thrust coefficient missing from the Excel export were fixed.
- Modification of solver results in the display layer was removed.
- The version badge on the home page replaced a status indicator that
  reported nothing.

## Packaging and updates

- macOS code signing was repaired; unsigned packages can no longer be built
  or published.
- The Turkish section of the release notes was being truncated and is now
  delivered in full.

## Security

- Tracebacks and request bodies were removed from error responses.
- Non-numeric input no longer crashes the validator.

## Included

- Three example projects (hybrid, solid, liquid).
- A findings registry that ties every closed defect to the guard test that
  prevents its return.

<!--HRMA-LANG:tr-->
# HRMA v2.6.26 — Kalite sürümü

Yeni mühendislik özelliği yok.

## Hibrit motor

- Emniyet katsayısı, yanma odası boyu ezmesi, lüle malzemesi, enjektör
  malzemesi, swirl odası çapı ve swirl açısı çözücüye bağlandı.
- Lüle konturu ve enjeksiyon hızı kaldırıldı; yineledikleri alanlar Lüle Tipi
  ve Hedef Hız.
- Lüle tipi listesine parabolik eklendi.
- Zamana göre itki ve yanma odası basıncı grafiği eklendi.
- Impingement enjektöründeki çökme düzeltildi.
- Enjektör devre modeli boyutlandıramadığında üretilen uydurma delik planı
  kaldırıldı.
- Ekranda gösterilen enjektör ile CAD'de çizilen enjektör birleştirildi.
- Yanma analizi grafiği seçilen oksitleyiciyi izliyor.
- Isı transferi analizi motorun kendi boğaz çapını, karakteristik hızını ve
  gaz özelliklerini kullanıyor.
- Kuru kütle geometri ve malzemeden hesaplanıyor.
- İrtifa performansı genişleme oranını izliyor.
- Yanma odası hacmi ve kamara boyu kaynağı etiketleri düzeltildi.

## Analiz güvertesi

- Dokuz panelde uzunluk birimi dönüşümü düzeltildi.
- Panellerin okuyamadığı alanlar bağlandı.

## Dışa aktarım ve arayüz

- Excel dışa aktarımında eksik olan motor adı ve itki katsayısı düzeltildi.
- Çözücü sonucunun gösterim katmanında değiştirilmesi engellendi.
- Ana sayfadaki hiçbir şey bildirmeyen durum göstergesi yerine sürüm bilgisi
  konuldu.

## Paketleme ve güncelleme

- macOS kod imzası onarıldı; imzasız paket artık derlenemiyor ve
  yayınlanamıyor.
- Sürüm notlarının kırpılan Türkçe bölümü tam olarak iletiliyor.

## Güvenlik

- Hata yanıtlarındaki traceback ve istek gövdesi kaldırıldı.
- Sayısal olmayan girdi artık doğrulayıcıyı çökertmiyor.

## Pakete girenler

- Üç örnek proje (hibrit, katı, sıvı).
- Kapatılan her kusuru, geri dönüşünü engelleyen bekçi teste bağlayan bulgu
  kayıt defteri.
