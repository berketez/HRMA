/* ====================================================================
   HRMA Analiz Güvertesi — Kullanıcı Verisi Doğrulama Paneli (Dalga 4A)
   --------------------------------------------------------------------
   POST /api/validation/upload-csv'yi UI'a bağlar: kullanıcı KENDİ static-fire
   CSV'sini yapıştırır/yükler, HRMA itki tahminiyle nicel karşılaştırılır
   (sentetik "doğrulama veritabanı" vitrine çıkmaz — ARGE kararı,
   docs/ANALIZ_PLATFORM_PLANI.md).

   Tahmin eğrisi kaynağı (öncelik sırası):
     1. TransientPanel.result.transient  → gerçek Pc(t)/F(t) yürüyüşü
     2. currentResults.motor.transient   → saklanmış transient eğrisi
     3. currentResults.motor.thrust + burn_time → sabit itki dikdörtgeni

   Güverte formu sayısal alan + select üretir; CSV metni için özel blok
   (textarea + dosya seçici) panel montajından sonra bölüme enjekte edilir,
   güvertenin otomatik "Run Analysis" butonu gizlenir (POST'u bu panel
   kendi butonuyla yapar — buildPayload CSV metni taşıyamaz).

   Yanıt şeması (test_client ile doğrulandı, 2026-07-14):
     { status:'success', parsed:{time,thrust,n_points,warnings},
       comparison:{metrics, grade, assessment, overlap}|null }

   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    const ENDPOINT = '/api/validation/upload-csv';
    const PANEL_ID = 'validation';

    // Yükleme boyut tavanı — tek uygulama import_ui.js'te (tavan sayfaya
    // sunucudan gelir, bu dosyada sayı yok). Modül yüklenmemişse ön denetim
    // yapılmaz; sunucu kapısı yine reddeder.
    function uploadSizeError(kind, bytes) {
        const IU = window.HRMAImportUI;
        return (IU && IU.uploadSizeError) ? IU.uploadSizeError(kind, bytes) : null;
    }
    function payloadTooLargeMessage(kind, bytes, resp, data) {
        const IU = window.HRMAImportUI;
        return (IU && IU.payloadTooLargeMessage)
            ? IU.payloadTooLargeMessage(kind, bytes, resp, data) : null;
    }
    function utf8ByteLength(text) {
        const IU = window.HRMAImportUI;
        return (IU && IU.utf8ByteLength) ? IU.utf8ByteLength(text) : null;
    }

    const GRADE_KINDS = {
        excellent: 'ok',
        good: 'info',
        fair: 'warn',
        poor: 'err',
    };

    // ------------------------------------------------------------------
    // Tahmin eğrisi sağlayıcısı (transient > saklanmış transient > sabit)
    // ------------------------------------------------------------------
    function predictedCurve() {
        try {
            const tr = window.TransientPanel && window.TransientPanel.result;
            if (tr && tr.transient && Array.isArray(tr.transient.time)
                && tr.transient.time.length > 3) {
                return { kind: 'transient',
                         time: tr.transient.time, thrust: tr.transient.thrust,
                         source: T('panel.validation.srcTransient', 'transient analysis F(t)') };
            }
        } catch (e) { /* transient paneli yoksa sıradaki kaynak */ }
        // Eski kod yalnız `currentResults.motor` altına bakıyordu; katı ve
        // sıvı yanıtları DÜZ olduğu için o iki motor tipinde tahmin kaynağı
        // hiçbir zaman bulunamıyor, panel "kaynak yok" diyordu.
        const results = window.currentResults;
        const m = results ? U.motorDict(results) : null;
        if (m && m.transient && Array.isArray(m.transient.time)
            && m.transient.time.length > 3) {
            return { kind: 'transient',
                     time: m.transient.time, thrust: m.transient.thrust,
                     source: T('panel.validation.srcStored', 'stored transient F(t)') };
        }
        // Katı motor düz sözlükte 'thrust' üretmiyor (ortalama/tepe ayrı);
        // merkezi okuyucu motor tipine göre doğru anahtarı seçer.
        const thrust = results ? U.readThrust(results) : undefined;
        const burnTime = results ? U.readBurnTime(results) : undefined;
        if (Number.isFinite(thrust) && Number.isFinite(burnTime) && burnTime > 0) {
            // ÖH D27 / P11B4-23 — BU EĞRİ ÖLÇÜM DEĞİL, İKİ NOKTALI
            // TASARIM NOKTASIDIR. `kind` makine künyesidir: lejant ve
            // sonuç bloğu bunu okuyup kullanıcıya SÖYLER (aşağıya bakınız).
            return { kind: 'design_point',
                     time: [0, burnTime], thrust: [thrust, thrust],
                     source: T('panel.validation.srcDesign', 'design point (constant thrust)') };
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Özel form bloğu (textarea + dosya seçici + karşılaştır butonu)
    // ------------------------------------------------------------------
    function customFormHtml() {
        return `<div id="vp_custom" style="margin:10px 0;">
            <div class="form-group">
                <label data-i18n="panel.validation.csvLabel">${T('panel.validation.csvLabel',
                    'Static-Fire CSV — paste text or choose a file (columns: time [s], thrust [N])')}</label>
                <textarea id="vp_csv_text" rows="8" spellcheck="false"
                    placeholder="time,thrust&#10;0.0,0&#10;0.1,412.5&#10;0.2,896.0&#10;..."
                    style="width:100%; font-family:var(--hd-mono); font-size:0.78rem;
                    background:var(--hd-inset, rgba(6,14,26,0.85));
                    color:var(--hd-ink, #cfe8f2);
                    border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                    border-radius:var(--hd-radius-sm, 8px); padding:8px 10px;
                    resize:vertical;"></textarea>
            </div>
            <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:8px;">
                <input type="file" id="vp_csv_file"
                    accept=".csv,.txt,.eng,.rse,text/csv,text/plain"
                    style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">
                <button class="btn" type="button" id="vp_run"
                    data-i18n="panel.validation.btnCompare">${T('panel.validation.btnCompare',
                    'Compare With HRMA Prediction')}</button>
                <span id="vp_pred_source" style="font-family:var(--hd-mono); font-size:0.72rem;
                    color:var(--hd-ink-dim, #7d97a5);"></span>
            </div>
            <div style="font-family:var(--hd-mono); font-size:0.7rem;
                color:var(--hd-ink-faint, #6a8491); margin-top:4px;"
                data-i18n="panel.validation.motorFileHint">${T('panel.validation.motorFileHint',
                'Motor thrust-curve files (.eng RASP / .rse RockSim) are imported and '
                + 'compared automatically when selected.')}</div>
            <div id="vp_motor_bar" style="display:none; margin-top:8px; align-items:center;
                gap:10px; flex-wrap:wrap;"></div>
        </div>`;
    }

    function refreshPredictionSourceLabel() {
        const el = document.getElementById('vp_pred_source');
        if (!el) return;
        const pred = predictedCurve();
        el.textContent = pred
            ? U.tf('panel.validation.predSource', { source: pred.source },
                   'Prediction source: {source}')
            : T('panel.validation.noPrediction',
                'No HRMA prediction yet — run a motor calculation first (parse-only mode).');
    }

    function augmentSection() {
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        if (!sec) return false;
        if (document.getElementById('vp_custom')) return true;  // idempotent
        // Güvertenin otomatik butonu gizlenir: buildPayload yalnız sayısal
        // alan okur, CSV metnini taşıyamaz — POST'u bu panel kendisi yapar.
        const dockBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (dockBtn && dockBtn.parentElement) {
            dockBtn.parentElement.style.display = 'none';
        }
        const holder = document.createElement('div');
        holder.innerHTML = customFormHtml();
        const status = document.getElementById('ad_status_' + PANEL_ID);
        sec.insertBefore(holder.firstElementChild, status);

        document.getElementById('vp_run')
            .addEventListener('click', runValidation);
        document.getElementById('vp_csv_file')
            .addEventListener('change', function (ev) {
                const file = ev.target.files && ev.target.files[0];
                if (!file) return;
                // .eng/.rse → motor dosyası içe aktarma akışı (backend
                // /api/import/motor-file); diğer uzantılar CSV metni olarak
                // textarea'ya yüklenir (mevcut davranış korunur).
                const isMotorFile = /\.(eng|rse)$/i.test(file.name || '');
                // Dosya OKUNMADAN önce boyut tavanı (sunucudan; V3 güvenlik
                // 5. tur): aşan dosya okunmaz, gönderilmez.
                const tooBig = uploadSizeError(isMotorFile ? 'motor_file' : 'csv',
                                               file.size);
                if (tooBig) {
                    const st = document.getElementById('ad_status_' + PANEL_ID);
                    if (st) st.textContent = U.tf('common.errorPrefix',
                        { message: tooBig }, 'ERROR: {message}');
                    ev.target.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = function () {
                    const text = String(reader.result || '');
                    if (isMotorFile) {
                        importMotorFile(text, file.name);
                    } else {
                        document.getElementById('vp_csv_text').value = text;
                    }
                };
                reader.onerror = function () {
                    const st = document.getElementById('ad_status_' + PANEL_ID);
                    if (st) st.textContent = T('panel.validation.fileError',
                        'Could not read the selected file.');
                };
                reader.readAsText(file);
            });
        refreshPredictionSourceLabel();
        return true;
    }

    // Güverte DOMContentLoaded'ta kurulur; bölüm görünene dek kısa
    // aralıklarla dene (montaj yarışına dayanıklılık — flow panel deseni).
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
    // Çalıştırma — POST {'csv_text', 'predicted_curve'?}
    // ------------------------------------------------------------------
    async function runValidation() {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        const btn = document.getElementById('vp_run');
        if (!status || !root || !btn) return;
        const textEl = document.getElementById('vp_csv_text');
        const csv = textEl ? textEl.value : '';
        if (!csv.trim()) {
            status.textContent = T('panel.validation.needCsv',
                'Paste CSV data or choose a file first.');
            return;
        }
        refreshPredictionSourceLabel();
        const pred = predictedCurve();
        btn.disabled = true;
        root.style.display = 'none';
        status.textContent = T('panel.validation.comparing', 'COMPARING…');
        try {
            const body = { csv_text: csv };
            if (pred) body.predicted_curve = { time: pred.time, thrust: pred.thrust };
            // Gönderilecek GÖVDE baytı tavanla (sunucudan) denetlenir:
            // yapıştırılan metin ve tahmin eğrisi de gövdededir.
            const payload = JSON.stringify(body);
            const payloadBytes = utf8ByteLength(payload);
            const tooBig = uploadSizeError('csv', payloadBytes);
            if (tooBig) throw new Error(tooBig);
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            const tooLarge = payloadTooLargeMessage('csv', payloadBytes,
                                                    resp, data);
            if (tooLarge) throw new Error(tooLarge);
            if (!resp.ok || !data || data.status === 'error') {
                // CSV çözüldü ama karşılaştırma anlamsız (örtüşme yok vb.):
                // backend 400 gövdesinde parsed taşır — yine de çizilir.
                if (data && data.parsed) {
                    U.purgePlots(root);   // eski grafiğin resize dinleyicisi sızmasın
                    root.innerHTML = '';
                    render({ parsed: data.parsed, comparison: null,
                             _predicted: pred }, root);
                    root.style.display = 'block';
                    status.textContent = U.tf('panel.validation.comparisonError',
                        { message: data.error }, 'COMPARISON ERROR: {message}');
                    return;
                }
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            U.purgePlots(root);   // eski grafiğin resize dinleyicisi sızmasın
            root.innerHTML = '';
            data._predicted = pred;
            render(data, root);
            root.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = U.tf('common.errorPrefix', { message: err.message },
                                      'ERROR: {message}');
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Motor dosyası (.eng/.rse) içe aktarma — POST /api/import/motor-file
    // Yanıttaki comparison, CSV akışıyla AYNI metrik şemasını taşır
    // (sözleşme: hrma/importers/api.py) — mevcut render yolu yeniden
    // kullanılır. Çok motorlu .rse dosyasında seçici gösterilir; seçim
    // değişince seçili motorun eğrisi upload-csv ucuyla (aynı compare())
    // yeniden karşılaştırılır.
    // ------------------------------------------------------------------
    let motorImport = null;   // { motors: [], selected: 0, fileWarnings: [] }

    function motorBarEl() { return document.getElementById('vp_motor_bar'); }

    function renderMotorBar() {
        const bar = motorBarEl();
        if (!bar) return;
        if (!motorImport || !motorImport.motors.length) {
            bar.style.display = 'none';
            bar.innerHTML = '';
            return;
        }
        bar.style.display = 'flex';
        let html = '';
        if (motorImport.motors.length > 1) {
            const opts = motorImport.motors.map(function (m, i) {
                const name = (m.meta && m.meta.name) || ('#' + i);
                return '<option value="' + i + '"'
                    + (i === motorImport.selected ? ' selected' : '') + '>'
                    + String(name).replace(/[&<>"']/g, '') + '</option>';
            }).join('');
            html += '<label style="font-size:0.78rem;" data-i18n="panel.validation.motorSelect">'
                + T('panel.validation.motorSelect', 'Motor (file contains multiple):')
                + '</label><select id="vp_motor_select" style="max-width:240px;">'
                + opts + '</select>';
        }
        bar.innerHTML = html;
        const sel = document.getElementById('vp_motor_select');
        if (sel) {
            sel.addEventListener('change', function () {
                motorImport.selected = parseInt(sel.value, 10) || 0;
                recompareSelectedMotor();
            });
        }
    }

    function renderMotorResult(motor, comparison, pred) {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        if (!root) return;
        U.purgePlots(root);
        root.innerHTML = '';
        // Meta satırı: ad/üretici/çap/boy/kütleler + impuls sınıfı
        if (window.HRMAImportUI && window.HRMAImportUI.metaLineHtml) {
            const meta = document.createElement('div');
            meta.innerHTML = window.HRMAImportUI.metaLineHtml(motor);
            root.appendChild(meta.firstElementChild);
        }
        render({
            parsed: { time: motor.time, thrust: motor.thrust,
                      n_points: motor.time.length,
                      warnings: motor.warnings || [] },
            comparison: comparison || null,
            _predicted: pred,
        }, root);
        // Dosya düzeyi uyarılar (motor uyarılarından ayrı, görünür olmalı)
        if (motorImport && motorImport.fileWarnings.length) {
            const div = document.createElement('div');
            div.innerHTML = U.listBlock(
                T('panel.validation.motorFileWarnings', 'Motor file warnings'),
                motorImport.fileWarnings, 'warn');
            root.appendChild(div);
        }
        root.style.display = 'block';
        if (status) status.textContent = '';
    }

    async function importMotorFile(content, filename) {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        if (!window.HRMAImportUI) {
            if (status) status.textContent = T('panel.validation.importUnavailable',
                'Motor file import module is not loaded on this page.');
            return;
        }
        refreshPredictionSourceLabel();
        const pred = predictedCurve();
        if (status) status.textContent = T('panel.validation.importing',
            'IMPORTING MOTOR FILE…');
        try {
            // Değişken adı BİLEREK 'data' değil: sözleşme bekçisi
            // (tests/test_wave4a_contract.py) 'data.' erişimlerini upload-csv
            // yanıtına, 'mfres.' erişimlerini /api/import/motor-file yanıtına
            // karşı doğrular — iki uç farklı şemadadır.
            const mfres = await window.HRMAImportUI.postMotorFile(
                content, filename,
                pred ? { time: pred.time, thrust: pred.thrust } : null);
            motorImport = { motors: mfres.motors || [],
                            selected: mfres.selected_index || 0,
                            fileWarnings: mfres.warnings || [] };
            renderMotorBar();
            renderMotorResult(mfres.motor, mfres.comparison, pred);
        } catch (err) {
            // Karşılaştırma örtüşmedi ama dosya çözüldüyse eğri yine çizilir
            // (upload-csv 400 gövde deseniyle aynı sözleşme)
            if (err.partial && Array.isArray(err.partial.motors)
                && err.partial.motors.length) {
                motorImport = { motors: err.partial.motors, selected: 0,
                                fileWarnings: err.partial.warnings || [] };
                renderMotorBar();
                renderMotorResult(err.partial.motors[0], null, pred);
                if (status) {
                    status.textContent = U.tf('panel.validation.comparisonError',
                        { message: err.message }, 'COMPARISON ERROR: {message}');
                }
                return;
            }
            console.error('HRMA motor file import failed:', err);
            if (status) {
                status.textContent = U.tf('panel.validation.importFailed',
                    { message: err.message }, 'MOTOR FILE IMPORT FAILED: {message}');
            }
            if (window.HRMAImportUI.toast) {
                window.HRMAImportUI.toast(err.message, 'err');
            }
        }
    }

    // Seçili motoru yeniden karşılaştır: eğri CSV'ye çevrilip upload-csv
    // ucuna gönderilir — CSV akışıyla birebir aynı compare() metrikleri
    async function recompareSelectedMotor() {
        if (!motorImport || !motorImport.motors.length) return;
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const motor = motorImport.motors[motorImport.selected]
            || motorImport.motors[0];
        refreshPredictionSourceLabel();
        const pred = predictedCurve();
        if (status) status.textContent = T('panel.validation.comparing', 'COMPARING…');
        // V3 KK 2. tur (UPL devri): seçili motorun eğrisi de aynı upload-csv
        // gövdesiyle gider; runValidation ile AYNI ortak denetimden geçer
        // (import_ui.js uploadSizeError / payloadTooLargeMessage). ÖLÇÜLDÜ
        // (dal tabanı 1b4bbff7): ön denetim yoktu ve sunucudan 413 düz metin
        // gelince ekranda HİÇBİR ileti çıkmıyordu (data null → koşul düşüyor).
        // Tavanı aşan gövde gönderilmez; seçilen motorun eğrisi
        // karşılaştırmasız çizilir ve ileti durum satırına yazılır.
        function sizeErrorOut(message) {
            renderMotorResult(motor, null, pred);
            if (status) {
                status.textContent = U.tf('common.errorPrefix',
                    { message: message }, 'ERROR: {message}');
            }
        }
        try {
            const body = {
                csv_text: window.HRMAImportUI.csvFromCurve(motor.time, motor.thrust),
            };
            if (pred) body.predicted_curve = { time: pred.time, thrust: pred.thrust };
            const payload = JSON.stringify(body);
            const payloadBytes = utf8ByteLength(payload);
            const tooBig = uploadSizeError('csv', payloadBytes);
            if (tooBig) {
                sizeErrorOut(tooBig);
                return;
            }
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            const tooLarge = payloadTooLargeMessage('csv', payloadBytes,
                                                    resp, data);
            if (tooLarge) {
                sizeErrorOut(tooLarge);
                return;
            }
            if (!resp.ok || !data || data.status === 'error') {
                renderMotorResult(motor, null, pred);
                if (status && data && data.error) {
                    status.textContent = U.tf('panel.validation.comparisonError',
                        { message: data.error }, 'COMPARISON ERROR: {message}');
                } else if (status) {
                    // Gövdesiz/çözülemeyen hata yanıtı: ham gövde basılmaz,
                    // yalnız HTTP durum kodu (runValidation ile aynı biçim).
                    status.textContent = U.tf('common.errorPrefix',
                        { message: 'HTTP ' + resp.status }, 'ERROR: {message}');
                }
                return;
            }
            renderMotorResult(motor, data.comparison, pred);
        } catch (err) {
            console.error('HRMA motor recompare failed:', err);
            if (status) {
                status.textContent = U.tf('common.errorPrefix',
                    { message: err.message }, 'ERROR: {message}');
            }
        }
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function drawCurves(parsed, pred, comparison, root) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(T('panel.validation.chartTitle',
            'Thrust Curve — Your Test Data vs HRMA Prediction'));
        const plot = document.createElement('div');
        wrap.appendChild(plot);
        root.appendChild(wrap);
        if (typeof Plotly === 'undefined') {
            plot.textContent = T('common.plotlyMissing', 'Plotly is not loaded — chart skipped.');
            return;
        }
        const traces = [{
            x: parsed.time, y: parsed.thrust, mode: 'lines',
            name: T('panel.validation.sUser', 'Your test data [N]'), line: { width: 2 },
        }];
        if (pred) {
            // ÖH D27 / P11B4-23 — LEJANT EĞRİNİN NE OLDUĞUNU SÖYLER.
            // ÖLÇÜLDÜ (a3/once.json): geçici rejim yokken panel iki noktalı
            // DİKDÖRTGEN tasarım noktasını 'HRMA prediction [N]' adıyla
            // çiziyordu; `pred.source` yalnız formun yanındaki alanda
            // duruyor, grafiğe ve sonuç bloğuna HİÇ ulaşmıyordu. Kullanıcı
            // gerçek atış verisini bir dikdörtgene karşı 'kötü uyum'
            // damgalı görüyor, kıyas eğrisinin ne olduğunu okuyamıyordu.
            traces.push({
                x: pred.time, y: pred.thrust, mode: 'lines',
                name: U.tf('panel.validation.sPredictedSrc',
                           { source: pred.source || '' },
                           'HRMA prediction [N] — {source}'),
                line: { width: 2, dash: 'dash' },
            });
        }
        const shapes = [];
        if (comparison && comparison.overlap) {
            shapes.push({
                type: 'rect', xref: 'x', yref: 'paper',
                x0: comparison.overlap.t_start, x1: comparison.overlap.t_end,
                y0: 0, y1: 1, fillcolor: 'rgba(0,229,255,0.05)',
                line: { width: 0 },
            });
        }
        Plotly.newPlot(plot, traces, {
            xaxis: { title: T('common.axis.timeS', 'Time (s)') },
            yaxis: { title: T('common.axis.thrustN', 'Thrust (N)') },
            shapes: shapes,
            margin: { t: 24, r: 16 },
            height: 340,
        }, { responsive: true, displaylogo: false });
    }

    /* ÖH D27 / P11B4-24 — EŞİK TABLOSU ARTIK PANELE GÖMÜLÜ DEĞİL.
       ÖLÇÜLDÜ (a3/once.json): `diffKind` 5/10/20 bandını KENDİ içinde
       tutuyordu; uç aynı sayıları (GRADE_THRESHOLDS_PCT) yayımlamıyordu —
       uçtaki eşik değişse rozetin hükmü ile kartların rengi sessizce
       ayrışırdı. Band artık `comparison.grade_thresholds_pct` ile gelir.
       İKİNCİ ÖLÇÜM: panel bandı ucun SKORLAMADIĞI üç metriğe de
       uyguluyordu (tepe itki, ortalama itki, yanma süresi); ucun puanı
       yalnız max(|impuls farkı|, NRMSE). Skora girmeyen kart artık
       renklendirilmez — rengin arkasında bir hüküm yoksa renk atılmaz.
       Uç bandı göndermezse hiçbir kart renklendirilmez (fail-closed:
       panel band UYDURMAZ). */
    function metricCards(metrics, bands, scored) {
        function diffKind(pct, metrik) {
            if (!bands || !Number.isFinite(pct)) return 'dim';
            if (Array.isArray(scored) && scored.indexOf(metrik) < 0) return 'dim';
            const a = Math.abs(pct);
            if (a <= bands.excellent) return 'ok';
            if (a <= bands.good) return 'info';
            if (a <= bands.fair) return 'warn';
            return 'err';
        }
        const unscoredTip = T('panel.validation.unscoredTip',
            'Not part of the agreement score (the score is '
            + 'max(|impulse difference|, NRMSE)) — shown uncoloured.');
        return '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard(T('panel.validation.cardTotalImpulse', 'TOTAL IMPULSE'),
                U.fmt(metrics.total_impulse_user_ns, 1) + ' / '
                + U.fmt(metrics.total_impulse_predicted_ns, 1), 'N·s',
                diffKind(metrics.total_impulse_diff_pct, 'total_impulse_diff_pct'),
                T('panel.validation.cardTotalImpulseTip',
                  'Measured / predicted — Sutton Eq. 2-1 (trapezoidal)'))
            + U.statCard(T('panel.validation.cardImpulseDiff', 'IMPULSE DIFF'),
                (metrics.total_impulse_diff_pct >= 0 ? '+' : '')
                + U.fmt(metrics.total_impulse_diff_pct, 1), '%',
                diffKind(metrics.total_impulse_diff_pct, 'total_impulse_diff_pct'), '')
            + U.statCard(T('panel.validation.cardPeakThrust', 'PEAK THRUST'),
                U.fmt(metrics.peak_thrust_user_n, 0) + ' / '
                + U.fmt(metrics.peak_thrust_predicted_n, 0), 'N',
                diffKind(metrics.peak_thrust_diff_pct, 'peak_thrust_diff_pct'),
                T('panel.validation.measuredPredicted', 'Measured / predicted')
                    + ' — ' + unscoredTip)
            + U.statCard(T('panel.validation.cardMeanThrust', 'MEAN THRUST'),
                U.fmt(metrics.mean_thrust_user_n, 0) + ' / '
                + U.fmt(metrics.mean_thrust_predicted_n, 0), 'N',
                diffKind(metrics.mean_thrust_diff_pct, 'mean_thrust_diff_pct'),
                T('panel.validation.cardMeanThrustTip', 'F_avg = I_t / t_burn (NFPA 1125 convention)')
                    + ' — ' + unscoredTip)
            + U.statCard(T('panel.validation.cardBurnTime', 'BURN TIME'),
                U.fmt(metrics.burn_time_user_s, 2) + ' / '
                + U.fmt(metrics.burn_time_predicted_s, 2), 's',
                diffKind(metrics.burn_time_diff_pct, 'burn_time_diff_pct'),
                T('panel.validation.cardBurnTimeTip', '5% of peak-thrust threshold (NFPA 1125)')
                    + ' — ' + unscoredTip)
            + U.statCard('RMSE', U.fmt(metrics.rmse_n, 1), 'N', 'dim',
                T('panel.validation.rmseTip', 'Root-mean-square error over the common time window'))
            + U.statCard('NRMSE', U.fmt(metrics.nrmse_pct, 1), '%',
                diffKind(metrics.nrmse_pct, 'nrmse_pct'),
                T('panel.validation.nrmseTip', 'RMSE normalized by the predicted peak thrust'))
            + '</div>';
    }

    function render(data, root) {
        const parsed = (data && data.parsed) || { time: [], thrust: [], warnings: [] };
        const comparison = data && data.comparison;
        const pred = data && data._predicted;

        const head = document.createElement('div');
        let html = U.sectionTitle(T('panel.validation.secParsed', 'Parsed Test Data'))
            + `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:4px 0;">${
                U.tf('panel.validation.pointsParsed',
                     { n: parsed.n_points || (parsed.time ? parsed.time.length : 0) },
                     '{n} data points parsed.')}</p>`;
        if (comparison) {
            const kind = GRADE_KINDS[comparison.grade] || 'dim';
            // ÖH D27 / P11B4-24 — rozet ipucu da eşiği UÇTAN okur; band
            // gelmezse sayı UYDURULMAZ, ipucu bandı hiç anmaz.
            const bands = comparison.grade_thresholds_pct;
            const gradeTip = bands
                ? U.tf('panel.validation.gradeTipBands',
                       { a: bands.excellent, b: bands.good, c: bands.fair },
                       'Score buckets published by the endpoint: '
                       + '{a}% / {b}% / {c}% (engineering judgment)')
                : T('panel.validation.gradeTipNoBands',
                    'The endpoint published no score buckets with this '
                    + 'response; the cards are left uncoloured.');
            html += U.sectionTitle(T('panel.validation.secAgreement', 'Agreement With HRMA Prediction'))
                + `<div style="margin:4px 0 8px;">${U.badge(
                    String(comparison.grade || '?').toUpperCase() + ' '
                        + T('panel.validation.agreementWord', 'AGREEMENT'),
                    kind, gradeTip)}</div>`
                // ÖH D27 / P11B4-23 — KIYAS EĞRİSİNİN NE OLDUĞU SONUÇ
                // BLOĞUNDA YAZAR. Ölçüldü: koşturulmuş sonuç bloğunda
                // 'design point' dizesi 0 kez geçiyordu; `render` pred'i
                // yalnız çizime veriyor, `pred.source`'u hiç okumuyordu.
                // Geçici rejim yokken kıyas iki noktalı bir DİKDÖRTGENDİR
                // ve 'POOR AGREEMENT' rozeti bu dikdörtgene karşıdır —
                // kullanıcının ölçüm verisi ya da yük hücresi hakkında bir
                // hüküm DEĞİLDİR. Uç böyle bir künye üretmiyorsa satır
                // hiç çıkmaz (fail-closed).
                + (pred && pred.source
                    ? `<p style="font-family:var(--hd-mono); font-size:0.75rem;
                        color:var(--hd-ink-dim, #7d97a5); margin:4px 0;">${
                        U.esc(U.tf('panel.validation.predSource',
                                   { source: pred.source },
                                   'Prediction source: {source}'))}</p>` : '')
                + (pred && pred.kind === 'design_point'
                    ? U.listBlock(T('panel.validation.designPointHead',
                        'The reference curve is a design point, not a computed transient'),
                        [T('panel.validation.designPointNote',
                           'No transient F(t) was available, so the comparison '
                           + 'runs against a two-point rectangle built from the '
                           + 'design thrust and burn time. A low grade here can '
                           + 'mean the motor simply does not burn at constant '
                           + 'thrust — run the transient analysis before reading '
                           + 'it as a test-data or model problem.')], 'warn')
                    : '')
                + metricCards(comparison.metrics || {}, bands,
                              comparison.scored_metrics)
                + `<p style="font-size:0.82rem; color:var(--hd-ink, #cfe8f2);
                    margin:10px 0;">${comparison.assessment || ''}</p>`;
        } else {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim, #7d97a5);
                margin:8px 0;">${T('panel.validation.parseOnly',
                'Parse-only mode: run a motor calculation (or the transient analysis) '
                + 'first, then compare again to get the quantitative agreement metrics.')}</p>`;
        }
        head.innerHTML = html;
        root.appendChild(head);

        drawCurves(parsed, pred, comparison, root);

        if (Array.isArray(parsed.warnings) && parsed.warnings.length) {
            const div = document.createElement('div');
            div.innerHTML = U.listBlock(T('panel.validation.parserNotes', 'CSV parser notes'),
                                        parsed.warnings, 'warn');
            root.appendChild(div);
        }
    }

    // ------------------------------------------------------------------
    // Kayıt — VALIDATION sekmesi; alan listesi boş (özel blok enjekte edilir)
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'User Data Validation — Static-Fire CSV vs HRMA Prediction',
        titleKey: 'panel.validation.title',
        category: 'VALIDATION',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [],
        fromResults: function () {
            // Sonuç değişince tahmin kaynağı etiketi tazelenir
            refreshPredictionSourceLabel();
            return null;
        },
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (performance_panel deseni)
    window.ValidationPanel = {
        _render: render,
        _predictedCurve: predictedCurve,
        _metricCards: metricCards,
        _augmentSection: augmentSection,
        _importMotorFile: importMotorFile,
        _recompareSelectedMotor: recompareSelectedMotor,
        run: runValidation,
    };
})();
