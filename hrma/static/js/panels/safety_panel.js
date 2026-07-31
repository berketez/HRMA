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
    const T = U.t;                       // çeviri kısayolu

    // Anahtarlar safety_analysis.py sözlükleriyle birebir
    const PROPELLANTS = [
        ['composite', 'Composite (APCP/HTPB)', 'prop.composite'],
        ['double_base', 'Double base (NC/NG)', 'prop.doubleBase'],
        ['composite_db', 'Composite double base', 'prop.compositeDb'],
        ['liquid_biprop', 'Liquid bipropellant', 'prop.liquidBiprop'],
        ['liquid_monoprop', 'Liquid monopropellant', 'prop.liquidMonoprop'],
        ['solid_monoprop', 'Solid monopropellant (AP)', 'prop.solidMonoprop'],
    ];
    const FACILITIES = [
        ['test_stand', 'Test stand', 'fac.testStand'],
        ['manufacturing', 'Manufacturing', 'fac.manufacturing'],
        ['transport', 'Transport', 'fac.transport'],
        ['launch', 'Launch site', 'fac.launch'],
    ];
    const MOTOR_TYPES = [
        ['hybrid', 'Hybrid', 'motor.hybrid'],
        ['liquid', 'Liquid', 'motor.liquid'],
        ['solid', 'Solid', 'motor.solid'],
    ];
    // Hazne/gövde malzemesi — hesap ucu (app.py:4348) bu değeri okuyup
    // basınçlı kap emniyetini merkezi materials_db dayanımlarıyla
    // hesaplıyor. Panelde alan YOKTU: kullanıcı Inconel 718 seçmiş olsa
    // bile güvenlik hükmü daima steel_4130 ile üretiliyordu (uç bunu
    // `defaults_applied` içinde bildiriyor, panel ise okumuyordu).
    // Liste structural_panel.js ile birebir; katalog gelirse yerine geçer.
    const MATERIALS = [
        ['steel_4130', 'Steel AISI 4130'],
        ['steel_4340', 'Steel AISI 4340'],
        ['steel', 'Carbon steel (A36-class)'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['ss_17_4ph', 'Stainless 17-4PH (H900)'],
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['al_7075_t6', 'Aluminum 7075-T6'],
        ['al_2024_t3', 'Aluminum 2024-T3'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['ti_grade2_cp', 'Titanium CP Grade 2'],
        ['inconel_718', 'Inconel 718'],
        ['inconel_625', 'Inconel 625'],
        ['cucrzr', 'CuCrZr (C18150)'],
        ['beryllium_copper_c17200', 'Beryllium copper C17200'],
        ['magnesium_az31b', 'Magnesium AZ31B'],
    ];

    // Dil değişiminde tazelenmesi için render sırasında kurulur
    function areaLabels() {
        return {
            structural: T('risk.structural', 'Structural'),
            pressure: T('risk.pressure', 'Pressure'),
            thermal: T('risk.thermal', 'Thermal'),
            explosive: T('risk.explosive', 'Explosive'),
            toxic: T('risk.toxic', 'Toxic'),
            fire: T('risk.fire', 'Fire'),
        };
    }
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
        const likelihood = axes.likelihood || [
            T('risk.rare', 'Rare'), T('risk.unlikely', 'Unlikely'),
            T('risk.possible', 'Possible'), T('risk.likely', 'Likely'),
            T('risk.frequent', 'Frequent')];
        const severity = axes.severity || [
            T('risk.negligible', 'Negligible'), T('risk.minor', 'Minor'),
            T('risk.major', 'Major'), T('risk.critical', 'Critical'),
            T('risk.catastrophic', 'Catastrophic')];
        const LBL = areaLabels();
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
                        title="${LBL[area] || area}: ${T('common.score', 'score')} ${U.fmt(risks[area], 1)} / 5"
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
            font-family:var(--hd-mono); margin:4px 0 10px;">${
            T('panel.safety.matrixNote',
              'Rows: likelihood · Columns: severity · Single-score risks are placed on '
              + 'the diagonal (score maps to both axes).')}</p>`;
        return html;
    }

    function priorityTable(risk) {
        const pri = risk.mitigation_priority || [];
        if (!pri.length) return '';
        const LBL = areaLabels();
        let html = `<table style="${U.TBL}">
            <thead><tr>
                <th style="${U.TD} text-align:left;">${T('panel.safety.priority', 'Priority')}</th>
                <th style="${U.TD} text-align:left;">${T('panel.safety.riskArea', 'Risk Area')}</th>
                <th style="${U.TD}">${T('panel.safety.scoreCol', 'Score')}</th>
            </tr></thead><tbody>`;
        pri.forEach(function (p) {
            html += `<tr>
                <td style="${U.TD} font-family:var(--hd-mono);">#${p.priority}</td>
                <td style="${U.TD}"><strong>${LBL[p.area] || p.area}</strong></td>
                <td style="${U.TD} text-align:center;">${scoreCell(p.risk_score)}</td>
            </tr>`;
        });
        return html + '</tbody></table>';
    }

    function pressureVesselBlock(press) {
        if (!press || !Object.keys(press).length) return '';
        let html = U.sectionTitle(T('panel.safety.secVessel', 'Pressure Vessel Summary'));
        html += `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.safety.pOperating', 'Operating'),
                U.fmt(press.operating_pressure_bar, 1), 'bar')
            + U.statCard(T('panel.safety.pDesign', 'Design'),
                U.fmt(press.design_pressure_bar, 1), 'bar')
            + U.statCard(T('panel.safety.pProof', 'Proof test'),
                U.fmt(press.proof_pressure_bar, 1), 'bar')
            + U.statCard(T('panel.safety.pHydro', 'Hydrostatic test'),
                U.fmt(press.hydrostatic_test_pressure_bar, 1), 'bar')
            + U.statCard(T('panel.safety.pBurst', 'Burst target'),
                U.fmt(press.required_burst_pressure_bar, 1), 'bar', 'warn',
                T('panel.safety.pBurstTip', 'Minimum required burst pressure'))
            + '</div>';
        const rows = [];
        if (press.vessel_classification) {
            rows.push([T('panel.safety.vesselClass', 'Vessel classification'),
                U.badge(String(press.vessel_classification).replace(/_/g, ' '), 'info')]);
        }
        if (press.inspection_requirements) {
            rows.push([T('panel.safety.inspection', 'Inspection'), press.inspection_requirements]);
        }
        if (press.applicable_codes && press.applicable_codes.length) {
            rows.push([T('panel.safety.codes', 'Applicable codes'),
                       press.applicable_codes.join(' · ')]);
        }
        if (press.safety_devices_required && press.safety_devices_required.length) {
            // D-track: backend {code,params,severity} döndürür; ham join()
            // "[object Object] · [object Object]" basardı (v2.6.2 regresyonu).
            rows.push([T('panel.safety.devices', 'Required safety devices'),
                       press.safety_devices_required.map(U.warnText).join(' · ')]);
        }
        if (rows.length) html += U.kvTable(rows);
        return html;
    }

    // Mevzuat uygunluğu DEĞERLENDİRİLMİYOR.
    //
    // Eskiden burası backend'in koşulsuz True döndürdüğü alanları yeşil
    // "NFPA: OK / OSHA: OK / DOT: OK" rozetleri olarak çiziyordu. Motorun
    // büyüklüğü, iticisi ve kullanım yeri ne olursa olsun üçü de yeşildi;
    // backend'in kod yorumları ("Would check specific NFPA requirements")
    // gerçek bir kontrol yapılmadığını zaten söylüyordu. Bu, kullanıcıda
    // yanlış bir otorite algısı yaratıyordu.
    //
    // Gerçek uygunluk değerlendirmesi madde-madde requirement karşılaştırması,
    // saha bilgisi ve yetkili bir değerlendirici ister. Bunlar yazılıma girdi
    // olarak verilmediği sürece burada hüküm gösterilmez.
    function complianceBadges(comp) {
        if (!comp || !Object.keys(comp).length) return '';
        const note = T('panel.safety.complianceNotEvaluated',
            'This software does not evaluate regulatory compliance. NFPA, OSHA, '
            + 'DOT and local requirements must be assessed by a qualified EHS / '
            + 'process-safety authority for your specific site, propellant and operation.');
        return U.sectionTitle(T('panel.safety.secCompliance', 'Regulatory compliance'))
            + `<div style="border:1px solid ${U.kindColor('warn')}; border-radius:8px;
                 padding:10px 14px; margin:8px 0; color:${U.kindColor('warn')};">
                 ${note}</div>`;
    }

    function render(data, root) {
        const s = data.safety_analysis || {};
        const risk = s.risk_assessment || {};
        const risks = risk.individual_risks || {};

        // ---- Üst rozetler ----
        let badges = '';
        if (risk.risk_level) {
            badges += U.badge(T('panel.safety.overallRisk', 'OVERALL RISK') + ': ' + risk.risk_level,
                riskLevelKind(risk.risk_level),
                U.tf('panel.safety.overallScoreTip', { value: U.fmt(risk.overall_risk_score, 2) },
                     'Weighted overall score {value} / 5'));
        }
        if (risk.acceptability) {
            const acc = String(risk.acceptability);
            badges += U.badge(acc.replace(/_/g, ' '),
                acc === 'ACCEPTABLE' ? 'ok'
                    : acc === 'ACCEPTABLE_WITH_CONTROLS' ? 'warn' : 'err');
        }
        if (risk.overall_risk_score != null) {
            badges += U.badge(T('panel.safety.scoreBadge', 'SCORE') + ': '
                + U.fmt(risk.overall_risk_score, 2) + ' / 5',
                bandKind(scoreBand(risk.overall_risk_score)));
        }
        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;

        // ---- Bireysel riskler ----
        const LBL = areaLabels();
        html += U.sectionTitle(T('panel.safety.secIndividual',
            'Individual Risks (1 = lowest, 5 = highest)'));
        html += U.kvTable(Object.keys(AREA_LABELS)
            .filter(function (a) { return risks[a] != null; })
            .map(function (a) { return [LBL[a], scoreCell(risks[a])]; }));

        // ---- Azaltım öncelikleri ----
        const pt = priorityTable(risk);
        if (pt) {
            html += U.sectionTitle(T('panel.safety.secMitigation', 'Mitigation Priority'));
            html += pt;
        }

        // ---- 5x5 risk matrisi ----
        html += U.sectionTitle(T('panel.safety.secMatrix', 'Risk Matrix (5×5)'));
        html += riskMatrixHtml(risk);

        // ---- Basınçlı kap özeti ----
        html += pressureVesselBlock(s.pressure_safety);

        // ---- Uyum rozetleri ----
        html += complianceBadges(s.compliance);

        // ---- Öneriler ----
        html += U.listBlock(T('common.recommendations', 'Recommendations'),
                            s.recommendations, 'info');

        root.innerHTML = html;
    }

    window.AnalysisDock.register({
        id: 'safety',
        title: 'Comprehensive Safety — Risk Assessment & Pressure Vessel',
        titleKey: 'panel.safety.title',
        category: 'SAFETY',
        endpoint: '/analyze_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['motor_type', 'Motor Type', 'hybrid', MOTOR_TYPES, 'common.f.motorType'],
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar'],
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 10, 'common.f.chamberTemperatureK'],
            ['thrust', 'Thrust (N)', 1000, 50, 'common.f.thrustN'],
            ['burn_time', 'Burn Time (s)', 10, 0.5, 'common.f.burnTimeS'],
            ['propellant_mass', 'Propellant Mass (kg)', 5, 0.5, 'common.f.propellantMassKg'],
            ['propellant_type', 'Propellant Type', 'composite', PROPELLANTS, 'common.f.propellantType'],
            ['facility_type', 'Facility Type', 'test_stand', FACILITIES, 'common.f.facilityType'],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005, 'common.f.chamberDiameterM'],
            ['wall_thickness', 'Wall Thickness (m)', 0.005, 0.001, 'common.f.wallThicknessM'],
            ['material', 'Material', 'steel_4130', MATERIALS, 'common.f.material'],
        ],
        fromResults: function (r) {
            const m = U.motorDict(r);
            const motorType = window.AnalysisDock.getMotorType();
            const sug = {
                motor_type: motorType,
                chamber_pressure: m.chamber_pressure,
                chamber_temperature: m.chamber_temperature,
                // İTKİ: katı motor düz sözlükte 'thrust' ÜRETMİYOR (ortalama
                // ve tepe itkiyi ayrı raporluyor) — alan 1000 N varsayılanında
                // kalıyordu, gerçek ortalama 1670,6 N.
                thrust: U.readThrust(r),
                burn_time: U.readBurnTime(r),
                // BİRİM: ham okunuyordu ve alan METRE etiketli; katı motorda
                // 75,0 (mm) ve sıvıda 120,0 (mm) geliyor -> panel 75 m / 120 m
                // çaplı bir kap için güvenlik hükmü üretiyordu.
                chamber_diameter: U.readLengthM(r, 'chamber_diameter'),
                // Sıvı motorda çift itergaç, katı/hibritte kompozit varsayılanı
                propellant_type: motorType === 'liquid' ? 'liquid_biprop' : 'composite',
                // İTERGAÇ KÜTLESİ: eskiden yalnız 'mdot_total' x burn_time ile
                // türetiliyordu; o anahtar SADECE hibritte var, katı ve sıvıda
                // alan 5 kg varsayılanında kalıyordu (gerçek: katı 2,41 kg,
                // sıvı 2756,5 kg). Artık her motor tipinin kendi kütle anahtarı
                // okunuyor; TNT eşdeğeri ve tahliye mesafeleri buna bağlı.
                propellant_mass: U.readPropellantMass(r),
                // CİDAR ve MALZEME hiç bağlı değildi: uç bunlar için
                // varsayılana düşüyor ve bunu `defaults_applied` ile
                // bildiriyordu (panel o alanı da okumuyor).
                wall_thickness: U.readWallThicknessM(r),
                material: U.readChamberMaterial(r),
            };
            return sug;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse malzeme select'ini 'structural' etiketli tam
    // listeyle doldur; değilse yukarıdaki fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'safety', fieldId: 'material',
            tags: ['structural'], fallback: MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render (dry-run)
    window.SafetyPanel = { _render: render };
})();
