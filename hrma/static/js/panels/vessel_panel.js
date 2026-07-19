/* ====================================================================
   HRMA Analiz Güvertesi — Basınçlı Kap Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/pressure-vessel-analysis sonucunu çizer:
   - Kod modu seçici: AIAA S-080 (uçuş) / ASME VIII Div 1 (yer)
   - Başlık metriği: actual_burst_pressure_bar — "bu tank kaç barda patlar"
   - Kartlar: gerekli kalınlık, MAWP, proof, hidrostatik test, burst
   - burst_margin PASS/MARGINAL/FAIL rozeti (status alanından)
   - Başlık (head) kalınlıkları tablosu, derating, warnings/assumptions
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   Backend: hrma/analysis/pressure_vessel.py (ASME VIII UG-27/UG-32,
   AIAA S-080A-2018, Faupel 1956 burst).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    var U = window.AnalysisDock.ui;
    var T = U.t;                         // çeviri kısayolu

    // FALLBACK listesi — /api/materials kataloğu yüklenemezse kullanılır
    // (materials_db kanonik anahtarları; katalog gelirse 'shell' etiketli
    // tam liste bunun yerine geçer)
    var MATERIALS = [
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['steel_4130', 'Steel AISI 4130'],
        ['steel', 'Steel (generic)'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['inconel_718', 'Inconel 718'],
    ];

    var CODE_MODES = [
        ['aiaa_s080', 'AIAA S-080 (flight hardware)', 'vessel.codeAiaa'],
        ['asme_viii', 'ASME VIII Div 1 (ground/test)', 'vessel.codeAsme'],
    ];

    var WELD_EFF = [
        ['1.00', '1.00 — full radiography', 'vessel.weldFull'],
        ['0.85', '0.85 — spot radiography', 'vessel.weldSpot'],
        ['0.70', '0.70 — no radiography', 'vessel.weldNone'],
    ];

    var HEAD_TYPES = [
        ['ellipsoidal_2_1', '2:1 Ellipsoidal', 'vessel.headEllipsoidal'],
        ['torispherical', 'Torispherical', 'vessel.headTorispherical'],
        ['hemispherical', 'Hemispherical', 'vessel.headHemispherical'],
    ];

    function statusKind(status) {
        var s = String(status || '').toUpperCase();
        if (s === 'PASS') return 'ok';
        if (s === 'MARGINAL') return 'warn';
        if (s === 'FAIL') return 'err';
        return 'info';
    }

    function marginKind(m) {
        if (m == null || !Number.isFinite(m)) return 'dim';
        if (m < 1.0) return 'err';
        if (m < 1.2) return 'warn';   // pressure_vessel.py MARGINAL eşiği
        return 'ok';
    }

    function render(data, root) {
        var d = data || {};
        var inputs = d.inputs || {};
        var der = d.derating || {};
        var heads = d.head_thicknesses_mm || {};

        // ---- Rozetler ----
        var badges = U.badge(T('common.statusUpper', 'STATUS') + ': ' + (d.status || '—'),
            statusKind(d.status),
            T('panel.vessel.statusTip',
              'PASS: all code checks met. MARGINAL: burst margin < 1.2. '
              + 'FAIL: burst margin < 1, wall below required, or over max service temperature.'));
        badges += U.badge(T('panel.vessel.codeBadge', 'CODE') + ': ' + (d.code_mode === 'asme_viii'
            ? 'ASME VIII Div 1' : 'AIAA S-080'), 'info');
        badges += U.badge(d.material_name || d.material || T('common.material', 'MATERIAL'), 'info');
        if (d.auto_sized) {
            badges += U.badge(T('panel.vessel.autoSized', 'AUTO-SIZED WALL'), 'warn',
                T('panel.vessel.autoSizedTip',
                  'No wall thickness supplied — sized to the code-required minimum.'));
        }

        var head = document.createElement('div');
        head.innerHTML = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + badges + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.vessel.cardBurst', 'Predicted burst pressure'),
                U.fmt(d.actual_burst_pressure_bar, 1), 'bar', marginKind(d.burst_margin),
                T('panel.vessel.cardBurstTip',
                  'min(Faupel thick-wall, thin-wall plastic limit) — the pressure at which '
                  + 'this vessel is predicted to rupture'))
            + U.statCard(T('panel.vessel.cardMargin', 'Burst margin'), U.fmt(d.burst_margin, 2),
                T('panel.vessel.timesRequired', '× required'), marginKind(d.burst_margin),
                U.tf('panel.vessel.cardMarginTip', { req: U.fmt(d.required_burst_pressure_bar, 1) },
                     'Predicted burst / required burst ({req} bar)'))
            + U.statCard(T('panel.vessel.cardReqThk', 'Required thickness'),
                U.fmt(d.required_thickness_mm, 2), 'mm', null,
                T('panel.vessel.cardReqThkTip', 'Code-required minimum wall thickness'))
            + U.statCard(T('panel.vessel.cardWallUsed', 'Wall used'),
                U.fmt(d.wall_thickness_used_mm, 2), 'mm',
                (Number.isFinite(d.thickness_margin) && d.thickness_margin < 1.0)
                    ? 'err' : 'ok',
                U.tf('panel.vessel.cardWallUsedTip', { m: U.fmt(d.thickness_margin, 2) },
                     'Thickness margin: {m}× required'))
            + U.statCard('MAWP', U.fmt(d.mawp_bar, 1), 'bar',
                (Number.isFinite(d.mawp_bar) && Number.isFinite(inputs.meop_bar)
                    && d.mawp_bar < inputs.meop_bar) ? 'err' : 'ok',
                T('panel.vessel.mawpTip', 'Maximum allowable working pressure with the wall used'))
            + '</div>';
        root.appendChild(head);

        // ---- Basınç merdiveni ----
        var mid = document.createElement('div');
        var html = U.sectionTitle(T('panel.vessel.secLadder', 'Pressure Ladder'));
        html += U.kvTable([
            [T('panel.vessel.meopInput', 'MEOP (input)'), U.fmt(inputs.meop_bar, 1) + ' bar'],
            [T('panel.vessel.proofPressure', 'Proof pressure (1.5 × MEOP)'),
             U.fmt(d.proof_pressure_bar, 1) + ' bar',
             T('panel.vessel.proofTip', 'AIAA S-080 proof factor')],
            [T('panel.vessel.hydroTest', 'Hydrostatic test (UG-99b)'),
             U.fmt(d.hydrostatic_test_pressure_bar, 1) + ' bar',
             '1.3 × MAWP × (S_test / S_design)'],
            [T('panel.vessel.requiredBurst', 'Required burst'),
             U.fmt(d.required_burst_pressure_bar, 1) + ' bar',
             d.code_mode === 'asme_viii'
                 ? T('panel.vessel.burstFactorAsme',
                     '3.5 × MEOP (Div 1 UTS margin interpretation — approximate)')
                 : T('panel.vessel.burstFactorAiaa', '2.0 × MEOP (AIAA S-080 burst factor)')],
            [T('panel.vessel.burstFaupel', 'Burst — Faupel thick-wall'),
             U.fmt(d.burst_faupel_bar, 1) + ' bar', 'Faupel (1956), Trans. ASME Vol. 78'],
            [T('panel.vessel.burstThin', 'Burst — thin-wall plastic limit'),
             U.fmt(d.burst_thin_wall_bar, 1) + ' bar',
             T('panel.vessel.burstThinTip', 'P_b = 2·UTS·t/(D+t) — approximate')],
            [T('panel.vessel.allowableStress', 'Allowable stress S'),
             U.fmt(d.allowable_stress_MPa, 1) + ' MPa',
             T('panel.vessel.allowableTip', 'min(UTS/3.5, YS/1.5) — ASME Section II-D criteria')],
        ]);

        // ---- Başlık (head) kalınlıkları ----
        html += U.sectionTitle(T('panel.vessel.secHeads', 'Head Thicknesses (ASME UG-32 geometry)'));
        html += U.kvTable(HEAD_TYPES.map(function (h) {
            var mark = (h[0] === d.head_type) ? ' — ' + T('common.selected', 'selected') : '';
            return [T(h[2], h[1]) + mark, U.fmt(heads[h[0]], 2) + ' mm'];
        }));

        // ---- Sıcaklık derating'i ----
        if (der && Number.isFinite(der.strength_retention_factor)) {
            html += U.sectionTitle(T('panel.vessel.secDerating', 'Temperature Derating'));
            html += U.kvTable([
                [T('panel.vessel.designTemp', 'Design temperature'), U.fmt(der.temperature_K, 0) + ' K ('
                    + U.fmt(der.temperature_C, 0) + ' °C)'],
                [T('panel.vessel.retention', 'Strength retention'),
                 U.fmt(der.strength_retention_factor * 100, 0) + ' %',
                 T('panel.vessel.retentionTip', 'MMPDS-style retention curve from materials_db')],
                [T('panel.vessel.derated', 'Derated yield / ultimate'),
                 U.fmt(der.derated_yield_strength_Pa / 1e6, 0) + ' / '
                    + U.fmt(der.derated_ultimate_strength_Pa / 1e6, 0) + ' MPa'],
            ]);
        }

        html += U.listBlock(T('common.warnings', 'Warnings'), d.warnings, 'warn');
        html += U.listBlock(T('common.assumptions', 'Assumptions'), d.assumptions, 'dim');
        mid.innerHTML = html;
        root.appendChild(mid);
    }

    window.AnalysisDock.register({
        id: 'vessel',
        title: 'Pressure Vessel — Sizing, MAWP & Real Burst Pressure',
        titleKey: 'panel.vessel.title',
        category: 'PRESSURE VESSEL',
        endpoint: '/api/pressure-vessel-analysis',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['code_mode', 'Design Code', 'aiaa_s080', CODE_MODES, 'panel.vessel.fDesignCode'],
            ['meop_bar', 'MEOP (bar)', 60, 1, 'panel.vessel.fMeop'],
            ['inner_diameter_mm', 'Inner Diameter (mm)', 150, 1, 'common.f.innerDiameterMm'],
            ['wall_thickness_mm', 'Wall Thickness (mm, blank = auto-size)', '', 0.1,
             'panel.vessel.fWallAuto'],
            ['material', 'Material', 'aluminum_6061', MATERIALS, 'common.f.material'],
            ['temperature_K', 'Design Temperature (K)', 293.15, 5, 'common.f.designTemperatureK'],
            ['weld_efficiency', 'Weld Joint Efficiency (UW-12)', '1.00', WELD_EFF,
             'panel.vessel.fWeld'],
            ['head_type', 'Head Type', 'ellipsoidal_2_1', HEAD_TYPES, 'panel.vessel.fHeadType'],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            // MEOP = hazne basıncı (bar) — plan Dalga 3 fromResults eşlemesi
            if (Number.isFinite(m.chamber_pressure)) {
                out.meop_bar = m.chamber_pressure;
            }
            if (Number.isFinite(m.chamber_diameter)) {
                out.inner_diameter_mm = m.chamber_diameter * 1000.0;
            }
            return out;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse select'i 'shell' etiketli tam listeyle
    // doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'vessel', fieldId: 'material',
            tags: ['shell'], fallback: MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render (dry-run)
    window.VesselPanel = { _render: render };
})();
