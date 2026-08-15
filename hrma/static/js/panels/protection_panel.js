/* ====================================================================
   HRMA Analiz Güvertesi — Termal Koruma Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/thermal-protection sonucunu çizer (thermal_panel'in yanında,
   THERMAL sekmesinde İKİNCİ panel — dock aynı kategoride panelleri alt
   alta gösterir):
   - Mode: ablative (Q* boyutlandırma) / heat_sink (1-D transient) /
     radiation_equilibrium (radyasyon-soğutmalı uzantı)
   - Ablatif: gereken kalınlık, gerileme hızı, Q* bandı
   - Heat-sink: T(x) Plotly çizgisi + T_w(t) geçmişi, time_to_limit
   - Radyasyon: denge cidar sıcaklığı, servis limiti marjı
   - Her modda 'SIMPLIFIED MODEL' rozeti (backend model_note alanı)
   Alan etiketleri [A]/[H]/[R] önekiyle hangi moda ait olduğunu söyler;
   backend beyaz listesi (app.py) hedef modun kullanmadığı alanları düşürür.
   Backend: hrma/analysis/thermal_protection.py (NASA SP-8093 sınıfı Q*,
   Incropera explicit FD, Sutton & Biblarz Ch. 8).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    var U = window.AnalysisDock.ui;
    var T = U.t;                         // çeviri kısayolu

    var MODES = [
        ['ablative', 'Ablative liner — Q* sizing', 'tps.modeAblative'],
        ['heat_sink', 'Heat-sink wall — 1-D transient', 'tps.modeHeatSink'],
        ['radiation_equilibrium', 'Radiation-cooled extension', 'tps.modeRadiation'],
    ];

    // FALLBACK — thermal_protection.py ABLATIVE_MATERIALS anahtarlarıyla
    // birebir; katalog gelirse 'ablative' etiketli DB kayıtlarıyla
    // BİRLEŞTİRİLİR (carbon_phenolic/epdm modele özgüdür, listede kalır)
    var ABLATIVES = [
        ['silica_phenolic', 'Silica-phenolic (MX-2600 class)', 'tps.silicaPhenolic'],
        ['carbon_phenolic', 'Carbon-phenolic (MX-4926 class)', 'tps.carbonPhenolic'],
        ['epdm', 'EPDM rubber insulation', 'tps.epdm'],
    ];

    // FALLBACK — materials_db anahtarları (heat-sink metal cidar);
    // katalog gelirse 'shell'+'liner' etiketli tam liste bunun yerine geçer
    var WALL_MATERIALS = [
        ['steel', 'Steel (generic)'],
        ['steel_4130', 'Steel AISI 4130'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['copper', 'Copper (OFHC)'],
        ['cucrzr', 'CuCrZr'],
        ['inconel_718', 'Inconel 718'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['graphite', 'Graphite'],
    ];

    // FALLBACK — thermal_protection.py RADIATION_EXTENSION_MATERIALS +
    // merkezi DB; katalog gelirse 'radiative' etiketli liste bunun yerine geçer
    var RAD_MATERIALS = [
        ['niobium_c103', 'Niobium C-103 (silicide coated)', 'tps.niobium'],
        ['carbon_carbon', 'Carbon-carbon (2D/3D C-C)', 'tps.carbonCarbon'],
        ['ss_316', 'Stainless 316'],
        ['inconel_718', 'Inconel 718'],
    ];

    function simplifiedBadge(note) {
        return U.badge(T('panel.protection.simplified', 'SIMPLIFIED MODEL'), 'warn',
            note || T('panel.protection.simplifiedTip',
                      'Preliminary hand-calculation model — see assumptions.'));
    }

    function limitKind(within) {
        if (within == null) return 'dim';
        return within ? 'ok' : 'err';
    }

    // ---- Ablatif mod ----
    function renderAblative(d, root) {
        var el = document.createElement('div');
        var band = Array.isArray(d.q_star_band_MJ_kg)
            ? d.q_star_band_MJ_kg.join('–') + ' MJ/kg' : '—';
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeAblative', 'MODE: ABLATIVE (Q*)'), 'info')
            + U.badge(d.material_name || d.material || '—', 'info')
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardThickness', 'Required liner thickness'),
                U.fmt(d.required_thickness_mm, 2),
                'mm', 'info', T('panel.protection.cardThicknessTip', 'Total recession × design margin'))
            + U.statCard(T('panel.protection.cardRecession', 'Total recession'),
                U.fmt(d.total_recession_mm, 2), 'mm')
            + U.statCard(T('panel.protection.cardRecessionRate', 'Recession rate (mean)'),
                U.fmt(d.recession_rate_mm_s, 3), 'mm/s')
            + U.statCard(T('panel.protection.cardQstar', 'Q* used'), U.fmt(d.q_star_MJ_kg, 1), 'MJ/kg', null,
                U.tf('panel.protection.cardQstarTip', { band: band },
                     'Literature band: {band} — conservative low end by default'))
            + '</div>'
            + U.kvTable([
                [T('panel.protection.meanFlux', 'Mean heat flux'), U.fmt(d.q_mean_W_m2 / 1e6, 2) + ' MW/m²'],
                [T('panel.protection.totalLoad', 'Total heat load'),
                 U.fmt(d.total_heat_load_J_m2 / 1e6, 1) + ' MJ/m²'],
                [T('common.burnTime', 'Burn Time'), U.fmt(d.burn_time_s, 1) + ' s'],
                [T('common.density', 'Density'), U.fmt(d.density_kg_m3, 0) + ' kg/m³'],
                [T('panel.protection.designMargin', 'Design margin'), U.fmt(d.design_margin, 2) + '×'],
                [T('common.source', 'Source'), d.source || '—'],
            ]);
        root.appendChild(el);
    }

    // ---- Heat-sink modu: kartlar + T(x) + T_w(t) grafikleri ----
    function renderHeatSink(d, root) {
        var el = document.createElement('div');
        var exceeded = !!d.exceeds_limit;
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeHeatSink', 'MODE: HEAT SINK (1-D FD)'), 'info')
            + U.badge(d.material_name || d.wall_material || '—', 'info')
            + (exceeded
                ? U.badge(T('panel.protection.limitExceeded', 'SERVICE LIMIT EXCEEDED'), 'err',
                    T('panel.protection.limitExceededTip',
                      'Inner wall reaches the material service limit during the burn'))
                : U.badge(T('panel.protection.withinLimit', 'WITHIN SERVICE LIMIT'), 'ok'))
            + (d.cfl_ok === false
                ? U.badge(T('panel.protection.cflUnstable', 'CFL UNSTABLE'), 'err',
                          T('panel.protection.cflTip', 'Explicit FD stability criterion violated'))
                : '')
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardInnerT', 'Inner wall T (end of burn)'),
                U.fmt(d.T_inner_K, 0), 'K', exceeded ? 'err' : 'ok')
            + U.statCard(T('panel.protection.cardOuterT', 'Outer wall T'), U.fmt(d.T_outer_K, 0), 'K')
            + U.statCard(T('panel.protection.serviceLimit', 'Service limit'),
                U.fmt(d.max_service_temp_K, 0), 'K', 'dim')
            + U.statCard(T('panel.protection.cardTimeToLimit', 'Time to limit'),
                (d.time_to_limit_s == null ? '—' : U.fmt(d.time_to_limit_s, 2)),
                's', exceeded ? 'err' : 'ok',
                T('panel.protection.cardTimeToLimitTip',
                  'Moment the inner wall reaches the service limit (\u201c\u2014\u201d = never during burn)'))
            + U.statCard(T('panel.protection.cardMargin', 'Margin to limit'), U.fmt(d.margin_to_limit_K, 0), 'K',
                exceeded ? 'err' : 'ok')
            + '</div>'
            + U.kvTable([
                [T('panel.protection.absorbedEnergy', 'Absorbed energy'),
                 U.fmt(d.absorbed_energy_J_m2 / 1e6, 2) + ' MJ/m²'],
                [T('panel.protection.hGas', 'h_gas (input, Bartz)'), U.fmt(d.h_gas_W_m2K, 0) + ' W/m²·K'],
                [T('panel.protection.recoveryTemp', 'Recovery temperature'), U.fmt(d.T_recovery_K, 0) + ' K'],
                [T('panel.protection.gridStep', 'Grid / time step'),
                 U.tf('panel.protection.gridStepValue',
                      { n: (d.n_nodes || '—'), dt: U.fmt(d.dt_s * 1e3, 2) },
                      '{n} nodes · dt = {dt} ms'),
                 'Fo = ' + U.fmt(d.Fo, 3) + ', Bi = ' + U.fmt(d.Bi, 3)
                    + ', CFL ok: ' + d.cfl_ok],
            ]);
        root.appendChild(el);

        if (typeof Plotly === 'undefined') return;

        // --- T(x) profili (yanma sonu) ---
        var x = Array.isArray(d.x_m) ? d.x_m : [];
        var Tp = Array.isArray(d.T_profile_K) ? d.T_profile_K : [];
        if (x.length && Tp.length === x.length) {
            var div1 = document.createElement('div');
            div1.style.marginTop = '10px';
            root.appendChild(div1);
            var shapes = [];
            var annotations = [];
            if (Number.isFinite(d.max_service_temp_K)) {
                shapes.push({
                    type: 'line', xref: 'paper', x0: 0, x1: 1,
                    y0: d.max_service_temp_K, y1: d.max_service_temp_K,
                    line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
                });
                annotations.push({
                    xref: 'paper', x: 1, y: d.max_service_temp_K,
                    xanchor: 'right', yanchor: 'bottom',
                    text: T('panel.protection.serviceLimit', 'Service limit') + ' — '
                        + Math.round(d.max_service_temp_K) + ' K',
                    showarrow: false, font: { size: 10, color: '#ff5d73' },
                });
            }
            Plotly.newPlot(div1, [{
                x: x.map(function (v) { return v * 1e3; }), y: Tp,
                type: 'scatter', mode: 'lines',
                line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.2f} mm<br>T = %{y:.0f} K<extra></extra>',
            }], {
                title: T('panel.protection.chartProfile', 'Wall Temperature Profile at End of Burn'),
                xaxis: { title: T('panel.protection.axisDepth', 'Depth from hot face (mm)') },
                yaxis: { title: T('common.axis.temperatureK', 'Temperature (K)') },
                shapes: shapes,
                annotations: annotations,
                height: 340,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
        }

        // --- T_w(t) geçmişi (store_history varsayılan açık) ---
        var h = d.history || {};
        var ht = Array.isArray(h.t_s) ? h.t_s : [];
        var hT = Array.isArray(h.T_inner_K) ? h.T_inner_K : [];
        if (ht.length > 1 && hT.length === ht.length) {
            var div2 = document.createElement('div');
            div2.style.marginTop = '10px';
            root.appendChild(div2);
            var shapes2 = [];
            var ann2 = [];
            if (Number.isFinite(d.max_service_temp_K)) {
                shapes2.push({
                    type: 'line', xref: 'paper', x0: 0, x1: 1,
                    y0: d.max_service_temp_K, y1: d.max_service_temp_K,
                    line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
                });
            }
            if (Number.isFinite(d.time_to_limit_s)) {
                shapes2.push({
                    type: 'line', yref: 'paper',
                    x0: d.time_to_limit_s, x1: d.time_to_limit_s, y0: 0, y1: 1,
                    line: { color: '#ff8c33', width: 1, dash: 'dot' },
                });
                ann2.push({
                    x: d.time_to_limit_s, yref: 'paper', y: 1,
                    xanchor: 'left', yanchor: 'top',
                    text: T('panel.protection.limitReached', 'Limit reached') + ' — '
                        + U.fmt(d.time_to_limit_s, 2) + ' s',
                    showarrow: false, font: { size: 10, color: '#ff8c33' },
                });
            }
            Plotly.newPlot(div2, [{
                x: ht, y: hT, type: 'scatter', mode: 'lines',
                line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 't = %{x:.2f} s<br>T_w = %{y:.0f} K<extra></extra>',
            }], {
                title: T('panel.protection.chartHistory', 'Hot-Face Temperature History'),
                xaxis: { title: T('common.axis.timeS', 'Time (s)') },
                yaxis: { title: T('panel.protection.axisInnerT', 'Inner wall temperature (K)') },
                shapes: shapes2,
                annotations: ann2,
                height: 320,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
        }
    }

    // ---- Radyasyon dengesi modu ----
    function renderRadiation(d, root) {
        var el = document.createElement('div');
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeRadiation', 'MODE: RADIATION EQUILIBRIUM'), 'info')
            + (d.material_name ? U.badge(d.material_name, 'info') : '')
            + (d.within_limit == null ? ''
                : (d.within_limit
                    ? U.badge(T('panel.protection.withinLimit', 'WITHIN SERVICE LIMIT'), 'ok')
                    : U.badge(T('panel.protection.limitExceeded', 'SERVICE LIMIT EXCEEDED'), 'err')))
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardEqWall', 'Equilibrium wall T'), U.fmt(d.T_wall_eq_K, 0), 'K',
                limitKind(d.within_limit),
                T('panel.protection.cardEqWallTip', 'h_g·(T_recovery − T_w) = ε·σ·T_w⁴ energy balance'))
            + U.statCard(T('panel.protection.serviceLimit', 'Service limit'),
                (d.service_limit_K == null ? '—' : U.fmt(d.service_limit_K, 0)),
                'K', 'dim')
            + U.statCard(T('common.margin', 'Margin'),
                (d.margin_K == null ? '—' : U.fmt(d.margin_K, 0)),
                'K', limitKind(d.within_limit))
            + U.statCard(T('panel.protection.cardRadFlux', 'Radiated flux'), U.fmt(d.q_rad_W_m2 / 1e6, 2), 'MW/m²')
            + '</div>'
            + U.kvTable([
                [T('panel.protection.emissivityUsed', 'Emissivity used'), U.fmt(d.emissivity, 2)],
                [T('panel.protection.hGas', 'h_gas (input, Bartz)'), U.fmt(d.h_gas_W_m2K, 0) + ' W/m²·K'],
                [T('panel.protection.recoveryTemp', 'Recovery temperature'), U.fmt(d.T_recovery_K, 0) + ' K'],
                [T('common.source', 'Source'), d.source || '—'],
            ]);
        root.appendChild(el);
    }

    function render(data, root) {
        var d = data || {};
        // Mod tespiti yanıt anahtarlarından (endpoint modu geri yansıtmaz)
        if (Array.isArray(d.T_profile_K)) {
            renderHeatSink(d, root);
        } else if (typeof d.T_wall_eq_K === 'number') {
            renderRadiation(d, root);
        } else {
            renderAblative(d, root);
        }
    }

    window.AnalysisDock.register({
        id: 'protection',
        title: 'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled',
        titleKey: 'panel.protection.title',
        category: 'THERMAL',
        endpoint: '/api/thermal-protection',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['mode', 'Analysis Mode', 'ablative', MODES, 'panel.protection.fMode'],
            ['q_net_W_m2', '[A] Net Heat Flux (W/m²)', 2000000, 100000, 'panel.protection.fQNet'],
            ['material', '[A] Ablative Material', 'silica_phenolic', ABLATIVES,
             'panel.protection.fAblativeMaterial'],
            ['design_margin', '[A] Design Margin (×)', 1.5, 0.1, 'panel.protection.fDesignMargin'],
            ['q_star_MJ_kg', '[A] Q* Override (MJ/kg, blank = band)', '', 0.5,
             'panel.protection.fQstarOverride'],
            ['burn_time_s', '[A/H] Burn Time (s)', 10, 0.5, 'panel.protection.fBurnTime'],
            ['h_gas_W_m2K', '[H/R] h_gas — Bartz (W/m²·K)', 3000, 100, 'panel.protection.fHgas'],
            ['T_recovery_K', '[H/R] Recovery Temperature (K)', 3200, 50, 'panel.protection.fTRecovery'],
            ['wall_thickness_m', '[H] Wall Thickness (m)', 0.005, 0.001, 'panel.protection.fWallThickness'],
            ['wall_material', '[H] Wall Material', 'steel', WALL_MATERIALS,
             'panel.protection.fWallMaterial'],
            ['T_initial_K', '[H] Initial Temperature (K)', 300, 5, 'panel.protection.fTInitial'],
            ['radiation_material', '[R] Extension Material', 'niobium_c103', RAD_MATERIALS,
             'panel.protection.fRadMaterial'],
            ['emissivity', '[R] Emissivity Override (blank = material)', '', 0.05,
             'panel.protection.fEmissivity'],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            if (Number.isFinite(m.burn_time)) out.burn_time_s = m.burn_time;
            // Plan Dalga 3: q / h_g önerileri motorun gerçek Bartz sonucundan
            // (motor.heat_transfer_analysis.gas_side_analysis)
            var hta = m.heat_transfer_analysis || {};
            var gsa = hta.gas_side_analysis || {};
            if (Number.isFinite(gsa.heat_flux)) {
                out.q_net_W_m2 = gsa.heat_flux;          // W/m² (boğaz tasarım yükü)
            }
            if (Number.isFinite(gsa.gas_side_coefficient)) {
                out.h_gas_W_m2K = gsa.gas_side_coefficient;
            } else {
                var htc = hta.heat_transfer_coefficients || {};
                if (Number.isFinite(htc.gas_side)) out.h_gas_W_m2K = htc.gas_side;
            }
            if (Number.isFinite(gsa.adiabatic_wall_temperature)) {
                out.T_recovery_K = gsa.adiabatic_wall_temperature;
            }
            return out;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse üç select'i etiket filtreleriyle doldur;
    // değilse fallback listeleri aynen kalır. Ablatif listesi MERGE ile
    // birleştirilir: carbon_phenolic/epdm yalnız thermal_protection.py
    // tablosunda vardır, kaybolmamalı.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'material',
            tags: ['ablative'], fallback: ABLATIVES, merge: true,
        });
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'wall_material',
            tags: ['shell', 'liner'], fallback: WALL_MATERIALS, merge: true,
        });
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'radiation_material',
            tags: ['radiative'], fallback: RAD_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render'lar (dry-run)
    window.ProtectionPanel = {
        _render: render,
        _renderAblative: renderAblative,
        _renderHeatSink: renderHeatSink,
        _renderRadiation: renderRadiation,
    };
})();
