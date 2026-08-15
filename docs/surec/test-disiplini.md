# Test disiplini

**Son güncelleme:** 2026-08-14
**Kapsam:** Test türleri ve hangi hata sınıfını yakaladıkları; "kusuru koruyan
bekçi" kavramı ve ölçülmüş örnekleri; mutasyon denetimi; eşik/taban disiplini;
yeni testin ne zaman yazılacağı; atlama (skip) bütçesi.
**Kapsam dışı:** Testin akışın neresinde yazıldığı (`gelistirme-akisi.md`),
yayın kapılarının test adımları (`surum-ve-yayin.md`), kurulum ve koşum
ayrıntısı (`CONTRIBUTING.md` §2).

---

## 1. Ölçülen durum (2026-08-14)

| Ölçüm | Değer |
|---|---|
| Toplanan test | **6549** |
| Toplama süresi | 52 s |
| Test dosyası (`tests/*.py`) | 219 dosya · 85 788 satır |
| Alt dizinler | `fea/`, `flow/`, `fixtures/`, `support/` |
| `conftest.py` | **yok** (depoda hiç yok) — bu yüzden `PYTHONPATH=.` zorunlu |
| `pytest.importorskip` kullanan dosya | 22 |
| `xfail` geçen satır | 6 |
| Kurulu pytest | 8.3.4 · `pytest-randomly` **kurulu değil** |

```bash
MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/ -q        # tam takım
python3 -m pytest --collect-only -q | tail -3                  # yalnız toplama
```

`pytest.ini` yalnız iki şey yapar ve ikisi de ölçülmüş bir kazadan doğdu:
`testpaths = tests` ve `norecursedirs` ile `packaging/`, `build.noindex`,
`payload`, `libs`, `dist`. Argümansız `pytest` depo kökünden toplamaya
başlayınca **paketlenmiş uygulamanın kendi kütüphanelerine** giriyor, yayın
kapısının 5/8 adımı hüküm vermeden ölüyor ve toplama sırasında yazılan 2724
`__pycache__` dizini imzalı paketin mührünü bozuyordu. Yani testler,
yayınlanacak ikilinin içine yazıp onu geçersiz kılıyordu.

**Sıra bağımsızlığı bugün mekanik olarak sınanmıyor.** `V2.6.26_BITIRME_PLANI`
§9 bunu bir hedef olarak yazmıştı (`-p randomly` dâhil yeşil), ancak ölçüm
sırasında eklenti kurulu değil ve `requirements-dev.txt` içinde de yok. Açık
kalem olarak burada duruyor.

---

## 2. Testin işi

Bu depoda testin işi "kod çalışıyor mu" değil, **iddia doğru mu**. Sınanan
iddia genelde şu üçünden biridir:

1. Bu sayı gerçekten hesaplanıyor mu, yoksa uydurma sabit mi?
2. Bu hüküm kazanıldı mı (`CALCULATED`, `PASS`, `OPTIMIZED`)?
3. İki parça arasındaki sözleşme (ad, birim, sıra, kaynak) tutuyor mu?

Yeni bir kusur bulunduğunda ilk soru "hangi test eklenmeli" değil, **"bu hangi
katmanın göremediği bir şey?"** Cevap "hiçbirinin" ise yeni bir katman
gerekir.

---

## 3. Test türleri ve hangi hatayı yakalarlar

Katman tablosunun kaynağı `docs/BULGU_KAYIT_DEFTERI.md`; burada koşum
tarafındaki karşılıklarıyla birlikte veriliyor.

| Tür | Sorduğu soru | Örnek dosya |
|---|---|---|
| **Birim / fizik** | Formül ve çözücü doğru mu (analitik çözüm, korunum, yayımlanmış motor) | `tests/test_combustion.py`, `tests/fea/` |
| **Bağlama — Katman A** | Arayüzdeki her form alanı bir toplayıcıda okunuyor mu? | `tests/test_field_wiring_layer_a.py` |
| **Bağlama — Katman B** | Payload'daki her anahtar çıktıyı gerçekten değiştiriyor mu? Hiçbir girdiden etkilenmeyen çıktı var mı? | `tests/test_field_wiring_layer_b.py` |
| **Birim (unit) çevrimi** | Panel, çözücünün verdiği değeri doğru birimde okuyor mu? | `tests/test_panel_units_v2626.py` |
| **Dürüstlük** | Hesaplanmamış bir şey hesaplanmış gibi sunuluyor mu? | `test_no_fabrication.py`, `test_safety_honesty.py`, `test_cad_notes_honesty.py`, `test_liquid_manufacturing_honesty.py` |
| **Tutarlılık** | Aynı fiziksel büyüklük iki panelde aynı değeri veriyor mu? | katı / sıvı / CAD tutarlılık bekçileri |
| **Davranış (vaka)** | Belirli bir kusur kendi somut senaryosuyla geri geldi mi? | `tests/test_hybrid_wired_fields_v2626.py` ve kusura özel dosyalar |
| **Ön yüz sözleşmesi** | Şablon/JS ile uç noktanın anahtarları ve dilleri uyuşuyor mu (Node gerektirir) | `tests/test_arayuz_sema_birim.py`, `tests/test_engine_warning_i18n.py` |
| **Paketleme** | Paket imzalı mı, içinde olması gerekenler var mı | `tests/test_packaging_signature.py` |
| **Yönetişim** | İddia dili ve standart atıfları kayıt defteriyle uyumlu mu | `tests/test_faz4_iddia_dili.py` (`tools/iddia_lint.py`'ı çağırır) |
| **Kayıt defteri bekçisi** | Defterin işaret ettiği testler gerçekten var mı | `tests/test_findings_registry.py` |
| **Korelasyon bekçisi** | Gerçek deney istatistiği sessizce kötüleşti mi | `tests/test_correlation_guards.py` |
| **Mutasyon denetimi** | Bekçinin kendisi kırılabiliyor mu | §5 |

**Katman A ile B birbirinin yerine geçmez.** A geçip B kırılabilir (toplayıcı
gönderiyor, çözücü okumuyor), B geçip A kırılabilir (çözücü okuyor, arayüz
göndermiyor). v2.6.25'te ikincisi yaşandı ve HTTP katmanını sınayan her test
"bağlandı" diyordu.

`tools/iddia_lint.py` hem `.pre-commit-config.yaml` içinden hem de test takımı
üzerinden koşar; yani CI'da da çalışır.

---

## 4. Vaka listelemek yerine taramak

`tests/test_no_fabrication.py` 17 **bilinen** vakayı sabitler. Vaka listelemek
yeni uydurmayı yakalamaz. `tests/support/shake.py` vaka listelemez, **tarar**:
her form alanı × her çıktı yaprağı matrisini kurar ve tek ölçümden iki hata
sınıfı çıkarır.

* **Satır hiç değişmiyorsa** o girdi **ölüdür** — kullanıcı değeri giriyor,
  sonuca hiç girmiyor. (Ölçülmüş: v2.5.2'de sıvının 55 girdisi, v2.6.25'te
  hibritin 3 termal alanı, v2.6.26'da katının ~29 alanı.)
* **Sütun hiçbir girdiyle değişmiyorsa** o çıktı **uydurma sabittir**.
  (`strand_burner_tests: 5`, `dimensional_accuracy_percent: 99.5`,
  `$500-800 USD` üç ayrı elle süpürmeden bu şekilde sağ çıkmıştı.)

Ölçüm koşulları (v2.6.26'da ölçüldü): yanıtlar bit düzeyinde deterministik,
Flask `test_client` kullanılır (gerçek sunucu açılmaz), 195 alanlık tam tarama
sıcak önbellekte 53 s.

Yeni bir kusur sınıfı bulunduğunda tercih sırası:

1. **Taranabilir mi?** Tarayıcı yaz — kalıcıdır, yeni vakaları da yakalar.
2. Taranamıyorsa vaka testi yaz — dar, ama hiç yoktan iyi.

### Beyaz liste çürüyemez

Tarayıcıların çoğunda "bu alan bilerek bağlı değil" diyen gerekçeli listeler
var (`DECLARED_UNMODELLED` gibi). İki kuralı vardır:

1. Her girişin bir gerekçesi olmak zorundadır ve gerekçe "sonra bağlarız"
   olamaz — o durumda alan arayüzden kaldırılır.
2. Listedeki alan sonradan bağlanır ya da arayüzden kalkarsa bekçi **kırılır**
   (`test_declared_lists_do_not_rot`). Aksi hâlde liste zamanla anlamını
   yitirir ve gerçekten ölü olan alanı gizlemeye başlar.

---

## 5. Kusuru koruyan bekçi

**Tanım:** Yanlış davranışı "beklenen" ilan ederek onu sözleşmeye çeviren
test. Kırmızı vermez, güven verir, ve kusuru **kalıcı** hâle getirir.

Nasıl oluşur: test, düzeltmeden **sonra** yazılır ve beklenen değer kodun o
anda ürettiği çıktıdan alınır. Kod ne diyorsa test onu onaylar.

### 5.1 Ölçülmüş örnekler

| Bekçi | Neyi kilitliyordu | Nasıl açığa çıktı |
|---|---|---|
| Atalet formülü testi | Yanlış atalet formülünü `rel=1e-12` ile donduruyordu | `CONTRIBUTING.md` §3.4 |
| Metin kontrolü | Asıl cümleyi hiç görmeyen bir alt dize kontrolü | `CONTRIBUTING.md` §3.4 |
| STEP sınır kutusu | Sınır kutusunu içe aktarılmış katıdan değil **STEP metninden** ölçüyordu | `CONTRIBUTING.md` §3.4 |
| `tests/test_v252_injector.py` (T11) | `tank_pressure` yokken `Pc + ΔP`'yi hesaplayıp çubuğa yine "Tank" yazan davranışı beklenen ilan ediyordu. Kullanıcı tanka 30/50/90 bar girerken çubuk üçünde de 24 bar gösteriyordu | Faz 6 tarayıcı denetimi |
| `tests/test_viz_parity.py` | **Aynı kusurun ikinci katmanı**: yalnız `[30.0, 38.5, 8.5]` değerlerine bakıyor, üçüncü çubuğun hâlâ "Tank" yazdığını görmüyordu | Aynı denetim |
| `tests/test_hibrit_baglama_a5a8a2.py` | Astar kalınlığı için `thickness > 0` diyen bekçi, NASA TM-107041'e karşı **~109 kat** fazla tahmini koruyordu | B6 sözleşmesi gözden geçirmesi |

İki ders: (a) değer doğru olsa bile **etiket** yanlış olabilir ve test yalnız
değere bakarsa kusuru kilitler; (b) aynı kusur iki ayrı katmanda iki ayrı
bekçiyle kilitlenebilir.

### 5.2 Nasıl önlenir

1. **Testi düzeltmesiz kodda koş ve kırmızıya düştüğünü gör.** "Bir test"
   değil, **eski davranışta düşen** bir test. Bu, `CONTRIBUTING.md` §3.4'ün de
   tek şartıdır.
2. **Beklenen değeri koddan türetme.** Bağımsız kaynak kullan: analitik çözüm,
   yayımlanmış motor verisi, korunum özdeşliği, ya da çözücünün kendi beyan
   ettiği tolerans.
3. **Sonucu değil sözleşmeyi kilitle.** Depodaki formülasyon:

   > "Üç meşru hüküm vardır ve hangisinin çıkacağı göreve bağlıdır (fikstür
   > motoru değişirse hüküm değişebilir; bekçi sonucu değil sözleşmeyi
   > kilitler)."

   Yani test "kalınlık 3,2 mm" demez; "zarf dışıysa kalınlık **yayımlanmaz**,
   ablasyon varsa kalınlık özdeşliği tutar" der.
4. **Eşiği yanıttan türet.** `tests/test_fea_panel.py` ve
   `tests/test_e_kulvari_pano.py` bunu açıkça yazar: eşik testte elle
   yazılmaz, yanıttan türetilir — böylece eşik ileride ölçümle güncellenirse
   bekçi kusuru kilitlemez.
5. **Şüphedeysen mutasyon denetimi ekle** (§6).

### 5.3 Eski bir bekçinin kusuru koruduğu anlaşılırsa

Test **gevşetilmez, düzeltilir** ve düzeltmenin gerekçesi testin docstring'ine
ölçümle yazılır. Depodaki kalıp:

```
2026-08-03 (Faz 6, T11): bu testin eski hâli kusuru kilitliyordu.
... [ne varsayıyordu, ölçülen gerçek ne] ...
Bu test artık hem değeri hem etiketi sınar — kusur geri gelirse düşer.
```

---

## 6. Mutasyon denetimi

Bekçinin tautoloji olmadığını kanıtlayan test: **düzeltme geri alınırsa bekçi
kırmızıya düşer mi?**

Ölçülmüş kalıp (`tests/test_kati_bogaz_ayrilma.py`): boğaz artık ulaşılan en
büyük yanma alanına göre boyutlandırılıyor. Mutasyon testi boğazı eski ölçüte
(`Ab(0)`) **desteklenen bir kolla** sabitler (`pin_throat_area` — üretim
toleransı Monte Carlo'sunun da kullandığı gerçek bir metot, iç yapıya yama
değil) ve basınç tavanının gerçekten bozulduğunu gösterir.

Aynı dosyada ikinci bir test daha var ve sebebi somut: **sabitleme kanalının
sessizce yutulmadığını** sınar. Sabitleme önce `overrides` sözlüğüyle
denenmiş, hiçbir etkisi olmamıştı; kanal sessizce yutulursa mutasyon testi
"geçer" ama hiçbir şeyi mutasyona uğratmaz.

Ne zaman zorunlu:

* Bekçi bir **tavan/eşik** kilitliyorsa (basınç tavanı, sapma sınırı).
* Bekçi tek bir sayıya bakıyorsa.
* Düzeltme, ölçülen büyük bir sapmayı kapatıyorsa (kat kat hatalar).

Toplu iş bittiğinde kaç bekçinin mutasyonla sınandığı raporlanır; ölçülmüş
örnek: dünya küresi işinde "bekçiler 10/10 mutasyon kırılımıyla sınandı"
(commit `30fa5fa`).

---

## 7. Eşik ve taban disiplini

### 7.1 Kırmızı testi eşik yükselterek yeşile çevirmek yasaktır

Bir test kırıldığında üç meşru yol vardır:

| Durum | Yapılacak |
|---|---|
| Kod yanlış | Kod düzeltilir. Varsayılan yol budur |
| Test yanlış (kusuru koruyordu / yanlış şeyi ölçüyordu) | Test **kanıtla** düzeltilir: docstring'e ölçüm yazılır, gerekiyorsa defter satırı güncellenir |
| Taban bilinçli olarak değişti (veri seti genişledi, model formu değişti) | Taban **açıkça** güncellenir: hash + gerekçe + commit gövdesinde beyan |

Dördüncü bir yol — "toleransı biraz açalım" — yoktur. Commit gövdelerindeki
standart cümle bunun beyanıdır: *"Kırılan mevcut testler hiçbir iddia
gevşetilmeden düzeltildi."*

### 7.2 Dondurulmuş taban örneği: korelasyon bekçileri

`tests/test_correlation_guards.py` gerçek deney korelasyonunun sessizce
kötüleşmesini (ya da şüpheli biçimde ani iyileşmesini) engeller. Beş
mekanizması var:

1. **DB içerik hash'i dondurulur.** Hash değiştiyse "DB mi değişti, fizik mi"
   ayrımı yapılamaz; test tabanın **bilinçli** güncellenmesini ister.
2. **Hücre başına kötüleşme kapısı:** medAPE ve |bias| taban × 1,25 üstüne
   çıkamaz (küçük tabanlar için mutlak pay eklenir).
3. **Fizik tavanları:** hibrit c\* medAPE ≤ %5, sıvı Isp_vac ≤ %5, katı
   burn_rate (in-sample) ≤ %5.
4. **Aşırı-iyileşme uyarısı:** medAPE tabanın yarısının altına inerse test
   kırmaz ama uyarır — ani "mucize" iyileşme çoğu kez döngüselliğin
   (ölçümün tahmine sızmasının) işaretidir.
5. **Kayıt sayısı tabanı:** hücrenin `n` değeri tabanın altına düşemez;
   kayıtlar istatistikten sessizce damlayamaz.

Aynı dosya dürüstlük notları da taşır: katı `burn_rate` hücresi **in-sample**
olduğu için %0,5 medAPE bağımsız tahmin becerisi değil implementasyon
doğrulamasıdır; hibrit `isp` tabanı önceki sürümdekinden **yüksektir** çünkü
eski değer c\* eksiğiyle CF fazlasının birbirini iptal etmesiydi. Taban dürüst
değerden donduruldu.

---

## 8. Atlama (skip) bütçesi

* **STEP/CAD işi:** atlama bütçesi **sıfır**. Ayrıca toplama tabanı var —
  145 test ölçülmüştü, 140'ın altına düşerse "toplama kırılmış olabilir" diye
  kapı kapanır. `xfail` atlama sayılmaz (junit XML ayrımı `type` alanından
  yapılır).
* **Ana takım:** atlananlar bilgi amaçlı envanterlenir ve raporlanır; atlama
  sebebiyle birlikte basılır.
* `pytest.importorskip` yalnız **gerçekten opsiyonel** bağımlılıklar için
  meşrudur (ölçüm: 22 dosya). Örnek: `build123d`/`OCP`, `numpy<2` pini yüzünden
  ana geliştirme ortamında bilerek yok.
* CI ayrıca ortamın kendisini doğrular: numpy pini korunuyor mu, PyYAML ve
  Node gerçekten kurulu mu. Bir bağımlılık eksik olduğu için sessizce atlanan
  test, yeşil görünen bir kör noktadır.

---

## 9. Yeni test ne zaman yazılır

| Durum | Zorunlu test |
|---|---|
| Davranış değişikliği (her türü) | Eski davranışta **kırmızıya düşen** bekçi |
| Yeni kusur kapatıldı | Kusura özel bekçi + `docs/BULGU_KAYIT_DEFTERI.md` satırı |
| Yeni fizik modülü | Doğrulama kümesi: analitik çözüm, yayımlanmış motor verisi ya da korunum kontrolü. Doğrulaması olmayan modül yayımlanmaz |
| Yeni panel / uç nokta | Bağlama (A+B) + birim çevrimi + dürüstlük (veri yoksa ne gösteriyor) |
| Yeni sabit / eşik | Tek kaynaktan geldiğini ve beyanlı olduğunu sınayan test |
| Yeni standart atfı | Önce `docs/STANDART_ATIFLARI.md` kaydı; `iddia_lint` zaten sınar |
| Paketleme değişikliği | İmza + içerik manifesti tarafında karşılığı |

Yazılmayacak test: kodun mevcut çıktısını fotoğraflayan, gerekçesiz sayı
donduran, ya da yalnız "çağrı patlamıyor" diyen test. Bunlar yeşil sayı üretir,
güvence üretmez.

---

## 10. Kısa kontrol listesi

- [ ] Test, düzeltmesiz kodda **kırmızı** görüldü
- [ ] Beklenen değer koddan değil bağımsız kaynaktan türetildi
- [ ] Sonuç değil sözleşme kilitlendi
- [ ] Gerekiyorsa mutasyon denetimi eklendi (ve mutasyon kanalının yutulmadığı
      sınandı)
- [ ] Hiçbir mevcut eşik gevşetilmedi; gevşetildiyse gerekçe ve taban
      güncellemesi commit gövdesinde
- [ ] Yeni atlama eklenmedi (eklendiyse opsiyonel bağımlılık gerekçesiyle)
- [ ] Defter satırı eklendi ve `tests/test_findings_registry.py` yeşil
