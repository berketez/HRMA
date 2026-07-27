<!--HRMA-LANG:en-->
# HRMA v2.6.25 — Field fix

v2.6.2 was unusable on a real machine. This release fixes that, and fixes the
process that let it ship.

## The application did not calculate anything

Every calculation returned `HTTP 403 Cross-origin request rejected`. Hybrid,
solid and liquid alike — the Calculate button did nothing on any engine type.

Root cause: v2.6.2 replaced wildcard CORS with a fixed origin allow-list of
`127.0.0.1:8080`, `localhost:8080`, `127.0.0.1:5000`, `localhost:5000`. But the
desktop launcher scans **ports 8080-8090 for a free one**. If anything already
holds 8080, HRMA starts on 8081, the interface is served from that origin, the
browser attaches `Origin: http://127.0.0.1:8081` to every POST, the list does
not recognise it — and the application's own page is rejected by its own API.

The allow-list is gone. The filter now requires the origin to be a **loopback
address on any port**, which is what "same machine" actually means. A remote
page can never present a loopback origin, and a DNS-rebinding attempt is caught
by a separate `Host` header check. The security properties v2.6.2 added are
unchanged: `evil.example`, LAN addresses and the `null` origin are still
rejected, and read requests are still never blocked by origin.

Why no test caught it: the test shared the code's blind spot. It sent a
hard-coded `Origin: http://127.0.0.1:8080`, which matched the hard-coded list —
the test confirmed the code's own assumption instead of measuring it. The
application had never been exercised on any port other than 8080. There is now
a regression test that walks **every port the launcher can choose**, and a
consistency check that fails if the launcher's range and the filter drift
apart.

## Dock icon was wrong when the app was closed

On macOS 26 (Tahoe) the icon appeared as a small tile inset inside a grey
system tile, while the icon was correct once the app was running.

Tahoe wraps the legacy `.icns` artwork of any bundle that ships no compiled
icon asset in its own rounded tile. Our artwork already drew its own rounded
tile at 80.5% of the canvas, so the result was a tile inside a tile. Measured
against reference applications, the fix is to make the bundle artwork
**full-bleed** and let the system apply the mask; no Xcode toolchain is
required. The running-app icon is supplied separately and stays pre-rounded,
because that code path bypasses the system mask. Windows icons are unaffected
and unchanged — Windows applies no system tile, and full-bleed artwork would
look worse there.

## Release notes now follow the interface language

The update prompt asked "Would you like to update?" in the interface language
but printed the release notes in whatever single language the GitHub release
body happened to use. Release bodies now carry both languages behind
machine-readable markers and the update window shows the matching one. Notes
published before this version have no markers and are shown in full, as before.

## Two wrong numbers found while fixing the red tests

Neither of these produced an error message. They produced answers.

**North and east were swapped in every 6-DOF result.** The v2.6.2 refactor
moved the integration frame to right-handed (east, north, up) but never wrote
the conversion back to the external contract, which is (north, east, up). The
`position` and `velocity` rows therefore left the solver with the north and
east channels exchanged — in the trajectory panel, in exported data, and in the
launch-site latitude/longitude mapping. A twin error on the wind input
(feeding `(north, east, up)` wind against `(east, north, up)` velocity) masked
it in the tests, because two swaps cancel. Coriolis acceleration is added
directly in the integration frame, so the cancellation did not reach it, and
that is what exposed the bug: at 45°N a vertical shot deflects 138.07 m west,
and the solver was reporting that deflection in the north channel.

**The "conservative" pressure-vessel formula was the least conservative one.**
Required wall thickness used the inner-radius thin-wall hoop form, labelled
conservative in the source comment. Compared against the exact Lamé thick-wall
solution at 60 bar, r = 75 mm, 4130 steel: the mean-radius membrane form is
0.010% off, the inner-radius form is 0.99% off — and a wall sized by it reaches
464.5 MPa at proof pressure, above the 460 MPa yield strength. Sizing now uses
the mean-radius form.

## Tests that were red

The v2.6.2 CI run finished red with 17 failing tests; 15 of them reproduced
locally. All are fixed. Besides the two findings above: bolted-joint
finite-life fatigue (the Basquin strength fraction became ultimate-strength
dependent in v2.6.2, shortening predicted life 1.40x — the test anchor was
rederived by hand, the tolerance was not relaxed), the uncertainty mean-shift
contract (split into the deliberately pinned efficiency term and the true
Jensen residual, which is now bounded 10x more tightly than the old single
threshold), a tautological safety factor reaching the PDF report, orphaned
interface dictionary keys, and a CI-only crash where a test guarded itself with
an attribute name that does not exist (`_HAS_B123D` instead of
`BUILD123D_AVAILABLE`), so it never skipped and crashed instead.

## Three hybrid inputs never reached the thermal model

On the hybrid page, **Chamber Material**, **Wall Thickness** and **Include
Cooling Channels** were serialised, sent to the server, and then ignored: the
heat-transfer call hard-coded 4130 steel, 5 mm and no cooling. Selecting
Inconel 718 with an 8 mm wall and radial channels produced exactly the same
numbers as leaving the defaults.

The consequence was not silence, it was a wrong answer. With no cooling path
the coolant-side film coefficient is 25 W/m²K, so the model finds essentially
no way to remove heat, the equilibrium wall temperature pins to the adiabatic
flame temperature, and **every realistic design reported a melting wall** — and
adding cooling to fix it changed nothing on screen.

All three now reach the solver. Selecting channels raises the film coefficient
to the regenerative range and emits a warning stating plainly that the
coefficient is taken from literature and that coolant flow, channel velocity,
pressure drop and boiling margin are not verified here. An unknown material or
an out-of-range thickness now warns instead of silently substituting.

While wiring this: the material selector's own default, `steel_304`, did not
resolve to any record in the material database (the record is named `ss_304`),
so the default selection would have failed the moment it was connected. The
alias was added. The solid and liquid engines were checked for the same
pattern; neither calls the heat-transfer module this way.

## Synthetic data removed from the installer

Both installers were carrying `experimental_data.db`, 79 MB. Its contents are
synthetic: 11 fabricated records (literature-inspired operating points with
generated sinusoid and seeded noise) and 12,096 rows of invented time series.
The layer was retired in v2.5.0 and nothing reads the file — but the packaging
step copied the whole `data/` directory, so it shipped anyway. One of its
tables has a `facility` column, so anyone opening it would reasonably read it
as data from a real test stand. It is now excluded at build time. Real
validation data lives in `hrma/data/validation_records/` and is version
controlled.

## The process that let this ship

v2.6.2 was published **14 minutes after** its CI run reported failure. What was
run instead of the full suite was a 25-check feature gate, which is not the
same thing.

`packaging/release_gate.sh` now enforces, mechanically, before any release:
version consistency across package, changelog, release notes and README; a
clean and pushed working tree; a green CI run **for that exact commit**; the
full test suite; and a live smoke test that starts a real server **on a
non-default port** and performs a hybrid, solid and liquid calculation over
HTTP. The publish script refuses to run if the gate is closed.

<!--HRMA-LANG:tr-->
# HRMA v2.6.25 — Saha düzeltmesi

v2.6.2 gerçek bir makinede kullanılamıyordu. Bu sürüm hem onu hem de o
sürümün çıkmasına izin veren süreci düzeltiyor.

## Uygulama hiçbir hesap yapmıyordu

Her hesap `HTTP 403 Cross-origin request rejected` dönüyordu. Hibrit, katı ve
sıvı fark etmeksizin — Hesapla düğmesi hiçbir motor tipinde çalışmıyordu.

Kök neden: v2.6.2, joker CORS'u kaldırıp yerine sabit bir köken listesi koydu:
`127.0.0.1:8080`, `localhost:8080`, `127.0.0.1:5000`, `localhost:5000`. Oysa
masaüstü başlatıcısı **8080-8090 arasında boş port arıyor**. 8080'i başka bir
şey tutuyorsa HRMA 8081'de başlıyor, arayüz o kökenden servis ediliyor,
tarayıcı her POST'a `Origin: http://127.0.0.1:8081` ekliyor, liste bunu
tanımıyor — ve uygulamanın kendi sayfası kendi API'sinden reddediliyor.

Sabit liste kaldırıldı. Süzgeç artık kökenin **herhangi bir portta geri döngü
adresi** olmasını şart koşuyor; "aynı makine" zaten bu demek. Uzaktaki bir
sayfa asla geri döngü kökeni sunamaz, DNS-rebinding denemesi de ayrı bir
`Host` başlığı denetimine takılır. v2.6.2'nin getirdiği güvenlik özellikleri
korunuyor: `evil.example`, yerel ağ adresleri ve `null` kökeni hâlâ
reddediliyor, okuma istekleri hâlâ köken yüzünden engellenmiyor.

Bunu neden hiçbir test yakalamadı: test, kodun kör noktasını paylaşıyordu.
Sabit `Origin: http://127.0.0.1:8080` gönderiyordu, o da sabit listeyle
eşleşiyordu — yani test ölçüm yapmıyor, kodun kendi varsayımını onaylıyordu.
Uygulama 8080 dışında hiçbir portta hiç denenmemişti. Artık **başlatıcının
seçebileceği her portu** dolaşan bir regresyon testi var; ayrıca başlatıcının
port aralığı ile süzgeç birbirinden ayrışırsa kırılan bir tutarlılık kontrolü
eklendi.

## Uygulama kapalıyken Dock simgesi bozuktu

macOS 26 (Tahoe) üzerinde simge, gri bir sistem karosunun içine gömülmüş
küçük bir karo olarak görünüyordu; uygulama açıkken ise doğruydu.

Tahoe, derlenmiş simge varlığı taşımayan bir uygulamanın eski `.icns` sanatını
kendi yuvarlatılmış karosunun içine alıyor. Bizim sanatımız zaten tuvalin
%80,5'inde kendi yuvarlatılmış karosunu çiziyordu; sonuç karo içinde karo.
Referans uygulamalarla ölçülerek bulunan çözüm, bundle sanatını **tam taşma**
yapıp maskeyi sisteme bırakmak; Xcode araç zinciri gerekmiyor. Uygulama
çalışırken kullanılan simge ayrı bir varlık olarak veriliyor ve önceden
yuvarlatılmış kalıyor, çünkü o kod yolu sistem maskesini atlıyor. Windows
simgeleri etkilenmedi ve değişmedi — Windows sistem karosu uygulamaz, orada
tam taşma daha kötü görünürdü.

## Sürüm notları artık arayüz dilini izliyor

Güncelleme penceresi "Güncellemek ister misiniz?" sorusunu arayüz dilinde
soruyor, hemen altındaki sürüm notunu ise GitHub sürüm gövdesi hangi dilde
yazıldıysa o dilde basıyordu. Sürüm gövdeleri artık iki dili de makine
tarafından okunabilir imlerle taşıyor ve güncelleme penceresi uyanı gösteriyor.
Bu sürümden önce yayımlanmış notlarda im yok; onlar eskisi gibi bütünüyle
gösteriliyor.

## Kırmızı testleri düzeltirken bulunan iki yanlış sayı

İkisi de hata mesajı üretmiyordu. Cevap üretiyorlardı.

**Her 6-DOF sonucunda kuzey ve doğu takas olmuş.** v2.6.2 refaktörü
entegrasyon çerçevesini sağ-elli (doğu, kuzey, yukarı) yaptı ama dış
sözleşmeye (kuzey, doğu, yukarı) geri dönüşü hiç yazmadı. `position` ve
`velocity` satırları çözücüden kuzey ile doğu kanalları yer değişmiş olarak
çıkıyordu — yörünge panelinde, dışa aktarılan veride ve fırlatma sahası
enlem/boylam eşlemesinde. Rüzgâr girdisindeki ikiz hata (`(kuzey, doğu,
yukarı)` rüzgârın `(doğu, kuzey, yukarı)` hıza karşı beslenmesi) bunu
testlerde maskeliyordu, çünkü iki takas birbirini götürür. Coriolis ivmesi
doğrudan entegrasyon çerçevesinde eklendiği için o götürme oraya ulaşmadı ve
hatayı açığa çıkardı: 45°K enlemde dik atış 138,07 m batıya sapar, çözücü ise
bu sapmayı kuzey kanalında raporluyordu.

**Basınç kabında "konservatif" denen formül en az konservatif olanmış.**
Gerekli cidar kalınlığı iç yarıçap ince cidar hoop formunu kullanıyordu ve
kaynak yorumunda konservatif diye niteleniyordu. 60 bar, r = 75 mm, 4130 çeliği
için tam Lamé kalın cidar çözümüyle karşılaştırıldığında: ortalama yarıçap
membran formu %0,010, iç yarıçap formu %0,99 sapıyor — ve onunla boyutlanan
cidar proof basıncında 464,5 MPa'ya ulaşıyor, yani 460 MPa akma dayanımının
üzerine çıkıyor. Boyutlandırma artık ortalama yarıçap formunu kullanıyor.

## Kırmızı olan testler

v2.6.2'nin CI koşusu 17 test kırmızı bitmişti; bunların 15'i yerelde de
düşüyordu. Hepsi düzeltildi. Yukarıdaki iki bulgunun yanı sıra: cıvatalı
bağlantı sonlu ömür yorulması (Basquin dayanım kesri v2.6.2'de kopma
dayanımına bağlandı, öngörülen ömür 1,40 kat kısaldı — test çapası el
hesabıyla yeniden türetildi, tolerans gevşetilmedi), belirsizlik ortalama
kayması sözleşmesi (bilinçli olarak sabitlenen verim terimi ile gerçek Jensen
artığına ayrıldı; artık için sınır eski tek eşikten 10 kat daha sıkı), PDF
raporuna ulaşan totolojik emniyet katsayısı, arayüz sözlüğünde öksüz kalan
anahtarlar ve yalnız CI'da çöken bir test: kendini var olmayan bir bayrak
adıyla korumaya çalışıyordu (`BUILD123D_AVAILABLE` yerine `_HAS_B123D`), bu
yüzden hiç atlanmayıp çöküyordu.

## Hibritte üç girdi termal modele hiç ulaşmıyordu

Hibrit sayfasındaki **Yanma Odası Malzemesi**, **Cidar Kalınlığı** ve
**Soğutma Kanalları** alanları serileştirilip sunucuya gidiyor, sonra göz ardı
ediliyordu: ısı transferi çağrısı 4130 çeliği, 5 mm ve soğutmasız değerlerini
sabit yazıyordu. Inconel 718 + 8 mm cidar + radyal kanal seçmek, varsayılanları
hiç değiştirmemekle birebir aynı sonucu veriyordu.

Sonucu sessiz değildi, yanlıştı. Soğutma yolu olmayınca soğutucu tarafı film
katsayısı 25 W/m²K olur, yani model ısıyı dışarı atacak bir yol bulamaz; denge
cidar sıcaklığı adyabatik alev sıcaklığına yapışır ve **gerçekçi her tasarım
eriyen cidar raporlar** — kullanıcı bunu düzeltmek için soğutma eklediğinde de
ekranda hiçbir şey değişmezdi.

Üçü de artık çözücüye ulaşıyor. Kanal seçildiğinde film katsayısı rejeneratif
aralığa yükselir ve şu açıkça bildirilir: katsayı literatürden alınmıştır;
soğutucu debisi, kanal hızı, basınç düşüşü ve kaynama marjı burada
doğrulanmaz. Tanınmayan malzeme ya da aralık dışı kalınlık artık sessizce
değiştirilmek yerine uyarı verir.

Bunu bağlarken çıktı: malzeme seçicisinin kendi varsayılanı olan `steel_304`
malzeme veritabanındaki hiçbir kayda çözülmüyordu (kaydın adı `ss_304`), yani
bağlantı kurulduğu anda varsayılan seçim hata verecekti. Takma ad eklendi.
Katı ve sıvı motorlar aynı kalıp için denetlendi; ikisi de ısı transferi
modülünü bu şekilde çağırmıyor.

## Kurulum paketinden sentetik veri çıkarıldı

Her iki kurulum paketi de 79 MB'lık `experimental_data.db` dosyasını
taşıyordu. İçeriği sentetiktir: 11 uydurma kayıt (literatürden esinlenilmiş
çalışma noktaları, üretilmiş sinüzoid ve tohumlanmış gürültü) ve 12 096
satır uydurma zaman serisi. Katman v2.5.0'da emekliye ayrılmıştı ve hiçbir
kod dosyayı okumuyor — ama paketleme adımı `data/` dizininin tamamını
kopyaladığı için dosya yine de kullanıcıya gidiyordu. Tablolarından birinde
`facility` (tesis) kolonu var; dosyayı açan biri bunu gerçek bir test
standından gelen veri olarak okur. Artık derleme sırasında dışlanıyor.
Gerçek doğrulama verisi `hrma/data/validation_records/` altında ve sürüm
kontrolünde.

## Bunun çıkmasına izin veren süreç

v2.6.2, CI koşusu başarısız raporunu verdikten **14 dakika sonra**
yayınlanmıştı. Tam takım yerine 25 kontrollük bir özellik kapısı koşturulmuştu;
bu ikisi aynı şey değil.

`packaging/release_gate.sh` artık her yayından önce mekanik olarak şunları
zorunlu kılıyor: paket, changelog, sürüm notu ve README arasında sürüm
tutarlılığı; temiz ve push edilmiş çalışma ağacı; **tam o commit için** yeşil
bir CI koşusu; tam test takımı; ve gerçek bir sunucuyu **varsayılan olmayan bir
portta** ayağa kaldırıp HTTP üzerinden hibrit, katı ve sıvı hesap yaptıran
canlı bir duman testi. Kapı kapalıysa yayın betiği çalışmayı reddediyor.
