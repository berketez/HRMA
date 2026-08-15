/* ====================================================================
   HRMA Yapısal FEA Paneli (D5 — v2.7 analiz modülünün kullanıcı yüzü)
   --------------------------------------------------------------------
   hrma/fea/ çözücüleri (mesh_axisym + structural_axisym + bridge) depoda
   çalışır hâldeydi ama 2026-08-04 denetimine kadar HİÇBİR kullanıcı yüzü
   yoktu: ne gerilme alanı, ne mesh, ne de yakınsama geçmişi görünüyordu.
   Bu panel POST /api/fea/structural yanıtını çizer.

   Berke'nin açık isteği (4 Ağustos 2026): "mesh AYARI görmesem de MESH'İ
   görmek isterim — iyi mesh atıyor mu göreyim". Panel bu yüzden mesh
   AYARI sunmaz (yakınsama sürücüsü kendi kararını verir) ama mesh'in
   KENDİSİNİ gösterir: tel-kafes katmanı, eleman kalite haritası ve
   yakınsama eğrisi.

   Ne çizilir (hepsi sunucu yanıtından, hesap YOK):
     (a) von Mises ve emniyet katsayısı KONTUR haritası — eksenel simetrik
         (z, r) kesiti üstünde, Plotly carpet + contourcarpet ile (yapısal
         eğrisel ızgara Plotly'nin contour/heatmap izlerinde 1B eksen
         ister; carpet tam olarak bu iş için vardır).
     (b) MESH tel-kafesi — yapısal ızgaranın i ve j çizgileri; eleman
         kenarlarının BİREBİR kendisidir (yaklaşım değil).
     (c) ELEMAN KALİTE haritası — en-boy oranı / ölçekli Jacobian; eşiği
         aşan eleman KIRMIZI. Eşikler sunucudan gelir (tek tanım yeri:
         app.py FEA_QUALITY_*; kaynak künyesi yanıtın quality._basis
         alanında, Verdict/CUBIT dörtgen ölçüt tablosu).
     (d) YAKINSAMA grafiği — maks von Mises (MPa) vs eleman sayısı;
         noktalar köprünün yakınsama geçmişinden gelir, beyan metni
         sunucunun kendi cümlesidir.

   SAHTE VERİ YASAĞI:
     * Sunucu NOT_MODELLED derse hiçbir alan çizilmez; eksik girdi listesi
       ve sunucunun gerekçesi basılır.
     * Emniyet katsayısı alanı null gelirse (malzeme kaydında akma yoksa)
       SF grafiği hiç kurulmaz — yerine "yayımlanmadı" çipi konur.
     * Motor sonucu değişince ESKİ FEA çıktısı SİLİNİR (bayat gerilme
       alanı yeni motorunmuş gibi gösterilmez).
     * İlerleme çubuğu YOKTUR: koşu süresi önceden bilinmez, belirsiz
       süreli iş için belirsiz gösterge (nabız) kullanılır.

   Birim: çözücü Pa döner; panel yalnızca 1e6'ya böler (MPa) ve bunu
   eksen başlığında + künye satırında beyan eder. Başka ölçekleme,
   yeniden örnekleme veya yumuşatma YOKTUR.

   Kullanım (advanced.html):
     <script src="/static/js/fea_panel.js"></script>
     FeaPanel.init({ anchorId: 'trajectoryPanel' });

   Bekçi testleri: tests/test_fea_panel.py (node ile izole koşum) +
   tests/test_fea_endpoint.py (uç sözleşmesi).
   ==================================================================== */

(function () {
    'use strict';

    const ENDPOINT = '/api/fea/structural';
    const PA_PER_MPA = 1e6;          // birim dönüşümünün TEK yeri

    let cfg = {};
    let lastMotorResults = null;     // paneli besleyecek motor sonucu
    let lastPayload = null;          // son FEA yanıtı (fea bloğu)
    let lastError = null;            // ağ/sunucu hatası metni
    let busy = false;
    let showMesh = true;             // tel-kafes katmanı açık/kapalı
    let qualityMetric = 'aspect_ratio';
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
    // Sunucu üretimi serbest metin (beyan/gerekçe alanları) — i18n_charts.js
    // sözlüğünden geçer, eşleşme yoksa AYNEN kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ==================================================================
    // >>> FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek uç yanıtlarıyla koşturur. Alan değerleri sunucudan geldiği
    // gibi taşınır; tek dönüşüm Pa → MPa bölmesidir ve beyan edilir.
    // ==================================================================

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    // node_index_grid: [i][j] — i eksenel istasyon, j cidar katmanı
    // (0 iç yüzey). Carpet izleri 2B diziyi [b][a] sırasıyla ister, yani
    // satır = katman (j), sütun = istasyon (i).
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

    // Düğüm alanı (N,) → carpet düzeni [j][i]. scale verilirse bölünür
    // (Pa → MPa); başka dönüşüm yapılmaz. Alan eksikse null döner.
    function fieldToGrid(mesh, values, scale) {
        const dims = gridDims(mesh);
        if (!dims || !Array.isArray(values)) return null;
        const g = mesh.node_index_grid;
        const div = (typeof scale === 'number' && scale !== 0) ? scale : 1;
        const out = [];
        for (let j = 0; j < dims.nj; j++) {
            const row = [];
            for (let i = 0; i < dims.ni; i++) {
                const v = values[g[i][j]];
                row.push(isNum(v) ? v / div : null);
            }
            out.push(row);
        }
        return out;
    }

    // Tel-kafes: yapısal ızgaranın bütün i ve j çizgileri. Eleman
    // kenarlarının kendisidir; tek iz olarak null ayraçlarla taşınır.
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
        // Her düğüm bir kez i-çizgisinde, bir kez j-çizgisinde geçer.
        return { x: x, y: y, node_visits: pts, n_nodes: dims.ni * dims.nj };
    }

    // Eleman merkezleri — dört düğümün ortalaması (sıra varsayımı YOK,
    // bağlantı dizisi neyse o kullanılır).
    function elementCentres(mesh) {
        const elems = mesh && mesh.elems;
        const nodes = mesh && mesh.nodes;
        if (!Array.isArray(elems) || !Array.isArray(nodes)) return null;
        const x = new Array(elems.length), y = new Array(elems.length);
        for (let e = 0; e < elems.length; e++) {
            const c = elems[e];
            let sx = 0, sy = 0;
            for (let k = 0; k < c.length; k++) {
                const n = nodes[c[k]];
                sx += n[0]; sy += n[1];
            }
            x[e] = sx / c.length;
            y[e] = sy / c.length;
        }
        return { x: x, y: y };
    }

    // Kalite bayrakları — eşikler SUNUCUDAN gelir (panelde eşik sabiti
    // yoktur). Sonlu olmayan/eksik ölçüt de bayraklanır: ölçülemeyen
    // eleman "iyi" sayılmaz.
    function qualityFlags(quality) {
        if (!quality || typeof quality !== 'object') return null;
        const th = quality.thresholds || {};
        const ar = Array.isArray(quality.aspect_ratio) ? quality.aspect_ratio : null;
        const sj = Array.isArray(quality.scaled_jacobian) ? quality.scaled_jacobian : null;
        if (!ar && !sj) return null;
        const n = (ar || sj).length;
        const arMax = isNum(th.aspect_ratio_max) ? th.aspect_ratio_max : null;
        const sjMin = isNum(th.scaled_jacobian_min) ? th.scaled_jacobian_min : null;
        const aspect = new Array(n), jac = new Array(n), any = new Array(n);
        for (let e = 0; e < n; e++) {
            const av = ar ? ar[e] : null;
            const sv = sj ? sj[e] : null;
            aspect[e] = (arMax === null || !ar) ? false
                : (!isNum(av) || av > arMax);
            jac[e] = (sjMin === null || !sj) ? false
                : (!isNum(sv) || sv < sjMin);
            any[e] = aspect[e] || jac[e];
        }
        return {
            aspect: aspect, jacobian: jac, any: any,
            thresholds: { aspect_ratio_max: arMax, scaled_jacobian_min: sjMin },
            counts: {
                aspect: aspect.filter(Boolean).length,
                jacobian: jac.filter(Boolean).length,
                any: any.filter(Boolean).length,
                total: n,
            },
        };
    }

    // Yakınsama geçmişi → grafik serileri (eleman sayısı vs maks von Mises).
    function buildConvergence(conv) {
        if (!conv || typeof conv !== 'object') return null;
        const hist = Array.isArray(conv.history) ? conv.history : [];
        const nElems = [], vmMPa = [], relPct = [];
        hist.forEach(function (h) {
            if (!h || typeof h !== 'object') return;
            if (!isNum(h.n_elems) || !isNum(h.max_von_mises)) return;
            nElems.push(h.n_elems);
            vmMPa.push(h.max_von_mises / PA_PER_MPA);
            relPct.push(isNum(h.rel_change) ? 100 * h.rel_change : null);
        });
        return {
            n_elems: nElems,
            von_mises_mpa: vmMPa,
            rel_change_pct: relPct,
            rounds: nElems.length,
            converged: conv.converged === true,
            tol_pct: isNum(conv.tol) ? 100 * conv.tol : null,
            final_rel_change_pct: isNum(conv.final_rel_change)
                ? 100 * conv.final_rel_change : null,
            beyan: (typeof conv.beyan === 'string') ? conv.beyan : null,
        };
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
                notes: (fea.notes && typeof fea.notes === 'object') ? fea.notes : null,
                warning: fea.warning || null,
                engine_layout: fea.engine_layout || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const vm = {
            mode: 'ok',
            engine_layout: fea.engine_layout || null,
            grid: grid,
            von_mises_mpa: fieldToGrid(mesh, fields.von_mises_pa, PA_PER_MPA),
            safety_factor: Array.isArray(fields.safety_factor)
                ? fieldToGrid(mesh, fields.safety_factor, 1) : null,
            wireframe: buildWireframe(mesh),
            centres: elementCentres(mesh),
            quality: fea.quality || null,
            flags: qualityFlags(fea.quality),
            convergence: buildConvergence(fea.convergence),
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_axial: mesh.n_axial, n_radial: mesh.n_radial,
                grid_ni: grid.ni, grid_nj: grid.nj,
                units: mesh.coordinate_units || null,
                meta: mesh.meta || null,
            },
            scalars: {
                von_mises_max_mpa: isNum(scalars.von_mises_gauss_max_pa)
                    ? scalars.von_mises_gauss_max_pa / PA_PER_MPA : null,
                min_safety_factor: isNum(scalars.min_safety_factor)
                    ? scalars.min_safety_factor : null,
                yield_mpa: isNum(scalars.yield_strength_pa)
                    ? scalars.yield_strength_pa / PA_PER_MPA : null,
                material_key: scalars.material_key || null,
                wall_thickness_m: isNum(scalars.wall_thickness_m)
                    ? scalars.wall_thickness_m : null,
                inner_pressure_pa: isNum(scalars.inner_pressure_pa)
                    ? scalars.inner_pressure_pa : null,
            },
            limits: fea.limits || null,
            not_modelled: (fea.meta && Array.isArray(fea.meta.not_modelled))
                ? fea.meta.not_modelled : [],
            basis: {
                fields: (fields && fields._basis) || null,
                quality: (fea.quality && fea.quality._basis) || null,
                solver: (fea.meta && fea.meta._basis) || null,
                inputs: (fea.meta && fea.meta.girdiler) || null,
            },
        };
        // Düğüm sayısı tutarlılığı: ızgara SUNUCUNUN beyan ettiği düğüm
        // sayısını vermiyorsa alan çizilmez (kısmî harita, haritasızlıktan
        // kötüdür).
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    // <<< FEA_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil (motor_viz3d / blowdown_panel kalıbı)
    // ------------------------------------------------------------------
    const MISSING_COLOR = '#8a93a0';
    const BAD_COLOR = '#ff5d73';        // eşik dışı eleman
    const MESH_COLOR = 'rgba(180,200,215,0.55)';

    // Renk skalaları: yalnız bu Plotly derlemesinde GERÇEKTEN bulunan adlar
    // kullanılır (plotly-1.58.5'te 'Turbo'/'RdYlGn' yoktur), emniyet
    // katsayısı skalası açıkça yazılır — düşük SF kırmızı, yüksek SF yeşil.
    const VM_COLORSCALE = 'Viridis';
    const SF_COLORSCALE = [[0.0, '#ff5d73'], [0.5, '#ffcf5c'], [1.0, '#2dd4a8']];

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

    function fmt(v, digits) {
        return isNum(v) ? v.toFixed(digits === undefined ? 2 : digits) : '—';
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="feaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▣ <span data-i18n="fea.title">${T('fea.title',
                'Structural FEA — Stress Field, Mesh and Convergence')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="fea.intro">${T('fea.intro',
                    'An axisymmetric finite element run on the chamber/nozzle wall of '
                    + 'THIS result: the solver refines the mesh until the peak von Mises '
                    + 'stress stops changing. You do not set the mesh — but you can see '
                    + 'it: the wireframe, the element quality map and the convergence '
                    + 'history are all drawn from the run itself. If an input is '
                    + 'missing, nothing is drawn and the missing item is named.')}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="fea_run" class="btn" type="button"
                    data-i18n="fea.run">${T('fea.run', 'Run structural analysis')}</button>
                <span id="fea_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="fea_show_mesh" checked>
                    <span data-i18n="fea.showMesh">${T('fea.showMesh',
                        'Show mesh wireframe')}</span>
                </label>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <span data-i18n="fea.qualityMetric">${T('fea.qualityMetric',
                        'Quality metric')}</span>
                    <select id="fea_metric">
                        <option value="aspect_ratio">${T('fea.metricAspect',
                            'Aspect ratio')}</option>
                        <option value="scaled_jacobian">${T('fea.metricJacobian',
                            'Scaled Jacobian')}</option>
                    </select>
                </label>
            </div>
            <div id="fea_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="fea_chip" style="margin:8px 0;"></div>
            <div id="fea_plot_vm" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_plot_sf" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_plot_quality" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_quality_note" style="font-family:var(--hd-mono); font-size:0.72rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <div id="fea_plot_conv" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_conv_note" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="fea_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="fea.basisTitle">${T('fea.basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)')}</summary>
                <div id="fea_basis_text" style="font-family:var(--hd-mono);
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
            name: TF('fea.meshTrace', { n: vm.mesh_info.n_elems },
                     'Mesh ({n} elements)'),
            hoverinfo: 'skip',
        };
    }

    // Eşik dışı eleman katmanı. HİÇBİRİ ya da HEPSİ eşik dışıysa katman
    // çizilmez: hepsi kırmızıysa halkalar ölçüt haritasını tamamen örter ve
    // ayırt edici bilgi taşımaz (sayı zaten rozette ve not satırında yazar).
    function badElementsTrace(vm) {
        const flags = vm.flags, centres = vm.centres;
        if (!flags || !centres) return null;
        if (flags.counts.any === 0 || flags.counts.any === flags.counts.total) {
            return null;
        }
        const x = [], y = [];
        for (let e = 0; e < flags.any.length; e++) {
            if (flags.any[e]) { x.push(centres.x[e]); y.push(centres.y[e]); }
        }
        if (!x.length) return null;
        // AÇIK halka: altındaki ölçüt rengini KAPATMAZ. İnce cidarda bütün
        // elemanlar eşiği aşabiliyor; dolu işaret kullanılsaydı ölçütün
        // nerede kötüleştiği görünmez olurdu.
        return {
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: BAD_COLOR, size: 10, symbol: 'circle-open',
                      line: { color: BAD_COLOR, width: 1.5 } },
            name: TF('fea.badElems', { n: x.length },
                     '{n} elements outside the quality range'),
        };
    }

    // Alan haritası: carpet + contourcarpet. Carpet izi yoksa (eski Plotly)
    // düğüm nokta haritasına düşülür ve bu durum çipte BEYAN edilir.
    function fieldFigure(vm, zGrid, title, colorbarTitle, colorscale, carpetId) {
        const g = vm.grid;
        const traces = [{
            type: 'carpet', carpet: carpetId,
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, {
            type: 'contourcarpet', carpet: carpetId,
            a: g.a, b: g.b, z: zGrid,
            contours: { coloring: 'fill', showlines: false },
            colorscale: colorscale,
            colorbar: { title: colorbarTitle, titleside: 'right' },
            name: colorbarTitle,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: title,
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği: düğüm noktaları, alan değerine göre renkli.
    function fieldFallbackFigure(vm, zGrid, title, colorbarTitle, colorscale) {
        const g = vm.grid;
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]); c.push(zGrid[j][i]);
            }
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: c, colorscale: colorscale, size: 6,
                      colorbar: { title: colorbarTitle, titleside: 'right' } },
            name: colorbarTitle,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: title,
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    function qualityFigure(vm) {
        const q = vm.quality, flags = vm.flags, centres = vm.centres;
        const values = (q && Array.isArray(q[qualityMetric])) ? q[qualityMetric] : null;
        if (!values || !centres || !flags) return null;
        // Ölçüt haritası BÜTÜN elemanları taşır (eşik dışı olanlar dahil):
        // ince cidarda hepsi eşiği aşabilir, o durumda bile kullanıcının
        // görmesi gereken şey ölçütün NEREDE kötüleştiğidir. Eşik dışı
        // elemanlar ayrıca kırmızı katmanla işaretlenir.
        const allX = [], allY = [], allC = [];
        for (let e = 0; e < values.length; e++) {
            allX.push(centres.x[e]); allY.push(centres.y[e]);
            allC.push(isNum(values[e]) ? values[e] : null);
        }
        const label = (qualityMetric === 'aspect_ratio')
            ? T('fea.metricAspect', 'Aspect ratio')
            : T('fea.metricJacobian', 'Scaled Jacobian');
        const traces = [];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        if (allX.length) {
            traces.push({
                x: allX, y: allY, mode: 'markers', type: 'scatter',
                marker: { color: allC, colorscale: 'Viridis', size: 5,
                          colorbar: { title: label, titleside: 'right' } },
                name: label,
            });
        }
        const bad = badElementsTrace(vm);
        if (bad) traces.push(bad);
        return {
            traces: traces,
            layout: {
                title: TF('fea.chartQuality', { metric: label },
                          'Element quality — {metric} (one marker per element, '
                          + 'placed at the element centroid)'),
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                legend: { orientation: 'h', y: 1.14 },
            },
        };
    }

    function convergenceFigure(conv) {
        return {
            traces: [{
                x: conv.n_elems, y: conv.von_mises_mpa,
                mode: 'lines+markers', type: 'scatter',
                marker: { size: 9 }, line: { width: 2 },
                name: T('fea.sVmMax', 'Peak von Mises [MPa]'),
            }],
            layout: {
                title: T('fea.chartConvergence',
                         'Mesh convergence — peak von Mises vs element count'),
                xaxis: { title: T('fea.axisElems', 'Elements in mesh [-]'),
                         type: 'log' },
                yaxis: { title: T('fea.axisVm', 'Peak von Mises [MPa]') },
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
            html += badge(T('fea.badgeEngine', 'ENGINE') + ': '
                + esc(String(vm.engine_layout).toUpperCase()), 'info');
        }
        html += badge(TF('fea.badgeMesh',
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes },
            'MESH {elems} elements / {nodes} nodes'), 'info');
        html += badge(TF('fea.badgeVm',
            { v: fmt(vm.scalars.von_mises_max_mpa, 1) },
            'PEAK von MISES {v} MPa (Gauss points)'), 'info');
        if (vm.scalars.min_safety_factor !== null) {
            const kind = vm.scalars.min_safety_factor < 1 ? 'err'
                : (vm.scalars.min_safety_factor < 1.5 ? 'warn' : 'ok');
            html += badge(TF('fea.badgeSf',
                { v: fmt(vm.scalars.min_safety_factor, 2) },
                'MIN SAFETY FACTOR {v} (Gauss points)'), kind);
        } else {
            html += badge(T('fea.badgeSfMissing',
                'SAFETY FACTOR NOT PUBLISHED (no yield strength in the material record)'),
                'dim');
        }
        const conv = vm.convergence;
        if (conv) {
            html += badge(conv.converged
                ? TF('fea.badgeConverged',
                     { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) },
                     'CONVERGED in {n} rounds to {pct}%')
                : TF('fea.badgeNotConverged',
                     { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) },
                     'NOT CONVERGED after {n} rounds (last change {pct}%)'),
                conv.converged ? 'ok' : 'warn');
        }
        if (vm.flags) {
            html += badge(TF('fea.badgeQuality',
                { bad: vm.flags.counts.any, total: vm.flags.counts.total },
                'MESH QUALITY {bad}/{total} elements outside the acceptable range'),
                vm.flags.counts.any ? 'warn' : 'ok');
        }
        if (carpetFallback) {
            html += badge(T('fea.badgeFallback',
                'CONTOUR UNAVAILABLE — node point map drawn instead'), 'dim');
        }
        el.innerHTML = html;
    }

    function renderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        if (vm.basis.solver) parts.push(SRV(vm.basis.solver));
        if (vm.basis.fields) parts.push(SRV(vm.basis.fields));
        if (vm.basis.quality) parts.push(SRV(vm.basis.quality));
        parts.push(TF('fea.unitNote', { }, 'Units: the solver returns Pa; the '
            + 'panel only divides by 1e6 to plot MPa. No smoothing, no '
            + 'resampling, no rescaling of the field is applied.'));
        parts.push(T('fea.axisNote', 'Axes are NOT equally scaled: the wall is '
            + 'thin compared with the engine length, so the radial axis is '
            + 'stretched to make the wall visible.'));
        // Manşet skaleri ile haritanın ucu AYNI SAYI DEĞİLDİR: skaler Gauss
        // noktalarındaki maksimumdan, harita ise düğümlere geri kazanılmış
        // alandan gelir. Fark küçüktür ama gizlenmez.
        parts.push(T('fea.gaussNote', 'The headline peak stress and minimum '
            + 'safety factor are taken at the Gauss points of the elements; '
            + 'the map shows the stress recovered at the nodes, so the extreme '
            + 'value read off the map can differ slightly from the headline '
            + 'number. Neither is rescaled to match the other.'));
        if (vm.limits && vm.limits.clamped) {
            parts.push(TF('fea.limitNote',
                { max: vm.limits.max_elems, allowed: vm.limits.rounds_allowed,
                  requested: vm.limits.rounds_requested },
                'Refinement was capped at {allowed} of {requested} rounds to keep '
                + 'the mesh within {max} elements.'));
        }
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(TF(
                'fea.notModelledCount', { n: vm.not_modelled.length },
                '{n} physics items are NOT modelled in this structural run:'))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        els.basis.style.display = '';
    }

    function hidePlots(els) {
        ['vm', 'sf', 'quality', 'conv'].forEach(function (k) {
            if (els[k]) els[k].style.display = 'none';
        });
        if (els.qualityNote) els.qualityNote.innerHTML = '';
        if (els.convNote) els.convNote.innerHTML = '';
    }

    function render() {
        const vm = buildViewModel(lastPayload, lastError);
        const els = {
            badges: document.getElementById('fea_badges'),
            chip: document.getElementById('fea_chip'),
            busy: document.getElementById('fea_busy'),
            vm: document.getElementById('fea_plot_vm'),
            sf: document.getElementById('fea_plot_sf'),
            quality: document.getElementById('fea_plot_quality'),
            qualityNote: document.getElementById('fea_quality_note'),
            conv: document.getElementById('fea_plot_conv'),
            convNote: document.getElementById('fea_conv_note'),
            basis: document.getElementById('fea_basis'),
            basisText: document.getElementById('fea_basis_text'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Belirsiz süreli iş: yüzde YOK, nabız var (sahte ilerleme yasak).
            els.busy.style.display = busy ? '' : 'none';
            els.busy.textContent = busy
                ? T('fea.busy', 'Running — the solver refines the mesh until the '
                    + 'peak stress stops changing; the duration is not known in '
                    + 'advance.') : '';
            if (busy) els.busy.setAttribute('data-indeterminate', 'true');
        }

        if (vm.mode !== 'ok') {
            hidePlots(els);
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = busy ? '' : chipHtml(
                    T('fea.chipIdle',
                      'NOT RUN YET — press "Run structural analysis" to solve the '
                      + 'wall of the current result'), '');
            } else if (vm.mode === 'not_modelled') {
                const missing = vm.missing.length
                    ? TF('fea.missingList', { list: vm.missing.join(', ') },
                         'Missing inputs: {list}')
                    : '';
                els.chip.innerHTML = chipHtml(
                    T('fea.chipNotModelled',
                      'NOT MODELLED — the solver result does not carry the inputs '
                      + 'the FEA needs; nothing is drawn'),
                    [missing, vm.reason].filter(Boolean).join('\n'));
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    T('fea.chipError', 'RUN FAILED — no field is drawn'), vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    T('fea.chipInvalid',
                      'DATA INCONSISTENT — the response carries no usable mesh grid; '
                      + 'nothing is plotted'), '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            hidePlots(els);
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                T('fea.chipGridMismatch',
                  'MESH INCONSISTENT — the node grid does not match the declared '
                  + 'node count; nothing is plotted'), '');
            return;
        }

        // Her basımda yedek bayrağı sıfırlanır: geçmişte bir kez carpet
        // çizilemediyse bu, sonraki basımda da öyle olduğu anlamına gelmez.
        carpetFallback = false;
        els.chip.innerHTML = '';
        renderBadges(els.badges, vm);
        renderBasis(els, vm);

        // von Mises alanı
        if (vm.von_mises_mpa) {
            els.vm.style.display = 'block';
            const title = T('fea.chartVm',
                'von Mises stress on the axisymmetric wall section [MPa]');
            const cbar = T('fea.cbarVm', 'von Mises [MPa]');
            try {
                drawFigure(els.vm, fieldFigure(vm, vm.von_mises_mpa, title, cbar,
                                               VM_COLORSCALE, 'feaCarpetVm'));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.vm, fieldFallbackFigure(vm, vm.von_mises_mpa,
                                                       title, cbar, VM_COLORSCALE));
                renderBadges(els.badges, vm);
            }
        } else {
            els.vm.style.display = 'none';
        }

        // Emniyet katsayısı alanı — yayımlanmadıysa GRAFİK YOK
        if (vm.safety_factor) {
            els.sf.style.display = 'block';
            const title = T('fea.chartSf',
                'Safety factor field (yield / von Mises) [-]');
            const cbar = T('fea.cbarSf', 'Safety factor [-]');
            try {
                drawFigure(els.sf, fieldFigure(vm, vm.safety_factor, title, cbar,
                                               SF_COLORSCALE, 'feaCarpetSf'));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.sf, fieldFallbackFigure(vm, vm.safety_factor,
                                                       title, cbar, SF_COLORSCALE));
                renderBadges(els.badges, vm);
            }
        } else {
            els.sf.style.display = 'none';
        }

        // Eleman kalite haritası
        const qFig = qualityFigure(vm);
        if (qFig) {
            els.quality.style.display = 'block';
            drawFigure(els.quality, qFig);
            if (els.qualityNote) {
                const th = vm.flags.thresholds;
                const c = vm.flags.counts;
                let qn = TF('fea.qualityNote',
                    { arMax: th.aspect_ratio_max, sjMin: th.scaled_jacobian_min,
                      bad: c.any, total: c.total },
                    'Acceptable range: aspect ratio <= {arMax} and scaled '
                    + 'Jacobian >= {sjMin}; {bad} of {total} elements are '
                    + 'outside it. Thresholds and metric definitions come from '
                    + 'the server; see the basis note below.');
                if (c.any === c.total && c.total > 0) {
                    qn += ' ' + T('fea.qualityAllFlagged',
                        'Every element is outside the range, so the red overlay '
                        + 'is omitted — it would cover the whole map without '
                        + 'telling you anything. Read the colour scale instead: '
                        + 'it shows where the metric is worst.');
                } else if (c.any > 0) {
                    qn += ' ' + T('fea.qualityRingNote',
                        'Elements outside the range are ringed in red.');
                }
                els.qualityNote.innerHTML = esc(qn);
            }
        } else {
            els.quality.style.display = 'none';
            if (els.qualityNote) els.qualityNote.innerHTML = '';
        }

        // Yakınsama
        const conv = vm.convergence;
        if (conv && conv.n_elems.length >= 2) {
            els.conv.style.display = 'block';
            drawFigure(els.conv, convergenceFigure(conv));
        } else {
            els.conv.style.display = 'none';
        }
        if (els.convNote) {
            let note = '';
            if (conv && conv.rounds) {
                note += esc(conv.converged
                    ? TF('fea.convText',
                         { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2),
                           tol: fmt(conv.tol_pct, 2) },
                         'Converged in {n} refinement rounds: the peak von Mises '
                         + 'changed by {pct}% between the last two meshes '
                         + '(tolerance {tol}%).')
                    : TF('fea.convTextNo',
                         { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2),
                           tol: fmt(conv.tol_pct, 2) },
                         'NOT converged: after {n} refinement rounds the peak von '
                         + 'Mises still changed by {pct}% between the last two '
                         + 'meshes (tolerance {tol}%). Read the result with this '
                         + 'in mind.'));
            }
            if (conv && conv.beyan) {
                note += (note ? ' ' : '') + esc(SRV(conv.beyan));
            }
            els.convNote.innerHTML = note;
        }
    }

    // ------------------------------------------------------------------
    // Koşum
    // ------------------------------------------------------------------
    function pickMotorResults() {
        if (typeof cfg.resultsProvider === 'function') {
            try {
                const r = cfg.resultsProvider();
                if (r && typeof r === 'object') return r;
            } catch (e) { /* sağlayıcı patlarsa genel yola düş */ }
        }
        if (lastMotorResults && typeof lastMotorResults === 'object') {
            return lastMotorResults.motor || lastMotorResults;
        }
        const cur = window.currentResults;
        if (cur && typeof cur === 'object') return cur.motor || cur;
        return null;
    }

    function run() {
        if (busy) return Promise.resolve(null);
        const motor = pickMotorResults();
        if (!motor) {
            lastPayload = null;
            lastError = T('fea.noResult',
                'No motor result on this page yet — run the motor calculation first.');
            render();
            return Promise.resolve(null);
        }
        busy = true;
        lastError = null;
        render();
        return fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motor_results: motor }),
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            busy = false;
            if (!r.ok || !r.body || r.body.status !== 'success') {
                lastPayload = null;
                lastError = (r.body && (r.body.detail || r.body.error))
                    || T('fea.httpError', 'The structural FEA endpoint returned an error.');
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
        if (lastPayload) {
            lastPayload = null;
            lastError = null;
        }
        render();
    }

    function init(opts) {
        cfg = opts || {};
        const anchor = document.getElementById(cfg.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);

        const runBtn = document.getElementById('fea_run');
        if (runBtn) runBtn.addEventListener('click', function () { run(); });
        const meshBox = document.getElementById('fea_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                showMesh = !!meshBox.checked;
                render();
            });
        }
        const metricSel = document.getElementById('fea_metric');
        if (metricSel) {
            metricSel.addEventListener('change', function () {
                qualityMetric = metricSel.value || 'aspect_ratio';
                render();
            });
        }

        // Hesap köprüsü: blowdown_panel.js ile AYNI desen. Özgün işlev her
        // koşulda çalışır; panel hatası hesap gösterimini engellemez.
        (function () {
            const original = window.displayCalculationResults;
            if (typeof original !== 'function') return;
            window.displayCalculationResults = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('FEA panel update failed:', e);
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

    window.FeaPanel = {
        init: init,
        update: update,
        run: run,
        buildViewModel: buildViewModel,
        setShowMesh: function (v) { showMesh = !!v; render(); },
        setQualityMetric: function (m) { qualityMetric = m; render(); },
        applyPayload: function (fea, error) {
            lastPayload = fea || null;
            lastError = error || null;
            busy = false;
            render();
        },
        get payload() { return lastPayload; },
    };

    // ==================================================================
    // GrainFeaPanel — KATI TANE KESİTİ düzlemsel FEA paneli (V2.7 Aşama C)
    // ------------------------------------------------------------------
    // Katı sayfasında (solid.html) yaşar; POST /api/fea/planar-grain
    // yanıtını çizer. Kamara cidarı panelinden (FeaPanel) farkları:
    //   * kesit (x, y) düzlemidir, eksenler EŞİT ölçeklenir (fiziksel
    //     kesit çarpıtılmaz);
    //   * emniyet katsayısı alanı YOKTUR — katı tane kabul ölçütü
    //     GERİNİMDİR (NASA SP-8073): port lif gerinimi kopma uzamasıyla
    //     oranlanır ve ayrı grafikte basılır;
    //   * kesit parametreleri sayfanın SON HESAP SONUCUNDAN okunur
    //     (paramsProvider) — panel geometri üretmez, uydurma değer yok.
    // Metinler init({labelsProvider}) üzerinden i18n_pages.js'ten gelir
    // (solid.* anahtarları); sağlayıcı yoksa İngilizce yedekler kullanılır.
    // Sahte veri yasağı FeaPanel ile aynı: NOT_MODELLED'da çizim yok,
    // yeni hesap eski alanı siler, belirsiz süreli koşuda yüzde yok.
    // ==================================================================

    let gCfg = {};
    let gLastPayload = null;
    let gLastError = null;
    let gBusy = false;
    let gShowMesh = true;
    let gLabels = {};

    const GRAIN_ENDPOINT = '/api/fea/planar-grain';

    function GL(name, fallback) {
        const v = gLabels && gLabels[name];
        return (typeof v === 'string' && v) ? v : fallback;
    }

    function gFmtTpl(tpl, params) {
        return String(tpl).replace(/\{(\w+)\}/g, function (whole, key) {
            return (params && key in params) ? String(params[key]) : whole;
        });
    }

    // ------------------------------------------------------------------
    // >>> GRAIN_FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; tek dönüşümler Pa→MPa bölmesi
    // ve gerinim→% çarpımı, ikisi de beyanlıdır.
    // ------------------------------------------------------------------
    function buildGrainViewModel(fea, errorText) {
        if (errorText) return { mode: 'error', error: String(errorText) };
        if (!fea || typeof fea !== 'object') return { mode: 'idle' };
        if (fea.status !== 'ok') {
            return {
                mode: 'not_modelled',
                status: fea.status || null,
                reason: (typeof fea.reason === 'string') ? fea.reason : '',
                warning: fea.warning || null,
                grain_type: fea.grain_type || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const bore = fea.bore || {};

        // Port gerinim eğrisi: istasyon açısı düğüm koordinatından (derece),
        // gerinim % — başka işlem yok.
        let boreCurve = null;
        if (Array.isArray(bore.node_ids) && Array.isArray(bore.strain_nodal)
                && bore.node_ids.length === bore.strain_nodal.length
                && Array.isArray(mesh.nodes)) {
            const thetaDeg = [], strainPct = [];
            for (let k = 0; k < bore.node_ids.length; k++) {
                const n = mesh.nodes[bore.node_ids[k]];
                if (!Array.isArray(n)) { boreCurve = null; break; }
                thetaDeg.push(Math.atan2(n[1], n[0]) * 180.0 / Math.PI);
                strainPct.push(isNum(bore.strain_nodal[k])
                    ? 100.0 * bore.strain_nodal[k] : null);
                boreCurve = { theta_deg: thetaDeg, strain_pct: strainPct };
            }
        }

        const vm = {
            mode: 'ok',
            grain_type: fea.grain_type || null,
            symmetry_fraction: isNum(fea.symmetry_fraction)
                ? fea.symmetry_fraction : null,
            grid: grid,
            von_mises_mpa: fieldToGrid(mesh, fields.von_mises_pa, PA_PER_MPA),
            wireframe: buildWireframe(mesh),
            centres: elementCentres(mesh),
            quality: fea.quality || null,
            flags: qualityFlags(fea.quality),
            convergence: buildConvergence(fea.convergence),
            bore_curve: boreCurve,
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_theta: mesh.n_theta, n_radial: mesh.n_radial,
                units: mesh.coordinate_units || null,
            },
            scalars: {
                von_mises_gauss_max_mpa: isNum(scalars.von_mises_gauss_max_pa)
                    ? scalars.von_mises_gauss_max_pa / PA_PER_MPA : null,
                von_mises_nodal_max_mpa: isNum(scalars.von_mises_nodal_max_pa)
                    ? scalars.von_mises_nodal_max_pa / PA_PER_MPA : null,
                max_bore_strain_pct: isNum(bore.max_strain)
                    ? 100.0 * bore.max_strain : null,
                strain_capability_pct: isNum(bore.strain_capability)
                    ? 100.0 * bore.strain_capability : null,
                strain_margin: isNum(bore.strain_margin)
                    ? bore.strain_margin : null,
            },
            warnings: Array.isArray(fea.warnings) ? fea.warnings : [],
            limits: fea.limits || null,
            not_modelled: (fea.meta && Array.isArray(fea.meta.not_modelled))
                ? fea.meta.not_modelled : [],
            basis: {
                fields: (fields && fields._basis) || null,
                bore: (bore && bore._basis) || null,
                inputs: (fea.meta && fea.meta.girdiler) || null,
                quality: (fea.quality && fea.quality._basis) || null,
            },
        };
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    // <<< GRAIN_FEA_VIEWMODEL_END
    // ------------------------------------------------------------------

    function grainPanelHtml() {
        return `
        <div class="panel" id="grainFeaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▣ ${esc(GL('title',
                'Grain Section FEA — Plane-Strain Stress and Bore Strain'))}</h2>
            <div class="chart-explanation">
                <span>${esc(GL('intro',
                    'A 2D plane-strain finite element run on the propellant grain '
                    + 'cross-section of THIS design (star, finocyl and slotted ports '
                    + 'are not axisymmetric, so the wall solver cannot see them). '
                    + 'The section polygon is built on the server from the motor '
                    + 'solver itself; the acceptance quantity is the bore surface '
                    + 'STRAIN against the propellant strain capability. If an input '
                    + 'is missing, nothing is drawn and the reason is named.'))}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="grainfea_run" class="btn" type="button">${esc(GL('run',
                    'Run grain section FEA'))}</button>
                <span id="grainfea_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="grainfea_show_mesh" checked>
                    <span>${esc(GL('showMesh', 'Show mesh wireframe'))}</span>
                </label>
            </div>
            <div id="grainfea_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="grainfea_chip" style="margin:8px 0;"></div>
            <div id="grainfea_plot_vm" class="plot-container" style="min-height:380px; display:none;"></div>
            <div id="grainfea_plot_bore" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="grainfea_plot_conv" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="grainfea_conv_note" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="grainfea_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">${esc(GL(
                    'basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)'))}</summary>
                <div id="grainfea_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></div>
            </details>
        </div>`;
    }

    function grainWireTrace(vm) {
        const w = vm.wireframe;
        return {
            x: w.x, y: w.y, mode: 'lines', type: 'scatter',
            line: { color: MESH_COLOR, width: 1 },
            name: gFmtTpl(GL('meshTrace', 'Mesh ({n} elements)'),
                          { n: vm.mesh_info.n_elems }),
            hoverinfo: 'skip',
        };
    }

    function grainFieldFigure(vm) {
        const g = vm.grid;
        const cbar = GL('cbarVm', 'von Mises [MPa]');
        const traces = [{
            type: 'carpet', carpet: 'grainCarpetVm',
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, {
            type: 'contourcarpet', carpet: 'grainCarpetVm',
            a: g.a, b: g.b, z: vm.von_mises_mpa,
            contours: { coloring: 'fill', showlines: false },
            colorscale: VM_COLORSCALE,
            colorbar: { title: cbar, titleside: 'right' },
            name: cbar,
        }];
        if (gShowMesh && vm.wireframe) traces.push(grainWireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: GL('chartVm',
                    'von Mises stress on the grain cross-section [MPa]'),
                xaxis: { title: GL('axisX', 'x [m]') },
                // Fiziksel kesit: eksenler EŞİT ölçekli (çarpıtma yok).
                yaxis: { title: GL('axisY', 'y [m]'),
                         scaleanchor: 'x', scaleratio: 1 },
                height: 380,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği (eski Plotly): düğüm nokta haritası — FeaPanel deseni.
    function grainFieldFallbackFigure(vm) {
        const g = vm.grid;
        const cbar = GL('cbarVm', 'von Mises [MPa]');
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]);
                c.push(vm.von_mises_mpa[j][i]);
            }
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: c, colorscale: VM_COLORSCALE, size: 6,
                      colorbar: { title: cbar, titleside: 'right' } },
            name: cbar,
        }];
        if (gShowMesh && vm.wireframe) traces.push(grainWireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: GL('chartVm',
                    'von Mises stress on the grain cross-section [MPa]'),
                xaxis: { title: GL('axisX', 'x [m]') },
                yaxis: { title: GL('axisY', 'y [m]'),
                         scaleanchor: 'x', scaleratio: 1 },
                height: 380,
                showlegend: false,
            },
        };
    }

    function grainBoreFigure(vm) {
        const bc = vm.bore_curve;
        const traces = [{
            x: bc.theta_deg, y: bc.strain_pct,
            mode: 'lines+markers', type: 'scatter',
            marker: { size: 6 }, line: { width: 2 },
            name: GL('boreTrace', 'Bore fibre strain [%]'),
        }];
        const cap = vm.scalars.strain_capability_pct;
        if (isNum(cap)) {
            traces.push({
                x: [Math.min.apply(null, bc.theta_deg),
                    Math.max.apply(null, bc.theta_deg)],
                y: [cap, cap],
                mode: 'lines', type: 'scatter',
                line: { color: BAD_COLOR, width: 2, dash: 'dash' },
                name: GL('capTrace', 'Strain capability [%]'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: GL('chartBore',
                    'Bore surface strain along the port (acceptance quantity)'),
                xaxis: { title: GL('axisTheta', 'Station angle [deg]') },
                yaxis: { title: GL('axisStrain', 'Strain [%]') },
                height: 300,
                legend: { orientation: 'h', y: 1.16 },
            },
        };
    }

    function grainConvergenceFigure(conv) {
        return {
            traces: [{
                x: conv.n_elems, y: conv.von_mises_mpa,
                mode: 'lines+markers', type: 'scatter',
                marker: { size: 9 }, line: { width: 2 },
                name: GL('convTrace', 'Peak von Mises (SPR nodal) [MPa]'),
            }],
            layout: {
                title: GL('chartConv',
                    'Mesh convergence — peak von Mises vs element count'),
                xaxis: { title: GL('axisElems', 'Elements in mesh [-]'),
                         type: 'log' },
                yaxis: { title: GL('axisVmConv',
                    'Peak von Mises (SPR nodal) [MPa]') },
                height: 300,
                showlegend: false,
            },
        };
    }

    function grainRenderBadges(el, vm) {
        let html = '';
        if (vm.grain_type) {
            let etiket = GL('badgeType', 'SECTION') + ': '
                + esc(String(vm.grain_type).toUpperCase());
            if (vm.symmetry_fraction) {
                etiket += ' · ' + gFmtTpl(GL('badgeSlice', '1/{n} slice'),
                                          { n: vm.symmetry_fraction });
            }
            html += badge(etiket, 'info');
        }
        html += badge(gFmtTpl(GL('badgeMesh',
            'MESH {elems} elements / {nodes} nodes'),
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes }),
            'info');
        html += badge(gFmtTpl(GL('badgeVm',
            'PEAK von MISES {v} MPa (Gauss points)'),
            { v: fmt(vm.scalars.von_mises_gauss_max_mpa, 3) }), 'info');
        html += badge(gFmtTpl(GL('badgeStrain',
            'MAX BORE STRAIN {v}% of {cap}% capability'),
            { v: fmt(vm.scalars.max_bore_strain_pct, 2),
              cap: fmt(vm.scalars.strain_capability_pct, 1) }), 'info');
        if (vm.scalars.strain_margin !== null) {
            // Eşikler motorun kendi risk sınıflamasıyla aynı
            // (solid_rocket_engine._calculate_grain_structural: >=2 Low,
            // >=1 Medium, <1 High).
            const m = vm.scalars.strain_margin;
            const kind = m < 1 ? 'err' : (m < 2 ? 'warn' : 'ok');
            html += badge(gFmtTpl(GL('badgeMargin',
                'STRAIN MARGIN {v} (capability / peak strain)'),
                { v: fmt(m, 2) }), kind);
        } else {
            html += badge(GL('badgeMarginMissing',
                'STRAIN MARGIN NOT PUBLISHED (no strain capability record)'),
                'dim');
        }
        const conv = vm.convergence;
        if (conv) {
            html += badge(conv.converged
                ? gFmtTpl(GL('badgeConverged', 'CONVERGED in {n} rounds to {pct}%'),
                          { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) })
                : gFmtTpl(GL('badgeNotConverged',
                    'NOT CONVERGED after {n} rounds (last change {pct}%)'),
                          { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) }),
                conv.converged ? 'ok' : 'warn');
        }
        if (vm.flags) {
            html += badge(gFmtTpl(GL('badgeQuality',
                'MESH QUALITY {bad}/{total} elements outside the acceptable range'),
                { bad: vm.flags.counts.any, total: vm.flags.counts.total }),
                vm.flags.counts.any ? 'warn' : 'ok');
        }
        el.innerHTML = html;
    }

    function grainRenderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        const g = vm.basis.inputs || {};
        if (g.geometri && g.geometri.kaynak) parts.push(SRV(g.geometri.kaynak));
        if (g.geometri && g.geometri.kesit) parts.push(SRV(g.geometri.kesit));
        if (g.malzeme && g.malzeme.kaynak) parts.push(SRV(g.malzeme.kaynak));
        if (g.analitik_blok_iliskisi) parts.push(SRV(g.analitik_blok_iliskisi));
        if (vm.basis.bore) parts.push(SRV(vm.basis.bore));
        if (vm.basis.quality) parts.push(SRV(vm.basis.quality));
        parts.push(GL('unitNote', 'Units: the solver returns Pa and unit '
            + 'strain; the panel only divides by 1e6 to plot MPa and '
            + 'multiplies strain by 100 to plot percent. No smoothing, no '
            + 'resampling, no rescaling of any field is applied. The section '
            + 'axes are drawn to equal scale.'));
        if (vm.limits && vm.limits.clamped) {
            parts.push(gFmtTpl(GL('limitNote',
                'Refinement was capped at {allowed} of {requested} rounds to '
                + 'keep the mesh within {max} elements.'),
                { max: vm.limits.max_elems,
                  allowed: vm.limits.rounds_allowed,
                  requested: vm.limits.rounds_requested }));
        }
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.warnings && vm.warnings.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};">`
                + esc(gFmtTpl(GL('inputWarnCount',
                    '{n} input warnings were declared by the motor solver:'),
                    { n: vm.warnings.length })) + '</p>';
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.warnings.map(function (w) {
                    const kod = (w && w.code) ? w.code : '';
                    const metin = (window.I18N && window.I18N.tf && kod)
                        ? window.I18N.tf(kod, (w && w.params) || {}, kod)
                        : kod;
                    return `<li style="margin:4px 0;">${esc(metin)}</li>`;
                }).join('') + '</ul>';
        }
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(gFmtTpl(GL(
                'notModelledCount',
                '{n} physics items are NOT modelled in this grain run:'),
                { n: vm.not_modelled.length }))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        els.basis.style.display = '';
    }

    function grainRender() {
        gLabels = (typeof gCfg.labelsProvider === 'function')
            ? (gCfg.labelsProvider() || {}) : {};
        const vm = buildGrainViewModel(gLastPayload, gLastError);
        const els = {
            badges: document.getElementById('grainfea_badges'),
            chip: document.getElementById('grainfea_chip'),
            busy: document.getElementById('grainfea_busy'),
            vm: document.getElementById('grainfea_plot_vm'),
            bore: document.getElementById('grainfea_plot_bore'),
            conv: document.getElementById('grainfea_plot_conv'),
            convNote: document.getElementById('grainfea_conv_note'),
            basis: document.getElementById('grainfea_basis'),
            basisText: document.getElementById('grainfea_basis_text'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Belirsiz süreli iş: yüzde YOK, nabız var (sahte gösterge yasak).
            els.busy.style.display = gBusy ? '' : 'none';
            els.busy.textContent = gBusy
                ? GL('busy', 'Running — the solver refines the section mesh '
                    + 'until the peak stress stops changing; the duration is '
                    + 'not known in advance.') : '';
            if (gBusy) els.busy.setAttribute('data-indeterminate', 'true');
        }

        function gizle() {
            ['vm', 'bore', 'conv'].forEach(function (k) {
                if (els[k]) els[k].style.display = 'none';
            });
            if (els.convNote) els.convNote.innerHTML = '';
        }

        if (vm.mode !== 'ok') {
            gizle();
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = gBusy ? '' : chipHtml(
                    GL('chipIdle', 'NOT RUN YET — press "Run grain section '
                        + 'FEA" to solve the grain cross-section of the '
                        + 'current result'), '');
            } else if (vm.mode === 'not_modelled') {
                els.chip.innerHTML = chipHtml(
                    GL('chipNotModelled', 'NOT MODELLED — this grain section '
                        + 'is not covered by the planar solver; nothing is '
                        + 'drawn'),
                    vm.reason);
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    GL('chipError', 'RUN FAILED — no field is drawn'),
                    vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    GL('chipInvalid', 'DATA INCONSISTENT — the response '
                        + 'carries no usable mesh grid; nothing is plotted'),
                    '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            gizle();
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                GL('chipGridMismatch', 'MESH INCONSISTENT — the node grid '
                    + 'does not match the declared node count; nothing is '
                    + 'plotted'), '');
            return;
        }

        els.chip.innerHTML = '';
        grainRenderBadges(els.badges, vm);
        grainRenderBasis(els, vm);

        if (vm.von_mises_mpa) {
            els.vm.style.display = 'block';
            try {
                drawFigure(els.vm, grainFieldFigure(vm));
            } catch (e) {
                drawFigure(els.vm, grainFieldFallbackFigure(vm));
            }
        } else {
            els.vm.style.display = 'none';
        }

        if (vm.bore_curve) {
            els.bore.style.display = 'block';
            drawFigure(els.bore, grainBoreFigure(vm));
        } else {
            els.bore.style.display = 'none';
        }

        const conv = vm.convergence;
        if (conv && conv.n_elems.length >= 2) {
            els.conv.style.display = 'block';
            drawFigure(els.conv, grainConvergenceFigure(conv));
        } else {
            els.conv.style.display = 'none';
        }
        if (els.convNote && conv && conv.beyan) {
            els.convNote.innerHTML = esc(SRV(conv.beyan));
        }
    }

    function grainRun() {
        if (gBusy) return Promise.resolve(null);
        const params = (typeof gCfg.paramsProvider === 'function')
            ? gCfg.paramsProvider() : null;
        if (!params || typeof params !== 'object') {
            gLastPayload = null;
            gLastError = GL('noResult', 'No motor result on this page yet — '
                + 'run the motor calculation first.');
            grainRender();
            return Promise.resolve(null);
        }
        gBusy = true;
        gLastError = null;
        grainRender();
        return fetch(GRAIN_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            gBusy = false;
            if (!r.ok || !r.body || r.body.status !== 'success') {
                gLastPayload = null;
                gLastError = (r.body && (r.body.detail || r.body.message
                    || r.body.error))
                    || GL('httpError',
                          'The grain FEA endpoint returned an error.');
            } else {
                gLastPayload = r.body.fea || null;
                gLastError = null;
            }
            grainRender();
            return gLastPayload;
        }).catch(function (e) {
            gBusy = false;
            gLastPayload = null;
            gLastError = String((e && e.message) || e);
            grainRender();
            return null;
        });
    }

    // Yeni motor sonucu geldi: eski kesit FEA çıktısı BAYATTIR, silinir.
    function grainUpdate() {
        if (gLastPayload || gLastError) {
            gLastPayload = null;
            gLastError = null;
        }
        grainRender();
    }

    function grainInit(opts) {
        gCfg = opts || {};
        gLabels = (typeof gCfg.labelsProvider === 'function')
            ? (gCfg.labelsProvider() || {}) : {};
        const anchor = document.getElementById(gCfg.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = grainPanelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }

        const runBtn = document.getElementById('grainfea_run');
        if (runBtn) runBtn.addEventListener('click', function () { grainRun(); });
        const meshBox = document.getElementById('grainfea_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                gShowMesh = !!meshBox.checked;
                grainRender();
            });
        }

        // Hesap köprüsü: sayfanın sonuç basım işlevi sarılır (katı sayfada
        // 'displayResults'); özgün işlev her koşulda çalışır.
        (function () {
            const ad = gCfg.hookName || 'displayCalculationResults';
            const original = window[ad];
            if (typeof original !== 'function') return;
            window[ad] = function () {
                const out = original.apply(this, arguments);
                try {
                    grainUpdate();
                } catch (e) {
                    console.error('Grain FEA panel update failed:', e);
                }
                return out;
            };
        })();

        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { grainRender(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        grainRender();
    }

    window.GrainFeaPanel = {
        init: grainInit,
        update: grainUpdate,
        run: grainRun,
        buildViewModel: buildGrainViewModel,
        setShowMesh: function (v) { gShowMesh = !!v; grainRender(); },
        applyPayload: function (fea, error) {
            gLastPayload = fea || null;
            gLastError = error || null;
            gBusy = false;
            grainRender();
        },
        get payload() { return gLastPayload; },
    };
})();
