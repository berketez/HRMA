/* ====================================================================
   HRMA Analiz Güvertesi — Belirsizlik (Monte Carlo UQ) Paneli
   --------------------------------------------------------------------
   POST /api/uncertainty-analysis'i UI'a bağlar. İstek gövdesi İÇ İÇE
   olduğundan ({motor_type, level, seed, inputs:{...}}) güvertenin düz
   buildPayload'ı kullanılamaz — comparative_panel deseniyle özel blok
   enjekte edilir, dock'un otomatik "Run Analysis" butonu gizlenir ve
   POST'u bu panel kendi butonuyla yapar.

   Girdi toplama: sayfanın MEVCUT /calculate form-toplayıcısı yeniden
   kullanılır — solid/liquid sayfalarında collectAllParameters(),
   hibrit sayfada getFormData() (aynı gövde /calculate'e gider).

   Sözleşme (v2.5.0 G3):
     fast/engineering → senkron yanıt:
       { status:'ok', motor_type, level, n_samples, failed_samples, seed,
         timing_s, mean_shift_percent:{out:%}, outputs:{ key:{ nominal,
         mean, std, cv, p5, p25, p50, p75, p95,
         histogram:{edges:[21], counts:[20]} } },
         sensitivity:{ key:[{param, rho} |rho| azalan] } }
     high_fidelity → { status:'queued', job_id } → GET /api/jobs/<id>
       ({status:'success', job:{state, progress, result|error}}) ile
       yoklanır; job.result yukarıdaki 'ok' gövdesidir.
     Hata → { status:'error', error:'...' } (mesaj OLDUĞU GİBİ, kırmızı).

   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir (renk
   zorlanmaz; yalnız tornado işaret tonu trace seviyesinde verilir).
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    const ENDPOINT = '/api/uncertainty-analysis';
    const PANEL_ID = 'uncertainty';

    const LEVELS = [
        ['fast', 'Fast Screening (~10-30 s)', 'uq.levelFast'],
        ['engineering', 'Engineering (~1-3 min)', 'uq.levelEng'],
        ['high_fidelity', 'High-Fidelity (~10-15 min)', 'uq.levelHigh'],
    ];

    const POLL_INTERVAL_MS = 2000;
    const POLL_MAX_TRIES = 900;        // 2 s x 900 = 30 dk emniyet tavanı

    // İnsan-okunur çıktı adları (sözleşmedeki anahtar kümesi; bilinmeyen
    // anahtar ad dönüşümüyle gösterilir — uydurma birim YOK)
    const OUTPUT_LABEL_KEYS = {
        isp: ['Isp', 'out.isp'],
        thrust: ['Thrust', 'out.thrust'],
        chamber_pressure: ['Chamber Pressure', 'out.chamberPressure'],
        c_star: ['C*', 'out.cStar'],
        total_impulse: ['Total Impulse', 'out.totalImpulse'],
        regression_rate_avg: ['Avg Regression Rate', 'out.regressionRateAvg'],
        max_pressure: ['Max Pressure', 'out.maxPressure'],
        mdot_total: ['Total Mass Flow', 'out.mdotTotal'],
    };

    let pollTimer = null;
    let lastData = null;

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function labelFor(key) {
        const pair = OUTPUT_LABEL_KEYS[key];
        if (pair) return T(pair[1], pair[0]);
        return key.replace(/_/g, ' ').replace(/\b\w/g, function (c) {
            return c.toUpperCase();
        });
    }

    // Sayı büyüklüğüne uyumlu biçim (Isp ~200 ile It ~1e5 aynı kartta)
    function fmtVal(x) {
        if (x == null || !isFinite(x)) return '—';
        const a = Math.abs(x);
        if (a !== 0 && (a >= 1e5 || a < 1e-2)) return x.toExponential(3);
        if (a >= 100) return x.toFixed(1);
        if (a >= 1) return x.toFixed(2);
        return x.toFixed(4);
    }

    // ------------------------------------------------------------------
    // Girdi toplama — sayfanın kendi /calculate toplayıcısı
    // ------------------------------------------------------------------
    function collectInputs() {
        try {
            if (typeof window.collectAllParameters === 'function') {
                return window.collectAllParameters();       // solid / liquid
            }
        } catch (e) { /* aşağı düş */ }
        try {
            if (typeof window.getFormData === 'function') {
                return window.getFormData();                // hybrid
            }
        } catch (e) { /* aşağıda null */ }
        return null;
    }

    // ------------------------------------------------------------------
    // Özel kontrol satırı (level + seed + Run)
    // ------------------------------------------------------------------
    function customFormHtml() {
        const opts = LEVELS.map(function (l) {
            return '<option value="' + l[0] + '" data-i18n="' + l[2] + '">'
                + T(l[2], l[1]) + '</option>';
        }).join('');
        return `<div id="uq_custom" style="margin:10px 0;">
            <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                <div class="form-group" style="min-width:220px;">
                    <label data-i18n="panel.uncertainty.fLevel">${
                        T('panel.uncertainty.fLevel', 'Analysis Level')}</label>
                    <select id="uq_level">${opts}</select>
                </div>
                <div class="form-group" style="width:110px;">
                    <label data-i18n="panel.uncertainty.fSeed">${
                        T('panel.uncertainty.fSeed', 'Seed')}</label>
                    <input type="number" id="uq_seed" value="42" step="1">
                </div>
                <div class="form-group">
                    <button class="btn" type="button" id="uq_run"
                        data-i18n="panel.uncertainty.btnRun">${
                        T('panel.uncertainty.btnRun', 'Run Uncertainty Analysis')}</button>
                </div>
            </div>
            <p style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;"
                data-i18n="panel.uncertainty.intro">${T('panel.uncertainty.intro',
                'Inputs are taken from the motor form above exactly as a normal '
                + 'calculation would send them. High-Fidelity runs are queued and '
                + 'polled in the background.')}</p>
        </div>`;
    }

    function augmentSection() {
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        if (!sec) return false;
        if (document.getElementById('uq_custom')) return true;   // idempotent
        // Güvertenin otomatik butonu gizlenir: gövde iç içe olduğundan
        // buildPayload kullanılamaz — POST'u bu panel yapar.
        const dockBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (dockBtn && dockBtn.parentElement) {
            dockBtn.parentElement.style.display = 'none';
        }
        const holder = document.createElement('div');
        holder.innerHTML = customFormHtml();
        const status = document.getElementById('ad_status_' + PANEL_ID);
        sec.insertBefore(holder.firstElementChild, status);
        document.getElementById('uq_run').addEventListener('click', run);
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
    // Durum satırı yardımcıları
    // ------------------------------------------------------------------
    function setStatus(text, kind) {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        if (!status) return;
        status.textContent = text;
        status.style.color = kind === 'err'
            ? 'var(--hd-red, #ff5d73)' : 'var(--hd-ink-dim, #7d97a5)';
    }

    function stopPolling() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    // ------------------------------------------------------------------
    // Çalıştırma — fast/engineering senkron, high_fidelity iş kuyruğu
    // ------------------------------------------------------------------
    async function run() {
        const root = document.getElementById('ad_root_' + PANEL_ID);
        const btn = document.getElementById('uq_run');
        const levelEl = document.getElementById('uq_level');
        const seedEl = document.getElementById('uq_seed');
        if (!root || !btn || !levelEl) return;

        const inputs = collectInputs();
        if (!inputs) {
            setStatus(T('panel.uncertainty.noForm',
                'Could not read the motor form on this page — form collector not found.'), 'err');
            return;
        }
        const level = levelEl.value;
        const seed = seedEl ? parseInt(seedEl.value, 10) : 42;

        stopPolling();
        btn.disabled = true;
        root.style.display = 'none';
        setStatus(level === 'high_fidelity'
            ? T('panel.uncertainty.submitting', 'SUBMITTING HIGH-FIDELITY JOB…')
            : T('panel.uncertainty.sampling', 'RUNNING MONTE CARLO SAMPLING…'));

        const payload = {
            motor_type: window.AnalysisDock.getMotorType(),
            level: level,
            seed: Number.isFinite(seed) ? seed : 42,
            inputs: inputs,
        };

        try {
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                // Hata mesajı (örnek-#0 tutarlılık dahil) OLDUĞU GİBİ gösterilir
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            if (data.status === 'queued' && data.job_id) {
                pollJob(data.job_id, 0, btn, root);
                return;
            }
            finish(data, btn, root);
        } catch (err) {
            setStatus(U.tf('common.errorPrefix', { message: err.message },
                           'ERROR: {message}'), 'err');
            btn.disabled = false;
        }
    }

    function pollJob(jobId, tries, btn, root) {
        if (tries >= POLL_MAX_TRIES) {
            setStatus(U.tf('panel.uncertainty.jobTimeout', { id: jobId },
                'ERROR: high-fidelity job timed out (still running server-side, job id {id}).'),
                'err');
            btn.disabled = false;
            return;
        }
        pollTimer = setTimeout(async function () {
            try {
                const resp = await fetch('/api/jobs/' + encodeURIComponent(jobId));
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || data.status !== 'success' || !data.job) {
                    throw new Error((data && data.error) || ('HTTP ' + resp.status));
                }
                const job = data.job;
                if (job.state === 'done') {
                    finish(job.result, btn, root);
                    return;
                }
                if (job.state === 'error') {
                    throw new Error(job.error || 'job failed');
                }
                const pct = Math.round(100 * (job.progress || 0));
                setStatus(U.tf('panel.uncertainty.jobProgress',
                    { state: job.state.toUpperCase(), pct: pct },
                    'HIGH-FIDELITY JOB {state} — {pct}%'));
                pollJob(jobId, tries + 1, btn, root);
            } catch (err) {
                setStatus(U.tf('common.errorPrefix', { message: err.message },
                               'ERROR: {message}'), 'err');
                btn.disabled = false;
            }
        }, POLL_INTERVAL_MS);
    }

    function finish(data, btn, root) {
        btn.disabled = false;
        if (!data || data.status !== 'ok' || !data.outputs) {
            setStatus(U.tf('common.errorPrefix',
                { message: (data && data.error)
                    || T('panel.uncertainty.badPayload',
                         'unexpected response payload from backend') },
                'ERROR: {message}'), 'err');
            return;
        }
        lastData = data;
        root.innerHTML = '';
        render(data, root);
        root.style.display = 'block';
        setStatus('');
    }

    // ------------------------------------------------------------------
    // Görselleştirme
    // ------------------------------------------------------------------
    function ciCard(key, o) {
        const name = escapeHtml(labelFor(key));
        return `<div style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:10px 14px;
                min-width:190px; flex:1;
                background:var(--hd-inset, rgba(6,14,26,0.85));">
            <div style="font-size:0.68rem; color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); text-transform:uppercase;
                 letter-spacing:0.08em;">${name}</div>
            <div style="font-size:1.2rem; font-family:var(--hd-mono);
                 color:var(--hd-ink-strong, #eaf7fb); margin-top:2px;"
                 title="${T('panel.uncertainty.p50Tip', 'Median of the Monte Carlo sample (P50)')}">
                ${fmtVal(o.p50)}</div>
            <div style="font-family:var(--hd-mono); font-size:0.72rem;
                 color:var(--hd-cyan, #00e5ff);"
                 title="${T('panel.uncertainty.bandTip', '90% band: 5th to 95th percentile')}">
                [${fmtVal(o.p5)}, ${fmtVal(o.p95)}]</div>
            <div style="font-family:var(--hd-mono); font-size:0.7rem;
                 color:var(--hd-ink-dim, #7d97a5); margin-top:4px;">
                ${T('panel.uncertainty.nominal', 'nominal')} ${fmtVal(o.nominal)} · σ ${fmtVal(o.std)}</div>
        </div>`;
    }

    function summaryCards(data) {
        return '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard(T('panel.uncertainty.cardLevel', 'LEVEL'),
                escapeHtml(String(data.level || '—')), '',
                'info', T('panel.uncertainty.cardLevelTip', 'Requested analysis level'))
            + U.statCard(T('panel.uncertainty.cardSamples', 'SAMPLES'), String(data.n_samples != null
                ? data.n_samples : '—'), '', 'info',
                T('panel.uncertainty.cardSamplesTip', 'Monte Carlo samples evaluated'))
            + U.statCard(T('panel.uncertainty.cardFailed', 'FAILED'), String(data.failed_samples != null
                ? data.failed_samples : '—'), '',
                (data.failed_samples > 0) ? 'warn' : 'ok',
                T('panel.uncertainty.cardFailedTip', 'Samples that failed to evaluate and were excluded'))
            + U.statCard(T('panel.uncertainty.cardSeed', 'SEED'), String(data.seed != null ? data.seed : '—'),
                '', 'dim', T('panel.uncertainty.cardSeedTip', 'Random seed (reproducibility)'))
            + U.statCard(T('panel.uncertainty.cardTime', 'TIME'), fmtVal(data.timing_s), 's', 'dim',
                T('panel.uncertainty.cardTimeTip', 'Wall-clock analysis time'))
            + '</div>';
    }

    function warningRows(data) {
        const items = [];
        if (data.failed_samples > 0) {
            items.push(U.tf('panel.uncertainty.warnFailed',
                { failed: data.failed_samples, total: data.n_samples },
                '{failed} of {total} samples failed and were excluded from the statistics.'));
        }
        const shifts = data.mean_shift_percent || {};
        Object.keys(shifts).forEach(function (k) {
            const v = shifts[k];
            if (typeof v === 'number' && isFinite(v) && Math.abs(v) >= 1.0) {
                items.push(U.tf('panel.uncertainty.warnShift',
                    { name: labelFor(k), shift: (v > 0 ? '+' : '') + v.toFixed(2) },
                    'Mean of {name} is shifted {shift}% from the nominal value '
                    + '(nonlinear response).'));
            }
        });
        return U.listBlock(T('panel.uncertainty.warningsTitle', 'Uncertainty warnings'),
                           items, 'warn');
    }

    function selectableKeys(data) {
        return Object.keys(data.outputs || {}).filter(function (k) {
            const h = data.outputs[k] && data.outputs[k].histogram;
            return h && Array.isArray(h.edges) && Array.isArray(h.counts);
        });
    }

    function drawHistogram(data, key, plotEl) {
        if (typeof Plotly === 'undefined') {
            plotEl.textContent = T('common.plotlyMissing', 'Plotly is not loaded — chart skipped.');
            return;
        }
        const o = data.outputs[key];
        const edges = o.histogram.edges;
        const counts = o.histogram.counts;
        const centers = [];
        const widths = [];
        for (let i = 0; i < counts.length; i++) {
            centers.push((edges[i] + edges[i + 1]) / 2);
            widths.push(edges[i + 1] - edges[i]);
        }
        const shapes = [];
        [['p5', 'dot'], ['p50', 'solid'], ['p95', 'dot']].forEach(function (m) {
            const x = o[m[0]];
            if (typeof x === 'number' && isFinite(x)) {
                shapes.push({ type: 'line', x0: x, x1: x, y0: 0, y1: 1,
                    yref: 'paper', line: { width: 1, dash: m[1] } });
            }
        });
        Plotly.newPlot(plotEl, [{
            type: 'bar',
            x: centers,
            y: counts,
            width: widths,
            hovertemplate: labelFor(key)
                + ': %{x:.4g}<br>' + T('panel.uncertainty.count', 'count')
                + ': %{y}<extra></extra>',
        }], {
            title: U.tf('panel.uncertainty.chartHistogram', { name: labelFor(key) },
                        '{name} — Monte Carlo Distribution'),
            xaxis: { title: labelFor(key) },
            yaxis: { title: T('panel.uncertainty.axisSampleCount', 'Sample count') },
            bargap: 0.05,
            shapes: shapes,
            height: 360,
        }, { responsive: true, displaylogo: false });
    }

    function drawTornado(data, key, plotEl) {
        if (typeof Plotly === 'undefined') {
            plotEl.textContent = T('common.plotlyMissing', 'Plotly is not loaded — chart skipped.');
            return;
        }
        const rows = ((data.sensitivity || {})[key] || []).slice(0, 6);
        if (!rows.length) {
            plotEl.textContent = T('panel.uncertainty.noSensitivity',
                'No sensitivity data available for this output.');
            return;
        }
        // |rho| azalan gelir; yatay barda en etkili en ÜSTTE dursun
        const ordered = rows.slice().reverse();
        Plotly.newPlot(plotEl, [{
            type: 'bar',
            orientation: 'h',
            x: ordered.map(function (r) { return r.rho; }),
            y: ordered.map(function (r) { return r.param; }),
            marker: {
                // İşaret renk tonuyla: pozitif korelasyon yeşil, negatif kırmızı
                color: ordered.map(function (r) {
                    return (r.rho >= 0) ? 'rgba(45, 212, 168, 0.85)'
                                        : 'rgba(255, 93, 115, 0.85)';
                }),
            },
            hovertemplate: '%{y}: ρ = %{x:.3f}<extra></extra>',
        }], {
            title: U.tf('panel.uncertainty.chartTornado',
                { name: labelFor(key), n: rows.length },
                'Sensitivity Tornado — {name} (top {n} by |ρ|)'),
            xaxis: { title: T('panel.uncertainty.axisSpearman', 'Spearman rank correlation ρ'),
                     range: [-1, 1] },
            height: 320,
            margin: { l: 160 },
        }, { responsive: true, displaylogo: false });
    }

    function render(data, root) {
        // 1) Koşu özeti + uyarılar
        const head = document.createElement('div');
        head.innerHTML = U.sectionTitle(T('panel.uncertainty.secSummary', 'Run Summary'))
            + summaryCards(data)
            + warningRows(data);
        root.appendChild(head);

        // 2) Çıktı başına CI kartları
        const keys = Object.keys(data.outputs || {});
        const cards = document.createElement('div');
        cards.innerHTML = U.sectionTitle(T('panel.uncertainty.secCi',
            'Output Confidence Intervals — P50 with [P5, P95] band'))
            + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + keys.map(function (k) { return ciCard(k, data.outputs[k]); }).join('')
            + '</div>';
        root.appendChild(cards);

        // 3) Seçilebilir çıktı: histogram + tornado
        const selKeys = selectableKeys(data);
        if (!selKeys.length) return;

        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(T('panel.uncertainty.secDistribution',
                'Distribution and Sensitivity'))
            + `<div class="form-group" style="max-width:280px;">
                 <label>${T('panel.uncertainty.fOutput', 'Output')}</label>
                 <select id="uq_out_select">`
            + selKeys.map(function (k) {
                return '<option value="' + escapeHtml(k) + '">'
                    + escapeHtml(labelFor(k)) + '</option>';
            }).join('')
            + '</select></div>';
        const histEl = document.createElement('div');
        const tornEl = document.createElement('div');
        tornEl.style.marginTop = '10px';
        wrap.appendChild(histEl);
        wrap.appendChild(tornEl);
        root.appendChild(wrap);

        function redraw(key) {
            // Aynı çerçevede, layout olmadan çizilirse Plotly kap genişliğini
            // ölçemez ve 700px varsayılanına düşer (kap ~1200px iken grafik
            // yarım kalır). Çizim bir sonraki çerçeveye ertelenir.
            window.requestAnimationFrame(function () {
                drawHistogram(data, key, histEl);
                drawTornado(data, key, tornEl);
            });
        }
        wrap.querySelector('#uq_out_select')
            .addEventListener('change', function (ev) { redraw(ev.target.value); });
        redraw(selKeys[0]);
    }

    // ------------------------------------------------------------------
    // Kayıt — UNCERTAINTY sekmesi; alan listesi boş (özel blok enjekte)
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Uncertainty Quantification — Monte Carlo Confidence Bands',
        titleKey: 'panel.uncertainty.title',
        category: 'UNCERTAINTY',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [],
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (comparative_panel deseni)
    window.UncertaintyPanel = {
        _render: render,
        _collectInputs: collectInputs,
        _labelFor: labelFor,
        _fmtVal: fmtVal,
        _augmentSection: augmentSection,
        get lastData() { return lastData; },
        run: run,
    };
})();
