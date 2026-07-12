/* ====================================================================
   HRMA 6-DOF Flight Dynamics Panel (advanced + solid + liquid — TEK kaynak)
   --------------------------------------------------------------------
   /api/six-dof-analysis'i UI'a bağlar: Barrowman stabilite (CN_α, CP,
   statik marj), weathercock, apoje ve uçuş serileri.

   Kullanım:
     <script src="/static/js/sixdof_panel.js"></script>
     SixDofPanel.init({
         anchorId: '...',            // panelin ÖNÜNE ekleneceği element (ops.)
         thrustProvider: function () {
             // Sayfaya göre itki kaynağı döndürür:
             //   {thrust_curve: {time:[], thrust:[]}}  → gerçek eğri
             //   {thrust: N, burn_time: s}             → sabit itki
             //   null                                  → panel formundaki değerler
         },
         defaults: { dry_mass: 8, propellant_mass: 4 }   // ops.
     });
   ==================================================================== */

(function () {
    'use strict';

    let cfg = {};

    const FIELDS = [
        // [id, label, default, step, açıklama]
        ['sd_body_d', 'Body Ø (m)', 0.10, 0.005],
        ['sd_body_l', 'Body Length (m)', 2.0, 0.05],
        ['sd_nose_l', 'Nose Length (m)', 0.40, 0.01],
        ['sd_dry_m', 'Dry Mass (kg)', 8.0, 0.1],
        ['sd_prop_m', 'Propellant Mass (kg)', 4.0, 0.1],
        ['sd_fin_root', 'Fin Root Chord (m)', 0.20, 0.005],
        ['sd_fin_tip', 'Fin Tip Chord (m)', 0.10, 0.005],
        ['sd_fin_span', 'Fin Span (m)', 0.11, 0.005],
        ['sd_fin_sweep', 'Fin Sweep (m)', 0.08, 0.005],
        ['sd_cd0', 'Cd₀', 0.45, 0.01],
        ['sd_wind', 'Wind Speed (m/s)', 5.0, 0.5],
        ['sd_wind_dir', 'Wind From (° from N)', 0.0, 5],
        ['sd_elev', 'Launch Elevation (°)', 90.0, 0.5],
        ['sd_rail', 'Rail Length (m)', 5.0, 0.5],
        ['sd_thrust', 'Thrust (N)', 1200.0, 50],
        ['sd_burn', 'Burn Time (s)', 6.0, 0.5],
    ];

    function fieldHtml([id, label, def, step]) {
        return `<div class="form-group">
            <label>${label}</label>
            <input type="number" id="${id}" value="${def}" step="${step}">
        </div>`;
    }

    function panelHtml(hasCurveSource) {
        const curveToggle = hasCurveSource ? `
            <div class="form-group" style="grid-column: 1 / -1;">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                    <input type="checkbox" id="sd_use_curve" checked style="width:auto;">
                    Use computed thrust curve (transient / motor solution) instead of constant thrust
                </label>
            </div>` : '';
        return `
        <div class="panel" id="sixDofPanel" style="width:100%;">
            <h2>▶ Flight Dynamics — 6-DOF Stability</h2>
            <div class="chart-explanation">
                <strong>What this shows:</strong> Rigid-body flight with quaternion
                attitude, Barrowman-derived CN<sub>α</sub>/CP (nose + fins, body
                interference), launch-rail constraint and wind-induced weathercocking.
                Linear small-α aerodynamics (α ≲ 15°) — use for <em>stability
                screening</em>, not tumbling flight.
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:10px; margin:12px 0;">
                ${FIELDS.map(fieldHtml).join('')}
                ${curveToggle}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="sd_run">Run 6-DOF</button>
                </div>
            </div>
            <div id="sd_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="sd_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="sd_plot_alt" class="plot-container" style="min-height:400px; display:none;"></div>
            <div id="sd_plot_alpha" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="sd_plot_track" class="plot-container" style="min-height:380px; display:none;"></div>
        </div>`;
    }

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)', warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)', info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        return `<span style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    function num(id) { return parseFloat(document.getElementById(id).value) || 0; }

    async function run() {
        const status = document.getElementById('sd_status');
        const badges = document.getElementById('sd_badges');
        const runBtn = document.getElementById('sd_run');
        runBtn.disabled = true;
        badges.innerHTML = '';
        status.textContent = 'INTEGRATING 6-DOF FLIGHT…';

        const payload = {
            body_diameter: num('sd_body_d'),
            body_length: num('sd_body_l'),
            nose_length: num('sd_nose_l'),
            nose_type: 'ogive',
            fin_count: 4,
            fin_root_chord: num('sd_fin_root'),
            fin_tip_chord: num('sd_fin_tip'),
            fin_span: num('sd_fin_span'),
            fin_sweep: num('sd_fin_sweep'),
            dry_mass: num('sd_dry_m'),
            propellant_mass: num('sd_prop_m'),
            cd0: num('sd_cd0'),
            wind_speed: num('sd_wind'),
            wind_direction_deg: num('sd_wind_dir'),
            launch_elevation_deg: num('sd_elev'),
            rail_length: num('sd_rail'),
        };

        // İtki kaynağı: sayfa sağlayıcısı (transient/solid eğrisi) veya form
        const useCurveEl = document.getElementById('sd_use_curve');
        let provided = null;
        if (cfg.thrustProvider && (!useCurveEl || useCurveEl.checked)) {
            try { provided = cfg.thrustProvider(); } catch (e) { provided = null; }
        }
        if (provided && provided.thrust_curve &&
            provided.thrust_curve.time && provided.thrust_curve.time.length > 3) {
            payload.thrust_curve = provided.thrust_curve;
        } else if (provided && provided.thrust && provided.burn_time) {
            payload.thrust = provided.thrust;
            payload.burn_time = provided.burn_time;
        } else {
            payload.thrust = num('sd_thrust');
            payload.burn_time = num('sd_burn');
        }

        try {
            const resp = await fetch('/api/six-dof-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            render(data, !!payload.thrust_curve);
            status.textContent = '';
        } catch (err) {
            status.textContent = 'HATA: ' + err.message;
        } finally {
            runBtn.disabled = false;
        }
    }

    function render(data, usedCurve) {
        const s = data.summary;
        const ser = data.series;
        const badges = document.getElementById('sd_badges');

        let html = badge(s.stable ? 'STABLE' : 'UNSTABLE', s.stable ? 'ok' : 'err');
        html += badge(`APOGEE ${(s.apogee / 1000).toFixed(2)} km @ ${s.apogee_time.toFixed(1)} s`, 'info');
        html += badge(`MAX MACH ${s.max_mach.toFixed(2)}`, 'info');
        html += badge(`MAX α ${s.max_alpha_deg.toFixed(1)}°`, s.max_alpha_deg < 10 ? 'ok' : 'warn');
        html += badge(`MARGIN ${s.static_margin_full.toFixed(2)} / ${s.static_margin_empty.toFixed(2)} cal`,
            (s.static_margin_full > 1 && s.static_margin_empty > 1) ? 'ok' : 'err');
        html += badge(`CNα ${s.cn_alpha.toFixed(2)} · CP ${s.x_cp.toFixed(3)} m`, 'info');
        html += badge('THRUST: ' + (usedCurve ? 'COMPUTED CURVE' : 'CONSTANT'), 'info');
        if (s.end_reason && s.end_reason !== 'apogee') {
            html += badge('END: ' + s.end_reason.toUpperCase(), 'warn');
        }
        badges.innerHTML = html;

        const altDiv = document.getElementById('sd_plot_alt');
        altDiv.style.display = 'block';
        Plotly.newPlot(altDiv, [
            { x: ser.time, y: ser.altitude, name: 'Altitude [m]', mode: 'lines',
              line: { width: 3 } },
            { x: ser.time, y: ser.mach, name: 'Mach', mode: 'lines', yaxis: 'y2',
              line: { width: 2, dash: 'dot' } },
        ], {
            title: 'Altitude & Mach vs Time (launch → apogee)',
            xaxis: { title: 'Time [s]' },
            yaxis: { title: 'Altitude [m]', rangemode: 'tozero' },
            yaxis2: { title: 'Mach', overlaying: 'y', side: 'right', rangemode: 'tozero' },
            height: 400, legend: { orientation: 'h', y: 1.12 },
        }, { responsive: true, displaylogo: false });

        const alphaDiv = document.getElementById('sd_plot_alpha');
        alphaDiv.style.display = 'block';
        Plotly.newPlot(alphaDiv, [
            { x: ser.time, y: ser.alpha_deg, name: 'α [deg]', mode: 'lines',
              line: { width: 2 } },
        ], {
            title: 'Angle of Attack (weathercock response)',
            xaxis: { title: 'Time [s]' },
            yaxis: { title: 'α [deg]', rangemode: 'tozero' },
            height: 340,
        }, { responsive: true, displaylogo: false });

        const trackDiv = document.getElementById('sd_plot_track');
        trackDiv.style.display = 'block';
        Plotly.newPlot(trackDiv, [
            { x: ser.east, y: ser.north, mode: 'lines+markers', name: 'Ground track',
              marker: { size: 3 } },
            { x: [ser.east[0]], y: [ser.north[0]], mode: 'markers', name: 'Launch',
              marker: { size: 12, symbol: 'star' } },
        ], {
            title: 'Ground Track (North vs East) — drift into wind = weathercock',
            xaxis: { title: 'East [m]' },
            yaxis: { title: 'North [m]', scaleanchor: 'x', scaleratio: 1 },
            height: 380,
        }, { responsive: true, displaylogo: false });
    }

    function init(options) {
        cfg = options || {};
        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = panelHtml(!!cfg.thrustProvider);
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(panel);
        }
        // Sayfa varsayılanları (kütle vb.)
        Object.entries(cfg.defaults || {}).forEach(([k, v]) => {
            const map = { dry_mass: 'sd_dry_m', propellant_mass: 'sd_prop_m',
                          thrust: 'sd_thrust', burn_time: 'sd_burn' };
            const el = map[k] && document.getElementById(map[k]);
            if (el) el.value = v;
        });
        document.getElementById('sd_run').addEventListener('click', run);
    }

    window.SixDofPanel = { init, run };
})();
