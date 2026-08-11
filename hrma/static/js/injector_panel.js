/* ====================================================================
   HRMA Injector Design Panel (liquid + advanced — TEK kaynak)
   --------------------------------------------------------------------
   /api/injector-design endpoint'ini UI'a bağlar (sözleşme:
   docs/10_Enjektor_ARGE.md bölüm B.2/C). sixdof_panel.js deseni.

   Kullanıcıya görünen tüm metinler İNGİLİZCE (v2.5.2 dil birliği).
   Şema çizimleri injector_schematics.js'ten gelir (varsa).

   Kullanım:
     <script src="/static/js/injector_schematics.js"></script>
     <script src="/static/js/injector_panel.js"></script>
     InjectorPanel.init({
         anchorId: 'trajectoryPanel',   // panelin ÖNÜNE ekleneceği element (ops.)
         motorType: 'hybrid'|'liquid',  // tip seçici filtreler + varsayılanlar
         resultsProvider: function () {
             // Mevcut hesap sonucundan otomatik doldurma; null → form değerleri
             // Dönen alanlar: mdot_ox, mdot_fuel, Pc_bar, T_c_K, mw_gas,
             //                rho_ox, rho_fuel (hepsi opsiyonel)
         }
     });
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    let cfg = {};
    let lastDesign = null;          // dil değişiminde yeniden çizmek için
    // lastDesign HANGİ tip için hesaplandı? Kullanıcı tipi değiştirip
    // yeniden koşmadıysa eski geometriyi yeni tipin çizimine BASMAK
    // yanlış bilgi olurdu (pintle sayılarıyla swirl çizmek gibi).
    let lastDesignType = null;

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

    const TYPE_OPTIONS = {
        // Spec A.1 seçim matrisi: hibritte yalnız oksitleyici devresi anlamlı.
        // Pintle hibritte de MEŞRUDUR (ox-merkezli tek akışkan, v2.5.2).
        hybrid: [
            ['showerhead', 'Showerhead (default)', 'inj.typeShowerheadDefault'],
            ['swirl', 'Pressure-swirl / vortex', 'inj.typeSwirl'],
            ['pintle', 'Pintle (throttleable)', 'inj.typePintle'],
            ['like_impinging', 'Like-impinging (self)', 'inj.typeLike'],
        ],
        liquid: [
            ['impinging_doublet', 'Unlike doublet (default)', 'inj.typeDoublet'],
            ['impinging_triplet', 'Unlike triplet (2:1)', 'inj.typeTriplet'],
            ['like_impinging', 'Like-impinging (self)', 'inj.typeLike'],
            ['showerhead', 'Showerhead', 'inj.typeShowerhead'],
            ['pintle', 'Pintle (throttleable)', 'inj.typePintle'],
            ['coax_swirl', 'Coaxial swirl', 'inj.typeCoaxSwirl'],
            ['swirl', 'Pressure-swirl', 'inj.typeSwirlOnly'],
        ],
    };

    // Alan açıklamaları (title): [anahtar, İngilizce yedek]
    const FIELD_HELP_KEYS = {
        inj_type: ['inj.helpType',
            'Injector element family. Drives the geometry model, the '
            + 'discharge-coefficient basis and the atomisation correlation.'],
        inj_dp: ['inj.helpDp',
            'Injector pressure drop as a fraction of chamber pressure. '
            + 'Typical 0.15-0.30; below 0.15 chug instability is likely '
            + '(NASA SP-8089).'],
        inj_mdot_ox: ['inj.helpMdotOx',
            'Oxidizer mass flow rate through the injector. Typical '
            + 'amateur/university range 0.1-5 kg/s.'],
        inj_mdot_fuel: ['inj.helpMdotFuel',
            'Fuel mass flow rate (liquid engines only). Set by the '
            + 'mixture ratio: mdot_fuel = mdot_ox / (O/F).'],
        inj_pc: ['inj.helpPc',
            'Chamber pressure at the design point. Hybrids typically '
            + '15-40 bar, liquids 30-150 bar.'],
        inj_rho_ox: ['inj.helpRhoOx',
            'Liquid oxidizer density at injection temperature. N2O at '
            + '293 K is about 745-790 kg/m3; LOX about 1141 kg/m3.'],
        inj_rho_fuel: ['inj.helpRhoFuel',
            'Liquid fuel density. RP-1 about 810 kg/m3, ethanol about 789 kg/m3.'],
        inj_inlet: ['inj.helpInlet',
            'Orifice inlet geometry. A radiused inlet (r/d >= 0.15) '
            + 'raises Cd to about 0.90-0.92; a sharp edge gives 0.63-0.84 and '
            + 'can hydraulically flip.'],
        inj_ld: ['inj.helpLd',
            'Orifice length-to-diameter ratio. 3-5 is the usual '
            + 'manufacturing sweet spot; below 1 the vena contracta dominates.'],
        inj_n2o: ['inj.helpN2o',
            'Self-pressurised nitrous oxide flashes across the orifice. '
            + 'With this enabled the Dyer NHNE two-phase model sets the flow '
            + 'rate and the pressure drop follows from tank temperature.'],
        inj_tox: ['inj.helpTox',
            'Nitrous oxide tank temperature. Sets saturation pressure '
            + '(about 50 bar at 293 K) and therefore the available dP.'],
        inj_tmr: ['inj.helpTmr',
            'Pintle total momentum ratio target. TMR = 1 gives a 60 deg '
            + 'spray half angle (Cheng 2017); usual band 0.5-2.'],
        // HİBRİT PİNTLE'IN GERÇEK KOLU (2026-08-09 ölçümü).
        // Kullanıcıya 'Pintle TMR target' gösteriliyordu ama hibritte TMR
        // BİR ÇIKTIDIR: aynı akışkan + aynı dP olduğu için hızlar eşittir ve
        // TMR = f/(1-f) bağıntısıyla YALNIZ radyal paydan doğar
        // (hrma/engines/injector_design.py:1660). Çözücünün okuduğu alan
        // `pintle.radial_fraction` idi ve arayüzde HİÇ açılmamıştı, 0,5'te
        // gömülü kalıyordu. Dolayısıyla TMR kutusunu çevirmek sonucu
        // değiştirmiyordu — atıl bir düğmeydi.
        inj_radial_fraction: ['inj.helpRadialFraction',
            'Share of the oxidizer flow sent through the radial tip holes '
            + '(the rest goes through the annulus). This is the real control '
            + 'for a single-fluid hybrid pintle: TMR = f/(1-f) follows from '
            + 'it, and the spray cone angle follows from TMR. Usual band '
            + '0.3-0.7.'],
        inj_bf: ['inj.helpBf',
            'Pintle blockage factor: fraction of the pintle circumference '
            + 'occupied by radial holes. TRW heritage band 0.3-0.74.'],
        inj_theta: ['inj.helpTheta',
            'Target spray cone half angle for swirl elements. The '
            + 'Giffen-Muraszew relation caps at about 18 deg; larger targets '
            + 'fall back to K = 1 with a warning.'],
    };

    function help(id) {
        const pair = FIELD_HELP_KEYS[id];
        return pair ? T(pair[0], pair[1]) : '';
    }

    function fieldHtml(id, labelKey, label, value, step, extra) {
        const hk = FIELD_HELP_KEYS[id];
        const hAttr = hk ? ` data-i18n-title="${hk[0]}" title="${help(id)}"` : '';
        return `<div class="form-group" ${extra || ''}${hAttr}>
            <label data-i18n="${labelKey}">${T(labelKey, label)}</label>
            <input type="number" id="${id}" value="${value}" step="${step}"${hAttr}>
        </div>`;
    }

    function panelHtml(motorType) {
        const isHybrid = motorType === 'hybrid';
        const typeOpts = (TYPE_OPTIONS[motorType] || TYPE_OPTIONS.liquid)
            .map(([v, t, k]) => `<option value="${v}" data-i18n="${k}">${T(k, t)}</option>`).join('');
        return `
        <div class="panel" id="injectorPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="inj.title">${T('inj.title', 'Injector Design')}</span> — <span
                data-i18n="${isHybrid ? 'inj.subHybrid' : 'inj.subLiquid'}">${isHybrid
                ? T('inj.subHybrid', 'HYBRID (oxidizer circuit only)')
                : T('inj.subLiquid', 'LIQUID (bipropellant)')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatItDoes">${T('common.whatItDoes',
                    'What it does:')}</strong>
                <span data-i18n="inj.intro">${T('inj.intro',
                    'Orifice sizing (mdot = Cd·A·sqrt(2·rho·dP)), Dyer NHNE two-phase '
                    + 'model for N2O, element-specific geometry (impingement angle and '
                    + 'momentum, pintle TMR/BF, swirl K to cone angle), SMD atomisation '
                    + 'estimate, manifold sizing and chug stability checks. '
                    + 'Sources: NASA SP-8089, Dyer 2007, Lefebvre.')}</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:12px 0;">
                <div class="form-group" data-i18n-title="inj.helpType" title="${help('inj_type')}">
                    <label data-i18n="inj.fType">${T('inj.fType', 'Injector type')}</label>
                    <select id="inj_type" data-i18n-title="inj.helpType"
                        title="${help('inj_type')}">${typeOpts}</select>
                </div>
                ${fieldHtml('inj_dp', 'inj.fDp', 'dP / Pc ratio', 0.20, 0.01)}
                ${fieldHtml('inj_mdot_ox', 'inj.fMdotOx', 'Oxidizer mdot (kg/s)', 2.0, 0.05)}
                ${isHybrid ? '' : fieldHtml('inj_mdot_fuel', 'inj.fMdotFuel', 'Fuel mdot (kg/s)', 0.8, 0.05)}
                ${fieldHtml('inj_pc', 'inj.fPc', 'Chamber pressure (bar)', isHybrid ? 20 : 100, 1)}
                ${fieldHtml('inj_rho_ox', 'inj.fRhoOx', 'Oxidizer density (kg/m3)', isHybrid ? 786 : 1141, 5)}
                ${isHybrid ? '' : fieldHtml('inj_rho_fuel', 'inj.fRhoFuel', 'Fuel density (kg/m3)', 810, 5)}
                <div class="form-group" data-i18n-title="inj.helpInlet" title="${help('inj_inlet')}">
                    <label data-i18n="inj.fInlet">${T('inj.fInlet', 'Orifice inlet')}</label>
                    <select id="inj_inlet" data-i18n-title="inj.helpInlet" title="${help('inj_inlet')}">
                        <option value="sharp" data-i18n="inj.inletSharp">${
                            T('inj.inletSharp', 'Sharp edge')}</option>
                        <option value="radiused" data-i18n="inj.inletRadiused">${
                            T('inj.inletRadiused', 'Radiused')}</option>
                    </select>
                </div>
                ${fieldHtml('inj_ld', 'inj.fLd', 'Orifice L/D', 4.0, 0.5)}
                ${isHybrid ? `
                <div class="form-group" id="inj_n2o_group" data-i18n-title="inj.helpN2o"
                     title="${help('inj_n2o')}">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" id="inj_n2o" checked style="width:auto;">
                        <span data-i18n="inj.fN2o">${T('inj.fN2o', 'N2O two-phase (Dyer NHNE)')}</span>
                    </label>
                </div>
                ${fieldHtml('inj_tox', 'inj.fTox', 'N2O tank temperature (K)', 293, 1)}` : ''}
                ${isHybrid
                    // Hibritte kullanıcının çevirebileceği GERÇEK kol radyal
                    // paydır; TMR onun çıktısıdır (yukarıdaki nota bakın).
                    ? fieldHtml('inj_radial_fraction', 'inj.fRadialFraction',
                                'Radial flow fraction (0-1)', 0.5, 0.05,
                                'id="inj_radial_fraction_group"')
                    : fieldHtml('inj_tmr', 'inj.fTmr', 'Pintle TMR target', 1.0, 0.05,
                                'id="inj_tmr_group"')}
                ${fieldHtml('inj_bf', 'inj.fBf', 'Pintle BF target', 0.58, 0.02, 'id="inj_bf_group"')}
                ${fieldHtml('inj_theta', 'inj.fTheta', 'Swirl cone half angle target (deg)', 45, 1,
                            'id="inj_theta_group"')}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="inj_run" data-i18n="inj.btnRun">${
                        T('inj.btnRun', 'Design injector')}</button>
                </div>
            </div>
            <div id="inj_dp_note" style="font-size:0.78rem; color:var(--hd-ink-dim);
                 margin:-4px 0 8px;"></div>
            <div id="inj_tmr_note" style="font-size:0.78rem; color:var(--hd-orange, #ff8c33);
                 margin:-4px 0 8px;"></div>
            <div id="inj_schematic" style="margin:10px 0; padding:8px;
                 border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                 border-radius:8px; max-width:520px;"></div>
            <div id="inj_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="inj_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="inj_results" style="display:none;"></div>
        </div>`;
    }

    function badge(text, kind, title) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)', warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)', info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        return `<span title="${title || ''}" style="border:1px solid ${c}; color:${c};
                 border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
                 font-size:0.75rem;">${text}</span>`;
    }

    function num(id, fallback) {
        const el = document.getElementById(id);
        if (!el) return fallback;
        const v = parseFloat(el.value);
        return Number.isFinite(v) ? v : fallback;
    }

    // Alan BOŞSA doldurur; kullanıcı bir değer girdiyse ASLA ezmez.
    // (Eski davranış her çalıştırmada elle girilen değeri siliyordu.)
    function fillIfEmpty(id, value) {
        const el = document.getElementById(id);
        if (!el || value == null || !Number.isFinite(value)) return;
        const raw = (el.value == null) ? '' : String(el.value).trim();
        if (raw === '') el.value = value;
    }

    function fmt(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—' : x.toFixed(d == null ? 2 : d);
    }

    // ------------------------------------------------------------------
    // Rozetler (spec bölüm D)
    // ------------------------------------------------------------------
    function badgesHtml(dz) {
        const st = dz.stability || {};
        const ox = dz.ox_circuit || {};
        const fu = dz.fuel_circuit;
        const at = dz.atomization || {};
        const mo = dz.momentum;
        let html = '';

        const dpPct = (st.dp_pc_ratio_ox != null) ? st.dp_pc_ratio_ox * 100 : null;
        html += badge(`dP/Pc ${fmt(dpPct, 0)}%`
            + (st.chug_ok ? '' : ' — ' + T('inj.chugRisk', 'CHUG RISK')),
            st.chug_ok ? 'ok' : 'err', st.chug_rule || '');

        const flowModel = ox.flow_model || 'SPI';
        html += badge(T('inj.modelBadge', 'MODEL') + ': ' + flowModel,
            (dz.fluid_ox === 'n2o' && flowModel !== 'NHNE') ? 'warn' : 'info',
            flowModel === 'NHNE'
                ? T('inj.nhneTip', 'Dyer NHNE two-phase model (AIAA 2007-5702)')
                : T('inj.spiTip', 'Single-phase SPI'));

        const flip = ox.hydraulic_flip_risk || (fu && fu.hydraulic_flip_risk);
        if (flip) html += badge(T('inj.flipRisk', 'FLIP RISK'), 'err',
            T('inj.flipTip', 'Hydraulic flip: cavitation-driven Cd collapse (Nurick 1976)'));

        if (mo && mo.momentum_ratio != null) {
            html += badge(`MR ${fmt(mo.momentum_ratio)} → `
                + T('inj.target', 'TARGET') + ' ' + fmt(mo.target),
                mo.ok ? 'ok' : 'warn', mo.rupe_factor != null ?
                (T('inj.rupeFactor', 'Rupe factor') + ': ' + fmt(mo.rupe_factor)) : '');
        } else if (mo && mo.tmr != null) {
            html += badge(`TMR ${fmt(mo.tmr)} → ` + T('inj.target', 'TARGET') + ' ' + fmt(mo.target),
                mo.ok ? 'ok' : 'warn');
        }

        if (at.smd_ox_um != null) {
            html += badge(`SMD ~${fmt(at.smd_ox_um, 0)} um (${at.correlation || '?'})`, 'info');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Devre tablosu + tipe özel bloklar (spec bölüm D)
    // ------------------------------------------------------------------
    function circuitRows(name, c) {
        if (!c) return '';
        const man = c.manifold || {};
        return `<tr>
            <td>${name}</td>
            <td>${c.n_orifices != null ? c.n_orifices : '—'}</td>
            <td>${fmt(c.orifice_d_mm)}</td>
            <td>${fmt(c.total_area_mm2, 1)}</td>
            <td>${fmt(c.delta_p_bar, 1)}</td>
            <td>${fmt(c.velocity_m_s, 1)}</td>
            <td title="${c.cd_basis || ''}" style="cursor:help;">${fmt(c.cd)}</td>
            <td>${fmt(man.d_mm, 1)} mm · v/v=${fmt(man.v_ratio)}</td>
        </tr>`;
    }

    const TBL = 'width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;';
    const TD = 'padding:6px 8px; border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));';

    function specificBlock(dz) {
        const rows = [];
        if (dz.pintle_geometry) {
            const p = dz.pintle_geometry;
            rows.push([T('inj.pintleDia', 'Pintle diameter D_p'), fmt(p.d_pintle_mm) + ' mm'],
                      [T('inj.skipDistance', 'Skip distance'),
                       fmt(p.skip_distance_mm) + ' mm (L_s/D_p=' + fmt(p.ls_over_dp) + ')'],
                      [T('inj.blockageFactor', 'Blockage factor BF'), fmt(p.bf)],
                      [T('inj.annulusGap', 'Annulus gap'), fmt(p.annulus_gap_mm) + ' mm'],
                      [T('inj.radialHoles', 'Radial holes'),
                       TF('inj.radialHolesValue',
                          { n: p.n_radial_holes, d: fmt(p.radial_hole_d_mm) },
                          '{n} x dia {d} mm')]);
            if (p.single_fluid) {
                rows.push([T('inj.elementArrangement', 'Element arrangement'),
                           TF('inj.singleFluid',
                              { pct: fmt((p.radial_flow_fraction || 0) * 100, 0) },
                              'Single-fluid (oxidizer-centred hybrid pintle); '
                              + 'radial flow share {pct}%')]);
            }
        }
        if (dz.swirl_geometry) {
            const s = dz.swirl_geometry;
            rows.push([T('inj.swirlK', 'Swirl constant K'), fmt(s.K)],
                      [T('inj.airCore', 'Air core X'), fmt(s.X_air_core)],
                      [T('inj.cdSwirl', 'Cd (effective swirl)'), fmt(s.cd_swirl)],
                      [T('inj.filmThickness', 'Film thickness'), fmt(s.film_thickness_mm, 3) + ' mm'],
                      [T('inj.tangentialInlets', 'Tangential inlets'),
                       TF('inj.radialHolesValue',
                          { n: s.tangential_inlets, d: fmt(s.inlet_d_mm) },
                          '{n} x dia {d} mm')]);
        }
        const imp = dz.pattern && dz.pattern.impingement;
        if (imp) {
            rows.push([T('inj.impingeAngle', 'Impingement half angle'),
                       fmt(imp.half_angle_deg, 1) + ' deg'],
                      [T('inj.freeJet', 'Free jet length'), fmt(imp.free_jet_length_mm, 1) + ' mm'],
                      [T('inj.elementSpacing', 'Element spacing'),
                       fmt(imp.element_spacing_mm, 1) + ' mm']);
        }
        const cone = dz.atomization && dz.atomization.spray_cone_half_angle_deg;
        if (cone != null) {
            rows.push([T('inj.sprayCone', 'Spray cone half angle'), fmt(cone, 1) + ' deg']);
        }
        if (!rows.length) return '';
        return `<h4 style="margin:12px 0 4px;">${T('inj.secGeometry',
            'Element-specific geometry')}</h4>
            <table style="${TBL}">` +
            rows.map(([k, v]) => `<tr><td style="${TD}"><strong>${k}</strong></td>
                <td style="${TD}">${v}</td></tr>`).join('') + '</table>';
    }

    function resultsHtml(dz) {
        const fu = dz.fuel_circuit;
        const at = dz.atomization || {};
        let html = '';

        if (dz.pattern && dz.pattern.description_tr) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.85rem;
                color:var(--hd-ink-dim); margin:8px 0;">${dz.pattern.description_tr}</p>`;
        }

        html += `<table style="${TBL}">
            <thead><tr>
                <th style="${TD} text-align:left;">${T('inj.colCircuit', 'Circuit')}</th>
                <th style="${TD}">${T('inj.colOrifices', 'Orifices')}</th>
                <th style="${TD}">${T('inj.colDia', 'dia (mm)')}</th>
                <th style="${TD}">${T('inj.colArea', 'Total A (mm2)')}</th>
                <th style="${TD}">${T('inj.colDp', 'dP (bar)')}</th>
                <th style="${TD}">${T('inj.colV', 'v (m/s)')}</th>
                <th style="${TD}">C_d</th>
                <th style="${TD}">${T('inj.colManifold', 'Manifold')}</th>
            </tr></thead><tbody>` +
            circuitRows(T('common.oxidizer', 'Oxidizer'), dz.ox_circuit) +
            (fu ? circuitRows(T('common.fuel', 'Fuel'), fu) : '') +
            '</tbody></table>';

        if (fu && at.smd_fuel_um != null) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim);">${
                TF('inj.fuelSmd', { v: fmt(at.smd_fuel_um, 0) },
                   'Fuel circuit SMD: ~{v} um')}</p>`;
        }

        html += specificBlock(dz);

        const warns = dz.warnings_tr || [];
        if (warns.length) {
            html += `<div style="border:1px solid var(--hd-orange, #ff8c33); border-radius:8px;
                padding:10px 14px; margin:10px 0; color:var(--hd-orange, #ff8c33);">
                <strong>${T('common.warnings', 'Warnings')}</strong>
                <ul style="margin:6px 0 0 18px;">` +
                warns.map(w => `<li>${w}</li>`).join('') + '</ul></div>';
        }

        const assum = dz.assumptions_tr || [];
        if (assum.length) {
            html += `<details style="margin:8px 0;"><summary style="cursor:pointer;
                color:var(--hd-ink-dim);">${T('common.assumptions', 'Assumptions')} (${assum.length})</summary>
                <ul style="margin:6px 0 0 18px; color:var(--hd-ink-dim); font-size:0.85rem;">` +
                assum.map(a => `<li>${a}</li>`).join('') + '</ul></details>';
        }

        const refs = dz.references || [];
        if (refs.length) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim); margin-top:8px;">
                ${T('common.references', 'References')}: ${refs.join(' · ')}</p>`;
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Payload (spec bölüm B.1) — provider değerleri YALNIZ boş alanları
    // doldurur, sonra TEK kaynak olarak formdan okunur (kullanıcı ne
    // gönderildiğini görür ve elle girdiği değer korunur)
    // ------------------------------------------------------------------
    function buildSpec() {
        if (cfg.resultsProvider) {
            let r = null;
            try { r = cfg.resultsProvider(); } catch (e) { r = null; }
            if (r) {
                fillIfEmpty('inj_mdot_ox', r.mdot_ox);
                fillIfEmpty('inj_mdot_fuel', r.mdot_fuel);
                fillIfEmpty('inj_pc', r.Pc_bar);
                fillIfEmpty('inj_rho_ox', r.rho_ox);
                fillIfEmpty('inj_rho_fuel', r.rho_fuel);
                cfg._tc = r.T_c_K; cfg._mw = r.mw_gas;
            }
        }
        const isHybrid = cfg.motorType === 'hybrid';
        const type = document.getElementById('inj_type').value;
        const dp = num('inj_dp', 0.20);
        const inlet = document.getElementById('inj_inlet').value;
        const n2oEl = document.getElementById('inj_n2o');
        const useN2o = isHybrid && n2oEl && n2oEl.checked;

        const spec = {
            motor_type: cfg.motorType,
            injector_type: type,
            mdot_ox: num('inj_mdot_ox', 0),
            rho_ox: num('inj_rho_ox', undefined),
            Pc_bar: num('inj_pc', 0),
            fluid_ox: useN2o ? 'n2o' : 'generic',
            inlet_ox: inlet,
            l_over_d: num('inj_ld', 4.0),
        };
        // İki-fazlı N2O'da dP tank sıcaklığından türer (doyma basıncı); form
        // oranı gönderilmez, aksi halde kullanıcı "değiştirdim ama değişmiyor"
        // durumuyla karşılaşır.
        if (useN2o) {
            spec.T_ox_K = num('inj_tox', 293);
        } else {
            spec.dp_ratio_ox = dp;
        }
        if (!isHybrid) {
            spec.mdot_fuel = num('inj_mdot_fuel', 0);
            spec.rho_fuel = num('inj_rho_fuel', 810);
            spec.dp_ratio_fuel = dp;
            spec.inlet_fuel = inlet;
        }
        if (cfg._tc != null) spec.T_c_K = cfg._tc;
        if (cfg._mw != null) spec.mw_gas = cfg._mw;
        if (type === 'pintle') {
            spec.pintle = { bf_target: num('inj_bf', 0.58) };
            if (isHybrid) {
                // Tek akışkanlı hibrit pintle: çözücünün GERÇEKTEN okuduğu
                // alan bu (injector_design.py:1637 `pin.get('radial_fraction')`).
                // Daha önce hiç gönderilmiyordu, çözücü 0,5 sabitinde kalıyordu.
                spec.pintle.radial_fraction = num('inj_radial_fraction', 0.5);
            } else {
                // Sıvı yakıt-merkezli pintle: TMR debilerden ve hızlardan
                // hesaplanır; tmr_target YALNIZ karşılaştırma hedefidir
                // (momentum.target). Geometriyi değiştirmez — bu durum
                // kullanıcıya aşağıda açıkça bildirilir.
                spec.pintle.tmr_target = num('inj_tmr', 1.0);
            }
        }
        if (type === 'swirl' || type === 'coax_swirl') {
            spec.swirl = { theta_target_deg: num('inj_theta', 45) };
        }
        return spec;
    }

    async function run() {
        const status = document.getElementById('inj_status');
        const badges = document.getElementById('inj_badges');
        const results = document.getElementById('inj_results');
        const btn = document.getElementById('inj_run');
        const typeEl = document.getElementById('inj_type');
        btn.disabled = true;
        badges.innerHTML = '';
        results.style.display = 'none';
        status.textContent = T('inj.designing', 'DESIGNING INJECTOR…');
        try {
            const resp = await fetch('/api/injector-design', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(buildSpec()),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            const dz = data.design || {};
            if (dz.status === 'error') throw new Error(dz.error || 'design error');
            lastDesign = dz;
            lastDesignType = typeEl ? typeEl.value : null;
            badges.innerHTML = badgesHtml(dz);
            results.innerHTML = resultsHtml(dz);
            results.style.display = 'block';
            // Hesap bitti: çizim ARTIK bu hesabın geometrisini gösterir
            // (delik sayısı, delik çapı, D_p, sprey açısı...).
            if (lastDesignType) {
                renderSchematic(lastDesignType, schematicGeometry(dz));
            }
            status.textContent = '';
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // ÇİZİM ARTIK HESABI GÖRÜYOR (2026-08-09)
    // ------------------------------------------------------------------
    // Şema çizimi ile panelin hesabı arasında hiç veri yolu yoktu: panel
    // 17 radyal delik hesaplayıp tabloya bastığında bile çizimde SABİT
    // 2 ok kalıyordu. Bu işlev /api/injector-design yanıtını çizimin
    // anladığı sözlüğe indirger. Bir alan yanıtta yoksa buraya da
    // KONULMAZ; çizim o künyeyi hiç basmaz (uydurma değer yok).
    function schematicGeometry(dz) {
        if (!dz) return null;
        const g = {};
        const put = (key, value) => {
            if (typeof value === 'number' && isFinite(value)) g[key] = value;
        };
        const p = dz.pintle_geometry;
        if (p) {
            put('n_radial_holes', p.n_radial_holes);
            put('radial_hole_d_mm', p.radial_hole_d_mm);
            put('d_pintle_mm', p.d_pintle_mm);
            put('annulus_gap_mm', p.annulus_gap_mm);
            put('skip_distance_mm', p.skip_distance_mm);
            put('bf', p.bf);
            put('radial_flow_fraction', p.radial_flow_fraction);
            // single_fluid YALNIZ hibrit ox-merkezli pintle'da gelir; sıvı
            // yakıt-merkezli düzende hiç yoktur (iki akışkan).
            if (p.single_fluid) g.single_fluid = true;
        }
        const s = dz.swirl_geometry;
        if (s) {
            put('tangential_inlets', s.tangential_inlets);
            put('inlet_d_mm', s.inlet_d_mm);
            put('film_thickness_mm', s.film_thickness_mm);
            put('K', s.K);
        }
        const ox = dz.ox_circuit;
        if (ox) {
            put('n_orifices', ox.n_orifices);
            put('orifice_d_mm', ox.orifice_d_mm);
        }
        const pat = dz.pattern || {};
        put('n_elements', pat.n_elements);
        if (pat.impingement) put('half_angle_deg', pat.impingement.half_angle_deg);
        if (dz.atomization) {
            put('spray_half_angle_deg', dz.atomization.spray_cone_half_angle_deg);
        }
        // Tek akışkan bilgisi coax/showerhead için de anlamlı: hibritte
        // yakıt devresi YOKTUR.
        if (!dz.fuel_circuit) g.single_fluid = true;
        return g;
    }

    function renderSchematic(type, geom) {
        const host = document.getElementById('inj_schematic');
        if (!host) return;
        if (window.InjectorSchematics) {
            // geom verilmezse son tasarımdan türetilir; o da yoksa çizim
            // sayısal künyesiz genel hâliyle basılır.
            const same = window.InjectorSchematics.resolve
                ? (window.InjectorSchematics.resolve(lastDesignType)
                   === window.InjectorSchematics.resolve(type))
                : (lastDesignType === type);
            const g = (geom !== undefined) ? geom
                : (lastDesignType && same ? schematicGeometry(lastDesign) : null);
            window.InjectorSchematics.render(type, host, g);
        } else {
            host.style.display = 'none';
        }
    }

    function syncTypeFields() {
        const type = document.getElementById('inj_type').value;
        const show = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.style.display = on ? '' : 'none';
        };
        show('inj_tmr_group', type === 'pintle');
        show('inj_radial_fraction_group', type === 'pintle');
        show('inj_bf_group', type === 'pintle');
        show('inj_theta_group', type === 'swirl' || type === 'coax_swirl');

        // TMR HEDEFİ SALT KARŞILAŞTIRMADIR (sıvı pintle).
        // ÖLÇÜLDÜ (2026-08-09, /api/injector-design): tmr_target 0,5 ->
        // achieved 0,4747; tmr_target 2,0 -> achieved 0,4747. Yani alanın
        // sonuca hiçbir etkisi yok, yalnız rozetteki "TARGET" sayısını
        // değiştiriyor. Sessizce bırakmak kullanıcıyı bu kolu çevirdiğinde
        // motorun değiştiğine inandırıyordu.
        const tmrNote = document.getElementById('inj_tmr_note');
        if (tmrNote) {
            tmrNote.textContent = (type === 'pintle'
                    && document.getElementById('inj_tmr'))
                ? T('inj.tmrEchoNote',
                    'This target does not change the geometry: for a '
                    + 'fuel-centred pintle the achieved TMR follows from the '
                    + 'mass flows and injection velocities. The value you '
                    + 'enter is only the band the achieved TMR is compared '
                    + 'against.')
                : '';
        }
        const tox = document.getElementById('inj_tox');
        const n2o = document.getElementById('inj_n2o');
        if (tox && n2o) tox.parentElement.style.display = n2o.checked ? '' : 'none';

        // İki-fazlı N2O açıkken dP/Pc alanı kullanıcı girdisi DEĞİLDİR:
        // basınç düşümü tank sıcaklığından (doyma basıncı) türer.
        const dpEl = document.getElementById('inj_dp');
        const note = document.getElementById('inj_dp_note');
        const twoPhase = !!(n2o && n2o.checked);
        if (dpEl) {
            dpEl.disabled = twoPhase;
            dpEl.style.opacity = twoPhase ? '0.5' : '';
            if (dpEl.parentElement) {
                dpEl.parentElement.title = twoPhase
                    ? T('inj.dpDisabledTip',
                        'Disabled: dP is set by tank temperature via Dyer NHNE '
                        + 'when two-phase N2O is enabled.')
                    : help('inj_dp');
            }
        }
        if (note) {
            note.textContent = twoPhase
                ? T('inj.dpNote',
                    'dP is set by tank temperature via Dyer NHNE when two-phase '
                    + 'N2O is enabled. Change the tank temperature to change dP.')
                : '';
        }

        renderSchematic(type);
    }

    function init(options) {
        cfg = options || {};
        cfg.motorType = cfg.motorType === 'hybrid' ? 'hybrid' : 'liquid';
        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = panelHtml(cfg.motorType);
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(panel);
        }
        document.getElementById('inj_run').addEventListener('click', run);
        document.getElementById('inj_type').addEventListener('change', syncTypeFields);
        const n2o = document.getElementById('inj_n2o');
        if (n2o) n2o.addEventListener('change', syncTypeFields);
        syncTypeFields();
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        // Dil değişince: sabit etiketler I18N.apply ile, sonuç bloğu saklanan
        // tasarımla yeniden basılır.
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                syncTypeFields();
                if (!lastDesign) return;
                const badges = document.getElementById('inj_badges');
                const results = document.getElementById('inj_results');
                if (badges) badges.innerHTML = badgesHtml(lastDesign);
                if (results && results.style.display !== 'none') {
                    results.innerHTML = resultsHtml(lastDesign);
                }
            });
        }
    }

    window.InjectorPanel = {
        init, run, renderSchematic,
        // Test amaçlı saf render (dry-run): B.2 şemalı design → HTML
        _renderHtml: function (dz) { return badgesHtml(dz) + resultsHtml(dz); },
        // Test amaçlı saf dönüşüm: /api/injector-design yanıtı → çizim
        // geometrisi (panel ile şema arasındaki veri yolu).
        _schematicGeometry: schematicGeometry,
        // Test amaçlı saf yük kurucu (DOM gerektirir; tarayıcı testinde).
        _buildSpec: buildSpec,
    };
})();
