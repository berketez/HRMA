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
| `--pages` | Virgülle ayrılmış sayfa listesi. Varsayılan `hybrid,solid,liquid`. Bilinmeyen ad **hata** verir (sessizce atlanmaz). |
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
8. Sayfa metni okunur ve `<sayfa>_tam.png` (tam sayfa) yazılır. Metin FEA
   koşumundan sonra okunduğu için sızıntı taraması FEA panellerinin
   bastığı metni de kapsar.

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

`/liquid` sayfasında FEA denetimi **yoktur ve bu bilinçlidir**: sıvı cidar
FEA'sı üründe yok (köşe tekilliği yüzünden koşum yakınsamıyor — bulgu
defterinde gerekçeli açık borç). `sayfalar.py`de boş bir panel listesi
durur; bu "denetim atlandı" değil, "denetlenecek panel yok" demektir.

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
* **Sıvı sayfasında FEA denetimi yok.** Panel üründe olmadığı için; borç
  kapandığında `sayfalar.py::SAYFALAR['liquid'].fea_panelleri` doldurulur.

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
* Hüküm mantığını değiştirmek: `denetimler.py` — tarayıcı gerektirmeyen
  saf fonksiyonlar, hepsi testte kilitli.
* **Değişikliği kanıtlamak:** bir eşiği/imzayı geçici bozup turun o
  denetimde KALDI dediğini görmek, testin tautoloji olmadığının tek
  kanıtıdır. Son kanıt: `FEA_CIZIM_MIN_KENAR_PX` 50 → 2000, termal imza
  `OLMAYAN_ROZET`, yasak imza ekranda duran bir rozete bağlandı → 6 FEA
  denetiminden 4'ü kırmızı, koşum denetimleri yeşil kaldı (koşum gerçekten
  olmuştu), eşikler geri alındı.
