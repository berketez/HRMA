/* ====================================================================
   HRMA Analiz Güvertesi — Termal Güvenlik Paneli
   --------------------------------------------------------------------
   POST /analyze_thermal_safety sonucunu çizer:
   - h_g (Bartz), q_throat / q_chamber, cidar sıcaklıkları → sayısal kartlar
   - Soğutma değerlendirmesi (verim, öneriler, ısı yükü)
   - Plotly çubuk: sıcaklıklar tek seri (cyan), malzeme limitleri
     etiketli referans çizgileri (tema plotly_dark.js'ten gelir)
   - Axial Profile bölümü: POST /api/analysis/wall-profile →
     {x_mm, area_ratio, mach, h_g, q_MW, T_wall_eq} dizileri;
     q(x) & T_wall(x) (ikincil eksen) + Mach(x) grafikleri.
     Endpoint henüz yoksa (404/501) panel kırılmaz, zarif mesaj basar.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;

    // Malzeme anahtarları heat_transfer_analysis.py self.materials ile birebir
    const MATERIALS = [
        ['steel', 'Steel (generic)'],
        ['steel_4130', 'Steel AISI 4130'],
        ['aluminum', 'Aluminum'],
        ['copper', 'Copper'],
        ['inconel', 'Inconel'],
        ['graphite', 'Graphite'],
        ['ablative', 'Ablative liner'],
    ];

    const COOLING = [
        ['natural', 'Natural (heat sink)'],
        ['forced', 'Forced convection'],
        ['regenerative', 'Regenerative'],
    ];

    function riskKind(level) {
        const t = String(level || '').toUpperCase();
        if (t === 'LOW') return 'ok';
        if (t === 'MEDIUM') return 'warn';
        if (t === 'HIGH' || t === 'CRITICAL') return 'err';
        return 'info';
    }

    function sfKind(sf) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        if (sf < 1.0) return 'err';
        if (sf < 2.0) return 'warn';   // heat_transfer_analysis.py uyarı eşiği
        return 'ok';
    }

    function temperaturePlot(root, ta) {
        if (typeof Plotly === 'undefined') return;
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const matp = ta.material_properties || {};

        const cats = [];
        const vals = [];
        function push(label, v) {
            if (typeof v === 'number' && Number.isFinite(v)) {
                cats.push(label);
                vals.push(v);
            }
        }
        push('Combustion gas', gsa.gas_temperature);
        push('Adiabatic wall', gsa.adiabatic_wall_temperature);
        push('Wall (inner)', wa.inner_temperature);
        push('Wall (outer)', wa.outer_temperature);
        if (!cats.length) return;

        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);

        // Limitler ayrı seri DEĞİL: etiketli referans çizgileri (status rengi
        // asla "series" olarak kullanılmaz; kimlik yalnız renkle taşınmaz)
        const shapes = [];
        const annotations = [];
        function limitLine(v, label, color) {
            if (typeof v !== 'number' || !Number.isFinite(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 1, y: v, xanchor: 'right', yanchor: 'bottom',
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 10, color: color },
            });
        }
        limitLine(matp.allowable_temperature, 'Allowable limit', '#ff8c33');
        limitLine(matp.melting_point, 'Melting point', '#ff5d73');

        Plotly.newPlot(div, [{
            x: cats, y: vals, type: 'bar',
            marker: { color: '#00e5ff', line: { width: 0 } },
            width: 0.55,
            hovertemplate: '%{x}: %{y:.0f} K<extra></extra>',
        }], {
            title: 'Wall Temperatures vs Material Limits',
            yaxis: { title: 'Temperature (K)', rangemode: 'tozero' },
            xaxis: { title: '' },
            shapes: shapes,
            annotations: annotations,
            height: 360,
            showlegend: false,
        }, { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Eksenel profil (Dalga 2): q(x), T_wall(x), Mach(x)
    // ------------------------------------------------------------------
    const WALL_PROFILE_ENDPOINT = '/api/analysis/wall-profile';

    // Dock buildPayload aynası: gövde formdan okunur; termal formda
    // olmayan nozul geometrisi son hesap sonucundan tamamlanır.
    function readAxialPayload() {
        const payload = {};
        const sec = document.getElementById('ad_sec_thermal');
        if (sec) {
            sec.querySelectorAll('[data-field]').forEach(function (el) {
                const key = el.getAttribute('data-field');
                if (el.tagName === 'SELECT') {
                    payload[key] = el.value;
                    return;
                }
                const v = parseFloat(el.value);
                if (Number.isFinite(v)) payload[key] = v;
            });
        }
        try {
            const m = (window.currentResults && window.currentResults.motor) || {};
            if (payload.throat_diameter == null && Number.isFinite(m.throat_diameter)) {
                payload.throat_diameter = m.throat_diameter;
            }
            if (payload.expansion_ratio == null && Number.isFinite(m.expansion_ratio)) {
                payload.expansion_ratio = m.expansion_ratio;
            }
        } catch (e) { /* sonuç yoksa backend varsayılanları kullanılır */ }
        return payload;
    }

    // Saf çizim: profil dizilerinden iki Plotly grafiği üretir.
    // En az bir grafik çizildiyse true döner (duman testi bunu kullanır).
    function renderAxialCharts(profile, host) {
        if (typeof Plotly === 'undefined') return false;
        const p = profile || {};
        const x = Array.isArray(p.x_mm) ? p.x_mm : [];
        if (!x.length) return false;
        const sameLen = function (arr) {
            return Array.isArray(arr) && arr.length === x.length;
        };
        let drew = false;

        // Boğaz konumu işareti (backend x_throat_mm veriyorsa)
        const throatX = (typeof p.x_throat_mm === 'number' && Number.isFinite(p.x_throat_mm))
            ? p.x_throat_mm : null;
        function throatShape() {
            if (throatX == null) return [];
            return [{
                type: 'line', yref: 'paper', x0: throatX, x1: throatX, y0: 0, y1: 1,
                line: { color: 'rgba(125, 151, 165, 0.55)', width: 1, dash: 'dot' },
            }];
        }
        function throatAnnotation() {
            if (throatX == null) return [];
            return [{
                x: throatX, yref: 'paper', y: 1, xanchor: 'left', yanchor: 'top',
                text: 'Throat', showarrow: false,
                font: { size: 10, color: '#7d97a5' },
            }];
        }

        // --- Grafik 1: q(x) sol eksen + T_wall(x) ikincil (sağ) eksen ---
        const traces1 = [];
        if (sameLen(p.q_MW)) {
            const qTrace = {
                x: x, y: p.q_MW, name: 'Heat flux q',
                type: 'scatter', mode: 'lines',
                line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²<extra></extra>',
            };
            if (sameLen(p.h_g)) {
                qTrace.customdata = p.h_g;
                qTrace.hovertemplate = 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²'
                    + '<br>h_g = %{customdata:.0f} W/m²·K<extra></extra>';
            }
            traces1.push(qTrace);
        }
        if (sameLen(p.T_wall_eq)) {
            traces1.push({
                x: x, y: p.T_wall_eq, name: 'Equilibrium wall T',
                type: 'scatter', mode: 'lines', yaxis: 'y2',
                line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall = %{y:.0f} K<extra></extra>',
            });
        }
        if (traces1.length) {
            const div1 = document.createElement('div');
            div1.style.marginTop = '10px';
            host.appendChild(div1);
            Plotly.newPlot(div1, traces1, {
                title: 'Axial Heat Flux & Equilibrium Wall Temperature',
                xaxis: { title: 'Axial position x (mm)' },
                yaxis: { title: 'Heat flux (MW/m²)', rangemode: 'tozero' },
                yaxis2: { title: 'Wall temperature (K)', overlaying: 'y',
                          side: 'right', showgrid: false },
                legend: { orientation: 'h' },
                shapes: throatShape(),
                annotations: throatAnnotation(),
                height: 380,
            }, { responsive: true, displaylogo: false });
            drew = true;
        }

        // --- Grafik 2: Mach(x), sonik referans çizgisiyle ---
        if (sameLen(p.mach)) {
            const machTrace = {
                x: x, y: p.mach, name: 'Mach',
                type: 'scatter', mode: 'lines',
                line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>M = %{y:.2f}<extra></extra>',
            };
            if (sameLen(p.area_ratio)) {
                machTrace.customdata = p.area_ratio;
                machTrace.hovertemplate = 'x = %{x:.1f} mm<br>M = %{y:.2f}'
                    + '<br>A/At = %{customdata:.2f}<extra></extra>';
            }
            const div2 = document.createElement('div');
            div2.style.marginTop = '10px';
            host.appendChild(div2);
            Plotly.newPlot(div2, [machTrace], {
                title: 'Axial Mach Number',
                xaxis: { title: 'Axial position x (mm)' },
                yaxis: { title: 'Mach number', rangemode: 'tozero' },
                shapes: [{
                    type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 1, y1: 1,
                    line: { color: 'rgba(255, 93, 115, 0.7)', width: 1, dash: 'dash' },
                }].concat(throatShape()),
                annotations: [{
                    xref: 'paper', x: 1, y: 1, xanchor: 'right', yanchor: 'bottom',
                    text: 'Sonic — M = 1', showarrow: false,
                    font: { size: 10, color: '#ff5d73' },
                }].concat(throatAnnotation()),
                height: 320,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
            drew = true;
        }
        return drew;
    }

    // Bölüm montajı: başlık + 'Compute Axial Profile' butonu + grafikler
    function mountAxialSection(root) {
        const sec = document.createElement('div');
        sec.innerHTML = U.sectionTitle('Axial Profile — Chamber to Nozzle Exit')
            + `<p style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5); margin:4px 0 8px;">
               Computes the axial distribution of heat flux, equilibrium wall
               temperature and Mach number along the chamber–nozzle axis
               (Bartz correlation with local area ratio).</p>`;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.id = 'ad_axial_thermal';
        btn.textContent = 'Compute Axial Profile';
        const status = document.createElement('div');
        status.style.cssText = 'font-family:var(--hd-mono); font-size:0.8rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0;';
        const charts = document.createElement('div');
        sec.appendChild(btn);
        sec.appendChild(status);
        sec.appendChild(charts);
        root.appendChild(sec);

        btn.addEventListener('click', async function () {
            btn.disabled = true;
            status.textContent = 'COMPUTING AXIAL PROFILE…';
            charts.innerHTML = '';
            try {
                const resp = await fetch(WALL_PROFILE_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(readAxialPayload()),
                });
                if (resp.status === 404 || resp.status === 501) {
                    // Backend ajanı endpoint'i paralel ekliyor — panel kırılmaz
                    status.textContent = 'Axial profile backend is updating — '
                        + 'please retry once the server has reloaded.';
                    return;
                }
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || data.status === 'error') {
                    throw new Error((data && data.error) || ('HTTP ' + resp.status));
                }
                // Diziler backend'de data.wall_profile altında (test_client ile
                // doğrulandı, 2026-07-14); kök ve data.profile da tolere edilir
                const profile = (data.wall_profile && data.wall_profile.x_mm)
                    ? data.wall_profile
                    : (data.profile && data.profile.x_mm) ? data.profile : data;
                if (!renderAxialCharts(profile, charts)) {
                    status.textContent = 'Unexpected response — no profile arrays found.';
                    return;
                }
                status.textContent = '';
            } catch (err) {
                status.textContent = 'ERROR: ' + err.message;
            } finally {
                btn.disabled = false;
            }
        });
    }

    function render(data, root) {
        const ta = data.thermal_analysis || {};
        const htc = ta.heat_transfer_coefficients || {};
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const cool = ta.cooling_analysis || {};
        const safe = ta.safety_analysis || {};
        const matp = ta.material_properties || {};
        const dpp = ta.design_parameters || {};

        // ---- Rozetler ----
        let badges = '';
        if (safe.risk_level) {
            badges += U.badge('THERMAL RISK: ' + safe.risk_level, riskKind(safe.risk_level));
        }
        badges += U.badge('COOLING: ' + String(dpp.cooling_type || '—').toUpperCase(), 'info',
            'Cooling efficiency ' + U.fmt(cool.cooling_efficiency, 2));
        if (htc.correlation) {
            badges += U.badge('MODEL: BARTZ', 'info', htc.correlation);
        }
        if (gsa.wall_temperature_unphysical) {
            badges += U.badge('WALL T UNPHYSICAL — cooling insufficient', 'err',
                'Predicted steady-state wall temperature exceeds physical limits; '
                + 'the wall would fail before reaching it. Improve cooling.');
        }

        // ---- Sayısal kartlar ----
        const tempKind = function (T) {
            if (typeof T !== 'number' || !Number.isFinite(T)) return 'dim';
            if (matp.melting_point != null && T >= matp.melting_point) return 'err';
            if (matp.allowable_temperature != null && T > matp.allowable_temperature) return 'warn';
            return 'ok';
        };
        const head = document.createElement('div');
        head.innerHTML = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`
            + `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard('h_g (gas side)', U.fmt(htc.gas_side, 0), 'W/m²·K', null,
                htc.correlation || '')
            + U.statCard('q_throat', U.fmt(gsa.throat_heat_flux / 1e6, 2), 'MW/m²')
            + U.statCard('q_chamber', U.fmt(gsa.chamber_heat_flux / 1e6, 2), 'MW/m²')
            + U.statCard('T_wall inner', U.fmt(wa.inner_temperature, 0), 'K',
                tempKind(wa.inner_temperature))
            + U.statCard('T_wall outer', U.fmt(wa.outer_temperature, 0), 'K',
                tempKind(wa.outer_temperature))
            + U.statCard('T_adiabatic wall', U.fmt(gsa.adiabatic_wall_temperature, 0), 'K')
            + '</div>';
        root.appendChild(head);

        // ---- Plotly çubuk ----
        temperaturePlot(root, ta);

        const tail = document.createElement('div');
        let thtml = U.sectionTitle('Heat Load & Cooling Assessment');
        thtml += U.kvTable([
            ['Total heat rate', U.fmt(cool.peak_heat_rate, 1) + ' kW'],
            ['Total heat energy (burn)', U.fmt(cool.total_heat_energy, 1) + ' MJ'],
            ['Cooling efficiency', U.fmt(cool.cooling_efficiency, 2)
                + ' (' + String(dpp.cooling_type || '—') + ')'],
            ['Required cooling area', U.fmt(cool.required_cooling_area, 2) + ' m²'],
            ['Heat sink mass (steel equiv.)', U.fmt(cool.heat_sink_mass, 1) + ' kg',
             'Steel heat-sink mass for a 200 K temperature rise'],
            ['Hot-gas surface area', U.fmt(gsa.surface_area, 3) + ' m²'],
        ]);

        thtml += U.sectionTitle('Thermal Safety Factors');
        const sfRow = function (label, v, note) {
            const c = U.kindColor(sfKind(v));
            return [label, `<span style="color:${c}; font-family:var(--hd-mono);">${U.fmt(v)}</span>`, note];
        };
        thtml += U.kvTable([
            sfRow('Melting safety factor', safe.melting_safety_factor,
                'Melting point / wall temperature'),
            sfRow('Temperature safety factor', safe.temperature_safety_factor,
                'Allowable temperature / wall temperature'),
            sfRow('Thermal stress safety factor', safe.stress_safety_factor),
            ['Thermal stress', U.fmt(safe.thermal_stress, 0) + ' MPa'],
            ['Material limits', U.fmt(matp.allowable_temperature, 0) + ' K allowable · '
                + U.fmt(matp.melting_point, 0) + ' K melting'],
            ['Wall thickness', U.fmt(dpp.wall_thickness, 1) + ' mm ('
                + (dpp.material || '—') + ')'],
        ]);

        const warns = [].concat(safe.warnings || [], gsa.warnings || []);
        thtml += U.listBlock('Warnings', warns, 'warn');
        const recs = [].concat(safe.recommendations || [], cool.recommendations || []);
        thtml += U.listBlock('Cooling Recommendations', recs, 'info');
        tail.innerHTML = thtml;
        root.appendChild(tail);

        // ---- Eksenel profil bölümü (ikinci buton + iki grafik) ----
        mountAxialSection(root);
    }

    window.AnalysisDock.register({
        id: 'thermal',
        title: 'Thermal Safety — Bartz Heat Transfer & Wall Temperatures',
        category: 'THERMAL',
        endpoint: '/analyze_thermal_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1],
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 10],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01],
            ['burn_time', 'Burn Time (s)', 10, 0.5],
            ['mdot_total', 'Total Mass Flow (kg/s)', 1.0, 0.05],
            ['wall_thickness', 'Wall Thickness (m)', 0.005, 0.001],
            ['material', 'Wall Material', 'steel', MATERIALS],
            ['cooling_type', 'Cooling Type', 'natural', COOLING],
        ],
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            return {
                chamber_pressure: m.chamber_pressure,
                chamber_temperature: m.chamber_temperature,
                chamber_diameter: m.chamber_diameter,
                chamber_length: m.chamber_length,
                burn_time: m.burn_time,
                mdot_total: m.mdot_total,
            };
        },
        render: render,
    });

    // Test / hata ayıklama: saf render (dry-run) + eksenel yardımcılar
    window.ThermalPanel = {
        _render: render,
        _renderAxialCharts: renderAxialCharts,
        _mountAxialSection: mountAxialSection,
        _readAxialPayload: readAxialPayload,
    };
})();
