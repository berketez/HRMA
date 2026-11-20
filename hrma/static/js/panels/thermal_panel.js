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
        // V307/SEKME-GÜVERTE (NK3-S-3): motorun ablatif soğutması. ÖLÇÜLDÜ
        // (olcum_once_A.json, sıvı L1 'ablative'): seçenek yoktu, alan
        // "Doğal (ısı emici)" varsayımında kalıyor ve sekme "SOĞUTMA:
        // NATURAL · Gereken soğutma alanı 266,26 m²" basıyordu. Uç bu sınıfı
        // astar yoluyla değerlendirir (heat_transfer_analysis.
        // LINER_PROTECTED_COOLING_TYPES) ve soğutma bütçesi yayımlamaz.
        ['ablative', 'Ablative Liner', 'panel.thermal.motorCooling.ablative'],
        // V307/GÜVERTE-ISIL (kalem 2): sıvı motorun öbür soğutma tipleri.
        // ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/guverte-isil/olcum_once.json,
        // örnek sıvı film / ışınım / dump): seçenek olmadığı için alan
        // "Doğal (ısı emici)" varsayımında kalıyor, sekme o motor için doğal
        // taşınımın hükmünü ("SOĞUTMA: Doğal") basıyordu. Tip artık motordan
        // taşınır; bu sekmenin (ve ucunun) bu tipler için modeli YOK, o
        // yüzden hesap yapılmaz (`SOGUTMA_MODELSIZ`, `localResult`).
        ['film_cooling', 'Film Cooling', 'panel.thermal.motorCooling.film_cooling'],
        ['radiative', 'Radiation Cooling', 'panel.thermal.motorCooling.radiative'],
        ['dump_cooling', 'Dump Cooling', 'panel.thermal.motorCooling.dump_cooling'],
    ];

    // Bu sekmenin MODELLEMEDİĞİ soğutma tipleri (sıvı motorun kendi adlarıyla;
    // uç bu adları 422 `unsupported_cooling_type` ile reddeder). Sekme bu
    // tiplerde istek göndermez; motor sonucunun soğutma bloğunu gösterir.
    const SOGUTMA_MODELSIZ = ['film_cooling', 'radiative', 'dump_cooling'];

    /* V307/GÜVERTE-ISIL (kalem 2) — MOTORUN KENDİ SOĞUTMA SONUCU (sıvı motor,
       Motor Alt Sistemleri → Soğutma Sistemi; `cooling_system` ve pasif ısıl
       koruma bloğu). Sayılar motor sonucundan AYNEN okunur, burada hesap
       yapılmaz; alan yoksa null kalır ve satırı basılmaz. */
    function motorSogutmaOku(m) {
        const cs = (m && m.cooling_system) || null;
        if (!cs || typeof cs !== 'object') return null;
        const sayi = function (v) {
            return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
        };
        const metin = function (v) { return (typeof v === 'string') ? v : ''; };
        const rad = yolOku(m, 'thermal_protection.passive_thermal_protection.radiation_equilibrium');
        return {
            tip: ilkMetin(m, SOGUTMA_YOLLARI) || '',
            toplamKw: sayi(cs.total_heat_load),
            odaKw: sayi(cs.chamber_heat_load),
            nozulKw: sayi(cs.nozzle_heat_load),
            cidarK: sayi(cs.wall_temperature_hot),
            cidarKaynak: metin(cs.wall_temperature_source),
            cozulenK: sayi(cs.wall_temperature_solved_K),
            cozumDurumu: metin(cs.wall_temperature_solved_status),
            sinirK: sayi(cs.wall_temperature_limit_K),
            sinirDurumu: metin(cs.wall_temperature_limit_status),
            filmDebisi: sayi(cs.film_cooling_flow),
            dumpCeketi: metin(cs.dump_cooling_jacket_status),
            isinim: (rad && typeof rad === 'object' && rad.status === 'modelled') ? {
                dengeK: sayi(rad.T_wall_eq_K),
                servisK: sayi(rad.service_limit_K),
                payK: sayi(rad.margin_K),
                sinirIci: (typeof rad.within_limit === 'boolean') ? rad.within_limit : null,
                malzeme: metin(rad.material_name),
            } : null,
        };
    }

    // Güvertenin `localResult` kancası: modellenmeyen soğutma tipinde uca
    // gidilmez; panel bu nesneyi çizer (motor sonucu o an okunur ve nesneyle
    // saklanır: dil değişiminde aynı sayılarla yeniden çizilir).
    function modelsizSogutmaSonucu(payload) {
        const tip = payload && payload.cooling_type;
        if (SOGUTMA_MODELSIZ.indexOf(tip) === -1) return null;
        let motor = null;
        try {
            const mt = (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
                ? window.AnalysisDock.getMotorType() : null;
            if (mt === 'liquid' && window.currentResults) {
                motor = motorSogutmaOku(U.motorDict(window.currentResults));
            }
        } catch (e) { motor = null; }
        return { cooling_not_modelled_here: true, cooling_type: tip,
                 motor_cooling: motor };
    }

    function renderModelsizSogutma(data, root) {
        const tip = String(data.cooling_type || '');
        const ad = sogutmaAdi(tip);
        const mc = data.motor_cooling;
        const sonlu = function (v) { return typeof v === 'number' && Number.isFinite(v); };
        const kutu = document.createElement('div');
        let h = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(U.tf('panel.thermal.notModelled.badge', { type: ad },
                'NOT MODELLED IN THIS TAB: {type}'), 'warn')
            + '</div>'
            + '<p data-thermal-cooling-not-modelled="' + U.esc(tip) + '"'
            + ' style="margin:8px 0; white-space:normal;">'
            + U.esc(U.tf('panel.thermal.notModelled.text', { type: ad },
                'This tab solves natural convection, forced convection, '
                + 'regenerative cooling and the ablative liner. It has no model '
                + 'for {type}, so nothing was computed and no request was sent. '
                + 'The cooling result of the motor result governs '
                + '(motor page: Engine Subsystems, Cooling System).'))
            + '</p>';
        const ayniTip = !!(mc && mc.tip === tip);
        if (!ayniTip) {
            h += '<p data-thermal-motor-cooling="absent" style="margin:8px 0;'
                + ' white-space:normal; color:var(--hd-ink-dim, #7d97a5);">'
                + U.esc(T('panel.thermal.notModelled.noMotor',
                    'The last motor result was not computed with this cooling '
                    + 'type, so there is no motor cooling result to show here.'))
                + '</p>';
            kutu.innerHTML = h;
            root.appendChild(kutu);
            return;
        }
        const rows = [[T('common.f.coolingType', 'Cooling Type'), U.esc(ad), '']];
        if (sonlu(mc.toplamKw)) {
            const parca = (sonlu(mc.odaKw) && sonlu(mc.nozulKw))
                ? ' ' + U.tf('panel.thermal.motorHeatLoadSplit',
                             { c: numL(mc.odaKw, 1), n: numL(mc.nozulKw, 1) },
                             '(chamber {c} + nozzle {n} kW)')
                : '';
            rows.push([T('panel.thermal.motorHeatLoad', 'Heat load — motor result (engine subsystems)'),
                '<span data-thermal-motor-heat-load="1">' + numL(mc.toplamKw, 1)
                + ' kW' + U.esc(parca) + '</span>', '']);
        }
        if (sonlu(mc.cidarK)) {
            const kaynak = /solved/i.test(mc.cidarKaynak)
                ? T('panel.thermal.motorWallSolved', 'the wall the motor solved')
                : (/max wall temperature/i.test(mc.cidarKaynak)
                   ? T('panel.thermal.motorWallUserMax', 'your maximum wall temperature')
                   : T('panel.thermal.motorWallAssumed', 'the motor\'s wall temperature assumption'));
            rows.push([T('panel.thermal.notModelled.loadWall',
                         'Wall temperature the heat load is taken at'),
                numL(mc.cidarK, 1) + ' K (' + U.esc(kaynak) + ')', '']);
        }
        if (mc.isinim && sonlu(mc.isinim.dengeK)) {
            const r = mc.isinim;
            let durum = '';
            if (r.sinirIci === true) {
                durum = T('panel.thermal.notModelled.withinLimit', 'within the service limit');
            } else if (r.sinirIci === false) {
                durum = T('panel.thermal.notModelled.limitExceeded', 'service limit exceeded');
            }
            rows.push([T('panel.thermal.notModelled.radWall',
                         'Wall temperature — motor result (radiation equilibrium)'),
                '<span data-thermal-motor-wall="solved" style="white-space:normal;">'
                + numL(r.dengeK, 1) + ' K'
                + (sonlu(r.servisK)
                    ? U.esc(' · ' + U.tf('panel.thermal.notModelled.radLimit',
                        { lim: numL(r.servisK, 0), m: numL(r.payK, 0) },
                        'service limit {lim} K, margin {m} K'))
                    : '')
                + (durum ? U.esc(' · ' + durum) : '')
                + '</span>', '']);
        } else if (sonlu(mc.cozulenK)) {
            rows.push([T('panel.thermal.notModelled.solvedWall',
                         'Wall temperature — motor result (solved)'),
                '<span data-thermal-motor-wall="solved">' + numL(mc.cozulenK, 1)
                + ' K</span>', '']);
        } else {
            rows.push([T('panel.thermal.notModelled.wall', 'Wall temperature — motor result'),
                '<span data-thermal-motor-wall="not-solved" style="white-space:normal;">'
                + U.esc(T('panel.thermal.notModelled.wallNotSolved',
                    'not solved: the motor chain has no wall temperature solver '
                    + 'for this cooling type; the heat load above is taken at '
                    + 'the wall temperature shown'))
                + '</span>', '']);
        }
        if (tip === 'film_cooling' && sonlu(mc.filmDebisi)) {
            rows.push([T('panel.thermal.notModelled.filmFlow',
                         'Film coolant flow — motor result'),
                numL(mc.filmDebisi, 3) + ' kg/s', '']);
        }
        if (tip === 'dump_cooling' && mc.dumpCeketi === 'NOT_MODELLED') {
            rows.push([T('panel.thermal.notModelled.dumpJacket',
                         'Dump cooling jacket — motor result'),
                U.esc(T('panel.thermal.notModelled.dumpJacketNot',
                        'not modelled in the motor result')), '']);
        }
        h += U.sectionTitle(T('panel.thermal.notModelled.title',
                              'Cooling Result of the Motor Result'))
            + '<div data-thermal-motor-cooling="shown">' + U.kvTable(rows) + '</div>';
        kutu.innerHTML = h;
        root.appendChild(kutu);
    }

    // V307/SEKME-GÜVERTE (NK3-S-9): motorun KENDİ ısı yükü (sıvı motorun
    // Motor Alt Sistemleri → Soğutma Sistemi bloğu, cooling_system). Bu
    // sekmenin "Toplam ısı gücü" ile AYNI tanım değildir (cidar sıcaklığı
    // tabanı, gaz ışınımı, Bartz katsayısının uygulanışı): iki sayı yan yana,
    // farkın nedeniyle basılır. Son motor sonucundan; yoksa null.
    let motorIsiYuku = null;

    function motorIsiYukuOku(m) {
        const cs = (m && m.cooling_system) || {};
        const sayi = function (v) {
            return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
        };
        const toplam = sayi(cs.total_heat_load);
        if (toplam === null) return null;
        return {
            toplam: toplam,                                   // kW
            oda: sayi(cs.chamber_heat_load),                  // kW
            nozul: sayi(cs.nozzle_heat_load),                 // kW
            cidarK: sayi(cs.wall_temperature_hot),            // K
            cidarKaynak: (typeof cs.wall_temperature_source === 'string')
                ? cs.wall_temperature_source : '',
        };
    }

    /* V307/GÜVERTE-ISIL (kalem 1) — MOTORUN KENDİ HAZNE ASTARI (sıvı,
       ablatif). ÖLÇÜLDÜ (docs/scofield/raw/OH/V307/guverte-isil/
       olcum_once.json): motor sonucu hazne astarını kendi Bartz zincirinin
       hazne katsayısıyla boyutlandırıyor (L1: 1,59 mm, gerileme 0,1375 mm/s);
       bu sekme aynı istasyonu ucun kendi ısı zincirinden yeniden türetiyordu
       (7,78 mm, 0,2080 mm/s) — aynı çekirdek, iki girdi, iki sayı; 50 bar
       örnekte iki ayrı ret (0,367 ⟷ 0,405 mm/s). Sekme artık motorun astar
       istasyonu girdilerini gövdeye koyar (form dışı bağlam): gerileme hızı,
       gerileme payı ve zarf hükmü motor sonucuyla aynıdır; bu sekmenin
       eklediği iletim payı ayrı satırda, adıyla durur. Son motor sonucundan;
       yoksa null. */
    let motorAstar = null;

    // `hibrit`: hibrit motorun astar bloğu ısıl koruma bloğunun kökündedir ve
    // kalınlığı iletim payını İÇERİR (hybrid_liner_sizing; bu sekmenin
    // kuralıyla aynı işlev).
    function motorAstarOku(m, hibrit) {
        const tp = (m && m.thermal_protection) || null;
        const p = hibrit ? tp : (tp && tp.passive_thermal_protection) || null;
        if (!p || typeof p !== 'object' || p.status !== 'modelled') return null;
        const cl = p.chamber_liner;
        if (!cl || typeof cl !== 'object') return null;
        const sayi = function (v) {
            return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
        };
        return {
            iletimDahil: sayi(cl.conduction_allowance_mm) !== null,
            kalinlikMm: sayi(cl.thickness),                    // mm
            durum: (typeof cl.thickness_status === 'string') ? cl.thickness_status : '',
            gerilemeMmS: sayi(cl.recession_rate_mm_s),
            hGaz: sayi(cl.h_gas_W_m2K),                        // W/m²K
            tSurucu: sayi(cl.T_recovery_K),                    // K
            cpGaz: sayi(cl.gas_cp_J_kgK),                      // J/kgK
        };
    }

    // Soğutma sınıfının okunur adı (rozet ve satırlar; ham değer basılmaz).
    function sogutmaAdi(v) {
        for (let i = 0; i < COOLING.length; i++) {
            if (COOLING[i][0] === v) return T(COOLING[i][2], COOLING[i][1]);
        }
        return coolingTypeName(v);
    }

    // V307/SEKME-GÜVERTE (NK3-S-3): soğutma bütçesi geri çekme kodları
    // (heat_transfer_analysis.COOLING_BUDGET_WITHHELD_*) -> okunur neden.
    const SOGUTMA_BUTCESI_GERI = {
        liner_protected_wall: ['panel.thermal.coolBudget.liner',
            'Not published: the ablative liner verdict governs. The liner '
            + 'absorbs the hot-gas heat, so a steady convection area budget of '
            + 'the bare wall does not describe this wall.'],
        supplied_wall_temperature: ['panel.thermal.coolBudget.supplied',
            'Not published: the supplied wall temperatures govern (the case '
            + 'temperature the motor solved behind its insulation). A steady '
            + 'natural-convection area budget of the bare wall does not '
            + 'describe this wall.'],
        ablative_cooling_class: ['panel.thermal.coolBudget.ablative',
            'Not published: ablative cooling. The liner absorbs the hot-gas '
            + 'heat by recession and conduction; a convection area budget and '
            + 'a cooling-class efficiency do not apply.'],
    };

    // V301/ÖRNEK-PANEL — cidar koruması (heat_transfer_analysis.
    // SUPPORTED_WALL_PROTECTIONS ile aynı değerler; uç başka değeri 422 ile
    // adıyla reddeder).
    const PROTECTION = [
        ['none', 'None (bare wall)', 'panel.thermal.protNone'],
        ['ablative_liner', 'Ablative liner sized by HRMA (Level-1 Q*)',
         'panel.thermal.protAblativeLiner'],
    ];

    // Motor yanıtındaki ilk sonlu sayı / ilk dolu metin ('a.b.c' yolları).
    function yolOku(o, yol) {
        let v = o;
        for (const p of String(yol).split('.')) {
            v = (v && typeof v === 'object') ? v[p] : undefined;
        }
        return v;
    }
    function ilkSayi(o, yollar) {
        for (const y of yollar) {
            const v = yolOku(o, y);
            if (typeof v === 'number' && Number.isFinite(v)) return v;
        }
        return undefined;
    }
    function ilkMetin(o, yollar) {
        for (const y of yollar) {
            const v = yolOku(o, y);
            if (typeof v === 'string' && v !== '') return v;
        }
        return undefined;
    }

    /* V301/ÖRNEK-PANEL (KABUL K2) — GAZ GİRDİLERİ MOTORUN KENDİSİNDEN.
       ÖLÇÜLDÜ (olcum/once_hybrid.json + betik/hibrit_girdi.py): panel
       c*, γ, M, boğaz çapı ve ışıyan tür kesirlerini GÖNDERMİYORDU; uç onları
       kendi varsayılanlarından türetiyordu: c* 1656,9 m/s (motor 1420,9,
       +%16,6), boğaz akısı 21,93 MW/m² (motorun aynı modülle çözdüğü 28,45,
       −%23), T_aw 3314,5 K (motor 3321,4). Aynı beş girdi gidince yanıt
       motorun heat_transfer_analysis bloğuyla aynı sayıyı veriyor
       (bit-aynı ham girdiyle; 6 anlamlı basamaklı öneriyle 0,003 K içinde).
       Hibrit yolları motorun ısı modülüne verdiği sözlüğün aynısıdır
       (hybrid_rocket_engine ``ht_input``); katıda Bartz gaz çifti motorun
       kendi Bartz zincirinin çiftidir (heat_transfer_analysis.
       bartz_gas_properties). Yol yoksa öneri yok, alan boş kalır ve uç
       kendi türetimini adıyla beyan eder. */
    const GAMMA_YOLLARI = ['heat_transfer_analysis.bartz_gas_properties.gamma', 'gamma'];
    const MW_YOLLARI = ['heat_transfer_analysis.bartz_gas_properties.molecular_weight',
                        'molecular_weight', 'thermochemistry.molecular_weight'];
    const SOGUTMA_YOLLARI = ['cooling_type',
                             'heat_transfer_analysis.design_parameters.cooling_type'];

    function riskKind(level) {
        const t = String(level || '').toUpperCase();
        if (t === 'LOW') return 'ok';
        if (t === 'MEDIUM') return 'warn';
        if (t === 'HIGH' || t === 'CRITICAL') return 'err';
        return 'info';
    }

    /* V3.0.5 SIVI-CIDAR (kalem 2): iki katmanlı rejeneratif sıvı cidarın
       sıcak gaz katmanı (astar) — motorun KENDİ kaydından; değilse null.
       Döner: { material: kanonik anahtar | undefined, thicknessM } */
    function sicakGazAstari(m, mt) {
        if (mt !== 'liquid') return null;
        const cs = yolOku(m, 'structural_analysis.chamber_structure') || {};
        const kat = Array.isArray(cs.wall_layers) ? cs.wall_layers : null;
        if (cs.wall_model !== 'two_layer_regenerative' || !kat || !kat.length) {
            return null;
        }
        const astar = kat.filter(function (k) {
            return k && k.role === 'liner';
        })[0] || {};
        const mk = (typeof astar.material_key === 'string' && astar.material_key)
            ? astar.material_key : undefined;
        const t = astar.thickness_mm;
        return {
            material: mk,
            thicknessM: (typeof t === 'number' && Number.isFinite(t) && t > 0)
                ? t / 1000 : undefined,
        };
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

    function temperaturePlot(root, ta, ps) {
        if (typeof Plotly === 'undefined') return;
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const matp = ta.material_properties || {};
        const kind = (ps && ps.kind) || 'bare';

        const cats = [];
        const vals = [];
        // V307/SEKME-GÜVERTE: ÖLÇÜLDÜ (tarayici/hibrit_L1_tr_1440.json, yazı
        // çakışması ölçümü): TR'de uzun kategori etiketleri ("Cidar iç
        // (çıplak, astarsız)" ⟷ "Cidar dış (çıplak, astarsız)") 1440 px'te
        // üst üste biniyordu. Parantezli niteleme ikinci satıra alınır
        // (metin aynı, yalnız satır kırılır).
        function push(label, v) {
            if (typeof v === 'number' && Number.isFinite(v)) {
                cats.push(String(label).replace(' (', '<br>('));
                vals.push(v);
            }
        }
        push(T('panel.thermal.combustionGas', 'Combustion gas'), gsa.gas_temperature);
        push(T('panel.thermal.adiabaticWall', 'Adiabatic wall'), gsa.adiabatic_wall_temperature);
        // V301/ÖRNEK-PANEL: hüküm verilen cidardaysa çubuklar O cidarı, çıplak
        // cidar dengesi ayrı ve adıyla; astar yolunda cidar çubukları çıplak
        // cidar olduğunu adıyla söyler (sınır çizgisinin üstünde etiketsiz
        // "Cidar" çubuğu korunan cidar hükmüyle çelişkili okunuyordu).
        if (kind === 'supplied') {
            push(T('panel.thermal.wallInnerSupplied', 'Wall inner (supplied)'),
                 ps.block.wall_temperature_hot_K);
            push(T('panel.thermal.wallOuterSupplied', 'Wall outer (supplied)'),
                 ps.block.wall_temperature_cold_K);
            push(T('panel.thermal.wallBareBound', 'Bare-wall bound'), wa.inner_temperature);
        } else if (kind === 'liner') {
            push(T('panel.thermal.wallInnerBare', 'Wall inner (bare, no liner)'), wa.inner_temperature);
            push(T('panel.thermal.wallOuterBare', 'Wall outer (bare, no liner)'), wa.outer_temperature);
        } else {
            push(T('panel.thermal.wallInner', 'Wall (inner)'), wa.inner_temperature);
            push(T('panel.thermal.wallOuter', 'Wall (outer)'), wa.outer_temperature);
        }
        if (!cats.length) return;

        const div = document.createElement('div');
        div.style.marginTop = '10px';
        root.appendChild(div);

        // Limitler ayrı seri DEĞİL: etiketli referans çizgileri (status rengi
        // asla "series" olarak kullanılmaz; kimlik yalnız renkle taşınmaz)
        const shapes = [];
        const annotations = [];
        // V301/ÖRNEK-PANEL: sınır etiketleri çizim alanının DIŞINDA, sağ
        // kenar boşluğunda (x = 1, xanchor left). Eskiden çizim alanının sağ
        // ucunda duruyor ve son çubuğun üstüne biniyordu (ölçüldü, 1280 px
        // ekran görüntüsü: "İzin verilen sınır — 811 K" son çubukta).
        // İzin etiketi çizginin altına, erime etiketi üstüne: iki etiket
        // (izin < erime) birbirinden ayrışır. Yazı 12 px (ORTAK grafik kuralı).
        function limitLine(v, label, color, yanchor) {
            if (typeof v !== 'number' || !Number.isFinite(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 1, xshift: 6, y: v, xanchor: 'left', yanchor: yanchor,
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 12, color: color },
            });
        }
        limitLine(canonicalAllowableK(ta), T('panel.thermal.allowableLimit', 'Allowable limit'), '#ff8c33', 'top');
        limitLine(matp.melting_point, T('panel.thermal.meltingPoint', 'Melting point'), '#ff5d73', 'bottom');

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
            // Sağ kenar boşluğu sınır etiketleri için (yukarıdaki not).
            margin: { r: annotations.length ? 200 : 40 },
            height: 360,
            showlegend: false,
        }, { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Eksenel profil (Dalga 2): q(x), T_wall(x), Mach(x)
    // ------------------------------------------------------------------
    const WALL_PROFILE_ENDPOINT = '/api/analysis/wall-profile';

    /* V306/TERMAL-KONTUR (KILAVUZ K-P4, S1) — MOTORUN NOZULU.
       ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/termal-kontur/olcum/once_ornek.json,
       taban 085d9adf7): üç örnekte de /analyze_thermal_safety gövdesinde
       hiçbir nozul geometrisi yoktu; ıslak alan integrali her koşuda
       örnekleyicinin JENERİK çıkış çapı ve lüle tipiyle alınıyordu (sıvı:
       sıcak gaz yüzeyi 0,153 m², ısı gücü 2042,6 kW). Motor sonucu konturu
       YAYIMLIYOR (ölçülen yollar olcum/motor_yollari.json: üç tipte üst
       düzey `nozzle_contour.points`, metre; `expansion_ratio`;
       `nozzle_angles.nozzle_type`). Bu alanlar formda kutu değildir; gövdeye
       güvertenin form dışı bağlam kanalıyla (`contextFromResults`) ve eksenel
       profil isteğine buradan girer.
       Kullanıcı hazne ya da boğaz çapını ELLE değiştirdiyse motorun konturu o
       hazneye/boğaza ait değildir (uç da çelişkiyi adıyla reddeder): kontur
       gönderilmez, konturu motorun genleşme oranı ve lüle tipi yeni boğazdan
       örnekler (künye bunu ayrıca söyler). Yol yoksa alan gönderilmez; uç
       bugünkü beyanlı jenerik yola düşer. */
    function kutuKirli(alan) {
        const el = document.getElementById('ad_f_thermal_' + alan);
        return !!(el && el.dataset && el.dataset.dirty === '1');
    }
    function nozulGeometrisi(r) {
        const m = U.motorDict(r);
        const out = {};
        const tip = ilkMetin(m, ['nozzle_angles.nozzle_type', 'nozzle_type',
                                 'nozzle_contour.divergent.type']);
        if (tip) out.nozzle_type = tip;
        const pts = yolOku(m, 'nozzle_contour.points');
        if (Array.isArray(pts) && pts.length >= 3
                && !kutuKirli('chamber_diameter') && !kutuKirli('throat_diameter')) {
            out.nozzle_contour = { points: pts };
            return out;
        }
        const eps = ilkSayi(m, ['expansion_ratio', 'motor_geometry.expansion_ratio']);
        if (eps !== undefined && eps > 1) out.expansion_ratio = eps;
        return out;
    }

    /* V307/GÜVERTE-ISIL (kalem 1) — ASTAR İSTASYONU BAĞLAMI. Motorun hazne
       astarı istasyonunun gaz tarafı girdileri (katsayı, sürücü sıcaklık,
       kenar gazı c_p'si) formda kutu değildir; gövdeye form dışı bağlam
       olarak girer. Yalnız (a) sıvı ablatif motorun astar bloğu bu çifti
       yayımladıysa, (b) formda astar yolu seçiliyse ve (c) istasyonu
       belirleyen kutular ELLE değiştirilmediyse: kullanıcı basıncı, sıcaklığı
       ya da geometriyi değiştirdiyse motorun istasyonu o motora ait değildir,
       gönderilmez ve uç istasyonu kendi zincirinden türetir (ekranda adıyla). */
    const ASTAR_ISTASYONU_KUTULARI = ['chamber_pressure', 'chamber_temperature',
        'chamber_diameter', 'throat_diameter', 'mdot_total', 'c_star', 'gamma',
        'molecular_weight'];
    // Formdaki seçicinin O ANKİ değeri; kutu çizilmediyse (form yok)
    // undefined — o zaman motorun tohumu geçerlidir.
    function kutuDegeri(alan) {
        const el = document.getElementById('ad_f_thermal_' + alan);
        return (el && el.tagName === 'SELECT' && typeof el.value === 'string')
            ? el.value : undefined;
    }
    function astarIstasyonu(r) {
        const mt = (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
            ? window.AnalysisDock.getMotorType() : null;
        if (mt !== 'liquid') return {};
        const m = U.motorDict(r);
        if (ilkMetin(m, SOGUTMA_YOLLARI) !== 'ablative') return {};
        const a = motorAstarOku(m, false);
        if (!a || a.hGaz === null || a.tSurucu === null) return {};
        const koruma = kutuDegeri('wall_protection');
        if (koruma !== undefined && koruma !== 'ablative_liner') return {};
        if (ASTAR_ISTASYONU_KUTULARI.some(kutuKirli)) return {};
        const out = { liner_h_gas_W_m2K: a.hGaz, liner_T_recovery_K: a.tSurucu };
        if (a.cpGaz !== null) out.liner_gas_cp_J_kgK = a.cpGaz;
        return out;
    }

    /* V307/GÜVERTE-ISIL (kalem 1) — ASTAR HÜKMÜNÜN DÖKÜMÜ. Toplam kalınlık =
       gerileme payı (Seviye-1 Q*) + iletim payı; istasyon girdilerinin
       kaynağı; motor sonucunun kendi astar sayısı yan yana. Boyutlanamadıysa
       neden sayılarıyla (gerileme hızı ⟷ model tavanı) ve motorun aynı
       istasyon için ne dediği. Ucun İngilizce cümlesi satır etiketinin
       ipucunda aynen durur. */
    function astarDokumu(ps, ma) {
        if (ps.kind !== 'liner' && ps.kind !== 'liner_not_sized') return '';
        const b = ps.block || {};
        const sz = b.sizing || {};
        const gi = b.inputs || {};
        const sonlu = function (v) { return typeof v === 'number' && Number.isFinite(v); };
        const kucuk = function (t) {
            return '<span style="font-size:0.72rem; white-space:normal;'
                + ' color:var(--hd-ink-dim, #7d97a5);"> · ' + U.esc(t) + '</span>';
        };
        const ayni = function (a, c) {
            return sonlu(a) && sonlu(c)
                && Math.abs(a - c) <= 1e-9 * Math.max(1, Math.abs(a));
        };
        const rows = [];
        if (ps.kind === 'liner') {
            rows.push([T('panel.thermal.liner.total', 'Liner thickness (total)'),
                '<span data-thermal-liner-total="1">'
                + numL(b.required_thickness_mm, 2) + ' mm</span>', '']);
            if (sonlu(sz.recession_allowance_mm)) {
                rows.push([T('panel.thermal.liner.recession',
                             'Recession allowance (Level-1 Q*)'),
                    '<span data-thermal-liner-recession="1">'
                    + numL(sz.recession_allowance_mm, 2) + ' mm</span>'
                    + (sonlu(sz.recession_rate_mm_s) && sonlu(sz.design_margin)
                        ? kucuk(U.tf('panel.thermal.liner.recessionHow',
                            { v: numL(sz.recession_rate_mm_s, 3),
                              t: numL(sz.burn_time_s, 2),
                              m: numL(sz.design_margin, 2) },
                            'recession rate {v} mm/s × burn time {t} s × design margin {m}'))
                        : ''), '']);
            }
            if (sonlu(sz.conduction_allowance_mm)) {
                rows.push([T('panel.thermal.liner.conduction', 'Conduction allowance'),
                    '<span data-thermal-liner-conduction="1">'
                    + numL(sz.conduction_allowance_mm, 2) + ' mm</span>'
                    + kucuk(T('panel.thermal.liner.conductionHow',
                        'insulation depth for the burn time')),
                    typeof sz.conduction_basis === 'string' ? U.esc(sz.conduction_basis) : '']);
            }
        } else {
            const hiz = b.recession_rate_mm_s;
            const tavan = b.recession_validity_max_mm_s;
            rows.push([T('panel.thermal.liner.notSized', 'Liner not sized'),
                '<span data-thermal-liner-not-sized="1" style="white-space:normal;">'
                + U.esc((sonlu(hiz) && sonlu(tavan) && hiz > tavan)
                    ? U.tf('panel.thermal.liner.rateAboveCeiling',
                        { v: numL(hiz, 3), max: numL(tavan, 2) },
                        'The recession rate {v} mm/s is above the {max} mm/s '
                        + 'validity ceiling of the Level-1 Q* model, so no '
                        + 'thickness is published.')
                    : T('panel.thermal.liner.notSizedOther',
                        'The Level-1 Q* model could not size this liner; no '
                        + 'thickness is published.'))
                + '</span>',
                typeof b.reason === 'string' ? U.esc(b.reason) : '']);
        }
        if (sonlu(gi.h_gas_W_m2K) && sonlu(gi.T_recovery_K)) {
            const verilmis = gi.liner_station_source === 'supplied';
            rows.push([T('panel.thermal.liner.station', 'Liner station inputs'),
                '<span data-thermal-liner-station="' + (verilmis ? 'supplied' : 'derived')
                + '" style="white-space:normal;">'
                + U.esc(U.tf(verilmis ? 'panel.thermal.liner.stationSupplied'
                                      : 'panel.thermal.liner.stationDerived',
                    { h: numL(gi.h_gas_W_m2K, 0), t: numL(gi.T_recovery_K, 0) },
                    verilmis
                        ? "motor result's chamber liner station: gas-side "
                          + 'coefficient {h} W/m²·K, driving temperature {t} K'
                        : "this tab's own heat chain (reference cooled wall): "
                          + 'gas-side coefficient {h} W/m²·K, driving temperature {t} K'))
                + '</span>',
                typeof gi.h_gas_source === 'string' ? U.esc(gi.h_gas_source) : '']);
        }
        if (ma) {
            let motorMetin;
            if (ma.kalinlikMm !== null && ma.iletimDahil) {
                motorMetin = U.tf('panel.thermal.liner.motorSizedTotal',
                    { mm: numL(ma.kalinlikMm, 2), v: numL(ma.gerilemeMmS, 3) },
                    '{mm} mm (recession allowance + conduction allowance, '
                    + 'recession rate {v} mm/s)');
                if (ps.kind === 'liner' && ayni(ma.kalinlikMm, b.required_thickness_mm)) {
                    motorMetin += ' · ' + T('panel.thermal.liner.sameTotal',
                        "equal to this tab's total");
                }
            } else if (ma.kalinlikMm !== null) {
                motorMetin = U.tf('panel.thermal.liner.motorSized',
                    { mm: numL(ma.kalinlikMm, 2), v: numL(ma.gerilemeMmS, 3) },
                    '{mm} mm (recession allowance only, recession rate {v} mm/s; '
                    + 'the motor result adds no conduction allowance)');
                if (ps.kind === 'liner' && ayni(ma.kalinlikMm, sz.recession_allowance_mm)) {
                    motorMetin += ' · ' + T('panel.thermal.liner.sameRecession',
                        "equal to this tab's recession allowance");
                }
            } else {
                motorMetin = U.tf('panel.thermal.liner.motorNotSized',
                    { v: numL(ma.gerilemeMmS, 3) },
                    'not sized (recession rate {v} mm/s)');
                if (ps.kind === 'liner_not_sized' && ayni(ma.gerilemeMmS, b.recession_rate_mm_s)) {
                    motorMetin += ' · ' + T('panel.thermal.liner.sameRefusal',
                        'the same station and the same reason as this tab');
                }
            }
            rows.push([T('panel.thermal.liner.motor', 'Chamber liner — motor result'),
                '<span data-thermal-liner-motor="1" style="white-space:normal;">'
                + U.esc(motorMetin) + '</span>', '']);
        }
        return U.sectionTitle(T('panel.thermal.liner.title', 'Ablative Liner Sizing'))
            + U.kvTable(rows);
    }

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
            // V306/TERMAL-KONTUR: ıslak alanla AYNI geometri (tek kaynak):
            // motorun konturu, yoksa genleşme oranı + lüle tipi.
            const geo = nozulGeometrisi(results);
            Object.keys(geo).forEach(function (k) {
                if (payload[k] == null) payload[k] = geo[k];
            });
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
    function mountAxialSection(root, superseded) {
        const sec = document.createElement('div');
        sec.innerHTML = U.sectionTitle(T('panel.thermal.secAxial',
                'Axial Profile — Chamber to Nozzle Exit'))
            + `<p style="font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5); margin:4px 0 8px;">${
               T('panel.thermal.axialIntro',
                 'Computes the axial distribution of heat flux, equilibrium wall '
                 + 'temperature and Mach number along the chamber-nozzle axis '
                 + '(Bartz correlation with local area ratio).')}</p>`
            // V301/ÖRNEK-PANEL: profil ucu (/api/analysis/wall-profile) çıplak
            // cidarın kararlı dengesini çözer (yanma süresi girmez, astar/
            // yalıtım yok — ucun kendi inputs_not_used beyanı). Hüküm korunan
            // cidardayken bu adıyla söylenir.
            + (superseded
                ? `<p data-thermal-axial-bare="1" style="font-size:0.78rem; color:var(--hd-orange, #ff8c33); margin:0 0 8px;">${
                   T('panel.thermal.axialBareNote',
                     'This profile is the steady equilibrium of the BARE wall (no liner or '
                     + 'insulation, no burn transient); the wall verdict is the protected-wall '
                     + 'block above.')}</p>`
                : '');
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
                    // V306/DİL-KATI 2. tur (TERMAL-KONTUR DEVİR): kullanıcı metninde HTTP
                    // kodu yok — ret gövdesi gerekçesizse ortak ret yedeği (HRMAReject).
                    throw new Error((data && data.error) || ((window.HRMAReject && window.HRMAReject.yedek) ? window.HRMAReject.yedek(resp.status) : ('HTTP ' + resp.status)));
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

    // V301/ÖRNEK-PANEL — korunan cidar hükmü (heat_transfer_analysis.
    // apply_wall_protection). Uç iki bloktan birini yayımlar; ikisi de yoksa
    // hüküm bugünkü çıplak cidar kontrolüdür ve panel eskisi gibi çizer.
    function protectionState(ta) {
        const sw = ta.supplied_wall_check;
        if (sw && sw.status === 'applied') return { kind: 'supplied', block: sw };
        const cl = ta.chamber_liner_check;
        if (cl && cl.status === 'applied') return { kind: 'liner', block: cl };
        if (cl && cl.verdict === 'NOT_SIZED') return { kind: 'liner_not_sized', block: cl };
        return { kind: 'bare', block: null };
    }

    function protectionBadges(ps) {
        if (ps.kind === 'supplied') {
            const b = ps.block;
            return U.badge(T('panel.thermal.badgeSuppliedWall', 'WALL VERDICT: SUPPLIED WALL')
                + ': ' + numL(b.wall_temperature_hot_K, 1) + ' / '
                + numL(b.wall_temperature_cold_K, 1) + ' K', 'info',
                T('panel.thermal.suppliedWallTip',
                  'The verdict below is evaluated at the supplied wall temperature '
                  + 'pair (here: the motor result\'s own solved wall). The bare-wall '
                  + 'equilibrium is kept as a bound only.'));
        }
        if (ps.kind === 'liner') {
            const b = ps.block;
            return U.badge(U.tf('panel.thermal.badgeLinerRequired',
                { mm: numL(b.required_thickness_mm, 2), material: String(b.material || '—') },
                'LINER REQUIRED: {mm} mm {material} (HRMA-sized)'), 'warn',
                T('panel.thermal.linerScopeTip',
                  'One ablative liner sized by HRMA (Level-1 Q*) for the whole chamber '
                  + 'wall at the chamber station. The wall temperature behind the liner '
                  + 'is not solved, so no margin is published for it.'));
        }
        if (ps.kind === 'liner_not_sized') {
            return U.badge(T('panel.thermal.badgeLinerNotSized',
                'LINER NOT SIZED — bare-wall verdict stands'), 'err',
                String(ps.block.reason || ''));
        }
        return '';
    }

    // V306/SIVI-SOĞUTMA (M-SIVI-30): güvertenin bağlı olduğu motorun soğutma
    // tipi (yalnız sıvı motor yanıtı; yoksa undefined).
    function motorCoolingType() {
        try {
            const mt = (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
                ? window.AnalysisDock.getMotorType() : null;
            if (mt !== 'liquid') return undefined;
            return ilkMetin(U.motorDict(window.currentResults), SOGUTMA_YOLLARI);
        } catch (e) {
            return undefined;
        }
    }
    function coolingTypeName(v) {
        const ad = {
            ablative: ['Ablative Liner', 'panel.thermal.motorCooling.ablative'],
            radiative: ['Radiation Cooling', 'panel.thermal.motorCooling.radiative'],
            film_cooling: ['Film Cooling', 'panel.thermal.motorCooling.film_cooling'],
            dump_cooling: ['Dump Cooling', 'panel.thermal.motorCooling.dump_cooling'],
        }[v];
        return ad ? T(ad[1], ad[0]) : String(v);
    }

    function render(data, root) {
        // V307/GÜVERTE-ISIL (kalem 2): modellenmeyen soğutma tipi — uca
        // gidilmedi; motor sonucunun soğutma bloğu basılır.
        if (data && data.cooling_not_modelled_here === true) {
            renderModelsizSogutma(data, root);
            return;
        }
        const ta = data.thermal_analysis || {};
        const htc = ta.heat_transfer_coefficients || {};
        const gsa = ta.gas_side_analysis || {};
        const wa = ta.wall_analysis || {};
        const cool = ta.cooling_analysis || {};
        const safe = ta.safety_analysis || {};
        const matp = ta.material_properties || {};
        const dpp = ta.design_parameters || {};
        const ps = protectionState(ta);
        const superseded = ps.kind === 'supplied' || ps.kind === 'liner';

        // ---- Rozetler ----
        let badges = protectionBadges(ps);
        if (safe.risk_level) {
            badges += U.badge(T('panel.thermal.badgeRisk', 'THERMAL RISK') + ': ' + safe.risk_level,
                              riskKind(safe.risk_level),
                              typeof safe.risk_level_basis === 'string' ? safe.risk_level_basis : '');
        }
        /* V306/SIVI-SOĞUTMA (M-SIVI-30): motorun soğutma tipi bu güvertenin
           seçeneklerinde (doğal / zorlanmış / rejeneratif) yoksa ve korunan
           cidar da uygulanmadıysa, hüküm motorun cidarına ait değildir —
           başlıkta adıyla söylenir (motorun tipi kendi sözlük adıyla). */
        const motorSog = motorCoolingType();
        if (motorSog && SOGUTMA_MODELSIZ.indexOf(motorSog) !== -1
                && !superseded) {
            badges += U.badge(U.tf('panel.thermal.badgeMotorCoolingNotModelled',
                { type: coolingTypeName(motorSog) },
                'MOTOR COOLING ({type}) NOT MODELLED HERE — verdict is for a bare wall'),
                'warn', T('panel.thermal.motorCoolingNotModelledTip',
                  'This deck models natural, forced and regenerative cooling only. '
                  + 'The verdict below is the bare-wall check and is not the '
                  + 'motor\'s own cooling result; the motor result page carries that.'));
        }
        // V307/SEKME-GÜVERTE (NK3-S-3): rozet soğutma sınıfının okunur adını
        // basar (ham değer büyük harfle basılmıyordu: "NATURAL"); bütçe geri
        // çekildiyse ipucu nedenini söyler.
        const butceGeri = SOGUTMA_BUTCESI_GERI[cool.required_cooling_area_withheld_code];
        badges += U.badge(T('panel.thermal.badgeCooling', 'COOLING') + ': '
            + (dpp.cooling_type ? sogutmaAdi(String(dpp.cooling_type)) : '—'), 'info',
            butceGeri ? T(butceGeri[0], butceGeri[1])
                : U.tf('panel.thermal.coolingEffTip', { value: numL(cool.cooling_efficiency, 2) },
                       'Cooling efficiency {value}'));
        if (htc.correlation) {
            badges += U.badge(T('panel.thermal.badgeModel', 'MODEL: BARTZ'), 'info', htc.correlation);
        }
        if (gsa.wall_temperature_unphysical && superseded) {
            // Çıplak cidar sınırı fiziksel değil, ama hüküm korunan cidarda:
            // kırmızı "soğutma yetersiz" rozeti hükmü çelişkili gösterirdi.
            badges += U.badge(T('panel.thermal.badgeBareBound',
                'BARE-WALL BOUND UNPHYSICAL — superseded by the protected-wall verdict'), 'info',
                T('panel.thermal.unphysicalTip',
                  'Predicted steady-state wall temperature exceeds physical limits; '
                  + 'the wall would fail before reaching it. Improve cooling.'));
        } else if (gsa.wall_temperature_unphysical) {
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
            + (ps.kind === 'supplied'
                // Hüküm verilen çifte kurulur: kartlar o çifti, çıplak cidar
                // sınırı ayrı ve renksiz (dim) kart olarak basılır.
                ? U.statCard(T('panel.thermal.cardTwallInSupplied', 'T_wall inner (supplied)'),
                    numL(ps.block.wall_temperature_hot_K, 0), 'K',
                    tempKind(ps.block.wall_temperature_hot_K))
                  + U.statCard(T('panel.thermal.cardTwallOutSupplied', 'T_wall outer (supplied)'),
                    numL(ps.block.wall_temperature_cold_K, 0), 'K',
                    tempKind(ps.block.wall_temperature_cold_K))
                  + U.statCard(T('panel.thermal.cardBareBound', 'Bare-wall bound (no protection)'),
                    numL(wa.inner_temperature, 0), 'K', 'dim', SRV(String(ps.block.bare_wall_basis || '')))
                : U.statCard(superseded
                    ? T('panel.thermal.cardTwallInBare', 'T_wall inner (bare wall, no liner)')
                    : T('panel.thermal.cardTwallIn', 'T_wall inner'),
                    numL(wa.inner_temperature, 0), 'K',
                    superseded ? 'dim' : tempKind(wa.inner_temperature))
                  + U.statCard(superseded
                    ? T('panel.thermal.cardTwallOutBare', 'T_wall outer (bare wall, no liner)')
                    : T('panel.thermal.cardTwallOut', 'T_wall outer'),
                    numL(wa.outer_temperature, 0), 'K',
                    superseded ? 'dim' : tempKind(wa.outer_temperature)))
            + U.statCard(T('panel.thermal.cardTaw', 'T_adiabatic wall'),
                numL(gsa.adiabatic_wall_temperature, 0), 'K')
            + '</div>';
        root.appendChild(head);

        // ---- Astar hükmünün dökümü (V307/GÜVERTE-ISIL kalem 1) ----
        const astarHtml = astarDokumu(ps, motorAstar);
        if (astarHtml) {
            const astarDiv = document.createElement('div');
            astarDiv.innerHTML = astarHtml;
            root.appendChild(astarDiv);
        }

        // ---- Plotly çubuk ----
        temperaturePlot(root, ta, ps);

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
        // V3.0.5 SIVI-CIDAR (KILAVUZ P4, DİL-2 deseni): TR ekranda ham makine
        // adları (heat_sink_mass, heat_sink_delta_T_K …) GÖRÜNÜR satırdan
        // kalktı: etiket ve ΔT/c_p/sınır özeti okunur metin (EN + TR);
        // makine alanları ve ucun İngilizce beyanı kapalı "Teknik ayrıntı"
        // kutusunda AYNEN durur (sayılar değişmedi).
        const hsOzet = [];
        if (typeof cool.heat_sink_delta_T_K === 'number') {
            hsOzet.push(U.tf('panel.thermal.heatSinkDeltaT',
                             { v: numL(cool.heat_sink_delta_T_K, 2) },
                             'ΔT {v} K'));
        }
        if (typeof cool.heat_sink_specific_heat_J_kgK === 'number') {
            hsOzet.push(U.tf('panel.thermal.heatSinkCp',
                             { v: numL(cool.heat_sink_specific_heat_J_kgK, 1) },
                             'specific heat {v} J/(kg·K)'));
        }
        if (typeof cool.heat_sink_temperature_limit_K === 'number') {
            hsOzet.push(U.tf('panel.thermal.heatSinkLimit',
                             { v: numL(cool.heat_sink_temperature_limit_K, 1) },
                             'temperature limit {v} K'));
        }
        const heatSinkRow = hsDeclared
            ? [T('panel.thermal.heatSinkMassDeclared',
                 'Heat-sink mass (selected material)'),
               numL(cool.heat_sink_mass, 1) + ' kg' + hsChip
               + (hsOzet.length
                  ? '<span style="font-size:0.72rem;'
                    + ' color:var(--hd-ink-dim, #7d97a5);"> · '
                    + hsOzet.join(' · ') + '</span>' : '')
               + '<details class="hd-teknik-ayrinti" style="margin-top:2px;">'
               + '<summary style="cursor:pointer; font-size:0.68rem;'
               + ' color:var(--hd-ink-dim, #7d97a5);">'
               + U.esc(T('common.techDetail', 'Technical detail (machine fields)'))
               + '</summary>'
               + '<span style="font-family:var(--hd-mono); font-size:0.68rem;'
               + ' color:var(--hd-ink-dim, #7d97a5);">heat_sink_mass · '
               + 'heat_sink_delta_T_K '
               + numL(cool.heat_sink_delta_T_K, 2)
               + ' · heat_sink_specific_heat_J_kgK '
               + numL(cool.heat_sink_specific_heat_J_kgK, 1)
               + (hsSource ? ' · heat_sink_specific_heat_source '
                  + U.esc(hsSource) : '')
               + (typeof cool.heat_sink_temperature_limit_K === 'number'
                  ? ' · heat_sink_temperature_limit_K '
                    + numL(cool.heat_sink_temperature_limit_K, 1) : '')
               + (hsBasis
                  ? '<br>heat_sink_delta_T_basis: ' + U.esc(hsBasis) : '')
               + '</span></details>',
               '']
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
        // V3.0.5 SIVI-CIDAR (KILAVUZ P4): görünür im OKUNUR metin (EN + TR);
        // makine alan adı kapalı "Teknik ayrıntı"da aynen durur.
        const genelAdlar = (generics || []).map(function (g) {
            return {
                exit_diameter: T('panel.thermal.genericField.exit_diameter',
                                 'exit diameter'),
                expansion_ratio: T('panel.thermal.genericField.expansion_ratio',
                                   'expansion ratio'),
                nozzle_type: T('panel.thermal.genericField.nozzle_type',
                               'nozzle type'),
            }[g] || g;
        }).join(', ');
        const genelOkunur = wibNote
            ? U.tf('panel.thermal.genericContourMark', { fields: genelAdlar },
                   'generic nozzle contour (not supplied: {fields})')
            : '';
        const derivedNote = genelOkunur;
        const teknikGenel = function () {
            return '<details class="hd-teknik-ayrinti" style="display:inline;">'
                + '<summary style="cursor:pointer; display:inline;'
                + ' font-size:0.64rem; color:var(--hd-ink-dim, #7d97a5);"> '
                + U.esc(T('common.techDetail', 'Technical detail (machine fields)'))
                + '</summary><span style="font-family:var(--hd-mono);'
                + ' font-size:0.64rem;"> wetted_integral_contour_basis.'
                + 'generic_defaults_used: ' + U.esc(generics.join(', '))
                + '</span></details>';
        };
        // GÖRÜNÜR im: üzerine gelinmeden okunmayan bir `title` metni
        // "ekranda" sayılmaz (a2 turunda ölçülen bekçi zaafı). Islak alandan
        // TÜREYEN her satır beyanı kendi metninde taşır.
        const derivedMark = wibNote
            ? ('<span data-thermal-derived-generic="1"'
               + ' style="font-size:0.66rem;'
               + ' color:var(--hd-orange, #ff8c33);"> · '
               + U.esc(genelOkunur) + ' ' + teknikGenel() + '</span>')
            : '';
        // V306/TERMAL-KONTUR (K-P4): jenerik değilse künye KAYNAĞI söyler.
        // Köken ucun makine alanından okunur (`wetted_integral_contour_basis
        // .origin`, cümle eşleştirmesi yok); alan yoksa hiçbir şey iddia
        // edilmez (fail-closed). Yayımlanmış kontur = motorun nozulu; canlı
        // örnekleme jenerik alan olmadan = gönderilen genleşme oranı / çıkış
        // çapı ve lüle tipiyle (ör. boğaz kutusu elle değiştirildiğinde).
        const konturKaynakOkunur = (wib && !wibNote)
            ? (wib.origin === 'motor_published_contour'
                ? U.tf('panel.thermal.contourFromMotor',
                       { n: Number.isFinite(wib.contour_points) ? wib.contour_points : '—' },
                       "motor's nozzle (published contour, {n} points)")
                : (wib.origin === 'sampled_from_geometry_fields'
                    && Array.isArray(generics) && !generics.length)
                    ? T('panel.thermal.contourSampledSupplied',
                        'nozzle contour drawn from the supplied nozzle size and type')
                    : '')
            : '';
        const konturKaynakMark = konturKaynakOkunur
            ? ('<span data-thermal-contour-origin="' + U.esc(String(wib.origin)) + '"'
               + ' style="font-size:0.68rem;'
               + ' color:var(--hd-ink-dim, #7d97a5);"> · '
               + U.esc(konturKaynakOkunur) + '</span>')
            : '';
        // V307/SEKME-GÜVERTE (NK3-S-9): motorun KENDİ ısı yükü yan yana,
        // tanım farkıyla. ÖLÇÜLDÜ (sıvı L1): motor 267,1 kW (oda 208,9 +
        // nozul 58,1) — 800 K sıcak cidarda (kullanıcının azami cidar
        // sıcaklığı), boğaz Bartz katsayısı odaya ölçeklenmiş, yalnız
        // taşınım; bu sekme 332,8 kW — 1073 K referans soğutulmuş cidarda
        // (malzemenin izin verilen sıcaklığı), yerel Bartz ıslak alan
        // integrali + Leckner gaz ışınımı. İki tanım aynı büyüklüğü farklı
        // tabanda anlatır; ikisi de adıyla ekranda.
        const mIsi = motorIsiYuku;
        const isiSatirlari = [];
        if (mIsi) {
            const parca = (Number.isFinite(mIsi.oda) && Number.isFinite(mIsi.nozul))
                ? ' ' + U.tf('panel.thermal.motorHeatLoadSplit',
                             { c: numL(mIsi.oda, 1), n: numL(mIsi.nozul, 1) },
                             '(chamber {c} + nozzle {n} kW)')
                : '';
            const motorCidar = /solved/i.test(mIsi.cidarKaynak)
                ? T('panel.thermal.motorWallSolved', 'the wall the motor solved')
                : (/max wall temperature/i.test(mIsi.cidarKaynak)
                   ? T('panel.thermal.motorWallUserMax', 'your maximum wall temperature')
                   : T('panel.thermal.motorWallAssumed', 'the motor\'s wall temperature assumption'));
            isiSatirlari.push([
                T('panel.thermal.motorHeatLoad', 'Heat load — motor result (engine subsystems)'),
                '<span data-thermal-motor-heat-load="1">'
                + numL(mIsi.toplam, 1) + ' kW' + U.esc(parca) + '</span>',
                '']);
            isiSatirlari.push([
                T('panel.thermal.heatLoadWhyDiffer', 'Why the two heat loads differ'),
                '<span data-thermal-heat-load-basis="1" style="font-size:0.74rem;'
                + ' white-space:normal;">'
                + U.esc(U.tf('panel.thermal.heatLoadBasis', {
                    tm: numL(mIsi.cidarK, 1), mk: motorCidar,
                    tr: numL(gsa.reference_wall_temperature, 1) },
                    'Wall temperature: the motor result takes the heat load at '
                    + '{tm} K ({mk}); this tab at the reference cooled wall '
                    + '{tr} K (the material\'s allowable temperature). Model: '
                    + 'the motor\'s bulk chain scales the throat Bartz '
                    + 'coefficient to the chamber and counts convection only; '
                    + 'this tab integrates the local Bartz coefficient along '
                    + 'the nozzle contour and adds gas radiation (Leckner).'))
                + '</span>', '']);
        }
        thtml += U.kvTable([
            [T('panel.thermal.totalHeatRate', 'Total heat rate'),
             numL(cool.peak_heat_rate, 1) + ' kW' + derivedMark, derivedNote],
        ].concat(isiSatirlari).concat([
            [T('panel.thermal.totalHeatEnergy', 'Total heat energy (burn)'),
             numL(cool.total_heat_energy, 1) + ' MJ' + derivedMark, derivedNote],
            // V307/SEKME-GÜVERTE (NK3-S-3): korunan cidarda (astar / verilmiş
            // cidar sıcaklığı) ya da ablatif sınıfta uç bütçeyi yayımlamaz;
            // satır sayı yerine nedenini basar.
            butceGeri
                ? [T('panel.thermal.coolingEfficiency', 'Cooling efficiency'), '—',
                   T(butceGeri[0], butceGeri[1])]
                : [T('panel.thermal.coolingEfficiency', 'Cooling efficiency'), numL(cool.cooling_efficiency, 2)
                    + ' (' + U.esc(dpp.cooling_type ? sogutmaAdi(String(dpp.cooling_type)) : '—') + ')'],
            butceGeri
                ? [T('panel.thermal.requiredArea', 'Required cooling area'),
                   '<span data-thermal-cooling-budget="'
                   + U.esc(String(cool.required_cooling_area_withheld_code)) + '"'
                   + ' style="font-size:0.74rem; white-space:normal;">'
                   + U.esc(T(butceGeri[0], butceGeri[1])) + '</span>', '']
                : [T('panel.thermal.requiredArea', 'Required cooling area'),
                   numL(cool.required_cooling_area, 2) + ' m²'],
            heatSinkRow,
            [T('panel.thermal.hotGasArea', 'Hot-gas surface area'),
             numL(gsa.surface_area, 3) + ' m²'
             + (wibNote
                ? '<span data-thermal-generic-contour="'
                  + String(generics.length) + '"'
                  + ' style="font-size:0.68rem;'
                  + ' color:var(--hd-orange, #ff8c33);"> · '
                  + U.esc(genelOkunur)
                  + '<details class="hd-teknik-ayrinti" style="display:inline;">'
                  + '<summary style="cursor:pointer; display:inline;'
                  + ' font-size:0.64rem; color:var(--hd-ink-dim, #7d97a5);"> '
                  + U.esc(T('common.techDetailSrv',
                            'Technical detail (solver statement, untranslated)'))
                  + '</summary><span style="font-family:var(--hd-mono);'
                  + ' font-size:0.64rem;"> '
                  + U.esc(SRV(String(wib.exit_diameter_source))) + '</span>'
                  + '</details></span>'
                : '')
             + konturKaynakMark,
             derivedNote || konturKaynakOkunur],
        ]));

        thtml += U.sectionTitle(T('panel.thermal.secSafety', 'Thermal Safety Factors')
            + (ps.kind === 'liner'
                ? ' — ' + T('panel.thermal.sfBareSuffix', 'bare wall (bound; the liner verdict governs)')
                : ps.kind === 'supplied'
                ? ' — ' + T('panel.thermal.sfSuppliedSuffix', 'at the supplied wall temperatures')
                : ''));
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
                + U.esc(String(matp.name || dpp.material || '—')) + ')'],
        ].filter(Boolean));

        // V301/ÖRNEK-PANEL: korunan cidar hükmünün aştığı çıplak cidar
        // kayıtları (superseded_by) ayrı, bilgi listesinde; aynı kayıt iki
        // listede (güvenlik + gaz tarafı) çift basılmaz.
        const tumu = [].concat(safe.warnings || [], gsa.warnings || []);
        const gorulen = {};
        const warns = [];
        const asilan = [];
        tumu.forEach(function (w) {
            const anahtar = (w && typeof w === 'object')
                ? JSON.stringify([w.code, w.params, w.severity]) : String(w);
            if (gorulen[anahtar]) return;
            gorulen[anahtar] = true;
            if (w && typeof w === 'object' && w.superseded_by) asilan.push(w);
            else warns.push(w);
        });
        thtml += U.listBlock(T('common.warnings', 'Warnings'), warns, 'warn');
        if (asilan.length) {
            thtml += U.listBlock(T('panel.thermal.supersededList',
                'Bare-wall check — superseded by the protected-wall verdict'), asilan, 'dim');
        }
        const recs = [].concat(safe.recommendations || [], cool.recommendations || []);
        // V301/ÖRNEK-PANEL: öneriler çıplak cidar dengesinin ısı yükünden
        // türer; hüküm korunan cidardayken başlık bunu adıyla söyler.
        thtml += U.listBlock(superseded
            ? T('panel.thermal.coolingRecsBare', 'Cooling recommendations — for the bare wall (bound)')
            : T('panel.thermal.coolingRecs', 'Cooling Recommendations'), recs, 'info');
        tail.innerHTML = thtml;
        root.appendChild(tail);

        // ---- Eksenel profil bölümü (ikinci buton + iki grafik) ----
        mountAxialSection(root, superseded);
    }

    window.AnalysisDock.register({
        id: 'thermal',
        title: 'Thermal Safety — Bartz Heat Transfer & Wall Temperatures',
        titleKey: 'panel.thermal.title',
        category: 'THERMAL',
        endpoint: '/analyze_thermal_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            // V307/SEKME-GÜVERTE (NK3-H-7 ailesi, M-HIBRIT-40): motordan
            // gelen büyüklüklerin tanım değeri BOŞ (eskiden 40 bar / 3000 K /
            // 0,1 m / 0,5 m / 1 kg/s / 5 mm — son hesap başarısızken sekme
            // o gizli motoru değerlendiriyordu). Boşsa istek gönderilmez,
            // alan adıyla söylenir (`required`).
            ['chamber_pressure', 'Chamber Pressure (bar)', '', 1, 'common.f.chamberPressureBar', 'panel.thermal.help.chamber_pressure'],
            ['chamber_temperature', 'Chamber Temperature (K)', '', 10, 'common.f.chamberTemperatureK', 'panel.thermal.help.chamber_temperature'],
            ['chamber_diameter', 'Chamber Diameter (m)', '', 0.005, 'common.f.chamberDiameterM', 'panel.thermal.help.chamber_diameter'],
            ['chamber_length', 'Chamber Length (m)', '', 0.01, 'common.f.chamberLengthM', 'panel.thermal.help.chamber_length'],
            ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS', 'panel.thermal.help.burn_time'], // OH-D37-S6: süre uydurulmaz — boşsa gövdeye girmez (safety_panel.js deseni)
            ['mdot_total', 'Total Mass Flow (kg/s)', '', 0.05, 'common.f.mdotTotal', 'panel.thermal.help.mdot_total'],
            ['wall_thickness', 'Wall Thickness (m)', '', 0.001, 'common.f.wallThicknessM', 'panel.thermal.help.hotWallThickness'],
            ['material', 'Wall Material', 'steel', MATERIALS, 'common.f.wallMaterial', 'panel.thermal.help.hotWallMaterial'],
            ['cooling_type', 'Cooling Type', 'natural', COOLING, 'common.f.coolingType', 'panel.thermal.help.cooling_type'],
            // V301/ÖRNEK-PANEL — motorun ısı zincirine verdiği gaz girdileri
            // (boşsa gönderilmez; uç kendi türetimini adıyla beyan eder).
            ['throat_diameter', 'Throat Diameter (m)', '', 0.001, 'common.f.throatDiameterM', 'panel.thermal.help.throat_diameter'],
            ['c_star', 'Characteristic velocity c* (m/s)', '', 10, 'panel.thermal.fCstar', 'panel.thermal.help.c_star'],
            ['gamma', 'Gas gamma (Bartz)', '', 0.01, 'panel.thermal.fGammaGas', 'panel.thermal.help.gamma'],
            ['molecular_weight', 'Molecular Weight (g/mol)', '', 0.5, 'common.f.molecularWeight', 'panel.thermal.help.molecular_weight'],
            ['x_H2O', 'H2O mole fraction (radiation)', '', 0.01, 'panel.thermal.fXH2O', 'panel.thermal.help.x_H2O'],
            ['x_CO2', 'CO2 mole fraction (radiation)', '', 0.01, 'panel.thermal.fXCO2', 'panel.thermal.help.x_CO2'],
            // V301/ÖRNEK-PANEL — KORUNAN CİDAR (heat_transfer_analysis.
            // apply_wall_protection). Boşsa / 'none' ise hüküm bugünkü
            // çıplak cidar kontrolüdür.
            ['wall_temperature_hot', 'Supplied hot-side wall temperature (K)', '', 5, 'panel.thermal.fWallHotSupplied', 'panel.thermal.help.wall_temperature_hot'],
            ['wall_temperature_cold', 'Supplied cold-side wall temperature (K)', '', 5, 'panel.thermal.fWallColdSupplied', 'panel.thermal.help.wall_temperature_cold'],
            ['wall_protection', 'Wall protection', 'none', PROTECTION, 'panel.thermal.fWallProtection', 'panel.thermal.help.wall_protection'],
        ],
        // V301/ÖRNEK-PANEL (kalem 5): yanma süresi boşsa istek GÖNDERİLMEZ ve
        // güverte alanı adıyla söyler (dock.missingFields); ipucu kullanıcıya
        // süreyi nereye gireceğini söyler. Eskiden boş alan gövdeye girmiyor,
        // uç 422 incomplete_thermal_input dönüyordu (ölçüldü: örnek sıvı,
        // olcum/once_liquid.json — motorda yanma süresi girdisi yok).
        required: ['burn_time', 'chamber_pressure', 'chamber_temperature',
                   'chamber_diameter', 'chamber_length', 'mdot_total',
                   'wall_thickness'],
        fromResults: function (r) {
            const m = U.motorDict(r);
            const mt = (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
                ? window.AnalysisDock.getMotorType() : null;
            /* V3.0.5 SIVI-CIDAR (kalem 2): iki katmanlı rejeneratif sıvı
               cidarda ısı akısını taşıyan SICAK GAZ cidarı ASTARDIR
               (structural_analysis.chamber_structure.wall_layers[0]).
               Eskiden malzeme `chamber_structure.material_key` (= DIŞ KABUK,
               Inconel 718) ve kalınlık YIĞIN (astar + kanal + kabuk, 5,5 mm)
               okunuyordu; panel CuCrZr 1 mm astarın marş çiftini Inconel 718
               sınırlarıyla (977 / 1533 K) değerlendiriyordu. ÖLÇÜLDÜ:
               docs/scofield/raw/OH/V301/sivi-cidar/olcum/k2_once.json.
               Astar kaydı eksikse kabuğa DÜŞÜLMEZ: alan önerilmez. */
            const astar = sicakGazAstari(m, mt);
            const sogutma = ilkMetin(m, SOGUTMA_YOLLARI);
            // V307/SEKME-GÜVERTE (NK3-S-9): yalnız sıvı motor bu bloğu
            // yayımlıyor (hibrit motorun ısı yükü bu sekmeyle aynı modülden
            // bit-aynı gelir; katı motor ısı yükü yayımlamaz — ölçüldü).
            motorIsiYuku = (mt === 'liquid') ? motorIsiYukuOku(m) : null;
            motorAstar = (mt === 'liquid' && sogutma === 'ablative')
                ? motorAstarOku(m, false)
                : (mt === 'hybrid' ? motorAstarOku(m, true) : null);
            const ek = {
                throat_diameter: U.readLengthM(r, 'throat_diameter'),
                c_star: ilkSayi(m, ['c_star']),
                gamma: ilkSayi(m, GAMMA_YOLLARI),
                molecular_weight: ilkSayi(m, MW_YOLLARI),
            };
            if (sogutma && COOLING.some(function (o) { return o[0] === sogutma; })) {
                ek.cooling_type = sogutma;
            }
            // Işıyan tür kesirleri YALNIZ motorun kendi denge çözümünden
            // geldiyse (künye 'caller supplied ...'); modül varsayılanı
            // tohumlanmaz — uç onu zaten kendisi beyan ediyor.
            const gsa = yolOku(m, 'heat_transfer_analysis.gas_side_analysis') || {};
            if (/^caller supplied/i.test(String(gsa.radiation_composition_source || ''))) {
                ek.x_H2O = ilkSayi(gsa, ['radiation_x_H2O']);
                ek.x_CO2 = ilkSayi(gsa, ['radiation_x_CO2']);
            }
            /* KORUNAN CİDAR — motorun KENDİ hükmünün girdisi:
               * katı: kasa yalıtım + astar arkasında; motor kasayı yanma
                 boyunca geçici (lumped) ÇÖZÜYOR (solid_rocket_engine.
                 _calculate_case_temperature; ölçüldü 313,55 K, sınır 811 K).
                 Bu ÇÖZÜLMÜŞ sıcaklık verilmiş cidar çifti olarak gider
                 (yığın kasa: iç = dış). Yanma süresi pozitif değilse
                 sıcaklık çözülmemiştir, gönderilmez.
               * sıvı: rejeneratif istasyon marşının ÇÖZDÜĞÜ cidar çifti —
                 güvertenin ortak okuyucusu (readWallTemperaturesK) yalnız
                 'solved' künyeli çifti döner (güvenlik paneliyle aynı sayı).
               * hibrit: kasa sıcaklığı bölge modelinde BEYANLIDIR, çözülmüş
                 değildir (V301/H-PANEL kararı: tohumlanmaz). Bölge modeli
                 bütün bölgeleri koruyorsa astar burada YENİDEN
                 boyutlandırılır (wall_protection = 'ablative_liner'). */
            if (mt === 'solid') {
                const ht = yolOku(m, 'thermal_analysis.heat_transfer') || {};
                const tKasa = ht.case_temperature_k;
                const tb = U.readBurnTime(r);
                if (typeof tKasa === 'number' && Number.isFinite(tKasa) && tKasa > 0
                        && typeof tb === 'number' && tb > 0) {
                    ek.wall_temperature_hot = tKasa;
                    ek.wall_temperature_cold = tKasa;
                }
            } else if (mt === 'liquid') {
                const cift = U.readWallTemperaturesK(r) || {};
                if (Number.isFinite(cift.hot) && Number.isFinite(cift.cold)) {
                    ek.wall_temperature_hot = cift.hot;
                    ek.wall_temperature_cold = cift.cold;
                }
                /* V306/SIVI-SOĞUTMA (M-SIVI-30) — GÜVENLİK NR-3 (a) ilkesi:
                   güverte motorun KENDİ ısıl koruma kararını okur. Ablatif
                   astarlı sıvı motorun pasif koruması motorda Level-1 Q*
                   ile boyutlanmıştır (thermal_protection.
                   passive_thermal_protection, status 'modelled'); güverte
                   aynı modelle astarı boyutlandırır (hibritle aynı yol).
                   ÖLÇÜLDÜ (L1, olcum/m30_termal_guverte.json): ön dolum
                   'doğal, çıplak cidar' iken TERMAL RİSK HIGH; korunan
                   cidarla MEDIUM (astar gerekli), çıplak cidar sınırı
                   bare_wall_risk_level'de kalır. */
                const pasif = yolOku(m, 'thermal_protection.passive_thermal_protection') || {};
                if (sogutma === 'ablative' && pasif.status === 'modelled') {
                    ek.wall_protection = 'ablative_liner';
                }
            } else if (mt === 'hybrid') {
                const zones = yolOku(m, 'chamber_wall_zones') || {};
                if (zones.status === 'modelled' && zones.all_zones_protected === true) {
                    ek.wall_protection = 'ablative_liner';
                }
            }
            return Object.assign(ek, {
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
                material: (astar ? astar.material : U.readChamberMaterial(r)),
                wall_thickness: (astar ? astar.thicknessM
                                 : U.readWallThicknessM(r)),
            });
        },
        // V306/TERMAL-KONTUR (K-P4): `fromResults` yalnız form kutularını
        // doldurur (güverte kutusu olmayan anahtarı yutar); motorun nozul
        // geometrisi form dışı bağlamdır. Gerekçe ve yollar: nozulGeometrisi.
        // V307/GÜVERTE-ISIL (kalem 2): modellenmeyen soğutma tipinde uca
        // gidilmez (güvertenin `localResult` kancası).
        localResult: modelsizSogutmaSonucu,
        // V307/GÜVERTE-ISIL (kalem 1): + motorun astar istasyonu girdileri.
        contextFromResults: function (r) {
            return Object.assign(nozulGeometrisi(r), astarIstasyonu(r));
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
        // Bekçi yüzeyi (V307/GÜVERTE-ISIL kalem 2).
        _unmodelledCooling: SOGUTMA_MODELSIZ.slice(),
        _localResult: modelsizSogutmaSonucu,
    };
})();
