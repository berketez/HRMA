/* ====================================================================
   HRMA Analiz Güvertesi — Basınçlı Kap Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/pressure-vessel-analysis sonucunu çizer:
   - Kod modu seçici: AIAA S-080 (uçuş) / ASME VIII Div 1 (yer)
   - Başlık metriği: actual_burst_pressure_bar — MODELLE TAHMİN EDİLEN kopma
     basıncı (ÖH D31 / OH-D30-13: 'actual' adı ölçülmüş dayanım DEĞİLDİR;
     min(Faupel 1956, ince cidar membran limiti) kestirimidir. Kart etiketi
     ve ipucu bunu söyler; ucun künyesi actual_burst_pressure_basis)
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
    // ÖH D24 / OH-D23-03 — varsayılan malzeme: ÖNCE sunucunun ilan
    // ettiği değer (materials_catalog.js -> /api/materials.
    // default_structural_material). Katalog betiği hiç yüklenmemişse
    // son çare ikiz sabit kullanılır; bu ikizin sunucudan AYRIŞMASI
    // bekçiyle yasaktır (tests/test_d24_fix_asamasi.py, panel
    // ikizlerini sunucu değeriyle EŞİTLER). Boş bırakmak seçenek
    // değildir: cıvatalı bağlantı ucu member_material'ı ZORUNLU
    // tutar (ÖH D15 / P5B1-05 fail-closed) ve panel varsayılan
    // koşumda 400 alırdı.
    var VARSAYILAN_MALZEME = (typeof window.HRMAMaterials !== 'undefined'
        && window.HRMAMaterials.defaultStructuralMaterial)
        ? window.HRMAMaterials.defaultStructuralMaterial()
        : 'aluminum_6061';   /* ikiz — bekçi sunucuyla eşitler */

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

    /* ÖH D30 · P11B4-15 — KAZANILMAMIŞ YEŞİL.
       ÖLÇÜLDÜ (a2/once.json: P11B4-15_marginKind_auto_sized_kapisi = 1 →
       yalnız rozet; _hedef_geri_okumasi_beyani = 0): duvar kalınlığı
       VERİLMEDİĞİNDE `pressure_vessel.py` cidarı `target_burst =
       MARGINAL_BURST_MARGIN * p_burst_req` ile boyutlandırır
       (pressure_vessel.py:811, MARGINAL_BURST_MARGIN = 1.2). Geri dönen
       `burst_margin` bu yüzden ≈ 1,20'dir ve panelin eşiği tam orada
       ("m < 1.2 → warn, değilse ok") durduğu için kart YEŞİL yanıyordu.
       O yeşil bir DOĞRULAMA değil, boyutlandırıcının kendi hedefinin geri
       okumasıdır — model kendi koyduğu hedefi kendi ölçüp geçti diyor.
       (Kardeş desen: fea_panel `badgeEngineSfTautological`.)

       Onarım: OLUMSUZ dallar (FAIL / MARGINAL) auto-sized durumda da
       aynen basılır — onlar gerçek bilgidir. Kazanılmamış olan yalnız
       ONAY yeşilidir: auto-sized iken 'ok' verilmez, kart nötr ('info')
       kalır ve ipucunda nedeni yazar. Eşik SAYISI gevşetilmedi. */
    function marginKind(m, autoSized) {
        if (m == null || !Number.isFinite(m)) return 'dim';
        if (m < 1.0) return 'err';
        if (m < 1.2) return 'warn';   // pressure_vessel.py MARGINAL eşiği
        return autoSized ? 'info' : 'ok';
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
            // ÖH D31 / OH-D30-13 — DÜRÜST AD ÖNCE OKUNUR.
            // Uç aynı sayıyı iki adla yayımlıyor: tarihsel
            // `actual_burst_pressure_bar` ve dürüst
            // `predicted_burst_pressure_bar`. Kart dürüst adı okur, eski
            // ad yalnız GERİYE DÖNÜK yedektir (eski sürüm uçları). İpucu
            // ucun KENDİ künyesini basar; metin panelde İCAT EDİLMEZ.
            + U.statCard(T('panel.vessel.cardBurst', 'Predicted burst pressure'),
                U.fmt(Number.isFinite(d.predicted_burst_pressure_bar)
                          ? d.predicted_burst_pressure_bar
                          : d.actual_burst_pressure_bar, 1), 'bar',
                marginKind(d.burst_margin, d.auto_sized),
                d.actual_burst_pressure_basis
                    || T('panel.vessel.cardBurstTip',
                         'min(Faupel thick-wall, thin-wall plastic limit) — the pressure at which '
                         + 'this vessel is predicted to rupture'))
            + U.statCard(T('panel.vessel.cardMargin', 'Burst margin'), U.fmt(d.burst_margin, 2),
                T('panel.vessel.timesRequired', '× required'),
                marginKind(d.burst_margin, d.auto_sized),
                d.auto_sized
                    ? U.tf('panel.vessel.cardMarginAutoTip',
                           { req: U.fmt(d.required_burst_pressure_bar, 1) },
                           'Predicted burst / required burst ({req} bar). No wall '
                           + 'thickness was supplied, so the wall was sized to hit '
                           + 'this very margin: the number reads back the sizing '
                           + 'target and is not an independent verification.')
                    : U.tf('panel.vessel.cardMarginTip',
                           { req: U.fmt(d.required_burst_pressure_bar, 1) },
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
             (d.proof_pressure_bar === null
              || d.proof_pressure_bar === undefined)
                 ? `<span style="color:var(--hd-ink-dim, #7d97a5);">—</span>`
                 : U.fmt(d.proof_pressure_bar, 1) + ' bar',
             d.proof_pressure_basis
                 || T('panel.vessel.proofTip', 'AIAA S-080 proof factor')],
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
            // OH-D30-13: iki korelasyonun MİNİMUMU olan yayımlanan sayı,
            // künyesiyle birlikte merdivende de durur ki okuyucu "ölçülmüş
            // dayanım" sanmasın.
            [T('panel.vessel.burstPredicted',
               'Burst — published prediction (min of the two above)'),
             U.fmt(Number.isFinite(d.predicted_burst_pressure_bar)
                       ? d.predicted_burst_pressure_bar
                       : d.actual_burst_pressure_bar, 1) + ' bar',
             d.actual_burst_pressure_basis || ''],
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

        // ÖH D24 / OH-D23-03 — VARSAYILAN KÜNYESİ EKRANA İNER.
        // Uç, ``material`` gönderilmediğinde kendi varsayılanını uygular ve
        // bunu ``defaults_applied`` ile BEYAN eder. Beyanı kimse basmazsa
        // beyan değildir: kullanıcı, kabın hangi malzemede boyutlandığını
        // yine göremez. Alan yanıtta HİÇ yoksa (eski uç) blok basılmaz —
        // olmayan bir beyan uydurulmaz. Boş liste beyanın KENDİSİDİR
        // ("hiçbir alan varsayılandan gelmedi") ve gösterilir.
        if (Array.isArray(d.defaults_applied)) {
            var kunyeBasligi = T('panel.vessel.secDefaults',
                'Inputs the endpoint filled from its own defaults');
            if (d.defaults_applied.length) {
                html += U.listBlock(kunyeBasligi,
                    d.defaults_applied.map(function (k) {
                        return (k && k.message)
                            ? k.message
                            : ((k && k.field) + ' = ' + (k && k.value));
                    }), 'warn');
            } else {
                html += U.listBlock(kunyeBasligi,
                    [T('panel.vessel.defaultsNone',
                       'None - every input below came from this form.')],
                    'dim');
            }
        }

        html += U.listBlock(T('common.warnings', 'Warnings'), d.warnings, 'warn');
        html += U.listBlock(T('common.assumptions', 'Assumptions'), d.assumptions, 'dim');
        mid.innerHTML = html;
        root.appendChild(mid);

        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, d, { deep: true });
    }

    window.AnalysisDock.register({
        id: 'vessel',
        title: 'Pressure Vessel — Sizing, MAWP & Real Burst Pressure',
        titleKey: 'panel.vessel.title',
        category: 'PRESSURE VESSEL',
        endpoint: '/api/pressure-vessel-analysis',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['code_mode', 'Design Code', 'aiaa_s080', CODE_MODES, 'panel.vessel.fDesignCode', 'panel.vessel.help.code_mode'],
            ['meop_bar', 'MEOP (bar)', 60, 1, 'panel.vessel.fMeop', 'panel.vessel.help.meop_bar'],
            ['inner_diameter_mm', 'Inner Diameter (mm)', 150, 1, 'common.f.innerDiameterMm', 'panel.vessel.help.inner_diameter_mm'],
            ['wall_thickness_mm', 'Wall Thickness (mm, blank = auto-size)', '', 0.1,
             'panel.vessel.fWallAuto', 'panel.vessel.help.wall_thickness_mm'],
            ['material', 'Material', VARSAYILAN_MALZEME, MATERIALS, 'common.f.material', 'panel.vessel.help.material'],
            ['temperature_K', 'Design Temperature (K)', 293.15, 5, 'common.f.designTemperatureK', 'panel.vessel.help.temperature_K'],
            ['weld_efficiency', 'Weld Joint Efficiency (UW-12)', '1.00', WELD_EFF,
             'panel.vessel.fWeld', 'panel.vessel.help.weld_efficiency'],
            ['head_type', 'Head Type', 'ellipsoidal_2_1', HEAD_TYPES, 'panel.vessel.fHeadType', 'panel.vessel.help.head_type'],
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            // MEOP = hazne basıncı (bar) — plan Dalga 3 fromResults eşlemesi
            if (Number.isFinite(m.chamber_pressure)) {
                out.meop_bar = m.chamber_pressure;
            }
            // BİRİM (2026-07-30 ölçümü): buradaki koşulsuz `* 1000` YALNIZ
            // hibritte doğruydu. Katı motorda chamber_diameter 75,0 ve sıvıda
            // 120,0 zaten MİLİMETRE geliyor — panel 75 000 mm (75 m) ve
            // 120 000 mm (120 m) iç çaplı bir basınçlı kap boyutlandırıyordu.
            // Çevirme merkezi tabloya taşındı (termal panel aynı alanı ters
            // yönde, 1000'e BÖLEREK bozuyordu; tek kaynak ikisini de düzeltir).
            var idMm = U.readLengthMM(r, 'chamber_diameter');
            if (Number.isFinite(idMm)) {
                out.inner_diameter_mm = idMm;
            }
            // V301/K-C1 (KT-22): katı sayfada malzeme ana tasarımın KASA
            // malzemesidir (structural_analysis.case_analysis.case_material).
            // ÖLÇÜLDÜ (denetim A-kati ekran_en.json): panel kasa 'steel' iken
            // kendi varsayılanıyla (VARSAYILAN_MALZEME, Al 6061) hesaplıyordu. Yanıtta
            // malzeme yoksa varsayılan kalır ve bu ADIYLA beyan edilir
            // (güvertenin __withheld künyesi); seçenek listesinde olmayan ad
            // güvertenin kendi kapısında durur (istek gönderilmez).
            if (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function'
                    && window.AnalysisDock.getMotorType() === 'solid') {
                var kasaMalz = U.readChamberMaterial ? U.readChamberMaterial(r) : undefined;
                if (typeof kasaMalz === 'string' && kasaMalz) {
                    out.material = kasaMalz;
                } else {
                    out.material = VARSAYILAN_MALZEME;
                    var gk = {};
                    gk.material = 'case_material_not_in_results: the solid motor result '
                        + 'publishes no case material, so the panel default '
                        + VARSAYILAN_MALZEME + ' is used';
                    out[U.WITHHELD_KEY || '__withheld'] = gk;
                }
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
