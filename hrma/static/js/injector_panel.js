/* ====================================================================
   HRMA Enjektör Tasarım Paneli (liquid + advanced — TEK kaynak)
   --------------------------------------------------------------------
   /api/injector-design endpoint'ini UI'a bağlar (sözleşme:
   docs/10_Enjektor_ARGE.md bölüm B.2/C). sixdof_panel.js deseni.

   Kullanım:
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

    const TYPE_OPTIONS = {
        // Spec A.1 seçim matrisi: hibritte yalnız oksitleyici devresi anlamlı
        hybrid: [
            ['showerhead', 'Showerhead (varsayılan)'],
            ['swirl', 'Basınç-Swirl / Vorteks'],
            ['pintle', 'Pintle (kısılabilir)'],
        ],
        liquid: [
            ['impinging_doublet', 'Unlike Doublet (varsayılan)'],
            ['impinging_triplet', 'Unlike Triplet (2:1)'],
            ['like_impinging', 'Like-Impinging (self)'],
            ['showerhead', 'Showerhead'],
            ['pintle', 'Pintle (kısılabilir)'],
            ['coax_swirl', 'Koaksiyel Swirl'],
            ['swirl', 'Basınç-Swirl'],
        ],
    };

    function fieldHtml(id, label, value, step, extra) {
        return `<div class="form-group" ${extra || ''}>
            <label>${label}</label>
            <input type="number" id="${id}" value="${value}" step="${step}">
        </div>`;
    }

    function panelHtml(motorType) {
        const isHybrid = motorType === 'hybrid';
        const typeOpts = (TYPE_OPTIONS[motorType] || TYPE_OPTIONS.liquid)
            .map(([v, t]) => `<option value="${v}">${t}</option>`).join('');
        return `
        <div class="panel" id="injectorPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▶ Enjektör Tasarımı — ${isHybrid ? 'HİBRİT (yalnız oksitleyici)' : 'SIVI (çift yakıt)'}</h2>
            <div class="chart-explanation">
                <strong>Ne yapar:</strong> Orifis boyutlandırma (ṁ=C<sub>d</sub>·A·√(2ρΔP)),
                N₂O için Dyer NHNE iki-faz modeli, tip bazlı geometri (impinging açı/momentum,
                pintle TMR/BF, swirl K→koni açısı), SMD atomizasyon tahmini, manifold ve
                chug kararlılık kontrolleri. Kaynaklar: NASA SP-8089, Dyer 2007, Lefebvre.
                Ayrıntı: <em>docs/10_Enjektor_ARGE.md</em>.
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:12px 0;">
                <div class="form-group">
                    <label>Enjektör Tipi</label>
                    <select id="inj_type">${typeOpts}</select>
                </div>
                ${fieldHtml('inj_dp', 'ΔP/Pc Oranı', 0.20, 0.01)}
                ${fieldHtml('inj_mdot_ox', 'ṁ Oksitleyici (kg/s)', 2.0, 0.05)}
                ${isHybrid ? '' : fieldHtml('inj_mdot_fuel', 'ṁ Yakıt (kg/s)', 0.8, 0.05)}
                ${fieldHtml('inj_pc', 'Oda Basıncı (bar)', isHybrid ? 20 : 100, 1)}
                ${fieldHtml('inj_rho_ox', 'ρ Oksitleyici (kg/m³)', isHybrid ? 786 : 1141, 5)}
                ${isHybrid ? '' : fieldHtml('inj_rho_fuel', 'ρ Yakıt (kg/m³)', 810, 5)}
                <div class="form-group">
                    <label>Orifis Girişi</label>
                    <select id="inj_inlet">
                        <option value="sharp">Keskin kenar</option>
                        <option value="radiused">Radüslü</option>
                    </select>
                </div>
                ${fieldHtml('inj_ld', 'Orifis L/D', 4.0, 0.5)}
                ${isHybrid ? `
                <div class="form-group" id="inj_n2o_group">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" id="inj_n2o" checked style="width:auto;">
                        N₂O iki-faz (Dyer NHNE)
                    </label>
                </div>
                ${fieldHtml('inj_tox', 'N₂O Tank Sıcaklığı (K)', 293, 1)}` : ''}
                ${fieldHtml('inj_tmr', 'Pintle TMR Hedefi', 1.0, 0.05, 'id="inj_tmr_group"')}
                ${fieldHtml('inj_bf', 'Pintle BF Hedefi', 0.58, 0.02, 'id="inj_bf_group"')}
                ${fieldHtml('inj_theta', 'Swirl Koni Yarı Açısı Hedefi (°)', 45, 1, 'id="inj_theta_group"')}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="inj_run">Enjektörü Tasarla</button>
                </div>
            </div>
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

    function setIf(id, value) {
        const el = document.getElementById(id);
        if (el && value != null && Number.isFinite(value)) el.value = value;
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
        html += badge(`ΔP/Pc %${fmt(dpPct, 0)}` + (st.chug_ok ? '' : ' — CHUG RİSKİ'),
            st.chug_ok ? 'ok' : 'err', st.chug_rule || '');

        const flowModel = ox.flow_model || 'SPI';
        html += badge('MODEL: ' + flowModel,
            (dz.fluid_ox === 'n2o' && flowModel !== 'NHNE') ? 'warn' : 'info',
            flowModel === 'NHNE' ? 'Dyer NHNE iki-faz modeli (AIAA 2007-5702)' : 'Tek-faz SPI');

        const flip = ox.hydraulic_flip_risk || (fu && fu.hydraulic_flip_risk);
        if (flip) html += badge('FLIP RİSKİ', 'err',
            'Hydraulic flip: kavitasyon kaynaklı Cd düşüşü (Nurick 1976)');

        if (mo && mo.momentum_ratio != null) {
            html += badge(`MR ${fmt(mo.momentum_ratio)} → HEDEF ${fmt(mo.target)}`,
                mo.ok ? 'ok' : 'warn', mo.rupe_factor != null ?
                ('Rupe faktörü: ' + fmt(mo.rupe_factor)) : '');
        } else if (mo && mo.tmr != null) {
            html += badge(`TMR ${fmt(mo.tmr)} → HEDEF ${fmt(mo.target)}`,
                mo.ok ? 'ok' : 'warn');
        }

        if (at.smd_ox_um != null) {
            html += badge(`SMD ~${fmt(at.smd_ox_um, 0)} µm (${at.correlation || '?'})`, 'info');
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
            rows.push(['Pintle çapı D_p', fmt(p.d_pintle_mm) + ' mm'],
                      ['Skip mesafesi', fmt(p.skip_distance_mm) + ' mm (L_s/D_p=' + fmt(p.ls_over_dp) + ')'],
                      ['Blockage faktörü BF', fmt(p.bf)],
                      ['Anülüs açıklığı', fmt(p.annulus_gap_mm) + ' mm'],
                      ['Radyal delikler', p.n_radial_holes + ' × Ø' + fmt(p.radial_hole_d_mm) + ' mm']);
        }
        if (dz.swirl_geometry) {
            const s = dz.swirl_geometry;
            rows.push(['Swirl sabiti K', fmt(s.K)],
                      ['Hava çekirdeği X', fmt(s.X_air_core)],
                      ['Cd (swirl etkin)', fmt(s.cd_swirl)],
                      ['Film kalınlığı', fmt(s.film_thickness_mm, 3) + ' mm'],
                      ['Teğetsel girişler', s.tangential_inlets + ' × Ø' + fmt(s.inlet_d_mm) + ' mm']);
        }
        const imp = dz.pattern && dz.pattern.impingement;
        if (imp) {
            rows.push(['Çarpışma yarı açısı', fmt(imp.half_angle_deg, 1) + '°'],
                      ['Serbest jet boyu', fmt(imp.free_jet_length_mm, 1) + ' mm'],
                      ['Eleman aralığı', fmt(imp.element_spacing_mm, 1) + ' mm']);
        }
        const cone = dz.atomization && dz.atomization.spray_cone_half_angle_deg;
        if (cone != null) rows.push(['Sprey koni yarı açısı', fmt(cone, 1) + '°']);
        if (!rows.length) return '';
        return `<h4 style="margin:12px 0 4px;">Tipe Özel Geometri</h4>
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
                <th style="${TD} text-align:left;">Devre</th>
                <th style="${TD}">Delik</th><th style="${TD}">Ø (mm)</th>
                <th style="${TD}">ΣA (mm²)</th><th style="${TD}">ΔP (bar)</th>
                <th style="${TD}">v (m/s)</th><th style="${TD}">C_d</th>
                <th style="${TD}">Manifold</th>
            </tr></thead><tbody>` +
            circuitRows('Oksitleyici', dz.ox_circuit) +
            (fu ? circuitRows('Yakıt', fu) : '') +
            '</tbody></table>';

        if (fu && at.smd_fuel_um != null) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim);">
                SMD yakıt devresi: ~${fmt(at.smd_fuel_um, 0)} µm</p>`;
        }

        html += specificBlock(dz);

        const warns = dz.warnings_tr || [];
        if (warns.length) {
            html += `<div style="border:1px solid var(--hd-orange, #ff8c33); border-radius:8px;
                padding:10px 14px; margin:10px 0; color:var(--hd-orange, #ff8c33);">
                <strong>Uyarılar</strong><ul style="margin:6px 0 0 18px;">` +
                warns.map(w => `<li>${w}</li>`).join('') + '</ul></div>';
        }

        const assum = dz.assumptions_tr || [];
        if (assum.length) {
            html += `<details style="margin:8px 0;"><summary style="cursor:pointer;
                color:var(--hd-ink-dim);">Varsayımlar (${assum.length})</summary>
                <ul style="margin:6px 0 0 18px; color:var(--hd-ink-dim); font-size:0.85rem;">` +
                assum.map(a => `<li>${a}</li>`).join('') + '</ul></details>';
        }

        const refs = dz.references || [];
        if (refs.length) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim); margin-top:8px;">
                Kaynaklar: ${refs.join(' · ')}</p>`;
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Payload (spec bölüm B.1) — provider değerleri form alanlarına yazılır,
    // sonra TEK kaynak olarak formdan okunur (kullanıcı ne gönderildiğini görür)
    // ------------------------------------------------------------------
    function buildSpec() {
        if (cfg.resultsProvider) {
            let r = null;
            try { r = cfg.resultsProvider(); } catch (e) { r = null; }
            if (r) {
                setIf('inj_mdot_ox', r.mdot_ox);
                setIf('inj_mdot_fuel', r.mdot_fuel);
                setIf('inj_pc', r.Pc_bar);
                setIf('inj_rho_ox', r.rho_ox);
                setIf('inj_rho_fuel', r.rho_fuel);
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
            dp_ratio_ox: dp,
            fluid_ox: useN2o ? 'n2o' : 'generic',
            inlet_ox: inlet,
            l_over_d: num('inj_ld', 4.0),
        };
        if (useN2o) spec.T_ox_K = num('inj_tox', 293);
        if (!isHybrid) {
            spec.mdot_fuel = num('inj_mdot_fuel', 0);
            spec.rho_fuel = num('inj_rho_fuel', 810);
            spec.dp_ratio_fuel = dp;
            spec.inlet_fuel = inlet;
        }
        if (cfg._tc != null) spec.T_c_K = cfg._tc;
        if (cfg._mw != null) spec.mw_gas = cfg._mw;
        if (type === 'pintle') {
            spec.pintle = { tmr_target: num('inj_tmr', 1.0),
                            bf_target: num('inj_bf', 0.58) };
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
        btn.disabled = true;
        badges.innerHTML = '';
        results.style.display = 'none';
        status.textContent = 'ENJEKTÖR TASARLANIYOR…';
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
            if (dz.status === 'error') throw new Error(dz.error || 'tasarım hatası');
            badges.innerHTML = badgesHtml(dz);
            results.innerHTML = resultsHtml(dz);
            results.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = 'HATA: ' + err.message;
        } finally {
            btn.disabled = false;
        }
    }

    function syncTypeFields() {
        const type = document.getElementById('inj_type').value;
        const show = (id, on) => {
            const el = document.getElementById(id);
            if (el) el.style.display = on ? '' : 'none';
        };
        show('inj_tmr_group', type === 'pintle');
        show('inj_bf_group', type === 'pintle');
        show('inj_theta_group', type === 'swirl' || type === 'coax_swirl');
        const tox = document.getElementById('inj_tox');
        const n2o = document.getElementById('inj_n2o');
        if (tox && n2o) tox.parentElement.style.display = n2o.checked ? '' : 'none';
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
    }

    window.InjectorPanel = {
        init, run,
        // Test amaçlı saf render (dry-run): B.2 şemalı design → HTML
        _renderHtml: function (dz) { return badgesHtml(dz) + resultsHtml(dz); },
    };
})();
