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

    //: Sunucudan gelen SERBEST METİN (gerekçe/beyan cümlesi): i18n_charts.js
    //: sözlük + desen sırasıyla çevirir, eşleşme yoksa metni AYNEN döndürür
    //: (asla anahtar, asla boş). cfd_panel / stability_panel / fea_panel ile
    //: birebir aynı yardımcı.
    //:
    //: OH-Z4-04 (2026-08-28): panel bu cümleleri HAM basıyordu. Z5 i18n
    //: süpürmesi `minimum_safety_factor_verdict_basis`in DÖRT dalını
    //: MSG_PATTERNS'e yazmıştı ama panelde kapı olmadığı için o kurallar
    //: ekrana hiç ulaşmıyordu — "kanal var, kapı yok" deseni. Kapı bu.
    //: Sunucunun kelimeleri DEĞİŞTİRİLMEZ; yalnız Türkçe kipte Türkçe
    //: karşılığı varsa o basılır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    //: V3 KK 3. tur (§28-50 (c)) — cidar satırlarında ondalık ayracı dile
    //: bağlı. ÖLÇÜLDÜ (docs/user_guide/img/v3_0/kanit/kayit_tr.json, TR kip,
    //: örnek katı): 'submitted_wall_thickness_mm 4.000'. `U.fmt` her zaman
    //: nokta basar; biçim güvertenin TEK kaynağından (`U.num` →
    //: I18N.number) gelir, basamak sayısı DEĞİŞMEZ. Sayı yoksa '—' (U.fmt
    //: ile aynı boşluk imi).
    function numL(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—'
            : U.num(x, d == null ? 2 : d);
    }

    /* Ucun HÜKÜM GERİ ÇEKİLDİ imi (structural_analysis.py
       ``STRUCTURAL_VERDICT_NOT_EVALUATED``). Tel sözleşmesidir; panelde
       TEK yerde yazılır (doktrin 4) ve hem durum hem risk kapısı buradan
       okur — P11B4-07'nin kusuru tam olarak bu iki kapının AYRI
       davranmasıydı. */
    const HUKUM_YOK = 'NOT_EVALUATED';

    function statusKind(s) {
        // structural_analysis.py sözlüğü: SAFE/ACCEPTABLE → ok,
        // MARGINAL → warn, UNSAFE/CRITICAL → err
        const t = String(s || '').toUpperCase();
        if (t === 'SAFE' || t === 'ACCEPTABLE') return 'ok';
        if (t === 'MARGINAL') return 'warn';
        if (t === 'UNSAFE' || t === 'CRITICAL') return 'err';
        // NOT_EVALUATED dahil: hüküm KAZANILMADI → nötr.
        return 'info';
    }

    /* ÖH D26 · P11B4-07 — AYNI OLGU İKİ RENKTE BASILAMAZ.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531): risk rozetinin rengi
       `rk.indexOf('LOW') !== -1 ? 'ok' : rk === 'MEDIUM' ? 'warn' : 'err'`
       üçlüsünden geliyordu (risk_rengi_ternary = 1) ve panelde
       `NOT_EVALUATED` adı HİÇ geçmiyordu (statuskind_not_evaluated = 0).
       Uç aynı koşumda `status` ve `risk_level` alanlarının İKİSİNİ de
       `NOT_EVALUATED` yapıyor (structural_analysis.py: `status =
       risk_level = STRUCTURAL_VERDICT_NOT_EVALUATED`), yani ekranda
       AYNI olgu için `STRUCTURE: NOT_EVALUATED` CYAN, `RISK:
       NOT_EVALUATED` KIRMIZI basılıyordu.

       Kırmızı bir HÜKÜMDÜR ("en yüksek risk"), oysa hüküm geri
       çekilmiştir: fail-closed karşılığı kırmızı değil NÖTR'dür
       (P11B4-04'ün totolojik hücre kararıyla aynı doktrin). Ölçüt
       gevşetilmiyor — gerçek HIGH/CRITICAL risk kırmızı kalır. */
    function riskKind(rk) {
        const t = String(rk || '').toUpperCase();
        if (t === HUKUM_YOK) return 'info';
        if (t.indexOf('LOW') !== -1) return 'ok';
        if (t === 'MEDIUM') return 'warn';
        return 'err';
    }

    // SF renk eşiği: <1 kırmızı (akma aşıldı), < gerekli-SF turuncu,
    // aksi yeşil. Gerekli SF backend malzeme kartından okunur.
    //
    // P11B4-04 — TOTOLOJİK SAYI YEŞİL BASILAMAZ
    // ------------------------------------------------------------------
    // Ölçülen (docs/scofield/raw/OH/D15/ui-paneller/a2/b4_ONCE.json):
    // uç `safety_factor_is_tautological` haritasında BEŞ modun BEŞİNİ de
    // `true` ilan ediyor ve gerekçesini yazıyor: "no wall thickness was
    // supplied by the user, so HRMA sized the wall to the allowable
    // stress: SF = target_SF x manufacturing allowance (input read back,
    // NOT an independent verification)". Yani sayı, kullanıcının kendi
    // hedefinin geri okumasıdır — bir ÖLÇÜM değildir.
    // Buna rağmen ekranda `Chamber hoop 4.80` ve `Chamber von Mises 5.54`
    // YEŞİL, `SF (pressure only)` ve `SF (total)` YEŞİL basılıyordu
    // (totolojik ama yeşil = 2 mod + 2 manşet satırı). Z4-B turunda
    // yalnız `safety_factor_is_tautological` İMİ eklenmiş, RENKLERE
    // dokunulmamıştı — im yeşilin yanında duruyordu.
    //
    // Yeşil "sınandı ve geçti" demektir; totolojik sayı sınanmamıştır.
    // Fail-closed karşılığı KIRMIZI değil NÖTR'dür: hüküm YOK. Bu yüzden
    // totolojik hücre `dim` (sönük) basılır — kazanılmamış bir hükmü
    // yeşile de kırmızıya da boyamak yanlış olurdu.
    /* ÖH D26 · P11B4-08 — RENK EŞİĞİ KAYAN NOKTA GÜRÜLTÜSÜNE OTURUYORDU.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531): `ciplak_kucuktur = 1` —
       karşılaştırma çıplak `sf < required` idi ve `bagil_tolerans = 0`.
       Uçtan gelen emniyet katsayısı bir BÖLME zincirinin sonucudur
       (izin verilen gerilme / gerilme); hedefiyle matematiksel olarak
       EŞİT olduğu koşumda bile ikili gösterimde 4,4e-16'lık artık
       kalabiliyor. Sonuç: ekranda AYNI sayı — `4.00` — bir satırda
       TURUNCU ("hedefin altında"), diğerinde YEŞİL basılıyordu.

       Kullanıcının gördüğü sayı ile rengin dayandığı sayı AYNI olmalıdır.
       Bağıl tolerans (doktrin 4: TEK yerde) ölçülen gürültünün yedi
       büyüklük mertebesi üstünde, mühendislik anlamı olan en küçük
       farkın çok altındadır — yani gerçek bir eksiklik ASLA yeşile
       boyanmaz, yalnız ikili gösterim artığı yutulur.

       Not: eşik gevşetilmiyor; `sf < 1.0` (akma) kapısı çıplak kalır,
       çünkü orada 1,0 tam sayıdır ve karşılaştırma zaten kesindir. */
    const SF_RENK_BAGIL_TOLERANS = 1e-9;

    function sfHedefiTutuyor(sf, required) {
        if (required == null || !Number.isFinite(required)) return true;
        if (sf >= required) return true;
        // required > 0 olduğu sürece bağıl fark; aksi hâlde mutlak fark.
        const olcek = Math.abs(required) > 0 ? Math.abs(required) : 1.0;
        return (required - sf) <= SF_RENK_BAGIL_TOLERANS * olcek;
    }

    function sfKind(sf, required, tautological) {
        if (sf == null || !Number.isFinite(sf)) return 'dim';
        // Akma aşılmışsa sayı totolojik olsa bile KIRMIZI kalır: hedefin
        // geri okuması bile 1'in altındaysa tasarım kendi hedefini tutmuyor.
        if (sf < 1.0) return 'err';
        if (tautological === true) return 'dim';
        if (!sfHedefiTutuyor(sf, required)) return 'warn';
        return 'ok';
    }

    function sfCell(sf, required, tautological) {
        let k = sfKind(sf, required, tautological);
        // 5. tur: motorun cidarı geçerlilik dışındaysa yeşil ("sınandı ve
        // geçti") basılmaz; sayı tanıdır. Kırmızı/turuncu aynen kalır.
        if (k === 'ok' && motorGecerlilikDisi()) k = 'dim';
        const c = U.kindColor(k);
        return `<span style="color:${c}; font-family:var(--hd-mono);">${U.fmt(sf)}</span>`;
    }

    // Modun insan-okur adı. Hem mod satırları hem de manşetin "kaynağı"
    // buradan okur; T() çağrı ANINDA çözülür (dil değişince yeniden çizim).
    function modeLabel(k) {
        const LABELS = {
            chamber_hoop: T('panel.structural.modeChamberHoop', 'Chamber hoop'),
            chamber_von_mises: T('panel.structural.modeChamberVm', 'Chamber von Mises'),
            end_cap: T('panel.structural.modeEndCap', 'End cap'),
            nozzle: T('panel.structural.modeNozzle', 'Nozzle throat'),
            buckling_axial: T('panel.structural.modeBuckling', 'Axial buckling'),
        };
        return LABELS[k] || k;
    }

    // Makine alan adı etiketi: ucun alan adı VERİ olarak basılır
    // (yeni çeviri anahtarı açmadan hangi sayının hangisi olduğu okunur).
    function machineLabel(name) {
        return `<span style="font-family:var(--hd-mono); font-size:0.75rem;
            color:var(--hd-ink-dim, #7d97a5);">${name}</span>`;
    }

    // Totoloji imi: sayının YANINDA ucun kendi alan adı. Yeni çeviri
    // anahtarı açılmaz — makine alan adı veri olarak basılır.
    function tautMark(isTaut) {
        return isTaut === true
            ? ` <span style="color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); font-size:0.7rem;"
                 >safety_factor_is_tautological</span>`
            : '';
    }

    function isNum(x) {
        return typeof x === 'number' && Number.isFinite(x);
    }

    // ------------------------------------------------------------------
    // HANGİ KOŞUM?  (P17B3-06)
    // ------------------------------------------------------------------
    // Aynı ekranda İKİ asgari emniyet katsayısı duruyor ve ikisi de aynı
    // adı taşıyordu: sayfa başındaki HUD kartı motor hesabının yapısal
    // bloğundan (`/calculate*` → `motor.structural_analysis.safety_analysis
    // .minimum_safety_factor`), güverte paneli ise KENDİ koşumundan
    // (`/analyze_structural_safety`). P17 turu bunları 0,81 ⟷ 1,07 ölçtü —
    // 1,0 eşiğinin iki yanı. Sayılar aynı BÜYÜKLÜĞÜN iki ayrı koşumudur;
    // ayrışmanın nedeni girdi kümesidir (cidar, cidar sıcaklığı, itki).
    // Bugünkü ölçüm (hibrit varsayılan tasarım, panel önerileriyle):
    // ikisi de 1,7173327063051922 — bit-özdeş. Yani ayrışma her koşuda
    // yok, ama VARDIĞINDA ekran hangisinin ne olduğunu söylemiyordu.
    // Çözüm: her sayı hangi koşumdan geldiğini ADIYLA taşır, panel de
    // motor koşumunun sayısını yanına basıp farkı ilan eder.
    const MOTOR_ENDPOINTS = {
        hybrid: '/calculate', solid: '/calculate_solid',
        liquid: '/calculate_liquid',
    };
    const PANEL_ENDPOINT = '/analyze_structural_safety';

    function motorEndpointName() {
        const dock = window.AnalysisDock;
        const t = (dock && typeof dock.getMotorType === 'function')
            ? dock.getMotorType() : null;
        // Motor tipi bilinmiyorsa uç adı UYDURULMAZ (null → künye basılmaz).
        return MOTOR_ENDPOINTS[t] || null;
    }

    // Son motor hesabının yapısal hükmü. `fromResults` her hesap sonrası
    // (AnalysisDock.refreshSuggestions) çağrıldığı için burada tazelenir;
    // hesap yapılmadıysa null kalır ve kıyas satırı HİÇ basılmaz.
    let motorSolve = null;

    // ------------------------------------------------------------------
    // Z5-C1 / OH-Z4-05 — KENDİ CİDARINI DOĞRULATMA DÖNGÜSÜ KIRILDI
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (2026-08-27, app.test_client; kanıt dosyası
    // docs/scofield/raw/OH/Z5/c/olcum_c1_once.txt):
    //   /calculate  cidar alanı BOŞ  ->  HRMA cidarı kendi boyutlandırdı
    //                                    design_mode: size
    //                                    wall_thickness_source: sized_by_hrma
    //                                    15,903671 mm
    //   panel fromResults o sayıyı cidar alanına doldurdu
    //   /analyze_structural_safety  ->  wall_thickness_source: user_supplied
    //                                   is_verification: true
    //                                   "...this result is a verification."
    // Yani HRMA kendi önerdiği cidarı "kullanıcının cidarı" diye doğruluyor,
    // panel de bunu bağımsız doğrulama gibi basıyordu.
    //
    // ARTIK: öneri yalnız motorun KENDİ künyesi "kullanıcının cidarı
    // sınandı" (design_mode: verify) dediğinde doldurulur. HRMA'nın kendi
    // boyutlandırdığı (design_mode: size) ya da KÜNYESİZ cidar uca HİÇ
    // gönderilmez; alan "sen boyutlandır" nöbetçisine (0) çekilir ve uç
    // KENDİ WALL_GATE_SIZED yolunu kazanır. Ölçüldü (olcum_c1_sifir_cidar.txt):
    //   wall_thickness = 0  ->  input_status: not_supplied
    //                           wall_thickness_source: sized_by_hrma
    //                           is_verification: FALSE
    //                           "...a DESIGN PROPOSAL, not a verification..."
    // Kullanıcı alana ELLE değer yazarsa `data-dirty` kapısı bu geri çekmeyi
    // ETKİSİZ kılar (analysis_dock applySuggestions ilk satırı) — gerçek
    // kullanıcı girdisi korunur ve user_supplied yolu aynen çalışır.
    //
    // `wallSuggestion`: son önerinin künyesi. Panel bunu ekrana da basar;
    // öneri hiç yapılmadıysa null kalır ve HİÇBİR ŞEY iddia edilmez.
    let wallSuggestion = null;

    //: Alanın "cidarı sen boyutlandır" nöbetçi değeri (panel alan tanımıyla
    //  birebir aynı: ['wall_thickness', ..., 0, 0.001]).
    const WALL_FIELD_SIZE_SENTINEL = 0;

    // Motor sonucundan cidar önerisi + künyesi. Dönen değer HER ZAMAN bir
    // SAYIDIR (metre): ya çözücünün kullanıcı cidarı ya da "sen boyutlandır"
    // nöbetçisi. Geri çekme künyesi `wallSuggestion`da saklanır ve öneri
    // sözlüğüne `__withheld` anahtarıyla iliştirilir (güverte sözleşmesi).
    // Sunucudan gelen künye metni HEM rozet ipucuna (title="…") HEM tabloya
    // giriyor; tırnak/açılı ayraç iki bağlamı da bozardı. Metin
    // ÇARPITILMAZ, yalnız zararsızlaştırılır (sıvı motorun künyesi serbest
    // cümledir: "next standard plate thickness above the requirement").
    function guvenliKunye(x) {
        return String(x === null || x === undefined ? '' : x)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function wallThicknessSuggestion(r) {
        const wp = U.readWallThicknessProvenance(r);
        const yol = wp.blockPath ? ('motor.' + wp.blockPath) : 'motor';
        wp.designMode = guvenliKunye(wp.designMode) || String(wp.designMode);
        wp.declared = guvenliKunye(wp.declared) || String(wp.declared);
        if (wp.source === U.WALL_PROV_USER && isNum(wp.value_m)) {
            wallSuggestion = {
                withheld: false,
                source: wp.source,
                valueMm: wp.value_mm,
                reason: 'wall_thickness from ' + yol + '.design_mode: '
                    + String(wp.designMode)
                    + ' (wall_thickness_source: ' + String(wp.declared) + ')',
            };
            return wp.value_m;
        }
        wallSuggestion = {
            withheld: true,
            source: wp.source,
            valueMm: wp.value_mm,
            reason: 'wall_thickness suggestion withheld: ' + yol
                + '.design_mode: ' + String(wp.designMode)
                + ' · wall_thickness_source: ' + String(wp.declared)
                + ' — HRMA sized this wall, so sending it back would be read '
                + 'as a user-supplied wall (is_verification: true)',
        };
        return WALL_FIELD_SIZE_SENTINEL;
    }

    // İki koşumun AYNI hazneyi anlatıp anlatmadığı: dört künye alanı. İkisi
    // de aynı sözlüğü yayımlıyor (structural_analysis.design_parameters +
    // chamber_analysis), yani kıyas alan adına dayanır, tahmine değil.
    const IDENTITY_FIELDS = [
        ['design_pressure', function (sa) {
            return (sa.design_parameters || {}).design_pressure; }],
        ['material', function (sa) {
            return (sa.design_parameters || {}).material; }],
        ['chamber diameter', function (sa) {
            return (sa.chamber_analysis || {}).diameter; }],
        ['chamber length', function (sa) {
            return (sa.chamber_analysis || {}).length; }],
    ];

    function designIdentity(sa) {
        const out = {};
        IDENTITY_FIELDS.forEach(function (f) { out[f[0]] = f[1](sa || {}); });
        return out;
    }

    // Farklı olan künye alanlarının adı + iki değeri. Boş liste = aynı hazne.
    function identityDiff(a, b) {
        if (!a || !b) return null;                 // kıyas yapılamaz
        const out = [];
        IDENTITY_FIELDS.forEach(function (f) {
            const x = a[f[0]], y = b[f[0]];
            if (isNum(x) && isNum(y)) {
                if (Math.abs(x - y) > Math.max(Math.abs(x), Math.abs(y)) * 1e-6) {
                    out.push(f[0] + ' ' + U.fmt(x, 3) + ' ⟷ ' + U.fmt(y, 3));
                }
                return;
            }
            if (String(x == null ? '' : x).toLowerCase()
                    !== String(y == null ? '' : y).toLowerCase()) {
                out.push(f[0] + ' ' + String(x == null ? '—' : x)
                         + ' ⟷ ' + String(y == null ? '—' : y));
            }
        });
        return out;
    }

    // ------------------------------------------------------------------
    // V3 yapi-sf 5. tur (14 Eki; 4. tur devir 1, ana model kararı) —
    // MOTORUN CİDARI MODEL GEÇERLİLİĞİ DIŞINDAYKEN PANEL ONAY BASMAZ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (kanit/t4_dock_panel_kati_al.json, kanit/t5_dock_panel_once.json):
    // katı sayfada (Al 6061, 4 mm, kasa 1636,8 K) motor künyesi
    // `case_analysis.model_validity_limit_exceeded: true` diyor; panel aynı
    // cidarı (design_mode: verify) /analyze_structural_safety'ye SICAKLIKSIZ
    // gönderiyor, uç 300 K'de değerlendirip `is_verification: true`,
    // "this result verifies the chamber wall only", design_target_assessment
    // `status: SAFE`, `FATIGUE: SAFE` yayımlıyordu. Sıvı radyatif vakada da
    // (chamber_structure, 1800 K) panel `SAFE`/`ACCEPTABLE` basıyordu.
    //
    // Karar: panel YALNIZ motorun kendi künye bloğundaki bayrağı okur
    // (ikinci ölçüt yazılmaz, yeni sunucu mantığı yok). Bayrak TRUE iken:
    // onay hükümleri (ONAY_HUKUMLERI) 'withheld' basılır, sunucunun doğrulama
    // cümlesi basılmaz, sayılar 'tanı' etiketiyle ve yeşilsiz kalır. Başarısız
    // hükümler (UNSAFE/CRITICAL/MARGINAL) SUSTURULMAZ (§28-44 deseni: FAIL
    // korunur). Bayrak yoksa ya da FALSE ise çıktı bit-aynı. Motorun çözülmüş
    // cidar sıcaklığı uca gidiyorsa (fromResults `wt`; hibrit) kapı AÇILMAZ:
    // uç aynı ölçütü o sıcaklıkta kendisi uygular (ölçüldü: hibrit örnekte
    // ucun kendi bayrağı True ve gerekçesi MODEL_VALIDITY_VERDICT_BASIS).
    let motorValidity = null;

    //: Onay sayılan hüküm sözcükleri (statusKind'in 'ok' sınıfı + kap
    //: sözlüğünün PASS/OK'u). Bayrak TRUE iken bunlar ekrana ÇIKMAZ.
    const ONAY_HUKUMLERI = ['SAFE', 'ACCEPTABLE', 'PASS', 'OK'];
    //: Geri çekilen hükmün makine dizesi (ucun `design_basis.verdict`
    //: sözlüğüyle aynı sözcük).
    const HUKUM_GERI_CEKILDI = 'withheld';

    function readMotorValidity(r) {
        const wp = U.readWallThicknessProvenance(r);
        if (!wp || !wp.blockPath) return null;
        let blk = U.motorDict(r);
        String(wp.blockPath).split('.').forEach(function (p) {
            blk = (blk && typeof blk === 'object') ? blk[p] : undefined;
        });
        if (!blk || typeof blk !== 'object'
                || blk.model_validity_limit_exceeded !== true) return null;
        return {
            path: 'motor.' + wp.blockPath,
            reasons: Array.isArray(blk.model_validity_reasons)
                ? blk.model_validity_reasons.map(guvenliKunye) : [],
        };
    }

    function motorGecerlilikDisi() {
        return motorValidity !== null;
    }

    // Bayrak TRUE iken onay hükmü 'withheld' olur; diğer hükümler aynen.
    function onayGeriCek(status) {
        if (!motorGecerlilikDisi()) return status;
        const t = String(status == null ? '' : status).toUpperCase();
        return ONAY_HUKUMLERI.indexOf(t) !== -1 ? HUKUM_GERI_CEKILDI : status;
    }

    function motorValidityBlock() {
        if (!motorGecerlilikDisi()) return '';
        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:6px 0;">`
            + U.badge(T('panel.structural.badgeModelValidity',
                        'OUTSIDE MODEL VALIDITY'), 'warn', motorValidity.path)
            + U.badge(T('panel.structural.verdictWithheld', 'VERDICT WITHHELD'),
                      'warn')
            + '</div>';
        html += `<p style="font-size:0.78rem; color:${U.kindColor('warn')};">${
            T('panel.structural.motorModelValidityNote',
              'The motor\'s own wall on this page is outside the validity '
              + 'limit of the current structural model. This panel run does '
              + 'not carry the motor\'s wall temperature, so it is not a '
              + 'verification of that wall: no acceptance is shown and the '
              + 'numbers below are diagnostic only.')}</p>`;
        const satir = [['model_validity_limit_exceeded',
            `<span style="color:${U.kindColor('warn')};
             font-family:var(--hd-mono); font-size:0.75rem;">true · ${
                motorValidity.path}</span>`]];
        if (motorValidity.reasons.length) {
            satir.push(['model_validity_reasons',
                `<span style="color:${U.kindColor('warn')};
                 font-family:var(--hd-mono); font-size:0.75rem;">${
                    motorValidity.reasons.join(', ')}</span>`]);
        }
        return html + U.kvTable(satir);
    }

    function readMotorSolve(r) {
        const sa = (U.motorDict(r) || {}).structural_analysis;
        if (!sa || typeof sa !== 'object') return null;
        const sf = sa.safety_analysis;
        if (!sf || typeof sf !== 'object') return null;
        if (!isNum(sf.minimum_safety_factor)) return null;
        const ca = sa.chamber_analysis || {};
        return {
            minimum: sf.minimum_safety_factor,
            earned: isNum(sf.minimum_earned_safety_factor)
                ? sf.minimum_earned_safety_factor : null,
            binding: Array.isArray(sf.binding_safety_factors)
                ? sf.binding_safety_factors.slice() : null,
            tautological: sf.binding_safety_factor_is_tautological,
            status: sf.status || null,
            wallMm: isNum(ca.wall_thickness_used_mm)
                ? ca.wall_thickness_used_mm : null,
            designMode: ca.design_mode || null,
            // Motor koşumu cidarı KENDİ mi boyutlandırdı? (Beyan yoksa
            // iddia edilmez.)
            sizedItsOwnWall: (String(ca.design_mode || '') === 'size'
                || String(ca.wall_thickness_source || '') === 'sized_by_hrma'),
            identity: designIdentity(sa),
        };
    }

    // ------------------------------------------------------------------
    // V3 KK (YP7 devri) — MOTORUN KENDİ TASARIM EMNİYET KATSAYISI HEDEFİ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (main fe18664e, örnek sıvı): motor safety_factor 2,5 (form)
    // ile hesaplanıyor, ama güverte yükünde `safety_factor` alanı YOKTU; uç
    // /analyze_structural_safety bu yüzden malzeme kaydının varsayılanını
    // (inconel_718: 3,0; design_basis.design_safety_factor_source =
    // materials_database_default) kullanıyor ve design_target_assessment
    // kullanıcının hedefini değil o varsayılanı notluyordu (katı: motor 3,0
    // ⟷ güverte 4,0). Ana model kararı: güverte motorun KENDİ hedefini
    // taşır; motor yayımlamıyorsa alan BOŞ kalır, uç malzeme varsayılanını
    // kullanır ve bu hem yanıtta (design_safety_factor_source) hem panelde
    // ADIYLA söylenir. Tek kaynak: motor yanıtının hedef alanı. Blok yolu
    // güvertenin künye haritasından (readWallThicknessProvenance) gelir;
    // her blokta hedefin alan adı aşağıdadır. Sıvının alanı `safety_factor`
    // adını taşır (safety_factor_basis: DESIGN TARGET read back); ad tek
    // başına belirsiz olduğu için yalnız hedefin künyesi (safety_factor_
    // source) da varsa okunur.
    const MOTOR_SF_TARGET_FIELD = {
        chamber_analysis: 'design_safety_factor_target',   // hibrit
        case_analysis: 'design_safety_factor',             // katı
        chamber_structure: 'safety_factor',                // sıvı
    };
    //: Hedef taşınamadığında güverte kaynak çipinin ipucu (makine dizesi).
    const MOTOR_SF_TARGET_ABSENT = 'motor_published_no_design_safety_factor_target';
    let motorSfTarget = null;

    function readMotorSfTarget(r) {
        const wp = U.readWallThicknessProvenance(r);
        if (!wp || !wp.blockPath) return null;
        const parts = String(wp.blockPath).split('.');
        const field = MOTOR_SF_TARGET_FIELD[parts[parts.length - 1]];
        if (!field) return null;
        let blk = U.motorDict(r);
        parts.forEach(function (p) {
            blk = (blk && typeof blk === 'object') ? blk[p] : undefined;
        });
        if (!blk || typeof blk !== 'object') return null;
        const v = blk[field];
        if (!isNum(v) || !(v > 0)) return null;
        if (field === 'safety_factor'
                && typeof blk.safety_factor_source !== 'string') return null;
        return { value: v, path: 'motor.' + wp.blockPath + '.' + field };
    }

    // design_target_assessment satırının hedef KAYNAĞI (yalnız bilinen
    // makine değerleri; sunucu metni HTML olarak girmez).
    function sfTargetSourceText(db, dta) {
        const src = (db && typeof db === 'object')
            ? db.design_safety_factor_source : null;
        if (src === 'materials_database_default') {
            return T('panel.structural.sfTargetMaterialDefault',
                     'source: material database default (the motor result '
                     + 'published no design safety factor target)');
        }
        if (src !== 'user_supplied') return null;
        const t = dta && dta.design_safety_factor_target;
        if (motorSfTarget && isNum(t) && Math.abs(motorSfTarget.value - t)
                <= 1e-9 * Math.max(1, Math.abs(t))) {
            return U.tf('panel.structural.sfTargetFromMotor',
                        { path: motorSfTarget.path },
                        'source: motor design target ({path})');
        }
        return T('panel.structural.sfTargetPanel',
                 'source: value entered in this panel');
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

    // ------------------------------------------------------------------
    // KAZANILMIŞ SF'nin KAYNAĞI  (P11B4-03 / P11S1-01)
    // ------------------------------------------------------------------
    // `minimum_earned_safety_factor` hangi mod(lar)dan geliyor? Yalnız
    // sunucunun AÇIKÇA "totolojik değil" dediği modlar sayılır: bayrağı
    // olmayan bir emniyet katsayısının kazanıldığı KANITLANAMAZ (modülün
    // kendi varsayılanı da True yönündedir — structural_analysis.py).
    function earnedModes(sf) {
        const modes = (sf && sf.safety_factors) || {};
        const taut = (sf && sf.safety_factor_is_tautological) || {};
        const earned = (sf && isNum(sf.minimum_earned_safety_factor))
            ? sf.minimum_earned_safety_factor : null;
        if (earned === null) return [];
        return Object.keys(modes).filter(function (k) {
            const v = modes[k];
            if (!isNum(v)) return false;        // sonsuz/NaN JSON'da null olur
            if (taut[k] !== false) return false;
            return Math.abs(v - earned) <= Math.abs(earned) * 1e-9;
        });
    }

    function safetyFactorTable(ca, sf, required, sa, db) {
        // SF_pressure / SF_total: backend ajanı bu alanları ekliyor;
        // henüz yoksa mevcut emniyet katsayılarına düş (görev sözleşmesi).
        const sfPressure = U.pick(ca, ['safety_factor_pressure', 'SF_pressure', 'sf_pressure'])
            || U.pick(sf, ['safety_factor_pressure', 'SF_pressure', 'sf_pressure'])
            || ca.hoop_safety_factor;
        const sfTotal = U.pick(ca, ['safety_factor_total', 'SF_total', 'sf_total'])
            || U.pick(sf, ['safety_factor_total', 'SF_total', 'sf_total'])
            || ca.von_mises_safety_factor;

        // ==============================================================
        // MANŞET — KULLANICININ KAZANDIĞI EMNİYET KATSAYISI
        // --------------------------------------------------------------
        // ÖLÇÜLDÜ (2026-08-27, panelin KENDİ alan varsayılanları + cidar
        // süpürmesi, /analyze_structural_safety, steel_4130 / 40 bar /
        // D=100 mm / d_boğaz=20 mm):
        //
        //   kullanıcı cidarı   minimum_safety_factor   minimum_earned_...
        //      2 mm                 3,0573                  3,0573
        //      3 mm                 4,0000                  4,5860
        //      5 mm                 4,0000                  7,6433
        //      8 mm                 4,0000                 11,2617
        //     15 mm                 4,0000                 17,9935
        //
        // Panel yalnız SOL sütunu basıyordu, üstelik "Minimum SF (all
        // modes)" etiketiyle. Kullanıcı cidarını 3'ten 15 mm'ye çıkarınca
        // ekrandaki sayı 4,00'de DONUYORDU: minimumu belirleyen iki mod
        // (nozzle + end_cap) HRMA'nın kendi boyutlandırdığı kesitler ve o
        // sayı tasarım hedefinin geri okuması (hedef x imalat payı).
        // Kullanıcının cidarının KAZANDIĞI marj ekranda hiç yoktu
        // (structural_panel.js grep: `minimum_earned_safety_factor` 0).
        //
        // Sıra artık: (1) kazanılmış sayı + onu belirleyen mod, (2) bütün
        // modların minimumu + hedef geri okuması olduğunda sunucunun kendi
        // gerekçesi. Alan yoksa sayı UYDURULMAZ — '—' ve nedeni.
        // ==============================================================
        //
        // Z4-A KANALI (aynı gün, uç katmanı): uç artık istasyon ayrımını
        // KENDİ yayımlıyor — `verified_stations` / `stations_not_verified`
        // / `stations_reading_back_target` / `earned_scope_status` /
        // `design_target_assessment` / `verdict_safety_factor(_source)` /
        // `minimum_safety_factor_basis`. Bunlar VARSA türetme yapılmaz,
        // ucun beyanı basılır; YOKSA panel kendi türetmesine (aşağıdaki
        // `earnedModes`) düşer ve hiçbir sayı uydurmaz.
        const earnedVal = (sf && isNum(sf.minimum_earned_safety_factor))
            ? sf.minimum_earned_safety_factor : null;
        const verified = (sf && Array.isArray(sf.verified_stations))
            ? sf.verified_stations : null;
        // Manşetin KAYNAĞI: kazanılmış minimumu BELİRLEYEN istasyon(lar).
        // Türetme (SF haritası + totoloji bayrakları) daha dardır, ucun
        // `verified_stations` listesi ise "doğrulanan bütün istasyonlar".
        // Kesişim varsa o basılır; türetme boşsa ucun listesine düşülür.
        let eModes = earnedModes(sf);
        if (verified && verified.length) {
            const kesisim = eModes.filter(function (k) {
                return verified.indexOf(k) !== -1;
            });
            eModes = kesisim.length ? kesisim : (eModes.length ? eModes : verified);
        }
        // 5. tur: motorun cidarı geçerlilik dışındaysa hükmün gerekçe
        // cümlesi ("…would pass…", "…an independent verification…") 300 K
        // koşumunun onay/doğrulama iddiasıdır — ne paragraf ne ipucu basılır.
        // İstisna: panel koşumu KENDİSİ de geçerlilik dışıysa (ucun kendi
        // `safety_analysis.model_validity_limit_exceeded` bayrağı) cümle
        // zaten tanı cümlesidir (structural_analysis.py
        // MODEL_VALIDITY_VERDICT_BASIS; "…never suppressed") ve kalır.
        const basisCek = motorGecerlilikDisi()
            && !(sf && sf.model_validity_limit_exceeded === true);
        const basis = basisCek ? ''
            : ((sf && sf.minimum_safety_factor_verdict_basis) || '');
        // OH-Z4-04: bu satırın etiketi 'Safety Factor' idi — kardeşi
        // 'Minimum SF (all modes)' iken manşetin KENDİ adı ('kazanılmış
        // asgari') ekranda yoktu; iki satır aynı tablodaydı ve hangisinin
        // kullanıcının cidarını sınadığı yalnız makine adından okunuyordu.
        const earnedLabel = T('panel.structural.sfMinEarned', 'Minimum SF (earned)')
            + ` <span style="color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); font-size:0.72rem;"
                 >minimum_earned_safety_factor</span>`;
        let earnedCell;
        if (earnedVal !== null) {
            earnedCell = sfCell(earnedVal, required)
                + (eModes.length
                    ? ` <span style="color:var(--hd-ink-dim, #7d97a5);
                         font-size:0.75rem;">· ${eModes.map(modeLabel).join(' · ')}</span>`
                    : '');
            // DOĞRULANAN KAPSAMIN HÜKMÜ: ucun kendi kararı. Üst rozetteki
            // genel hüküm (NOT_EVALUATED) kapsamın TAMAMI doğrulanmadığı
            // için geri çekilebilir; bu satır doğrulanan kesitlerin hükmünü
            // ADIYLA taşır, aksi hâlde ekranda hiç görünmezdi.
            if (sf.earned_scope_status) {
                // 5. tur: onay hükmü geri çekilince yanındaki risk düzeyi de
                // (o hükmün parçası) basılmaz.
                const esSt = onayGeriCek(sf.earned_scope_status);
                const esCek = esSt !== sf.earned_scope_status;
                earnedCell += ` <span style="color:${U.kindColor(
                    statusKind(esSt))};
                     font-family:var(--hd-mono); font-size:0.72rem;"
                     >earned_scope_status: ${esSt}${
                    (sf.earned_scope_risk_level && !esCek)
                        ? ' · earned_scope_risk_level: '
                          + sf.earned_scope_risk_level : ''}</span>`;
            }
        } else {
            // Kazanılmış SF YOK: değerlendirilen kesitlerin hepsi HRMA'nın
            // kendi boyutlandırdığı kesitler. Sayı yerine gerekçe.
            earnedCell = `<span style="color:${U.kindColor('warn')};
                 font-family:var(--hd-mono);">—</span>
                 <span style="color:var(--hd-ink-dim, #7d97a5); font-size:0.75rem;"
                 >· ${(sf && sf.minimum_earned_safety_factor === null)
                      ? 'minimum_earned_safety_factor: null'
                      : 'minimum_earned_safety_factor'}</span>`;
        }
        // Üçüncü öge kvTable'da `title="…"` ipucudur — o da sunucunun
        // cümlesidir, çeviri kanalından geçer (OH-Z4-04).
        // ==============================================================
        // ÖH D23 / OH-D22-05 — MANŞET SAYISI KENDİ ADIYLA BASILIR
        // --------------------------------------------------------------
        // ÖLÇÜLDÜ (once.json OH-D22-05): uç ``headline_safety_factor``
        // + ``headline_safety_factor_source`` alanlarını YAYIMLIYOR
        // (structural_analysis.py::_analyze_safety_factors) ama bu dosyada
        // grep 0; panelin ilk satırı hâlâ ``minimum_earned_safety_factor``
        // idi (grep 12). Yani "hükmün çekildiği sayı" ile "kazanılmış
        // asgari" ayrıştığında ekran hangisinin MANŞET olduğunu
        // söylemiyordu — P7B3-23'ün ekran ayağı buydu.
        //
        // Fail-closed: sayı UYDURULMAZ ve türetilmez. Satır YALNIZ uç
        // kendi künyesini (``headline_safety_factor_source``) yayımladıysa
        // basılır; hüküm geri çekilmişse (alan null) sayı yerine ucun
        // kendi gerekçesi görünür. P5B1-01'in kazandığı iki satır
        // (kazanılmış asgari + bütün modların minimumu) OLDUĞU GİBİ kalır;
        // bu satır onların ÜSTÜNE eklenir, yerlerini almaz.
        // ==============================================================
        const rows = [];
        if (sf && typeof sf.headline_safety_factor_source === 'string'
                && sf.headline_safety_factor_source) {
            const headlineVal = isNum(sf.headline_safety_factor)
                ? sf.headline_safety_factor : null;
            const headlineLabel = T('panel.structural.sfHeadline',
                                    'Headline SF (verdict)')
                + ` <span style="color:var(--hd-ink-dim, #7d97a5);
                     font-family:var(--hd-mono); font-size:0.72rem;"
                     >headline_safety_factor</span>`;
            let headlineCell;
            if (headlineVal !== null) {
                headlineCell = sfCell(headlineVal, required);
            } else {
                // Hüküm geri çekilmiş: manşete hiçbir sayı terfi ETMEZ.
                headlineCell = `<span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono);">—</span>
                     <span style="color:var(--hd-ink-dim, #7d97a5);
                      font-size:0.75rem;">· headline_safety_factor: null</span>`;
            }
            rows.push([headlineLabel, headlineCell,
                       SRV(sf.headline_safety_factor_source)]);
        }
        rows.push([earnedLabel, earnedCell, SRV(basis)]);

        if (sf && sf.minimum_safety_factor != null) {
            // Bu satır "bütün modlar"ın minimumudur ve HRMA'nın kendi
            // boyutlandırdığı kesitleri de içerir. Belirleyici mod(lar)
            // totolojikse künye bunu ADIYLA söyler; gerekçe cümlesi
            // tablonun altında sunucunun kendi kelimeleriyle basılır.
            const tautological = (sf.binding_safety_factor_is_tautological === true);
            const bind = Array.isArray(sf.binding_safety_factors)
                ? sf.binding_safety_factors : [];
            const mep = motorEndpointName();
            const allLabel = T('panel.structural.sfMinAll', 'Minimum SF (all modes)')
                + ` <span style="color:var(--hd-ink-dim, #7d97a5);
                     font-family:var(--hd-mono); font-size:0.72rem;"
                     >${PANEL_ENDPOINT}</span>`;
            // P11B4-04: belirleyici mod totolojikse bu sayı da bir ÖLÇÜM
            // değil, hedefin geri okumasıdır — yeşil hüküm düşer.
            let allCell = sfCell(sf.minimum_safety_factor, required, tautological);
            if (bind.length) {
                allCell += ` <span style="color:var(--hd-ink-dim, #7d97a5);
                     font-size:0.75rem;">· ${bind.map(modeLabel).join(' · ')}</span>`;
            }
            // Hedef geri okuması imi: uç istasyonları adıyla veriyorsa
            // onlar basılır (daha bilgili), yoksa bayrağın kendi adı.
            const readback = Array.isArray(sf.stations_reading_back_target)
                ? sf.stations_reading_back_target : null;
            // İm YALNIZ minimumu belirleyen istasyon hedefi geri okuyorsa
            // basılır. Aksi hâlde bu satırdaki sayı gerçek bir ölçümdür ve
            // "hedef geri okuması" imi YANLIŞ olurdu (ölçüldü: 2 mm cidar —
            // binding chamber_hoop, geri okuyanlar end_cap+nozzle).
            // Z4: sunucunun KESKİN alanı öncelikli — yayımlanmışsa türetme
            // yerine o okunur (JS some() ⟷ sunucu all() ayrışması kapanır).
            const bindOkur = (typeof sf.binding_safety_factor_reads_back_target
                    === 'boolean')
                ? sf.binding_safety_factor_reads_back_target
                : !!(readback && readback.length && bind.length
                && bind.some(function (k) { return readback.indexOf(k) !== -1; }));
            if (bindOkur) {
                allCell += ` <span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono); font-size:0.72rem;"
                     >stations_reading_back_target: ${readback.join(', ')}</span>`;
                // OH-Z4-04: makine adı KALIR (alan adresi), yanına ne demek
                // olduğu iki dilde yazılır. Bu im olmadan kullanıcı bu
                // sayıyı kendi cidarının doğrulaması sanıyordu.
                allCell += ` <span style="color:${U.kindColor('warn')};
                     font-size:0.72rem;">${T('panel.structural.sfTargetReadback',
                    'This safety factor reads the design target back — it was '
                    + 'not measured on a wall you supplied.')}</span>`;
            } else if (!readback && tautological) {
                allCell += ` <span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono); font-size:0.72rem;"
                     >binding_safety_factor_is_tautological: true</span>`;
            }
            // Bu SAYININ ne olduğunu ucun kendi cümlesi söylüyorsa ipucu o.
            rows.push([allLabel, allCell,
                       SRV(sf.minimum_safety_factor_basis || basis)]);

            // HEDEF AYRI SATIRDA (görev kalemi 1): HRMA'nın kendi
            // boyutlandırdığı kesitlerin hükmü, sayısı ve hangi kesitler
            // olduğu — ucun `design_target_assessment` bloğundan.
            const dta = sf.design_target_assessment;
            if (dta && typeof dta === 'object') {
                const st = dta.status ? String(dta.status) : null;
                // P11B4-04: bu sayı ADIYLA hedeften türer
                // (`target_derived_…`); hiçbir koşulda bağımsız bir
                // doğrulama değildir, yeşil basılamaz.
                let cell = sfCell(dta.target_derived_minimum_safety_factor,
                                  required, true);
                const ek = [];
                if (isNum(dta.design_safety_factor_target)) {
                    ek.push('design_safety_factor_target: '
                            + U.fmt(dta.design_safety_factor_target, 1));
                    // V3 KK: hedefin kaynağı ADIYLA (sessiz düşüş yok).
                    const kaynak = sfTargetSourceText(db, dta);
                    if (kaynak) ek.push(kaynak);
                }
                if (Array.isArray(dta.stations) && dta.stations.length) {
                    ek.push('stations: ' + dta.stations.join(', '));
                }
                if (ek.length) {
                    cell += ` <span style="color:var(--hd-ink-dim, #7d97a5);
                         font-size:0.72rem; font-family:var(--hd-mono);"
                         >· ${ek.join(' · ')}</span>`;
                }
                if (st) {
                    const stG = onayGeriCek(st);
                    cell += ` <span style="color:${U.kindColor(statusKind(stG))};
                         font-family:var(--hd-mono); font-size:0.72rem;"
                         >status: ${stG}${(dta.risk_level && stG === st)
                             ? ' · risk_level: ' + dta.risk_level : ''}</span>`;
                }
                rows.push(['design_target_assessment', cell,
                           SRV(dta.basis || '')]);
            }

            // Hükmün ÇEKİLDİĞİ sayı (uç ayrı yayımlıyorsa): kaynağıyla.
            if (isNum(sf.verdict_safety_factor)) {
                rows.push([
                    'verdict_safety_factor',
                    sfCell(sf.verdict_safety_factor, required)
                    + (sf.verdict_safety_factor_source
                        ? ` <span style="color:var(--hd-ink-dim, #7d97a5);
                             font-size:0.72rem; font-family:var(--hd-mono);"
                             >· ${sf.verdict_safety_factor_source}</span>` : ''),
                    String(sf.verdict_safety_factor_source || ''),
                ]);
            }
            // Motor hesabının AYNI büyüklüğü — varsa yan yana (P17B3-06).
            // Δ YALNIZ iki koşum aynı hazneyi anlatıyorsa basılır; künye
            // alanları ayrışıyorsa fark bir çelişki DEĞİLDİR ve o zaman
            // ayrışan alanların ADI yazılır (yanlış alarm üretilmez).
            if (motorSolve && mep) {
                const fark = identityDiff(motorSolve.identity, designIdentity(sa));
                let cell = sfCell(motorSolve.minimum, required);
                if (isNum(motorSolve.wallMm)) {
                    cell += ` <span style="color:var(--hd-ink-dim, #7d97a5);
                         font-size:0.75rem;">· wall_thickness_used_mm
                         ${U.fmt(motorSolve.wallMm, 2)}</span>`;
                }
                if (fark && fark.length) {
                    cell += ` <span style="color:${U.kindColor('info')};
                         font-size:0.72rem;">· ${fark.join(' · ')}</span>`;
                } else if (fark) {
                    const d = Math.abs(motorSolve.minimum - sf.minimum_safety_factor);
                    const rel = d / Math.max(1e-12, Math.abs(sf.minimum_safety_factor));
                    if (rel > 1e-6) {
                        cell += ` <span style="color:${U.kindColor('warn')};
                             font-family:var(--hd-mono); font-size:0.72rem;">Δ
                             ${U.fmt(d, 2)}</span>`;
                    }
                }
                rows.push([
                    T('panel.structural.sfMinAll', 'Minimum SF (all modes)')
                    + ` <span style="color:var(--hd-ink-dim, #7d97a5);
                         font-family:var(--hd-mono); font-size:0.72rem;"
                         >${mep}</span>`,
                    cell,
                    'motor.structural_analysis.safety_analysis.minimum_safety_factor',
                ]);
            }
        }

        // P11B4-04: iki manşet satırı ODA bloğunun sayılarıdır; totoloji
        // hükmü de o bloktan okunur (`chamber_analysis
        // .safety_factor_is_tautological`), mod haritasından değil.
        const caTaut = (ca && ca.safety_factor_is_tautological === true);
        rows.push([T('panel.structural.sfPressureOnly', 'SF (pressure only)'),
            sfCell(sfPressure, required, caTaut) + tautMark(caTaut),
            T('panel.structural.sfPressureOnlyTip',
              'Pressure-only safety factor (hoop based when backend field is absent)')]);
        rows.push([T('panel.structural.sfTotal', 'SF (total, incl. thermal)'),
            sfCell(sfTotal, required, caTaut) + tautMark(caTaut),
            T('panel.structural.sfTotalTip',
              'Combined safety factor (von Mises based when backend field is absent)')]);

        const modes = (sf && sf.safety_factors) || {};
        const taut = (sf && sf.safety_factor_is_tautological) || {};
        Object.keys(modes).forEach(function (k) {
            // Mod satırı da hangi sınıfta olduğunu taşır: sunucu "totolojik
            // değil" demişse o mod kullanıcının kesitini sınıyor demektir.
            // P11B4-04: im YETMEZ — sayının RENGİ de hükmü taşır, o yüzden
            // totoloji bayrağı sfCell'e geçirilir (yeşil hüküm düşer).
            rows.push(['&nbsp;&nbsp;· ' + modeLabel(k),
                       sfCell(modes[k], required, taut[k] === true)
                       + tautMark(taut[k] === true)]);
        });
        if (required != null) {
            rows.push([T('panel.structural.sfRequired', 'Required design SF (material)'),
                `<span style="font-family:var(--hd-mono);">${U.fmt(required, 1)}</span>`]);
        }
        let html = U.kvTable(rows);
        // Sunucunun kendi gerekçe cümlesi HAM basılır (designBasisBlock ve
        // buck.source ile aynı desen): hedef geri okuması mı, bağımsız
        // doğrulama mı — cümleyi panel yazmaz, sunucu yazar.
        if (basis) {
            html += `<p style="font-size:0.78rem; color:${U.kindColor(
                (sf && sf.binding_safety_factor_is_tautological === true)
                    ? 'warn' : 'info')};">${SRV(basis)}</p>`;
        }
        // OH-Z4-04: motor koşumu yokken kıyas satırı DÜŞÜYOR (fail-closed —
        // uydurma kıyas yok) ama düştüğü SÖYLENMİYORDU; kullanıcı ikinci
        // sayının neden olmadığını göremiyordu. Uç adı bilerek BASILMAZ:
        // koşum yokken uç adını basmak "kıyas var" izlenimi verir ve
        // tests/test_z5guard_urun_tur.py::
        // test_motor_kosumu_yoksa_kiyas_satiri_basilmaz o dizeyi yasaklıyor.
        if (!motorSolve && sf && sf.minimum_safety_factor != null) {
            html += `<p style="font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5);">${T(
                'panel.structural.runMotorSolve',
                'No motor result on this page yet — run the motor '
                + 'calculation first.')}</p>`;
        }
        return html;
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
    // Cidar kapısının ÜÇ durumu (app.py `_classify_wall_thickness_gate`):
    //   sized_by_hrma          — kullanıcı cidar vermedi, HRMA boyutlandırdı
    //   user_supplied          — kullanıcının cidarı GERÇEKTEN sınandı
    //   user_value_not_applied — değer geldi ama hesaba girmedi (okunamadı
    //                            ya da çözücü başka bir kalınlık kullandı)
    // OH-Z2-06 ölçümü: panel `sized = (src === 'sized_by_hrma')` ile İKİ
    // durumlu okuyordu, yani üçüncü durum yeşil "WALL: AS SUPPLIED"
    // rozetine düşüyordu — kullanıcının vermediği bir cidar için "sizin
    // verdiğiniz" demek. Üçüncü durumun sözlükte karşılığı YOK; rozet o
    // durumda alanın kendi makine değerini basar (uydurma İngilizce metin
    // eklenmez) ve kırmızıdır. Sunucunun gerekçe cümlesi hemen altında.
    // Rozetin ipucu metni: kapının kendi makine durumu + (ölçülebiliyorsa)
    // sınanan cidarın motor koşumunun KENDİ boyutlandırdığı cidarla aynı
    // olduğu uyarısı. Bu bir metin İDDİASI değil, iki sayının kıyasıdır:
    // panelin cidar alanı `fromResults` ile motor sonucundan doldurulur,
    // dolayısıyla "kullanıcının verdiği cidar" aslında HRMA'nın kendi
    // önerisi olabilir ve o hâlde hüküm bir doğrulama değil geri okumadır.
    function wallGateTip(db, ca) {
        let tip = String(db.wall_thickness_input_status
                         || db.wall_thickness_source || '');
        const panelWall = (ca || {}).wall_thickness_used_mm;
        if (motorSolve && isNum(motorSolve.wallMm) && isNum(panelWall)
                && motorSolve.sizedItsOwnWall
                && Math.abs(motorSolve.wallMm - panelWall)
                    <= Math.abs(panelWall) * 1e-6) {
            const mep = motorEndpointName();
            tip += ' | wall_thickness_used_mm ' + U.fmt(panelWall, 3)
                + ' = ' + (mep || 'motor') + ' chamber_analysis.design_mode: '
                + String(motorSolve.designMode);
        }
        // Z5-C1: önerinin GERİ ÇEKİLDİĞİ durumda gerekçe rozetin ipucuna da
        // iner (kaynak çipiyle aynı makine dizesi).
        if (wallSuggestion && wallSuggestion.withheld) {
            tip += ' | ' + wallSuggestion.reason;
        }
        return tip;
    }

    function wallGateBadge(db, ca) {
        const src = String(db.wall_thickness_source || '');
        const tip = wallGateTip(db, ca);
        if (src === 'sized_by_hrma') {
            return U.badge(T('panel.structural.wallSized', 'WALL: SIZED BY HRMA'),
                           'warn', tip);
        }
        if (src === 'user_supplied' && db.is_verification !== false) {
            return U.badge(T('panel.structural.wallUser', 'WALL: AS SUPPLIED'),
                           motorGecerlilikDisi() ? 'warn' : 'ok', tip);
        }
        if (src) {
            return U.badge('wall_thickness_source: ' + src, 'err', tip);
        }
        // Beyan HİÇ yok: rozet bir şey İDDİA ETMEZ.
        return U.badge('wall_thickness_source: —', 'dim', '');
    }

    function designBasisBlock(db, ca, sf) {
        if (!db || typeof db !== 'object') return '';
        /* ÖH D26 · P11B4-02 — EKRANDA İKİ HÜKÜM ÇELİŞİYORDU.

           ÖLÇÜLDÜ (a3/once.json, taban 7751531):
             hukum_rozeti_kapisi = 1        (yalnız db.verdict'e bakıyor)
             hukum_rozeti_status_goruyor = 0
             not_evaluated_gerekce_basiliyor = 0
           Rozet YALNIZ `design_basis.verdict` alanına bakıyordu; oysa
           HÜKMÜN kendisi `safety_analysis.status` alanındadır ve uç onu
           `NOT_EVALUATED`'e çekebiliyor (kapsam tam doğrulanmadıysa —
           `stations_not_verified`). O koşumda ekranda yan yana
           "VERDICT ISSUED" ile "STRUCTURE: NOT_EVALUATED" duruyordu ve
           gerekçe (`safety_analysis.verdict_withheld_reasons`) panelde
           hiç OKUNMUYORDU: kullanıcı hükmün neden verilmediğini
           göremiyordu.

           Fail-closed: iki alandan HANGİSİ geri çekilmişse rozet geri
           çekilmiş olanı söyler; gerekçe listesi İKİ kanaldan birleşir
           (tekrarlar düşer). Yeni sayı ya da yeni cümle üretilmez. */
        const safety = (sf && typeof sf === 'object') ? sf : {};
        const withheld = String(db.verdict || '') === 'withheld'
            || String(safety.status || '').toUpperCase() === HUKUM_YOK
            || motorGecerlilikDisi();
        let html = U.sectionTitle(T('panel.structural.secDesignBasis',
                                    'Basis of this verdict'));
        // ==============================================================
        // Z5-C2 / P17B2-11 — ROZET ANLAMBİLİMİ AYRIŞTIRILDI
        // --------------------------------------------------------------
        // ÖLÇÜLEN KUSUR: aynı rozet şeridinde yeşil "VERDICT ISSUED" ile
        // yeşil "BUCKLING: SAFE" BİREBİR aynı yeşildi; hemen yanlarında
        // kırmızı "STRUCTURE: UNSAFE" duruyordu. Yeşil böylece iki ayrı
        // şey demek oluyordu: "hüküm üretildi" ve "geçti". Kullanıcı
        // UNSAFE bir yapının şeridinde iki yeşil rozet görüyordu.
        //
        // ARTIK: "hüküm üretildi" bir SÜREÇ durumudur, bir GEÇME değil —
        // nötr ton (info/cyan) alır. Yeşil YALNIZ "geçti" (SAFE) demektir.
        // Durum rozetleri (SAFE yeşil / UNSAFE kırmızı / MARGINAL amber)
        // aynen korunur; renk paletine yeni ton eklenmez.
        // ==============================================================
        html += `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:6px 0;">`
            + U.badge(withheld
                    ? T('panel.structural.verdictWithheld', 'VERDICT WITHHELD')
                    : T('panel.structural.verdictIssued', 'VERDICT ISSUED'),
                withheld ? 'warn' : 'info')
            + wallGateBadge(db, ca)
            + '</div>';
        // Z5-C1: panelin cidar önerisini GERİ ÇEKTİĞİ durumda gerekçe
        // ekranda, makine adlarıyla. Öneri hiç yapılmadıysa satır basılmaz.
        if (wallSuggestion) {
            html += U.kvTable([[
                'wall_thickness_suggestion',
                `<span style="color:${U.kindColor(
                    wallSuggestion.withheld ? 'warn' : 'info')};
                 font-family:var(--hd-mono); font-size:0.75rem;">${
                    wallSuggestion.withheld ? 'withheld' : 'applied'}</span>
                 <span style="color:var(--hd-ink-dim, #7d97a5);
                  font-size:0.72rem;"> · ${U.esc(wallSuggestion.reason)}</span>${
                    wallSuggestion.withheld
                        ? `<br><span style="color:${U.kindColor('warn')};
                            font-size:0.75rem;">${T(
                            'panel.structural.wallNotApplied',
                            'Wall thickness suggestion withheld — not applied'
                        )}</span>` : ''}`,
            ]]);
        }
        // DOĞRULAMANIN KAPSAMI (Z4-A kanalı): "doğrulama" damgası bütün
        // hazneyi kapsamayabilir — uç neyin sınandığını
        // (`is_verification_scope`) ve hangi istasyonların DIŞARIDA
        // kaldığını (`stations_not_verified`) ayrı ayrı yayımlıyor. Kapsam
        // eksikse yeşil "VERDICT ISSUED / WALL: AS SUPPLIED" ikilisi tek
        // başına yanıltır; bu satırlar kapsamı adıyla yazar.
        if (db.verification_scope_complete === false
                || db.is_verification_scope
                || (Array.isArray(db.stations_not_verified)
                    && db.stations_not_verified.length)) {
            const kapsam = [];
            if (db.is_verification_scope) {
                kapsam.push(['is_verification_scope',
                             String(db.is_verification_scope)]);
            }
            if (Array.isArray(db.stations_not_verified)) {
                kapsam.push(['stations_not_verified',
                    `<span style="color:${U.kindColor(
                        db.stations_not_verified.length ? 'warn' : 'ok')};
                     font-family:var(--hd-mono);">${
                        db.stations_not_verified.length
                            ? db.stations_not_verified.join(', ') : '—'}</span>`]);
            }
            if (typeof db.verification_scope_complete === 'boolean') {
                kapsam.push(['verification_scope_complete',
                    `<span style="color:${U.kindColor(
                        db.verification_scope_complete ? 'ok' : 'warn')};
                     font-family:var(--hd-mono);">${
                        String(db.verification_scope_complete)}</span>`]);
            }
            if (kapsam.length) html += U.kvTable(kapsam);
            // OH-Z4-04: yukarıdaki satırlar ALAN ADLARIDIR (bilinçli makine
            // yolu). Kapsamın gerçekten eksik olduğu durumda bunun ne demek
            // olduğu iki dilde de yazılır — aksi hâlde yeşil "VERDICT ISSUED
            // / WALL: AS SUPPLIED" ikilisi tek başına okunuyordu.
            if (db.verification_scope_complete === false
                    || (Array.isArray(db.stations_not_verified)
                        && db.stations_not_verified.length)) {
                html += `<p style="font-size:0.78rem; color:${
                    U.kindColor('warn')};">${T(
                    'panel.structural.scopeIncomplete',
                    'Verification scope is incomplete: some stations in the '
                    + 'basket were not verified.')}</p>`;
            }
        }
        // "Gönderilen ⟷ değerlendirilen" çifti yalnız üçüncü durumda
        // yayımlanıyor; varsa sayılar da basılır (mesaj metnin içinde
        // taşıyor ama sayı satırı aranabilir olmalı).
        if (db.submitted_wall_thickness_mm != null
                || db.evaluated_wall_thickness_mm != null) {
            html += U.kvTable([
                ['submitted_wall_thickness_mm',
                 `<span style="font-family:var(--hd-mono);">${
                     numL(db.submitted_wall_thickness_mm, 3)}</span>`],
                ['evaluated_wall_thickness_mm',
                 `<span style="font-family:var(--hd-mono);">${
                     numL(db.evaluated_wall_thickness_mm, 3)}</span>`],
            ]);
        }
        // Sunucunun kendi gerekçe metni ham basılır (buck.source, fast.warning
        // ile aynı desen) — panel onu yeniden yazmaz, çarpıtamaz.
        // 5. tur: motorun cidarı geçerlilik dışındaysa sunucunun cümlesi
        // ("…this result verifies the chamber wall only") BASILMAZ — o
        // cümle 300 K koşumunun doğrulama iddiasıdır; yerine makine satırı.
        if (db.message && motorGecerlilikDisi()) {
            html += U.kvTable([['design_basis.message',
                `<span style="color:${U.kindColor('warn')};
                 font-family:var(--hd-mono); font-size:0.75rem;">${
                    HUKUM_GERI_CEKILDI} · model_validity_limit_exceeded</span>`]]);
        } else if (db.message) {
            html += `<p style="font-size:0.8rem; color:${U.kindColor(
                withheld ? 'warn' : 'info')};">${SRV(db.message)}</p>`;
        }
        // P11B4-02: gerekçe İKİ kanaldan birleşir — design_basis'in kendi
        // listesi ve safety_analysis'inki. Aynı kod iki kez basılmaz.
        const reasons = [];
        [db.verdict_withheld_reasons, safety.verdict_withheld_reasons]
            .forEach(function (liste) {
                if (!Array.isArray(liste)) return;
                liste.forEach(function (k) {
                    if (reasons.indexOf(k) === -1) reasons.push(k);
                });
            });
        if (reasons.length) {
            html += U.listBlock(T('panel.structural.withheldReasons',
                                  'Why no acceptance was issued'),
                                reasons.map(hukumKoduMetni), 'warn');
        }
        const notEval = db.not_evaluated;
        if (notEval && notEval.length) {
            html += U.listBlock(T('panel.structural.notEvaluated',
                                  'Not evaluated'),
                                notEval.map(degerlendirilmeyenMetni), 'warn');
        }
        return html;
    }

    /* ==================================================================
       ÖH D26 / P11B4-06 — HÜKMÜN GEREKÇESİ ÇİĞ MAKİNE ANAHTARIYDI
       ==================================================================
       ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): ``design_basis``
       bloğunun iki gerekçe listesi ekrana OLDUĞU GİBİ iniyordu —
       kullanıcı "Why no acceptance was issued" başlığının altında
       ``safety_factor_is_tautological``, "Not evaluated" altında
       ``wall_temperature`` okuyordu. Bunlar ürün metni değil, sunucunun
       İÇ anahtarlarıdır; hükmün NEDEN geri çekildiğini yalnız kodu
       yazan bilir.

       Onarım bir çeviri katmanıdır, bir GİZLEME katmanı değildir:
         * bilinen her kod insan cümlesine çevrilir (i18n anahtarı +
           İngilizce yedek metin);
         * ham anahtar cümlenin YANINDA parantez içinde KALIR — künye
           izlenebilirliği daralmaz (ÖK-22);
         * BİLİNMEYEN kod aynen basılır (fail-closed): sözlükte yoksa
           panel bir cümle UYDURMAZ, kodu olduğu gibi gösterir ve
           kullanıcı en azından bir arama anahtarı görür.

       Kod envanteri app.py'den ölçüldü (``verdict_withheld_reasons``
       append noktaları + ``withheld_reason`` kapıları). */
    const WITHHELD_REASON_TEXT = {
        safety_factor_is_tautological: [
            'panel.structural.reasonTautological',
            'The safety factor could not be earned: the analysis compared '
            + 'the wall against a thickness it had sized itself, so the '
            + 'result is a tautology, not a verification.'],
        wall_temperature_not_computed: [
            'panel.structural.reasonWallTempNotComputed',
            'No wall temperature was computed, so the thermal derating of '
            + 'the material strength could not be applied.'],
        material_identity_unresolved: [
            'panel.structural.reasonMaterialUnresolved',
            'The material record could not be resolved to a single '
            + 'identity, so its allowable stress is not owned by any '
            + 'named material.'],
        user_wall_thickness_not_applied: [
            'panel.structural.reasonUserWallNotApplied',
            'The wall thickness you supplied was not the one evaluated: '
            + 'the analysis substituted its own value, so this run does '
            + 'not verify your wall.'],
        // V3 yapi-sf 2. tur (karar §28-24 (C)): structural_analysis.py
        // STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON.
        model_validity_limit_exceeded: [
            'panel.structural.reasonModelValidity',
            'The chamber was evaluated outside the validity limit of the '
            + 'current structural model (wall temperature at or above the '
            + 'melting point, or above the strength-derating data), so no '
            + 'acceptance and no numeric design verdict is issued; the '
            + 'numbers are diagnostic only.'],
    };

    /* V3 yapi-sf 2. tur (karar §28-24 (C)) — MODEL GEÇERLİLİK SATIRI.
       Uç `chamber_analysis.model_validity_limit_exceeded` bayrağını ve
       gerekçe kodlarını yayımlıyor. Bayrak TRUE iken hazne SF'si, cidar ve
       kütle TANI amaçlıdır: rozet + açıklama + kodlar (makine adı) basılır.
       Bayrak yoksa/FALSE ise hiçbir şey basılmaz (olumlu bir "geçerli"
       damgası UYDURULMAZ). Kodlar çevrilmez (makine adı), cümle i18n. */
    function modelValidityBlock(ca) {
        if (!ca || ca.model_validity_limit_exceeded !== true) return '';
        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:6px 0;">`
            + U.badge(T('panel.structural.badgeModelValidity',
                        'OUTSIDE MODEL VALIDITY'), 'warn')
            + '</div>';
        html += `<p style="font-size:0.78rem; color:${U.kindColor('warn')};">${
            T('panel.structural.modelValidityNote',
              'The structural result is outside the validity limit of the '
              + 'current model: the wall is evaluated at a temperature at or '
              + 'above the melting point of its material, or above its '
              + 'strength-derating data. The strength, safety factors, wall '
              + 'thickness and masses shown are diagnostic only, not valid '
              + 'design outputs. A failing or unreachable result here is a '
              + 'limit of the current model (bare-wall thermal model without '
              + 'grain, liner or insulation protection), not a statement '
              + 'that a real motor of this design is impossible.')}</p>`;
        if (Array.isArray(ca.model_validity_reasons)
                && ca.model_validity_reasons.length) {
            html += U.kvTable([['model_validity_reasons',
                `<span style="color:${U.kindColor('warn')};
                 font-family:var(--hd-mono); font-size:0.75rem;">${
                    ca.model_validity_reasons.join(', ')}</span>`]]);
        }
        return html;
    }

    //: `not_evaluated` listesi ALAN ADI taşır (gerekçe kodu değil).
    //: Aynı kural: bilinen ad cümleye çevrilir, ham ad yanında kalır,
    //: bilinmeyen ad aynen basılır.
    const NOT_EVALUATED_TEXT = {
        wall_temperature: [
            'panel.structural.notEvalWallTemperature',
            'Wall temperature — no temperature input reached the analysis, '
            + 'so thermal effects are switched off in this run.'],
    };

    function _kodMetni(sozluk, kod) {
        const ad = String(kod);
        const rec = sozluk[ad];
        if (!rec) return ad;            // bilinmeyen kod GİZLENMEZ
        return T(rec[0], rec[1]) + ' (' + ad + ')';
    }

    function hukumKoduMetni(kod) {
        return _kodMetni(WITHHELD_REASON_TEXT, kod);
    }

    function degerlendirilmeyenMetni(ad) {
        return _kodMetni(NOT_EVALUATED_TEXT, ad);
    }

    // ------------------------------------------------------------------
    // CİDAR SICAKLIĞININ KAYNAĞI  (`structural_analysis.thermal_analysis`)
    // ------------------------------------------------------------------
    // Uç bu bloğu ZATEN gönderiyordu (`wall_temperature_source`,
    // `thermal_model_ran`, iki cidar sıcaklığı), panel HİÇ okumuyordu.
    // Termal gerilme, mukavemet deratingi ve servis sıcaklığı hükmünün
    // tamamı bu iki sayıdan türüyor; hangisinin ÇÖZÜM hangisinin TAHMİN
    // olduğu ekranda yazmıyordu. Modülün kendi sözlüğü (structural_analysis
    // ._wall_temperature_source):
    //   heat_transfer_module         — ısı modülünün çözdüğü gerçek cidar
    //   chamber_temperature_estimate — yalnız gaz sıcaklığı verildi, cidar
    //                                  radyasyon-denge TAHMİNİ
    //   not_evaluated                — hiç sıcaklık girdisi yok, termal
    //                                  etki KAPALI (iki cidar da ortam)
    const WALL_TEMP_SOURCE_KIND = {
        heat_transfer_module: 'ok',
        chamber_temperature_estimate: 'warn',
        not_evaluated: 'warn',
    };

    function wallTemperatureBlock(th) {
        if (!th || typeof th !== 'object') return '';
        const src = th.wall_temperature_source;
        if (src == null && th.wall_temperature_inner_K == null) return '';
        const ran = th.thermal_model_ran !== false && src !== 'not_evaluated';
        const LABELS = {
            heat_transfer_module: T('panel.structural.wallTempSolved',
                'WALL TEMPERATURE: SOLVED (heat-transfer module)'),
            chamber_temperature_estimate: T('panel.structural.wallTempEstimated',
                'WALL TEMPERATURE: ESTIMATED FROM GAS TEMPERATURE'),
            not_evaluated: T('panel.structural.wallTempNotEvaluated',
                'WALL TEMPERATURE: NOT EVALUATED (thermal path did not run)'),
        };
        let html = U.sectionTitle(T('panel.structural.secWallTemperature',
                                    'Wall temperature behind the thermal terms'));
        html += `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:6px 0;">`
            + U.badge(LABELS[src] || (T('panel.structural.wallTempSourceLabel',
                                        'WALL TEMPERATURE SOURCE') + ': '
                                      + String(src == null ? '—' : src)),
                      WALL_TEMP_SOURCE_KIND[src] || 'info')
            + '</div>';
        // Hesaplanmamış sıcaklık YAYIMLANMAZ: uç bu durumda alanları
        // None'a çekiyor, panel de sayı yerine gerekçeyi basar.
        if (ran) {
            html += U.kvTable([
                [T('panel.structural.wallTempHot', 'Hot-side (inner) wall'),
                 U.fmt(th.wall_temperature_inner_K, 1) + ' K'],
                [T('panel.structural.wallTempCold', 'Cold-side (outer) wall'),
                 U.fmt(th.wall_temperature_outer_K, 1) + ' K'],
                [T('panel.structural.wallTempDelta', 'Through-wall gradient ΔT'),
                 U.fmt(th.wall_delta_T_K, 1) + ' K'],
            ]);
            // V3 yapi-sf 2. tur Ş3: yukarıdaki ΔT sıcaklıkların HESAPLANDIĞI
            // cidara aittir; ısıl hoop gerilmesini süren ΔT DEĞERLENDİRİLEN
            // cidardakidir (boyutlandırma kipinde sabit akıyla ölçeklenir).
            // İki cidar ve iki ΔT ayrı satırda, ucun yayımladığı sayıyla.
            const ekSatir = [];
            if (isNum(th.thermal_reference_wall_thickness_mm)) {
                ekSatir.push([T('panel.structural.wallTempRefWall',
                    'Wall the temperatures and ΔT above were computed on'),
                    numL(th.thermal_reference_wall_thickness_mm, 3) + ' mm']);
            }
            if (isNum(th.evaluated_wall_thickness_mm)
                    && isNum(th.wall_delta_T_at_evaluated_wall_K)) {
                ekSatir.push([T('panel.structural.wallTempDeltaEvaluated',
                    'ΔT on the evaluated wall (drives the thermal hoop stress)'),
                    numL(th.wall_delta_T_at_evaluated_wall_K, 1) + ' K · '
                    + numL(th.evaluated_wall_thickness_mm, 3) + ' mm']);
            }
            if (ekSatir.length) html += U.kvTable(ekSatir);
        }
        // Sunucunun kendi gerekçe metni ham basılır (designBasisBlock deseni).
        const note = th.basis || th.service_temperature_basis;
        if (note) {
            html += `<p style="font-size:0.78rem; color:${U.kindColor(
                ran ? 'info' : 'warn')};">${SRV(note)}</p>`;
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
        // P11B4-05 — KAZANILMAMIŞ "BUCKLING: SAFE" YEŞİLİ
        // --------------------------------------------------------------
        // Ölçülen (b4_ONCE.json): panel varsayılanlarıyla (itki alanı 0)
        // uç `buckling_status: "SAFE"` diyor ama
        // `axial_buckling_safety_factor: null`,
        // `applied_axial_stress_MPa: 0.0`,
        // `axial_compression_force_N: 0.0`,
        // `governing_load_case: "unpressurized"`.
        // Yani hesap hiç eksenel yük GÖRMEDİ; "SAFE" bir ölçüm değil,
        // yükün yokluğudur. Ekranda YEŞİL rozet + "Buckling safety
        // factor —" duruyordu; kullanıcı bunu ancak bir em tireden
        // anlayabiliyordu.
        // Fail-closed: emniyet katsayısı yayımlanmamışsa hüküm KAZANILMADI
        // — rozet yeşil olamaz, nötr (`info`) basılır ve YANINA ucun kendi
        // alan adı konur ki durumun neden hükümsüz olduğu okunsun.
        const bstat = onayGeriCek(
            String(buck.buckling_status || 'UNKNOWN').toUpperCase());
        const bSf = buck.axial_buckling_safety_factor;
        const bKazanildi = isNum(bSf);
        badges += U.badge(T('panel.structural.badgeBuckling', 'BUCKLING') + ': ' + bstat,
                          bKazanildi ? statusKind(bstat) : 'info',
                          SRV(buck.source || ''));
        if (!bKazanildi) {
            badges += U.badge('axial_buckling_safety_factor: null', 'info',
                SRV(buck.applied_axial_stress_pressurized_basis || ''));
        }
        if (sf.status) {
            badges += U.badge(T('panel.structural.badgeStructure', 'STRUCTURE') + ': '
                + onayGeriCek(sf.status),
                statusKind(onayGeriCek(sf.status)),
                U.tf('panel.structural.verdictTip', { sf: U.fmt(sf.minimum_safety_factor) },
                     'Overall structural verdict (min SF = {sf})'));
        }
        if (sf.risk_level) {
            let rk = String(sf.risk_level).toUpperCase();
            // 5. tur: düşük risk bir onaydır; bayrak TRUE iken geri çekilir.
            if (motorGecerlilikDisi() && riskKind(rk) === 'ok') {
                rk = HUKUM_GERI_CEKILDI;
            }
            // P11B4-07: renk TEK kapıdan (riskKind) — durum rozetiyle
            // aynı olgu aynı rengi alır.
            badges += U.badge(T('common.risk', 'RISK') + ': ' + rk,
                riskKind(rk));
        }
        if (fat.fatigue_status) {
            badges += U.badge(T('panel.structural.badgeFatigue', 'FATIGUE') + ': '
                              + onayGeriCek(fat.fatigue_status),
                              statusKind(onayGeriCek(fat.fatigue_status)));
        }
        if (dp.material) {
            badges += U.badge(T('common.material', 'MATERIAL') + ': '
                + String(dp.material).toUpperCase(), 'info',
                U.tf('panel.structural.designPressureTip',
                     { p: U.fmt(dp.design_pressure, 1), f: U.fmt(dp.design_pressure_factor, 2) },
                     'Design pressure {p} bar (factor {f})'));
        }

        let html = `<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">${badges}</div>`;

        // ---- V3 yapi-sf 2. tur (C): model geçerlilik satırı (rozetlerin
        // hemen ardında: sayılar okunmadan önce tanı amaçlı oldukları
        // görülmeli) ----
        html += modelValidityBlock(ca);
        // 5. tur: motorun KENDİ cidarının geçerlilik bayrağı (fromResults).
        html += motorValidityBlock();

        // ---- Hükmün dayanağı (rozetlerin HEMEN ardında: kullanıcı sayıları
        // okumadan önce bunun doğrulama mı öneri mi olduğunu görmeli) ----
        html += designBasisBlock(data.design_basis, ca, sf);

        // ---- ÖH D21 / P5B1-10: DOLDURULAN AMA HESABA GİRMEYEN ALANLAR ----
        // Uç `inputs_not_consumed` bloğunu yayımlıyor: kapıdan geçmek
        // ZORUNDA olan ama yapısal modele HİÇ ulaşmayan alanlar (bugün
        // yalnız `burn_time`). Beyan ekrana inmezse kullanıcı doldurduğu
        // sayının sonucu değiştirdiğini sanmaya devam eder — bu paketin
        // kendi kuralı (ters yön sözleşmesi): yayımlanan dürüstlük alanı
        // panelde geçmek zorundadır. Sunucunun gerekçesi serverText'ten
        // geçer (TR karşılığı varsa Türkçe, yoksa AYNEN; V3 KK 3. tur).
        const notConsumed = data.inputs_not_consumed;
        if (notConsumed && typeof notConsumed === 'object'
                && Object.keys(notConsumed).length) {
            html += U.kvTable(Object.keys(notConsumed).sort().map(function (k) {
                const ham = notConsumed[k] || {};
                // Gerekçe SRV'den geçer; kaçış aşağıda aynen (SG-05 deseni).
                const rec = { reason: SRV(ham.reason || '') };
                return [U.esc(k),
                    `<span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono); font-size:0.75rem;"
                     >${U.esc(T('panel.structural.notConsumed',
                         'not consumed by this analysis'))}</span>
                     <span style="color:var(--hd-ink-dim, #7d97a5);
                      font-size:0.72rem;"> · ${U.esc(rec.reason || '')}</span>`];
            }));
        }

        // ---- ÖH D22 / P5B1-18: KULLANICININ VERMEDİĞİ GİRDİLER ----------
        // Uç `inputs_defaulted` bloğunu yayımlıyor: çağıranın GÖNDERMEDİĞİ
        // ve modülün kendi belgelenmiş varsayılanını uyguladığı alanlar
        // (değer + birim + gerekçe). ÖLÇÜLDÜ (once.json P5B1-16_18): boş
        // sözlükten tam bir sayı takımı çıkıyordu (30,0 bar tasarım
        // basıncı, 95,5416 MPa hoop, 2,7278 kg ağırlık) ve hangi girdinin
        // varsayılandan geldiğini söyleyen tek bir alan yoktu. Beyan ekrana
        // inmezse kullanıcı o sayıları KENDİ motorunun sayıları sanır.
        // Sunucunun İngilizce gerekçesi AYNEN basılır (yeni i18n anahtarı
        // üretilmez, metin uydurulmaz).
        const defaulted = data.inputs_defaulted;
        if (defaulted && typeof defaulted === 'object'
                && Object.keys(defaulted).length) {
            html += U.kvTable(Object.keys(defaulted).sort().map(function (k) {
                const rec = defaulted[k] || {};
                const birim = rec.unit ? ' ' + String(rec.unit) : '';
                return [U.esc(k),
                    `<span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono); font-size:0.75rem;"
                     >${U.esc(rec.value)}${U.esc(birim)} · ${U.esc(T(
                         'panel.structural.defaultNotSupplied',
                         'default (not supplied)'))}</span>
                     <span style="color:var(--hd-ink-dim, #7d97a5);
                      font-size:0.72rem;"> · ${U.esc(rec.reason || '')}</span>`];
            }));
            if (data.inputs_defaulted_basis) {
                html += `<p style="font-size:0.72rem;
                  color:var(--hd-ink-dim, #7d97a5);"
                  >${String(data.inputs_defaulted_basis)}</p>`;
            }
        }

        /* ---- ÖH D26 / OH-B3-03: `defaults_applied` (Z5/Z7 UI yarısı) ----
           ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``:
           panel_defaults_applied_okumasi = 0): uç bu listeyi
           ``/analyze_structural_safety`` yanıtının ÜST katında
           yayımlıyordu (bugün ``material``; kardeş ``/analyze_safety``
           ile aynı kanal) ve panel adı bir kez bile anmıyordu. Sonuç:
           kullanıcı hangi sayıyı KENDİSİNİN verdiğini ekrandan
           göremiyordu — Z7'nin "141 varsayılanlı okuma" ayağının arayüz
           yarısı buydu. `tests/test_wave3_contract.py` bu borcu
           ``'structural/ust'`` altında xfail(strict) borç imiyle
           taşıyordu; im bu onarımla KALDIRILDI.

           `inputs_defaulted` (değer+birim+gerekçe sözlüğü) ile AYNI ŞEY
           DEĞİLDİR: bu liste ÇIPLAK ALAN ADLARIDIR ve ucun iki kanalı
           birbirini kapsamaz — biri boşken diğeri dolu olabilir. Boş
           liste de ANLAMLIDIR ("hiçbir varsayılan uygulanmadı"), ama
           sessiz kalmasın diye yalnız dolu olduğunda satır açılır;
           boşluğun kendisi aşağıdaki künye cümlesiyle söylenir. */
        const defApplied = data.defaults_applied;
        if (Array.isArray(defApplied) && defApplied.length) {
            html += U.kvTable(defApplied.slice().sort().map(function (ad) {
                return [String(ad),
                    `<span style="color:${U.kindColor('warn')};
                     font-family:var(--hd-mono); font-size:0.75rem;"
                     >default applied (you did not supply this field)</span>`];
            }));
            html += `<p style="font-size:0.72rem;
              color:var(--hd-ink-dim, #7d97a5);">${
                T('panel.structural.defaultsApplied',
                  'The endpoint published these fields as defaulted: the '
                  + 'number used is the module\'s own documented default, '
                  + 'not a value you supplied.')}</p>`;
        } else if (Array.isArray(defApplied)) {
            html += `<p style="font-size:0.72rem;
              color:var(--hd-ink-dim, #7d97a5);">${
                T('panel.structural.defaultsAppliedNone',
                  'defaults_applied: none — every field this analysis '
                  + 'consumed came from your input.')}</p>`;
        }

        // ---- Cidar sıcaklığının kaynağı (termal terimlerin dayanağı) ----
        // Gerilme tablosundan ÖNCE: termal kolonun sayıları buradan türüyor.
        html += wallTemperatureBlock(sa.thermal_analysis);

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
        html += U.sectionTitle(T('panel.structural.secSafetyFactors', 'Safety Factors')
            + (motorGecerlilikDisi()
                ? ' · ' + T('panel.structural.diagnosticOnly', 'diagnostic only')
                : ''));
        html += safetyFactorTable(ca, sf, required, sa, data.design_basis);

        // ---- Cidar kalınlığı ----
        // ÖH D15 / P11B4-31 — ANALİZİ SÜREN CİDAR EKRANDA YOKTU.
        // ÖLÇÜLDÜ (once.json, gerçek /analyze_structural_safety,
        // wall_thickness = 0,005 m): yükte `chamber_analysis
        // .wall_thickness_used_mm = 5,0` ve `wall_thickness_source =
        // "user_supplied"` duruyor; bölüm ise yalnız "Minimum required
        // 2.62 mm / Recommended (with margin) 3.14 mm" basıyordu — "5.00 mm"
        // ekran metninde 0 kez geçiyordu. Gerilmelerin, emniyet
        // katsayılarının ve burkulmanın tamamı 5,00 mm'den çıktığı hâlde
        // ekrandaki tek cidar çifti tasarım ÖNERİSİdir; üstteki yeşil
        // "WALL: AS SUPPLIED" rozetiyle birlikte okununca kullanılan cidar
        // gibi duruyordu.
        //
        // Onarım: KULLANILAN cidar bölümün İLK satırı olur, makine alan
        // adıyla (yeni çeviri anahtarı açılmadı) ve ucun kendi kaynak
        // beyanıyla. Alan yoksa satır HİÇ çıkmaz (fail-closed); öneri
        // satırları da yalnız kendi alanları varsa basılır.
        const usedWallMm = isNum(ca.wall_thickness_used_mm)
            ? ca.wall_thickness_used_mm : null;
        if (ca.minimum_thickness != null || ca.recommended_thickness != null
                || usedWallMm !== null) {
            html += U.sectionTitle(T('panel.structural.secThickness', 'Wall Thickness'));
            const thRows = [];
            if (usedWallMm !== null) {
                thRows.push(['<span style="font-family:var(--hd-mono);'
                    + ' font-size:0.72rem;">wall_thickness_used_mm</span>',
                    '<strong>' + U.fmt(usedWallMm, 2) + ' mm</strong>'
                    + (ca.wall_thickness_source
                        ? ' <span style="font-family:var(--hd-mono);'
                          + ' font-size:0.68rem; color:var(--hd-ink-dim, #7d97a5);">'
                          + 'wall_thickness_source: '
                          + String(ca.wall_thickness_source) + '</span>'
                        : '')]);
            }
            if (ca.minimum_thickness != null) {
                thRows.push([T('panel.structural.minRequired', 'Minimum required'),
                    U.fmt(ca.minimum_thickness) + ' mm']);
            }
            if (ca.recommended_thickness != null) {
                thRows.push([T('panel.structural.recommendedMargin', 'Recommended (with margin)'),
                    U.fmt(ca.recommended_thickness) + ' mm']);
            }
            html += U.kvTable(thRows);
        }

        // ---- Burkulma ----
        html += U.sectionTitle(T('panel.structural.secBuckling', 'Buckling (NASA SP-8007)'));
        // P11B4-05: uç 19 burkulma alanı yayımlıyor, panel 6'sını
        // basıyordu. Aşağıdaki satırlar YÜKÜN HANGİ DURUMDA OLDUĞUNU
        // söyleyen alanlardır — hepsi ucun kendi sayısı, hiçbiri
        // hesaplanmaz; alan yoksa satır HİÇ çıkmaz (fail-closed).
        // Etiketler makine alan adıdır: yeni çeviri anahtarı açılmadı.
        const buckRows = [
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
        ];
        function buckRow(alan, deger, birim) {
            if (deger == null) return;
            buckRows.push([machineLabel(alan),
                isNum(deger) ? (U.fmt(deger, 2) + (birim ? ' ' + birim : ''))
                             : String(deger)]);
        }
        buckRow('governing_load_case', buck.governing_load_case);
        buckRow('axial_compression_force_N', buck.axial_compression_force_N, 'N');
        buckRow('pressure_stabilizing_stress_MPa',
                buck.pressure_stabilizing_stress_MPa, 'MPa');
        buckRow('stabilizing_pressure_bar', buck.stabilizing_pressure_bar, 'bar');
        buckRow('applied_axial_stress_unpressurized_MPa',
                buck.applied_axial_stress_unpressurized_MPa, 'MPa');
        buckRow('applied_axial_stress_pressurized_MPa',
                buck.applied_axial_stress_pressurized_MPa, 'MPa');
        buckRow('length_over_radius', buck.length_over_radius);
        buckRow('classical_axial_buckling_stress_MPa',
                buck.classical_axial_buckling_stress_MPa, 'MPa');
        buckRow('external_pressure_model', buck.external_pressure_model);
        html += U.kvTable(buckRows);
        // Ucun kendi 300+ karakterlik gerekçesi: "0 tam olarak sıfırdır,
        // eksik model değil" cümlesi ekrana hiç çıkmıyordu.
        if (buck.applied_axial_stress_pressurized_basis) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);">
                <span style="font-family:var(--hd-mono);"
                    >applied_axial_stress_pressurized_basis</span>:
                ${SRV(buck.applied_axial_stress_pressurized_basis)}</p>`;
        }
        if (buck.source) {
            html += `<p style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);">
                ${T('common.source', 'Source')}: ${SRV(buck.source)}</p>`;
        }

        // ---- Yorulma ----
        html += U.sectionTitle(T('panel.structural.secFatigue', 'Fatigue'));
        html += U.kvTable([
            [T('common.status', 'Status'),
             U.badge(onayGeriCek(fat.fatigue_status) || '—',
                     statusKind(onayGeriCek(fat.fatigue_status)))],
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
        // ---- ÖH D23 / OH-D18-10 (ayak-3): İKİ KAPAK TİPİNİN AYRI HÜKMÜ --
        // ÖLÇÜLDÜ (once.json OH-D18-10): üretici (structural_analysis.py,
        // P9B1-17) `head_stress_by_type_MPa` + `head_safety_factor_by_type`
        // + `_basis` yayımlıyor; panelde grep 0 idi. Panel yalnız
        // `head_safety_factor`ı basıyordu — o da YALNIZ `recommended_type`
        // için geçerlidir. İmalatta öteki tip çiziliyorsa (ihraç katmanı
        // DÜZ kapak modelliyor) kullanıcı ekranda yanlış tipin hükmünü
        // okuyordu. Sayı türetilmez: ucun kendi sözlüğü basılır, gerekçe
        // cümlesi de ucun kendi `_basis` alanıdır (SRV kanalı).
        const sfTip = cap.head_safety_factor_by_type;
        const stressTip = cap.head_stress_by_type_MPa;
        if (sfTip && typeof sfTip === 'object') {
            const onerilen = String(cap.recommended_type || '').toLowerCase();
            const tipSatirlari = Object.keys(sfTip).map(function (tip) {
                const etiket = tip.toUpperCase()
                    + (tip.toLowerCase() === onerilen
                        ? ' · recommended_type' : '');
                const gerilme = (stressTip && isNum(stressTip[tip]))
                    ? ` <span style="color:var(--hd-ink-dim, #7d97a5);
                         font-family:var(--hd-mono); font-size:0.72rem;"
                         >head_stress_by_type_MPa: ${U.fmt(stressTip[tip])} MPa</span>`
                    : '';
                return [etiket,
                        (isNum(sfTip[tip]) ? sfCell(sfTip[tip], required) : '—')
                        + gerilme,
                        SRV(cap.head_safety_factor_by_type_basis || '')];
            });
            if (tipSatirlari.length) {
                html += `<p style="font-size:0.78rem;
                     color:var(--hd-ink-dim, #7d97a5); margin:6px 0 2px;">
                     ${T('panel.structural.headSfByType',
                         'Head safety factor by cap type')}
                     <span style="font-family:var(--hd-mono);"
                      >head_safety_factor_by_type</span></p>`;
                html += U.kvTable(tipSatirlari);
            }
        }
        /* ÖH D26 · P11B4-01 — HER KOŞUMDA BİR UYARI YUTULUYORDU.

           ÖLÇÜLDÜ (a3/once.json, taban 7751531):
             sunucu_fasteners_warning  = 1   (TEKİL 'warning')
             sunucu_fasteners_warnings = 1   (ÇOĞUL 'warnings')
             panel_fast_warning  = 2 · panel_fast_warnings = 0
           Uç `fastener_analysis` bloğunda İKİ kanal yayımlıyor: tekil
           `warning` (yalnız standart dışı cıvata çapı gerektiğinde dolar)
           ve çoğul `warnings` (HER koşumda dolu —
           `warn.structural.fastener_preload_not_modeled`). Panel yalnız
           tekilini okuyordu, yani ön-yük fiziğinin MODELLENMEDİĞİ uyarısı
           — ki asıl kritik ölçüt AYRILMA'dır ve burada hiç
           denetlenmiyor — hiçbir koşumda ekrana çıkmıyordu.

           İki kanal birleştirilir (sıra: tekil önce, ucun kendi sırası
           korunur); ikisi de boşsa blok basılmaz. */
        const fastUyarilar = (fast.warning ? [fast.warning] : [])
            .concat(Array.isArray(fast.warnings) ? fast.warnings : []);
        if (fastUyarilar.length) {
            html += U.listBlock(T('panel.structural.fastenerWarning', 'Fastener Warning'),
                                fastUyarilar, 'warn');
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

        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, sa, { deep: true });
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
            ['burn_time', 'Burn Time (s)', '', 0.5, 'common.f.burnTimeS'], // OH-D37-S6: süre uydurulmaz — boşsa gövdeye girmez (safety_panel.js deseni)
            // GAZ SICAKLIĞI (ÖH D15 birleştirme ölçümü, 1 Eyl 2026): bu alanın
            // varsayılanı 0 İDİ ve etiketi "0 = skip thermal" diyordu. Yapısal
            // kulvarın sıcaklık kapısı (app.py `_STRUCTURAL_TEMPERATURE_FIELDS`,
            // P5B1-19) birleştikten sonra ÖLÇÜLDÜ: panelin KENDİ varsayılan
            // yükü — analysis_dock buildPayload sonlu her varsayılanı gönderir,
            // 0 da sonludur — ucu 422 `invalid_structural_input`
            // (`chamber_temperature: must_be_positive`) ile geri çeviriyordu.
            // Yani kullanıcı paneli açıp hiçbir şeye dokunmadan Run'a bastığında
            // hüküm değil hata alıyordu.
            //
            // Kapı GEVŞETİLMEZ: 0 K mutlak sıcaklıkta FİZİKSEL bir değerdir ve
            // `hrma/utils/input_guard.py`'nin ilkesi ("0 ile 'verilmedi' ASLA
            // karıştırılmaz") burada geçerlidir; kapı 1e9 K / -500 K / 50000 K
            // için kazanılmış hükmünü aynen korur. Doğru desen bu listenin
            // ALTINDA zaten yazılı: cidar sıcaklığı çifti tam bu gerekçeyle BOŞ
            // DİZE kullanıyor. Bu alan da ona hizalanır — boş alan payload'a
            // KONMAZ (buildPayload) ve alan sayısal varsayılan taşımadığı için
            // `requiredFieldInfo` onu isteğe bağlı sayar, istek durdurulmaz.
            //
            // Sentinel ANLAMI değişmez, taşıyıcısı değişir. Yeni varsayılanla
            // ölçüldü (aynı gövde, alan gönderilmeden): HTTP 200 ·
            // `thermal_analysis.status = NOT_MODELLED` · `basis = "Thermal path
            // not run: no gas or wall temperature supplied."` ·
            // `safety_analysis.thermal_margin_ratio = None` — yani termal yol
            // eskisi gibi ATLANIR, uydurma bir termal hüküm üretilmez.
            ['chamber_temperature', 'Gas Temperature (K, blank = skip thermal)',
             '', 50, 'common.f.gasTemperatureBlank'],
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
            // CİDAR SICAKLIĞI (F5-2, 2026-08-17 ölçümü): bu iki alan da
            // listede YOKTU. Uç ikisini de BİRİNCİ ÖNCELİKLE okuyor
            // (app.py `for wall_key in ('wall_temperature_hot',
            // 'wall_temperature_cold')`) ve yapısal modül onları
            // `_estimate_wall_delta_T`'de 1. sırada kullanıyor. Panel
            // göndermediği için ısı zincirinin ÇÖZDÜĞÜ cidar sıcaklığı
            // güverteye hiç ulaşmıyordu; uç gaz sıcaklığından türeyen
            // TAHMİN yoluna düşüyordu. Aynı örnek hibrit motorda ölçüldü:
            //     güverte  T_iç = 729,9 K   SF_min = 4,000  (MARGINAL)
            //     motor    T_iç = 3369,3 K  SF_min = 2,134
            //
            // Varsayılan BOŞ dize ('') = isteğe bağlı alan sözleşmesi
            // (analysis_dock buildPayload: boş alan payload'a KONMAZ,
            // istek durdurulmaz). 0 varsayılanı KULLANILMAZ: mutlak
            // sıcaklıkta 0 K fiziksel bir değerdir, "verilmedi" ile
            // karıştırılamaz — `wall_thickness`/`thrust` alanlarındaki
            // "0 = atla" sözleşmesi burada geçerli DEĞİLDİR.
            //
            // Uydurma bir sıcaklık ENJEKTE EDİLMEZ: fromResults yalnız
            // çözücünün kendi beyanı "çözüldü / kullanıcı verdi" dediğinde
            // doldurur (bkz. AnalysisDock.ui.readWallTemperaturesK).
            ['wall_temperature_hot', 'Hot-side Wall Temperature (K, blank = '
             + 'let HRMA estimate from gas temperature)', '', 10,
             'common.f.wallTemperatureHotK'],
            ['wall_temperature_cold', 'Cold-side Wall Temperature (K, blank = '
             + 'let HRMA estimate from gas temperature)', '', 10,
             'common.f.wallTemperatureColdK'],
            // TASARIM EMNİYET KATSAYISI HEDEFİ (V3 KK, YP7 devri): bu alan
            // listede YOKTU; uç hedefi hep malzeme kaydının varsayılanından
            // alıyordu. Varsayılan BOŞ dize = isteğe bağlı (buildPayload boş
            // alanı göndermez, uç malzeme varsayılanına düşer ve bunu
            // design_safety_factor_source ile beyan eder). fromResults
            // motorun KENDİ hedefini doldurur (readMotorSfTarget).
            ['safety_factor', 'Design Safety Factor target (blank = material '
             + 'database default)', '', 0.1, 'common.f.designSafetyFactorTarget'],
            ['material', 'Material', 'steel_4130', MATERIALS, 'common.f.material'],
        ],
        fromResults: function (r) {
            const m = U.motorDict(r);
            // P17B3-06: motor hesabının KENDİ asgari emniyet katsayısı
            // burada saklanır (güverte her hesap sonrası bu kancayı
            // çağırır). Panel kendi koşumunu çizerken o sayıyı yanına
            // basar; sonuç yoksa null kalır ve kıyas satırı basılmaz.
            motorSolve = readMotorSolve(r);
            // V3 KK: motorun KENDİ tasarım emniyet katsayısı hedefi (tek
            // kaynak: motor yanıtının hedef alanı); yoksa null.
            motorSfTarget = readMotorSfTarget(r);
            // Cidar sıcaklığı çifti: yalnız çözücünün kendi kaynak beyanı
            // "çözüldü / kullanıcı verdi" dediğinde gelir; aksi hâlde boş
            // sözlüktür ve iki alan BOŞ kalır (tahmin geri beslenmez).
            const wt = U.readWallTemperaturesK(r);
            // 5. tur: motor künye bloğunun geçerlilik bayrağı (her hesapta
            // tazelenir; bayrak yoksa/FALSE ise null → eski davranış).
            // Motorun çözülmüş cidar sıcaklığı uca GİDİYORSA (hibrit:
            // heat_transfer_module) uç aynı ölçütü o sıcaklıkta KENDİSİ
            // uygular (yanıtta kendi bayrağı ve tanı gerekçesi); panel ikinci
            // kez karışmaz. Kusur yalnız sıcaklıksız gönderimde (katı, sıvı).
            motorValidity = (isNum(wt.hot) && isNum(wt.cold))
                ? null : readMotorValidity(r);
            // Z5-C1: cidar önerisi + künyesi (aşağıdaki `wallSuggestion`).
            const wallM = wallThicknessSuggestion(r);
            // BİRİM (2026-07-30 ölçümü): bu üç uzunluk HAM okunuyordu ve
            // alanlar METRE etiketli. Hibritte doğruydu, ama katı motorda
            // chamber_diameter 75,0 (mm) ve sıvıda 120,0 (mm) geliyor —
            // panel bunları 75 m ve 120 m sanıyordu. Merkezi çözümleyici
            // motor tipine göre metreye getiriyor.
            const out = {
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
                // CİDAR: çözücünün kullandığı kalınlık (METRE) — ama artık
                // KÜNYESİYLE. Z5-C1: yalnız motorun kendi beyanı "kullanıcının
                // cidarı sınandı" (design_mode: verify) dediğinde doldurulur;
                // HRMA'nın kendi boyutlandırdığı cidar uca GÖNDERİLMEZ, alan
                // "sen boyutlandır" nöbetçisine çekilir (gerekçe künyede).
                // Gerekçe: yukarıdaki wallThicknessSuggestion açıklaması.
                wall_thickness: wallM,
                // CİDAR SICAKLIĞI ÇİFTİ — ikisi birlikte gelir ya da hiç
                // gelmez (yapısal modül tek başına gelen sıcaklığı zaten
                // kullanamıyor, ama uç 'termal koştu' bayrağını kaldırırdı).
                wall_temperature_hot: wt.hot,
                wall_temperature_cold: wt.cold,
                // TASARIM EMNİYET KATSAYISI HEDEFİ: motorun kendi hedefi;
                // yayımlamadıysa null (alan boş kalır, uç malzeme
                // varsayılanını adıyla beyan eder).
                safety_factor: motorSfTarget ? motorSfTarget.value : null,
            };
            // Geri çekme künyesi: alanın DEĞERİ sayı kalır (nöbetçi), ama
            // güverte onu "hesaptan geldi" diye imlemez ve gerekçeyi kaynak
            // çipinin ipucuna basar. Öneri gerçekten uygulandıysa künye
            // sözlüğü HİÇ konmaz.
            const gerekce = {};
            if (wallSuggestion && wallSuggestion.withheld) {
                gerekce.wall_thickness = wallSuggestion.reason;
            }
            // V3 KK: hedef taşınamadıysa kaynak çipi nedenini söyler.
            if (!motorSfTarget) gerekce.safety_factor = MOTOR_SF_TARGET_ABSENT;
            if (Object.keys(gerekce).length) out[U.WITHHELD_KEY] = gerekce;
            return out;
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

    // Test / hata ayıklama: saf render (dry-run) — injector_panel deseni.
    // P11B4-07 / P11B4-08 bekçileri renk kapılarını DOM'suz ölçer
    // (fea_panel `_fieldFigure` deseniyle aynı saf katman yüzeyi).
    window.StructuralPanel = {
        _render: render,
        _sfKind: sfKind,
        _riskKind: riskKind,
        _statusKind: statusKind,
        _SF_RENK_BAGIL_TOLERANS: SF_RENK_BAGIL_TOLERANS,
    };
})();
