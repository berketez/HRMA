# Changelog · Değişiklik günlüğü

All notable changes to HRMA are listed here, newest first. Each entry is
written twice: English first, then Turkish. The in-app **Release Notes**
window carries the full, item-by-item list for every version.

HRMA'daki kayda değer değişiklikler burada, en yenisi en üstte olacak şekilde
listelenir. Her kayıt iki dilde yazılır: önce İngilizce, sonra Türkçe.
Uygulama içindeki **Sürüm Notları** penceresi her sürümün kalem kalem tam
listesini taşır.

---

## 3.0.0 — English

*Released 2026-10-15.*

HRMA 3.0.0 is the first release after 2.6.26. The work that was announced
in the application as "2.6.27 (in development)" ships in this release; a
separate 2.6.27 was never published.

HRMA is a **preliminary-design tool**: requirement → engine → analysis →
revision → CAD → hand-off to detailed analysis. It is not a
flight-qualification tool. The theme of this release is that a number is
published with its validity limits, and that a verdict the model cannot
support is **withheld with its reason** instead of being shown as a pass.

### Engine physics

- **One allowable-temperature ladder for thermal safety verdicts.** The safety
  analysis and the heat-flux chart's service limit now read the same
  allowable temperature of the material as the thermal module. Measured
  effect: stainless steel 304/316 1143 → 1073 K, carbon-carbon 2273 →
  1920 K; in a margin window of 1.3 the overall risk of such a design moves
  from MEDIUM to HIGH. A wall-temperature profile without a stated source,
  or one that cannot be read, no longer receives a positive thermal verdict.
  The thermal panel names the limit that gives the verdict (for plain steel
  the 811 K structural service limit, not the 1073 K allowable temperature
  listed next to it).
- **Hybrid: N₂O liquid inlet state is an input.** Tank temperature and
  oxidiser phase enter the combustion enthalpy balance (default: saturated
  liquid at 293.15 K, CoolProp HEOS; NASA RP-1311 §4.1). On the example
  hybrid motor: chamber temperature −56.1 K, c* −1.195 %, Isp −1.175 %.
  Gas-phase oxidisers and LOX, H₂O₂, air and aluminium cases are unchanged.
- **Hybrid: tank pressure in N₂O saturation mode.** The form shows the tank
  pressure the model actually uses (the saturation pressure at the tank
  temperature) as read-only, and the API warns when a request sends a
  different value. Example hybrid: 55.0 → 50.5 bar. The tank temperature
  has one default, 293.15 K, for the injector plate and the engine alike
  (the plate used 293 K).
- **Hybrid chamber material: one default.** A request that names no chamber
  material now uses stainless steel 304, the material the form already
  showed as selected, instead of 4130 steel, and the response declares it.
  In the browser an untouched selector sent no material, so the calculation
  used 4130 while the screen showed 304. Example hybrid: minimum structural
  safety factor 0.836 → 0.232, dry mass 85.16 → 96.80 kg.
- **Hybrid injector.** The orifice-diameter band has a single definition
  (0.5–2.5 mm, Sutton; Mishra) instead of four; plans outside the canonical
  showerhead path can change. An injector plan whose clipped pressure drop
  misses the target mass flow by more than 5 % is no longer marked as
  passing (`target_flow_not_met`). The chug-ratio residual is broken down
  term by term.
- **Hybrid grain segmentation** is reported as not modelled instead of a
  segment count the solver never used.
- **Solid APCP thermochemistry from NASA CEA.** The APCP reference record
  is the CEA equilibrium set (flame temperature 3614.8 → 3399.65 K, c*
  1598.2 → 1585.4 m/s, γ 1.1338, M 27.829 kg/kmol); the Bartz heat-transfer
  correlation uses the frozen chamber γ (1.1862) from the same run. Default
  APCP motor: sea-level Isp +0.81 %, throat heat flux −2.78 %. The
  two-phase module no longer publishes "gas-only" effective properties when
  the record already contains the condensed phase (it would count it twice).
- **Solid page defaults come from the same APCP record.** On a fresh solid
  page: density 1850 → 1810 kg/m³, chamber temperature 3200 → 3399.65 K,
  γ 1.25 → 1.1338, c* 1550 → 1585.4 m/s; sea-level Isp 206.14 → 217.60 s,
  average thrust 3134.95 → 3236.30 N, propellant mass 6.611 → 6.468 kg.
  With the corrected chamber temperature a graphite nozzle now receives a
  nozzle over-temperature warning.
- **Safety analysis: propellant class from the engine's own propellant.**
  For classes without a sourced TNT equivalent (hybrid in the safety panel,
  sugar propellants such as KNDX, black powder) the TNT equivalent, blast
  distance, fragment range and evacuation distance are "not evaluated" with
  the reason, instead of a number that had no source. The API and the PDF
  report follow the same rule as the panel: a solid propellant takes its
  class from its catalogue family (composite, double base), so KNDX is no
  longer counted as composite (1.011 kg TNT, 1600 m evacuation, MEDIUM →
  not evaluated, LOW). Example hybrid in the panel: 5.435 kg TNT and 1600 m
  evacuation → not evaluated. APCP and liquid results are unchanged.
- **Safety panel: no thermal verdict from a non-physical wall temperature.**
  For an uncooled hybrid the heat module marks its equilibrium wall
  temperature as not physical; the panel no longer sends it, so the thermal
  verdict and the combined pressure-plus-thermal safety factor are withheld
  with the reason. Example hybrid: CRITICAL (combined safety factor 0.713)
  → MEDIUM, partial.
- **Structural verdicts follow the model's validity limit.** When the
  structural model is outside its validity range (for example, the solved
  wall temperature does not reach the structural analysis), approval
  verdicts are withheld and say why: end-cap "sized and verified", the
  sizing-mode approval, the analysis-deck verdict badge, and the design
  target, fatigue and buckling verdicts of the structural safety analysis.
  The numbers stay visible. In a 52-case before/after measurement 23 cases
  changed from "SAFE · VERY LOW" to "NOT EVALUATED"; no number changed and
  no failing verdict was hidden. The liquid structural card now names the
  read-back design safety-factor target and the operating hoop safety
  factor separately.
- **The analysis deck's structural panel uses the engine's own design
  target.** The deck sends the engine's design safety-factor target instead
  of the material default and names its source. Solid example: target
  4.0 → 3.0, design-target verdict SAFE · VERY LOW → ACCEPTABLE · LOW;
  liquid example: 3.0 → 2.5, ACCEPTABLE · LOW → MARGINAL · MEDIUM.
- **Structural FEA load model.** `/api/fea/structural` loads the convergent
  and divergent sections with the 1D isentropic static pressure (γ from the
  engine result; constant chamber pressure as a declared fallback), applies
  the closed-end force and checks the force balance on every run (tolerance
  1e-3 of the end force; otherwise the verdict is withheld). The response
  states the scope: pressure loads only, no thermal stress and no
  temperature-dependent strength. Example motors, minimum safety factor:
  liquid 2.23 → 3.63 (with the wall HRMA now sizes, below), hybrid 5.53 →
  9.22, solid 1.03 → 2.19; all three verdicts, previously withheld as
  sensitive to the support location, are now given.
- **Liquid chamber wall sized by HRMA.** The liquid page no longer pre-fills
  an unsourced 5 mm wall; the engine sizes it (example: 2 mm).
- **Regenerative cooling: one temperature limit.** The cooling verdict's
  service limit is the material's allowable temperature, as in the thermal
  module, instead of its melting point (copper 1358 → 723 K, Inconel 718
  1533 → 977 K); a wall between the allowable and the melting temperature
  is now UNSAFE instead of WARNING. Peak wall temperatures, heat loads and
  pressure drops are unchanged.
- **Regenerative cooling inputs come from the engine.** The cooling panel no
  longer pre-fills unsourced values (80 channels, channel width and depth,
  liner thickness, water coolant, inlet temperature and pressure): each
  field takes the engine's published value or stays empty and required, and
  no request is sent while a required field is empty. `/api/regen-cooling`
  answers a request without `n_channels` with a named 400. When the coolant
  station march cannot run, a warning says so instead of the thermal
  verdict disappearing silently.
- **Supercritical hydrogen cooling.** Channel sizing and the published
  coolant velocity use the same hydrogen density; before, the sizing used a
  liquid density and the published velocity was about four times the
  target the sizing assumed it met. The velocity target itself is listed
  under Known limitations.
- **Liquid page fuel density.** Changing the fuel no longer sends another
  fuel's density as input (for example RP-1's 810 kg/m³ for LH2); a value
  typed by hand is kept, with a warning when the selected fuel differs. On
  a pressure-fed cycle, turbopump efficiency and gas-generator temperature
  are listed as unused inputs.

### CAD

- **CAD is drawn from the analysis geometry (single source).** An
  independent CAD check had found places where the exporter drew its own
  rule instead of the analysed engine (a star grain drawn as a plain tube,
  propellant volume +23.3 %; hybrid nozzle wall 3 mm in STEP but 7.19 mm in
  STL; tank volume 1.23×). These are fixed.
- **Fail-closed manufacturing export.** Every manufacturing export (STEP,
  DXF, drawing PDF, STL package, single STL, complete package,
  `/api/export-cad`) is refused by the server with the same named reasons
  when the structural safety factor is below 1 or the structural model is
  outside its validity range (example hybrid: drawing PDF, STL package and
  `/api/export-cad` 200 → 422). Star and finocyl grains, which the CAD
  kernel cannot yet draw faithfully, are refused with a reason instead of
  being exported as a circular port.
- **One nozzle-contour check for every export.** A contour that turns back,
  a throat radius of curvature that is not positive or cannot be read, or a
  contour angle that cannot be read gets a named 422 instead of a file built
  on a silent default (for angles 30°, 8° or 15°); a malformed contour
  block that caused a server error gets 422 too. The solid and liquid CAD
  packages draw the nozzle contour the engine published, and the DXF class
  table is written in a fixed order (same file on every run apart from
  timestamps).
- **Tank model** is a declared flat-ended cylinder; part names carry their
  source.
- **Smooth nozzle surfaces.** The nozzle in STEP is one B-spline surface of
  revolution through the same contour points instead of about a hundred
  conical facets. Lengths and end diameters are bit-identical; the throat
  differs by less than 1e-7 mm. A malformed contour returns a named 422
  error instead of a server error. The package README notes that a CAD
  tool's default volume of these surfaces can be off by 0.04–1.5 %, and
  that HRMA's nozzle mass is not read from the file.

### Launch-site map

- **Detailed offline map** (about 13 MB of bundled assets): vector borders
  with level of detail, and city and country labels that appear as you zoom
  in. Labels stay readable over snow and ice, and their count is capped
  when the whole globe is shown.
- **Bundled Earth imagery.** A packaged NASA Blue Marble texture (December
  2004, about 2 km per pixel at the equator, 1,073 tiles, 15.9 MB) is drawn
  without any network request; online tiles are requested only for finer
  detail and only when the switch below is on. The map note gives the
  measured offset between the vector coastline and the imagery (Kennedy
  coast against a NASA GIBS tile: median 598 m, 90th percentile 1.3 km).
- **Place names** follow Türkiye's official usage for a short, listed set
  of names (for example *Türkiye*, *Greek Cypriot Administration of
  Southern Cyprus*, *Khankendi*); Crimea is shown as part of Ukraine. Every
  other name is unchanged from Natural Earth 5.1.2, and the corrections are
  recorded in the map's provenance.
- **Privacy switch for satellite imagery.** Downloading imagery tiles is
  **off by default**. Until you turn it on, the server makes no outside
  request; tiles already in the local cache are still shown.

### Security

- Local API origin gates tightened: a page on another local port can no
  longer trigger the side-effecting GET endpoints, and an Origin without a
  port is checked against the server's real port.
- Request bodies: one 32 MiB limit for every endpoint, enforced by the web
  server before the body is buffered (oversized requests get a JSON 413);
  per-request item limits for configuration and composition lists; at most
  100 simultaneous connections.
- Content-Security-Policy adds `object-src 'none'` and `base-uri 'none'`.
  Server and error text is escaped before it reaches the page.
- Upload screens (STEP, OpenRocket `.ork`, motor file, CSV) check the size
  limit before sending the file; the limit is read from the server. The
  validation panel's re-compare checks it too, and an oversized request
  (413) is shown as a readable message.
- An automated API fuzzing run (3,090 requests over 104 endpoint methods)
  went from 456 findings to 0: malformed input now gets 400/422 with a
  reason instead of a server error.
- Export endpoints no longer crash on a malformed nested block. When a
  nested block of the export payload (for example `design_summary`,
  `structural_analysis`, `heat_transfer_analysis.wall_analysis`,
  `grain_design`) arrived as text or a list instead of an object, nine
  export endpoints returned HTTP 500 (measured: 108 of 10,720 requests).
  They now return 422 `invalid_export_geometry` naming the full field
  path; an unreadable `nozzle_angles` block gets the nozzle contour gate's
  refusal. The STL package endpoint returns the assembly generator's named
  refusal (422, as `/api/export-cad` does) instead of a 500 when the
  throat or exit diameter is not published.

### Interface

- Chart and panel texts follow the interface language (Turkish/English).
- Stability and transient panels show where their numbers come from.
- **OpenRocket corner:** the OpenRocket features are collected in one tab
  in the right sidebar. The RASP motor designation is the impulse-class
  letter plus the average thrust (thrustcurve.org format) instead of the
  case diameter, and the default motor name is no longer cut short when
  OpenRocket reads it.
- The unlinked `/simple` and `/uzaytek` pages were removed.
- The warning for a project saved by an older version follows the interface
  language. The CFD run-time note, the feed-system chart labels and the new
  "Ox Tank (required)" label have Turkish text, and the Turkish interface
  uses one word for "nozzle" throughout.
- The FEA panel shows the load model (pressure distribution, closed-end
  force, scope, force balance) and marks a peak that sits in the loaded end
  band as a diagnosis, not a verdict.
- The solid endpoint no longer declares "APCP, endpoint default" when the
  motor took its propellant from the propellant name or the burn-rate preset
  (example KNDX motor); the numbers are unchanged.
- The Turkish and English user guides (PDF) have v3.0 sections with new
  screenshots: withheld verdicts, thermal results, panel provenance, hybrid
  warnings, CAD export refusals and the map.
- Turkish mode no longer shows leftover English text or decimal points in
  the solid structural tab (risk classes, closure-bolt note), the analysis
  deck's structural and thermal panels, the launch-site vehicle notes and
  load warnings, the uncertainty panel's conditions and the hybrid
  warnings' material names; percentages use the Turkish form (%16,2).
- When the heat module flags its equilibrium wall temperature as not
  physical, the safety panel now says that this is why the thermal axis
  is not evaluated (previously it looked like a missing input).
- Uncertainty analysis: a zero diameter input now means "auto", as it
  does in the engine calculation; the example hybrid motor's uncertainty
  run previously failed with `non_physical_uncertainty_input`.
- CFD run-time note: a viscous run now quotes the viscous worst-case
  table (it used to quote the inviscid figure, e.g. 19.9 s for runs that
  took hundreds of seconds). Both tables were re-measured with one
  protocol (iteration ceiling, shocked back-pressure case, at least two
  repeats); the default level without numba measures 18.5 s. The
  viscous table comes from a loaded machine and is a cautious upper
  bound; the note says so.

### Robustness

- A cached NASA CEA object could be reused after RocketCEA's own cache had
  been cleared, which made some liquid runs fail depending on what ran
  before them. The cache entry is now checked and rebuilt.
- NASA CEA calls ran outside the shared lock. With four parallel threads,
  5 of 5 runs returned silently wrong numbers (for example an ethanol case,
  sea-level Isp 234.909 → 200.404 s). Calls now hold the same lock; serial
  results are bit-identical. When RocketCEA is installed but a call fails,
  the fallback to tabulated data is announced with a warning instead of
  happening silently; the liquid engine reports it as a failed call, not as
  RocketCEA being absent. The isolated NASA CEA data directory is checked
  before use and pinned again if something else moved it.

### Earlier campaign (announced as 2.6.27)

Also in this release, each with before/after numbers in the in-app notes:
ablation physics rebuilt (blowing blockage solved from B′ instead of a
constant 0.5; corrected surface temperatures); the page no longer overrides
the catalogue burn rate; real-gas blowdown pressurant sizing; hybrid
explosive equivalence derived instead of tabulated; the PDF report's safety
section is fed; liquid water hammer (2 → 7 propellants), dump cooling and
power balance; FEA bridge closure margin and thin-wall warning; buckling
envelope and burst-pressure naming; KNDX and KNSB thermochemistry on the
CEA basis; empty form fields are no longer sent and each endpoint declares
the defaults it applied.

### Known limitations

- **2D CFD with back pressure** (`POST /api/cfd/nozzle`, `Pb_Pa`): the
  outlet boundary also imposes the back pressure on cells where the flow is
  reversed. Measured on shocked, over-expanded cases: reversed flow at the
  outlet in 22 of 42 runs in the final field. Every such case already
  returns "not converged / plateau" with a `suspect` separation verdict, so
  none is presented as validated; treat exit-region wall pressure and
  separation output of these runs as qualitative.
- **Supercritical hydrogen coolant velocity.** Channel sizing applies the
  40 m/s liquid-coolant velocity target (NASA SP-8087) to supercritical
  hydrogen as well; a hydrogen-specific target is planned for 3.1. The
  result errs on the safe side (deeper channels, lower coolant-side heat
  transfer, a hotter predicted wall; example LH2 variant: peak hot wall
  1478 K instead of 1387 K, UNSAFE either way), so it does not produce a
  false SAFE.
- **Hybrid TNT equivalent in the API and the PDF report.** The derived
  factor is per kilogram of oxidiser, but the endpoint and the report carry
  no oxidiser-mass input, so it is applied to the total propellant mass.
  The result is too high, on the conservative side (example hybrid:
  5.765 kg TNT; about 5.05 kg on the oxidiser mass). The safety panel does
  not evaluate it for hybrids (see above).
- Star and finocyl grains are not exported to CAD (see above).
- The assembly STL is not a closed solid; use STEP for CAD work.

### Not in this release (planned for 3.1 and later)

- C++ solver core; 3D CFD and 3D FEA; combusting (reactive) CFD; modal FEA.
- CAD with hand-drawn level of detail: injector head and dome, flanges and
  bolt circles, O-ring grooves, ports, regenerative cooling channels, true
  port cross-section, closed STL.
- System parts: turbopump, preburner, feed lines, valves, gimbal; exhaust
  plume visuals.
- A more compact map encoding.
- Gas-only two-phase properties for APCP; validity flags on number-only
  structural fields (liquid mass chain, thickness, mass, T/W).

---

## 3.0.0 — Türkçe

*Yayın tarihi: 2026-10-15.*

HRMA 3.0.0, 2.6.26'dan sonraki ilk sürümdür. Uygulamada "2.6.27
(geliştirme sürüyor)" diye duyurulan çalışma bu sürümle çıkar; ayrı bir
2.6.27 hiç yayımlanmadı.

HRMA bir **ön tasarım aracıdır**: gereksinim → motor → analiz → revizyon →
CAD → ayrıntılı analize aktarım. Uçuş yeterlilik aracı değildir. Bu sürümün
ana fikri şudur: her sayı geçerlilik sınırıyla yayımlanır; modelin
dayanamadığı bir hüküm "geçti" gibi gösterilmez, **gerekçesiyle
bekletilir**.

### Motor fiziği

- **Isıl güvenlik hükümlerinde tek izin sıcaklığı basamağı.** Güvenlik analizi ve ısı
  akısı grafiğindeki servis sınırı artık malzemenin izin sıcaklığını ısıl
  modülle aynı yerden okur. Ölçülen etki: paslanmaz çelik 304/316 1143 →
  1073 K, karbon-karbon 2273 → 1920 K; 1,3'lük pay penceresinde böyle bir
  tasarımın genel riski ORTA'dan YÜKSEK'e çıkar. Kaynağı belirtilmemiş ya da
  okunamayan bir cidar sıcaklığı profili artık olumlu ısıl hüküm almaz.
  Isıl panel hükmü veren sınırı adıyla yazar (düz çelikte yanında yazan
  1073 K izin sıcaklığı değil, 811 K yapısal servis sınırı).
- **Hibrit: N₂O sıvı giriş durumu bir girdidir.** Tank sıcaklığı ve
  oksitleyici fazı yanma entalpi dengesine girer (varsayılan: 293,15 K'de
  doymuş sıvı, CoolProp HEOS; NASA RP-1311 §4.1). Örnek hibrit motorda:
  oda sıcaklığı −56,1 K, c* −%1,195, Isp −%1,175. Gaz fazlı oksitleyiciler
  ile LOX, H₂O₂, hava ve alüminyum vakaları değişmez.
- **Hibrit: N₂O doyma kipinde tank basıncı.** Form, modelin gerçekten
  kullandığı tank basıncını (tank sıcaklığındaki doyma basıncı) salt-okur
  gösterir; istek farklı bir değer gönderirse API uyarır. Örnek hibrit:
  55,0 → 50,5 bar. Tank sıcaklığının enjektör plakası ve motor için tek
  varsayılanı var: 293,15 K (plaka 293 K kullanıyordu).
- **Hibrit kamara malzemesi: tek varsayılan.** Kamara malzemesi vermeyen
  istek artık 4130 çeliği yerine formun zaten seçili gösterdiği 304
  paslanmaz çeliği kullanır ve yanıt bunu beyan eder. Tarayıcıda
  dokunulmamış seçici malzeme göndermiyordu; ekran 304 gösterirken hesap
  4130 ile yapılıyordu. Örnek hibrit: en küçük yapısal emniyet katsayısı
  0,836 → 0,232, kuru kütle 85,16 → 96,80 kg.
- **Hibrit enjektör.** Orifis çapı bandının dört ayrı tanımı yerine tek
  tanımı var (0,5–2,5 mm; Sutton, Mishra); kanonik duş başlığı yolu dışındaki
  planlar değişebilir. Kırpılan basınç düşüşüyle hedef debiyi %5'ten fazla
  kaçıran enjektör planı artık "geçti" almaz (`target_flow_not_met`). Chug
  oranının kalıntısı terim terim ayrıştırılır.
- **Hibrit tane segmentasyonu**, çözücünün hiç kullanmadığı bir segment
  sayısı yerine "modellenmedi" diye bildirilir.
- **Katı APCP termokimyası NASA CEA'dan.** APCP referans kaydı CEA denge
  takımıdır (alev sıcaklığı 3614,8 → 3399,65 K, c* 1598,2 → 1585,4 m/s,
  γ 1,1338, M 27,829 kg/kmol); Bartz ısı transferi bağıntısı aynı koşunun
  donmuş oda γ'sını (1,1862) kullanır. Varsayılan APCP motoru: deniz
  seviyesi Isp +%0,81, boğaz ısı akısı −%2,78. İki faz modülü, kayıt
  yoğuşkan fazı zaten içeriyorsa "yalnız gaz" etkin özelliklerini artık
  yayımlamaz (yoğuşkanı iki kez sayardı).
- **Katı sayfa varsayılanları aynı APCP kaydından gelir.** Taze katı
  sayfada: yoğunluk 1850 → 1810 kg/m³, oda sıcaklığı 3200 → 3399,65 K,
  γ 1,25 → 1,1338, c* 1550 → 1585,4 m/s; deniz seviyesi Isp 206,14 →
  217,60 s, ortalama itki 3134,95 → 3236,30 N, itici kütlesi 6,611 →
  6,468 kg. Düzeltilmiş oda sıcaklığıyla grafit nozul artık nozul aşırı
  sıcaklık uyarısı alır.
- **Güvenlik analizi: itici sınıfı motorun kendi iticisinden.** Kaynaklı
  TNT eşdeğeri olmayan sınıflarda (güvenlik panelinde hibrit, KNDX gibi
  şeker iticiler, kara barut) TNT eşdeğeri, patlama mesafesi, parça menzili
  ve tahliye mesafesi kaynağı olmayan bir sayı yerine gerekçesiyle
  "değerlendirilmedi" olur. API ve PDF raporu panelle aynı kuralı izler:
  katı itici sınıfını katalog ailesinden alır (kompozit, çift bazlı), bu
  yüzden KNDX artık kompozit sayılmaz (1,011 kg TNT, 1600 m tahliye, ORTA →
  değerlendirilmedi, DÜŞÜK). Paneldeki örnek hibrit: 5,435 kg TNT ve
  1600 m tahliye → değerlendirilmedi. APCP ve sıvı sonuçları değişmedi.
- **Güvenlik paneli: fiziksel olmayan cidar sıcaklığından ısıl hüküm
  yok.** Soğutmasız hibritte ısı modülü kendi denge cidar sıcaklığını
  fiziksel değil diye imler; panel artık bu sıcaklığı göndermez, ısıl hüküm
  ve basınç-artı-ısıl birleşik emniyet katsayısı gerekçesiyle bekletilir.
  Örnek hibrit: KRİTİK (birleşik emniyet katsayısı 0,713) → ORTA, kısmi.
- **Yapısal hükümler modelin geçerlilik sınırına uyar.** Yapısal model
  geçerlilik aralığının dışındaysa (örneğin çözülen cidar sıcaklığı yapısal
  analize ulaşmıyorsa) onay hükümleri gerekçesiyle bekletilir: uç kapağı
  "boyutlandırıldı ve doğrulandı", boyutlandırma kipindeki onay, analiz
  güvertesindeki hüküm rozeti ve yapısal güvenlik analizinin tasarım hedefi,
  yorulma ve burkulma hükümleri. Sayılar görünür kalır. 52 vakalık önce/sonra
  ölçümünde 23 vaka "GÜVENLİ · ÇOK DÜŞÜK"ten "DEĞERLENDİRİLMEDİ"ye geçti;
  hiçbir sayı değişmedi, hiçbir başarısız hüküm gizlenmedi. Sıvı yapısal
  kartı, geri okunan tasarım emniyet katsayısı hedefini ve işletme çember
  emniyet katsayısını ayrı adlarla gösterir.
- **Analiz güvertesinin yapısal paneli motorun kendi tasarım hedefini
  kullanır.** Güverte malzeme varsayılanı yerine motorun tasarım emniyet
  katsayısı hedefini gönderir ve kaynağını adıyla yazar. Katı örnek: hedef
  4,0 → 3,0, tasarım hedefi hükmü GÜVENLİ · ÇOK DÜŞÜK → KABUL EDİLEBİLİR ·
  DÜŞÜK; sıvı örnek: 3,0 → 2,5, KABUL EDİLEBİLİR · DÜŞÜK → SINIRDA · ORTA.
- **Yapısal FEA yük modeli.** `/api/fea/structural` yakınsak ve ıraksak
  bölümü 1B izantropik statik basınçla yükler (γ motor sonucundan; yedek
  olarak beyanlı sabit oda basıncı), kapalı uç kuvvetini uygular ve her
  koşuda kuvvet dengesini denetler (tolerans uç kuvvetinin 1e-3'ü; tutmazsa
  hüküm bekletilir). Yanıt kapsamı yazar: yalnız basınç yükü; ısıl gerilme
  ve sıcaklığa bağlı dayanım kapsam dışı. Örnek motorlarda en küçük emniyet
  katsayısı: sıvı 2,23 → 3,63 (HRMA'nın artık boyutlandırdığı cidarla,
  aşağıda), hibrit 5,53 → 9,22, katı 1,03 → 2,19; mesnet yerine duyarlı diye
  bekletilen üç hüküm de artık veriliyor.
- **Sıvı motor kamara cidarını HRMA boyutlandırır.** Sıvı sayfası artık
  kaynaksız 5 mm cidar ön-dolgusu koymaz; cidarı motor boyutlandırır
  (örnek: 2 mm).
- **Rejeneratif soğutma: tek sıcaklık sınırı.** Soğutma hükmünün servis
  sınırı, erime sıcaklığı yerine ısıl modüldeki gibi malzemenin izin
  sıcaklığıdır (bakır 1358 → 723 K, Inconel 718 1533 → 977 K); izin ile
  erime sıcaklığı arasındaki cidar artık UYARI değil GÜVENSİZ alır. Tepe
  cidar sıcaklıkları, ısı yükleri ve basınç düşüşleri değişmedi.
- **Rejeneratif soğutma girdileri motordan gelir.** Soğutma paneli artık
  kaynaksız değer ön-doldurmaz (80 kanal, kanal genişliği ve derinliği,
  astar kalınlığı, su soğutucusu, giriş sıcaklığı ve basıncı): her alan
  motorun yayımladığı değeri alır ya da boş ve zorunlu kalır; zorunlu alan
  boşken istek gönderilmez. `/api/regen-cooling`, `n_channels` taşımayan
  isteğe adlı 400 döner. Soğutucu istasyon marşı koşamadığında ısıl hüküm
  sessizce kaybolmaz, bunu bir uyarı söyler.
- **Süperkritik hidrojen soğutması.** Kanal boyutlandırması ve yayımlanan
  soğutucu hızı aynı hidrojen yoğunluğunu kullanır; önceden boyutlandırma
  sıvı yoğunluğu kullanıyordu ve yayımlanan hız, boyutlandırmanın
  tutturduğunu sandığı hedefin yaklaşık dört katıydı. Hız hedefinin kendisi
  Bilinen sınırlamalar'da.
- **Sıvı sayfasında yakıt yoğunluğu.** Yakıt değişince başka yakıtın
  yoğunluğu girdi diye gitmez (örneğin LH2 için RP-1'in 810 kg/m³'ü); elle
  girilen değer korunur, seçili yakıt farklıysa uyarı gösterilir. Basınç
  beslemeli çevrimde turbopompa verimi ve gaz üreteci sıcaklığı
  kullanılmayan girdiler diye listelenir.

### CAD

- **CAD analiz geometrisinden çizilir (tek kaynak).** Bağımsız bir CAD
  denetimi, dışa aktarıcının yer yer analiz edilen motoru değil kendi
  kuralını çizdiğini bulmuştu (yıldız tane düz boru çiziliyordu, itici
  hacmi +%23,3; hibrit nozul eti STEP'te 3 mm, STL'de 7,19 mm; tank hacmi
  1,23 kat). Bunlar düzeltildi.
- **Fail-closed imalat çıktısı.** Yapısal emniyet katsayısı 1'in altındaysa
  ya da yapısal model geçerlilik aralığının dışındaysa her imalat çıktısı
  (STEP, DXF, çizim PDF'i, STL paketi, tek STL, tam paket,
  `/api/export-cad`) sunucuda aynı adlı gerekçelerle reddedilir (örnek
  hibrit: çizim PDF'i, STL paketi ve `/api/export-cad` 200 → 422). CAD
  çekirdeğinin henüz sadık çizemediği yıldız ve finocyl taneler, dairesel
  port diye dışa aktarılmak yerine gerekçesiyle reddedilir.
- **Her dışa aktarım için tek nozul konturu denetimi.** Geri dönen kontur,
  pozitif olmayan ya da okunamayan boğaz eğrilik yarıçapı ya da okunamayan
  kontur açısı, sessiz bir varsayılana (açılarda 30°, 8° ya da 15°) dayanan
  dosya yerine adlı 422 alır; sunucu hatasına yol açan bozuk kontur bloğu da
  422 alır. Katı ve sıvı CAD paketleri motorun yayımladığı nozul konturunu
  çizer; DXF sınıf tablosu sabit sırayla yazılır (zaman damgası dışında her
  koşuda aynı dosya).
- **Tank modeli** beyanlı düz uçlu silindirdir; parça adları kaynağını
  taşır.
- **Pürüzsüz nozul yüzeyi.** STEP'teki nozul, yüze yakın konik yüzey yerine
  aynı kontur noktalarından geçen tek bir B-spline dönel yüzeydir. Boy ve uç
  çapları bit-aynı; boğaz farkı 1e-7 mm'nin altında. Bozuk kontur sunucu
  hatası yerine adlı 422 hatası döndürür. Paket README'si, bir CAD aracının
  bu yüzeyler için varsayılan hacminin %0,04–1,5 sapabileceğini ve HRMA'nın
  nozul kütlesinin dosyadan okunmadığını yazar.

### Fırlatma sahası haritası

- **Ayrıntılı çevrimdışı harita** (yaklaşık 13 MB paketli varlık): ayrıntı
  düzeyli vektör sınırlar ve yakınlaştırdıkça görünen şehir ve ülke
  etiketleri. Etiketler kar ve buz üstünde okunur kalır; bütün küre
  gösterilirken sayıları sınırlanır.
- **Paketli Dünya görüntüsü.** Paketli NASA Blue Marble dokusu (Aralık
  2004, ekvatorda piksel başına yaklaşık 2 km, 1073 karo, 15,9 MB) hiçbir
  ağ isteği olmadan çizilir; çevrimiçi karolar yalnız daha ince ayrıntı için
  ve yalnız aşağıdaki anahtar açıkken istenir. Harita notu, vektör kıyı
  çizgisi ile görüntü arasındaki ölçülmüş kaymayı yazar (Kennedy kıyısında
  NASA GIBS karosuna karşı: medyan 598 m, 90. yüzdelik 1,3 km).
- **Yer adları**, listelenmiş kısa bir ad kümesinde Türkiye'nin resmî
  kullanımına uyar (örneğin *Türkiye*, *Güney Kıbrıs Rum Yönetimi*,
  *Elazığ*, *Akmescit*); Kırım Ukrayna'nın parçası olarak gösterilir. Öteki
  bütün adlar Natural Earth 5.1.2 ile aynıdır; düzeltmeler haritanın künyesine
  yazılır.
- **Uydu görüntüsü için gizlilik anahtarı.** Görüntü karolarının indirilmesi
  **varsayılan olarak kapalıdır**. Siz açana kadar sunucu dışarıya hiç istek
  atmaz; yerel önbellekteki karolar yine gösterilir.

### Güvenlik

- Yerel API köken kapıları sıkılaştı: başka bir yerel porttaki sayfa yan
  etkili GET uçlarını artık tetikleyemez; portsuz Origin sunucunun gerçek
  portuyla denetlenir.
- İstek gövdesi: her uç için tek 32 MiB sınırı, gövde tamponlanmadan önce
  web sunucusunda uygulanır (sınırı aşan istek JSON 413 alır); konfigürasyon
  ve bileşim listelerinde istek başına kalem sınırı; en çok 100 eşzamanlı
  bağlantı.
- İçerik Güvenliği Politikası'na `object-src 'none'` ve `base-uri 'none'`
  eklendi. Sunucu ve hata metinleri sayfaya girmeden önce kaçışlanır.
- Yükleme ekranları (STEP, OpenRocket `.ork`, motor dosyası, CSV) dosyayı
  göndermeden önce boyut sınırını denetler; sınır sunucudan okunur.
  Doğrulama panelinin yeniden karşılaştırması da denetler; sınırı aşan
  istek (413) okunur bir iletiyle gösterilir.
- Otomatik API bulandırma (fuzz) koşusu (104 uç yöntemi üstünde 3090 istek)
  456 bulgudan 0'a indi: bozuk girdi artık sunucu hatası yerine gerekçeli
  400/422 alır.
- Dışa aktarım uçları bozuk bir iç blokta artık çökmez. İhracat yükünün
  bir iç bloğu (örneğin `design_summary`, `structural_analysis`,
  `heat_transfer_analysis.wall_analysis`, `grain_design`) sözlük yerine
  metin ya da liste gelince dokuz dışa aktarım ucu HTTP 500 veriyordu
  (ölçüldü: 10 720 isteğin 108'i). Artık alanın tam yolunu adlandıran 422
  `invalid_export_geometry` döner; okunamayan `nozzle_angles` bloğu nozul
  konturu kapısının reddini alır. STL paketi ucu, boğaz ya da çıkış çapı
  yayımlanmamışsa 500 yerine montaj üreticisinin adlı reddini döndürür
  (422, `/api/export-cad` gibi).

### Arayüz

- Grafik ve panel metinleri arayüz dilini izler (Türkçe/İngilizce).
- Kararlılık ve geçici rejim panelleri sayılarının nereden geldiğini
  gösterir.
- **OpenRocket köşesi:** OpenRocket özellikleri sağ kenar çubuğunda tek bir
  sekmede toplandı. RASP motor adı kasa çapı yerine itki sınıfı harfi ile
  ortalama itkiden oluşur (thrustcurve.org biçimi); varsayılan motor adı
  OpenRocket okurken artık kırpılmıyor.
- Bağlantısız `/simple` ve `/uzaytek` sayfaları kaldırıldı.
- Eski bir sürümle kaydedilmiş proje uyarısı arayüz dilini izler. CFD
  süre notu, besleme sistemi grafik etiketleri ve yeni "Oksitleyici tankı
  (gerekli basınç)" etiketi Türkçedir; Türkçe arayüz "nozzle" için her
  yerde tek terim (nozul) kullanır.
- FEA paneli yük modelini (basınç dağılımı, kapalı uç kuvveti, kapsam,
  kuvvet dengesi) gösterir; yük uygulanan uç bandındaki tepeyi hüküm değil
  tanı diye işaretler.
- Katı uç, motor iticisini itici adından ya da yanma hızı ön ayarından
  aldığında artık "APCP, uç varsayılanı" beyan etmez (örnek KNDX motoru);
  sayılar değişmedi.
- Türkçe ve İngilizce kullanma kılavuzlarına (PDF) yeni ekran görüntüleriyle
  v3.0 bölümleri eklendi: bekletilen hükümler, ısıl sonuçlar, panel
  künyeleri, hibrit uyarıları, CAD dışa aktarım retleri ve harita.
- Türkçe kipte artık İngilizce kalan metin ve nokta ondalık yok: katı
  Yapısal sekmesi (risk sınıfları, kapak cıvatası notu), analiz
  güvertesinin yapısal ve ısıl panelleri, fırlatma sahasında araç
  künyesi ve yükleme uyarıları, belirsizlik panelinin koşulları ve hibrit
  uyarılarındaki malzeme adları; yüzde Türkçe biçimde (%16,2).
- Isı modülü kendi denge cidar sıcaklığını fiziksel değil diye
  işaretlediğinde güvenlik paneli, ısıl eksenin bu yüzden
  değerlendirilmediğini söyler (önceden eksik girdi gibi görünüyordu).
- Belirsizlik analizi: sıfır çap girdisi, motor hesabında olduğu gibi
  "otomatik" demektir; örnek hibrit motorun belirsizlik koşusu önceden
  `non_physical_uncertainty_input` ile düşüyordu.
- CFD süre notu: viskoz koşu artık viskoz en kötü hâl tablosunu söyler
  (önceden viskozsuz değeri söylüyordu; örneğin yüzlerce saniye süren
  koşularda 19,9 s). İki tablo tek protokolle yeniden ölçüldü (yineleme
  tavanı, şoklu geri basınçlı vaka, en az iki tekrar); varsayılan seviye
  numba olmadan 18,5 s ölçüldü. Viskoz tablo yüklü makineden gelir ve
  temkinli bir üst sınırdır; not bunu söyler.

### Kararlılık

- Önbellekteki bir NASA CEA nesnesi, RocketCEA'nın kendi önbelleği
  boşaltıldıktan sonra yeniden kullanılabiliyordu; bu, bazı sıvı motor
  koşularını kendinden önce ne koştuğuna göre düşürüyordu. Önbellek kaydı
  artık denetlenip yeniden kurulur.
- NASA CEA çağrıları ortak kilidin dışında koşuyordu. Dört paralel iş
  parçacığında 5 koşunun 5'i sessizce yanlış sayı döndürdü (örneğin bir
  etanol vakasında deniz seviyesi Isp 234,909 → 200,404 s). Çağrılar artık
  aynı kilidi tutar; seri sonuçlar bit-aynı. RocketCEA kuruluyken bir çağrı
  başarısız olursa tablo verisine geçiş sessiz olmaz, uyarıyla bildirilir;
  sıvı motor bunu RocketCEA yok diye değil, başarısız çağrı diye bildirir.
  Yalıtılmış NASA CEA veri dizini kullanılmadan önce denetlenir, başka bir
  bileşen onu kaydırmışsa yeniden sabitlenir.

### Önceki kampanya (2.6.27 diye duyurulan)

Bu sürümde ayrıca şunlar var; her birinin önce/sonra sayıları uygulama
içi notlarda: ablasyon fiziği yeniden kuruldu (üfleme blokajı sabit 0,5
yerine B′'den çözülür; yüzey sıcaklıkları düzeltildi); sayfa artık katalog
yanma hızını ezmiyor; basınçlandırıcı boyutlandırmasında gerçek gaz; hibrit
patlayıcı eşdeğeri tablodan okunmaz, türetilir; PDF raporunun güvenlik
bölümü besleniyor; sıvı motorda su koçu (2 → 7 itici), dump soğutma ve güç
dengesi; FEA köprüsünde kapama tabanı payı ve ince cidar uyarısı; burkulma
zarfı ve kopma basıncı adı; KNDX ve KNSB termokimyası CEA tabanında; boş
form alanları artık gönderilmez ve her uç uyguladığı varsayılanları beyan
eder.

### Bilinen sınırlamalar

- **Geri basınçlı 2B CFD** (`POST /api/cfd/nozzle`, `Pb_Pa`): çıkış sınır
  koşulu, akışın ters döndüğü hücrelere de geri basıncı dayatır. Şoklu,
  aşırı genişlemiş vakalarda ölçüldü: 42 koşunun 22'sinde son alanda çıkışta
  geri akış var. Bu vakaların hepsi zaten "yakınsamadı / plato" ve `suspect`
  ayrılma hükmüyle döner, hiçbiri doğrulanmış diye sunulmaz; bu koşularda
  çıkış bölgesindeki duvar basıncını ve ayrılma çıktısını nitel kabul edin.
- **Süperkritik hidrojen soğutucu hızı.** Kanal boyutlandırması 40 m/s
  sıvı soğutucu hız hedefini (NASA SP-8087) süperkritik hidrojene de
  uygular; hidrojene özgü hedef 3.1'e planlandı. Sonuç güvenli yönde sapar
  (daha derin kanal, daha düşük soğutucu tarafı ısı transferi, daha sıcak
  öngörülen cidar; örnek LH2 varyantı: tepe sıcak cidar 1387 K yerine
  1478 K, iki durumda da GÜVENSİZ), yani yanlış bir GÜVENLİ üretmez.
- **API ve PDF raporunda hibrit TNT eşdeğeri.** Türetilmiş çarpan kilogram
  oksitleyici başınadır, ama uç ve rapor oksitleyici kütlesi girdisi
  taşımadığı için toplam itici kütlesine uygulanır. Sonuç ihtiyatlı yönde
  fazladır (örnek hibrit: 5,765 kg TNT; oksitleyici kütlesiyle yaklaşık
  5,05 kg). Güvenlik paneli hibritte bunu değerlendirmez (yukarıya bakın).
- Yıldız ve finocyl taneler CAD'e aktarılmaz (yukarıya bakın).
- Montaj STL'i kapalı bir katı değildir; CAD işi için STEP kullanın.

### Bu sürümde yok (3.1 ve sonrasına planlandı)

- C++ çözücü çekirdeği; 3B CFD ve 3B FEA; yanmalı (reaktif) CFD; modal FEA.
- Elle çizilmiş ayrıntıda CAD: enjektör kafası ve domu, flanşlar ve cıvata
  dairesi, O-ring kanalları, portlar, rejeneratif soğutma kanalları, gerçek
  port kesiti, kapalı STL.
- Sistem parçaları: turbopompa, ön yakıcı, besleme hatları, valfler,
  gimbal; egzoz plümü görselleri.
- Daha sıkı harita kodlaması.
- APCP için yalnız gaz iki faz özellikleri; yalnız sayı taşıyan yapısal
  alanlarda (sıvı kütle zinciri, kalınlık, kütle, T/W) geçerlilik bayrakları.

---

Earlier versions: see `packaging/release_notes_v*.md` and the in-app
Release Notes window. · Önceki sürümler: `packaging/release_notes_v*.md`
ve uygulama içi Sürüm Notları penceresi.
