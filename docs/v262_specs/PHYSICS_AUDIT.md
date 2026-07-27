# HRMA fizik denetimi — satır satır denklem kataloğu

Kaynak: 10 salt-okunur ajanla yapılan denklem/kaynak denetimi (2026-07-26).
Her bulgu koddaki denklemi, olması gerekeni, gerçek kaynağını ve ÖLÇÜLEN
sayısal etkiyi taşır. Ajanlara "emin değilsen YANLIS deme" talimatı verildi.

**Toplam 195 bulgu.** Düzeltme gerektiren: 106. Kod doğru: 61. Doğru ama kaynaksız: 28.

| Ciddiyet | Adet |
|---|---|
| KRITIK | 4 |
| YUKSEK | 26 |
| ORTA | 55 |
| DUSUK | 110 |

| Hüküm | Adet |
|---|---|
| DOGRU | 61 |
| GECERSIZ_ZARF | 56 |
| YANLIS_FORMUL | 34 |
| KAYNAKSIZ_AMA_DOGRU | 28 |
| YANLIS_KATSAYI | 14 |
| YANLIS_BIRIM | 1 |
| SAHTE_KAYNAK | 1 |

---


## KRITIK

### [ ] F001 — `hrma/engines/injector_design.py::swirl_solve`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
coef = np.sqrt(32.0 / np.pi ** 2)  →  K = coef·√((1−X)³/X²)
```

**Olması gereken:** Katsayı ters çevrilmiş: √(32/π²)=1.8006 yerine √(π²/32)=π/(4√2)=0.55536 olmalı. Doğru Giffen–Muraszew/Taylor bağıntısı K = (π/(4√2))·√((1−X)³/X²), K = A_p/(D_s·d_o). Bunu kendi türetimimle (maksimum debi ilkesi + hava çekirdeği yüzeyinde Bernoulli) doğruladım ve Abramovich formu sinα = 2μA/(1+√(1−φ)), A = π/(4K), φ = 1−X ile birebir örtüştüğünü teyit ettim. Kanıt kod içinde: aynı fonksiyondaki sinθ = (π/2)·Cd/(K(1+√X)) bağıntısı Lefebvre'in K = A_p/(D_s·d_o) tanımına aittir; iki bağıntı 32/π² = 3.242 kat farklı K tanımı kullandığı için modül kendi kendisiyle çelişiyor.

**Kaynak:** Giffen & Muraszew (1953); Lefebvre & McDonell, Atomization and Sprays 2. baskı Böl. 6 (simplex atomizör, K = A_p/(D_s·d_o), Cd = √((1−X)³/(1+X)), sinθ = (π/2)Cd/(K(1+√X))); Abramovich geometrik karakteristik A = π/(4K)

**Sayısal etki:** ÖLÇÜLDÜ (scratchpad/swirl_check.py). Kod vs referans: K=0.3 → Cd 0.094 vs 0.240 (2.54x düşük), θ 15.4° vs 46.1°; K=1.0 → Cd 0.245 vs 0.495 (2.02x), θ 12.8° vs 29.8°; K=0.2 → 2.68x. Cd doğrudan enjeksiyon alanına girdiği için (A = ṁ/(Cd√(2ρΔP))) toplam delik alanı 1.7-2.7 KAT fazla boyutlanıyor. Kodla erişilebilir MAKS sprey yarı açısı 17.5°, referansla 71.2° — gerçek basınç-swirl atomizörleri rutin olarak 30-60° yarı açı (60-120° tam koni) verir. Tam tasarım koşusu (hibrit swirl, ṁ=2 kg/s, Pc=30 bar, N₂O): Cd=0.245, n=39, d=2.49 mm, A=190.4 mm², θ=12.8° — doğru katsayıyla A ≈ 94 mm² olurdu. Koddaki 'theta_target > 16° çözülemez → K=1.0'a düş' geçici çözümü bu hatanın SEMPTOMUDUR, sebebi değil.

### [ ] F002 — `slosh_analysis.py::CylindricalTankSlosh.baffle_damping`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
gamma = 2.83 * exp(-4.60 * d_s/R) * (A_baffle/A_tank)**1.5
```

**Olması gereken:** Miles bagintisi bir de SALKINIM GENLIGI carpani icerir: gamma = 2.83 * exp(-4.60*d_s/R) * (A_b/A_T)^(3/2) * sqrt(eta/R), burada eta cidardaki serbest yuzey dalga genligidir. Kod bu terimi tamamen atlamis, yani ortuk olarak eta/R = 1 (dalga genligi = tank yaricapi) varsaymis; bu, modulun kendi ilan ettigi 'dogrusal kucuk genlik' teorisiyle celisir. API'de (app.py /api/slosh-analysis) genlik girdisi hic yok, yani kullanici duzeltemiyor.

**Kaynak:** Bauer, H.F., NASA MSFC MTP-AERO-62-81 (1962), 'Theory of Fluid Oscillations in a Circular Cylindrical Ring Tank...', Tek Halka Bafl bolumu: 'C sabiti ... yaklasik 2.83 degerindedir', 'Daha buyuk yuzey genligi icin sonumleme orani sqrt(ksi_w/a) ile artar', 'bafl genisligi arttikca sonumleme orani alfa^(3/2) ile artar'. Bagimsiz teyit: NASA 20130000590 (Validation of Slosh Model Parameters and Anti-Slosh Baffle Designs, 2012), Denklem 10 parametre listesi: 'eta cidarda salkinim dalga genligidir' — Dodge 2000 formu. Ayrica NASA 20170000435 basligi ('...to Small Slosh Amplitudes') genlik bagimliligini dogrudan teyit eder.

**Sayısal etki:** OLCULDU. w/R=0.10, d_s/R=0.05 icin kod zeta=0.1862 (kritigin %18.6'si!) veriyor. Tam Miles: eta/R=0.20 -> 0.0833 (2.24x fazla), eta/R=0.10 -> 0.0589 (3.16x), eta/R=0.05 -> 0.0416 (4.47x), eta/R=0.02 -> 0.0263 (7.07x). Tek halka bafl icin %18.6 sonumleme fiziksel olarak absurt (olculen degerler tipik %1-10). recommend_baffle(0.01, d/R=0.10) w/R=0.0159 oneriyor; eta/R=0.05'te dogrusu w/R=0.0438 — bafl 2.8x dar cikiyor. Yon: HER ZAMAN sonumlemeyi FAZLA tahmin ediyor => slosh kararliligi icin KONSERVATIF DEGIL. Modulun ilan ettigi +/-2x bandi (_MILES_BAND_FACTOR) bu hatayi kapsamiyor. Mevcut tests/test_slosh.py yalnizca monotonluk kontrol ettigi icin hata testlerden geciyor.

### [ ] F003 — `structural_analysis.py::_analyze_chamber_wall`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
allowable = yield_der/safety_factor ; min_t = P*r/allowable ; rec_t = 1.2*min_t ; hoop = P*r/rec_t ; SF = yield_der/hoop
```

**Olması gereken:** DONGUNUN TAM YERI BURASI. rec_t'yi allowable'dan uretip sonra ayni allowable'a gore SF hesaplamak cebirsel olarak SF = safety_factor * 1.2 verir; P, r, D, design_pressure_factor ve malzeme dayanimi TAMAMEN sadelesir. Dogru yapi IKI AYRI MOD olmali: (1) BOYUTLANDIR (size): t_req = P*r/(sigma_y_der/SF_hedef) — cikti yalnizca kalinlik onerisi, SF raporlanmaz; (2) DOGRULA (verify): motor_data['wall_thickness'] (KULLANICININ GERCEK CIDARI) girdi alinir, sigma = P*r/t_gercek hesaplanir, SF = sigma_y_der/sigma raporlanir. Su an analyze_structure 'wall_thickness' anahtarini stress zincirinde HIC okumuyor (yalnizca _estimate_wall_delta_T'de 5 mm varsayilan olarak kullaniliyor), yani DOGRULAMA MODU YOK. Ayrica materials_db'deki 'safety_factor' bir MALZEME OZELLIGI DEGIL, tasarim/otorite kararidir; malzeme kaydindan cikip cagirana (design_safety_factor argumani) tasinmali. 1.2 imalat payi da kaynaksiz; ayri ve belgeli bir imalat/korozyon payi (ASME UG-25 corrosion allowance benzeri) olmali.

**Kaynak:** Yontem hatasi — kaynak gerekmez. Boyutlandir/dogrula ayrimi icin ASME BPVC VIII-1 UG-27 (t hesabi) + UG-98/MAWP (mevcut t'den geri hesap) ikilisi referans desendir; ayni desen bu depoda pressure_vessel.py::analyze icinde DOGRU kurulmus (wall_thickness_mm verilirse dogrular, None ise boyutlandirir).

**Sayısal etki:** OLCULDU. steel_4130, D=150 mm: Pc = 5 / 20 / 50 bar icin safety_factor_pressure = 4.8000 / 4.8000 / 4.8000 (tamamen ayni) ve pressure_hoop_stress = 95.54 MPa (tamamen ayni). design_pressure_factor 1.0->1.5 degistirildiginde de SF = 4.8000 sabit. Yani SF = safety_factor(4.0) * 1.2 = 4.8 birebir. Yalnizca t/r >= 0.1'de Lame devreye girince kirilir (Pc=100 bar -> 4.4272; 500 bar -> 3.1933) — bu da gercek bir marj degil, kalin-cidar duzeltmesinin sizmasidir. inconel_718 (safety_factor=3.0) -> SF = 3.6000 = 3.0*1.2. Tautoloji %100 dogrulandi.

### [ ] F004 — `structural_analysis.py::_analyze_end_caps`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
bolt_circle_stress = pressure * (bolt_circle_diameter/2) / flat_head_thickness ; head_safety_factor = allowable_stress / bolt_circle_stress
```

**Olması gereken:** P*R/t bir SILINDIR ince-cidar hoop formuludur; DUZ DAIRESEL PLAKAYA (kapak) ve ustelik civata dairesi yaricapina uygulanmasinin Roark, Shigley veya ASME'de karsiligi YOKTUR. Kapak zaten bir satir yukarida duz-plaka egilme formulunden (sigma = 3P*a^2*(3+nu)/(8t^2)) boyutlandirildigi icin o kalinlikta gercek tepe gerilme TANIM GEREGI allowable'a esittir ve gercek SF = safety_factor = 4.00'dur. Dogrusu: (a) kapak civata dairesinden disari flans momenti tasiyorsa ASME VIII-1 Appendix 2 flans analizi, (b) civatali duz kapak icin UG-34 t = d*sqrt(C*P/(S*E) + 1.9*W*h_G/(S*E*d^3)) (C=0.3, ikinci terim civata momenti), (c) basit kontrol icin plaka egilme gerilmesinin kendisi. Ayrica head_safety_factor 'flat' kalinliktan hesaplanirken recommended_type cogu zaman 'dished' donuyor — raporlanan SF onerilmeyen kapak tipine ait.

**Kaynak:** Roark's Formulas for Stress and Strain, Tablo 11.2 (duz dairesel plaka, uniform yuk); ASME BPVC VIII-1 UG-34 (civatali duz kapaklar) ve Appendix 2 (flans). Koddaki formul icin kaynak bulunamadi.

**Sayısal etki:** OLCULDU. steel_4130, D=150 mm, gercek kapak SF'si her basincta 4.00 iken kodun head_safety_factor'u: Pc=5 bar -> 10.284 (2.57x FAZLA gosteriyor), 33 bar -> 4.003 (tesadufen dogru), 50 bar -> 3.252, 100 bar -> 2.300, 150 bar -> 1.878 (2.13x AZ gosteriyor), 300 bar -> 1.328 (3.01x az). Formul sqrt(allowable/P) gibi olcekleniyor. DAHA KOTUSU: Pc >= 50 bar'da bu uyduruk sayi minimum_safety_factor'u YONETIYOR (governing = end_cap) ve Pc >= 150 bar'da tum motoru status='UNSAFE', risk_level='HIGH' ilan ediyor — oysa kapak SF 4.00'a boyutlandirilmis durumda. Kullanicinin gordugu nihai emniyet karari bu formulden cikiyor.


## YUKSEK

### [ ] F005 — `combustion_analysis.py::_fallback_equilibrium_composition`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
composition = {'CO2':0.22,'CO':0.08,'H2O':0.12,'N2':0.54,...}  (istasyona göre sabit); mw_mix = Σ X_i·M_i
```

**Olması gereken:** Ürün bileşimi elemental C/H/O/N/AL girdisinden türetilmeli (en azından basit C→CO2/CO, H→H2O, N→N2 atom dengesi + su-gaz shift). Şu haliyle bileşim girdiden BAĞIMSIZ: LOX/HTPB gibi azotsuz bir çiftte bile ürünlerin %54'ü N2 sayılıyor, dolayısıyla MW her itici çiftinde 29.6 g/mol'e çakılıyor.

**Kaynak:** Kaynak yok — sayılar kod içinde sabit yazılmış, hiçbir referansa dayanmıyor. Doğrusu için Gordon & McBride NASA RP-1311 (denge) ya da en azından atom-denge tabanlı bir kapalı-form çözüm gerekir.

**Sayısal etki:** ÖLÇÜLDÜ (cantera_available=False zorlanarak, RocketCEA referansına karşı): htpb/n2o O/F=6 Pc=20 bar → c* 1541.8 vs CEA 1613.3 (-4.4%), MW 29.6 vs gerçek 25.5. htpb/lox O/F=2 Pc=40 → c* 1551.2 vs 1791.4 (-13.4%), gerçek MW 22.0. paraffin/lox O/F=2.5 → -10.4%. pmma/lox O/F=1.5 → Tc +21.7%, c* -8.9%. ÖNEM: Cantera requirements.txt'te YOK ve packaging betiklerinde hiç geçmiyor; temiz kurulumda bu yol VARSAYILAN olur. (Paketleme teyidi benim kapsamım değil, yalnız sayısal hatayı ölçtüm.)

### [ ] F006 — `correlation_runner.py::_aggregate (+ _cell, _basic_stats)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
cells = [_cell(mt, q, entries, "high_medium") ...] ; "n": len(errors) — her kayıt bağımsız örnek sayılıyor
```

**Olması gereken:** medAPE/bias/RMS'in 'n bağımsız gözlem' yorumu, kayıtların bağımsız olmasını gerektirir. Aynı test kampanyasının/aynı tesisin ardışık atışları sistematik (tesis, enjektör, yakıt lotu, ölçüm zinciri) hatayı PAYLAŞIR; etkin serbestlik derecesi kayıt sayısı değil kampanya sayısıdır. Hücreye en azından 'n_kayit / n_bagimsiz_kampanya' ikilisi yazılmalı, tercihen kampanya-içi ortalama alınıp kampanya düzeyinde istatistik verilmeli (kümelenmiş veri).

**Kaynak:** Klasik kümelenmiş-örneklem (pseudoreplication) sorunu: Hurlbert, 'Pseudoreplication and the Design of Ecological Field Experiments', Ecological Monographs 54(2), 1984 — alan bağımsız, ilke aynı. Roket doğrulamasında karşılığı: ASME V&V 20-2009 Böl. 3 (tekrarlı ölçümlerde sistematik vs rastgele bileşen ayrımı).

**Sayısal etki:** ÖLÇÜLDÜ (tam DB koşusu, hücre başına test_id kaynak öneki sayımı): hybrid c_star n=18 -> 1 kampanya (rezaei2018); hybrid isp n=18 -> 1; hybrid thrust n=18 -> 1; hybrid port_diameter_final n=18 -> 1; hybrid chamber_pressure n=35 -> 2 kampanya; hybrid regression_rate n=35 -> 2 kampanya; solid burn_rate n=27 -> 1 kaynak (nakka1999). Yalnız liquid isp_vac (n=14 -> 14 farklı motor) gerçekten bağımsız. Yani hibrit tarafında bildirilen etkin n, gerçek bağımsız n'nin 18-35 katı; güven aralığı ~sqrt(18)=4.2 ila sqrt(35)=5.9 kat DAR görünüyor. Bir tesise özgü %5 sistematik sapma, n=18 ile 'ölçüldü' gibi raporlanır ama ortalamadan kaybolmaz.

### [ ] F007 — `correlation_runner.py::_cell + to_markdown (record_adapters.py::_run_strand IN-SAMPLE etiketi ile birlikte)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
cell = {..., **_basic_stats(entries), "entries": [{test_id, error_pct, confidence}]}  — adapter_notes ('IN-SAMPLE', 'ZAYIF KANIT') hücreye ve markdown özetine HİÇ taşınmıyor
```

**Olması gereken:** Adaptör, kaydın a-n fitinin kaynak veri setinde olduğunu tespit edip 'IN-SAMPLE: skor bağımsız tahmin değil implementasyon doğrulamasıdır' notunu yazıyor; _run_liquid ise thrust_vac için 'ZAYIF KANIT' notu yazıyor. Ama _aggregate yalnız confidence ve anomaly'ye göre ayırıyor; _cell notları atıyor; to_markdown yalnız not_supported / insufficient_inputs / runner_errors / engine_warnings basıyor. In-sample kayıtlar ana hücreden AYRI bir katmana çıkarılmalı (anomaly katmanı gibi) veya hücreye 'n_in_sample' alanı eklenmeli.

**Kaynak:** Kodun kendi dürüstlük sözleşmesi: record_adapters.py::_run_strand içindeki 'IN-SAMPLE ... skor bagimsiz tahmin degil implementasyon dogrulamasidir' notu ve _run_liquid içindeki 'ZAYIF KANIT' notu. Genel ilke: Hastie, Tibshirani & Friedman, 'The Elements of Statistical Learning', 2. baskı, Böl. 7.2 (training error vs test error).

**Sayısal etki:** ÖLÇÜLDÜ: solid burn_rate hücresinin 27 girişinin 27'si (%100) burn_rate_db.BURN_RATE_LAWS[...]['fit_source_records'] içinde — out-of-sample nokta SIFIR. Hücre medAPE %0.51, RMS %1.99 olarak ana tabloda yayımlanıyor; bu bir tahmin doğruluğu değil, fit'in yeniden üretilmesidir. liquid thrust_vac hücresinin 4 girişinin 4'ü de measured thrust_sl'i TÜKETMİŞ (consumed_measured=['thrust_sl']) — yani hücrenin medAPE %0.2'si adaptörün kendi uyardığı kapanış kontrolüdür. Hafifletici: docs/correlation_report/report.md ve COMMENTARY.md metninde katı için 'in-sample by construction' uyarısı ELLE yazılmış; ancak koşucunun kendi çıktısı (JSON + to_markdown + API) bu uyarıyı taşımıyor, dolayısıyla otomatik tüketen her yol niteliksiz sayıyı görüyor.

### [x] F008 — `correlation_runner.py::run_correlation (+ _score_adapter_result, _basic_stats)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
error_pct = (predicted - measured) / measured * 100   — measurement_uncertainty bloğu HİÇ okunmuyor (grep: dosyada 'uncertain' geçmiyor)
```

**Olması gereken:** Hata yüzdesi formülü doğru, ama doğrulama metriği ölçüm belirsizliğini içermeli. Asgarisi: her skorlanan giriş için |error| ile bildirilen u_ölçüm karşılaştırılıp normalize hata E_n = (tahmin-ölçüm)/(k*u) raporlanmalı; hücre düzeyinde belirsizlik-ağırlıklı bias ve ki-kare uyum ölçütü verilmeli. Şu anda ±%0.81 bildirilmiş bir c* ölçümü ile hiç belirsizlik bildirmeyen (grafikten sayısallaştırılmış) bir ölçüm istatistikte eşit ağırlık taşıyor.

**Kaynak:** Şemanın kendisi: hrma/data/validation_records/SCHEMA.md satır 45 ve 'measurement_uncertainty bloğu' bölümü (value/type/coverage_k/source alanları tanımlı). Metrik tarafı: ISO/IEC Guide 98-3 (GUM) ve ASME V&V 20-2009, 'Standard for Verification and Validation in Computational Fluid Dynamics and Heat Transfer', Böl. 2 (doğrulama karşılaştırma hatası E = S - D ve u_val).

**Sayısal etki:** ÖLÇÜLDÜ: DB'deki 209 kaydın 56'sı measurement_uncertainty bloğu taşıyor; istatistiğe giren 191 skorlanan girişin 108'i (%57) böyle bir kayıttan geliyor. Örnek: tüm hyb-rezaei2018 kayıtları c_star_mps için {'value': 0.0081, 'type':'relative', 'coverage_k': null} bildiriyor — yani ±%0.81. hybrid c_star hücresinin medAPE'si %2.3; ölçüm belirsizliğinin ~3 katı, yani model hatası ölçüm gürültüsünden ayrışabilir durumda ama rapor bunu SÖYLEMİYOR. Tersine liquid thrust_vac hücresinde medAPE %0.2 raporlanıyor; bu değer tipik itki ölçüm belirsizliğinin (%0.5-1) ALTINDA, yani ölçüm çözünürlüğünün altında bir 'doğruluk' iddiası olarak okunuyor. coverage_k null olan kayıtlarda k bilinmediği için ağırlıklandırma yapılamaz — bu da dürüstçe raporlanmalı.

### [ ] F009 — `cycle_power_balance.py::solve_cycle (FFSC dalı, tit_ox ataması)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
tit_ox = float(TIT_DEFAULT_K['ffsc_ox_rich'])   # koşulsuz 750 K, kullanıcı tit_K'si yalnız yakıt miline uygulanıyor
```

**Olması gereken:** Ox-zengin mil TIT'i kullanıcıya açılmalı (ayrı tit_ox_K parametresi). Şu haliyle 481 kg/s'lik ox akışı 750 K ve cp=1091 J/kgK ile sürüldüğü için ox milinin enerji marjı çok dar; çözüm PR ∈ [1.02, 4.0] penceresinde köke ancak zar zor giriyor. Ayrıca türbin gücü doyarken (1-PR^-x) pompa gücü PR ile DOĞRUSAL büyüdüğü için artık fonksiyonunun bir tepesi var; tepe negatife düşünce gerçekte var olan bir motor 'infeasible' ilan ediliyor.

**Kaynak:** TIT bandı için verilen kaynak doğru (Sutton 9. baskı Böl. 6 ORSC, RD-170 ~772 K). Sorun kaynakta değil, sabitin kullanıcıya kapalı olmasında.

**Sayısal etki:** ÖLÇÜLDÜ (Raptor: Pc=300 bar, mdot=650 kg/s, MR=3.6, CH4/LOX). Varsayılanlarla kapanıyor (ox_disch=776.3 bar, artık 2.3e-15). ANCAK: eta_pump=0.65 (dosyanın KENDİ alıntıladığı Sutton 0.65-0.80 bandının alt ucu) -> YAKINSAMADI; eta_turbine=0.65 -> YAKINSAMADI; preburner_injector_dp_frac=0.25 (SP-8089'un 0.15-0.25 bandının üst ucu) -> YAKINSAMADI; gas_injector_dp_frac=0.25 -> YAKINSAMADI. Yani var olan bir motor, eşit derecede savunulabilir girdilerle 'güç dengesi kurulamıyor' diye reddediliyor.

### [ ] F010 — `cycle_power_balance.py::solve_cycle (expander dalı) + ::_turbine_specific_work`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
gamma_t = cp_turb / max(cp_turb - r_sp, 1e-6);  dh = eta*cp*T*(1 - PR**(-(g-1)/g))
```

**Olması gereken:** Expander çevriminde türbin akışkanı YOĞUN süperkritik akışkandır (H2 40-130 K / 45-70 bar; CH4 277 K / 133 bar). Bu rejimde termik mükemmel gaz bağıntısı gamma = cp/(cp - R) GEÇERSİZDİR (cp - cv >> R). CoolProp zaten import edilmiş: ya gamma = CP.PropsSI('CVMASS',...) ile cp/cv alınmalı, ya da (doğrusu) izentropik entalpi düşümü doğrudan hesaplanmalı: s1=S(T,p); h2s=H(p/PR, s1); dh = eta*(h1-h2s). Yanma gazı dalları (GG/staged/FFSC) bu hatadan etkilenmez — orada CEA zaten ideal gaz varsayar ve Tr>4.5 olduğu için bağıntı geçerlidir.

**Kaynak:** Bağıntının kendisi doğru kaynaklı (Sutton & Biblarz 9. baskı Böl. 3/10, termik mükemmel gaz) ancak uygulandığı rejim kaynağın geçerlilik zarfı dışında. Karşılaştırma referansı: CoolProp 6.8.0 (NIST REFPROP tabanlı) izentropik entalpi düşümü.

**Sayısal etki:** ÖLÇÜLDÜ (kodun KENDİ yakınsadığı çözüm noktalarında, eta_t=0.78): metan expander (Pc=60 bar, mdot=50, Q=8000 kW) TIT=276.8 K, p_in=132.7 bar, PR=1.923 -> dh_kod=69.8 kJ/kg, gerçek gaz izentropik=48.8 kJ/kg => türbin işi %+42.9 FAZLA. gamma_kod=1.173, gamma_gerçek(cp/cv)=2.023. LH2 (RL10 benzeri, Pc=32.75, Q=2500 kW): TIT=84.8 K, dh_kod=155.0 vs 144.3 kJ/kg => %+7.4. Ham çalışma noktalarında (PR=1.5 sabit) hata %+13 ile %+63 arası. TIT>200 K'de hata %3'e iner. Yön: türbin gücü FAZLA hesaplanıyor -> expander güç dengesi olduğundan İYİMSER kapanıyor.

### [ ] F011 — `heat_transfer_analysis.py::_analyze_gas_side_heat_transfer`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
if T_wall > max_service:  # 'critical' yanma-delinme bayrağı
    warn('warn.thermal.wall_exceeds_service')
elif T_wall > allowable: warn(... 'warning')
```

**Olması gereken:** Kritik eşik erime noktasının ALTINDA olmalı. materials_db'de steel/steel_4130/steel_4340 için max_service_temperature = 2000 K iken melting_point = 1773/1705/1700 K; ss_304 (1723 vs 1673) ve ss_316 (1672 vs 1644) de aynı durumda. Kritik bayrak min(max_service_temperature, melting_point) ile veya ayrı bir 'T_wall > melting_point' kontrolüyle kurulmalı. Ayrıca 'warn.thermal.approaches_melting' metni cidar erimenin ÜSTÜNDEYKEN 'erimeye yaklaşıyor' diyor.

**Kaynak:** Fiziksel tutarlılık (servis sınırı < erime noktası); hrma/data/materials_db.py kayıtlarının kendi 'melting_point' alanları. Bu bir literatür formülü hatası değil, eşik/veri tutarsızlığı.

**Sayısal etki:** ÖLÇÜLDÜ. analyze_heat_transfer'i steel + regeneratif ile taradım; 1773 K < T_wall < 2000 K penceresine düşen gerçek girdi setleri var: Pc=20 bar/t=8 mm -> T_wall=1924 K; Pc=30/5 mm -> 1911 K; Pc=40/3 mm -> 1851 K; Pc=50/3 mm -> 1977 K. Dördünde de cidar çelik erime noktasının 78-204 K ÜSTÜNDE ama üretilen uyarıların hiçbiri 'critical' değil (yalnız wall_exceeds_allowable + approaches_melting, ikisi de 'warning'). Yön GÜVENSİZ: erimiş cidar 'sınır aşıldı' seviyesinde raporlanıyor. Ek olarak thermal_protection.py aynı çelik için 'max_service_temp' = 811 K kullanıyor — iki panel aynı malzeme için 2.5x farklı sınır gösteriyor.

### [ ] F012 — `hrma/engines/injector_design.py::design_injector (sigma_ox / sigma_fuel varsayılanı)`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
sigma_ox = spec.get('sigma_ox', 0.02)  → smd_elkotb / smd_lefebvre_swirl / smd_impinging
```

**Olması gereken:** N₂O için 293 K'de yüzey gerilimi σ ≈ 0.00175 N/m'dir (kritik nokta 309.5 K'ye yakın olduğu için çok düşüktür). Varsayılan 0.02 N/m yaklaşık 11.4 KAT yüksektir. Doğrusu: fluid_ox == 'n2o' ise σ tablodan/doyma sıcaklığından alınmalı. Bu değer AYNI DEPODA zaten mevcut: hrma/utils/injector_design.py::SIGMA_OX = {'n2o': 0.00175, 'lox': 0.013} (NIST WebBook atfıyla) — iki modül çelişiyor.

**Kaynak:** NIST WebBook / ESDU: N₂O σ ≈ 1.75 mN/m @ 293 K; depo içi teyit: hrma/utils/injector_design.py::SIGMA_OX

**Sayısal etki:** ÖLÇÜLDÜ (scratchpad/case.py). Elkotb SMD ∝ σ^0.737 → 56.6 µm (σ=0.02) vs 9.4 µm (σ=0.00175) = 6.02 KAT aşırı tahmin. Lefebvre swirl SMD ∝ σ^0.25 → 1.84 kat. Impinging SMD ∝ We^(−1/3) ∝ σ^(1/3) → 2.25 kat. Frontend'i taradım: injector_panel.js spec'e sigma_ox/sigma_fuel HİÇ göndermiyor (yalnız mdot_ox, mdot_fuel, Pc_bar, T_c_K, mw_gas), dolayısıyla varsayılan HER kullanıcı koşusunda devrede.

### [ ] F013 — `hrma/engines/injector_design.py::design_injector (smd_lefebvre_swirl çağrısı)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
smd_ox = smd_lefebvre_swirl(sigma_ox, mu_ox, mdot_ox, ox['delta_p_bar']*PA_PER_BAR, rho_gas)
```

**Olması gereken:** Lefebvre basınç-swirl korelasyonundaki ṁ_L TEK atomizöre ait debidir (korelasyon tek simplex memede kalibre edilmiştir). Kod TOPLAM oksitleyici debisini geçiriyor; eleman başına debi mdot_ox/n_orifices olmalı.

**Kaynak:** Lefebvre & McDonell, Atomization and Sprays 2. baskı — SMD = 2.25 σ^0.25 μ_L^0.25 ṁ_L^0.25 ΔP_L^(−0.5) ρ_A^(−0.25), ṁ_L = tek atomizör sıvı debisi

**Sayısal etki:** ÖLÇÜLDÜ. SMD ∝ ṁ^0.25 → sapma n^0.25. Gerçek tasarım koşusunda (hibrit swirl, ṁ=2 kg/s, Pc=30 bar) çözücü n=39 eleman seçiyor → 39^0.25 = 2.50 KAT aşırı tahmin. Ayrı doğrulama: ṁ=3 kg/s toplam → 114.3 µm; eleman başına (n=30) → 48.9 µm. Bulgu #3'ün σ hatasıyla birleşince swirl SMD toplam ≈ 4.6 kat şişiyor.

### [ ] F014 — `hrma/engines/injector_design.py::design_injector (swirl / coax_swirl dalı)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
a_p = K * np.pi * r_s * r_o   ;   'swirl_number': np.pi * r_o * r_s / a_p
```

**Olması gereken:** K = A_p/(D_s·d_o) = A_p/(4·r_s·r_o) tanımından A_p = 4·K·r_s·r_o olmalı; kod π·K·r_s·r_o kullanıyor (π yerine 4). Ayrıca 'swirl_number' olarak dönen büyüklük π·r_o·r_s/A_p = 1/K'dır; bu, standart girdap sayısı S (eksenel açısal momentum akısı / (R × eksenel momentum akısı)) DEĞİLDİR — ad yanıltıcı.

**Kaynak:** Lefebvre & McDonell, Atomization and Sprays 2. baskı Böl. 6 (atomizör sabiti tanımı); girdap sayısı için Gupta, Lilley & Syred, Swirl Flows (1984)

**Sayısal etki:** Ölçmedim (bulgu #1 düzeltilmeden anlamlı sayı çıkmaz). Yalnız π↔4 farkı teğet giriş alanını π/4 = 0.785 kat, giriş çapını 0.886 kat kaydırır. Bulgu #1'in K ölçek hatasıyla birleşince (kod K'sı Lefebvre K'sının 3.242 katı) toplam teğet port alanı ≈ 2.55 kat, inlet_d_mm ≈ 1.60 kat sapar. 'film_thickness_mm' ve 'X_air_core' de aynı X hatasını taşır.

### [ ] F015 — `hrma/utils/injector_design.py::__init__ (basınç düşümü seçimi)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
available_delta_P = tank_pressure - chamber_pressure ; if available_delta_P < min_delta_P: self.delta_P_inj = min_delta_P
```

**Olması gereken:** Tank besleme sisteminin sağlayabildiği ΔP yetersizse kod ΔP'yi yine 0.15·Pc'ye ZORLUYOR ve yalnız ekrana yazı basıyor. Bu, var olmayan bir basınç düşümüyle boyutlandırma yapmaktır: enjeksiyon alanı A = ṁ/(Cd√(2ρΔP)) küçük çıkar, gerçekte teslim edilen debi hedefin altında kalır. Doğrusu: ΔP = available_delta_P kullanılıp tasarımın hedef debiyi karşılayamadığı açıkça raporlanmalı (ya da hata döndürülmeli).

**Kaynak:** Süreklilik + besleme sistemi basınç dengesi (Huzel & Huang Böl. 4; NASA SP-8089 ΔP/Pc ilkesi bir HEDEFTİR, garanti değil)

**Sayısal etki:** ÖLÇÜLDÜ (scratchpad/utils_case.py, Pc=30 bar): P_tank=31 bar (mevcut ΔP = 1.0 bar) → kod ΔP=4.5 bar kullanıyor, yani MEVCUDUN 4.5 KATI. Alan √4.5 = 2.12 kat küçük boyutlanıyor → gerçek koşulda teslim debisi hedefin ~%53 altında. P_tank=34 (mevcut 4.0) → yine 4.5 kullanılıyor (%12 fazla). Kaynak etiketi 'saturation-driven' olarak raporlandığı için kullanıcıya bu bir modelleme kararı gibi görünüyor.

### [ ] F016 — `hrma/utils/injector_design.py::_calculate_pintle`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
gap = A_ann_required/(pi*D_avg) ; gap = max(0.0003, min(gap, 0.003)) ; A_ann = pi*D_avg*gap
```

**Olması gereken:** Boşluk imalat bandına kırpıldıktan SONRA alan yeniden hesaplanıyor ama D_outer/D_pintle sabit bırakılıyor → süreklilik (ṁ = Cd·A·√(2ρΔP)) bozuluyor ve teslim debisi sessizce hedeften sapıyor. Aynı modülün _calculate_showerhead ve _calculate_impingement fonksiyonları bu sorunu (denetim bulgusu #118) delik SAYISINI yeniden çözerek düzeltmiş; pintle dalı düzeltilmemiş. Doğrusu: kırpma olduğunda D_outer (veya D_pintle) yeniden çözülmeli ya da en azından uyarı üretilmeli. Not: A = π·D_avg·gap bağıntısının kendisi TAM doğrudur (π(D_o²−D_i²)/4 ile özdeş).

**Kaynak:** Süreklilik/orifis denklemi (Sutton & Biblarz Böl. 8); modül içi tutarlılık (aynı dosyadaki showerhead/impingement düzeltmesi)

**Sayısal etki:** ÖLÇÜLDÜ (scratchpad/utils_case.py; ρ=750, Pc=30 bar, P_tank=50, Cd=0.7, D_outer=50 mm, D_pintle=25 mm): ṁ_hedef=1 → sapma yok; ṁ=6 → sapma yok; ṁ=12 kg/s → gap 4.85 mm iken 3.00 mm'ye kırpılıyor, alan 571.4 → 353.4 mm², teslim debisi 7.42 kg/s = HEDEFİN %38 ALTINDA, hiçbir uyarı yok. Ters yönde (gap < 0.3 mm) debi hedefin üstüne çıkar.

### [ ] F017 — `hrma/utils/injector_design.py::_calculate_swirl`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
spray_angle = 90  # degrees
```

**Olması gereken:** Sprey açısı SABİT olarak 90 yazılmış — hiçbir geometri/akış girdisine bağlı değil, bir denklem yok. Basınç-swirl atomizörde sprey açısı hava çekirdeği oranı X ve atomizör sabiti K'nın fonksiyonudur: sinθ = (π/2)Cd/(K(1+√X)). Ayrıca birim belirsiz (yarı açı mı tam koni mi belirtilmemiş). Uydurma sayı olduğu için ya gerçek bağıntı bağlanmalı ya da None döndürülüp 'modellenmedi' denmelidir.

**Kaynak:** Giffen & Muraszew (1953) / Lefebvre Böl. 6 — sprey açısı geometriye bağlıdır; sabit değildir

**Sayısal etki:** ÖLÇÜLDÜ: her girdi kombinasyonunda çıktı 90. Gerçek simplex atomizörlerde yarı açı 30-60° (tam koni 60-120°) bandında geometriyle değişir; 90 tam koni olarak okunursa tipik, yarı açı olarak okunursa fiziksel üst sınırdır. Kullanıcıya 'hesaplanmış' bir alan gibi sunuluyor.

### [ ] F018 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
self.flux_mode = flux_mode if flux_mode in ('total','ox') else 'total'  ->  RegressionAnalyzer.regression_rate(..., flux_mode='total') ile r = a*(G_ox+G_fuel)^n
```

**Olması gereken:** Katsayı tabanı ile akı tabanı EŞLEŞMELİ. HYBRID_REGRESSION_COEFFICIENTS'taki (a,n) çiftlerinin tamamı G_ox tabanlı deneysel fitlerdir (Doran 2007; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2 — o tablolarda korelasyon değişkeni oksitleyici akısıdır). Marxman'ın teorik r = a*G_total^0.8*x^-0.2 formu, KENDİ teorik katsayısıyla kullanılmalıdır. G_ox-fitli a/n'yi G_total ile beslemek çift sayımdır. Varsayılan tasarım yolunda flux_mode='ox' olmalı ya da 'total' seçildiğinde a, (1+1/OF)^n ile geri ölçeklenmelidir.

**Kaynak:** Marxman & Gilbert, 9th Symp. (Int.) on Combustion, 1963; Sutton & Biblarz, Rocket Propulsion Elements 9. baskı Böl. 16; katsayı tabanı: Doran et al. AIAA 2007-5352 ve Zilliac & Karabeyoglu AIAA 2006-4504 (her ikisi de G_ox tabanlı fit)

**Sayısal etki:** ÖLÇÜLDÜ. HTPB a=3.68e-5, n=0.555, G_ox=350 kg/m²s sabit tutularak 'ox'→'total' geçişinde r_dot artışı: O/F=12 →+4.8%, O/F=8 →+7.2%, O/F=6 →+9.8%, O/F=4 →+15.1%, O/F=3 →+20.6%, O/F=2 →+32.6%, O/F=1.5 →+45.8%. Tam motor koşusu (F=2 kN, t_b=10 s, O/F=6, Pc=25 bar, HTPB/N2O): r_dot_initial 0.9502→1.0430 mm/s (+9.8%), r_dot_avg 0.8338→0.8978 mm/s (+7.7%), L_grain 863.6→786.7 mm (−8.9%). Projenin KENDİ doğrulama katmanı (record_adapters.py::_run_hybrid) bu yüzden flux_mode='ox' zorluyor ve yorumunda '(1+1/OF)^n = 1.15-1.36 sistematik çarpanı bindirir' diyor — ama kullanıcıya giden varsayılan hâlâ 'total'. Doğrulama katmanının reddettiği taban, ürün varsayılanı olarak kalmış.

### [ ] F019 — `hybrid_rocket_engine.py::_set_fuel_properties`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
regression = HYBRID_REGRESSION_COEFFICIENTS.get(fuel_key, ...['htpb'])  # htpb: a=3.68e-5, n=0.555
```

**Olması gereken:** İstenen medAPE %35.1 / bias −%20.2'nin TEŞHİSİ: sapma FORMÜLDEN değil KATSAYIDAN geliyor, ve tek bir yakıtta toplanıyor. Doğrulama DB'sindeki hibrit kayıtları (anomali dışı, high+medium güven) yakıta göre ayırdığımda: parafin n=17, bias +%9.4, medAPE %6.9 (mükemmel — katsayılar zaten o kampanyadan geliyor); HTPB n=43, bias −%39.5, medAPE %46.6. İki bağımsız HTPB kampanyası da aynı yönde: carmicino2013 n=25 bias −%33.3, rezaei2018 n=18 bias −%48.0. n=0.555 sabit tutulup DB'nin HTPB kayıtlarına en iyi a aranırsa a=6.24e-5 çıkıyor — koddaki değerin 1.70 KATI.

**Kaynak:** Doran, Dyer, Lohner, Dunn, Cantwell, 'Nitrous Oxide Hybrid Rocket Motor Fuel Regression Rate Characterization', AIAA 2007-5352 (makale gerçek ve doğru atıflanmış; tam metin ücretli olduğu için 0.132/0.555 tablo satırını BİREBİR DOĞRULAYAMADIM). Dikkat: 'pe' girdisi de Zilliac & Karabeyoglu Tablo 2'den a=0.132 diye alınmış — iki farklı yakıt/oksitleyici çifti için aynı a değeri şüphelidir, PDF'ten yeniden okunmalı.

**Sayısal etki:** ÖLÇÜLDÜ. Kendi bağımsız hesabım rapordaki test-başına hataları BİREBİR üretti (t4l-04 +25.7%, t4l-12 +53.5%, t4l-11 −15.0%, tst −14.3%), yani teşhis modeli doğru. Negatif bias'ın ANLAMI: model regresyonu düşük tahmin ediyor → yakıt debisini düşük, O/F'yi yüksek tahmin ediyor → grain'i ~%25 fazla uzun boyutlandırıyor → gerçekte O/F tasarımın altına düşüyor VE web gerçekte tahminden ~%25 ERKEN tükeniyor. Bu GÜVENLİ OLMAYAN yön: model 'web dayanır' derken kovan yanma sonuna kadar dayanmayabilir. Not: proje bunu docs/correlation_report/COMMENTARY.md'de dürüstçe belgelemiş; asıl eksik kodda uyarı olmaması.

### [ ] F020 — `hybrid_rocket_engine.py::_set_fuel_properties`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
fuel_key = self.fuel_type.lower(); regression = HYBRID_REGRESSION_COEFFICIENTS.get(fuel_key, ...)  # oxidizer_type HİÇ kullanılmıyor
```

**Olması gereken:** Hibrit regresyon katsayıları OKSİTLEYİCİYE kuvvetle bağlıdır (HTPB/GOX ile HTPB/N2O arasında a tipik olarak 2 kat fark eder; alev sıcaklığı, blowing parametresi ve radyasyon payı farklıdır). Katsayı anahtarı (yakıt, oksitleyici) çifti olmalı; eşleşme yoksa açık uyarı verilmeli. Ayrıca her katsayı çiftine geçerli G aralığı alanı eklenip regression_rate() o aralık dışında uyarmalı.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 16 (regresyon korelasyonlarının oksitleyici-özgüllüğü); Chiaverini & Kuo, Fundamentals of Hybrid Rocket Combustion and Propulsion, AIAA Progress Vol. 218, 2007

**Sayısal etki:** ÖLÇÜLDÜ (kısmen). Kod, N2O tabanlı HTPB katsayılarını HTPB/LOX ve HTPB/GOX motorlarına, O2 tabanlı HDPE katsayılarını PE/N2O motorlarına hiçbir uyarı vermeden uyguluyor; DB'de her iki durum da var (htpb/lox n=1, pe/n2o n=11). Geçerlilik aralığı denetimi: HTPB alt kümesini G_avg bantlarına ayırdığımda bias G<100 kg/m²s'te −%48.9 (n=16), 100-300'de −%35.6 (n=24), >300'de −%19.7 (n=3) — hata düşük akıda sistematik olarak büyüyor, yani fit aralığı dışına çıkış ölçülebilir bir etken. Kod ne alt ne üst sınırda uyarı üretiyor (tek uyarı G_ox>600 flooding kontrolü).

### [ ] F021 — `pressure_vessel.py::analyze`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
t_burst_req = 2R*p_burst_req/(2*su - p_burst_req) ; actual_burst = min(burst_faupel, burst_thin) ; burst_margin = actual_burst/required_burst ; status FAIL if margin<1.0, MARGINAL if <1.2
```

**Olması gereken:** Otomatik boyutlandirma ile kabul kriteri BIRBIRIYLE TUTARSIZ: t_burst_req yalnizca ince-cidar ortalama-cap formunu (2*su*t/(D+t)) TAM ESITLIKLE cozuyor, yani hedef marj 1.000; ama kabul kriteri hem min(Faupel, ince) kullaniyor (Faupel ince-cidar rejiminde ~%0.3 DAHA DUSUK) hem de >= 1.2 istiyor. Sonuc: modul kendi hesapladigi minimum kalinligi kendi kriterinde birakiyor. Dogrusu: t_burst_req, kabul kriterinde kullanilan AYNI fonksiyondan (min(Faupel, ince) >= MARGINAL_BURST_MARGIN * required_burst) sayisal koke gitmeli (brentq/bisection) veya boyutlandirma hedefi acikca 1.2*required_burst alinmali.

**Kaynak:** Yontem/tutarlilik hatasi. Faupel (Trans. ASME Vol.78, 1956) ve ince-cidar membran limit formullerinin kendileri dogru ve dogru alintilanmis.

**Sayısal etki:** OLCULDU. D_ic=150 mm, steel_4130, wall_thickness_mm=None (oto-boyut): code_mode='asme_viii' -> MEOP=20 bar margin=0.9977 status=FAIL; 60 bar margin=0.9997 FAIL; 120/200/400 bar margin=1.003/1.007/1.019 MARGINAL. code_mode='aiaa_s080' -> MEOP=20..400 bar margin=1.182..1.115, HEPSI MARGINAL. aluminum_6061 ve titanium_6al4v oto-boyut -> margin=1.0000 MARGINAL. Yani otomatik boyutlandirma HICBIR ZAMAN 'PASS' uretemiyor (tek istisna ss_304, cunku akma-yonetimli sizing burst'u fazlaca asiyor: 1.336 PASS) ve dusuk basincta ASME modunda kendi min kalinligini 'FAIL' diye rapor ediyor.

### [ ] F022 — `record_adapters.py::_run_hybrid (+ correlation_runner.py::_aggregate)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
f_new = mdot_total * G_0 * res["isp"]  ...  predictions = {"thrust": f_n, "thrust_mean": f_n, "total_impulse": f_n * burn_time}   (mdot_total = mdot_ox*(1+of)/of, mdot_ox ve of TÜKETİLEN ÖLÇÜMLER)
```

**Olması gereken:** thrust bağımsız bir tahmin değildir: ölçülen kütle debisi x model Isp'sidir. Deney kaynakları Isp'yi zaten Isp_ölçüm = F_ölçüm/(mdot_ölçüm*g0) diye tanımladığı için thrust hatası ile isp hatası CEBİRSEL OLARAK AYNI büyüklüktür. total_impulse = thrust x (tüketilen burn_time) üçüncü kopyadır. _run_liquid'de thrust_vac için yazılan 'ZAYIF KANIT' notunun aynısı hibritte de olmalı; ayrıca bu üç hücre ayrı ayrı n=18 diye raporlanmamalı (tek karşılaştırma, tek n).

**Kaynak:** Kod içi kendi ilkesi: record_adapters.py modül docstring'i 'tüketilen girdilerin aritmetik türevi olan büyüklükleri derived_bases listesinde açıkça bildirir — koşucu bunları skorlamaz'. Aynı ilke _run_liquid::thrust_vac için uygulanmış (ZAYIF KANIT notu), _run_hybrid::thrust için uygulanmamış. Standart doğrulama pratiği: Oberkampf & Roy, 'Verification and Validation in Scientific Computing', CUP 2010, Böl. 12 (bağımlı çıktıların ayrı doğrulama metriği sayılmaması).

**Sayısal etki:** ÖLÇÜLDÜ (tam DB, 209 kayıt koşuldu): hybrid isp hücresi ile hybrid thrust hücresi AYNI 18 testi içeriyor; test başına |isp_err - thrust_err| maksimum 0.055 yüzde puanı (ör. t26: isp +9.6488%, thrust +9.6412%). İki hücre de bias +9.6%, medAPE 9.1%, RMS 10.5%, aynı iki aykırı. Etki: yayımlanan tabloda 18+18=36 bağımsız doğrulama noktası gibi görünen şey tek bir 18 noktalı karşılaştırmadır — hibrit doğrulama kapsamı %100 abartılmış görünüyor. docs/correlation_report/report.md'de ayrı parity_hybrid_isp.png ve parity_hybrid_thrust.png olarak iki grafik basılıyor.

### [ ] F023 — `six_dof_trajectory.py::SixDOFTrajectory.__init__`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
y0 = [0,0,0, ...] ; _derivatives: h = max(r[2], 0.0) ; rho, a = _atmosphere(h)
```

**Olması gereken:** h_atm = launch_altitude + r[2]. Modülde launch_altitude parametresi HİÇ YOK; atmosfer daima deniz seviyesinden ölçülüyor. Kardeş trajectory_analysis bunu destekliyor (launch_altitude / site.elevation_m), 6-DOF desteklemiyor — v2.6.2'nin fırlatma sahası entegrasyonuyla doğrudan çelişiyor.

**Kaynak:** USSA 1976 profil tanımı: yoğunluk mutlak irtifanın fonksiyonudur, AGL'nin değil.

**Sayısal etki:** ÖLÇÜLDÜ (_atmosphere'a 1500 m ofset enjekte ederek): apoje 4016.8 m → 4324.1 m, %7.65 fark. 1000-1500 m rakımlı sahalar (Türkiye dahil) için tipik. Yön: kod apojeyi EKSİK tahmin ediyor (fazla sürükleme).

### [ ] F024 — `solid_rocket_engine.py::SolidRocketEngine.__init__ (burn_rate_a varsayılanı)`

**Hüküm:** YANLIS_BIRIM · **Görünür:** evet

**Koddaki denklem:**
```
burn_rate_a=0.005, burn_rate_n=0.35  →  burn_rate(): base_rate = self.a * (pressure ** self.n)   # pressure [bar], sonuç [m/s]
```

**Olması gereken:** a = 0.0022334 (m/s / bar^0.35). Projenin KENDİ tek-kaynak kataloğu bunu zaten doğru veriyor: propellants_db._APCP_REFERENCE = mm_mpa_to_m_bar(5.0, 0.35) = a'/(1000·10^n). 0.005 değeri 'r[mm/s] = 5.0·P[MPa]^0.35' fitinin MPa tabanlı katsayısıdır; bar ile değerlendirilince tam 10^0.35 = 2.2387 kat şişer. UI ipucundaki 'APCP: 0.003-0.008' bandı da aynı hatayı kodluyor; bar konvansiyonunda doğru bant ~0.0013-0.0036'dır.

**Kaynak:** Projenin kendi belgesi: hrma/data/burn_rate_db.py modül docstring'i bu hatayı birebir tarif ediyor ('katsayının kökeni MPa tabanlı iken bar ile değerlendirilmesi tek yönlü x2.24 şişme veriyordu'). Katsayı bandı: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Böl. 12 (AP/HTPB/Al için r ≈ 5-13 mm/s @ 1000 psi ≈ 69 bar).

**Sayısal etki:** ÖLÇÜLDÜ (BATES, D_oda=100 mm, L=500 mm, D_çekirdek=30 mm, Pc=40 bar, APCP): a=0.005 → t_b=2.186 s, F_ort=6797 N, F_maks=10812 N, boğaz 47.9 mm. a=0.002233 (katalog) → t_b=4.849 s, F_ort=3097 N, F_maks=4523 N, boğaz 30.9 mm. Yanma süresi 2.22 kat kısa, ortalama itki 2.19 kat yüksek, boğaz alanı 2.41 kat büyük. Toplam impuls doğru kalıyor (14884 vs 15026 N·s, kütle korunumu sağlam) — yani hata itki/süre/boğaz üçlüsünde, impulsta değil. r(70 bar): 22.1 mm/s (uydurulmuş hızlı yakıt) yerine 9.88 mm/s (gerçek AP/HTPB/Al).

### [ ] F025 — `solid_rocket_engine.py::burn_rate (parçalı KNDX/KNSB yasasının tek üslü yasaya donması)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
base_rate = self.a * (pressure ** self.n)   # (a, n) TASARIM basıncında bir kez çözülür, tüm yanma boyunca sabit tutulur
```

**Olması gereken:** Yanma hızı her adımda ANLIK basınçtan, parçalı yasadan okunmalı: burn_rate_db.burn_rate_mmps(prop, Pc/10). burn_rate_db'nin kendi docstring'i bunu şart koşuyor ('KN-şeker yakıtların yayımlanmış davranışı PARÇALIDIR; tek a-n tüm basınç aralığını temsil etmez') ama motor tam da bunu yapıyor: /api/burn-rate/resolve tek bir rejimin (a, n) ikilisini forma yazıyor, motor onu Pc 5 kat değişse bile kullanıyor.

**Kaynak:** R. Nakka, 'Solid Propellant Burn Rate' (Experimental Rocketry, 1999/2001) — KNDX/KNSB rejim tabloları; ayrıca hrma/data/burn_rate_db.py'nin kendi uyarısı.

**Sayısal etki:** ÖLÇÜLDÜ (BATES 100/500/30 mm, KNDX termokimyası): tasarım 70 bar → rejim 4 (5.93-8.50 MPa, a=0.024184, n=-0.148) donuyor; koşu sırasında Pc 31.5-72.1 bar geziyor; anlık r sapması ortalama +8.9%, TEPE +71.6%. Tasarım 30 bar → rejim 3 (2.57-5.93 MPa, n=0.688) donuyor; Pc 1.6-33.5 bar; sapma ortalama -36.1%, dip -62.0%. Yani KNDX/KNSB preset yolunda yanma hızı, yanmanın ikinci yarısında 1.7 kata kadar yanlış.

### [ ] F026 — `structural_analysis.py::_analyze_chamber_wall`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
hoop_stress = pressure_hoop_stress + thermal_hoop_stress ; hoop_safety_factor = yield_for_design / hoop_stress
```

**Olması gereken:** Basinc hoop'u BIRINCIL (P, yuk kontrollu) gerilmedir; termal gradyan gerilmesi IKINCIL (Q, deplasman kontrollu) gerilmedir. Bu ikisi toplanip AKMA dayanimiyla oranlanamaz — ikincil gerilme akma ustunde plastik uyum (shakedown) ile kendini sinirlar, kirilma yaratmaz. ASME VIII-2 Part 5 / Section III NB-3222.2: P+Q icin limit 3*Sm (shakedown), P icin limit Sm. Kod dogru olani zaten hesapliyor (safety_factor_pressure) ama tepe/ozet alan olarak safety_factor = safety_factor_total (P+Q vs yield) yayiliyor. Yapilmasi gereken: P/Sm ve (P+Q)/3Sm ayri kriterler olarak raporlansin; tek 'safety_factor' alani birincil yuke bagli olsun, shakedown ayri bayrak olsun. Ek olarak termal tepe cekme DIS yuzeyde, Lame basinc tepesi IC yuzeydedir — toplama konservatif ama es-konumlu degil, bu da beyan edilmeli.

**Kaynak:** ASME BPVC VIII-2 (2021) Part 5.2.2 gerilme siniflandirmasi ve 5.5.6 shakedown; ASME III NB-3222.2 (3Sm kurali). Timoshenko & Goodier termal gerilme formulunun kendisi dogru.

**Sayısal etki:** OLCULDU. Tipik rejeneratif cidar (wall_temperature_hot=800 K, cold=500 K, Pc=50 bar, steel_4130, D=150 mm): P_hoop = 70.7 MPa, Q_termal = 505.5 MPa, P+Q = 576.2 MPa. Kod: safety_factor_total = 0.556, minimum_safety_factor = 0.556, status = 'UNSAFE'. ASME kriteri: Sm = min(Su/3, Sy/1.5) = 243.3 MPa; P/Sm = 0.291 (KABUL), (P+Q)/3Sm = 576.2/730.0 = 0.789 (KABUL, shakedown saglaniyor). Yani tamamen normal bir rejeneratif hazne yanlis sekilde 'UNSAFE' ilan ediliyor; SF 1/0.556 = 1.80 kat fazla karamsar ve kriter tipi yanlis.

### [ ] F027 — `structural_analysis.py::_analyze_nozzle_structure`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
min_t = P*r_t/allowable ; req_t = min_t*SCF ; effective_stress = SCF*P*r_t/req_t ; safety_factor = yield_strength/effective_stress
```

**Olması gereken:** Iki ayri kusur: (1) TAUTOLOJI — effective_stress = SCF*P*r_t/(min_t*SCF) = allowable, dolayisiyla safety_factor = yield/allowable = safety_factor(malzeme) her zaman. Koddaki 2026-07-16 yorumu bunu zaten itiraf ediyor ('SF = SF_mat olarak dogru raporlanir') ama bu bir DOGRULAMA degil, girdinin geri okunmasidir; _analyze_chamber_wall ile ayni boyutlandir/dogrula ayrimi gerekir. (2) DERATING YOK — bogaz motorun EN SICAK istasyonu (Bartz tepe isi akisi orada) oldugu halde mat_props['yield_strength'] ODA SICAKLIGI degeriyle kullaniliyor; hazne cidari ise ayni cagride derate ediliyor. Ayni analizde iki farkli dayanim tabani kullanmak tutarsiz ve bogaz yonunde tehlikeli. Bogaz da _derate_strength'ten gecmeli, ayrica bogaz termal gradyan gerilmesi (rejeneratif bogazda baskin yuk) hic hesaba katilmiyor.

**Kaynak:** Ince-cidar hoop: Sutton & Biblarz 'Rocket Propulsion Elements' Ch.8 / Roark Ch.13. Derating: MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 (modulun kendi kullandigi kaynak). Tautolojinin kaynagi yok.

**Sayısal etki:** OLCULDU. chamber_temperature=3200 K verilen motorda hazne dayanimi retention=0.537 ile derate ediliyor (yield 460 -> 247 MPa) ama nozzle_analysis['safety_factor'] = 4.0000 (= safety_factor) sabit kaliyor; Pc 5..500 bar ve steel/alum/ss304/titanyum icin hep 4.0000. Bogaz izin verilen gerilmesi hazneninkine gore 1/0.537 = 1.86 kat FAZLA gosteriliyor.

### [ ] F028 — `trajectory_analysis.py::_calculate_performance_metrics`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
burnout_altitude = phases['powered']['max_altitude_powered']  (= np.max(sol.y[1]) over t∈[0, burn_time+2]) ; burnout_velocity = sqrt(vx[-1]²+vz[-1]²)
```

**Olması gereken:** Güçlü faz t_span=(0, burn_time+2) ile 2 s FAZLA entegre ediliyor; yanma-sonu büyüklükleri t=burn_time'da örneklenmeli (np.interp(burn_time, t, z) ve aynı anda hız). 'max_altitude_powered' ise yanma-sonu irtifası DEĞİL, 2 s serbest tırmanış dahil tepe değeri.

**Kaynak:** Tanım gereği (yanma-sonu = motor kesme anı). Kaynak sorunu değil, örnekleme anı hatası — Sutton & Biblarz Böl.4 burnout tanımı.

**Sayısal etki:** ÖLÇÜLDÜ (F=3000 N, t_b=4 s, m_kuru=20 kg, m_yakıt=8 kg, 85°): gerçek yanma-sonu irtifa 806.7 m / hız 399.7 m/s. Raporlanan: 1487.0 m (+%84.3) ve 300.8 m/s (−%24.7). phase_breakdown.apogee_time 24.47 s raporluyor, gerçek apoje 26.47 s (2 s erken). altitude_efficiency de aynı oranda şişiyor (%37.8).

### [ ] F029 — `uq_adapters.py::make_hybrid_factory / make_liquid_factory (uncertainty.py::run_uncertainty nominal kontrolü ile birlikte)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
hibrit: eta = sample.get('eta_c_star') -> HybridRocketEngine(eta_c_star=0.93 nominal)  |  sıvı: isp*eta, c_star*eta, mdot/eta (eta nominal 0.96). Buna karşılık app.py /calculate rotası eta_c_star HİÇ geçmiyor (grep: app.py'de eta_c_star yok).
```

**Olması gereken:** uq_adapters modül docstring'i madde 1: 'Kurucu blokları app.py'deki ilgili /calculate* rotasını BİREBİR izler ... UQ nominal koşusu ile deterministik hesap arasında girdi-yorumu farkı olamaz.' Bu iddia eta_c_star için YANLIŞ: dağılım 'absolute' modda olduğu için nominal_value() = mean = 0.93 (hibrit) / 0.96 (sıvı) döner ve UQ nominali teorik c*'a bu verimi uygular, ana sayfa uygulamaz. uncertainty.py'nin 1e-9'luk 'deterministik tutarlılık garantisi' ise engine_factory'yi KENDİSİYLE karşılaştırır (nominal_result = engine_factory(nominal_sample) vs örnek #0), dolayısıyla bu sapmayı yapısal olarak GÖREMEZ — garanti sanılan koruma bu hatanın zarfının dışındadır. Ya /calculate aynı eta'yı uygulamalı, ya UQ nominali eta=1.0'a sabitlenip eta yalnız dağılımda örneklenmeli, ya da fark UI'da açıkça yazılmalı.

**Kaynak:** Kodun kendi sözleşmesi (uq_adapters.py docstring madde 1; uncertainty.py docstring 'deterministik tutarlilik garantisi — spec 7.3'). eta_c* tanımı doğru kaynaklı: Sutton & Biblarz, 'Rocket Propulsion Elements', 9. baskı, Denk. 3-31 (c*_teslim = eta_c* · c*_teorik) — formülün kendisi doğru, sorun iki yol arasındaki asimetrik uygulama.

**Sayısal etki:** ÖLÇÜLDÜ (aynı girdilerle iki yol koşuldu). HİBRİT (F=1000 N, t=10 s, O/F=6, Pc=20 bar, HTPB): UQ nominal isp=214.222 s vs /calculate 230.347 s -> TAM -%7.00; c_star 1506.2 vs 1619.6 m/s -> -%7.00 (thrust ve total_impulse F-sabit sözleşmesi gereği %0 fark). SIVI (F=100 kN, Pc=100 bar, MR=2.5, RP1/LOX): isp 287.099 vs 299.061 s -> -%4.00; c_star 1736.5 vs 1808.9 m/s -> -%4.00; mdot_total 35.518 vs 34.097 kg/s -> +%4.17. Yani kullanıcı ana sayfada Isp=230 s görüp UQ panelinde nominal 214 s görüyor ve hiçbir açıklama yok. Sıvı tarafında ÇİFT SAYIM riskini ayrıca kontrol ettim: liquid_rocket_engine.py DELIVERED_ETA_CSTAR_DEFAULT = 1.0 olduğu için motor içinde ikinci bir eta uygulanmıyor — yani sapmanın tamamı bu asimetriden geliyor, çift sayım YOK.

### [ ] F030 — `water_hammer.py::WaterHammerAnalyzer.analyze`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
peak_pressure = p_work + dp_applied  (ve status = SAFE/MARGINAL/UNSAFE bu tepe degerden)
```

**Olması gereken:** Joukowsky darbesi vanada +dP kadar YUKARI, yansima sonrasi -dP kadar ASAGI salinim uretir. Asagi salinim sivinin buhar basincinin altina inerse sivi sutunu kopar (kolon ayrilmasi/kavitasyon) ve sutun yeniden birlestiginde tepe basinc Joukowsky degerini ~2 kata kadar asabilir. Kod ne asagi salinimi (p_work - dP) hesapliyor ne de p_buhar ile kiyasliyor; hicbir uyari uretmiyor. En az bir kontrol gerekli: p_work - dP_instant < p_vapor(T) ise 'kolon ayrilmasi riski, Joukowsky ust sinir DEGIL' uyarisi.

**Kaynak:** Wylie, E.B. & Streeter, V.L., 'Fluid Transients', McGraw-Hill (1978), Bolum 9 (column separation / kavitasyonlu gecici akis); ayrica Bergant, Simpson & Tijsseling, 'Water hammer with column separation: A historical review', J. Fluids and Structures 22 (2006) — birlesme darbesinin Joukowsky'yi asmasi belgelenmis.

**Sayısal etki:** OLCULDU (modulun kendi FLUID_PROPERTIES tablosundaki iki sivi ile). N2O, 1 inc hat (25.4x1.65 mm), 50 bar calisma, 10 m/s: kod a=488.3 m/s, dP=38.33 bar, tepe=88.33 bar, status='SAFE'. Asagi salinim = 50-38.33 = 11.67 bar; N2O buhar basinci 293 K'de ~50.8 bar => hat KESINLIKLE flash yapar, hicbir uyari yok. LOX, 50 mm hat, 30 bar, 8 m/s: dP=76.72 bar => asagi salinim = -46.7 bar (NEGATIF MUTLAK BASINC), warnings listesi TAMAMEN BOS. Kolon birlesme darbesi ~2x Joukowsky alinirsa N2O ornegindeki gercek tepe ~127 bar olur; kod 88 bar diyip 'SAFE' verir. Not: modul 'no cavitation' varsayimini assumptions listesinde belirtiyor, ama sayisal bir kontrol/uyari yok ve SAFE/UNSAFE hukmu bu yuzden konservatif degil.


## ORTA

### [ ] F031 — `bolted_joint.py::analyze`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
F_i = 0.75*A_t*S_p ; n_proof = S_p*A_t/(F_i + C*P) ; n_0 = F_i/(P*(1-C)) ; ayrica torque() 'preload_scatter_band_N' = [0.75*F_i, 1.25*F_i]
```

**Olması gereken:** Tork-kontrollu sikmada +/-%25 on-yuk sacilimi HESAPLANIP RAPORLANIYOR ama emniyet faktorlerine HIC UYGULANMIYOR — tum SF'ler nominal F_i ile hesaplaniyor. Standart uygulama (NASA-STD-5020 Sec. 6.2, Shigley Sec. 8-8): akma/proof kontrolu MAKSIMUM on-yukle (F_i_max = 1.25*F_i), ayrilma (separation) kontrolu MINIMUM on-yukle (F_i_min = 0.75*F_i) yapilir. Iki ayri SF (n_proof_min ve n_separation_min) raporlanmali; tek nominal deger yaniltici.

**Kaynak:** NASA-STD-5020A 'Requirements for Threaded Fastening Systems in Spaceflight Hardware' Sec. 6.2 (max/min preload); Shigley's Mechanical Engineering Design 10th ed. Sec. 8-8. Koddaki Eq. 8-24...8-30 formullerinin kendileri DOGRU ve dogru alintilanmis.

**Sayısal etki:** OLCULDU. M10 8.8, l=30 mm, celik uye, 8 civata, 60 bar x 160 mm sizdirmazlik capi: A_t=58 mm^2, S_p*A_t=33.64 kN, F_i=25.23 kN, C=0.1661, P_civata=15.08 kN. Kod raporu: n_proof=1.213, n_0=2.006, UYARI YOK. +%25 sacilimla F_i=31.54 kN -> F_b=34.04 kN > S_p*A_t=33.64 kN, n_proof=0.988 -> CIVATA PROOF DAYANIMINI ASIYOR (kod bunu gormuyor; %23 fazla marj gosteriyor). -%25 sacilimla n_0 = 2.006 -> 1.505 (%25 dusus, 1.5 uyari esiginin tam sinirinda).

### [ ] F032 — `combustion_analysis.py::_calculate_isentropic_efficiency`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
h_actual = h_oda − h_çıkış (Cantera denge entalpileri); h_isentropic = cp_oda·(T_c − T_e_izentropik); eta = min(1.0, max(0.8, h_actual/h_isentropic))
```

**Olması gereken:** Pay ve payda AYNI tabanda olmalı. h_actual kayan-denge (shifting) entalpi düşüşüdür ve rekombinasyon ısısını içerir; payda ise donmuş (frozen) cp ile hesaplanmış izentropik düşüştür. Oran bu yüzden yapısal olarak >1 çıkar ve kırpma bunu maskeler — fonksiyon fiilen HER ZAMAN 1.0 döndürür. Doğrusu: payda da aynı izentropik denge çözümünden (gas.SP + equilibrate) alınmalı, ya da alan tamamen kaldırılmalı.

**Kaynak:** Kaynak bulunamadı — kodda atıf yok. İzentropik verim tanımı standarttır ama buradaki uygulaması tanımla uyuşmuyor.

**Sayısal etki:** ÖLÇÜLDÜ: htpb/n2o O/F=6 Pc=20 bar → h_actual = 2423.9 kJ/kg, h_isentropic = 1.610·(3307.1−2178.9) = 1816.4 kJ/kg, ham oran = 1.334; kırpma sonrası raporlanan değer 1.0. Yani çıktıda 'nozul izentropik verimi %100' yazıyor — bilgi taşımayan, sabit bir sayı.

### [ ] F033 — `combustion_analysis.py::_empirical_flame_temperature`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
T = base_temp · f(φ) · (1 + 0.05·ln(P));  f(φ) = 1/(1 + 0.25·ln²φ), [0.35, 1] kırpması; base_temp = 3200 K (+500 Al, +200 H)
```

**Olması gereken:** Basınç katsayısı ~0.05 yerine ~0.03 olmalı. Ölçüm: kod 1→200 bar arasında Tc'yi %26.5 artırıyor; CEA aynı aralıkta (N2O/HTPB O/F=6) %17.0 artırıyor. Katsayı ln-tabanlı fitle 0.05·(17.0/26.5) ≈ 0.032 olmalı. φ zarfı ayrıca yakıt-fakir uçta fazla sıcak (bkz. sayısal etki).

**Kaynak:** Kaynak bulunamadı — kod 'kaba zarf' olduğunu dürüstçe söylüyor, hiçbir literatüre atıf yapmıyor. Kalibrasyon için CEA taraması yeterli olurdu.

**Sayısal etki:** ÖLÇÜLDÜ (RocketCEA N2O/HTPB referansı): Pc=1 bar kod 3076 K / CEA 3013 K (+2.1%); Pc=20 bar 3536/3322 (+6.4%); Pc=100 bar 3784/3469 (+9.1%); Pc=200 bar 3891/3525 (+10.4%). O/F taraması: O/F=2 kod 2354 K / CEA 1986 K (+18.5%), O/F=6 +6.4%, O/F=8 +10.1%. Tepe konumu (O/F≈8) doğru. c* ∝ √Tc olduğundan c* etkisi +1…+5%. Yalnızca Cantera'sız yolda etkin — ama yukarıdaki bulgu nedeniyle bu yol muhtemelen varsayılan.

### [ ] F034 — `combustion_analysis.py::analyze_combustion`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
exit_pressure = 1.0  # Sea level  →  exit_temperature, exit_composition, performance['isp'], performance['cf'] hep bu p_e'de
```

**Olması gereken:** Çıkış istasyonu motorun GERÇEK genişleme oranından türeyen p_e'de çözülmeli (ya da fonksiyon p_e/ε'yi parametre almalı). Şu an raporlanan isp/cf her zaman 'deniz seviyesine eşlenik lüle' değeridir; kullanıcının girdiği ε ne olursa olsun değişmez. Ayrıca 'deniz seviyesi' 1.0 bar yazılmış, ISA değeri 1.01325 bar (hrma.constants içinde zaten var).

**Kaynak:** İzentropik bağıntıların kendisi doğru (Sutton & Biblarz 9. baskı Eq. 3-7/3-15). Sabit 1.0 bar seçimi kaynaksız.

**Sayısal etki:** ÖLÇÜLDÜ: htpb/n2o O/F=6 Pc=20 bar → p_e=1.0 bar sabitinden türeyen efektif ε=3.74; A_e=0.00606 m². Motor ε=8 veya 16 ile tasarlandıysa raporlanan isp (232.1 s) ve calculate_altitude_performance tablosunun tamamı BAŞKA bir lülenin sayılarıdır. 1.0 vs 1.01325 bar farkının kendisi ihmal edilebilir (~8 N / 4544 N = %0.2). Hibrit motorun manşet Isp'si kendi _calculate_thrust_coefficient'inden geldiği için bu ikincil bir sayıdır ama JSON/proje kaydına giriyor.

### [ ] F035 — `correlation_runner.py::_mad_outliers`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
mad = median(|e - med|) ; aykırı <=> |e - med| > OUTLIER_MAD_FACTOR * mad  (OUTLIER_MAD_FACTOR = 3.0)
```

**Olması gereken:** Ham MAD, normal dağılım için sigma'nın 0.6745 katıdır; sigma tahmini MAD/0.6745 = 1.4826*MAD'dır. '3 sigma' kuralı isteniyorsa eşik 3*1.4826*MAD = 4.45*MAD olmalı (veya doğrudan modified z-score |0.6745*(e-med)/MAD| > 3.5 — Iglewicz & Hoaglin). Şu haliyle 3*ham MAD yalnızca 3/1.4826 = 2.02 sigma'ya karşılık geliyor. Ayrıca len(entries) >= 3 alt sınırı çok gevşek: n=3-5'te MAD tahmini anlamsızdır.

**Kaynak:** Iglewicz & Hoaglin, 'How to Detect and Handle Outliers', ASQC Quality Press, Vol. 16 of The ASQC Basic References in Quality Control, 1993 (modified z-score, 0.6745 ölçek sabiti). Rousseeuw & Croux, JASA 88(424), 1993 (MAD'ın tutarlılık çarpanı 1.4826). Koddaki 3.0 için kaynak bulunamadı — yorum satırı yok.

**Sayısal etki:** ÖLÇÜLDÜ (20000 Monte Carlo tekrarı, temiz normal veri): n=27'de 3*ham MAD verinin %6.2'sini aykırı işaretliyor (gerçek 3-sigma beklentisi %0.27) -> 23 kat fazla işaretleme; n=18'de %6.8; n=35'te %5.8; n=4'te %10.4. Gerçek koşuda karşılığı: solid burn_rate 27 girişin 5'ini (%18.5), liquid thrust_vac 4 girişin 1'ini (%25) aykırı işaretledi. Etki sunumsal ama ciddi: aykırılar ATILMIYOR (doğru karar) ama 'excl. outliers' satırı ana satırın hemen altına basılıyor ve solid burn_rate RMS'i %1.99 -> %0.70 (3 kat düşüş), liquid thrust_vac medAPE %0.2 -> %0.1 oluyor. Okur her zaman daha güzel olan ikinci satırı alıntılayabilir.

### [ ] F036 — `cycle_power_balance.py::solve_cycle (expander dalı, p_ref)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
p_ref = p_te * 1.7 * PA_PER_BAR   # h_in, TIT ve cp_turb hep bu SABİT tahminde okunuyor; PR çözüldükten sonra tekrarlanmıyor
```

**Olması gereken:** staged_combustion ve FFSC dallarında ön yakıcı basıncı için 6 adımlık DIŞ İTERASYON var (p_pb_guess -> detail['p_pb']); expander dalında aynı geri besleme YOK. Türbin gerçek giriş basıncı p_te*pr_root'tur, p_te*1.7 değil. Kriyojenik H2'de cp psödo-kritik tepe yüzünden basınca çok duyarlıdır; en az bir dış iterasyon eklenmeli (kod bunu 'coolprop_cp_pressure_assumption' ile etiketliyor ama sayısal etkisini vermiyor).

**Kaynak:** Gerçek gaz özellikleri: CoolProp 6.8.0 (H2: Leachman 2009 EOS).

**Sayısal etki:** ÖLÇÜLDÜ (H2, cp J/kgK): 40 K'de 40 bar 23112 / 64 bar 16221 (%-30); 50 K'de 40 bar 20487 / 64 bar 19161 (%-6); 60 K'de 40 bar 15387 / 64 bar 17009 (%+11). Kodun kendi RL10-benzeri çözümlerinde gerçek türbin giriş basıncı 44-70 bar arasında değişiyor, oysa özellikler hep 64 bar'da okunuyor. Türbin özgül işine etkisi bu rejimde %5-15 mertebesinde; 200 K üstü TIT'lerde ihmal edilebilir (%<1).

### [ ] F037 — `heat_transfer_analysis.py::_analyze_cooling_requirements`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
elif cooling_type == 'regenerative':
    coolant_flow_rate = heat_rate/(4180*50)
    required_surface_area = heat_rate/(2000.0*100)
```

**Olması gereken:** h = 20000 W/m^2K kullanılmalı — _coolant_side_coefficient rejeneratif için 20000 döndürüyor ve kendi docstring'i 'önceki 2000 W/m^2/K bir mertebe düşüktü' diyor. 2000 değeri eski sürümden kalmış. 'natural' (25) ve 'forced' (100) dalları _coolant_side_coefficient ile tutarlı; yalnız rejeneratif dal kopmuş. Ayrıca heat_sink_mass = E/(460*200) seçilen malzemeden bağımsız olarak çelik cp=460 J/kgK varsayıyor (bakır 385, alüminyum 896 — 2.3x'e kadar hata).

**Kaynak:** Modülün kendi merkezi kaynağı (_coolant_side_coefficient, Huzel & Huang Böl. 4: rejeneratif için 1e4-5e4 W/m^2K). Dış literatür atfı yok — 25/50/100/200 K sıcaklık farkları da kaynaksız mühendislik kabulü.

**Sayısal etki:** ÖLÇÜLDÜ. Aynı 60 bar motorda required_cooling_area = 13.56 m^2 döndü; h=20000 ile 1.36 m^2 olurdu. Yani rejeneratif 'gereken soğutma alanı' tam 10x fazla raporlanıyor (kullanıcıya doğrudan gösterilen alan). heat_sink_mass = 590 kg değeri de malzeme seçiminden bağımsız çelik varsayımıyla üretiliyor.

### [ ] F038 — `heat_transfer_analysis.py::_analyze_gas_side_heat_transfer`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
surface_area = pi*D*L + pi*(D/2)^2
total_heat_rate = chamber_heat_flux*surface_area + throat_heat_flux*throat_area
```

**Olması gereken:** Toplam ısı yükü konturun TAMAMI üzerinden integre edilmeli: Q = sum q(x)*2*pi*r(x)*ds. Şu anki ifade konverjan bölümü ve tüm diverjan nozulu tamamen dışarıda bırakıyor; boğaz akısını yalnız A_t (boğaz KESİT alanı, ıslak alan değil) üzerinde uyguluyor. analyze_axial_profile zaten doğru konturu üretiyor — integrali oradan almak yeterli.

**Kaynak:** Kaynak formül değil, geometrik ıslak-alan tanımı. Sutton & Biblarz Böl. 8'de toplam ısı yükü ıslak yüzey integrali olarak tanımlanır.

**Sayısal etki:** ÖLÇÜLDÜ. Pc=60 bar, Dc=0.12 m, Lc=0.35 m, Dt=0.08 m, eps=16 çelik motor: modül total_heat_rate = 2712 kW. Aynı motorun analyze_axial_profile çıktısını 200 istasyonda kontur boyunca integre ettim (konverjan+boğaz+diverjan) = 2074 kW; buna silindirik gövde (0.132 m^2 x 17.8 MW/m^2 ~ 2350 kW) eklenince gerçek toplam ~4400 kW. Yani yaklaşık %38 EKSİK tahmin, GÜVENSİZ yön: bu değer doğrudan coolant_flow_rate ve heat_sink_mass'ı boyutlandırıyor (soğutucu debisi ve ısı-yutucu kütlesi %38 küçük çıkıyor).

### [ ] F039 — `hrma/engines/injector_design.py::_solve_circuit (N₂O besleme basıncı kelepçesi)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
if spec_p_feed_given: p1_bar = min(p_feed_bar, p_sat_bar)
```

**Olması gereken:** Kullanıcının verdiği besleme basıncı doyma basıncının ÜSTÜNE çıkamıyor. Fiziksel olarak N₂O tankı helyum ile süper-şarj edilebilir (aşırı soğutulmuş sıvı) ve bu yaygın bir uçuş konfigürasyonudur; bu durumda P₁ > P_sat geçerlidir ve NHNE zaten κ = √((P₁−P₂)/(P_v−P₂)) ile doğru davranır (κ artar → SPI'ye yaklaşır). Kelepçe, geçerli bir fiziksel durumu sessizce yasaklıyor.

**Kaynak:** Dyer ve ark. AIAA 2007-5702 (NHNE aşırı-soğutulmuş dalı zaten tanımlı); Zilliac & Karabeyoglu, AIAA 2005-3549 (süper-şarjlı N₂O besleme)

**Sayısal etki:** ÖLÇÜLDÜ: T=293 K'de P_sat=50.54 bar. Kullanıcı p_feed=70 bar, Pc=30 bar verirse kod P₁'i 50.54'e kırpıyor. Kırpılmamış hesap (nhne_mass_flow doğrudan çağrıldı): P₁=70 bar → ṁ=0.0954 kg/s, κ=1.40; P₁=50.54 bar → ṁ=0.0592 kg/s, κ=1.00. Yani birim alan debisi %61 düşük çıkıyor → toplam enjeksiyon alanı ~1.6 KAT fazla boyutlanıyor.

### [ ] F040 — `hrma/engines/injector_design.py::design_injector (mu_ox / mu_fuel varsayılanı)`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
mu_ox = spec.get('mu_ox', 2e-4)  → nu_ox = mu_ox / rho_ox_l → smd_elkotb
```

**Olması gereken:** 2e-4 Pa·s LOX için makul (≈1.9e-4 @ 90 K) ama N₂O sıvısı için 293 K'de μ ≈ 6.3e-5 Pa·s'dir (~3.2 kat düşük). Varsayılan akışkandan bağımsız sabit; fluid_ox='n2o' iken doyma tablosundan/sıcaklıktan alınmalı.

**Kaynak:** NIST WebBook — N₂O sıvı viskozitesi ≈ 6.3e-5 Pa·s @ 293 K

**Sayısal etki:** ÖLÇÜLDÜ: Elkotb SMD ∝ ν^0.385 → μ=2e-4 vs 6.3e-5 kullanımı SMD'yi 1.56 KAT şişiriyor. Bulgu #3 (σ, 6.02x) ile birleşince N₂O showerhead SMD'si toplam ~9 kat aşırı tahmin ediliyor (56.6 µm yerine gerçekçi ≈ 6 µm mertebesi).

### [ ] F041 — `hrma/engines/injector_design.py::design_injector (rupe_factor)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
rupe = (rho_f * v_f**2 * d_f) / (rho_ox * v_ox**2 * d_ox)
```

**Olması gereken:** Formülün KENDİSİ doğrudur (Rupe'un ρV²d oranı kriteri). Ancak kodda her iki devre de v = Cd√(2ΔP/ρ) ile çözüldüğü ve genelde aynı ΔP kullanıldığı için ρv² = 2·ΔP·Cd² olur ve YOĞUNLUK/HIZ TAMAMEN SADELEŞİR: Rupe ≡ d_f/d_ox. Delik çapları da _plan_orifices'in ayrık band mantığından geldiği için kriter neredeyse her zaman ~1.0 çıkar. Yani Rupe kontrolü fiilen hiçbir şeyi test etmiyor — 'geçti' demesi tasarımın iyi olduğunu göstermiyor. Doğrusu: iki devrenin ΔP'si ayrı seçilebilmeli, ya da kriter tasarım DEĞİŞKENİ olarak (çap/ΔP çözülerek) uygulanmalı.

**Kaynak:** Rupe, JPL Progress Report 20-195 (1953) — unlike-doublet karışım kriteri (formül doğru; uygulama zarfı sorunlu)

**Sayısal etki:** ÖLÇÜLDÜ (sıvı, LOX/RP-1 benzeri: ṁ_ox=23, ṁ_f=10 kg/s, Pc=60, ρ_ox=1140, ρ_f=810, p_feed=75 bar her iki devre): ρv² = 1.825e6 (ox) = 1.825e6 (yakıt), rupe_factor = 1.0012, d_f/d_ox = 1.001. Momentum oranı ise 0.516 çıkıp doğru şekilde uyarı veriyor — yani kullanıcı 'Rupe tamam ama momentum kötü' diye çelişkili bir tablo görüyor.

### [ ] F042 — `hrma/utils/injector_design.py::_calculate_showerhead`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
v_exit = np.sqrt(2 * delta_P_Pa / self.rho_ox)  (A_inj ise Cd ile hesaplanıyor)
```

**Olması gereken:** Raporlanan alan A = ṁ/(Cd√(2ρΔP)) GEOMETRİK alandır; bu alan üzerindeki ortalama hız ṁ/(ρA) = Cd·√(2ΔP/ρ)'dir. Kod ise ideal (vena contracta) hızı √(2ΔP/ρ) raporluyor → 'exit_velocity' ile 'injection_area' birbiriyle tutarsız (ṁ = ρ·A·v sağlanmıyor). Kardeş modül hrma/engines/injector_design.py::_solve_circuit AYNI büyüklük için Cd·√(2ΔP/ρ) kullanıyor — iki modül farklı tanım veriyor. Weber ve Reynolds sayıları da bu hızdan besleniyor.

**Kaynak:** Sutton & Biblarz Böl. 8 (orifis akışı, Cd ve süreklilik); modüller arası tutarlılık

**Sayısal etki:** ÖLÇÜLDÜ (ṁ=2 kg/s, ρ=750, Pc=30, Cd=0.7): raporlanan v=40.0 m/s, süreklilik hızı ṁ/(ρA)=28.0 m/s → oran 1.429 = 1/Cd. Weber sayısı v²'ye bağlı olduğu için 675381 vs 330937 = 2.04 KAT fark. _check_warnings'in 20-50 m/s bandı da bu şişik hızla değerlendiriliyor (Cd düşükse yanlış 'çok hızlı' uyarısı).

### [ ] F043 — `hrma/utils/injector_design.py::_calculate_swirl (A_eff / exit_orifice_area)`

**Hüküm:** SAHTE_KAYNAK · **Görünür:** evet

**Koddaki denklem:**
```
A_eff = A_slots * 0.6 ; exit_orifice_area = A_eff
```

**Olması gereken:** 0.6 katsayısı için kaynak yok ('accounting for swirl losses' yorumu bir atıf değil). Daha önemlisi: swirl atomizörde ÇIKIŞ ORİFİS ALANI ile TEĞET GİRİŞ (yuva) ALANI birbirinden bağımsız geometrik büyüklüklerdir ve K = A_p/(D_s·d_o) ile ilişkilidir; A_o = 0.6·A_p diye bir fiziksel bağıntı yoktur. Ayrıca 0.6 ile deşarj katsayısı (kod ayrıca C_d=0.7 kullanıyor) arasında çift-sayım riski var.

**Kaynak:** kaynak bulunamadı (0.6 için); doğru ilişki: Lefebvre Böl. 6, K = A_p/(D_s·d_o)

**Sayısal etki:** ÖLÇÜLDÜ (ṁ=2 kg/s, Pc=30 bar, ρ=750): A_slot=95.2 mm² → A_eff = exit_orifice_area = 57.1 mm². Bu 'çıkış orifis alanı' hiçbir gerçek geometriye karşılık gelmiyor; hata büyüklüğü K'ya bağlı olduğu için mertebe tahmini veremiyorum (bağıntı yanlış tipte, kalibrasyon hatası değil).

### [ ] F044 — `hrma/utils/injector_design.py::_check_warnings (kavitasyon kriteri)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
if self.ox_phase == 'liquid' and self.delta_P_inj > 0.5 * self.P_tank: 'Cavitation risk detected'
```

**Olması gereken:** Kavitasyon kriteri buhar basıncı içermiyor. Doğrusu Nurick kavitasyon sayısıdır: K_c = (P₁ − P_v)/(P₁ − P₂); K_c ≲ 1.5-2 ise kavitasyon/hidrolik flip riski. ΔP > 0.5·P_tank ölçütü ne akışkana ne sıcaklığa bağlı — aynı modülün P_vapor bilgisi (51 bar @ 293 K, doğru) mevcut olmasına rağmen kullanılmıyor. Kardeş modül (engines) Nurick'i doğru uyguluyor.

**Kaynak:** Nurick, ASME J. Fluids Eng. 98 (1976) — K = (P₁−P_v)/(P₁−P₂)

**Sayısal etki:** Ölçmedim (yalnız uyarı metni, hiçbir boyut sürmüyor). Yön olarak: doymuş N₂O'da (P₁ = P_v) gerçek K_c = 0, yani kavitasyon KESİN — ama kod ΔP < 0.5·P_tank olduğu sürece hiç uyarmıyor. Ters yönde, düşük buhar basınçlı yakıtta ΔP büyükse yanlış-pozitif veriyor.

### [ ] F045 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
G_ox_avg = (G_ox_initial + self.G_ox_final)/2 ; reg_avg = regression_rate(a, n, G_ox_avg, ...) ; self.r_dot_avg = reg_avg['r_dot']
```

**Olması gereken:** Deneysel literatürde ve DB'nin measured.regression_rate_avg alanında raporlanan büyüklük UZAY-ZAMAN ORTALAMASIDIR: r̄ = (D_final − D_initial)/(2·t_b). Kod bunun yerine 'uç noktaların aritmetik ortalama akısında değerlendirilen anlık regresyon'u raporluyor. İki tanım aynı değildir: (i) r=a·G^n, n<1 için G'de içbükeydir, Jensen gereği a·ort(G)^n ≥ ort(a·G^n); (ii) G_ox(t) ∝ D⁻² azalan-dışbükey olduğundan uç nokta aritmetik ortalaması gerçek zaman ortalamasının üstündedir. Model D_final'ı ZATEN hesapladığı için (D_f−D_i)/(2·t_b) bedelsiz ve tam tutarlı olurdu.

**Kaynak:** Uzay-zaman ortalamalı regresyon tanımı: Chiaverini & Kuo (2007) Böl. 2; Karabeyoglu et al., JPP 20(6) 2004 veri indirgeme bölümü (kütle kaybı / çap ölçümü yöntemi)

**Sayısal etki:** ÖLÇÜLDÜ. DB'nin HTPB+parafin kümesinde (n=60) kodun raporladığı r_dot_avg ile bias −%25.6, aynı modelin kendi zaman ortalaması ((D_f−D_i)/2t_b) ile bias −%29.7. Yani mevcut tanım modelin gerçek sapmasını sistematik olarak +%5.8 maskeliyor. Doğrulama tablosundaki −%20.2 bias, tutarlı tanımla yaklaşık −%26'ya iner.

### [ ] F046 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
grain_design['grain_type'] = 'cylindrical_bore' ; A_port = np.pi*(D_port/2)**2 ; G_ox = self.mdot_ox/A_port  # port sayısı parametresi YOK
```

**Olması gereken:** N portlu grain'de her portun akısı G_ox = mdot_ox/(N·A_port_tek), yanma çevresi ise N·π·D'dir. Kod tüm grain'leri tek dairesel port varsayıyor, port sayısı ne girdi ne çıktı olarak var. Wagon-wheel / çok portlu geometri seçilirse ya reddedilmeli ya da N açıkça modellenmelidir.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 16 (çok portlu grain akı dağılımı); Story, 'Large-Scale Hybrid Motor Testing', NTRS 20060047689 (AMROC DM-01 çok portlu)

**Sayısal etki:** ÖLÇEMEDİM (kodda N parametresi olmadığı için karşılaştırma koşulamaz). Büyüklük mertebesi: verilen mdot_ox ve toplam port alanı için tek-port varsayımı G_ox'u N kat büyütür, yanma çevresini N kat küçültür; r_dot ∝ N^n, mdot_f ∝ N^(n−1) → N=4 için r_dot ~2.2 kat yüksek, mdot_f ~%45 düşük çıkar. Doğrulama DB'sinde grain_geometry='multi_port' kayıtları var (hyb-amroc1993-htpb-lox-dm01-b1) ve bunlar tek-port modeliyle koşuluyor.

### [ ] F047 — `hybrid_rocket_engine.py::calculate`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
self.At = self.mdot_total*self.C_star/(self.P_c*1e5*CD)  ; sonrasında Pc ve CF yanma boyunca SABİT varsayılır (boğaz erozyonu terimi yok)
```

**Olması gereken:** Hibrit motorlarda grafit/fenolik boğaz oksitleyici-zengin akışta belirgin erozyona uğrar; boğaz alanı büyüdükçe Pc = mdot·c*/At düşer, CF ve Isp düşer. Katı motor modülünde erozyon modeli VAR (solid_rocket_engine.py::erosion_rate), hibritte yok. En azından bir erozyon oranı girdisi + Pc(t) düzeltmesi ya da açık bir 'erozyon modellenmiyor' uyarısı olmalı.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 15/16; Chiaverini & Kuo (2007) lüle erozyonu bölümü; DB kaydı hyb-amroc1993 notu: boğaz alanı 364→418 in² (yakmalar arası ölçülmüş gerçek erozyon)

**Sayısal etki:** ÖLÇEMEDİM (modelde erozyon parametresi yok). Literatür mertebesi: 10-30 s yanmada grafit boğazda %5-15 çap büyümesi tipiktir → At %10-32 artar → Pc aynı oranda düşer → CF ve Isp birkaç % düşer. AMROC kaydında ölçülen alan artışı %15 (çapta %7.2). Tasarım noktası sabit-Pc raporladığı için kullanıcı bu düşüşü hiç görmüyor.

### [x] F048 — `kinetic_efficiency.py::KineticEfficiency._evaluate_engineering`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
damkohler = (t_res / tau_chem) * (throat_diameter / 0.05);  t_res = L* * rho_c * c* / P_c;  tau_chem = 1.5e-3 * (20/P_c_bar)**2
```

**Olması gereken:** Alt formullerin her biri dogru ve kaynakli: t_res = L*.rho_c.c*/P_c gercekten Sutton Es. 8-9'un (t_s = V_c.rho_c/mdot) turevi ve boyutsal olarak s veriyor; uc-cisimli rekombinasyon icin tau ~ P^-2 dogru. ANCAK bunlarin bir Damkohler'e birlestirilmesi kaynaksiz: LULE icindeki rekombinasyon donmasini yoneten akis zaman olcegi ODA kalis suresi degil, LULE genisleme zaman olcegidir (tau_exp ~ boğaz yaricapi/a*, Bray ani-donma argumani). Kod bunu yalnizca dogrusal bir D_t/0.05 carpaniyla yamiyor ve TAU_CHEM_REF_S = 1.5 ms hicbir kaynaga dayanmiyor (kodun kendi yorumu 'order-of-magnitude anchor' diyor). Sonuc: tahmin, lule kinetigini fiziksel olarak yonetmeyen bir oda parametresine (L*) duyarli.

**Kaynak:** Kaynak bulunamadi (TAU_CHEM_REF_S = 1.5e-3 s ve D_THROAT_REF_M = 0.05 m icin). Dogru olan alt formuller: Sutton & Biblarz 9. baski Es. 8-9 (kalis suresi); Bray, K.N.C., J. Fluid Mech. 6 (1959) ani-donma analizi; Vincenti & Kruger Bol. 8. Buyukluk mertebesi capasi: NASA SP-8120 (1976) kinetik kayip %0.1-3 bandi — kodun urettigi degerler bu bantta.

**Sayısal etki:** OLCULDU. Egilimler fiziksel olarak DOGRU: Pc 5->250 bar icin kayip %3.88 -> %0.03; D_t 0.01->1.0 m icin %3.45 -> %0.20. Mertebe SP-8120 bandiyla uyumlu. SORUN: yalnizca L* degistirilerek (Pc=20 bar, D_t=0.05 m sabit) kayip %2.61 (L*=0.6 m) -> %1.06 (L*=3 m), yani 2.5x oynuyor — L* lule rekombinasyonunu yonetmez. Bu sapma modulun raporladigi bandin ([0.707, 3.446]%) ICINDE kaliyor, dolayisiyla kullanici yanlis yonlendirilmiyor ama 'L* degistirince kinetik kayip degisiyor' davranisi fiziksel degil.

### [ ] F049 — `nozzle_design.py::_calculate_nozzle_geometry`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
wall_thickness = max(0.003, dt·0.1);  nozzle_mass = surface_area · wall_thickness · 7850
```

**Olması gereken:** Duvar kalınlığı boğaz ÇAPININ %10'u olamaz — kalınlık basınç ve malzeme dayanımından gelir (ince cidar: t = P·r/σ_izin, emniyet katsayısıyla) ve büyük motorlarda çapla lineer büyümez. 'max(3 mm, 0.1·dt)' kuralının hiçbir kaynağı yok ve ölçekle patlıyor. Ayrıca yoğunluk 7850 kg/m³ (çelik) sabit; grafit/ablatif/Inconel lüleler için yanlış.

**Kaynak:** Kaynak bulunamadı — kodda atıf yok. Basınç kabı kalınlığı için doğru referans: Huzel & Huang NASA SP-125 Böl. 4; Sutton & Biblarz 9. baskı Böl. 8.

**Sayısal etki:** ÖLÇÜLDÜ: At=0.05 m² (dt=252 mm), ε=25, bell → wall_thickness 25.2 mm, estimated_mass 780.6 kg. Küçük motorda (At=0.01 m², dt=113 mm) → 11.3 mm. Kalınlık değeri visualization.py'de lüle cidarını ÇİZMEK için okunuyor (motor_data['nozzle_geometry']['wall_thickness']), yani kullanıcı bu sayıyı ekranda geometri olarak görüyor.

### [ ] F050 — `nozzle_design.py::_calculate_nozzle_performance`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
pressure_ratio = chamber_pressure/exit_pressure; cf_momentum = f(exit_pressure/chamber_pressure); pa = exit_pressure (ambient_pressure=None ise) → cf_ideal = cf_momentum + ε·0
```

**Olması gereken:** exit_pressure, expansion_ratio ile TUTARLI olmalı: p_e izentropik alan-Mach bağıntısından ε ve γ ile çözülüp CF'ye o değer girmeli (fonksiyonun kendisi calculate_nozzle_flow_properties içinde bu çözümü zaten yapıyor). Şu an ε ile p_e bağımsız iki girdi ve tutarlılık denetimi yok; hybrid_rocket_engine.py::calculate 4. konumsal argümana P_a geçiyor (exit_pressure=P_a) → sabit geometrili lülede CF/Isp genişleme oranından TAMAMEN bağımsız çıkıyor.

**Kaynak:** Denklemlerin kendisi doğru: Sutton & Biblarz, Rocket Propulsion Elements 9. baskı Eq. 3-30 (CF) ve Eq. 3-32 (c*). Hata denklemde değil, girdi sözleşmesinde.

**Sayısal etki:** ÖLÇÜLDÜ (γ=1.20, R=350, Tc=3400 K, Pc=40 bar, konik): ε=4,8,16,40,100 için design_nozzle'ın döndürdüğü specific_impulse HEPSİNDE aynı: 252.53 s. İzentropik p_e(ε) ile hesaplanan doğru değerler: ε=8→250.9 s (+0.7%), ε=16→231.2 s (+9.3%), ε=40→144.7 s (+74.6%). c* değeri ayrıca formülle birebir doğrulandı (1682.06 = 1682.06).

### [ ] F051 — `nozzle_design.py::_design_bell_nozzle`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
theta_n = 30.0; theta_e = 8.0  (genişleme oranından BAĞIMSIZ sabitler); Ld = 0.8·(re − rt)/tan(15°)
```

**Olması gereken:** Rao %80 bell'de θn ve θe genişleme oranının fonksiyonudur (Rao 1958 grafikleri; Sutton & Biblarz 9. baskı Fig. 3-14): kabaca ε=10 → θn≈22-25°, θe≈13-15°; ε=25 → θn≈27°, θe≈11°; ε=50 → θn≈30°, θe≈9°; ε=100 → θn≈32°, θe≈7-8°. Sabit (30°, 8°) çifti ancak ε≈50-100 için doğrudur. ε'ye bağlı bir enterpolasyon tablosu ya da Rao karakteristik çözümü gerekir. Zarf denetimi de yok: ε=4 ile çağrıldığında sessizce ε≈70 geometrisi üretiliyor.

**Kaynak:** Kodun atfı (Rao 1958; Sutton Fig. 3-14; Huzel & Huang Fig. 4-15) DOĞRU kaynaklardır — ama o kaynaklar tam olarak açıların ε ile değiştiğini söyler; kod bunu sabitlemiş. Ld'nin %80 tanımı da eksik: referans 15° konik uzunluğu literatürde boğaz yayı katkısını (R_1(sec θ−1)/tan θ) içerir, kod yalnız (re−rt)/tan15 alıyor.

**Sayısal etki:** θe=8° → λ=0.9951; ε=10'a uygun θe≈14° → λ=0.9851. Fark %1.0 Isp (ayrık kayıp çarpımında doğrudan). Ld eksik terimi: R_1=1.5·rt için ~0.198·rt, ε=10'da toplam 8.06·rt'ye göre %2.5 kısa uzunluk. Kontur ayrıca CAD/STEP/3B görselleştirmeye tek kaynak (sample_nozzle_inner_contour) olduğundan geometri de düşük-ε motorlarda gerçek Rao konturu değil.

### [ ] F052 — `pressurant_sizing.py::autogenous_pressurant (heat_duty_j)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
heat_duty_j = m_gas * gas['cp'] * max(T - 90.0, 0.0)   # ~90 K kriyojenik taban
```

**Olması gereken:** Sıvı iticiyi gaz haline getirmenin entalpi yükü = (sıvı duyulur ısı) + BUHARLAŞMA GİZLİ ISISI h_fg + (gaz duyulur ısı). Kod yalnız gaz cp'siyle duyulur ısı hesaplıyor, h_fg'yi TAMAMEN atlıyor. Ayrıca 90 K sabit tabanı yalnız oksijen için doğru; metan NBP 111.67 K, hidrojen NBP 20.28 K. Doğrusu: dh = h(T_besleme, p_tank) - h_sıvı(NBP) — CoolProp ile tek satır.

**Kaynak:** h_fg değerleri: NIST WebBook / CoolProp 6.8.0 (O2 213.1 kJ/kg, CH4 510.8 kJ/kg, H2 449.1 kJ/kg — hepsi NBP'de).

**Sayısal etki:** ÖLÇÜLDÜ (6 bar tank, kodun kendi besleme sıcaklıkları): GOX 250 K -> kod 147 kJ/kg, gerçek 359 kJ/kg (%-59 EKSİK). GCH4 250 K -> kod 357, gerçek 798 kJ/kg (%-55). GH2 200 K -> kod 1573, gerçek 2558 kJ/kg (%-39). Yani ısı değiştirici yükü ~2 kat eksik raporlanıyor; alan 'approx_heat_duty_j' olarak API'den dönüyor.

### [ ] F053 — `pressurant_sizing.py::autogenous_pressurant (m_gas)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
m_gas = P_tank*V_p/(R*T)/eta   # collapse/ullage-çökme düzeltmesi YOK
```

**Olması gereken:** regulated_pressurant fonksiyonu kriyojenik tanklarda gazın soğuk sıvıya ısı kaptırıp büzülmesi için 'collapse_factor' (1.0-1.6) sunuyor; autogenous yolunda böyle bir düzeltme YOK. Oysa autogenous'ta durum daha ağırdır: GOX bir LOX tankının serbest yüzeyinde yoğuşur, GCH4 metan üstünde yoğuşur — gerçek gaz talebi ideal envanterin belirgin üstündedir. En azından aynı collapse_factor parametresi buraya da açılmalı ve varsayılan 1.0 'iyimser alt sınır' diye etiketlenmeli.

**Kaynak:** Basınçlandırma-çökmesi kavramı: Sutton & Biblarz 9. baskı Böl. 6; Huzel & Huang Böl. 5 (pressurant collapse / use factor). Kodun kendi regulated dalı da bu bandı 1.0-1.6 diye alıntılıyor.

**Sayısal etki:** ÖLÇÜLEMEDİ — sayısal çökme faktörü tank geometrisi, çalkalanma ve giriş difüzörüne bağlı; bu modülde modellenmiyor. Büyüklük mertebesi tahmini: kodun kendi alıntıladığı 1.0-1.6 bandı temel alınırsa gaz kütlesi %20-60 EKSİK. liquid_rocket_engine.py'de 'fraction_of_propellant' olarak itici bütçesine giriyor, o yüzden etkisi taşınıyor.

### [ ] F054 — `pressurant_sizing.py::regulated_pressurant`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
m_iso = P_tank*V_p/(R*T0)*f_corr ;  m_adia = P_tank*V_p/(R*T_adia)*f_corr ;  usable_density = (P_store - P_min)/(R*T0) ;  bottle_volume = m_delivered/usable_density
```

**Olması gereken:** Kodlanan denklem ULLAGE gaz envanteridir (ideal gaz yasası), depolanan-gaz BOYUTLANDIRMA denklemi değildir; docstring'in '(Sutton Eq. 6-1)' atfı bu yüzden şüpheli. Klasik kapalı form (Sutton Böl. 6 / Huzel & Huang Böl. 5, adyabatik enerji dengesinden türetilir): m_g = gamma*p_t*V_p / (R*T0*(1 - p_t/p_s)) ve V_şişe = gamma*p_t*V_p/(p_s - p_t). Ayrıca kod TUTARSIZ karışım yapıyor: teslim edilen kütleyi TAM ADYABATİK (en soğuk, en ağır) sınırdan alırken şişe boşalmasını İZOTERMAL kabul ediyor. Sabit basınçlı boşaltmada ullage gazı asimptotik olarak GİRİŞ sıcaklığına yaklaşır (d(mh)=h_in·dm), tüm ullage hiçbir zaman tam genişlemiş şişe sıcaklığına inmez; m_adia bu yüzden gevşek bir üst sınırdır ve 'recommended' olarak seçilmesi aşırı muhafazakârdır.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 6 (gaz basınçlı besleme) — bölüm doğru, denklem numarası doğrulanamadı; kapalı form bağımsız olarak enerji dengesinden türetildi ve Huzel & Huang Böl. 5 ile aynı yapıdadır.

**Sayısal etki:** ÖLÇÜLDÜ (V_p=1 m3, T0=293.15 K): He 200->20 bar: kod m_stored=9.27 kg / V_şişe=282 L, kapalı form 6.08 kg / 185 L => kod 1.52x. He 300->20 bar: 10.47 kg / 213 L vs 5.87 kg / 119 L => 1.79x. N2 200->20 bar: 49.87 kg / 217 L vs 35.76 kg / 156 L => 1.39x. Yani şişe kütlesi/sayısı %39-79 fazla çıkıyor (bottle_count kullanıcıya gösteriliyor).

### [ ] F055 — `pressurant_sizing.py::regulated_pressurant / ::blowdown_pressurant (GAS_PROPERTIES)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
usable_density = (P_store - P_min)/(R*T0) ; stored_mass = P_store*bottle_volume/(R*T0) ; gas_mass = P0*V_u0/(R*T0)
```

**Olması gereken:** 200-400 bar depolamada ideal gaz yasası yetersiz; sıkıştırılabilirlik faktörü Z gereklidir: rho = p/(Z·R·T). Docstring'de Z'den hiç söz edilmiyor ve 'STANDARD_STORAGE_PRESSURES = (200e5, 300e5)' varsayılanları tam bu rejimde. CoolProp zaten projede kurulu (tank_blowdown.py kullanıyor) — helyum/azot için Z(p,T) doğrudan alınabilir.

**Kaynak:** Gerçek gaz verisi: CoolProp 6.8.0 (Helium: Ortiz-Vega 2013 EOS; Nitrogen: Span 2000 EOS), NIST WebBook ile aynı kaynak.

**Sayısal etki:** ÖLÇÜLDÜ: He 200 bar/293 K Z=1.095, 300 bar/293 K Z=1.141, 300 bar/200 K Z=1.213, 400 bar/200 K Z=1.281. N2 200 bar/293 K Z=1.052, 300 bar Z=1.140. Sonuç: aynı su hacmindeki şişeye sığan gerçek kütle kodun sandığından %10-14 (He 200-300 bar) / %5-14 (N2) DAHA AZ; yani şişe hacmi ve bottle_count o oranda EKSİK boyutlanıyor. Bu, bir önceki bulgunun (%39-79 fazla boyutlama) tersi yönde çalışır ama onu tamamen dengelemez.

### [x] F056 — `record_adapters.py::_run_hybrid (regresyon katsayısı in-sample denetimi yokluğu)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
flux_mode='ox' ile HybridRocketEngine; regresyon katsayıları propellant_database.HYBRID_REGRESSION_COEFFICIENTS['paraffin'] = {'a': 1.17e-4, 'n': 0.62}; predictions['regression_rate'] ana istatistiğe giriyor
```

**Olması gereken:** Katı tarafta burn_rate_db.BURN_RATE_LAWS[...]['fit_source_records'] alanı sayesinde in-sample kayıtlar tespit edilebiliyor. Hibrit regresyon katsayıları için BÖYLE BİR ALAN YOK — dolayısıyla hybrid regression_rate hücresine giren kayıtların, katsayıyı üreten fitin veri setinde olup olmadığı YAPISAL OLARAK denetlenemiyor. HYBRID_REGRESSION_COEFFICIENTS girdilerine de fit_source_records eklenmeli.

**Kaynak:** Katsayının kendi künyesi doğru ve kodda yazılı: propellant_database.py — 'paraffin': Karabeyoglu et al., J. Propulsion and Power 20(6), 2004 (SP-1a) ve Zilliac & Karabeyoglu, AIAA 2006-4504, Tablo 2 (a=0.488, n=0.62; r mm/s, G g/cm²·s -> a_SI = 0.488e-3 * 10^-0.62 = 1.17e-4 — DÖNÜŞÜMÜ KONTROL ETTİM, doğru). Kayıt künyesi: Karabeyoglu, Zilliac, Castellucci, Urbanczyk, Stevens, Inalhan, Cantwell, AIAA 2003-1162, NASA Ames HCF, SP-1a parafin. Aynı yazar grubu, aynı yakıt formülasyonu, aynı tesis. AIAA 2006-4504 Tablo 2'nin fit veri kümesinin tam listesini DOĞRULAYAMADIM (makale metnine erişmedim) — bu yüzden 'in-sample' iddiasında bulunmuyorum, yalnız denetlenemez olduğunu bildiriyorum.

**Sayısal etki:** ÖLÇEMEDİM (kaynak makalenin fit veri kümesi teyit edilemedi). Büyüklük mertebesi: hybrid regression_rate hücresinin 35 girişinin 17'si (%49) hyb-karabeyoglu2003-paraffin-gox-* kayıtlarıdır. Bu 17 kayıt gerçekten fit kaynağıysa hücrenin yarısı in-sample demektir; hücrenin bias'ı -%20.2, medAPE %35.1 olduğuna göre in-sample bile OLSA model hâlâ ciddi sapıyor — yani bu bulgunun mevcut sayıları güzelleştirme yönünde bir etkisi görünmüyor, risk ileriye dönüktür (katsayı iyileştirilirse sahte iyileşme görünür).

### [ ] F057 — `regen_cooling.py::_interp_table`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
t = min(max(temperature, t_col[0]), t_col[-1]) ; 'clamped': bool(...)
```

**Olması gereken:** Üretilen 'clamped' bayrağı solve() içinde HİÇ okunmuyor (grep ile doğruladım: yalnız 274. satırda üretiliyor, tüketen yok). Tablo sınırı dışına çıkan istasyonlar için — Jackson yolundaki jackson_wall_clamped uyarısının muadili gibi — açık bir uyarı üretilmeli. RP-1 tablosu 500 K'de, su tablosu 400 K'de bitiyor; RP-1 rejeneratif devrelerde yığın sıcaklığı rutin olarak 500 K'yi aşar (modülün kendi koklaşma eşiği 561 K cidar sıcaklığı).

**Kaynak:** Incropera & DeWitt 6. baskı Tablo A.6 (su, 280-400 K bandı); RP-1 tablosu zaten 'approximate' etiketli mühendislik derlemesi. Tablo dışı kullanım kaynağın geçerlilik zarfının dışıdır.

**Sayısal etki:** ÖLÇTÜM (su üzerinden, CoolProp ile karşılaştırarak): 459 K / 80 bar'da tablo klampı rho=937 (gerçek 885), mu=2.17e-4 (gerçek 1.47e-4, %48 yüksek), Pr=1.342 (gerçek 0.960). Sabit mdot'ta h_c oranı 0.856 — yani klamplı tablo h_c'yi %14 EKSİK veriyor (cidar sıcaklığında muhafazakâr yön). RP-1 için CoolProp muadili olmadığından 500 K üstü her istasyon sessizce donmuş özellik kullanıyor; benzer büyüklükte (%15-30) bir sapma bekliyorum ama RP-1 referans verisi olmadan ÖLÇEMEDİM. Bu ortamda CoolProp KURULU, dolayısıyla su yolu şu an etkilenmiyor; coolant_props_source='table' seçilirse veya CoolProp'suz kurulumda etkilenir.

### [ ] F058 — `regression_analysis.py::regression_rate`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
mdot_f = rho_f*np.pi*port_diameter*grain_length*r_dot ; G_fuel = mdot_f/A_port ; G_total = G_ox + G_fuel
```

**Olması gereken:** Marxman'da G_total YEREL bir büyüklüktür: G_total(x) = G_ox + (1/A_port)*∫₀ˣ ρ_f·π·D·r dx'. Baş uçta (x=0) G_fuel=0, kuyruk uçta tam değer. Kod, TÜM grain boyunca üretilen yakıtı port ÇIKIŞ değeri olarak alıp bunu tek istasyon değeri gibi kullanıyor. Boy-ortalaması alınırsa G_fuel ≈ çıkış değerinin YARISI olur. Docstring bunu 'konservatif üst sınır' diye kabul ediyor ama sonuç r_dot, port çapı ve yakıt debisi olarak kullanıcıya doğrudan sayı olarak sunuluyor — konservatiflik burada belirsizlik değil sistematik sapmadır.

**Kaynak:** Marxman & Gilbert (1963); Sutton & Biblarz 9. baskı Böl. 16 (yerel akı tanımı); Chiaverini & Kuo (2007) Böl. 2

**Sayısal etki:** HESAPLANDI (analitik, n=0.555): çıkış değeri yerine boy-ortalaması (G_fuel/2) kullanılsaydı r_dot oranı (1+1/OF)^n / (1+1/(2·OF))^n olurdu → O/F=6'da −%4.2, O/F=2'de −%11.4. Bu, yukarıdaki flux_mode bulgusunun ÜSTÜNE binen ikinci çarpandır; ikisi birlikte O/F=2'de r_dot'u toplam ~%33 yukarı iter.

### [ ] F059 — `six_dof_trajectory.py::BarrowmanAero.__init__`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
cn_fins = (4·n·(s/d)²)/(1+sqrt(1+(2·l_mid/(cr+ct))²)) ; self.cn_alpha = cn_nose + cn_fins  (Mach'tan bağımsız, sabit)
```

**Olması gereken:** C_Nα ve x_cp Mach'a bağlı olmalı. Barrowman lineer teorisi sıkıştırılamaz (düşük subsonik) sonuçtur; OpenRocket subsonikte Prandtl-Glauert (1/β, β=sqrt(1−M²)), süpersonikte ayrı kanat teorisi uygular. Kod tüm Mach'larda tek sabit değer kullanıyor.

**Kaynak:** Barrowman 1967 (geçerlilik: düşük subsonik, küçük α); Niskanen 2009 OpenRocket Technical Documentation — sıkıştırılabilirlik düzeltmesi bölümü.

**Sayısal etki:** ÖLÇEMEDİM (kodda Mach'lı referans yok). Büyüklük mertebesi: ince profil 2B eğimi subsonikte 2π/β, süpersonikte 4/sqrt(M²−1); M=2'de 6.28→2.31, yani kanat normal-kuvvet eğimi ~%60 düşer. Kod bu düşüşü modellemediği için süpersonikte kanat etkinliğini ve statik marjı FAZLA gösterir (iyimser stabilite hükmü). Test aracım M_max=1.18'e ulaştı — bu zarfa girmek tipik.

### [ ] F060 — `six_dof_trajectory.py::SixDOFTrajectory.__init__`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
latitude_deg=0.0, coriolis=True  (imza varsayılanları)
```

**Olması gereken:** Coriolis varsayılan AÇIK ve enlem varsayılan 0° (EKVATOR) → yatay Coriolis MAKSİMUM. Enlem verilmediğinde ya coriolis=False olmalı ya da enlem zorunlu kılınmalı. Çağıran katman (app.py::six_dof_analysis) latitude_deg'i HİÇ geçmiyor, dolayısıyla her kullanıcı ekvator Coriolis'i alıyor.

**Kaynak:** Coriolis ivmesinin enlem bağımlılığı: dik atışta yatay bileşen ∝ cos φ (klasik sonuç).

**Sayısal etki:** ÖLÇÜLDÜ (dik atış, apoje ~4 km): sürüklenme lat=0 → 8.606 m batı; lat=39.9 → 6.595 m batı; lat=60 → 4.295 m; lat=90 → 0.000 m (kutupta Ω∥v, doğru). Ekvator varsayımı 39.9°N sahada sürüklenmeyi %30.5 fazla gösteriyor. Mutlak büyüklük küçük (metre mertebesi) ama v2.6.2'nin eklediği tek yeni fiziği doğrudan bozuyor.

### [ ] F061 — `six_dof_trajectory.py::SixDOFTrajectory._derivatives`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** hayır

**Koddaki denklem:**
```
c_mq = -self.aero.cn_alpha * (arm / self.aero.d) ** 2 ; M_b[1] += qbar*S*d*c_mq*(w_b[1]*d/(2*u_mag))
```

**Olması gereken:** c_mq = -2.0 * cn_alpha * (arm/d)². Türetme: CP'de indüklenen α = q·l/V → F_N = q̄·S·C_Nα·(q·l/V), kol l → M = −q̄·S·C_Nα·l²·q/V. Boyutsuzlaştırma M = q̄·S·d·C_mq·(q·d/2V) ile eşitlenince C_mq = −2·C_Nα·(l/d)² çıkar. Koddaki katsayı tam olarak yarısı.

**Kaynak:** Standart pitch-damping türevi (Barrowman tabanlı model roket stabilite formülasyonu; Mandell/Caporaso/Bengen 'Topics in Advanced Model Rocketry', sönüm momenti katsayısı C2A). Kod docstring'i 'Niskanen §4.2.3' diyor — bu atfı çevrimdışı doğrulayamadım, bölüm numarası şüpheli.

**Sayısal etki:** ÖLÇÜLDÜ (doğrudan moment testi, α=0, q=1 rad/s, V=250 m/s, h=1000 m): kod −0.3586 N·m, analitik −0.7171 N·m → oran tam 0.5000. Uçuş etkisi ÖLÇÜLDÜ ve KÜÇÜK: c_mq iki katına çıkarılınca apoje %0.025, max_alpha %0.3 değişti (SM=1.6 cal); SM=0.80 cal düşük marjda bile max_alpha farkı %0.2. Yani formül kesin yanlış ama denenen zarfta sayısal etkisi ihmal edilebilir (α quasi-statik trim'e hakim, salınım transienti değil).

### [ ] F062 — `six_dof_trajectory.py::SixDOFTrajectory._derivatives`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
M_b sadece aerodinamik sönüm içeriyor; jet (itki) sönümü terimi yok
```

**Olması gereken:** Yanma sırasında jet damping terimi eklenmeli: M_jet = −ṁ·(x_e − x_cg)²·ω_pitch (kütle akışının araçtan çıkarken taşıdığı açısal momentum). Modelin sönüm bütçesi yanma fazında eksik.

**Kaynak:** Roket uçuş dinamiği standart terimi (NASA SP-8036 / Greensite; jet damping türevi ṁ·l_e²). Barrowman'ın orijinal statik stabilite çalışmasında yok, 6-DOF literatüründe standart.

**Sayısal etki:** TAHMİN + KISMİ ÖLÇÜM: test motoru (ṁ=2 kg/s, x_e−x_cg≈1.05-1.2 m) için jet sönümü ≈ 2.2-2.9 N·m/(rad/s). Aynı koşulda aerodinamik sönüm (analitik, doğru katsayıyla) ≈ 0.43 N·m/(rad/s), kodun uyguladığı ise ≈ 0.21. Yani yanma fazında toplam sönüm ~5-13 kat eksik. Uçuş çıktısındaki etkisi ölçülemedi (kod yamalanmadan jet terimi eklenemiyor); yukarıdaki C_mq×2 deneyi sönüm duyarlılığının bu zarfta düşük olduğunu gösterdiği için etkinin de küçük olması beklenir, ama rüzgâr kesmesi/gust senaryolarında büyür.

### [ ] F063 — `six_dof_trajectory.py::SixDOFTrajectory._derivatives`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
g = G0 * (R_EARTH/(R_EARTH+h))**2  (G0 = 9.80665 sabit)
```

**Olması gereken:** Modül docstring'i 'merkezkaç WGS84 normal yerçekimine katlanmıştır' diyor ve latitude_deg parametresi alıyor; ancak kod enlemden bağımsız 9.80665 kullanıyor. Beyan edilen dönen-çerçeve tutarlılığı sağlanmıyor. hrma/analysis/launch_site.py::local_gravity(lat, alt) (NIMA TR8350.2 Denk. 4-3) zaten mevcut; taban değer oradan alınmalı. Ters-kare irtifa bağımlılığının KENDİSİ doğru (serbest-hava gradyanı −3.086e-6 s⁻² ile birinci mertebede uyumlu).

**Kaynak:** WGS84 normal yerçekimi (Somigliana): ekvator 9.7803 m/s², kutup 9.8322 m/s²; 9.80665 ~45° enlem tanımlı standart değer.

**Sayısal etki:** TAHMİN: ekvator/kutupta g hatası ±%0.27. Serbest tırmanışta apoje ≈ v²/2g olduğundan apojede ~%0.27 sistematik sapma. Sayısal olarak küçük; asıl sorun docstring'in gerçekleşmemiş bir fiziği beyan etmesi ('asla uydurma' ilkesi).

### [x] F064 — `six_dof_trajectory.py::_drag_coefficient_mach`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
M<0.8: cd0 ; M<1.05: cd0*(1+2*(M−0.8)) ; else: cd0*(1.05+0.45*exp(−1.3*(M−1.05)))
```

**Olması gereken:** Eğrinin ŞEKLİ (subsonik plato → M≈1.05'te ~1.5·Cd0 transonik tepe → süpersonik ~1.05·Cd0 platosu) literatürle niteliksel uyumlu. Ancak docstring 'trajectory_analysis ile aynı şekil' diyor — DEĞİL. İki modül aynı araç için farklı sürükleme veriyor. Katsayıların (0.45, 1.3, 1.05 ve 2D'deki 1.3, tau=2.0) hiçbiri belirli bir yayına izlenebilir değil.

**Kaynak:** Hoerner 'Fluid-Dynamic Drag' 1965 Böl.16 ve OpenRocket dokümantasyonu transonik tepe ~1.5× mertebesini destekler; SAYISAL katsayılar için kaynak bulunamadı (uydurma kaynak yazmıyorum).

**Sayısal etki:** ÖLÇÜLDÜ (cd0=1 normalize): M=1.20'de 6-DOF 1.4203 / 2D 1.3000 → %9.25 fark; M=3.0'da −%5.73; M≤1.05'te birebir aynı. Test aracı M_max=1.18 — yani tam ayrışma bölgesinde. Aynı motorun 2D ve 6-DOF panelleri farklı apoje verir.

### [ ] F065 — `solid_rocket_engine.py::_apply_overrides (erosive_k / temp_coeff form varsayılanlarının yakıt tablosunu ezmesi)`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
m = self._override_val('erosive_k', 0.0, 1.0);  if m is not None: self.erosive_burning_coeff = m   # UI varsayılanı 0.0002
```

**Olması gereken:** v2.4.5'te '×0.58 yeniden kalibre edildi' denen yakıt-başına k değerleri (APCP 0.0136, KNSU 0.0155, BP 0.0110, DB 0.0115, sugar 0.0123) UI yolunda ÖLÜ VERİdir: solid.html her koşuda erosive_k=0.0002 gönderiyor ve tabloyu eziyor. Form alanı boş bırakıldığında (ya da yakıt seçildiğinde) tablo değerinin kazanması gerekir. Aynı desen temp_coeff'te de var: APCP tablosu σ_p=0.0042 iken UI 0.002 gönderip eziyor. Ayrıca UI'daki 'erosive_m' (erozif üs, varsayılan 0.8) alanı motorda HİÇ okunmuyor — üs kodda sabit 0.8.

**Kaynak:** kaynak bulunamadı — 0.0002 ve 0.002 form varsayılanlarının hiçbir literatür/ölçüm dayanağı kodda ya da tooltip'te belirtilmemiş.

**Sayısal etki:** ÖLÇÜLDÜ (APCP, UI varsayılan yükü): motorun k'sı 0.0136 yerine 0.0002 oluyor (68 kat küçük). G=2000 kg/m²s, D_p/D_ç=0.3'te erozif çarpan 1.0602 (tablo) yerine 1.0009 (UI) — yani erozif yanma varsayılan koşuda fiilen KAPALI. σ_p 0.0042 yerine 0.002 → varsayılan ΔT=4.85 K'de yanma hızı düzeltmesi %2.0 yerine %0.97.

### [ ] F066 — `solid_rocket_engine.py::_apply_overrides + burn_rate (sıcaklık hassasiyeti kapsamı: σ_p iki farklı formda, π_K hiç yok)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
self.a = self.a * np.exp(self.burn_rate_temp_coeff * (m - self.temp_ref))   [üstel]   VE   temp_correction = 1.0 + self.burn_rate_temp_coeff * (temperature - self.temp_ref)   [lineer]
```

**Olması gereken:** σ_p MODELLENMİŞ ve referans sıcaklık tek noktaya (self.temp_ref) sabitlenmiş — çifte sayım YOK (calculate_thrust_curve'de current_temp = temp_ref ile başladığı için lineer terim 1.0 kalır). Ancak aynı fiziksel duyarlılık iki farklı fonksiyonel formla uygulanıyor; birinci mertebede eşdeğer olsalar da büyük ΔT'de ayrışırlar. π_K = (∂ln Pc/∂T)_Kn = σ_p/(1-n) ise HİÇ modellenmemiş: sıcak-gün/soğuk-gün MEOP koşusu yok, dolayısıyla emniyet panelindeki maksimum işletme basıncı yalnız ortam sıcaklığındaki nominal koşudan geliyor.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 12 (σ_p ve π_K tanımları, π_K = σ_p/(1-n) bağıntısı); NASA SP-8064.

**Sayısal etki:** ÖLÇÜLDÜ: iki formun farkı ΔT=30 K, σ_p=0.0042'de exp(0.126)=1.1343 vs 1+0.126=1.1260 → %0.74. π_K eksikliği ise ölçülemedi (kodda karşılığı yok): APCP için σ_p=0.0042, n=0.35 ile π_K = 0.0065 /K, yani -20 °C'den +50 °C'ye 70 K'lik depolama bandı MEOP'u yaklaşık e^(0.0065·70) = 1.57 kat, yani %57 yükseltir. Bu, emniyet payı hesabına hiç girmiyor.

### [ ] F067 — `solid_rocket_engine.py::_calculate_erosive_effects`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
'erosive_enhancement_percent': min(25, mass_flux / 100 * 5)
```

**Olması gereken:** Bu satır motorun KENDİ erozif modeliyle hiç ilgisi olmayan uydurma bir doğrudur. Aynı sayfada raporlanan değer, burn_rate() içinde fiilen uygulanan 1 + k·((G-100)/400)^0.8·(D_p/D_ç)^-0.2 çarpanından okunmalıdır. Ayrıca 'port_diameter_effect': 'Moderate' hiçbir hesaba dayanmayan sabit metindir.

**Kaynak:** kaynak bulunamadı (ne kodda atıf var ne literatürde böyle bir lineer form)

**Sayısal etki:** ÖLÇÜLDÜ: G=1000 kg/m²s'de bu fonksiyon '%25 erozif artış' (50'den kırpılmış) raporluyor; çözücünün fiilen kullandığı artış aynı koşulda +3.31% (yakıt tablosu k=0.0136 ile) ve +0.09% (UI varsayılanı k=0.0002 ile). Yani kullanıcıya gösterilen sayı, hesaba giren fizikten 7.5 ile 275 kat büyük. G=500'ün üzerindeki her koşuda 25 tavanına yapışır (sabit sayı).

### [ ] F068 — `solid_rocket_engine.py::_thrust_coefficient (sabit geometrili nozulda anlık optimum genişleme varsayımı)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
Pe_Pc = p_amb / P_c_bar;  CF_ideal = sqrt(2γ²/(γ-1) · (2/(γ+1))^((γ+1)/(γ-1)) · (1 - Pe_Pc^((γ-1)/γ)))
```

**Olması gereken:** Bu, Pe = Pa (optimum genişleme) varsayan Sutton Denk. 3-30 özel hâlidir ve her zaman ULAŞILABİLİR EN BÜYÜK CF'i verir. Motorun nozulu ise sabit geometrilidir (ε = A_e/A_t sabit); Pc yanma boyunca değişince nozul tasarım-dışına düşer. Doğrusu: ε'dan Pe/Pc'yi izentropik çözüp CF = λ·CF_momentum + ε·(Pe - Pa)/Pc kullanmak (bu doğru form zaten transient_ballistics._thrust_coefficient'te var). Ayrıca aşırı genişlemede akış ayrılması kontrolü (Summerfield: Pe ≳ 0.4·Pa) hiç yok.

**Kaynak:** Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Denk. 3-30/3-31 (CF'in basınç-itki terimi); ayrılma ölçütü için Summerfield kriteri, Sutton Böl. 3 ve 5.

**Sayısal etki:** ÖLÇÜLDÜ (BATES, APCP, Pc tasarım 40 bar, sabit ε=5.93): koşu boyunca Pc 40→7.8 bar düşüyor; koddaki anlık-optimum CF, aynı basınçta gerçek sabit-ε nozulun CF'ini yanma kuyruğunda +33.6%'ya kadar aşıyor. Toplam impulsa etkisi +1.53% (kuyruk itkisi küçük olduğundan). Pc=7.8 bar'da Pe = 0.16 bar, yani Pe/Pa = 0.16 → gerçek nozul çoktan ayrılmış olurdu; kod bunu hiç uyarmıyor. Sabit basınçlı end-burner'da sapma 0.00%.

### [ ] F069 — `solid_rocket_engine.py::burn_rate (100 mm/s sessiz kırpma)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
max_rate = 0.1  # 100 mm/s maximum physical limit\n        return min(corrected_rate, max_rate)
```

**Olması gereken:** Kırpma yapılacaksa kullanıcıya UYARI üretilmeli (_w('warn.solid...')). app.py burn_rate_a'yı 0.1'e kadar KABUL ediyor, yani sınır meşru girdiyle aşılabiliyor ve kullanıcı girdiği katsayının sessizce yok sayıldığını hiçbir yerde görmüyor. Ayrıca 100 mm/s 'fiziksel sınır' iddiası kaynaksızdır; katalize edilmiş kompozit ve çift-tabanlı yakıtlarda daha yüksek hızlar yayımlanmıştır.

**Kaynak:** kaynak bulunamadı (kodda atıf yok)

**Sayısal etki:** ÖLÇÜLDÜ: a=0.05 (app.py doğrulamasında geçerli girdi), n=0.35, Pc=40 bar → ham r = 182 mm/s, burn_rate() 100 mm/s döndürüyor (-45%) ve design_warnings BOŞ kalıyor. Boğaz da kırpılmış hızla boyutlandırıldığı için sonuç 'tutarlı' görünüyor; kullanıcı 1.8 kat yanlış bir yanma hızıyla motor tasarladığını fark edemiyor.

### [ ] F070 — `solid_rocket_engine.py::burn_rate (erozif çarpanın formu, eşiği ve büyüklüğü)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
reynolds_factor = ((self.mass_flux - 100.0) / 400.0) ** 0.8;  geom_factor = max(port_diameter_ratio, 0.05) ** -0.2;  erosive_factor = 1.0 + k * reynolds_factor * geom_factor
```

**Olması gereken:** Üç ayrı sorun: (1) Lenoir-Robillard'ın D^-0.2 terimi BOYUTLU port çapıdır (fiziksel uzunluk); kod BOYUTSUZ D_port/D_oda oranı kullanıyor, dolayısıyla model ölçek-değişmezdir — 20 mm portlu bir amatör motorla 2 m portlu bir booster aynı geometrik çarpanı alır, oysa erozif yanma tam da küçük portta baskındır (mutlak ölçek iki dekat içinde 2.5 kat fark yaratır). (2) Eşik 100 kg/m²s, klasik Green/Summerfield erozif başlangıç eşiğinin (≈0.6 lbm/in²s ≈ 420 kg/m²s) 4 katı altındadır. (3) Çarpan toplamsal L-R terimi yerine taban hıza ÇARPILIYOR ve üfleme/sönümleme terimi exp(-β·ρp·r/G) tamamen düşmüş.

**Kaynak:** Lenoir & Robillard (1957), 'A Mathematical Method to Predict the Effects of Erosive Burning'; Sutton & Biblarz 9. baskı Böl. 12. Kodun atfı dürüst ('L-R indirgenmiş vekili') ama k katsayılarının kendisi için kaynak bulunamadı — v2.4.5 commit'i katsayıları 'x0.58, orta-yanma eşdeğerliği' ile ölçeklemiş, dış kaynak yok.

**Sayısal etki:** ÖLÇÜLDÜ (APCP, tablo k=0.0136): G=500→+1.7%, G=1000→+3.3%, G=2000→+6.0%, G=4000→+10.7% (D_p/D_ç=0.3). Yayımlanmış erozif yanma verisinde G≈1000-2000 kg/m²s'de r/r0 tipik olarak 1.2-2.0 aralığındadır — model bu rejimde büyüklüğü yaklaşık 5-10 kat DÜŞÜK tahmin ediyor. Pratik sonuç: SOLID_DESIGN_POINT'in kendi uyarı eşiğinde (1400 kg/m²s) model yalnız +4.6% veriyor, yani ateşleme basınç tepesi sistematik olarak eksik tahmin ediliyor.

### [ ] F071 — `solid_rocket_engine.py::calculate_thrust_curve (boğaz erozyonu hiç yok)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
A_t = m_dot_design * self.c_star / (self.P_c * 1e5)  # m^2, SABİT   +   docstring: 'yanma boyunca SABİT tutulur (gerçek motorda boğaz rijittir)'
```

**Olması gereken:** Grafit/fenolik boğaz rijit DEĞİLDİR; difüzyon-kontrollü oksidasyonla geriler. Projenin kendi hibrit modülünde çalışan model zaten var: transient_ballistics.ThroatErosionModel (ṙ = a_ref·(Pc/70 bar)^0.8, grafit a_ref = 0.05-0.15 mm/s). Katı motor çözücüsü her adımda d_t'yi büyütmeli. Ek olarak UI'daki 'erosion_factor' (varsayılan 0.001) alanı backend'e gidiyor ama hiçbir yerde OKUNMUYOR — kullanıcı boğaz erozyonu girip hiçbir sayının değişmediğini göremiyor.

**Kaynak:** Thakre & Yang, 'Chemical Erosion of Graphite and Refractory Metal Nozzles in Solid-Propellant Rocket Motors', J. Propulsion and Power 24(4), 2008; Bartz 1957 (h_g ∝ Pc^0.8 ölçeklemesi); Geisler AIAA grafit bandı 0.05-0.25 mm/s. (Depodaki transient_ballistics.py bu kaynakları zaten künyeliyor.)

**Sayısal etki:** ÖLÇÜLDÜ (grafit a_ref=0.15 mm/s, Pc=40 bar → ṙ=0.0937 mm/s): kısa BATES (t_b=2.19 s, d_t=47.9 mm) → ΔA_t/A_t = +1.8%, yanma sonu Pc -2.6%, itki -0.9% → İHMAL EDİLEBİLİR. Uzun end-burner (t_b=27.5 s, d_t=11.5 mm) → d_t 11.5→16.7 mm, ΔA_t/A_t = +113%, yanma sonu Pc -69%, itki -34%. Yani hata motor sınıfına göre <1% ile ~%35 arasında; küçük boğazlı/uzun yanmalı motorlarda ciddi.

### [ ] F072 — `structural_analysis.py::_analyze_fasteners`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
total_force = P*pi*(D/2)^2 ; force_per_bolt = total_force*bolt_safety_factor/num_bolts (bolt_safety_factor=4.0) ; required_A_t = force_per_bolt/400e6
```

**Olması gereken:** Uc sorun: (1) ETIKET/BIRIM YANILTICISI — 'force_per_bolt' adiyla ve kN birimiyle donen sayi gercek civata basina yukun 4 KATI (tasarim yuku). Bir mühendis bu degeri gercek yuk sanip boyutlandirirsa 4x hata yapar; alan adi 'design_force_per_bolt_N' olmali ve gercek yuk ayrica verilmeli. (2) ON-YUK FIZIGI YOK — on-yuklu bir baglantida civata yuku F_i + C*P'dir, 4*P/n degil; asil kritik kriter olan AYRILMA (separation, F_i/(P(1-C))) hic kontrol edilmiyor. Ayni depoda dogru model bolted_joint.py'de mevcut; bu fonksiyon onu cagirmali (parametre tutarliligi kurali). (3) KAYNAKSIZ SABITLER — bolt_safety_factor=4.0 ve bolt_allowable_stress=400 MPa icin atif yok; 400 MPa sinif 8.8'in S_p=580 MPa'sinin %69'u, yani 4.0 ile birlikte S_p'ye gore etkin 5.8 kat marj yigiliyor.

**Kaynak:** Shigley's Mechanical Engineering Design 10th ed. Ch.8 Eq. 8-24...8-30 (on-yuklu baglanti); A_t/A_nom ~ 0.75 orani ISO 898-1 (kodda DOGRU uygulanmis). 4.0 ve 400 MPa icin kaynak bulunamadi.

**Sayısal etki:** OLCULDU. P_design=90 bar, D=150 mm: total_force=159.0 kN dogru; ancak force_per_bolt=79.52 kN raporlaniyor, gercek civata basina dis yuk 159.0/8 = 19.88 kN (4.00x sisirilmis etiket). Ayni yuk bolted_joint.py ile cozulurse (8xM10 8.8) n_proof ve n_0 birbirinden bagimsiz kriterler olarak cikar; mevcut fonksiyon M20 oneriyor, bolted_joint on-yuk/ayrilma tabaninda farkli sonuc verebilir — iki modul ayni fizik icin iki farkli cevap uretiyor.

### [ ] F073 — `structural_analysis.py::_analyze_safety_factors`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
sf_candidates = {chamber_hoop: yield/sigma, chamber_von_mises: yield/sigma, nozzle: yield/sigma, end_cap: allowable/sigma} ; min_safety_factor = min(...)
```

**Olması gereken:** min() alinan dort SF'den ucu AKMA dayanimina (yield_for_design/sigma), biri (end_cap) IZIN VERILEN GERILMEYE (allowable = yield/safety_factor) gore tanimli. Tanim gereği end_cap SF'si digerlerinden safety_factor (=4.0) kat daha kucuk cikar; bu yuzden neredeyse her zaman min()'i o kazanir. Ayni sepette karsilastirilan tum SF'ler AYNI referans dayanima (tercihen derate edilmis akma) gore normalize edilmeli; farkli referans isteniyorsa 'margin of safety' (MS = SF/SF_hedef - 1) gibi boyutsuz ortak olcu kullanilmali.

**Kaynak:** Yontem hatasi; ortak SF tanimi icin NASA-STD-5001 / AIAA S-080A margin-of-safety pratigi.

**Sayısal etki:** OLCULDU. Pc=50 bar, steel_4130, D=150: chamber_hoop=4.205, chamber_von_mises=4.306, nozzle=4.000, end_cap=3.252 -> min=3.252 (end_cap yonetiyor). end_cap ayni yield tabaniyla tanimlansaydi 4*3.252=13.0 olurdu ve min 4.000'e (nozzle) kayardi. Yani nihai 'minimum_safety_factor' 4.0 kat farkli bir tanimdan geliyor.

### [ ] F074 — `structural_analysis.py::_analyze_safety_factors`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
T_wall = wall_temperature_K (yoneten senaryonun derating sicakligi) ; thermal_margin_ratio = T_wall/T_service
```

**Olması gereken:** 'cooled_gradient' senaryosu yonettiginde wall_temperature_K = 0.5*(T_ic + T_dis), yani ORTALAMA cidar sicakligi. Servis sicakligi asimi ise IC (sicak) yuzde olur; oran T_ic/T_service ile degerlendirilmeli. Ayni sekilde _derate_strength'in dondurdugu 'exceeds_max_service_temp' bayragi da ortalama sicaklikta hesaplandigi icin sicak yuz limiti astiginda False kaliyor. Dayanim derating'i icin ortalama makul (kesit ortalamasi tasima kapasitesini belirler) ama SERVIS SINIRI / yumusama / surunme kontrolu TEPE sicaklikta yapilmali — iki farkli sicaklik, iki farkli amac.

**Kaynak:** Yontem hatasi. Malzeme servis siniri tanimi: MMPDS / malzeme ureticisi kisa-sureli maruziyet sinirlari (tepe metal sicakligina uygulanir).

**Sayısal etki:** OLCULDU. wall_temperature_hot=860 K, cold=560 K, steel_4130 (max_service_temp=811 K): kod T_wall=710 K, thermal_margin_ratio=0.8755 ve exceeds_max_service_temp=False raporluyor. Tepe cidar tabanli olsaydi ratio = 860/811 = 1.0604 (>1 -> kesin UNSAFE) ve exceeds=True olurdu. Ikinci ornek (hot=790, cold=740): kod 0.9433, tepe tabanli 0.9741. Sinir bandi 0.85/1.00 esikleri civarinda status yanlis siniflanabiliyor.

### [ ] F075 — `structural_analysis.py::_check_buckling`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
sigma_cl = E/sqrt(3(1-nu^2))*(t/r) ; gamma = 1-0.901*(1-exp(-phi)), phi=(1/16)*sqrt(r/t) ; sigma_comp = F/(2*pi*r*t) ; net = max(sigma_comp - p_design*r/(2t), 0) ; p_cr_ext = E/(4(1-nu^2))*(t/r)^3
```

**Olması gereken:** TEYIT: 2026-07-16 'burkulma basma-yuku' duzeltmesi FORMUL OLARAK DOGRU. sigma_cl, gamma/phi knockdown ve p_cr_ext denklemleri NASA SP-8007 (1968) ile birebir uyusuyor; eski hatanin (ic basinc boylamsal CEKME gerilmesini burkulma yuku sanma) gercekten giderildigini ve yerine F/(2*pi*r*t) gercek basmanin kondugunu dogruladim. ANCAK uc zarf sorunu var: (1) URETIMDE OLU KOD — hicbir cagirici 'thrust' anahtarini gecmiyor (hybrid_rocket_engine.py struct_input'ta yok; app.py /analyze_structural_safety'de yok), dolayisiyla axial_compression_force her zaman 0 ve axial_buckling_safety_factor her zaman inf/'SAFE'. (2) STABILIZE KREDI SISIRILMIS — basinc cekme kredisi design_pressure (=1.5*Pc) ile hesaplaniyor; kredi cikarildigi icin YUKSEK basinc kullanmak NET BASMAYI AZALTIR, yani konservatif degil. Kredi MEOP (veya alt sinir basinci) ile alinmali. (3) YANLIS YUK DURUMU — burkulma gercekte BASINCSIZ durumda (nakliye, montaj on-yuku, ates oncesi/kapanis, ucus atalet yuku) kritiktir; kod yalnizca basincli durumu bakiyor, basincsiz durum hic degerlendirilmiyor. Ayrica 'length' argumani alinip HIC KULLANILMIYOR — dis basinc formulu uzun-silindir varsayimi, L/r kontrolu yok (konservatif yonde ama beyansiz).

**Kaynak:** NASA SP-8007 'Buckling of Thin-Walled Circular Cylinders' (revised 1968), NTRS 19680026348 — atif DOGRU, denklemler kaynakla uyusuyor.

**Sayısal etki:** OLCULDU. Pc=50 bar, D=150 mm, t=10.96 mm: thrust HIC verilmezse applied_axial_stress = 0.0, SF = inf, status 'SAFE'. thrust=50000 N verilse bile sigma_comp = 50000/(2*pi*0.075*0.01096) = 9.68 MPa < basinc kredisi 25.75 MPa -> net = 0.0, SF yine inf. Kredi MEOP (50 bar) ile alinsaydi 17.16 MPa olurdu, hala net=0 — ama t/r kucuk ve F buyuk motorlarda fark isaret degistirir. Sonuc: burkulma kontrolu pratikte hicbir motorda tetiklenmiyor (uretim yolunda %100 inf).

### [x] F076 — `structural_analysis.py::_estimate_wall_delta_T`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
T_cap = max_service_temp * WALL_TEMP_SERVICE_FRACTION (=0.9) ; T_inner = min(T_chamber, T_cap) ; t_wall = motor_data.get('wall_thickness', 0.005)
```

**Olması gereken:** Dis yuzey enerji dengesi (k/t*(T_ic-T_dis) = h*(T_dis-T_amb) + eps*sigma*(T_dis^4-T_amb^4)) FIZIKSEL OLARAK DOGRU ve sabit-nokta cozumu de dogru; sogutmasiz ince metal cidarda gradyanin ~2 K oldugu tespiti dogru. ANCAK T_inner'i belirleyen 0.9 katsayisi tamamen kalibrasyonsuz bir yer tutucu ve TUM derating'i (dolayisiyla gerekli kalinligi) o belirliyor. Dogrusu: cidar ic yuzey sicakligi da ayni enerji dengesinden cozulmeli (q_gaz_tarafi = h_g*(T_aw - T_ic) ile eslenerek) — yani _estimate_wall_delta_T gaz-tarafi isi tasinim katsayisini (Bartz) girdi almali, ya da bu yol tamamen kapatilip cidar sicakligi ZORUNLU girdi yapilmali. Ikinci sorun: t_wall varsayilani 5 mm sabit; hicbir cagirici bu anahtari gecmiyor ve boyutlandirilan gercek kalinlik (ornekte 10.96 mm) kullanilmiyor -> ic tutarsizlik.

**Kaynak:** Enerji dengesinin kendisi standart (Incropera & DeWitt, yuzey enerji dengesi). 0.9 katsayisi icin kaynak bulunamadi — kodun kendi yorumu da 'tahmin' oldugunu beyan ediyor.

**Sayısal etki:** OLCULDU. steel_4130 (max_service_temp=811 K), chamber_temperature=3200 K: T_inner = 0.9*811 = 729.9 K, retention = 0.5373, yield_for_design = 247.2 MPa. Katsayi 0.8 olsaydi T=648.8 K -> retention ~0.697 (yield 320.6 MPa), 1.0 olsaydi T=811 K -> retention ~0.373. Yani tek bir kaynaksiz sayi gerekli cidar kalinligini 1.4x-1.9x bandinda oynatiyor. Gradyan tahmini ise dogru: 5 mm celik icin dT = 1.95 K (docstring'in ~2 K iddiasiyla uyumlu).

### [ ] F077 — `tank_blowdown.py::N2OTankBlowdown._vapor_step`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
ratio = max(self.m_v/self._vapor_m0, 1e-6);  P = P0*ratio**1.27;  T = T0*ratio**0.27
```

**Olması gereken:** Adyabatik ideal gaz bağıntılarının kendisi DOĞRU (sabit V'de P/P0=(m/m0)^gamma, T/T0=(m/m0)^(gamma-1) — türetim doğru). Sorun: hiçbir alt sınır yok. m_v her adımda en fazla %80 çekildiği için ratio geometrik olarak 1e-6 tabanına iniyor ve model N2O'yu üçlü noktasının (182.33 K) ve her türlü fiziksel basıncın çok altına götürüyor. Buhar fazına ya bir T/P tabanı (ör. üçlü nokta veya 240 K bant sınırı) + uyarı konmalı, ya da sıvı bitince simülasyon 'burnout' ile sonlandırılmalı.

**Kaynak:** N2O üçlü noktası 182.33 K / 87.9 kPa (NIST WebBook). gamma=1.27 seçimi doğrulandı: CoolProp N2O ideal gaz gamma(300 K, 1 bar)=1.279.

**Sayısal etki:** ÖLÇÜLDÜ: from_oxidizer_mass(16.5 kg, 293.15 K), mdot=1.2 kg/s, 14 s simülasyon -> sıvı t=12.46 s'de bitiyor (P=31.7 bar, T=273.7 K, bunlar doğru), sonra 1.5 s'de T_son=159.6 K ve P_son=2.50 bar. T_init=253 K senaryosunda T_min=5.79 K ve P_min=3e-7 bar — fiziksel olarak imkânsız değerler, uyarısız. P(t)/T(t) zaman serisi kullanıcıya çiziliyor.

### [ ] F078 — `thermal_protection.py::heat_sink_transient`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
T_profile_K / T_max_K erime noktası kontrolü olmadan raporlanıyor; limit olarak yalnız mat['max_service_temp'] kullanılıyor
```

**Olması gereken:** Sabit özellikli iletim modeli erime/faz değişimi içermediğinden, T erime noktasını aştığı anda profil fiziksel anlamını yitirir. Sonuçta erime noktası kıyası ve açık bir 'cidar eridi, model geçersiz' bayrağı bulunmalı (mevcut exceeds_limit/time_to_limit_s yalnız yapısal servis sınırını gösteriyor).

**Kaynak:** Kaynak formül hatası değil; Sutton & Biblarz Böl. 8.4 heat-sink yönteminin varsayım zarfı (kısa yanma, cidar erime altında kalır).

**Sayısal etki:** ÖLÇTÜM: 5 mm çelik, h_g=8000 W/m^2K, Tr=3300 K, 5 s -> T_inner = 2889 K, T_outer = 2716 K raporlanıyor. Çeliğin erime noktası 1773 K; yani model erimiş çeliğin 1100 K üstünde bir sıcaklık profili çiziyor. exceeds_limit=True ve time_to_limit_s=0.086 s doğru şekilde bildiriliyor (kullanıcı tamamen kör değil), ama T_profile_K/T_max_K grafik olarak anlamsız. Ayrıca bu modül 'max_service_temp'=811 K kullanırken heat_transfer_analysis aynı çelik için 'max_service_temperature'=2000 K kullanıyor — iki panel arasında 2.5x sınır tutarsızlığı.

### [ ] F079 — `thermal_protection.py::radiation_equilibrium`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
h_g*(T_recovery - T_w) = eps*sigma*T_w^4
```

**Olması gereken:** Denge denkleminin kendisi doğru (Sutton & Biblarz Böl. 8.6), ancak görüş faktörü 1 ve ~0 K çevre varsayımı iki fiziksel terimi ihmal ediyor: (a) nozul uzantısının iç yüzeyi kendisini görür (F < 1), (b) gelen gaz ışınımı (Leckner q_rad) hesaba katılmıyor. Her iki ihmal de T_w'yi EKSİK tahmin ettirir — güvensiz yön, çünkü bu değer doğrudan C-103 (1640 K) / C-C (1920 K) malzeme seçim kararını veriyor.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 8.6 (radyasyon soğutmalı uzantı enerji dengesi). Görüş faktörü ve gaz ışınımı ihmalleri model notunda dürüstçe beyan edilmiş.

**Sayısal etki:** Bisection çözümünü doğruladım: h=500, Tr=2800 -> T_w=1835.2 K, artık f(T_w) = -1.3e-5 (sayısal olarak tam); h=1500, Tr=3000 -> T_w=2260.2 K. C-103 limiti 1640 K ile karşılaştırma doğru çalışıyor (within_limit=False). İhmal edilen terimlerin büyüklüğünü ÖLÇEMEDİM (görüş faktörü nozul yarım açısına bağlı, modülde geometri girdisi yok); mertebe tahmini: F=0.8 alınsa T_w ~ %5 (yaklaşık 90-110 K) yükselirdi — 1640 K sınırına yakın tasarımlarda kararı çevirebilecek büyüklükte.

### [ ] F080 — `trajectory_analysis.py::_calculate_descent_flight`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
if t > 2: cd_override = 1.4 ; area_current = 2.0  # m² parachute reference area
```

**Olması gereken:** Paraşüt alanı ARAÇTAN BAĞIMSIZ sabit kodlanmış (2.0 m²) ve kullanıcı girdisi yok; buna rağmen landing_velocity bir güvenlik metriği olarak raporlanıyor. Alan kullanıcı girdisi olmalı ya da metrik 'varsayımsal' etiketiyle sunulmalı. Ayrıca Cd=1.4 ancak referans alan İZDÜŞÜM alanı ise doğrudur (içi boş yarımküre Cd≈1.42, Hoerner); Knacke'nin tabloları NOMİNAL alan S0 tabanında Cd0≈0.62-0.80 verir — docstring'deki 'Knacke 1992 → hemisferik paraşüt Cd~1.4' atfı Knacke'nin kendi alan konvansiyonuyla uyuşmuyor. Hangi alan tanımının kullanıldığı kodda yazmıyor.

**Kaynak:** Knacke, 'Parachute Recovery Systems Design Manual' 1992 (Cd0, nominal alan tabanlı); Hoerner 1965 (izdüşüm alanı tabanlı içi boş yarımküre Cd≈1.42).

**Sayısal etki:** ÖLÇÜLDÜ: 20 kg kuru araç için raporlanan iniş hızı 10.70 m/s. Alan kullanıcı aracına göre 0.5 m² olsaydı bu ~21 m/s, 5 m² olsaydı ~6.8 m/s olurdu — yani metrik tamamen sabit koda bağlı, ±2x aralıkta keyfi.

### [ ] F081 — `trajectory_analysis.py::_calculate_powered_flight`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
thrust_current = thrust  (irtifadan bağımsız sabit) — six_dof_trajectory.py::_thrust_at de aynı
```

**Olması gereken:** İtki ortam basıncına bağlıdır: F(h) = F_ref + (P_ref − P_amb(h))·A_e. Her iki uçuş modülü de deniz seviyesi itkisini tüm irtifalarda sabit kullanıyor; nozul çıkış alanı bilgisi hiç taşınmıyor (flight_vehicle.normalize şemasında A_e alanı da yok).

**Kaynak:** Sutton & Biblarz, 'Rocket Propulsion Elements' Böl.3 (itki denklemi F = ṁ·v_e + (p_e − p_a)·A_e).

**Sayısal etki:** TAHMİN (ölçemedim, A_e uçuş modeline hiç geçmiyor): F=3000 N, Pc=20 bar, Cf≈1.5 → A_t≈0.001 m², ε=4 → A_e≈0.004 m². 4 km irtifada ΔF ≈ (101325−61660)·0.004 ≈ 159 N ≈ %5.3. Yanma boyunca ortalama ~%2-3 ek impuls → apoje ~%3-5 EKSİK tahmin ediliyor (güvenli olmayan yön: gerçek uçuş daha yükseğe çıkar).

### [ ] F082 — `trajectory_analysis.py::_wind_vector`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
vx_wind = wind_speed * cos(wind_direction_rad)   # docstring: 'rüzgarın ESTİĞİ yön'
```

**Olması gereken:** Meteorolojik konvansiyonda rüzgâr yönü rüzgârın GELDİĞİ yöndür; vektör −V·(cos, sin) olmalı. Kardeş modül six_dof_trajectory.__init__ doğru konvansiyonu kullanıyor (self.wind = −V·[cos,sin,0], 'rüzgârın geldiği yön'). Aynı üründe aynı isimli girdi iki panelde TERS anlam taşıyor.

**Kaynak:** WMO / standart meteoroloji konvansiyonu (rüzgâr yönü = geldiği yön). McCoy 1999 balistik metinlerinde de aynı.

**Sayısal etki:** ÖLÇÜLDÜ (15 m/s rüzgâr, 85° atış): wind_direction=0 → menzil +6395.9 m; wind_direction=180 → −4134.5 m. Yani yalnızca konvansiyon işareti yüzünden iniş noktası ~10.5 km ötelenir. (Büyüklüğün kendisi fiziksel olarak doğru: paraşütle ~360 s iniş × 15 m/s ≈ 5.4 km her yöne.) İki panelin aynı girdi için zıt yön vermesi kullanıcıya çelişkili iniş noktası gösterir.

### [ ] F083 — `uncertainty.py::_lhs_unit + spearman_sensitivity`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
_qmc.LatinHypercube(d=d, seed=seed).random(n)  — optimization/dekorelasyon parametresi verilmiyor; ardından spearman_sensitivity ham |rho| ile sıralanıp raporlanıyor
```

**Olması gereken:** LHS yalnız MARJİNAL tabakalamayı garantiler; sütunlar arası örneklem korelasyonunu sıfırlamaz. Küçük n'de bu sahte korelasyon, duyarlılık tablosunu doğrudan kirletir: modele HİÇ girmeyen bir parametre, önemli bir parametreyle tesadüfen korele olduğu için sıfırdan belirgin biçimde farklı |rho| alır. Çözüm: scipy.stats.qmc.LatinHypercube(..., optimization='random-cd') veya Iman-Conover dekorelasyonu; asgari olarak duyarlılık listesine bir GÜRÜLTÜ TABANI (n'e bağlı) yazılmalı ve altındaki rho'lar 'ayırt edilemez' işaretlenmeli.

**Kaynak:** Iman & Conover, 'A distribution-free approach to inducing rank correlation among input variables', Communications in Statistics B11(3), 1982 (LHS sütunlarında istenmeyen korelasyonun giderilmesi). scipy.stats.qmc.LatinHypercube dokümantasyonu: optimization=None varsayılan, 'random-cd' korelasyon/tutarsızlığı azaltır.

**Sayısal etki:** ÖLÇÜLDÜ (hibrit modelinin gerçek boyutu d=6, 60 tohum): n=200 (FAST, VARSAYILAN seviye) -> sütunlar arası en büyük |r| ortalama 0.145, maksimum 0.246. n=1000 -> 0.063; n=3000 -> 0.037. Duyarlılık tablosuna etkisi ayrıca ölçüldü (y = 3*x0, x1..x4 modele hiç girmiyor, n=200, 200 tohum): modele girmeyen girdilerin aldığı en büyük |Spearman| ortalama 0.102, 95. yüzdelik 0.171, maksimum 0.213. Yani Fast modda tamamen alakasız bir parametre rutin olarak ~0.10-0.20 'duyarlılık' gösteriyor ve |rho| azalan sıralamada gerçek ama zayıf bir parametrenin ÜSTÜNE çıkabiliyor. Kullanıcı bu listeyi 'hangi parametre önemli' diye okuyor.

### [ ] F084 — `uncertainty.py::run_uncertainty (MC döngüsü, failed listesi)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
except Exception as exc: ... failed.append({'index': i, 'error': str(exc)}); continue   — ardından istatistik yalnız kept_rows üzerinde; uyarı yalnız len(failed) > FAILED_SAMPLE_WARN_THRESHOLD (=5) ise
```

**Olması gereken:** Patlayan örnekler girdi uzayında rastgele DEĞİL, tipik olarak tek bir kuyrukta kümelenir (yakınsamama, fiziksel olmayan geometri). Bunları atmak dağılımı tek yönlü kırpar: ortalama kayar, std ve kuyruk yüzdelikleri (P5/P95) sistematik olarak DARALIR. Rapor en azından (a) başarısız örneklerin hangi girdi bölgesinde olduğunu (girdi ortalaması vs başarılıların ortalaması), (b) düzeltilmiş/sınırlanmış bir kuyruk tahmini veya 'P95 alt sınırdır' notunu vermeli. Eşik (5) kaynaksız bir sihirli sayı; oran tabanlı (%1 gibi) ve HER başarısızlıkta görünür olmalı.

**Kaynak:** Kaynak bulunamadı (eşik 5 için). İlke: eksik/başarısız gözlem mekanizması sonuca bağlıysa (MNAR) tam-vaka analizi yanlıdır — Little & Rubin, 'Statistical Analysis with Missing Data', 3. baskı, Böl. 1-2.

**Sayısal etki:** ÖLÇÜLDÜ (yapay model y=100x, x~truncnorm(1, 0.15), yalnız ÜST kuyruk x>1.25 patlıyor, n=1000): 48/1000 (%4.8) başarısız. Raporlanan ortalama 98.62 (gerçek 100.00, yanlılık -%1.38); raporlanan std 13.28 (gerçek 15.00, -%11.5); raporlanan P95 119.59 (gerçek ~124.67, -%4.1); cv_percent %13.47 (gerçek %15). Yani belirsizlik bandı sistematik olarak DAR gösteriliyor — güvenlik açısından yanlış yön. Eşik altı senaryo (2 başarısız/1000): 'warning' alanı HİÇ oluşmuyor, P95 sapması -%0.29 (bu düzeyde zararsız ama görünmez). Ayrıca sonuçtaki 'n_samples' alanı tam n'i (1000) bildiriyor, istatistik ise 952 örnek üzerinde — tüketen taraf yanlış paydayla çalışabilir.

### [x] F085 — `uncertainty.py::run_uncertainty + _stats_block`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
'p5': np.percentile(arr,5), 'p95': np.percentile(arr,95), 'mean', 'std' — hiçbirinin örnekleme hatası (SE) veya yakınsama tanısı raporlanmıyor; n yalnız LEVEL_BUDGETS'ten sabit geliyor
```

**Olması gereken:** İstatistiklerin FORMÜLLERİ doğru (mean, std, yüzdelikler, cv, Jensen boşluğu 'mean_shift_percent' — hepsi standart ve doğru tanımlı). Eksik olan MC yakınsama kanıtı: koşan ortalama/yüzdelik izi, ortalama için standart hata, yüzdelikler için bootstrap güven aralığı veya çoklu tohumla tekrarlanabilirlik kontrolü yok. Sabit bütçe (200/1000/3000) yakınsama garantisi değildir. Asgari düzeltme: her çıktı için mean_se ve p5/p95 için bootstrap CI eklenmeli, ya da rapor 'bu değerler ±X% MC gürültüsü taşır' demeli.

**Kaynak:** MC yakınsama tanılaması standart pratiği: Robert & Casella, 'Monte Carlo Statistical Methods', 2. baskı, Springer 2004, Böl. 12 (yakınsama izleme). Yüzdelik SE'si için: Serfling, 'Approximation Theorems of Mathematical Statistics', 1980, örneklem yüzdeliklerinin asimptotik varyansı p(1-p)/(n f(x_p)^2).

**Sayısal etki:** ÖLÇÜLDÜ (2000 tekrar, CV=%10 tipik çıktı dağılımı): n=200 (FAST = VARSAYILAN) -> ortalama SE %0.71, P5 SE %1.46, P95 SE %1.41. n=1000 -> %0.32 / %0.66 / %0.66. n=3000 -> %0.18 / %0.39 / %0.38. Yani Fast modda kullanıcıya tam ondalıkla sunulan P95 değeri ±%1.4 MC gürültüsü taşıyor; iki koşu (farklı tohum) arasında P95 %3'e kadar oynayabilir ve arayüzde bunu gösteren hiçbir şey yok. Not: LHS ORTALAMANIN SE'sini düz MC'ye göre düşürür, kuyruk yüzdeliklerinde kazanç çok daha azdır — yukarıdaki rakamlar düz MC üst sınırıdır.


## DUSUK

### [x] F086 — `bolted_joint.py::preload`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
F_p = A_t*S_p ; F_i = 0.75*F_p (yeniden kullanilabilir) / 0.90*F_p (kalici) ; T = K*F_i*d ; k_b = A_t*E_b/l ; k_m = E_m*d*A*exp(B*d/l) ; C = k_b/(k_b+k_m) ; F_b = F_i + C*P ; n_0 = F_i/(P*(1-C))
```

**Kaynak:** Shigley's Mechanical Engineering Design 10th ed. Sec. 8-7 Eq. (8-31)/(8-32) [on-yuk], Eq. (8-27) [tork], Eq. (8-23) + Table 8-8 [Wileman k_m], Eq. (8-24)...(8-30) [yuk paylasimi ve emniyetler]; Wileman, Choudury & Green (1991) J. Mech. Design 113; ISO 898-1:2013 Table 3 + Table A.1; ISO 3506-1 — TUM atiflar dogrulandi, denklemler ve sabitler kaynaklarla birebir.

**Sayısal etki:** OLCULDU, HEPSI GECTI. (a) Tork: 8.8 kuru, 0.75*S_p on-yuk -> M6 10.49 / M8 25.47 / M10 50.46 / M12 88.01 / M16 218.5 / M20 441.0 N*m; yayimlanmis ureticinin 8.8 tork tablosuna gore sapma +0.9% ... +2.3% (kabul). (b) Wileman sabitleri: celik A=0.78715 B=0.62873, aluminyum A=0.79670 B=0.63816 — Shigley Table 8-8 ile birebir. (c) M10/l=30mm/celik uye: kod k_b=3.8667e8, k_m=1.9414e9, C=0.1661; bagimsiz el hesabim ayni 4 haneye kadar; C degeri Shigley'in tipik 0.15-0.35 bandinda. (d) SF denklemleri: n_p=1.213, n_L=3.358, n_0=2.006 — el hesabimla birebir. (e) ISO 898-1 gerilme alanlari (M4 8.78 ... M24 353 mm^2) ve sinif dayanimlari (8.8 d<=16: 580/640/800; 10.9: 830/940/1040; 12.9: 970/1100/1220 MPa) standart degerlerle birebir. Birim yonetimi (mm^2 -> m^2, mm -> m, bar -> Pa) her yerde dogru. Bu modul denetlenen uc dosyanin ACIK ARA en saglami.

### [x] F087 — `burn_rate_db.py::BURN_RATE_LAWS + resolve_engine_coeffs`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
r[mm/s] = a·P[MPa]^n (5 rejim);  a_engine = a_db / (1000 · 10^n),  n değişmez
```

**Kaynak:** R. Nakka, 'Solid Propellant Burn Rate' (Experimental Rocketry, 1999/2001), KNDX/KNSB rejim fitleri.

**Sayısal etki:** DOĞRULANDI, sapma yok. KNDX 5 rejim (8.88/0.619, 7.55/-0.009, 3.84/0.688, 17.2/-0.148, 4.78/0.442) ve KNSB 5 rejim (10.71/0.625, 8.763/-0.314, 7.852/-0.013, 3.907/0.535, 9.653/0.064) Nakka'nın yayımlanmış tablolarıyla BİREBİR aynı; basınç sınırları da aynı. Birim dönüşümü boyut analiziyle türetildi (r[m/s] = a_db/1000·(P_bar/10)^n = a_db/(1000·10^n)·P_bar^n) ve sayısal olarak bit-tam doğrulandı: KNDX 10/30/50/70/100 bar'da db yolu ile motor-konvansiyonu yolu arasında fark ≤ 3.6e-15 mm/s. Fiziksel çapa da tutuyor: KNDX @ 70 bar = 12.90 mm/s (Nakka'nın yayımlanmış eğrisi ~13 mm/s @ 7 MPa).

### [x] F088 — `cea_bridge.py::_compute_rocketcea`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
c_star = get_Cstar(...)·0.3048; tc = get_Tcomb(...)·5/9; pc_psia = pc_bar·14.5037738; cp = get_Chamber_Transport(...,frozen=1)[0]·4184
```

**Kaynak:** Birim tanımları NIST SP 811 (ft=0.3048 m tam, termokimyasal kalori=4.184 J tam, 1 bar=14.5037738 psi). RocketCEA v1.2.1 API sözleşmesi: get_Isp → vakum Isp, estimate_Ambient_Isp(Pamb) → ortam Isp'si, get_SpeciesMoleFractions → (molWt, {tür:[oda,...,çıkış]}) — kodun docstring'lerindeki atıflar doğru, uydurma yok.

**Sayısal etki:** ÖLÇÜLDÜ, ham RocketCEA'ya karşı BİREBİR: LH2/LOX Pc=206.4 bar MR=6.03 → köprü c*=2320.7 m/s, ham CEA 7614.0 ft/s×0.3048 = 2320.7 (sapma 0.00%); Tc 3603.7 K vs 6487.0 °R×5/9 = 3603.9 K (%0.006); Isp_vac(ε=69) 462.75 vs 462.76 s. cp: LOX/CH4 100 bar MR=3.6 → 2292.2 J/(kg·K), docstring'in iddia ettiği değerle uyumlu. Fiziksel akıl kontrolü: RS-25 yayımlanmış teslim c*≈2320 m/s, Isp_vac 452.3 s (ideal 462.8 → η≈0.977, beklenen bantta).

### [ ] F089 — `cea_bridge.py::_from_fallback`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
def _from_fallback(fallback, pc_bar, eps): ...  # eps parametresi gövdede HİÇ kullanılmıyor
```

**Olması gereken:** Fonksiyon genişleme oranını alıp yok sayıyor; statik tablo ε=200 çapasına demirli olduğundan hangi ε istenirse istensin ε=200 Isp'si dönüyor. Bu, 2026-07-22'de RocketCEA yolunda düzeltilen hatanın ta kendisi. En azından validity['note'] içine 'isp_vac_s ε=200 çapasıdır, istenen ε=... değil' yazılmalı, ya da parametre imzadan kaldırılmalı.

**Kaynak:** Yok — kodun kendi docstring'i tablonun 'Pc=100 bar çapası' olduğunu söylüyor ama ε çapasından söz etmiyor.

**Sayısal etki:** ÖLÇÜLDÜ (RocketCEA ile ε duyarlılığı): LH2/LOX Pc=206.4 MR=6.03 → ε=25:442.4 s, ε=69:462.8 s, ε=200:478.1 s. Tabloyu ε=69'luk bir motora uygulamak %3.3 aşırı-tahmin demek. ETKİ BUGÜN TELAFİ EDİLİYOR: liquid_rocket_engine.py::_apply_nozzle_off_design_once fallback yolunda CF oranıyla (isp_sl·CF(ε)/CF(ε_eşlenik) ve Isp_vac = Isp_sl + P_a·ε·c*/(P_c·C_D·g0)) ε düzeltmesini uyguluyor — bu iki bağıntıyı elle doğruladım, boyutça ve fizikçe DOĞRU. Yani bulgu latent.

### [ ] F090 — `cea_bridge.py::get_combustion_properties`

**Hüküm:** YANLIS_FORMUL · **Görünür:** hayır

**Koddaki denklem:**
```
amb_key = round(float(ambient_bar), _AMB_ROUND) if ambient_bar else None  →  _compute_rocketcea: amb_bar = ambient_bar if ambient_bar else STD_SEA_LEVEL_BAR
```

**Olması gereken:** `if ambient_bar` yerine `if ambient_bar is not None` olmalı. 0.0 bar (vakum) geçerli ve anlamlı bir girdidir; şu an falsy sayıldığı için sessizce 1.01325 bar'a (deniz seviyesi) düşüyor ve fonksiyon 'vakum Isp'si istedim' diyene deniz seviyesi Isp'si döndürüyor — hata da vermiyor.

**Kaynak:** Fizik hatası değil, sözleşme hatası; RocketCEA estimate_Ambient_Isp(Pamb) kullanımı doğru (Pamb psia'ya çevriliyor).

**Sayısal etki:** ÖLÇÜLDÜ (LH2/LOX, Pc=206.4 bar, MR=6.03, ε=69): ambient_bar=0.0 → isp_sl_s = 387.46 s; ambient_bar=0.001 → 462.68 s. Yani vakum talebi %16.3 düşük cevap alıyor. ŞU AN GİZLİ: tek çağıran liquid_rocket_engine.py::_resolve_combustion_reference ambient_bar=self.P_a geçiyor ve P_a sabit 1.01325 — dolayısıyla bugün kullanıcıya yansımıyor, ama tuzak duruyor.

### [x] F091 — `cea_bridge.py::get_combustion_properties`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
expansion_ratio → _compute_rocketcea(eps) → get_Isp(Pc, MR, eps) ; record_adapters.py::_predict_liquid → overrides['nozzle_expansion_ratio'] = eps_record
```

**Kaynak:** 2026-07-23 commit 8f3a87b ('Sıvı doğrulama: yayımlanmış genişleme oranı ve çevrim tipi kayıttan motora geçiriliyor').

**Sayısal etki:** DÜZELTME TEYİT EDİLDİ. Köprünün ε duyarlılığını ölçtüm (LH2/LOX Pc=206.4 MR=6.03): ε=25→442.41 s, ε=40→452.64, ε=69→462.75, ε=100→468.71, ε=200→478.10 s. Bu, liquid_rocket_engine.py::_resolve_combustion_reference yorumundaki 'RS-25 ε=69'da 462.8 s, ε=200'de 478.1 s' iddiasıyla BİREBİR aynı. record_adapters yayımlanmış ε'yi overrides['nozzle_expansion_ratio'] ile geçiriyor, motor onu expansion_ratio_input olarak alıp CEA'yı o ε'da çözüyor ve _apply_nozzle_off_design_once çift-sayımı açıkça engelliyor. Zincir doğru kurulmuş. TEK KALAN AÇIK: aynı ε disiplini _from_fallback yolunda yok (yukarıdaki ayrı bulgu).

### [x] F092 — `combustion_analysis.py::_calculate_frozen_shifting_isp`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
v_e = √(2·(h_0 − h_e));  shifting: gas.SP=(s_0,P_e)+equilibrate('SP');  frozen: gas.TPY=(T_0,P_c,Y_0) sonra gas.SP=(s_0,P_e) equilibrate YOK
```

**Kaynak:** Sutton & Biblarz 9. baskı Eq. 3-15b (enerji denklemi); NASA RP-1311 Part I lüle hız denklemi; NASA CEA'nın frozen/equilibrium ayrımıyla aynı fizik. Atıflar gerçek ve yerinde.

**Sayısal etki:** ÖLÇÜLDÜ: htpb/n2o O/F=6 Pc=20 bar → frozen 223.84 s, shifting 232.09 s (shifting > frozen, fiziksel olarak doğru sıra ve ~%3.7 fark tipik banttadır). Kod ayrıca isp_shift < isp_froz olursa None'a düşerek yakınsama bozukluğunu sessizce kabul etmiyor. calculate_altitude_performance'in sabit-geometri itki denklemini (F = mdot·v_e + (P_e−P_a)·A_e, A_e = mdot·R_e·T_e/(P_e·v_e), CF = F/(mdot·c*)) elle yeniden hesapladım: h=0'da kod 4544.0 N / 231.68 s, elle 4544.0 N / 231.68 s — birebir.

### [x] F093 — `combustion_analysis.py::_calculate_performance_parameters`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
c_star = √(R_c·T_c/γ) / (2/(γ+1))^((γ+1)/(2(γ−1))); v_throat = √(γ_t·R_t·T_t); v_exit = √(2γR_cT_c/(γ−1)·(1−(P_e/P_c)^((γ−1)/γ))); cf = v_exit/c_star; MW_mix = 1/Σ(Y_i/M_i)
```

**Kaynak:** Sutton & Biblarz 9. baskı Eq. 3-32 (c*), Eq. 3-10 (boğaz ses hızı, yerel γ ile — kod bunu doğru yapıyor), Eq. 3-15/3-16 (v_e), Eq. 3-30 (CF = v_e/c* eşlenik genleşmede). Kütle-kesri karışım MW'si için harmonik ortalama doğru form.

**Sayısal etki:** ÖLÇÜLDÜ, RocketCEA referansına karşı (Cantera/gri30 açık): htpb/n2o O/F=6 Pc=20 → Tc −0.44%, c* +0.39%; htpb/lox O/F=2 Pc=40 → Tc +0.21%, c* +1.74%; pe/n2o O/F=7 Pc=30 → Tc −2.42%, c* +0.62%; htpb/n2o O/F=3 Pc=20 → Tc −3.58%, c* −2.14%; htpb/n2o O/F=10 → +0.43% / +0.55%. Stokiyometri de doğrulandı: HTPB/N2O stok. O/F=8.964 (elle: 5.5·32/54 ÷ 0.3636 = 8.965). Tüm yakıt yanma denklemleri (paraffin, htpb, pe, pmma, pla, abs, Al) O atom dengesinden tek tek denetlendi — hepsi denk. H2O2 0.4704 ve hava 0.2314 katsayıları doğru.

### [x] F094 — `combustion_analysis.py::_calculate_reactant_enthalpy`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
ox_key == 'n2o' → hf_ox = 82.05 kJ/mol (propellant_specs['n2o'])
```

**Kaynak:** 82.05 kJ/mol, N2O'nun GAZ fazı, 298.15 K standart oluşum entalpisidir (NIST). Hibrit motorlar doymuş SIVI N2O besler (~20 °C); sıvı için değer buharlaşma entalpisi kadar düşüktür (~−16.5 kJ/mol → ≈65.5 kJ/mol). ANCAK RocketCEA'nın kendi N2O kartı da 298.15 K gaz değerini kullanır, dolayısıyla kodun CEA çapraz-doğrulaması kendi içinde tutarlıdır. Bilinçli/uyumlu bir sözleşme olarak DOĞRU kabul ediyorum, sadece 'sıvı N2O' varsayıldığı sanılmasın diye belgelenmeli.

**Sayısal etki:** Tahmini (ölçemedim, çünkü CEA referansı da aynı kartı kullanıyor → karşılaştırma farkı göstermez): 16.5 kJ/mol / 44 g/mol = 375 kJ/kg N2O; O/F=6'da karışım başına ~321 kJ/kg → ΔTc ≈ 321000/2000 ≈ +160 K (~%5), c* ~%2.4. Gerçek doymuş sıvıya kıyasla sistematik iyimserlik.

### [ ] F095 — `combustion_analysis.py::_calculate_thermodynamic_properties`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
'mass_averaged_mw': sum(30.0 for _ in properties.values()) / 3  # Simplified
```

**Olması gereken:** Gerçek istasyon MW'leri zaten aynı fonksiyonda hesaplanıyor (comp['molecular_weight']); ortalama onlardan alınmalı. Şu an sabit 30.0 döndürülüyor — hesaplanan değerle ilgisi yok, 'asla uydurma' ilkesine aykırı bir yer tutucu.

**Kaynak:** Kaynak yok, kod 'Simplified' diyor.

**Sayısal etki:** ÖLÇÜLDÜ: htpb/n2o O/F=6 Pc=20 bar → gerçek oda MW 25.52, throat/exit benzeri; raporlanan mass_averaged_mw = 30.0 (+17.6%). Bu alanı tüketen bir hesap bulamadım (yalnız JSON çıktısında duruyor), o yüzden türev hata üretmiyor.

### [x] F096 — `combustion_analysis.py::analyze_combustion`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
throat_temperature = T_c·2/(γ+1); throat_composition = _calculate_equilibrium_composition(elements, P_t, T_t, 'throat')  → equilibrate('TP')
```

**Kaynak:** P_c/P_t ve T_t/T_c bağıntıları Sutton & Biblarz 9. baskı Eq. 3-20/3-22 ile birebir DOĞRU. Kavramsal incelik: kayan-denge akışta boğaz durumu izentropik olarak (s sabit, equilibrate('SP')) çözülmeli; kod dondurulmuş-γ ile T_t'yi kestirip orada TP dengesi kuruyor. _calculate_frozen_shifting_isp zaten doğru SP yöntemini kullandığı için manşet Isp etkilenmiyor.

**Sayısal etki:** ÖLÇÜLDÜ (htpb/n2o O/F=6 Pc=20 bar): kodun ürettiği çıkış istasyonundan türeyen efektif ε = 3.74; aynı γ=1.16 ve P_c/P_e=20 için tam izentropik değer 3.79 → %1.3 sapma. Boğaz istasyonu için sapma benzer mertebede (<%2). c* oda değerlerinden hesaplandığı için c*'a hiç yansımıyor.

### [x] F097 — `correlation_runner.py::_basic_stats + _score_adapter_result (metrik tanımları)`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
error_pct = (predicted - measured)/measured*100 ; bias_pct = fmean(errors) ; rms_pct = sqrt(fmean(e^2)) ; median_ape_pct = median(|e|) ; mape_pct = fmean(|e|) ; measured==0 -> 'measured_zero' (skorlanmaz)
```

**Kaynak:** Standart tahmin doğruluğu tanımları: Hyndman & Koehler, 'Another look at measures of forecast accuracy', International Journal of Forecasting 22(4), 2006 (MAPE = ortalama|100(y-ŷ)/y|; MdAPE = medyan|...|). İşaretli bağıl hata (ölçüm paydada) ve bias tanımı da bu kaynakla uyumlu.

**Sayısal etki:** Sapma yok — beş tanımı da elle kontrol ettim, hepsi standart ve iç tutarlı. Sıfır ölçüme karşı 'measured_zero' koruması var (bölme hatası yok). İşaret sözleşmesi hem kodda hem to_markdown başlığında açıkça yazılı ('(predicted - measured)/measured*100'), bias görünür kalıyor. db_content_hash (test_id sıralı kanonik JSON + sha256) ve deterministic_view (zaman alanlarını soyma) da doğru kurulmuş; koşucu gerçekten saf fonksiyon.

### [x] F098 — `correlation_runner.py::_score_adapter_result (kapsam boşluğu: takma ad tablosu eksik)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
BASE_ALIASES: 'thrust_avg'->'thrust_mean' VAR; ama 'regression_rate_avg', 'chamber_pressure_avg', 'gox_avg' için takma ad YOK; 'c_star_efficiency' ve 'thrust_coefficient' DIMENSIONLESS_BASES'te değil
```

**Olması gereken:** Fizik hatası değil, kapsam ve tutarlılık boşluğu. 'thrust_avg' takma adla yakalanırken aynı '_avg' kalıbı basınç ve regresyon hızında yakalanmıyor; boyutsuz ölçümler (c* verimi, itki katsayısı) boyutsuz taban listesinde olmadığı için 'unknown_unit' olarak düşüyor. En kritiği c_star_efficiency: adaptörün kendi notu 'teorik c* kullanıldı, teslim c*'a karşı pozitif sapma beklenir' diyor — DB'de bu sapmayı ölçen 64 kayıt var ama okunmuyor.

**Kaynak:** Kaynak gerekmiyor (kod içi tutarlılık bulgusu). Referans: record_adapters.py::BASE_ALIASES ve DIMENSIONLESS_BASES tanımları.

**Sayısal etki:** ÖLÇÜLDÜ (209 kaydın measured anahtarları sayıldı): skorlanamayan/eşlenemeyen ölçüm anahtarları — of_ratio 129 (girdi olarak tüketiliyor, doğru), c_star_efficiency 64, regression_rate_avg 48, gox_* ~100, chamber_pressure_avg 25, thrust_coefficient 14. Karşılaştırma için ana istatistiğe giren toplam skorlanan giriş yalnız 191. Yani DB'nin ölçüm içeriğinin büyük kısmı doğrulamaya hiç girmiyor; 209 kaydın 107'si zaten 'insufficient_inputs' (%51). Doğruluk rakamları yanlış değil ama 'n=209 gerçek kayıt' ifadesi ile fiilen skorlanan kapsam arasında büyük fark var ve to_markdown bu farkı yalnız status_counts satırıyla gösteriyor.

### [x] F099 — `cycle_power_balance.py::ETA_TURBINE_CLOSED_DEFAULT ve ETA_TURBINE_OPEN_DEFAULT (NASA SP-8110 atfı)`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
ETA_TURBINE_OPEN_DEFAULT = 0.65 ; ETA_TURBINE_CLOSED_DEFAULT = 0.78
```

**Kaynak:** ATIF DOĞRULANDI — kaynak belge indirilip metni çıkarıldı. NASA SP-8110 'Liquid Rocket Engine Turbines' (Ocak 1974, NTRS 19740026132), belge s.15-17 (fig. 13-14 civarı), birebir: gaz jeneratörü ve tap-off çevrimlerindeki iki sıralı türbinler için 'efficiencies vary from 35 to 65 percent', hemen ardından 'Staged-combustion and expander-cycle turbines are capable of attaining efficiencies above 80 percent because the lower turbine system pressure ratios generally permit operation in a more efficient range of velocity ratio.' Kodun yorumundaki hem %35-65 bandı hem '>%80' ifadesi hem de sayfa/şekil referansı DOĞRU. SAHTE KAYNAK DEĞİL. Yalnız ikincil atıf (RS-25 HPFTP %81.1 / HPOTP %74.6, 'Boeing/Rocketdyne SSME Orientation 1998') DOĞRULANAMADI: kaynak PDF (large.stanford.edu) 3 denemede de yarım indi. Uydurma olduğuna dair bir kanıt YOK; kapalı çevrim varsayılanı 0.78, doğrulanmış SP-8110 '>%80' ifadesinin ALTINDA olduğu için bu ikincil atıf doğrulanamasa bile seçim muhafazakârdır.

**Sayısal etki:** Kapalı çevrim varsayılanının etkisi ÖLÇÜLDÜ (Raptor FFSC): eta_t=0.78 -> ox_disch 776.3 bar, Ppompa 73.87 MW; eta_t=0.85 -> 668.7 bar, 65.63 MW; eta_t=0.65 -> çözüm YOK. Yani sınıflandırmanın kendisi (0.65 yerine 0.78) kapalı çevrimlerin ÇÖZÜLEBİLİR olmasının ön şartı. Açık çevrim 0.65 değeri ise doğrulanmış SP-8110 bandının ÜST ucudur (bant ortası 0.50); 0.50 kullanılsaydı GG bleed debisi ve dolayısıyla açık çevrim Isp kaybı ~%30 artardı (F-1 örneğinde Isp kaybı 2.26 s -> ~2.7 s). Bu iyimserlik etiketlenmemiş.

### [x] F100 — `cycle_power_balance.py::_exhaust_isp_s`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
ve = sqrt(2*cp*T_e*(1 - (p_a/p_e)**((g-1)/g))) ; Isp = ve/G_0
```

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 3 (ideal nozul çıkış hızı, Eq. 3-15/3-16 ailesi). Türbin çıkış toplam sıcaklığının durgunluk sıcaklığı olarak kullanılması doğru. p_e <= p_a durumunda 0 döndürüp çağırana uyarı bırakması dürüst davranış.

**Sayısal etki:** Denklem doğru ama TAM UYUM (optimum genişleme) varsayımı bir ÜST SINIRDIR: gerçek GG egzoz nozulları çok düşük genişleme oranlıdır. Ölçülen (F-1, PR=16.4, TIT=1062 K): T_ex=770 K, p_ex=4.56 bar -> Isp_egzoz=118.3 s, motor Isp kaybı 2.26 s. Bu bir varsayım etiketiyle işaretlenmiyor; gerçekte kayıp bir miktar daha büyüktür. Sayısal sapma ölçülemedi (gerçek egzoz nozul geometrisi modellenmiyor).

### [x] F101 — `cycle_power_balance.py::_pump_power_w`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
P = mdot * dp_bar * PA_PER_BAR / (rho * eta)
```

**Kaynak:** Sutton & Biblarz, 'Rocket Propulsion Elements' 9. baskı Böl. 10 (pompa gücü/hidrolik güç); Huzel & Huang NASA SP-125 Böl. 6. Boyut analizi: (kg/s)·(Pa)/(kg/m3) = W — TEMİZ.

**Sayısal etki:** SAYISAL OLARAK DOĞRULANDI. RS-25 (Pc=206.4 bar, mdot=514.5 kg/s, MR=6.03, LH2, staged fuel-rich): kod yakıt pompası 51.87 MW — yayımlanan HPFTP ~53 MW (%2 sapma); ox 13.53 MW — yayımlanan HPOTP ana kademe ~15 MW. Ön yakıcı basıncı kod 327.6 bar — yayımlanan SSME FPB ~327 bar (%0.2!). Ön yakıcı O/F kod 0.917 — yayımlanan ~0.87-0.90. Türbin PR kod 1.38 — yayımlanan ~1.5. F-1 (Pc=70 bar, mdot=2578, MR=2.27): kod 28.75 MW ama kodun basınç zinciri 86 bar veriyor; gerçek F-1 pompa çıkışı ~125 bar'a ölçeklenince 41.6 MW — yayımlanan ~41 MW (55 000 hp). Denklem ve birimler sağlam.

### [x] F102 — `cycle_power_balance.py::_turbine_specific_work ve ::_turbine_exit_temp`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
dh = eta*cp*T_in*(1 - PR**(-(g-1)/g)) ;  T_ex = T_in*(1 - eta*(1 - PR**(-(g-1)/g)))
```

**Kaynak:** İzentropik iş × izentropik verim; izentropik verim tanımı gereği T_ex bağıntısı türetilir. Sutton & Biblarz 9. baskı Böl. 10; NASA SP-8110 Böl. 2.2 (türbin aerotermodinamik nokta tasarımı) aynı formülasyonu kullanır. Birimler: J/(kg·K)·K = J/kg — TEMİZ. Donmuş (frozen) cp seçimi türbin genişlemesi için standart ve kaynakta açıkça belirtilmiş.

**Sayısal etki:** Yanma gazı dallarında DOĞRULANDI. CEA'dan gelen özellikler NIST ile karşılaştırıldı: ox-zengin ön yakıcı gazı (MW=31.45, 750 K) cp=1091 J/kgK — saf O2 750 K'de 1083 J/kgK (%0.7); yakıt-zengin CH4 gazı (MW=15.59, 900 K) cp=3629 J/kgK — saf CH4 900 K'de ~3620 J/kgK (%0.3). Birim dönüşümleri de tek tek denetlendi: °R->K bölme 1.8 (doğru), BTU/(lbm·°R)->J/(kg·K) katsayısı 4186.8 (kesin değer 1055.056/(0.45359237·5/9)=4186.8, DOĞRU), bar->psia 14.503773773 (DOĞRU). NOT: 500-700 bar ön yakıcı basıncında CEA'nın ideal gaz varsayımı ~%3-8 gerçek gaz sapması bırakır (Tr~4.7-4.9, Z~1.05-1.10) — bu, dosyanın kapsamı dışında bilinçli bir sadeleştirme.

### [ ] F103 — `cycle_power_balance.py::solve_cycle (FFSC çapraz besleme)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
solve_shaft(...) her mili YALNIZ kendi pompasıyla dengeliyor; ox ön yakıcısına giden YAKIT için basınç kısıtı yok (assumptions: 'ffsc_cross_feed_not_modelled')
```

**Olması gereken:** staged_combustion dalı çapraz akış için AÇIKÇA bir boost kademesi modelliyor (_pump_power_w(pb_ox, max(d_ox_boost - disch_ox_main, 0), ...)). FFSC dalında aynı simetri yok: ox-zengin ön yakıcıya giden küçük yakıt akışının pompa çıkışından besleneceği yazılıyor ama YAKIT pompası çıkışı gereken basıncın altında kalıyor. Gerçek FFSC motorlarında bunun için ayrı bir kick/boost kademesi vardır ve raporlanan yakıt pompası çıkış basıncı bu yüzden gerçeğin altındadır.

**Kaynak:** Mimari kaynak doğru (Sutton 9. baskı Böl. 6 full-flow şeması). Eksik olan, aynı dosyanın staged dalında zaten uygulanmış olan boost-kademe muhasebesi.

**Sayısal etki:** ÖLÇÜLDÜ (Raptor: Pc=300, mdot=650, MR=3.6): ox ön yakıcısına 8.43 kg/s YAKIT gidiyor, gereken besleme basıncı 774.3 bar, oysa raporlanan yakıt pompası çıkışı 628.8 bar -> 145.6 bar EKSİK. İhmal edilen pompa gücü 0.387 MW = toplam pompa gücünün %0.52'si (güç dengesine etkisi küçük). Ters yön (yakıt ön yakıcısına giden 35.6 kg/s oks) sorunsuz: 626.8 bar gerekiyor, ox pompası 776.3 bar veriyor.

### [x] F104 — `cycle_power_balance.py::solve_cycle (staged_combustion, ox_rich raporlaması) / ::_pump_dict`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
_pump_dict('fuel', m_fuel_total, pump_inlet_fuel_bar, detail['d_fuel'], detail['p_fp'], ...)
```

**Olması gereken:** Güç hesabı DOĞRU (ana akış oda zincirine, küçük ön yakıcı akışı boost kademesiyle yüksek basınca), ama raporlanan sözlükte TAM debi ile BOOST çıkış basıncı yan yana yazılıyor; okuyucu bu iki alandan gücü yeniden hesaplarsa tutmuyor. 'note' alanı durumu açıklıyor ama sayılar kendi içinde çelişkili kalıyor. dp_bar/discharge alanları kademe kademe (main / boost) verilmeli.

**Kaynak:** RS-25 HPOTP ana+boost mimarisi (NASA SP-8107 'Turbopump Systems for Liquid Rocket Engines') — atıf yerinde.

**Sayısal etki:** ÖLÇÜLDÜ (RD-180 benzeri ORSC: Pc=261.7 bar, mdot=1250, MR=2.72, RP-1): raporlanan yakıt pompası ṁ=336 kg/s ve çıkış=721.7 bar. Bu ikisinden P=ṁ·ΔP/(rho·eta)=39.8 MW çıkar, oysa raporlanan power_W=18.54 MW — %115 fark. Güç doğru, raporlama yanıltıcı.

### [x] F105 — `cycle_power_balance.py::solve_cycle (tap_off dalı)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
pb = solve_preburner_of(fuel, oxidizer, p_gas, tit, 'fuel_rich')  ama akış bölüşümü ANA mr ile: m_ox_b, m_f_b = _flow_split(mdot_bleed, mr)
```

**Olması gereken:** Tap-off gazının özellikleri O/F~0.17'lik yakıt-zengin tabakadan alınırken, o gazın itici muhasebesi ANA O/F (ör. 2.27) üzerinden yapılıyor. İki taraf birbirini tutmuyor: gerçekte yakıt-zengin tabakayı beslemek için fazladan yakıt harcanır ve kalan oda karışımı bir miktar oks-zengine kayar. Kod bunu 'tapoff_gas_model' info etiketiyle işaretliyor — sahte sayı üretmiyor, ama tutarsızlık sayısallaştırılmamış.

**Kaynak:** Tap-off mimarisi: Sutton 9. baskı Böl. 6; NASA SP-8110 fig. 11 (tapoff çevrimi). Tabaka O/F'i için nicel bir kaynak bulunamadı — tap-off gaz sıcaklığı gerçekte film/tabaka tasarımına bağlıdır.

**Sayısal etki:** ÖLÇÜLEMEDİ — tabaka karışım modeli bu dosyada yok, dolayısıyla sapma sayısallaştırılamıyor. Büyüklük mertebesi: bleed oranı tipik olarak %1-5 olduğundan ana oda O/F kayması aynı mertebede (<%5) kalır; ayrıca tap-off dalı ana odayı mdot_main ile raporluyor, oysa gaz odadan ALINDIĞI için c*/Pc'yi belirleyen mdot_total'dir.

### [x] F106 — `flight_vehicle.py::_normalize_hybrid`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
inert = _num(kd.get('dry_mass_estimate_kg'))  ; kaynak: dry_mass_est = 0.25 * self.m_total
```

**Olması gereken:** Hibrit motorun atıl kütlesi 'yakıtın %25'i' kaba oranıyla tahmin ediliyor ve bu değer doğrudan 6-DOF aracının kuru kütlesine giriyor. Kod bunu engine_inert_mass_is_estimate=True + açıklayıcı not ile DÜRÜSTÇE işaretliyor (bu doğru davranış). Yine de bileşen dökümü olmayan bir tahminin uçuş sonucunu ne kadar sürüklediği kullanıcıya sayısal olarak gösterilmeli.

**Kaynak:** hybrid_rocket_engine.py içindeki kendi yorumu ('~25% of propellant for small motors') dışında kaynak bulunamadı.

**Sayısal etki:** ÖLÇÜLDÜ (kuru kütle taraması): m_dry 18 → 24 kg (±%15) apojeyi 3965.9 → 3691.3 m taşıyor (%6.9). Yani atıl kütle tahminindeki ±%25'lik bir hata apojede ~%10 hataya dönüşüyor.

### [x] F107 — `flight_vehicle.py::normalize`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
hybrid: engine_od_m = chamber_diameter (bölme YOK) ; solid/liquid: _mm_to_m(chamber_diameter) ; liquid prop yedeği = total_mass_flow·burn_time
```

**Kaynak:** Motor modüllerinin kendi çıktı birimleri (kod-teyitli).

**Sayısal etki:** BİRİM İDDİALARI KAYNAK KODLA TEK TEK DOĞRULANDI: hybrid chamber_diameter = self.D_ch (metre, D_port_final·1.5 ya da girdi) → bölme yapmaması DOĞRU; solid chamber_diameter = D_chamber·1000 (mm) ve cad_design.case_design.outer_diameter = ·1000 (mm) → /1000 DOĞRU; liquid chamber_diameter cooling'ten mm (kaynakta 'already in mm' yorumu teyitli) → /1000 DOĞRU; liquid overall_length_mm = cooling.chamber_length(mm) + nozzle_length·1000 → mm+mm tutarlı; liquid total_mass_flow = F/(isp·g0) yani kg/s → ·burn_time = kg DOĞRU. 1000x sınıfı bir birim hatası BULUNAMADI. Çift-sayım da doğru ayrılmış (atıl kütle propelanı içermiyor).

### [x] F108 — `heat_transfer_analysis.py::_analyze_thermal_safety`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
sigma_th = E * alpha * dT_wall / (2*(1-nu))
```

**Kaynak:** İnce plaka/kabukta doğrusal kalınlık-boyu sıcaklık gradyanının yüzey gerilmesi: Timoshenko & Goodier, Theory of Elasticity; Boley & Weiner, Theory of Thermal Stresses Böl. 10-11. Atıf ile formül örtüşüyor.

**Sayısal etki:** Birim denetimi: Pa * (1/K) * K = Pa ✓. dT_wall artık wall_analysis'ten gelen GERÇEK cidar-içi gradyan (T_inner - T_outer), tam ankastre E*alpha*(Tw-293) formu değil — v2.5.2 düzeltmesi doğru yönde. Malzeme özellikleri _resolve_mechanical_properties ile seçilen kayıttan okunuyor, çelik hardcode kalmamış (yalnız hiçbir kayıt bulunamazsa jenerik çelik varsayılanı devreye giriyor).

### [x] F109 — `heat_transfer_analysis.py::_bartz_coefficient`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
h_g = (0.026/D_t^0.2) * (mu^0.2*cp/Pr^0.6) * (Pc/c*)^0.8 * (D_t/R_c)^0.1 * (A_t/A)^0.9 * sigma ;  sigma = 1/([0.5*(Tw/Tc)*m2 + 0.5]^0.68 * m2^0.12), m2 = 1+(g-1)/2*M^2
```

**Kaynak:** Bartz, D.R. (1957), Jet Propulsion 27(1); Sutton & Biblarz, Rocket Propulsion Elements 9th ed., Eq. 8-22 ve Eq. 8-23. Katsayı 0.026, üsler (0.2 / 0.8 / 0.1 / 0.9) ve sigma düzeltmesi kaynakla birebir örtüşüyor.

**Sayısal etki:** 2026-07-16 g0 düzeltmesi TEYİT EDİLDİ. Boyut analizi elle yapıldı: kg^1 · m^0 · s^-3 · K^-1 = W/(m^2·K) TAM olarak çıkıyor, yani SI'de g0 terimi gerçekten olmamalı (olsaydı h_g g0^0.8 = 6.21x şişerdi — docstring'deki 6.2 değeri de doğru). Sayısal sağlama (kodu çalıştırdım): SSME sınıfı (206 bar, Dt=0.262 m, c*=2340) h_g=40.4 kW/m^2K, q_boğaz=112 MW/m^2 (Tw=800 K); RP-1/LOX (48 bar) q=25.4 MW/m^2; F-1 sınıfı (70 bar) q=28.9 MW/m^2; küçük hibrit (20 bar) q=14.0 MW/m^2. Hepsi yayımlanmış boğaz akısı bantlarının (SSME ~100-160, RP-1 motorları ~20-35 MW/m^2) içinde. g0'lı hatalı form 700 MW/m^2 verirdi. Eğrilik terimi (1/rc_over_dt)^0.1 = (D_t/R_c)^0.1 doğru yönde yazılmış.

### [x] F110 — `heat_transfer_analysis.py::_calculate_cooling_efficiency`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
efficiencies = {'natural':0.3, 'forced':0.6, 'regenerative':0.9}
```

**Olması gereken:** Bu sayıların fiziksel bir tanımı yok ('soğutma verimi' hangi oran? ısı çekme oranı mı, sıcaklık etkinliği mi?). Ya bir tanım + kaynak eklenmeli ya da çıktıdan kaldırılmalı. Aynı şekilde _analyze_cooling_requirements'taki 50 K / 100 K / 200 K sıcaklık artışları da kaynaksız kabul.

**Kaynak:** Kaynak bulunamadı — literatürde bu üç değeri veren bir tablo tanımıyorum. Mühendislik sezgisiyle sıralaması doğru (doğal < zorlanmış < rejeneratif) ama sayılar keyfi.

**Sayısal etki:** ÖLÇÜLEMEDİ — tanımsız bir büyüklüğün sapması hesaplanamaz. Kullanıcıya 'cooling_efficiency' olarak gösteriliyor, yani sayısal bir iddia gibi görünüyor; gerçekte sabit bir etikettir. Türetilen başka bir hesaba girmiyor (yalnız raporlanıyor), dolayısıyla fiziksel zincire zarar vermiyor.

### [ ] F111 — `heat_transfer_analysis.py::_gas_absorptivity`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** hayır

**Koddaki denklem:**
```
alpha = (T_g/T_w)^0.5 * eps_g(T_w, p*L*(T_w/T_g))
```

**Olması gereken:** Modest Eq. (10.146) üsleri TÜRE GÖRE farklıdır: H2O için (T_g/T_w)^0.5, CO2 için (T_g/T_w)^0.65. Kod karışımın tamamına 0.5 uyguluyor, yani CO2 absorptivitesi eksik hesaplanıyor.

**Kaynak:** Modest, Radiative Heat Transfer, Eq. (10.146) (Hottel absorptivite ölçekleme kuralı).

**Sayısal etki:** ÖLÇÜLDÜ/HESAPLANDI. T_g/T_w = 3500/800 = 4.4 için üs farkı 4.4^0.15 = 1.24, yani CO2 payı %24 eksik. Ancak alpha_g terimi q_rad içinde T_w^4 ile çarpılıyor: (800/3500)^4 = 0.0027, alpha katkısı q_rad'ın ~%0.6'sı. Net etki q_rad'da <%0.2, toplam ısı akısında <%0.02 — pratikte ölçülemez. Yalnız kayıt için bildiriyorum, düzeltme aciliyeti yok.

### [x] F112 — `heat_transfer_analysis.py::_get_gas_properties`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
gas_viscosity = 1.184e-7 * MW^0.5 * T^0.6   [kg/(m*s)]
```

**Kaynak:** Bartz (1957) viskozite korelasyonu, orijinali mu = 46.6e-10 * M^0.5 * T^0.6 [lb/(in*s)], T in °R. Birim dönüşümünü elle yaptım: 1 lb/(in*s) = 17.858 kg/(m*s), T[°R]^0.6 = 1.8^0.6 * T[K]^0.6 = 1.4310 * T[K]^0.6 -> 46.6e-10 * 17.858 * 1.4310 = 1.1909e-7. Kod 1.184e-7 kullanıyor.

**Sayısal etki:** Katsayı tam SI dönüşümünden %0.58 düşük (1.184e-7 yerine 1.191e-7). Bartz'da mu yalnız 0.2. kuvvette girdiğinden h_g üzerindeki etki %0.12 — yuvarlama düzeyinde, düzeltme gerekmez. Pr = 4g/(9g-5) (Eucken, Sutton Eq. 8-23) ve cp = g*R/(g-1) doğru; g=1.2 için Pr=0.828 çıkıyor (tipik yanma gazı 0.8-0.85 bandı).

### [x] F113 — `heat_transfer_analysis.py::_resolve_throat_conditions`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
c* = sqrt(g*R*Tc)/(g*sqrt((2/(g+1))^((g+1)/(g-1))))  ;  A_t = mdot*c*/Pc  ;  T_t = Tc/(1+(g-1)/2)
```

**Kaynak:** Sutton & Biblarz Eq. 3-32 (c*), tıkanmış boğazda süreklilik (c* tanımı), izantropik M=1 durum bağıntısı.

**Sayısal etki:** Cebirsel olarak sadeleştirdim: kodun ifadesi sqrt(R*Tc)/Gamma ile ÖZDEŞ (Gamma = sqrt(g)*(2/(g+1))^((g+1)/(2(g-1)))). Ayrıca _calculate_heat_transfer_coefficients içindeki boğaz statik basıncı düzeltmesini de doğruladım: rho_t*a_t = Pc*(2/(g+1))^(g/(g-1)) * sqrt(g/(R*T_t)) = Pc/c* özdeşliği TAM olarak sağlanıyor, yani raporlanan Reynolds artık tutarlı (yorumdaki '1.8x şişme' düzeltmesi doğru).

### [x] F114 — `heat_transfer_analysis.py::_species_emissivity`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
factor = 1 - ((A-1)*(1-P_E)/(A+B-1+P_E)) * exp(-c*(log10(pal_m/pal))^2)  ;  eps_0 = exp(sum_i a_i(t)*x^i)
```

**Kaynak:** Leckner, Combustion and Flame 19(1):33-48 (1972); Modest, Radiative Heat Transfer, Tablo 10.4. KATSAYI MATRİSLERİ birebir doğrulandı: H2O (-2.2118, -1.1987, 0.035596 / 0.85667, 0.93048, -0.14391 / -0.10838, -0.17156, 0.045915) ve CO2 (-3.9893, 2.7669, -2.1081, 0.39163 / 1.2710, -1.1090, 1.0195, -0.21897 / -0.23678, 0.19731, -0.19544, 0.044644) tabloyla aynı; A/B/c/(p_aL)_m/P_E parametreleri (H2O: 1.888-2.053log10(t), 1.10t^-1.4, 0.5, 13.2t^2, p+2.56p_a/sqrt(t) — CO2: 1+0.1t^-1.45, 0.23, 1.47, 0.054/t^2 veya 0.225t^2, p+0.28p_a) de birebir. DÜRÜSTLÜK NOTU: paydadaki +P_E işaretini birincil kaynaktan (Modest Tablo 10.4 / Leckner 1972 orijinali) bu oturumda TEYİT EDEMEDİM — web erişimiyle formülün tam hâline ulaşamadım. Kodun kendi yorumu bunun bilinçli bir sapma olduğunu söylüyor.

**Sayısal etki:** ÖLÇÜLDÜ. Üretilen eps_g değerleri fiziksel: 20 bar/L=0.18 m -> 0.173; 70 bar/L=0.18 m -> 0.329 (roket haznesi literatür bandı 0.2-0.4). q_rad(3500 K gaz, 800 K cidar, 70 bar) = 2.50 MW/m^2, kara cisim üst sınırı 8.5 MW/m^2 — toplam boğaz akısının ~%8'i, docstring'deki '%5-30' bandıyla tutarlı. İşaret duyarlılığını ölçtüm: -P_E formu 3000 K'de eps_g'yi %12-13 ARTIRIYOR, yani toplam akıda ~%1 fark; ayrıca -P_E formu P_E = A+B-1 (~2 bar) noktasında kutup üretiyor ve yüksek basınçta eps'i basınçla AZALTIYOR (basınç genişlemesi fiziğine aykırı). Kodun seçimi asimptotik olarak sağlıklı. Etki küçük olduğu için severity DUSUK.

### [ ] F115 — `heat_transfer_analysis.py::_species_emissivity`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
_LECKNER_T_MAX = 3000.0  # K ; T = min(max(T_g, 300), 3000)
```

**Olması gereken:** Leckner (1972) korelasyonunun bildirilen sıcaklık geçerlilik aralığı ~300-2500 K'dir; 2500-3000 K bandı ekstrapolasyondur. Roket haznesi 3000-3600 K'de çalıştığından korelasyon ZATEN her çağrıda zarfın dışında. Optik derinlik kelepçesi (1e-4..1e3 bar*cm) ise Leckner'in p_aL aralığıyla (0.001-10 bar*m) uyumlu — o taraf temiz.

**Kaynak:** Leckner (1972) fit aralığı; Modest Tablo 10.4 geçerlilik notu (300 K <= T <= 2500 K).

**Sayısal etki:** Kelepçenin YÖNÜ kodun iddia ettiği gibi muhafazakâr: eps_g bu bantta sıcaklıkla azaldığından 3400 K'lik gazı 3000 K'de kelepçelemek eps'i ABARTIR. Ölçtüm: 3000 K'de eps_g=0.329 (70 bar, L=0.18 m); gerçek 3400 K değeri daha düşük olurdu. Yani hata güvenli yönde. Belgelenmiş bir mühendislik bekçisi; yalnız 'literatür sınırı 2500 K' notu docstring'de eksik.

### [ ] F116 — `heat_transfer_analysis.py::analyze_axial_profile`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
h_i = _bartz_coefficient(..., Tw_ref, ...)  ; sonra denge cidarı bisection'da AYNI h_i kullanılıyor
```

**Olması gereken:** Bartz sigma düzeltmesi cidar sıcaklığına bağlı olduğundan denge cidar sıcaklığı çözümünde h_g de iterasyona sokulmalı (regen_cooling.py::_station_wall_balance bunu doğru yapıyor — 60 adımlı sabit nokta). heat_transfer_analysis'te h_g referans cidarda dondurulmuş.

**Kaynak:** Sutton & Biblarz Eq. 8-22 sigma teriminin tanımı (Tw bağımlılığı).

**Sayısal etki:** HESAPLADIM. Tc=3000 K, M=1 için sigma(Tw=300 K)/sigma(Tw=1073 K) = 1.163. Yani denge cidarı referans cidardan çok soğuk çıkarsa h_g %16 EKSİK kullanılıyor -> denge cidar sıcaklığı ve q eksik tahmin ediliyor (güvensiz yön, ama sınırlı). Tasarım akısı (Tw_ref'te değerlendirilen, panelin ana güvenlik sayısı) bundan etkilenmiyor; yalnız T_wall_eq etkileniyor.

### [x] F117 — `hrma/engines/injector_design.py::_design_gas_gas_coaxial`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
j_mom = (rho_out*v_out**2)/(rho_in*v_in**2) ; gap = (sqrt(D_i^2 + 4*A_ann/pi) − D_i)/2
```

**Kaynak:** Sutton & Biblarz Böl. 9 (koaksiyel shear enjektör, momentum-akı oranı J = (ρu²)_dış/(ρu²)_iç); anülüs geometrisi cebirsel olarak tam

**Sayısal etki:** Anülüs boşluk formülü TAM doğrudur (A = π(D_o²−D_i²)/4 ile özdeş, yaklaşım değil) — aynı formül pintle ve utils koaksiyel dallarında da doğru. J tanımı standart. ΔP/Pc bandının (0.08-0.10) gaz-gaz için MÜHENDİSLİK KILAVUZU olduğu, SP-8089'un sıvı için olduğu kodda AÇIKÇA etiketlenmiş ve 'assumption' olarak raporlanıyor — bu dürüst ve doğru bir davranış, uydurma değil. Tek küçük not: boğulmuş postta rho_exit/v_exit boğaz (P*, T*) değerleridir; odaya genişleyen jetin momentum akısı basınç-itki terimini de içerir, dolayısıyla J muhafazakâr tarafta kalır (kılavuz seviyesinde önemsiz).

### [x] F118 — `hrma/engines/injector_design.py::compressible_orifice_flow`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
boğulmuş: Cd·A·P0·sqrt(g/(R·T0))·(2/(g+1))^((g+1)/(2(g−1))) ; boğulmamış: Cd·A·P0·sqrt((2g/((g−1)R T0))·(Pr^(2/g) − Pr^((g+1)/g)))
```

**Kaynak:** J.D. Anderson, Modern Compressible Flow 3. baskı Böl. 3 (izentropik lüle/orifis debisi); P*/P0 = (2/(γ+1))^(γ/(γ−1))

**Sayısal etki:** ÖLÇÜLDÜ: γ=1.2 için iki dal kritik oranda süreklidir (boğulmuş boyutsuz akı 0.6485, boğulmamış dalın Pr=Pr_crit'teki değeri 0.6493 — %0.1 fark, sadece yuvarlama). T*/T0 = 2/(γ+1), Mach = √((2/(γ−1))(Pr^(−(γ−1)/γ)−1)), ρ_çıkış = P/(R·T) bağıntılarının tümü doğru. Birimler SI ve tutarlı; R = R_UNIVERSAL/MW (8314.46 J/(kmol·K) ÷ kg/kmol) doğru.

### [x] F119 — `hrma/engines/injector_design.py::design_injector (RHO_GAS_DEFAULT)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
rho_gas = RHO_GAS_DEFAULT = 5.0 kg/m³ (T_c veya mw verilmezse)
```

**Olması gereken:** T_c/mw verildiğinde ideal gaz bağıntısı ρ = Pc/((R_u/MW)·T_c) doğru kurulmuş ve birimler tutarlı (R_UNIVERSAL = 8314.46 J/(kmol·K), mw kg/kmol — hybrid_rocket_engine.py 8314.46/self.R ve liquid_rocket_engine.py mw_g_mol ile besliyor, KONTROL EDİLDİ ve tutarlı). Varsayılan 5.0 kg/m³ ise yalnız yüksek Pc için makul; düşük odalarda 2-3 kat yüksek.

**Kaynak:** İdeal gaz hâl denklemi; varsayılan sayı için kaynak bulunamadı (kod bunu 'assumption' olarak açıkça raporluyor — dürüst)

**Sayısal etki:** ÖLÇÜLDÜ/hesaplandı: Pc=20 bar, T_c=3000 K, MW=22 → gerçek ρ=1.76 kg/m³, varsayılan 5.0 → 2.8 kat yüksek. SMD etkisi: Elkotb ρ_A^0.06 → yalnız %6; Lefebvre swirl ρ_A^(−0.25) → SMD %23 DÜŞÜK. İhmal edilebilir mertebede.

### [x] F120 — `hrma/engines/injector_design.py::design_injector (impinging_triplet TMR)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
tmr = (2.0*mdot_ox*v_ox*np.sin(np.radians(half))) / (mdot_fuel*v_f)  ; ok = 0.7 <= tmr <= 2.0
```

**Olması gereken:** O-F-O triplet için standart tasarım kriteri iki dış jetin ve merkez jetin momentumlarının dengelenmesidir; ancak sin(yarı açı) çarpanının bu haliyle hangi kaynaktan geldiğini bulamadım. Merkez jet eksenel ve iki dış jet eksene simetrik ise dış jetlerin ENİNE bileşenleri birbirini zaten götürür, dolayısıyla 'dış enine momentum / merkez momentum' oranı doğrudan bir denge kriteri değildir. Kabul bandı (0.7-2.0) da kaynaksız. Not: yalnız uyarı bayrağı üretiyor, hiçbir GEOMETRİK boyutu sürmüyor.

**Kaynak:** kaynak bulunamadı (sin çarpanı ve 0.7-2.0 bandı için); genel triplet pratiği NASA SP-8089 Böl. 2'de niteliksel

**Sayısal etki:** sin(30°)=0.5 olduğundan TMR = (ṁ_o v_o)/(ṁ_f v_f) çıkıyor. LOX/RP-1'de O/F=2.3, v_f/v_o=1.19 → TMR ≈ 1.93, bandın üst ucunda; O/F=2.6'da 2.2 → her koşuda uyarı üretir. Tasarım boyutu değişmediği için etki yalnız yanlış-pozitif uyarı.

### [x] F121 — `hrma/engines/injector_design.py::discharge_coefficient / hydraulic_flip_risk / _solve_circuit (K_c)`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
K_c = (p1_bar − p_v_bar)/max(p1_bar − pc_bar, 1e-9) ; flip = sharp ve 1 ≤ L/D ≤ 5 ve K_c < 1.5
```

**Kaynak:** Nurick, ASME J. Fluids Eng. 98 (1976) — K = (P₁−P_v)/(P₁−P₂), kavitasyonlu rejimde Cd = C_c√K; hidrolik flip keskin girişli, orta L/D orifislerde düşük K'da gözlenir. Cd tablosu (keskin kısa 0.63 / keskin orta 0.78 / keskin uzun 0.84 / radüslü 0.90-0.92) SP-8089 ve Lefebvre Böl. 5 tipik değerleriyle uyumlu.

**Sayısal etki:** Birim tutarlı (bar/bar → boyutsuz). Doymuş N₂O'da P₁ = P_v → K_c = 0 çıkıyor ve flip uyarısı veriliyor — bu FİZİKSEL OLARAK DOĞRU (doymuş sıvı orifiste kesinlikle flaşlar). N₂O olmayan devrelerde P_v = 0.05 bar varsayımı açıkça 'assumption' olarak raporlanıyor (dürüst). Tek not: FLIP_KC_LIMIT = 1.5 eşiği için kesin bir yayımlanmış sayı doğrulayamadım; Nurick verilerinde geçiş 1.5-2.0 bandındadır, yani 1.5 muhafazakâr ve savunulabilir.

### [x] F122 — `hrma/engines/injector_design.py::hem_mass_flow`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
G(P_t) = rho2(P_t)*sqrt(2*(h1−h2(P_t))), s2 = s1, P_t ∈ [P2,P1] taranıp maksimum alınır
```

**Kaynak:** Homojen denge modeli — Solomon (2011) uygulama deseni; izentropik flaş genişleme. Aşırı-soğutulmuş giriş entalpisi h₁ = h_l(T₁) + (P₁−P_v)/ρ_l sıkıştırılamaz sıvı için doğru; s₁ ≈ s_l(T₁) yaklaşımı standart.

**Sayısal etki:** Doğrulandı: kalite x, karışım yoğunluğu 1/ρ = (1−x)/ρ_l + x/ρ_v ve boğulma tarama mantığı doğru. Entropi tablosunun (240-306 K) sıcaklık ızgarası tank_blowdown ile aynı; ekstrapolasyon np.clip ile kapatılmış. Zarf uyarısı: T₁ > 306 K'de tablo kırpılıyor (N₂O kritik 309.5 K) — sessiz ama muhafazakâr.

### [x] F123 — `hrma/engines/injector_design.py::nhne_mass_flow`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
kappa = sqrt((p1−p2)/(pv−p2)) ; m_nhne = (kappa*m_spi + m_hem)/(1+kappa)
```

**Kaynak:** Dyer, Doran, Dunn, Zilliac ve ark., AIAA 2007-5702, 'Modeling Feed System Flow Physics for Self-Pressurizing Propellants' — κ = √((P₁−P₂)/(P_v−P₂)), ṁ = (κ·ṁ_SPI + ṁ_HEM)/(1+κ). Kodda verilen atıf DOĞRU; uydurma değil.

**Sayısal etki:** ÖLÇÜLDÜ ve teyit edildi (scratchpad/case.py): doymuş giriş (P₁=P_v) için κ tam olarak 1.000 çıkıyor → ṁ_NHNE = (ṁ_SPI+ṁ_HEM)/2. Bu, Dyer modelinin literatürde bilinen ve alıntılanan davranışıdır. N₂O 293 K (P_sat=50.54 bar) → Pc=30 bar, d=1.5 mm, Cd=0.78: SPI=0.0783, HEM=0.0402, NHNE=0.0592 kg/s; kütle akısı G=33 513 kg/(s·m²) — Dyer/Solomon deneysel bandı (~20-60 ×10³) içinde. SPI > NHNE > HEM sıralaması ve P₂ ≥ P_v'de saf SPI'ye sürekli geçiş doğru. Boğulma taraması çözünürlüğü de test edildi: 60 → 2000 nokta arasında fark %0.005 (ihmal edilebilir).

### [x] F124 — `hrma/engines/injector_design.py::pintle_spray_angle`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
theta = arccos(1/(1+TMR))
```

**Kaynak:** Cheng ve ark. (2017) pintle sprey açısı korelasyonu; TRW mirası (Dressler & Bauer AIAA 2000-3871). Kontrol hacmi momentum korunumundan: cosθ = M_eksenel/(M_eksenel + M_radyal) = 1/(1+TMR).

**Sayısal etki:** Sınır kontrolleri doğru: TMR=1 → 60° (yayımlanmış pintle verisiyle uyumlu), TMR→0 → 0°, TMR→∞ → 90°. Hibrit dalındaki TMR = f/(1−f) türetimi de doğru (aynı akışkan + aynı ΔP → hızlar eşit, sadeleşiyor); f=0.5 → TMR=1 → θ=60°, kod yorumuyla tutarlı. Sıvı dalındaki TMR = (ṁ_f·v_f)/(ṁ_ox·v_ox) radyal/eksenel tanımına uygun.

### [x] F125 — `hrma/engines/injector_design.py::smd_elkotb`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
SMD = 3.08*nu^0.385*(sigma*rho_l)^0.737*rho_A^0.06*dP^(−0.54)
```

**Kaynak:** Elkotb, Progress in Energy and Combustion Science 8 (1982) — düz orifis dizel SMD korelasyonu; Lefebvre & McDonell, Atomization and Sprays'de aktarılmıştır

**Sayısal etki:** BİRİM DOĞRULAMASI YAPILDI (kritikti): SI girdilerle (ν m²/s, σ N/m, ρ kg/m³, ΔP Pa) çıktı METRE cinsindendir. Dizel referansıyla sınandı: ν=3e-6, σ=0.03, ρ_l=830, ρ_A=25, ΔP=1e7 Pa → 4.95e-5 m = 49.5 µm; 100 bar'da dizel için yayımlanmış SMD 30-60 µm bandına oturuyor. Kod çıktıyı 1e6 ile çarpıp µm'ye çeviriyor — doğru. ZARF UYARISI: korelasyon dizel için (ν 1-5 cSt, ΔP 5-100 MPa) kalibre edildi; kod bunu N₂O'da (ν ≈ 0.13 cSt) ve ΔP ≈ 0.4-1 MPa'da kullanıyor, yani kalibrasyon zarfının belirgin dışında — bu ayrı bir belirsizlik kaynağı (kod bunu belirtmiyor).

### [x] F126 — `hrma/engines/injector_design.py::smd_impinging`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
D32 = C_imp·d_j·We_j^(−1/3),  We_j = ρ_l·v²·d_j/σ,  C_imp = 2.6
```

**Olması gereken:** We^(−1/3) ölçeklemesi çarpışan-jet sıvı tabakası kırılımı için standart ve savunulabilir (Dombrowski & Johns / Hasson & Peck tabaka kararsızlığı analizinden çıkar). Ancak sabit için verilen atıf ('Ingebo TN 3265 eğilimi') doğrulanamadı: Ingebo'nun NACA TN 3265 korelasyonları hava akımındaki çarpışan jetler için farklı üslerle (D32 ~ d^a·V^b) verilmiştir; C_imp=2.6 değerini o kaynakta bulamadım. Kodun kendisi 'band 2-4, kalibre edilebilir' diyerek dürüst davranıyor — atıf 'ölçeklendirme benzeri' değil 'kaynak' gibi okunuyor, netleştirilmeli.

**Kaynak:** kaynak bulunamadı (C_imp=2.6 için); ölçekleme için Dombrowski & Johns (1963), Lefebvre Böl. 6

**Sayısal etki:** C_imp bandı 2-4 olduğuna göre SMD'de ±%54 belirsizlik (2.6 → 4.0 arası). Ölçüm: d_j=1 mm, v=30 m/s, ρ=750, σ=0.00175 → SMD=35.7 µm (C=2.6) / 54.9 µm (C=4.0). Bulgu #3'ün σ hatası bu daldan da geçiyor (2.25x).

### [x] F127 — `hrma/engines/injector_design.py::smd_lefebvre_swirl`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
SMD = 2.25*sigma^0.25*mu^0.25*mdot^0.25*dP^(−0.5)*rho_A^(−0.25)
```

**Kaynak:** Lefebvre & McDonell, Atomization and Sprays 2. baskı — basınç-swirl (simplex) SMD korelasyonu

**Sayısal etki:** Formül ve birimler doğru; SI girdilerle çıktı metre (σ=0.02, μ=2e-4, ṁ=1, ΔP=1e6, ρ_A=5 → 6.7e-5 m = 67 µm, makul). Tek sorun ÇAĞRI tarafında: ṁ eleman başına değil toplam veriliyor — bulgu #5'e bakınız.

### [x] F128 — `hrma/engines/injector_design.py::spi_mass_flow`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
mdot = Cd*A*sqrt(2*rho*dP)
```

**Kaynak:** Sutton & Biblarz, Rocket Propulsion Elements 9. baskı Böl. 8; NASA SP-8089

**Sayısal etki:** Boyut analizi yapıldı: [kg/m³·Pa]^0.5·m² = kg/s. Birim sözleşmesi doğru (A m², ρ kg/m³, ΔP Pa). dp ≤ 0'da 0 döndürme koruması var. hrma/utils/injector_design.py'deki tüm dallar da aynı denklemi bar→Pa dönüşümüyle (×1e5) doğru kuruyor.

### [ ] F129 — `hrma/utils/injector_design.py::_optimize_showerhead_holes`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
A_actual = N*pi*(d_h/2)**2 ; v_actual = mdot/(rho*A_actual) ; penalty += (v_actual - v_target)**2/100
```

**Olması gereken:** d_h = 2√(A_required/(Nπ)) olduğu için A_actual ≡ A_required, yani v_actual N'den TAMAMEN BAĞIMSIZ bir sabittir. 'Hız sapması' ceza terimi optimizasyonda hiçbir iş yapmıyor (ölü terim) — kullanıcının verdiği target_velocity=30 m/s girdisi sonucu etkilemiyor. Hız hedefini gerçekten uygulamak için ΔP (veya Cd) çözülmelidir, delik sayısı değil.

**Kaynak:** Süreklilik: ṁ = ρ·A·v — A sabitken v de sabit (Sutton & Biblarz Böl. 8)

**Sayısal etki:** ÖLÇÜLDÜ: v_actual = ṁ/(ρA_required) = Cd·√(2ΔP/ρ) = 28.0 m/s (ṁ=2, ρ=750, Pc=30, Cd=0.7) — N=4..200 aralığında değişmiyor. Sonuç: N yalnız çap ve L/D cezalarıyla belirleniyor; kullanıcının 'target_velocity' girdisi sessizce yutuluyor.

### [x] F130 — `hybrid_rocket_engine.py::_calculate_expansion_ratio`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
Pc/Pe = (1+(g-1)/2*Me²)^(g/(g-1)) çözülür, sonra eps = (1/Me)*((2/(g+1))*(1+(g-1)/2*Me²))^((g+1)/(2*(g-1)))
```

**Kaynak:** Sutton & Biblarz 9. baskı Denk. 3-13 (izentropik basınç-Mach) ve Denk. 3-14 (alan-Mach); Pe=Pa eşlenik genleşme koşulu Böl. 3.3

**Sayısal etki:** SAYISAL OLARAK SINANDI. Kodun çıktısı kapalı-form analitik değerle karşılaştırıldı: γ=1.20 Pc/Pa=20 → 3.6251 vs 3.6251; γ=1.20 Pc/Pa=68 → 8.8669 vs 8.8669; γ=1.25 Pc/Pa=100 → 10.6785 vs 10.6785. Fark %0.000. Kelepçe max(1.01, min(eps,250)) yalnız matematiksel geçerlilik sınırıdır, tipik tasarım aralığına dokunmuyor.

### [x] F131 — `hybrid_rocket_engine.py::_calculate_thrust_coefficient`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
CF = lambda*sqrt(2*g²/(g-1)*(2/(g+1))^((g+1)/(g-1))*(1-(Pe/Pc)^((g-1)/g))) + (Pe-Pa)*eps/Pc, Me brentq ile alan-Mach bağıntısından, Pe izentropik
```

**Kaynak:** Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Denk. 3-30 (momentum terimi) ve Denk. 3-31 (basınç terimi); alan-Mach bağıntısı Denk. 3-14; λ diverjans faktörü Tablo 3-3

**Sayısal etki:** SAYISAL OLARAK SINANDI. λ=1'e normalize edilmiş ideal CF: γ=1.20, ε=10, Pc/Pa=100 → 1.6428 (Sutton Şekil 3-6 okuması ≈1.64); γ=1.20, ε=4, Pc/Pa=20 → 1.4068; γ=1.30, ε=25, Pc/Pa=1000 → 1.7383; γ=1.20, ε=50, vakum → 1.9038 (γ=1.2 için teorik üst sınır 2.246, tutarlı). Birim tutarlılığı da doğru: Pe, Pc'den türetildiği için Pe/Pc ve (Pe−Pa)/Pc oranlarında bar birimi sadeleşiyor. λ yalnız momentum terimine uygulanmış — doğru pratik.

### [x] F132 — `hybrid_rocket_engine.py::_compile_results`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
dry_mass_est = 0.25*self.m_total ; total_mass = self.m_total + dry_mass_est ; 'number_of_segments': max(1, int(fuel_length/0.3))
```

**Olması gereken:** İki sihirli sayı: (a) kuru kütle = itici kütlesinin %25'i — küçük motorlar için makul bir mertebedir ama kodda kaynak yok, kamara basıncına/malzemeye/emniyet katsayısına bağlı olması gerekirdi ve modül zaten yapısal analiz koşuyor (structural_results'tan gerçek kovan kütlesi türetilebilirdi); (b) 0.3 m segment boyu üretim varsayımıdır, kaynağı yok. İkisi de design_summary altında mühendislik sayısı gibi sunuluyor.

**Kaynak:** Kaynak bulunamadı (kodda atıf yok). Küçük hibritlerde itici kütle oranı 0.6-0.8 aralığı literatürde yaygındır, %25 kuru kütle bununla uyumludur ama motor-özgü değildir.

**Sayısal etki:** ÖLÇEMEDİM (referans karşılaştırması için gerçek kovan kütlesi verisi gerekir). Sabit %25 varsayımı düşük basınçlı küçük motorda kuru kütleyi abartır, yüksek basınçlı büyük motorda hafife alır; mertebe olarak ±2 kat sapma beklenebilir. total_mass_kg kullanıcıya doğrudan gösteriliyor.

### [ ] F133 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** YANLIS_FORMUL · **Görünür:** hayır

**Koddaki denklem:**
```
self.L_grain = mdot_f/(rho_f*pi*D*r_dot_ox_only) ; reg0 = regression_rate(..., grain_length=self.L_grain) ; self.r_dot_initial = reg0['r_dot'] ; self.L_grain = mdot_f/(rho_f*pi*D*self.r_dot_initial)   # r_dot_initial GÜNCELLENMİYOR
```

**Olması gereken:** flux_mode='total' iken r_dot ile L_grain karşılıklı bağımlıdır (L → mdot_f → G_fuel → G_total → r → L). Kod tek geçiş yapıyor: saklanan r_dot_initial, GÜNCELLENMEDEN ÖNCEKİ (daha uzun) L_grain'e karşılık geliyor; sonrasında L_grain yeni r ile yeniden çözülüyor ama r geri güncellenmiyor. Sabit-nokta L üzerinde de kapatılmalı (tasarım noktasında analitik kapanış zaten var: G_fuel = G_ox/OF, dolayısıyla G_total = G_ox·(1+1/OF)).

**Kaynak:** Kodun kendi iterasyon mantığının tutarlılık gereği; harici kaynak gerekmiyor (iç tutarsızlık)

**Sayısal etki:** ÖLÇÜLDÜ. F=2 kN, O/F=6, HTPB/N2O, flux_mode='total': kod G_total_initial=414.0 kg/m²s ve r_dot_initial=1.0430 mm/s saklıyor. Güncellenmiş L_grain=786.7 mm ile kendi içinde tutarlı değerler G_total=407.9 ve r=1.0341 mm/s. Sapma +%0.9 (G_total'de +%1.5). flux_mode='ox' varsayılanında etki SIFIR (r, L'den bağımsız).

### [x] F134 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
D_port += 2*r_dot*dt ; num_steps = max(200, ceil(t_b*2*r_dot_init/(0.01*D_port_init))) ; m_f_grain = rho_f*(pi/4)*(D_f²-D_i²)*L_grain
```

**Kaynak:** Silindirik port geometrisi kütle korunumu (temel geometri); ileri Euler integrasyonu

**Sayısal etki:** ÖLÇÜLDÜ. Çap artışı = 2·yarıçap artışı doğru. Adım sayısı kuralı ilk adımdaki çap sıçramasını %1'de tutuyor; boyut analizi tutarlı (t_b[s]·r[m/s]/D[m] boyutsuz). Kütle kapanışı sınandı: F=2 kN, O/F=6, t_b=10 s koşusunda geometriden gelen m_f = 1.2087 kg, tasarım debisinden mdot_f·t_b = 1.2277 kg → fark yalnız −%1.5 (O/F kaymasının doğal sonucu, hata değil). Toplam itici kütlesi 8.575 kg, I_tot/(g0·Isp) gereksinimi 8.594 kg → %0.2 tutarlı. İleri Euler'in port büyümesini hafif abartması 200+ adımda ihmal edilebilir.

### [x] F135 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
delta_P = 0.2*self.P_c [bar] ; injection_velocity = sqrt(2*delta_P*1e5/rho_ox) [m/s]
```

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 8 (enjektör basınç düşümü ~%20 Pc); sıkıştırılamaz Bernoulli / SPI modeli

**Sayısal etki:** Birim dönüşümü DOĞRU (bar→Pa için 1e5 çarpanı var, sık yapılan 1000x hatası yok). Zarf notu: kendinden basınçlı N2O'da SPI modeli geçersizdir (enjektörde flaşlama/kavitasyon olur, SPI debiyi abartır) — kod bunu biliyor ve gerçek tasarımı Dyer NHNE'ye (injector_design) yönlendiriyor; SPI hızı yalnızca modül patlarsa devreye giren yedek yolda raporlanıyor. Bu doğru bir mimari karar.

### [x] F136 — `hybrid_rocket_engine.py::_design_fuel_grain`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
Blowdown/transient bağlantısı: hibrit tasarım noktası sabit mdot_ox ve sabit Pc varsayar; zamana bağlı çözüm transient_ballistics.py'de RegressionAnalyzer.regression_rate(e.a, e.n, G_ox, ..., flux_mode=e.flux_mode) ile aynı yasayı kullanır
```

**Kaynak:** İki modül arasındaki tutarlılık denetimi (transient_ballistics.py satır ~395-448)

**Sayısal etki:** TUTARLILIK DOĞRULANDI: blowdown/transient çözücü tasarım motorunun a, n, rho_f, L_grain ve flux_mode değerlerini birebir devralıyor ve port büyümesini aynı D += 2·r·dt şemasıyla ilerletiyor — iki yerde farklı regresyon yasası YOK. Bunun bir yan sonucu: yukarıdaki flux_mode='total' taban uyuşmazlığı blowdown çözümüne de aynen aktarılıyor (bağımsız bir hata değil, aynı hatanın taşınması). Tasarım noktasının sabit-Pc olması bir sınırlama olarak dürüstçe ayrı modüle bırakılmış.

### [x] F137 — `hybrid_rocket_engine.py::calculate`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
CD = 0.98 ; self.At = self.mdot_total*self.C_star/(self.P_c*1e5*CD)
```

**Olması gereken:** Yön doğru: gerçek boğazda sınır tabaka tıkanması nedeniyle mdot_gerçek = C_D·Pc·At/c*, dolayısıyla At = mdot·c*/(Pc·C_D) ve C_D<1 boğazı büyütür. İki not: (1) 0.98 değerinin kaynağı kodda yok (tipik aralık 0.97-0.99, geometriye ve boğaz yarıçap oranına bağlı, Sutton Böl. 3); (2) eta_c_star verildiğinde self.C_star ZATEN teslim edilen c*'tır ve teslim c*'ın tanımı Pc·At/mdot olduğundan C_D ile bölmek aynı kaybı ikinci kez sayar.

**Kaynak:** Sutton & Biblarz 9. baskı Böl. 3 (boğaz akış katsayısı); tam 0.98 değeri için kodda kaynak bulunamadı

**Sayısal etki:** Sabit %2.0 boğaz alanı büyütmesi (çapta %1.0). eta_c_star verilmediğinde (varsayılan) çift sayım yok. eta_c_star=0.92 verilirse çift sayılan pay ~%2, yani gerçekleşen Pc talep edilenin ~%2 altına düşer.

### [x] F138 — `kinetic_efficiency.py::KineticEfficiency._evaluate_high_fidelity + _single_gamma_isp`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
v = sqrt(2*(h0 - h_e));  dY_k/dt = wdot_k*W_k/rho;  dh_chem = h(T_e_sh,P_e,Y_kin) - h(T_e_sh,P_e,Y_eq);  v_pred^2 = v_sh^2 - 2*dh_chem
```

**Kaynak:** Sutton & Biblarz 9. baski Es. 3-15b (tek-gamma ideal cikis hizi) — atif dogru; NASA RP-1311 (CEA) enerji yontemi; Bray J. Fluid Mech. 6 (1959) donmus/kayan sinirlari. Tur korunum denklemi standart Lagrange formu.

**Sayısal etki:** Sayisal olarak SINANAMADI — high_fidelity yolu Cantera + gercek bir lule profili gerektiriyor ve bu denetimde tam bir yanma cozumu kosturmadim. Boyut analizi temiz: net_production_rates [kmol/m^3/s] * W [kg/kmol] / rho [kg/m^3] = 1/s (dogru). Enerji yontemi dogru: donmus dal 'equilibrate' cagirmadan gas.SP ile, kayan dal equilibrate('SP') ile ayarlanmis — bu Cantera'da dogru desen. dh_chem'in ayni (T,P) noktasinda alinmasi, dayatilan T(x) profilinin duyulur-isi hatasini kayba karistirmamasi acisindan savunulabilir ve kodda gerekcelendirilmis; birinci-derece yaklasim oldugu belirtilmis. Onemli guvenlik ozelligi: _build_result frozen <= predicted <= shifting koselemesini her seviyede zorluyor.

### [ ] F139 — `nozzle_design.py::_calculate_nozzle_performance`

**Hüküm:** YANLIS_FORMUL · **Görünür:** hayır

**Koddaki denklem:**
```
ve = cf_actual * c_star  →  'exit_velocity': ve
```

**Olması gereken:** cf·c* efektif egzoz hızıdır (c = Isp·g0), çıkış hızı v_e DEĞİLDİR. v_e yalnız momentum teriminden gelir: v_e = cf_momentum·c* (ya da doğrudan v_e = √[2γRT_c/(γ−1)·(1−(p_e/p_c)^((γ−1)/γ))]). İkisi ancak adapte genleşmede (p_e = p_a) eşittir.

**Kaynak:** Sutton & Biblarz 9. baskı Eq. 2-6 (c = Isp·g0) ve Eq. 3-16 (v_2) ayrımı.

**Sayısal etki:** ÖLÇÜLDÜ (γ=1.20, R=350, Tc=3400, Pc=40 bar, p_e=0.4 bar, ambient_pressure=0.0): 'exit_velocity' 2939.0 m/s, gerçek v_e = 2766.2 m/s → +6.2%. Varsayılan yolda (ambient_pressure=None → p_a=p_e) fark TAM SIFIR, ve şu an tek çağıran (hybrid_rocket_engine) ambient_pressure geçmiyor. Yani bugün hatalı sayı üretmiyor, etiket yanlış.

### [x] F140 — `nozzle_design.py::_design_bell_nozzle`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
'length_efficiency': 0.98  (konik 0.95, parabolik 0.96)
```

**Kaynak:** Kaynak bulunamadı. Değerler mertebe olarak makul (bell > parabolik > konik sıralaması doğru) ama 'length_efficiency' literatürde tanımlı bir büyüklük değil; muhtemelen diverjans verimiyle karıştırılmış.

**Sayısal etki:** Ölçülemedi — grep ile taradım, bu anahtarı okuyan hiçbir hesap yok (yalnız contour sözlüğüyle JSON'a giriyor). Sayısal etkisi sıfır; risk, kullanıcının bunu λ sanmasıdır (gerçek λ ayrı hesaplanıyor: bell 0.9951, konik 0.9830, parabolik 0.9924 ölçüldü).

### [x] F141 — `nozzle_design.py::_divergence_efficiency`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
konik: lambda = 0.5·(1 + cos α);  bell/parabolik: lambda = 0.5·(1 + cos θ_e)
```

**Kaynak:** Konik dal: Sutton & Biblarz 9. baskı Eq. 3-34 ve Table 3-3 — atıf DOĞRU, 15°→0.983 tablo değeriyle birebir. Bell dalı için Sutton sec. 3.4'te bu kapalı-form YOKTUR; kod bunu kendi yorumunda zaten itiraf ediyor (θe=8° → 0.995, gerçek %80 Rao bell λ≈0.985-0.99) ve toplam çarpımın legacy 0.98 kalibrasyonuna bağlı olduğunu açıklıyor. Atıf zayıf ama sonuç bilinçli ve belgelenmiş.

**Sayısal etki:** ÖLÇÜLDÜ: konik(15°) λ=0.9830 (Sutton tablosu 0.983 — %0.0 sapma), bell(θe=8°) λ=0.9951, parabolik(θe=10° varsayılan) λ=0.9924. Toplam η_nozzle: konik 0.9683, bell 0.9803, parabolik 0.9776 — bell değeri legacy 0.98 ile %0.03 içinde, kodun iddia ettiği kalibrasyon gerçekten tutuyor. Bell λ'sındaki iyimserlik ~%0.5-1 ama toplam çarpım konservatif bantta kaldığı için net etki küçük.

### [x] F142 — `nozzle_flow_1d.py::NozzleFlow1D._solve_normal_shock + _solve_separation`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
eps_exit_2 = eps_exit * p02_p01 (A_e/A2*); Pe = Pc*p02_p01*(P/P0)|Mexit = Pa cozumu.  Ayrilma: P_cidar(eps) = k*P_ambient, k=0.40
```

**Kaynak:** Anderson, 'Modern Compressible Flow', 3. baski, Bol. 5.4 (quasi-1D sok eslemesi, A2* = A1*.P01/P02). Ayrilma: Summerfield, M., Foster, C.R., Swan, W.C., 'Flow Separation in Overexpanded Supersonic Exhaust Nozzles', Jet Propulsion 24 (1954) — 0.35-0.40 bandi dogru, kod bandin konservatif ucunu (0.40) varsayilan yapmis.

**Sayısal etki:** OLCULDU. Sok dali: Pc=3 bar, eps=4, Pa=2.4 atm icin cozucu M1=1.7191, M2=0.6131 buluyor ve cikis basincini 243180.0 Pa olarak veriyor — hedef geri basinc 243180.0 Pa ile TAM eslesme. Kutle korunumu artigi 2.2e-12. Ayrilma dali: eps=25, Pc=20 bar, deniz seviyesi -> ayrilma duzlemi eps_sep=6.978, P_cidar=40530 Pa = 0.40*101325 (kriter tam saglaniyor). Ayrilmis itki elle dogrulandi: mdot*u_sep + (P_sep-Pa)*A_sep = 2.4989*2441.2 - 833 = 5267 N, kod 5265.6 N. Istasyon kutle korunumu max bagil hata 3.4e-11, cidar-basinci integrali capraz kontrolu %0.35-0.49 (yalnizca ayriklastirma).

### [ ] F143 — `nozzle_flow_1d.py::NozzleFlow1D.solve`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
thrust_effective = thrust * lambda_div * (1.0 - friction_loss_fraction)   [thrust = mdot*u_e + (P_e-P_a)*A_e]
```

**Olması gereken:** Sutton & Biblarz 9. baski Es. 3-34'te dagilma (divergence) faktoru YALNIZCA momentum terimine uygulanir: F = lambda*mdot*v_e + (P_e - P_a)*A_e. Kod lambda'yi (ve surtunme kesrini) basinc terimine de uyguluyor; basinc terimi negatifken (asiri-genisleme) kayip yerine SAHTE KAZANC uretiyor. Dogrusu: thrust_effective = lambda_div*(1-f)*mdot*u_e + (P_e - P_a)*A_e.

**Kaynak:** Sutton & Biblarz, 'Rocket Propulsion Elements', 9. baski, Es. 3-34 (lambda = (1+cos alpha)/2, konik dagilma duzeltmesi momentum itkisine uygulanir); ayni konvansiyon Huzel & Huang NASA SP-125 Bol. 1'de.

**Sayısal etki:** OLCULDU (Pc=70 bar, Tc=3500 K, gamma=1.2, D_t=0.10 m, eps=25, konik 15 derece). Vakum: kod F_eff=98071 N, Sutton formu 98237 N -> -0.169%. Deniz seviyesi (ayrilmis rejim): kod 82435 N, Sutton formu 82161 N -> +0.333%. Yani mertebe %0.2-0.4; buyuk basinc terimli (yuksek eps, vakum) veya siddetli asiri-genisleme durumlarinda %0.5'e kadar cikabilir. Kucuk ama sistematik ve isaret olarak yanlis yonde.

### [ ] F144 — `nozzle_flow_1d.py::NozzleFlow1D.solve`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
REGIME_UNCHOKED dalinda bile istasyon dongusu supersonic=(i > i_t) ile supersonik dali cozmeye devam ediyor
```

**Olması gereken:** _classify_regime dokumantasyonu 'unchoked' icin 'results are limited to the classification' diyor, ama solve() yine de tam supersonik cozumu uretip performance blogunu dolduruyor. Bogulmamis (unchoked) durumda ya cozum reddedilmeli ya da performance alanlari None dondurulmeli.

**Kaynak:** Anderson, 'Modern Compressible Flow', 3. baski, Bol. 5.4 — bogulmamis lulede bogazda M<1 olur, alan-Mach supersonik dali gecersizdir.

**Sayısal etki:** OLCULDU. Pc=1.0 bar, Pa=0.9999 bar, eps=25: regime='unchoked' etiketi dogru ama ayni cikti icinde exit_mach=3.913, mdot=0.1249 kg/s ve thrust = -4546.5 N (NEGATIF ITKI) raporlaniyor. Erisim zorlugu: eps=25 icin Pa/Pc > 0.9997 gerekiyor (cok dar), ama dusuk genisleme oraninda (eps=1.5) esik Pa/Pc > 0.88'e cikar — kuyruk-sonu (tail-off) veya cok dusuk basincli test noktasinda gercekten uretilebilir.

### [x] F145 — `nozzle_flow_1d.py::NozzleFlow1D.solve (Bartz baglantisi)`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
h_g = (0.026/D_t^0.2)*(mu^0.2*cp/Pr^0.6)*(Pc/c*)^0.8*(D_t/R_c)^0.1*(A_t/A)^0.9*sigma;  q = h_g*(Taw - Tw)
```

**Kaynak:** Bartz, D.R., 'A Simple Equation for Rapid Estimation of Rocket Nozzle Convective Heat Transfer Coefficients', Jet Propulsion 27 (1957); Sutton & Biblarz 9. baski Es. 8-22/8-23. Katsayi 0.026 DOGRU (0.023 Dittus-Boelter'dir, Bartz degil). Modul korelasyonu kopyalamiyor, heat_transfer_analysis'ten ithal ediyor — tek kaynak kurali korunmus.

**Sayısal etki:** OLCULDU, BIRIM HATASI YOK. Pc=70 bar, Tc=3500 K, D_t=0.10 m, T_w=800 K: h_g(bogaz)=16484 W/m^2K, q(bogaz)=44.2 MW/m^2, Taw(bogaz)=3480.5 K. Karsilastirma: SSME bogazi (Pc=207 bar) ~80-160 MW/m^2; Pc^0.8 ile 70 bar'a olceklenince ~34-67 MW/m^2 bekleniyor -> 44.2 MW/m^2 dogru mertebede. SI formunda g0 yok, (Pc/c*) dogrudan kg/(m^2.s) veriyor — Pa/(m/s) girildigi teyit edildi (1000x hata YOK). Pr = 4g/(9g-5) = 0.8276, recovery factor r = Pr^(1/3) = 0.9391 — turbulent recovery icin dogru. Taw hicbir istasyonda 800 K'nin altina inmiyor, dolayisiyla Tw=min(Tw, Taw-1) kirpmasi devreye girmiyor.

### [x] F146 — `nozzle_flow_1d.py::isentropic_ratios + area_ratio_from_mach + normal_shock_relations + ideal_thrust_coefficient`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
T/T0=[1+(g-1)/2 M^2]^-1; A/A*=(1/M)[(2/(g+1))(1+(g-1)/2 M^2)]^((g+1)/(2(g-1))); M2^2=[1+(g-1)/2 M1^2]/[g M1^2-(g-1)/2]; CF=sqrt(2g^2/(g-1)(2/(g+1))^((g+1)/(g-1))[1-(Pe/Pc)^((g-1)/g)])+(Pe-Pa)/Pc*eps
```

**Kaynak:** NACA Report 1135 (1953), Tablo I ve II; Anderson, 'Modern Compressible Flow', 3. baski, Es. 3.28-3.31, 3.51, 3.57, 3.63, 5.20; Sutton & Biblarz 9. baski Es. 3-14, 3-30. Koddaki atiflar DOGRU — belirtilen kaynaklarda bu denklemler gercekten var.

**Sayısal etki:** OLCULDU, TAM ESLESME. gamma=1.4 icin NACA 1135 tablosuna karsi: M=2 -> P/P0=0.127805 (tablo 0.12780), A/A*=1.68750 (tablo 1.6875); M=3 -> P/P0=0.027224 (tablo 0.027224), A/A*=4.23457 (tablo 4.2346); M=5 -> A/A*=25.0000 (tablo 25.000). Normal sok M1=2 -> M2=0.57735 / P2P1=4.50000 / P02P01=0.72087 (tablo 0.57735 / 4.5000 / 0.72087); M1=3 -> 0.47519 / 10.3333 / 0.32834 (tablo 0.47519 / 10.333 / 0.32834). 5-6 anlamli basamak tam uyum. CF: cozucunun urettigi CF=1.84238, elle hesaplanan ideal CF=1.84238 (vakum, eps=25, gamma=1.2). Birim sozlesmesi de temiz: pc/pa Pa, T K, capalar m, R_UNIVERSAL/MW[g/mol] dogru sekilde J/(kg.K) veriyor (8314.46/24 = 346.44).

### [x] F147 — `pressurant_sizing.py::blowdown_pressurant`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
P_final = P0*(V_u0/(V_u0+V_p))**n ;  T_final = T0*(P_final/P0)**((n-1)/n) ;  varsayilan polytropic_n=1.2
```

**Olması gereken:** Politropik genişleme denklemleri DOĞRU ve birimleri temiz (P·V^n=sabit ve T·P^((1-n)/n)=sabit ikilisi tutarlı). Eksikler: (a) varsayılan n=1.2 sihirli sayısının kaynağı yok — He için gamma=1.667, N2 için 1.4 olduğuna göre 1.2 makul bir ara değer ama hangi tanka/hangi boşaltma hızına ait olduğu belirtilmemiş; (b) n <= gamma kısıtı doğrulanmıyor, kullanıcı n=1.8 verirse termodinamik olarak imkânsız bir genişleme sessizce kabul ediliyor (yalnız n>0 kontrolü var).

**Kaynak:** Politropik blowdown: Huzel & Huang NASA SP-125 Böl. 5 — atıf yerinde. n=1.2 varsayılanı için kaynak bulunamadı.

**Sayısal etki:** Denklem hatası yok. n duyarlılığı: V_u0=0.3 m3, V_p=0.7 m3, P0=40 bar -> n=1.0'da P_son=12.0 bar, n=1.2'de 9.65 bar, n=1.4'te 7.77 bar. Yani n seçimi son basıncı ±%25 oynatıyor ve blowdown oranı (motor off-design zarfı) doğrudan bundan çıkıyor.

### [ ] F148 — `pressure_vessel.py::_derate_strength`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
if temp_C <= temps[0]: retention = factors[0]  (egrinin en dusuk noktasi, tipik 20 C -> 1.00)
```

**Olması gereken:** Derating egrileri yalnizca YUKSEK sicaklik icin tanimli (20 C'den baslar). Kriyojenik tank analizinde (LOX 90 K, LN2 77 K, LH2 20 K -> -183/-196/-253 C) retention 1.00'a sabitleniyor, yani oda sicakligi ozellikleri kullaniliyor. DAYANIM acisindan konservatif (gercek metaller kriyoda guclenir: Al 2219 ~+%40, SS 304 ~+%80 akma), ama SUNEKLIK/KIRILGANLIK acisindan tehlikeli: ferritik/martenzitik celikler (steel_4130, steel, ss_17_4ph) kriyoda gevrek kirilma yapar ve bu modul hicbir uyari vermez. En azindan T < 200 K icin 'malzeme kriyojenik servise uygunlugu dogrulanmali (DBTT)' uyarisi eklenmeli; ideali kriyo tarafi da olan bir egri.

**Kaynak:** MMPDS / MIL-HDBK-5 dusuk sicaklik bolumleri; ASME BPVC VIII-1 UHA/UCS-66 (dusuk sicaklik darbe testi gerekleri, DBTT). Kod egrisinin kriyo tarafi icin kaynak yok (egri yok).

**Sayısal etki:** OLCULDU. pv.analyze(..., temperature_K=90) -> derating retention 1.00, hicbir uyari uretilmiyor. Dayanim yonunde etki yok/konservatif (gercek kriyo akma daha yuksek), ancak gevrek kirilma riski icin kullanicinin gordugu uyari sayisi = 0. Etki buyuklugu 'guvenlik bildirimi eksigi' kategorisinde, sayisal sapma degil.

### [ ] F149 — `pressure_vessel.py::analyze`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
t_req = max(1.5*P*R/sy, 2.0*P*R/su) ; docstring: 'ince-cidar hoop'tan (sigma = P*r_i/t, ic yaricap — konservatif)'
```

**Olması gereken:** Docstring'in 'ic yaricap — konservatif' iddiasi TERSTIR. sigma = P*r/t'de r buyudukce sigma buyur; r_ic < r_ort < r_dis oldugundan IC yaricap uc secenegin EN AZ konservatif olanidir. Ayni modulun ASME kolu t = P*R/(S*E - 0.6*P) kullaniyor ki bu sigma = P*R/t + 0.6*P'ye denktir, yani ic-yaricap-yalniz formdan daha yuksek gerilme verir. Dogrusu: ortalama yaricap (r_i + t/2) veya ASME formu kullanilmali; en azindan docstring'deki yanlis 'konservatif' iddiasi kaldirilmali.

**Kaynak:** Shigley's Mechanical Engineering Design, ince cidarli basincli kap (ortalama yaricap membran formu); ASME BPVC VIII-1 UG-27(c)(1) (0.6*P terimi ayni etkinin kod karsiligidir).

**Sayısal etki:** OLCULDU (analitik + kod). Sapma = t/(2*r_i). steel_4130 60 bar / D=150 mm oto-boyut: t=1.467 mm, r=75 mm -> gerilme %0.98 az gosteriliyor (ihmal edilebilir). Kalin durumda t/r=0.1 -> %5, t/r=0.2 -> %10 az gosterim. Kucuk ama sistematik ve yanlis yonde; belgelenen iddiayla ters.

### [x] F150 — `pressure_vessel.py::burst_pressure_faupel`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
P_b = (2/sqrt(3))*sigma_y*(2 - sigma_y/sigma_u)*ln(b/a)
```

**Kaynak:** Faupel, J.H., 'Yield and Bursting Characteristics of Heavy-Wall Cylinders', Transactions of the ASME, Vol. 78 (1956), pp. 1031-1064 — atif DOGRU, denklem kaynaktaki formla birebir.

**Sayısal etki:** OLCULDU. steel_4130 (sy=460, su=730 MPa), a=75 mm, t=5 mm: kod 469.594 bar, bagimsiz el hesabim 469.59 bar. Birebir. Ayrica ASME UG-27/UG-32(d)/(e)/(f) formullerini de teker teker dogruladim: 60 bar/D=150/S=208.6 MPa icin silindir t_req=1.467 mm, 2:1 elipsoidal 1.470 mm (silindirle ~esit — 2026-07-16'da bildirilen 'yarimkure formulu 2:1 sanildi' hatasinin duzeldigini teyit ediyor), yarimkure 0.735 mm (tam yarisi, dogru), torisferik 2.602 mm. UG-99(b) hidrotest = 1.3*MAWP*(S_test/S_design) dogru. S = min(su/3.5, sy/1.5) ASME Section II-D (1999+) kriteri dogru.

### [x] F151 — `record_adapters.py::UNIT_TO_SI, split_quantity_key, to_si, convert_block`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
kgf=9.80665, lbf=4.4482216152605, psia=psi=6894.757293168, in=0.0254, in2=0.00064516, atm=101325, gpcc=1000, gpcm2s=10, lbps=lb=0.45359237, kgpm2s=1, mmps=1e-3, cmps=1e-2, inps=0.0254; en uzun sonek önce (_SUFFIXES_BY_LEN)
```

**Kaynak:** BIPM SI Broşürü 9. baskı (g_n = 9.80665 m/s², kgf tanımı); NIST SP 811 Ek B.8 (lbf = 4.448 221 615 260 5 N; lb = 0.453 592 37 kg tam; in = 0.0254 m tam; psi = 6894.757293168 Pa). Türetilenler elle doğrulandı: in² = 0.0254² = 6.4516e-4 m² ✓; 1 g/cm³ = 1000 kg/m³ ✓; 1 g/(cm²·s) = 1e-3 kg / 1e-4 m² / s = 10 kg/(m²·s) ✓.

**Sayısal etki:** Sapma yok — tüm çarpanları tek tek denetledim, hepsi tam. Çakışma riskini de test ettim: sonekler uzunluğa göre azalan sırada denendiği için 'thrust_kgf' -> kgf (kg veya g DEĞİL), 'impulse_lbfs' -> lbfs (lbf/lb DEĞİL), 'throat_area_m2' -> m2 (m DEĞİL), 'rate_mmps' -> mmps (mps/s DEĞİL) doğru ayrışıyor. Sıcaklık için tabloda HİÇ sonek yok (k, c, degc yok) — bu kasıtlı bir boşluk gibi görünüyor ve iyi: sessiz Kelvin/Celsius karışması İMKANSIZ, sıcaklık anahtarları 'unconverted' -> 'unknown_unit' olarak görünür kalıyor. Bilinmeyen sonekli sayı asla 'SI kabul edilip' skorlanmıyor (to_si None döndürüyor) — bu doğru savunmacı davranış.

### [x] F152 — `record_adapters.py::_run_solid / _run_liquid / _run_hybrid / _run_strand (motor arayüzü birim devri)`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
solid: chamber_diameter=d_chamber*1000.0 (m->mm), grain_length=*1000, core_diameter=*1000, chamber_pressure=pc/1e5 (Pa->bar) | liquid: chamber_pressure=pc/1e5 | hybrid: chamber_pressure=pc_bar (bar), atmospheric_pressure=ambient_pa/1e5, predictions['chamber_pressure']=pc_bar*1e5 (bar->Pa) | strand: burn_rate_db.burn_rate_mps(prop_key, pressure) ve yedek r = engine.a * (pressure/1e5)**engine.n
```

**Kaynak:** Motor tarafı sözleşmeleri kodda açık: hrma/data/burn_rate_db.py::burn_rate_mps docstring 'r [m/s] — SI sarmalayıcı (basınç Pa alır)' ve resolve_engine_coeffs docstring 'Motor konvansiyonu (SolidRocketEngine.calculate_burn_rate): r[m/s] = a_engine * (P[bar])^n'. uq_adapters.py::make_solid_factory varsayılanları (chamber_diameter=100, grain_length=500, core_diameter=30 mm; chamber_pressure=40 bar) mm/bar sözleşmesini teyit ediyor.

**Sayısal etki:** Sapma yok. Bu projede daha önce 1000x hatalar bulunduğu için her devri ayrı denetledim: convert_block çıktısı HER ZAMAN SI (m, Pa) — katı motoruna mm/bar, sıvı ve hibrite bar veriliyor; ölçümle karşılaştırılan tahminler (chamber_pressure) tekrar Pa'ya çevriliyor, dolayısıyla measured_si (Pa) ile aynı boyutta. Strand yolunda iki farklı a-n sözleşmesi var (DB: r[mm/s]=a*(P[MPa])^n, motor: r[m/s]=a*(P[bar])^n) ve kod her birine DOĞRU birimi veriyor — burn_rate_mps'e Pa, motor yedeğine pressure/1e5 (bar). Yanlış olsaydı 10^0.35 = 2.24 kat (%124) hata görünürdü; koşuda solid burn_rate medAPE %0.51 çıkması bu zincirin tutarlı olduğunu ayrıca teyit ediyor.

### [x] F153 — `regen_cooling.py::RP1_COKING_TEMP_K / jackson_nu / pseudocritical_temperature`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
RP1_COKING_TEMP_K = 561.0 K ; Nu_b = 0.0183 Re_b^0.82 Pr_b^0.5 (rho_w/rho_b)^0.3 (cp_bar/cp_b)^n
```

**Kaynak:** RP-1 koklaşma eşiği 561 K = 550 °F, Huzel & Huang Böl. 4 ile örtüşüyor. Jackson & Hall (1979), Kakac & Spalding (ed.), Turbulent Forced Convection in Channels and Bundles Cilt 2; Jackson (2013) Nucl. Eng. Des. 264 — katsayı 0.0183 ve üsler (0.82 / 0.5 / 0.3) kaynakla birebir. Metan/hidrojen için CoolProp zorunlu tutulması ve tablo/sabit değere düşmeyi reddetmesi 'asla uydurma' ilkesiyle tutarlı.

**Sayısal etki:** Jackson Nu elle doğrulandı (yukarıda). cp_bar = (h_w - h_b)/(T_w - T_b) entegre ortalama tanımı doğru; pseudo-kritik arama kaba ızgara + altın oran ile bimodal cp(T) tuzağına karşı korumalı — bu detay doğru düşünülmüş. ParaHydrogen seçimi (normal H2 değil) roket LH2'si için doğru (NBP'de >%99 para). Entalpi tabanlı marş (h2=h1+dQ/mdot, T=T(P,h)) pseudo-kritik cp tepesinde dT=dQ/(m*cp) formundan üstün — doğru tercih.

### [ ] F154 — `regen_cooling.py::dittus_boelter_nu`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
Geçerlilik: Re>=1e4, 0.6<=Pr<=160, L/D>=10 — kodda yalnız Re taraması var (min_re < RE_TURBULENT_FLOOR uyarısı)
```

**Olması gereken:** Prandtl bandı ve giriş-uzunluğu (L/D>=10) koşulu da taranmalı; ayrıca büyük cidar/yığın özellik farkında Dittus-Boelter'in bilinen sapması için Sieder-Tate (mu_b/mu_w)^0.14 düzeltmesi yoksa bu açıkça model notunda niceliksel olarak belirtilmeli.

**Kaynak:** Incropera & DeWitt 6. baskı Eq. 8.60 geçerlilik notu; korelasyonun bildirilen saçılımı ~+/-%25.

**Sayısal etki:** Test ettiğim çalışma noktalarında Pr zarf İÇİNDE kaldı: su 0.96-1.34, RP-1 5.6 (500 K) - 22.8 (290 K), hepsi 0.6-160 bandında. Yani pratikte tetiklenmesi zor bir eksik; asıl belirsizlik korelasyonun kendi +/-%25 saçılımı ve Sieder-Tate düzeltmesinin yokluğu (yüksek akılı roket kanalında h_c'yi tipik olarak %10-20 etkiler). Modül bunu 'approximate' etiketiyle dürüstçe beyan ediyor.

### [x] F155 — `regen_cooling.py::dittus_boelter_nu / hydraulic_diameter_rect / haaland_friction_factor / darcy_weisbach_dp / acceleration_dp / fin_area_ratio`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
Nu=0.023Re^0.8Pr^0.4 ; D_h=2wh/(w+h) ; 1/sqrt(f)=-1.8log10(6.9/Re+(e/D/3.7)^1.11) ; dP=f(L/D)(rho V^2/2) ; dP_acc=G^2(1/rho_out-1/rho_in) ; A_eff/A=(w+2*eta*h)/pitch, eta=tanh(mL)/mL, m=sqrt(2h_c/(k*t_land))
```

**Kaynak:** Incropera & DeWitt 6. baskı Eq. 8.60 (Dittus-Boelter, n=0.4 ısıtma) ve Böl. 3.6 Eq. 3.85-3.86 (düz dikdörtgen fin, adyabatik uç); White, Fluid Mechanics 7. baskı Eq. 6.10/6.12/6.49 (Darcy-Weisbach, laminer 64/Re, Haaland); Collier & Thome 3. baskı Böl. 2 (ivmelenme terimi); Huzel & Huang Böl. 4 (kanal sırtları fin olarak). Atıfların hepsi gerçek ve formüller kaynakla örtüşüyor.

**Sayısal etki:** HEPSİNİ SAYISAL SINADIM. D_h(2x2 mm)=2.000 mm ✓. Nu(Re=1e5,Pr=5)=437.840 — elle 437.840 ✓. Haaland(Re=1e5, pürüzsüz)=0.017825 vs Blasius 0.316Re^-0.25=0.017770 -> %0.31 fark (Haaland'ın ilan edilen ~%2 doğruluğu içinde) ✓. Laminer f(Re=1000)=0.0640=64/1000 ✓. Jackson Nu(Re=1e5,Pr=2,oranlar=1,n=0.4)=325.811 — elle 0.0183*1e5^0.82*2^0.5=325.811 ✓. fin_area_ratio elle hesapla birebir (eta=0.7568) ✓. acceleration_dp elle birebir ✓. jackson_exponent_n parçalı formu Jackson & Hall 1979 ile örtüşüyor ve rejim sınırlarında sürekli.

### [x] F156 — `regen_cooling.py::solve`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
dQ = q*dA ; dT = dQ/(mdot_total*cp) ; q = (Taw - T_c)/(1/h_g + t_w/k_w + 1/h_c)
```

**Kaynak:** Huzel & Huang Böl. 4 (bir boyutlu cidar direnç devresi + istasyon entalpi dengesi); Sutton & Biblarz Böl. 8.

**Sayısal etki:** ENERJİ KORUNUMUNU ÖLÇTÜM: 60 bar / bakır astar / 100 kanal / su testinde mdot*cp_mean*dT = 2692.123 kW, total_heat_W = 2692.123 kW — makine hassasiyetinde kapanıyor ✓. Fiziksel sonuçlar da tutarlı: tepe akı 35.5 MW/m^2 (60 bar için literatür bandı 25-40), max cidar 947 K, dP=2.86 bar, min Re=2.08e4 (türbülan tabanın üstünde). dA gaz tarafı çevresi üzerinden, dT toplam mdot ile — konvansiyon tutarlı (kanal başına bölme hatası YOK). Boğaz istasyonu ızgaraya kesin oturuyor (M=1 tam yakalanıyor).

### [x] F157 — `regression_analysis.py::LIQUEFYING_FUELS`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
LIQUEFYING_FUELS = {'paraffin': {'entrainment_in_correlation': True}}  # hesapta EK entrainment çarpanı UYGULANMIYOR
```

**Kaynak:** Karabeyoglu, Altman & Cantwell, JPP 18(3) 2002 (entrainment teorisi); Karabeyoglu et al., JPP 20(6) 2004 (SP-1a a/n ölçümleri — deneysel fit entrainment'i zaten içerir); Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2

**Sayısal etki:** AMPİRİK OLARAK DOĞRULANDI. Karar (deneysel a/n zaten entrainment'i içerdiği için ek çarpan uygulamamak) doğrulama verisinde teyit ediliyor: parafin alt kümesi n=17, bias +%9.4, medAPE %6.9 — DB'deki en iyi hibrit performansı. Birim dönüşümü de doğru: a=0.488 (mm/s, g/cm²s) → 0.488e-3·10^-0.62 = 1.171e-4 SI, kod 1.17e-4. TEK SINIRLAMA (bulgu değil, zarf notu): saf güç yasasının Pc bağımlılığı yoktur; entrainment sürüklenen sıvı tabakanın dinamik basıncına bağlı olduğu için parafin korelasyonu farklı Pc'ye ekstrapole edilirken bu sapma modellenmiyor. HTPB gibi eriyen olmayan yakıtlarda Pc bağımsızlığı zaten doğru fizik.

### [ ] F158 — `regression_analysis.py::analyze_regression_vs_time`

**Hüküm:** YANLIS_FORMUL · **Görünür:** evet

**Koddaki denklem:**
```
dt = burn_time/(time_steps-1) ; for t in time_array: ... ; if t < burn_time - dt: port_radius += r_dot*dt
```

**Olması gereken:** 100 noktalı linspace(0, t_b) ızgarasında son noktaya ulaşmak için 99 güncelleme gerekir; koşul t < t_b − dt yalnız 98 güncelleme yaptırıyor (son iki nokta özdeş çıkıyor). Koşul 't < burn_time - dt/2' ya da index tabanlı 'i < time_steps-1' olmalı.

**Kaynak:** Sayısal integrasyon ızgara tutarlılığı (iç tutarsızlık, harici kaynak gerekmiyor)

**Sayısal etki:** ÖLÇÜLDÜ. mdot_ox=0.7 kg/s, D_i=50 mm, t_b=10 s, HTPB, flux_mode='ox': modül D_final=66.119 mm veriyor, 100 000 adımlı referans integrasyon 66.239 mm. Çapta −%0.18, BÜYÜME PAYINDA −%0.74 hata. Yalnız /api/regression-analysis grafiğini etkiler, tasarım zincirini etkilemez.

### [ ] F159 — `regression_analysis.py::compare_fuel_types`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
conditions = base_conditions.copy(); conditions['regression_a']=...; conditions['regression_n']=...  # fuel_density GÜNCELLENMİYOR
```

**Olması gereken:** analyze_regression_vs_time, rho_f'yi önce motor_data['fuel_density']'den okur. Karşılaştırma çağrısında base_conditions içinde bir fuel_density varsa (ör. parafin 900 kg/m³), PMMA (1180) ve ABS (1050) eğrileri de o yoğunlukla çizilir. conditions['fuel_density'] = fuel_props['density'] de atanmalı.

**Kaynak:** Modülün kendi yakıt tablosuyla tutarsızlık (iç tutarsızlık)

**Sayısal etki:** HESAPLANDI (analitik). Etki yalnız flux_mode='total' modunda var (G_fuel ∝ rho_f). Parafin↔PMMA arasındaki %31 yoğunluk hatası, G_fuel/G_total≈0.14 tipik payında G_total'i ~%4.3, r_dot'u ~%2.4 kaydırır. flux_mode='ox' modunda etki sıfır. Yalnız karşılaştırma grafiğini etkiler.

### [x] F160 — `regression_analysis.py::regression_rate`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
sabit-nokta: r_new = a*(G_ox + rho_f*pi*D*L*r_dot/A_port)^n, |r_new-r_dot| <= tol*max(r_new,1e-12) ile durma, yakınsamazsa RuntimeWarning
```

**Kaynak:** Sabit-nokta yakınsama koşulu (Banach): |dF/dr| = n·G_fuel/G_total < 1

**Sayısal etki:** ANALİTİK OLARAK DOĞRULANDI. İterasyon fonksiyonunun türevi n·G_fuel/G_total'dir; tablodaki tüm yakıtlarda n ≤ 0.62 < 1 ve G_fuel/G_total < 1 olduğundan iterasyon KOŞULSUZ yakınsar (tipik 3-6 adım). n>1 durumunda ıraksama mümkündür ve kod bunu sessiz geçmeyip uyarıyor — doğru davranış. Bağıl tolerans kullanımı da doğru (mutlak tolerans SI'da r~1e-3 m/s için anlamsız olurdu).

### [x] F161 — `six_dof_trajectory.py::BarrowmanAero.__init__`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
cn_fins = 4n(s/d)²/(1+sqrt(1+(2·l_mid/(cr+ct))²)) · (1 + R/(s+R)) ; xcp_rel = m(cr+2ct)/(3(cr+ct)) + (1/6)(cr+ct−cr·ct/(cr+ct)) ; burun C_Nα=2, x_cp: konik 2/3·Ln, ogive 0.466·Ln, parabolik 0.5·Ln
```

**Kaynak:** Barrowman 1967, 'The Practical Calculation of the Aerodynamic Characteristics of Slender Finned Vehicles'; OpenRocket Technical Documentation (Niskanen 2009) Barrowman bölümü. Gövde-kanat girişim faktörü K_fb = 1 + R/(s+R) ve orta-veter hattı l = sqrt(s² + (m+(ct−cr)/2)²) standart ifadeler.

**Sayısal etki:** ELDE DOĞRULANDI (d=0.15, Ln=0.5 ogive, L=2.5, n=4, cr=0.20, ct=0.10, s=0.08, sweep=0.10): elde hesap C_Nα = 5.09595 /rad, x_cp = 1.53939 m; kod 5.0959 ve 1.5394 → 5 anlamlı hanede aynı. Ara adımlar da uyuştu (l_mid=0.094340, girişim 1.483871). Referans alan S_ref = πd²/4 doğru. NOT: 's' EXPOSED YARI-AÇIKLIK olarak kullanılıyor; çağıranlar (app.py, sixdof_panel.js çizimi R+fin_span, ork_import 'height') hepsi yarı-açıklık veriyor — tutarlı.

### [ ] F162 — `six_dof_trajectory.py::SixDOFTrajectory._inertia`

**Hüküm:** YANLIS_FORMUL · **Görünür:** hayır

**Koddaki denklem:**
```
I_t = m * (3.0*r*r + self.aero.L ** 2) / 12.0   (components=None dalı)
```

**Olması gereken:** Bu ifade tekdüze silindirin GEOMETRİK MERKEZİNDEN geçen enine atalet momentidir; oysa Euler denklemi ve momentler CG etrafında yazılıyor (r_cp_b = x_cp − x_cg). Paralel eksen terimi eksik: I_t(cg) = m(3r²+L²)/12 + m·(x_cg − L/2)². Varsayılan x_cg_full = 0.55·L ile bu terim m·(0.05L)² kadardır.

**Kaynak:** Paralel eksen (Huygens-Steiner) teoremi; tekdüze silindir atalet momenti standart tablo.

**Sayısal etki:** HESAPLANDI: x_cg = 0.55L'de eksik terim = m·L²·0.0025, ana terim m·L²/12 = m·L²·0.0833 → I_t %3.0 eksik. Pitch doğal frekansı ∝ 1/sqrt(I_t) → %1.5 yüksek. Uçuş çıktısında ölçülebilir etki görülmedi (apoje/max_alpha değişimi gürültü seviyesinde).

### [ ] F163 — `six_dof_trajectory.py::SixDOFTrajectory.solve`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
max_alpha = alpha_arr[burn_mask].max()  — alpha yalnız çözücü çıktı noktalarında örnekleniyor (dense_output=False)
```

**Olması gereken:** max_alpha SÜREKLİ maksimum değil, adım noktalarındaki ÖRNEKLENMİŞ maksimumdur. Pitch doğal periyodu bu araçta ~0.5 s; varsayılan max_step=0.1 s ile periyot başına ~5 örnek düşer, tepe kaçabilir. 'stable' hükmü (max_alpha < 15°) bu değere bağlı.

**Kaynak:** Sayısal örnekleme; scipy solve_ivp dense_output belgeleri.

**Sayısal etki:** ÖLÇÜLDÜ: aynı senaryoda max_step=0.2 → 1.212°, 0.05 → 1.401°, 0.02 → 1.394° (adım değişimiyle %15 saçılma). Apoje çok daha kararlı (%0.06 saçılma). Tipik marjda (α≈1-3° vs eşik 15°) hüküm değişmiyor; kararsızlığa yakın araçlarda değiştirebilir.

### [x] F164 — `six_dof_trajectory.py::SixDOFTrajectory.solve`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
solve_ivp(RK45, max_step=0.1, rtol=1e-5, atol=1e-7) + hit_ground/apogee/tumble olayları
```

**Kaynak:** Dormand-Prince RK45 (scipy); enerji korunumu testi standart entegratör doğrulaması.

**Sayısal etki:** ENERJİ KORUNUMU ÖLÇÜLDÜ: sürükleme kapalı (cd0=0), yanma sonrası serbest uçuşta özgül enerji E = ½v² − μ/(R+z) izlendi → bağıl sapma 7.45e-9 (574 adım, ~4 km apoje, 11.8 km'lik dik senaryoda). Ters-kare potansiyelle tutarlı, entegratör toleransları yeterli. Adım duyarlılığı: max_step 0.2/0.05/0.02 için apoje 3978.87/3979.52/3977.28 m (%0.06 saçılma) — apoje adımdan bağımsız. Restoratif aerodinamik moment de analitikle tam 1.0000 oranında (işaret doğru: burun bağıl rüzgâra dönüyor).

### [ ] F165 — `six_dof_trajectory.py::_atmosphere`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** hayır

**Koddaki denklem:**
```
H = h * R_EARTH / (R_EARTH + h)   (R_EARTH = 6_371_000)
```

**Olması gereken:** USSA 1976 geopotansiyel dönüşümü R = 6 356 766 m (etkin yarıçap) kullanır; kardeş trajectory_analysis._atm_full bunu doğru yapıyor (self.R_geopotential = 6356766.0). 6-DOF ortalama Dünya yarıçapını kullanıyor.

**Kaynak:** U.S. Standard Atmosphere 1976, geopotansiyel yükseklik tanımı (r0 = 6 356 766 m).

**Sayısal etki:** ÖLÇÜLDÜ ve İHMAL EDİLEBİLİR: 47 km'de geopotansiyel farkı ~0.4 m. Yoğunluk her iki modülde de USSA 1976 tablosuna %0.008 içinde uyuyor (0-47 km, geopotansiyel referansla). Sadece tutarlılık (kural #11) meselesi.

### [x] F166 — `six_dof_trajectory.py::_atmosphere`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
USSA 1976 katman formülleri: lapse≠0 → P = P_b(T/T_b)^(−g0/(L·R)); lapse=0 → P = P_b·exp(−g0(H−H_b)/(R·T_b)); rho = P/(R·T); a = sqrt(γRT)
```

**Kaynak:** U.S. Standard Atmosphere 1976, Denk. 33a/33b; ISA_LAYERS tablosu hrma/constants.py'de doğru (0/11/20/32/47/51/71 km, lapse ve taban basınçları tabloyla uyumlu).

**Sayısal etki:** SAYISAL OLARAK DOĞRULANDI (geopotansiyel referansla): H=0/11/20/32/47 km'de yoğunluk hatası sırasıyla −%0.000/−%0.001/−%0.002/−%0.006/−%0.008. Kardeş trajectory_analysis._atm_full aynı doğrulukta. Ses hızı da tablo değerleriyle %0.03 içinde. Tablo üstü izotermal uzantı ve T≥150 K / P≥1e-9 tabanları negatif/NaN'ı doğru engelliyor.

### [ ] F167 — `six_dof_trajectory.py::_coriolis_acceleration`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
(N,E,U) sol-elli çerçevesi için np.cross geçici (E,N,U) sağ-elli çerçevede yapılıyor — YALNIZ Coriolis için
```

**Olması gereken:** Docstring'in kendi tespiti doğru: (N,E,U) sıralaması sol-ellidir (N×E = −U). Ancak bu düzeltme SADECE ötelemeli Coriolis terimine uygulandı; modülün geri kalanı (M_b = np.cross(r_cp_b, F_n_b), w_dot'taki np.cross(w_b, I·w_b), _quat_derivative, _quat_to_dcm) sağ-elli çapraz çarpım varsayımını sürdürüyor. Yani dönme dinamiği hâlâ ayna-görüntüsü bir dünyada, öteleme Coriolis'i ise gerçek dünyada hesaplanıyor. Tutarlı çözüm: çerçeveyi baştan (E,N,U) yapmak.

**Kaynak:** Vektör analizi: sol-elli ortonormal tabanda (a×b) bileşenleri = −np.cross(a,b).

**Sayısal etki:** ÖLÇÜLEMEYECEK KADAR KÜÇÜK, gerekçesi analitik: roll hiç uyarılmıyor (p(0)=0, tek roll terimi −k·p sönümü) → p≡0 → ω×Iω = 0 özdeş olarak sıfır; pitch/yaw problemi düzlemsel alt-problem olduğu için ayna simetriktir. Coriolis kaynaklı yanal hız (~1 m/s) ile aero tutum kuplajının düzlem-dışı bileşeni ikinci mertebe. Doğrulama testlerimde tespit edilebilir sapma çıkmadı. Bilinçli borç olarak kaydedilmeli; kanat cant/roll tahriki eklenirse GERÇEK hataya dönüşür.

### [x] F168 — `six_dof_trajectory.py::_coriolis_acceleration`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
a = −2·Ω×v, Ω_(E,N,U) = Ω_E·(0, cosφ, sinφ), Ω_E = 7.292115e-5 rad/s
```

**Kaynak:** IERS Konvansiyonları 2010 (ω_E = 7.292115e-5 rad/s); dönen çerçeve fiktif ivme tanımı (Goldstein, 'Classical Mechanics'). launch_site.py::OMEGA_EARTH ile aynı değer, teyit edildi.

**Sayısal etki:** DÖRT YÖN TESTİ GEÇTİ: (1) ekvatorda dik atış (v=300 m/s yukarı) → a_E = −0.04375 m/s² (BATI), klasik sonuçla ve 2Ωv = 0.04375 büyüklüğüyle birebir; (2) 45°K doğuya → güneye 0.0309 + yukarı 0.0309 (Eötvös terimi dahil, hareketin SAĞINA sapma); (3) 45°K kuzeye → doğuya 0.0309 (yine sağa); (4) 45°G doğuya → kuzeye (SOLA), güney yarımküre işareti doğru. Bağımsız yazdığım referans hesapla 1e-9 içinde aynı. Kutupta dik atışta 0.000 m (Ω∥v) — doğru.

### [x] F169 — `six_dof_trajectory.py::_quat_derivative`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
q̇ = ½·[−xp−y·qy−zr, wp+yr−z·qy, w·qy+zp−xr, wr+x·qy−yp]
```

**Kaynak:** Hamilton quaternion kinematiği; skaler-önce, gövde→atalet quaternion'u için q̇ = ½·q⊗[0,ω_b] (Kuipers, 'Quaternions and Rotation Sequences'; Markley & Crassidis, 'Fundamentals of Spacecraft Attitude Determination and Control').

**Sayısal etki:** SAYISAL OLARAK TEYİT EDİLDİ: sonlu farkla (dt=1e-6) C(q+q̇dt) hesaplanıp beklenen C₀·(I+[ω]ₓdt) ile karşılaştırıldı → ‖fark‖ = 5.5e-13 (yuvarlama seviyesi). Ters sıra (½·ω⊗q) karşılığı ‖fark‖ = 8.9e-7, yani 6 mertebe kötü. 2026-07-13 düzeltmesi DOĞRU ve hâlâ yerinde. _quat_to_dcm de gövde→atalet yönünde tutarlı.

### [x] F170 — `slosh_analysis.py::CylindricalTankSlosh.natural_frequency + slosh_mass_ratio + pendulum_length`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
omega_n^2 = (lambda_n*g_eff/R)*tanh(lambda_n*h/R);  m_1/m_liq = (2R/(lambda_1*h*(lambda_1^2-1)))*tanh(lambda_1*h/R);  l_1 = g_eff/omega_1^2
```

**Kaynak:** Abramson, H.N. (ed.), 'The Dynamic Behavior of Liquids in Moving Containers', NASA SP-106 (1966), Bol. 2; Dodge, F.T., 'The New Dynamic Behavior of Liquids in Moving Containers', SwRI (2000), Bol. 1. Modal kokler (J1'(x)=0) dogru.

**Sayısal etki:** OLCULDU. SLOSH_ROOTS = (1.8412, 5.3314, 8.5363, 11.7060); scipy.special.jnp_zeros(1,4) = (1.84118378, 5.33144277, 8.53631637, 11.7060049) — 5 basamak tam. Kutle orani h/R=1'de 0.4322; Dodge doluluk grafigi ~0.43 (kodun kendi docstring capasi) — teyitli. Frekans R=1 m, h=2 m, g=9.80665: f1=0.6759 Hz (el hesabi omega=4.2465). Sig doldurma limitinde oran 2/(lambda^2-1)=0.837'ye asimptot ediyor, 1'i asmiyor — fiziksel. Pendulum uzunlugu g/omega^2 = R/(lambda*tanh(lambda h/R)) ile ozdes. g_eff dokumantasyonu da dogru: ucusta ozgul kuvvet T/m'dir.

### [x] F171 — `slosh_analysis.py::CylindricalTankSlosh.recommend_baffle`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
note: 'add baffles spaced ~1 radius apart down the tank'
```

**Olması gereken:** Literatur silindirik tanklar icin s <= 0.2R bafl araligi oneriyor, ~1R degil. Kodun kendi kullandigi exp(-4.6*d/R) sonum yasasi bunu zaten ima ediyor: d/R = 1'de exp(-4.6) = 0.010, yani yuzeyden bir yaricap asagidaki bafl, yuzey baflinin ancak %1'i kadar sonumleme verir. '~1 yaricap arali' oneri, tank bosalirken sonumlemede neredeyse tam bir bosluk birakir.

**Kaynak:** NASA 20130000590 (Validation of Slosh Model Parameters and Anti-Slosh Baffle Designs, 27th Aerospace Testing Seminar 2012), Abramson 1969'a atifla: 'For the commonly used cylindrical tank, a good design principle is spacing the ring baffles at a distance s <= 0.2R'. Ayrica Bauer MTP-AERO-62-81 (1962) coklu-bafl formulu exp[-4.6(d/a + (n-1)D/a)].

**Sayısal etki:** Sayisal hesap degil, tasarim onerisi metni — ama kodun kendi denklemi uzerinden olculebilir: d/R=1'de sonum carpani exp(-4.6)=0.010; d/R=0.2'de exp(-0.92)=0.399. Yani onerilen aralikta ikinci bafl birinciden ~40x daha az etkili, literatur araliginda ise ~2.5x daha az. Kullaniciya gosterilen 'note' alaninda.

### [x] F172 — `solid_rocket_engine.py::SOLID_DESIGN_POINT bates_core_factor / bates_web_factor (4.0 / 3.0)`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
L_seg = 4·r_core + 3·web  (orta-web nötrlük ailesi)
```

**Kaynak:** NASA SP-8064 BATES nötrlük analizi; Sutton & Biblarz Böl. 12.

**Sayısal etki:** ANALİTİK OLARAK DOĞRULANDI, sapma yok. A(w) = 2π(r_0+w)(L_0−2w) + 2π(R²−(r_0+w)²) → dA/dw = 2π(L_0 − 4r_0 − 6w). Web ortasında (w = W/2) dA/dw = 0 koşulu → L_0 = 4r_0 + 3W. Koddaki 4.0 ve 3.0 katsayıları bu türevle BİREBİR aynı; yuvarlanmış ya da uydurulmuş bir 'yaklaşık nötr' değil, tam çözüm.

### [x] F173 — `solid_rocket_engine.py::_calculate_grain_structural`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
σ_r = K[D − C2(1−2ν)/r²] − T0 ;  σ_θ = K[D + C2(1−2ν)/r²] − T0 ;  K = E/((1+ν)(1−2ν)) ;  T0 = E·α·ΔT/(1−2ν) ;  σ_z = ν(σ_r+σ_θ) − E·α·ΔT ;  u(b) = P·b²/(E_kasa·t)
```

**Kaynak:** Timoshenko & Goodier, 'Theory of Elasticity' (kalın cidarlı silindir + üniform sıcaklık, düzlem şekil değiştirme); NASA SP-8073 (kabul ölçütü gerinim kabiliyeti).

**Sayısal etki:** TERİM TERİM DOĞRULANDI, sapma yok. Lamé + termal düzlem-şekil-değiştirme çözümünden yeniden türettim: σ_r = 2D(λ+μ) − 2μC2/r² − T0 ile λ+μ = E/(2(1+ν)(1−2ν)) → 2D(λ+μ) = K·D ✓ ve 2μ = E/(1+ν) → K(1−2ν) ✓. Sınır koşullarının cebirsel çözümü de doğru: C2 = b·u_kasa − D·b², denom = K(1 + (1−2ν)(b/a)²) — elle çözdüğüm ifadeyle birebir. σ_z için ε_z = 0 koşulu doğru uygulanmış. bore_strain = u(a)/a gerçekten port yüzeyi hoop gerinimidir ve kabul ölçütü gerilme değil GERİNİM üzerinden veriliyor — SP-8073'e uygun. Kt = 2.0 keskin köşe yığılması 'çözülmemiş köşe yarıçapı' notuyla açıkça beyan ediliyor.

### [ ] F174 — `solid_rocket_engine.py::_estimate_expansion_ratio (ortam basıncı sabit kodlanmış)`

**Hüküm:** YANLIS_KATSAYI · **Görünür:** evet

**Koddaki denklem:**
```
P_atm = 1.01325  # bar\n        Pe_Pc = P_atm / self.P_c
```

**Olması gereken:** self.ambient_pressure_bar kullanılmalı (kullanıcı test_altitude / atm_pressure girdiğinde _apply_overrides bunu zaten kuruyor ve _thrust_coefficient ile _calculate_theoretical_isp onu KULLANIYOR). Ayrıca modülde SEA_LEVEL_PRESSURE_BAR sabiti tanımlıyken burada 1.01325 tekrar sabit yazılmış (magic number tekrarı).

**Kaynak:** İç tutarlılık: aynı dosyadaki _thrust_coefficient ve _calculate_theoretical_isp getattr(self,'ambient_pressure_bar',...) okuyor.

**Sayısal etki:** ÖLÇÜLDÜ: test_altitude=5000 m (Pa=0.5402 bar) → CF = 1.5842 (0.54 bar'da optimum genişlemeye karşılık gelen ε = 9.48'i varsayar) ama raporlanan/CAD'e giden genişleme oranı ε = 5.932 (deniz seviyesi) kalıyor. Yani itki, imal edilecek nozuldan 1.6 kat büyük bir ε'nun performansıyla hesaplanıyor; gerçek ε=5.93 nozulun 5000 m'deki CF'i ≈ 1.549, yani itki ~%2.2 iyimser. Deniz seviyesinde (varsayılan) sapma 0.00%.

### [x] F175 — `solid_rocket_engine.py::_isp_loss_breakdown (iki-fazlı akış kaybı)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
two_phase_losses = 100.0 * TWO_PHASE_LOSS_COEFF * x_particle   (k = 0.12);  X_p(apcp) = 0.18 * 101.96/(2*26.98) = 0.3401;  'two_phase_losses_applied': False
```

**Olması gereken:** Stokiyometri DOĞRU: 2Al + 3/2 O2 → Al2O3, kütle oranı 101.96/(2·26.98) = 1.8895, ürün kütlesi = yakıt kütlesi olduğundan X_Al2O3 = 0.18·1.8895 = 0.3401 — birebir doğru. Sorun ikili: (a) η = 1 − k·X_p lineer formunun ve k=0.12'nin kaynağı yok; nozzle_design.py'nin kendi yorumu bunu 'k≈0.12 bu aralığı verir' diye GERİYE DÖNÜK uydurulmuş bir uydurma-katsayı olarak beyan ediyor, dolayısıyla docstring'deki 'Sutton & Biblarz sec. 3.5' atfı forma değil yalnız olguya aittir. (b) Kayıp yalnız RAPORLANIYOR, itki katsayısına UYGULANMIYOR ('applied: False'), yani metalize APCP'nin partikül-gecikme kaybı teslim edilen Isp'ye hiç girmiyor.

**Kaynak:** Stokiyometri: standart atom kütleleri (Al 26.98, Al2O3 101.96) — DOĞRU. Kayıp formu ve k=0.12 için kaynak bulunamadı; Sutton & Biblarz sec. 3.5 iki-fazlı akış kaybının varlığını ve mertebesini (%1-4) verir ama bu lineer bağıntıyı vermez.

**Sayısal etki:** ÖLÇÜLDÜ: APCP için raporlanan two_phase_losses = 100·0.12·0.3401 = %4.08; şeker (X_p=0.44) %5.28; siyah barut (X_p=0.55) %6.60. Mertebe literatür bandının (%1-4 metalize kompozit) üst ucunda, yani makul. Uygulanmadığı için teslim edilen Isp bu kadar iyimser kalıyor — ancak UI varsayılanı nozzle_efficiency=0.95 (tablo değeri 0.985 yerine) zaten %3.5 ek kayıp getirdiğinden net etki büyük ölçüde örtülüyor.

### [x] F176 — `solid_rocket_engine.py::burn_rate (yüksek basınç plato düzeltmesi)`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
if pressure > 100: pressure_plateau = 1.0 - 0.02 * np.log10(pressure / 100)  # yorum: 'verified from test data'
```

**Olması gereken:** Belirsiz. Plato/mesa davranışı gerçektir ama (a) tek bir logaritmik form TÜM yakıtlara ayrımsız uygulanıyor (plato göstermeyen AP/HTPB dahil), (b) 0.02 katsayısının ve 100 bar kırılma noktasının kaynağı belirtilmemiş, (c) 'verified from test data' hangi test olduğunu söylemiyor. Doğrulanamadığı için DÜŞÜK ciddiyette bırakıyorum — düzeltmeden önce kaynağın bulunması gerekir, körlemesine kaldırılmamalı.

**Kaynak:** kaynak bulunamadı

**Sayısal etki:** ÖLÇÜLDÜ: 150 bar'da çarpan 0.9965 (-0.35%), 200 bar'da 0.9940 (-0.60%), 500 bar'da 0.9860 (-1.4%). app.py Pc'yi 200 bar'la sınırladığından pratik etki her koşulda %0.6'nın altında — yani kaynaksız olsa bile zararı ihmal edilebilir düzeyde.

### [x] F177 — `solid_rocket_engine.py::calculate_burn_area (BATES) + _propellant_volume`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
A_core = n·2π·r_i·L_seg ;  A_ends = n·2π·(r_o²−r_i²) ;  r_i = r_0+w, L_seg = L/n − 2w
```

**Kaynak:** NASA SP-8064 'Solid Propellant Grain Design and Internal Ballistics'; Sutton & Biblarz 9. baskı Böl. 12 (BATES geometrisi).

**Sayısal etki:** DOĞRULANDI. Analitik: V(w) = n·π(r_o²−r_i²)(L/n−2w) → −dV/dw = n·2π·r_i·L_seg + n·2π(r_o²−r_i²) = A_core + A_ends, yani kütle korunumu ÖZDEŞ olarak sağlanıyor. Sayısal ölçüm (100/500/30 mm, APCP), yakılan/mevcut kütle oranı: bates 0.9986, star 0.9985, wagon_wheel 0.9971, finocyl 0.9998, slotted 0.9968, end_burner 1.0000 — altı grain tipinin hepsinde sapma < %0.35 (kalan sapma dt=0.01 s ayrıklaştırmasından).

### [x] F178 — `solid_rocket_engine.py::calculate_thrust_curve (denge basıncı çözümü) + _design_health_warnings (n≥1)`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
P_new [bar] = ρ_p · A_b · r(Pc) · c* / (A_t · 1e5);  A_t = ṁ_tasarım · c* / (Pc_tasarım · 1e5);  n ≥ 1.0 → 'critical' uyarı
```

**Kaynak:** Sutton & Biblarz 9. baskı Denk. 12-6 (Kn denge basıncı); NASA SP-8089.

**Sayısal etki:** DOĞRULANDI. Türev doğru: ρ_p·A_b·a·Pc^n = Pc·A_t/c* → Pc^(1-n) = Kn·a·ρ_p·c* → Pc = (Kn·a·ρ_p·c*)^(1/(1-n)) — docstring'deki formla birebir. Boyut analizi temiz: kg/s · m/s / m² = Pa, ÷1e5 → bar; A_t = kg/s · m/s / Pa = m². Kapalı form yerine sönümlü sabit-nokta (0.5 gevşetme) kullanılması n<1'de daralma garantisi verir ve sıcaklık/plato/erozif düzeltmelerini denge çözümünün İÇİNE alır — kapalı formdan daha doğrudur. n≥1 tekilliği 'critical' uyarıyla açıkça yakalanıyor (app.py n'yi 1.0'a kadar kabul ettiği için bu uyarı gerçekten gerekli) ve yakınsamama artık sabit True yerine gerçek durumla raporlanıyor.

### [ ] F179 — `solid_rocket_engine.py::calculate_thrust_curve (sahte grain sıcaklık evrimi)`

**Hüküm:** YANLIS_FORMUL · **Görünür:** hayır

**Koddaki denklem:**
```
heat_transfer_rate = 0.001  # Simplified coefficient\n                current_temp += heat_transfer_rate * dt\n                current_temp = min(current_temp, self.T_c * 0.5)
```

**Olması gereken:** Bu bir model değil, birimsiz bir sihirli sayıdır: 0.001 hangi büyüklük (K/s? W/m²K?) belli değil, hiçbir kütle/ısı kapasitesi/geometri girmiyor ve T_c/2 tavanı fiziksel bir anlam taşımıyor. Grain kütlesinin ortalama sıcaklığı yanma süresince pratik olarak DEĞİŞMEZ (ısı nüfuz derinliği ~0.1 mm); ya blok tamamen kaldırılmalı ya da gerçek bir yüzey ısıl dalga modeliyle değiştirilmeli.

**Kaynak:** kaynak bulunamadı

**Sayısal etki:** ÖLÇÜLDÜ: dt=0.01 s ile adım başına +1e-5 K; 27.5 s'lik end-burner koşusunda toplam +0.0275 K. σ_p=0.002 ile yanma hızına etkisi 5.5e-5 bağıl (%0.006). Sayısal olarak ZARARSIZ; sorun uydurma bir 'fizik' bloğunun kodda durması.

### [x] F180 — `structural_analysis.py::_analyze_chamber_wall`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
thin: sigma = P*r/t ; t/r >= 0.1 ise Lame: sigma_hoop(ic) = P*(b^2+a^2)/(b^2-a^2), pressure_hoop = max(thin, lame) ; kalin rejimde 3-eksenli von Mises sigma_r = -P ile
```

**Kaynak:** Lame (1833); Timoshenko & Goodier 'Theory of Elasticity' Art.28; Roark's Formulas for Stress and Strain 9th ed. Tablo 13.5 (kalin silindir, ic basinc, ic yuzey hoop = P*(b^2+a^2)/(b^2-a^2)) — atif ve denklem birebir uyusuyor. Ince/kalin esigi t/r<0.1 (D/t>20) Shigley/Roark standardi.

**Sayısal etki:** OLCULDU, DOGRU CALISIYOR. D=150 mm steel_4130: Pc=50 bar -> t/r=0.0785, model='thin_wall'; Pc=100 bar -> t/r=0.157, model='lame_thick_wall', hoop 95.54 -> 103.59 MPa (Lame %8.4 daha yuksek, konservatif yonde secilmis); Pc=500 bar -> t/r=0.785, hoop 143.61 MPa. Zarf ihlali YOK: t/r>=0.1'de ince cidar formulu SESSIZCE kullanilmiyor, otomatik Lame'ye geciliyor ve max() ile daima buyuk olan aliniyor. Kalin rejimde von Mises'in 3-eksenli (sigma_r=-P dahil) forma gecmesi de dogru ve konservatif. TEK KUCUK NOT: kalin rejimde boylamsal gerilme hala ince-cidar formuyle (P*r/2t) aliniyor; kapali-uc kalin silindir icin dogrusu P*a^2/(b^2-a^2) (t/r=0.314'te %15 fark) — bu fark von Mises'i biraz YUKARI ittigi icin konservatif, duzeltilmesi opsiyonel.

### [ ] F181 — `structural_analysis.py::_analyze_fatigue`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
f_frac = 0.9 ; a_basq = (f*S_u)^2/S_e ; b_basq = -log10(f*S_u/S_e)/3 ; N = (sigma_ar/a)^(1/b)
```

**Olması gereken:** Shigley Fig. 6-18'de f faktoru S_ut'ye baglidir: S_ut <= 70 kpsi (~483 MPa) icin f ~ 0.9, 100 kpsi (~690 MPa) icin f ~ 0.82, 200 kpsi icin f ~ 0.77. Kod f=0.9'u SABIT kullaniyor ve bunu docstring'de kabul ediyor ('S_u <= ~490 MPa icin 0.9'), ama zarf zorlanmiyor: steel_4130 (S_u=730 MPa), inconel_718, titanium gibi yuksek dayanimli malzemelerde f ~0.77-0.79 olmali. f fazla alinmasi sonlu omru FAZLA gosterir (non-konservatif). Ayrica S_e olarak materials_db'nin duzeltilmemis 'fatigue_limit' degeri kullaniliyor — Shigley Eq. 6-46'daki S_e DUZELTILMIS dayanim sinirdir (Marin k_a yuzey, k_b boyut, k_c yuk, k_d sicaklik, k_e guvenilirlik carpanlari); ozellikle k_d (sicaklik) bu modulde zaten hesaplanan retention faktoruyle baglanabilirdi.

**Kaynak:** Shigley's Mechanical Engineering Design 10th ed. Fig. 6-18 (f-S_ut egrisi), Eq. 6-14/6-15 (Basquin a,b), Eq. 6-46 (Goodman), Sec. 6-9 (Marin faktorleri). Goodman ve Basquin denklemlerinin kendileri DOGRU yazilmis.

**Sayısal etki:** OLCULDU. steel_4130 (S_u=730 MPa, S_e=230 MPa): sigma_ar=300 MPa icin f=0.9 -> N=1.74e5 cevrim, f=0.79 -> N=1.36e5 (1.28x fazla gosterim). sigma_ar=400 MPa icin f=0.9 -> N=2.62e4, f=0.79 -> N=1.56e4 (1.68x fazla gosterim). Etki yalnizca n_f<1 dalinda (sonlu omur) gorunur. AYRICA TEYIT: 2026-07-14'te bildirilen MPa/Pa 1e6 birim hatasinin gercekten duzeldigini dogruladim (hoop 58.78 MPa girdi -> max_stress 58.78 MPa, fatigue_limit 230 MPa, SF=5.95 — tutarli).

### [x] F182 — `structural_analysis.py::_analyze_nozzle_structure`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
stress_concentration_factor = 2.0 if nozzle_type == 'conical' else 1.5
```

**Olması gereken:** Yigilma faktorunun 2.0/1.5 degerleri icin kodda Peterson'a atif var ama Peterson'da 'konik nozul bogazi = 2.0' diye bir tablo girdisi YOKTUR; Peterson'daki K_t degerleri belirli geometrik detaylara (omuz filetosu r/d ve D/d oranlari) baglidir. Buyukluk mertebesi makul (ic basincli kabuk gecis bolgesi K_t tipik 1.5-3.0) ama sayilar gercek geometriden (yakinsak koni acisi, bogaz filetosu yaricapi R_c/R_t) turetilmiyor. Dogrusu: K_t'yi bogaz filetosu yaricapi oraniyla parametrelestirmek (Peterson Ch.3 kabuk-gecisi grafikleri) veya nozul geometrisinden hesaplanan degeri kullanmak; degilse 'approximate, geometriden bagimsiz varsayim' diye acikca beyan etmek.

**Kaynak:** kaynak bulunamadi (kodda 'Peterson Stress Concentration Factors' atfi var ancak bu spesifik 2.0/1.5 degerlerinin Peterson'daki karsiligini dogrulayamadim).

**Sayısal etki:** Sayisal etki OLCULEMEDI cunku SF zaten tautolojik (bulgu #3): SCF hem gerekli kalinligi hem etkin gerilmeyi ayni katsayiyla carptigi icin raporlanan nozzle safety_factor'da TAMAMEN sadelesiyor (SCF 1.5 ve 2.0 icin de safety_factor=4.0000). Etki yalnizca 'required_throat_thickness' ciktisinda: 2.0 vs 1.5 -> onerilen bogaz kalinligi %33 farkli. Tautoloji giderildikten SONRA bu katsayi SF'yi dogrudan etkileyecegi icin o an kaynaklandirilmasi zorunlu hale gelir.

### [x] F183 — `structural_analysis.py::_thermal_hoop_stress`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
sigma_thermal = E*alpha*delta_T/(2*(1-nu))
```

**Kaynak:** Timoshenko & Goodier 'Theory of Elasticity' (uzun silindir, eksenel kisitli, lineer radyal gradyan); Boley & Weiner 'Theory of Thermal Stresses' Ch.10-11; Roark's 9th ed. Ch.16 — atif dogru, klasik yuzey degeri dogru yazilmis (2 carpani paydada, dis yuzde cekme). 2026'daki 'konservatiflik icin 2'yi dusurme' hatasinin gercekten geri alindigini dogruladim.

**Sayısal etki:** OLCULDU. steel_4130 (E=200 GPa, alpha=12.3e-6, nu=0.27), dT=300 K: kod 505.5 MPa; el hesabi 200e9*12.3e-6*300/(2*0.73) = 505.5 MPa. Birebir. Birimler tutarli (Pa cikti, K girdi).

### [ ] F184 — `tank_blowdown.py::N2OSaturation._interp (ve step'teki bant kenetlemesi)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
T = float(np.clip(T, _T_MIN, _T_MAX))  # 240-306 K, sessiz ;  step(): 'if f_lo > 0: self.T = T_lo' (uyarı yok)
```

**Olması gereken:** Model bandı docstring'de dürüstçe ilan edilmiş (240-306 K) ama bandın dışına çıkıldığında SESSİZCE kenetleniyor — ne uyarı üretiliyor ne de durum sözlüğünde bir bayrak var. Kenetlendiği anda raporlanan basınç (240 K'de 11.88 bar) artık fiziksel değil, bant tabanının değeri. En az bir 'out_of_band' bayrağı state sözlüğüne eklenmeli.

**Kaynak:** Geçerlilik bandının kendisi kaynaklı (gömülü tablo 240-306 K; N2O kritik nokta 309.52 K, NIST). Eksik olan zarf ihlalinin raporlanması.

**Sayısal etki:** Normal senaryoda (293 K başlangıç, tam sıvı boşaltma -> 273.7 K) bant tabanına HİÇ ulaşılmıyor, yani sıvı fazında pratik etkisi yok. Bant ihlali esas olarak buhar (kuyruk) fazında oluşuyor ve bu ayrı bir bulgu olarak raporlandı. Ölçülen: T_init=253 K senaryosunda sıvı fazı bandın içinde kalıyor, taşma yalnız buhar fazında.

### [x] F185 — `tank_blowdown.py::N2OTankBlowdown.from_oxidizer_mass`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
tank_volume = (oxidizer_mass / rho_l) / liquid_fill_fraction
```

**Olması gereken:** Denklem kendi tanımı içinde doğru ama 'oxidizer_mass' burada YÜKLENEN TOPLAM N2O değil, yalnız SIVI kütlesidir; ullage'daki buhar sayılmıyor. Kullanıcı 'yükleyeceğim oksitleyici' diye toplam kütleyi verirse tank o oranda küçük boyutlanır. Ya parametre adı liquid_mass olmalı ya da hacim m_toplam = V·(f·rho_l + (1-f)·rho_v) denkleminden çözülmeli.

**Kaynak:** Kaynak gerekmeyen basit hacim muhasebesi; buhar yoğunluğu değerleri CoolProp/NIST.

**Sayısal etki:** ÖLÇÜLDÜ: 16.5 kg sıvı, 293.15 K, %85 dolum -> V=0.02473 m3, ullage buharı m_v0=0.586 kg. Yani gerçek toplam yük 17.086 kg; kullanıcı 16.5 kg'ı TOPLAM sanırsa tank %3.4-3.6 küçük çıkar. Yüksek sıcaklıkta daha da büyür (306 K'de rho_v=271 kg/m3 -> ~%9).

### [x] F186 — `tank_blowdown.py::N2OTankBlowdown.step ve ::_split_masses ve ::_SAT_TABLE`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
U_target = (m_l*u_l + m_v*u_v) - dm*h_l ;  m_l = (V - m*v_v)/(v_l - v_v)
```

**Kaynak:** Denge (equilibrium) iki-faz blowdown modeli: Whitmore & Chandler, Journal of Propulsion and Power 27(4), 2011; Zilliac & Karabeyoglu AIAA 2005-3549. Enerji dengesi dU/dt = -mdot·h_l (sıvı çıkışı doygun sıvı entalpisiyle ayrılır) standarttır ve kodda birebir uygulanmış. Hacim kısıtından m_l türetimi cebirsel olarak doğrulandı.

**Sayısal etki:** SAYISAL OLARAK DOĞRULANDI. (1) Gömülü doygunluk tablosunun 23 satırının tamamı CoolProp/Span-Wagner ile karşılaştırıldı: Psat, rho_l, rho_v, h_l, u_l sapması %0.000 — tablo gerçekten CoolProp'tan üretilmiş, uydurma değil. Psat(293.15 K)=50.53 bar (docstring 50.5 diyor, DOĞRU). (2) Kütle korunumu: 16.5 kg N2O, mdot=1.2 kg/s, 14 s -> m_baş=17.0859 kg, m_son+çekilen=17.0899 kg, hata %0.023. (3) Fizik trendi: 293.15 K / 50.5 bar -> sıvı bitiminde 273.7 K / 31.7 bar, dT=-19.5 K — literatürdeki tam boşaltma için tipik 15-25 K soğuma bandıyla uyumlu.

### [ ] F187 — `tank_blowdown.py::N2O_GAMMA_VAPOR`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** evet

**Koddaki denklem:**
```
N2O_GAMMA_VAPOR = 1.27  # buhar fazı adyabatik üssü
```

**Olması gereken:** 1.27 değeri N2O'nun İDEAL GAZ gamma'sıdır (doğrulandı: CoolProp cp/cv @300 K, 1 bar = 1.279). Ancak kullanıldığı yer 293 K / 50 bar doygun buhardır; orada gerçek cp/cv = 3.11. İdeal gaz varsayımı bu noktada da tutmuyor: doygun buhar yoğunluğu 158 kg/m3, ideal gaz p/(RT) ise 91 kg/m3 (%42 sapma). Kuyruk tahmini olduğu docstring'de yazıyor ama sayısal geçersizliğin boyutu belirtilmemiş.

**Kaynak:** CoolProp 6.8.0 (N2O: Lemmon & Span 2006 EOS); ideal gaz gamma doğrulaması aynı kaynaktan.

**Sayısal etki:** ÖLÇÜLDÜ: gamma_ideal=1.279, gamma_gerçek(293 K doygun buhar)=3.107 (2.4 kat). Yalnız sıvı tükendikten SONRAKİ kuyruk fazını etkiler; hibrit tasarımında sıvı tükenmesi fiilen yanma sonu olduğu için tasarım noktası sonuçlarına etkisi yok.

### [x] F188 — `thermal_protection.py::ablative_thickness`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
s_dot = q_net/(rho*Q*) ; toplam gerileme = (integral q dt)/(rho*Q*) ; gereken = toplam * design_margin
```

**Olması gereken:** Model denklemi standart ve doğru; sorun Q* BANTLARININ kaynağında. Silika-fenolik için verilen 8-12 MJ/kg bandını birincil kaynakta (NASA SP-8091 veya Sutton Böl. 8.5) doğrulayamadım. Yaygın olarak alıntılanan etkin ablasyon ısısı değerleri ~2000-5000 Btu/lbm = 4.6-11.6 MJ/kg aralığındadır; bu doğruysa bandın 'konservatif alt ucu' olarak sunulan 8 MJ/kg aslında konservatif OLMAYABİLİR. Ayrıca Q* malzeme sabiti değildir — yerel entalpi farkına (h_r - h_w) ve üfleme etkisine güçlü bağlıdır; tek sayı kullanımı Seviye-1 modeldir (modül bunu doğru şekilde beyan ediyor).

**Kaynak:** Denklem: NASA SP-8091 sınıfı ablatif boyutlandırma / Sutton & Biblarz 9. baskı Böl. 8.5 (etkin ablasyon ısısı kavramı) — GERÇEK ve uygun atıf. Q* sayısal bantları (8-12 / 25-30 / 4-6 MJ/kg) için kaynak bulunamadı; kodun kendisi de yalnız 'literature band' diyor, sayfa/tablo vermiyor.

**Sayısal etki:** ÖLÇTÜM: q=5 MW/m^2, 10 s, silika-fenolik (rho=1400 merkezi DB'den, Q*=8 MJ/kg) -> s_dot = 0.446 mm/s, toplam 4.46 mm, 1.5 payla 6.70 mm. Karbon-fenolik -> 0.138 mm/s. Her ikisi de KTİ nozul ablasyonu için yayımlanmış bantlarla (silika-fenolik ~0.2-0.5 mm/s, karbon-fenolik ~0.05-0.2 mm/s) uyumlu, yani sonuçlar makul. Birim denetimi temiz: [W/m^2]/([kg/m^3][J/kg]) = m/s ✓. Q* bandı alt ucu 4.6 MJ/kg olsaydı gerileme 1.74x artardı — bu belirsizlik tasarım payının (1.5) içinde ERİMEZ.

### [x] F189 — `thermal_protection.py::heat_sink_transient`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
Tn[0] = T[0] + 2Fo(T1-T0) + 2Fo*Bi*(Tr-T0) ; Tn[i]=T[i]+Fo(T[i+1]-2T[i]+T[i-1]) ; Tn[-1]=T[-1]+2Fo(T[-2]-T[-1]) ; dt = cfl*dx^2/(2*alpha*(1+Bi))
```

**Kaynak:** Incropera & DeWitt 6. baskı §5.10, Tablo 5.3 (açık FD düğüm denklemleri ve kararlılık ölçütleri: iç düğüm Fo<=1/2, taşınımlı yüzey düğümü Fo(1+Bi)<=1/2). Atıf ile ayrıklaştırma birebir örtüşüyor; Bi = h*dx/k ağ Biot sayısı doğru tanımlanmış.

**Sayısal etki:** ANALİTİK DOĞRULAMA YAPTIM (en güçlü sonuç): kalın çelik cidar (50 mm, yarı-sonsuz rejim), h=5000 W/m^2K, Tr=3000 K, t=2 s için FD iç yüzey = 1373.33 K, Carslaw & Jaeger / Incropera Eq. 5.63 kapalı çözümü = 1373.31 K -> sıcaklık yükselişi üzerinden %0.00 sapma. Enerji dengesi de kapanıyor: soğurulan 1.914e7 J/m^2, depolanan 1.914e7 J/m^2, fark %0.00 (yarım-hücre ağırlıkları doğru). Şema, kararlılık kelepçesi ve enerji korunumu TEMİZ.

### [x] F190 — `transient_ballistics.py::ThroatErosionModel.rate_m_s / rate_mm_s + TransientBallistics.solve (erozyon kuplajı)`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
ṙ[mm/s] = a_ref·(Pc[bar]/70)^0.8 ;  rate_m_s(Pc_pa) = rate_mm_s(Pc_pa/1e5)/1000 ;  d_throat += 2·ṙ·dt ;  total_recession = (d_son − d_ilk)/2
```

**Kaynak:** Bartz 1957 (h_g ∝ (Pc/c*)^0.8 → difüzyon-kontrollü oksidasyonda Pc^0.8 ölçeklemesi); Thakre & Yang, J. Prop. Power 24(4), 2008; Geisler AIAA grafit bandı.

**Sayısal etki:** BİRİM DENETİMİ TEMİZ, sapma yok. Pa→bar dönüşümü ÷1e5 doğru (1 bar = 1e5 Pa), mm/s→m/s ÷1000 doğru. ṙ yarıçap gerilemesi olduğundan çapa 2·ṙ·dt eklenmesi doğru, geri okumada da /2 ile yarıçapa dönülüyor — tutarlı. Pc^0.8 üssünün Bartz'a dayandırılması fiziksel olarak savunulabilir (difüzyon-sınırlı erozyon konvektif taşınımla ölçeklenir). a_ref bantları 'approximate, ±%50 saçılım normaldir' diye AÇIKÇA beyan edilmiş ve varsayılan bandın konservatif üst ucundan seçilmiş — dürüst. Çelik/bakır için katsayı uydurmak yerine ValueError atılması doğru davranış. TransientBallistics.solve içindeki C_F = λ·C_F,mom + ε·Pe/Pc − ε·Pa/Pc formu da Sutton Denk. 3-30/3-31 ile birebir (λ yalnız momentum terimine uygulanmış — doğru pratik).

### [x] F191 — `uncertainty.py::_stats_block`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
std = float(np.std(arr))   # ddof=0 (popülasyon standart sapması)
```

**Olması gereken:** MC örneklerinden dağılım genişliği kestirilirken yansız kestirici ddof=1'dir (Bessel düzeltmesi). ddof=0 kullanımı std'yi sistematik olarak düşük gösterir. Kod bunu bilinçli bir seçim olarak (mevcut solid run_monte_carlo._stats kalıbıyla uyum) docstring'de bildiriyor.

**Kaynak:** Standart istatistik (Bessel düzeltmesi). Koddaki gerekçe: uncertainty.py::_stats_block docstring 'Mevcut solid run_monte_carlo._stats kalibinin genellestirilmis halidir (std ddof=0 ayni sekilde)'.

**Sayısal etki:** ÖLÇÜLDÜ: n=200'de ddof=0 std, ddof=1'e göre -%0.25 düşük (0.924480 vs 0.926800). n=1000'de -%0.05, n=3000'de -%0.017. Pratikte önemsiz; bu listede yer alması yalnız tamlık için. cv_percent aynı oranda etkileniyor.

### [ ] F192 — `uncertainty.py::sample_inputs (nominal_first bloğu)`

**Hüküm:** GECERSIZ_ZARF · **Görünür:** hayır

**Koddaki denklem:**
```
if nominal_first: for j, name in enumerate(names): X[0, j] = distributions[name].nominal_value()   — LHS matrisinin 0. satırı ÜZERİNE yazılıyor
```

**Olması gereken:** Latin Hypercube'ün tanımı: her boyut n tabakaya bölünür ve HER tabakadan tam bir örnek alınır. 0. satırın üzerine nominal vektör yazılması, o satırın işgal ettiği tabakayı boşaltır ve merkez bölgeyi ikinci kez doldurur — yani örnek artık kesin LHS değildir, marjinal tabakalama bozulur. Doğrusu: nominal vektör LHS matrisine EK satır olarak (n+1 satır) konulup istatistikten dışlanmalı, ya da bozulma her koşuda ölçülüp raporlanmalı. Not: bu, spec 7.3 determinizm garantisi için bilinçli bir takas ve docstring'de açıkça yazılı — gizli değil.

**Kaynak:** McKay, Beckman & Conover, 'A Comparison of Three Methods for Selecting Values of Input Variables in the Analysis of Output from a Computer Code', Technometrics 21(2), 1979 (LHS tanımı: boyut başına n tabaka, tabaka başına bir örnek).

**Sayısal etki:** ÖLÇÜLDÜ (hibrit dağılımları, regression_lambda sütunu, seed=7): n=200 (FAST varsayılan) -> atılan LHS örneği 1.19549 yerine 1.0 kondu; sütun ortalaması 1.000143 -> 0.999165 (-%0.098), sütun std'si 0.145630 -> 0.144970 (-%0.45). n=1000 -> ortalama -%0.0056, std -%0.0075. Yani etki 1/n ile sönüyor ve Engineering/High-Fidelity'de ihmal edilebilir; yalnız Fast modda binde bir mertebesinde, sistematik olarak nominale doğru çekiyor ve dağılımı hafifçe daraltıyor. Tasarım takası olarak kabul edilebilir; belgelenmiş.

### [x] F193 — `uncertainty.py::spearman_sensitivity (yöntem seçimi ve Sobol'un yokluğu)`

**Hüküm:** DOGRU · **Görünür:** hayır

**Koddaki denklem:**
```
spearmanr(col, y) -> |rho| azalan sıralı liste + _SENSITIVITY_METHOD_NOTE ('captures monotonic effects only')
```

**Kaynak:** Spearman sıra korelasyonunun tarama amaçlı duyarlılık ölçütü olarak kullanımı standarttır: Saltelli et al., 'Global Sensitivity Analysis: The Primer', Wiley 2008, Böl. 1-2 (korelasyon tabanlı ölçütler monotonik/tarama düzeyi; varyans-tabanlı Sobol için Saltelli şeması N(d+2) model koşusu gerektirir — kodun Sobol'u kapsam dışı bırakma gerekçesi bu kaynakla birebir doğru).

**Sayısal etki:** Sapma yok. Hesabın kendisi doğru: sabit sütun/çıktı için rho=0 temizliği doğru, NaN yakalama doğru, scipy'nin hem yeni (res.statistic) hem eski (res.correlation) arayüzü ele alınmış. Monotonik-olmayan etkileşimleri kaçırdığı method_note ile DÜRÜSTÇE raporlanıyor ve Sobol'un neden dahil edilmediği doğru gerekçeyle yazılmış — bu, bu dosyadaki en dürüst bölümlerden biri. TEK KUSUR ayrı bulgu olarak listelendi (LHS dekorelasyonu yokluğundan gelen gürültü tabanı raporlanmıyor); yöntemin kendisi doğru.

### [x] F194 — `water_hammer.py::WaterHammerAnalyzer.analyze`

**Hüküm:** KAYNAKSIZ_AMA_DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
p_yield = sigma_y * t_wall / r_i   (docstring: 'ic yaricap konservatif')
```

**Olması gereken:** Formulun kendisi standart ince-cidar hoop bagintisi (sigma = P*r/t) ve dogru. ANCAK docstring'deki 'ic yaricap konservatif' iddiasi TERS: sigma = P*r/t'te daha BUYUK r daha buyuk gerilme => daha konservatif. r_i, r_ortalama ve r_dis arasindan EN AZ konservatif olanidir (en yuksek izin verilen basinci verir). Barlow / ASME B31.3 dis capi kullanir. Iddia ya duzeltilmeli ya da r_o'ya gecilmeli. (Not: 'pressure_vessel.py ile ayni gelenek' iddiasi DOGRU — o modul de r_i kullanip ayni sekilde 'konservatif' diyor, yani hata paylasilan bir etiket hatasi.)

**Kaynak:** Shigley's Mechanical Engineering Design, Bol. 3 (ince cidarli basincli kaplar); ASME B31.3 / Barlow formulu P = 2*S*t/D_dis.

**Sayısal etki:** OLCULDU. ss_304, D_i=500 mm, t=5 mm (t/r_i=0.02): kod hoop akma basinci 43.00 bar; Barlow (dis cap) 42.16 bar -> kod %2.0 daha az konservatif. Hata buyuklugu tam olarak t/r_i kadar; modulun ince-cidar gecerlilik sinirinda (t/r_i=0.1) %10'a cikar. Kucuk, ama emniyet hukmunu (SAFE/MARGINAL sinirini) hafifce yanlis tarafa kaydirir ve docstring iddiasi yanilticidir.

### [x] F195 — `water_hammer.py::wave_speed + joukowsky_pressure_rise + critical_closure_time + slow_closure_pressure_rise`

**Hüküm:** DOGRU · **Görünür:** evet

**Koddaki denklem:**
```
a = sqrt(K/rho)/sqrt(1 + K*D/(E*t));  dP = rho*a*dv;  t_c = 2L/a;  dP_slow = dP*(t_c/t_close) = 2*rho*L*dv/t_close
```

**Kaynak:** Wylie, E.B. & Streeter, V.L., 'Fluid Transients', McGraw-Hill (1978), Bol. 1 (Es. 1-6, 1-10); Halliwell, A.R., ASCE J. Hydraulics Div. 89 (1963); Michaud (1878) / Allievi (1902) yavas kapanma. Koddaki atiflar dogru; restraint faktoru c1=1 varsayimi acikca belgelenmis.

**Sayısal etki:** OLCULDU. Su/celik klasik ornek (K=2.19 GPa, rho=998, D=0.5 m, t=5 mm, E=207 GPa): kod a_elastic=1032.6 m/s, a_rigid=1481.3 m/s — elle hesap 1481/sqrt(2.058)=1032.4 ile uyumlu; literatur su/celik bandi 1000-1200 m/s. dP/dv = 20.24 bar / 2 m/s = 10.1 bar per m/s — su/celik icin klasik ~10 bar/(m/s) parmak hesabiyla tam uyum. Yavas kapanma: t_close=5 s icin kod 4.790 bar, kapali form 2*998*600*2/5/1e5 = 4.790 bar — TAM eslesme. Sivi tablosu da tutarli: K ve rho'dan turetilen ses hizlari (su 1481, N2O 492, RP-1 1267, LOX 888 m/s) her sivinin kendi 'source' alanindaki bantlarin icinde.


---

## Ajan kapsam beyanları

> DENETLENEN (sayisal olarak calistirilarak): 
> 
> structural_analysis.py — analyze_structure, _analyze_chamber_wall (ince/kalin cidar secimi, Lame, von Mises 2D+3D, iki-SF raporu), _thermal_hoop_stress, _estimate_wall_delta_T (sabit-nokta enerji dengesi dahil), _derate_strength (interpolasyon + uc nokta klamplari), _check_buckling (SP-8007 uc denklemi + uygulanan yuk), _analyze_nozzle_structure, _analyze_end_caps, _analyze_fasteners, _analyze_fatigue (Goodman + Basquin), _calculate_weight, _analyze_safety_factors (SF sepeti, termal marj, oneri kodlari), WALL_TEMP_SERVICE_FRACTION sabiti.
> 
> pressure_vessel.py — analyze (her iki code_mode), _derate_strength, _asme_allowable, _head_thicknesses (UG-32 d/e/f), burst_pressure_faupel, burst_pressure_thin_wall, _validate_inputs, oto-boyutlandirma dali, durum esikleri.
> 
> bolted_joint.py — _bolt_class_props (dort sinif), THREAD_STRESS_AREA_MM2 (12 boy), preload, torque, stiffness (Wileman), analyze (Eq. 8-24...8-30), analyze_bolted_joint sarmalayicisi.
> 
> Ek olarak baglam icin OKUDUM (denetim kapsaminda degil ama birim/zincir dogrulamasi icin gerekliydi): hrma/data/materials_db.py (steel_4130, steel, ss_304, ss_316, aluminum_6061 kayitlari ve derating egrileri), hrma/app.py'nin iki cagirici ucu (satir ~2356 ve ~3656), hrma/engines/hybrid_rocket_engine.py struct_input kurulumu.
> 
> DOGRULAMA YONTEMI: Fonksiyonlari gercekten import edip calistirdim. Referans motor: D_hazne=150 mm, L=500 mm, d_bogaz=50 mm, steel_4130; Pc taramasi 5-500 bar; malzeme taramasi 5 malzeme; cidar sicakligi senaryolari (verilmemis / chamber_temperature=3200 K / gercek 800-500 K rejeneratif / 860-560 K servis-siniri asimi). Denklemleri bagimsiz el hesabiyla karsilastirdim (Faupel, Wileman k_m, Shigley n_p/n_L/n_0, termal hoop, UG-27). Civata torklarini yayimlanmis 8.8 sinifi tork tablosuyla karsilastirdim (sapma +0.9...+2.3%). Gecici betikler scratchpad'de: /private/tmp/claude-501/-Users-apple-Desktop-dosyalar-HRMA/de50138d-c13a-49d0-b62c-0c3699c94c32/scratchpad/t1.py ... t5.py. HICBIR PROJE DOSYASINI DEGISTIRMEDIM.
> 
> DENETLEYEMEDIGIM / EKSIK BIRAKTIGIM:
> 1. SCF 2.0/1.5 degerlerinin Peterson'daki tam karsiligini kitaba erisimim olmadigi icin dogrulayamadim — 'kaynak bulunamadi' olarak isaretledim, YANLIS_KATSAYI demedim.
> 2. materials_db'deki dayanim/derating VERILERININ kendilerini (yield 460 MPa, fatigue_limit 230 MPa, derating egrisi noktalari) MMPDS/MatWeb kaynaklarina karsi tek tek dogrulamadim — kapsamim uc dosyadaki DENKLEMLERDI, veri katmani degil. Sadece fatigue_limit'in Shigley'in 0.5*Su kuralindan dusuk (0.315*Su) oldugunu, yani konservatif oldugunu not ettim.
> 3. bolted_joint.py'de DIS SIYIRMA (thread stripping) kontrolu HIC YOK — dis kavrama boyu (L_e), ic/dis dis kesme alanlari (ASME B1.1 / FED-STD-H28 formulleri) ve alt malzeme dayaniminin civata dayanimina orani hesaplanmiyor. Yumusak malzemeye (aluminum_6061 uye, S_u=310 MPa) sikilan 12.9 sinifi civatada (S_u=1220 MPa) sıyırma birincil kirilma modudur ve modul bunu gormez. Bu bir YANLIS DENKLEM degil, EKSIK DENKLEMDIR — findings'e uydurma bir verdict ile koymadim, burada bildiriyorum.
> 4. bolted_joint.py'de CIVATA YORULMASI yok (Shigley Sec. 8-11: sigma_a = C*P/(2*A_t), sigma_i = F_i/A_t, Goodman ile n_f). Basincli kap civatasi her ateslemede cevrim gorur; hazne cidari icin yorulma hesaplanirken civata icin hesaplanmamasi tutarsiz. Yine EKSIK, yanlis degil.
> 5. Kaldirma (prying) etkisi, kesme yuku, contali baglanti (soft gasket) ve flans donmesi bolted_joint kapsaminda degil — modul bunlari 'assumptions' listesinde DURUSTCE beyan ediyor, bu yuzden bulgu saymadim.
> 6. six_dof, heat_transfer gibi bu uc dosyaya cidar sicakligi besleyen modullerin kendi dogrulugunu denetlemedim (kapsam disi); yalnizca anahtar sozlesmesinin (wall_temperature_hot/cold) tutarli aktigini dogruladim.
> 7. 'thrust' anahtarinin frontend'den gelirken N mi kN mi oldugunu izleyemedim (uretim yolunda hic gecilmiyor, bu yuzden su an etkisiz); burkulma canlandirilirsa bu birim mutlaka dogrulanmali.

> NOT: DONGUNUN TAM HARITASI (ana gelistirici icin, oncelik sirasiyla):
> 
> Dongu tek yerde degil, UC yerde ayni desende tekrarliyor ve hepsi ayni kok nedene dayaniyor: BOYUTLANDIRMA ile DOGRULAMA ayni fonksiyonda ic ice.
> 
>   [1] _analyze_chamber_wall:  t = P*r/(sigma_y/SF_mat) * 1.2  ->  sigma = P*r/t  ->  SF = sigma_y/sigma = SF_mat*1.2
>   [2] _analyze_nozzle_structure: t = (P*r_t/(sigma_y/SF_mat)) * SCF -> sigma = SCF*P*r_t/t = sigma_y/SF_mat -> SF = SF_mat
>   [3] _analyze_end_caps: t plaka formulunden allowable'a boyutlandiriliyor -> sonra SILINDIR hoop formulu ile uyduruk bir gerilme uretilip ona gore SF veriliyor (bkz. bulgu #2)
> 
> Onerdigim yapi (imza kirmadan yapilabilir):
> 
>   A) analyze_structure'a `wall_thickness` (ve istege bagli `nozzle_throat_thickness`, `head_thickness`) girdisi eklensin. materials_db'deki `safety_factor` alani, yeni `design_safety_factor` argumaniyla ezilebilsin (malzeme kaydinda kalabilir ama VARSAYILAN olarak, ozellik olarak degil).
> 
>   B) _analyze_chamber_wall iki cikti ailesi versin:
>        SIZING (her zaman):  required_thickness_mm, recommended_thickness_mm  (mevcut hesap aynen kalir)
>        VERIFICATION (t verilmisse):  actual_hoop_stress, actual_von_mises, safety_factor_pressure, safety_factor_total, margin_of_safety = SF/SF_hedef - 1
>      t verilmemisse verification alanlari None donsun ve UI 'boyutlandirma modu — emniyet faktoru degerlendirilemedi' desin. Su anki gibi SF_mat*1.2'yi geri okuyup 'emniyet faktoru' diye gostermek en tehlikeli davranistir, cunku kullanici bunu bagimsiz bir dogrulama saniyor.
> 
>   C) minimum_safety_factor sepeti tek referansa (derate edilmis akma) normalize edilsin (bulgu #7), end_cap uyduruk formulu ASME UG-34 veya gercek plaka egilme gerilmesiyle degistirilsin (bulgu #2).
> 
>   D) Birincil/ikincil ayrimi: `safety_factor` (tepe seviye) = safety_factor_pressure olsun; termal icin ayri `shakedown_ratio = (P+Q)/(3*Sm)` alani eklensin (bulgu #4). Aksi halde her rejeneratif hazne 'UNSAFE' cikmaya devam eder.
> 
>   E) pressure_vessel.py::analyze zaten DOGRU deseni kuruyor (wall_thickness_mm verilirse dogrular, None ise boyutlandirir) — structural_analysis icin birebir kopyalanabilir referans o dosyadir. Tek pürüzü oto-boyutlandirmanin kabul kriteriyle tutarsizligi (bulgu #5).
> 
> OLUMLU TESPITLER (bozmayin):
>   - Lame / ince-cidar gecisi t/r=0.1'de DOGRU calisiyor, zarf ihlali YOK, max() ile daima konservatif olan seciliyor.
>   - Kalin rejimde von Mises'in 3-eksenli (sigma_r=-P) forma gecmesi dogru.
>   - Termal hoop formulu (E*alpha*dT/(2(1-nu))) dogru; 2'nin dusurulmesi hatasi gercekten geri alinmis.
>   - Yorulmadaki MPa/Pa 1e6 birim hatasi gercekten duzelmis (dogruladim).
>   - 2026-07-16 'burkulma basma-yuku' duzeltmesi FORMUL OLARAK DOGRU ve SP-8007 ile birebir — ama uretimde hic tetiklenmiyor (bulgu #6).
>   - 2026-07-16 '2:1 elipsoidal yerine yarimkure formulu' duzeltmesi hem structural hem pressure_vessel'de dogru uygulanmis (elipsoidal t ~ silindir t, yarimkure tam yarisi — sayisal olarak dogruladim).
>   - bolted_joint.py butunuyle saglam: tork tablolariyla %2 icinde, Shigley denklemleriyle birebir, ISO 898-1/3506-1 degerleri dogru, birim yonetimi kusursuz. Tek eksigi on-yuk sacilimini SF'lere uygulamamasi ve dis siyirma/civata yorulmasinin hic olmamasi.
> 
> BIRIM DENETIMI OZETI: Bu uc dosyada 1000x tipi birim hatasi BULAMADIM. structural_analysis girdiyi bar alip hemen Pa'ya ceviriyor, cikti sozlukunde tutarli sekilde MPa/mm/kN kullaniyor ve bunu yorumla isaretliyor. pressure_vessel bar->Pa, mm->m donusumlerini analyze basinda tek yerde yapiyor. bolted_joint mm^2->m^2 ve mm->m donusumlerini her alt fonksiyonda dogru yapiyor. Tespit ettigim tek etiket sorunu _analyze_fasteners'in 'force_per_bolt' alani (deger 4x tasarim yuku, adi gercek yuk ima ediyor — bulgu #10).

> DENETLENEN (satır satır okundu + mümkün olan her yerde sayısal olarak sınandı):
> 
> 1) hrma/data/burn_rate_db.py — TAMAMI (144 satır). KNDX/KNSB 5'er rejimin a-n değerleri ve basınç sınırları Nakka 1999/2001 yayımlanmış tablolarıyla tek tek karşılaştırıldı (birebir tuttu). resolve_engine_coeffs birim dönüşümü elle türetildi ve 5 basınçta bit-tam doğrulandı (fark ≤3.6e-15). _select_regime sınır davranışı incelendi.
> 
> 2) hrma/analysis/transient_ballistics.py — TAMAMI (518 satır). ThroatErosionModel (Pa→bar, mm/s→m/s, yarıçap↔çap), _exit_pressure_ratio, _momentum_cf, _thrust_coefficient, blowdown SPI enjektör kalibrasyonu (ṁ=K√(2ρΔP)), yarı-kararlı kamara kapanışı Pc=ṁc*/(Cd·At), erozyon-ε kuplajı, SP-8089 ΔP/Pc eşikleri okundu. NOT: bu modül HİBRİT motor içindir; görev tanımındaki 'nozul erozyonu' fiziği burada yaşıyor ve doğru. Katı motorda erozyon modeli YOK (bulgu #3).
> 
> 3) hrma/engines/solid_rocket_engine.py — fizik yükü taşıyan tüm fonksiyonlar okundu: burn_rate, calculate_burn_area (6 grain tipi), calculate_thrust_curve (denge basıncı + tükeniş kapanışı), _thrust_coefficient, _calculate_theoretical_isp, _estimate_throat_diameter, _estimate_expansion_ratio, _expansion_ratio_from_pressure_ratio, _propellant_volume(_uncached), _port_flow_area, _bates_geometry_for/_bates_segment_count, _design_burn_rate, _apply_overrides (tüm override zinciri), _set_propellant_properties, _isp_loss_breakdown, _calculate_detailed_analysis, _calculate_advanced_performance, _calculate_erosive_effects, _analyze_burn_rate_consistency, _web_utilization_percent, _calculate_grain_structural, _calculate_heat_flux, _chamber_gas_side, _insulation_*, _calculate_safety_analysis, _case_design, _design_health_warnings, SOLID_DESIGN_POINT/SOLID_CASE_DESIGN/SOLID_CONDENSED_MASS_FRACTION/GRAIN_MECHANICS sabit blokları.
> 
> SAYISAL OLARAK SINANANLAR (scratchpad'e geçici betikler, hiçbir dosya değiştirilmedi):
> - 6 grain tipinde kütle korunumu (yakılan/mevcut oranı ölçüldü)
> - a=0.005 vs katalog a=0.002233 uçtan uca motor koşusu (t_b, F, I_t, boğaz)
> - KNDX donmuş-rejim hatası (iki tasarım basıncında, yanma boyunca r sapması)
> - erozif çarpanın G ve D/D_oda taramasında büyüklüğü; UI override'ının etkisi
> - sabit-ε nozulun gerçek CF'i ile koddaki anlık-optimum CF karşılaştırması (impuls + tepe sapma)
> - grafit boğaz erozyonunun ihmalinin BATES vs end-burner'da Pc/itki etkisi
> - 100 mm/s kırpmasının tetiklenmesi ve uyarı üretilmemesi
> - test_altitude=5000 m'de CF/ε tutarsızlığı
> - _calculate_grain_structural'ın Lamé+termal cebri elle yeniden türetildi
> 
> DENETLEYEMEDİKLERİM (dürüst liste):
> - APCP/KNSU/siyah barut/çift-tabanlı yakıtların c*, γ, T_c, MW dörtlüleri 'CEA-tutarlı sentetik referans' diye beyan edilmiş; CEA'yı çalıştıramadığım için Eq. 3-32 iç tutarlılığını doğrulamakla yetindim, MUTLAK doğruluklarını doğrulayamadım. SOLID_CONDENSED_MASS_FRACTION'ın şeker (0.44) ve siyah barut (0.55) değerleri de aynı sebeple doğrulanamadı (APCP'nin 0.3401 stokiyometrisi doğrulandı).
> - Erozif yanma katsayılarının (k = 0.0136 vb.) hangi statik ateşleme verisine kalibre edildiğini bulamadım; v2.4.5 commit mesajı yalnız '×0.58, orta-yanma eşdeğerliği' diyor, dış kaynak yok. Bu yüzden büyüklük eleştirimi literatür BANDIYLA karşılaştırma üzerinden yaptım, ölçülmüş bir referans motorla değil.
> - star/wagon_wheel/finocyl/slotted'ın shapely poligon-ofset makinesini (Huygens kurulumu, _clipped_burn_perimeter, _radial_slot_offset) satır satır DENETLEMEDİM; yalnız kütle korunumu testiyle uçtan uca sınadım (hepsi <%0.35 sapma verdi). Poligon kurulumunda gizli bir geometri hatası bu testten kaçabilir.
> - _calculate_case_temperature (geçici kasa ısınması, açık Euler 2000 adım), _calculate_thermal_analysis, _calculate_cost_analysis, run_monte_carlo ve CAD/çizim üreten fonksiyonlar KAPSAM DIŞI bırakıldı (görev tanımı katı balistiğe odaklıydı).
> - pressure_vessel.PressureVesselAnalyzer'ın Faupel kalın cidar formülünü doğrulamadım (ayrı modül, kapsam dışı).
> - Star/finocyl/slotted koşularının 'pressure_collapse' ile sonlanmasını inceledim ama kök nedenini kovalamadım (kütle korunumu bozulmadığı için fizik hatası olduğuna dair kanıtım yok).

> NOT: GENEL DEĞERLENDİRME: Katı motor iç balistiğinin ÇEKİRDEĞİ sağlam. Denge basıncı türevi, BATES yanma alanı/kütle korunumu, orta-web nötrlük ailesi (4r+3W tam çözüm), Lamé+termal grain gerilme analizi ve Nakka rejim tablosu ile birim dönüşümü — hepsi doğru. Hatalar çeperde: varsayılan katsayılarda, model geçerlilik zarflarında ve rapor katmanında.
> 
> ÖNCELİK SIRASI (düzeltme yaparken):
> 1. burn_rate_a varsayılanı 0.005 → 0.002233 (motor + app.py + solid.html + tooltip bandı). Tek satırlık düzeltme, %120 itki hatasını kapatıyor. propellants_db zaten doğru değeri üretiyor; varsayılanı oradan çekmek magic-number tekrarını da bitirir.
> 2. KNDX/KNSB parçalı yasasının anlık basınçtan okunması (burn_rate içinde burn_rate_db.burn_rate_mmps çağrısı). Preset yolunu kullanan her koşuyu etkiliyor.
> 3. erosive_k UI varsayılanının (0.0002) yakıt tablosunu ezmesini kesmek — aksi hâlde v2.4.5'te yapılan tüm erozif kalibrasyon çalışması ölü kod.
> 
> KAPSAM DIŞI AMA GÖRDÜĞÜM (fizik değil, başka ekibin işi olabilir — bilgi olsun diye):
> - _calculate_safety_analysis['failure_modes'] tasarımdan BAĞIMSIZ sabitler döndürüyor: case_rupture_probability 1e-6, nozzle_failure 1e-5, ignition_failure 1e-4, overall_reliability 0.999. Aynı şekilde _calculate_quality_analysis'in TAMAMI sabit (dimensional_accuracy 99.5, 'Ra 3.2 μm', tolerans yüzdeleri). Kullanıcıya hesaplanmış güvenilirlik gibi görünüyor. Zaten açık olan A1-3 (sahte uygunluk rozetleri) göreviyle aynı aile.
> - burn_rate_db._select_regime docstring'i 'rejim sınırında ALT rejim geçerlidir' diyor ama kod (p_min <= p < p_max) sınırda ÜST rejimi seçiyor. Sayısal etkisi yok, yalnız docstring yanlış.
> - solid.html'in 'erosive_m' (erozif üs) alanı backend'e gidiyor, motorda hiç okunmuyor; üs kodda sabit 0.8. Aynı şekilde 'erosion_factor' (boğaz erozyonu) alanı da tamamen ölü.
> - UI varsayılan termokimyası (density 1850, c* 1550, γ 1.25, T_c 3200) motorun kendi APCP tablosundan (1810 / 1598.2 / 1.1986 / 3614.8) ve propellants_db'den farklı; override kazandığı için fiilen çalışan set UI'ınki. İki kaynak arasındaki fark c*'ta %3.0, yoğunlukta %2.2. CLAUDE.md kural 11 (tek tanım noktası) ihlali.
> - Kn raporlaması geometrik boğaz alanından (A_t/Cd) hesaplanıyor; balistiği çözen etkin A_t'den değil. UI varsayılanı Cd=0.98 ile raporlanan Kn gerçek balistik Kn'den %2 düşük.

> DENETLEDIKLERIM (dort dosyanin tamami satir satir okundu, sonra SAYISAL olarak sinandi):
> 
> uncertainty.py — UncertainInput.ppf (truncnorm a=(low-mean)/sigma, b=(high-mean)/sigma scipy sozlesmesi: DOGRU), nominal_value, get_default_distributions override mantigi, _lhs_unit (scipy qmc + saf-numpy yedegi; yedek permutasyonlu tabaka mantigi da DOGRU), sample_inputs, _stats_block (mean/std/cv/yuzdelikler/mean_shift/histogram), spearman_sensitivity, run_uncertainty MC dongusu ve ornek #0 tutarlilik kapisi, _diverged_result, _extract_outputs/_auto_output_keys. Sayisal deney: LHS sutun-arasi sahte korelasyon (60 tohum x 3 n), sahte duyarlilik testi (200 tohum), nominal_first tabakalama bozulmasi, basarisiz-ornek dislama yanliligi (yapay tek-kuyruk basarisizlik modeli, n=1000), P5/P95/ortalama ornekleme hatasi (2000 tekrar x 3 n), ddof=0 vs ddof=1.
> 
> uq_adapters.py — normalize_overrides, build_distributions, UNMAPPED_PARAMS, _pick_outputs/_finite_float, uc fabrikanin da kurucu bloklari. Sayisal deney: UQ nominal ciktilarini gercek /calculate ve /calculate_liquid deterministik yollariyla ayni girdilerle karsilastirdim (hibrit -%7.00, sivi -%4.00 sapma olculdu). Sivi eta uygulamasinin matematigini (Isp*eta, c**eta, mdot/eta, F sabit) boyut analiziyle dogruladim ve DELIVERED_ETA_CSTAR_DEFAULT=1.0 oldugunu teyit ederek cift-sayim olmadigini gosterdim.
> 
> correlation_runner.py — db_content_hash, _score_adapter_result durum makinesi, _basic_stats (bes metrigin tanimi), _mad_outliers, _cell, _aggregate katmanlamasi (main/low/anomaly), run_correlation, deterministic_view, to_markdown. Sayisal deney: TAM DB uzerinde run_correlation() kosuldu (209 kayit, 95 ok, 191 skorlanan giris), sonuc JSON'u kaydedilip hucre hucre analiz edildi; MAD esiginin gercek isaretleme orani 20000 tekrarli MC ile olculdu (4 farkli n); hucre basina bagimsiz kampanya sayisi test_id oneklerinden sayildi; measurement_uncertainty tasiyan kayit/giris sayisi sayildi.
> 
> record_adapters.py — UNIT_TO_SI'nin HER carpani tek tek NIST SP 811 / BIPM'e karsi dogrulandi ve turetilenler (in2, gpcc, gpcm2s) elle yeniden hesaplandi; split_quantity_key'in en-uzun-sonek-once mantigi cakisma senaryolariyla (kgf/kg/g, lbfs/lbf/lb, m2/m, mmps/mps/s, _min/_in) sinandi; convert_block'un null/egri/metin/cift-yazma dallari okundu; _run_hybrid sabit-nokta dongusu ve tuketilen-olcum muhasebesi, _run_liquid eps/cycle girdi gerekcesi ve ZAYIF KANIT notu, _run_solid, _run_strand'in iki ayri a-n birim sozlesmesi (burn_rate_db Pa vs motor bar) kaynagina gidilerek dogrulandi. Sayisal deney: hybrid isp ve thrust hucrelerinin test-basina hatalari karsilastirilip cebirsel ozdeslik gosterildi; solid burn_rate girislerinin burn_rate_db fit_source_records ile kesisimi sayildi (27/27).
> 
> DENETLEYEMEDIKLERIM (durustce):
> 1. Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2'nin parafin fitinin HANGI test kosularindan uretildigini teyit edemedim (makaleye erismedim). Bu yuzden hyb-karabeyoglu2003-* kayitlarinin in-sample olup olmadigini IDDIA ETMIYORUM; yalnizca hibrit tarafta boyle bir denetimi mumkun kilan fit_source_records mekanizmasinin HIC OLMADIGINI bildiriyorum.
> 2. Sobol/Morris indisleri kodda YOK — dolayisiyla "dogru hesaplaniyor mu" sorusunu sinayacak bir sey yok; yoklugun gerekcesi (Saltelli semasi N(d+2) kosu ister) kaynakla dogrulandi ve gecerli.
> 3. Hucre basina istatistiklerin OZ-KAYNAK dogrulugunu (yani DB'deki her olcum degerinin kaynak makaleyle eslesip eslesmedigini) denetlemedim — bu bu ajanin gorevi degildi, veri girisi denetimi ayri bir is.
> 4. MC yakinsamasini gercek motor fabrikalariyla coklu-tohum kosarak olcmedim (hibrit UQ ornek basina ~100-200 ms, 3 tohum x 1000 ornek pratik degildi); onun yerine yakinsama hatasini analitik/sentetik olarak sinirladim ve rakamlari duz-MC UST SINIRI olarak isaretledim.
> 5. Frontend'in bu istatistikleri nasil gosterdigine bakmadim (gorev disi); "user_visible" bayraklarini, degerin API yanitina/yayimlanan rapora girip girmedigine gore verdim.
> 
> DOGRU BULDUKLARIM (zorlama bulgu uretmemek icin acikca yaziyorum): birim donusum tablosunun tamami, motor arayuzu birim devirleri (mm/bar/Pa), medAPE/MAPE/bias/RMS tanimlari, isaretli hata sozlesmesi, measured_zero korumasi, bilinmeyen sonekli sayinin asla SI kabul edilmemesi, db_content_hash + deterministic_view determinizmi, Spearman yonteminin kendisi ve monotoniklik uyarisi, Sobol'un kapsam disi birakilma gerekcesi, sivi eta_c* uygulamasinin matematigi, aykirilarin ATILMAMASI karari, anomaly katmaninin ayrilmasi, sentetik kayitlarin kosulsuz dislanmasi, cd_injector'un eslenemedigi icin sahte 0 duyarlilik yerine hic raporlanmamasi.

> NOT: EN ONEMLI UC BULGU (oncelik sirasi):
> 
> 1. `record_adapters.py::_run_hybrid` — hibrit `thrust` ve `isp` hucreleri CEBIRSEL OLARAK AYNI karsilastirmadir (test basina fark < 0.055 yuzde puani, olculdu). Yayimlanan raporda iki ayri n=18 hucre + iki ayri parity grafigi olarak duruyor. `total_impulse` ucuncu kopya. Duzeltme ucuz: `_run_liquid`'deki "ZAYIF KANIT" notunun aynisini hibrit thrust/total_impulse icin de yaz ve hucreyi ayri katmana al.
> 
> 2. `uq_adapters.py` eta_c_star asimetrisi — UQ nominali ile ana sayfanin nominali arasinda hibritte TAM -%7.00, sivida -%4.00 fark var. `uncertainty.py`'nin 1e-9 "deterministik tutarlilik garantisi" fabrikanin kendisini kendisiyle karsilastirdigi icin bu sapmayi yapisal olarak goremez — yani var olan koruma, korudugu sanilan seyi korumuyor. Bu, dosyanin kendi docstring iddiasini ("BIREBIR izler ... girdi-yorumu farki olamaz") yanlislayan tek bulgu.
> 
> 3. `correlation_runner.py` — olcum belirsizligi hic okunmuyor (skorlanan 191 girisin 108'i bildirilmis belirsizlik tasiyan kayitlardan) VE her kayit bagimsiz sayiliyor (hibrit hucrelerin hepsi 1-2 kampanya). Ikisi birlikte, yayimlanan medAPE degerlerinin guven araligini oldugundan ~4-6 kat dar gosteriyor.
> 
> BIR NOT: Bu dort dosya, denetledigim kod yiginlarina gore ALISILMADIK derecede durust yazilmis. Adaptor kendi zayif noktalarini ("ZAYIF KANIT", "IN-SAMPLE", "c* tahmini teorik, pozitif sapma beklenir", "a-n HRMA varsayilanidir") kendisi etiketliyor. Bulgularimin cogu YENI hata degil, bu durust etiketlerin toplulastirma katmaninda KAYBOLMASI: `_cell` ve `to_markdown` adapter_notes'u tasimiyor. En ucuz ve en yuksek getirili tek duzeltme bu — notlari hucreye ve markdown tablosuna tasimak (in_sample_n, weak_evidence bayraklari).
> 
> BIR RISK UYARISI: `OUTLIER_MAD_FACTOR = 3.0` degerini duzeltirken dikkat — 4.45'e cikarmak aykiri sayisini dusurur ve `stats_excl_outliers` satirlari degisir; mevcut testler bu sayilara baglanmis olabilir. Aykirilar zaten ATILMADIGI icin bu sadece sunum meselesidir, acele edilmemeli.

> DENETLENEN (satır satır okundu + mümkün olan her yerde SAYISAL sınandı; RocketCEA 1.2.1 ve Cantera 3.1.0 bu makinede kurulu olduğu için gerçek referans karşılaştırması yapabildim):
> 
> cea_bridge.py — TAMAMI (391 satır). Denetlenen: birim sabitleri (FT_PER_S_TO_M_PER_S, DEG_R_TO_K, BAR_TO_PSIA, CAL_PER_G_K_TO_J_PER_KG_K), map_propellants kart eşlemesi, _compute_rocketcea'nın her RocketCEA API çağrısı ve dönüş birimi, get_Isp'in vakum Isp döndürdüğü iddiası, estimate_Ambient_Isp(Pamb) kullanımı, get_SpeciesMoleFractions istasyon indeksleme, _from_fallback anahtar takma adları, _not_modelled dürüstlüğü, önbellek yuvarlama anahtarları, validity bayrakları. Ham RocketCEA'ya karşı c*/Tc/Isp birebir doğrulandı.
> 
> nozzle_design.py — TAMAMI (648 satır). Denetlenen: c* formülü (formülle birebir doğrulandı), CF momentum + basınç terimi (Sutton Eq. 3-30), ayrık kayıp modeli çarpımı, _divergence_efficiency her iki dal, bell/konik/parabolik kontur uzunlukları ve açıları, _resolve_contraction, boğaz yayı yarıçapları (1.5·rt / 0.382·rt), _calculate_nozzle_geometry (frustum yüzey/hacim formülleri DOĞRU; duvar kalınlığı kuralı hatalı), calculate_nozzle_flow_properties'in tüm izentropik bağıntıları, brentq alan-Mach çözümü (Sutton Eq. 3-14, DOĞRU) ve fallback yaklaşıklığı, sample_nozzle_inner_contour'un mm/m birim tutarlılığı (mm-mm, TUTARLI) ve Bézier teğet kurgusu.
> 
> combustion_analysis.py — TAMAMI (1443 satır). Denetlenen: elemental kütle dengeleri (7 yakıt + 5 oksitleyici, her biri elle toplandı — hepsi ≤%0.2 içinde kapanıyor), stokiyometrik yanma denklemleri (7'sinin de O atom dengesi denk), _estimate_flame_temperature HP-denge kurgusu, _calculate_reactant_enthalpy birim zinciri (kJ/mol→J/kg), _elements_to_cantera_composition'un TPY (kütle) kullanımı, denge γ'sının SP pertürbasyonuyla türetilmesi (n_s = dlnP/dlnρ|_s, RP-1311 yöntemi — DOĞRU), boğaz/çıkış izentropik bağıntıları, frozen/shifting Isp enerji denklemi, c*/CF/Isp zinciri, calc_mw harmonik ortalaması, calc_enthalpy/calc_entropy birim zincirleri, irtifa performansı (iki fonksiyon da elle yeniden hesaplandı), _calculate_isentropic_efficiency, find_optimum_of_ratio önbelleği (fizik etkisi yok).
> 
> SAYISAL SINAMA YAPILAN REFERANSLAR: LH2/LOX (RS-25 koşulları), RP-1/LOX (Merlin sınıfı), N2O/HTPB, LOX/HTPB, N2O/PE, LOX/paraffin, LOX/PMMA — hepsi RocketCEA'ya karşı. Ayrıca Cantera'sız yol zorlanarak ölçüldü.
> 
> DENETLEYEMEDİĞİM / SINIRLARIM:
> 1. _fallback_equilibrium_composition bulgusunun ŞİDDETİ, Cantera'nın paketlenmiş uygulamada bulunup bulunmamasına bağlı. requirements.txt'te ve packaging/ betiklerinde 'cantera' geçmiyor (grep ile tarandı, .spec dosyası bulunamadı) — ama paketleme benim kapsamım değil, kesin hüküm vermedim. Yalnız fallback yolunun sayısal hatasını ölçtüm.
> 2. nozzle_design'ın 'performance' bloğunun kullanıcı arayüzünde nerede göründüğünü tam izleyemedim: grep ile templates/static içinde hibrit 'nozzle_design.performance' tüketicisi bulamadım (yalnız solid.html kendi ayrı bloğunu okuyor). API JSON'una ve proje kaydına girdiği kesin, ana panelde gösterildiği kesin değil — user_visible alanlarını buna göre temkinli işaretledim.
> 3. Rao %80 bell'in ε'ye bağlı θn/θe değerlerini hafızadan verdim (Rao 1958 grafikleri); elimde grafiğin sayısal tablosu yoktu, o yüzden 'kabaca' diye yazdım ve bulguyu GECERSIZ_ZARF olarak işaretledim — YANLIS_KATSAYI demedim.
> 4. N2O sıvı/gaz entalpi farkının etkisini ÖLÇEMEDİM: referans aldığım RocketCEA da aynı gaz-fazı kartını kullandığı için karşılaştırma bu farkı göstermez; yalnız elle mertebe tahmini verdim.
> 5. Katı motor tarafı (solid_rocket_engine) ve hybrid'in kendi CF/Isp zinciri bu üç dosyanın dışında; yalnız çağrı sözleşmesini doğrulamak için okudum, denetlemedim.
> 6. Kod DEĞİŞTİRMEDİM. Geçici betikler yalnız scratchpad altında (t1_cea.py … t6.py).

> NOT: GENEL HÜKÜM: Üç dosyanın FİZİK ÇEKİRDEĞİ sağlam. cea_bridge'in birim dönüşümleri ham CEA'ya karşı birebir; combustion_analysis'in Cantera'lı yolu RocketCEA'ya karşı c*'ta ±%2, Tc'de ±%3.6 içinde; nozzle_design'ın c* ve CF formülleri Sutton Eq. 3-30/3-32 ile birebir. Kodda atıf verilen yerlerin çoğunda atıf GERÇEK ve YERİNDE — sahte kaynak bulmadım (tek zayıf nokta bell λ'sının Sutton sec. 3.4'e atfı, o da kodun kendi yorumunda itiraf edilmiş).
> 
> SORULAN İKİ ÖZEL MADDE:
> 1) "Adaptör yayımlanmış genişleme oranını motora geçirmiyordu" düzeltmesi — TEYİT EDİLDİ ve doğru. Zincirin üç halkasını da ayrı ayrı sınadım: (a) cea_bridge get_Isp'e ε'yi geçiyor ve Isp gerçekten ε ile değişiyor (ε=69→462.75 s, ε=200→478.10 s — koddaki yorumun iddia ettiği sayılarla birebir), (b) record_adapters._predict_liquid yayımlanmış ε'yi overrides ile geçiriyor ve geçmediğinde adapter_notes'a dürüstçe yazıyor, (c) _apply_nozzle_off_design_once canlı-CEA yolunda çift sayımı açıkça engelliyor. medAPE %8.9→%1.0 iyileşmesi bu fizikle tutarlı. TEK EKSİK: aynı ε disiplini _from_fallback (RocketCEA'sız) yolunda YOK — orada tablo ε=200 çapasında kalıyor, ama liquid motor CF-oranı düzeltmesiyle telafi ediyor (o iki bağıntıyı da elle doğruladım, doğrular).
> 
> 2) vacuum_isp_ratio'nun Pc bağımlılığı — bu fonksiyon hrma/constants.py'de ve YALNIZ solid_rocket_engine.py tarafından çağrılıyor; verilen üç dosyanın hiçbirinde kullanılmıyor, o yüzden bulgu listesine almadım. Yine de okudum: ratio = 0.953 + 0.0405·ln(ε) + 0.005·(γ−1.2). Fizik olarak Isp_vac/Isp_sl = 1 + P_a·ε/(P_c·CF_sl) olduğundan oran Pc'ye GERÇEKTEN bağlıdır (Pc arttıkça oran 1'e yaklaşır) ve formülde Pc hiç yok. Açık karar olarak duruyor demek doğru; kapatmak için ya Pc'yi argümana almak ya da doğrudan _cf_at(ε, 0)/_cf_at(ε, P_a) oranını kullanmak gerekir. Bu kararı ilgili dosyanın denetçisine bırakıyorum.
> 
> ÖNCELİK SIRASI (benim kanaatim): (1) _fallback_equilibrium_composition sabit bileşimi — Cantera'sız kurulumda c* %13'e varan hata, azotsuz çiftlerde %54 N2 fiziksel olarak savunulamaz; en azından Cantera'yı requirements'a almak ya da fallback'te atom-denge tabanlı basit bir çözüm koymak. (2) nozzle_design'a P_a'nın exit_pressure olarak geçmesi — ε'nin CF üstündeki etkisini tamamen siliyor. (3) isentropic_efficiency'nin sabit 1.0 raporlaması ve mass_averaged_mw=30 — ikisi de "asla uydurma" ilkesine doğrudan aykırı yer tutucular, kaldırmak düzeltmekten kolay. (4) Bell θn/θe sabitleri, duvar kalınlığı kuralı.
> 
> BULGU ÜRETMEK İÇİN ZORLAMADIĞIM YERLER (doğru buldum, ayrıca yazmadım): İterasyonlu/önbellekli yollar davranışı değiştirmiyor (deepcopy + tam-değer anahtar disiplini doğru kurulmuş). two_phase_loss_coeff=0.12 ile η=1−0.12·X_p modeli, X_p=0.30'da %3.6 kayıp veriyor — Sutton'ın metalize katıda bildirdiği %2-4 bandıyla tutarlı, kabul ediyorum. friction 0.99 / kinetic 0.995 varsayılanları Sutton'ın verdiği bantların içinde. sample_nozzle_inner_contour'un mm/mm birim tutarlılığını ayrıca kontrol ettim (Rn hem mm hem fallback 0.382·rt mm) — burada 1000x tuzağı YOK. HTPB Hf'nin CEA R-45 kartına (+2.7 kJ/mol) çekilmesi doğru karar; Tc'nin CEA'ya %0.5 içinde oturması bunu kanıtlıyor.

> DENETLENEN DOSYALAR: hrma/analysis/heat_transfer_analysis.py (1389 satır, TAMAMI okundu), hrma/analysis/regen_cooling.py (1521 satır, TAMAMI okundu), hrma/analysis/thermal_protection.py (559 satır, TAMAMI okundu). NOT: görevde adı geçen dosya yolu 'hrma/analysis/regen_cooling.py' mevcut; üçü de var.
> 
> TAM DENETLENEN VE SAYISAL OLARAK SINANAN FONKSİYONLAR:
> - heat_transfer_analysis: _bartz_coefficient (boyut analizi elle + 4 referans motorla çalıştırıldı), _adiabatic_wall_temperature, _get_gas_properties (Bartz viskozite katsayısı elle birim dönüşümüyle karşılaştırıldı), _resolve_throat_conditions (c* özdeşliği cebirsel olarak sadeleştirildi, rho_t*a_t = Pc/c* özdeşliği ispatlandı), _mach_from_area_ratio, _species_emissivity / _gas_emissivity / _gas_absorptivity / _gas_radiation_flux (Leckner katsayı matrisleri Modest Tablo 10.4 ile satır satır karşılaştırıldı, eps_g taraması yapıldı, +P_E / -P_E işaret duyarlılığı ayrı betikle ölçüldü), _analyze_gas_side_heat_transfer, _analyze_wall_temperature, _analyze_cooling_requirements, _analyze_thermal_safety, _resolve_mechanical_properties, _coolant_side_coefficient, _calculate_cooling_efficiency, analyze_heat_transfer ve analyze_axial_profile (uçtan uca çalıştırıldı, kontur integrali ile toplam ısı yükü çapraz kontrol edildi).
> - regen_cooling: dittus_boelter_nu, hydraulic_diameter_rect, haaland_friction_factor (Blasius ile çapraz), darcy_weisbach_dp, fin_area_ratio (elle eta hesabıyla), acceleration_dp, jackson_nu, jackson_exponent_n, pseudocritical_temperature (algoritma incelendi), _interp_table/water_properties/rp1_properties (klamp davranışı CoolProp ile ölçüldü), _station_wall_balance, _station_wall_balance_sc, _build_stations, solve (60 bar/bakır/su ile uçtan uca çalıştırıldı, enerji korunumu makine hassasiyetinde doğrulandı).
> - thermal_protection: ablative_thickness (çalıştırıldı), heat_sink_transient (Carslaw & Jaeger yarı-sonsuz analitik çözümüyle karşılaştırıldı — %0.00 sapma; enerji dengesi %0.00), radiation_equilibrium (bisection artığı ölçüldü), _resolve_ablative, analyze dağıtıcısı.
> - Ek olarak hrma/data/materials_db.py'nin sıcaklık limit alanları (allowable_temperature / max_service_temp / max_service_temperature / melting_point) 24 malzeme için tablo hâlinde taranıp erime noktasıyla karşılaştırıldı (bu üç modülün geçerlilik eşiklerini oradan aldığı için).
> 
> DENETLEYEMEDİĞİM / EKSİK KALAN NOKTALAR (DÜRÜST LİSTE):
> 1. LECKNER BASINÇ DÜZELTMESİNİN PAYDA İŞARETİ: koddaki (A+B-1+P_E) formunu birincil kaynaktan (Modest Radiative Heat Transfer Tablo 10.4 / Leckner 1972 orijinal makalesi) TEYİT EDEMEDİM. Web araması formülün tam hâlini vermedi (jina MCP yetkisiz döndü, WebSearch/WebFetch sonuçları formülü içermedi), elimde kitap yok. Katsayı matrislerinin ve A/B/c/(p_aL)_m/P_E parametrelerinin tümü doğrulandı; yalnız bu tek işaret açık kaldı. Fiziksel asimptotik davranış kodun seçimini destekliyor ve sayısal etkisi toplam akıda ~%1 olduğu için DUSUK verdim — ama kesin cevap için kitabın Tablo 10.4'üne bakılmalı.
> 2. RP-1 ÖZELLİK TABLOSUNUN DOĞRULUĞU: 290-500 K bandındaki rho/cp/k/mu değerlerini bağımsız bir kaynakla karşılaştıramadım (CoolProp'ta RP-1 yok, elimde NIST/Huzel eki yok). Modül zaten +/-%2/8/15/25 belirsizlik bandı beyan ediyor; bu beyanı doğrulayamadım da yanlışlayamadım da.
> 3. Q* BANTLARI (8-12 / 25-30 / 4-6 MJ/kg): NASA SP-8091 metnine erişemedim. Bulgu olarak 'kaynak bulunamadı' işaretledim, uydurma bir doğrulama yazmadım.
> 4. RADYASYON SOĞUTMALI UZANTIDA GÖRÜŞ FAKTÖRÜ İHMALİNİN BÜYÜKLÜĞÜ: modülde nozul geometrisi girdisi olmadığı için F'yi hesaplayamadım; yalnız mertebe tahmini verdim ve bunu bulguda açıkça belirttim.
> 5. C-103 (1640 K) ve C-C (1920 K) servis limitlerini ve emisivite değerlerini (0.75 / 0.85) bağımsız kaynakla teyit etmedim — bunlar 'approximate/heritage' etiketli ve makul göründükleri için bulgu üretmedim, ama teyit edilmiş de değiller.
> 6. KAPSAM DIŞI BIRAKTIĞIM KONULAR (görev talimatı gereği): import hataları, frontend, i18n uyarı kodları ve katalogları (_mk_warning metinleri), güvenlik, testlerin kendisi. Yalnız bir yerde bu sınırı aştım: materials_db sıcaklık alanları — çünkü üç modülün de fiziksel geçerlilik eşiği oradan geliyor ve orada gerçek bir güvenlik açığı buldum.
> 7. SATIR NUMARASI VERMEDİM (talimat gereği); tüm bulgular dosya::fonksiyon biçiminde işaretlendi.
> 
> GENEL KANAAT: Bu üç modülün ÇEKİRDEK FİZİĞİ sağlam. Bartz (g0'sız SI formu dahil), Dittus-Boelter, Haaland, Jackson, fin verimi, açık FD şeması ve termal gerilme formülünün hepsi kaynaklarıyla birebir örtüşüyor ve sayısal sınamalardan geçti; FD çözücü analitik çözümle %0.00, regen marşı enerji korunumuyla makine hassasiyetinde uyuşuyor. Ciddi bulgular denklemlerde DEĞİL, geçerlilik eşiklerinde ve kalan eski katsayılarda: (a) çelik ailesinde kritik yanma-delinme eşiğinin erime noktasının üstünde olması, (b) toplam ısı yükünde nozul yüzeyinin tamamen atlanması (%38 eksik), (c) rejeneratif soğutma alanında kalmış eski h=2000 katsayısı (10x).

> DENETLENEN DOSYALAR (ikisi de tam okundu, salt okunur; hiçbir dosya değiştirilmedi):
> 1. hrma/engines/injector_design.py (1418 satır) — v2.6.2 ana modül
> 2. hrma/utils/injector_design.py (572 satır) — ESKİ InjectorDesign sınıfı; DUPLİKE DEĞİL, farklı bir modeldir ve HÂLÂ CANLIDIR (hrma/app.py:38 import ediyor, satır 487'de /api/... hibrit akışında çağrılıyor). İki modül aynı fiziği farklı katsayı/tanımlarla kuruyor — çelişkileri bulgularda ayrıca işaretledim (σ_N2O, çıkış hızı tanımı, kavitasyon kriteri).
> 
> DENETLENEN FİZİK (görevde istenen listeye göre):
> - Orifis debi denklemi ṁ = Cd·A·√(2ρΔP): her iki modülde, tüm dallarda boyut analizi yapıldı → DOĞRU (bar→Pa ×1e5 dönüşümleri de doğru).
> - Cd seçim tablosu (SP-8089/Lefebvre bandları) → makul, DOĞRU.
> - Dyer NHNE: κ tanımı ve ağırlıklama Dyer ve ark. AIAA 2007-5702 ile birebir örtüşüyor, atıf GERÇEK ve DOĞRU. Sayısal olarak koşturuldu (doymuş girişte κ=1.000 → SPI/HEM aritmetik ortalaması, literatürde bilinen davranış; G=33 513 kg/(s·m²) deneysel bantta).
> - SPI ve HEM limitleri, boğulma taraması (çözünürlük duyarlılığı test edildi: %0.005), izentropik çıkış kalitesi → DOĞRU.
> - Kavitasyon/Nurick K_c → engines'te DOĞRU; utils'te YANLIŞ (bulgu listesinde).
> - 7 enjektör tipi momentum kriterleri: doublet MR, Rupe faktörü, triplet TMR, pintle TMR/θ, gaz-gaz J, swirl → hepsi tek tek denetlendi.
> - SMD korelasyonları (Elkotb, Lefebvre swirl, impinging We^-1/3): FORMÜLLER doğru; BİRİM (SI→metre) dizel referans hesabıyla teyit edildi; GİRDİLERDE (σ, μ, ṁ) ciddi hatalar bulundu.
> - Chug kararlılık marjı ΔP/Pc ≥ 0.15-0.20 (SP-8089) → DOĞRU ve doğru atıflı.
> - Sıkıştırılabilir gaz-gaz orifis akışı (Anderson Böl. 3) → kritik oranda süreklilik sayısal olarak teyit edildi, DOĞRU.
> 
> SAYISAL SINAMA: 4 betik yazıp çalıştırdım (scratchpad/swirl_check.py, case.py, utils_case.py + HEM çözünürlük testi). Bulguların çoğunda ÖLÇÜLEN sapma verdim (swirl Cd 2.02-2.68x, SMD 6.02x/2.50x/1.56x, pintle debi −%38, tank ΔP 4.5x, Weber 2.04x, Rupe ≡ d_f/d_ox).
> 
> DENETLEYEMEDİKLERİM (dürüst liste):
> - AKUSTİK MOD FREKANSI: Görevde istendi ama iki dosyanın HİÇBİRİNDE hesaplanmıyor. engines modülü bunu açıkça 'kapsam dışı' olarak raporluyor (warn.injector.acoustic_out_of_scope) ve sahte sayı üretmiyor — bu doğru davranış. Denetlenecek denklem yok.
> - CHUG'un GERÇEK kararlılık analizi (besleme inertansı/kompliyansı + yanma zaman gecikmesi, Wenzel & Szuch NASA TN D-7376) hiçbir modülde yok; yalnız ΔP/Pc kural-eşiği var. Kod bunu 'chug_rule' metniyle kural olarak sunuyor, model olarak değil — yanıltıcı bulmadım ama eksikliği not ediyorum.
> - N₂O DOYMA/ENTROPİ TABLOSU (_N2O_ENTROPY_TABLE, 23 nokta): CoolProp/Span-Wagner ile ÜRETİLDİĞİ söyleniyor; makinede CoolProp kurulu olmadığı için değerleri bağımsız doğrulayamadım. İçsel tutarlılık (s_l artıyor, s_v azalıyor, kritik noktaya yaklaşırken yakınsıyorlar) doğru görünüyor, ama bunu 'teyit edildi' saymıyorum.
> - _SAT (N2OSaturation) sınıfının kendisi bu görevin dosya kapsamı dışındaydı (tank_blowdown.py) — h_l, h_v, rho_l, rho_v, psat çıktılarını doğru varsaydım. psat(293.15) = 50.54 bar çıkması NIST değeriyle (50.8 bar) %0.5 uyumlu, bu dolaylı bir güven işareti.
> - Elkotb/Lefebvre/impinging korelasyonlarının HRMA'ya özgü deneysel doğrulaması yapılmadı (referans motor SMD ölçümü elimde yok); sapma tahminlerim korelasyonun kendi üs yapısından türetilmiş oran hesaplarıdır.
> - injector_panel.js / frontend akışını yalnız 'sigma_ox gönderiliyor mu' sorusunu yanıtlamak için grepledim (gönderilmiyor); frontend denetimi kapsamım dışıdır.
> - Kullanılmayan sabit MANIFOLD_AREA_RATIO_MIN = 4.0 (Huzel & Huang) hiçbir yerde kontrol edilmiyor — fizik hatası değil, ölü sabit; bulgu olarak saymadım.

> NOT: EN ÖNEMLİ TEK BULGU: hrma/engines/injector_design.py::swirl_solve içindeki np.sqrt(32.0/np.pi**2) katsayısı ters çevrilmiş — np.sqrt(np.pi**2/32.0) olmalı. Bu tek karakter düzeyinde bir hata değil, kök-altı ters çevirme; sonucu swirl enjektör Cd'sini 2-2.7 kat düşürüyor ve sprey yarı açısını fiziksel olarak imkânsız bir 17.5° tavanına hapsediyor. Koddaki 'theta_target > 16° çözülemez, K=1.0'a düş' geçici çözümü ve 'düz orifisten düşük olması fizikseldir' açıklaması bu hatanın etrafında inşa edilmiş; katsayı düzeltilirse ikisi de gereksizleşir (referansla 71° yarı açıya kadar çözülebiliyor). Doğruluğu üç bağımsız yoldan teyit ettim: (a) maksimum-debi ilkesinden kendi türetimim, (b) kodun KENDİ sinθ = (π/2)Cd/(K(1+√X)) bağıntısıyla iç tutarlılık, (c) Abramovich formu sinα = 2μA/(1+√(1−φ)), A = π/(4K) ile birebir örtüşme. Ayrıca düzeltilmiş sürüm literatür değerlerini üretiyor (K=0.3 → Cd=0.24, tam koni 92° — tipik simplex atomizör).
> 
> İKİNCİ ÖNEMLİ NOKTA: engines modülü ile utils modülü aynı fiziği FARKLI değerlerle kuruyor ve utils'te doğru olan (σ_N2O = 0.00175 N/m, NIST atıflı) engines'te yanlış (0.02), utils'te yanlış olan (kavitasyon kriteri) engines'te doğru (Nurick). İki modül arasında bir doğruluk senkronizasyonu turu, ayrı ayrı düzeltmeden daha verimli olur.
> 
> DÜRÜSTLÜK NOTU: Dyer NHNE (2026-07-13'te eklenen, özel dikkat istenen kısım) DOĞRU çıktı — hem denklem hem atıf gerçek, hem de sayısal davranışı literatürle uyumlu. Orada bulgu üretmek için zorlamadım. Aynı şekilde sıkıştırılabilir gaz-gaz akışı, pintle sprey açısı, orifis denklemi ve SMD korelasyonlarının FORMÜLLERİ temiz; sorunlar korelasyonlara verilen GİRDİLERDE (σ, μ, eleman başına debi) ve utils modülünün süreklilik ihlallerinde yoğunlaşıyor.

> DENETLENEN (4 dosyanin TAMAMI satir satir okundu, toplam ~2350 satir):
> 
> nozzle_flow_1d.py — modul duzeyi 4 yardimci (isentropic_ratios, area_ratio_from_mach, normal_shock_relations, ideal_thrust_coefficient) NACA Report 1135 tablolarina karsi 5-6 basamak SAYISAL olarak dogrulandi. Sinif metotlari: __init__ dogrulamalari, from_motor_data (bar->Pa donusumu dogru), _build_stations (kontur ornekleyici, bogaz cakmasi, cidar aci turevi), _mach_from_area, _classify_regime (6 dalli rejim merdiveni), _solve_separation, _solve_normal_shock, solve (kutle debisi, c*, istasyon dizileri, itki, cidar-integrali capraz kontrolu, kayiplar, Bartz baglantisi). 4 farkli referans kosusu yapildi: vakum/eps=25, deniz seviyesi ayrilmis, normal sok, bogulmamis kose durumu. Bartz'in ithal edildigi heat_transfer_analysis.py fonksiyonlari da (birim sozlesmesi icin) okundu.
> 
> water_hammer.py — 4 modul yardimcisi elle hesapla dogrulandi (dalga hizi klasik su/celik ornegi, Joukowsky 10 bar/(m/s) parmak hesabi, yavas kapanma kapali formu tam eslesme). FLUID_PROPERTIES tablosundaki 4 sivinin K/rho'dan turetilen ses hizlari kendi 'source' bantlariyla kiyaslandi. Hoop basinc sinifi Barlow ile kiyaslandi. _closure_recommendation tersleme cebiri kontrol edildi. N2O ve LOX ile gercekci besleme hatti senaryolari kosturuldu.
> 
> slosh_analysis.py — frekans, kutle orani, sarkac uzunlugu, modal kokler (scipy.special.jnp_zeros ile teyit), fill_sweep, baffle_damping, recommend_baffle, _coincidence, analyze. Miles bafl bagintisi icin IKI bagimsiz NASA kaynagi indirilip metni cikarildi (MTP-AERO-62-81 1962 ve NTRS 20130000590 2012) — eksik genlik terimi bu iki kaynaktan dogrulandi.
> 
> kinetic_efficiency.py — _extract_state (birim/anahtar sozlesmesi, rho_c kg/m^3 ve MW g/mol combustion_analysis ciktisiyla capraz kontrol edildi), _single_gamma_isp, _evaluate_fast, _evaluate_engineering (Pc, D_t ve L* taramalari yapildi), _blend_fraction, _build_result koselemesi, _validate_profile. Damkohler egilimleri ve mertebeleri NASA SP-8120 %0.1-3 bandiyla kiyaslandi.
> 
> DENETLENEMEYEN / SINIRLI:
> 1. kinetic_efficiency.py::_evaluate_high_fidelity — Cantera sonlu-hiz entegrasyonu SAYISAL olarak kosturulmadi (gercek bir yanma cozumu + lule profili gerekiyordu, denetim suresi icinde uretmedim). Yalnizca boyut analizi, Cantera desen dogrulugu (SP/equilibrate kullanimi) ve enerji yontemi mantigi denetlendi. Cantera mekanizmasinin (gri30/h2o2) rekombinasyon hiz sabitlerinin kendisi denetlenmedi — bu mekanizma dosyalarinin dogrulugu ustlenildi.
> 2. _elements_to_mass_fraction_string yolu (elemental -> atomik tur) yalnizca okundu, kosturulmadi.
> 3. water_hammer'daki thick-wall dalga hizi duzeltmesi: kod t/r>0.1'de 'wave-speed correction is unaffected' diyor; bunu N2O 1 inc borusu icin elle kontrol ettim (thin 488.3 vs thick ~491.7 m/s, %0.7 fark) — ihmal edilebilir buldugum icin bulgu OLARAK YAZMADIM, yanlis alarm riski var.
> 4. materials_db'deki ss_304 dayanim degerleri (sigma_y ~215 MPa cikti, makul) ayri bir kaynak denetimine tabi tutulmadi — o dosya kapsamimda degildi.
> 5. sample_nozzle_inner_contour geometrisinin kendisi (nozzle_design.py) denetlenmedi; yalnizca cikardigi acilarin (konik 15 derece) tutarliligi kontrol edildi.
> 6. Bartz'in kendisi heat_transfer_analysis.py'de yasiyor; katsayi/birim/sigma formu denetlendi ama o dosyanin tam denetimi kapsamim disindaydi.
> 
> NOT ETMEK ISTEDIGIM, BULGU YAZMADIGIM NOKTALAR (yanlis alarm riski nedeniyle):
> - nozzle_flow_1d ayrilmis rejimde CF=1.3409 ile CF_ideal=0.5758'i yan yana raporluyor (2.3x fark). Ikisi FARKLI seyler (biri ayrilmis, digeri tam-yapisik ideal) ve tanimlari kod icinde tutarli; ama kullaniciya aciklamasiz yan yana gosterilmesi kafa karistirici. Fizik hatasi degil, sunum meselesi.
> - nozzle_flow_1d bell lule icin lambda'yi (theta_n+theta_e)/2'de degerlendiriyor; bu Huzel & Huang esdeger-koni yaklasimidir ve kod 'approximate' etiketliyor — dogru uygulama.
> - slosh modulunde fill_height'in tank yuksekligini asip asmadigi kontrol edilmiyor, ama modul tank yuksekligini hic almiyor; tasarim tercihi.
> - kinetic_efficiency'de t_res'in Pc'den bagimsiz cikmasi (rho_c ~ Pc oldugu icin) matematiksel olarak DOGRU, bug degil.

> NOT: ONCELIK SIRASI (geliştirici icin):
> 
> 1. slosh_analysis.py::baffle_damping — Miles bagintisina sqrt(eta/R) genlik terimi eklenmeli ve API'ye bir slosh_amplitude_ratio girdisi (varsayilan ~0.05, NASA SP-8009 tasarim pratigi) acilmali. Su anki hali tek bir halka bafl icin %18.6 kritik sonumleme raporluyor; bu deger fiziksel degil ve tasarimciyi 3x dar bafl secmeye goturur. En yuksek riskli bulgu bu.
> 
> 2. water_hammer.py::analyze — asagi salinim (p_work - dP) hesaplanip sivinin buhar basinciyla kiyaslanmali. FLUID_PROPERTIES tablosuna zaten sivi bazli bir vapor_pressure_Pa alani eklemek yeterli (N2O 293 K: ~50.8 bar, LOX 90 K: ~1.0 bar, RP-1: ihmal edilebilir, su 20 C: 2.3 kPa). Kolon ayrilmasi tespit edilirse status UNSAFE'e cekilmese bile en az bir uyari ve 'Joukowsky bu rejimde ust sinir degildir' notu dusulmeli. LOX orneginde kod sifir uyariyla -46.7 bar mutlak basinc ima ediyor.
> 
> 3. nozzle_flow_1d.py::solve — tek satirlik duzeltme: lambda ve surtunme kesri yalnizca momentum terimine uygulanmali. Etki %0.2-0.4 ama isaret hatasi iceriyor.
> 
> 4. kinetic_efficiency.py — Damkohler'in L* bagimliligi savunulabilir degil; L* yerine lule genisleme zaman olcegine (or. r_bogaz/a*) gecilirse fizik duzelir. Aciliyeti dusuk cunku sonuc zaten ilan edilen bandin icinde ve modul kendi belirsizligini durustce tasiyor.
> 
> GENEL DEGERLENDIRME: Bu dort dosyanin cekirdek gaz dinamigi ve akiskan gecici rejim matematigi CIDDI SEKILDE DOGRU. nozzle_flow_1d'nin izentropik/sok cozucusu NACA 1135'e 6 basamak oturuyor, kutle korunumu 1e-11 mertebesinde, sok eslemesi geri basinci tam yakaliyor. water_hammer'in dort analitik yardimcisi da elle dogrulanabilir kapali formlarla tam eslesiyor. slosh frekans/kutle bagintilari SP-106 ile birebir. Bulunan sorunlar cekirdek denklemlerde DEGIL, cevre modellerinde: eksik bir ampirik carpan (Miles genligi), eksik bir gecerlilik kontrolu (kavitasyon), bir kayip terimi yanlis yere uygulanmis (lambda) ve bir heuristik surucu (Damkohler). Kod genelinde atiflar SAHTE DEGIL — kontrol ettigim her atif (NACA 1135, Anderson, Sutton Es. 3-14/3-30/3-34/8-9/8-22, Wylie & Streeter Es. 1-6/1-10, Summerfield 1954, Bartz 0.26 degil 0.026) gercekten iddia edilen kaynakta var. Bu, denetledigim projeler icinde alisilmadik derecede iyi bir atif hijyeni.
> 
> BIRIM SOZLESMESI: Bu dort dosyada 1000x tipi birim hatasi BULAMADIM. Kritik gecisler tek tek kontrol edildi: from_motor_data bar->Pa (x1e5) dogru; R_UNIVERSAL/MW[g/mol] -> J/(kg.K) dogru; _build_stations mm ile calisip alan oranini boyutsuz uretiyor (mm/mm), sonra alan m^2 boyutuna a_throat_area ile geri donuyor — tutarli; water_hammer mm->m ve bar->Pa donusumleri dogru; slosh tamamen SI. Bartz'a Pc Pa cinsinden gidiyor (h_g mertebesi bunu teyit ediyor).

> DENETLENEN DOSYALAR: hrma/engines/hybrid_rocket_engine.py (1291 satır) ve hrma/analysis/regression_analysis.py (420 satır) — tamamı okundu.
> 
> SATIR SATIR DENETLENEN FONKSİYONLAR:
> - hybrid_rocket_engine.py::__init__ ve ::_set_fuel_properties (yakıt özellikleri, regresyon katsayısı seçimi, G_ox_design varsayılanı, eta_c_star bandı)
> - ::calculate (Isp=CF·c*/g0, mdot=F/(g0·Isp), O/F bölüşümü, At=mdot·c*/(Pc·CD), Ae=At·ε, V_c=L*·At, L* bölümlendirme modeli, m_f/m_f_loaded/sliver, ısı→yapısal zincir bağlantısı)
> - ::_calculate_c_star (delege; c* bant kontrolü ve eta_c_star uygulaması denetlendi, iç termokimya CombustionAnalyzer'ın işi — bu denetimin kapsamı dışı)
> - ::_instantaneous_performance (O/F→c*/Isp önbelleği, sabit-CF varsayımı)
> - ::_calculate_expansion_ratio (SAYISAL SINANDI, analitik izentropikle %0.000 uyum)
> - ::_calculate_thrust_coefficient (SAYISAL SINANDI, 4 nokta Sutton Denk. 3-30/Şekil 3-6 ile uyumlu)
> - ::_get_oxidizer_density (yoğunluk kaynak zinciri ve makulluk pencereleri)
> - ::_design_fuel_grain (enjektör ΔP/Bernoulli, port boyutlandırma, Marxman kapanışı, Euler time-marching, adım tavanı, web tükenme kapısı, G_ox/G_total ortalamaları, m_f_grain)
> - ::_compile_results (birim dönüşümleri, grain_design, injector_design + yedek yol, design_summary geometrisi, L_conv/L_div)
> - regression_analysis.py::regression_rate (SABİT-NOKTA İTERASYONU analitik yakınsama analizi dahil)
> - ::analyze_regression_vs_time (integrasyon ızgarası — off-by-one bulundu)
> - ::compare_fuel_types (yoğunluk taşıma hatası bulundu)
> - Modül sabitleri: LIQUEFYING_FUELS, PRE/POST_CHAMBER_D_FACTOR, PORT_TO_CHAMBER_MAX_RATIO, MAX_BURN_INTEGRATION_STEPS
> 
> SAYISAL OLARAK SINANAN (ölçüm yaptım, tahmin etmedim):
> 1. Doğrulama DB'sinin 151 hibrit kaydından regresyon hızı ölçümü olanları çıkarıp bağımsız bir referans model (log-log fit + 3000 adımlı port integrasyonu) kurdum. Modelim, docs/correlation_report/report.md'deki test-başına hataları BİREBİR üretti (t4l-04 +25.7%, t4l-12 +53.5%, t4l-11 −15.0%, tst −14.3%, t4l-07 −6.9%) — yani teşhis aracı doğrulandı. Ardından bias'ı yakıta, kaynağa ve G bandına ayırdım.
> 2. Gerçek HybridRocketEngine koşuları (F=2 kN, t_b=10 s, O/F=6, Pc=25 bar, HTPB/N2O) flux_mode='ox' ve 'total' için karşılaştırıldı.
> 3. flux_mode etkisinin O/F bağımlılığı 7 O/F noktasında ölçüldü.
> 4. CF ve ε kapalı-form/tablo referanslarıyla karşılaştırıldı.
> 5. analyze_regression_vs_time'ın port çapı 100 000 adımlı referans integrasyonla karşılaştırıldı.
> 
> DENETLEYEMEDİĞİM / SINIRLARIM (dürüst liste):
> - Doran et al. AIAA 2007-5352'nin tablo satırını BİREBİR doğrulayamadım: makalenin varlığını ve künyesini web'den teyit ettim, tam metin ücretli. a=0.132 / n=0.555 değerinin o makaleye ait olduğunu KANITLAYAMADIM. 'pe' girişinin de a=0.132 olması (farklı yakıt+oksitleyici çifti için aynı sayı) şüphelidir; Zilliac & Karabeyoglu AIAA 2006-4504 Tablo 2 PDF'inden yeniden okunmalı. Bu yüzden HTPB katsayısı bulgusunu 'SAHTE_KAYNAK' değil 'YANLIS_KATSAYI' olarak işaretledim — sapma ampirik olarak kanıtlı, atıfın sahteliği DEĞİL.
> - Çok portlu geometri ve boğaz erozyonu etkilerini SAYISAL olarak ölçemedim, çünkü kodda bu parametreler hiç yok; verdiğim rakamlar analitik ölçekleme (r ∝ N^n) ve DB'deki ölçülmüş erozyon (%15 alan) üzerinden mertebe tahminidir, ölçüm değildir.
> - dry_mass_est=0.25·m_total varsayımını referans kovan kütlesi verisi olmadığı için ölçemedim.
> - pe/n2o (11 kayıt) ve abs alt kümelerini istatistiğe sokamadım: bu kayıtlarda başlangıç port çapı ya da yanma süresi yok, adaptör onları zaten 'insufficient' olarak eliyor. Oksitleyici-körlüğü bulgusunun sayısal etkisi bu yüzden yalnız HTPB üzerinden gösterilebildi.
> - CombustionAnalyzer'ın iç termokimyası (c*, gamma, MW, denge çözümü), NozzleDesigner, HeatTransferAnalyzer, StructuralAnalyzer ve injector_design modüllerinin denklemleri BU DENETİMİN KAPSAMI DIŞINDA — yalnız hibrit motordan onlara geçen argümanların birim/anlam tutarlılığını kontrol ettim.
> - Frontend'in /api/regression-analysis'e hangi birimlerle (m mi mm mi) motor_data gönderdiğini KONTROL ETMEDİM (frontend benim işim değil); modülün beklediği birim (metre) docstring'de doğru belgelenmiş.
> - Hiçbir dosyayı değiştirmedim. Geçici hesap betikleri yalnız stdin'den çalıştırıldı, diske yazılmadı.
> 
> GENEL DEĞERLENDİRME: İki dosyanın ÇEKİRDEK denklemleri (izentropik nozul, CF, port büyüme integrasyonu, kütle kapanışı, sabit-nokta iterasyonu, birim dönüşümleri) DOĞRU ve sayısal olarak teyit edildi — birim hatası, 1000x tipi bir hata BULAMADIM. Sorunlar denklem formunda değil, (a) katsayı-akı tabanı uyuşmazlığında, (b) katsayıların geçerlilik zarfının denetlenmemesinde, (c) HTPB katsayısının DB verisine karşı 1.70 kat düşük kalmasında, (d) modellenmeyen fizikte (çok port, boğaz erozyonu) yoğunlaşıyor.

> NOT: İSTENEN ÖZEL TEŞHİS — medAPE %35.1 / bias −%20.2 nereden geliyor?
> 
> CEVAP: FORMÜLDEN DEĞİL, KATSAYIDAN. Ve toplam sayı iki tamamen farklı alt kümeyi gizliyor.
> 
> Yakıta göre ayırdığımda (anomali dışı, high+medium güven kayıtlar):
>   parafin  n=17  bias +%9.4   medAPE %6.9   <- korelasyon mükemmel çalışıyor
>   HTPB     n=43  bias −%39.5  medAPE %46.6  <- tüm hata burada
> Kaynağa göre HTPB: carmicino2013 n=25 bias −%33.3 ; rezaei2018 n=18 bias −%48.0. İki bağımsız kampanya da aynı yönde, yani tek bir şüpheli veri kümesi değil.
> 
> Formül formu elenmiştir:
> - n=0.555 SABİT tutulup DB'nin HTPB kayıtlarına en iyi a arandığında a=6.24e-5 çıkıyor, koddaki 3.68e-5'in 1.70 KATI. Yani tek serbestlik derecesi (a) sapmayı büyük ölçüde kapatıyor — formun kendisi bozuk olsaydı sabit bir çarpan yetmezdi.
> - Eksik L^m terimi ana neden OLAMAZ: r ∝ L^-0.2 ile %70'lik açığı kapatmak için grain boyu oranının 1.7^-5 ≈ 0.07 olması gerekirdi, fiziksel değil.
> - G bandına göre bias monoton: G<100 → −%48.9, 100-300 → −%35.6, >300 → −%19.7. Yani geçerlilik zarfı dışına çıkış (Doran fitinin ~10-30 g/cm²s aralığı, DB'de 3.5-52 g/cm²s var) sapmayı BÜYÜTÜYOR ama zarf içinde de −%35 kalıyor — zarf tek başına açıklamıyor, katsayı seviyesi de düşük.
> 
> BIAS'IN NEGATİF OLMASININ ANLAMI (mühendislik sonucu):
> bias = (tahmin − ölçüm)/ölçüm olduğu için negatif = model regresyonu DÜŞÜK tahmin ediyor. Zinciri: r düşük → mdot_f düşük → O/F yüksek tahmin ediliyor → grain hedef debiyi tutturmak için ~%25 FAZLA UZUN boyutlandırılıyor. Gerçekte:
>   1. O/F tasarımın ALTINA düşer (fazla yakıt), Isp optimumdan kayar;
>   2. web tahminden ~%25 DAHA ERKEN tükenir. Model "web dayanır" derken kovan yanma bitmeden delinebilir. Bu GÜVENLİ OLMAYAN yöndür ve regresyon hızı sayısı kullanıcıya doğrudan gösterildiği için user_visible'dır.
> 
> İLGİNÇ VE ÖNEMLİ: İKİ HATA BİRBİRİNİ KISMEN KAPATIYOR.
> Doğrulama katmanı flux_mode='ox' zorluyor ve orada bias −%20.2 çıkıyor. Ama kullanıcıya giden VARSAYILAN tasarım yolu flux_mode='total' ve bu, r_dot'u O/F=6'da ölçtüğüm gibi +%9.8 (O/F=2'de +%32.6) yukarı itiyor. Yani ürün varsayılanında görünür bias yaklaşık −%13'e iniyor — ama FİZİKSEL OLARAK YANLIŞ bir taban uyuşmazlığı sayesinde. Kapanma O/F'ye bağlı olduğu için saçılmayı (medAPE) düzeltmiyor, sadece ortalamayı maskeliyor. Projenin kendi doğrulama katmanı 2026-07-18'de bu tabanı açıkça reddetmiş ('(1+1/OF)^n = 1.15-1.36 sistematik çarpanı bindirir' yorumu record_adapters.py içinde duruyor) ama aynı karar tasarım yoluna taşınmamış. Bu, 2026-07-13'teki "G_total bilinçli karar" kaydının ARTIK GEÇERSİZ olduğunun kanıtıdır: gerekçe "Marxman teorisi G_total kullanır" idi, doğru; ama HRMA'nın katsayıları Marxman'ın teorik katsayıları değil, G_ox tabanlı deneysel fitler. Teori ile fit tabanı karıştırılmış.
> 
> ÖNERİLEN SIRA (Berke'ye): (1) tasarım varsayılanını 'ox' yap — doğrulama katmanıyla aynı tabana gel, ölçülebilir ve tek satırlık; (2) katsayı tablosuna (yakıt, oksitleyici) anahtarı + geçerli G aralığı alanı ekle, aralık dışında uyar; (3) regression_rate_avg'ı (D_f−D_i)/(2·t_b) olarak raporla — model D_f'yi zaten hesaplıyor, bedelsiz ve deney tanımıyla birebir; (4) HTPB katsayısını yeniden kaynaklandır (Doran PDF'i + Zilliac Tablo 2 birebir okunsun) — DB'ye FİT ETME, bu "asla uydurma" ilkesini çiğner; yayımlanmış başka bir HTPB/N2O korelasyonu daha uygunsa onu atıflı olarak ekleyin ve iki korelasyon arasındaki farkı belirsizlik olarak raporlayın.
> 
> DÜRÜSTLÜK NOTU: docs/correlation_report/COMMENTARY.md bu sınırlamayı zaten doğru teşhis etmiş ve hiçbir katsayının doğrulama verisine fit edilmediğini açıkça yazmış. Yani bu bir gizlenmiş hata değil, BİLİNEN bir sınırlama. Benim eklediğim: (a) sapmanın yakıt/kaynak/G-bandı ayrışımının sayısal ölçümü, (b) formül formunun ve L^m eksikliğinin eleme yoluyla dışlanması, (c) tasarım varsayılanı ile doğrulama varsayılanının çeliştiğinin tespiti, (d) r_dot_avg tanımının deney tanımıyla uyuşmadığının ve gerçek sapmayı %5.8 maskelediğinin ölçümü.

> DENETLENEN (satır satır okundu + çoğu sayısal olarak sınandı):
> 
> six_dof_trajectory.py — TAMAMI (651 satır). _atmosphere, _drag_coefficient_mach, BarrowmanAero.__init__/static_margin, _quat_to_dcm, _quat_derivative, _quat_from_elevation_azimuth, _coriolis_acceleration, SixDOFTrajectory.__init__/_thrust_at/_mass_at/_cg_at/_inertia/_derivatives/solve. Sayısal sınamalar: (a) atmosfer vs USSA 1976 tablosu 5 irtifada, (b) quaternion sırası sonlu-fark DCM testiyle, (c) Coriolis 4 yön/enlem senaryosu + bağımsız referans hesap, (d) enerji korunumu (sürüklemesiz serbest uçuş), (e) adım duyarlılığı 3 max_step, (f) pitch sönüm momenti doğrudan moment testi, (g) restoratif moment analitik karşılaştırma, (h) Barrowman elde tam türetme, (i) enlem taraması ile sürüklenme, (j) rakım ofseti ile apoje duyarlılığı, (k) kuru kütle duyarlılığı, (l) iki modülün Cd(M) eğrilerinin karşılaştırması.
> 
> trajectory_analysis.py — fizik kısmının TAMAMI. set_launch_site, _drag_coefficient_mach, _wind_vector, calculate_trajectory, _aero_drag_components, _calculate_powered_flight, _calculate_coasting_flight, _calculate_descent_flight, _combine_flight_phases, _calculate_performance_metrics, _atm_full, _get_atmospheric_properties. Uçtan uca çalıştırılıp yanma-sonu/apoje/iniş metrikleri gerçek değerlerle karşılaştırıldı.
> 
> flight_vehicle.py — TAMAMI, ama bu dosya fizik denklemi değil BİRİM/ALAN eşleme katmanı. Her birim iddiası (hybrid m, solid/liquid mm; kg/s·s=kg; mm+mm) motor modüllerinin kaynak satırlarına grep'le tek tek doğrulandı. recompute_from_project ve _recompute_* fonksiyonları OKUNDU ama ÇALIŞTIRILMADI (tam motor turu gerektiriyor); parametre adı/varsayılan eşlemesi denetlenmedi — o iş girdi-doğrulama ekibinin.
> 
> DENETLEYEMEDİĞİM / EMİN OLAMADIĞIM:
> 1. "Niskanen 2009 §4.2.3" atfını doğrulayamadım (belge depoda yok, çevrimdışı çalıştım). C_mq'nun 2 kat eksik olduğunu ELDE TÜRETEREK ve SAYISAL MOMENT TESTİYLE gösterdim; bölüm numarasının yanlış olduğunu iddia etmiyorum, doğrulayamadım diyorum.
> 2. Barrowman sonucunu gerçek bir uçuş/OpenRocket koşusuyla karşılaştıramadım — yalnız Barrowman denklemlerinin elde türetilmiş haliyle karşılaştırdım. Yani "kod denklemi doğru uyguluyor" doğrulandı; "denklem bu araç için doğru sonuç veriyor" doğrulanmadı.
> 3. İtki-irtifa düzeltmesinin (p_e−p_a)A_e etkisini ÖLÇEMEDİM çünkü A_e uçuş modeline hiç aktarılmıyor; verdiğim %5 rakamı tipik ε=4 nozul üzerinden ANALİTİK TAHMİNDİR.
> 4. Sıkıştırılabilirlik (Prandtl-Glauert / süpersonik kanat teorisi) etkisini ölçemedim; kodda karşılaştırılacak Mach'lı referans yok. Verdiğim "%60 eğim düşüşü" 2B ince profil teorisinden gelen büyüklük mertebesidir, bu geometri için hesaplanmış değer değildir.
> 5. Jet sönümünün uçuş çıktısına etkisini ölçemedim (terim kodda yok, yamalamadan eklenemez). Yalnız moment/(rad/s) mertebesini karşılaştırdım.
> 6. El-ellilik (handedness) sorununun ölçülebilir etkisini BULAMADIM ve bunu dürüstçe bildiriyorum: roll hiç uyarılmadığı için gyroscopic terim özdeş sıfır. Ayna-görüntüsü kuplajın hangi senaryoda ortaya çıkacağını analitik olarak açıkladım, sayısal kanıt üretemedim.
> 7. Kapsam dışı bıraktım (talimat gereği): import/frontend/güvenlik/i18n, create_trajectory_plots görselleştirmesi, app.py endpoint sözleşmeleri (yalnız latitude_deg'in geçirilmediği fiziksel sonucu kaydettim), tile_cache.py, input_guard.py.

> NOT: ÖNCELİK SIRASI (düzeltme için önerim):
> 1. trajectory_analysis yanma-sonu metrikleri — tek satırlık örnekleme düzeltmesi, %84'lük yanlış sayı gidiyor. En yüksek fayda/risk oranı.
> 2. 6-DOF'a launch_altitude parametresi — %7.65 apoje hatası, v2.6.2'nin fırlatma sahası entegrasyonuyla zaten aynı dalgada.
> 3. latitude_deg'in çağıran katmandan geçirilmesi + geçmezse coriolis=False'a düşülmesi. Şu anki hâl "Coriolis eklendi" diyor ama herkese ekvator uyguluyor.
> 4. C_mq ×2 ve g_local — küçük ama kesin, düşük riskli.
> 
> DÜRÜSTLÜK NOTU: Bu modüller genel olarak İYİ durumda. 2026-07-13'te düzeltilen quaternion sırası hâlâ doğru (6 mertebe farkla teyit), Coriolis'in yönü dört senaryoda da doğru, Barrowman denklemleri 5 hanede birebir, atmosfer USSA 1976'ya %0.008 içinde, entegratör enerjiyi 7.4e-9 bağıl hassasiyetle koruyor ve flight_vehicle'da 1000x sınıfı bir birim hatası YOK. Bulguların çoğu "eksik terim / geçerlilik zarfı / raporlama anı" sınıfında; gerçek anlamda YANLIŞ YAZILMIŞ denklem sayısı iki (C_mq katsayısı ve tekdüze I_t'nin paralel-eksen eksiği), ikisinin de ölçülen uçuş etkisi %0.3'ün altında.
> 
> BULGU ÜRETMEK İÇİN ZORLAMADIĞIM YERLER: _mass_at'in C1 perf yeniden yazımını bit-aynılık iddiasıyla birlikte okudum, matematiği doğru (np.trapz segment sırası korunmuş); thrust_curve doğrulaması, ray fazı kuvvet izdüşümü, apoje/tumble olay fonksiyonları, rüzgâr vektörünün 6-DOF'taki kurulumu, çift-sayım ayrımı (atıl vs propelan) — hepsi doğru, bulgu yazmadım.
> 
> Geçici hesap betikleri: /private/tmp/claude-501/-Users-apple-Desktop-dosyalar-HRMA/de50138d-c13a-49d0-b62c-0c3699c94c32/scratchpad/t1.py … t8.py (hiçbir proje dosyası değiştirilmedi).

> DENETLENEN (satır satır, 3 dosyanın TAMAMI okundu — 1216 + 356 + 294 satır):
> 
> cycle_power_balance.py — denetlenen fonksiyonlar: _w, _norm_fuel, _norm_ox, _get_cea, preburner_gas_properties, solve_preburner_of, _turbine_specific_work, _turbine_exit_temp, _pump_power_w, _exhaust_isp_s, _flow_split, _shaft_dict, _pump_dict, _turbine_dict, solve_cycle (6 çevrim dalının HEPSİ: pressure_fed, gas_generator, tap_off, staged_combustion, full_flow_staged_combustion, expander). Ayrıca modül düzeyi 20+ sabitin her biri (TIT_DEFAULT_K, TIT_UNCOOLED_LIMIT_K, TIT_OX_RICH_LIMIT_K, INJECTOR_DP_FRAC_*, OPEN_CYCLE_TURBINE_PR_*, STAGED_PR_TYPICAL, PR_SOLVE_*, ETA_PUMP_DEFAULT, ETA_TURBINE_*, BLEED_FRACTION_*, DENSITY_NBP_KG_M3, FUEL_MOLAR_MASS_KG_KMOL, FUEL_NBP_K, _BTU_LBM_R_TO_J_KG_K, _BAR_TO_PSIA) kaynak/birim açısından tek tek kontrol edildi. FFSC kapalı-form akış bölüşümü (x, y, denom) cebirsel olarak elle türetilip koddaki ifadeyle karşılaştırıldı — DOĞRU (sayısal olarak da doğrulandı: x=8.43 kg/s).
> 
> pressurant_sizing.py — gas_properties, regulated_pressurant, blowdown_pressurant, autogenous_pressurant, analyze_pressurant + GAS_PROPERTIES / AUTOGENOUS_GAS / AUTOGENOUS_FEED_TEMP_K sabitleri. Özgül gaz sabitleri elle doğrulandı (He 2077.3, N2 296.80, GOX 259.8, GCH4 518.3, GH2 4124 — hepsi R_UNIVERSAL/M ile tutarlı); gaz cp değerleri NIST ile karşılaştırıldı (GOX 918 vs 918, GCH4 2230 vs 2226, GH2 14300 vs 14307 — DOĞRU).
> 
> tank_blowdown.py — N2OSaturation (8 özellik metodu), N2OTankBlowdown.__init__, from_oxidizer_mass, _split_masses, _internal_energy, pressure, step, _begin_vapor_phase, _vapor_step, _pack_state, simulate + gömülü _SAT_TABLE'ın 23 satırının TAMAMI.
> 
> SAYISAL SINAMA YAPILDI (scratchpad'de 8 betik; rocketcea 1.2.1 + CoolProp 6.8.0 kurulu, gerçek çalıştırma):
> - Raptor FFSC (Pc=300, mdot=650, MR=3.6) + 10 girdi duyarlılık senaryosu
> - RS-25 staged combustion (Pc=206.4, mdot=514.5, MR=6.03) — yayımlanan HPFTP gücü, FPB basıncı, FPB O/F ile karşılaştırma
> - F-1 gaz jeneratörü (Pc=70, mdot=2578, MR=2.27)
> - RD-180 benzeri ORSC (Pc=261.7, mdot=1250, MR=2.72)
> - RL10 benzeri expander, 8 farklı rejeneratif ısı yükü
> - N2O tank blowdown (16.5 kg, 293 K ve 253 K), kütle korunumu + tablo doğrulama
> - Basınçlandırma: kod çıktısı vs kapalı-form + CoolProp gerçek gaz Z
> 
> SORULAN "779 BAR TESADÜF MÜ" SORUSUNUN CEVABI: Kod 776.3 bar veriyor (bellekteki 779 ile aynı mertebede). TESADÜF DEĞİL — zincir yapısal olarak kapanıyor: Pc 300 -> p_türbin_çıkış 345 -> güç dengesinden PR_ox=1.952 -> ön yakıcı 673.3 -> ×1.15 enjektör -> +2 hat -> 776.3 bar; güç artığı 2.3e-15 (gerçekten kapanıyor, ox türbin 46.0 MW = ox pompa 45.97 MW). Ayrıca sonuç ÖLÇEKTEN BAĞIMSIZ (mdot 650->750 yapıldığında basınçlar birebir aynı kalıyor, yalnız güç ölçekleniyor) — yani basınç zinciri tamamen Pc, MR, verimler ve ΔP oranlarının fonksiyonu. AMA doğruluğu tamamen VARSAYILAN VERİMLERE bağlı: eta_t 0.78->0.85'te 668.7 bar, eta_p 0.75->0.85'te 640.1 bar, TIT_f 1050'de 865.5 bar. Yayımlanan 600-850 bar bandına düşmesi savunulabilir varsayımların ORTASINDA olmasından; bandın ±%13'lük iç oynaklığı var. Kritik zayıflık ayrı bulgu olarak raporlandı: eta_pump=0.65 (dosyanın kendi alıntıladığı bandın alt ucu) veya preburner ΔP=0.25 verildiğinde gerçek bir motor 'infeasible' ilan ediliyor.
> 
> KAYNAK DOĞRULAMA — YAPILAN: NASA SP-8110 belgesi NTRS'ten indirildi (19.5 MB, 160 sayfa), OCR metni çıkarıldı, alıntı BİREBİR bulundu (s.15-17): "efficiencies vary from 35 to 65 percent. Staged-combustion and expander-cycle turbines are capable of attaining efficiencies above 80 percent..." Koddaki atıf DOĞRU, uydurma değil.
> 
> DENETLENEMEYEN / EMİN OLAMADIĞIM NOKTALAR (dürüst liste):
> 1. RS-25 HPFTP %81.1 / HPOTP %74.6 rakamları: 'Boeing/Rocketdyne SSME Orientation 1998' PDF'i (large.stanford.edu) 4 ayrı denemede de yarım indi (4.4 MB -> 1.5 MB -> 1.0 MB), doğrulanamadı. UYDURMA OLDUĞUNA DAİR KANIT YOK — 'doğrulanamadı' diye işaretledim, 'sahte kaynak' DEMİYORUM.
> 2. Sutton 'Eq. 6-1' ve 'Table 10-3' numaralandırmaları: kitap elimde yok, numaraları doğrulayamadım. Basınçlandırma bulgusunda kapalı formu enerji dengesinden BAĞIMSIZ olarak kendim türetip karşılaştırdım; numaralandırma iddiasını değil, denklemin İÇERİĞİNİ denetledim.
> 3. NASA SP-8089 (enjektör ΔP 0.15-0.20 bandı) ve SP-8107 atıfları: belgeler indirilmedi, doğrulanamadı. Bu bantlar sektör pratiğiyle uyumlu göründüğü için bulgu üretmedim.
> 4. Yakıt-zengin CH4 ön yakıcısında O/F=0.268'de CEA'nın katı karbon (is) öngörüp öngörmediğini ve bunun frozen cp / MW değerlerini nasıl etkilediğini kontrol EDEMEDİM (rocketcea'nın kondanse faz raporlaması bu API'den okunamıyor). cp=3629 J/kgK NIST CH4 değeriyle uyuştuğu için sorun görünmüyor ama kesin değilim.
> 5. Ön yakıcı gerçek gaz etkisi (500-700 bar): CEA ideal gaz varsayımının getirdiği sapmayı yalnız Z ile mertebe olarak tahmin ettim (%3-8), gerçek karışım EOS ile ÖLÇMEDİM.
> 6. Tap-off tabaka O/F tutarsızlığını sayısallaştıramadım (model bu dosyada yok).
> 7. Autogenous ullage-çökme faktörünü ölçemedim (bu modülde modellenmiyor); yalnız kodun kendi alıntıladığı 1.0-1.6 bandını referans aldım.
> 
> KAPSAM DIŞI BIRAKILAN (görev tanımı gereği): import/frontend/güvenlik/i18n konularına HİÇ bakmadım. Uyarı kodlarının frontend'de çevrilip çevrilmediğini denetlemedim. Hiçbir dosya DEĞİŞTİRİLMEDİ; scratchpad'e yazılan 8 geçici betik ve indirilen PDF'ler dışında iz bırakılmadı (PDF'ler silindi).

> NOT: EN ÖNEMLİ İKİ BULGU (öncelik sırası):
> 
> 1) EXPANDER GAMMA HATASI (YUKSEK) — cycle_power_balance.py expander dalı yoğun süperkritik akışkana ideal gaz gamma'sı uyguluyor; metan expander'da türbin işi %+42.9 fazla çıkıyor. CoolProp zaten import edilmiş durumda, düzeltme 2 satır: izentropik entalpi düşümünü doğrudan al (s1=S(T,p); h2s=H(p/PR,s1); dh=eta*(h1-h2s)). Bu değişiklik SADECE expander dalını etkiler — GG/staged/FFSC dallarına DOKUNMAYIN, orada bağıntı geçerli ve RS-25'e karşı doğrulandı.
> 
> 2) FFSC OX MİLİ TIT'İ KAPALI (YUKSEK) — tit_ox koşulsuz 750 K; kullanıcının tit_K'si yalnız yakıt miline gidiyor. Bu, gerçek motorların 'infeasible' çıkmasının ana sebebi. Ayrı bir tit_ox_K parametresi (varsayılan 750, sınır TIT_OX_RICH_LIMIT_K=850) açılması yeterli.
> 
> DÜZELTME YAPILIRKEN BOZULMAMASI GEREKENLER (bunlar DOĞRULANMIŞ, dokunmayın):
> - _pump_power_w ve _turbine_specific_work: RS-25'e karşı doğrulandı (FPB basıncı %0.2, HPFTP gücü %2 sapma). Bunlar sağlam.
> - tank_blowdown.py sıvı fazı ve gömülü doygunluk tablosu: tablo CoolProp ile %0.000 uyuşuyor, kütle korunumu %0.02. Sağlam.
> - FFSC kapalı-form akış bölüşümü (x, y, denom): cebirsel türetme DOĞRU.
> - Birim dönüşüm sabitleri (4186.8, 14.503773773, /1.8): hepsi kesin değerlerle DOĞRU.
> - NASA SP-8110 atfı: birebir doğrulandı, SAHTE DEĞİL. Bu yorum bloğunu silmeyin/değiştirmeyin.
> 
> BİRİM DENETİMİ SONUCU: Bu üç dosyada 1000x tipi birim hatası BULUNAMADI. Basınçlar tutarlı biçimde bar (PA_PER_BAR ile Pa'ya çevriliyor), pressurant_sizing.py tutarlı biçimde SI (Pa/m3/K), tank_blowdown.py tutarlı biçimde SI. Kritik dönüşümlerin hepsi tek tek doğrulandı. Bu üç dosya, projenin bilinen 'katı mm / sıvı karışık' birim sorunundan etkilenmemiş.
