/* ====================================================================
   HRMA 6-DOF Flight Dynamics Panel (advanced + solid + liquid — TEK kaynak)
   --------------------------------------------------------------------
   /api/six-dof-analysis'i UI'a bağlar: Barrowman stabilite (CN_α, CP,
   statik marj), weathercock, apoje ve uçuş serileri.

   v2.5.2 eklentileri (OpenRocket benzeri):
     - Mass & Balance bileşen tablosu (Simple / Component modu; Component
       modunda dry/propellant kütleleri ve x_cg_full/x_cg_empty tablodan
       türetilir, localStorage modu hatırlar)
     - Yeni girdi alanları: nose_type, fin_count, fin_position,
       launch_azimuth_deg (backend zaten kabul ediyor)
     - Canlı SVG roket şeması: burun profili (ogive/koni/parabol), gövde,
       kanat trapezi, motor bölgesi, CG-full/CG-empty/CP işaretleri ve
       kalibre cinsinden statik marj bandı. CP istemci tarafında Barrowman
       ile hesaplanır (six_dof_trajectory.py::BarrowmanAero birebir aynası)
       ve Run sonrası backend x_cp ile karşılaştırılır (console.warn).
     - Girdi doğrulama: boş/geçersiz/işaret-dışı alan kırmızı vurgulanır,
       panelde İngilizce hata satırı gösterilir ve Run engellenir.

   Kullanım:
     <script src="/static/js/sixdof_panel.js"></script>
     SixDofPanel.init({
         anchorId: '...',            // panelin ÖNÜNE ekleneceği element (ops.)
         thrustProvider: function () {
             // Sayfaya göre itki kaynağı döndürür:
             //   {thrust_curve: {time:[], thrust:[]}}  → gerçek eğri
             //   {thrust: N, burn_time: s}             → sabit itki
             //   null                                  → panel formundaki değerler
         },
         defaults: { dry_mass: 8, propellant_mass: 4 }   // ops.
     });
   ==================================================================== */

(function () {
    'use strict';

    let cfg = {};
    let lastRender = null;          // dil değişiminde yeniden çizmek için

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
    let massMode = 'simple';            // 'simple' | 'component'

    const MODE_KEY = 'hrma.sixdof.massMode';   // localStorage anahtarı

    // v2.5.5 içe aktarma durumu: .eng/.rse itki eğrisi + .ork kayıtları
    let importedMotors = [];            // /api/import/motor-file MOTOR listesi
    let importedIdx = 0;                // seçili motor
    let orkSavedSims = null;            // .ork saved_simulations (Run sonrası kart)
    let orkFileName = null;

    // Tema renkleri (CSS değişkeni + koyu tema yedeği) — badge'lerle aynı set
    const COLORS = {
        red: 'var(--hd-red, #ff5d73)',
        green: 'var(--hd-green, #2dd4a8)',
        yellow: 'var(--hd-yellow, #ffd166)',
        orange: 'var(--hd-orange, #ff8c33)',
        cyan: 'var(--hd-cyan, #00e5ff)',
        blue: 'var(--hd-blue, var(--hd-cyan, #00e5ff))',
        dim: 'var(--hd-ink-dim, #8899aa)',
    };

    // six_dof_trajectory.py ile paylaşılan sabitler (tek yerde tanım):
    // CG fallback kesirleri SixDOFTrajectory.__init__ (0.55·L / 0.50·L),
    // burun CP faktörleri BarrowmanAero ile birebir aynı olmalı.
    const CG_FULL_FRACTION = 0.55;
    const CG_EMPTY_FRACTION = 0.50;
    const NOSE_XCP_FACTOR = { conical: 2.0 / 3.0, ogive: 0.466, parabolic: 0.5 };
    const CP_MATCH_TOL_M = 1e-4;        // istemci↔backend CP tutarlılık eşiği [m]
    const CNA_MATCH_TOL = 1e-3;         // CN_α tutarlılık eşiği [1/rad]
    const MOTOR_ZONE_FRACTION = 0.2;    // şemada vurgulanan arka motor bölgesi

    // [id, label, default, step, rule]
    // rule: 'pos' (> 0 zorunlu), 'nonneg' (>= 0), 'any' (sonlu sayı yeter)
    const FIELDS = [
        { id: 'sd_body_d', key: 'sixdof.fBodyD', label: 'Body Diameter (m)', def: 0.10, step: 0.005, rule: 'pos' },
        { id: 'sd_body_l', key: 'sixdof.fBodyL', label: 'Total Length (m)', def: 2.0, step: 0.05, rule: 'pos' },
        { id: 'sd_nose_l', key: 'sixdof.fNoseL', label: 'Nose Length (m)', def: 0.40, step: 0.01, rule: 'pos' },
        { id: 'sd_nose_type', key: 'sixdof.fNoseType', label: 'Nose Type', def: 'ogive', type: 'select',
          options: [['ogive', 'Ogive', 'sixdof.noseOgive'], ['conical', 'Conical', 'sixdof.noseConical'],
                    ['parabolic', 'Parabolic', 'sixdof.noseParabolic']] },
        { id: 'sd_fin_count', key: 'sixdof.fFinCount', label: 'Fin Count', def: '4', type: 'select',
          options: [['3', '3'], ['4', '4']] },
        { id: 'sd_fin_root', key: 'sixdof.fFinRoot', label: 'Fin Root Chord (m)', def: 0.20, step: 0.005, rule: 'pos' },
        { id: 'sd_fin_tip', key: 'sixdof.fFinTip', label: 'Fin Tip Chord (m)', def: 0.10, step: 0.005, rule: 'nonneg' },
        { id: 'sd_fin_span', key: 'sixdof.fFinSpan', label: 'Fin Span (m)', def: 0.11, step: 0.005, rule: 'pos' },
        { id: 'sd_fin_sweep', key: 'sixdof.fFinSweep', label: 'Fin Sweep (m)', def: 0.08, step: 0.005, rule: 'nonneg' },
        { id: 'sd_fin_pos', key: 'sixdof.fFinPos', label: 'Fin Root LE from Nose (m)', def: 1.80, step: 0.01, rule: 'nonneg' },
        { id: 'sd_dry_m', key: 'sixdof.fDryMass', label: 'Dry Mass (kg)', def: 8.0, step: 0.1, rule: 'pos' },
        { id: 'sd_prop_m', key: 'common.f.propellantMassKg', label: 'Propellant Mass (kg)', def: 4.0, step: 0.1, rule: 'pos' },
        { id: 'sd_cd0', key: 'sixdof.fCd0', label: 'Cd₀ (subsonic)', def: 0.45, step: 0.01, rule: 'pos' },
        { id: 'sd_wind', key: 'sixdof.fWind', label: 'Wind Speed (m/s)', def: 5.0, step: 0.5, rule: 'nonneg' },
        { id: 'sd_wind_dir', key: 'sixdof.fWindDir', label: 'Wind From (° from N)', def: 0.0, step: 5, rule: 'any' },
        { id: 'sd_elev', key: 'sixdof.fElevation', label: 'Launch Elevation (°)', def: 90.0, step: 0.5, rule: 'pos' },
        { id: 'sd_azimuth', key: 'sixdof.fAzimuth', label: 'Launch Azimuth (° from N)', def: 0.0, step: 5, rule: 'any' },
        { id: 'sd_rail', key: 'sixdof.fRail', label: 'Rail Length (m)', def: 5.0, step: 0.5, rule: 'pos' },
        { id: 'sd_thrust', key: 'common.f.thrustN', label: 'Thrust (N)', def: 1200.0, step: 50, rule: 'pos' },
        { id: 'sd_burn', key: 'common.f.burnTimeS', label: 'Burn Time (s)', def: 6.0, step: 0.5, rule: 'pos' },
    ];

    // Component modu varsayılan satırları (2 m / 12 kg temsili araç;
    // toplamlar Simple mod varsayılanlarıyla tutarlı: dry 8 kg + prop 4 kg)
    function defaultComponents() {
        return [
            { name: T('sixdof.compNose', 'Nose cone'), mass: 0.5, x: 0.20, propellant: false },
            { name: T('sixdof.compBody', 'Body tube'), mass: 3.0, x: 1.20, propellant: false },
            { name: T('sixdof.compFins', 'Fins'), mass: 0.5, x: 1.90, propellant: false },
            { name: T('sixdof.compMotor', 'Motor (dry)'), mass: 4.0, x: 1.70, propellant: false },
            { name: T('sixdof.compProp', 'Oxidizer/Fuel'), mass: 4.0, x: 1.55, propellant: true },
        ];
    }

    // ------------------------------------------------------------------
    // Küçük yardımcılar
    // ------------------------------------------------------------------

    function $(id) { return document.getElementById(id); }

    function num(id) {
        // Sessiz 0 YOK: geçersiz girdi NaN döner, doğrulama katmanı yakalar.
        const el = $(id);
        return el ? parseFloat(el.value) : NaN;
    }

    function fmt(v, n) { return isFinite(v) ? v.toFixed(n) : '--'; }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                     '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    function markInvalid(el, bad) {
        if (!el) return;
        el.style.borderColor = bad ? COLORS.red : '';
        el.style.boxShadow = bad ? ('0 0 0 1px ' + COLORS.red) : '';
    }

    function badge(text, kind) {
        const colors = { ok: COLORS.green, warn: COLORS.orange,
                         err: COLORS.red, info: COLORS.cyan };
        const c = colors[kind] || colors.info;
        return `<span style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    // Statik marj renk bandı (NASA amatör roket pratiği; kalibre cinsinden)
    function marginBand(sm) {
        if (!isFinite(sm)) return { color: COLORS.red, label: T('sixdof.bandUnknown', 'CG/CP UNKNOWN') };
        if (sm < 1.0) return { color: COLORS.red, label: T('sixdof.bandUnstable', 'UNSTABLE / MARGINAL') };
        if (sm <= 2.0) return { color: COLORS.green, label: T('sixdof.bandStable', 'STABLE') };
        if (sm <= 3.0) {
            return { color: COLORS.yellow,
                     label: T('sixdof.bandSlightlyOver', 'STABLE (SLIGHTLY OVERSTABLE)') };
        }
        return { color: COLORS.orange, label: T('sixdof.bandOverstable', 'OVERSTABLE') };
    }

    // ------------------------------------------------------------------
    // İstemci tarafı Barrowman — six_dof_trajectory.py::BarrowmanAero'nun
    // birebir JS aynası (burun CN_α=2 + tip x_cp faktörü; kanat terimi +
    // gövde girişim çarpanı). Backend formülü değişirse Run sonrası CP
    // karşılaştırması console.warn ile tutarsızlığı bildirir.
    // ------------------------------------------------------------------

    function computeBarrowman(g) {
        const d = g.body_d;
        const cnNose = 2.0;
        const f = NOSE_XCP_FACTOR.hasOwnProperty(g.nose_type)
            ? NOSE_XCP_FACTOR[g.nose_type] : NOSE_XCP_FACTOR.ogive;
        const xcpNose = f * g.nose_l;

        let cnFins = 0.0, xcpFins = 0.0;
        if (g.fin_count && g.fin_span > 0 && g.fin_root > 0) {
            const n = g.fin_count, s = g.fin_span;
            const cr = g.fin_root, ct = g.fin_tip, m = g.fin_sweep;
            const xf = (isFinite(g.fin_position) && g.fin_position >= 0)
                ? g.fin_position : (g.body_l - cr);
            const lMid = Math.sqrt(s * s + Math.pow(m + (ct - cr) / 2.0, 2));
            cnFins = (4.0 * n * Math.pow(s / d, 2)) /
                (1.0 + Math.sqrt(1.0 + Math.pow(2.0 * lMid / (cr + ct), 2)));
            const rBody = d / 2.0;
            cnFins *= 1.0 + rBody / (s + rBody);
            const xcpRel = (m * (cr + 2.0 * ct)) / (3.0 * (cr + ct)) +
                (1.0 / 6.0) * (cr + ct - cr * ct / (cr + ct));
            xcpFins = xf + xcpRel;
        }
        const cnAlpha = cnNose + cnFins;
        return { cnAlpha: cnAlpha,
                 xCp: (cnNose * xcpNose + cnFins * xcpFins) / cnAlpha };
    }

    // ------------------------------------------------------------------
    // HTML kurulumları
    // ------------------------------------------------------------------

    function fieldHtml(f) {
        const lab = '<label' + (f.key ? ' data-i18n="' + f.key + '"' : '') + '>'
            + T(f.key, f.label) + '</label>';
        if (f.type === 'select') {
            const opts = f.options.map(function (o) {
                const sel = String(o[0]) === String(f.def) ? ' selected' : '';
                const attr = o[2] ? ' data-i18n="' + o[2] + '"' : '';
                return '<option value="' + o[0] + '"' + sel + attr + '>'
                    + T(o[2], o[1]) + '</option>';
            }).join('');
            return '<div class="form-group">' + lab +
                '<select id="' + f.id + '">' + opts + '</select></div>';
        }
        return '<div class="form-group">' + lab +
            '<input type="number" id="' + f.id + '" value="' + f.def +
            '" step="' + f.step + '"></div>';
    }

    function compRowHtml(c) {
        const cell = 'style="width:100%; box-sizing:border-box;"';
        // estimated:true (.ork geometri+yoğunluk tahmini) satırları görsel
        // işaret taşır ve düzenlenebilir kalır (uydurma-veri-yasağı: tahmin
        // olduğu kullanıcıya açıkça gösterilir)
        const estMark = c.estimated
            ? '<span title="' + escapeHtml(c.note || T('sixdof.orkEstimatedTip',
                    'Estimated from geometry and material density — edit as needed.'))
                + '" style="color:' + COLORS.orange + '; font-family:var(--hd-mono);'
                + ' font-size:0.7rem; margin-left:4px;">'
                + T('sixdof.est', 'est.') + '</span>'
            : '';
        return '<tr' + (c.estimated ? ' data-estimated="1"' : '') + '>' +
            '<td style="padding:2px 4px;' +
                (c.estimated ? ' border-left:2px solid ' + COLORS.orange + ';' : '') +
                '"><input type="text" class="sd-c-name" value="' +
                escapeHtml(c.name) + '" ' + cell + '>' + estMark + '</td>' +
            '<td style="padding:2px 4px;"><input type="number" class="sd-c-mass" value="' +
                c.mass + '" step="0.1" min="0" ' + cell + '></td>' +
            '<td style="padding:2px 4px;"><input type="number" class="sd-c-x" value="' +
                c.x + '" step="0.01" min="0" ' + cell + '></td>' +
            '<td style="padding:2px 4px; text-align:center;">' +
                '<input type="checkbox" class="sd-c-prop"' +
                (c.propellant ? ' checked' : '') + ' style="width:auto;"></td>' +
            '<td style="padding:2px 4px; text-align:center;">' +
                '<button type="button" class="btn sd-c-del" ' +
                'style="padding:2px 10px; font-size:0.75rem;" data-i18n="common.remove">'
                + T('common.remove', 'Remove') + '</button></td>' +
            '</tr>';
    }

    function massBalanceHtml() {
        return '' +
        '<div style="margin:14px 0; border:1px solid var(--hd-line, rgba(128,128,128,0.25)); ' +
                'border-radius:8px; padding:12px;">' +
            '<h3 style="margin:0 0 8px 0; font-size:0.95rem;" data-i18n="sixdof.massBalance">'
                + T('sixdof.massBalance', 'Mass & Balance') + '</h3>' +
            '<div style="display:flex; gap:18px; flex-wrap:wrap; margin-bottom:8px; font-size:0.85rem;">' +
                '<label style="display:flex; align-items:center; gap:6px; cursor:pointer;">' +
                    '<input type="radio" name="sd_mass_mode" value="simple" style="width:auto;">' +
                    '<span data-i18n="sixdof.simpleMode">'
                    + T('sixdof.simpleMode', 'Simple mode — enter total masses manually')
                    + '</span></label>' +
                '<label style="display:flex; align-items:center; gap:6px; cursor:pointer;">' +
                    '<input type="radio" name="sd_mass_mode" value="component" style="width:auto;">' +
                    '<span data-i18n="sixdof.componentMode">'
                    + T('sixdof.componentMode',
                        'Component mode — masses and CG derived from the table')
                    + '</span></label>' +
            '</div>' +
            '<div id="sd_comp_wrap" style="display:none;">' +
                '<div style="overflow-x:auto;">' +
                '<table id="sd_comp_table" style="width:100%; border-collapse:collapse; font-size:0.85rem;">' +
                    '<thead><tr>' +
                        '<th style="text-align:left; padding:4px 6px;" data-i18n="sixdof.colComponent">'
                            + T('sixdof.colComponent', 'Component') + '</th>' +
                        '<th style="text-align:left; padding:4px 6px;" data-i18n="sixdof.colMass">'
                            + T('sixdof.colMass', 'Mass (kg)') + '</th>' +
                        '<th style="text-align:left; padding:4px 6px;" data-i18n="sixdof.colPosition">'
                            + T('sixdof.colPosition', 'Position from nose tip (m)') + '</th>' +
                        '<th style="padding:4px 6px;" data-i18n="sixdof.colPropellant">'
                            + T('sixdof.colPropellant', 'Propellant') + '</th>' +
                        '<th style="padding:4px 6px;"></th>' +
                    '</tr></thead>' +
                    '<tbody id="sd_comp_body"></tbody>' +
                '</table></div>' +
                '<div style="margin-top:8px;">' +
                    '<button type="button" class="btn" id="sd_comp_add" ' +
                        'style="padding:4px 12px; font-size:0.8rem;" data-i18n="sixdof.addComponent">'
                        + T('sixdof.addComponent', 'Add Component') + '</button>' +
                '</div>' +
                '<div id="sd_comp_summary" style="font-family:var(--hd-mono); ' +
                    'font-size:0.78rem; color:' + COLORS.dim + '; margin-top:8px;"></div>' +
            '</div>' +
        '</div>';
    }

    // İtki kaynağı seçici + motor dosyası (.eng/.rse) + .ork içe aktarma
    // kutusu (v2.5.5 — backend: /api/import/motor-file, /api/import/ork)
    function importControlsHtml() {
        return `
            <div class="form-group" style="grid-column: 1 / -1;">
                <label data-i18n="sixdof.thrustSource">${T('sixdof.thrustSource',
                    'Thrust source')}</label>
                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <select id="sd_thrust_src" style="max-width:280px;">
                        <option value="auto" data-i18n="sixdof.srcAuto">${T('sixdof.srcAuto',
                            'Page result / form values (default)')}</option>
                        <option value="imported" data-i18n="sixdof.srcImported">${
                            T('sixdof.srcImported', 'Imported motor file (.eng/.rse)')}</option>
                    </select>
                    <input type="file" id="sd_motor_file" accept=".eng,.rse"
                        style="display:none; font-size:0.78rem; color:${COLORS.dim};">
                    <select id="sd_motor_select" style="display:none; max-width:220px;"></select>
                    <span id="sd_motor_status" style="font-family:var(--hd-mono);
                        font-size:0.72rem; color:${COLORS.dim};"></span>
                </div>
            </div>`;
    }

    function orkBoxHtml() {
        return `
        <div style="margin:14px 0; border:1px solid var(--hd-line, rgba(128,128,128,0.25));
                border-radius:8px; padding:12px;">
            <h3 style="margin:0 0 8px 0; font-size:0.95rem;" data-i18n="sixdof.orkTitle">${
                T('sixdof.orkTitle', 'OpenRocket Import (.ork)')}</h3>
            <div style="font-size:0.78rem; color:${COLORS.dim}; margin-bottom:8px;"
                data-i18n="sixdof.orkIntro">${T('sixdof.orkIntro',
                'Loads the rocket geometry into the aero fields (only values found in '
                + 'the file — missing ones are left untouched) and the component masses '
                + 'into the Mass & Balance table. Estimated rows are marked and editable.')}</div>
            <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <input type="file" id="sd_ork_file" accept=".ork,.xml"
                    style="font-size:0.78rem; color:${COLORS.dim};">
                <span id="sd_ork_status" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:${COLORS.dim};"></span>
            </div>
            <div id="sd_ork_report" style="margin-top:8px;"></div>
        </div>`;
    }

    function panelHtml(hasCurveSource) {
        const curveToggle = hasCurveSource ? `
            <div class="form-group" style="grid-column: 1 / -1;">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                    <input type="checkbox" id="sd_use_curve" checked style="width:auto;">
                    <span data-i18n="sixdof.useCurve">${T('sixdof.useCurve',
                        'Use computed thrust curve (transient / motor solution) '
                        + 'instead of constant thrust')}</span>
                </label>
            </div>` : '';
        return `
        <div class="panel" id="sixDofPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▶ <span data-i18n="sixdof.title">${T('sixdof.title',
                'Flight Dynamics — 6-DOF Stability')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="sixdof.intro">${T('sixdof.intro',
                    'Rigid-body flight with quaternion attitude, Barrowman-derived '
                    + 'CN_alpha/CP (nose + fins, body interference), launch-rail '
                    + 'constraint and wind-induced weathercocking. The vehicle diagram '
                    + 'below updates live: CG (full/empty), CP and the static margin '
                    + 'react to every input. Linear small-alpha aerodynamics '
                    + '(alpha < 15 deg) — use for stability screening, not tumbling flight.')}</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:10px; margin:12px 0;">
                ${FIELDS.map(fieldHtml).join('')}
                ${curveToggle}
                ${importControlsHtml()}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="sd_run" data-i18n="sixdof.btnRun">${
                        T('sixdof.btnRun', 'Run 6-DOF')}</button>
                </div>
            </div>
            ${orkBoxHtml()}
            ${massBalanceHtml()}
            <div style="font-family:var(--hd-mono); font-size:0.8rem; color:${COLORS.dim}; margin:4px 0;">
                <span data-i18n="sixdof.layoutNote">${T('sixdof.layoutNote',
                    'Vehicle layout — live CG / CP preview (Barrowman, client-side)')}</span>
            </div>
            <div id="sd_schematic" style="margin:6px 0;"></div>
            <div id="sd_margin" style="margin:6px 0; display:none;"></div>
            <div id="sd_errors" style="display:none; color:${COLORS.red};
                 font-family:var(--hd-mono); font-size:0.8rem; margin:8px 0;"></div>
            <div id="sd_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="sd_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="sd_ork_compare" style="display:none; margin:8px 0;"></div>
            <div id="sd_plot_alt" class="plot-container" style="min-height:400px; display:none;"></div>
            <div id="sd_plot_alpha" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="sd_plot_track" class="plot-container" style="min-height:380px; display:none;"></div>
            <div id="sd_plot_traj3d" class="plot-container" style="min-height:460px; display:none;"></div>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Bileşen tablosu (Mass & Balance)
    // ------------------------------------------------------------------

    function addComponentRow(c) {
        const tbody = $('sd_comp_body');
        if (tbody) tbody.insertAdjacentHTML('beforeend', compRowHtml(c));
    }

    function readComponents() {
        const rows = document.querySelectorAll('#sd_comp_body tr');
        const out = [];
        for (let i = 0; i < rows.length; i++) {
            const tr = rows[i];
            const nameEl = tr.querySelector('.sd-c-name');
            const massEl = tr.querySelector('.sd-c-mass');
            const xEl = tr.querySelector('.sd-c-x');
            const propEl = tr.querySelector('.sd-c-prop');
            if (!massEl || !xEl) continue;
            out.push({
                name: nameEl ? nameEl.value.trim() : '',
                mass: parseFloat(massEl.value),
                x: parseFloat(xEl.value),
                propellant: !!(propEl && propEl.checked),
                els: { mass: massEl, x: xEl },
            });
        }
        return out;
    }

    function deriveMassProps(comps) {
        // x_cg_full = Σm·x/Σm (tüm satırlar); x_cg_empty yakıt hariç
        let mAll = 0.0, mxAll = 0.0, mDry = 0.0, mxDry = 0.0, mProp = 0.0;
        comps.forEach(function (c) {
            if (!isFinite(c.mass) || c.mass <= 0 || !isFinite(c.x)) return;
            mAll += c.mass;
            mxAll += c.mass * c.x;
            if (c.propellant) {
                mProp += c.mass;
            } else {
                mDry += c.mass;
                mxDry += c.mass * c.x;
            }
        });
        return {
            dry: mDry, prop: mProp,
            cgFull: mAll > 0 ? mxAll / mAll : NaN,
            cgEmpty: mDry > 0 ? mxDry / mDry : NaN,
        };
    }

    // ------------------------------------------------------------------
    // Doğrulama — sessiz 0 yerine kırmızı vurgu + İngilizce hata satırı
    // ------------------------------------------------------------------

    function checkRule(v, rule) {
        if (!isFinite(v)) return T('sixdof.errNumber', 'must be a valid number');
        if (rule === 'pos' && v <= 0) return T('sixdof.errPositive', 'must be greater than 0');
        if (rule === 'nonneg' && v < 0) return T('sixdof.errNonNegative', 'must be 0 or greater');
        return null;
    }

    function validateAll(requireThrustForm) {
        const errors = [];
        FIELDS.forEach(function (f) {
            const el = $(f.id);
            if (!el || f.type === 'select') return;
            // Component modunda toplamlar tablodan türetilir (readonly)
            if (massMode === 'component' &&
                (f.id === 'sd_dry_m' || f.id === 'sd_prop_m')) {
                markInvalid(el, false);
                return;
            }
            // İtki eğrisi kullanılacaksa formdaki thrust/burn zorunlu değil
            if (!requireThrustForm && (f.id === 'sd_thrust' || f.id === 'sd_burn')) {
                markInvalid(el, false);
                return;
            }
            const msg = checkRule(parseFloat(el.value), f.rule || 'any');
            markInvalid(el, !!msg);
            if (msg) errors.push(T(f.key, f.label) + ': ' + msg + '.');
        });

        // Geometri tutarlılığı (çapraz alan kontrolleri) — bu ihlaller
        // Barrowman CP'sini anlamsız yapar, sessiz geçmemeli.
        const bodyL = parseFloat(($('sd_body_l') || {}).value);
        const noseL = parseFloat(($('sd_nose_l') || {}).value);
        const finPos = parseFloat(($('sd_fin_pos') || {}).value);
        const finRoot = parseFloat(($('sd_fin_root') || {}).value);
        if (isFinite(bodyL) && isFinite(noseL) && noseL >= bodyL) {
            markInvalid($('sd_nose_l'), true);
            errors.push(T('sixdof.errNoseTooLong',
                'Nose Length must be smaller than the total length.'));
        }
        if (isFinite(bodyL) && isFinite(finPos) && isFinite(finRoot) &&
            finPos + finRoot > bodyL + 1e-9) {
            markInvalid($('sd_fin_pos'), true);
            errors.push(T('sixdof.errFinBeyond',
                'Fin Root LE from Nose + Fin Root Chord must not exceed the total length.'));
        }

        if (massMode === 'component') {
            const comps = readComponents();
            if (!comps.length) {
                errors.push(T('sixdof.errNoComponents',
                    'Component table: at least one component row is required.'));
            }
            comps.forEach(function (c, i) {
                const label = T('sixdof.colComponent', 'Component') + ' ' + (i + 1) +
                    (c.name ? ' ("' + c.name + '")' : '');
                const mBad = !isFinite(c.mass) || c.mass <= 0;
                const xOutside = isFinite(bodyL) && isFinite(c.x) && c.x > bodyL + 1e-9;
                const xBad = !isFinite(c.x) || c.x < 0 || xOutside;
                markInvalid(c.els.mass, mBad);
                markInvalid(c.els.x, xBad);
                if (mBad) {
                    errors.push(label + ': ' + T('sixdof.errCompMass',
                        'mass must be a number greater than 0 kg.'));
                }
                if (!isFinite(c.x) || c.x < 0) {
                    errors.push(label + ': ' + T('sixdof.errCompPosition',
                        'position from nose tip must be 0 m or greater.'));
                } else if (xOutside) {
                    errors.push(label + ': ' + TF('sixdof.errCompBeyond', { len: bodyL },
                        'position from nose tip must not exceed the total length ({len} m).'));
                }
            });
            const mp = deriveMassProps(comps);
            if (comps.length && mp.dry <= 0) {
                errors.push(T('sixdof.errDryZero',
                    'Component table: total dry (non-propellant) mass must be greater than 0.'));
            }
            if (comps.length && mp.prop <= 0) {
                errors.push(T('sixdof.errPropZero',
                    'Component table: total propellant mass is 0 — mark at least one row as propellant.'));
            }
        }

        const errDiv = $('sd_errors');
        if (errDiv) {
            errDiv.innerHTML = errors.map(function (e) {
                return '<div>- ' + escapeHtml(e) + '</div>';
            }).join('');
            errDiv.style.display = errors.length ? 'block' : 'none';
        }
        return { ok: errors.length === 0, errors: errors };
    }

    // ------------------------------------------------------------------
    // Canlı şema (SVG yan görünüş) + statik marj bandı
    // ------------------------------------------------------------------

    function readGeometry() {
        return {
            body_d: num('sd_body_d'),
            body_l: num('sd_body_l'),
            nose_l: num('sd_nose_l'),
            nose_type: $('sd_nose_type') ? $('sd_nose_type').value : 'ogive',
            fin_count: $('sd_fin_count') ? parseInt($('sd_fin_count').value, 10) : 4,
            fin_root: num('sd_fin_root'),
            fin_tip: num('sd_fin_tip'),
            fin_span: num('sd_fin_span'),
            fin_sweep: num('sd_fin_sweep'),
            fin_position: num('sd_fin_pos'),
        };
    }

    function currentCg(derived, g) {
        if (massMode === 'component' && derived &&
            isFinite(derived.cgFull) && isFinite(derived.cgEmpty)) {
            return { full: derived.cgFull, empty: derived.cgEmpty, estimated: false };
        }
        // Simple mod: backend'in kaba CG tahminini aynala (0.55·L / 0.50·L)
        return { full: CG_FULL_FRACTION * g.body_l,
                 empty: CG_EMPTY_FRACTION * g.body_l, estimated: true };
    }

    function noseTopProfile(type, Ln, R) {
        // Üst profil örnek noktaları [x, y] — y: eksenden yarıçap
        const pts = [];
        const N = 16;
        for (let i = 0; i <= N; i++) {
            const x = Ln * i / N;
            let y;
            if (type === 'conical') {
                y = R * x / Ln;
            } else if (type === 'parabolic') {
                const xi = x / Ln;
                y = R * (2.0 * xi - xi * xi);          // K'=1 tam parabol
            } else {                                   // tangent ogive
                const rho = (R * R + Ln * Ln) / (2.0 * R);
                y = Math.sqrt(Math.max(rho * rho - (Ln - x) * (Ln - x), 0.0)) + R - rho;
            }
            pts.push([x, Math.max(y, 0.0)]);
        }
        return pts;
    }

    function drawSchematic(g, cg) {
        const host = $('sd_schematic');
        const band = $('sd_margin');
        if (!host || !band) return;
        const geomOk = isFinite(g.body_d) && g.body_d > 0 &&
            isFinite(g.body_l) && g.body_l > 0 &&
            isFinite(g.nose_l) && g.nose_l > 0 && g.nose_l < g.body_l;
        if (!geomOk) {
            host.innerHTML = '<div style="font-family:var(--hd-mono); font-size:0.8rem; ' +
                'color:' + COLORS.dim + ';">' + T('sixdof.errGeometry',
                'Enter a valid geometry (diameter, total length, nose length) '
                + 'to draw the vehicle.') + '</div>';
            band.innerHTML = '';
            band.style.display = 'none';
            return;
        }

        const bar = computeBarrowman(g);
        const L = g.body_l, R = g.body_d / 2.0;
        const finOk = isFinite(g.fin_span) && g.fin_span > 0 &&
            isFinite(g.fin_root) && g.fin_root > 0 &&
            isFinite(g.fin_tip) && g.fin_tip >= 0;
        const span = finOk ? g.fin_span : 0.0;

        const W = 1000, padX = 42, topPad = 24, labelZone = 26;
        const k = (W - 2 * padX) / L;
        const halfH = Math.max((R + span) * k, 26);
        const cy = topPad + halfH;
        const H = cy + halfH + labelZone;
        const X = function (x) { return padX + x * k; };

        const p = [];
        const bodyStyle = 'fill="currentColor" fill-opacity="0.07" ' +
            'stroke="currentColor" stroke-opacity="0.75" stroke-width="1.5"';

        // Eksen çizgisi
        p.push('<line x1="' + (X(0) - 14) + '" y1="' + cy + '" x2="' + (X(L) + 14) +
            '" y2="' + cy + '" stroke="currentColor" stroke-opacity="0.3" ' +
            'stroke-width="1" stroke-dasharray="6 5"/>');

        // Gövde
        p.push('<rect x="' + X(g.nose_l).toFixed(2) + '" y="' + (cy - R * k).toFixed(2) +
            '" width="' + ((L - g.nose_l) * k).toFixed(2) +
            '" height="' + (2 * R * k).toFixed(2) + '" ' + bodyStyle + '/>');

        // Motor bölgesi vurgusu (arka kısım)
        const xm = L * (1.0 - MOTOR_ZONE_FRACTION);
        p.push('<rect x="' + X(xm).toFixed(2) + '" y="' + (cy - R * k + 1).toFixed(2) +
            '" width="' + ((L - xm) * k).toFixed(2) +
            '" height="' + Math.max(2 * R * k - 2, 2).toFixed(2) +
            '" fill="' + COLORS.orange + '" fill-opacity="0.16"/>');
        p.push('<text x="' + X((xm + L) / 2).toFixed(2) + '" y="' + (cy + 3.5).toFixed(2) +
            '" text-anchor="middle" font-size="10" font-family="var(--hd-mono, monospace)" ' +
            'fill="' + COLORS.orange + '" fill-opacity="0.9">MOTOR</text>');

        // Burun (tipe göre profil)
        const prof = noseTopProfile(g.nose_type, g.nose_l, R);
        let dPath = 'M ' + X(0).toFixed(2) + ' ' + cy.toFixed(2);
        for (let i = 1; i < prof.length; i++) {
            dPath += ' L ' + X(prof[i][0]).toFixed(2) + ' ' +
                (cy - prof[i][1] * k).toFixed(2);
        }
        for (let i = prof.length - 1; i >= 1; i--) {
            dPath += ' L ' + X(prof[i][0]).toFixed(2) + ' ' +
                (cy + prof[i][1] * k).toFixed(2);
        }
        dPath += ' Z';
        p.push('<path d="' + dPath + '" ' + bodyStyle + '/>');

        // Kanat trapezleri (üst + alt yan görünüş)
        if (finOk) {
            const xf = (isFinite(g.fin_position) && g.fin_position >= 0)
                ? g.fin_position : (L - g.fin_root);
            const sweep = isFinite(g.fin_sweep) ? g.fin_sweep : 0.0;
            const finStyle = 'fill="currentColor" fill-opacity="0.13" ' +
                'stroke="currentColor" stroke-opacity="0.75" stroke-width="1.5"';
            const finPts = function (sign) {
                const yRoot = cy + sign * R * k;
                const yTip = cy + sign * (R + g.fin_span) * k;
                return [
                    X(xf).toFixed(2) + ',' + yRoot.toFixed(2),
                    X(xf + sweep).toFixed(2) + ',' + yTip.toFixed(2),
                    X(xf + sweep + g.fin_tip).toFixed(2) + ',' + yTip.toFixed(2),
                    X(xf + g.fin_root).toFixed(2) + ',' + yRoot.toFixed(2),
                ].join(' ');
            };
            p.push('<polygon points="' + finPts(-1) + '" ' + finStyle + '/>');
            p.push('<polygon points="' + finPts(1) + '" ' + finStyle + '/>');
        }

        // CG (dolu: dolu daire; boş: içi boş daire) ve CP (elmas)
        if (isFinite(cg.full)) {
            p.push('<circle cx="' + X(cg.full).toFixed(2) + '" cy="' + cy.toFixed(2) +
                '" r="7" fill="' + COLORS.blue + '"/>');
        }
        if (isFinite(cg.empty)) {
            p.push('<circle cx="' + X(cg.empty).toFixed(2) + '" cy="' + cy.toFixed(2) +
                '" r="7" fill="none" stroke="' + COLORS.blue + '" stroke-width="2"/>');
        }
        if (isFinite(bar.xCp)) {
            const cx = X(bar.xCp);
            p.push('<path d="M ' + cx.toFixed(2) + ' ' + (cy - 9).toFixed(2) +
                ' L ' + (cx + 7).toFixed(2) + ' ' + cy.toFixed(2) +
                ' L ' + cx.toFixed(2) + ' ' + (cy + 9).toFixed(2) +
                ' L ' + (cx - 7).toFixed(2) + ' ' + cy.toFixed(2) +
                ' Z" fill="' + COLORS.red + '"/>');
        }

        // Statik marj etiketi (kalibre) — şemanın sol üstünde
        const smFull = (bar.xCp - cg.full) / g.body_d;
        const smEmpty = (bar.xCp - cg.empty) / g.body_d;
        const bd = marginBand(Math.min(smFull, smEmpty));
        p.push('<text x="' + padX + '" y="14" font-size="12" ' +
            'font-family="var(--hd-mono, monospace)" fill="' + bd.color + '">' +
            'SM ' + fmt(smFull, 2) + ' / ' + fmt(smEmpty, 2) + ' cal &mdash; ' +
            bd.label + '</text>');

        host.innerHTML =
            '<svg viewBox="0 0 ' + W + ' ' + H.toFixed(0) + '" width="100%" ' +
            'style="display:block; max-height:260px;" role="img" ' +
            'aria-label="' + T('sixdof.diagramAria',
                'Rocket side view with CG and CP markers') + '">' +
            p.join('') + '</svg>' +
            '<div style="display:flex; flex-wrap:wrap; gap:14px; ' +
                'font-family:var(--hd-mono); font-size:0.75rem; margin-top:4px;">' +
            '<span style="color:' + COLORS.blue + ';">&#9679; '
                + T('sixdof.cgFull', 'CG full') + ' ' +
                fmt(cg.full, 3) + ' m' + (cg.estimated ? ' (' + T('sixdof.est', 'est.') + ')' : '') + '</span>' +
            '<span style="color:' + COLORS.blue + ';">&#9675; '
                + T('sixdof.cgEmpty', 'CG empty') + ' ' +
                fmt(cg.empty, 3) + ' m' + (cg.estimated ? ' (' + T('sixdof.est', 'est.') + ')' : '') + '</span>' +
            '<span style="color:' + COLORS.red + ';">&#9670; CP ' +
                fmt(bar.xCp, 3) + ' m</span>' +
            '<span style="color:' + COLORS.dim + ';">CN&#945; ' +
                fmt(bar.cnAlpha, 2) + ' /rad</span>' +
            '</div>';

        band.style.display = 'block';
        band.innerHTML =
            '<span style="border:1px solid ' + bd.color + '; color:' + bd.color +
            '; border-radius:6px; padding:4px 10px; font-family:var(--hd-mono); ' +
            'font-size:0.78rem; display:inline-block;">' +
            TF('sixdof.staticMargin', { full: fmt(smFull, 2), empty: fmt(smEmpty, 2) },
               'STATIC MARGIN {full} cal (full) / {empty} cal (empty)') + ' — ' + bd.label +
            (cg.estimated
                ? ' | ' + T('sixdof.cgEstimated',
                    'CG estimated (0.55 L / 0.50 L) — switch to Component mode '
                    + 'for a mass-based CG')
                : '') +
            '</span>';
    }

    function updateLive() {
        let derived = null;
        if (massMode === 'component') {
            const comps = readComponents();
            derived = deriveMassProps(comps);
            const dEl = $('sd_dry_m'), pEl = $('sd_prop_m');
            if (dEl && isFinite(derived.dry)) dEl.value = derived.dry.toFixed(3);
            if (pEl && isFinite(derived.prop)) pEl.value = derived.prop.toFixed(3);
            const sum = $('sd_comp_summary');
            if (sum) {
                sum.textContent = TF('sixdof.derivedSummary',
                    { dry: fmt(derived.dry, 3), prop: fmt(derived.prop, 3),
                      cgFull: fmt(derived.cgFull, 3), cgEmpty: fmt(derived.cgEmpty, 3) },
                    'Derived: dry {dry} kg | propellant {prop} kg | CG full {cgFull} m '
                    + '| CG empty {cgEmpty} m (from nose tip)');
            }
        }
        const useCurveEl = $('sd_use_curve');
        // İçe aktarılmış motor eğrisi seçili ve yüklüyse formdaki
        // thrust/burn alanları zorunlu değildir (eğri dosyadan gelir)
        const srcEl = $('sd_thrust_src');
        const importedReady = !!(srcEl && srcEl.value === 'imported'
            && importedMotors.length);
        const requireThrustForm = !importedReady &&
            !(cfg.thrustProvider && (!useCurveEl || useCurveEl.checked));
        validateAll(requireThrustForm);
        const g = readGeometry();
        drawSchematic(g, currentCg(derived, g));
    }

    // ------------------------------------------------------------------
    // Mod geçişi (Simple / Component) — localStorage ile hatırlanır
    // ------------------------------------------------------------------

    function setMode(mode, persist) {
        massMode = mode === 'component' ? 'component' : 'simple';
        const wrap = $('sd_comp_wrap');
        if (wrap) wrap.style.display = massMode === 'component' ? 'block' : 'none';
        ['sd_dry_m', 'sd_prop_m'].forEach(function (id) {
            const el = $(id);
            if (!el) return;
            el.readOnly = massMode === 'component';
            el.style.opacity = massMode === 'component' ? '0.65' : '';
        });
        const radios = document.querySelectorAll('input[name="sd_mass_mode"]');
        for (let i = 0; i < radios.length; i++) {
            radios[i].checked = radios[i].value === massMode;
        }
        if (persist) {
            try { localStorage.setItem(MODE_KEY, massMode); } catch (e) { /* gizli mod */ }
        }
        updateLive();
    }

    // ------------------------------------------------------------------
    // Çalıştırma
    // ------------------------------------------------------------------

    async function run() {
        const status = $('sd_status');
        const badges = $('sd_badges');
        const runBtn = $('sd_run');

        // İtki kaynağı önceliği: içe aktarılmış motor dosyası (seçiliyse) →
        // sayfa sağlayıcısı (transient/solid eğrisi) → form değerleri
        const srcEl = $('sd_thrust_src');
        const wantImported = !!(srcEl && srcEl.value === 'imported');
        let importedCurve = null;
        if (wantImported) {
            const im = importedMotors[importedIdx] || importedMotors[0];
            if (!im) {
                status.textContent = T('sixdof.noMotorLoaded',
                    'Choose a motor file (.eng/.rse) first.');
                return;
            }
            importedCurve = { time: im.time, thrust: im.thrust };
        }
        const useCurveEl = $('sd_use_curve');
        let provided = null;
        if (!importedCurve && cfg.thrustProvider
            && (!useCurveEl || useCurveEl.checked)) {
            try { provided = cfg.thrustProvider(); } catch (e) { provided = null; }
        }
        const hasCurve = !!(importedCurve || (provided && provided.thrust_curve &&
            provided.thrust_curve.time && provided.thrust_curve.time.length > 3));
        const hasConst = !!(!hasCurve && provided && provided.thrust && provided.burn_time);

        // Doğrulama: geçersiz girdiyle Run yok
        const check = validateAll(!hasCurve && !hasConst);
        if (!check.ok) {
            status.textContent = T('sixdof.fixInputs',
                'ERROR: fix the highlighted inputs before running.');
            return;
        }

        runBtn.disabled = true;
        badges.innerHTML = '';
        status.textContent = T('sixdof.integrating', 'INTEGRATING 6-DOF FLIGHT…');

        const g = readGeometry();
        const payload = {
            body_diameter: g.body_d,
            body_length: g.body_l,
            nose_length: g.nose_l,
            nose_type: g.nose_type,
            fin_count: g.fin_count,
            fin_root_chord: g.fin_root,
            fin_tip_chord: g.fin_tip,
            fin_span: g.fin_span,
            fin_sweep: g.fin_sweep,
            fin_position: g.fin_position,
            cd0: num('sd_cd0'),
            wind_speed: num('sd_wind'),
            wind_direction_deg: num('sd_wind_dir'),
            launch_elevation_deg: num('sd_elev'),
            launch_azimuth_deg: num('sd_azimuth'),
            rail_length: num('sd_rail'),
        };

        if (massMode === 'component') {
            // Tablo türetimi: toplamlar + CG'ler mevcut backend anahtarlarıyla
            const comps = readComponents();
            const mp = deriveMassProps(comps);
            payload.dry_mass = mp.dry;
            payload.propellant_mass = mp.prop;
            payload.x_cg_full = mp.cgFull;
            payload.x_cg_empty = mp.cgEmpty;
            // İleriye dönük: bileşen listesi (atalet modeli için; backend
            // şimdilik yoksayabilir — six_dof_trajectory.py destekliyor)
            payload.components = comps
                .filter(function (c) {
                    return isFinite(c.mass) && c.mass > 0 &&
                        isFinite(c.x) && c.x >= 0;
                })
                .map(function (c) {
                    return { mass: c.mass, x: c.x, propellant: c.propellant };
                });
        } else {
            payload.dry_mass = num('sd_dry_m');
            payload.propellant_mass = num('sd_prop_m');
        }

        if (importedCurve) {
            payload.thrust_curve = importedCurve;
        } else if (hasCurve) {
            payload.thrust_curve = provided.thrust_curve;
        } else if (hasConst) {
            payload.thrust = provided.thrust;
            payload.burn_time = provided.burn_time;
        } else {
            payload.thrust = num('sd_thrust');
            payload.burn_time = num('sd_burn');
        }

        try {
            const resp = await fetch('/api/six-dof-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            render(data, !!payload.thrust_curve);

            // İstemci Barrowman ↔ backend tutarlılık bekçisi
            const client = computeBarrowman(g);
            const s = data.summary;
            // H1-B10: `s.x_cp` / `s.cn_alpha` çözücü çöktüğünde null gelir
            // (ölçüldü: dry_mass=0 -> summary alanlarının hepsi null).
            // null ile aritmetik 0 gibi davranır, eşik aşılır ve
            // `null.toFixed(4)` TypeError atardı. Karşılaştırma yalnız İKİ
            // taraf da sayıysa yapılır.
            if (isFinite(client.xCp) && Number.isFinite(s.x_cp) &&
                Math.abs(client.xCp - s.x_cp) > CP_MATCH_TOL_M) {
                console.warn('SixDofPanel: client-side Barrowman CP (' +
                    client.xCp.toFixed(4) + ' m) does not match backend x_cp (' +
                    s.x_cp.toFixed(4) + ' m) — formulas out of sync?');
            }
            if (isFinite(client.cnAlpha) && Number.isFinite(s.cn_alpha) &&
                Math.abs(client.cnAlpha - s.cn_alpha) > CNA_MATCH_TOL) {
                console.warn('SixDofPanel: client-side CN_alpha (' +
                    client.cnAlpha.toFixed(3) + ') does not match backend (' +
                    s.cn_alpha.toFixed(3) + ') — formulas out of sync?');
            }
            status.textContent = '';
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            runBtn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Motor dosyası (.eng/.rse) itki kaynağı — /api/import/motor-file
    // ------------------------------------------------------------------

    function refreshImportControls() {
        const srcEl = $('sd_thrust_src');
        const fileEl = $('sd_motor_file');
        const selEl = $('sd_motor_select');
        if (!srcEl || !fileEl || !selEl) return;
        const imported = srcEl.value === 'imported';
        fileEl.style.display = imported ? 'inline-block' : 'none';
        selEl.style.display = (imported && importedMotors.length > 1)
            ? 'inline-block' : 'none';
        if (imported && importedMotors.length > 1 && !selEl.options.length) {
            fillMotorSelect();
        }
    }

    function fillMotorSelect() {
        const selEl = $('sd_motor_select');
        if (!selEl) return;
        selEl.innerHTML = importedMotors.map(function (m, i) {
            const name = (m.meta && m.meta.name) || ('#' + i);
            return '<option value="' + i + '"' + (i === importedIdx ? ' selected' : '')
                + '>' + escapeHtml(name) + '</option>';
        }).join('');
    }

    function setMotorStatus(text, colorVar) {
        const el = $('sd_motor_status');
        if (!el) return;
        el.textContent = text || '';
        el.style.color = colorVar || COLORS.dim;
    }

    // meta.prop_mass_kg önerisi: alan SESSİZCE ezilmez — doldurulur, turuncu
    // vurgulanır ve durum satırında açıkça bildirilir (kullanıcı onayına açık)
    function suggestPropMass(motor) {
        const meta = (motor && motor.meta) || {};
        if (typeof meta.prop_mass_kg !== 'number' || !isFinite(meta.prop_mass_kg)
            || meta.prop_mass_kg <= 0) return;
        const el = $('sd_prop_m');
        if (!el || massMode === 'component') return;   // tabloda türetiliyor
        el.value = meta.prop_mass_kg.toFixed(3);
        el.style.borderColor = COLORS.orange;
        el.style.boxShadow = '0 0 0 1px ' + COLORS.orange;
        el.title = TF('sixdof.propMassSuggested', { m: meta.prop_mass_kg.toFixed(3) },
            'Propellant mass filled from the motor file ({m} kg) — please review.');
        setMotorStatus(TF('sixdof.propMassSuggested', { m: meta.prop_mass_kg.toFixed(3) },
            'Propellant mass filled from the motor file ({m} kg) — please review.'),
            COLORS.orange);
        updateLive();
    }

    // İçe aktarılan motor listesini itki kaynağı olarak devreye al
    // (.eng/.rse dosya seçiminden ve .ork gömülü motorundan ortak kullanılır)
    function adoptImportedMotors(motors, sourceName) {
        importedMotors = motors || [];
        importedIdx = 0;
        const srcEl = $('sd_thrust_src');
        if (srcEl) srcEl.value = 'imported';
        fillMotorSelect();
        refreshImportControls();
        const m = importedMotors[0];
        if (m) {
            setMotorStatus(TF('sixdof.usingMotor',
                { name: (m.meta && m.meta.name) || sourceName || '?',
                  n: m.time.length },
                'Using imported motor: {name} ({n} points)'));
            suggestPropMass(m);
        }
        updateLive();
    }

    async function onMotorFileChosen(file) {
        if (!window.HRMAImportUI) return;
        setMotorStatus(T('sixdof.importingMotor', 'IMPORTING MOTOR FILE…'));
        try {
            const text = await window.HRMAImportUI.readFileAsText(file);
            const data = await window.HRMAImportUI.postMotorFile(text, file.name, null);
            adoptImportedMotors(data.motors || [], file.name);
        } catch (err) {
            console.error('SixDofPanel motor file import failed:', err);
            setMotorStatus(TF('sixdof.motorImportFailed', { message: err.message },
                'Motor file import failed: {message}'), COLORS.red);
            if (window.HRMAImportUI.toast) window.HRMAImportUI.toast(err.message, 'err');
        }
    }

    // ------------------------------------------------------------------
    // OpenRocket .ork içe aktarma — /api/import/ork
    // ------------------------------------------------------------------

    // 6-DOF sözleşme anahtarı -> panel alan id'si (metre; null'lara DOKUNULMAZ)
    const ORK_FIELD_MAP = {
        nose_length: 'sd_nose_l',
        body_diameter: 'sd_body_d',
        body_length: 'sd_body_l',
        fin_root_chord: 'sd_fin_root',
        fin_tip_chord: 'sd_fin_tip',
        fin_span: 'sd_fin_span',
        fin_sweep: 'sd_fin_sweep',
        fin_position: 'sd_fin_pos',
    };

    function setOrkStatus(text, colorVar) {
        const el = $('sd_ork_status');
        if (!el) return;
        el.textContent = text || '';
        el.style.color = colorVar || COLORS.dim;
    }

    function applyOrkAero(aero) {
        let applied = 0;
        const notes = [];
        Object.keys(ORK_FIELD_MAP).forEach(function (key) {
            const v = aero ? aero[key] : null;
            if (typeof v !== 'number' || !isFinite(v)) return;   // null → dokunma
            const el = $(ORK_FIELD_MAP[key]);
            if (!el) return;
            el.value = v;
            applied += 1;
        });
        if (aero && typeof aero.nose_type === 'string' && aero.nose_type) {
            const el = $('sd_nose_type');
            if (el && ['ogive', 'conical', 'parabolic'].indexOf(aero.nose_type) !== -1) {
                el.value = aero.nose_type;
                applied += 1;
            }
        }
        if (aero && typeof aero.fin_count === 'number' && isFinite(aero.fin_count)) {
            const el = $('sd_fin_count');
            if (el && ['3', '4'].indexOf(String(aero.fin_count)) !== -1) {
                el.value = String(aero.fin_count);
                applied += 1;
            } else {
                notes.push(TF('sixdof.finCountSkipped', { n: aero.fin_count },
                    'Fin count {n} is not supported by this panel (3 or 4) — '
                    + 'field left unchanged.'));
            }
        }
        return { applied: applied, notes: notes };
    }

    function applyOrkComponents(components) {
        if (!Array.isArray(components) || !components.length) return 0;
        const tbody = $('sd_comp_body');
        if (!tbody) return 0;
        setMode('component', true);
        tbody.innerHTML = '';
        components.forEach(function (c) {
            addComponentRow({
                name: c.name || T('sixdof.colComponent', 'Component'),
                mass: (typeof c.mass_kg === 'number' && isFinite(c.mass_kg))
                    ? c.mass_kg : 0,
                x: (typeof c.x_m === 'number' && isFinite(c.x_m)) ? c.x_m : 0,
                propellant: !!c.propellant,
                estimated: !!c.estimated,
                note: c.note,
            });
        });
        updateLive();
        return components.length;
    }

    function orkListHtml(titleText, items) {
        if (!Array.isArray(items) || !items.length) return '';
        return '<div style="margin:4px 0;"><strong style="font-size:0.75rem;">'
            + escapeHtml(titleText) + '</strong><ul style="margin:2px 0 0 18px;'
            + ' font-size:0.72rem; color:' + COLORS.dim + ';">'
            + items.map(function (x) { return '<li>' + escapeHtml(x) + '</li>'; }).join('')
            + '</ul></div>';
    }

    function renderOrkReport(data, aeroResult, nComponents) {
        const box = $('sd_ork_report');
        if (!box) return;
        let html = '';
        // Uyarılar görünür olmalı (sözleşme: estimated/approximated kullanıcıya)
        if (Array.isArray(data.warnings) && data.warnings.length) {
            html += '<div style="border:1px solid ' + COLORS.orange + ';'
                + ' border-radius:8px; padding:8px 12px; margin:6px 0;'
                + ' color:' + COLORS.orange + '; font-size:0.75rem;">'
                + '<strong>' + escapeHtml(T('sixdof.orkWarnings',
                    'OpenRocket import warnings')) + '</strong>'
                + '<ul style="margin:4px 0 0 18px;">'
                + data.warnings.map(function (w) {
                    return '<li>' + escapeHtml(w) + '</li>';
                }).join('') + '</ul></div>';
        }
        (aeroResult.notes || []).forEach(function (n) {
            html += '<div style="font-size:0.72rem; color:' + COLORS.orange + ';">'
                + escapeHtml(n) + '</div>';
        });
        html += '<div style="font-family:var(--hd-mono); font-size:0.72rem;'
            + ' color:' + COLORS.dim + '; margin:4px 0;">'
            + escapeHtml(TF('sixdof.orkApplied', { n: aeroResult.applied },
                'Applied {n} aero field(s) from the .ork file.'))
            + (nComponents
                ? ' ' + escapeHtml(TF('sixdof.componentsLoaded', { n: nComponents },
                    '{n} component(s) loaded into the Mass & Balance table.'))
                : '')
            + '</div>';
        // mapping_report: katlanabilir özet kutusu
        const mr = data.mapping_report || {};
        html += '<details style="margin:6px 0; font-size:0.75rem;">'
            + '<summary style="cursor:pointer; color:' + COLORS.cyan + ';'
            + ' font-family:var(--hd-mono);">'
            + escapeHtml(T('sixdof.mappingReport', 'Mapping report')) + '</summary>'
            + orkListHtml(T('sixdof.mrMapped', 'Mapped'), mr.mapped)
            + orkListHtml(T('sixdof.mrApproximated', 'Approximated'), mr.approximated)
            + orkListHtml(T('sixdof.mrSkipped', 'Skipped'), mr.skipped)
            + '</details>';
        // Gömülü motor: Görev 2 mekanizmasını yeniden kullan
        if (Array.isArray(data.embedded_motors) && data.embedded_motors.length) {
            html += '<button type="button" class="btn" id="sd_ork_use_motor"'
                + ' style="padding:4px 12px; font-size:0.75rem;">'
                + escapeHtml(T('sixdof.useEmbeddedMotor',
                    'Use the motor embedded in the .ork file as thrust source'))
                + '</button>';
        }
        box.innerHTML = html;
        const useBtn = $('sd_ork_use_motor');
        if (useBtn) {
            useBtn.addEventListener('click', function () {
                adoptImportedMotors(data.embedded_motors, orkFileName);
            });
        }
    }

    async function onOrkFileChosen(file) {
        if (!window.HRMAImportUI) return;
        setOrkStatus(T('sixdof.orkImporting', 'IMPORTING .ORK FILE…'));
        try {
            const data = await window.HRMAImportUI.postOrk(file);
            orkFileName = file.name;
            const aeroResult = applyOrkAero(data.aero || {});
            const nComponents = applyOrkComponents(data.components);
            orkSavedSims = (Array.isArray(data.saved_simulations)
                && data.saved_simulations.length) ? data.saved_simulations : null;
            renderOrkReport(data, aeroResult, nComponents);
            setOrkStatus('');
            const cmp = $('sd_ork_compare');
            if (cmp) { cmp.style.display = 'none'; cmp.innerHTML = ''; }
            updateLive();
        } catch (err) {
            console.error('SixDofPanel .ork import failed:', err);
            setOrkStatus(TF('sixdof.orkImportFailed', { message: err.message },
                'OpenRocket import failed: {message}'), COLORS.red);
            if (window.HRMAImportUI.toast) window.HRMAImportUI.toast(err.message, 'err');
        }
    }

    // Run SONRASI: OpenRocket kayıtlı simülasyonu vs HRMA 6-DOF kartı —
    // yalnız iki tarafta da olan alanlar karşılaştırılır (fark %)
    function renderOrkComparison(summary) {
        const box = $('sd_ork_compare');
        if (!box) return;
        if (!orkSavedSims || !orkSavedSims.length || !summary) {
            box.style.display = 'none';
            box.innerHTML = '';
            return;
        }
        const sim = orkSavedSims[0];
        const rows = [];
        function addRow(labelText, orVal, hrmaVal, digits, unit) {
            if (typeof orVal !== 'number' || !isFinite(orVal)) return;
            if (typeof hrmaVal !== 'number' || !isFinite(hrmaVal)) return;
            const diff = orVal !== 0 ? (hrmaVal - orVal) / Math.abs(orVal) * 100 : NaN;
            rows.push([labelText,
                orVal.toFixed(digits) + ' ' + unit,
                hrmaVal.toFixed(digits) + ' ' + unit,
                isFinite(diff) ? ((diff >= 0 ? '+' : '') + diff.toFixed(1) + '%') : '--']);
        }
        addRow(T('sixdof.cmpApogee', 'Apogee'), sim.apogee_m, summary.apogee, 0, 'm');
        addRow(T('sixdof.cmpMaxVelocity', 'Max velocity'), sim.max_velocity_ms,
               summary.max_speed, 1, 'm/s');
        addRow(T('sixdof.cmpMaxMach', 'Max Mach'), sim.max_mach, summary.max_mach, 2, '');
        addRow(T('sixdof.cmpTimeToApogee', 'Time to apogee'), sim.time_to_apogee_s,
               summary.apogee_time, 1, 's');
        if (!rows.length) {
            box.style.display = 'none';
            box.innerHTML = '';
            return;
        }
        const td = 'padding:4px 10px; border-bottom:1px solid'
            + ' var(--hd-line, rgba(0,229,255,0.14)); font-size:0.8rem;';
        box.style.display = 'block';
        box.innerHTML =
            '<div style="border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));'
            + ' border-radius:8px; padding:10px 14px;">'
            + '<div style="font-family:var(--hd-mono); font-size:0.75rem;'
            + ' color:' + COLORS.cyan + '; margin-bottom:4px;">'
            + escapeHtml(T('sixdof.orkCompareTitle',
                'OpenRocket saved simulation vs HRMA 6-DOF'))
            + (sim.name ? ' — ' + escapeHtml(sim.name) : '') + '</div>'
            + '<table style="border-collapse:collapse;">'
            + '<tr>'
            + '<th style="' + td + ' text-align:left;"></th>'
            + '<th style="' + td + ' text-align:left;">OpenRocket</th>'
            + '<th style="' + td + ' text-align:left;">HRMA</th>'
            + '<th style="' + td + ' text-align:left;">'
            + escapeHtml(T('sixdof.cmpDiff', 'Diff')) + '</th></tr>'
            + rows.map(function (r) {
                return '<tr><td style="' + td + '"><strong>' + escapeHtml(r[0])
                    + '</strong></td><td style="' + td + '">' + escapeHtml(r[1])
                    + '</td><td style="' + td + '">' + escapeHtml(r[2])
                    + '</td><td style="' + td + '">' + escapeHtml(r[3]) + '</td></tr>';
            }).join('')
            + '</table>'
            + '<div style="font-size:0.7rem; color:' + COLORS.dim + '; margin-top:4px;">'
            + escapeHtml(T('sixdof.orkCompareNote',
                'Only fields present on both sides are compared. OpenRocket values '
                + 'come from the simulation stored in the .ork file.')) + '</div>'
            + '</div>';
    }

    function render(data, usedCurve) {
        lastRender = { data: data, usedCurve: usedCurve };
        const s = data.summary;
        const ser = data.series;
        const badges = $('sd_badges');

        // ==============================================================
        // NULL ALAN KAPISI (Faz 5 / H1-B10)
        // --------------------------------------------------------------
        // Uç, ölçemediği büyüklüğü BİLEREK `null` yayımlıyor: çözücü
        // çöktüğünde ve zirveye varılmadan entegrasyon ufkuna dayanıldığında
        // (`end_reason = 'time_limit'`) apoje / apoje anı / kararlılık
        // hükmü null döner.
        // ÖLÇÜLDÜ (2026-08-03, POST /api/six-dof-analysis,
        // {dry_mass:20, propellant_mass:10, thrust:3000, burn_time:5, t_max:1}):
        //   HTTP 200, summary.apogee = null, apogee_time = null, stable = null
        // ESKİ KOD `s.apogee_time.toFixed(1)` çağırıyordu -> TypeError
        // ("Cannot read properties of null (reading 'toFixed')"); paneldeki
        // try/catch bunu yakalayıp durum satırına ham JS mesajını basıyordu.
        // Kullanıcı "entegrasyon zirveye varmadan bitti" yerine ayrıştırıcı
        // gürültüsü görüyordu. Ayrıca `s.stable` null iken `s.stable ? ... : ...`
        // dalı UYDURMA BİR HÜKÜM basıyordu: ölçülmemiş kararlılık "UNSTABLE"
        // diye gösteriliyordu.
        // Kural: sayı yoksa SAYI BASILMAZ; niçin olmadığı yazılır.
        // ==============================================================
        const numOf = (v) => (typeof v === 'number' && Number.isFinite(v)) ? v : null;
        const fx = (v, d) => { const n = numOf(v); return n === null ? null : n.toFixed(d); };

        let html;
        if (numOf(s.stable) === null && typeof s.stable !== 'boolean') {
            html = badge(T('sixdof.stabilityNotEvaluated',
                           'STABILITY NOT EVALUATED'), 'warn');
        } else {
            html = badge(s.stable ? T('sixdof.bandStable', 'STABLE')
                                  : T('sixdof.unstable', 'UNSTABLE'), s.stable ? 'ok' : 'err');
        }

        const apKm = fx(numOf(s.apogee) === null ? null : s.apogee / 1000, 2);
        const apT = fx(s.apogee_time, 1);
        if (apKm !== null && apT !== null) {
            html += badge(TF('sixdof.badgeApogee', { km: apKm, t: apT },
                             'APOGEE {km} km @ {t} s'), 'info');
        } else {
            html += badge(T('sixdof.apogeeNotReported',
                            'APOGEE NOT REPORTED — the integration ended before '
                            + 'a peak was found'), 'warn');
        }

        const mach = fx(s.max_mach, 2);
        if (mach !== null) {
            html += badge(TF('sixdof.badgeMaxMach', { m: mach }, 'MAX MACH {m}'), 'info');
        }
        const alpha = fx(s.max_alpha_deg, 1);
        if (alpha !== null) {
            html += badge(TF('sixdof.badgeMaxAlpha', { a: alpha }, 'MAX alpha {a} deg'),
                          s.max_alpha_deg < 10 ? 'ok' : 'warn');
        }
        // NASA amatör roket pratiği: hedef 1.5-2 kalibre; >3 aşırı-stabil
        // (rüzgâra dönme + irtifa kaybı) — 2026-07-15 GPT-5.6 çapraz kontrol önerisi
        const smFull = numOf(s.static_margin_full);
        const smEmpty = numOf(s.static_margin_empty);
        if (smFull !== null && smEmpty !== null) {
            const smMin = Math.min(smFull, smEmpty);
            const smMax = Math.max(smFull, smEmpty);
            const smKind = smMin <= 1 ? 'err' : (smMax > 3 ? 'warn' : 'ok');
            html += badge(TF('sixdof.badgeMargin',
                             { full: smFull.toFixed(2), empty: smEmpty.toFixed(2) },
                             'MARGIN {full} / {empty} cal')
                + (smMax > 3 ? ' — ' + T('sixdof.overStable', 'OVER-STABLE') : ''), smKind);
        }
        const cnAlpha = fx(s.cn_alpha, 2);
        const xCp = fx(s.x_cp, 3);
        if (cnAlpha !== null && xCp !== null) {
            html += badge(`CNα ${cnAlpha} · CP ${xCp} m`, 'info');
        }
        html += badge(T('sixdof.thrustBadge', 'THRUST') + ': '
            + (usedCurve ? T('sixdof.computedCurve', 'COMPUTED CURVE')
                         : T('sixdof.constantThrust', 'CONSTANT')), 'info');
        if (s.end_reason && s.end_reason !== 'apogee') {
            html += badge(T('transient.badgeEnd', 'END') + ': '
                + s.end_reason.toUpperCase(), 'warn');
        }
        badges.innerHTML = html;

        // .ork kayıtlı simülasyon karşılaştırma kartı (varsa)
        renderOrkComparison(s);

        const altDiv = $('sd_plot_alt');
        altDiv.style.display = 'block';
        Plotly.newPlot(altDiv, [
            { x: ser.time, y: ser.altitude, name: T('sixdof.sAltitude', 'Altitude [m]'),
              mode: 'lines', line: { width: 3 } },
            { x: ser.time, y: ser.mach, name: 'Mach', mode: 'lines', yaxis: 'y2',
              line: { width: 2, dash: 'dot' } },
        ], {
            title: T('sixdof.chartAlt', 'Altitude & Mach vs Time (launch to apogee)'),
            xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
            yaxis: { title: T('sixdof.sAltitude', 'Altitude [m]'), rangemode: 'tozero' },
            yaxis2: { title: 'Mach', overlaying: 'y', side: 'right', rangemode: 'tozero' },
            height: 400, legend: { orientation: 'h', y: 1.12 },
        }, { responsive: true, displaylogo: false });

        const alphaDiv = $('sd_plot_alpha');
        alphaDiv.style.display = 'block';
        Plotly.newPlot(alphaDiv, [
            { x: ser.time, y: ser.alpha_deg, name: 'α [deg]', mode: 'lines',
              line: { width: 2 } },
        ], {
            title: T('sixdof.chartAlpha', 'Angle of Attack (weathercock response)'),
            xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
            yaxis: { title: 'α [deg]', rangemode: 'tozero' },
            height: 340,
        }, { responsive: true, displaylogo: false });

        const trackDiv = $('sd_plot_track');
        trackDiv.style.display = 'block';
        Plotly.newPlot(trackDiv, [
            { x: ser.east, y: ser.north, mode: 'lines+markers',
              name: T('sixdof.sGroundTrack', 'Ground track'), marker: { size: 3 } },
            { x: [ser.east[0]], y: [ser.north[0]], mode: 'markers',
              name: T('sixdof.sLaunch', 'Launch'), marker: { size: 12, symbol: 'star' } },
        ], {
            title: T('sixdof.chartTrack',
                'Ground Track (North vs East) — drift into wind = weathercock'),
            xaxis: { title: T('sixdof.axisEast', 'East [m]') },
            yaxis: { title: T('sixdof.axisNorth', 'North [m]'), scaleanchor: 'x', scaleratio: 1 },
            height: 380,
        }, { responsive: true, displaylogo: false });

        // 3B yörünge (v2.5.5): doğu/kuzey/irtifa uzayında uçuş hattı, Mach
        // ile renklendirilir (colorbar); apoje işaretçisi + zemine kesikli
        // izdüşüm izi. Veri /api/six-dof-analysis serisinde zaten var;
        // scatter3d line colorbar'ı plotly.js 1.58.5'te destekli (trace
        // modülü colorbar tanımında {container:'line'} girdisi mevcut).
        // Koyu tema plotly_dark.js sarmalayıcısından otomatik gelir.
        const trajDiv = $('sd_plot_traj3d');
        if (trajDiv && ser.east && ser.north && ser.altitude &&
            ser.altitude.length > 1) {
            trajDiv.style.display = 'block';
            // Apoje: serideki en yüksek irtifa örneği
            let ia = 0;
            for (let i = 1; i < ser.altitude.length; i++) {
                if (ser.altitude[i] > ser.altitude[ia]) ia = i;
            }
            const groundZ = ser.altitude.map(function () { return 0; });
            Plotly.newPlot(trajDiv, [
                {
                    type: 'scatter3d', mode: 'lines',
                    x: ser.east, y: ser.north, z: ser.altitude,
                    name: T('sixdof.sTrajectory', 'Trajectory'),
                    line: {
                        width: 6,
                        color: ser.mach,
                        // Tema paletiyle hizalı sıralı skala (cyan → sarı → kırmızı)
                        colorscale: [[0, '#00e5ff'], [0.5, '#ffd166'], [1, '#ff5d73']],
                        showscale: true,
                        colorbar: { title: 'Mach', thickness: 14, len: 0.55 },
                    },
                },
                {
                    type: 'scatter3d', mode: 'lines',
                    x: ser.east, y: ser.north, z: groundZ,
                    name: T('sixdof.sGroundProj', 'Ground projection'),
                    line: { width: 3, color: 'rgba(136, 153, 170, 0.6)', dash: 'dash' },
                    hoverinfo: 'skip',
                },
                {
                    type: 'scatter3d', mode: 'markers+text',
                    x: [ser.east[ia]], y: [ser.north[ia]], z: [ser.altitude[ia]],
                    name: T('sixdof.sApogee', 'Apogee'),
                    marker: { size: 5, symbol: 'diamond', color: '#ffd166' },
                    text: [T('sixdof.sApogee', 'Apogee')],
                    textposition: 'top center',
                    textfont: { size: 11 },
                },
            ], {
                title: T('sixdof.chart3d',
                    '3D Trajectory (East / North / Altitude) — colored by Mach'),
                scene: {
                    xaxis: { title: T('sixdof.axisEast', 'East [m]') },
                    yaxis: { title: T('sixdof.axisNorth', 'North [m]') },
                    zaxis: { title: T('sixdof.sAltitude', 'Altitude [m]') },
                },
                height: 460,
                legend: { orientation: 'h', y: 1.02 },
            }, { responsive: true, displaylogo: false });
        }
    }

    // ------------------------------------------------------------------
    // Kurulum — init imzası SABİT: 3 sayfa (advanced/solid/liquid) aynı
    // seçeneklerle çağırıyor ({anchorId, thrustProvider, defaults})
    // ------------------------------------------------------------------

    function init(options) {
        cfg = options || {};
        const anchor = cfg.anchorId ? $(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = panelHtml(!!cfg.thrustProvider);
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(panel);
        }

        // Sayfa varsayılanları (kütle vb.)
        Object.entries(cfg.defaults || {}).forEach(([k, v]) => {
            const map = { dry_mass: 'sd_dry_m', propellant_mass: 'sd_prop_m',
                          thrust: 'sd_thrust', burn_time: 'sd_burn' };
            const el = map[k] && $(map[k]);
            if (el) el.value = v;
        });

        // Bileşen tablosu varsayılan satırları
        defaultComponents().forEach(addComponentRow);

        // Canlı güncelleme: tüm form girdileri şema/doğrulamayı tetikler
        FIELDS.forEach(function (f) {
            const el = $(f.id);
            if (!el) return;
            el.addEventListener('input', updateLive);
            el.addEventListener('change', updateLive);
        });
        const useCurveEl = $('sd_use_curve');
        if (useCurveEl) useCurveEl.addEventListener('change', updateLive);

        // İtki kaynağı seçici + motor dosyası + .ork içe aktarma olayları
        const srcEl = $('sd_thrust_src');
        if (srcEl) {
            srcEl.addEventListener('change', function () {
                refreshImportControls();
                updateLive();
            });
        }
        const motorFileEl = $('sd_motor_file');
        if (motorFileEl) {
            motorFileEl.addEventListener('change', function (ev) {
                const file = ev.target.files && ev.target.files[0];
                if (file) onMotorFileChosen(file);
            });
        }
        const motorSelEl = $('sd_motor_select');
        if (motorSelEl) {
            motorSelEl.addEventListener('change', function () {
                importedIdx = parseInt(motorSelEl.value, 10) || 0;
                const m = importedMotors[importedIdx];
                if (m) {
                    setMotorStatus(TF('sixdof.usingMotor',
                        { name: (m.meta && m.meta.name) || '?', n: m.time.length },
                        'Using imported motor: {name} ({n} points)'));
                    suggestPropMass(m);
                }
            });
        }
        const orkFileEl = $('sd_ork_file');
        if (orkFileEl) {
            orkFileEl.addEventListener('change', function (ev) {
                const file = ev.target.files && ev.target.files[0];
                if (file) onOrkFileChosen(file);
            });
        }
        refreshImportControls();

        // Tablo olayları (delegasyon)
        const tbody = $('sd_comp_body');
        if (tbody) {
            tbody.addEventListener('input', updateLive);
            tbody.addEventListener('change', updateLive);
            tbody.addEventListener('click', function (ev) {
                const btn = ev.target && ev.target.closest
                    ? ev.target.closest('.sd-c-del') : null;
                if (btn) {
                    const tr = btn.closest('tr');
                    if (tr && tr.parentNode) tr.parentNode.removeChild(tr);
                    updateLive();
                }
            });
        }
        const addBtn = $('sd_comp_add');
        if (addBtn) {
            addBtn.addEventListener('click', function () {
                addComponentRow({ name: T('sixdof.colComponent', 'Component'),
                                  mass: 1.0, x: 0.0, propellant: false });
                updateLive();
            });
        }

        // Mod radyoları + kayıtlı mod
        const radios = document.querySelectorAll('input[name="sd_mass_mode"]');
        for (let i = 0; i < radios.length; i++) {
            radios[i].addEventListener('change', function (ev) {
                setMode(ev.target.value, true);
            });
        }
        let saved = 'simple';
        try { saved = localStorage.getItem(MODE_KEY) || 'simple'; } catch (e) { /* gizli mod */ }

        $('sd_run').addEventListener('click', run);
        setMode(saved, false);      // updateLive'ı da çağırır (ilk şema çizimi)
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        // Dil değişince: sabit etiketler I18N.apply ile, şema/rozet/grafikler
        // saklanan sonuçla yeniden basılır.
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                updateLive();
                if (lastRender) {
                    try { render(lastRender.data, lastRender.usedCurve); }
                    catch (e) { /* çizim yoksa sessiz */ }
                }
            });
        }
    }

    window.SixDofPanel = { init, run };
})();
