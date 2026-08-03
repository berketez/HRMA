# Tarayıcı denetim iskelesi (`tools/browser_harness/`)

Arayüzü **gerçek bir tarayıcıda** gezip görsel kusurları makinece yakalar.
Birim testlerinin göremediği kusur sınıfı içindir: boş kalan 3B tuval,
çizilmeyen egzoz, konsola düşen hata, ekrana sızan `[object Object]`.

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
6. Ölçüm alınır, iki ekran görüntüsü yazılır:
   `<sayfa>_tam.png` (tam sayfa) ve `<sayfa>_3b.png` (tuvalin kendisi).

---

## Denetimler

| Ad | Sorusu | Doğrudan dayanağı |
|---|---|---|
| `akis_tamam` | Gezinti kesintiye uğradı mı? | Adımların istisna kaydı |
| `tuval_dolu` | 3B tuval boş mu? | `MotorViz3D.snapshot()` PNG'sinin piksel analizi |
| `plume_cizildi` | Egzoz çiziliyor mu? | `_plume.geometry.drawRange.count` |
| `konsol_temiz` | Konsolda hata var mı? | Playwright `console` + `pageerror` |
| `sizinti_yok` | Ekrana iç değer sızmış mı? | `document.body.innerText` taraması |

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
      "olcumler": { "viz": {}, "piksel": {}, "plume_baslatma": "ui", "http_hatalari": [] },
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

## Bakım

* Eşik değiştirmek: yalnız `esikler.py`. Modüller ve testler oradan okur.
* Sayfa eklemek: `sayfalar.py::SAYFALAR`. `tests/test_browser_harness.py`
  sayfa kümesinin `tests/support/inventory.py::PAGES` ile aynı kalmasını
  ve yolların `hrma/app.py` yönlendirmelerinde gerçekten var olmasını
  sınar.
* Hüküm mantığını değiştirmek: `denetimler.py` — tarayıcı gerektirmeyen
  saf fonksiyonlar, hepsi testte kilitli.
