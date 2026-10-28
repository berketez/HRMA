<!--HRMA-LANG:en-->
# HRMA v3.0.5 — stable release: corrections

*Released 2026-10-28.*

HRMA 3.0.5 is a corrections release. It fixes the problems found after 3.0.0 by an external tester, by an audit of the solid and liquid pages and by an end-to-end user test of the interface. The work prepared as 3.0.1 ships here; a separate 3.0.1 was never published. It adds no new analysis modules.

## Highlights

- **Inputs are checked and rejected by name.** An out-of-range or contradictory input is rejected with the field name and its accepted range instead of being clipped or replaced silently. An empty field sends no hidden number.
- **Every input has a help note** — what it is, its unit, what it changes in the calculation and what happens when it is left empty.
- **NASA CEA comparison** for all three engine types; solid propellant thermochemistry is now evaluated at the motor's own chamber pressure. The comparison is a code verification, not a validation against test firings, and changes no design number.
- **Hybrid:** zoned chamber-wall thermal model (critical warnings on the example 43 → 7) and a c* efficiency input with a sourced default (N2O/HTPB 0.89; example 3 kN motor Isp 235.9 → 210.1 s).
- **Solid:** a propellant selector; the default propellant is KNDX and the default grain is 100 mm in diameter with a 48 mm core and a length of 400 mm; a case the grain does not fit, a core larger than the grain and a port smaller than the throat are refused.
- **Liquid:** regenerative cooling includes the fin (rib) effect and the Sieder-Tate viscosity correction; carbon deposition on the RP-1 hot wall is modelled; the regenerative wall is a liner inside a structural closeout, each checked on its own; the RP-1 coking limit is 728 K (561 K is a warning).
- **Charts:** a time axis for the transient analysis, separate charts and readable labels; result cards show the final value at once.
- **Design with AI:** copy the whole design context into the assistant you use and paste its suggestion back; HRMA calls no AI service and checks every proposed value before applying it.
- **Flight:** a saved project flies the same motor as the page.
- **CAD:** the pintle is drawn with its real holes; STEP and STL use one nozzle source; the example hybrid exports again.
- **Projects:** projects saved with older versions are migrated when opened; project names may contain Turkish letters.

See CHANGELOG.md for the full list and the published numbers that changed.

## Updating

- The in-app update takes about 4 minutes. Do not open HRMA until it has finished.
- Projects saved with 3.0.0 or earlier open in 3.0.5. Unchanged copies of the shipped examples are refreshed once; a copy you changed is never touched.
- An older solid project whose "case diameter" meant the grain diameter is migrated with a load warning: check the case diameter after opening.
- Some published numbers change (see CHANGELOG.md), so the same project can give different results than in 3.0.0.

<!--HRMA-LANG:tr-->
# HRMA v3.0.5 — Kararlı sürüm: düzeltmeler

*Yayın tarihi: 2026-10-28.*

HRMA 3.0.5 bir düzeltme sürümüdür. 3.0.0'dan sonra dış testçinin, katı ve sıvı sayfa denetiminin ve arayüzün baştan sona kullanıcı testinin bulduğu sorunları düzeltir. 3.0.1 adıyla hazırlanan çalışma bu sürümle çıkar; ayrı bir 3.0.1 hiç yayımlanmadı. Yeni analiz modülü eklemez.

## Öne çıkanlar

- **Girdiler denetlenir, adıyla reddedilir.** Kabul aralığı dışındaki ya da çelişen bir girdi, sessizce kırpılmak ya da değiştirilmek yerine alan adı ve kabul aralığıyla reddedilir. Boş alan gizli sayı göndermez.
- **Her girdinin yanında açıklama var:** ne olduğu, birimi, hesapta neyi değiştirdiği ve boş bırakılırsa ne olduğu.
- **NASA CEA karşılaştırması** üç motor tipinde; katı itici termokimyası artık motorun kendi hazne basıncında hesaplanır. Karşılaştırma bir kod doğrulamasıdır, test ateşlemelerine karşı geçerleme değildir; hiçbir tasarım sayısını değiştirmez.
- **Hibrit:** bölgeli hazne cidarı ısıl modeli (örnekte kritik uyarı 43 → 7) ve kaynaklı varsayılanı olan c* verimi girdisi (N₂O/HTPB 0,89; 3 kN örnek motorda Isp 235,9 → 210,1 s).
- **Katı:** yakıt seçici; varsayılan yakıt KNDX, varsayılan tane 100 mm çaplı, 48 mm çekirdekli ve 400 mm boylu; taneyi almayan kasa, taneden büyük çekirdek ve boğazdan küçük port reddedilir.
- **Sıvı:** rejeneratif soğutmada kanat (kaburga) etkisi ve Sieder-Tate viskozite düzeltmesi; RP-1 sıcak cidarında karbon birikimi modellenir; rejeneratif cidar, yapısal bir dış kabuğun içinde kanallı bir astardır ve her katman ayrı denetlenir; RP-1 koklaşma sınırı 728 K'dir (561 K uyarıdır).
- **Grafikler:** geçici analizde zaman ekseni, ayrı grafikler ve okunur etiketler; sonuç kartları son değeri hemen gösterir.
- **Yapay Zekâ ile Tasarla:** tasarımın bütün bağlamını kullandığınız asistana kopyalayın, önerisini geri yapıştırın; HRMA hiçbir yapay zekâ hizmetini çağırmaz ve önerilen her değeri uygulamadan önce denetler.
- **Uçuş:** kayıtlı proje sayfadaki motorun aynısını uçurur.
- **CAD:** pintle gerçek delikleriyle çizilir; STEP ve STL tek lüle kaynağını kullanır; örnek hibrit yeniden dışa aktarılabiliyor.
- **Projeler:** eski sürümlerle kaydedilmiş projeler açılırken göç ettirilir; proje adında Türkçe harf kullanılabilir.

Tam liste ve değişen yayımlanmış sayılar için CHANGELOG.md'ye bakın.

## Güncelleme

- Uygulama içi güncelleme yaklaşık 4 dakika sürer. Bitene kadar HRMA'yı açmayın.
- 3.0.0 ve öncesiyle kaydedilmiş projeler 3.0.5'te açılır. Dağıtılan örneklerin değiştirilmemiş kopyaları bir kez yenilenir; sizin değiştirdiğiniz kopyaya dokunulmaz.
- "Kasa çapı" alanı tane çapı anlamına gelen eski bir katı proje, yükleme uyarısıyla göç ettirilir: açtıktan sonra kasa çapını denetleyin.
- Bazı yayımlanmış sayılar değişti (bkz. CHANGELOG.md); aynı proje 3.0.0'dakinden farklı sonuç verebilir.
