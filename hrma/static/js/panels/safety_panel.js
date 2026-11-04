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
    // ÖH D37 A1b panel-js 5. tur (14 Eki) — İTİCİ SINIFI MOTORUN KENDİ
    // İTİCİSİNDEN. ÖLÇÜLDÜ (KAB 14 Eki dock.json; a1/t5/once.json): panel
    // katı VE hibrit motoru 'composite' (APCP/HTPB) diye gönderiyordu.
    // Örnek N2O/HTPB hibritte uç sınıf composite, TNT 5,435 kg, ölümcül
    // parça menzili ve patlama tahliyesi 1600 m basıyordu; örnek KNDX
    // katıda (şeker itici) yine composite, TNT 1,011 kg, tahliye 1600 m.
    // Yayımlanan sayılar katı kompozit iticinindi, motorun değil.
    // 'not_modelled' bir itici SINIFI değildir (TNT çarpanı ve toksik kuralı
    // yok); uçtaki tek tanımı safety_analysis.PROPELLANT_CLASS_NOT_MODELLED.
    // Bu yüzden PROPELLANTS (sunucunun KNOWN_PROPELLANT_CLASSES ikizi)
    // listesine GİRMEZ, seçiciye ayrı bir seçenek olarak eklenir.
    const PROPELLANT_NOT_MODELLED = 'not_modelled';
    // Isı modülünün kendi "denge cidarı fiziksel değil" bayrağı (motor
    // sözlüğünde; heat_transfer_analysis.py 'wall_temperature_unphysical').
    const WALL_UNPHYSICAL_PATH = ['heat_transfer_analysis',
        'gas_side_analysis', 'wall_temperature_unphysical'];
    // V3 KK 3. tur (§28-50 (c)) — cidar çifti NEDEN gönderilmedi.
    // ÖLÇÜLDÜ (örnek hibrit; KLV 14 Eki): panel bayrak yüzünden çifti
    // göndermeyince uç termal ekseni geri çekiyor ve ekranda yalnız
    // 'girdi verilmedi' gerekçesi okunuyordu; kullanıcı eksik bir alan
    // doldurması gerektiğini sanıyor. Neden ısı modülünün KENDİ uyarısıdır.
    // Bu kodlar heat_transfer_analysis.py'de bayrağı TRUE yapan iki daldır
    // (erime noktası / servis sınırı aşımı).
    const WALL_UNPHYSICAL_CODES = ['warn.thermal.wall_exceeds_melting',
        'warn.thermal.wall_exceeds_service'];
    // Son öneride çiftin bayrak yüzünden GÖNDERİLMEDİĞİ bilgisi (yalnız
    // ekran künyesi; uca giden gövdeye GİRMEZ). null = geri tutma yok.
    let wallPairWithheld = null;
    // V301/PANEL (NK-18) — YAPISAL HÜKÜM MOTORUN ZİNCİRİNDEN.
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/panel/guvenlik_once.json): örnek
    // hibritte Performans Özeti NOT_EVALUATED (HRMA'nın boyutlandırdığı
    // cidar hüküm kazanmaz) derken bu sekme UNSAFE 5/5, PDF SAFE basıyordu;
    // katı ve sıvı örnekte de sekme UNSAFE (çıplak cidar Bartz tahmini).
    // Hüküm artık motorun KENDİ yapısal zincirinden gelir: panel motor
    // sonucunun hüküm bloğunu bağlam olarak gönderir, uç onu TEK işlevden
    // okur (safety_analysis.motor_structural_verdict). Yol tablosu
    // sunucudaki MOTOR_STRUCTURAL_VERDICT_BLOCKS ile AYNI (bekçi eşler).
    // Yollar parça dizisidir (noktalı dizge i18n anahtarıyla karışmasın).
    const MOTOR_VERDICT_BLOCKS = {
        hybrid: [['motor', 'structural_analysis', 'safety_analysis'],
                 ['structural_analysis', 'safety_analysis']],
        solid: [['safety_analysis', 'pressure_safety']],
        liquid: [['structural_analysis', 'chamber_structure']],
    };
    // ÖRNEK-PANEL DEVİR 1: hibritte cidarın ısıl hükmü motorun bölge
    // modelidir (yakıt bloğu altı korunur, açık bölgelere astar). Kasa
    // sıcaklığı BEYANLIDIR (tohumlanmaz); hükmün gerekçesi bu blokla taşınır.
    // Sunucudaki MOTOR_WALL_ZONE_BLOCKS ile AYNI (bekçi eşler).
    const MOTOR_ZONE_BLOCKS = {
        hybrid: [['motor', 'chamber_wall_zones'], ['chamber_wall_zones']],
    };

    function ilkBlok(r, yollar) {
        for (const parcalar of (yollar || [])) {
            let o = r;
            for (const p of parcalar) {
                o = (o && typeof o === 'object') ? o[p] : undefined;
            }
            if (o && typeof o === 'object' && !Array.isArray(o)
                && Object.keys(o).length) {
                return { parcalar: parcalar, blok: o };
            }
        }
        return null;
    }

    function yolaKoy(kopya, parcalar, blok) {
        let hedef = kopya;
        parcalar.forEach(function (p, i) {
            if (i === parcalar.length - 1) { hedef[p] = blok; return; }
            if (!hedef[p] || typeof hedef[p] !== 'object') hedef[p] = {};
            hedef = hedef[p];
        });
    }

    // Motor sonucundan YALNIZ hüküm bloğunu (ve hibritte bölge bloğunu),
    // sonucun kendi yol biçimiyle taşır (sunucu aynı yolu okur). Hüküm
    // bloğu yoksa null: bağlam gönderilmez.
    function motorVerdictResult(r, motorType) {
        if (!r || typeof r !== 'object') return null;
        const hukum = ilkBlok(r, MOTOR_VERDICT_BLOCKS[motorType]);
        if (!hukum) return null;
        const kopya = {};
        yolaKoy(kopya, hukum.parcalar, hukum.blok);
        const bolge = ilkBlok(r, MOTOR_ZONE_BLOCKS[motorType]);
        if (bolge) yolaKoy(kopya, bolge.parcalar, bolge.blok);
        return kopya;
    }

    // İtki tohumu — fromResults ile impuls bağlamının TEK okuyucusu.
    // V301/PANEL: katıda modülün 'thrust' tanımı TEPE itkidir (bağlama
    // kuvveti = itki × SF bir YÜK; K-C1 karar 4, PDF de max_thrust
    // gönderiyor). ÖLÇÜLDÜ (guvenlik_once.json, örnek KNDX): sekme ortalama
    // 1298,54 N, PDF tepe 1498,19 N basıyordu — aynı motor için iki bağlama
    // kuvveti. Tepe itki yoksa güvertenin ortak okuyucusu (ortalama) kalır.
    function seededThrust(r, motorType) {
        const m = U.motorDict(r) || {};
        if (motorType === 'solid' && Number.isFinite(m.max_thrust)) {
            return m.max_thrust;
        }
        return U.readThrust(r);
    }

    // Hüküm bloğunun ait olduğu yapısal girdiler — fromResults ile AYNI
    // okuyucular (tek yer). Uç, istekteki değerler bunlardan ayrışırsa
    // (kullanıcı güvertede cidar/basınç/çap değiştirdi) motorun hükmünü
    // benimsemez ve nedenini yazar.
    function structuralSeeds(r) {
        const m = U.motorDict(r);
        return {
            chamber_pressure: m.chamber_pressure,
            chamber_diameter: U.readLengthM(r, 'chamber_diameter'),
            wall_thickness: U.readWallThicknessM(r),
        };
    }
    const PROPELLANT_OPTIONS = PROPELLANTS.concat([[PROPELLANT_NOT_MODELLED,
        'Not modelled (no sourced TNT equivalent)', 'prop.notModelled']]);
    // Uç geri çekme kodu -> panelin kendi gerekçe metni (EN = TR sözlükte).
    const NOT_MODELLED_TEXT = {
        hybrid_oxidiser_tank: ['panel.safety.notModelledHybrid',
            'Hybrid motor: the fuel grain is an inert polymer and is not an explosive on its own; the explosive hazard is the decomposition of the oxidiser (N2O) held in the oxidiser tank, a separate vessel that this release does not model. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published.'],
        solid_no_sourced_tnt: ['panel.safety.notModelledSolid',
            'This solid propellant (potassium nitrate/sugar family such as KNDX, KNSB, KNSU, KNER, or black powder) has no primary-sourced TNT equivalent in HRMA, so the explosive verdict was not evaluated. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published.'],
        no_sourced_tnt: ['panel.safety.notModelledGeneric',
            'HRMA has no primary-sourced TNT equivalent for this propellant, so the explosive verdict was not evaluated. No TNT equivalent, blast distance, fragment throw range or evacuation distance is published.'],
    };

    // Motorun KENDİ iticisinden patlayıcı sınıfı (öneri; kullanıcının elle
    // yaptığı seçim güvertede 'dirty' olarak AYNEN korunur).
    //  * sıvı   -> 'liquid_biprop' (mevcut davranış, bit-aynı)
    //  * hibrit -> 'not_modelled' (tane atıl; tehlike ayrı oksitleyici
    //              tankında, bu sürümde modellenmedi)
    //  * katı   -> merkezi katalogdaki AİLE (propellants_db 'family',
    //              /api/propellants -> HRMAPropellants). Aile PROPELLANTS
    //              içinde bir sınıfsa (composite, double_base) o; değilse
    //              (sugar, other) ya da katalog/anahtar çözülemezse
    //              'not_modelled' (FAIL-CLOSED: bilinmeyen kimlik ürün
    //              varsayılanına ÇEVRİLMEZ). Eşleme tablosu YAZILMAZ: aile
    //              adı ile sınıf anahtarı aynı kelimedir, üyelik sınanır.
    function propellantClassFromMotor(r, motorType) {
        if (motorType === 'liquid') return 'liquid_biprop';
        if (motorType === 'hybrid') return PROPELLANT_NOT_MODELLED;
        if (motorType !== 'solid') return undefined;
        const m = U.motorDict(r);
        const key = (m && typeof m.propellant_type === 'string')
            ? m.propellant_type : null;
        const cat = window.HRMAPropellants;
        const rec = (key && cat && typeof cat.get === 'function')
            ? cat.get(key) : null;
        const family = (rec && typeof rec.family === 'string')
            ? rec.family : null;
        const isClass = !!family && PROPELLANTS.some(function (p) {
            return p[0] === family;
        });
        return isClass ? family : PROPELLANT_NOT_MODELLED;
    }
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
    // ÖH D37 A1c panel-dil · dil-sozluk Devir 2 — seçenekler sözlük
    // anahtarlı (mat.*; A1a dil-sozluk deseni: termal/koruma listeleri).
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/A1c/panel-dil/a1/once/tarayici.json,
    // hibrit TR): bu seçicide 16 seçeneğin 13'ü İngilizce, 3'ü 177 px'e
    // sığmıyordu ('Stainless 17-4PH (H900)', 'Beryllium copper C17200',
    // 'Carbon steel (A36-class)'). DEĞERLER aynen (uca giden anahtar); dile
    // bağlı olmayan alaşım kodları anahtarsız (EN = TR).
    const MATERIALS = [
        ['steel_4130', 'Steel AISI 4130', 'mat.steelAisi4130'],
        ['steel_4340', 'Steel AISI 4340', 'mat.steelAisi4340'],
        ['steel', 'Carbon steel (A36)', 'mat.carbonSteelA36'],
        ['ss_304', 'Stainless 304', 'mat.stainless304'],
        ['ss_316', 'Stainless 316', 'mat.stainless316'],
        ['ss_17_4ph', '17-4PH (H900)'],
        ['aluminum_6061', 'Aluminum 6061-T6', 'mat.aluminum6061'],
        ['al_7075_t6', 'Aluminum 7075-T6', 'mat.aluminum7075'],
        ['al_2024_t3', 'Aluminum 2024-T3', 'mat.aluminum2024'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V', 'mat.titanium6al4v'],
        ['ti_grade2_cp', 'Titanium CP Grade 2', 'mat.titaniumGrade2'],
        ['inconel_718', 'Inconel 718'],
        ['inconel_625', 'Inconel 625'],
        ['cucrzr', 'CuCrZr (C18150)'],
        ['beryllium_copper_c17200', 'BeCu C17200'],
        ['magnesium_az31b', 'Magnesium AZ31B', 'mat.magnesiumAz31b'],
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
    // V301/NK-19: ucun yayımladığı İngilizce eksen adı → sözlük anahtarı
    // (safety_analysis._generate_risk_matrix 'axes').
    const RISK_EKSEN_ANAHTARI = {
        Rare: 'risk.rare', Unlikely: 'risk.unlikely', Possible: 'risk.possible',
        Likely: 'risk.likely', Frequent: 'risk.frequent',
        Negligible: 'risk.negligible', Minor: 'risk.minor', Major: 'risk.major',
        Critical: 'risk.critical', Catastrophic: 'risk.catastrophic',
    };

    // Koşum kartının alanları — TEK kaynak. register() bu diziyi verir,
    // varsayılan künyesi (defaultsBlock) etiketleri buradan okur; ikinci
    // bir etiket listesi tutmak iki listenin ayrışmasını davet ederdi.
    const FIELDS = [
        ['motor_type', 'Motor Type', 'hybrid', MOTOR_TYPES, 'common.f.motorType', 'panel.safety.help.motor_type'],
        ['chamber_pressure', 'Chamber Pressure (bar)', 40, 1, 'common.f.chamberPressureBar', 'panel.safety.help.chamber_pressure'],
        ['chamber_temperature', 'Chamber Temperature (K)', 3000, 10, 'common.f.chamberTemperatureK', 'panel.safety.help.chamber_temperature'],
        ['thrust', 'Thrust (N)', 1000, 50, 'common.f.thrustN', 'panel.safety.help.thrust'],
        // ÖH D36 / onemli2-sivi a2 — SÜRE VE KÜTLE UYDURULMAZ.
        // ÖLÇÜLDÜ (docs/scofield/raw/OH/D36/onemli2-sivi/a2/once.json K2):
        // süre verilmeyen sıvı motorda çözücü `burn_time` ve itici kütlesi
        // YAYIMLAMIYOR (LU-1, Berke onaylı); `readBurnTime` /
        // `readPropellantMass` undefined döndüğü için (applySuggestions
        // yalnız sonlu sayı yazar) kutuda panelin nöbetçi değerleri 10 s ve
        // 5 kg KALIYOR ve gövdeye kullanıcının girdisi gibi gidiyordu:
        // /analyze_safety `inputs_used.burn_time_s = 10`, termal maruziyet
        // 10 s, TNT eşdeğeri 5 kg itici kütlesinden. Varsayılan artık BOŞ
        // DİZE (ısı zinciri çiftiyle aynı sözleşme: sonlu sayı olmayan
        // varsayılan = alan boşsa gövdeye HİÇ konmaz). Süre yoksa uç süreye
        // bağlı kolları ADIYLA geri çeker (`burn_time_dependent_not_evaluated`;
        // aşağıdaki bloklar '—' + gerekçe basar); kütle yoksa uç 422 +
        // `missing_fields: ['propellant_mass']` döner ve güverte alanın
        // ADINI basar (hüküm, verisi olmayan motor için üretilmez). Süre ve
        // kütle çözücüde varsa (hibrit, katı, süreli sıvı) öneri alanı
        // doldurur: gönderilen gövde bit-aynıdır (a2/sonra.json K2).
        ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS', 'panel.safety.help.burn_time'],
        ['propellant_mass', 'Propellant Mass (kg)', '', 0.5, 'common.f.propellantMassKg', 'panel.safety.help.propellant_mass'],
        ['propellant_type', 'Propellant Type', 'composite', PROPELLANT_OPTIONS, 'common.f.propellantType', 'panel.safety.help.propellant_type'],
        ['facility_type', 'Facility Type', 'test_stand', FACILITIES, 'common.f.facilityType', 'panel.safety.help.facility_type'],
        ['chamber_diameter', 'Chamber Diameter (m)', 0.1, 0.005, 'common.f.chamberDiameterM', 'panel.safety.help.chamber_diameter'],
        ['wall_thickness', 'Wall Thickness (m)', 0.005, 0.001, 'common.f.wallThicknessM', 'panel.safety.help.wall_thickness'],
        ['material', 'Material', 'steel_4130', MATERIALS, 'common.f.material', 'panel.safety.help.material'],
        // ISI ZİNCİRİ ÇİFTİ (OH-Z3-01). Varsayılanı BOŞ DİZE: güvertenin
        // zorunlu-alan sözleşmesinde (analysis_dock::requiredFieldInfo)
        // sonlu sayı olmayan varsayılan = isteğe bağlı alan. Boş kalırsa
        // gövdeye HİÇ konmaz; uç termal hükmü geri çeker ve panel bunun
        // beyanını basar (thermalBasisBlock). Doluysa uç ısı zincirini
        // GERÇEKTEN koşar. Alan etiketleri sözlükte ZATEN vardı
        // (common.f.wallTemperature*K — yapısal/termal panellerin ikizi);
        // bu tur yeni çeviri anahtarı AÇILMADI.
        // ISI ZİNCİRİ GEOMETRİSİ (ÖH D27 · P5B2-12, panel yarısı).
        // ÖLÇÜLDÜ (a2/once.json `safety_fields_isi_zinciri`): panelin
        // gönderdiği 13 alanın içinde `chamber_length` ve
        // `throat_diameter` YOKTU. Uç (`_SAFETY_THERMAL_CHAIN_FIELDS`,
        // app.py) ikisini de kabul ediyor ve onlarsız termal hükmü
        // FAIL-CLOSED geri çekiyor — kardeş bekçi
        // test_thermal_axis_ladder_reaches_the_ceiling ısı zinciri TAM
        // yükle 2,0 -> 4,0 -> 5,0 merdivenini CANLI uçta ölçüyor, yani
        // motor tarafı çalışıyordu; eksik olan PANELİN GÖNDERDİĞİ
        // ALANLARDI. Kullanıcı bu iki alanı gönderemediği için termal
        // eksen ekranda hiç hüküm üretemiyordu.
        // Varsayılan BOŞ DİZE: yukarıdaki cidar sıcaklığı çiftiyle aynı
        // sözleşme — sonlu sayı olmayan varsayılan = isteğe bağlı alan,
        // boş kalırsa gövdeye HİÇ konmaz ve uç eskisi gibi hükmü geri
        // çeker (sayı UYDURULMAZ, ne panelde ne uçta).
        ['chamber_length',
         'Chamber Length (m, blank = thermal verdict is withheld)',
         '', 0.01, 'common.f.chamberLengthM', 'panel.safety.help.chamber_length'],
        ['throat_diameter',
         'Throat Diameter (m, blank = thermal verdict is withheld)',
         '', 0.001, 'common.f.throatDiameterM', 'panel.safety.help.throat_diameter'],
        ['wall_temperature_hot',
         'Hot-side Wall Temperature (K, blank = let HRMA estimate from gas temperature)',
         '', 5, 'common.f.wallTemperatureHotK', 'panel.safety.help.wall_temperature_hot'],
        ['wall_temperature_cold',
         'Cold-side Wall Temperature (K, blank = let HRMA estimate from gas temperature)',
         '', 5, 'common.f.wallTemperatureColdK', 'panel.safety.help.wall_temperature_cold'],
    ];

    /* V301/CI-ÜRÜN (28 Eki) — tesis/yerleşim tehlikesi dayanağı.
       Sunucu cümlesi (safety_analysis.py ``facility_hazard.basis``) sabit
       bir İngilizce beyandır. EN: aynen basılır. TR: sözlükteki Türkçe özet
       + kapalı teknik ayrıntıda aynı cümle aynen (kullanıcı neyin
       çevrildiğini görebilir). Dayanak yoksa satır hiç basılmaz. */
    function facilityHazardBasisHtml(fh) {
        const ham = String((fh && fh.basis) || '');
        if (!ham) return '';
        const tr = !!(window.I18N && window.I18N.lang === 'tr');
        const govde = tr
            ? esc(T('panel.safety.facilityHazardBasis', ham))
              + '<details style="margin-top:2px; font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">'
              + '<summary style="cursor:pointer;">'
              + esc(T('common.techDetailSrv', 'Technical detail (solver statement, untranslated)'))
              + '</summary>' + esc(ham) + '</details>'
            : esc(ham);
        return '<div data-safety-field="risk_assessment.facility_hazard.basis"'
            + ' style="margin:0 0 8px; font-size:0.8rem; line-height:1.45;'
            + ' color:var(--hd-ink-dim, #7d97a5);">' + govde + '</div>';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Alan adının ekran etiketi (koşum kartındaki etiketin AYNISI). Uç,
    // panelde karşılığı olmayan bir alanı beyan ederse adı HAM basılır —
    // uydurma etiket yazmak beyanı çarpıtırdı.
    function fieldLabel(id) {
        for (let i = 0; i < FIELDS.length; i++) {
            if (FIELDS[i][0] === id) return T(FIELDS[i][4], FIELDS[i][1]);
        }
        return String(id);
    }

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

    // ÖH D20 / P12aB5-10: bant rengi TABLOSU buradan KALDIRILDI. Ölçüldü
    // (once.json): bu satır içi tablo `results_hud.css`'in dört basamaklı
    // merdivenini eziyordu (kehribar basamağı kayıp, iki kırmızı) ve satır
    // içi stil sayfa stilini geçtiği için tasarım katmanı ölüydü. Renk artık
    // YALNIZ `results_hud.css` `.hd-rm-cell[data-band=...]` kuralından gelir;
    // burada üretilen tek şey `data-band` sözcüğüdür.

    function riskLevelKind(level) {
        const t = String(level || '').toUpperCase();
        if (t === 'LOW') return 'ok';
        if (t === 'MEDIUM') return 'warn';
        return 'err';
    }

    // Ucun kayıt ağırlığı (`severity`) → güvertenin rozet sınıfı. Ağırlık
    // UYDURULMAZ: tanınmayan bir değer 'info' rozetiyle OLDUĞU GİBİ basılır,
    // sessizce düşürülmez (ÖH D15 / P11B4-11 kalıntısı).
    function severityKind(sev) {
        const t = String(sev || '').toLowerCase();
        if (t === 'error' || t === 'critical' || t === 'danger') return 'err';
        if (t === 'warning' || t === 'warn') return 'warn';
        return 'info';
    }

    function scoreCell(score) {
        const c = U.kindColor(bandKind(scoreBand(score)));
        // V306/GÜVENLİK (NR-4): skor da kullanıcı ondalığıyla (TR virgül).
        return `<span style="color:${c}; font-family:var(--hd-mono);">${U.num(score, 1)} / 5</span>`;
    }

    // ------------------------------------------------------------------
    // 5x5 risk matrisi — data-attribute'lu grid. Tek skorlu (1-5)
    // değerlendirme köşegen hücreye yerleştirilir (olabilirlik ve şiddet
    // ayrı raporlanmadığı için skor her iki eksene de eşlenir).
    // ------------------------------------------------------------------
    function riskMatrixHtml(risk) {
        const rm = risk.risk_matrix || {};
        const axes = rm.axes || {};
        // V301/NK-19 (28 Eki): uç eksen adlarını İngilizce yayımlıyor; panel
        // onları aynen basıyordu (TR ekranda "Rare … Catastrophic"). Bilinen
        // adın sözlük karşılığı basılır; bilinmeyen ad AYNEN kalır.
        const eksenAdi = function (ad) {
            const anahtar = RISK_EKSEN_ANAHTARI[ad];
            return anahtar ? T(anahtar, ad) : ad;
        };
        const likelihood = (axes.likelihood || [
            'Rare', 'Unlikely', 'Possible', 'Likely', 'Frequent']).map(eksenAdi);
        const severity = (axes.severity || [
            'Negligible', 'Minor', 'Major', 'Critical',
            'Catastrophic']).map(eksenAdi);
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

        // ÖH D20 / P12aB5-10: hücre/eksen/kapsayıcı yerleşimi ve renkleri
        // `results_hud.css` `.hd-riskmatrix` bloğunda yaşar. Buradaki satır
        // içi kopyalar kaldırıldı — satır içi stil sayfa stilini geçtiği için
        // aynı kuralın iki yerde durması tasarım katmanını ölü bırakıyordu.
        let html = '<div class="hd-riskmatrix" data-rows="5" data-cols="5">';

        // Satırlar: olabilirlik 5 (üst) → 1 (alt)
        for (let li = 5; li >= 1; li--) {
            html += `<div class="hd-rm-axis" data-axis="likelihood" data-index="${li}"
                >${likelihood[li - 1] || li}</div>`;
            for (let si = 1; si <= 5; si++) {
                // Hücre bandı: ortalama skor (l+s)/2, backend eşikleri
                const band = scoreBand((li + si) / 2);
                const key = li + ':' + si;
                const cellChips = (chips[key] || []).map(function (area) {
                    return `<span class="hd-rm-chip" data-risk="${area}"
                        title="${LBL[area] || area}: ${T('common.score', 'score')} ${U.fmt(risks[area], 1)} / 5"
                        >${AREA_SHORT[area] || area}</span>`;
                }).join('');
                const dolu = (chips[key] || []).length > 0;
                html += `<div class="hd-rm-cell${dolu ? ' hit' : ''}"
                    data-likelihood="${li}" data-severity="${si}"
                    data-band="${band}" data-risks="${(chips[key] || []).join(',')}"
                    >${cellChips}</div>`;
            }
        }
        // Alt eksen: şiddet başlıkları
        html += '<div class="hd-rm-corner"></div>';
        for (let si = 1; si <= 5; si++) {
            html += `<div class="hd-rm-axis" data-axis="severity" data-index="${si}"
                >${severity[si - 1] || si}</div>`;
        }
        html += '</div>';
        html += `<p style="font-size:0.68rem; color:var(--hd-ink-faint, #6a8491);
            font-family:var(--hd-mono); margin:4px 0 10px;">${
            T('panel.safety.matrixNote',
              'Rows: likelihood · Columns: severity · Single-score risks are placed on '
              + 'the diagonal (score maps to both axes).')}</p>`;

        // ---- Kabul ölçütü açıklaması (ÖH D15 / P11B4-11 kalıntısı) ----
        // ÖLÇÜLDÜ (b4_11_alan_ONCE.json): uç her bandın NE TALEP ETTİĞİNİ
        // `risk_matrix.acceptance` ile yayımlıyordu ("CRITICAL: Unacceptable —
        // redesign or re-site", "HIGH: Requires risk reduction before test",
        // ...); panel matrisi renkli çiziyor ama bu dört cümlenin HİÇBİRİNİ
        // basmıyordu. Kullanıcı hücrenin rengini görüyor, o rengin kendisinden
        // ne istediğini okuyamıyordu. Metin UCUN kendi metnidir — burada
        // yeniden yazılmaz, çevrilmez, sıralaması dışında dokunulmaz.
        const acc = rm.acceptance || {};
        const accKeys = Object.keys(acc);
        if (accKeys.length) {
            const SIRA = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
            const sirali = SIRA.filter(function (k) { return k in acc; })
                .concat(accKeys.filter(function (k) {
                    return SIRA.indexOf(k) === -1;
                }));
            // V301/NK-19 (28 Eki): sol sütun ham makine yolunu
            // ("risk_matrix.acceptance.LOW"), sağ sütun ucun İngilizce
            // cümlesini basıyordu. Bant adı ve cümle sözlükten gelir; EN
            // sözlük metni ucun metniyle aynıdır (bekçi:
            // tests/test_v301_risk_matrisi_dil.py). Tanınmayan bant AYNEN.
            // Anahtarlar SABİT adla çağrılır (kullanılmayan anahtar denetimi
            // tests/test_i18n_common.py dinamik birleştirmeyi görmez).
            const BANT_ADI = {
                LOW: T('panel.safety.accBand.LOW', 'LOW'),
                MEDIUM: T('panel.safety.accBand.MEDIUM', 'MEDIUM'),
                HIGH: T('panel.safety.accBand.HIGH', 'HIGH'),
                CRITICAL: T('panel.safety.accBand.CRITICAL', 'CRITICAL'),
            };
            const KABUL_CUMLESI = {
                LOW: T('panel.safety.acc.LOW', String(acc.LOW)),
                MEDIUM: T('panel.safety.acc.MEDIUM', String(acc.MEDIUM)),
                HIGH: T('panel.safety.acc.HIGH', String(acc.HIGH)),
                CRITICAL: T('panel.safety.acc.CRITICAL', String(acc.CRITICAL)),
            };
            html += U.kvTable(sirali.map(function (k) {
                const bilinen = SIRA.indexOf(k) !== -1;
                return ['<span data-safety-field="risk_matrix.acceptance.'
                    + esc(k) + '">'
                    + esc(bilinen ? BANT_ADI[k] : k)
                    + '</span>',
                    '<span style="color:'
                    + U.kindColor(bandKind(String(k).toLowerCase()))
                    + ';">' + esc(bilinen ? KABUL_CUMLESI[k] : String(acc[k]))
                    + '</span>'];
            }));
        }
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

    // Sayı ya da '—' (kullanıcı dilinde ondalık; U.num boş dize döndürür).
    function nb(v, d) {
        return isNum(v) ? U.num(v, d) : '—';
    }

    // V306/GÜVENLİK (NR-19) — DEĞERLENDİRİLEN KATMAN. Uç
    // `pressure_safety.evaluated_layer` ile patlama basıncının hangi
    // katmanda (tek cidar ya da iki katmanlı sıvı cidarın dış kabuğu) ve o
    // katmanın işletmede hangi basıncı taşıdığını yayımlar. Sayılar ucun;
    // burada yalnız biçimlenir.
    // V306/SIVI-KÜTLE (kalem 3): motor dış kabuğu YAYIMLAMADIYSA uç katmanı
    // `withheld` imiyle döner; satır nedenini adıyla söyler, sayı basılmaz.
    const LAYER_WITHHELD_TEXT = {
        cooling_circuit_not_solved: ['panel.safety.layerWithheld.cooling_circuit_not_solved',
            'closeout (outer shell) of the two-layer regenerative wall — NOT evaluated: the regenerative cooling circuit of this design is not solved and the closeout is sized from that circuit, so the motor does not publish this layer. No burst pressure, burst margin or vessel verdict is computed for it, and the drawn wall (liner + channels + closeout) is not evaluated as a solid wall in its place.'],
        closeout_verdict_withheld: ['panel.safety.layerWithheld.closeout_verdict_withheld',
            'closeout (outer shell) of the two-layer regenerative wall — NOT evaluated: the motor withheld its closeout verdict (see the motor\'s structural result). No burst pressure, burst margin or vessel verdict is computed for it, and the drawn wall is not evaluated as a solid wall in its place.'],
        closeout_not_evaluated: ['panel.safety.layerWithheld.closeout_not_evaluated',
            'closeout (outer shell) of the two-layer regenerative wall — NOT evaluated: the motor did not size or evaluate the closeout. No burst pressure, burst margin or vessel verdict is computed for it, and the drawn wall is not evaluated as a solid wall in its place.'],
    };
    function evaluatedLayerRow(rows, el, pc) {
        if (!el || typeof el !== 'object' || !el.role) return;
        let metin;
        if (el.withheld === true) {
            const k = LAYER_WITHHELD_TEXT[el.withheld_code];
            if (!k) return;
            metin = T(k[0], k[1]);
        } else if (el.role === 'closeout') {
            metin = U.tf('panel.safety.layerCloseout', {
                material: String(el.material || el.material_key || '—'),
                t: nb(el.thickness_mm, 2), d: nb(el.inner_diameter_mm, 1),
                T: nb(el.temperature_K, 1), p: nb(el.load_pressure_bar, 1),
                pc: nb(pc, 1), s: nb(el.motor_hoop_stress_MPa, 1),
                m: nb(el.burst_margin_vs_load_pressure, 2),
                stack: nb(el.stack_thickness_mm, 2),
                dc: nb(el.chamber_diameter_mm, 1) },
                'closeout (outer shell) of the two-layer regenerative wall — '
                + '{material}, {t} mm, inner diameter {d} mm, at {T} K (the '
                + 'temperature the motor solved for it). In operation this '
                + 'layer carries the coolant pressure {p} bar (chamber '
                + 'pressure {pc} bar); the motor\'s hoop stress {s} MPa is '
                + 'this layer at that pressure. Predicted burst pressure / '
                + 'coolant pressure = {m}. The drawn wall {stack} mm at the '
                + 'chamber diameter {dc} mm is liner + channels + closeout, '
                + 'not a solid wall, and is not used.');
        } else {
            metin = U.tf('panel.safety.layerSingle', {
                material: String(el.material || el.material_key || '—'),
                t: nb(el.thickness_mm, 2), d: nb(el.inner_diameter_mm, 1),
                p: nb(el.load_pressure_bar, 1) },
                'chamber wall (single wall, as entered) — {material}, {t} '
                + 'mm, inner diameter {d} mm; load: chamber pressure {p} bar');
        }
        rows.push([fieldLabelUser('evaluated_layer',
            T('panel.safety.layerLabel', 'Evaluated layer')),
            '<span data-safety-layer="' + esc(String(el.role)) + '"'
            + ' style="font-size:0.74rem; line-height:1.45;">' + esc(metin)
            + '</span>']);
    }

    // Kullanıcı etiketi; makine yolu yalnız `data-safety-field` niteliğinde
    // (ekran süpürmesi ad+değer bağını oradan kurar), görünür metinde değil.
    function fieldLabelUser(path, label) {
        return '<span data-safety-field="' + esc(path) + '">' + esc(label)
            + '</span>';
    }

    // V306/GÜVENLİK (NR-4) — Basınçlı Kap Özeti kullanıcı dilinde.
    // Sözcük tabloları ucun yayımladığı sabit değerlerin karşılığıdır
    // (safety_analysis._analyze_pressure_vessel_safety); tanınmayan değer
    // AYNEN basılır (uydurma çeviri yok). Anahtarlar literal.
    function vesselClassWord(v) {
        switch (String(v)) {
        case 'LOW_PRESSURE': return T('panel.safety.vesselClassWord.LOW_PRESSURE', 'LOW PRESSURE');
        case 'MEDIUM_PRESSURE': return T('panel.safety.vesselClassWord.MEDIUM_PRESSURE', 'MEDIUM PRESSURE');
        case 'HIGH_PRESSURE': return T('panel.safety.vesselClassWord.HIGH_PRESSURE', 'HIGH PRESSURE');
        default: return String(v).replace(/_/g, ' ');
        }
    }
    function inspectionText(v) {
        switch (String(v)) {
        case 'Annual visual, 5-year hydrostatic':
            return T('panel.safety.inspect.annual5', 'Annual visual, 5-year hydrostatic');
        case '2-year visual, 10-year hydrostatic':
            return T('panel.safety.inspect.y2y10', '2-year visual, 10-year hydrostatic');
        case '5-year visual, 15-year hydrostatic':
            return T('panel.safety.inspect.y5y15', '5-year visual, 15-year hydrostatic');
        default: return String(v);
        }
    }
    function severityWord(v) {
        switch (String(v).toLowerCase()) {
        case 'info': return T('panel.safety.sev.info', 'info');
        case 'warning': return T('panel.safety.sev.warning', 'warning');
        case 'critical': return T('panel.safety.sev.critical', 'critical');
        default: return String(v);
        }
    }
    function vesselStatusWord(v) {
        switch (String(v)) {
        case 'PASS': return T('panel.safety.vesselStatus.PASS', 'PASS');
        case 'MARGINAL': return T('panel.safety.vesselStatus.MARGINAL', 'MARGINAL');
        case 'FAIL': return T('panel.safety.vesselStatus.FAIL', 'FAIL');
        case 'NOT_EVALUATED': return T('panel.safety.vesselStatus.NOT_EVALUATED', 'NOT EVALUATED');
        default: return String(v);
        }
    }

    // Kullanıcı etiketli sayı satırı (değer yoksa satır KONMAZ).
    function addUserRow(rows, path, label, value, digits, unit) {
        if (!isNum(value)) return;
        rows.push([fieldLabelUser(path, label),
            monoCell(esc(U.num(value, digits)) + (unit ? ' ' + esc(unit) : ''))]);
    }

    // Uç künyesi: görünür satır kullanıcı cümlesidir; ucun ham cümlesi
    // kapalı "Teknik ayrıntı" altında AYNEN durur (akış paneli / DİL-2
    // deseni). Kullanıcı cümlesi yoksa ham cümle yalnız ayrıntıda kalır.
    function addBasisRow(rows, path, label, ham, kullanici) {
        if (typeof ham !== 'string' || !ham.trim()) return;
        rows.push([fieldLabelUser(path, label),
            '<span style="font-size:0.74rem; line-height:1.45;">'
            + (kullanici ? esc(kullanici) : '')
            + '<details style="margin-top:2px; font-size:0.72rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);"><summary style="cursor:pointer;">'
            + esc(T('common.techDetailSrv',
                    'Technical detail (solver statement, untranslated)'))
            + '</summary>' + esc(ham) + '</details></span>']);
    }

    function pressureVesselBlock(press) {
        if (!press || !Object.keys(press).length) return '';
        let html = U.sectionTitle(T('panel.safety.secVessel', 'Pressure Vessel Summary'));
        // V306/GÜVENLİK (NR-19): uç kabul (proof) testini hidrostatik test
        // sayar ve ikisine AYNI sayıyı yazar (AIAA S-080A, tek tanım). Aynı
        // sayı iki kutuda basılmaz; tek kutu ikisini birden adlar.
        const tekTest = isNum(press.proof_pressure_bar)
            && press.hydrostatic_test_pressure_bar === press.proof_pressure_bar;
        // V306/SIVI-KÜTLE (kalem 4-5): sıvı motor donanımında gereksinim
        // değerlendirilen katmanın MDP'sinden ve NASA-STD-5012C Tablo 1
        // katsayılarıyla; kutu ipuçları hangi standart olduğunu söyler.
        const k5012 = press.code_mode === 'nasa_std_5012c';
        html += `<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">`
            + U.statCard(T('panel.safety.pOperating', 'Operating'),
                nb(press.operating_pressure_bar, 1), 'bar')
            + U.statCard(T('panel.safety.pDesign', 'Design'),
                nb(press.design_pressure_bar, 1), 'bar')
            + (tekTest
                ? U.statCard(T('panel.safety.pProofHydro',
                               'Proof test (hydrostatic)'),
                    nb(press.proof_pressure_bar, 1), 'bar', null,
                    k5012
                        ? T('panel.safety.pProofHydroTip5012',
                            'Acceptance (proof) pressure test = 1.20 × MDP '
                            + '(NASA-STD-5012C Table 1, liquid engine hardware); '
                            + 'it is the hydrostatic test, no separate higher '
                            + 'acceptance test pressure is defined')
                        : T('panel.safety.pProofHydroTip',
                      'Acceptance (proof) pressure test = 1.5 × operating '
                      + 'pressure (AIAA S-080A); it is the hydrostatic test, '
                      + 'no separate higher test pressure is defined'))
                : U.statCard(T('panel.safety.pProof', 'Proof test'),
                    nb(press.proof_pressure_bar, 1), 'bar')
                  + U.statCard(T('panel.safety.pHydro', 'Hydrostatic test'),
                    nb(press.hydrostatic_test_pressure_bar, 1), 'bar'))
            + (k5012 && isNum(press.qualification_test_pressure_bar)
                ? U.statCard(T('panel.safety.pQual', 'Qualification test'),
                    nb(press.qualification_test_pressure_bar, 1), 'bar', null,
                    T('panel.safety.pQualTip',
                      'Qualification pressure test = 1.50 × MDP '
                      + '(NASA-STD-5012C Table 1, liquid engine hardware)'))
                : '')
            + U.statCard(T('panel.safety.pBurst', 'Burst target'),
                nb(press.required_burst_pressure_bar, 1), 'bar', 'warn',
                k5012
                    ? T('panel.safety.pBurstTip5012',
                        'Minimum required burst pressure = 1.50 × MDP '
                        + '(NASA-STD-5012C Table 1, liquid engine hardware: '
                        + 'ultimate-pressure analysis factor of safety)')
                    : T('panel.safety.pBurstTip',
                  'Minimum required burst pressure = 2.0 × operating '
                  + 'pressure (AIAA S-080A)'))
            + '</div>';
        const rows = [];
        // NR-19: patlama basıncının HANGİ katmanda, HANGİ yükle
        // değerlendirildiği — tablonun ilk satırı.
        evaluatedLayerRow(rows, press.evaluated_layer,
                          press.operating_pressure_bar);
        // V306/SIVI-KÜTLE (kalem 4): gereksinimin kurulduğu basınç —
        // değerlendirilen katmanın MDP'si (tek cidarda oda basıncı).
        addUserRow(rows, 'mdp_bar',
            T('panel.safety.pMdp', 'MDP (evaluated layer)'),
            press.mdp_bar, 1, 'bar');
        addBasisRow(rows, 'mdp_basis',
            T('panel.safety.basisLabel', 'Basis'), press.mdp_basis,
            T('panel.safety.pMdpTip',
              'Maximum design pressure of the evaluated layer: the largest pressure difference it carries (closeout of a two-layer wall: the highest jacket coolant pressure). The test and burst requirements are built from it.'));
        // V306/GÜVENLİK (NR-4): satır etiketleri KULLANICI DİLİNDE; makine
        // yolu yalnız `data-safety-field` niteliğinde kalır (ekran
        // süpürmesi ad+değer bağını oradan kurar). Sayılar kullanıcı
        // ondalığıyla (TR virgül). Uç künyeleri (İngilizce, makine adlı)
        // kapalı "Teknik ayrıntı" altında AYNEN; görünür satır kısa
        // kullanıcı cümlesidir.
        if (press.vessel_classification) {
            rows.push([fieldLabelUser('vessel_classification',
                T('panel.safety.vesselClass', 'Vessel classification')),
                U.badge(esc(vesselClassWord(press.vessel_classification)),
                        'info')]);
        }
        if (press.inspection_requirements) {
            rows.push([fieldLabelUser('inspection_requirements',
                T('panel.safety.inspection', 'Inspection')),
                esc(inspectionText(press.inspection_requirements))]);
        }
        // V306/SIVI-KÜTLE (kalem 5): deneme/patlama gereksiniminin standardı.
        addBasisRow(rows, 'code_basis',
            T('panel.safety.codeLabel', 'Test and burst requirement standard'),
            (typeof press.code_basis === 'string' && press.code_mode)
                ? String(press.code_mode) + ': ' + press.code_basis
                : press.code_basis,
            k5012
                ? T('panel.safety.code5012',
                    'NASA-STD-5012C (2025-12-31), Table 1: liquid engine hardware (chamber layers). Propellant tanks and lines follow AIAA S-080A.')
                : T('panel.safety.codeS080',
                    'AIAA S-080A-2018: metallic pressure vessels'));
        if (press.applicable_codes && press.applicable_codes.length) {
            rows.push([fieldLabelUser('applicable_codes',
                T('panel.safety.codes', 'Applicable codes')),
                esc(press.applicable_codes.join(' · '))]);
        }
        if (press.safety_devices_required && press.safety_devices_required.length) {
            // D-track: backend {code,params,severity} döndürür; aygıt başına
            // satır + ucun kendi ağırlık beyanı (ÖH D15 / P11B4-11).
            press.safety_devices_required.forEach(function (dev, i) {
                const sev = (dev && dev.severity) ? String(dev.severity) : null;
                rows.push([fieldLabelUser('safety_devices_required[' + i + ']',
                    U.tf('panel.safety.deviceN', { n: i + 1 },
                         'Safety device {n}')),
                    U.warnText(dev)
                    + (sev ? ' ' + U.badge(esc(severityWord(sev)),
                                           severityKind(sev)) : '')]);
            });
        }
        // Kabın geometrisi ve tahmini patlama basıncı (ÖH D29 · OH-D28-04,
        // ÖH D15 / P11B4-11). Uç `pressure_safety`yi MİLİMETRE yayımlar.
        addUserRow(rows, 'inner_diameter_mm',
            T('panel.safety.innerDiameter', 'Inner diameter'),
            press.inner_diameter_mm, 1, 'mm');
        addUserRow(rows, 'wall_thickness_mm',
            T('panel.safety.wallThickness', 'Wall thickness'),
            press.wall_thickness_mm, 2, 'mm');
        addUserRow(rows, 'actual_burst_pressure_bar',
            T('panel.safety.predictedBurst', 'Predicted burst pressure'),
            press.actual_burst_pressure_bar, 1, 'bar');
        addBasisRow(rows, 'actual_burst_pressure_basis',
            T('panel.safety.basisLabel', 'Basis'),
            press.actual_burst_pressure_basis,
            T('panel.safety.burstBasisText',
              'model prediction, not a measured strength: the smaller of the '
              + 'Faupel (1956) thick-wall and Harvey thin-wall bursting '
              + 'relations; no burst test and no batch coupon data'));
        addUserRow(rows, 'burst_margin',
            T('panel.safety.burstMarginReq',
              'Burst margin (vs required burst pressure)'),
            press.burst_margin, 2, '');
        addUserRow(rows, 'burst_margin_vs_meop',
            T('panel.safety.burstMarginMeop',
              'Burst margin (vs operating pressure)'),
            press.burst_margin_vs_meop, 2, '');
        addBasisRow(rows, 'burst_margin_definition',
            T('panel.safety.marginDefLabel', 'Margin definitions'),
            press.burst_margin_definition,
            T('panel.safety.burstMarginDefText',
              'the first margin is against the required burst pressure, the '
              + 'second against the operating pressure; they differ by the '
              + 'burst factor and are not compared to the same thresholds'));
        addBasisRow(rows, 'design_pressure_basis',
            T('panel.safety.designBasisLabel', 'Design pressure'),
            press.design_pressure_basis,
            isNum(press.design_pressure_factor)
                ? U.tf('panel.safety.designBasisText',
                       { f: U.num(press.design_pressure_factor, 2) },
                       'operating pressure × {f} (HRMA safety margin)')
                : null);
        addBasisRow(rows, 'burst_pressure_source',
            T('panel.safety.burstModelLabel', 'Burst pressure model'),
            press.burst_pressure_source,
            T('panel.safety.burstModelText',
              'Faupel thick-wall / thin-wall plastic limit'));
        if (press.vessel_status) {
            const st = String(press.vessel_status);
            rows.push([fieldLabelUser('vessel_status',
                T('panel.safety.vesselStatus', 'Vessel status')),
                U.badge(esc(vesselStatusWord(st)), st === 'PASS' ? 'ok'
                    : (st === 'NOT_EVALUATED' ? 'warn' : 'err'))]);
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
        // ÖH D15 / P11B4-11 kalıntısı: ucun kendi beyan kodu
        // (`compliance.disclaimer_code`) ekranda hiç görünmüyordu — aşağıdaki
        // cümlenin güvertenin kendi metni mi yoksa UCUN beyanı mı olduğu
        // okunamıyordu. Kod makine yoluyla basılır (yeni çeviri anahtarı yok).
        // V306/GÜVENLİK (NR-4): ucun beyan kodu görünür etiket değildir;
        // kapalı "Teknik ayrıntı" altında, cümlenin ucun beyanı olduğunu
        // gösteren tek iz olarak durur.
        const kod = comp.disclaimer_code
            ? '<details data-safety-field="compliance.disclaimer_code"'
              + ' style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);">'
              + '<summary style="cursor:pointer;">'
              + esc(T('common.techDetailSrv',
                      'Technical detail (solver statement, untranslated)'))
              + '</summary>' + esc(String(comp.disclaimer_code)) + '</details>'
            : '';
        return U.sectionTitle(T('panel.safety.secCompliance', 'Regulatory compliance'))
            + `<div style="border:1px solid ${U.kindColor('warn')}; border-radius:8px;
                 padding:10px 14px; margin:8px 0; color:${U.kindColor('warn')};">
                 ${note}</div>` + kod;
    }

    // ------------------------------------------------------------------
    // VARSAYILAN KÜNYESİ — uçun `defaults_applied` beyanı
    // ------------------------------------------------------------------
    // /analyze_safety, zorunlu OLMAYAN bir alan istekte yoksa kendi
    // varsayılanını kullanır ve bunu yanıtın `defaults_applied` listesiyle
    // BEYAN EDER (app.py::analyze_safety). ÖLÇÜLDÜ (2026-08-18, gerçek uç
    // yanıtı + node içinde gerçek render): panel bu listeyi hiç okumuyordu.
    // Yalnız dört zorunlu alanı taşıyan bir istekte uç ALTI alanı
    // (chamber_temperature, thrust, burn_time, propellant_type,
    // facility_type, material) kendi varsayılanından alıyor; ekranda ise
    // bunun tek bir izi yoktu — kullanıcı TNT eşdeğerini, tahliye
    // mesafesini, muayene aralığını ve basınçlı kap emniyetini kendi
    // verisinden çıkmış sanıyordu. Künye güvertenin ASSUMED çipiyle basılır
    // (analysis_dock source katmanı — renk + şekil + ipucu tek yerden).
    //
    // Beyan HİÇ yoksa (alan yanıtta yok: eski/başka bir uç) hiçbir şey
    // iddia edilmez, blok BASILMAZ. Boş liste ise beyanın KENDİSİDİR:
    // "hiçbir alan varsayılandan gelmedi" ayrı bir bilgidir, gösterilir.
    // ÖH D15 / P11B4-13 — DÜRÜSTLÜK CÜMLESİ ÖLÇÜMLE YANLIŞTI.
    // ÖLÇÜLDÜ (once.json, gerçek /analyze_safety yanıtı + node render):
    // panel bütün FIELDS alanlarını gönderdiği için uç `defaults_applied: []`
    // döndürüyor ve panel "every input behind the numbers below came from
    // this form" cümlesini basıyordu. AYNI yanıtta iki alan kendi
    // varsayımını BEYAN ediyor:
    //   thermal_safety.radiating_area_basis
    //     = "ASSUMED L/D = 5 (chamber_length was not supplied)"
    //   explosive_hazards.fragment_hazards.case_mass_basis  (aynı varsayım)
    // `chamber_length` panelin FIELDS listesinde HİÇ yok, yani kullanıcı onu
    // gönderemiyor; `defaults_applied` sözleşmesi de bu varsayımı kapsamıyor.
    // Cümle bu yüzden ekrandaki EN GÜÇLÜ dürüstlük iddiasıyken FİİLEN YANLIŞ.
    //
    // Kusur, künye eklenerek değil YANLIŞ CÜMLE KALDIRILARAK giderilir:
    // yanıtın kendi ağacı ASSUMED beyanı için taranır (alan adı gömülü
    // DEĞİL — beyanın kendisi aranır); beyan varsa mutlak cümle basılmaz,
    // yerine beyanı YAPAN alanların makine yolu listelenir. Sayı üretilmez,
    // varsayım "düzeltilmez": ekran yalnız gerçeği söyler.
    const ASSUMED_RE = /\bASSUMED\b/;

    function scanAssumedBases(node, path, out, depth) {
        if (!node || depth > 6 || out.length >= 12) return out;
        if (typeof node === 'string') {
            if (ASSUMED_RE.test(node)) out.push([path, node]);
            return out;
        }
        if (Array.isArray(node)) {
            node.forEach(function (v, i) {
                scanAssumedBases(v, path + '[' + i + ']', out, depth + 1);
            });
            return out;
        }
        if (typeof node === 'object') {
            Object.keys(node).forEach(function (k) {
                scanAssumedBases(node[k], path ? path + '.' + k : k, out, depth + 1);
            });
        }
        return out;
    }

    function declaredAssumptions(data) {
        if (!data || typeof data !== 'object') return [];
        return scanAssumedBases(data.safety_analysis, '', [], 0);
    }

    function defaultsBlock(applied, data) {
        if (!Array.isArray(applied)) return '';
        const title = U.sectionTitle(T('panel.safety.secDefaults',
            'Inputs the endpoint filled from its own defaults'));
        if (!applied.length) {
            const assumed = declaredAssumptions(data);
            if (assumed.length) {
                // Mutlak cümle KAZANILMADI: uç bu yanıtta kendi geometri
                // varsayımını beyan ediyor. Beyanı yapan alanlar makine
                // yoluyla, ucun KENDİ cümlesiyle basılır.
                return title
                    + '<p data-safety-defaults="assumed" style="font-size:0.7rem;'
                    + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 8px;">'
                    + esc(U.tf('panel.safety.defaultsNote',
                        { n: assumed.length },
                        '{n} input(s) below did not come from you. The risk '
                        + 'scores, TNT equivalent, stand-off distances and '
                        + 'pressure-vessel margins on this page were computed '
                        + 'with these values.'))
                    + '</p>'
                    + U.kvTable(assumed.map(function (pair) {
                        return [machineLabel(pair[0]),
                            '<span data-safety-assumed="' + esc(pair[0]) + '"'
                            + ' style="font-size:0.72rem;">' + esc(pair[1])
                            + '</span>'
                            // ÖH D26 / P11B2-10 — damga ELLE konmuyor:
                            // hüküm ucun KENDİ cümlesinden (pair[1]) ortak
                            // sınıflandırıcıyla çıkar. Uç cümlesini
                            // değiştirirse çip de onunla değişir.
                            + U.source.chip(U.source.of({ basis: pair[1] },
                                null, { value: pair[1] }))];
                    }));
            }
            return title + '<p data-safety-defaults="none" style="font-size:0.7rem;'
                + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 10px;">'
                + esc(T('panel.safety.noDefaults',
                    'The endpoint declared no defaults: every input behind the '
                    + 'numbers below came from this form.')) + '</p>';
        }
        const basis = T('panel.safety.defaultsBasis',
            'The request did not carry this field, so the endpoint used its own '
            + 'default value — the number below is not yours.');
        const rows = applied.map(function (key) {
            return [fieldLabel(key),
                '<span data-safety-default="' + esc(key) + '"'
                + ' style="font-family:var(--hd-mono); font-size:0.7rem;">'
                + esc(key) + '</span>'
                // ÖH D26 / P11B2-10 — hüküm metinden türer (elle damga yok).
                + U.source.chip(U.source.of({ basis: basis }, null,
                                            { value: basis }))];
        });
        return title
            + '<p data-safety-defaults="list" style="font-size:0.7rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 8px;">'
            + esc(U.tf('panel.safety.defaultsNote', { n: applied.length },
                '{n} input(s) below did not come from you. The risk scores, TNT '
                + 'equivalent, stand-off distances and pressure-vessel margins '
                + 'on this page were computed with these values.')) + '</p>'
            + U.kvTable(rows);
    }

    // ==================================================================
    // Ç — UCUN YAYIMLADIĞI BLOKLAR EKRANA İNİYOR (OH-B3-01 + OH-B4-02)
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (2026-08-27, app.test_client, POST /analyze_safety, panelin
    // kendi alan varsayılanlarıyla): uç `safety_analysis` altında 13 blok
    // yayımlıyor; panel bunlardan yalnız üçünü (risk_assessment,
    // pressure_safety, compliance) + `recommendations`ı çiziyordu.
    // DOKUZ blok — 89 çocuk alan — ekrana HİÇ inmiyordu:
    //   explosive_hazards 11, thermal_safety 32, structural_safety 12,
    //   fire_hazards 7, toxic_hazards 7, inputs_used 6,
    //   operational_safety 6, emergency_procedures 4, safety_equipment 4
    // Yani TNT eşdeğeri, patlama/parça mesafeleri, quantity-distance
    // tablosu, hoop gerilmesi, emniyet katsayıları ve termal hükmün
    // KENDİSİ hesaplanıyor ama kullanıcıya gösterilmiyordu.
    //
    // ETİKETLER — bu tur i18n anahtarı AÇMAZ. Panelin kendi TESCİLLİ
    // deseni uygulanır (bkz. `fieldLabel`: "panelde karşılığı olmayan bir
    // alanı beyan ederse adı HAM basılır — uydurma etiket yazmak beyanı
    // çarpıtırdı"). Her satırın etiketi, değerin geldiği MAKİNE YOLUdur;
    // bölüm başlığı da blokun yanıttaki adıdır. i18n süpürme dalgası
    // anahtarları bu adlara takacak (bkz. rapor: bekçi-borcu).
    //
    // FAIL-CLOSED — satır YALNIZ yanıtta gerçekten bulunan değer için
    // konur. `null` bir sayı değildir: ya satır hiç konmaz, ya da uç onu
    // "değerlendirilmedi" diye BEYAN ettiyse '—' + NOT MODELLED çipiyle
    // konur (`addWithheldRow`). Hiçbir dalda uydurma sayı yazılmaz.
    // ==================================================================

    function isNum(v) {
        return typeof v === 'number' && Number.isFinite(v);
    }

    // Değerin geldiği makine yolu — satırın etiketi budur.
    function machineLabel(path) {
        return '<span data-safety-field="' + esc(path) + '"'
            + ' style="font-family:var(--hd-mono); font-size:0.72rem;">'
            + esc(path) + '</span>';
    }

    function monoCell(text) {
        return '<span style="font-family:var(--hd-mono);">' + text + '</span>';
    }

    // Tek satır. Değer yoksa (null/undefined/boş metin/sonsuz sayı) SATIR
    // KONMAZ — yokluğun yerine sayı uydurulmaz.
    function addRow(rows, path, value, digits, unit) {
        if (value === null || value === undefined) return;
        if (typeof value === 'number') {
            if (!Number.isFinite(value)) return;
            rows.push([machineLabel(path),
                monoCell(U.fmt(value, digits == null ? 2 : digits)
                         + (unit ? ' ' + esc(unit) : ''))]);
            return;
        }
        if (typeof value === 'boolean') {
            rows.push([machineLabel(path),
                U.badge(String(value), value ? 'warn' : 'ok')]);
            return;
        }
        const text = String(value);
        if (!text) return;
        rows.push([machineLabel(path), esc(text)]);
    }

    // Uç bu alanı "değerlendirilmedi" diye BEYAN etti: '—' + NOT MODELLED
    // çipi (gerekçe ipucunda). Sayı yerine boşluk değil, BEYAN görünür.
    function addWithheldRow(rows, path, basis) {
        rows.push([machineLabel(path),
            '<span data-safety-withheld="' + esc(path) + '">—</span>'
            // ÖH D26 / P11B2-10 — 'missing' hükmü de sınıflandırıcıdan:
            // değer YOK (value:null) olduğu için sayı kapısı kapanır.
            + U.source.chip(U.source.of({ basis: basis || null }, null,
                                        { value: null }))]);
    }

    // Metin listesi (prosedür / gereklilik dizileri). Sunucu kaydı sözlük
    // de olabilir; `U.warnText` üç biçimi de okur ({code,params,severity},
    // düz metin, iç içe liste) — ham join() '[object Object]' basardı.
    function addListRow(rows, path, items) {
        if (!Array.isArray(items) || !items.length) return;
        rows.push([machineLabel(path),
            '<ul style="margin:0 0 0 16px; padding:0;">'
            + items.map(function (x) { return '<li>' + U.warnText(x) + '</li>'; })
                   .join('') + '</ul>']);
    }

    // {distance_m, overpressure_kpa, scaled_distance_m_per_kg13, basis}
    // ÖH D28 / arayuz a1 (OH-D27-16) — MESAFENİN KÜNYESİ EKRANDA.
    // ÖLÇÜLDÜ (a1/once.json, taban 7cd08bcc): D26 / yapisal-sistem a1
    // (`aabdcdcd`, P5B2-05) patlama mesafelerini elle yazılmış Z
    // tablosundan Kinney-Graham bağıntısına taşıdı ve her kayda `basis`
    // (model künyesi) + `scaled_distance_m_per_kg13` (Hopkinson-Cranz
    // ölçekli mesafe Z) ekledi; bu okuyucu 374 baytlık gövdesinde
    // İKİSİNİ DE 0 kez okuyordu. Kullanıcı emniyet mesafesini görüyor,
    // hangi modelden geldiğini ve hangi Z'ye denk düştüğünü göremiyordu
    // — oysa eski tablo o bağıntıyla UYUŞMUYORDU (property_damage'da
    // -%52,8 KISA taraf), yani künye tam da bu yüzden eklendi.
    // Alanlar AYNEN basılır; yoksa parça eklenmez (fail-closed, panel
    // ne Z ne model adı UYDURUR).
    // `basis` dört kaydın DÖRDÜNDE de aynı dizedir (tek model beyanı);
    // ekrana bir kez yazılır. `durum` nesnesi son yazılan künyeyi tutar,
    // FARKLI bir künye gelirse o da basılır — susturma değil, tekrar
    // bastırmadır.
    function addBlastRow(rows, path, o, durum) {
        if (!o || !isNum(o.distance_m)) return;
        let hucre = U.fmt(o.distance_m, 1) + ' m'
            + (isNum(o.overpressure_kpa)
                ? ' @ ' + U.fmt(o.overpressure_kpa, 1) + ' kPa' : '');
        if (isNum(o.scaled_distance_m_per_kg13)) {
            hucre += ' · Z = ' + U.fmt(o.scaled_distance_m_per_kg13, 4)
                + ' m/kg^(1/3)';
        }
        rows.push([machineLabel(path), monoCell(hucre)]);
        const kunye = o.basis;
        if (kunye && durum && durum.sonBasis !== kunye) {
            durum.sonBasis = kunye;
            rows.push([machineLabel(path + '.basis'),
                '<span style="font-size:0.72rem; line-height:1.4;">'
                + esc(String(kunye)) + '</span>']);
        }
    }

    // {distance_m, k_factor} çifti (quantity-distance tablosu)
    function addQdRow(rows, path, o) {
        if (!o || !isNum(o.distance_m)) return;
        rows.push([machineLabel(path),
            monoCell(U.fmt(o.distance_m, 1) + ' m'
                + (isNum(o.k_factor) ? ' · k = ' + U.fmt(o.k_factor, 3) : ''))]);
    }

    // Bölüm başlığı = blokun yanıttaki MAKİNE YOLU (çeviri gerektirmez;
    // kullanıcı hangi yanıt bloğunu okuduğunu birebir görür). Değişkenle
    // çağrılır — düz metin başlık yasağının kastettiği "çevrilmemiş UI
    // cümlesi" değildir.
    function blockSection(name, rows) {
        if (!rows.length) return '';
        const path = 'safety_analysis.' + name;
        return U.sectionTitle(path) + U.kvTable(rows);
    }

    // ==================================================================
    // ÖH D36 / onemli2-sivi a2 — SÜREYE BAĞLI KOLLAR EKRANDA ADIYLA
    // ------------------------------------------------------------------
    // Uç (safety_analysis.py, a2 Madde 2) yanma süresi verilmediğinde
    // süreye bağlı alanları None yapar ve bunu BEYAN eder: termal blokta
    // `burn_time_not_evaluated` + `burn_time_reason`, serbest kalan motorda
    // `not_evaluated` + `reason`, üst seviyede
    // `burn_time_dependent_not_evaluated` {status, reason, fields}. Bu
    // okuyucu beyanlı boşluğu eskiden SESSİZCE atlıyordu (addRow null'da
    // satır koymaz) — kullanıcı "maruziyet süresi" satırının neden
    // kaybolduğunu göremezdi. Kural termal kardeşiyle (addThermalRow) aynı:
    // beyanlıysa satır '—' + NOT MODELLED çipiyle KONUR, beyansız boşluk
    // atlanır. Süre verildiğinde beyan yoktur ve satırlar eskisi gibidir.
    // ==================================================================
    function burnTimeGate(fields, reason) {
        return { fields: Array.isArray(fields) ? fields : [],
                 reason: reason || null };
    }

    // `key`: beyan listesinde aranan ad; `path`: ekrandaki makine yolu.
    function addGatedRow(rows, gate, path, key, value, digits, unit) {
        if ((value === null || value === undefined)
                && gate && gate.fields.indexOf(key) !== -1) {
            addWithheldRow(rows, path, gate.reason);
            return;
        }
        addRow(rows, path, value, digits, unit);
    }

    function inputsUsedBlock(b, burnTimeDecl) {
        if (!b) return '';
        const decl = (burnTimeDecl && typeof burnTimeDecl === 'object')
            ? burnTimeDecl : null;
        const gate = burnTimeGate(decl && decl.fields, decl && decl.reason);
        const rows = [];
        addRow(rows, 'motor_type', b.motor_type);
        addRow(rows, 'propellant_type', b.propellant_type);
        addRow(rows, 'facility_type', b.facility_type);
        addRow(rows, 'chamber_material', b.chamber_material);
        addRow(rows, 'thrust_n', b.thrust_n, 1, 'N');
        addGatedRow(rows, gate, 'burn_time_s', 'inputs_used.burn_time_s',
                    b.burn_time_s, 2, 's');
        if (gate.fields.length) {
            // Görünür beyan (ipucuna gömülmez, ÖH D21 / P17B2-08): panel
            // cümlesi EN+TR sözlükte; hangi alanların geri çekildiği ucun
            // KENDİ listesinden makine yoluyla basılır (uydurma liste yok).
            rows.push([machineLabel('burn_time_dependent_not_evaluated'),
                '<span data-safety-burn-time-withheld="1"'
                + ' style="font-size:0.72rem; line-height:1.4;">'
                + esc(T('panel.safety.burnTimeWithheldNote',
                    'Burn time was not supplied and no duration is assumed, '
                    + 'so the items listed below that depend on it were not '
                    + 'evaluated. Enter a burn time to get them.'))
                + '</span>']);
            rows.push([machineLabel('burn_time_dependent_not_evaluated.fields'),
                monoCell(esc(gate.fields.map(String).join(', ')))]);
        }
        return blockSection('inputs_used', rows);
    }

    function structuralSafetyBlock(b) {
        if (!b) return '';
        const rows = [];
        // V301/PANEL (NK-18): hükmün KAYNAĞI önce söylenir. Motorun zinciri
        // ise Performans Özeti ile aynı kayıttır; geri çekme gerekçesi ve
        // dayanak cümlesi çözücünün kendi metnidir (burada yazılmaz).
        if (b.verdict_source === 'motor_structural_chain') {
            rows.push([machineLabel('verdict_source'),
                '<span data-safety-verdict-source="motor_structural_chain"'
                + ' style="font-size:0.72rem; line-height:1.4;">'
                + esc(T('panel.safety.verdictFromMotor',
                    'This structural verdict is the motor\'s own structural '
                    + 'chain — the same record the Performance Summary '
                    + 'shows. The hoop numbers below are this panel\'s '
                    + 'diagnostic check, not a second verdict.'))
                + '</span>']);
        } else if (b.verdict_source) {
            rows.push([machineLabel('verdict_source'),
                '<span data-safety-verdict-source="' + esc(b.verdict_source)
                + '" style="font-size:0.72rem; line-height:1.4;">'
                + esc(T('panel.safety.verdictFromModule',
                    'This structural verdict is this panel\'s thin-wall hoop '
                    + 'check at room-temperature yield; no motor result '
                    + 'verdict applies to these inputs.'))
                + '</span>']);
        }
        addRow(rows, 'verdict_block', b.verdict_block);
        addRow(rows, 'verdict_withheld', b.verdict_withheld);
        if (Array.isArray(b.verdict_withheld_reasons)
            && b.verdict_withheld_reasons.length) {
            rows.push([machineLabel('verdict_withheld_reasons'),
                monoCell(esc(b.verdict_withheld_reasons.map(String)
                    .join(', ')))]);
        }
        addRow(rows, 'verdict_basis', b.verdict_basis);
        addRow(rows, 'verdict_risk_level', b.verdict_risk_level);
        addRow(rows, 'motor_verdict_safety_factor',
               b.motor_verdict_safety_factor, 2);
        const red = b.motor_verdict_not_adopted;
        if (red && typeof red === 'object') {
            rows.push([machineLabel('motor_verdict_not_adopted'),
                '<span data-safety-motor-verdict-not-adopted="1"'
                + ' style="font-size:0.72rem; line-height:1.4;">'
                + esc(T('panel.safety.motorVerdictNotAdopted',
                    'The structural inputs here differ from the motor result '
                    + 'they were filled from, so the motor\'s verdict does '
                    + 'not apply to this design.'))
                + (Array.isArray(red.fields) ? ' ' + monoCell(esc(
                    red.fields.map(function (f) {
                        return (f && f.field) + ': ' + (f && f.request)
                            + ' ≠ ' + (f && f.motor_result);
                    }).join('; '))) : '')
                + '</span>']);
            addRow(rows, 'motor_verdict_not_adopted.reason', red.reason);
            addRow(rows, 'motor_verdict_not_adopted.basis', red.basis);
        }
        addRow(rows, 'structural_integrity', b.structural_integrity);
        addRow(rows, 'module_structural_integrity_basis',
               b.module_structural_integrity_basis);
        addRow(rows, 'material', b.material);
        addRow(rows, 'material_name', b.material_name);
        addRow(rows, 'hoop_stress_mpa', b.hoop_stress_mpa, 2, 'MPa');
        addRow(rows, 'yield_strength_mpa', b.yield_strength_mpa, 1, 'MPa');
        addRow(rows, 'ultimate_strength_mpa', b.ultimate_strength_mpa, 1, 'MPa');
        addRow(rows, 'yield_safety_factor', b.yield_safety_factor, 2);
        addRow(rows, 'ultimate_safety_factor', b.ultimate_safety_factor, 2);
        // ÖH D15 birleşmesi (1 Eyl 2026) — BİRLEŞİK GERİLME ZİNCİRİ.
        // Uç, hoop + termal gradyan gerilmesini toplayıp HÜKMÜ bu üç
        // alandan veriyor (`governing_safety_factor` ısı çifti geldiğinde
        // yayımlanır). Panel yalnız hoop'tan gelen `yield_safety_factor`i
        // basıyordu: ölçüldü (ısı çiftli koşum) hoop SF ile birleşik SF
        // ayrışıyor ve ekranda YALNIZ iyimser olan görünüyordu. Künye
        // (`combined_stress_basis`) ısı zinciri kurulamadığında da gelir
        // ve "NOT EVALUATED" diye başlar — yani boşluk beyanlıdır.
        addRow(rows, 'combined_stress_mpa', b.combined_stress_mpa, 2, 'MPa');
        addRow(rows, 'combined_safety_factor', b.combined_safety_factor, 2);
        addRow(rows, 'governing_safety_factor', b.governing_safety_factor, 2);
        addRow(rows, 'combined_stress_basis', b.combined_stress_basis);
        addRow(rows, 'recommended_inspection_interval',
               b.recommended_inspection_interval);
        const likelihood = b.failure_likelihood || {};
        addRow(rows, 'failure_likelihood.likelihood_class',
               likelihood.likelihood_class);
        addRow(rows, 'failure_likelihood.basis', likelihood.basis);
        addRow(rows, 'failure_modes_basis', b.failure_modes_basis);
        const modes = b.failure_modes;
        if (Array.isArray(modes) && modes.length) {
            // V301/PANEL (ÖRNEK-PANEL DEVİR 2): listedeki "CRITICAL" bu
            // motorun hükmü DEĞİL, genel basınçlı kap kontrol listesinin
            // SONUÇ ağırlığıdır (uç alanı artık consequence_severity). Ekran
            // bunu adıyla söyler; hüküm yukarıdaki structural_integrity'dir.
            rows.push([machineLabel('failure_modes'),
                '<div style="font-size:0.72rem; line-height:1.4;"'
                + ' data-safety-failure-modes-note="1">'
                + esc(T('panel.safety.failureModesNotVerdict',
                    'Generic pressure-vessel checklist: the word after each '
                    + 'mode is the consequence if that failure occurred, not '
                    + 'a verdict for this motor.'))
                + '</div>'
                + modes.map(function (m) {
                    const agirlik = (m.consequence_severity !== undefined)
                        ? m.consequence_severity : m.severity;
                    return '<div>' + esc(m.mode) + ' — ' + esc(agirlik)
                        + ': ' + esc(m.consequences) + '</div>';
                }).join('')]);
        }
        return blockSection('structural_safety', rows);
    }

    // Termal blokta boş alanların ÇOĞU beyanlıdır: uç bunları
    // `thermal_not_evaluated` listesine koyar (ÖH Z3 onarımı). Beyanlıysa
    // satır '—' + NOT MODELLED ile KONUR; beyansız boşluk atlanır.
    // ÖH D36 / onemli2-sivi a2: `gate` (isteğe bağlı) süre beyanıdır —
    // cidar kapısının beyanı (`thermal_not_evaluated`) önce gelir, alan
    // orada yoksa süre beyanına bakılır.
    function addThermalRow(rows, notEvaluated, because, path, value,
                           digits, unit, gate) {
        if ((value === null || value === undefined)
                && notEvaluated.indexOf(path) !== -1) {
            addWithheldRow(rows, path, because);
            return;
        }
        addGatedRow(rows, gate || null, path, path, value, digits, unit);
    }

    // Termal eksen geri çekildiyse ve son öneri çifti bayrak yüzünden
    // göndermediyse nedeni ADIYLA basar (EN = TR sözlük metni + ısı
    // modülünün kendi uyarısı, kaçışlı). Kullanıcı çifti elle verdiyse uç
    // hükmü verir (geri çekme yok) ve bu not basılmaz.
    function wallWithheldNote(withheld) {
        if (!withheld || !wallPairWithheld) return '';
        const uyarilar = wallPairWithheld.warnings.map(function (w) {
            return esc(U.warnText(w));
        }).filter(Boolean);
        return '<p data-safety-wall-unphysical="1" style="font-size:0.75rem;'
            + ' color:var(--hd-orange, #ff8c33); margin:6px 0;">'
            + esc(T('panel.safety.wallPairUnphysical',
                'Thermal axis not evaluated: the wall temperature pair was '
                + 'NOT sent, because the heat module marks its own '
                + 'equilibrium wall temperature as unphysical '
                + '(heat_transfer_analysis.gas_side_analysis.'
                + 'wall_temperature_unphysical = true). This is not a '
                + 'missing input: the wall would fail before reaching that '
                + 'temperature. The heat module\'s own warning:'))
            + (uyarilar.length ? ' ' + uyarilar.join(' · ') : '')
            + '</p>';
    }

    function thermalSafetyBlock(b) {
        if (!b) return '';
        const notEvaluated = Array.isArray(b.thermal_not_evaluated)
            ? b.thermal_not_evaluated : [];
        const because = b.thermal_verdict_withheld_because
            || b.wall_temperature_source || null;
        // Süre beyanı (a2): uç süre verilmediğinde bu dört alanı adıyla
        // geri çeker (safety_analysis.THERMAL_BURN_TIME_FIELDS + kazanılmamış
        // thermal_protection_required).
        const bt = burnTimeGate(b.burn_time_not_evaluated, b.burn_time_reason);
        const rows = [];
        addRow(rows, 'thermal_verdict', b.thermal_verdict);
        addRow(rows, 'wall_temperature_source', b.wall_temperature_source);
        addRow(rows, 'thermal_verdict_withheld_because',
               b.thermal_verdict_withheld_because);
        addRow(rows, 'material', b.material);
        addRow(rows, 'material_name', b.material_name);
        addRow(rows, 'chamber_temperature_k', b.chamber_temperature_k, 1, 'K');
        addGatedRow(rows, bt, 'exposure_duration_s', 'exposure_duration_s',
                    b.exposure_duration_s, 2, 's');
        addRow(rows, 'material_max_service_temp_k',
               b.material_max_service_temp_k, 1, 'K');
        addRow(rows, 'material_melting_point_k', b.material_melting_point_k,
               1, 'K');
        addThermalRow(rows, notEvaluated, because, 'material_recommendation',
                      b.material_recommendation);
        addThermalRow(rows, notEvaluated, because,
                      'estimated_wall_temperature_k',
                      b.estimated_wall_temperature_k, 1, 'K');
        addThermalRow(rows, notEvaluated, because, 'inner_wall_temperature_k',
                      b.inner_wall_temperature_k, 1, 'K');
        addThermalRow(rows, notEvaluated, because, 'outer_wall_temperature_k',
                      b.outer_wall_temperature_k, 1, 'K');
        addThermalRow(rows, notEvaluated, because, 'wall_delta_T_k',
                      b.wall_delta_T_k, 1, 'K');
        addThermalRow(rows, notEvaluated, because,
                      'material_thermal_safety_factor',
                      b.material_thermal_safety_factor, 2);
        addThermalRow(rows, notEvaluated, because, 'melting_safety_factor',
                      b.melting_safety_factor, 2);
        addThermalRow(rows, notEvaluated, because,
                      'steel_thermal_safety_factor',
                      b.steel_thermal_safety_factor, 2);
        addThermalRow(rows, notEvaluated, because,
                      'aluminum_thermal_safety_factor',
                      b.aluminum_thermal_safety_factor, 2);
        addThermalRow(rows, notEvaluated, because, 'thermal_stress_mpa',
                      b.thermal_stress_mpa, 1, 'MPa');
        addRow(rows, 'thermal_stress_formula', b.thermal_stress_formula);
        // ÖH D15 birleşmesi (1 Eyl 2026) — TERMAL GERİLME HÜKMÜ + DAYANAĞI.
        // Uç sıcaklığa göre DÜŞÜRÜLMÜŞ akma dayanımını (ve ham kayıt
        // değerini) ayrı ayrı yayımlıyor; katsayı ikisinin oranıdır.
        // Üçü de `thermal_not_evaluated` listesine giriyor (ısı zinciri
        // kurulmadığında), o yüzden beyanlı boşluk kolundan basılır —
        // sessiz atlanırsa 'NOT MODELLED' çipi de düşerdi.
        addThermalRow(rows, notEvaluated, because,
                      'material_yield_strength_MPa',
                      b.material_yield_strength_MPa, 1, 'MPa');
        addThermalRow(rows, notEvaluated, because,
                      'derated_yield_strength_MPa',
                      b.derated_yield_strength_MPa, 1, 'MPa');
        addThermalRow(rows, notEvaluated, because,
                      'thermal_stress_safety_factor',
                      b.thermal_stress_safety_factor, 2);
        addRow(rows, 'thermal_stress_basis', b.thermal_stress_basis);
        addThermalRow(rows, notEvaluated, because, 'wall_exceeds_melting_point',
                      b.wall_exceeds_melting_point);
        addThermalRow(rows, notEvaluated, because, 'cooling_required',
                      b.cooling_required);
        addThermalRow(rows, notEvaluated, because, 'thermal_protection_required',
                      b.thermal_protection_required, undefined, undefined, bt);
        addRow(rows, 'surface_emissivity', b.surface_emissivity, 2);
        addRow(rows, 'radiating_area_m2', b.radiating_area_m2, 4, 'm²');
        addRow(rows, 'radiating_area_basis', b.radiating_area_basis);
        addThermalRow(rows, notEvaluated, because,
                      'radiating_surface_temperature_k',
                      b.radiating_surface_temperature_k, 1, 'K');
        addThermalRow(rows, notEvaluated, because,
                      'radiant_heat_hazard_distance_m',
                      b.radiant_heat_hazard_distance_m, 2, 'm');
        addThermalRow(rows, notEvaluated, because,
                      'radiant_flux_at_hazard_distance_kw_m2',
                      b.radiant_flux_at_hazard_distance_kw_m2, 2, 'kW/m²');
        addThermalRow(rows, notEvaluated, because,
                      'second_degree_burn_distance_m',
                      b.second_degree_burn_distance_m, 2, 'm', bt);
        addThermalRow(rows, notEvaluated, because,
                      'recommended_minimum_standoff_m',
                      b.recommended_minimum_standoff_m, 2, 'm', bt);
        addListRow(rows, 'thermal_not_evaluated', b.thermal_not_evaluated);
        // V306/GÜVENLİK (NR-3 a): motorun bölge sonucu varken çıplak cidar
        // uyarısı termal eksenin gerekçesi olarak BASILMAZ (bölge notu
        // bireysel risk tablosunun altında, tek yerde).
        return (motorZoneThermalNote(b)
                ? '' : wallWithheldNote(b.thermal_verdict === 'withheld'))
            + blockSection('thermal_safety', rows);
    }

    function explosiveHazardsBlock(b) {
        if (!b) return '';
        const rows = [];
        addRow(rows, 'explosive_classification', b.explosive_classification);
        addRow(rows, 'explosive_class', b.explosive_class);
        // ÖH D36 dil2 a2: dayanak cümlesi sunucu cümlesidir, serverText'ten
        // geçer (TR karşılığı varsa Türkçe, yoksa aynen).
        addReasonRow(rows, 'explosive_class_basis', b.explosive_class_basis);
        addRow(rows, 'propellant_mass_kg', b.propellant_mass_kg, 3, 'kg');
        addRow(rows, 'tnt_equivalent_kg', b.tnt_equivalent_kg, 3, 'kg');
        addRow(rows, 'tnt_equivalent_factor', b.tnt_equivalent_factor, 3);
        const blast = b.blast_distances || {};
        // OH-D27-16: `durum` künye tekrarını bastırır (dört kayıt aynı
        // model beyanını taşır); ilk kayıtta yazılır, farklısı gelirse
        // yeniden yazılır.
        const blastDurum = { sonBasis: null };
        addBlastRow(rows, 'blast_distances.lethal', blast.lethal, blastDurum);
        addBlastRow(rows, 'blast_distances.serious_injury',
                    blast.serious_injury, blastDurum);
        addBlastRow(rows, 'blast_distances.minor_injury', blast.minor_injury,
                    blastDurum);
        addBlastRow(rows, 'blast_distances.property_damage',
                    blast.property_damage, blastDurum);
        const frag = b.fragment_hazards || {};
        addRow(rows, 'fragment_hazards.estimated_case_mass_kg',
               frag.estimated_case_mass_kg, 3, 'kg');
        addRow(rows, 'fragment_hazards.case_mass_basis', frag.case_mass_basis);
        // 5. tur: Gurney parça hızı şarjı patlayıcı sayar; uç modellenmeyen
        // iticide üç alanı None + fragment_throw_status ile geri çeker.
        // Satır kaybolmaz: '—' + DEĞERLENDİRİLMEDİ çipi (gerekçe ipucunda).
        const atisYok = typeof frag.fragment_throw_status === 'string'
            && frag.fragment_throw_status.trim();
        const gurneyRow = function (path, v, d, unit) {
            if (atisYok) addWithheldRow(rows, path, frag.fragment_throw_reason);
            else addRow(rows, path, v, d, unit);
        };
        gurneyRow('fragment_hazards.fragment_velocity_ms',
                  frag.fragment_velocity_ms, 1, 'm/s');
        addRow(rows, 'fragment_hazards.lethal_velocity_threshold_ms',
               frag.lethal_velocity_threshold_ms, 1, 'm/s');
        gurneyRow('fragment_hazards.lethal_fragment_range_m',
                  frag.lethal_fragment_range_m, 0, 'm');
        gurneyRow('fragment_hazards.maximum_range_m',
                  frag.maximum_range_m, 0, 'm');
        // ÖH D23 / P5B2-21: alan adı ve birim düzeltildi (kg/m², parça
        // SAYISI değil). ÖH D23 / P5B2-24: uydurma boyut dağılımı geri
        // çekildi; yerine geri çekme gerekçesi basılır.
        addRow(rows, 'fragment_hazards.fragment_areal_mass_density_kg_m2',
               frag.fragment_areal_mass_density_kg_m2, 8, 'kg/m²');
        addRow(rows, 'fragment_hazards.fragment_areal_mass_density_basis',
               frag.fragment_areal_mass_density_basis);
        const sizes = frag.fragment_size_distribution || {};
        addListRow(rows, 'fragment_size_distribution.small_fragments_g',
                   sizes.small_fragments_g);
        addListRow(rows, 'fragment_size_distribution.medium_fragments_g',
                   sizes.medium_fragments_g);
        addListRow(rows, 'fragment_size_distribution.large_fragments_g',
                   sizes.large_fragments_g);
        addRow(rows, 'fragment_hazards.fragment_size_distribution_withheld',
               frag.fragment_size_distribution_withheld);
        const loose = frag.unrestrained_motor || {};
        // ÖH D36 / onemli2-sivi a2: impuls = itki x süre ve ondan türeyen
        // hız/enerji süre verilmediğinde uçta ADIYLA geri çekilir
        // (`not_evaluated` + `reason`); beyanlı boşluk '—' + çip basar.
        const looseGate = burnTimeGate(loose.not_evaluated, loose.reason);
        addGatedRow(rows, looseGate, 'unrestrained_motor.total_impulse_ns',
                    'total_impulse_ns', loose.total_impulse_ns, 1, 'N·s');
        addRow(rows, 'unrestrained_motor.mean_flight_mass_kg',
               loose.mean_flight_mass_kg, 3, 'kg');
        addGatedRow(rows, looseGate, 'unrestrained_motor.burnout_velocity_ms',
                    'burnout_velocity_ms', loose.burnout_velocity_ms, 1, 'm/s');
        addGatedRow(rows, looseGate, 'unrestrained_motor.kinetic_energy_j',
                    'kinetic_energy_j', loose.kinetic_energy_j, 0, 'J');
        addRow(rows, 'unrestrained_motor.required_restraint_force_n',
               loose.required_restraint_force_n, 0, 'N');
        addRow(rows, 'unrestrained_motor.note', loose.note);
        const qd = b.qd_requirements || {};
        addQdRow(rows, 'qd_requirements.inhabited_building',
                 qd.inhabited_building);
        addQdRow(rows, 'qd_requirements.public_traffic_route',
                 qd.public_traffic_route);
        addQdRow(rows, 'qd_requirements.personnel_facility',
                 qd.personnel_facility);
        addQdRow(rows, 'qd_requirements.ammunition_storage',
                 qd.ammunition_storage);
        addQdRow(rows, 'qd_requirements.explosives_facility',
                 qd.explosives_facility);
        addListRow(rows, 'storage_requirements', b.storage_requirements);
        addListRow(rows, 'transport_requirements', b.transport_requirements);
        return blockSection('explosive_hazards', rows);
    }

    function fireHazardsBlock(b) {
        if (!b) return '';
        const rows = [];
        addRow(rows, 'fire_classification', b.fire_classification);
        addRow(rows, 'fire_spread_potential', b.fire_spread_potential);
        const ignition = b.auto_ignition_risk || {};
        addRow(rows, 'auto_ignition_risk.risk_level', ignition.risk_level);
        addRow(rows, 'auto_ignition_risk.note', ignition.note);
        const distances = b.fire_safety_distances || {};
        addRow(rows, 'fire_safety_distances.personnel_distance_m',
               distances.personnel_distance_m, 1, 'm');
        addRow(rows, 'fire_safety_distances.equipment_distance_m',
               distances.equipment_distance_m, 1, 'm');
        addRow(rows, 'fire_safety_distances.public_distance_m',
               distances.public_distance_m, 1, 'm');
        addRow(rows, 'fire_safety_distances.radiant_heat_m',
               distances.radiant_heat_m, 1, 'm');
        addRow(rows, 'fire_safety_distances.source', distances.source);
        if (distances.disclaimer_code) {
            rows.push([machineLabel('fire_safety_distances.disclaimer_code'),
                       U.warnText(distances.disclaimer_code)]);
        }
        const suppression = b.suppression_system || {};
        addRow(rows, 'suppression_system.primary_agent',
               suppression.primary_agent);
        addListRow(rows, 'suppression_system.systems', suppression.systems);
        addListRow(rows, 'fire_fighting_procedures', b.fire_fighting_procedures);
        addListRow(rows, 'ignition_sources_control', b.ignition_sources_control);
        return blockSection('fire_hazards', rows);
    }

    function toxicHazardsBlock(b) {
        if (!b) return '';
        const rows = [];
        addRow(rows, 'toxic_hazard_level', b.toxic_hazard_level);
        addRow(rows, 'detection_required', b.detection_required);
        if (b.disclaimer_code) {
            rows.push([machineLabel('disclaimer_code'),
                       U.warnText(b.disclaimer_code)]);
        }
        addListRow(rows, 'toxic_components', b.toxic_components);
        addListRow(rows, 'ppe_requirements', b.ppe_requirements);
        const limits = b.exposure_limits || {};
        Object.keys(limits).forEach(function (name) {
            addRow(rows, 'exposure_limits.' + name, limits[name]);
        });
        const basis = b.guidance_basis || {};
        addRow(rows, 'guidance_basis.release_scenarios', basis.release_scenarios);
        addRow(rows, 'guidance_basis.ppe_requirements', basis.ppe_requirements);
        addRow(rows, 'guidance_basis.emergency_treatment',
               basis.emergency_treatment);
        addRow(rows, 'guidance_basis.verification_required',
               basis.verification_required);
        return blockSection('toxic_hazards', rows);
    }

    function operationalSafetyBlock(b) {
        if (!b) return '';
        const rows = [];
        const limits = b.personnel_limits || {};
        addRow(rows, 'personnel_limits.test_cell_during_operation',
               limits.test_cell_during_operation, 0);
        addRow(rows, 'personnel_limits.control_room', limits.control_room);
        addRow(rows, 'personnel_limits.observation_area',
               limits.observation_area);
        addRow(rows, 'personnel_limits.note', limits.note);
        addListRow(rows, 'pre_operation_checks', b.pre_operation_checks);
        addListRow(rows, 'operation_procedures', b.operation_procedures);
        addListRow(rows, 'post_operation_procedures',
                   b.post_operation_procedures);
        addListRow(rows, 'training_requirements', b.training_requirements);
        addListRow(rows, 'qualification_requirements',
                   b.qualification_requirements);
        return blockSection('operational_safety', rows);
    }

    function emergencyProceduresBlock(b) {
        if (!b) return '';
        const rows = [];
        const explosion = b.explosion_response || {};
        // 5. tur: patlayıcı modeli olmayan iticide tahliye kazanılmadı.
        if (typeof explosion.evacuation_distance_status === 'string'
                && explosion.evacuation_distance_status.trim()) {
            addWithheldRow(rows, 'explosion_response.evacuation_distance',
                           explosion.evacuation_distance_reason);
        } else {
            addRow(rows, 'explosion_response.evacuation_distance',
                   explosion.evacuation_distance, 1, 'm');
        }
        addListRow(rows, 'explosion_response.immediate_actions',
                   explosion.immediate_actions);
        addListRow(rows, 'explosion_response.re-entry_criteria',
                   explosion['re-entry_criteria']);
        const fire = b.fire_response || {};
        addRow(rows, 'fire_response.evacuation_distance',
               fire.evacuation_distance, 1, 'm');
        addRow(rows, 'fire_response.suppression_method',
               fire.suppression_method);
        addListRow(rows, 'fire_response.immediate_actions',
                   fire.immediate_actions);
        const toxic = b.toxic_release_response || {};
        addRow(rows, 'toxic_release_response.evacuation_distance',
               toxic.evacuation_distance, 1, 'm');
        addListRow(rows, 'toxic_release_response.immediate_actions',
                   toxic.immediate_actions);
        const decon = toxic.decontamination || {};
        Object.keys(decon).forEach(function (name) {
            addRow(rows, 'toxic_release_response.decontamination.' + name,
                   decon[name]);
        });
        const medical = b.medical_response || {};
        addRow(rows, 'medical_response.on_site_capabilities',
               medical.on_site_capabilities);
        addRow(rows, 'medical_response.hospital_notification',
               medical.hospital_notification);
        addRow(rows, 'medical_response.basis', medical.basis);
        if (medical.disclaimer_code) {
            rows.push([machineLabel('medical_response.disclaimer_code'),
                       U.warnText(medical.disclaimer_code)]);
        }
        addListRow(rows, 'medical_response.antidotes_required',
                   medical.antidotes_required);
        addListRow(rows, 'medical_response.treatment_protocols',
                   medical.treatment_protocols);
        return blockSection('emergency_procedures', rows);
    }

    function safetyEquipmentBlock(b) {
        if (!b) return '';
        const rows = [];
        addRow(rows, 'facility_type', b.facility_type);
        addListRow(rows, 'fixed_systems', b.fixed_systems);
        addListRow(rows, 'personal_equipment', b.personal_equipment);
        addListRow(rows, 'emergency_equipment', b.emergency_equipment);
        return blockSection('safety_equipment', rows);
    }

    // ==================================================================
    // B3 (OH-Z3-01) — TERMAL EKSENİN BEYANLARI EKRANDA
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ: uç ısı zinciri kurulamadığında termal ekseni `null` yapıp
    // bunu ÜÇ ayrı beyanla söylüyor (`risks_not_evaluated`,
    // `overall_risk_score_is_partial`, üst seviye `thermal_basis`); panel
    // hiçbirini okumuyordu: `individual_risks` tablosu `!= null` süzgeciyle
    // termal satırını, matris de `Number.isFinite` süzgeciyle çipini
    // sessizce düşürüyordu. Ekranda "termal risk yok" görünüyordu — oysa
    // "termal risk ÖLÇÜLMEDİ". Eksik değerlendirme düşük risk DEĞİLDİR.
    // ==================================================================
    function thermalBasisBlock(basis) {
        if (!basis || typeof basis !== 'object') return '';
        const rows = [];
        addRow(rows, 'verdict', basis.verdict);
        addRow(rows, 'wall_temperature_source', basis.wall_temperature_source);
        addRow(rows, 'message', basis.message);
        addListRow(rows, 'verdict_withheld_reasons',
                   basis.verdict_withheld_reasons);
        addListRow(rows, 'missing_thermal_inputs', basis.missing_thermal_inputs);
        const groups = basis.missing_thermal_input_groups;
        if (Array.isArray(groups) && groups.length) {
            rows.push([machineLabel('missing_thermal_input_groups'),
                '<ul style="margin:0 0 0 16px; padding:0;">'
                + groups.map(function (g) {
                    return '<li>' + esc(g.label || (g.any_of || []).join(' / '))
                        + '</li>';
                }).join('') + '</ul>']);
        }
        addListRow(rows, 'not_evaluated', basis.not_evaluated);
        if (!rows.length) return '';
        const path = 'thermal_basis';
        return U.sectionTitle(path) + U.kvTable(rows);
    }

    // ==================================================================
    // ÖH D36 / dil2-i18n-pdf a2 — PATLAYICI VE TOKSİK HÜKMÜN KÜNYESİ
    // (D35 pdf kulvarı devri 2; app.py `_lift_toxic_basis` belgesindeki
    // "AÇIK BORÇ": `thermalBasisBlock`un ikizi yoktu).
    //
    // ÖLÇÜLDÜ (raw/OH/D36/dil2-i18n-pdf/a2/once.json K4, taban bb7ee57c,
    // gerçek /analyze_safety yanıtı, kimliksiz 'apcp' itici): uç
    // `explosive_hazards.explosive_verdict_withheld_because`,
    // `explosive_hazards.requirements_scope` ve üst seviye `toxic_basis`
    // (9 alan, `toxic_hazard_level_withheld_because` dahil) yayımlıyordu;
    // panelde bu alanların HİÇBİRİ adıyla geçmiyordu (etiket sayısı 0).
    // Patlayıcı geri çekme cümlesi yalnız TESADÜFEN görünüyordu, çünkü
    // `explosive_class_basis` aynı dizeyi taşıyor.
    //
    // FAIL-CLOSED: alan yoksa (hüküm verilen koşum) patlayıcı bloğu HİÇ
    // çizilmez; toksik künye uç yayımladıkça çizilir (tıpkı termal künye
    // gibi). Gerekçe metni sunucunun cümlesidir ve `I18N.serverText`ten
    // geçer: TR karşılığı i18n_charts.js'te; karşılığı yoksa İngilizce
    // AYNEN kalır (uydurma çeviri yok).
    // ==================================================================
    function serverSentence(text) {
        const api = window.I18N;
        return (api && typeof api.serverText === 'function')
            ? api.serverText(String(text)) : String(text);
    }

    // Sunucu cümlesi taşıyan satır: makine etiketi + (çevrilmiş) cümle.
    function addReasonRow(rows, path, value) {
        if (typeof value !== 'string' || !value.trim()) return;
        rows.push([machineLabel(path),
            '<span data-safety-reason="' + esc(path) + '"'
            + ' style="font-size:0.72rem; line-height:1.4;">'
            + esc(serverSentence(value)) + '</span>']);
    }

    function basisSection(kind, title, note, rows) {
        if (!rows.length) return '';
        return '<div data-safety-basis="' + esc(kind) + '">'
            + U.sectionTitle(esc(title))
            + (note ? '<p style="font-size:0.74rem; margin:2px 0 6px;">'
                      + esc(note) + '</p>' : '')
            + U.kvTable(rows) + '</div>';
    }

    // 5. tur: uç 'modellenmedi' beyanını (explosive_not_modelled) koduyla
    // yayımlar; panel gri DEĞERLENDİRİLMEDİ rozeti + kendi gerekçesini
    // (EN = TR) basar. Tanınmayan kod genel metne düşer (sessiz boşluk yok).
    function notModelledRow(rows, beyan) {
        if (!beyan || typeof beyan !== 'object') return;
        const kod = typeof beyan.code === 'string' ? beyan.code : '';
        const metin = Object.prototype.hasOwnProperty.call(NOT_MODELLED_TEXT, kod)
            ? NOT_MODELLED_TEXT[kod] : NOT_MODELLED_TEXT.no_sourced_tnt;
        rows.push([machineLabel('explosive_not_modelled'),
            '<span data-safety-not-modelled="' + esc(kod) + '">'
            + U.badge(esc(T('panel.safety.explosiveNotEvaluated',
                            'EXPLOSIVE VERDICT: NOT EVALUATED')), 'dim')
            + ' <span style="font-size:0.72rem; line-height:1.4;">'
            + esc(T(metin[0], metin[1])) + '</span></span>']);
    }

    // V301/FİZİK-2 (kalem 8a): sıvı çift-iticide TNT eşdeğerinin dayanağı
    // (14 CFR 420 Ek E Tablo E-5 ya da kaynaksız HRMA seçimi), EN+TR.
    //: Tablo E-5 sütunları → sözlük anahtarı (harfî; anahtar taraması görür).
    const TNT_SCENARIO_TEXT = {
        static_test_stand: function () {
            return T('panel.safety.scenario.static_test_stand',
                     'static test stand');
        },
        launch_pad: function () {
            return T('panel.safety.scenario.launch_pad', 'launch pad');
        },
    };
    function tntBasisNote(b) {
        const d = b && b.tnt_equivalent_basis;
        if (!d || typeof d !== 'object') return '';
        const oran = U.fmt(100 * Number(d.effective_factor), 3);
        const tnt = U.fmt(Number(d.tnt_equivalent_kg), 4);
        const senaryo = Object.prototype.hasOwnProperty.call(
            TNT_SCENARIO_TEXT, d.scenario)
            ? TNT_SCENARIO_TEXT[d.scenario]() : String(d.scenario || '—');
        const metin = d.status === 'sourced'
            ? U.tf('panel.safety.tntSourced',
                   { factor: oran, tnt: tnt, scenario: senaryo },
                   'TNT equivalent {factor} % of the propellant mass ({tnt} '
                   + 'kg) — source: 14 CFR Part 420 Appendix E, Table E-5; '
                   + 'scenario: {scenario}')
            : U.tf('panel.safety.tntUnsourced', { factor: oran, tnt: tnt },
                   'TNT equivalent {factor} % of the propellant mass ({tnt} '
                   + 'kg) — unsourced HRMA choice: this propellant pair or '
                   + 'facility type is not in 14 CFR Part 420 Appendix E, '
                   + 'Table E-5');
        return '<p data-safety-tnt-basis="' + esc(String(d.status)) + '"'
            + ' style="font-size:0.72rem; margin:4px 0;">' + esc(metin)
            + '</p>';
    }

    function explosiveBasisBlock(b) {
        if (!b || typeof b !== 'object') return '';
        const not = tntBasisNote(b);
        const rows = [];
        notModelledRow(rows, b.explosive_not_modelled);
        addReasonRow(rows, 'explosive_verdict_withheld_because',
                     b.explosive_verdict_withheld_because);
        addReasonRow(rows, 'requirements_scope', b.requirements_scope);
        if (!rows.length) return not;
        // Beyanlı kolda (not_modelled) 'sınıf çözülemedi' notu basılmaz:
        // sınıf çözülemedi DEĞİL, modellenmediği beyan edildi (rozet yukarıda).
        const withheld = typeof b.explosive_verdict_withheld_because === 'string'
            && b.explosive_verdict_withheld_because.trim()
            && !b.explosive_not_modelled;
        return not + basisSection('explosive_verdict',
            T('panel.safety.secExplosiveBasis', 'Explosive verdict basis'),
            withheld ? T('panel.safety.explosiveWithheldNote',
                'No TNT-equivalent class was resolved, so no TNT equivalent, blast distance or quantity-distance is published. The reason below is the solver\'s own.')
                     : '',
            rows);
    }

    function listText(v) {
        return (Array.isArray(v) && v.length) ? v.map(String).join(', ') : null;
    }

    function toxicBasisBlock(basis) {
        if (!basis || typeof basis !== 'object') return '';
        const rows = [];
        addReasonRow(rows, 'toxic_hazard_level_withheld_because',
                     basis.toxic_hazard_level_withheld_because);
        addRow(rows, 'toxic_inventory_resolution',
               basis.toxic_inventory_resolution);
        addReasonRow(rows, 'toxic_inventory_basis', basis.toxic_inventory_basis);
        addRow(rows, 'propellant_class', basis.propellant_class);
        addRow(rows, 'propellant_class_source', basis.propellant_class_source);
        addRow(rows, 'resolvable_propellant_classes',
               listText(basis.resolvable_propellant_classes));
        addRow(rows, 'known_propellant_classes',
               listText(basis.known_propellant_classes));
        addReasonRow(rows, '_basis', basis._basis);
        return basisSection('toxic_basis',
            T('panel.safety.secToxicBasis', 'Toxic verdict basis'), '', rows);
    }

    // Risk sepetinin kendi kısmilik beyanları (matristen sessizce düşen
    // eksenin ekrandaki karşılığı).
    function partialRiskBlock(risk) {
        const rows = [];
        addListRow(rows, 'risks_not_evaluated', risk.risks_not_evaluated);
        addListRow(rows, 'mitigation_priority_not_evaluated',
                   risk.mitigation_priority_not_evaluated);
        addRow(rows, 'overall_risk_score_is_partial',
               risk.overall_risk_score_is_partial);
        addRow(rows, 'risk_level_is_partial', risk.risk_level_is_partial);
        addRow(rows, 'partial_assessment_basis', risk.partial_assessment_basis);
        addRow(rows, 'acceptability_withheld_because',
               risk.acceptability_withheld_because);
        addRow(rows, 'aggregation_basis', risk.aggregation_basis);
        if (!rows.length) return '';
        // V306/GÜVENLİK (NR-4): ham risk künyesi (makine alanları) kapalı
        // "Teknik ayrıntı" altında; kısmilik kullanıcıya üst şeritteki
        // cümleyle söylenir (NR-3).
        return '<details data-safety-basis="risk_assessment"'
            + ' style="font-size:0.75rem; margin:6px 0;"><summary'
            + ' style="cursor:pointer;">'
            + esc(T('panel.safety.riskBasisDetail',
                    'Risk assessment basis (technical detail, untranslated)'))
            + '</summary>' + U.kvTable(rows) + '</details>';
    }

    // ==================================================================
    // V306/GÜVENLİK (NR-3) — TEK HÜKÜM, AÇIK KISMİLİK, MOTORUN CİDAR SONUCU
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/guvenlik/olcum/guvenlik_once.json,
    // üç örnek motor, panelin kendi gövdesi + gerçek uç + panelin render'ı):
    // (b) yapısal (hibritte termal de) eksen değerlendirilmemişken üst
    //     şeritte yeşil "MOTOR TASARIM RİSKİ: LOW" ve yeşil "SKOR 2.00 / 5";
    //     kısmilik yalnız aşağıdaki İngilizce ham alanda;
    // (a) hibritte termal eksenin gerekçesi ısı modülünün ÇIPLAK CİDAR
    //     uyarısıydı ("3257 K, erime 1673 K aşılıyor") — motorun kendi
    //     sonucu (yakıt bloğu altı korunur, ön/son odaya astar) o kaydı
    //     `superseded_by = chamber_wall_zones` ile geçersiz kılmışken.
    // ==================================================================
    const NOT_EVALUATED_WORD = 'NOT_EVALUATED';
    const RISK_WORDS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
    // Kabul sözcükleri: safety_analysis._risk_band çıktıları (+ geri çekme).
    const ACCEPTABILITY_KEYS = {
        ACCEPTABLE: ['panel.safety.accWord.ACCEPTABLE', 'ACCEPTABLE'],
        ACCEPTABLE_WITH_CONTROLS: ['panel.safety.accWord.ACCEPTABLE_WITH_CONTROLS',
                                   'ACCEPTABLE WITH CONTROLS'],
        REQUIRES_MITIGATION: ['panel.safety.accWord.REQUIRES_MITIGATION',
                              'REQUIRES MITIGATION'],
        UNACCEPTABLE: ['panel.safety.accWord.UNACCEPTABLE', 'UNACCEPTABLE'],
    };

    // Hüküm sözcüğü kullanıcı dilinde; tanınmayan sözcük AYNEN kalır.
    function riskWord(level) {
        const t = String(level == null ? '' : level).toUpperCase();
        if (t === NOT_EVALUATED_WORD) {
            return T('app.state.notEvaluated', 'NOT EVALUATED');
        }
        if (RISK_WORDS.indexOf(t) !== -1) return T('panel.safety.accBand.' + t, t);
        return String(level);
    }

    function acceptabilityWord(acc) {
        const t = String(acc == null ? '' : acc);
        if (t === NOT_EVALUATED_WORD) {
            return T('panel.safety.accWord.NOT_EVALUATED',
                     'ACCEPTABILITY: NOT EVALUATED');
        }
        const k = ACCEPTABILITY_KEYS[t];
        return k ? T(k[0], k[1]) : t.replace(/_/g, ' ');
    }

    // Geri çekilmiş hüküm kırmızı DEĞİL, kehribardır (Performans Özeti
    // "HÜKÜM GERİ ÇEKİLDİ" rozetiyle aynı ton).
    function verdictKind(level) {
        return String(level || '').toUpperCase() === NOT_EVALUATED_WORD
            ? 'warn' : riskLevelKind(level);
    }

    // Motor eksenlerinden en az biri değerlendirilmediyse
    // {evaluated, missing, total}; değilse (ya da eski yanıt) null.
    function motorAxesPartial(risk) {
        const ev = risk && risk.motor_axes_evaluated;
        const yok = risk && risk.motor_axes_not_evaluated;
        if (!Array.isArray(ev) || !Array.isArray(yok) || !yok.length) return null;
        return { evaluated: ev.map(String), missing: yok.map(String),
                 total: ev.length + yok.length };
    }

    function motorPartialNote(kismi, risk) {
        if (!kismi) return '';
        const LBL = areaLabels();
        const adlar = function (liste) {
            return liste.map(function (a) { return LBL[a] || a; }).join(', ');
        };
        const skor = (typeof risk.overall_risk_score === 'number'
                      && Number.isFinite(risk.overall_risk_score))
            ? risk.overall_risk_score : null;
        const metin = (kismi.evaluated.length && skor !== null)
            ? U.tf('panel.safety.partialMotorNote', {
                done: kismi.evaluated.length, total: kismi.total,
                evaluated: adlar(kismi.evaluated),
                missing: adlar(kismi.missing), score: U.num(skor, 2) },
                'Partial assessment: {done} of {total} motor-design axes '
                + 'were evaluated ({evaluated}); not evaluated: {missing}. '
                + 'The worst evaluated axis scores {score} / 5, which is only '
                + 'a lower bound, so no low-risk verdict is given. A missing '
                + 'evaluation is not a low risk.')
            : U.tf('panel.safety.partialMotorNoteNone', {
                total: kismi.total, missing: adlar(kismi.missing) },
                'None of the {total} motor-design axes could be evaluated '
                + '({missing}), so no motor design risk is given.');
        return '<p data-safety-partial="1" style="font-size:0.75rem;'
            + ' color:' + U.kindColor('warn') + '; margin:2px 0 8px;">'
            + esc(metin) + '</p>';
    }

    // NR-3 (a): hibritte cidarın ısıl sonucu motorun BÖLGE modelidir
    // (Performans Özeti "YANMA ODASI CİDARI: ÜÇ BÖLGE" kartıyla aynı kayıt;
    // uç onu `thermal_safety.motor_wall_zones` ile geri yansıtır). Ad ve
    // hüküm sözcükleri o kartın sözlük anahtarlarıdır (aynı dil); sayılar
    // kaydın kendi alanlarıdır, burada eşik hesaplanmaz.
    const ZONE_NAME_KEYS = {
        grain_section: ['app.zones.grain', 'Under the fuel grain'],
        pre_chamber: ['app.zones.pre', 'Pre-combustion chamber'],
        post_chamber: ['app.zones.post', 'Post-combustion chamber'],
    };
    const ZONE_VERDICT_KEYS = {
        PROTECTED_DURING_BURN: ['app.zones.vProtected', 'PROTECTED DURING BURN'],
        NOT_PROTECTED: ['app.zones.vNotProtected', 'NOT PROTECTED'],
        LINER_REQUIRED: ['app.zones.vLinerRequired', 'LINER REQUIRED'],
        BARE_WALL_CRITICAL: ['app.zones.vBareCritical', 'BARE WALL: CRITICAL'],
        BARE_WALL_WITHIN_LIMIT: ['app.zones.vBareOk', 'BARE WALL WITHIN LIMIT'],
        NOT_PRESENT: ['app.zones.vAbsent', 'NOT PRESENT'],
    };

    function motorZoneThermalNote(th) {
        const bolge = th && th.motor_wall_zones;
        if (!bolge || !Array.isArray(bolge.zones) || !bolge.zones.length) {
            return '';
        }
        const satirlar = bolge.zones.map(function (z) {
            const ad = ZONE_NAME_KEYS[z.zone];
            const hk = ZONE_VERDICT_KEYS[z.verdict];
            const ayrinti = [];
            if (z.verdict === 'PROTECTED_DURING_BURN'
                    && isNum(z.casing_temperature_K)) {
                ayrinti.push(U.tf('app.zones.grainDetail',
                    { T: U.num(z.casing_temperature_K, 2) },
                    'the fuel grain covers the case for the whole burn; case '
                    + 'temperature {T} K (declared, not computed)'));
            }
            if (z.verdict === 'LINER_REQUIRED' && isNum(z.liner_thickness_mm)) {
                ayrinti.push(U.tf('app.zones.linerDetail',
                    { mm: U.num(z.liner_thickness_mm, 2) },
                    'this zone needs a {mm} mm insulation liner (HRMA sized it)'));
            }
            if (z.verdict === 'BARE_WALL_CRITICAL') {
                ayrinti.push(T('app.zones.noLiner',
                    'no liner sizing in this run: the critical bare-wall '
                    + 'verdict stands'));
            }
            return '<li data-safety-zone="' + esc(String(z.zone)) + '">'
                + '<strong>' + esc(ad ? T(ad[0], ad[1]) : String(z.zone))
                + '</strong>: ' + esc(hk ? T(hk[0], hk[1]) : String(z.verdict))
                + (ayrinti.length ? ' — ' + esc(ayrinti.join(' · ')) : '')
                + '</li>';
        }).join('');
        const sonuc = bolge.all_zones_protected
            ? T('panel.safety.zoneThermalDeclared',
                'The case temperature in this model is declared, not '
                + 'computed, so no thermal risk score is given and the '
                + 'thermal axis is shown as not evaluated. The heat '
                + 'module\'s bare-wall equilibrium (a wall with no fuel '
                + 'grain and no liner) is not this motor\'s wall and is not '
                + 'used for this verdict.')
            : T('panel.safety.zoneThermalNotAll',
                'Not every zone is protected in the motor\'s own model (see '
                + 'the zone verdicts). No thermal risk score is computed '
                + 'from a separate model.');
        return '<div data-safety-zone-thermal="1" style="font-size:0.75rem;'
            + ' margin:6px 0; padding:6px 8px; border:1px solid '
            + U.kindColor('dim') + '; border-radius:6px;">'
            + '<strong>' + esc(T('panel.safety.zoneThermalTitle',
                'Thermal axis: the motor\'s own chamber-wall result (the '
                + 'same record as the Performance Summary card)'))
            + '</strong><ul style="margin:4px 0 4px 16px; padding:0;">'
            + satirlar + '</ul>' + esc(sonuc) + '</div>';
    }

    function render(data, root) {
        const s = data.safety_analysis || {};
        const risk = s.risk_assessment || {};
        const risks = risk.individual_risks || {};
        const notEvaluatedAxes = Array.isArray(risk.risks_not_evaluated)
            ? risk.risks_not_evaluated : [];

        // ---- Üst rozetler ----
        // KISMİLİK: uç `risk_level_is_partial` / `overall_risk_score_is_partial`
        // yayımladığında rozetin yanına eksenin ADI ile bir NOT MODELLED çipi
        // konur. Rozetin rengi değiştirilmez (uydurma sınıf üretmemek için),
        // ama "bu hüküm eksik eksenlerle kuruldu" beyanı görünür olur.
        const partialChip = (notEvaluatedAxes.length
                             || risk.overall_risk_score_is_partial
                             || risk.risk_level_is_partial)
            // ÖH D26 / P11B2-10 — hüküm sınıflandırıcıdan (değer yok).
            ? U.source.chip(U.source.of({ basis: (risk.partial_assessment_basis
                                      || risk.acceptability_withheld_because
                                      || null) }, null, { value: null }),
                            'risks_not_evaluated: '
                            + (notEvaluatedAxes.join(', ') || '-'))
            : '';
        let badges = '';
        // V306/GÜVENLİK (NR-3 b): motor eksenlerinin kısmiliği (uç
        // `motor_axes_evaluated` / `motor_axes_not_evaluated` yayımlar).
        const kismi = motorAxesPartial(risk);
        if (risk.risk_level) {
            // V301/FİZİK-2 (kalem 8b): risk_level motorun KENDİ eksenlerinden
            // (yapısal, basınçlı kap, termal); tesis ekseni ayrı rozette.
            // V306/GÜVENLİK (NR-3 b): değerlendirilmeyen motor ekseni varken
            // uç LOW / MEDIUM sınıfını geri çeker (NOT_EVALUATED); rozet o
            // sözcüğü kullanıcı dilinde basar ve kaç eksenin
            // değerlendirildiğini rozetin İÇİNDE söyler. Yeşil yalnız
            // bütün motor eksenleri değerlendirilip LOW çıktığında yanar.
            const etiket = risk.facility_hazard
                ? T('panel.safety.motorDesignRisk', 'MOTOR DESIGN RISK')
                : T('panel.safety.overallRisk', 'OVERALL RISK');
            badges += '<span data-safety-motor-risk="'
                + esc(String(risk.risk_level)) + '">'
                + U.badge(etiket + ': ' + riskWord(risk.risk_level)
                    + (kismi ? ' · ' + U.tf('panel.safety.axesEvaluated',
                        { done: kismi.evaluated.length, total: kismi.total },
                        '{done} OF {total} AXES EVALUATED') : ''),
                    kismi ? 'warn' : verdictKind(risk.risk_level),
                    U.tf('panel.safety.overallScoreTip',
                         { value: U.num(risk.overall_risk_score, 2) },
                         'Worst evaluated axis score {value} / 5'))
                + '</span>'
                + (risk.risk_level_is_partial ? partialChip : '');
        }
        if (risk.acceptability) {
            const acc = String(risk.acceptability);
            // Geri çekilmiş kabul sözcüğü, aynı nedenle geri çekilmiş risk
            // rozetini ikinci kez söylemez (tek hüküm, tek rozet).
            if (!(acc === NOT_EVALUATED_WORD
                  && String(risk.risk_level) === NOT_EVALUATED_WORD)) {
                badges += U.badge(acceptabilityWord(acc),
                    acc === 'ACCEPTABLE' ? 'ok'
                        : acc === 'ACCEPTABLE_WITH_CONTROLS' ? 'warn'
                            : acc === NOT_EVALUATED_WORD ? 'warn' : 'err');
            }
        }
        if (risk.overall_risk_score != null) {
            // Kısmi sepette skor yalnız değerlendirilen eksenlerin en
            // kötüsüdür (alt sınır): etiket bunu söyler, renk nötrdür.
            badges += U.badge((kismi
                    ? T('panel.safety.scoreBadgePartial',
                        'SCORE OF EVALUATED AXES')
                    : T('panel.safety.scoreBadge', 'SCORE')) + ': '
                + U.num(risk.overall_risk_score, 2) + ' / 5',
                kismi ? 'dim' : bandKind(scoreBand(risk.overall_risk_score)))
                + (risk.overall_risk_score_is_partial ? partialChip : '');
        }
        // V301/FİZİK-2 (kalem 8b): tesis / yerleşim tehlikesi motor
        // hükmünden AYRI rozet; en yüksek sınıfta "güvenlik mesafesi / tesis
        // önlemi gerekli" (uyarı) — motora "yeniden tasarla" denmez.
        const fh = risk.facility_hazard;
        if (fh && fh.risk_level) {
            badges += U.badge(T('panel.safety.facilityHazard',
                'FACILITY / SITING HAZARD') + ': ' + riskWord(fh.risk_level),
                verdictKind(fh.risk_level),
                U.tf('panel.safety.overallScoreTip',
                     { value: U.num(fh.score, 2) },
                     'Worst evaluated axis score {value} / 5'));
            if (fh.requirement) {
                badges += U.badge(T('panel.safety.facilityRequirement',
                    'SAFETY DISTANCE / FACILITY MEASURES REQUIRED — a '
                    + 'facility requirement of the propellant inventory, not '
                    + 'a motor design defect'), 'warn');
            }
        }
        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;
        // V306/GÜVENLİK (NR-3 b): kısmilik cümlesi rozetin HEMEN altında,
        // kullanıcı dilinde (ham `risk_level_is_partial` alanı aşağıda
        // künye olarak kalır).
        html += motorPartialNote(kismi, risk);
        // V301/CI-ÜRÜN (28 Eki): tesis rozetinin DAYANAĞI ekranda. Uç
        // ``risk_assessment.facility_hazard.basis`` cümlesini yayımlıyor
        // ama panel yalnız rozeti basıyordu (CI d15 süpürmesi: 1/309 sağır
        // yaprak). EN'de sunucu cümlesi AYNEN; TR'de Türkçe özet + kapalı
        // "Teknik ayrıntı (çözücü beyanı, çevrilmedi)" altında aynı cümle
        // (akış paneli / DİL-2 deseni). Sayı yok, yalnız beyan.
        html += facilityHazardBasisHtml(fh);

        // ---- Varsayılan künyesi (uç beyanı) ----
        // Hükmün HEMEN ardında: aşağıdaki her sayı bu girdilere dayanıyor,
        // hangisinin kullanıcıdan gelmediği okunmadan hüküm okunmamalı.
        html += defaultsBlock(data.defaults_applied, data);

        // ---- Bireysel riskler ----
        const LBL = areaLabels();
        html += U.sectionTitle(T('panel.safety.secIndividual',
            'Individual Risks (1 = lowest, 5 = highest)'));
        // DEĞERLENDİRİLMEYEN EKSEN SESSİZCE DÜŞMEZ (OH-Z3-01): uç ekseni
        // `null` bırakıp adını `risks_not_evaluated` içinde BEYAN ettiyse
        // satır '—' + NOT MODELLED çipiyle KONUR. Eski süzgeç (`!= null`)
        // ekseni tablodan silerdi ve ekran "termal risk yok" derdi.
        html += U.kvTable(Object.keys(AREA_LABELS)
            .filter(function (a) {
                return risks[a] != null || notEvaluatedAxes.indexOf(a) !== -1;
            })
            .map(function (a) {
                if (risks[a] != null) return [LBL[a], scoreCell(risks[a])];
                return [LBL[a],
                    '<span data-risk-not-evaluated="' + esc(a) + '">—</span>'
                    // ÖH D26 / P11B2-10 — hüküm sınıflandırıcıdan.
                    + U.source.chip(U.source.of(
                        { basis: (risk.partial_assessment_basis
                                  || risk.acceptability_withheld_because
                                  || null) }, null, { value: null }))];
            }));
        // V3 KK 3. tur: termal eksen değerlendirilmediyse nedeni tablonun
        // hemen altında da ADIYLA (yalnız 'girdi yok' çipi yetmez).
        // V306/GÜVENLİK (NR-3 a): motor kendi cidar bölge sonucunu
        // yayımladıysa termal eksenin gerekçesi O sonuçtur (tek kaynak);
        // ısı modülünün çıplak cidar uyarısı ancak motorun bölge modeli
        // yokken basılır.
        html += motorZoneThermalNote(s.thermal_safety)
            || wallWithheldNote(notEvaluatedAxes.indexOf('thermal') !== -1);

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

        // ---- Risk sepetinin kısmilik beyanları (B3) ----
        html += partialRiskBlock(risk);

        // ---- Termal hükmün künyesi (uçun üst seviye beyanı, B3) ----
        html += thermalBasisBlock(data.thermal_basis);

        // ---- Patlayıcı ve toksik hükmün künyesi (ÖH D36 dil2 a2) ----
        html += explosiveBasisBlock(s.explosive_hazards);
        html += toxicBasisBlock(data.toxic_basis);

        // ---- Ucun yayımladığı ve eskiden HİÇ inmeyen dokuz blok ----
        html += inputsUsedBlock(s.inputs_used,
                                s.burn_time_dependent_not_evaluated);
        html += structuralSafetyBlock(s.structural_safety);
        html += thermalSafetyBlock(s.thermal_safety);
        html += explosiveHazardsBlock(s.explosive_hazards);
        html += fireHazardsBlock(s.fire_hazards);
        html += toxicHazardsBlock(s.toxic_hazards);
        html += operationalSafetyBlock(s.operational_safety);
        html += emergencyProceduresBlock(s.emergency_procedures);
        html += safetyEquipmentBlock(s.safety_equipment);

        root.innerHTML = html;

        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, s, { deep: true });
    }

    window.AnalysisDock.register({
        id: 'safety',
        title: 'Comprehensive Safety — Risk Assessment & Pressure Vessel',
        titleKey: 'panel.safety.title',
        category: 'SAFETY',
        endpoint: '/analyze_safety',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: FIELDS,
        fromResults: function (r) {
            const m = U.motorDict(r);
            const motorType = window.AnalysisDock.getMotorType();
            const yapisal = structuralSeeds(r);
            const sug = {
                motor_type: motorType,
                chamber_pressure: yapisal.chamber_pressure,
                chamber_temperature: m.chamber_temperature,
                // İTKİ: katı motor düz sözlükte 'thrust' ÜRETMİYOR (ortalama
                // ve tepe itkiyi ayrı raporluyor) — alan 1000 N varsayılanında
                // kalıyordu, gerçek ortalama 1670,6 N. Tohum tek yardımcıdan
                // (seededThrust): impuls bağlamı aynı sayıyı taşır.
                thrust: seededThrust(r, motorType),
                burn_time: U.readBurnTime(r),
                // BİRİM: ham okunuyordu ve alan METRE etiketli; katı motorda
                // 75,0 (mm) ve sıvıda 120,0 (mm) geliyor -> panel 75 m / 120 m
                // çaplı bir kap için güvenlik hükmü üretiyordu.
                chamber_diameter: yapisal.chamber_diameter,
                // Motorun KENDİ iticisinden (5. tur; propellantClassFromMotor).
                // Eski satır katı/hibritte daima 'composite' yazıyordu.
                propellant_type: propellantClassFromMotor(r, motorType),
                // İTERGAÇ KÜTLESİ: eskiden yalnız 'mdot_total' x burn_time ile
                // türetiliyordu; o anahtar SADECE hibritte var, katı ve sıvıda
                // alan 5 kg varsayılanında kalıyordu (gerçek: katı 2,41 kg,
                // sıvı 2756,5 kg). Artık her motor tipinin kendi kütle anahtarı
                // okunuyor; TNT eşdeğeri ve tahliye mesafeleri buna bağlı.
                // ÖH D36 / onemli2-sivi a2: çözücü kütle yayımlamadıysa
                // (süresiz sıvı) öneri undefined kalır ve alan BOŞ kalır;
                // 5 kg nöbetçisi kalktı (FIELDS notu).
                propellant_mass: U.readPropellantMass(r),
                // CİDAR ve MALZEME hiç bağlı değildi: uç bunlar için
                // varsayılana düşüyor ve bunu `defaults_applied` ile
                // bildiriyordu (panel o alanı da okumuyor).
                wall_thickness: yapisal.wall_thickness,
                material: U.readChamberMaterial(r),
                // V301/H-PANEL (NK-17): ısı zinciri geometrisi motorun
                // HESAPLADIĞI değerlerden tohumlanır. ÖLÇÜLDÜ (son kullanıcı
                // testi, örnek hibrit): iki alan boş ve "MODELLENMEDİ"
                // kalıyordu, uç kabuk kütlesini ve ışınım alanını VARSAYILAN
                // L/D = 5 ile kuruyordu (gerçek kamara L/D = 12,2); aynı
                // güvertenin TERMAL sekmesi oda boyunu 0,983 m tohumluyordu.
                // Okuyucu güvertenin ortak birim tablosundan (LENGTH_UNITS:
                // hibrit m, sıvı mm, katıda chamber_length yayımlanmaz →
                // alan boş kalır, uç adıyla geri çeker).
                chamber_length: U.readLengthM(r, 'chamber_length'),
                throat_diameter: U.readLengthM(r, 'throat_diameter'),
            };
            // ISI ZİNCİRİ (OH-Z3-01) — güvertenin MEVCUT okuyucusu.
            // `readWallTemperaturesK` çözücünün kaynak beyanını denetler ve
            // yalnız ÇÖZÜLMÜŞ bir çift döner; beyan 'assumed …' diyorsa ya
            // da ikisinden biri eksikse BOŞ sözlük döner. O durumda alanlar
            // doldurulmaz (applySuggestions yalnız sonlu sayıyı yazar),
            // istekte gitmez ve uç termal hükmü geri çeker — panel de bu
            // geri çekmeyi ekrana basar. Sıcaklık HİÇBİR dalda uydurulmaz.
            // ÖH D37 A1b panel-js 6. tur (devir 13) — FİZİKSEL OLMAYAN CİDAR
            // GÖNDERİLMEZ. ÖLÇÜLDÜ (a1/t6/cidar_kaynagi.json, örnek hibrit):
            // çifti (3312,5 / 3289,4 K) yapısal blok 'heat_transfer_module'
            // kaynağıyla aktarıyor; sayı ısı modülünün soğutmasız
            // ('natural') DENGE cidarıdır (wall_analysis.inner_temperature
            // = gas_side_analysis.estimated_wall_temperature; T_aw 3321,3 K,
            // gaz 3333,0 K) ve AYNI modül onu
            // gas_side_analysis.wall_temperature_unphysical = true diye
            // imliyor (erime 1673 K üstü). Panel bu bayrağı okumuyordu; gaz
            // geri kazanım sıcaklığına eşit bir sayı cidar diye gidiyor,
            // termal 5,0 ve yapısal 5,0 (birleşik SF 0,71) basılıyordu.
            // Motor fiziksel bir cidar sıcaklığı YAYIMLAMIYOR (çıplak cidar
            // geçmişi model_valid = false; astar yalnız yüzey sıcaklığı
            // veriyor) — çift gönderilmez, uç termal hükmü ve birleşik
            // (basınç + termal) katsayıyı adıyla geri çeker. Sayı uydurulmaz.
            const unphysical = (function () {
                let o = U.motorDict(r);
                for (const k of WALL_UNPHYSICAL_PATH) {
                    if (!o || typeof o !== 'object') return false;
                    o = o[k];
                }
                return o === true;
            })();
            const wall = unphysical ? {} : (U.readWallTemperaturesK(r) || {});
            // V3 KK 3. tur: geri tutmanın nedeni ekran için saklanır.
            wallPairWithheld = unphysical ? {
                warnings: (function () {
                    const g = ((U.motorDict(r) || {}).heat_transfer_analysis
                               || {}).gas_side_analysis || {};
                    return (Array.isArray(g.warnings) ? g.warnings : [])
                        .filter(function (w) {
                            return w && typeof w === 'object'
                                && WALL_UNPHYSICAL_CODES.indexOf(w.code) !== -1;
                        });
                })(),
            } : null;
            if (Number.isFinite(wall.hot) && Number.isFinite(wall.cold)) {
                sug.wall_temperature_hot = wall.hot;
                sug.wall_temperature_cold = wall.cold;
            } else if (motorType === 'solid') {
                // V301/PANEL (ÖRNEK-PANEL DEVİR 1): katıda cidar = kasa;
                // motor onu yalıtım + astar arkasında yığın ÇÖZER (iç = dış).
                // ÖLÇÜLDÜ (ornek-panel/olcum/devir_guvenlik_kati.txt): çift
                // gitmeyince uç 1683,7 K çıplak cidara düşüyor, risk
                // CRITICAL + do_not_proceed; motorun 313,553 K'iyle MEDIUM.
                // Okuyucu güvertede tek: ısıl panel aynı yolu ve kapıyı
                // kullanıyor, iki panel aynı çifti gönderir.
                const tKasa = U.readSolvedCaseTemperatureK(r);
                if (Number.isFinite(tKasa)) {
                    sug.wall_temperature_hot = tKasa;
                    sug.wall_temperature_cold = tKasa;
                }
            }
            return sug;
        },
        // V301/PANEL (NK-18): form alanı OLMAYAN bağlam (güverte
        // runPanel bunu gövdeye ekler; ekranda girdi değildir). Motor
        // sonucu varken uç (1) yapısal hükmü motorun zincirinden okur,
        // (2) çıplak cidar ısı tahminini KOŞMAZ: cidar sıcaklığı yalnız
        // motorun çözülmüş çifti (yukarıda) olabilir.
        contextFromResults: function (r) {
            const motorType = window.AnalysisDock.getMotorType();
            const ctx = {};
            const blok = motorVerdictResult(r, motorType);
            if (blok) {
                const girdiler = {};
                const tohum = structuralSeeds(r);
                Object.keys(tohum).forEach(function (k) {
                    if (typeof tohum[k] === 'number' && Number.isFinite(tohum[k])) {
                        girdiler[k] = tohum[k];
                    }
                });
                ctx.motor_result = blok;
                ctx.motor_verdict_inputs = girdiler;
            }
            // V301/FİZİK-2 (KABUL 12): serbest kalan motorun impulsu motorun
            // YAYIMLADIĞI toplam impulstur (PDF tablosu ve PDF güvenlik
            // bölümüyle aynı sayı). ÖLÇÜLDÜ (fizik-2/k2_k3_pdf_guvenlik_
            // once.json, örnek KNDX): sekme tepe itki × süre = 3411,5 N·s,
            // motor 2956,9 N·s basıyordu. Kayıt, formu tohumlayan itki ve
            // süreyle gider; kullanıcı ikisinden birini değiştirirse uç kaydı
            // benimsemez ve itki × süreyi adıyla basar.
            const m = U.motorDict(r) || {};
            const ti = m.total_impulse;
            const itki = seededThrust(r, motorType);
            const sure = U.readBurnTime(r);
            if (typeof ti === 'number' && Number.isFinite(ti) && ti > 0
                    && Number.isFinite(itki) && Number.isFinite(sure)) {
                ctx.motor_total_impulse = {
                    total_impulse_ns: ti,
                    source: 'motor result total_impulse',
                    inputs: { thrust: itki, burn_time: sure },
                };
            }
            // V301/FİZİK-2 (kalem 8a): sıvı çift-iticide TNT eşdeğeri itici
            // ÇİFTİNE göre kaynaktan (14 CFR 420 Ek E Tablo E-5); çiftin
            // adları motor sonucundan (form alanı değil, bağlam).
            if (motorType === 'liquid') {
                ['oxidizer_type', 'fuel_type'].forEach(function (k) {
                    if (typeof m[k] === 'string' && m[k].trim()) {
                        ctx[k] = m[k].trim();
                    }
                });
            }
            return Object.keys(ctx).length ? ctx : null;
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
    window.SafetyPanel = {
        _render: render,
        // Bekçi yüzeyi: künye bloğu DOM'suz da ölçülebilsin (etiketler
        // koşum kartının alan listesinden gelir — kopya liste yok).
        _defaultsBlock: defaultsBlock,
        _explosiveBasisBlock: explosiveBasisBlock,
        _toxicBasisBlock: toxicBasisBlock,
        _fieldLabel: fieldLabel,
        _fields: FIELDS,
        _propellantClassFromMotor: propellantClassFromMotor,
        _thermalSafetyBlock: thermalSafetyBlock,
        _motorVerdictBlocks: MOTOR_VERDICT_BLOCKS,
        _motorVerdictResult: motorVerdictResult,
    };
})();
