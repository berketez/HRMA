/* ====================================================================
   HRMA Analiz Güvertesi — Cıvatalı Bağlantı Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/bolted-joint sonucunu çizer (STRUCTURAL sekmesinde
   structural_panel'in altında ikinci panel):
   - Cıvata formu: boyut (M4–M24), sınıf (ISO 898-1 / ISO 3506-1), sayı,
     sıkma boyu, üye malzemesi, yağlama, yeniden kullanım
   - Tork önerisi + tork-kontrollü sıkmada ±%25 ön-yük saçılım bandı
   - Ayrılma (separation) marjı rozeti + emniyet faktörü kartları
     (Shigley 10th ed. Eq. 8-24…8-30)
   Backend: hrma/analysis/bolted_joint.py.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    var U = window.AnalysisDock.ui;

    // bolted_joint.py THREAD_STRESS_AREA_MM2 anahtarlarıyla birebir
    var SIZES = ['M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M14', 'M16',
                 'M18', 'M20', 'M22', 'M24'].map(function (s) { return [s, s]; });

    var CLASSES = [
        ['8.8', '8.8 (ISO 898-1)'],
        ['10.9', '10.9 (ISO 898-1)'],
        ['12.9', '12.9 (ISO 898-1)'],
        ['A2-70', 'A2-70 stainless (ISO 3506-1)'],
    ];

    // materials_db anahtarları (sıkılan üye malzemesi)
    var MEMBER_MATERIALS = [
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['steel', 'Steel (generic)'],
        ['steel_4130', 'Steel AISI 4130'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['inconel_718', 'Inconel 718'],
    ];

    var LUBRICATION = [
        ['false', 'Dry assembly (K = 0.20)'],
        ['true', 'Lubricated (K = 0.15)'],
    ];

    var REUSE = [
        ['true', 'Reusable — preload 75% of proof'],
        ['false', 'Permanent — preload 90% of proof'],
    ];

    function sfKind(sf, warnBelow) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        if (sf < 1.0) return 'err';
        if (sf < (warnBelow == null ? 1.5 : warnBelow)) return 'warn';
        return 'ok';
    }

    function fmtKN(n) {
        return (n == null || !Number.isFinite(n)) ? '—' : (n / 1e3).toFixed(2);
    }

    function render(data, root) {
        var j = (data && data.joint) || {};
        var bolt = j.bolt || {};
        var pre = j.preload || {};
        var tq = j.torque || {};
        var st = j.stiffness || {};
        var loads = j.loads || {};
        var sf = j.safety_factors || {};
        var sep = j.separation || {};

        // ---- Rozetler ----
        var badges = '';
        badges += sep.separated
            ? U.badge('JOINT SEPARATED', 'err',
                'External load exceeds the preload capacity — the joint opens')
            : U.badge('JOINT CLOSED', sfKind(sf.separation_factor_n0),
                'Separation factor n₀ = ' + U.fmt(sf.separation_factor_n0, 2));
        badges += U.badge(
            (bolt.count || '—') + ' × ' + (bolt.size || '—') + ' class '
            + (bolt.property_class || '—'), 'info', bolt.strength_source || '');
        badges += U.badge('MODEL: SHIGLEY CH. 8', 'info', j.source || '');

        var scatter = Array.isArray(tq.preload_scatter_band_N)
            ? tq.preload_scatter_band_N : [null, null];

        var head = document.createElement('div');
        head.innerHTML = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + badges + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard('Recommended torque', U.fmt(tq.recommended_torque_Nm, 1), 'N·m',
                'info', 'T = K·F_i·d, K = ' + U.fmt(tq.K_nut_factor, 2)
                + ' (' + (tq.condition || '—') + ')')
            + U.statCard('Preload F_i', fmtKN(pre.preload_N), 'kN', null,
                pre.basis || '')
            + U.statCard('Preload scatter ±' + U.fmt(tq.preload_uncertainty_pct, 0) + '%',
                fmtKN(scatter[0]) + ' – ' + fmtKN(scatter[1]), 'kN', 'warn',
                'Torque-controlled tightening scatter band (Shigley Sec. 8-8)')
            + U.statCard('Proof SF', U.fmt(sf.proof_SF, 2), '', sfKind(sf.proof_SF, 1.2),
                'S_p·A_t / F_bolt (Shigley Eq. 8-28)')
            + U.statCard('Overload factor n_L', U.fmt(sf.overload_factor_nL, 2), '',
                sfKind(sf.overload_factor_nL, 1.2), 'Shigley Eq. 8-29')
            + U.statCard('Separation factor n₀', U.fmt(sf.separation_factor_n0, 2), '',
                sfKind(sf.separation_factor_n0), 'F_i / (P·(1−C)) — Shigley Eq. 8-30')
            + '</div>';
        root.appendChild(head);

        // ---- Tablolar ----
        var tail = document.createElement('div');
        var html = U.sectionTitle('Load Sharing');
        html += U.kvTable([
            ['Pressure load basis', (loads.pressure_bar == null ? '—'
                : U.fmt(loads.pressure_bar, 1) + ' bar on seal area')],
            ['Total external load', fmtKN(loads.total_external_load_N) + ' kN'],
            ['External load per bolt', fmtKN(loads.external_load_per_bolt_N) + ' kN'],
            ['Bolt total load F_b', fmtKN(loads.bolt_total_load_N) + ' kN',
             'F_b = F_i + C·P (Shigley Eq. 8-24)'],
            ['Member clamp load F_m', fmtKN(loads.member_clamp_load_N) + ' kN',
             'F_m = F_i − (1−C)·P (Shigley Eq. 8-25) — ≤ 0 means separation'],
            ['Joint constant C', U.fmt(st.joint_constant_C, 3),
             st.model || ''],
            ['Separation load per bolt', fmtKN(sep.separation_load_per_bolt_N) + ' kN'],
        ]);

        html += U.sectionTitle('Bolt Data');
        html += U.kvTable([
            ['Stress area A_t', U.fmt(bolt.stress_area_mm2, 1) + ' mm²',
             'ISO 898-1:2013 Table A.1 (coarse thread)'],
            ['Proof / yield / ultimate', U.fmt(bolt.proof_strength_MPa, 0) + ' / '
                + U.fmt(bolt.yield_strength_MPa, 0) + ' / '
                + U.fmt(bolt.ultimate_strength_MPa, 0) + ' MPa',
             bolt.strength_source || ''],
            ['Proof load F_p', fmtKN(pre.proof_load_N) + ' kN'],
            ['Member material', st.member_material || '—'],
        ]);

        html += U.listBlock('Warnings', j.warnings, 'warn');
        html += U.listBlock('Assumptions', j.assumptions, 'dim');
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    window.AnalysisDock.register({
        id: 'joint',
        title: 'Bolted Joint — Preload, Torque & Separation (Shigley)',
        category: 'STRUCTURAL',
        endpoint: '/api/bolted-joint',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['pressure_bar', 'Chamber Pressure (bar)', 40, 1],
            ['seal_diameter_mm', 'Seal / Effective Diameter (mm)', 100, 1],
            ['bolt_count', 'Bolt Count', 8, 1],
            ['size', 'Bolt Size', 'M8', SIZES],
            ['property_class', 'Property Class', '8.8', CLASSES],
            ['grip_length_mm', 'Grip Length (mm)', 20, 1],
            ['member_material', 'Member Material', 'aluminum_6061', MEMBER_MATERIALS],
            ['lubricated', 'Thread Condition', 'false', LUBRICATION],
            ['reusable', 'Connection Type', 'true', REUSE],
            ['external_axial_load_n', 'Extra Axial Load (N, optional)', '', 100],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            if (Number.isFinite(m.chamber_pressure)) {
                out.pressure_bar = m.chamber_pressure;
            }
            // Sızdırmazlık çapı önerisi: hazne iç çapı (O-ring yüz contası)
            if (Number.isFinite(m.chamber_diameter)) {
                out.seal_diameter_mm = m.chamber_diameter * 1000.0;
            }
            return out;
        },
        render: render,
    });

    // Test / hata ayıklama: saf render (dry-run)
    window.JointPanel = { _render: render };
})();
