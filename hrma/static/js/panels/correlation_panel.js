/* ====================================================================
   HRMA Analiz Güvertesi — Deneysel Korelasyon Raporu Paneli
   --------------------------------------------------------------------
   GET /api/correlation-report'u UI'a bağlar: HRMA tahminleri, elle
   doğrulanmış deney veritabanına (hrma/validation/experiment_db) karşı
   koşulur; motor_type x quantity hücreleri bias / RMS / medyan APE ile
   tablolanır. POST {refresh:true} önbelleği yok sayıp yeniden koşturur.

   Sözleşme (v2.5.0 G3):
     { status:'ok', db_hash, cached, generated_s,
       record_counts:{ total, scored, insufficient_inputs, not_supported,
                       runner_error },
       cells:[ { motor_type, quantity, layer:'main'|'low_confidence'|
                 'anomaly', n, bias_percent, rms_percent,
                 median_ape_percent, mape_percent, worst_test_id } ],
       skipped_summary:{...}, markdown:'...' }
     Hata → { status:'error', error:'...' }.

   GET/POST ayrımı güvertenin tek-POST runPanel'ine sığmadığından
   comparative_panel deseni: özel blok + kendi fetch'i, dock'un otomatik
   "Run Analysis" butonu gizli. Sayfanın motor tipi satırları öne alınır
   (hibrit sayfada hybrid üstte) ama TÜM tablo görünür.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    const ENDPOINT = '/api/correlation-report';
    const PANEL_ID = 'correlation';

    // [katman, başlık anahtarı, başlık EN, not anahtarı, not EN]
    const LAYER_SECTIONS = [
        ['low_confidence', 'panel.correlation.layerLow', 'Low-confidence records',
         'panel.correlation.layerLowNote',
         'Records whose provenance or digitization confidence is limited; '
         + 'scored separately so they cannot skew the headline statistics.'],
        ['anomaly', 'panel.correlation.layerAnomaly', 'Anomalous records',
         'panel.correlation.layerAnomalyNote',
         'Records flagged as statistical outliers versus the model; '
         + 'kept visible for engineering review instead of being deleted.'],
    ];

    let lastData = null;

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function fmtPct(v) {
        return (typeof v === 'number' && isFinite(v))
            ? ((v > 0 ? '+' : '') + v.toFixed(1)) : '—';
    }

    function fmtAbsPct(v) {
        return (typeof v === 'number' && isFinite(v)) ? v.toFixed(1) : '—';
    }

    // ------------------------------------------------------------------
    // Özel kontrol satırı (Run + cached rozeti + Refresh)
    // ------------------------------------------------------------------
    function customFormHtml() {
        return `<div id="corr_custom" style="margin:10px 0;">
            <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <button class="btn" type="button" id="corr_run"
                    data-i18n="panel.correlation.btnRun">${T('panel.correlation.btnRun',
                    'Run Correlation vs Experimental Database')}</button>
                <button class="btn" type="button" id="corr_refresh" disabled
                    data-i18n-title="panel.correlation.refreshTip"
                    title="${T('panel.correlation.refreshTip',
                        'Ignore the cached report and re-run every record')}"
                    data-i18n="panel.correlation.btnRefresh">${T('panel.correlation.btnRefresh',
                    'Refresh (re-run)')}</button>
                <span id="corr_cached_badge"></span>
            </div>
            <p style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;"
                data-i18n="panel.correlation.intro">${T('panel.correlation.intro',
                'Compares HRMA predictions against the hand-verified experimental '
                + 'record database. Results are cached by database content hash; '
                + 'Refresh forces a full re-run.')}</p>
        </div>`;
    }

    function augmentSection() {
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        if (!sec) return false;
        if (document.getElementById('corr_custom')) return true;  // idempotent
        // Güvertenin otomatik POST butonu gizlenir: bu panel GET (rapor)
        // ve POST {refresh:true} (yeniden koşum) ayrımını kendi yapar.
        const dockBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (dockBtn && dockBtn.parentElement) {
            dockBtn.parentElement.style.display = 'none';
        }
        const holder = document.createElement('div');
        holder.innerHTML = customFormHtml();
        const status = document.getElementById('ad_status_' + PANEL_ID);
        sec.insertBefore(holder.firstElementChild, status);
        document.getElementById('corr_run')
            .addEventListener('click', function () { run(false); });
        document.getElementById('corr_refresh')
            .addEventListener('click', function () { run(true); });
        return true;
    }

    // Güverte DOMContentLoaded'ta kurulur; bölüm görünene dek dene
    // (montaj yarışına dayanıklılık — validation/comparative deseni)
    function scheduleAugment() {
        if (augmentSection()) return;
        let tries = 0;
        const timer = setInterval(function () {
            tries += 1;
            if (augmentSection() || tries > 40) clearInterval(timer);
        }, 250);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleAugment);
    } else {
        scheduleAugment();
    }

    // ------------------------------------------------------------------
    // Çalıştırma — GET rapor / POST {refresh:true} yeniden koşum
    // ------------------------------------------------------------------
    async function run(refresh) {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        const runBtn = document.getElementById('corr_run');
        const refreshBtn = document.getElementById('corr_refresh');
        const badge = document.getElementById('corr_cached_badge');
        if (!status || !root || !runBtn) return;

        runBtn.disabled = true;
        if (refreshBtn) refreshBtn.disabled = true;
        root.style.display = 'none';
        status.style.color = 'var(--hd-ink-dim, #7d97a5)';
        status.textContent = refresh
            ? T('panel.correlation.rerunning', 'RE-RUNNING FULL CORRELATION (cache ignored)…')
            : T('panel.correlation.running', 'RUNNING CORRELATION REPORT…');
        if (badge) badge.innerHTML = '';

        try {
            const resp = await fetch(ENDPOINT, refresh ? {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh: true }),
            } : { method: 'GET' });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            lastData = data;
            if (badge) {
                badge.innerHTML = U.badge(
                    data.cached ? T('panel.correlation.cached', 'CACHED')
                                : T('panel.correlation.freshRun', 'FRESH RUN'),
                    data.cached ? 'dim' : 'ok',
                    data.cached
                        ? T('panel.correlation.cachedTip',
                            'Served from cache keyed by database content hash')
                        : T('panel.correlation.freshTip', 'Computed in this request'));
            }
            root.innerHTML = '';
            render(data, root);
            root.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.style.color = 'var(--hd-red, #ff5d73)';
            status.textContent = U.tf('common.errorPrefix', { message: err.message },
                                      'ERROR: {message}');
        } finally {
            runBtn.disabled = false;
            if (refreshBtn) refreshBtn.disabled = !lastData;
        }
    }

    // ------------------------------------------------------------------
    // Tablolama
    // ------------------------------------------------------------------
    // Sayfanın motor tipi üstte; grup içinde motor_type + quantity sırası
    function orderCells(cells) {
        const page = window.AnalysisDock.getMotorType();
        return cells.slice().sort(function (a, b) {
            const ap = (a.motor_type === page) ? 0 : 1;
            const bp = (b.motor_type === page) ? 0 : 1;
            if (ap !== bp) return ap - bp;
            if (a.motor_type !== b.motor_type) {
                return a.motor_type < b.motor_type ? -1 : 1;
            }
            if (a.quantity !== b.quantity) {
                return a.quantity < b.quantity ? -1 : 1;
            }
            return 0;
        });
    }

    function cellRowHtml(c) {
        const page = window.AnalysisDock.getMotorType();
        const isPage = c.motor_type === page;
        const motorStyle = isPage
            ? 'color:var(--hd-cyan, #00e5ff); font-weight:bold;'
            : 'color:var(--hd-ink, #cfe8f2);';
        const tip = T('panel.correlation.worstRecord', 'Worst record') + ': '
            + escapeHtml(String(c.worst_test_id || 'n/a'))
            + (typeof c.mape_percent === 'number' && isFinite(c.mape_percent)
                ? (' | MAPE ' + c.mape_percent.toFixed(1) + '%') : '');
        return `<tr title="${tip}">
            <td style="${U.TD} ${motorStyle}">${escapeHtml(c.motor_type)}</td>
            <td style="${U.TD}">${escapeHtml(c.quantity)}</td>
            <td style="${U.TD} text-align:right; font-family:var(--hd-mono);">${c.n != null ? c.n : '—'}</td>
            <td style="${U.TD} text-align:right; font-family:var(--hd-mono);">${fmtPct(c.bias_percent)}</td>
            <td style="${U.TD} text-align:right; font-family:var(--hd-mono);">${fmtAbsPct(c.rms_percent)}</td>
            <td style="${U.TD} text-align:right; font-family:var(--hd-mono);">${fmtAbsPct(c.median_ape_percent)}</td>
        </tr>`;
    }

    function cellTableHtml(cells) {
        if (!cells.length) {
            return `<p style="font-family:var(--hd-mono, monospace);
                font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">
                ${T('panel.correlation.noCells', 'No cells in this layer.')}</p>`;
        }
        const TH = U.TD + ' color:var(--hd-ink-dim, #7d97a5);'
            + ' font-family:var(--hd-mono); font-size:0.7rem;'
            + ' text-transform:uppercase; letter-spacing:0.06em;';
        return `<table style="${U.TBL}">
            <thead><tr>
                <th style="${TH} text-align:left;">${T('panel.correlation.colMotor', 'Motor')}</th>
                <th style="${TH} text-align:left;">${T('panel.correlation.colQuantity', 'Quantity')}</th>
                <th style="${TH} text-align:right;">n</th>
                <th style="${TH} text-align:right;"
                    title="${T('panel.correlation.biasTip',
                        'Signed mean percent error (model minus experiment)')}">${
                    T('panel.correlation.colBias', 'Bias %')}</th>
                <th style="${TH} text-align:right;"
                    title="${T('panel.correlation.rmsTip', 'Root-mean-square percent error')}">${
                    T('panel.correlation.colRms', 'RMS %')}</th>
                <th style="${TH} text-align:right;"
                    title="${T('panel.correlation.apeTip', 'Median absolute percent error')}">${
                    T('panel.correlation.colApe', 'Median APE %')}</th>
            </tr></thead>
            <tbody>${orderCells(cells).map(cellRowHtml).join('')}</tbody>
        </table>`;
    }

    function collapsibleLayerHtml(title, note, cells) {
        return `<details style="margin:10px 0; border:1px solid
                var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:8px 12px;">
            <summary style="cursor:pointer; color:var(--hd-ink-strong, #eaf7fb);">
                ${escapeHtml(title)}
                <span style="font-family:var(--hd-mono); font-size:0.7rem;
                    color:var(--hd-ink-dim, #7d97a5);">
                    (${U.tf('panel.correlation.cellCount', { n: cells.length },
                             '{n} cells')})</span>
            </summary>
            <p style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;">
                ${escapeHtml(note)}</p>
            ${cellTableHtml(cells)}
        </details>`;
    }

    function summaryLineHtml(data) {
        const rc = data.record_counts || {};
        const parts = [
            T('panel.correlation.cntTotal', 'total') + ' ' + (rc.total != null ? rc.total : '—'),
            T('panel.correlation.cntScored', 'scored') + ' ' + (rc.scored != null ? rc.scored : '—'),
            T('panel.correlation.cntInsufficient', 'insufficient inputs') + ' '
                + (rc.insufficient_inputs != null ? rc.insufficient_inputs : '—'),
            T('panel.correlation.cntUnsupported', 'not supported') + ' '
                + (rc.not_supported != null ? rc.not_supported : '—'),
        ];
        if (rc.runner_error) {
            parts.push(T('panel.correlation.cntRunnerError', 'runner errors') + ' '
                + rc.runner_error);
        }
        const hash = String(data.db_hash || '');
        const shortHash = hash ? hash.slice(0, 12) : '—';
        return `<div style="font-family:var(--hd-mono, monospace);
                font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);
                margin:8px 0;">
            ${T('panel.correlation.recordsLabel', 'Records')}: ${escapeHtml(parts.join(' · '))}
            &nbsp;|&nbsp; db
            <span title="${escapeHtml(hash)}"
                style="color:var(--hd-cyan, #00e5ff);">${escapeHtml(shortHash)}</span>
            &nbsp;|&nbsp; ${T('panel.correlation.generatedIn', 'generated in')}
            ${(typeof data.generated_s === 'number' && isFinite(data.generated_s))
                ? data.generated_s.toFixed(2) : '—'} s
        </div>`;
    }

    function render(data, root) {
        const cells = Array.isArray(data.cells) ? data.cells : [];
        const main = cells.filter(function (c) { return c.layer === 'main'; });

        const head = document.createElement('div');
        head.innerHTML = U.sectionTitle(T('panel.correlation.secMain',
                'Correlation vs Experimental Database'))
            + summaryLineHtml(data)
            + U.sectionTitle(T('panel.correlation.secLayer', 'Main layer — motor type x quantity'))
            + `<p style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
                color:var(--hd-ink-dim, #7d97a5); margin:2px 0 6px;">${
                T('panel.correlation.mainNote',
                  "Rows for this page's motor type are listed first. Hover a row "
                  + 'for the worst-scoring test id.')}</p>`
            + '<div style="overflow-x:auto;">' + cellTableHtml(main) + '</div>';
        root.appendChild(head);

        LAYER_SECTIONS.forEach(function (sec) {
            const layerCells = cells.filter(function (c) {
                return c.layer === sec[0];
            });
            if (!layerCells.length) return;
            const holder = document.createElement('div');
            holder.innerHTML = collapsibleLayerHtml(T(sec[1], sec[2]), T(sec[3], sec[4]),
                                                    layerCells);
            root.appendChild(holder.firstElementChild);
        });
    }

    // ------------------------------------------------------------------
    // Kayıt — CORRELATION sekmesi; alan listesi boş (özel blok enjekte)
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Experimental Correlation — Model vs Static-Fire Database',
        titleKey: 'panel.correlation.title',
        category: 'CORRELATION',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [],
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (comparative_panel deseni)
    window.CorrelationPanel = {
        _render: render,
        _orderCells: orderCells,
        _cellTableHtml: cellTableHtml,
        _augmentSection: augmentSection,
        get lastData() { return lastData; },
        run: run,
    };
})();
