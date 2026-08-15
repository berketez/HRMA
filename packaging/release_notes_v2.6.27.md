<!--HRMA-LANG:en-->
# HRMA v2.6.27 — Physics correctness campaign (in development)

This version is being built party by party on main and has NOT been published
yet: per the release strategy the public release is deferred to the FINAL
build, and this file grows with the campaign. Everything below was measured
before and after; where a number changed, both are written down.

## Ablation physics rebuilt (tenth party)

- **The blowing blockage was a constant 0.5 — the wrong regime's number.**
  psi = 0.5 corresponds to B' of 1.3–2.5, which is atmospheric-entry TPS
  territory; rocket liner operating points sit at B' of 0.02–0.25 where the
  blockage is 0.90–1.00. On an aluminized solid-motor throat the constant
  flipped the sign of the net flux: the model reported zero recession where
  the measurement is 0.124–0.139 mm/s. The blockage is now solved
  self-consistently from B' (Aerotherm/CMA reduction, lambda = 0.4) and its
  derivation is published next to the result.
- **no_net_heating no longer publishes a 0.0 mm liner as "sized".** Zero
  recession does not mean zero thickness: the liner is then governed by the
  case/bond-line temperature limit (NASA SP-8093 practice), which this
  Level-1 module does not model — so no thickness is published, and the
  reason is stated.
- **Surface temperatures corrected**: silica-phenolic 1900 → 2050 K (the old
  value sat below the measured range), EPDM 800 → 2300 K (800 K was the
  decomposition onset, not a surface temperature), carbon-phenolic 3000 K
  kept but relabelled as a calibrated effective temperature with its
  validation point (under-predicts measured throat erosion by 20–28%; the
  1.5 design margin absorbs that).
- **A 10× misread of NASA TM-107041 fixed.** The validation band's upper end
  was quoted as 0.082 mm/s; the report's Table 2 column carries a 10^-2
  multiplier and the real value is 0.00822 mm/s (cross-checked against the
  mil/s column). The band now lives in one place and the validation test
  reproduces the report's actual test condition (25.4 mm throat, 11.38 bar,
  GH2/GOX, ~2386 K, 164 s).
- **Wrong monograph citation fixed everywhere**: "SP-8091" is "The Planet
  Saturn"; internal insulation is SP-8093 and nozzle liners are SP-8115.
- **Solid closures now sized per station with the right material family**:
  forward dome EPDM (SP-8093: dome insulation is an elastomer), nozzle entry
  silica-phenolic (SP-8115 class), each driven by its own station's Bartz
  coefficient — previously both closures published the same throat-flux
  number and a nozzle-liner material.

## The page no longer overrides the catalog burn rate

An untouched solid-motor form silently sent a = 0.005, defeating the
backend's catalog resolution (a = 0.0022334 for APCP): the same motor got a
2.3× different thrust curve and a spurious off-catalog warning. Untouched
fields are no longer sent; the backend resolves the catalog value and
declares its source.

## Real-gas blowdown pressurant sizing

The blowdown branch assumed ideal gas; at 300 bar storage the trapped-mass
error is ~14% (helium Z = 1.141 at 293 K). The compressibility factor is now
applied with the same declaration pattern the regulated branch already used.

## Platforms

- A Lean 4 formal-verification platform now lives in `formal/`: 19 theorems
  guarding solver assumptions, a machine-readable registry linking each
  theorem to the code line it protects, and a gate that fails when the link
  rots (it caught 3 of 4 stale line references on its first run).
- Process, scope and architecture documentation under `docs/surec/`,
  `docs/kapsam/`, `docs/mimari/` — written from measurements, kept live by
  a documented liveness rule.

<!--HRMA-LANG:tr-->
# HRMA v2.6.27 — Fizik doğruluk kampanyası (geliştirme sürüyor)

Bu sürüm main üzerinde parti parti inşa ediliyor ve HENÜZ YAYIMLANMADI:
yayın stratejisi gereği kamuya sürüm FINAL derlemesine ertelendi; bu dosya
kampanyayla birlikte büyüyor. Aşağıdaki her şey önce/sonra ölçüldü; sayı
değiştiyse ikisi de yazıldı.

## Ablasyon fiziği yeniden kuruldu (onuncu parti)

- **Üfleme blokajı sabit 0,5'ti — yanlış rejimin sayısı.** psi = 0,5,
  B' = 1,3–2,5 demektir; bu atmosferik giriş TPS bölgesidir. Roket astarı
  çalışma noktaları B' = 0,02–0,25'te oturur ve blokaj 0,90–1,00'dir.
  Alüminyumlu katı motor boğazında sabit katsayı net akının İŞARETİNİ
  çeviriyordu: ölçüm 0,124–0,139 mm/s iken model sıfır gerileme diyordu.
  Blokaj artık B'den öz-tutarlı çözülür (Aerotherm/CMA indirgemesi,
  lambda = 0,4) ve türetimi sonucun yanında yayımlanır.
- **no_net_heating artık 0,0 mm astarı "boyutlandı" diye yayımlamaz.**
  Sıfır gerileme sıfır kalınlık demek değildir: astar o durumda kasa/bağ
  hattı sıcaklık sınırıyla belirlenir (NASA SP-8093 pratiği) ve bu Seviye-1
  modül onu modellemez — kalınlık yayımlanmaz, gerekçesi yazılır.
- **Yüzey sıcaklıkları düzeltildi**: silika-fenolik 1900 → 2050 K (eski
  değer ölçüm bandının altındaydı), EPDM 800 → 2300 K (800 K bozunma
  başlangıcıydı, yüzey sıcaklığı değil), karbon-fenolik 3000 K korundu ama
  künyesi düzeltildi (kalibre edilmiş etkin sıcaklık; ölçülen boğaz
  erozyonunu %20–28 eksik tahmin eder, 1,5 tasarım payı bunu yutar).
- **NASA TM-107041'in 10× yanlış okunması düzeltildi.** Doğrulama bandının
  üst ucu 0,082 mm/s diye geçiyordu; raporun Tablo 2 sütunu 10^-2 çarpanlı
  ve gerçek değer 0,00822 mm/s (mil/s sütunuyla çapraz doğrulandı). Bant
  artık tek yerde tanımlı ve doğrulama testi raporun GERÇEK koşulunu
  kullanıyor (25,4 mm boğaz, 11,38 bar, GH2/GOX, ~2386 K, 164 s).
- **Yanlış monograf künyesi her yerde düzeltildi**: "SP-8091" aslında
  "Satürn Gezegeni" monografıdır; iç yalıtım SP-8093, nozul astarı SP-8115.
- **Katı kapaklar artık istasyon bazında ve doğru malzeme ailesiyle
  boyutlanıyor**: ön kubbe EPDM (SP-8093: kubbe yalıtımı elastomerdir),
  lüle girişi silika-fenolik (SP-8115 sınıfı); her biri kendi istasyonunun
  Bartz katsayısıyla sürülür — eskiden iki kapak aynı boğaz-akısı sayısını
  ve bir nozul astarı malzemesini yayımlıyordu.

## Sayfa artık katalog yanma hızını ezmiyor

Dokunulmamış katı motor formu sessizce a = 0,005 gönderiyor ve arka ucun
katalog çözümünü (APCP için a = 0,0022334) etkisizleştiriyordu: aynı motor
2,3 kat farklı itki eğrisi alıyor ve sahte katalog-dışı uyarısı görüyordu.
Dokunulmamış alan artık gönderilmiyor; arka uç katalog değerini çözüp
kaynağını beyan ediyor.

## Basınçlandırıcı boyutlandırmasında gerçek gaz

Blowdown dalı ideal gaz varsayıyordu; 300 bar depolamada hapsolmuş kütle
hatası ~%14 (helyum Z = 1,141, 293 K). Sıkıştırılabilirlik faktörü artık
regüle dalın kullandığı beyan deseniyle uygulanıyor.

## Platformlar

- `formal/` altında Lean 4 biçimsel doğrulama platformu: çözücü
  varsayımlarını koruyan 19 teorem, her teoremi koruduğu kod satırına
  bağlayan makine-okunur kayıt defteri ve bağ çürüyünce kırılan bir kapı
  (ilk koşusunda 4 satır bağından 3'ünün kaydığını yakaladı).
- `docs/surec/`, `docs/kapsam/`, `docs/mimari/` altında ölçülerek yazılmış
  süreç, kapsam ve mimari dokümantasyonu — belgelenmiş canlılık kuralıyla
  güncel tutuluyor.
