/* ====================================================================
   HRMA Analiz Güvertesi — Rejeneratif Soğutma Paneli (Dalga 4B)
   --------------------------------------------------------------------
   POST /api/regen-cooling sonucunu çizer (1D istasyon marşı, analiz modu;
   hrma/analysis/regen_cooling.py — Bartz gaz tarafı + Dittus-Boelter
   soğutucu tarafı + ince-cidar iletim).

   Panel içeriği:
     - Rozetler: soğutucu, cidar malzemesi, akış yönü; cidar sıcaklığı
       malzeme limitini aşarsa KIRMIZI rozet; RP-1 koklaşırsa KIRMIZI rozet.
     - Kartlar: tepe cidar T + marj, soğutucu çıkış T + ΔT, toplam ΔP,
       tepe ısı akısı, maks hız, min Reynolds.
     - Plotly: T_wall_hot(x) / T_wall_cold(x) / T_coolant(x) — malzeme
       izin verilen sınır çizgisi + RP-1 koklaşma çizgisi (boğaz işareti).
     - İkinci grafik: q(x) [MW/m²] sol eksen + P_coolant(x) [bar] sağ eksen.
     - Uyarılar + model notu (dürüst sınırlar).

   YALNIZ sıvı motor (motorTypes:['liquid']) — hibrit/katıda rejeneratif
   soğutma anlamsızdır.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    // FALLBACK — soğutucu tarafı cidar malzemeleri, materials_db
    // anahtarlarıyla birebir (get_material; regen_cooling.py wall_material).
    // Bakır/CuCrZr yüksek iletkenlikleriyle tipik rejeneratif liner.
    // Katalog gelirse 'liner'+'shell' etiketli tam liste bunun yerine geçer.
    // V301/DİL (NK-67): çevrilebilen adlar ortak malzeme anahtarlarıyla
    // (protection_panel.js ile aynı); özel adlar (CuCrZr, Inconel) aynen.
    const WALL_MATERIALS = [
        ['copper', 'Copper (OFHC)', 'mat.copperOfhc'],
        ['cucrzr', 'CuCrZr'],
        ['inconel_718', 'Inconel 718'],
        ['ss_304', 'Stainless 304', 'mat.stainless304'],
        ['steel_4130', 'Steel AISI 4130', 'mat.steelAisi4130'],
    ];

    // ÖH A2 sivi-sogutma · 7. tur (F-17): soğutucu ön-dolgusu 'water' idi —
    // hiçbir hesaptan değil. Seçici artık boş seçimle açılır; değer motorun
    // yakıtından gelir (soğutucu = yakıt, fromResults) ya da kullanıcı seçer.
    // Boş seçim gövdeye gitmez: alan spec.required'da (güverte durdurur).
    // Metan ve hidrojen: modül ikisini de çözüyor (CoolProp, süperkritik
    // marş; regen_cooling.canonical_coolant_name 'lh2' → 'hydrogen'), ama
    // seçicide yoktu — LH2 motorunun paneli 'water' ile koşuyordu (ölçüldü,
    // sart7/olcum/k12_once_sonra.json). Değerler motorun yakıt anahtarıyla
    // aynıdır ki öneri doğrudan eşleşsin.
    const COOLANTS = [
        ['', '— select —', 'panel.regen.coolantSelect'],
        ['water', 'Water', 'coolant.water'],
        ['rp1', 'RP-1 (kerosene)', 'coolant.rp1'],
        ['methane', 'Methane (LCH4)', 'coolant.methane'],
        ['lh2', 'Hydrogen (LH2)', 'coolant.hydrogen'],
    ];

    const FLOW_DIRECTIONS = [
        ['counterflow', 'Counterflow (exit → chamber)', 'coolant.counterflow'],
        ['coflow', 'Co-flow (chamber → exit)', 'coolant.coflow'],
    ];

    /* ÖH D27 a4 · P11B5-15 — LİMİTSİZ MALZEMEDE YEŞİL HÜKÜM YOK.

       ÖLÇÜLDÜ (a4/once.json, `p11b5_15_wallkind_limitsiz_yesil` = 1):
       fonksiyonun son satırı koşulsuz `return 'ok'` idi. Üç limitin
       (erime / servis / izin verilen) HİÇBİRİ çözülemediğinde — ablatif
       astar gibi ERİMEYEN, servis sıcaklığı yayımlanmayan kayıtlarda tam
       olarak böyle olur — panel YEŞİL `WALL WITHIN LIMIT` basıyordu.
       Ölçülen vakada T_wall,hot = 3.249,6 K'de yeşil rozet çıkıyordu:
       kıyaslanacak bir limit YOKKEN "limit içinde" hükmü veriliyordu.

       FAIL-CLOSED: hüküm ancak KIYASLANACAK BİR LİMİT varsa kazanılır.
       Limit yoksa dönüş 'dim' ve çağıran taraf yeşil rozet yerine
       "limit yayımlanmadı" rozetini basar. Sayı uydurulmaz, hüküm
       uydurulmaz. */
    const WALL_LIMIT_FIELDS = ['material_melting_K',
                               'material_service_limit_K',
                               'material_allowable_temp_K'];

    function wallLimitsResolved(summary) {
        return WALL_LIMIT_FIELDS.filter(function (f) {
            return Number.isFinite(summary && summary[f]);
        });
    }

    // Tepe cidar sıcaklığının malzeme limitlerine göre önem derecesi
    function wallKind(summary) {
        const t = summary.max_wall_hot_K;
        if (typeof t !== 'number' || !Number.isFinite(t)) return 'dim';
        if (Number.isFinite(summary.material_melting_K) && t > summary.material_melting_K) return 'err';
        if (Number.isFinite(summary.material_service_limit_K) && t > summary.material_service_limit_K) return 'err';
        if (Number.isFinite(summary.material_allowable_temp_K) && t > summary.material_allowable_temp_K) return 'warn';
        // Kıyas noktası yoksa hüküm KAZANILMAMIŞTIR.
        if (!wallLimitsResolved(summary).length) return 'dim';
        return 'ok';
    }

    // ------------------------------------------------------------------
    // Sıcaklık profili: T_wall_hot / T_wall_cold / T_coolant + limit çizgileri
    // ------------------------------------------------------------------
    function temperaturePlot(root, cooling) {
        if (typeof Plotly === 'undefined') return false;
        const x = Array.isArray(cooling.x_mm) ? cooling.x_mm : [];
        if (!x.length) return false;
        const sm = cooling.summary || {};

        const traces = [];
        const sameLen = function (a) { return Array.isArray(a) && a.length === x.length; };
        if (sameLen(cooling.T_wall_hot_K)) {
            traces.push({
                x: x, y: cooling.T_wall_hot_K, name: T('panel.regen.sHotWall', 'Hot-wall T (gas side)'),
                type: 'scatter', mode: 'lines', line: { color: '#ff5d73', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall,hot = %{y:.0f} K<extra></extra>',
            });
        }
        if (sameLen(cooling.T_wall_cold_K)) {
            traces.push({
                x: x, y: cooling.T_wall_cold_K, name: T('panel.regen.sColdWall', 'Cold-wall T (coolant side)'),
                type: 'scatter', mode: 'lines', line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>T_wall,cold = %{y:.0f} K<extra></extra>',
            });
        }
        if (sameLen(cooling.T_coolant_K)) {
            traces.push({
                x: x, y: cooling.T_coolant_K, name: T('panel.regen.sCoolantBulk', 'Coolant bulk T'),
                type: 'scatter', mode: 'lines', line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>T_coolant = %{y:.0f} K<extra></extra>',
            });
        }
        if (!traces.length) return false;

        // Limit + koklaşma çizgileri (durum rengi asla "seri" değil — etiketli
        // referans çizgisi; kimlik yalnız renkle taşınmaz).
        const shapes = [];
        const annotations = [];
        function refLine(v, label, color) {
            if (typeof v !== 'number' || !Number.isFinite(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 0, y: v, xanchor: 'left', yanchor: 'bottom',
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 10, color: color },
            });
        }
        refLine(sm.material_allowable_temp_K, T('panel.regen.allowableWall', 'Allowable wall limit'), '#ff8c33');
        refLine(sm.material_melting_K, T('panel.thermal.meltingPoint', 'Melting point'), '#ff5d73');
        // RP-1 koklaşma çizgisi (yalnız RP-1: coking_threshold_K dolu)
        refLine(sm.coking_threshold_K, T('panel.regen.cokingLine', 'RP-1 coking threshold'), '#c678dd');

        // Boğaz konumu işareti
        const throatX = (typeof cooling.x_throat_mm === 'number'
            && Number.isFinite(cooling.x_throat_mm)) ? cooling.x_throat_mm : null;
        if (throatX != null) {
            shapes.push({
                type: 'line', yref: 'paper', x0: throatX, x1: throatX, y0: 0, y1: 1,
                line: { color: 'rgba(125,151,165,0.55)', width: 1, dash: 'dot' },
            });
            annotations.push({
                x: throatX, yref: 'paper', y: 1, xanchor: 'left', yanchor: 'top',
                text: T('common.throat', 'Throat'), showarrow: false, font: { size: 10, color: '#7d97a5' },
            });
        }

        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);
        Plotly.newPlot(div, traces, {
            title: T('panel.regen.chartTemps',
                'Wall & Coolant Temperatures Along the Chamber-Nozzle Axis'),
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.temperatureK', 'Temperature (K)'), rangemode: 'tozero' },
            shapes: shapes,
            annotations: annotations,
            legend: { orientation: 'h' },
            height: 380,
        }, { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Isı akısı q(x) + soğutucu basıncı P(x) (ikincil eksen)
    // ------------------------------------------------------------------
    function fluxPressurePlot(root, cooling) {
        if (typeof Plotly === 'undefined') return false;
        const x = Array.isArray(cooling.x_mm) ? cooling.x_mm : [];
        if (!x.length) return false;
        const sameLen = function (a) { return Array.isArray(a) && a.length === x.length; };
        const traces = [];
        if (sameLen(cooling.q_MW_m2)) {
            traces.push({
                // ADLANDIRMA (v2.6.27, parti 20): bu seri termal panelin
                // q(x) serisiyle AYNI anahtarı kullanıyordu ama tanımı
                // farklı — burada akı KUPLE cidar dengesinden çözülür
                // (regen_cooling.py::_station_wall_balance, q = (T_aw −
                // T_soğutucu)/(1/h_g + t_c/k_c + 1/h_c)); sıcak cidar
                // sıcaklığı sonuçtur, sabit bir referans değil. Ölçüldü
                // (panel varsayılanları, boğaz): 28,50 MW/m², T_wall_hot
                // 1263 K — termal panelin referans-cidar tasarım yükü aynı
                // sınıfta 24,1-26,0 MW/m². Tek anahtar iki tanımı taşıyamaz.
                x: x, y: cooling.q_MW_m2, name: T('panel.regen.heatFluxSeriesBalance', 'Heat flux q (coupled wall balance)'),
                type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.1f} mm<br>q = %{y:.2f} MW/m²<extra></extra>',
            });
        }
        if (sameLen(cooling.P_coolant_bar)) {
            traces.push({
                x: x, y: cooling.P_coolant_bar, name: T('panel.regen.sCoolantP', 'Coolant pressure'),
                type: 'scatter', mode: 'lines', yaxis: 'y2',
                line: { color: '#ff8c33', width: 2, dash: 'dot' },
                hovertemplate: 'x = %{x:.1f} mm<br>P = %{y:.2f} bar<extra></extra>',
            });
        }
        if (!traces.length) return false;
        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);
        Plotly.newPlot(div, traces, {
            title: T('panel.regen.chartFlux', 'Heat Flux & Coolant Pressure'),
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.heatFlux', 'Heat flux (MW/m²)'), rangemode: 'tozero' },
            yaxis2: { title: T('panel.regen.axisCoolantP', 'Coolant pressure (bar)'),
                      overlaying: 'y', side: 'right', showgrid: false },
            legend: { orientation: 'h' },
            height: 320,
        }, { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Ana render
    // ------------------------------------------------------------------
    function render(data, root) {
        const cooling = (data && data.cooling) || {};
        const sm = cooling.summary || {};

        // ---- Rozetler ----
        let badges = '';
        badges += U.badge(T('panel.regen.badgeCoolant', 'COOLANT') + ': '
            + String(sm.coolant || '—').toUpperCase(), 'info');
        badges += U.badge(T('panel.regen.badgeLiner', 'LINER') + ': '
            + String(sm.wall_material_name || sm.wall_material || '—'),
            'info', T('panel.regen.linerTip', 'Regenerative liner material (k_w, temperature limits)'));
        badges += U.badge(T('panel.regen.badgeFlow', 'FLOW') + ': '
            + String(sm.flow_direction || '—').toUpperCase(), 'dim');

        const wk = wallKind(sm);
        if (wk === 'err') {
            badges += U.badge(T('panel.regen.wallOver', 'WALL OVER LIMIT'), 'err',
                T('panel.regen.wallOverTip',
                  'Peak hot-wall temperature exceeds the material service/melting limit — '
                  + 'liner failure; increase coolant flow, change material or resize channels.'));
        } else if (wk === 'warn') {
            badges += U.badge(T('panel.regen.wallNear', 'WALL NEAR LIMIT'), 'warn',
                T('panel.regen.wallNearTip',
                  'Peak hot-wall temperature exceeds the allowable (strength) limit — margin reduced.'));
        } else if (wk === 'ok') {
            // Hangi limite göre "içinde"? Rozet artık kıyas noktalarını da
            // taşır — "limit içinde" hükmü ancak bir limit adıyla anlamlı.
            badges += U.badge(T('panel.regen.wallWithin', 'WALL WITHIN LIMIT'),
                'ok', 'Compared against: ' + wallLimitsResolved(sm).join(', '));
        } else if (wk === 'dim' && Number.isFinite(sm.max_wall_hot_K)) {
            // P11B5-15: cidar sıcaklığı ÇÖZÜLDÜ ama kıyaslanacak limit
            // yayımlanmadı (ablatif / limitsiz kayıt). Eskiden burada
            // YEŞİL rozet vardı; artık hükmün geri çekildiği yazılıyor.
            badges += U.badge(T('panel.regen.wallNoLimit',
                                'WALL LIMIT NOT PUBLISHED'), 'warn',
                'No melting / service / allowable temperature was published '
                + 'for this liner material, so no "within limit" verdict is '
                + 'earned for T_wall,hot = '
                + U.fmt(sm.max_wall_hot_K, 1) + ' K.');
        }
        if (sm.coking) {
            badges += U.badge(T('panel.regen.coking', 'RP-1 COKING'), 'err',
                T('panel.regen.cokingTip',
                  'Coolant-side wall temperature exceeds the ~561 K RP-1 coking threshold — '
                  + 'carbon deposition and channel fouling likely (Huzel & Huang Ch. 4).'));
        }

        // ---- Sayısal kartlar ----
        const marginKind = (typeof sm.wall_temp_margin_K === 'number'
            && Number.isFinite(sm.wall_temp_margin_K))
            ? (sm.wall_temp_margin_K < 0 ? 'err' : (sm.wall_temp_margin_K < 100 ? 'warn' : 'ok'))
            : 'dim';
        const head = document.createElement('div');
        head.innerHTML = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`
            + `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.regen.cardPeakWall', 'PEAK WALL T'), U.fmt(sm.max_wall_hot_K, 0), 'K', wk,
                U.tf('panel.regen.cardPeakWallTip', { x: U.fmt(sm.max_wall_hot_x_mm, 1) },
                     'Peak hot-wall (gas side) temperature at x = {x} mm'))
            + U.statCard(T('panel.regen.cardMargin', 'WALL MARGIN'), U.fmt(sm.wall_temp_margin_K, 0), 'K', marginKind,
                T('panel.regen.cardMarginTip', 'Allowable limit − peak wall temperature'))
            + U.statCard(T('panel.regen.cardExitT', 'COOLANT EXIT T'), U.fmt(sm.coolant_exit_temp_K, 0), 'K', 'info',
                T('panel.regen.cardExitTip', 'Coolant bulk temperature at the outlet'))
            + U.statCard(T('panel.regen.cardDeltaT', 'COOLANT ΔT'), U.fmt(sm.coolant_dT_K, 0), 'K', 'dim',
                T('panel.regen.cardDeltaTip', 'Total coolant temperature rise (enthalpy balance)'))
            + U.statCard(T('panel.regen.cardDrop', 'PRESSURE DROP'), U.fmt(sm.total_pressure_drop_bar, 2), 'bar', 'info',
                T('panel.regen.cardDropTip', 'Darcy-Weisbach + Haaland friction across the channels'))
            + U.statCard(T('panel.regen.cardPeakFluxBalance', 'PEAK HEAT FLUX (coupled wall balance)'),
                U.fmt(sm.peak_heat_flux_MW_m2, 2), 'MW/m²', 'dim',
                T('panel.regen.cardPeakFluxTip',
                  'Peak of the coupled gas/wall/coolant station balance '
                  + 'q = (T_aw - T_coolant)/(1/h_g + t_w/k_w + 1/h_c); the '
                  + 'hot-wall temperature is solved, not a fixed reference'))
            + U.statCard(T('panel.regen.cardMaxV', 'MAX VELOCITY'), U.fmt(sm.max_coolant_velocity_m_s, 1), 'm/s', 'dim', '')
            + U.statCard(T('panel.regen.cardMinRe', 'MIN REYNOLDS'), U.fmt(sm.min_reynolds, 0), '', 'dim',
                T('panel.regen.cardMinReTip',
                  'Minimum channel Reynolds number (Dittus-Boelter turbulent floor ~1e4)'))
            + '</div>';
        root.appendChild(head);

        // ---- Grafikler ----
        temperaturePlot(root, cooling);
        fluxPressurePlot(root, cooling);

        // ---- Uyarılar + model notu ----
        const tail = document.createElement('div');
        let html = '';
        if (Array.isArray(sm.warnings) && sm.warnings.length) {
            html += U.listBlock(T('common.warnings', 'Warnings'), sm.warnings, 'warn');
        }
        // ÖH D22 / P4B2-10 — Dittus-Boelter GEÇERLİLİK ZARFI panele iniyor.
        // Zarf taraması ürün yoluna yeni girdi; sayısı ve ihlalleri
        // kullanıcıya gösterilmezse tarama yine görünmez kalırdı. Yeni
        // i18n ANAHTARI AÇILMADI (anahtar dosyaları arayuz kulvarında):
        // satırlar mevcut "model varsayımları" bloğuna ekleniyor.
        const notlar = [];
        if (cooling.model_note) { notlar.push(cooling.model_note); }
        /* ÖH D26 / OH-B3-02 — CİDAR SICAKLIĞI KAÇ İSTASYONDA
           EKSTRAPOLASYONLA GELDİ?
           ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``:
           cooling_clamped_stations = 0): /api/regen-cooling
           `summary.property_table_clamped_stations` yayımlıyor —
           özellik tablosunun GEÇERLİ BANDI DIŞINA düşüp kırpılan istasyon
           sayısı — ve cooling_panel.js basmıyordu. Yukarıdaki "PEAK WALL
           T" / "WALL MARGIN" kartları bu istasyonların sayılarıyla
           kuruluyor; kaçının bant dışında olduğu ekranda yazmıyorsa
           kullanıcı hepsini ölçülmüş sanır.
           tests/test_wave4b_contract.py bunu 'cooling/summary' altında
           xfail(strict) borç imiyle taşıyordu.
           SIFIR da bir cevaptır ("hiçbiri kırpılmadı") ve söylenir. */
        const kirpilan = sm.property_table_clamped_stations;
        if (kirpilan !== null && kirpilan !== undefined) {
            notlar.push('property_table_clamped_stations = '
                + U.fmt(kirpilan, 0)
                + ' — coolant property lookups that fell OUTSIDE the '
                + 'validated table band and were clamped to its edge; the '
                + 'wall temperature at those stations is an extrapolation, '
                + 'not a table reading.');
        }
        const dbz = cooling.dittus_boelter_envelope;
        if (dbz) {
            notlar.push('Dittus-Boelter validity envelope: Re_min = '
                + U.fmt(dbz.reynolds_min, 0)
                + ', Pr = ' + U.fmt(dbz.prandtl_min, 2)
                + '-' + U.fmt(dbz.prandtl_max, 2)
                + ', L/D = ' + U.fmt(dbz.length_over_diameter, 1)
                // ÖH D25 / P11B2-12: `|| 0` yerine komşu satırların
                // dürüst biçimlendiricisi (U.fmt -> '—').
                + ' over ' + U.fmt(dbz.stations_using_dittus_boelter, 0)
                + ' station(s), channel length '
                + U.fmt(dbz.channel_length_m, 3) + ' m — '
                + (dbz.in_envelope ? 'satisfied.' : 'VIOLATED.'));
            if (Array.isArray(dbz.violations)) {
                dbz.violations.forEach(function (v) { notlar.push(v); });
            }
            if (dbz.note) { notlar.push(dbz.note); }
            if (dbz.sieder_tate_correction_applied === false) {
                notlar.push('Sieder-Tate correction applied: no.');
            }
            if (dbz.scatter_pct) {
                notlar.push('Reported scatter: +/-'
                    + U.fmt(dbz.scatter_pct, 0) + '%.');
            }
        }
        if (notlar.length) {
            html += U.listBlock(T('common.modelAssumptions', 'Model assumptions & limits'),
                                notlar, 'dim');
        }
        tail.innerHTML = html;
        root.appendChild(tail);
    }

    // ------------------------------------------------------------------
    // Kayıt
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: 'cooling',
        title: 'Regenerative Cooling — 1D Station March (Bartz + Dittus-Boelter)',
        titleKey: 'panel.regen.title',
        category: 'THERMAL',
        endpoint: '/api/regen-cooling',
        motorTypes: ['liquid'],
        long: true,
        fields: [
            ['chamber_pressure', 'Chamber Pressure (bar)', 50, 1, 'common.f.chamberPressureBar', 'panel.regen.help.chamber_pressure'],
            ['chamber_temperature', 'Chamber Temperature (K)', 3400, 10, 'common.f.chamberTemperatureK', 'panel.regen.help.chamber_temperature'],
            ['throat_diameter', 'Throat Diameter (m)', 0.05, 0.001, 'common.f.throatDiameterM', 'panel.regen.help.throat_diameter'],
            ['expansion_ratio', 'Expansion Ratio', 8, 0.1, 'common.f.expansionRatio', 'panel.regen.help.expansion_ratio'],
            ['gamma', 'Gamma (frozen)', 1.2, 0.01, 'common.f.gammaFrozen', 'panel.regen.help.gamma'],
            ['molecular_weight', 'Molecular Weight (g/mol)', 22, 0.5, 'common.f.molecularWeight', 'panel.regen.help.molecular_weight'],
            // ÖH A2 sivi-sogutma · 7. tur (F-17 ilkesi: kaynaksız ön-dolgu
            // yok): soğutucu 'water', giriş sıcaklığı 300 K, giriş basıncı
            // 60 bar, kanal genişliği 2,0 mm, derinliği 3,0 mm ve astar
            // 1,0 mm hiçbir hesaptan gelmiyordu. Tanım değeri artık BOŞ;
            // ön-dolgu motorun YAYIMLADIĞI değerdir (fromResults; yalnız
            // sonlu pozitif, yalnız kanal devresi varken). Yayımlanmamışsa
            // alan boş kalır ve ZORUNLUDUR (spec.required): güverte isteği
            // göndermez, eksik alanı adıyla söyler.
            ['coolant', 'Coolant', '', COOLANTS, 'panel.regen.fCoolant', 'panel.regen.help.coolant'],
            ['coolant_mdot', 'Coolant Mass Flow (kg/s)', 2.0, 0.05, 'panel.regen.fCoolantMdot', 'panel.regen.help.coolant_mdot'],
            ['coolant_inlet_temp', 'Coolant Inlet T (K)', '', 5, 'panel.regen.fInletT', 'panel.regen.help.coolant_inlet_temp'],
            ['coolant_inlet_pressure', 'Coolant Inlet P (bar)', '', 1, 'panel.regen.fInletP', 'panel.regen.help.coolant_inlet_pressure'],
            // ÖH A2 sivi-sogutma · 6. tur (F-17 ilkesi: kaynaksız ön-dolgu
            // yok): eskiden 80 yazılı geliyordu — hiçbir hesaptan değil. Ön-dolgu
            // artık /calculate_liquid'in YAYIMLADIĞI kanal sayısıdır
            // (cooling_system.cooling_channels, fromResults); motor sonucu yoksa
            // ya da N yayımlanmadıysa alan BOŞ kalır ve uç n_channels'ı adıyla
            // ister (HTTP 400) — uydurma sayıyla hesap yapılmaz.
            ['n_channels', 'Number of Channels', '', 1, 'panel.regen.fChannels', 'panel.regen.help.n_channels'],
            ['channel_width', 'Channel Width (mm)', '', 0.1, 'panel.regen.fChannelW', 'panel.regen.help.channel_width'],
            ['channel_height', 'Channel Height (mm)', '', 0.1, 'panel.regen.fChannelH', 'panel.regen.help.channel_height'],
            ['wall_thickness', 'Liner Thickness (mm)', '', 0.1, 'panel.regen.fLinerThickness', 'panel.regen.help.wall_thickness'],
            ['wall_material', 'Liner Material', 'copper', WALL_MATERIALS, 'panel.regen.fLinerMaterial', 'panel.regen.help.wall_material'],
            ['flow_direction', 'Flow Direction', 'counterflow', FLOW_DIRECTIONS, 'panel.regen.fFlowDir', 'panel.regen.help.flow_direction'],
        ],
        // 'BOŞ + ZORUNLU' beyanı (analysis_dock.requiredFieldInfo): tanım
        // değeri boş olan bu alanlar isteğe bağlı DEĞİL — uç n_channels'ı
        // adıyla ister, kalanlar için güverte isteği durdurur.
        required: ['n_channels', 'coolant', 'coolant_inlet_temp',
                   'coolant_inlet_pressure', 'channel_width',
                   'channel_height', 'wall_thickness'],
        // Sıvı motor sonuçlarından otomatik dolum: soğutucu = yakıt akışı.
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const sug = {};
            if (Number.isFinite(m.chamber_pressure)) sug.chamber_pressure = m.chamber_pressure;
            if (Number.isFinite(m.chamber_temperature)) sug.chamber_temperature = m.chamber_temperature;
            // BİRİM: alan METRE etiketli; katı motorda throat_diameter
            // 17,96 (mm) geliyordu ve panel 17,96 m boğaz çapıyla hesap
            // yapıyordu. Merkezi çözümleyici metreye getiriyor.
            const dtM = U.readLengthM(r, 'throat_diameter');
            if (Number.isFinite(dtM)) sug.throat_diameter = dtM;
            if (Number.isFinite(m.expansion_ratio) && m.expansion_ratio > 1) {
                sug.expansion_ratio = m.expansion_ratio;
            }
            if (Number.isFinite(m.gamma)) sug.gamma = m.gamma;
            if (Number.isFinite(m.molecular_weight)) sug.molecular_weight = m.molecular_weight;
            // Rejeneratif soğutucu tipik olarak yakıttır → yakıt debisini öner.
            // Eski kod 'fuel_flow' (yalnız sıvıda var) ve 'mdot_fuel' (HİÇBİR
            // çözücüde yok) anahtarlarını arıyordu; hibritin gerçek anahtarı
            // 'mdot_f'. Hibritte alan 2,0 kg/s panel varsayılanında kalıyordu,
            // gerçek yakıt debisi 0,158 kg/s — 12,6 kat fazla soğutucu.
            // Kanal sayısı: motorun yayımladığı N (pozitif TAM sayı). Yoksa
            // öneri yok — alan tanım değerinde (boş) kalır, uç adıyla reddeder.
            const cs = (r && typeof r.cooling_system === 'object' && r.cooling_system) || {};
            const nPub = cs.cooling_channels;
            if (Number.isInteger(nPub) && nPub >= 1) {
                sug.n_channels = nPub;
                // 7. tur (F-17): kanal devresi VARSA motorun yayımladığı
                // kesit, astar, soğutucu ve giriş hâli. Devre yoksa (ablatif,
                // ışınımsal, sığmayan ceket) bu sayılar motorun varsayılan
                // kalıntısıdır (bkz. liquid_rocket_engine kanalsız beyanı) —
                // önerilmez, alan boş kalır.
                const pozitif = function (v) {
                    return (typeof v === 'number' && Number.isFinite(v) && v > 0) ? v : null;
                };
                const w = pozitif(cs.channel_width_mm);
                if (w !== null) sug.channel_width = w;
                const h = pozitif(cs.channel_height_mm);
                if (h !== null) sug.channel_height = h;
                // Marşın ısıyı İLETTİĞİ sıcak cidar (RP-1: hazne cidarı;
                // süperkritik: astar) — sığma bloğunda künyesiyle yayımlanır.
                const fit = (cs.channel_count_fit && typeof cs.channel_count_fit === 'object')
                    ? cs.channel_count_fit : {};
                const tw = pozitif(fit.hot_wall_thickness_mm);
                if (tw !== null) sug.wall_thickness = tw;
                const tin = pozitif(cs.coolant_inlet_temperature);
                if (tin !== null) sug.coolant_inlet_temp = tin;
                // Giriş basıncını motor YALNIZ süperkritik marşta yayımlar;
                // RP-1 marşının giriş basıncı yanıtta yok → alan boş kalır.
                const sc = (cs.regen_supercritical && typeof cs.regen_supercritical === 'object')
                    ? cs.regen_supercritical : {};
                const pin = pozitif(sc.inlet_pressure_bar);
                if (pin !== null) sug.coolant_inlet_pressure = pin;
                // Soğutucu = yakıt (motorun marşı da yakıtı soğutucu alır).
                // Seçicide olmayan ad güvertenin kapısına düşer (seçim
                // değişmez, koşum durur, gerekçe ekranda).
                const yakit = (typeof r.fuel_type === 'string') ? r.fuel_type.trim() : '';
                if (yakit) sug.coolant = yakit;
            }
            const mdotFuel = U.readFuelFlow(r);
            if (Number.isFinite(mdotFuel) && mdotFuel > 0) sug.coolant_mdot = mdotFuel;
            return sug;
        },
        render: render,
    });

    /* ÖH D27 a4 · P11B5-15 — REJENERATİF ASTAR SEÇİCİSİNDEN ABLATİF ÇIKAR.

       ÖLÇÜLDÜ (a4/once.json, `p11b5_15_astar_ablatif_suzgeci` = 0): katalog
       yüklendiğinde seçici 'liner'+'shell' etiketli TÜM kayıtları sunuyordu
       ve `materials_db.py` içindeki `ablative` kaydının etiketleri
       ['ablative', 'liner'] — yani silika-fenolik ablatif astar rejeneratif
       KANAL malzemesi olarak seçilebiliyordu. Ablatif astar kömürleşerek
       kütle kaybeder; içine soğutma kanalı işlenmez ve bu panelin modeli
       (Bartz + Dittus-Boelter + ince cidar iletimi) o malzeme için
       tanımsızdır. Seçilebilir olması, panelin kendisinin çözemeyeceği bir
       konfigürasyonu meşru gösteriyordu.

       Süzgeç KATALOĞUN KENDİ etiketinden okunur; bu dosyada malzeme adı
       listesi tutulmaz (tek kaynak: materials_db 'tags'). */
    const NON_REGEN_TAG = 'ablative';

    function ablatifAnahtarlar(H) {
        const kayitlar = H.list(['liner', 'shell']) || [];
        const out = {};
        kayitlar.forEach(function (m) {
            const t = m.tags || [];
            if (t.indexOf(NON_REGEN_TAG) !== -1) out[m.key] = true;
        });
        return out;
    }

    // Merkezi katalog yüklüyse liner select'ini 'liner'+'shell' etiketli
    // listeyle doldur; değilse fallback aynen kalır.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        const H = window.HRMAMaterials;
        H.populateSelect({
            panelId: 'cooling', fieldId: 'wall_material',
            tags: ['liner', 'shell'], fallback: WALL_MATERIALS,
        }).then(function (ok) {
            if (!ok) return;
            const yasak = ablatifAnahtarlar(H);
            if (!Object.keys(yasak).length) return;
            // 1) Henüz monte edilmemiş paneller spec.fields üzerinden bu
            //    diziyi okur — yerinde süz.
            for (let i = WALL_MATERIALS.length - 1; i >= 0; i--) {
                if (yasak[WALL_MATERIALS[i][0]]) WALL_MATERIALS.splice(i, 1);
            }
            // 2) Monte edilmiş select varsa seçeneği kaldır; seçili olan
            //    yasaklıysa listenin ilk geçerli kaydına düş.
            const el = document.getElementById('ad_f_cooling_wall_material');
            if (el && el.tagName === 'SELECT') {
                const secili = el.value;
                Array.prototype.slice.call(el.options).forEach(function (o) {
                    if (yasak[o.value]) el.removeChild(o);
                });
                if (yasak[secili] && el.options.length) el.selectedIndex = 0;
            }
        });
    }

    // Test / hata ayıklama: saf render + çizim yardımcıları
    window.CoolingPanel = {
        _render: render,
        _temperaturePlot: temperaturePlot,
        _fluxPressurePlot: fluxPressurePlot,
        _wallKind: wallKind,
        _wallLimitsResolved: wallLimitsResolved,
        _ablatifAnahtarlar: ablatifAnahtarlar,
        _wallMaterials: WALL_MATERIALS,
    };
})();
