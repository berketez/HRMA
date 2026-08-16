# formal/ — HRMA biçimsel doğrulama platformu

Lean 4 + Mathlib ile HRMA'nın çözücülerine verilen **matematiksel varsayımların**
makine ispatları. Bir varsayım yanlışsa çözücü sessizce yanlış dala oturur —
test yeşil kalır, sayı yanlış çıkar. Buradaki teoremler o varsayım sınıfının
bir daha sessizce bozulamamasını sağlar; `check.py` kapısı da teorem ↔ Python
bağının çürümesini engeller.

**Ölçülen durum (16 Ağustos 2026):** `LeanLab/` altında 58 `theorem`/`lemma`
bildirimi var; bunların 39'u kayıt defterindeki (registry.json) ana teoremlerdir,
kalanı yardımcı lemma/ara adımdır. `lake build` bu depoda çalıştırıldı ve
`Build completed successfully (8662 jobs)` ile bitti; 39 teoremin tamamının
`#print axioms` çıktısı `[propext, Classical.choice, Quot.sound]` — hiçbirinde
`sorryAx` yok. (16 Ağu eklemesi: CFD analitik referans kulvarı,
`HRMACfdReferans.lean`, 20 teorem — izantropik özdeşlikler, normal şok
Rankine-Hugoniot türetim tutarlılığı, HLLC ara-durum özdeşlikleri, boğulmuş
debi türetimi; `docs/mimari/cfd-tasarimi.md` §"Lean biçimsel ayak".)

## Dizin

| Dosya | Ne |
|---|---|
| `lean-toolchain` | Lean sürüm pini: `leanprover/lean4:v4.32.2` |
| `lakefile.toml` | Lake proje tanımı; Mathlib `v4.32.2` pinli |
| `lake-manifest.json` | Bağımlılık kilidi (Mathlib rev `905b9581...` dahil) — commit'lenir |
| `LeanLab.lean` | Kök modül: altı HRMA ispat dosyasını içe aktarır |
| `LeanLab/HRMA.lean` | Alan/Mach bağıntısının süpersonik dalda tekliği |
| `LeanLab/HRMANozzleBranch.lean` | Subsonik dal ve `brentq` alt sınırının (1.0001) gerekçesi |
| `LeanLab/HRMAGeometry.lean` | Kesik koni halka hacmi; ince kabuk hatası tam `π·t²·L` |
| `LeanLab/HRMAAtmosphere.lean` | ISA katman tablosunun sınır sürekliliği ve tepe sıcaklığı |
| `LeanLab/HRMAInjector.lean` | Nurick kavitasyon sayısının `P_v`'ye göre hata yönü |
| `LeanLab/HRMACfdReferans.lean` | CFD analitik referansları: izantropik özdeşlikler, normal şok RH türetimi, HLLC ara-durum özdeşlikleri, boğulmuş debi türetimi |
| `registry.json` | **Kayıt defteri:** her teorem → koruduğu Python satırı (makine-okunur) |
| `check.py` | **Kapı:** derleme + `sorryAx` + bağ denetimi; çıkış kodu 0/1 |
| `HRMA_ISPATLARI.md` | 2 Ağustos 2026 tarihli ayrıntılı ispat kaydı (tarihî anlık görüntü) |

`.lake/` (≈7 GB Mathlib önbelleği ve derleme çıktıları) `.gitignore`'dadır,
depoya girmez.

## Çalıştırma

Gereksinim: [elan](https://github.com/leanprover/elan) (Lean sürüm yöneticisi).
`lean-toolchain` dosyası sayesinde bu dizinde her `lake`/`lean` çağrısı
otomatik olarak 4.32.2 ile çalışır.

```bash
cd formal

# İlk kurulumda (temiz klonda) Mathlib'in hazır derlenmiş dosyalarını indir.
# Bu adım atlanırsa Mathlib sıfırdan derlenir — saatler sürer.
lake exe cache get

lake build            # her şeyi derle ve doğrula
```

Tam denetim (önerilen):

```bash
python3 formal/check.py               # depo kökünden
python3 formal/check.py --skip-build  # derlemeyi atla, aksiyom + bağ denetimi
python3 formal/check.py --links-only  # yalnız bağ denetimi (Lean gerekmez)
```

`check.py` üç şeyi denetler ve herhangi biri düşerse **1** ile çıkar:

1. **Derleme** — `lake build` başarılı mı, çıktıda `sorry`/`sorryAx` var mı.
2. **Aksiyom** — registry'deki her teorem için `#print axioms` çalıştırır;
   teorem yoksa ya da `sorryAx`'a dayanıyorsa hata. (Önbellekli derleme sessiz
   kaldığında bile delikli ispatı yakalar.)
3. **Bağ** — registry'deki her `lean_file:lean_line` satırında gerçekten o
   teorem bildirimi, her `python_file:python_line` satırında gerçekten
   `anchor` metni var mı. Satır kaydıysa yeni satırı önerir.

## Yeni teorem ekleme akışı

1. İspatı `LeanLab/` altına yaz (ya da mevcut dosyaya ekle); yeni dosyaysa
   `LeanLab.lean`'e `import LeanLab.YeniDosya` satırını ekle.
2. Dosyanın sonuna `#print axioms TeoremAdi` koy (delik denetimi için).
3. `registry.json`'a kayıt ekle: teorem adı, Lean dosya/satır, koruduğu
   Python dosya/satır, o satırda geçen `anchor` metni, iki dilde iddia.
4. `python3 formal/check.py` çalıştır — TAMAM demeden commit'leme.

Python tarafında korunan satır değişirse (satır kayması dahil) `check.py`
hata verir; kayıt defterindeki `python_line`/`anchor` güncellenerek bağ
bilinçli biçimde yeniden kurulur. Amaç tam olarak bu: bağın **sessizce**
kopmaması.

## Neyi kanıtlıyor

İspatlar, koddaki formüllerin **Lean'de yeniden yazılmış** hâllerinin
matematiksel doğruluğunu gösterir: monotonluk (kök tekliği), kapalı biçim ↔
integral eşitliği, tablo sürekliliği, hata yönü. Her teorem genel matematik
değil, `hrma/` içindeki belirli bir satırın gerekçesidir; hangi satır olduğu
`registry.json`'dadır.

## Neyi KANITLAMIYOR

Dürüst sınırlar:

* **Python'un ifadeyi doğru uyguladığını kanıtlamaz.** Lean ile Python
  arasında otomatik anlam bağı yok; bağ, registry'deki satır referansıdır ve
  `check.py` yalnız satırın **yerinde durduğunu** denetler, anlamını değil.
  Python tarafının doğruluğu test paketiyle (`tests/`) sınanır.
* **Fiziksel model seçimini kanıtlamaz.** "Nurick ölçütü doğru ölçüttür",
  "ISA 1976 doğru atmosferdir" birer deney/standart sorusudur, ispat sorusu
  değildir. İspatlanan, seçilen modelin matematiksel tutarlılığıdır.
* **Kayan nokta aritmetiğini modellemez.** Teoremler gerçel sayılar (ℝ)
  üzerinde geçerlidir; yuvarlama/taşma davranışı ayrı bir konudur.
* **Kapsam seçicidir.** 39 teorem, denetimlerde fiilen hata çıkmış üç sınıfı
  (kök tekliği, hacim formülü, tablo tutarlılığı), bir hata-yönü analizini ve
  CFD test merdiveninin analitik referans bağıntılarını (izantropik, normal
  şok, HLLC ara-durum, boğulmuş debi) kapsar; HRMA'nın bütün fiziği
  biçimselleştirilmiş değildir. Sayısal çözücünün kendisi (ayrıklaştırma,
  akı seçimi, zaman ilerletme) ispat konusu değildir — test merdiveni
  doğrular. Yeni varsayımlar yukarıdaki akışla eklenir.

## Köken

Bu platform 14 Ağustos 2026'da `~/Desktop/dosyalar/lean-lab` çalışma
alanından depoya taşındı (kaynak silinmedi). Kaynaktaki `Basic.lean`
(kurulum alıştırması; `hata_sinirli` teoreminde **kasıtlı** bir `sorry`
içerir, Aristotle denemeleri için hedef) HRMA ile ilgisiz olduğu ve kapının
`sorry` denetimini anlamsızlaştıracağı için bilinçli olarak **taşınmadı**.
