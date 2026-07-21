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
    var CAPTIONS = {
        'chartCap.performance_plots': 'Main performance dashboard: each tile shows one quantity over the burn (thrust, chamber pressure and type-specific values such as O/F ratio or regression rate). Steady, flat curves indicate stable operation; hover to read exact values with units.',
        'chartCap.solid_performance_plots': 'Solid motor performance dashboard: thrust, chamber pressure and burn characteristics over the burn. A rising Kn curve means a progressive burn, a falling one regressive.',
        'chartCap.liquid_performance_plots': 'Liquid engine performance dashboard: the main operating quantities of the selected design in one view. Hover any tile to read exact values with units.',
        'chartCap.motor_plot': 'Scaled cross-section of the motor: casing, propellant, chamber and nozzle with key dimensions. Use it to sanity-check proportions before CAD export or manufacturing.',
        'chartCap.injector_plot': 'Face and flow schematic of the selected injector type: orifice layout and the key dimensions that set atomization quality and pressure drop.',
        'chartCap.motor_3d_plot': 'Interactive 3D view of the motor geometry. Drag to rotate, scroll to zoom.',
        'chartCap.trajectory_plot': 'Flight prediction driven by this motor’s thrust curve: altitude vs range, altitude, velocity and acceleration over time, flight phases and a performance summary.',
        'chartCap.trajectory_plots': 'Flight prediction driven by this engine’s thrust curve: altitude vs range, altitude, velocity and acceleration over time, flight phases and a performance summary.',
        'chartCap.parametric_plot': 'Parameter sweep: one design input varies while the others stay fixed, showing its effect on Isp, thrust, mass and throat diameter. Read it for trends and trade-offs rather than absolute limits.',
        'chartCap.altitude_performance_plot': 'Nozzle performance vs altitude: as ambient pressure falls, specific impulse, thrust and thrust coefficient rise toward their vacuum values. The last tile shows the atmospheric pressure model used.',
        'chartCap.thrust_altitude_plot': 'Thrust, specific impulse and impulse efficiency along the climb: how much performance the nozzle gains or loses away from its design altitude.',
        'chartCap.mass_fractions_plot': 'Combustion product species (mass fractions) at the chamber, throat and exit stations. Shifts between stations show how the gas composition changes while expanding through the nozzle.',
        'chartCap.combustion_analysis_plot': 'Chamber equilibrium analysis from the thermochemical solver: product composition and flame temperature for the selected propellants and O/F ratio.',
        'chartCap.realtime_dashboard_plot': 'Dashboard summary of the burn: six gauges show instantaneous thrust, chamber pressure, mass flow, temperature, O/F and Isp; the bottom row tracks propellant mass, burn rate and port diameter over time.',
        'chartCap.thrust_plot': 'Thrust vs time for the solid motor, derived from grain geometry and burn rate. The curve shape (neutral, progressive or regressive) follows the evolution of the burning surface area.',
        'chartCap.pressure_plot': 'Chamber pressure vs time. The peak must stay below the casing’s allowable pressure with margin; the curve mirrors the thrust curve through the nozzle relation.',
        'chartCap.altitude_analysis_plot': 'Specific impulse and thrust vs altitude: performance climbs toward vacuum values as ambient pressure drops.',
        'chartCap.altitude_profile_plot': 'Nozzle behavior vs altitude: thrust coefficient, exit Mach number and efficiency, showing where the nozzle runs over- or under-expanded.',
        'chartCap.tp_plot': 'Time-resolved run: chamber pressure and thrust including ignition transient, steady phase and tail-off, instead of a single steady-state point.',
        'chartCap.tp_tank_plot': 'Tank conditions during blowdown: pressure and temperature fall as propellant is consumed, which drives the thrust decay above.',
        'chartCap.sd_plot_alt': '6-DOF flight: altitude and Mach number vs time. The Mach trace shows where the aerodynamic loading peaks.',
        'chartCap.sd_plot_alpha': 'Angle of attack vs time: how far the nose points away from the velocity vector. Small, quickly damped values indicate stable flight; sustained large values indicate weathercocking or instability.',
        'chartCap.sd_plot_track': 'Ground track: horizontal drift (north/east) caused by wind and thrust misalignment. Useful for range safety and recovery planning.',
        'chartCap.sd_plot_traj3d': '3D flight path colored by Mach number, with its ground projection below. Rotate to inspect drift and the apogee point.'
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
            var fallback = CAPTIONS['chartCap.' + el.id];
            if (!fallback) return;
            attach(el, 'chartCap.' + el.id, fallback);
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
    window.HRMA_CAPTIONS = { attach: attach };
})();
