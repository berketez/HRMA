/* ====================================================================
   HRMA Transient Analysis Panel (yalnız hibrit sayfası)
   --------------------------------------------------------------------
   /api/transient-analysis'i UI'a bağlar: gerçek Pc(t)/F(t) eğrileri,
   regülatörlü veya N₂O blowdown besleme, SP-8089 kararlılık uyarıları.

   Kullanım (advanced.html):
     <script src="/static/js/transient_panel.js"></script>
     TransientPanel.init({ anchorId: 'trajectoryPanel' });

   Sonuç iki yere yayılır:
     1. window.currentResults.motor.transient  → .eng export'u gerçek
        itki eğrisini kullanır (openrocket_integration._generate_thrust_curve)
     2. window.TransientPanel.lastResult       → 6-DOF paneli thrust_curve
        zinciri + dijital ikiz (MotorViz3D) beslemesi
   ==================================================================== */

(function () {
    'use strict';

    let lastResult = null;

    // advanced.html form alanlarından motor parametrelerini topla
    // (calculate() payload'ıyla aynı ID'ler; yalnız transient'in ihtiyacı olanlar)
    function collectMotorParams() {
        const num = (id, d) => {
            const el = document.getElementById(id);
            const v = el ? parseFloat(el.value) : NaN;
            return isFinite(v) ? v : d;
        };
        const str = (id, d) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : d;
        };
        return {
            thrust: num('thrust', 1000),
            burn_time: num('burn_time', 10),
            of_ratio: num('of_ratio', 7.0),
            chamber_pressure: num('chamber_pressure', 20),
            atmospheric_pressure: num('ambient_pressure', 1.01325),
            l_star: num('l_star', 1.0),
            expansion_ratio: Math.max(0, num('expansion_ratio', 0)),
            nozzle_type: str('nozzle_type', 'conical'),
            regression_a: num('regression_a', 3.68e-5),
            regression_n: num('regression_n', 0.555),
            fuel_density: num('fuel_density', 920),
            chamber_diameter_input: num('chamber_diameter_input', 0),
            fuel_type: str('fuel_type', 'htpb'),
            oxidizer_type: str('oxidizer_type', 'n2o'),
        };
    }

    function panelHtml() {
        return `
        <div class="panel" id="transientPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▶ Transient Analysis — Pc(t) / F(t)</h2>
            <div class="chart-explanation">
                <strong>What this shows:</strong> Time-resolved chamber pressure and
                thrust from the quasi-steady internal-ballistics march
                (P<sub>c</sub> = ṁ·c*/C<sub>D</sub>A<sub>t</sub> re-solved each step with the
                instantaneous equilibrium c*). Blowdown mode couples a
                self-pressurizing N₂O tank with SP-8089 injector-stability margins.
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:12px 0;">
                <div class="form-group">
                    <label>Feed Mode</label>
                    <select id="tp_feed_mode">
                        <option value="regulated">Regulated (constant ṁ)</option>
                        <option value="blowdown">N₂O Blowdown (self-pressurizing)</option>
                    </select>
                </div>
                <div class="form-group" id="tp_tank_temp_group" style="display:none;">
                    <label>Tank Temperature (K)</label>
                    <input type="number" id="tp_tank_temp" value="293.15" step="0.5" min="245" max="305">
                </div>
                <div class="form-group" id="tp_fill_group" style="display:none;">
                    <label>Liquid Fill Fraction</label>
                    <input type="number" id="tp_fill" value="0.85" step="0.01" min="0.5" max="0.95">
                </div>
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="tp_run">Run Transient</button>
                </div>
            </div>
            <div id="tp_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="tp_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="tp_plot" class="plot-container" style="min-height:420px; display:none;"></div>
            <div id="tp_tank_plot" class="plot-container" style="min-height:360px; display:none;"></div>
        </div>`;
    }

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        return `<span style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    async function run() {
        const status = document.getElementById('tp_status');
        const badges = document.getElementById('tp_badges');
        const runBtn = document.getElementById('tp_run');
        runBtn.disabled = true;
        status.textContent = 'SOLVING TRANSIENT BALLISTICS…';
        badges.innerHTML = '';

        const payload = collectMotorParams();
        payload.feed_mode = document.getElementById('tp_feed_mode').value;
        payload.tank_temperature = parseFloat(document.getElementById('tp_tank_temp').value) || 293.15;
        payload.liquid_fill_fraction = parseFloat(document.getElementById('tp_fill').value) || 0.85;

        try {
            const resp = await fetch('/api/transient-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            lastResult = data;
            window.TransientPanel.lastResult = data;
            render(data);

            // .eng export'u gerçek eğriyi kullansın diye motor sonucuna enjekte et
            if (window.currentResults && window.currentResults.motor) {
                window.currentResults.motor.transient = {
                    time: data.transient.time,
                    thrust: data.transient.thrust,
                };
            }
            // Dijital ikiz koşuyorsa transient veriyi ilet (plume/HUD ∝ itki)
            if (window.MotorViz3D && MotorViz3D.get && MotorViz3D.get()) {
                try { MotorViz3D.setTransient(data.transient); } catch (e) { /* eski sürüm */ }
            }
            status.textContent = '';
        } catch (err) {
            status.textContent = 'HATA: ' + err.message;
        } finally {
            runBtn.disabled = false;
        }
    }

    function render(data) {
        const tr = data.transient;
        const dp = data.design_point || {};
        const badges = document.getElementById('tp_badges');

        const eventKind = {
            burn_time_reached: 'ok', web_exhausted: 'ok',
            oxidizer_depleted: 'info', injector_unstable: 'err',
            feed_pressure_lost: 'err', time_limit: 'warn',
        }[tr.end_event] || 'info';
        let html = badge('END: ' + tr.end_event.toUpperCase(), eventKind);
        html += badge(`BURN ${tr.burn_duration.toFixed(2)} s`, 'info');
        html += badge(`IMPULSE ${(tr.total_impulse / 1000).toFixed(1)} kN·s`, 'info');
        if (dp.total_impulse_design) {
            const ratio = 100 * tr.total_impulse / dp.total_impulse_design;
            html += badge(`vs DESIGN ${ratio.toFixed(0)}%`, ratio > 85 ? 'ok' : 'warn');
        }
        (tr.warnings || []).forEach(w => { html += badge(w, 'warn'); });
        badges.innerHTML = html;

        // F(t) + Pc(t) çift eksen (plotly_dark otomatik koyu temalar)
        const plotDiv = document.getElementById('tp_plot');
        plotDiv.style.display = 'block';
        Plotly.newPlot(plotDiv, [
            { x: tr.time, y: tr.thrust, name: 'Thrust [N]', mode: 'lines',
              line: { width: 3 } },
            { x: tr.time, y: tr.chamber_pressure.map(p => p / 1e5),
              name: 'Chamber Pressure [bar]', mode: 'lines', yaxis: 'y2',
              line: { width: 2, dash: 'dot' } },
        ], {
            title: 'Transient Thrust & Chamber Pressure',
            xaxis: { title: 'Time [s]' },
            yaxis: { title: 'Thrust [N]', rangemode: 'tozero' },
            yaxis2: { title: 'P_c [bar]', overlaying: 'y', side: 'right',
                      rangemode: 'tozero' },
            height: 420,
            legend: { orientation: 'h', y: 1.12 },
        }, { responsive: true, displaylogo: false });

        // Blowdown tank geçmişi
        const tankDiv = document.getElementById('tp_tank_plot');
        if (tr.feed_mode === 'blowdown' && tr.tank_pressure && tr.tank_pressure.length) {
            tankDiv.style.display = 'block';
            Plotly.newPlot(tankDiv, [
                { x: tr.time, y: tr.tank_pressure.map(p => p / 1e5),
                  name: 'Tank Pressure [bar]', mode: 'lines', line: { width: 3 } },
                { x: tr.time, y: tr.tank_temperature,
                  name: 'Tank Temperature [K]', mode: 'lines', yaxis: 'y2',
                  line: { width: 2, dash: 'dot' } },
            ], {
                title: 'N₂O Tank Blowdown History',
                xaxis: { title: 'Time [s]' },
                yaxis: { title: 'P_tank [bar]' },
                yaxis2: { title: 'T_tank [K]', overlaying: 'y', side: 'right' },
                height: 360,
                legend: { orientation: 'h', y: 1.14 },
            }, { responsive: true, displaylogo: false });
        } else {
            tankDiv.style.display = 'none';
        }
    }

    function init(opts) {
        opts = opts || {};
        const anchor = document.getElementById(opts.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }
        document.getElementById('tp_run').addEventListener('click', run);
        document.getElementById('tp_feed_mode').addEventListener('change', function () {
            const bd = this.value === 'blowdown';
            document.getElementById('tp_tank_temp_group').style.display = bd ? '' : 'none';
            document.getElementById('tp_fill_group').style.display = bd ? '' : 'none';
        });
    }

    window.TransientPanel = { init, run, lastResult: null,
        get result() { return lastResult; } };
})();
