/* ====================================================================
   HRMA Analiz Güvertesi — Termal Güvenlik Paneli
   --------------------------------------------------------------------
   POST /analyze_thermal_safety sonucunu çizer:
   - h_g (Bartz), q_throat / q_chamber, cidar sıcaklıkları → sayısal kartlar
   - Soğutma değerlendirmesi (verim, öneriler, ısı yükü)
   - Plotly çubuk: sıcaklıklar tek seri (cyan), malzeme limitleri
     etiketli referans çizgileri (tema plotly_dark.js'ten gelir)
   - Axial Profile bölümü: POST /api/analysis/wall-profile →
     {x_mm, area_ratio, mach, h_g, q_MW, T_wall_eq} dizileri;
     q(x) & T_wall(x) (ikincil eksen) + Mach(x) grafikleri.
     Endpoint henüz yoksa (404/501) panel kırılmaz, zarif mesaj basar.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    // FALLBACK listesi — /api/materials kataloğu yüklenemezse kullanılır
    // (anahtarlar heat_transfer_analysis.py self.materials içinde çözülür;
    // katalog gelirse 'liner'+'shell' etiketli tam liste bunun yerine geçer)
    //
    // v2.6.26: liste çözücülerin BİLDİRDİĞİ kanonik malzemeleri kapsamıyordu.
    // Sıvı motor hazne malzemesini 'inconel_718' olarak raporluyor; bu anahtar
    // listede olmadığı için katalog yüklenemediğinde öneri uygulanamıyordu
    // (olmayan bir seçeneğe value atamak tarayıcıda seçimi düşürür). Aşağıdaki
    // anahtarların hepsi /analyze_thermal_safety ucunda AYRI ısıl özelliklerle
    // çözülüyor — ölçüldü: k 0,5-401 W/m·K, T_allow 450-3300 K.
    const MATERIALS = [
        ['steel', 'Steel (generic)', 'mat.steelGeneric'],
        ['steel_4130', 'Steel AISI 4130'],
        ['steel_4340', 'Steel AISI 4340'],
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['ss_17_4ph', 'Stainless 17-4PH (H900)'],
        ['aluminum', 'Aluminum', 'mat.aluminum'],
        ['aluminum_6061', 'Aluminum 6061-T6'],
        ['al_7075_t6', 'Aluminum 7075-T6'],
        ['al_2024_t3', 'Aluminum 2024-T3'],
        ['copper', 'Copper', 'mat.copper'],
        ['cucrzr', 'CuCrZr (C18150)'],
        ['beryllium_copper_c17200', 'Beryllium copper C17200'],
        ['inconel', 'Inconel'],
        ['inconel_718', 'Inconel 718'],
        ['inconel_625', 'Inconel 625'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V'],
        ['ti_grade2_cp', 'Titanium CP Grade 2'],
        ['magnesium_az31b', 'Magnesium AZ31B'],
        ['graphite', 'Graphite', 'mat.graphite'],
        ['ablative', 'Ablative liner', 'mat.ablativeLiner'],
    ];

    const COOLING = [
        ['natural', 'Natural (heat sink)', 'cool.natural'],
        ['forced', 'Forced convection', 'cool.forced'],
        ['regenerative', 'Regenerative', 'cool.regenerative'],
    ];

    function riskKind(level) {
        const t = String(level || '').toUpperCase();
        if (t === 'LOW') return 'ok';
        if (t === 'MEDIUM') return 'warn';
        if (t === 'HIGH' || t === 'CRITICAL') return 'err';
        return 'info';
    }

    function sfKind(sf) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        if (sf < 1.0) return 'err';
        if (sf < 2.0) return 'warn';   // heat_transfer_analysis.py uyarı eşiği
        return 'ok';
    }

    function temperaturePlot(root, ta) {
        if (typeof Plotly === 'undefined') return;
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const matp = ta.material_properties || {};

        const cats = [];
        const vals = [];
        function push(label, v) {
            if (typeof v === 'number' && Number.isFinite(v)) {
                cats.push(label);
                vals.push(v);
            }
        }
        push(T('panel.thermal.combustionGas', 'Combustion gas'), gsa.gas_temperature);
        push(T('panel.thermal.adiabaticWall', 'Adiabatic wall'), gsa.adiabatic_wall_temperature);
        push(T('panel.thermal.wallInner', 'Wall (inner)'), wa.inner_temperature);
        push(T('panel.thermal.wallOuter', 'Wall (outer)'), wa.outer_temperature);
        if (!cats.length) return;

        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);

        // Limitler ayrı seri DEĞİL: etiketli referans çizgileri (status rengi
        // asla "series" olarak kullanılmaz; kimlik yalnız renkle taşınmaz)
        const shapes = [];
        const annotations = [];
        function limitLine(v, label, color) {
            if (typeof v !== 'number' || !Number.isFinite(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 1, y: v, xanchor: 'right', yanchor: 'bottom',
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 10, color: color },
            });
        }
        limitLine(matp.allowable_temperature, T('panel.thermal.allowableLimit', 'Allowable limit'), '#ff8c33');
        limitLine(matp.melting_point, T('panel.thermal.meltingPoint', 'Melting point'), '#ff5d73');

        Plotly.newPlot(div, [{
            x: cats, y: vals, type: 'bar',
            marker: { color: '#00e5ff', line: { width: 0 } },
            width: 0.55,
            hovertemplate: '%{x}: %{y:.0f} K<extra></extra>',
        }], {
            title: T('panel.thermal.chartTemps', 'Wall Temperatures vs Material Limits'),
            yaxis: { title: T('common.axis.temperatureK', 'Temperature (K)'), rangemode: 'tozero' },
            // T65 (2026-08-03) — x ekseninde BAŞLIK NESNESİ YOK, BİLEREK.
            // Önceki hâli `xaxis: { title: '' }` idi; plotly_dark.js:92 boş
            // dizgeyi de nesneye çeviriyor ve ÖLÇÜLEN layout şu oluyordu:
            // {"text":"","font":{...},"standoff":8}. Metinsiz bir başlık
            // nesnesi "başlık koymayı unuttuk" ile "başlık gereksiz"i aynı
            // gösteriyor. Burada başlık GEREKSİZDİR: eksen kategoriktir ve
            // etiketlerin kendisi (yanma gazı / adyabatik cidar / cidar iç /
            // cidar dış) ölçülen büyüklüğü zaten söyler. Boş nesne yerine
            // hiç nesne kurulmaz — niyet artık koddan okunur.
            shapes: shapes,
            annotations: annotations,
            height: 360,
            showlegend: false,
        }, { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Eksenel profil (Dalga 2): q(x), T_wall(x), Mach(x)
    // ------------------------------------------------------------------
    const WALL_PROFILE_ENDPOINT = '/api/analysis/wall-profile';

    // Dock buildPayload aynası: gövde formdan okunur; termal formda
    // olmayan nozul geometrisi son hesap sonucundan tamamlanır.
    function readAxialPayload() {
        const payload = {};
        const sec = document.getElementById('ad_sec_thermal');
        if (sec) {
            sec.querySelectorAll('[data-field]').forEach(function (el) {
                const key = el.getAttribute('data-field');
                if (el.tagName === 'SELECT') {
                    payload[key] = el.value;
                    return;
                }
                const v = parseFloat(el.value);
                if (Number.isFinite(v)) payload[key] = v;
            });
        }
        try {
            const results = window.currentResults;
            const m = U.motorDict(results);
            // BİRİM: /api/analysis/wall-profile boğaz çapını METRE bekliyor
            // (app.py). Burada değer HAM okunuyordu; katı motorda çözücü
            // 17,96 (mm) döndürdüğü için eksenel profil 17,96 m boğazla
            // çözülüyordu. Eski kod ayrıca yalnız `currentResults.motor`
            // altına bakıyordu — katı ve sıvı yanıtları DÜZ olduğu için
            // orada hiçbir zaman bir şey bulamıyordu.
            const dtM = U.readLengthM(results, 'throat_diameter');
            if (payload.throat_diameter == null && Number.isFinite(dtM)) {
                payload.throat_diameter = dtM;
            }
            if (payload.expansion_ratio == null && Number.isFinite(m.expansion_ratio)) {
                payload.expansion_ratio = m.expansion_ratio;
            }
        } catch (e) { /* sonuç yoksa backend varsayılanları kullanılır */ }
        return payload;
    }

    // Saf çizim: profil dizilerinden iki Plotly grafiği üretir.
    // En az bir grafik çizildiyse true döner (duman testi bunu kullanır).
    function renderAxialCharts(profile, host) {
        if (typeof Plotly === 'undefined') return false;
        const p = profile || {};
        const x = Array.isArray(p.x_mm) ? p.x_mm : [];
        if (!x.length) return false;
        const sameLen = function (arr) {
            return Array.isArray(arr) && arr.length === x.length;
        };
        let drew = false;

        // Boğaz konumu işareti (backend x_throat_mm veriyorsa)
        const throatX = (typeof p.x_throat_mm === 'number' && Number.isFinite(p.x_throat_mm))
            ? p.x_throat_mm : null;
        function throatShape() {
            if (throatX == null) return [];
            return [{
                type: 'line', yref: 'paper', x0: throatX, x1: throatX, y0: 0, y1: 1,
                line: { color: 'rgba(125, 151, 165, 0.55)', width: 1, dash: 'dot' },
            }];
        }
        function throatAnnotation() {
            if (throatX == null) return [];
            return [{
                x: throatX, yref: 'paper', y: 1, xanchor: 'left', yanchor: 'top',
                text: T('common.throat', 'Throat'), showarrow: false,
                font: { size: 10, color: '#7d97a5' },
            }];
        }

        // --- Grafik 1: q(x) sol eksen + T_wall(x) ikincil (sağ) eksen ---
        const traces1 = [];
        if (sameLen(p.q_MW)) {
            const qTrace = {
                // ADLANDIRMA (v2.6.27, parti 20): `p.q_MW` REFERANS SOĞUTULMUŞ
                // CİDARDAKİ tasarım yüküdür (heat_transfer_analysis.py,
                // `q_flux[i] = gas_side_flux(Tw_ref)`; T_w,ref =
                // min(izin verilen, 0,8*T_aw)) — aynı grafiğin sağ
                // ekseninde duran DENGE cidar sıcaklığındaki akı DEĞİLDİR.
                // Ölçüldü (40 bar / 3000 K / çelik / doğal soğutma, boğaz):
                // referans cidarda 25,98 MW/m², denge cidarında (T_wall_eq =
                // 2976,8 K) 0,088 MW/m² — 294 kat. Çıplak ad bu iki eğriyi
                // aynı şey sanmaya davet ediyordu.
                x: x, y: p.q_MW, name: T('panel.thermal.heatFluxSeriesRefWall', 'Heat flux q (reference cooled wall)'),
                type: 'scatter', mode: 'lines',
                line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²<extra></extra>',
            };
            if (sameLen(p.h_g)) {
                qTrace.customdata = p.h_g;
                qTrace.hovertemplate = 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²'
                    + '<br>h_g = %{customdata:.0f} W/m²·K<extra></extra>';
            }
            traces1.push(qTrace);
        }
        if (sameLen(p.T_wall_eq)) {
            traces1.push({
                x: x, y: p.T_wall_eq, name: T('panel.thermal.eqWallSeries', 'Equilibrium wall T'),
                type: 'scatter', mode: 'lines', yaxis: 'y2',
                line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall = %{y:.0f} K<extra></extra>',
            });
        }
        if (traces1.length) {
            const div1 = document.createElement('div');
            div1.style.marginTop = '10px';
            host.appendChild(div1);
            Plotly.newPlot(div1, traces1, {
                title: T('panel.thermal.chartAxialQ', 'Axial Heat Flux & Equilibrium Wall Temperature'),
                xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
                yaxis: { title: T('common.axis.heatFlux', 'Heat flux (MW/m²)'), rangemode: 'tozero' },
                yaxis2: { title: T('common.axis.wallTemp', 'Wall temperature (K)'), overlaying: 'y',
                          side: 'right', showgrid: false },
                legend: { orientation: 'h' },
                shapes: throatShape(),
                annotations: throatAnnotation(),
                height: 380,
            }, { responsive: true, displaylogo: false });
            drew = true;
        }

        // --- Grafik 2: Mach(x), sonik referans çizgisiyle ---
        if (sameLen(p.mach)) {
            const machTrace = {
                x: x, y: p.mach, name: 'Mach',
                type: 'scatter', mode: 'lines',
                line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>M = %{y:.2f}<extra></extra>',
            };
            if (sameLen(p.area_ratio)) {
                machTrace.customdata = p.area_ratio;
                machTrace.hovertemplate = 'x = %{x:.1f} mm<br>M = %{y:.2f}'
                    + '<br>A/At = %{customdata:.2f}<extra></extra>';
            }
            const div2 = document.createElement('div');
            div2.style.marginTop = '10px';
            host.appendChild(div2);
            Plotly.newPlot(div2, [machTrace], {
                title: T('panel.thermal.chartAxialMach', 'Axial Mach Number'),
                xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
                yaxis: { title: T('common.axis.machNumber', 'Mach number'), rangemode: 'tozero' },
                shapes: [{
                    type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 1, y1: 1,
                    line: { color: 'rgba(255, 93, 115, 0.7)', width: 1, dash: 'dash' },
                }].concat(throatShape()),
                annotations: [{
                    xref: 'paper', x: 1, y: 1, xanchor: 'right', yanchor: 'bottom',
                    text: T('panel.thermal.sonic', 'Sonic — M = 1'), showarrow: false,
                    font: { size: 10, color: '#ff5d73' },
                }].concat(throatAnnotation()),
                height: 320,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
            drew = true;
        }
        return drew;
    }

    // Bölüm montajı: başlık + 'Compute Axial Profile' butonu + grafikler
    function mountAxialSection(root) {
        const sec = document.createElement('div');
        sec.innerHTML = U.sectionTitle(T('panel.thermal.secAxial',
                'Axial Profile — Chamber to Nozzle Exit'))
            + `<p style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5); margin:4px 0 8px;">${
               T('panel.thermal.axialIntro',
                 'Computes the axial distribution of heat flux, equilibrium wall '
                 + 'temperature and Mach number along the chamber-nozzle axis '
                 + '(Bartz correlation with local area ratio).')}</p>`;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.id = 'ad_axial_thermal';
        btn.textContent = T('panel.thermal.btnAxial', 'Compute Axial Profile');
        const status = document.createElement('div');
        status.style.cssText = 'font-family:var(--hd-mono); font-size:0.8rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0;';
        const charts = document.createElement('div');
        sec.appendChild(btn);
        sec.appendChild(status);
        sec.appendChild(charts);
        root.appendChild(sec);

        btn.addEventListener('click', async function () {
            btn.disabled = true;
            status.textContent = T('panel.thermal.computingAxial', 'COMPUTING AXIAL PROFILE…');
            U.purgePlots(charts);   // eski grafiklerin resize dinleyicileri sızmasın
            charts.innerHTML = '';
            try {
                const resp = await fetch(WALL_PROFILE_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(readAxialPayload()),
                });
                if (resp.status === 404 || resp.status === 501) {
                    // Backend ajanı endpoint'i paralel ekliyor — panel kırılmaz
                    status.textContent = T('panel.thermal.axialUpdating',
                        'Axial profile backend is updating — '
                        + 'please retry once the server has reloaded.');
                    return;
                }
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || data.status === 'error') {
                    throw new Error((data && data.error) || ('HTTP ' + resp.status));
                }
                // Diziler backend'de data.wall_profile altında (test_client ile
                // doğrulandı, 2026-07-14); kök ve data.profile da tolere edilir
                const profile = (data.wall_profile && data.wall_profile.x_mm)
                    ? data.wall_profile
                    : (data.profile && data.profile.x_mm) ? data.profile : data;
                if (!renderAxialCharts(profile, charts)) {
                    status.textContent = T('panel.thermal.noProfile',
                        'Unexpected response — no profile arrays found.');
                    return;
                }
                status.textContent = '';
            } catch (err) {
                status.textContent = U.tf('common.errorPrefix', { message: err.message },
                                          'ERROR: {message}');
            } finally {
                btn.disabled = false;
            }
        });
    }

    function render(data, root) {
        const ta = data.thermal_analysis || {};
        const htc = ta.heat_transfer_coefficients || {};
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const cool = ta.cooling_analysis || {};
        const safe = ta.safety_analysis || {};
        const matp = ta.material_properties || {};
        const dpp = ta.design_parameters || {};

        // ---- Rozetler ----
        let badges = '';
        if (safe.risk_level) {
            badges += U.badge(T('panel.thermal.badgeRisk', 'THERMAL RISK') + ': ' + safe.risk_level,
                              riskKind(safe.risk_level));
        }
        badges += U.badge(T('panel.thermal.badgeCooling', 'COOLING') + ': '
            + String(dpp.cooling_type || '—').toUpperCase(), 'info',
            U.tf('panel.thermal.coolingEffTip', { value: U.fmt(cool.cooling_efficiency, 2) },
                 'Cooling efficiency {value}'));
        if (htc.correlation) {
            badges += U.badge(T('panel.thermal.badgeModel', 'MODEL: BARTZ'), 'info', htc.correlation);
        }
        if (gsa.wall_temperature_unphysical) {
            badges += U.badge(T('panel.thermal.badgeUnphysical',
                'WALL T UNPHYSICAL — cooling insufficient'), 'err',
                T('panel.thermal.unphysicalTip',
                  'Predicted steady-state wall temperature exceeds physical limits; '
                  + 'the wall would fail before reaching it. Improve cooling.'));
        }

        // ---- Sayısal kartlar ----
        const tempKind = function (temp) {
            if (typeof temp !== 'number' || !Number.isFinite(temp)) return 'dim';
            if (matp.melting_point != null && temp >= matp.melting_point) return 'err';
            if (matp.allowable_temperature != null && temp > matp.allowable_temperature) return 'warn';
            return 'ok';
        };
        const head = document.createElement('div');
        head.innerHTML = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`
            + `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.thermal.cardHg', 'h_g (gas side)'), U.fmt(htc.gas_side, 0),
                'W/m²·K', null, htc.correlation || '')
            // ADLANDIRMA (v2.6.27, parti 20): iki kart da REFERANS SOĞUTULMUŞ
            // cidardaki Bartz tasarım yüküdür (heat_transfer_analysis.py,
            // `throat_heat_flux = gas_side_flux(Tw_ref, h_gas)` ve
            // `chamber_heat_flux = gas_side_flux(Tw_ref, h_chamber)`;
            // ölçüldü 40 bar / 3000 K / çelik: 24,12 ve 2,40 MW/m²,
            // T_w,ref = 1073 K). Rejeneratif panelin
            // tepe akısı ise KUPLE cidar dengesinden gelir — aynı adı
            // taşıyamazlar (ölçüm için panel.regen.cardPeakFluxBalance).
            + U.statCard(T('panel.thermal.cardQThroatRefWall', 'q_throat (reference cooled wall)'),
                U.fmt(gsa.throat_heat_flux / 1e6, 2), 'MW/m²', null,
                T('panel.thermal.cardQThroatTip',
                  'Bartz design load at the reference cooled wall '
                  + '(T_w,ref = min(allowable, 0.8*T_aw)); not the flux at the '
                  + 'equilibrium wall temperature'))
            + U.statCard(T('panel.thermal.cardQChamberRefWall', 'q_chamber (reference cooled wall)'),
                U.fmt(gsa.chamber_heat_flux / 1e6, 2), 'MW/m²')
            + U.statCard(T('panel.thermal.cardTwallIn', 'T_wall inner'),
                U.fmt(wa.inner_temperature, 0), 'K', tempKind(wa.inner_temperature))
            + U.statCard(T('panel.thermal.cardTwallOut', 'T_wall outer'),
                U.fmt(wa.outer_temperature, 0), 'K', tempKind(wa.outer_temperature))
            + U.statCard(T('panel.thermal.cardTaw', 'T_adiabatic wall'),
                U.fmt(gsa.adiabatic_wall_temperature, 0), 'K')
            + '</div>';
        root.appendChild(head);

        // ---- Plotly çubuk ----
        temperaturePlot(root, ta);

        const tail = document.createElement('div');
        let thtml = U.sectionTitle(T('panel.thermal.secHeatLoad', 'Heat Load & Cooling Assessment'));
        thtml += U.kvTable([
            [T('panel.thermal.totalHeatRate', 'Total heat rate'), U.fmt(cool.peak_heat_rate, 1) + ' kW'],
            [T('panel.thermal.totalHeatEnergy', 'Total heat energy (burn)'),
             U.fmt(cool.total_heat_energy, 1) + ' MJ'],
            [T('panel.thermal.coolingEfficiency', 'Cooling efficiency'), U.fmt(cool.cooling_efficiency, 2)
                + ' (' + String(dpp.cooling_type || '—') + ')'],
            [T('panel.thermal.requiredArea', 'Required cooling area'),
             U.fmt(cool.required_cooling_area, 2) + ' m²'],
            [T('panel.thermal.heatSinkMass', 'Heat sink mass (steel equiv.)'),
             U.fmt(cool.heat_sink_mass, 1) + ' kg',
             T('panel.thermal.heatSinkTip', 'Steel heat-sink mass for a 200 K temperature rise')],
            [T('panel.thermal.hotGasArea', 'Hot-gas surface area'), U.fmt(gsa.surface_area, 3) + ' m²'],
        ]);

        thtml += U.sectionTitle(T('panel.thermal.secSafety', 'Thermal Safety Factors'));
        const sfRow = function (label, v, note) {
            const c = U.kindColor(sfKind(v));
            return [label, `<span style="color:${c}; font-family:var(--hd-mono);">${U.fmt(v)}</span>`, note];
        };
        thtml += U.kvTable([
            sfRow(T('panel.thermal.sfMelting', 'Melting safety factor'), safe.melting_safety_factor,
                T('panel.thermal.sfMeltingTip', 'Melting point / wall temperature')),
            sfRow(T('panel.thermal.sfTemperature', 'Temperature safety factor'),
                safe.temperature_safety_factor,
                T('panel.thermal.sfTemperatureTip', 'Allowable temperature / wall temperature')),
            sfRow(T('panel.thermal.sfStress', 'Thermal stress safety factor'), safe.stress_safety_factor),
            [T('panel.thermal.thermalStress', 'Thermal stress'), U.fmt(safe.thermal_stress, 0) + ' MPa'],
            [T('panel.thermal.materialLimits', 'Material limits'),
             U.tf('panel.thermal.materialLimitsValue',
                  { allow: U.fmt(matp.allowable_temperature, 0), melt: U.fmt(matp.melting_point, 0) },
                  '{allow} K allowable · {melt} K melting')],
            [T('common.f.wallThickness', 'Wall thickness'), U.fmt(dpp.wall_thickness, 1) + ' mm ('
                + (dpp.material || '—') + ')'],
        ]);

        const warns = [].concat(safe.warnings || [], gsa.warnings || []);
        thtml += U.listBlock(T('common.warnings', 'Warnings'), warns, 'warn');
        const recs = [].concat(safe.recommendations || [], cool.recommendations || []);
        thtml += U.listBlock(T('panel.thermal.coolingRecs', 'Cooling Recommendations'), recs, 'info');
        tail.innerHTML = thtml;
        root.appendChild(tail);

        // ---- Eksenel profil bölümü (ikinci buton + iki grafik) ----
        mountAxialSection(root);
    }

    window.AnalysisDock.register({
        id: 'thermal',
        title: 'Thermal Safety — Bartz Heat Transfer & Wall Temperatures',
        titleKey: 'panel.thermal.title',
        category: 'THERMAL',
        endpoint: '/analyze_thermal_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar'],
            ['chamber_temperature', 'Chamber Temperature (K)', 3000, 10, 'common.f.chamberTemperatureK'],
            ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005, 'common.f.chamberDiameterM'],
            ['chamber_length', 'Chamber Length (m)', 0.5, 0.01, 'common.f.chamberLengthM'],
            ['burn_time', 'Burn Time (s)', 10, 0.5, 'common.f.burnTimeS'],
            ['mdot_total', 'Total Mass Flow (kg/s)', 1.0, 0.05, 'common.f.mdotTotal'],
            ['wall_thickness', 'Wall Thickness (m)', 0.005, 0.001, 'common.f.wallThicknessM'],
            ['material', 'Wall Material', 'steel', MATERIALS, 'common.f.wallMaterial'],
            ['cooling_type', 'Cooling Type', 'natural', COOLING, 'common.f.coolingType'],
        ],
        fromResults: function (r) {
            const m = U.motorDict(r);
            // BİRİM SÖZLEŞMESİ (2026-07-30 yeniden ölçüldü):
            // Buradaki eski `mmToM` yardımcısı çözücüden gelen
            // chamber_diameter / chamber_length değerlerini KOŞULSUZ 1000'e
            // bölüyordu. Yorumu yalnız katı ve sıvı motoru sayıyordu, HİBRİT
            // atlanmıştı — oysa panel motorTypes: ['hybrid','liquid','solid']
            // ile hibritte de kayıtlı. Hibrit çözücü bu iki alanı ZATEN METRE
            // döndürüyor (ölçüm: chamber_diameter 0,0798685 m -> panele
            // 7,99e-05 m, yani 0,08 mm çaplı oda). Sonuç: q_chamber 8,4 kat
            // yüksek, ısı kuyusu kütlesi 6,7 kat düşük çıkıyordu.
            // Çevirme artık panelde değil, ölçülmüş birim tablosunu tutan
            // merkezi AnalysisDock.ui.readLengthM içinde yapılıyor.
            return {
                chamber_pressure: m.chamber_pressure,
                chamber_temperature: m.chamber_temperature,
                chamber_diameter: U.readLengthM(r, 'chamber_diameter'),
                chamber_length: U.readLengthM(r, 'chamber_length'),
                burn_time: U.readBurnTime(r),
                // Eski kod 'total_mass_flow' (yalnız sıvıda var) ve
                // 'propellant_mass' (yalnız katıda var) anahtarlarını
                // arıyordu; hibritte ikisi de YOK, bu yüzden alan panel
                // varsayılanı 1,0 kg/s'de kalıyordu (gerçek: 1,2643 kg/s).
                mdot_total: U.readMassFlow(r),
                // Aşağıdaki iki alan hiç bağlı DEĞİLDİ: kullanıcı sayfada
                // AISI 304 / 8 mm seçmişken panel 'steel' ve 5 mm ile
                // hesaplıyordu (hesap ucu varsayılanları).
                material: U.readChamberMaterial(r),
                wall_thickness: U.readWallThicknessM(r),
            };
        },
        render: render,
    });

    // Merkezi katalog yüklüyse cidar malzemesi select'ini 'liner'+'shell'
    // etiketli listeyle doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'thermal', fieldId: 'material',
            tags: ['liner', 'shell'], fallback: MATERIALS, merge: true,
        });
    }

    // Test / hata ayıklama: saf render (dry-run) + eksenel yardımcılar
    window.ThermalPanel = {
        _render: render,
        _renderAxialCharts: renderAxialCharts,
        _mountAxialSection: mountAxialSection,
        _readAxialPayload: readAxialPayload,
    };
})();
