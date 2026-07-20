# HRMA v2.5.2

Bu sürüm iki işten oluşuyor: kullanıcı testinden gelen arayüz ve fizik
düzeltmeleri, ve onların peşinden açılan kapsamlı bir **uydurma veri
denetimi**. İkincisi sürümün asıl gövdesi.

## Neden bu sürüm farklı

Teknik çizim çıktısında, sabit tasarım itkisine yapay bir düşüş eklenip
"hesaplanmış itki eğrisi" diye çizildiği fark edildi. Aynı sınıftan başka
kaç vaka olduğu bilinmediği için kod tabanının tamamı tarandı.

Ölçüt tekti: *kullanıcı bu sayının kendi girdisinden hesaplandığına inanır
mı? İnanıyorsa gerçekten hesaplanıyor mu?*

Sonuç: 65 bulgu (12 kritik, 39 major, 14 minor). Hepsi giderildi. **Hiçbir
panel, grafik veya çıktı kaldırılmadı**; her biri gerçek hesapla beslendi,
hesap mümkün olmayan yerler kullanıcının gördüğü noktada etiketlendi.

## Kritik düzeltmeler

**Sıvı motor girdileri artık gerçekten kullanılıyor.** Formdaki alanların
hiçbiri çözücüye ulaşmıyordu; motor yalnız yedi parametre alıyordu. 33 alan
bağlandı ve her biri duyarlılık ölçümüyle doğrulandı. Genişleme oranı
50→12: vakum Isp 352.6→334.2 s. Yanma verimi %97→80: deniz seviyesi Isp
311→249 s. Enjektör elemanı 100→400: orifis çapı 2.33→0.27 mm. Emniyet
katsayısı 2.5→6.0: izin verilen gerilme 383→160 MPa. Bağlanamayan 35 alan
`unwired_inputs` ile açıkça beyan ediliyor.

**Rejeneratif soğutma tasarımı hesaplanıyor.** 10 kN ve 250 kN motorlar
birebir aynı kartı gösteriyordu (180 kanal, 15 m/s, 50 MW/m², 8 bar). Artık
Bartz ve kanal hidroliğinden geliyor: 10 kN → 19 kanal, 0.99 bar; 250 kN →
68 kanal, 113.6 bar (ve "soğutucu basınç düşümü oda basıncının %57'si"
uyarısı).

**Nozul Mach alanı düzeltildi.** Iraksayan bir Newton iterasyonu ve keyfi
geometri kullanılıyordu; yakınsak bölge süpersonik dalda çözülüyordu.
Quasi-1D çözücüye bağlandı: giriş 0.274, boğaz tam 1.000, çıkış 3.604,
analitik izentropik çözümle birebir. Eski değerler 2000 kat sapıyordu.

**Cidar ısı akısı alanı gerçek Bartz profilinden.** Sabit taban ve keyfi
şekil fonksiyonları kaldırıldı. Oda basıncı 20/40/80 bar → tepe akı
20.8/36.2/63.1 MW/m², Bartz'ın basınç üssüyle uyumlu.

**Yanma verimi göstergesi hesaplanıyor.** Her koşuda tam %95 gösteriyordu
(anahtar hiç üretilmiyordu, varsayılana düşüyordu). Artık c* ve kinetik
verimden: O/F 3/6/9 → %99.34/98.23/97.35.

**Katı motor emniyet basınçları hesaplanıyor.** Tasarım/patlama/tahliye
değerleri sabitti; iki farklı motor aynı sayıları veriyordu. Artık basınçlı
kap analizinden: küçük motor 120/341/102 bar, büyük motor 270/746/230 bar.
Kritik: 200 bar çalışan motorda patlama basıncı 150 bar (işletme basıncının
altında) gösteriliyordu, şimdi 1897 bar.

**OpenRocket `.eng` dosyası dürüst.** Gerçek eğri yokken uydurma yükselme
rampası, %15 düşüş ve sönme ekleniyordu. Artık gerçek transient varsa o
taşınıyor, yoksa sabit itki yazılıp dosyaya "constant-thrust approximation"
notu düşülüyor.

**CAD kütlesi yapısal analizle tutarlı.** Sabit 5 mm cidar varsayılıyordu.
20 kN motorda kamara kütlesi 92.6→605 kg (yapısal modülle ondalık hanesine
kadar aynı), itki-ağırlık oranı 21→3.25.

**Kriyojenik itici özellikleri.** LOX, LH2 ve metan oda sıcaklığında
sorgulanıyordu, yani gaz yoğunluğu dönüyordu. Depolama durumuna bağlandı:
LOX 1141.2, LH2 70.9, metan 422.4 kg/m³ (literatürle %0.5 içinde). Kullanıcı
bilerek başka bir sıcaklık verirse fazı açıkça bildiriliyor.

**Yakıt doğrulama ucu.** Karışım özellikleri uydurma formüllerden
üretiliyordu (`900 + karbon sayısı × 50`) ve "NASA CEA Database" diye
etiketleniyordu. Oluşum entalpisi formülden türetilemez; artık boş dönüyor
ve nedeni yazıyor. Molekül ağırlığı (gerçekten türetilebilir) hesaplanmaya
devam ediyor. Kaynak atfı bileşen bazında dürüst.

**Termal analiz.** Cidar dış sıcaklığı bazı koşullarda negatif çıkıyordu
(−3115 K). İletim düşümü artık denge-tutarlı akıdan. Termal gerilme seçilen
malzemenin özelliklerinden ve klasik cidar-gradyan formundan; emniyet durumu
sıcaklık marjını da yansıtıyor.

## Kullanıcı testinden gelen düzeltmeler

Regresyon hızı ve port büyümesi grafiği boş kalıyordu (gömülü Plotly sürümü
ikili veri formatını çözemiyordu). Enjektör tipi kesit çizimine iletilmiyordu.
Kesit lejantındaki renkler grafikle uyuşmuyordu. L\* geometriyi
değiştirmiyordu (artık değiştiriyor ve gerçekleşen L\* raporlanıyor).
Teknik rapor PDF'inde görseller üretilemiyordu (3200×2000 piksel, baskı için
aydınlık zemine çevrilerek gömülüyor). Export paneli taşıyordu ve analiz
`.json` iniyordu (Excel, CSV ve PDF geldi). Optimum O/F propellant
seçilmeden hesaplanıyordu.

## Yeni yetenekler

- **Tam çift dilli arayüz.** 3395 çeviri anahtarı (EN/TR birebir eşit).
  Grafik metinleri dahil: eksen başlıkları, seri adları ve hover metinleri
  de çevriliyor.
- **Katı yakıt propellant kataloğu.** 12 kayıt, 23 takma ad. Seçince
  özellikler doluyor; elle değiştirdiğin alan işaretlenip korunuyor.
- **Malzeme kütüphanesi 11 → 24 kayıt**, tam şema doğrulamasıyla.
- **Uçuş dinamiği bileşen tablosu**: kütle ve konum girişi, canlı ağırlık
  merkezi, basınç merkezi ve statik marj, roket şeması.
- **Motor tipleri arası parite**: performans panosu, veritabanı rozetleri,
  DXF/STEP/ZIP/Excel çıktıları ve uyarı panelleri üç sayfada da.

## Kalıcı bekçi

`tests/test_no_fabrication.py`: sonuç yolunda tohumsuz rastgelelik yasak;
ana girdiler çıktıyı değiştirmek zorunda; bugün düzeltilen her uydurma
kilitli. Toplam test sayısı 1311 → 2169.

## Bilinen sınırlar

Sıvı motorda başlatma ve durdurma geçici rejimi modellenmiyor (ilgili
alanlar arayüzde bu şekilde işaretli). Bazı imalat toleransları ve yüzey
pürüzlülükleri tasarım kararı olmadığı için standart değerlerle, kaynağı
yazılı olarak veriliyor. Işıyan yüzey alanı uzunluk verilmediğinde L/D = 5
varsayımıyla hesaplanıyor ve bu çıktıda belirtiliyor.
