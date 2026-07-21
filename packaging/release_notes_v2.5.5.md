# HRMA v2.5.5

Büyük özellik sürümü. Dört ana başlık: tek tıkla tam otomatik güncelleme,
proje kaydet/yükle, dış formatlardan içe aktarma (OpenRocket / RASP /
RockSim / STEP-CAD) ve kapsamlı görselleştirme-performans iyileştirmeleri.

## Tam otomatik güncelleme

Önceki davranış: "Şimdi güncelle" düğmesi kurulum dosyasını indirip
işletim sistemine açtırıyor, kurulumun geri kalanı (uygulamayı kapatmak,
macOS'ta sürükle-bırak ve "değiştirilsin mi?" onayı, Windows'ta sihirbaz
adımları) kullanıcıya kalıyordu.

Yeni davranış: "Şimdi güncelle" düğmesine basıldıktan sonra hiçbir şey
sormadan indirme yapılır, uygulama kendini kapatır, yeni sürüm sessizce
kurulur ve HRMA kendiliğinden yeniden açılır.

Güvenlik ve sağlamlık katmanları:
- İndirilen dosya, boyut ve (GitHub API sağladığında) SHA-256 özetiyle
  doğrulanır; eksik ya da bozuk indirmeyle kurulum denenmez.
- macOS'ta eski uygulama, yeni sürümün gerçekten AÇILDIĞI doğrulanana
  kadar silinmez; yeni sürüm açılmazsa eski sürüm otomatik geri yüklenir.
- Kaynak koddan çalışma, DMG içinden çalıştırma (App Translocation),
  yazılamayan hedef ve yetersiz disk alanı durumlarında otomatik kurulum
  denenmez; eski davranışa (kurulum dosyasını açma) dönülür.
- Windows'ta sessiz kurulum NSIS /S ile MEVCUT kurulum dizinine yapılır;
  kurulum sırasında küçük bir durum penceresi gösterilir.
- Her adım Belgeler/HRMA/hrma_update_log.txt dosyasına yazılır; herhangi
  bir hata durumunda kurulum dosyası elle kurulmak üzere açılır.

Not: Bu mekanizma v2.5.5 ile geldiği için ilk sessiz güncelleme deneyimi
v2.5.5'ten SONRAKİ sürüme geçişte yaşanır; v2.5.4'ten v2.5.5'e geçiş son
kez eski akışla yapılır.

## Proje kaydet / yükle

Üç tasarım sayfasının (hibrit, katı, sıvı) üstünde proje şeridi: Save /
Save As / Open / New. Tasarımlar .hrma dosyaları olarak
Belgeler/HRMA/projects altında saklanır; ana sayfada son projeler
listelenir. Kaydedilen içerik: tüm form girdileri, sekme durumu, elle
değiştirilen analiz güvertesi alanları ve küçük bir sonuç özeti.
Kaydedilmemiş değişiklik uyarısı ve bozuk dosya toleransı vardır; silme
kalıcı değildir (çöp klasörüne taşınır).

## Dış formatlardan içe aktarma

Tasarım akışının tersi: hazır bir motor/roket verisini HRMA'ya alıp
sayısal sonuçlara dönüştürme.

- **.eng (RASP) / .rse (RockSim) itki eğrileri:** Doğrulama paneli bu
  dosyaları kabul eder; HRMA'nın tahmini ile içe aktarılan gerçek/katalog
  eğrisi üst üste çizilir, fark metrikleri (toplam impuls, pik/ortalama
  itki, yanma süresi, RMSE, not) raporlanır. 6-DOF uçuş simülasyonunda
  içe aktarılan motor, itki kaynağı olarak seçilebilir.
- **.ork (OpenRocket):** Gövde/burun/kanat geometrisi ve kütle tablosu
  6-DOF girdilerine otomatik eşlenir; hesaplanan kütleler "tahmin"
  etiketiyle gelir ve düzenlenebilir. Dosyada OpenRocket'ın kayıtlı
  simülasyon sonuçları varsa HRMA sonuçlarıyla yan yana karşılaştırma
  kartı gösterilir. Eşlenen/yaklaşıklanan/atlanan her öge raporlanır.
- **STEP (CAD):** "Import from CAD" akışı dosyayı analiz eder, motor
  eksenini ve silindir/koni yüzeylerini bulur, kesit çizimi üzerinde
  boğaz/çıkış/oda/cidar ölçü ADAYLARINI önerir; kullanıcı her ölçüyü
  onaylayıp forma uygular, malzeme ve yakıt seçimini yapıp normal analizi
  çalıştırır. Bulunamayan hiçbir ölçü sessizce doldurulmaz.

## Görselleştirme ve simülasyon iyileştirmeleri

- 3D motor sahnesine ortam haritası ve ACES ton eşleme eklendi — metal
  yüzeyler gerçekçi parlıyor. Egzoz plume'u artık lüle çıkış açısı ve
  genişleme oranıyla ölçekleniyor (bell dar, konik geniş; şok elmasları
  tasarım noktasına göre sönümleniyor).
- Yanma animasyonu performansı: grain geometrisi artık her karede değil
  anlamlı yarıçap değişimlerinde yeniden kuruluyor; görünmeyen sekmede
  render durur; kare süresi uzayınca kalite otomatik düşer. PNG anlık
  görüntü (Frame) düğmesi eklendi.
- 6-DOF paneline Mach ile renklendirilmiş 3D uçuş yörüngesi grafiği
  (zemin izdüşümü ve apoje işaretiyle) eklendi.
- Grafik açıklama katmanı: 24 ana grafiğin altında "ne gösterir, nasıl
  okunur" satırı (iki dilli). Grafiklerde soru işareti kalmasın diye.
- PNG dışa aktarım düzeltildi: saydam zemin yerine koyu tema zemini,
  ekran boyutunun 2 katı çözünürlük (700x500 sabit boyut kaldırıldı).
- Gösterge (gauge) renkleri koyu temada kaybolmuyor; regresyon
  grafiğindeki beyaz özet kutusu koyu temaya alındı; parametrik analiz
  grafiği dar pencerede taşmıyor, birimli hover bilgisi veriyor.
- Aynı zaman eksenini paylaşan panellerde senkron yakınlaştırma
  (birinde zoom hepsine uygulanır).
- Boş grafik hatasının kökü olan to_json/bdata uyumsuzluğu tek merkezden
  kapatıldı ve bekçi testiyle korunuyor.

## Performans

- Isp yüzey taraması ve O/F süpürmeleri istekler arası önbelleklendi
  (aynı girdiyle tekrar hesap yok).
- Katı motor grain geometrisi (star/wagon/finocyl poligonları, kasa
  diskleri) modül önbelleklerine alındı.
- Yanma denge çözümü ve optimum O/F araması için tekrar hesap önbelleği.
- Panel JS katmanında gereksiz tam yeniden çizimler azaltıldı.
- Sayısal sonuçlar bit-aynı korunmuştur; yalnız tekrar hesaplar önlenir.

## Arayüz düzeltmeleri

- Sayfa sonunda esneyerek kaydırmada (macOS lastik bant / Windows
  overscroll) görünen bembeyaz alan koyu tema zeminiyle kapatıldı;
  pencere açılışındaki beyaz parlama giderildi.
Sürüm 2511 otomatik testle doğrulanmıştır (v2.5.4: 2182). Yeni testler:
otomatik güncelleme (45), import ayrıştırıcıları ve uçları (97), proje
deposu (98), arayüz sözleşmeleri (29) ve grafik katmanı bekçileri.
