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
        return '<tr>' +
            '<td style="padding:2px 4px;"><input type="text" class="sd-c-name" value="' +
                escapeHtml(c.name) + '" ' + cell + '></td>' +
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
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="sd_run" data-i18n="sixdof.btnRun">${
                        T('sixdof.btnRun', 'Run 6-DOF')}</button>
                </div>
            </div>
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
            <div id="sd_plot_alt" class="plot-container" style="min-height:400px; display:none;"></div>
            <div id="sd_plot_alpha" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="sd_plot_track" class="plot-container" style="min-height:380px; display:none;"></div>
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
        const requireThrustForm =
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

        // İtki kaynağı: sayfa sağlayıcısı (transient/solid eğrisi) veya form
        const useCurveEl = $('sd_use_curve');
        let provided = null;
        if (cfg.thrustProvider && (!useCurveEl || useCurveEl.checked)) {
            try { provided = cfg.thrustProvider(); } catch (e) { provided = null; }
        }
        const hasCurve = !!(provided && provided.thrust_curve &&
            provided.thrust_curve.time && provided.thrust_curve.time.length > 3);
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

        if (hasCurve) {
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
            if (isFinite(client.xCp) &&
                Math.abs(client.xCp - s.x_cp) > CP_MATCH_TOL_M) {
                console.warn('SixDofPanel: client-side Barrowman CP (' +
                    client.xCp.toFixed(4) + ' m) does not match backend x_cp (' +
                    s.x_cp.toFixed(4) + ' m) — formulas out of sync?');
            }
            if (isFinite(client.cnAlpha) &&
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

    function render(data, usedCurve) {
        lastRender = { data: data, usedCurve: usedCurve };
        const s = data.summary;
        const ser = data.series;
        const badges = $('sd_badges');

        let html = badge(s.stable ? T('sixdof.bandStable', 'STABLE')
                                  : T('sixdof.unstable', 'UNSTABLE'), s.stable ? 'ok' : 'err');
        html += badge(TF('sixdof.badgeApogee',
                         { km: (s.apogee / 1000).toFixed(2), t: s.apogee_time.toFixed(1) },
                         'APOGEE {km} km @ {t} s'), 'info');
        html += badge(TF('sixdof.badgeMaxMach', { m: s.max_mach.toFixed(2) },
                         'MAX MACH {m}'), 'info');
        html += badge(TF('sixdof.badgeMaxAlpha', { a: s.max_alpha_deg.toFixed(1) },
                         'MAX alpha {a} deg'), s.max_alpha_deg < 10 ? 'ok' : 'warn');
        // NASA amatör roket pratiği: hedef 1.5-2 kalibre; >3 aşırı-stabil
        // (rüzgâra dönme + irtifa kaybı) — 2026-07-15 GPT-5.6 çapraz kontrol önerisi
        const smMin = Math.min(s.static_margin_full, s.static_margin_empty);
        const smMax = Math.max(s.static_margin_full, s.static_margin_empty);
        const smKind = smMin <= 1 ? 'err' : (smMax > 3 ? 'warn' : 'ok');
        html += badge(TF('sixdof.badgeMargin',
                         { full: s.static_margin_full.toFixed(2),
                           empty: s.static_margin_empty.toFixed(2) },
                         'MARGIN {full} / {empty} cal')
            + (smMax > 3 ? ' — ' + T('sixdof.overStable', 'OVER-STABLE') : ''), smKind);
        html += badge(`CNα ${s.cn_alpha.toFixed(2)} · CP ${s.x_cp.toFixed(3)} m`, 'info');
        html += badge(T('sixdof.thrustBadge', 'THRUST') + ': '
            + (usedCurve ? T('sixdof.computedCurve', 'COMPUTED CURVE')
                         : T('sixdof.constantThrust', 'CONSTANT')), 'info');
        if (s.end_reason && s.end_reason !== 'apogee') {
            html += badge(T('transient.badgeEnd', 'END') + ': '
                + s.end_reason.toUpperCase(), 'warn');
        }
        badges.innerHTML = html;

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
