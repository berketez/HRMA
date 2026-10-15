<!--HRMA-LANG:en-->
# HRMA v3.0.0 — validity limits and withheld verdicts

The first release after 2.6.26. The work shown in the application as
"2.6.27 (in development)" ships here; a separate 2.6.27 was never published.
HRMA is a preliminary-design tool, not a flight-qualification tool. In this
release a number is published with its validity limits, and a verdict the
model cannot support is withheld with its reason instead of shown as a pass.

## Engine physics

- One allowable-temperature ladder for thermal safety verdicts: stainless steel
  304/316 1143 → 1073 K, carbon-carbon 2273 → 1920 K. A wall-temperature
  profile without a stated source gets no positive thermal verdict.
- Hybrid: the N₂O liquid inlet state (tank temperature, phase; default
  saturated liquid at 293.15 K) enters the enthalpy balance. Example hybrid:
  chamber temperature −56.1 K, Isp −1.175 %. In saturation mode the tank
  pressure the model uses is shown read-only (example: 55.0 → 50.5 bar).
- Hybrid: a request without a chamber material uses stainless steel 304,
  the material the form shows, instead of 4130 (example hybrid minimum
  structural safety factor 0.836 → 0.232).
- Hybrid injector: one orifice-diameter band (0.5–2.5 mm); a plan that
  misses the target mass flow by more than 5 % is not marked as passing.
- Solid APCP thermochemistry from NASA CEA (flame temperature 3614.8 →
  3399.65 K, c* 1598.2 → 1585.4 m/s); default APCP motor sea-level Isp
  +0.81 %, throat heat flux −2.78 %. The solid page's defaults come from
  the same record (fresh page sea-level Isp 206.14 → 217.60 s).
- Safety: hybrid (in the panel), sugar and black-powder propellants have no
  sourced TNT equivalent, so TNT equivalent, blast and evacuation distances
  are "not evaluated" with the reason instead of an unsourced number. The
  API and the PDF report use the same propellant-class rule as the panel
  (KNDX is no longer counted as composite).
- Structural approvals (end caps, sizing mode, design target, fatigue,
  buckling) are withheld with a reason when the structural model is outside
  its validity range. Numbers stay visible; in 52 measured cases 23 went
  from "SAFE · VERY LOW" to "NOT EVALUATED", no number changed.
- Structural FEA loads the nozzle with the 1D isentropic pressure and the
  closed-end force and checks the force balance; the scope is pressure
  only. Example minimum safety factors: liquid 2.23 → 3.63, hybrid 5.53 →
  9.22, solid 1.03 → 2.19, now given instead of withheld.
- Regenerative cooling: one temperature limit (the allowable temperature,
  not the melting point; copper 1358 → 723 K); cooling inputs come from the
  engine instead of unsourced pre-fills; the liquid chamber wall is sized
  by HRMA (example 5 → 2 mm).

## CAD

- CAD is drawn from the analysis geometry; nine geometry errors found by an
  independent CAD check are fixed (for example a star grain drawn as a plain
  tube, a hybrid nozzle wall of 3 mm in STEP and 7.19 mm in STL).
- Every manufacturing export (STEP, DXF, drawing PDF, STL) is refused when
  the structural safety factor is below 1 or the model is outside its
  validity range; one nozzle-contour check gives a named 422 instead of a
  silent default. Star and finocyl grains are refused with a reason
  instead of being exported as a circular port.
- The nozzle in STEP is a smooth B-spline surface of revolution through the
  same contour points; dimensions are unchanged.

## Map, security, interface

- Detailed offline launch-site map with city and country labels and a
  bundled NASA Blue Marble texture (15.9 MB); listed place names follow
  official Turkish usage; satellite imagery downloads are off until you
  turn them on.
- One 32 MiB request-body limit enforced by the web server before
  buffering, tighter origin gates for side-effecting requests, a stricter
  Content-Security-Policy, and malformed input answered with 400/422
  instead of a server error (automated fuzzing: 456 findings → 0).
- Chart and panel texts follow the interface language; OpenRocket features
  are gathered in one sidebar tab with thrustcurve.org-style motor names.
- Fixed: parallel NASA CEA calls could return silently wrong numbers (5 of
  5 four-thread runs); the calls now share one lock.
- Export endpoints return a named 422 instead of HTTP 500 for a malformed
  nested block (108 of 10,720 measured requests); Turkish mode has no
  leftover English text; the example hybrid's uncertainty run works (a zero
  diameter means auto); the CFD run-time note quotes the matching inviscid
  or viscous table.

## Known limitations

- 2D CFD with back pressure: the outlet also imposes the back pressure on
  reversed-flow cells. Every such shocked case already returns
  "not converged / plateau" with a `suspect` separation verdict; treat the
  exit-region output of these runs as qualitative.
- Supercritical hydrogen: channel sizing applies the 40 m/s liquid-coolant
  velocity target (NASA SP-8087); the result is on the safe side (hotter
  predicted wall). A hydrogen-specific target is planned for 3.1.
- Hybrid TNT equivalent in the API and the PDF report is applied to the
  total propellant mass, not the oxidiser mass (too high, conservative;
  example 5.765 kg vs about 5.05 kg).
- Star and finocyl grains are not exported to CAD; the assembly STL is not a
  closed solid (use STEP).
- Not in this release: 3D CFD/FEA, combusting CFD, modal FEA, detailed CAD
  (injector head, flanges, cooling channels), system parts (turbopump,
  valves, gimbal). Planned for 3.1 and later.

The full list is in `CHANGELOG.md` and in the in-app Release Notes window.

<!--HRMA-LANG:tr-->
# HRMA v3.0.0 — geçerlilik sınırları ve bekletilen hükümler

2.6.26'dan sonraki ilk sürüm. Uygulamada "2.6.27 (geliştirme sürüyor)" diye
gösterilen çalışma bu sürümle çıkar; ayrı bir 2.6.27 hiç yayımlanmadı. HRMA
bir ön tasarım aracıdır, uçuş yeterlilik aracı değildir. Bu sürümde her sayı
geçerlilik sınırıyla yayımlanır; modelin dayanamadığı hüküm "geçti" gibi
gösterilmez, gerekçesiyle bekletilir.

## Motor fiziği

- Isıl güvenlik hükümlerinde tek izin sıcaklığı basamağı: paslanmaz çelik 304/316
  1143 → 1073 K, karbon-karbon 2273 → 1920 K. Kaynağı belirtilmemiş cidar
  sıcaklığı profili olumlu ısıl hüküm almaz.
- Hibrit: N₂O sıvı giriş durumu (tank sıcaklığı, faz; varsayılan 293,15 K'de
  doymuş sıvı) entalpi dengesine girer. Örnek hibrit: oda sıcaklığı
  −56,1 K, Isp −%1,175. Doyma kipinde modelin kullandığı tank basıncı
  salt-okur gösterilir (örnek: 55,0 → 50,5 bar).
- Hibrit: kamara malzemesi vermeyen istek 4130 yerine formun gösterdiği 304
  paslanmaz çeliği kullanır (örnek hibrit en küçük yapısal emniyet katsayısı
  0,836 → 0,232).
- Hibrit enjektör: tek orifis çapı bandı (0,5–2,5 mm); hedef debiyi %5'ten
  fazla kaçıran plan "geçti" almaz.
- Katı APCP termokimyası NASA CEA'dan (alev sıcaklığı 3614,8 → 3399,65 K,
  c* 1598,2 → 1585,4 m/s); varsayılan APCP motoru deniz seviyesi Isp
  +%0,81, boğaz ısı akısı −%2,78. Katı sayfanın varsayılanları aynı
  kayıttan gelir (taze sayfada deniz seviyesi Isp 206,14 → 217,60 s).
- Güvenlik: hibrit (panelde), şeker ve kara barut iticilerinin kaynaklı TNT
  eşdeğeri yok; TNT eşdeğeri, patlama ve tahliye mesafeleri kaynaksız bir
  sayı yerine gerekçesiyle "değerlendirilmedi" olur. API ve PDF raporu
  panelle aynı itici sınıfı kuralını kullanır (KNDX artık kompozit
  sayılmaz).
- Yapısal onaylar (uç kapakları, boyutlandırma kipi, tasarım hedefi,
  yorulma, burkulma) yapısal model geçerlilik aralığının dışındaysa
  gerekçesiyle bekletilir. Sayılar görünür kalır; ölçülen 52 vakanın 23'ü
  "GÜVENLİ · ÇOK DÜŞÜK"ten "DEĞERLENDİRİLMEDİ"ye geçti, hiçbir sayı değişmedi.
- Yapısal FEA nozulu 1B izantropik basınç ve kapalı uç kuvvetiyle yükler,
  kuvvet dengesini denetler; kapsam yalnız basınçtır. Örnek en küçük
  emniyet katsayıları: sıvı 2,23 → 3,63, hibrit 5,53 → 9,22, katı 1,03 →
  2,19; artık bekletilmiyor, veriliyor.
- Rejeneratif soğutma: tek sıcaklık sınırı (erime değil izin sıcaklığı;
  bakır 1358 → 723 K); soğutma girdileri kaynaksız ön-dolgu yerine motordan
  gelir; sıvı kamara cidarını HRMA boyutlandırır (örnek 5 → 2 mm).

## CAD

- CAD analiz geometrisinden çizilir; bağımsız CAD denetiminin bulduğu dokuz
  geometri hatası düzeltildi (örneğin düz boru çizilen yıldız tane, STEP'te
  3 mm STL'de 7,19 mm olan hibrit nozul eti).
- Yapısal emniyet katsayısı 1'in altındaysa ya da model geçerlilik
  aralığının dışındaysa her imalat çıktısı (STEP, DXF, çizim PDF'i, STL)
  reddedilir; tek nozul konturu denetimi sessiz varsayılan yerine adlı 422
  verir. Yıldız ve finocyl taneler dairesel port diye aktarılmaz,
  gerekçesiyle reddedilir.
- STEP'teki nozul, aynı kontur noktalarından geçen pürüzsüz B-spline dönel
  yüzeydir; ölçüler değişmedi.

## Harita, güvenlik, arayüz

- Şehir ve ülke etiketli, paketli NASA Blue Marble dokulu (15,9 MB)
  ayrıntılı çevrimdışı fırlatma sahası haritası; listelenmiş yer adları
  Türkiye'nin resmî kullanımına uyar; uydu görüntüsü indirme siz açana
  kadar kapalıdır.
- Web sunucusunda tamponlamadan önce uygulanan tek 32 MiB istek gövdesi
  sınırı, yan etkili isteklerde daha sıkı köken kapıları, daha sıkı İçerik
  Güvenliği Politikası; bozuk girdi sunucu hatası yerine 400/422 alır
  (otomatik bulandırma: 456 bulgu → 0).
- Grafik ve panel metinleri arayüz dilini izler; OpenRocket özellikleri
  thrustcurve.org biçiminde motor adlarıyla tek bir kenar sekmesinde.
- Düzeltildi: paralel NASA CEA çağrıları sessizce yanlış sayı
  döndürebiliyordu (dört iş parçacıklı 5 koşunun 5'i); çağrılar artık tek
  kilidi paylaşır.
- Dışa aktarım uçları bozuk bir iç blokta HTTP 500 yerine adlı 422 döndürür
  (ölçülen 10 720 isteğin 108'i); Türkçe kipte İngilizce kalan metin yok;
  örnek hibritin belirsizlik koşusu çalışır (sıfır çap otomatik demektir);
  CFD süre notu uygun (viskozsuz ya da viskoz) tabloyu söyler.

## Bilinen sınırlamalar

- Geri basınçlı 2B CFD: çıkış, ters akan hücrelere de geri basıncı dayatır.
  Bu tür şoklu vakaların hepsi zaten "yakınsamadı / plato" ve `suspect`
  ayrılma hükmüyle döner; bu koşuların çıkış bölgesi çıktısını nitel kabul
  edin.
- Süperkritik hidrojen: kanal boyutlandırması 40 m/s sıvı soğutucu hız
  hedefini (NASA SP-8087) uygular; sonuç güvenli yöndedir (daha sıcak
  öngörülen cidar). Hidrojene özgü hedef 3.1'e planlandı.
- API ve PDF raporunda hibrit TNT eşdeğeri oksitleyici kütlesine değil
  toplam itici kütlesine uygulanır (fazla, ihtiyatlı; örnek 5,765 kg ⟷
  yaklaşık 5,05 kg).
- Yıldız ve finocyl taneler CAD'e aktarılmaz; montaj STL'i kapalı katı
  değildir (STEP kullanın).
- Bu sürümde yok: 3B CFD/FEA, yanmalı CFD, modal FEA, ayrıntılı CAD
  (enjektör kafası, flanşlar, soğutma kanalları), sistem parçaları
  (turbopompa, valfler, gimbal). 3.1 ve sonrasına planlandı.

Tam liste `CHANGELOG.md` dosyasında ve uygulama içi Sürüm Notları
penceresinde.
