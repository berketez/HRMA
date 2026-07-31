/* ====================================================================
   HRMA Analiz Güvertesi — Karşılaştırmalı Analiz Paneli (COMPARE)
   --------------------------------------------------------------------
   POST /api/comparative-analysis'i UI'a bağlar: kullanıcı her hesap
   sonrasında "Snapshot current result" ile mevcut sonucun metriklerini
   ({thrust, isp, total_impulse, total_mass(varsa)}) verdiği adla
   hafızaya alır (JS dizisi — sayfa ömrü, kalıcı depolama yok);
   2+ snapshot birikince "Compare" aktifleşir ve konfigürasyonlar
   backend'de karşılaştırılır.

   Yanıt şeması (app.py comparative_analysis, 2026-07-16):
     { status:'success', plot:'<JSON string {data,layout}>',
       analysis:{ best_thrust, best_isp, best_efficiency, total_configs } }
   400 → { status:'error', error:'...' } (panelde okunur gösterilir).

   Güverte formu sayısal alan üretir; snapshot listesi + adlandırma için
   özel blok panel montajından sonra bölüme enjekte edilir, güvertenin
   otomatik "Run Analysis" butonu gizlenir (POST'u bu panel kendi
   butonuyla yapar — buildPayload snapshot sözlüğünü taşıyamaz).
   Desen: validation_panel.js (özel blok + kendi POST'u).
   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    const ENDPOINT = '/api/comparative-analysis';
    const PANEL_ID = 'comparative';

    // Snapshot deposu — sayfa ömrü boyunca yaşar (kalıcı depolama yok)
    const snapshots = [];

    // ------------------------------------------------------------------
    // Metrik çıkarımı — sayfa tipine dayanıklı (hybrid: results.motor,
    // solid/liquid: düz results). Yalnız gerçekten mevcut ve sonlu
    // değerler alınır; total_mass yoksa alan hiç gönderilmez (backend
    // eksik anahtarı tolere eder, ilgili panel boş kalır).
    // ------------------------------------------------------------------
    function num(v) {
        return (typeof v === 'number' && isFinite(v)) ? v : null;
    }

    function currentMetrics() {
        const r = window.currentResults;
        if (!r) return null;
        const m = U.motorDict(r);
        const out = {};
        // Katı motor düz sözlükte 'thrust' ÜRETMİYOR (ortalama ve tepe itki
        // ayrı anahtarlarda); eskiden karşılaştırmaya itki ve toplam impuls
        // hiç girmiyordu. Merkezi okuyucu motor tipine göre çözer.
        const thrust = num(U.readThrust(r));
        const isp = num(m.isp);
        let totalImpulse = num(m.total_impulse);
        if (totalImpulse == null && thrust != null) {
            const burnTime = num(U.readBurnTime(r));
            if (burnTime != null) totalImpulse = thrust * burnTime;
        }
        const totalMass = (num(m.total_mass) != null)
            ? num(m.total_mass) : num(m.total_motor_mass);
        if (thrust != null) out.thrust = thrust;
        if (isp != null) out.isp = isp;
        if (totalImpulse != null) out.total_impulse = totalImpulse;
        if (totalMass != null) out.total_mass = totalMass;
        return Object.keys(out).length ? out : null;
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ------------------------------------------------------------------
    // Özel blok (ad girişi + snapshot listesi + Compare butonu)
    // ------------------------------------------------------------------
    function customFormHtml() {
        return `<div id="cmp_custom" style="margin:10px 0;">
            <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                <div class="form-group" style="flex:1; min-width:180px;">
                    <label data-i18n="panel.comparative.fName">${
                        T('panel.comparative.fName', 'Configuration name')}</label>
                    <input type="text" id="cmp_name" maxlength="40"
                        data-i18n-placeholder="panel.comparative.namePlaceholder"
                        placeholder="${T('panel.comparative.namePlaceholder',
                            'e.g. baseline, high-Pc, long-burn')}"
                        style="width:100%;">
                </div>
                <div class="form-group">
                    <button class="btn" type="button" id="cmp_snapshot"
                        data-i18n="panel.comparative.btnSnapshot">${
                        T('panel.comparative.btnSnapshot', 'Snapshot current result')}</button>
                </div>
                <div class="form-group">
                    <button class="btn" type="button" id="cmp_run" disabled
                        data-i18n="panel.comparative.btnCompare">${
                        T('panel.comparative.btnCompare', 'Compare')}</button>
                </div>
            </div>
            <div id="cmp_list" style="margin-top:8px;"></div>
            <p style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;"
                data-i18n="panel.comparative.intro">${T('panel.comparative.intro',
                'Snapshots live for this page session only. At least 2 are '
                + 'required for a comparison.')}</p>
        </div>`;
    }

    function snapshotRow(snap, idx) {
        const parts = [];
        if (snap.metrics.thrust != null)
            parts.push('F=' + U.fmt(snap.metrics.thrust, 0) + ' N');
        if (snap.metrics.isp != null)
            parts.push('Isp=' + U.fmt(snap.metrics.isp, 1) + ' s');
        if (snap.metrics.total_impulse != null)
            parts.push('It=' + U.fmt(snap.metrics.total_impulse, 0) + ' N·s');
        if (snap.metrics.total_mass != null)
            parts.push('m=' + U.fmt(snap.metrics.total_mass, 2) + ' kg');
        return `<div style="display:flex; gap:10px; align-items:baseline;
                padding:6px 10px; margin:4px 0; flex-wrap:wrap;
                border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px);
                background:var(--hd-inset, rgba(6,14,26,0.85));">
            <strong style="color:var(--hd-ink-strong, #eaf7fb);">
                ${escapeHtml(snap.name)}</strong>
            <span style="font-family:var(--hd-mono, monospace); font-size:0.72rem;
                color:var(--hd-ink-dim, #7d97a5);">${parts.join(' · ')}</span>
            <button type="button" data-cmp-remove="${idx}"
                style="margin-left:auto; background:transparent; cursor:pointer;
                border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                border-radius:4px; color:var(--hd-ink-dim, #7d97a5);
                font-family:var(--hd-mono, monospace); font-size:0.68rem;
                padding:2px 8px;">${T('common.removeUpper', 'REMOVE')}</button>
        </div>`;
    }

    function refreshList() {
        const list = document.getElementById('cmp_list');
        const runBtn = document.getElementById('cmp_run');
        if (!list || !runBtn) return;
        list.innerHTML = snapshots.map(snapshotRow).join('');
        runBtn.disabled = snapshots.length < 2;
        list.querySelectorAll('[data-cmp-remove]').forEach(function (b) {
            b.addEventListener('click', function () {
                const i = parseInt(b.getAttribute('data-cmp-remove'), 10);
                if (Number.isInteger(i)) snapshots.splice(i, 1);
                refreshList();
            });
        });
    }

    function takeSnapshot() {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const nameEl = document.getElementById('cmp_name');
        const metrics = currentMetrics();
        if (!metrics) {
            if (status) status.textContent = T('panel.comparative.noResult',
                'No calculation result yet — run a motor calculation first.');
            return;
        }
        let name = (nameEl && nameEl.value.trim())
            || ('config-' + (snapshots.length + 1));
        // Aynı ad ikinci kez gelirse üzerine yazılır (backend sözlüğü
        // isim-anahtarlı — sessiz kayıp yerine bilinçli güncelleme)
        const existing = snapshots.findIndex(function (s) { return s.name === name; });
        if (existing !== -1) {
            snapshots[existing] = { name: name, metrics: metrics };
            if (status) status.textContent = U.tf('panel.comparative.snapUpdated',
                { name: name, count: snapshots.length },
                'Snapshot "{name}" updated ({count} stored).');
        } else {
            snapshots.push({ name: name, metrics: metrics });
            if (status) status.textContent = U.tf('panel.comparative.snapStored',
                { name: name, count: snapshots.length },
                'Snapshot "{name}" stored ({count} total).');
        }
        if (nameEl) nameEl.value = '';
        refreshList();
    }

    function augmentSection() {
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        if (!sec) return false;
        if (document.getElementById('cmp_custom')) return true;  // idempotent
        // Güvertenin otomatik butonu gizlenir: buildPayload yalnız sayısal
        // alan okur, snapshot sözlüğünü taşıyamaz — POST'u bu panel yapar.
        const dockBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (dockBtn && dockBtn.parentElement) {
            dockBtn.parentElement.style.display = 'none';
        }
        const holder = document.createElement('div');
        holder.innerHTML = customFormHtml();
        const status = document.getElementById('ad_status_' + PANEL_ID);
        sec.insertBefore(holder.firstElementChild, status);

        document.getElementById('cmp_snapshot')
            .addEventListener('click', takeSnapshot);
        document.getElementById('cmp_run')
            .addEventListener('click', runComparison);
        refreshList();
        return true;
    }

    // Güverte DOMContentLoaded'ta kurulur; bölüm görünene dek kısa
    // aralıklarla dene (montaj yarışına dayanıklılık — validation deseni).
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
    // Çalıştırma — POST { motor_configs: {ad: {metrikler}} }
    // ------------------------------------------------------------------
    async function runComparison() {
        const status = document.getElementById('ad_status_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        const btn = document.getElementById('cmp_run');
        if (!status || !root || !btn) return;
        if (snapshots.length < 2) {
            status.textContent = T('panel.comparative.needTwo',
                'At least 2 snapshots are required for comparison.');
            return;
        }
        const motorConfigs = {};
        snapshots.forEach(function (s) { motorConfigs[s.name] = s.metrics; });

        btn.disabled = true;
        root.style.display = 'none';
        status.textContent = T('panel.validation.comparing', 'COMPARING…');
        try {
            const resp = await fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motor_configs: motorConfigs }),
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                // 400 gövdesi net mesaj taşır — panelde okunur gösterilir
                throw new Error((data && data.error) || ('HTTP ' + resp.status));
            }
            U.purgePlots(root);   // eski grafiğin resize dinleyicisi sızmasın
            root.innerHTML = '';
            render(data, root);
            root.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = U.tf('common.errorPrefix', { message: err.message },
                                      'ERROR: {message}');
        } finally {
            btn.disabled = snapshots.length < 2;
        }
    }

    // ------------------------------------------------------------------
    // Çizim — plot JSON string {data,layout} + best_* özet satırları
    // ------------------------------------------------------------------
    function parseFigure(pd) {
        try {
            const fig = (typeof pd === 'string') ? JSON.parse(pd) : pd;
            if (fig && Array.isArray(fig.data)) return fig;
        } catch (e) { /* aşağıda null */ }
        return null;
    }

    function summaryCards(analysis) {
        if (!analysis) return '';
        return '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard(T('panel.comparative.bestThrust', 'BEST THRUST'),
                escapeHtml(analysis.best_thrust || '—'), '',
                analysis.best_thrust ? 'ok' : 'dim',
                T('panel.comparative.bestThrustTip',
                  'Highest thrust among configurations that report it'))
            + U.statCard(T('panel.comparative.bestIsp', 'BEST ISP'),
                escapeHtml(analysis.best_isp || '—'), '',
                analysis.best_isp ? 'ok' : 'dim',
                T('panel.comparative.bestIspTip',
                  'Highest specific impulse among configurations that report it'))
            + U.statCard(T('panel.comparative.bestEfficiency', 'BEST EFFICIENCY'),
                escapeHtml(analysis.best_efficiency || '—'), '',
                analysis.best_efficiency ? 'ok' : 'dim',
                T('panel.comparative.bestEfficiencyTip',
                  'Highest Isp / total mass ratio (needs both metrics)'))
            + U.statCard(T('panel.comparative.configs', 'CONFIGS'),
                String(analysis.total_configs || 0), '', 'info',
                T('panel.comparative.configsTip', 'Number of configurations compared'))
            + '</div>';
    }

    function render(data, root) {
        const head = document.createElement('div');
        head.innerHTML = U.sectionTitle(T('panel.comparative.secSummary', 'Comparison Summary'))
            + summaryCards(data && data.analysis);
        root.appendChild(head);

        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(T('panel.comparative.secChart',
            'Motor Configuration Comparison'));
        const plot = document.createElement('div');
        wrap.appendChild(plot);
        root.appendChild(wrap);

        const fig = parseFigure(data && data.plot);
        if (!fig) {
            plot.textContent = T('common.badPayload', 'Unexpected plot payload from backend.');
            return;
        }
        if (typeof Plotly === 'undefined') {
            plot.textContent = T('common.plotlyMissing', 'Plotly is not loaded — chart skipped.');
            return;
        }
        Plotly.newPlot(plot, fig.data, fig.layout || {},
            { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Kayıt — COMPARE sekmesi; alan listesi boş (özel blok enjekte edilir)
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Comparative Analysis — Snapshot & Compare Configurations',
        titleKey: 'panel.comparative.title',
        category: 'COMPARE',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [],
        render: render,
    });

    // Test / hata ayıklama: saf yardımcılar (validation_panel deseni)
    window.ComparativePanel = {
        _render: render,
        _currentMetrics: currentMetrics,
        _parseFigure: parseFigure,
        _snapshots: snapshots,
        _augmentSection: augmentSection,
        snapshot: takeSnapshot,
        run: runComparison,
    };
})();
