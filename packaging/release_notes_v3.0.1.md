<!--HRMA-LANG:en-->
# HRMA v3.0.1 — stable release: corrections

*Released 2026-10-27.*

HRMA 3.0.1 is a corrections release. It fixes the problems found after 3.0.0 by an external tester, by an audit of the solid and liquid pages and by an end-to-end user test of the interface. It adds no new analysis modules.

## Highlights

- **Inputs are checked and rejected by name.** An out-of-range or contradictory input is rejected with the field name and its accepted range instead of being clipped or replaced silently.
- **Every input has a help note** — what it is, its unit, what it changes in the calculation and what happens when it is left empty.
- **NASA CEA comparison** for all three engine types; solid propellant thermochemistry is now evaluated at the motor's own chamber pressure.
- **Hybrid:** zoned chamber-wall thermal model and a c* efficiency input with a sourced default.
- **Liquid:** regenerative cooling includes the fin (rib) effect and the Sieder-Tate viscosity correction; carbon deposition on the RP-1 hot wall is modelled.
- **Charts:** a time axis for the transient analysis, separate charts and readable labels.
- **Projects:** projects saved with older versions are migrated when opened; project names may contain Turkish letters.

See CHANGELOG.md for the full list and the published numbers that changed.

**Updating:** the in-app update takes about 4 minutes. Do not open HRMA until it has finished.

<!--HRMA-LANG:tr-->
# HRMA v3.0.1 — Kararlı sürüm: düzeltmeler

*Yayın tarihi: 2026-10-27.*

HRMA 3.0.1 bir düzeltme sürümüdür. 3.0.0'dan sonra dış testçinin, katı ve sıvı sayfa denetiminin ve arayüzün baştan sona kullanıcı testinin bulduğu sorunları düzeltir. Yeni analiz modülü eklemez.

## Öne çıkanlar

- **Girdiler denetlenir, adıyla reddedilir.** Kabul aralığı dışındaki ya da çelişen bir girdi, sessizce kırpılmak ya da değiştirilmek yerine alan adı ve kabul aralığıyla reddedilir.
- **Her girdinin yanında açıklama var:** ne olduğu, birimi, hesapta neyi değiştirdiği ve boş bırakılırsa ne olduğu.
- **NASA CEA karşılaştırması** üç motor tipinde; katı itici termokimyası artık motorun kendi hazne basıncında hesaplanır.
- **Hibrit:** bölgeli hazne cidarı ısıl modeli ve kaynaklı varsayılanı olan c* verimi girdisi.
- **Sıvı:** rejeneratif soğutmada kanat (kaburga) etkisi ve Sieder-Tate viskozite düzeltmesi; RP-1 sıcak cidarında karbon birikimi modellenir.
- **Grafikler:** geçici analizde zaman ekseni, ayrı grafikler ve okunur etiketler.
- **Projeler:** eski sürümlerle kaydedilmiş projeler açılırken göç ettirilir; proje adında Türkçe harf kullanılabilir.

Tam liste ve değişen yayımlanmış sayılar için CHANGELOG.md'ye bakın.

**Güncelleme:** uygulama içi güncelleme yaklaşık 4 dakika sürer. Bitene kadar HRMA'yı açmayın.
