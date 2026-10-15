# Tarayıcı denetim iskelesi (`tools/browser_harness/`)

Arayüzü **gerçek bir tarayıcıda** gezip görsel kusurları makinece yakalar.
Birim testlerinin göremediği kusur sınıfı içindir: boş kalan 3B tuval,
çizilmeyen egzoz, konsola düşen hata, ekrana sızan `[object Object]`,
düğmesine basılınca hiçbir şey çizmeyen FEA paneli.

Faz 6'da bu gezinti **elle** yapıldı ve bulunanların çoğu hiçbir testin
kapsamadığı yerdeydi. Bu paket aynı gezintiyi depoya kalıcı bir araca
çevirir; her sürümde tek komutla koşar ve hükmünü JSON rapora yazar.

---

## Kurulum

Playwright ve bir Chromium yapısı gerekir. **`requirements.txt` /
`requirements-dev.txt` içinde değildir** — iskele isteğe bağlı bir araçtır,
kurulu değilse `run_tour.py` açık bir hata verip durur, sessizce geçmez.

```bash
pip install playwright
python -m playwright install chromium   # paketli Chromium'u indirir
```

Paketli Chromium indirilemiyorsa iskele sistemdeki Chrome/Edge'e düşer
(`--channel auto`, varsayılan). Hangi yapının kullanıldığı raporun
`tarayici` alanında yazar.

Piksel ölçümü `Pillow` ve `numpy` kullanır; ikisi de `requirements.txt`
içinde zaten var.

---

## Kullanım

```bash
# En sade hâli: uygulamayı kendisi başlatır, gezer, öldürür
python tools/browser_harness/run_tour.py --out /tmp/tur

# Tek sayfa
python tools/browser_harness/run_tour.py --pages hybrid --out /tmp/tur

# Zaten çalışan bir sunucuya bağlan (bu durumda sunucu ÖLDÜRÜLMEZ)
python tools/browser_harness/run_tour.py --out /tmp/tur \
    --base-url http://127.0.0.1:8080

# Tarayıcıyı görünür pencerede aç (elle izlemek için)
python tools/browser_harness/run_tour.py --out /tmp/tur --headed
```

| Argüman | Anlamı |
|---|---|
| `--pages` | Virgülle ayrılmış sayfa listesi. Varsayılan `hybrid,solid,liquid,index,formulas,launch-site` (ÖH D21 / P17B1-16: üç HESAPLI motor sayfası + ürünün üç HESAPSIZ sayfası). Bilinmeyen ad **hata** verir (sessizce atlanmaz). |

**Hesaplı ⟷ hesapsız sayfa.** `sayfalar.Sayfa.hesap_var=False` olan sayfalarda (`/`, `/formulas`, `/launch-site`) hesap düğmesi, 3B sahne, FEA paneli ve Analiz Merkezi YOKTUR; tur bunları aramaz ve o sayfalar için tuval/egzoz/Merkez denetimi **üretmez** — hayalet denetim, kusuru olmayan sayfayı kırmızıya boyar. Geriye kullanıcının o sayfada gerçekten maruz kaldığı dört ölçüm kalır: konsol hatası, ekrana sızan iç değer, yerleşim taşması/örtüşmesi ve tam sayfa görüntüsünün sahte olup olmadığı.
| `--out` | Zorunlu. Rapor ve ekran görüntüleri buraya yazılır. |
| `--base-url` | Verilmezse `python -m hrma.run` alt süreç olarak başlatılır; boş bir port seçilir ve tur nasıl biterse bitsin süreç **öldürülür**. |
| `--headed` | Tarayıcıyı görünür açar. |
| `--channel` | `auto` (varsayılan) / `chrome` / `msedge` / boş kanal. |

**Çıkış kodu:** bütün denetimler geçerse `0`, herhangi biri kalırsa `1`,
argüman/sunucu hatasında `2`.

### Sayfa başına ne yapılır

1. Sayfa açılır, ağ sessizliği beklenir.
2. Hesap düğmesine basılır (`onclick` seçicisiyle — arayüz dili değişince
   kör kalmasın diye görünen metne bakılmaz).
3. Sayfanın kendi sonuç nesnesi (`window.currentResults`) dolana kadar
   beklenir. "Ekranda bir şeyler belirdi" yeterli sayılmaz.
4. 3B sahne kendiliğinden kurulmuyorsa açma düğmesine basılır
   (katıda `show3DVisualization()`).
5. Yanma başlatılır: önce **gerçek arayüz düğmesi** (`button.viz-play`),
   olmazsa `MotorViz3D.get().play()`. Hangi yolun kullanıldığı rapora
   yazılır (`olcumler.plume_baslatma`).
6. 3B ölçüm alınır ve `<sayfa>_3b.png` yazılır (tuvalin kendisi).
7. Sayfanın **FEA panelleri** koşturulur (aşağıda). FEA, 3B ölçümden
   SONRA gelir: koşum sayfaya büyük çizim kapları ekleyip düzeni
   değiştirir, tuval anlık görüntüsü ondan etkilenmesin.
8. **Analiz Merkezi** ölçülür ve kiracıları koşturulur (aşağıda). Merkez
   FEA'dan sonra gelir; koşum GERÇEKTİR ve sayfa başına **bir kez**
   yapılır (CFD 'coarse' seviyesinde ~2-11 s).
9. Sayfa metni okunur ve `<sayfa>_tam.png` (tam sayfa) yazılır. Metin FEA
   ve Merkez koşumundan sonra okunduğu için sızıntı taraması ikisinin de
   bastığı metni kapsar.

---

## Denetimler

| Ad | Sorusu | Doğrudan dayanağı |
|---|---|---|
| `akis_tamam` | Gezinti kesintiye uğradı mı? | Adımların istisna kaydı |
| `tuval_dolu` | 3B tuval boş mu? | `MotorViz3D.snapshot()` PNG'sinin piksel analizi |
| `plume_cizildi` | Egzoz çiziliyor mu? | `_plume.geometry.drawRange.count` |
| `konsol_temiz` | Konsolda hata var mı? | Playwright `console` + `pageerror` |
| `sizinti_yok` | Ekrana iç değer sızmış mı? | `document.body.innerText` taraması |
| `fea_<panel>_kosum` | Koşum bitti mi, sonuç yayımlandı mı? | `window.<API>.payload` |
| `fea_<panel>_cizim` | Beklenen çizimler ekranda mı? | Kap görünürlüğü + `.js-plotly-plot` + kaptaki `svg`/`canvas` |
| `fea_<panel>_rozet` | Beklenen hüküm basıldı mı, eski kusur geri geldi mi? | `#<panel>_badges` içindeki `[data-badge]` metinleri |
| `fea_<panel>_yuk_caprazi` | Ekran, yükü gösteriyor mu? Hüküm rozetlerinin sayısı ve rengi payload ile tutuyor mu? | `yuk_ozeti` (payload'ın skaler/hüküm blokları) ⟷ rozet metni + `data-badge` rengi |
| `yerlesim_yatay_tasma` | Sayfa görüntü alanını yatay aşıyor mu? | `documentElement.scrollWidth − clientWidth` |
| `yerlesim_metin_ortusmesi` | Görünür metinler üst üste binmiş mi? | Metin yapraklarının `getBoundingClientRect` kutuları (ata-torun ve çizim kapları hariç) |
| `merkez_cerceve` | Analiz Merkezi kurulu mu, gri satırların nedeni yazılı mı? | `#analysisCenter` + üç sütun + `[data-ac-row]` durum/neden öznitelikleri |
| `merkez_<kiraci>_kosum` | Kiracının koşumu koştu mu, yanıt bloğu geldi mi? | `AnalysisCenter.history()` son kaydı |
| `merkez_<kiraci>_cizim` | Kiracının çizimleri ekranda mı? | `#ac_view_root` içindeki kapların görünürlüğü + `.js-plotly-plot` + `svg` |
| `merkez_<kiraci>_rozet` | Beyanlar basıldı mı, renkler dürüst mü, emekli imza döndü mü? | `[data-cfd-badge]` metni + renk sınıfı + yükün kendi alanları |

Sayfa başına: 5 temel + 2 yerleşim + FEA paneli başına 4 (yük çaprazı
yalnız yük yayımlanmışken üretilir) + Merkez çerçevesi 1 + kiracı başına 3.
Bugünkü toplam **49 denetim** (hibrit 19, katı 15, sıvı 15).

**ÖH Faz 0 genişlemesi (P17 savcı reçetesi, 26 Ağu 2026).** P17'nin
ölçtüğü boşluk: tur FEA yükünün yalnız VARLIĞINI kaydediyordu, hüküm
rozetini silmek/sayısını bozmak/yeşile çevirmek 87 mutasyonun 80'inde
turdan geçiyordu (%8 ayırt edicilik). Üç ekleme bunu kapatır:

* **Hüküm imzaları (Kural B):** SF, malzeme sınırı ve gerinim marjı hüküm
  aileleri artık beklenen imza — rozeti SİLMEK imza katmanında yakalanır.
* **Rozet ⟷ yük çaprazı (Kural D, fail-closed):** tur artık payload'ın
  skaler/hüküm bloklarını da kaydeder (`yuk_ozeti`); hüküm rozetlerinin
  sayısı ve rengi Python tarafında BAĞIMSIZ türetilip ekranla çaprazlanır
  (savcı ölçümü: ayırt edicilik %90,8; 29 dürüst değişimde 0 yanlış
  alarm — `raw/P17/S1-olcum-04.py`). Yük içeriği kaydedilmemişse kapı
  KAPANIR: "kanal var kapı yok" desenine izin yok. Dürüst kırmızı GEÇER —
  kural fiziği değil arayüzü cezalandırır (C adayının reddi: S1-olcum-03).
* **Yerleşim denetimleri:** yatay taşma (P17B1-19'un bekçisi) + görünür
  metin örtüşmesi ("iç içe geçmiş ekran" sınıfının makine bekçisi).

Mutasyon kanıtları: `tests/test_gorsel_kapi_faz0.py` (sil / sayı boz /
yeşile çevir kırmızı; dürüst değişim yeşil).

Eşiklerin tamamı **tek dosyadadır**: `esikler.py`. Her sabitin yanında
neden o değer olduğu yazılıdır ve **rapora da kopyalanır** (`esikler`
alanı), böylece eski bir rapor eşik değişse bile doğru yorumlanır.

### `tuval_dolu`

İki ölçüt birlikte sorulur:

* **doluluk oranı** — çizilmiş piksel / toplam piksel (eşik %2).
  Arka planın ne olduğu görüntüden çıkarılır: WebGL bağlamı `alpha: true`
  ile kurulduğu için çizilmemiş alan alfa = 0'dır; tuval tamamen opaksa
  (Plotly yedeği) "en sık geçen renk" arka plan sayılır.
* **içerik entropisi** — dolu piksellerin parlaklık dağılımının Shannon
  entropisi (eşik 1 bit). Tek başına doluluk yetmez: düz renkli bir yer
  tutucu dikdörtgen de tuvali doldurur, ama entropisi 0'dır.

### `plume_cizildi`

Doğrudan ölçüt `drawRange.count`'tur. `_buildPlume` bu aralığı 0'dan
başlatır ve `_updatePlume` **yalnız çözücü nozul çıkış durumunu verdiyse**
büyütür (`motor_viz3d.js`). Yani **0 = egzoz hiç çizilmiyor**.

Aralık 0 çıktığında rapor gerekçeyi de yazar:

* `_plumeInfo` yok → çözücünün nozul çıkış durumu sahneye ulaşmamış.
  Çizimin atlanması burada **bilinçlidir** (uydurma alev yasağı); kusur
  çizimde değil, veriyi oraya taşıyan kanaldadır. Denetim yine de **KALIR** —
  kullanıcı ekranda egzoz görmüyorsa sonuç aynıdır.
* yanma duraklamış / plume anahtarı kapalı → ayrı gerekçe yazılır.

`MotorViz3D`'ye hiç erişilemezse (Three.js yok, WebGL yok, sahne kurulmadı)
tuvaldeki parlak piksel oranı **vekil** ölçüt olarak kullanılır ve hüküm
`kesinlik: "dolayli"` işaretlenir. Rapor bunu gizlemez.

---

## FEA panelleri

Bu tur, FEA panellerinin **ürün turunu** yapar: düğmeye basar, koşumun
bitmesini bekler, çizimlerin ekrana geldiğini ve rozetlerin doğru hükmü
bastığını ölçer. Faz 4-5'te bu gezinti elle yapılmıştı; buradaki üç
denetim aynı gezintiyi kalıcı hâle getirir.

| Sayfa | Panel | Kimlik | Koşum düğmesi | Beklenen çizimler |
|---|---|---|---|---|
| `/hybrid` | Yapısal (cidar) | `#feaPanel` | `#fea_run` | `fea_plot_vm`, `fea_plot_sf`, `fea_plot_quality`, `fea_plot_conv` |
| `/hybrid` | Termal (geçici) | `#thermalFeaPanel` | `#fea_t_run` | `fea_t_plot_field`, `fea_t_plot_inner`, `fea_t_plot_hist` |
| `/solid` | Tane kesiti | `#grainFeaPanel` | `#grainfea_run` | `grainfea_plot_vm`, `grainfea_plot_bore`, `grainfea_plot_conv` |

| `/liquid` | Yapısal (cidar) | `#feaPanel` | `#fea_run` | hibritteki dört çizimin aynısı |

**Nöbet değişimi (2026-08-15).** `/liquid` sayfasında eskiden FEA denetimi
yoktu: sıvı cidar FEA'sı köşe tekilliği yüzünden yakınsamıyordu. Borç
`mesh_axisym`in dış yüzey eğrilik tabanıyla kapandı ve panel `liquid.html`e
bağlandı; sayfa artık yapısal üçlüyü denetliyor. Termal ve tane panelleri
sıvıya **bilerek** eklenmedi (termal zincir bu sayfada yok, tane katıya
özgü) ve bu, "denetim atlandı" değil "denetlenecek panel yok" demektir.

Termal panelin ortam sıcaklığı alanı `293.15` ön-dolu gelir ve tur ona
**dokunmaz**: denetlenen şey kullanıcının gördüğü varsayılan yoldur.

### Koşum nasıl beklenir

Panelin süresi önceden bilinmez (panelin kendi beyanı da bunu söyler), o
yüzden sabit uyku yoktur. Sıra şudur:

1. Düğmeye basılır.
2. **Meşgul göstergesinin açılması** beklenir (`FEA_BASLAMA_ZAMAN_ASIMI_MS`).
   Açılmazsa koşum muhtemelen hiç başlamamıştır (ör. sayfada motor sonucu
   yok); bu rapora `basladi: false` diye yazılır.
3. **Göstergenin kapanması** beklenir (`FEA_KOSUM_ZAMAN_ASIMI_MS`, termalde
   `FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS`).
4. Panel yeniden okunur.

Hüküm göstergeye değil **panelin kendi sonuç nesnesine** bakar
(`window.FeaPanel.payload` vb.): düğmeye basılıp uç hata döndüğünde de
ekranda bir şey değişir ama çizilecek alan yoktur. Koşum başarısızsa
panelin kendi çipi (`#fea_chip` …) gerekçeyi yazar ve o gerekçe hükmün
içine kopyalanır — "FEA kaldı" tek başına tanı koydurmaz.

### "Çizim var" ne demek

Üç ölçüt **birlikte** sorulur ve üçü de ölçülür:

* kap görünür (`display != none`, kutusu en az `FEA_CIZIM_MIN_KENAR_PX`),
* kap Plotly'nin çizdiği kap (`.js-plotly-plot` sınıfı),
* kabın içinde gerçekten `svg` veya `canvas` düğümü var.

Tek başına hiçbiri yetmez: kap açık kalıp Plotly çizim atabilir, ya da
gizli bir kapta eski çizim durabilir — ikisi de "ekranda" değildir.

### Rozet imzaları

Rozetlerin hepsi aynı `[data-badge]` kabına basılır; hangi rozetin hangi
hükmü taşıdığını yalnız **metni** söyler. Dizge karşılaştırması bu yüzden
burada kaçınılmazdır. Körleşmemesi için iki bağ kurulmuştur
(`esikler.ROZET_IMZALARI`):

* her imza **dil varyantları** taşır (`ACCEPTANCE METRIC` / `KABUL ÖLÇÜTÜ`);
  tur `en-US` ile koşar ama TR arayüzde de kör kalmaz;
* her imza ürünün **sözlük anahtarına** bağlıdır ve
  `tests/test_browser_harness_fea.py` anahtarın EN ve TR karşılığında
  imzanın gerçekten geçtiğini sınar. Rozet metni yeniden yazılırsa tur
  sessizce yeşile dönmez: birim bekçi kırmızı verir.

Aranan imzalar:

| İmza | Nerede | Ne söylüyor |
|---|---|---|
| `mesh_bozulmasi` | yapısal + tane | Alarmı yalnız ölçekli Jacobian sürer (`Jacobian` terimi iki dilde de aynı) |
| `uzamis_elemanlar` | yapısal | Uzama **ayrı ve nötr** rozette; bozulmayla aynı çuvala girmemiş |
| `kabul_olcutu` | tane | Yakınsama hükmü tepe von Mises'in değil **port lif geriniminin** (NASA SP-8073) |
| `tepe_cidar_sicakligi` | termal | Koşumun tek satırlık sonucu ekranda |
| `birlesik_kalite_alarmi` | **YASAK** | Eski birleşik rozet ("… outside the acceptable range"). Ekranda görülürse ayrışma geri alınmış demektir; denetim KALIR |

**Rozetin rengi hükme girmez.** `data-badge` değeri ölçülür ve rapora
yazılır, ama kırmızı bir rozet kapıyı kapatmaz: renk tasarım noktasının
fiziğini anlatır (emniyet katsayısı, yakınsama, erime sınırı), arayüz
kusurunu değil. Ölçülen örnek: termal panelde `EXCEEDS MELTING POINT`
rozeti kırmızıdır (3056 K > 1673 K) — bu motorun sonucudur, panelin
kusuru değil.

---

## Analiz Merkezi ve kiracıları

Merkez (`analysis_center.js`) üç sütunlu bir workbench'tir: **bileşen
ağacı | koşum kartı | sonuç görüntüleyici** + oturum içi koşum geçmişi.
Panellerden farkı, kiracının kendi düğmesi/rozet kabı olmamasıdır: tek bir
`#ac_run` düğmesi ve tek bir `#ac_view_root` kabı vardır, kiracı oraya
çizer. Bugünkü tek canlı kiracı **CFD**'dir (`panels/cfd_panel.js`,
`POST /api/cfd/nozzle`) ve üç sayfada da kayıtlıdır.

| Ne | Nerede | Denetim |
|---|---|---|
| Çerçeve | `#analysisCenter`, `ac_tree`/`ac_card`/`ac_view`, `#ac_history` | `merkez_cerceve` |
| Koşum | `#ac_row_nozzle_flow_cfd` → `#ac_run` → `AnalysisCenter.history()` | `merkez_cfd_kosum` |
| Çizimler | `#ac_view_root` içindeki `cfd_wall_*`, `cfd_field_*`, `cfd_res_*` | `merkez_cfd_cizim` |
| Rozetler | `[data-cfd-badge]` metni + renk sınıfı + yükün kendi alanları | `merkez_cfd_rozet` |

**Çerçeve neyi ölçer.** Tasarımın kural 1'i: uygulanamayan satır
**gizlenmez**, gri durur ve nedeni **adıyla** yazılır. Denetim bunu ölçer:
üç sütun ayakta mı, kiracılı satır `ready` mi, her gri satırın nedeni
yazılı mı, çerçevenin "nedenini adlandırmadı" emniyet ağı ekranda mı
(görünüyorsa bir kiracı beyansız ret vermiş demektir).

**Koşum gerçektir.** Sayfa başına bir kez, panelin kendi varsayılanıyla
(`resolution = coarse`) koşar; tur alanlara **dokunmaz**. Bitiş işareti
`AnalysisCenter.history()` kaydıdır — kayıt hem başarılı hem başarısız
koşumda düşer. İkinci bir dürüst çıkış daha beklenir: zorunlu alan boşsa
`run()` isteği hiç göndermez, meşgul olmaz ve gerekçeyi durum satırına
yazar; bu yakalanmasaydı kusur "takıldı" diye görünürdü.

**Çizim ölçütü burada daha dar.** FEA'da `svg` VEYA `canvas` kabul
edilir; CFD'de **`svg` aranır**, çünkü panelin üç grafiğinin izleri de SVG
üretir (`scatter`, `carpet`, `contourcarpet`). WebGL'e düşmüş bir kap,
çizimin beklenen yoldan çıktığını söyler.

**Rozet denetimi üç şeyi birden sorar** ve üçü de arayüz kusurunu hedefler,
fiziği değil:

1. **Beyan varlığı.** Fizikten bağımsız imzalar ekranda olmalı: yakınsama
   beyanı, ayrılma hükmü, kütle/enerji artığı, çekirdek, şok sensörü,
   sınırlayıcı, süre. Hangi dalın çıktığı (yakınsadı/yakınsamadı,
   ayrıldı/ayrılmadı) tasarım noktasının fiziğidir ve hükme girmez.
2. **Renk dürüstlüğü.** Kabul rengi (yeşil) yalnız oturmuş bir hükme
   verilebilir: `converged=false` iken yakınsama rozeti, köprü
   `judgment_confidence='suspect'` derken "ayrılma yok" rozeti yeşil
   **basılamaz**. Eşiği yayımlanmayan sayılar (kütle/enerji artığı) nötr
   (`info`/`dim`) kalmak zorundadır — uç bir kabul eşiği yayımlamıyor,
   panelin kendi eşiğini uydurması da yasak.
3. **Koşullu beyanlar.** Yanıt `budget_advisory` ya da `suspect`
   taşıyorsa o beyanın rozeti ekranda olmalı; taşımadığı hâlde
   görünüyorsa da kusurdur (beyan yankısı uydurulamaz).

Aranan CFD imzaları: `cfd_yakinsama_hukmu`, `cfd_ayrilma_hukmu`,
`cfd_kutle_artigi`, `cfd_enerji_artigi`, `cfd_cekirdek`, `cfd_sok_sensoru`,
`cfd_sinirlayici`, `cfd_sure`; koşullu olanlar `cfd_butce_uyarisi` ve
`cfd_ayrilma_supheli`; renk kurallarının bağlandığı **dar** imzalar
`cfd_yakinsadi` ve `cfd_ayrilma_yok`.

**Dar imzalar neden negatif bağlam taşır.** İngilizcede `NOT CONVERGED`
dizesi `CONVERGED`i içerir, `NO SEPARATION JUDGEMENT` de `NO SEPARATION`ı.
`haric_varyantlar` olmadan renk kuralı yanlış rozete uygulanır ve
"yakınsamayan koşu yeşil basılmış" hükmü asla ateşlemezdi.

**Yasak imzalar (emekli sözleşme).**

| İmza | Ne söylüyor |
|---|---|
| `cfd_bayat_giris_uyarisi` | Giriş Mach eşiğine (0,15) bakan `INLET ADVISORY` rozeti. Çözücünün giriş BC'si karakteristik biçime çevrilince eşik ölçülen hiçbir şeyi bildirmez oldu ve sağlıklı koşularda turuncu rozet basıyordu. Ekranda görülürse bayat kod geri gelmiş demektir |
| `cfd_bayat_mach_esigi` | Aynı sözleşmenin alan adı (`threshold_mach`). Dilden bağımsızdır ve rozette değil **girdi yankısı tablosunda** döner — bu yüzden tarama panelin görünen metninin tamamı üstünde de yapılır |
| `merkez_beyansiz_neden` | Çerçevenin "uygulanamaz dedi ama nedenini adlandırmadı" emniyet ağı |

Ölçülen (16 Ağu 2026, üç sayfa canlı): hibrit 16592 iterasyonda yakınsadı
(10,3 s, `numba`), bütçe uyarısı **ateşledi** ve yeşil yakınsama rozetiyle
aynı ekranda durdu — "uyarı hüküm değildir" cümlesinin canlı kanıtı. Katı
5183 iterasyon (3,0 s), sıvı 2915 iterasyon (1,6 s) ve sıvıda ayrılma
**öngörüldü** (ıraksak bölgenin %29,1'i). Üçünde de yasak imza yok.

---

## Piksel turu — oluşmuş sayfanın dili, ondalığı ve geometrisi (ÖH D37)

Defter **OH-D33-45** (yüksek): 16 Eylül'de kılavuz ekran karelerinden üç
kusur çıktı ve yukarıdaki denetimlerin hiçbiri görmemişti — yarım çeviri
(anahtar var, Python'un doldurduğu yer tutucunun içeriği İngilizce), aynı
panelde virgül ve nokta ondalık, künye taşması. Üçü de YALNIZ oluşmuş
sayfada görünür. Piksel turu bunları ölçer.

```bash
# Üç motor sayfası × TR/EN × 1440x900/390x844, örnek proje + hesap sonrası
python tools/browser_harness/run_piksel.py --out /tmp/piksel
# Çalışan sunucuya bağlan, tek kombinasyon
python tools/browser_harness/run_piksel.py --out /tmp/piksel \
    --base-url http://127.0.0.1:8191 --pages liquid --langs tr --widths 390
```

Her kombinasyon **temiz** bir tarayıcı bağlamında açılır: dil, sayfa
yüklenmeden önce ürünün kendi `localStorage` anahtarına (`hrma_lang`)
yazılır ve sayfanın gerçekten o dilde açıldığı `I18N.lang`den okunur;
sayfa `?project=<örnek>` ile açılır (`examples/*.hrma`), proje şeridi
projeyi yükler, tur hesabı tetikler ve **yeni** sonuç nesnesini bekler.
`--base-url` verilmezse `HRMA_PROJECTS_DIR` `<out>/projeler` yapılır:
örnek tohumlama kullanıcının gerçek proje dizinine yazmaz.

| Denetim | Sorusu | Kırmızı |
|---|---|---|
| `piksel_dil_safligi` | Görünür metin sayfanın dilinde mi? | TR'de İngilizce cümle imzası: Türkçe harf taşımayan ≥3 ardışık sözcük ve içinde ≥1 İngilizce işlev sözcüğü (the/is/are/with/from/of/to/and/this/was/for, sözcük sınırıyla; Türkçede de sözcük olan 'not' listede DEĞİL — a2). EN'de Türkçe imza: ç/ğ/ı/ö/ş/ü (ve büyükleri — a2'de ç/ö/ü eklendi) taşıyan küçük harfli sözcük ya da ≥2 böyle sözcük; tek, büyük harfli yabancı ad ("Müller") imza değil |
| `piksel_ondalik_tutarliligi` | Ondalık ayracı sayfanın dilinde mi, panelde tek mi? | (1) TR sayfada muaf olmayan TEK bir noktalı ondalık (a2, ana model kararı: hedef 0); (2) bir `.panel`/`.card` içinde (iç kartlar dahil — her kart AYRI grup) hem `\d,\d` hem `\d.\d` ondalık. EN'de virgüllü ondalık sayısı ve uyarı kaplarında 6 anlamlı basamağa dayanan sayılar (OH-D22-02) RAPORLANIR |
| `piksel_oge_tasmasi` | Metin kutusu içeriğinden dar mı? | `scrollWidth > clientWidth + 1`: overflow görünür (`tasan`) ya da gizli ve başlıksız (`kesilen`) |
| `piksel_ebeveyn_asimi` | Metin öğesi ebeveyn kutusunu aşıyor mu? | Ebeveyn kaydırmalı değilken yatay aşım > 1 px |
| `piksel_yatay_kaydirma` | Belge görüntü alanından geniş mi? | `scrollWidth − min(innerWidth, clientWidth) > 2 px` (ana turun toleransı). Suçlular kök ve en derin olarak listelenir; `visibility:hidden` suçlu **DV-TOOLTIP** diye sayılır |

**Ölçüm (`piksel.py::JS_PIKSEL`).** Tek geçişte görünür her metin
BİRİMİ, metin taşıyan blok kutuları, ebeveyn aşımları ve sayfa genişliği
okunur. Dil ve ondalık birimi **blok metnidir** (a2): satır içi olmayan
her öğenin kendi metni + satır içi torunlarının metni, belge sırasıyla —
`<p>The pressure <b>is</b> below <i>the</i> limit</p>` tek cümledir;
satır içi olmayan çocuk, `<br>` ve SVG birimi keser; SVG `<text>` ve
seçili `<select>` etiketi ayrı birimdir. Görünürlük ana turun yerleşim
ölçümüyle aynı ilkededir: `display:none` ve `opacity:0` atlanır, kapalı
`<details>` yalnız özetini gösterir; her metin düğümünün satır kutuları
atalardan gelen kırpma dikdörtgeniyle kesiştirilir (max-height:0
akordeonun ve kaydırmalı kabın görünmeyen satırının metni ölçülmez).
Birim metni `PIKSEL_BIRIM_METIN_UST_SINIRI` karakteri aşarsa kesik sayılır
ve dil/ondalık denetimi fail-closed kalır.
Sayfa kaydırması suçluları kırpan bir ataya (Plotly SVG'si, kaydırmalı
tablo kabı) ya da sabit konuma takılan öğeleri SAYMAZ — onlar belgeyi
kaydırmaz.

**Muafiyet tek yerdedir** (`esikler.py`) ve her girdi gerekçelidir; muaf
metin sessizce düşmez, denetimin ölçümüne ADIYLA sayılır:

* öğe düzeyi (`PIKSEL_MUAF_SECICILER`): `code/pre/kbd/samp`, künye
  sınıfları (TAM ad: `.hd-verdict-kunye`, `.hd-metric-note` — alt dize
  seçicisi YOK, a2), `[data-machine]`,
  açılmış çözücü künyesi (`details[id$=_basis]` gövdesi; `<summary>` muaf
  DEĞİL), `[data-src-field]`;
* metin düzeyi (`DIL_SAFLIGI_MAKINE_BELIRTECLERI`): adres, uzantılı dosya
  adı, yol, alt çizgili alan adı, noktalı nitelik yolu, camelCase;
* ondalık (`ONDALIK_MUAF_DESENLERI`): sürüm, bölüm/tablo/denklem
  numarası, tarih, IP; Plotly'nin TR binlik tiki (`10.000`) `belirsiz_binlik`
  sayılır, ondalık sayılmaz. Form `value=`, SVG öznitelikleri ölçüme hiç
  girmez.
* Geometri denetimleri muafiyet TANIMAZ: künye taşması tam olarak
  OH-D33-44'ün kusuruydu.

**Sözlük yarışı kipi** (`--dict-delay-ms 3000`): `/hybrid` ve `/liquid`
şablonları ortak sözlüğü (`i18n_common.js`) `<script>` ile yüklemez,
`analysis_dock.js` onu dinamik ekler. Sözlük geç kaydolursa JS'in o ana
kadar `T()` ile bastığı metin İngilizce yedekte kalır ve dil değişmediği
için yeniden basılmaz. Kip bu isteği bekletir; aralıklı kusuru her koşumda
görünür kılar (ölçülen: `/hybrid` TR'de `#inj_dp_note` ve enjektör şeması
etiketleri — bkz. `docs/scofield/raw/OH/D37/piksel-bekci/a1/rapor.md`).

Rapor: `<out>/piksel_raporu.json` (kombinasyon başına beş denetim +
`akis_tamam`, ölçülen ağacın commit'i, eşiklerin kopyası). Çıkış kodu
run_tour ile aynı sözleşmededir. **Varsayılan kapı turu bu denetimleri
koşturmaz**; ayrı kiptir (bağlama kararı Faz C / paketleme).

**Sınırlar.** Yalnız ekranda görünen metin ölçülür: kapalı sekme,
üzerine gelinince açılan ipucu balonu, `title`/`placeholder` öznitelikleri
ve PDF dil denetimine girmez. İmza işlev sözcüğüne dayanır: işlev sözcüğü
taşımayan kısa İngilizce etiket ("Chamber Pressure") yakalanmaz. Tur
FEA/Merkez koşumlarını tetiklemez (yalnız hesap sonrası ekran).

---

## Rapor

`<out>/tour_report.json`. Ana alanlar:

```jsonc
{
  "surum": 1,
  "olusturma_utc": "…",
  "temel_url": "http://127.0.0.1:PORT",
  "sunucu":  { "kaynak": "alt_surec|harici", "port": 0, "gunluk": "…/sunucu.log" },
  "tarayici": { "motor": "chromium", "kanal": "chrome", "surum": "…" },
  "esikler":  { "…": "hükmün verildiği andaki eşiklerin kopyası" },
  "sayfalar": [
    {
      "ad": "solid",
      "gecti": false,
      "sureler_s": { "yukleme_s": 0.7, "hesap_s": 0.3 },
      "ekran_goruntuleri": { "tam_sayfa": "…/solid_tam.png", "uc_boyut": "…/solid_3b.png" },
      "olcumler": { "viz": {}, "piksel": {}, "plume_baslatma": "ui", "http_hatalari": [],
                    "fea": { "yapisal": { "yuk_var": true, "kosum_s": 0.14,
                                          "rozetler": [], "cizimler": {} } } },
      "asamalar": ["sayfa açıldı: …", "hesap düğmesine basıldı: …"],
      "denetimler": [
        { "ad": "plume_cizildi", "gecti": false, "ozet": "…",
          "dayanak": "MotorViz3D.get()._plume.geometry.drawRange.count",
          "kesinlik": "dogrudan", "olcum": {}, "esik": {} }
      ]
    }
  ],
  "ozet": { "gecen_sayfa": 2, "kalan_sayfa": 1, "kalan_denetimler": [] },
  "gecti": false
}
```

**Sahte veri yasağı.** Raporda ölçülmemiş sayı yoktur. Her denetim
`dayanak` alanıyla değerin nereden okunduğunu, her ölçüm bloğu `_dayanak`
alt sözlüğüyle her alanın nasıl hesaplandığını söyler. Ölçüm alınamadıysa
denetim **kalır** ve gerekçesi "ölçülemedi" olur — sessizce geçmiş sayılmaz.

---

## Kapıya bağlama (örnek — bağlamayı bu paket yapmaz)

İskele kendi başına bir kapı **değildir**; kapıya bağlamak paketleme
tarafının işidir. Aşağıdaki iki örnek olduğu gibi kullanılabilir.

### `packaging/release_gate.sh` içine bir adım olarak

```bash
# N/M  Tarayıcı denetim turu: 3B tuval, egzoz, konsol, sızıntı
TUR_DIZINI="$(mktemp -d)/browser_tour"
if python3 -c 'import playwright' 2>/dev/null; then
    if python3 tools/browser_harness/run_tour.py \
            --pages hybrid,solid,liquid --out "$TUR_DIZINI"; then
        echo "  N/M  GEÇTİ — tarayıcı turu temiz"
    else
        echo "  N/M  KALDI — ayrıntı: $TUR_DIZINI/tour_report.json"
        KAPI_KAPALI=1
    fi
else
    # Playwright yoksa adım ATLANMAZ, AÇIKÇA eksik sayılır: sessizce
    # "geçti" demek kapının kendisini yalancı yapar.
    echo "  N/M  ATLANDI — playwright kurulu değil (pip install playwright)"
    KAPI_EKSIK=1
fi
```

### CI adımı olarak

```yaml
- name: Tarayıcı denetim turu
  run: |
    pip install playwright
    python -m playwright install --with-deps chromium
    python tools/browser_harness/run_tour.py --out artifacts/browser_tour
- name: Turu artefakt olarak yükle
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: browser-tour
    path: artifacts/browser_tour
```

Ekran görüntüleri kalır kalmaz artefakt olarak saklanmalıdır: "kaldı"
diyen bir rapor, kanıt görüntüsü olmadan tanı koydurmaz.

---

## Bilinen sınırlar

* **Yalnız görünen metin taranır.** `document.body.innerText` kapalı
  sekmelerin içeriğini vermez; kapalı bir sekmedeki `[object Object]`
  sızıntısı bu turda görünmez.
* **Örnek girdiler sayfaların varsayılanlarıdır.** Tur, formu değiştirmeden
  hesabı tetikler; farklı bir tasarım noktasında ortaya çıkan kusurları
  aramaz.
* **`--base-url` verildiğinde sunucu öldürülmez.** Başkasının başlattığı
  süreç başkasının sorumluluğudur.
* **Vekil egzoz ölçütü zayıftır.** `MotorViz3D` erişilemediğinde parlak
  piksel oranına bakılır; parlak bir arka plan yanlış "geçti" üretebilir.
  Bu yüzden hüküm `dolayli` işaretlenir.
* **Tek tarayıcı.** Yalnız Chromium ailesi denenir; Safari/Firefox'a özgü
  WebGL kusurları bu turda görünmez.
* **FEA rozetleri metinden okunur.** Rozetin hangi hüküm olduğunu DOM'da
  metinden başka söyleyen bir işaret yok (`data-badge` yalnız rengi
  taşıyor). İmzalar sözlüğe bağlandı ve iki dilde sınanıyor, ama ürün
  tarafında rozetlere anlamsal bir öznitelik (ör. `data-badge-key`)
  eklenirse bu bağ daha sağlamı ile değiştirilmelidir.
* **FEA süreleri bugünün makinesinde ölçüldü.** Koşumlar 0,1-0,2 s sürüyor
  (uçlar yerelde); zaman aşımları bunun ~1000 katı bir üst sınır olarak
  konuldu. Amaç bugünkü süreyi kilitlemek değil, takılmış bir koşumun turu
  süresiz bekletmesini engellemektir.
* **Merkez'de tek kiracı denetleniyor.** Bugün CFD dışında kayıtlı kiracı
  yok; kalan beş matris satırı gri duruyor ve tur yalnız "nedeni yazılı
  mı" diye soruyor. Satırlar Merkez'e taşındıkça
  `sayfalar.py::MerkezKiracisi` tanımı eklenmelidir, yoksa yeni kiracı
  denetimsiz kalır (tur onu "gri satır" sanmaz — `absent` durumu gerekçe
  taşıdığı sürece yeşil kalır).
* **CFD koşumu turun en uzun adımıdır.** Sayfa başına bir gerçek çözüm
  koşuyor (ölçülen 1,6-10,3 s, `coarse`). Varsayılan `standard`a kayarsa
  süre iki katına çıkar; birim bekçi varsayılanın `coarse` kaldığını
  sınıyor.
* **Merkez'in rozet renkleri hükme GİRER.** FEA'nın tersine: burada renk
  bir kabul beyanıdır (yeşil = "bu hüküm oturmuş"), o yüzden yakınsamayan
  koşuya ya da şüpheli hükme verilmiş yeşil kapıyı kapatır. Sayının
  büyüklüğü yine fiziktir ve hükme girmez.

## Bakım

* Eşik değiştirmek: yalnız `esikler.py`. Modüller ve testler oradan okur.
* Sayfa eklemek: `sayfalar.py::SAYFALAR`. `tests/test_browser_harness.py`
  sayfa kümesinin `tests/support/inventory.py::PAGES` ile aynı kalmasını
  ve yolların `hrma/app.py` yönlendirmelerinde gerçekten var olmasını
  sınar.
* FEA paneli eklemek: `sayfalar.py::FeaPaneli` ile bir tanım yaz ve ilgili
  sayfanın `fea_panelleri` demetine koy — akış, ölçüm ve üç denetim
  kendiliğinden gelir. `tests/test_browser_harness_fea.py` her kimliğin
  panel kaynağında (`id="…"`) gerçekten durduğunu ve panelin
  `window.<API>.payload` kanalını açtığını sınar.
* Merkez kiracısı eklemek: `sayfalar.py::MerkezKiracisi` ile bir tanım yaz
  ve ilgili sayfanın `merkez_kiracilari` demetine koy — satır seçimi,
  koşum, çizim ve rozet denetimi kendiliğinden gelir.
  `tests/test_browser_harness_merkez.py` satır seçicisinin ürünün kimlik
  kuralından (`ac_row_` + `componentId_analysisId`) türediğini ve her
  imzanın sözlükte iki dilde durduğunu sınar.
* Hüküm mantığını değiştirmek: `denetimler.py` — tarayıcı gerektirmeyen
  saf fonksiyonlar, hepsi testte kilitli.
* **Değişikliği kanıtlamak:** bir eşiği/imzayı geçici bozup turun o
  denetimde KALDI dediğini görmek, testin tautoloji olmadığının tek
  kanıtıdır. Kanıt (FEA turu): `FEA_CIZIM_MIN_KENAR_PX` 50 → 2000, termal
  imza `OLMAYAN_ROZET`, yasak imza ekranda duran bir rozete bağlandı → 6
  FEA denetiminden 4'ü kırmızı, koşum denetimleri yeşil kaldı (koşum
  gerçekten olmuştu), eşikler geri alındı.
  Kanıt (Merkez turu, 16 Ağu 2026): (a) canlı sayfaya sahte bir
  `INLET ADVISORY … threshold_mach 0.15` rozeti enjekte edildi →
  `merkez_cfd_rozet` KIRMIZI, iki yasak imza da adıyla raporlandı, diğer
  14 denetim yeşil kaldı; (b) aynı sahte rozet dururken
  `CFD_KIRACISI.yasak_imzalar` boşaltıldı → tur yeşile döndü, yani kırmızıyı
  veren şey listenin kendisiydi; (c) `cfd_kutle_artigi` imzası sözlükte
  olmayan bir metne bağlandı → 12 birim bekçi kırmızı; (d) `converged=false`
  renk kuralı söküldü → `test_yakinsamayan_kosuya_kabul_rengi_yasak`
  kırmızı. Dördü de geri alındı (md5 doğrulandı).
