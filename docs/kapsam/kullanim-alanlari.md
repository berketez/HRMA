# Kullanım Alanları — Kim, Ne İçin, Ne İçin Değil

**Son güncelleme: 2026-08-14**
**Kapsam:** HRMA'nın hangi kullanıcı ve hangi amaç için tasarlandığı;
hangi amaç için tasarlanmadığı. Yasaklar ve sorumluluk için
[yasaklar-ve-sorumluluk.md](yasaklar-ve-sorumluluk.md), teknik sınırlar
için [gecerlilik-zarfi.md](gecerlilik-zarfi.md).

**Ölçüm tabanı:** `2e2375d`.

---

## 1. Yazılımın kendi beyanı

Kök `README.md` ve `docs/VALIDATION_STATUS.md`, HRMA'yı tek bir cümlede
konumlandırır: **ön tasarım ve eğitim aracı, uçuş kalifikasyon aracı
değil.** Bu belge o cümlenin ayrıntısıdır.

---

## 2. Kimler kullanır

### Öğrenci ve amatör roket takımları

Tipik iş: bir hedef itki/toplam impuls için motor ailesi seçmek, boğaz ve
lüle geometrisini çıkarmak, yakıt kütlesini ve yanma süresini
boyutlandırmak, hazne cidar kalınlığını ilk mertebeden belirlemek, itki
eğrisini `.eng` olarak alıp uçuş simülasyonuna taşımak.

HRMA'nın bu iş için verdiği: üç motor ailesinde tam çözüm, gerçek çözücü
geometrisinden üretilen STL/STEP/DXF ve ölçülendirilmiş teknik resim,
OpenRocket `.eng` çıktısı (gerçek hesaplanan itki eğrisiyle), Monte Carlo
belirsizlik bantları.

HRMA'nın bu iş için **vermediği**: imalat toleransı, malzeme kabulü,
ateşleme geçici rejimi, test güvenliği planı. Bunlar takımın kendi
sorumluluğundadır.

### Ders, ödev ve öğretim

Formül sayfası (`/formulas`), her sayının künyesini taşıyan çıktı yapısı
ve `docs/STANDART_ATIFLARI.md` kayıt defteri, bir hesabın hangi bağıntıdan
geldiğini izlenebilir kılar. `NOT_MODELLED` disiplini öğretici bir
tarafa da sahiptir: öğrenci, bir modelin nerede bittiğini görür.

### Ön tasarım ve ticaret çalışması (trade study)

Parametre taraması, karşılaştırmalı analiz paneli, belirsizlik nicelemesi
(P50 ve [P5, P95]) ve Spearman duyarlılık tornado grafiği, "hangi girdi
sonucu sürüyor" sorusuna sayısal cevap verir. Tasarım uzayını daraltmak
için uygundur.

### Bağımsız bir hesabın çapraz kontrolü

Elde CEA, RPA veya openMotor çıktısı varsa HRMA ikinci bir görüş olarak
kullanılabilir. Ters yön de geçerlidir ve **tavsiye edilir**: HRMA
sonucunu bağımsız bir kodla karşılaştırın.

### Yayımlanmış deney verisiyle karşılaştırma

`hrma/data/validation_records/` altındaki künyeli kayıtlar ve
`/api/correlation-report` uç noktası, modelin gerçek ateşleme verisine
göre nerede durduğunu ölçer. Sonuçlar
[`docs/VALIDATION_STATUS.md`](../VALIDATION_STATUS.md) içindeki makine
üretimi blokta yayımlanır.

---

## 3. Hangi amaçla kullanılır

| Amaç | HRMA'nın rolü |
|---|---|
| Motor ailesi ve çalışma noktası seçimi | Birincil araç |
| Ön geometri (boğaz, lüle, tane, enjektör) | Birincil araç |
| Duyarlılık ve belirsizlik taraması | Birincil araç |
| Test öncesi tasarım uzayını daraltma | Birincil araç |
| Eğitim ve öğretim | Birincil araç |
| İmalat resmi taslağı üretme | Yardımcı — resim gözden geçirilmeden imalata verilmez |
| Uçuş simülasyonuna itki eğrisi sağlama | Yardımcı — `.eng` çıktısı |
| Yapısal ve termal ilk mertebe kontrol | Yardımcı — bağımsız kontrol şart |

---

## 4. Hangi amaçla KULLANILMAZ

### Uçuş sertifikasyonu ve kalifikasyon

HRMA hiçbir kalifikasyon süreci yürütmez. Yazılımın kendi denetçisi
(`tools/iddia_lint.py`) "flight-certified" ve "certified for flight"
ifadelerini yasaklı kalıp olarak tarar; gerekçe kayıtlıdır:
"kalifikasyon süreci yok". Bir motorun uçuşa uygunluğu, tanımlı bir
kalifikasyon programı, kabul testleri ve yetkili bir otoritenin kararıyla
belirlenir.

### Nihai tasarım doğrulaması

Yazılım, tasarımın son halini onaylamaz. `docs/VALIDATION_STATUS.md`
bilinen sınırlar bölümünün ilk maddesi açıktır: yanma kararsızlığı,
ateşleme geçicileri, sert başlangıç ve gerçek teslim edilen c\* verimi
yalnız **fiziksel yer ateşlemesiyle** belirlenebilir. HRMA testten önce
tasarımı daraltır; testin yerine geçmez.

### İnsanlı sistemler

Hiçbir insanlı sistem gereksinimi (tasarım güvence düzeyi, bağımsız
doğrulama ve geçerleme, yedeklilik analizi, arıza ağacı) bu yazılımın
kapsamında değildir.

### Mevzuat uygunluğu, izin veya sigorta değerlendirmesi

NFPA, OSHA, DOT, yerel mevzuat ve sigorta gereksinimleri alanları
`NOT_EVALUATED` döner (`hrma/analysis/safety_analysis.py:1201-1205`).
Yazılımın çıktısı bir izin başvurusunda uygunluk kanıtı olarak
kullanılamaz.

### Emniyet mesafesi, tehlike alanı ve tahliye planı

HRMA emniyet mesafesi hesaplamaz. `safety_limits.py` yalnız model girdisi
akıl sağlığı sınırlarına bakar ve modülün kendi ifadesiyle bir güvenlik
kapısı değildir.

### İmalata doğrudan gönderilecek nihai üretim paketi

CAD ve resim çıktıları gerçek çözücü geometrisinden üretilir, ancak
tolerans ve yüzey gereksinimleri sizin detay resminizin işidir (bkz.
`hrma/engines/solid_rocket_engine.py:5423-5429` ve `:5528-5534`).

### Gerçek zamanlı denetim veya uçuş yazılımı

HRMA çevrimdışı bir masaüstü analiz uygulamasıdır; uçuş donanımına
gömülmez, gerçek zamanlı döngüde koşmaz.

### Silah veya patlayıcı sistem geliştirme

Bkz. [yasaklar-ve-sorumluluk.md](yasaklar-ve-sorumluluk.md).

---

## 5. Önerilen iş akışı

```
1. HRMA'da ön tasarım
      ↓
2. Belirsizlik taraması (/api/uncertainty-analysis) — sonucun bandını gör
      ↓
3. Bağımsız çapraz kontrol: NASA CEA (RocketCEA), openMotor (katı),
   RPA Lite (sıvı), Nakka SRM (şeker), CPropep / Combustion Toolbox
      ↓
4. İki kod arasındaki farkı AÇIKLA — kapatamadığın fark bir bulgudur
      ↓
5. Hidrostatik kanıt testi (hazne ve tank)
      ↓
6. Ölçümlü yer ateşlemesi (basınç, itki, mümkünse cidar sıcaklığı)
      ↓
7. Ölçümü modelle karşılaştır; sapmayı kayıt altına al
      ↓
8. Ancak bundan sonra uçuş kararı — ve o karar yazılımın değil, sizin
```

Adım 3 ve 5 atlanamaz. `docs/VALIDATION_STATUS.md` bunları "ateşleme
öncesi her hâlde gerekir" başlığı altında sayar.

---

## 6. Kullanıcıdan beklenen yetkinlik

HRMA uzman yerine geçmez; uzmanın hesap yükünü azaltır. Kullanıcının
şunları yapabilmesi beklenir:

- Bir çıktının `status` ve `_basis` alanlarını okuyup sayının nereden
  geldiğini anlamak.
- Bir modelin geçerlilik zarfının dışına çıktığını fark etmek ve o sayıyı
  kullanmamak.
- Bağımsız bir kodla karşılaştırma yapmak ve farkı yorumlamak.
- Kendi motorunun imalat, test ve güvenlik sorumluluğunu üstlenmek.

Bu yetkinliklere sahip olmayan bir kullanıcı HRMA'yı **öğrenmek** için
kullanabilir; bir motoru **ateşlemek** için tek başına kullanmamalıdır.
