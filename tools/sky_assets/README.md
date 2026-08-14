# Gök küresi statik varlıkları — kaynak, lisans ve yeniden üretim

Fırlatma sahası küresinin arkasındaki gökyüzü iki dosyaya dayanır. İkisi de
`build_sky_assets.py` tarafından **kaynağından indirilerek** üretilir; elle
düzenlenmez, elle üretilmez.

| Varlık | Boyut | Kaynak | Lisans |
|---|---:|---|---|
| `hrma/static/img/milky_way_eso0932a_4096.webp` | 1 544 398 bayt (1,54 MB) | ESO eso0932a | CC BY 4.0 |
| `hrma/static/data/bsc5p_stars.bin` | 109 160 bayt (109,2 kB) | Yale BSC5 (V/50) | Kamu malı |

## Yeniden üretme

```bash
python3 tools/sky_assets/build_sky_assets.py
```

Ham indirmeler `/tmp/hrma_sky_assets` altında önbelleklenir; **depo içine hiç
yazılmaz**. Başka bir önbellek dizini için `HRMA_SKY_CACHE=/yol/dizin`.

Doğrulama:

```bash
python3 -m pytest tests/test_gokyuzu_varliklari.py -q
```

---

## 1. Samanyolu dokusu

* **Eser:** "The Milky Way panorama" (GigaGalaxy Zoom projesi, eso0932a)
* **Sayfa:** <https://www.eso.org/public/images/eso0932a/>
* **İndirilen dosya:** <https://cdn.eso.org/images/large/eso0932a.jpg>
  (6000×3000, 8 228 817 bayt, HTTP 200, `image/jpeg`)
* **Atıf (ZORUNLU):** `ESO/S. Brunier`
* **Lisans:** Creative Commons Attribution 4.0 International (CC BY 4.0),
  <https://creativecommons.org/licenses/by/4.0/>
  Dayanak: ESO telif politikası
  (<https://www.eso.org/public/outreach/copyright/>) — *"ESO images, videos and
  web texts are released under the Creative Commons Attribution 4.0
  International License"*. Doğrulandı: 2026-08-14.

**Atıf yükümlülüğü:** CC BY 4.0 atıf ister. `ESO/S. Brunier` künyesi bu
dosyada ve üretici betiğin başlığında kayıtlıdır; künyenin kullanıcıya görünen
yüzeyde (kredi/hakkında ekranı) de gösterilmesi bağlayan tarafın işidir.

### Dönüştürme

6000×3000 (zaten tam 2:1) → **4096×2048**, Lanczos yeniden örnekleme,
WebP kalite 80 (`method=6`). Pillow'da WebP desteği yoksa betik JPEG q=85'e
düşer ve dosya adı `.jpg` olur.

İki ölçü de zorunludur:

* **Tam 2:1** — küre UV eşlemesi equirectangular varsayar; oran bozulursa doku
  enlemde kayar. Kaynak 2:1 değilse betik oranı bozmadan ortadan kırpar.
* **İkinin kuvveti kenar** — WebGL1 (three.js r128) POT olmayan dokularda
  mipmap üretemez, dokuyu çalışma anında yeniden ölçekler.

### DİKKAT: doku GALAKTİK koordinatlardadır

Panorama galaktik düzlem yatay olacak şekilde kurulmuştur (ESO sayfasının
kendi ifadesi: *"the Galactic Plane running horizontally through the image"*).
Üretilen dosya üzerinde ölçüldü: en parlak sütun genişliğin %51,9'unda, en
parlak satır yüksekliğin %51,7'sinde — yani **galaktik merkez görüntünün
ortasında**.

Aşağıdaki yıldız katalogu ise **J2000 ekvatoryal** (RA/Dec). İkisi aynı
equirectangular eşlemeyle üst üste konursa **yıldızlar Samanyolu bandına
oturmaz**. Bağlayan tarafın iki seçeneği var:

1. Yıldızları ekvatoryalden galaktiğe döndürmek, ya da
2. Doku küresine sabit bir dönüşüm uygulamak.

Dönüşüm için J2000 galaktik kutup sabitleri (Hipparcos/ESA 1997):

```
kuzey galaktik kutup : RA = 192,85948°   Dec = +27,12825°
kuzey gök kutbunun galaktik boylamı : l = 122,93192°
```

Bu sabitler bu depoda **doğrulandı**: dönüşüm, kataloğun kendi GLON/GLAT
sütunlarıyla (bayt 91-102) 9096 yıldızın tamamında karşılaştırıldı →
ortalama sapma 0,0024°, en büyük sapma 0,068° (kataloğun 2 ondalıklı
yuvarlamasıyla uyumlu). Ayrıca Sgr A* (RA 266,4168°, Dec −29,0078°) bu
dönüşümle l = 359,944°, b = −0,046° veriyor, yani galaktik merkez.

Betik bu dönüşümü **uygulamaz**: ham veriyi ham haliyle verir.

---

## 2. Yıldız katalogu

* **Eser:** Bright Star Catalogue, 5th Revised Ed. (Preliminary Version)
* **Künye:** Hoffleit D., Warren Jr W.H., *The Bright Star Catalogue, 5th
  Revised Ed.*, Astronomical Data Center, NSSDC/ADC (1991).
  Bibcode `1964BS....C......0H`, CDS kataloğu `V/50`.
* **İndirilen dosya:** <http://tdc-www.harvard.edu/catalogs/bsc5.dat.gz>
  (590 228 bayt sıkıştırılmış, 1 704 879 bayt açılmış, HTTP 200)
* **Biçim belgesi:** <http://tdc-www.harvard.edu/catalogs/ybsc5.readme>
* **Lisans:** **Kamu malı.** ADC/CDS astronomi kataloğu; telif kısıtı yoktur.
  Atıf bilimsel nezakettir, hukuki şart değildir.

> Dosya adı `bsc5p_stars.bin` — "BSC5P" HEASARC'ın aynı kataloğa verdiği addır.
> İçerik yukarıdaki Harvard TDC kopyasından (V/50) üretilmiştir.

### Kullanılan sütunlar

`ybsc5.readme` içindeki "Byte-by-byte Description of file: catalog"
bölümünden birebir alındı (1-tabanlı sütun numaraları):

| Sütun | Biçim | Alan | Açıklama |
|---|---|---|---|
| 76-77 | I2 | `RAh` | J2000 sağ açıklık, saat |
| 78-79 | I2 | `RAm` | dakika |
| 80-83 | F4.1 | `RAs` | saniye |
| 84 | A1 | `DE-` | dik açıklık işareti |
| 85-86 | I2 | `DEd` | derece |
| 87-88 | I2 | `DEm` | yay dakikası |
| 89-90 | I2 | `DEs` | yay saniyesi |
| 103-107 | F5.2 | `Vmag` | görsel kadir |

Dönüşüm: `ra_deg = (RAh + RAm/60 + RAs/3600) × 15`,
`dec_deg = işaret × (DEd + DEm/60 + DEs/3600)`.

**Hiza kanıtı:** betik her koşumda HR 2491'i (Sirius) ölçer ve
06h45m08,9s / −16°42′58″ / V = −1,46 (yani RA 101,2871°, Dec −16,7161°)
çıkmazsa üretimi durdurur. Sütunlar kayarsa dosya tam boyutlu ama anlamsız
olurdu; bu denetim onu imkânsız kılar.

### Kaç yıldız var? — ölçülen gerçek

Katalogda **9110** kayıt var. Bunların **14'ü yıldız değil** (1908
derlemesinden kalan nova/galaksi girdileri; numaralandırma korunsun diye
tutulmuşlar) ve konum/kadir alanları boştur. Geriye konumu ve V kadiri
ölçülmüş **9096 yıldız** kalır.

BSC'nin *nominal* sınırı V = 6,5'tir, **ama dosyanın kendisi V = 7,96'ya kadar
yıldız taşır**: V > 6,5 olan 692 gerçek yıldız vardır. Ölçülen dağılım:

| V (yuvarlanmış) | −1 | 0 | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| yıldız | 2 | 8 | 12 | 71 | 192 | 619 | 1943 | 5557 | 686 | 6 |

Bu yüzden **6,5'te kesilmedi**: kesmek katalogu 9096'dan **8404**'e düşürür,
yani ölçülmüş 692 gerçek yıldızı atardı. Kazanç 692 × 12 = 8,1 kB; kayıp
gerçek veri. `VMAG_SINIR = 8.0` (kataloğun en sönük değerinin üstünde), yani
konumu ve kadiri olan her yıldız yazılır. Betik iki sayıyı da koşum günlüğüne
basar.

### İkili biçim (little-endian)

```
ofset  tip          alan
0      4 bayt       sihirli imza: 'BSC1'  (0x42 0x53 0x43 0x31)
4      uint32       N — kayıt sayısı
8      N × 12 bayt  kayıt:
         +0  float32  ra_deg   J2000 sağ açıklık, derece, [0, 360)
         +4  float32  dec_deg  J2000 dik açıklık, derece, [−90, +90]
         +8  float32  vmag     görsel kadir (V), küçük = parlak
```

Toplam boyut = `8 + 12·N`. Başlıkta sürüm alanı **yoktur**; biçim değişirse
sihirli imza `BSC2` olmalıdır ki eski okuyucu sessizce yanlış ayrıştırmasın.

JS tarafı için okuma taslağı:

```js
const dv = new DataView(arrayBuffer);
const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1),
                                  dv.getUint8(2), dv.getUint8(3));
if (magic !== 'BSC1') throw new Error('beklenmeyen yıldız katalogu biçimi');
const n = dv.getUint32(4, true);            // true = little-endian
for (let i = 0; i < n; i++) {
    const o = 8 + 12 * i;
    const raDeg  = dv.getFloat32(o,     true);
    const decDeg = dv.getFloat32(o + 4, true);
    const vmag   = dv.getFloat32(o + 8, true);
}
```

### Üretilen dosyanın ölçülen değerleri

```
yıldız sayısı : 9096
RA            : [0,0800 ; 359,9792] derece
Dec           : [−88,9564 ; +89,2642] derece
V             : [−1,46 ; +7,96] kadir
dosya boyutu  : 109 160 bayt = 8 + 12 × 9096
```

---

## Belirlenimlilik

Aynı girdi → aynı çıktı. Dosyalara zaman damgası, rastgele tohum ya da sözlük
sırası girmez; yıldızlar katalog sırasında (HR numarası) yazılır. İki temiz
koşum bit düzeyinde aynı dosyaları üretti (2026-08-14 doğrulaması).

Doku baytları Pillow/libwebp sürümüne bağlıdır. Aşağıdaki SHA-256 değerleri
**Pillow 10.4.0 / Python 3.12.7 / macOS arm64** ile üretilmiştir; başka bir
Pillow sürümü aynı görüntüyü farklı baytlarla kodlayabilir (görüntü aynı
kalır, özet değişir).

```
25113f645122dbaf3178717f5c604452616cabb55aedb5bab737f6de8880f483  milky_way_eso0932a_4096.webp
d013f166bc0b2326eab86892addbe5f3b67e4452b3f8e9263df6fb587aaeed22  bsc5p_stars.bin
```

`bsc5p_stars.bin` özeti Python sürümünden bağımsızdır (saf `struct.pack`).

## Dürüstlük kuralı

Betik, indirme başarısız olursa **prosedürel yıldız alanı ya da gradyan doku
üretmez**. Yanıtın HTTP kodu, boyutu ve ilk baytları (JPEG/gzip imzası)
denetlenir; biri tutmazsa betik yüksek sesle durur ve yarım dosya bırakmaz.
Aynı biçimde, yıldız sayısı beklenen aralığın ([8500, 9200]) dışına düşerse ya
da Sirius denetimi tutmazsa üretim durdurulur.

## Paketleme

Varlıklar `hrma/` ağacının içinde durduğu için paketleme betiklerinin
(`packaging/build_mac_app.sh`, `packaging/build_win_payload.sh`) mevcut
`rsync -a --exclude='__pycache__' "$SRC/hrma"` satırıyla **kendiliğinden**
pakete girer; ayrı bir kopyalama kuralı gerekmez.

Yayın kapısının 8/8 adımındaki içerik manifesti (`manifest_denetle`,
`packaging/release_gate.sh`) statik dosyaları tek tek saymaz; dizin düzeyinde
denetler (`app/data`, `app/examples`, `launcher.py`, `hrma/app.py`,
`__pycache__`). Bu yüzden manifeste yeni giriş eklenmedi. Eklenen ~1,65 MB,
±%20'lik boyut sapması eşiğinin yanında ihmal edilebilir (DMG 551 MB → %0,3).
