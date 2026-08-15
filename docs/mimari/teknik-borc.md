# Teknik borç — ne borçlu, nerede, neden bekliyor

**Son güncelleme:** 2026-08-14
**Kapsam:** Bilinen ve **ölçülmüş** teknik borçlar. Her madde: borcun ne
olduğu, kodda nerede durduğu, hangi ölçümle bulunduğu, neden bekletildiği ve
kapatma ölçütü. Gelecek işlerin sıralaması [yol-haritasi.md](yol-haritasi.md)'de.

**Ölçüm tabanı:** `2e2375d`, 14 Ağustos 2026.

---

## 0. Bu belgenin var oluş sebebi: borç greplenemiyor

```bash
grep -rn "TODO\|FIXME" hrma/ --include='*.py' --include='*.js' \
  | grep -v __pycache__ | grep -v vendor
# → 0 sonuç
```

Birinci taraf kaynağında **tek bir `TODO` ya da `FIXME` yok.** Bu, borcun
olmadığı anlamına gelmiyor: bu depoda borç **düzyazıyla** kaydediliyor —
docstring'lerde, blok yorumlarında, `_basis` metinlerinde, `NOT_MODELLED`
maddelerinde. Örnek, `thermal_protection.py` içinde birebir şöyle yazılı:

> *"MERKEZİLEŞTİRME BORCU: depoda tek bir fizik-sabitleri modülü YOK …
> Bu modül kendi tanımını KORUR (import zinciri açmamak için) ama borç
> kayıtlıdır."*

Bu üslubun **iyi** yanı: borcun gerekçesi, ölçümü ve etkisi kaydın içinde
duruyor; `# TODO: fix this` bunların hiçbirini taşımaz. **Kötü** yanı:
araçla toplanamıyor, dolayısıyla unutulabiliyor. Bu belge o toplamayı elle
yapar.

> **Bakım kuralı:** yeni bir borç yaratıldığında (a) gerekçesi kodda düzyazı
> olarak kalır, (b) bu belgeye tek satırlık bir madde eklenir. `TODO` yorumu
> ekleme geleneği başlatılmaz — mevcut üslup daha iyi bilgi taşıyor.

---

## 1. Arayüz, arka ucun kapattığı yanma hızı kusurunu geri açıyor

**Ölçek:** S (düzeltme), ama etkisi büyük · **Sınıf:** dikiş kusuru (Katman A)

### Ölçüm

Aynı motor, iki yoldan çağrıldı (`app.test_client()`, temiz `HEAD` kopyası,
APCP, Ø100 mm, tane 500 mm, çekirdek 30 mm, 40 bar):

| Yol | `burn_rate_a_source` | `a` | Yanma süresi | Ortalama itki |
|---|---|---:|---:|---:|
| Alan **gönderilmedi** (API) | `central_catalog:apcp` | 0,0022334 | **4,860 s** | **3 065 N** |
| Alan **0,005** geldi (tarayıcı) | `request` | 0,005 | **2,186 s** | **6 739 N** |

Fark: yanma süresi **2,22 kat**, ortalama itki **2,20 kat**. Toplam impuls
neredeyse aynı kalıyor (14 894 ↔ 14 734 N·s) — yani kusur, toplam impulse
bakan bir gözle **görünmez**.

İkinci yolda kullanıcı ayrıca şu uyarıyı alıyor:
`warn.solid.burn_rate_off_catalog` — *kendi yazmadığı* bir sayı yüzünden
"kataloğun dışındasın" uyarısı.

### Kök

Arka uç bu kusuru v2.6.27'de (A3) kapattı: `_build_solid_engine`
(`hrma/app.py:3140`) artık alan gelmediyse motora hiç geçmiyor, değeri
merkezî katalogdan çözüyor ve kaynağını beyan ediyor. Ama şablon tarafı
eski sayıyı hâlâ üç yerde taşıyor:

* `hrma/templates/solid.html:1242` — `<input id="burn_rate_a" value="0.005">`
* `hrma/templates/solid.html:3658` — `parseFloat(...) || 0.005`
* `hrma/templates/solid.html:4443` — `resetForm()` alanı `'0.005'` yapıyor

Yanma hızı ön ayarı (`burn_rate_preset`) varsayılan olarak `custom`
olduğundan, sayfa açılışında `/api/burn-rate/resolve` **çağrılmaz**.
Kullanıcı alana hiç dokunmasa bile `0.005` gönderilir ve arka uç bunu
`request` (yani "kullanıcı böyle istedi") sayar.

### Neden bekliyor

Arka uç düzeltmesi ile şablon düzeltmesi ayrı ajan kulvarlarındaydı; kapı
testleri API katmanını sınadığı için yeşil kaldı. Kusur, tam olarak bu
deponun en pahalı sınıfı: **iki parça tek başına doğru, aradaki dikiş
yanlış.**

### Kapatma ölçütü

`solid.html` yanma hızı alanları boş açılır (ya da seçilen yakıtın katalog
değeriyle açılır ve kaynağı ekranda yazar); toplayıcıdaki `|| 0.005`
kalkar; bir bekçi, sayfanın ürettiği yükte `burn_rate_a` yokken yanıtın
`burn_rate_a_source == 'central_catalog:apcp'` döndüğünü doğrular.

---

## 2. Stefan-Boltzmann sabiti altı ayrı yerde tanımlı

**Ölçek:** S · **Sınıf:** parametre tutarlılığı

```bash
grep -rn "5.670374419e-8" hrma/ --include='*.py' | grep -v __pycache__
```

| Dosya | Ad |
|---|---|
| `hrma/analysis/heat_transfer_analysis.py:121` | `self.stefan_boltzmann` |
| `hrma/analysis/safety_analysis.py:31` | `'stefan_boltzmann'` |
| `hrma/analysis/structural_analysis.py:318` | `SIGMA_SB` |
| `hrma/analysis/thermal_protection.py` | `STEFAN_BOLTZMANN` |
| `hrma/fea/thermal_axisym.py:103` | `STEFAN_BOLTZMANN_W_M2K4` |
| `hrma/engines/solid_rocket_engine.py:301` | `'stefan_boltzmann'` |

Altısı da **aynı** CODATA 2018 değerini taşıyor; bugün bir sapma yok. Borç
sayının yanlışlığı değil, **tek kaynak kuralının çiğnenmesi**: `hrma/constants.py`
15 sabit tanımlıyor ama fiziksel sabitler için ortak bir yer değil.

**Neden bekliyor:** `thermal_protection.py` içinde gerekçesi yazılı — import
zinciri açmamak için modül kendi tanımını koruyor. Ayrıca altı dosya altı
farklı ajan kulvarına ait; eşzamanlı dokunmak çakışma riski taşıyor.

**Kapatma ölçütü:** `hrma/constants.py`'ye (ya da yeni bir
`hrma/physical_constants.py`'ye) tek tanım; altı yer oradan import eder; bir
bekçi testi aynı sayının ikinci kez tanımlanmasını yakalar.

---

## 3. `gimbal_mount` — yazılmış, test edilmiş, hiçbir yere bağlanmamış

**Ölçek:** S (bağlama) · **Sınıf:** yetim modül

```bash
grep -rn "gimbal_mount" --include="*.py" --include="*.js" --include="*.html" .
```

Sonuç: modülün kendisi, `tests/test_c_kulvari_bilesenler.py` (iki çağrı) ve
`i18n_pages.js` içinde **yalnız arayüz etiketi** olarak geçen iki dize
(`liq.ui.1_axis_gimbal_mount`, `liq.ui.2_axis_gimbal_mount`). Yani sayfada
gimbal *seçeneği* var, arkasında hesap **yok**.

`hrma/analysis/gimbal_mount.py`, C3 kalemi olarak eksiksiz yazılmış: itki +
sapma açısı → eksenel/yanal bileşen ve itki kaybı → pivot momentleri →
aktüatör kuvveti ve stroku → montaj halkası zorlamaları → cıvata dairesi
başına yük. Kendi `NOT_MODELLED` sözlüğü de var.

**Neden bekliyor:** C kulvarı modülleri (C1-C4) bir dalgada yazıldı, bağlama
sonraki dalgaya bırakıldı; bağlama dalgası C1, C2 ve C4'ü kapattı, C3'e
sıra gelmeden durdu.

**Kapatma ölçütü:** sıvı (ve gerekiyorsa katı) motorda bir `_gimbal_block`
üreticisi; sonuç sözlüğüne bağlama; arayüzdeki gimbal seçeneğinin bu bloğu
göstermesi. Bu, [yol-haritasi.md](yol-haritasi.md) § 3'teki **2. kapı
ölçütünü** (çekirdek-yetim modül sıfır) doğrudan engelleyen tek kalemdir.

---

## 4. Emekli uçların ölü ağırlığı

**Ölçek:** S · **Sınıf:** ölü kod

`/api/cfd-analysis`, `/api/kinetic-analysis` ve `/api/professional-analysis`
**HTTP 501** döndürüyor ve halef uca yönlendiriyor — doğru karar, çünkü
ölçüm ikisinin de kullanılamaz olduğunu göstermişti (`cfd_analysis.py`
kütle korunumu sağlamıyor ve 3 iterasyonda ıraksıyordu; `kinetic_analysis.py`
stiff ODE'yi explicit RK45 ile sürüyor, tek istasyon ~23 dakika alıyordu).

Ama modüller hâlâ **uygulama açılışında yükleniyor**:

```
hrma/app.py:65  from hrma.analysis.cfd_analysis import cfd_analyzer
hrma/app.py:66  from hrma.analysis.kinetic_analysis import kinetic_analyzer
```

Toplam ~2 100 satır ölü kod her başlangıçta içe aktarılıyor, `hrma/analysis/__init__.py`
üzerinden de dışa veriliyor. `app.py:7926` civarındaki bir blok kendi
yorumunda "bu blok zaten yukarıdaki 501 nedeniyle erişilemez" diyor.

**Neden bekliyor:** 501 yanıtı "orijinal işleyici korunur" notuyla yazılmış —
halef modellerin (`nozzle_flow_1d`, `kinetic_efficiency`) tam olgunlaşması
beklenmiş. Bugün ikisi de bağlı ve testli.

**Kapatma ölçütü:** iki modül `hrma/analysis/` altından kaldırılır ya da
`legacy/` altına taşınır; `app.py` içe aktarımları ve erişilemez bloklar
silinir; 501 yanıtı yönlendirme alanıyla kalır.

---

## 5. `app.py` monoliti

**Ölçek:** L · **Sınıf:** yapısal

9 579 satır, 91 route, tek dosya. İçinde route'ların yanı sıra: güvenlik
kapıları, birim dönüştürücüler, JSON temizleyici, iz kimliği üreteci,
motor kurucuları, dışa aktarım orkestrasyonu, STL önbelleği, stdout
gürültü süzgeci ve tip kapıları.

**Ölçülen bedel:** paralel ajan çalışmasında `app.py` en sık çakışan
dosyadır; dosya sahipliği kuralı çoğu zaman "app.py'ye tek ajan dokunur"
biçiminde bir darboğaza dönüşüyor.

**Neden bekliyor:** bölme, 91 route'un tamamını ilgilendiren bir refactor;
tek bir yanlış import sırası uygulamayı açılışta düşürür ve bu, yayın
kapısının en pahalı kırılma biçimidir. Ayrıca 2.6.27 kampanyası boyunca
`app.py` sürekli değişti — hareketli hedefte refactor yapılmaz.

**Kapatma ölçütü:** Flask Blueprint'lerine bölme (sayfa / hesap / analiz /
dışa aktarım / veri / kabuk), çapraz kesen yardımcıların ayrı modüle
alınması; 6 503 testin tamamı yeşil kalmalı, açılış süresi ölçülüp
karşılaştırılmalı.

---

## 6. Sürüm dizesi gerçeği göstermiyor

**Ölçek:** S · **Sınıf:** künye

`hrma/__init__.py:8` → `__version__ = "2.6.26"`. Oysa depoda 2.6.27'nin
dokuz partisi işlenmiş durumda.

Bu dize üç yere gidiyor: `inject_app_version()` ile her şablona,
`utils/projects.py` içinde kaydedilen `.hrma` proje dosyalarına, ve
`utils/update_checker.py` üzerinden güncelleme karşılaştırmasına. Yani
bugün kaydedilen bir proje dosyası **kendini yanlış sürümle künyeliyor**.

**Neden bekliyor:** sürüm artırımı yayın turunun adımı olarak tanımlı ve
2.6.27 henüz yayın turuna girmedi; kamuya sürüm de
[yol-haritasi.md](yol-haritasi.md) § 4 gereği FINAL'e ertelendi.

**Kapatma ölçütü:** sürüm artışı iç sürüm üretiminin (etiket → runner →
taslak) zorunlu ilk adımı yapılır; bir bekçi, etiket ile `__version__`
uyuşmazlığını yakalar.

---

## 7. İki ayrı `injector_design` modülü

**Ölçek:** M · **Sınıf:** çoğaltma

| Dosya | Satır | Kullanan |
|---|---:|---|
| `hrma/engines/injector_design.py` | 1 918 | Hibrit + sıvı motor, `/api/injector-design`; kendi belgesinde "TEK gerçek kaynak" diyor |
| `hrma/utils/injector_design.py` | 1 266 | `app.py:39` (`InjectorDesign`), `app.py:335` (`injector_plate_structural`) |

İkisi ayrı yaşamıyor: `utils` sürümü, sapmayı kapatmak için `engines`
sürümünden **otoriter yardımcıları** içeri alıyor (`swirl_solve`,
`swirl_K_from_theta`, swirl açı/K zarfı sabitleri ve pintle ucu sentezi).
Kod yorumu bunu açıkça söylüyor: *"iki modül AYNI katsayı ve aynı zarfı
kullansın"*, ve pintle için *"radyal delik dizisi yalnız kardeş modülde
modellenmişti, bu modül pintle'ı çıplak anülüs sanıyordu"*.

Yani bilinen sapmalar tek tek kapatılmış; **çoğaltmanın kendisi duruyor** ve
her yeni enjektör kalemi iki yerde düşünülmeyi gerektiriyor.

**Neden bekliyor:** `utils` sürümü uç katmanının plaka yapısal hesabını da
taşıyor; birleştirme, `app.py` çağrılarının ve enjektör panelinin
sözleşmesini değiştirir.

**Kapatma ölçütü:** tek modül; plaka yapısal hesabı `analysis/` ya da
`engines/` altında net bir yere taşınır; `hrma/utils/injector_design.py`
silinir.

---

## 8. Arka uçta olan girdiler arayüzde yok

**Ölçek:** M · **Sınıf:** dikiş kusuru (Katman A)

Ölçüldü:

| Anahtar | Motorda okunuyor | Şablonda alan |
|---|---:|---:|
| `closure_bolt_size` | sıvı: 1 | `liquid.html`: **0** |
| `closure_bolt_class` | sıvı: 1 | `liquid.html`: **0** |
| `closure_bolt_count` | sıvı: 2, hibrit: 11 | `liquid.html`: **0**, `advanced.html`: **0** |

Motor bu alanları `self.overrides` üzerinden okuyor ve verilmediğinde
yapılandırma varsayılanına düşüyor. Yani kapak cıvatası analizi koşuyor,
ama kullanıcı **tasarımını değiştiremiyor**; API'den çağıran bir istemci
değiştirebiliyor.

Aynı sınıf, vana/hat girdileri için de kayıtlı (kampanya kuyruğunda "sıvı UI
form alanları" olarak geçiyor).

**Neden bekliyor:** bağlama dalgalarının yazılı kuralı "yalnız bağlama, panel
işi yok" idi; arayüz alanı açmak ayrı bir kulvar.

**Kapatma ölçütü:** `tests/support/inventory.py` (Katman A) taramasının,
motorun `overrides`'tan okuduğu her anahtarı ilgili şablonda araması; eksik
olanların ya forma eklenmesi ya da "arayüzde bilinçli olarak yok" listesine
gerekçesiyle yazılması.

---

## 9. `thermal_protection` — iki yollu ablasyon modeli (bilinçli geçici ikilik)

**Ölçek:** M · **Sınıf:** göç borcu

`ThermalProtectionAnalyzer.ablative_thickness` bugün **iki yol** taşıyor:

* **Yeni yol (opt-in):** çağıran `h_gas_W_m2K` **ve** `T_recovery_K` verirse
  net akı burada çözülür — üfleme blokajı, yüzeyin yeniden ışıması ve
  ablasyon sıcaklığı hesaba girer; geçerlilik kapısı bağlayıcıdır (ihlalde
  kalınlık yayımlanmaz, `thickness_status='NOT_MODELLED'`).
* **Eski yol (varsayılan):** bu ikisi verilmezse hesap birebir eskisi gibi
  yapılır — çağıranın verdiği akı doğrudan kullanılır.

Eski yolun kusuru ölçülmüştü: soğuk cidar Bartz akısı besleniyordu, iki
fiziksel terim eksikti ve boğazda ~10² mertebesinde fazla tahmine yol
açıyordu (geometrik denetim de yoktu — varsayılan bir sıvı koşuda boğaz
astarı, boğaz yarıçapının 184 katı çıkıp "sized" yayımlanıyordu).

Dosyanın kendi ifadesiyle bu **"GEÇİCİ İKİLİK bilinçlidir"**: üç motor tipi
de bu fonksiyonu çağırıyor ve hepsini aynı anda yeni yola geçirmek tek
dalgaya sığmadı.

**Kapatma ölçütü:** üç motorun blok üreticileri de `h_gas_W_m2K` +
`T_recovery_K` göndersin; eski yol kaldırılsın; kapı koşulsuz hâle gelsin.

---

## 10. Fizik kapsamı borçları

Bunlar "kod kalitesi" değil, **modelin bilinçli sınırlarıdır**. Kodda
`NOT_MODELLED` olarak beyanlı oldukları için kullanıcıya görünürler; burada
listelenmelerinin sebebi yol haritasında karşılıklarının olması.

| Borç | Nerede beyanlı | Ölçek | Not |
|---|---|---|---|
| Lüle boyunca P(x) motor sonucunda yayımlanmıyor → FEA iç yüzeye **sabit** Pc uyguluyor | `fea/bridge.py` | M | `nozzle_flow_1d` bu profili üretebiliyor ama motor sözlüğüne konmuyor |
| Katı tanesi için **2B düzlemsel** FEA kipi yok | `fea/__init__.py` — "[V2.7 Aşama C — henüz yok]" | L | Star/finocyl/slotted eksenel simetrik değil |
| `pressurant_sizing` blowdown dalında **gerçek-gaz düzeltmesi yok** (C5) | kampanya kaydı | M | 300 bar'da %5+ hata ölçüldü, kod yazılmadı |
| **A11 tank tek-geometri** | kampanya kaydı | L | En büyük tekil borç; 2.7 kapı ölçütü |
| Kavitasyon dinamiği, off-design pompa/türbin haritası, rotordinamik | `turbopump_sizing.NOT_MODELLED` | XL | NPSH marjı bir *tasarım kuralı karşılaştırmasıdır*, kararlılık hükmü değil |
| Ateşleme kimyası, alev yayılımı, sert ateşleme dinamiği, elektriksel ateşleme zinciri | `igniter_sizing.NOT_MODELLED` (9 madde) | XL | Güvenli pencere sabit-hacim ideal-gaz **sınırıdır**, hüküm değil |
| Gerçek CFD | — | XL | v3/v3.5 |
| Yanma tepkisi modeli (F2'nin ikinci yarısı) | — | XL | Akustik modlar var, tepki fonksiyonu yok |

---

## 11. Süreç borçları

| Borç | Ölçüm | Not |
|---|---|---|
| Motor dosyaları tek sınıfta çok büyük | `liquid_rocket_engine.py` 9 674, `solid_rocket_engine.py` 9 374 satır | `app.py` ile aynı sınıf sorun: paralel çalışmada darboğaz. Bölme, blok üretici metotların (`_*_block`) ayrı karışımlara (mixin) taşınmasıyla başlayabilir |
| `hrma/data/` içinde dört ayrı itici kaynağı | `propellant_database.py`, `propellants_db.py`, `open_source_propellant_api.py`, `web_propellant_api.py` | Hangi kaynağın hangi durumda otorite olduğu kod okumadan anlaşılmıyor |
| Windows arayüz kalemleri doğrulanmadı | `2e2375d` commit başlığı: "Windows'ta DOĞRULANMADI" | macOS'ta yazıldı, Windows'ta görülmedi |
| Isp / ısı-akısı adlandırma tutarsızlığı | kampanya kuyruğu | Aynı büyüklük farklı bloklarda farklı adla geçiyor |

---

## 12. Borç sıralaması — kapatma önerisi

Ölçüt: **kullanıcıya yanlış sayı gösterme riski** > **kapı ölçütünü
engelleme** > **bakım maliyeti**.

| Sıra | Madde | Gerekçe |
|---:|---|---|
| 1 | § 1 arayüz yanma hızı varsayılanı | Kullanıcıya bugün 2,2 kat yanlış yanma süresi gösteriyor |
| 2 | § 3 gimbal bağlaması | 2.7 kapı ölçütü #2'yi tek başına engelliyor; iş S ölçeğinde |
| 3 | § 8 eksik arayüz girdileri | Aynı dikiş sınıfı; Katman A taramasıyla sistematik kapanır |
| 4 | § 6 sürüm dizesi | Proje dosyalarını yanlış künyeliyor, düzeltmesi tek satır |
| 5 | § 2 sabit merkezîleştirme + § 4 ölü kod | Bakım borcu, risksiz |
| 6 | § 9 ablasyon göçü | Fizik doğruluğu; üç motorun aynı anda güncellenmesini ister |
| 7 | § 10 A11 + C5 | Fizik kapsamı; yol haritasının açık kalemleri |
| 8 | § 5 `app.py` + § 11 motor dosyaları | Büyük refactor; hareketli hedef durulunca |

---

## 13. Ölçümü tekrarlama

```bash
# TODO/FIXME (birinci taraf)
grep -rn "TODO\|FIXME" hrma/ --include='*.py' --include='*.js' \
  | grep -v __pycache__ | grep -v vendor

# Düzyazı borç kayıtları
grep -rn "borç\|BORÇ\|MERKEZİLEŞTİRME" hrma/ --include='*.py' | grep -v __pycache__

# Yetim modül taraması — İKİ import biçimini de kapsamak zorunda:
#   from hrma.analysis.X import ...   ve   from hrma.analysis import X
# (Yalnız birincisini arayan bir tarama flight_vehicle, tile_cache ve
#  uq_adapters'ı yanlışlıkla yetim sayar — üçü de ikinci biçimle bağlı.)
# 14 Ağustos 2026 çıktısı: yalnız gimbal_mount
for m in $(ls hrma/analysis/*.py | xargs -n1 basename | sed 's/.py//'); do
  [ "$m" = "__init__" ] && continue
  n=$(grep -rlE "analysis\.$m\b|analysis import ([A-Za-z_]+, )*$m\b" hrma \
      --include='*.py' | grep -v "analysis/$m.py" | grep -v __pycache__ | wc -l)
  [ "$n" -eq 0 ] && echo "YETİM: $m"
done

# Sabit çoğaltması
grep -rn "5.670374419e-8" hrma/ --include='*.py' | grep -v __pycache__

# Arayüz ↔ motor anahtar boşluğu (örnek)
for k in closure_bolt_size closure_bolt_class closure_bolt_count; do
  echo "$k: liquid.html=$(grep -c $k hrma/templates/liquid.html)" \
       "advanced.html=$(grep -c $k hrma/templates/advanced.html)" \
       "sıvı motor=$(grep -c $k hrma/engines/liquid_rocket_engine.py)"
done
```
