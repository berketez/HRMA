<!--HRMA-LANG:en-->
# HRMA v3.0.6 — stable release: corrections

*Released 2026-11-09.*

HRMA 3.0.6 is a corrections release. It fixes what an engineering review of the solid, liquid and hybrid pages found after 3.0.5: places where the same quantity was published with two different numbers, numbers that came from a default or an unsolved model, and panels that disagreed with the motor. It also fixes the language and readability findings of the 3.0.5 user test. It adds no new analysis modules.

## Highlights

- **One quantity, one number.** Where two panels published different values for the same quantity (impulse, consumed propellant, thermal exposure time, test pressure, nozzle contour, jacket pressure drop, optimum O/F), there is now a single value; where two definitions really differ, both are shown with the reason. The Thermal Safety panel computes on the motor's own nozzle contour.
- **Hybrid:** the delivered impulse, burn time and average Isp of a self-pressurised N2O tank come from the tank blowdown solution (3 kN example inputs of 3.0.5: 29 956 → 26 843 N·s); the loaded oxidiser includes the ullage vapour and the dry mass includes the injector plate; the example uses a sourced regression law (Carmicino et al. 2013); thirteen unsourced validator bands were removed.
- **Liquid:** the motor Isp is based on the total propellant consumption and is shown next to the thrust-chamber Isp (example sea level 254.8 / 257.1 s); the combustion chamber is checked against NASA-STD-5012C (AIAA S-080 stays for tanks and lines); when the cooling circuit has no valid solution, the feed, cycle, motor performance and mass numbers that depend on it are withheld with their reason; the regenerative jacket has a single pressure drop, solved together with the cycle in staged-combustion and expander engines; a fixed nozzle that separates at sea level is refused by name (the liquid page designs at sea level).
- **Solid:** one nozzle contour in the response, the 3D view, STEP and FEA; one test-pressure ladder on the Safety tab and the deck; the nozzle mass comes from the drawn contour; grain stress results that the model cannot resolve at sharp port corners are not published; the validation panel uses the motor's own thrust curve; solver-filled component masses in a saved project are refreshed by Calculate.
- **Safety and structure:** an incomplete motor assessment is shown as NOT EVALUATED instead of a low risk; a single test-pressure ladder per vessel; the two-layer liquid wall is checked layer by layer.
- **Flight:** the unburned hybrid grain and the propellant left in the tank fly with the vehicle (lift-off mass = motor total mass); the OpenRocket .eng propellant mass is the mass burned; the load factor is the sensed acceleration; the 6-DOF thrust is corrected for altitude; a parametric sweep point gives the same apogee as Calculate; a saved project keeps its flight setup.
- **Language and readability:** charts no longer overflow their panels and follow a live language switch; user texts carry no HTTP codes, raw keys or API field names; the Turkish PDF uses the interface language with Turkish fonts and decimal commas.
- **Updates:** on macOS an update in progress no longer opens the old version.
- **Licence:** HRMA is now distributed under GPL-3.0-or-later (it ships the GPLv3-licensed RocketCEA library); the licence text and third-party notices are in the package.

See CHANGELOG.md for the full list and the published numbers that changed.

## Updating

- The in-app update takes about 4 minutes. Do not open HRMA until it has finished.
- Projects saved with 3.0.5 or earlier open in 3.0.6. Unchanged copies of the shipped examples are refreshed once; a copy you changed is never touched.
- Some published numbers change (see CHANGELOG.md), so the same project can give different results than in 3.0.5. A saved liquid design whose fixed nozzle separates at sea level now opens with a named refusal and the largest expansion ratio that stays attached.

<!--HRMA-LANG:tr-->
# HRMA v3.0.6 — Kararlı sürüm: düzeltmeler

*Yayın tarihi: 2026-11-09.*

HRMA 3.0.6 bir düzeltme sürümüdür. 3.0.5'ten sonra katı, sıvı ve hibrit sayfaların mühendislik incelemesinin bulduklarını düzeltir: aynı büyüklüğün iki farklı sayıyla yayımlandığı yerler, varsayılandan ya da çözülmemiş bir modelden gelen sayılar ve motorla çelişen paneller. 3.0.5 kullanıcı testinin dil ve okunabilirlik bulgularını da düzeltir. Yeni analiz modülü eklemez.

## Öne çıkanlar

- **Tek büyüklük, tek sayı.** Aynı büyüklük için iki panelin farklı değer yayımladığı yerlerde (impuls, harcanan itici, ısıl maruziyet süresi, test basıncı, nozul konturu, ceket basınç düşümü, optimum O/F) artık tek değer var; iki tanım gerçekten farklıysa ikisi nedeniyle birlikte gösterilir. Termal Güvenlik paneli motorun kendi nozul konturuyla hesaplar.
- **Hibrit:** kendinden basınçlı N2O tankında teslim impulsu, yanma süresi ve ortalama Isp tank boşalma çözümünden gelir (3.0.5'in 3 kN örnek girdileriyle 29 956 → 26 843 N·s); yüklü oksitleyici ullage buharını, kuru kütle enjektör plakasını içerir; örnek kaynaklı regresyon bağıntısını (Carmicino ve ark. 2013) kullanır; doğrulayıcının kaynaksız 13 bandı kalktı.
- **Sıvı:** motor Isp'si toplam itici tüketimine göredir ve itki odası Isp'sinin yanında gösterilir (örnek deniz seviyesi 254,8 / 257,1 s); yanma odası NASA-STD-5012C'ye göre denetlenir (AIAA S-080 tanklar ve hatlar için kalır); soğutma devresinin geçerli çözümü yoksa ona bağlı besleme, çevrim, motor performansı ve kütle sayıları nedenleriyle bekletilir; rejeneratif ceketin tek basınç düşümü vardır ve kademeli yanmalı ve genleşmeli motorlarda çevrimle birlikte çözülür; deniz seviyesinde ayrılan sabit nozul adıyla reddedilir (sıvı sayfası deniz seviyesinde tasarlar).
- **Katı:** yanıtta, 3B görünümde, STEP'te ve FEA'da tek nozul konturu; Güvenlik sekmesinde ve güvertede tek test basıncı merdiveni; nozul kütlesi çizilen konturdan gelir; modelin keskin port köşelerinde çözemediği tane gerilme sonuçları yayımlanmaz; doğrulama paneli motorun kendi itki eğrisini kullanır; kayıtlı projede çözücünün doldurduğu bileşen kütlelerini Hesapla yeniler.
- **Güvenlik ve yapı:** eksik motor değerlendirmesi düşük risk yerine DEĞERLENDİRİLMEDİ olarak gösterilir; her kap için tek test basıncı merdiveni; iki katmanlı sıvı cidar katman katman denetlenir.
- **Uçuş:** hibritte yanmayan tane ve tankta kalan itici araçla uçar (kalkış kütlesi = motorun toplam kütlesi); OpenRocket .eng itici kütlesi yanan kütledir; yük çarpanı algılanan ivmedir; 6-DOF itkisi irtifaya göre düzeltilir; parametrik tarama noktası Hesapla ile aynı apojeyi verir; kaydedilen proje uçuş kurulumunu saklar.
- **Dil ve okunabilirlik:** grafikler panellerinden taşmaz ve canlı dil geçişini izler; kullanıcı metinlerinde HTTP kodu, ham anahtar ya da API alan adı yok; Türkçe PDF arayüz dilinde, Türkçe yazı tipi ve ondalık virgülle üretilir.
- **Güncelleme:** macOS'ta süren güncelleme eski sürümü açmaz.
- **Lisans:** HRMA artık GPL-3.0-or-later ile dağıtılır (GPLv3 lisanslı RocketCEA kütüphanesini içerir); lisans metni ve üçüncü taraf bildirimleri pakettedir.

Tam liste ve değişen yayımlanmış sayılar için CHANGELOG.md dosyasına bakın.

## Güncelleme

- Uygulama içi güncelleme yaklaşık 4 dakika sürer. Bitene kadar HRMA'yı açmayın.
- 3.0.5 ve öncesiyle kaydedilen projeler 3.0.6'da açılır. Paketle gelen örneklerin değiştirilmemiş kopyaları bir kez yenilenir; değiştirdiğiniz kopyaya dokunulmaz.
- Bazı yayımlanmış sayılar değişir (CHANGELOG.md), bu yüzden aynı proje 3.0.5'tekinden farklı sonuç verebilir. Sabit nozulu deniz seviyesinde ayrılan kayıtlı bir sıvı tasarım artık adlı retle ve akışın yapışık kaldığı en büyük genleşme oranıyla açılır.
