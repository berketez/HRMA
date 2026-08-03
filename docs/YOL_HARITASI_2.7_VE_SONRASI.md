# HRMA yol haritası — v2.7 ve sonrası

**Tarih:** 3 Ağustos 2026 · **Taban:** HEAD `9d3728e` (v2.6.26 öncesi)
**Durum:** v2.6.26 çıkana kadar HİÇBİRİ başlamaz. Bu belge iş kırılımıdır.

Bu belgedeki her sayı ölçüldü, tahmin edilmedi. Ölçüm komutları madde
başlarında.

---

## 0. Ölçülen mevcut durum

### 0.1 Motor tipleri arasındaki derinlik farkı

```bash
wc -l hrma/engines/*_rocket_engine.py
grep -c "NOT_MODELLED\|not_modelled" hrma/engines/<tip>_rocket_engine.py
```

| | Sıvı | Hibrit | Katı |
|---|---:|---:|---:|
| Kod satırı | 7766 | **2657** | 7232 |
| Bağlı alt sistem | 10 | **6** | 7 |
| `NOT_MODELLED` beyanı | 47 | **4** | 23 |

Hibrit her ölçüde en sığ. Ama asıl mesele üçüncü satır: **4** sayısı hibritin
daha çok şey modellediği anlamına gelmiyor — **modellemediğini beyan etmediği**
anlamına geliyor. Sıvı 47 yerde "bunu hesaplamıyorum" diyor, hibrit 4.

### 0.2 Ortak analiz modüllerinin bağlanma durumu

`hrma/analysis/` altında 26 modül var. Onbirinin motor tipine bağlanma durumu:

| Modül | Sıvı | Hibrit | Katı | app.py |
|---|:-:|:-:|:-:|:-:|
| `bolted_joint` | — | — | ✓ | ✓ |
| `pressurant_sizing` | ✓ | — | — | ✓ |
| `pressure_vessel` | — | — | ✓ | ✓ |
| `tank_blowdown` | — | — | — | **—** |
| `water_hammer` | — | — | — | ✓ |
| `slosh_analysis` | — | — | — | ✓ |
| `kinetic_analysis` | — | — | — | ✓ |
| `launch_site` | ✓ | — | ✓ | ✓ |
| `regen_cooling` | ✓ | — | — | ✓ |
| `thermal_protection` | ✓ | — | ✓ | ✓ |
| `uncertainty` | — | — | ✓ | ✓ |

**İki sonuç:**

1. **Hibrit, on bir modülün HİÇBİRİNE bağlı değil.** Programın adı
   *Hybrid Rocket Motor Analysis* ve en sığ motor tipi hibrit.
2. **`tank_blowdown.py` hiçbir yere bağlı değil** — ne motora, ne `app.py`'ye.
   Yazılmış, duruyor, kullanılmıyor. Ve blowdown beslemesi tam olarak
   hibrit N₂O motorunun ihtiyacı.

Bu iki gözlem, en ucuz derinlik kazancının nerede olduğunu söylüyor: **yeni
fizik yazmadan, var olan modülleri bağlayarak.**

### 0.3 Efor ölçeği

`S` birkaç saat · `M` 1-3 gün · `L` 1-2 hafta · `XL` aylar

---

## Kulvar A — Motor tipleri arasında derinlik eşitleme

**En yüksek getirili kulvar.** Çoğu kalem yeni fizik değil, var olan modülü
ikinci bir motor tipine bağlamak. Her kalem bittiğinde hibrit/katı, sıvının
sahip olduğu bir yeteneği kazanır.

| ID | İş | Girdi durumu | Çıktı | Efor |
|---|---|---|---|---|
| **A1** | `tank_blowdown` → hibrit | Modül yazılı, hiç bağlı değil. Hibritte tank hacmi, başlangıç basıncı, ṁ var | Blowdown eğrisi: tank basıncı(t), ṁ(t), itki düşüşü — **hibritin en büyük fizik açığı** | M |
| **A2** | `slosh_analysis` → hibrit + sıvı | Modül var, yalnız `app.py`'de. Tank çapı/dolum oranı hesaplanıyor | Slosh frekansı, kütle oranı, baffle ihtiyacı. `g_eff` uçuşta değiştiği için yörüngeyle bağlanmalı | M |
| **A3** | `pressure_vessel` → hibrit + sıvı tankı | Katıda bağlı, diğerlerinde yok | Tank/oda için ASME membran + kapak gerilmesi, tek yerden | S |
| **A4** | `bolted_joint` → hibrit + sıvı | Katıda bağlı | Kapak cıvatası boyut/sınıf/sayı, ön yükleme, sızdırmazlık marjı | S |
| **A5** | `thermal_protection` → hibrit | Sıvı ve katıda bağlı | Yalıtım kalınlığı, ablatif çekilme, cidar sıcaklık geçmişi | M |
| **A6** | `water_hammer` → sıvı + hibrit besleme hattı | Modül var, yalnız `app.py`'de. Hat uzunluğu/çapı, ṁ, vana kapanma süresi gerekiyor | Joukowsky tepe basıncı, vana kapanma kısıtı | S |
| **A7** | `uncertainty` → hibrit + sıvı | Katıda bağlı | Girdi belirsizliğinin çıktıya taşınması (şu an yalnız katıda) | M |
| **A8** | `launch_site` → hibrit | Sıvı ve katıda bağlı | Rakım/ortam düzeltmesi, menzil güvenliği girdisi | S |
| **A9** | Hibritte **O/F kayması** | Regresyon hesaplanıyor; O/F sabit varsayılıyor | Yanma boyunca O/F(t), Isp(t) — hibritin karakteristik davranışı | M |
| **A10** | Hibritte `NOT_MODELLED` beyan taraması | 4 beyan vs sıvıda 47 | Hibritin modellemediği her şey açıkça beyanlı hâle gelir | S |

**A10 önce yapılmalı.** Hibritin ne yapmadığını bilmeden ne ekleyeceğimizi
seçemeyiz; ayrıca kullanıcı bugün hibritte sessiz varsayımlarla karşılaşıyor.

---

## Kulvar B — CAD ve görselleştirme derinleştirme

Ölçüm: `motor_viz3d.js` şu an **10 `CylinderGeometry` + 6 `TorusGeometry` +
1 `LatheGeometry`** ile kurulu.

| ID | İş | Girdi durumu | Çıktı | Efor |
|---|---|---|---|---|
| **B1** | **Soğutma kanalı geometrisi** | `regen_cooling` `n_channels`, genişlik, yükseklik, land **hesaplıyor**; hiç çizilmiyor | Gerçek kanal dizisi, kesit görünümü. Tek en yüksek görsel kazanç, yeni fizik yok | S |
| **B2** | **Enjektör delik deseni** | `n_holes`, `d_h`, desen tipi, L/D hesaplanıyor; plaka çiziliyor delik yok | Plakada gerçek delik yerleşimi, çarpışma noktaları, swirl açısı | S |
| **B3** | Lüle konturunu 3B'de gerçek profilden çiz | Ortak kontur örnekleyici var (STL yolunda kullanılıyor) | 3B görünüm ile export aynı geometriden | S |
| **B4** | **Kaynağa göre renklendirme** | `_basis`/`_source`/`NOT_MODELLED` zaten var | Hesaplanmış / kullanıcı / varsayım / modellenmemiş yüzeyler ayrı renk. **Hiçbir CAD aracının yapmadığı şey** | M |
| **B5** | Katı grain yanma animasyonu | Regresyon zaman serisi hesaplanıyor | Grain'in yanma boyunca erimesi — statik modellerin yapamadığı | M |
| **B6** | Kesit (cutaway) görünümü | Cidar kalınlığı, kanal, grain hepsi var | Mühendislik açısından en değerli görsel | M |
| **B7** | Fotogerçekçi render | B1-B6 bitince | Malzeme, ışık, gölge — sunum kalitesi | M |

**Sıra: B3 → B1 → B2 → B6 → B4 → B5 → B7.** B4 (kaynak renklendirme)
teknik olarak B1-B3'ten sonra gelmeli ama **ürün açısından en ayırt edici
madde odur** — gösterilebilir bir şey lazımsa öne alınabilir.

---

## Kulvar C — Yeni bileşen modülleri

Bunlar "HRMA hesaplamıyor" denen bileşenler. Hepsi hesaplanabilir; sadece
modül yazılmamış.

| ID | İş | Ne gerekiyor | Ne çıkar | Efor |
|---|---|---|---|---|
| **C1** | **Turbopompa boyutlandırma** | `cycle_power_balance` ṁ, ΔP, verim, mil gücü, TIT veriyor. **Eksik: mil devri N.** Zincir: NPSH → emme özgül devri Nss → N üst sınırı → özgül devir Ns → çark çapı, kanat sayısı, indüser. Kaynak: Huzel & Huang NASA SP-125 Böl. 6; Sutton Böl. 10 | Çark çapı, kanat sayısı, indüser geometrisi, türbin ortalama çapı ve kademe sayısı, **NPSH marjı** | L |
| **C2** | Vana ve besleme hattı | Hat çapı/uzunluğu var; vana için Cv, açılma süresi | Vana boyutu, basınç düşüm bütçesi, hat güzergâhı geometrisi | M |
| **C3** | Gimbal ve itki montajı | İtki, gimbal açısı, montaj noktası | Aktüatör kuvveti, montaj yükleri, halka geometrisi | M |
| **C4** | Ateşleyici | Kendi fiziği yok — torch/piroteknik akış, enerji, süre | Ateşleyici debisi, enerjisi, güvenli ateşleme penceresi | M |
| **C5** | Tank basınçlandırma sistemi | `pressurant_sizing` sıvıda bağlı | Helyum/N₂ şişe boyutu, regülatör, hibrite de bağlanmalı (A1 ile) | S |

**C1 asıl iş.** Üç şeyi birden veriyor: turbopompa görselinin hesaplanmış hâli,
gerçek kavitasyon marjı (Lean'de biçimsel ispatladığımız `K_c` işinin
turbopompa karşılığı), ve v2.7 mesh analizinin girdisi.

**C1 doğrulama kümesi zorunlu:** Merlin, RD-180, RL10 için yayımlanmış N,
çark çapı ve NPSH değerleriyle karşılaştırma. Bu olmadan C1 yayımlanmaz.

---

## Kulvar D — v2.7 analiz modülü (mesh + termal + yapısal)

Ayrıntı: `docs/V2.7_ANALIZ_MODULU.md`. Özet iş kırılımı:

| ID | İş | Efor |
|---|---|---|
| **D1** | Eksenel simetrik yapısal çözücü (kendi yapısal mesher'ımız, gmsh yok) | L |
| **D2** | Eksenel simetrik ısı çözücü (kararlı + geçici) | L |
| **D3** | Doğrulama kümesi — **zorunlu**: Lamé kalın cidar, 1-B geçici iletim, patch testi, mesh yakınsaması | M |
| **D4** | CAD → mesh köprüsü (kontur + cidar + kanal geometrisinden) | M |
| **D5** | Sonuç görselleştirme (gerilme/sıcaklık konturu) | M |

**Bağımlılık:** D4, B1'e bağlı — soğutma kanalı geometrisi olmadan ısı analizi
eksik kalır. Yani **B1 hem görsel hem analiz kulvarını besliyor.**

CFD bu sürümde YOK. v3/v3.5.

---

## Kulvar E — Arayüz ve pano

| ID | İş | Girdi durumu | Efor |
|---|---|---|---|
| **E1** | Sekme → ızgara yerleşim | `analysis_dock.js` grid destekliyor, 14 panel var | S |
| **E2** | **Bağlı güncelleme + "ne değişti" vurgusu** | Girdi değişince etkilenen grafikler güncellenip **değişen büyüklükler işaretlensin** (eski → yeni) | M |
| **E3** | Grafiklerde kaynak renklendirme | `_basis`/`_source` var — B4'ün grafik karşılığı | S |
| **E4** | İki tasarımı üst üste karşılaştırma | `comparative_panel` var | S |
| **E5** | Duyarlılık grafiği — hangi girdi amacı gerçekten oynatıyor | Parametrik tarama altyapısı var | M |

**Not:** E1'i Faz 6'nın (tarayıcıda mühendis gözüyle denetim) çıkardığı somut
listeyle yapmak, şimdi tahminle yapmaktan iyidir.

---

## Kulvar F — v3 ve sonrası

| ID | İş | Efor |
|---|---|---|
| **F1** | CFD (lüle iç akışı, ayrılma, şok) | XL |
| **F2** | Yanma kararsızlığı ayrıntılı model (akustik mod + yanma tepkisi) | XL |
| **F3** | Test verisi korelasyonu — kör holdout, ölçüm belirsizliği zinciri | XL |
| **F4** | Çok fazlı akış, tanecik yükü | XL |

---

## Önerilen sıra

**v2.6.26 çıktıktan hemen sonra**

1. **A10** — hibritin beyan taraması (S). En ucuz, en çok yanlış güveni keser.
2. **B3 + B1 + B2** (S+S+S). Görünür kazanç, yeni fizik yok, sürüm riski yok.
3. **A1** — `tank_blowdown` hibrite (M). Yazılmış ama hiç bağlanmamış modül.

**v2.7**

4. **A2-A8** — modül bağlama kalemleri, tercihen paralel (kesişmeyen dosyalar).
5. **D1-D5** — analiz modülü, D3 (doğrulama) olmadan yayımlanmaz.
6. **B6 + B4** — kesit görünümü ve kaynak renklendirme.
7. **E1-E4** — Faz 6 listesiyle birlikte.

**v2.8 / v3**

8. **C1** turbopompa + doğrulama kümesi.
9. **C2-C5**, **A9**, **B5**, **B7**, **E5**.
10. **F1-F4**.

---

## Her kalem için değişmez kural

Modül hangi kulvarda olursa olsun:

* Girdi ve çıktısı **beyanlı** olacak: `_basis` / `_source` / `_status` /
  `NOT_MODELLED`.
* Beyanı **okuyan bir karar kapısı** olacak. Faz 4'ün en pahalı dersi:
  `_defaults_used`'a 14 yerde yazılıyordu, 0 yerde okunuyordu.
* Çizilen hiçbir yüzey ve gösterilen hiçbir sayı **hesaplanmamış** olmayacak.
  Hesaplanmayan şey çizilmez; yerine "modellenmedi" beyanı konur.
* Yeni fizik modülü **doğrulama kümesiyle** gelir (analitik çözüm, yayımlanmış
  motor verisi, ya da korunum kontrolü). Doğrulaması olmayan modül yayımlanmaz.
