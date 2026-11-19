/*
   HRMA i18n — GRAFİK VE SUNUCU MESAJLARI SÖZLÜĞÜ  (i18n_charts.js)
   ================================================================
   Grafik metinleri sunucuda üretiliyor (visualization.py,
   advanced_results.py, regression/trajectory modülleri) ve bir kısmı da
   panel JS dosyalarında (transient_panel.js, sixdof_panel.js,
   panels/*.js) doğrudan Plotly'ye veriliyor. Toplam ~250 metin noktası
   var. Bunları 250 ayrı yerden çevirmek yerine TEK BOĞAZDAN çeviriyoruz:
   plotly_dark.js zaten Plotly.newPlot / Plotly.react çağrılarını
   sarmalıyor; oradaki translateFigure() bu dosyadaki sözlüğü kullanır.

   ANAHTAR = İNGİLİZCE METNİN KENDİSİ
   ----------------------------------
   Böylece backend metni değişmediği sürece eşleşme otomatik olur ve
   backend'e hiç dokunmadan çeviri yapılır. Anahtarlar aranmadan önce
   normalize edilir (kırpma + çoklu boşluk sadeleştirme).

   =================================================================
   DIŞARIYA AÇILAN SÖZLEŞME (diğer ajanlar bunu çağırır)
   =================================================================
     window.I18N.chartText(text)   -> String
       Grafik metnini aktif dile çevirir. Sırayla dener:
         1. Sözlükte birebir eşleşme (normalize edilmiş)
         2. Desen kuralları (Hole 12, Ring 2, hole 3, Conv. 15.0° ...)
         3. <extra></extra> / <b> / <sub> kabuklarını soyup tekrar dener
         4. <br> ile bölünmüş her parçayı ayrı ayrı çevirir
         5. "Etiket: değer" ve "Taban (birim)" kalıplarında yalnız
            etiketi/tabanı çevirir, sayıyı ve birimi olduğu gibi bırakır
       Hiçbiri tutmazsa METNİ AYNEN döndürür — asla anahtar, asla boş.
       Dil 'en' ise metin hiç değiştirilmez.

     window.I18N.serverText(msg)   -> String
       API'den gelen uyarı/hata metinlerini çevirir. Sırayla:
         1. Sözlükte birebir eşleşme
         2. Sunucu mesajı desenleri (sayı/isim içeren mesajlar için;
            yakalanan gruplar korunur, yalnız sabit kısım çevrilir)
         3. Eşleşme yoksa metin AYNEN döner
       Dizi verilirse (Array) her elemanı çevrilmiş yeni dizi döner.

     window.I18N.serverTexts(list) -> Array   (serverText'in dizi hâli)

   Her ikisi de I18N yüklenmemişse window.HRMAChartI18N üstünden de
   erişilebilir; i18n.js sonradan yüklenirse kancalar ona taşınır.

   Sözlük kalıbı i18n.js'teki çok-parçalı sözlük sözleşmesine uyar:
   anahtar/değer tek tırnakta, satır başına bir çift, EN ve TR anahtar
   kümeleri birebir aynı.
*/
(function (global) {
    'use strict';

    /* Çift yükleme koruması: şablon script etiketi + plotly_dark.js'in
       tembel yüklemesi aynı anda gerçekleşirse sözlük iki kez kaydolup
       "yinelenen anahtar" uyarısı yağdırmasın. */
    if (global.__HRMA_I18N_CHARTS) return;
    global.__HRMA_I18N_CHARTS = true;

    var DICT = {
        en: {            '(reference cooled wall)': '(reference cooled wall)',
            // V306/DİL-KATI M-KATI-17: solid_rocket_engine heat_release_rate_operating_point (Isıl sekme).
            'peak of the solved burn': 'peak of the solved burn',
            // V3.0.5 T-ÇAPA-C1: regen_cooling.RP1_COKING_BASIS (soğutma paneli rozet ipucu).
            'RP-1 coolant-side wall temperature, two tiers: 728 K is the design criterion of NASA SP-8087 (1972) sec. 3.1.1.5.4 p. 62 ("do not operate with liquid-wall temperatures above 850 F (728 K) for RP-1") - above it the design does not meet that criterion; 561 K is a deposit-risk WARNING level of this software, based on experimental findings (NASA CR-168277: deposits in copper tubes at 560-750 K) that must be validated for the application conditions; it does not by itself make the design unsafe. Staying below 728 K does NOT mean the wall stays free of deposits or is safe.': 'RP-1 coolant-side wall temperature, two tiers: 728 K is the design criterion of NASA SP-8087 (1972) sec. 3.1.1.5.4 p. 62 ("do not operate with liquid-wall temperatures above 850 F (728 K) for RP-1") - above it the design does not meet that criterion; 561 K is a deposit-risk WARNING level of this software, based on experimental findings (NASA CR-168277: deposits in copper tubes at 560-750 K) that must be validated for the application conditions; it does not by itself make the design unsafe. Staying below 728 K does NOT mean the wall stays free of deposits or is safe.',
            // V306/GÜVERTE-HATA: /analyze_structural_safety termal yol koşmadığında (Yapısal sekme).
            'No wall or gas temperature was supplied, so the thermal path did not run and no wall temperature is assumed: the material strength is read at 293.15 K, the ambient reference of the heat-transfer chain (no thermal derating).': 'No wall or gas temperature was supplied, so the thermal path did not run and no wall temperature is assumed: the material strength is read at 293.15 K, the ambient reference of the heat-transfer chain (no thermal derating).',
            'Thermal path not run: no gas or wall temperature supplied.': 'Thermal path not run: no gas or wall temperature supplied.',
            // V306/DİL-ORTAK (NR-14 ölçümü): /calculate doğrulama reddinin `error` cümlesi (hrma/app.py, 5 yer).
            'Validation failed': 'Validation failed',
            '3D Hybrid Rocket Motor Visualization': '3D Hybrid Rocket Motor Visualization',
            '3D Motor Assembly': '3D Motor Assembly',
            '3D Motor Visualization': '3D Motor Visualization',
            '3D Performance Map: Chamber Pressure vs O/F vs Isp': '3D Performance Map: Chamber Pressure vs O/F vs Isp',
            '3D Performance Surface Analysis': '3D Performance Surface Analysis',
            '3D visualization unavailable': '3D visualization unavailable',
            'ABS Plastic': 'ABS Plastic',

            'Acceleration': 'Acceleration',
            'Acceleration (g)': 'Acceleration (g)',
            'Acceleration Profile': 'Acceleration Profile',
            'Load Factor Profile': 'Load Factor Profile',
            'Load factor (g)': 'Load factor (g)',
            'Load factor (sensed)': 'Load factor (sensed)',
            'Kinematic |dv/dt|': 'Kinematic |dv/dt|',
            'Advanced Performance — 3D Surface, Mach Contour, Heat Flux': 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
            'Altitude': 'Altitude',
            'Altitude & Mach vs Time (launch → apogee)': 'Altitude & Mach vs Time (launch → apogee)',
            'Altitude (km)': 'Altitude (km)',
            'Altitude Performance Analysis': 'Altitude Performance Analysis',
            'Altitude [m]': 'Altitude [m]',
            'Altitude vs Time': 'Altitude vs Time',
            'Angle': 'Angle',
            'Angle of Attack (weathercock response)': 'Angle of Attack (weathercock response)',
            'Annular Passage': 'Annular Passage',
            /* T64 ile aynı kusur ailesi (visualization.py:3280): pintle anülüs
               boşluğu bildirilmediğinde bu iz adı üretiliyor ve sözlükte
               olmadığı için TR modda İngilizce kalıyordu. Kısa kayıt
               'Annulus gap 0.350 mm' biçimini de kurtarır. */
            'Annulus gap': 'Annulus gap',
            'Annulus gap (not reported)': 'Annulus gap (not reported)',
            'Apogee': 'Apogee',
            'Area': 'Area',
            'Atmospheric Pressure': 'Atmospheric Pressure',
            'Atmospheric Pressure vs Altitude': 'Atmospheric Pressure vs Altitude',
            'Average Values': 'Average Values',
            'Axial Heat Flux & Equilibrium Wall Temperature': 'Axial Heat Flux & Equilibrium Wall Temperature',
            'Axial Mach Number': 'Axial Mach Number',
            'Axial Position (mm)': 'Axial Position (mm)',
            'Axial position (mm)': 'Axial position (mm)',
            'Axial position x (mm)': 'Axial position x (mm)',
            'BURNOUT': 'BURNOUT',
            'Bartz axial profile unavailable — inputs missing': 'Bartz axial profile unavailable — inputs missing',
            'Basic Motor Shape': 'Basic Motor Shape',
            'Body Diameter (m)': 'Body Diameter (m)',
            'Body and swirl-chamber outlines are schematic: the solver reports slot sizes and the exit orifice area, not the housing diameters. Do not machine from this view.': 'Body and swirl-chamber outlines are schematic: the solver reports slot sizes and the exit orifice area, not the housing diameters. Do not machine from this view.',
            /* V307 DİL-SUNUCU (kalem 5) — PDF belgesinde en sık İngilizce kalan çözücü/güvenlik cümleleri (V306 DİL-SUNUCU devir_rapor_dil_tr.json, vaka >= 7). */
            'Advisory comparison only. It does not change any number HRMA publishes (the design is sized from the HRMA solver alone) and it applies no pass/fail threshold, because no sourced threshold exists for the difference between two equilibrium codes.': 'Advisory comparison only. It does not change any number HRMA publishes (the design is sized from the HRMA solver alone) and it applies no pass/fail threshold, because no sourced threshold exists for the difference between two equilibrium codes.',
            'NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) through RocketCEA': 'NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) through RocketCEA',
            'Authorized personnel behind rated barrier': 'Authorized personnel behind rated barrier',
            'Basic first aid, oxygen, decontamination': 'Basic first aid, oxygen, decontamination',
            'Essential test crew only': 'Essential test crew only',
            'No personnel inside exclusion zone from pressurization to safing': 'No personnel inside exclusion zone from pressurization to safing',
            'No trajectory range is quoted because it depends on drag and attitude, which this model does not solve.;': 'No trajectory range is quoted because it depends on drag and attitude, which this model does not solve.;',
            'Notify trauma center of potential casualties': 'Notify trauma center of potential casualties',
            'The tie-down must react the thrust with the structural safety factor.': 'The tie-down must react the thrust with the structural safety factor.',
            'confirm against the propellant SDS, current DOT Emergency Response Guidebook guidance and the responsible occupational physician / industrial-hygiene assessment before use': 'confirm against the propellant SDS, current DOT Emergency Response Guidebook guidance and the responsible occupational physician / industrial-hygiene assessment before use',
            'general emergency-planning checklist - NOT medical advice; every item must be confirmed against the propellant SDS and with the responsible occupational physician before it is relied upon': 'general emergency-planning checklist - NOT medical advice; every item must be confirmed against the propellant SDS and with the responsible occupational physician before it is relied upon',
            'general first-aid checklist - NOT medical advice; this software is not a physician': 'general first-aid checklist - NOT medical advice; this software is not a physician',
            'general hypergolic/toxic handling practice - not tied to a specific standard clause': 'general hypergolic/toxic handling practice - not tied to a specific standard clause',
            'generic cube-root mass scaling chosen for this tool - not taken from NFPA or quantity-distance tables; verify against the applicable range safety rules before use': 'generic cube-root mass scaling chosen for this tool - not taken from NFPA or quantity-distance tables; verify against the applicable range safety rules before use',
            'shell mass from chamber diameter, length and wall thickness': 'shell mass from chamber diameter, length and wall thickness',
            'Standard test-stand PPE (eye/ear protection, flame-resistant clothing)': 'Standard test-stand PPE (eye/ear protection, flame-resistant clothing)',
            'Free-air spherical TNT peak overpressure, Kinney & Graham, Explosive Shocks in Air, 2nd ed.': 'Free-air spherical TNT peak overpressure, Kinney & Graham, Explosive Shocks in Air, 2nd ed.',
            'Hopkinson-Cranz scaling Z = R / W^(1/3).': 'Hopkinson-Cranz scaling Z = R / W^(1/3).',
            'The scaled distance is solved from that correlation for the stated target overpressure, not read from a hand-written table.': 'The scaled distance is solved from that correlation for the stated target overpressure, not read from a hand-written table.',
            'no toxic inventory could be identified for this propellant, so no antidote requirement was determined. This is NOT a statement that no antidote is needed: name the propellant components and consult the propellant SDS and the responsible occupational physician.': 'no toxic inventory could be identified for this propellant, so no antidote requirement was determined. This is NOT a statement that no antidote is needed: name the propellant components and consult the propellant SDS and the responsible occupational physician.',
            'Water deluge (exposure protection)': 'Water deluge (exposure protection)',
            'Residual grain can reignite from hot surfaces; enforce cooldown': 'Residual grain can reignite from hot surfaces; enforce cooldown',
            'Decontaminate (remove clothing, flush 15 min) before transport, Transport with propellant safety data sheet, Observe gas-exposure casualties for delayed symptoms (24-48 h)': 'Decontaminate (remove clothing, flush 15 min) before transport, Transport with propellant safety data sheet, Observe gas-exposure casualties for delayed symptoms (24-48 h)',
            'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Standard test-stand PPE (eye/ear protection, flame-resistant clothing)': 'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Standard test-stand PPE (eye/ear protection, flame-resistant clothing)',
            'Activate fire suppression system': 'Activate fire suppression system',
            'Sound fire alarm': 'Sound fire alarm',
            'Evacuate upwind': 'Evacuate upwind',
            'Call fire department': 'Call fire department',
            'Prepare for secondary explosions': 'Prepare for secondary explosions',
            'Allow minimum cooling time before approach': 'Allow minimum cooling time before approach',
            'Check for unexploded ordnance': 'Check for unexploded ordnance',
            'Document all observations': 'Document all observations',
            'Secure facility and equipment': 'Secure facility and equipment',
            'Conduct post-test inspection': 'Conduct post-test inspection',
            'Decontaminate (remove clothing, flush 15 min) before transport': 'Decontaminate (remove clothing, flush 15 min) before transport',
            'Transport with propellant safety data sheet': 'Transport with propellant safety data sheet',
            'Observe gas-exposure casualties for delayed symptoms (24-48 h)': 'Observe gas-exposure casualties for delayed symptoms (24-48 h)',
            'Documented propellant-handling qualification for operators': 'Documented propellant-handling qualification for operators',
            'Test conductor certified on abort procedures': 'Test conductor certified on abort procedures',
            'Annual requalification and emergency drill participation': 'Annual requalification and emergency drill participation',
            'Don appropriate PPE': 'Don appropriate PPE',
            'Evacuate downwind areas': 'Evacuate downwind areas',
            'Activate gas detection systems': 'Activate gas detection systems',
            'Contact HAZMAT team': 'Contact HAZMAT team',
            'Establish decontamination procedures': 'Establish decontamination procedures',
            'First aid + burn kit': 'First aid + burn kit',
            'Emergency shower/eyewash': 'Emergency shower/eyewash',
            'Backup communications': 'Backup communications',
            'Fire blankets and extinguishers': 'Fire blankets and extinguishers',
            'Hot work permit system within exclusion zone': 'Hot work permit system within exclusion zone',
            'Bonding/grounding of all transfer equipment': 'Bonding/grounding of all transfer equipment',
            'Non-sparking tools for propellant handling': 'Non-sparking tools for propellant handling',
            'ATEX/intrinsically-safe electrical equipment in vapor zones': 'ATEX/intrinsically-safe electrical equipment in vapor zones',
            'No smoking / no open flame policy with physical enforcement': 'No smoking / no open flame policy with physical enforcement',
            'Maintain minimum safe distance': 'Maintain minimum safe distance',
            'Monitor pressure and temperature continuously': 'Monitor pressure and temperature continuously',
            'Have abort procedures ready': 'Have abort procedures ready',
            'Maintain constant communication': 'Maintain constant communication',
            'Document all anomalies immediately': 'Document all anomalies immediately',
            'Minimum 2-hour cooling period': 'Minimum 2-hour cooling period',
            'EOD clearance if required': 'EOD clearance if required',
            'Structural damage assessment': 'Structural damage assessment',
            'Environmental monitoring complete': 'Environmental monitoring complete',
            'Remote firing and abort system': 'Remote firing and abort system',
            'Blast barrier or berm': 'Blast barrier or berm',
            'Fixed deluge (per fire analysis)': 'Fixed deluge (per fire analysis)',
            'Area gas detection (per toxic analysis)': 'Area gas detection (per toxic analysis)',
            'Sound evacuation alarm immediately': 'Sound evacuation alarm immediately',
            'Evacuate to minimum safe distance': 'Evacuate to minimum safe distance',
            'Account for all personnel': 'Account for all personnel',
            'Contact emergency services': 'Contact emergency services',
            'Establish incident command post': 'Establish incident command post',
            'Verify all safety systems functional': 'Verify all safety systems functional',
            'Confirm personnel evacuation complete': 'Confirm personnel evacuation complete',
            'Check weather conditions acceptable': 'Check weather conditions acceptable',
            'Verify emergency response teams ready': 'Verify emergency response teams ready',
            'Test communication systems': 'Test communication systems',
            'Confirm fire suppression systems armed': 'Confirm fire suppression systems armed',
            'Evacuate to safety distance and account for personnel': 'Evacuate to safety distance and account for personnel',
            'Actuate remote deluge; do NOT approach burning propellant': 'Actuate remote deluge; do NOT approach burning propellant',
            'Notify fire brigade with propellant data sheet': 'Notify fire brigade with propellant data sheet',
            'Re-enter only after thermal + toxic clearance measurements': 'Re-enter only after thermal + toxic clearance measurements',
            'Flame-resistant clothing': 'Flame-resistant clothing',
            'Hearing and eye protection': 'Hearing and eye protection',
            'Hard hats in mechanical hazard areas': 'Hard hats in mechanical hazard areas',
            'Propellant hazards and compatibility training': 'Propellant hazards and compatibility training',
            'Emergency response and evacuation drills': 'Emergency response and evacuation drills',
            'Pressure systems safety awareness': 'Pressure systems safety awareness',
            'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn)': 'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn)',
            'Fixed remote-actuated deluge over test stand': 'Fixed remote-actuated deluge over test stand',
            'Rated portable extinguishers at all egress points': 'Rated portable extinguishers at all egress points',
            'a fragment mass distribution requires a fragmentation model (Mott/Gurney: case thickness, material ductility, explosive loading ratio), which this module does not solve. The previously published 0.1-1 / 1-10 / 10-100 g bins were a fixed constant identical for every motor, so they were withdrawn rather than presented as an analysis result.': 'a fragment mass distribution requires a fragmentation model (Mott/Gurney: case thickness, material ductility, explosive loading ratio), which this module does not solve. The previously published 0.1-1 / 1-10 / 10-100 g bins were a fixed constant identical for every motor, so they were withdrawn rather than presented as an analysis result.',
            'case mass spread uniformly over the disc of radius maximum_range_m: sigma = m_case / (pi * R^2) [kg/m^2]. This is an AREAL MASS density, NOT a fragment COUNT density: this module does not model the fragmentation spectrum, so it cannot say how many pieces land per square metre.': 'case mass spread uniformly over the disc of radius maximum_range_m: sigma = m_case / (pi * R^2) [kg/m^2]. This is an AREAL MASS density, NOT a fragment COUNT density: this module does not model the fragmentation spectrum, so it cannot say how many pieces land per square metre.',
            'generic sqrt(mass) scaling with tool-chosen coefficients - not an ERG/dispersion-model result': 'generic sqrt(mass) scaling with tool-chosen coefficients - not an ERG/dispersion-model result',
            'radiant heating can ignite adjacent structures; wide firebreak needed': 'radiant heating can ignite adjacent structures; wide firebreak needed',
            'Class A fuel grain + oxidizer-enhanced burning': 'Class A fuel grain + oxidizer-enhanced burning',
            'Class B (flammable liquid) with oxidizer-enhanced burning': 'Class B (flammable liquid) with oxidizer-enhanced burning',
            'Do not derive a verified delivered-performance claim from this Isp.': 'Do not derive a verified delivered-performance claim from this Isp.',
            'Foam (AFFF) on liquid spill; water for cooling': 'Foam (AFFF) on liquid spill; water for cooling',
            'HD 1.1 equivalent treatment recommended — mass explosion potential': 'HD 1.1 equivalent treatment recommended — mass explosion potential',
            'The delivered Isp published by this run carries NO verified two-phase (particle-lag) correction.': 'The delivered Isp published by this run carries NO verified two-phase (particle-lag) correction.',
            'The tau-choice sensitivity block is NOT published': 'The tau-choice sensitivity block is NOT published',
            'Vapor accumulation near hot components; ventilate before approach': 'Vapor accumulation near hot components; ventilate before approach',
            'Cryogenic/toxic liquid transfer procedures (as applicable)': 'Cryogenic/toxic liquid transfer procedures (as applicable)',
            'Propellant hazards and compatibility training, Emergency response and evacuation drills, Pressure systems safety awareness, Cryogenic/toxic liquid transfer procedures (as applicable)': 'Propellant hazards and compatibility training, Emergency response and evacuation drills, Pressure systems safety awareness, Cryogenic/toxic liquid transfer procedures (as applicable)',
            'Segregate oxidizer and fuel storage': 'Segregate oxidizer and fuel storage',
            'Grounded, ventilated storage area': 'Grounded, ventilated storage area',
            'No ignition sources within exclusion zone': 'No ignition sources within exclusion zone',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone': 'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone',
            'Transport per ADR/DOT dangerous goods rules': 'Transport per ADR/DOT dangerous goods rules',
            'Documented and placarded load': 'Documented and placarded load',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load': 'Transport per ADR/DOT dangerous goods rules, Documented and placarded load',
            'Condensed-phase anchor window for X_p: 0-0.4 (NASA SP-8039 (1971) Fig. 8 data window: 0-40 wt% condensed metal oxide in exhaust).': 'Condensed-phase anchor window for X_p: 0-0.4 (NASA SP-8039 (1971) Fig. 8 data window: 0-40 wt% condensed metal oxide in exhaust).',
            'This run\'s theoretical numbers ARE NASA CEA (RocketCEA): the table compares them with what HRMA delivers after its loss chain; it is not an independent check of the thermochemistry.': 'This run\'s theoretical numbers ARE NASA CEA (RocketCEA): the table compares them with what HRMA delivers after its loss chain; it is not an independent check of the thermochemistry.',
            '10 % of the propellant weight': '10 % of the propellant weight',
            'No specific antidote required — supportive care': 'No specific antidote required — supportive care',
            'local spread possible; clear combustibles within safety distance': 'local spread possible; clear combustibles within safety distance',
            'RP-1/LOX (Kerosene/Liquid Oxygen)': 'RP-1/LOX (Kerosene/Liquid Oxygen)',
            'Foam or CO2 capability for liquid fuel spill fires': 'Foam or CO2 capability for liquid fuel spill fires',
            'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn), Foam or CO2 capability for liquid fuel spill fires, Fixed remote-actuated deluge over test stand, Rated portable extinguishers at all egress points': 'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn), Foam or CO2 capability for liquid fuel spill fires, Fixed remote-actuated deluge over test stand, Rated portable extinguishers at all egress points',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S4): hibrit yakıt bloğu zarf bağıntısı (grain_sizing_rule.formula). */
            'grain outer diameter = final port diameter + 2 × residual web': 'grain outer diameter = final port diameter + 2 × residual web',
            'grain outer diameter = final port diameter × (1 + 1/sin(π/N)) + 2 × residual web': 'grain outer diameter = final port diameter × (1 + 1/sin(π/N)) + 2 × residual web',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S9): hibrit chug döngüsü tau_choice_not_measured.reason. */
            'The tau-choice sensitivity block is NOT published: this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.': 'The tau-choice sensitivity block is NOT published: this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.',
            /* V307 DİL-SUNUCU (kalem 6): güverte/analiz uçlarının adlı ret cümleleri (app.py 'cannot be produced from …'). */
            'A Monte Carlo reliability figure cannot be produced from physically impossible inputs. Nothing was sampled.': 'A Monte Carlo reliability figure cannot be produced from physically impossible inputs. Nothing was sampled.',
            'A flight solution cannot be produced from physically impossible inputs. Nothing was integrated.': 'A flight solution cannot be produced from physically impossible inputs. Nothing was integrated.',
            'A heat transfer analysis cannot be produced from a non-finite or non-positive wall thickness: the through-wall conduction resistance is undefined. No result was computed.': 'A heat transfer analysis cannot be produced from a non-finite or non-positive wall thickness: the through-wall conduction resistance is undefined. No result was computed.',
            'A heat transfer analysis cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.': 'A heat transfer analysis cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.',
            'A quasi-1D nozzle solution cannot be produced from server defaults: the regime, CF, thrust and throat state that this analysis publishes ARE these numbers. The missing fields describe the motor and its operating environment; they cannot be derived from the rest of the request and none was assumed on your behalf. Nothing was solved.': 'A quasi-1D nozzle solution cannot be produced from server defaults: the regime, CF, thrust and throat state that this analysis publishes ARE these numbers. The missing fields describe the motor and its operating environment; they cannot be derived from the rest of the request and none was assumed on your behalf. Nothing was solved.',
            'A regression curve cannot be produced from defaults. Provide the missing values: they set the time grid, the oxidiser flux and the port growth, so every point of the curve depends on them.': 'A regression curve cannot be produced from defaults. Provide the missing values: they set the time grid, the oxidiser flux and the port growth, so every point of the curve depends on them.',
            'A reliability figure cannot be produced from inputs that were not supplied. No defaults were applied and no samples were drawn; the solid motor calculation refuses the same request.': 'A reliability figure cannot be produced from inputs that were not supplied. No defaults were applied and no samples were drawn; the solid motor calculation refuses the same request.',
            'A safety assessment cannot be produced from defaults. Provide the missing values.': 'A safety assessment cannot be produced from defaults. Provide the missing values.',
            'A safety assessment cannot be produced from non-finite, non-positive or wrongly typed values. No verdict was computed.': 'A safety assessment cannot be produced from non-finite, non-positive or wrongly typed values. No verdict was computed.',
            'A structural assessment cannot be produced from defaults. Provide the missing values.': 'A structural assessment cannot be produced from defaults. Provide the missing values.',
            'A structural assessment cannot be produced from values that are not numbers. Fix the listed field; nothing was assumed.': 'A structural assessment cannot be produced from values that are not numbers. Fix the listed field; nothing was assumed.',
            'A structural verdict cannot be produced from defaults. None of the fields that define the pressure vessel was supplied, so every safety factor would describe the module\'s own placeholder motor rather than yours. No value was assumed and no analysis was attempted.': 'A structural verdict cannot be produced from defaults. None of the fields that define the pressure vessel was supplied, so every safety factor would describe the module\'s own placeholder motor rather than yours. No value was assumed and no analysis was attempted.',
            'A thermal safety verdict cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.': 'A thermal safety verdict cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.',
            'A thermal safety verdict cannot be produced from non-finite or non-positive values. No risk level was computed.': 'A thermal safety verdict cannot be produced from non-finite or non-positive values. No risk level was computed.',
            'A thermal safety verdict cannot be produced from that nozzle geometry. The wetted area integral runs over the whole contour, so a malformed contour or two inputs that disagree on the same nozzle are not resolved on your behalf. Fix the listed fields; nothing was computed.': 'A thermal safety verdict cannot be produced from that nozzle geometry. The wetted area integral runs over the whole contour, so a malformed contour or two inputs that disagree on the same nozzle are not resolved on your behalf. Fix the listed fields; nothing was computed.',
            'A thermal safety verdict cannot be produced from that supplied wall temperature pair. Fix the listed fields; nothing was computed.': 'A thermal safety verdict cannot be produced from that supplied wall temperature pair. Fix the listed fields; nothing was computed.',
            'A thermal safety verdict cannot be produced from that value. Fix the listed field; no value was assumed and no risk level was computed.': 'A thermal safety verdict cannot be produced from that value. Fix the listed field; no value was assumed and no risk level was computed.',
            'An axial wall profile cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature and the nozzle contour; they are not assumed on your behalf. Provide the missing values.': 'An axial wall profile cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature and the nozzle contour; they are not assumed on your behalf. Provide the missing values.',
            'An axial wall profile cannot be produced from non-finite, non-positive or out-of-range values. No profile was computed and no value was assumed.': 'An axial wall profile cannot be produced from non-finite, non-positive or out-of-range values. No profile was computed and no value was assumed.',
            /* V307 DİL-SUNUCU (kalem 6): güverte/analiz uçlarının adlı ret cümleleri (app.py 'cannot be produced from …'). */
            'An uncertainty analysis cannot be produced from defaults: every distribution is centred on a motor input. Provide the motor form fields in "inputs".': 'An uncertainty analysis cannot be produced from defaults: every distribution is centred on a motor input. Provide the motor form fields in "inputs".',
            /* V307 DİL-SUNUCU (kalem 5): PDF belgesinde İngilizce kalan çözücü/güvenlik cümleleri (ek tur). */
            'Class 1 explosives routing and escort requirements apply': 'Class 1 explosives routing and escort requirements apply',
            'Pressure-rated, relief-equipped transport containers': 'Pressure-rated, relief-equipped transport containers',
            'Dedicated magazine with quantity-distance siting': 'Dedicated magazine with quantity-distance siting',
            'Secondary containment and leak detection for liquid propellants': 'Secondary containment and leak detection for liquid propellants',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply, Pressure-rated, relief-equipped transport containers': 'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply, Pressure-rated, relief-equipped transport containers',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply': 'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Pressure-rated, relief-equipped transport containers': 'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Pressure-rated, relief-equipped transport containers',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting, Secondary containment and leak detection for liquid propellants': 'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting, Secondary containment and leak detection for liquid propellants',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting': 'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting',
            'Half-mask respirator with appropriate cartridge available': 'Half-mask respirator with appropriate cartridge available',
            'Chemical splash goggles and gloves': 'Chemical splash goggles and gloves',
            'Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves': 'Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves',
            'Portable detectors for entry teams': 'Portable detectors for entry teams',
            'Alarm setpoints at 50% of exposure limit': 'Alarm setpoints at 50% of exposure limit',
            'Fixed gas detection for: n2o, Portable detectors for entry teams, Alarm setpoints at 50% of exposure limit': 'Fixed gas detection for: n2o, Portable detectors for entry teams, Alarm setpoints at 50% of exposure limit',
            'Personal dosimetry/badge sampling for exposed personnel': 'Personal dosimetry/badge sampling for exposed personnel',
            'Post-operation area sampling before re-entry': 'Post-operation area sampling before re-entry',
            'Medical surveillance program for routine handlers': 'Medical surveillance program for routine handlers',
            'Personal dosimetry/badge sampling for exposed personnel, Post-operation area sampling before re-entry, Medical surveillance program for routine handlers': 'Personal dosimetry/badge sampling for exposed personnel, Post-operation area sampling before re-entry, Medical surveillance program for routine handlers',
            'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves': 'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves',
            'limited to immediate test area': 'limited to immediate test area',
            'No bias was extrapolated.': 'No bias was extrapolated.',
            'Fresh air, oxygen if hypoxic symptoms': 'Fresh air, oxygen if hypoxic symptoms',
            'HD 1.3 equivalent — mass fire / minor blast hazard': 'HD 1.3 equivalent — mass fire / minor blast hazard',
            'An unrecognised material is not a default material.': 'An unrecognised material is not a default material.',
            'HD 1.4 equivalent — minor hazard, local effects only': 'HD 1.4 equivalent — minor hazard, local effects only',
            'Worst-case full inventory release, neutral weather (F stability)': 'Worst-case full inventory release, neutral weather (F stability)',
            'Class 1.3-type solid propellant fire (self-oxidized, cannot be smothered)': 'Class 1.3-type solid propellant fire (self-oxidized, cannot be smothered)',
            'verify against the propellant SDS and current DOT Emergency Response Guidebook guidance': 'verify against the propellant SDS and current DOT Emergency Response Guidebook guidance',
            'Layer 2, the closeout, covers the channels and carries the coolant pressure as a hoop shell.': 'Layer 2, the closeout, covers the channels and carries the coolant pressure as a hoop shell.',
            'The band is reported for the coefficient in force, NOT as a validated bias for this oxidizer.': 'The band is reported for the coefficient in force, NOT as a validated bias for this oxidizer.',
            'The drawn chamber wall is the stack liner + channel depth + closeout; the governing safety factor of the stack is the smaller of the two layers.': 'The drawn chamber wall is the stack liner + channel depth + closeout; the governing safety factor of the stack is the smaller of the two layers.',
            'Controlled ignition sources only': 'Controlled ignition sources only',
            'Methane/LOX (Liquid Methane/Liquid Oxygen)': 'Methane/LOX (Liquid Methane/Liquid Oxygen)',
            'sized by the injector model': 'sized by the injector model',
            'the PBAN binder has no closed formula or enthalpy in HRMA': 'the PBAN binder has no closed formula or enthalpy in HRMA',
            'single-exponent Saint-Robert law r = a * Pc^n with the coefficients supplied for this propellant': 'single-exponent Saint-Robert law r = a * Pc^n with the coefficients supplied for this propellant',
            '14 CFR Part 420, Appendix E, Table E-5 "Energetic Liquid Explosive Equivalents" (CFR 2024 edition)': '14 CFR Part 420, Appendix E, Table E-5 "Energetic Liquid Explosive Equivalents" (CFR 2024 edition)',
            'M = 1/n (NASA RP-1311 Part I eq. 2.3a): mixture mass per mole of gas, condensed phase included in the mass': 'M = 1/n (NASA RP-1311 Part I eq. 2.3a): mixture mass per mole of gas, condensed phase included in the mass',
            'NASA CEA (Gordon & McBride, NASA RP-1311) through RocketCEA (CEA2); rocket problem, equilibrium (shifting) composition, infinite-area combustor, condensed species in equilibrium': 'NASA CEA (Gordon & McBride, NASA RP-1311) through RocketCEA (CEA2); rocket problem, equilibrium (shifting) composition, infinite-area combustor, condensed species in equilibrium',
            'Isp(vac) at the selected O/F divided by the maximum Isp of this very O/F scan (same solver chain, CEA-anchored); the selected O/F is itself one of the scan points, so the ratio cannot exceed 100%': 'Isp(vac) at the selected O/F divided by the maximum Isp of this very O/F scan (same solver chain, CEA-anchored); the selected O/F is itself one of the scan points, so the ratio cannot exceed 100%',
            'catalogue record (one NASA CEA run at the record pressure); its chamber-pressure dependence is not modelled': 'catalogue record (one NASA CEA run at the record pressure); its chamber-pressure dependence is not modelled',
            'catalogue record convention (see the record source text)': 'catalogue record convention (see the record source text)',
            '1D station march available for RP-1 regenerative cooling only; the values above come from the Bartz chamber/nozzle integration.': '1D station march available for RP-1 regenerative cooling only; the values above come from the Bartz chamber/nozzle integration.',
            'TNT = 0.35 x propellant mass (the module default; no sourced factor for this case)': 'TNT = 0.35 x propellant mass (the module default; no sourced factor for this case)',
            'number of equivalent circular combustion ports actually used by the grain model of this run. It is the value the port gate accepted: zero, negative and fractional inputs are rejected by name rather than silently rounded, and an omitted input means one port.': 'number of equivalent circular combustion ports actually used by the grain model of this run. It is the value the port gate accepted: zero, negative and fractional inputs are rejected by name rather than silently rounded, and an omitted input means one port.',
            /* V307 DİL-SUNUCU (kalem 5): PDF belgesinde İngilizce kalan çözücü/güvenlik cümleleri (ek tur). */
            'Let solid propellant burn out; cool surroundings only': 'Let solid propellant burn out; cool surroundings only',
            'Evacuate to safety distance and account for personnel, Actuate remote deluge; do NOT approach burning propellant, Notify fire brigade with propellant data sheet, Let solid propellant burn out; cool surroundings only, Re-enter only after thermal + toxic clearance measurements': 'Evacuate to safety distance and account for personnel, Actuate remote deluge; do NOT approach burning propellant, Notify fire brigade with propellant data sheet, Let solid propellant burn out; cool surroundings only, Re-enter only after thermal + toxic clearance measurements',
            'Layer 1, the liner, is the channelled hot-gas wall: its thickness (gas side to channel base) is the hot wall of the thermal chain, and it is checked for the coolant-to-gas pressure difference across the channel span between lands plus the thermal stress through its thickness.': 'Layer 1, the liner, is the channelled hot-gas wall: its thickness (gas side to channel base) is the hot wall of the thermal chain, and it is checked for the coolant-to-gas pressure difference across the channel span between lands plus the thermal stress through its thickness.',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Secondary containment and leak detection for liquid propellants': 'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Secondary containment and leak detection for liquid propellants',
            'isentropic expansion coefficient from the propellant record; the same value the thrust coefficient and expansion-ratio solutions use': 'isentropic expansion coefficient from the propellant record; the same value the thrust coefficient and expansion-ratio solutions use',
            'generic sqrt(mass) scaling with tool-chosen per-component coefficients - not an ERG/dispersion-model result': 'generic sqrt(mass) scaling with tool-chosen per-component coefficients - not an ERG/dispersion-model result',
            'The published bias body was measured on HTPB/n2o campaigns only': 'The published bias body was measured on HTPB/n2o campaigns only',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 4): structural_analysis.py YAPISAL DEĞER KAYNAKLARI defterinin gerekçe hücreleri (SRV); Türkçede makine adı yerine okunur ad. */
            'design_safety_factor_target is the design safety factor you entered (the target). earned_safety_factor is the safety factor the selected or sized thickness actually has. governing_condition names what set that thickness: "stress" - sized by the stress rule to the target, so the earned factor equals the target (times any declared allowance) and the thickness scales with the target; "minimum_thickness" - a manufacturing floor is thicker than the stress rule needs, so the earned factor is above the target and does not scale with it; "user_wall" - your thickness, verified; "standard_size" - the bolt diameter is rounded up to the next ISO 261 size. safety_factor_verdict is FAIL when the earned factor is below the target.': 'design_safety_factor_target is the design safety factor you entered (the target). earned_safety_factor is the safety factor the selected or sized thickness actually has. governing_condition names what set that thickness: "stress" - sized by the stress rule to the target, so the earned factor equals the target (times any declared allowance) and the thickness scales with the target; "minimum_thickness" - a manufacturing floor is thicker than the stress rule needs, so the earned factor is above the target and does not scale with it; "user_wall" - your thickness, verified; "standard_size" - the bolt diameter is rounded up to the next ISO 261 size. safety_factor_verdict is FAIL when the earned factor is below the target.',
            'net axial compression in the pressurised load case: max(thrust compression F/(2*pi*r*t) - internal pressure longitudinal tension p*r/(2t), 0). A value of exactly zero is the clamp, not a missing model: the pressure tension exceeds the axial compression, so this load case cannot buckle the shell and the unpressurised case governs. Both contributors are published next to this field (axial_compression_force_N, pressure_stabilizing_stress_MPa).': 'net axial compression in the pressurised load case: max(thrust compression F/(2*pi*r*t) - internal pressure longitudinal tension p*r/(2t), 0). A value of exactly zero is the clamp, not a missing model: the pressure tension exceeds the axial compression, so this load case cannot buckle the shell and the unpressurised case governs. Both contributors are published next to this field (axial_compression_force_N, pressure_stabilizing_stress_MPa).',
            '2:1 ellipsoidal head membrane, inverse of ASME VIII-1 UG-32(d)': '2:1 ellipsoidal head membrane, inverse of ASME VIII-1 UG-32(d)',
            'Both verdicts are evaluated at head_thickness_used_mm with the SAME reference strength (derated yield): flat from the Roark Table 11.2 simply-supported circular plate bending stress, dished from the inverse of ASME VIII-1 UG-32(d) for a 2:1 ellipsoidal head. head_safety_factor is the entry for recommended_type; a layer that manufactures or draws the other type must quote that type entry instead of borrowing this one.': 'Both verdicts are evaluated at head_thickness_used_mm with the SAME reference strength (derated yield): flat from the Roark Table 11.2 simply-supported circular plate bending stress, dished from the inverse of ASME VIII-1 UG-32(d) for a 2:1 ellipsoidal head. head_safety_factor is the entry for recommended_type; a layer that manufactures or draws the other type must quote that type entry instead of borrowing this one.',
            'ESTIMATE: 30% of chamber weight (engineering rule of thumb, not a geometry calculation; the nozzle material is not reflected here)': 'ESTIMATE: 30% of chamber weight (engineering rule of thumb, not a geometry calculation; the nozzle material is not reflected here)',
            'Fields the caller did not supply, for which this module applied its own documented default (see STRUCTURAL_INPUT_DEFAULTS). An empty object means every geometry/pressure input below came from the caller. A value that was supplied but is not physical is REJECTED (NonPhysicalStructuralInput), never defaulted.': 'Fields the caller did not supply, for which this module applied its own documented default (see STRUCTURAL_INPUT_DEFAULTS). An empty object means every geometry/pressure input below came from the caller. A value that was supplied but is not physical is REJECTED (NonPhysicalStructuralInput), never defaulted.',
            'Ground reference for the external-pressure load case: the ISA / U.S. Standard Atmosphere 1976 sea-level pressure, 1.01325 bar (hrma.constants.P_SEA_LEVEL_PA). It is a REFERENCE for the ground scenarios (cooling condensation, closed drain) and is NOT applied automatically; pass it as external_pressure to obtain a verdict.': 'Ground reference for the external-pressure load case: the ISA / U.S. Standard Atmosphere 1976 sea-level pressure, 1.01325 bar (hrma.constants.P_SEA_LEVEL_PA). It is a REFERENCE for the ground scenarios (cooling condensation, closed drain) and is NOT applied automatically; pass it as external_pressure to obtain a verdict.',
            'bolt spacing = pi*D_bolt_circle/n compared with the required bolt diameter; the minimum pitch factor 2.5 is a DECLARED flange practice value (wrench clearance and edge distance; Taylor Forge / ASME VIII-1 App.2 bolted-flange practice), not a calibration constant. Bolt count is chosen from the diameter rule first and only reduced when the layout does not close - the occupied circumference goes like sqrt(n), so fewer, larger bolts fit where many small ones do not. bolt_layout_ok=false means the published pattern does not meet that pitch; bolt_layout_interferes=true means the bolts overlap outright.': 'bolt spacing = pi*D_bolt_circle/n compared with the required bolt diameter; the minimum pitch factor 2.5 is a DECLARED flange practice value (wrench clearance and edge distance; Taylor Forge / ASME VIII-1 App.2 bolted-flange practice), not a calibration constant. Bolt count is chosen from the diameter rule first and only reduced when the layout does not close - the occupied circumference goes like sqrt(n), so fewer, larger bolts fit where many small ones do not. bolt_layout_ok=false means the published pattern does not meet that pitch; bolt_layout_interferes=true means the bolts overlap outright.',
            'cylindrical shell volume x material density, using the evaluated wall thickness': 'cylindrical shell volume x material density, using the evaluated wall thickness',
            'declared design assumption, not derived from throat fillet geometry': 'declared design assumption, not derived from throat fillet geometry',
            'design pressure = chamber pressure x this design pressure factor. The factor is passed in as a constant by the calling engine, it is NOT computed here and it is NOT the safety_factor entered by the user - it is a separate multiplier that compounds with it (proof/burst pressure margin over MEOP).': 'design pressure = chamber pressure x this design pressure factor. The factor is passed in as a constant by the calling engine, it is NOT computed here and it is NOT the safety_factor entered by the user - it is a separate multiplier that compounds with it (proof/burst pressure margin over MEOP).',
            'evaluated against the wall HRMA sized in the motor result (not a wall you supplied), at this analysis\'s design pressure': 'evaluated against the wall HRMA sized in the motor result (not a wall you supplied), at this analysis\'s design pressure',
            'head_thickness_used_mm is the thickness at which THIS block evaluated the head stress and safety factor; it is NOT a statement about which head thickness goes to manufacturing. The legacy field name says "used"; read it as "evaluated". In size mode it is the sized thickness of recommended_type, in verify mode it is the actual thickness supplied by the caller and then it equals neither sizing output; head_thickness_used_type names which of the two it is ("flat", "dished" or "user_supplied"). A layer that draws, exports or manufactures a specific head type must take that type thickness by name through head_thickness_field_by_type[type] - the CAD/STEP export models a FLAT head and therefore takes flat_head_thickness, which is a different quantity from head_thickness_used_mm whenever recommended_type is "dished" - and must quote head_safety_factor_by_type[type] for the verdict of that same part.': 'head_thickness_used_mm is the thickness at which THIS block evaluated the head stress and safety factor; it is NOT a statement about which head thickness goes to manufacturing. The legacy field name says "used"; read it as "evaluated". In size mode it is the sized thickness of recommended_type, in verify mode it is the actual thickness supplied by the caller and then it equals neither sizing output; head_thickness_used_type names which of the two it is ("flat", "dished" or "user_supplied"). A layer that draws, exports or manufactures a specific head type must take that type thickness by name through head_thickness_field_by_type[type] - the CAD/STEP export models a FLAT head and therefore takes flat_head_thickness, which is a different quantity from head_thickness_used_mm whenever recommended_type is "dished" - and must quote head_safety_factor_by_type[type] for the verdict of that same part.',
            'lowest of all computed safety factors, including the sections HRMA sized itself; it is NOT the number the verdict is drawn from (see verdict_safety_factor)': 'lowest of all computed safety factors, including the sections HRMA sized itself; it is NOT the number the verdict is drawn from (see verdict_safety_factor)',
            'manufacturing allowance constant (structural_analysis.py MANUFACTURING_ALLOWANCE_FACTOR): recommended thickness = minimum thickness x this factor. It is NOT computed from this design and it is NOT a safety factor - it is stock tolerance, machining and corrosion allowance taken from general tube/plate manufacturing practice (ASME BPVC VIII-1 UG-25 corrosion-allowance pattern).': 'manufacturing allowance constant (structural_analysis.py MANUFACTURING_ALLOWANCE_FACTOR): recommended thickness = minimum thickness x this factor. It is NOT computed from this design and it is NOT a safety factor - it is stock tolerance, machining and corrosion allowance taken from general tube/plate manufacturing practice (ASME BPVC VIII-1 UG-25 corrosion-allowance pattern).',
            'materials_db recommended design factor for this material - NOT the design safety factor entered by the user': 'materials_db recommended design factor for this material - NOT the design safety factor entered by the user',
            'not evaluated: no external-pressure load case was declared. Pass external_pressure (applied ambient pressure, Pa) and internal_pressure_min (lowest internal pressure in that case, Pa) to obtain a verdict. This module does not assume a load case; the ground reference pressure is published as ground_reference_external_pressure_bar for the caller to use deliberately.': 'not evaluated: no external-pressure load case was declared. Pass external_pressure (applied ambient pressure, Pa) and internal_pressure_min (lowest internal pressure in that case, Pa) to obtain a verdict. This module does not assume a load case; the ground reference pressure is published as ground_reference_external_pressure_bar for the caller to use deliberately.',
            'per-station map, SHARP definition: true only when the station was sized by HRMA AND the published factor reads the design target back (factor >= target). A sized station whose factor fell BELOW the target is a measurement (a load the sizing did not cover pulled it down) and is NOT marked tautological. The looser question - "did HRMA pick this wall?" - is published as safety_factor_station_sized_by_hrma and is what the verdict machinery uses (fail-closed).': 'per-station map, SHARP definition: true only when the station was sized by HRMA AND the published factor reads the design target back (factor >= target). A sized station whose factor fell BELOW the target is a measurement (a load the sizing did not cover pulled it down) and is NOT marked tautological. The looser question - "did HRMA pick this wall?" - is published as safety_factor_station_sized_by_hrma and is what the verdict machinery uses (fail-closed).',
            'predicted life for the computed stress state (Goodman + Basquin); the design target is design_cycles': 'predicted life for the computed stress state (Goodman + Basquin); the design target is design_cycles',
            'preload physics NOT evaluated: the clamped grip length of the closure joint was not supplied (motor field \'closure_grip_length_m\'). Without it the bolt/member stiffness ratio C is unknown, so joint separation — which is the governing criterion for a preloaded flange — cannot be checked. bolt_safety_factor below is the DESIGN INPUT read back, not a verified capacity.': 'preload physics NOT evaluated: the clamped grip length of the closure joint was not supplied (motor field \'closure_grip_length_m\'). Without it the bolt/member stiffness ratio C is unknown, so joint separation — which is the governing criterion for a preloaded flange — cannot be checked. bolt_safety_factor below is the DESIGN INPUT read back, not a verified capacity.',
            'static tensile sizing only: F_design = SF * P/n over thread stress area, allowable = ISO 898-1 proof stress S_p; preload and separation are NOT modelled here': 'static tensile sizing only: F_design = SF * P/n over thread stress area, allowable = ISO 898-1 proof stress S_p; preload and separation are NOT modelled here',
            'strength retention interpolated from the material derating_curve (MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 pattern)': 'strength retention interpolated from the material derating_curve (MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 pattern)',
            'stress ratio R = sigma_min/sigma_max is fixed at zero BY THE CYCLE MODEL, not computed: every firing is treated as one full 0 -> P -> 0 pressure cycle, so the minimum stress is zero. If your duty cycle keeps the chamber pressurised between firings (or preloads it), R is not zero and this Goodman evaluation does not apply.': 'stress ratio R = sigma_min/sigma_max is fixed at zero BY THE CYCLE MODEL, not computed: every firing is treated as one full 0 -> P -> 0 pressure cycle, so the minimum stress is zero. If your duty cycle keeps the chamber pressurised between firings (or preloads it), R is not zero and this Goodman evaluation does not apply.',
            'the stress rule solves the bolt diameter at the target (F_design = SF * P/n over the thread stress area, ISO 898-1 proof stress); the product takes the next ISO 261 coarse-thread size, so the earned factor of the selected bolt is at or above the target unless no standard size is large enough.': 'the stress rule solves the bolt diameter at the target (F_design = SF * P/n over the thread stress area, ISO 898-1 proof stress); the product takes the next ISO 261 coarse-thread size, so the earned factor of the selected bolt is at or above the target unless no standard size is large enough.',
            'measured wall temperature supplied by the caller (wall_temperature_hot); the service-limit check uses it directly': 'measured wall temperature supplied by the caller (wall_temperature_hot); the service-limit check uses it directly',
            'No gas temperature (chamber_temperature) and no wall temperatures were supplied, so the thermal path did not run. The values previously reported here were the ambient default that marks the thermal model as OFF, not computed wall temperatures. Safety factors above are pressure-only.': 'No gas temperature (chamber_temperature) and no wall temperatures were supplied, so the thermal path did not run. The values previously reported here were the ambient default that marks the thermal model as OFF, not computed wall temperatures. Safety factors above are pressure-only.',
            'no chamber temperature was supplied: the thermal axis is inactive and the ambient temperature is echoed': 'no chamber temperature was supplied: the thermal axis is inactive and the ambient temperature is echoed',
            'the motor result\'s own case temperature (hybrid chamber zone protection: grain protection under the grain, insulation liner in the open zones), adopted because the chamber pressure, diameter and wall match the motor result; the gas-temperature estimate is not used, so this tab evaluates the wall at the same temperature the motor sized it at.': 'the motor result\'s own case temperature (hybrid chamber zone protection: grain protection under the grain, insulation liner in the open zones), adopted because the chamber pressure, diameter and wall match the motor result; the gas-temperature estimate is not used, so this tab evaluates the wall at the same temperature the motor sized it at.',
            'two-layer regenerative wall (wall_model): safety_factor is the DESIGN TARGET read back (safety_factor_source). hoop_safety_factor is computed on the CLOSEOUT, the layer that carries the coolant pressure: derated yield at the closeout temperature divided by its hoop stress (closeout thickness chosen by HRMA, so it is not a verification of a shell you built). The liner is checked separately (wall_layers); the stack factor is wall_stack_safety_factor.': 'two-layer regenerative wall (wall_model): safety_factor is the DESIGN TARGET read back (safety_factor_source). hoop_safety_factor is computed on the CLOSEOUT, the layer that carries the coolant pressure: derated yield at the closeout temperature divided by its hoop stress (closeout thickness chosen by HRMA, so it is not a verification of a shell you built). The liner is checked separately (wall_layers); the stack factor is wall_stack_safety_factor.',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 6, KILAVUZ ÜB-5): sıvı formu Oda Malzemesi künyesi (materials_db source; liquid.html bunu SRV olmadan basıyor, DİL-EKRAN-2). */
            'AK Steel 304/304L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 304 (E, k, cp, alpha, melting range 1400-1450 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).': 'AK Steel 304/304L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 304 (E, k, cp, alpha, melting range 1400-1450 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).',
            'AK Steel 316/316L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 316 (E, k, cp, alpha, melting range 1371-1399 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).': 'AK Steel 316/316L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 316 (E, k, cp, alpha, melting range 1371-1399 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).',
            'Mechanical + derating: Special Metals INCONEL alloy 718 datasheet (prior structural table). Thermal: Special Metals 718 datasheet (k=11.4 W/m-K RT, cp=435 J/kg-K, melting range 1260-1336 C).': 'Mechanical + derating: Special Metals INCONEL alloy 718 datasheet (prior structural table). Thermal: Special Metals 718 datasheet (k=11.4 W/m-K RT, cp=435 J/kg-K, melting range 1260-1336 C).',
            'Special Metals INCONEL alloy 625 datasheet (annealed: Fty ~490 MPa, Ftu ~930 MPa, E 208 GPa, rho 8440, k 9.8 W/m-K RT, cp 410 J/kg-K, melting 1290-1350 C); fatigue ~0.4*UTS approximate; derating from datasheet elevated-temperature yield (approximate). k/cp curves: Special Metals 625 datasheet, approximate.': 'Special Metals INCONEL alloy 625 datasheet (annealed: Fty ~490 MPa, Ftu ~930 MPa, E 208 GPa, rho 8440, k 9.8 W/m-K RT, cp 410 J/kg-K, melting 1290-1350 C); fatigue ~0.4*UTS approximate; derating from datasheet elevated-temperature yield (approximate). k/cp curves: Special Metals 625 datasheet, approximate.',
            'Mechanical + derating: MMPDS 6061-T6 (prior structural table). Thermal: ASM Metals Handbook Vol. 2 / MatWeb 6061-T6 (k=167 W/m-K, cp=896 J/kg-K, solidus 582 C); emissivity = sooted/oxidized service surface assumption (conservative for gas-side radiation absorption).': 'Mechanical + derating: MMPDS 6061-T6 (prior structural table). Thermal: ASM Metals Handbook Vol. 2 / MatWeb 6061-T6 (k=167 W/m-K, cp=896 J/kg-K, solidus 582 C); emissivity = sooted/oxidized service surface assumption (conservative for gas-side radiation absorption).',
            'Mechanical: ASM Metals Handbook Vol. 2, C10200 annealed (yield ~69 MPa, UTS ~220 MPa, E 117 GPa, fatigue 62 MPa @1e8); derating curve approximate from ASM elevated-temperature copper data. Thermal: prior heat_transfer_analysis table (pure Cu handbook values).': 'Mechanical: ASM Metals Handbook Vol. 2, C10200 annealed (yield ~69 MPa, UTS ~220 MPa, E 117 GPa, fatigue 62 MPa @1e8); derating curve approximate from ASM elevated-temperature copper data. Thermal: prior heat_transfer_analysis table (pure Cu handbook values).',
            'KME Elbrodur G / Luvata CuCr1Zr (C18150) datasheets: aged Rp0.2 >= 310 MPa, Rm >= 400 MPa, E ~128 GPa, k ~320 W/m-K, softening ~475-500 C; fatigue and derating approximate from ITER CuCrZr materials assessments. Regeneratively cooled chamber liner alloy (NASA GRCop analog class). k/cp curves: ITER material property handbook CuCr1Zr (aged), approximate.': 'KME Elbrodur G / Luvata CuCr1Zr (C18150) datasheets: aged Rp0.2 >= 310 MPa, Rm >= 400 MPa, E ~128 GPa, k ~320 W/m-K, softening ~475-500 C; fatigue and derating approximate from ITER CuCrZr materials assessments. Regeneratively cooled chamber liner alloy (NASA GRCop analog class). k/cp curves: ITER material property handbook CuCr1Zr (aged), approximate.',
            'Mechanical: AZoM/MatWeb AISI 4130 normalized; derating MMPDS/MIL-HDBK-5 Fig. 2.3.1.1.1; alpha ASM Metals Handbook. Thermal: MatWeb AISI 4130 (k, cp, solidus).': 'Mechanical: AZoM/MatWeb AISI 4130 normalized; derating MMPDS/MIL-HDBK-5 Fig. 2.3.1.1.1; alpha ASM Metals Handbook. Thermal: MatWeb AISI 4130 (k, cp, solidus).',
            /* V307 DİL-SUNUCU-2 (kalem 2): PDF belgesinde İngilizce kalan çözücü cümleleri, bugünkü kodda birebir duranlar (hibrit/katı/sıvı künyeleri). */
            'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns. DELIVERED quantities come from the N2O self-pressurised tank blowdown solution of this run (tank_blowdown; the same curve the flight is integrated with): total_impulse = total_impulse_delivered_Ns = tank_blowdown.total_impulse_Ns. total_impulse_requested_Ns carries the design intent; constant_oxidizer_flow_budget carries the regulated-feed budget of the same design for comparison.': 'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns. DELIVERED quantities come from the N2O self-pressurised tank blowdown solution of this run (tank_blowdown; the same curve the flight is integrated with): total_impulse = total_impulse_delivered_Ns = tank_blowdown.total_impulse_Ns. total_impulse_requested_Ns carries the design intent; constant_oxidizer_flow_budget carries the regulated-feed budget of the same design for comparison.',
            'explicit declarations of physics this hybrid solver does NOT compute (roadmap A10; the pattern the liquid and solid engines already follow). Every entry was verified against the code: the named computation exists nowhere in the hybrid chain, and items already declared at their own source (rigid-throat erosion, kinetic-efficiency diagnosis, multi-port equivalent-model warning) are not duplicated here. A missing value is declared as missing, not replaced by a number.': 'explicit declarations of physics this hybrid solver does NOT compute (roadmap A10; the pattern the liquid and solid engines already follow). Every entry was verified against the code: the named computation exists nowhere in the hybrid chain, and items already declared at their own source (rigid-throat erosion, kinetic-efficiency diagnosis, multi-port equivalent-model warning) are not duplicated here. A missing value is declared as missing, not replaced by a number.',
            'ACTUAL free volume in m^3 enclosed by the fuel port plus the pre/post-combustion chambers at the design instant; this is what L*_achieved is computed from.': 'ACTUAL free volume in m^3 enclosed by the fuel port plus the pre/post-combustion chambers at the design instant; this is what L*_achieved is computed from.',
            'CF_vac x Pc x A_t integrated over the same thrust curve as the sea-level impulse (Sutton & Biblarz Eq. 3-30/3-31 with Pa = 0); this is THIS motor\'s fixed nozzle in vacuum, not a vacuum-optimised nozzle. Replaces the empirical log fit that did not see chamber pressure.': 'CF_vac x Pc x A_t integrated over the same thrust curve as the sea-level impulse (Sutton & Biblarz Eq. 3-30/3-31 with Pa = 0); this is THIS motor\'s fixed nozzle in vacuum, not a vacuum-optimised nozzle. Replaces the empirical log fit that did not see chamber pressure.',
            'DELIVERED burn-averaged specific impulse of THIS run: total_impulse_delivered_Ns / (propellant_mass_total * g0) with the BIPM standard gravity. The identity I = Isp * m * g0 closes exactly against the two fields named here, so a consumer never has to choose between two descriptions of the same burn. It is NOT the same quantity as the headline isp: that one is the design-point instant (CF * c_star / g0) and belongs to the closed design set (thrust, mdot_total, c_star, cf, isp). The two differ because the O/F of a hybrid drifts as the port regresses; isp_design_point_delta_pct reports that cost as a percentage, and of_shift.regulated carries the whole history. of_shift.regulated.isp_mass_avg_s is this same burn-averaged quantity taken over the solver trapezoid mass (propellant_mass_consumed_kg) instead of the published propellant_mass_total.': 'DELIVERED burn-averaged specific impulse of THIS run: total_impulse_delivered_Ns / (propellant_mass_total * g0) with the BIPM standard gravity. The identity I = Isp * m * g0 closes exactly against the two fields named here, so a consumer never has to choose between two descriptions of the same burn. It is NOT the same quantity as the headline isp: that one is the design-point instant (CF * c_star / g0) and belongs to the closed design set (thrust, mdot_total, c_star, cf, isp). The two differ because the O/F of a hybrid drifts as the port regresses; isp_design_point_delta_pct reports that cost as a percentage, and of_shift.regulated carries the whole history. of_shift.regulated.isp_mass_avg_s is this same burn-averaged quantity taken over the solver trapezoid mass (propellant_mass_consumed_kg) instead of the published propellant_mass_total.',
            'DESIGN TARGET chamber volume in m^3: requested L* times throat area (L* x A_t). NOT the free volume of the built chamber and NOT the gross cylinder swept by the case.': 'DESIGN TARGET chamber volume in m^3: requested L* times throat area (L* x A_t). NOT the free volume of the built chamber and NOT the gross cylinder swept by the case.',
            'burn_time is the burn the motor actually sustains. The steady hybrid design never clips the burn: the grain outer diameter is sized to the final ports, and a chamber diameter too small for the requested burn is rejected by name (grain_envelope_too_small_for_final_ports) instead of publishing a shorter burn. burn_time therefore equals burn_time_requested_s and burn_time_clipped is false in every published design.': 'burn_time is the burn the motor actually sustains. The steady hybrid design never clips the burn: the grain outer diameter is sized to the final ports, and a chamber diameter too small for the requested burn is rejected by name (grain_envelope_too_small_for_final_ports) instead of publishing a shorter burn. burn_time therefore equals burn_time_requested_s and burn_time_clipped is false in every published design.',
            'oxidizer_mass is the LOADED mass: the tank is sized for the REQUESTED burn time (m_ox = mdot_ox x burn_time_requested_s) because the tank is hardware and does not shrink when the grain runs out early. oxidizer_mass_consumed_kg is what the burn actually uses and oxidizer_mass_residual_kg is the unburnt remainder that flies as dead weight. The mass budget must use the loaded value, the performance budget the consumed one.': 'oxidizer_mass is the LOADED mass: the tank is sized for the REQUESTED burn time (m_ox = mdot_ox x burn_time_requested_s) because the tank is hardware and does not shrink when the grain runs out early. oxidizer_mass_consumed_kg is what the burn actually uses and oxidizer_mass_residual_kg is the unburnt remainder that flies as dead weight. The mass budget must use the loaded value, the performance budget the consumed one.',
            'propellant_type_source names the INPUT the propellant identity was resolved from; propellant_property_source names the TABLE its thermochemistry was read from. They are provenance declarations, not computed quantities: read them before comparing these results with a reference motor, because a derived identity or an inherited secondary coefficient set is not the same evidence as an explicit selection with its own record.': 'propellant_type_source names the INPUT the propellant identity was resolved from; propellant_property_source names the TABLE its thermochemistry was read from. They are provenance declarations, not computed quantities: read them before comparing these results with a reference motor, because a derived identity or an inherited secondary coefficient set is not the same evidence as an explicit selection with its own record.',
            'the post-combustion chamber length is clamped to [0.3, 3] x chamber diameter, so the achievable L* of a hybrid is set by the grain port volume and that clamp - NOT by the liquid engine literature band. l_star_achieved is the value this run actually built.': 'the post-combustion chamber length is clamped to [0.3, 3] x chamber diameter, so the achievable L* of a hybrid is set by the grain port volume and that clamp - NOT by the liquid engine literature band. l_star_achieved is the value this run actually built.',
            'total_impulse = thrust x burn_time: the design thrust (thrust) held for the burn time (burn_time, see burn_time_source), a steady-state constant-thrust burn at the design operating point; start-up and shut-down transients and throttling are not included. The design report, the PDF performance table and safety section and the OpenRocket export read this number.': 'total_impulse = thrust x burn_time: the design thrust (thrust) held for the burn time (burn_time, see burn_time_source), a steady-state constant-thrust burn at the design operating point; start-up and shut-down transients and throttling are not included. The design report, the PDF performance table and safety section and the OpenRocket export read this number.',
            'HRMA\'s theoretical solid thermochemistry (T_c, c*, gamma, M) and its ideal nozzle (optimum area ratio and thrust coefficient) ARE the NASA CEA solution of this composition at this chamber pressure. Equal columns show that the solver uses them unchanged; this is not an independent check of the thermochemistry.': 'HRMA\'s theoretical solid thermochemistry (T_c, c*, gamma, M) and its ideal nozzle (optimum area ratio and thrust coefficient) ARE the NASA CEA solution of this composition at this chamber pressure. Equal columns show that the solver uses them unchanged; this is not an independent check of the thermochemistry.',
            'NASA CEA equilibrium chamber gamma_s at this chamber pressure (condensed phase included); the nozzle solution is the CEA shifting-equilibrium expansion (see thermochemistry.nozzle)': 'NASA CEA equilibrium chamber gamma_s at this chamber pressure (condensed phase included); the nozzle solution is the CEA shifting-equilibrium expansion (see thermochemistry.nozzle)',
            'NASA CEA equilibrium chamber gamma_s at this chamber pressure; CEA did not solve the nozzle, so the thrust coefficient and expansion-ratio solutions use this value in the single-gamma relations': 'NASA CEA equilibrium chamber gamma_s at this chamber pressure; CEA did not solve the nozzle, so the thrust coefficient and expansion-ratio solutions use this value in the single-gamma relations',
            'NASA CEA shifting-equilibrium expansion (condensed phase included) to P_e = P_ambient at the design chamber pressure; off-design steps keep the fixed geometry with an equivalent single-gamma exponent gamma_nozzle that reproduces the CEA (P_e/P_c, area ratio) pair and a momentum anchor cf_anchor that reproduces the CEA thrust coefficient': 'NASA CEA shifting-equilibrium expansion (condensed phase included) to P_e = P_ambient at the design chamber pressure; off-design steps keep the fixed geometry with an equivalent single-gamma exponent gamma_nozzle that reproduces the CEA (P_e/P_c, area ratio) pair and a momentum anchor cf_anchor that reproduces the CEA thrust coefficient',
            'solved: 1D RP-1 regenerative station march (thermal_protection.station_march.coolant_exit_temperature_K)': 'solved: 1D RP-1 regenerative station march (thermal_protection.station_march.coolant_exit_temperature_K)',
            'solved: 1D RP-1 regenerative station march, peak hot-gas-side wall (thermal_protection.station_march.peak_wall_temperature_K)': 'solved: 1D RP-1 regenerative station march, peak hot-gas-side wall (thermal_protection.station_march.peak_wall_temperature_K)',
            /* V307 DİL-SON (kalem 8b): bugünkü kodla yeniden üretilen PDF derleminde çevrilemeyen sabit parçalar (k8_pdf_derlem_once.json). */
            'Chug (design point):': 'Chug (design point):',
            'Propellant mass loaded basis:': 'Propellant mass loaded basis:',
            'Nozzle material basis:': 'Nozzle material basis:',
            'Oxidizer mass inventory basis:': 'Oxidizer mass inventory basis:',
            'Whether the supplied efficiency really covers the loss is not checked.': 'Whether the supplied efficiency really covers the loss is not checked.',
            'Supplying a two-phase loss factor applies that factor; leaving the nozzle and kinetic efficiency fields empty applies the built-in estimate on the propellant-table nozzle efficiency.': 'Supplying a two-phase loss factor applies that factor; leaving the nozzle and kinetic efficiency fields empty applies the built-in estimate on the propellant-table nozzle efficiency.',
            'The thrust coefficient therefore carries no separate two-phase factor (two_phase_efficiency_applied = 1.0).': 'The thrust coefficient therefore carries no separate two-phase factor (two_phase_efficiency_applied = 1.0).',
            'A supplied efficiency is taken to be a delivered (lumped) value that already covers the two-phase loss; applying the built-in estimate on top of it would count that loss twice (measured on the solid page defaults: Isp over theoretical 0.84 with both, against 0.88-0.93 measured on six BATES firings of NASA-CR-158815).': 'A supplied efficiency is taken to be a delivered (lumped) value that already covers the two-phase loss; applying the built-in estimate on top of it would count that loss twice (measured on the solid page defaults: Isp over theoretical 0.84 with both, against 0.88-0.93 measured on six BATES firings of NASA-CR-158815).',
            'Jacket pressure drop (single value: feed budget, cycle, cooling)': 'Jacket pressure drop (single value: feed budget, cycle, cooling)',
            'Jacket pressure drop, bulk Bartz estimate (diagnostic, not used by the feed budget)': 'Jacket pressure drop, bulk Bartz estimate (diagnostic, not used by the feed budget)',
            'single-layer wall: the nozzle is the chamber wall carried along the contour, so its material is the chamber material (no separate nozzle material input on the liquid page)': 'single-layer wall: the nozzle is the chamber wall carried along the contour, so its material is the chamber material (no separate nozzle material input on the liquid page)',
            'The two disagree: the rule tests only the injector gain dP_inj/Pc, the loop also uses the sensitive time lag and the chamber time constant.': 'The two disagree: the rule tests only the injector gain dP_inj/Pc, the loop also uses the sensitive time lag and the chamber time constant.',
            'cooling_type \'ablative\': HRMA has no wall-temperature solver for a passively cooled wall in this chain (passive_thermal_protection sizes the liner/heat sink, it does not publish an equilibrium wall temperature)': 'cooling_type \'ablative\': HRMA has no wall-temperature solver for a passively cooled wall in this chain (passive_thermal_protection sizes the liner/heat sink, it does not publish an equilibrium wall temperature)',
            'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns, never the requested value. total_impulse_requested_Ns carries the design intent (thrust x requested burn time) and the two differ whenever the thrust curve is not perfectly flat (O/F shift as the port opens). Delivered basis: trapz(F(t), t) of this run\'s own thrust curve over [0, burn_time_effective_s].': 'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns, never the requested value. total_impulse_requested_Ns carries the design intent (thrust x requested burn time) and the two differ whenever the thrust curve is not perfectly flat (O/F shift as the port opens). Delivered basis: trapz(F(t), t) of this run\'s own thrust curve over [0, burn_time_effective_s].',
            'this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.': 'this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.',
            'LOADED propellant: oxidizer_mass (loaded; in a self-pressurised N2O tank liquid + ullage vapour) + fuel_mass_loaded (the cast grain, unburnt sliver included). propellant_mass_total is a different total: loaded oxidizer + BURNED fuel (fuel_mass).': 'LOADED propellant: oxidizer_mass (loaded; in a self-pressurised N2O tank liquid + ullage vapour) + fuel_mass_loaded (the cast grain, unburnt sliver included). propellant_mass_total is a different total: loaded oxidizer + BURNED fuel (fuel_mass).',
            'oxidizer_type \'n2o\' is not a tabulated class; the hybrid oxidiser \'n2o\' was read from it and selected the \'hybrid_n2o\' class. The equivalence is derived from the oxidiser decomposition enthalpy (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, eq. 2), not from a liquid-bipropellant table: the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence.': 'oxidizer_type \'n2o\' is not a tabulated class; the hybrid oxidiser \'n2o\' was read from it and selected the \'hybrid_n2o\' class. The equivalence is derived from the oxidiser decomposition enthalpy (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, eq. 2), not from a liquid-bipropellant table: the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence.',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 3): structural_analysis.py burkulma external_pressure_model (YAPISAL burkulma tablosu, SRV). */
            /* V307 DİL-SUNUCU-2: structural_analysis.py thermal_analysis.service_temperature_basis (YAPISAL ısıl not, SRV). */
            'peak (inner-wall) metal temperature; strength derating uses the section-average temperature': 'peak (inner-wall) metal temperature; strength derating uses the section-average temperature',
            'long-cylinder classical form (length-independent); conservative for short cylinders': 'long-cylinder classical form (length-independent); conservative for short cylinders',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 7): thermal_protection.py ABLATIVE_MATERIALS silica_phenolic source (ISIL KORUMA künyesi). */
            'Q* 8-12 MJ/kg literature band, NASA SP-8093 class silica-phenolic ablatives; Sutton & Biblarz 9th ed. Ch. 8.5. Density from central materials_db record \'ablative\' (silica-phenolic class).': 'Q* 8-12 MJ/kg literature band, NASA SP-8093 class silica-phenolic ablatives; Sutton & Biblarz 9th ed. Ch. 8.5. Density from central materials_db record \'ablative\' (silica-phenolic class).',
            'Q* 25-30 MJ/kg literature band (high heat-flux carbon-phenolic, NASA SP-8115 class nozzle liners / CPIA data); density ~1450 kg/m3 typical MX-4926 (approximate).': 'Q* 25-30 MJ/kg literature band (high heat-flux carbon-phenolic, NASA SP-8115 class nozzle liners / CPIA data); density ~1450 kg/m3 typical MX-4926 (approximate).',
            'Q* 4-6 MJ/kg literature band (filled EPDM internal insulation, NASA SP-8093 class); density ~1100 kg/m3 typical aramid/silica-filled EPDM (approximate).': 'Q* 4-6 MJ/kg literature band (filled EPDM internal insulation, NASA SP-8093 class); density ~1100 kg/m3 typical aramid/silica-filled EPDM (approximate).',
            /* V307 DİL-SUNUCU (ÜB-3): app.py /analyze_structural_safety design_basis.message (motorun cidarı). */
            'The wall thickness is the wall HRMA sized in the motor result, not a wall you built; it is evaluated here as drawn. This is not a verification of your own wall, and the verdict is the motor\'s own structural verdict when the request matches the motor result.': 'The wall thickness is the wall HRMA sized in the motor result, not a wall you built; it is evaluated here as drawn. This is not a verification of your own wall, and the verdict is the motor\'s own structural verdict when the request matches the motor result.',
            'Body tube': 'Body tube',
            'Bolted Joint — Preload, Torque & Separation (Shigley)': 'Bolted Joint — Preload, Torque & Separation (Shigley)',
            'Burn Area': 'Burn Area',
            'Burn Area & Kn vs Time': 'Burn Area & Kn vs Time',
            'Burn Area (cm²)': 'Burn Area (cm²)',
            'Burn Rate': 'Burn Rate',
            'Burn Time (s)': 'Burn Time (s)',
            'Burn rate coefficient': 'Burn rate coefficient',
            'Burn rate exponent': 'Burn rate exponent',
            'Burnout': 'Burnout',
            'CG/CP UNKNOWN': 'CG/CP UNKNOWN',
            'COMBUSTION ACTIVE': 'COMBUSTION ACTIVE',
            'Cam': 'Cam',
            'Cavitation risk detected': 'Cavitation risk detected',
            'Cd₀ (subsonic)': 'Cd₀ (subsonic)',
            'Center': 'Center',
            'Centerline': 'Centerline',
            'Chamber': 'Chamber',
            'Chamber &Oslash;': 'Chamber &Oslash;',
            'Chamber Body': 'Chamber Body',
            'Chamber Equilibrium Composition (solver)': 'Chamber Equilibrium Composition (solver)',
            'Chamber Length': 'Chamber Length',
            'Chamber Outline': 'Chamber Outline',
            'Chamber Pressure': 'Chamber Pressure',
            'Chamber Pressure (bar)': 'Chamber Pressure (bar)',
            'Chamber Pressure [bar]': 'Chamber Pressure [bar]',
            'Chamber Wall': 'Chamber Wall',
            'Chamber diameter (mm)': 'Chamber diameter (mm)',
            'Chamber pressure (bar)': 'Chamber pressure (bar)',
            'Chamber wall': 'Chamber wall',
            'Chemical Equilibrium': 'Chemical Equilibrium',
            'Circuit': 'Circuit',
            'Circular': 'Circular',
            'Cold-wall T (coolant side)': 'Cold-wall T (coolant side)',
            'Combustion (c*) Efficiency': 'Combustion (c*) Efficiency',
            'Combustion Analysis Dashboard': 'Combustion Analysis Dashboard',
            'Combustion Efficiency': 'Combustion Efficiency',
            'Combustion Efficiency (%)': 'Combustion Efficiency (%)',
            'Comparative Analysis — Snapshot & Compare Configurations': 'Comparative Analysis — Snapshot & Compare Configurations',
            'Complete Trajectory Analysis': 'Complete Trajectory Analysis',
            'Component': 'Component',
            'Comprehensive Safety — Risk Assessment & Pressure Vessel': 'Comprehensive Safety — Risk Assessment & Pressure Vessel',
            'Compressed Air': 'Compressed Air',
            'Cone angle not reported by the solver (drawn schematically)': 'Cone angle not reported by the solver (drawn schematically)',
            'Configuration': 'Configuration',
            'Consider heat sink or thermal mass for short burns': 'Consider heat sink or thermal mass for short burns',
            'Consider higher strength material': 'Consider higher strength material',
            'Consider thermal barrier coating': 'Consider thermal barrier coating',
            'Convective flux (Bartz, heat-sink wall)': 'Convective flux (Bartz, heat-sink wall)',
            'Coolant bulk T': 'Coolant bulk T',
            'Coolant pressure': 'Coolant pressure',
            'Coolant pressure (bar)': 'Coolant pressure (bar)',
            'Cooling Effectiveness': 'Cooling Effectiveness',
            'Cooling Jacket': 'Cooling Jacket',
            'Core &Oslash;': 'Core &Oslash;',
            'Core P(x) [bar]': 'Core P(x) [bar]',
            'Core diameter (mm)': 'Core diameter (mm)',
            'Counter-clockwise vortex': 'Counter-clockwise vortex',
            'Cross-Section View': 'Cross-Section View',
            'Cutaway': 'Cutaway',
            'Cycles to Failure': 'Cycles to Failure',
            'Depth from hot face (mm)': 'Depth from hot face (mm)',
            'Design Mode': 'Design Mode',
            'Design flux at reference cooled wall (conv + radiation)': 'Design flux at reference cooled wall (conv + radiation)',
            'Design point (motor result)': 'Design point (motor result)',
            // V307/GRAFİK-BİRİM (kalem 5): PERFORMANS 3B yüzey künyesi (iz adı, ipucu, not maddeleri).
            'Design point (as supplied)': 'Design point (as supplied)',
            "Design (Pc, O/F) at this surface's expansion basis": "Design (Pc, O/F) at this surface's expansion basis",
            'Design point reported by the motor solver': 'Design point reported by the motor solver',
            'Design point AS SUPPLIED to this figure — the caller did not declare it as a motor-solver result, so it was not re-solved here': 'Design point AS SUPPLIED to this figure — the caller did not declare it as a motor-solver result, so it was not re-solved here',
            "Design operating point, drawn at THIS SURFACE's basis (optimum / sea-level expansion, Pe = 1 bar) so that its height is comparable with the surface around it": "Design operating point, drawn at THIS SURFACE's basis (optimum / sea-level expansion, Pe = 1 bar) so that its height is comparable with the surface around it",
            'Expansion basis NOT checked: the solver did not converge at this node, so the height of this marker is not verified against the surface': 'Expansion basis NOT checked: the solver did not converge at this node, so the height of this marker is not verified against the surface',
            'Combustion-instability bands are NOT modeled here; the earlier shaded band had no sourced criterion and was removed.': 'Combustion-instability bands are NOT modeled here; the earlier shaded band had no sourced criterion and was removed.',
            'Sea-level expansion (Pe = 1 bar) is used for Isp.': 'Sea-level expansion (Pe = 1 bar) is used for Isp.',
            'Diameter': 'Diameter',
            'Dimensions': 'Dimensions',
            'Download plot as a png': 'Download plot as a png',
            'Dry Mass (kg)': 'Dry Mass (kg)',
            'East [m]': 'East [m]',
            'Effectiveness (%)': 'Effectiveness (%)',
            'Efficiency (%)': 'Efficiency (%)',
            'Equilibrium Isp': 'Equilibrium Isp',
            'Equilibrium wall T': 'Equilibrium wall T',
            'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.': 'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.',
            'Exhaust': 'Exhaust',
            'Exit Orifice': 'Exit Orifice',
            'Expansion &epsilon;': 'Expansion &epsilon;',
            'Expansion Ratio &epsilon;': 'Expansion Ratio &epsilon;',
            'Experimental Correlation — Model vs Static-Fire Database': 'Experimental Correlation — Model vs Static-Fire Database',
            'Exploded': 'Exploded',
            'Fallback schematic — the detailed injector view was not available for this run; plate outline is drawn, not computed.': 'Fallback schematic — the detailed injector view was not available for this run; plate outline is drawn, not computed.',
            'Fallback schematic — the solver nozzle contour was not available for this run;': 'Fallback schematic — the solver nozzle contour was not available for this run;',
            'Feed System Pressure Budget': 'Feed System Pressure Budget',
            'Feed System Pressure Budget (per circuit)': 'Feed System Pressure Budget (per circuit)',
            'Feed System — Slosh, Pressurant & Water Hammer': 'Feed System — Slosh, Pressurant & Water Hammer',
            /* ÖH D27 / P12aB3-03 — ENJEKTÖR KÜNYESİNİN İKİ SATIRI.
               ÖLÇÜLDÜ (a3/once.json): `chartText()` TR modunda altı
               satırın ikisini AYNEN İngilizce bırakıyordu — 'Face
               pattern: …' (çizimin süs olduğunu söyleyen künye) ve
               'Total Flow: not reported' (sayının raporlanmadığını
               söyleyen dürüstlük satırı). Sebep: 'Etiket: değer'
               kuralı etiketi sözlükte bulamayınca satırın TAMAMINI
               bırakıyor. Etiket + üç desen değeri + 'not reported'
               burada; üretici hrma/visualization/visualization.py. */
            'Face pattern': 'Face pattern',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S2) — enjektör şeması künye satırları (visualization.py). */
            'Hole positions are a schematic fill of the plate, NOT a drilling layout: the solver publishes the hole count and diameter, not the hole coordinates': 'Hole positions are a schematic fill of the plate, NOT a drilling layout: the solver publishes the hole count and diameter, not the hole coordinates',
            'Hole count: not reported by the solver — the face layout is NOT drawn': 'Hole count: not reported by the solver — the face layout is NOT drawn',
            'No hole marks, per-hole flow or total orifice area can be stated without it': 'No hole marks, per-hole flow or total orifice area can be stated without it',
            'Fill ratio h/R': 'Fill ratio h/R',
            'Fin Count': 'Fin Count',
            'Fin Root Chord (m)': 'Fin Root Chord (m)',
            'Fin Root LE from Nose (m)': 'Fin Root LE from Nose (m)',
            'Fin Span (m)': 'Fin Span (m)',
            'Fin Sweep (m)': 'Fin Sweep (m)',
            'Fin Tip Chord (m)': 'Fin Tip Chord (m)',
            'Final port': 'Final port',
            'Finocyl': 'Finocyl',
            'Fins': 'Fins',
            'Flame Temperature Profile': 'Flame Temperature Profile',
            'Flange': 'Flange',
            'Flash boiling risk detected': 'Flash boiling risk detected',
            'Flight Path': 'Flight Path',
            'Flight Phases': 'Flight Phases',
            'Flow Annulus': 'Flow Annulus',
            'Flow Channel': 'Flow Channel',
            'Flow Direction': 'Flow Direction',
            'Flow Streamlines': 'Flow Streamlines',
            'Flow separation (Summerfield)': 'Flow separation (Summerfield)',
            'circular rings (layout only, total area unchanged)':
                'circular rings (layout only, total area unchanged)',
            'hex lattice (layout only, total area unchanged)':
                'hex lattice (layout only, total area unchanged)',
            'square grid (layout only, total area unchanged)':
                'square grid (layout only, total area unchanged)',
            'not reported': 'not reported',
            'Frequency f1 (Hz)': 'Frequency f1 (Hz)',
            'Fuel': 'Fuel',
            'Fuel Feed': 'Fuel Feed',
            'Fuel Grain': 'Fuel Grain',
            'Fuel Type Regression Rate Comparison': 'Fuel Type Regression Rate Comparison',
            'Fuel grain': 'Fuel grain',
            'Full angle': 'Full angle',
            'GEOMETRY PREVIEW — 3D shape only; performance figures are unchanged. Re-run Calculate to update the analysis.': 'GEOMETRY PREVIEW — 3D shape only; performance figures are unchanged. Re-run Calculate to update the analysis.',
            'Grain Length': 'Grain Length',
            'Grain length (mm)': 'Grain length (mm)',
            'Ground Track (North vs East) — drift into wind = weathercock': 'Ground Track (North vs East) — drift into wind = weathercock',
            'Ground track': 'Ground track',
            'HRMA prediction [N]': 'HRMA prediction [N]',
            'Head End': 'Head End',
            'Heat Flux & Coolant Pressure': 'Heat Flux & Coolant Pressure',
            'Heat Flux (MW/m2)': 'Heat Flux (MW/m2)',
            'Heat Map': 'Heat Map',
            'Heat Map (no data)': 'Heat Map (no data)',
            'Heat Transfer Analysis Dashboard': 'Heat Transfer Analysis Dashboard',
            'Heat flux': 'Heat flux',
            'Heat flux (MW/m²)': 'Heat flux (MW/m²)',
            'Heat flux q': 'Heat flux q',
            'Height (m)': 'Height (m)',
            'High heat load - consider regenerative cooling': 'High heat load - consider regenerative cooling',
            'Hollow-cone spray': 'Hollow-cone spray',
            'Hot-Face Temperature History': 'Hot-Face Temperature History',
            'Hot-wall T (gas side)': 'Hot-wall T (gas side)',
            'Hybrid Rocket Motor - Axial Cross-Section View': 'Hybrid Rocket Motor - Axial Cross-Section View',
            'Hybrid Rocket Performance Analysis': 'Hybrid Rocket Performance Analysis',
            'Hydrogen Peroxide': 'Hydrogen Peroxide',
            /* Faz 6 / T64 (3 Ağustos 2026): bu iki iz adı BİREBİR sözlükte
               durmalı. PATTERNS listesindeki [/^Impinging pairs \((.+)\)$/]
               kuralı parantez içini olduğu gibi kopyalar; açı gerçekten
               bildirildiğinde ('2θ=60°') doğru davranış budur, 'angle not
               reported' geldiğinde ise metin İngilizce kalıyordu (ölçüldü:
               TR modda 'Çarpışmalı çiftler (angle not reported)').
               chartText() önce birebir sözlüğe bakar (lookup -> applyPatterns),
               bu yüzden birebir kayıt kuralı kendiliğinden yener. */
            'Impinging pairs (angle not reported)': 'Impinging pairs (angle not reported)',
            'Implement temperature monitoring': 'Implement temperature monitoring',
            'Improve cooling system': 'Improve cooling system',
            'Impulse Efficiency': 'Impulse Efficiency',
            'Impulse Efficiency vs Altitude': 'Impulse Efficiency vs Altitude',
            'Included angle': 'Included angle',
            'Included angle not reported by the solver (drawn schematically)': 'Included angle not reported by the solver (drawn schematically)',
            'Increase chamber wall thickness': 'Increase chamber wall thickness',
            'Increase wall thickness': 'Increase wall thickness',
            'Initial port': 'Initial port',
            'Inj. inlet': 'Inj. inlet',
            'Inj. ΔP': 'Inj. ΔP',
            'Injection Slot': 'Injection Slot',
            'Injection Velocity': 'Injection Velocity',
            'Injection Velocity (m/s)': 'Injection Velocity (m/s)',
            'Injector': 'Injector',
            'Injector Body': 'Injector Body',
            'Injector Face': 'Injector Face',
            'Injector Head': 'Injector Head',
            'Injector Plate': 'Injector Plate',
            'Injector Pressure': 'Injector Pressure',
            'Injector plate': 'Injector plate',
            'Inner jet': 'Inner jet',
            'Inner wall temperature (K)': 'Inner wall temperature (K)',
            'Iso': 'Iso',
            // ÖH D21 / P11B1-06 — 3B güverte Isp çipi referansını söyler.
            'Isp (vacuum)': 'Isp (vacuum)',
            'Isp (sea level)': 'Isp (sea level)',
            'Isp (design altitude)': 'Isp (design altitude)',
            'Isp (reference not declared)': 'Isp (reference not declared)',
            // V307/KÜÇÜKLER-2 (kalem 3): karşılaştırma figürü Isp ekseni/başlığı ortam satırı (panel.ambient.* ile aynı ifade).
            'sea level': 'sea level',
            'vacuum': 'vacuum',
            'design ambient not declared by the result': 'design ambient not declared by the result',
            'Isp vs O/F (equilibrium sweep)': 'Isp vs O/F (equilibrium sweep)',
            'Landing': 'Landing',
            'Landing under parachute': 'Landing under parachute',
            'Launch': 'Launch',
            'Launch Azimuth (° from N)': 'Launch Azimuth (° from N)',
            'Launch Elevation (°)': 'Launch Elevation (°)',
            'Legend min/max are DESIGN loads evaluated at the reference cooled wall (gas_side_analysis.chamber/throat_heat_flux); the flux at the equilibrium wall temperature can come out about 2.5x lower.': 'Legend min/max are DESIGN loads evaluated at the reference cooled wall (gas_side_analysis.chamber/throat_heat_flux); the flux at the equilibrium wall temperature can come out about 2.5x lower.',
            'Length (m)': 'Length (m)',
            'Length (mm)': 'Length (mm)',
            'Like-on-like doublet': 'Like-on-like doublet',
            'Liner / annulus': 'Liner / annulus',
            'Liquid Oxygen': 'Liquid Oxygen',
            'Liquid Rocket Performance Analysis': 'Liquid Rocket Performance Analysis',
            'Location': 'Location',
            'Low pressure drop (<20% of chamber pressure)': 'Low pressure drop (<20% of chamber pressure)',
            'M8 Mounting Hole': 'M8 Mounting Hole',
            'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY': 'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY',
            'MOTOR SIMULATION': 'MOTOR SIMULATION',
            'Mach': 'Mach',
            'Mach Number Distribution': 'Mach Number Distribution',
            'Mach field': 'Mach field',
            'Mach number': 'Mach number',
            'Mass (kg)': 'Mass (kg)',
            'Mass Flow': 'Mass Flow',
            'Mass Flow Rate': 'Mass Flow Rate',
            'Mass Flow Rate (kg/s)': 'Mass Flow Rate (kg/s)',
            'Mass Flow Rates': 'Mass Flow Rates',
            'Mass Fraction': 'Mass Fraction',
            'Mass Fractions Through Nozzle': 'Mass Fractions Through Nozzle',
            'Mass flow': 'Mass flow',
            'Mass vs Isp': 'Mass vs Isp',
            'Mass vs Thickness': 'Mass vs Thickness',
            'Material': 'Material',
            'Max Altitude (km)': 'Max Altitude (km)',
            'Maximum Altitude (km)': 'Maximum Altitude (km)',
            'Maximum Altitude — NOT AVAILABLE (solver did not reach apogee)': 'Maximum Altitude — NOT AVAILABLE (solver did not reach apogee)',
            'Mole Fraction': 'Mole Fraction',
            'Mole fraction': 'Mole fraction',
            'Monitor wall temperature during operation': 'Monitor wall temperature during operation',
            'Motor (dry)': 'Motor (dry)',
            'Motor Burnout': 'Motor Burnout',
            'Motor Chamber': 'Motor Chamber',
            'Motor Configuration Comparison': 'Motor Configuration Comparison',
            // V307/GRAFİK-BİRİM (kalem 5): karşılaştırma figürünün panel başlıkları.
            'Thrust Comparison': 'Thrust Comparison',
            'Isp Comparison': 'Isp Comparison',
            'Total Impulse Comparison': 'Total Impulse Comparison',
            'Isp vs Total Mass': 'Isp vs Total Mass',
            'Motor Outline': 'Motor Outline',
            'Motor Visualization (Simplified)': 'Motor Visualization (Simplified)',
            'Mounting Holes': 'Mounting Holes',
            'Multi-Port': 'Multi-Port',
            'NO BURN TIME SUPPLIED: TIME AXIS NOT DRAWN': 'NO BURN TIME SUPPLIED: TIME AXIS NOT DRAWN',
            'NORMAL SHOCK IN NOZZLE': 'NORMAL SHOCK IN NOZZLE',
            'Natural cooling insufficient - use forced cooling': 'Natural cooling insufficient - use forced cooling',
            'Nitrous Oxide': 'Nitrous Oxide',
            'No data available': 'No data available',
            'Normal shock (quasi-1D)': 'Normal shock (quasi-1D)',
            'North [m]': 'North [m]',
            'Nose Length (m)': 'Nose Length (m)',
            'Nose Type': 'Nose Type',
            'Nose cone': 'Nose cone',
            'Note: Cryogenic propellants require specialized handling equipment': 'Note: Cryogenic propellants require specialized handling equipment',
            'Nozzle': 'Nozzle',
            'Nozzle Bottom': 'Nozzle Bottom',
            'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)': 'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)',
            'Nozzle Mach Distribution Analysis': 'Nozzle Mach Distribution Analysis',
            'Nozzle Mach Number Distribution': 'Nozzle Mach Number Distribution',
            'Nozzle Profile': 'Nozzle Profile',
            'Nozzle Station': 'Nozzle Station',
            'Nozzle Top': 'Nozzle Top',
            'Nozzle wall': 'Nozzle wall',
            'N₂O Tank Blowdown History': 'N₂O Tank Blowdown History',
            'O/F Ratio': 'O/F Ratio',
            'O/F Ratio Optimization': 'O/F Ratio Optimization',
            'OVEREXPANDED': 'OVEREXPANDED',
            'OVERSTABLE': 'OVERSTABLE',
            'Of Ratio': 'Of Ratio',
            'Operating Point': 'Operating Point',
            'Orbit': 'Orbit',
            'Orifices': 'Orifices',
            'Outer Body': 'Outer Body',
            'Outer annulus': 'Outer annulus',
            'Ox Tank (required)': 'Ox Tank (required)',
            'Oxidizer': 'Oxidizer',
            'Oxidizer Feed': 'Oxidizer Feed',
            'Oxidizer Injection Velocity': 'Oxidizer Injection Velocity',
            'Oxidizer Mass Flux': 'Oxidizer Mass Flux',
            'Oxidizer/Fuel': 'Oxidizer/Fuel',
            'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT': 'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT',
            'PERFECT EXPANSION': 'PERFECT EXPANSION',
            'Parachute deploy': 'Parachute deploy',
            'Paraffin Wax': 'Paraffin Wax',
            'Parametric Analysis: Of Ratio Sweep': 'Parametric Analysis: Of Ratio Sweep',
            'Parametric Analysis: O/F Ratio Sweep': 'Parametric Analysis: O/F Ratio Sweep',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 9): app.py create_parametric_plot başlığı ve x ekseni; arayüzün sunduğu üç tarama (O/F, oda basıncı, genişleme oranı). */
            'Parametric Analysis: Chamber Pressure Sweep': 'Parametric Analysis: Chamber Pressure Sweep',
            'Parametric Analysis: Expansion Ratio Sweep': 'Parametric Analysis: Expansion Ratio Sweep',
            'Expansion Ratio': 'Expansion Ratio',
            'Performance Chart': 'Performance Chart',
            'Performance Summary': 'Performance Summary',
            'Pintle Injector - Cross Section': 'Pintle Injector - Cross Section',
            'Pintle Post': 'Pintle Post',
            'Pintle post': 'Pintle post',
            'Plot data unavailable': 'Plot data unavailable',
            'Polyethylene': 'Polyethylene',
            'Port': 'Port',
            'Port &Oslash;': 'Port &Oslash;',
            'Port (Final)': 'Port (Final)',
            'Port Diameter': 'Port Diameter',
            'Port Diameter (mm)': 'Port Diameter (mm)',
            'Port Diameter Growth': 'Port Diameter Growth',
            'Port diameter (mm)': 'Port diameter (mm)',
            'Port growth': 'Port growth',
            'Position': 'Position',
            'Position (m)': 'Position (m)',
            'Pressurant': 'Pressurant',
            'Pressure': 'Pressure',
            'Pressure (bar)': 'Pressure (bar)',
            'Pressure Distribution': 'Pressure Distribution',
            'Pressure Drop': 'Pressure Drop',
            'Pressure Drop (bar)': 'Pressure Drop (bar)',
            'Pressure Vessel — Sizing, MAWP & Real Burst Pressure': 'Pressure Vessel — Sizing, MAWP & Real Burst Pressure',
            'Propellant Mass': 'Propellant Mass',
            'Propellant Mass (kg)': 'Propellant Mass (kg)',
            'Propellant Mass Flow': 'Propellant Mass Flow',
            'Propellant Mass vs Of Ratio': 'Propellant Mass vs Of Ratio',
            'Propellant Mass vs O/F Ratio': 'Propellant Mass vs O/F Ratio',
            'Quasi-1D: Mach is uniform across each cross-section — the radial axis shows geometry only, no boundary layer is modeled.': 'Quasi-1D: Mach is uniform across each cross-section — the radial axis shows geometry only, no boundary layer is modeled.',
            'Radial Position (mm)': 'Radial Position (mm)',
            'Radial distance': 'Radial distance',
            'Radius (m)': 'Radius (m)',
            'Radius (mm)': 'Radius (mm)',
            'Rail Length (m)': 'Rail Length (m)',
            'Range': 'Range',
            'Range (km)': 'Range (km)',
            'Real-Time Motor Performance Dashboard': 'Real-Time Motor Performance Dashboard',
            'Regenerative Cooling — 1D Station March (Bartz + Dittus-Boelter)': 'Regenerative Cooling — 1D Station March (Bartz + Dittus-Boelter)',
            'Regression Rate': 'Regression Rate',
            'Regression Rate & Port Growth': 'Regression Rate & Port Growth',
            'Regression Rate (mm/s)': 'Regression Rate (mm/s)',
            'Regression rate': 'Regression rate',
            'Regression rate (mm/s)': 'Regression rate (mm/s)',
            'Reset View': 'Reset View',
            'S-N Curve': 'S-N Curve',
            'SEPARATED': 'SEPARATED',
            'SHOWERHEAD INJECTOR': 'SHOWERHEAD INJECTOR',
            'STABLE': 'STABLE',
            'STABLE (SLIGHTLY OVERSTABLE)': 'STABLE (SLIGHTLY OVERSTABLE)',
            'STANDBY': 'STANDBY',
            'Safety Factor': 'Safety Factor',
            'Sample count': 'Sample count',
            'Severe temperature derating (>30% yield loss): cool wall or change material': 'Severe temperature derating (>30% yield loss): cool wall or change material',
            'Showerhead': 'Showerhead',
            'Showerhead Injector - Front View': 'Showerhead Injector - Front View',
            'Showerhead pattern': 'Showerhead pattern',
            'Side': 'Side',
            'Slosh': 'Slosh',
            'Slosh Frequency & Mass Fraction vs Fill Level': 'Slosh Frequency & Mass Fraction vs Fill Level',
            'Slosh frequency f1': 'Slosh frequency f1',
            'Slosh mass fraction': 'Slosh mass fraction',
            'Solid Rocket Performance Analysis': 'Solid Rocket Performance Analysis',
            'Sonic — M = 1': 'Sonic — M = 1',
            'Spearman rank correlation ρ': 'Spearman rank correlation ρ',
            'Species': 'Species',
            'Specific Impulse': 'Specific Impulse',
            'Specific Impulse (s)': 'Specific Impulse (s)',
            'Specific Impulse vs Altitude': 'Specific Impulse vs Altitude',
            'Specific Impulse vs Of Ratio': 'Specific Impulse vs Of Ratio',
            'Specific Impulse vs O/F Ratio': 'Specific Impulse vs O/F Ratio',
            /* T64 ile aynı gerekçe: visualization.py:3316 açı bildirilmediğinde
               bu metni üretir; birebir kayıt olmazsa 'Püskürtme konisi
               (angle not reported)' diye yarı İngilizce kalır. Kısa 'Spray cone'
               kaydı ise 'Spray cone 2θ=60°' biçimini kurtarır (translateSegment
               sondaki sayıyı koruyup başı sözlükten geçirir). */
            'Spray cone': 'Spray cone',
            'Spray cone (angle not reported)': 'Spray cone (angle not reported)',
            'Star': 'Star',
            'Station': 'Station',
            'Stress (MPa)': 'Stress (MPa)',
            'Stress Amplitude (MPa)': 'Stress Amplitude (MPa)',
            'Structural Analysis Dashboard': 'Structural Analysis Dashboard',
            'Structural Min SF': 'Structural Min SF',
            'injector circuit solution': 'injector circuit solution',
            'Structural Safety — Pressure Vessel, Buckling, Fatigue': 'Structural Safety — Pressure Vessel, Buckling, Fatigue',
            'Support Arms': 'Support Arms',
            'Sweep maximum': 'Sweep maximum',
            'Swirl Chamber': 'Swirl Chamber',
            'Swirl Direction': 'Swirl Direction',
            'Swirl Flow Pattern': 'Swirl Flow Pattern',
            'Swirl Flow Region': 'Swirl Flow Region',
            'Swirl Injector - Face View': 'Swirl Injector - Face View',
            'Swirl Pattern': 'Swirl Pattern',
            'Swirl Region': 'Swirl Region',
            'T_wall': 'T_wall',
            'T_wall inner': 'T_wall inner',
            'T_wall outer': 'T_wall outer',
            'Tangential slot (swirl generator)': 'Tangential slot (swirl generator)',
            'Tangential slots': 'Tangential slots',
            'Tank Pressure [bar]': 'Tank Pressure [bar]',
            'Tank Temperature [K]': 'Tank Temperature [K]',
            'Temperature': 'Temperature',
            'Temperature (K)': 'Temperature (K)',
            'Temperature Distribution (K)': 'Temperature Distribution (K)',
            'Temperature by Station (solver)': 'Temperature by Station (solver)',
            'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled': 'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled',
            'Thermal Safety — Bartz Heat Transfer & Wall Temperatures': 'Thermal Safety — Bartz Heat Transfer & Wall Temperatures',
            'Thickness': 'Thickness',
            'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis': 'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis',
            'Throat': 'Throat',
            'Throat &Oslash;': 'Throat &Oslash;',
            'Throat Diameter': 'Throat Diameter',
            'Throat Diameter (mm)': 'Throat Diameter (mm)',
            'Throat Diameter vs Of Ratio': 'Throat Diameter vs Of Ratio',
            'Throat Diameter vs O/F Ratio': 'Throat Diameter vs O/F Ratio',
            'Throat station': 'Throat station',
            'Thrust': 'Thrust',
            'Thrust & Chamber Pressure vs Time': 'Thrust & Chamber Pressure vs Time',
            'Thrust (N)': 'Thrust (N)',
            /* ÖH D27 / P12aB3-06 — İTKİ KÜNYE AİLESİNİN ÜÇ DURUMU.
               ÖLÇÜLDÜ (a3/once.json): üçlünün yalnız VARSAYIM durumu
               sözlükteydi; iki ÇÖZÜLMÜŞ durum 'İtki (computed transient)'
               / 'İtki (computed curve)' diye yarı İngilizce çıkıyordu
               ('Taban (birim)' kuralı parantez içini BİRİM sanıyor, oysa
               burada parantez içi KÜNYE). Üretici:
               hrma/export/cad_visualization.py — eğrinin çözülmüş mü
               yoksa düz bir varsayım mı olduğunu söyleyen aile. */
            'Thrust (computed curve)': 'Thrust (computed curve)',
            'Thrust (computed transient)': 'Thrust (computed transient)',
            'Thrust (design point, constant-thrust assumption)': 'Thrust (design point, constant-thrust assumption)',
            'Thrust Coefficient': 'Thrust Coefficient',
            'Thrust Coefficient vs Altitude': 'Thrust Coefficient vs Altitude',
            'Thrust [N]': 'Thrust [N]',
            'Thrust vs Altitude': 'Thrust vs Altitude',
            'Thrust vs Of Ratio': 'Thrust vs Of Ratio',
            'Thrust vs O/F Ratio': 'Thrust vs O/F Ratio',
            'Time': 'Time',
            'Time (s)': 'Time (s)',
            'Time [s]': 'Time [s]',
            'Total Area': 'Total Area',
            'Total Flow': 'Total Flow',
            'Total Impulse': 'Total Impulse',
            'Total Impulse (N⋅s)': 'Total Impulse (N⋅s)',
            'Total Impulse Analysis - Altitude Performance': 'Total Impulse Analysis - Altitude Performance',
            'Total Length (m)': 'Total Length (m)',
            'Total Mass (kg)': 'Total Mass (kg)',
            'Total Velocity': 'Total Velocity',
            'Trajectory Profile': 'Trajectory Profile',
            'Transient': 'Transient',
            'Transient Thrust & Chamber Pressure': 'Transient Thrust & Chamber Pressure',
            'UNCHOKED': 'UNCHOKED',
            'UNDEREXPANDED': 'UNDEREXPANDED',
            'UNSTABLE / MARGINAL': 'UNSTABLE / MARGINAL',
            'HRMA Hybrid Rocket Motor - 3D CAD Design': 'HRMA Hybrid Rocket Motor - 3D CAD Design',
            'HRMA Hybrid Rocket Motor - Simplified View': 'HRMA Hybrid Rocket Motor - Simplified View',
            'Uncertainty Quantification — Monte Carlo Confidence Bands': 'Uncertainty Quantification — Monte Carlo Confidence Bands',
            'Use high thermal conductivity materials': 'Use high thermal conductivity materials',
            'Use higher temperature material': 'Use higher temperature material',
            'User Data Validation — Static-Fire CSV vs HRMA Prediction': 'User Data Validation — Static-Fire CSV vs HRMA Prediction',
            'Velocity': 'Velocity',
            'Velocity (m/s)': 'Velocity (m/s)',
            'Velocity Magnitude (m/s)': 'Velocity Magnitude (m/s)',
            'Velocity Profile': 'Velocity Profile',
            'Vertical Velocity': 'Vertical Velocity',
            'Von Mises Stress (MPa)': 'Von Mises Stress (MPa)',
            'WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>': 'WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>',
            'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!': 'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!',
            'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis': 'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis',
            'Wall Heat Flux Distribution': 'Wall Heat Flux Distribution',
            'Wall Heat Flux Waterfall Analysis': 'Wall Heat Flux Waterfall Analysis',
            'Wall P(x) [bar]': 'Wall P(x) [bar]',
            'Wall Temperature': 'Wall Temperature',
            'Wall Temperature Profile at End of Burn': 'Wall Temperature Profile at End of Burn',
            'Wall Temperatures vs Material Limits': 'Wall Temperatures vs Material Limits',
            'Wall Thickness (mm)': 'Wall Thickness (mm)',
            'Wall heat flux, heat-sink wall': 'Wall heat flux, heat-sink wall',
            'Wall temperature (K)': 'Wall temperature (K)',
            'Wall temperature approaches melting point': 'Wall temperature approaches melting point',
            'Wall temperature exceeds allowable limit': 'Wall temperature exceeds allowable limit',
            'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material': 'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material',
            'Water Hammer': 'Water Hammer',
            'Web Remaining': 'Web Remaining',
            'Width (m)': 'Width (m)',
            'Wind From (° from N)': 'Wind From (° from N)',
            'Wind Speed (m/s)': 'Wind Speed (m/s)',
            'X Position (mm)': 'X Position (mm)',
            'Y Position (mm)': 'Y Position (mm)',
            'Your test data [N]': 'Your test data [N]',
            'Zone': 'Zone',
            'aluminum': 'aluminum',
            'carbon fiber': 'carbon fiber',
            'nozzle proportions are drawn, not computed.': 'nozzle proportions are drawn, not computed.',
            'outer': 'outer',
            'stainless steel': 'stainless steel',
            'steel': 'steel',
            'titanium': 'titanium',
            'turbine mean diameter withheld: the pitch speed is a clipped bound, so the diameter would only restate that bound.': 'turbine mean diameter withheld: the pitch speed is a clipped bound, so the diameter would only restate that bound.',
            'turbine pitch speed capped below the optimum velocity ratio; stage count estimate is at its validity limit.': 'turbine pitch speed capped below the optimum velocity ratio; stage count estimate is at its validity limit.',
            'α [deg]': 'α [deg]',

            /* 2026-08-04 — app.py'nin son Türkçe hata/uyarı borcu EN'e
               çevrildi; TR karşılıkları buradan döner (serverText). */
            'CAD assembly could not be generated': 'CAD assembly could not be generated',
            'STL generation failed': 'STL generation failed',
            'injector design error': 'injector design error',
            'Required inputs for the solid motor calculation are missing; defaults were not applied and no design was produced.': 'Required inputs for the solid motor calculation are missing; defaults were not applied and no design was produced.',
            'Geometry mode takes diameter/length/core, design-point mode takes thrust + burn time. For the tutorial scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.': 'Geometry mode takes diameter/length/core, design-point mode takes thrust + burn time. For the tutorial scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.',
            'Required inputs for the liquid motor calculation are missing; defaults were not applied and no design was produced.': 'Required inputs for the liquid motor calculation are missing; defaults were not applied and no design was produced.',
            'For the tutorial/demo scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.': 'For the tutorial/demo scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.',
            'the model COMPUTES this distance from the impingement angle and hole diameter; see the value in the results': 'the model COMPUTES this distance from the impingement angle and hole diameter; see the value in the results',
            'this path models like-on-like doublets; the momentum-ratio criterion applies to unlike impingement': 'this path models like-on-like doublets; the momentum-ratio criterion applies to unlike impingement',
            'a hybrid injects ONE liquid stream (the oxidizer); the fuel/oxidizer momentum-ratio criterion applies only to unlike (fuel-on-oxidizer) impingement': 'a hybrid injects ONE liquid stream (the oxidizer); the fuel/oxidizer momentum-ratio criterion applies only to unlike (fuel-on-oxidizer) impingement',
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'the model COMPUTES the recess from the inner jet diameter; see the value in the results',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array',
            'this path sizes a single coaxial element for the whole oxidizer flow; multi-element arrays are not modelled': 'this path sizes a single coaxial element for the whole oxidizer flow; multi-element arrays are not modelled',

            /* ÖH D35 / OH-GT-19, OH-GT-21, OH-GT-22 (22 Eylül 2026) —
               TÜRKÇE EKRANDA KALAN ÇÖZÜCÜ CÜMLELERİ.
               ÖLÇÜLDÜ: docs/scofield/raw/OH/D35/dil-safligi/a1/once.json
                 GT19  besleme hattı / vana `validity` mesajlarının 6'sı
                       (gerçek /calculate_liquid yanıtı) TR'de İngilizce
                 GT21  gerekçe paragrafları (chug, hüküm künyesi, kütle
                       tanımı) `serverText`ten geçiyor ama karşılığı yok
                 GT22  figür kategori etiketleri, gösterge adı ve enjektör
                       şeması anotasyonları sözlükte hiç yok
               ÇEVİRİ BİREBİR: cümlenin fizik iddiası, sayıları, alan ve
               kaynak adları (F_L, p_v, IEC 60534-2-1, oxidizer_mass_basis)
               DEĞİŞMEZ. */
            'the choked pressure drop dP = F_L^2*(p1 - F_F*p_v) was NOT computed because critical_pressure_Pa was not supplied (the liquid critical pressure ratio factor F_F needs it). Cavitation and flashing WERE screened from the vapour pressure alone; only the choked limit is missing.': 'the choked pressure drop dP = F_L^2*(p1 - F_F*p_v) was NOT computed because critical_pressure_Pa was not supplied (the liquid critical pressure ratio factor F_F needs it). Cavitation and flashing WERE screened from the vapour pressure alone; only the choked limit is missing.',
            'the water-hammer coupling was NOT produced: wall_thickness_m is required, because the wave speed depends on the pipe wall elasticity.': 'the water-hammer coupling was NOT produced: wall_thickness_m is required, because the wave speed depends on the pipe wall elasticity.',
            'the water-hammer coupling was NOT produced: no fluid key was supplied, and no default fluid label is substituted. The wave speed needs a tabulated liquid bulk modulus; pass the propellant\'s own key (or bulk_modulus_Pa with a custom label) to get the coupling.': 'the water-hammer coupling was NOT produced: no fluid key was supplied, and no default fluid label is substituted. The wave speed needs a tabulated liquid bulk modulus; pass the propellant\'s own key (or bulk_modulus_Pa with a custom label) to get the coupling.',
            'the water-hammer coupling was NOT produced: the line budget leaves no usable pressure at the valve, which is where the surge originates. Fix the line sizing first (the valve was not sized either, for the same reason).': 'the water-hammer coupling was NOT produced: the line budget leaves no usable pressure at the valve, which is where the surge originates. Fix the line sizing first (the valve was not sized either, for the same reason).',
            'the valve was NOT sized: the line budget leaves no usable inlet pressure at the valve. Fix the line sizing first.': 'the valve was NOT sized: the line budget leaves no usable inlet pressure at the valve. Fix the line sizing first.',
            'non-choked turbulent liquid flow: the full valve pressure drop is used in the sizing equation.': 'non-choked turbulent liquid flow: the full valve pressure drop is used in the sizing equation.',
            'choked/flashing service: the sizing equation is evaluated at the choked pressure drop dP = F_L^2*(p1 - F_F*p_v), because flow stops rising beyond it (IEC 60534-2-1).': 'choked/flashing service: the sizing equation is evaluated at the choked pressure drop dP = F_L^2*(p1 - F_F*p_v), because flow stops rising beyond it (IEC 60534-2-1).',
            'flashing service was detected from the vapour pressure, but the sizing equation could NOT be moved to the choked pressure drop because critical_pressure_Pa was not supplied. The Cv below is evaluated at the FULL valve pressure drop and is therefore a LOWER BOUND on the required capacity, not a verified non-choked sizing.': 'flashing service was detected from the vapour pressure, but the sizing equation could NOT be moved to the choked pressure drop because critical_pressure_Pa was not supplied. The Cv below is evaluated at the FULL valve pressure drop and is therefore a LOWER BOUND on the required capacity, not a verified non-choked sizing.',
            'the flow regime was NOT verified: without critical_pressure_Pa the choked limit dP = F_L^2*(p1 - F_F*p_v) cannot be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'the flow regime was NOT verified: without critical_pressure_Pa the choked limit dP = F_L^2*(p1 - F_F*p_v) cannot be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.',
            'the flow regime was NOT verified: without vapor_pressure_Pa neither the cavitation index nor the choked limit can be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'the flow regime was NOT verified: without vapor_pressure_Pa neither the cavitation index nor the choked limit can be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.',
            'cavitation and flashing were NOT evaluated because vapor_pressure_Pa was not supplied. No safe/unsafe verdict is implied - supply the fluid properties to get one.': 'cavitation and flashing were NOT evaluated because vapor_pressure_Pa was not supplied. No safe/unsafe verdict is implied - supply the fluid properties to get one.',
            'A solid motor has no injector and no feed system, so the classical chug criterion (injector pressure drop ratio decoupling the feed from the chamber) has no counterpart here. No injector input is passed to the module: its chug report is NOT_EVALUATED by construction, not because data is missing. The solid-motor low-frequency counterpart (L* / bulk-mode instability) is NOT modelled.': 'A solid motor has no injector and no feed system, so the classical chug criterion (injector pressure drop ratio decoupling the feed from the chamber) has no counterpart here. No injector input is passed to the module: its chug report is NOT_EVALUATED by construction, not because data is missing. The solid-motor low-frequency counterpart (L* / bulk-mode instability) is NOT modelled.',
            'No acceptance is issued: the wall was sized by HRMA to meet the target safety factor, so the reported safety factor is that target read back (target x manufacturing allowance), not an independent verification. Supply the real wall_thickness (m) to obtain a verification. A remaining MARGINAL/UNSAFE status is a warning and is never suppressed.': 'No acceptance is issued: the wall was sized by HRMA to meet the target safety factor, so the reported safety factor is that target read back (target x manufacturing allowance), not an independent verification. Supply the real wall_thickness (m) to obtain a verification. A remaining MARGINAL/UNSAFE status is a warning and is never suppressed.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. Supply \'case_thickness\' (mm) to obtain one. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. Supply \'case_thickness\' (mm) to obtain one. A remaining MARGINAL/FAIL status is a warning and is never suppressed.',
            // V301/T-ÇAPA-D (kalem 1): kap hükmü dayanak cümleleri (katı motor + uç katmanı).
            'No acceptance is issued: the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'No acceptance is issued: the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.',
            'No acceptance is issued: the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'No acceptance is issued: the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.',
            'The case wall thickness was supplied by the user, so the burst margin and the vessel status are an evaluation of that wall.': 'The case wall thickness was supplied by the user, so the burst margin and the vessel status are an evaluation of that wall.',
            'The case wall thickness was supplied by the user and is the wall that was evaluated, so the burst margin and the vessel status are an evaluation of that wall.': 'The case wall thickness was supplied by the user and is the wall that was evaluated, so the burst margin and the vessel status are an evaluation of that wall.',
            'LOADED lift-off mass: dry mass + LOADED oxidizer (oxidizer_mass) + LOADED fuel grain (fuel_mass_loaded, which includes the unburnt sliver that flies as dead weight). The mass budget uses loaded values; the performance budget uses the consumed ones (fuel_mass, oxidizer_mass_consumed_kg) - same rule as oxidizer_mass_basis.': 'LOADED lift-off mass: dry mass + LOADED oxidizer (oxidizer_mass) + LOADED fuel grain (fuel_mass_loaded, which includes the unburnt sliver that flies as dead weight). The mass budget uses loaded values; the performance budget uses the consumed ones (fuel_mass, oxidizer_mass_consumed_kg) - same rule as oxidizer_mass_basis.',
            'The analysis reported that it does not apply, but named no reason.': 'The analysis reported that it does not apply, but named no reason.',
            'Total': 'Total',
            'Peak': 'Peak',
            'Average': 'Average',
            'Design Pc': 'Design Pc',
            'Exit': 'Exit',
            'Tank Outlet': 'Tank Outlet',
            'Main Valve': 'Main Valve',
            'Filters (assumed K=10)': 'Filters (assumed K=10)',
            // ÖH A2 sivi-sogutma · 7. tur: sıvı 'Pressure Distribution'
            // çubuk kategorileri (visualization._perf_panels_liquid).
            'Feed': 'Feed',
            'Feed (Fuel)': 'Feed (Fuel)',
            'Feed (Ox)': 'Feed (Ox)',
            'Feed Lines': 'Feed Lines',
            // V301/L-REJ (NK-36): yakıt bütçesinin rejeneratif ceket kalemi
            // (fuel_line.regen_jacket) — 'Cooling Jacket' anahtarı bu sözlükte
            // zaten vardı (yinelenen ikinci tanım kaldırıldı, ana model).
            'This run (solver)': 'This run (solver)',
            'injector plate': 'injector plate',
            'parallel axial jets': 'parallel axial jets',
            'feed manifold': 'feed manifold',
            'included angle 2θ': 'included angle 2θ',
            'impingement point': 'impingement point',
            'flat spray fan': 'flat spray fan',
            'chamber side →': 'chamber side →',
            'dP → jet velocity': 'dP → jet velocity',
            'Showerhead injector plate': 'Showerhead injector plate',
            'Pintle injector': 'Pintle injector',
            'Swirl injector plate': 'Swirl injector plate',
            'Impinging-jet injector plate': 'Impinging-jet injector plate',
            'Coaxial injector plate': 'Coaxial injector plate',
            /* ÖH D36 / dil2-i18n-pdf a2 (K4) — güvenlik panelinin patlayıcı
               ve toksik hüküm künyesi (safety_panel.js explosiveBasisBlock /
               toxicBasisBlock) sunucu cümlelerini serverText üzerinden basar.
               Cümleler hrma/analysis/safety_analysis.py:1539 (requirements_scope),
               :1615 (toxic_hazard_level_withheld_because), toksik envanter
               sınıflandırıcısı (tanınmayan sınıf) ve app.py _lift_toxic_basis
               (_basis) ile BİREBİR; üretici cümleyi değiştirirse eşleşme düşer
               ve metin İngilizce AYNEN kalır (uydurma çeviri yok). */
            'Unconditional items only: the TNT-threshold items (magazine siting, Class 1 routing) are withheld with the explosive verdict.': 'Unconditional items only: the TNT-threshold items (magazine siting, Class 1 routing) are withheld with the explosive verdict.',
            'No toxic inventory could be identified for this propellant, so no toxic hazard level was computed. A hazard that was not assessed is not an absent hazard.': 'No toxic inventory could be identified for this propellant, so no toxic hazard level was computed. A hazard that was not assessed is not an absent hazard.',
            'where the toxic verdict came from: which propellant class the request resolved to, whether an inventory could be identified for it, and why. A level of NOT_EVALUATED means no toxic hazard was assessed - it does NOT mean there is no toxic hazard.': 'where the toxic verdict came from: which propellant class the request resolved to, whether an inventory could be identified for it, and why. A level of NOT_EVALUATED means no toxic hazard was assessed - it does NOT mean there is no toxic hazard.',
            'propellant_type did not resolve to any propellant class HRMA has a toxic inventory rule for, so no toxic inventory was identified. An unidentified propellant is not a non-toxic propellant: no toxic hazard level is published for it.': 'propellant_type did not resolve to any propellant class HRMA has a toxic inventory rule for, so no toxic inventory was identified. An unidentified propellant is not a non-toxic propellant: no toxic hazard level is published for it.',
            /* ÖH D37 · A1b dil-cozucu-nesri — çözücü nesri (DV36-02, DV36-03,
               DV-GT21, DV36-21, DV-MIXED). Cümleler üreticinin kendi
               dizeleriyle BİREBİR (dosya:satır kalem yorumlarında,
               tests/test_d37_dil_b1.py üreticiden okur); üretici değişirse
               eşleşme düşer ve metin İngilizce AYNEN kalır. */
            'Solver warnings for this injector': 'Solver warnings for this injector',
            'liquid monopropellant: the hydrazine family (MMH / UDMH / N2H4) is inventoried from the tabulated exposure limits.': 'liquid monopropellant: the hydrazine family (MMH / UDMH / N2H4) is inventoried from the tabulated exposure limits.',
            'the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence': 'the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence',
            'time-marching solution: F = mdot_total(t)*Isp(t)*g0, Pc = mdot_total(t)*c_star(t)/(Cd*At) with the same throat discharge coefficient the throat was sized with (single C_D contract: the mass flow carries Cd, the throat area is geometric); oxidiser flow is constant, fuel flow follows the regressing port': 'time-marching solution: F = mdot_total(t)*Isp(t)*g0, Pc = mdot_total(t)*c_star(t)/(Cd*At) with the same throat discharge coefficient the throat was sized with (single C_D contract: the mass flow carries Cd, the throat area is geometric); oxidiser flow is constant, fuel flow follows the regressing port',
            'Self-pressurised N2O tank blowdown solution of this run: tank pressure, oxidiser flow, chamber pressure and thrust fall during the burn. This is the delivered curve the flight integrates; its trapezoidal integral is the published total impulse. The curve starts at t = 0 with the ignition state and each solver step is integrated once. The constant-oxidiser-flow design curve is published separately for comparison.': 'Self-pressurised N2O tank blowdown solution of this run: tank pressure, oxidiser flow, chamber pressure and thrust fall during the burn. This is the delivered curve the flight integrates; its trapezoidal integral is the published total impulse. The curve starts at t = 0 with the ignition state and each solver step is integrated once. The constant-oxidiser-flow design curve is published separately for comparison.',
            'solid grain burn-back solver (time-marched): burn area from grain regression, chamber pressure from the iterative pressure-burn rate fixed point (r = a*Pc^n)': 'solid grain burn-back solver (time-marched): burn area from grain regression, chamber pressure from the iterative pressure-burn rate fixed point (r = a*Pc^n)',
            'the O/F-ratio extremes and the specific-impulse extremes': 'the O/F-ratio extremes and the specific-impulse extremes',
            'the first samples of flow separation, of loss of choking and of burnout': 'the first samples of flow separation, of loss of choking and of burnout',
            'total impulse, burn time, average thrust, O/F shift statistics, warnings': 'total impulse, burn time, average thrust, O/F shift statistics, warnings',
            'time-averaged c*, time-averaged Isp, O/F shift statistics': 'time-averaged c*, time-averaged Isp, O/F shift statistics',
            'total impulse, average thrust, curve shape, stability, warnings': 'total impulse, average thrust, curve shape, stability, warnings',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + nozzle. SCOPE LIMITS: the nozzle share is a 30%-of-chamber rule of thumb (see nozzle_weight_basis), and the injector is NOT included. The CAD mass breakdown (cad_design.performance_summary.mass_breakdown.total_dry_mass) is a DIFFERENT total: it uses the as-drawn nozzle and the injector but omits the closures, so the two do not agree.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + nozzle. SCOPE LIMITS: the nozzle share is a 30%-of-chamber rule of thumb (see nozzle_weight_basis), and the injector is NOT included. The CAD mass breakdown (cad_design.performance_summary.mass_breakdown.total_dry_mass) is a DIFFERENT total: it uses the as-drawn nozzle and the injector but omits the closures, so the two do not agree.',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items.',
            // V3 yapi-sf 2. tur: yapısal künyeler (karar §28-24 (C), Ş6) — EN kimlik.
            'TRUE means: a wall temperature used in this structural evaluation is at or above the melting point of the material, or above the last point of its strength-derating data. Above that point the strength is held at the last curve value (an upper bound, not a conservative value), and at or above melting the section has no load-carrying capacity at all. The strength, safety factors, wall thickness and masses computed from this evaluation are therefore outside the validity limit of the structural model: they are published as diagnostic numbers only, not as valid design outputs, and no acceptance and no numeric design verdict is issued. When the wall temperature comes from the heat-transfer module (wall_temperature_source = heat_transfer_module) it is a bare-wall steady-state estimate in which protection by the propellant grain, liner or insulation is not modelled, so an unreachable or failing result is a limit of the current model, not a statement that a real motor of this design is impossible.': 'TRUE means: a wall temperature used in this structural evaluation is at or above the melting point of the material, or above the last point of its strength-derating data. Above that point the strength is held at the last curve value (an upper bound, not a conservative value), and at or above melting the section has no load-carrying capacity at all. The strength, safety factors, wall thickness and masses computed from this evaluation are therefore outside the validity limit of the structural model: they are published as diagnostic numbers only, not as valid design outputs, and no acceptance and no numeric design verdict is issued. When the wall temperature comes from the heat-transfer module (wall_temperature_source = heat_transfer_module) it is a bare-wall steady-state estimate in which protection by the propellant grain, liner or insulation is not modelled, so an unreachable or failing result is a limit of the current model, not a statement that a real motor of this design is impossible.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor was computed at a wall temperature outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). How the wall was chosen is stated in design_mode, sizing_feasible and sizing_infeasible_reason.': 'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor was computed at a wall temperature outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). How the wall was chosen is stated in design_mode, sizing_feasible and sizing_infeasible_reason.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind these masses comes from a structural evaluation outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded).': 'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind these masses comes from a structural evaluation outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded).',
            'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (wall temperature at or above the melting point of the material, or above its strength-derating data). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.': 'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (wall temperature at or above the melting point of the material, or above its strength-derating data). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.',
            'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.': 'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.',
            'DRAWN SOLID (single source), insert + structural housing nozzle: inner contour from nozzle_design.sample_nozzle_inner_contour, the insert thickness added outward with the density of the selected nozzle material (nozzle_material), then the housing thickness with the density of the chamber material (nozzle_geometry.nozzle_construction). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass.': 'DRAWN SOLID (single source), insert + structural housing nozzle: inner contour from nozzle_design.sample_nozzle_inner_contour, the insert thickness added outward with the density of the selected nozzle material (nozzle_material), then the housing thickness with the density of the chamber material (nozzle_geometry.nozzle_construction). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass.',
            'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability': 'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.',
            // V306/HİBRİT-KÜTLE (kalem 6): enjektör dahil kuru kütle künyesi — EN kimlik.
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight.',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.',
            'The through-wall temperature difference was computed on the wall named in thermal_reference_wall_thickness_mm. In size mode it is scaled to the evaluated wall by the thickness ratio (fixed heat flux, planar conduction drop q*t/k), so the sized wall and its published thermal stress come from the same model (equal values mean the same wall). With no reference wall the difference is held at the supplied value. In verify mode the difference belongs to the supplied wall and is not scaled.': 'The through-wall temperature difference was computed on the wall named in thermal_reference_wall_thickness_mm. In size mode it is scaled to the evaluated wall by the thickness ratio (fixed heat flux, planar conduction drop q*t/k), so the sized wall and its published thermal stress come from the same model (equal values mean the same wall). With no reference wall the difference is held at the supplied value. In verify mode the difference belongs to the supplied wall and is not scaled.',
            'TRUE means: the evaluated wall was chosen by HRMA to meet the design safety factor target, so this section was not checked against a thickness you supplied. It does NOT by itself mean the published safety factor equals the target: sizing puts the TOTAL hoop stress (pressure + thermal, at the derated strength) on the target; when no thickness can reach it, sizing_feasible is false and the published factor is a measurement below the target. Use safety_factor_reads_back_target for that question.': 'TRUE means: the evaluated wall was chosen by HRMA to meet the design safety factor target, so this section was not checked against a thickness you supplied. It does NOT by itself mean the published safety factor equals the target: sizing puts the TOTAL hoop stress (pressure + thermal, at the derated strength) on the target; when no thickness can reach it, sizing_feasible is false and the published factor is a measurement below the target. Use safety_factor_reads_back_target for that question.',
            '\'tautological\' here means the binding station\'s wall was SIZED by HRMA (design_mode == size), i.e. it was not checked against a thickness you supplied. It does NOT mean the number equals the design target: sizing puts the TOTAL hoop stress (pressure + thermal) on the target, and where no thickness reaches it the chamber reports sizing_feasible = false and the published factor is a measurement below the target. The sharp answer is binding_safety_factor_reads_back_target; the per-station inventory is stations_reading_back_target.': '\'tautological\' here means the binding station\'s wall was SIZED by HRMA (design_mode == size), i.e. it was not checked against a thickness you supplied. It does NOT mean the number equals the design target: sizing puts the TOTAL hoop stress (pressure + thermal) on the target, and where no thickness reaches it the chamber reports sizing_feasible = false and the published factor is a measurement below the target. The sharp answer is binding_safety_factor_reads_back_target; the per-station inventory is stations_reading_back_target.',
            'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (thin_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification': 'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (thin_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification',
            'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (lame_thick_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification': 'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (lame_thick_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification',
            'no wall thickness was supplied by the user and the requested safety factor is UNREACHABLE for the sizing load (see sizing_load and sizing_infeasible_reason), so the reported thickness does not meet the target; the safety factor below is a MEASUREMENT, not a read-back': 'no wall thickness was supplied by the user and the requested safety factor is UNREACHABLE for the sizing load (see sizing_load and sizing_infeasible_reason), so the reported thickness does not meet the target; the safety factor below is a MEASUREMENT, not a read-back',
            'structural analysis not available': 'structural analysis not available',
            'Sweep maximum (grid node, not the solver optimum)': 'Sweep maximum (grid node, not the solver optimum)',
            'Sea-level exit, Pc': 'Sea-level exit, Pc',
            'Sweep ceiling, same solver, refined between grid nodes (not the solver optimum)': 'Sweep ceiling, same solver, refined between grid nodes (not the solver optimum)',
            'Sweep ceiling (refined)': 'Sweep ceiling (refined)',
            'This run': 'This run',
            'Isp vs O/F sweep not available: propellant identity (fuel/oxidizer/chamber pressure) was not supplied to this figure.': 'Isp vs O/F sweep not available: propellant identity (fuel/oxidizer/chamber pressure) was not supplied to this figure.',
            'Mixed provenance (see property_sources)': 'Mixed provenance (see property_sources)',
            'Derived from chemical formula (molecular weight only); not present in the NASA CEA species table': 'Derived from chemical formula (molecular weight only); not present in the NASA CEA species table',
            'NASA CEA species table': 'NASA CEA species table',
            /* ÖH D37 · A1c panel-dil — sunucu beyan cümleleri (K5). Anahtar
               üreticinin cümlesiyle BİREBİR: CAD performans grafiği iki
               gerekçesi (cad_visualization.py PERFORMANCE_CHART_NOT_DRAWN_REASON
               + _add_performance_chart itki notu), yanma süresi verilmedi
               gerekçeleri (safety_analysis.py / liquid_rocket_engine.py
               BURN_TIME_NOT_SUPPLIED_REASON, combustion_analysis.py
               calculate_thrust_at_altitudes 'reason'), A1b-3 panel-js
               OH-D37-G2 koşu noktası ipucu/notu (panel-js raporundan birebir;
               denetçi 2. tur Ş4: panel-js 4bbbd32f visualization.py ile
               karakter karakter karşılaştırıldı).
               tests/test_d37_panel_dil_a1.py cümleleri üreticiden alır;
               üretici değişirse eşleşme düşer ve metin İngilizce AYNEN kalır. */
            'Performance chart not drawn: burn_time was not published by the solver (no burn time was supplied) and no duration is assumed.': 'Performance chart not drawn: burn_time was not published by the solver (no burn time was supplied) and no duration is assumed.',
            'Performance chart not drawn: thrust was not published by the solver and no design thrust is assumed.': 'Performance chart not drawn: thrust was not published by the solver and no design thrust is assumed.',
            'burn time not supplied: motor_data carries no burn_time and no duration is assumed (the previous code silently used 10 s), so the quantities that depend on it were not evaluated. Supply burn_time [s] to get them.': 'burn time not supplied: motor_data carries no burn_time and no duration is assumed (the previous code silently used 10 s), so the quantities that depend on it were not evaluated. Supply burn_time [s] to get them.',
            'the burn time was not supplied (max_burn_duration is empty) and no default is assumed, so nothing that depends on it was computed: burn_time, total_impulse, propellant_mass_kg, the propellant tank card, the feed-system tank volumes and the autogenous pressurant budget. Fill "Maximum Burn Duration" (or send use_tutorial_defaults for the declared tutorial value) to get them.': 'the burn time was not supplied (max_burn_duration is empty) and no default is assumed, so nothing that depends on it was computed: burn_time, total_impulse, propellant_mass_kg, the propellant tank card, the feed-system tank volumes and the autogenous pressurant budget. Fill "Maximum Burn Duration" (or send use_tutorial_defaults for the declared tutorial value) to get them.',
            'burn time not supplied (motor_data has no positive burn_time) and no duration is assumed, so the sea-level thrust (total impulse / burn time) and the altitude table built on it were not computed. The previous code silently used 10 s here.': 'burn time not supplied (motor_data has no positive burn_time) and no duration is assumed, so the sea-level thrust (total impulse / burn time) and the altitude table built on it were not computed. The previous code silently used 10 s here.',
            'Exit: ISA sea level, no nozzle ε': 'Exit: ISA sea level, no nozzle ε',
            'Exit basis not published': 'Exit basis not published',
            /* Denetçi 2. tur Ş4 — panel-js 4bbbd32f (2. tur Ş6): ε yolunda
               çıkış basıncı yayımlanmadıysa ipucu satırı 'nan bar' yerine
               bunu basar (visualization.py koşu noktası bloğu; metin o
               dalın dosyasından okundu). Desen (p_e … bar) bunu tutmaz. */
            'Exit: supplied nozzle ε, p_e not published': 'Exit: supplied nozzle ε, p_e not published',
            /* Ayrıntılı CAD alt grafik başlıkları (cad_visualization.py
               DetailedCADGenerator subplot_titles, sıvı :4306 / katı :4913) —
               beyan notuyla aynı figür; 'Cross-Section View' zaten vardı. */
            'External View': 'External View',
            'Grain Cross-Section': 'Grain Cross-Section',
            'This run point: the solver result does not publish its exit basis, so whether the point shares the sweep curve\'s sea-level path or uses the design expansion ratio is not stated.': 'This run point: the solver result does not publish its exit basis, so whether the point shares the sweep curve\'s sea-level path or uses the design expansion ratio is not stated.',
            /* V3 KK 3. tur (15 Eki, §28-50 (c)) — TR kipte İngilizce kalan
               sunucu cümleleri. Anahtar üreticinin cümlesiyle BİREBİR
               (tests/test_v3_kucuk.py 3. tur cümleleri üreticiden kurar);
               üretici değişirse eşleşme düşer, metin AYNEN kalır. */
            'No closure bolt count was supplied, so the joint is not sized. Enter the number of closure bolts to get separation and proof safety factors.': 'No closure bolt count was supplied, so the joint is not sized. Enter the number of closure bolts to get separation and proof safety factors.',
            'burn_time is validated but NOT used by the structural model: stresses and safety factors are steady-state at the design pressure, and the fatigue check counts PRESSURISATION CYCLES (design_cycles), which a burn duration does not set. No burn time was assumed on your behalf either - the field simply does not enter this analysis. Creep and other time-at-temperature effects are NOT modelled here (they would be the only route by which a burn duration could change these numbers).': 'burn_time is validated but NOT used by the structural model: stresses and safety factors are steady-state at the design pressure, and the fatigue check counts PRESSURISATION CYCLES (design_cycles), which a burn duration does not set. No burn time was assumed on your behalf either - the field simply does not enter this analysis. Creep and other time-at-temperature effects are NOT modelled here (they would be the only route by which a burn duration could change these numbers).',
            'NOT GIVEN — neither exit_diameter nor expansion_ratio was supplied; the sampler falls back to its own generic exit diameter, so the divergent extent of this axis is NOT this motor\'s': 'NOT GIVEN — neither exit_diameter nor expansion_ratio was supplied; the sampler falls back to its own generic exit diameter, so the divergent extent of this axis is NOT this motor\'s',
            'outputs.*.p5/p25/p50/p75/p95 and std/cv_percent': 'outputs.*.p5/p25/p50/p75/p95 and std/cv_percent',
            'every model input not listed in conditional_on_inputs': 'every model input not listed in conditional_on_inputs',
            'independent (zero rank correlation)': 'independent (zero rank correlation)',
            'These percentiles describe the spread produced by the listed input distributions alone. They are NOT a confidence interval on the true motor performance: model-form error (empirical correlation uncertainty, omitted physics) is not sampled and is not included, inputs are sampled as independent, and every input not listed is held at its nominal value. Widening or narrowing this band by changing input distributions does not change how well the model matches hardware.': 'These percentiles describe the spread produced by the listed input distributions alone. They are NOT a confidence interval on the true motor performance: model-form error (empirical correlation uncertainty, omitted physics) is not sampled and is not included, inputs are sampled as independent, and every input not listed is held at its nominal value. Widening or narrowing this band by changing input distributions does not change how well the model matches hardware.',
            'engine dry mass only: this result publishes no propellant tank mass, so tank structure and any residual propellant are NOT included': 'engine dry mass only: this result publishes no propellant tank mass, so tank structure and any residual propellant are NOT included',
            'engine dry mass not published by the motor model; tank structure and residual propellant are therefore not accounted for either': 'engine dry mass not published by the motor model; tank structure and residual propellant are therefore not accounted for either',
        },
        tr: {            '(reference cooled wall)': '(referans soğutulmuş cidar)',
            // V306/DİL-KATI M-KATI-17: solid_rocket_engine heat_release_rate_operating_point (Isıl sekme).
            'peak of the solved burn': 'çözülen yanmanın tepesi',
            // V3.0.5 T-ÇAPA-C1: regen_cooling.RP1_COKING_BASIS (soğutma paneli rozet ipucu).
            'RP-1 coolant-side wall temperature, two tiers: 728 K is the design criterion of NASA SP-8087 (1972) sec. 3.1.1.5.4 p. 62 ("do not operate with liquid-wall temperatures above 850 F (728 K) for RP-1") - above it the design does not meet that criterion; 561 K is a deposit-risk WARNING level of this software, based on experimental findings (NASA CR-168277: deposits in copper tubes at 560-750 K) that must be validated for the application conditions; it does not by itself make the design unsafe. Staying below 728 K does NOT mean the wall stays free of deposits or is safe.': 'RP-1 soğutucu tarafı cidar sıcaklığı, iki kademe: 728 K, NASA SP-8087 (1972) bölüm 3.1.1.5.4 s. 62 tasarım ölçütüdür ("RP-1 için sıvı tarafı cidar sıcaklığı 850 F (728 K) üstünde çalıştırmayın") — bunun üstünde tasarım o ölçütü karşılamaz; 561 K bu yazılımın deneysel bulgulara (NASA CR-168277: bakır tüplerde 560-750 K arasında birikim) dayanan birikim riski UYARI düzeyidir ve uygulama koşulları için doğrulanmalıdır; tek başına tasarımı güvensiz yapmaz. 728 K altında kalmak cidarın birikimsiz ya da güvenli kaldığı anlamına GELMEZ.',
            // V306/GÜVERTE-HATA: /analyze_structural_safety termal yol koşmadığında (Yapısal sekme).
            'No wall or gas temperature was supplied, so the thermal path did not run and no wall temperature is assumed: the material strength is read at 293.15 K, the ambient reference of the heat-transfer chain (no thermal derating).': 'Cidar ya da gaz sıcaklığı verilmedi; termal yol koşmadı ve cidar sıcaklığı varsayılmadı: malzeme dayanımı, ısı zincirinin ortam referansı olan 293,15 K sıcaklıkta okunur (ısıl düşürme yok).',
            'Thermal path not run: no gas or wall temperature supplied.': 'Termal yol koşmadı: gaz ya da cidar sıcaklığı verilmedi.',
            'Validation failed': 'Doğrulama başarısız',
            '3D Hybrid Rocket Motor Visualization': 'Hibrit Roket Motoru 3B Görselleştirme',
            '3D Motor Assembly': '3B Motor Montajı',
            '3D Motor Visualization': '3B Motor Görselleştirmesi',
            '3D Performance Map: Chamber Pressure vs O/F vs Isp': '3B Performans Haritası: Oda basıncı — O/F — Özgül itki',
            '3D Performance Surface Analysis': '3B Performans Yüzeyi Analizi',
            '3D visualization unavailable': '3B görselleştirme kullanılamıyor',
            'ABS Plastic': 'ABS Plastiği',

            'Acceleration': 'İvme',
            'Acceleration (g)': 'İvme (g)',
            'Acceleration Profile': 'İvme Profili',
            'Load Factor Profile': 'Yük Çarpanı Profili',
            'Load factor (g)': 'Yük çarpanı (g)',
            'Load factor (sensed)': 'Yük çarpanı (algılanan)',
            'Kinematic |dv/dt|': 'Kinematik |dv/dt|',
            'Advanced Performance — 3D Surface, Mach Contour, Heat Flux': 'Gelişmiş Performans — 3B Yüzey, Mach Konturu, Isı Akısı',
            'Altitude': 'İrtifa',
            'Altitude & Mach vs Time (launch → apogee)': 'İrtifa ve Mach Sayısı - Zaman (kalkış → apoje)',
            'Altitude (km)': 'İrtifa (km)',
            'Altitude Performance Analysis': 'İrtifa Performans Analizi',
            'Altitude [m]': 'İrtifa [m]',
            'Altitude vs Time': 'İrtifa - Zaman',
            'Angle': 'Açı',
            'Angle of Attack (weathercock response)': 'Hücum Açısı (rüzgâra dönme tepkisi)',
            'Annular Passage': 'Halka Geçit',
            'Annulus gap': 'Halka boşluğu',
            'Annulus gap (not reported)': 'Halka boşluğu (bildirilmedi)',
            'Apogee': 'Apoje',
            'Area': 'Alan',
            'Atmospheric Pressure': 'Atmosfer Basıncı',
            'Atmospheric Pressure vs Altitude': 'Atmosfer Basıncı - İrtifa',
            'Average Values': 'Ortalama Değerler',
            'Axial Heat Flux & Equilibrium Wall Temperature': 'Eksenel Isı Akısı ve Denge Cidar Sıcaklığı',
            'Axial Mach Number': 'Eksenel Mach Sayısı',
            'Axial Position (mm)': 'Eksenel Konum (mm)',
            'Axial position (mm)': 'Eksenel konum (mm)',
            'Axial position x (mm)': 'Eksenel konum x (mm)',
            'BURNOUT': 'YANMA BİTTİ',
            'Bartz axial profile unavailable — inputs missing': 'Bartz eksenel profili yok — girdiler eksik',
            'Basic Motor Shape': 'Temel Motor Biçimi',
            'Body Diameter (m)': 'Gövde Çapı (m)',
            'Body and swirl-chamber outlines are schematic: the solver reports slot sizes and the exit orifice area, not the housing diameters. Do not machine from this view.': 'Gövde ve girdap odası dış hatları şematiktir: çözücü yuva ölçülerini ve çıkış deliği alanını bildirir, gövde çaplarını değil. Bu görünümden imalat yapmayın.',
            /* V307 DİL-SUNUCU (kalem 5) — PDF belgesinde en sık İngilizce kalan çözücü/güvenlik cümleleri (V306 DİL-SUNUCU devir_rapor_dil_tr.json, vaka >= 7). */
            'Advisory comparison only. It does not change any number HRMA publishes (the design is sized from the HRMA solver alone) and it applies no pass/fail threshold, because no sourced threshold exists for the difference between two equilibrium codes.': 'Yalnız bilgi amaçlı karşılaştırma. HRMA\'nın yayımladığı hiçbir sayıyı değiştirmez (tasarım yalnız HRMA çözücüsüyle boyutlandırılır) ve geçti/kaldı eşiği uygulamaz, çünkü iki denge kodu arasındaki fark için kaynaklı bir eşik yoktur.',
            'NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996) through RocketCEA': 'NASA CEA (Gordon & McBride, NASA RP-1311, 1994/1996), RocketCEA üzerinden',
            'Authorized personnel behind rated barrier': 'Yetkili personel, dayanım sınıfı belgeli bariyerin arkasında',
            'Basic first aid, oxygen, decontamination': 'Temel ilk yardım, oksijen, dekontaminasyon',
            'Essential test crew only': 'Yalnız zorunlu test ekibi',
            'No personnel inside exclusion zone from pressurization to safing': 'Basınçlandırmadan emniyete almaya kadar yasak bölgede personel bulunmaz',
            'No trajectory range is quoted because it depends on drag and attitude, which this model does not solve.;': 'Sürükleme ve duruşa bağlı olduğu için yörünge menzili verilmez; bu model ikisini de çözmez.;',
            'Notify trauma center of potential casualties': 'Olası yaralılar için travma merkezine haber verin',
            'The tie-down must react the thrust with the structural safety factor.': 'Bağlama düzeni itkiyi yapısal emniyet katsayısıyla karşılamalıdır.',
            'confirm against the propellant SDS, current DOT Emergency Response Guidebook guidance and the responsible occupational physician / industrial-hygiene assessment before use': 'kullanmadan önce itici güvenlik bilgi formu (SDS), güncel DOT Acil Müdahale Kılavuzu (ERG) ve sorumlu işyeri hekimi / endüstriyel hijyen değerlendirmesiyle doğrulayın',
            'general emergency-planning checklist - NOT medical advice; every item must be confirmed against the propellant SDS and with the responsible occupational physician before it is relied upon': 'genel acil durum planlama kontrol listesi - tıbbi tavsiye DEĞİLDİR; her madde, güvenilmeden önce itici güvenlik bilgi formuyla ve sorumlu işyeri hekimiyle doğrulanmalıdır',
            'general first-aid checklist - NOT medical advice; this software is not a physician': 'genel ilk yardım kontrol listesi - tıbbi tavsiye DEĞİLDİR; bu yazılım hekim değildir',
            'general hypergolic/toxic handling practice - not tied to a specific standard clause': 'genel hipergolik/zehirli madde elleçleme uygulaması - belirli bir standart maddesine bağlı değildir',
            'generic cube-root mass scaling chosen for this tool - not taken from NFPA or quantity-distance tables; verify against the applicable range safety rules before use': 'bu araç için seçilmiş genel küp kök kütle ölçeklemesi - NFPA\'dan ya da miktar-mesafe tablolarından alınmamıştır; kullanmadan önce geçerli atış alanı emniyet kurallarıyla doğrulayın',
            'shell mass from chamber diameter, length and wall thickness': 'kamara çapı, uzunluğu ve cidar kalınlığından kabuk kütlesi',
            'Standard test-stand PPE (eye/ear protection, flame-resistant clothing)': 'Standart test standı KKD\'si (göz/kulak koruması, aleve dayanıklı giysi)',
            'Free-air spherical TNT peak overpressure, Kinney & Graham, Explosive Shocks in Air, 2nd ed.': 'Serbest havada küresel TNT tepe aşırı basıncı, Kinney & Graham, Explosive Shocks in Air, 2. baskı',
            'Hopkinson-Cranz scaling Z = R / W^(1/3).': 'Hopkinson-Cranz ölçeklemesi Z = R / W^(1/3).',
            'The scaled distance is solved from that correlation for the stated target overpressure, not read from a hand-written table.': 'Ölçeklenmiş mesafe, belirtilen hedef aşırı basınç için bu bağıntıdan çözülür; elle yazılmış bir tablodan okunmaz.',
            'no toxic inventory could be identified for this propellant, so no antidote requirement was determined. This is NOT a statement that no antidote is needed: name the propellant components and consult the propellant SDS and the responsible occupational physician.': 'bu itici için zehirli madde envanteri belirlenemedi, bu yüzden panzehir gereksinimi belirlenmedi. Bu, panzehire gerek olmadığı anlamına GELMEZ: itici bileşenlerini adlandırın, itici güvenlik bilgi formuna ve sorumlu işyeri hekimine danışın.',
            'Water deluge (exposure protection)': 'Su baskını sistemi (komşu yapıların korunması)',
            'Residual grain can reignite from hot surfaces; enforce cooldown': 'Kalan yakıt bloğu sıcak yüzeylerden yeniden tutuşabilir; soğuma süresini zorunlu tutun',
            'Decontaminate (remove clothing, flush 15 min) before transport, Transport with propellant safety data sheet, Observe gas-exposure casualties for delayed symptoms (24-48 h)': 'Taşımadan önce dekontaminasyon yapın (giysileri çıkarın, 15 dk yıkayın), İtici güvenlik bilgi formuyla birlikte taşıyın, Gaza maruz kalan yaralıları gecikmeli belirtiler için gözlem altında tutun (24-48 sa)',
            'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Standard test-stand PPE (eye/ear protection, flame-resistant clothing)': 'Aleve dayanıklı giysi, Kulak ve göz koruması, Mekanik tehlike alanlarında baret, Standart test standı KKD\'si (göz/kulak koruması, aleve dayanıklı giysi)',
            'Activate fire suppression system': 'Yangın söndürme sistemini devreye alın',
            'Sound fire alarm': 'Yangın alarmını çalıştırın',
            'Evacuate upwind': 'Rüzgârın estiği yöne doğru tahliye edin',
            'Call fire department': 'İtfaiyeyi arayın',
            'Prepare for secondary explosions': 'İkincil patlamalara hazırlıklı olun',
            'Allow minimum cooling time before approach': 'Yaklaşmadan önce asgari soğuma süresini bekleyin',
            'Check for unexploded ordnance': 'Patlamamış mühimmat olup olmadığını denetleyin',
            'Document all observations': 'Bütün gözlemleri kayda geçirin',
            'Secure facility and equipment': 'Tesisi ve donanımı emniyete alın',
            'Conduct post-test inspection': 'Test sonrası muayeneyi yapın',
            'Decontaminate (remove clothing, flush 15 min) before transport': 'Taşımadan önce dekontaminasyon yapın (giysileri çıkarın, 15 dk yıkayın)',
            'Transport with propellant safety data sheet': 'İtici güvenlik bilgi formuyla birlikte taşıyın',
            'Observe gas-exposure casualties for delayed symptoms (24-48 h)': 'Gaza maruz kalan yaralıları gecikmeli belirtiler için gözlem altında tutun (24-48 sa)',
            'Documented propellant-handling qualification for operators': 'Operatörler için belgelenmiş itici elleçleme yeterliliği',
            'Test conductor certified on abort procedures': 'Test yöneticisi iptal prosedürlerinde sertifikalı',
            'Annual requalification and emergency drill participation': 'Yıllık yeniden yeterlilik ve acil durum tatbikatına katılım',
            'Don appropriate PPE': 'Uygun KKD\'yi giyin',
            'Evacuate downwind areas': 'Rüzgâr altındaki alanları tahliye edin',
            'Activate gas detection systems': 'Gaz algılama sistemlerini devreye alın',
            'Contact HAZMAT team': 'Tehlikeli madde (HAZMAT) ekibine haber verin',
            'Establish decontamination procedures': 'Dekontaminasyon prosedürlerini başlatın',
            'First aid + burn kit': 'İlk yardım + yanık seti',
            'Emergency shower/eyewash': 'Acil duş/göz yıkama',
            'Backup communications': 'Yedek haberleşme',
            'Fire blankets and extinguishers': 'Yangın battaniyeleri ve söndürücüler',
            'Hot work permit system within exclusion zone': 'Yasak bölgede sıcak çalışma izin sistemi',
            'Bonding/grounding of all transfer equipment': 'Bütün aktarma donanımının eş potansiyel bağlantısı/topraklaması',
            'Non-sparking tools for propellant handling': 'İtici elleçlemede kıvılcım çıkarmayan aletler',
            'ATEX/intrinsically-safe electrical equipment in vapor zones': 'Buhar bölgelerinde ATEX/kendinden güvenli elektrik donanımı',
            'No smoking / no open flame policy with physical enforcement': 'Fiziksel önlemle uygulanan sigara ve açık alev yasağı',
            'Maintain minimum safe distance': 'Asgari güvenli mesafeyi koruyun',
            'Monitor pressure and temperature continuously': 'Basıncı ve sıcaklığı sürekli izleyin',
            'Have abort procedures ready': 'İptal prosedürlerini hazır tutun',
            'Maintain constant communication': 'Kesintisiz haberleşmeyi sürdürün',
            'Document all anomalies immediately': 'Her anomaliyi hemen kayda geçirin',
            'Minimum 2-hour cooling period': 'En az 2 saatlik soğuma süresi',
            'EOD clearance if required': 'Gerekirse patlayıcı imha (EOD) temizliği',
            'Structural damage assessment': 'Yapısal hasar değerlendirmesi',
            'Environmental monitoring complete': 'Çevresel izleme tamamlandı',
            'Remote firing and abort system': 'Uzaktan ateşleme ve iptal sistemi',
            'Blast barrier or berm': 'Patlama bariyeri ya da toprak set',
            'Fixed deluge (per fire analysis)': 'Sabit su baskını sistemi (yangın analizine göre)',
            'Area gas detection (per toxic analysis)': 'Alan gaz algılama (zehirlilik analizine göre)',
            'Sound evacuation alarm immediately': 'Tahliye alarmını hemen çalıştırın',
            'Evacuate to minimum safe distance': 'Asgari güvenli mesafeye tahliye edin',
            'Account for all personnel': 'Bütün personelin sayımını yapın',
            'Contact emergency services': 'Acil servislere haber verin',
            'Establish incident command post': 'Olay komuta noktası kurun',
            'Verify all safety systems functional': 'Bütün emniyet sistemlerinin çalıştığını doğrulayın',
            'Confirm personnel evacuation complete': 'Personel tahliyesinin tamamlandığını teyit edin',
            'Check weather conditions acceptable': 'Hava koşullarının uygun olduğunu denetleyin',
            'Verify emergency response teams ready': 'Acil müdahale ekiplerinin hazır olduğunu doğrulayın',
            'Test communication systems': 'Haberleşme sistemlerini sınayın',
            'Confirm fire suppression systems armed': 'Yangın söndürme sistemlerinin kurulu olduğunu teyit edin',
            'Evacuate to safety distance and account for personnel': 'Güvenli mesafeye tahliye edin ve personelin sayımını yapın',
            'Actuate remote deluge; do NOT approach burning propellant': 'Uzaktan su baskınını çalıştırın; yanan iticiye YAKLAŞMAYIN',
            'Notify fire brigade with propellant data sheet': 'İtfaiyeye itici bilgi formuyla haber verin',
            'Re-enter only after thermal + toxic clearance measurements': 'Yalnız ısıl + zehirlilik temizlik ölçümlerinden sonra yeniden girin',
            'Flame-resistant clothing': 'Aleve dayanıklı giysi',
            'Hearing and eye protection': 'Kulak ve göz koruması',
            'Hard hats in mechanical hazard areas': 'Mekanik tehlike alanlarında baret',
            'Propellant hazards and compatibility training': 'İtici tehlikeleri ve uyumluluk eğitimi',
            'Emergency response and evacuation drills': 'Acil müdahale ve tahliye tatbikatları',
            'Pressure systems safety awareness': 'Basınçlı sistem emniyeti farkındalığı',
            'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn)': 'Yapıları soğutmak için su baskını (not: katı itici yangınları söndürülemez — komşu yapıları koruyun, yanmasına izin verin)',
            'Fixed remote-actuated deluge over test stand': 'Test standı üzerinde uzaktan çalıştırılan sabit su baskını',
            'Rated portable extinguishers at all egress points': 'Bütün çıkış noktalarında sınıfı belgeli seyyar söndürücüler',
            'a fragment mass distribution requires a fragmentation model (Mott/Gurney: case thickness, material ductility, explosive loading ratio), which this module does not solve. The previously published 0.1-1 / 1-10 / 10-100 g bins were a fixed constant identical for every motor, so they were withdrawn rather than presented as an analysis result.': 'parça kütle dağılımı bir parçalanma modeli gerektirir (Mott/Gurney: kasa kalınlığı, malzeme sünekliği, patlayıcı yükleme oranı); bu modül onu çözmez. Önceden yayımlanan 0,1-1 / 1-10 / 10-100 g aralıkları her motor için aynı sabit olduğundan bir analiz çıktısı gibi sunulmak yerine kaldırıldı.',
            'case mass spread uniformly over the disc of radius maximum_range_m: sigma = m_case / (pi * R^2) [kg/m^2]. This is an AREAL MASS density, NOT a fragment COUNT density: this module does not model the fragmentation spectrum, so it cannot say how many pieces land per square metre.': 'kasa kütlesi en büyük menzil yarıçaplı diske düzgün yayılmış kabul edilir: sigma = m_kasa / (pi * R^2) [kg/m^2]. Bu bir ALAN KÜTLE yoğunluğudur, PARÇA ADEDİ yoğunluğu DEĞİLDİR: bu modül parçalanma spektrumunu modellemez, metrekareye kaç parça düştüğünü söyleyemez.',
            'generic sqrt(mass) scaling with tool-chosen coefficients - not an ERG/dispersion-model result': 'araçça seçilmiş katsayılarla genel karekök(kütle) ölçeklemesi - ERG/dağılım modelinin çıktısı değildir',
            'radiant heating can ignite adjacent structures; wide firebreak needed': 'ışınım ısınması komşu yapıları tutuşturabilir; geniş yangın şeridi gerekir',
            'Class A fuel grain + oxidizer-enhanced burning': 'A sınıfı yakıt bloğu + oksitleyiciyle şiddetlenen yanma',
            'Class B (flammable liquid) with oxidizer-enhanced burning': 'B sınıfı (yanıcı sıvı), oksitleyiciyle şiddetlenen yanma',
            'Do not derive a verified delivered-performance claim from this Isp.': 'Bu Isp\'den doğrulanmış bir teslim performansı iddiası çıkarmayın.',
            'Foam (AFFF) on liquid spill; water for cooling': 'Sıvı dökülmesine köpük (AFFF); soğutma için su',
            'HD 1.1 equivalent treatment recommended — mass explosion potential': 'HD 1.1 eşdeğeri işlem önerilir — kütlesel patlama olasılığı',
            'The delivered Isp published by this run carries NO verified two-phase (particle-lag) correction.': 'Bu koşunun yayımladığı teslim Isp\'si doğrulanmış HİÇBİR iki fazlı (parçacık gecikmesi) düzeltme taşımaz.',
            'The tau-choice sensitivity block is NOT published': 'τ seçimi duyarlılık bloğu YAYIMLANMAZ',
            'Vapor accumulation near hot components; ventilate before approach': 'Sıcak bileşenlerin yakınında buhar birikimi; yaklaşmadan önce havalandırın',
            'Cryogenic/toxic liquid transfer procedures (as applicable)': 'Kriyojenik/zehirli sıvı aktarma yöntemleri (uygulanabildiği ölçüde)',
            'Propellant hazards and compatibility training, Emergency response and evacuation drills, Pressure systems safety awareness, Cryogenic/toxic liquid transfer procedures (as applicable)': 'İtici tehlikeleri ve uyumluluk eğitimi, Acil müdahale ve tahliye tatbikatları, Basınçlı sistem emniyeti farkındalığı, Kriyojenik/zehirli sıvı aktarma yöntemleri (uygulanabildiği ölçüde)',
            'Segregate oxidizer and fuel storage': 'Oksitleyici ve yakıt depolamasını ayırın',
            'Grounded, ventilated storage area': 'Topraklanmış, havalandırılan depolama alanı',
            'No ignition sources within exclusion zone': 'Yasak bölge içinde ateşleme kaynağı bulunmasın',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone': 'Oksitleyici ve yakıt depolamasını ayırın, Topraklanmış, havalandırılan depolama alanı, Yasak bölge içinde ateşleme kaynağı bulunmasın',
            'Transport per ADR/DOT dangerous goods rules': 'ADR/DOT tehlikeli madde kurallarına göre taşıma',
            'Documented and placarded load': 'Belgelenmiş ve levhalanmış yük',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load': 'ADR/DOT tehlikeli madde kurallarına göre taşıma, Belgelenmiş ve levhalanmış yük',
            'Condensed-phase anchor window for X_p: 0-0.4 (NASA SP-8039 (1971) Fig. 8 data window: 0-40 wt% condensed metal oxide in exhaust).': 'X_p için yoğuşmuş faz çapa penceresi: 0-0,4 (NASA SP-8039 (1971) Şekil 8 veri penceresi: egzozda kütlece %0-40 yoğuşmuş metal oksit).',
            'This run\'s theoretical numbers ARE NASA CEA (RocketCEA): the table compares them with what HRMA delivers after its loss chain; it is not an independent check of the thermochemistry.': 'Bu koşunun teorik sayıları NASA CEA (RocketCEA) sayılarıdır: tablo bunları HRMA\'nın kayıp zincirinden sonra teslim ettiği değerlerle karşılaştırır; termokimyanın bağımsız bir denetimi değildir.',
            '10 % of the propellant weight': 'itici ağırlığının %10\'u',
            'No specific antidote required — supportive care': 'Özel bir panzehir gerekmez — destekleyici bakım',
            'local spread possible; clear combustibles within safety distance': 'yerel yayılma olası; güvenlik mesafesi içindeki yanıcıları kaldırın',
            'RP-1/LOX (Kerosene/Liquid Oxygen)': 'RP-1/LOX (Kerosen/Sıvı Oksijen)',
            'Foam or CO2 capability for liquid fuel spill fires': 'Sıvı yakıt dökülme yangınları için köpük ya da CO2 donanımı',
            'Water deluge for cooling structures (note: solid propellant fires are not extinguishable — protect exposures and let burn), Foam or CO2 capability for liquid fuel spill fires, Fixed remote-actuated deluge over test stand, Rated portable extinguishers at all egress points': 'Yapıları soğutmak için su baskını (not: katı itici yangınları söndürülemez — komşu yapıları koruyun, yanmasına izin verin), Sıvı yakıt dökülme yangınları için köpük ya da CO2 donanımı, Test standı üzerinde uzaktan çalıştırılan sabit su baskını, Bütün çıkış noktalarında sınıfı belgeli seyyar söndürücüler',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S4): hibrit yakıt bloğu zarf bağıntısı (grain_sizing_rule.formula). */
            'grain outer diameter = final port diameter + 2 × residual web': 'blok dış çapı = son port çapı + 2 × artık et',
            'grain outer diameter = final port diameter × (1 + 1/sin(π/N)) + 2 × residual web': 'blok dış çapı = son port çapı × (1 + 1/sin(π/N)) + 2 × artık et',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S9): hibrit chug döngüsü tau_choice_not_measured.reason. */
            'The tau-choice sensitivity block is NOT published: this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.': 'τ seçimi duyarlılık bloğu YAYIMLANMAZ: bu koşu bu mekanizmaya ait İKİNCİ bir zaman ölçeği çözmedi; döngünün karşılaştırılacağı bir şey yoktu. Bu "ölçülmedi" demektir, "ölçüldü ve duyarsız" DEĞİL — yayımlanan tek τ değeri bütün belirsizliğini hükme, frekansa ve büyüme hızına taşır.',
            /* V307 DİL-SUNUCU (kalem 6): güverte/analiz uçlarının adlı ret cümleleri (app.py 'cannot be produced from …'). */
            'A Monte Carlo reliability figure cannot be produced from physically impossible inputs. Nothing was sampled.': 'Fiziksel olarak olanaksız girdilerle Monte Carlo güvenilirlik değeri üretilemez. Hiçbir örnek çekilmedi.',
            'A flight solution cannot be produced from physically impossible inputs. Nothing was integrated.': 'Fiziksel olarak olanaksız girdilerle uçuş çözümü üretilemez. Hiçbir şey integre edilmedi.',
            'A heat transfer analysis cannot be produced from a non-finite or non-positive wall thickness: the through-wall conduction resistance is undefined. No result was computed.': 'Sonlu olmayan ya da pozitif olmayan cidar kalınlığıyla ısı transferi analizi üretilemez: cidar boyunca iletim direnci tanımsızdır. Sonuç hesaplanmadı.',
            'A heat transfer analysis cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.': 'Varsayılan değerlerle ısı transferi analizi üretilemez. Bu değerler Bartz kütle akısını, geri kazanım sıcaklığını, ıslak alanı ve cidar boyunca iletimi belirler; sizin yerinize varsayılmaz. Eksik değerleri girin.',
            'A quasi-1D nozzle solution cannot be produced from server defaults: the regime, CF, thrust and throat state that this analysis publishes ARE these numbers. The missing fields describe the motor and its operating environment; they cannot be derived from the rest of the request and none was assumed on your behalf. Nothing was solved.': 'Sunucu varsayılanlarıyla yarı-1B nozul çözümü üretilemez: bu analizin yayımladığı rejim, CF, itki ve boğaz durumu TAM OLARAK bu sayılardır. Eksik alanlar motoru ve işletme ortamını tanımlar; isteğin geri kalanından türetilemez ve sizin yerinize hiçbiri varsayılmadı. Hiçbir şey çözülmedi.',
            'A regression curve cannot be produced from defaults. Provide the missing values: they set the time grid, the oxidiser flux and the port growth, so every point of the curve depends on them.': 'Yakıt gerileme eğrisi varsayılan değerlerle üretilemez. Eksik değerleri girin: bunlar zaman ızgarasını, oksitleyici akısını ve port büyümesini belirler; eğrinin her noktası onlara bağlıdır.',
            'A reliability figure cannot be produced from inputs that were not supplied. No defaults were applied and no samples were drawn; the solid motor calculation refuses the same request.': 'Verilmeyen girdilerle güvenilirlik değeri üretilemez. Varsayılan uygulanmadı ve örnek çekilmedi; katı motor hesabı da aynı isteği reddeder.',
            'A safety assessment cannot be produced from defaults. Provide the missing values.': 'Varsayılan değerlerle güvenlik değerlendirmesi üretilemez. Eksik değerleri girin.',
            'A safety assessment cannot be produced from non-finite, non-positive or wrongly typed values. No verdict was computed.': 'Sonlu olmayan, pozitif olmayan ya da yanlış türde değerlerle güvenlik değerlendirmesi üretilemez. Hüküm hesaplanmadı.',
            'A structural assessment cannot be produced from defaults. Provide the missing values.': 'Varsayılan değerlerle yapısal değerlendirme üretilemez. Eksik değerleri girin.',
            'A structural assessment cannot be produced from values that are not numbers. Fix the listed field; nothing was assumed.': 'Sayı olmayan değerlerle yapısal değerlendirme üretilemez. Listelenen alanı düzeltin; hiçbir şey varsayılmadı.',
            'A structural verdict cannot be produced from defaults. None of the fields that define the pressure vessel was supplied, so every safety factor would describe the module\'s own placeholder motor rather than yours. No value was assumed and no analysis was attempted.': 'Varsayılan değerlerle yapısal hüküm üretilemez. Basınçlı kabı tanımlayan alanların hiçbiri verilmedi; bu yüzden her emniyet katsayısı sizin motorunuzu değil, modülün kendi yer tutucu motorunu tanımlardı. Hiçbir değer varsayılmadı ve analiz denenmedi.',
            'A thermal safety verdict cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature, the wetted area and the through-wall conduction; they are not assumed on your behalf. Provide the missing values.': 'Varsayılan değerlerle ısıl güvenlik hükmü üretilemez. Bu değerler Bartz kütle akısını, geri kazanım sıcaklığını, ıslak alanı ve cidar boyunca iletimi belirler; sizin yerinize varsayılmaz. Eksik değerleri girin.',
            'A thermal safety verdict cannot be produced from non-finite or non-positive values. No risk level was computed.': 'Sonlu olmayan ya da pozitif olmayan değerlerle ısıl güvenlik hükmü üretilemez. Risk düzeyi hesaplanmadı.',
            'A thermal safety verdict cannot be produced from that nozzle geometry. The wetted area integral runs over the whole contour, so a malformed contour or two inputs that disagree on the same nozzle are not resolved on your behalf. Fix the listed fields; nothing was computed.': 'Bu nozul geometrisiyle ısıl güvenlik hükmü üretilemez. Islak alan integrali bütün kontur boyunca alınır; bu yüzden bozuk bir kontur ya da aynı nozul için çelişen iki girdi sizin yerinize çözülmez. Listelenen alanları düzeltin; hiçbir şey hesaplanmadı.',
            'A thermal safety verdict cannot be produced from that supplied wall temperature pair. Fix the listed fields; nothing was computed.': 'Verilen cidar sıcaklığı çiftiyle ısıl güvenlik hükmü üretilemez. Listelenen alanları düzeltin; hiçbir şey hesaplanmadı.',
            'A thermal safety verdict cannot be produced from that value. Fix the listed field; no value was assumed and no risk level was computed.': 'Bu değerle ısıl güvenlik hükmü üretilemez. Listelenen alanı düzeltin; hiçbir değer varsayılmadı ve risk düzeyi hesaplanmadı.',
            'An axial wall profile cannot be produced from defaults. These values set the Bartz mass flux, the recovery temperature and the nozzle contour; they are not assumed on your behalf. Provide the missing values.': 'Varsayılan değerlerle eksenel cidar profili üretilemez. Bu değerler Bartz kütle akısını, geri kazanım sıcaklığını ve nozul konturunu belirler; sizin yerinize varsayılmaz. Eksik değerleri girin.',
            'An axial wall profile cannot be produced from non-finite, non-positive or out-of-range values. No profile was computed and no value was assumed.': 'Sonlu olmayan, pozitif olmayan ya da aralık dışı değerlerle eksenel cidar profili üretilemez. Profil hesaplanmadı ve hiçbir değer varsayılmadı.',
            /* V307 DİL-SUNUCU (kalem 6): güverte/analiz uçlarının adlı ret cümleleri (app.py 'cannot be produced from …'). */
            'An uncertainty analysis cannot be produced from defaults: every distribution is centred on a motor input. Provide the motor form fields in "inputs".': 'Belirsizlik analizi varsayılan değerlerle üretilemez: her dağılım bir motor girdisinin çevresinde kurulur. Motor formu alanlarını girin.',
            /* V307 DİL-SUNUCU (kalem 5): PDF belgesinde İngilizce kalan çözücü/güvenlik cümleleri (ek tur). */
            'Class 1 explosives routing and escort requirements apply': 'Sınıf 1 patlayıcı güzergâh ve refakat kuralları uygulanır',
            'Pressure-rated, relief-equipped transport containers': 'Basınca dayanıklı, tahliye vanalı taşıma kapları',
            'Dedicated magazine with quantity-distance siting': 'Miktar-mesafe kuralına göre yerleştirilmiş özel patlayıcı deposu',
            'Secondary containment and leak detection for liquid propellants': 'Sıvı iticiler için ikincil muhafaza ve sızıntı algılama',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply, Pressure-rated, relief-equipped transport containers': 'ADR/DOT tehlikeli madde kurallarına göre taşıma, Belgelenmiş ve levhalanmış yük, Sınıf 1 patlayıcı güzergâh ve refakat kuralları uygulanır, Basınca dayanıklı, tahliye vanalı taşıma kapları',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Class 1 explosives routing and escort requirements apply': 'ADR/DOT tehlikeli madde kurallarına göre taşıma, Belgelenmiş ve levhalanmış yük, Sınıf 1 patlayıcı güzergâh ve refakat kuralları uygulanır',
            'Transport per ADR/DOT dangerous goods rules, Documented and placarded load, Pressure-rated, relief-equipped transport containers': 'ADR/DOT tehlikeli madde kurallarına göre taşıma, Belgelenmiş ve levhalanmış yük, Basınca dayanıklı, tahliye vanalı taşıma kapları',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting, Secondary containment and leak detection for liquid propellants': 'Oksitleyici ve yakıt depolamasını ayırın, Topraklanmış, havalandırılan depolama alanı, Yasak bölge içinde ateşleme kaynağı bulunmasın, Miktar-mesafe kuralına göre yerleştirilmiş özel patlayıcı deposu, Sıvı iticiler için ikincil muhafaza ve sızıntı algılama',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Dedicated magazine with quantity-distance siting': 'Oksitleyici ve yakıt depolamasını ayırın, Topraklanmış, havalandırılan depolama alanı, Yasak bölge içinde ateşleme kaynağı bulunmasın, Miktar-mesafe kuralına göre yerleştirilmiş özel patlayıcı deposu',
            'Half-mask respirator with appropriate cartridge available': 'Uygun filtreli yarım yüz maskesi hazır bulundurulur',
            'Chemical splash goggles and gloves': 'Kimyasal sıçramaya karşı gözlük ve eldiven',
            'Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves': 'Uygun filtreli yarım yüz maskesi hazır bulundurulur, Kimyasal sıçramaya karşı gözlük ve eldiven',
            'Portable detectors for entry teams': 'Giriş ekipleri için taşınabilir dedektörler',
            'Alarm setpoints at 50% of exposure limit': 'Alarm eşikleri maruziyet sınırının %50\'sinde',
            'Fixed gas detection for: n2o, Portable detectors for entry teams, Alarm setpoints at 50% of exposure limit': 'Sabit gaz algılama: n2o, Giriş ekipleri için taşınabilir dedektörler, Alarm eşikleri maruziyet sınırının %50\'sinde',
            'Personal dosimetry/badge sampling for exposed personnel': 'Maruz kalan personel için kişisel dozimetri/rozet örneklemesi',
            'Post-operation area sampling before re-entry': 'Yeniden girişten önce işlem sonrası alan örneklemesi',
            'Medical surveillance program for routine handlers': 'Düzenli çalışanlar için tıbbi gözetim programı',
            'Personal dosimetry/badge sampling for exposed personnel, Post-operation area sampling before re-entry, Medical surveillance program for routine handlers': 'Maruz kalan personel için kişisel dozimetri/rozet örneklemesi, Yeniden girişten önce işlem sonrası alan örneklemesi, Düzenli çalışanlar için tıbbi gözetim programı',
            'Flame-resistant clothing, Hearing and eye protection, Hard hats in mechanical hazard areas, Half-mask respirator with appropriate cartridge available, Chemical splash goggles and gloves': 'Aleve dayanıklı giysi, Kulak ve göz koruması, Mekanik tehlike alanlarında baret, Uygun filtreli yarım yüz maskesi hazır bulundurulur, Kimyasal sıçramaya karşı gözlük ve eldiven',
            'limited to immediate test area': 'yalnız yakın test alanıyla sınırlı',
            'No bias was extrapolated.': 'Hiçbir yanlılık dışdeğerlemesi yapılmadı.',
            'Fresh air, oxygen if hypoxic symptoms': 'Temiz hava; hipoksi belirtisi varsa oksijen',
            'HD 1.3 equivalent — mass fire / minor blast hazard': 'HD 1.3 eşdeğeri — kütlesel yangın / küçük patlama tehlikesi',
            'An unrecognised material is not a default material.': 'Tanınmayan bir malzemenin yerine varsayılan malzeme konmaz.',
            'HD 1.4 equivalent — minor hazard, local effects only': 'HD 1.4 eşdeğeri — küçük tehlike, yalnız yerel etkiler',
            'Worst-case full inventory release, neutral weather (F stability)': 'En kötü durum: bütün envanterin salımı, nötr hava (F kararlılık sınıfı)',
            'Class 1.3-type solid propellant fire (self-oxidized, cannot be smothered)': 'Sınıf 1.3 tipi katı itici yangını (kendi oksitleyicisini taşır, boğularak söndürülemez)',
            'verify against the propellant SDS and current DOT Emergency Response Guidebook guidance': 'iticinin güvenlik bilgi formu (SDS) ve güncel DOT Acil Müdahale Kılavuzu ile doğrulayın',
            'Layer 2, the closeout, covers the channels and carries the coolant pressure as a hoop shell.': 'Katman 2, kapama kabuğu, kanalları örter ve soğutucu basıncını çevresel kabuk olarak taşır.',
            'The band is reported for the coefficient in force, NOT as a validated bias for this oxidizer.': 'Bant, yürürlükteki katsayı için bildiriliyor; bu oksitleyici için DOĞRULANMIŞ bir yanlılık olarak DEĞİL.',
            'The drawn chamber wall is the stack liner + channel depth + closeout; the governing safety factor of the stack is the smaller of the two layers.': 'Çizilen yanma odası cidarı astar + kanal derinliği + kapama kabuğu yığınıdır; yığının belirleyici emniyet katsayısı iki katmanın küçük olanıdır.',
            'Controlled ignition sources only': 'Yalnız denetimli ateşleme kaynakları',
            'Methane/LOX (Liquid Methane/Liquid Oxygen)': 'Metan/LOX (Sıvı Metan/Sıvı Oksijen)',
            'sized by the injector model': 'enjektör modeliyle boyutlandırıldı',
            'the PBAN binder has no closed formula or enthalpy in HRMA': 'PBAN bağlayıcının HRMA\'da kapalı formülü ya da entalpisi yok',
            'single-exponent Saint-Robert law r = a * Pc^n with the coefficients supplied for this propellant': 'tek üslü Saint-Robert yasası r = a · Pc^n, bu itici için verilen katsayılarla',
            '14 CFR Part 420, Appendix E, Table E-5 "Energetic Liquid Explosive Equivalents" (CFR 2024 edition)': '14 CFR Part 420, Ek E, Tablo E-5 "Energetic Liquid Explosive Equivalents" (CFR 2024 baskısı)',
            'M = 1/n (NASA RP-1311 Part I eq. 2.3a): mixture mass per mole of gas, condensed phase included in the mass': 'M = 1/n (NASA RP-1311 Kısım I, Denk. 2.3a): gazın mol başına karışım kütlesi; yoğuşmuş faz kütleye dâhil',
            'NASA CEA (Gordon & McBride, NASA RP-1311) through RocketCEA (CEA2); rocket problem, equilibrium (shifting) composition, infinite-area combustor, condensed species in equilibrium': 'NASA CEA (Gordon & McBride, NASA RP-1311), RocketCEA (CEA2) üzerinden; roket problemi, denge (kayan) bileşimi, sonsuz kesitli yanma odası, dengede yoğuşmuş türler',
            'Isp(vac) at the selected O/F divided by the maximum Isp of this very O/F scan (same solver chain, CEA-anchored); the selected O/F is itself one of the scan points, so the ratio cannot exceed 100%': 'Seçilen O/F\'deki Isp(vak), bu O/F taramasının en büyük Isp\'sine bölünür (aynı çözücü zinciri, CEA\'ya çapalı); seçilen O/F taramanın noktalarından biridir, bu yüzden oran %100\'ü aşamaz',
            'catalogue record (one NASA CEA run at the record pressure); its chamber-pressure dependence is not modelled': 'katalog kaydı (kayıt basıncında tek bir NASA CEA koşusu); yanma odası basıncına bağımlılığı modellenmez',
            'catalogue record convention (see the record source text)': 'katalog kaydı kuralı (kaydın kaynak metnine bakın)',
            '1D station march available for RP-1 regenerative cooling only; the values above come from the Bartz chamber/nozzle integration.': '1B istasyon yürüyüşü yalnız RP-1 rejeneratif soğutması için var; yukarıdaki değerler Bartz yanma odası/nozul integrasyonundan gelir.',
            'TNT = 0.35 x propellant mass (the module default; no sourced factor for this case)': 'TNT = 0,35 × itici kütlesi (modülün varsayılanı; bu durum için kaynaklı katsayı yok)',
            'number of equivalent circular combustion ports actually used by the grain model of this run. It is the value the port gate accepted: zero, negative and fractional inputs are rejected by name rather than silently rounded, and an omitted input means one port.': 'bu koşunun yakıt bloğu modelinin gerçekten kullandığı eşdeğer dairesel yanma portu sayısı. Port kapısının kabul ettiği değerdir: sıfır, negatif ve kesirli girdiler sessizce yuvarlanmak yerine adıyla reddedilir; girilmeyen değer tek port demektir.',
            /* V307 DİL-SUNUCU (kalem 5): PDF belgesinde İngilizce kalan çözücü/güvenlik cümleleri (ek tur). */
            'Let solid propellant burn out; cool surroundings only': 'Katı iticinin yanıp bitmesine izin verin; yalnız çevreyi soğutun',
            'Evacuate to safety distance and account for personnel, Actuate remote deluge; do NOT approach burning propellant, Notify fire brigade with propellant data sheet, Let solid propellant burn out; cool surroundings only, Re-enter only after thermal + toxic clearance measurements': 'Güvenli mesafeye tahliye edin ve personelin sayımını yapın, Uzaktan su baskınını çalıştırın; yanan iticiye YAKLAŞMAYIN, İtfaiyeye itici bilgi formuyla haber verin, Katı iticinin yanıp bitmesine izin verin; yalnız çevreyi soğutun, Yalnız ısıl + zehirlilik temizlik ölçümlerinden sonra yeniden girin',
            'Layer 1, the liner, is the channelled hot-gas wall: its thickness (gas side to channel base) is the hot wall of the thermal chain, and it is checked for the coolant-to-gas pressure difference across the channel span between lands plus the thermal stress through its thickness.': 'Katman 1, astar, kanallı sıcak gaz cidarıdır: kalınlığı (gaz tarafından kanal tabanına) ısıl zincirin sıcak cidarıdır ve kanal sırtları arasındaki açıklık boyunca soğutucu ile gaz arasındaki basınç farkına ve kalınlığı boyunca ısıl gerilmeye göre denetlenir.',
            'Segregate oxidizer and fuel storage, Grounded, ventilated storage area, No ignition sources within exclusion zone, Secondary containment and leak detection for liquid propellants': 'Oksitleyici ve yakıt depolamasını ayırın, Topraklanmış, havalandırılan depolama alanı, Yasak bölge içinde ateşleme kaynağı bulunmasın, Sıvı iticiler için ikincil muhafaza ve sızıntı algılama',
            'isentropic expansion coefficient from the propellant record; the same value the thrust coefficient and expansion-ratio solutions use': 'itici kaydından izantropik genleşme katsayısı; itki katsayısı ve genleşme oranı çözümlerinin kullandığı aynı değer',
            'generic sqrt(mass) scaling with tool-chosen per-component coefficients - not an ERG/dispersion-model result': 'araçça bileşen başına seçilmiş katsayılarla genel karekök(kütle) ölçeklemesi - ERG/dağılım modelinin çıktısı değildir',
            'The published bias body was measured on HTPB/n2o campaigns only': 'Yayımlanan yanlılık gövdesi yalnız HTPB/n2o kampanyalarında ölçüldü',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 4): structural_analysis.py YAPISAL DEĞER KAYNAKLARI defterinin gerekçe hücreleri (SRV); Türkçede makine adı yerine okunur ad. */
            'design_safety_factor_target is the design safety factor you entered (the target). earned_safety_factor is the safety factor the selected or sized thickness actually has. governing_condition names what set that thickness: "stress" - sized by the stress rule to the target, so the earned factor equals the target (times any declared allowance) and the thickness scales with the target; "minimum_thickness" - a manufacturing floor is thicker than the stress rule needs, so the earned factor is above the target and does not scale with it; "user_wall" - your thickness, verified; "standard_size" - the bolt diameter is rounded up to the next ISO 261 size. safety_factor_verdict is FAIL when the earned factor is below the target.': 'Tasarım emniyet katsayısı hedefi, girdiğiniz tasarım emniyet katsayısıdır (hedef). Kazanılan emniyet katsayısı, seçilen ya da boyutlandırılan kalınlığın gerçekte sahip olduğu emniyet katsayısıdır. Belirleyici koşul o kalınlığı neyin belirlediğini söyler: "gerilme" - gerilme kuralıyla hedefe göre boyutlandırıldı, bu yüzden kazanılan katsayı hedefe eşittir (beyan edilen pay varsa onunla çarpılmış) ve kalınlık hedefle ölçeklenir; "asgari kalınlık" - bir imalat alt sınırı gerilme kuralının istediğinden kalındır, bu yüzden kazanılan katsayı hedefin üstündedir ve onunla ölçeklenmez; "kullanıcı cidarı" - sizin kalınlığınız, doğrulandı; "standart boyut" - cıvata çapı bir sonraki ISO 261 boyutuna yukarı yuvarlanır. Kazanılan katsayı hedefin altındaysa emniyet katsayısı hükmü BAŞARISIZ olur.',
            'net axial compression in the pressurised load case: max(thrust compression F/(2*pi*r*t) - internal pressure longitudinal tension p*r/(2t), 0). A value of exactly zero is the clamp, not a missing model: the pressure tension exceeds the axial compression, so this load case cannot buckle the shell and the unpressurised case governs. Both contributors are published next to this field (axial_compression_force_N, pressure_stabilizing_stress_MPa).': 'basınçlı yük durumunda net eksenel basma: max(itki basması F/(2*pi*r*t) - iç basıncın boyuna çekmesi p*r/(2t), 0). Tam sıfır değer eksik model değil, kırpmadır: basınç çekmesi eksenel basmayı aşar, bu yüzden bu yük durumu kabuğu burkamaz ve basınçsız durum belirleyicidir. İki katkı da bu alanın yanında yayımlanır (eksenel basma kuvveti, basıncın dengeleyici gerilmesi).',
            '2:1 ellipsoidal head membrane, inverse of ASME VIII-1 UG-32(d)': '2:1 elipsoidal kapak zarı, ASME VIII-1 UG-32(d) bağıntısının tersi',
            'Both verdicts are evaluated at head_thickness_used_mm with the SAME reference strength (derated yield): flat from the Roark Table 11.2 simply-supported circular plate bending stress, dished from the inverse of ASME VIII-1 UG-32(d) for a 2:1 ellipsoidal head. head_safety_factor is the entry for recommended_type; a layer that manufactures or draws the other type must quote that type entry instead of borrowing this one.': 'İki hüküm de değerlendirilen kapak kalınlığında AYNI referans dayanımla (düşürülmüş akma) verilir: düz kapak Roark Tablo 11.2 basit mesnetli dairesel plaka eğilme gerilmesinden, bombeli kapak 2:1 elipsoidal kapak için ASME VIII-1 UG-32(d) bağıntısının tersinden. Kapak emniyet katsayısı önerilen kapak türünün değeridir; öteki türü üreten ya da çizen bir katman bunu ödünç almak yerine o türün kendi değerini kullanmalıdır.',
            'ESTIMATE: 30% of chamber weight (engineering rule of thumb, not a geometry calculation; the nozzle material is not reflected here)': 'TAHMİN: yanma odası ağırlığının %30\'u (mühendislik başparmak kuralı, geometri hesabı değil; nozul malzemesi burada yansıtılmaz)',
            'Fields the caller did not supply, for which this module applied its own documented default (see STRUCTURAL_INPUT_DEFAULTS). An empty object means every geometry/pressure input below came from the caller. A value that was supplied but is not physical is REJECTED (NonPhysicalStructuralInput), never defaulted.': 'Çağıranın vermediği ve bu modülün kendi belgelenmiş varsayılanını uyguladığı alanlar (bkz. yapısal girdi varsayılanları). Boş bir nesne, aşağıdaki her geometri/basınç girdisinin çağırandan geldiği anlamına gelir. Verilen ama fiziksel olmayan bir değer REDDEDİLİR (fiziksel olmayan yapısal girdi), asla varsayılanla değiştirilmez.',
            'Ground reference for the external-pressure load case: the ISA / U.S. Standard Atmosphere 1976 sea-level pressure, 1.01325 bar (hrma.constants.P_SEA_LEVEL_PA). It is a REFERENCE for the ground scenarios (cooling condensation, closed drain) and is NOT applied automatically; pass it as external_pressure to obtain a verdict.': 'Dış basınç yük durumu için yer referansı: ISA / U.S. Standard Atmosphere 1976 deniz seviyesi basıncı, 1,01325 bar (HRMA deniz seviyesi basıncı sabiti). Yer senaryoları (soğutma yoğuşması, kapalı tahliye) için bir REFERANSTIR ve kendiliğinden UYGULANMAZ; hüküm almak için dış basınç olarak girin.',
            'bolt spacing = pi*D_bolt_circle/n compared with the required bolt diameter; the minimum pitch factor 2.5 is a DECLARED flange practice value (wrench clearance and edge distance; Taylor Forge / ASME VIII-1 App.2 bolted-flange practice), not a calibration constant. Bolt count is chosen from the diameter rule first and only reduced when the layout does not close - the occupied circumference goes like sqrt(n), so fewer, larger bolts fit where many small ones do not. bolt_layout_ok=false means the published pattern does not meet that pitch; bolt_layout_interferes=true means the bolts overlap outright.': 'cıvata aralığı = π·D/n (D: cıvata dairesi çapı), gereken cıvata çapıyla karşılaştırılır; asgari adım katsayısı 2,5 BEYANLI bir flanş uygulama değeridir (anahtar boşluğu ve kenar mesafesi; Taylor Forge / ASME VIII-1 Ek 2 cıvatalı flanş uygulaması), kalibrasyon sabiti değildir. Cıvata sayısı önce çap kuralından seçilir ve yalnız yerleşim kapanmadığında azaltılır - kaplanan çevre sqrt(n) gibi büyür, bu yüzden çok sayıda küçük cıvatanın sığmadığı yere daha az sayıda büyük cıvata sığar. "Cıvata yerleşimi uygun: hayır" yayımlanan düzenin bu adımı sağlamadığını, "cıvatalar çakışıyor: evet" cıvataların doğrudan üst üste bindiğini gösterir.',
            'cylindrical shell volume x material density, using the evaluated wall thickness': 'silindirik kabuk hacmi x malzeme yoğunluğu, değerlendirilen cidar kalınlığıyla',
            'declared design assumption, not derived from throat fillet geometry': 'beyanlı tasarım varsayımı, boğaz köşe yuvarlatması geometrisinden türetilmedi',
            'design pressure = chamber pressure x this design pressure factor. The factor is passed in as a constant by the calling engine, it is NOT computed here and it is NOT the safety_factor entered by the user - it is a separate multiplier that compounds with it (proof/burst pressure margin over MEOP).': 'tasarım basıncı = yanma odası basıncı x bu tasarım basıncı katsayısı. Katsayıyı çağıran motor sabit olarak geçirir; burada HESAPLANMAZ ve kullanıcının girdiği emniyet katsayısı DEĞİLDİR - onunla çarpılarak birleşen ayrı bir çarpandır (MEOP üstünde prova/patlama basıncı payı).',
            'evaluated against the wall HRMA sized in the motor result (not a wall you supplied), at this analysis\'s design pressure': 'motor hesabında HRMA\'nın boyutlandırdığı cidara (sizin verdiğiniz bir cidar değil) bu analizin tasarım basıncında göre değerlendirildi',
            'head_thickness_used_mm is the thickness at which THIS block evaluated the head stress and safety factor; it is NOT a statement about which head thickness goes to manufacturing. The legacy field name says "used"; read it as "evaluated". In size mode it is the sized thickness of recommended_type, in verify mode it is the actual thickness supplied by the caller and then it equals neither sizing output; head_thickness_used_type names which of the two it is ("flat", "dished" or "user_supplied"). A layer that draws, exports or manufactures a specific head type must take that type thickness by name through head_thickness_field_by_type[type] - the CAD/STEP export models a FLAT head and therefore takes flat_head_thickness, which is a different quantity from head_thickness_used_mm whenever recommended_type is "dished" - and must quote head_safety_factor_by_type[type] for the verdict of that same part.': 'Değerlendirilen kapak kalınlığı, BU bloğun kapak gerilmesini ve emniyet katsayısını değerlendirdiği kalınlıktır; hangi kapak kalınlığının imalata gittiğine dair bir beyan DEĞİLDİR. Eski alan adı "kullanılan" der; onu "değerlendirilen" diye okuyun. Boyutlandırma kipinde önerilen kapak türünün boyutlandırılmış kalınlığıdır; doğrulama kipinde çağıranın verdiği gerçek kalınlıktır ve o zaman iki boyutlandırma çıktısının hiçbirine eşit değildir; değerlendirilen kapak türü alanı hangisi olduğunu adlandırır ("düz", "bombeli" ya da "kullanıcının verdiği"). Belirli bir kapak türünü çizen, dışa aktaran ya da üreten bir katman o türün kalınlığını türe göre kapak kalınlığı alanından adıyla almalıdır - CAD/STEP dışa aktarımı DÜZ kapak modeller ve bu yüzden düz kapak kalınlığını alır; bu, önerilen tür "bombeli" olduğunda değerlendirilen kapak kalınlığından farklı bir büyüklüktür - ve aynı parçanın hükmü için türe göre kapak emniyet katsayısını kullanmalıdır.',
            'lowest of all computed safety factors, including the sections HRMA sized itself; it is NOT the number the verdict is drawn from (see verdict_safety_factor)': 'HRMA\'nın kendi boyutlandırdığı kesitler dahil hesaplanan bütün emniyet katsayılarının en düşüğü; hükmün dayandığı sayı DEĞİLDİR (bkz. hükmün dayandığı emniyet katsayısı)',
            'manufacturing allowance constant (structural_analysis.py MANUFACTURING_ALLOWANCE_FACTOR): recommended thickness = minimum thickness x this factor. It is NOT computed from this design and it is NOT a safety factor - it is stock tolerance, machining and corrosion allowance taken from general tube/plate manufacturing practice (ASME BPVC VIII-1 UG-25 corrosion-allowance pattern).': 'imalat payı sabiti (yapısal modülün imalat payı katsayısı): önerilen kalınlık = asgari kalınlık x bu katsayı. Bu tasarımdan HESAPLANMAZ ve bir emniyet katsayısı DEĞİLDİR - genel boru/levha imalat uygulamasından alınan stok toleransı, talaşlı işleme ve korozyon payıdır (ASME BPVC VIII-1 UG-25 korozyon payı deseni).',
            'materials_db recommended design factor for this material - NOT the design safety factor entered by the user': 'bu malzeme için malzeme veritabanının önerdiği tasarım katsayısı - kullanıcının girdiği tasarım emniyet katsayısı DEĞİLDİR',
            'not evaluated: no external-pressure load case was declared. Pass external_pressure (applied ambient pressure, Pa) and internal_pressure_min (lowest internal pressure in that case, Pa) to obtain a verdict. This module does not assume a load case; the ground reference pressure is published as ground_reference_external_pressure_bar for the caller to use deliberately.': 'değerlendirilmedi: dış basınç yük durumu beyan edilmedi. Hüküm almak için dış basıncı (uygulanan ortam basıncı, Pa) ve en düşük iç basıncı (o durumdaki en düşük iç basınç, Pa) girin. Bu modül bir yük durumu varsaymaz; yer referans basıncı, çağıranın bilerek kullanması için yer referansı dış basıncı olarak yayımlanır.',
            'per-station map, SHARP definition: true only when the station was sized by HRMA AND the published factor reads the design target back (factor >= target). A sized station whose factor fell BELOW the target is a measurement (a load the sizing did not cover pulled it down) and is NOT marked tautological. The looser question - "did HRMA pick this wall?" - is published as safety_factor_station_sized_by_hrma and is what the verdict machinery uses (fail-closed).': 'istasyon başına eşlem, KESKİN tanım: yalnız istasyonu HRMA boyutlandırdıysa VE yayımlanan katsayı tasarım hedefini geri okuyorsa (katsayı >= hedef) doğrudur. Katsayısı hedefin ALTINA düşen boyutlandırılmış bir istasyon bir ölçümdür (boyutlandırmanın kapsamadığı bir yük onu aşağı çekti) ve totolojik diye İŞARETLENMEZ. Daha gevşek soru - "bu cidarı HRMA mı seçti?" - istasyonu HRMA boyutlandırdı alanında yayımlanır ve hüküm mekanizması onu kullanır (şüphede hüküm verilmez).',
            'predicted life for the computed stress state (Goodman + Basquin); the design target is design_cycles': 'hesaplanan gerilme durumu için öngörülen ömür (Goodman + Basquin); tasarım hedefi tasarım çevrim sayısıdır',
            'preload physics NOT evaluated: the clamped grip length of the closure joint was not supplied (motor field \'closure_grip_length_m\'). Without it the bolt/member stiffness ratio C is unknown, so joint separation — which is the governing criterion for a preloaded flange — cannot be checked. bolt_safety_factor below is the DESIGN INPUT read back, not a verified capacity.': 'ön yük fiziği DEĞERLENDİRİLMEDİ: kapama bağlantısının sıkıştırılan tutma boyu verilmedi (motor alanı: kapama tutma boyu). O olmadan cıvata/parça rijitlik oranı C bilinmez, bu yüzden ön yüklü bir flanşın belirleyici ölçütü olan bağlantı ayrılması denetlenemez. Aşağıdaki cıvata emniyet katsayısı doğrulanmış bir kapasite değil, TASARIM GİRDİSİNİN geri okunmasıdır.',
            'static tensile sizing only: F_design = SF * P/n over thread stress area, allowable = ISO 898-1 proof stress S_p; preload and separation are NOT modelled here': 'yalnız statik çekme boyutlandırması: F_tasarım = SF * P/n, diş gerilme alanı üstünden; izin verilen = ISO 898-1 prova gerilmesi S_p; ön yük ve ayrılma burada MODELLENMEZ',
            'strength retention interpolated from the material derating_curve (MMPDS / MIL-HDBK-5 Fig. 2.3.1.1.1 pattern)': 'dayanım korunumu malzemenin dayanım düşürme eğrisinden ara değerlendi (MMPDS / MIL-HDBK-5 Şekil 2.3.1.1.1 deseni)',
            'stress ratio R = sigma_min/sigma_max is fixed at zero BY THE CYCLE MODEL, not computed: every firing is treated as one full 0 -> P -> 0 pressure cycle, so the minimum stress is zero. If your duty cycle keeps the chamber pressurised between firings (or preloads it), R is not zero and this Goodman evaluation does not apply.': 'gerilme oranı R = σmin/σmax ÇEVRİM MODELİ GEREĞİ sıfırda sabittir, hesaplanmaz: her ateşleme tam bir 0 -> P -> 0 basınç çevrimi sayılır, bu yüzden en düşük gerilme sıfırdır. Görev çevriminiz yanma odasını ateşlemeler arasında basınçlı tutuyorsa (ya da ön yüklüyorsa) R sıfır değildir ve bu Goodman değerlendirmesi geçerli olmaz.',
            'the stress rule solves the bolt diameter at the target (F_design = SF * P/n over the thread stress area, ISO 898-1 proof stress); the product takes the next ISO 261 coarse-thread size, so the earned factor of the selected bolt is at or above the target unless no standard size is large enough.': 'gerilme kuralı cıvata çapını hedefte çözer (F_tasarım = SF * P/n, diş gerilme alanı üstünden, ISO 898-1 prova gerilmesi); ürün bir sonraki ISO 261 kaba diş boyutunu alır, bu yüzden yeterince büyük standart boyut yoksa dışında seçilen cıvatanın kazanılan katsayısı hedefte ya da üstündedir.',
            'measured wall temperature supplied by the caller (wall_temperature_hot); the service-limit check uses it directly': 'çağıranın verdiği ölçülmüş cidar sıcaklığı (sıcak cidar sıcaklığı); servis sınırı denetimi onu doğrudan kullanır',
            'No gas temperature (chamber_temperature) and no wall temperatures were supplied, so the thermal path did not run. The values previously reported here were the ambient default that marks the thermal model as OFF, not computed wall temperatures. Safety factors above are pressure-only.': 'Gaz sıcaklığı (yanma odası sıcaklığı) ve cidar sıcaklığı verilmedi, bu yüzden ısıl yol koşmadı. Burada daha önce bildirilen değerler ısıl modelin KAPALI olduğunu gösteren ortam varsayılanıydı, hesaplanmış cidar sıcaklıkları değildi. Yukarıdaki emniyet katsayıları yalnız basınçtandır.',
            'no chamber temperature was supplied: the thermal axis is inactive and the ambient temperature is echoed': 'yanma odası sıcaklığı verilmedi: ısıl eksen etkin değil ve ortam sıcaklığı aynen yansıtılır',
            'the motor result\'s own case temperature (hybrid chamber zone protection: grain protection under the grain, insulation liner in the open zones), adopted because the chamber pressure, diameter and wall match the motor result; the gas-temperature estimate is not used, so this tab evaluates the wall at the same temperature the motor sized it at.': 'motor hesabının kendi kasa sıcaklığı (hibrit yanma odası bölge koruması: yakıt bloğunun altında blok koruması, açık bölgelerde yalıtım astarı); yanma odası basıncı, çapı ve cidarı motor hesabıyla eşleştiği için benimsendi; gaz sıcaklığı tahmini kullanılmaz, bu yüzden bu sekme cidarı motorun onu boyutlandırdığı sıcaklıkta değerlendirir.',
            'two-layer regenerative wall (wall_model): safety_factor is the DESIGN TARGET read back (safety_factor_source). hoop_safety_factor is computed on the CLOSEOUT, the layer that carries the coolant pressure: derated yield at the closeout temperature divided by its hoop stress (closeout thickness chosen by HRMA, so it is not a verification of a shell you built). The liner is checked separately (wall_layers); the stack factor is wall_stack_safety_factor.': 'iki katmanlı rejeneratif cidar (cidar modeli): emniyet katsayısı TASARIM HEDEFİNİN geri okunmasıdır (emniyet katsayısı kaynağı). Çember emniyet katsayısı, soğutucu basıncını taşıyan katman olan KAPAMA KABUĞU üstünde hesaplanır: kapama kabuğu sıcaklığındaki düşürülmüş akma, çember gerilmesine bölünür (kapama kabuğu kalınlığını HRMA seçti, bu yüzden sizin ürettiğiniz bir kabuğun doğrulaması değildir). İç astar ayrıca denetlenir (cidar katmanları); katman yığınının katsayısı cidar yığını emniyet katsayısıdır.',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 6, KILAVUZ ÜB-5): sıvı formu Oda Malzemesi künyesi (materials_db source; liquid.html bunu SRV olmadan basıyor, DİL-EKRAN-2). */
            'AK Steel 304/304L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 304 (E, k, cp, alpha, melting range 1400-1450 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).': 'AK Steel 304/304L Ürün Veri Bülteni (oda sıcaklığı + yüksek sıcaklık akma); MatWeb/ASM 304 (E, k, cp, alfa, erime aralığı 1400-1450 C); yorulma ~0,35*UTS, östenitik paslanmaz çelik tasarım uygulaması (ASM Handbook Cilt 19, yaklaşık).',
            'AK Steel 316/316L Product Data Bulletin (RT + elevated temperature yield); MatWeb/ASM 316 (E, k, cp, alpha, melting range 1371-1399 C); fatigue ~0.35*UTS austenitic SS design practice (ASM Handbook Vol. 19, approximate).': 'AK Steel 316/316L Ürün Veri Bülteni (oda sıcaklığı + yüksek sıcaklık akma); MatWeb/ASM 316 (E, k, cp, alfa, erime aralığı 1371-1399 C); yorulma ~0,35*UTS, östenitik paslanmaz çelik tasarım uygulaması (ASM Handbook Cilt 19, yaklaşık).',
            'Mechanical + derating: Special Metals INCONEL alloy 718 datasheet (prior structural table). Thermal: Special Metals 718 datasheet (k=11.4 W/m-K RT, cp=435 J/kg-K, melting range 1260-1336 C).': 'Mekanik + dayanım düşürme: Special Metals INCONEL alloy 718 veri sayfası (önceki yapısal tablo). Isıl: Special Metals 718 veri sayfası (k=11,4 W/m-K oda sıcaklığında, cp=435 J/kg-K, erime aralığı 1260-1336 C).',
            'Special Metals INCONEL alloy 625 datasheet (annealed: Fty ~490 MPa, Ftu ~930 MPa, E 208 GPa, rho 8440, k 9.8 W/m-K RT, cp 410 J/kg-K, melting 1290-1350 C); fatigue ~0.4*UTS approximate; derating from datasheet elevated-temperature yield (approximate). k/cp curves: Special Metals 625 datasheet, approximate.': 'Special Metals INCONEL alloy 625 veri sayfası (tavlanmış: Fty ~490 MPa, Ftu ~930 MPa, E 208 GPa, rho 8440, k 9,8 W/m-K oda sıcaklığında, cp 410 J/kg-K, erime 1290-1350 C); yorulma ~0,4*UTS, yaklaşık; dayanım düşürme veri sayfasının yüksek sıcaklık akma değerlerinden (yaklaşık). k/cp eğrileri: Special Metals 625 veri sayfası, yaklaşık.',
            'Mechanical + derating: MMPDS 6061-T6 (prior structural table). Thermal: ASM Metals Handbook Vol. 2 / MatWeb 6061-T6 (k=167 W/m-K, cp=896 J/kg-K, solidus 582 C); emissivity = sooted/oxidized service surface assumption (conservative for gas-side radiation absorption).': 'Mekanik + dayanım düşürme: MMPDS 6061-T6 (önceki yapısal tablo). Isıl: ASM Metals Handbook Cilt 2 / MatWeb 6061-T6 (k=167 W/m-K, cp=896 J/kg-K, solidus 582 C); yayıcılık = isli/oksitlenmiş servis yüzeyi varsayımı (gaz tarafı ışınım soğurması için muhafazakâr).',
            'Mechanical: ASM Metals Handbook Vol. 2, C10200 annealed (yield ~69 MPa, UTS ~220 MPa, E 117 GPa, fatigue 62 MPa @1e8); derating curve approximate from ASM elevated-temperature copper data. Thermal: prior heat_transfer_analysis table (pure Cu handbook values).': 'Mekanik: ASM Metals Handbook Cilt 2, C10200 tavlanmış (akma ~69 MPa, UTS ~220 MPa, E 117 GPa, yorulma 62 MPa @1e8); dayanım düşürme eğrisi ASM yüksek sıcaklık bakır verisinden, yaklaşık. Isıl: önceki ısı transferi analizi tablosu (saf Cu el kitabı değerleri).',
            'KME Elbrodur G / Luvata CuCr1Zr (C18150) datasheets: aged Rp0.2 >= 310 MPa, Rm >= 400 MPa, E ~128 GPa, k ~320 W/m-K, softening ~475-500 C; fatigue and derating approximate from ITER CuCrZr materials assessments. Regeneratively cooled chamber liner alloy (NASA GRCop analog class). k/cp curves: ITER material property handbook CuCr1Zr (aged), approximate.': 'KME Elbrodur G / Luvata CuCr1Zr (C18150) veri sayfaları: yaşlandırılmış Rp0,2 >= 310 MPa, Rm >= 400 MPa, E ~128 GPa, k ~320 W/m-K, yumuşama ~475-500 C; yorulma ve dayanım düşürme ITER CuCrZr malzeme değerlendirmelerinden, yaklaşık. Rejeneratif soğutmalı yanma odası astar alaşımı (NASA GRCop benzeri sınıf). k/cp eğrileri: ITER malzeme özellikleri el kitabı CuCr1Zr (yaşlandırılmış), yaklaşık.',
            'Mechanical: AZoM/MatWeb AISI 4130 normalized; derating MMPDS/MIL-HDBK-5 Fig. 2.3.1.1.1; alpha ASM Metals Handbook. Thermal: MatWeb AISI 4130 (k, cp, solidus).': 'Mekanik: AZoM/MatWeb AISI 4130 normalize edilmiş; dayanım düşürme MMPDS/MIL-HDBK-5 Şekil 2.3.1.1.1; alfa ASM Metals Handbook. Isıl: MatWeb AISI 4130 (k, cp, solidus).',
            /* V307 DİL-SUNUCU-2 (kalem 2): PDF belgesinde İngilizce kalan çözücü cümleleri, bugünkü kodda birebir duranlar (hibrit/katı/sıvı künyeleri). */
            'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns. DELIVERED quantities come from the N2O self-pressurised tank blowdown solution of this run (tank_blowdown; the same curve the flight is integrated with): total_impulse = total_impulse_delivered_Ns = tank_blowdown.total_impulse_Ns. total_impulse_requested_Ns carries the design intent; constant_oxidizer_flow_budget carries the regulated-feed budget of the same design for comparison.': 'Toplam impuls HER durumda bu koşunun TESLİM EDİLEN impulsudur: her zaman teslim edilen toplam impulsla (N·s) aynı sayıdır. TESLİM EDİLEN büyüklükler bu koşunun N2O kendinden basınçlı tank boşalması çözümünden gelir (tank boşalması; uçuşun integre edildiği eğrinin aynısı): toplam impuls = teslim edilen toplam impuls = tank boşalmasının toplam impulsu. İstenen toplam impuls tasarım amacını taşır; sabit oksitleyici debisi bütçesi aynı tasarımın düzenlenmiş besleme bütçesini karşılaştırma için taşır.',
            'explicit declarations of physics this hybrid solver does NOT compute (roadmap A10; the pattern the liquid and solid engines already follow). Every entry was verified against the code: the named computation exists nowhere in the hybrid chain, and items already declared at their own source (rigid-throat erosion, kinetic-efficiency diagnosis, multi-port equivalent-model warning) are not duplicated here. A missing value is declared as missing, not replaced by a number.': 'bu hibrit çözücünün HESAPLAMADIĞI fiziğin açık beyanları (yol haritası A10; sıvı ve katı motorların zaten izlediği desen). Her kayıt koda karşı doğrulandı: adı geçen hesap hibrit zincirinin hiçbir yerinde yoktur; kendi kaynağında zaten beyan edilen kalemler (rijit boğaz aşınması, kinetik verim tanısı, çok portlu eşdeğer model uyarısı) burada yinelenmez. Eksik bir değer eksik olarak beyan edilir, bir sayıyla değiştirilmez.',
            'ACTUAL free volume in m^3 enclosed by the fuel port plus the pre/post-combustion chambers at the design instant; this is what L*_achieved is computed from.': 'Tasarım anında yakıt portu ile ön/son yanma odalarının çevrelediği GERÇEK serbest hacim, m^3; ulaşılan L* bundan hesaplanır.',
            'CF_vac x Pc x A_t integrated over the same thrust curve as the sea-level impulse (Sutton & Biblarz Eq. 3-30/3-31 with Pa = 0); this is THIS motor\'s fixed nozzle in vacuum, not a vacuum-optimised nozzle. Replaces the empirical log fit that did not see chamber pressure.': 'Deniz seviyesi impulsuyla aynı itki eğrisi üzerinden integre edilen CF(vak) x Pc x At (Sutton & Biblarz Denk. 3-30/3-31, Pa = 0); bu, vakum için eniyilenmiş bir nozul değil, BU motorun vakumdaki sabit nozuludur. Yanma odası basıncını görmeyen eski ampirik logaritmik eğri uyarlamasının yerini alır.',
            'DELIVERED burn-averaged specific impulse of THIS run: total_impulse_delivered_Ns / (propellant_mass_total * g0) with the BIPM standard gravity. The identity I = Isp * m * g0 closes exactly against the two fields named here, so a consumer never has to choose between two descriptions of the same burn. It is NOT the same quantity as the headline isp: that one is the design-point instant (CF * c_star / g0) and belongs to the closed design set (thrust, mdot_total, c_star, cf, isp). The two differ because the O/F of a hybrid drifts as the port regresses; isp_design_point_delta_pct reports that cost as a percentage, and of_shift.regulated carries the whole history. of_shift.regulated.isp_mass_avg_s is this same burn-averaged quantity taken over the solver trapezoid mass (propellant_mass_consumed_kg) instead of the published propellant_mass_total.': 'BU koşunun TESLİM EDİLEN yanma ortalaması özgül impulsu: teslim edilen toplam impuls (N·s) / (toplam itici kütlesi * g0), BIPM standart yerçekimiyle. I = Isp * m * g0 özdeşliği burada adı geçen iki alanla tam kapanır; böylece bir tüketici aynı yanmanın iki tanımı arasında seçim yapmak zorunda kalmaz. Manşetteki Isp ile AYNI büyüklük DEĞİLDİR: o, tasarım noktası anıdır (CF * c* / g0) ve kapalı tasarım kümesine aittir (itki, toplam debi, c*, CF, Isp). İkisi farklıdır, çünkü hibritte port gerilerken O/F kayar; tasarım noktası Isp farkı (%) bu bedeli yüzde olarak verir, düzenlenmiş O/F kayması kaydı da bütün geçmişi taşır. O kaydın kütle ortalamalı Isp değeri, yayımlanan toplam itici kütlesi yerine çözücünün yamuk kuralı kütlesi (tüketilen itici kütlesi) üzerinden alınan aynı yanma ortalaması büyüklüğüdür.',
            'DESIGN TARGET chamber volume in m^3: requested L* times throat area (L* x A_t). NOT the free volume of the built chamber and NOT the gross cylinder swept by the case.': 'TASARIM HEDEFİ yanma odası hacmi, m^3: istenen L* çarpı boğaz alanı (L* x At). Yapılan odanın serbest hacmi DEĞİLDİR ve kasanın süpürdüğü brüt silindir DEĞİLDİR.',
            'burn_time is the burn the motor actually sustains. The steady hybrid design never clips the burn: the grain outer diameter is sized to the final ports, and a chamber diameter too small for the requested burn is rejected by name (grain_envelope_too_small_for_final_ports) instead of publishing a shorter burn. burn_time therefore equals burn_time_requested_s and burn_time_clipped is false in every published design.': 'Yanma süresi, motorun gerçekte sürdürdüğü yanmadır. Kararlı hibrit tasarım yanmayı asla kırpmaz: blok dış çapı son portlara göre boyutlandırılır ve istenen yanma için fazla küçük bir yanma odası çapı, daha kısa bir yanma yayımlamak yerine adıyla reddedilir (blok zarfı son portlar için fazla küçük). Bu yüzden yayımlanan her tasarımda yanma süresi istenen yanma süresine eşittir ve yanma kırpılmış diye işaretlenmez.',
            'oxidizer_mass is the LOADED mass: the tank is sized for the REQUESTED burn time (m_ox = mdot_ox x burn_time_requested_s) because the tank is hardware and does not shrink when the grain runs out early. oxidizer_mass_consumed_kg is what the burn actually uses and oxidizer_mass_residual_kg is the unburnt remainder that flies as dead weight. The mass budget must use the loaded value, the performance budget the consumed one.': 'Oksitleyici kütlesi YÜKLENEN kütledir: tank İSTENEN yanma süresine göre boyutlandırılır (m(oks) = ṁ(oks) x istenen yanma süresi), çünkü tank donanımdır ve blok erken bittiğinde küçülmez. Tüketilen oksitleyici kütlesi yanmanın gerçekte kullandığı kütledir; artık oksitleyici kütlesi ise ölü ağırlık olarak uçan yanmamış kalandır. Kütle bütçesi yüklenen değeri, performans bütçesi tüketileni kullanmalıdır.',
            'propellant_type_source names the INPUT the propellant identity was resolved from; propellant_property_source names the TABLE its thermochemistry was read from. They are provenance declarations, not computed quantities: read them before comparing these results with a reference motor, because a derived identity or an inherited secondary coefficient set is not the same evidence as an explicit selection with its own record.': 'İtici türü kaynağı, itici kimliğinin çözüldüğü GİRDİYİ adlandırır; itici özellik kaynağı, termokimyasının okunduğu TABLOYU adlandırır. Bunlar hesaplanmış büyüklükler değil, köken beyanlarıdır: bu sonuçları bir referans motorla karşılaştırmadan önce okuyun; çünkü türetilmiş bir kimlik ya da devralınmış ikincil katsayı takımı, kendi kaydı olan açık bir seçimle aynı kanıt değildir.',
            'the post-combustion chamber length is clamped to [0.3, 3] x chamber diameter, so the achievable L* of a hybrid is set by the grain port volume and that clamp - NOT by the liquid engine literature band. l_star_achieved is the value this run actually built.': 'son yanma odası boyu [0,3, 3] x yanma odası çapı aralığına kırpılır; bu yüzden bir hibritin ulaşılabilir L* değerini sıvı motor literatür bandı DEĞİL, blok port hacmi ve bu kırpma belirler. Ulaşılan L* bu koşunun gerçekte kurduğu değerdir.',
            'total_impulse = thrust x burn_time: the design thrust (thrust) held for the burn time (burn_time, see burn_time_source), a steady-state constant-thrust burn at the design operating point; start-up and shut-down transients and throttling are not included. The design report, the PDF performance table and safety section and the OpenRocket export read this number.': 'toplam impuls = itki x yanma süresi: tasarım itkisi (itki) yanma süresi boyunca (yanma süresi, bkz. yanma süresi kaynağı) tutulur; tasarım çalışma noktasında kararlı, sabit itkili bir yanmadır; başlangıç ve kapanış geçici durumları ve kısma dahil değildir. Tasarım raporu, PDF performans tablosu ve güvenlik bölümü ile OpenRocket dışa aktarımı bu sayıyı okur.',
            'HRMA\'s theoretical solid thermochemistry (T_c, c*, gamma, M) and its ideal nozzle (optimum area ratio and thrust coefficient) ARE the NASA CEA solution of this composition at this chamber pressure. Equal columns show that the solver uses them unchanged; this is not an independent check of the thermochemistry.': 'HRMA\'nın teorik katı termokimyası (Tc, c*, gamma, M) ve ideal nozulu (en uygun alan oranı ve itki katsayısı) bu bileşimin bu yanma odası basıncındaki NASA CEA çözümünün KENDİSİDİR. Eşit sütunlar, çözücünün bunları değiştirmeden kullandığını gösterir; bu, termokimyanın bağımsız bir denetimi değildir.',
            'NASA CEA equilibrium chamber gamma_s at this chamber pressure (condensed phase included); the nozzle solution is the CEA shifting-equilibrium expansion (see thermochemistry.nozzle)': 'Bu yanma odası basıncında NASA CEA denge oda gaması γs (yoğuşmuş faz dahil); nozul çözümü CEA kayan denge genişlemesidir (bkz. termokimya → nozul)',
            'NASA CEA equilibrium chamber gamma_s at this chamber pressure; CEA did not solve the nozzle, so the thrust coefficient and expansion-ratio solutions use this value in the single-gamma relations': 'Bu yanma odası basıncında NASA CEA denge oda gaması γs; CEA nozulu çözmedi, bu yüzden itki katsayısı ve genişleme oranı çözümleri bu değeri tek-gamma bağıntılarında kullanır',
            'NASA CEA shifting-equilibrium expansion (condensed phase included) to P_e = P_ambient at the design chamber pressure; off-design steps keep the fixed geometry with an equivalent single-gamma exponent gamma_nozzle that reproduces the CEA (P_e/P_c, area ratio) pair and a momentum anchor cf_anchor that reproduces the CEA thrust coefficient': 'Tasarım yanma odası basıncında Pe = P(ortam) olana kadar NASA CEA kayan denge genişlemesi (yoğuşmuş faz dahil); tasarım dışı adımlar sabit geometriyi korur, CEA (Pe/Pc, alan oranı) çiftini yeniden üreten eşdeğer tek-gamma üssünü (nozul gaması) ve CEA itki katsayısını yeniden üreten bir momentum çapasını (itki katsayısı çapası) kullanır',
            'solved: 1D RP-1 regenerative station march (thermal_protection.station_march.coolant_exit_temperature_K)': 'çözüldü: 1B RP-1 rejeneratif istasyon yürüyüşü (ısıl koruma → istasyon yürüyüşü → soğutucu çıkış sıcaklığı)',
            'solved: 1D RP-1 regenerative station march, peak hot-gas-side wall (thermal_protection.station_march.peak_wall_temperature_K)': 'çözüldü: 1B RP-1 rejeneratif istasyon yürüyüşü, sıcak gaz tarafı tepe cidar sıcaklığı (ısıl koruma → istasyon yürüyüşü → tepe cidar sıcaklığı)',
            /* V307 DİL-SON (kalem 8b): bugünkü kodla yeniden üretilen PDF derleminde çevrilemeyen sabit parçalar (k8_pdf_derlem_once.json). */
            'Chug (design point):': 'Chug (tasarım noktası):',
            'Propellant mass loaded basis:': 'Yüklü itici kütlesinin dayanağı:',
            'Nozzle material basis:': 'Nozul malzemesinin dayanağı:',
            'Oxidizer mass inventory basis:': 'Oksitleyici kütle envanterinin dayanağı:',
            'Whether the supplied efficiency really covers the loss is not checked.': 'Verilen verimin bu kaybı gerçekten kapsayıp kapsamadığı denetlenmez.',
            'Supplying a two-phase loss factor applies that factor; leaving the nozzle and kinetic efficiency fields empty applies the built-in estimate on the propellant-table nozzle efficiency.': 'İki fazlı kayıp çarpanı verilirse o çarpan uygulanır; nozul ve kinetik verim alanları boş bırakılırsa yerleşik tahmin, itici tablosunun nozul verimi üzerine uygulanır.',
            'The thrust coefficient therefore carries no separate two-phase factor (two_phase_efficiency_applied = 1.0).': 'Bu yüzden itki katsayısı ayrı bir iki fazlı çarpan taşımaz (uygulanan iki faz verimi = 1,0).',
            'A supplied efficiency is taken to be a delivered (lumped) value that already covers the two-phase loss; applying the built-in estimate on top of it would count that loss twice (measured on the solid page defaults: Isp over theoretical 0.84 with both, against 0.88-0.93 measured on six BATES firings of NASA-CR-158815).': 'Verilen verim, iki fazlı kaybı zaten kapsayan teslim edilmiş (toplu) bir değer kabul edilir; yerleşik tahmini bunun üstüne uygulamak o kaybı iki kez saymak olurdu (katı sayfası varsayılanlarında ölçüldü: ikisi birlikte teorik Isp oranı 0,84; NASA-CR-158815\'in altı BATES ateşlemesinde ölçülen 0,88-0,93).',
            'Jacket pressure drop (single value: feed budget, cycle, cooling)': 'Ceket basınç düşümü (tek değer: besleme bütçesi, çevrim, soğutma)',
            'Jacket pressure drop, bulk Bartz estimate (diagnostic, not used by the feed budget)': 'Ceket basınç düşümü, toplu Bartz tahmini (tanı amaçlı, besleme bütçesinde kullanılmaz)',
            'single-layer wall: the nozzle is the chamber wall carried along the contour, so its material is the chamber material (no separate nozzle material input on the liquid page)': 'tek katmanlı cidar: nozul, kontur boyunca sürdürülen oda cidarıdır; bu yüzden malzemesi oda malzemesidir (sıvı sayfasında ayrı bir nozul malzemesi girdisi yok)',
            'The two disagree: the rule tests only the injector gain dP_inj/Pc, the loop also uses the sensitive time lag and the chamber time constant.': 'İkisi uyuşmuyor: kural yalnız enjektör kazancını (dP_inj/Pc) sınar, çevrim modeli duyarlı zaman gecikmesini ve oda zaman sabitini de kullanır.',
            'cooling_type \'ablative\': HRMA has no wall-temperature solver for a passively cooled wall in this chain (passive_thermal_protection sizes the liner/heat sink, it does not publish an equilibrium wall temperature)': 'soğutma türü \'ablative\': HRMA\'nın bu zincirde pasif soğutulan bir cidar için cidar sıcaklığı çözücüsü yok (pasif ısıl koruma astarı/ısı yutucuyu boyutlandırır, denge cidar sıcaklığı yayımlamaz)',
            'total_impulse is the DELIVERED impulse of this run in EVERY case: it is always the same number as total_impulse_delivered_Ns, never the requested value. total_impulse_requested_Ns carries the design intent (thrust x requested burn time) and the two differ whenever the thrust curve is not perfectly flat (O/F shift as the port opens). Delivered basis: trapz(F(t), t) of this run\'s own thrust curve over [0, burn_time_effective_s].': 'Toplam itki HER durumda bu koşumun TESLİM EDİLEN itkisidir: her zaman teslim edilen toplam itkiyle aynı sayıdır, asla istenen değer değildir. İstenen toplam itki tasarım niyetini taşır (itki x istenen yanma süresi) ve itki eğrisi tam düz olmadığında ikisi ayrışır (port açıldıkça O/F kayması). Teslim dayanağı: bu koşumun kendi itki eğrisinin [0, etkin yanma süresi] aralığındaki trapz(F(t), t) integrali.',
            'this run resolved no SECOND time scale that belongs to this mechanism, so there was nothing to run the loop against. This is "not measured", NOT "measured and insensitive" - the single published tau_s carries its full uncertainty into verdict, frequency_hz and growth_rate_1_s.': 'bu koşum bu mekanizmaya ait İKİNCİ bir zaman ölçeği çözmedi, bu yüzden döngüyü karşısında koşturacak bir şey yoktu. Bu "ölçülmedi" demektir, "ölçüldü ve duyarsız" DEĞİL: yayımlanan tek τ_s, tüm belirsizliğini hükme, frekansa ve büyüme hızına taşır.',
            'LOADED propellant: oxidizer_mass (loaded; in a self-pressurised N2O tank liquid + ullage vapour) + fuel_mass_loaded (the cast grain, unburnt sliver included). propellant_mass_total is a different total: loaded oxidizer + BURNED fuel (fuel_mass).': 'YÜKLÜ itici: oksitleyici kütlesi (yüklü; kendinden basınçlı N2O tankında sıvı + boşluk buharı) + yüklü yakıt kütlesi (dökülmüş tane, yanmayan artık dahil). Toplam itici kütlesi başka bir toplamdır: yüklü oksitleyici + YANAN yakıt (yakıt kütlesi).',
            'oxidizer_type \'n2o\' is not a tabulated class; the hybrid oxidiser \'n2o\' was read from it and selected the \'hybrid_n2o\' class. The equivalence is derived from the oxidiser decomposition enthalpy (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, eq. 2), not from a liquid-bipropellant table: the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence.': 'Oksitleyici türü \'n2o\' tablodaki bir sınıf değil; hibrit oksitleyici \'n2o\' ondan okundu ve hibrit N2O sınıfını seçti. Eşdeğerlik, sıvı çift itici tablosundan değil oksitleyicinin bozunma entalpisinden türetilir (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, denk. 2): hibrit yakıt tanesi oksitleyici taşımaz ve TNT eşdeğerliğine katkı vermez.',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 3): structural_analysis.py burkulma external_pressure_model (YAPISAL burkulma tablosu, SRV). */
            /* V307 DİL-SUNUCU-2: structural_analysis.py thermal_analysis.service_temperature_basis (YAPISAL ısıl not, SRV). */
            'peak (inner-wall) metal temperature; strength derating uses the section-average temperature': 'tepe (iç cidar) metal sıcaklığı; dayanım düşürme kesit ortalaması sıcaklığını kullanır',
            'long-cylinder classical form (length-independent); conservative for short cylinders': 'uzun silindir klasik biçimi (boydan bağımsız); kısa silindirler için muhafazakâr',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 7): thermal_protection.py ABLATIVE_MATERIALS silica_phenolic source (ISIL KORUMA künyesi). */
            'Q* 8-12 MJ/kg literature band, NASA SP-8093 class silica-phenolic ablatives; Sutton & Biblarz 9th ed. Ch. 8.5. Density from central materials_db record \'ablative\' (silica-phenolic class).': 'Q* 8-12 MJ/kg literatür bandı, NASA SP-8093 sınıfı silika-fenolik ablatifler; Sutton & Biblarz 9. baskı, Bölüm 8.5. Yoğunluk merkezi malzeme veritabanının \'ablative\' kaydından (silika-fenolik sınıfı).',
            'Q* 25-30 MJ/kg literature band (high heat-flux carbon-phenolic, NASA SP-8115 class nozzle liners / CPIA data); density ~1450 kg/m3 typical MX-4926 (approximate).': 'Q* 25-30 MJ/kg literatür bandı (yüksek ısı akılı karbon-fenolik, NASA SP-8115 sınıfı nozul astarları / CPIA verisi); yoğunluk ~1450 kg/m3, tipik MX-4926 (yaklaşık).',
            'Q* 4-6 MJ/kg literature band (filled EPDM internal insulation, NASA SP-8093 class); density ~1100 kg/m3 typical aramid/silica-filled EPDM (approximate).': 'Q* 4-6 MJ/kg literatür bandı (dolgulu EPDM iç yalıtım, NASA SP-8093 sınıfı); yoğunluk ~1100 kg/m3, tipik aramid/silika dolgulu EPDM (yaklaşık).',
            /* V307 DİL-SUNUCU (ÜB-3): app.py /analyze_structural_safety design_basis.message (motorun cidarı). */
            'The wall thickness is the wall HRMA sized in the motor result, not a wall you built; it is evaluated here as drawn. This is not a verification of your own wall, and the verdict is the motor\'s own structural verdict when the request matches the motor result.': 'Cidar kalınlığı, HRMA\'nın motor çözümünde boyutlandırdığı cidardır, sizin kurduğunuz bir cidar değildir; burada çizildiği gibi değerlendirilir. Bu, kendi cidarınızın doğrulaması değildir; istek motor çözümüyle örtüşüyorsa hüküm motorun kendi yapısal hükmüdür.',
            'Body tube': 'Gövde tüpü',
            'Bolted Joint — Preload, Torque & Separation (Shigley)': 'Cıvatalı Bağlantı — Ön Yük, Tork ve Ayrılma (Shigley)',
            'Burn Area': 'Yanma alanı',
            'Burn Area & Kn vs Time': 'Yanma Alanı ve Kn - Zaman',
            'Burn Area (cm²)': 'Yanma alanı (cm²)',
            'Burn Rate': 'Yanma hızı',
            'Burn Time (s)': 'Yanma Süresi (s)',
            'Burn rate coefficient': 'Yanma hızı katsayısı',
            'Burn rate exponent': 'Yanma hızı üsteli',
            'Burnout': 'Yanma sonu',
            'CG/CP UNKNOWN': 'AĞIRLIK/BASINÇ MERKEZİ BİLİNMİYOR',
            'COMBUSTION ACTIVE': 'YANMA SÜRÜYOR',
            'Cam': 'Kamera',
            'Cavitation risk detected': 'Kavitasyon riski tespit edildi',
            'Cd₀ (subsonic)': 'Cd₀ (ses altı)',
            'Center': 'Merkez',
            'Centerline': 'Eksen çizgisi',
            'Chamber': 'Yanma odası',
            'Chamber &Oslash;': 'Oda çapı',
            'Chamber Body': 'Oda Gövdesi',
            'Chamber Equilibrium Composition (solver)': 'Oda denge bileşimi (çözücü)',
            'Chamber Length': 'Oda boyu',
            'Chamber Outline': 'Oda Dış Hattı',
            'Chamber Pressure': 'Oda basıncı',
            'Chamber Pressure (bar)': 'Oda basıncı (bar)',
            'Chamber Pressure [bar]': 'Oda basıncı [bar]',
            'Chamber Wall': 'Oda cidarı',
            'Chamber diameter (mm)': 'Oda çapı (mm)',
            'Chamber pressure (bar)': 'Oda basıncı (bar)',
            'Chamber wall': 'Oda cidarı',
            'Chemical Equilibrium': 'Kimyasal Denge',
            'Circuit': 'Devre',
            'Circular': 'Dairesel',
            'Cold-wall T (coolant side)': 'Soğuk cidar sıcaklığı (soğutucu tarafı)',
            'Combustion (c*) Efficiency': 'Yanma (c*) Verimi',
            'Combustion Analysis Dashboard': 'Yanma Analizi Panosu',
            'Combustion Efficiency': 'Yanma verimi',
            'Combustion Efficiency (%)': 'Yanma verimi (%)',
            'Comparative Analysis — Snapshot & Compare Configurations': 'Karşılaştırmalı Analiz — Anlık Görüntü ve Yapılandırma Karşılaştırma',
            'Complete Trajectory Analysis': 'Tam Yörünge Analizi',
            'Component': 'Bileşen',
            'Comprehensive Safety — Risk Assessment & Pressure Vessel': 'Kapsamlı Güvenlik — Risk Değerlendirmesi ve Basınçlı Kap',
            'Compressed Air': 'Basınçlı Hava',
            'Cone angle not reported by the solver (drawn schematically)': 'Koni açısı çözücü tarafından bildirilmedi (şematik çizim)',
            'Configuration': 'Yapılandırma',
            'Consider heat sink or thermal mass for short burns': 'Kısa yanmalar için ısı emici veya termal kütle kullanmayı değerlendirin',
            'Consider higher strength material': 'Daha yüksek dayanımlı malzeme kullanmayı değerlendirin',
            'Consider thermal barrier coating': 'Termal bariyer kaplaması kullanmayı değerlendirin',
            'Convective flux (Bartz, heat-sink wall)': 'Taşınım akısı (Bartz, ısı emici cidar)',
            'Coolant bulk T': 'Soğutucu yığın sıcaklığı',
            'Coolant pressure': 'Soğutucu basıncı',
            'Coolant pressure (bar)': 'Soğutucu basıncı (bar)',
            'Cooling Effectiveness': 'Soğutma Etkinliği',
            'Cooling Jacket': 'Soğutma Ceketi',
            'Core &Oslash;': 'Çekirdek çapı',
            'Core P(x) [bar]': 'Çekirdek P(x) [bar]',
            'Core diameter (mm)': 'Çekirdek çapı (mm)',
            'Counter-clockwise vortex': 'Saat yönünün tersine girdap',
            'Cross-Section View': 'Kesit Görünümü',
            'Cutaway': 'Kesit',
            'Cycles to Failure': 'Kırılmaya Kadar Çevrim Sayısı',
            'Depth from hot face (mm)': 'Sıcak yüzeyden derinlik (mm)',
            'Design Mode': 'Tasarım modu',
            'Design flux at reference cooled wall (conv + radiation)': 'Referans soğutulmuş cidarda tasarım akısı (taşınım + ışınım)',
            'Design point (motor result)': 'Tasarım noktası (motor çıktısı)',
            // V307/GRAFİK-BİRİM (kalem 5): PERFORMANS 3B yüzey künyesi (iz adı, ipucu, not maddeleri).
            'Design point (as supplied)': 'Tasarım noktası (verildiği gibi)',
            "Design (Pc, O/F) at this surface's expansion basis": 'Tasarım (Pc, O/F), bu yüzeyin genleşme tabanında',
            'Design point reported by the motor solver': 'Motor çözücüsünün bildirdiği tasarım noktası',
            'Design point AS SUPPLIED to this figure — the caller did not declare it as a motor-solver result, so it was not re-solved here': 'Bu grafiğe VERİLDİĞİ GİBİ tasarım noktası — çağıran onu motor çözücüsünün çıktısı olarak beyan etmedi; bu yüzden burada yeniden çözülmedi',
            "Design operating point, drawn at THIS SURFACE's basis (optimum / sea-level expansion, Pe = 1 bar) so that its height is comparable with the surface around it": 'Tasarım çalışma noktası; yüksekliği çevresindeki yüzeyle karşılaştırılabilsin diye BU YÜZEYİN tabanında (optimum / deniz seviyesi genleşmesi, Pe = 1 bar) çizildi',
            'Expansion basis NOT checked: the solver did not converge at this node, so the height of this marker is not verified against the surface': 'Genleşme tabanı DENETLENMEDİ: çözücü bu düğümde yakınsamadı; bu yüzden bu işaretin yüksekliği yüzeye göre doğrulanmadı',
            'Combustion-instability bands are NOT modeled here; the earlier shaded band had no sourced criterion and was removed.': 'Yanma kararsızlığı bantları burada MODELLENMEZ; önceki gölgeli bandın kaynaklı bir ölçütü yoktu ve kaldırıldı.',
            'Sea-level expansion (Pe = 1 bar) is used for Isp.': 'Isp için deniz seviyesi genleşmesi (Pe = 1 bar) kullanılır.',
            'Diameter': 'Çap',
            'Dimensions': 'Ölçüler',
            'Download plot as a png': 'Grafiği PNG olarak indir',
            'Dry Mass (kg)': 'Kuru Kütle (kg)',
            'East [m]': 'Doğu [m]',
            'Effectiveness (%)': 'Etkinlik (%)',
            'Efficiency (%)': 'Verim (%)',
            'Equilibrium Isp': 'Denge Isp değeri',
            'Equilibrium wall T': 'Denge cidar sıcaklığı',
            'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.': 'Denge cidar sıcaklığı adyabatik cidar sıcaklığına dayanmış durumda: modellenen soğutma açıkça yetersiz.',
            'Exhaust': 'Egzoz',
            'Exit Orifice': 'Çıkış deliği',
            'Expansion &epsilon;': 'Genişleme &epsilon;',
            'Expansion Ratio &epsilon;': 'Genişleme oranı &epsilon;',
            'Experimental Correlation — Model vs Static-Fire Database': 'Deneysel Korelasyon — Model ve Statik Ateşleme Veri Tabanı',
            'Exploded': 'Patlatılmış',
            'Fallback schematic — the detailed injector view was not available for this run; plate outline is drawn, not computed.': 'Yedek şema — bu koşuda ayrıntılı enjektör görünümü üretilemedi; plaka dış hattı çizilmiştir, hesaplanmamıştır.',
            'Fallback schematic — the solver nozzle contour was not available for this run;': 'Yedek şema — bu koşuda çözücü nozul konturu üretilemedi;',
            'Feed System Pressure Budget': 'Besleme Sistemi Basınç Bütçesi',
            'Feed System Pressure Budget (per circuit)': 'Besleme Sistemi Basınç Bütçesi (devre başına)',
            'Feed System — Slosh, Pressurant & Water Hammer': 'Besleme Sistemi — Çalkantı, Basınçlandırıcı ve Su Koçu',
            'Face pattern': 'Yüz deseni',
            /* V307 DİL-SUNUCU (DİL-HİBRİT S2) — enjektör şeması künye satırları (visualization.py). */
            'Hole positions are a schematic fill of the plate, NOT a drilling layout: the solver publishes the hole count and diameter, not the hole coordinates': 'Delik konumları plakanın şematik bir dolgusudur, delme yerleşimi DEĞİLDİR: çözücü delik koordinatlarını değil, delik sayısını ve çapını yayımlar',
            'Hole count: not reported by the solver — the face layout is NOT drawn': 'Delik sayısı: çözücü bildirmedi — yüz yerleşimi ÇİZİLMEDİ',
            'No hole marks, per-hole flow or total orifice area can be stated without it': 'Bu sayı olmadan delik işareti, delik başına debi ya da toplam delik alanı belirtilemez',
            'Fill ratio h/R': 'Doluluk oranı h/R',
            'Fin Count': 'Kanatçık Sayısı',
            'Fin Root Chord (m)': 'Kanatçık Kök Veteri (m)',
            'Fin Root LE from Nose (m)': 'Kanatçık Kök Hücum Kenarının Burna Uzaklığı (m)',
            'Fin Span (m)': 'Kanatçık Açıklığı (m)',
            'Fin Sweep (m)': 'Kanatçık Ok Açıklığı (m)',
            'Fin Tip Chord (m)': 'Kanatçık Uç Veteri (m)',
            'Final port': 'Son port',
            'Finocyl': 'Kanatlı silindir (finocyl)',
            'Fins': 'Kanatçıklar',
            'Flame Temperature Profile': 'Alev Sıcaklığı Profili',
            'Flange': 'Flanş',
            'Flash boiling risk detected': 'Ani kaynama riski tespit edildi',
            'Flight Path': 'Uçuş Yolu',
            'Flight Phases': 'Uçuş Aşamaları',
            'Flow Annulus': 'Akış halkası',
            'Flow Channel': 'Akış kanalı',
            'Flow Direction': 'Akış yönü',
            'Flow Streamlines': 'Akış Çizgileri',
            'Flow separation (Summerfield)': 'Akış ayrılması (Summerfield)',
            'circular rings (layout only, total area unchanged)':
                'dairesel halkalar (yalnız yerleşim, toplam alan değişmez)',
            'hex lattice (layout only, total area unchanged)':
                'altıgen örgü (yalnız yerleşim, toplam alan değişmez)',
            'square grid (layout only, total area unchanged)':
                'kare ızgara (yalnız yerleşim, toplam alan değişmez)',
            'not reported': 'raporlanmadı',
            'Frequency f1 (Hz)': 'Frekans f1 (Hz)',
            'Fuel': 'Yakıt',
            'Fuel Feed': 'Yakıt Beslemesi',
            'Fuel Grain': 'Yakıt bloğu',
            'Fuel Type Regression Rate Comparison': 'Yakıt Tipine Göre Regresyon Hızı Karşılaştırması',
            'Fuel grain': 'Yakıt bloğu',
            'Full angle': 'Tam açı',
            'GEOMETRY PREVIEW — 3D shape only; performance figures are unchanged. Re-run Calculate to update the analysis.': 'GEOMETRİ ÖNİZLEMESİ — yalnız 3B biçim; performans değerleri değişmez. Analizi güncellemek için Hesapla adımını yeniden çalıştırın.',
            'Grain Length': 'Grain boyu',
            'Grain length (mm)': 'Yakıt bloğu uzunluğu (mm)',
            'Ground Track (North vs East) — drift into wind = weathercock': 'Yer İzi (Kuzey - Doğu) — rüzgâra sürüklenme = rüzgâra dönme',
            'Ground track': 'Yer izi',
            'HRMA prediction [N]': 'HRMA tahmini [N]',
            'Head End': 'Ön kapak',
            'Heat Flux & Coolant Pressure': 'Isı Akısı ve Soğutucu Basıncı',
            'Heat Flux (MW/m2)': 'Isı Akısı (MW/m2)',
            'Heat Map': 'Isı haritası',
            'Heat Map (no data)': 'Isı haritası (veri yok)',
            'Heat Transfer Analysis Dashboard': 'Isı Transferi Analiz Panosu',
            'Heat flux': 'Isı akısı',
            'Heat flux (MW/m²)': 'Isı akısı (MW/m²)',
            'Heat flux q': 'Isı akısı q',
            'Height (m)': 'Yükseklik (m)',
            'High heat load - consider regenerative cooling': 'Yüksek ısı yükü - rejeneratif soğutmayı değerlendirin',
            'Hollow-cone spray': 'İçi boş konik püskürtme',
            'Hot-Face Temperature History': 'Sıcak Yüzey Sıcaklık Geçmişi',
            'Hot-wall T (gas side)': 'Sıcak cidar sıcaklığı (gaz tarafı)',
            'Hybrid Rocket Motor - Axial Cross-Section View': 'Hibrit Roket Motoru - Eksenel Kesit Görünümü',
            'Hybrid Rocket Performance Analysis': 'Hibrit Roket Performans Analizi',
            'Hydrogen Peroxide': 'Hidrojen Peroksit',
            'Impinging pairs (angle not reported)': 'Çarpışmalı çiftler (açı bildirilmedi)',
            'Implement temperature monitoring': 'Sıcaklık izlemesi uygulayın',
            'Improve cooling system': 'Soğutma sistemini iyileştirin',
            'Impulse Efficiency': 'İmpuls verimi',
            'Impulse Efficiency vs Altitude': 'İmpuls Verimi - İrtifa',
            'Included angle': 'Kesişme açısı',
            'Included angle not reported by the solver (drawn schematically)': 'Kesişme açısı çözücü tarafından bildirilmedi (şematik çizim)',
            'Increase chamber wall thickness': 'Oda cidar kalınlığını artırın',
            'Increase wall thickness': 'Cidar kalınlığını artırın',
            'Initial port': 'Başlangıç portu',
            'Inj. inlet': 'Enj. girişi',
            'Inj. ΔP': 'Enj. ΔP',
            'Injection Slot': 'Enjeksiyon yarığı',
            'Injection Velocity': 'Enjeksiyon Hızı',
            'Injection Velocity (m/s)': 'Enjeksiyon Hızı (m/s)',
            'Injector': 'Enjektör',
            'Injector Body': 'Enjektör Gövdesi',
            'Injector Face': 'Enjektör Yüzü',
            'Injector Head': 'Enjektör Başlığı',
            'Injector Plate': 'Enjektör plakası',
            'Injector Pressure': 'Enjektör Basıncı',
            'Injector plate': 'Enjektör plakası',
            'Inner jet': 'İç jet',
            'Inner wall temperature (K)': 'İç cidar sıcaklığı (K)',
            'Iso': 'İzometrik',
            // ÖH D21 / P11B1-06 — 3B güverte Isp çipi referansını söyler.
            'Isp (vacuum)': 'Isp (vakum)',
            'Isp (sea level)': 'Isp (deniz seviyesi)',
            'Isp (design altitude)': 'Isp (tasarım irtifası)',
            'Isp (reference not declared)': 'Isp (referans beyan edilmedi)',
            // V307/KÜÇÜKLER-2 (kalem 3): karşılaştırma figürü Isp ekseni/başlığı ortam satırı (panel.ambient.* ile aynı ifade).
            'sea level': 'deniz seviyesi',
            'vacuum': 'vakum',
            'design ambient not declared by the result': 'tasarım ortamı sonuçta beyan edilmedi',
            'Isp vs O/F (equilibrium sweep)': 'Isp - O/F (denge taraması)',
            'Landing': 'İniş',
            'Landing under parachute': 'Paraşütle iniş',
            'Launch': 'Kalkış',
            'Launch Azimuth (° from N)': 'Kalkış Azimutu (° kuzeyden)',
            'Launch Elevation (°)': 'Kalkış Yükseliş Açısı (°)',
            'Legend min/max are DESIGN loads evaluated at the reference cooled wall (gas_side_analysis.chamber/throat_heat_flux); the flux at the equilibrium wall temperature can come out about 2.5x lower.': 'Efsanedeki min/maks değerler REFERANS SOĞUTULMUŞ CİDARDA değerlendirilen TASARIM yükleridir (gas_side_analysis.chamber/throat_heat_flux); denge cidar sıcaklığındaki akı bundan yaklaşık 2,5 kat düşük çıkabilir.',
            'Length (m)': 'Uzunluk (m)',
            'Length (mm)': 'Uzunluk (mm)',
            'Like-on-like doublet': 'Benzer-benzere çift jet',
            'Liner / annulus': 'Astar / halka boşluğu',
            'Liquid Oxygen': 'Sıvı Oksijen',
            'Liquid Rocket Performance Analysis': 'Sıvı Yakıtlı Roket Performans Analizi',
            'Location': 'Konum',
            'Low pressure drop (<20% of chamber pressure)': 'Düşük basınç düşüşü (oda basıncının %20 altında)',
            'M8 Mounting Hole': 'M8 Montaj Deliği',
            'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY': 'MOTOR EKSENEL KESİTİ — ÇÖZÜCÜ GEOMETRİSİ',
            'MOTOR SIMULATION': 'MOTOR BENZETİMİ',
            'Mach': 'Mach sayısı',
            'Mach Number Distribution': 'Mach Sayısı Dağılımı',
            'Mach field': 'Mach alanı',
            'Mach number': 'Mach sayısı',
            'Mass (kg)': 'Kütle (kg)',
            'Mass Flow': 'Kütle debisi',
            'Mass Flow Rate': 'Kütle debisi',
            'Mass Flow Rate (kg/s)': 'Kütle debisi (kg/s)',
            'Mass Flow Rates': 'Kütle Debileri',
            'Mass Fraction': 'Kütle oranı',
            'Mass Fractions Through Nozzle': 'Nozul Boyunca Kütle Oranları',
            'Mass flow': 'Kütle debisi',
            'Mass vs Isp': 'Kütle - Isp',
            'Mass vs Thickness': 'Kütle - Kalınlık',
            'Material': 'Malzeme',
            'Max Altitude (km)': 'Azami İrtifa (km)',
            'Maximum Altitude (km)': 'Azami irtifa (km)',
            'Maximum Altitude — NOT AVAILABLE (solver did not reach apogee)': 'Azami irtifa — YOK (çözücü apojeye ulaşmadı)',
            'Mole Fraction': 'Mol oranı',
            'Mole fraction': 'Mol kesri',
            'Monitor wall temperature during operation': 'Çalışma sırasında cidar sıcaklığını izleyin',
            'Motor (dry)': 'Motor (kuru)',
            'Motor Burnout': 'Motor Yanma Sonu',
            'Motor Chamber': 'Motor Odası',
            'Motor Configuration Comparison': 'Motor Yapılandırma Karşılaştırması',
            // V307/GRAFİK-BİRİM (kalem 5): karşılaştırma figürünün panel başlıkları.
            'Thrust Comparison': 'İtki Karşılaştırması',
            'Isp Comparison': 'Isp Karşılaştırması',
            'Total Impulse Comparison': 'Toplam İtki Karşılaştırması',
            'Isp vs Total Mass': 'Isp - Toplam Kütle',
            'Motor Outline': 'Motor Dış Hattı',
            'Motor Visualization (Simplified)': 'Motor Görselleştirmesi (Basitleştirilmiş)',
            'Mounting Holes': 'Bağlantı delikleri',
            'Multi-Port': 'Çok portlu',
            'NO BURN TIME SUPPLIED: TIME AXIS NOT DRAWN': 'YANMA SÜRESİ VERİLMEDİ: ZAMAN EKSENİ ÇİZİLMEDİ',
            'NORMAL SHOCK IN NOZZLE': 'NOZULDA NORMAL ŞOK',
            'Natural cooling insufficient - use forced cooling': 'Doğal soğutma yetersiz - zorlanmış soğutma kullanın',
            'Nitrous Oxide': 'Nitröz Oksit',
            'No data available': 'Veri yok',
            'Normal shock (quasi-1D)': 'Dik şok (yarı-1B)',
            'North [m]': 'Kuzey [m]',
            'Nose Length (m)': 'Burun Uzunluğu (m)',
            'Nose Type': 'Burun Tipi',
            'Nose cone': 'Burun konisi',
            'Note: Cryogenic propellants require specialized handling equipment': 'Not: Kriyojenik iticiler özel taşıma ve kullanım ekipmanı gerektirir',
            'Nozzle': 'Nozul',
            'Nozzle Bottom': 'Nozul Altı',
            'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)': 'Nozul Akışı — Yarı-1B Sıkıştırılabilir (Rejim, P(x), M(x), CF)',
            'Nozzle Mach Distribution Analysis': 'Nozul Mach Dağılımı Analizi',
            'Nozzle Mach Number Distribution': 'Nozul Mach Sayısı Dağılımı',
            'Nozzle Profile': 'Nozul Profili',
            'Nozzle Station': 'Nozul istasyonu',
            'Nozzle Top': 'Nozul Üstü',
            'Nozzle wall': 'Nozul cidarı',
            'N₂O Tank Blowdown History': 'N₂O Tankı Boşalma Geçmişi',
            'O/F Ratio': 'O/F oranı',
            'O/F Ratio Optimization': 'O/F Oranı Optimizasyonu',
            'OVEREXPANDED': 'AŞIRI GENİŞLEMİŞ',
            'OVERSTABLE': 'AŞIRI KARARLI',
            'Of Ratio': 'O/F oranı',
            'Operating Point': 'Çalışma Noktası',
            'Orbit': 'Döndür',
            'Orifices': 'Delikler',
            'Outer Body': 'Dış gövde',
            'Outer annulus': 'Dış halka',
            'Ox Tank (required)': 'Oksitleyici tankı (gerekli basınç)',
            'Oxidizer': 'Oksitleyici',
            'Oxidizer Feed': 'Oksitleyici Beslemesi',
            'Oxidizer Injection Velocity': 'Oksitleyici Enjeksiyon Hızı',
            'Oxidizer Mass Flux': 'Oksitleyici kütle akısı',
            'Oxidizer/Fuel': 'Oksitleyici/Yakıt',
            'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT': 'PARAMETRİK 3B MODEL — GEOMETRİ ÇÖZÜCÜ ÇIKTISINDAN CANLI',
            'PERFECT EXPANSION': 'TAM GENİŞLEME',
            'Parachute deploy': 'Paraşüt açılışı',
            'Paraffin Wax': 'Parafin Mumu',
            'Parametric Analysis: Of Ratio Sweep': 'Parametrik Analiz: O/F Oranı Taraması',
            'Parametric Analysis: O/F Ratio Sweep': 'Parametrik Analiz: O/F Oranı Taraması',
            /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 9): app.py create_parametric_plot başlığı ve x ekseni; arayüzün sunduğu üç tarama (O/F, oda basıncı, genişleme oranı). */
            'Parametric Analysis: Chamber Pressure Sweep': 'Parametrik Analiz: Oda Basıncı Taraması',
            'Parametric Analysis: Expansion Ratio Sweep': 'Parametrik Analiz: Genişleme Oranı Taraması',
            'Expansion Ratio': 'Genişleme Oranı',
            'Performance Chart': 'Performans Grafiği',
            'Performance Summary': 'Performans Özeti',
            'Pintle Injector - Cross Section': 'Pintle Enjektör - Kesit',
            'Pintle Post': 'Pintle Mili',
            'Pintle post': 'Pintle mili',
            'Plot data unavailable': 'Grafik verisi yok',
            'Polyethylene': 'Polietilen',
            'Port': 'Port kesiti',
            'Port &Oslash;': 'Port çapı',
            'Port (Final)': 'Port (Son)',
            'Port Diameter': 'Port çapı',
            'Port Diameter (mm)': 'Port çapı (mm)',
            'Port Diameter Growth': 'Port Çapı Büyümesi',
            'Port diameter (mm)': 'Port çapı (mm)',
            'Port growth': 'Port büyümesi',
            'Position': 'Konum',
            'Position (m)': 'Konum (m)',
            'Pressurant': 'Basınçlandırıcı',
            'Pressure': 'Basınç',
            'Pressure (bar)': 'Basınç (bar)',
            'Pressure Distribution': 'Basınç Dağılımı',
            'Pressure Drop': 'Basınç düşüşü',
            'Pressure Drop (bar)': 'Basınç düşüşü (bar)',
            'Pressure Vessel — Sizing, MAWP & Real Burst Pressure': 'Basınçlı Kap — Boyutlandırma, MAWP ve Gerçek Patlama Basıncı',
            'Propellant Mass': 'İtici kütlesi',
            'Propellant Mass (kg)': 'İtici Kütlesi (kg)',
            'Propellant Mass Flow': 'İtici kütle debisi',
            'Propellant Mass vs Of Ratio': 'İtici Kütlesi - O/F Oranı',
            'Propellant Mass vs O/F Ratio': 'İtici Kütlesi - O/F Oranı',
            'Quasi-1D: Mach is uniform across each cross-section — the radial axis shows geometry only, no boundary layer is modeled.': 'Yarı-1B: Mach her kesitte türdeştir — radyal eksen yalnız geometriyi gösterir, sınır tabaka modellenmemiştir.',
            'Radial Position (mm)': 'Radyal Konum (mm)',
            'Radial distance': 'Eksenden uzaklık',
            'Radius (m)': 'Yarıçap (m)',
            'Radius (mm)': 'Yarıçap (mm)',
            'Rail Length (m)': 'Ray Uzunluğu (m)',
            'Range': 'Menzil',
            'Range (km)': 'Menzil (km)',
            // V301/DİL (NK-11): pano canlı ölçüm değil, TASARIM NOKTASIdır
            // (EN başlık sunucu figür metni; EN değer anahtarla aynı kalmalı).
            'Real-Time Motor Performance Dashboard': 'Tasarım Noktası Motor Performans Panosu',
            'Regenerative Cooling — 1D Station March (Bartz + Dittus-Boelter)': 'Rejeneratif Soğutma — 1B İstasyon Yürüyüşü (Bartz + Dittus-Boelter)',
            'Regression Rate': 'Regresyon hızı',
            'Regression Rate & Port Growth': 'Regresyon Hızı ve Port Büyümesi',
            'Regression Rate (mm/s)': 'Regresyon hızı (mm/s)',
            'Regression rate': 'Regresyon hızı',
            'Regression rate (mm/s)': 'Regresyon hızı (mm/s)',
            'Reset View': 'Görünümü sıfırla',
            'S-N Curve': 'S-N Eğrisi',
            'SEPARATED': 'AYRILMIŞ',
            'SHOWERHEAD INJECTOR': 'DUŞ BAŞLIKLI ENJEKTÖR',
            'STABLE': 'KARARLI',
            'STABLE (SLIGHTLY OVERSTABLE)': 'KARARLI (HAFİF AŞIRI KARARLI)',
            'STANDBY': 'BEKLEMEDE',
            'Safety Factor': 'Emniyet Katsayısı',
            'Sample count': 'Örnek sayısı',
            'Severe temperature derating (>30% yield loss): cool wall or change material': 'Ağır sıcaklık kaybı (%30 üzeri akma dayanımı kaybı): cidarı soğutun veya malzemeyi değiştirin',
            'Showerhead': 'Duş başlıklı',
            'Showerhead Injector - Front View': 'Duş Başlıklı Enjektör - Önden Görünüm',
            'Showerhead pattern': 'Duş başlığı deseni',
            'Side': 'Yandan',
            'Slosh': 'Çalkantı',
            'Slosh Frequency & Mass Fraction vs Fill Level': 'Çalkantı Frekansı ve Kütle Oranı - Doluluk Seviyesi',
            'Slosh frequency f1': 'Çalkantı frekansı f1',
            'Slosh mass fraction': 'Çalkantı kütle oranı',
            'Solid Rocket Performance Analysis': 'Katı Yakıtlı Roket Performans Analizi',
            'Sonic — M = 1': 'Ses hızı — M = 1',
            'Spearman rank correlation ρ': 'Spearman sıra korelasyonu ρ',
            'Species': 'Türler',
            'Specific Impulse': 'Özgül itki',
            'Specific Impulse (s)': 'Özgül itki (s)',
            'Specific Impulse vs Altitude': 'Özgül İtki - İrtifa',
            'Specific Impulse vs Of Ratio': 'Özgül İtki - O/F Oranı',
            'Specific Impulse vs O/F Ratio': 'Özgül İtki - O/F Oranı',
            'Spray cone': 'Püskürtme konisi',
            'Spray cone (angle not reported)': 'Püskürtme konisi (açı bildirilmedi)',
            'Star': 'Yıldız',
            'Station': 'İstasyon',
            'Stress (MPa)': 'Gerilme (MPa)',
            'Stress Amplitude (MPa)': 'Gerilme Genliği (MPa)',
            'Structural Analysis Dashboard': 'Yapısal Analiz Panosu',
            'Structural Min SF': 'Yapısal asgari emniyet katsayısı',
            'injector circuit solution': 'enjektör devresi çözümü',
            'Structural Safety — Pressure Vessel, Buckling, Fatigue': 'Yapısal Güvenlik — Basınçlı Kap, Burkulma, Yorulma',
            'Support Arms': 'Destek kolları',
            'Sweep maximum': 'Tarama azamisi',
            'Swirl Chamber': 'Girdap odası',
            'Swirl Direction': 'Girdap Yönü',
            'Swirl Flow Pattern': 'Girdap Akış Deseni',
            'Swirl Flow Region': 'Girdap Akış Bölgesi',
            'Swirl Injector - Face View': 'Girdaplı Enjektör - Önden Görünüm',
            'Swirl Pattern': 'Girdap deseni',
            'Swirl Region': 'Girdap bölgesi',
            'T_wall': 'T_cidar',
            'T_wall inner': 'T_cidar iç',
            'T_wall outer': 'T_cidar dış',
            'Tangential slot (swirl generator)': 'Teğetsel yarık (girdap üreteci)',
            'Tangential slots': 'Teğetsel yarıklar',
            'Tank Pressure [bar]': 'Tank basıncı [bar]',
            'Tank Temperature [K]': 'Tank sıcaklığı [K]',
            'Temperature': 'Sıcaklık',
            'Temperature (K)': 'Sıcaklık (K)',
            'Temperature Distribution (K)': 'Sıcaklık Dağılımı (K)',
            'Temperature by Station (solver)': 'İstasyona göre sıcaklık (çözücü)',
            'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled': 'Termal Koruma — Ablatif / Isı Emici / Işınımla Soğutmalı',
            'Thermal Safety — Bartz Heat Transfer & Wall Temperatures': 'Termal Güvenlik — Bartz Isı Transferi ve Cidar Sıcaklıkları',
            'Thickness': 'Kalınlık',
            'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis': 'İnce cidar varsayımı geçersiz (t/r>=0,1): kalın cidar (Lame) analizi kullanın',
            'Throat': 'Boğaz',
            'Throat &Oslash;': 'Boğaz çapı',
            'Throat Diameter': 'Boğaz çapı',
            'Throat Diameter (mm)': 'Boğaz çapı (mm)',
            'Throat Diameter vs Of Ratio': 'Boğaz Çapı - O/F Oranı',
            'Throat Diameter vs O/F Ratio': 'Boğaz Çapı - O/F Oranı',
            'Throat station': 'Boğaz istasyonu',
            'Thrust': 'İtki',
            'Thrust & Chamber Pressure vs Time': 'İtki ve Oda Basıncı - Zaman',
            'Thrust (N)': 'İtki (N)',
            'Thrust (computed curve)': 'İtki (hesaplanan eğri)',
            'Thrust (computed transient)': 'İtki (hesaplanan geçici rejim)',
            'Thrust (design point, constant-thrust assumption)': 'İtki (tasarım noktası, sabit itki varsayımı)',
            'Thrust Coefficient': 'İtki katsayısı',
            'Thrust Coefficient vs Altitude': 'İtki Katsayısı - İrtifa',
            'Thrust [N]': 'İtki [N]',
            'Thrust vs Altitude': 'İtki - İrtifa',
            'Thrust vs Of Ratio': 'İtki - O/F Oranı',
            'Thrust vs O/F Ratio': 'İtki - O/F Oranı',
            'Time': 'Zaman',
            'Time (s)': 'Zaman (s)',
            'Time [s]': 'Zaman [s]',
            'Total Area': 'Toplam alan',
            'Total Flow': 'Toplam debi',
            'Total Impulse': 'Toplam İtki',
            'Total Impulse (N⋅s)': 'Toplam İtki (N⋅s)',
            'Total Impulse Analysis - Altitude Performance': 'Toplam İmpuls Analizi - İrtifa Performansı',
            'Total Length (m)': 'Toplam Uzunluk (m)',
            'Total Mass (kg)': 'Toplam Kütle (kg)',
            'Total Velocity': 'Toplam Hız',
            'Trajectory Profile': 'Yörünge Profili',
            'Transient': 'Zaman çözümlü',
            'Transient Thrust & Chamber Pressure': 'Zaman Çözümlü İtki ve Oda Basıncı',
            'UNCHOKED': 'BOĞULMAMIŞ AKIŞ',
            'UNDEREXPANDED': 'EKSİK GENİŞLEMİŞ',
            'UNSTABLE / MARGINAL': 'KARARSIZ / SINIRDA',
            'HRMA Hybrid Rocket Motor - 3D CAD Design': 'HRMA Hibrit Roket Motoru - 3B CAD Tasarımı',
            'HRMA Hybrid Rocket Motor - Simplified View': 'HRMA Hibrit Roket Motoru - Basitleştirilmiş Görünüm',
            'Uncertainty Quantification — Monte Carlo Confidence Bands': 'Belirsizlik Niceleme — Monte Carlo Güven Bantları',
            'Use high thermal conductivity materials': 'Yüksek ısı iletkenliğine sahip malzeme kullanın',
            'Use higher temperature material': 'Daha yüksek sıcaklığa dayanıklı malzeme kullanın',
            'User Data Validation — Static-Fire CSV vs HRMA Prediction': 'Kullanıcı Verisi Doğrulama — Statik Ateşleme CSV ve HRMA Tahmini',
            'Velocity': 'Hız',
            'Velocity (m/s)': 'Hız (m/s)',
            'Velocity Magnitude (m/s)': 'Hız Büyüklüğü (m/s)',
            'Velocity Profile': 'Hız Profili',
            'Vertical Velocity': 'Düşey hız',
            'Von Mises Stress (MPa)': 'Von Mises Gerilmesi (MPa)',
            'WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>': 'CİDAR ISI AKISI — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>',
            'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!': 'UYARI: HTPB/ClF3 son derece hipergolik ve tehlikelidir.',
            'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis': 'Oda–Nozul Ekseni Boyunca Cidar ve Soğutucu Sıcaklıkları',
            'Wall Heat Flux Distribution': 'Cidar Isı Akısı Dağılımı',
            'Wall Heat Flux Waterfall Analysis': 'Cidar Isı Akısı Şelale Analizi',
            'Wall P(x) [bar]': 'Cidar P(x) [bar]',
            'Wall Temperature': 'Cidar Sıcaklığı',
            'Wall Temperature Profile at End of Burn': 'Yanma Sonunda Cidar Sıcaklık Profili',
            'Wall Temperatures vs Material Limits': 'Cidar Sıcaklıkları - Malzeme Sınırları',
            'Wall Thickness (mm)': 'Cidar Kalınlığı (mm)',
            'Wall heat flux, heat-sink wall': 'Cidar ısı akısı, ısı emici cidar',
            'Wall temperature (K)': 'Cidar sıcaklığı (K)',
            'Wall temperature approaches melting point': 'Cidar sıcaklığı erime noktasına yaklaşıyor',
            'Wall temperature exceeds allowable limit': 'Cidar sıcaklığı izin verilen sınırı aşıyor',
            'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material': 'Cidar sıcaklığı malzemenin servis sınırına %15 kadar yaklaştı: soğutma ekleyin, yalıtın veya daha yüksek sıcaklığa dayanıklı malzeme seçin',
            'Water Hammer': 'Su koçu',
            'Web Remaining': 'Kalan web',
            'Width (m)': 'Genişlik (m)',
            'Wind From (° from N)': 'Rüzgâr Yönü (° kuzeyden)',
            'Wind Speed (m/s)': 'Rüzgâr Hızı (m/s)',
            'X Position (mm)': 'X konumu (mm)',
            'Y Position (mm)': 'Y konumu (mm)',
            'Your test data [N]': 'Test verileriniz [N]',
            'Zone': 'Bölge',
            'aluminum': 'alüminyum',
            'carbon fiber': 'karbon fiber',
            'nozzle proportions are drawn, not computed.': 'nozul oranları çizilmiştir, hesaplanmamıştır.',
            'outer': 'dış',
            'stainless steel': 'paslanmaz çelik',
            'steel': 'çelik',
            'titanium': 'titanyum',
            'turbine mean diameter withheld: the pitch speed is a clipped bound, so the diameter would only restate that bound.': 'Türbin ortalama çapı geri çekildi: çevresel hız kırpılmış bir sınırdır, dolayısıyla çap yalnızca o sınırı yeniden ifade ederdi.',
            'turbine pitch speed capped below the optimum velocity ratio; stage count estimate is at its validity limit.': 'Türbin çevresel hızı en uygun hız oranının altında sınırlandı; kademe sayısı tahmini geçerlilik sınırındadır.',
            'α [deg]': 'α [derece]',

            /* 2026-08-04 — app.py'nin son Türkçe hata/uyarı borcu EN'e
               çevrildi; TR karşılıkları buradan döner (serverText). */
            'CAD assembly could not be generated': 'CAD montajı üretilemedi',
            'STL generation failed': 'STL üretilemedi',
            'injector design error': 'enjektör tasarım hatası',
            'Required inputs for the solid motor calculation are missing; defaults were not applied and no design was produced.': 'Katı motor hesabı için zorunlu girdiler eksik; varsayılanla doldurulup tasarım üretilmedi.',
            'Geometry mode takes diameter/length/core, design-point mode takes thrust + burn time. For the tutorial scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.': 'Geometri kipinde çap/boy/çekirdek, tasarım noktası kipinde itki + yanma süresi verilir. Öğretici senaryo için "use_tutorial_defaults": true gönderin; sonuç "defaults_applied" alanıyla hangi girdilerin varsayılandan geldiğini beyan eder.',
            'Required inputs for the liquid motor calculation are missing; defaults were not applied and no design was produced.': 'Sıvı motor hesabı için zorunlu girdiler eksik; varsayılanla doldurulup tasarım üretilmedi.',
            'For the tutorial/demo scenario send "use_tutorial_defaults": true; the result declares which inputs came from defaults in the "defaults_applied" field.': 'Öğretici/tanıtım senaryosu için "use_tutorial_defaults": true gönderin; sonuç "defaults_applied" alanıyla hangi girdilerin varsayılandan geldiğini beyan eder.',
            'the model COMPUTES this distance from the impingement angle and hole diameter; see the value in the results': 'model bu mesafeyi çarpışma açısı ve delik çapından HESAPLAR; sonuçtaki değere bakınız',
            'this path models like-on-like doublets; the momentum-ratio criterion applies to unlike impingement': 'bu yol benzer-akışkan (like-on-like) doublet modeller; momentum oranı ölçütü farklı-akışkan çarpışmada geçerlidir',
            'a hybrid injects ONE liquid stream (the oxidizer); the fuel/oxidizer momentum-ratio criterion applies only to unlike (fuel-on-oxidizer) impingement': 'hibrit TEK bir sıvı akım (oksitleyici) enjekte eder; yakıt/oksitleyici momentum oranı ölçütü yalnız farklı-akışkan (yakıta oksitleyici) çarpışmada geçerlidir',
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'model girintiyi iç jet çapından HESAPLAR; sonuçtaki değere bakınız',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'bu yol tek koaksiyel eleman boyutlandırır; çok elemanlı dizilim için Enjektör Tasarımı panelini kullanınız',
            'this path sizes a single coaxial element for the whole oxidizer flow; multi-element arrays are not modelled': 'bu yol bütün oksitleyici debisi için tek bir koaksiyel eleman boyutlandırır; çok elemanlı dizilim modellenmez',

            /* ÖH D35 / OH-GT-19, OH-GT-21, OH-GT-22 (22 Eylül 2026) —
               TÜRKÇE EKRANDA KALAN ÇÖZÜCÜ CÜMLELERİ.
               ÖLÇÜLDÜ: docs/scofield/raw/OH/D35/dil-safligi/a1/once.json
                 GT19  besleme hattı / vana `validity` mesajlarının 6'sı
                       (gerçek /calculate_liquid yanıtı) TR'de İngilizce
                 GT21  gerekçe paragrafları (chug, hüküm künyesi, kütle
                       tanımı) `serverText`ten geçiyor ama karşılığı yok
                 GT22  figür kategori etiketleri, gösterge adı ve enjektör
                       şeması anotasyonları sözlükte hiç yok
               ÇEVİRİ BİREBİR: cümlenin fizik iddiası, sayıları, alan ve
               kaynak adları (F_L, p_v, IEC 60534-2-1, oxidizer_mass_basis)
               DEĞİŞMEZ. */
            'the choked pressure drop dP = F_L^2*(p1 - F_F*p_v) was NOT computed because critical_pressure_Pa was not supplied (the liquid critical pressure ratio factor F_F needs it). Cavitation and flashing WERE screened from the vapour pressure alone; only the choked limit is missing.': 'boğulmuş basınç düşümü dP = F_L^2*(p1 - F_F*p_v) HESAPLANMADI: akışkanın kritik basıncı verilmedi (sıvı kritik basınç oranı çarpanı F_F bunu ister). Kavitasyon ve ani buharlaşma yalnız buhar basıncından TARANDI; eksik olan yalnızca boğulma sınırıdır.',
            'the water-hammer coupling was NOT produced: wall_thickness_m is required, because the wave speed depends on the pipe wall elasticity.': 'su koçu bağlaması ÜRETİLMEDİ: boru cidar kalınlığı zorunludur, çünkü dalga hızı boru cidarının esnekliğine bağlıdır.',
            'the water-hammer coupling was NOT produced: no fluid key was supplied, and no default fluid label is substituted. The wave speed needs a tabulated liquid bulk modulus; pass the propellant\'s own key (or bulk_modulus_Pa with a custom label) to get the coupling.': 'su koçu bağlaması ÜRETİLMEDİ: akışkan anahtarı verilmedi ve yerine varsayılan bir akışkan etiketi KONMAZ. Dalga hızı tablolanmış bir sıvı hacimsel modülü ister; bağlamayı almak için iticinin kendi anahtarını (ya da özel etiketle birlikte bulk_modulus_Pa) geçirin.',
            'the water-hammer coupling was NOT produced: the line budget leaves no usable pressure at the valve, which is where the surge originates. Fix the line sizing first (the valve was not sized either, for the same reason).': 'su koçu bağlaması ÜRETİLMEDİ: hat bütçesi, basınç dalgasının doğduğu yer olan vanada kullanılabilir basınç bırakmıyor. Önce hat boyutlandırmasını düzeltin (aynı sebeple vana da boyutlandırılmadı).',
            'the valve was NOT sized: the line budget leaves no usable inlet pressure at the valve. Fix the line sizing first.': 'vana BOYUTLANDIRILMADI: hat bütçesi vanada kullanılabilir bir giriş basıncı bırakmıyor. Önce hat boyutlandırmasını düzeltin.',
            'non-choked turbulent liquid flow: the full valve pressure drop is used in the sizing equation.': 'boğulmamış türbülanslı sıvı akışı: boyutlandırma denkleminde vananın TAM basınç düşümü kullanılır.',
            'choked/flashing service: the sizing equation is evaluated at the choked pressure drop dP = F_L^2*(p1 - F_F*p_v), because flow stops rising beyond it (IEC 60534-2-1).': 'boğulmuş/ani buharlaşmalı servis: boyutlandırma denklemi boğulmuş basınç düşümünde dP = F_L^2*(p1 - F_F*p_v) değerlendirilir, çünkü akış bunun ötesinde artmaz (IEC 60534-2-1).',
            'flashing service was detected from the vapour pressure, but the sizing equation could NOT be moved to the choked pressure drop because critical_pressure_Pa was not supplied. The Cv below is evaluated at the FULL valve pressure drop and is therefore a LOWER BOUND on the required capacity, not a verified non-choked sizing.': 'ani buharlaşmalı servis buhar basıncından saptandı, ancak boyutlandırma denklemi boğulmuş basınç düşümüne TAŞINAMADI: akışkanın kritik basıncı verilmedi. Aşağıdaki Cv, vananın TAM basınç düşümünde değerlendirilmiştir ve bu yüzden gereken kapasitenin bir ALT SINIRIDIR; doğrulanmış, boğulmamış bir boyutlandırma değildir.',
            'the flow regime was NOT verified: without critical_pressure_Pa the choked limit dP = F_L^2*(p1 - F_F*p_v) cannot be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'akış rejimi DOĞRULANMADI: akışkanın kritik basıncı olmadan boğulma sınırı dP = F_L^2*(p1 - F_F*p_v) değerlendirilemez, dolayısıyla bu boyutlandırmanın boğulmamış olduğu BİLİNMİYOR. Aşağıdaki Cv vananın tam basınç düşümünü kullanır ve vana boğulmuş çıkarsa gereken kapasitenin bir ALT SINIRIDIR.',
            'the flow regime was NOT verified: without vapor_pressure_Pa neither the cavitation index nor the choked limit can be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'akış rejimi DOĞRULANMADI: akışkanın buhar basıncı olmadan ne kavitasyon indisi ne de boğulma sınırı değerlendirilebilir, dolayısıyla bu boyutlandırmanın boğulmamış olduğu BİLİNMİYOR. Aşağıdaki Cv vananın tam basınç düşümünü kullanır ve vana boğulmuş çıkarsa gereken kapasitenin bir ALT SINIRIDIR.',
            'cavitation and flashing were NOT evaluated because vapor_pressure_Pa was not supplied. No safe/unsafe verdict is implied - supply the fluid properties to get one.': 'kavitasyon ve ani buharlaşma DEĞERLENDİRİLMEDİ: akışkanın buhar basıncı verilmedi. Buradan güvenli/güvensiz bir hüküm çıkarılamaz — hüküm için akışkan özelliklerini verin.',
            'A solid motor has no injector and no feed system, so the classical chug criterion (injector pressure drop ratio decoupling the feed from the chamber) has no counterpart here. No injector input is passed to the module: its chug report is NOT_EVALUATED by construction, not because data is missing. The solid-motor low-frequency counterpart (L* / bulk-mode instability) is NOT modelled.': 'Katı motorda enjektör ve besleme sistemi yoktur; bu yüzden klasik chug ölçütünün (beslemeyi odadan ayıran enjektör basınç düşümü oranı) burada bir karşılığı yoktur. Modüle hiçbir enjektör girdisi geçirilmez: chug raporu, veri eksik olduğu için değil, KURULUŞ GEREĞİ değerlendirilmez. Katı motorun alçak frekanslı karşılığı (L* / yığın kip kararsızlığı) MODELLENMEMİŞTİR.',
            'No acceptance is issued: the wall was sized by HRMA to meet the target safety factor, so the reported safety factor is that target read back (target x manufacturing allowance), not an independent verification. Supply the real wall_thickness (m) to obtain a verification. A remaining MARGINAL/UNSAFE status is a warning and is never suppressed.': 'Onay VERİLMEZ: cidarı hedef emniyet katsayısını tutturmak için HRMA\'nın kendisi boyutlandırdı; dolayısıyla bildirilen emniyet katsayısı o hedefin geri okunmasıdır (hedef x imalat payı), bağımsız bir doğrulama değildir. Doğrulama için gerçek cidar kalınlığını (m) girin. Geriye kalan MARGINAL/UNSAFE durumu bir uyarıdır ve asla bastırılmaz.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. Supply \'case_thickness\' (mm) to obtain one. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: gövde cidar kalınlığı verilmedi, bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden kendisi boyutlandırdı. O cidarı denetleyip \'geçti\' demek, tasarım hedefinin geri okunmasıdır; bağımsız bir doğrulama değildir. Doğrulama için gövde cidar kalınlığını (mm) girin. Geriye kalan SINIRDA/BAŞARISIZ durumu bir uyarıdır ve asla bastırılmaz.',
            // V301/T-ÇAPA-D (kalem 1): kap hükmü dayanak cümleleri (katı motor + uç katmanı).
            'No acceptance is issued: the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: kasa cidar sıcaklığı çözülmedi (case_temperature_status); bu yüzden yapısal model bu kasa cidarının sıcaklığına karşı denetlenemez. Bu bloktaki patlama basıncı, patlama payı ve emniyet katsayısı oda sıcaklığındaki kasa dayanımını kullanır; yalnız tanı amaçlı sayılardır, bu kasa cidarının denetimi değildir. \'case_thickness\' göndermek bunu değiştirmez. Geriye kalan SINIRDA/BAŞARISIZ durumu bir uyarıdır ve asla bastırılmaz.',
            'No acceptance is issued: the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: ısı aktarımı modelinin hesapladığı kasa cidar sıcaklığı yapısal modelin geçerlilik sınırının dışında (model_validity_limit_exceeded, model_validity_reasons). Bu bloktaki patlama basıncı, patlama payı ve emniyet katsayısı oda sıcaklığındaki kasa dayanımını kullanır; yalnız tanı amaçlı sayılardır, bu kasa cidarının denetimi değildir. Bu kasa sıcaklığında \'case_thickness\' göndermek bunu değiştirmez. Geriye kalan SINIRDA/BAŞARISIZ durumu bir uyarıdır ve asla bastırılmaz.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature was not solved (case_temperature_status), so the structural model cannot be checked against the temperature of this case wall. The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: gövde cidar kalınlığı verilmedi, bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden kendisi boyutlandırdı. O cidarı denetleyip \'geçti\' demek, tasarım hedefinin geri okunmasıdır; bağımsız bir doğrulama değildir. Ayrıca kasa cidar sıcaklığı çözülmedi (case_temperature_status); bu yüzden yapısal model bu kasa cidarının sıcaklığına karşı denetlenemez. Bu bloktaki patlama basıncı, patlama payı ve emniyet katsayısı oda sıcaklığındaki kasa dayanımını kullanır; yalnız tanı amaçlı sayılardır, bu kasa cidarının denetimi değildir. \'case_thickness\' göndermek bunu değiştirmez. Geriye kalan SINIRDA/BAŞARISIZ durumu bir uyarıdır ve asla bastırılmaz.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. In addition, the case wall temperature computed by the heat-transfer model is outside the validity limit of the structural model (model_validity_limit_exceeded, model_validity_reasons). The burst pressure, burst margin and safety factor in this block use the room-temperature case strength, so they are diagnostic numbers only and not a check of this case wall; sending \'case_thickness\' does not change that at this case temperature. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: gövde cidar kalınlığı verilmedi, bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden kendisi boyutlandırdı. O cidarı denetleyip \'geçti\' demek, tasarım hedefinin geri okunmasıdır; bağımsız bir doğrulama değildir. Ayrıca ısı aktarımı modelinin hesapladığı kasa cidar sıcaklığı yapısal modelin geçerlilik sınırının dışında (model_validity_limit_exceeded, model_validity_reasons). Bu bloktaki patlama basıncı, patlama payı ve emniyet katsayısı oda sıcaklığındaki kasa dayanımını kullanır; yalnız tanı amaçlı sayılardır, bu kasa cidarının denetimi değildir. Bu kasa sıcaklığında \'case_thickness\' göndermek bunu değiştirmez. Geriye kalan SINIRDA/BAŞARISIZ durumu bir uyarıdır ve asla bastırılmaz.',
            'The case wall thickness was supplied by the user, so the burst margin and the vessel status are an evaluation of that wall.': 'Gövde cidar kalınlığını kullanıcı verdi; patlama payı ve kap durumu o cidarın değerlendirmesidir.',
            'The case wall thickness was supplied by the user and is the wall that was evaluated, so the burst margin and the vessel status are an evaluation of that wall.': 'Gövde cidar kalınlığını kullanıcı verdi ve değerlendirilen cidar odur; patlama payı ve kap durumu o cidarın değerlendirmesidir.',
            'LOADED lift-off mass: dry mass + LOADED oxidizer (oxidizer_mass) + LOADED fuel grain (fuel_mass_loaded, which includes the unburnt sliver that flies as dead weight). The mass budget uses loaded values; the performance budget uses the consumed ones (fuel_mass, oxidizer_mass_consumed_kg) - same rule as oxidizer_mass_basis.': 'YÜKLÜ kalkış kütlesi: kuru kütle + YÜKLÜ oksitleyici kütlesi + YÜKLÜ yakıt tanesi kütlesi (yanmadan ölü ağırlık olarak uçan artık dilim de içindedir). Kütle bütçesi yüklü değerleri, başarım bütçesi tüketilen yakıt ve oksitleyici kütlelerini kullanır — oksitleyici kütlesi dayanağıyla aynı kural.',
            'The analysis reported that it does not apply, but named no reason.': 'Analiz, uygulanamadığını bildirdi ama bunun sebebini adlandırmadı.',
            'Total': 'Toplam',
            'Peak': 'Tepe',
            'Average': 'Ortalama',
            'Design Pc': 'Tasarım Pc',
            'Exit': 'Çıkış',
            'Tank Outlet': 'Tank çıkışı',
            'Main Valve': 'Ana vana',
            'Filters (assumed K=10)': 'Filtreler (K=10 kabul edildi)',
            // ÖH A2 sivi-sogutma · 7. tur: sıvı 'Pressure Distribution'
            // çubuk kategorileri (visualization._perf_panels_liquid).
            'Feed': 'Besleme',
            'Feed (Fuel)': 'Besleme (yakıt)',
            'Feed (Ox)': 'Besleme (oksitleyici)',
            'Feed Lines': 'Besleme hatları',
            // V301/L-REJ (NK-36): rejeneratif ceket kalemi — anahtar bu
            // sözlükte zaten 'Soğutma Ceketi' olarak vardı (ikinci tanım kaldırıldı).
            'This run (solver)': 'Bu koşum (çözücü)',
            'injector plate': 'enjektör plakası',
            'parallel axial jets': 'paralel eksenel jetler',
            'feed manifold': 'besleme manifoldu',
            'included angle 2θ': 'dâhil açı 2θ',
            'impingement point': 'çarpışma noktası',
            'flat spray fan': 'düz püskürtme yelpazesi',
            'chamber side →': 'oda tarafı →',
            'dP → jet velocity': 'dP → jet hızı',
            'Showerhead injector plate': 'Duş başlıklı enjektör plakası',
            'Pintle injector': 'Pintle enjektör',
            'Swirl injector plate': 'Girdaplı enjektör plakası',
            'Impinging-jet injector plate': 'Çarpışmalı jet enjektör plakası',
            'Coaxial injector plate': 'Koaksiyel enjektör plakası',
            /* ÖH D36 / dil2-i18n-pdf a2 (K4) — güvenlik panelinin patlayıcı
               ve toksik hüküm künyesi (safety_panel.js explosiveBasisBlock /
               toxicBasisBlock) sunucu cümlelerini serverText üzerinden basar.
               Cümleler hrma/analysis/safety_analysis.py:1539 (requirements_scope),
               :1615 (toxic_hazard_level_withheld_because), toksik envanter
               sınıflandırıcısı (tanınmayan sınıf) ve app.py _lift_toxic_basis
               (_basis) ile BİREBİR; üretici cümleyi değiştirirse eşleşme düşer
               ve metin İngilizce AYNEN kalır (uydurma çeviri yok). */
            'Unconditional items only: the TNT-threshold items (magazine siting, Class 1 routing) are withheld with the explosive verdict.': 'Yalnız koşulsuz maddeler yayımlandı: TNT eşiğine bağlı maddeler (magazin yerleşimi, Sınıf 1 güzergâhı) patlayıcı hükmüyle birlikte geri çekildi.',
            'No toxic inventory could be identified for this propellant, so no toxic hazard level was computed. A hazard that was not assessed is not an absent hazard.': 'Bu itici için toksik envanter belirlenemedi, bu yüzden toksik tehlike seviyesi hesaplanmadı. Değerlendirilmemiş bir tehlike, olmayan bir tehlike değildir.',
            'where the toxic verdict came from: which propellant class the request resolved to, whether an inventory could be identified for it, and why. A level of NOT_EVALUATED means no toxic hazard was assessed - it does NOT mean there is no toxic hazard.': 'toksik hükmün kaynağı: istek hangi itici sınıfına çözüldü, o sınıf için envanter belirlenebildi mi ve neden. NOT_EVALUATED seviyesi hiçbir toksik tehlikenin değerlendirilmediği anlamına gelir; toksik tehlike olmadığı anlamına GELMEZ.',
            'propellant_type did not resolve to any propellant class HRMA has a toxic inventory rule for, so no toxic inventory was identified. An unidentified propellant is not a non-toxic propellant: no toxic hazard level is published for it.': 'propellant_type, HRMA\'nın toksik envanter kuralı bulunan hiçbir itici sınıfına çözülmedi; bu yüzden toksik envanter belirlenmedi. Tanımlanamayan bir itici, toksik olmayan bir itici değildir: onun için toksik tehlike seviyesi yayımlanmaz.',
            /* ÖH D37 · A1b dil-cozucu-nesri — çözücü nesri (DV36-02, DV36-03,
               DV-GT21, DV36-21, DV-MIXED). Cümleler üreticinin kendi
               dizeleriyle BİREBİR (dosya:satır kalem yorumlarında,
               tests/test_d37_dil_b1.py üreticiden okur); üretici değişirse
               eşleşme düşer ve metin İngilizce AYNEN kalır. */
            'Solver warnings for this injector': 'Bu enjektör için çözücü uyarıları',
            'liquid monopropellant: the hydrazine family (MMH / UDMH / N2H4) is inventoried from the tabulated exposure limits.': 'sıvı tek itici: hidrazin ailesi (MMH / UDMH / N2H4) tablolanmış maruziyet sınırlarından envantere alınır.',
            'the hybrid fuel grain carries no oxidiser and contributes no TNT equivalence': 'hibrit yakıt bloğu oksitleyici taşımaz ve TNT eşdeğerine katkı yapmaz',
            'time-marching solution: F = mdot_total(t)*Isp(t)*g0, Pc = mdot_total(t)*c_star(t)/(Cd*At) with the same throat discharge coefficient the throat was sized with (single C_D contract: the mass flow carries Cd, the throat area is geometric); oxidiser flow is constant, fuel flow follows the regressing port': 'zaman adımlı çözüm: F = mdot_total(t)*Isp(t)*g0, Pc = mdot_total(t)*c_star(t)/(Cd*At); boğaz hangi boşaltma katsayısıyla boyutlandırıldıysa aynısı kullanılır (tek C_D sözleşmesi: kütle debisi Cd taşır, boğaz alanı geometriktir); oksitleyici debisi sabittir, yakıt debisi gerileyen portu izler',
            'Self-pressurised N2O tank blowdown solution of this run: tank pressure, oxidiser flow, chamber pressure and thrust fall during the burn. This is the delivered curve the flight integrates; its trapezoidal integral is the published total impulse. The curve starts at t = 0 with the ignition state and each solver step is integrated once. The constant-oxidiser-flow design curve is published separately for comparison.': 'Bu koşunun kendinden basınçlı N2O tankı boşalma çözümü: yanma boyunca tank basıncı, oksitleyici debisi, oda basıncı ve itki düşer. Uçuşun entegre ettiği teslim eğrisidir; yamuk integrali yayımlanan toplam impulstur. Eğri t = 0 anında ateşleme durumuyla başlar ve her çözücü adımı bir kez entegre edilir. Sabit oksitleyici debili tasarım eğrisi karşılaştırma için ayrıca yayımlanır.',
            'solid grain burn-back solver (time-marched): burn area from grain regression, chamber pressure from the iterative pressure-burn rate fixed point (r = a*Pc^n)': 'katı yakıt bloğu geri yanma çözücüsü (zaman adımlı): yanma alanı blok gerilemesinden, oda basıncı yinelemeli basınç-yanma hızı sabit noktasından (r = a*Pc^n)',
            'the O/F-ratio extremes and the specific-impulse extremes': 'O/F oranının uç değerleri ve özgül itkinin uç değerleri',
            'the first samples of flow separation, of loss of choking and of burnout': 'akış ayrılmasının, boğulma kaybının ve yanma sonunun ilk örnekleri',
            'total impulse, burn time, average thrust, O/F shift statistics, warnings': 'toplam itki, yanma süresi, ortalama itki, O/F kayması istatistikleri, uyarılar',
            'time-averaged c*, time-averaged Isp, O/F shift statistics': 'zaman ortalamalı c*, zaman ortalamalı Isp, O/F kayması istatistikleri',
            'total impulse, average thrust, curve shape, stability, warnings': 'toplam itki, ortalama itki, eğri biçimi, kararlılık, uyarılar',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + nozzle. SCOPE LIMITS: the nozzle share is a 30%-of-chamber rule of thumb (see nozzle_weight_basis), and the injector is NOT included. The CAD mass breakdown (cad_design.performance_summary.mass_breakdown.total_dry_mass) is a DIFFERENT total: it uses the as-drawn nozzle and the injector but omits the closures, so the two do not agree.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: yapısal analizin toplam ağırlığı = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + nozul. KAPSAM SINIRLARI: nozul payı kamaranın %30\'u kadar alınan bir başparmak kuralıdır (bkz. nozul ağırlığı dayanağı) ve enjektör DAHİL DEĞİLDİR. CAD kütle dökümünün kuru toplamı FARKLI bir toplamdır: çizilen nozulu ve enjektörü kullanır ama uç kapaklarını dışarıda bırakır; bu yüzden ikisi birbirini tutmaz.',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: yapısal analizin toplam ağırlığı = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (CAD kütle dökümündeki nozul kütlesiyle aynı sayı). KAPSAM SINIRI: enjektör DAHİL DEĞİLDİR; CAD kütle dökümünün kuru toplamı enjektörü içerir ama uç kapaklarını dışarıda bırakır, bu yüzden iki toplam tam olarak bu iki kalem kadar farklıdır.',
            // V3 yapi-sf 2. tur: yapısal künyeler (karar §28-24 (C), Ş6) — TR.
            'TRUE means: a wall temperature used in this structural evaluation is at or above the melting point of the material, or above the last point of its strength-derating data. Above that point the strength is held at the last curve value (an upper bound, not a conservative value), and at or above melting the section has no load-carrying capacity at all. The strength, safety factors, wall thickness and masses computed from this evaluation are therefore outside the validity limit of the structural model: they are published as diagnostic numbers only, not as valid design outputs, and no acceptance and no numeric design verdict is issued. When the wall temperature comes from the heat-transfer module (wall_temperature_source = heat_transfer_module) it is a bare-wall steady-state estimate in which protection by the propellant grain, liner or insulation is not modelled, so an unreachable or failing result is a limit of the current model, not a statement that a real motor of this design is impossible.': 'TRUE şu demektir: bu yapısal değerlendirmede kullanılan bir cidar sıcaklığı malzemenin erime noktasında ya da üstünde, veya dayanım düşürme verisinin son noktasının üstündedir. O noktanın üstünde dayanım eğrinin son değerinde tutulur (bir üst sınırdır, muhafazakâr bir değer değildir); erime noktasında ya da üstünde kesitin hiç yük taşıma kapasitesi yoktur. Bu değerlendirmeden hesaplanan dayanım, emniyet katsayıları, cidar kalınlığı ve kütleler bu yüzden yapısal modelin geçerlilik sınırı dışındadır: geçerli tasarım çıktısı olarak değil, yalnız tanı amaçlı sayılar olarak yayımlanırlar; ne onay ne de sayısal tasarım hükmü verilir. Cidar sıcaklığı ısı transferi modülünden geldiğinde (wall_temperature_source = heat_transfer_module) bu, yakıt tanesi, astar ya da yalıtım korumasının modellenmediği çıplak cidar kararlı hâl tahminidir; bu yüzden ulaşılamaz ya da başarısız bir sonuç mevcut modelin sınırıdır, bu tasarımda gerçek bir motorun olanaksız olduğu anlamına gelmez.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor was computed at a wall temperature outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). How the wall was chosen is stated in design_mode, sizing_feasible and sizing_infeasible_reason.': 'YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu emniyet katsayısı, yapısal modelin geçerlilik sınırı dışındaki bir cidar sıcaklığında hesaplandı (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). Cidarın nasıl seçildiği design_mode, sizing_feasible ve sizing_infeasible_reason alanlarında yazılıdır.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind these masses comes from a structural evaluation outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded).': 'YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu kütlelerin arkasındaki kamara cidar kalınlığı, yapısal modelin geçerlilik sınırı dışındaki bir yapısal değerlendirmeden geliyor (chamber_analysis.model_validity_limit_exceeded).',
            'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (wall temperature at or above the melting point of the material, or above its strength-derating data). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.': 'Ne onay ne de sayısal tasarım hükmü verildi: hazne, yapısal modelin geçerlilik sınırı dışında değerlendirildi (cidar sıcaklığı malzemenin erime noktasında ya da üstünde, veya dayanım düşürme verisinin üstünde). Bu yanıttaki emniyet katsayıları tanı amaçlı sayılardır. Kalan bir MARGINAL ya da UNSAFE durumu MEVCUT modelin uyarısıdır ve asla bastırılmaz; ama bu tasarımda gerçek bir motorun olanaksız olduğu anlamına gelmez.',
            'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.': 'ÇİZİLEN KATI (tek kaynak): CAD dışa aktarımının çizdiği nozul kabuğu - iç kontur nozzle_design.sample_nozzle_inner_contour\'dan gelir, nozzle_geometry.wall_thickness cidarı dışa doğru eklenir, yoğunluk seçilen nozul malzemesinindir (nozzle_material). Aynı sayı cad_design.performance_summary.mass_breakdown.nozzle_mass ve nozzle_geometry.estimated_mass alanlarındadır. Eski "kamara kütlesinin %30\'u" başparmak kuralı artık kullanılmıyor.',
            'DRAWN SOLID (single source), insert + structural housing nozzle: inner contour from nozzle_design.sample_nozzle_inner_contour, the insert thickness added outward with the density of the selected nozzle material (nozzle_material), then the housing thickness with the density of the chamber material (nozzle_geometry.nozzle_construction). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass.': 'ÇİZİLEN KATI (tek kaynak), ek + yapısal gövdeli nozul: iç kontur nozzle_design.sample_nozzle_inner_contour\'dan gelir, önce ek kalınlığı seçilen nozul malzemesinin yoğunluğuyla (nozzle_material), sonra gövde kalınlığı yanma odası malzemesinin yoğunluğuyla dışa doğru eklenir (nozzle_geometry.nozzle_construction). Aynı sayı cad_design.performance_summary.mass_breakdown.nozzle_mass ve nozzle_geometry.estimated_mass alanlarındadır.',
            'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability': 'nozul tasarımcısının KENDİ yakınsak konisi (kendi kamara yarıçapı, bu motorun kamarası değil) ve ıraksak kesimi üzerinde kesik koni halkası - çizilen nozuldan farklı bir geometri, yalnız izlenebilirlik için tutuluyor',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: yapısal analizin toplam ağırlığı = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (CAD kütle dökümündeki nozul kütlesiyle aynı sayı). KAPSAM SINIRI: enjektör DAHİL DEĞİLDİR; CAD kütle dökümünün kuru toplamı enjektörü içerir ama uç kapaklarını dışarıda bırakır, bu yüzden iki toplam tam olarak bu iki kalem kadar farklıdır. YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu kütlenin arkasındaki kamara cidar kalınlığı, yapısal modelin geçerlilik sınırı dışındaki bir yapısal değerlendirmeden geliyor (kamara analizinin model geçerlilik sınırı aşıldı bayrağı); ondan türeyen uçuş zinciri sayıları da aynı sınırı taşır.',
            // V306/HİBRİT-KÜTLE (kalem 6): enjektör dahil kuru kütle künyesi — TR.
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: yapısal analizin toplam ağırlığı = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (CAD kütle dökümündeki nozul kütlesiyle aynı sayı) + enjektör plakası (CAD kütle dökümündeki enjektör kütlesiyle aynı sayı). CAD kütle dökümünün kuru toplamı yalnız ÇİZİLEN parçaları sayar; uç kapakları çizilmediği için o toplam tam olarak uç kapaklarının kütlesi kadar küçüktür.',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass) + the injector plate (weight_analysis.injector_weight, the same number as cad_design.performance_summary.mass_breakdown.injector_mass). The CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) counts the DRAWN parts only; the end closures are not drawn, so it is smaller by exactly weight_analysis.end_caps_weight. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: yapısal analizin toplam ağırlığı = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (CAD kütle dökümündeki nozul kütlesiyle aynı sayı) + enjektör plakası (CAD kütle dökümündeki enjektör kütlesiyle aynı sayı). CAD kütle dökümünün kuru toplamı yalnız ÇİZİLEN parçaları sayar; uç kapakları çizilmediği için o toplam tam olarak uç kapaklarının kütlesi kadar küçüktür. TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu kütlenin arkasındaki kamara cidar kalınlığı, yapısal modelin geçerlilik sınırı dışındaki bir yapısal değerlendirmeden geliyor (kamara analizinin model geçerlilik sınırı aşıldı bayrağı); ondan türeyen uçuş zinciri sayıları da aynı sınırı taşır.',
            'The through-wall temperature difference was computed on the wall named in thermal_reference_wall_thickness_mm. In size mode it is scaled to the evaluated wall by the thickness ratio (fixed heat flux, planar conduction drop q*t/k), so the sized wall and its published thermal stress come from the same model (equal values mean the same wall). With no reference wall the difference is held at the supplied value. In verify mode the difference belongs to the supplied wall and is not scaled.': 'Cidar boyunca sıcaklık farkı thermal_reference_wall_thickness_mm alanında adı geçen cidarda hesaplandı. Boyutlandırma kipinde bu fark kalınlık oranıyla değerlendirilen cidara ölçeklenir (sabit ısı akısı, düzlem iletim düşüşü q*t/k); böylece boyutlandırılan cidar ve yayımlanan ısıl gerilmesi aynı modelden gelir (eşit değerler aynı cidar demektir). Referans cidar yoksa fark verilen değerde tutulur. Doğrulama kipinde fark verilen cidara aittir ve ölçeklenmez.',
            'TRUE means: the evaluated wall was chosen by HRMA to meet the design safety factor target, so this section was not checked against a thickness you supplied. It does NOT by itself mean the published safety factor equals the target: sizing puts the TOTAL hoop stress (pressure + thermal, at the derated strength) on the target; when no thickness can reach it, sizing_feasible is false and the published factor is a measurement below the target. Use safety_factor_reads_back_target for that question.': 'TRUE şu demektir: değerlendirilen cidarı HRMA, tasarım emniyet katsayısı hedefini sağlayacak biçimde seçti; yani bu kesit sizin verdiğiniz bir kalınlığa karşı sınanmadı. Bu tek başına yayımlanan emniyet katsayısının hedefe eşit olduğu anlamına GELMEZ: boyutlandırma TOPLAM hoop gerilmesini (basınç + ısıl, düşürülmüş dayanımda) hedefe oturtur; hiçbir kalınlık ona ulaşamıyorsa sizing_feasible false olur ve yayımlanan katsayı hedefin altındaki bir ölçümdür. O soru için safety_factor_reads_back_target alanını kullanın.',
            '\'tautological\' here means the binding station\'s wall was SIZED by HRMA (design_mode == size), i.e. it was not checked against a thickness you supplied. It does NOT mean the number equals the design target: sizing puts the TOTAL hoop stress (pressure + thermal) on the target, and where no thickness reaches it the chamber reports sizing_feasible = false and the published factor is a measurement below the target. The sharp answer is binding_safety_factor_reads_back_target; the per-station inventory is stations_reading_back_target.': 'Buradaki \'totolojik\', bağlayan istasyonun cidarını HRMA\'nın BOYUTLANDIRDIĞI (design_mode == size), yani sizin verdiğiniz bir kalınlığa karşı sınanmadığı anlamına gelir. Sayının tasarım hedefine eşit olduğu anlamına GELMEZ: boyutlandırma TOPLAM hoop gerilmesini (basınç + ısıl) hedefe oturtur; hiçbir kalınlığın ulaşamadığı yerde hazne sizing_feasible = false bildirir ve yayımlanan katsayı hedefin altındaki bir ölçümdür. Keskin yanıt binding_safety_factor_reads_back_target alanıdır; istasyon başına döküm stations_reading_back_target alanındadır.',
            'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (thin_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification': 'kullanıcı cidar kalınlığı vermedi; HRMA cidarı, değerlendirmede kullanılan AYNI gerilme modeliyle (thin_wall) boyutlandırdı; çıkan SF hedef_SF x imalat payının geri okunmasıdır ve bağımsız bir doğrulama DEĞİLDİR',
            'no wall thickness was supplied by the user, so HRMA sized the wall with the SAME stress model used to evaluate it (lame_thick_wall); the resulting SF reads back target_SF x manufacturing allowance and is NOT an independent verification': 'kullanıcı cidar kalınlığı vermedi; HRMA cidarı, değerlendirmede kullanılan AYNI gerilme modeliyle (lame_thick_wall) boyutlandırdı; çıkan SF hedef_SF x imalat payının geri okunmasıdır ve bağımsız bir doğrulama DEĞİLDİR',
            'no wall thickness was supplied by the user and the requested safety factor is UNREACHABLE for the sizing load (see sizing_load and sizing_infeasible_reason), so the reported thickness does not meet the target; the safety factor below is a MEASUREMENT, not a read-back': 'kullanıcı cidar kalınlığı vermedi ve istenen emniyet katsayısı boyutlandırma yükü için ULAŞILAMAZ (bkz. sizing_load ve sizing_infeasible_reason); bu yüzden bildirilen kalınlık hedefi sağlamıyor; aşağıdaki emniyet katsayısı bir geri okuma değil, ÖLÇÜMDÜR',
            'structural analysis not available': 'yapısal analiz yok',
            'Sweep maximum (grid node, not the solver optimum)': 'Tarama azamisi (ızgara düğümü, çözücü optimumu değil)',
            'Sea-level exit, Pc': 'Deniz seviyesi çıkışı, Pc',
            'Sweep ceiling, same solver, refined between grid nodes (not the solver optimum)': 'Tarama tavanı, aynı çözücü, ızgara düğümleri arasında inceltildi (çözücü optimumu değil)',
            'Sweep ceiling (refined)': 'Tarama tavanı (inceltilmiş)',
            'This run': 'Bu koşum',
            'Isp vs O/F sweep not available: propellant identity (fuel/oxidizer/chamber pressure) was not supplied to this figure.': 'Isp - O/F taraması yok: itici kimliği (yakıt/oksitleyici/oda basıncı) bu figüre verilmedi.',
            'Mixed provenance (see property_sources)': 'Karma köken (bkz. property_sources)',
            'Derived from chemical formula (molecular weight only); not present in the NASA CEA species table': 'Kimyasal formülden türetildi (yalnız molekül ağırlığı); NASA CEA tür tablosunda yok',
            'NASA CEA species table': 'NASA CEA tür tablosu',
            /* ÖH D37 · A1c panel-dil — sunucu beyan cümleleri (K5). Anahtar
               üreticinin cümlesiyle BİREBİR: CAD performans grafiği iki
               gerekçesi (cad_visualization.py PERFORMANCE_CHART_NOT_DRAWN_REASON
               + _add_performance_chart itki notu), yanma süresi verilmedi
               gerekçeleri (safety_analysis.py / liquid_rocket_engine.py
               BURN_TIME_NOT_SUPPLIED_REASON, combustion_analysis.py
               calculate_thrust_at_altitudes 'reason'), A1b-3 panel-js
               OH-D37-G2 koşu noktası ipucu/notu (panel-js raporundan birebir;
               denetçi 2. tur Ş4: panel-js 4bbbd32f visualization.py ile
               karakter karakter karşılaştırıldı).
               tests/test_d37_panel_dil_a1.py cümleleri üreticiden alır;
               üretici değişirse eşleşme düşer ve metin İngilizce AYNEN kalır. */
            'Performance chart not drawn: burn_time was not published by the solver (no burn time was supplied) and no duration is assumed.': 'Performans grafiği çizilmedi: çözücü burn_time yayımlamadı (yanma süresi verilmedi) ve süre varsayılmıyor.',
            'Performance chart not drawn: thrust was not published by the solver and no design thrust is assumed.': 'Performans grafiği çizilmedi: çözücü itkiyi (thrust) yayımlamadı ve tasarım itkisi varsayılmıyor.',
            'burn time not supplied: motor_data carries no burn_time and no duration is assumed (the previous code silently used 10 s), so the quantities that depend on it were not evaluated. Supply burn_time [s] to get them.': 'yanma süresi verilmedi: motor_data burn_time taşımıyor ve süre varsayılmıyor (önceki kod sessizce 10 s kullanıyordu); bu yüzden ona bağlı büyüklükler değerlendirilmedi. Bunları almak için burn_time [s] verin.',
            'the burn time was not supplied (max_burn_duration is empty) and no default is assumed, so nothing that depends on it was computed: burn_time, total_impulse, propellant_mass_kg, the propellant tank card, the feed-system tank volumes and the autogenous pressurant budget. Fill "Maximum Burn Duration" (or send use_tutorial_defaults for the declared tutorial value) to get them.': 'yanma süresi verilmedi (max_burn_duration boş) ve varsayılan kabul edilmiyor; bu yüzden ona bağlı hiçbir şey hesaplanmadı: burn_time, total_impulse, propellant_mass_kg, itici tankı kartı, besleme sistemi tank hacimleri ve otojen basınçlandırıcı bütçesi. Bunları almak için "Azami Yanma Süresi" alanını doldurun (ya da beyan edilen eğitim değeri için use_tutorial_defaults gönderin).',
            'burn time not supplied (motor_data has no positive burn_time) and no duration is assumed, so the sea-level thrust (total impulse / burn time) and the altitude table built on it were not computed. The previous code silently used 10 s here.': 'yanma süresi verilmedi (motor_data pozitif bir burn_time taşımıyor) ve süre varsayılmıyor; bu yüzden deniz seviyesi itkisi (toplam itki / yanma süresi) ve onun üzerine kurulan irtifa tablosu hesaplanmadı. Önceki kod burada sessizce 10 s kullanıyordu.',
            'Exit: ISA sea level, no nozzle ε': 'Çıkış: ISA deniz seviyesi, nozul ε yok',
            'Exit basis not published': 'Çıkış künyesi yayımlanmadı',
            /* Denetçi 2. tur Ş4 — panel-js 4bbbd32f (2. tur Ş6) ε yolu,
               p_e yayımlanmadı hâli (EN tarafındaki nota bakın). Terim:
               nozzle → nozul (D27 tek terim kuralı, test_d27_arayuz_a2
               p12ab205); ilk turun G2 metinlerindeki lüle de nozul oldu. */
            'Exit: supplied nozzle ε, p_e not published': 'Çıkış: verilen nozul ε, p_e yayımlanmadı',
            /* Ayrıntılı CAD alt grafik başlıkları (cad_visualization.py
               DetailedCADGenerator subplot_titles, sıvı :4306 / katı :4913) —
               beyan notuyla aynı figür; 'Cross-Section View' zaten vardı. */
            'External View': 'Dış Görünüm',
            'Grain Cross-Section': 'Yakıt Bloğu Kesiti',
            'This run point: the solver result does not publish its exit basis, so whether the point shares the sweep curve\'s sea-level path or uses the design expansion ratio is not stated.': 'Bu koşum noktası: çözücü çıktısı çıkış künyesini yayımlamıyor; bu yüzden noktanın tarama eğrisinin deniz seviyesi yolunu mu paylaştığı yoksa tasarım genişleme oranını mı kullandığı belirtilmiyor.',
            /* V3 KK 3. tur (15 Eki, §28-50 (c)) — TR kipte İngilizce kalan
               sunucu cümleleri. Anahtar üreticinin cümlesiyle BİREBİR
               (tests/test_v3_kucuk.py 3. tur cümleleri üreticiden kurar);
               üretici değişirse eşleşme düşer, metin AYNEN kalır. */
            'No closure bolt count was supplied, so the joint is not sized. Enter the number of closure bolts to get separation and proof safety factors.': 'Kapak cıvatası sayısı verilmedi; bu yüzden birleşim boyutlandırılmadı. Ayrılma ve prova emniyet katsayılarını görmek için kapak cıvatası sayısını girin.',
            'burn_time is validated but NOT used by the structural model: stresses and safety factors are steady-state at the design pressure, and the fatigue check counts PRESSURISATION CYCLES (design_cycles), which a burn duration does not set. No burn time was assumed on your behalf either - the field simply does not enter this analysis. Creep and other time-at-temperature effects are NOT modelled here (they would be the only route by which a burn duration could change these numbers).': 'Yanma süresi doğrulanır ama yapısal model onu KULLANMAZ: gerilmeler ve emniyet katsayıları tasarım basıncında kararlı durum değerleridir; yorulma denetimi ise bir yanma süresinin belirlemediği BASINÇLANDIRMA ÇEVRİMLERİNİ (tasarım çevrim sayısı) sayar. Sizin yerinize bir yanma süresi de varsayılmadı - alan bu analize hiç girmez. Sünme ve sıcaklıkta geçen süreye bağlı öteki etkiler burada MODELLENMEZ (yanma süresinin bu sayıları değiştirebileceği tek yol onlar olurdu).',
            'NOT GIVEN — neither exit_diameter nor expansion_ratio was supplied; the sampler falls back to its own generic exit diameter, so the divergent extent of this axis is NOT this motor\'s': 'VERİLMEDİ — ne exit_diameter ne de expansion_ratio verildi; örnekleyici kendi genel çıkış çapına düşer, bu yüzden bu eksenin ıraksak uzantısı bu motorunki DEĞİLDİR',
            'outputs.*.p5/p25/p50/p75/p95 and std/cv_percent': 'outputs.*.p5/p25/p50/p75/p95 ve std/cv_percent',
            'every model input not listed in conditional_on_inputs': 'conditional_on_inputs içinde listelenmeyen her model girdisi',
            'independent (zero rank correlation)': 'bağımsız (sıra korelasyonu sıfır)',
            'These percentiles describe the spread produced by the listed input distributions alone. They are NOT a confidence interval on the true motor performance: model-form error (empirical correlation uncertainty, omitted physics) is not sampled and is not included, inputs are sampled as independent, and every input not listed is held at its nominal value. Widening or narrowing this band by changing input distributions does not change how well the model matches hardware.': 'Bu yüzdelikler yalnız listelenen girdi dağılımlarının ürettiği yayılımı anlatır. Gerçek motor performansı için bir güven aralığı DEĞİLDİR: model biçimi hatası (ampirik bağıntı belirsizliği, ihmal edilen fizik) örneklenmez ve banda dâhil edilmez, girdiler bağımsız örneklenir ve listelenmeyen her girdi nominal değerinde tutulur. Girdi dağılımlarını değiştirerek bu bandı genişletmek ya da daraltmak, modelin donanımla ne kadar uyuştuğunu değiştirmez.',
            'engine dry mass only: this result publishes no propellant tank mass, so tank structure and any residual propellant are NOT included': 'yalnız motor kuru kütlesi: bu sonuç itici tankı kütlesi yayımlamıyor, bu yüzden tank yapısı ve artık itici DAHİL DEĞİLDİR',
            'engine dry mass not published by the motor model; tank structure and residual propellant are therefore not accounted for either': 'motor kuru kütlesi motor modelince yayımlanmadı; bu yüzden tank yapısı ve artık itici de hesaba katılmadı',
        }
    };

    /* ------------------------------------------------------------------
       Desen kuralları — sayı/isim taşıdığı için sözlüğe giremeyen metinler
       ------------------------------------------------------------------
       Her kural: [regex, tr_şablonu, çevrilecek_grup_indisleri?]. Şablonda
       $1..$9 yakalanan grupları taşır; sayı ve birim asla çevrilmez.
       Üçüncü alan verilirse o gruplar önce sözlükten geçirilir (ör.
       "Showerhead Injector - Front View" -> "Duş başlıklı Enjektörü ...").
       Kurallar YALNIZ Türkçe için çalışır — İngilizcede metne dokunulmaz.
    */
    /* ÖH D37 · A1c panel-dil (K5 a) — DetailedCAD çizilmeyen parça
       etiketleri ve nedenleri (cad_visualization.py DetailedCADGenerator
       LIQUID_NOT_DRAWN_PARTS / SOLID_NOT_DRAWN_PARTS / *_REASON; tek tanım
       orada). Sözlüğe (DICT) girmez: bu kısa sözcükler grafiklerin başka
       yerlerinde tek başına çevrilmesin diye yalnız beyan deseninde kullanılır. */
    var CIZILMEYEN_PARCA_TR = {
        'injector head': 'enjektör kafası',
        'cooling jacket': 'soğutma ceketi',
        'feed lines': 'besleme hatları',
        'flanges/bolts': 'flanşlar/cıvatalar',
        'sensors': 'sensörler',
        'grain pattern': 'yakıt bloğu deseni',
        'inhibitor': 'yanma engelleyici',
        'case details': 'kasa ayrıntıları'
    };
    var CIZILMEME_NEDENI_TR = {
        'no dimension is published for them': 'bunlar için yayımlanmış ölçü yok',
        'the detailed solid-motor generator is not modelled':
            'ayrıntılı katı motor üreticisi modellenmedi'
    };

    /* V307/GRAFİK-BİRİM (kalem 5) — 3B yüzey künyesi desen işlevlerinin
       yardımcıları: sayı ondalık kanonundan (YAKALANAN), ortam etiketi ortam
       sözlüğünden / desenlerinden (çevrilemezse AYNEN). */
    function yuzeySayi(d) { return YAKALANAN(String(d), currentLang()); }
    function yuzeyOrtami(etiket) {
        var lang = currentLang();
        var hit = lookup(etiket, lang);
        if (hit !== null) return hit;
        hit = applyPatterns(etiket, PATTERNS, lang);
        return (hit !== null) ? hit : etiket;
    }

    var PATTERNS = [
        [/^Hole (\d+)$/, 'Delik $1'],
        /* V307/KÜÇÜKLER-2 (kalem 3): karşılaştırma figürünün ortam satırı
           (panel.ambient.altitudeP / altitude / pressure ile aynı ifade). */
        [/^(-?\d+) m design altitude \((\S+) bar\)$/, '$1 m tasarım irtifası ($2 bar)'],
        [/^(-?\d+) m design altitude$/, '$1 m tasarım irtifası'],
        [/^(\S+) bar design ambient$/, '$1 bar tasarım ortamı'],
        /* V307/GRAFİK-BİRİM (kalem 5): PERFORMANS 3B yüzey künyesi. Sayılar
           ondalık kanonundan (YAKALANAN), ortam etiketi yukarıdaki ortam
           sözlüğü/desenlerinden (yuzeyOrtami) geçer; seçmeli parçalar işlevle. */
        [/^Isp on this surface at that node: (\S+) s$/, 'Bu düğümde yüzeyin Isp değeri: $1 s'],
        [/^(Isp reported by the motor solver|Isp AS SUPPLIED to this figure — the caller did not declare it as a motor-solver result, so it was not re-solved here): (\d[\d.]*) s( at expansion ratio (\d[\d.]*)| \(expansion ratio not reported\))?(, design ambient: (.+))?$/,
         function (m, kaynak, isp, epsTum, eps, ortTum, ort) {
             var bas = (kaynak === 'Isp reported by the motor solver')
                 ? 'Motor çözücüsünün bildirdiği Isp'
                 : 'Bu grafiğe VERİLDİĞİ GİBİ Isp (çağıran onu motor çözücüsünün çıktısı olarak beyan etmedi; burada yeniden çözülmedi)';
             return bas + ': ' + yuzeySayi(isp) + ' s'
                 + (eps ? ', genleşme oranı ' + yuzeySayi(eps)
                        : (epsTum ? ' (genleşme oranı bildirilmedi)' : ''))
                 + (ort ? ', tasarım ortamı: ' + yuzeyOrtami(ort) : '');
         }],
        /* Çıplak "Isp <sayı> s" satırı yalnız genleşme oranı / ortam
           ekiyle çevrilir; eksiz satır (ve "Isp: %{y} s" gibi ipucu
           şablonları) EŞLEŞMEZ, olduğu gibi kalır. */
        [/^Isp (\d[\d.]*) s(?=( at expansion ratio |, design ambient: ))( at expansion ratio (\d[\d.]*))?(, design ambient: (.+))?$/,
         function (m, isp, ileri, epsTum, eps, ortTum, ort) {
             return 'Isp ' + yuzeySayi(isp) + ' s'
                 + (eps ? ', genleşme oranı ' + yuzeySayi(eps) : '')
                 + (ort ? ', tasarım ortamı: ' + yuzeyOrtami(ort) : '');
         }],
        [/^Difference: (\S+) s \((\S+%)\) — this is an expansion-basis difference, NOT a distance from the optimum on this surface$/,
         'Fark: $1 s ($2) — bu bir genleşme tabanı farkıdır, bu yüzeydeki optimuma uzaklık DEĞİLDİR'],
        [/^Expansion basis checked: this surface solves (\S+) s at the same node, i\.e\. (\S+) s — within the (\S+%) band, so the two are read on the same basis$/,
         'Genleşme tabanı denetlendi: bu yüzey aynı düğümde $1 s çözüyor, yani $2 s — $3 bandının içinde; ikisi aynı tabanda okunur'],
        [/^Sea-level exit; O\/F band (\S+)-(\S+), step (\S+)$/, 'Deniz seviyesi çıkışı; O/F bandı $1-$2, adım $3'],
        [/^Chemical-equilibrium sweep, (\d+)\/(\d+) nodes solved \| (.+?)( \(reference pair — propellant identity not supplied\))?( \| (\d+) node\(s\) unsolved \(drawn as gaps\))?$/,
         function (m, cozulen, toplam, cift, ref, eksikTum, eksik) {
             return 'Kimyasal denge taraması, ' + cozulen + '/' + toplam
                 + ' düğüm çözüldü | ' + cift
                 + (ref ? ' (referans çift — itici kimliği verilmedi)' : '')
                 + (eksik ? ' | ' + eksik + ' düğüm çözülemedi (boşluk olarak çizildi)' : '');
         }],
        [/^The design-point cross is drawn at THIS surface's expansion basis \((\S+) s at Pc (\S+) bar, O\/F (\S+)\); the motor itself reports (\S+) s( at expansion ratio (\S+))?(, design ambient: (.+?))? — a (\S+) s \((\S+%)\) expansion-basis difference, not a distance from this surface's optimum\.$/,
         function (m, ys, pc, of, isp, epsTum, eps, ortTum, ort, fark, yuzde) {
             return 'Tasarım noktası haçı BU yüzeyin genleşme tabanında çizildi ('
                 + yuzeySayi(ys) + ' s; Pc ' + yuzeySayi(pc) + ' bar, O/F ' + yuzeySayi(of)
                 + '); motorun kendisi ' + yuzeySayi(isp) + ' s bildiriyor'
                 + (eps ? ' (genleşme oranı ' + yuzeySayi(eps) + ')' : '')
                 + (ort ? ', tasarım ortamı: ' + yuzeyOrtami(ort) : '')
                 + ' — ' + yuzeySayi(fark) + ' s (' + yuzeySayi(yuzde)
                 + ') genleşme tabanı farkı; bu yüzeyin optimumuna uzaklık değildir.';
         }],
        [/^The motor design point is NOT drawn on this surface: the sweep was solved for the reference pair above because the caller did not supply this motor's propellant identity, so the design point \(Pc (\S+) bar, O\/F (\S+), Isp (\S+) s\) belongs to a different propellant system and its position relative to this surface would mean nothing\.$/,
         'Motorun tasarım noktası bu yüzeye ÇİZİLMEDİ: çağıran bu motorun itici kimliğini vermediği için tarama yukarıdaki referans çift için çözüldü; tasarım noktası (Pc $1 bar, O/F $2, Isp $3 s) başka bir itici sistemine aittir ve bu yüzeye göre konumu bir anlam taşımaz.'],
        [/^The design point is NOT drawn on this surface: its Isp of (\S+) s is above the highest Isp this sweep actually solved \((\S+) s at Pc (\S+) bar, O\/F (\S+), from (the grid maximum|local refinement around the grid maximum)\) — by (\S+) s \((\S+%)\)\. A point above the equilibrium ceiling of its own surface comes from a different basis \(vacuum vs sea-level expansion, or another operating point\), so its position here would mean nothing\. Check the design point against the motor result before reading it off this figure\.$/,
         function (m, isp, tavan, pc, of, kaynak, fark, yuzde) {
             return 'Tasarım noktası bu yüzeye ÇİZİLMEDİ: Isp değeri (' + yuzeySayi(isp)
                 + ' s) bu taramanın gerçekten çözdüğü en yüksek Isp değerinin ('
                 + yuzeySayi(tavan) + ' s; Pc ' + yuzeySayi(pc) + ' bar, O/F ' + yuzeySayi(of) + '; '
                 + (kaynak === 'the grid maximum' ? 'ızgara azamisinden'
                                                  : 'ızgara azamisi çevresindeki yerel inceltmeden')
                 + ') ' + yuzeySayi(fark) + ' s (' + yuzeySayi(yuzde) + ') üstünde. Kendi yüzeyinin '
                 + 'denge tavanının üstündeki bir nokta başka bir tabandan gelir (vakum ⟷ deniz '
                 + 'seviyesi genleşmesi ya da başka bir çalışma noktası); buradaki konumu bir anlam '
                 + 'taşımaz. Bu grafikten okumadan önce tasarım noktasını motor çıktısıyla karşılaştırın.';
         }],
        [/^Surface not available: the equilibrium solver rejected every node of this sweep( \((.+)\))?\. No surrogate surface is drawn\.$/,
         function (m, hTum, hata) {
             return 'Yüzey yok: denge çözücüsü bu taramanın her düğümünü reddetti'
                 + (hata ? ' (' + hata + ')' : '') + '. Yerine geçecek bir yüzey çizilmez.';
         }],
        [/^Ring (\d+), hole (\d+)$/, 'Halka $1, delik $2'],
        [/^Injection Holes \((\d+)\)$/, 'Enjeksiyon delikleri ($1)'],
        [/^(\d+) Holes x dia (.+)$/, '$1 delik x çap $2'],
        /* V307 DİL-SUNUCU (DİL-HİBRİT S2): enjektör şeması, yerleşim çizilemediğinde. */
        [/^Face layout NOT drawn: the schematic spacing would put hole centres (\S+) mm apart, closer than the (\S+) mm hole diameter — those holes cannot coexist on the plate$/,
         'Yüz yerleşimi ÇİZİLMEDİ: şematik aralık delik merkezlerini $1 mm arayla koyardı, $2 mm delik çapından daha yakın — bu delikler plakada bir arada bulunamaz'],
        [/^(\d+) axial orifices$/, '$1 eksenel delik'],
        [/^Conv\. Angle (.+)$/, 'Yakınsama açısı $1'],
        [/^Div\. Angle (.+)$/, 'Iraksama açısı $1'],
        [/^Conv\. (.+)$/, 'Yakınsak $1'],
        [/^Div\. (.+)$/, 'Iraksak $1'],
        [/^Convergent (.+)$/, 'Yakınsak $1'],
        [/^Divergent (.+)$/, 'Iraksak $1'],
        [/^Conical divergent: (.+)$/, 'Konik ıraksak: $1'],
        [/^Bell contour: (.+)$/, 'Çan kontur: $1'],
        [/^Impinging pairs \((.+)\)$/, 'Çarpışmalı çiftler ($1)'],
        /* v3.0.0 (15 Eki): visualization.py kesit ölçüsü, bölümlü tanede
           'Grain stack = 364 mm (3 x 120 + 2 x 2 gap)' basıyor; Türkçe
           arayüzde İngilizce kalıyordu (ekran görüntüsünde ölçüldü). */
        [/^Grain stack = (\S+ mm) \((\d+) x (\S+) \+ (\d+) x (\S+) gap\)$/,
         'Yakıt blokları = $1 ($2 × $3 + $4 × $5 boşluk)'],
        [/^Grain = (.+)$/, 'Yakıt bloğu = $1'],
        /* Faz 6 / T43 (3 Ağustos 2026): sonek kuralı GENEL kuraldan ÖNCE
           gelmeli — applyPatterns ilk eşleşmeyi uygular. visualization.py:3527
           web tamamen tükendiğinde '(web fully consumed)' ekliyor; genel kural
           '(.+)' ile bu soneki de yutup İngilizce bırakıyordu (ölçüldü:
           'Son port Ø99.8 mm (web fully consumed)'). */
        /* ÖH D37 · A1b dil-cozucu-nesri (DV36-16): ölçü ('Ø99.8 mm',
           '0.83 mm/s') artık cümle içi ölçü kanonundan (I18N_OLCU →
           I18N.decimalText) geçer — TR 'Son port Ø99,8 mm'. Eskiden sayı
           noktalı taşınıyordu ve virgül yalnız plotly_dark.js figür
           geçişinde geliyordu; chartText işlevini doğrudan çağıran yol (Excel /
           panel başlığı) noktalı kalıyordu. İkinci geçiş idempotent:
           virgüllü sayı plotly_dark SAYI_ZINCIRI içine yeniden girmez. */
        [/^Final port (.+) \(web fully consumed\)$/,
         function (_t, olcu) { return 'Son port ' + I18N_OLCU(olcu) + ' (web tamamen tükendi)'; }],
        [/^Final port (.+)$/, function (_t, olcu) { return 'Son port ' + I18N_OLCU(olcu); }],
        [/^End-of-burn port: (.+)$/, function (_t, olcu) { return 'Yanma sonu portu: ' + I18N_OLCU(olcu); }],
        [/^Regression Rate \(avg: (.+)\)$/, function (_t, olcu) { return 'Regresyon hızı (ort: ' + I18N_OLCU(olcu) + ')'; }],
        /* ÖH D37 · A1b dil-cozucu-nesri (DV36-21) — G-1 tarama işaretinin
           hover satırları (visualization.py:3136-3144, :5052-5055). */
        [/^Band (\S+)-(\S+), step (\S+)$/, 'Bant $1-$2, adım $3'],
        [/^Isp (\S+) s \(solver\)$/, 'Isp $1 s (çözücü)'],
        [/^Grid maximum was (\S+) s$/, 'Izgara azamisi $1 s idi'],
        /* ÖH D37 · A1c panel-dil (K5 d) — A1b-3 panel-js OH-D37-G2 koşu
           noktası ipucusunun ε içeren çıkış satırı (visualization.py, panel-js
           dalı; p_e ondalığı YAKALANAN ile kanondan geçer). */
        [/^Exit: supplied nozzle ε, p_e (\S+) bar$/, 'Çıkış: verilen nozul ε, p_e $1 bar'],
        /* ÖH D37 · A1c panel-dil (K5 a) — DetailedCAD çizilmeyen parça
           beyanı (cad_visualization.py DetailedCADGenerator._not_drawn_block:
           'Parts not drawn: <etiket>, … (<neden>)'). Etiketler ve neden
           KAPALI ailedir (LIQUID/SOLID_NOT_DRAWN_PARTS + *_REASON);
           FAIL-CLOSED: biri tanınmazsa cümle AYNEN döner (yarı Türkçe liste
           üretilmez). */
        [/^Parts not drawn: (.+) \(([^()]+)\)$/,
         function (tum, liste, neden) {
             var n = Object.prototype.hasOwnProperty.call(CIZILMEME_NEDENI_TR, neden)
                 ? CIZILMEME_NEDENI_TR[neden] : null;
             if (n === null) return tum;
             var parcalar = liste.split(', ');
             var tr = [];
             for (var i = 0; i < parcalar.length; i++) {
                 if (!Object.prototype.hasOwnProperty.call(CIZILMEYEN_PARCA_TR, parcalar[i])) {
                     return tum;
                 }
                 tr.push(CIZILMEYEN_PARCA_TR[parcalar[i]]);
             }
             return 'Çizilmeyen parçalar: ' + tr.join(', ') + ' (' + n + ')';
         }],
        [/^(.+) Regression Analysis$/, '$1 Regresyon Analizi'],
        [/^(.+) Injector - Front View$/, '$1 Enjektörü - Önden Görünüm', [1]],
        [/^Sensitivity Tornado —\s*(.*)$/, 'Duyarlılık Tornado Grafiği — $1'],
        [/^Limit reached —\s*(.*)$/, 'Sınıra ulaşıldı — $1'],
        [/^Service limit —\s*(.*)$/, 'Servis sınırı — $1'],
        [/^Maximum Altitude \((.+)\)$/, 'Azami irtifa ($1)'],
        [/^L<sub>chamber<\/sub> = (.+)$/, 'L<sub>oda</sub> = $1'],
        [/^L<sub>total<\/sub> = (.+)$/, 'L<sub>toplam</sub> = $1'],
        [/^(\d+) Holes$/, '$1 delik'],
        /* P12aB3-10 (Z5 i18n) — ÖLÜ KURAL SİLİNDİ:
               [/^Throat station$/, 'Boğaz istasyonu'],
           `chartText`/`serverText` ÖNCE sözlüğe bakar (bkz. translateSegment:
           lookup → applyPatterns). 'Throat station' sözlükte zaten var
           (satır 929, 'Boğaz istasyonu'), dolayısıyla bu kural HİÇ
           çalışmıyordu. İkinci bir kaynak tutmak, ikisinin ileride
           ayrışmasına davetiyeydi — tek kaynak sözlüktür. */

        /* --- 2026-08-03, dinamik yüzey taraması ------------------------
           Aşağıdakiler tek koşuda ölçülerek bulundu: /calculate,
           /calculate_solid ve /calculate_liquid yanıtlarındaki figür
           metinleri toplanıp sözlükten geçirildi, çevrilmeden kalanlar
           buraya kural olarak yazıldı. Hepsi SAYI TAŞIYAN metinler, yani
           birebir sözlük girdisi olamazlar. */

        /* Nozul kontur açıları — visualization.py:3990. noz_type
           capitalize() ile geldiği için taban ad 1. grupta sözlükten
           geçirilir (Bell_80 gibi kayıtlı olmayan ad aynen kalır). */
        [/^Conical divergent: α = (.+)°$/, 'Konik ıraksak: α = $1°'],
        [/^(.+) contour: θ<sub>n<\/sub> = (.+)° → θ<sub>e<\/sub> = (.+)°$/,
         '$1 konturu: θ<sub>n</sub> = $2° → θ<sub>e</sub> = $3°'],

        /* Paraşüt açılış işaretçisi — trajectory_analysis.py:1700.
           '(assumed)' bayrağı ayrı kural: iç içe isteğe bağlı grup
           çevrilmeden İngilizce kalırdı. */
        [/^Parachute deploy at (\S+) s — (\S+) m2 at Cd (\S+) \(assumed\); mean descent (\S+) m\/s$/,
         'Paraşüt açılışı $1 s — $2 m2, Cd $3 (varsayılan); ortalama iniş hızı $4 m/s'],
        [/^Parachute deploy at (\S+) s — (\S+) m2 at Cd (\S+); mean descent (\S+) m\/s$/,
         'Paraşüt açılışı $1 s — $2 m2, Cd $3; ortalama iniş hızı $4 m/s'],
        [/^Parachute deploy at (\S+) s — (\S+) m2 at Cd (\S+) \(assumed\)$/,
         'Paraşüt açılışı $1 s — $2 m2, Cd $3 (varsayılan)'],
        [/^Parachute deploy at (\S+) s — (\S+) m2 at Cd (\S+)$/,
         'Paraşüt açılışı $1 s — $2 m2, Cd $3'],
        [/^Parachute deploy at (\S+) s$/, 'Paraşüt açılışı $1 s'],

        /* İkinci eksen beyanı — visualization.py:_perf_relation_note.
           Kısa etiket ('= Burn Area / 2.524 cm²') ile uzun ipucu cümlesi
           AYNI ölçümden üretiliyor; ikisi de buradan geçer. Büyüklük adı
           (grup 1/2) sözlükten geçirilir, sayı ve birim korunur. */
        [/^= (.+?) \/ (.+)$/, '= $1 / $2', [1]],
        [/^= (.+?) x (.+)$/, '= $1 x $2', [1]],
        [/^&asymp; (.+?) \/ (.+)$/, '&asymp; $1 / $2', [1]],
        [/^&asymp; (.+?) x (.+)$/, '&asymp; $1 x $2', [1]],
        [/^(.+) &mdash; this axis is (.+?) divided by the constant (.+)\. The ratio was measured across this run and is fixed to within (.+), so the curve carries nothing the left axis does not already show: it is a unit conversion, meant to be read as a second scale\.$/,
         '$1 &mdash; bu eksen, $2 büyüklüğünün $3 sabitine bölünmüş hâlidir. Oran bu koşu boyunca ölçüldü ve $4 içinde sabit kaldı; yani eğri, sol eksenin zaten gösterdiğinden fazlasını taşımaz: bir birim dönüşümüdür, ikinci bir ölçek olarak okunmalıdır.',
         [2]],
        [/^(.+) &mdash; this axis is (.+?) multiplied by the constant (.+)\. The ratio was measured across this run and is fixed to within (.+), so the curve carries nothing the left axis does not already show: it is a unit conversion, meant to be read as a second scale\.$/,
         '$1 &mdash; bu eksen, $2 büyüklüğünün $3 sabitiyle çarpılmış hâlidir. Oran bu koşu boyunca ölçüldü ve $4 içinde sabit kaldı; yani eğri, sol eksenin zaten gösterdiğinden fazlasını taşımaz: bir birim dönüşümüdür, ikinci bir ölçek olarak okunmalıdır.',
         [2]],
        [/^(.+) &mdash; this axis follows (.+?) almost exactly: the measured (.+?) ratio is (.+?) and varies by only (.+?)% over this run, so both curves have the same shape\. That small variation is (.+), not an independent quantity\.$/,
         '$1 &mdash; bu eksen $2 büyüklüğünü neredeyse birebir izler: ölçülen $3 oranı $4 ve bu koşu boyunca yalnız %$5 değişiyor, yani iki eğrinin biçimi aynı. Bu küçük değişim $6 kaynaklıdır, bağımsız bir büyüklük değildir.',
         [2]],

        /* Emniyet katsayısı eşiği — visualization.py yapısal pano */
        [/^Min SF: (.+)$/, 'En düşük GK: $1']
    ];

    /* Sunucu mesajı desenleri (uyarı / doğrulama / hata metinleri).
       Yakalanan gruplar (sayı, malzeme adı, birim) korunur. */
    /* ----------------------------------------------------------------
       Cümle içi ölçü yerelleştirmesi (OH-D33-43).
       ``I18N.decimalText`` TEK KAYNAKTIR; yoksa sayı OLDUĞU GİBİ kalır
       (uydurma biçimlendirme yok). Künye/makine dizeleri buradan GEÇMEZ:
       ayrım cümle ⟷ künyedir (fix-38a ile aynı kanon).
       ---------------------------------------------------------------- */
    function I18N_SAYI(x) {
        /* ÖH D35: eskiden `window.I18N && I18N.decimalText` yazıyordu —
           ikinci ad KÜRESEL `I18N`di ve `window` de KÜRESEL bir addı.
           İkisi de bu dosyanın kendi kökünde YOK: IIFE zaten kökü `global`
           parametresiyle alıyor (dosyanın geri kalanı öyle okuyor). Sözlüğü
           bir `window` taklidi üstünde taşıyan ya da hiç `window` tanımlamayan
           koşum ortamlarında eski biçim ReferenceError atıyordu; kusur
           TABANDA da vardı, OH-GT-24(d) yardımcıyı HER yakalamaya bağlayınca
           görünür oldu. Erişim tek addan: `global`. */
        var api = global && global.I18N;
        return (api && api.decimalText) ? api.decimalText(x) : x;
    }

    /* '24.9 m/s' gibi sayı+birim parçasında YALNIZ sayıyı yerelleştirir. */
    function I18N_OLCU(x) {
        return String(x).replace(/-?\d+(?:\.\d+)?/g, function (sayi) {
            return I18N_SAYI(sayi);
        });
    }

    /* Kavitasyon mesajının İngilizce parantez içi. Tanımadığı biçimi
       DEĞİŞTİRMEZ: yarım çeviri üretmektense İngilizce bırakmak yeğdir. */
    function I18N_KAVITASYON_ICI(ic) {
        var m = String(ic).match(
            /^injector inlet P_1 = (\S+) bar, dP = (\S+) bar, P_v = (\S+) bar at (\S+) K$/);
        if (!m) { return ic; }
        return 'enjektör girişi P_1 = ' + I18N_SAYI(m[1])
            + ' bar, dP = ' + I18N_SAYI(m[2])
            + ' bar, P_v = ' + I18N_SAYI(m[3])
            + ' bar (' + I18N_SAYI(m[4]) + ' K)';
    }

    /* V307 DİL-SON — yapısal hüküm gerekçesinin istasyon listesi. Sunucu
       okunur İngilizce adı basar (structural_analysis
       STRUCTURAL_STATION_NAMES_EN = app.sfst.* İngilizcesi); burada sözlük
       anahtarına eşlenip Türkçesi basılır. takim 'app.sfst' -> hüküm şeridi
       adları, 'panel' -> güverte YAPISAL tablosunun adları
       (panel.structural.mode*). Tanınmayan ad varsa liste AYNEN döner;
       boş liste ('none') 'yok' olur. */
    /* V307/ŞERİT-GÜRÜLTÜ (DİL-SON KARAR 2): hüküm cümlesinin dört dalı TEK ad
       kümesi kullanır — YAPISAL tablosunun adları (panel.structural.mode*:
       "Oda çember gerilmesi", "Oda von Mises", "Kapak", "Nozul boğazı",
       "Eksenel burkulma"). Önce 1/2/4. dal şerit adlarını (app.sfst.*: "kamara
       çevresel gerilmesi", "uç kapak", "nozul"), 3. dal tablo adlarını
       basıyordu: aynı panelde aynı istasyon iki adla. Seçim ölçümle (RAPOR
       ŞERİT-GÜRÜLTÜ kalem 2): sözlüklerde "çember gerilme" 25 / "çevresel
       gerilme" 6 (taban), TR kılavuzda 9 / 1, testlerde 16 / 2 dosya; hüküm cümlesi
       YAPISAL panelinde, tablonun hemen yanında basılır. */
    var YAPISAL_ISTASYON_ANAHTARI = {
        'nozzle': 'panel.structural.modeNozzle',
        'end cap': 'panel.structural.modeEndCap',
        'chamber hoop stress': 'panel.structural.modeChamberHoop',
        'chamber von Mises stress': 'panel.structural.modeChamberVm',
        'axial buckling': 'panel.structural.modeBuckling'
    };
    function _yapisalIstasyonTr(liste) {
        if (liste === 'none') { return 'yok'; }
        var I = global.I18N, tablo = YAPISAL_ISTASYON_ANAHTARI;
        var ad = String(liste).split(', ').map(function (x) {
            var k = Object.prototype.hasOwnProperty.call(tablo, x) ? tablo[x] : null;
            return (k && I && typeof I.has === 'function' && I.has(k)) ? I.t(k) : null;
        });
        return (ad.indexOf(null) !== -1) ? liste : ad.join(', ');
    }

    /* V3 KK 2. tur (CFDS devri) — runtime_basis cümlesinin değişmeyen ilk
       cümlesinin TR karşılığı (iki desen de bunu kullanır; tek kopya). */
    var CFD_SURE_GOVDE_TR = 'solver_runtime_s kararlı çözücü sürücüsünün '
        + 'kendi süresi, runtime_s ise isteğin tamamıdır (doğrulama, ağ, '
        + 'çözüm, ayrılma, seyreltme).';

    var MSG_PATTERNS = [
        /* V307 DİL-SON (kalem 8b): bugünkü PDF derleminin dize şablonları (k8_pdf_derlem_once.json).
           Üreticiler: hrma/export/pdf_generator.py _chug_verdict_line (yalın dal: kural/kısma eki yok)
           ve iki faz kaybı künyesi. Sayılar yakalamadan AYNEN taşınır. */
        [/^feed-coupled chug loop model STABLE \(growth rate (\S+) 1\/s, (\S+) Hz\)$/,
         'besleme bağlaşımlı chug çevrimi modeli KARARLI (büyüme hızı $1 1/s, $2 Hz)'],
        [/^feed-coupled chug loop model MARGINAL \(growth rate (\S+) 1\/s, (\S+) Hz\)$/,
         'besleme bağlaşımlı chug çevrimi modeli SINIRDA (büyüme hızı $1 1/s, $2 Hz)'],
        [/^feed-coupled chug loop model UNSTABLE \(growth rate (\S+) 1\/s, (\S+) Hz\)$/,
         'besleme bağlaşımlı chug çevrimi modeli KARARSIZ (büyüme hızı $1 1/s, $2 Hz)'],
        [/^oxidizer_type '(\S+)' names no hybrid oxidiser with a derived TNT equivalence \(derived: ([^)]+)\), so no TNT-equivalent class was won\. The product default oxidiser is NOT substituted for a named oxidiser HRMA cannot identify\.$/,
         'Oksitleyici türü \'$1\', TNT eşdeğerliği türetilmiş bir hibrit oksitleyiciyi adlandırmıyor (türetilenler: $2), bu yüzden TNT eşdeğeri sınıfı kazanılmadı. HRMA\'nın tanıyamadığı adlı bir oksitleyicinin yerine ürünün varsayılan oksitleyicisi konmaz.'],
        /* V307 DİL-SON (kalem 8b, ikinci tur): ablatif soğutmada hedef sıcaklık cümleleri (K değeri yakalanır). */
        [/^your limit (\S+) K can only be checked against a SOLVED wall temperature and none exists on this run - cooling_type 'ablative': HRMA has no wall-temperature solver for a passively cooled wall in this chain \(passive_thermal_protection sizes the liner\/heat sink, it does not publish an equilibrium wall temperature\)\. The cooling numbers were evaluated AT your target \(a requirement\); that does not show the wall stays below it\.$/,
         'sınırınız $1 K yalnız ÇÖZÜLMÜŞ bir cidar sıcaklığına karşı denetlenebilir ve bu koşumda öyle bir sıcaklık yok - soğutma türü \'ablative\': HRMA\'nın bu zincirde pasif soğutulan bir cidar için cidar sıcaklığı çözücüsü yok (pasif ısıl koruma astarı/ısı yutucuyu boyutlandırır, denge cidar sıcaklığı yayımlamaz). Soğutma sayıları hedefinizde (bir gereksinim) değerlendirildi; bu, cidarın hedefin altında kaldığını göstermez.'],
        [/^the structural verdict of this block \(allowable_stress, stress_margin, hoop_safety_factor, model validity\) is evaluated at (\S+) K, which is your maximum wall temperature TARGET - a requirement, not a solved result\. No solved wall temperature exists on this run: cooling_type 'ablative': HRMA has no wall-temperature solver for a passively cooled wall in this chain \(passive_thermal_protection sizes the liner\/heat sink, it does not publish an equilibrium wall temperature\)$/,
         'bu bloğun yapısal hükmü (izin verilen gerilme, gerilme payı, çevresel emniyet katsayısı, model geçerliliği) $1 K\'de değerlendirildi; bu sizin azami cidar sıcaklığı HEDEFİNİZDİR - bir gereksinim, çözülmüş bir sonuç değil. Bu koşumda çözülmüş cidar sıcaklığı yok: soğutma türü \'ablative\': HRMA\'nın bu zincirde pasif soğutulan bir cidar için cidar sıcaklığı çözücüsü yok (pasif ısıl koruma astarı/ısı yutucuyu boyutlandırır, denge cidar sıcaklığı yayımlamaz)'],
        [/^Throttle map: ratio rule met but the loop model does not say stable at (.+) \(not counted as stable\)$/,
         'Kısma haritası: $1 noktalarında oran kuralı sağlanıyor ama çevrim modeli kararlı demiyor (kararlı sayılmadı)'],
        [/^The built-in size-corrected two-phase \(particle-lag\) loss estimate of hrma\.analysis\.two_phase_loss for this motor is (\S+) %, but it is NOT applied: a nozzle or kinetic efficiency was supplied with the request\.$/,
         'Bu motor için yerleşik, boyut düzeltmeli iki fazlı (parçacık gecikmesi) kayıp tahmini %$1, ama UYGULANMADI: istekte nozul ya da kinetik verim verildi.'],
        /* 3.0.6 (9 Kas, ana model) — ENJEKTÖR Cd DAYANAĞI. Üretici:
           hrma/engines/injector_design.py discharge_coefficient
           ('{gerekçe}; L/D={l_over_d} -> Cd={cd} ({künye})'), CD_TABLE
           gerekçeleri ve CD_TABLE_SOURCE künyeleri. Hibrit enjektör
           tablosunun 'Boşaltma Katsayısı Dayanağı' satırı TR ekranda
           İngilizce kalıyordu (test_v301_dil_ekran, hibrit örnek L/D 1,23).
           Fail-closed: gerekçe ya da künye tablodakilerden biri değilse
           metin AYNEN kalır (çevrilmedi sayılır). */
        [/^([\s\S]+); L\/D=(\S+) -> Cd=(\S+) \(([\s\S]+)\)$/,
         function (t, neden, ld, cd, kunye) {
             var NEDEN_TR = {
                 'sharp inlet, short (L/D<1): vena contracta dominates':
                     'keskin kenarlı giriş, kısa (L/D<1): vena contracta baskın',
                 'sharp inlet, reattaching (L/D 1-5): table value between the separated and full-flow regimes':
                     'keskin kenarlı giriş, yeniden tutunan akış (L/D 1-5): tablo değeri ayrık akış ile tam dolu akış rejimlerinin arasında',
                 'sharp inlet, long (L/D>5): table value 0.84 is ABOVE the full-flow plateau of NASA SP-8089 Fig. 15 (p. 43, about 0.82); wall friction can only lower Cd, so this value is optimistic by about 2.4% (correction pending)':
                     'keskin kenarlı giriş, uzun (L/D>5): tablo değeri 0,84, NASA SP-8089 Şekil 15\'teki (s. 43, yaklaşık 0,82) tam dolu akış platosunun ÜSTÜNDE; cidar sürtünmesi Cd\'yi yalnız düşürebilir, bu yüzden bu değer yaklaşık %2,4 iyimser (düzeltme bekliyor)',
                 'radiused inlet (r/d >= 0.15), short':
                     'yuvarlatılmış giriş (r/d ≥ 0,15), kısa',
                 'radiused inlet (r/d >= 0.15): stable Cd':
                     'yuvarlatılmış giriş (r/d ≥ 0,15): kararlı Cd',
                 'sharp inlet, long': 'keskin kenarlı giriş, uzun',
                 'radiused inlet, long': 'yuvarlatılmış giriş, uzun'
             };
             var KUNYE_TR = {
                 'NASA SP-8089 (Gill & Nurick 1976) Fig. 13 p. 38 and Fig. 15 p. 43; Lefebvre & McDonell, Atomization and Sprays, 2nd ed., Ch. 5':
                     'NASA SP-8089 (Gill & Nurick 1976) Şekil 13 s. 38 ve Şekil 15 s. 43; Lefebvre & McDonell, Atomization and Sprays, 2. baskı, Böl. 5',
                 'NASA SP-8089 (Gill & Nurick 1976); Lefebvre & McDonell, Atomization and Sprays, 2nd ed., Ch. 5':
                     'NASA SP-8089 (Gill & Nurick 1976); Lefebvre & McDonell, Atomization and Sprays, 2. baskı, Böl. 5',
                 'outside table, end value': 'tablo dışı, uç değer'
             };
             var n = Object.prototype.hasOwnProperty.call(NEDEN_TR, neden) ? NEDEN_TR[neden] : null;
             var k = Object.prototype.hasOwnProperty.call(KUNYE_TR, kunye) ? KUNYE_TR[kunye] : null;
             if (n === null || k === null) return t;
             return n + '; L/D=' + I18N_SAYI(ld) + ' → Cd=' + I18N_SAYI(cd) + ' (' + k + ')';
         }],
        /* V301/UÇUŞ NK-47 — 6-DOF UCUNUN "GÖVDE MOTORU TAŞIYAMAZ" REDDİ.
           Üretici: hrma/app.py six_dof_analysis + hrma/analysis/
           flight_vehicle.py airframe_fit_conflicts (çap ve boy cümleleri
           isteğe bağlı, sırası sabit). Sayılar sunucudan gelir; burada
           yalnız ondalık kanonundan geçer. */
        [/^No flight was solved: the airframe is smaller than the engine it is asked to carry\.(?: The body outer diameter (\S+) mm is smaller than the engine envelope (\S+) mm \(case\/chamber outer diameter or nozzle exit, whichever is larger\): this airframe cannot carry this engine\.)?(?: The body length (\S+) m is shorter than the engine length (\S+) m: this airframe cannot carry this engine\.)?$/,
         function (_t, cap, zarf, boy, motorBoy) {
             return 'Uçuş çözülmedi: gövde, taşıması istenen motordan küçük.'
                 + (cap ? ' Gövde dış çapı ' + I18N_SAYI(cap) + ' mm, motor zarfından ('
                     + I18N_SAYI(zarf) + ' mm; kasa/kamara dış çapı ya da lüle çıkışı, '
                     + 'hangisi büyükse) küçük: bu gövde bu motoru taşıyamaz.' : '')
                 + (boy ? ' Gövde boyu ' + I18N_SAYI(boy) + ' m, motor boyundan ('
                     + I18N_SAYI(motorBoy) + ' m) kısa: bu gövde bu motoru taşıyamaz.' : '');
         }],
        /* V307/AĞIRLIK-MERKEZİ — 6-DOF ucunun kanat kuralı reddi (app.py
           six_dof_analysis, fin_rule_not_met). Ağırlık merkezi bileşenlerden
           kurulunca sıvı örnek bu dala düşer; TR karşılığı Fırlatma
           Sahası sözlüğündeki aynı cümleyle (i18n_launch_site.js site.finRuleNotMet)
           AYNI metin. */
        [/^No fin span up to (\S+) m keeps the static margin above the stability threshold with these fin chords and this body( \(no fins to size: the fin count or root chord is 0\))?\. Enter the fin geometry, lengthen the fin chords or the body, or move mass forward\. Nothing was flown\.$/,
         function (_t, enCok, kanatYok) {
             return 'Bu kanatçık veterleri ve bu gövdeyle ' + I18N_SAYI(enCok)
                 + ' m\'ye kadar hiçbir kanatçık açıklığı statik marjı kararlılık eşiğinin üstünde tutmuyor'
                 + (kanatYok ? ' (boyutlandırılacak kanatçık yok: kanatçık sayısı ya da kök veteri 0)' : '')
                 + '. Kanatçık geometrisini girin, veterleri ya da gövdeyi uzatın veya kütleyi öne alın. Uçuş yapılmadı.';
         }],
        /* V307/AĞIRLIK-MERKEZİ — bileşen ağırlık merkezi kurulamadı
           (flight_vehicle.component_cg; uç 422 centre_of_gravity_not_built).
           Arayüzden ulaşılabilen iki dal: itici ya da kuru kütle motorunkiyle
           uyuşmuyor. Sayılar sunucudan. */
        [/^The propellant mass (\S+) kg is not the (\S+) kg the engine burns in flight, so the engine tanks cannot place it: the centre of gravity from components is not built\. Restore the engine's propellant mass or enter the centre of gravity \(component table\)\. Nothing was integrated\.$/,
         function (_t, p, yanan) {
             return 'İtici kütlesi ' + I18N_SAYI(p) + ' kg, motorun uçuşta yaktığı '
                 + I18N_SAYI(yanan) + ' kg değil; motorun tankları bu kütleyi yerleştiremez: '
                 + 'ağırlık merkezi bileşenlerden kurulmadı. Motorun itici kütlesini geri yazın '
                 + 'ya da ağırlık merkezini girin (bileşen tablosu). Uçuş hesaplanmadı.';
         }],
        [/^The dry mass (\S+) kg is below the (\S+) kg the engine flies with \(dry items \+ propellant left in the tanks\), so the centre of gravity from components is not built\. Enter at least the engine flying dry mass or the centre of gravity \(component table\)\. Nothing was integrated\.$/,
         function (_t, kuru, motor) {
             return 'Kuru kütle ' + I18N_SAYI(kuru) + ' kg, motorun uçuşta taşıdığı '
                 + I18N_SAYI(motor) + ' kg\'dan (kuru kalemler + tanklarda kalan itici) küçük; '
                 + 'ağırlık merkezi bileşenlerden kurulmadı. En az motorun uçan kuru kütlesini '
                 + 'ya da ağırlık merkezini (bileşen tablosu) girin. Uçuş hesaplanmadı.';
         }],
        /* V307 DİL-SUNUCU-2 (kalem 3, AĞIRLIK-MERKEZİ-2 DEVİR 2) — FAYDALI
           YÜK retleri. Üretici: hrma/app.py six_dof_analysis
           (payload_needs_component_cg, 422) ve hrma/analysis/flight_vehicle.py
           _payload_gate / component_cg (PAYLOAD_INCOMPLETE,
           PAYLOAD_OUTSIDE_BODY, DRY_MASS_BELOW_ENGINE_AND_PAYLOAD,
           LAYOUT_NUMBER_INVALID yük alanları; uç ' Nothing was integrated.'
           ekler). Motor sayfası 6-DOF paneli ve Fırlatma Sahası cümleyi
           serverText ile basar. Terimler sixdof.help.payloadMass /
           payloadStation TR metniyle aynı. Yalnız dize şablonları: PDF
           çevirmeni (rapor_sozluk.py) ve bekçi de aynı kuralları koşar.
           Sayılar sunucudan; yalnız ondalık kanonundan geçer. */
        [/^The payload mass and station are placed only in the centre of gravity built from the engine components \(derived airframe, simple mass mode\)\. With your own airframe or centre of gravity, put the payload in your mass budget\. Nothing was integrated\.$/,
         'Faydalı yükün kütlesi ve konumu yalnız motorun kütle kalemlerinden kurulan ağırlık merkezine (türetilmiş gövde, basit kütle kipi) konur. Kendi gövdenizle ya da kendi ağırlık merkezinizle faydalı yükü kendi kütle bütçenize yazın. Uçuş hesaplanmadı.'],
        [/^The payload needs both its mass and its station from the nose tip\. Nothing was integrated\.$/,
         'Faydalı yük için hem kütlesi hem burun ucundan konumu gerekir. Uçuş hesaplanmadı.'],
        [/^The payload station (\S+) m from the nose tip is beyond the (\S+) m body\. Nothing was integrated\.$/,
         'Faydalı yükün burun ucundan $1 m konumu, $2 m gövdenin dışında kalıyor. Uçuş hesaplanmadı.'],
        [/^The dry mass (\S+) kg is below the (\S+) kg the engine flies with plus the (\S+) kg payload, so the centre of gravity from components is not built\. The payload is part of the dry mass\. Nothing was integrated\.$/,
         'Kuru kütle $1 kg, motorun uçuşta taşıdığı $2 kg ile $3 kg faydalı yükün toplamından küçük; ağırlık merkezi bileşenlerden kurulmadı. Faydalı yük kuru kütlenin parçasıdır. Uçuş hesaplanmadı.'],
        [/^payload_mass must be a finite number 0 or above\. Nothing was integrated\.$/,
         'Faydalı Yük Kütlesi sonlu bir sayı olmalı ve 0 ya da büyük olmalı. Uçuş hesaplanmadı.'],
        [/^payload_station must be a finite number above 0\. Nothing was integrated\.$/,
         'Faydalı Yük Konumu sonlu bir sayı olmalı ve 0\'dan büyük olmalı. Uçuş hesaplanmadı.'],
        /* V3 KK 3. tur (15 Eki, §28-50 (c)) — FIRLATMA SAHASI ARAÇ KÜNYESİ.
           Üretici: hrma/analysis/flight_vehicle.py _hybrid_inert_note /
           _liquid_inert_mass (engine_inert_mass_note). Dayanak kuyruğu
           (motorun dry_mass_basis cümlesi) bu sözlüğün KENDİ çekirdeğinden
           geçer; çevrilemezse cümlenin TAMAMI İngilizce kalır (fail-closed:
           yarı Türkçe karışık metin yok). Oran ondalık kanonundan geçer. */
        [/^dry mass computed by the motor structural model, NOT the (\S+) rule of thumb(?:; measured dry\/propellant ratio (\S+))?(?:; basis: ([\s\S]+))?$/,
         function (_t, oran, olcum, dayanak) {
             var d = '';
             if (dayanak) {
                 var c = sunucuCevir(dayanak, currentLang());
                 if (c === null) return _t;
                 d = '; dayanak: ' + c;
             }
             return 'kuru kütle motorun yapısal modelince hesaplandı, '
                 + I18N_SAYI(oran) + ' başparmak kuralından DEĞİL'
                 + (olcum ? '; ölçülen kuru/itici oranı ' + I18N_SAYI(olcum) : '')
                 + d;
         }],
        [/^estimated as ~(\S+) x propellant mass \(hybrid dry mass has no component breakdown\)$/,
         function (_t, oran) {
             return 'itici kütlesinin ~' + I18N_SAYI(oran) + ' katı olarak'
                 + ' kestirildi (hibrit kuru kütlesinin bileşen dökümü yok)';
         }],
        [/^hybrid dry mass not published by the motor model(?: \(([\s\S]+)\))?$/,
         function (_t, dayanak) {
             var d = '';
             if (dayanak) {
                 var c = sunucuCevir(dayanak, currentLang());
                 if (c === null) return _t;
                 d = ' (' + c + ')';
             }
             return 'hibrit kuru kütlesi motor modelince yayımlanmadı' + d;
         }],
        [/^flying inert mass = ([\s\S]+); the nominal burned propellant is reported separately \(no double counting\)$/,
         function (_t, parcalar) {
             var adlar = {
                 'engine dry mass': 'motor kuru kütlesi',
                 'propellant tank dry structure': 'itici tankı kuru yapısı',
                 'loaded-minus-nominal (reserve) propellant':
                     'yüklenen eksi nominal (yedek) itici'
             };
             var out = [];
             var liste = parcalar.split(' + ');
             for (var i = 0; i < liste.length; i++) {
                 var m = /^(.+) (\d+(?:\.\d+)?) kg$/.exec(liste[i]);
                 if (!m || !Object.prototype.hasOwnProperty.call(adlar, m[1])) {
                     return _t;
                 }
                 out.push(adlar[m[1]] + ' ' + I18N_SAYI(m[2]) + ' kg');
             }
             return 'uçan atıl kütle = ' + out.join(' + ')
                 + '; nominal yanan itici ayrıca raporlanır (çift sayım yok)';
         }],
        /* V306/SIVI-KÜTLE (M-SIVI-1) — sıvı uçan atıl kütle künyesinin araç
           kalemi eki (hrma/analysis/flight_vehicle.py
           VEHICLE_ITEMS_NOT_IN_ENGINE_NOTE): kumanda / aviyonik motor kuru
           kütlesinde değil. Gövde bu sözlüğün kendi çekirdeğinden geçer;
           çevrilemezse cümlenin TAMAMI İngilizce kalır (fail-closed). */
        [/^([\s\S]+); not in the engine dry mass: controls \/ avionics \(controller box, harness, sensors\), a vehicle item HRMA does not estimate - include it in the airframe dry mass$/,
         function (_t, govde) {
             var g = sunucuCevir(govde, currentLang());
             if (g === null || g === govde) return _t;
             return g + '; motor kuru kütlesinde yok: kumanda / aviyonik'
                 + ' (denetleyici kutusu, kablo demeti, sensörler), HRMA\'nın'
                 + ' tahmin etmediği bir araç kalemi; gövde kuru kütlesine ekleyin';
         }],
        /* V3 KK 2. tur (CFDS devri) — CFD ucunun ``runtime_basis`` cümlesi
           (hrma/app.py api_cfd_nozzle; panelde RUNTIME rozetinin ipucu,
           cfd_panel.js SRV). İki biçim: bugünkü main cümlesi ve V3
           cfd-sure dalının (_cfd_runtime_basis) cümlesi. Saniye yakalaması
           ondalık kanonundan geçer. FAIL-CLOSED: ölçülmemiş hücre ('None')
           ya da çevrilemeyen kuyruk (ölçüm koşulu metni) varsa cümle
           ÇEVRİLMEZ (girdiyle özdeş dönüş = "çevrilmedi"); yarı Türkçe
           karışık metin üretilmez, sayı uydurulmaz. */
        [/^solver_runtime_s is the steady driver itself, runtime_s the whole request \(validation, grid, solve, separation, thinning\)\. Measured worst case for this level and backend: (\S+) s\.$/,
         function (_t, saniye) {
             if (!/^\d+(?:\.\d+)?$/.test(saniye)) return _t;
             return CFD_SURE_GOVDE_TR + ' Bu seviye ve arka uç için ölçülen en kötü süre: '
                 + I18N_SAYI(saniye) + ' s.';
         }],
        [/^solver_runtime_s is the steady driver itself, runtime_s the whole request \(validation, grid, solve, separation, thinning\)\. Measured worst case for this level and backend: (.+?) - (inviscid \(Euler\)|viscous, turbulence '([\w-]+)') run, level '([\w-]+)', backend '([\w-]+)', from (CFD_[A-Z_]+)\. ([\s\S]+)$/,
         function (_t, beyan, _kipHam, turb, seviye, arkaUc, tablo, kuyruk) {
             var b;
             var sn = /^(\d+(?:\.\d+)?) s$/.exec(beyan);
             var olcm = /^NOT MEASURED \(this cell has no value in (CFD_[A-Z_]+); no estimate is published in its place\)$/.exec(beyan);
             if (sn) {
                 b = I18N_SAYI(sn[1]) + ' s';
             } else if (olcm) {
                 b = 'ÖLÇÜLMEDİ (' + olcm[1] + ' tablosunda bu hücrenin değeri yok; yerine tahmin yayımlanmaz)';
             } else {
                 return _t;
             }
             var kuyrukTr = sunucuCevir(kuyruk, currentLang());
             if (kuyrukTr === null) return _t;
             var kip = turb ? ("viskoz, türbülans '" + turb + "'")
                            : 'viskozsuz (Euler)';
             return CFD_SURE_GOVDE_TR + ' Bu seviye ve arka uç için ölçülen en kötü süre: '
                 + b + ' — ' + kip + " koşusu, seviye '" + seviye
                 + "', arka uç '" + arkaUc + "', kaynak " + tablo + '. '
                 + kuyrukTr;
         }],
        /* ÖH V3 cfd-sure 4. tur (15 Eki, ana model) — runtime_basis cümlesinin
           KUYRUĞU: iki en kötü hâl tablosunun ölçüm koşulu
           (hrma/app.py CFD_WORST_CASE_MEASURED_ON; beyan_uret.py üretir).
           Euler hücreleri sakin, viskoz hücreler yüklü ölçümden — metin iki
           koşulu ayrı söyler. Sayılar yakalanır (uydurma yok); biçim tutmazsa
           eşleşmez ve üst desen bütün cümleyi çevirmeden bırakır (fail-closed). */
        [/^Measured on (.+?) \((\d+) cores; numba with NUMBA_NUM_THREADS=(\d+), the product default\)\. Inviscid \(Euler\) cells: on ([\d, -]+) \(1-minute load average (\d+)-(\d+) before each run\)\. Viscous cells: on ([\d, -]+) with other jobs running \(1-minute load average (\d+)-(\d+)\): a loaded machine, so those numbers are a cautious upper bound, not quiet-machine figures\. Method: each level\/backend cell runs to the iteration ceiling \((\d+) iterations, early exit disabled, JIT warm-up excluded\) for the no-back-pressure case and for the shocked back-pressure case, at least (\d+) repeats each; the published value is the largest measured runtime_s rounded up to 0\.1 s\.$/,
         function (_t, marka, cekirdek, isParcacigi, eGun, eMin, eMax, vGun, vMin, vMax, tavan, tekrar) {
             return marka + ' üzerinde ölçüldü (' + cekirdek
                 + ' çekirdek; numba, NUMBA_NUM_THREADS=' + isParcacigi
                 + ', ürün varsayılanı). Viskozsuz (Euler) hücreler: ' + eGun
                 + ' (her koşudan önce 1 dakikalık yük ortalaması ' + eMin + '-' + eMax
                 + '). Viskoz hücreler: ' + vGun
                 + ', makinede başka işler çalışırken (1 dakikalık yük ortalaması '
                 + vMin + '-' + vMax + '): yüklü makine, bu yüzden bu sayılar temkinli'
                 + ' bir üst sınırdır, sessiz makine değeri değildir. Yöntem: her'
                 + ' seviye/arka uç hücresi yineleme tavanına kadar koşar (' + tavan
                 + ' yineleme, erken çıkış kapalı, JIT ısınması hariç); geri basınçsız'
                 + ' vaka ve şoklu geri basınçlı vaka için her biri en az ' + tekrar
                 + ' tekrar; yayımlanan değer, ölçülen en büyük runtime_s değerinin 0,1 s'
                 + "'ye yukarı yuvarlanmışıdır.";
         }],
        /* ÖH D35 / OH-GT-21 (22 Eylül 2026) — enjektör plakası emniyet
           katsayısı uyarısı. hrma/utils/injector_design.py:1849; dört sayı
           taşıdığı için sözlüğe değil desene girer. Sayılar YAKALANAN
           üzerinden ondalık kanonundan geçer (OH-GT-24(d)). */
        [/^Injector plate safety factor (\S+) is below the target (\S+): (\S+) mm required, (\S+) mm given \((.+)\)\.$/,
         'Enjektör plakası emniyet katsayısı $1, hedef $2 değerinin altında: $3 mm gerekli, $4 mm verildi ($5).'],
        /* V307/PLAKA-MARŞ (19 Kas 2026) — iki yük durumlu plaka uyarısı
           (hrma/app.py ``_enjektor_plaka_iki_durum``): durum adı sabit
           gövdeye girer, sayılar yakalanır. */
        [/^Injector plate safety factor (\S+) is below the target (\S+) in the operating load case \(face load (\S+) bar\): (\S+) mm required, (\S+) mm given \((.+)\)\.$/,
         'Enjektör plakası emniyet katsayısı $1, çalışma yük durumunda hedef $2 değerinin altında (yüzey yükü $3 bar): $4 mm gerekli, $5 mm verildi ($6).'],
        [/^Injector plate safety factor (\S+) is below the target (\S+) in the start\/shutdown load case \(face load (\S+) bar\): (\S+) mm required, (\S+) mm given \((.+)\)\.$/,
         'Enjektör plakası emniyet katsayısı $1, marş/kesme yük durumunda hedef $2 değerinin altında (yüzey yükü $3 bar): $4 mm gerekli, $5 mm verildi ($6).'],
        /* ÖH D36 / dil2-i18n-pdf a2 (K4) — patlayıcı sınıfı dayanağı:
           hrma/analysis/safety_analysis.py _resolve_explosive_class. İlki
           GERİ ÇEKME cümlesidir (explosive_verdict_withheld_because ile
           explosive_class_basis aynı dizeyi taşır); itici adı ve sınıf
           listesi yakalanır, sabit gövde çevrilir. Hibrit çözümleyicinin
           uzun dayanak cümleleri burada YOK: onlar İngilizce aynen kalır. */
        [/^propellant_type '(.+)' is not a tabulated class and no motor_type was supplied, so no TNT-equivalent class was won\. Tabulated classes: (.+)\. Supply motor_type \('solid' \| 'hybrid' \| 'liquid'\) or a tabulated propellant_type to have the explosive verdict computed\.$/,
         "propellant_type '$1' tablodaki bir sınıf değil ve motor_type verilmedi; bu yüzden hiçbir TNT eşdeğeri sınıfı kazanılmadı. Tablodaki sınıflar: $2. Patlayıcı hükmünün hesaplanması için motor_type ('solid' | 'hybrid' | 'liquid') ya da tablodaki bir propellant_type verin."],
        [/^propellant_type '(.+)' matched the TNT-equivalent table$/,
         "propellant_type '$1' TNT eşdeğeri tablosuyla eşleşti"],
        /* Toksik envanter dayanağı, tablolanmış bileşeni olmayan sınıf
           (ör. 'composite'): sınıf adı yakalanır. */
        [/^'(.+)' has no tabulated toxic component in HRMA, so no toxic inventory is reported\. SCOPE: this covers the stored propellant only\. Combustion PRODUCTS \(for example HCl and alumina from ammonium-perchlorate composites\) are NOT inventoried by this analysis\.$/,
         "'$1' için HRMA'da tablolanmış toksik bileşen yok, bu yüzden toksik envanter bildirilmiyor. KAPSAM: bu yalnız depolanan iticiyi kapsar. Yanma ÜRÜNLERİ (örneğin amonyum perkloratlı kompozitlerden HCl ve alümina) bu analizde envantere ALINMAZ."],
        /* ÖH D36 / dil2-i18n-pdf a2 (taban kırmızısı) — kanon delik planının
           imalat bandı beyanı. hrma/utils/injector_design.py:836 (D35 /
           OH-ON-01) düz metin üretir; {code, params} kaydı yok, bu yüzden
           çeviri burada, desende. ÖLÇÜLDÜ (bb7ee57c,
           tests/test_i18n_charts.py kapsam bekçisi): gerçek /calculate
           yanıtında çevrilemeyen TEK mesajdı, kapsam %92,3 (< %95).
           Bant uçları AYRI yakalanır: '0.30-2.00' bütün hâlde saf ondalık
           değildir ve YAKALANAN onu olduğu gibi bırakırdı. */
        [/^Solved orifice diameter (\S+) mm is outside the manufacturing band \((\S+)-(\S+) mm\)\. The hole plan comes from the injector circuit solution and is NOT resized here: resizing would publish a second, different injector in the same answer\. Either widen the band or change the feed pressure \/ orifice count\.$/,
         'Çözülen orifis çapı $1 mm, imalat bandının ($2-$3 mm) dışında. Delik planı enjektör devresi çözümünden gelir ve burada yeniden BOYUTLANDIRILMAZ: yeniden boyutlandırmak aynı yanıtta ikinci, farklı bir enjektör yayımlamak olurdu. Ya bandı genişletin ya da besleme basıncını / orifis sayısını değiştirin.'],
        /* ÖH D37 A2 hibrit · 9. tur (7. tur Devir 36) — kanon DIŞI duş
           başlığı kırpma gövdesi (hrma/utils/injector_design.py
           _calculate_showerhead). Eski gövde "to preserve target flow rate"
           diyordu; yeni gövde hedef debi sınıfıyla uyumlu. Teslim cümlesi
           KUYRUK_DESENLERI dizisinden ayrı çevrilir. İstenen delik sayısı cümlesi
           isteğe bağlıdır (otomatik planda yok). */
        [/^Hole diameter clamped to manufacturing band \((\S+)-(\S+) mm\); hole count adjusted to (\S+) to cover the injection area required for the target flow at the design pressure drop\.(?: The requested hole count \((\S+)\) was NOT delivered\.)?$/,
         function (_t, lo, hi, n, istenen) {
             return 'Delik çapı imalat bandına (' + I18N_SAYI(lo) + '-'
                 + I18N_SAYI(hi) + ' mm) kırpıldı; delik sayısı, hedef '
                 + 'debinin tasarım basınç düşümünde gerektirdiği enjeksiyon '
                 + 'alanını karşılamak için ' + n + ' olarak ayarlandı.'
                 + (istenen ? ' İstenen delik sayısı (' + istenen
                    + ') TESLİM EDİLMEDİ.' : '');
         }],
        /* ÖH D37 A2 hibrit · 9. tur (7. tur Devir 37) — kullanıcının
           sabitlediği çarpışmalı delik çapı (orifice_diameter; d_min = d_max)
           kırpma gövdesi. Teslim cümlesi kuyruktan çevrilir. */
        [/^Hole diameter fixed by the request at (\S+) mm \(orifice_diameter\): (the requested|the auto-selected minimum of) (\S+) doublet pairs would need (\S+) mm holes for the target flow at the design pressure drop, so the plan uses (\S+) pairs of (\S+) mm holes\.$/,
         function (_t, d_sabit, kaynak, n_ist, d_gerek, n_plan, d_plan) {
             return 'Delik çapı istekte ' + I18N_SAYI(d_sabit)
                 + ' mm olarak sabitlendi (orifice_diameter): '
                 + (kaynak === 'the requested' ? 'istenen '
                    : 'otomatik seçilen en az ')
                 + n_ist + ' çarpışmalı jet çifti, tasarım basınç düşümünde '
                 + 'hedef debi için ' + I18N_SAYI(d_gerek) + ' mm delik '
                 + 'gerektirirdi; bu yüzden plan ' + n_plan + ' çift × '
                 + I18N_SAYI(d_plan) + ' mm delik kullanır.';
         }],
        /* ÖH D37 A2 hibrit · 10. tur (HB9 devir 47) — çarpışmalı kırpmanın
           iki eski gövdesi (hrma/utils/injector_design.py, çap banda
           sığmadı): (a) istenen çift yeniden çözüldü, (b) çift değişmedi /
           otomatik en az çift, delik kırpıldı. 9. turdan beri teslim
           kuyruğu KUYRUK_DESENLERI ile ayrılıyordu ama gövdenin deseni
           yoktu: TR arayüzde metin fail-closed İngilizce kalıyordu.
           Sayılar I18N_SAYI ile (ondalık virgül). */
        [/^Requested (\S+) doublet pairs would need (\S+) mm holes, outside the manufacturing band \((\S+)-(\S+) mm\); the pair count was re-solved to (\S+) pairs of (\S+) mm holes\.$/,
         function (_t, n_ist, d_gerek, lo, hi, n_plan, d_plan) {
             return 'İstenen ' + n_ist + ' çarpışmalı jet çifti '
                 + I18N_SAYI(d_gerek) + ' mm delik gerektirirdi; bu, imalat '
                 + 'bandının (' + I18N_SAYI(lo) + '-' + I18N_SAYI(hi)
                 + ' mm) dışında. Çift sayısı ' + n_plan + ' çift × '
                 + I18N_SAYI(d_plan) + ' mm deliğe yeniden çözüldü.';
         }],
        [/^(Requested|The auto-selected minimum of) (\S+) doublet pairs would need (\S+) mm holes, outside the manufacturing band \((\S+)-(\S+) mm\); the holes were clamped to (\S+) mm with (\S+) pairs, so the injection area is (\S+) mm\^2 against the (\S+) mm\^2 required for the target flow at the design pressure drop \(ratio (\S+)\); the exit velocity is divided by the same ratio\.$/,
         function (_t, kaynak, n_ist, d_gerek, lo, hi, d_plan, n_plan,
                   a_tes, a_ger, oran) {
             return (kaynak === 'Requested' ? 'İstenen '
                     : 'Otomatik seçilen en az ')
                 + n_ist + ' çarpışmalı jet çifti ' + I18N_SAYI(d_gerek)
                 + ' mm delik gerektirirdi; bu, imalat bandının ('
                 + I18N_SAYI(lo) + '-' + I18N_SAYI(hi) + ' mm) dışında. '
                 + 'Delikler ' + n_plan + ' çiftle ' + I18N_SAYI(d_plan)
                 + ' mm\'ye kırpıldı; enjeksiyon alanı ' + I18N_SAYI(a_tes)
                 + ' mm², hedef debinin tasarım basınç düşümünde gerektirdiği '
                 + I18N_SAYI(a_ger) + ' mm²\'ye karşı (oran '
                 + I18N_SAYI(oran) + '); çıkış hızı aynı orana bölünür.';
         }],
        /* ÖH D20 / P12aB4-15 — proje deposu ve STEP içe aktarımının sunucu
           metinleri. Ölçüldü (raw/OH/D20/electron/a1/once.json): bu dört
           mesaj TR kipinde bildirimlerde İngilizce çıkıyordu; boşluk hem
           ÇAĞRI (project_bar.js / step_import_ui.js `serverText`
           çağırmıyordu) hem SÖZLÜK tarafındaydı. Metinler
           hrma/utils/projects.py tarafından üretilen hâlleriyle eşleşir. */
        [/^Project name is a reserved device name$/,
         'Proje adı Windows\'ta bir aygıt için ayrılmış bir addır'],
        [/^Project '(.+)' not found$/, "'$1' adlı proje bulunamadı"],
        [/^Project document is (.+) bytes; limit is (.+) bytes \(1 MB\)$/,
         'Proje belgesi $1 bayt; sınır $2 bayt (1 MB)'],
        [/^payload\.format_version must be (.+)$/,
         'payload.format_version $1 olmalı'],
        [/^Project name must be a string$/, 'Proje adı bir dize olmalı'],
        [/^Project name must not start with a dot$/,
         'Proje adı nokta ile başlayamaz'],
        [/^Project name must not end with a dot or space$/,
         'Proje adı nokta ya da boşluk ile bitemez'],
        // v2.6.27 — turbopompa (C1) ve basincli kap boyutlandirma uyarilari.
        // Ucu de sayi tasidigi icin birebir sozluge degil desene giriyor
        // (dosya kurali: sabit metin -> sozluk, sayili metin -> PATTERNS).
        [/^NPSH margin is non-positive \(available (.+) m, required (.+) m at Nss capability (.+)\); reduce shaft speed or raise tank pressure\.$/,
         'NPSH marjı pozitif değil (mevcut $1 m, gereken $2 m; Nss kapasitesi $3); mil hızını düşürün ya da tank basıncını yükseltin.'],
        [/^supplied shaft speed (.+) rpm exceeds the suction-limited maximum (.+) rpm for the target suction capability Nss (.+); NPSH margin will be negative\.$/,
         'Verilen mil hızı $1 rpm, hedef emme kapasitesi Nss $3 için emme sınırlı en yüksek hız olan $2 rpm değerini aşıyor; NPSH marjı negatif olacak.'],
        [/^Wall thickness not supplied — sized to satisfy both the code minimum \((.+) mm\) and a burst margin of (.+) against the required burst pressure \((.+) mm\); using (.+) mm\.$/,
         'Cidar kalınlığı verilmedi — hem yönetmelik alt sınırını ($1 mm) hem de gereken patlama basıncına karşı $2 katlık patlama marjını ($3 mm) sağlayacak biçimde boyutlandırıldı; kullanılan değer $4 mm.'],
        /* V307 DİL-SUNUCU (kalem 2 + ÜB-4) — BASINÇLI KAP uyarı ve
           varsayım satırları. Üretici: hrma/analysis/pressure_vessel.py
           analyze() (warnings / assumptions). Yalnız dize şablonları: PDF
           (rapor_sozluk.py) de aynı kuralları koşar. Kriyojenik uyarının
           ortak başı + altı dalı ayrı kural (her biri tam cümle). */
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. WARNING: this material is BRITTLE AT EVERY TEMPERATURE \(carbon \/ ceramic matrix, no ductile regime\), so there is no ductile-to-brittle transition to be above\. It is NOT covered by the ASME BPVC VIII-1 UHA-51 low-temperature exemptions, which apply to austenitic stainless, aluminium, copper and nickel alloys only\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. UYARI: bu malzeme HER SICAKLIKTA GEVREKTİR (karbon / seramik matris, sünek rejimi yok); bu yüzden üstünde kalınabilecek bir sünek-gevrek geçişi yoktur. Yalnız östenitik paslanmaz, alüminyum, bakır ve nikel alaşımlarına uygulanan ASME BPVC VIII-1 UHA-51 düşük sıcaklık muafiyetlerinin KAPSAMINDA DEĞİLDİR.'],
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. This module could not resolve the material name (.+) in the materials database, so it makes NO claim about its low-temperature ductility: verify the DBTT of the actual grade before cryogenic service\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. Bu modül $2 malzeme adını malzeme veritabanında çözemedi; bu yüzden düşük sıcaklık sünekliği hakkında HİÇBİR iddiada bulunmaz: kriyojenik işletmeden önce gerçek kalitenin DBTT değerini doğrulayın.'],
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. The materials database resolves this entry \((.+)\) but records NO qualified low-temperature ductility verdict for it \(its low-temperature ductility class is neither 'ductile when cold' nor 'DBTT-sensitive'\), so this module makes NO claim either way and grants NO ASME BPVC VIII-1 UHA-51 exemption: qualify the actual grade against its DBTT before cryogenic service\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. Malzeme veritabanı bu kaydı ($2) çözüyor, ama onun için kalifiye edilmiş bir düşük sıcaklık süneklik hükmü KAYDETMİYOR (düşük sıcaklık süneklik sınıfı ne \'soğukta sünek\' ne de \'DBTT\'ye duyarlı\'); bu yüzden bu modül iki yönde de HİÇBİR iddiada bulunmaz ve ASME BPVC VIII-1 UHA-51 muafiyeti VERMEZ: kriyojenik işletmeden önce gerçek kaliteyi DBTT değerine göre kalifiye edin.'],
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. WARNING: this material family \(ferritic \/ martensitic steel or bcc refractory\) is DBTT-sensitive and is NOT exempt from low-temperature impact testing \(ASME BPVC VIII-1 UCS-66\) — brittle fracture risk\. Consider an austenitic stainless, aluminium or nickel alloy for cryogenic tanks\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. UYARI: bu malzeme ailesi (ferritik / martenzitik çelik ya da hacim merkezli kübik refrakter metal) DBTT\'ye duyarlıdır ve düşük sıcaklık darbe testinden MUAF DEĞİLDİR (ASME BPVC VIII-1 UCS-66) — gevrek kırılma riski. Kriyojenik tanklar için östenitik paslanmaz, alüminyum ya da nikel alaşımı düşünün.'],
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. Austenitic stainless, aluminium, copper and nickel alloys stay ductile when cold \(ASME BPVC VIII-1 UHA-51 exemptions\), but the specific grade and weld procedure still require qualification\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. Östenitik paslanmaz, alüminyum, bakır ve nikel alaşımları soğukta sünek kalır (ASME BPVC VIII-1 UHA-51 muafiyetleri), ama belirli kalite ve kaynak yöntemi yine de kalifikasyon gerektirir.'],
        [/^Cryogenic service \((\S+) K\): material suitability must be verified against the ductile-to-brittle transition temperature \(DBTT\); this module does not model low-temperature fracture toughness\. WARNING: this material is NOT among the families covered by the ASME BPVC VIII-1 UHA-51 low-temperature exemptions \(austenitic stainless, aluminium, copper and nickel alloys\)\. Titanium, magnesium and refractory alloys in particular need their own low-temperature toughness qualification; no exemption is assumed here\.$/,
         'Kriyojenik işletme ($1 K): malzemenin uygunluğu sünek-gevrek geçiş sıcaklığına (DBTT) göre doğrulanmalıdır; bu modül düşük sıcaklık kırılma tokluğunu modellemez. UYARI: bu malzeme ASME BPVC VIII-1 UHA-51 düşük sıcaklık muafiyetlerinin kapsadığı ailelerden (östenitik paslanmaz, alüminyum, bakır ve nikel alaşımları) DEĞİLDİR. Özellikle titanyum, magnezyum ve refrakter alaşımlar kendi düşük sıcaklık tokluk kalifikasyonlarını gerektirir; burada muafiyet varsayılmaz.'],
        [/^Low-temperature fracture toughness \(ductile-to-brittle transition\) is NOT modelled by this module\. For a DBTT-sensitive material family in cryogenic service the governing failure mode is therefore outside the analysis, so a PASS\/MARGINAL verdict cannot be earned: the strength and burst checks below say nothing about brittle fracture\. Qualify the grade to ASME BPVC VIII-1 UCS-66 \(impact testing\) or choose an austenitic stainless, aluminium or nickel alloy\.$/,
         'Düşük sıcaklık kırılma tokluğu (sünek-gevrek geçiş) bu modülde MODELLENMEZ. Kriyojenik işletmedeki DBTT\'ye duyarlı bir malzeme ailesi için belirleyici hasar biçimi bu yüzden analizin dışındadır; GEÇTİ / SINIRDA hükmü kazanılamaz: aşağıdaki dayanım ve patlama denetimleri gevrek kırılma hakkında hiçbir şey söylemez. Kaliteyi ASME BPVC VIII-1 UCS-66\'ya göre (darbe testi) kalifiye edin ya da östenitik paslanmaz, alüminyum veya nikel alaşımı seçin.'],
        [/^Verdict withheld: the governing failure mode at this temperature \(brittle fracture of a DBTT-sensitive material\) is not modelled here, so no acceptance can be granted \(status = NOT_EVALUATED\)\. The strength and burst numbers below remain valid on their own terms\.$/,
         'Hüküm verilmedi: bu sıcaklıktaki belirleyici hasar biçimi (DBTT\'ye duyarlı bir malzemenin gevrek kırılması) burada modellenmez; bu yüzden kabul verilemez (durum: DEĞERLENDİRİLMEDİ). Aşağıdaki dayanım ve patlama sayıları kendi koşullarında geçerli kalır.'],
        [/^Design temperature (\S+) K exceeds the material's maximum structural service temperature \((\S+) K\) — vessel is NOT acceptable at this temperature\.$/,
         'Tasarım sıcaklığı $1 K, malzemenin en yüksek yapısal servis sıcaklığını ($2 K) aşıyor — kap bu sıcaklıkta KABUL EDİLEMEZ.'],
        [/^Material strength derated to (\S+)% of room-temperature values at (\S+) C \(MMPDS-style retention curve\)\.$/,
         'Malzeme dayanımı $2 °C\'de oda sıcaklığı değerlerinin %$1 düzeyine düşürüldü (MMPDS tarzı dayanım korunum eğrisi).'],
        [/^Design temperature (\S+) C is below the lowest point of the material derating curve \((\S+) C\) — room-temperature strength is assumed\. Real metals gain strength when cold, so this is conservative for strength but says NOTHING about low-temperature toughness\.$/,
         'Tasarım sıcaklığı $1 °C, malzemenin dayanım düşürme eğrisinin en alt noktasının ($2 °C) altında — oda sıcaklığı dayanımı varsayılır. Gerçek metaller soğukta dayanım kazanır; bu, dayanım için tutucudur ama düşük sıcaklık tokluğu hakkında HİÇBİR ŞEY söylemez.'],
        [/^P > 0\.385\*S\*E — outside UG-27 thin-shell formula validity; ASME Appendix 1-2 thick-wall equations required \(results here are approximate\)\.$/,
         'P > 0,385·S·E — UG-27 ince kabuk bağıntısının geçerlilik alanı dışında; ASME Ek 1-2 kalın cidar denklemleri gerekir (buradaki sonuçlar yaklaşıktır).'],
        [/^Auto-sizing cannot reach the required burst pressure \((\S+) bar = (\S+) x (\S+) bar\) with this material at any wall thickness — the thin-wall plastic limit saturates at 2\*UTS\. Choose a stronger material or lower MEOP\.$/,
         'Otomatik boyutlandırma bu malzemeyle hiçbir cidar kalınlığında gereken patlama basıncına ($1 bar = $2 × $3 bar) ulaşamıyor — ince cidar plastik sınırı 2·UTS\'de doyuma ulaşır. Daha dayanımlı bir malzeme seçin ya da MEOP\'yi düşürün.'],
        [/^t\/r = (\S+) > 0\.1 — thin-wall assumptions degrade; thick-wall \(Lame\) analysis recommended for stress detail\. Burst estimate remains valid \(Faupel is a thick-wall model\)\.$/,
         't/r = $1 > 0,1 — ince cidar varsayımları zayıflar; gerilme ayrıntısı için kalın cidar (Lamé) analizi önerilir. Patlama kestirimi geçerli kalır (Faupel bir kalın cidar modelidir).'],
        [/^t > 0\.5\*R — outside UG-27 scope \(Appendix 1-2 governs\)\.$/,
         't > 0,5·R — UG-27 kapsamı dışında (Ek 1-2 geçerlidir).'],
        [/^HEAD UNDER-THICKNESS: the 2:1 ellipsoidal head needs (\S+) mm \(UG-32\) but only (\S+) mm is available\. The shell check passes on its own, but a vessel is not stronger than its head, so no overall PASS is issued\.$/,
         'KAPAK KALINLIĞI YETERSİZ: 2:1 elipsoidal kapak $1 mm gerektiriyor (UG-32), ama yalnız $2 mm var. Gövde denetimi tek başına geçiyor; ancak bir kap kapağından daha dayanıklı olamaz, bu yüzden genel GEÇTİ verilmez.'],
        [/^HEAD UNDER-THICKNESS: the torispherical head needs (\S+) mm \(UG-32\) but only (\S+) mm is available\. The shell check passes on its own, but a vessel is not stronger than its head, so no overall PASS is issued\.$/,
         'KAPAK KALINLIĞI YETERSİZ: torisferik kapak $1 mm gerektiriyor (UG-32), ama yalnız $2 mm var. Gövde denetimi tek başına geçiyor; ancak bir kap kapağından daha dayanıklı olamaz, bu yüzden genel GEÇTİ verilmez.'],
        [/^HEAD UNDER-THICKNESS: the hemispherical head needs (\S+) mm \(UG-32\) but only (\S+) mm is available\. The shell check passes on its own, but a vessel is not stronger than its head, so no overall PASS is issued\.$/,
         'KAPAK KALINLIĞI YETERSİZ: yarım küresel kapak $1 mm gerektiriyor (UG-32), ama yalnız $2 mm var. Gövde denetimi tek başına geçiyor; ancak bir kap kapağından daha dayanıklı olamaz, bu yüzden genel GEÇTİ verilmez.'],
        [/^Burst margin (\S+) is below (\S+) — acceptable but thin; consider material certification and manufacturing scatter\.$/,
         'Patlama marjı $1, $2 eşiğinin altında — kabul edilebilir ama ince; malzeme sertifikasını ve imalat saçılımını göz önünde bulundurun.'],
        [/^ASME allowable stress derived as min\(UTS\/3\.5, YS\/1\.5\) per Section II-D criteria from the material database \(approximate; code-tabulated values may differ\)\.$/,
         'ASME izin verilen gerilmesi, Section II-D ölçütlerine göre malzeme veritabanından min(UTS/3,5, YS/1,5) olarak türetildi (yaklaşık; standardın tablo değerleri farklı olabilir).'],
        [/^Thin-wall plastic-limit burst uses the mean-diameter membrane form P_b = 2\*UTS\*t\/\(D\+t\) \(approximate\)\.$/,
         'İnce cidar plastik sınır patlaması ortalama çaplı zar bağıntısını kullanır: P_b = 2·UTS·t/(D+t) (yaklaşık).'],
        [/^AIAA S-080 head thicknesses reuse ASME UG-32 geometry factors with S_eff = min\(YS\/1\.5, UTS\/2\.0\) \(approximate; S-080 specifies design factors, not closed-form head equations\)\.$/,
         'AIAA S-080 kapak kalınlıkları ASME UG-32 geometri katsayılarını S_eff = min(YS/1,5, UTS/2,0) ile kullanır (yaklaşık; S-080 tasarım katsayılarını verir, kapalı biçimli kapak denklemlerini vermez).'],
        [/^Temperature derating interpolated from the material database MMPDS-style retention curve \(short-time exposure\)\.$/,
         'Sıcaklık düşürmesi malzeme veritabanındaki MMPDS tarzı dayanım korunum eğrisinden ara değerlemeyle alındı (kısa süreli maruziyet).'],
        [/^Weld joint efficiency E = (\S+) is applied as a strength knock-down on the pressure boundary \(shell thickness, MAWP and burst assessment\), because the weld land is the governing section — ASME BPVC VIII-1 uses the same S\*E construction in UG-27\(c\)\(1\)\.$/,
         'Kaynak bağlantı verimi E = $1, basınç sınırında dayanım düşürmesi olarak uygulanır (gövde kalınlığı, MAWP ve patlama değerlendirmesi), çünkü belirleyici kesit kaynak bölgesidir — ASME BPVC VIII-1, UG-27(c)(1)\'de aynı S·E yapısını kullanır.'],
        [/^Head thickness was not supplied, so the head is checked against the SAME wall thickness as the shell \((\S+) mm\)\. If the head is formed from a different plate, supply its own thickness\.$/,
         'Kapak kalınlığı verilmedi; bu yüzden kapak, gövdeyle AYNI cidar kalınlığına göre denetlendi ($1 mm). Kapak farklı bir levhadan şekillendiriliyorsa kendi kalınlığını girin.'],
        /* V307 DİL-SUNUCU-2 (kalem 2) — PDF belgesinde en sık kalan BİÇİMLİ çözücü
           künyeleri (bugünkü kodda doğrulandı): solid_rocket_engine.py vakum
           nozulu önerisi ve iki faz durum gerekçesi, liquid_rocket_engine.py
           boğaz boşaltma katsayısı künyesi, safety_analysis.py zehirli envanter
           sınıf notu (iki kuyruk). Dize şablonları: PDF çevirmeni de koşar.
           Yakalanan değerler (kullanıcının yazdığı itici adı, sınıf adı)
           AYNEN taşınır. */
        [/^SUGGESTED vacuum-optimised nozzle \(4x the sea-level expansion ratio, capped at 40 for separation\/mass limits\)\. This motor is not built with it: the delivered nozzle has eps = (\S+) and isp_vacuum is computed for THAT nozzle\.$/,
         'ÖNERİLEN, vakum için eniyilenmiş nozul (deniz seviyesi genişleme oranının 4 katı, ayrılma/kütle sınırları için 40 ile sınırlı). Bu motor onunla yapılmaz: teslim edilen nozulun genişleme oranı $1 ve vakum Isp O nozul için hesaplanır.'],
        [/^X_p = (\S+) > 0 and no user multiplier was supplied, so the thrust coefficient carries NO two-phase factor at all \(two_phase_efficiency_applied = 1\.0\) even though the solver's own models estimate a non-zero loss for this state\.$/,
         'Yoğuşmuş faz kütle kesri $1 > 0 ve kullanıcı çarpanı verilmedi; bu yüzden itki katsayısı HİÇBİR iki fazlı katsayı taşımıyor (uygulanan iki faz verimi = 1,0), oysa çözücünün kendi modelleri bu durum için sıfırdan farklı bir kayıp tahmin ediyor.'],
        [/^nozzle throat discharge coefficient C_D used to size the geometric throat: A_t = mdot_main_chamber \* c_star \/ \(P_c \* C_D\)\. C_D = (\S+) is an ASSUMED engineering value, not a measured or document-cited number for this propellant pair\. It sits inside the published band for well designed converging-diverging throats \(discharge correction ~0\.98-1\.0; Sutton & Biblarz, "Rocket Propulsion Elements" 9th ed\., Ch\. 3\)\. HRMA has no throat boundary layer solution, so the value is NOT solved\. It is the term that closes Isp = C_F \* c_star \/ \(g0 \* C_D\): with C_D < 1 the geometric throat is larger than the effective one, so the published Isp exceeds C_F\*c_star\/g0 by exactly 1\/C_D$/,
         'geometrik boğazı boyutlandırmakta kullanılan nozul boğazı boşaltma katsayısı CD: At = ṁ(ana oda) · c* / (Pc · CD). CD = $1 VARSAYILMIŞ bir mühendislik değeridir; bu itici çifti için ölçülmüş ya da belgeyle gösterilmiş bir sayı değildir. İyi tasarlanmış daralan-genişleyen boğazlar için yayımlanmış bandın içindedir (boşaltma düzeltmesi ~0,98-1,0; Sutton & Biblarz, "Rocket Propulsion Elements" 9. bs., Bölüm 3). HRMA\'nın boğaz sınır tabakası çözümü yoktur; bu yüzden değer ÇÖZÜLMEZ. Isp = CF · c* / (g0 · CD) bağıntısını kapatan terimdir: CD < 1 iken geometrik boğaz etkin boğazdan büyüktür, bu yüzden yayımlanan Isp, CF·c*/g0 değerini tam 1/CD kadar aşar.'],
        [/^The value sent in propellant_type \('(.+?)'\) is not one of the propellant classes HRMA has a toxic inventory rule for and no tabulated component name was found in it, so the class below was taken from motor_type \('(\S+)'\), NOT from what you typed\. '(\S+)' names a propellant CLASS, not a propellant: the toxic inventory depends on which propellants are actually used \(LOX\/RP-1 and N2O4\/MMH are both liquid bipropellants and are not comparable; a hybrid's inventory is set by its oxidiser\)\. Name the propellant in propellant_type \(for example '(.+?)'\) to get an inventory\.$/,
         'İtici türü alanına gönderilen değer (\'$1\'), HRMA\'nın zehirli envanter kuralı olan itici sınıflarından biri değil ve içinde tablolu bir bileşen adı bulunmadı; bu yüzden aşağıdaki sınıf yazdığınızdan DEĞİL, motor türünden (\'$2\') alındı. \'$3\' bir itici değil, bir itici SINIFI adlandırır: zehirli envanter gerçekte hangi iticilerin kullanıldığına bağlıdır (LOX/RP-1 ve N2O4/MMH ikisi de sıvı çift iticidir ve karşılaştırılamaz; bir hibridin envanterini oksitleyicisi belirler). Envanter almak için iticiyi itici türü alanında adlandırın (örneğin \'$4\').'],
        [/^The value sent in propellant_type \('(.+?)'\) is not one of the propellant classes HRMA has a toxic inventory rule for and no tabulated component name was found in it, so the class below was taken from motor_type \('(\S+)'\), NOT from what you typed\. '(\S+)' has no tabulated toxic component in HRMA, so no toxic inventory is reported\. SCOPE: this covers the stored propellant only\. Combustion PRODUCTS \(for example HCl and alumina from ammonium-perchlorate composites\) are NOT inventoried by this analysis\.$/,
         'İtici türü alanına gönderilen değer (\'$1\'), HRMA\'nın zehirli envanter kuralı olan itici sınıflarından biri değil ve içinde tablolu bir bileşen adı bulunmadı; bu yüzden aşağıdaki sınıf yazdığınızdan DEĞİL, motor türünden (\'$2\') alındı. \'$3\' için HRMA\'da tablolu zehirli bileşen yok; bu yüzden zehirli envanter bildirilmez. KAPSAM: bu yalnız depolanan iticiyi kapsar. Yanma ÜRÜNLERİ (örneğin amonyum perklorat kompozitlerinden HCl ve alümina) bu analizde envantere ALINMAZ.'],
        /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 4) — YAPISAL DEĞER KAYNAKLARI
           defterinin değişken parçalı üç gerekçesi (structural_analysis.py
           recommendation_basis istasyon listesi, kapak kütlesi kapak türü,
           yorulma dayanım düşürme yüzdesi). İstasyon makine adları YAPISAL
           panel tablosunun adlarıyla (panel.structural.mode*); tanınmayan ad
           ya da tür varsa cümle AYNEN kalır. */
        [/^Thickness \/ material recommendations are drawn ONLY from safety factors measured on a drawn wall\. Stations whose factor is the design target read back \((.+?)\) issue no advice, because the number describes the target you typed, not the hardware; the target itself is graded in design_target_assessment\. Supply the real wall \/ throat \/ head thickness to earn advice for those stations\.$/,
         function (tum, liste) {
             var I = global.I18N, ADLAR = {nozzle: 'panel.structural.modeNozzle',
                 end_cap: 'panel.structural.modeEndCap', chamber_hoop: 'panel.structural.modeChamberHoop',
                 chamber_von_mises: 'panel.structural.modeChamberVm',
                 buckling_axial: 'panel.structural.modeBuckling'};
             var adlar;
             if (liste === 'none') {
                 adlar = 'yok';
             } else {
                 var ad = liste.split(', ').map(function (x) {
                     return (ADLAR[x] && I && typeof I.has === 'function' && I.has(ADLAR[x]))
                         ? I.t(ADLAR[x]) : null;
                 });
                 if (ad.indexOf(null) !== -1) return tum;
                 adlar = ad.join(', ');
             }
             return 'Kalınlık / malzeme önerileri YALNIZ çizilmiş bir cidar üstünde ölçülen emniyet '
                 + 'katsayılarından çıkarılır. Katsayısı tasarım hedefinin geri okunması olan istasyonlar ('
                 + adlar + ') öneri vermez; çünkü sayı donanımı değil, yazdığınız hedefi anlatır; hedefin '
                 + 'kendisi tasarım hedefi değerlendirmesinde derecelendirilir. Bu istasyonlar için öneri '
                 + 'almak üzere gerçek cidar / boğaz / kapak kalınlığını girin.';
         }],
        [/^evaluated cap thickness \(head_thickness_used_mm\) — the user thickness in verify mode, the sized thickness in size mode; flat\/dished sizing outputs are NOT used for mass\. The head type this mass belongs to is named in end_cap_thickness_used_type \((flat|dished|user_supplied)\); a layer that draws or manufactures another head type is weighing a different part and must size it from that type own thickness field \(end_cap_analysis\.head_thickness_field_by_type\)\.$/,
         function (tum, tur) {
             var TUR = {flat: 'düz', dished: 'bombeli', user_supplied: 'kullanıcının verdiği'};
             return 'değerlendirilen kapak kalınlığı — doğrulama kipinde kullanıcının kalınlığı, '
                 + 'boyutlandırma kipinde boyutlandırılan kalınlık; düz/bombeli boyutlandırma çıktıları '
                 + 'kütle için KULLANILMAZ. Bu kütlenin ait olduğu kapak türü değerlendirilen kapak türü '
                 + 'alanında adlandırılır (' + TUR[tur] + '); başka bir kapak türünü çizen ya da üreten '
                 + 'bir katman farklı bir parçayı tartıyordur ve onu o türün kendi kalınlık alanından '
                 + 'boyutlandırmalıdır (türe göre kapak kalınlığı alanı).';
         }],
        [/^endurance limit and ultimate strength are derated to (\S+)% of their room-temperature values using the material temperature-retention curve evaluated at the governing wall temperature \(Shigley 10th ed\. Sec\. 6-7 temperature factor k_d; the tabulated curve is a YIELD retention curve, so carrying it to the endurance limit is approximate\)$/,
         'yorulma dayanımı ve çekme dayanımı, belirleyici cidar sıcaklığında değerlendirilen malzeme sıcaklık-korunum eğrisiyle oda sıcaklığı değerlerinin %$1 düzeyine düşürülür (Shigley 10. bs. Bölüm 6-7 sıcaklık katsayısı kd; tablolanmış eğri bir AKMA korunum eğrisidir, bu yüzden onu yorulma dayanımına taşımak yaklaşıktır)'],
        /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 9, DİL-HİBRİT O4/S7) — OPTİMUM O/F
           öneri cümlesi. Üretici: hrma/utils/optimum_of_ratio.py
           get_recommendation (uç find-optimum-of; advanced.html SRV ile
           basar). Motor türü üç makine adından biri; tanınmayan tür ya da
           sınıf varsa cümle AYNEN kalır. Sayılar sunucudan; yalnız ondalık
           kanonundan geçer (işaret korunur). */
        [/^Computed optimum O\/F for (\S+) \((hybrid|liquid|solid)\): (\S+) \(combustion equilibrium scan at your chamber pressure\)\. Reference table value: (\S+) \(difference (\S+), (\S+)%\)\. The reference value is not computed for your operating point; the scanned value is\.(?: NOTE: this pair is listed under (hybrid|liquid|solid) motors in the reference table, not (hybrid|liquid|solid)\.)?$/,
         function (tum, cift, tip, olculen, referans, fark, yuzde, sinif, istenen) {
             var TUR = {hybrid: 'hibrit', liquid: 'sıvı', solid: 'katı'};
             return cift + ' (' + TUR[tip] + ') için hesaplanan optimum O/F: ' + I18N_SAYI(olculen)
                 + ' (oda basıncınızda yanma dengesi taraması). Referans tablo değeri: '
                 + I18N_SAYI(referans) + ' (fark ' + I18N_SAYI(fark) + ', %' + I18N_SAYI(yuzde)
                 + '). Referans değer çalışma noktanız için hesaplanmamıştır; taranan değer hesaplanmıştır.'
                 + (sinif ? ' NOT: bu çift referans tablosunda ' + TUR[istenen] + ' değil, '
                     + TUR[sinif] + ' motorlar altında listelenir.' : '');
         }],
        [/^No reference O\/F value for (\S+) as a (hybrid|liquid|solid) motor\. Use the combustion analysis result for this pair\.(?: Computed optimum O\/F \(combustion equilibrium scan\): (\S+)\.)?$/,
         function (tum, cift, tip, olculen) {
             var TUR = {hybrid: 'Hibrit', liquid: 'Sıvı', solid: 'Katı'};
             return TUR[tip] + ' motor olarak ' + cift + ' için referans O/F değeri yok. '
                 + 'Bu çift için yanma analizi sonucunu kullanın.'
                 + (olculen ? ' Hesaplanan optimum O/F (yanma dengesi taraması): '
                     + I18N_SAYI(olculen) + '.' : '');
         }],
        /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 7) — ISIL KORUMA validity_note.
           Üretici: hrma/analysis/thermal_protection.py (model_valid=False
           dalı): MODEL OUT OF ENVELOPE öneki + gerekçeler (noktalı virgülle,
           1-3 adet, her biri sayılı) + sabit gövde + (çağıranın akısıysa) kuyruk.
           Gerekçe listesi değişken olduğu için işlev gövdeli: her parça kendi
           kuralıyla çevrilir; TANINMAYAN parça varsa cümlenin TAMAMI AYNEN
           kalır (yarı Türkçe metin yok). Sayılar sunucudan; yalnız ondalık
           kanonundan geçer. RECESSION_VALID_MAX_MM_S makine adı Türkçe metinde
           okunur adla ("gerileme hızı geçerlilik tavanı"). */
        [/^MODEL OUT OF ENVELOPE: ([\s\S]+?)\. No thickness is published for this station: a Level-1 steady Q\* model cannot size it\. Use an in-depth pyrolysis\/char \(CMA-class\) analysis, or change the design point \(flux, burn time, material\)\.( The flux came from the CALLER \(no surface energy balance was solved here\), so the envelope was judged on the caller-supplied flux — see flux_basis\.)?$/,
         function (tum, gerekceler, cagiran) {
             var KURALLAR = [
                 [/^the computed recession rate (\S+) mm\/s is above the (\S+) mm\/s validity ceiling of this Level-1 steady Q\* model \(measured ablative rates stay below it; see RECESSION_VALID_MAX_MM_S\)$/,
                  function (h, tavan) {
                      return 'hesaplanan gerileme hızı ' + I18N_SAYI(h) + ' mm/s, bu Seviye-1 kararlı Q* modelinin '
                          + I18N_SAYI(tavan) + ' mm/s geçerlilik tavanının üstünde (ölçülen ablatif hızlar bu tavanın '
                          + 'altında kalır; bkz. gerileme hızı geçerlilik tavanı)';
                  }],
                 [/^the required liner thickness (\S+) mm is larger than the station radius (\S+) mm — a liner cannot be thicker than the passage it lines, so this is not a design, it is the model leaving its envelope$/,
                  function (t, r) {
                      return 'gereken astar kalınlığı ' + I18N_SAYI(t) + ' mm, istasyon yarıçapından ('
                          + I18N_SAYI(r) + ' mm) büyük — bir astar kapladığı geçitten kalın olamaz; bu bir '
                          + 'tasarım değil, modelin zarfının dışına çıkmasıdır';
                  }],
                 [/^the total recession (\S+) mm exceeds the station radius (\S+) mm — the station would burn through before the end of burn$/,
                  function (g, r) {
                      return 'toplam gerileme ' + I18N_SAYI(g) + ' mm, istasyon yarıçapını (' + I18N_SAYI(r)
                          + ' mm) aşıyor — istasyon yanma bitmeden delinir';
                  }]
             ];
             var parcalar = gerekceler.split('; ');
             /* İlk gerekçenin parantez içindeki '; see …' ayracı da '; ' ile
                bölünür: o parçayı geri birleştir. */
             var birlesik = [];
             for (var i = 0; i < parcalar.length; i++) {
                 if (/^see RECESSION_VALID_MAX_MM_S\)$/.test(parcalar[i]) && birlesik.length) {
                     birlesik[birlesik.length - 1] += '; ' + parcalar[i];
                 } else {
                     birlesik.push(parcalar[i]);
                 }
             }
             var tr = [];
             for (var j = 0; j < birlesik.length; j++) {
                 var bulundu = null;
                 for (var k = 0; k < KURALLAR.length && bulundu === null; k++) {
                     var m = KURALLAR[k][0].exec(birlesik[j]);
                     if (m) bulundu = KURALLAR[k][1].apply(null, m.slice(1));
                 }
                 if (bulundu === null) return tum;
                 tr.push(bulundu);
             }
             return 'MODEL ZARFIN DIŞINDA: ' + tr.join('; ') + '. Bu istasyon için kalınlık '
                 + 'yayımlanmaz: Seviye-1 kararlı Q* modeli onu boyutlandıramaz. Derinlemesine '
                 + 'piroliz/kömürleşme (CMA sınıfı) analizi kullanın ya da tasarım noktasını '
                 + '(akı, yanma süresi, malzeme) değiştirin.'
                 + (cagiran ? ' Akı ÇAĞIRANDAN geldi (burada yüzey enerji dengesi çözülmedi); '
                     + 'bu yüzden zarf, çağıranın verdiği akıyla değerlendirildi — akının dayanağına bakın.' : '');
         }],
        /* V307 DİL-SUNUCU (kalem 6) — SIVI tasarım ortamı künyeleri
           (liquid_rocket_engine.py DESIGN_AMBIENT_BASIS, _SEA_LEVEL_BASIS,
           FIXED_NOZZLE_SEPARATION_DESIGN_AMBIENT_BASIS, deniz seviyesi
           durumunun neden_ds dalları). TR metinde ham alan adı yerine okunur ad. */
        [/^The thrust you enter is the engine thrust at the design ambient pressure p_a \(sea_level: 1\.01325 bar, ISA \/ US Standard Atmosphere 1976 at 0 m; altitude: the ISA pressure of the entered geometric altitude, the same atmosphere table the altitude performance table and the trajectory solver use; pressure: the entered pressure; vacuum: p_a = 0\)\. The propellant flow, the throat and everything sized from them follow from F = mdot\*g0\*Isp\(p_a\) with the same-nozzle identity F\(p_a\) = F_vac - p_a\*A_e \(Sutton & Biblarz 9th ed\., Eq\. 2-14 and 3-29\)\. The flow separation check \(Summerfield criterion, P_e < (\S+) x p_a; Summerfield, Foster & Swan, Jet Propulsion 24\(9\), 1954\) is applied at the design ambient: a nozzle that is attached there is a valid design even when it separates at sea level, and the sea-level state is then published separately \(design_ambient\.sea_level\)\.$/,
         'Girdiğiniz itki, tasarım ortam basıncı p_a\'daki motor itkisidir (deniz seviyesi: 1,01325 bar, ISA / US Standard Atmosphere 1976, 0 m; irtifa: girilen geometrik irtifanın ISA basıncı, irtifa performans tablosu ve yörünge çözücüsüyle aynı atmosfer tablosu; basınç: girilen basınç; vakum: p_a = 0). İtici debisi, boğaz ve bunlardan boyutlandırılan her şey F = ṁ·g0·Isp(p_a) bağıntısından ve aynı nozul özdeşliği F(p_a) = F_vak − p_a·A_e\'den gelir (Sutton & Biblarz 9. bs., Denk. 2-14 ve 3-29). Akış ayrılması denetimi (Summerfield ölçütü, P_e < $1 × p_a; Summerfield, Foster & Swan, Jet Propulsion 24(9), 1954) tasarım ortamında uygulanır: orada bağlı akışlı bir nozul, deniz seviyesinde ayrılsa bile geçerli bir tasarımdır; deniz seviyesi durumu bu durumda ayrıca yayımlanır (tasarım ortamı → deniz seviyesi durumu).'],
        [/^sea-level state of THIS nozzle \(same expansion ratio, same chamber pressure, same propellant flow\) at 1\.01325 bar: the exit pressure is the isentropic exit pressure of the nozzle \(independent of ambient\), the flow is attached when P_e >= (\S+) x 1\.01325 bar \(Summerfield criterion on the one-dimensional exit pressure, the same test as the design point\), and thrust \/ Isp come from the 0 m row of the altitude performance table \(same-nozzle identity F\(0\) = F_vac - p_sl\*A_e, Sutton & Biblarz 9th ed\., Eq\. 2-14\)\. They are published only for attached flow\. max_attached_expansion_ratio is the largest expansion ratio that stays attached at sea level at this chamber pressure\.$/,
         'BU nozulun 1,01325 bar\'daki deniz seviyesi durumu (aynı genleşme oranı, aynı yanma odası basıncı, aynı itici debisi): çıkış basıncı nozulun izantropik çıkış basıncıdır (ortamdan bağımsız); P_e ≥ $1 × 1,01325 bar olduğunda akış bağlıdır (tek boyutlu çıkış basıncına uygulanan Summerfield ölçütü, tasarım noktasıyla aynı sınama); itki / Isp irtifa performans tablosunun 0 m satırından gelir (aynı nozul özdeşliği F(0) = F_vak − p_dz·A_e, Sutton & Biblarz 9. bs., Denk. 2-14). Yalnız bağlı akış için yayımlanır. "Bağlı kalan en büyük genleşme oranı" değeri, bu yanma odası basıncında akışın deniz seviyesinde bağlı kaldığı en büyük genleşme oranını verir.'],
        [/^the nozzle separates at sea level by the Summerfield criterion \(P_e = (\S+) bar < (\S+) x 1\.01325 bar = (\S+) bar\): attached-flow relations do not hold there and separated nozzle flow is NOT modelled, so no sea-level thrust or Isp is published\. The test uses the one-dimensional exit pressure: a contoured nozzle whose wall pressure at the exit is higher than that value can stay attached, and the wall pressure distribution is not solved here\.$/,
         'nozul deniz seviyesinde Summerfield ölçütüne göre ayrılıyor (P_e = $1 bar < $2 × 1,01325 bar = $3 bar): orada bağlı akış bağıntıları geçerli değildir ve ayrılmış nozul akışı MODELLENMEZ; bu yüzden deniz seviyesi itkisi ya da Isp yayımlanmaz. Sınama tek boyutlu çıkış basıncını kullanır: çıkıştaki cidar basıncı bu değerden yüksek olan profilli bir nozul bağlı kalabilir; cidar basıncı dağılımı burada çözülmez.'],
        [/^the nozzle exit pressure could not be solved, so the sea-level state is not evaluated$/,
         'nozul çıkış basıncı çözülemedi; bu yüzden deniz seviyesi durumu değerlendirilmedi'],
        /* V307 DİL-SUNUCU (kalem 5) — PDF belgesinin cümle cümle böldüğü çözücü parçaları. */
        [/^this run uses '(.+?)', which is outside that envelope\.$/,
         'bu koşu $1 kullanıyor, yani o zarfın DIŞINDA.'],
        [/^UnresolvedChamberMaterial: Chamber material '(.+?)' is not in the material database, so no safety verdict was computed\.$/,
         'Yanma odası malzemesi \'$1\' malzeme veritabanında yok; bu yüzden güvenlik hükmü hesaplanmadı.'],
        [/^verified against the user-supplied case wall thickness \((\S+) mm, evaluated exactly as entered - HRMA does not raise it to the (\S+) mm manufacturing floor\)\.$/,
         'kullanıcının verdiği kasa cidar kalınlığına göre doğrulandı ($1 mm, girildiği gibi değerlendirildi - HRMA onu $2 mm imalat alt sınırına yükseltmez).'],
        /* V307 DİL-SUNUCU-2 (DİL-EKRAN DEVİR 11, NK3-K-3) — katı kasa cidarı
           safety_factor_basis öteki dalları (solid_rocket_engine.py; PDF kasa
           satırı ve çizim künyesi). Dize şablonu: PDF çevirmeni de koşar. */
        [/^verified against the user-supplied case wall thickness \((\S+) mm, evaluated exactly as entered - HRMA does not raise it to the (\S+) mm manufacturing floor\)\. NOTE: this wall is BELOW that manufacturing floor; the safety factor below describes the thin wall you entered, not a wall HRMA would propose\.$/,
         'kullanıcının verdiği kasa cidar kalınlığına göre doğrulandı ($1 mm, girildiği gibi değerlendirildi - HRMA onu $2 mm imalat alt sınırına yükseltmez). NOT: bu cidar o imalat alt sınırının ALTINDA; aşağıdaki emniyet katsayısı HRMA\'nın önereceği bir cidarı değil, girdiğiniz ince cidarı anlatır.'],
        [/^NOT a verification: no case thickness was supplied, so HRMA sized the wall from the hoop stress to meet the design safety factor \(t = P\*r\/\(sigma_y\/SF\)\)\. Dividing the yield strength by the resulting hoop stress returns that same design safety factor - it is the INPUT read back\. Supply case_thickness \(mm\) to obtain an independent verification\.$/,
         'Doğrulama DEĞİL: kasa kalınlığı verilmedi; bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden boyutlandırdı (t = P*r/(sigma_y/SF)). Akma dayanımını ortaya çıkan çember gerilmesine bölmek aynı tasarım emniyet katsayısını verir - bu, GİRDİNİN geri okunmasıdır. Bağımsız bir doğrulama için kasa kalınlığını (mm) girin.'],
        [/^NOT a verification: no case thickness was supplied, so HRMA sized the wall from the hoop stress to meet the design safety factor \(t = P\*r\/\(sigma_y\/SF\)\)\. Dividing the yield strength by the resulting hoop stress returns that same design safety factor - it is the INPUT read back\. Supply case_thickness \(mm\) to obtain an independent verification\. In this run the hoop stress only required (\S+) mm, so the proposal was raised to the (\S+) mm manufacturing floor and the safety factor above is that floor, not the design target\.$/,
         'Doğrulama DEĞİL: kasa kalınlığı verilmedi; bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden boyutlandırdı (t = P*r/(sigma_y/SF)). Akma dayanımını ortaya çıkan çember gerilmesine bölmek aynı tasarım emniyet katsayısını verir - bu, GİRDİNİN geri okunmasıdır. Bağımsız bir doğrulama için kasa kalınlığını (mm) girin. Bu koşuda çember gerilmesi yalnız $1 mm gerektiriyordu; bu yüzden öneri $2 mm imalat alt sınırına yükseltildi ve yukarıdaki emniyet katsayısı tasarım hedefi değil, o alt sınırın katsayısıdır.'],
        [/^piecewise regime table "(.+?)" evaluated at the INSTANTANEOUS chamber pressure; the single a\/n pair entered for this motor was NOT used \(no single exponent represents this law\)$/,
         'parçalı rejim tablosu "$1" ANLIK yanma odası basıncında değerlendirildi; bu motor için girilen tek a/n çifti KULLANILMADI (bu yasayı tek bir üs temsil etmez)'],
        [/^Giffen-Muraszew swirl: K=(\S+) -> X=(\S+) -> Cd=(\S+) \(being lower than a plain orifice is physical\)$/,
         'Giffen-Muraszew girdabı: K=$1 → X=$2 → Cd=$3 (düz bir delikten düşük olması fizikseldir)'],
        /* V307 DİL-SUNUCU (kalem 6) — besleme bütçesi grafiğinin künye notu
           (visualization.py 'Feed budget basis — ' + çözücünün yöntem / filtre notu). */
        [/^Feed budget basis — Darcy-Weisbach with Haaland friction factor plus local loss coefficients \(Crane TP-410\);the injector item is taken from the injector design; filter\/strainer loss uses an assumed loss coefficient K=(\S+)\.$/,
         'Besleme bütçesi dayanağı — Haaland sürtünme katsayılı Darcy-Weisbach ile yerel kayıp katsayıları (Crane TP-410); enjektör kalemi enjektör tasarımından alınır; filtre/süzgeç kaybı varsayılan K=$1 kayıp katsayısını kullanır.'],
        [/^Feed budget basis — Darcy-Weisbach with Haaland friction factor plus local loss coefficients \(Crane TP-410\);the injector item is taken from the injector design\.$/,
         'Besleme bütçesi dayanağı — Haaland sürtünme katsayılı Darcy-Weisbach ile yerel kayıp katsayıları (Crane TP-410); enjektör kalemi enjektör tasarımından alınır.'],
        [/^the sea-level row of the altitude performance table is not published for this design \(altitude_performance\[0\]\.not_modelled_reason\)$/,
         'irtifa performans tablosunun deniz seviyesi satırı bu tasarım için yayımlanmıyor (nedeni o satırın kendi gerekçesinde)'],
        [/^Summerfield flow separation criterion \(the one this engine also applies to its altitude table and throttle map\): an over-expanded nozzle separates when the exit pressure P_e falls below (\S+) x the ambient pressure P_a\. The engine is sized at the design ambient you selected \(the thrust you enter is the engine thrust at that ambient pressure\) with attached-flow nozzle relations, which do not hold for a separated nozzle, so no design is published for an expansion ratio that separates there\. The largest attached expansion ratio is solved from the same nozzle relation \(exit pressure equal to the separation pressure\)$/,
         'Summerfield akış ayrılması ölçütü (bu motorun irtifa tablosunda ve kısma haritasında da uyguladığı ölçüt): aşırı genleşmiş bir nozul, çıkış basıncı P_e ortam basıncı P_a\'nın $1 katının altına düştüğünde ayrılır. Motor, seçtiğiniz tasarım ortamında (girdiğiniz itki o ortam basıncındaki motor itkisidir) bağlı akış nozul bağıntılarıyla boyutlandırılır; bu bağıntılar ayrılmış bir nozulda geçerli değildir, bu yüzden orada ayrılan bir genleşme oranı için tasarım yayımlanmaz. Bağlı kalan en büyük genleşme oranı aynı nozul bağıntısından çözülür (çıkış basıncı ayrılma basıncına eşit)'],
        // Geçici-rejim (blowdown) kararlılık uyarıları — dinamik değerli
        [/^t=(.+)s: ΔP\/Pc=(.+) < (.+) — combustion instability limit, simulation stopped$/,
         't=$1 s: ΔP/Pc=$2 < $3 — yanma kararsızlığı sınırı, simülasyon durduruldu'],
        // ÖH D18 (P2B4-08): künye artık acoustic_modes.
        // CHUG_THRESHOLD_CITATION'dan gelir (geri çekilmiş SP-8089 atfı
        // kaldırıldı). Desen künyeyi YAKALAR, sabit metne bağlanmaz —
        // künye değişirse çeviri sessizce düşmez.
        [/^t=(.+)s: ΔP\/Pc=(.+) < (.+) — chugging risk \((.+)\)$/,
         't=$1 s: ΔP/Pc=$2 < $3 — chugging riski ($4)'],
        /* ÖH D28 fix-28b — blowdown "kesilmiş kuyruk" uyarısı (hibrit a1,
           OH-D27-09; hrma/analysis/transient_ballistics.py). Ürün TEK yerde
           İKİ kuyrukla üretiyor: buhar yolu zarfı terk ediyorsa gerekçe
           sayılı (üçlü nokta / akış durma kütle oranları), etmiyorsa kısa
           beyan. İKİSİ de burada; yalnız birini yazmak, o koşumda üretilmeyen
           hâli TR kipinde İngilizce bırakırdı ve kapsam bekçisi bunu
           görmezdi (kapsam yalnız ÜRETİLEN metni ölçer). Ortak gövde iki
           desende de birebir aynıdır: ürün cümlesi değişirse İKİSİ birden
           düşer, biri sessizce ayakta kalmaz. */
        [/^TRUNCATED TAIL-OFF: the march stops the instant the liquid is exhausted, so no vapour step is integrated\. (.+?) kg of oxidiser is still in the tank; valued at the oxidiser-specific impulse of the last integrated step \(F\/mdot_ox\) that is worth (.+?) N·s, (.+?) % of the impulse reported above\. It is NOT modelled here: the adiabatic vapour path would fall below the N2O triple point \(mass ratio (.+?)\) before the flow could stop at ambient pressure \(mass ratio (.+?)\), i\.e\. the tank tail-off model is out of envelope there\.$/,
         'KESİLMİŞ KUYRUK: yürüyüş sıvı tükendiği anda duruyor, bu yüzden hiçbir buhar adımı integre edilmiyor. Tankta hâlâ $1 kg oksitleyici var; son integre edilen adımın oksitleyiciye göre özgül itkisiyle (F/mdot_ox) değerlendirildiğinde bu $2 N·s eder, yukarıda bildirilen itkinin %$3 kadarı. Burada MODELLENMEMİŞTİR: adyabatik buhar yolu, akış ortam basıncında durabilmeden (kütle oranı $5) önce N2O üçlü noktasının (kütle oranı $4) altına düşerdi; yani tank kuyruk modeli orada zarfın dışındadır.'],
        [/^TRUNCATED TAIL-OFF: the march stops the instant the liquid is exhausted, so no vapour step is integrated\. (.+?) kg of oxidiser is still in the tank; valued at the oxidiser-specific impulse of the last integrated step \(F\/mdot_ox\) that is worth (.+?) N·s, (.+?) % of the impulse reported above\. It is NOT modelled here \(the tail-off model is not integrated by this solver\)\.$/,
         'KESİLMİŞ KUYRUK: yürüyüş sıvı tükendiği anda duruyor, bu yüzden hiçbir buhar adımı integre edilmiyor. Tankta hâlâ $1 kg oksitleyici var; son integre edilen adımın oksitleyiciye göre özgül itkisiyle (F/mdot_ox) değerlendirildiğinde bu $2 N·s eder, yukarıda bildirilen itkinin %$3 kadarı. Burada MODELLENMEMİŞTİR (kuyruk modeli bu çözücü tarafından integre edilmiyor).'],
        [/^(.+) value must be between (.+), given: (.+)$/,
         '$1 değeri $2 aralığında olmalı, girilen: $3', [1]],
        [/^(.+) must be positive, given: (.+)$/,
         '$1 pozitif olmalı, girilen: $2', [1]],
        [/^Unsupported oxidizer key ['"](.+)['"]\. Supported oxidizers: (.+)$/,
         'Desteklenmeyen oksitleyici anahtarı $1. Desteklenen oksitleyiciler: $2'],
        [/^UNSAFE: equilibrium wall temperature (\S+) K exceeds (\S+) service limit (\S+) K with the specified cooling — burn-through likely\. Required cooling load q=(.+) at the throat\.$/,
         'GÜVENSİZ: denge cidar sıcaklığı $1 K, belirtilen soğutmayla $2 malzemesinin $3 K servis sınırını aşıyor — cidar delinmesi olası. Boğazda gereken soğutma yükü q=$4.'],
        // ÖH D15 / P4B2-09 (regen_cooling.py) — ince-cidar zarfının UYARI
        // bandı. Üç sayı taşıdığı için sözlüğe değil desene giriyor.
        [/^THIN-WALL ENVELOPE: the flat-plate conduction resistance used here differs from the cylindrical solution by (.+) at the throat \(wall_thickness (.+) mm vs throat radius (.+) mm\); the published hot-wall temperature is biased HIGH by that order\. Model note assumes t_w << r_wall\.$/,
         'İNCE CİDAR ZARFI: burada kullanılan düz levha iletim direnci boğazda silindirik çözümden $1 ayrılıyor (cidar kalınlığı $2 mm, boğaz yarıçapı $3 mm); yayımlanan sıcak cidar sıcaklığı bu mertebede YUKARI yönde yanlıdır. Model notu t_w << r_cidar varsayar.'],
        [/^High thrust \((.+)N\) requires professional test stand and safety equipment$/,
         'Yüksek itki ($1 N) profesyonel test standı ve güvenlik ekipmanı gerektirir'],
        [/^Moderate thrust \((.+)N\) requires reinforced test stand and remote operations$/,
         'Orta seviye itki ($1 N) güçlendirilmiş test standı ve uzaktan çalıştırma gerektirir'],
        [/^Long burn time \((.+)s\) requires thermal management and structural analysis$/,
         'Uzun yanma süresi ($1 s) termal yönetim ve yapısal analiz gerektirir'],
        [/^Extreme temperature \((.+)K\) requires (.+)$/,
         'Aşırı sıcaklık ($1 K) şunu gerektirir: $2'],
        [/^L\/D ratio \((.+)\) outside optimal range \((.+)\)$/,
         'L/D oranı ($1) en uygun aralığın ($2) dışında'],
        [/^Exit velocity \((.+) m\/s\) outside optimal range \((.+)\)$/,
         'Çıkış hızı ($1 m/s) en uygun aralığın ($2) dışında'],
        /* V301/E2: iki bandın kaynağı YOK — üretici (utils/injector_design.py
           _check_warnings) artık "optimal" demiyor, HRMA buluşsal eşiği olduğunu
           söylüyor. Eski iki desen kayıtlı sonuçlar için yerinde kalır. */
        [/^Exit velocity \((.+) m\/s\) outside the (.+) m\/s band \(HRMA heuristic threshold - no literature value; not a design limit\)$/,
         'Çıkış hızı ($1 m/s) $2 m/s bandının dışında (HRMA buluşsal eşiği - literatür değeri yok; tasarım sınırı değil)'],
        [/^Impingement angle \((.+) deg\) outside the (.+) deg band \(HRMA heuristic threshold - no literature value; NASA SP-8089 pp\. 78-79 recommends 60 deg\)$/,
         'Çarpışma açısı ($1 derece) $2 derece bandının dışında (HRMA buluşsal eşiği - literatür değeri yok; NASA SP-8089 s. 78-79 60 derece önerir)'],
        [/^L\/D ratio \((.+)\) outside the (.+) band \(HRMA heuristic threshold - no literature value; NASA SP-8089 p\. 84 notes that intermediate L\/D of about 4-6 is susceptible to hydraulic flip\)$/,
         'L/D oranı ($1) $2 bandının dışında (HRMA buluşsal eşiği - literatür değeri yok; NASA SP-8089 s. 84, yaklaşık 4-6 arası ara L/D değerlerinin hidrolik flip\'e duyarlı olduğunu belirtir)'],
        [/^Low Reynolds number \((.+)\) - laminar flow expected$/,
         'Düşük Reynolds sayısı ($1) - laminer akış bekleniyor'],
        [/^Port diameter \((.+)m\) is very large relative to chamber \((.+)m\)\. Check structural integrity\.$/,
         'Port çapı ($1 m) oda çapına ($2 m) göre çok büyük. Yapısal bütünlüğü denetleyin.'],
        [/^Unusual hybrid fuel: (.+)\. Common fuels: (.+)$/,
         'Alışılmadık hibrit yakıt: $1. Yaygın yakıtlar: $2'],
        [/^Unusual hybrid oxidizer: (.+)\. Common oxidizers: (.+)$/,
         'Alışılmadık hibrit oksitleyici: $1. Yaygın oksitleyiciler: $2'],
        [/^Unusual liquid fuel: (.+)\. Common fuels: (.+)$/,
         'Alışılmadık sıvı yakıt: $1. Yaygın yakıtlar: $2'],
        [/^Unusual liquid oxidizer: (.+)\. Common oxidizers: (.+)$/,
         'Alışılmadık sıvı oksitleyici: $1. Yaygın oksitleyiciler: $2'],
        [/^Unusual solid propellant: (.+)\. Common propellants: (.+)$/,
         'Alışılmadık katı itici: $1. Yaygın iticiler: $2'],
        [/^WARNING: (.+) is hypergolic - ignites on contact!$/,
         'UYARI: $1 hipergoliktir - temas ettiği anda tutuşur.'],
        [/^WARNING: (.+) is an amateur propellant\. (.*)$/,
         'UYARI: $1 amatör bir iticidir. $2'],
        [/^CRITICAL: Burst pressure \((.+) bar\) requires (.+)$/,
         'KRİTİK: Patlama basıncı ($1 bar) şunu gerektirir: $2'],
        [/^Skipped (\d+) non-numeric or malformed data row\(s\)\.$/,
         '$1 sayısal olmayan veya bozuk veri satırı atlandı.'],
        [/^Unknown pipe material ['"](.+)['"] — falling back to (.+)$/,
         'Bilinmeyen boru malzemesi $1 — $2 değerine geri dönülüyor'],

        /* ================================================================
           2026-08-03 — {code, params} SÖZLEŞMESİ DIŞINDA KALAN UÇLAR
           ----------------------------------------------------------------
           Aşağıdaki modüller uyarıyı hâlâ DÜZ İNGİLİZCE metin olarak
           döndürüyor: hrma/validation/motor_validation.py,
           hrma/validation/user_data_validation.py,
           hrma/importers/motor_file.py, hrma/analysis/regen_cooling.py.
           Sözleşmeyi değiştirmek bu dosyaların API'sini ve testlerini
           kırardı; bunun yerine metin BURADA yakalanıyor. Backend bir gün
           {code, params}'a geçerse bu kurallar sessizce ıskalar, hiçbir
           şeyi bozmaz.
           ================================================================ */

        /* --- motor_validation.py --------------------------------------- */
        [/^Invalid motor type: (.+)$/, 'Geçersiz motor tipi: $1'],
        [/^Missing required parameter: (.+)$/, 'Zorunlu parametre eksik: $1'],
        [/^(.+) must be numeric, got (.+)$/, '$1 sayısal olmalı, gelen: $2', [1]],
        [/^(.+) = (.+) is outside valid range \[(.+)\] (.*)$/,
         '$1 = $2 geçerli aralığın [$3] $4 dışında', [1]],
        /* P12aB3-10 (Z5 i18n) — İKİ ÖLÜ KURAL SİLİNDİ. Silinen hâlleri:
               [/^WARNING: HTPB\/ClF3 is extremely hypergolic and dangerous!$/,
                'UYARI: HTPB/ClF3 aşırı hipergoliktir ve tehlikelidir.'],
               [/^Note: Cryogenic propellants require specialized handling equipment$/,
                'Not: Kriyojenik iticiler özel elleçleme ekipmanı gerektirir'],
           İKİSİ DE sözlükte AYRI bir Türkçe karşılıkla duruyordu:
             'UYARI: HTPB/ClF3 son derece hipergolik ve tehlikelidir.'
             'Not: Kriyojenik iticiler özel taşıma ve kullanım ekipmanı gerektirir'
           `serverText` sözlüğe ÖNCE baktığı için kullanıcının gördüğü metin
           hep sözlük sürümüydü; kural sürümü hiç çalışmadı. Aynı GÜVENLİK
           uyarısının iki Türkçe hâlini taşımak, birinin düzeltilip diğerinin
           unutulması demekti. Tek kaynak sözlük olarak sabitlendi; ekranda
           GÖRÜNEN metin değişmedi (ölçüldü: her ikisi de sözlükten geliyordu). */
        [/^Throat diameter \((.+)\) must be smaller than chamber diameter \((.+)\)$/,
         'Boğaz çapı ($1) oda çapından ($2) küçük olmalı'],
        [/^Exit diameter \((.+)\) must be larger than throat diameter \((.+)\)$/,
         'Çıkış çapı ($1) boğaz çapından ($2) büyük olmalı'],
        [/^Tank pressure \((.+)\) must be higher than chamber pressure \((.+)\)$/,
         'Tank basıncı ($1) oda basıncından ($2) yüksek olmalı'],
        /* v3.0.1 (22 Eki, V301/E2 devri 5) — KULLANICI TANK KİPİ 422
           CÜMLELERİ. Üretici: hrma/engines/hybrid_rocket_engine.py kullanıcı
           tank basıncı ret kayıtları (tank_pressure_required,
           tank_pressure_not_above_chamber_pressure,
           tank_pressure_below_saturation). Sayılar ondalık kanonundan geçer.
           Birden çok ret kaydı tek cümlede birleşirse desen tutmaz ve cümle
           İngilizce kalır (yarım çeviri yok). Bekçi:
           tests/test_v301_tank_ret_dili.py */
        [/^tank_pressure_source = 'user' takes the injector feed pressure from 'tank_pressure' \(bar, absolute\), which was not supplied\. No server default is used in this mode\.$/,
         "tank_pressure_source = 'user' kipinde enjektör besleme basıncı "
         + "'tank_pressure' alanından (bar, mutlak) alınır; bu alan "
         + 'gönderilmedi. Bu kipte sunucu varsayılanı kullanılmaz.'],
        [/^Injector pressure drop dP = P_1 - P_c = (\S+) - (\S+) = (\S+) bar is not positive \(P_1 = P_tank = (\S+) bar; feed line loss not included\)\. No oxidizer flow can be delivered: raise the tank pressure above the chamber pressure\.$/,
         function (_t, p1, pc, dp, pt) {
             return 'Enjektör basınç düşümü dP = P_1 - P_c = '
                 + I18N_SAYI(p1) + ' - ' + I18N_SAYI(pc) + ' = '
                 + I18N_SAYI(dp) + ' bar pozitif değil (P_1 = P_tank = '
                 + I18N_SAYI(pt) + ' bar; besleme hattı kaybı dahil '
                 + 'değil). Oksitleyici akışı sağlanamaz: tank basıncını '
                 + 'oda basıncının üstüne çıkarın.';
         }],
        [/^Tank pressure (\S+) bar is below the N2O saturation pressure at the tank temperature, P_sat\((\S+) K\) = (\S+) bar \(HRMA tolerance (\S+) %\)\. This is inconsistent with the default equilibrium initial state: liquid N2O at T_tank cannot be held in equilibrium below its saturation pressure \(a metastable liquid is not modelled\)\. Raise the tank pressure to at least (\S+) bar or lower the tank temperature\.$/,
         function (_t, pt, T, psat, tol, pmin) {
             return 'Tank basıncı ' + I18N_SAYI(pt) + ' bar, tank '
                 + 'sıcaklığındaki N2O doyma basıncının altında: P_sat('
                 + I18N_SAYI(T) + ' K) = ' + I18N_SAYI(psat) + ' bar (HRMA '
                 + 'toleransı %' + I18N_SAYI(tol) + '). Bu, varsayılan '
                 + 'denge başlangıç durumuyla tutarsız: T_tank sıcaklığındaki '
                 + 'sıvı N2O doyma basıncının altında dengede tutulamaz (yarı '
                 + 'kararlı sıvı modellenmez). Tank basıncını en az '
                 + I18N_SAYI(pmin) + ' bar yapın ya da tank sıcaklığını '
                 + 'düşürün.';
         }],
        /* V306/HİBRİT-MODEL (M-HIBRIT-10): gaz faz N2O besleme reddi
           (hybrid_rocket_engine.user_tank_pressure_state). */
        [/^Gaseous N2O feed at (\S+) bar is above the N2O saturation pressure at the tank temperature, P_sat\((\S+) K\) = (\S+) bar \(HRMA tolerance (\S+) %\): at that temperature N2O condenses above P_sat, so the feed cannot be gaseous\. Lower the supply pressure to at most (\S+) bar, raise the temperature, or select the liquid phase\.$/,
         function (_t, pt, T, psat, tol, pmax) {
             return 'Gaz N2O beslemesi ' + I18N_SAYI(pt) + ' bar, tank '
                 + 'sıcaklığındaki N2O doyma basıncının üstünde: P_sat('
                 + I18N_SAYI(T) + ' K) = ' + I18N_SAYI(psat) + ' bar (HRMA '
                 + 'toleransı %' + I18N_SAYI(tol) + '). Bu sıcaklıkta N2O '
                 + 'doyma basıncının üstünde yoğuşur, besleme gaz olamaz. '
                 + 'Besleme basıncını en çok ' + I18N_SAYI(pmax)
                 + ' bar yapın, sıcaklığı yükseltin ya da sıvı fazı seçin.';
         }],
        /* V306/HİBRİT-MODEL (M-HIBRIT-25, 4 Kas): çiftin ölçüm penceresi
           geçerli kayıt sayısı pratik kapının altında — varsayılan yok
           (hybrid_rocket_engine._eta_varsayilan_cozumu). */
        [/^No sourced c\* efficiency default for (\S+): after excluding (\d+) firing\(s\) whose measurement window is not valid, (\d+) valid measured firing\(s\) remain \(HRMA requires at least (\d+); practical gate, not a statistical criterion\)\. Enter the c\* efficiency \(%\) of this motor\.$/,
         function (_t, cift, k, n, m) {
             return cift + ' için kaynaklı c* verimi varsayılanı kurulamadı: '
                 + 'ölçüm penceresi geçerli olmayan ' + k + ' ateşleme '
                 + 'dışlandıktan sonra ' + n + ' geçerli ölçülmüş ateşleme '
                 + 'kalıyor (HRMA en az ' + m + ' ister; pratik kapı, '
                 + 'istatistiksel ölçüt değil). Bu motorun c* verimini (%) '
                 + 'girin.';
         }],
        /* v3.0.1 (22 Eki, V301/K-A) — KATI TASARIM REDDİ 422 CÜMLELERİ.
           Üreticiler: hrma/engines/solid_rocket_engine.py
           (_check_case_fit, _check_port_throat, 7c core_not_inside_grain) ve
           hrma/app.py /calculate_solid (_kati_reddedilen_girdi_hatasi,
           _kati_gecersiz_tane_hatasi, core_too_large_for_grain). Sayılar
           ondalık kanonundan geçer. Bir parça tanınmazsa (ör. çok alanlı ret
           cümlesinde bilinmeyen madde) cümle İngilizce kalır (yarım çeviri
           yok). Bekçi: tests/test_v301_kati_geometri.py */
        [/^No design was published: the case inner diameter \(chamber_diameter\) (\S+) mm is below the (\S+) mm minimum that the (\S+) mm grain needs with its (\S+) mm liner and (\S+) mm insulation \(case inner diameter >= grain outer diameter \+ 2 x \(liner \+ insulation\)\)\. Enter at least (\S+) mm, leave chamber_diameter empty so HRMA derives the case from the grain, or reduce outer_diameter, liner_thickness or insulation_thickness; the case is not enlarged silently\.$/,
         function (_t, beyan, gereken, tane, astar, yalitim, gir) {
             return 'Tasarım yayımlanmadı: kasa iç çapı (chamber_diameter) '
                 + I18N_SAYI(beyan) + ' mm; ' + I18N_SAYI(tane) + ' mm '
                 + 'yakıt bloğunun ' + I18N_SAYI(astar) + ' mm astar ve '
                 + I18N_SAYI(yalitim) + ' mm yalıtımla birlikte gerektirdiği '
                 + 'en az ' + I18N_SAYI(gereken) + ' mm değerinin altında '
                 + '(kasa iç çapı >= yakıt bloğu dış çapı + 2 x (astar + '
                 + 'yalıtım)). En az ' + I18N_SAYI(gir) + ' mm girin, '
                 + 'kasanın yakıt bloğundan türetilmesi için chamber_diameter '
                 + 'alanını boş bırakın ya da outer_diameter, liner_thickness '
                 + 'veya insulation_thickness değerini küçültün; kasa '
                 + 'sessizce büyütülmez.';
         }],
        [/^No design was published: the core diameter (\S+) mm is not smaller than the grain outer diameter (\S+) mm \(outer_diameter\), so the (\S+) grain has no propellant web\. Enter a core diameter below (\S+) mm or a larger grain outer diameter\.$/,
         function (_t, cekirdek, od, tip, od2) {
             return 'Tasarım yayımlanmadı: çekirdek çapı '
                 + I18N_SAYI(cekirdek) + ' mm, yakıt bloğu dış çapından ('
                 + I18N_SAYI(od) + ' mm, outer_diameter) küçük değil; bu '
                 + 'nedenle ' + tip + ' yakıt bloğunda et kalmıyor. '
                 + I18N_SAYI(od2) + ' mm altında bir çekirdek çapı ya da daha '
                 + 'büyük bir yakıt bloğu dış çapı girin.';
         }],
        /* V301/K-D (NK-31): ileti iki alanı adıyla ve sayısıyla söyler. */
        [/^No design was published: the core diameter \(core_diameter\) (\S+) mm does not fit the grain outer diameter \(outer_diameter\) (\S+) mm: it leaves less than the (\S+) mm minimum web on each side\. The largest accepted core for this grain is (\S+) mm and the smallest grain outer diameter for this core is (\S+) mm\. Enter a core diameter of at most (\S+) mm or a grain outer diameter of at least (\S+) mm\.$/,
         function (_t, cekirdek, od, web, enbuyuk, enkucukOd, enbuyuk2, enkucukOd2) {
             return 'Tasarım yayımlanmadı: çekirdek çapı (core_diameter) '
                 + I18N_SAYI(cekirdek) + ' mm, yakıt bloğu dış çapına '
                 + '(outer_diameter) ' + I18N_SAYI(od) + ' mm sığmıyor: her '
                 + 'iki yanda en az ' + I18N_SAYI(web) + ' mm et kalınlığı '
                 + 'kalmıyor. Bu yakıt bloğu için kabul edilen en büyük '
                 + 'çekirdek ' + I18N_SAYI(enbuyuk) + ' mm, bu çekirdek için '
                 + 'en küçük yakıt bloğu dış çapı ' + I18N_SAYI(enkucukOd)
                 + ' mm. En çok ' + I18N_SAYI(enbuyuk2) + ' mm çekirdek çapı '
                 + 'ya da en az ' + I18N_SAYI(enkucukOd2) + ' mm yakıt bloğu '
                 + 'dış çapı girin.';
         }],
        [/^No design was published: the initial port flow area (\S+) mm\^2 \(core diameter (\S+) mm, (\S+)\) is not larger than the throat area (\S+) mm\^2 \(throat diameter (\S+) mm, sized by the solver\), port\/throat area ratio (\S+)\. The flow would choke in the port, not at the nozzle throat\. (.+)\.$/,
         function (_t, kanal, cekirdek, tip, bogaz, bogazCap, oran, eylem) {
             var m, eylemTr = null;
             if ((m = /^Enter a core diameter of at least (\S+) mm \(the throat is re-sized with the core\), or lower the burning area or raise the chamber pressure$/.exec(eylem))) {
                 eylemTr = 'En az ' + I18N_SAYI(m[1]) + ' mm çekirdek çapı '
                     + 'girin (boğaz çekirdekle yeniden boyutlanır) ya da '
                     + 'yanma alanını küçültün veya oda basıncını yükseltin';
             } else if (/^An end burner flows through the full grain cross-section, so enlarge the grain outer diameter or reduce the burning area \/ raise the chamber pressure$/.test(eylem)) {
                 eylemTr = 'Uçtan yanan yakıt bloğunda akış bütün kesitten '
                     + 'geçer; yakıt bloğu dış çapını büyütün ya da yanma '
                     + 'alanını küçültün / oda basıncını yükseltin';
             } else if ((m = /^No core diameter inside the (\S+) mm grain makes the port larger than the throat; enlarge the grain outer diameter, shorten the grain or raise the chamber pressure$/.exec(eylem))) {
                 eylemTr = I18N_SAYI(m[1]) + ' mm yakıt bloğunun içinde '
                     + 'kanalı boğazdan büyük yapan bir çekirdek çapı yok; '
                     + 'yakıt bloğu dış çapını büyütün, bloğu kısaltın ya da '
                     + 'oda basıncını yükseltin';
             }
             if (eylemTr === null) return _t;
             return 'Tasarım yayımlanmadı: başlangıç kanal akış alanı '
                 + I18N_SAYI(kanal) + ' mm^2 (çekirdek çapı '
                 + I18N_SAYI(cekirdek) + ' mm, ' + tip + ') boğaz alanından '
                 + '(' + I18N_SAYI(bogaz) + ' mm^2, boğaz çapı '
                 + I18N_SAYI(bogazCap) + ' mm, çözücü boyutlandırdı) büyük '
                 + 'değil; kanal/boğaz alan oranı ' + I18N_SAYI(oran) + '. '
                 + 'Akış nozul boğazında değil kanalda boğulur. ' + eylemTr
                 + '.';
         }],
        [/^No design was published: the solver found no burning surface for this (\S+) grain \(outer diameter (\S+) mm, core diameter (\S+) mm, length (\S+) mm\), so no thrust curve exists\. Check the grain dimensions and the (\S+) grain parameters\.$/,
         function (_t, tip, od, cekirdek, boy, tip2) {
             return 'Tasarım yayımlanmadı: çözücü bu ' + tip + ' yakıt '
                 + 'bloğunda (dış çap ' + I18N_SAYI(od) + ' mm, çekirdek çapı '
                 + I18N_SAYI(cekirdek) + ' mm, uzunluk ' + I18N_SAYI(boy)
                 + ' mm) yanma yüzeyi bulamadı, itki eğrisi oluşmuyor. Yakıt '
                 + 'bloğu ölçülerini ve ' + tip2 + ' parametrelerini '
                 + 'denetleyin.';
         }],
        [/^No design was published: the solver could not build this (\S+) grain \(outer diameter (\S+) mm, core diameter (\S+) mm, length (\S+) mm; solver code (\S+)\)\. Check the grain dimensions\.$/,
         function (_t, tip, od, cekirdek, boy, kod) {
             return 'Tasarım yayımlanmadı: çözücü bu ' + tip + ' yakıt '
                 + 'bloğunu kuramadı (dış çap ' + I18N_SAYI(od) + ' mm, '
                 + 'çekirdek çapı ' + I18N_SAYI(cekirdek) + ' mm, uzunluk '
                 + I18N_SAYI(boy) + ' mm; çözücü kodu ' + kod + '). Yakıt '
                 + 'bloğu ölçülerini denetleyin.';
         }],
        /* v3.0.1 (27 Eki, V301/K-C2, NK-29/NK-70) — yakıt kimliği ⟷ yanma
           hızı rejim tablosu çelişkisi (solid_rocket_engine.py
           _resolve_propellant_type ve 8. blok). Bekçi:
           tests/test_v301_kati_yakit_kimligi.py */
        [/^No design was published: the burn-rate regime table '([^']+)' \((burn_rate_law|burn_rate_preset)\) belongs to a different propellant than the selected propellant '([^']+)' \(propellant_type\)\. The thrust curve, burn time and pressure would come from '[^']+' while the identity says '[^']+'\. Select the preset of the same propellant, or 'custom' to use the a-n pair\.$/,
         function (_t, yasa, alan, kimlik) {
             return 'Tasarım yayımlanmadı: \'' + yasa + '\' yanma hızı rejim '
                 + 'tablosu (' + alan + ') seçili yakıttan (\'' + kimlik
                 + '\', propellant_type) farklı bir yakıta ait. İtki eğrisi, '
                 + 'yanma süresi ve basınç \'' + yasa + '\' yakıtından, kimlik '
                 + 'ise \'' + kimlik + '\' yakıtından gelirdi. Aynı yakıtın '
                 + 'hazır ayarını ya da a-n çiftini kullanmak için \'custom\' '
                 + 'seçin.';
         }],
        [/^No design was published: no propellant_type was sent and the two fields that name a propellant disagree - (\w+) = '([^']*)' is the catalogue record '([^']+)', (\w+) = '([^']*)' is '([^']+)'\. Choosing one would mix two propellants \(burn rate from one, identity from the other\)\. Send propellant_type \(the solid page's catalogue selector\) or make the two fields agree\.$/,
         function (_t, a1, d1, k1, a2, d2, k2) {
             return 'Tasarım yayımlanmadı: propellant_type gönderilmedi ve '
                 + 'yakıt adlandıran iki alan çelişiyor - ' + a1 + ' = \''
                 + d1 + '\' \'' + k1 + '\' katalog kaydı, ' + a2 + ' = \''
                 + d2 + '\' ise \'' + k2 + '\'. Birini seçmek iki yakıtı '
                 + 'karıştırırdı (yanma hızı birinden, kimlik ötekinden). '
                 + 'propellant_type gönderin (katı sayfasının katalog '
                 + 'seçicisi) ya da iki alanı uyumlu yapın.';
         }],
        [/^No design was published: (\d+) input\(s\) could not be used as entered and HRMA does not replace them with built-in values: (.+)\. Correct the field\(s\) and calculate again\.$/,
         function (_t, sayi, maddeler) {
             var birimTr = {'segments': 'segment', 'bolts': 'cıvata',
                            'points': 'uç', 'deg': '°'};
             var parcalar = String(maddeler).split('; ');
             var cevrilen = [];
             for (var i = 0; i < parcalar.length; i++) {
                 var p = parcalar[i], m, tr = null;
                 if ((m = /^(\w+) = (.+) is outside the accepted range (\S+) to (\S+?)(?: (\S+))?$/.exec(p))) {
                     var birim = m[5] ? (' ' + (birimTr[m[5]] || m[5])) : '';
                     tr = alanAdi(m[1]) + ' = ' + I18N_SAYI(m[2]) + ', kabul edilen '
                         + I18N_SAYI(m[3]) + ' - ' + I18N_SAYI(m[4]) + birim
                         + ' aralığının dışında';
                 } else if ((m = /^(\w+) = (.+) is not a whole number \(accepted (\S+) to (\S+)\)$/.exec(p))) {
                     tr = alanAdi(m[1]) + ' = ' + I18N_SAYI(m[2]) + ' tam sayı değil '
                         + '(kabul edilen ' + I18N_SAYI(m[3]) + ' - '
                         + I18N_SAYI(m[4]) + ')';
                 } else if ((m = /^(\w+) = (.+) is a true\/false flag, not a number$/.exec(p))) {
                     tr = alanAdi(m[1]) + ' = ' + m[2] + ' bir doğru/yanlış bayrağı, '
                         + 'sayı değil';
                 } else if ((m = /^(\w+) is not a finite number$/.exec(p))) {
                     tr = alanAdi(m[1]) + ' sonlu bir sayı değil';
                 } else if ((m = /^(\w+) = (.+) is not a number \(use a dot as the decimal separator\)$/.exec(p))) {
                     tr = alanAdi(m[1]) + ' = ' + m[2] + ' sayı değil (ondalık ayracı '
                         + 'olarak nokta kullanın)';
                 } else if ((m = /^(\w+) = (.+) could not be used$/.exec(p))) {
                     tr = alanAdi(m[1]) + ' = ' + m[2] + ' kullanılamadı';
                 }
                 if (tr === null) return _t;
                 cevrilen.push(tr);
             }
             return 'Tasarım yayımlanmadı: ' + sayi + ' girdi yazıldığı '
                 + 'gibi kullanılamadı ve HRMA bunların yerine yerleşik '
                 + 'değer koymaz: ' + cevrilen.join('; ') + '. Alan(lar)ı '
                 + 'düzeltip yeniden hesaplayın.';
         }],
        /* v3.0.1 (26 Eki, V301/L-A) — SIVI TASARIM REDDİ 422 CÜMLELERİ.
           Üretici: hrma/app.py ``_sivi_kapanis_reddi`` (oda çapı ⟷ boğaz,
           basınç beslemeli tank < gerekli besleme basıncı, kapanmayan
           turbopompa çevrimi) ve /calculate_liquid tank/chug kapısının 400
           cümleleri (hrma/utils/common_fixes.py validate_pressure_
           consistency). Bant dışı girdi reddi katı ucun AYNI cümlesini
           kullanır ("KATI TASARIM REDDİ 422" bloğu). Sayılar ondalık
           kanonundan geçer; tanınmayan biçimde cümle İngilizce kalır.
           Bekçi: tests/test_v301_sivi_kapilar.py */
        [/^No design was published: the chamber diameter (\S+) mm \(chamber_diameter\) gives a contraction ratio of (\S+) with the solved (\S+) mm throat, outside the accepted (\S+) to (\S+) band; the solver would otherwise drop it and size the chamber from the contraction ratio\. Enter a chamber diameter between (\S+) and (\S+) mm, or leave chamber_diameter empty\.$/,
         function (_t, dc, cr, dt, lo, hi, enAz, enCok) {
             return 'Tasarım yayımlanmadı: ' + I18N_SAYI(dc) + ' mm oda '
                 + 'çapı (chamber_diameter), çözülen ' + I18N_SAYI(dt)
                 + ' mm boğazla ' + I18N_SAYI(cr) + ' daralma oranı '
                 + 'veriyor; bu, kabul edilen ' + I18N_SAYI(lo) + ' - '
                 + I18N_SAYI(hi) + ' bandının dışında. Kabul edilseydi '
                 + 'çözücü bu değeri atıp odayı daralma oranından '
                 + 'boyutlandıracaktı. ' + I18N_SAYI(enAz) + ' ile '
                 + I18N_SAYI(enCok) + ' mm arasında bir oda çapı girin ya da '
                 + 'chamber_diameter alanını boş bırakın.';
         }],
        [/^No design was published: the pressure-fed tank pressure (\S+) bar \(feed_pressure\) is (\S+) bar below the (\S+) bar the feed chain requires \(chamber pressure \+ injector pressure drop \+ cooling jacket pressure drop \+ feed line losses; binding side: (fuel|oxidizer)\), so the tanks cannot deliver the design flow\. Enter a feed pressure of at least (\S+) bar; the recommended tank pressure with the (\S+) bar declared margin is (\S+) bar\.$/,
         function (_t, tank, acik, gerekli, taraf, enAz, pay, oneri) {
             return 'Tasarım yayımlanmadı: basınç beslemeli tank basıncı '
                 + I18N_SAYI(tank) + ' bar (feed_pressure), besleme '
                 + 'zincirinin gerektirdiği ' + I18N_SAYI(gerekli) + ' bar '
                 + 'değerinin ' + I18N_SAYI(acik) + ' bar altında (oda '
                 + 'basıncı + enjektör basınç düşümü + soğutma ceketi basınç '
                 + 'düşümü + besleme hattı kayıpları; bağlayıcı taraf: '
                 + (taraf === 'fuel' ? 'yakıt' : 'oksitleyici') + '); '
                 + 'tanklar tasarım debisini veremez. En az '
                 + I18N_SAYI(enAz) + ' bar besleme basıncı girin; '
                 + I18N_SAYI(pay) + ' bar beyanlı pay dahil önerilen tank '
                 + 'basıncı ' + I18N_SAYI(oneri) + ' bar.';
         }],
        [/^No design was published: feed_pressure was not supplied; in a pressure-fed cycle the tank pressure is the injector feed pressure and the solver does not assume one\. The feed chain requires at least (\S+) bar \(chamber pressure \+ injector pressure drop \+ cooling jacket pressure drop \+ feed line losses; binding side: (fuel|oxidizer)\)\. Enter a feed pressure of at least (\S+) bar; the recommended tank pressure with the (\S+) bar declared margin is (\S+) bar\.$/,
         function (_t, gerekli, taraf, enAz, pay, oneri) {
             return 'Tasarım yayımlanmadı: feed_pressure gönderilmedi; '
                 + 'basınç beslemeli çevrimde tank basıncı enjektörü '
                 + 'besleyen basıncın kendisidir ve çözücü bir değer '
                 + 'varsaymaz. Besleme zinciri en az ' + I18N_SAYI(gerekli)
                 + ' bar gerektiriyor (oda basıncı + enjektör basınç düşümü '
                 + '+ soğutma ceketi basınç düşümü + besleme hattı kayıpları; '
                 + 'bağlayıcı taraf: '
                 + (taraf === 'fuel' ? 'yakıt' : 'oksitleyici') + '). En az '
                 + I18N_SAYI(enAz) + ' bar besleme basıncı girin; '
                 + I18N_SAYI(pay) + ' bar beyanlı pay dahil önerilen tank '
                 + 'basıncı ' + I18N_SAYI(oneri) + ' bar.';
         }],
        [/^No design was published: the (\S+) cycle did not close at this design point - the cycle solver reports (.+)\. The pump, turbine and cycle numbers of a cycle that does not close do not describe a working engine, so they are not published\. Change the cycle, the propellants or the operating point\.$/,
         function (_t, cevrim, kodlar) {
             return 'Tasarım yayımlanmadı: ' + cevrim + ' çevrimi bu '
                 + 'tasarım noktasında kapanmadı; çevrim çözücüsünün '
                 + 'bildirdiği: ' + I18N_OLCU(kodlar) + '. Kapanmayan bir çevrimin '
                 + 'pompa, türbin ve çevrim sayıları çalışan bir motoru '
                 + 'anlatmaz, bu yüzden yayımlanmaz. Çevrimi, iticileri ya da '
                 + 'çalışma noktasını değiştirin.';
         }],
        /* Sıvı ucunun Cd kapısı (app.py OH-D16-05, invalid_discharge_
           coefficient) — sayfa artık cümleyi bastığı için TR karşılığı eklendi. */
        [/^'discharge_coefficient' must be a number in \[(\S+), (\S+)\] \(given: (.+)\)\. A discharge coefficient is the ratio of actual to ideal mass flow through an orifice, so it is dimensionless and cannot exceed 1 or be zero or negative\. No substitute value is used and the design is not published with a silently replaced coefficient\.$/,
         function (_t, lo, hi, verilen) {
             return "'discharge_coefficient' [" + I18N_SAYI(lo) + '; '
                 + I18N_SAYI(hi) + '] aralığında bir sayı olmalı (verilen: '
                 + verilen + '). Akış katsayısı bir orifisten geçen gerçek '
                 + 'debinin ideal debiye oranıdır; boyutsuzdur, 1\'i aşamaz, '
                 + 'sıfır ya da negatif olamaz. Yerine başka değer konmaz ve '
                 + 'tasarım sessizce değiştirilmiş bir katsayıyla '
                 + 'yayımlanmaz.';
         }],
        [/^Tank pressure \((\S+) bar\) must be greater than chamber pressure \((\S+) bar\)$/,
         function (_t, tank, pc) {
             return 'Tank basıncı (' + I18N_SAYI(tank) + ' bar) oda '
                 + 'basıncından (' + I18N_SAYI(pc) + ' bar) büyük olmalı';
         }],
        [/^Insufficient pressure drop\. Need at least (\S+) bar drop for proper injection$/,
         function (_t, dp) {
             return 'Basınç düşümü yetersiz. Düzgün enjeksiyon için en az '
                 + I18N_SAYI(dp) + ' bar düşüm gerekir';
         }],
        /* v3.0.1 (V301/H4) — geçici uçta blowdown ⟷ kullanıcı tank kipi reddi
           (app.py _gecici_besleme_kipi_kapisi). */
        [/^feed_mode 'blowdown' models a self-pressurising N2O tank, but this design uses tank_pressure_source = 'user' \(a pressurised feed at the user-set tank pressure\), so a blowdown curve would describe a different motor\. Use feed_mode 'regulated' for this design\.$/,
         "feed_mode 'blowdown' kendinden basınçlı bir N2O tankını modeller, "
         + "ama bu tasarım tank_pressure_source = 'user' kullanıyor "
         + '(kullanıcının verdiği tank basıncında basınçlandırılmış '
         + 'besleme); blowdown eğrisi başka bir motoru anlatırdı. Bu tasarım '
         + "için feed_mode 'regulated' kullanın."],
        [/^Total impulse \((.+)\) doesn['’]t match thrust×time \((.+)\)$/,
         'Toplam impuls ($1), itki×süre ile ($2) uyuşmuyor'],

        /* --- user_data_validation.py (ölçüm CSV dosyası içe aktarma) -- */
        [/^CSV content must be text\. Please upload a plain-text CSV file\.$/,
         'CSV içeriği metin olmalı. Düz metin bir CSV dosyası yükleyin.'],
        [/^The uploaded file is empty\. Expected a CSV with time and thrust columns \(e\.g\. (.+)\)\.$/,
         'Yüklenen dosya boş. Zaman ve itki sütunlu bir CSV bekleniyordu (ör. $1).'],
        [/^Line (.+) \((.+)\) is neither a recognized header nor numeric data; skipped\.$/,
         '$1. satır ($2) ne tanınan bir başlık ne de sayısal veri; atlandı.'],
        [/^No header row detected; assuming column 1 is time \[s\] and column 2 is thrust \[N\]\.$/,
         'Başlık satırı bulunamadı; 1. sütun zaman [s], 2. sütun itki [N] varsayıldı.'],
        /* Mesaj TEK parça geliyor (user_data_validation.py:252 iki dizeyi
           birleştiriyor); iki ayrı kural yazılırsa applyPatterns İLK
           eşleşmede döner ve ikinci cümle İngilizce kalır — ölçüldü. */
        [/^Could not parse thrust data: at least 2 numeric \(time, thrust\) rows are required\. Check that the file is a CSV with columns like ['"](.+)['"] \(seconds, newtons\)\.$/,
         'İtki verisi çözümlenemedi: en az 2 sayısal (zaman, itki) satırı gerekli. '
         + 'Dosyanın $1 benzeri sütunlara sahip bir CSV olduğunu denetleyin (saniye, newton).'],
        [/^Time values were not sorted; rows were re-ordered by time\.$/,
         'Zaman değerleri sıralı değildi; satırlar zamana göre yeniden sıralandı.'],
        [/^Duplicate time stamps removed \(first occurrence kept\)\.$/,
         'Yinelenen zaman damgaları kaldırıldı (ilk görülen korundu).'],
        [/^Could not parse thrust data: fewer than 2 distinct time stamps remain after cleaning\.$/,
         'İtki verisi çözümlenemedi: temizlemeden sonra 2 farklı zaman damgasından az kaldı.'],
        [/^Negative thrust values present — check load-cell tare\/offset\. Values were kept as-is\.$/,
         'Negatif itki değerleri var — yük hücresi darasını/ofsetini denetleyin. Değerler olduğu gibi korundu.'],
        [/^(.+) curve time and thrust arrays must be 1-D and of equal length\.$/,
         '$1 eğrisinin zaman ve itki dizileri tek boyutlu ve eşit uzunlukta olmalı.'],
        [/^(.+) curve needs at least 2 points\.$/, '$1 eğrisi en az 2 nokta gerektirir.'],
        [/^(.+) curve contains non-finite values\.$/, '$1 eğrisi sonlu olmayan değer içeriyor.'],
        [/^(.+) curve has duplicate time stamps; clean the data first \((.+)\)\.$/,
         '$1 eğrisinde yinelenen zaman damgaları var; önce veriyi temizleyin ($2).'],
        [/^(.+) curve dict must contain ['"](.+)['"] and ['"](.+)['"] keys\.$/,
         '$1 eğrisi sözlüğü $2 ve $3 anahtarlarını içermeli.'],
        [/^(.+) curve must be a dict with (.+) or a \(time, thrust\) pair of arrays\.$/,
         '$1 eğrisi $2 anahtarlı bir sözlük ya da (zaman, itki) dizi çifti olmalı.'],
        [/^Thrust curve peak is not positive; cannot determine burn time\.$/,
         'İtki eğrisinin tepe değeri pozitif değil; yanma süresi belirlenemiyor.'],
        [/^User and predicted thrust curves do not overlap in time; check the time units\/offset of the uploaded data\.$/,
         'Kullanıcı ve öngörülen itki eğrileri zamanda örtüşmüyor; yüklenen verinin zaman birimini/ofsetini denetleyin.'],
        [/^Predicted curve has non-positive total impulse or peak thrust; comparison is not meaningful\.$/,
         'Öngörülen eğrinin toplam impulsu veya tepe itkisi pozitif değil; karşılaştırma anlamlı değil.'],
        [/^Burn time evaluated to zero; the thrust curve may be a single spike or corrupted\.$/,
         'Yanma süresi sıfır çıktı; itki eğrisi tek bir sivri uç olabilir ya da bozuk olabilir.'],
        [/^Unit row suggests non-SI units \((.+)\); values are used as-is\. Expected seconds and newtons\.$/,
         'Birim satırı SI dışı birim gösteriyor ($1); değerler olduğu gibi kullanıldı. Saniye ve newton bekleniyordu.'],
        [/^Unit row \((.+)\) skipped\.$/, 'Birim satırı ($1) atlandı.'],
        [/^Comma-delimited file appears to use commas as decimal separators too; adjacent fields were merged \((.+)\)\.$/,
         'Virgülle ayrılmış dosya virgülü ondalık ayırıcı olarak da kullanıyor gibi; komşu alanlar birleştirildi ($1).'],

        /* --- importers/motor_file.py (RASP .eng / RSE .rse) ------------- */
        [/^Final thrust point is (.+); a RASP\/RSE curve is expected to end near 0 N \(burnout\)\.$/,
         'Son itki noktası $1; RASP/RSE eğrisinin 0 N civarında bitmesi beklenir (yanma sonu).'],
        [/^Header propellant mass \((.+)\) exceeds loaded mass \((.+)\); check the file\.$/,
         'Başlıktaki itici kütlesi ($1) yüklü kütleyi ($2) aşıyor; dosyayı denetleyin.'],
        [/^File contains more than one motor definition; only the first motor was parsed\.$/,
         'Dosya birden çok motor tanımı içeriyor; yalnız ilk motor çözümlendi.'],
        [/^Implicit RASP ignition point \((.+)\) prepended per format definition\.$/,
         'Örtük RASP ateşleme noktası ($1) biçim tanımı gereği başa eklendi.'],
        [/^File contains (.+) engine definitions; the first usable one is selected by default\.$/,
         'Dosya $1 motor tanımı içeriyor; öntanımlı olarak ilk kullanılabilir olan seçildi.'],
        [/^Thrust at t=0 is (.+); RASP curves normally start from 0 N\.$/,
         't=0 anındaki itki $1; RASP eğrileri normalde 0 N ile başlar.'],
        [/^An <eng-data> point without numeric t\/f attributes was skipped\.$/,
         'Sayısal t/f niteliği olmayan bir <eng-data> noktası atlandı.'],
        [/^Engine ['"](.+)['"] skipped: (.+)$/, '$1 motoru atlandı: $2'],
        [/^Declared (.+) \((.+)\) differs from the value computed from the curve \((.+)\) by (.+)%\.$/,
         'Bildirilen $1 ($2), eğriden hesaplanan değerden ($3) %$4 farklı.'],
        [/^Line (.+) skipped \(not numeric time\/thrust data\): (.+)\.$/,
         '$1. satır atlandı (sayısal zaman/itki verisi değil): $2.'],

    /* --- analysis/regen_cooling.py + enjektör uçları ---------------- */
        [/^COKING: RP-1 coolant-side wall temperature reaches (\S+) K, above the ~(\S+) K coking threshold \((.+)\) — carbon deposition and channel fouling likely\.$/,
         'KOKLAŞMA: RP-1 soğutucu tarafı cidar sıcaklığı $1 K değerine ulaşıyor, ~$2 K koklaşma eşiğinin üstünde ($3) — karbon birikmesi ve kanal tıkanması olası.'],
        /* V301/DİL-2 — L-KABUK kulvarının iki eşikli koklaşma uyarıları
           (regen_cooling.py; 728 K NASA SP-8087 ölçütü, 561 K yazılım
           uyarı eşiği). Sayılar ve kaynak künyeleri AYNEN. */
        [/^COKING LIMIT: RP-1 coolant-side wall temperature reaches (\S+) K, above the (\S+) K design criterion of NASA SP-8087 sec\. 3\.1\.1\.5\.4 for RP-1 liquid-wall temperature — the design does not meet this criterion\.$/,
         'KOKLAŞMA SINIRI: RP-1 soğutucu tarafı cidar sıcaklığı $1 K değerine ulaşıyor; NASA SP-8087 bölüm 3.1.1.5.4\'ün RP-1 sıvı cidar sıcaklığı için koyduğu $2 K tasarım ölçütünün üstünde — tasarım bu ölçütü sağlamıyor.'],
        [/^COKING RISK: RP-1 coolant-side wall temperature reaches (\S+) K, above the (\S+) K deposit-risk warning level \(software warning based on NASA CR-168277 copper-tube deposits at 560-750 K; validate for the application\) and below the (\S+) K NASA SP-8087 criterion — not a statement that the wall stays deposit-free\.$/,
         'KOKLAŞMA RİSKİ: RP-1 soğutucu tarafı cidar sıcaklığı $1 K değerine ulaşıyor; $2 K birikim riski uyarı düzeyinin üstünde (NASA CR-168277\'deki 560-750 K bakır tüp birikimlerine dayanan yazılım uyarısı; uygulama için doğrulanmalı) ve $3 K NASA SP-8087 ölçütünün altında — cidarın birikimsiz kalacağı anlamına gelmez.'],
        [/^CRITICAL: peak hot-wall temperature (\S+) K exceeds (.+) melting point (\S+) K — liner failure\.$/,
         'KRİTİK: tepe sıcak cidar sıcaklığı $1 K, $2 malzemesinin $3 K erime sıcaklığını aşıyor — astar hasarı.'],
        /* V301/L-KARBON — LOX/RP-1 karbon birikimi (regen_cooling.py). */
        [/^CARBON DEPOSIT: LOX\/RP-1 gas-side carbon deposit resistance applied \(NASA SP-125 Fig\. 4-25; throat R_d (\S+) m2K\/W\)\. Peak hot wall (\S+) K with the deposit, (\S+) K where it spalls \(no deposit, same coolant state\)\.$/,
         'KARBON BİRİKİMİ: LOX/RP-1 gaz tarafı karbon birikimi ısıl direnci uygulandı (NASA SP-125 Şekil 4-25; boğazda R_d $1 m2K/W). Tepe sıcak cidar birikimle $2 K, birikimin döküldüğü yerde $3 K (birikim yok, aynı soğutucu durumu).'],
        [/^CRITICAL: where the carbon deposit spalls the hot wall reaches (\S+) K, above the (.+) melting point (\S+) K — local liner failure \(NASA SP-8087 sec\. 3\.4\.1: spalling shall not cause failure\)\.$/,
         'KRİTİK: karbon birikiminin döküldüğü yerde sıcak cidar $1 K değerine ulaşıyor, $2 malzemesinin $3 K erime sıcaklığının üstünde — yerel astar hasarı (NASA SP-8087 §3.4.1: dökülme hasara yol açmamalı).'],
        [/^CARBON DEPOSIT: carbon deposit not modelled \(out of envelope\): (.+) \(the deposit was observed experimentally only in that range, NASA TP-2862\)\.$/,
         function (_t, ic) {
             var tr = String(ic)
                 .replace(/O\/F (\S+) outside (\S+)/g, 'O/F $1, $2 bandının dışında')
                 .replace(/Pc (\S+) bar outside (\S+) bar/g, 'Pc $1 bar, $2 bar bandının dışında');
             return 'KARBON BİRİKİMİ: modellenmedi (zarf dışı): ' + tr
                 + ' (birikim deneyle yalnız bu aralıkta gözlendi, NASA TP-2862).';
         }],
        /* OH-D33-43 — fix-38a'nın (OH-D33-34) AÇIK BIRAKTIĞI İKİ DESEN.
           ÖLÇÜLDÜ (tr-07-warnings karesi, kılavuzda yayımlandı): aynı Türkçe
           panelde hem virgül hem nokta duruyordu. Virgüllü olanlar
           'Genleşme oranı 3,9', 'q=20,7 MW/m2', 'medyan sapma %-39,5';
           noktalı kalanlar tam olarak aşağıdaki iki mesajdı
           ('K_c = -6.59 < 1.5', 'Cd=0.78 ile ulaşılan hız 24.9 m/s').
           Kök: sayılar $1/$2/$3 olarak AYNEN geçiyordu, decimalText'ten
           geçmiyordu. fix-38a tek deseni onardı, bu ikisi açık kaldı.

           Kavitasyon mesajının üçüncü yakalaması ayrıca TAMAMEN İngilizce
           bir parantez taşıyor ('injector inlet P_1 = 24.0 bar, dP = 4.0 bar,
           P_v = 50.4 bar at 293 K'); o da burada çevrilir. Çeviremediği bir
           biçimle karşılaşırsa metni OLDUĞU GİBİ bırakır (uydurma yok). */
        [/^Cavitation risk: Nurick cavitation number K_c = (\S+) < (\S+) \((.+)\)$/,
         function (_t, kc, esik, ic) {
             return 'Kavitasyon riski: Nurick kavitasyon sayısı K_c = '
                 + I18N_SAYI(kc) + ' < ' + I18N_SAYI(esik)
                 + ' (' + I18N_KAVITASYON_ICI(ic) + ')';
         }],
        [/^Target injection velocity \((.+)\) is not set by hole count: with Cd=(\S+) the achieved velocity is (.+)\. Reaching the target needs dP = (.+) \(currently (.+)\)\.$/,
         function (_t, hedef, cd, ulasilan, gereken, sucan) {
             return 'Hedef püskürtme hızı (' + I18N_OLCU(hedef)
                 + ') delik sayısıyla belirlenmiyor: Cd=' + I18N_SAYI(cd)
                 + ' ile ulaşılan hız ' + I18N_OLCU(ulasilan)
                 + '. Hedefe ulaşmak için dP = ' + I18N_OLCU(gereken)
                 + ' gerekir (şu an ' + I18N_OLCU(sucan) + ').';
         }],

        /* ================================================================
           OH-Z3-04 (Z5 i18n) — REJENERATİF SOĞUTMA UYARILARININ GERİ KALANI
           ----------------------------------------------------------------
           ÖLÇÜM (bu parti): hrma/analysis/regen_cooling.py 15 uyarı üretiyor;
           bunlardan YALNIZ 2'si (COKING ve CRITICAL erime) yukarıda
           yakalanıyordu. Kalan 13'ü Türkçe arayüzde İNGİLİZCE kalıyordu —
           aralarında güvenlikle ilgili olanlar da var (kaynama, çekirdekli
           kaynama, kritik altı basınç, geometrik sığmama, yakınsamama).
           Defterin adıyla andığı 'NOTE:' ve 'GEOMETRY:' satırları bu 13'ün
           içinde; süpürme onlarla sınırlı tutulmadı, çünkü aynı listedeki
           öbür 11'i İngilizce bırakmak aynı kusurun devamı olurdu.

           SIRA: burada yakalanan metinlerin hepsi ÖZGÜL öneklidir
           ('BOILING:', 'GEOMETRY:', 'CONVERGENCE:' ...); yukarıdaki genel
           kurallarla ('WARNING: ... is an amateur propellant.' gibi)
           çakışmazlar. Sayı ve birimler yakalama grubuyla AYNEN taşınır —
           çeviri hiçbir sayıyı yeniden yazmaz.
           ================================================================ */
        [/^UNSAFE: peak hot-wall temperature (\S+) K exceeds (.+) service limit (\S+) K\.$/,
         'GÜVENSİZ: tepe sıcak cidar sıcaklığı $1 K, $2 malzemesinin $3 K servis sınırını aşıyor.'],
        [/^WARNING: peak hot-wall temperature (\S+) K exceeds (.+) allowable (\S+) K — strength margin reduced\.$/,
         'UYARI: tepe sıcak cidar sıcaklığı $1 K, $2 malzemesinin izin verilen $3 K sıcaklığını aşıyor — dayanım marjı azaldı.'],
        [/^PROPERTY RANGE: (.+?) bulk temperature leaves the internal property table band \((.+?) K\) at (\S+) station\(s\) \(T_bulk (.+?) K\); properties there are FROZEN at the nearest band edge — transport properties and the coolant-side coefficient are an extrapolation outside the source validity envelope\.$/,
         'ÖZELLİK ARALIĞI: $1 yığın sıcaklığı, iç özellik tablosunun bandını ($2 K) $3 istasyonda terk ediyor (T_bulk $4 K); oradaki özellikler en yakın bant kenarında DONDURULDU — taşınım özellikleri ve soğutucu tarafı katsayısı, kaynağın geçerlilik zarfının dışında bir dış değer atamasıdır.'],
        // V301/DİL: duvar tarafı özellik bandı uyarısı (regen_cooling.py
        // "PROPERTY RANGE (WALL)"); TR ekranda İngilizce kalıyordu ve
        // test_backend_uyari_metinleri_kapsam_bekcisi main'de de kırmızıydı.
        [/^PROPERTY RANGE \(WALL\): the (\S+) coolant-side wall temperature is above the internal property table band \((\S+)-(\S+) K\) at (\S+) station\(s\); the Sieder-Tate wall viscosity there is held at the band edge, so the \(mu_b\/mu_w\)\^0\.14 correction is UNDER-stated and the coolant-side coefficient is a conservative lower bound \(peak correction factor used (\S+)\)\.$/,
         function (_t, sogutucu, alt, ust, n, f) {
             return 'ÖZELLİK ARALIĞI (CİDAR): ' + sogutucu + ' soğutucu tarafı'
                 + ' cidar sıcaklığı ' + n + ' istasyonda iç özellik tablosunun'
                 + ' bandının (' + I18N_SAYI(alt) + '-' + I18N_SAYI(ust) + ' K)'
                 + ' üstünde; oradaki Sieder-Tate cidar viskozitesi bant'
                 + ' kenarında tutuluyor, bu yüzden (mu_b/mu_w)^0,14 düzeltmesi'
                 + ' EKSİK hesaplanıyor ve soğutucu tarafı katsayısı ihtiyatlı'
                 + ' bir alt sınırdır (kullanılan en büyük düzeltme çarpanı '
                 + I18N_SAYI(f) + ').';
         }],
        // V301/DİL: sıvı otojen basınçlandırma kapsam gerekçesi
        // (liquid_rocket_engine.py _autogenous_applicable).
        [/^autogenous pressurisation is modelled only for methane\/LOX and LH2\/LOX; '([^']*)' is not supported \(the other propellants use stored helium\)$/,
         function (_t, cift) {
             return 'otojen basınçlandırma yalnız metan/LOX ve LH2/LOX için'
                 + ' modellenir; \'' + cift + '\' desteklenmiyor (diğer'
                 + ' iticiler depolanmış helyum kullanır)';
         }],
        // V301/DİL: N2O tank boşalmasının ideal-gaz kuyruğu (tank_blowdown.py).
        [/^IDEAL-GAS TAIL-OFF: the liquid is exhausted at (\S+) K \/ (\S+) bar and the remaining vapour is expanded with the IDEAL-GAS adiabatic relation \(gamma = (\S+), the ideal-gas value of N2O: CoolProp 6\.8\.0 cp\/cv at 300 K \/ 1 bar = 1\.279\)\. At the SATURATED-VAPOUR state where it is applied the assumption does not hold: the real cp\/cv at 293 K saturated vapour is 3\.107 \(2\.4x\) and the real vapour density 158\.0 kg\/m3 versus 91\.2 kg\/m3 from p\/\(RT\) \(-42%\)\. The tail-off curve is an order-of-magnitude estimate only; the liquid-phase results up to this instant are unaffected\.$/,
         function (_t, tK, pBar, gamma) {
             return 'İDEAL-GAZ KUYRUĞU: sıvı ' + I18N_SAYI(tK) + ' K / '
                 + I18N_SAYI(pBar) + ' bar\'da tükeniyor ve kalan buhar İDEAL-GAZ'
                 + ' adyabatik bağıntısıyla genişletiliyor (gamma = '
                 + I18N_SAYI(gamma) + ', N2O\'nun ideal-gaz değeri: CoolProp 6.8.0,'
                 + ' 300 K / 1 bar\'da cp/cv = 1,279). Uygulandığı DOYMUŞ BUHAR'
                 + ' durumunda bu varsayım tutmaz: 293 K doymuş buharda gerçek'
                 + ' cp/cv 3,107 (2,4 kat) ve gerçek buhar yoğunluğu 158,0 kg/m3,'
                 + ' p/(RT) ile bulunan 91,2 kg/m3\'e karşı (%-42). Kuyruk eğrisi'
                 + ' yalnız mertebe kestirimidir; bu ana kadarki sıvı faz'
                 + ' sonuçları etkilenmez.';
         }],
        [/^NOTE: minimum channel Reynolds number (\S+) is below the Dittus-Boelter turbulent floor \(~1e4\); the coolant-side coefficient there is an extrapolation\.$/,
         'NOT: en düşük kanal Reynolds sayısı $1, Dittus-Boelter türbülanslı akış tabanının (~1e4) altında; oradaki soğutucu tarafı katsayısı bir dış değer atamasıdır.'],
        [/^GEOMETRY: (\S+) channels of width (\S+) mm exceed the throat circumference \((\S+) mm\) — channels do not physically fit; reduce count\/width\.$/,
         'GEOMETRİ: $2 mm genişliğindeki $1 kanal, boğaz çevresini ($3 mm) aşıyor — kanallar fiziksel olarak sığmıyor; kanal sayısını ya da genişliğini azaltın.'],
        [/^BOILING: water exit temperature (\S+) K exceeds the saturation temperature (\S+) K at the outlet pressure — single-phase assumption violated\.$/,
         'KAYNAMA: su çıkış sıcaklığı $1 K, çıkış basıncındaki $2 K doyma sıcaklığını aşıyor — tek fazlı akış varsayımı ihlal edildi.'],
        [/^SUBCRITICAL PRESSURE: (.+?) inlet pressure (\S+) bar is below the critical pressure (\S+) bar — boiling is possible; the model stays single phase and only FLAGS the risk \(no two-phase model\)\.$/,
         'KRİTİK ALTI BASINÇ: $1 giriş basıncı $2 bar, $3 bar olan kritik basıncın altında — kaynama olasıdır; model tek fazlı kalır ve riski yalnız İŞARETLER (iki fazlı model yok).'],
        [/^NOTE: coolant bulk temperature crosses the pseudo-critical temperature \((\S+) K at inlet pressure\) along the channel — strong property variation; the enthalpy march and Jackson property-ratio corrections account for it to first order\.$/,
         'NOT: soğutucunun yığın sıcaklığı kanal boyunca sözde kritik sıcaklığı (giriş basıncında $1 K) geçiyor — özellikler güçlü biçimde değişiyor; entalpi yürüyüşü ve Jackson özellik-oranı düzeltmeleri bunu birinci mertebeden hesaba katar.'],
        [/^BOILING: coolant bulk temperature reaches\/exceeds the local saturation temperature at (\S+) station\(s\) \(subcritical pressure\) — single-phase assumption violated; results there are not valid\.$/,
         'KAYNAMA: soğutucunun yığın sıcaklığı $1 istasyonda yerel doyma sıcaklığına ulaşıyor ya da onu aşıyor (kritik altı basınç) — tek fazlı akış varsayımı ihlal edildi; oradaki sonuçlar geçerli değildir.'],
        [/^BOILING RISK: coolant bulk temperature is within (\S+) K \(screening margin\) of the local saturation temperature at (\S+) station\(s\)\.$/,
         'KAYNAMA RİSKİ: soğutucunun yığın sıcaklığı $2 istasyonda yerel doyma sıcaklığına $1 K (tarama marjı) kadar yaklaşıyor.'],
        [/^NUCLEATE BOILING RISK: coolant-side wall temperature exceeds the local saturation temperature at (\S+) station\(s\) \(subcritical pressure\) — wall boiling not modelled\.$/,
         'ÇEKİRDEKLİ KAYNAMA RİSKİ: soğutucu tarafı cidar sıcaklığı $1 istasyonda yerel doyma sıcaklığını aşıyor (kritik altı basınç) — cidar kaynaması modellenmiyor.'],
        [/^CONVERGENCE: the coupled wall balance did not converge to 1e-3 K at (\S+) station\(s\) — wall temperatures there carry iteration residual\.$/,
         'YAKINSAMA: eşleşik cidar dengesi $1 istasyonda 1e-3 K değerine yakınsamadı — oradaki cidar sıcaklıkları iterasyon artığı taşıyor.'],
        [/^NOTE: Jackson wall-side property ratios evaluated at the (.+?) EOS temperature limit \((\S+) K\) at (\S+) station\(s\) — the coolant-side coefficient there is an extrapolation \(wall-limit warnings apply independently\)\.$/,
         'NOT: Jackson cidar tarafı özellik oranları, $1 için EOS sıcaklık sınırında ($2 K) $3 istasyonda değerlendirildi — oradaki soğutucu tarafı katsayısı bir dış değer atamasıdır (cidar sınırı uyarıları bağımsız olarak geçerlidir).'],

        /* ================================================================
           OH-Z4-04 (Z5 i18n) — YAPISAL HÜKMÜN GEREKÇE CÜMLELERİ
           ----------------------------------------------------------------
           hrma/analysis/structural_analysis.py:2057-2084 dört gerekçe dalı
           üretiyor (`minimum_safety_factor_verdict_basis`). Panel bu metni
           HAM basıyordu, yani Türkçe arayüzde İngilizce kalıyordu — kural
           yazıldığı gün ÖLÜ koddu ("kanal var, kapı yok").
           KAPI 2026-08-28'de AÇILDI (OH-Z5S i18n kalanı): hem
           `panels/structural_panel.js` (yerel `SRV` yardımcısı: basis
           paragrafı, `db.message`, cidar sıcaklığı notu, `buck.source` ve
           kvTable ipuçları) hem de `app.js` hüküm şeridi metni artık
           `serverText`ten geçiriyor. Ölçüm: raw/OH/Z5S/i18nkalan (TABAN'da
           TR kipte 10 İngilizce gerekçe, şimdi 0). Bekçi:
           tests/test_z5i18n_kalan.py. İstasyon adları (chamber_hoop,
           end_cap …) MAKİNE ADIDIR ve çevrilmez — grupla aynen taşınır.
           ================================================================ */
        /* V307 DİL-SON (DİL-SUNUCU-2 KALAN 1): sunucu cümlesi artık alan
           adı ve istasyon anahtarı yerine okunur İngilizce ad basıyor
           (structural_analysis.STRUCTURAL_STATION_NAMES_EN = ekran kartının
           app.sfst.* İngilizcesi). Dört desen o okunur adları yakalar ve
           önceki Türkçe adlara eşler; TR ekran çıktısı önceki sürümle aynı.
           Tanınmayan ad varsa o liste AYNEN (başka ad konmaz); boş liste
           'none' -> 'yok'. */
        [/^No acceptance is issued and no verdict is issued at all: every safety factor in this response \((.+?)\) is the design target read back - HRMA sized those sections to meet the target, so the number cannot fall below it and carries no information about a wall you built\. Supply the real wall \/ throat \/ head thickness to earn a verdict; the target itself is graded separately \(sections HRMA sized, design target read back\)\.$/,
         function (tum, istasyonlar) {
             return 'Ne onay ne de hüküm verildi: bu yanıttaki her emniyet katsayısı (' + _yapisalIstasyonTr(istasyonlar) + ') tasarım hedefinin geri okunmasıdır — HRMA o kesitleri hedefi sağlayacak biçimde boyutlandırdı, dolayısıyla sayı hedefin altına düşemez ve sizin ürettiğiniz bir cidar hakkında hiçbir bilgi taşımaz. Hüküm kazanmak için gerçek cidar / boğaz / kapak kalınlığını girin; hedefin kendisi ayrıca derecelendirilir (HRMA\'nın boyutlandırdığı kesitler, tasarım hedefinin geri okuması).';
         }],
        [/^No acceptance is issued: the measured sections \((.+?)\) would pass, but (.+?) were sized by HRMA and therefore not verified\. An acceptance that does not cover every station is not an acceptance\. The measured-scope result is published separately \(measured-scope status\)\.$/,
         function (tum, olculen, boyutlanan) {
             return 'Onay verilmedi: ölçülen kesitler (' + _yapisalIstasyonTr(olculen) + ') geçerdi, ama ' + _yapisalIstasyonTr(boyutlanan) + ' kesitlerini HRMA boyutlandırdı ve bu yüzden doğrulanmadılar. Her istasyonu kapsamayan bir onay, onay değildir. Ölçülen kapsamın sonucu ayrı bir alanda (ölçülen kapsam durumu) yayımlanır.';
         }],
        [/^The verdict comes from the safety factor behind the verdict: the lowest safety factor actually measured on a drawn wall \((.+?)\)\. This is a measured warning and is never suppressed\. Sections not verified: (.+?); of those, (.+?) only read the design target back\.$/,
         function (tum, olculen, dogrulanmayan, geriOkuyan) {
             /* V307/DİL-EKRAN (KILAVUZ ÜB-3): istasyon adları güverte YAPISAL
                panelinin tablosuyla aynı anahtarlardan (panel.structural.mode*). */
             return 'Hüküm, çizilmiş bir cidar üstünde gerçekten ölçülen en düşük emniyet katsayısından geliyor (' + _yapisalIstasyonTr(olculen) + '). Bu ölçülmüş bir uyarıdır ve asla bastırılmaz. Doğrulanmayan kesitler: ' + _yapisalIstasyonTr(dogrulanmayan) + '; bunlardan ' + _yapisalIstasyonTr(geriOkuyan) + ' yalnız tasarım hedefini geri okuyor.';
         }],
        [/^Every station in the basket was evaluated against a user-supplied thickness \((.+?)\), so the verdict is an independent verification drawn from the safety factor behind the verdict\.$/,
         function (tum, olculen) {
             return 'Sepetteki her istasyon kullanıcının verdiği bir kalınlığa karşı değerlendirildi (' + _yapisalIstasyonTr(olculen) + '), dolayısıyla hüküm, hükmün dayandığı emniyet katsayısından çekilen bağımsız bir doğrulamadır.';
         }],
        /* V3 yapi-sf 2. tur: headline_safety_factor_source geri çekilme dalı
           (structural_analysis.py; gerekçe kodları makine adıdır, aynen taşınır). */
        [/^none: the verdict is withheld \((.+?)\), so no safety factor is promoted to the headline\. minimum_safety_factor is the basket minimum and can be the design target read back; minimum_earned_safety_factor covers only the stations that were actually measured\. Neither is a headline verdict\.$/,
         'yok: hüküm geri çekildi ($1); bu yüzden hiçbir emniyet katsayısı manşete taşınmadı. minimum_safety_factor sepetin minimumudur ve tasarım hedefinin geri okunması olabilir; minimum_earned_safety_factor yalnız gerçekten ölçülen istasyonları kapsar. İkisi de manşet hükmü değildir.'],

        /* ================================================================
           ÖH D33-3 / OH-D33-13 — `safety_analysis.verdict_basis`in
           KAPSANMAYAN İKİ DALI
           ----------------------------------------------------------------
           ÖLÇÜLDÜ (raw/OH/D33-3/arayuz-i18n/a1/once.json, M2; kanıt
           docs/user_guide/img/tr-02-results.png): Türkçe sonuç panelinde
           yapısal hüküm bloğu İngilizce bir cümle taşıyordu — "The
           user-supplied wall thickness was verified, but end_cap, nozzle
           were sized by HRMA…" — hemen altındaki hüküm cümlesi Türkçeyken
           (aynı blokta iki dil). Kaynak `hrma/app.py:20487` ve onun
           kardeşi `:20496`; yukarıdaki Z4-04 kümesi
           `minimum_safety_factor_verdict_basis` dallarını kapatmıştı ama
           `verdict_basis`in bu İKİ dalı hiçbir desene girmemişti.
           İstasyon adları ($1) MAKİNE ADIdır, grupla aynen taşınır.
           ================================================================ */
        [/^The user-supplied wall thickness was verified, but (.+?) were sized by HRMA and are therefore not verified\. No acceptance covering the whole assembly is issued; the measured-scope result is in safety_analysis\.measured_scope_status and the design target itself is graded in safety_analysis\.design_target_assessment\.$/,
         'Kullanıcının verdiği cidar kalınlığı doğrulandı, ama $1 kesitlerini HRMA boyutlandırdı ve bu yüzden doğrulanmadılar. Bütün montajı kapsayan bir onay verilmiyor; ölçülen kapsamın sonucu safety_analysis.measured_scope_status alanında, tasarım hedefinin kendisi ise safety_analysis.design_target_assessment alanında derecelendirilir.'],
        [/^Verified against the user-supplied wall thickness\.$/,
         'Kullanıcının verdiği cidar kalınlığına karşı doğrulandı.'],

        /* ================================================================
           OH-Z4-04 (Z5S kalanı, 2026-08-28) — CİDAR KAPISININ `message`i
           ----------------------------------------------------------------
           `hrma/app.py::_classify_wall_thickness_gate` DÖRT gövde üretiyor
           (`design_basis.message`). Panel ve app.js hüküm şeridi bu metni
           ARTIK `serverText`ten geçiriyor (kapı bu partide açıldı), ama
           metinlerin Türkçe karşılığı YOKTU — kapı açık, oda boştu.
           ÖLÇÜLDÜ (raw/OH/Z5S/i18nkalan): Türkçe kipte dört gövdenin dördü
           de İngilizce kalıyordu.

           İKİNCİ gövdenin (`A wall thickness WAS submitted but it …`) iç
           gerekçesi KAPALI bir kümedir (app.py:8219-8227, dört değer), bu
           yüzden iç içe desen yerine DÖRT TAM CÜMLE yazıldı: yakalama
           grubunun içini sözlükten geçirmek yarı-Türkçe cümle üretirdi
           (dosyanın kendi 'iç içe desen çözemez' notuyla aynı gerekçe).
           Sayılar ve birim adı ($1/$2/$3) MAKİNEDİR, aynen taşınır.
           ================================================================ */
        [/^No wall thickness was supplied, so HRMA sized the wall itself\. This result is a DESIGN PROPOSAL, not a verification of a wall you built\.$/,
         'Cidar kalınlığı verilmedi, bu yüzden cidarı HRMA kendisi boyutlandırdı. Bu sonuç bir TASARIM ÖNERİSİDİR, sizin ürettiğiniz bir cidarın doğrulaması değildir.'],
        [/^The supplied wall thickness was evaluated against the design pressure; this result is a verification\.$/,
         'Verilen cidar kalınlığı tasarım basıncına karşı değerlendirildi; bu sonuç bir doğrulamadır.'],
        [/^A wall thickness WAS submitted but it could not be read as a number \(check the decimal separator: HRMA reads 5\.0, not 5,0; booleans and lists are rejected\), so it never reached the solver; HRMA sized the wall itself instead\. The numbers below describe that other wall, so they are not a verification of your design\.$/,
         'Bir cidar kalınlığı GÖNDERİLDİ ama sayı olarak okunamadı (ondalık ayırıcıyı denetleyin: HRMA 5.0 okur, 5,0 okumaz; mantıksal değerler ve listeler kabul edilmez), bu yüzden çözücüye hiç ulaşmadı; cidarı HRMA kendisi boyutlandırdı. Aşağıdaki sayılar o başka cidarı anlatıyor, dolayısıyla sizin tasarımınızın doğrulaması değildir.'],
        [/^A wall thickness WAS submitted but it was not a positive number, and a wall has to have a positive thickness, so it never reached the solver; HRMA sized the wall itself instead\. The numbers below describe that other wall, so they are not a verification of your design\.$/,
         'Bir cidar kalınlığı GÖNDERİLDİ ama pozitif bir sayı değildi ve bir cidarın kalınlığı pozitif olmak zorundadır, bu yüzden çözücüye hiç ulaşmadı; cidarı HRMA kendisi boyutlandırdı. Aşağıdaki sayılar o başka cidarı anlatıyor, dolayısıyla sizin tasarımınızın doğrulaması değildir.'],
        [/^A wall thickness WAS submitted but it was NaN or infinite, so it never reached the solver; HRMA sized the wall itself instead\. The numbers below describe that other wall, so they are not a verification of your design\.$/,
         'Bir cidar kalınlığı GÖNDERİLDİ ama NaN ya da sonsuzdu, bu yüzden çözücüye hiç ulaşmadı; cidarı HRMA kendisi boyutlandırdı. Aşağıdaki sayılar o başka cidarı anlatıyor, dolayısıyla sizin tasarımınızın doğrulaması değildir.'],
        [/^A wall thickness WAS submitted but it was not usable, so it never reached the solver; HRMA sized the wall itself instead\. The numbers below describe that other wall, so they are not a verification of your design\.$/,
         'Bir cidar kalınlığı GÖNDERİLDİ ama kullanılabilir değildi, bu yüzden çözücüye hiç ulaşmadı; cidarı HRMA kendisi boyutlandırdı. Aşağıdaki sayılar o başka cidarı anlatıyor, dolayısıyla sizin tasarımınızın doğrulaması değildir.'],
        [/^The wall thickness you submitted was NOT the one evaluated: the solver rejected it \(out of range or unreadable\) and fell back to its own value\. The numbers below describe that other wall, so they are not a verification of your design\. \(submitted (.+?) mm, evaluated (.+?) mm; this endpoint reads the field in (.+?)\.\)$/,
         'Gönderdiğiniz cidar kalınlığı değerlendirilen kalınlık DEĞİLDİ: çözücü onu reddetti (aralık dışı ya da okunamaz) ve kendi değerine düştü. Aşağıdaki sayılar o başka cidarı anlatıyor, dolayısıyla sizin tasarımınızın doğrulaması değildir. (gönderilen $1 mm, değerlendirilen $2 mm; bu uç alanı $3 biriminde okur.)'],

        /* --- app.py son i18n borcu (2026-08-04): tüketilmeyen enjektör
           girdisi uyarıları + CAD/yörünge hata gövdeleri.
           SIRA ÖNEMLİ: özel 'pattern is not modelled' kuralı, genel
           'was not consumed' kuralından ÖNCE gelmeli — genel kuralın
           2. grubu yalnız SÖZLÜKTEN geçer, iç içe desen çözemez. */
        [/^Input '(.+)' was not consumed: the '(.+)' pattern is not modelled on this path; use the Injector Design panel for a full solution \((.+)\)$/,
         '\'$1\' girdisi kullanılmadı: \'$2\' düzeni bu yolda modellenmiyor; tam çözüm için Enjektör Tasarımı panelini kullanınız ($3)'],
        [/^Input '(.+)' was not consumed: (.+)$/,
         '\'$1\' girdisi kullanılmadı: $2', [2]],
        [/^the '(.+)' pattern is not modelled on this path; use the Injector Design panel for a full solution \((.+)\)$/,
         '\'$1\' düzeni bu yolda modellenmiyor; tam çözüm için Enjektör Tasarımı panelini kullanınız ($2)'],
        /* V306/HİBRİT-KÜTLE (kalem 8) · çizilebilir kamara boyu bandı
           (cad_visualization CHAMBER_LENGTH_MAX_BASIS; üst sınır HRMA seçimi). */
        [/^CAD generation failed: chamber_length_out_of_range: chamber length ([0-9.eE+-]+) as published(?: \(length_units='[^']*'\))? is outside the band this exporter can draw \[([0-9.eE+-]+), ([0-9.eE+-]+)\] m \(both bounds included\); no substitute length is used; the upper bound is an HRMA choice for the in-memory assembly \(STL, 3D view, mass breakdown\), not a physical limit; the STEP package is built by a separate generator$/,
         'CAD üretilemedi: kamara boyu $1 m, bellek içi montajın çizebildiği [$2; $3] m bandının dışında (iki uç dâhil); yerine başka bir boy konmadı. Üst sınır bellek içi montaj (STL, 3B görünüm, kütle dökümü) için HRMA seçimidir, fiziksel bir sınır değildir; STEP paketi ayrı bir üreticiyle kurulur'],
        [/^CAD generation failed: (.+)$/, 'CAD üretilemedi: $1'],
        [/^Trajectory plot could not be generated: (.+)$/,
         'Yörünge grafiği üretilemedi: $1'],
        /* ÖH D21 / OH-D21-01 — enjektör L/D kapısının 'HÜKÜM VERİLMEDİ' uyarısı
           (hrma/utils/injector_design.py, D20 app-api L/D kapısı). Sayı taşıdığı
           için desene girer; taban kaydı-5 bekçisi (test_i18n_charts::
           test_backend_uyari_metinleri_kapsam_bekcisi) bu metni %90,9 kapsamla
           çevrilmemiş yakalamıştı. */
        [/^L\/D band check NOT ISSUED: L\/D = (.+) is computed from the module default plate thickness \((.+) mm\), not from this design; supply plate_thickness \(orifice length\) to obtain the 3-5 band verdict\.$/,
         'L/D bant denetimi VERİLMEDİ: L/D = $1 bu tasarımdan değil, modülün varsayılan plaka kalınlığından ($2 mm) hesaplandı; 3-5 bant hükmü için plate_thickness (delik uzunluğu) verin.'],
        /* V301/HİBRİT-DIŞA (kalem 4): kazanılmamış plakada L/D artık
           yayımlanmıyor; uyarı sayı taşımaz (injector_design.LD_NOT_ISSUED_WARNING).
           Yukarıdaki eski biçim kayıtlı sonuçlar için kalır. */
        [/^L\/D band check NOT ISSUED: no plate thickness \(orifice length\) was supplied, so L\/D is not computed for this design; supply plate_thickness to obtain the 3-5 band verdict\.$/,
         'L/D bant denetimi VERİLMEDİ: plaka kalınlığı (delik uzunluğu) verilmedi, bu yüzden bu tasarım için L/D hesaplanmadı; 3-5 bant hükmü için plate_thickness verin.'],
        /* ÖH D33-3 / OH-D33-46 — HTPB YANLILIK BEYANININ ZARF GEREKÇESİ.

           ÖLÇÜLEN KUSUR (bu depo, 16 Eylül 2026; hibrit 1 kN, HTPB,
           oksitleyici LOX/H2O2): ``warn.hybrid.htpb_coeff_bias``
           yükündeki ``campaign_scope_reason`` alanı Türkçe uyarı
           panelinde OLDUĞU GİBİ İngilizce basılıyordu. Alanın Python
           tarafında DÜZ METİN kalması zorunludur — sözleşmesini
           ``tests/test_d32_hibrit_a1.py`` kilitliyor (``isinstance(str)``
           + zarfın ve koşunun ADI metnin içinde geçmeli) — bu yüzden
           çevirisi sunucu-metni kanalına düşer, tam da bu tablonun işi.

           Oksitleyici adları (n2o / lox / h2o2) MAKİNEDİR, aynen taşınır;
           Python tarafı koşunun adını ``%r`` ile yazdığı için tek tırnak
           deseni de burada soyulur. Eşleşme yoksa metin AYNEN döner
           (fail-closed). */
        [/^The published bias body was measured on HTPB\/(.+?) campaigns only; this run uses '(.+?)', which is outside that envelope\. The band is reported for the coefficient in force, NOT as a validated bias for this oxidizer\. No bias was extrapolated\.$/,
         'Yayımlanan yanlılık gövdesi yalnız HTPB/$1 kampanyalarında ölçüldü; bu koşu $2 kullanıyor, yani o zarfın DIŞINDA. Bant, yürürlükteki katsayı için bildiriliyor; bu oksitleyici için DOĞRULANMIŞ bir yanlılık olarak DEĞİL. Hiçbir yanlılık dışdeğerlemesi yapılmadı.'],
        /* ==============================================================
           ÖH D37 · A1b dil-cozucu-nesri — ÇÖZÜCÜ NESRİ (serverText kanalı)
           ==============================================================
           Her desen üreticinin KENDİ cümlesiyle birebirdir (dosya:satır
           kalem başında); tests/test_d37_dil_b1.py cümleyi ÜRETİCİDEN alır
           (gerçek SafetyAnalyzer / _two_phase_correction_state / sampling
           bloğu), elle yazılmış kopyadan değil. Tırnak içindeki adlar
           (itici, sınıf, alan adı) MAKİNEDİR, aynen taşınır; sayılar
           YAKALANAN / I18N_SAYI / I18N_OLCU üzerinden ondalık kanonundan
           geçer. FAIL-CLOSED: iç parça (tane notu, kuyruk cümle, pencere
           künyesi) tanınmazsa işlev eşleşmeyi AYNEN döndürür — yarı Türkçe
           cümle üretilmez. */

        /* DV36-03 · toksik envanter dayanağı — safety_analysis.py
           _toxic_inventory (tablolu bileşen adıyla çözüldü). */
        [/^propellant_type named (.+), which is in the tabulated exposure-limit list\.$/,
         'propellant_type içinde adı geçen $1, tablolanmış maruziyet sınırı listesinde yer alıyor.'],
        [/^the request named '(.+?)', which is in the tabulated exposure-limit list\.$/,
         "istekte adı geçen '$1', tablolanmış maruziyet sınırı listesinde yer alıyor."],
        /* sınıf adı verildi, itici adı yok (liquid_biprop / hybrid_n2o) */
        [/^'(.+?)' names a propellant CLASS, not a propellant: the toxic inventory depends on which propellants are actually used \(LOX\/RP-1 and N2O4\/MMH are both liquid bipropellants and are not comparable; a hybrid's inventory is set by its oxidiser\)\. Name the propellant in propellant_type \(for example '(.+?)'\) to get an inventory\.$/,
         "'$1' bir itici değil, bir itici SINIFI adıdır: toksik envanter gerçekte hangi iticilerin kullanıldığına bağlıdır (LOX/RP-1 ile N2O4/MMH ikisi de sıvı çift iticidir ve karşılaştırılamaz; bir hibritin envanterini oksitleyicisi belirler). Envanter almak için iticiyi propellant_type alanında adıyla yazın (örneğin '$2')."],
        /* motor_type yedeği ön notu (_ad_notu) + ardından gelen sınıf
           cümlesi: ön not kendi karşılığıyla, gövde kendi kanalından
           (sunucuCevir) çevrilir; gövde çevrilemezse hiçbiri. */
        [/^The value sent in propellant_type \((.+?)\) is not one of the propellant classes HRMA has a toxic inventory rule for and no tabulated component name was found in it, so the class below was taken from motor_type \((.+?)\), NOT from what you typed\. (.+)$/,
         function (tum, gonderilen, motorTipi, govde) {
             var ic = sunucuCevir(govde, currentLang());
             if (ic === null) return tum;
             return "propellant_type alanında gönderilen değer (" + gonderilen
                 + "), HRMA'nın toksik envanter kuralı olan itici sınıflarından"
                 + ' biri değil ve içinde tablolanmış bir bileşen adı bulunamadı;'
                 + ' bu yüzden aşağıdaki sınıf yazdığınızdan DEĞİL, motor_type'
                 + ' değerinden (' + motorTipi + ') alındı. ' + ic;
         }],

        /* ÖH D37 A1b panel-js 5. tur · modellenmedi beyanı —
           safety_analysis.py EXPLOSIVE_NOT_MODELLED_REASONS (üç cümle). */
        [/^propellant_type 'not_modelled' was declared for a hybrid motor, so the explosive verdict was not evaluated\. The hybrid fuel grain is an inert polymer and is not an explosive on its own; the explosive hazard is the decomposition of the oxidiser held in the oxidiser tank, a separate vessel whose oxidiser mass and geometry are not inputs of this assessment\. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published\.$/,
         "propellant_type 'not_modelled' bir hibrit motor için beyan edildi; bu yüzden patlayıcı hükmü değerlendirilmedi. Hibrit yakıt tanesi atıl bir polimerdir ve tek başına patlayıcı değildir; patlayıcı tehlike, oksitleyici tankında tutulan oksitleyicinin ayrışmasıdır ve bu tank, oksitleyici kütlesi ile geometrisi bu değerlendirmenin girdisi olmayan ayrı bir kaptır. TNT eşdeğeri, patlama mesafesi, parça fırlatma menzili ve tahliye mesafesi yayımlanmadı."],
        [/^propellant_type 'not_modelled' was declared for a solid motor, so the explosive verdict was not evaluated\. HRMA has no primary-sourced TNT equivalent for this propellant family \(potassium nitrate\/sugar propellants such as KNDX, KNSB, KNSU and KNER, or black powder\)\. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published\.$/,
         "propellant_type 'not_modelled' bir katı motor için beyan edildi; bu yüzden patlayıcı hükmü değerlendirilmedi. HRMA içinde bu itici ailesi (KNDX, KNSB, KNSU ve KNER gibi potasyum nitrat/şeker iticiler ya da kara barut) için birincil kaynaklı bir TNT eşdeğeri yok. TNT eşdeğeri, patlama mesafesi, parça fırlatma menzili ve tahliye mesafesi yayımlanmadı."],
        [/^propellant_type 'not_modelled' was declared, so the explosive verdict was not evaluated: HRMA has no primary-sourced TNT equivalent for this propellant\. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published\.$/,
         "propellant_type 'not_modelled' beyan edildi; bu yüzden patlayıcı hükmü değerlendirilmedi: HRMA içinde bu itici için birincil kaynaklı bir TNT eşdeğeri yok. TNT eşdeğeri, patlama mesafesi, parça fırlatma menzili ve tahliye mesafesi yayımlanmadı."],

        /* V306/HİBRİT-KÜTLE (kalem 7) · sınıf BEYANSIZ kazanılmadığında
           Gurney alanları ve tahliye geri çekilir — safety_analysis.py
           FRAGMENT_THROW_WITHHELD_REASON / EVACUATION_WITHHELD_REASON
           (TR metin i18n_report.js report.safe.fragment_withheld ile aynı). */
        [/^not published: the fragment velocity, the lethal fragment range and the maximum fragment range come from the Gurney relation, which treats the propellant mass as the explosive charge; the explosive verdict for this propellant is withheld \(see "explosive verdict withheld because" above\), so no explosive charge is established and these three numbers are not earned$/,
         'yayımlanmadı: parça hızı, öldürücü parça menzili ve en büyük parça menzili, itici kütlesini patlayıcı şarj sayan Gurney bağıntısından gelir; bu iticinin patlayıcı hükmü bekletildi (yukarıdaki "Patlayıcı hükmünün bekletilme nedeni" satırına bakın), dolayısıyla patlayıcı şarj kurulmadı ve bu üç sayı kazanılmadı'],
        [/^not published: the explosion evacuation distance is the larger of the blast injury distance and the Gurney lethal fragment range; the explosive verdict for this propellant is withheld \(see "explosive verdict withheld because"\), so neither input is established$/,
         'yayımlanmadı: patlama tahliye mesafesi, patlama yaralanma mesafesi ile Gurney öldürücü parça menzilinin büyüğüdür; bu iticinin patlayıcı hükmü bekletildi ("Patlayıcı hükmünün bekletilme nedeni" satırına bakın), dolayısıyla iki girdi de kurulmadı'],

        /* DV36-03 · patlayıcı sınıfı dayanağı — safety_analysis.py
           _resolve_explosive_class (motor_type yedeği) ve
           _resolve_hybrid_explosive_class (iki uzun cümle). */
        [/^propellant_type '(.+)' is not a tabulated class; motor_type '(.+?)' selected the '(.+?)' class$/,
         "propellant_type '$1' tablodaki bir sınıf değil; '$3' sınıfını motor_type '$2' seçti"],
        [/^(propellant_type|oxidizer_type) '(.*)' is not a tabulated class; the hybrid oxidiser '(.+?)' was read from it and selected the '(.+?)' class\. The equivalence is derived from the oxidiser decomposition enthalpy \(Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, eq\. 2\), not from a liquid-bipropellant table: (.+)\.$/,
         function (tum, alan, ham, ox, sinif, tane) {
             var t = taneNotu(tane);
             if (t === null) return tum;
             return alan + " '" + ham + "' tablodaki bir sınıf değil; hibrit"
                 + " oksitleyici '" + ox + "' bu değerden okundu ve '" + sinif
                 + "' sınıfını seçti. Eşdeğerlik bir sıvı çift itici tablosundan"
                 + ' değil, oksitleyicinin ayrışma entalpisinden türetilir'
                 + ' (Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933,'
                 + ' denk. 2): ' + t + '.';
         }],
        [/^(propellant_type|oxidizer_type) '(.*)' is not a tabulated class and names no hybrid oxidiser; motor_type 'hybrid' selected the '(.+?)' class from the product default oxidiser '(.+?)'\. This is an ASSUMPTION about your motor, not something you supplied: name the oxidiser in propellant_type \(for example '(.+?)'\) to have it resolved\. Other tabulated hybrid oxidisers give a HIGHER equivalence \((.+) vs (\S+)\); note that (.+)\.$/,
         function (tum, alan, ham, sinif, ox, ornek, digerleri, varsayilan, tane) {
             var t = taneNotu(tane);
             if (t === null) return tum;
             return alan + " '" + ham + "' tablodaki bir sınıf değil ve bir"
                 + " hibrit oksitleyici adı taşımıyor; motor_type 'hybrid',"
                 + " ürünün varsayılan oksitleyicisi '" + ox + "' üzerinden '"
                 + sinif + "' sınıfını seçti. Bu, motorunuz hakkında bir"
                 + ' VARSAYIMDIR, sizin verdiğiniz bir şey değildir: çözülmesi'
                 + ' için oksitleyiciyi propellant_type alanında adıyla yazın'
                 + " (örneğin '" + ornek + "'). Tablodaki diğer hibrit"
                 + ' oksitleyiciler DAHA YÜKSEK bir eşdeğerlik verir ('
                 + I18N_OLCU(digerleri) + ', karşısında ' + I18N_SAYI(varsayilan)
                 + '); ayrıca: ' + t + '.';
         }],

        /* DV-GT21 · thrust_curve.sampling.basis — curve_sampling.py
           sampling_block şablonu; iki liste motora özgüdür (hibrit / katı
           çağıranlar) ve SÖZLÜKTEN geçer. Liste tanınmazsa İngilizce
           kalır — fail-closed: o hâlde cümlenin tamamı AYNEN döner. */
        [/^The solver time step is UNCHANGED; only the published array is thinned\. Thinning keeps, in every bucket, the samples of largest and smallest thrust \(so the peak and the envelope survive\) plus the first and last sample, the peak-pressure sample, and (.+)\. Every derived quantity in this response \((.+)\) is computed from the FULL-resolution solution, not from this array\.$/,
         function (tum, olaylar, turetilen) {
             var dil = currentLang();
             var o = lookup(normalize(olaylar), dil);
             var d = lookup(normalize(turetilen), dil);
             if (o === null || d === null) return tum;
             return 'Çözücünün zaman adımı DEĞİŞMEDİ; yalnız yayımlanan dizi'
                 + ' seyreltildi. Seyreltme her kovada en büyük ve en küçük'
                 + ' itkili örnekleri (tepe ve zarf korunur diye), ilk ve son'
                 + ' örneği, tepe basınç örneğini ve ' + o + ' tutar. Bu'
                 + ' yanıttaki her türetilmiş büyüklük (' + d + ') bu diziden'
                 + ' değil, TAM çözünürlüklü çözümden hesaplanır.';
         }],

        /* DV-GT21 · katı iki-faz düzeltmesi durum künyesi —
           solid_rocket_engine.py _two_phase_correction_state (beş dal;
           dördü ortak kuyruğu taşır). Baş cümle IKI_FAZ_BASLARI sözlüğünden, kuyruk
           ve pencere künyesi burada çevrilir. Pencerenin kaynak künyesi
           (parantez içi, NASA SP-8039 ...) KÜNYEDİR, aynen kalır. */
        [/^(.*?)The delivered Isp published by this run carries NO verified two-phase \(particle-lag\) correction\. The linear diagnostic eta_2phase = 1 - (\S+)\*X_p and the size-corrected estimate in results\.two_phase_loss are BOTH diagnostics \(applied_to_isp = false\); which of them, if either, should be applied by default is an OPEN decision\. Do not derive a verified delivered-performance claim from this Isp\. Condensed-phase anchor window for X_p: (.+)\.$/,
         function (tum, bas, k, pencere) {
             var b = ikiFazBasi(bas);
             var p = ikiFazPenceresi(pencere);
             if (b === null || p === null) return tum;
             return b + 'Bu koşunun yayımladığı teslim Isp değeri, doğrulanmış'
                 + ' bir iki-faz (parçacık gecikmesi) düzeltmesi TAŞIMAZ.'
                 + ' Doğrusal teşhis eta_2phase = 1 - ' + I18N_SAYI(k) + '*X_p'
                 + ' ile results.two_phase_loss içindeki boyut düzeltmeli'
                 + ' kestirim İKİSİ DE teşhistir (applied_to_isp = false);'
                 + ' hangisinin, uygulanacaksa, varsayılan olarak uygulanacağı'
                 + ' AÇIK bir karardır. Bu Isp değerinden doğrulanmış bir teslim'
                 + ' performansı iddiası türetmeyin. X_p için yoğuşmuş faz çapa'
                 + ' penceresi: ' + p + '.';
         }],
        [/^The condensed-phase mass fraction of this propellant is exactly zero, so the particle-lag loss is exactly zero in both models \(100\*(\S+)\*0 = 0 and 100\*K\*0\*g\(x\) = 0 for every x\)\. No correction is needed and none is applied; this is the ONLY state in which the absence of a two-phase correction is itself verified\.$/,
         'Bu iticinin yoğuşmuş faz kütle kesri tam olarak sıfırdır; bu yüzden parçacık gecikmesi kaybı iki modelde de tam olarak sıfırdır (100*$1*0 = 0 ve her x için 100*K*0*g(x) = 0). Düzeltme gerekmez ve uygulanmaz; iki-faz düzeltmesinin YOKLUĞUNUN kendisinin doğrulandığı TEK durum budur.'],

        /* DV36-21 · G-1 tarama işaretinin not satırları — visualization.py
           _combustion dashboard (notlar '- ' ile başlar; tire kuralı
           translateSegment içinde ayrılır ve gövde buradan geçer). */
        [/^Sweep maximum O\/F (\S+) is a grid node of a (\d+)-point sea-level-exit sweep; the canonical optimum O\/F is the solver's own value, searched continuously at the design expansion ratio, so the two differ\.$/,
         'Tarama azamisi O/F $1, $2 noktalı deniz seviyesi çıkışlı bir taramanın ızgara düğümüdür; kanonik optimum O/F çözücünün kendi değeridir ve tasarım genişleme oranında sürekli aranır; bu yüzden ikisi farklıdır.'],
        [/^This run O\/F (\S+) is OUTSIDE the swept band (\S+)-(\S+); the curve does not cover the operating point\.$/,
         'Bu koşumun O/F değeri $1, taranan $2-$3 bandının DIŞINDA; eğri çalışma noktasını kapsamıyor.'],
        [/^Sweep maximum sits on the END of the swept band \(O\/F (\S+)\); it is the largest value IN THIS BAND, not a proven optimum - the true peak may lie outside\.$/,
         'Tarama azamisi taranan bandın UCUNDA duruyor (O/F $1); BU BANTTAKİ en büyük değerdir, kanıtlanmış bir optimum değildir - gerçek tepe bandın dışında olabilir.'],
        /* ÖH D37 · A1c panel-dil (K5 d) — A1b-3 panel-js OH-D37-G2 koşu
           noktası notu (visualization.py). V306/SAYI (NR-1): çıkış künyesi
           KODU kullanıcı notundan çıktı (izin meta alanında kalır). Künyesiz
           üçüncü hâl sözlükte (DICT). */
        [/^This run point: the run O\/F solved with the exit anchored to ISA sea level and no nozzle expansion ratio - the same exit anchor as the sweep curve; it is not the motor's delivered Isp at its nozzle expansion ratio\.$/,
         'Bu koşum noktası: koşumun O/F değeri, çıkışı ISA deniz seviyesine bağlanarak ve nozul genişleme oranı olmadan çözüldü - tarama eğrisiyle aynı çıkış çapası; motorun kendi nozul genişleme oranındaki teslim Isp değeri değildir.'],
        [/^This run point: the run O\/F solved with the exit at the supplied nozzle expansion ratio; the sweep curve is anchored to ISA sea level with no expansion ratio - a different thermochemistry path, so the point need not lie on the curve\.$/,
         'Bu koşum noktası: koşumun O/F değeri, çıkış verilen nozul genişleme oranında alınarak çözüldü; tarama eğrisi genişleme oranı olmadan ISA deniz seviyesine bağlıdır - farklı bir termokimya yolu, bu yüzden noktanın eğrinin üzerinde olması gerekmez.'],

        /* V306/SAYI (NR-1) — yanma panosunun c* verimi ve kinetik verim
           satırları (visualization._combustion_efficiency_breakdown).
           Gösterge motorun manşete uyguladığı η_c* değerini okur; η_kin
           ayrı satırdır. Sayılar sunucudan; yalnız ondalık kanonundan geçer. */
        [/^c\* efficiency η_c\* = (\S+)%, applied to this run's headline \(delivered c\* = η_c\* × theoretical equilibrium c\*\); source: not entered; sourced default \(median of the measured firings in HRMA's validation records\)\.$/,
         'c* verimi η_c* = %$1; bu koşumun ana sonucuna uygulandı (teslim c* = η_c* × kuramsal denge c*). Kaynak: girilmedi; kaynaklı varsayılan (HRMA doğrulama kayıtlarındaki ölçülmüş ateşlemelerin ortancası).'],
        [/^c\* efficiency η_c\* = (\S+)%, applied to this run's headline \(delivered c\* = η_c\* × theoretical equilibrium c\*\); source: your input\.$/,
         'c* verimi η_c* = %$1; bu koşumun ana sonucuna uygulandı (teslim c* = η_c* × kuramsal denge c*). Kaynak: sizin girdiniz.'],
        [/^c\* efficiency: none applied - HRMA holds no measured value for this propellant pair and none was entered, so the headline uses the ideal \(theoretical equilibrium\) c\*\.$/,
         'c* verimi: uygulanmadı - HRMA bu itici çifti için ölçülmüş bir değer tutmuyor ve değer girilmedi; ana sonuç ideal (kuramsal denge) c* değerini kullanır.'],
        [/^Kinetic efficiency: not resolved for this run; no finite-rate nozzle loss is applied\.$/,
         'Kinetik verim: bu koşumda çözülmedi; sonlu hızlı kimya nozul kaybı uygulanmadı.'],
        [/^Kinetic efficiency η_kin = (\S+)% \(finite-rate nozzle loss\): not applied - this run uses the thrust coefficient you entered as given\.$/,
         'Kinetik verim η_kin = %$1 (sonlu hızlı kimya nozul kaybı): uygulanmadı - bu koşum girdiğiniz itki katsayısını olduğu gibi kullanır.'],
        [/^Kinetic efficiency η_kin = (\S+)% \(finite-rate nozzle loss\): applied to this run's headline thrust coefficient, not to c\*\.$/,
         'Kinetik verim η_kin = %$1 (sonlu hızlı kimya nozul kaybı): bu koşumun ana sonucundaki itki katsayısına uygulandı, c* değerine değil.'],
        [/^Kinetic efficiency η_kin = (\S+)% \(finite-rate nozzle loss\): this run does not state whether its headline thrust coefficient applies it\.$/,
         'Kinetik verim η_kin = %$1 (sonlu hızlı kimya nozul kaybı): bu koşum, ana sonucundaki itki katsayısının bunu uygulayıp uygulamadığını belirtmiyor.'],
        [/^c\* efficiency η_c\* = 100\.00%: no c\* efficiency was supplied to this analysis, so delivered c\* equals the theoretical equilibrium c\*\.$/,
         'c* verimi η_c* = %100,00: bu analize c* verimi verilmedi; teslim c* kuramsal denge c* değerine eşittir.'],
        [/^c\* efficiency η_c\* = (\S+)% = delivered c\* \/ theoretical equilibrium c\* of this analysis\.$/,
         'c* verimi η_c* = %$1 = bu analizin teslim c* / kuramsal denge c* oranı.'],
        [/^Kinetic efficiency η_kin = (\S+)% \(finite-rate correlation estimate for this analysis\): not applied to any motor result\.$/,
         'Kinetik verim η_kin = %$1 (bu analiz için sonlu hızlı kimya bağıntısı kestirimi): hiçbir motor sonucuna uygulanmadı.'],
        [/^Kinetic efficiency: not available for this analysis\.$/,
         'Kinetik verim: bu analiz için kullanılamıyor.'],

        /* DV36-22 · tasarım raporu L* notu — hybrid_rocket_engine.py
           l_star_note (iki dal). Ekrana inmesi için app.js'in notu
           SRV'den geçirmesi gerekir (DEVİR, rapor). */
        [/^Requested L\* = (\S+) m is below the volume the grain port geometry already provides; achieved L\* is (\S+) m\. Increase L\* above that value to lengthen the post-combustion chamber\.$/,
         'İstenen L* = $1 m, yakıt bloğu port geometrisinin zaten sağladığı hacmin altında; ulaşılan L* $2 m. Art-yanma odasını uzatmak için L* değerini bunun üstüne çıkarın.'],
        [/^Requested L\* = (\S+) m is above the volume this chamber can enclose: the post-combustion chamber is clamped at (\S+) x the chamber diameter \((\S+) mm\), so the achieved L\* is (\S+) m\. The requested value was NOT applied\.$/,
         'İstenen L* = $1 m, bu kamaranın kapsayabileceği hacmin üstünde: art-yanma odası kamara çapının $2 katında ($3 mm) kelepçelenir, bu yüzden ulaşılan L* $4 m. İstenen değer UYGULANMADI.'],

        /* DV-MIXED · karışım bileşimi köken notu —
           database_integrations.py:312 (bileşen adları MAKİNE, aynen). */
        [/^Mixed provenance: NASA CEA species table for (.+); molecular weight derived from formula for (.+)$/,
         'Karma köken: $1 için NASA CEA tür tablosu; $2 için molekül ağırlığı formülden türetildi'],

        /* V301/DİL-2 (ÖRNEK-PANEL devri) — /api/flow-analysis kinetik notları
           (hrma/app.py _run_kinetic_chain + hızlı tarama dalı). Eksik alan
           adları formdaki adlarla (yakıt / oksitleyici). */
        [/^Fast Screening level: station arrays and the kinetic-efficiency chain require the Engineering fidelity level\.$/,
         'Hızlı Tarama seviyesi: istasyon dizileri ve kinetik verim zinciri Mühendislik doğruluk seviyesini gerektirir.'],
        [/^Kinetic-efficiency chain skipped: provide 'of_ratio' \(and optionally 'fuel_type', 'oxidizer_type'\) to evaluate nozzle kinetic losses\.$/,
         'Kinetik verim zinciri atlandı: nozul kinetik kayıplarını değerlendirmek için O/F oranını (isteğe bağlı olarak yakıt ve oksitleyici türünü) verin.'],
        [/^Kinetic-efficiency chain not evaluated: 'of_ratio' was supplied without (fuel_type|oxidizer_type|fuel_type and oxidizer_type); no propellant is assumed on your behalf\. Supply the fuel and the oxidizer to evaluate the nozzle kinetic losses\.$/,
         function (_t, eksik) {
             var ad = {'fuel_type': 'yakıt türü', 'oxidizer_type': 'oksitleyici türü',
                       'fuel_type and oxidizer_type': 'yakıt ve oksitleyici türü'}[eksik];
             return 'Kinetik verim zinciri değerlendirilmedi: O/F oranı ' + ad
                 + ' olmadan verildi; sizin yerinize itici varsayılmaz. Nozul kinetik '
                 + 'kayıplarını değerlendirmek için yakıtı ve oksitleyiciyi verin.';
         }],

        /* V301/DİL-2 (NK-35) — enjektör deseni tanımı
           (hrma/engines/injector_design.py `desc`). Sayılar AYNEN; d_j jet
           çapı simgesidir. */
        [/^(\d+) unlike doublet pairs, 2θ=(\d+)°, free jet (\d+)·d_j$/,
         '$1 farklı akışkanlı çift (unlike doublet), 2θ=$2°, serbest jet boyu $3·d_j'],
        [/^(\d+) O-F-O triplets \(outer 2×ox\., centre fuel\), 2θ=(\d+)°$/,
         '$1 O-Y-O üçlüsü (dışta 2 oksitleyici, ortada yakıt), 2θ=$2°'],
        [/^(\d+) oxidizer \+ (\d+) fuel like-doublets \(same-fluid pairs\), 2θ=(\d+)° — no blowapart risk$/,
         '$1 oksitleyici + $2 yakıt aynı akışkanlı çift (like doublet), 2θ=$3° — ayrışma (blowapart) riski yok'],
        [/^(\d+) like-doublets \(same-fluid pairs\), 2θ=(\d+)° — no blowapart risk$/,
         '$1 aynı akışkanlı çift (like doublet), 2θ=$2° — ayrışma (blowapart) riski yok'],
        [/^(\d+)-orifice showerhead \(d=(\S+) mm, axial parallel jets\)$/,
         '$1 delikli duş başlığı (d=$2 mm, eksenel paralel jetler)'],

        /* V301/DİL-2 (K-C2 D5) — katı yanma profili dayanağı
           (solid_rocket_engine.py _thrust_shape 'basis'). */
        [/^Shape is decided on the burning window \(thrust above (\d+)% of peak\), using the time-weighted mean and the interior peak, not the first and last samples\.$/,
         'Biçim yanma penceresinde (itkinin tepenin %$1 değerinin üstünde kaldığı bölüm) zaman ağırlıklı ortalama ve iç tepe ile belirlenir; ilk ve son örnekler kullanılmaz.'],

        /* V301/DİL-2 (DİL §6 AÇIK 1) — hibrit grafik altı sunucu notları.
           Kaynak: visualization.py (pano notları, yanma panosu bileşim
           notu, 3B sahne notları) ve injector_design.py doymuş giriş notu.
           Alan ve seri adları ADLA çevrilir; tanınmayan ad varsa desen
           eşleşmeyi AYNEN döndürür (çevrilmedi sayılır, yarım çeviri yok). */
        [/^The six gauges are this design point, not a live reading: they are the solved thrust, chamber pressure, mass flow, temperature, O\/F and Isp of the run, and they do not change with time\. Only the bottom row is a time history\.$/,
         'Altı gösterge bu tasarım noktasıdır, canlı okuma değildir: koşumun çözülmüş itkisi, oda basıncı, kütle debisi, sıcaklığı, O/F değeri ve Isp değeridir; zamanla değişmez. Yalnız alt sıra zaman geçmişidir.'],
        [/^Gauge scale from the solver time history — (.+)$/,
         function (tum, liste) {
             var parca = liste.split('; ').map(function (p) {
                 var m = /^(\w+): full scale (\S+) from (\w+)\.(\w+) peak$/.exec(p);
                 if (!m || !DIL2_PANO_ALAN_TR[m[1]]
                         || !DIL2_PANO_SERI_TR[m[3] + '.' + m[4]]) return null;
                 return DIL2_PANO_ALAN_TR[m[1]] + ': tam ölçek '
                     + I18N_SAYI(m[2]) + ' (' + DIL2_PANO_SERI_TR[m[3] + '.' + m[4]]
                     + ' tepesi)';
             });
             if (parca.indexOf(null) !== -1) return tum;
             return 'Gösterge ölçeği çözücünün zaman geçmişinden — ' + parca.join('; ');
         }],
        [/^No published reference series for (.+): the value is shown as a number, no needle is drawn \(a needle without a reference would imply a scale that does not exist\)\.$/,
         function (tum, liste) {
             var ad = dil2Adlar(liste, DIL2_PANO_ALAN_TR);
             if (ad === null) return tum;
             return ad.charAt(0).toLocaleUpperCase('tr') + ad.slice(1)
                 + ' için yayımlanmış referans serisi yok: değer sayı olarak '
                 + 'gösterilir, ibre çizilmez (referanssız bir ibre uydurma bir ölçek olurdu).';
         }],
        [/^Not available for this run: (.+)\.$/,
         function (tum, liste) {
             var ad = dil2Adlar(liste, DIL2_PANO_ALAN_TR);
             return (ad === null) ? tum : 'Bu koşumda yayımlanmadı: ' + ad + '.';
         }],
        [/^Bottom row units come from the solver time history: time \[s\], propellant mass \[kg\], regression rate r = \(dD\/dt\)\/2 \[mm\/s\] — the panel titled "Burn Rate" plots exactly this — and port diameter \[mm\]\.$/,
         'Alt sıranın birimleri çözücünün zaman geçmişinden gelir: zaman [s], itici kütlesi [kg], regresyon hızı r = (dD/dt)/2 [mm/s] — "Yanma hızı" başlıklı panel tam olarak bunu çizer — ve port çapı [mm].'],
        [/^Equilibrium composition: showing the (\d+) largest of (\d+) species reported by the solver; the (\d+) not drawn sum to (\S+) mole fraction\.$/,
         'Denge bileşimi: çözücünün bildirdiği $2 türün en büyük $1 tanesi gösteriliyor; çizilmeyen $3 türün toplamı $4 mol kesri.'],
        [/^Chamber wall drawn with its solved thickness (\S+) mm \(source: (.+)\) — the same value the 2-D section and the CAD export use\.$/,
         function (tum, mm, kaynak) {
             var k = dil2CidarKaynagi(kaynak);
             if (k === null) return tum;
             return 'Kamara cidarı çözülmüş kalınlığıyla çizildi: ' + I18N_SAYI(mm)
                 + ' mm (kaynak: ' + k + ') — 2B kesit ve CAD dışa aktarımı da aynı değeri kullanır.';
         }],
        [/^Lengths resolved to SI from: (.+)$/,
         function (tum, liste) {
             var parca = liste.split(', ').map(function (p) {
                 var m = /^(\w+) \(([^()]+)\)$/.exec(p);
                 if (!m || !DIL2_UZUNLUK_TR[m[1]] || !DIL2_BIRIM_KAYNAGI_TR[m[2]]) return null;
                 return DIL2_UZUNLUK_TR[m[1]] + ' (' + DIL2_BIRIM_KAYNAGI_TR[m[2]] + ')';
             });
             if (parca.indexOf(null) !== -1) return tum;
             return 'Uzunlukların SI birimi şuradan çözüldü: ' + parca.join(', ');
         }],
        /* V307 DİL-SUNUCU (DİL-HİBRİT S3) — 3B motor sahnesinin künye
           satırları (visualization.py create_3d_motor_visualization notlar). */
        [/^Fuel grain length (\S+) mm \(solver\) inside a (\S+) mm chamber: the remaining (\S+) mm are the pre\/post-combustion volumes, which carry no fuel\.$/,
         'Yakıt bloğu boyu $1 mm (çözücü), $2 mm\'lik yanma odasının içinde: kalan $3 mm, yakıt taşımayan ön/son yanma hacimleridir.'],
        [/^Chamber wall thickness is NOT drawn: this solution reports no structural wall thickness \((.+)\)\. The grey surface is the outer surface only, not a wall — do not scale a thickness from it\.$/,
         function (tum, kaynak) {
             var k = dil2CidarKaynagi(kaynak);
             if (k === null) return tum;
             return 'Kamara cidar kalınlığı ÇİZİLMEDİ: bu çözüm yapısal cidar kalınlığı bildirmiyor (' + k
                 + '). Gri yüzey yalnız dış yüzeydir, cidar değildir — ondan kalınlık ölçeklemeyin.';
         }],
        [/^The fuel grain surface is not drawn: this solution reports a grain outer diameter but no grain length, and stretching the grain over the whole chamber would show the pre\/post-combustion volumes as solid fuel\.$/,
         'Yakıt bloğu yüzeyi çizilmedi: bu çözüm blok dış çapını bildiriyor ama blok boyunu bildirmiyor; bloğu bütün yanma odası boyunca uzatmak ön/son yanma hacimlerini katı yakıt gibi gösterirdi.'],
        [/^The fuel grain surface is not drawn: the published grain stack \((\S+) mm\) does not fit the published chamber \((\S+) mm\); silently trimming it would hide the contradiction\.$/,
         'Yakıt bloğu yüzeyi çizilmedi: yayımlanan blok yığını ($1 mm) yayımlanan yanma odasına ($2 mm) sığmıyor; sessizce kırpmak bu çelişkiyi gizlerdi.'],
        [/^The fuel grain surface is not drawn: this solution does not report a grain outer diameter, and a geometric guess would be read off this scene as measured geometry\.$/,
         'Yakıt bloğu yüzeyi çizilmedi: bu çözüm blok dış çapını bildirmiyor; geometrik bir tahmin bu sahneden ölçülmüş geometri gibi okunurdu.'],
        [/^No flow channel \(port\) is drawn: this solution publishes no initial port diameter\. A liquid bipropellant engine has no fuel port, and a placeholder channel would be read off this scene as measured geometry\.$/,
         'Akış kanalı (port) çizilmedi: bu çözüm başlangıç port çapı yayımlamıyor. Sıvı çift itkili motorun yakıt portu yoktur; yer tutucu bir kanal bu sahneden ölçülmüş geometri gibi okunurdu.'],
        [/^Saturated N2O inlet \(K_c = 0\): flashing two-phase flow is expected and is modelled by Dyer NHNE in the injector circuit; hydraulic-flip verdict: see the circuit$/,
         function (tum) {
             var I = global.I18N;
             var k = 'info.injector.saturated_inlet_two_phase';
             return (I && typeof I.has === 'function' && I.has(k)) ? I.t(k) : tum;
         }]
    ];

    /* V301/DİL-2 — grafik notlarındaki makine adlarının TR karşılıkları.
       Adlar visualization.py dosyasının yayımladığı alan/seri adlarıdır
       (DASHBOARD_GAUGE_REFERANSLARI, _SCENE_3D_*_LENGTHS,
       motor_geometry.resolve_length_m kaynak dizeleri). */
    var DIL2_PANO_ALAN_TR = {
        'thrust': 'itki', 'chamber_pressure': 'oda basıncı',
        'mdot_total': 'toplam kütle debisi', 'chamber_temperature': 'oda sıcaklığı',
        'of_ratio': 'O/F', 'isp': 'Isp', 'time history (row 3)': 'zaman geçmişi (3. sıra)'
    };
    var DIL2_PANO_SERI_TR = {
        'thrust_curve.thrust': 'itki eğrisinin', 'thrust_curve.pressure': 'basınç eğrisinin',
        'thrust_curve.mass_flow': 'kütle debisi eğrisinin'
    };
    var DIL2_UZUNLUK_TR = {
        'chamber_diameter': 'oda çapı', 'chamber_length': 'oda boyu',
        'throat_diameter': 'boğaz çapı', 'exit_diameter': 'çıkış çapı',
        'port_diameter_initial': 'ilk port çapı'
    };
    var DIL2_BIRIM_KAYNAGI_TR = {
        'declared:m': 'beyanlı birim: m', 'declared:mm': 'beyanlı birim: mm',
        'motor_geometry': 'motor geometrisi kaydı', 'm': 'm', 'mm': 'mm'
    };
    function dil2Adlar(liste, tablo) {
        var ad = liste.split(', ').map(function (x) {
            return Object.prototype.hasOwnProperty.call(tablo, x) ? tablo[x] : null;
        });
        return (ad.indexOf(null) !== -1) ? null : ad.join(', ');
    }
    /* cad_visualization.py cidar kalınlığı künyesinin beş hâli. */
    function dil2CidarKaynagi(k) {
        var t = [
            [/^structural analysis \(recommended thickness\) \[\w+\]$/,
             'yapısal analiz, önerilen kalınlık'],
            [/^structural analysis \(thickness used in the stress check\) \[\w+\]$/,
             'yapısal analiz, gerilme denetiminde kullanılan kalınlık'],
            [/^structural analysis \(as-designed wall thickness, verified against the pressure load\) \[\w+\]$/,
             'yapısal analiz, tasarlanan cidar kalınlığı; basınç yüküne karşı doğrulandı'],
            [/^structural analysis \(as-designed wall thickness, SIZED to the design safety factor target - NOT a pressure-load verification\) \[\w+\]$/,
             'yapısal analiz, tasarlanan cidar kalınlığı; emniyet katsayısı hedefine göre BOYUTLANDIRILDI, basınç yükü doğrulaması DEĞİL'],
            [/^structural analysis \(as-designed wall thickness; this analysis does not state whether the wall was checked against the pressure load\) \[\w+\]$/,
             'yapısal analiz, tasarlanan cidar kalınlığı; analiz cidarın basınç yüküne karşı denetlenip denetlenmediğini söylemiyor']
        ];
        for (var i = 0; i < t.length; i++) if (t[i][0].test(k)) return t[i][1];
        return null;
    }

    /* "Etiket: değer" ve "Taban (birim)" kalıplarında yalnız etiket/taban
       çevrilir. Ayrılabilecek metinlerin sonunda kalan birim sözcükleri. */
    var UNIT_WORDS = [
        [/(\d)\s+deg\b/g, '$1 derece'],
        [/(\d)\s+holes\b/g, '$1 delik'],
        /* V306/SAYI (NR-1): yanma panosunun eski eta_c* / eta_kin satırının
           parantez parçaları buradaydı; satır tam cümleye döndü
           (MSG_PATTERNS, NR-1 bloğu). */
        [/\bmole fraction\b/g, 'mol kesri']
    ];

    /* ------------------------------------------------------------------
       Çeviri motoru
       ------------------------------------------------------------------ */

    function currentLang() {
        return (global.I18N && global.I18N.lang) || 'en';
    }

    function normalize(text) {
        return String(text).replace(/\s+/g, ' ').trim();
    }

    /* Sözlükte birebir arar. Bulamazsa null döner (metin AYNEN kalsın diye
       boş dize veya anahtar DÖNDÜRÜLMEZ). */
    function lookup(text, lang) {
        var table = DICT[lang];
        if (table && Object.prototype.hasOwnProperty.call(table, text)) {
            return table[text];
        }
        /* Sözlük i18n.js içine kaydedildiyse oradan da denenir: başka bir
           dosya aynı metni tanımlamış olabilir. */
        if (global.I18N && typeof global.I18N.has === 'function' &&
            global.I18N.lang === lang && global.I18N.has(text)) {
            return global.I18N.t(text, null);
        }
        return null;
    }

    /* ÖH D35 / OH-GT-24(d) — YAKALANAN SAYI ONDALIK KANONUNA BAĞLANDI.

       ÖLÇÜLEN KUSUR (raw/OH/D35/dil-safligi/a1/once.json, GT24):
       `serverText` desenleri cümleyi Türkçeye çeviriyor ama YAKALANAN
       sayıyı aynen basıyordu. regen_cooling.py'nin ince-cidar uyarısı TR
       ekranda "... 8.2% ... 5.0 mm ... 27.4 mm" okunuyordu: aynı panelde
       `I18N.number` ile basılan sayılar virgüllüyken desenden geçenler
       noktalı kalıyordu (tek cümlede iki ayraç).

       TEK KAYNAK: ayraç hükmü `I18N.decimalText`in (i18n.js, ÖH D30 /
       P12aB1-01) kendisidir; burada ikinci bir biçimlendirme YAZILMAZ.
       YÜZDE: TDK'da işaret sayının ÖNÜNDEDİR (%8,2). Yakalama tam olarak
       "sayı%" / "sayı %" biçimindeyse çevrilir.

       FAIL-CLOSED: tanınmayan yakalama (sürüm '2.6.27', tarih, birimli
       metin, malzeme adı) DEĞİŞTİRİLMEZ — yarım biçimlendirme, yanlış
       biçimlendirmedir. EN kipinde hiç dokunulmaz. */
    function YAKALANAN(deger, lang) {
        if (lang !== 'tr' || typeof deger !== 'string' || !deger) return deger;
        var d = I18N_SAYI(deger);
        if (d !== deger) return d;                 /* saf ondalık */
        /* V306/DİL-ORTAK (DİL-KATI D10, M-KATI-33): aralık yakalaması
           ('50.0-10000.0') da aynı kanondan — aynı cümlede iki ayraç
           ('50.0-10000.0 aralığında …, girilen: 1,5') kalmasın. Uçlar saf
           ondalık değilse (tarih, sürüm) I18N_SAYI onları değiştirmez. */
        var ar = /^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$/.exec(deger);
        if (ar) return I18N_SAYI(ar[1]) + '-' + I18N_SAYI(ar[2]);
        var m = /^([+-]?\d+(?:\.\d+)?)\s?%$/.exec(deger);
        if (m) return '%' + I18N_SAYI(m[1]);       /* yüzde: %8,2 */
        return deger;
    }

    function applyPatterns(text, rules, lang) {
        for (var i = 0; i < rules.length; i++) {
            var re = rules[i][0];
            var match = re.exec(text);
            if (!match) continue;

            var groups = rules[i][2];
            /* Şablonu DİZE olmayan kurallar (kendi değiştirici işlevini
               taşıyanlar: kavitasyon, enjeksiyon hızı, hüküm katsayısı)
               kendi işlevini koşar; sayı biçimini onlar KENDİ içinde
               yapar (I18N_OLCU / I18N_SAYI). Bu dal el değmeden kalır. */
            if (typeof rules[i][1] !== 'string') {
                return text.replace(re, rules[i][1]);
            }
            if (!groups || !groups.length) {
                /* `text.replace` SEMANTİĞİ KORUNUR (kuralların hepsi ^...$
                   çapalı değil; çevresindeki metin düşmemeli), ama `$n`
                   genişletmesi artık burada yapılır ki yakalama ondalık
                   kanonundan geçsin. */
                return text.replace(re, function () {
                    var args = arguments;
                    var parts = [];
                    for (var a = 1; a < args.length; a++) {
                        /* offset (sayı) gelince yakalamalar bitmiştir */
                        if (typeof args[a] === 'number') break;
                        parts.push(args[a]);
                    }
                    return rules[i][1].replace(/\$(\d)/g, function (whole, n) {
                        var p = parts[Number(n) - 1];
                        return (p === undefined || p === null) ? ''
                            : YAKALANAN(String(p), lang);
                    });
                });
            }

            /* Belirtilen gruplar önce sözlükten geçer (bulunamazsa aynen
               kalır), sonra şablona yerleştirilir. */
            var parts = match.slice(1);
            for (var g = 0; g < groups.length; g++) {
                var idx = groups[g] - 1;
                if (idx < 0 || idx >= parts.length) continue;
                var hit = lookup(normalize(parts[idx] || ''), lang);
                if (hit !== null) parts[idx] = hit;
            }
            return rules[i][1].replace(/\$(\d)/g, function (whole, n) {
                var p = parts[Number(n) - 1];
                return (p === undefined || p === null) ? ''
                    : YAKALANAN(String(p), lang);
            });
        }
        return null;
    }

    function applyUnitWords(text) {
        for (var i = 0; i < UNIT_WORDS.length; i++) {
            text = text.replace(UNIT_WORDS[i][0], UNIT_WORDS[i][1]);
        }
        return text;
    }

    /* Değer tarafı: sayı/birim ağırlıklı. Yalnız sözlük + birim sözcükleri. */
    function translateValue(value, lang) {
        var hit = lookup(normalize(value), lang);
        if (hit !== null) return hit;
        hit = applyPatterns(normalize(value), PATTERNS, lang);
        if (hit !== null) return hit;
        return applyUnitWords(value);
    }

    /* <br> ile bölünmemiş tek parça. */
    function translateSegment(segment, lang) {
        var raw = segment;
        var text = normalize(segment);
        if (!text) return raw;

        var hit = lookup(text, lang);
        if (hit !== null) return hit;

        hit = applyPatterns(text, PATTERNS, lang);
        if (hit !== null) return hit;

        /* ÖH D37 · A1b dil-cozucu-nesri (DV36-02, DV36-21) — FİGÜR NOT /
           UYARI KUTUSU SATIRI. visualization.py not ve uyarı kutularını
           '- ' ile başlayan satırlarla kurar (enjektör şeması
           '- WARNING: <çözücü mesajı>', yanma panosu '- <not>'). Gövde
           SUNUCU NESRİDİR: chartText sözlüğü onu tanımıyordu, satır TR
           ekranda İngilizce kalıyordu (ölçüldü: a1/once.json). Gövde
           serverText çekirdeğinden geçer; çevrilemezse satır AYNEN kalır. */
        var tire = /^-\s+(\S[\s\S]*)$/.exec(text);
        if (tire) {
            var tireTr = tireSatiri(tire[1], lang);
            if (tireTr !== null) return '- ' + tireTr;
        }

        /* <b>…</b> / <sub>…</sub> / <i>…</i> kabuğu: içi çevrilir, etiket kalır */
        var tag = /^<(b|i|sub|sup|em|strong)>([\s\S]*)<\/\1>$/.exec(text);
        if (tag) {
            return '<' + tag[1] + '>' + translateSegment(tag[2], lang) + '</' + tag[1] + '>';
        }

        /* "Etiket: değer" — etiket çevrilir, değer olduğu gibi kalır */
        var pair = /^([^:]{1,60}):\s*([\s\S]*)$/.exec(text);
        if (pair) {
            var label = lookup(normalize(pair[1]), lang);
            if (label !== null) {
                return label + ': ' + translateValue(pair[2], lang);
            }
        }

        /* "Taban (birim)" — yalnız taban çevrilir */
        var paren = /^(.+?)\s*\(([^()]*)\)$/.exec(text);
        if (paren) {
            var base = lookup(normalize(paren[1]), lang);
            if (base !== null) {
                return base + ' (' + paren[2] + ')';
            }
        }

        /* "Taban ←" / "Taban →" — ÇİFT EKSENLİ EFSANE OKU.
           ÖH D34 / OH-GT-03: katı sayfasının ``markDualAxisSeries``i
           (hrma/templates/solid.html) efsane adının SONUNA eksen yönünü
           ekler (← sol eksen, → sağ eksen). Ok BAŞIBOŞ DEĞİLDİR
           — ölçüldü: üst üste düşen iki eğriyi ayırmak için bilerek
           konmuş. Ama ek, sözlük aramasını bozuyordu: 'Thrust' →
           'İtki' çevriliyorken 'Thrust ←' İngilizce kalıyordu (ölçüm:
           a1/once_ok.json). Gövde ile ek AYRI çevrilir; gövde sözlükte
           yoksa hiçbir şey değiştirilmez (yedek davranış korunur). */
        var eksenOku = /^(.+?)\s+([\u2190\u2192])$/.exec(text);
        if (eksenOku) {
            var okGovde = lookup(normalize(eksenOku[1]), lang);
            if (okGovde !== null) return okGovde + ' ' + eksenOku[2];
        }

        /* "Taban 12.3" — sondaki sayı korunur */
        var numbered = /^(.+?)\s+([-+]?\d[\d.,]*\s*\S{0,6})$/.exec(text);
        if (numbered) {
            var head = lookup(normalize(numbered[1]), lang);
            if (head !== null) return head + ' ' + numbered[2];
        }

        return applyUnitWords(raw);
    }

    /* V301/L-E (NK-36): çevrilmiş adı `satir` satıra böler — en uzun satırı
       en kısa yapan boşluktan; uzun kalan taraf kalan satır hakkıyla yeniden
       bölünür (visualization._wrap_category_label ile aynı kural). Boşluksuz
       ad olduğu gibi döner; KISALTMA yok. */
    function yenidenSar(metin, satir) {
        if (typeof metin !== 'string' || satir < 2 || metin.indexOf(' ') === -1) {
            return metin;
        }
        var k = metin.split(' ');
        var enIyi = null, enIyiMaks = null;
        for (var i = 1; i < k.length; i++) {
            var sol = k.slice(0, i).join(' '), sag = k.slice(i).join(' ');
            var maks = Math.max(sol.length, sag.length);
            if (enIyiMaks === null || maks < enIyiMaks) {
                enIyi = [sol, sag]; enIyiMaks = maks;
            }
        }
        if (enIyi[1].length >= enIyi[0].length) {
            enIyi[1] = yenidenSar(enIyi[1], satir - 1);
        } else {
            enIyi[0] = yenidenSar(enIyi[0], satir - 1);
        }
        return enIyi[0] + '<br>' + enIyi[1];
    }

    /* V301/DİL-2 (DİL §6 AÇIK 1): SARILMIŞ DİPNOT MADDESİ BÜTÜN çevrilir.
       N-grafik G3 dipnotu taşmasın diye maddeleri sunucuda satırlara
       sarıyor (visualization.py textwrap: madde '- ' ile başlar, devam
       satırı iki boşlukla). Parça parça çeviri her satırı ayrı aradığı için
       tam cümle desenleri ("Sweep maximum O/F …", "This run point: …")
       artık eşleşmiyor, TR ekranda madde İngilizce kalıyordu (ölçüldü:
       dil-2/once.json, hybrid#combustion_analysis_plot). Madde satırları
       birleştirilip tire kuralından (tireSatiri) geçer; çeviri AYNI satır
       sayısına dengeli bölünür (sunucunun ayırdığı alt boşluk değişmez,
       dipnot lejanta inmez). FAIL-CLOSED: madde çevrilemezse satırları eski
       yoldan (parça parça) geçer; dipnot biçiminde olmayan metin null. */
    function sarilmisMaddeler(body, lang) {
        var satirlar = body.split(/<br\s*\/?>/i);
        var gruplar = [], devam = false;
        for (var i = 0; i < satirlar.length; i++) {
            var s = satirlar[i];
            if (/^-\s/.test(s)) {
                gruplar.push([s]);
            } else if (/^ {2}\S/.test(s) && gruplar.length) {
                gruplar[gruplar.length - 1].push(s);
                devam = true;
            } else {
                return null;
            }
        }
        if (!devam) return null;
        var cikti = [];
        gruplar.forEach(function (g) {
            if (g.length === 1) {
                cikti.push(translateSegment(g[0], lang));
                return;
            }
            var birlesik = normalize(g.join(' '));
            var m = /^-\s+(\S[\s\S]*)$/.exec(birlesik);
            var tr = m ? tireSatiri(m[1], lang) : null;
            if (tr === null) {
                g.forEach(function (x) { cikti.push(translateSegment(x, lang)); });
                return;
            }
            dengeliSar('- ' + tr, g.length).forEach(function (x, k) {
                cikti.push(k === 0 ? x : '  ' + x);
            });
        });
        return cikti.join('<br>');
    }

    /* Metni en çok `n` satıra, satır boylarını dengeleyerek böler (sözcük
       sınırında; sözcük kırılmaz). */
    function dengeliSar(metin, n) {
        var k = metin.split(' ');
        var gen = Math.ceil(metin.length / n);
        for (;;) {
            var satir = [], cur = '';
            k.forEach(function (w) {
                if (cur && (cur.length + 1 + w.length) > gen) {
                    satir.push(cur); cur = w;
                } else {
                    cur = cur ? cur + ' ' + w : w;
                }
            });
            if (cur) satir.push(cur);
            if (satir.length <= n) return satir;
            gen += 4;
        }
    }

    /* Grafik metni çevirisi — dışa açılan ana giriş noktası. */
    function chartText(text) {
        if (typeof text !== 'string' || !text) return text;
        var lang = currentLang();
        if (lang === 'en') return text;
        if (!DICT[lang]) return text;

        /* Plotly hover şablonlarındaki <extra></extra> kabuğu ayrılır */
        var extra = '';
        var body = text;
        var m = /^([\s\S]*?)(<extra>[\s\S]*?<\/extra>)\s*$/.exec(text);
        if (m) { body = m[1]; extra = m[2]; }

        var direct = lookup(normalize(body), lang);
        if (direct !== null) return direct + extra;

        var patterned = applyPatterns(normalize(body), PATTERNS, lang);
        if (patterned !== null) return patterned + extra;

        /* V301/L-E (NK-36): SARILMIŞ kategori adı BÜTÜN olarak çevrilir.
           Sunucu kalabalık kategori eksenini satırlara böler
           (visualization._wrap_category_label: "Cooling<br>Jacket",
           "Filters<br>(assumed<br>K=10)"). Parça parça çeviri her satırı
           ayrı aradığı için TR ekranda "Cooling Jacket", "Tank Outlet",
           "Main Valve" İngilizce, "Feed Lines" yarı çevrili ("Besleme
           Lines") kalıyordu — sözlükte tam adlar varken. Önce satırlar
           boşlukla birleştirilip tam ad aranır; bulunursa çeviri AYNI
           satır sayısına, en uzun satırı en kısa yapan boşluklardan yeniden
           bölünür (sunucunun kuralının aynısı). Bulunamazsa eski yol. */
        if (/<br\s*\/?>/i.test(body)) {
            var satirSayisi = body.split(/<br\s*\/?>/i).length;
            var butun = lookup(normalize(body.replace(/<br\s*\/?>/gi, ' ')), lang);
            if (butun !== null) return yenidenSar(butun, satirSayisi) + extra;
            var madde = sarilmisMaddeler(body, lang);
            if (madde !== null) return madde + extra;
        }

        /* <br> / <br /> ayırıcıları KORUNARAK parça parça çevrilir */
        var parts = body.split(/(<br\s*\/?>)/i);
        var out = '';
        for (var i = 0; i < parts.length; i++) {
            out += /^<br\s*\/?>$/i.test(parts[i]) ? parts[i]
                                                  : translateSegment(parts[i], lang);
        }
        return out + extra;
    }

    /* ÖH D33-3 / OH-D33-13 — SONRADAN EKLENEN SONUÇ CÜMLESİ GÖVDEYİ
       ÇEVİRİSİZ BIRAKIYORDU.

       ÖLÇÜLEN KUSUR (raw/OH/D33-3/arayuz-i18n/a1/once.json, M2 —
       gerçek /calculate yanıtı, hibrit 1 kN / 20 bar / N2O-HTPB, cidar
       3 mm): `hrma/app.py::_carry_structural_verdict_outcome` hüküm
       yayımlandığında `structural_design_basis.message` gövdesinin SONUNA
       bir cümle EKLİYOR ("Outcome of that verification: UNSAFE (risk
       HIGH). The verdict safety factor is 1.4."). Cidar kapısının yedi
       deseni `$` ile çıpalı yazılmıştı; kuyruk eklenince desen artık
       eşleşmiyor ve Türkçe kipte GÖVDENİN TAMAMI İngilizce kalıyordu.
       Ölçülen: altı gerçek gövdenin BEŞİ İngilizce (çıpalı desenin
       çalıştığı tek hâl kuyruksuz gövde). Kusuru mevcut bekçi
       görmüyordu çünkü `tests/test_z5i18n_kalan.py::
       test_cidar_kapisinin_her_govdesi_turkceye_geciyor` kapı
       fonksiyonunu DOĞRUDAN çağırıyor, yani kuyruğun eklendiği yoldan
       hiç geçmiyor (şablon-körü bekçi sınıfı).

       Onarım desenleri ÇOĞALTMAZ (kuyruk × gövde kombinatoriği): kuyruk
       KAPALI bir ailedir ve tek yerde üretilir, burada gövdeden AYRILIP
       kendi karşılığıyla değiştirilir, gövde kendi kanalından geçer.
       FAIL-CLOSED: gövde çevrilemezse hiçbir şey birleştirilmez, metin
       AYNEN döner — yarı Türkçe bir cümle üretmek, İngilizce kalmaktan
       daha kötüdür. Durum belirteçleri (UNSAFE / HIGH) ve sayılar
       MAKİNEDİR, rozetlerdeki gibi aynen taşınır. */
    var KUYRUK_DESENLERI = [
        [/ The structural module published no verdict for this run, so no acceptance is issued here either\.$/,
         ' Yapısal modül bu koşum için hüküm yayımlamadı, dolayısıyla burada da onay verilmiyor.'],
        /* ÖH D33-3 / fix-38a (ana model, 16 Eylül 2026): sayı MAKİNE
           değildir, NESİRDİR — kullanıcıya cümle içinde okunur. OH-D33-12
           gösterge kartlarını ``I18N.decimalText`` kanonuna bağladı ama bu
           kuyruk cümlesi ``toFixed`` çıktısını AYNEN taşıyordu; ölçüldü
           (kılavuz ekran tazeleme turu, tr-02-results): kart '0,81' derken
           aynı ekrandaki cümle 'Hüküm emniyet katsayısı 0.8058.' diyordu.
           Künye dökümündeki ``verdict_safety_factor: 0.805757`` MAKİNEDİR
           ve olduğu gibi kalır; ayrım cümle ⟷ künyedir. */
        [/ The verdict safety factor is (\S+?)\.$/,
         function (_t, sayi) {
             /* ÖH D35: kök `global`den okunur (küresel `window`/`I18N`
                adları bu dosyanın koşum ortamlarında var olmayabilir);
                biçimlendirme TEK KAYNAK `I18N_SAYI` üzerinden. */
             return ' Hüküm emniyet katsayısı ' + I18N_SAYI(sayi) + '.';
         }],
        [/ Outcome of that verification: (\S+?) \(risk (\S+?)\)\.$/,
         ' Bu doğrulamanın sonucu: $1 (risk $2).'],
        [/ Outcome of that verification: (\S+?)\.$/,
         ' Bu doğrulamanın sonucu: $1.'],
        /* ÖH D37 A2 hibrit · 9. tur — kırpılan enjektör planının TESLİM
           cümlesi (hrma/utils/injector_design.py
           _impingement_clamp_delivery; çarpışmalı ve kanon dışı duş başlığı
           kırpma metinlerinin ortak kuyruğu). Gövde kendi deseninden
           çevrilmezse birleştirme yapılmaz (fail-closed). */
        [/ Delivered injection area (\S+) mm\^2 against (\S+) mm\^2 required: (\S+)x \(area (\S+)% larger\)\. Target flow (\S+) kg\/s; exit velocity at the target flow (\S+) m\/s\. At the published pressure drop \((\S+) bar\) the orifice equation gives (\S+) kg\/s \((\S+)x the target\); the target flow rate is not verified at this pressure drop\.$/,
         function (_t, a_tes, a_ger, oran, fazla, mdot, v, dp, mdot_dp, oran2) {
             return ' Teslim edilen enjeksiyon alanı ' + I18N_SAYI(a_tes)
                 + ' mm², gereken ' + I18N_SAYI(a_ger) + ' mm²: '
                 + I18N_SAYI(oran) + ' kat (alan %' + I18N_SAYI(fazla)
                 + ' büyük). Hedef debi ' + I18N_SAYI(mdot) + ' kg/s; hedef '
                 + 'debide çıkış hızı ' + I18N_SAYI(v) + ' m/s. Yayımlanan '
                 + 'basınç düşümünde (' + I18N_SAYI(dp) + ' bar) orifis '
                 + 'bağıntısı ' + I18N_SAYI(mdot_dp) + ' kg/s verir (hedefin '
                 + I18N_SAYI(oran2) + ' katı); hedef debi bu basınç '
                 + 'düşümünde doğrulanmadı.';
         }]
    ];

    /* Gövdeden soyulabilen kuyrukları (en fazla KUYRUK_DESENLERI kadar)
       sondan başlayarak ayırır. Dönüş: { govde, kuyruk } — hiç kuyruk
       yoksa `kuyruk` boş dizedir. */
    function kuyrugaAyir(text) {
        var govde = text;
        var kuyruk = '';
        for (var tur = 0; tur < KUYRUK_DESENLERI.length; tur++) {
            var soyuldu = false;
            for (var i = 0; i < KUYRUK_DESENLERI.length; i++) {
                var re = KUYRUK_DESENLERI[i][0];
                var m = re.exec(govde);
                if (!m) continue;
                kuyruk = govde.slice(m.index).replace(re, KUYRUK_DESENLERI[i][1])
                    + kuyruk;
                govde = govde.slice(0, m.index);
                soyuldu = true;
                break;
            }
            if (!soyuldu) break;
        }
        return { govde: govde, kuyruk: kuyruk };
    }

    /* ÖH D35 / OH-GT-19 — BESLEME HATTI ÖN EKİ.
       valve_feedline.py artık mesajın başına hangi hat olduğunu yazıyor
       ('[fuel line] ...'). Ön ek AYRILIR, gövde normal yolundan çevrilir
       ve ön ek Türkçe karşılığıyla geri takılır; aksi hâlde aynı gövde
       için sözlükte hat sayısı kadar ikinci kayıt gerekirdi.
       FAIL-CLOSED: tanınmayan ön ek çevrilmez, metin olduğu gibi normal
       yola devam eder (uydurma hat adı yazılmaz). */
    /* V301/DİL-2 (kök 7): ret cümlesindeki makine alan adı ekranda formun
       ETİKETİYLE (reject_body.js HRMAReject.etiket — <label for>); sayfada
       etiketi yoksa ya da DOM yoksa ad AYNEN (uydurma ad yok). */
    function alanAdi(ad) {
        var R = global.HRMAReject;
        var e = (R && typeof R.etiket === 'function') ? R.etiket(ad) : null;
        return e || ad;
    }

    var HAT_ONEKLERI = {
        'fuel line': 'yakıt hattı',
        'oxidizer line': 'oksitleyici hattı',
        /* V301/K-C1 (K-A DEVİR 13): ret gövdelerinin durum kodu öneki
           (reject_body.js HRMAReject.metni '[status] …'). Kod adları
           hrma/app.py ret gövdelerindeki 'status' değerleridir. */
        'invalid_input': 'geçersiz girdi',
        'incomplete_input': 'eksik girdi',
        'validation_error': 'doğrulama hatası',
        'incomplete_geometry': 'eksik geometri',
        'inconsistent_geometry': 'tutarsız geometri',
        'unresolved_geometry_units': 'geometri birimi çözülemedi',
        /* V301/DİL-2: sıvı ucunun bant reddi kodu (L-A tek bant kapısı). */
        'input_not_accepted': 'girdi kabul edilmedi',
        /* V307/SIVI-ORTAM (NK3-S-4): sıvı ucunun ayrılan sabit nozul ve
           tasarım ortamı ret kodları (TR ekranda ham İngilizce kod
           görünüyordu). Kod adları hrma/engines/liquid_rocket_engine.py
           FIXED_NOZZLE_SEPARATED_CODE ve DESIGN_AMBIENT_*_CODE. */
        'fixed_nozzle_separated_at_design_ambient': 'sabit nozul tasarım ortamında ayrılıyor',
        'design_ambient_mode_not_recognised': 'tasarım ortamı seçimi tanınmadı',
        'design_ambient_mode_required': 'tasarım ortamı seçimi gerekli',
        'design_ambient_value_required': 'tasarım ortamı değeri gerekli',
        'design_ambient_value_not_accepted': 'tasarım ortamı değeri kabul edilmedi',
        'design_ambient_requires_expansion_ratio': 'tasarım ortamı genişleme oranını ister',
        'design_ambient_needs_cea_solution': 'tasarım ortamı yanma çözümünü ister'
    };

    /* DV36-03 — hibrit patlayıcı dayanağının yakıt bloğu notu
       (safety_analysis.py _resolve_hybrid_explosive_class grain_notu, iki
       dal). Tanınmazsa null (çağıran cümlenin tamamını AYNEN bırakır). */
    function taneNotu(metin) {
        var t = normalize(metin);
        var m = /^the fuel grain named \((.+)\) is an inert polymer and contributes no TNT equivalence$/.exec(t);
        if (m) {
            return 'adı geçen yakıt bloğu (' + m[1] + ') atıl bir polimerdir'
                + ' ve TNT eşdeğerine katkı yapmaz';
        }
        return lookup(t, currentLang());
    }

    /* DV-GT21 — katı iki-faz durum künyesinin baş cümleleri
       (solid_rocket_engine.py _two_phase_correction_state). Boş baş =
       ortak kuyruk tek başına. Tanınmazsa null. */
    var IKI_FAZ_BASLARI = [
        [/^A user two-phase efficiency multiplier eta = (\S+) was supplied and IS applied to the thrust coefficient\. It is a user input, not a validated model result: the solver does not check it against any published correlation\.$/,
         function (_t, eta) {
             return 'Kullanıcı bir iki-faz verim çarpanı eta = ' + I18N_SAYI(eta)
                 + ' verdi ve bu çarpan itki katsayısına UYGULANIR. Bu bir'
                 + ' kullanıcı girdisidir, doğrulanmış bir model sonucu'
                 + ' değildir: çözücü onu yayımlanmış hiçbir bağıntıyla'
                 + ' karşılaştırmaz.';
         }],
        [/^No condensed-phase mass fraction could be established for this propellant, so neither the linear diagnostic nor the module estimate is earned and no two-phase correction is applied\.$/,
         function () {
             return 'Bu itici için yoğuşmuş faz kütle kesri belirlenemedi;'
                 + ' bu yüzden ne doğrusal teşhis ne de modül kestirimi'
                 + ' kazanılır ve hiçbir iki-faz düzeltmesi uygulanmaz.';
         }],
        [/^X_p = (\S+) lies OUTSIDE the published data window of the K anchor \((.+)\); hrma\.analysis\.two_phase_loss refuses to produce a loss number for this state \(OUT_OF_PUBLISHED_RANGE\)\. The K anchors are aluminium-oxide anchors \(AFRPL aluminium rule of thumb; NASA SP-8039 Fig\. 8 metal-oxide family\) and this propellant's condensed phase is not necessarily Al2O3, so the linear diagnostic 100\*(\S+)\*X_p would be a pure extrapolation here\. It is therefore NOT published: detailed_analysis\.theoretical_vs_actual_isp\.two_phase_losses is null for this propellant and carries two_phase_losses_withheld_reason = "outside_anchor_envelope"\. No delivered-Isp number changes because of this: the diagnostic was never applied to the thrust coefficient \(two_phase_losses_applied = false\)\.$/,
         function (_t, xp, pencere, k) {
             var p = ikiFazPenceresi(pencere);
             if (p === null) return null;
             return 'X_p = ' + I18N_SAYI(xp) + ', K çapasının yayımlanmış veri'
                 + ' penceresinin DIŞINDA (' + p + '); hrma.analysis.two_phase_loss'
                 + ' bu durum için kayıp sayısı üretmeyi reddeder'
                 + ' (OUT_OF_PUBLISHED_RANGE). K çapaları alüminyum oksit'
                 + ' çapalarıdır (AFRPL alüminyum başparmak kuralı; NASA SP-8039'
                 + ' Fig. 8 metal oksit ailesi) ve bu iticinin yoğuşmuş fazı'
                 + ' Al2O3 olmak zorunda değildir; bu yüzden doğrusal teşhis 100*'
                 + I18N_SAYI(k) + '*X_p burada salt bir dışdeğerleme olurdu. Bu'
                 + ' nedenle YAYIMLANMAZ: detailed_analysis.theoretical_vs_actual_isp.'
                 + 'two_phase_losses bu itici için null ve'
                 + ' two_phase_losses_withheld_reason = "outside_anchor_envelope"'
                 + ' taşır. Bu yüzden hiçbir teslim Isp sayısı değişmez: teşhis'
                 + ' itki katsayısına hiç uygulanmadı (two_phase_losses_applied'
                 + ' = false).';
         }],
        [/^The size-corrected two-phase \(particle-lag\) loss estimate of hrma\.analysis\.two_phase_loss, (\S+) % \(band (\S+) %\), IS applied to the thrust coefficient, so the published Isp, thrust and total impulse include it\. No user multiplier was supplied\. Basis: NASA SP-8039 \(1971\) Fig\. 8 gives the delivered Isp efficiency as a zero-oxide intercept \(about 98 % for a 15 deg cone, the propellant-table nozzle efficiency\) minus an oxide-dependent drop \(this estimate\), and Fig\. 7 draws the divergence and two-phase losses as separate bands, so the product does not double count\. Cross-check: six 32 kg BATES firings in NASA-CR-158815 measured a mean nozzle efficiency of 0\.945 against 0\.943 from this product\. It is an engineering estimate, not a verified value for this propellant\.$/,
         function (_t, kayip, bant) {
             /* V307 KATI-DOĞRULAMA faz 3 (B1): modül tahmini uygulandı. */
             return 'İki fazlı (parçacık gecikmesi) kaybın boyut düzeltmeli tahmini, %'
                 + I18N_SAYI(kayip) + ' (bant %' + String(bant).split('-').map(I18N_SAYI).join('–')
                 + '), itki katsayısına UYGULANIR; yayımlanan Isp, itki ve toplam itki'
                 + ' bu kaybı içerir. Kullanıcı çarpanı verilmedi. Dayanak: NASA SP-8039'
                 + ' (1971) Şekil 8 teslim Isp verimini sıfır oksit kesişimi (15° koni için'
                 + ' yaklaşık %98; itici tablosundaki nozul verimi) eksi oksit kesrine bağlı'
                 + ' düşüş (bu tahmin) olarak verir; Şekil 7 ıraksama ve iki fazlı kayıpları'
                 + ' ayrı bantlarla çizer, yani çarpım çift sayım değildir. Sağlama:'
                 + ' NASA-CR-158815\'in altı 32 kg BATES ateşlemesinde ölçülen ortalama nozul'
                 + ' verimi ' + I18N_SAYI('0.945') + ', bu çarpımdan ' + I18N_SAYI('0.943')
                 + '. Mühendislik tahminidir; bu itici için doğrulanmış değer değildir.';
         }],
        [/^X_p = (\S+) > 0 and no user multiplier was supplied, so the thrust coefficient carries NO two-phase factor at all \(two_phase_efficiency_applied = 1\.0\) even though the solver's own models estimate a non-zero loss for this state\.$/,
         function (_t, xp) {
             /* ``two_phase_efficiency_applied = 1.0`` MAKİNE künyesidir
                (alan = değer), nokta kalır. */
             return 'X_p = ' + I18N_SAYI(xp) + ' > 0 ve kullanıcı çarpanı'
                 + ' verilmedi; bu yüzden çözücünün kendi modelleri bu durum için'
                 + ' sıfırdan farklı bir kayıp kestirse de itki katsayısı HİÇBİR'
                 + ' iki-faz çarpanı taşımaz (two_phase_efficiency_applied = 1.0).';
         }]
    ];

    function ikiFazBasi(bas) {
        var t = normalize(bas);
        if (!t) return '';
        for (var i = 0; i < IKI_FAZ_BASLARI.length; i++) {
            var m = IKI_FAZ_BASLARI[i][0].exec(t);
            if (!m) continue;
            var c = IKI_FAZ_BASLARI[i][1].apply(null, m);
            return (c === null) ? null : c + ' ';
        }
        return null;
    }

    /* Pencere künyesi: '0-0.4 (kaynak)' → aralık ondalık kanonundan geçer,
       kaynak künyesi AYNEN kalır; ya da çözücünün 'UNKNOWN - ...' hâli. */
    function ikiFazPenceresi(metin) {
        var t = normalize(metin);
        var m = /^(\S+)-(\S+) \((.+)\)$/.exec(t);
        if (m) return I18N_SAYI(m[1]) + '-' + I18N_SAYI(m[2]) + ' (' + m[3] + ')';
        if (t === 'UNKNOWN - the published data window could not be read from hrma.analysis.two_phase_loss') {
            return 'BİLİNMİYOR - yayımlanmış veri penceresi hrma.analysis.two_phase_loss içinden okunamadı';
        }
        return null;
    }

    /* DV36-02 — enjektör şemasının çözücü uyarı kutusu satırı
       (visualization.py:7106 ``'%s: %s' % (SEV, message)``). Önem düzeyi
       çözücünün kapalı ailesidir (injector_design: warning / info;
       çizicinin varsayılanı WARNING); tanınmayan düzey satırı ÇEVİRİSİZ
       bırakır (fail-closed, uydurma etiket yok). */
    var SEVIYE_TR = {
        'WARNING': 'UYARI',
        'INFO': 'BİLGİ',
        'ERROR': 'HATA',
        'CRITICAL': 'KRİTİK'
    };

    /* Figür not/uyarı kutusunun '- gövde' satırı: gövde sunucu nesridir ve
       serverText çekirdeğinden geçer. Çevrilemezse null (satır AYNEN). */
    function tireSatiri(govde, lang) {
        var sev = /^([A-Z]{3,10}):\s+([\s\S]+)$/.exec(govde);
        if (sev) {
            if (!Object.prototype.hasOwnProperty.call(SEVIYE_TR, sev[1])) return null;
            var mesaj = sunucuCevir(sev[2], lang);
            return (mesaj === null) ? null : SEVIYE_TR[sev[1]] + ': ' + mesaj;
        }
        return sunucuCevir(govde, lang);
    }

    /* ÖH D37 · A1b dil-cozucu-nesri — serverText'in ÇEKİRDEĞİ (sözlük →
       sunucu desenleri → grafik desenleri → kuyruk ayırma). Çeviri yoksa
       null döner; iç içe çağıranlar (figür tire satırı, ön not + gövde)
       "çevrilmedi" durumunu ayırt edip metni AYNEN bırakabilsin diye.
       serverText davranışı DEĞİŞMEDİ: null → gelen mesaj aynen. Bir desen
       işlevi fail-closed dalında eşleşmeyi aynen döndürürse (girdiyle
       özdeş çıktı) bu da "çevrilmedi" sayılır. */
    function sunucuCevir(text, lang) {
        function cevrildi(h) { return h !== null && h !== text; }
        var hit = lookup(text, lang);
        if (hit !== null) return hit;

        /* Desenler tek ve çift tırnağı birlikte kabul eder; metin ham
           hâliyle eşleştirilir ki çıktıda tırnak biçimi değişmesin. */
        hit = applyPatterns(text, MSG_PATTERNS, lang);
        if (cevrildi(hit)) return hit;

        hit = applyPatterns(text, PATTERNS, lang);
        if (cevrildi(hit)) return hit;

        /* OH-D33-13: gövde + sonradan eklenen sonuç cümlesi. */
        var parca = kuyrugaAyir(text);
        if (parca.kuyruk) {
            var govde = lookup(parca.govde, lang);
            if (govde === null) {
                govde = applyPatterns(parca.govde, MSG_PATTERNS, lang);
            }
            if (govde === null) {
                govde = applyPatterns(parca.govde, PATTERNS, lang);
            }
            if (govde !== null) return govde + parca.kuyruk;
        }
        return null;
    }

    /* Sunucudan gelen uyarı / hata metni çevirisi. */
    function serverText(message) {
        if (Array.isArray(message)) return serverTexts(message);
        if (typeof message !== 'string' || !message) return message;
        var lang = currentLang();
        if (lang === 'en' || !DICT[lang]) return message;

        var text = normalize(message);

        var onek = /^\[([^\]]+)\]\s+([\s\S]+)$/.exec(text);
        if (onek && Object.prototype.hasOwnProperty.call(
                HAT_ONEKLERI, onek[1])) {
            return '[' + HAT_ONEKLERI[onek[1]] + '] ' + serverText(onek[2]);
        }

        var hit = sunucuCevir(text, lang);
        return (hit === null) ? message : hit;
    }

    function serverTexts(list) {
        if (!Array.isArray(list)) return list;
        var out = [];
        for (var i = 0; i < list.length; i++) out.push(serverText(list[i]));
        return out;
    }

    /* ------------------------------------------------------------------
       Yayın: I18N varsa oraya, yoksa geçici taşıyıcıya (sonra taşınır)
       ------------------------------------------------------------------ */

    var HELPERS = {
        chartText: chartText,
        serverText: serverText,
        serverTexts: serverTexts,
        dictionary: DICT
    };
    global.HRMAChartI18N = HELPERS;

    function attach() {
        if (!global.I18N) return false;
        global.I18N.chartText = chartText;
        global.I18N.serverText = serverText;
        global.I18N.serverTexts = serverTexts;
        if (typeof global.I18N.register === 'function') {
            global.I18N.register(DICT, 'i18n_charts.js');
        }
        return true;
    }

    if (!attach()) {
        /* i18n.js henüz yüklenmemiş: sözlüğü kuyruğa bırak, kancaları da
           I18N belirir belirmez tak (kısa yoklama; en fazla ~5 sn). */
        (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
        if (typeof global.setTimeout === 'function') {
            var tries = 0;
            var timer = global.setInterval(function () {
                if (global.I18N) {
                    global.I18N.chartText = chartText;
                    global.I18N.serverText = serverText;
                    global.I18N.serverTexts = serverTexts;
                    global.clearInterval(timer);
                } else if (++tries > 100) {
                    global.clearInterval(timer);
                }
            }, 50);
        }
    }
})(typeof window !== 'undefined' ? window : this);
