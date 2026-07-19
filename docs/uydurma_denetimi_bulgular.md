# HRMA uydurma veri denetimi — bulgu defteri

Tarih: 2026-07-19. Denetim TAMAMLANDI (4/4 ajan).

Tetikleyen: teknik çizimde uydurma itki eğrisi ve enjektör hover metninde
rastgele gürültü bulunması. Berke kararı: yayın durdu, önce bu defter kapanacak.
İkinci karar: **hiçbir panel kaldırılmayacak** — her biri gerçek hesapla beslenecek,
hesap mümkün değilse dürüst etiketle kalacak.

Ölçüt: *kullanıcı bu sayının kendi girdisinden hesaplandığına inanır mı?*
İnanıyorsa ve hesaplanmıyorsa bulgudur. Kaynaklı fiziksel sabitler, etiketli
tahminler ve tohumlanmış Monte Carlo bulgu DEĞİLDİR.

Toplam 65 bulgu: 12 kritik, 39 major, 14 minor.


---

## Kritik

### hrma/engines/liquid_rocket_engine.py:15-18 (LiquidRocketEngine.__init__) + hrma/app.py:1552-1560
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Sıvı motor formundaki ~55 sayısal girdinin tamamı motora HİÇ ulaşmıyor. Constructor yalnız thrust, chamber_pressure, mixture_ratio, fuel_type, oxidizer_type, cooling_type, injector_type parametrelerini kabul ediyor; /calculate_liquid de sadece bu 7'sini gönderiyor. liquid.html:3300-3366 arası gönderilen cooling_channels, characteristic_length (L*), nozzle_expansion_ratio, throat_diameter, chamber_diameter, contraction_ratio, injector_elements, injector_pressure_drop, discharge_coefficient, combustion_efficiency, max_wall_temp, safety_factor, chamber_wall_thickness, fuel/oxidizer_injection_velocity, fuel/oxidizer_orifice_diameter, chamber_material, feed_pressure, turbopump_efficiency ... hepsi sessizce çöpe gidiyor.

**Kullanıcı etkisi:** Kullanıcı 'Nozzle Expansion Ratio = 50', 'Cooling Channels = 80', 'L* = 1.2 m', 'Injector Pressure Drop = 20 bar', 'Combustion Efficiency = %97' gibi onlarca alanı doldurup Calculate'e basıyor. Hiçbiri sonucu değiştirmiyor. Sonuç sayfasında görünen expansion ratio, kanal sayısı, orifis çapı motorun kendi iç varsayımlarından geliyor — kullanıcı kendi tasarım kararlarının hesaba girdiğine inanıyor.

**Kanıt:** app.py:1552-1560 -> `engine = LiquidRocketEngine(thrust=..., chamber_pressure=..., mixture_ratio=..., fuel_type=..., oxidizer_type=..., cooling_type=..., injector_type=...)` — `data` sözlüğündeki diğer hiçbir anahtar geçirilmiyor (katı motorda yapılan `overrides=data` bağlantısı sıvıda YOK).
Sayısal kanıt (Flask test client, /calculate_liquid; isp_sea_level, isp_vacuum, c_star, throat_diameter, exit_diameter, expansion_ratio, chamber_diameter, chamber_length, total_mass_flow, thrust_to_weight, engine_mass imzası karşılaştırıldı):
  cooling_channels 80->300  ETKİSİZ
  characteristic_length 1.2->3.0  ETKİSİZ
  nozzle_expansion_ratio 50->12  ETKİSİZ
  injector_elements 100->400  ETKİSİZ
  discharge_coefficient 0.7->0.4  ETKİSİZ
  injector_pressure_drop 20->60  ETKİSİZ
  chamber_diameter 200->500  ETKİSİZ
  throat_diameter 50->120  ETKİSİZ
  contraction_ratio 4->10  ETKİSİZ
  max_wall_temp 800->1200  ETKİSİZ
  safety_factor 2.5->6.0  ETKİSİZ
  chamber_wall_thickness 5->20  ETKİSİZ
  fuel_injection_velocity 25->60  ETKİSİZ
  combustion_efficiency 97->70  ETKİSİZ
(14/14 girdi tamamen etkisiz; imzanın tek bir hanesi bile değişmiyor.)

**Önerilen çözüm:** Katı motorda uygulanan desenin aynısı: LiquidRocketEngine'e `overrides=None` parametresi + `_override_val(key, lo, hi)` / `_apply_overrides()` ekle ve app.py:1552'de `overrides=data` geçir. Fiziksel olarak bağlanabilecekler (L*, expansion_ratio, contraction_ratio, cooling_channels, injector dp/Cd/element sayısı, max_wall_temp, safety_factor, yield/malzeme) gerçekten hesaba girsin. Bilinçli olarak bağlanmayacak alanlar UI'da 'informational / not used in solver' etiketiyle işaretlensin veya formdan kaldırılsın.

### hrma/engines/liquid_rocket_engine.py:2313-2331 (_calculate_thermal_protection_system)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Rejeneratif soğutma tasarımının TAMAMI sabit: cooling_channels=180, channel_dimensions='2mm x 3mm', coolant_velocity=15 m/s, wall_temperature=800 K, heat_flux=50 MW/m², pressure_drop=8 bar, temperature_rise=150 K. Hiçbiri itki, oda basıncı, yakıt, kütle debisi veya geometriyle değişmiyor. Üstelik aynı motorda calculate_cooling_requirements() GERÇEK Bartz hesabı yapıyor ve tamamen farklı sayılar üretiyor.

**Kullanıcı etkisi:** Sıvı motor sonuç sayfasındaki 'Thermal Protection' kartında (liquid.html:3990-4001) kullanıcı şunu görüyor: Channel Count 180, Coolant Velocity 15.0 m/s, Heat Flux 50.0 MW/m², Wall Temperature 800 K, Temperature Rise 150 K, Pressure Drop 8.0 bar. Bunları kendi motorunun soğutma tasarımı sanıp kanal sayısı/soğutucu debisi kararı veriyor. Aynı sayfanın başka bir yerinde (liquid.html:2112-2120 ve PDF raporu satır 4433) gerçek hesaptan gelen ÇELİŞKİLİ değerler duruyor.

**Kanıt:** Kod: `if self.cooling_type == 'regenerative': return {'cooling_channels': 180, 'coolant_velocity': 15, 'wall_temperature': 800, 'heat_flux': 50, 'pressure_drop': 8, 'temperature_rise': 150}`
Sayısal kanıt (/calculate_liquid):
  10 kN / 100 bar -> thermal_protection = {cooling_channels:180, coolant_velocity:15, heat_flux:50, wall_temperature:800, pressure_drop:8, temperature_rise:150}
  250 kN / 200 bar -> thermal_protection = {cooling_channels:180, coolant_velocity:15, heat_flux:50, wall_temperature:800, pressure_drop:8, temperature_rise:150}  (BİRE BİR AYNI)
Aynı 10 kN koşusunda GERÇEK hesap (cooling_system):
  cooling_channels=80, peak_heat_flux=80996.8, coolant_temperature_rise=390.5 K, cooling_pressure_drop=0.035 bar, chamber_heat_flux=8714.2
Yani ekranda 180 kanal / 50 MW/m² / 8 bar / 150 K yazarken, gerçek modül 80 kanal / ~81 MW/m² tepe akı / 0.035 bar / 390.5 K diyor.

**Önerilen çözüm:** _calculate_thermal_protection_system'ı sabit sözlük döndürmekten çıkar; calculate_cooling_requirements() sonucundan (kanal sayısı, tepe akı, cidar sıcaklıkları, soğutucu ΔP ve ΔT) türet. Tek doğruluk kaynağı cooling_system olsun; thermal_protection yalnız o sonucun sunum katmanı olsun. Türetilemeyen kalemler (kanal kesiti gibi) 'assumed / design guideline' etiketiyle verilsin.

### hrma/engines/liquid_rocket_engine.py:2143-2225 (_generate_performance_optimization_maps)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Isp-vs-O/F ve c*-vs-O/F 'optimizasyon haritaları' yanma çözücüsüyle hiç konuşmuyor; sabit tepe değerlere (isp_max=353, cstar_max=1823 — RP-1/LOX için gömülü; diğer tüm yakıt çiftleri için 350/1800) uydurma bir parabol uygulanarak üretiliyor: mr_efficiency = 1 - 0.15*((mr-optimal_mr)/optimal_mr)^2. Basınç haritası da aynı şekilde uydurma (pc_factor = min(1.1,(pc/100)^0.1)) ve irtifa haritasındaki thrust_vs_alt = F*isp_improvement fiziksel bir bağıntı değil.

**Kullanıcı etkisi:** Sıvı motor 'Performance Maps' sekmesinde kullanıcı 'Performance vs Mixture Ratio' Plotly grafiğini görüyor (liquid.html:2507-2526) ve buradan O/F seçiyor. Grafik, aynı sayfada raporlanan gerçek Isp ile tutarsız. Metan/LOX'ta grafik ~350 s tepe gösterirken sayfanın üstünde Vacuum Isp = 376.8 s yazıyor — 27 saniyelik sahte fark. Kullanıcı O/F optimizasyonunu yanlış eğriye göre yapıyor.

**Kanıt:** Kod: `if self.fuel_type=='rp1' and self.oxidizer_type=='lox': optimal_mr=2.56; isp_max=353; cstar_max=1823  else: optimal_mr=2.0; isp_max=350; cstar_max=1800` ardından `mr_efficiency = 1 - 0.15*((mr-optimal_mr)/optimal_mr)**2` ve `isp_vs_mr.append(isp_max*mr_efficiency)`.
Sayısal kanıt (/calculate_liquid):
  RP-1/LOX 10 kN: harita isp_vs_mr[0:5] = [343.92, 346.04, 347.87, 349.42, 350.70]; cstar_vs_mr[0:3] = [1776.1, 1787.0, 1796.5]; gerçek hesap isp_vacuum = 353.15, c_star = 1823.16
  Metan/LOX 10 kN: harita isp_vs_mr[0:5] = [346.72, 348.22, 349.26, 349.85, 349.99] (tepe ~350); gerçek hesap isp_vacuum = 376.81
Harita metan için LOX/RP-1 dışı 'else' dalına düşüp 350/1800 sabitlerini kullanıyor, yakıt kimyasını hiç görmüyor.

**Önerilen çözüm:** Haritaları CombustionAnalyzer/CEA taramasıyla üret (hibrit tarafındaki /api/optimum-of deseni: her O/F için analyze_combustion çağrısı, aynı c*/Isp zinciri). Bu maliyetliyse en azından tasarım noktasındaki gerçek Isp/c*'a normalize et ve grafiğe 'scan of the same combustion solver' etiketi koy. Hiçbir koşulda gerçek sonuçla çelişen sabit tepe değer kullanılmasın.

### hrma/visualization/visualization.py:1564 (create_combustion_analysis_plots), UI: static/js/app.js:618 → templates/advanced.html:1706 #combustionAnalysisPanel
*Kapsam: Analiz modülleri*

**Uydurma olan:** "Combustion Analysis" panosunun TEK sayısal çıktısı olan "Combustion Efficiency" göstergesi her zaman %95.0 gösteriyor. `combustion_data.get('combustion_efficiency', 0.95)` — CombustionAnalyzer.analyze_combustion() bu anahtarı HİÇ üretmiyor (döndürdüğü anahtarlar: compositions, conditions, elemental_composition, equivalence_ratio, performance, stoichiometric_of). Panonun diğer 3 çeyreği (Chemical Equilibrium, Flame Temperature Profile, O/F Ratio Optimization) de beklenen anahtarlar hiç üretilmediği için tamamen BOŞ çiziliyor.

**Kullanıcı etkisi:** Hibrit sayfasında "Combustion Analysis" paneli açılıyor, başlık altındaki açıklama "seçilen yakıt çifti için kimyasal denge ve yanma kalitesi" diyor. Kullanıcı O/F'yi, Pc'yi, yakıtı değiştiriyor; gösterge hep %95 kalıyor ve bunu kendi motorunun hesaplanmış yanma verimi sanıyor. Ayrıca delta referansı 95 olduğu için "hedefte" izlenimi veriyor.

**Kanıt:** Kod: `efficiency = combustion_data.get('combustion_efficiency', 0.95)` → `go.Indicator(value=efficiency*100, title={'text': "Combustion Efficiency (%)"}, delta={'reference': 95})`.
Çalıştırılan kanıt (gerçek CombustionAnalyzer çıktısıyla):
  O/F 2.0 Pc 10.0 -> traces: 1 [('indicator', 95.0)]
  O/F 6.0 Pc 20.0 -> traces: 1 [('indicator', 95.0)]
  O/F 12.0 Pc 50.0 -> traces: 1 [('indicator', 95.0)]
Figürde toplam 1 trace var — yani panonun görünen tek verisi bu sabit.

**Önerilen çözüm:** Ya gerçek c* verimini bağla (combustion_analysis['performance']['eta_c_star'] / c_star_delivered zaten var), ya da anahtar yoksa göstergeyi HİÇ çizme ve panelde "Combustion efficiency not computed" yaz. Boş çeyrekler için de veri yoksa panelin tamamını gizle (renderOptionalPlot zaten destekliyor).

### hrma/visualization/visualization.py:2206-2336 (create_nozzle_mach_area_ratio_contour); UI: static/js/panels/performance_panel.js:29 → /api/advanced-performance-analysis
*Kapsam: Analiz modülleri*

**Uydurma olan:** Mach alanı hem uydurma bir geometriden (boğaz nozul boyunun %10'unda sabit, alan dağılımı ((x-0.1)/0.9)**0.8 keyfi, gamma=1.25 sabit, duvar yakınında %30 keyfi Mach azaltımı) hem de YAKINSAMAYAN bir Newton iterasyonundan geliyor (türev formülü yanlış). Sonuç Mach değerleri fiziksel olarak imkânsız. Grafik "NASA-STD-5012 Compliant Design" alt başlığıyla sunuluyor ve panel bilgi kartı "NASA-STD-5012 Pressure Vessels & Pressurized Systems" referansını gösteriyor.

**Kullanıcı etkisi:** Analiz Güvertesi > Advanced Performance panelinde "Nozzle Mach Number Distribution & Flow Analysis" konturu çiziliyor, "Potential Shock Zone" anotasyonu ekleniyor. Kullanıcı kendi boğaz alanı/genişleme oranını girdiği için çıkan Mach dağılımının kendi lülesine ait olduğuna inanır ve aşırı/eksik genişleme kararını buna göre verir. Kontur seviyeleri 0.5-4.0 aralığına sabitlendiği için grafik makul GÖRÜNÜYOR, altındaki sayılar çöp.

**Kanıt:** Kod: `mach_guess = 2.0*np.sqrt(area_ratio-1)`; `df = -1/mach_guess**2 * (...)` (zincir kuralı terimi eksik) → ıraksama.
Çalıştırılan kanıt (eps=16, gamma=1.25): merkez çizgi Mach profili
  [1797.09, 1.00, 2532.22, 3974.83, 4902.28, 5611.62, 6198.85, 6707.32, 7160.22, 7571.47]
Doğru izentropik değer (brentq ile A/At=16, γ=1.25): M_exit = 3.797
Yani ~2000 kat hata. Ayrıca eps=60'ta duvar yarıçapı 138.2 mm çiziliyor ama y ekseni `np.linspace(-0.05, 0.05, 30)` ile ±50 mm'e sabit → lüle duvarı grafiğin dışında kalıyor.
Ek hata: subsonik dalda `mach = 0.5*area_ratio` hesaplanıyor ama `mach_numbers.append(...)` sadece else dalında var → dizi boyu tutmuyor.

**Önerilen çözüm:** Bu figürü ya kaldır ya da gerçek çözücüye bağla: hrma/analysis/nozzle_flow_1d.py (NozzleFlow1D) quasi-1D akışı zaten hesaplıyor ve hrma.engines.nozzle_design.sample_nozzle_inner_contour gerçek konturu veriyor. Newton yerine brentq/analitik ters çözüm kullan, gamma'yı motor sonucundan al, y eksenini gerçek yarıçapa ölçekle. NASA referans etiketi ancak gerçekten o metodoloji uygulanıyorsa kalsın.

### hrma/visualization/visualization.py:2336-2450 (create_wall_heat_flux_waterfall_plot); UI: static/js/panels/performance_panel.js EXTRA_FIGURES 'heat_flux'
*Kapsam: Analiz modülleri*

**Uydurma olan:** Cidar ısı akısı alanının TAMAMI uydurma: taban akı varsayılan 2e6 W/m² (Bartz'dan gelmiyor), eksenel değişim `1+2*exp(-((X-throat)/50)^2)` (50 mm keyfi), zamansal değişim `1-exp(-t/5)` (5 s keyfi), ve 5 MW/m²'yi aşan hücrelerin akısını 1.5 ile ÇARPAN "thermal runaway" kuralı (kendi kendini besleyen, fiziksel karşılığı olmayan bir işlem). "NASA SP-8124 Thermal Design Criteria" olarak etiketleniyor.

**Kullanıcı etkisi:** Kullanıcı "Wall Heat Flux Distribution: Thermal Runaway Analysis" başlıklı 3B yüzeyi görüyor, üstünde kırmızı "Thermal Runaway Risk" işaretleri var. Bunu kendi motorunun soğutma/ablatif kararı için kullanır. Oysa projede GERÇEK Bartz tabanlı HeatTransferAnalyzer var ve bu figür ondan hiç beslenmiyor.

**Kanıt:** Kod: `HEAT_FLUX = base_heat_flux * axial_factor * transient_factor`; `runaway_mask = HEAT_FLUX > 5e6; HEAT_FLUX[runaway_mask] *= 1.5`.
Çalıştırılan kanıt (varsayılan panel değerleriyle): heat flux MW/m² aralığı 2.00 - 13.47. 13.47 MW/m² değeri tamamen `2.0 * 3.0(axial peak) * 1.5(transient) * 1.5(runaway çarpanı)` çarpımından geliyor, hiçbir termal çözümden değil.
Projede gerçek kaynak: hrma/analysis/heat_transfer_analysis.py → gas_side_analysis.heat_flux (Bartz).

**Önerilen çözüm:** HeatTransferAnalyzer'ın Bartz akısını eksenel istasyonlara uygula; zaman boyutu isteniyorsa transient_ballistics'ten Pc(t) alıp q(t) ∝ Pc(t)^0.8 ile ölçekle. "Runaway" çarpanını kaldır (akı eşiği aşınca akı artmaz; malzeme sıcaklığı artar). Gerçek hesap yoksa figürü çizme.

### hrma/export/openrocket_integration.py:220-241 (_generate_thrust_curve fallback); tetikleyiciler: templates/solid.html:4066-4077 ve templates/liquid.html:4360-4370
*Kapsam: Analiz modülleri*

**Uydurma olan:** Bugün cad_visualization'da düzeltilen hatanın BİREBİR aynısı, bu sefer .eng dosyasında: gerçek eğri yoksa sabit itkiye %15 doğrusal düşüş + 0.1 s'lik uydurma yükselme rampası (×0.8) + 0.5 s'lik uydurma sönme (×0.3) ekleniyor ve "Realistic hybrid motor thrust curve" diye üretiliyor. Fonksiyon SADECE motor_data['transient'] anahtarına bakıyor; katı motorun GERÇEK `thrust_curve` (time/thrust/pressure dizileri) çıktısına hiç bakmıyor.

**Kullanıcı etkisi:** Katı ve sıvı sayfalarındaki "OpenRocket .eng" butonu, backend'e transient/thrust_curve İÇERMEYEN elle kurulmuş bir sözlük gönderiyor → fallback HER ZAMAN çalışıyor. Kullanıcı .eng dosyasını OpenRocket'e alıp uçuş simülasyonu yapıyor ve eğriyi kendi motorunun hesaplanmış itki eğrisi sanıyor. Katıda özellikle vahim: progresif/regresif grain (yıldız, BATES) gerçek eğrisi bu %15'lik düz düşüşten tamamen farklıdır ve zaten hesaplanmıştır. Sıvıda ayrıca UI mesajı ".eng file downloaded (constant thrust, X s burn)" diyor — dosyanın içi sabit DEĞİL, %15 düşen bir eğri; etiket dosyayla çelişiyor.

**Kanıt:** Kod: `regression_factor = 1.0 - 0.15 * (t / burn_time)`; `thrust = avg_thrust * (t/0.1) * 0.8`; `thrust = avg_thrust * (burn_time-t)/0.5 * 0.3`.
Çalıştırılan kanıt (2000 N, 10 s katı motor, solid.html'in gönderdiği alanlarla birebir):
  0.101 1997.0 / 0.202 1993.9 / ... / 9.495 1715.2 / 9.596 484.8 / ... / 10.000 0.0
solid.html:4066 gönderilen sözlük: motor_name,total_impulse,thrust,burn_time,isp,propellant_mass_total,throat_diameter,chamber_pressure — transient YOK, thrust_curve YOK.
Ayrıca hibritte de currentResults.motor.transient yalnızca kullanıcı Transient panelini ÇALIŞTIRIRSA doluyor (static/js/transient_panel.js:142); çalıştırmazsa .eng sessizce uydurma eğriyi alıyor ve kullanıcı hangisini aldığını bilmiyor.

**Önerilen çözüm:** 1) _generate_thrust_curve'e `thrust_curve` (time/thrust) kaynağını ekle — katı çözücü zaten üretiyor. 2) solid.html/liquid.html payload'larına gerçek eğriyi koy. 3) Gerçek eğri yoksa şablon eğri ÜRETME: ya sabit itki yaz ya da 400 dön; .eng başlığındaki yorum satırına hangi kaynağın kullanıldığını (`; thrust curve: transient solver` / `; constant-thrust assumption`) yaz ki dosya kendini beyan etsin.

### hrma/export/cad_visualization.py:1042-1069 (_estimate_component_mass) ve 1014-1040 (_generate_cad_performance_summary); UI: /api/export-cad → cad_exports.performance_summary, /api/generate-complete-package → analysis.weight_breakdown
*Kapsam: Analiz modülleri*

**Uydurma olan:** Kamara kütlesi SABİT 5 mm cidar kalınlığı ve sabit çelik yoğunluğuyla hesaplanıyor (`inner_r = outer_r - 0.005  # 5mm wall`), oysa aynı motor sonucunda yapısal analizin hesapladığı gerçek `structural_analysis.chamber_analysis.recommended_thickness` mevcut. Bu kütleden türetilen `total_dry_mass` ve `thrust_to_weight` de aynı ölçüde yanlış.

**Kullanıcı etkisi:** Kullanıcı CAD/paket çıktısında "chamber_mass", "total_dry_mass" ve "thrust_to_weight" değerlerini görüyor ve motorunun kuru kütlesini/itki-ağırlık oranını buradan alıyor. Değer motor büyüdükçe katlanarak sapıyor — roket kütle bütçesi ve T/W kararı doğrudan yanlış çıkar.

**Kanıt:** Kod: `inner_r = outer_r - 0.005  # 5mm wall`, `density = 7850`.
Çalıştırılan kanıt (aynı motor sonucundan gerçek kalınlıkla karşılaştırma):
  T=2000 N  : sabit 5 mm → 10.88 kg ; gerçek 10.95 mm → 22.41 kg  (2.1x)
  T=20000 N : sabit 5 mm → 92.62 kg ; gerçek 29.05 mm → 490.72 kg (5.3x)
  T=60000 N : sabit 5 mm → 267.01 kg; gerçek 48.16 mm → 2328.80 kg (8.7x)
T/W bu kütleden: 20 kN motor için ~21 raporlanıyor, gerçek kütleyle ~4.

**Önerilen çözüm:** _estimate_component_mass'i structural_analysis.chamber_analysis.recommended_thickness ve seçilen malzeme yoğunluğuyla besle (materials_db'de var). Yapısal analiz yoksa kütleyi hiç raporlama veya alanı açıkça 'NOT ANALYZED' yaz — CAD katmanı zaten wall_case'i doğru okuyor (satır 143-147), aynı değeri kütle hesabına da geçir.

### hrma/export/drawing_generator.py:88 (_injector_face_png) — hrma/visualization/visualization.py:2923 (create_showerhead_with_tooltips) ile çelişkili; ayrıca hrma/export/cad_visualization.py:167
*Kapsam: Analiz modülleri*

**Uydurma olan:** Aynı motor koşusunda enjektör için ÜÇ farklı ve birbirini tutmayan kaynak kullanıcıya sunuluyor: (a) ekrandaki enjektör grafiği injector_results'tan, (b) imalat çizimi PDF'i motor_results['injector_design']'tan, (c) CAD teknik çizim sözlüğü 16'ya kırpılmış bir sayıdan. Hiçbiri diğerinden haberdar değil, hiçbirinde "bu şu kaynaktan" etiketi yok.

**Kullanıcı etkisi:** Kullanıcı imalat için teknik çizim PDF'ini kullanıyor (sayfa 2: "INJECTOR FACE — N × Ø d mm"). Ekranda 50 delik × 0.94 mm görüp plakayı çizimden 5 delik × 2.26 mm olarak deldiriyor. 10 kat delik sayısı farkı = tamamen farklı ΔP, hız, atomizasyon ve yanma kararlılığı. Gerçek donanım üretilen bir hatadır.

**Kanıt:** Aynı motor (2000 N, O/F 6, Pc 20 bar, showerhead) tek koşuda:
  UI enjektör paneli (injector_results): n_holes=50, d=0.94 mm, v=25.6 m/s, ΔP=4.0 bar
  Teknik çizim PDF (motor_results['injector_design']): n=5, d=2.26 mm, v=70.2 m/s, ΔP=30.54 bar
Ayrıca cad_visualization.py:167 `injector_orifices = max(1, min(injector_orifices, 16))` kırpması yüzünden:
  T=20 kN: çözücü 41 orifis → CAD teknik çizim 16
  T=60 kN: çözücü 120 orifis → CAD teknik çizim 16
(16'ya kırpma yorumu 'boolean kararlılığı' diyor — mesh üretimi için makul olabilir ama kırpılmış sayı teknik çizim/spesifikasyon çıktısına da yazılıyor.)

**Önerilen çözüm:** Enjektör için TEK doğruluk kaynağı belirle (injector_results tercih edilmeli, kullanıcı ΔP/hız hedeflerini oradan giriyor) ve motor_results'a onu yaz; drawing_generator, cad_visualization ve visualization aynı sözlüğü okusun. Mesh kırpması gerekiyorsa yalnız MESH'te kırp; teknik çizim/spec çıktısına gerçek sayıyı yaz ve çizimde 'pattern shown schematically, N=41' notu ekle.

### hrma/data/database_integrations.py:303,308,197 + hrma/templates/advanced.html:2731-2745
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** /api/validate-fuel ucunun döndürdüğü mixture_properties tamamen uydurma formüllerden geliyor ama 'NASA CEA Database' etiketiyle sunuluyor: density = 900 + (C atom sayısı)*50, specific_heat = 1500 + MW*10, heat_of_formation = bileşiğin ΔHf'i değil, ATOMİK gaz-fazı oluşum entalpilerinin toplamı.

**Kullanıcı etkisi:** Hibrit sayfasında 'Custom / Mixture' yakıt tanımlayıp Validate'e basan kullanıcı yeşil kutuda şunu görüyor: 'Composition validated successfully with NASA CEA database — Calculated Properties: Heat of Formation: 4174.5 kJ/mol, Estimated Density: 1100 kg/m³, Specific Heat: 2041 J/kg·K'. Daha kötüsü advanced.html:2743 bu uydurma yoğunluğu doğrudan fuel_density form alanına YAZIYOR ve fuel_density /calculate'te GERÇEKTEN kullanılan bir çözücü girdisi (duyarlılık testinde 'KULLANILAN' listesinde). Yani uydurma bir formül motor sonucunu değiştiriyor.

**Kanıt:** database_integrations.py:301-310 →
  if 'C' in comp.get('elements', {}):
      comp_density = 900 + comp.get('elements', {}).get('C', 1) * 50
  else:
      comp_density = 800
  comp_cp = 1500 + comp['molecular_weight'] * 10
ve satır 197: 'source': 'NASA CEA Database'.
Canlı test: POST /api/validate-fuel {'composition':[{'formula':'C4H6','percentage':100}]} →
  {'mixture_properties': {'density': 1100.0, 'specific_heat': 2040.92, 'heat_of_formation': 4174.54, 'molecular_weight': 54.092}, 'source': 'NASA CEA Database'}
Gerçek: 1,3-bütadien ΔHf(g) = +110 kJ/mol; HTPB ≈ -50 kJ/mol mertebesi. 4174.54 fiziksel olarak imkânsız (4*716.68 + 6*217.97 = atomik ΔHf toplamı).
Ayrıca NasaCeaAPI.validate_fuel_composition hiçbir ağ çağrısı yapmıyor (inspect ile doğrulandı: kaynakta 'self.session' / 'requests' YOK) — 13 elemanlı yerel bir sözlük.

**Önerilen çözüm:** 1) 'source' alanını gerçeği söyleyecek şekilde değiştir: 'HRMA local elemental estimator (NOT NASA CEA)'. 2) density/specific_heat tahmin formüllerini ya kaldır ya da çıktıda 'ESTIMATE — not a measured/CEA value' etiketiyle döndür. 3) advanced.html:2743'teki otomatik fuel_density yazımını KALDIR (veya kullanıcıya onay sor); uydurma değer çözücü girdisine sızmamalı. 4) heat_of_formation'ı bileşik ΔHf'i olmadan hiç raporlama (None döndür).

### hrma/data/open_source_propellant_api.py:306,333,499,523 + hrma/templates/liquid.html:1889-1960
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** /api/get-propellant-properties ucu LOX/LH2 için CoolProp'u 298.15 K, 101325 Pa'da (oda koşulları) sorguluyor → kriyojenik SIVI yerine GAZ yoğunluğu dönüyor. CoolProp'un tanımadığı akışkanlarda (rp1, n2o4, htpb) ise tüm PropsSI çağrıları düşüyor, sabit varsayılanlar (800 / 1200) dönüyor ama 'source' hâlâ 'CoolProp' kalıyor (satır 333 etiket, hata try'ından ÖNCE atanıyor).

**Kullanıcı etkisi:** Sıvı motor sayfası açılışta ve her yakıt/oksitleyici değişiminde bu ucu çağırıyor ve sonucu YEŞİL 'Real-time Data' rozetiyle gösteriyor: LOX için 'Density: 1.3 kg/m³' (gerçek 1141), LH2 için '0.1 kg/m³' (gerçek 71), N2O4 için 1200 (gerçek 1443). Üstelik liquid.html:1912 ve :1950 bu değerleri fuel_density / oxidizer_density / fuel_viscosity / oxidizer_viscosity form alanlarına YAZIYOR — yani sayfadaki 1141 varsayılanı 1.3 ile eziliyor ve bu değer raporlara/export'lara giriyor.

**Kanıt:** open_source_propellant_api.py:306 →
  properties['density'] = CP.PropsSI('D', 'T', temperature, 'P', pressure, cp_name)   # T=298.15 K, P=101325 Pa sabit
satır 333 → properties['source'] = 'CoolProp'   (hemen ardından gelen critical_temperature erişimi KeyError atıyor, except yakalıyor ama etiket kalıyor)
Canlı test:
  oxidizer/lox : source='CoolProp' density=1.3087864284209203 visc=2.055e-05
  liquid_fuel/lh2: source='CoolProp' density=0.0823481221374309
  liquid_fuel/rp1: source='CoolProp' density=800   (stdout: "Error getting CoolProp properties for rp1: 'critical_temperature'")
  oxidizer/n2o4  : source='CoolProp' density=1200  (aynı hata)
liquid.html:1911-1914 →
  if (props.density && document.getElementById('fuel_density')) { document.getElementById('fuel_density').value = props.density; }
Aynı dosyada oxidizer_density için :1949-1951.

**Önerilen çözüm:** 1) Kriyojenikler için CoolProp'u doymuş sıvı noktasında sorgula (PropsSI('D','T',T_sat,'Q',0,fluid)) veya kaynağı yerel tabloya sabitle. 2) properties['source']='CoolProp' atamasını try bloğunun EN SONUNA, yalnız en az bir PropsSI başarılıysa çalışacak biçimde taşı; başarısızsa 'source' = 'HRMA default (CoolProp unavailable for this fluid)'. 3) get_propellant_for_ui'deki `.get('density', 800/1200)` gibi sessiz varsayılanları ayrı bir `assumed_defaults` listesine yaz ve UI'da 'estimated' etiketiyle göster. 4) liquid.html'deki otomatik form-alanı ezme davranışını kaldır ya da 'Real-time Data' rozetini kaynak gerçekten canlıysa göster.

### hrma/engines/solid_rocket_engine.py:845-898 (calculate_burn_area) + hrma/templates/solid.html:603-608 (grain_type seçenekleri) + hrma/app.py:1448 (/calculate_solid)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** calculate_burn_area yalnız 'bates', 'star', 'wagon_wheel' dallarını tanıyor; geri kalan HER grain tipi etiketsiz `else: # end_burner` dalına düşüyor. UI dropdown'ında 'Finocyl' ve 'Slotted' seçenekleri var; ikisi de bu sessiz fallback'e giriyor. Uç hiçbir doğrulama yapmıyor, hiçbir uyarı üretmiyor, sonuçta grain_design.grain_type hâlâ 'finocyl' yazıyor.

**Kullanıcı etkisi:** Kullanıcı Finocyl (roketçilikte çok yaygın bir grain) seçtiğinde APCP için Isp = 17.92 s, ortalama itki 614 N gibi fiziksel olarak saçma bir sonuç alıyor — ama sonuç 'error':None, 'warnings':None, 'design_warnings':[] ile TAMAMEN NORMAL bir hesap gibi dönüyor. Kullanıcı bu sayıyı kendi finocyl tasarımının performansı sanıyor. Aynı payload BATES ile 234.81 s veriyor.

**Kanıt:** solid_rocket_engine.py:894 →
  else:  # end_burner
      r_outer = self.D_chamber / 2
      return np.pi * r_outer**2
Canlı test (aynı payload, yalnız grain_type değişiyor):
  bates        Isp=234.81 tb=1.760 It=15223.2
  star         Isp=233.61 tb=1.750 It=13782.5
  end_burner   Isp=233.67 tb=26.930 It=16647.5
  finocyl      Isp=17.92  tb=1.890 It=1161.8   error=None warnings=None design_warnings=[]
  slotted      Isp=17.92  tb=1.890 It=1161.8   error=None warnings=None design_warnings=[]
  moon_burner / rod_and_tube / slotted_tube da aynı 17.92 s
Ayrıca fin_count / fin_width / fin_length alanları grain_type='finocyl' iken bile çıktıyı hiç değiştirmiyor (test: üçü de YUTULDU).

**Önerilen çözüm:** En azından /calculate_solid'de grain_type'ı desteklenen küme ({bates, star, wagon_wheel, end_burner}) ile doğrula ve desteklenmeyende 400 + açık hata döndür (/api/burn-rate/resolve'daki dürüst kalıp gibi). Kalıcı çözüm: finocyl/slotted için gerçek Huygens-ofset port poligonu ekle (star/wagon_wheel'de zaten var) ve fin_* alanlarını bağla. UI dropdown'ından desteklenmeyen seçenekleri kaldır ya da 'not implemented' olarak devre dışı bırak.


---

## Major

### hrma/engines/liquid_rocket_engine.py:2250-2278 (_calculate_efficiency_breakdown)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Kayıp dökümü tamamen sabit: divergence 2.5, boundary_layer 1.5, heat_transfer 1.0, combustion_incomplete 2.0, mixing 1.5, kinetic 0.5, nozzle_length 1.0 -> toplam 10.0 -> overall_efficiency = 90.0. Nozul tipi, genişleme oranı, enjektör tipi, oda basıncı, yakıt hiçbiri etkilemiyor. Ayrıca 'efficiency_improvements' metinleri ('+1.5% Isp', '+0.5% Isp per 10 bar') de sabit.

**Kullanıcı etkisi:** 'Efficiency' sekmesinde kullanıcı 'Performance Losses (Overall Efficiency: 90.0%)' başlıklı pasta grafiği görüyor (liquid.html:2713-2737) ve hangi kaybın baskın olduğuna göre tasarım değiştirmeye çalışıyor. Grafik her motor için birebir aynı — 15° konik ile Rao bell arasında, ε=8 ile ε=100 arasında hiç fark yok.

**Kanıt:** Kod: `losses = {'divergence_loss':2.5, 'boundary_layer_loss':1.5, 'heat_transfer_loss':1.0, 'combustion_incomplete':2.0, 'mixing_loss':1.5, 'kinetic_loss':0.5, 'nozzle_length_loss':1.0}; total_loss=sum(losses.values()); actual_efficiency = 100 - total_loss`
Sayısal kanıt:
  10 kN/100 bar -> loss_breakdown {boundary_layer:1.5, combustion_incomplete:2.0, divergence:2.5, heat_transfer:1.0, kinetic:0.5, mixing:1.5, nozzle_length:1.0}, overall_efficiency 90.0
  250 kN/200 bar -> AYNI sözlük, overall_efficiency 90.0

**Önerilen çözüm:** NozzleDesigner'da zaten var olan ayrık kayıp modelini (nozzle_design.py:317-410: divergence_efficiency, friction_efficiency, two_phase_efficiency, kinetic_efficiency) kullan — bunlar nozul tipi/kontur açısından gerçekten hesaplanıyor. Yanma tarafı için _analyze_combustion_chamber_detailed'ın hesapladığı mixing_efficiency/combustion_efficiency değerlerini bağla. Bağlanamayan kalemler ('heat_transfer_loss' gibi) 'assumed 1.0%' olarak açıkça etiketlensin.

### hrma/engines/liquid_rocket_engine.py:2277-2311 (_calculate_structural_loads)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Üç ayrı sorun: (a) safety_factor = 4.0 sabit, kullanıcının girdiği safety_factor okunmuyor; (b) 'material': 'Inconel 718' etiketi ile material_yield_strength = 250e6 Pa çelişiyor — 250 MPa yumuşak çeliğin akma değeri, Inconel 718'in akması ~1030-1100 MPa; (c) stress_margin tanım gereği DAİMA 0.0: duvar kalınlığı allowable_stress'ten çözülüp hoop stress aynı kalınlıktan geri hesaplandığı için hoop_stress ≡ allowable_stress.

**Kullanıcı etkisi:** Sonuç sayfasındaki 'Structural Analysis' kartında (liquid.html:3974-3987) kullanıcı 'Material: Inconel 718 / Allowable Stress: 62.5 MPa / Safety Factor: 4.00 / Wall Thickness: 7.79 mm' görüyor. Inconel 718 seçtiğini sanıp 250 MPa'lık bir malzemeye göre boyutlandırılmış duvar kalınlığını imalata veriyor — ya 4x fazla ağır ya da (malzeme gerçekten çelikse) etiket yanlış. Stres marjı her motorda %0.0 çıktığı için 'marj yok' sanıyor.

**Kanıt:** Kod:
  safety_factor = 4.0
  material_yield_strength = 250e6  # Pa
  allowable_stress = material_yield_strength / safety_factor
  chamber_wall_thickness = (P*d/2)/allowable_stress ; actual_hoop_stress = (P*d/2)/chamber_wall_thickness
  stress_margin = (allowable - actual)/allowable*100
  ... 'material': 'Inconel 718'
Sayısal kanıt (/calculate_liquid):
  10 kN/100 bar -> {allowable_stress: 62.5, hoop_stress: 62.5, safety_factor: 4.0, stress_margin: 0.0, material: 'Inconel 718', wall_thickness: 7.79}
  250 kN/200 bar -> {allowable_stress: 62.5, hoop_stress: 62.5, safety_factor: 4.0, stress_margin: 0.0, material: 'Inconel 718', wall_thickness: 55.11}
safety_factor girdisi 2.5->6.0 değiştirildiğinde çıktı hiç değişmiyor (bkz. bulgu #1 taraması).

**Önerilen çözüm:** Malzemeyi merkezi malzeme kütüphanesinden (hrma/data materials) çek: kullanıcının chamber_material seçimi + yield_strength girdisi ile tutarlı σ_y kullan. safety_factor kullanıcı girdisinden gelsin. Etiket ile kullanılan σ_y'nin aynı kaynaktan geldiğini test kilidiyle garanti et. stress_margin'i anlamlı hale getir (ör. seçilen standart et kalınlığına göre) veya tautolojik olduğu için kaldır.

### hrma/engines/liquid_rocket_engine.py:1363-1364 ve 1522
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Motor kuru kütlesi `engine_mass = max(F/1000, 50)` — 10 kN'a kadar her motor için tam 50 kg. Yakıt kütlesi `'propellant_mass_kg': self.mdot_total * 300` — kullanıcının hiç girmediği 300 saniyelik yanma süresi varsayımı, hiçbir yerde etiketlenmiyor. T/W oranı da bu uydurma 50 kg'dan türetiliyor.

**Kullanıcı etkisi:** 'Design Summary' kartında (liquid.html:4031-4032) ve PDF raporunda kullanıcı 'Engine Mass: 50.0 kg', 'Thrust / Weight: 20.4', 'Propellant Mass: 981.3 kg' görüyor. Araç kütle bütçesini ve tank boyutlandırmasını bu sayılara göre yapıyor. 981 kg yakıt sayısı tamamen 300 s varsayımından geliyor — kullanıcı 20 saniyelik bir test motoru tasarlıyor olabilir.

**Kanıt:** Kod:
  engine_mass = self.F / 1000  # kg
  engine_mass = max(engine_mass, 50)  # Minimum 50 kg
  thrust_to_weight = self.F / (engine_mass * self.g0)
  ... 'propellant_mass_kg': self.mdot_total * 300,  # 300s burn time
Sayısal kanıt (10 kN, Pc=100, MR=2.5): design_summary.masses = {engine_mass_kg: 50, propellant_mass_kg: 981.2567, thrust_to_weight: 20.394}. total_mass_flow = 3.27086 kg/s; 3.27086 * 300 = 981.2567 -> yakıt kütlesi birebir mdot*300. Ayrıca _detailed_component_sizing (satır 2365-2385) aynı motor için total_dry_mass ~123 kg hesaplıyor -> 50 kg ile çelişiyor.

**Önerilen çözüm:** Yanma süresini kullanıcı girdisi yap (liquid formunda zaten max_burn_duration alanı var, backende hiç gitmiyor) ve yakıt kütlesini ondan hesapla; girdi yoksa değeri 'assumed 300 s burn' etiketiyle göster. engine_mass için _detailed_component_sizing'in bileşen bazlı toplamını tek kaynak yap (iki farklı kuru kütle raporlanmasın); 50 kg tabanını kaldır.

### hrma/engines/liquid_rocket_engine.py:1683-1697 (_calculate_feed_system_pressure_drops)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Besleme hattı basınç düşümlerinin tamamı sabit: tank_outlet 0.1, main_valve 0.5, filters 0.3, feed_lines 1.2, injector 3.0, total 5.1 bar. Debi, hat çapı, akışkan yoğunluğu/viskozitesi, hat uzunluğu hiçbiri girmiyor. Ayrıca 'injector: 3.0 bar' aynı motorun kendi enjektör hesabıyla çelişiyor (impinging için ΔP = 0.22·Pc = 22 bar).

**Kullanıcı etkisi:** PDF/Excel raporunun 'Feed system' sayfasında (liquid.html:4454-4462) kullanıcı 'Tank outlet drop: 0.100 bar, Main valve drop: 0.500 bar, Filter drop: 0.300 bar, Feed line drop: 1.200 bar, Injector drop: 3.000 bar, Total oxidizer-side drop: 5.100 bar, Oxidizer pump discharge pressure: 105.10 bar' görüyor — 3 ondalık basamakla, hesaplanmış gibi. Pompa/tank basınç gereksinimini bu sayıya göre belirliyor; gerçek enjektör düşümü 22 bar olduğu için pompa basıncı ~19 bar eksik boyutlandırılıyor.

**Kanıt:** Kod: `pressure_drops = {'tank_outlet':0.1,'main_valve':0.5,'filters':0.3,'feed_lines':1.2,'injector':3.0,'total_ox':5.1,'total_fuel':5.1,'pump_discharge_pressure_ox': self.P_c+5.1, 'pump_discharge_pressure_fuel': self.P_c+5.1}`
Sayısal kanıt (/calculate_liquid, 10 kN / Pc=100): feed_system.pressure_drops = {feed_lines:1.2, filters:0.3, injector:3.0, main_valve:0.5, tank_outlet:0.1, total_fuel:5.1, total_ox:5.1, pump_discharge_pressure_ox:105.1}. Aynı yanıtta injector hesabı pressure_drop_factor=0.22 ile ΔP_ox = 22 bar veriyor (calculate_injector_design, satır 1002-1003) -> aynı enjektör için iki farklı ΔP raporlanıyor. 250 kN/200 bar koşusunda da kalemler bire bir aynı kalıyor.

**Önerilen çözüm:** Hat düşümlerini Darcy-Weisbach ile hesapla: _calculate_line_diameter (satır 1559) zaten hat çapını üretiyor; ṁ, ρ, μ, L ve fitting K katsayılarıyla gerçek ΔP çıkar. 'injector' kalemi doğrudan calculate_injector_design'ın ΔP'sinden alınsın (tek kaynak). Hesaplanamayan kalemler ('filters' gibi) 'assumed' etiketiyle ve 1 ondalıkla verilsin — 3 ondalık sahte kesinlik.

### hrma/engines/liquid_rocket_engine.py:1988-2065 (_analyze_detailed_feed_system)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Turbopompa performans eğrileri uydurma parabollerden üretiliyor: head_coeff = 1.2 - 0.8*(Q/Q0-1)^2, eta = 0.78*(1-2.5*(Q/Q0-1)^2), npsh_req = 15 + 25*(Q/Q0-0.8)^2 — pompa özgül hızı, çark geometrisi veya akışkan özellikleriyle ilgisi yok. Türbin kalemleri de sabit: inlet_temperature=1200 K, pressure_ratio=8.5, efficiency=85, rotational_speed=25000 rpm, blade_tip_speed=400 m/s. performance_margins (flow 10, pressure 15, power 20, npsh 50) tamamen sabit.

**Kullanıcı etkisi:** 'Feed System' sekmesinde 'Turbopump Performance Map' grafiği çiziliyor (liquid.html:2594-2624: head_curve ve efficiency_curve Plotly'ye veriliyor). Kullanıcı bu H-Q ve verim eğrisini kendi pompası için hesaplanmış sanıp çalışma noktası/NPSH marjı kararı veriyor. Türbin devri 25000 rpm ve uç hızı 400 m/s her motorda aynı — 10 kN da olsa 500 kN da olsa.

**Kanıt:** Kod: `head_coeff = 1.2 - 0.8*(flow_ratio-1)**2`, `eta = eta_peak*(1 - 2.5*(flow_ratio-1)**2)` (eta_peak=0.78 sabit), `npsh_req = 15 + 25*(flow_ratio-0.8)**2`, `turbine_inlet_temp = 1200`, `turbine_pressure_ratio = 8.5`, `'rotational_speed': 25000`, `'blade_tip_speed': 400`, `'efficiency': 85`.
Sayısal kanıt (/calculate_liquid):
  10 kN -> turbine = {blade_tip_speed:400, efficiency:85, inlet_temperature:1200, pressure_ratio:8.5, rotational_speed:25000, power_output:30313.8}
  500 kN/250 bar -> turbine = {blade_tip_speed:400, efficiency:85, inlet_temperature:1200, pressure_ratio:8.5, rotational_speed:25000, power_output:1515690.5}
  Yalnız power_output ölçekleniyor; devir, uç hızı, verim, giriş sıcaklığı, basınç oranı ve tüm performance_margins sabit.

**Önerilen çözüm:** Ya pompayı gerçek boyutlandır (özgül hız Ns'den verim ve devir; Euler head; NPSH_req = σ·H), ya da bu bloğu tamamen kaldır. Grafik kalırsa başlığı 'Representative centrifugal pump characteristic (not sized for this engine)' olarak etiketle. Sabit türbin kalemleri 'typical values' etiketiyle ayrı bir 'Assumptions' bölümüne taşınsın.

### hrma/engines/liquid_rocket_engine.py:1384
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** `vacuum_optimized_isp = actual_isp_vac * 1.05` — 'uzay optimize tasarım için ek %5' diye hiçbir fiziksel dayanağı olmayan sabit çarpan. Nozul yeniden boyutlandırılmıyor, genişleme oranı değişmiyor, sadece sayı %5 büyütülüyor. Aynı satırda `expansion_ratio_vacuum = min(300, eps*2.5)` de keyfi.

**Kullanıcı etkisi:** Sonuç kartında 'Space Optimized Isp' (liquid.html:2053) ve PDF raporunda 'Space-optimised Isp (s)' (satır 4419) olarak gösteriliyor, 2 ondalık hassasiyetle. Kullanıcı üst kademe motorunun vakum performansını bu sayıya göre hesaplıyor — %5 Isp, delta-V bütçesinde ciddi bir yalan.

**Kanıt:** Kod: `vacuum_optimized_isp = actual_isp_vac * 1.05  # Uzay optimize tasarım için ek %5` ve satır 1442 `'expansion_ratio_vacuum': min(300, nozzle_geom['expansion_ratio'] * 2.5)`. Bu iki değer birbirinden bağımsız üretiliyor: %5'lik Isp artışı, 2.5x genişleme oranından izentropik olarak türetilmiş DEĞİL. 10 kN RP-1/LOX koşusunda isp_vacuum=353.15 -> isp_vacuum_optimized=370.81, oysa gerçek vakum nozulu ε=2.5x ile çözülse farklı bir değer çıkardı.

**Önerilen çözüm:** 'Space optimized Isp'yi ya expansion_ratio_vacuum ile gerçekten yeniden hesapla (calculate_nozzle_geometry'yi P_a=0 ve yeni ε ile çağır, CF ve Isp'yi izentropik olarak çöz), ya da alanı tamamen kaldır. Ara çözüm olarak %5 çarpanı kalacaksa etiket 'Isp(vac) x 1.05 (rule-of-thumb, not a re-solved nozzle)' olsun.

### hrma/engines/solid_rocket_engine.py:2069-2077 (_calculate_safety_analysis)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Emniyet analizinde design_pressure_bar=100, burst_pressure_bar=150, relief_valve_setting_bar=85 sabit. Kasa çapı, oda basıncı, malzeme veya duvar kalınlığıyla hiç değişmiyor. Bu değerler, aynı sözlükte GERÇEKTEN hesaplanan pressure_safety_factor'ün yanında duruyor — kullanıcı hepsinin aynı hesaptan geldiğini varsayıyor.

**Kullanıcı etkisi:** Katı motor 'Safety Analysis' sekmesinde (solid.html:3446-3452) kullanıcı 'Maximum Operating Pressure: 40.0 bar / Design Pressure: 100 bar / Burst Pressure: 150 bar / Safety Factor: 7.5' görüyor. 200 bar oda basıncıyla çalışan bir motor tasarlasa bile hâlâ 'Burst Pressure 150 bar' yazıyor — yani patlama basıncı işletme basıncının ALTINDA gösteriliyor ve kullanıcı bunu fark etmiyor. Doğrudan can güvenliği kararı bu ekrandan veriliyor.

**Kanıt:** Kod: `'pressure_safety': {'max_operating_pressure_bar': max_pressure, 'design_pressure_bar': 100, 'safety_factor': pressure_safety_factor, 'burst_pressure_bar': 150, 'relief_valve_setting_bar': 85}`
Sayısal kanıt (SolidRocketEngine.calculate_performance):
  A) BATES, D=100mm, L=500mm, core=30mm, Pc=40 bar -> design_pressure_bar=100, burst_pressure_bar=150, relief=85
  B) BATES, D=200mm, L=900mm, core=60mm, Pc=90 bar -> design_pressure_bar=100, burst_pressure_bar=150, relief=85  (AYNI)
  Aynı koşularda gerçek çıktılar değişiyor: average_thrust 6819.9 -> 37434.2 N, propellant_mass 6.47 -> 46.57 kg.

**Önerilen çözüm:** design_pressure = MEOP x tasarım faktörü (P_c x 1.5 veya kullanıcının safety_factor girdisi), burst_pressure = σ_ult·t/r (aynı Barlow zinciri, _calculate_dry_mass ile aynı duvar kalınlığından), relief = design x 0.85 olarak hesapla. Sabit kalması gereken varsa (relief valf ayarı gibi) 'recommendation' olarak etiketlensin, 'bar' birimiyle hesaplanmış değer gibi sunulmasın.

### hrma/engines/solid_rocket_engine.py:1194-1203 (_calculate_thermal_analysis) ve 2241-2243 (_calculate_case_temperature)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** (a) thermal_efficiency_percent = 85.2 ve insulation_effectiveness = 94.8 sabit, thermal_protection_rating = 'Excellent' sabit. (b) Kasa sıcaklığı `return 298 + (self.T_c - 298) * 0.1` — 'Simplified heat transfer' yorumuyla uydurulmuş bir formül; yanma süresi, duvar kalınlığı, yalıtım kalınlığı, malzeme ısıl iletkenliği hiçbiri girmiyor. 2 saniyelik bir motorla 30 saniyelik bir motor aynı kasa sıcaklığını veriyor.

**Kullanıcı etkisi:** 'Thermal Analysis' sekmesinde (solid.html:3394 ve 3400-3402) kullanıcı 'Thermal Efficiency: 85.2% / Case Temperature: 630 K / Insulation Effectiveness: 94.8% / Thermal Protection Rating: Excellent' görüyor. 630 K (357°C) kasa sıcaklığına göre yalıtım kalınlığı ve kasa malzemesi seçiyor; bu sayı motorun yanma süresinden tamamen bağımsız üretiliyor.

**Kanıt:** Kod: `'thermal_efficiency_percent': 85.2`, `'insulation_effectiveness': 94.8`, `'thermal_protection_rating': 'Excellent'`; ve `def _calculate_case_temperature(self): return 298 + (self.T_c - 298) * 0.1  # Simplified heat transfer`
Sayısal kanıt: A (D=100/L=500/core=30/Pc=40) ve B (D=200/L=900/core=60/Pc=90) koşularında:
  thermal_efficiency_percent: 85.2 / 85.2
  insulation_effectiveness: 94.8 / 94.8
  case_temperature_k: 629.68 / 629.68  (APCP T_c=3614.8 -> 298 + 3316.8*0.1 = 629.68; geometri ve basınçtan tamamen bağımsız)
Not: aynı modülde convective_heat_flux GERÇEK Bartz ile hesaplanıyor (_calculate_heat_flux, satır 2201) — yani doğru altyapı zaten var, kasa sıcaklığı ona bağlanmamış.

**Önerilen çözüm:** Kasa sıcaklığını mevcut Bartz akısı + yalıtım/kasa kalınlığı + yanma süresiyle geçici (lumped-capacitance veya 1B iletim) çöz: T_case(t_b) = f(q, t_wall, k, rho, cp, t_b). thermal_efficiency ve insulation_effectiveness ya gerçek ısı bilançosundan türetilsin ya da kaldırılsın; 'Excellent' gibi niteleyiciler hesaplanan sayıya bağlansın.

### hrma/engines/solid_rocket_engine.py:1116-1121 (_calculate_detailed_analysis)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** theoretical_vs_actual_isp altındaki kayıp kalemleri sabit: combustion_losses=3.2, nozzle_losses=2.1, two_phase_losses=1.8 (yüzde). Aynı sözlükte teorik Isp ve c* verimi GERÇEKTEN hesaplanıyor — kayıplar onların yanında hesaplanmış gibi duruyor. Ayrıca web_thickness_utilization=98.5 sabit.

**Kullanıcı etkisi:** 'Performance Analysis' sekmesinde (solid.html:3345-3346) kullanıcı 'Combustion Losses: 3.2% / Nozzle Losses: 2.1%' görüyor. Metalize APCP (iki-fazlı kayıp yüksek) ile şeker yakıtı (iki-faz farklı) arasında hiç fark yok; 15° konik ile daha uzun nozul arasında da yok. Kullanıcı bu kayıp dağılımına bakarak nozul mu yanma mı iyileştireceğine karar veriyor.

**Kanıt:** Kod: `'theoretical_vs_actual_isp': {'theoretical_isp': self._calculate_theoretical_isp(avg_pressure), 'combustion_losses': 3.2, 'nozzle_losses': 2.1, 'two_phase_losses': 1.8}` ve `'web_thickness_utilization': 98.5`
Sayısal kanıt: A ve B koşularında combustion_losses 3.2/3.2, nozzle_losses 2.1/2.1, two_phase_losses 1.8/1.8, web_thickness_utilization 98.5/98.5 (dört büyüklük de değişmiyor, oysa aynı sözlükteki c_star_efficiency_percent ve theoretical_isp değişiyor).

**Önerilen çözüm:** nozzle_losses'ı self.nozzle_efficiency'den (1-η)·100 olarak türet — bu değer zaten yakıt tablosundan geliyor ve kullanıcı override edebiliyor. combustion_losses'ı hesaplanan c_star_efficiency'den türet (100 - η_c*). two_phase_losses'ı yakıtın partikül kütle kesrinden hesapla (nozzle_design.two_phase_loss_coeff modeli hazır). web_thickness_utilization'ı gerçek web tüketiminden (D_port_final vs max_web) hesapla.

### hrma/engines/solid_rocket_engine.py:2195-2199 (_calculate_grain_stress)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Grain gerilmesi = 2.5 MPa sabit termal gerilme + Pc·0.1 'Simplified pressure-induced stress'. Yakıtın elastik modülü, Poisson oranı, termal genleşme katsayısı, grain geometrisi (web/çap oranı), soğuma ΔT'si hiçbiri girmiyor. Bu değerden türetilen structural_efficiency ve crack_propagation_risk da aynı şekilde uydurma.

**Kullanıcı etkisi:** 'Structural Analysis' sekmesinde (solid.html:3372-3375) kullanıcı 'Maksimum Grain Stress: 6.5 MPa / Structural Efficiency: 95.0% / Crack Propagation Risk: Medium / Thermal Expansion Compatibility: Good' görüyor. Grain çatlama riski hakkında karar veriyor — oysa sayı yalnızca oda basıncının onda birine 2.5 eklenmiş hali. Yıldız (star) grain'in keskin köşe gerilme yığılması gibi gerçek çatlama mekanizması hiç modellenmiyor.

**Kanıt:** Kod:
  thermal_stress = 2.5  # MPa, typical thermal expansion stress
  pressure_stress = self.P_c * 0.1  # Simplified pressure-induced stress
  return thermal_stress + pressure_stress
Sayısal kanıt: A (Pc=40) -> max_grain_stress_mpa = 6.5 = 2.5 + 40*0.1 ; B (Pc=90) -> 11.5 = 2.5 + 90*0.1. Grain tipi bates->star, çap 100->200 mm, core 30->60 mm değiştirildiğinde değer yalnız Pc üzerinden değişiyor — geometriyle hiç ilgilenmiyor.
Ayrıca satır 2022 `_calculate_grain_hoop_stress` diye ikinci bir grain gerilme fonksiyonu daha var (ölü/çelişkili ikinci kaynak).

**Önerilen çözüm:** Ya gerçek modeli kur (kalın cidarlı silindir iç basınç çözümü + serbest büzülme termal gerilmesi: σ_th = E·α·ΔT/(1-ν), E/α/ν yakıt tablosundan), ya da bu üç satırı sonuçtan kaldır. Kalacaksa 'order-of-magnitude estimate' etiketiyle ve tek ondalıksız gösterilsin; crack_propagation_risk gibi kategorik yargılar uydurma sayıdan türetilmesin.

### hrma/engines/solid_rocket_engine.py:141-175 (_apply_overrides)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Katı motor formunun 'Efficiency Factors' ve 'Mass & structural' grupları backende ulaşıyor ama _apply_overrides bunları hiç okumuyor: combustion_efficiency, cf_efficiency, overall_efficiency, discharge_coeff, kinetic_efficiency, divergence_loss, two_phase_loss, erosion_factor, yield_strength, safety_factor, case_thickness, liner_thickness, liner_density, chamber_volume, convergent_angle, divergent_angle, atm_pressure, test_altitude, ambient_temp. (throat/exit/expansion'ın bilinçli bağlanmadığı docstring'de yazıyor, ama verim faktörleri için böyle bir gerekçe bile yok.)

**Kullanıcı etkisi:** Kullanıcı solid.html'de 'Combustion Efficiency = 0.95', 'CF Efficiency = 0.98', 'Kinetic Efficiency = 0.97', 'Two-Phase Loss = 0.98', 'Yield Strength = 250 MPa', 'Safety Factor = 2.5' alanlarını doldurup hesaplatıyor. Hiçbiri Isp'yi, itkiyi veya duvar kalınlığını değiştirmiyor. Üstelik sonuç sayfası 'Combustion Losses %3.2' ve 'Safety Factor' gösteriyor — kullanıcı kendi girdiği verimlerin uygulandığını sanıyor.

**Kanıt:** _apply_overrides yalnız şu anahtarları okuyor: density, char_velocity, gamma, flame_temp, nozzle_efficiency, erosive_k, temp_coeff, initial_temp (+ ayrıca grain_count, case_material başka yerde).
Sayısal kanıt (SolidRocketEngine(overrides={k:v}) ile average_thrust/Isp/total_impulse/throat_d/exit_d/eps/propellant_mass/isp_vac/safety_factor/wall_thickness imzası):
  combustion_efficiency 0.80 -> ETKİSİZ ; cf_efficiency 0.85 -> ETKİSİZ ; overall_efficiency 0.80 -> ETKİSİZ
  discharge_coeff 0.85 -> ETKİSİZ ; kinetic_efficiency 0.90 -> ETKİSİZ ; divergence_loss 0.05 -> ETKİSİZ
  two_phase_loss 0.90 -> ETKİSİZ ; erosion_factor 0.01 -> ETKİSİZ ; yield_strength 900 -> ETKİSİZ
  safety_factor 1.5 -> ETKİSİZ ; case_thickness 20 -> ETKİSİZ ; liner_thickness 6 -> ETKİSİZ
  liner_density 1800 -> ETKİSİZ ; chamber_volume 12 -> ETKİSİZ ; convergent_angle 20 -> ETKİSİZ ; divergent_angle 25 -> ETKİSİZ
Karşılaştırma — çalışanlar: nozzle_efficiency 0.85 -> ETKİLİ (F, Isp, It, Isp_vac) ; density 1600 -> ETKİLİ ; char_velocity 1400 -> ETKİLİ ; gamma 1.15 -> ETKİLİ ; initial_temp 250 -> ETKİLİ ; grain_count 3 -> ETKİLİ

**Önerilen çözüm:** Fiziksel karşılığı olanları _apply_overrides'a bağla: combustion_efficiency -> c* çarpanı (η_c*), cf_efficiency/kinetic_efficiency/divergence_loss/two_phase_loss -> _thrust_coefficient içindeki toplam nozul verimine, erosion_factor -> erosive_burning_coeff, yield_strength+safety_factor+case_material -> _calculate_structural_analysis/_calculate_dry_mass/_calculate_safety_analysis'teki sabit 250e6/3.0 yerine, atm_pressure/test_altitude -> SEA_LEVEL_PRESSURE_BAR yerine. Bağlanamayacaklar formdan kaldırılsın veya 'display only' etiketi alsın.

### hrma/engines/hybrid_rocket_engine.py:1100-1161 (motor içi injector_design) ile hrma/app.py:317-330 (utils.InjectorDesign) arasında
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Aynı hibrit motor için AYNI istekte iki tamamen farklı enjektör tasarımı üretilip ikisi de kullanıcıya gösteriliyor. Motor içi yol (engines/injector_design.py, Dyer NHNE) N2O için ΔP'yi doyma basıncından türetiyor; ayrı InjectorDesign nesnesi (utils/injector_design.py) ise ΔP = %20·Pc kullanıyor ve kullanıcının `pressure_drop` override'ını yalnız O uyguluyor. Sonuçlar 13 kat farklı delik sayısı veriyor.

**Kullanıcı etkisi:** Kullanıcı 'Design Report' bölümünde 'Number of Holes: 41 / Hole Diameter: 0.73 mm / Pressure Drop: 4.00 bar' (app.js:784-786) görüyor; aynı motorun Excel çıktısındaki 'Injector' sayfasında (advanced.html:4390-4396) ise 'number of orifices: 3 / orifice diameter mm: 2.0659 / injection pressure drop bar: 30.3733' yazıyor. Hangisine göre delik açacağını bilmiyor. Dahası kullanıcı ΔP override'ı girdiğinde yalnız birinci sayı değişiyor.

**Kanıt:** Sayısal kanıt (/calculate, hibrit: F=1000 N, t_b=10 s, O/F=6, Pc=20 bar, N2O/HTPB, showerhead, oxidizer_temp=293 K, tank_pressure=50 bar):
  motor['injector_design'] = {n_orifices: 3, orifice_d_mm: 2.0659, delta_p_bar: 30.3733, velocity: 70.03 m/s, cd: 0.78, total_area_mm2: 10.056}
  injector (utils)          = {n_holes: 41, hole_diameter: 0.7341 mm, pressure_drop_bar: 4.0, exit_velocity: 25.61 m/s, cd: 0.70, injection_area: 17.351 mm2}
  -> delik sayısı 13.7x, ΔP 7.6x, enjeksiyon hızı 2.7x farklı.
Override testi: istek gövdesine pressure_drop=12.0 eklendiğinde
  utils injector dP = 12.0 (source='user override')
  motor injector_design dP = 30.3733 (DEĞİŞMEDİ)
Sebep: hybrid_rocket_engine.py:736 `delta_P = 0.2 * self.P_c` sabit ve motor kullanıcı ΔP'sini hiç almıyor; ayrıca N2O dalında engines/injector_design.py:_solve_circuit p1 = p_sat(T) alıp dp_ratio_ox'u yok sayıyor.

**Önerilen çözüm:** Tek enjektör kaynağı bırak: engines/injector_design.py (NHNE + Cd tablosu + delik planı) tek doğruluk kaynağı olsun; app.py'deki ayrı InjectorDesign çağrısı ya kaldırılsın ya da yalnızca çizim/şema için kullanılıp sayı yayımlamasın. HybridRocketEngine'e `injector_delta_p` / `feed_pressure` parametresi ekle ve kullanıcı ΔP'si motorun içindeki tasarıma da geçsin. Ekranda ve Excel'de aynı sözlük okunsun.

### hrma/engines/hybrid_rocket_engine.py:274 ve 954
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Raporlanan 'chamber_volume' = L*·A_t, yani kullanıcının girdiği L*'ın boğaz alanıyla çarpımı — motorun fiilen tasarlanan oda hacmi DEĞİL. Motor kendi gerçek hacmini `V_c_actual` olarak ayrıca hesaplıyor (satır 321-322) ama kullanıcıya `chamber_volume` gösteriliyor. Aradaki fark 3-4 kat.

**Kullanıcı etkisi:** Design Report'un 'Motor Geometry' tablosunda (app.js:759-762) kullanıcı üst üste şunu görüyor: 'Chamber Diameter: 80.5 mm / Chamber Length: 629.0 mm / Chamber Volume: 365.8 cm³'. Bu üç sayı birbiriyle geometrik olarak tutarsız — 80.5 mm çap x 629 mm boy silindir 3203 cm³ eder, gerçek serbest hacim (port + ön/art yanma odası) 1242.7 cm³'tür. Kullanıcı oda hacmine göre yalıtım/dolgu ve L* değerlendirmesi yapıyor. Ayrıca L* 0.3'ten 2.0'a çıkarıldığında chamber_volume 110->732 cm³ artıyor ama motorun boyu, art-yanma odası ve gerçekleşen L* hiç değişmiyor — kullanıcı L*'ın geometriyi büyüttüğünü sanıyor.

**Kanıt:** Kod: satır 274 `self.V_c = self.L_star * self.At` ; satır 321-323 `V_chamber_actual = V_port_avg + (L_pre + L_post)*A_ch ; self.V_c_actual = V_chamber_actual` ; satır 954 `'chamber_volume': self.V_c` (gerçeği ayrıca `'chamber_volume_actual'` ile veriyor, UI onu okumuyor).
Sayısal kanıt (F=1000 N, t_b=10 s, O/F=6, Pc=20 bar, N2O/HTPB, konik):
  L*=0.3 -> L_chamber=629.04 mm, L_post=24.16 mm, L*_ach=3.397, chamber_volume=109.7 cm³, chamber_volume_actual=1242.7 cm³
  L*=0.5 -> L_chamber=629.04, L_post=24.16, L*_ach=3.397, chamber_volume=182.9,  actual=1242.7
  L*=1.0 -> L_chamber=629.04, L_post=24.16, L*_ach=3.397, chamber_volume=365.8,  actual=1242.7
  L*=2.0 -> L_chamber=629.04, L_post=24.16, L*_ach=3.397, chamber_volume=731.6,  actual=1242.7
  L*=20  -> L_chamber=846.45, L_post=241.56, L*_ach=6.424, chamber_volume=7316.1, actual=2349.8
Geometrik kontrol: D_ch=80.52 mm, L=629.0 mm -> π/4·D²·L = 3203.2 cm³. Raporlanan 365.8 cm³ ne silindir zarfı ne de gerçek serbest hacim.

**Önerilen çözüm:** Rapordaki 'Chamber Volume' alanını `chamber_volume_actual`'a bağla (app.js:762 ve 2214). İstenen L*·A_t değeri gösterilecekse ayrı bir satırda 'Requested L* volume' etiketiyle verilsin. L* notu (l_star_note) zaten doğru ve gösteriliyor — bu iyi; eksik olan hacim satırının hangi hacmi gösterdiği.

### hrma/export/cad_visualization.py:675-676, 785, 793 (_add_cross_section_view); ayrıca 1464 (_create_nozzle_mesh, sıvı detaylı CAD)
*Kapsam: Analiz modülleri*

**Uydurma olan:** CAD panelindeki "Cross-Section View" alt grafiğinde konverjan/diverjan açıları `motor_data.get('convergent_angle', 15.0)` / `('divergent_angle', 12.0)` ile okunuyor; bu anahtarlar motor sonucunda HİÇ YOK (gerçek değerler `nozzle_angles` ve `nozzle_contour.divergent` altında). Sonuç: her motor için 15° / 12° çiziliyor ve lejantta "Conv. 15.0°" / "Div. 12.0°" olarak ETİKETLENİYOR. Boğaz konumu da bu uydurma açıdan türetildiği için çizilen geometri gerçek konturdan farklı.

**Kullanıcı etkisi:** Kullanıcı 3D CAD panelinde motorunun kesitini görüyor, lejantta açıları okuyor ve bunları imalat/kontrol değeri sanıyor. Bell lüle seçse bile diverjan düz koni 12° olarak çiziliyor.

**Kanıt:** Gerçek koşu (bell lüle, 2000 N):
  çözücü: nozzle_angles = {'convergent_half_angle_deg': 45.0, 'divergent_half_angle_deg': 11.0, 'nozzle_type': 'bell'}, nozzle_contour.divergent = {'throat_angle': 30.0, 'exit_angle': 8.0, 'type': 'bell'}
  CAD figür trace adları: [..., 'Throat', 'Conv. 15.0°', 'Div. 12.0°', ...]
  CAD technical_drawings.nozzle: {'convergence_angle': 15, 'divergence_angle': 12}
`'convergent_angle' in motor_results` → False, `'divergent_angle' in motor_results` → False (doğrulandı).

**Önerilen çözüm:** Açıları `nozzle_angles`/`nozzle_contour.divergent`'ten oku; daha iyisi bu alt grafiği de sample_nozzle_inner_contour ile çiz (visualization.create_improved_motor_cross_section zaten öyle yapıyor — iki kesit arasındaki çelişki de böylece kapanır). Anahtar yoksa açı etiketini hiç yazma.

### hrma/export/cad_visualization.py:903-941 (_generate_technical_drawings)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Teknik çizim sözlüğündeki imalat spesifikasyonları sabit: kamara `wall_thickness: 5.0` mm, enjektör `plate_thickness: 30` mm, malzemeler ('Steel 304', 'Graphite', 'Stainless Steel 316') ve toleranslar/yüzey pürüzlülükleri motor sonucundan bağımsız. Kullanıcının malzeme seçimi ve yapısal analizin hesapladığı kalınlık yok sayılıyor.

**Kullanıcı etkisi:** /api/export-cad ve /api/generate-complete-package çıktısında 'technical_drawings' başlığıyla iniyor; kullanıcı bunu imalat spesifikasyonu sanır. 5 mm cidar, yapısal analizin güvenli dediği kalınlığın yarısından az — basınç kabı emniyet marjını doğrudan ilgilendirir.

**Kanıt:** Kod: `'wall_thickness': 5.0,  # mm`, `'plate_thickness': 30,`, `'material': 'Steel 304'`.
Çalıştırılan kanıt (aynı motor): CAD teknik çizim wall_thickness = 5.0 mm; structural_analysis.chamber_analysis.recommended_thickness = 10.94 mm (2.2x eksik). 20 kN motorda gerçek 29.05 mm.

**Önerilen çözüm:** wall_thickness'i structural_analysis'ten, malzemeleri kullanıcının seçtiği materials_db kaydından al. Veri yoksa alanı 'see structural analysis' / 'NOT SPECIFIED' yaz — sabit sayı yazma.

### hrma/visualization/visualization.py:2995 (create_showerhead_with_tooltips)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Her deliğin hover metnindeki "Mass flow: X g/s" değeri `injector_data.get('mdot_ox', 1.0) / n_holes * 1000` ile hesaplanıyor; ancak InjectorDesign.calculate() çıktısında `mdot_ox` anahtarı YOK → payda hep 1.0 kg/s. Yani delik başına debi her zaman 1000/n_holes g/s.

**Kullanıcı etkisi:** Kullanıcı enjektör plakası grafiğinde bir deliğin üstüne gelip "Mass flow: 13.70 g/s" okuyor ve bunu kendi oksitleyici debisinden hesaplanmış sanıyor. Delik başına debi, delik çapı/hız doğrulaması için doğrudan kullanılan bir büyüklük.

**Kanıt:** Çalıştırılan kanıt (aynı fonksiyon, gerçek InjectorDesign çıktısıyla):
  mdot_ox=0.5 kg/s, n=20 → hover 50.00 g/s | gerçek 25.0 g/s
  mdot_ox=1.2 kg/s, n=20 → hover 50.00 g/s | gerçek 60.0 g/s
  mdot_ox=5.0 kg/s, n=73 → hover 13.70 g/s | gerçek 68.49 g/s  (5x hata)
`'mdot_ox' in injector_results` → False (doğrulandı).

**Önerilen çözüm:** Debiyi çağrı yerinden geçir (app.py:408'de motor_results['mdot_ox'] elde) veya injector_results'a mdot_ox alanını ekle. Anahtar yoksa hover satırını hiç yazma.

### hrma/visualization/visualization.py:3308-3311, 3428-3455 (create_swirl_injector)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Swirl enjektör yüz görünüşündeki mühendislik ölçü çağrıları tamamen sabit: `outer_diameter` anahtarı çözücü çıktısında YOK → D_outer = 50.0 mm; oda çapı 0.6×R_out; çıkış orifisi 0.35×R_ch. Sonuçta her tasarımda aynı üç ölçü yazılıyor: D_outer 50.0 mm, D_chamber 30.0 mm, d_exit 10.5 mm. Çift oklu ölçü çizgileriyle, teknik resim konvansiyonunda sunuluyor.

**Kullanıcı etkisi:** Kullanıcı swirl enjektör görselinde ölçülendirilmiş bir teknik resim görüyor. Sadece teğetsel yuva boyutları (slot_width/slot_height) gerçek çözücüden geliyor; enjektörün akışı belirleyen ÇIKIŞ ORİFİSİ çapı ve gövde çapı uydurma ve her motorda aynı. Bu ölçülerle parça imal edilirse hesaplanan akış elde edilmez.

**Kanıt:** Çalıştırılan kanıt (aynı fonksiyon, gerçek swirl çözücü çıktısıyla):
  mdot_ox=0.5 → d_exit = 10.5 mm, D_outer = 50.0 mm, D_chamber = 30.0 mm
  mdot_ox=3.0 → d_exit = 10.5 mm, D_outer = 50.0 mm, D_chamber = 30.0 mm  (6x debi, ölçü aynı)
`'outer_diameter' in injector_results` → False (doğrulandı; swirl dalı bu alanı hiç üretmiyor).

**Önerilen çözüm:** Çıkış orifisi çapını gerçek akış alanından türet (injection_area / discharge_coefficient ilişkisi swirl dalında zaten var) veya bu üç ölçü çağrısını kaldırıp yerine 'schematic — not to scale' notu koy. Sabit değeri ölçü oku ile göstermek teknik resim iddiasıdır.

### hrma/visualization/advanced_results.py:129, 133-138 (create_cea_style_results)
*Kapsam: Analiz modülleri*

**Uydurma olan:** "PERFORMANCE PARAMETERS" tablosunun Vacuum sütunu: itki ve Cf düz bir ×1.15 çarpanıyla üretiliyor (`motor_results['thrust'] * 1.15`, `motor_results['cf'] * 1.15`). Aynı tablodaki Isp ise GERÇEK `vacuum_isp` değerini kullanıyor. İki değer birbiriyle çelişiyor. Ayrıca satır 30 `Oxidizer: N2O` sabit yazıyor ve `fuel_type` anahtarı motor sonucunda olmadığı için yakıt hep 'HTPB' görünüyor.

**Kullanıcı etkisi:** "THEORETICAL ROCKET PERFORMANCE" başlıklı, NASA CEA çıktısı biçiminde bir rapor. Kullanıcı LOX/parafin seçmiş olsa bile rapor N2O/HTPB yazıyor; vakum itkisi ve Cf, kendi genişleme oranından hesaplanmış sanılıyor ama sabit çarpan. (Not: bu metin şu an /calculate yanıtında `cea_results` anahtarıyla dönüyor fakat hiçbir şablon/JS render etmiyor — kullanıcı arayüzde göremiyor. Yine de API tüketicisi ve ileride bağlanacak panel için yanıltıcı.)

**Kanıt:** Çalıştırılan kanıt (LOX + parafin seçilmiş motor):
  '  Fuel Type: HTPB'      ← kullanıcı parafin seçti ('fuel_type' in motor_results → False)
  '  Oxidizer: N2O'        ← kullanıcı LOX seçti (kod sabiti)
  'Specific Impulse   227.1   255.2  s'   → gerçek oran 255.2/227.1 = 1.124
  'Thrust             2000    2300   N'   → 2000×1.15 (tutarlı olsaydı 2248 N)
  'Cf                 1.4056  1.6165 -'   → 1.4056×1.15 (tutarlı olsaydı 1.580)
Aynı tabloda iki farklı vakum/deniz-seviyesi oranı (1.124 ve 1.15) kullanılıyor.

**Önerilen çözüm:** F_vac = F_sl + Pa·Ae (veya F_sl × Isp_vac/Isp_sl), Cf_vac = Cf_sl × aynı oran. Yakıt/oksitleyici adlarını motor sonucuna yaz (engine.calculate() çıktısına fuel_type/oxidizer_type ekle) ve raporda oradan oku. Sabit 'N2O' satırını kaldır.

### hrma/export/pdf_generator.py:280, 284 (_create_executive_summary)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Güvenlik bölümü, `analysis_results['safety']` hiç yoksa bile basılıyor: `safety.get('overall_rating', 0)` → 0.0 ve eşik karşılaştırması 0 > 7 yanlış olduğu için başlık "REVIEW REQUIRED" oluyor. app.py:4160'daki `_build_pdf_analysis_sections` 'safety' anahtarına dokunmuyor, hibrit/katı/sıvı UI'ları da göndermiyor.

**Kullanıcı etkisi:** Kullanıcı teknik rapor PDF'ini indiriyor ve Executive Summary'de "Safety Assessment: REVIEW REQUIRED / Overall Safety Rating: 0.0/10" okuyor. Hiçbir güvenlik analizi çalıştırılmadığı halde yazılım motorunu 10 üzerinden 0 puanla değerlendirmiş gibi görünüyor — hem uydurma hem de raporu paylaşılabilir bir belge olarak değersizleştiriyor.

**Kanıt:** Üretilen gerçek PDF metninden (pypdf ile çıkarıldı, hibrit motor sonucu + boş safety):
  'Safety Assessment: REVIEW REQUIRED'
  'Overall Safety Rating: 0.0/10'
  'Critical Issues: 0'
Kod: `safety_status = "ACCEPTABLE" if safety.get('overall_rating', 0) > 7 else "REVIEW REQUIRED"`.

**Önerilen çözüm:** `if not safety: return story` — güvenlik bloğunu hiç basma; veya "Safety analysis not run" yaz. Rapor katmanının geri kalanında zaten uygulanan 'N/A yaz, uydurma' ilkesi burada da geçerli olmalı.

### hrma/export/pdf_generator.py:305-309 (_create_motor_configuration)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Uydurma değil ama aynı sınıftan bir sahte-sayı: hibrit yolunda motor_data ölçüleri METRE cinsindendir; PDF bunları `f"{...:.2f} mm"` ile mm etiketiyle basıyor. Sonuç fiziksel olarak imkânsız ölçüler.

**Kullanıcı etkisi:** Teknik rapor PDF'inde "Chamber Diameter 0.10 mm", "Chamber Length 0.88 mm", "Throat Diameter 0.03 mm" yazıyor. Kullanıcı raporu paylaşırsa veya ölçüleri buradan alırsa 1000 kat hatalı. Katı sayfası mm gönderdiği için orada doğru — yani aynı rapor motor tipine göre farklı birim yorumluyor, hangisinin doğru olduğu belgede yazmıyor.

**Kanıt:** Üretilen gerçek PDF metninden (hibrit motor, chamber_diameter = 0.10496 m):
  'Chamber Diameter  0.10 mm'
  'Chamber Length    0.88 mm'
  'Throat Diameter   0.03 mm'
  'Exit Diameter     0.06 mm'
Ayrıca 'Motor Type N/A' ve 'Propellant Type N/A' — hibrit sonucunda motor_type/propellant_type anahtarları yok, bu yüzden hibrite özgü satırlar (O/F, oksitleyici, yakıt) hiç basılmıyor.

**Önerilen çözüm:** Tek birim sözleşmesi belirle (metre) ve PDF'te ×1000 yaparak mm bas; ya da motor_geometry.py'deki dönüştürücüleri kullanarak tüm rotaları aynı şekle getir. motor_type'ı da doldur ki hibrit satırları basılsın.

### hrma/visualization/visualization.py:2528-2560 (_add_injector_cross_section, pintle dalı)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Ana motor kesitindeki pintle geometrisi, gerçek enjektör hesabından değil kamara yarıçapının sabit oranlarından türetiliyor: `d_p = inj.get('pintle_diameter_mm', 0.22*2*rc)` ve `gap = inj.get('annulus_gap_mm', max(0.5, 0.06*r_p))`. Bu anahtarlar hibrit motor sonucunun injector_design sözlüğünde YOK. Buna rağmen hover'da "D_pintle: X mm" ve "Gap: Y mm" olarak sayı veriliyor, ayrıca "Skip distance ~ Z mm" tamamen uydurma (pintle çapına eşitleniyor).

**Kullanıcı etkisi:** Kesit üstünde gezinen kullanıcı pintle çapını ve anülüs boşluğunu okuyor. Anülüs boşluğu enjeksiyon hızını doğrudan belirleyen büyüklük; enjektör panelinde gördüğü değerle kesitte gördüğü değer farklı ve hangisinin geçerli olduğu hiçbir yerde yazmıyor.

**Kanıt:** Aynı motor (2000 N, pintle):
  Kesit hover: 'Pintle post | D_pintle: 23.1 mm | Skip distance ~ 23.1 mm'
  Kesit hover: 'Annular oxidizer sheet | Gap: 0.69 mm'
  Gerçek InjectorDesign çıktısı: pintle_diameter = 25.0 mm, gap = 0.300 mm  (gap 2.3x sapma)
motor_results['injector_design'] anahtarları: injector_type, oxidizer_flow_rate_kg_s, injection_velocity_m_s, number_of_orifices, orifice_diameter_mm, injection_pressure_drop_bar, manifold_diameter_mm, discharge_coefficient, total_injector_area_mm2 — pintle_diameter_mm / annulus_gap_mm YOK.

**Önerilen çözüm:** InjectorDesign'ın pintle_diameter/gap değerlerini motor_results['injector_design']'a yaz ve kesit oradan okusun. Değer yoksa hover'da sayı verme, 'schematic' yaz. Aynı sorun swirl (spray_angle 45° varsayılanı) ve impingement (60° varsayılanı) dallarında da var.

### hrma/export/cad_visualization.py:1648-1671 (_get_component_details); UI: templates/liquid.html:4620-4680 updateCadDescription
*Kapsam: Analiz modülleri*

**Uydurma olan:** Sıvı sayfasındaki "Detailed CAD" panelinin "Component Details" bloğu tamamen sabit: soğutma kanal sayısı 24, malzemeler 'Inconel 718' / 'C-C Composite' / 'Stainless Steel 316L', soğutma tipi 'Regenerative'. Enjektör delik sayısı da sabit — istek gövdesinde JS `injector_holes: 24` gönderiyor (liquid.html:4623), çözücünün hesapladığı `injector_design.number_of_elements` kullanılmıyor.

**Kullanıcı etkisi:** Kullanıcı CAD görselinin altında "Injector: unlike_impinging (24 holes)", "Cooling: Regenerative (24 channels)", "Chamber: Inconel 718" okuyor ve bunları kendi tasarımının bileşen özeti sanıyor. Kullanıcı film soğutma seçse, farklı malzeme seçse bile aynı metin çıkıyor. Ayrıca sıvı çözücü kendi soğutma analizinde 80 kanal kullanıyor (liquid_rocket_engine.py:863) — kullanıcı aynı oturumda hem 80 hem 24 görüyor.

**Kanıt:** Kod: `'cooling': {'type': 'Regenerative', 'channel_count': 24, ...}`, `'materials': {'chamber': 'Inconel 718', 'nozzle': 'C-C Composite', 'injector': 'Stainless Steel 316L'}`.
liquid.html:4623 `injector_holes: 24,` (form/çözücüden okunmuyor, sabit).
liquid_rocket_engine.py:863 `n_channels = 80  # Number of cooling channels` ve 911 `'cooling_channels': n_channels` → aynı sayfada 80 raporlanıyor.

**Önerilen çözüm:** component_details'i currentResults'tan doldur: injector_design.number_of_elements, cooling_system.cooling_channels, kullanıcının seçtiği malzeme. Veri yoksa satırı gösterme. Sabit malzeme listesi ancak 'reference design' olarak açıkça etiketlenirse kalabilir.

### hrma/export/openrocket_integration.py:259 (_create_eng_file) ve 442-518 (generate_flight_profile) / 288-310 (_calculate_flight_performance)
*Kapsam: Analiz modülleri*

**Uydurma olan:** (a) .eng dosyasının motor satırındaki yüklü kütle `loaded_mass = prop_mass + 0.5` — kasa kütlesi her motorda sabit 0.5 kg varsayılıyor. (b) generate_flight_profile'da itki, `abs(thrust_time - t) < 0.01` toleransıyla eşleşme aranarak örnekleniyor; zaman ızgaraları uyuşmadığı için adımların çoğunda itki 0 alınıyor ve irtifa/hız serileri anlamsız çıkıyor. Aynı yanıtta closed-form `estimated_apogee` bambaşka bir sayı veriyor.

**Kullanıcı etkisi:** (a) OpenRocket uçuş simülasyonu yüklü kütleyi doğrudan kullanır; 10 kg yakıtlı bir motorun kasası 0.5 kg değildir — apoje tahmini sistematik olarak yüksek çıkar. (b) /api/export-simulation ve /calculate yanıtındaki 'flight_profile' altında iki çelişkili irtifa sayısı dönüyor; kullanıcı hangisini okursa 100 kattan fazla farklı sonuç alır. (Not: bu iki uç şu an hiçbir şablondan çağrılmıyor — /calculate yanıtındaki openrocket_data render edilmiyor. Bu yüzden 'major', 'critical' değil.)

**Kanıt:** (a) Kod: `loaded_mass = prop_mass + 0.5  # Add case mass estimate`. Üretilen .eng motor satırı: `N30-UZAYTEK-SOLID 30.0 500.0 P 10.000 10.500 UZAYTEK` — 10 kg yakıt, 10.5 kg yüklü.
(b) Çalıştırılan kanıt: 200 zaman noktasının yalnız 13'ünde itki eşleşti (kalan 187 adımda thrust=0). Rapor edilen max_altitude = 1277.2 m, aynı yanıttaki performance_summary.estimated_apogee = 171090.4 m (134x fark).

**Önerilen çözüm:** (a) Kasa kütlesini CAD/yapısal kütle tahmininden al veya .eng'de yalnız yakıt kütlesini yaz ve kullanıcıdan yüklü kütle iste. (b) İtkiyi np.interp ile ara-değerle; iki apoje kaynağından birini kaldır. Kullanılmıyorlarsa fonksiyonları silmek de geçerli bir çözüm.

### hrma/analysis/safety_analysis.py:289-290 (+ _calculate_radiant_heat_distance, satır ~470)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Radyan ısı tehlike mesafesi, ışıyan YÜZEY ALANI yerine cidar kalınlığının 100 katı geçilerek hesaplanıyor. `_calculate_radiant_heat_distance(self, temperature, area)` imzası m² bekliyor; çağıran `wall_thickness * 100` yolluyor (0.005 m -> 0.5 'm²'). Üstelik ışıyan yüzey sıcaklığı olarak dış cidar değil HAZNE GAZI sıcaklığı (3000 K) kullanılıyor; Stefan-Boltzmann T^4 olduğu için akı ~123 kat şişiyor.

**Kullanıcı etkisi:** Çıktı `radiant_heat_hazard_distance_m` adıyla dönüyor — kullanıcı bunu 'test sırasında kaç metre uzakta durmalıyım' diye okur. Ayrıca `thermal_protection_required = (mesafe > 3.0)` bayrağını, o da Güvenlik panelindeki görünür 'Thermal' risk skorunu (1-5) ve ağırlıklı genel risk seviyesini besliyor. Fiziksel olarak anlamsız bir sonuç: cidar KALINLAŞTIKÇA tehlike mesafesi BÜYÜYOR.

**Kanıt:** Kod:
    radiant_heat_distance = self._calculate_radiant_heat_distance(
        chamber_temperature, wall_thickness * 100  # convert to area approximation
    )

Çalıştırılmış kanıt (Flask test client, /analyze_safety, Tc=3000 K sabit):
  wall_thickness=0.005 m -> hazard distance  7.65 m  (kullanılan 'alan' = 0.5 m2)
  wall_thickness=0.020 m -> hazard distance 15.29 m  (kullanılan 'alan' = 2.0 m2)
  wall_thickness=0.050 m -> hazard distance 24.18 m  (kullanılan 'alan' = 5.0 m2)
Mesafe kalınlığın kareköküyle ölçekleniyor — yani sayı tamamen kalınlıktan türüyor, gerçek ışıyan alandan değil.

**Önerilen çözüm:** Gerçek dış yüzey alanını hesapla (A = pi*D*L + uç kapaklar, chamber_diameter/chamber_length zaten motor_data'da mevcut) ve ışıyan sıcaklık olarak gaz sıcaklığını değil dış cidar sıcaklığını kullan. Cidar sıcaklığı için mevcut HeatTransferAnalyzer sonucunu (Bartz + soğutma) parametre olarak geçir. Gerçek alan/sıcaklık yoksa alanı uydurmak yerine ValueError yükselt ya da alanı çıktıda 'assumed_radiating_area_m2' olarak AÇIKÇA raporla.

### hrma/analysis/safety_analysis.py:278 (_analyze_thermal_safety)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Cidar sıcaklığı `wall_temperature = chamber_temperature * 0.3` sabit katsayısıyla üretiliyor. Malzeme, cidar kalınlığı, soğutma tipi, kütle debisi, Bartz katsayısı — hiçbiri girmiyor. Projede bunu gerçekten hesaplayan bir modül (heat_transfer_analysis.HeatTransferAnalyzer, Bartz) zaten var; bu ikinci, çelişkili kaynak.

**Kullanıcı etkisi:** `estimated_wall_temperature_k` alanı ve ondan türeyen `cooling_required` bayrağı, Güvenlik panelindeki 'Thermal' risk skorunu ve genel risk rozetini (LOW/MEDIUM/HIGH/CRITICAL) belirliyor. Kullanıcı emniyet kararı için bu rozete bakıyor. Aynı motorda Termal paneli 2978 K derken Güvenlik paneli 900 K diyor — kullanıcı hangisinin doğru olduğunu bilemez.

**Kanıt:** Kod:
    wall_temperature = chamber_temperature * 0.3  # Rough approximation
    ...
    'cooling_required': wall_temperature > steel_max_temp / self.safety_margins.temperature_safety_factor

Çalıştırılmış kanıt (aynı motor: Pc=40 bar, Tc=3000 K, t=5 mm):
  /analyze_safety   -> estimated_wall_temperature_k = 900.0   (tam olarak 0.3*3000)
  Tc=2200 K yapınca -> 660.0                                   (tam olarak 0.3*2200)
  /analyze_thermal_safety (Bartz) -> estimated_wall_temperature = 2978.03 K

Risk skoru duyarlılık testi (individual_risks.thermal, overall_score, level):
  taban (steel, Tc=3000)   -> (4.0, 2.15, MEDIUM)
  material=inconel_718     -> (4.0, 2.15, MEDIUM)   <-- süperalaşım hiç fark etmiyor
  wall_thickness=0.05 m    -> (4.0, 2.15, MEDIUM)   <-- 10x kalınlık fark etmiyor
  Tc=2000 K                -> (3.0, 2.00, MEDIUM)   <-- SADECE Tc etkiliyor

**Önerilen çözüm:** _analyze_thermal_safety'yi kendi 0.3 katsayısıyla cidar sıcaklığı üretmekten çıkar; HeatTransferAnalyzer'ın gerçek sonucunu (wall_analysis / gas_side_analysis) analyze_comprehensive_safety üzerinden parametre olarak al. Malzeme sıcaklık limitlerini de sabit 800/600 K yerine materials_db'den (max_service_temperature) çek — `material` zaten endpoint'ten geçiyor ama yapısal kısımda kullanılıp termal kısımda yok sayılıyor.

### hrma/analysis/safety_analysis.py:285-286
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Termal gerilme sabit kodlanmış çelik özellikleriyle hesaplanıyor: E=200 GPa, alfa=12e-6, ve delta-T olarak (cidar sıcaklığı - 293 K) yani tam ankastre kısıt varsayımı. Kullanıcının seçtiği malzeme hiç okunmuyor. materials_db'de her malzemenin gerçek E ve alfa değeri mevcut.

**Kullanıcı etkisi:** `thermal_stress_mpa` alanı Güvenlik analizi yanıtında dönüyor ve malzeme ne seçilirse seçilsin AYNI kalıyor. Aynı motor için Yapısal panel 3.3 MPa (çelik) / 0.1 MPa (alüminyum) derken Güvenlik yanıtı her ikisinde de 1456.8 MPa veriyor — ~440 kat fark ve hiçbir çeliğin kopma dayanımının üstünde. Kullanıcı iki panelden hangisine inanacağını bilemez.

**Kanıt:** Kod:
    thermal_expansion_steel = 12e-6 * (wall_temperature - 293)  # strain
    thermal_stress_estimate = 200e9 * thermal_expansion_steel   # Pa (simplified)

Çalıştırılmış kanıt (Pc=40 bar, Tc=3000 K, D=0.1 m, t=5 mm):
  material=steel_4130:
      /analyze_safety            thermal_stress_mpa        = 1456.8
      /analyze_structural_safety thermal_hoop_stress_MPa   =    3.3
  material=aluminum_6061:
      /analyze_safety            thermal_stress_mpa        = 1456.8   <-- DEĞİŞMEDİ
      /analyze_structural_safety thermal_hoop_stress_MPa   =    0.1
Sayı malzemeden tamamen bağımsız — sabit çelik varsayımının kanıtı.

**Önerilen çözüm:** Bu ikinci hesabı tamamen kaldır ve structural_analysis'in zaten materials_db'den E/alfa çekerek hesapladığı thermal_hoop_stress değerini kullan (structural_safety sonucu aynı fonksiyonda mevcut). Ayrı bir tahmin gerekiyorsa en azından get_material(material)['youngs_modulus'] / ['thermal_expansion'] kullan ve cidar boyunca delta-T'yi tam ankastre (T_wall - 293) yerine cidar içi gradyandan al.

### hrma/app.py:3243 ve 3247 (/api/trajectory-analysis)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Yörünge hesabında fırlatma açısı ve rüzgâr hızı istekten okunmayıp sabit kodlanıyor: `'launch_angle': 85.0` ve `'wind_speed': 0.0`. Kullanıcının formda girdiği değerler frontend tarafından GÖNDERİLİYOR ama backend'de sessizce atılıyor. Aynı dosyada başka uçlar (app.py:522, app.py:1810) aynı alanı `data.get('launch_angle', 85)` ile DOĞRU şekilde okuyor — yani çelişkili ikinci kaynak.

**Kullanıcı etkisi:** Advanced sayfasındaki Trajectory Analysis formunda 'Launch Angle (degrees)' ve 'Wind Speed (m/s)' alanları var; tooltip'leri açıkça '90 = dikey fırlatma, 45 = maksimum menzil yörüngesi' ve 'Yörüngeyi etkileyen yatay rüzgâr hızı' diyor. Kullanıcı 45 derece ve 20 m/s girip 'Calculate Trajectory Performance' basıyor; sonuç her zaman 85 derece ve sıfır rüzgâr için hesaplanıyor. Apoje, menzil ve sürüklenme değerleri girdiyle alakasız.

**Kanıt:** Backend (app.py):
        launch_params = {
            ...
            'launch_angle': 85.0,  # Near-vertical launch (85 degrees)
            ...
            'wind_speed': 0.0,  # No wind
            'wind_direction': 0.0  # Wind direction in degrees
        }

Frontend gerçekten yolluyor (hrma/static/js/app.js:2097-2129):
        const launchAngle = parseFloat(document.getElementById('launch_angle')?.value || 90);
        const windSpeed  = parseFloat(document.getElementById('wind_speed')?.value || 0);
        ... launch_angle: launchAngle, wind_speed: windSpeed
UI alanları mevcut: hrma/templates/advanced.html:1518 (launch_angle), :1528 (wind_speed).

Çalıştırılmış kanıt (Flask test client, aynı motor, sadece açı değişti):
    launch_angle = 30  -> NO-EFFECT (66 sayısal alanın 66'sı bit-özdeş)
    wind_speed   = 40  -> NO-EFFECT (66/66 bit-özdeş)
Ayrıca trajectory_start_altitude / trajectory_end_altitude / trajectory_points de gönderiliyor ve hiç okunmuyor (üçü de NO-EFFECT).
NOT: modülün kendisi (hrma/analysis/trajectory_analysis.py:194-200) launch_angle ve wind_speed'i doğru kullanıyor — hata yalnızca endpoint katmanında.

**Önerilen çözüm:** launch_params sözlüğünü istekten doldur: 'launch_angle': float(data.get('launch_angle', 85)), 'wind_speed': float(data.get('wind_speed', 0)), 'wind_direction': float(data.get('wind_direction', 0)). trajectory_start_altitude / end_altitude / points ya gerçekten kullanılsın ya da UI'dan kaldırılsın.

### hrma/app.py:3309 (motor_type) ve hrma/analysis/safety_analysis.py:79 (burn_time), :428 (thrust)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Güvenlik panelinin üç girdi alanı backend'e ulaşıyor ama hiç kullanılmıyor:
- `motor_type`: app.py:3309'da yerel değişkene okunuyor, motor_data sözlüğüne KONMUYOR ve analyze_comprehensive_safety'ye geçirilmiyor — tamamen düşüyor.
- `burn_time`: safety_analysis.py:79'da okunuyor, fonksiyonun devamında hiçbir yerde kullanılmıyor.
- `thrust`: _analyze_explosive_hazards'a, oradan _calculate_fragment_hazards(propellant_mass, thrust)'a geçiriliyor; fonksiyon parametreyi alıyor ama gövdesinde bir kez bile kullanmıyor (parça hızı yalnız propellant_mass ve case_mass'tan Gurney ile geliyor).

**Kullanıcı etkisi:** Güvenlik panelinde 'Motor Type', 'Thrust (N)' ve 'Burn Time (s)' alanları görünür stepper'larla duruyor (safety_panel.js:280,283,284). Kullanıcı itkiyi 1 kN'dan 9 kN'a çıkarıp yeniden çalıştırıyor; parça menzili, tahliye mesafesi, risk skoru — hiçbir sayı kımıldamıyor. Kullanıcı bu alanların emniyet değerlendirmesini etkilediğine inanıyor.

**Kanıt:** Kod (safety_analysis.py):
    def _calculate_fragment_hazards(self, propellant_mass: float, thrust: float) -> Dict:
        case_mass = propellant_mass * 0.15
        gurney_velocity = 2700
        fragment_velocity = gurney_velocity * np.sqrt(propellant_mass / (case_mass + propellant_mass / 2))
        ...   # 'thrust' gövdede hiç geçmiyor

Çalıştırılmış kanıt (/analyze_safety, 219 sayısal alan):
    motor_type = 'solid'  -> NO-EFFECT (219/219 bit-özdeş)
    thrust     = 9000     -> NO-EFFECT (219/219 bit-özdeş)
    burn_time  = 40       -> NO-EFFECT (219/219 bit-özdeş)
Karşılaştırma için aynı testte propellant_mass=50 -> 19 alan değişiyor, chamber_diameter=0.25 -> 3 alan değişiyor (yani harness çalışıyor).

**Önerilen çözüm:** İki seçenekten biri: (a) alanları gerçekten kullan — motor_type'ı propellant TNT eşdeğeri/patlama sınıfı seçimine bağla, burn_time'ı termal maruziyet ve yangın senaryosu süresine bağla, thrust'ı ya kullan ya imzadan kaldır; veya (b) kullanılmıyorlarsa safety_panel.js fields listesinden SİL. Ara çözüm olarak bırakılacaksa panelde 'bilgi amaçlı, risk skorunu etkilemez' etiketi zorunlu.

### hrma/visualization/visualization.py:2135-2153 (create_chamber_pressure_mixture_ratio_3d_surface) — Analiz Güvertesi 'Advanced Performance' panelini besliyor
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** '3D Performance Surface — Isp vs Chamber Pressure & O/F' yüzeyi hiçbir termokimya çözmüyor. Kullanıcının girdiği `base_isp` sabitini iki adet uydurulmuş analitik şekil fonksiyonuyla çarpıyor: pressure_factor = 1 + 0.15*ln(Pc/20)*exp(-(Pc-50)^2/800) ve mixture_factor = 1 - 0.3*((OF-OF_opt)/OF_opt)^2. Katsayıların (0.15, 800, 0.3) hiçbir kaynağı yok. 'Kararsızlık bölgesi' maskesi de uydurma: (Pc>80 & OF<2) | (Pc<15 & OF>5) koşulunda Isp %30 düşürülüyor. Yakıt/oksitleyici yüzeye hiç girmiyor.

**Kullanıcı etkisi:** Figür başlığı '3D Performance Map ... NASA SP-125 Based Analysis', bilgi kartı referansı 'NASA SP-125 Liquid-Propellant Rocket Engine Performance' ve açıklaması 'Shows optimum O/F ratio and chamber pressure regions with combustion instability bands'. Kullanıcı bunu gerçek bir performans haritası sanıp 'Pc'yi 50 bara çıkarırsam Isp 344 s olur' ya da 'şu bölgede yanma kararsızlığı var' diye tasarım kararı verir. Panel `fromResults` ile base_isp'yi gerçek motor Isp'sinden dolduruyor, bu da sayıyı daha da inandırıcı yapıyor.

**Kanıt:** Kod:
    ISP = base_isp * pressure_factor * mixture_factor
    instability_mask = (PC > 80) & (OF < 2.0) | (PC < 15) & (OF > 5.0)
    ISP[instability_mask] *= 0.7

Çalıştırılmış kanıt: base_isp'yi 300 -> 600 yaptığımda yüzeyin HER noktasında oran tam olarak 2.000000 (min=max=2.000000). Yani yüzey = base_isp x sabit şekil; hiçbir fizik yeniden çözülmüyor. base_isp=300 ile tepe Isp = 344.16 s (uydurma %14.7 kazanç).

**Önerilen çözüm:** Yüzeyi mevcut CEA/denge zincirinden (HybridRocketEngine._instantaneous_performance veya kinetic_efficiency'nin kullandığı analizör) Pc x O/F ızgarasında gerçekten hesaplat — yavaşsa ızgarayı 8x8'e düşür ve önbelleğe al. Bu yapılamıyorsa figürü kaldır; hiçbir koşulda 'NASA SP-125' referansıyla sunma. Kararsızlık bandı ya kaynaklı bir kritere (ör. SP-8089 dP/Pc) bağlanmalı ya da tamamen çıkarılmalı.
KAPSAM NOTU: dosya hrma/analysis/ altında değil, ama beslediği panel (performance_panel.js) Analiz Güvertesi'nin bir paneli ve advanced/liquid/solid üç sayfada da yüklü.

### hrma/visualization/visualization.py:2361-2373 (create_wall_heat_flux_waterfall_plot) — Analiz Güvertesi 'Advanced Performance' paneli
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Cidar ısı akısı yüzeyi Bartz'ı, hazne basıncını, kütle debisini, malzemeyi hiç kullanmıyor. Kullanıcının girdiği `base_heat_flux` sabitini iki uydurma şekille çarpıyor: eksenel olarak sabit 50 mm genişlikli bir Gauss (axial_factor = 1 + 2*exp(-((X-throat)/50)^2), yani boğazda daima tam 3x) ve zamansal olarak sabit 5 s zaman sabitli bir kurulum eğrisi (transient_factor = 1 + 0.5*(1-exp(-T/5))). Üstüne 'termal kaçış' adıyla, 5 MW/m2'yi aşan hücreler ayrıca 1.5 ile çarpılıp süreksiz bir sıçrama yaratılıyor.

**Kullanıcı etkisi:** Figür 'Wall Heat Flux Distribution: Thermal Runaway Analysis / NASA SP-8124 Thermal Design Criteria' başlığıyla sunuluyor ve kırmızı 'Thermal Runaway Risk' işaretleri basıyor. Kullanıcı soğutma yeterli mi diye buna bakıyor. Varsayılan girdilerle (2 MW/m2) grafik zaten 9.0-13.5 MW/m2 tepe ve termal kaçış alarmı gösteriyor — tamamen uydurma bir alarm. Ayrıca akının yanma boyunca %50 artması fiziksel değil (sabit Pc'de gaz tarafı akı kabaca sabittir, artan şey cidar sıcaklığıdır).

**Kanıt:** Kod:
    axial_factor = 1.0 + 2.0 * np.exp(-((X - throat_position) / 50)**2)
    transient_factor = 1.0 + 0.5 * thermal_buildup      # thermal_buildup = 1-exp(-T/5)
    HEAT_FLUX = base_heat_flux * axial_factor * transient_factor
    HEAT_FLUX[runaway_mask] *= 1.5

Çalıştırılmış kanıt (varsayılan: burn_time=30, base=2e6 W/m2):
    t=0   tepe akı =  8.990 MW/m2
    t=son tepe akı = 13.474 MW/m2   (tam %50 artış — transient_factor'ın kendisi)
Girdi olarak Pc, mdot, malzeme veya soğutma tipi alınmıyor; sonuç sadece base_heat_flux ile lineer ölçekleniyor.

**Önerilen çözüm:** Projede zaten gerçek eksenel Bartz profili var: HeatTransferAnalyzer.analyze_axial_profile (POST /api/analysis/wall-profile, q_conv_W_m2 ve h_g_W_m2K dizileri döndürüyor ve girdilere doğru tepki veriyor — testte throat_diameter/expansion_ratio/gamma/nozzle_type hepsi sonucu değiştiriyor). Şelale figürünü o profil üzerine kur; zaman ekseni gerekiyorsa gerçek geçici cidar ısınmasından (thermal_protection.heat_sink çözümü) al. Uydurma runaway çarpanını kaldır; kritik akı karşılaştırması gerçek q ile yapılsın.

### hrma/visualization/visualization.py:2233-2258 (create_nozzle_mach_area_ratio_contour) — Analiz Güvertesi 'Advanced Performance' paneli
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Üç ayrı kusur: (1) Newton iterasyonu ıraksıyor ve fiziksel olmayan Mach sayıları üretiyor. (2) Yakınsak (converging) bölge de supersonik dalda çözülüyor — ses altı akış supersonik gösteriliyor; ayrıca area_ratio<=1 dalında `mach = 0.5*area_ratio` hesaplanıp listeye EKLENMİYOR, bu yüzden sütunlar kayıyor. (3) 'Sınır tabaka etkisi' diye uydurma bir çarpan (y_norm>0.8 için 1-0.3*(y_norm-0.8)/0.2) uygulanıyor; ayrıca Mach alanı yarıçap boyunca sabit kopyalanıyor (MACH[:, i] = mach), yani '2D kontur' aslında 1D. Radyal alan gerçek nozul yarıçapından bağımsız sabit +-0.05 m.

**Kullanıcı etkisi:** Figür 'Nozzle Mach Number Distribution & Flow Analysis / NASA-STD-5012 Compliant Design' başlığıyla ve 'Potential Shock Zone' ek açıklamasıyla sunuluyor. Kontur ölçeği 0.5-4.0 Mach'a ayarlı ama alan 7877'ye kadar değer içeriyor; kullanıcı akış alanı analizi sandığı şeyde tamamen anlamsız bir grafik görüyor.

**Kanıt:** Kod:
        if area_ratio <= 1.0:
            mach = 0.5 * area_ratio          # <-- hesaplanıyor ama append EDİLMİYOR
        else:
            mach_guess = 2.0 * np.sqrt(area_ratio - 1)
            for _ in range(10): ...          # sönümsüz Newton
            mach_numbers.append(max(1.0, mach_guess))

Çalıştırılmış kanıt (throat_area=0.001, nozzle_length=0.1, eps=16):
    MACH ızgara şekli (30, 50)
    merkez hattı ilk 8 sütun: [1257.96  835.71  71.75  0.70  0.70  0.70  0.70  426.17]
    son sütun: [5408.51  5461.48  5513.66]
    min/max: 0.7 / 7876.66
Gerçek bir nozulda maksimum Mach ~4-5 mertebesindedir; 7877 çözümün ıraksadığının kanıtıdır.

**Önerilen çözüm:** Bu figürü kendi izantropik çözücüsüyle üretmeyi bırak; hrma/analysis/nozzle_flow_1d.NozzleFlow1D zaten doğrulanmış quasi-1D çözüm veriyor (POST /api/flow-analysis, fidelity='engineering' -> stations.mach dizisi; testte tüm geometri/gaz girdilerine doğru tepki veriyor). Kontur yarıçap eksenini gerçek duvar konturundan (sample_nozzle_inner_contour) al. Uydurma 'sınır tabaka' çarpanını kaldır veya gerçek bir profil (1/7 kuvvet yasası) kullanıp öyle etiketle.

### hrma/app.py:3839 (/api/get-fuel-properties)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Sıvı/katı yakıt yoğunluğu `species.molecular_weight * 10` (sıvı fazda) veya doğrudan molekül ağırlığı (diğer fazlarda) olarak 'hesaplanıyor'. Yanıt `'source': 'NASA CEA Database', 'real_time': True` ile etiketleniyor.

**Kullanıcı etkisi:** Bu uç şu an hiçbir şablon tarafından çağrılmıyor (istemci tüketicisi yok), ama uygulama açıkken erişilebilir bir API ve 'NASA CEA / real_time' iddiasıyla tamamen yanlış yoğunluk dağıtıyor. Bu uç bir gün UI'ya bağlanırsa (veya kullanıcı/harici bir araç çağırırsa) RP-1'i 1673 kg/m³, LH2'yi 2.0 kg/m³, HTPB'yi 54 kg/m³ olarak öğrenir.

**Kanıt:** app.py:3839 →
  'density': species.molecular_weight * 10 if species.phase == 'liquid' else species.molecular_weight,
Canlı test:
  rp1     source='NASA CEA Database' real_time=True density=1673.1  (gerçek 810)
  lh2     source='NASA CEA Database' real_time=True density=2.016   (gerçek 71)
  htpb    source='NASA CEA Database' real_time=True density=54.09   (gerçek 920)
  methane density=16.043 (gerçek 423), mmh=460.7 (874), udmh=601 (791), paraffin=352.7 (900)
Ayrıca aynı dosyadaki get_cached_fuel_properties (app.py:3878+) RP-1 için 810 diyor — uç kendi içinde de çelişiyor.

**Önerilen çözüm:** MW*10 formülünü kaldır; yoğunluğu chemical_database/propellant_database'in gerçek density alanından oku, yoksa alanı hiç döndürme. `'real_time': True` iddiasını kaldır (chemical_db yerel bir tablo). Uç tüketilmiyorsa tamamen sil — canlı bir yanlış-veri kaynağı olarak durmasın.

### hrma/data/database_integrations.py:346-378 (test_connections) + hrma/templates/solid.html:415, liquid.html:518, advanced.html (aynı rozet)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** 'NASA CEA Connected' bağlantı rozeti. test_connections, CEA'yı `validate_fuel_composition([('C4H6',100.0)])` çağrısının 'success' dönmesine bakarak 'connected' işaretliyor — ama bu fonksiyon HİÇ ağ çağrısı yapmıyor, 13 elemanlı yerel bir atom ağırlığı sözlüğüne bakıyor. Dolayısıyla rozet ağ olsun olmasın DAİMA yeşil.

**Kullanıcı etkisi:** Üç motor sayfasında da 'Propellant Data' panelinin başlığında yeşil 'NASA CEA Connected' yazıyor. Kullanıcı formdaki termokimya değerlerinin canlı NASA CEA'dan geldiğine inanıyor; gelmiyor. NIST rozeti de benzer: modülün kendi docstring'i 'Gerçek NIST HTML yapısına göre tam ayrıştırma UYGULANMADI' diyor, canlı testte HTTP 200 dönüyor ama çıkarılan özellik sözlüğü BOŞ ({}) — buna rağmen 'NIST WebBook Connected' yazıyor.

**Kanıt:** database_integrations.py:369-373 →
  cea_result = self.cea.validate_fuel_composition([('C4H6', 100.0)])
  results['cea'] = {'status': 'connected' if cea_result['status'] == 'success' else 'error', ...}
inspect ile: NasaCeaAPI.validate_fuel_composition + _validate_component kaynağında 'self.session' ve 'requests' geçmiyor → ağ çağrısı yok.
Canlı test: GET /api/database-status → {'cea': {'status':'connected','message':'Connected successfully'}, 'nist': {'status':'connected',...}}
NistWebBookAPI.get_compound_properties('N2O') → status='success' ama data={} (regex hiçbir şey çıkaramadı).
database_integrations.py:67-72 docstring: 'NOT: Gerçek NIST HTML yapısına göre tam ayrıştırma UYGULANMADI'.

**Önerilen çözüm:** CEA için 'connected' kavramını kaldır; rozeti 'NASA CEA reference tables (bundled, offline)' yap. NIST için status'ü ayrıştırılan özellik sayısına bağla (properties boşsa 'error'/'no data'), sadece HTTP 200'e değil.

### hrma/templates/solid.html:2506-2612 (collectAllParameters) + hrma/app.py:1448-1490 (/calculate_solid) + hrma/engines/solid_rocket_engine.py:141-178 (_apply_overrides)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Katı motor formu 76 alan gönderiyor; uç ve motorun _apply_overrides'ı bunların yalnız ~15'ini okuyor. Kalan ~54 alan hiçbir konfigürasyonda çıktıyı değiştirmiyor. Sıvı sayfasında bunun için dürüstlük paneli var (liquid.html:496-513 'Solver Input Scope'), katı ve hibrit sayfasında YOK.

**Kullanıcı etkisi:** Kullanıcı 3 ondalık hassasiyetle 7 ayrı verim katsayısı giriyor (Combustion Efficiency, Cf Efficiency, Overall Efficiency, Discharge Coeff, Kinetic Efficiency, Divergence Loss, Two-Phase Loss) — hiçbiri Isp'yi değiştirmiyor (yalnız nozzle_efficiency çalışıyor). Kasa dayanımı (yield_strength), emniyet faktörü, kasa kalınlığı ve astar kalınlığı yok sayılıyor ama sonuçta yapısal/termal 'analiz' tabloları gösteriliyor. atm_pressure ve test_altitude yok sayılıyor → raporlanan Isp her zaman sabit ortam basıncında. molecular_weight (yakıt kataloğunun otomatik doldurduğu alan) hiç kullanılmıyor. outer_diameter (grain dış çapı) yok sayılıyor → grain her zaman kasayı doldurur varsayılıyor, yakıt kütlesi şişiyor. propellant_type formda HİÇ gönderilmiyor (yalnız propellant_name var) → motor her zaman 'apcp' kabul ediyor.

**Kanıt:** Duyarlılık testi (her alan tek tek değiştirilip tam JSON yanıt karşılaştırıldı), aşırı değerlerle teyit:
  combustion_efficiency 0.95→0.5 ETKISIZ | cf_efficiency 0.98→0.5 ETKISIZ | overall_efficiency 0.92→0.4 ETKISIZ
  discharge_coeff 0.98→0.5 ETKISIZ | kinetic_efficiency 0.97→0.5 ETKISIZ | divergence_loss 0.02→0.3 ETKISIZ
  two_phase_loss 0.98→0.5 ETKISIZ | yield_strength 250→1200 ETKISIZ | safety_factor 2.5→10 ETKISIZ
  case_thickness 8→40 ETKISIZ | web_thickness 25→5 ETKISIZ | insulation_thickness 3→20 ETKISIZ
  propellant_mass 0→900 ETKISIZ | atm_pressure 101.325→20 ETKISIZ | test_altitude 0→20000 ETKISIZ
  erosive_m 0.8→0.1 ETKISIZ | outer_diameter 100→300 ETKISIZ | molecular_weight 28.5→60 ETKISIZ
  nozzle_material 'graphite'→'tungsten' ETKISIZ | fin_count/fin_width/fin_length (grain_type='finocyl' iken) ETKISIZ
molecular_weight için tam JSON yanıt bit-bit AYNI çıktı (IDENTICAL FULL RESULT: True).
propellant_type: solid.html:2506-2612'de yok; app.py:1481 data.get('propellant_type','apcp') → daima 'apcp'.
Etkili olanlar: burn_rate_a, burn_rate_n, chamber_diameter, chamber_pressure, char_velocity, core_diameter, density, erosive_k, flame_temp, gamma, grain_count, grain_length, grain_type, initial_temp, nozzle_efficiency, case_material, (star_points/star_radius yalnız grain_type='star' iken).

**Önerilen çözüm:** 1) liquid.html:496-513'teki 'Solver Input Scope' dürüstlük panelinin aynısını solid.html ve advanced.html'e ekle ve listeyi bu denetimin çıkardığı 'etkili alanlar' kümesiyle birebir tut. 2) Etkisiz alanları ya bağla ya da UI'da görsel olarak 'recorded only, does not drive the solver' rozetiyle işaretle. 3) propellant_type'ı formdan gönder (propellant_name yerine katalog anahtarını) — aksi halde erozif yanma katsayısı, egzoz MW'si ve maliyet tablosu daima APCP'nin. 4) atm_pressure/test_altitude'u Isp hesabına bağla veya sayfadan kaldır. 5) Kalıcı bekçi testi: her sayfa için 'ilan edilen etkili alan listesi' ile gerçek duyarlılık testini karşılaştıran bir pytest yaz.

### hrma/engines/solid_rocket_engine.py:1161,1162,1196,1201,1202,1219-1221 + hrma/templates/solid.html:3400,3402,3403,3420-3422,3429-3430
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Katı motor sonucundaki 'Termal Analiz' ve 'İmalat' tablolarındaki bir dizi yüzde ve derecelendirme sabit kodlanmış: thermal_efficiency_percent=85.2, insulation_effectiveness=94.8, thermal_protection_rating='Excellent', thermal_barrier_effectiveness=92.5, joint_reliability=98.2; karışım oranları oxidizer 68% / fuel 18% / binder 12% / additives 2%; kürleme 333 K, 24 saat; case_max_temp_k=673, grain_max_temp_k=423, safety_margin_k=150.

**Kullanıcı etkisi:** Kullanıcı sonuç sayfasında 'Insulation Effectiveness: 94.8%', 'Thermal Efficiency: 85.2%', 'Thermal Protection Rating: Excellent' satırlarını, hesaplanmış convective_heat_flux ve case_temperature_k ile AYNI tabloda görüyor — hangisinin hesaplandığını, hangisinin sabit olduğunu ayırt edemiyor. Karışım oranları propellant_type'a bağlı görünüyor ama propellant_type formdan hiç gelmediği için (yukarıdaki bulgu) daima 68/18/12 gösteriliyor; KNDX (KNO3 %65 / dekstroz %35) seçen kullanıcı da 68/18/12 görüyor. 94.8 gibi tek ondalıklı bir sayı sahte kesinlik üretiyor.

**Kanıt:** solid_rocket_engine.py:1196-1203 →
  'thermal_efficiency_percent': 85.2
  ...
  'insulation_effectiveness': 94.8,
  'thermal_protection_rating': 'Excellent'
satır 1219-1221 →
  'oxidizer_percent': 68 if self.propellant_type == 'apcp' else 75,
  'fuel_percent': 18 if self.propellant_type == 'apcp' else 15,
  'binder_percent': 12 if self.propellant_type == 'apcp' else 8,
solid.html:3402 →
  Insulation Effectiveness: ${(heatTransfer.insulation_effectiveness || 94.8).toFixed(1)}%
solid.html:3420-3422 → Oxidizer/Fuel/Binder yüzdeleri aynı tabloda render ediliyor.
Canlı test: propellant_type formdan gelmediği için daima 'apcp' dalı seçiliyor (r.get('propellant_type') == 'apcp' teyit edildi).

**Önerilen çözüm:** Hesaplanmayan bu alanları ya sonuç sözleşmesinden tamamen çıkar, ya da her birine `"basis": "assumed"` işareti ekleyip UI'da 'assumed' rozetiyle göster (app.py:3690+ _build_pdf_analysis_sections'ta uygulanan 'sabit/uydurma değer ÜRETİLMEZ' ilkesinin aynısı). Karışım yüzdelerini propellants_db kaydındaki gerçek oxidizer/fuel metninden türet ya da hiç gösterme. UI'daki `|| 94.8`, `|| 85.2`, `|| 68` gibi istemci-tarafı yedek sabitlerini de kaldır (backend hiç göndermese bile ekrana sayı basıyorlar).

### hrma/engines/liquid_rocket_engine.py:2283-2300 + hrma/templates/liquid.html:3992-3998
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Sıvı motor yapısal analizi merkezi materials_db'yi ve kullanıcının malzeme seçimini yok sayıp sabit 250 MPa akma + SF 4.0 kullanıyor. Dahası cidar kalınlığı allowable_stress'ten çözülüp ardından hoop gerilme AYNI kalınlıktan geri hesaplandığı için hoop_stress her zaman allowable_stress'e eşit çıkıyor; stress_margin daima 0.

**Kullanıcı etkisi:** Sıvı motor sonuç panelinde 'Hoop Stress: 62.5 MPa' ve 'Allowable Stress: 62.5 MPa' satırlarını gören kullanıcı bunun kendi tasarımı için hesaplanmış bir gerilme sanıyor. Oysa Pc 30 bar da olsa 200 bar da olsa sayı 62.5 MPa (=250/4). Ayrıca aynı motor /analyze_structural_safety ucundan geçirilirse materials_db'deki gerçek dayanımlar (ör. AISI 4130 için 460 MPa) kullanılıyor → aynı motor için iki farklı yapısal sonuç. materials_db.py docstring'i bu 'üçüncü sabit çelik' sorununun çözüldüğünü söylüyor, ama sıvı motorda hâlâ duruyor.

**Kanıt:** liquid_rocket_engine.py:2285-2294 →
  safety_factor = 4.0
  material_yield_strength = 250e6  # Pa
  allowable_stress = material_yield_strength / safety_factor
  chamber_wall_thickness = (chamber_internal_pressure * chamber_diameter/2) / allowable_stress
  actual_hoop_stress = (chamber_internal_pressure * chamber_diameter/2) / chamber_wall_thickness
Canlı test (/calculate_liquid, F=100 kN, RP-1/LOX):
  Pc=30  → wall_thickness=13.50 mm, hoop_stress=62.50, allowable=62.5, stress_margin=-1.19e-14
  Pc=100 → wall_thickness=24.65 mm, hoop_stress=62.50, allowable=62.5, stress_margin=-1.19e-14
  Pc=200 → wall_thickness=34.85 mm, hoop_stress=62.50, allowable=62.5, stress_margin=0.0
liquid.html:3997-3998 her ikisini de tabloya basıyor.
materials_db.py docstring satır 5-9: 'safety_analysis üçüncü bir sabit çelik (250/400 MPa) kullanıyordu → aynı motor için üç farklı emniyet faktörü raporlanabiliyordu.' (sıvı motorda düzeltilmemiş)

**Önerilen çözüm:** materials_db.get_material() ile kullanıcının seçtiği malzemeyi kullan; safety_factor'ü de malzeme kaydından (veya kullanıcı girdisinden) al. hoop_stress'i kalınlığın bağımsız bir girdisinden (kullanıcı case_thickness'i veya standart boru cidarı) hesapla; kalınlığı gerilmeden çözüp gerilmeyi kalınlıktan geri hesaplayan totolojiyi kır. Tautolojik kaldığı sürece stress_margin'i raporlama.

### hrma/app.py:3302-3348 (/analyze_safety) + hrma/static/js/panels/safety_panel.js:314,317,318
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Güvenlik panelinde 'Motor Type', 'Thrust (N)' ve 'Burn Time (s)' alanları var, üçü de POST gövdesine giriyor ve app.py motor_data sözlüğüne koyuyor; ama SafetyAnalyzer bunları hiç okumuyor — çıktı bit-bit aynı kalıyor.

**Kullanıcı etkisi:** Kullanıcı 1 kN'lik bir motor ile 50 kN'lik bir motoru aynı güvenlik sonucunu alarak karşılaştırıyor; 10 s ile 120 s yanma süresi arasında da fark yok. Panel bu alanları motor sonucundan otomatik dolduruyor (safety_panel.js fromResults: thrust, burn_time, motor_type), bu da kullanıcının 'sonucum bu değerlere göre hesaplandı' inancını pekiştiriyor.

**Kanıt:** Canlı test (/analyze_safety, diğer tüm alanlar sabit):
  thrust      1000→50000        YUTULDU (tam JSON aynı)
  burn_time   10→120            YUTULDU
  motor_type  'hybrid'→'solid'  YUTULDU
  propellant_type 'composite'→'double_base'  DEGISTI
  facility_type 'test_stand'→'bunker'        DEGISTI
  material 'steel_4130'→'aluminum_6061'      DEGISTI
  propellant_mass 5→500                      DEGISTI
app.py:3311-3326 üçünü de motor_data'ya koyuyor ama analyze_comprehensive_safety kullanmıyor.

**Önerilen çözüm:** Ya SafetyAnalyzer'da bu üç girdiyi kullan (motor_type → farklı tehlike sınıfı; thrust/burn_time → toplam salınan enerji, test standı reaksiyon yükü), ya da üç alanı panelden kaldır. Yarım yol: alanları 'context only — does not affect the computed hazard' notuyla işaretle.

### hrma/data/open_source_propellant_api.py:476-537 + hrma/data/offline_snapshot.json (entries: pubchem:htpb, pubchem:rp1, pubchem:apcp) + hrma/data/propellant_database.py:68+ vs hrma/data/propellants_db.py
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Üç ayrı yakıt veri kaynağı arasında çelişkiler ve yanlış kimyasal eşleşmeler. (a) Paketlenmiş çevrimdışı PubChem snapshot'ında 'htpb' anahtarı tamamen farklı bir bileşiğe (CID 53298156, C21H17ClN4O, 'N-(3-chloro-4-methoxyphenyl)-4-(pyridin-3-ylmethyl)phthalazin-1-amine' — bir ilaç molekülü, MW 376.8) işaret ediyor; 'rp1' hekzadekan (C16H34, MW 226.44) olarak kaydedilmiş. (b) propellant_database.py ile merkezi propellants_db.py çelişiyor: KNSU yoğunluğu 1840 vs 1889, APCP 1800 vs 1810, KNDX alev sıcaklığı 3000 K vs 1710 K, KNDX a/n 0.008/0.45 vs merkezi rejim fiti 0.000788/0.688.

**Kullanıcı etkisi:** /api/get-propellant-properties HTPB için MW='376.8' (bir ilaç molekülünün ağırlığı), APCP için MW='652.4' döndürüyor ve hepsini source='CoolProp' etiketiyle veriyor. Sıvı sayfası bu ucun MW alanını 'Real-time Data / MW: 376.8 g/mol' olarak ekrana basıyor. KNDX için combustion_temp=3000 K (gerçek/merkezi değer 1710 K, %75 hata) ve specific_impulse=130 s dönüyor — bunlar sabit `_estimate_isp` tahminleri.

**Kanıt:** offline_snapshot.json entries →
  "pubchem:htpb": {"data": {"cid": 53298156, "formula": "C21H17ClN4O", "iupac_name": "N-(3-chloro-4-methoxyphenyl)-4-(pyridin-3-ylmethyl)phthalazin-1-amine", "molecular_weight": "376.8"}}
  "pubchem:rp1": {"data": {"cid": 11006, "formula": "C16H34", "iupac_name": "hexadecane", "molecular_weight": "226.44"}}
Canlı test:
  hybrid_fuel/htpb → source='CoolProp' MW='376.8'
  solid_propellant/apcp → MW='652.4' combustion_temp=3000 (merkezi: 3614.8)
  solid_propellant/kndx → density=1800 (merkezi 1850) burn_rate_a=0.008 n=0.45 combustion_temp=3000 (merkezi 1710) specific_impulse=130
Çapraz tablo taraması:
  knsu   propellant_database rho=1840  || propellants_db rho=1889
  apcp   propellant_database rho=1800  || propellants_db rho=1810
  kndx   propellant_database a=0.008 n=0.45 || propellants_db a=0.000788 n=0.688
Not: propellants_db.py docstring'i propellant_database'in a-n'lerinin 'KULLANILMAZ' olduğunu söylüyor — ama /api/get-propellant-properties merge'ünde (app.py:3036-3046) yine de dışarı sızıyorlar.

**Önerilen çözüm:** 1) offline_snapshot.json'daki pubchem:htpb / pubchem:rp1 / pubchem:apcp kayıtlarını sil (isim-tabanlı PubChem araması polimer/karışım için anlamsız); bu maddelerin MW'sini propellants_db/chemical_database'den ver. 2) /api/get-propellant-properties'in propellant_database.py merge'ünü kes; katı yakıtlar için tek doğruluk kaynağı propellants_db + burn_rate_db olsun (propellants_db docstring'inin zaten söz verdiği davranış). 3) propellant_database.py'deki birim-etiketsiz a-n çiftlerini ve çelişen yoğunlukları kaldır veya modülü emekliye ayır.

### hrma/templates/solid.html:435 + hrma/data/propellants_db.py (validated alanı) + solid.html:1872-1883 (tablo render)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** Katalog paneli 'Pick a propellant row to load its validated properties into the form below' diyor. Oysa 12 kayıttan 10'unda `validated: False`. Kayıt şemasındaki `validated`, `c_star_basis`, `notes` ve `burn_rate_ref` alanları /api/propellants ile istemciye gidiyor ama tablo yalnız name/oxidizer/fuel/density/a/n/c*/Tc/source sütunlarını basıyor — 'typical, indicative only' uyarısını taşıyan burn_rate_ref ve notes hiç gösterilmiyor.

**Kullanıcı etkisi:** Kullanıcı 'Blue Thunder' veya 'PBAN/AP/Al' satırına tıklayıp yanma hızı katsayılarını forma yüklüyor ve 'validated' kelimesine güveniyor. Gerçekte bu a/n değerleri jenerik literatür bandı; kaydın kendi notes'u 'Typical values, NOT a manufacturer specification' diyor ama bu metin ekrana hiç gelmiyor. a katsayısı tabloda 7 ondalıkla gösterilerek ayrıca sahte kesinlik üretiyor.

**Kanıt:** propellants_db.py validated bayrakları:
  apcp=False, htpb_ap_al=False, apcp_nonaluminized=False, pban_ap_al=False, blue_thunder=False,
  kndx=True, knsb=True, knsu=False, sugar=False, kner=False, double_base=False, black_powder=False
solid.html:435 → 'Pick a propellant row to load its validated properties into the form below.'
solid.html:1872-1883 render'da yalnız 9 sütun; p.validated / p.notes / p.burn_rate_ref hiç kullanılmıyor.
propellants_db.py:43-46 docstring: "'validated: False' olan bir yakıtla yapılan yanma hızı hesabı tasarım kararına temel alınmamalıdır; kullanıcıya bu ayrım UI'da gösterilebilsin diye alan kayıt şemasının parçasıdır." — alan var, gösterim yok.

**Önerilen çözüm:** 1) 'validated properties' ifadesini 'catalogue properties' olarak düzelt. 2) Tabloya bir 'Burn-rate law' sütunu ekle: validated=true → 'Validated (Nakka regime fit)', false → 'Typical / indicative'. 3) Seçilen satırın notes + burn_rate_ref metnini form altında göster. 4) validated=false bir yakıtla hesap yapıldığında sonuç warnings listesine bir uyarı ekle.


---

## Minor

### hrma/engines/liquid_rocket_engine.py:1030 ve 1100-1102 (calculate_injector_design)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** `weber_number` çıktısı, hesaplanan bir Weber sayısı değil; damlacık çapını türetmek için KULLANILAN girdi sabiti (target_weber = 12) aynen geri raporlanıyor. Ayrıca `combustion_efficiency` enjektör tipine göre sabit (impinging 0.98, coaxial 0.96, showerhead 0.99, diğer 0.95) ve motorun gerçek Isp zincirine hiç uygulanmıyor. surface_tension = 0.02 N/m de yakıt/oksitleyiciden bağımsız sabit.

**Kullanıcı etkisi:** Sonuç JSON'unda injector_design.weber_number = 12 ve combustion_efficiency = 0.98 duruyor; kullanıcı (JSON/Ask-AI çıktısı üzerinden veya ileride bir panele bağlandığında) atomizasyonun Weber sayısının hesaplandığını sanıyor. Enjektör tipini değiştirdiğinde 'combustion efficiency' değişiyor ama Isp hiç değişmiyor — etki yanılsaması. Ekranda doğrudan render edilmediği için etkisi sınırlı, bu yüzden minor.

**Kanıt:** Kod: `target_weber = 12` ... `droplet_diameter = target_weber * surface_tension / (rho_gas * v_relative**2)` ... çıktı sözlüğünde `'weber_number': target_weber`.
Sayısal kanıt (/calculate_liquid, 10 kN/Pc=100/MR=2.5):
  injector_type='impinging' -> weber_number = 12, combustion_efficiency = 0.98
  injector_type='pintle'    -> weber_number = 12, combustion_efficiency = 0.95
  Her iki koşuda isp_sea_level ve isp_vacuum bire bir aynı (combustion_efficiency performansa uygulanmıyor).
Ayrıca `surface_tension = 0.02  # N/m typical for cryogenics` — RP-1 (~0.023) ile LOX (~0.013) ayrımı yok.

**Önerilen çözüm:** weber_number alanını kaldır veya gerçek We = ρ_gas·v_rel²·D/σ olarak (hesaplanan damlacık çapıyla) geri hesapla — o zaman tanım gereği 12 çıkar ama en azından tutarlı olur; daha iyisi engines/injector_design.py'nin SMD/atomization bloğundan gelen değeri kullan (o modül zaten Elkotb/Lefebvre ile gerçek SMD üretiyor). surface_tension'ı yakıt veritabanından al. combustion_efficiency ya c* zincirine uygulansın ya da 'nominal for this element type' etiketi alsın.

### hrma/engines/solid_rocket_engine.py:1255-1278 (_calculate_flight_simulation), 2026-2051 (_calculate_environmental_effects), 2097-2119 (_calculate_quality_analysis), 2120-2143 (_calculate_advanced_performance), 2245-2259 (_estimate_apogee/_estimate_max_velocity/_estimate_max_acceleration/_estimate_flight_time)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Dört koca blok tamamen sabit sayı: apogee 3500 m, max_velocity 450 m/s, max_acceleration 8.5 g, flight_time 45 s, thrust_to_weight_initial 4.2, payload_capacity 0.5 kg, mission_success_probability 0.92, combustion_efficiency 94.5%, c_star_efficiency 96.2%, optimal_expansion_ratio 25, propellant_mass_fraction 0.75, cold/hot temperature performans yüzdeleri, dimensional_accuracy 99.5%, failure_modes olasılıkları... Hepsi calculate_performance()'ın döndürdüğü sözlükte (satır 2703-2707) yer alıyor. Ayrıca `_calculate_flight_simulation` içinde hesaplanan `thrust_profile = np.linspace(P_c*0.8, P_c*1.2, 100)` diye kullanılmayan bir sahte dizi var.

**Kullanıcı etkisi:** Şu anda solid.html bu blokları RENDER ETMİYOR — kullanıcı ekranda görmüyor. Ancak /calculate_solid HTTP yanıtında aynen dönüyorlar, yani JSON'u indiren/inceleyen veya ileride bir panele bağlayan herkes bunları hesaplanmış sanır. 'apogee_altitude_m: 3500' ve 'mission_success_probability: 0.92' gibi değerler özellikle tehlikeli. Ekranda görünmediği için minor.

**Kanıt:** Kod: `def _estimate_apogee(self): return 3500  # m, typical for this motor class` ; `def _estimate_max_velocity(self): return 450` ; `def _estimate_max_acceleration(self): return 8.5` ; `def _estimate_flight_time(self): return 45`.
Sayısal kanıt: A (D=100/L=500/core=30/Pc=40) ve B (D=200/L=900/core=60/Pc=90) koşularında bire bir aynı:
  flight.apogee_m 3500/3500 ; flight.max_vel 450/450 ; flight.twr_init 4.2/4.2 ; flight.payload_kg 0.5/0.5
  adv.comb_eff 94.5/94.5 ; adv.opt_eps 25/25 ; adv.prop_mass_frac 0.75/0.75
  env.cold_burnrate_red 8.5/8.5 ; qual.dim_accuracy 99.5/99.5
Aynı koşularda gerçek çıktılar 5.5x değişiyor (average_thrust 6819.9 -> 37434.2 N).
UI taraması: solid.html'de flight_simulation / advanced_performance / quality_analysis / environmental_analysis anahtarlarını okuyan hiçbir render fonksiyonu yok.

**Önerilen çözüm:** Blokları sonuç sözlüğünden kaldır. Uçuş tahmini gerekiyorsa hrma/analysis/trajectory_analysis.py (gerçek 3-DOF/6-DOF çözücü) çağrılsın ve araç kütlesi/sürükleme kullanıcıdan alınsın. Kalitatif üretim/kalite metinleri 'guideline' bölümüne taşınıp sayısal alan olmaktan çıkarılsın.

### hrma/engines/solid_rocket_engine.py:2394
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Balistik denge çözümünün sonucunda `'convergence_achieved': True` koşulsuz döndürülüyor. İç sabit-nokta döngüsü (satır 2344-2352, 100 iterasyon) yakınsamasa da bayrak True kalıyor; ayrıca döngü 500 bar tavanı veya t>1000 s güvenlik sınırıyla kırıldığında da True dönüyor.

**Kullanıcı etkisi:** Doğrudan ekranda görünmüyor ama sonuç sözleşmesinde 'yakınsama sağlandı' güvencesi veriyor. Bir tüketici (test, doğrulama paneli, dış araç) bu bayrağa güvenirse yakınsamamış bir itki eğrisini geçerli sayar. Şu an render edilmediği için minor; emin olmadığım nokta ileride bir doğrulama panelinin bunu okuyup okumayacağı.

**Kanıt:** Kod (calculate_thrust_curve dönüşü): `return {'time': ..., 'thrust': ..., ..., 'throat_area': A_t, 'convergence_achieved': True}` — fonksiyon gövdesinde bu değeri False yapan hiçbir dal yok; iç döngü `for _ in range(100)` break etmeden bitse bile True.

**Önerilen çözüm:** Her zaman adımında iç döngünün break edip etmediğini izleyip toplam bayrağı (ör. `all_converged`) buradan üret; ayrıca 500 bar / t>1000 s güvenlik kesmelerinde ayrı bir 'terminated_by' alanı döndür ve design_warnings'e İngilizce uyarı ekle.

### hrma/engines/hybrid_rocket_engine.py:550-569 (_instantaneous_performance)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Anlık c*/Isp hesabı başarısız olursa `except Exception: cstar_inst = getattr(self, 'C_star', 1500.0)` ile sessizce tasarım c*'ına (ya da 1500 m/s sabitine) düşülüyor; CF yoksa `cf = 1.5` sabiti kullanılıyor. Bu değerler of_shift_performance dizilerine hiçbir işaret bırakmadan giriyor.

**Kullanıcı etkisi:** O/F kayması grafiğinde (of_shift_performance c_star/isp serileri) yanma çözücüsünün patladığı O/F aralıkları düz bir çizgi olarak görünür ve kullanıcı bunu 'performans bu aralıkta sabit' diye okur. Ayrıca c_star_time_avg / isp_time_avg bu sahte değerlerle ortalanır. Cantera bu ortamda çalıştığı için pratikte nadiren tetikleniyor — bu yüzden minor; ancak tetiklendiğinde tamamen sessiz.

**Kanıt:** Kod:
  try: ... cstar_inst = results['performance']['c_star'] ...
  except Exception: cstar_inst = getattr(self, 'C_star', 1500.0)
  cf = getattr(self, 'CF', None)
  if cf is None or not np.isfinite(cf): cf = 1.5
Dönen tuple'da veya _compile_results'taki 'of_shift_performance' sözlüğünde (satır 1042-1051) hiçbir 'fallback' / 'source' bayrağı yok.

**Önerilen çözüm:** Fallback'e düşülen noktaları bir maske dizisinde işaretle ve of_shift_performance'a `'fallback_mask'` + `'note'` alanı ekle; UI bu noktaları kesikli çizgi/gri bant olarak göstersin. Zaman ortalamaları hesaplanırken fallback noktaları dışlansın veya not düşülsün.

### hrma/engines/combustion_analysis.py:733-841 (_fallback_equilibrium_composition)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Cantera yoksa/hata verirse denge bileşimi sabit tablodan geliyor: oda için CO2 0.22, CO 0.08, H2O 0.12, H2 0.02, N2 0.54, OH 0.015... Bu kesirler yakıttan, oksitleyiciden ve O/F'den TAMAMEN bağımsız (yalnız Al varsa alümina ekleniyor). gamma da sıcaklığın doğrusal fonksiyonundan (1.33 - 4e-5·T) tahmin ediliyor.

**Kullanıcı etkisi:** Cantera'nın kurulu olmadığı bir makinede kullanıcı 'Mass Fractions' / yanma ürünleri tablosunu görür ve bunu kendi yakıt/oksitleyici çifti için hesaplanmış sanır; N2O/HTPB ile LOX/parafin aynı bileşimi verir. Bu paketlemede Cantera var (cantera_available=True doğrulandı), yani şu an tetiklenmiyor — bu yüzden minor. Sözlükte `'source': 'empirical_fallback'` işareti VAR ama hiçbir UI/rapor bunu okumuyor, yani kullanıcıya etiket ulaşmıyor.

**Kanıt:** Kod: sabit `composition` sözlükleri (station == 'chamber'/'throat'/'exit' için) ve satır 840 `'source': 'empirical_fallback'`.
Doğrulama: `grep -rn "empirical_fallback" --include=*.py --include=*.js --include=*.html .` -> yalnız combustion_analysis.py:840 (tek eşleşme). Yani işaret hiçbir tüketici tarafından okunmuyor.
Ortam kontrolü: `CombustionAnalyzer().cantera_available` -> True (bu makinede fallback devrede değil).

**Önerilen çözüm:** `source` alanını analyze_combustion çıktısının üst seviyesine taşı (ör. `results['solver'] = 'cantera' | 'empirical_fallback'`) ve UI'da yanma sonuçlarının üstünde görünür bir uyarı bandı göster ('Chemical equilibrium solver unavailable — composition is an empirical approximation'). Ayrıca bu durumda c*/Isp gibi türev sayılar da 'approximate' etiketiyle işaretlensin.

### hrma/utils/optimum_of_ratio.py:1-4 (modül docstring), 49-90 (find_optimum_hybrid), 92-126 (find_optimum_liquid), 128-197 (_calculate_isp_hybrid/_calculate_isp_liquid)
*Kapsam: Motor çekirdekleri*

**Uydurma olan:** Modül başlığı 'Uses NASA CEA data and real-time calculations' diyor; gerçekte hiçbir CEA/denge hesabı yok. Isp değerleri tablodan alınan tepe değere (peak_vac_isp) uydurma bir Gauss çanı uygulanarak üretiliyor: isp = base_isp · exp(-2·((of-of_opt)/of_opt)²) · (Pc/20)^0.05. find_optimum_hybrid/find_optimum_liquid bu diziden 'performance_curve' ve 'max_isp' döndürüyor.

**Kullanıcı etkisi:** Şu anda kullanıcı etkisi YOK: /api/optimum-of endpoint'i (app.py:3080-3131) artık gerçek CombustionAnalyzer taramasını kullanıyor ve bu iki fonksiyon hiçbir yerden çağrılmıyor (yalnız get_recommendation kullanılıyor). Yani ölü kod. Ancak modül docstring'i yanıltıcı ve fonksiyonlar hâlâ dışa açık — bir sonraki değişiklikte yanlışlıkla bağlanabilir. Bu yüzden minor.

**Kanıt:** Kod: `_calculate_isp_hybrid`: `efficiency = np.exp(-2*deviation**2)` ; `isp = base_isp * efficiency * pressure_factor` (base_isp = self.peak_vac_isp[key], elle yazılmış tablo).
Çağrı taraması: `grep -rn "find_optimum_hybrid\|find_optimum_liquid" --include=*.py --include=*.js --include=*.html .` -> yalnız optimum_of_ratio.py'nin kendi tanımları. app.py:38'de yalnız `of_optimizer` import ediliyor ve sadece satır 3122'de `get_recommendation` çağrılıyor.
Docstring: satır 1-4 `"""Optimum O/F Ratio Finder for all motor types / Uses NASA CEA data and real-time calculations"""`

**Önerilen çözüm:** find_optimum_hybrid / find_optimum_liquid / _calculate_isp_* fonksiyonlarını sil (ölü kod). Modül yalnız get_recommendation için kalacaksa docstring'i düzelt: 'Literature reference O/F table (Sutton & Biblarz, NASA CEA typical values) — lookup only, no thermochemistry'. Ayrıca get_recommendation'ın döndürdüğü tablo değeri ile CombustionAnalyzer'ın hesapladığı optimum aynı ekranda gösteriliyorsa hangisinin referans hangisinin hesap olduğu etiketlensin.

### hrma/visualization/visualization.py:1926 (create_3d_motor_visualization)
*Kapsam: Analiz modülleri*

**Uydurma olan:** 3D motor görselleştirmesinde lüle boyu `nozzle_length = 100  # mm` olarak sabit; motor sonucundaki gerçek kontur boyu (nozzle_contour.total_length) kullanılmıyor. Boğaz konumu da bu sabitin %30'una yerleştiriliyor.

**Kullanıcı etkisi:** Kullanıcı /calculate sonrası 3D motor görselini kendi geometrisinin ölçekli bir temsili sanıyor. Lüle boyu her motorda 100 mm çizildiği için kamara/lüle oranı yanlış görünüyor. Aynı sayfadaki 2D kesit (create_improved_motor_cross_section) gerçek konturu kullanıyor → iki görsel çelişiyor.

**Kanıt:** Kod: `nozzle_length = 100  # mm` ve `throat_pos = L/2 + nozzle_length * 0.3`.
Gerçek koşu (2000 N, konik): nozzle_contour.total_length = 72.65 mm; bell varyantında 61.72 mm. Her ikisinde de 3D görselde 100 mm çiziliyor.

**Önerilen çözüm:** sample_nozzle_inner_contour()'u burada da kullan (2D kesit, STEP ve STL zaten kullanıyor — bu fonksiyon tek kalan istisna).

### hrma/visualization/visualization.py:2934, 2967, 2977 (create_showerhead_with_tooltips)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Enjektör plakası çapı sabit 100 mm (`plate_diameter = 100  # mm`) ve delik halka yarıçapları sabit (25 mm, ring_num*18 mm). Plaka hover'ında "Diameter: 100 mm" ve "Material: stainless steel" yazıyor.

**Kullanıcı etkisi:** Kullanıcı plaka üstüne gelince 100 mm çap okuyor; kendi kamara çapından bağımsız. Delik deseninin plakaya göre yerleşimi de ölçekli değil, dolayısıyla desen imalat için kullanılamaz ama kullanılabilirmiş gibi görünüyor.

**Kanıt:** Çalıştırılan kanıt (mdot_ox=3.0, n_holes=30):
  PLATE HOVER: 'Injector plate | Diameter: 100 mm | Thickness: 3.0 mm | Material: stainless steel'
Aynı hover, kamara çapı ne olursa olsun değişmiyor (plate_diameter modül içinde sabit).

**Önerilen çözüm:** Plaka çapını motor kamara çapından geçir; halka yarıçaplarını plaka çapına oranla. Geçirilemiyorsa hover'dan çap ve malzeme satırlarını kaldır.

### hrma/export/cad_visualization.py:1693-1706 (_get_solid_component_details)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Katı motor bileşen detayları sabit: `'case': {'material': 'Steel 4130', 'thickness': '5mm', 'factor_of_safety': 2.5}`. Emniyet katsayısı hesaplanmış bir değer değil, yazılı bir sabit.

**Kullanıcı etkisi:** /api/detailed-cad/solid çağrıldığında component_details içinde emniyet katsayısı 2.5 dönüyor. Emniyet katsayısı bu yazılımın en kritik çıktılarından biri ve projede gerçek yapısal analiz mevcut; sabit 2.5 daha önce temizlenmiş 'sabit SF 4.0' kalıntısının aynı sınıftan bir örneği. (Katı sayfasında bu uç şu an çağrılmıyor — bu yüzden minor; ama endpoint canlı.)

**Kanıt:** Kod: `'case': {'material': 'Steel 4130', 'thickness': '5mm', 'factor_of_safety': 2.5}`. app.py:4382 `/api/detailed-cad/solid` bu sözlüğü `component_details` olarak döndürüyor. Aynı dosyadaki generate_solid_motor_cad zaten boş bir figür üretiyor (bileşen eklenmemiş, yorum: 'Implementation would be similar').

**Önerilen çözüm:** Alanı structural_analysis'ten doldur veya sözlükten çıkar. generate_solid_motor_cad gövdesi boş olduğu için endpoint'i 501 döndürmek de dürüst bir seçenek.

### hrma/app.py:412-414 (create_improved_motor_cross_section → create_motor_plot fallback) ve 405-411 (create_improved_injector_design → create_injector_plot fallback)
*Kapsam: Analiz modülleri*

**Uydurma olan:** Etiketlenmemiş sessiz fallback: yeni (gerçek kontur tabanlı) kesit çizimi herhangi bir istisna atarsa `except Exception: pass` ile eski `create_motor_plot`'a düşülüyor. Eski fonksiyon lüle boyunu `max(d_e_mm*1.5, 80)` ile uyduruyor, diverjanı `div_progress**0.7` keyfi güç yasasıyla çiziyor, plaka yarıçapını 60 mm sabitliyor (create_injector_plot:437).

**Kullanıcı etkisi:** Kullanıcı hata mesajı görmüyor; ekranda yine bir kesit çizimi beliriyor ama geometrisi çözücüden değil. Hangi çizimi gördüğünü ayırt edemez. Bu bugün düzeltilen hatalarla aynı sınıf: uydurma geometri, normal sonuç gibi.

**Kanıt:** Kod (app.py:405-414):
  try: motor_plot = create_improved_motor_cross_section(motor_results)
  except Exception: motor_plot = create_motor_plot(motor_results)
visualization.py:131 `nozzle_length = max(d_e_mm * 1.5, 80)  # Realistic nozzle length`
visualization.py:437 `plate_radius_mm = 60  # Fixed reasonable size`
Not: bu yolun pratikte ne sıklıkta tetiklendiğini ölçmedim — bu yüzden 'minor'. Ama tetiklendiğinde kullanıcıya hiçbir işaret verilmiyor.

**Önerilen çözüm:** Fallback'e düşüldüğünde figüre görünür bir uyarı anotasyonu ekle ('Fallback schematic — solver contour unavailable') ve istisnayı logla. Uzun vadede eski fonksiyonları kaldır.

### hrma/analysis/structural_analysis.py:322, 787 + hrma/static/js/panels/structural_panel.js:203, 253
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Yapısal panelde 'Burn Time (s)' girdi alanı var ve backend'e geçiyor (app.py:3366 motor_data'ya konuyor, structural_analysis.py:322'de okunuyor) ama yorulma modeli bilinçli olarak çevrim saymıyor; `design_cycles = 25` sabit. Modelin kendisi fizik açısından DOĞRU ve docstring bunu açıkça anlatıyor; sorun sunum katmanında: panel bu sayıyı 'Estimated cycles (this duty)' (bu göreve ait tahmini çevrim) etiketiyle gösteriyor ve backend'in gönderdiği `assumptions` listesini HİÇ render etmiyor.

**Kullanıcı etkisi:** Kullanıcı yanma süresini 10 s'den 40 s'ye çıkarıyor, 'Estimated cycles (this duty)' hâlâ 25 diyor ve yorulma emniyet katsayısı kılını kıpırdatmıyor. Etiket 'bu göreve ait' dediği için kullanıcı sayının kendi girdisinden türediğine inanıyor; oysa sabit bir varsayım ve o varsayımı açıklayan metin ekranda görünmüyor.

**Kanıt:** Backend yanıtı gerçekten dürüst — assumptions listesi mevcut:
    "Design cycle count = 25 (proof test + test campaign + flight; approximate, override via parameter)"
ama structural_panel.js içinde 'assumptions' kelimesi hiç geçmiyor (grep: yalnızca 'Fastener Warning' ve 'Recommendations' listBlock'ları render ediliyor).

Çalıştırılmış kanıt (/analyze_structural_safety, 145 sayısal alan):
    burn_time = 40 -> NO-EFFECT (145/145 bit-özdeş)
Karşılaştırma: chamber_temperature=3200 -> 62 alan, material=aluminum_6061 -> 80 alan değişiyor.

**Önerilen çözüm:** İki küçük düzeltme: (1) structural_panel.js:203'teki etiketi 'Estimated cycles (this duty)' yerine 'Design cycles (assumption)' yap ve yanına design_cycles varsayımını tooltip olarak koy; (2) fat.assumptions'ı U.listBlock ile render et (diğer paneller zaten bunu yapıyor). İsteğe bağlı: paneldeki 'Burn Time' alanını 'Design Cycles' alanıyla değiştir — backend zaten design_cycles parametresini destekliyor.

### hrma/app.py:3283 (/api/trajectory-analysis, create_trajectory_plots except bloğu)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** Grafik üretimi hata verirse, kullanıcıya sessizce (0,0)'dan (10,1000)'e giden iki noktalı düz bir çizgi 'Trajectory' adıyla ve 'Trajectory Analysis' başlığıyla gösteriliyor. Hiçbir uyarı, hiçbir 'fallback/hesaplanamadı' etiketi yok — normal bir sonuç gibi çiziliyor.

**Kullanıcı etkisi:** Hesap patladığında kullanıcı hata görmüyor; 10 saniyede 1000 metreye çıkan düz bir 'yörünge' görüyor ve bunu motorunun gerçek yörüngesi sanıyor. status alanı hâlâ 'success' dönüyor.

**Kanıt:** Kod:
            trajectory_plot = json.dumps({
                'data': [{'x': [0, 10], 'y': [0, 1000], 'type': 'scatter', 'name': 'Trajectory'}],
                'layout': {'title': 'Trajectory Analysis', 'xaxis': {'title': 'Time (s)'}, 'yaxis': {'title': 'Altitude (m)'}}
            })
EMİN OLMADIĞIM KISIM: normal girdilerle bu dalı tetikleyemedim (test ettiğim tüm çağrılarda 'create_trajectory_plots completed successfully' bastı), yani pratikte ne sıklıkta çalıştığını ölçemedim. Bu yüzden minor işaretledim — ama tetiklendiğinde etiketsiz uydurma veri gösterdiği kodda kesin.

**Önerilen çözüm:** Fallback figürü tamamen kaldır; grafik üretimi başarısızsa yanıtta plot_data yerine {'status':'error'} veya en azından 'plot_unavailable': true + hata mesajı dön, frontend de 'Chart could not be generated' yazsın. Sahte veri hiçbir koşulda çizilmemeli.

### hrma/app.py:3198-3199 ve 3219-3221 (/api/trajectory-analysis hibrit dalı)
*Kapsam: Görselleştirme ve rapor*

**Uydurma olan:** İstek `thrust` VEYA `burn_time` içermiyorsa kod hibrit dala düşüyor ve motoru sabit `thrust=1000, burn_time=10` ile kuruyor; sonra motor_data'ya `'burn_time': 10.0` ve `'total_impulse': engine.F * 10.0` yazıyor. Kullanıcının `total_impulse` girdisi hiç okunmuyor. Yani toplam impuls ile tanımlanmış bir motor için yörünge, sabit 1000 N / 10 s / 10 000 N.s'lik hayali bir motorla uçuruluyor. Hiçbir uyarı yok.

**Kullanıcı etkisi:** Kullanıcı 50 000 N.s ve 200 000 N.s'lik iki farklı motor için yörünge istiyor, ikisinde de aynı 1000 N / 10 s motorun yörüngesini alıyor. Yanıtın `engine_data` bloğu da thrust=1000, burn_time=10, total_impulse=10000 raporluyor — kullanıcı bunu kendi motoru sanıyor. Apoje, maksimum hız, menzil hepsi yanlış.

**Kanıt:** Çalıştırılmış kanıt (/api/trajectory-analysis, thrust ve burn_time gönderilmeden):
  total_impulse=50000,  Pc=20 -> engine_data {'thrust': 1000, 'burn_time': 10.0, 'total_impulse': 10000.0, 'isp': 228.92}
  total_impulse=200000, Pc=45 -> engine_data {'thrust': 1000, 'burn_time': 10.0, 'total_impulse': 10000.0, 'isp': 250.83}
Sadece Isp (Pc'den) değişiyor; itki ve süre sabit kalıyor, total_impulse tamamen yok sayılıyor.

EMİN OLMADIĞIM KISIM: bu dalın UI'dan ne kadar erişilebilir olduğunu kanıtlayamadım — advanced.html:884/895'te thrust ve burn_time alanları varsayılan dolu (1000 / 10) geliyor, dolayısıyla kullanıcı alanı elle boşaltmadıkça dal tetiklenmeyebilir. API'yi doğrudan kullanan veya alanı temizleyen senaryoda kesin tetikleniyor. Bu belirsizlik yüzünden minor.

**Önerilen çözüm:** Hibrit dalda sabit 1000/10 kullanmak yerine: total_impulse verilmişse HybridRocketEngine'i total_impulse ile kur (sınıf bu parametreyi zaten destekliyor — /api/transient-analysis:719'da öyle kullanılıyor) ve motor_data'ya engine.t_b / engine.F gerçek değerlerini yaz. Hiçbiri verilmemişse sessizce varsayılan uydurmak yerine 400 dön: "thrust+burn_time veya total_impulse gerekli".

### hrma/static/js/app.js:112 + hrma/templates/advanced.html:1044-1050 (contraction_ratio) ; hrma/utils/injector_design.py:528-531 + advanced.html:1312 (target_velocity)
*Kapsam: Veri, doğrulama, uçlar*

**Uydurma olan:** İki hibrit form alanı gönderildiği hâlde sonuca hiç etki etmiyor. (a) contraction_ratio: app.js gönderiyor, app.py /calculate hiç okumuyor (kaynakta geçmiyor). (b) target_velocity: InjectorDesign'a geçiyor ama _optimize_showerhead_holes'un amaç fonksiyonunda matematiksel olarak etkisiz — A_actual = N·π·(d_h/2)² ile d_h = 2√(A_required/(Nπ)) birlikte A_actual ≡ A_required verdiği için v_actual N'den bağımsız sabit; hız cezası sabit bir kaydırma olup argmin'i değiştirmiyor.

**Kullanıcı etkisi:** (a) Kullanıcı 'Contraction Ratio Ac/At' alanına 4 yazıp tooltip'te 'Higher ratios reduce oxidizer velocity in chamber, affecting mixing and combustion efficiency' okuyor; hiçbir şey değişmiyor. (b) Kullanıcı 'Target Injection Velocity 30 m/s' yerine 120 yazıyor; enjektör tasarımında hiçbir sayı değişmiyor — delik sayısı, delik çapı, çıkış hızı aynı kalıyor.

**Kanıt:** Duyarlılık testi /calculate (total_impulse yok, trajectory açık):
  YUTULAN: chamber_temperature, contraction_ratio, gamma, gas_constant, hole_diameter_max*, target_velocity, vehicle_length, wind_direction
  (*hole_diameter_max ayrı testte ETKİLİ çıktı: 2.0→0.35 iken n_holes/hole_diameter/injection_area değişti — yanlış pozitif elendi)
Enjektör alt-testi (yalnız enjektör sözlüğü karşılaştırıldı):
  target_velocity=120  → değişen alan: HİÇBİRİ
  hole_diameter_max=0.35 → L_D_ratio, hole_diameter, injection_area, n_holes, reynolds_number, weber_number değişti
  hole_diameter_min=1.0  → aynı alanlar değişti
  n_holes=40             → aynı alanlar değişti
grep -rn 'contraction_ratio' hrma/app.py → sonuç yok.
Not: chamber_temperature / gamma / gas_constant / vehicle_length / wind_direction hibrit UI'da input olarak YOK (app.js sabit varsayılan gönderiyor) — kullanıcı etkisi olmadığı için bulgu saymadım.

**Önerilen çözüm:** contraction_ratio'yu HybridRocketEngine/nozzle_design'ın contraction_area_ratio parametresine bağla (nozzle_design.py:146 zaten kabul ediyor), ya da alanı formdan kaldır. target_velocity için: ya ΔP'yi hedef hızdan çözecek bir mod ekle (v hedefi → A_required → ΔP), ya da alanı 'informational / check value' olarak etiketle ve gerçekleşen çıkış hızıyla farkı kullanıcıya göster.
