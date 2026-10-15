/* ====================================================================
   HRMA Analiz Güvertesi — Termal Koruma Paneli (Dalga 3)
   --------------------------------------------------------------------
   POST /api/thermal-protection sonucunu çizer (thermal_panel'in yanında,
   THERMAL sekmesinde İKİNCİ panel — dock aynı kategoride panelleri alt
   alta gösterir):
   - Mode: ablative (Q* boyutlandırma) / heat_sink (1-D transient) /
     radiation_equilibrium (radyasyon-soğutmalı uzantı)
   - Ablatif: gereken kalınlık, gerileme hızı, Q* bandı
   - Heat-sink: T(x) Plotly çizgisi + T_w(t) geçmişi, time_to_limit
   - Radyasyon: denge cidar sıcaklığı, servis limiti marjı
   - Her modda 'SIMPLIFIED MODEL' rozeti (backend model_note alanı)
   Alan etiketleri [A]/[H]/[R] önekiyle hangi moda ait olduğunu söyler;
   backend beyaz listesi (app.py) hedef modun kullanmadığı alanları düşürür.
   Backend: hrma/analysis/thermal_protection.py (NASA SP-8093 sınıfı Q*,
   Incropera explicit FD, Sutton & Biblarz Ch. 8).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    var U = window.AnalysisDock.ui;
    var T = U.t;                         // çeviri kısayolu

    var MODES = [
        ['ablative', 'Ablative liner (Q*)', 'tps.modeAblative'],
        ['heat_sink', 'Heat-sink wall (1-D)', 'tps.modeHeatSink'],
        ['radiation_equilibrium', 'Radiative extension', 'tps.modeRadiation'],
    ];

    // FALLBACK — thermal_protection.py ABLATIVE_MATERIALS anahtarlarıyla
    // birebir; katalog gelirse 'ablative' etiketli DB kayıtlarıyla
    // BİRLEŞTİRİLİR (carbon_phenolic/epdm modele özgüdür, listede kalır)
    var ABLATIVES = [
        ['silica_phenolic', 'Silica-phenolic', 'tps.silicaPhenolic'],
        ['carbon_phenolic', 'Carbon-phenolic', 'tps.carbonPhenolic'],
        ['epdm', 'EPDM insulation', 'tps.epdm'],
    ];

    // FALLBACK — materials_db anahtarları (heat-sink metal cidar);
    // katalog gelirse 'shell'+'liner' etiketli tam liste bunun yerine geçer
    var WALL_MATERIALS = [
        ['steel', 'Steel (generic)', 'mat.steelGeneric'],
        ['steel_4130', 'Steel AISI 4130', 'mat.steelAisi4130'],
        ['ss_304', 'Stainless 304', 'mat.stainless304'],
        ['ss_316', 'Stainless 316', 'mat.stainless316'],
        ['aluminum_6061', 'Aluminum 6061-T6', 'mat.aluminum6061'],
        ['copper', 'Copper (OFHC)', 'mat.copperOfhc'],
        ['cucrzr', 'CuCrZr'],
        ['inconel_718', 'Inconel 718'],
        ['titanium_6al4v', 'Titanium Ti-6Al-4V', 'mat.titanium6al4v'],
        ['graphite', 'Graphite', 'mat.graphite'],
    ];

    // FALLBACK — thermal_protection.py RADIATION_EXTENSION_MATERIALS +
    // merkezi DB; katalog gelirse 'radiative' etiketli liste bunun yerine geçer
    var RAD_MATERIALS = [
        ['niobium_c103', 'Nb C-103 (silicide)', 'tps.niobium'],
        ['carbon_carbon', 'Carbon-carbon (C-C)', 'tps.carbonCarbon'],
        ['ss_316', 'Stainless 316', 'mat.stainless316'],
        ['inconel_718', 'Inconel 718'],
    ];

    // ==================================================================
    // B5 (ÖH defter P17B3-02) — AKI MOTORUN KENDİ ÖLÇÜMÜNDEN GELİR
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (2026-08-27, üç örnek proje + app.test_client):
    //   hibrit : motor.heat_transfer_analysis.gas_side_analysis.heat_flux
    //            = 26 297 815,58 W/m²   -> `fromResults` BULUYOR
    //   katı   : aynı yol YOK -> öneri yalnız `burn_time_s`
    //   sıvı   : aynı yol YOK -> öneri yalnız `burn_time_s`
    // Yani katı ve sıvıda alan panelin 2 000 000 W/m² VARSAYILANINDA
    // kalıyor ve uç İKİ FARKLI MOTOR için birebir aynı hükmü basıyordu:
    //   q = 2,0 MW/m²  ->  required_thickness_mm = 2,6786 (ikisinde de)
    // Oysa iki motor da ölçülmüş akısını YAYIMLIYOR:
    //   katı  thermal_analysis.heat_transfer.convective_heat_flux_kw_m2
    //         = 16 380,976 kW/m² (16,38 MW/m²) -> 5,0967 mm
    //   sıvı  cooling_system.peak_heat_flux
    //         = 52 145,527 kW/m² (52,15 MW/m²) -> 2095,13 mm
    // (Sıvının sayısı REJENERATİF tasarım yükü olduğu için ablatif model
    // zarfının dışına çıkar; ucun kendi geçerlilik beyanları bunu söyler.
    // Panel sayıyı DEĞİŞTİRMEZ, yalnız nereden geldiğini beyan eder.)
    //
    // BİRİM TUZAĞI (ölçülerek doğrulandı): `cooling_system.*heat_flux`
    // kW/m², `thermal_protection.*heat_flux` ise MW/m² yayımlıyor (aynı
    // büyüklük, 1000 kat fark: 52 145,527 ⟷ 52,145527). Bu okuyucu
    // KW/M² yayımlayan alanları okur ve 1e3 ile W/m²'ye çevirir.
    //
    // HİBRİT YOLU DEĞİŞTİRİLMEDİ: aşağıdaki okuyucular yalnız hibrit yolu
    // sayı VERMEDİĞİNDE devreye girer (bit-aynı çapa koşumu raporda).
    // ==================================================================

    //: Ablatif akı alanının panel varsayılanı — TEK tanım noktası. Hem
    //: `fields` girdisi hem "hüküm kazanılmış mı" ölçütü buradan okur;
    //: iki yerde ayrı yazmak ölçütü sessizce kaydırırdı.
    var DEFAULT_Q_NET_W_M2 = 2000000;

    //: Son önerinin künyesi: hangi motor tipinde, hangi makine yolundan,
    //: hangi sayı okundu. `render` bunu ucun yankıladığı `q_caller_W_m2`
    //: ile karşılaştırıp hükmün kazanılmış olup olmadığını söyler.
    //: Uydurulmaz: yalnız `fromResults` gerçekten okuduğunda dolar.
    var lastFluxRead = null;

    function numOrNull(v) {
        return (typeof v === 'number' && Number.isFinite(v)) ? v : null;
    }

    //: TEK KAYNAK (ÖH D18 · P11S1-03 ŞART): "panelin okuduğu sayı ile
    //: koşumda kullanılan sayı aynı mı" ölçütü. `fluxProvenance` (akı) ve
    //: `fluxUsage` (h_gas / T_recovery çifti) AYNI göreli toleransı
    //: kullanır; eşiği iki yerde yazmak ölçütü sessizce kaydırırdı.
    var SAME_NUMBER_REL_TOL = 1e-6;

    //: `ref` panelin motordan OKUDUĞU sayı, `other` ucun yankıladığı
    //: (koşuma giren) sayı. Biri bile çözülemiyorsa EŞİT DEĞİLDİR —
    //: fail-closed: "bilinmiyor" asla "uyuşuyor" sayılmaz.
    function sameNumber(ref, other) {
        var a = numOrNull(ref);
        var b = numOrNull(other);
        if (a === null || b === null) return false;
        return Math.abs(a - b)
               <= SAME_NUMBER_REL_TOL * Math.max(1, Math.abs(a));
    }

    function pathGet(obj, path) {
        var cur = obj;
        var parts = path.split('.');
        for (var i = 0; i < parts.length; i++) {
            if (!cur || typeof cur !== 'object') return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    // Motor tipi -> ucun yayımladığı BOĞAZ/TEPE istasyonu (ablatif astar
    // en kötü istasyona göre boyutlanır). Karışık istasyon birleştirmesi
    // YOK: q, h_gas ve T_recovery aynı istasyondan okunur.
    var MEASURED_FLUX_PATHS = {
        solid: {
            q_kw_m2: 'thermal_analysis.heat_transfer.convective_heat_flux_kw_m2',
            h_gas: 'cad_design.insulation_system.aft_insulation.h_gas_W_m2K',
            t_recovery: 'cad_design.insulation_system.aft_insulation.T_recovery_K',
        },
        liquid: {
            q_kw_m2: 'cooling_system.peak_heat_flux',
            h_gas: 'cooling_system.bartz_coefficient',
            // Sıvı zincir bir toparlanma sıcaklığı YAYIMLAMIYOR (ölçüldü):
            // alan boş bırakılır, uydurulmaz.
            t_recovery: null,
        },
    };

    // Ölçülmüş akıyı (W/m²) + kardeşlerini okur. Yol yoksa null döner —
    // başka bir motor tipinin yolu DENENMEZ (yanlış motorun sayısını
    // basmak, varsayılanı basmaktan daha tehlikelidir).
    function readMeasuredFlux(m, motorType) {
        var spec = MEASURED_FLUX_PATHS[motorType];
        if (!spec) return null;
        var qkw = numOrNull(pathGet(m, spec.q_kw_m2));
        if (qkw === null) return null;
        return {
            motorType: motorType,
            q_W_m2: qkw * 1e3,
            q_path: spec.q_kw_m2,
            h_gas_W_m2K: spec.h_gas ? numOrNull(pathGet(m, spec.h_gas)) : null,
            T_recovery_K: spec.t_recovery
                ? numOrNull(pathGet(m, spec.t_recovery)) : null,
        };
    }

    //: Hükmün künyesi için satır etiketi (makine yolu — bu tur i18n
    //: anahtarı açılmaz; süpürme dalgası anahtarı bu ada takacak).
    var FLUX_BASIS_LABEL = 'q_net_W_m2 (used value provenance)';

    //: ÖH P11B5-02 — radyasyon hükmünün künye satırları. Aynı makine-yolu
    //: deseni (yukarıdaki FLUX_BASIS_LABEL emsali): bu tur i18n anahtarı
    //: AÇILMAZ, çünkü sözlük dosyaları (hrma/static/js/i18n_*.js) bu
    //: paketin mülkü değildir ve "sözlükte olmayan anahtar" bekçisi
    //: (tests/test_i18n_common.py::test_every_used_key_exists_in_dictionary)
    //: yeni anahtarı KIRMIZI yapar. Süpürme dalgası anahtarı bu adlara
    //: takacak; alanların ekrana İNMESİ bugünden kazanılır.
    var VERDICT_BASIS_LABEL = 'unconservative (verdict provenance)';
    var VIEW_FACTOR_LABEL = 'view_factor (surface to space)';
    var GAS_RAD_LABEL = 'q_gas_radiation_W_m2 (incident, input)';
    var VERDICT_EARNED_TEXT =
        'view_factor and q_gas_radiation_W_m2 were both supplied: no known '
        + 'omission pushes this equilibrium wall temperature down.';

    // Ucun yankıladığı akı ile panelin motordan okuduğu akıyı karşılaştırır.
    //   'measured' : sayı motorun ÖLÇÜLMÜŞ akısı (yolu beyan edilir)
    //   'user'     : ne ölçüm ne panel varsayılanı — elle girilmiş
    //   'default'  : ölçüm YOK ve sayı panelin kendi varsayılanı; hüküm
    //                KAZANILMAMIŞtır (P17B3-02'nin ta kendisi)
    function fluxProvenance(qUsed) {
        var read = lastFluxRead;
        if (numOrNull(qUsed) === null) {
            return { kind: 'missing', text: 'q_caller_W_m2 not published' };
        }
        if (read && sameNumber(read.q_W_m2, qUsed)) {
            return { kind: 'computed',
                     text: read.motorType + ' · ' + read.q_path
                           // ÖH D31 · OH-D30-06: biçim tek kaynaktan (I18N.number) — TR kipinde virgül.
                           + ' = ' + U.num(read.q_W_m2 / 1e6, 3) + ' MW/m2' };
        }
        if (Math.abs(qUsed - DEFAULT_Q_NET_W_M2) < 1e-9) {
            return { kind: 'assumed',
                     text: 'panel default ' + DEFAULT_Q_NET_W_M2
                           + ' W/m2 — no measured motor flux was read for '
                           + 'this run' };
        }
        return { kind: 'user', text: 'entered in the form (not this run\'s '
                                     + 'measured flux)' };
    }

    //: Formda GÖRÜNEN akı satırının etiketi. `FLUX_BASIS_LABEL` "kullanılan
    //: sayının künyesi"ni taşır; bu satır kullanıcının YAZDIĞI sayıyı ve o
    //: sayının koşuma girip girmediğini ayrı ayrı söyler.
    var CALLER_FLUX_LABEL = 'q_caller_W_m2 ([A] Net Heat Flux, as entered)';

    // ÖH D16 · P11S1-03 — HANGİ SAYI KULLANILDI?
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D16/arayuz/a1/once.json, M1): güvertenin
    // gönderdiği gövdede `h_gas_W_m2K` ve `T_recovery_K` HER koşumda dolu
    // (panel varsayılanları 3000 / 3200), dolayısıyla uç yüzey enerji
    // dengesi yolunu açıyor ve kullanıcının `[A] Net Heat Flux` alanına
    // yazdığı sayı HESABA HİÇ GİRMİYOR: 2 → 50 MW/m² (25×) süpürmesinde
    // `required_thickness_mm` altı koşumda da 3,413436612744386 ve
    // `recession_rate_mm_s` 0,22756244084962568 — ayrık değer sayısı 1.
    // Uç bunu `flux_basis` ile AÇIKÇA söylüyordu; panel bu alanı hiç
    // okumuyordu (kaynakta geçiş sayısı 0) ve üstelik "kullanılan sayının
    // künyesi" satırına kullanıcının YANKILANAN değerinin künyesini
    // ("entered in the form") basıyordu — koşuma girmemiş bir sayı hükmün
    // kaynağı gibi gösteriliyordu.
    //
    // Fail-closed sonuç: enerji dengesi yolunda hükmü taşıyan çift
    // (h_gas, T_recovery); o çift bu koşumda motordan OKUNMADIYSA sayı
    // kazanılmamıştır ve kart '—' basar. Eski yol (çift verilmemiş, akı
    // doğrudan kullanılmış) BİREBİR korunur — `flux_basis` o dalda
    // 'caller_supplied_no_energy_balance' gelir ve künye eskisi gibi
    // `fluxProvenance`ten okunur.
    //
    // ÖH D18 · P11S1-03 ŞART (Fable-D15/D16) — ÇİFTİN VARLIĞI DEĞİL,
    // AYNILIĞI ARANIR. ÖLÇÜLDÜ (`once_p11s1_03.json`, taban 9071a64):
    // güverte gövdesi ucun `h_gas_W_m2K`/`T_recovery_K` alanlarına KENDİ
    // varsayılanlarını (3000 / 3200) gönderiyor; panel ise KNDX katı
    // motorundan bambaşka bir çift okuyor (16293,32 W/m²K · 1705,38 K).
    // Eski ölçüt yalnız "okunan çift VAR mı" diye baktığı için künye
    // `computed` basılıyor, üstelik metin "both read from solid · …
    // station" diyordu: koşuma GİRMEMİŞ bir çift hükmün kaynağı gibi
    // gösteriliyor ve 3,41 mm kazanılmış sayı olarak yayımlanıyordu.
    //
    // Fail-closed ölçüt: hüküm ancak ucun YANKILADIĞI çift, panelin
    // motordan OKUDUĞU çiftle (aynı göreli tolerans, `sameNumber`)
    // örtüşürse kazanılır. Örtüşmüyorsa kullanılan çift kullanıcının
    // formundan gelmiştir → kind 'user', `earned:false` ('—').
    //: ÖH D24 · OH-D20-11 (Fable-D18 kısım-1) — YASAKLI LİSTE → İZİNLİ LİSTE.
    //: Eski ölçüt `p.kind !== 'assumed'` idi, yani `fluxProvenance`in DÖRT
    //: türünden üçü (`computed`, `user`, `missing`) kazanılmış sayılıyordu.
    //: `missing` = "`q_caller_W_m2` uçtan hiç yayımlanmadı"; hükmü taşıyan
    //: sayı BİLİNMİYORSA hüküm kazanılmamıştır. Bugün ulaşılamaz bir daldı
    //: (bu yolda alan her koşumda dolu geliyor) ama yasaklı liste,
    //: `fluxProvenance`e yarın eklenecek her yeni türü sessizce
    //: "kazanılmış" sayar — fail-open kalıntısı. İzinli liste tersini
    //: yapar: adı burada YAZMAYAN tür kazanılmaz. `computed` = bu koşumun
    //: ölçülen motor akısı; `user` = kullanıcının forma yazdığı ve BU
    //: yolda gerçekten kullanılan sayı.
    var EARNED_FLUX_KINDS = ['computed', 'user'];

    function fluxUsage(d) {
        var basis = (d && typeof d.flux_basis === 'string')
            ? d.flux_basis : null;
        if (basis !== 'surface_energy_balance') {
            var p = fluxProvenance(d && d.q_caller_W_m2);
            return { basis: basis, callerUsed: (basis ? true : null),
                     kind: p.kind, text: p.text, pairMatch: null,
                     earned: EARNED_FLUX_KINDS.indexOf(p.kind) !== -1 };
        }
        var read = lastFluxRead;
        var readPair = !!(read && numOrNull(read.h_gas_W_m2K) !== null
                          && numOrNull(read.T_recovery_K) !== null);
        //: Ucun yankıladığı (koşuma GİREN) çift. Uç bu iki alanı her iki
        //: yolda da yayımlar; yayımlamıyorsa çift doğrulanamaz ve hüküm
        //: kazanılmaz (fail-closed).
        var usedH = numOrNull(d && d.h_gas_W_m2K);
        var usedT = numOrNull(d && d.T_recovery_K);
        var pairMeasured = readPair
            && sameNumber(read.h_gas_W_m2K, usedH)
            && sameNumber(read.T_recovery_K, usedT);
        var ortak = 'surface_energy_balance — the entered net heat flux is '
            + 'NOT used; the flux is solved at the ablation surface '
            + 'from h_gas and T_recovery';
        if (pairMeasured) {
            return {
                basis: basis, callerUsed: false, kind: 'computed',
                pairMatch: true, earned: true,
                text: ortak + ' (both read from ' + read.motorType + ' · '
                      + read.q_path + ' station)',
            };
        }
        if (readPair) {
            //: Okunan çift VAR ama koşuma GİREN çift o değil: kullanılan
            //: sayılar formdan geldi. Künye bunu adıyla söyler.
            return {
                basis: basis, callerUsed: false, kind: 'user',
                pairMatch: false, earned: false,
                text: ortak + ' — but the pair sent to the endpoint ('
                      + 'h_gas=' + (usedH === null ? 'not published' : usedH)
                      + ', T_recovery='
                      + (usedT === null ? 'not published' : usedT)
                      + ') differs from the pair read from '
                      + read.motorType + ' · ' + read.q_path
                      + ' (h_gas=' + read.h_gas_W_m2K
                      + ', T_recovery=' + read.T_recovery_K
                      + '), so this verdict is not earned',
            };
        }
        return {
            basis: basis, callerUsed: false, kind: 'assumed',
            pairMatch: false, earned: false,
            text: ortak + ' (h_gas / T_recovery are the panel\'s own '
                  + 'defaults for this run — no measured motor pair was '
                  + 'read, so this verdict is not earned)',
        };
    }

    function simplifiedBadge(note) {
        return U.badge(T('panel.protection.simplified', 'SIMPLIFIED MODEL'), 'warn',
            note || T('panel.protection.simplifiedTip',
                      'Preliminary hand-calculation model — see assumptions.'));
    }

    // ==================================================================
    // ÖH D15 / P11B5-01 (kritik) — UCUN GEÇERLİLİK HÜKMÜ EKRANA İNER
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (2026-08-31, app.test_client + node içinde GERÇEK render,
    // `docs/scofield/raw/OH/D15/ui-paneller/a1/olc_b5_01.py`): uç
    // `/api/thermal-protection` zarf dışındaki koşumlarda
    // `model_valid:false` + `validity_note` yayımlıyor; ÖLÇÜLEN ÜÇ
    // vakanın ÜÇÜNDE de bu beyanın ekranda TEK BİR izi yoktu
    // (`model_valid` ve `validity_note` panel kaynağında hiç geçmiyordu).
    // Kullanıcı zarf dışı bir koşumun gerileme/cidar sayılarını, üstelik
    // her koşuda basılan (yani sıfır bilgi taşıyan) `SIMPLIFIED MODEL`
    // rozetinin altında, tasarım sayısı olarak okuyordu.
    //
    // FAIL-CLOSED: hüküm KAZANILMADIYSA sayı hüküm gibi basılmaz. Ablatif
    // kartlarda dosyanın kendi tescilli deseni uygulanır ('—' + beyan
    // çipi; bkz. `fluxProvenance` / `earned`), heat-sink'te sayı grafikle
    // birlikte kalır ama hükmün geçersizliği KIRMIZI rozetle ve ucun
    // KENDİ cümlesiyle görünür olur. Uydurma sayı, uydurma metin YOK:
    // ekrana çıkan her karakter yanıtın kendi alanından gelir.
    //
    // ETİKET: makine yolu deseni (emsal: FLUX_BASIS_LABEL) — bu tur i18n
    // anahtarı AÇILMAZ, süpürme dalgası bu ada takacak.
    // ==================================================================

    //: HTML kaçışı — ucun cümlesi ekrana HAM metin olarak girer
    //: (safety_panel.js::esc ile birebir; innerHTML'e gömülen sunucu
    //: metni kaçışsız bırakılmaz).
    function esc(x) {
        return String(x == null ? '' : x)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    //: Geçerlilik künyesinin satır etiketi — ucun alan adları.
    var VALIDITY_LABEL = 'model_valid / validity_note (endpoint verdict)';

    //: Model geçerli mi? YALNIZ ucun açık `false` hükmü geçersizdir;
    //: alan yoksa (eski/başka bir uç) hiçbir şey İDDİA EDİLMEZ.
    function modelInvalid(d) {
        return d && d.model_valid === false;
    }

    //: Zarf dışı koşumun rozeti. Etiket sabit, GEREKÇE ucun cümlesidir.
    function validityBadge(d) {
        if (!modelInvalid(d)) return '';
        return U.badge(T('panel.protection.modelNotValid', 'MODEL NOT VALID'),
                       'err', d.validity_note || '');
    }

    //: Künye satırı. Geçersizse ucun cümlesi HAM basılır (kısaltılmaz —
    //: sayıyı zarfın dışına iten büyüklüğü o cümle söylüyor). Geçerliyse
    //: beyanın kendisi bilgidir: "uç bu koşumu zarf içinde ilan etti".
    function validityRow(d) {
        if (d.model_valid === undefined || d.model_valid === null) return null;
        var gecersiz = modelInvalid(d);
        return [VALIDITY_LABEL,
            '<span data-tps-model-valid="' + (gecersiz ? 'false' : 'true') + '">'
            + esc(gecersiz
                ? (d.validity_note
                   || T('panel.protection.modelNotValidBare',
                        'The endpoint declared this run outside the model '
                        + 'validity envelope.'))
                : T('panel.protection.modelValidText',
                    'The endpoint declared this run inside the model validity '
                    + 'envelope.'))
            + '</span>'];
    }

    //: Künye satırını tablo listesine ekler (satır yoksa hiçbir şey olmaz).
    function withValidityRow(rows, d) {
        var r = validityRow(d);
        if (r) rows.unshift(r);
        return rows;
    }

    // Hüküm rengi. İKİ EKSEN (ÖH P11B5-02, kritik):
    //   (1) sayı sınırın altında mı?  -> within_limit
    //   (2) sayının KENDİSİ kazanılmış mı? -> unconservative
    // Uç "bu hüküm iyimser" (`unconservative:true`) derken ekranın YEŞİL
    // basması, kullanıcının okuyabileceği tek uyarı kanalını kapatır. Bu
    // yüzden iyimser hükümde YEŞİL YOKTUR: sınırın altındaki sayı 'warn'
    // rengine düşer (sınırın üstündeyse zaten 'err' — iyimserlik onu
    // iyileştirmez, kırmızı kalır).
    function limitKind(within, unconservative) {
        if (within == null) return 'dim';
        if (!within) return 'err';
        return unconservative ? 'warn' : 'ok';
    }

    // ---- Ablatif mod ----
    function renderAblative(d, root) {
        var el = document.createElement('div');
        var band = Array.isArray(d.q_star_band_MJ_kg)
            ? d.q_star_band_MJ_kg.join('–') + ' MJ/kg' : '—';
        // KAZANILMAMIŞ HÜKÜM BASILMAZ (B5): akı panelin kendi varsayılanı
        // ise ve bu koşum için motordan ölçülmüş bir akı OKUNMADIYSA,
        // kalınlık/gerileme kartları sayı yerine '—' basar. Sayı yanıttan
        // SİLİNMEZ; yalnız "kazanılmış hüküm" gibi gösterilmez (emsal: ÖH
        // Z3 sıvı Termal Koruma kartının ablatif '—' + gerekçe deseni).
        // D16 · P11S1-03: künye artık ucun `flux_basis` hükmünden okunur.
        // Eski yolda (`caller_supplied_no_energy_balance`) `fluxUsage`
        // doğrudan `fluxProvenance`i döndürür — davranış bit-aynı.
        var prov = fluxUsage(d);
        var callerProv = fluxProvenance(d.q_caller_W_m2);
        // KAZANILMIŞ HÜKÜM İKİ KOŞULLUDUR (P11B5-01): hükmü TAŞIYAN girdi
        // ölçülmüş olmalı VE uç koşumu kendi geçerlilik zarfının içinde
        // ilan etmiş olmalı. Zarf dışında gerileme/kalınlık sayıları
        // tasarım sayısı DEĞİLDİR; sayıyı taşıyan tek yer ucun kendi
        // `validity_note` cümlesidir.
        // D18 · P11S1-03 ŞART: "kazanıldı mı" ölçütü artık künye TÜRÜNDEN
        // türetilmez (uyuşmaz çiftte tür 'user' olur ama hüküm kazanılmaz);
        // `fluxUsage` kararı tek yerde verir ve `earned` ile bildirir.
        var earned = prov.earned === true && !modelInvalid(d);
        var dash = '—';
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeAblative', 'MODE: ABLATIVE (Q*)'), 'info')
            + U.badge(d.material_name || d.material || '—', 'info')
            + validityBadge(d)
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardThickness', 'Required liner thickness'),
                (earned ? U.fmt(d.required_thickness_mm, 2) : dash)
                + U.source.chip({ kind: prov.kind, declared: true,
                                  basis: prov.text }),
                'mm', 'info', T('panel.protection.cardThicknessTip', 'Total recession × design margin'))
            + U.statCard(T('panel.protection.cardRecession', 'Total recession'),
                (earned ? U.fmt(d.total_recession_mm, 2) : dash), 'mm')
            + U.statCard(T('panel.protection.cardRecessionRate', 'Recession rate (mean)'),
                (earned ? U.fmt(d.recession_rate_mm_s, 3) : dash), 'mm/s')
            + U.statCard(T('panel.protection.cardQstar', 'Q* used'), U.fmt(d.q_star_MJ_kg, 1), 'MJ/kg', null,
                U.tf('panel.protection.cardQstarTip', { band: band },
                     'Literature band: {band} — conservative low end by default'))
            + '</div>'
            + U.kvTable(withValidityRow([
                // Hükmün ARDINDAKİ SAYI nereden geldi? Kartlardan ÖNCE
                // okunması gereken satır (P17B3-02'nin ekrandaki karşılığı).
                [FLUX_BASIS_LABEL,
                 '<span data-tps-flux-kind="' + prov.kind + '"'
                 + ' data-tps-flux-basis="'
                 + (prov.basis || 'unpublished') + '"'
                 // D18 · P11S1-03 ŞART: hükmü taşıyan çiftin koşuma girip
                 // girmediği ayrı bir kancadır — künye türü tek başına
                 // "kazanıldı" demeye yetmez.
                 + ' data-tps-pair-match="'
                 + (prov.pairMatch === true ? 'true'
                    : (prov.pairMatch === false ? 'false' : 'na')) + '"'
                 + ' data-tps-earned="' + (earned ? 'true' : 'false') + '">'
                 + prov.text + '</span>'],
                // Kullanıcının YAZDIĞI sayı ile KULLANILAN sayı ayrı
                // satırlardır; ikisinin aynı olmadığı koşumda bunu ekran
                // söyler (D16 · P11S1-03).
                [CALLER_FLUX_LABEL,
                 '<span data-tps-caller-used="'
                 + (prov.callerUsed === false ? 'false'
                    : (prov.callerUsed === true ? 'true' : 'unknown')) + '">'
                 + (numOrNull(d.q_caller_W_m2) === null ? '—'
                    : U.fmt(d.q_caller_W_m2 / 1e6, 2) + ' MW/m²')
                 + (prov.callerUsed === false
                    ? ' — NOT used in this run (echoed for comparison only; '
                      + 'the used value is the mean heat flux below)'
                    : (prov.callerUsed === true
                       ? ' — used directly as the net surface flux ('
                         + callerProv.text + ')'
                       : ' — flux_basis not published by the endpoint, so '
                         + 'whether this value was used cannot be stated'))
                 + '</span>'],
                [T('panel.protection.meanFlux', 'Mean heat flux'), U.fmt(d.q_mean_W_m2 / 1e6, 2) + ' MW/m²'],
                [T('panel.protection.totalLoad', 'Total heat load'),
                 U.fmt(d.total_heat_load_J_m2 / 1e6, 1) + ' MJ/m²'],
                [T('common.burnTime', 'Burn Time'), U.fmt(d.burn_time_s, 1) + ' s'],
                [T('common.density', 'Density'), U.fmt(d.density_kg_m3, 0) + ' kg/m³'],
                [T('panel.protection.designMargin', 'Design margin'), U.fmt(d.design_margin, 2) + '×'],
                [T('common.source', 'Source'), d.source || '—'],
            ], d));
        root.appendChild(el);
    }

    // ---- Heat-sink modu: kartlar + T(x) + T_w(t) grafikleri ----
    function renderHeatSink(d, root) {
        var el = document.createElement('div');
        var exceeded = !!d.exceeds_limit;
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeHeatSink', 'MODE: HEAT SINK (1-D FD)'), 'info')
            + U.badge(d.material_name || d.wall_material || '—', 'info')
            + (exceeded
                ? U.badge(T('panel.protection.limitExceeded', 'SERVICE LIMIT EXCEEDED'), 'err',
                    T('panel.protection.limitExceededTip',
                      'Inner wall reaches the material service limit during the burn'))
                : U.badge(T('panel.protection.withinLimit', 'WITHIN SERVICE LIMIT'), 'ok'))
            + (d.cfl_ok === false
                ? U.badge(T('panel.protection.cflUnstable', 'CFL UNSTABLE'), 'err',
                          T('panel.protection.cflTip', 'Explicit FD stability criterion violated'))
                : '')
            // ERİME (P11B5-01): uç `exceeds_melting` yayımlıyordu, panel
            // okumuyordu. "Servis sınırı aşıldı" ile "cidar ERİDİ" aynı
            // rozet DEĞİLDİR; modelin faz değişimi yok, bu yüzden erime
            // sonrası sayı bir sıcaklık değil bir üst sınır ihlalidir.
            + (d.exceeds_melting === true
                ? U.badge(T('panel.protection.exceedsMelting',
                            'EXCEEDS MELTING POINT'), 'err',
                          d.validity_note || '')
                : '')
            + validityBadge(d)
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardInnerT', 'Inner wall T (end of burn)'),
                U.fmt(d.T_inner_K, 0), 'K', exceeded ? 'err' : 'ok')
            + U.statCard(T('panel.protection.cardOuterT', 'Outer wall T'), U.fmt(d.T_outer_K, 0), 'K')
            + U.statCard(T('panel.protection.serviceLimit', 'Service limit'),
                U.fmt(d.max_service_temp_K, 0), 'K', 'dim')
            + U.statCard(T('panel.protection.cardTimeToLimit', 'Time to limit'),
                (d.time_to_limit_s == null ? '—' : U.fmt(d.time_to_limit_s, 2)),
                's', exceeded ? 'err' : 'ok',
                T('panel.protection.cardTimeToLimitTip',
                  'Moment the inner wall reaches the service limit (\u201c\u2014\u201d = never during burn)'))
            + U.statCard(T('panel.protection.cardMargin', 'Margin to limit'), U.fmt(d.margin_to_limit_K, 0), 'K',
                exceeded ? 'err' : 'ok')
            + '</div>'
            + U.kvTable(withValidityRow([
                // ERİME EKSENİ — uçun yayımladığı, panelin okumadığı üçlü.
                // Satır YALNIZ uç gerçekten yayımladıysa konur (fail-closed).
                ['melting_point_K',
                 (d.melting_point_K == null ? '—'
                  : U.fmt(d.melting_point_K, 0) + ' K')],
                ['time_to_melting_s',
                 (d.time_to_melting_s == null ? '—'
                  : U.fmt(d.time_to_melting_s, 2) + ' s')],
                ['margin_to_melting_K',
                 (d.margin_to_melting_K == null ? '—'
                  : U.fmt(d.margin_to_melting_K, 0) + ' K')],
                [T('panel.protection.absorbedEnergy', 'Absorbed energy'),
                 U.fmt(d.absorbed_energy_J_m2 / 1e6, 2) + ' MJ/m²'],
                [T('panel.protection.hGas', 'h_gas (input, Bartz)'), U.fmt(d.h_gas_W_m2K, 0) + ' W/m²·K'],
                [T('panel.protection.recoveryTemp', 'Recovery temperature'), U.fmt(d.T_recovery_K, 0) + ' K'],
                [T('panel.protection.gridStep', 'Grid / time step'),
                 U.tf('panel.protection.gridStepValue',
                      { n: (d.n_nodes || '—'), dt: U.fmt(d.dt_s * 1e3, 2) },
                      '{n} nodes · dt = {dt} ms'),
                 'Fo = ' + U.fmt(d.Fo, 3) + ', Bi = ' + U.fmt(d.Bi, 3)
                    + ', CFL ok: ' + d.cfl_ok],
            ], d));
        root.appendChild(el);

        if (typeof Plotly === 'undefined') return;

        // --- T(x) profili (yanma sonu) ---
        var x = Array.isArray(d.x_m) ? d.x_m : [];
        var Tp = Array.isArray(d.T_profile_K) ? d.T_profile_K : [];
        if (x.length && Tp.length === x.length) {
            var div1 = document.createElement('div');
            div1.style.marginTop = '10px';
            root.appendChild(div1);
            var shapes = [];
            var annotations = [];
            if (Number.isFinite(d.max_service_temp_K)) {
                shapes.push({
                    type: 'line', xref: 'paper', x0: 0, x1: 1,
                    y0: d.max_service_temp_K, y1: d.max_service_temp_K,
                    line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
                });
                annotations.push({
                    xref: 'paper', x: 1, y: d.max_service_temp_K,
                    xanchor: 'right', yanchor: 'bottom',
                    text: T('panel.protection.serviceLimit', 'Service limit') + ' — '
                        + Math.round(d.max_service_temp_K) + ' K',
                    showarrow: false, font: { size: 10, color: '#ff5d73' },
                });
            }
            Plotly.newPlot(div1, [{
                x: x.map(function (v) { return v * 1e3; }), y: Tp,
                type: 'scatter', mode: 'lines',
                line: { color: '#00e5ff', width: 2 },
                hovertemplate: 'x = %{x:.2f} mm<br>T = %{y:.0f} K<extra></extra>',
            }], {
                title: T('panel.protection.chartProfile', 'Wall Temperature Profile at End of Burn'),
                xaxis: { title: T('panel.protection.axisDepth', 'Depth from hot face (mm)') },
                yaxis: { title: T('common.axis.temperatureK', 'Temperature (K)') },
                shapes: shapes,
                annotations: annotations,
                height: 340,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
        }

        // --- T_w(t) geçmişi (store_history varsayılan açık) ---
        var h = d.history || {};
        var ht = Array.isArray(h.t_s) ? h.t_s : [];
        var hT = Array.isArray(h.T_inner_K) ? h.T_inner_K : [];
        if (ht.length > 1 && hT.length === ht.length) {
            var div2 = document.createElement('div');
            div2.style.marginTop = '10px';
            root.appendChild(div2);
            var shapes2 = [];
            var ann2 = [];
            if (Number.isFinite(d.max_service_temp_K)) {
                shapes2.push({
                    type: 'line', xref: 'paper', x0: 0, x1: 1,
                    y0: d.max_service_temp_K, y1: d.max_service_temp_K,
                    line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
                });
            }
            if (Number.isFinite(d.time_to_limit_s)) {
                shapes2.push({
                    type: 'line', yref: 'paper',
                    x0: d.time_to_limit_s, x1: d.time_to_limit_s, y0: 0, y1: 1,
                    line: { color: '#ff8c33', width: 1, dash: 'dot' },
                });
                ann2.push({
                    x: d.time_to_limit_s, yref: 'paper', y: 1,
                    xanchor: 'left', yanchor: 'top',
                    text: T('panel.protection.limitReached', 'Limit reached') + ' — '
                        + U.fmt(d.time_to_limit_s, 2) + ' s',
                    showarrow: false, font: { size: 10, color: '#ff8c33' },
                });
            }
            Plotly.newPlot(div2, [{
                x: ht, y: hT, type: 'scatter', mode: 'lines',
                line: { color: '#2dd4a8', width: 2 },
                hovertemplate: 't = %{x:.2f} s<br>T_w = %{y:.0f} K<extra></extra>',
            }], {
                title: T('panel.protection.chartHistory', 'Hot-Face Temperature History'),
                xaxis: { title: T('common.axis.timeS', 'Time (s)') },
                yaxis: { title: T('panel.protection.axisInnerT', 'Inner wall temperature (K)') },
                shapes: shapes2,
                annotations: ann2,
                height: 320,
                showlegend: false,
            }, { responsive: true, displaylogo: false });
        }
    }

    // ---- Radyasyon dengesi modu ----
    function renderRadiation(d, root) {
        var el = document.createElement('div');
        // ÖH P11B5-02 (KRİTİK): uç `unconservative` + `unconservative_note`
        // yayımlıyordu, panel İKİSİNİ DE hiç okumuyordu — ekran 1621 K'de
        // %1,2 marjı YEŞİL "WITHIN SERVICE LIMIT" basıyor, ucun kendi
        // cümlesi ("both omissions push the equilibrium wall temperature
        // DOWN, so the material verdict below is optimistic") ise
        // kullanıcıya HİÇ ulaşmıyordu. Lüle uzantısı malzemesi (C-103 /
        // C-C) bu ekranda seçildiği için hüküm doğrudan bir malzeme
        // kararına dönüşüyor.
        var uncons = (d.unconservative === true);
        var uncNote = d.unconservative_note || '';
        var verdictBadge = '';
        if (d.within_limit != null) {
            if (!d.within_limit) {
                verdictBadge = U.badge(
                    T('panel.protection.limitExceeded', 'SERVICE LIMIT EXCEEDED'), 'err');
            } else if (uncons) {
                // Sınırın altında AMA hüküm KAZANILMAMIŞ: yeşil BASILMAZ.
                // Etiket aynı kalır (mevcut anahtar), RENK ve İPUCU değişir;
                // ipucu ucun kendi cümlesidir — panel yeni bir iddia
                // uydurmaz, susturulan iddiayı ekrana taşır.
                verdictBadge = U.badge(
                    T('panel.protection.withinLimit', 'WITHIN SERVICE LIMIT'),
                    'warn', uncNote);
            } else {
                verdictBadge = U.badge(
                    T('panel.protection.withinLimit', 'WITHIN SERVICE LIMIT'), 'ok');
            }
        }
        el.innerHTML =
            '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.protection.badgeRadiation', 'MODE: RADIATION EQUILIBRIUM'), 'info')
            + (d.material_name ? U.badge(d.material_name, 'info') : '')
            + verdictBadge
            + (uncons ? U.badge(VERDICT_BASIS_LABEL, 'warn', uncNote) : '')
            + validityBadge(d)
            + simplifiedBadge(d.model_note)
            + '</div>'
            + '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.protection.cardEqWall', 'Equilibrium wall T'), U.fmt(d.T_wall_eq_K, 0), 'K',
                limitKind(d.within_limit, uncons),
                T('panel.protection.cardEqWallTip', 'h_g·(T_recovery − T_w) = ε·σ·T_w⁴ energy balance'))
            + U.statCard(T('panel.protection.serviceLimit', 'Service limit'),
                (d.service_limit_K == null ? '—' : U.fmt(d.service_limit_K, 0)),
                'K', 'dim')
            + U.statCard(T('common.margin', 'Margin'),
                (d.margin_K == null ? '—' : U.fmt(d.margin_K, 0)),
                'K', limitKind(d.within_limit, uncons))
            + U.statCard(T('panel.protection.cardRadFlux', 'Radiated flux'), U.fmt(d.q_rad_W_m2 / 1e6, 2), 'MW/m²')
            + '</div>'
            + U.kvTable(withValidityRow([
                // Hükmün DÜRÜSTLÜK satırı: kartlardan ÖNCE okunur.
                [VERDICT_BASIS_LABEL,
                 '<span data-tps-unconservative="' + (uncons ? 'true' : 'false') + '">'
                 + (uncons ? uncNote : VERDICT_EARNED_TEXT)
                 + '</span>'],
                [VIEW_FACTOR_LABEL, U.fmt(d.view_factor, 3)],
                [GAS_RAD_LABEL,
                 U.fmt(d.q_gas_radiation_W_m2 / 1e6, 3) + ' MW/m²'],
                [T('panel.protection.emissivityUsed', 'Emissivity used'), U.fmt(d.emissivity, 2)],
                [T('panel.protection.hGas', 'h_gas (input, Bartz)'), U.fmt(d.h_gas_W_m2K, 0) + ' W/m²·K'],
                [T('panel.protection.recoveryTemp', 'Recovery temperature'), U.fmt(d.T_recovery_K, 0) + ' K'],
                [T('common.source', 'Source'), d.source || '—'],
            ], d));
        root.appendChild(el);
    }

    function render(data, root) {
        var d = data || {};
        // Mod tespiti yanıt anahtarlarından (endpoint modu geri yansıtmaz)
        if (Array.isArray(d.T_profile_K)) {
            renderHeatSink(d, root);
        } else if (typeof d.T_wall_eq_K === 'number') {
            renderRadiation(d, root);
        } else {
            renderAblative(d, root);
        }
        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Üç kip de aynı defteri alır: ucun `flux_basis` / `q_star_source`
        // gibi beyanları ortak sınıflandırıcıdan geçer, panel kendi
        // damgasını uydurmaz. Beyan yoksa düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, d, { deep: true });
    }

    window.AnalysisDock.register({
        id: 'protection',
        title: 'Thermal Protection — Ablative / Heat-Sink / Radiation-Cooled',
        titleKey: 'panel.protection.title',
        category: 'THERMAL',
        endpoint: '/api/thermal-protection',
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['mode', 'Analysis Mode', 'ablative', MODES, 'panel.protection.fMode'],
            ['q_net_W_m2', '[A] Net Heat Flux (W/m²)', DEFAULT_Q_NET_W_M2, 100000, 'panel.protection.fQNet'],
            ['material', '[A] Ablative Material', 'silica_phenolic', ABLATIVES,
             'panel.protection.fAblativeMaterial'],
            ['design_margin', '[A] Design Margin (×)', 1.5, 0.1, 'panel.protection.fDesignMargin'],
            ['q_star_MJ_kg', '[A] Q* Override (MJ/kg, blank = band)', '', 0.5,
             'panel.protection.fQstarOverride'],
            ['burn_time_s', '[A/H] Burn Time (s)', 10, 0.5, 'panel.protection.fBurnTime'],
            ['h_gas_W_m2K', '[H/R] h_gas — Bartz (W/m²·K)', 3000, 100, 'panel.protection.fHgas'],
            ['T_recovery_K', '[H/R] Recovery Temperature (K)', 3200, 50, 'panel.protection.fTRecovery'],
            ['wall_thickness_m', '[H] Wall Thickness (m)', 0.005, 0.001, 'panel.protection.fWallThickness'],
            ['wall_material', '[H] Wall Material', 'steel', WALL_MATERIALS,
             'panel.protection.fWallMaterial'],
            ['T_initial_K', '[H] Initial Temperature (K)', 300, 5, 'panel.protection.fTInitial'],
            ['radiation_material', '[R] Extension Material', 'niobium_c103', RAD_MATERIALS,
             'panel.protection.fRadMaterial'],
            ['emissivity', '[R] Emissivity Override (blank = material)', '', 0.05,
             'panel.protection.fEmissivity'],
            // ÖH P11B5-02 KALANI (adıyla açık borç): çekirdek
            // ``view_factor`` + ``q_gas_radiation_W_m2`` girdilerini kabul
            // ediyor ve /api/thermal-protection artık ikisini de GEÇİRİYOR
            // (app.py `_TP_MODE_KEYS`), ama panele FORM ALANI eklemek
            // hrma/static/js/i18n_*.js sözlüğüne iki anahtar yazmayı
            // gerektirir; sözlük bu paketin mülkü DEĞİLDİR. Alanlar
            // sözlük anahtarlarıyla birlikte i18n dalgasında açılacak.
            // Bugün kazanılan: değerler ekrana İNİYOR (kvTable) ve hüküm
            // ihmal edilmişken YEŞİL basılmıyor.
        ],
        fromResults: function (r) {
            var m = (r && r.motor) || r || {};
            var out = {};
            if (Number.isFinite(m.burn_time)) out.burn_time_s = m.burn_time;
            // Plan Dalga 3: q / h_g önerileri motorun gerçek Bartz sonucundan
            // (motor.heat_transfer_analysis.gas_side_analysis)
            var hta = m.heat_transfer_analysis || {};
            var gsa = hta.gas_side_analysis || {};
            if (Number.isFinite(gsa.heat_flux)) {
                out.q_net_W_m2 = gsa.heat_flux;          // W/m² (boğaz tasarım yükü)
            }
            if (Number.isFinite(gsa.gas_side_coefficient)) {
                out.h_gas_W_m2K = gsa.gas_side_coefficient;
            } else {
                var htc = hta.heat_transfer_coefficients || {};
                if (Number.isFinite(htc.gas_side)) out.h_gas_W_m2K = htc.gas_side;
            }
            if (Number.isFinite(gsa.adiabatic_wall_temperature)) {
                out.T_recovery_K = gsa.adiabatic_wall_temperature;
            }
            // --- B5: hibrit yolu sayı vermediyse motorun KENDİ ölçümü ---
            // Yukarıdaki hibrit dalı DEĞİŞTİRİLMEDİ; bu blok yalnız o dal
            // boş kaldığında (katı/sıvı) devreye girer. Ölçüm yoksa alan
            // varsayılanında kalır ve `renderAblative` hükmü GERİ ÇEKER.
            var motorType = (window.AnalysisDock.getMotorType
                             && window.AnalysisDock.getMotorType()) || null;
            lastFluxRead = null;
            if (!Number.isFinite(out.q_net_W_m2) && motorType) {
                var measured = readMeasuredFlux(m, motorType);
                if (measured) {
                    lastFluxRead = measured;
                    out.q_net_W_m2 = measured.q_W_m2;
                    if (measured.h_gas_W_m2K !== null
                            && !Number.isFinite(out.h_gas_W_m2K)) {
                        out.h_gas_W_m2K = measured.h_gas_W_m2K;
                    }
                    if (measured.T_recovery_K !== null
                            && !Number.isFinite(out.T_recovery_K)) {
                        out.T_recovery_K = measured.T_recovery_K;
                    }
                }
            } else if (Number.isFinite(out.q_net_W_m2)) {
                // Hibrit dalının bulduğu sayı da künyelenir: hükmün
                // ardındaki akının yolu ekranda beyan edilebilsin.
                lastFluxRead = {
                    motorType: motorType || 'hybrid',
                    q_W_m2: out.q_net_W_m2,
                    q_path: 'heat_transfer_analysis.gas_side_analysis.heat_flux',
                    h_gas_W_m2K: numOrNull(out.h_gas_W_m2K),
                    T_recovery_K: numOrNull(out.T_recovery_K),
                };
            }
            return out;
        },
        render: render,
    });

    // Merkezi katalog yüklüyse üç select'i etiket filtreleriyle doldur;
    // değilse fallback listeleri aynen kalır. Ablatif listesi MERGE ile
    // birleştirilir: carbon_phenolic/epdm yalnız thermal_protection.py
    // tablosunda vardır, kaybolmamalı.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'material',
            tags: ['ablative'], fallback: ABLATIVES, merge: true,
        });
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'wall_material',
            tags: ['shell', 'liner'], fallback: WALL_MATERIALS, merge: true,
        });
        window.HRMAMaterials.populateSelect({
            panelId: 'protection', fieldId: 'radiation_material',
            tags: ['radiative'], fallback: RAD_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render'lar (dry-run)
    window.ProtectionPanel = {
        _render: render,
        _renderAblative: renderAblative,
        _renderHeatSink: renderHeatSink,
        _renderRadiation: renderRadiation,
        // Bekçi yüzeyi (D15/P11B5-01): geçerlilik hükmü DOM'suz ölçülsün.
        _modelInvalid: modelInvalid,
        _validityRow: validityRow,
        // Bekçi yüzeyi (B5): akı künyesi DOM'suz da ölçülebilsin.
        _readMeasuredFlux: readMeasuredFlux,
        _fluxProvenance: fluxProvenance,
        _lastFluxRead: function () { return lastFluxRead; },
        _defaultQ: DEFAULT_Q_NET_W_M2,
    };
})();
