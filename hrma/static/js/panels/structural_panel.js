/* ====================================================================
   HRMA Analiz Güvertesi — Yapısal Güvenlik Paneli
   --------------------------------------------------------------------
   POST /analyze_structural_safety sonucunu çizer:
   - von Mises / hoop / termal gerilme (MPa) tablosu
   - SF_pressure + SF_total ayrı satırlar (backend alanı yoksa mevcut
     hoop / von Mises emniyet katsayılarına düşer)
   - Burkulma SAFE/MARGINAL/CRITICAL rozeti (NASA SP-8007 kaynaklı)
   - Yorulma, cıvata ve kapak özetleri
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;

    // Malzeme anahtarları structural_analysis.py self.materials ile birebir
    const MATERIALS = [
        ['steel_4130', 'Steel AISI 4130'],
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['inconel_718', 'Inconel 718'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
    ];

    function statusKind(s) {
        // structural_analysis.py sözlüğü: SAFE/ACCEPTABLE → ok,
        // MARGINAL → warn, UNSAFE/CRITICAL → err
        const t = String(s || '').toUpperCase();
        if (t === 'SAFE' || t === 'ACCEPTABLE') return 'ok';
        if (t === 'MARGINAL') return 'warn';
        if (t === 'UNSAFE' || t === 'CRITICAL') return 'err';
        return 'info';
    }

    // SF renk eşiği: <1 kırmızı (akma aşıldı), < gerekli-SF turuncu,
    // aksi yeşil. Gerekli SF backend malzeme kartından okunur.
    function sfKind(sf, required) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        if (sf < 1.0) return 'err';
        if (required != null && sf < required) return 'warn';
        return 'ok';
    }

    function sfCell(sf, required) {
        const c = U.kindColor(sfKind(sf, required));
        return `<span style="color:${c}; font-family:var(--hd-mono);">${U.fmt(sf)}</span>`;
    }

    function stressTable(ca, required) {
        const rows = [
            ['Von Mises (combined)', ca.von_mises_stress, ca.von_mises_safety_factor],
            ['Hoop (pressure)', U.pick(ca, ['pressure_hoop_stress', 'hoop_stress']),
             ca.hoop_safety_factor],
            ['Hoop (thermal)', ca.thermal_hoop_stress, null],
            ['Longitudinal (axial)', ca.longitudinal_stress, null],
        ];
        return `<table style="${U.TBL}">
            <thead><tr>
                <th style="${U.TD} text-align:left;">Stress Component</th>
                <th style="${U.TD}">Stress (MPa)</th>
                <th style="${U.TD}">Safety Factor</th>
            </tr></thead><tbody>` +
            rows.map(function (r) {
                return `<tr><td style="${U.TD}"><strong>${r[0]}</strong></td>
                    <td style="${U.TD} text-align:center; font-family:var(--hd-mono);">${U.fmt(r[1])}</td>
                    <td style="${U.TD} text-align:center;">${r[2] == null ? '—' : sfCell(r[2], required)}</td>
                </tr>`;
            }).join('') + '</tbody></table>';
    }

    function safetyFactorTable(ca, sf, required) {
        // SF_pressure / SF_total: backend ajanı bu alanları ekliyor;
        // henüz yoksa mevcut emniyet katsayılarına düş (görev sözleşmesi).
        const sfPressure = U.pick(ca, ['safety_factor_pressure', 'SF_pressure', 'sf_pressure'])
            || U.pick(sf, ['safety_factor_pressure', 'SF_pressure', 'sf_pressure'])
            || ca.hoop_safety_factor;
        const sfTotal = U.pick(ca, ['safety_factor_total', 'SF_total', 'sf_total'])
            || U.pick(sf, ['safety_factor_total', 'SF_total', 'sf_total'])
            || ca.von_mises_safety_factor;

        const rows = [
            ['SF (pressure only)', sfCell(sfPressure, required),
             'Pressure-only safety factor (hoop based when backend field is absent)'],
            ['SF (total, incl. thermal)', sfCell(sfTotal, required),
             'Combined safety factor (von Mises based when backend field is absent)'],
        ];
        if (sf && sf.minimum_safety_factor != null) {
            rows.push(['Minimum SF (all modes)', sfCell(sf.minimum_safety_factor, required)]);
        }
        const modes = (sf && sf.safety_factors) || {};
        const LABELS = {
            chamber_hoop: 'Chamber hoop',
            chamber_von_mises: 'Chamber von Mises',
            end_cap: 'End cap',
            nozzle: 'Nozzle throat',
            buckling_axial: 'Axial buckling',
        };
        Object.keys(modes).forEach(function (k) {
            rows.push(['&nbsp;&nbsp;· ' + (LABELS[k] || k), sfCell(modes[k], required)]);
        });
        if (required != null) {
            rows.push(['Required design SF (material)',
                `<span style="font-family:var(--hd-mono);">${U.fmt(required, 1)}</span>`]);
        }
        return U.kvTable(rows);
    }

    function render(data, root) {
        const sa = data.structural_analysis || {};
        const ca = sa.chamber_analysis || {};
        const sf = sa.safety_analysis || {};
        const buck = sa.buckling_analysis || {};
        const fat = sa.fatigue_analysis || {};
        const fast = sa.fastener_analysis || {};
        const cap = sa.end_cap_analysis || {};
        const mp = sa.material_properties || {};
        const dp = sa.design_parameters || {};
        const wt = sa.weight_analysis || {};
        const required = (typeof mp.safety_factor === 'number') ? mp.safety_factor : null;

        // ---- Rozetler ----
        let badges = '';
        const bstat = String(buck.buckling_status || 'UNKNOWN').toUpperCase();
        badges += U.badge('BUCKLING: ' + bstat, statusKind(bstat), buck.source || '');
        if (sf.status) {
            badges += U.badge('STRUCTURE: ' + sf.status, statusKind(sf.status),
                'Overall structural verdict (min SF = ' + U.fmt(sf.minimum_safety_factor) + ')');
        }
        if (sf.risk_level) {
            const rk = String(sf.risk_level).toUpperCase();
            badges += U.badge('RISK: ' + rk,
                rk.indexOf('LOW') !== -1 ? 'ok' : rk === 'MEDIUM' ? 'warn' : 'err');
        }
        if (fat.fatigue_status) {
            badges += U.badge('FATIGUE: ' + fat.fatigue_status, statusKind(fat.fatigue_status));
        }
        if (dp.material) {
            badges += U.badge('MATERIAL: ' + String(dp.material).toUpperCase(), 'info',
                'Design pressure ' + U.fmt(dp.design_pressure, 1) + ' bar (factor '
                + U.fmt(dp.design_pressure_factor, 2) + ')');
        }

        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;

        // ---- Gerilmeler ----
        html += U.sectionTitle('Wall Stresses');
        html += stressTable(ca, required);
        if (ca.governing_thermal_scenario) {
            html += `<p style="font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">
                Governing thermal scenario: <strong>${ca.governing_thermal_scenario}</strong>
                · yield strength used: ${U.fmt(ca.yield_strength_used_MPa, 0)} MPa
                · hoop model: ${ca.pressure_hoop_model || '—'}</p>`;
        }

        // ---- Emniyet katsayıları ----
        html += U.sectionTitle('Safety Factors');
        html += safetyFactorTable(ca, sf, required);

        // ---- Cidar kalınlığı ----
        if (ca.minimum_thickness != null || ca.recommended_thickness != null) {
            html += U.sectionTitle('Wall Thickness');
            html += U.kvTable([
                ['Minimum required', U.fmt(ca.minimum_thickness) + ' mm'],
                ['Recommended (with margin)', U.fmt(ca.recommended_thickness) + ' mm'],
            ]);
        }

        // ---- Burkulma ----
        html += U.sectionTitle('Buckling (NASA SP-8007)');
        html += U.kvTable([
            ['Applied axial stress', U.fmt(buck.applied_axial_stress_MPa) + ' MPa'],
            ['Critical buckling stress (knocked down)',
             U.fmt(buck.critical_axial_buckling_stress_MPa, 0) + ' MPa'],
            ['Buckling safety factor', sfCell(buck.axial_buckling_safety_factor, required)],
            ['Knockdown factor γ', U.fmt(buck.knockdown_factor_gamma, 3)],
            ['Critical external pressure', U.fmt(buck.critical_external_pressure_bar, 1) + ' bar'],
        ]);
        if (buck.source) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);">
                Source: ${buck.source}</p>`;
        }

        // ---- Yorulma ----
        html += U.sectionTitle('Fatigue');
        html += U.kvTable([
            ['Status', U.badge(fat.fatigue_status || '—', statusKind(fat.fatigue_status))],
            ['Estimated cycles (this duty)', fat.estimated_cycles != null ? fat.estimated_cycles : '—'],
            ['Estimated life', fat.estimated_life || '—'],
            ['Fatigue safety factor', U.fmt(fat.fatigue_safety_factor, 1)],
            ['Endurance limit', U.fmt(fat.fatigue_limit, 0) + ' MPa'],
        ]);

        // ---- Cıvata ve kapak ----
        html += U.sectionTitle('Fasteners & End Cap');
        html += U.kvTable([
            ['Bolts', (fast.num_bolts != null ? fast.num_bolts : '—') + ' × '
                + (fast.recommended_bolt_size || '—')],
            ['Bolt safety factor', sfCell(fast.bolt_safety_factor, null)],
            ['Force per bolt', U.fmt(fast.force_per_bolt) + ' kN (total '
                + U.fmt(fast.total_force) + ' kN)'],
            ['Bolt spacing', U.fmt(fast.bolt_spacing, 1) + ' mm'],
            ['End cap type', String(cap.recommended_type || '—').toUpperCase()],
            ['Head thickness (dished / flat)', U.fmt(cap.dished_head_thickness) + ' / '
                + U.fmt(cap.flat_head_thickness) + ' mm'],
            ['Head safety factor', sfCell(cap.head_safety_factor, required)],
        ]);
        if (fast.warning) {
            html += U.listBlock('Fastener Warning', [fast.warning], 'warn');
        }

        // ---- Kütle özeti ----
        if (wt.total_weight != null) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim, #7d97a5);">
                Estimated structure mass: <strong style="color:var(--hd-ink, #cfe8f2);">
                ${U.fmt(wt.total_weight)} kg</strong>
                (chamber ${U.fmt(wt.chamber_weight)} · nozzle ${U.fmt(wt.nozzle_weight)}
                · end caps ${U.fmt(wt.end_caps_weight)} kg)</p>`;
        }

        // ---- Öneriler ----
        html += U.listBlock('Recommendations', sf.recommendations, 'info');

        root.innerHTML = html;
    }

    window.AnalysisDock.register({
        id: 'structural',
        title: 'Structural Safety — Pressure Vessel, Buckling, Fatigue',
        category: 'STRUCTURAL',
        endpoint: '/analyze_structural_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01],
            ['throat_diameter', 'Throat Diameter (m)', 0.02, 0.001],
            ['burn_time', 'Burn Time (s)', 10, 0.5],
            ['chamber_temperature', 'Gas Temperature (K, 0 = skip thermal)', 0, 50],
            ['material', 'Material', 'steel_4130', MATERIALS],
        ],
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            return {
                chamber_pressure: m.chamber_pressure,
                chamber_diameter: m.chamber_diameter,
                chamber_length: m.chamber_length,
                throat_diameter: m.throat_diameter,
                burn_time: m.burn_time,
                chamber_temperature: m.chamber_temperature,
            };
        },
        render: render,
    });

    // Test / hata ayıklama: saf render (dry-run) — injector_panel deseni
    window.StructuralPanel = { _render: render };
})();
