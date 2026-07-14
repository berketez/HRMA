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

    // materials_db anahtarları (hrma/data/materials_db.py MATERIALS ile birebir)
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
        ['aiaa_s080', 'AIAA S-080 (flight hardware)'],
        ['asme_viii', 'ASME VIII Div 1 (ground/test)'],
    ];

    var WELD_EFF = [
        ['1.00', '1.00 — full radiography'],
        ['0.85', '0.85 — spot radiography'],
        ['0.70', '0.70 — no radiography'],
    ];

    var HEAD_TYPES = [
        ['ellipsoidal_2_1', '2:1 Ellipsoidal'],
        ['torispherical', 'Torispherical'],
        ['hemispherical', 'Hemispherical'],
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
        var badges = U.badge('STATUS: ' + (d.status || '—'), statusKind(d.status),
            'PASS: all code checks met. MARGINAL: burst margin < 1.2. '
            + 'FAIL: burst margin < 1, wall below required, or over max service temperature.');
        badges += U.badge('CODE: ' + (d.code_mode === 'asme_viii'
            ? 'ASME VIII Div 1' : 'AIAA S-080'), 'info');
        badges += U.badge(d.material_name || d.material || 'material', 'info');
        if (d.auto_sized) {
            badges += U.badge('AUTO-SIZED WALL', 'warn',
                'No wall thickness supplied — sized to the code-required minimum.');
        }

        var head = document.createElement('div');
        head.innerHTML = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + badges + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard('Predicted burst pressure', U.fmt(d.actual_burst_pressure_bar, 1),
                'bar', marginKind(d.burst_margin),
                'min(Faupel thick-wall, thin-wall plastic limit) — the pressure at which '
                + 'this vessel is predicted to rupture')
            + U.statCard('Burst margin', U.fmt(d.burst_margin, 2), '× required',
                marginKind(d.burst_margin),
                'Predicted burst / required burst ('
                + U.fmt(d.required_burst_pressure_bar, 1) + ' bar)')
            + U.statCard('Required thickness', U.fmt(d.required_thickness_mm, 2), 'mm', null,
                'Code-required minimum wall thickness')
            + U.statCard('Wall used', U.fmt(d.wall_thickness_used_mm, 2), 'mm',
                (Number.isFinite(d.thickness_margin) && d.thickness_margin < 1.0)
                    ? 'err' : 'ok',
                'Thickness margin: ' + U.fmt(d.thickness_margin, 2) + '× required')
            + U.statCard('MAWP', U.fmt(d.mawp_bar, 1), 'bar',
                (Number.isFinite(d.mawp_bar) && Number.isFinite(inputs.meop_bar)
                    && d.mawp_bar < inputs.meop_bar) ? 'err' : 'ok',
                'Maximum allowable working pressure with the wall used')
            + '</div>';
        root.appendChild(head);

        // ---- Basınç merdiveni ----
        var mid = document.createElement('div');
        var html = U.sectionTitle('Pressure Ladder');
        html += U.kvTable([
            ['MEOP (input)', U.fmt(inputs.meop_bar, 1) + ' bar'],
            ['Proof pressure (1.5 × MEOP)', U.fmt(d.proof_pressure_bar, 1) + ' bar',
             'AIAA S-080 proof factor'],
            ['Hydrostatic test (UG-99b)', U.fmt(d.hydrostatic_test_pressure_bar, 1) + ' bar',
             '1.3 × MAWP × (S_test / S_design)'],
            ['Required burst', U.fmt(d.required_burst_pressure_bar, 1) + ' bar',
             d.code_mode === 'asme_viii'
                 ? '3.5 × MEOP (Div 1 UTS margin interpretation — approximate)'
                 : '2.0 × MEOP (AIAA S-080 burst factor)'],
            ['Burst — Faupel thick-wall', U.fmt(d.burst_faupel_bar, 1) + ' bar',
             'Faupel (1956), Trans. ASME Vol. 78'],
            ['Burst — thin-wall plastic limit', U.fmt(d.burst_thin_wall_bar, 1) + ' bar',
             'P_b = 2·UTS·t/(D+t) — approximate'],
            ['Allowable stress S', U.fmt(d.allowable_stress_MPa, 1) + ' MPa',
             'min(UTS/3.5, YS/1.5) — ASME Section II-D criteria'],
        ]);

        // ---- Başlık (head) kalınlıkları ----
        html += U.sectionTitle('Head Thicknesses (ASME UG-32 geometry)');
        html += U.kvTable(HEAD_TYPES.map(function (h) {
            var mark = (h[0] === d.head_type) ? ' — selected' : '';
            return [h[1] + mark, U.fmt(heads[h[0]], 2) + ' mm'];
        }));

        // ---- Sıcaklık derating'i ----
        if (der && Number.isFinite(der.strength_retention_factor)) {
            html += U.sectionTitle('Temperature Derating');
            html += U.kvTable([
                ['Design temperature', U.fmt(der.temperature_K, 0) + ' K ('
                    + U.fmt(der.temperature_C, 0) + ' °C)'],
                ['Strength retention', U.fmt(der.strength_retention_factor * 100, 0) + ' %',
                 'MMPDS-style retention curve from materials_db'],
                ['Derated yield / ultimate',
                 U.fmt(der.derated_yield_strength_Pa / 1e6, 0) + ' / '
                    + U.fmt(der.derated_ultimate_strength_Pa / 1e6, 0) + ' MPa'],
            ]);
        }

        html += U.listBlock('Warnings', d.warnings, 'warn');
        html += U.listBlock('Assumptions', d.assumptions, 'dim');
        mid.innerHTML = html;
        root.appendChild(mid);
    }

    window.AnalysisDock.register({
        id: 'vessel',
        title: 'Pressure Vessel — Sizing, MAWP & Real Burst Pressure',
        category: 'PRESSURE VESSEL',
        endpoint: '/api/pressure-vessel-analysis',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['code_mode', 'Design Code', 'aiaa_s080', CODE_MODES],
            ['meop_bar', 'MEOP (bar)', 60, 1],
            ['inner_diameter_mm', 'Inner Diameter (mm)', 150, 1],
            ['wall_thickness_mm', 'Wall Thickness (mm, blank = auto-size)', '', 0.1],
            ['material', 'Material', 'aluminum_6061', MATERIALS],
            ['temperature_K', 'Design Temperature (K)', 293.15, 5],
            ['weld_efficiency', 'Weld Joint Efficiency (UW-12)', '1.00', WELD_EFF],
            ['head_type', 'Head Type', 'ellipsoidal_2_1', HEAD_TYPES],
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

    // Test / hata ayıklama: saf render (dry-run)
    window.VesselPanel = { _render: render };
})();
