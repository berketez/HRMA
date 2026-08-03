<!--HRMA-LANG:en-->
# HRMA v2.6.26 — Quality release

This release is about numbers that were wrong and screens that said things the
solver never said. Most of the work is repair, not new capability — but the
exhaust plume and the recovery phase are genuinely new physics, not new buttons.

Everything below was measured before and after. Where a number changed, the old
and the new one are both written down.

## Numbers that were wrong

- **Ascent trajectory was off by a factor of 20 for a whole class of vehicles.**
  Any vehicle with a thrust-to-weight ratio below about 2.9 was affected, even
  when launched straight up. Measured at 85° with T/W 2.19: apogee was 13.86 m,
  an independent reference integration gives 286.86 m, and the corrected solver
  gives 286.94 m. At 30° the old code reported a 4.01 m apogee after 1306 s of
  flight and an apogee altitude of −54722 m — below the ground — while the
  endpoint still answered "success". Three separate causes: no check on whether
  the integrator's stop event ever fired, no launch rail, and no ground plane.
- **Solid motor characteristic velocity was 2.89× too low.** The helper button
  returned 508.7 m/s for a propellant whose real value is about 1470 m/s; one
  term in the formula was inverted.
- **Solid motor propellant mass was 3× too high in the form.** The form
  multiplied the full grain length by the grain count while the solver treats
  the entered length as the total stack. The form said 19.833 kg, the solver
  6.611 kg; every export used the solver number.
- **End-of-burn port diameter ignored the inhibitor layout.** When the outer
  surface also burns, the web is consumed from two sides and burnout happens at
  half the web. Burn time already changed (1.80 s → 1.07 s) but the reported
  final port stayed at the grain outer diameter in both cases. It is now
  100.0 mm and 65.0 mm respectively.
- **Two 1000× unit errors.** DXF drawings had no declared unit and came out
  1000× too large; the liquid engine report PDF printed throat and exit
  diameters 1000× too small. A solid-fuel grain was also being drawn into the
  manufacturing drawing of a liquid engine, where no grain exists.
- **The CAD envelope diameter read only the nozzle exit.** On most designs the
  widest point of a nozzle is the convergent inlet, which starts at chamber
  diameter; on motors with a low expansion ratio the envelope therefore came
  out smaller than the part. It reported 162.53 mm where the drawn solid
  measured 168.11 mm. The envelope is now read from the actual maximum radius
  of the inner contour, so it agrees with the solid by construction.
- **Nozzle mass was about 8% low.** The shell was placed on the mid-contour
  (2πrt) while the drawn solid adds wall thickness outward, so a πt² term was
  dropped. Invisible on a thin wall, but once the wall material was connected
  the wall grew to 7.79 mm and the error reached 7.7% — 0.694 kg reported
  against 0.751 kg. The full annulus volume is now used. A sibling test had
  been written against the same wrong formula and was corrected.

## Things that did not work at all

- **STL export could delete the working directory.** The cleanup step called
  `rmtree` on the directory part of the export path; when that path was
  relative, the directory part is `.` — the current working directory. This
  happened three times during development, taking the entire source tree with
  it. Deletion is now confined to a temporary directory this module created
  itself: it must sit under the system temp root and carry the expected prefix.

- **Running two copies of the application at once crashed it.** Both processes
  wrote to the same CEA scratch file. Each process now gets its own data
  directory, and calls are serialised inside a process; cache hits do not take
  the lock.
- **"Fly this site" on the launch site page never worked.** Two functions with
  the same name existed in one scope; the later one won, so eight numeric
  fields were sent as the string "--" and the server refused the request. The
  page showed the error rather than drawing an invented trajectory.
- **The map tile endpoint dropped every response.** An attribution string
  containing an em dash was written into an HTTP header, which is Latin-1 only.
  The server logged "200" and sent nothing; the browser's six connections per
  host filled up and the whole page stopped loading. Measured: 0 bytes after a
  15 s timeout, now 40,586 bytes in 3 ms.
- **The correlation report endpoint killed the process** (a Fortran `ERROR
  STOP` reached the interpreter). Same root cause as the CEA crash above.

## Exhaust plume and recovery

- **The 3D exhaust plume is now derived from the solver's nozzle exit state** —
  exit pressure, ambient pressure, exit Mach, exit velocity and gamma. It
  previously used invented constants, including a particle speed proportional
  to model length times a random number and a pressure ratio of the form
  `(8/ε)^1.15` where neither 8 nor 1.15 had any basis. Shock cell spacing now
  uses the Prandtl–Pack relation `L_s = 1.306 · D_j · √(M_j² − 1)`.
- **No exit state, no flame.** If the solver does not publish an exit
  condition, the plume is not drawn. It used to show a flowing flame anyway.
- **The descent phase can now be given a parachute.** Area, drag coefficient
  and deploy delay are new inputs on the solid page; leaving a field empty
  keeps the solver's own documented assumption and the result is stamped
  "assumed" so the two cases are never confused.

## Screens that said more than the solver did

- **A bar labelled "Tank" never showed tank pressure.** It showed chamber
  pressure plus injector drop. Entering 30, 50 or 90 bar produced the same
  24 bar. The tank pressure now reaches the result and the bar follows it; when
  no tank pressure is given the bar is labelled "Inj. inlet", which is what the
  value actually is.
- The motor cross-section drew grain, liner and case wall from the chamber
  diameter rather than from the entered dimensions, so changing the grain
  diameter changed nothing on screen.
- Risk classification returned LOW for malformed input, because every
  comparison against a non-number is false and no branch was taken. Malformed
  input is now refused with a clear list of the offending fields.
- Endpoints that used to answer 500, hang for minutes, or return JSON the
  browser could not parse now validate their input and refuse it explicitly.

## Verification

- The test suite went from 4351 to **5084 tests**, with one skip and no
  failures. The skipped test is genuinely inapplicable in that process.
- **Front-end guards now run in CI.** Thirty test files verify interface
  contracts by executing JavaScript with Node, and Node was never installed in
  the CI image — so none of them had ever run there. The same pattern hid 47
  STEP export tests, which now run in their own job.
- **Nineteen assumptions embedded in the code were proved formally** in Lean 4
  with Mathlib, with no unproved steps: the lower bound of the area-ratio root
  search, the exact nozzle mass integral, the continuity of the six atmosphere
  layers, and the monotonicity of the cavitation index in vapour pressure.
- **Every screen was audited in a browser** — 164 buttons, 107 analyses and 68
  charts across the four pages. Seventy-six findings were recorded, eight of
  them severe; each closed one is tied to a test that fails if the defect
  returns.

## Packaging

- The three build scripts pointed at a hard-coded directory that no longer
  contained the source; packaging would have copied an empty tree.
- The macOS build died on its first line because it copied a cache directory
  that does not exist in the repository. That directory is an accelerator, not
  an input; it is now optional.
- macOS code signing was repaired; unsigned packages can no longer be built or
  published.

## Security

- Tracebacks and request bodies were removed from error responses.
- Non-numeric input no longer crashes the validator.

## Included

- Three example projects (hybrid, solid, liquid).
- A findings registry that ties every closed defect to the guard test that
  prevents its return.

<!--HRMA-LANG:tr-->
# HRMA v2.6.26 — Kalite sürümü

Bu sürüm, yanlış çıkan sayılar ve çözücünün hiç söylemediği şeyleri söyleyen
ekranlar üzerine. İşin çoğu onarım, yeni yetenek değil — ama egzoz alevi ve iniş
fazı gerçekten yeni fizik, yeni düğme değil.

Aşağıdakilerin hepsi önce ve sonra ölçüldü. Bir sayı değiştiyse eskisi de
yenisi de yazıyor.

## Yanlış çıkan sayılar

- **Tırmanış yörüngesi bütün bir araç sınıfında 20 kat sapıyordu.** İtki/ağırlık
  oranı yaklaşık 2,9'un altındaki her araç etkileniyordu, dik atışta bile.
  85° ve T/W 2,19 ölçümü: apoje 13,86 m çıkıyordu, bağımsız bir referans
  entegrasyonu 286,86 m veriyor, düzeltilmiş çözücü 286,94 m veriyor. 30°'de
  eski kod 1306 saniyelik uçuşun ardından 4,01 m apoje ve −54722 m apoje
  yüksekliği — yer altı — bildiriyor, uç yine de "başarılı" diyordu. Üç ayrı
  sebep: entegratörün durma olayının tetiklenip tetiklenmediği hiç denetlenmiyor,
  fırlatma rayı yok, yer düzlemi kısıtı yok.
- **Katı motorun karakteristik hızı 2,89 kat düşük çıkıyordu.** Yardımcı düğme,
  gerçek değeri yaklaşık 1470 m/s olan bir yakıt için 508,7 m/s döndürüyordu;
  formüldeki bir terim ters alınmıştı.
- **Katı motorun yakıt kütlesi formda 3 kat yüksekti.** Form, tam tane boyunu
  tane sayısıyla çarpıyordu; oysa çözücü girilen boyu toplam yığın boyu kabul
  ediyor. Form 19,833 kg diyordu, çözücü 6,611 kg; bütün dışa aktarımlar
  çözücünün sayısını kullanıyordu.
- **Yanma sonu port çapı inhibitör düzenini yok sayıyordu.** Dış yüzey de
  yanıyorsa web iki cepheden tüketilir ve tükenme yarı web'te olur. Yanma süresi
  zaten değişiyordu (1,80 s → 1,07 s) ama bildirilen son port iki durumda da
  tane dış çapı olarak kalıyordu. Artık sırasıyla 100,0 mm ve 65,0 mm.
- **İki tane 1000 kat birim hatası.** DXF çizimlerinin birimi beyan edilmemişti
  ve 1000 kat büyük çıkıyordu; sıvı motor rapor PDF'i boğaz ve çıkış çapını
  1000 kat küçük basıyordu. Ayrıca sıvı motorun imalat çizimine, orada var
  olmayan bir katı yakıt tanesi çiziliyordu.
- **CAD zarf çapı yalnız lüle çıkışına bakıyordu.** Çoğu tasarımda lülenin en
  geniş yeri konverjan girişidir ve orası kamara çapında başlar; genişleme oranı
  düşük motorlarda zarf bu yüzden parçadan küçük çıkıyordu. 162,53 mm
  bildiriliyordu, çizilen katının gerçeği 168,11 mm idi. Zarf artık iç konturun
  gerçek maksimum yarıçapından okunuyor, yani çizilen katıyla tanım gereği aynı.
- **Lüle kütlesi yaklaşık %8 düşük çıkıyordu.** Kabuk konturun ortasına
  konuyordu (2πrt), oysa çizilen katı cidarı kontura dışarı ekliyor; böylece bir
  πt² terimi düşüyordu. İnce cidarda görünmeyen bu fark, cidar malzemesi
  bağlanıp cidar 7,79 mm'ye çıkınca %7,7'ye ulaştı — 0,751 kg yerine 0,694 kg
  bildiriliyordu. Artık tam halka hacmi kullanılıyor. Kardeş bir test de aynı
  yanlış formüle göre yazılmıştı, o da düzeltildi.

## Hiç çalışmayan şeyler

- **STL dışa aktarımı çalışma dizinini silebiliyordu.** Temizlik adımı, dışa
  aktarım yolunun dizin kısmına `rmtree` çağırıyordu; o yol göreli olduğunda
  dizin kısmı `.` olur — yani çalışma dizininin kendisi. Geliştirme sırasında üç
  kez yaşandı ve kaynak ağacının tamamını götürdü. Silme artık yalnız bu modülün
  kendi ürettiği geçici dizinle sınırlı: hem sistem geçici kökünün altında olmalı
  hem de beklenen öneki taşımalı.

- **Uygulamanın iki kopyasını aynı anda açmak çökertiyordu.** İki süreç de aynı
  CEA geçici dosyasına yazıyordu. Artık her süreç kendi veri dizinini alıyor ve
  çağrılar süreç içinde sıraya giriyor; önbellek isabetleri kilide girmiyor.
- **Fırlatma sahası sayfasındaki "Fly this site" düğmesi hiç çalışmıyordu.** Tek
  kapsamda aynı adı taşıyan iki fonksiyon vardı; sonraki kazandığı için sekiz
  sayısal alan sunucuya "--" dizgesi olarak gidiyor ve istek reddediliyordu.
  Sayfa uydurma bir yörünge çizmek yerine hatayı gösteriyordu.
- **Harita karosu ucu her yanıtı düşürüyordu.** İçinde uzun tire geçen bir atıf
  metni HTTP başlığına yazılıyordu; HTTP başlıkları yalnız Latin-1 taşır. Sunucu
  günlüğe "200" yazıp tek bayt göndermiyordu; tarayıcının host başına altı
  bağlantısı dolunca sayfanın tamamı yüklenmez oluyordu. Ölçüldü: 15 saniyelik
  zaman aşımının sonunda 0 bayt, şimdi 3 milisaniyede 40.586 bayt.
- **Korelasyon raporu ucu süreci öldürüyordu** (bir Fortran `ERROR STOP`
  yorumlayıcıya kadar ulaşıyordu). Kök nedeni yukarıdaki CEA çökmesiyle aynı.

## Egzoz alevi ve iniş

- **3B egzoz alevi artık çözücünün lüle çıkış durumundan türüyor** — çıkış
  basıncı, ortam basıncı, çıkış Mach'ı, çıkış hızı ve gama. Önceden uydurma
  sabitler kullanılıyordu: parçacık hızı model uzunluğu çarpı rastgele bir sayı,
  basınç oranı ise `(8/ε)^1,15` biçimindeydi ve ne 8'in ne de 1,15'in bir
  dayanağı vardı. Şok hücre aralığı artık Prandtl–Pack bağıntısıyla
  hesaplanıyor: `L_s = 1,306 · D_j · √(M_j² − 1)`.
- **Çıkış durumu yoksa alev de yok.** Çözücü bir çıkış koşulu yayımlamıyorsa
  alev hiç çizilmiyor. Eskiden o durumda da akışkan bir alev gösteriliyordu.
- **İniş fazına artık paraşüt verilebiliyor.** Alan, sürükleme katsayısı ve
  açılma gecikmesi katı sayfasında yeni girdiler; boş bırakılan alan çözücünün
  kendi belgelenmiş varsayımını koruyor ve sonuç "varsayım" damgası taşıyor, iki
  durum birbirine karışmıyor.

## Çözücünün söylediğinden fazlasını söyleyen ekranlar

- **"Tank" etiketli çubuk hiçbir zaman tank basıncını göstermiyordu.** Yanma
  odası basıncı artı enjektör düşümünü gösteriyordu. 30, 50 ya da 90 bar girmek
  aynı 24 barı üretiyordu. Tank basıncı artık sonuca ulaşıyor ve çubuk onu
  izliyor; tank basıncı verilmediğinde çubuk "Inj. inlet" diye etiketleniyor,
  çünkü değer gerçekte odur.
- Motor kesiti tane, astar ve kasa cidarını girilen ölçülerden değil oda
  çapından çiziyordu; tane çapını değiştirmek ekranda hiçbir şeyi
  değiştirmiyordu.
- Risk sınıflandırması bozuk girdide LOW dönüyordu, çünkü sayı olmayan bir
  değerle yapılan her karşılaştırma yanlıştır ve hiçbir dala girilmiyordu. Bozuk
  girdi artık hangi alanların hatalı olduğu açıkça listelenerek reddediliyor.
- Eskiden 500 dönen, dakikalarca asılı kalan ya da tarayıcının ayrıştıramadığı
  JSON döndüren uçlar artık girdilerini denetliyor ve açıkça reddediyor.

## Doğrulama

- Test paketi 4351'den **5084 teste** çıktı; bir atlama var, kırık yok. Atlanan
  test o süreçte gerçekten uygulanabilir değil.
- **Ön yüz bekçileri artık CI'da koşuyor.** Otuz test dosyası arayüz
  sözleşmelerini JavaScript'i Node ile çalıştırarak doğruluyor, ama CI
  görüntüsünde Node hiç kurulu değildi — yani hiçbiri orada bir kez bile
  koşmamıştı. Aynı örüntü 47 STEP dışa aktarım testini de gizliyordu; onlar da
  artık kendi işlerinde koşuyor.
- **Koda gömülü on dokuz varsayım biçimsel olarak ispatlandı**: Lean 4 ve
  Mathlib ile, ispatsız adım bırakmadan — alan oranı kök aramasının alt sınırı,
  lüle kütlesi integralinin tam değeri, altı atmosfer katmanının sürekliliği ve
  kavitasyon indisinin buhar basıncına göre kesin azalanlığı.
- **Her ekran tarayıcıda denetlendi** — dört sayfada 164 düğme, 107 analiz ve
  68 grafik. Yetmiş altı bulgu kaydedildi, sekizi ağır; kapatılan her bulgu,
  kusur geri gelirse düşen bir teste bağlandı.

## Paketleme

- Üç derleme betiği, artık kaynağı barındırmayan sabit bir dizini gösteriyordu;
  paketleme boş bir ağaçtan kopyalayacaktı.
- macOS derlemesi ilk satırında ölüyordu, çünkü depoda bulunmayan bir önbellek
  dizinini kopyalıyordu. O dizin bir girdi değil hızlandırıcı; artık isteğe
  bağlı.
- macOS kod imzası onarıldı; imzasız paket artık derlenemiyor ve yayınlanamıyor.

## Güvenlik

- Hata yanıtlarındaki traceback ve istek gövdesi kaldırıldı.
- Sayısal olmayan girdi artık doğrulayıcıyı çökertmiyor.

## Pakete girenler

- Üç örnek proje (hibrit, katı, sıvı).
- Kapatılan her kusuru, geri dönüşünü engelleyen bekçi teste bağlayan bulgu
  kayıt defteri.
