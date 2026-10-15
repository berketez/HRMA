/* ====================================================================
   HRMA Analiz Güvertesi — Gelişmiş Performans Paneli
   --------------------------------------------------------------------
   POST /api/advanced-performance-analysis sonuçlarını çizer.
   Endpoint çağrı başına TEK figür üretir (analysis_type seçicili):
   - 3d_surface  : Pc – O/F – Isp yüzeyi (kimyasal denge çözücüsü)
   - nozzle_mach : Mach–alan oranı konturu (NACA Rapor 1135 / Anderson,
                   "Modern Compressible Flow" — nozzle_flow_1d.py:12-26)
   - heat_flux   : cidar ısı akısı şelalesi (Bartz 1957; NASA SP-8124
                   "Liquid Rocket Engine Self-Cooled Combustion Chambers")
   DENETİM DÜZELTMESİ (2026-08-02, C2/C3): bu blok Mach–alan konturunun
   kaynağı olarak NASA-STD-5012 yazıyordu. O belgenin gerçek adı "Strength
   and Life Assessment Requirements for Liquid-Fueled Space Propulsion
   System Engines" (Rev. B, 2016) — bir mukavemet/ömür standardı; içinde
   gaz dinamiği bağıntısı yok. SP-8124 de "Thermal Design Criteria" değil.
   Doğrulanmış başlıklar: docs/STANDART_ATIFLARI.md.
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

    // Motorun itici kimliği (fromResults'ta yakalanır, her istekte eklenir).
    // Form alanı DEĞİL: kullanıcı elle giremez, dolayısıyla motorla çelişemez.
    let sonIticiler = { fuel_type: null, oxidizer_type: null };

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
        // İtici kimliği (T18): bilinmiyorsa GÖNDERİLMEZ — uydurma bir çift
        // yollamaktansa uç kendi referans çiftine düşsün ve bunu beyan etsin.
        if (sonIticiler.fuel_type) payload.fuel_type = sonIticiler.fuel_type;
        if (sonIticiler.oxidizer_type) payload.oxidizer_type = sonIticiler.oxidizer_type;
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
    // `motor_geometry` bloğudur (her alan SI).
    //
    // ÖH D33-2 / arayuz-panel a1 · kalem OH-D32-01 (defter zinciri P7B1-06)
    // -------------------------------------------------------------------
    // BURADA İKİNCİ BİR BANT DURUYORDU: çap tavanı 1,0 m ve boy tavanı
    // 5,0 m elle yazılıydı, blok yoksa "değer tavanın üstündeyse değer
    // milimetredir" diye ÇIKARIM yapılıyordu. ÖLÇÜLDÜ (a1/once.json,
    // bölüm K1): bu iki sayı doğrulayıcının KENDİ kanonuyla ayrışıyordu —
    // motor_validation.DIAMETER_UNIT_INFERENCE_MAX_M 5,0 m ve
    // LENGTH_UNIT_INFERENCE_MAX_M 20,0 m (ikisi de CANONICAL_LIMITS
    // tablosundan TÜRETİLİR, elle yazılmaz). Aradaki boşlukta kalan meşru
    // ölçüler panelde 1000 kat küçülüyordu:
    //
    //     girdi (kanonik bant içi)   panel okudu     sunucu okur
    //     chamber_diameter 1,5 m     0,0015 m        1,5 m
    //     chamber_length   6,0 m     0,006 m         6,0 m
    //     throat_diameter  1,2 m  -> alan 1,131e-6 m²  1,131 m² (10^6 kat)
    //
    // Bandı arayüze yayımlayan bir uç YOK (/api/limits benzeri uç
    // app-api-uc kulvarına devredildi — bkz. a1/rapor.md). Bandın ikinci
    // kopyası TAŞINMAZ ve sayı UYDURULMAZ; birim çözümü ürünün MEVCUT tek
    // kaynağına devredilir (aşağıdaki geoLength).
    // Canlı yolda kayıp yoktur: ÖLÇÜLDÜ (a1/once.json, K1) üç motor
    // tipinin /calculate ailesi de `motor_geometry` bloğunu
    // chamber_length / chamber_diameter / throat_diameter ile yayımlıyor.
    // Blok GELMEYEN yol da ölçüldü: ham `HybridRocketEngine.calculate()`
    // sonucu `motor_geometry` taşımaz (üst seviye metre) ve tamamen silmek
    // tests/test_unit_contract.py::TestPerformancePanelUnits::
    // test_throat_area_and_chamber_length_are_physical[hybrid] bekçisini
    // kırıyordu — yani gerçek bir yeteneği düşürüyordu. Güvertenin
    // ölçülmüş birim tablosuna devir hem kusuru hem o kaybı kapatır.

    //: Bu turda birimi ÇÖZÜLEMEYEN alan adları — sessiz yedek yerine ADLI
    //: yokluk. Test yüzeyi bunu `_unresolvedGeometry()` ile okur.
    let birimiCozulemeyenAlanlar = [];

    // Birim çözümü İKİ TEK-KAYNAKTAN gelir, panelden ASLA:
    //   1) normalize `motor_geometry` bloğu (her alan SI — uç garanti eder),
    //   2) güvertenin MERKEZİ birim sözleşmesi
    //      (`analysis_dock.js::readLengthM`, motor tipine göre ÖLÇÜLMÜŞ
    //      `LENGTH_UNITS` tablosu — hibrit 'm', katı 'mm', sıvıda alan alan).
    // İkisi de konuşmuyorsa alan ÖNERİSİZ kalır ve adı beyan edilir.
    // Büyüklükten çıkarım (eski `siLength`) YOK: bir sayının kaç olduğu
    // birimini söylemez.
    function geoLength(m, geo, key, r) {
        if (geo && Number.isFinite(geo[key]) && geo[key] > 0) return geo[key];
        if (U && typeof U.readLengthM === 'function') {
            const v = U.readLengthM(r, key);
            if (typeof v === 'number' && Number.isFinite(v) && v > 0) return v;
        }
        if (m && m[key] !== undefined && m[key] !== null
                && birimiCozulemeyenAlanlar.indexOf(key) < 0) {
            birimiCozulemeyenAlanlar.push(key);
        }
        return null;
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

    // ------------------------------------------------------------------
    // ÖH D37 A1a pdf-grafik-step · CW-SU6 — KATIDA O/F HARİTASI İSTENMEZ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (``docs/scofield/raw/OH/A1a/pdf-grafik-step/a1/once.json``
    // K4): panel üç motor tipine de kaydoluyordu ve güvertenin POST'u
    // `analysis_type` göndermediği için uç her Çalıştır'da 3B yüzeyi
    // (Isp – Pc – O/F) döndürüyordu — katı sayfasında da. Önceden
    // karıştırılmış katı itici için O/F bir tasarım değişkeni DEĞİLDİR;
    // katının iticisi yakıt/oksitleyici çifti de taşımadığından yüzey uç
    // tarafında referans çiftine düşüyordu. Sunucu motor tipini göremez
    // (`app.py` `engine_data` gövdesinde `motor_type` yok) → karar istemcide:
    //   * hibrit/sıvı: 'performance' kaydı AYNEN (yüzey + iki ek figür);
    //   * katı: ayrı kayıt; güvertenin POST'u `analysis_type` seçicisiyle
    //     gider (Mach konturu / ısı akısı), yüzey HİÇ istenmez ve yerinde
    //     gri + neden durur. Yalnız yüzeyi besleyen iki alan (O/F, taban
    //     Isp — `app.py` 3d_surface `engine_data`) katı formunda yok.
    const SURFACE_ONLY_FIELDS = ['optimal_of_ratio', 'base_isp'];
    const SOLID_OF_NA_EN = 'The 3D performance surface (Isp vs chamber '
        + 'pressure and O/F) is not drawn for a solid motor: O/F is not a '
        + 'design variable of a premixed solid propellant — its oxidizer-to-'
        + 'fuel ratio is fixed by the propellant formulation. The figure was '
        + 'not requested.';
    // Seçici seçenekleri güvertenin biçiminde: [değer, etiket, etiketAnahtarı]
    const SOLID_FIGURES = EXTRA_FIGURES.map(function (f) {
        return [f[0], f[2], f[1]];
    });

    function selectedSolidFigure() {
        const sec = document.getElementById('ad_sec_performance_solid');
        const el = sec && sec.querySelector
            ? sec.querySelector('[data-field="analysis_type"]') : null;
        const v = el ? el.value : null;
        for (let i = 0; i < SOLID_FIGURES.length; i++) {
            if (SOLID_FIGURES[i][0] === v) return SOLID_FIGURES[i];
        }
        return null;
    }

    function renderSolid(data, root) {
        // 1) Yüzeyin yerinde gri + neden — figür istenmedi, çizilmez.
        const na = document.createElement('div');
        na.setAttribute('data-perf-na', 'of_surface');
        na.style.cssText = 'border:1px dashed var(--hd-line, rgba(125,151,165,0.45));'
            + ' border-radius:var(--hd-radius-sm, 8px); padding:10px 14px;'
            + ' margin:8px 0; color:var(--hd-ink-dim, #7d97a5); font-size:0.8rem;';
        na.innerHTML = U.sectionTitle(T('panel.performance.figSurface',
            '3D Performance Surface — Isp vs Chamber Pressure & O/F'));
        const neden = document.createElement('p');
        neden.style.margin = '6px 0 0';
        neden.textContent = T('panel.performance.solidOfNa', SOLID_OF_NA_EN);
        na.appendChild(neden);
        root.appendChild(na);
        // 2) Güvertenin POST'u seçilen figürü döndürdü.
        const secim = selectedSolidFigure();
        const baslik = secim ? T(secim[2], secim[1])
            : ((data && data.analysis_info && data.analysis_info.title)
               || T('panel.performance.titleSolid',
                    'Advanced Performance — Mach Contour, Heat Flux'));
        drawResponse(figureBlock(root, baslik), data);
    }

    const PERF_FIELDS = [
            ['chamber_pressure', 'Chamber Pressure (bar)', 50, 1, 'common.f.chamberPressureBar'],
            ['optimal_of_ratio', 'Optimal O/F Ratio', 3.5, 0.1, 'common.f.optimalOf'],
            ['base_isp', 'Base Isp (s)', 300, 5, 'common.f.baseIsp'],
            ['expansion_ratio', 'Expansion Ratio', 16, 0.5, 'common.f.expansionRatio'],
            ['throat_area', 'Throat Area (m²)', 0.001, 0.0001, 'common.f.throatAreaM2'],
            ['nozzle_length', 'Nozzle Length (m)', 0.1, 0.01, 'common.f.nozzleLengthM'],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01, 'common.f.chamberLengthM'],
            ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS'], // OH-D37-S6: süre uydurulmaz — boşsa gövdeye girmez (safety_panel.js deseni)
            ['base_heat_flux', 'Base Heat Flux (W/m²)', 2000000, 100000, 'common.f.baseHeatFlux'],
            ['critical_heat_flux', 'Critical Heat Flux (MW/m²)', 4.0, 0.5, 'common.f.criticalHeatFlux'],
            // Bartz ısı akısı çözücüsünün gaz hâli girdileri (bulgu 6): bunlar
            // gönderilmediğinde backend 3000 K / gamma 1.2 / 1 kg/s
            // varsayılanlarına düşüyor ve farklı itergaçlar aynı grafiği veriyordu.
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 50, 'common.f.chamberTemperatureK'],
            ['gamma', 'Gamma (frozen)', 1.2, 0.01, 'common.f.gammaFrozen'],
            ['mdot_total', 'Total Mass Flow (kg/s)', 1.0, 0.1, 'common.f.mdotTotal'],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.01, 'common.f.chamberDiameterM'],
    ];

    window.AnalysisDock.register({
        id: 'performance',
        title: 'Advanced Performance — 3D Surface, Mach Contour, Heat Flux',
        titleKey: 'panel.performance.title',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid'],
        fields: PERF_FIELDS,
        fromResults: fromResults,
        render: render,
    });

    window.AnalysisDock.register({
        id: 'performance_solid',
        title: 'Advanced Performance — Mach Contour, Heat Flux',
        titleKey: 'panel.performance.titleSolid',
        category: 'PERFORMANCE',
        endpoint: ENDPOINT,
        motorTypes: ['solid'],
        fields: [['analysis_type', 'Figure', SOLID_FIGURES[0][0], SOLID_FIGURES,
                  'panel.performance.figChoice']].concat(
            PERF_FIELDS.filter(function (f) {
                return SURFACE_ONLY_FIELDS.indexOf(f[0]) === -1;
            })),
        fromResults: fromResults,
        render: renderSolid,
    });

    // Saf eşleme: motor sonucu -> form alanları. register() içindeki anonim
    // fonksiyondan çıkarıldı ki test doğrudan çağırabilsin.
    function fromResults(r) {
        const m = (r && r.motor) || r || {};
        const geo = (m.motor_geometry && typeof m.motor_geometry === 'object')
            ? m.motor_geometry : null;
        birimiCozulemeyenAlanlar = [];

        // 2026-08-03 (Faz 6, T18 kök nedeni): itici KİMLİĞİ hiçbir zaman
        // isteğe girmiyordu. Uç (app.py::advanced_performance_analysis)
        // `fuel_type` / `oxidizer_type` alanlarını zaten okuyor, ama panel
        // yalnız SAYISAL form alanlarını gönderiyordu — sonuçta RP-1/LOX
        // sayfasında bile denge yüzeyi N2O/HTPB referans çiftiyle çözülüyor,
        // üstüne o yüzeye ait olmayan bir tasarım noktası basılıyordu.
        // Kimlik burada yakalanır (motor sonucu tek doğruluk kaynağıdır) ve
        // readFormPayload her istekte ekler; arayüze yeni alan eklenmez,
        // kullanıcının elle tutarlı tutması gerekmez.
        sonIticiler = {
            fuel_type: m.fuel_type || m.fuel || null,
            oxidizer_type: m.oxidizer_type || m.oxidizer || null,
        };
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
        const chamberL = geoLength(m, geo, 'chamber_length', r);
        if (chamberL !== null) sug.chamber_length = chamberL;
        const chamberD = geoLength(m, geo, 'chamber_diameter', r);
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
        const throatD = geoLength(m, geo, 'throat_diameter', r);
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
        //: OH-D32-01 — emekli `_siLength` çıkarımının yerine ADLI yokluk:
        //: son `fromResults` turunda birimi çözülemeyen alan adları.
        _unresolvedGeometry: function () {
            return birimiCozulemeyenAlanlar.slice();
        },
        // Birim sözleşmesi testi (tests/test_unit_contract.py) bu saf
        // fonksiyonu gerçek motor yanıtı üzerinde node ile çalıştırır.
        _fromResults: fromResults,
    };
})();
