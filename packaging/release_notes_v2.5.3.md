# HRMA v2.5.3

Saha hatası sürümü. v2.5.2 sonrası gerçek kullanıcılardan gelen iki
Windows hatası düzeltildi. Yeni özellik yok; bu sürüm yalnız bu iki hatayı
kapatır.

## PDF Technical / Complete raporları takılmıyor

**Belirti:** PDF Summary çalışıyor; PDF Technical Report ve PDF Complete
Report butonları "Generating PDF..." üzerinde sonsuza kadar kalıyordu.

**Kök neden:** Summary raporu grafik içermez; Technical ve Complete
raporları ise grafikleri sunucuda kaleido (gömülü Chromium) ile PNG'ye
çevirir. Bazı Windows makinelerinde kaleido.exe — antivirüs engeli veya
eksik sistem bileşeni yüzünden — hiç çıktı üretmeden bloke oluyor. plotly
bu durumda süresiz bekler: istek asılı kalır, buton hiç geri gelmez ve her
deneme bir sunucu iş parçacığını kalıcı olarak tüketir.

**Düzeltme:** Grafik render'ı artık merkezi bir katmandan geçiyor
(`hrma/export/chart_render.py`):

- Kaleido çağrısı zaman aşımı korumalı (ilk render 45 sn, sonrakiler
  20 sn). Süre aşılırsa asılı süreç sonlandırılır ve kaleido o oturum
  için devre dışı işaretlenir — sonraki grafikler hiç beklemez.
- Kaleido kullanılamadığında 2B grafikler (itki, basınç, irtifa eğrileri)
  matplotlib emniyet çizicisiyle aynı veriden çizilip PDF'e gömülür.
  Rapor her koşulda üretilir.
- Kesit ve CAD gibi shape-temelli figürler emniyet çizicisiyle anlamlı
  çizilemeyeceğinden uydurma görsel gömülmez; ilgili sayfaya durum notu
  basılır.
- Arayüz tarafında da emniyet var: PDF isteği 3 dakikada yanıt almazsa
  iptal edilir ve buton hata mesajıyla geri açılır. Buton hiçbir koşulda
  takılı kalmaz.

Aynı koruma teknik çizim PDF'i ve ZIP paketindeki çizimler için de
geçerli (projedeki dört kaleido çağrısının tamamı bu katmandan geçiyor).

## Kurulum hatası: "Error opening file for writing"

**Belirti:** Güncelleme kurulumunda
`C:\Users\...\AppData\Local\HRMA\python\_decimal.pyd` için "Error opening
file for writing" hatası.

**Kök neden:** Uygulama içi güncelleyici, indirilen Setup'ı HRMA hâlâ
açıkken başlatıyor. Çalışan uygulamanın dosyaları kilitli olduğundan
kurulum üzerine yazamıyordu; kurulum sihirbazındaki "önce kapatın" notu
bunu engellemiyordu.

**Düzeltme:** Setup artık kuruluma başlamadan önce kurulum dizininden
çalışan tüm HRMA süreçlerini tespit ediyor. Bulursa kullanıcıya soruyor
("OK ile HRMA otomatik kapatılır") ve onaydan sonra süreçleri kapatıp
kuruluma devam ediyor. Aynı koruma kaldırıcıda da var. Eski sürümden
güncellerken bu iletişim kutusu bir kez görünür; v2.5.3 sonrası
güncellemeler kesintisiz akar.

## Test

İki düzeltme, yayın öncesi üç ajanlı bağımsız incelemeden geçirildi;
bulunan bir kritik (kurulumdaki süreç tespiti 64-bit Windows'ta sessiz
kalırdı — bitness'ten bağımsız yönteme geçildi) ve bir major (eşzamanlı
iki PDF isteğinde sağlıklı render'ın yanlışlıkla devre dışı
işaretlenebilmesi — render'lar serileştirildi) bulgu da bu sürümde
kapatıldı.

Toplam test 2169 → 2182. Yeni bekçiler: asılan kaleido simülasyonunda
raporun yine de üretildiği ve grafiğin gerçekten gömüldüğü, emniyet
çizicisinin gerçek PNG çizdiği, shape-temelli figürlerin nota düştüğü,
eşzamanlı isteklerin render'ı yanlışlıkla devre dışı bırakmadığı ve
teknik çizim yolunun asla kilitlenmediği doğrulanıyor
(`tests/test_chart_render.py`).
