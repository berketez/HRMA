/* ====================================================================
   HRMA Analiz Güvertesi — Rejeneratif Soğutma Paneli (Dalga 4B)
   --------------------------------------------------------------------
   POST /api/regen-cooling sonucunu çizer (1D istasyon marşı, analiz modu;
   hrma/analysis/regen_cooling.py — Bartz gaz tarafı + Dittus-Boelter
   soğutucu tarafı + ince-cidar iletim).

   Panel içeriği:
     - Rozetler: soğutucu, cidar malzemesi, akış yönü; cidar sıcaklığı
       malzeme limitini aşarsa KIRMIZI rozet; RP-1 koklaşırsa KIRMIZI rozet.
     - Kartlar: tepe cidar T + marj, soğutucu çıkış T + ΔT, toplam ΔP,
       tepe ısı akısı, maks hız, min Reynolds.
     - Plotly: T_wall_hot(x) / T_wall_cold(x) / T_coolant(x) — malzeme
       izin verilen sınır çizgisi + RP-1 koklaşma çizgisi (boğaz işareti).
     - İkinci grafik: q(x) [MW/m²] sol eksen + P_coolant(x) [bar] sağ eksen.
     - Uyarılar + model notu (dürüst sınırlar).

   YALNIZ sıvı motor (motorTypes:['liquid']) — hibrit/katıda rejeneratif
   soğutma anlamsızdır.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    // FALLBACK — soğutucu tarafı cidar malzemeleri, materials_db
    // anahtarlarıyla birebir (get_material; regen_cooling.py wall_material).
    // Bakır/CuCrZr yüksek iletkenlikleriyle tipik rejeneratif liner.
    // Katalog gelirse 'liner'+'shell' etiketli tam liste bunun yerine geçer.
    const WALL_MATERIALS = [
        ['copper', 'Copper (OFHC)'],
        ['cucrzr', 'CuCrZr alloy'],
        ['inconel_718', 'Inconel 718'],
        ['ss_304', 'Stainless 304'],
        ['steel_4130', 'Steel AISI 4130'],
    ];

    const COOLANTS = [
        ['water', 'Water', 'coolant.water'],
        ['rp1', 'RP-1 (kerosene)', 'coolant.rp1'],
    ];

    const FLOW_DIRECTIONS = [
        ['counterflow', 'Counterflow (exit → chamber)', 'coolant.counterflow'],
        ['coflow', 'Co-flow (chamber → exit)', 'coolant.coflow'],
    ];

    // Tepe cidar sıcaklığının malzeme limitlerine göre önem derecesi
    function wallKind(summary) {
        const t = summary.max_wall_hot_K;
        if (typeof t !== 'number' || !Number.isFinite(t)) return 'dim';
        if (Number.isFinite(summary.material_melting_K) && t > summary.material_melting_K) return 'err';
        if (Number.isFinite(summary.material_service_limit_K) && t > summary.material_service_limit_K) return 'err';
        if (Number.isFinite(summary.material_allowable_temp_K) && t > summary.material_allowable_temp_K) return 'warn';
        return 'ok';
    }

    // ------------------------------------------------------------------
    // Sıcaklık profili: T_wall_hot / T_wall_cold / T_coolant + limit çizgileri
    // ------------------------------------------------------------------
    function temperaturePlot(root, cooling) {
        if (typeof Plotly === 'undefined') return false;
        const x = Array.isArray(cooling.x_mm) ? cooling.x_mm : [];
        if (!x.length) return false;
        const sm = cooling.summary || {};

        const traces = [];
        const sameLen = function (a) { return Array.isArray(a) && a.length === x.length; };
        if (sameLen(cooling.T_wall_hot_K)) {
            traces.push({
                x: x, y: cooling.T_wall_hot_K, name: T('panel.regen.sHotWall', 'Hot-wall T (gas side)'),
                type: 'scatter', mode: 'lines', line: { color: '#ff5d73', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall,hot = %{y:.0f} K<extra></extra>',
            });
        }
        if (sameLen(cooling.T_wall_cold_K)) {
            traces.push({
                x: x, y: cooling.T_wall_cold_K, name: T('panel.regen.sColdWall', 'Cold-wall T (coolant side)'),
                type: 'scatter', mode: 'lines', line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall,cold = %{y:.0f} K<extra></extra>',
            });
        }
        if (sameLen(cooling.T_coolant_K)) {
            traces.push({
                x: x, y: cooling.T_coolant_K, name: T('panel.regen.sCoolantBulk', 'Coolant bulk T'),
                type: 'scatter', mode: 'lines', line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>T_coolant = %{y:.0f} K<extra></extra>',
            });
        }
        if (!traces.length) return false;

        // Limit + koklaşma çizgileri (durum rengi asla "seri" değil — etiketli
        // referans çizgisi; kimlik yalnız renkle taşınmaz).
        const shapes = [];
        const annotations = [];
        function refLine(v, label, color) {
            if (typeof v !== 'number' || !Number.isFinite(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 0, y: v, xanchor: 'left', yanchor: 'bottom',
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 10, color: color },
            });
        }
        refLine(sm.material_allowable_temp_K, T('panel.regen.allowableWall', 'Allowable wall limit'), '#ff8c33');
        refLine(sm.material_melting_K, T('panel.thermal.meltingPoint', 'Melting point'), '#ff5d73');
        // RP-1 koklaşma çizgisi (yalnız RP-1: coking_threshold_K dolu)
        refLine(sm.coking_threshold_K, T('panel.regen.cokingLine', 'RP-1 coking threshold'), '#c678dd');

        // Boğaz konumu işareti
        const throatX = (typeof cooling.x_throat_mm === 'number'
            && Number.isFinite(cooling.x_throat_mm)) ? cooling.x_throat_mm : null;
        if (throatX != null) {
            shapes.push({
                type: 'line', yref: 'paper', x0: throatX, x1: throatX, y0: 0, y1: 1,
                line: { color: 'rgba(125,151,165,0.55)', width: 1, dash: 'dot' },
            });
            annotations.push({
                x: throatX, yref: 'paper', y: 1, xanchor: 'left', yanchor: 'top',
                text: T('common.throat', 'Throat'), showarrow: false, font: { size: 10, color: '#7d97a5' },
            });
        }

        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);
        Plotly.newPlot(div, traces, {
            title: T('panel.regen.chartTemps',
                'Wall & Coolant Temperatures Along the Chamber-Nozzle Axis'),
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.temperatureK', 'Temperature (K)'), rangemode: 'tozero' },
            shapes: shapes,
            annotations: annotations,
            legend: { orientation: 'h' },
            height: 380,
        }, { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Isı akısı q(x) + soğutucu basıncı P(x) (ikincil eksen)
    // ------------------------------------------------------------------
    function fluxPressurePlot(root, cooling) {
        if (typeof Plotly === 'undefined') return false;
        const x = Array.isArray(cooling.x_mm) ? cooling.x_mm : [];
        if (!x.length) return false;
        const sameLen = function (a) { return Array.isArray(a) && a.length === x.length; };
        const traces = [];
        if (sameLen(cooling.q_MW_m2)) {
            traces.push({
                // ADLANDIRMA (v2.6.27, parti 20): bu seri termal panelin
                // q(x) serisiyle AYNI anahtarı kullanıyordu ama tanımı
                // farklı — burada akı KUPLE cidar dengesinden çözülür
                // (regen_cooling.py::_station_wall_balance, q = (T_aw −
                // T_soğutucu)/(1/h_g + t_c/k_c + 1/h_c)); sıcak cidar
                // sıcaklığı sonuçtur, sabit bir referans değil. Ölçüldü
                // (panel varsayılanları, boğaz): 28,50 MW/m², T_wall_hot
                // 1263 K — termal panelin referans-cidar tasarım yükü aynı
                // sınıfta 24,1-26,0 MW/m². Tek anahtar iki tanımı taşıyamaz.
                x: x, y: cooling.q_MW_m2, name: T('panel.regen.heatFluxSeriesBalance', 'Heat flux q (coupled wall balance)'),
                type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²<extra></extra>',
            });
        }
        if (sameLen(cooling.P_coolant_bar)) {
            traces.push({
                x: x, y: cooling.P_coolant_bar, name: T('panel.regen.sCoolantP', 'Coolant pressure'),
                type: 'scatter', mode: 'lines', yaxis: 'y2',
                line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>P = %{y:.2f} bar<extra></extra>',
            });
        }
        if (!traces.length) return false;
        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);
        Plotly.newPlot(div, traces, {
            title: T('panel.regen.chartFlux', 'Heat Flux & Coolant Pressure'),
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.heatFlux', 'Heat flux (MW/m²)'), rangemode: 'tozero' },
            yaxis2: { title: T('panel.regen.axisCoolantP', 'Coolant pressure (bar)'),
                      overlaying: 'y', side: 'right', showgrid: false },
            legend: { orientation: 'h' },
            height: 320,
        }, { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Ana render
    // ------------------------------------------------------------------
    function render(data, root) {
        const cooling = (data && data.cooling) || {};
        const sm = cooling.summary || {};

        // ---- Rozetler ----
        let badges = '';
        badges += U.badge(T('panel.regen.badgeCoolant', 'COOLANT') + ': '
            + String(sm.coolant || '—').toUpperCase(), 'info');
        badges += U.badge(T('panel.regen.badgeLiner', 'LINER') + ': '
            + String(sm.wall_material_name || sm.wall_material || '—'),
            'info', T('panel.regen.linerTip', 'Regenerative liner material (k_w, temperature limits)'));
        badges += U.badge(T('panel.regen.badgeFlow', 'FLOW') + ': '
            + String(sm.flow_direction || '—').toUpperCase(), 'dim');

        const wk = wallKind(sm);
        if (wk === 'err') {
            badges += U.badge(T('panel.regen.wallOver', 'WALL OVER LIMIT'), 'err',
                T('panel.regen.wallOverTip',
                  'Peak hot-wall temperature exceeds the material service/melting limit — '
                  + 'liner failure; increase coolant flow, change material or resize channels.'));
        } else if (wk === 'warn') {
            badges += U.badge(T('panel.regen.wallNear', 'WALL NEAR LIMIT'), 'warn',
                T('panel.regen.wallNearTip',
                  'Peak hot-wall temperature exceeds the allowable (strength) limit — margin reduced.'));
        } else if (wk === 'ok') {
            badges += U.badge(T('panel.regen.wallWithin', 'WALL WITHIN LIMIT'), 'ok', '');
        }
        if (sm.coking) {
            badges += U.badge(T('panel.regen.coking', 'RP-1 COKING'), 'err',
                T('panel.regen.cokingTip',
                  'Coolant-side wall temperature exceeds the ~561 K RP-1 coking threshold — '
                  + 'carbon deposition and channel fouling likely (Huzel & Huang Ch. 4).'));
        }

        // ---- Sayısal kartlar ----
        const marginKind = (typeof sm.wall_temp_margin_K === 'number'
            && Number.isFinite(sm.wall_temp_margin_K))
            ? (sm.wall_temp_margin_K < 0 ? 'err' : (sm.wall_temp_margin_K < 100 ? 'warn' : 'ok'))
            : 'dim';
        const head = document.createElement('div');
        head.innerHTML = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`
            + `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.regen.cardPeakWall', 'PEAK WALL T'), U.fmt(sm.max_wall_hot_K, 0), 'K', wk,
                U.tf('panel.regen.cardPeakWallTip', { x: U.fmt(sm.max_wall_hot_x_mm, 1) },
                     'Peak hot-wall (gas side) temperature at x = {x} mm'))
            + U.statCard(T('panel.regen.cardMargin', 'WALL MARGIN'), U.fmt(sm.wall_temp_margin_K, 0), 'K', marginKind,
                T('panel.regen.cardMarginTip', 'Allowable limit − peak wall temperature'))
            + U.statCard(T('panel.regen.cardExitT', 'COOLANT EXIT T'), U.fmt(sm.coolant_exit_temp_K, 0), 'K', 'info',
                T('panel.regen.cardExitTip', 'Coolant bulk temperature at the outlet'))
            + U.statCard(T('panel.regen.cardDeltaT', 'COOLANT ΔT'), U.fmt(sm.coolant_dT_K, 0), 'K', 'dim',
                T('panel.regen.cardDeltaTip', 'Total coolant temperature rise (enthalpy balance)'))
            + U.statCard(T('panel.regen.cardDrop', 'PRESSURE DROP'), U.fmt(sm.total_pressure_drop_bar, 2), 'bar', 'info',
                T('panel.regen.cardDropTip', 'Darcy-Weisbach + Haaland friction across the channels'))
            + U.statCard(T('panel.regen.cardPeakFluxBalance', 'PEAK HEAT FLUX (coupled wall balance)'),
                U.fmt(sm.peak_heat_flux_MW_m2, 2), 'MW/m²', 'dim',
                T('panel.regen.cardPeakFluxTip',
                  'Peak of the coupled gas/wall/coolant station balance '
                  + 'q = (T_aw - T_coolant)/(1/h_g + t_w/k_w + 1/h_c); the '
                  + 'hot-wall temperature is solved, not a fixed reference'))
            + U.statCard(T('panel.regen.cardMaxV', 'MAX VELOCITY'), U.fmt(sm.max_coolant_velocity_m_s, 1), 'm/s', 'dim', '')
            + U.statCard(T('panel.regen.cardMinRe', 'MIN REYNOLDS'), U.fmt(sm.min_reynolds, 0), '', 'dim',
                T('panel.regen.cardMinReTip',
                  'Minimum channel Reynolds number (Dittus-Boelter turbulent floor ~1e4)'))
            + '</div>';
        root.appendChild(head);

        // ---- Grafikler ----
        temperaturePlot(root, cooling);
        fluxPressurePlot(root, cooling);

        // ---- Uyarılar + model notu ----
        const tail = document.createElement('div');
        let html = '';
        if (Array.isArray(sm.warnings) && sm.warnings.length) {
            html += U.listBlock(T('common.warnings', 'Warnings'), sm.warnings, 'warn');
        }
        if (cooling.model_note) {
            html += U.listBlock(T('common.modelAssumptions', 'Model assumptions & limits'),
                                [cooling.model_note], 'dim');
        }
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    // ------------------------------------------------------------------
    // Kayıt
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: 'cooling',
        title: 'Regenerative Cooling — 1D Station March (Bartz + Dittus-Boelter)',
        titleKey: 'panel.regen.title',
        category: 'THERMAL',
        endpoint: '/api/regen-cooling',
        motorTypes: ['liquid'],
        long: true,
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 50, 1, 'common.f.chamberPressureBar'],
            ['chamber_temperature', 'Chamber Temperature (K)', 3400, 10, 'common.f.chamberTemperatureK'],
            ['throat_diameter', 'Throat Diameter (m)', 0.05, 0.001, 'common.f.throatDiameterM'],
            ['expansion_ratio', 'Expansion Ratio', 8, 0.1, 'common.f.expansionRatio'],
            ['gamma', 'Gamma (frozen)', 1.2, 0.01, 'common.f.gammaFrozen'],
            ['molecular_weight', 'Molecular Weight (g/mol)', 22, 0.5, 'common.f.molecularWeight'],
            ['coolant', 'Coolant', 'water', COOLANTS, 'panel.regen.fCoolant'],
            ['coolant_mdot', 'Coolant Mass Flow (kg/s)', 2.0, 0.05, 'panel.regen.fCoolantMdot'],
            ['coolant_inlet_temp', 'Coolant Inlet T (K)', 300, 5, 'panel.regen.fInletT'],
            ['coolant_inlet_pressure', 'Coolant Inlet P (bar)', 60, 1, 'panel.regen.fInletP'],
            ['n_channels', 'Number of Channels', 80, 1, 'panel.regen.fChannels'],
            ['channel_width', 'Channel Width (mm)', 2.0, 0.1, 'panel.regen.fChannelW'],
            ['channel_height', 'Channel Height (mm)', 3.0, 0.1, 'panel.regen.fChannelH'],
            ['wall_thickness', 'Liner Thickness (mm)', 1.0, 0.1, 'panel.regen.fLinerThickness'],
            ['wall_material', 'Liner Material', 'copper', WALL_MATERIALS, 'panel.regen.fLinerMaterial'],
            ['flow_direction', 'Flow Direction', 'counterflow', FLOW_DIRECTIONS, 'panel.regen.fFlowDir'],
        ],
        // Sıvı motor sonuçlarından otomatik dolum: soğutucu = yakıt akışı.
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const sug = {};
            if (Number.isFinite(m.chamber_pressure)) sug.chamber_pressure = m.chamber_pressure;
            if (Number.isFinite(m.chamber_temperature)) sug.chamber_temperature = m.chamber_temperature;
            // BİRİM: alan METRE etiketli; katı motorda throat_diameter
            // 17,96 (mm) geliyordu ve panel 17,96 m boğaz çapıyla hesap
            // yapıyordu. Merkezi çözümleyici metreye getiriyor.
            const dtM = U.readLengthM(r, 'throat_diameter');
            if (Number.isFinite(dtM)) sug.throat_diameter = dtM;
            if (Number.isFinite(m.expansion_ratio) && m.expansion_ratio > 1) {
                sug.expansion_ratio = m.expansion_ratio;
            }
            if (Number.isFinite(m.gamma)) sug.gamma = m.gamma;
            if (Number.isFinite(m.molecular_weight)) sug.molecular_weight = m.molecular_weight;
            // Rejeneratif soğutucu tipik olarak yakıttır → yakıt debisini öner.
            // Eski kod 'fuel_flow' (yalnız sıvıda var) ve 'mdot_fuel' (HİÇBİR
            // çözücüde yok) anahtarlarını arıyordu; hibritin gerçek anahtarı
            // 'mdot_f'. Hibritte alan 2,0 kg/s panel varsayılanında kalıyordu,
            // gerçek yakıt debisi 0,158 kg/s — 12,6 kat fazla soğutucu.
            const mdotFuel = U.readFuelFlow(r);
            if (Number.isFinite(mdotFuel) && mdotFuel > 0) sug.coolant_mdot = mdotFuel;
            return sug;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse liner select'ini 'liner'+'shell' etiketli
    // listeyle doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'cooling', fieldId: 'wall_material',
            tags: ['liner', 'shell'], fallback: WALL_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render + çizim yardımcıları
    window.CoolingPanel = {
        _render: render,
        _temperaturePlot: temperaturePlot,
        _fluxPressurePlot: fluxPressurePlot,
        _wallKind: wallKind,
    };
})();
