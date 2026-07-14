/* ====================================================================
   HRMA Analysis Dock — analiz güvertesi çekirdeği
   --------------------------------------------------------------------
   Kategori sekmeli (THERMAL / STRUCTURAL / SAFETY, ileride genişler)
   analiz paneli konteyneri. Paneller kendilerini AnalysisDock.register
   ile kaydeder; script yüklenme sırası: önce bu dosya, sonra paneller.
   Desen: injector_panel.js (IIFE + init({anchorId, resultsProvider})).

   Kullanım (entegrasyon sözleşmesi — DEĞİŞTİRME):
     <script src="/static/js/analysis_dock.js"></script>
     <script src="/static/js/panels/structural_panel.js"></script>
     ...
     AnalysisDock.init({
         anchorId: 'trajectoryPanel',      // güverte bu elemanın ÖNÜNE kurulur
         motorType: 'hybrid'|'liquid'|'solid',
         resultsProvider: function () { return window.currentResults; }
     });

   Panel kaydı:
     AnalysisDock.register({
         id, title, category, endpoint, motorTypes,
         fields: [[inputId, label, defaultValue, step], ...],
             // step bir dizi ise ([[value, label], ...]) alan <select> olur
         fromResults: function (currentResults) { return {inputId: değer}; },
             // Alan ÖNERİLERİ — kullanıcı üzerine yazabilir; POST gövdesi
             // HER ZAMAN formdan okunur (kullanıcının elle değiştirdiği
             // alanlar bir daha ezilmez: data-dirty koruması).
         render: function (data, rootEl) { ... },  // ham JSON yanıtı çizer
         long: true|false                          // uzun süren analiz uyarısı
     });
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // Başlangıç kategori seti — register bilinmeyen kategoriyle gelirse
    // sekme dinamik eklenir (ileride genişleme sözleşmesi).
    const BASE_CATEGORIES = ['THERMAL', 'STRUCTURAL', 'SAFETY'];

    let cfg = {};
    let inited = false;
    let activeCategory = null;
    const registry = [];          // kayıt sırası korunur
    const registeredIds = {};

    // ------------------------------------------------------------------
    // Ortak UI yardımcıları (paneller AnalysisDock.ui üzerinden kullanır)
    // ------------------------------------------------------------------
    const TBL = 'width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;';
    const TD = 'padding:6px 8px; border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));';

    const KIND_COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };

    function kindColor(kind) {
        return KIND_COLORS[kind] || KIND_COLORS.info;
    }

    function fmt(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—' : x.toFixed(d == null ? 2 : d);
    }

    // İlk anlamlı (sonlu sayı veya boş olmayan string) değeri döndürür.
    // Backend alan adı varyasyonlarına (SF_pressure / sf_pressure vb.)
    // dayanıklı okuma için.
    function pick(obj, keys) {
        if (!obj) return null;
        for (let i = 0; i < keys.length; i++) {
            const v = obj[keys[i]];
            if (typeof v === 'number' && Number.isFinite(v)) return v;
            if (typeof v === 'string' && v !== '') return v;
        }
        return null;
    }

    function badge(text, kind, title) {
        const c = kindColor(kind);
        return `<span title="${title || ''}" style="border:1px solid ${c}; color:${c};
                 border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
                 font-size:0.75rem; display:inline-block;">${text}</span>`;
    }

    // Sayısal kart (thermal panel "numeric cards" vb.)
    function statCard(label, value, unit, kind, title) {
        const c = kind ? kindColor(kind) : 'var(--hd-ink-strong, #eaf7fb)';
        return `<div title="${title || ''}" style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:10px 14px; min-width:150px; flex:1;
                background:var(--hd-inset, rgba(6,14,26,0.85));">
            <div style="font-size:0.68rem; color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); text-transform:uppercase;
                 letter-spacing:0.08em;">${label}</div>
            <div style="font-size:1.25rem; font-family:var(--hd-mono); color:${c}; margin-top:2px;">
                ${value}<span style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);"> ${unit || ''}</span>
            </div>
        </div>`;
    }

    // İki sütunlu anahtar/değer tablosu: rows = [[label, value, tooltip?], ...]
    function kvTable(rows) {
        return `<table style="${TBL}">` + rows.map(r =>
            `<tr><td style="${TD}" ${r[2] ? `title="${r[2]}"` : ''}><strong>${r[0]}</strong></td>
             <td style="${TD}">${r[1]}</td></tr>`).join('') + '</table>';
    }

    function sectionTitle(text) {
        return `<h4 style="margin:14px 0 4px; color:var(--hd-ink-strong, #eaf7fb);">${text}</h4>`;
    }

    // Uyarı / öneri kutusu (injector_panel uyarı bloğu deseni)
    function listBlock(title, items, kind) {
        if (!items || !items.length) return '';
        const c = kindColor(kind || 'warn');
        return `<div style="border:1px solid ${c}; border-radius:8px;
            padding:10px 14px; margin:10px 0; color:${c};">
            <strong>${title}</strong><ul style="margin:6px 0 0 18px;">` +
            items.map(w => `<li>${w}</li>`).join('') + '</ul></div>';
    }

    // ------------------------------------------------------------------
    // DOM yardımcıları
    // ------------------------------------------------------------------
    function fieldDomId(panelId, fieldId) {
        return 'ad_f_' + panelId + '_' + fieldId;
    }

    function fieldHtml(panelId, f) {
        const fid = f[0], label = f[1], defVal = f[2], step = f[3];
        const domId = fieldDomId(panelId, fid);
        if (Array.isArray(step)) {
            // step bir seçenek listesi: [[value, label], ...] → <select>
            const opts = step.map(o =>
                `<option value="${o[0]}"${o[0] === defVal ? ' selected' : ''}>${o[1]}</option>`).join('');
            return `<div class="form-group"><label>${label}</label>
                <select id="${domId}" data-field="${fid}">${opts}</select></div>`;
        }
        return `<div class="form-group"><label>${label}</label>
            <input type="number" id="${domId}" data-field="${fid}" value="${defVal}" step="${step}"></div>`;
    }

    function panelSectionHtml(spec) {
        const fieldsHtml = (spec.fields || []).map(f => fieldHtml(spec.id, f)).join('');
        return `
        <div id="ad_sec_${spec.id}" style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
             border-radius:var(--hd-radius-sm, 8px); padding:12px 16px; margin:12px 0;">
            <h3 style="margin:0 0 8px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;">
                ${spec.title}
                <span style="font-family:var(--hd-mono); font-size:0.68rem;
                      color:var(--hd-ink-faint, #46606d);">${spec.endpoint || ''}</span>
            </h3>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
                 gap:10px; margin:10px 0;">
                ${fieldsHtml}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="ad_run_${spec.id}">Run Analysis</button>
                </div>
            </div>
            <div id="ad_status_${spec.id}" style="font-family:var(--hd-mono);
                 color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <div id="ad_root_${spec.id}" style="display:none;"></div>
        </div>`;
    }

    function tabButtonHtml(cat) {
        return `<button type="button" class="ad-tab" data-category="${cat}"
            style="font-family:var(--hd-mono); font-size:0.78rem; letter-spacing:0.08em;
            padding:7px 16px; cursor:pointer; border-radius:6px 6px 0 0;
            border:1px solid var(--hd-line, rgba(0,229,255,0.14)); border-bottom:none;
            background:transparent; color:var(--hd-ink-dim, #7d97a5);">${cat}</button>`;
    }

    function dockHtml() {
        return `
        <div class="panel" id="analysisDock" style="width:100%; grid-column: 1 / -1;">
            <h2>&#9654; Analysis Dock</h2>
            <div class="chart-explanation">
                <strong>What it does:</strong> Runs detailed engineering analyses
                (thermal, structural, safety) on the current motor design.
                Inputs are pre-filled from the latest calculation results —
                you can override any value before running. The request is
                always built from the form fields shown.
            </div>
            <div id="ad_tabs" style="display:flex; gap:6px; margin:14px 0 0; flex-wrap:wrap;"></div>
            <div id="ad_panes" style="border-top:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));"></div>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Kategori sekmeleri
    // ------------------------------------------------------------------
    function ensureCategory(cat) {
        const tabs = document.getElementById('ad_tabs');
        const panes = document.getElementById('ad_panes');
        if (!tabs || !panes) return null;
        let pane = document.getElementById('ad_pane_' + cat);
        if (pane) return pane;

        const holder = document.createElement('div');
        holder.innerHTML = tabButtonHtml(cat);
        const btn = holder.firstElementChild;
        btn.addEventListener('click', function () { selectCategory(cat); });
        tabs.appendChild(btn);

        pane = document.createElement('div');
        pane.id = 'ad_pane_' + cat;
        pane.style.display = 'none';
        pane.innerHTML = `<p class="ad-empty" style="color:var(--hd-ink-dim, #7d97a5);
            font-family:var(--hd-mono); font-size:0.8rem; margin:12px 0;">
            No analyses registered in this category yet.</p>`;
        panes.appendChild(pane);
        return pane;
    }

    function selectCategory(cat) {
        activeCategory = cat;
        const tabs = document.querySelectorAll('#ad_tabs .ad-tab');
        tabs.forEach(function (b) {
            const on = b.getAttribute('data-category') === cat;
            b.style.background = on ? 'rgba(0, 229, 255, 0.10)' : 'transparent';
            b.style.color = on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)';
            b.style.borderColor = on ? 'var(--hd-line-strong, rgba(0,229,255,0.42))'
                                     : 'var(--hd-line, rgba(0,229,255,0.14))';
        });
        const panes = document.getElementById('ad_panes');
        if (!panes) return;
        Array.prototype.forEach.call(panes.children, function (p) {
            p.style.display = (p.id === 'ad_pane_' + cat) ? 'block' : 'none';
        });
    }

    // ------------------------------------------------------------------
    // Öneri (fromResults) uygulama — kullanıcının elle değiştirdiği
    // alanlar (data-dirty) EZİLMEZ; POST her zaman formdan okunur.
    // ------------------------------------------------------------------
    function applySuggestions(spec) {
        if (!cfg.resultsProvider || !spec.fromResults) return;
        let r = null;
        try { r = cfg.resultsProvider(); } catch (e) { r = null; }
        if (!r) return;
        let sug = null;
        try { sug = spec.fromResults(r); } catch (e) { sug = null; }
        if (!sug) return;
        Object.keys(sug).forEach(function (k) {
            const el = document.getElementById(fieldDomId(spec.id, k));
            if (!el || el.dataset.dirty === '1') return;
            const v = sug[k];
            if (el.tagName === 'SELECT') {
                if (v != null) el.value = String(v);
                return;
            }
            if (typeof v === 'number' && Number.isFinite(v)) el.value = v;
        });
    }

    function buildPayload(spec) {
        applySuggestions(spec);
        const payload = {};
        const sec = document.getElementById('ad_sec_' + spec.id);
        if (!sec) return payload;
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') {
                payload[key] = el.value;
                return;
            }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) payload[key] = v;
            // NaN → alan gönderilmez, backend kendi varsayılanını kullanır
        });
        return payload;
    }

    // ------------------------------------------------------------------
    // Çalıştırma
    // ------------------------------------------------------------------
    async function runPanel(spec) {
        const status = document.getElementById('ad_status_' + spec.id);
        const root = document.getElementById('ad_root_' + spec.id);
        const btn = document.getElementById('ad_run_' + spec.id);
        if (!status || !root || !btn) return;
        btn.disabled = true;
        root.style.display = 'none';
        status.textContent = spec.long
            ? 'RUNNING — this analysis may take a while…' : 'RUNNING…';
        try {
            const resp = await fetch(spec.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildPayload(spec)),
            });
            const data = await resp.json();
            if (!resp.ok || data.status === 'error') {
                throw new Error(data.error || ('HTTP ' + resp.status));
            }
            root.innerHTML = '';
            spec.render(data, root);
            root.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = 'ERROR: ' + err.message;
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Panel montajı
    // ------------------------------------------------------------------
    function panelApplies(spec) {
        return !spec.motorTypes || spec.motorTypes.indexOf(cfg.motorType) !== -1;
    }

    function mountPanel(spec) {
        const pane = ensureCategory(spec.category);
        if (!pane) return;
        const empty = pane.querySelector('.ad-empty');
        if (empty) empty.remove();
        const holder = document.createElement('div');
        holder.innerHTML = panelSectionHtml(spec);
        pane.appendChild(holder.firstElementChild);

        document.getElementById('ad_run_' + spec.id)
            .addEventListener('click', function () { runPanel(spec); });
        // Kullanıcı bir alanı elle değiştirirse öneriler onu bir daha ezmez
        const sec = document.getElementById('ad_sec_' + spec.id);
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            el.addEventListener('input', function () { el.dataset.dirty = '1'; });
            el.addEventListener('change', function () { el.dataset.dirty = '1'; });
        });
        // İlk montajda sonuçtan önerileri doldur (varsa)
        applySuggestions(spec);
    }

    // ------------------------------------------------------------------
    // Genel API
    // ------------------------------------------------------------------
    function register(spec) {
        if (!spec || !spec.id || !spec.category || !spec.endpoint
            || typeof spec.render !== 'function') {
            if (window.console) console.warn('AnalysisDock.register: invalid spec', spec);
            return;
        }
        if (registeredIds[spec.id]) {
            if (window.console) console.warn('AnalysisDock.register: duplicate id', spec.id);
            return;
        }
        registeredIds[spec.id] = true;
        registry.push(spec);
        if (inited && panelApplies(spec)) mountPanel(spec);
    }

    function init(options) {
        if (inited) return;
        cfg = options || {};
        cfg.motorType = cfg.motorType || 'hybrid';

        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = dockHtml();
        const dock = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(dock, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(dock);
        }
        inited = true;

        // Temel sekmeler her zaman kurulur; yeni kategoriler talep üzerine eklenir
        BASE_CATEGORIES.forEach(ensureCategory);
        registry.filter(panelApplies).forEach(mountPanel);
        selectCategory(activeCategory || BASE_CATEGORIES[0]);
    }

    function getMotorType() {
        return cfg.motorType || 'hybrid';
    }

    // Sonuç değiştiğinde entegrasyon katmanı çağırabilir: dirty olmayan
    // alanları en güncel sonuçla tazeler (opsiyonel kolaylık).
    function refreshSuggestions() {
        if (!inited) return;
        registry.filter(panelApplies).forEach(applySuggestions);
    }

    window.AnalysisDock = {
        init: init,
        register: register,
        getMotorType: getMotorType,
        refreshSuggestions: refreshSuggestions,
        selectCategory: selectCategory,
        ui: {
            badge: badge,
            statCard: statCard,
            kvTable: kvTable,
            sectionTitle: sectionTitle,
            listBlock: listBlock,
            fmt: fmt,
            pick: pick,
            kindColor: kindColor,
            TBL: TBL,
            TD: TD,
        },
        // Test / hata ayıklama için salt-okunur kayıt listesi
        _registry: registry,
    };
})();
