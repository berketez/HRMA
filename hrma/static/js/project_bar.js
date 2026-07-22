/* ====================================================================
   HRMA Proje Şeridi — project_bar.js (v2.5.5)
   --------------------------------------------------------------------
   Proje kaydet/yükle arayüzü (backend: hrma/utils/projects_api.py,
   ARGE raporu 2026-07-21):

     GET  /api/projects              — liste (corrupt işaretli)
     POST /api/projects/save         — {name, payload, overwrite}
     GET  /api/projects/load/<name>  — tam belge + warnings

   Davranış sözleşmesi (ARGE raporu):
     - inputs.fields: sayfadaki id'li input/select/textarea → id->değer
       (checkbox bool, number number, diğerleri string). Dinamik panellerin
       (analiz güvertesi, 6-DOF, enjektör, transient) alanları HARİÇ.
     - inputs.dynamic.composition_rows: hibrit özel yakıt satırları
       (class tabanlı, id'siz — jenerik serileştirici kaçırır).
     - inputs.ui_state: hibrit sekme durumu (design/environment/analysis).
     - inputs.dock_overrides: güvertede data-dirty=1 işaretli ad_f_* alanlar.
     - Geri yüklemede HER alana change (ve input) olayı yayılır — bağımlı
       hesaplar (updateMixtureDensity, expansion ratio vb.) tetiklensin.
     - Yükleme sonuç HESAPLAMAZ; kullanıcı Calculate'e basar.
     - results_summary yalnız liste kartlarında gösterilir, asla
       currentResults'a enjekte edilmez.

   Landing (index.html): yalnız "Recent Projects" şeridi — endpoint yoksa
   ya da liste boşsa şerit hiç görünmez.

   Uçlar app'e kayıtlı olmayabilir (test ortamı): her fetch hatası
   toast + konsol ile zarifçe raporlanır, sayfa çalışmaya devam eder.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    // ------------------------------------------------------------------
    // Sayfa tespiti
    // ------------------------------------------------------------------
    var PATH_TYPE = { '/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid' };
    var TYPE_PATH = { hybrid: '/hybrid', solid: '/solid', liquid: '/liquid' };
    var path = location.pathname.replace(/\/+$/, '') || '/';
    var motorType = PATH_TYPE[path] || null;
    var isLanding = (path === '/');
    if (!motorType && !isLanding) return;      // formulas vb. — şerit yok

    // Proje adı kuralı (sunucudaki beyaz listenin istemci aynası):
    // [A-Za-z0-9 _.-] 1-80, nokta ile başlayamaz, nokta/boşluk ile bitemez
    var NAME_RE = /^[A-Za-z0-9 _.\-]{1,80}$/;
    function validName(name) {
        if (typeof name !== 'string') return false;
        if (!NAME_RE.test(name)) return false;
        if (name.charAt(0) === '.') return false;
        if (/[. ]$/.test(name)) return false;
        return true;
    }

    // Dinamik panel kökleri: bu alt ağaçlardaki alanlar projeye SERİLEŞTİRİLMEZ
    // (güverte ad_f_* alanları ayrıca dock_overrides olarak ele alınır)
    var DYNAMIC_ROOTS = '#analysisDock, #sixDofPanel, #injectorPanel, '
        + '#transientPanel, #hrmaProjectBar, #hrmaProjectModal, #stepImportModal';

    var NEW_NAME_SS_KEY = 'hrma_pending_new_project';

    var state = {
        name: null,          // aktif proje adı (null = kaydedilmemiş)
        savedName: null,     // diskte var olduğu bilinen ad (overwrite kararı)
        dirty: false,
        restoring: false,
        source: null,        // "STEP import (x.step)" gibi köken notu
    };

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                     '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    // Ana yol import_ui.js'tir (advanced/liquid/solid). Ana sayfada import_ui
    // yüklü DEĞİLDİR, bu yüzden aşağıdaki yedek çalışır. İki uygulama da AYNI
    // istif kabını (#hrma-toast-stack) kullanır: bildirimler üst üste binmez,
    // alt kenardan yukarı dizilir (bkz. import_ui.js'teki İSTİFLEME notu).
    var TOAST_HOST_ID = 'hrma-toast-stack';

    function toastHost() {
        var host = document.getElementById(TOAST_HOST_ID);
        if (host) return host;
        host = document.createElement('div');
        host.id = TOAST_HOST_ID;
        host.style.cssText =
            'position:fixed; right:18px; bottom:18px; z-index:99995;' +
            'display:flex; flex-direction:column; gap:8px; align-items:flex-end;' +
            'pointer-events:none;';
        document.body.appendChild(host);
        return host;
    }

    function toast(message, kind) {
        if (window.HRMAImportUI && window.HRMAImportUI.toast) {
            window.HRMAImportUI.toast(message, kind);
            return;
        }
        try {
            var colors = { ok: 'var(--hd-green, #2dd4a8)', err: 'var(--hd-red, #ff5d73)',
                           warn: 'var(--hd-orange, #ff8c33)', info: 'var(--hd-cyan, #00e5ff)' };
            var c = colors[kind] || colors.info;
            var node = document.createElement('div');
            node.style.cssText =
                'max-width:420px; padding:12px 16px; font-size:0.82rem;' +
                'font-family:var(--hd-mono, monospace); color:' + c + ';' +
                'background:var(--hd-panel-solid, #0a1524); border:1px solid ' + c + ';' +
                'border-radius:var(--hd-radius-sm, 8px); pointer-events:auto;' +
                'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));';
            node.textContent = String(message);
            toastHost().appendChild(node);
            setTimeout(function () {
                var host = node.parentNode;
                if (host) host.removeChild(node);
                if (host && host.id === TOAST_HOST_ID && !host.firstChild
                    && host.parentNode) {
                    host.parentNode.removeChild(host);
                }
            }, 6000);
        } catch (e) { /* sessiz */ }
    }

    // ==================================================================
    // SERİLEŞTİRME
    // ==================================================================

    function serializeFields() {
        var fields = {};
        // BELGE GENELİ tarama (v2.5.5 duman testi düzeltmesi): hibrit
        // sayfada form bölümleri .container içinde değil .panel div'lerinde
        // yaşıyor — .container beyaz listesi 226 alandan yalnız 15'ini
        // görüyordu (geometri/yakıt/oksitleyici kaydedilmiyordu). Dinamik
        // panel ve kendi modallarımız DYNAMIC_ROOTS ile zaten dışlanır.
        var nodes = document.querySelectorAll(
            'input[id], select[id], textarea[id]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var type = (el.getAttribute('type') || '').toLowerCase();
            if (type === 'file' || type === 'button' || type === 'submit'
                || type === 'radio') continue;
            if (el.closest && el.closest(DYNAMIC_ROOTS)) continue;
            if (el.id === 'langSelect') continue;
            if (type === 'checkbox') {
                fields[el.id] = !!el.checked;
            } else if (type === 'number') {
                var raw = String(el.value);
                if (raw.trim() === '') {
                    fields[el.id] = '';
                } else {
                    var num = parseFloat(raw);
                    fields[el.id] = isFinite(num) ? num : raw;
                }
            } else {
                fields[el.id] = String(el.value);
            }
        }
        return fields;
    }

    // Hibrit özel yakıt bileşimi satırları (class tabanlı, id'siz)
    function serializeCompositionRows() {
        var rows = document.querySelectorAll('#composition_rows .composition-row');
        if (!rows.length) return null;
        var out = [];
        for (var i = 0; i < rows.length; i++) {
            var compound = rows[i].querySelector('.compound');
            var pct = rows[i].querySelector('.percentage');
            var pctVal = pct ? parseFloat(pct.value) : NaN;
            out.push({
                compound: compound ? String(compound.value) : '',
                percentage: isFinite(pctVal) ? pctVal : '',
            });
        }
        return out;
    }

    // Hibrit sekme durumu — hangi kap "active" ise onun adı saklanır
    function serializeUiState() {
        if (motorType !== 'hybrid') return null;
        var ui = {};
        function activeOf(pairs) {
            for (var i = 0; i < pairs.length; i++) {
                var el = document.getElementById(pairs[i][0]);
                if (el && el.classList.contains('active')) return pairs[i][1];
            }
            return null;
        }
        var env = activeOf([['single_env', 'single'], ['profile_env', 'profile']]);
        var design = activeOf([['thrust_time_design', 'thrust_time'],
                               ['total_impulse_design', 'total_impulse']]);
        var analysis = activeOf([['single_tab', 'single'], ['parametric_tab', 'parametric'],
                                 ['trajectory_tab', 'trajectory']]);
        if (env) ui.environment_tab = env;
        if (design) ui.design_tab = design;
        if (analysis) ui.analysis_tab = analysis;
        return Object.keys(ui).length ? ui : null;
    }

    // Analiz güvertesi: yalnız kullanıcının elle değiştirdiği (data-dirty=1)
    // ad_f_* alanları — öneri mekanizması bozulmasın (ARGE kararı)
    function serializeDockOverrides() {
        var out = {};
        var nodes = document.querySelectorAll('#analysisDock [id^="ad_f_"]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el.dataset || el.dataset.dirty !== '1') continue;
            if (el.tagName === 'SELECT') {
                out[el.id] = String(el.value);
            } else {
                var v = parseFloat(el.value);
                out[el.id] = isFinite(v) ? v : String(el.value);
            }
        }
        return Object.keys(out).length ? out : null;
    }

    // Küçük sonuç özeti — yalnız liste kartları için; panellere geri basılmaz
    function serializeResultsSummary() {
        var cr = window.currentResults;
        if (!cr) return null;
        var out = {};
        function put(key, v) {
            if (typeof v === 'number' && isFinite(v)) out[key] = v;
        }
        if (motorType === 'hybrid') {
            var m = cr.motor || {};
            put('thrust_N', m.thrust);
            put('isp_s', m.isp);
            put('burn_time_s', m.burn_time);
            put('chamber_pressure_bar', m.chamber_pressure);
            put('total_impulse_Ns', m.total_impulse);
        } else if (motorType === 'solid') {
            put('total_impulse_Ns', cr.total_impulse);
            put('burn_time_s', cr.burn_time);
            put('chamber_pressure_bar', cr.chamber_pressure);
            put('isp_s', cr.isp_sea_level);
            if (cr.thrust_curve && Array.isArray(cr.thrust_curve.thrust)
                && cr.thrust_curve.thrust.length) {
                put('peak_thrust_N', Math.max.apply(null, cr.thrust_curve.thrust));
            }
        } else if (motorType === 'liquid') {
            put('thrust_N', cr.thrust);
            put('isp_s', cr.isp_sea_level);
            put('isp_vacuum_s', cr.isp_vacuum);
            put('chamber_pressure_bar', cr.chamber_pressure);
        }
        if (!Object.keys(out).length) return null;
        if (typeof window.HRMA_VERSION === 'string') {
            out.computed_with_version = window.HRMA_VERSION;
        }
        return out;
    }

    function buildPayload(name) {
        var inputs = { fields: serializeFields() };
        var rows = serializeCompositionRows();
        if (rows) inputs.dynamic = { composition_rows: rows };
        var ui = serializeUiState();
        if (ui) inputs.ui_state = ui;
        var dock = serializeDockOverrides();
        if (dock) inputs.dock_overrides = dock;

        var payload = {
            format: 'hrma-project',
            format_version: 1,
            motor_type: motorType,
            name: name,
            inputs: inputs,
        };
        var descEl = document.getElementById('motor_description');
        if (descEl && String(descEl.value).trim()) {
            payload.description = String(descEl.value);
        }
        var summary = serializeResultsSummary();
        if (summary) payload.results_summary = summary;
        return payload;
    }

    // ==================================================================
    // GERİ YÜKLEME
    // ==================================================================

    function dispatchFieldEvents(el) {
        // Bağımlı hesaplar iki olaydan birini dinleyebiliyor (solid sayfası
        // expansion ratio 'input', hibrit fuel_type 'change') — ikisi de yayılır
        try {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) { /* eski tarayıcı — sessiz */ }
    }

    function restoreUiState(ui) {
        if (!ui || motorType !== 'hybrid') return;
        function fixButtons(fnName, value) {
            var btn = document.querySelector(
                'button[onclick*="' + fnName + '(\'' + value + '\')"]');
            if (btn && btn.parentElement) {
                var tabs = btn.parentElement.querySelectorAll('.tab');
                for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
                btn.classList.add('active');
            }
        }
        if (ui.environment_tab && typeof window.switchEnvironmentTab === 'function') {
            window.switchEnvironmentTab(ui.environment_tab);
            fixButtons('switchEnvironmentTab', ui.environment_tab);
        }
        if (ui.design_tab && typeof window.switchDesignTab === 'function') {
            window.switchDesignTab(ui.design_tab);
            fixButtons('switchDesignTab', ui.design_tab);
        }
        if (ui.analysis_tab && typeof window.switchTab === 'function') {
            window.switchTab(ui.analysis_tab);
        }
    }

    function restoreFields(fields) {
        var skipped = 0;
        Object.keys(fields || {}).forEach(function (id) {
            var el = document.getElementById(id);
            if (!el || el.closest(DYNAMIC_ROOTS)) { skipped += 1; return; }
            var v = fields[id];
            var type = (el.getAttribute('type') || '').toLowerCase();
            if (type === 'checkbox') {
                el.checked = !!v;
            } else {
                el.value = (v === null || v === undefined) ? '' : String(v);
            }
            dispatchFieldEvents(el);
        });
        return skipped;
    }

    function restoreCompositionRows(rows) {
        if (!Array.isArray(rows) || !rows.length) return;
        var container = document.getElementById('composition_rows');
        if (!container || typeof window.addCompositionRow !== 'function') return;
        container.innerHTML = '';
        rows.forEach(function (row) {
            window.addCompositionRow();
            var last = container.lastElementChild;
            if (!last) return;
            var compound = last.querySelector('.compound');
            var pct = last.querySelector('.percentage');
            if (compound) compound.value = row.compound != null ? row.compound : '';
            if (pct) pct.value = row.percentage != null ? row.percentage : '';
            if (compound) dispatchFieldEvents(compound);
            if (pct) dispatchFieldEvents(pct);
        });
    }

    // Güverte alanları DOMContentLoaded sonrasında panel kayıtlarıyla kurulur;
    // alanlar görünene dek kısa aralıklarla dener (montaj yarışı koruması)
    function restoreDockOverrides(overrides) {
        if (!overrides || !Object.keys(overrides).length) return;
        var tries = 0;
        var timer = setInterval(function () {
            tries += 1;
            var pending = 0;
            Object.keys(overrides).forEach(function (id) {
                var el = document.getElementById(id);
                if (!el) { pending += 1; return; }
                if (el.dataset.hrmaRestored === '1') return;
                el.value = String(overrides[id]);
                el.dataset.dirty = '1';
                el.dataset.hrmaRestored = '1';
            });
            if (!pending || tries > 40) clearInterval(timer);
        }, 250);
    }

    function applyProject(doc) {
        state.restoring = true;
        try {
            var inputs = doc.inputs || {};
            restoreUiState(inputs.ui_state);
            var skipped = restoreFields(inputs.fields);
            if (inputs.dynamic && inputs.dynamic.composition_rows) {
                restoreCompositionRows(inputs.dynamic.composition_rows);
            }
            restoreDockOverrides(inputs.dock_overrides);
            if (skipped > 0) {
                toast(TF('proj.loadedWithSkips', { n: skipped },
                    '{n} saved field(s) have no matching input on this page and were skipped.'),
                    'warn');
            }
        } finally {
            state.restoring = false;
        }
        state.dirty = false;
        // Geri yüklemenin tetiklediği sayfa işleyicileri (karışım yoğunluğu,
        // önizleme vb.) asenkron olay üretebilir — kısa tolerans penceresi
        // içinde gelen olaylar kullanıcı düzenlemesi sayılmaz (sahte yıldız).
        state.restoreGraceUntil = Date.now() + 800;
        renderBar();
    }

    // ==================================================================
    // HTTP
    // ==================================================================

    async function apiList() {
        var resp = await fetch('/api/projects');
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok || !data || !Array.isArray(data.projects)) {
            throw new Error((data && data.error) || ('HTTP ' + resp.status));
        }
        return data.projects;
    }

    async function apiSave(name, overwrite) {
        var resp = await fetch('/api/projects/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, payload: buildPayload(name),
                                   overwrite: !!overwrite }),
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok) {
            var err = new Error((data && data.error) || ('HTTP ' + resp.status));
            err.status = resp.status;
            throw err;
        }
        return data;
    }

    async function apiLoad(name) {
        var resp = await fetch('/api/projects/load/' + encodeURIComponent(name));
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok || !data || !data.project) {
            throw new Error((data && data.error) || ('HTTP ' + resp.status));
        }
        return data;
    }

    // ==================================================================
    // MODAL ALTYAPISI (update_check.js enjekte-modal deseni)
    // ==================================================================

    function closeModal() {
        var m = document.getElementById('hrmaProjectModal');
        if (m) m.remove();
    }

    function openModalShell(titleText) {
        closeModal();
        var wrap = document.createElement('div');
        wrap.id = 'hrmaProjectModal';
        wrap.style.cssText =
            'position:fixed; inset:0; z-index:99980; display:flex;' +
            'align-items:center; justify-content:center;' +
            'background:rgba(2,6,12,0.72); backdrop-filter:blur(4px);';
        var box = document.createElement('div');
        box.style.cssText =
            'max-width:560px; width:calc(100% - 48px); max-height:80vh;' +
            'overflow-y:auto; padding:22px 24px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2); font-family:var(--hd-sans, sans-serif);';
        var head = document.createElement('div');
        head.style.cssText =
            'font-size:14px; font-weight:700; letter-spacing:0.6px;' +
            'margin-bottom:12px; color:var(--hd-cyan, #00e5ff);' +
            'font-family:var(--hd-mono, monospace); text-transform:uppercase;';
        head.textContent = titleText;
        box.appendChild(head);
        wrap.appendChild(box);
        wrap.addEventListener('click', function (ev) {
            if (ev.target === wrap) closeModal();
        });
        document.body.appendChild(wrap);
        return box;
    }

    function modalButton(labelText, primary) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.style.cssText =
            'padding:9px 16px; font-size:13px; font-weight:600; cursor:pointer;' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            'font-family:var(--hd-sans, sans-serif);' +
            (primary
                ? 'border:none; background:var(--hd-cyan, #00e5ff); color:#04070d;'
                : 'background:transparent; color:var(--hd-ink, #cfe8f2);'
                  + 'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));');
        btn.textContent = labelText;
        return btn;
    }

    // Ad soran modal (Save As / New) — onSubmit(name) yalnız geçerli adla çağrılır
    function promptNameModal(titleText, defaultName, onSubmit) {
        var box = openModalShell(titleText);
        var label = document.createElement('div');
        label.style.cssText = 'font-size:13px; margin-bottom:6px;';
        label.textContent = T('proj.nameLabel', 'Project name');
        var input = document.createElement('input');
        input.type = 'text';
        input.value = defaultName || '';
        input.maxLength = 80;
        input.style.cssText =
            'width:100%; box-sizing:border-box; padding:9px 10px; font-size:14px;' +
            'background:var(--hd-inset, rgba(6,14,26,0.85));' +
            'color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:var(--hd-radius-sm, 8px); margin-bottom:6px;';
        var rule = document.createElement('div');
        rule.style.cssText =
            'font-size:11.5px; color:var(--hd-ink-dim, #7d97a5); margin-bottom:12px;';
        rule.textContent = T('proj.nameRule',
            'Allowed: letters, digits, space, _ . - (1-80 chars; must not start '
            + 'with a dot or end with a dot/space).');
        var err = document.createElement('div');
        err.style.cssText =
            'display:none; font-size:12px; color:var(--hd-red, #ff5d73); margin-bottom:10px;';
        err.textContent = T('proj.nameInvalid', 'Invalid project name — check the naming rule.');
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:10px; justify-content:flex-end;';
        var okBtn = modalButton(T('common.ok', 'OK'), true);
        var cancelBtn = modalButton(T('proj.btnCancel', 'Cancel'), false);
        cancelBtn.onclick = closeModal;
        function submit() {
            var name = input.value.trim();
            if (!validName(name)) {
                err.style.display = 'block';
                return;
            }
            closeModal();
            onSubmit(name);
        }
        okBtn.onclick = submit;
        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') submit();
        });
        row.appendChild(cancelBtn);
        row.appendChild(okBtn);
        box.appendChild(label);
        box.appendChild(input);
        box.appendChild(rule);
        box.appendChild(err);
        box.appendChild(row);
        input.focus();
        input.select();
    }

    function confirmModal(titleText, messageText, confirmLabel, onConfirm) {
        var box = openModalShell(titleText);
        var msg = document.createElement('div');
        msg.style.cssText = 'font-size:13.5px; line-height:1.55; margin-bottom:16px;';
        msg.textContent = messageText;
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:10px; justify-content:flex-end;';
        var okBtn = modalButton(confirmLabel, true);
        var cancelBtn = modalButton(T('proj.btnCancel', 'Cancel'), false);
        cancelBtn.onclick = closeModal;
        okBtn.onclick = function () { closeModal(); onConfirm(); };
        row.appendChild(cancelBtn);
        row.appendChild(okBtn);
        box.appendChild(msg);
        box.appendChild(row);
    }

    // ==================================================================
    // KAYDET / AÇ / YENİ akışları
    // ==================================================================

    function defaultNameSuggestion() {
        var el = document.getElementById('motor_name');
        var candidate = el ? String(el.value).trim() : '';
        if (candidate && validName(candidate)) return candidate;
        return state.name || '';
    }

    async function doSave(name, overwrite) {
        try {
            var info = await apiSave(name, overwrite);
            state.name = info.name || name;
            state.savedName = state.name;
            state.dirty = false;
            renderBar();
            toast(TF('proj.saved', { name: state.name }, 'Project "{name}" saved.'), 'ok');
        } catch (err) {
            if (err.status === 409) {
                // Aynı ad diskte var — üzerine yazma onayı (Save As önerisi)
                confirmModal(T('proj.saveAsTitle', 'Save Project As'),
                    TF('proj.exists', { name: name },
                       'A project named "{name}" already exists.') + ' '
                    + T('proj.overwriteQ', 'Overwrite the existing project?'),
                    T('proj.btnOverwrite', 'Overwrite'),
                    function () { doSave(name, true); });
                return;
            }
            console.error('HRMA project save failed:', err);
            toast(TF('proj.saveFailed', { message: err.message },
                     'Save failed: {message}'), 'err');
        }
    }

    function onSave() {
        if (state.name && state.savedName === state.name) {
            doSave(state.name, true);       // mevcut projeye kaydet
            return;
        }
        onSaveAs();
    }

    function onSaveAs() {
        promptNameModal(T('proj.saveAsTitle', 'Save Project As'),
            defaultNameSuggestion(),
            function (name) {
                doSave(name, name === state.savedName);
            });
    }

    function onNew() {
        function start() {
            promptNameModal(T('proj.newTitle', 'New Project'), '', function (name) {
                try { sessionStorage.setItem(NEW_NAME_SS_KEY, name); }
                catch (e) { /* gizli mod */ }
                state.dirty = false;    // onay alındı; beforeunload tekrar sormasın
                location.href = location.pathname;      // temiz varsayılanlar
            });
        }
        if (state.dirty) {
            confirmModal(T('proj.newTitle', 'New Project'),
                T('proj.unsavedWarn', 'You have unsaved changes. Continue and discard them?'),
                T('common.ok', 'OK'), start);
        } else {
            start();
        }
    }

    async function loadIntoPage(name) {
        try {
            var data = await apiLoad(name);
            var doc = data.project || {};
            var docType = doc.motor_type;
            if (docType && docType !== motorType && TYPE_PATH[docType]) {
                state.dirty = false;    // kullanıcı onayı alındı; ikinci (tarayıcı) uyarı çıkmasın
                location.href = TYPE_PATH[docType] + '?project=' + encodeURIComponent(name);
                return;
            }
            applyProject(doc);
            state.name = doc.name || name;
            state.savedName = state.name;
            renderBar();
            if (Array.isArray(data.warnings)) {
                data.warnings.forEach(function (w) { console.warn('HRMA project:', w); });
            }
            try {
                var url = location.pathname + '?project=' + encodeURIComponent(state.name);
                history.replaceState(null, '', url);
            } catch (e) { /* dosya protokolü vb. */ }
            toast(TF('proj.loaded', { name: state.name }, 'Project "{name}" loaded.'), 'ok');
        } catch (err) {
            console.error('HRMA project load failed:', err);
            toast(TF('proj.loadFailed', { message: err.message },
                     'Could not load project: {message}'), 'err');
        }
    }

    function summaryMini(summary) {
        if (!summary) return '';
        var bits = [];
        if (typeof summary.thrust_N === 'number' && isFinite(summary.thrust_N)) {
            bits.push('F ' + summary.thrust_N.toFixed(0) + ' N');
        }
        if (typeof summary.peak_thrust_N === 'number' && isFinite(summary.peak_thrust_N)) {
            bits.push('Fpk ' + summary.peak_thrust_N.toFixed(0) + ' N');
        }
        if (typeof summary.isp_s === 'number' && isFinite(summary.isp_s)) {
            bits.push('Isp ' + summary.isp_s.toFixed(1) + ' s');
        }
        if (typeof summary.total_impulse_Ns === 'number' && isFinite(summary.total_impulse_Ns)) {
            bits.push('It ' + summary.total_impulse_Ns.toFixed(0) + ' N·s');
        }
        return bits.join(' · ');
    }

    function projectRow(p) {
        var row = document.createElement('div');
        var corrupt = !!p.corrupt;
        row.style.cssText =
            'display:flex; gap:12px; align-items:baseline; flex-wrap:wrap;' +
            'padding:9px 10px; margin:4px 0; border:1px solid' +
            ' var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            (corrupt ? 'opacity:0.45; cursor:not-allowed;' : 'cursor:pointer;');
        var name = document.createElement('span');
        name.style.cssText =
            'font-weight:600; color:var(--hd-ink-strong, #eaf7fb); font-size:13.5px;';
        name.textContent = p.name;
        row.appendChild(name);
        var typeBadge = document.createElement('span');
        typeBadge.style.cssText =
            'font-family:var(--hd-mono, monospace); font-size:10.5px;' +
            'letter-spacing:0.08em; color:var(--hd-cyan, #00e5ff);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:5px; padding:1px 7px; text-transform:uppercase;';
        typeBadge.textContent = corrupt
            ? T('proj.corrupt', 'CORRUPT') : String(p.motor_type || '?');
        if (corrupt) typeBadge.style.color = 'var(--hd-red, #ff5d73)';
        row.appendChild(typeBadge);
        if (p.updated_at) {
            var date = document.createElement('span');
            date.style.cssText =
                'font-family:var(--hd-mono, monospace); font-size:11px;' +
                'color:var(--hd-ink-dim, #7d97a5);';
            date.textContent = String(p.updated_at).slice(0, 16).replace('T', ' ');
            row.appendChild(date);
        }
        var mini = summaryMini(p.results_summary);
        if (mini) {
            var sum = document.createElement('span');
            sum.style.cssText =
                'font-family:var(--hd-mono, monospace); font-size:11px;' +
                'color:var(--hd-ink-dim, #7d97a5);';
            sum.textContent = mini;
            row.appendChild(sum);
        }
        if (!corrupt) {
            row.addEventListener('click', function () {
                closeModal();
                function go() {
                    if (p.motor_type && p.motor_type !== motorType
                        && TYPE_PATH[p.motor_type]) {
                        state.dirty = false;   // onay alındı; tarayıcı uyarısı yinelenmesin
                        location.href = TYPE_PATH[p.motor_type]
                            + '?project=' + encodeURIComponent(p.name);
                    } else {
                        loadIntoPage(p.name);
                    }
                }
                if (state.dirty) {
                    confirmModal(T('proj.openTitle', 'Open Project'),
                        T('proj.unsavedWarn',
                          'You have unsaved changes. Continue and discard them?'),
                        T('common.ok', 'OK'), go);
                } else {
                    go();
                }
            });
        }
        return row;
    }

    async function onOpen() {
        var box = openModalShell(T('proj.openTitle', 'Open Project'));
        var status = document.createElement('div');
        status.style.cssText =
            'font-family:var(--hd-mono, monospace); font-size:12px;' +
            'color:var(--hd-ink-dim, #7d97a5); margin:4px 0;';
        status.textContent = T('common.loading', 'Loading…');
        box.appendChild(status);
        try {
            var projects = await apiList();
            status.remove();
            if (!projects.length) {
                var none = document.createElement('div');
                none.style.cssText = 'font-size:13px; color:var(--hd-ink-dim, #7d97a5);';
                none.textContent = T('proj.noProjects', 'No saved projects yet.');
                box.appendChild(none);
                return;
            }
            projects.forEach(function (p) { box.appendChild(projectRow(p)); });
        } catch (err) {
            console.error('HRMA project list failed:', err);
            status.textContent = TF('proj.listFailed', { message: err.message },
                'Could not load the project list: {message}');
            status.style.color = 'var(--hd-red, #ff5d73)';
        }
    }

    // ==================================================================
    // ŞERİT (navbar altı ince bar) — yalnız tasarım sayfaları
    // ==================================================================

    var barEls = {};

    function renderBar() {
        if (!barEls.name) return;
        barEls.name.textContent = state.name || T('proj.untitled', 'Untitled');
        barEls.star.style.display = state.dirty ? 'inline' : 'none';
        barEls.source.textContent = state.source
            ? TF('proj.sourceStep', { source: state.source }, 'Source: {source}') : '';
    }

    function buildBar() {
        var navbar = document.querySelector('.navbar');
        if (!navbar || !navbar.parentNode) return;
        var bar = document.createElement('div');
        bar.id = 'hrmaProjectBar';
        bar.style.cssText =
            'display:flex; align-items:center; gap:10px; flex-wrap:wrap;' +
            'padding:7px 24px; background:rgba(4, 9, 17, 0.85);' +
            'border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'font-family:var(--hd-mono, monospace); font-size:0.78rem;';

        var label = document.createElement('span');
        label.style.cssText =
            'color:var(--hd-ink-faint, #46606d); letter-spacing:0.1em;' +
            'text-transform:uppercase;';
        label.setAttribute('data-i18n', 'proj.label');
        label.textContent = T('proj.label', 'Project');
        bar.appendChild(label);

        var name = document.createElement('span');
        name.style.cssText = 'color:var(--hd-cyan-soft, #6fd3e6); font-weight:600;';
        bar.appendChild(name);

        var star = document.createElement('span');
        star.style.cssText = 'color:var(--hd-orange, #ff8c33); display:none;';
        star.textContent = '*';
        star.title = T('proj.dirtyHint', 'Unsaved changes');
        bar.appendChild(star);

        var btnStyle =
            'padding:4px 12px; font-size:0.72rem; letter-spacing:0.05em; cursor:pointer;' +
            'background:transparent; color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:6px; font-family:var(--hd-mono, monospace);';
        function barButton(key, labelText, handler) {
            var b = document.createElement('button');
            b.type = 'button';
            b.style.cssText = btnStyle;
            b.setAttribute('data-i18n', key);
            b.textContent = labelText;
            b.addEventListener('click', handler);
            bar.appendChild(b);
            return b;
        }
        barButton('proj.btnSave', T('proj.btnSave', 'Save'), onSave);
        barButton('proj.btnSaveAs', T('proj.btnSaveAs', 'Save As'), onSaveAs);
        barButton('proj.btnOpen', T('proj.btnOpen', 'Open'), onOpen);
        barButton('proj.btnNew', T('proj.btnNew', 'New'), onNew);
        barButton('proj.btnImportStep',
                  T('proj.btnImportStep', 'Import from CAD (STEP)'), function () {
            if (window.StepImportUI && window.StepImportUI.open) {
                window.StepImportUI.open();
            } else {
                toast(T('stepimp.notLoaded',
                    'STEP import module is not loaded on this page.'), 'err');
            }
        });

        var source = document.createElement('span');
        source.style.cssText =
            'margin-left:auto; color:var(--hd-ink-dim, #7d97a5); font-size:0.72rem;';
        bar.appendChild(source);

        navbar.parentNode.insertBefore(bar, navbar.nextSibling);
        barEls = { name: name, star: star, source: source };
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(bar);
        renderBar();
    }

    // ==================================================================
    // KİRLİ (dirty) TAKİBİ + beforeunload
    // ==================================================================

    function watchDirty() {
        function onEdit(ev) {
            if (state.restoring) return;
            var t = ev.target;
            if (state.restoring) return;    // geri yükleme olayları düzenleme değil
            if (Date.now() < (state.restoreGraceUntil || 0)) return;
            if (!t || !t.tagName) return;
            var tag = t.tagName.toUpperCase();
            if (tag !== 'INPUT' && tag !== 'SELECT' && tag !== 'TEXTAREA') return;
            if (t.id === 'langSelect') return;
            if (t.closest('#hrmaProjectBar, #hrmaProjectModal, #stepImportModal')) return;
            if (t.closest('#analysisDock')) {
                // Güvertede yalnız ad_f_* alanları projeye girer
                if (!/^ad_f_/.test(t.id || '')) return;
            } else if (t.closest('#sixDofPanel, #injectorPanel, #transientPanel')) {
                return;                     // dinamik panel alanları proje dışı
            }
            if (!state.dirty) {
                state.dirty = true;
                renderBar();
            }
        }
        document.addEventListener('input', onEdit, true);
        document.addEventListener('change', onEdit, true);
        window.addEventListener('beforeunload', function (ev) {
            if (!state.dirty) return undefined;
            ev.preventDefault();
            ev.returnValue = '';
            return '';
        });
    }

    // ==================================================================
    // LANDING — Recent Projects şeridi (boşsa / uç yoksa hiç görünmez)
    // ==================================================================

    async function buildRecentStrip() {
        var projects;
        try {
            projects = await apiList();
        } catch (err) {
            console.warn('HRMA recent projects unavailable:', err.message);
            return;                          // uç yok / hata → şerit yok
        }
        var usable = projects.filter(function (p) { return !p.corrupt; }).slice(0, 5);
        if (!usable.length) return;
        var container = document.querySelector('.container');
        if (!container) return;
        var section = document.createElement('div');
        section.id = 'hrmaRecentProjects';
        section.style.cssText = 'margin-top:46px;';
        var title = document.createElement('div');
        title.className = 'section-label';
        title.setAttribute('data-i18n', 'proj.recentTitle');
        title.textContent = T('proj.recentTitle', 'Recent Projects');
        section.appendChild(title);
        var list = document.createElement('div');
        list.style.cssText =
            'display:flex; gap:12px; flex-wrap:wrap; justify-content:center;';
        usable.forEach(function (p) {
            var a = document.createElement('a');
            var target = TYPE_PATH[p.motor_type] || '/hybrid';
            a.href = target + '?project=' + encodeURIComponent(p.name);
            a.className = 'aux-link';
            var mini = summaryMini(p.results_summary);
            a.textContent = p.name + ' [' + String(p.motor_type || '?').toUpperCase() + ']'
                + (mini ? ' — ' + mini : '');
            list.appendChild(a);
        });
        section.appendChild(list);
        var aux = container.querySelector('.aux-links');
        if (aux) container.insertBefore(section, aux);
        else container.appendChild(section);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(section);
    }

    // ==================================================================
    // KURULUM
    // ==================================================================

    function initDesignPage() {
        buildBar();
        watchDirty();
        // Dil değişince serbest metinler (proje adı yer tutucusu, kaynak notu)
        // yeniden basılır; data-i18n taşıyan düğmeleri I18N.apply zaten çevirir
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(renderBar);
        // ?project=<ad> ile açıldıysa otomatik yükle
        var params = null;
        try { params = new URLSearchParams(location.search); } catch (e) { params = null; }
        var wanted = params ? params.get('project') : null;
        if (wanted) {
            loadIntoPage(wanted);
            return;
        }
        // "New" akışından gelen bekleyen ad
        try {
            var pending = sessionStorage.getItem(NEW_NAME_SS_KEY);
            if (pending) {
                sessionStorage.removeItem(NEW_NAME_SS_KEY);
                state.name = pending;
                state.savedName = null;
                renderBar();
                toast(TF('proj.newStarted', { name: pending },
                    'New project "{name}" — fill the form and press Save.'), 'info');
            }
        } catch (e) { /* gizli mod */ }
    }

    function init() {
        if (isLanding) buildRecentStrip();
        else initDesignPage();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Dış modüller için küçük API (step_import_ui "Apply to form" sonrası
    // köken notu düşer ve şeridi kirli işaretler)
    window.HRMAProjectBar = {
        setSource: function (text) {
            state.source = text ? String(text) : null;
            if (!state.restoring && text) state.dirty = true;
            renderBar();
        },
        markDirty: function () {
            state.dirty = true;
            renderBar();
        },
        // Test / hata ayıklama kancaları (saf yardımcılar)
        _validName: validName,
        _buildPayload: buildPayload,
        _state: state,
    };
})();
