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

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

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
            // DÜZELTME (2026-07-19): 'ambient_pressure' ID'li alan sayfada YOK;
            // gerçek alan advanced.html'deki #single_pressure (app.js de onu
            // okuyor). Eski hâlinde transient analiz kullanıcının irtifasını /
            // ölçtüğü basıncı görmüyor, sessizce 1.01325 bar'a düşüyordu.
            atmospheric_pressure: num('single_pressure', 1.01325),
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
            <h2>▶ <span data-i18n="transient.title">${T('transient.title',
                'Transient Analysis — Pc(t) / F(t)')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="transient.intro">${T('transient.intro',
                    'Time-resolved chamber pressure and thrust from the quasi-steady '
                    + 'internal-ballistics march (Pc = mdot·c*/CD·At re-solved each step '
                    + 'with the instantaneous equilibrium c*). Blowdown mode couples a '
                    + 'self-pressurizing N2O tank with SP-8089 injector-stability margins.')}</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:12px 0;">
                <div class="form-group">
                    <label data-i18n="transient.feedMode">${T('transient.feedMode', 'Feed Mode')}</label>
                    <select id="tp_feed_mode">
                        <option value="regulated" data-i18n="transient.feedRegulated">${
                            T('transient.feedRegulated', 'Regulated (constant mass flow)')}</option>
                        <option value="blowdown" data-i18n="transient.feedBlowdown">${
                            T('transient.feedBlowdown', 'N2O Blowdown (self-pressurizing)')}</option>
                    </select>
                </div>
                <div class="form-group" id="tp_tank_temp_group" style="display:none;">
                    <label data-i18n="transient.tankTemp">${T('transient.tankTemp',
                        'Tank Temperature (K)')}</label>
                    <input type="number" id="tp_tank_temp" value="293.15" step="0.5" min="245" max="305">
                </div>
                <div class="form-group" id="tp_fill_group" style="display:none;">
                    <label data-i18n="transient.fillFraction">${T('transient.fillFraction',
                        'Liquid Fill Fraction')}</label>
                    <input type="number" id="tp_fill" value="0.85" step="0.01" min="0.5" max="0.95">
                </div>
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="tp_run"
                        data-i18n="transient.btnRun">${T('transient.btnRun',
                        'Run Transient')}</button>
                </div>
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="tp_export" disabled
                            data-i18n-title="transient.exportTip"
                            title="${T('transient.exportTip',
                                'Download the time-resolved curves as an Excel workbook (CSV fallback)')}"
                            data-i18n="transient.btnExport">${T('transient.btnExport',
                            'Export Excel')}</button>
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
        status.textContent = T('transient.solving', 'SOLVING TRANSIENT BALLISTICS…');
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
            const expBtn = document.getElementById('tp_export');
            if (expBtn) expBtn.disabled = false;

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
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
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
        let html = badge(T('transient.badgeEnd', 'END') + ': '
            + tr.end_event.toUpperCase(), eventKind);
        html += badge(TF('transient.badgeBurn', { s: tr.burn_duration.toFixed(2) },
                         'BURN {s} s'), 'info');
        html += badge(TF('transient.badgeImpulse',
                         { v: (tr.total_impulse / 1000).toFixed(1) },
                         'IMPULSE {v} kN·s'), 'info');
        if (dp.total_impulse_design) {
            const ratio = 100 * tr.total_impulse / dp.total_impulse_design;
            html += badge(TF('transient.badgeVsDesign', { pct: ratio.toFixed(0) },
                             'vs DESIGN {pct}%'), ratio > 85 ? 'ok' : 'warn');
        }
        (tr.warnings || []).forEach(w => { html += badge(w, 'warn'); });
        badges.innerHTML = html;

        // F(t) + Pc(t) çift eksen (plotly_dark otomatik koyu temalar)
        // react: aynı div'e her koşuda / dil değişiminde tekrar çizilir;
        // newPlot'un tam yıkım+kurulumu yerine fark tabanlı güncelleme
        // (plotly 1.34+; ilk çizimde kendiliğinden newPlot'a düşer)
        const plotDiv = document.getElementById('tp_plot');
        plotDiv.style.display = 'block';
        Plotly.react(plotDiv, [
            { x: tr.time, y: tr.thrust, name: T('transient.sThrust', 'Thrust [N]'),
              mode: 'lines', line: { width: 3 } },
            { x: tr.time, y: tr.chamber_pressure.map(p => p / 1e5),
              name: T('transient.sPc', 'Chamber Pressure [bar]'), mode: 'lines', yaxis: 'y2',
              line: { width: 2, dash: 'dot' } },
        ], {
            title: T('transient.chartMain', 'Transient Thrust & Chamber Pressure'),
            xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
            yaxis: { title: T('transient.sThrust', 'Thrust [N]'), rangemode: 'tozero' },
            yaxis2: { title: 'P_c [bar]', overlaying: 'y', side: 'right',
                      rangemode: 'tozero' },
            height: 420,
            legend: { orientation: 'h', y: 1.12 },
        }, { responsive: true, displaylogo: false });

        // Blowdown tank geçmişi
        const tankDiv = document.getElementById('tp_tank_plot');
        if (tr.feed_mode === 'blowdown' && tr.tank_pressure && tr.tank_pressure.length) {
            tankDiv.style.display = 'block';
            // react: aynı div'e tekrar çizim (bkz. tp_plot notu)
            Plotly.react(tankDiv, [
                { x: tr.time, y: tr.tank_pressure.map(p => p / 1e5),
                  name: T('transient.sTankP', 'Tank Pressure [bar]'), mode: 'lines',
                  line: { width: 3 } },
                { x: tr.time, y: tr.tank_temperature,
                  name: T('transient.sTankT', 'Tank Temperature [K]'), mode: 'lines', yaxis: 'y2',
                  line: { width: 2, dash: 'dot' } },
            ], {
                title: T('transient.chartTank', 'N2O Tank Blowdown History'),
                xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
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
        const expBtn = document.getElementById('tp_export');
        if (expBtn) expBtn.addEventListener('click', exportCurves);
        document.getElementById('tp_feed_mode').addEventListener('change', function () {
            const bd = this.value === 'blowdown';
            document.getElementById('tp_tank_temp_group').style.display = bd ? '' : 'none';
            document.getElementById('tp_fill_group').style.display = bd ? '' : 'none';
        });
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        // Dil değişince rozetler/grafik başlıkları saklanan sonuçla yeniden basılır
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                if (lastResult) {
                    try { render(lastResult); } catch (e) { /* çizim yoksa sessiz */ }
                }
            });
        }
    }

    // Zaman-cozumlu egrileri Excel olarak indir (sunucu openpyxl ile uretir;
    // uretemezse CSV'ye duser). Berke istegi: transient sonuclari bilgisayara
    // inebilsin.
    async function exportCurves() {
        if (!lastResult || !lastResult.transient) return;
        const t = lastResult.transient;
        const headers = [T('transient.colTime', 'Time (s)'),
                         T('transient.colThrust', 'Thrust (N)'),
                         T('transient.colPc', 'Chamber pressure (bar)')];
        const cols = [t.time || [], t.thrust || [], t.chamber_pressure || []];
        if (t.of_ratio && t.of_ratio.length) {
            headers.push(T('transient.colOf', 'O/F ratio')); cols.push(t.of_ratio);
        }
        if (t.port_diameter && t.port_diameter.length) {
            headers.push(T('transient.colPort', 'Port diameter (mm)'));
            cols.push(t.port_diameter.map(function (v) { return v * 1000; }));
        }
        if (t.tank_pressure && t.tank_pressure.length) {
            headers.push(T('transient.colTankP', 'Tank pressure (bar)'));
            cols.push(t.tank_pressure);
        }
        if (t.tank_temperature && t.tank_temperature.length) {
            headers.push(T('transient.colTankT', 'Tank temperature (K)'));
            cols.push(t.tank_temperature);
        }
        const n = Math.max.apply(null, cols.map(function (c) { return c.length; }));
        const rows = [];
        for (let i = 0; i < n; i++) {
            rows.push(cols.map(function (c) {
                return (c[i] === undefined || c[i] === null) ? '' : c[i];
            }));
        }

        const motor = (window.currentResults && window.currentResults.motor) || {};
        const name = motor.motor_name || 'HRMA_Motor';
        const stamp = new Date().toISOString().split('T')[0];
        const fname = name + '_transient_' + stamp + '.xlsx';

        const download = function (blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            window.URL.revokeObjectURL(url); document.body.removeChild(a);
        };

        try {
            const resp = await fetch('/api/export-xlsx', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    filename: fname,
                    sheets: [{name: 'Transient', headers: headers, rows: rows}]
                })
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            download(await resp.blob(), fname);
        } catch (e) {
            console.warn('XLSX export unavailable, falling back to CSV:', e);
            const esc = function (v) {
                const x = (v === null || v === undefined) ? '' : String(v);
                // Formul enjeksiyonu (CWE-1236): elektronik tablolar '=' '+' '-' '@'
                // ve sekme/CR ile baslayan METNI formul/komut sayabilir. Sayi
                // gorunen degerlere (-5000, +3.2e4) DOKUNULMAZ, yoksa veri bozulur.
                var y = x;
                if (/^[=+\-@\t\r]/.test(y) && !(y !== '' && isFinite(Number(y)))) { y = "'" + y; }
                return /[",\n]/.test(y) ? '"' + y.replace(/"/g, '""') + '"' : y;
            };
            const lines = [headers.map(esc).join(',')];
            rows.forEach(function (r) { lines.push(r.map(esc).join(',')); });
            download(new Blob([lines.join('\n')], {type: 'text/csv;charset=utf-8;'}),
                     fname.replace(/\.xlsx$/, '.csv'));
        }
    }

    window.TransientPanel = { init, run, lastResult: null,
        get result() { return lastResult; } };
})();
