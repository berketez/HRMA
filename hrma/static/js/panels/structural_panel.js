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
    const T = U.t;                       // çeviri kısayolu

    // FALLBACK listesi — /api/materials kataloğu yüklenemezse kullanılır.
    // Anahtarlar merkezi materials_db kanonik adlarıyla birebir; katalog
    // gelirse 'structural' etiketli tam liste bunun yerine geçer.
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
            [T('panel.structural.vonMises', 'Von Mises (combined)'),
             ca.von_mises_stress, ca.von_mises_safety_factor],
            [T('panel.structural.hoopPressure', 'Hoop (pressure)'),
             U.pick(ca, ['pressure_hoop_stress', 'hoop_stress']), ca.hoop_safety_factor],
            [T('panel.structural.hoopThermal', 'Hoop (thermal)'), ca.thermal_hoop_stress, null],
            [T('panel.structural.longitudinal', 'Longitudinal (axial)'), ca.longitudinal_stress, null],
        ];
        return `<table style="${U.TBL}">
            <thead><tr>
                <th style="${U.TD} text-align:left;">${T('panel.structural.stressComponent', 'Stress Component')}</th>
                <th style="${U.TD}">${T('panel.structural.stressMpa', 'Stress (MPa)')}</th>
                <th style="${U.TD}">${T('common.safetyFactor', 'Safety Factor')}</th>
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
            [T('panel.structural.sfPressureOnly', 'SF (pressure only)'), sfCell(sfPressure, required),
             T('panel.structural.sfPressureOnlyTip',
               'Pressure-only safety factor (hoop based when backend field is absent)')],
            [T('panel.structural.sfTotal', 'SF (total, incl. thermal)'), sfCell(sfTotal, required),
             T('panel.structural.sfTotalTip',
               'Combined safety factor (von Mises based when backend field is absent)')],
        ];
        if (sf && sf.minimum_safety_factor != null) {
            rows.push([T('panel.structural.sfMinAll', 'Minimum SF (all modes)'),
                       sfCell(sf.minimum_safety_factor, required)]);
        }
        const modes = (sf && sf.safety_factors) || {};
        const LABELS = {
            chamber_hoop: T('panel.structural.modeChamberHoop', 'Chamber hoop'),
            chamber_von_mises: T('panel.structural.modeChamberVm', 'Chamber von Mises'),
            end_cap: T('panel.structural.modeEndCap', 'End cap'),
            nozzle: T('panel.structural.modeNozzle', 'Nozzle throat'),
            buckling_axial: T('panel.structural.modeBuckling', 'Axial buckling'),
        };
        Object.keys(modes).forEach(function (k) {
            rows.push(['&nbsp;&nbsp;· ' + (LABELS[k] || k), sfCell(modes[k], required)]);
        });
        if (required != null) {
            rows.push([T('panel.structural.sfRequired', 'Required design SF (material)'),
                `<span style="font-family:var(--hd-mono);">${U.fmt(required, 1)}</span>`]);
        }
        return U.kvTable(rows);
    }

    // ------------------------------------------------------------------
    // HÜKMÜN DAYANAĞI  (`design_basis`)
    // ------------------------------------------------------------------
    // Uç bu bloğu ZATEN gönderiyordu (app.py `/analyze_structural_safety`
    // → 'design_basis'), panel HİÇ okumuyordu. İçinde tam olarak şu yazıyor:
    // cidarı kullanıcı mı verdi yoksa HRMA mı boyutlandırdı, hüküm verildi
    // mi yoksa geri mi çekildi, hangi değerlendirme hiç koşmadı.
    // Bu blok basılmadığı için kullanıcı, HRMA'nın kendi boyutlandırdığı
    // cidara verdiği "SAFE"i, kendi cidarının doğrulanmış hükmü sanıyordu.
    function designBasisBlock(db) {
        if (!db || typeof db !== 'object') return '';
        const withheld = String(db.verdict || '') === 'withheld';
        const sized = String(db.wall_thickness_source || '') === 'sized_by_hrma';
        let html = U.sectionTitle(T('panel.structural.secDesignBasis',
                                    'Basis of this verdict'));
        html += `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:6px 0;">`
            + U.badge(withheld
                    ? T('panel.structural.verdictWithheld', 'VERDICT WITHHELD')
                    : T('panel.structural.verdictIssued', 'VERDICT ISSUED'),
                withheld ? 'warn' : 'ok')
            + U.badge(sized
                    ? T('panel.structural.wallSized', 'WALL: SIZED BY HRMA')
                    : T('panel.structural.wallUser', 'WALL: AS SUPPLIED'),
                sized ? 'warn' : 'ok')
            + '</div>';
        // Sunucunun kendi gerekçe metni ham basılır (buck.source, fast.warning
        // ile aynı desen) — panel onu yeniden yazmaz, çarpıtamaz.
        if (db.message) {
            html += `<p style="font-size:0.8rem; color:${U.kindColor(
                withheld ? 'warn' : 'info')};">${db.message}</p>`;
        }
        const reasons = db.verdict_withheld_reasons;
        if (reasons && reasons.length) {
            html += U.listBlock(T('panel.structural.withheldReasons',
                                  'Why no acceptance was issued'), reasons, 'warn');
        }
        const notEval = db.not_evaluated;
        if (notEval && notEval.length) {
            html += U.listBlock(T('panel.structural.notEvaluated',
                                  'Not evaluated'), notEval, 'warn');
        }
        return html;
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
        badges += U.badge(T('panel.structural.badgeBuckling', 'BUCKLING') + ': ' + bstat,
                          statusKind(bstat), buck.source || '');
        if (sf.status) {
            badges += U.badge(T('panel.structural.badgeStructure', 'STRUCTURE') + ': ' + sf.status,
                statusKind(sf.status),
                U.tf('panel.structural.verdictTip', { sf: U.fmt(sf.minimum_safety_factor) },
                     'Overall structural verdict (min SF = {sf})'));
        }
        if (sf.risk_level) {
            const rk = String(sf.risk_level).toUpperCase();
            badges += U.badge(T('common.risk', 'RISK') + ': ' + rk,
                rk.indexOf('LOW') !== -1 ? 'ok' : rk === 'MEDIUM' ? 'warn' : 'err');
        }
        if (fat.fatigue_status) {
            badges += U.badge(T('panel.structural.badgeFatigue', 'FATIGUE') + ': ' + fat.fatigue_status,
                              statusKind(fat.fatigue_status));
        }
        if (dp.material) {
            badges += U.badge(T('common.material', 'MATERIAL') + ': '
                + String(dp.material).toUpperCase(), 'info',
                U.tf('panel.structural.designPressureTip',
                     { p: U.fmt(dp.design_pressure, 1), f: U.fmt(dp.design_pressure_factor, 2) },
                     'Design pressure {p} bar (factor {f})'));
        }

        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;

        // ---- Hükmün dayanağı (rozetlerin HEMEN ardında: kullanıcı sayıları
        // okumadan önce bunun doğrulama mı öneri mi olduğunu görmeli) ----
        html += designBasisBlock(data.design_basis);

        // ---- Gerilmeler ----
        html += U.sectionTitle(T('panel.structural.secStresses', 'Wall Stresses'));
        html += stressTable(ca, required);
        if (ca.governing_thermal_scenario) {
            html += `<p style="font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">
                ${T('panel.structural.governingScenario', 'Governing thermal scenario')}:
                <strong>${ca.governing_thermal_scenario}</strong>
                · ${T('panel.structural.yieldUsed', 'yield strength used')}:
                ${U.fmt(ca.yield_strength_used_MPa, 0)} MPa
                · ${T('panel.structural.hoopModel', 'hoop model')}:
                ${ca.pressure_hoop_model || '—'}</p>`;
        }

        // ---- Emniyet katsayıları ----
        html += U.sectionTitle(T('panel.structural.secSafetyFactors', 'Safety Factors'));
        html += safetyFactorTable(ca, sf, required);

        // ---- Cidar kalınlığı ----
        if (ca.minimum_thickness != null || ca.recommended_thickness != null) {
            html += U.sectionTitle(T('panel.structural.secThickness', 'Wall Thickness'));
            html += U.kvTable([
                [T('panel.structural.minRequired', 'Minimum required'),
                 U.fmt(ca.minimum_thickness) + ' mm'],
                [T('panel.structural.recommendedMargin', 'Recommended (with margin)'),
                 U.fmt(ca.recommended_thickness) + ' mm'],
            ]);
        }

        // ---- Burkulma ----
        html += U.sectionTitle(T('panel.structural.secBuckling', 'Buckling (NASA SP-8007)'));
        html += U.kvTable([
            [T('panel.structural.appliedAxial', 'Applied axial stress'),
             U.fmt(buck.applied_axial_stress_MPa) + ' MPa'],
            [T('panel.structural.criticalBuckling', 'Critical buckling stress (knocked down)'),
             U.fmt(buck.critical_axial_buckling_stress_MPa, 0) + ' MPa'],
            [T('panel.structural.bucklingSf', 'Buckling safety factor'),
             sfCell(buck.axial_buckling_safety_factor, required)],
            [T('panel.structural.knockdown', 'Knockdown factor γ'),
             U.fmt(buck.knockdown_factor_gamma, 3)],
            [T('panel.structural.criticalExternal', 'Critical external pressure'),
             U.fmt(buck.critical_external_pressure_bar, 1) + ' bar'],
        ]);
        if (buck.source) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);">
                ${T('common.source', 'Source')}: ${buck.source}</p>`;
        }

        // ---- Yorulma ----
        html += U.sectionTitle(T('panel.structural.secFatigue', 'Fatigue'));
        html += U.kvTable([
            [T('common.status', 'Status'),
             U.badge(fat.fatigue_status || '—', statusKind(fat.fatigue_status))],
            [T('panel.structural.estCycles', 'Estimated cycles (this duty)'),
             fat.estimated_cycles != null ? fat.estimated_cycles : '—'],
            [T('panel.structural.estLife', 'Estimated life'), fat.estimated_life || '—'],
            [T('panel.structural.fatigueSf', 'Fatigue safety factor'),
             U.fmt(fat.fatigue_safety_factor, 1)],
            [T('panel.structural.enduranceLimit', 'Endurance limit'),
             U.fmt(fat.fatigue_limit, 0) + ' MPa'],
        ]);

        // ---- Cıvata ve kapak ----
        html += U.sectionTitle(T('panel.structural.secFasteners', 'Fasteners & End Cap'));
        html += U.kvTable([
            [T('panel.structural.bolts', 'Bolts'),
             (fast.num_bolts != null ? fast.num_bolts : '—') + ' × '
                + (fast.recommended_bolt_size || '—')],
            [T('panel.structural.boltSf', 'Bolt safety factor'), sfCell(fast.bolt_safety_factor, null)],
            [T('panel.structural.forcePerBolt', 'Force per bolt'),
             U.tf('panel.structural.forcePerBoltValue',
                  { each: U.fmt(fast.force_per_bolt), total: U.fmt(fast.total_force) },
                  '{each} kN (total {total} kN)')],
            [T('panel.structural.boltSpacing', 'Bolt spacing'), U.fmt(fast.bolt_spacing, 1) + ' mm'],
            [T('panel.structural.endCapType', 'End cap type'),
             String(cap.recommended_type || '—').toUpperCase()],
            [T('panel.structural.headThickness', 'Head thickness (dished / flat)'),
             U.fmt(cap.dished_head_thickness) + ' / ' + U.fmt(cap.flat_head_thickness) + ' mm'],
            [T('panel.structural.headSf', 'Head safety factor'), sfCell(cap.head_safety_factor, required)],
        ]);
        if (fast.warning) {
            html += U.listBlock(T('panel.structural.fastenerWarning', 'Fastener Warning'),
                                [fast.warning], 'warn');
        }

        // ---- Kütle özeti ----
        if (wt.total_weight != null) {
            html += `<p style="font-size:0.8rem; color:var(--hd-ink-dim, #7d97a5);">
                ${T('panel.structural.massEstimate', 'Estimated structure mass')}:
                <strong style="color:var(--hd-ink, #cfe8f2);">
                ${U.fmt(wt.total_weight)} kg</strong>
                (${U.tf('panel.structural.massBreakdown',
                        { chamber: U.fmt(wt.chamber_weight), nozzle: U.fmt(wt.nozzle_weight),
                          caps: U.fmt(wt.end_caps_weight) },
                        'chamber {chamber} · nozzle {nozzle} · end caps {caps} kg')})</p>`;
        }

        // ---- Öneriler ----
        html += U.listBlock(T('common.recommendations', 'Recommendations'),
                            sf.recommendations, 'info');

        root.innerHTML = html;
    }

    window.AnalysisDock.register({
        id: 'structural',
        title: 'Structural Safety — Pressure Vessel, Buckling, Fatigue',
        titleKey: 'panel.structural.title',
        category: 'STRUCTURAL',
        endpoint: '/analyze_structural_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar'],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005, 'common.f.chamberDiameterM'],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01, 'common.f.chamberLengthM'],
            ['throat_diameter', 'Throat Diameter (m)', 0.02, 0.001, 'common.f.throatDiameterM'],
            ['burn_time', 'Burn Time (s)', 10, 0.5, 'common.f.burnTimeS'],
            ['chamber_temperature', 'Gas Temperature (K, 0 = skip thermal)', 0, 50,
             'common.f.gasTemperatureSkip'],
            // İtki alanı yoktu, bu yüzden hesap ucuna hiç gitmiyordu ve
            // eksenel burkulma DAİMA sıfır basma yüküyle koşuyordu
            // (uygulanan gerilme 0,0 MPa, emniyet katsayısı boş "—").
            // Varsayılan 0 = "eksenel yükü atla" (app.py:4398 `if
            // data.get('thrust')`), yani eski davranış korunur; sonuç
            // varsa fromResults gerçek itkiyi doldurur.
            ['thrust', 'Thrust (N)', 0, 50, 'common.f.thrustN'],
            // CİDAR KALINLIĞI (2026-08-09 ölçümü): bu alan listede YOKTU.
            // Panel /analyze_structural_safety'yi cidar bilgisi OLMADAN
            // çağırıyordu; uç da bu durumda cidarı KENDİ boyutlandırıp
            // sonucu döndürüyor (app.py: `wall_thickness_source =
            // 'sized_by_hrma'`). Sonuç: aynı sayfada, aynı motor için,
            // kullanıcının kendi cidarıyla hesaplanmış yapısal hüküm ile
            // HRMA'nın kendi boyutlandırdığı cidarın hükmü yan yana
            // duruyordu — ve hangisinin hangisi olduğu hiçbir yerde
            // yazmıyordu. Kardeş paneller (safety_panel, thermal_panel)
            // bu alanı zaten gönderiyor; tek kopuk olan bu paneldi.
            //
            // Varsayılan 0 = "cidarı ben vermiyorum, sen boyutlandır"
            // (aynı paneldeki `thrust` 0 = "eksenel yükü atla" sözleşmesi;
            // uç tarafında app.py `actual_wall_thickness <= 0` → None).
            // 5 mm gibi bir varsayılan ENJEKTE EDİLMEZ: o, kullanıcının
            // vermediği bir cidarı vermiş gibi göstermek olurdu ve uç
            // sonucu "doğrulama" diye damgalardı.
            ['wall_thickness', 'Wall Thickness (m)', 0, 0.001,
             'common.f.wallThicknessM'],
            ['material', 'Material', 'steel_4130', MATERIALS, 'common.f.material'],
        ],
        fromResults: function (r) {
            const m = U.motorDict(r);
            // BİRİM (2026-07-30 ölçümü): bu üç uzunluk HAM okunuyordu ve
            // alanlar METRE etiketli. Hibritte doğruydu, ama katı motorda
            // chamber_diameter 75,0 (mm) ve sıvıda 120,0 (mm) geliyor —
            // panel bunları 75 m ve 120 m sanıyordu. Merkezi çözümleyici
            // motor tipine göre metreye getiriyor.
            return {
                chamber_pressure: m.chamber_pressure,
                chamber_diameter: U.readLengthM(r, 'chamber_diameter'),
                chamber_length: U.readLengthM(r, 'chamber_length'),
                throat_diameter: U.readLengthM(r, 'throat_diameter'),
                burn_time: U.readBurnTime(r),
                chamber_temperature: m.chamber_temperature,
                // MALZEME hiç döndürülmüyordu: alan varsayılanı steel_4130,
                // arayüz varsayılanı ise steel_304. Aynı oda için ölçüm:
                // steel_4130 SF 4,512 / cidar 2,33 mm  <- panelin gösterdiği
                // ss_304     SF 1,309 / cidar 7,46 mm  <- kullanıcının seçtiği
                // Panel 3,4 kat iyimser emniyet katsayısı gösteriyordu.
                material: U.readChamberMaterial(r),
                // İTKİ: hesap ucu (app.py:4398) 'thrust' verilirse eksenel
                // burkulmayı gerçek basma yüküyle hesaplıyor; verilmezse
                // eksenel kuvvet 0 kalıyor ve burkulma kontrolü ölü kalıyordu.
                thrust: U.readThrust(r),
                // CİDAR: çözücünün kullandığı kalınlık (METRE). Merkezi
                // okuyucu motor tipine göre mm→m çevirir; safety_panel ve
                // thermal_panel de aynı yardımcıyı kullanıyor, böylece üç
                // panel aynı cidarla hesaplar. Sonuç yoksa öneri boş kalır
                // ve alan 0'da (= "sen boyutlandır") durur.
                wall_thickness: U.readWallThicknessM(r),
            };
        },
        render: render,
    });

    // Merkezi katalog yüklüyse select'i 'structural' etiketli tam listeyle
    // doldur; değilse yukarıdaki fallback aynen kalır (typeof guard —
    // materials_catalog.js script'i eklenmemişse de panel çalışır).
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'structural', fieldId: 'material',
            tags: ['structural'], fallback: MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render (dry-run) — injector_panel deseni
    window.StructuralPanel = { _render: render };
})();
