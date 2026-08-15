/* ====================================================================
   HRMA Termal FEA Paneli (D2 — geçici ısı iletimi çözücüsünün kullanıcı yüzü)
   --------------------------------------------------------------------
   POST /api/fea/thermal ucu 2026-08-15 denetimine kadar SAĞLAMDI ama
   HİÇBİR kullanıcı yüzü onu çağırmıyordu (ölçüldü): kullanıcı ne sıcaklık
   alanını ne de malzeme sınırı hükmünü görebiliyordu. Bu panel zinciri
   kapatır — 2.7 kapı ölçütü #1: "mesh üstünde sıcaklık konturu EKRANDA".

   ÖLÇÜLMÜŞ ÇALIŞAN ZİNCİR (canlı sunucuda doğrulandı, bire bir uyulur):
     1) Hibrit sonucunun DÜZ alanlarından POST /api/analysis/wall-profile
        → yanıt.wall_profile (x_mm, h_g, T_recovery, ...).
     2) POST /api/fea/thermal gövdesi:
        { motor_results: <sonuç sözlüğü>,
          axial_profile: <wall_profile bloğu AYNEN>,
          ambient_temperature_K: <kullanıcı alanı> }
        → fea.fields.temperature_final_K (düğüm alanı), iç yüzey T(z),
          tepe cidar T(t) geçmişi, mesh, malzeme sınırı hükmü, enerji
          bütçesi, zaman adımı beyanı, warnings[].
   Motor sözlüğünden h(z) TÜRETİLMEZ (uç da türetmez; app.py:7576
   docstring). Eksik girdi → HTTP 200 + fea.missing[] + fea.reason;
   panel hiçbir şey çizmez, eksiği ADIYLA basar.

   BİRİM TUZAĞI (panels/thermal_panel.js readAxialPayload'da ölçülen
   kusurun aynısı): /api/analysis/wall-profile uzunlukları METRE bekler,
   ama motor sonuç sözlükleri motor tipine göre mm taşıyabilir (katı düz
   alanları mm, hibrit m — analysis_dock.js LENGTH_UNITS, ölçülmüş).
   Dönüşüm ALANIN KAYNAĞINA göre yapılır: önce AnalysisDock.ui.readLengthM
   (tek tanım yeri), o yoksa motor_geometry SI bloğu. "x > 2 ise mm'dir"
   gibi büyüklük sezgiseli YOKTUR ve bekçi testi bunu kilitler.

   SAHTE VERİ YASAĞI (fea_panel.js sözleşmesinin aynısı):
     * status != 'ok' → hiçbir alan çizilmez; missing/reason basılır.
     * Çekirdek motor alanı eksikse uç HİÇ ÇAĞRILMAZ: wall-profile ucunun
       sunucu varsayılanları (20 bar / 3000 K ...) BAŞKA bir motorun
       profili demektir; panel eksiği kendi beyanıyla adlandırır.
     * ambient_temperature_K kullanıcı alanı boşsa UYDURULMAZ; uç eksiği
       kendi sözleşmesiyle adlandırır ve panel onu basar.
     * Yeni motor sonucu gelince eski FEA çıktısı BAYATTIR, silinir.
     * outer_ambient İSTENMEZ: uç dış yüzeyi adyabatik alır ve bunu kendi
       cümlesiyle beyan eder; panel o beyanı AYNEN gösterir.
     * İlerleme yüzdesi yoktur; belirsiz süreli iş belirsiz gösterge alır.

   Birim: çözücü kelvin + metre + saniye döner; panel HİÇBİR ölçekleme,
   yumuşatma veya yeniden örnekleme yapmaz (değerler aynen çizilir).

   Kullanım (advanced.html):
     <script src="/static/js/thermal_fea_panel.js"></script>
     ThermalFeaPanel.init({ anchorId: 'feaPanel',
                            fallbackAnchorId: 'trajectoryPanel',
                            hookName: 'displayCalculationResults' });
   Panel #feaPanel'in HEMEN ALTINA yerleşir.

   Bekçi testleri: tests/test_thermal_fea_panel.py (node ile izole koşum)
   + tests/test_fea_termal_uc.py (uç sözleşmesi).
   ==================================================================== */

(function () {
    'use strict';

    const PROFILE_ENDPOINT = '/api/analysis/wall-profile';
    const THERMAL_ENDPOINT = '/api/fea/thermal';

    let cfg = {};
    let lastMotorResults = null;     // paneli besleyecek motor sonucu
    let lastPayload = null;          // son FEA yanıtı (fea bloğu)
    let lastError = null;            // ağ/sunucu hatası metni
    let busy = false;
    let showMesh = true;             // tel-kafes katmanı açık/kapalı
    let carpetFallback = false;      // carpet çizilemedi → nokta haritası

    // i18n köprüleri — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // Sunucu üretimi serbest metin (beyan/gerekçe) — sözlükte karşılığı
    // varsa çevrilir, yoksa AYNEN kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    function fmt(v, digits) {
        return isNum(v) ? v.toFixed(digits === undefined ? 2 : digits) : '—';
    }

    // Enerji artığı gibi çok küçük sayılar için üstel biçim.
    function fmtExp(v) {
        return isNum(v) ? v.toExponential(1) : '—';
    }

    // ==================================================================
    // >>> THERMAL_FEA_PAYLOAD_START
    // Girdi hazırlığı — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // doğrudan koşturur (birim dönüşümü kilidi burada sınanır).
    // ==================================================================

    function motorDictLocal(r) {
        return (r && r.motor && typeof r.motor === 'object') ? r.motor : (r || null);
    }

    // AnalysisDock yokken kullanılan uzunluk okuyucu (METRE döner).
    // Öncelik motor_geometry bloğudur: o blok SI beyanlıdır
    // (analysis_dock.js readLengthM ölçümüyle aynı). Düz alan ancak bu
    // panelin yaşadığı hibrit sayfa sözleşmesiyle okunur: hibrit düz
    // uzunlukları METREDİR (LENGTH_UNITS.hybrid, ölçülmüş). Büyüklüğe
    // bakarak birim TAHMİN EDİLMEZ — mm taşıyan katı/sıvı sözlükleri
    // motor_geometry SI bloğuyla yakalanır, yakalanamıyorsa alan eksik
    // sayılır (uydurma dönüşüm yok).
    function fallbackLengthM(results, key) {
        const m = motorDictLocal(results) || {};
        const g = m.motor_geometry;
        if (g && typeof g === 'object' && isNum(g[key])) {
            return g[key];              // motor_geometry SI (ölçüldü)
        }
        const v = m[key];
        return isNum(v) ? v : undefined;
    }

    // Uzunluk okuma — TEK yetkili AnalysisDock.ui.readLengthM'dir (motor
    // tipine göre mm/m tablosunu o taşır; tablo burada İKİNCİ KEZ
    // yazılmaz). Dock yüklü değilse (test ortamı) yukarıdaki yedek çalışır.
    function readLen(results, key) {
        const AD = window.AnalysisDock;
        if (AD && AD.ui && typeof AD.ui.readLengthM === 'function') {
            const v = AD.ui.readLengthM(results, key);
            return isNum(v) ? v : undefined;
        }
        return fallbackLengthM(results, key);
    }

    //: Uçtaki motor_data çekirdeğinin düz (birimsiz sorunlu olmayan)
    //: alanları — hepsinin sunucu tarafında VARSAYILANI vardır, o yüzden
    //: eksikse istek GÖNDERİLMEZ (varsayılan başka motorun profili olur).
    const CORE_FLAT_FIELDS = ['chamber_pressure', 'chamber_temperature',
                              'burn_time', 'mdot_total'];
    //: Uzunluk alanları — uç METRE bekler; okuma readLen üzerinden.
    const CORE_LENGTH_FIELDS = ['chamber_diameter', 'chamber_length'];

    // Ölçülmüş zincirin 1. adımının gövdesi. Dönüş: { body, missing }.
    // missing doluysa istek atılmaz; eksikler ADIYLA panelde basılır.
    function buildWallProfileBody(results) {
        const m = motorDictLocal(results) || {};
        const body = {};
        const missing = [];
        CORE_FLAT_FIELDS.forEach(function (k) {
            if (isNum(m[k])) body[k] = m[k];
            else missing.push(k);
        });
        CORE_LENGTH_FIELDS.forEach(function (k) {
            const v = readLen(results, k);
            if (isNum(v)) body[k] = v;
            else missing.push(k);
        });
        // Boğaz çapı ve genleşme oranı: varsa AYNEN geçirilir (metre
        // dönüşümü readLen'den); yoksa uç aynı motor verisinden kendisi
        // türetir — bu türetme uydurma değil, aynı fiziğin devamıdır.
        const dt = readLen(results, 'throat_diameter');
        if (isNum(dt)) body.throat_diameter = dt;
        if (isNum(m.expansion_ratio)) body.expansion_ratio = m.expansion_ratio;
        return { body: body, missing: missing };
    }
    // <<< THERMAL_FEA_PAYLOAD_END
    // ==================================================================

    // ==================================================================
    // >>> THERMAL_FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek uç yanıtlarıyla koşturur. Alan değerleri sunucudan geldiği
    // gibi taşınır; sıcaklık için HİÇBİR ölçekleme yoktur.
    // ==================================================================

    // node_index_grid: [i][j] — i eksenel istasyon, j cidar katmanı
    // (0 iç/gaz yüzeyi). Carpet izleri 2B diziyi [b][a] sırasıyla ister.
    function gridDims(mesh) {
        const g = mesh && mesh.node_index_grid;
        if (!Array.isArray(g) || !g.length || !Array.isArray(g[0])) return null;
        return { ni: g.length, nj: g[0].length };
    }

    // Düğüm koordinatlarından carpet ızgarası: x[j][i], y[j][i] (metre).
    function buildCarpetGrid(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        if (!Array.isArray(nodes)) return null;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        for (let j = 0; j < dims.nj; j++) {
            const rx = [], ry = [];
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                if (!Array.isArray(n)) return null;
                rx.push(n[0]);
                ry.push(n[1]);
            }
            x.push(rx);
            y.push(ry);
        }
        const a = [], b = [];
        for (let i = 0; i < dims.ni; i++) a.push(i);
        for (let j = 0; j < dims.nj; j++) b.push(j);
        return { a: a, b: b, x: x, y: y, ni: dims.ni, nj: dims.nj };
    }

    // Düğüm alanı (N,) → carpet düzeni [j][i]. Sıcaklık kelvin gelir ve
    // kelvin çizilir: ölçek çarpanı YOKTUR (bekçi bunu kilitler).
    function fieldToGrid(mesh, values) {
        const dims = gridDims(mesh);
        if (!dims || !Array.isArray(values)) return null;
        const g = mesh.node_index_grid;
        const out = [];
        for (let j = 0; j < dims.nj; j++) {
            const row = [];
            for (let i = 0; i < dims.ni; i++) {
                const v = values[g[i][j]];
                row.push(isNum(v) ? v : null);
            }
            out.push(row);
        }
        return out;
    }

    // Tel-kafes: yapısal ızgaranın bütün i ve j çizgileri; eleman
    // kenarlarının kendisidir (fea_panel.js ile aynı kurgu).
    function buildWireframe(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        let pts = 0;
        for (let i = 0; i < dims.ni; i++) {
            for (let j = 0; j < dims.nj; j++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        for (let j = 0; j < dims.nj; j++) {
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        return { x: x, y: y, node_visits: pts, n_nodes: dims.ni * dims.nj };
    }

    // Sunucu yanıtı (fea bloğu) → çizilebilir görünüm modeli.
    function buildViewModel(fea, errorText) {
        if (errorText) return { mode: 'error', error: String(errorText) };
        if (!fea || typeof fea !== 'object') return { mode: 'idle' };
        if (fea.status !== 'ok') {
            return {
                mode: 'not_modelled',
                status: fea.status || null,
                missing: Array.isArray(fea.missing) ? fea.missing : [],
                reason: (typeof fea.reason === 'string') ? fea.reason : '',
                warning: fea.warning || null,
                engine_layout: fea.engine_layout || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const hist = fea.history || {};
        const meta = fea.meta || {};

        // İç yüzey eğrisi: iki dizi AYNI uzunluktaysa çizilir; değilse
        // kısmî eğri uydurulmaz.
        let innerCurve = null;
        if (Array.isArray(fields.inner_surface_z_m)
                && Array.isArray(fields.inner_surface_T_final_K)
                && fields.inner_surface_z_m.length
                && fields.inner_surface_z_m.length
                    === fields.inner_surface_T_final_K.length) {
            innerCurve = {
                z_m: fields.inner_surface_z_m,
                T_K: fields.inner_surface_T_final_K,
            };
        }

        // Tepe cidar sıcaklığı geçmişi: aynı uzunluk şartı aynı sebeple.
        let historyCurve = null;
        if (Array.isArray(hist.times_s)
                && Array.isArray(hist.peak_wall_T_history_K)
                && hist.times_s.length
                && hist.times_s.length === hist.peak_wall_T_history_K.length) {
            historyCurve = {
                times_s: hist.times_s,
                peak_T_K: hist.peak_wall_T_history_K,
            };
        }

        const sinir = (fea.material_limits && typeof fea.material_limits === 'object')
            ? fea.material_limits : null;
        const bc = (meta.sinir_kosullari_koprusu
                    && typeof meta.sinir_kosullari_koprusu === 'object')
            ? meta.sinir_kosullari_koprusu : {};

        const vm = {
            mode: 'ok',
            engine_layout: fea.engine_layout || null,
            grid: grid,
            temperature_K: fieldToGrid(mesh, fields.temperature_final_K),
            wireframe: buildWireframe(mesh),
            inner: innerCurve,
            history: historyCurve,
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_axial: mesh.n_axial, n_radial: mesh.n_radial,
                grid_ni: grid.ni, grid_nj: grid.nj,
                units: mesh.coordinate_units || null,
            },
            scalars: {
                peak_wall_T_K: isNum(scalars.peak_wall_T_K)
                    ? scalars.peak_wall_T_K : null,
                peak_time_s: isNum(scalars.peak_time_s)
                    ? scalars.peak_time_s : null,
                inner_surface_peak_T_K: isNum(scalars.inner_surface_peak_T_K)
                    ? scalars.inner_surface_peak_T_K : null,
                inner_surface_peak_z_m: isNum(scalars.inner_surface_peak_z_m)
                    ? scalars.inner_surface_peak_z_m : null,
                burn_time_s: isNum(scalars.burn_time_s)
                    ? scalars.burn_time_s : null,
                ambient_temperature_K: isNum(scalars.ambient_temperature_K)
                    ? scalars.ambient_temperature_K : null,
                material_key: scalars.material_key || null,
                wall_thickness_m: isNum(scalars.wall_thickness_m)
                    ? scalars.wall_thickness_m : null,
            },
            material_limits: sinir,
            energy: (fea.energy && typeof fea.energy === 'object')
                ? fea.energy : null,
            time_step: (fea.time_step && typeof fea.time_step === 'object')
                ? fea.time_step : null,
            warnings: Array.isArray(fea.warnings) ? fea.warnings : [],
            limits: fea.limits || null,
            not_modelled: Array.isArray(meta.not_modelled)
                ? meta.not_modelled : [],
            bc: {
                outer: (typeof bc.dis_yuzey === 'string') ? bc.dis_yuzey : null,
                inner: (typeof bc.ic_yuzey === 'string') ? bc.ic_yuzey : null,
                initial: (typeof bc.baslangic_kosulu === 'string')
                    ? bc.baslangic_kosulu : null,
                window: (typeof bc.zaman_penceresi === 'string')
                    ? bc.zaman_penceresi : null,
            },
            basis: {
                solver: meta._basis || null,
                fields: fields._basis || null,
                history: hist._basis || null,
                limits_note: (fea.limits && fea.limits._basis) || null,
                material: (sinir && sinir._basis) || null,
                mesh_policy: (meta.mesh_politikasi
                              && meta.mesh_politikasi.beyan) || null,
            },
        };
        // Izgara SUNUCUNUN beyan ettiği düğüm sayısını vermiyorsa alan
        // çizilmez (kısmî harita, haritasızlıktan kötüdür).
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    // <<< THERMAL_FEA_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil (fea_panel.js kalıbı)
    // ------------------------------------------------------------------
    const MISSING_COLOR = '#8a93a0';
    const ALLOW_COLOR = '#ff8c33';      // izin sınırı çizgisi (turuncu)
    const MELT_COLOR = '#ff5d73';       // erime noktası çizgisi (kırmızı)
    const MESH_COLOR = 'rgba(180,200,215,0.55)';
    // Bu Plotly derlemesinde (1.58.5) GERÇEKTEN bulunan bir skala:
    // 'Hot' — sıcaklık alanı için siyah→kırmızı→sarı.
    const T_COLORSCALE = 'Hot';

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
            dim: MISSING_COLOR,
        };
        const c = colors[kind] || colors.info;
        return `<span data-badge="${kind}" style="border:1px solid ${c}; color:${c};
            border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
            font-size:0.75rem;">${text}</span>`;
    }

    function chipHtml(label, reason) {
        let html = `<span data-chip="not-modelled" style="border:1px solid ${MISSING_COLOR};
            color:${MISSING_COLOR}; border-radius:6px; padding:4px 10px;
            font-family:var(--hd-mono); font-size:0.75rem;">${esc(label)}</span>`;
        if (reason) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0 0;
                white-space:pre-wrap;">${esc(SRV(reason))}</p>`;
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="thermalFeaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▣ <span data-i18n="feaT.title">${T('feaT.title',
                'Thermal FEA — Transient Wall Temperature Field')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="feaT.intro">${T('feaT.intro',
                    'A transient heat-conduction finite element run on the nozzle wall '
                    + 'of THIS result: the gas-side film coefficient profile h(z) is '
                    + 'computed first (Bartz, wall-profile endpoint) and fed to the '
                    + 'solver as a boundary condition — nothing is fabricated from a '
                    + 'single throat number. You see the temperature field on the '
                    + 'mesh at the end of the burn, the gas-side surface temperature '
                    + 'along the wall and the peak wall temperature history. If an '
                    + 'input is missing, nothing is drawn and the missing item is '
                    + 'named.')}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="fea_t_run" class="btn" type="button"
                    data-i18n="feaT.run">${T('feaT.run', 'Run thermal analysis')}</button>
                <span id="fea_t_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <span data-i18n="feaT.ambientLabel">${T('feaT.ambientLabel',
                        'Initial / ambient temperature [K]')}</span>
                    <input type="number" id="fea_t_ambient" value="293.15" step="0.05"
                        style="width:90px;">
                </label>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="fea_t_show_mesh" checked>
                    <span data-i18n="feaT.showMesh">${T('feaT.showMesh',
                        'Show mesh wireframe')}</span>
                </label>
            </div>
            <div id="fea_t_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="fea_t_chip" style="margin:8px 0;"></div>
            <div id="fea_t_warnings" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-orange, #ff8c33); margin:6px 0;"></div>
            <div id="fea_t_plot_field" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_t_plot_inner" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_t_plot_hist" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_t_bc_note" style="font-family:var(--hd-mono); font-size:0.72rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="fea_t_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="feaT.basisTitle">${T('feaT.basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)')}</summary>
                <div id="fea_t_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></div>
            </details>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function wireTrace(vm) {
        const w = vm.wireframe;
        return {
            x: w.x, y: w.y, mode: 'lines', type: 'scatter',
            line: { color: MESH_COLOR, width: 1 },
            name: TF('feaT.meshTrace', { n: vm.mesh_info.n_elems },
                     'Mesh ({n} elements)'),
            hoverinfo: 'skip',
        };
    }

    // Malzeme sınırı referans çizgileri (değerler SUNUCUDAN; panel eşik
    // uydurmaz). thermal_panel.js limitLine kalıbı.
    function limitShapes(vm) {
        const ml = vm.material_limits || {};
        const shapes = [], annotations = [];
        function line(v, label, color) {
            if (!isNum(v)) return;
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
        line(ml.allowable_temperature_K,
             T('feaT.allowLine', 'Allowable'), ALLOW_COLOR);
        line(ml.melting_point_K,
             T('feaT.meltLine', 'Melting point'), MELT_COLOR);
        return { shapes: shapes, annotations: annotations };
    }

    // T(z, r) konturu: carpet + contourcarpet MESH üstünde (yapısal
    // panelin kontur+tel-kafes yaklaşımı). Değerler kelvin, AYNEN.
    function fieldFigure(vm) {
        const g = vm.grid;
        const cbar = T('feaT.cbarField', 'T [K]');
        const traces = [{
            type: 'carpet', carpet: 'feaTCarpet',
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, {
            type: 'contourcarpet', carpet: 'feaTCarpet',
            a: g.a, b: g.b, z: vm.temperature_K,
            contours: { coloring: 'fill', showlines: false },
            colorscale: T_COLORSCALE,
            colorbar: { title: cbar, titleside: 'right' },
            name: cbar,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: T('feaT.chartField',
                         'Wall temperature at end of burn — T(z, r) [K]'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği (eski Plotly): düğüm nokta haritası — fea_panel deseni.
    function fieldFallbackFigure(vm) {
        const g = vm.grid;
        const cbar = T('feaT.cbarField', 'T [K]');
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]);
                c.push(vm.temperature_K[j][i]);
            }
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: c, colorscale: T_COLORSCALE, size: 6,
                      colorbar: { title: cbar, titleside: 'right' } },
            name: cbar,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: T('feaT.chartField',
                         'Wall temperature at end of burn — T(z, r) [K]'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // İç (gaz tarafı) yüzey sıcaklığı T(z) — çözücü alanının j = 0
    // düğümleri, sunucudan okunduğu gibi.
    function innerFigure(vm) {
        const lim = limitShapes(vm);
        return {
            traces: [{
                x: vm.inner.z_m, y: vm.inner.T_K,
                mode: 'lines+markers', type: 'scatter',
                marker: { size: 6 }, line: { width: 2 },
                name: T('feaT.innerTrace', 'Inner (gas-side) surface T [K]'),
            }],
            layout: {
                title: T('feaT.chartInner',
                         'Inner (gas-side) surface temperature at end of burn'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisT', 'Temperature [K]') },
                shapes: lim.shapes,
                annotations: lim.annotations,
                height: 300,
                showlegend: false,
            },
        };
    }

    // Tepe cidar sıcaklığı geçmişi T(t) — zaman adımı yakınsamasının
    // ölçüldüğü büyüklüğün kendisi (history._basis).
    function historyFigure(vm) {
        const lim = limitShapes(vm);
        return {
            traces: [{
                x: vm.history.times_s, y: vm.history.peak_T_K,
                mode: 'lines', type: 'scatter',
                line: { width: 2 },
                name: T('feaT.histTrace', 'Peak wall temperature [K]'),
            }],
            layout: {
                title: T('feaT.chartHistory',
                         'Peak wall temperature history over the burn'),
                xaxis: { title: T('feaT.axisTime', 'Time [s]') },
                yaxis: { title: T('feaT.axisT', 'Temperature [K]') },
                shapes: lim.shapes,
                annotations: lim.annotations,
                height: 300,
                showlegend: false,
            },
        };
    }

    function drawFigure(el, figure) {
        Plotly.react(el, figure.traces, figure.layout,
                     { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Basım
    // ------------------------------------------------------------------
    function renderBadges(el, vm) {
        let html = '';
        if (vm.engine_layout) {
            html += badge(T('feaT.badgeEngine', 'ENGINE') + ': '
                + esc(String(vm.engine_layout).toUpperCase()), 'info');
        }
        html += badge(TF('feaT.badgeMesh',
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes },
            'MESH {elems} elements / {nodes} nodes'), 'info');
        html += badge(TF('feaT.badgePeak',
            { v: fmt(vm.scalars.peak_wall_T_K, 0),
              t: fmt(vm.scalars.peak_time_s, 2) },
            'PEAK WALL T {v} K at t = {t} s'), 'info');

        // Malzeme sınırı hükmü — hüküm ve değerler SUNUCUDAN gelir
        // (material_limits); panel eşik uydurmaz, yalnız renk kodlar.
        const ml = vm.material_limits;
        if (ml && (isNum(ml.allowable_temperature_K) || isNum(ml.melting_point_K))) {
            if (ml.exceeds_melting === true) {
                html += badge(TF('feaT.badgeOverMelting',
                    { melt: fmt(ml.melting_point_K, 0) },
                    'EXCEEDS MELTING POINT ({melt} K) — the material would not '
                    + 'survive this burn'), 'err');
            } else if (ml.exceeds_allowable === true) {
                html += badge(TF('feaT.badgeOverAllowable',
                    { allow: fmt(ml.allowable_temperature_K, 0),
                      melt: fmt(ml.melting_point_K, 0) },
                    'EXCEEDS ALLOWABLE {allow} K (melting point {melt} K)'),
                    'warn');
            } else if (ml.exceeds_allowable === false) {
                html += badge(TF('feaT.badgeWithinLimits',
                    { allow: fmt(ml.allowable_temperature_K, 0) },
                    'WITHIN ALLOWABLE {allow} K'), 'ok');
            } else {
                // İzin sınırı kayıtta yok; yalnız erime hükmü verilebildi.
                html += badge(TF('feaT.badgeAllowMissing',
                    { melt: fmt(ml.melting_point_K, 0) },
                    'ALLOWABLE NOT PUBLISHED — below melting point {melt} K'),
                    'dim');
            }
        } else {
            html += badge(T('feaT.badgeLimitsMissing',
                'MATERIAL LIMITS NOT PUBLISHED (no temperature limit in the '
                + 'material record)'), 'dim');
        }

        if (vm.energy && isNum(vm.energy.residual_rel)) {
            html += badge(TF('feaT.badgeEnergy',
                { v: fmtExp(vm.energy.residual_rel) },
                'ENERGY RESIDUAL {v} (relative)'), 'info');
        }
        if (vm.time_step && 'converged' in vm.time_step) {
            html += badge(vm.time_step.converged
                ? T('feaT.badgeStepOk', 'TIME STEP CONVERGED')
                : T('feaT.badgeStepNo', 'TIME STEP NOT CONVERGED — read the '
                    + 'declaration below'),
                vm.time_step.converged ? 'ok' : 'warn');
        }
        if (carpetFallback) {
            html += badge(T('feaT.badgeFallback',
                'CONTOUR UNAVAILABLE — node point map drawn instead'), 'dim');
        }
        el.innerHTML = html;
    }

    // warnings[] — GrainFeaPanel warn işleme deseni: {code, params} kaydı
    // I18N.tf ile basılır; sözlükte yoksa kod AYNEN görünür (gizlenmez).
    function renderWarnings(el, vm) {
        if (!el) return;
        if (!vm.warnings || !vm.warnings.length) {
            el.innerHTML = '';
            return;
        }
        let html = '<p style="margin:0 0 4px;">'
            + esc(TF('feaT.warnCount', { n: vm.warnings.length },
                     '{n} warnings declared by the solver:')) + '</p>';
        html += '<ul style="margin:0 0 0 18px;">'
            + vm.warnings.map(function (w) {
                const kod = (w && w.code) ? w.code : '';
                const metin = (window.I18N && window.I18N.tf && kod)
                    ? window.I18N.tf(kod, (w && w.params) || {}, kod)
                    : kod;
                return `<li style="margin:4px 0;">${esc(metin)}</li>`;
            }).join('') + '</ul>';
        el.innerHTML = html;
    }

    function renderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        if (vm.basis.solver) parts.push(SRV(vm.basis.solver));
        if (vm.basis.fields) parts.push(SRV(vm.basis.fields));
        if (vm.basis.history) parts.push(SRV(vm.basis.history));
        if (vm.basis.material) parts.push(SRV(vm.basis.material));
        if (vm.basis.mesh_policy) parts.push(SRV(vm.basis.mesh_policy));
        if (vm.bc.inner) parts.push(SRV(vm.bc.inner));
        if (vm.bc.initial) parts.push(SRV(vm.bc.initial));
        if (vm.bc.window) parts.push(SRV(vm.bc.window));
        if (vm.time_step && vm.time_step.beyan) parts.push(SRV(vm.time_step.beyan));
        if (vm.basis.limits_note) parts.push(SRV(vm.basis.limits_note));
        parts.push(T('feaT.unitNote', 'Units: the solver returns kelvin, '
            + 'metres and seconds; the panel plots them exactly as received. '
            + 'No smoothing, no resampling, no rescaling of any field is '
            + 'applied.'));
        parts.push(T('feaT.axisNote', 'Axes of the field map are NOT equally '
            + 'scaled: the wall is thin compared with the engine length, so '
            + 'the radial axis is stretched to make the wall visible.'));
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(TF(
                'feaT.notModelledCount', { n: vm.not_modelled.length },
                '{n} physics items are NOT modelled in this thermal run:'))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        els.basis.style.display = '';
    }

    function hidePlots(els) {
        ['field', 'inner', 'hist'].forEach(function (k) {
            if (els[k]) els[k].style.display = 'none';
        });
        if (els.bcNote) els.bcNote.innerHTML = '';
        if (els.warnings) els.warnings.innerHTML = '';
    }

    function render() {
        const vm = buildViewModel(lastPayload, lastError);
        const els = {
            badges: document.getElementById('fea_t_badges'),
            chip: document.getElementById('fea_t_chip'),
            busy: document.getElementById('fea_t_busy'),
            warnings: document.getElementById('fea_t_warnings'),
            field: document.getElementById('fea_t_plot_field'),
            inner: document.getElementById('fea_t_plot_inner'),
            hist: document.getElementById('fea_t_plot_hist'),
            bcNote: document.getElementById('fea_t_bc_note'),
            basis: document.getElementById('fea_t_basis'),
            basisText: document.getElementById('fea_t_basis_text'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Belirsiz süreli iş: yüzde YOK, nabız var (sahte ilerleme yasak).
            els.busy.style.display = busy ? '' : 'none';
            els.busy.textContent = busy
                ? T('feaT.busy', 'Running — the gas-side profile is computed '
                    + 'first, then the transient solver refines its time step '
                    + 'until the peak temperature stops changing; the duration '
                    + 'is not known in advance.') : '';
            if (busy) els.busy.setAttribute('data-indeterminate', 'true');
        }

        if (vm.mode !== 'ok') {
            hidePlots(els);
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = busy ? '' : chipHtml(
                    T('feaT.chipIdle',
                      'NOT RUN YET — press "Run thermal analysis" to solve the '
                      + 'wall of the current result'), '');
            } else if (vm.mode === 'not_modelled') {
                const missing = vm.missing.length
                    ? TF('feaT.missingList', { list: vm.missing.join(', ') },
                         'Missing inputs: {list}')
                    : '';
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipNotModelled',
                      'NOT MODELLED — the inputs the thermal FEA needs are not '
                      + 'all available; nothing is drawn'),
                    [missing, vm.reason].filter(Boolean).join('\n'));
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipError', 'RUN FAILED — no field is drawn'),
                    vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipInvalid',
                      'DATA INCONSISTENT — the response carries no usable mesh '
                      + 'grid; nothing is plotted'), '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            hidePlots(els);
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                T('feaT.chipGridMismatch',
                  'MESH INCONSISTENT — the node grid does not match the '
                  + 'declared node count; nothing is plotted'), '');
            return;
        }

        // Her basımda yedek bayrağı sıfırlanır (fea_panel deseni).
        carpetFallback = false;
        els.chip.innerHTML = '';
        renderBadges(els.badges, vm);
        renderWarnings(els.warnings, vm);
        renderBasis(els, vm);

        // Dış yüzey sınır koşulu beyanı — uç adyabatik dışı KENDİSİ beyan
        // eder; panel o cümleyi aynen gösterir (outer_ambient istenmez).
        if (els.bcNote) {
            els.bcNote.innerHTML = vm.bc.outer
                ? '<strong data-i18n="feaT.bcOuter">'
                    + esc(T('feaT.bcOuter',
                            'Outer surface boundary condition (declared by '
                            + 'the solver):')) + '</strong> ' + esc(SRV(vm.bc.outer))
                : '';
        }

        // T(z, r) alanı — MESH üstünde kontur
        if (vm.temperature_K) {
            els.field.style.display = 'block';
            try {
                drawFigure(els.field, fieldFigure(vm));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.field, fieldFallbackFigure(vm));
                renderBadges(els.badges, vm);
            }
        } else {
            els.field.style.display = 'none';
        }

        // İç yüzey T(z)
        if (vm.inner) {
            els.inner.style.display = 'block';
            drawFigure(els.inner, innerFigure(vm));
        } else {
            els.inner.style.display = 'none';
        }

        // Tepe cidar T(t) geçmişi (tek nokta eğri değildir, çizilmez)
        if (vm.history && vm.history.times_s.length >= 2) {
            els.hist.style.display = 'block';
            drawFigure(els.hist, historyFigure(vm));
        } else {
            els.hist.style.display = 'none';
        }
    }

    // ------------------------------------------------------------------
    // Koşum
    // ------------------------------------------------------------------
    function pickResults() {
        if (typeof cfg.resultsProvider === 'function') {
            try {
                const r = cfg.resultsProvider();
                if (r && typeof r === 'object') return r;
            } catch (e) { /* sağlayıcı patlarsa genel yola düş */ }
        }
        if (lastMotorResults && typeof lastMotorResults === 'object') {
            return lastMotorResults;
        }
        const cur = window.currentResults;
        return (cur && typeof cur === 'object') ? cur : null;
    }

    function readAmbientK() {
        const el = document.getElementById('fea_t_ambient');
        const v = el ? parseFloat(el.value) : NaN;
        return isNum(v) ? v : undefined;
    }

    function run() {
        if (busy) return Promise.resolve(null);
        const results = pickResults();
        const motor = motorDictLocal(results);
        if (!motor || typeof motor !== 'object') {
            lastPayload = null;
            lastError = T('feaT.noResult',
                'No motor result on this page yet — run the motor calculation first.');
            render();
            return Promise.resolve(null);
        }

        // Çekirdek alan eksikse wall-profile ucu HİÇ çağrılmaz: o ucun
        // sunucu varsayılanları başka bir motorun profili olurdu. Eksik
        // ADIYLA beyan edilir (panelin kendi beyanı — uç yanıtı değil).
        const built = buildWallProfileBody(results);
        if (built.missing.length) {
            lastPayload = {
                status: 'NOT_MODELLED',
                missing: built.missing,
                reason: T('feaT.clientMissingReason',
                    'The motor result on this page does not carry these '
                    + 'fields. The wall-profile endpoint would silently '
                    + 'substitute defaults for them — that would be another '
                    + 'motor\'s profile — so it is not called. (Declared by '
                    + 'the panel, before any request.)'),
            };
            lastError = null;
            render();
            return Promise.resolve(null);
        }

        const ambientK = readAmbientK();

        busy = true;
        lastError = null;
        render();
        // Adım 1 — h(z) profili (ölçülmüş zincir): /api/analysis/wall-profile
        return fetch(PROFILE_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(built.body),
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            if (!r.ok || !r.body || r.body.status !== 'success') {
                throw new Error((r.body && r.body.error)
                    || T('feaT.profileHttpError',
                         'The wall-profile endpoint returned an error; the '
                         + 'thermal FEA was not attempted.'));
            }
            const wp = r.body.wall_profile;
            if (!wp || !Array.isArray(wp.x_mm) || !wp.x_mm.length) {
                throw new Error(T('feaT.profileEmpty',
                    'The wall-profile endpoint returned no axial stations; '
                    + 'the thermal FEA was not attempted.'));
            }
            // Adım 2 — geçici termal FEA: wall_profile bloğu AYNEN geçer.
            const govde = {
                motor_results: motor,
                axial_profile: wp,
            };
            // Ortam sıcaklığı kullanıcı alanından; boş/geçersizse
            // UYDURULMAZ — uç eksiği kendi sözleşmesiyle adlandırır.
            if (ambientK !== undefined) govde.ambient_temperature_K = ambientK;
            return fetch(THERMAL_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(govde),
            });
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            busy = false;
            if (!r.ok || !r.body || r.body.status !== 'success') {
                lastPayload = null;
                lastError = (r.body && (r.body.detail || r.body.error))
                    || T('feaT.httpError',
                         'The thermal FEA endpoint returned an error.');
            } else {
                lastPayload = r.body.fea || null;
                lastError = null;
            }
            render();
            return lastPayload;
        }).catch(function (e) {
            busy = false;
            lastPayload = null;
            lastError = String((e && e.message) || e);
            render();
            return null;
        });
    }

    // Yeni motor sonucu geldi: eski FEA çıktısı BAYATTIR, silinir.
    function update(results) {
        lastMotorResults = results || null;
        if (lastPayload || lastError) {
            lastPayload = null;
            lastError = null;
        }
        render();
    }

    function init(opts) {
        cfg = opts || {};
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        // Panel #feaPanel'in HEMEN ALTINA yerleşir (yapısal FEA'nın termal
        // kardeşi). Çapa yoksa yapısal panelin kendi çapasının önüne, o da
        // yoksa sonuç ızgarasına düşülür.
        const anchor = document.getElementById(cfg.anchorId || 'feaPanel');
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor.nextSibling);
        } else {
            const fb = document.getElementById(
                cfg.fallbackAnchorId || 'trajectoryPanel');
            if (fb && fb.parentNode) {
                fb.parentNode.insertBefore(panel, fb);
            } else {
                (document.querySelector('.results-grid')
                    || document.body).appendChild(panel);
            }
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);

        const runBtn = document.getElementById('fea_t_run');
        if (runBtn) runBtn.addEventListener('click', function () { run(); });
        const meshBox = document.getElementById('fea_t_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                showMesh = !!meshBox.checked;
                render();
            });
        }

        // Hesap köprüsü: fea_panel.js/blowdown_panel.js ile AYNI desen.
        // advanced.html'de sonuç basıcısı 'displayCalculationResults'tır
        // (app.js:176'dan çağrılır; 'displayResults' bu sayfada YOKTUR).
        // Özgün işlev her koşulda çalışır; panel hatası hesabı engellemez.
        (function () {
            const ad = cfg.hookName || 'displayCalculationResults';
            const original = window[ad];
            if (typeof original !== 'function') return;
            window[ad] = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('Thermal FEA panel update failed:', e);
                }
                return out;
            };
        })();

        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        render();
    }

    window.ThermalFeaPanel = {
        init: init,
        update: update,
        run: run,
        buildViewModel: buildViewModel,
        setShowMesh: function (v) { showMesh = !!v; render(); },
        applyPayload: function (fea, error) {
            lastPayload = fea || null;
            lastError = error || null;
            busy = false;
            render();
        },
        // Bekçi testleri için: birim dönüşümü kilidi bu iki işlev üstünde
        // sınanır (AnalysisDock yokken yedek yol koşar).
        _buildWallProfileBody: buildWallProfileBody,
        _fallbackLengthM: fallbackLengthM,
        get payload() { return lastPayload; },
    };
})();
