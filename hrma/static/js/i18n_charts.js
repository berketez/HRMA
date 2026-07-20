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
        en: {
            'Acceleration': 'Acceleration',
            'Acceleration (g)': 'Acceleration (g)',
            'Acceleration Profile': 'Acceleration Profile',
            'Advanced Performance — 3D Surface, Mach Contour, Heat Flux': 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
            'Altitude': 'Altitude',
            'Altitude & Mach vs Time (launch → apogee)': 'Altitude & Mach vs Time (launch → apogee)',
            'Altitude (km)': 'Altitude (km)',
            'Altitude [m]': 'Altitude [m]',
            'Altitude Performance Analysis': 'Altitude Performance Analysis',
            'Altitude vs Time': 'Altitude vs Time',
            'Angle': 'Angle',
            'Angle of Attack (weathercock response)': 'Angle of Attack (weathercock response)',
            'Apogee': 'Apogee',
            'Area': 'Area',
            'Atmospheric Pressure': 'Atmospheric Pressure',
            'Atmospheric Pressure vs Altitude': 'Atmospheric Pressure vs Altitude',
            'Average Values': 'Average Values',
            'Axial Heat Flux & Equilibrium Wall Temperature': 'Axial Heat Flux & Equilibrium Wall Temperature',
            'Axial Mach Number': 'Axial Mach Number',
            'Axial position (mm)': 'Axial position (mm)',
            'Axial position x (mm)': 'Axial position x (mm)',
            'Body Diameter (m)': 'Body Diameter (m)',
            'Body tube': 'Body tube',
            'Bolted Joint — Preload, Torque & Separation (Shigley)': 'Bolted Joint — Preload, Torque & Separation (Shigley)',
            'Burn Area': 'Burn Area',
            'Burn Area & Kn vs Time': 'Burn Area & Kn vs Time',
            'Burn Area (cm²)': 'Burn Area (cm²)',
            'Burn Rate': 'Burn Rate',
            'Burn Time (s)': 'Burn Time (s)',
            'Burnout': 'Burnout',
            'CG/CP UNKNOWN': 'CG/CP UNKNOWN',
            'Cd₀ (subsonic)': 'Cd₀ (subsonic)',
            'Center': 'Center',
            'Centerline': 'Centerline',
            'Chamber': 'Chamber',
            'Chamber Pressure': 'Chamber Pressure',
            'Chamber Pressure (bar)': 'Chamber Pressure (bar)',
            'Chamber Pressure [bar]': 'Chamber Pressure [bar]',
            'Chamber Wall': 'Chamber Wall',
            'Chamber diameter (mm)': 'Chamber diameter (mm)',
            'Chamber pressure (bar)': 'Chamber pressure (bar)',
            'Chamber wall': 'Chamber wall',
            'Chemical Equilibrium': 'Chemical Equilibrium',
            'Cold-wall T (coolant side)': 'Cold-wall T (coolant side)',
            'Combustion / Kinetic Efficiency': 'Combustion / Kinetic Efficiency',
            'Combustion Analysis Dashboard': 'Combustion Analysis Dashboard',
            'Combustion Efficiency': 'Combustion Efficiency',
            'Combustion Efficiency (%)': 'Combustion Efficiency (%)',
            'Comparative Analysis — Snapshot & Compare Configurations': 'Comparative Analysis — Snapshot & Compare Configurations',
            'Complete Trajectory Analysis': 'Complete Trajectory Analysis',
            'Component': 'Component',
            'Comprehensive Safety — Risk Assessment & Pressure Vessel': 'Comprehensive Safety — Risk Assessment & Pressure Vessel',
            'Coolant bulk T': 'Coolant bulk T',
            'Coolant pressure': 'Coolant pressure',
            'Coolant pressure (bar)': 'Coolant pressure (bar)',
            'Core P(x) [bar]': 'Core P(x) [bar]',
            'Core diameter (mm)': 'Core diameter (mm)',
            'Cross-Section View': 'Cross-Section View',
            'Depth from hot face (mm)': 'Depth from hot face (mm)',
            'Diameter': 'Diameter',
            'Dimensions': 'Dimensions',
            'Dry Mass (kg)': 'Dry Mass (kg)',
            'East [m]': 'East [m]',
            'Efficiency (%)': 'Efficiency (%)',
            'Equilibrium wall T': 'Equilibrium wall T',
            'Exit Orifice': 'Exit Orifice',
            'Experimental Correlation — Model vs Static-Fire Database': 'Experimental Correlation — Model vs Static-Fire Database',
            'Feed System — Slosh, Pressurant & Water Hammer': 'Feed System — Slosh, Pressurant & Water Hammer',
            'Feed System Pressure Budget': 'Feed System Pressure Budget',
            'Fill ratio h/R': 'Fill ratio h/R',
            'Fin Count': 'Fin Count',
            'Fin Root Chord (m)': 'Fin Root Chord (m)',
            'Fin Root LE from Nose (m)': 'Fin Root LE from Nose (m)',
            'Fin Span (m)': 'Fin Span (m)',
            'Fin Sweep (m)': 'Fin Sweep (m)',
            'Fin Tip Chord (m)': 'Fin Tip Chord (m)',
            'Final port': 'Final port',
            'Fins': 'Fins',
            'Flame Temperature Profile': 'Flame Temperature Profile',
            'Flight Path': 'Flight Path',
            'Flight Phases': 'Flight Phases',
            'Flow Annulus': 'Flow Annulus',
            'Flow Channel': 'Flow Channel',
            'Flow Direction': 'Flow Direction',
            'Frequency f1 (Hz)': 'Frequency f1 (Hz)',
            'Fuel Grain': 'Fuel Grain',
            'Fuel grain': 'Fuel grain',
            'Ground Track (North vs East) — drift into wind = weathercock': 'Ground Track (North vs East) — drift into wind = weathercock',
            'Ground track': 'Ground track',
            'HRMA prediction [N]': 'HRMA prediction [N]',
            'Head End': 'Head End',
            'Heat Flux & Coolant Pressure': 'Heat Flux & Coolant Pressure',
            'Heat flux': 'Heat flux',
            'Heat flux (MW/m²)': 'Heat flux (MW/m²)',
            'Heat flux q': 'Heat flux q',
            'Hot-Face Temperature History': 'Hot-Face Temperature History',
            'Hot-wall T (gas side)': 'Hot-wall T (gas side)',
            'Hybrid Rocket Performance Analysis': 'Hybrid Rocket Performance Analysis',
            'Impulse Efficiency': 'Impulse Efficiency',
            'Impulse Efficiency vs Altitude': 'Impulse Efficiency vs Altitude',
            'Included angle': 'Included angle',
            'Initial port': 'Initial port',
            'Injection Slot': 'Injection Slot',
            'Injector': 'Injector',
            'Injector Performance': 'Injector Performance',
            'Injector Plate': 'Injector Plate',
            'Injector plate': 'Injector plate',
            'Inner wall temperature (K)': 'Inner wall temperature (K)',
            'Landing': 'Landing',
            'Launch': 'Launch',
            'Launch Azimuth (° from N)': 'Launch Azimuth (° from N)',
            'Launch Elevation (°)': 'Launch Elevation (°)',
            'Length (m)': 'Length (m)',
            'Length (mm)': 'Length (mm)',
            'Like-on-like doublet': 'Like-on-like doublet',
            'Liner (insulation)': 'Liner (insulation)',
            'Liquid Rocket Performance Analysis': 'Liquid Rocket Performance Analysis',
            'Location': 'Location',
            'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY': 'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY',
            'Mach': 'Mach',
            'Mach number': 'Mach number',
            'Mass (kg)': 'Mass (kg)',
            'Mass Flow': 'Mass Flow',
            'Mass Flow Rate': 'Mass Flow Rate',
            'Mass Flow Rate (kg/s)': 'Mass Flow Rate (kg/s)',
            'Mass Flow Rates': 'Mass Flow Rates',
            'Mass Fraction': 'Mass Fraction',
            'Mass Fractions Through Nozzle': 'Mass Fractions Through Nozzle',
            'Mass flow': 'Mass flow',
            'Material': 'Material',
            'Maximum Altitude (km)': 'Maximum Altitude (km)',
            'Mole Fraction': 'Mole Fraction',
            'Motor (dry)': 'Motor (dry)',
            'Motor Burnout': 'Motor Burnout',
            'Mounting Holes': 'Mounting Holes',
            'NORMAL SHOCK IN NOZZLE': 'NORMAL SHOCK IN NOZZLE',
            'North [m]': 'North [m]',
            'Nose Length (m)': 'Nose Length (m)',
            'Nose Type': 'Nose Type',
            'Nose cone': 'Nose cone',
            'Nozzle': 'Nozzle',
            'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)': 'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)',
            'Nozzle Station': 'Nozzle Station',
            'N₂O Tank Blowdown History': 'N₂O Tank Blowdown History',
            'O/F Ratio': 'O/F Ratio',
            'O/F Ratio Optimization': 'O/F Ratio Optimization',
            'OVEREXPANDED': 'OVEREXPANDED',
            'OVERSTABLE': 'OVERSTABLE',
            'Of Ratio': 'Of Ratio',
            'Operating Point': 'Operating Point',
            'Orifices': 'Orifices',
            'Outer Body': 'Outer Body',
            'Oxidizer Mass Flux': 'Oxidizer Mass Flux',
            'Oxidizer/Fuel': 'Oxidizer/Fuel',
            'PERFECT EXPANSION': 'PERFECT EXPANSION',
            'Parametric Analysis: Of Ratio Sweep': 'Parametric Analysis: Of Ratio Sweep',
            'Performance Chart': 'Performance Chart',
            'Performance Summary': 'Performance Summary',
            'Port Diameter': 'Port Diameter',
            'Port Diameter (mm)': 'Port Diameter (mm)',
            'Port Diameter Growth': 'Port Diameter Growth',
            'Port diameter (mm)': 'Port diameter (mm)',
            'Port growth': 'Port growth',
            'Position': 'Position',
            'Position (m)': 'Position (m)',
            'Pressure': 'Pressure',
            'Pressure (bar)': 'Pressure (bar)',
            'Pressure Distribution': 'Pressure Distribution',
            'Pressure Drop': 'Pressure Drop',
            'Pressure Drop (bar)': 'Pressure Drop (bar)',
            'Pressure Vessel — Sizing, MAWP & Real Burst Pressure': 'Pressure Vessel — Sizing, MAWP & Real Burst Pressure',
            'Pressurant': 'Pressurant',
            'Propellant Mass': 'Propellant Mass',
            'Propellant Mass (kg)': 'Propellant Mass (kg)',
            'Propellant Mass Flow': 'Propellant Mass Flow',
            'Propellant Mass vs Of Ratio': 'Propellant Mass vs Of Ratio',
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
            'SEPARATED': 'SEPARATED',
            'SHOWERHEAD INJECTOR': 'SHOWERHEAD INJECTOR',
            'STABLE': 'STABLE',
            'STABLE (SLIGHTLY OVERSTABLE)': 'STABLE (SLIGHTLY OVERSTABLE)',
            'Sample count': 'Sample count',
            'Showerhead': 'Showerhead',
            'Showerhead Injector - Front View': 'Showerhead Injector - Front View',
            'Showerhead pattern': 'Showerhead pattern',
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
            'Structural Min SF': 'Structural Min SF',
            'Structural Safety — Pressure Vessel, Buckling, Fatigue': 'Structural Safety — Pressure Vessel, Buckling, Fatigue',
            'Support Arms': 'Support Arms',
            'Swirl Chamber': 'Swirl Chamber',
            'Swirl Pattern': 'Swirl Pattern',
            'Swirl Region': 'Swirl Region',
            'Tank Pressure [bar]': 'Tank Pressure [bar]',
            'Tank Temperature [K]': 'Tank Temperature [K]',
            'Temperature': 'Temperature',
            'Temperature (K)': 'Temperature (K)',
            'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled': 'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled',
            'Thermal Safety — Bartz Heat Transfer & Wall Temperatures': 'Thermal Safety — Bartz Heat Transfer & Wall Temperatures',
            'Thickness': 'Thickness',
            'Throat': 'Throat',
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
            'Total Impulse Analysis - Altitude Performance': 'Total Impulse Analysis - Altitude Performance',
            'Total Length (m)': 'Total Length (m)',
            'Total Velocity': 'Total Velocity',
            'Trajectory Profile': 'Trajectory Profile',
            'Transient': 'Transient',
            'Transient Thrust & Chamber Pressure': 'Transient Thrust & Chamber Pressure',
            'UNCHOKED': 'UNCHOKED',
            'UNDEREXPANDED': 'UNDEREXPANDED',
            'UNSTABLE / MARGINAL': 'UNSTABLE / MARGINAL',
            'UZAYTEK Hybrid Rocket Motor - 3D CAD Design': 'UZAYTEK Hybrid Rocket Motor - 3D CAD Design',
            'Uncertainty Quantification — Monte Carlo Confidence Bands': 'Uncertainty Quantification — Monte Carlo Confidence Bands',
            'User Data Validation — Static-Fire CSV vs HRMA Prediction': 'User Data Validation — Static-Fire CSV vs HRMA Prediction',
            'Velocity': 'Velocity',
            'Velocity (m/s)': 'Velocity (m/s)',
            'Velocity Profile': 'Velocity Profile',
            'Vertical Velocity': 'Vertical Velocity',
            'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis': 'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis',
            'Wall P(x) [bar]': 'Wall P(x) [bar]',
            'Wall Temperature Profile at End of Burn': 'Wall Temperature Profile at End of Burn',
            'Wall Temperatures vs Material Limits': 'Wall Temperatures vs Material Limits',
            'Wall temperature (K)': 'Wall temperature (K)',
            'Water Hammer': 'Water Hammer',
            'Wind From (° from N)': 'Wind From (° from N)',
            'Wind Speed (m/s)': 'Wind Speed (m/s)',
            'X Position (mm)': 'X Position (mm)',
            'Y Position (mm)': 'Y Position (mm)',
            'Your test data [N]': 'Your test data [N]',
            'α [deg]': 'α [deg]',
            'Burn rate coefficient': 'Burn rate coefficient',
            'Burn rate exponent': 'Burn rate exponent',
            'Grain length (mm)': 'Grain length (mm)',
            'aluminum': 'aluminum',
            'carbon fiber': 'carbon fiber',
            'stainless steel': 'stainless steel',
            'steel': 'steel',
            'titanium': 'titanium',
            '3D Hybrid Rocket Motor Visualization': '3D Hybrid Rocket Motor Visualization',
            '3D Motor Assembly': '3D Motor Assembly',
            'Cavitation risk detected': 'Cavitation risk detected',
            'Consider heat sink or thermal mass for short burns': 'Consider heat sink or thermal mass for short burns',
            'Consider higher strength material': 'Consider higher strength material',
            'Consider thermal barrier coating': 'Consider thermal barrier coating',
            'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.': 'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.',
            'Flash boiling risk detected': 'Flash boiling risk detected',
            'High heat load - consider regenerative cooling': 'High heat load - consider regenerative cooling',
            'Implement temperature monitoring': 'Implement temperature monitoring',
            'Improve cooling system': 'Improve cooling system',
            'Increase chamber wall thickness': 'Increase chamber wall thickness',
            'Increase wall thickness': 'Increase wall thickness',
            'Low pressure drop (<20% of chamber pressure)': 'Low pressure drop (<20% of chamber pressure)',
            'Monitor wall temperature during operation': 'Monitor wall temperature during operation',
            'Natural cooling insufficient - use forced cooling': 'Natural cooling insufficient - use forced cooling',
            'Note: Cryogenic propellants require specialized handling equipment': 'Note: Cryogenic propellants require specialized handling equipment',
            'Severe temperature derating (>30% yield loss): cool wall or change material': 'Severe temperature derating (>30% yield loss): cool wall or change material',
            'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis': 'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis',
            'Use high thermal conductivity materials': 'Use high thermal conductivity materials',
            'Use higher temperature material': 'Use higher temperature material',
            'Wall temperature approaches melting point': 'Wall temperature approaches melting point',
            'Wall temperature exceeds allowable limit': 'Wall temperature exceeds allowable limit',
            'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material': 'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material',
            'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!': 'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!'
        },
        tr: {
            'Acceleration': 'İvme',
            'Acceleration (g)': 'İvme (g)',
            'Acceleration Profile': 'İvme Profili',
            'Advanced Performance — 3D Surface, Mach Contour, Heat Flux': 'Gelişmiş Performans — 3B Yüzey, Mach Konturu, Isı Akısı',
            'Altitude': 'İrtifa',
            'Altitude & Mach vs Time (launch → apogee)': 'İrtifa ve Mach Sayısı - Zaman (kalkış → apoje)',
            'Altitude (km)': 'İrtifa (km)',
            'Altitude [m]': 'İrtifa [m]',
            'Altitude Performance Analysis': 'İrtifa Performans Analizi',
            'Altitude vs Time': 'İrtifa - Zaman',
            'Angle': 'Açı',
            'Angle of Attack (weathercock response)': 'Hücum Açısı (rüzgâra dönme tepkisi)',
            'Apogee': 'Apoje',
            'Area': 'Alan',
            'Atmospheric Pressure': 'Atmosfer Basıncı',
            'Atmospheric Pressure vs Altitude': 'Atmosfer Basıncı - İrtifa',
            'Average Values': 'Ortalama Değerler',
            'Axial Heat Flux & Equilibrium Wall Temperature': 'Eksenel Isı Akısı ve Denge Cidar Sıcaklığı',
            'Axial Mach Number': 'Eksenel Mach Sayısı',
            'Axial position (mm)': 'Eksenel konum (mm)',
            'Axial position x (mm)': 'Eksenel konum x (mm)',
            'Body Diameter (m)': 'Gövde Çapı (m)',
            'Body tube': 'Gövde tüpü',
            'Bolted Joint — Preload, Torque & Separation (Shigley)': 'Cıvatalı Bağlantı — Ön Yük, Tork ve Ayrılma (Shigley)',
            'Burn Area': 'Yanma alanı',
            'Burn Area & Kn vs Time': 'Yanma Alanı ve Kn - Zaman',
            'Burn Area (cm²)': 'Yanma alanı (cm²)',
            'Burn Rate': 'Yanma hızı',
            'Burn Time (s)': 'Yanma Süresi (s)',
            'Burnout': 'Yanma sonu',
            'CG/CP UNKNOWN': 'AĞIRLIK/BASINÇ MERKEZİ BİLİNMİYOR',
            'Cd₀ (subsonic)': 'Cd₀ (ses altı)',
            'Center': 'Merkez',
            'Centerline': 'Eksen çizgisi',
            'Chamber': 'Yanma odası',
            'Chamber Pressure': 'Oda basıncı',
            'Chamber Pressure (bar)': 'Oda basıncı (bar)',
            'Chamber Pressure [bar]': 'Oda basıncı [bar]',
            'Chamber Wall': 'Oda cidarı',
            'Chamber diameter (mm)': 'Oda çapı (mm)',
            'Chamber pressure (bar)': 'Oda basıncı (bar)',
            'Chamber wall': 'Oda cidarı',
            'Chemical Equilibrium': 'Kimyasal Denge',
            'Cold-wall T (coolant side)': 'Soğuk cidar sıcaklığı (soğutucu tarafı)',
            'Combustion / Kinetic Efficiency': 'Yanma / Kinetik Verim',
            'Combustion Analysis Dashboard': 'Yanma Analizi Panosu',
            'Combustion Efficiency': 'Yanma verimi',
            'Combustion Efficiency (%)': 'Yanma verimi (%)',
            'Comparative Analysis — Snapshot & Compare Configurations': 'Karşılaştırmalı Analiz — Anlık Görüntü ve Yapılandırma Karşılaştırma',
            'Complete Trajectory Analysis': 'Tam Yörünge Analizi',
            'Component': 'Bileşen',
            'Comprehensive Safety — Risk Assessment & Pressure Vessel': 'Kapsamlı Güvenlik — Risk Değerlendirmesi ve Basınçlı Kap',
            'Coolant bulk T': 'Soğutucu yığın sıcaklığı',
            'Coolant pressure': 'Soğutucu basıncı',
            'Coolant pressure (bar)': 'Soğutucu basıncı (bar)',
            'Core P(x) [bar]': 'Çekirdek P(x) [bar]',
            'Core diameter (mm)': 'Çekirdek çapı (mm)',
            'Cross-Section View': 'Kesit Görünümü',
            'Depth from hot face (mm)': 'Sıcak yüzeyden derinlik (mm)',
            'Diameter': 'Çap',
            'Dimensions': 'Ölçüler',
            'Dry Mass (kg)': 'Kuru Kütle (kg)',
            'East [m]': 'Doğu [m]',
            'Efficiency (%)': 'Verim (%)',
            'Equilibrium wall T': 'Denge cidar sıcaklığı',
            'Exit Orifice': 'Çıkış deliği',
            'Experimental Correlation — Model vs Static-Fire Database': 'Deneysel Korelasyon — Model ve Statik Ateşleme Veri Tabanı',
            'Feed System — Slosh, Pressurant & Water Hammer': 'Besleme Sistemi — Çalkantı, Basınçlandırıcı ve Su Koçu',
            'Feed System Pressure Budget': 'Besleme Sistemi Basınç Bütçesi',
            'Fill ratio h/R': 'Doluluk oranı h/R',
            'Fin Count': 'Kanatçık Sayısı',
            'Fin Root Chord (m)': 'Kanatçık Kök Veteri (m)',
            'Fin Root LE from Nose (m)': 'Kanatçık Kök Hücum Kenarının Burna Uzaklığı (m)',
            'Fin Span (m)': 'Kanatçık Açıklığı (m)',
            'Fin Sweep (m)': 'Kanatçık Ok Açıklığı (m)',
            'Fin Tip Chord (m)': 'Kanatçık Uç Veteri (m)',
            'Final port': 'Son port',
            'Fins': 'Kanatçıklar',
            'Flame Temperature Profile': 'Alev Sıcaklığı Profili',
            'Flight Path': 'Uçuş Yolu',
            'Flight Phases': 'Uçuş Aşamaları',
            'Flow Annulus': 'Akış halkası',
            'Flow Channel': 'Akış kanalı',
            'Flow Direction': 'Akış yönü',
            'Frequency f1 (Hz)': 'Frekans f1 (Hz)',
            'Fuel Grain': 'Yakıt bloğu',
            'Fuel grain': 'Yakıt bloğu',
            'Ground Track (North vs East) — drift into wind = weathercock': 'Yer İzi (Kuzey - Doğu) — rüzgâra sürüklenme = rüzgâra dönme',
            'Ground track': 'Yer izi',
            'HRMA prediction [N]': 'HRMA tahmini [N]',
            'Head End': 'Ön kapak',
            'Heat Flux & Coolant Pressure': 'Isı Akısı ve Soğutucu Basıncı',
            'Heat flux': 'Isı akısı',
            'Heat flux (MW/m²)': 'Isı akısı (MW/m²)',
            'Heat flux q': 'Isı akısı q',
            'Hot-Face Temperature History': 'Sıcak Yüzey Sıcaklık Geçmişi',
            'Hot-wall T (gas side)': 'Sıcak cidar sıcaklığı (gaz tarafı)',
            'Hybrid Rocket Performance Analysis': 'Hibrit Roket Performans Analizi',
            'Impulse Efficiency': 'İmpuls verimi',
            'Impulse Efficiency vs Altitude': 'İmpuls Verimi - İrtifa',
            'Included angle': 'Kesişme açısı',
            'Initial port': 'Başlangıç portu',
            'Injection Slot': 'Enjeksiyon yarığı',
            'Injector': 'Enjektör',
            'Injector Performance': 'Enjektör Performansı',
            'Injector Plate': 'Enjektör plakası',
            'Injector plate': 'Enjektör plakası',
            'Inner wall temperature (K)': 'İç cidar sıcaklığı (K)',
            'Landing': 'İniş',
            'Launch': 'Kalkış',
            'Launch Azimuth (° from N)': 'Kalkış Azimutu (° kuzeyden)',
            'Launch Elevation (°)': 'Kalkış Yükseliş Açısı (°)',
            'Length (m)': 'Uzunluk (m)',
            'Length (mm)': 'Uzunluk (mm)',
            'Like-on-like doublet': 'Benzer-benzere çift jet',
            'Liner (insulation)': 'Astar (yalıtım)',
            'Liquid Rocket Performance Analysis': 'Sıvı Yakıtlı Roket Performans Analizi',
            'Location': 'Konum',
            'MOTOR AXIAL CROSS-SECTION — SOLVER GEOMETRY': 'MOTOR EKSENEL KESİTİ — ÇÖZÜCÜ GEOMETRİSİ',
            'Mach': 'Mach sayısı',
            'Mach number': 'Mach sayısı',
            'Mass (kg)': 'Kütle (kg)',
            'Mass Flow': 'Kütle debisi',
            'Mass Flow Rate': 'Kütle debisi',
            'Mass Flow Rate (kg/s)': 'Kütle debisi (kg/s)',
            'Mass Flow Rates': 'Kütle Debileri',
            'Mass Fraction': 'Kütle oranı',
            'Mass Fractions Through Nozzle': 'Nozul Boyunca Kütle Oranları',
            'Mass flow': 'Kütle debisi',
            'Material': 'Malzeme',
            'Maximum Altitude (km)': 'Azami irtifa (km)',
            'Mole Fraction': 'Mol oranı',
            'Motor (dry)': 'Motor (kuru)',
            'Motor Burnout': 'Motor Yanma Sonu',
            'Mounting Holes': 'Bağlantı delikleri',
            'NORMAL SHOCK IN NOZZLE': 'NOZULDA NORMAL ŞOK',
            'North [m]': 'Kuzey [m]',
            'Nose Length (m)': 'Burun Uzunluğu (m)',
            'Nose Type': 'Burun Tipi',
            'Nose cone': 'Burun konisi',
            'Nozzle': 'Nozul',
            'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)': 'Nozul Akışı — Yarı-1B Sıkıştırılabilir (Rejim, P(x), M(x), CF)',
            'Nozzle Station': 'Nozul istasyonu',
            'N₂O Tank Blowdown History': 'N₂O Tankı Boşalma Geçmişi',
            'O/F Ratio': 'O/F oranı',
            'O/F Ratio Optimization': 'O/F Oranı Optimizasyonu',
            'OVEREXPANDED': 'AŞIRI GENİŞLEMİŞ',
            'OVERSTABLE': 'AŞIRI KARARLI',
            'Of Ratio': 'O/F oranı',
            'Operating Point': 'Çalışma Noktası',
            'Orifices': 'Delikler',
            'Outer Body': 'Dış gövde',
            'Oxidizer Mass Flux': 'Oksitleyici kütle akısı',
            'Oxidizer/Fuel': 'Oksitleyici/Yakıt',
            'PERFECT EXPANSION': 'TAM GENİŞLEME',
            'Parametric Analysis: Of Ratio Sweep': 'Parametrik Analiz: O/F Oranı Taraması',
            'Performance Chart': 'Performans Grafiği',
            'Performance Summary': 'Performans Özeti',
            'Port Diameter': 'Port çapı',
            'Port Diameter (mm)': 'Port çapı (mm)',
            'Port Diameter Growth': 'Port Çapı Büyümesi',
            'Port diameter (mm)': 'Port çapı (mm)',
            'Port growth': 'Port büyümesi',
            'Position': 'Konum',
            'Position (m)': 'Konum (m)',
            'Pressure': 'Basınç',
            'Pressure (bar)': 'Basınç (bar)',
            'Pressure Distribution': 'Basınç Dağılımı',
            'Pressure Drop': 'Basınç düşüşü',
            'Pressure Drop (bar)': 'Basınç düşüşü (bar)',
            'Pressure Vessel — Sizing, MAWP & Real Burst Pressure': 'Basınçlı Kap — Boyutlandırma, MAWP ve Gerçek Patlama Basıncı',
            'Pressurant': 'Basınçlandırıcı',
            'Propellant Mass': 'İtici kütlesi',
            'Propellant Mass (kg)': 'İtici Kütlesi (kg)',
            'Propellant Mass Flow': 'İtici kütle debisi',
            'Propellant Mass vs Of Ratio': 'İtici Kütlesi - O/F Oranı',
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
            'SEPARATED': 'AYRILMIŞ',
            'SHOWERHEAD INJECTOR': 'DUŞ BAŞLIKLI ENJEKTÖR',
            'STABLE': 'KARARLI',
            'STABLE (SLIGHTLY OVERSTABLE)': 'KARARLI (HAFİF AŞIRI KARARLI)',
            'Sample count': 'Örnek sayısı',
            'Showerhead': 'Duş başlıklı',
            'Showerhead Injector - Front View': 'Duş Başlıklı Enjektör - Önden Görünüm',
            'Showerhead pattern': 'Duş başlığı deseni',
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
            'Structural Min SF': 'Yapısal asgari emniyet katsayısı',
            'Structural Safety — Pressure Vessel, Buckling, Fatigue': 'Yapısal Güvenlik — Basınçlı Kap, Burkulma, Yorulma',
            'Support Arms': 'Destek kolları',
            'Swirl Chamber': 'Girdap odası',
            'Swirl Pattern': 'Girdap deseni',
            'Swirl Region': 'Girdap bölgesi',
            'Tank Pressure [bar]': 'Tank basıncı [bar]',
            'Tank Temperature [K]': 'Tank sıcaklığı [K]',
            'Temperature': 'Sıcaklık',
            'Temperature (K)': 'Sıcaklık (K)',
            'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled': 'Termal Koruma — Ablatif / Isı Emici / Işınımla Soğutmalı',
            'Thermal Safety — Bartz Heat Transfer & Wall Temperatures': 'Termal Güvenlik — Bartz Isı Transferi ve Cidar Sıcaklıkları',
            'Thickness': 'Kalınlık',
            'Throat': 'Boğaz',
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
            'Total Impulse Analysis - Altitude Performance': 'Toplam İmpuls Analizi - İrtifa Performansı',
            'Total Length (m)': 'Toplam Uzunluk (m)',
            'Total Velocity': 'Toplam Hız',
            'Trajectory Profile': 'Yörünge Profili',
            'Transient': 'Zaman çözümlü',
            'Transient Thrust & Chamber Pressure': 'Zaman Çözümlü İtki ve Oda Basıncı',
            'UNCHOKED': 'BOĞULMAMIŞ AKIŞ',
            'UNDEREXPANDED': 'EKSİK GENİŞLEMİŞ',
            'UNSTABLE / MARGINAL': 'KARARSIZ / SINIRDA',
            'UZAYTEK Hybrid Rocket Motor - 3D CAD Design': 'UZAYTEK Hibrit Roket Motoru - 3B CAD Tasarımı',
            'Uncertainty Quantification — Monte Carlo Confidence Bands': 'Belirsizlik Niceleme — Monte Carlo Güven Bantları',
            'User Data Validation — Static-Fire CSV vs HRMA Prediction': 'Kullanıcı Verisi Doğrulama — Statik Ateşleme CSV ve HRMA Tahmini',
            'Velocity': 'Hız',
            'Velocity (m/s)': 'Hız (m/s)',
            'Velocity Profile': 'Hız Profili',
            'Vertical Velocity': 'Düşey hız',
            'Wall & Coolant Temperatures Along the Chamber–Nozzle Axis': 'Oda–Nozul Ekseni Boyunca Cidar ve Soğutucu Sıcaklıkları',
            'Wall P(x) [bar]': 'Cidar P(x) [bar]',
            'Wall Temperature Profile at End of Burn': 'Yanma Sonunda Cidar Sıcaklık Profili',
            'Wall Temperatures vs Material Limits': 'Cidar Sıcaklıkları - Malzeme Sınırları',
            'Wall temperature (K)': 'Cidar sıcaklığı (K)',
            'Water Hammer': 'Su koçu',
            'Wind From (° from N)': 'Rüzgâr Yönü (° kuzeyden)',
            'Wind Speed (m/s)': 'Rüzgâr Hızı (m/s)',
            'X Position (mm)': 'X konumu (mm)',
            'Y Position (mm)': 'Y konumu (mm)',
            'Your test data [N]': 'Test verileriniz [N]',
            'α [deg]': 'α [derece]',
            'Burn rate coefficient': 'Yanma hızı katsayısı',
            'Burn rate exponent': 'Yanma hızı üsteli',
            'Grain length (mm)': 'Yakıt bloğu uzunluğu (mm)',
            'aluminum': 'alüminyum',
            'carbon fiber': 'karbon fiber',
            'stainless steel': 'paslanmaz çelik',
            'steel': 'çelik',
            'titanium': 'titanyum',
            '3D Hybrid Rocket Motor Visualization': 'Hibrit Roket Motoru 3B Görselleştirme',
            '3D Motor Assembly': '3B Motor Montajı',
            'Cavitation risk detected': 'Kavitasyon riski tespit edildi',
            'Consider heat sink or thermal mass for short burns': 'Kısa yanmalar için ısı emici veya termal kütle kullanmayı değerlendirin',
            'Consider higher strength material': 'Daha yüksek dayanımlı malzeme kullanmayı değerlendirin',
            'Consider thermal barrier coating': 'Termal bariyer kaplaması kullanmayı değerlendirin',
            'Equilibrium wall temperature pinned near the adiabatic-wall temperature: modelled cooling is grossly insufficient.': 'Denge cidar sıcaklığı adyabatik cidar sıcaklığına dayanmış durumda: modellenen soğutma açıkça yetersiz.',
            'Flash boiling risk detected': 'Ani kaynama riski tespit edildi',
            'High heat load - consider regenerative cooling': 'Yüksek ısı yükü - rejeneratif soğutmayı değerlendirin',
            'Implement temperature monitoring': 'Sıcaklık izlemesi uygulayın',
            'Improve cooling system': 'Soğutma sistemini iyileştirin',
            'Increase chamber wall thickness': 'Oda cidar kalınlığını artırın',
            'Increase wall thickness': 'Cidar kalınlığını artırın',
            'Low pressure drop (<20% of chamber pressure)': 'Düşük basınç düşüşü (oda basıncının %20 altında)',
            'Monitor wall temperature during operation': 'Çalışma sırasında cidar sıcaklığını izleyin',
            'Natural cooling insufficient - use forced cooling': 'Doğal soğutma yetersiz - zorlanmış soğutma kullanın',
            'Note: Cryogenic propellants require specialized handling equipment': 'Not: Kriyojenik iticiler özel taşıma ve kullanım ekipmanı gerektirir',
            'Severe temperature derating (>30% yield loss): cool wall or change material': 'Ağır sıcaklık kaybı (%30 üzeri akma dayanımı kaybı): cidarı soğutun veya malzemeyi değiştirin',
            'Thin-wall assumption invalid (t/r>=0.1): use thick-wall (Lame) analysis': 'İnce cidar varsayımı geçersiz (t/r>=0,1): kalın cidar (Lame) analizi kullanın',
            'Use high thermal conductivity materials': 'Yüksek ısı iletkenliğine sahip malzeme kullanın',
            'Use higher temperature material': 'Daha yüksek sıcaklığa dayanıklı malzeme kullanın',
            'Wall temperature approaches melting point': 'Cidar sıcaklığı erime noktasına yaklaşıyor',
            'Wall temperature exceeds allowable limit': 'Cidar sıcaklığı izin verilen sınırı aşıyor',
            'Wall temperature is within 15% of the material service limit: add cooling, insulate, or select a higher-temperature material': 'Cidar sıcaklığı malzemenin servis sınırına %15 kadar yaklaştı: soğutma ekleyin, yalıtın veya daha yüksek sıcaklığa dayanıklı malzeme seçin',
            'WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!': 'UYARI: HTPB/ClF3 son derece hipergolik ve tehlikelidir.'
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
        [/^Throat station$/, 'Boğaz istasyonu']
    ];

    /* Sunucu mesajı desenleri (uyarı / doğrulama / hata metinleri).
       Yakalanan gruplar (sayı, malzeme adı, birim) korunur. */
    var MSG_PATTERNS = [
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
         'Bilinmeyen boru malzemesi $1 — $2 değerine geri dönülüyor']
    ];

    /* "Etiket: değer" ve "Taban (birim)" kalıplarında yalnız etiket/taban
       çevrilir. Ayrılabilecek metinlerin sonunda kalan birim sözcükleri. */
    var UNIT_WORDS = [
        [/(\d)\s+deg\b/g, '$1 derece'],
        [/(\d)\s+holes\b/g, '$1 delik']
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
