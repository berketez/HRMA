/* ====================================================================
   HRMA Analiz Güvertesi — Gelişmiş Performans Paneli
   --------------------------------------------------------------------
   POST /api/advanced-performance-analysis sonuçlarını çizer.
   Endpoint çağrı başına TEK figür üretir (analysis_type seçicili):
   - 3d_surface  : Pc – O/F – Isp yüzeyi (NASA SP-125)
   - nozzle_mach : Mach–alan oranı konturu (NASA-STD-5012)
   - heat_flux   : cidar ısı akısı şelalesi (NASA SP-8124)
   Dock'un kendi POST'u analysis_type göndermez → backend varsayılanı
   3d_surface döner; kalan iki figür render içinde ayrıca çekilir.
   Yanıt şeması (test_client ile doğrulandı, 2026-07-14):
     { status:'success', plot_data:'<JSON string {data,layout}>',
       analysis_info:{ title, reference, description } }
   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;

    const ENDPOINT = '/api/advanced-performance-analysis';

    // Ana POST (dock) → 3d_surface; bunlar render içinde ek olarak çekilir
    const EXTRA_FIGURES = [
        ['nozzle_mach', 'Nozzle Mach–Area Ratio Contour'],
        ['heat_flux', 'Wall Heat Flux Waterfall'],
    ];

    // ------------------------------------------------------------------
    // Dock buildPayload aynası: POST gövdesi HER ZAMAN formdan okunur
    // (panel dock dosyasına dokunmadan aynı sözleşmeyi uygular)
    // ------------------------------------------------------------------
    function readFormPayload() {
        const payload = {};
        const sec = document.getElementById('ad_sec_performance');
        if (!sec) return payload;
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') {
                payload[key] = el.value;
                return;
            }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) payload[key] = v;
        });
        return payload;
    }

    // plot_data backend'den JSON *string* gelir (PlotlyJSONEncoder);
    // obje gelirse de tolere edilir. Geçersiz payload → null.
    function parseFigure(pd) {
        try {
            const fig = (typeof pd === 'string') ? JSON.parse(pd) : pd;
            if (fig && Array.isArray(fig.data)) return fig;
        } catch (e) { /* aşağıda null */ }
        return null;
    }

    function infoCard(info) {
        if (!info || (!info.title && !info.description)) return '';
        return `<div style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
            border-left:3px solid var(--hd-cyan, #00e5ff);
            border-radius:var(--hd-radius-sm, 8px); padding:10px 14px; margin:8px 0;
            background:var(--hd-inset, rgba(6,14,26,0.85));">
            <strong style="color:var(--hd-ink-strong, #eaf7fb);">${info.title || ''}</strong>
            <div style="font-family:var(--hd-mono); font-size:0.7rem;
                 color:var(--hd-ink-dim, #7d97a5); margin:2px 0;">${info.reference || ''}</div>
            <p style="margin:6px 0 0; font-size:0.8rem;
               color:var(--hd-ink, #cfe8f2);">${info.description || ''}</p>
        </div>`;
    }

    // Bir figür bloğu: başlık + durum satırı + bilgi kartı alanı + grafik
    function figureBlock(root, heading) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(heading);
        const status = document.createElement('div');
        status.style.cssText = 'font-family:var(--hd-mono); font-size:0.78rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:4px 0;';
        const info = document.createElement('div');
        const plot = document.createElement('div');
        wrap.appendChild(status);
        wrap.appendChild(info);
        wrap.appendChild(plot);
        root.appendChild(wrap);
        return { wrap: wrap, status: status, info: info, plot: plot };
    }

    // Yanıtı bloğa çizer; başarıysa true
    function drawResponse(block, resp) {
        block.info.innerHTML = infoCard(resp && resp.analysis_info);
        const fig = parseFigure(resp && resp.plot_data);
        if (!fig) {
            block.status.textContent = 'Unexpected plot payload from backend.';
            return false;
        }
        if (typeof Plotly === 'undefined') {
            block.status.textContent = 'Plotly is not loaded — chart skipped.';
            return false;
        }
        Plotly.newPlot(block.plot, fig.data, fig.layout || {},
            { responsive: true, displaylogo: false });
        block.status.textContent = '';
        return true;
    }

    // Ek figürleri (nozzle_mach / heat_flux) formdaki güncel değerlerle çek
    async function fetchExtraFigure(analysisType, heading, root) {
        const block = figureBlock(root, heading);
        block.status.textContent = 'LOADING…';
        try {
            const payload = readFormPayload();
            payload.analysis_type = analysisType;
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.status === 404 || resp.status === 501) {
                // Zarif düşüş: endpoint geçici yoksa panel kırılmaz
                block.status.textContent =
                    'Backend updating — this figure will be available after the server reloads.';
                return;
            }
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            drawResponse(block, data);
        } catch (err) {
            block.status.textContent = 'ERROR: ' + err.message;
        }
    }

    function render(data, root) {
        // 1) Dock'un kendi POST yanıtı — 3D performans yüzeyi
        const main = figureBlock(root,
            '3D Performance Surface — Isp vs Chamber Pressure & O/F');
        drawResponse(main, data);

        // 2) Kalan iki hazır figür ayrı çağrılarla (paralel) gelir
        EXTRA_FIGURES.forEach(function (f) {
            fetchExtraFigure(f[0], f[1], root);
        });
    }

    window.AnalysisDock.register({
        id: 'performance',
        title: 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 50, 1],
            ['optimal_of_ratio', 'Optimal O/F Ratio', 3.5, 0.1],
            ['base_isp', 'Base Isp (s)', 300, 5],
            ['expansion_ratio', 'Expansion Ratio', 16, 0.5],
            ['throat_area', 'Throat Area (m²)', 0.001, 0.0001],
            ['nozzle_length', 'Nozzle Length (m)', 0.1, 0.01],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01],
            ['burn_time', 'Burn Time (s)', 30, 0.5],
            ['base_heat_flux', 'Base Heat Flux (W/m²)', 2000000, 100000],
            ['critical_heat_flux', 'Critical Heat Flux (MW/m²)', 4.0, 0.5],
        ],
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const sug = {
                chamber_pressure: m.chamber_pressure,
                optimal_of_ratio: m.of_ratio,
                burn_time: m.burn_time,
                expansion_ratio: m.expansion_ratio,
                chamber_length: m.chamber_length,
            };
            // base_isp: doğrudan isp; yoksa F/(ṁ·g0) türetilir
            if (Number.isFinite(m.isp)) {
                sug.base_isp = m.isp;
            } else if (Number.isFinite(m.thrust) && Number.isFinite(m.mdot_total)
                       && m.mdot_total > 0) {
                sug.base_isp = Number((m.thrust / (m.mdot_total * 9.80665)).toPrecision(5));
            }
            // Backend alan (m²) ister; sonuçta çap (m) var → A = π d²/4
            if (Number.isFinite(m.throat_diameter)) {
                sug.throat_area = Number(
                    (Math.PI * m.throat_diameter * m.throat_diameter / 4).toPrecision(6));
            }
            return sug;
        },
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (injector_panel deseni)
    window.PerformancePanel = {
        _render: render,
        _parseFigure: parseFigure,
        _readFormPayload: readFormPayload,
    };
})();
