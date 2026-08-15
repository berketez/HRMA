# F3 dış test verisi — istek listesi (statik ateşleme)

**Amaç:** 2.7 kapı ölçütü #3 — en az bir dış kullanıcının gerçek test verisiyle
kapanmış korelasyon döngüsü (öngörü → ateşleme → ölçüm → korelasyon).
**İlk aday:** Ayberk'in takımının toplu/statik testi. Liste motor tipinden
bağımsızdır; her dış kullanıcıya aynı liste gönderilir.
**Şema bağı:** Bu liste `hrma/data/validation_records/SCHEMA.md` (schema_version
1.0, `record_type: static_fire`) alanlarına birebir eşlenir; veri geldiğinde
kayıt `experiment_db.ensure_valid_record`'dan geçmeden korelasyona giremez.

## 1. Olmazsa olmazlar (bunlarsız döngü kapanmaz)

| # | İstenen | Biçim | Şema karşılığı |
|---|---|---|---|
| 1 | **İtki-zaman eğrisi** (yük hücresi, HAM) | CSV: `t [s], F [N veya kgf]` — grafik fotoğrafı DEĞİL, ham örnekleme (Hz'i de yazın) | `measured.thrust_*` eğrisi (`{time_s, value}`) |
| 2 | **Yakıt/oksitleyici kütleleri** — yakma ÖNCESİ ve SONRASI tartım | sayı + birim (g/kg) | `measured` (tüketim, O/F, regresyon) |
| 3 | **Motor geometrisi** — boğaz çapı, çıkış çapı; katı/hibritte tane dış/iç çap + boy, port çapı yakma ÖNCESİ ve SONRASI | sayı + birim (mm) | `geometry` (regresyon hızı buradan) |
| 4 | **Yakıt ve oksitleyici kimliği** — tam bileşim (ör. HTPB %85 + Al %15; N2O; KNSB 65/35) + biliniyorsa yoğunluk | metin + sayı | `propellants` |
| 5 | **Ayarlanan işletme değerleri** — hibrit/sıvıda tank basıncı ve/veya hedef debi; katıda yoktur | sayı + birim | `inputs` |
| 6 | **Test künyesi** — tarih, yer/stand, testi yapan takım, test kimliği | metin | `source`, `test_id` |
| 7 | **Ortam koşulları** — ortam sıcaklığı ve basıncı (ya da rakım) | sayı + birim | `inputs` |

## 2. Çok değerli (varsa mutlaka)

| İstenen | Neden |
|---|---|
| **Kamara basıncı-zaman eğrisi** (CSV, ham) | c* ve yanma verimi korelasyonunun kendisi; itkiden çok daha ayırt edici |
| **Sensör kalibrasyonu/belirsizliği** (yük hücresi + basınç: tam ölçek, sınıf, son kalibrasyon) | `measurement_uncertainty` — YOKSA UYDURMAYIZ, alan hiç yazılmaz; varsa korelasyon skoru belirsizlikle yorumlanır |
| **Anormallik notu** (ateşleme gecikmesi, chuffing, nozul erozyonu, sızıntı, erken kesme) | `anomaly` — "temiz yakma" varsayımı yapılmaz |
| **Nozul boğazı yakma SONRASI çapı** | Erozyon → performans farkının ayrıştırılması |
| **Video/foto** (varsa) | Anormallik doğrulaması (repoya girmez, yalnız değerlendirme) |

## 3. HRMA tarafı (döngünün öngörü yarısı)

- Motorun **HRMA'daki tasarımı**: `.hrma` proje dosyası YA DA girdi seti
  (hangi sayfada, hangi girdilerle). Test edilen motor ile HRMA'ya girilen
  motor AYNI olmalı — öngörü kaydı test GÜNÜNDEN ÖNCE alınırsa döngü
  "önceden tahmin" niteliği kazanır (sonradan uydurma şüphesi kalmaz).

## 4. Biçim kuralları (şemadan)

- Sayılar **orijinal birimleriyle** gelsin (kgf ise kgf; psi ise psi) — birimi
  anahtarın yanına yazın; dönüşümü biz yaparız (`units_original` ilkesi).
- Zaman serileri **ham CSV**; grafikten sayısallaştırma zorunda kalırsak
  `digitized: true` işaretlenir (güven düşer — mümkünse ham).
- Ölçülmeyen şey için tahmin İSTEMİYORUZ — "ölçmedik" de veridir (`null`).
- Birden çok yakma varsa her yakma AYRI kayıt (test_id: `hyb-ayberk2026-b1`
  deseni).

## Durum

- [ ] Liste Ayberk'e gönderildi (Berke)
- [ ] Veri geldi → `validation_records/` kaydı + doğrulayıcı
- [ ] Korelasyon koşusu + `correlation_panel` → kapı #3 kapanış kanıtı
