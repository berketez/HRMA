# Yasaklar, Güvenlik Uyarıları ve Sorumluluk

**Son güncelleme: 2026-08-14**
**Kapsam:** Kullanım yasakları, güvenlik uyarıları, lisans koşulları ve
sorumluluk reddi. Teknik sınırlar için [ne-yapmaz.md](ne-yapmaz.md),
kullanım senaryoları için [kullanim-alanlari.md](kullanim-alanlari.md).

**Ölçüm tabanı:** `2e2375d`.

---

## 1. Lisans — ölçülmüş durum

`LICENSE` dosyası **MIT Lisansı**dır. Telif: *Copyright (c) 2026 Berke
Tezgöçen*.

MIT'in bu belge açısından iki kritik hükmü:

> **"THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND"** —
> yazılım olduğu gibi, hiçbir garanti verilmeksizin sağlanır. Ticari
> elverişlilik, belirli bir amaca uygunluk ve ihlal etmeme garantileri
> dahil **hiçbir garanti yoktur**.

> **"IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE"** —
> yazarlar ve telif hakkı sahipleri, yazılımın kullanımından doğan hiçbir
> talep, zarar veya sorumluluktan **sorumlu tutulamaz**.

Yani: yazılımı kullanmak, kopyalamak, değiştirmek ve dağıtmak serbesttir;
**sonuçlarının sorumluluğu tamamen kullanıcıya aittir**. Bu bir hukuk
metni özetidir, hukuki tavsiye değildir; bağlayıcı metin `LICENSE`
dosyasının kendisidir.

### Atıf

Akademik kullanımda `CITATION.cff` dosyasındaki künye kullanılır. Künye
metninin kendisi de kapsamı tekrar eder: *"HRMA is not a
flight-qualification tool; see docs/VALIDATION_STATUS.md … before citing
any number produced by it."*

---

## 2. Kullanım yasakları

Aşağıdakiler yazılımın **amaçlanan kullanımı dışındadır**. Bu bir teknik
kısıt değil, bir kapsam beyanıdır: yazılım bunları yapabilecek bilgiyi
üretmez ve bu amaçla kullanılması hem yanlış hem tehlikelidir.

### 2.1 Sertifikasyon, uygunluk veya kabul kanıtı olarak kullanmak

HRMA çıktısı hiçbir sertifikasyon, ruhsat, izin, sigorta veya kabul
sürecinde uygunluk kanıtı olarak sunulamaz. Yazılım uygunluk
değerlendirmesi yapmaz ve yapmadığını açıkça beyan eder: NFPA, OSHA,
DOT, yerel mevzuat ve sigorta alanları `NOT_EVALUATED` döner
(`hrma/analysis/safety_analysis.py:1201-1205`).

### 2.2 Emniyet kararı vermek için kullanmak

Yazılım işletme emniyeti hükmü veremez. `safety_limits.py` modülü kendi
docstring'inde bir güvenlik kapısı olmadığını söyler; rapor metnindeki
"MOTOR SAFE FOR OPERATION" ifadesi kaldırılmıştır
(`hrma/analysis/safety_limits.py:98-113`). Bir motoru ateşleme kararı,
yazılımın değil, ölçümlü testin ve sorumlu kişinin kararıdır.

### 2.3 Fiziksel test yerine kullanmak

`docs/VALIDATION_STATUS.md` bilinen sınırlar bölümünün ilk maddesi:
yanma kararsızlığı, ateşleme geçicileri, sert başlangıç ve gerçek teslim
edilen c\* verimi **yalnız fiziksel yer ateşlemesiyle** belirlenebilir.
HRMA testi daraltır, testin yerine geçmez.

### 2.4 İnsanlı sistemlerde kullanmak

İnsan taşıyan hiçbir sistemin tasarımında, doğrulamasında veya işletiminde
kullanılmaz.

### 2.5 Silah veya patlayıcı cihaz geliştirmek

Yazılım itki analizi için yazılmıştır. Silah, mühimmat veya patlayıcı
cihaz geliştirme amacıyla kullanılması amaçlanan kullanım dışındadır ve
bulunduğunuz ülkenin ihracat kontrolü ve ceza mevzuatına tabi olabilir.
Bu mevzuata uymak kullanıcının sorumluluğudur.

### 2.6 Zarf dışı sonucu "sayı" gibi kullanmak

`NOT_MODELLED`, `not_analyzed`, `NOT_EVALUATED`, `no_published_data`
veya `model_valid=False` dönen bir alanın yerine kendi tahmininizi koyup
sonucu "HRMA hesabı" diye sunmak yanlıştır. Aynı biçimde,
`outside_validity_band` işaretli bir ölçütü işaretsizmiş gibi
raporlamak da yanlıştır. Ayrıntı:
[gecerlilik-zarfi.md](gecerlilik-zarfi.md).

### 2.7 Doğrulanmamış katsayılarla tasarım yapmak

Hibrit regresyon tablosunda dört katsayı çifti (`pla`, `carbon`,
`aluminum`, `al2o3`) "yayınlanmış, hakemli bir korelasyon bulunamadı …
**tasarım için kullanmayın**" notunu taşır
(`hrma/data/propellant_database.py:48-53`). Bu not bir öneri değil, bir
sınırdır.

### 2.8 Çıktıyı künyesinden koparmak

Bir HRMA sayısını raporunuza taşırken sürümü, `_basis` künyesini ve
varsa `validity_note` uyarısını da taşıyın. `docs/VALIDATION_STATUS.md`
içindeki korelasyon bloğu **elle düzenlenemez**; bir sayıyı oradan
alıntılamadan önce bloğun başındaki üretim künyesi (tarih, koşucu
sürümü, commit) okunmalıdır.

---

## 3. Yazılımın kendine yasakladığı dil

Depo, kazanılmamış hükümleri makinece engeller: `tools/iddia_lint.py`,
`hrma/` ağacını ve kullanıcıya giden belgeleri tarar; kayıtta olmayan bir
isabette çıkış kodu 1 verir. Yasaklı kalıplar ve gerekçeleri
(`tools/iddia_lint.py:131-162`):

| Kalıp | Neden yasak |
|---|---|
| `NASA-grade` | Akreditasyon iddiası: NASA hiçbir HRMA çıktısını derecelendirmedi |
| `NASA-validated` | Bağımsız doğrulama iddiası: depoda NASA doğrulaması yok |
| `NASA standards methodology` | Uygunluk iddiası: hiçbir kod yolu standart uygunluğu denetlemiyor |
| `flight-certified` | Uçuş sertifikasyonu iddiası: kalifikasyon süreci yok |
| `manufacturing-ready` | İmalata hazırlık hükmü: tolerans/malzeme kabulü yapılmıyor |
| `safe for operation` | İşletme emniyeti hükmü: model emniyet kararı veremez |
| `professional-grade` | Derecelendirme iddiası: ölçülebilir karşılığı yok |
| `guaranteed` | Garanti dili: sayısal sonuç için garanti verilemez |
| `high-fidelity` | Sadakat iddiası: yalnız tanımlı bir çözüm kademesinin **adı** olarak meşru, ürün sıfatı olarak değil |
| `digital twin` | Dijital ikiz iddiası: kalibrasyon ve telemetri bağı yok |
| `NFPA/OSHA/DOT/ASME/ISO/AIAA-compliant` | Yönetmelik uygunluğu hükmü: uygunluk denetimi koşmuyor |
| `acceptable for preliminary design` | Tasarım aşaması kabul hükmü: dayanağı olan bir eşik yok |

Bu tablo yalnız iç disiplin değildir; **kullanıcı için de ölçüttür.**
HRMA çıktısını aktarırken bu ifadeleri kullanmayın — yazılım onları
kendisi için kullanmayı yasaklamıştır.

---

## 4. Güvenlik uyarıları

### 4.1 İtici üretimi, işlenmesi ve depolanması kapsam dışıdır

HRMA **hiçbir** yakıt hazırlama, karıştırma, dökme, presleme, kürleme,
depolama veya taşıma talimatı üretmez ve bu konuda hiçbir çıktısı yoktur.
Katı itici hazırlığı yangın ve patlama riski taşır; oksitleyiciler
(N₂O, LOX, H₂O₂) kendi başlarına ciddi tehlike kaynağıdır. Bu işler
yerel mevzuata, uygun tesise ve deneyimli bir sorumluya ihtiyaç duyar.

### 4.2 Test güvenliği kapsam dışıdır

Test standı tasarımı, ankraj, emniyet mesafesi, siper, uzaktan ateşleme,
tahliye planı, yangın söndürme ve acil durum prosedürleri yazılımın
kapsamı dışındadır. HRMA emniyet mesafesi hesaplamaz.

### 4.3 Basınçlı sistem uyarısı

Hazne ve tanklar basınçlı kaptır. Yazılımın yapısal marjı konservatif
olsa bile **hidrostatik kanıt testinin yerine geçmez**
(`docs/VALIDATION_STATUS.md`, bilinen sınırlar #6). Kanıt testi yapılmamış
bir hazne ateşlenmemelidir.

### 4.4 Küçük motorlarda iyimserlik

Yaklaşık 75 mm altındaki katı motorlarda teslim edilen Isp fazla iyimser
çıkar; iki fazlı akış, ısı kaybı ve kısa L\* ölçek etkileri
modellenmemektedir. Küçük motor tasarımında bu sapma bilinerek çalışılmalıdır.

### 4.5 Yazılım güvenliği

Güvenlik açığı bildirimi için `SECURITY.md` dosyasındaki süreç izlenir
(bildirim adresi, beklenen yanıt süreleri ve açıklama politikası orada
tanımlıdır). Açık bir güvenlik açığı için herkese açık GitHub konusu
açılmaz.

---

## 5. Sorumluluk reddi

HRMA bir **ön tasarım ve eğitim** aracıdır.

1. Yazılımın ürettiği hiçbir sayı, bir motorun güvenli, uygun veya uçuşa
   elverişli olduğunun kanıtı **değildir**.
2. Yazılım MIT lisansı altında, **hiçbir garanti verilmeksizin** ("AS IS")
   sağlanmaktadır; yazar ve telif hakkı sahibi, yazılımın kullanımından
   doğan hiçbir zarardan sorumlu tutulamaz.
3. Tasarım, imalat, test ve işletme kararlarının tamamı **kullanıcının
   sorumluluğundadır**.
4. Yerel mevzuata, izin süreçlerine ve güvenlik kurallarına uymak
   kullanıcının sorumluluğundadır.
5. Herhangi bir motoru ateşlemeden önce bağımsız bir kodla çapraz kontrol
   (CEA / RPA / openMotor), hidrostatik kanıt testi ve ölçümlü yer
   ateşlemesi **gereklidir**.

Bu koşulları kabul etmiyorsanız yazılımı tasarım amacıyla kullanmayın.
