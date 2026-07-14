/* ====================================================================
   HRMA Analiz Güvertesi — Termal Güvenlik Paneli
   --------------------------------------------------------------------
   POST /analyze_thermal_safety sonucunu çizer:
   - h_g (Bartz), q_throat / q_chamber, cidar sıcaklıkları → sayısal kartlar
   - Soğutma değerlendirmesi (verim, öneriler, ısı yükü)
   - Plotly çubuk: sıcaklıklar tek seri (cyan), malzeme limitleri
     etiketli referans çizgileri (tema plotly_dark.js'ten gelir)
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

    // Test / hata ayıklama: saf render (dry-run)
    window.ThermalPanel = { _render: render };
})();
