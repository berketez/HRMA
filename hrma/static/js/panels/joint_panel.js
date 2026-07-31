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
    var T = U.t;                         // çeviri kısayolu

    // bolted_joint.py THREAD_STRESS_AREA_MM2 anahtarlarıyla birebir
    var SIZES = ['M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M14', 'M16',
                 'M18', 'M20', 'M22', 'M24'].map(function (s) { return [s, s]; });

    var CLASSES = [
        ['8.8', '8.8 (ISO 898-1)'],
        ['10.9', '10.9 (ISO 898-1)'],
        ['12.9', '12.9 (ISO 898-1)'],
        ['A2-70', 'A2-70 stainless (ISO 3506-1)', 'joint.classA270'],
    ];

    // FALLBACK listesi — /api/materials kataloğu yüklenemezse kullanılır
    // (sıkılan üye malzemesi; katalog gelirse 'bolt'+'structural' etiketli
    // tam liste bunun yerine geçer)
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
        ['false', 'Dry assembly (K = 0.20)', 'joint.dry'],
        ['true', 'Lubricated (K = 0.15)', 'joint.lubricated'],
    ];

    var REUSE = [
        ['true', 'Reusable — preload 75% of proof', 'joint.reusable'],
        ['false', 'Permanent — preload 90% of proof', 'joint.permanent'],
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
            ? U.badge(T('panel.joint.separated', 'JOINT SEPARATED'), 'err',
                T('panel.joint.separatedTip',
                  'External load exceeds the preload capacity — the joint opens'))
            : U.badge(T('panel.joint.closed', 'JOINT CLOSED'), sfKind(sf.separation_factor_n0),
                U.tf('panel.joint.n0Tip', { n0: U.fmt(sf.separation_factor_n0, 2) },
                     'Separation factor n0 = {n0}'));
        badges += U.badge(
            (bolt.count || '—') + ' × ' + (bolt.size || '—') + ' '
            + T('panel.joint.classWord', 'class') + ' '
            + (bolt.property_class || '—'), 'info', bolt.strength_source || '');
        badges += U.badge(T('panel.joint.model', 'MODEL: SHIGLEY CH. 8'), 'info', j.source || '');

        var scatter = Array.isArray(tq.preload_scatter_band_N)
            ? tq.preload_scatter_band_N : [null, null];

        var head = document.createElement('div');
        head.innerHTML = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + badges + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.joint.cardTorque', 'Recommended torque'),
                U.fmt(tq.recommended_torque_Nm, 1), 'N·m',
                'info', 'T = K·F_i·d, K = ' + U.fmt(tq.K_nut_factor, 2)
                + ' (' + (tq.condition || '—') + ')')
            + U.statCard(T('panel.joint.cardPreload', 'Preload F_i'), fmtKN(pre.preload_N), 'kN', null,
                pre.basis || '')
            + U.statCard(U.tf('panel.joint.cardScatter', { pct: U.fmt(tq.preload_uncertainty_pct, 0) },
                              'Preload scatter ±{pct}%'),
                fmtKN(scatter[0]) + ' – ' + fmtKN(scatter[1]), 'kN', 'warn',
                T('panel.joint.cardScatterTip',
                  'Torque-controlled tightening scatter band (Shigley Sec. 8-8)'))
            + U.statCard(T('panel.joint.cardProofSf', 'Proof SF'), U.fmt(sf.proof_SF, 2), '',
                sfKind(sf.proof_SF, 1.2), 'S_p·A_t / F_bolt (Shigley Eq. 8-28)')
            + U.statCard(T('panel.joint.cardOverload', 'Overload factor n_L'),
                U.fmt(sf.overload_factor_nL, 2), '',
                sfKind(sf.overload_factor_nL, 1.2), 'Shigley Eq. 8-29')
            + U.statCard(T('panel.joint.cardSeparation', 'Separation factor n0'),
                U.fmt(sf.separation_factor_n0, 2), '',
                sfKind(sf.separation_factor_n0), 'F_i / (P·(1−C)) — Shigley Eq. 8-30')
            + '</div>';
        root.appendChild(head);

        // ---- Tablolar ----
        var tail = document.createElement('div');
        var html = U.sectionTitle(T('panel.joint.secLoads', 'Load Sharing'));
        html += U.kvTable([
            [T('panel.joint.pressureBasis', 'Pressure load basis'), (loads.pressure_bar == null ? '—'
                : U.tf('panel.joint.pressureBasisValue', { p: U.fmt(loads.pressure_bar, 1) },
                       '{p} bar on seal area'))],
            [T('panel.joint.totalExternal', 'Total external load'),
             fmtKN(loads.total_external_load_N) + ' kN'],
            [T('panel.joint.externalPerBolt', 'External load per bolt'),
             fmtKN(loads.external_load_per_bolt_N) + ' kN'],
            [T('panel.joint.boltTotal', 'Bolt total load F_b'), fmtKN(loads.bolt_total_load_N) + ' kN',
             'F_b = F_i + C·P (Shigley Eq. 8-24)'],
            [T('panel.joint.memberClamp', 'Member clamp load F_m'),
             fmtKN(loads.member_clamp_load_N) + ' kN',
             T('panel.joint.memberClampTip',
               'F_m = F_i − (1−C)·P (Shigley Eq. 8-25) — ≤ 0 means separation')],
            [T('panel.joint.jointConstant', 'Joint constant C'), U.fmt(st.joint_constant_C, 3),
             st.model || ''],
            [T('panel.joint.separationLoad', 'Separation load per bolt'),
             fmtKN(sep.separation_load_per_bolt_N) + ' kN'],
        ]);

        html += U.sectionTitle(T('panel.joint.secBolt', 'Bolt Data'));
        html += U.kvTable([
            [T('panel.joint.stressArea', 'Stress area A_t'), U.fmt(bolt.stress_area_mm2, 1) + ' mm²',
             T('panel.joint.stressAreaTip', 'ISO 898-1:2013 Table A.1 (coarse thread)')],
            [T('panel.joint.proofYieldUts', 'Proof / yield / ultimate'),
             U.fmt(bolt.proof_strength_MPa, 0) + ' / '
                + U.fmt(bolt.yield_strength_MPa, 0) + ' / '
                + U.fmt(bolt.ultimate_strength_MPa, 0) + ' MPa',
             bolt.strength_source || ''],
            [T('panel.joint.proofLoad', 'Proof load F_p'), fmtKN(pre.proof_load_N) + ' kN'],
            [T('panel.joint.memberMaterial', 'Member material'), st.member_material || '—'],
        ]);

        html += U.listBlock(T('common.warnings', 'Warnings'), j.warnings, 'warn');
        html += U.listBlock(T('common.assumptions', 'Assumptions'), j.assumptions, 'dim');
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    window.AnalysisDock.register({
        id: 'joint',
        title: 'Bolted Joint — Preload, Torque & Separation (Shigley)',
        titleKey: 'panel.joint.title',
        category: 'STRUCTURAL',
        endpoint: '/api/bolted-joint',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['pressure_bar', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar'],
            ['seal_diameter_mm', 'Seal / Effective Diameter (mm)', 100, 1, 'panel.joint.fSealDiameter'],
            ['bolt_count', 'Bolt Count', 8, 1, 'panel.joint.fBoltCount'],
            ['size', 'Bolt Size', 'M8', SIZES, 'panel.joint.fBoltSize'],
            ['property_class', 'Property Class', '8.8', CLASSES, 'panel.joint.fPropertyClass'],
            ['grip_length_mm', 'Grip Length (mm)', 20, 1, 'panel.joint.fGripLength'],
            ['member_material', 'Member Material', 'aluminum_6061', MEMBER_MATERIALS,
             'panel.joint.fMemberMaterial'],
            ['lubricated', 'Thread Condition', 'false', LUBRICATION, 'panel.joint.fThreadCondition'],
            ['reusable', 'Connection Type', 'true', REUSE, 'panel.joint.fConnectionType'],
            ['external_axial_load_n', 'Extra Axial Load (N, optional)', '', 100,
             'panel.joint.fExtraAxial'],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            if (Number.isFinite(m.chamber_pressure)) {
                out.pressure_bar = m.chamber_pressure;
            }
            // Sızdırmazlık çapı önerisi: hazne iç çapı (O-ring yüz contası)
            // BİRİM (2026-07-30 ölçümü): koşulsuz `* 1000` yalnız hibritte
            // doğruydu; katı (75,0) ve sıvı (120,0) motorlarda değer zaten
            // MİLİMETRE geliyor ve panel 75 m / 120 m'lik conta çapıyla
            // cıvata hesabı yapıyordu.
            var sealMm = U.readLengthMM(r, 'chamber_diameter');
            if (Number.isFinite(sealMm)) {
                out.seal_diameter_mm = sealMm;
            }
            return out;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse üye malzemesi select'ini 'bolt'+'structural'
    // etiketli listeyle doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'joint', fieldId: 'member_material',
            tags: ['bolt', 'structural'], fallback: MEMBER_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render (dry-run)
    window.JointPanel = { _render: render };
})();
