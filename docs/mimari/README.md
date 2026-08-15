# HRMA mimari belgeleri

**Son güncelleme:** 2026-08-14
**Kapsam:** Bu dizin iki soruyu cevaplar: **sistem nasıl kurulu** ve **nereye
gidiyor**. Nasıl kurulacağı (`INSTALL.md`), nasıl kullanılacağı
(`docs/USER_MANUAL.md`), nasıl katkı verileceği (`CONTRIBUTING.md`) ve fizik
doğrulamasının durumu (`docs/VALIDATION_STATUS.md`) başka belgelerin işidir.

---

## Belgeler

| Belge | Ne cevaplar |
|---|---|
| **[sistem-haritasi.md](sistem-haritasi.md)** | Hangi dizin neyden sorumlu, hangi katman hangi katmanı çağırır, her parça ne kadar büyük. Katman diyagramı, 91 ucun gruplanması, analiz modüllerinin **ölçülmüş bağlama matrisi**, bağımlılıklar ve pin gerekçeleri |
| **[veri-akisi.md](veri-akisi.md)** | Bir isteğin uçtan uca yolculuğu: form alanı → toplayıcı → HTTP → uç kapıları → motor → analiz modülleri → yanıt sözlüğü → panel. `/calculate_solid` gerçek fonksiyon adları ve `dosya:satır` referanslarıyla izlendi; ölçülmüş 62 anahtarlı yanıt |
| **[modul-sozlesmeleri.md](modul-sozlesmeleri.md)** | Katmanlar arasında neyin garanti edildiği: analiz modülü ne alır ne döndürür, `NOT_MODELLED` beyanının taahhüdü, motor ↔ analiz sınırı, uç ↔ motor sözleşmesi, yeni modül kontrol listesi |
| **[yol-haritasi.md](yol-haritasi.md)** | Ölçülmüş bugün + planlanan yarın. A-F kulvarlarının **bugünkü** durumu, 2.7 kapı ölçütleri, yayın stratejisi, açık kuyruk, ve mevcut plan dosyaları arasındaki **çelişkiler** |
| **[teknik-borc.md](teknik-borc.md)** | Bilinen borçlar: her biri nerede, hangi ölçümle bulundu, neden bekliyor, nasıl kapanır. Kapatma sıralaması önerisiyle |

---

## Bu belgelerin kuralı

**Ölçmediğimizi yazmıyoruz.** Buradaki her sayı bir komutun çıktısıdır ve
komut belgede yazılıdır. Bir modülün ne yaptığı iddia edilmeden önce dosya
açılmıştır; bir satır sayısı verilmeden önce `wc -l` çalıştırılmıştır.

**Tarih uydurmuyoruz.** Plan dosyalarında geçen tarihler *karar* tarihleridir.
Teslim tarihi hiçbir kaynakta yoktur; bu belgelerde de yoktur.

**Eskimeyi işaretliyoruz.** Ölçüm tabanı her belgenin başında commit ve tarih
olarak yazılıdır. Plan dosyalarındaki eskimiş tablolar
[yol-haritasi.md § 8](yol-haritasi.md#8-plan-dosyaları-arasındaki-çelişkiler-ve-eskimeler)'de
tek tek işaretlenmiştir — kaynak dosyalara dokunulmamıştır.

---

## Nereden başlamalı

| Amacınız | Okuyun |
|---|---|
| Depoyu ilk kez açtınız | `sistem-haritasi.md` § 1-2, sonra `veri-akisi.md` § 2 |
| Yeni bir fizik modülü yazacaksınız | `modul-sozlesmeleri.md` § 1 ve § 7 (kontrol listesi) |
| "Ekrandaki bu sayı nereden geliyor?" | `veri-akisi.md` § 3 ve § 7 (ölçen araçlar) |
| Bir modülü motora bağlayacaksınız | `modul-sozlesmeleri.md` § 2, sonra `yol-haritasi.md` § 2 |
| Ne üzerinde çalışacağınıza karar veriyorsunuz | `yol-haritasi.md` § 3 (kapı ölçütleri) + `teknik-borc.md` § 12 (sıralama) |
| Bir kusuru kovalıyorsunuz | `veri-akisi.md` § 7 → `python3 tools/wiring_map.py --page <sayfa>` |

---

## Hızlı ölçüm

```bash
# Büyüklük
find hrma -name "*.py" -not -path "*__pycache__*" | wc -l
find hrma -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | sort -rn | head -20

# Uçlar
grep -c "@app.route" hrma/app.py

# Beyan yoğunluğu
grep -rn "NOT_MODELLED" hrma/ --include='*.py' | grep -v __pycache__ | wc -l

# Testler
python3 -m pytest --collect-only -q 2>&1 | tail -2

# Canlı bağlama haritası (ölçerek üretir; hibritte ~40 sn)
python3 tools/wiring_map.py --page hybrid
```

---

## İlgili belgeler

| Belge | Konu |
|---|---|
| `docs/YOL_HARITASI_2.7_VE_SONRASI.md` | Kulvar tanımlarının kaynağı (durum tabloları eskimiş — [yol-haritasi.md § 8.1](yol-haritasi.md)) |
| `docs/V2.7_ANALIZ_MODULU.md` | 2B eksenel simetrik FEA kararının gerekçesi ve doğrulama vakaları |
| `docs/ANALIZ_PLATFORM_PLANI.md` | Analiz güvertesi mimarisi ve panel kalıbı |
| `docs/GUVEN_SURUMU_PLANI.md` | Belirsizlik nicelemesi ve deney doğrulama altyapısının tasarımı |
| `docs/SPACE_CAPABILITY.md` | Kármán sınıfı hibrit için yetenek matrisi ve kapsam dışı listesi |
| `docs/VALIDATION_STATUS.md`, `docs/VALIDATION_SOURCES.md` | Fizik doğrulamasının durumu ve kaynak künyeleri |
| `docs/STANDART_ATIFLARI.md` | Standart ve literatür atıfları |
| `docs/BICIMSEL_ISPATLAR.md` | Lean ile doğrulanmış varsayımlar |
| `docs/USER_MANUAL.md` | Kullanma kılavuzu |
| `CONTRIBUTING.md`, `docs/RELEASE.md` | Katkı ve yayın süreci |
