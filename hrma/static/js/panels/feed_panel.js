/* ====================================================================
   HRMA Analiz Güvertesi — Besleme Sistemi Paneli (Dalga 4B)
   --------------------------------------------------------------------
   Kategori 'FEED SYSTEM' — üç sekmeli alt bölüm, her biri kendi formu,
   kendi Run butonu ve kendi kartları/grafikleriyle:

     • Slosh       POST /api/slosh-analysis     (liquid + hybrid)
                   NASA SP-106 / Dodge 2000 doğrusal çalkalanma; doluluk
                   eğrisi grafiği (f1 & slosh-kütle oranı vs h/R).
     • Pressurant  POST /api/pressurant-sizing  (liquid + hybrid)
                   Regüleli / blowdown gaz boyutlandırma (Sutton Böl. 6).
     • Water Ham.  POST /api/water-hammer        (liquid + hybrid + solid)
                   Joukowsky/Allievi geçici basınç; SAFE/UNSAFE rozeti +
                   önerilen kapanma süresi.

   Bu panel, güvertenin tek-endpoint/tek-form akışı yerine kendi sekmeli
   arayüzünü güverte bölüm kabuğuna (ad_root_feed) yerleştirir; kayıt sadece
   FEED SYSTEM kategori sekmesini ve motor-tipi kapısını üretmek içindir
   (flow_panel.js'in dock-elemanı bekleme desenini yansıtır).

   Motor-tipi kapısı: slosh + pressurant yalnız liquid/hybrid (katı motorda
   sıvı tank yok); water hammer her hatta olabildiği için üç tipte de görünür.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const PANEL_ID = 'feed';

    // ------------------------------------------------------------------
    // Sekme tanımları — her biri kendi endpoint'i, alanları, render'ı,
    // motor-tipi kapısı ve motor sonucundan öneri fonksiyonuyla.
    // ------------------------------------------------------------------
    const GASES = [['helium', 'Helium'], ['nitrogen', 'Nitrogen']];
    const PIPE_MATERIALS = [
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['steel_4130', 'Steel AISI 4130'],
        ['aluminum_6061', 'Aluminum 6061'],
        ['titanium_6al4v', 'Titanium 6Al-4V'],
    ];
    const WH_FLUIDS = [
        ['water', 'Water'], ['n2o', 'Nitrous oxide (N2O)'],
        ['rp1', 'RP-1 (kerosene)'], ['lox', 'Liquid oxygen'],
    ];
    const PRESS_MODES = [['regulated', 'Regulated'], ['blowdown', 'Blowdown']];

    // ---- Slosh render --------------------------------------------------
    function renderSlosh(data, root) {
        const s = (data && data.slosh) || {};
        const cards = '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard('SLOSH FREQ f1', U.fmt(s.f1_hz, 3), 'Hz', 'info',
                'Fundamental lateral slosh natural frequency (SP-106 Eq. 2.4)')
            + U.statCard('SLOSH MASS FRACTION', U.fmt(s.slosh_mass_ratio, 3), '', 'dim',
                'm1/m_liquid — fraction of liquid that participates in the fundamental mode')
            + U.statCard('SLOSH MASS', U.fmt(s.slosh_mass_kg, 1), 'kg',
                (s.slosh_mass_kg == null ? 'dim' : 'dim'),
                'Absolute fundamental slosh mass (needs density/mass)')
            + U.statCard('PENDULUM LENGTH', U.fmt(s.pendulum_length, 3), 'm', 'dim',
                'Equivalent-pendulum length of the slosh mass')
            + U.statCard('FILL RATIO h/R', U.fmt(s.fill_ratio, 2), '', 'dim', '')
            + '</div>';

        const head = document.createElement('div');
        head.innerHTML = cards;
        root.appendChild(head);

        // Doluluk eğrisi: f1(h/R) sol eksen + slosh-kütle oranı sağ eksen
        const sweep = s.fill_sweep || {};
        if (typeof Plotly !== 'undefined' && Array.isArray(sweep.fill_ratio)
            && sweep.fill_ratio.length) {
            const div = document.createElement('div');
            div.style.marginTop = '10px';
            root.appendChild(div);
            const traces = [];
            if (Array.isArray(sweep.f1_hz)) {
                traces.push({
                    x: sweep.fill_ratio, y: sweep.f1_hz, name: 'Slosh frequency f1',
                    type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 },
                    hovertemplate: 'h/R = %{x:.2f}<br>f1 = %{y:.3f} Hz<extra></extra>',
                });
            }
            if (Array.isArray(sweep.slosh_mass_ratio)) {
                traces.push({
                    x: sweep.fill_ratio, y: sweep.slosh_mass_ratio, name: 'Slosh mass fraction',
                    type: 'scatter', mode: 'lines', yaxis: 'y2',
                    line: { color: '#2dd4a8', width: 2, dash: 'dot' },
                    hovertemplate: 'h/R = %{x:.2f}<br>m1/m = %{y:.3f}<extra></extra>',
                });
            }
            // Mevcut doluluk seviyesi işareti
            const shapes = [];
            if (Number.isFinite(s.fill_ratio)) {
                shapes.push({
                    type: 'line', yref: 'paper', x0: s.fill_ratio, x1: s.fill_ratio,
                    y0: 0, y1: 1, line: { color: 'rgba(255,140,51,0.7)', width: 1.5, dash: 'dash' },
                });
            }
            Plotly.newPlot(div, traces, {
                title: 'Slosh Frequency & Mass Fraction vs Fill Level',
                xaxis: { title: 'Fill ratio h/R' },
                yaxis: { title: 'Frequency f1 (Hz)', rangemode: 'tozero' },
                yaxis2: { title: 'Slosh mass fraction', overlaying: 'y', side: 'right', showgrid: false },
                legend: { orientation: 'h' },
                shapes: shapes,
                height: 340,
            }, { responsive: true, displaylogo: false });
        }

        // Baffle sönümleme + uyarılar + model notu
        const baffle = s.baffle || {};
        const tail = document.createElement('div');
        let html = '';
        const rows = [];
        if (baffle.damping_ratio != null) {
            rows.push(['Ring-baffle damping ratio',
                U.fmt(baffle.damping_ratio, 4) + ' (band ' + U.fmt(baffle.damping_ratio_low, 4)
                + '–' + U.fmt(baffle.damping_ratio_high, 4) + ')',
                'Miles (1958) single flat ring baffle — approximate (factor ~2 band)']);
            rows.push(['Blocked-area ratio', U.fmt(baffle.blocked_area_ratio, 3)]);
        } else if (baffle.recommended_width_ratio != null) {
            rows.push(['Recommended baffle width w/R', U.fmt(baffle.recommended_width_ratio, 3),
                baffle.note || '']);
            rows.push(['Target damping ratio', U.fmt(baffle.target_damping_ratio, 4)]);
        }
        if (rows.length) {
            html += U.sectionTitle('Ring-Baffle Damping (Miles, approximate)') + U.kvTable(rows);
        }
        if (Array.isArray(s.coincidence_warnings) && s.coincidence_warnings.length) {
            html += U.listBlock('Frequency-coincidence warnings', s.coincidence_warnings, 'warn');
        }
        if (s.model_note) html += U.listBlock('Model assumptions & limits', [s.model_note], 'dim');
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    // ---- Pressurant render --------------------------------------------
    function renderPressurant(data, root) {
        const p = (data && data.pressurant) || {};
        const mode = (data && data.mode) || 'regulated';
        const head = document.createElement('div');
        let cards = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge('MODE: ' + mode.toUpperCase(), 'info')
            + U.badge('GAS: ' + String(p.gas || '—').toUpperCase(), 'dim')
            + '</div><div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">';
        if (mode === 'regulated') {
            const iso = p.isothermal || {};
            const adia = p.adiabatic || {};
            const st = p.storage || {};
            cards += U.statCard('DELIVERED GAS', U.fmt(p.recommended_delivered_mass_kg, 3), 'kg', 'info',
                'Recommended (conservative, adiabatic bound) pressurant mass')
                + U.statCard('ISOTHERMAL BOUND', U.fmt(iso.gas_mass_kg, 3), 'kg', 'dim',
                    'Slow (dense-gas) minimum mass')
                + U.statCard('ADIABATIC BOUND', U.fmt(adia.gas_mass_kg, 3), 'kg', 'dim',
                    'Fast (cold-gas) maximum mass')
                + U.statCard('BOTTLE VOLUME', U.fmt(st.bottle_water_volume_m3 * 1000, 1), 'L', 'dim',
                    'Required storage bottle water volume')
                + U.statCard('BOTTLE COUNT', U.fmt(st.bottle_count, 0), '×', 'info',
                    '50 L standard bottles (ceil)')
                + U.statCard('RESIDUAL GAS', U.fmt(st.residual_mass_kg, 3), 'kg', 'dim',
                    'Unusable gas left below P_min');
        } else {
            const bdKind = (Number.isFinite(p.blowdown_ratio) && p.blowdown_ratio > 4) ? 'warn' : 'ok';
            cards += U.statCard('BLOWDOWN RATIO', U.fmt(p.blowdown_ratio, 2), '', bdKind,
                'P_initial / P_final — engine must tolerate this pressure range')
                + U.statCard('INITIAL PRESSURE', U.fmt(p.initial_pressure / 1e5, 1), 'bar', 'dim', '')
                + U.statCard('FINAL PRESSURE', U.fmt(p.final_pressure / 1e5, 1), 'bar', 'info', '')
                + U.statCard('FINAL TEMP', U.fmt(p.final_temperature_K, 0), 'K', 'dim',
                    'Polytropic cooling of the trapped gas')
                + U.statCard('TRAPPED GAS', U.fmt(p.gas_mass_kg, 3), 'kg', 'dim', '')
                + U.statCard('POLYTROPIC n', U.fmt(p.polytropic_n, 2), '', 'dim',
                    '1.0 isothermal .. gamma adiabatic');
        }
        cards += '</div>';
        head.innerHTML = cards;
        root.appendChild(head);

        const tail = document.createElement('div');
        let html = '';
        if (p.model_note) html += U.listBlock('Model assumptions & limits', [p.model_note], 'dim');
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    // ---- Water hammer render ------------------------------------------
    function whKind(status) {
        if (status === 'SAFE') return 'ok';
        if (status === 'MARGINAL') return 'warn';
        if (status === 'UNSAFE') return 'err';
        return 'dim';
    }

    function renderWaterHammer(data, root) {
        const w = (data && data.water_hammer) || {};
        const pipe = w.pipe || {};
        const kind = whKind(w.status);
        const head = document.createElement('div');
        let html = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge('STATUS: ' + String(w.status || '—'), kind,
                'SAFE ≤ MAWP · MARGINAL ≤ hoop yield · UNSAFE > hoop yield')
            + U.badge('FLUID: ' + String(w.fluid_name || w.fluid || '—'), 'dim',
                (w.fluid_properties && w.fluid_properties.source) || '')
            + U.badge('CLOSURE: ' + String(w.closure_regime || '—').toUpperCase(), 'info')
            + '</div>';
        html += '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard('PEAK PRESSURE', U.fmt(w.peak_pressure_bar, 1), 'bar', kind,
                'Working pressure + applied transient rise')
            + U.statCard('JOUKOWSKY RISE', U.fmt(w.joukowsky_pressure_rise_bar, 1), 'bar', 'dim',
                'Instantaneous-closure rise ρ·a·Δv (Joukowsky 1898)')
            + U.statCard('APPLIED RISE', U.fmt(w.applied_pressure_rise_bar, 1), 'bar', 'info',
                'Rise for the actual closure time (Michaud reduction if slow)')
            + U.statCard('WAVE SPEED', U.fmt(w.wave_speed_m_s, 0), 'm/s', 'dim',
                'Elastic-pipe corrected (Wylie & Streeter Eq. 1-10)')
            + U.statCard('CRITICAL TIME 2L/a', U.fmt(w.critical_closure_time_ms, 1), 'ms', 'dim',
                'Closure faster than this → full Joukowsky pressure')
            + U.statCard('PIPE MAWP', U.fmt(pipe.mawp_bar, 1), 'bar', 'dim',
                (pipe.mawp_source || '') + ' · ' + (pipe.material_name || ''))
            + U.statCard('RECOMMENDED CLOSURE', U.fmt(w.recommended_closure_time_ms, 1), 'ms',
                (w.recommended_closure_time_ms == null ? 'ok' : 'warn'),
                'Minimum valve closure time to keep the peak within the pipe MAWP')
            + '</div>';
        head.innerHTML = html;
        root.appendChild(head);

        const tail = document.createElement('div');
        let t = '';
        if (w.recommendation) {
            t += '<p style="font-size:0.85rem; color:var(--hd-ink, #cfe8f2); margin:8px 0;">'
                + w.recommendation + '</p>';
        }
        if (Array.isArray(w.warnings) && w.warnings.length) {
            t += U.listBlock('Warnings', w.warnings, kind === 'err' ? 'err' : 'warn');
        }
        if (Array.isArray(w.assumptions) && w.assumptions.length) {
            t += U.listBlock('Model assumptions & limits', w.assumptions, 'dim');
        }
        tail.innerHTML = t;
        root.appendChild(tail);
    }

    // ------------------------------------------------------------------
    // Sekme kataloğu
    // ------------------------------------------------------------------
    const TABS = [
        {
            key: 'slosh', label: 'Slosh', endpoint: '/api/slosh-analysis',
            motorTypes: ['liquid', 'hybrid'], render: renderSlosh,
            fields: [
                ['radius', 'Tank Radius (m)', 0.3, 0.01],
                ['fill_height', 'Fill Height (m)', 0.6, 0.01],
                ['g_eff', 'Axial Acceleration (m/s²)', 9.81, 0.1],
                ['fluid_density', 'Propellant Density (kg/m³)', 810, 1],
                ['baffle_width_ratio', 'Baffle Width w/R', 0.15, 0.01],
                ['baffle_depth_ratio', 'Baffle Depth d/R', 0.10, 0.01],
            ],
            suggest: function (m) {
                const sug = {};
                const ox = m.propellant_tanks && m.propellant_tanks.oxidizer_tank;
                const dim = ox && ox.dimensions;
                if (dim && Number.isFinite(dim.diameter)) {
                    sug.radius = Number((dim.diameter / 2 / 1000).toPrecision(4)); // mm → m radius
                }
                if (dim && Number.isFinite(dim.length)) {
                    sug.fill_height = Number((dim.length / 1000 * 0.9).toPrecision(4)); // ~90% dolu
                }
                let rho = m.oxidizer_density;
                if (!Number.isFinite(rho) && ox && ox.propellant_data) rho = ox.propellant_data.density;
                if (Number.isFinite(rho)) sug.fluid_density = Math.round(rho);
                return sug;
            },
        },
        {
            key: 'pressurant', label: 'Pressurant', endpoint: '/api/pressurant-sizing',
            motorTypes: ['liquid', 'hybrid'], render: renderPressurant,
            note: 'Regulated uses tank/storage pressure; Blowdown uses initial ullage '
                + 'volume and initial pressure. Unused fields are ignored per mode.',
            fields: [
                ['mode', 'Architecture', 'regulated', PRESS_MODES],
                ['gas', 'Pressurant Gas', 'helium', GASES],
                ['propellant_volume', 'Propellant Volume (m³)', 0.5, 0.01],
                ['initial_temperature', 'Gas Temperature (K)', 293, 1],
                ['tank_pressure', 'Tank Pressure (bar) [reg]', 20, 1],
                ['storage_pressure', 'Storage Pressure (bar) [reg]', 200, 5],
                ['regulator_margin', 'Regulator Margin [reg]', 0.10, 0.01],
                ['collapse_factor', 'Collapse Factor [reg]', 1.0, 0.05],
                ['initial_ullage_volume', 'Initial Ullage Vol (m³) [bd]', 0.10, 0.01],
                ['initial_pressure', 'Initial Pressure (bar) [bd]', 30, 1],
                ['polytropic_n', 'Polytropic n [bd]', 1.2, 0.05],
            ],
            suggest: function (m) {
                const sug = {};
                if (Number.isFinite(m.chamber_pressure)) sug.tank_pressure = Number(m.chamber_pressure.toPrecision(4));
                const ox = m.propellant_tanks && m.propellant_tanks.oxidizer_tank;
                const dim = ox && ox.dimensions;
                if (dim && Number.isFinite(dim.volume)) {
                    sug.propellant_volume = Number((dim.volume / 1000).toPrecision(4)); // L → m³
                }
                return sug;
            },
        },
        {
            key: 'water_hammer', label: 'Water Hammer', endpoint: '/api/water-hammer',
            motorTypes: ['liquid', 'hybrid', 'solid'], render: renderWaterHammer,
            fields: [
                ['fluid', 'Line Fluid', 'water', WH_FLUIDS],
                ['line_length_m', 'Line Length (m)', 20, 0.5],
                ['line_id_mm', 'Line Inner Diameter (mm)', 25, 1],
                ['wall_thickness_mm', 'Wall Thickness (mm)', 2, 0.1],
                ['working_pressure_bar', 'Working Pressure (bar)', 20, 1],
                ['mdot_kg_s', 'Mass Flow (kg/s)', 5, 0.1],
                ['valve_closure_time_ms', 'Valve Closure Time (ms)', 50, 1],
                ['pipe_material', 'Pipe Material', 'ss_304', PIPE_MATERIALS],
            ],
            suggest: function (m) {
                const sug = {};
                if (Number.isFinite(m.chamber_pressure)) sug.working_pressure_bar = Number(m.chamber_pressure.toPrecision(4));
                let mdotOx = m.mdot_ox;
                if (!Number.isFinite(mdotOx)) mdotOx = m.oxidizer_flow;
                if (Number.isFinite(mdotOx) && mdotOx > 0) sug.mdot_kg_s = Number(mdotOx.toPrecision(4));
                return sug;
            },
        },
    ];

    // ------------------------------------------------------------------
    // Form yardımcıları
    // ------------------------------------------------------------------
    function fieldDom(tabKey, fid) { return 'feed_' + tabKey + '_' + fid; }

    function fieldHtml(tabKey, f) {
        const fid = f[0], label = f[1], def = f[2], step = f[3];
        const id = fieldDom(tabKey, fid);
        if (Array.isArray(step)) {
            const opts = step.map(function (o) {
                return '<option value="' + o[0] + '"' + (o[0] === def ? ' selected' : '')
                    + '>' + o[1] + '</option>';
            }).join('');
            return '<div class="form-group"><label>' + label + '</label>'
                + '<select id="' + id + '" data-field="' + fid + '">' + opts + '</select></div>';
        }
        return '<div class="form-group"><label>' + label + '</label>'
            + '<input type="number" id="' + id + '" data-field="' + fid + '" value="'
            + def + '" step="' + step + '"></div>';
    }

    function readForm(paneEl) {
        const payload = {};
        paneEl.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') { payload[key] = el.value; return; }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) payload[key] = v;
        });
        return payload;
    }

    // Motor sonucundan önerileri (dirty olmayan alanlara) uygula
    function applyTabSuggestions(tab, paneEl) {
        if (typeof tab.suggest !== 'function') return;
        const r = window.currentResults;
        const m = (r && r.motor) || r;
        if (!m) return;
        let sug = null;
        try { sug = tab.suggest(m); } catch (e) { sug = null; }
        if (!sug) return;
        Object.keys(sug).forEach(function (k) {
            const el = document.getElementById(fieldDom(tab.key, k));
            if (!el || el.dataset.dirty === '1') return;
            const v = sug[k];
            if (el.tagName === 'SELECT') { if (v != null) el.value = String(v); return; }
            if (Number.isFinite(v)) el.value = v;
        });
    }

    // ------------------------------------------------------------------
    // Sekme çalıştırma
    // ------------------------------------------------------------------
    async function runTab(tab, paneEl) {
        const status = paneEl.querySelector('.feed-status');
        const result = paneEl.querySelector('.feed-result');
        const btn = paneEl.querySelector('.feed-run');
        if (!status || !result || !btn) return;
        btn.disabled = true;
        result.style.display = 'none';
        status.textContent = 'RUNNING…';
        try {
            const resp = await fetch(tab.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(readForm(paneEl)),
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            result.innerHTML = '';
            tab.render(data, result);
            result.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = 'ERROR: ' + err.message;
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Sekmeli arayüz montajı (güverte bölüm kabuğuna)
    // ------------------------------------------------------------------
    function visibleTabs() {
        const mt = window.AnalysisDock.getMotorType();
        return TABS.filter(function (t) { return t.motorTypes.indexOf(mt) !== -1; });
    }

    function subTabButtonHtml(tab, active) {
        const on = active;
        return '<button type="button" class="feed-tab" data-tab="' + tab.key + '"'
            + ' style="font-family:var(--hd-mono); font-size:0.76rem; letter-spacing:0.06em;'
            + ' padding:6px 14px; cursor:pointer; border-radius:6px 6px 0 0;'
            + ' border:1px solid var(--hd-line, rgba(0,229,255,0.14)); border-bottom:none;'
            + ' background:' + (on ? 'rgba(0,229,255,0.10)' : 'transparent') + ';'
            + ' color:' + (on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)')
            + ';">' + tab.label + '</button>';
    }

    function paneHtml(tab, active) {
        const fields = tab.fields.map(function (f) { return fieldHtml(tab.key, f); }).join('');
        const noteHtml = tab.note
            ? '<p style="font-size:0.76rem; color:var(--hd-ink-dim, #7d97a5); margin:4px 0 8px;">'
              + tab.note + '</p>'
            : '';
        return '<div class="feed-pane" data-pane="' + tab.key + '"'
            + ' style="display:' + (active ? 'block' : 'none') + '; padding:12px 4px 4px;">'
            + noteHtml
            + '<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));'
            + ' gap:10px; margin:6px 0;">' + fields
            + '<div class="form-group" style="align-self:end;">'
            + '<button class="btn feed-run" type="button">Run Analysis</button></div></div>'
            + '<div class="feed-status" style="font-family:var(--hd-mono);'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>'
            + '<div class="feed-result" style="display:none;"></div></div>';
    }

    function selectSubTab(container, key) {
        container.querySelectorAll('.feed-tab').forEach(function (b) {
            const on = b.getAttribute('data-tab') === key;
            b.style.background = on ? 'rgba(0,229,255,0.10)' : 'transparent';
            b.style.color = on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)';
        });
        container.querySelectorAll('.feed-pane').forEach(function (p) {
            p.style.display = (p.getAttribute('data-pane') === key) ? 'block' : 'none';
        });
    }

    let mounted = false;

    function mountFeedTools() {
        if (mounted) return true;
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        if (!sec || !root) return false;
        mounted = true;

        // Güvertenin varsayılan tek-Run akışını gizle (kendi sekme Run'larımız var)
        const runBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (runBtn) {
            const grp = runBtn.closest('.form-group');
            (grp || runBtn).style.display = 'none';
        }
        const st = document.getElementById('ad_status_' + PANEL_ID);
        if (st) st.style.display = 'none';
        // Bölüm başlığındaki tek-endpoint ipucunu üç endpoint özetiyle değiştir
        const hint = sec.querySelector('h3 span');
        if (hint) hint.textContent = 'slosh · pressurant · water-hammer';

        const tabs = visibleTabs();
        if (!tabs.length) { root.style.display = 'none'; return true; }
        const activeKey = tabs[0].key;

        const bar = tabs.map(function (t) { return subTabButtonHtml(t, t.key === activeKey); }).join('');
        const panes = tabs.map(function (t) { return paneHtml(t, t.key === activeKey); }).join('');
        root.innerHTML = '<div class="feed-tabbar" style="display:flex; gap:6px;'
            + ' flex-wrap:wrap; margin:6px 0 0;">' + bar + '</div>'
            + '<div class="feed-panes" style="border-top:1px solid'
            + ' var(--hd-line-strong, rgba(0,229,255,0.42)); padding-top:4px;">' + panes + '</div>';
        root.style.display = 'block';

        // Sekme geçişleri
        root.querySelectorAll('.feed-tab').forEach(function (b) {
            b.addEventListener('click', function () {
                const key = b.getAttribute('data-tab');
                selectSubTab(root, key);
                const tab = tabs.filter(function (t) { return t.key === key; })[0];
                const pane = root.querySelector('.feed-pane[data-pane="' + key + '"]');
                if (tab && pane) applyTabSuggestions(tab, pane);
            });
        });

        // Her sekme: Run butonu + dirty izleme + ilk öneri dolumu
        tabs.forEach(function (tab) {
            const pane = root.querySelector('.feed-pane[data-pane="' + tab.key + '"]');
            if (!pane) return;
            const btn = pane.querySelector('.feed-run');
            if (btn) btn.addEventListener('click', function () { runTab(tab, pane); });
            pane.querySelectorAll('[data-field]').forEach(function (el) {
                el.addEventListener('input', function () { el.dataset.dirty = '1'; });
                el.addEventListener('change', function () { el.dataset.dirty = '1'; });
            });
            applyTabSuggestions(tab, pane);
        });
        return true;
    }

    // Güverte bölüm kabuğu init sırasında kurulur; hazır olana kadar yokla
    // (flow_panel.js'in select bekleme desenini yansıtır).
    function scheduleMount() {
        if (mountFeedTools()) return;
        let tries = 0;
        const timer = setInterval(function () {
            tries += 1;
            if (mountFeedTools() || tries > 60) clearInterval(timer);
        }, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleMount);
    } else {
        scheduleMount();
    }

    // ------------------------------------------------------------------
    // Kayıt: yalnız FEED SYSTEM kategori sekmesini + bölüm kabuğunu + motor
    // tipi kapısını üretmek için. Gerçek işi sekmeler kendi endpoint'leriyle
    // yapar; render() güverte Run'ı (gizli) tetiklenirse aracı kurar.
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Feed System — Slosh, Pressurant & Water Hammer',
        category: 'FEED SYSTEM',
        endpoint: '/api/water-hammer',
        motorTypes: ['liquid', 'hybrid', 'solid'],
        fields: [],
        // Öneriler sekme bazında uygulanır (applyTabSuggestions); dock
        // alan-öneri mekanizması bu panelde kullanılmaz.
        fromResults: function () { return {}; },
        render: function () { mountFeedTools(); },
    });

    // Test / hata ayıklama: saf render + yardımcılar
    window.FeedPanel = {
        _renderSlosh: renderSlosh,
        _renderPressurant: renderPressurant,
        _renderWaterHammer: renderWaterHammer,
        _whKind: whKind,
        _tabs: TABS,
        _mountFeedTools: mountFeedTools,
    };
})();
