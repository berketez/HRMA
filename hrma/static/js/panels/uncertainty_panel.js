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
         sensitivity:{ key:[{param, rho, noise_floor, significant}
                            |rho| azalan] },
         sensitivity_status:'modelled'|'not_modelled',
         sensitivity_basis:'...', sensitivity_method_note:'...',
         sensitivity_meta:{ noise_floor, n_used, min_samples, ... } }

   DUYARLILIK ÇİZİMİNİN KURALI (v2.6.27 E5):
     Tornado "hangi girdi amacı gerçekten oynatıyor" sorusunu yanıtlar.
     Bu yüzden GÜRÜLTÜ SİNYAL GİBİ ÇİZİLEMEZ: uçtan gelen 'significant'
     hükmü (|rho| > noise_floor) çubuğun görünümünü belirler, panel kendi
     eşiğini UYDURMAZ. Ölçüldü (2026-08-18, katı motor n=60): max_pressure
     çıktısında DÖRT parametrenin dördü de gürültü tabanının (0,324)
     altındaydı; hüküm taşınmadan önce panel bunları yeşil/kırmızı sıralı
     bir tornado olarak çiziyordu, yani okuyucu "yoğunluk basıncı sürüyor"
     sonucunu ÖRNEKLEME GÜRÜLTÜSÜNDEN çıkarıyordu.
     Uç sıralamayı hiç üretmediyse (status='not_modelled') grafik ÇİZİLMEZ;
     yerine ucun kendi gerekçe metni gösterilir — sıfır/boş çubuk yok.
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

    // Tornado çubuk tavanı: |rho| sıralı listeden en çok bu kadarı çizilir.
    // Kesme OLURSA beyan edilir (sessiz veri kaybı yok — kalan parametre
    // sayısı grafiğin altında yazılır).
    const TORNADO_MAX_BARS = 6;

    // Plotly düzeni CSS var() ÇÖZMEZ; theme.css jetonlarının HEX ikizleri
    // burada adlarıyla durur (kalıp: panels/stability_panel.js K4 bloğu).
    // Bu üçlü theme.css ile bekçiyle kilitlidir (test_duyarlilik_e5.py).
    const GREEN_HEX = '#2dd4a8';    // --hd-green   : pozitif ve ANLAMLI ρ
    const RED_HEX = '#ff5d73';      // --hd-red     : negatif ve ANLAMLI ρ
    const INK_DIM_HEX = '#7d97a5';  // --hd-ink-dim : gürültü tabanı altı

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
        // ÖH D31 · OH-D30-06: duyarlık merdiveni aynı, ayraç yerel.
        if (a >= 100) return U.num(x, 1);
        if (a >= 1) return U.num(x, 2);
        return U.num(x, 4);
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
    // v3.0.1 N-girdi-1: girdinin "?" ipucu — ortak bileşen (field_help.js →
    // HRMAHelp); anahtar çağrıda LİTERAL. Bileşen yoksa basılmaz.
    function helpHtml(key) {
        if (!window.HRMAHelp || typeof window.HRMAHelp.html !== 'function') return '';
        return window.HRMAHelp.html(key, T(key, ''));
    }

    function customFormHtml() {
        const opts = LEVELS.map(function (l) {
            return '<option value="' + l[0] + '" data-i18n="' + l[2] + '">'
                + T(l[2], l[1]) + '</option>';
        }).join('');
        return `<div id="uq_custom" style="margin:10px 0;">
            <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                <div class="form-group" style="min-width:220px;">
                    <div class="ad-field-head"><label data-i18n="panel.uncertainty.fLevel">${
                        T('panel.uncertainty.fLevel', 'Analysis Level')}</label>${
                        helpHtml('panel.uncertainty.help.level')}</div>
                    <select id="uq_level">${opts}</select>
                </div>
                <div class="form-group" style="width:110px;">
                    <div class="ad-field-head"><label data-i18n="panel.uncertainty.fSeed">${
                        T('panel.uncertainty.fSeed', 'Seed')}</label>${
                        helpHtml('panel.uncertainty.help.seed')}</div>
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
                // V3 KK 3. tur (§28-50 (c)) — RET OKUNUR CÜMLEYLE.
                // ÖLÇÜLDÜ (KLV 14 Eki + kk3/olc_uq.py, örnek hibrit): ekranda
                // yalnız 'HATA: non_physical_uncertainty_input' vardı; gövde
                // alan adını (invalid_fields) ve gerekçeyi ZATEN taşıyordu.
                // Cümle güvertenin ortak ret okuyucusundan (U.rejectText):
                // bilinen kod sözlük metni, alanlar adıyla; tanınmayan kod
                // HAM + işaretli (uydurma yok). Yalnız MAKİNE KODU taşıyan
                // retler bu yoldan geçer; ucun cümle olarak yazdığı ret
                // (ör. 'seed' reddi) ve okuyucu yoksa eski davranış.
                if (data && typeof data === 'object'
                        && typeof data.error === 'string'
                        && /^[a-z][a-z0-9_]*$/.test(data.error)
                        && typeof U.rejectText === 'function') {
                    throw new Error(U.rejectText(data, resp.status, {
                        non_physical_uncertainty_input: [
                            'panel.uncertainty.errNonPhysicalInput',
                            'No uncertainty analysis was run: every distribution '
                            + 'is centred on a motor input, and the inputs below '
                            + 'hold a value that cannot exist. Nothing was '
                            + 'clamped or replaced by a default.'],
                    }));
                }
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
                // ÖH D25 / P11B2-12 — SAHTE İLERLEME YASAĞI: `|| 0`
                // yedeği, uç `progress` alanını yayımlamadığında ekrana
                // "— 0%" yazıyordu. Yüzde yalnız uç gerçekten bir oran
                // bildirdiğinde basılır; bildirmezse durum yüzdesiz
                // söylenir (ilerleme UYDURULMAZ).
                if (Number.isFinite(job.progress)) {
                    setStatus(U.tf('panel.uncertainty.jobProgress',
                        { state: job.state.toUpperCase(),
                          pct: Math.round(100 * job.progress) },
                        'HIGH-FIDELITY JOB {state} — {pct}%'));
                } else {
                    setStatus(U.tf('panel.uncertainty.jobProgressNoPct',
                        { state: job.state.toUpperCase() },
                        'HIGH-FIDELITY JOB {state} — progress not reported'));
                }
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
        U.purgePlots(root);   // eski grafiklerin resize dinleyicileri sızmasın
        root.innerHTML = '';
        render(data, root);
        root.style.display = 'block';
        setStatus('');
    }

    // ------------------------------------------------------------------
    // Görselleştirme
    // ------------------------------------------------------------------
    /* ÖH D26 · P11B4-17 — DAĞILIMI OLMAYAN ÇIKTI GÜVEN BANDI GİBİ
       BASILIYORDU.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531):
         sunucu_std_yayini = 1 · kart_hepsini_basiyor = 1
         dagilim_kapisi = 0 · dejenere_kart_ayri = 0
         secici_yalniz_histogram = 1
       Panel `Object.keys(data.outputs)` ile HER çıktıyı aynı biçimde
       "P50 [P5, P95] güven bandı" kartı olarak basıyor ve histogram
       seçicisine sokuyordu. Monte Carlo koşumunda bir çıktı hiçbir
       belirsiz parametreden etkilenmiyorsa σ = 0 olur: o çıktının P5,
       P50 ve P95'i AYNI SAYIDIR. Ekranda ise "[x, x]" bir BAND gibi
       duruyor ve histogramı tek çubuktan ibaret çıkıyordu — kullanıcı
       ölçülmemiş bir belirsizliği ölçülmüş sanıyordu (doktrin 6).

       Kapı: dağılım VAR mı? Ölçüt ucun kendi `std` alanıdır; alan
       gelmiyorsa yüzdeliklerin özdeşliğine bakılır. Sayı uydurulmaz,
       kart SİLİNMEZ — dejenere çıktı KENDİ biçiminde (tek değer,
       "no distribution" imiyle) basılır ve histogram seçicisine
       GİRMEZ. */
    function dagilimVar(o) {
        if (!o || typeof o !== 'object') return false;
        if (typeof o.std === 'number' && isFinite(o.std)) return o.std > 0;
        // `std` yoksa: yayımlanan yüzdelikler birbirinden farklı mı?
        const p5 = o.p5, p95 = o.p95;
        if (typeof p5 === 'number' && typeof p95 === 'number'
                && isFinite(p5) && isFinite(p95)) {
            return p5 !== p95;
        }
        // Ne σ ne yüzdelik geldi: BAND İDDİA EDİLMEZ (fail-closed).
        return false;
    }

    /* Dejenere çıktı kartı: tek değer + ucun kendi σ'sı. Band, medyan
       yorumu ve yüzdelik köşeli parantezi YOKTUR. */
    function degenerateCard(key, o) {
        const name = escapeHtml(labelFor(key));
        return `<div data-uq-degenerate="1"
                style="border:1px dashed var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:10px 14px;
                min-width:190px; flex:1;
                background:var(--hd-inset, rgba(6,14,26,0.85));">
            <div style="font-size:0.68rem; color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); text-transform:uppercase;
                 letter-spacing:0.08em;">${name}</div>
            <div style="font-size:1.2rem; font-family:var(--hd-mono);
                 color:var(--hd-ink-dim, #7d97a5); margin-top:2px;">
                ${fmtVal(o.p50)}</div>
            <div style="font-family:var(--hd-mono); font-size:0.72rem;
                 color:var(--hd-ink-dim, #7d97a5); margin-top:4px;">
                ${T('panel.uncertainty.noDistribution',
                    'no distribution in this run — every sample returned the '
                    + 'same value (std = 0); this output is not sensitive to '
                    + 'any of the sampled parameters')}</div>
            <div style="font-family:var(--hd-mono); font-size:0.7rem;
                 color:var(--hd-ink-dim, #7d97a5); margin-top:4px;">
                ${T('panel.uncertainty.nominal', 'nominal')} ${fmtVal(o.nominal)} · σ ${fmtVal(o.std)}</div>
        </div>`;
    }

    function ciCard(key, o) {
        // P11B4-17 — dağılımı olmayan çıktı BAND kartı olarak basılmaz.
        if (!dagilimVar(o)) return degenerateCard(key, o);
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
            + samplerCards(data)
            + '</div>';
    }

    /* ÖH D30 · P11B4-19 — KOŞUMUN KÜNYESİ EKRANA HİÇ ÇIKMIYORDU.
       ÖLÇÜLDÜ (a2/once.json: P11B4-19_panel_distributions = 0,
       _panel_sampler = 0, _panel_uq_version = 0): uç künyenin TAMAMINI
       yayımlıyor — `sampler` (örnekleyici: LHS / Sobol / MC),
       `uq_version` (UQ çekirdeğinin sürümü) ve `inputs_used` (her belirsiz
       girdinin dağılım tanımı + literatür künyesi; uncertainty.py:948,
       `UncertainInput.describe()`) — panel üçünü de okumuyordu. Kullanıcı
       "P50 [P5, P95]" bandına bakıp bandın HANGİ dağılımlardan, hangi
       örnekleyiciyle ve hangi sürümle çıktığını göremiyordu; aynı ekran
       iki farklı dağılım kümesinden aynı biçimde çıkıyordu.

       Fail-closed: alan gelmiyorsa kart/satır HİÇ basılmaz — "—" ile
       doldurulmaz, varsayılan uydurulmaz. */
    function samplerCards(data) {
        var html = '';
        if (data.sampler) {
            html += U.statCard(T('panel.uncertainty.cardSampler', 'SAMPLER'),
                escapeHtml(String(data.sampler)), '', 'info',
                T('panel.uncertainty.cardSamplerTip',
                  'Sampling scheme the endpoint used to draw the inputs'));
        }
        if (data.uq_version) {
            html += U.statCard(T('panel.uncertainty.cardUqVersion', 'UQ CORE'),
                escapeHtml(String(data.uq_version)), '', 'dim',
                T('panel.uncertainty.cardUqVersionTip',
                  'Version of the uncertainty core that produced this run'));
        }
        return html;
    }

    /* Dağılım künyesi tablosu — `inputs_used` kaydının KENDİ alanları.
       Sayı türetilmez; alan yoksa hücre çizilmez (fail-closed). */
    function distributionsHtml(data) {
        const list = Array.isArray(data.inputs_used) ? data.inputs_used : null;
        if (!list || !list.length) return '';
        const TD = 'padding:4px 8px; border-bottom:1px solid '
            + 'var(--hd-line, rgba(0,229,255,0.14)); font-size:0.72rem;';
        const satirlar = list.map(function (d) {
            if (!d || typeof d !== 'object') return '';
            const etiket = d.dist_label
                ? escapeHtml(String(d.dist_label))
                : `<span style="color:var(--hd-ink-dim, #7d97a5);">${
                    escapeHtml(T('panel.uncertainty.distUnreported',
                                 'distribution not reported'))}</span>`;
            const uygular = d.applies_to
                ? escapeHtml(String(d.applies_to)) : '';
            const kunye = d.source_note
                ? escapeHtml(String(d.source_note)) : '';
            return `<tr>
                <td style="${TD} font-family:var(--hd-mono);">${
                    escapeHtml(String(d.name != null ? d.name : '?'))}</td>
                <td style="${TD} font-family:var(--hd-mono);">${etiket}</td>
                <td style="${TD} font-family:var(--hd-mono);">${
                    escapeHtml(String(d.mode != null ? d.mode : ''))}</td>
                <td style="${TD}">${uygular}</td>
                <td style="${TD} color:var(--hd-ink-dim, #7d97a5);">${kunye}</td>
            </tr>`;
        }).join('');
        const TH = TD + ' color:var(--hd-ink-dim, #7d97a5);'
            + ' font-family:var(--hd-mono); font-size:0.68rem;'
            + ' text-transform:uppercase; letter-spacing:0.06em;';
        return `<details data-uq-distributions="${list.length}"
                style="margin:10px 0; border:1px solid
                var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:8px 12px;">
            <summary style="cursor:pointer; color:var(--hd-ink-strong, #eaf7fb);">
                ${escapeHtml(T('panel.uncertainty.distTitle',
                               'Input distributions this run sampled'))}
                <span style="font-family:var(--hd-mono); font-size:0.7rem;
                    color:var(--hd-ink-dim, #7d97a5);">(${list.length})</span>
            </summary>
            <table style="width:100%; border-collapse:collapse; margin-top:6px;">
                <tr>
                    <th style="${TH} text-align:left;">${escapeHtml(
                        T('panel.uncertainty.distName', 'input'))}</th>
                    <th style="${TH} text-align:left;">${escapeHtml(
                        T('panel.uncertainty.distLabel', 'distribution'))}</th>
                    <th style="${TH} text-align:left;">${escapeHtml(
                        T('panel.uncertainty.distMode', 'applied as'))}</th>
                    <th style="${TH} text-align:left;">${escapeHtml(
                        T('panel.uncertainty.distApplies', 'affects'))}</th>
                    <th style="${TH} text-align:left;">${escapeHtml(
                        T('panel.uncertainty.distSource', 'source'))}</th>
                </tr>
                ${satirlar}
            </table>
        </details>`;
    }

    /* ÖH D37 A1b panel-js · OH-D30-12 JS AYAĞI — BANDIN KAPSAMI EKRANDA.

       ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/panel-js/a1/once/olcum.json,
       `alan_gecisleri`): uç gövdesi (`_uq_contract_body`, A1a uc-kapi)
       `conditionality` bloğunu dokuz alanıyla yayımlıyor; bu panelde
       dokuz alanın DOKUZU da 0 kez geçiyordu. Kullanıcı "P50 [P5, P95]"
       bandını motorun gerçek performansı için bir güven aralığı sanıyordu;
       oysa ucun kendi bloğu bandın yalnız LİSTELENEN girdilerin
       dağılımından çıktığını, girdilerin bağımsız varsayıldığını,
       listelenmeyen her girdinin nominalde dondurulduğunu ve MODEL
       HATASININ banda girmediğini söylüyor.

       Alan adları sözleşmedir (kural 11 — hrma/analysis/uncertainty.py
       `_conditionality_block`); panel ad UYDURMAZ, sayı TÜRETMEZ, sunucu
       düzyazısını çeviri kanalından (I18N.serverText) geçirir. Blok yoksa
       (absent_in_response) satır da kutu da YOK — fail-closed. Okuma AÇIK
       özellik erişimiyle yapılır (`c.applies_to`), dinamik `c[ad]` ile
       değil: ters-yön sözleşme bekçileri okuma envanterini kaynaktan
       çıkarır. */
    function srvText(text) {
        const s = String(text);
        return (window.I18N && typeof window.I18N.serverText === 'function')
            ? window.I18N.serverText(s) : s;
    }

    function conditionalityHtml(data) {
        const c = data && data.conditionality;
        if (!c || typeof c !== 'object') return '';
        const TD = 'padding:3px 8px; border-bottom:1px solid '
            + 'var(--hd-line, rgba(0,229,255,0.14)); font-size:0.72rem;'
            + ' vertical-align:top;';
        const satirlar = [];
        function satir(alan, etiket, degerHtml) {
            satirlar.push('<tr data-uq-cond-field="' + alan + '">'
                + '<td style="' + TD + ' color:var(--hd-ink-dim, #7d97a5);">'
                + escapeHtml(etiket) + '</td>'
                + '<td style="' + TD + ' font-family:var(--hd-mono);'
                + ' color:var(--hd-ink-dim, #7d97a5);">' + alan + '</td>'
                + '<td style="' + TD + ' color:var(--hd-ink, #cfe8f2);">'
                + degerHtml + '</td></tr>');
        }
        const duz = function (v) { return escapeHtml(srvText(v)); };
        const tam = function (v) {
            return (typeof v === 'number' && isFinite(v))
                ? escapeHtml(U.num(v)) : escapeHtml(String(v));
        };
        if (c.applies_to !== undefined && c.applies_to !== null) {
            satir('applies_to', T('panel.uncertainty.condAppliesTo',
                'Applies to'), duz(c.applies_to));
        }
        if (Array.isArray(c.conditional_on_inputs)) {
            satir('conditional_on_inputs', T('panel.uncertainty.condInputs',
                'Conditional on these sampled inputs'),
                '<span style="font-family:var(--hd-mono);">'
                + escapeHtml(c.conditional_on_inputs.join(', ')) + '</span>');
        }
        if (c.input_count !== undefined && c.input_count !== null) {
            satir('input_count', T('panel.uncertainty.condInputCount',
                'Number of sampled inputs'), tam(c.input_count));
        }
        if (c.frozen_at_nominal !== undefined && c.frozen_at_nominal !== null) {
            satir('frozen_at_nominal', T('panel.uncertainty.condFrozen',
                'Held at nominal'), duz(c.frozen_at_nominal));
        }
        if (c.sampler !== undefined && c.sampler !== null) {
            satir('sampler', T('panel.uncertainty.cardSampler', 'SAMPLER'),
                '<span style="font-family:var(--hd-mono);">'
                + escapeHtml(String(c.sampler)) + '</span>');
        }
        if (c.n_effective !== undefined && c.n_effective !== null) {
            satir('n_effective', T('panel.uncertainty.condNEff',
                'Samples behind the band'), tam(c.n_effective));
        }
        if (c.input_correlation_assumed !== undefined
                && c.input_correlation_assumed !== null) {
            satir('input_correlation_assumed',
                T('panel.uncertainty.condCorrelation',
                  'Input correlation assumed'),
                duz(c.input_correlation_assumed));
        }
        if (typeof c.model_form_uncertainty_included === 'boolean') {
            satir('model_form_uncertainty_included',
                T('panel.uncertainty.condModelForm',
                  'Model-form uncertainty included'),
                c.model_form_uncertainty_included
                    ? escapeHtml(T('panel.uncertainty.condYes', 'yes'))
                    : '<b>' + escapeHtml(T('panel.uncertainty.condNo', 'no'))
                      + '</b>');
        }
        if (c.interpretation !== undefined && c.interpretation !== null) {
            satir('interpretation', T('panel.uncertainty.condInterpretation',
                'How to read the band'), duz(c.interpretation));
        }
        if (!satirlar.length) return '';
        return '<div data-uq-conditionality="1" style="margin:8px 0 12px;'
            + ' border:1px solid var(--hd-line, rgba(0,229,255,0.14));'
            + ' border-left:3px solid var(--hd-amber, #ffbe46);'
            + ' border-radius:var(--hd-radius-sm, 8px); padding:8px 12px;'
            + ' background:var(--hd-inset, rgba(6,14,26,0.85));">'
            + '<div style="font-size:0.74rem; color:var(--hd-ink-strong, #eaf7fb);'
            + ' margin-bottom:4px;">'
            + escapeHtml(T('panel.uncertainty.condTitle',
                'What this P5–P95 band is conditional on'))
            + ' <span style="font-family:var(--hd-mono); font-size:0.66rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);">conditionality</span></div>'
            + '<table style="width:100%; border-collapse:collapse;">'
            + satirlar.join('') + '</table></div>';
    }

    function warningRows(data) {
        const items = [];
        if (data.failed_samples > 0) {
            items.push(U.tf('panel.uncertainty.warnFailed',
                { failed: data.failed_samples, total: data.n_samples },
                '{failed} of {total} samples failed and were excluded from the statistics.'));
        }
        // ÖH D15 / P11B4-16 — PANELİN KAZANMADIĞI NEDENSELLİK İDDİASI.
        // ÖLÇÜLDÜ (once.json, gerçek /api/uncertainty-analysis, fast/seed 42):
        // panel "Mean of C* is shifted -7.07% … (nonlinear response)" basıyor;
        // AYNI yanıtın `consistency_note` alanı bunun yanlış olduğunu yazıyor:
        //   "the dominant term is usually NOT nonlinearity here — the nominal
        //    of the following parameter(s) is pinned to the deterministic
        //    path … eta_c_star: nominal 1 vs distribution mean 0.93 (-7.00%)"
        // Kayma -7,07 ⟷ pinlenmiş parametrenin açıkladığı -7,00: kaymanın
        // %99'u panelin "doğrusalsızlık" dediği şey DEĞİL. Panel bu nedeni
        // hiçbir zaman ÖLÇMEDİ, yalnız etiketledi.
        //
        // Kapı: uç kendi tutarlılık notunu yayımlıyorsa panelin RAKİP nedensel
        // iddiası basılmaz — kayma MAKİNE ALANI olarak (yeni çeviri anahtarı
        // açılmadan) basılır, gerekçe ucun KENDİ cümlesiyle verilir. Not yoksa
        // (eski uç) eski davranış korunur; sayı hiçbir dalda uydurulmaz.
        const note = (typeof data.consistency_note === 'string')
            ? data.consistency_note.trim() : '';
        const shifts = data.mean_shift_percent || {};
        Object.keys(shifts).forEach(function (k) {
            const v = shifts[k];
            if (typeof v === 'number' && isFinite(v) && Math.abs(v) >= 1.0) {
                if (note) {
                    items.push('mean_shift_percent.' + k + ' = '
                        + (v > 0 ? '+' : '') + U.num(v, 2) + ' %');
                } else {
                    items.push(U.tf('panel.uncertainty.warnShift',
                        { name: labelFor(k), shift: (v > 0 ? '+' : '') + U.num(v, 2) },
                        'Mean of {name} is shifted {shift}% from the nominal value '
                        + '(nonlinear response).'));
                }
            }
        });
        let block = U.listBlock(T('panel.uncertainty.warningsTitle', 'Uncertainty warnings'),
                                items, 'warn');
        if (note) {
            // T-ÇAPA-C2 (BELGE §8.1-3): TR ekranda 'consistency_note MC mean
            // differs …' makine adı + İngilizce paragraf basılıyordu. Etiket
            // sözlükten; cümle sunucu çeviri kanalından (tanınırsa çevrili).
            // TR'de tanınmazsa yarım çeviri YOK: Türkçe özet + kapalı "Teknik
            // ayrıntı (çözücü beyanı, çevrilmedi)" altında tam metin AYNEN
            // (DİL terim kararı 2 deseni). Makine adı title'da kalır.
            const I = window.I18N;
            const cevrili = (I && typeof I.serverText === 'function')
                ? I.serverText(note) : note;
            const tr = !!(I && I.lang === 'tr');
            const etiket = '<span title="consistency_note" style="font-family:var(--hd-mono);">'
                + escapeHtml(T('panel.uncertainty.consistencyNoteLabel', 'Consistency note'))
                + ':</span> ';
            const govde = (tr && cevrili === note)
                ? escapeHtml(T('panel.uncertainty.consistencyNoteSummary',
                    'The Monte Carlo mean differs from the nominal value; the nominal deterministic value remains the design point.'))
                  + '<details class="hd-teknik-ayrinti"><summary style="cursor:pointer;">'
                  + escapeHtml(T('common.techDetailSrv', 'Technical detail (solver statement, untranslated)'))
                  + '</summary>' + escapeHtml(note) + '</details>'
                : escapeHtml(cevrili);
            block += '<p data-uq-consistency-note="1"'
                + ' style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);'
                + ' margin:6px 0 10px;">' + etiket + govde + '</p>';
        }
        return block;
    }

    function selectableKeys(data) {
        return Object.keys(data.outputs || {}).filter(function (k) {
            const o = data.outputs[k];
            const h = o && o.histogram;
            // P11B4-17: histogramın VARLIĞI yetmez — dağılımı olmayan
            // çıktının histogramı tek çubuktur ve "dağılım" diye
            // gösterilemez.
            return dagilimVar(o)
                && h && Array.isArray(h.edges) && Array.isArray(h.counts);
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
        // react: aynı div'e tekrar çizimde (çıktı seçici değişince) tam
        // yıkım/yeniden kurulum yerine fark tabanlı güncelleme (plotly 1.34+)
        Plotly.react(plotEl, [{
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

    // ------------------------------------------------------------------
    // Duyarlılık (tornado) — SAF katman
    // ------------------------------------------------------------------
    // Aşağıdaki üç fonksiyon DOM'a dokunmaz ve Plotly çağırmaz: yanıttan
    // çizim nesnesini kurar. Ayrılma sebebi, bekçilerin izleri yanıtın
    // KENDİ dizileriyle karşılaştırabilmesidir (kalıp:
    // panels/stability_panel.js _rootLocusFigure).

    function sensitivityRows(data, key) {
        const rows = (data && data.sensitivity) ? data.sensitivity[key] : null;
        return Array.isArray(rows) ? rows : [];
    }

    // Gürültü tabanı YALNIZ yanıttan okunur (önce skaler meta, sonra satır
    // künyesi). Hiçbiri yoksa null döner — panel taban UYDURMAZ.
    function noiseFloorOf(data, rows) {
        const meta = (data && data.sensitivity_meta) || {};
        if (typeof meta.noise_floor === 'number' && isFinite(meta.noise_floor)) {
            return meta.noise_floor;
        }
        for (let i = 0; i < rows.length; i++) {
            const v = rows[i] && rows[i].noise_floor;
            if (typeof v === 'number' && isFinite(v)) return v;
        }
        return null;
    }

    // Satırın hükmü: uçtan gelen 'significant' TEK KAYNAKTIR. Alan yoksa
    // (eski çekirdek) tabanla karşılaştırılır; taban da yoksa hüküm YOK
    // sayılır (null) ve çubuk nötr çizilir — panel kendi eşiğini uydurmaz.
    function rowSignificant(row, floor) {
        if (row && typeof row.significant === 'boolean') return row.significant;
        if (row && typeof row.rho === 'number'
                && typeof floor === 'number' && isFinite(floor)) {
            return Math.abs(row.rho) > floor;
        }
        return null;
    }

    function fmtRho(x) {
        if (typeof x !== 'number' || !isFinite(x)) return '—';
        // ÖH D31 · OH-D30-06: biçim tek kaynaktan (I18N.number) — TR kipinde virgül.
        return (x >= 0 ? '+' : '−') + U.num(Math.abs(x), 3);
    }

    /**
     * Tornado çizim nesnesi. Dönen alanlar:
     *   status : 'modelled' | 'not_modelled'
     *   notes  : grafiğin ALTINA yazılan beyan satırları (uçtan gelen
     *            gerekçe + yöntem notu + kesme beyanı)
     *   traces / layout : yalnız status='modelled' iken
     * İzlerin x/y/text dizileri yanıt satırlarından TÜRETİLİR; bu dosyada
     * çizime giren sayısal dizi literali YOKTUR.
     */
    function tornadoFigure(data, key) {
        const status = (data && data.sensitivity_status) || null;
        const rows = sensitivityRows(data, key);
        const notes = [];
        const basis = data && data.sensitivity_basis;

        // Uç sıralamayı ÜRETMEDİYSE panel de üretmez: gerekçe OLDUĞU GİBİ.
        if (status === 'not_modelled' || !rows.length) {
            notes.push(basis || T('panel.uncertainty.noSensitivity',
                'No sensitivity data available for this output.'));
            return { status: 'not_modelled', notes: notes,
                     traces: null, layout: null };
        }

        const floor = noiseFloorOf(data, rows);
        const shown = rows.slice(0, TORNADO_MAX_BARS);
        // |rho| azalan gelir; yatay barda en etkili en ÜSTTE dursun
        const ordered = shown.slice().reverse();
        const flags = ordered.map(function (r) {
            return rowSignificant(r, floor);
        });

        // RENK TEK BAŞINA TAŞIYICI DEĞİL (analysis_dock.js E3 ilkesi,
        // WCAG 1.4.1): işaret zaten çubuğun YÖNÜ ile, anlamlılık ise
        // desen + metin eki ile de taşınır. Renk üçüncü, yedek katman.
        const trace = {
            type: 'bar',
            orientation: 'h',
            x: ordered.map(function (r) { return r.rho; }),
            y: ordered.map(function (r) { return r.param; }),
            text: ordered.map(function (r, i) {
                return fmtRho(r.rho) + (flags[i] === false
                    ? ' ' + T('panel.uncertainty.belowFloorTag', '(noise)') : '');
            }),
            textposition: 'auto',
            marker: {
                color: ordered.map(function (r, i) {
                    if (flags[i] === false) return INK_DIM_HEX;
                    return (r.rho >= 0) ? GREEN_HEX : RED_HEX;
                }),
                pattern: {
                    shape: flags.map(function (f) { return f === false ? '.' : ''; }),
                },
            },
            hovertemplate: '%{y}: ρ = %{x:.3f}<extra></extra>',
        };

        const shapes = [];
        if (typeof floor === 'number' && isFinite(floor) && floor > 0) {
            // Taban çizgileri yanıttaki DEĞERDEN kurulur (literal değil).
            [floor, -floor].forEach(function (xv) {
                shapes.push({ type: 'line', x0: xv, x1: xv, y0: 0, y1: 1,
                    yref: 'paper', line: { width: 1, dash: 'dot',
                                           color: INK_DIM_HEX } });
            });
            notes.push(U.tf('panel.uncertainty.floorNote', { floor: U.num(floor, 3) },
                'Dotted lines mark the noise floor ±{floor}: bars inside this '
                + 'band are indistinguishable from sampling noise and are drawn '
                + 'dimmed/dotted, not ranked as real effects.'));
        }
        if (rows.length > shown.length) {
            notes.push(U.tf('panel.uncertainty.tornadoTruncated',
                { shown: shown.length, total: rows.length },
                'Showing the {shown} strongest of {total} parameters by |ρ|.'));
        }
        if (basis) notes.push(basis);
        if (data.sensitivity_method_note) notes.push(data.sensitivity_method_note);

        return {
            status: 'modelled',
            notes: notes,
            traces: [trace],
            layout: {
                title: U.tf('panel.uncertainty.chartTornado',
                    { name: labelFor(key), n: shown.length },
                    'Sensitivity Tornado — {name} (top {n} by |ρ|)'),
                xaxis: {
                    title: T('panel.uncertainty.axisSpearman',
                             'Spearman rank correlation ρ'),
                    range: [-1, 1],
                },
                shapes: shapes,
                height: 320,
                margin: { l: 160 },
            },
        };
    }

    function noteBlockHtml(notes) {
        if (!notes || !notes.length) return '';
        return '<div data-uq-sens-basis="1" style="font-family:var(--hd-mono,'
            + ' monospace); font-size:0.66rem; line-height:1.5;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;">'
            + notes.map(function (n) {
                return '<p style="margin:0 0 4px;">' + escapeHtml(n) + '</p>';
            }).join('')
            + '</div>';
    }

    function drawTornado(data, key, plotEl, noteEl) {
        const fig = tornadoFigure(data, key);
        if (noteEl) noteEl.innerHTML = noteBlockHtml(fig.notes);
        if (fig.status !== 'modelled') {
            // Önceki seçimden kalan canlı grafik varsa serbest bırak
            // (textContent grafiği purge'suz siler, dinleyici sızar)
            U.purgePlots(plotEl);
            plotEl.textContent = fig.notes[0] || '';
            return;
        }
        if (typeof Plotly === 'undefined') {
            plotEl.textContent = T('common.plotlyMissing', 'Plotly is not loaded — chart skipped.');
            return;
        }
        // react: seçici değişiminde aynı div'e fark tabanlı güncelleme
        Plotly.react(plotEl, fig.traces, fig.layout,
                     { responsive: true, displaylogo: false });
    }

    function render(data, root) {
        // 1) Koşu özeti + uyarılar
        const head = document.createElement('div');
        head.innerHTML = U.sectionTitle(T('panel.uncertainty.secSummary', 'Run Summary'))
            + summaryCards(data)
            + warningRows(data)
            // ÖH D30 · P11B4-19 — dağılım künyesi koşu özetinin altında.
            + distributionsHtml(data);
        root.appendChild(head);

        // 2) Çıktı başına CI kartları
        const keys = Object.keys(data.outputs || {});
        const cards = document.createElement('div');
        cards.innerHTML = U.sectionTitle(T('panel.uncertainty.secCi',
            'Output Confidence Intervals — P50 with [P5, P95] band'))
            // ÖH D37 A1b panel-js · OH-D30-12 — bandın kapsamı, bandı
            // okuyan kartların HEMEN üstünde (katlanmaz; yoksa hiç yok).
            + conditionalityHtml(data)
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
        // Duyarlılık beyanı grafiğin ALTINDA, KENDİ kabında durur: dayanak
        // (kaç örnek, hangi örneklemden) ve yöntem sınırı (yalnız monotonik
        // etki) kullanıcıya ULAŞMADAN sıralama okunamaz.
        const noteEl = document.createElement('div');
        wrap.appendChild(histEl);
        wrap.appendChild(tornEl);
        wrap.appendChild(noteEl);
        root.appendChild(wrap);

        function redraw(key) {
            // Aynı çerçevede, layout olmadan çizilirse Plotly kap genişliğini
            // ölçemez ve 700px varsayılanına düşer (kap ~1200px iken grafik
            // yarım kalır). Çizim bir sonraki çerçeveye ertelenir.
            window.requestAnimationFrame(function () {
                drawHistogram(data, key, histEl);
                drawTornado(data, key, tornEl, noteEl);
            });
        }
        wrap.querySelector('#uq_out_select')
            .addEventListener('change', function (ev) { redraw(ev.target.value); });
        redraw(selKeys[0]);

        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, data, { deep: true });
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
        _conditionalityHtml: conditionalityHtml,
        // Duyarlılık saf katmanı (bekçiler izleri yanıtla karşılaştırsın)
        _tornadoFigure: tornadoFigure,
        _sensitivityRows: sensitivityRows,
        _noiseFloorOf: noiseFloorOf,
        _rowSignificant: rowSignificant,
        _selectableKeys: selectableKeys,
        _maxBars: TORNADO_MAX_BARS,
        _themeHex: { green: GREEN_HEX, red: RED_HEX, dim: INK_DIM_HEX },
        get lastData() { return lastData; },
        run: run,
    };
})();
