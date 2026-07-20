# HRMA v2.5.4

Saha hatası ve görsel iyileştirme sürümü. v2.5.3 sonrası gerçek
kullanıcılardan gelen üç hata düzeltildi; ayrıca arayüzün uzay teması
zenginleştirildi ve depo kök dizini toparlandı.

## Gösterge panellerinde üst üste binen başlıklar

**Belirti:** Combustion Analysis panosunda "eta_c* x eta_kinetic (%)" ile
"Combustion / Kinetic Efficiency" başlıkları; Real-Time Motor Performance
panosunda da pano başlığı, hücre başlığı ve gösterge başlığı birbirinin
üstüne basılıp okunmaz hâle geliyordu.

**Kök neden:** make_subplots hücre başlığı (subplot_titles) ile Plotly
Indicator'ın kendi başlığı aynı noktaya çizilir. İki panoda da her iki
başlık birden verilmişti.

**Düzeltme:** Gösterge hücrelerinde tek başlık kaldı (hücre başlığı);
birim bilgisi sayının sonekine taşındı (1000 N, 20 bar, 0.554 kg/s...).
Pano başlığı üst marja sabitlendi. Projede aynı deseni kullanan enjektör
göstergesi zaten böyle çalışıyordu — davranış birleştirildi.

## Real-Time panosunda boş kalan ikinci sıra

**Belirti:** Real-Time Motor Performance panosunda Temperature, O/F Ratio
ve Isp hücrelerinde yalnız başlık görünüyor, gösterge hiç çizilmiyordu.

**Kök neden:** İkinci sıranın hücre başlıkları tanımlanmış ama gösterge
izleri hiç eklenmemişti.

**Düzeltme:** Üç gösterge, çözücünün gerçek sonuç anahtarlarından
(chamber_temperature, of_ratio, isp) beslenerek eklendi. Sıfır/eksik
değerde eksen aralığı artık çökmez (0'a bölünme benzeri [0, 0] aralığı
korumaya alındı).

## Excel dışa aktarma: "openpyxl is not installed"

**Belirti:** Kurulum paketlerinde Excel çalışma kitabı indirme "export
failed: openpyxl is not installed; falling back to CSV is recommended."
hatası veriyordu; ayrıca hata bildirimi bir önceki bildirimin üstüne
binip okunmuyordu.

**Kök neden:** openpyxl, kaynak kurulumun requirements.txt dosyasında
vardı ama kurulum paketi bağımlılık listesinde
(packaging/requirements_bundle.txt) unutulmuştu. Bildirim çakışması ise
solid/liquid sayfalarındaki bildirimlerin hepsinin aynı sabit noktaya
çizilmesindendi.

**Düzeltme:**

- openpyxl kurulum paketine eklendi (mac + win); derleme betiğine ve
  paket duman testine openpyxl varlık kontrolü kondu — bir daha sessizce
  düşemez.
- Solid ve liquid sayfalarındaki Excel dışa aktarma, sunucu Excel
  üretemezse artık kullanıcıyı ham hatayla bırakmıyor: aynı veriler
  otomatik CSV olarak iniyor (advanced sayfasındaki davranışla parite).
- Bildirimler artık dikey istife basılıyor; iki mesaj üst üste binmiyor.

## Arayüz: daha dolu bir uzay arka planı

- Tüm koyu sayfaların arka planına ince bir yıldız alanı eklendi (saf
  CSS, beş katmanlı döşeme; içerik panellerinin daima altında kalır).
- Ana sayfa hero bölümündeki yıldız sayısı artırıldı; ayrı fazda
  parıldayan ikinci bir yıldız takımı ve soluk bir nebula katmanı eklendi.

## Depo kök dizini temizliği

Kökteki gevşek dokümanlar docs/ altına taşındı (HRMA_Paper, RELEASE,
SPACE_CAPABILITY, VALIDATION_STATUS, USER_MANUAL, validation_results.png);
ikonlar packaging/ altına alındı. Tüm bağlantılar ve otomatik
VALIDATION_STATUS güncelleyicisinin yazma yolu buna göre düzeltildi.

## Test

Toplam test: 2182 (tamamı geçiyor). Değişiklikler yayın öncesi üç ajanlı
bağımsız incelemeden geçirildi; incelemenin render kanıtıyla yakaladığı
bir major bulgu (gösterge tepe tick etiketinin hücre başlığıyla veri
bağımlı çakışması — göstergeler hücre içinde aşağı sıkıştırılarak
çözüldü) ve iki minör bulgu (ana sayfa nebula katman sırası, taşınan
kılavuzun eski yol referansı) bu sürümde kapatıldı.
