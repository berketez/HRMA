/* ====================================================================
   HRMA Analiz Güvertesi — Lüle Akışı Paneli (Dalga 4A)
   --------------------------------------------------------------------
   POST /api/flow-analysis sonuçlarını çizer (sahte CFD panelinin halefi:
   quasi-1D sıkıştırılabilir akış, docs/ANALIZ_PLATFORM_PLANI.md).

   Fidelity seçici:
     fast        → izantropik özet (rejim + CF/itki kartları)
     engineering → tam istasyon dizileri (P(x), M(x)) + Bartz + kinetik zincir
   High-Fidelity kinetik seçeneği yalnız Cantera mevcutsa listelenir —
   tespit /api/kinetic-efficiency {probe:true} yanıtının fidelity_used
   alanından yapılır (backend sözleşmesi).

   Yanıt şeması (test_client ile doğrulandı, 2026-07-14):
     { status:'success', fidelity, flow:{stations?, throat, regime,
       performance, losses, inputs}, kinetic_efficiency|null, kinetic_note? }

   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;

    const ENDPOINT = '/api/flow-analysis';
    const KINETIC_ENDPOINT = '/api/kinetic-efficiency';
    const PANEL_ID = 'flow';

    // Rejim rozetleri — separated/şok/boğulmamış KIRMIZI (görev sözleşmesi)
    const REGIME_INFO = {
        underexpanded: { label: 'UNDEREXPANDED', kind: 'info' },
        perfectly_expanded: { label: 'PERFECT EXPANSION', kind: 'ok' },
        overexpanded: { label: 'OVEREXPANDED', kind: 'warn' },
        separated: { label: 'SEPARATED', kind: 'err' },
        normal_shock_in_nozzle: { label: 'NORMAL SHOCK IN NOZZLE', kind: 'err' },
        unchoked: { label: 'UNCHOKED', kind: 'err' },
    };

    function regimeInfo(type) {
        return REGIME_INFO[type] || { label: String(type || 'UNKNOWN').toUpperCase(), kind: 'dim' };
    }

    // ------------------------------------------------------------------
    // High-Fidelity yetenek sondası: Cantera + reaksiyonlu mekanizma varsa
    // kinetik model seçicisine 'high_fidelity' seçeneği eklenir.
    // ------------------------------------------------------------------
    let hfProbeDone = false;

    function appendHighFidelityOption() {
        const sel = document.getElementById('ad_f_' + PANEL_ID + '_kinetic_fidelity');
        if (!sel) return false;
        if (!sel.querySelector('option[value="high_fidelity"]')) {
            const opt = document.createElement('option');
            opt.value = 'high_fidelity';
            opt.textContent = 'High-Fidelity (Cantera finite-rate)';
            sel.appendChild(opt);
        }
        return true;
    }

    function probeHighFidelity() {
        if (hfProbeDone) return;
        hfProbeDone = true;
        fetch(KINETIC_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ probe: true, fidelity: 'high_fidelity' }),
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
              if (!j || j.fidelity_used !== 'high_fidelity') return;
              // Güverte DOMContentLoaded'ta kurulur; select henüz yoksa
              // kısa aralıklarla dene (montaj yarışına dayanıklılık).
              if (appendHighFidelityOption()) return;
              let tries = 0;
              const timer = setInterval(function () {
                  tries += 1;
                  if (appendHighFidelityOption() || tries > 40) clearInterval(timer);
              }, 250);
          })
          .catch(function () { /* sonda başarısız → seçenek eklenmez */ });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', probeHighFidelity);
    } else {
        probeHighFidelity();
    }

    // ------------------------------------------------------------------
    // Çizim yardımcıları
    // ------------------------------------------------------------------
    function plotBlock(root, heading) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(heading);
        const plot = document.createElement('div');
        wrap.appendChild(plot);
        root.appendChild(wrap);
        return plot;
    }

    function separationShape(sep) {
        if (!sep || !Number.isFinite(sep.station_x_mm)) return [];
        return [{
            type: 'line', xref: 'x', yref: 'paper',
            x0: sep.station_x_mm, x1: sep.station_x_mm, y0: 0, y1: 1,
            line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
        }];
    }

    function drawStationPlots(flow, root) {
        const st = flow.stations;
        if (!st || !Array.isArray(st.x_mm) || !st.x_mm.length) {
            const note = document.createElement('p');
            note.style.cssText = 'font-family:var(--hd-mono); font-size:0.78rem;'
                + ' color:var(--hd-ink-dim, #7d97a5); margin:10px 0;';
            note.textContent = 'Fast Screening level: station arrays P(x)/M(x) '
                + 'require the Engineering fidelity level.';
            root.appendChild(note);
            return;
        }
        if (typeof Plotly === 'undefined') {
            const note = document.createElement('p');
            note.textContent = 'Plotly is not loaded — station charts skipped.';
            root.appendChild(note);
            return;
        }
        const sep = flow.regime && flow.regime.separation;
        const shapes = separationShape(sep);

        // P(x): çekirdek + cidar basıncı (ayrılmada ortam platosu görünür)
        const pBar = st.pressure_Pa.map(function (p) { return p / 1e5; });
        const pWallBar = (st.wall_pressure_Pa || st.pressure_Pa)
            .map(function (p) { return p / 1e5; });
        Plotly.newPlot(plotBlock(root, 'Static Pressure Along the Nozzle — P(x)'), [
            { x: st.x_mm, y: pBar, mode: 'lines', name: 'Core P(x) [bar]',
              line: { width: 2 } },
            { x: st.x_mm, y: pWallBar, mode: 'lines',
              name: 'Wall P(x) [bar]', line: { width: 1.5, dash: 'dot' } },
        ], {
            xaxis: { title: 'Axial position x (mm)' },
            yaxis: { title: 'Pressure (bar)' },
            shapes: shapes,
            margin: { t: 24, r: 16 },
            height: 320,
        }, { responsive: true, displaylogo: false });

        // M(x)
        Plotly.newPlot(plotBlock(root, 'Mach Number Along the Nozzle — M(x)'), [
            { x: st.x_mm, y: st.mach, mode: 'lines', name: 'Mach', line: { width: 2 } },
        ], {
            xaxis: { title: 'Axial position x (mm)' },
            yaxis: { title: 'Mach number' },
            shapes: shapes.concat([{
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: 1, y1: 1,
                line: { color: 'rgba(125,151,165,0.6)', width: 1, dash: 'dot' },
            }]),
            margin: { t: 24, r: 16 },
            height: 320,
        }, { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Kinetik kayıp bandı kartı
    // ------------------------------------------------------------------
    function kineticCard(kin, note) {
        if (!kin) {
            if (!note) return '';
            return `<p style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0;">${note}</p>`;
        }
        const band = kin.loss_band_pct || [null, null];
        const lo = U.fmt(band[0], 2), hi = U.fmt(band[1], 2);
        const fidelityBadge = U.badge(
            'KINETICS: ' + String(kin.fidelity_used || '?').toUpperCase(),
            kin.fidelity_used === 'high_fidelity' ? 'ok' : 'info',
            kin.model_note || '');
        return U.sectionTitle('Kinetic Efficiency — Frozen/Shifting Bracket')
            + `<div style="margin:4px 0 8px;">${fidelityBadge}</div>`
            + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard('KINETIC LOSS', U.fmt(kin.kinetic_loss_pct, 2), '%',
                kin.kinetic_loss_pct > 3 ? 'warn' : 'ok',
                'Isp loss vs shifting equilibrium')
            + U.statCard('LOSS BAND', lo + ' – ' + hi, '%', 'dim',
                'Honest uncertainty band on the kinetic loss')
            + U.statCard('ISP FROZEN', U.fmt(kin.isp_frozen, 1), 's', 'dim', '')
            + U.statCard('ISP PREDICTED', U.fmt(kin.isp_predicted, 1), 's', 'info', '')
            + U.statCard('ISP SHIFTING', U.fmt(kin.isp_shifting, 1), 's', 'dim', '')
            + '</div>';
    }

    // ------------------------------------------------------------------
    // Ana render
    // ------------------------------------------------------------------
    function render(data, root) {
        const flow = (data && data.flow) || {};
        const regime = flow.regime || {};
        const perf = flow.performance || {};
        const losses = flow.losses || {};
        const info = regimeInfo(regime.type);

        const head = document.createElement('div');
        let sepNote = '';
        if (regime.separation) {
            sepNote = `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">
                Separation at x = ${U.fmt(regime.separation.station_x_mm, 1)} mm
                (area ratio ${U.fmt(regime.separation.area_ratio, 2)}) —
                Summerfield criterion.</p>`;
        }
        head.innerHTML = U.sectionTitle('Flow Regime — Quasi-1D Classification')
            + `<div style="margin:4px 0 6px;">${U.badge(info.label, info.kind,
                regime.separation_criterion || '')}
               <span style="font-family:var(--hd-mono); font-size:0.72rem;
                     color:var(--hd-ink-dim, #7d97a5); margin-left:10px;">
                 ${data.fidelity === 'fast' ? 'FAST SCREENING' : 'ENGINEERING'} ·
                 ${flow.model || ''}</span></div>`
            + `<p style="font-size:0.82rem; color:var(--hd-ink, #cfe8f2); margin:6px 0;">
                ${regime.description || ''}</p>`
            + sepNote
            + U.sectionTitle('Thrust & Thrust Coefficient')
            + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard('CF', U.fmt(perf.CF, 3), '',
                'info', 'Thrust coefficient F/(Pc·At)')
            + U.statCard('CF IDEAL', U.fmt(perf.CF_ideal, 3), '',
                'dim', 'Sutton & Biblarz 9th ed. Eq. 3-30')
            + U.statCard('CF EFFECTIVE', U.fmt(losses.CF_effective, 3), '',
                'dim', 'After divergence + friction losses (approximate)')
            + U.statCard('THRUST', U.fmt(perf.thrust_N, 0), 'N', 'info', '')
            + U.statCard('EFFECTIVE THRUST', U.fmt(losses.thrust_effective_N, 0), 'N',
                'dim', losses.note || '')
            + U.statCard('MASS FLOW', U.fmt(perf.mass_flow_kg_s, 3), 'kg/s', 'dim', '')
            + U.statCard('C*', U.fmt(perf.c_star_m_s, 0), 'm/s', 'dim',
                'Analytic characteristic velocity (Sutton Eq. 3-32)')
            + U.statCard('EXIT MACH', U.fmt(perf.exit && perf.exit.mach, 2), '',
                'dim', '')
            + '</div>'
            + kineticCard(data.kinetic_efficiency, data.kinetic_note);
        root.appendChild(head);

        drawStationPlots(flow, root);

        // Varsayımlar — dürüst model sınırları (İngilizce, kullanıcıya görünür)
        if (Array.isArray(flow.assumptions) && flow.assumptions.length) {
            const div = document.createElement('div');
            div.innerHTML = U.listBlock('Model assumptions & limits',
                flow.assumptions, 'dim');
            root.appendChild(div);
        }
    }

    // ------------------------------------------------------------------
    // Kayıt
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)',
        category: 'FLOW',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['fidelity', 'Fidelity Level', 'engineering', [
                ['fast', 'Fast Screening'],
                ['engineering', 'Engineering'],
            ]],
            ['kinetic_fidelity', 'Kinetic Model', 'engineering', [
                ['fast', 'Fast (equilibrium reference)'],
                ['engineering', 'Engineering (JANNAF-style)'],
                // 'high_fidelity' seçeneği Cantera sondası başarılıysa eklenir
            ]],
            ['chamber_pressure', 'Chamber Pressure (bar)', 20, 1],
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 50],
            ['gamma', 'Gamma (frozen)', 1.2, 0.01],
            ['molecular_weight', 'Molecular Weight (g/mol)', 24, 0.5],
            ['throat_diameter', 'Throat Diameter (m)', 0.02, 0.001],
            ['exit_diameter', 'Exit Diameter (m)', 0.06, 0.001],
            ['ambient_pressure', 'Ambient Pressure (Pa)', 101325, 1000],
            ['n_stations', 'Axial Stations (30-60)', 45, 1],
            ['of_ratio', 'O/F Ratio (kinetics)', 6.0, 0.1],
            ['fuel_type', 'Fuel (kinetics)', 'htpb', [
                ['htpb', 'HTPB'], ['paraffin', 'Paraffin'], ['pe', 'PE'],
                ['pmma', 'PMMA'], ['abs', 'ABS'], ['pla', 'PLA'],
            ]],
            ['oxidizer_type', 'Oxidizer (kinetics)', 'N2O', [
                ['N2O', 'N2O'], ['LOX', 'LOX'], ['H2O2', 'H2O2'],
            ]],
        ],
        // Hibrit/katı/sıvı sayfalarında motor sonuçlarından otomatik dolum
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const sug = {};
            if (Number.isFinite(m.chamber_pressure)) sug.chamber_pressure = m.chamber_pressure;
            if (Number.isFinite(m.chamber_temperature)) sug.chamber_temperature = m.chamber_temperature;
            if (Number.isFinite(m.gamma)) sug.gamma = m.gamma;
            if (Number.isFinite(m.molecular_weight)) sug.molecular_weight = m.molecular_weight;
            if (Number.isFinite(m.throat_diameter)) sug.throat_diameter = m.throat_diameter;
            if (Number.isFinite(m.exit_diameter)) {
                sug.exit_diameter = m.exit_diameter;
            } else if (Number.isFinite(m.expansion_ratio) && m.expansion_ratio > 1
                       && Number.isFinite(m.throat_diameter)) {
                sug.exit_diameter = Number(
                    (m.throat_diameter * Math.sqrt(m.expansion_ratio)).toPrecision(5));
            }
            if (Number.isFinite(m.of_ratio)) sug.of_ratio = m.of_ratio;
            return sug;
        },
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (performance_panel deseni)
    window.FlowPanel = {
        _render: render,
        _regimeInfo: regimeInfo,
        _kineticCard: kineticCard,
        _appendHighFidelityOption: appendHighFidelityOption,
    };
})();
