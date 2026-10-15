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
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'the model COMPUTES the recess from the inner jet diameter; see the value in the results',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array',

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
            'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (see chamber_analysis.model_validity_limit_exceeded). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.': 'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (see chamber_analysis.model_validity_limit_exceeded). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.',
            'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.': 'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.',
            'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability': 'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.',
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
            'Design Mode': 'Tasarım modu',
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
            'Face pattern': 'Yüz deseni',
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
            'the model COMPUTES the recess from the inner jet diameter; see the value in the results': 'model girintiyi iç jet çapından HESAPLAR; sonuçtaki değere bakınız',
            'this path sizes a single coaxial element; use the Injector Design panel for a multi-element array': 'bu yol tek koaksiyel eleman boyutlandırır; çok elemanlı dizilim için Enjektör Tasarımı panelini kullanınız',

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
            'the choked pressure drop dP = F_L^2*(p1 - F_F*p_v) was NOT computed because critical_pressure_Pa was not supplied (the liquid critical pressure ratio factor F_F needs it). Cavitation and flashing WERE screened from the vapour pressure alone; only the choked limit is missing.': 'boğulmuş basınç düşümü dP = F_L^2*(p1 - F_F*p_v) HESAPLANMADI: critical_pressure_Pa verilmedi (sıvı kritik basınç oranı çarpanı F_F bunu ister). Kavitasyon ve ani buharlaşma yalnız buhar basıncından TARANDI; eksik olan yalnızca boğulma sınırıdır.',
            'the water-hammer coupling was NOT produced: wall_thickness_m is required, because the wave speed depends on the pipe wall elasticity.': 'su koçu bağlaması ÜRETİLMEDİ: wall_thickness_m zorunludur, çünkü dalga hızı boru cidarının esnekliğine bağlıdır.',
            'the water-hammer coupling was NOT produced: no fluid key was supplied, and no default fluid label is substituted. The wave speed needs a tabulated liquid bulk modulus; pass the propellant\'s own key (or bulk_modulus_Pa with a custom label) to get the coupling.': 'su koçu bağlaması ÜRETİLMEDİ: akışkan anahtarı verilmedi ve yerine varsayılan bir akışkan etiketi KONMAZ. Dalga hızı tablolanmış bir sıvı hacimsel modülü ister; bağlamayı almak için iticinin kendi anahtarını (ya da özel etiketle birlikte bulk_modulus_Pa) geçirin.',
            'the water-hammer coupling was NOT produced: the line budget leaves no usable pressure at the valve, which is where the surge originates. Fix the line sizing first (the valve was not sized either, for the same reason).': 'su koçu bağlaması ÜRETİLMEDİ: hat bütçesi, basınç dalgasının doğduğu yer olan vanada kullanılabilir basınç bırakmıyor. Önce hat boyutlandırmasını düzeltin (aynı sebeple vana da boyutlandırılmadı).',
            'the valve was NOT sized: the line budget leaves no usable inlet pressure at the valve. Fix the line sizing first.': 'vana BOYUTLANDIRILMADI: hat bütçesi vanada kullanılabilir bir giriş basıncı bırakmıyor. Önce hat boyutlandırmasını düzeltin.',
            'non-choked turbulent liquid flow: the full valve pressure drop is used in the sizing equation.': 'boğulmamış türbülanslı sıvı akışı: boyutlandırma denkleminde vananın TAM basınç düşümü kullanılır.',
            'choked/flashing service: the sizing equation is evaluated at the choked pressure drop dP = F_L^2*(p1 - F_F*p_v), because flow stops rising beyond it (IEC 60534-2-1).': 'boğulmuş/ani buharlaşmalı servis: boyutlandırma denklemi boğulmuş basınç düşümünde dP = F_L^2*(p1 - F_F*p_v) değerlendirilir, çünkü akış bunun ötesinde artmaz (IEC 60534-2-1).',
            'flashing service was detected from the vapour pressure, but the sizing equation could NOT be moved to the choked pressure drop because critical_pressure_Pa was not supplied. The Cv below is evaluated at the FULL valve pressure drop and is therefore a LOWER BOUND on the required capacity, not a verified non-choked sizing.': 'ani buharlaşmalı servis buhar basıncından saptandı, ancak boyutlandırma denklemi boğulmuş basınç düşümüne TAŞINAMADI: critical_pressure_Pa verilmedi. Aşağıdaki Cv, vananın TAM basınç düşümünde değerlendirilmiştir ve bu yüzden gereken kapasitenin bir ALT SINIRIDIR; doğrulanmış, boğulmamış bir boyutlandırma değildir.',
            'the flow regime was NOT verified: without critical_pressure_Pa the choked limit dP = F_L^2*(p1 - F_F*p_v) cannot be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'akış rejimi DOĞRULANMADI: critical_pressure_Pa olmadan boğulma sınırı dP = F_L^2*(p1 - F_F*p_v) değerlendirilemez, dolayısıyla bu boyutlandırmanın boğulmamış olduğu BİLİNMİYOR. Aşağıdaki Cv vananın tam basınç düşümünü kullanır ve vana boğulmuş çıkarsa gereken kapasitenin bir ALT SINIRIDIR.',
            'the flow regime was NOT verified: without vapor_pressure_Pa neither the cavitation index nor the choked limit can be evaluated, so this sizing is not known to be non-choked. The Cv below uses the full valve pressure drop and is a LOWER BOUND on the required capacity if the valve turns out to be choked.': 'akış rejimi DOĞRULANMADI: vapor_pressure_Pa olmadan ne kavitasyon indisi ne de boğulma sınırı değerlendirilebilir, dolayısıyla bu boyutlandırmanın boğulmamış olduğu BİLİNMİYOR. Aşağıdaki Cv vananın tam basınç düşümünü kullanır ve vana boğulmuş çıkarsa gereken kapasitenin bir ALT SINIRIDIR.',
            'cavitation and flashing were NOT evaluated because vapor_pressure_Pa was not supplied. No safe/unsafe verdict is implied - supply the fluid properties to get one.': 'kavitasyon ve ani buharlaşma DEĞERLENDİRİLMEDİ: vapor_pressure_Pa verilmedi. Buradan güvenli/güvensiz bir hüküm çıkarılamaz — hüküm için akışkan özelliklerini verin.',
            'A solid motor has no injector and no feed system, so the classical chug criterion (injector pressure drop ratio decoupling the feed from the chamber) has no counterpart here. No injector input is passed to the module: its chug report is NOT_EVALUATED by construction, not because data is missing. The solid-motor low-frequency counterpart (L* / bulk-mode instability) is NOT modelled.': 'Katı motorda enjektör ve besleme sistemi yoktur; bu yüzden klasik chug ölçütünün (beslemeyi odadan ayıran enjektör basınç düşümü oranı) burada bir karşılığı yoktur. Modüle hiçbir enjektör girdisi geçirilmez: chug raporu, veri eksik olduğu için değil, KURULUŞ GEREĞİ NOT_EVALUATED\'dir. Katı motorun alçak frekanslı karşılığı (L* / yığın kip kararsızlığı) MODELLENMEMİŞTİR.',
            'No acceptance is issued: the wall was sized by HRMA to meet the target safety factor, so the reported safety factor is that target read back (target x manufacturing allowance), not an independent verification. Supply the real wall_thickness (m) to obtain a verification. A remaining MARGINAL/UNSAFE status is a warning and is never suppressed.': 'Onay VERİLMEZ: cidarı hedef emniyet katsayısını tutturmak için HRMA\'nın kendisi boyutlandırdı; dolayısıyla bildirilen emniyet katsayısı o hedefin geri okunmasıdır (hedef x imalat payı), bağımsız bir doğrulama değildir. Doğrulama için gerçek wall_thickness (m) değerini verin. Geriye kalan MARGINAL/UNSAFE durumu bir uyarıdır ve asla bastırılmaz.',
            'No acceptance is issued: no case thickness was supplied, so HRMA sized the wall itself from the hoop stress to meet the design safety factor. Checking that wall and reporting a pass is the design target read back, not an independent verification. Supply \'case_thickness\' (mm) to obtain one. A remaining MARGINAL/FAIL status is a warning and is never suppressed.': 'Onay VERİLMEZ: gövde cidar kalınlığı verilmedi, bu yüzden HRMA cidarı tasarım emniyet katsayısını tutturmak üzere çember gerilmesinden kendisi boyutlandırdı. O cidarı denetleyip \'geçti\' demek, tasarım hedefinin geri okunmasıdır; bağımsız bir doğrulama değildir. Doğrulama için \'case_thickness\' (mm) verin. Geriye kalan MARGINAL/FAIL durumu bir uyarıdır ve asla bastırılmaz.',
            'LOADED lift-off mass: dry mass + LOADED oxidizer (oxidizer_mass) + LOADED fuel grain (fuel_mass_loaded, which includes the unburnt sliver that flies as dead weight). The mass budget uses loaded values; the performance budget uses the consumed ones (fuel_mass, oxidizer_mass_consumed_kg) - same rule as oxidizer_mass_basis.': 'YÜKLÜ kalkış kütlesi: kuru kütle + YÜKLÜ oksitleyici (oxidizer_mass) + YÜKLÜ yakıt tanesi (fuel_mass_loaded; yanmadan ölü ağırlık olarak uçan artık dilim de içindedir). Kütle bütçesi yüklü değerleri, başarım bütçesi tüketilen değerleri (fuel_mass, oxidizer_mass_consumed_kg) kullanır — oxidizer_mass_basis ile aynı kural.',
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
            'solid grain burn-back solver (time-marched): burn area from grain regression, chamber pressure from the iterative pressure-burn rate fixed point (r = a*Pc^n)': 'katı yakıt bloğu geri yanma çözücüsü (zaman adımlı): yanma alanı blok gerilemesinden, oda basıncı yinelemeli basınç-yanma hızı sabit noktasından (r = a*Pc^n)',
            'the O/F-ratio extremes and the specific-impulse extremes': 'O/F oranının uç değerleri ve özgül itkinin uç değerleri',
            'the first samples of flow separation, of loss of choking and of burnout': 'akış ayrılmasının, boğulma kaybının ve yanma sonunun ilk örnekleri',
            'total impulse, burn time, average thrust, O/F shift statistics, warnings': 'toplam itki, yanma süresi, ortalama itki, O/F kayması istatistikleri, uyarılar',
            'time-averaged c*, time-averaged Isp, O/F shift statistics': 'zaman ortalamalı c*, zaman ortalamalı Isp, O/F kayması istatistikleri',
            'total impulse, average thrust, curve shape, stability, warnings': 'toplam itki, ortalama itki, eğri biçimi, kararlılık, uyarılar',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + nozzle. SCOPE LIMITS: the nozzle share is a 30%-of-chamber rule of thumb (see nozzle_weight_basis), and the injector is NOT included. The CAD mass breakdown (cad_design.performance_summary.mass_breakdown.total_dry_mass) is a DIFFERENT total: it uses the as-drawn nozzle and the injector but omits the closures, so the two do not agree.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: structural_analysis.weight_analysis.total_weight = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + nozul. KAPSAM SINIRLARI: nozul payı kamaranın %30\'u kadar alınan bir başparmak kuralıdır (bkz. nozzle_weight_basis) ve enjektör DAHİL DEĞİLDİR. CAD kütle dökümü (cad_design.performance_summary.mass_breakdown.total_dry_mass) FARKLI bir toplamdır: çizilen nozulu ve enjektörü kullanır ama uç kapaklarını dışarıda bırakır; bu yüzden ikisi birbirini tutmaz.',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: structural_analysis.weight_analysis.total_weight = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (cad_design.performance_summary.mass_breakdown.nozzle_mass ile aynı sayı). KAPSAM SINIRI: enjektör DAHİL DEĞİLDİR; CAD kütle dökümü toplamı (cad_design.performance_summary.mass_breakdown.total_dry_mass) enjektörü içerir ama uç kapaklarını dışarıda bırakır, bu yüzden iki toplam tam olarak bu iki kalem kadar farklıdır.',
            // V3 yapi-sf 2. tur: yapısal künyeler (karar §28-24 (C), Ş6) — TR.
            'TRUE means: a wall temperature used in this structural evaluation is at or above the melting point of the material, or above the last point of its strength-derating data. Above that point the strength is held at the last curve value (an upper bound, not a conservative value), and at or above melting the section has no load-carrying capacity at all. The strength, safety factors, wall thickness and masses computed from this evaluation are therefore outside the validity limit of the structural model: they are published as diagnostic numbers only, not as valid design outputs, and no acceptance and no numeric design verdict is issued. When the wall temperature comes from the heat-transfer module (wall_temperature_source = heat_transfer_module) it is a bare-wall steady-state estimate in which protection by the propellant grain, liner or insulation is not modelled, so an unreachable or failing result is a limit of the current model, not a statement that a real motor of this design is impossible.': 'TRUE şu demektir: bu yapısal değerlendirmede kullanılan bir cidar sıcaklığı malzemenin erime noktasında ya da üstünde, veya dayanım düşürme verisinin son noktasının üstündedir. O noktanın üstünde dayanım eğrinin son değerinde tutulur (bir üst sınırdır, muhafazakâr bir değer değildir); erime noktasında ya da üstünde kesitin hiç yük taşıma kapasitesi yoktur. Bu değerlendirmeden hesaplanan dayanım, emniyet katsayıları, cidar kalınlığı ve kütleler bu yüzden yapısal modelin geçerlilik sınırı dışındadır: geçerli tasarım çıktısı olarak değil, yalnız tanı amaçlı sayılar olarak yayımlanırlar; ne onay ne de sayısal tasarım hükmü verilir. Cidar sıcaklığı ısı transferi modülünden geldiğinde (wall_temperature_source = heat_transfer_module) bu, yakıt tanesi, astar ya da yalıtım korumasının modellenmediği çıplak cidar kararlı hâl tahminidir; bu yüzden ulaşılamaz ya da başarısız bir sonuç mevcut modelin sınırıdır, bu tasarımda gerçek bir motorun olanaksız olduğu anlamına gelmez.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: this safety factor was computed at a wall temperature outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). How the wall was chosen is stated in design_mode, sizing_feasible and sizing_infeasible_reason.': 'YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu emniyet katsayısı, yapısal modelin geçerlilik sınırı dışındaki bir cidar sıcaklığında hesaplandı (chamber_analysis.model_validity_limit_exceeded, model_validity_reasons). Cidarın nasıl seçildiği design_mode, sizing_feasible ve sizing_infeasible_reason alanlarında yazılıdır.',
            'DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind these masses comes from a structural evaluation outside the validity limit of the structural model (chamber_analysis.model_validity_limit_exceeded).': 'YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu kütlelerin arkasındaki kamara cidar kalınlığı, yapısal modelin geçerlilik sınırı dışındaki bir yapısal değerlendirmeden geliyor (chamber_analysis.model_validity_limit_exceeded).',
            'No acceptance and no numeric design verdict is issued: the chamber was evaluated outside the validity limit of the structural model (see chamber_analysis.model_validity_limit_exceeded). The safety factors in this response are diagnostic numbers. A remaining MARGINAL or UNSAFE status is a warning from the CURRENT model and is never suppressed, but it is not a statement that a real motor of this design is impossible.': 'Ne onay ne de sayısal tasarım hükmü verildi: hazne, yapısal modelin geçerlilik sınırı dışında değerlendirildi (bkz. chamber_analysis.model_validity_limit_exceeded). Bu yanıttaki emniyet katsayıları tanı amaçlı sayılardır. Kalan bir MARGINAL ya da UNSAFE durumu MEVCUT modelin uyarısıdır ve asla bastırılmaz; ama bu tasarımda gerçek bir motorun olanaksız olduğu anlamına gelmez.',
            'DRAWN SOLID (single source): the nozzle shell drawn by the CAD export - inner contour from nozzle_design.sample_nozzle_inner_contour, wall nozzle_geometry.wall_thickness added outward, density of the selected nozzle material (nozzle_material). The same number is cad_design.performance_summary.mass_breakdown.nozzle_mass and nozzle_geometry.estimated_mass. The former 30%-of-chamber rule of thumb is no longer used.': 'ÇİZİLEN KATI (tek kaynak): CAD dışa aktarımının çizdiği nozul kabuğu - iç kontur nozzle_design.sample_nozzle_inner_contour\'dan gelir, nozzle_geometry.wall_thickness cidarı dışa doğru eklenir, yoğunluk seçilen nozul malzemesinindir (nozzle_material). Aynı sayı cad_design.performance_summary.mass_breakdown.nozzle_mass ve nozzle_geometry.estimated_mass alanlarındadır. Eski "kamara kütlesinin %30\'u" başparmak kuralı artık kullanılmıyor.',
            'conical frustum annulus over the nozzle designer\'s OWN convergent cone (its own chamber radius, not this motor\'s chamber) and divergent section - a different geometry from the drawn nozzle, kept only for traceability': 'nozul tasarımcısının KENDİ yakınsak konisi (kendi kamara yarıçapı, bu motorun kamarası değil) ve ıraksak kesimi üzerinde kesik koni halkası - çizilen nozuldan farklı bir geometri, yalnız izlenebilirlik için tutuluyor',
            'AUTHORITATIVE dry mass for the flight chain (.eng, trajectory, T/W): structural_analysis.weight_analysis.total_weight = chamber shell (real wall thickness x material density) + end closures + the DRAWN nozzle (same number as cad_design.performance_summary.mass_breakdown.nozzle_mass). SCOPE LIMIT: the injector is NOT included; the CAD mass breakdown total (cad_design.performance_summary.mass_breakdown.total_dry_mass) includes the injector but omits the closures, so the two totals differ by exactly those two items. DIAGNOSTIC ONLY, NOT A VALID DESIGN OUTPUT: the chamber wall thickness behind this mass comes from a structural evaluation outside the validity limit of the structural model (structural_analysis.chamber_analysis.model_validity_limit_exceeded); the flight-chain numbers derived from it carry the same limit.': 'Uçuş zinciri (.eng, yörünge, T/W) için YETKİLİ kuru kütle: structural_analysis.weight_analysis.total_weight = kamara kabuğu (gerçek cidar kalınlığı x malzeme yoğunluğu) + uç kapakları + ÇİZİLEN nozul (cad_design.performance_summary.mass_breakdown.nozzle_mass ile aynı sayı). KAPSAM SINIRI: enjektör DAHİL DEĞİLDİR; CAD kütle dökümü toplamı (cad_design.performance_summary.mass_breakdown.total_dry_mass) enjektörü içerir ama uç kapaklarını dışarıda bırakır, bu yüzden iki toplam tam olarak bu iki kalem kadar farklıdır. YALNIZ TANI AMAÇLI, GEÇERLİ TASARIM ÇIKTISI DEĞİL: bu kütlenin arkasındaki kamara cidar kalınlığı, yapısal modelin geçerlilik sınırı dışındaki bir yapısal değerlendirmeden geliyor (structural_analysis.chamber_analysis.model_validity_limit_exceeded); ondan türeyen uçuş zinciri sayıları da aynı sınırı taşır.',
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
            'burn_time is validated but NOT used by the structural model: stresses and safety factors are steady-state at the design pressure, and the fatigue check counts PRESSURISATION CYCLES (design_cycles), which a burn duration does not set. No burn time was assumed on your behalf either - the field simply does not enter this analysis. Creep and other time-at-temperature effects are NOT modelled here (they would be the only route by which a burn duration could change these numbers).': 'burn_time doğrulanır ama yapısal model onu KULLANMAZ: gerilmeler ve emniyet katsayıları tasarım basıncında kararlı durum değerleridir; yorulma denetimi ise bir yanma süresinin belirlemediği BASINÇLANDIRMA ÇEVRİMLERİNİ (design_cycles) sayar. Sizin yerinize bir yanma süresi de varsayılmadı - alan bu analize hiç girmez. Sünme ve sıcaklıkta geçen süreye bağlı öteki etkiler burada MODELLENMEZ (yanma süresinin bu sayıları değiştirebileceği tek yol onlar olurdu).',
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

    /* V3 KK 2. tur (CFDS devri) — runtime_basis cümlesinin değişmeyen ilk
       cümlesinin TR karşılığı (iki desen de bunu kullanır; tek kopya). */
    var CFD_SURE_GOVDE_TR = 'solver_runtime_s kararlı çözücü sürücüsünün '
        + 'kendi süresi, runtime_s ise isteğin tamamıdır (doğrulama, ağ, '
        + 'çözüm, ayrılma, seyreltme).';

    var MSG_PATTERNS = [
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
        [/^TRUNCATED TAIL-OFF: the march stops the instant the liquid is exhausted, so no vapour step is integrated\. (.+?) kg of oxidiser is still in the tank; valued at the oxidiser-specific impulse of the last integrated step \(F\/mdot_ox\) that is worth (.+?) N\*s, (.+?) % of the impulse reported above\. It is NOT modelled here: the adiabatic vapour path would fall below the N2O triple point \(mass ratio (.+?)\) before the flow could stop at ambient pressure \(mass ratio (.+?)\), i\.e\. the tank tail-off model is out of envelope there\.$/,
         'KESİLMİŞ KUYRUK: yürüyüş sıvı tükendiği anda duruyor, bu yüzden hiçbir buhar adımı integre edilmiyor. Tankta hâlâ $1 kg oksitleyici var; son integre edilen adımın oksitleyiciye göre özgül itkisiyle (F/mdot_ox) değerlendirildiğinde bu $2 N*s eder, yukarıda bildirilen itkinin %$3 kadarı. Burada MODELLENMEMİŞTİR: adyabatik buhar yolu, akış ortam basıncında durabilmeden (kütle oranı $5) önce N2O üçlü noktasının (kütle oranı $4) altına düşerdi; yani tank kuyruk modeli orada zarfın dışındadır.'],
        [/^TRUNCATED TAIL-OFF: the march stops the instant the liquid is exhausted, so no vapour step is integrated\. (.+?) kg of oxidiser is still in the tank; valued at the oxidiser-specific impulse of the last integrated step \(F\/mdot_ox\) that is worth (.+?) N\*s, (.+?) % of the impulse reported above\. It is NOT modelled here \(the tail-off model is not integrated by this solver\)\.$/,
         'KESİLMİŞ KUYRUK: yürüyüş sıvı tükendiği anda duruyor, bu yüzden hiçbir buhar adımı integre edilmiyor. Tankta hâlâ $1 kg oksitleyici var; son integre edilen adımın oksitleyiciye göre özgül itkisiyle (F/mdot_ox) değerlendirildiğinde bu $2 N*s eder, yukarıda bildirilen itkinin %$3 kadarı. Burada MODELLENMEMİŞTİR (kuyruk modeli bu çözücü tarafından integre edilmiyor).'],
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
        [/^CRITICAL: peak hot-wall temperature (\S+) K exceeds (.+) melting point (\S+) K — liner failure\.$/,
         'KRİTİK: tepe sıcak cidar sıcaklığı $1 K, $2 malzemesinin $3 K erime sıcaklığını aşıyor — astar hasarı.'],
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
        [/^No acceptance is issued and no verdict is issued at all: every safety factor in this response \((.+?)\) is the design target read back - HRMA sized those sections to meet the target, so the number cannot fall below it and carries no information about a wall you built\. Supply the real wall \/ throat \/ head thickness to earn a verdict; the target itself is graded in design_target_assessment\.$/,
         'Ne onay ne de hüküm verildi: bu yanıttaki her emniyet katsayısı ($1) tasarım hedefinin geri okunmasıdır — HRMA o kesitleri hedefi sağlayacak biçimde boyutlandırdı, dolayısıyla sayı hedefin altına düşemez ve sizin ürettiğiniz bir cidar hakkında hiçbir bilgi taşımaz. Hüküm kazanmak için gerçek cidar / boğaz / kapak kalınlığını girin; hedefin kendisi design_target_assessment içinde derecelendirilir.'],
        [/^No acceptance is issued: the measured sections \((.+?)\) would pass, but (.+?) were sized by HRMA and therefore not verified\. An acceptance that does not cover every station is not an acceptance\. The measured-scope result is published separately in measured_scope_status\.$/,
         'Onay verilmedi: ölçülen kesitler ($1) geçerdi, ama $2 kesitlerini HRMA boyutlandırdı ve bu yüzden doğrulanmadılar. Her istasyonu kapsamayan bir onay, onay değildir. Ölçülen kapsamın sonucu measured_scope_status alanında ayrıca yayımlanır.'],
        [/^The verdict comes from verdict_safety_factor, the lowest safety factor actually measured on a drawn wall \((.+?)\)\. This is a measured warning and is never suppressed\. Sections not verified: (.+?); of those, (.+?) only read the design target back\.$/,
         'Hüküm verdict_safety_factor alanından geliyor: çizilmiş bir cidar üstünde gerçekten ölçülen en düşük emniyet katsayısı ($1). Bu ölçülmüş bir uyarıdır ve asla bastırılmaz. Doğrulanmayan kesitler: $2; bunlardan $3 yalnız tasarım hedefini geri okuyor.'],
        [/^Every station in the basket was evaluated against a user-supplied thickness \((.+?)\), so the verdict is an independent verification drawn from verdict_safety_factor\.$/,
         'Sepetteki her istasyon kullanıcının verdiği bir kalınlığa karşı değerlendirildi ($1), dolayısıyla hüküm verdict_safety_factor alanından çekilen bağımsız bir doğrulamadır.'],
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
        [/^Sweep maximum O\/F (\S+) is a grid node of a (\d+)-point sea-level-exit sweep; the canonical optimum O\/F is the solver value \(motor\.optimum_of_ratio\), searched continuously at the design expansion ratio, so the two differ\.$/,
         'Tarama azamisi O/F $1, $2 noktalı deniz seviyesi çıkışlı bir taramanın ızgara düğümüdür; kanonik optimum O/F çözücünün değeridir (motor.optimum_of_ratio) ve tasarım genişleme oranında sürekli aranır; bu yüzden ikisi farklıdır.'],
        [/^This run O\/F (\S+) is OUTSIDE the swept band (\S+)-(\S+); the curve does not cover the operating point\.$/,
         'Bu koşumun O/F değeri $1, taranan $2-$3 bandının DIŞINDA; eğri çalışma noktasını kapsamıyor.'],
        [/^Sweep maximum sits on the END of the swept band \(O\/F (\S+)\); it is the largest value IN THIS BAND, not a proven optimum - the true peak may lie outside\.$/,
         'Tarama azamisi taranan bandın UCUNDA duruyor (O/F $1); BU BANTTAKİ en büyük değerdir, kanıtlanmış bir optimum değildir - gerçek tepe bandın dışında olabilir.'],
        /* ÖH D37 · A1c panel-dil (K5 d) — A1b-3 panel-js OH-D37-G2 koşu
           noktası notu (visualization.py, panel-js dalı; raporundan birebir).
           Çıkış künyesi kodu MAKİNEDİR, aynen taşınır. Künyesiz üçüncü hâl
           sözlükte (DICT). */
        [/^This run point: the run O\/F solved with the exit anchored to ISA sea level and no nozzle expansion ratio \(exit basis (\S+)\) - the same exit anchor as the sweep curve; it is not the motor's delivered Isp at its nozzle expansion ratio\.$/,
         'Bu koşum noktası: koşumun O/F değeri, çıkışı ISA deniz seviyesine bağlanarak ve nozul genişleme oranı olmadan çözüldü (çıkış künyesi $1) - tarama eğrisiyle aynı çıkış çapası; motorun kendi nozul genişleme oranındaki teslim Isp değeri değildir.'],
        [/^This run point: the run O\/F solved with the exit at the supplied nozzle expansion ratio \(exit basis (\S+)\); the sweep curve is anchored to ISA sea level with no expansion ratio - a different thermochemistry path, so the point need not lie on the curve\.$/,
         'Bu koşum noktası: koşumun O/F değeri, çıkış verilen nozul genişleme oranında alınarak çözüldü (çıkış künyesi $1); tarama eğrisi genişleme oranı olmadan ISA deniz seviyesine bağlıdır - farklı bir termokimya yolu, bu yüzden noktanın eğrinin üzerinde olması gerekmez.'],

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
         'Karma köken: $1 için NASA CEA tür tablosu; $2 için molekül ağırlığı formülden türetildi']
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
    var HAT_ONEKLERI = {
        'fuel line': 'yakıt hattı',
        'oxidizer line': 'oksitleyici hattı'
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
