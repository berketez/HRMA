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
    const T = U.t;                       // çeviri kısayolu (i18n yoksa İngilizce yedek)

    const ENDPOINT = '/api/advanced-performance-analysis';

    // Ana POST (dock) → 3d_surface; bunlar render içinde ek olarak çekilir
    const EXTRA_FIGURES = [
        ['nozzle_mach', 'panel.performance.figMach', 'Nozzle Mach–Area Ratio Contour'],
        ['heat_flux', 'panel.performance.figHeat', 'Wall Heat Flux Waterfall'],
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

    // ------------------------------------------------------------------
    // Birim sözleşmesi (2026-07-19 Codex denetimi, bulgu 5)
    // ------------------------------------------------------------------
    // Üst seviye motor sonuçları tipe göre FARKLI birim kullanır:
    //   katı   : throat_diameter 47.93 -> MİLİMETRE
    //   sıvı   : chamber_length 97.96  -> MİLİMETRE, throat_diameter METRE
    //   hibrit : hepsi METRE
    // Panel hepsini SI sanıyordu: sıvıda kamara 1000 kat uzun, katıda boğaz
    // alanı 10^6 kat büyük gidiyordu. Tek doğruluk kaynağı normalize
    // `motor_geometry` bloğu (SI); yoksa büyüklükten çıkarım yapılır —
    // eşikler Python tarafıyla aynı (hrma/export/openrocket_integration.py).
    const DIAMETER_SI_MAX_M = 1.0;
    const LENGTH_SI_MAX_M = 5.0;

    function siLength(value, siMax) {
        const v = Number(value);
        if (!Number.isFinite(v) || v <= 0) return null;
        return v > siMax ? v / 1000 : v;      // > eşik ise değer milimetredir
    }

    // motor_geometry varsa oradan (SI garantili), yoksa çıkarımla
    function geoLength(m, geo, key, siMax) {
        if (geo && Number.isFinite(geo[key]) && geo[key] > 0) return geo[key];
        return siLength(m[key], siMax);
    }

    // İlk sonlu pozitif değer (üretici/tüketici anahtar adı farkları için)
    function firstFinite(obj, keys) {
        for (let i = 0; i < keys.length; i++) {
            const v = Number(obj[keys[i]]);
            if (Number.isFinite(v)) return v;
        }
        return null;
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
            block.status.textContent = T('common.badPayload',
                'Unexpected plot payload from backend.');
            return false;
        }
        if (typeof Plotly === 'undefined') {
            block.status.textContent = T('common.plotlyMissing',
                'Plotly is not loaded — chart skipped.');
            return false;
        }
        Plotly.newPlot(block.plot, fig.data, fig.layout || {},
            { responsive: true, displaylogo: false });
        block.status.textContent = '';
        return true;
    }

    // Ek figürleri (nozzle_mach / heat_flux) formdaki güncel değerlerle çek
    async function fetchExtraFigure(analysisType, headingKey, headingEn, root) {
        const block = figureBlock(root, T(headingKey, headingEn));
        block.status.textContent = T('common.loading', 'LOADING…');
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
                block.status.textContent = T('common.backendUpdating',
                    'Backend updating — this figure will be available after the server reloads.');
                return;
            }
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            drawResponse(block, data);
        } catch (err) {
            block.status.textContent = U.tf('common.errorPrefix',
                { message: err.message }, 'ERROR: {message}');
        }
    }

    function render(data, root) {
        // 1) Dock'un kendi POST yanıtı — 3D performans yüzeyi
        const main = figureBlock(root, T('panel.performance.figSurface',
            '3D Performance Surface — Isp vs Chamber Pressure & O/F'));
        drawResponse(main, data);

        // 2) Kalan iki hazır figür ayrı çağrılarla (paralel) gelir
        EXTRA_FIGURES.forEach(function (f) {
            fetchExtraFigure(f[0], f[1], f[2], root);
        });
    }

    window.AnalysisDock.register({
        id: 'performance',
        title: 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
        titleKey: 'panel.performance.title',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 50, 1, 'common.f.chamberPressureBar'],
            ['optimal_of_ratio', 'Optimal O/F Ratio', 3.5, 0.1, 'common.f.optimalOf'],
            ['base_isp', 'Base Isp (s)', 300, 5, 'common.f.baseIsp'],
            ['expansion_ratio', 'Expansion Ratio', 16, 0.5, 'common.f.expansionRatio'],
            ['throat_area', 'Throat Area (m²)', 0.001, 0.0001, 'common.f.throatAreaM2'],
            ['nozzle_length', 'Nozzle Length (m)', 0.1, 0.01, 'common.f.nozzleLengthM'],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01, 'common.f.chamberLengthM'],
            ['burn_time', 'Burn Time (s)', 30, 0.5, 'common.f.burnTimeS'],
            ['base_heat_flux', 'Base Heat Flux (W/m²)', 2000000, 100000, 'common.f.baseHeatFlux'],
            ['critical_heat_flux', 'Critical Heat Flux (MW/m²)', 4.0, 0.5, 'common.f.criticalHeatFlux'],
            // Bartz ısı akısı çözücüsünün gaz hâli girdileri (bulgu 6): bunlar
            // gönderilmediğinde backend 3000 K / gamma 1.2 / 1 kg/s
            // varsayılanlarına düşüyor ve farklı itergaçlar aynı grafiği veriyordu.
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 50, 'common.f.chamberTemperatureK'],
            ['gamma', 'Gamma (frozen)', 1.2, 0.01, 'common.f.gammaFrozen'],
            ['mdot_total', 'Total Mass Flow (kg/s)', 1.0, 0.1, 'common.f.mdotTotal'],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.01, 'common.f.chamberDiameterM'],
        ],
        fromResults: fromResults,
        render: render,
    });

    // Saf eşleme: motor sonucu -> form alanları. register() içindeki anonim
    // fonksiyondan çıkarıldı ki test doğrudan çağırabilsin.
    function fromResults(r) {
        const m = (r && r.motor) || r || {};
        const geo = (m.motor_geometry && typeof m.motor_geometry === 'object')
            ? m.motor_geometry : null;
        const sug = {
            chamber_pressure: m.chamber_pressure,
            burn_time: m.burn_time,
            expansion_ratio: m.expansion_ratio,
            chamber_temperature: m.chamber_temperature,
            gamma: m.gamma,
        };
        // O/F: üretici anahtar adları tipe göre değişir (bulgu 4) —
        // hibrit of_ratio, sıvı mixture_ratio / optimal_mixture_ratio.
        const of = firstFinite(m, ['of_ratio', 'mixture_ratio',
                                   'optimal_mixture_ratio']);
        if (of !== null) sug.optimal_of_ratio = of;

        // Uzunluklar SI'ya normalize edilir (bulgu 5)
        const chamberL = geoLength(m, geo, 'chamber_length', LENGTH_SI_MAX_M);
        if (chamberL !== null) sug.chamber_length = chamberL;
        const chamberD = geoLength(m, geo, 'chamber_diameter', DIAMETER_SI_MAX_M);
        if (chamberD !== null) sug.chamber_diameter = chamberD;

        // base_isp: doğrudan isp (sıvıda isp_sea_level, katıda
        // specific_impulse); yoksa F/(ṁ·g0) türetilir
        const isp = firstFinite(m, ['isp', 'specific_impulse', 'isp_sea_level']);
        const thrust = firstFinite(m, ['thrust', 'average_thrust']);
        const mdot = firstFinite(m, ['mdot_total', 'total_mass_flow']);
        if (isp !== null) {
            sug.base_isp = isp;
        } else if (thrust !== null && mdot !== null && mdot > 0) {
            sug.base_isp = Number((thrust / (mdot * 9.80665)).toPrecision(5));
        }
        // Kütle debisi: yoksa Isp tanımından türetilir (ṁ = F/(Isp·g0))
        if (mdot !== null && mdot > 0) {
            sug.mdot_total = mdot;
        } else if (thrust !== null && isp !== null && isp > 0) {
            sug.mdot_total = Number((thrust / (isp * 9.80665)).toPrecision(6));
        }
        // Backend alan (m²) ister; sonuçta çap var → A = π d²/4
        const throatD = geoLength(m, geo, 'throat_diameter', DIAMETER_SI_MAX_M);
        if (throatD !== null) {
            sug.throat_area = Number(
                (Math.PI * throatD * throatD / 4).toPrecision(6));
        }
        return sug;
    }

    // Test / hata ayıklama: saf yardımcılar (injector_panel deseni)
    window.PerformancePanel = {
        _render: render,
        _parseFigure: parseFigure,
        _readFormPayload: readFormPayload,
        _siLength: siLength,
        // Birim sözleşmesi testi (tests/test_unit_contract.py) bu saf
        // fonksiyonu gerçek motor yanıtı üzerinde node ile çalıştırır.
        _fromResults: fromResults,
    };
})();
