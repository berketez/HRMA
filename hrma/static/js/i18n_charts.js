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
        en: {            '3D Hybrid Rocket Motor Visualization': '3D Hybrid Rocket Motor Visualization',
            '3D Motor Assembly': '3D Motor Assembly',
            '3D Motor Visualization': '3D Motor Visualization',
            '3D Performance Surface Analysis': '3D Performance Surface Analysis',
            '3D visualization unavailable': '3D visualization unavailable',
            'ABS Plastic': 'ABS Plastic',

            'Acceleration': 'Acceleration',
            'Acceleration (g)': 'Acceleration (g)',
            'Acceleration Profile': 'Acceleration Profile',
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
            'Combustion / Kinetic Efficiency': 'Combustion / Kinetic Efficiency',
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
            'Feed System — Slosh, Pressurant & Water Hammer': 'Feed System — Slosh, Pressurant & Water Hammer',
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
            'Frequency f1 (Hz)': 'Frequency f1 (Hz)',
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
            'Isp vs O/F (equilibrium sweep)': 'Isp vs O/F (equilibrium sweep)',
            'Landing': 'Landing',
            'Landing under parachute': 'Landing under parachute',
            'Launch': 'Launch',
            'Launch Azimuth (° from N)': 'Launch Azimuth (° from N)',
            'Launch Elevation (°)': 'Launch Elevation (°)',
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
            'Motor Outline': 'Motor Outline',
            'Motor Visualization (Simplified)': 'Motor Visualization (Simplified)',
            'Mounting Holes': 'Mounting Holes',
            'Multi-Port': 'Multi-Port',
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
            'Oxidizer Feed': 'Oxidizer Feed',
            'Oxidizer Injection Velocity': 'Oxidizer Injection Velocity',
            'Oxidizer Mass Flux': 'Oxidizer Mass Flux',
            'Oxidizer/Fuel': 'Oxidizer/Fuel',
            'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT': 'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT',
            'PERFECT EXPANSION': 'PERFECT EXPANSION',
            'Parachute deploy': 'Parachute deploy',
            'Paraffin Wax': 'Paraffin Wax',
            'Parametric Analysis: Of Ratio Sweep': 'Parametric Analysis: Of Ratio Sweep',
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
            'T_wall inner': 'T_wall inner',
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
            'Throat station': 'Throat station',
            'Thrust': 'Thrust',
            'Thrust & Chamber Pressure vs Time': 'Thrust & Chamber Pressure vs Time',
            'Thrust (N)': 'Thrust (N)',
            'Thrust (design point, constant-thrust assumption)': 'Thrust (design point, constant-thrust assumption)',
            'Thrust Coefficient': 'Thrust Coefficient',
            'Thrust Coefficient vs Altitude': 'Thrust Coefficient vs Altitude',
            'Thrust [N]': 'Thrust [N]',
            'Thrust vs Altitude': 'Thrust vs Altitude',
            'Thrust vs Of Ratio': 'Thrust vs Of Ratio',
            'Time': 'Time',
            'Time (s)': 'Time (s)',
            'Time [s]': 'Time [s]',
            'Total Area': 'Total Area',
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
            'UZAYTEK Hybrid Rocket Motor - 3D CAD Design': 'UZAYTEK Hybrid Rocket Motor - 3D CAD Design',
            'UZAYTEK Hybrid Rocket Motor - Simplified View': 'UZAYTEK Hybrid Rocket Motor - Simplified View',
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
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'the model COMPUTES the recess from the inner jet diameter; see the value in the results',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array',
        },
        tr: {            '3D Hybrid Rocket Motor Visualization': 'Hibrit Roket Motoru 3B Görselleştirme',
            '3D Motor Assembly': '3B Motor Montajı',
            '3D Motor Visualization': '3B Motor Görselleştirmesi',
            '3D Performance Surface Analysis': '3B Performans Yüzeyi Analizi',
            '3D visualization unavailable': '3B görselleştirme kullanılamıyor',
            'ABS Plastic': 'ABS Plastiği',

            'Acceleration': 'İvme',
            'Acceleration (g)': 'İvme (g)',
            'Acceleration Profile': 'İvme Profili',
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
            'Combustion / Kinetic Efficiency': 'Yanma / Kinetik Verim',
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
            'Design Mode': 'Tasarım kipi',
            'Design flux at reference cooled wall (conv + radiation)': 'Referans soğutulmuş cidarda tasarım akısı (taşınım + ışınım)',
            'Design point (motor result)': 'Tasarım noktası (motor çıktısı)',
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
            'Feed System — Slosh, Pressurant & Water Hammer': 'Besleme Sistemi — Çalkantı, Basınçlandırıcı ve Su Koçu',
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
            'Frequency f1 (Hz)': 'Frekans f1 (Hz)',
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
            'Isp vs O/F (equilibrium sweep)': 'Isp - O/F (denge taraması)',
            'Landing': 'İniş',
            'Landing under parachute': 'Paraşütle iniş',
            'Launch': 'Kalkış',
            'Launch Azimuth (° from N)': 'Kalkış Azimutu (° kuzeyden)',
            'Launch Elevation (°)': 'Kalkış Yükseliş Açısı (°)',
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
            'Motor Outline': 'Motor Dış Hattı',
            'Motor Visualization (Simplified)': 'Motor Görselleştirmesi (Basitleştirilmiş)',
            'Mounting Holes': 'Bağlantı delikleri',
            'Multi-Port': 'Çok portlu',
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
            'Oxidizer Feed': 'Oksitleyici Beslemesi',
            'Oxidizer Injection Velocity': 'Oksitleyici Enjeksiyon Hızı',
            'Oxidizer Mass Flux': 'Oksitleyici kütle akısı',
            'Oxidizer/Fuel': 'Oksitleyici/Yakıt',
            'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT': 'PARAMETRİK 3B MODEL — GEOMETRİ ÇÖZÜCÜ ÇIKTISINDAN CANLI',
            'PERFECT EXPANSION': 'TAM GENİŞLEME',
            'Parachute deploy': 'Paraşüt açılışı',
            'Paraffin Wax': 'Parafin Mumu',
            'Parametric Analysis: Of Ratio Sweep': 'Parametrik Analiz: O/F Oranı Taraması',
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
            'Quasi-1D: Mach is uniform across each cross-section — the radial axis shows geometry only, no boundary layer is modeled.': 'Yarı-1B: Mach her kesitte türdeştir — radyal eksen yalnız geometriyi gösterir, sınır tabaka modellenmemiştir.',
            'Radial Position (mm)': 'Radyal Konum (mm)',
            'Radial distance': 'Eksenden uzaklık',
            'Radius (m)': 'Yarıçap (m)',
            'Radius (mm)': 'Yarıçap (mm)',
            'Rail Length (m)': 'Ray Uzunluğu (m)',
            'Range': 'Menzil',
            'Range (km)': 'Menzil (km)',
            'Real-Time Motor Performance Dashboard': 'Gerçek Zamanlı Motor Performans Panosu',
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
            'Safety Factor': 'Güvenlik Katsayısı',
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
            'Spray cone': 'Püskürtme konisi',
            'Spray cone (angle not reported)': 'Püskürtme konisi (açı bildirilmedi)',
            'Star': 'Yıldız',
            'Station': 'İstasyon',
            'Stress (MPa)': 'Gerilme (MPa)',
            'Stress Amplitude (MPa)': 'Gerilme Genliği (MPa)',
            'Structural Analysis Dashboard': 'Yapısal Analiz Panosu',
            'Structural Min SF': 'Yapısal asgari emniyet katsayısı',
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
            'T_wall inner': 'T_cidar iç',
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
            'Throat station': 'Boğaz istasyonu',
            'Thrust': 'İtki',
            'Thrust & Chamber Pressure vs Time': 'İtki ve Oda Basıncı - Zaman',
            'Thrust (N)': 'İtki (N)',
            'Thrust (design point, constant-thrust assumption)': 'İtki (tasarım noktası, sabit itki varsayımı)',
            'Thrust Coefficient': 'İtki katsayısı',
            'Thrust Coefficient vs Altitude': 'İtki Katsayısı - İrtifa',
            'Thrust [N]': 'İtki [N]',
            'Thrust vs Altitude': 'İtki - İrtifa',
            'Thrust vs Of Ratio': 'İtki - O/F Oranı',
            'Time': 'Zaman',
            'Time (s)': 'Zaman (s)',
            'Time [s]': 'Zaman [s]',
            'Total Area': 'Toplam alan',
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
            'UZAYTEK Hybrid Rocket Motor - 3D CAD Design': 'UZAYTEK Hibrit Roket Motoru - 3B CAD Tasarımı',
            'UZAYTEK Hybrid Rocket Motor - Simplified View': 'UZAYTEK Hibrit Roket Motoru - Basitleştirilmiş Görünüm',
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
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'model girintiyi iç jet çapından HESAPLAR; sonuçtaki değere bakınız',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'bu yol tek koaksiyel eleman boyutlandırır; çok elemanlı dizilim için Enjektör Tasarımı panelini kullanınız',
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
    var PATTERNS = [
        [/^Hole (\d+)$/, 'Delik $1'],
        [/^Ring (\d+), hole (\d+)$/, 'Halka $1, delik $2'],
        [/^Injection Holes \((\d+)\)$/, 'Enjeksiyon delikleri ($1)'],
        [/^(\d+) Holes x dia (.+)$/, '$1 delik x çap $2'],
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
        [/^Grain = (.+)$/, 'Yakıt bloğu = $1'],
        /* Faz 6 / T43 (3 Ağustos 2026): sonek kuralı GENEL kuraldan ÖNCE
           gelmeli — applyPatterns ilk eşleşmeyi uygular. visualization.py:3527
           web tamamen tükendiğinde '(web fully consumed)' ekliyor; genel kural
           '(.+)' ile bu soneki de yutup İngilizce bırakıyordu (ölçüldü:
           'Son port Ø99.8 mm (web fully consumed)'). */
        [/^Final port (.+) \(web fully consumed\)$/, 'Son port $1 (web tamamen tükendi)'],
        [/^Final port (.+)$/, 'Son port $1'],
        [/^End-of-burn port: (.+)$/, 'Yanma sonu portu: $1'],
        [/^Regression Rate \(avg: (.+)\)$/, 'Regresyon hızı (ort: $1)'],
        [/^(.+) Regression Analysis$/, '$1 Regresyon Analizi'],
        [/^(.+) Injector - Front View$/, '$1 Enjektörü - Önden Görünüm', [1]],
        [/^Sensitivity Tornado —\s*(.*)$/, 'Duyarlılık Tornado Grafiği — $1'],
        [/^Limit reached —\s*(.*)$/, 'Sınıra ulaşıldı — $1'],
        [/^Service limit —\s*(.*)$/, 'Servis sınırı — $1'],
        [/^Maximum Altitude \((.+)\)$/, 'Azami irtifa ($1)'],
        [/^L<sub>chamber<\/sub> = (.+)$/, 'L<sub>oda</sub> = $1'],
        [/^L<sub>total<\/sub> = (.+)$/, 'L<sub>toplam</sub> = $1'],
        [/^(\d+) Holes$/, '$1 delik'],
        [/^Throat station$/, 'Boğaz istasyonu'],

        /* --- 2026-08-03, dinamik yüzey taraması ------------------------
           Aşağıdakiler tek koşuda ölçülerek bulundu: /calculate,
           /calculate_solid ve /calculate_liquid yanıtlarındaki figür
           metinleri toplanıp sözlükten geçirildi, çevrilmeden kalanlar
           buraya kural olarak yazıldı. Hepsi SAYI TAŞIYAN metinler, yani
           birebir sözlük girdisi olamazlar. */

        /* Nozul kontur açıları — visualization.py:3990. noz_type
           capitalize() ile geldiği için taban ad grup 1'de sözlükten
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

        /* Güvenlik katsayısı eşiği — visualization.py yapısal pano */
        [/^Min SF: (.+)$/, 'En düşük GK: $1']
    ];

    /* Sunucu mesajı desenleri (uyarı / doğrulama / hata metinleri).
       Yakalanan gruplar (sayı, malzeme adı, birim) korunur. */
    var MSG_PATTERNS = [
        // Geçici-rejim (blowdown) kararlılık uyarıları — dinamik değerli
        [/^t=(.+)s: ΔP\/Pc=(.+) < (.+) — combustion instability limit, simulation stopped$/,
         't=$1 s: ΔP/Pc=$2 < $3 — yanma kararsızlığı sınırı, simülasyon durduruldu'],
        [/^t=(.+)s: ΔP\/Pc=(.+) < (.+) — chugging risk \(SP-8089\)$/,
         't=$1 s: ΔP/Pc=$2 < $3 — chugging riski (SP-8089)'],
        [/^(.+) value must be between (.+), given: (.+)$/,
         '$1 değeri $2 aralığında olmalı, girilen: $3', [1]],
        [/^(.+) must be positive, given: (.+)$/,
         '$1 pozitif olmalı, girilen: $2', [1]],
        [/^Unsupported oxidizer key ['"](.+)['"]\. Supported oxidizers: (.+)$/,
         'Desteklenmeyen oksitleyici anahtarı $1. Desteklenen oksitleyiciler: $2'],
        [/^UNSAFE: equilibrium wall temperature (\S+) K exceeds (\S+) service limit (\S+) K with the specified cooling — burn-through likely\. Required cooling load q=(.+) at the throat\.$/,
         'GÜVENSİZ: denge cidar sıcaklığı $1 K, belirtilen soğutmayla $2 malzemesinin $3 K servis sınırını aşıyor — cidar delinmesi olası. Boğazda gereken soğutma yükü q=$4.'],
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
        [/^WARNING: HTPB\/ClF3 is extremely hypergolic and dangerous!$/,
         'UYARI: HTPB/ClF3 aşırı hipergoliktir ve tehlikelidir.'],
        [/^Note: Cryogenic propellants require specialized handling equipment$/,
         'Not: Kriyojenik iticiler özel elleçleme ekipmanı gerektirir'],
        [/^Throat diameter \((.+)\) must be smaller than chamber diameter \((.+)\)$/,
         'Boğaz çapı ($1) oda çapından ($2) küçük olmalı'],
        [/^Exit diameter \((.+)\) must be larger than throat diameter \((.+)\)$/,
         'Çıkış çapı ($1) boğaz çapından ($2) büyük olmalı'],
        [/^Tank pressure \((.+)\) must be higher than chamber pressure \((.+)\)$/,
         'Tank basıncı ($1) oda basıncından ($2) yüksek olmalı'],
        [/^Total impulse \((.+)\) doesn['’]t match thrust×time \((.+)\)$/,
         'Toplam impuls ($1), itki×süre ile ($2) uyuşmuyor'],

        /* --- user_data_validation.py (ölçüm CSV'si içe aktarma) -------- */
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
        [/^CRITICAL: peak hot-wall temperature (\S+) K exceeds (.+) melting point (\S+) K — liner failure\.$/,
         'KRİTİK: tepe sıcak cidar sıcaklığı $1 K, $2 malzemesinin $3 K erime sıcaklığını aşıyor — astar hasarı.'],
        [/^Cavitation risk: Nurick cavitation number K_c = (\S+) < (\S+) \((.+)\)$/,
         'Kavitasyon riski: Nurick kavitasyon sayısı K_c = $1 < $2 ($3)'],
        [/^Target injection velocity \((.+)\) is not set by hole count: with Cd=(\S+) the achieved velocity is (.+)\. Reaching the target needs dP = (.+) \(currently (.+)\)\.$/,
         'Hedef püskürtme hızı ($1) delik sayısıyla belirlenmiyor: Cd=$2 ile ulaşılan hız $3. Hedefe ulaşmak için dP = $4 gerekir (şu an $5).'],

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
        [/^CAD generation failed: (.+)$/, 'CAD üretilemedi: $1'],
        [/^Trajectory plot could not be generated: (.+)$/,
         'Yörünge grafiği üretilemedi: $1']
    ];

    /* "Etiket: değer" ve "Taban (birim)" kalıplarında yalnız etiket/taban
       çevrilir. Ayrılabilecek metinlerin sonunda kalan birim sözcükleri. */
    var UNIT_WORDS = [
        [/(\d)\s+deg\b/g, '$1 derece'],
        [/(\d)\s+holes\b/g, '$1 delik'],
        /* 2026-08-03: sayı/sembol ağırlıklı olduğu için bütün hâlde
           sözlüğe de desene de girmeyen metinlerin İÇİNDEKİ sabit
           parçalar. Örnek (ölçüldü, /calculate yanıtı):
             '- eta_c* = 100.00% (theoretical equilibrium; no measured c*
              efficiency supplied) | eta_kin = 98.93% (engineering
              finite-rate correlation)'
           Burada çevrilecek olan yalnız parantez içleri; sayılar,
           semboller ve ayırıcılar olduğu gibi kalır. */
        [/\(theoretical equilibrium; no measured c\* efficiency supplied\)/g,
         '(kuramsal denge; ölçülmüş c* verimi verilmedi)'],
        [/\(engineering finite-rate correlation\)/g,
         '(mühendislik sonlu-hız bağıntısı)'],
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
        /* Sözlük i18n.js'e kaydedildiyse oradan da denenir: başka bir
           dosya aynı metni tanımlamış olabilir. */
        if (global.I18N && typeof global.I18N.has === 'function' &&
            global.I18N.lang === lang && global.I18N.has(text)) {
            return global.I18N.t(text, null);
        }
        return null;
    }

    function applyPatterns(text, rules, lang) {
        for (var i = 0; i < rules.length; i++) {
            var re = rules[i][0];
            var match = re.exec(text);
            if (!match) continue;

            var groups = rules[i][2];
            if (!groups || !groups.length) return text.replace(re, rules[i][1]);

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
                return (p === undefined || p === null) ? '' : p;
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

        /* "Taban 12.3" — sondaki sayı korunur */
        var numbered = /^(.+?)\s+([-+]?\d[\d.,]*\s*\S{0,6})$/.exec(text);
        if (numbered) {
            var head = lookup(normalize(numbered[1]), lang);
            if (head !== null) return head + ' ' + numbered[2];
        }

        return applyUnitWords(raw);
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

        /* <br> / <br /> ayırıcıları KORUNARAK parça parça çevrilir */
        var parts = body.split(/(<br\s*\/?>)/i);
        var out = '';
        for (var i = 0; i < parts.length; i++) {
            out += /^<br\s*\/?>$/i.test(parts[i]) ? parts[i]
                                                  : translateSegment(parts[i], lang);
        }
        return out + extra;
    }

    /* Sunucudan gelen uyarı / hata metni çevirisi. */
    function serverText(message) {
        if (Array.isArray(message)) return serverTexts(message);
        if (typeof message !== 'string' || !message) return message;
        var lang = currentLang();
        if (lang === 'en' || !DICT[lang]) return message;

        var text = normalize(message);
        var hit = lookup(text, lang);
        if (hit !== null) return hit;

        /* Desenler tek ve çift tırnağı birlikte kabul eder; metin ham
           hâliyle eşleştirilir ki çıktıda tırnak biçimi değişmesin. */
        hit = applyPatterns(text, MSG_PATTERNS, lang);
        if (hit !== null) return hit;

        hit = applyPatterns(text, PATTERNS, lang);
        if (hit !== null) return hit;

        return message;
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
