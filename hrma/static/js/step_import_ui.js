/* ====================================================================
   HRMA STEP Eşleme Ekranı — step_import_ui.js (v2.5.5)
   --------------------------------------------------------------------
   POST /api/import/step (hrma/importers/step_api.py) sonucunu modal bir
   eşleme ekranına bağlar:

     (a) Kesit çizimi — profile_2d inner/outer meridyen poligonları
         (z yatay, r dikey; alt yarı aynalı), Plotly + plotly_dark teması.
     (b) Aday listesi — candidates tablosu; satır hover'ında kesitte
         z-aralığı vurgusu (Plotly shapes).
     (c) Öneri eşleme formu — suggestions'taki HER alan için değer +
         confidence rozeti + aday referansı. GELMEYEN alan boş kalır ve
         "not found" etiketi alır — ASLA tahmin üretilmez (uydurma-veri
         yasağı; backend de aynı sözleşmede).
     (d) Apply to form — onaylı değerler sayfanın form alanlarına yazılır
         (change + input olayı yayılır), throat+exit'ten expansion ratio
         hesabı sayfada alan varsa yapılır, proje şeridine "Source: STEP
         import" notu düşülür.
     (e) warnings listesi + montajda katı seçici (solids → solid_index
         ile yeniden POST).

   Hatalar: 501 dependency_missing → açık kurulum mesajı; diğer 4xx/5xx
   → hata mesajı. Uç kayıtlı değilse fetch hatası da aynı yoldan düşer.
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

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                     '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    var PATH_TYPE = { '/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid' };
    var motorType = PATH_TYPE[location.pathname.replace(/\/+$/, '') || '/'] || null;

    // STEP önerisi -> sayfa form alanı eşlemesi (yalnız SAYFADA VAR OLAN
    // id'lere yazılır; birimler sözleşme gereği mm'ye normalize gelir).
    // expansionField: throat+exit çapından ε=(De/Dt)^2 yazılacak alan.
    // solid sayfasında expansion_ratio alanı readonly'dir ve sayfanın kendi
    // updateExpansionRatio dinleyicisi throat/exit 'input' olayıyla dolar.
    var PAGE_MAPS = {
        hybrid: {
            fields: {
                chamber_diameter_mm: 'chamber_diameter_input',
                chamber_length_mm: 'chamber_length_override',
                wall_thickness_mm: 'wall_thickness',
            },
            expansionField: 'expansion_ratio',
        },
        solid: {
            fields: {
                throat_diameter_mm: 'throat_diameter',
                exit_diameter_mm: 'exit_diameter',
                chamber_diameter_mm: 'chamber_diameter',
                chamber_length_mm: 'grain_length',
                wall_thickness_mm: 'case_thickness',
            },
            expansionField: null,
        },
        liquid: {
            fields: {
                throat_diameter_mm: 'throat_diameter',
                chamber_diameter_mm: 'chamber_diameter',
                wall_thickness_mm: 'chamber_wall_thickness',
            },
            expansionField: 'nozzle_expansion_ratio',
        },
    };

    // Öneri anahtarları — ekranda gösterilme sırası ve etiket anahtarları
    var SUGGESTION_KEYS = [
        ['throat_diameter_mm', 'stepimp.fieldThroat', 'Throat diameter (mm)'],
        ['exit_diameter_mm', 'stepimp.fieldExit', 'Exit diameter (mm)'],
        ['chamber_diameter_mm', 'stepimp.fieldChamberD', 'Chamber diameter (mm)'],
        ['chamber_length_mm', 'stepimp.fieldChamberL', 'Chamber length (mm)'],
        ['wall_thickness_mm', 'stepimp.fieldWall', 'Wall thickness (mm)'],
    ];

    var CONF_COLORS = {
        high: 'var(--hd-green, #2dd4a8)',
        medium: 'var(--hd-yellow, #ffd166)',
        low: 'var(--hd-orange, #ff8c33)',
    };

    var lastFile = null;        // katı seçiminde yeniden POST için saklanır
    var lastData = null;
    var plotEl = null;

    function toast(message, kind) {
        if (window.HRMAImportUI && window.HRMAImportUI.toast) {
            window.HRMAImportUI.toast(message, kind);
        } else if (window.console) {
            console.warn('HRMA STEP import:', message);
        }
    }

    // ------------------------------------------------------------------
    // Modal iskeleti
    // ------------------------------------------------------------------
    function closeModal() {
        var m = document.getElementById('stepImportModal');
        if (m) {
            if (plotEl && window.Plotly && typeof Plotly.purge === 'function') {
                try { Plotly.purge(plotEl); } catch (e) { /* boş */ }
            }
            plotEl = null;
            m.remove();
        }
    }

    function openModalShell() {
        closeModal();
        var wrap = document.createElement('div');
        wrap.id = 'stepImportModal';
        wrap.style.cssText =
            'position:fixed; inset:0; z-index:99985; display:flex;' +
            'align-items:center; justify-content:center;' +
            'background:rgba(2,6,12,0.72); backdrop-filter:blur(4px);';
        var box = document.createElement('div');
        box.style.cssText =
            'max-width:980px; width:calc(100% - 40px); max-height:88vh;' +
            'overflow-y:auto; padding:22px 26px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2); font-family:var(--hd-sans, sans-serif);';
        var head = document.createElement('div');
        head.style.cssText =
            'display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;' +
            'margin-bottom:10px;';
        var title = document.createElement('span');
        title.style.cssText =
            'font-size:14px; font-weight:700; letter-spacing:0.6px;' +
            'color:var(--hd-cyan, #00e5ff); font-family:var(--hd-mono, monospace);' +
            'text-transform:uppercase;';
        title.setAttribute('data-i18n', 'stepimp.title');
        title.textContent = T('stepimp.title', 'STEP Import — Dimension Mapping');
        head.appendChild(title);
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.style.cssText =
            'margin-left:auto; padding:5px 14px; cursor:pointer; font-size:12px;' +
            'background:transparent; color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius-sm, 8px);';
        closeBtn.setAttribute('data-i18n', 'common.close');
        closeBtn.textContent = T('common.close', 'Close');
        closeBtn.onclick = closeModal;
        head.appendChild(closeBtn);
        box.appendChild(head);
        var body = document.createElement('div');
        body.id = 'stepImportBody';
        box.appendChild(body);
        wrap.appendChild(box);
        document.body.appendChild(wrap);
        return body;
    }

    // ------------------------------------------------------------------
    // Analiz çağrısı
    // ------------------------------------------------------------------
    async function analyze(file, solidIndex) {
        var body = openModalShell();
        body.innerHTML =
            '<div style="font-family:var(--hd-mono, monospace); font-size:0.82rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);">'
            + escapeHtml(T('stepimp.analyzing', 'ANALYZING STEP GEOMETRY…')) + '</div>';
        try {
            var form = new FormData();
            form.append('file', file, file.name);
            if (solidIndex !== undefined && solidIndex !== null) {
                form.append('solid_index', String(solidIndex));
            }
            var resp = await fetch('/api/import/step', { method: 'POST', body: form });
            var data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (resp.status === 501 || (data && data.error_kind === 'dependency_missing')) {
                body.innerHTML = errorHtml(T('stepimp.depMissing',
                    'STEP analysis is not available in this installation — the CAD '
                    + 'geometry dependency is missing. Install the optional CAD '
                    + 'support package and restart HRMA.'));
                return;
            }
            if (!resp.ok || !data || data.error) {
                var msg = (data && data.error) || ('HTTP ' + resp.status);
                body.innerHTML = errorHtml(TF('stepimp.failed', { message: msg },
                    'STEP import failed: {message}'));
                return;
            }
            lastFile = file;
            lastData = data;
            renderResult(body, data, file);
        } catch (err) {
            console.error('HRMA STEP import failed:', err);
            body.innerHTML = errorHtml(TF('stepimp.failed', { message: err.message },
                'STEP import failed: {message}'));
        }
    }

    function errorHtml(message) {
        return '<div style="border:1px solid var(--hd-red, #ff5d73);'
            + ' color:var(--hd-red, #ff5d73); border-radius:8px; padding:12px 14px;'
            + ' font-size:0.85rem;">' + escapeHtml(message) + '</div>';
    }

    // ------------------------------------------------------------------
    // Sonuç ekranı
    // ------------------------------------------------------------------
    function sectionTitle(text) {
        return '<h4 style="margin:16px 0 6px; color:var(--hd-ink-strong, #eaf7fb);'
            + ' font-size:0.95rem;">' + escapeHtml(text) + '</h4>';
    }

    function warningsBlock(warnings) {
        if (!Array.isArray(warnings) || !warnings.length) return '';
        var items = warnings.map(function (w) {
            return '<li>' + escapeHtml(w) + '</li>';
        }).join('');
        return '<div style="border:1px solid var(--hd-orange, #ff8c33);'
            + ' border-radius:8px; padding:10px 14px; margin:10px 0;'
            + ' color:var(--hd-orange, #ff8c33); font-size:0.82rem;">'
            + '<strong>' + escapeHtml(T('stepimp.warnings', 'STEP import warnings'))
            + '</strong><ul style="margin:6px 0 0 18px;">' + items + '</ul></div>';
    }

    function renderResult(body, data, file) {
        var html = '';

        // Üst bilgi satırı: dosya, birim, süre
        html += '<div style="font-family:var(--hd-mono, monospace); font-size:0.75rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin-bottom:6px;">'
            + escapeHtml(String(data.filename || file.name)) + ' | '
            + escapeHtml(TF('stepimp.unitLine', { unit: String(data.unit || '?'),
                                                  s: String(data.analysis_seconds) },
                'unit: {unit} (normalized to mm) | analysis: {s} s')) + '</div>';

        html += warningsBlock(data.warnings);

        // (e) Montaj: katı seçici
        if (Array.isArray(data.solids) && data.solids.length > 1) {
            var opts = data.solids.map(function (s) {
                var sel = (s.index === data.solid_analyzed_index) ? ' selected' : '';
                return '<option value="' + s.index + '"' + sel + '>'
                    + escapeHtml(s.name || ('solid_' + s.index))
                    + ' (' + (s.volume_mm3 / 1000).toFixed(1) + ' cm3)</option>';
            }).join('');
            html += '<div style="margin:8px 0;"><label style="font-size:0.82rem;'
                + ' margin-right:8px;">'
                + escapeHtml(T('stepimp.solids', 'Solid to analyze')) + '</label>'
                + '<select id="si_solid_select" style="max-width:320px;">'
                + opts + '</select></div>';
        }

        // (a) Kesit çizimi
        html += sectionTitle(T('stepimp.crossSection', 'Cross-Section (meridian profile)'));
        html += '<div id="si_profile_plot" style="min-height:320px;"></div>';

        // (b) Aday listesi
        html += sectionTitle(T('stepimp.candidates', 'Detected surfaces'));
        var cands = Array.isArray(data.candidates) ? data.candidates : [];
        if (cands.length) {
            var td = 'padding:5px 8px; border-bottom:1px solid'
                + ' var(--hd-line, rgba(0,229,255,0.14));';
            var rows = cands.map(function (c, i) {
                var dTxt = (typeof c.d1_mm === 'number' ? c.d1_mm.toFixed(2) : '--')
                    + (typeof c.d2_mm === 'number' ? ' → ' + c.d2_mm.toFixed(2) : '');
                var zTxt = (typeof c.z0_mm === 'number' ? c.z0_mm.toFixed(1) : '--')
                    + ' … ' + (typeof c.z1_mm === 'number' ? c.z1_mm.toFixed(1) : '--');
                return '<tr class="si-cand-row" data-z0="' + c.z0_mm + '" data-z1="'
                    + c.z1_mm + '" style="cursor:default;">'
                    + '<td style="' + td + '">#' + i + '</td>'
                    + '<td style="' + td + '">' + escapeHtml(c.kind || '?') + '</td>'
                    + '<td style="' + td + '">' + escapeHtml(c.surface || '?') + '</td>'
                    + '<td style="' + td + '">' + dTxt + '</td>'
                    + '<td style="' + td + '">' + zTxt + '</td></tr>';
            }).join('');
            var th = 'text-align:left; padding:5px 8px; font-family:'
                + 'var(--hd-mono, monospace); font-size:0.7rem; letter-spacing:0.06em;'
                + ' color:var(--hd-ink-dim, #7d97a5); text-transform:uppercase;';
            html += '<div style="overflow-x:auto;"><table style="width:100%;'
                + ' border-collapse:collapse; font-size:0.82rem;">'
                + '<thead><tr>'
                + '<th style="' + th + '">#</th>'
                + '<th style="' + th + '">' + escapeHtml(T('stepimp.colKind', 'Type')) + '</th>'
                + '<th style="' + th + '">' + escapeHtml(T('stepimp.colSurface', 'Side')) + '</th>'
                + '<th style="' + th + '">' + escapeHtml(T('stepimp.colDiameter', 'Diameter (mm)')) + '</th>'
                + '<th style="' + th + '">' + escapeHtml(T('stepimp.colZ', 'z range (mm)')) + '</th>'
                + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
            html += '<div style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);'
                + ' margin:4px 0;">'
                + escapeHtml(T('stepimp.hoverHint',
                    'Hover a row to highlight its span on the cross-section.'))
                + '</div>';
        } else {
            html += '<div style="font-size:0.82rem; color:var(--hd-ink-dim, #7d97a5);">'
                + escapeHtml(T('stepimp.noCandidates',
                    'No cylindrical or conical surfaces were recognized in this solid.'))
                + '</div>';
        }

        // (c) Öneri eşleme formu
        html += sectionTitle(T('stepimp.suggestions', 'Suggested dimensions'));
        html += '<div style="font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);'
            + ' margin-bottom:8px;">'
            + escapeHtml(T('stepimp.suggestionsIntro',
                'Review each value before applying. Fields the analysis could not '
                + 'find stay empty — nothing is ever guessed. Clear a field to skip it.'))
            + '</div>';
        var pageMap = PAGE_MAPS[motorType] || { fields: {}, expansionField: null };
        var sugg = data.suggestions || {};
        html += '<div style="display:grid;'
            + ' grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px;">';
        SUGGESTION_KEYS.forEach(function (entry) {
            var key = entry[0];
            var label = T(entry[1], entry[2]);
            var s = sugg[key];
            var targetId = pageMap.fields[key] || null;
            var hasTarget = !!(targetId && document.getElementById(targetId));
            var usableForEps = (!hasTarget && pageMap.expansionField
                && (key === 'throat_diameter_mm' || key === 'exit_diameter_mm'));
            var conf = s ? String(s.confidence || 'low') : null;
            var confColor = CONF_COLORS[conf] || 'var(--hd-ink-dim, #7d97a5)';
            html += '<div style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));'
                + ' border-radius:8px; padding:10px 12px;">'
                + '<div style="font-size:0.78rem; margin-bottom:4px;">'
                + escapeHtml(label) + '</div>'
                + '<input type="number" step="0.01" class="si-sugg" data-key="' + key + '"'
                + ' value="' + (s && typeof s.value === 'number' ? s.value : '') + '"'
                + ((hasTarget || usableForEps) ? '' : ' disabled')
                + ' style="width:100%; box-sizing:border-box; padding:6px 8px;'
                + ' background:var(--hd-inset, rgba(6,14,26,0.85));'
                + ' color:var(--hd-ink, #cfe8f2); border:1px solid'
                + ' var(--hd-line, rgba(0,229,255,0.14)); border-radius:6px;">'
                + '<div style="display:flex; gap:8px; margin-top:5px; flex-wrap:wrap;'
                + ' font-family:var(--hd-mono, monospace); font-size:0.68rem;">'
                + (s
                    ? '<span style="border:1px solid ' + confColor + '; color:' + confColor
                        + '; border-radius:5px; padding:1px 7px; text-transform:uppercase;">'
                        + escapeHtml(conf) + '</span>'
                        + (typeof s.candidate_index === 'number'
                            ? '<span style="color:var(--hd-ink-dim, #7d97a5);">'
                                + escapeHtml(TF('stepimp.candidateRef',
                                    { i: s.candidate_index }, 'candidate #{i}')) + '</span>'
                            : '')
                    : '<span style="color:var(--hd-ink-dim, #7d97a5);">'
                        + escapeHtml(T('stepimp.notFound', 'not found')) + '</span>')
                + ((hasTarget || usableForEps)
                    ? ''
                    : '<span style="color:var(--hd-ink-faint, #46606d);">'
                        + escapeHtml(T('stepimp.noTargetShort', 'no form field on this page'))
                        + '</span>')
                + '</div></div>';
        });
        html += '</div>';

        // (d) Apply
        html += '<div style="display:flex; gap:10px; justify-content:flex-end;'
            + ' margin-top:16px;">'
            + '<button type="button" id="si_apply" class="btn" style="padding:9px 18px;">'
            + escapeHtml(T('stepimp.btnApply', 'Apply to form')) + '</button></div>';

        body.innerHTML = html;

        drawProfile(data);

        // Aday satırı hover vurgusu
        var candRows = body.querySelectorAll('.si-cand-row');
        for (var i = 0; i < candRows.length; i++) {
            (function (tr) {
                tr.addEventListener('mouseenter', function () {
                    highlightSpan(parseFloat(tr.getAttribute('data-z0')),
                                  parseFloat(tr.getAttribute('data-z1')));
                    tr.style.background = 'rgba(0, 229, 255, 0.07)';
                });
                tr.addEventListener('mouseleave', function () {
                    highlightSpan(null, null);
                    tr.style.background = '';
                });
            })(candRows[i]);
        }

        // Katı seçimi — dosya saklandı, solid_index ile yeniden POST
        var solidSel = document.getElementById('si_solid_select');
        if (solidSel) {
            solidSel.addEventListener('change', function () {
                analyze(lastFile, parseInt(solidSel.value, 10));
            });
        }

        var applyBtn = document.getElementById('si_apply');
        if (applyBtn) applyBtn.addEventListener('click', applyToForm);

        if (window.I18N && window.I18N.applyTo) {
            window.I18N.applyTo(document.getElementById('stepImportModal'));
        }
    }

    // ------------------------------------------------------------------
    // Kesit çizimi (profile_2d) — z yatay, r dikey; alt yarı aynalı
    // ------------------------------------------------------------------
    function drawProfile(data) {
        plotEl = document.getElementById('si_profile_plot');
        if (!plotEl) return;
        if (typeof Plotly === 'undefined') {
            plotEl.textContent = T('common.plotlyMissing',
                'Plotly is not loaded — chart skipped.');
            return;
        }
        var profile = data.profile_2d || {};
        var traces = [];
        function polylineTraces(pts, labelText, color) {
            if (!Array.isArray(pts) || pts.length < 2) return;
            var z = pts.map(function (p) { return p[0]; });
            var r = pts.map(function (p) { return p[1]; });
            var rNeg = r.map(function (v) { return -v; });
            traces.push({ x: z, y: r, mode: 'lines', name: labelText,
                          line: { width: 2, color: color } });
            traces.push({ x: z, y: rNeg, mode: 'lines', showlegend: false,
                          hoverinfo: 'skip', name: labelText,
                          line: { width: 2, color: color } });
        }
        // Plotly CSS değişkeni çözemez — tema paletinin somut renkleri
        polylineTraces(profile.outer, T('stepimp.outer', 'Outer contour'), '#00e5ff');
        polylineTraces(profile.inner, T('stepimp.inner', 'Inner contour'), '#ff8c33');
        if (!traces.length) {
            plotEl.textContent = T('stepimp.noProfile',
                'No cross-section profile was returned for this solid.');
            return;
        }
        Plotly.newPlot(plotEl, traces, {
            xaxis: { title: 'z (mm)' },
            yaxis: { title: 'r (mm)', scaleanchor: 'x', scaleratio: 1 },
            margin: { t: 24, r: 16 },
            height: 320,
            legend: { orientation: 'h', y: 1.1 },
        }, { responsive: true, displaylogo: false });
        if (window.HRMA_CAPTIONS && window.HRMA_CAPTIONS.attach) {
            window.HRMA_CAPTIONS.attach(plotEl, 'chartCap.stepProfile',
                'What this shows: the meridian cross-section reconstructed from the '
                + 'STEP solid — outer and inner contours mirrored about the motor axis. '
                + 'How to read it: z runs along the axis, r is the radius; hover a row '
                + 'in the surface table to highlight its axial span.');
        }
    }

    function highlightSpan(z0, z1) {
        if (!plotEl || typeof Plotly === 'undefined') return;
        var shapes = [];
        if (isFinite(z0) && isFinite(z1)) {
            shapes.push({
                type: 'rect', xref: 'x', yref: 'paper',
                x0: z0, x1: z1, y0: 0, y1: 1,
                fillcolor: 'rgba(0,229,255,0.10)', line: { width: 0 },
            });
        }
        try { Plotly.relayout(plotEl, { shapes: shapes }); }
        catch (e) { /* grafik henüz kurulmadıysa sessiz */ }
    }

    // ------------------------------------------------------------------
    // (d) Apply to form — onaylı değerler sayfa alanlarına
    // ------------------------------------------------------------------
    function dispatchFieldEvents(el) {
        try {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) { /* sessiz */ }
    }

    function applyToForm() {
        var pageMap = PAGE_MAPS[motorType] || { fields: {}, expansionField: null };
        var inputs = document.querySelectorAll('#stepImportModal .si-sugg');
        var values = {};
        for (var i = 0; i < inputs.length; i++) {
            var v = parseFloat(inputs[i].value);
            if (isFinite(v) && v > 0) values[inputs[i].getAttribute('data-key')] = v;
        }
        var applied = 0;
        Object.keys(values).forEach(function (key) {
            var targetId = pageMap.fields[key];
            if (!targetId) return;
            var el = document.getElementById(targetId);
            if (!el) return;
            el.value = values[key];
            dispatchFieldEvents(el);
            applied += 1;
        });
        // Throat + exit çapından genişleme oranı (sayfada alan varsa)
        if (pageMap.expansionField && values.throat_diameter_mm
            && values.exit_diameter_mm) {
            var epsEl = document.getElementById(pageMap.expansionField);
            if (epsEl) {
                var eps = Math.pow(values.exit_diameter_mm / values.throat_diameter_mm, 2);
                epsEl.value = eps.toFixed(2);
                dispatchFieldEvents(epsEl);
                applied += 1;
                toast(TF('stepimp.expansion', { er: eps.toFixed(2) },
                    'Expansion ratio {er} computed from throat and exit diameters.'),
                    'info');
            }
        }
        if (!applied) {
            toast(T('stepimp.nothingApplied',
                'No values to apply — fill or confirm at least one field.'), 'warn');
            return;
        }
        var fname = lastData && lastData.filename
            ? lastData.filename : (lastFile ? lastFile.name : 'STEP');
        if (window.HRMAProjectBar && window.HRMAProjectBar.setSource) {
            window.HRMAProjectBar.setSource('STEP import (' + fname + ')');
        }
        toast(TF('stepimp.applied', { n: applied },
            '{n} field(s) applied to the form (source: STEP import).'), 'ok');
        closeModal();
    }

    // ------------------------------------------------------------------
    // Giriş noktası — proje şeridindeki düğme çağırır
    // ------------------------------------------------------------------
    function open() {
        if (!motorType) return;
        var picker = document.createElement('input');
        picker.type = 'file';
        picker.accept = '.step,.stp';
        picker.style.display = 'none';
        picker.addEventListener('change', function () {
            var file = picker.files && picker.files[0];
            if (file) analyze(file, null);
            picker.remove();
        });
        document.body.appendChild(picker);
        picker.click();
    }

    window.StepImportUI = {
        open: open,
        // Test / hata ayıklama kancaları
        _analyze: analyze,
        _applyToForm: applyToForm,
        _pageMaps: PAGE_MAPS,
    };
})();
