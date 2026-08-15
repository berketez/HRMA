# Geliştirme akışı

**Son güncelleme:** 2026-08-14
**Kapsam:** Bir işin baştan sona akışı — bulgunun nereden geldiği, nasıl
ölçüldüğü, nasıl kapandığı, hangi commit'e girdiği; parti/faz düzeni ve paralel
çalışmada dosya sahipliği.
**Kapsam dışı:** Testin nasıl yazılacağı (`test-disiplini.md`), yayın kapıları
(`surum-ve-yayin.md`), tek bir değişikliğin zorunlu adımları
(`kod-degisiklik-proseduru.md`).

Bu belge var olan pratiği tarif eder; yeni bir yöntem önermez. Anlatılan akış
`git log` ve `docs/dev/` çıktılarından okundu.

---

## 1. İşin birimi bulgudur, özellik değil

HRMA'da yapılan işlerin çoğunun adı "şu özelliği ekle" değil, **"şu sayı
yanlış / bu alan bağlı değil / bu hüküm kazanılmamış"**. Depodaki iş kırılımı
da böyle: `docs/BULGU_KAYIT_DEFTERI.md` bir yapılacaklar listesi değil, kusur
geçmişidir.

Bunun pratik sonucu şudur: **iş, bir ölçümle başlar ve bir ölçümle biter.**
Arada yapılan kod değişikliği, iki ölçüm arasındaki farkı açıklamak
zorundadır.

Yeni yetenek eklenirken bile akış aynı kalır, çünkü yeni modülün de bir "önce"
durumu vardır: `docs/YOL_HARITASI_2.7_VE_SONRASI.md` kalemlerinin tamamı
"modül yazılı ama bağlı değil", "beyan 4'e karşı 47", "delik hesaplanıyor ama
çizilmiyor" gibi **ölçülmüş eksiklerdir**.

---

## 2. Bulgu nereden gelir

Ölçülen kaynaklar, son iki sürümün commit'lerinden:

| Kaynak | Örnek | Nasıl işlenir |
|---|---|---|
| **Kullanıcı hata raporu** | Ayberk'in hibrit motorda bulduğu 16 madde (commit `116b4ea`) | Her madde önce **yeniden üretilir**, sonra teşhis edilir. Üç maddede teşhis yanlış çıktı ve asıl kusur başka yerdeydi — kullanıcı belirtiyi doğru, sebebi yanlış bildirebilir |
| **Mekanik tarayıcı** | `tests/support/shake.py` sarsım matrisi; `tools/sabit_tarayici.py` | Tarama listeyi kendi üretir; elle süpürmenin üç kez kaçırdığı sınıf budur |
| **Bağlama haritası** | `tools/wiring_map.py` → `docs/dev/wiring_map_*.html` | "Ölü alan 0, ölçülemedi 0" bir faz kapısıdır (`V2.6.26_BITIRME_PLANI` Faz 3) |
| **Dış denetim raporu** | Codex raporu teyidi (Faz 4, commit `48f2f37`) | Rapor **kanıt değil iddiadır**: her madde `YAPILDI / BASİT / ORTA / BÜYÜK` diye kanıtla sınıflandırılır |
| **Tarayıcıda mühendis denetimi** | Faz 6, 76 bulgu, 8'i ağır (commit `bfc0770`) | Testlerin yapısal olarak göremediği katman: panel çizimi, eksen birimi, 3B geometri |
| **CI / yayın kapısı kırılması** | `d44b7ce` "CI'ı Linux'ta kıran iki platform farkı", `edd69f7` "STEP paketi bekçisi tek ortam varsayıyordu" | Kapının kırılması da bir bulgudur ve aynı akıştan geçer |
| **Bağımsız hakem turu** | Dünya küresi işi: 11 bulgu (commit `30fa5fa`) | Yazan ajan dışında bir göz; bekçiler mutasyonla sınanır |

Ortak nokta: **hiçbir kaynak kendi başına "kapandı" diyemez.** Bunun için
`tools/kusur_teyit.py` ayrıca yazıldı — kusurları kapatan ajanların raporuna
hiç bakmadan, uygulamanın kendi HTTP yanıtından ölçer.

---

## 3. Bir bulgunun yaşam döngüsü

Aşağıdaki yedi adım `docs/BULGU_KAYIT_DEFTERI.md` §"Bir bulgu nasıl kapatılır"
maddesinin uygulanmış hâlidir. Adım 5 atlanırsa kusur **kapanmış sayılmaz**.

### 3.1 Ölç (teşhis)

Kusuru gerçek bir istekle yeniden üret ve sayıyı yaz. Ölçüm tercihen
uygulamanın kendi arayüzünden yapılır (Flask test istemcisi ya da canlı
sunucu), kod okuyarak varılan kanaatten değil.

```bash
# Tipik teşhis: aynı uca iki farklı girdiyle sor, yaprağın kıpırdayıp
# kıpırdamadığına bak.
PYTHONPATH=. python3 tools/sabit_tarayici.py --sayfa solid
PYTHONPATH=. python3 tools/kusur_teyit.py --sayfa liquid
```

"Muhtemelen" ile başlayan bulgu bulgu değildir. Ölçülen sayı bulgunun
kimliğidir ve commit gövdesine girer.

### 3.2 Kök nedeni bul

Belirti değil **sözleşme kırığı** düzeltilir. Bu kod tabanında bulunan ciddi
kusurların neredeyse tamamı aynı sınıftan: iki parça tek başına doğru,
aralarındaki sözleşme yanlış.

Ölçülmüş örnekler:

* Sıvıda `expansion_ratio` sessizce yok sayılıyordu; kök neden ad
  uyuşmazlığıydı — çözücü `nozzle_expansion_ratio` okuyordu (commit `116b4ea`).
* Regresyon oranı sapmasını ölçen uyarı üründe hiç ateşlemiyordu; kapı `a`/`n`
  değerlerinin `None` olmasını bekliyordu, form alanları her istekte dolu
  gidiyordu (aynı commit).
* Aynı fizik sorununda üç motor üç ayrı şey yapıyordu: sıvı uyarıyor, katı
  sessizce itkiyi sıfıra kırpıyor, hibrit hiç kırpmıyordu.

Kök neden bulunmadan yapılan düzeltme, aynı kusurun ikinci çağrı yerinde
hayatta kalmasına izin verir — v2.6.26'da ısı transferi çağrısı boğaz çapını
göndermiyordu, oysa aynı dosyadaki lüle malzemesi çağrısı gönderiyordu.

### 3.3 Düzelt

Düzeltmenin sınırı `kod-degisiklik-proseduru.md`'de. Akış açısından tek kural:
**düzeltme, ölçülen belirtiyi açıklamak zorundadır.** Belirtiyi açıklamayan
düzeltme, yanlış yeri düzelttiğinin işaretidir.

Hesaplanamayan bir şey varsa uydurulmaz; `NOT_MODELLED` / `not_analyzed` /
`_basis` beyanıyla açık edilir. Bu, akışın "düzeltme" adımının meşru bir
sonucudur — kusur kapanmış sayılır çünkü artık yanlış sayı gösterilmiyor.

### 3.4 Yeniden ölç

Aynı ölçüm tekrarlanır ve **önce/sonra yan yana** yazılır. Depodaki commit
gövdeleri bu tabloların kendisidir:

```
aşım +%32/78/95/116 -> %0/-0,1/-0,3/-0,8
6157 nokta / 519 KB -> 201 nokta / 17,8 KB
eps=35'te Isp 7,6 -> 177,54 s, eps=40'ta NaN çökmesi kapandı
```

Önce/sonra sayısı olmayan iş "yapıldı" sayılmaz. Bu kural performans işlerinde
de aynen geçerlidir (`V2.6.26_BITIRME_PLANI` §7.2).

### 3.5 Bekçi yaz

Kusurun **kendisini** yakalayan test. Testin nasıl yazılacağı ve nasıl
doğrulanacağı `test-disiplini.md`'de; akış açısından kural tek cümledir:

> Bekçisi olmayan "kapandı" kaydı, kapandığın kanıtı değil, yalnızca
> iddiasıdır.

Bekçinin gerçekten kırılabildiği, mümkünse **mutasyon denetimiyle** gösterilir
(eski davranış geri getirilir, bekçi kırmızıya düşer).

### 3.6 Deftere işle

`docs/BULGU_KAYIT_DEFTERI.md` tablosuna satır eklenir: kusur + bekçi
(`test_dosyasi.py::test_adi`). Bu satırın doğruluğunu
`tests/test_findings_registry.py` mekanik olarak sınar — bekçi yeniden
adlandırılır ya da silinirse defter sessizce eskimez, test kırılır.

Kapatılamayan ama bilinen kalemler defterin **"Açık borç"** bölümüne gerekçeyle
yazılır. Bu liste kısaltılmak içindir; uzuyorsa bir şey yanlış gidiyordur.

### 3.7 Commit

Commit disiplini §6'da.

---

## 4. Partiler ve fazlar

İşler tek tek değil, **çakışmasız kümeler** hâlinde yürütülür. İki farklı
düzen ölçüldü ve ikisi de kullanımda:

### 4.1 Faz düzeni (büyük kampanya)

`docs/V2.6.26_BITIRME_PLANI.md`: Faz 0-7, her fazın **çıkış kapısı** var ve
kapı ölçülen bir sayıdır, "bitti" beyanı değil.

| Faz | Çıkış kapısı (örnek) |
|---|---|
| 1 — 138 kusurun kapatılması | 138/138 kapalı veya gerekçeli reddedildi; her kalem için önce/sonra ölçüm |
| 3 — Bağlama haritası | Üç sayfada ölü 0, ölçülemedi 0, yankı yalnız beyanlı |
| 5 — Hata avı + performans | Ölçülen açılış/hesap süreleri önce-sonra tabloda |
| 7 — Son hal | Takım yeşil, harita yeşil, denetim raporu temiz |

Bir faz, kapısı geçmeden kapanmaz. Her fazın sonunda commit alınır; geri dönüş
faz düzeyinde mümkündür ve `git diff` okunabilir kalır.

### 4.2 Parti düzeni (sürüm içi ilerleme)

v2.6.27 kampanyası "parti" adı verilen kümelerle ilerledi ve bu doğrudan commit
başlıklarında görünür (`b4c21ef` birinci parti … `30fa5fa` dokuzuncu parti).
Bir parti = birlikte ölçülüp birlikte kapatılan, dosya kümeleri kesişmeyen bir
kalem yığını.

Partiler **elle değil ölçümden** üretilebilir: `tools/kusur_partileri.py` her
kalemin dokunacağı dosya kümesini çıkarır, aynı dosyayı paylaşan kalemleri tek
bileşene toplar, hiçbir dosya iki partide görünmeyecek şekilde dağıtır.

---

## 5. Paralel çalışma: dosya sahipliği

Aynı dosyaya iki yazıcı dokunursa son yazan kazanır ve diğerinin işi
**sessizce kaybolur**. Bu depoda bunun bedeli ölçüldü ve prosedür ona göre
kuruldu (`docs/dev/faz1_ajan_talimati.md`):

1. Her yazıcı yalnız **kendi dosya kümesine** yazar; başka her dosya
   salt-okunurdur.
2. Kümelerin kesişimi boşsa paralel, değilse **sıralı** çalışılır.
3. `hrma/app.py` ve şablonlar tek elden işlenir — en çok değişen ve en çok
   kesişen dosyalardır (ölçüm: `kod-degisiklik-proseduru.md` §3).
4. Kendi kümesi dışında bir değişiklik gerektiğini gören yazıcı **değiştirmez**,
   bildirir; birleştirmeyi tek el yapar.
5. Yazıcının çıktısı kanıtsız kabul edilmez: dosya:satır ya da test adı
   istenir.

Bu kurallar yalnız çok kişili/çok ajanlı çalışma için değil; tek kişi de
paralel dallarda aynı tuzağa düşer.

---

## 6. Commit disiplini

### 6.1 Başlık

Ölçülen üç desen (son 60 commit):

| Desen | Ne zaman | Örnek |
|---|---|---|
| `<sürüm> <sıra> parti: <özet>` | Sürüm içi toplu ilerleme | `2.6.27 dokuzuncu parti: dünya küresi — sRGB, gök küresi (ESO+BSC5P), roket modeli, karo kapısı, hakem kapanışı` |
| `Faz N: <kapı>` | Kampanya fazı | `Faz 5: hata avı — yörüngede 20x hata, süreç öldüren uç, iki 1000x birim hatası` |
| Kusurun kendisi, geçmiş zaman cümlesi | Tek kusurluk commit | `Testler yayınlanacak ikilinin içine yazıyordu`, `macOS paketi ana bağımlılıkları hiç almıyordu` |

Üçüncü desen dikkate değer: başlık "düzeltme yapıldı" demez, **neyin yanlış
olduğunu** söyler. `git log --oneline` böylece kusur geçmişi olarak okunur.

Doğrulanmamış iş başlıkta beyan edilir:
`Windows penceresi: ... (Windows'ta DOĞRULANMADI)`. Bu, doğrulanmamış işi
doğrulanmış gibi göstermemenin commit karşılığıdır.

### 6.2 Gövde

Gövde, §3'teki akışın kanıt dökümüdür. Ölçülen commit'lerde tekrar eden
bölümler:

* **`Ölçülen:`** satırı — önce/sonra sayıları, birimleriyle.
* Teşhisi yanlış çıkan maddeler ayrıca yazılır ("Madde 5 hibritte YOK, katıda
  VAR") — yanlış teşhis de bilgidir.
* Kapatılan her kusur için kök neden tek cümleyle.
* **Doğrulama bölümü:** yeni test dosyaları, mutasyon denetimi yapıldıysa
  sonucu, ve gevşetme olup olmadığı:
  *"Kırılan mevcut testler hiçbir iddia gevşetilmeden düzeltildi."*
* Beyanla sınırlanan (kapatılamayan) kalemler açıkça yazılır.

### 6.3 Ara kayıt etiketleri

Uzun kampanyalarda gün sonu / mola durumları etiketlenir. Ölçülen etiketler:
`wip-A-dalgasi-20260810`, `wip-B-dalgasi-20260811`, `wip-dalga6-20260810`,
`wip-gun-sonu-20260811`, `wip-mola-20260814`. Bir kısmı `git stash` nesnesini
işaret eder (iki ebeveynli), bir kısmı normal commit.

Amaç: yarım kalan iş kaybolmasın ve "nerede kalmıştık" sorusu ölçümle
cevaplansın. Etiket mesajı ne bittiğini ve ne kaldığını yazar:

```
wip: mola çekimi — B dalgası ara durumu (Cantera+termal+sıvı/hibrit ablatif+
B2 örnekleme+hole_pattern tamam; katı bağlama+NPSH kaldı)
```

Bu etiketler yayın etiketi (`v*`) **değildir** ve yayın otomasyonunu
tetiklemez — otomasyon yalnız `v*` desenini dinler (`surum-ve-yayin.md` §4).

---

## 7. Ölçüm araçları

Akışın her adımında elle iş yerine ölçüm aracı tercih edilir. Depoda ölçülen
araçlar:

| Araç | Hangi soruyu cevaplar | Çıktı |
|---|---|---|
| `tools/wiring_map.py` | "Bu sayı nereden geliyor?" / "Bu alan nereye gidiyor?" | `docs/dev/wiring_map_*.html` |
| `tests/support/shake.py` | Hangi girdi ölü, hangi çıktı hiçbir girdiye tepki vermiyor | Test içinden `shake.run(...)` |
| `tools/sabit_tarayici.py` | Şablonda karşılığı olmayan anahtarlar dâhil, sabit kalan yapraklar | `docs/dev/sabit_tarama.json` |
| `tools/sabit_siniflandirma.py` | Sabit yaprağın **neden** sabit olduğu (ızgara / standart / tanım / beyanlı / sınıflandırılmamış) | Sınıflandırma raporu |
| `tools/kusur_teyit.py` | "Kapandı" iddiası doğru mu (rapora bakmadan) | `docs/dev/kusur_teyit.json`, çıkış kodu 2 = açık kusur var |
| `tools/kusur_partileri.py` | Çakışmasız yazma partileri | `docs/dev/kusur_partileri.json` |
| `tools/iddia_lint.py` | Kazanılmamış hüküm ve yanlış standart başlığı | Çıkış kodu 1 = kayıtsız isabet |
| `tools/browser_harness/` | Tarayıcı katmanı (panel, grafik, konsol hatası) | `docs/dev/tarayici_denetimi.md` |

Bu araçların çıktısı `docs/dev/` altında **git ile izlenir**; yani bir ölçümün
ne zaman ve hangi ağaçta alındığı sonradan bulunabilir.

---

## 8. Akışın bilinen kırılma noktaları

Aşağıdakiler bu depoda gerçekten oldu; akış bu yüzden bu hâlde.

| Kırılma | Ne oldu | Akıştaki karşılığı |
|---|---|---|
| Elle süpürme yetmez | Aynı uydurma sabitler **üç ayrı** elle süpürmeden sağ çıktı | Vaka listelemek yerine taramak (§2, `test-disiplini.md` §4) |
| Rapor kanıt sanıldı | Kusuru kapatan ajanların raporu doğru varsayıldı | `tools/kusur_teyit.py` bağımsız ölçüm |
| Alt küme yeşil sanıldı | Yalnız bir dosya koşulup "kapı 25/25" denildi; sürüm kırmızı CI ile çıktı | Tam takım zorunlu (`surum-ve-yayin.md` kapı 5/8) |
| Test kodun kör noktasını paylaştı | Hem uygulama hem test portun 8080 olduğunu varsayıyordu; kullanıcıda 403 | Canlı duman testi varsayılan olmayan portta (kapı 6/8) |
| Bekçi kusuru kilitledi | Test, yanlış davranışı "beklenen" ilan etti | Mutasyon denetimi (`test-disiplini.md` §5) |
| Paralel yazım işi yuttu | Aynı dosyaya iki yazıcı | Ölçümden üretilen çakışmasız partiler (§4.2, §5) |

---

## 9. Kısa kontrol listesi

Bir iş "bitti" denmeden önce:

- [ ] Belirti gerçek bir istekle **yeniden üretildi**, sayı yazıldı
- [ ] Kök neden bulundu (belirti değil sözleşme düzeltildi)
- [ ] Aynı ölçüm tekrarlandı, önce/sonra yan yana
- [ ] Bekçi yazıldı ve **düzeltmesiz kodda kırmızıya düştüğü görüldü**
- [ ] Gerekiyorsa mutasyon denetimi eklendi
- [ ] `docs/BULGU_KAYIT_DEFTERI.md` satırı eklendi
- [ ] Tam takım yeşil (`kod-degisiklik-proseduru.md` §5)
- [ ] Commit gövdesi ölçümleri ve gevşetme yapılmadığını yazıyor
