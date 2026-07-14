/* ====================================================================
   HRMA Analiz Güvertesi — Kapsamlı Güvenlik Paneli
   --------------------------------------------------------------------
   POST /analyze_safety sonucunu çizer:
   - risk_assessment: bireysel riskler (1-5) + azaltım öncelik sırası
   - Basınçlı kap özeti (işletme/tasarım/proof/hidrostatik/burst hedefi)
   - 5x5 risk matrisi: data-attribute'lu basit grid (hd-riskmatrix
     sınıfları — HUD CSS katmanı görünümü devralacak, inline stiller
     yalnız CSS gelmeden önce okunabilirlik için)
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;

    // Anahtarlar safety_analysis.py sözlükleriyle birebir
    const PROPELLANTS = [
        ['composite', 'Composite (APCP/HTPB)'],
        ['double_base', 'Double base (NC/NG)'],
        ['composite_db', 'Composite double base'],
        ['liquid_biprop', 'Liquid bipropellant'],
        ['liquid_monoprop', 'Liquid monopropellant'],
        ['solid_monoprop', 'Solid monopropellant (AP)'],
    ];
    const FACILITIES = [
        ['test_stand', 'Test stand'],
        ['manufacturing', 'Manufacturing'],
        ['transport', 'Transport'],
        ['launch', 'Launch site'],
    ];
    const MOTOR_TYPES = [
        ['hybrid', 'Hybrid'],
        ['liquid', 'Liquid'],
        ['solid', 'Solid'],
    ];

    const AREA_LABELS = {
        structural: 'Structural', pressure: 'Pressure', thermal: 'Thermal',
        explosive: 'Explosive', toxic: 'Toxic', fire: 'Fire',
    };
    const AREA_SHORT = {
        structural: 'STRUCT', pressure: 'PRESS', thermal: 'THERM',
        explosive: 'EXPL', toxic: 'TOX', fire: 'FIRE',
    };

    // Skor bandı — safety_analysis.py eşikleri (<=2 LOW, <=3 MEDIUM,
    // <=4 HIGH, >4 CRITICAL) ile aynı
    function scoreBand(score) {
        if (score == null || !Number.isFinite(score)) return 'unknown';
        if (score <= 2.0) return 'low';
        if (score <= 3.0) return 'medium';
        if (score <= 4.0) return 'high';
        return 'critical';
    }

    function bandKind(band) {
        return { low: 'ok', medium: 'warn', high: 'err', critical: 'err' }[band] || 'info';
    }

    const BAND_BG = {
        low: 'rgba(45, 212, 168, 0.12)',
        medium: 'rgba(255, 140, 51, 0.12)',
        high: 'rgba(255, 93, 115, 0.14)',
        critical: 'rgba(255, 93, 115, 0.32)',
    };

    function riskLevelKind(level) {
        const t = String(level || '').toUpperCase();
        if (t === 'LOW') return 'ok';
        if (t === 'MEDIUM') return 'warn';
        return 'err';
    }

    function scoreCell(score) {
        const c = U.kindColor(bandKind(scoreBand(score)));
        return `<span style="color:${c}; font-family:var(--hd-mono);">${U.fmt(score, 1)} / 5</span>`;
    }

    // ------------------------------------------------------------------
    // 5x5 risk matrisi — data-attribute'lu grid. Tek skorlu (1-5)
    // değerlendirme köşegen hücreye yerleştirilir (olabilirlik ve şiddet
    // ayrı raporlanmadığı için skor her iki eksene de eşlenir).
    // ------------------------------------------------------------------
    function riskMatrixHtml(risk) {
        const rm = risk.risk_matrix || {};
        const axes = rm.axes || {};
        const likelihood = axes.likelihood
            || ['Rare', 'Unlikely', 'Possible', 'Likely', 'Frequent'];
        const severity = axes.severity
            || ['Negligible', 'Minor', 'Major', 'Critical', 'Catastrophic'];
        const risks = risk.individual_risks || {};

        // Hücre → köşegen chip eşlemesi
        const chips = {};
        Object.keys(risks).forEach(function (area) {
            const s = risks[area];
            if (typeof s !== 'number' || !Number.isFinite(s)) return;
            const idx = Math.min(5, Math.max(1, Math.round(s)));
            const key = idx + ':' + idx;
            (chips[key] = chips[key] || []).push(area);
        });

        const cellBase = 'min-height:52px; border-radius:4px; padding:4px 6px;'
            + ' display:flex; flex-wrap:wrap; gap:3px; align-items:flex-start;'
            + ' border:1px solid var(--hd-line, rgba(0,229,255,0.14));';
        const axisStyle = 'font-family:var(--hd-mono); font-size:0.62rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); text-transform:uppercase;'
            + ' letter-spacing:0.06em; align-self:center; padding:2px 6px;';

        let html = `<div class="hd-riskmatrix" data-rows="5" data-cols="5"
            style="display:grid; grid-template-columns:auto repeat(5, 1fr); gap:2px;
            margin:10px 0; max-width:760px;">`;

        // Satırlar: olabilirlik 5 (üst) → 1 (alt)
        for (let li = 5; li >= 1; li--) {
            html += `<div class="hd-rm-axis" data-axis="likelihood" data-index="${li}"
                style="${axisStyle} text-align:right;">${likelihood[li - 1] || li}</div>`;
            for (let si = 1; si <= 5; si++) {
                // Hücre bandı: ortalama skor (l+s)/2, backend eşikleri
                const band = scoreBand((li + si) / 2);
                const key = li + ':' + si;
                const cellChips = (chips[key] || []).map(function (area) {
                    return `<span class="hd-rm-chip" data-risk="${area}"
                        title="${AREA_LABELS[area] || area}: score ${U.fmt(risks[area], 1)} / 5"
                        style="font-family:var(--hd-mono); font-size:0.6rem;
                        border:1px solid var(--hd-ink-dim, #7d97a5); border-radius:4px;
                        padding:1px 5px; color:var(--hd-ink, #cfe8f2);
                        background:var(--hd-inset, rgba(6,14,26,0.85));">${AREA_SHORT[area] || area}</span>`;
                }).join('');
                html += `<div class="hd-rm-cell" data-likelihood="${li}" data-severity="${si}"
                    data-band="${band}" data-risks="${(chips[key] || []).join(',')}"
                    style="${cellBase} background:${BAND_BG[band]};">${cellChips}</div>`;
            }
        }
        // Alt eksen: şiddet başlıkları
        html += `<div class="hd-rm-corner" style="${axisStyle}"></div>`;
        for (let si = 1; si <= 5; si++) {
            html += `<div class="hd-rm-axis" data-axis="severity" data-index="${si}"
                style="${axisStyle} text-align:center;">${severity[si - 1] || si}</div>`;
        }
        html += '</div>';
        html += `<p style="font-size:0.68rem; color:var(--hd-ink-faint, #46606d);
            font-family:var(--hd-mono); margin:4px 0 10px;">
            Rows: likelihood · Columns: severity · Single-score risks are placed on
            the diagonal (score maps to both axes).</p>`;
        return html;
    }

    function priorityTable(risk) {
        const pri = risk.mitigation_priority || [];
        if (!pri.length) return '';
        let html = `<table style="${U.TBL}">
            <thead><tr>
                <th style="${U.TD} text-align:left;">Priority</th>
                <th style="${U.TD} text-align:left;">Risk Area</th>
                <th style="${U.TD}">Score</th>
            </tr></thead><tbody>`;
        pri.forEach(function (p) {
            html += `<tr>
                <td style="${U.TD} font-family:var(--hd-mono);">#${p.priority}</td>
                <td style="${U.TD}"><strong>${AREA_LABELS[p.area] || p.area}</strong></td>
                <td style="${U.TD} text-align:center;">${scoreCell(p.risk_score)}</td>
            </tr>`;
        });
        return html + '</tbody></table>';
    }

    function pressureVesselBlock(press) {
        if (!press || !Object.keys(press).length) return '';
        let html = U.sectionTitle('Pressure Vessel Summary');
        html += `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard('Operating', U.fmt(press.operating_pressure_bar, 1), 'bar')
            + U.statCard('Design', U.fmt(press.design_pressure_bar, 1), 'bar')
            + U.statCard('Proof test', U.fmt(press.proof_pressure_bar, 1), 'bar')
            + U.statCard('Hydrostatic test', U.fmt(press.hydrostatic_test_pressure_bar, 1), 'bar')
            + U.statCard('Burst target', U.fmt(press.required_burst_pressure_bar, 1), 'bar', 'warn',
                'Minimum required burst pressure')
            + '</div>';
        const rows = [];
        if (press.vessel_classification) {
            rows.push(['Vessel classification',
                U.badge(String(press.vessel_classification).replace(/_/g, ' '), 'info')]);
        }
        if (press.inspection_requirements) {
            rows.push(['Inspection', press.inspection_requirements]);
        }
        if (press.applicable_codes && press.applicable_codes.length) {
            rows.push(['Applicable codes', press.applicable_codes.join(' · ')]);
        }
        if (press.safety_devices_required && press.safety_devices_required.length) {
            rows.push(['Required safety devices', press.safety_devices_required.join(' · ')]);
        }
        if (rows.length) html += U.kvTable(rows);
        return html;
    }

    function complianceBadges(comp) {
        if (!comp || !Object.keys(comp).length) return '';
        let badges = '';
        const boolBadge = function (label, ok) {
            if (ok == null) return '';
            return U.badge(label + (ok ? ': OK' : ': FAIL'), ok ? 'ok' : 'err');
        };
        badges += boolBadge('NFPA', comp.nfpa_compliance);
        badges += boolBadge('OSHA', comp.osha_compliance);
        badges += boolBadge('DOT', comp.dot_compliance);
        if (comp.insurance_requirements === 'REQUIRES_REVIEW') {
            badges += U.badge('INSURANCE: REVIEW', 'warn');
        }
        if (comp.local_regulations === 'REQUIRES_REVIEW') {
            badges += U.badge('LOCAL REGS: REVIEW', 'warn');
        }
        if (!badges) return '';
        return U.sectionTitle('Compliance')
            + `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;
    }

    function render(data, root) {
        const s = data.safety_analysis || {};
        const risk = s.risk_assessment || {};
        const risks = risk.individual_risks || {};

        // ---- Üst rozetler ----
        let badges = '';
        if (risk.risk_level) {
            badges += U.badge('OVERALL RISK: ' + risk.risk_level, riskLevelKind(risk.risk_level),
                'Weighted overall score ' + U.fmt(risk.overall_risk_score, 2) + ' / 5');
        }
        if (risk.acceptability) {
            const acc = String(risk.acceptability);
            badges += U.badge(acc.replace(/_/g, ' '),
                acc === 'ACCEPTABLE' ? 'ok'
                    : acc === 'ACCEPTABLE_WITH_CONTROLS' ? 'warn' : 'err');
        }
        if (risk.overall_risk_score != null) {
            badges += U.badge('SCORE: ' + U.fmt(risk.overall_risk_score, 2) + ' / 5',
                bandKind(scoreBand(risk.overall_risk_score)));
        }
        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;

        // ---- Bireysel riskler ----
        html += U.sectionTitle('Individual Risks (1 = lowest, 5 = highest)');
        html += U.kvTable(Object.keys(AREA_LABELS)
            .filter(function (a) { return risks[a] != null; })
            .map(function (a) { return [AREA_LABELS[a], scoreCell(risks[a])]; }));

        // ---- Azaltım öncelikleri ----
        const pt = priorityTable(risk);
        if (pt) {
            html += U.sectionTitle('Mitigation Priority');
            html += pt;
        }

        // ---- 5x5 risk matrisi ----
        html += U.sectionTitle('Risk Matrix (5×5)');
        html += riskMatrixHtml(risk);

        // ---- Basınçlı kap özeti ----
        html += pressureVesselBlock(s.pressure_safety);

        // ---- Uyum rozetleri ----
        html += complianceBadges(s.compliance);

        // ---- Öneriler ----
        html += U.listBlock('Recommendations', s.recommendations, 'info');

        root.innerHTML = html;
    }

    window.AnalysisDock.register({
        id: 'safety',
        title: 'Comprehensive Safety — Risk Assessment & Pressure Vessel',
        category: 'SAFETY',
        endpoint: '/analyze_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['motor_type', 'Motor Type', 'hybrid', MOTOR_TYPES],
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1],
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 10],
            ['thrust', 'Thrust (N)', 1000, 50],
            ['burn_time', 'Burn Time (s)', 10, 0.5],
            ['propellant_mass', 'Propellant Mass (kg)', 5, 0.5],
            ['propellant_type', 'Propellant Type', 'composite', PROPELLANTS],
            ['facility_type', 'Facility Type', 'test_stand', FACILITIES],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005],
            ['wall_thickness', 'Wall Thickness (m)', 0.005, 0.001],
        ],
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const motorType = window.AnalysisDock.getMotorType();
            const sug = {
                motor_type: motorType,
                chamber_pressure: m.chamber_pressure,
                chamber_temperature: m.chamber_temperature,
                thrust: m.thrust,
                burn_time: m.burn_time,
                chamber_diameter: m.chamber_diameter,
                // Sıvı motorda çift itergaç, katı/hibritte kompozit varsayılanı
                propellant_type: motorType === 'liquid' ? 'liquid_biprop' : 'composite',
            };
            // Toplam itergaç kütlesi = kütle debisi × yanma süresi
            if (Number.isFinite(m.mdot_total) && Number.isFinite(m.burn_time)) {
                sug.propellant_mass = m.mdot_total * m.burn_time;
            }
            return sug;
        },
        render: render,
    });

    // Test / hata ayıklama: saf render (dry-run)
    window.SafetyPanel = { _render: render };
})();
