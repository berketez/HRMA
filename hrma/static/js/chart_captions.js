/*
 * HRMA grafik açıklama katmanı (2026-07-21 isteği: "kullanıcının soru
 * işareti kalmasın").
 *
 * Ana grafiklerin altına, grafiğin NE GÖSTERDİĞİNİ ve NASIL OKUNACAĞINI
 * bir-iki cümleyle anlatan sönük bir açıklama satırı ekler. Metinler
 * i18n_common.js sözlüğünden gelir (chartCap.* anahtarları); buradaki
 * İngilizce metinler yalnız sözlük yüklenemezse görünen yedektir.
 *
 * Çalışma şekli: Plotly.newPlot / Plotly.react sarmalanır (plotly_dark.js
 * sarmalayıcısının ÜSTÜNE zincirlenir — bu dosya ondan SONRA yüklenmeli);
 * bilinen id'li bir konteynere çizim yapıldığında konteynerin hemen
 * altına data-i18n işaretli açıklama düğümü eklenir. i18n.js dil
 * değişiminde ve sözlük geç kaydında düğümü kendiliğinden yeniler.
 *
 * Panel JS'leri (dinamik div üretenler) için dışa açık API:
 *   window.HRMA_CAPTIONS.attach(el, 'chartCap.anahtar', 'EN yedek metin')
 */
(function () {
    'use strict';
    if (typeof Plotly === 'undefined' || Plotly.__hrmaCaptions) return;
    Plotly.__hrmaCaptions = true;

    // Konteyner id → İngilizce yedek metin. Sözlük anahtarı her zaman
    // 'chartCap.' + id'dir; asıl EN/TR metinler i18n_common.js'te yaşar.
    // ÖH D20 / P12aB3-11 — ÖLÇÜLDÜ (once.json): bu yedek metinlerin üçü
    // (chartCap.pressure_plot, .trajectory_plot, .trajectory_plots) sözlükteki
    // EN karşılığından YALNIZ tipografik kesme işareti (U+2019) yüzünden
    // ayrışıyordu; diğer 20 kalem birebir aynıydı. Yedekler artık sözlüğün
    // kullandığı ASCII kesme işaretini taşır — "aynı metin" tek biçimde.
    var CAPTIONS = {
        'chartCap.performance_plots': 'Main performance dashboard: each tile shows one quantity over the burn (thrust, chamber pressure and type-specific values such as O/F ratio or regression rate). Steady, flat curves indicate stable operation; hover to read exact values with units.',
        'chartCap.solid_performance_plots': 'Solid motor performance dashboard: thrust, chamber pressure and burn characteristics over the burn. A rising Kn curve means a progressive burn, a falling one regressive.',
        'chartCap.liquid_performance_plots': 'Liquid engine performance dashboard: the main operating quantities of the selected design in one view. Hover any tile to read exact values with units.',
        'chartCap.motor_plot': 'Scaled cross-section of the motor: casing, propellant, chamber and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
        // ÖH D17 / P12aB3-02: eski metin delik YERLEŞİMİNİN basınç düşümünü
        // ve atomizasyonu 'belirlediğini' söylüyordu. Ölçüm bunun tersini
        // veriyor: hole_pattern circular/hexagonal/square üç koşumda 26
        // sayısal alanın 0'ını değiştiriyor (pressure_drop_bar, hole_diameter,
        // n_holes, injection_velocity_m_s, reynolds_number, injection_area …
        // hepsi bit-aynı). Figürün KENDİ künyesi de zaten 'layout only, total
        // area unchanged' diyordu. Anahtar YENİDEN ADLANDIRILDI: eski
        // 'chartCap.injector_plot' TR karşılığı i18n_common.js'te yanlış
        // nedenselliği taşıyor ve i18n 'ilk kazanır' kuralıyla ezilemiyor;
        // düzeltilmiş metin i18n_shell.js'te yeni anahtarla yaşıyor.
        'chartCap.injectorFace': 'Face and flow schematic of the selected injector type: orifice layout, hole count and hole diameter. The face pattern is drawing only \u2014 changing it moves no computed number; pressure drop and atomization follow from hole diameter, hole count and mass flow.',
        'chartCap.motor_3d_plot': 'Interactive 3D view of the motor geometry. Drag to rotate, scroll to zoom.',
        'chartCap.trajectory_plot': 'Flight prediction driven by this motor\'s thrust curve: altitude vs range, altitude, velocity and acceleration over time, flight phases and a performance summary.',
        'chartCap.trajectory_plots': 'Flight prediction driven by this engine\'s thrust curve: altitude vs range, altitude, velocity and acceleration over time, flight phases and a performance summary.',
        'chartCap.parametric_plot': 'Parameter sweep: one design input varies while the others stay fixed, showing its effect on Isp, thrust, mass and throat diameter. Read it for trends and trade-offs rather than absolute limits.',
        'chartCap.altitude_performance_plot': 'Nozzle performance vs altitude: as ambient pressure falls, specific impulse, thrust and thrust coefficient rise toward their vacuum values. The last tile shows the atmospheric pressure model used.',
        'chartCap.thrust_altitude_plot': 'Thrust, specific impulse and impulse efficiency along the climb: how much performance the nozzle gains or loses away from its design altitude.',
        'chartCap.mass_fractions_plot': 'Combustion product species (mass fractions) at the chamber, throat and exit stations. Shifts between stations show how the gas composition changes while expanding through the nozzle.',
        'chartCap.combustion_analysis_plot': 'Chamber equilibrium analysis from the thermochemical solver: product composition and flame temperature for the selected propellants and O/F ratio.',
        'chartCap.realtime_dashboard_plot': 'Dashboard summary of the run: the six gauges are this design point, not a live reading. They are the solved thrust, chamber pressure, mass flow, temperature, O/F and Isp, and they do not change with time; only the bottom row is a time history, tracking propellant mass, burn rate and port diameter over the burn.',
        'chartCap.thrust_plot': 'Thrust vs time for the solid motor, derived from grain geometry and burn rate. The curve shape (neutral, progressive or regressive) follows the evolution of the burning surface area.',
        'chartCap.pressure_plot': 'Chamber pressure vs time. The peak must stay below the casing\'s allowable pressure with margin; the curve mirrors the thrust curve through the nozzle relation.',
        'chartCap.altitude_analysis_plot': 'Specific impulse and thrust vs altitude: performance climbs toward vacuum values as ambient pressure drops.',
        'chartCap.altitude_profile_plot': 'Nozzle behavior vs altitude: thrust coefficient, exit Mach number and efficiency, showing where the nozzle runs over- or under-expanded.',
        'chartCap.tp_plot': 'Time-resolved run on the solver\'s own time steps: thrust (top) and chamber pressure (bottom) on one shared time axis. The dashed line is the design burn time t_b; if the run stops earlier, its end event is marked where it stopped. No ignition transient or integrated tail-off is modelled: the curve starts at the first solved step.',
        'chartCap.tp_tank_plot': 'Tank conditions during blowdown: tank pressure (top) and temperature (bottom) fall as oxidizer is consumed, which drives the thrust decay above. Same time axis and markers as the chart above.',
        'chartCap.sd_plot_alt': '6-DOF flight: altitude and Mach number vs time. The Mach trace shows where the aerodynamic loading peaks.',
        'chartCap.sd_plot_alpha': 'Angle of attack vs time: how far the nose points away from the velocity vector. Small, quickly damped values indicate stable flight; sustained large values indicate weathercocking or instability.',
        'chartCap.sd_plot_track': 'Ground track: horizontal drift (north/east) caused by wind and thrust misalignment. Useful for range safety and recovery planning.',
        'chartCap.sd_plot_traj3d': '3D flight path colored by Mach number, with its ground projection below. Rotate to inspect drift and the apogee point.',
        // ÖH D17 / P12aB3-09: aşağıdaki 7 konteyner sabit id ile
        // Plotly.newPlot ediliyordu ama listede karşılığı yoktu, bu yüzden
        // maybeAttach onları sessizce atlıyordu. Aralarında iki Monte Carlo
        // histogramı (kaç örnek, hangi dağılım) ve imalata gidebilecek iki CAD
        // görünümü vardı — yani en çok açıklama isteyenler.
        'chartCap.solid_motor_kesit': 'Scaled cross-section of the solid motor: case, propellant grain, core port and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
        // ÖH D23 / P17B2-09: sıvı kesiti (liquid.html:1879) sabit id ile
        // çiziliyor ama defterde karşılığı YOKTU; maybeAttach onu sessizce
        // atlıyordu (D17 turu yalnız katı kardeşini yakalamıştı, canlı DOM
        // çaprazı bunu ekledi). Altyazısız kalan son kap buydu.
        'chartCap.liquid_motor_kesit': 'Scaled cross-section of the liquid engine: chamber, injector face, throat and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
        'chartCap.mc_hist_thrust': 'Monte Carlo thrust distribution: one bar per bin over the sampled runs, with the nominal design value marked. Width shows how sensitive thrust is to the input tolerances you entered \u2014 it is not a manufacturing guarantee.',
        'chartCap.mc_hist_isp': 'Monte Carlo sea-level specific impulse distribution over the sampled runs, with the nominal design value marked. Read the spread as the effect of the input tolerances, not as a measured scatter.',
        'chartCap.altitude_plot': 'Delivered specific impulse vs altitude: as ambient pressure falls, Isp rises toward its vacuum value. The curve uses the standard atmosphere, not local site conditions.',
        // ÖH D19 / P12aB3-09 (Fable-D17 ŞART): eski metin bu figürü
        // 'uçuş çözümünün önizlemesi' sayıyordu. Ürün öyle çalışmıyor:
        // advanced.html previewAltProfile() hiçbir çözücüye gitmez;
        // kullanıcının girdiği alt_start/alt_end/alt_points taraması
        // boyunca altitudeToPressure() = ISA 1976 ortam basıncını çizer.
        'chartCap.altitude_preview': 'Ambient pressure vs altitude over the sweep you entered (alt_start to alt_end, alt_points samples), computed from the built-in US Standard Atmosphere 1976 model. It is neither a flight profile nor a solver result \u2014 no number here comes from the engine solution.',
        'chartCap.cad_visualization': 'CAD view generated from the solved geometry. It is a drawing of the dimensions listed in the design table \u2014 tolerances, fillets and joints are not modelled and it is not a manufacturing drawing.',
        'chartCap.cad_3d_view': 'Interactive 3D CAD view of the solved motor geometry. Drag to rotate, scroll to zoom. Tolerances, fillets and joints are not modelled \u2014 it is not a manufacturing drawing.'
    };

    // Konteyner id -> sözlük anahtarı. Varsayılan 'chartCap.' + id'dir;
    // burada YALNIZ ayrılan eşlemeler durur (ÖH D17 / P12aB3-02).
    var CAPTION_KEYS = {
        injector_plot: 'chartCap.injectorFace'
    };

    var MARK = 'hrma-chart-caption';

    function attach(el, key, fallbackEn) {
        if (!el || !el.parentNode) return;
        var cap = null;
        var next = el.nextElementSibling;
        if (next && next.className === MARK && next.getAttribute('data-for') === (el.id || '')) {
            cap = next;              // aynı konteynere yeniden çizim — çoğaltma
        } else {
            cap = document.createElement('div');
            cap.className = MARK;
            cap.setAttribute('data-for', el.id || '');
            cap.style.cssText =
                'font-family:var(--hd-sans, sans-serif);font-size:12px;' +
                'line-height:1.55;color:var(--hd-ink-dim, #7d97a5);' +
                'margin:6px 2px 14px;padding-left:10px;max-width:980px;' +
                'border-left:2px solid var(--hd-line, rgba(0,229,255,0.14));';
            el.parentNode.insertBefore(cap, el.nextSibling);
        }
        cap.setAttribute('data-i18n', key);
        cap.textContent = fallbackEn || cap.textContent;
        // Yeni eklenen düğümü hemen aktif dile çevir (i18n hazırsa)
        if (window.I18N && window.I18N.apply) {
            try { window.I18N.apply(cap); } catch (e) { /* kozmetik */ }
        }
    }

    function maybeAttach(gd) {
        try {
            var el = (typeof gd === 'string') ? document.getElementById(gd) : gd;
            if (!el || !el.id) return;
            var key = CAPTION_KEYS[el.id] || ('chartCap.' + el.id);
            var fallback = CAPTIONS[key];
            if (!fallback) return;
            attach(el, key, fallback);
        } catch (e) { /* açıklama kozmetiktir, çizimi asla engellemez */ }
    }

    ['newPlot', 'react'].forEach(function (name) {
        var orig = Plotly[name];
        if (typeof orig !== 'function') return;
        Plotly[name] = function (gd) {
            var out = orig.apply(this, arguments);
            maybeAttach(gd);
            return out;
        };
    });

    // Panel JS'lerinin dinamik konteynerleri için dışa açık API (2. faz)
    // attachKnown: konteynerin KENDİ id'sinden anahtarı ve yedek metni
    // çözer (ÖH D19 / P12aB3-09 ŞART-2). Plotly'siz çizim yolları
    // (Three.js güvertesi) metni yeniden yazmak zorunda kalmaz — TEK KAYNAK.
    window.HRMA_CAPTIONS = { attach: attach, attachKnown: maybeAttach };
})();
