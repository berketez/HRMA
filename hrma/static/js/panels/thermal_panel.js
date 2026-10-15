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

    // V3 KK 3. tur (§28-50 (c)) — TR KİPİNDE NOKTALI ONDALIK.
    // ÖLÇÜLDÜ (docs/user_guide/img/v3_0/kanit/kayit_tr.json, TR kip, örnek
    // katı, güverte termal paneli): '51.20 MW/m²', '616.4 kW', '0.27',
    // '493.16 m²'. `U.fmt` her zaman nokta basar; ekrandaki sayı metni
    // güvertenin TEK biçim kaynağından (`U.num` → I18N.number) gelir.
    // Basamak sayısı DEĞİŞMEZ; sayı yoksa U.fmt ile aynı '—' imi.
    function numL(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—'
            : U.num(x, d == null ? 2 : d);
    }

    // Sunucu cümlesi (ör. ıslak alan konturu beyanı) TR kipte çevrilir;
    // eşleşme yoksa AYNEN (i18n_charts.js serverText sözleşmesi).
    function SRV(text) {
        return (window.I18N && typeof window.I18N.serverText === 'function')
            ? window.I18N.serverText(text) : text;
    }

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
        ['steel_4130', 'Steel AISI 4130', 'mat.steelAisi4130'],
        ['steel_4340', 'Steel AISI 4340', 'mat.steelAisi4340'],
        ['ss_304', 'Stainless 304', 'mat.stainless304'],
        ['ss_316', 'Stainless 316', 'mat.stainless316'],
        ['ss_17_4ph', '17-4PH (H900)'],
        ['aluminum', 'Aluminum', 'mat.aluminum'],
        ['aluminum_6061', 'Aluminum 6061-T6', 'mat.aluminum6061'],
        ['al_7075_t6', 'Aluminum 7075-T6', 'mat.aluminum7075'],
        ['al_2024_t3', 'Aluminum 2024-T3', 'mat.aluminum2024'],
        ['copper', 'Copper', 'mat.copper'],
        ['cucrzr', 'CuCrZr (C18150)'],
        ['beryllium_copper_c17200', 'BeCu C17200'],
        ['inconel', 'Inconel'],
        ['inconel_718', 'Inconel 718'],
        ['inconel_625', 'Inconel 625'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V', 'mat.titanium6al4v'],
        ['ti_grade2_cp', 'Titanium CP Grade 2', 'mat.titaniumGrade2'],
        ['magnesium_az31b', 'Magnesium AZ31B', 'mat.magnesiumAz31b'],
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

    /* ÖH D37 A2-1 termal 7. tur — karar §28-24 §3/§4 (panel çelişkisi):
       TEK EŞİK. Kart rengi, "Material limits … allowable" satırı ve
       grafikteki "Allowable limit" çizgisi sunucunun KANONİK izin
       basamağını okur: `safety_analysis.threshold_ladder.allowable_K`
       (= materials_db.temperature_limits(rec).allowable_K = min(
       allowable_temperature, max_service_temp)); sıcaklık emniyet
       katsayısı ve critical `temp_exceeds_allowable` uyarısı da bu
       sayıdan kurulur. ÖLÇÜLDÜ (Sunum 2 §3 [4. tur] bilgi satırı): ham
       `material_properties.allowable_temperature` okunurken pencere
       vakalarında (cidar 811-1000 K, bakırda 723-1000 K) kart YEŞİL ve
       "1000 K allowable" basılıyor, aynı yanıt critical uyarı veriyordu.
       Sunucu basamağı yayımlamadıysa sayı UYDURULMAZ (null → '—', çizgi
       yok); ham alana geri düşülmez. */
    function canonicalAllowableK(ta) {
        const sa = (ta && ta.safety_analysis) || {};
        const tl = sa.threshold_ladder;
        const v = tl && tl.allowable_K;
        return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
    }

    /* V3 KK (KAB devri 5, karar §28-31 tek izin basamağı): aynı yanıtta
       `material_properties.allowable_temperature` (malzeme kaydının ısıl izin
       ADAYI) ile `threshold_ladder.allowable_K` (hükmü veren basamak) farklı
       olabiliyor — ÖLÇÜLDÜ 'steel' 1073 K ⟷ 811 K (max_service_temp). Satır,
       sunucunun yayımladığı `allowable_governed_by` + `allowable_candidates_K`
       alanlarından hükmü vereni ve ötekini ADIYLA basar. Yalnız bilinen iki
       aday adı basılır (sabit sözlük, sunucu metni HTML olarak girmez);
       alan yoksa ya da ad tanınmıyorsa satır HİÇ basılmaz (uydurma yok). */
    function governingLimitName(field) {
        if (field === 'max_service_temp') {
            return T('panel.thermal.limitNameService',
                     'structural service limit (max_service_temp)');
        }
        if (field === 'allowable_temperature') {
            return T('panel.thermal.limitNameAllowable',
                     'material allowable temperature (allowable_temperature)');
        }
        return null;
    }

    function governingLimitRow(ta) {
        const sa = (ta && ta.safety_analysis) || {};
        const tl = sa.threshold_ladder || {};
        const gov = tl.allowable_governed_by;
        const cands = (tl.allowable_candidates_K
                       && typeof tl.allowable_candidates_K === 'object')
            ? tl.allowable_candidates_K : null;
        const allowK = canonicalAllowableK(ta);
        const govName = governingLimitName(gov);
        if (!cands || govName === null || allowK === null) return null;
        const govK = cands[gov];
        if (typeof govK !== 'number' || !Number.isFinite(govK)
                || govK !== allowK) return null;
        const other = gov === 'max_service_temp'
            ? 'allowable_temperature' : 'max_service_temp';
        const otherK = cands[other];
        let text;
        if (typeof otherK !== 'number' || !Number.isFinite(otherK)) {
            text = U.tf('panel.thermal.governingLimitSingle',
                        { gov: govName, govK: U.fmt(govK, 0) },
                        '{gov} = {govK} K gives the verdict');
        } else if (otherK === govK) {
            text = U.tf('panel.thermal.governingLimitEqual',
                        { gov: govName, other: governingLimitName(other),
                          govK: U.fmt(govK, 0) },
                        '{gov} and {other} are both {govK} K; '
                        + 'that limit gives the verdict');
        } else {
            text = U.tf('panel.thermal.governingLimitValue',
                        { gov: govName, govK: U.fmt(govK, 0),
                          other: governingLimitName(other),
                          otherK: U.fmt(otherK, 0) },
                        '{gov} = {govK} K gives the verdict · '
                        + '{other} = {otherK} K does not');
        }
        return [T('panel.thermal.governingLimit', 'Governing temperature limit'),
                text];
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
        limitLine(canonicalAllowableK(ta), T('panel.thermal.allowableLimit', 'Allowable limit'), '#ff8c33');
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
            U.tf('panel.thermal.coolingEffTip', { value: numL(cool.cooling_efficiency, 2) },
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
        const allowK = canonicalAllowableK(ta);   // tek eşik (7. tur)
        const tempKind = function (temp) {
            if (typeof temp !== 'number' || !Number.isFinite(temp)) return 'dim';
            if (matp.melting_point != null && temp >= matp.melting_point) return 'err';
            if (allowK != null && temp > allowK) return 'warn';
            return 'ok';
        };
        const head = document.createElement('div');
        head.innerHTML = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`
            + `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.thermal.cardHg', 'h_g (gas side)'), numL(htc.gas_side, 0),
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
                numL(gsa.throat_heat_flux / 1e6, 2), 'MW/m²', null,
                T('panel.thermal.cardQThroatTip',
                  'Bartz design load at the reference cooled wall '
                  + '(T_w,ref = min(allowable, 0.8*T_aw)); not the flux at the '
                  + 'equilibrium wall temperature'))
            + U.statCard(T('panel.thermal.cardQChamberRefWall', 'q_chamber (reference cooled wall)'),
                numL(gsa.chamber_heat_flux / 1e6, 2), 'MW/m²')
            + U.statCard(T('panel.thermal.cardTwallIn', 'T_wall inner'),
                numL(wa.inner_temperature, 0), 'K', tempKind(wa.inner_temperature))
            + U.statCard(T('panel.thermal.cardTwallOut', 'T_wall outer'),
                numL(wa.outer_temperature, 0), 'K', tempKind(wa.outer_temperature))
            + U.statCard(T('panel.thermal.cardTaw', 'T_adiabatic wall'),
                numL(gsa.adiabatic_wall_temperature, 0), 'K')
            + '</div>';
        root.appendChild(head);

        // ---- Plotly çubuk ----
        temperaturePlot(root, ta);

        const tail = document.createElement('div');
        let thtml = U.sectionTitle(T('panel.thermal.secHeatLoad', 'Heat Load & Cooling Assessment'));
        // ÖH D15 / P11B5-05 — ISI KUYUSU ETİKETİ ÖLÇÜMLE TERSTİ.
        // ÖLÇÜLDÜ (once.json, gerçek /analyze_thermal_safety, 40 bar/3000 K/
        // 5 mm, yalnız `material` değişiyor): kütle SEÇİLEN malzemenin
        // cp'siyle ve ucun KENDİ ΔT'siyle hesaplanıyor —
        //   steel  24,18 kg  ΔT 517,85 K  cp 460   limit  811 K
        //   graphite 0,73 kg ΔT 3.006,85 K cp 710  limit 3300 K
        //   Al 6061 49,00 kg ΔT 183,85 K   cp 896  limit  477 K
        // Ekrandaki "(steel equiv.)" ve "for a 200 K temperature rise"
        // ipucu hiçbir satırda doğru değil (sapma 0,92× ile 15,0× arası);
        // grafit seçen kullanıcı "0,73 kg çelik, 200 K ısınır" okuyor.
        // Ucun kendi beyanı (`heat_sink_delta_T_basis`,
        // `heat_sink_specific_heat_source`, `heat_sink_temperature_limit_K`)
        // ekranda hiç yoktu.
        //
        // Onarım: uç kendi tabanını yayımlıyorsa YANLIŞ etiket ve ipucu
        // BASILMAZ; satır makine alan adıyla (yeni çeviri anahtarı açılmadı)
        // ve ucun kendi ΔT/cp/kaynak beyanıyla çıkar. Beyan yoksa (eski uç)
        // eski satır korunur — sayı hiçbir dalda değişmez.
        const hsBasis = (typeof cool.heat_sink_delta_T_basis === 'string')
            ? cool.heat_sink_delta_T_basis : null;
        const hsSource = (typeof cool.heat_sink_specific_heat_source === 'string')
            ? cool.heat_sink_specific_heat_source : null;
        const hsDeclared = !!(hsBasis || hsSource
            || typeof cool.heat_sink_delta_T_K === 'number');
        // ÖH D25 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI ARTIK BAĞLI.
        // Pano (analysis_dock.js) `U.source.of()` ile ucun KENDİ beyanını
        // dört duruma çeviriyordu (computed/user/assumed/missing) ama hiçbir
        // panel onu çağırmıyordu: ölçüldü (once.json), 16 panelin 13'ü beyan
        // alanı OKUYOR, sınıflandırıcıyı çağıran panel sayısı 0'dı — katman
        // ölüydü. Burada beyan METNİ zaten okunuyordu; hükmü artık ORTAK
        // sınıflandırıcı verir, panel kendi damgasını uydurmaz.
        const hsInfo = (U.source && U.source.of)
            ? U.source.of({ basis: hsBasis, source: hsSource }, null,
                          { value: cool.heat_sink_mass })
            : null;
        const hsChip = (hsInfo && U.source.chip) ? U.source.chip(hsInfo) : '';
        const heatSinkRow = hsDeclared
            ? ['<span style="font-family:var(--hd-mono); font-size:0.72rem;">'
               + 'heat_sink_mass</span>',
               numL(cool.heat_sink_mass, 1) + ' kg' + hsChip
               + '<span style="font-family:var(--hd-mono); font-size:0.68rem;'
               + ' color:var(--hd-ink-dim, #7d97a5);"> · heat_sink_delta_T_K '
               + numL(cool.heat_sink_delta_T_K, 2)
               + ' · heat_sink_specific_heat_J_kgK '
               + numL(cool.heat_sink_specific_heat_J_kgK, 1)
               + (hsSource ? ' · heat_sink_specific_heat_source ' + hsSource : '')
               + (typeof cool.heat_sink_temperature_limit_K === 'number'
                  ? ' · heat_sink_temperature_limit_K '
                    + numL(cool.heat_sink_temperature_limit_K, 1) : '')
               + (hsBasis
                  ? '<br>heat_sink_delta_T_basis: ' + hsBasis : '')
               + '</span>',
               hsBasis || '']
            : [T('panel.thermal.heatSinkMass', 'Heat sink mass (steel equiv.)'),
               numL(cool.heat_sink_mass, 1) + ' kg',
               T('panel.thermal.heatSinkTip',
                 'Steel heat-sink mass for a 200 K temperature rise')];

        // ÖH D15 / P11B5-06 — JENERİK LÜLE KONTURU BEYANI EKRANDA YOKTU.
        // ÖLÇÜLDÜ (once.json): uç `gas_side_analysis
        // .wetted_integral_contour_basis` içinde kendi cümlesini yazıyor —
        // "neither exit_diameter nor expansion_ratio was supplied; the
        //  sampler falls back to its own generic exit diameter, so the
        //  divergent extent of this axis is NOT this motor's"
        // (`generic_defaults_used = ['exit_diameter','nozzle_type']`).
        // Panel formunda çıkış çapı / genleşme oranı alanı YOK, yani beyan
        // varsayılan kullanımda HER koşuda üretiliyor. Ekranda ise yalnız
        // "Hot-gas surface area 0.198 m²" duruyordu; aynı ıslak alandan
        // türeyen üç sayı (toplam ısı hızı — ölçülen %31,5'i jenerik lüle
        // konturundan, toplam ısı enerjisi, ısı kuyusu kütlesi) künyesizdi.
        //
        // Onarım: beyan varsa ıslak alan satırı ucun kendi cümlesini taşır
        // ve türeyen satırlar aynı beyana bağlanır. Beyan yoksa hiçbir şey
        // iddia edilmez (fail-closed).
        const wib = gsa.wetted_integral_contour_basis;
        const generics = (wib && Array.isArray(wib.generic_defaults_used))
            ? wib.generic_defaults_used : null;
        const wibNote = (wib && generics && generics.length)
            ? ('wetted_integral_contour_basis.generic_defaults_used: '
               + generics.join(', ') + ' — ' + SRV(String(wib.exit_diameter_source || '')))
            : '';
        const derivedNote = wibNote
            ? ('wetted_integral_contour_basis.generic_defaults_used: '
               + generics.join(', '))
            : '';
        // GÖRÜNÜR im: üzerine gelinmeden okunmayan bir `title` metni
        // "ekranda" sayılmaz (a2 turunda ölçülen bekçi zaafı). Islak alandan
        // TÜREYEN her satır beyanı kendi metninde taşır.
        const derivedMark = wibNote
            ? ('<span data-thermal-derived-generic="1"'
               + ' style="font-family:var(--hd-mono); font-size:0.66rem;'
               + ' color:var(--hd-orange, #ff8c33);"> · '
               + 'wetted_integral_contour_basis.generic_defaults_used: '
               + generics.join(', ') + '</span>')
            : '';
        thtml += U.kvTable([
            [T('panel.thermal.totalHeatRate', 'Total heat rate'),
             numL(cool.peak_heat_rate, 1) + ' kW' + derivedMark, derivedNote],
            [T('panel.thermal.totalHeatEnergy', 'Total heat energy (burn)'),
             numL(cool.total_heat_energy, 1) + ' MJ' + derivedMark, derivedNote],
            [T('panel.thermal.coolingEfficiency', 'Cooling efficiency'), numL(cool.cooling_efficiency, 2)
                + ' (' + String(dpp.cooling_type || '—') + ')'],
            [T('panel.thermal.requiredArea', 'Required cooling area'),
             numL(cool.required_cooling_area, 2) + ' m²'],
            heatSinkRow,
            [T('panel.thermal.hotGasArea', 'Hot-gas surface area'),
             numL(gsa.surface_area, 3) + ' m²'
             + (wibNote
                ? '<span data-thermal-generic-contour="'
                  + String(generics.length) + '"'
                  + ' style="font-family:var(--hd-mono); font-size:0.68rem;'
                  + ' color:var(--hd-orange, #ff8c33);"> · '
                  + U.esc(SRV(String(wib.exit_diameter_source))) + '</span>'
                : ''),
             wibNote],
        ]);

        thtml += U.sectionTitle(T('panel.thermal.secSafety', 'Thermal Safety Factors'));
        const sfRow = function (label, v, note) {
            const c = U.kindColor(sfKind(v));
            return [label, `<span style="color:${c}; font-family:var(--hd-mono);">${numL(v)}</span>`, note];
        };
        thtml += U.kvTable([
            sfRow(T('panel.thermal.sfMelting', 'Melting safety factor'), safe.melting_safety_factor,
                T('panel.thermal.sfMeltingTip', 'Melting point / wall temperature')),
            sfRow(T('panel.thermal.sfTemperature', 'Temperature safety factor'),
                safe.temperature_safety_factor,
                T('panel.thermal.sfTemperatureTip', 'Allowable temperature / wall temperature')),
            sfRow(T('panel.thermal.sfStress', 'Thermal stress safety factor'), safe.stress_safety_factor),
            [T('panel.thermal.thermalStress', 'Thermal stress'), numL(safe.thermal_stress, 0) + ' MPa'],
            [T('panel.thermal.materialLimits', 'Material limits'),
             U.tf('panel.thermal.materialLimitsValue',
                  { allow: numL(allowK, 0), melt: numL(matp.melting_point, 0) },
                  '{allow} K allowable · {melt} K melting')],
            governingLimitRow(ta),
            [T('common.f.wallThickness', 'Wall thickness'), numL(dpp.wall_thickness, 1) + ' mm ('
                + (dpp.material || '—') + ')'],
        ].filter(Boolean));

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
            ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS'], // OH-D37-S6: süre uydurulmaz — boşsa gövdeye girmez (safety_panel.js deseni)
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
