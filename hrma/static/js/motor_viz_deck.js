/*
 * MotorVizDeck — MotorViz3D için hazır simülasyon güvertesi.
 *
 * Solid/liquid sayfaları gibi kendi HUD'unu elle kurmak istemeyen sayfalar
 * için: verilen konteynere komple güverteyi (başlık + araç çubuğu + 3D
 * sahne + tasarım paneli + zaman çizelgesi + telemetri) enjekte eder ve
 * kablolar. Stiller theme.css'teki .viz-* sınıflarından gelir;
 * motor_viz3d.js yüklü olmalıdır.
 *
 * Kullanım:
 *   MotorVizDeck.create('container_id', motorData, {
 *       title: 'MOTOR SIMULATION',
 *       subtitle: 'PARAMETRIC 3D MODEL',
 *       motorType: 'solid' | 'liquid' | 'hybrid',   // motorData.viz_motor_type'ı ezer
 *       portShape: 'star' | 'multiport' | ...        // başlangıç port kesiti
 *   })
 *
 * motorData şeması MotorViz3D ile aynıdır (results.motor — SI metre).
 *
 * Parite notu (2026-07-19): advanced.html'deki hibrit güvertede 12 buton,
 * hız kontrolü, tasarım modu ve 6 telemetri çipi var; bu güverte katı/sıvı
 * sayfalarında aynı yetenek setini sunar. Farklar YALNIZ fizik gereğidir:
 * sıvıda port çapı / web kalıntısı yoktur, katıda O/F yoktur. Var olmayan
 * büyüklük için çip UYDURULMAZ — motorData'da alan yoksa çip hiç basılmaz.
 */
(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    var UID = 0;

    var PORT_LABELS = {
        circular: 'Circular', star: 'Star',
        multiport: 'Multi-Port', finocyl: 'Finocyl'
    };

    /* Kamera ön ayarı adları: motor_viz3d.cycleCameraPreset() küçük harf
       anahtar döndürür, ekranda İngilizce karşılığı TX()'ten geçer. */
    var CAM_LABELS = {
        iso: 'Iso', side: 'Side', nozzle: 'Nozzle', injector: 'Injector'
    };

    /* Uzun sabit metinler tek yerde: hem ilk çizimde hem refreshLabels()'ta
       AYNI İngilizce kaynaktan çevrilsinler (kaynak ikiye ayrılırsa biri
       sözlükte, öteki dışında kalır ve dil değişiminde metin donar). */
    var DESIGN_STATUS_TEXT =
        'GEOMETRY PREVIEW — 3D shape only; performance figures are unchanged. ' +
        'Re-run Calculate to update the analysis.';
    var HEAT_LEGEND_TEXT = 'WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup>';
    /* ÖH D29 · P11B1-14 — NİTELEYİCİ GÜVERTEYE DE TAŞINDI.
       ÖLÇÜLDÜ (a3/once.json): hibrit sayfa (advanced.html) efsanesi
       'WALL HEAT FLUX — BARTZ (reference cooled wall)' derken güverte
       yalnız 'WALL HEAT FLUX — BARTZ (A_t/A)^0.9' diyordu; niteleyici
       advanced.html'de bir ADLANDIRMA BORCU kapanışıdır (oradaki HTML
       yorumu: min/maks değerler referans soğutulmuş cidarda değerlendirilen
       TASARIM yükleridir; denge cidar sıcaklığındaki akı bundan ~2,5 kat
       düşük çıkabilir) ve güvertede yoktu — aynı sayı iki sayfada iki ayrı
       adla okunuyordu.
       Niteleyici AYRI bir dize olarak tutulur: HEAT_LEGEND_TEXT'in kendisi
       çeviri sözlüğünde (i18n_charts.js) BİREBİR bu metinle anahtarlıdır,
       dizeyi değiştirmek TR karşılığını düşürürdü (i18n dosyaları bu
       dalgada kardeş kulvarın elinde). İki parça ayrı ayrı TX'ten geçer. */
    var HEAT_LEGEND_WALL_REF = '(reference cooled wall)';
    var HEAT_LEGEND_DEBT_NOTE =
        'Legend min/max are DESIGN loads evaluated at the reference cooled '
        + 'wall (gas_side_analysis.chamber/throat_heat_flux); the flux at the '
        + 'equilibrium wall temperature can come out about 2.5x lower.';
    //: Öznitelik kaçışı (modül düzeyi) — efsane başlığının title'ı.
    function escAttr(t) {
        return String(t === null || t === undefined ? '' : t)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function heatLegendHead() {
        return TX(HEAT_LEGEND_TEXT) + ' ' + TX(HEAT_LEGEND_WALL_REF);
    }
    var STATUS_STANDBY = 'STANDBY';
    var STATUS_BURNOUT = 'BURNOUT';
    var STATUS_BURNING = 'COMBUSTION ACTIVE';
    /* ÖH D36 / onemli2-sivi a2 — SÜRE YOKSA ZAMAN EKSENİ ÇİZİLMEZ.
       ÖLÇÜLDÜ (docs/scofield/raw/OH/D36/onemli2-sivi/a2/once.json K7):
       sıvı sayfa adaptörü sabit `burn_time: 10` basıyordu ve sahne
       `num(md.burn_time, 10)` yedeğini taşıyordu; saat "t = 0,00 s /
       10,00 s", kaydırıcı ve oynatma, süresi VERİLMEMİŞ bir motorda uydurma
       bir yanma süresi üzerinde koşuyordu. Sahne artık süre yoksa
       `dims.burnTime = null` verir; güverte oynatma düğmesini ve
       kaydırıcıyı gizler, saatin yerine bu beyanı yazar. Metin anahtarı
       i18n_charts.js'te (EN + TR). Süre verildiğinde (hibrit, katı, süreli
       sıvı) şerit eskisiyle aynıdır. */
    var NO_TIME_AXIS_TEXT = 'NO BURN TIME SUPPLIED: TIME AXIS NOT DRAWN';
    var DEFAULT_TITLE = 'MOTOR SIMULATION';
    var DEFAULT_SUBTITLE = 'PARAMETRIC 3D MODEL — LIVE GEOMETRY FROM SOLVER OUTPUT';

    // Tasarım modu slider aralıkları (taban değerin katı olarak)
    var DESIGN_DIA_SPAN = [0.6, 1.4];      // kamara çapı: ±%40
    var DESIGN_LEN_SPAN = [0.6, 1.6];      // kamara/grain boyu: -%40 … +%60
    var DESIGN_EPS_RANGE = [2, 60];        // genişleme oranı mutlak sınırları
    var DESIGN_SLIDER_STEPS = 1000;        // slider tam sayı çözünürlüğü
    var DESIGN_DEBOUNCE_MS = 120;          // istemci tarafı yeniden çizim gecikmesi
    var HUD_THROTTLE_MS = 80;              // telemetri yazma sıklığı (~12 Hz)
    // ÖH D25 / OH-D24-05 — TEK KAYNAK. Bu sayı burada TANIMLANMAZ:
    // `static/js/units_constants.js` ön yüzün tek birim çevrim kaynağıdır
    // (ölçüldü: aynı tanım dört JS dosyasındaydı). Modül yoksa sessiz bir
    // yedek UYDURULMAZ — requirePaPerBar() hata fırlatır.
    var PA_PER_BAR = (function () {
        var g = (typeof window !== 'undefined') ? window : globalThis;
        // Tarayıcı: <script src="/static/js/units_constants.js"> modülü
        // window'a yazar. Node (bekçi koşumları panel dosyasını require
        // eder): modül kardeş dosyadan çözülür. İKİ yolda da sayı TEK
        // yerde yaşar; burada yeniden TANIMLANMAZ.
        if (!g.HRMAUnits && typeof require === 'function') {
            try { g.HRMAUnits = require('./units_constants.js').UNITS; } catch (e) { /* yok */ }
            if (g.HRMAUnits && !g.HRMAUnits.requirePaPerBar) {
                try {
                    g.HRMAUnits.requirePaPerBar =
                        require('./units_constants.js').requirePaPerBar;
                } catch (e) { /* yok */ }
            }
        }
        if (!g.HRMAUnits || !g.HRMAUnits.requirePaPerBar) {
            throw new Error('units_constants.js must load before this panel: '
                + 'PA_PER_BAR has a single source and is not re-declared here.');
        }
        return g.HRMAUnits.requirePaPerBar();
    }());

    /* --- CFD alanı denetim grubu (parti 30) ---------------------------
       Güverte CFD KOŞTURMAZ: alanı Analiz Merkezi'ndeki CFD kiracısı
       sahneye bindirir (panels/cfd_panel.js -> MotorViz3D.setCfdField).
       Güverte yalnız YÜKLÜ alanı sürer; alan yokken grup gri durur ve
       nedenini yazar (sahte düğme yok).

       Düğmelerin kimlikleri motor_viz3d.js'in CFD_METRICS tablosundan
       gelir; buradaki tek ek bilgi güvertenin dar araç çubuğuna sığan
       SEMBOLDÜR (etiketin tamamı düğmenin title'ında durur). Sembol
       kümesinin metrik kümesiyle eşitliği bekçilidir:
       tests/test_cfd_alan_koprusu.py */
    var CFD_METRIC_SYMBOLS = { mach: 'M', pressure: 'p', temperature: 'T' };

    /* Sahnenin üretebildiği RED kodlarının TAM kümesi. Panelde de bir
       kopyası var; iki dosya birbirini ithal edemez (cfd_panel.js yalnız
       Merkez sayfalarında, güverte katı/sıvı sayfalarında yüklü) ve
       motor_viz3d.js kod listesini DIŞA AÇMIYOR. İkisi de üreticinin
       KENDİ kaynağına küme eşitliği bekçisiyle bağlıdır — liste burada
       kaymışsa test kırmızı döner. Kullanıcıya basılan METİN yine
       sahnenin reason.key/fallback çiftinden gelir; mesajın ikinci bir
       tanımı yoktur. */
    var CFD_REASON_CODES = ['no_scene', 'no_solver_contour',
        'contour_mismatch', 'missing_metric', 'bad_field_block', 'no_field'];

    function el(id) { return document.getElementById(id); }

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }

    /* Güverte metinleri için ikinci köprü: ANAHTAR = İNGİLİZCE METNİN
       KENDİSİ (i18n_charts.js sözleşmesi). Neden T() değil: `viz.*` anahtar
       uzayı i18n_common.js'te tanımlı ve bu dosyayla birlikte
       güncellenemiyor; oysa i18n_charts.js sözlüğü zaten "metin = anahtar"
       kuralıyla çalışıyor ve register() ile I18N'e katılıyor. Eşleşme
       bulunamazsa metin AYNEN döner (asla anahtar, asla boş).
       2026-08-03: bu dosyanın görünür metinlerinin tamamı sabit
       İngilizceydi — TR modda 3B güverte tek kelime Türkçe göstermiyordu. */
    function TX(text) {
        var api = window.I18N || window.HRMAChartI18N;
        return (api && typeof api.chartText === 'function') ? api.chartText(text) : text;
    }

    /* ÖH D23 / P17B2-10 — ÇİP BAŞLIĞINDAKİ SEMBOL BÜYÜTÜLMEZ.
       ÖLÇÜLDÜ (P17 B2-tur-09, canlı /liquid; kod noktası okundu):
       `.viz-chip .k { text-transform: uppercase }` (theme.css) çip
       başlığındaki ε (U+03B5 GREEK SMALL LETTER EPSILON) karakterini
       Ε (U+0395 GREEK CAPITAL LETTER EPSILON) yapıyordu; ekranda okunan
       dize `EXPANSION Ε 50.0`. Çoğu yazı tipinde Ε ile Latin E ayırt
       edilemez, yani genişleme oranının STANDART SEMBOLÜ ekranda yok
       oluyor — kullanıcı 'EXPANSION E' okuyor. Aynı kural `P<sub>c</sub>`
       alt indisini de düzleştiriyordu (`PC 100.0bar`).

       Onarım RENDER anındadır, etiket KAYNAĞINDA değil: sözlük anahtarı
       (TX'in eşleştirdiği İngilizce kaynak metin) olduğu gibi kalır,
       yalnız çevrilmiş çıktıdaki sembol karakterleri büyütmeden muaf bir
       kaba sarılır. Böylece hem EN hem TR sözlük girdileri bozulmaz.

       Kapsam: Yunan harfleri (U+0370–U+03FF), Ø (U+00D8/U+00F8) ve
       <sub>/<sup> içerikleri. ASCII harfler büyütülmeye devam eder. */
    var SEMBOL_DESENI = /([Ͱ-ϿØø])/g;

    function sembolKoru(html) {
        if (typeof html !== 'string' || !html) return html;
        // HTML varlıkları (&epsilon; &Oslash; …) tarayıcıda çözülünce
        // yukarıdaki bloğa düşer; dize hâlindeyken de yakalanmaları için
        // varlık adları ayrıca sarılır.
        var out = html.replace(/(&[A-Za-z]+;)/g, function (m) {
            return /^&(amp|lt|gt|quot|apos|nbsp);$/.test(m)
                ? m : '<span class="viz-sym">' + m + '</span>';
        });
        out = out.replace(/(<sub>[\s\S]*?<\/sub>|<sup>[\s\S]*?<\/sup>)/g,
            function (m) { return '<span class="viz-sym">' + m + '</span>'; });
        return out.replace(SEMBOL_DESENI, '<span class="viz-sym">$1</span>');
    }

    /* Çip başlığı = çevrilmiş metin + sembol koruması (tek yol). */
    function TXK(text) { return sembolKoru(TX(text)); }

    function portLabel(shape) {
        return TX(PORT_LABELS[shape] || PORT_LABELS.circular);
    }

    function camLabel(name) {
        return TX(CAM_LABELS[name] ||
                  (String(name).charAt(0).toUpperCase() + String(name).slice(1)));
    }

    function isNum(v) { return typeof v === 'number' && isFinite(v); }

    /* ÖH D36 / OH-P-11 (B-2 kalanı) — GÜVERTE SAYILARI TEK KAYNAKTAN.

       ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/D36/sahne-hud/a1/once.json):
       D35 sayi-bicimi kulvarı ekran sayısını i18n.js kanonuna bağladı
       (app.js / solid.html / liquid.html / motor_viz3d.js) ama bu dosyaya
       sahip değildi: güvertede 18 satırda 20 `toFixed` çağrısı vardı, hiçbiri
       `I18N.number`dan geçmiyordu. Türkçe oturumda (once.json M1, 14
       noktalı / 0 virgüllü ondalık) saat "t = 1.23 s / 3.20 s", çipler
       "40.0 mm" / "222.8 s" / "40.3 bar", ısı efsanesi "3.28 MW/m²",
       tasarım sürgüsü "100.0 mm" — hepsi NOKTA; aynı
       ekranın kartları ise VİRGÜL basıyordu (ÖH D33-3 / OH-D33-12'nin
       kart-uyarı ayrışmasının güverte kopyası).

       Onarım ayracı BURADA SEÇMEZ: karar motor_viz3d.js `numTxt` ile aynı
       delegatörlerle i18n.js'e devredilir (`I18N.number` / `I18N.unit` /
       `I18N.percent`), önceden biçimlenmiş metin (`toExponential`) ise
       `I18N.decimalText` kanalından geçer. Basamak sayısı DEĞİŞMEZ.
       Sözlük motoru yoksa (bekçi düzenekleri güverteyi I18N'siz de
       koşturur) eski davranışa düşülür: sayı UYDURULMAZ, yalnız ayraç
       yerelleşmez. Bekçi: tests/test_d36_sahne_a1.py */
    function numTxt(v, d) {
        return (window.I18N && typeof window.I18N.number === 'function')
            ? window.I18N.number(v, d)
            : (isNum(v) ? (d === undefined ? String(v) : v.toFixed(d)) : String(v));
    }
    function unitTxt(v, unit, d) {
        return (window.I18N && typeof window.I18N.unit === 'function')
            ? window.I18N.unit(v, unit, d)
            : (numTxt(v, d) + (unit ? ' ' + unit : ''));
    }
    function pctTxt(v, d) {
        return (window.I18N && typeof window.I18N.percent === 'function')
            ? window.I18N.percent(v, d) : (numTxt(v, d) + '%');
    }
    function decTxt(text) {
        return (window.I18N && typeof window.I18N.decimalText === 'function')
            ? window.I18N.decimalText(text) : text;
    }

    /* 3B sahnenin yayımladığı metrik tablosu (tek kaynak). Sahne yoksa
       güverte zaten kurulmaz (create() MotorViz3D'yi şart koşuyor). */
    function cfdMetrics() {
        var t = window.MotorViz3D && window.MotorViz3D.CFD_METRICS;
        return Array.isArray(t) ? t : [];
    }

    function cfdMetricById(id) {
        var t = cfdMetrics();
        for (var i = 0; i < t.length; i++) {
            if (t[i].id === id) return t[i];
        }
        return null;
    }

    /* Aralık uçları: büyüklüğü önceden bilinmiyor (Mach ~1, basınç ~1e6),
       bant dışına çıkınca üstel biçime geçilir — sayı kırpılmaz. */
    function cfdNum(v) {
        if (!isNum(v)) return '—';
        var a = Math.abs(v);
        if (a !== 0 && (a >= 1e4 || a < 1e-2)) return decTxt(v.toExponential(3));
        return numTxt(v, 3);
    }

    /* RED sözlüğü -> okunur metin. Metin SAHNENİN kendi anahtar/yedek
       çiftinden gelir; kod açıkça basılır, tanınmayan kod adıyla beyan
       edilir (sessiz "olmadı" mesajı yasak). */
    function cfdReasonText(reason) {
        if (!reason || typeof reason !== 'object') {
            return T('viz.cfd.noReason',
                'The 3D scene refused, but returned no reason block.');
        }
        var kod = String(reason.code == null ? '' : reason.code);
        var metin = reason.key ? T(reason.key, reason.fallback || kod)
                               : String(reason.fallback || kod);
        if (CFD_REASON_CODES.indexOf(kod) < 0) {
            metin = T('viz.cfd.unknownCode',
                'Refusal code unknown to this deck:') + ' ' + (kod || '?')
                + ' — ' + metin;
        }
        var p = reason.params, ek = [];
        if (p && typeof p === 'object') {
            Object.keys(p).forEach(function (k) {
                ek.push(k + '=' + String(p[k]));
            });
        }
        return '[' + (kod || '?') + '] ' + metin
            + (ek.length ? ' (' + ek.join(', ') + ')' : '');
    }

    function firstNum() {
        for (var i = 0; i < arguments.length; i++) {
            if (isNum(arguments[i])) return arguments[i];
        }
        return null;
    }

    // Derin olmayan güvenli kopya (tasarım modunda taban veriyi bozmamak için)
    function shallowClone(o) {
        var out = {}, k;
        for (k in o) { if (Object.prototype.hasOwnProperty.call(o, k)) out[k] = o[k]; }
        return out;
    }

    // --- Telemetri çipleri: yalnız VERİSİ OLAN büyüklükler basılır -----------
    function chipList(p, opts, md) {
        var isLiquid = opts.motorType === 'liquid';
        var isSolid = opts.motorType === 'solid';
        var chips = [];

        // Katı ve hibritte port/web anlamlıdır (yakıt grain'i regrese eder)
        // label = İNGİLİZCE kaynak metin; ekrana basılırken TX()'ten geçer
        // (refreshLabels dil değişiminde aynı kaynaktan yeniden yazar).
        if (!isLiquid) {
            chips.push({ id: p + '_port', label: isSolid ? 'Core &Oslash;' : 'Port &Oslash;' });
            chips.push({ id: p + '_web', label: 'Web Remaining' });
        }
        // O/F yalnız iki propellantlı motorlarda ve YALNIZ veri varsa
        if (!isSolid && (isNum(md.of_ratio) || isNum(md.of_ratio_initial) ||
                         isNum(md.mixture_ratio))) {
            chips.push({ id: p + '_of', label: 'O/F Ratio' });
        }
        // --- ÖH D21 / P11B1-06: Isp ÇİPİ REFERANSINI SÖYLER ------------
        // ÖLÇÜLDÜ (raw/OH/D21/arayuz/a1/once.json, M5): çipin etiketi
        // niteliksiz 'Isp' idi ve sıvı sayfası ona VAKUM değerini
        // besliyordu (liquid.html: `isp: num(results.isp_vacuum, ...)`)
        // — yanındaki 'Thrust' çipi ise aynı yanıtın `thrust` alanını,
        // yani tasarım/deniz seviyesi itkisini basıyordu. İki çip yan
        // yana iki farklı ortamdan konuşuyordu.
        // Referans UYDURULMAZ: güverte sayının hangi ortamda
        // hesaplandığını bilemez, bunu ÇAĞIRAN beyan eder
        // (`motorData.isp_reference`). Beyan yoksa sayı gizlenmez ama
        // NİTELİKSİZ de yayımlanmaz: etiket referansın beyan
        // edilmediğini söyler.
        chips.push({ id: p + '_isp', label: ispLabel(md) });
        chips.push({ id: p + '_thrust', label: 'Thrust' });
        if (isNum(md.chamber_pressure)) {
            chips.push({ id: p + '_pc', label: 'P<sub>c</sub>' });
        }
        // Genişleme oranı: doğrudan verilir ya da çıkış/boğaz çapından türer
        if (expansionRatio(md) !== null) {
            chips.push({ id: p + '_eps', label: 'Expansion &epsilon;' });
        }
        // Sıvıda port çapı yoktur; boğaz çapı sabit ölçü olarak gösterilir
        if (isLiquid && isNum(md.throat_diameter)) {
            chips.push({ id: p + '_dt', label: 'Throat &Oslash;' });
        }
        return chips;
    }

    // Isp çipinin etiketi — referans ÇAĞIRANIN beyanından gelir.
    // Kabul edilen beyanlar `motorData.isp_reference` alanında:
    //   'vacuum'      -> vakum Isp
    //   'sea_level'   -> deniz seviyesi Isp
    //   'design_alt'  -> tasarım irtifasının ortam basıncında Isp
    // Tanınmayan ya da eksik beyan sessizce 'vakum' sayılmaz.
    var ISP_REFERANS_ETIKETLERI = {
        vacuum: 'Isp (vacuum)',
        sea_level: 'Isp (sea level)',
        design_alt: 'Isp (design altitude)'
    };
    var ISP_REFERANSSIZ_ETIKET = 'Isp (reference not declared)';

    function ispLabel(md) {
        var ref = md && md.isp_reference;
        if (typeof ref !== 'string') return ISP_REFERANSSIZ_ETIKET;
        return Object.prototype.hasOwnProperty.call(
            ISP_REFERANS_ETIKETLERI, ref)
            ? ISP_REFERANS_ETIKETLERI[ref] : ISP_REFERANSSIZ_ETIKET;
    }

    function expansionRatio(md) {
        if (isNum(md.expansion_ratio) && md.expansion_ratio > 1) return md.expansion_ratio;
        if (isNum(md.exit_diameter) && isNum(md.throat_diameter) && md.throat_diameter > 0) {
            var eps = Math.pow(md.exit_diameter / md.throat_diameter, 2);
            return isFinite(eps) && eps > 1 ? eps : null;
        }
        return null;
    }

    // --- Tasarım modu kontrolleri: motor tipine göre anlamlı parametreler ----
    function designControls(opts, md) {
        var isSolid = opts.motorType === 'solid';
        var ctrls = [];
        var dch = firstNum(md.chamber_diameter);
        var len = firstNum(md.grain_length, md.chamber_length);
        var eps = expansionRatio(md);

        if (isNum(dch) && dch > 0) {
            ctrls.push({
                key: 'dch', label: 'Chamber &Oslash;',
                lo: dch * DESIGN_DIA_SPAN[0], hi: dch * DESIGN_DIA_SPAN[1], val: dch,
                fmt: function (v) { return unitTxt(v * 1000, 'mm', 1); }
            });
        }
        if (isNum(len) && len > 0) {
            ctrls.push({
                key: 'len', label: isSolid ? 'Grain Length' : 'Chamber Length',
                lo: len * DESIGN_LEN_SPAN[0], hi: len * DESIGN_LEN_SPAN[1], val: len,
                fmt: function (v) { return unitTxt(v * 1000, 'mm', 0); }
            });
        }
        if (eps !== null) {
            ctrls.push({
                key: 'eps', label: 'Expansion Ratio &epsilon;',
                lo: Math.max(DESIGN_EPS_RANGE[0], eps * 0.4),
                hi: Math.min(DESIGN_EPS_RANGE[1], Math.max(eps * 2.2, eps + 4)),
                val: eps,
                fmt: function (v) { return numTxt(v, 1); }
            });
        }
        return ctrls;
    }

    /* CFD alanı denetim grubu — sahnenin ALTINDA, tasarım panelinin
       ardında. Görsel kimlik mevcut sınıflardan gelir (.viz-design /
       .viz-dctrl / .viz-toolbar / .viz-btn / .viz-dstatus); yeni renk
       paleti ya da tipografi UYDURULMAZ. Alan yüklü değilken düğmeler
       disabled ve durum satırı nedenini yazar. */
    function cfdGroupHtml(p) {
        var dugmeler = cfdMetrics().map(function (m) {
            return '<button class="viz-btn" id="' + p + '_cfd_m_' + m.id +
                '" data-cfd-metric="' + m.id + '" title="' +
                T(m.labelKey, m.labelFallback) + '" disabled>' +
                (CFD_METRIC_SYMBOLS[m.id] || m.id) + '</button>';
        }).join('');
        return '' +
            '  <div class="viz-design" id="' + p + '_cfd">' +
            '    <div class="viz-dctrl">' +
            '      <div class="dk"><span id="' + p + '_cfd_k">' +
                     T('viz.cfd.group', 'CFD FIELD') + '</span>' +
            '        <b id="' + p + '_cfd_range">—</b></div>' +
            '      <div class="viz-toolbar">' + dugmeler +
            '        <button class="viz-btn warn" id="' + p + '_cfd_off" ' +
                       'disabled>' + T('viz.cfd.close', 'Close') + '</button>' +
            '      </div>' +
            '    </div>' +
            '    <div class="viz-dstatus" id="' + p + '_cfd_status"></div>' +
            '  </div>';
    }

    function deckHtml(p, opts, chips, ctrls) {
        // Port kesiti YALNIZ sıvıda anlamsızdır (yakıt grain'i yoktur);
        // katı ve hibritte port şekli döngüsü sunulur
        var hasPort = opts.motorType !== 'liquid';

        var designHtml = '';
        if (ctrls.length) {
            designHtml =
                '  <div class="viz-design" id="' + p + '_design" style="display: none;">' +
                ctrls.map(function (c) {
                    return '<div class="viz-dctrl">' +
                        '<div class="dk"><span id="' + p + '_dl_' + c.key + '">' +
                        TX(c.label) + '</span>' +
                        '<b id="' + p + '_dv_' + c.key + '">—</b></div>' +
                        '<input type="range" id="' + p + '_ds_' + c.key + '" min="0" max="' +
                        DESIGN_SLIDER_STEPS + '" value="0"></div>';
                }).join('') +
                '    <div class="viz-dstatus" id="' + p + '_dstatus">' +
                TX(DESIGN_STATUS_TEXT) + '</div>' +
                '  </div>';
        }

        return '' +
            '<div class="viz-deck">' +
            '  <div class="viz-head">' +
            '    <div>' +
            '      <div class="viz-title" id="' + p + '_title"><span class="viz-dot"></span>' +
                     TX(opts.title) + '</div>' +
            '      <div class="viz-sub" id="' + p + '_sub">' + TX(opts.subtitle) + '</div>' +
            '    </div>' +
            '    <div class="viz-toolbar">' +
            '      <button class="viz-btn active" id="' + p + '_btn_cut">' + TX('Cutaway') + '</button>' +
            '      <button class="viz-btn active" id="' + p + '_btn_dim">' + TX('Dimensions') + '</button>' +
            '      <button class="viz-btn warn active" id="' + p + '_btn_plume">' + TX('Exhaust') + '</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_exp">' + TX('Exploded') + '</button>' +
            (hasPort
                ? '      <button class="viz-btn" id="' + p + '_btn_portshape">' +
                  TX('Port') + ': ' + portLabel(opts.portShape) + '</button>'
                : '') +
            '      <button class="viz-btn warn" id="' + p + '_btn_heat">' + TX('Heat Map') + '</button>' +
            (ctrls.length
                ? '      <button class="viz-btn warn" id="' + p + '_btn_design">' +
                  TX('Design Mode') + '</button>'
                : '') +
            '      <button class="viz-btn" id="' + p + '_btn_rot">' + TX('Orbit') + '</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_cam">' +
                       TX('Cam') + ': ' + camLabel('iso') + '</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_quality">HQ</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_speed">1&times;</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_frame">' +
                       T('viz.btnFrame', 'Save PNG') + '</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_reset">' + TX('Reset View') + '</button>' +
            '    </div>' +
            '  </div>' +
            '  <div class="viz-stage">' +
            '    <div id="' + p + '_viewport" style="position: absolute; inset: 0;"></div>' +
            '    <div class="viz-corner tl"></div><div class="viz-corner tr"></div>' +
            '    <div class="viz-corner bl"></div><div class="viz-corner br"></div>' +
            '    <div class="viz-status" id="' + p + '_status">' + TX(STATUS_STANDBY) + '</div>' +
            '    <div class="viz-heatlegend" id="' + p + '_heatlegend" style="display: none;">' +
            '      <div id="' + p + '_hl_head" title="' +
                     escAttr(TX(HEAT_LEGEND_DEBT_NOTE)) + '">' +
                     heatLegendHead() + '</div>' +
            '      <div class="bar"></div>' +
            '      <div class="lbl"><span id="' + p + '_hl_min">—</span><span id="' + p + '_hl_max">—</span></div>' +
            '      <div class="tw" id="' + p + '_hl_wall">—</div>' +
            /* ÖH P11B1-01: çözücünün cidar hükmü için ayrı satır. Boşken
               gizli durur (uydurma rozet yok), doluysa kırmızı basar. */
            '      <div class="tw" id="' + p + '_hl_verdict" style="display: none;"></div>' +
            '    </div>' +
            '  </div>' +
            designHtml +
            cfdGroupHtml(p) +
            '  <div class="viz-timeline">' +
            '    <button class="viz-play" id="' + p + '_play">&#9654;</button>' +
            '    <input type="range" id="' + p + '_slider" min="0" max="1000" value="0">' +
            '    <div class="viz-clock" id="' + p + '_clock">t = ' + numTxt(0, 2) + ' s / — s</div>' +
            '  </div>' +
            '  <div class="viz-telemetry">' +
            chips.map(function (c) {
                return '<div class="viz-chip" id="' + c.id + '_chip">' +
                    '<div class="k" id="' + c.id + '_k">' + TXK(c.label) + '</div>' +
                    '<div class="v" id="' + c.id + '">—</div></div>';
            }).join('') +
            '  </div>' +
            '</div>';
    }

    function create(containerId, motorData, opts) {
        var host = el(containerId);
        if (!host) return null;
        if (!(window.MotorViz3D && MotorViz3D.isSupported())) return null;

        opts = Object.assign({
            title: DEFAULT_TITLE,
            subtitle: DEFAULT_SUBTITLE,
            motorType: motorData.viz_motor_type || 'hybrid',
            portShape: 'circular'
        }, opts || {});
        motorData.viz_motor_type = opts.motorType;

        var p = 'vzd' + (++UID);
        var chips = chipList(p, opts, motorData);
        var ctrls = designControls(opts, motorData);
        var chipIds = {};
        chips.forEach(function (c) { chipIds[c.id] = true; });
        // ÖH D28 · OH-D27-14 — KONTEYNERİN TEK SAHİBİ OLMALI.
        // ÖLÇÜLDÜ (D27 arayuz a1 riskler §2): güverte gövdesi buraya
        // YAZILDIKTAN sonra `MotorViz3D.mount` başarısız olursa (aşağıda
        // `if (!viz) return null;`) create null döner, ama yazdığı gövde
        // konteynerde KALIR. Çağıran o null'ı görüp eski yedek yola düşer
        // (solid.html: `Plotly.newPlot('cad_3d_view', ...)` kendi
        // "CAD geometry not returned by the solver" raporuyla) ve aynı
        // konteynerde İKİ ayrı red raporu yarışır — kullanıcının hangisini
        // gördüğü Plotly'nin gövdeyi temizleme sırasına kalır.
        // Kural: bu işlev başarısız dönerse konteyneri BULDUĞU GİBİ bırakır.
        var oncekiGovde = host.innerHTML;
        function govdeyiGeriAl() { host.innerHTML = oncekiGovde; }
        host.innerHTML = deckHtml(p, opts, chips, ctrls);

        // Statik (zamanla değişmeyen) çip değerleri bir kez yazılır
        var staticPcBar = isNum(motorData.chamber_pressure) ? motorData.chamber_pressure : null;
        var epsValue = expansionRatio(motorData);

        var hudLast = 0;
        // CFD grubu ancak sahne kurulup grup kablolandıktan SONRA
        // tazelenir: mount sırasında düşen ilk kareler `viz` daha
        // atanmamışken onTick'i çağırabiliyor.
        var cfdSyncArmed = false;
        // ÖH D36 / onemli2-sivi a2: zaman ekseni yalnız GERÇEK bir yanma
        // süresiyle çizilir (NO_TIME_AXIS_TEXT notu). Döner: eksen var mı.
        function zamanEkseni(bt) {
            var varMi = isNum(bt) && bt > 0;
            var play = el(p + '_play'), slider = el(p + '_slider');
            var clock = el(p + '_clock');
            if (play) play.style.display = varMi ? '' : 'none';
            if (slider) slider.style.display = varMi ? '' : 'none';
            if (clock) {
                clock.setAttribute('data-no-time', varMi ? '' : '1');
                if (!varMi) clock.textContent = TX(NO_TIME_AXIS_TEXT);
            }
            return varMi;
        }

        var viz = MotorViz3D.mount(p + '_viewport', motorData, {
            onTick: function (s) {
                var now = performance.now();
                if (now - hudLast < HUD_THROTTLE_MS) return;
                hudLast = now;
                var play = el(p + '_play'), slider = el(p + '_slider');
                var clock = el(p + '_clock'), status = el(p + '_status');
                if (!play || !slider) return;
                var zaman = zamanEkseni(s.burnTime);
                play.innerHTML = s.playing ? '&#10074;&#10074;' : '&#9654;';
                play.classList.toggle('burning', s.burning);
                if (zaman) {
                    var pr = (s.time / s.burnTime) * 1000;
                    slider.value = pr;
                    slider.style.setProperty('--p', (pr / 10) + '%');
                    clock.innerHTML = 't = <b>' + numTxt(s.time, 2) + '</b> s / ' + numTxt(s.burnTime, 2) + ' s';
                }
                if (status) {
                    // Durum metni onTick'te YENİDEN yazıldığı için dil
                    // değişimini kendiliğinden yakalar; kaynağı da veri
                    // niteliğinde saklanır ki duran sahnede refreshLabels
                    // aynı durumu doğru dilde tazeleyebilsin.
                    // a2: süre yoksa "yanma bitti" denmez (zaman ekseni yok).
                    var src = s.burning ? STATUS_BURNING
                            : (zaman && s.time >= s.burnTime - 1e-3
                               ? STATUS_BURNOUT : STATUS_STANDBY);
                    status.setAttribute('data-src', src);
                    status.textContent = TX(src);
                    status.classList.toggle('burning', !!s.burning);
                }
                setChip(p + '_port', numTxt(s.portDiameter, 1), 'mm', s.burning);
                // Yüzde işaretinin yeri dile bağlıdır (I18N.percent: TR "%68",
                // EN "68%"); işaret sayının içine yazılır, ayrı birim yok.
                setChip(p + '_web', pctTxt(s.webRemaining * 100, 0), '', s.burning);
                setChip(p + '_of', isNum(s.of) ? numTxt(s.of, 2) : '—', '', s.burning);
                setChip(p + '_isp', s.isp ? numTxt(s.isp, 1) : '—', 's', s.burning);
                var tv = s.thrust >= 1000 ? numTxt(s.thrust / 1000, 2) : numTxt(s.thrust, 0);
                setChip(p + '_thrust', s.thrust > 0 ? tv : '0', s.thrust >= 1000 ? 'kN' : 'N', s.burning);
                // Pc: transient eğri varsa anlık (Pa → bar), yoksa tasarım değeri
                var pcBar = isNum(s.pc) ? s.pc / PA_PER_BAR : staticPcBar;
                setChip(p + '_pc', isNum(pcBar) ? numTxt(pcBar, 1) : '—', 'bar',
                        s.burning && isNum(s.pc));
                // CFD alanı Merkez'den bindirilebilir; grubu sahnenin
                // GERÇEK durumundan tazele (imza değişmediyse yazmaz).
                if (cfdSyncArmed) cfdSyncFromScene();
            },
            // Kalite değişimi (otomatik perf düşüşü dahil) HQ butonuna yansır
            onQualityChange: function (mode) {
                var qb = el(p + '_btn_quality');
                if (!qb) return;
                qb.textContent = mode === 'perf' ? 'PERF' : 'HQ';
                qb.classList.toggle('active', mode === 'perf');
            }
        });
        if (!viz) { govdeyiGeriAl(); return null; }
        // a2: ilk kare gelmeden (gizli sekmede onTick hiç düşmeyebilir)
        // zaman ekseninin durumu sahnenin GERÇEK süresinden kurulur.
        zamanEkseni(viz.dims && viz.dims.burnTime);
        if (opts.portShape !== 'circular' && opts.motorType !== 'liquid') {
            viz.setPortShape(opts.portShape);
            syncPortBtn();
        }

        // Zamanla değişmeyen çipler
        if (epsValue !== null) setChip(p + '_eps', numTxt(epsValue, 1), '', false);
        if (isNum(motorData.throat_diameter)) {
            setChip(p + '_dt', numTxt(motorData.throat_diameter * 1000, 1), 'mm', false);
        }

        function setChip(id, val, unit, hot) {
            if (!chipIds[id]) return;          // bu motor tipinde çip yok
            var e = el(id);
            if (e) e.innerHTML = val + (unit ? '<small>' + unit + '</small>' : '');
            var chip = el(id + '_chip');
            if (chip) chip.classList.toggle('hot', !!hot);
        }

        function toggleBtn(btnId, prop, setter) {
            var b = el(btnId);
            if (!b) return;
            b.onclick = function () {
                var next = !viz.state[prop];
                setter.call(viz, next);
                b.classList.toggle('active', next);
            };
        }

        function syncPortBtn() {
            var b = el(p + '_btn_portshape');
            if (!b) return;
            b.textContent = TX('Port') + ': ' + portLabel(viz.state.portShape);
            b.classList.toggle('active', viz.state.portShape !== 'circular');
        }

        toggleBtn(p + '_btn_cut', 'cutaway', viz.setCutaway);
        toggleBtn(p + '_btn_dim', 'labels', viz.setLabels);
        toggleBtn(p + '_btn_plume', 'plume', viz.setPlume);
        toggleBtn(p + '_btn_exp', 'exploded', viz.setExploded);
        toggleBtn(p + '_btn_rot', 'autoRotate', viz.setAutoRotate);
        var resetBtn = el(p + '_btn_reset');
        if (resetBtn) resetBtn.onclick = function () { viz.resetCamera(); };

        // Frame/PNG: görünür karenin PNG'sini indirir (senkron snapshot —
        // preserveDrawingBuffer gerektirmez, motor_viz3d.js görev 7)
        var frameBtn = el(p + '_btn_frame');
        if (frameBtn) frameBtn.onclick = function () {
            var url = viz.snapshot();
            if (!url) return;
            var a = document.createElement('a');
            a.href = url;
            a.download = 'hrma_motor_' + opts.motorType + '_' + Date.now() + '.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        };

        // Kamera preset döngüsü (Iso → Side → Nozzle → Injector)
        var camBtn = el(p + '_btn_cam');
        var camPreset = 'iso';
        if (camBtn) camBtn.onclick = function () {
            var name = viz.cycleCameraPreset();
            if (!name) return;
            camPreset = name;
            camBtn.textContent = TX('Cam') + ': ' + camLabel(name);
        };
        // Kalite anahtarı: HQ ↔ PERF (düşük pixelRatio + az partikül)
        var qBtn = el(p + '_btn_quality');
        if (qBtn) qBtn.onclick = function () {
            var mode = qBtn.textContent === 'HQ' ? 'perf' : 'high';
            viz.setQuality(mode);
            qBtn.textContent = mode === 'perf' ? 'PERF' : 'HQ';
            qBtn.classList.toggle('active', mode === 'perf');
        };
        // Oynatma hızı döngüsü (0.5× → 1× → 2× → 4×) — hibrit güverte paritesi
        var speedBtn = el(p + '_btn_speed');
        if (speedBtn) speedBtn.onclick = function () {
            var sp = viz.cycleSpeed();
            speedBtn.innerHTML = (sp % 1 === 0 ? sp : numTxt(sp, 1)) + '&times;';
            speedBtn.classList.toggle('active', sp !== 1);
        };

        var portBtn = el(p + '_btn_portshape');
        if (portBtn) portBtn.onclick = function () { viz.cyclePortShape(); syncPortBtn(); };

        /* --- Isı haritası efsanesinin HÜKÜM satırı (ÖH P11B1-01) ----------
           ÖLÇÜLEN KUSUR (varsayılan hibrit koşusu): efsane
           `T_wall inner 3283 K / outer 3256 K` diye ÇIPLAK sayı basıyordu.
           Aynı yükte duran ve sahnenin HİÇ okumadığı alanlar:
             heat_transfer_analysis.gas_side_analysis
               .wall_temperature_unphysical = true
             …warnings[] = warn.thermal.wall_exceeds_melting  (critical;
               T_wall 3283 K ⟷ steel_4130 erime 1705 K — erimenin 1,93 katı)
             …warnings[] = warn.thermal.wall_pinned_adiabatic (critical;
               yani ekrandaki sayı bir cidar sıcaklığı DEĞİL, çözücünün
               adyabatik cidara SABİTLEDİĞİ yer tutucu)
           Sonuç: eriyen bir motorun ısı haritası sağlıklıymış gibi
           görünüyordu. Efsane artık çözücünün hükmünü de basar.

           Hüküm burada ÜRETİLMEZ: kayıt yükten okunur, metni I18N.tf ile
           kendi kodundan kurulur (iki dilde de tanımlı). Yükte hüküm yoksa
           satır hiç görünmez — uydurma rozet yasak. Bayrak açık ama hüküm
           yayımlanmamışsa satır yine de basılır ve alanın MAKİNE ADINI
           yazar; "fizik-dışı" bayrağı asla sessiz kalmaz. */
        function escText(s) {
            return String(s === null || s === undefined ? '' : s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        function heatVerdict() {
            var ht = (motorData && motorData.heat_transfer_analysis) || {};
            var gas = ht.gas_side_analysis || {};
            var seen = Object.create(null);
            var texts = [];
            [gas.warnings, (ht.safety_analysis || {}).warnings,
             (ht.wall_analysis || {}).warnings].forEach(function (list) {
                (Array.isArray(list) ? list : []).forEach(function (w) {
                    if (typeof w === 'string') {
                        if (!/^CRITICAL\b/i.test(w.trim())) return;
                        if (seen[w]) return;
                        seen[w] = true;
                        texts.push(w.trim());
                        return;
                    }
                    if (!w || String(w.severity || '').toLowerCase() !== 'critical') return;
                    var params = w.params || {};
                    var id = w.code + '|' + Object.keys(params).sort()
                        .map(function (k) { return k + '=' + String(params[k]); }).join(',');
                    if (seen[id]) return;
                    seen[id] = true;
                    texts.push((window.I18N && window.I18N.tf)
                        ? window.I18N.tf(w.code, params, w.fallback || w.code)
                        : (w.fallback || w.code));
                });
            });
            return {
                unphysical: gas.wall_temperature_unphysical === true,
                texts: texts
            };
        }

        /* --- Cidar sıcaklığının KAYNAK BEYANI (Z5-C5) ---------------------
           Efsanedeki cidar sıcaklığı satırı, sayı YOKSA eskiden BOŞ kalıyordu
           — kullanıcı "ölçülmedi mi, sıfır mı, hata mı?" ayrımını yapamıyordu.
           Sıvı motorda blok (Z5-C5) cidar sıcaklığını yalnız ÇÖZÜLDÜĞÜNDE
           yayımlar; çözülmediğinde sayı yerine çözücünün KENDİ kaynak beyanı
           basılır. Metin burada ÜRETİLMEZ: yükteki alan adı + değeri ham
           geçer (makine dizesi — çeviri anahtarı açılmaz).

           ÖH D29 · OH-D17-26 — BEYAN, DIŞ SICAKLIK VARKEN DE BASILIR.
           ÖLÇÜLDÜ (a2/once.json OH-D17-26, `erken_cikis_ikili_veya: true`):
           erken çıkış koşulu `info.tWallInner || info.tWallOuter` idi; iki
           sayıdan HERHANGİ biri gelince beyan tümden susuyordu. Katı motor
           (`hrma/engines/solid_rocket_engine.py:12849`) `inner_temperature`ı
           bile bile `None` yayımlıyor — kendi yorumuyla: bir varsayımı iç
           cidar sıcaklığı diye göstermemek için — ve yanına yalnız
           `outer_temperature` ile kaynak künyesini koyuyor. Dış sayı geldiği
           için beyan susuyor, efsanede önünde boş slaş duran tek bir sayı
           (`/ outer … K`) kalıyor ve kullanıcı iç cidarın HİÇ çözülmediğini
           göremiyordu.
           İki dal:
             (1) hiçbir sayı yok    -> eski davranış (tam kaynak beyanı),
             (2) dış var / iç yok   -> `wallTempInnerMissing` dalı: sayı
                 gizlenmez, yanına iç cidarın çözülmediği ve çözücünün
                 künyesi yazılır.
           Uydurma yok: künye yükte yoksa satır yalnız alanın MAKİNE ADINI
           söyler (`wall_analysis.inner_temperature = null`). */
        var wallTempInnerMissing = 'wall_analysis.inner_temperature = null';

        function wallTempKunye() {
            var ht = (motorData && motorData.heat_transfer_analysis) || {};
            var wall = ht.wall_analysis || {};
            var src = wall.wall_temperature_source;
            if (wall.wall_temperature_status) {
                return 'wall_temperature_status: '
                    + escText(wall.wall_temperature_status)
                    + (src ? ' (' + escText(src) + ')' : '');
            }
            if (src) return 'wall_temperature_source: ' + escText(src);
            return '';
        }

        function wallTempNote(info) {
            var icVar = !!(info && info.tWallInner);
            var disVar = !!(info && info.tWallOuter);
            if (icVar) return '';           // iç cidar çözüldü: beyan gerekmez
            var kunye = wallTempKunye();
            if (disVar) {
                // (2) Dış sayı var, iç yok — SAYININ YANINDA eksik olanın adı.
                return ' · ' + TX('T_wall inner') + ': '
                    + wallTempInnerMissing
                    + (kunye ? ' (' + kunye + ')' : '');
            }
            // (1) Hiç sayı yok — eski davranış.
            return kunye ? TX('T_wall') + ': ' + kunye : '';
        }

        function syncHeatVerdict() {
            var box = el(p + '_hl_verdict');
            if (!box) return;
            var vd = heatVerdict();
            if (!vd.unphysical && !vd.texts.length) {
                box.innerHTML = '';
                box.style.display = 'none';
                return;
            }
            var body = vd.texts.length
                ? vd.texts.map(escText).join('<br>')
                : 'wall_temperature_unphysical = true';
            box.innerHTML = '<b>' + escText(T('app.warn.critical', 'CRITICAL'))
                + '</b> ' + body;
            box.style.color = '#ff7a85';
            box.style.whiteSpace = 'normal';
            box.style.lineHeight = '1.35';
            box.style.marginTop = '4px';
            box.style.maxWidth = '280px';
            box.style.display = 'block';
        }

        var heatBtn = el(p + '_btn_heat');
        // Isıl analiz verisi olmayan motorlarda (örn. katı — yer tutucu akı)
        // buton hiç gösterilmez
        if (heatBtn && !viz.getHeatInfo()) {
            heatBtn.style.display = 'none';
            heatBtn = null;
        }
        if (heatBtn) heatBtn.onclick = function () {
            var info = viz.getHeatInfo();
            var legend = el(p + '_heatlegend');
            if (!info) {
                heatBtn.classList.remove('active');
                if (legend) legend.style.display = 'none';
                heatBtn.textContent = TX('Heat Map (no data)');
                setTimeout(function () { heatBtn.textContent = TX('Heat Map'); }, 1800);
                return;
            }
            var on = viz.setHeatMap(!viz.state.heatMap);
            heatBtn.classList.toggle('active', on);
            if (legend) {
                legend.style.display = on ? 'block' : 'none';
                if (on) {
                    var fmt = function (q) {
                        return q >= 1e6 ? unitTxt(q / 1e6, 'MW/m²', 2)
                                        : unitTxt(q / 1e3, 'kW/m²', 0);
                    };
                    // ÖH D24 · P11B1-02: uçlara RAMPANIN kendi alanı yazılır.
                    // Eskiden sol uca `info.qChamber` yazılıyordu; rampanın
                    // t=0'ı log ölçeğinde qC·0,6'ya oturduğu için etiket
                    // bandın dibini 1,6667 kat yanlış adlandırıyordu.
                    el(p + '_hl_min').textContent = fmt(info.qRampMin);
                    el(p + '_hl_max').textContent = fmt(info.qRampMax);
                    // OH-D17-26: ayırıcı slaş yalnız İKİ sayı da varken
                    // yazılır — iç cidar çözülmediğinde satır eskiden
                    // `/ outer … K` diye boş slaşla başlıyordu.
                    el(p + '_hl_wall').textContent =
                        (info.tWallInner
                            ? TX('T_wall inner') + ' ' + unitTxt(info.tWallInner, 'K', 0) : '') +
                        (info.tWallOuter
                            ? (info.tWallInner ? ' / ' + TX('outer') + ' ' : TX('T_wall outer') + ' ')
                              + unitTxt(info.tWallOuter, 'K', 0) : '') +
                        wallTempNote(info);
                    // Çıplak sayının yanında çözücünün hükmü (ÖH P11B1-01)
                    syncHeatVerdict();
                }
            }
        };

        /* --- CFD alanı denetim grubu --------------------------------------
           Güverte alanı KENDİ yüklemez (CFD koşumu Analiz Merkezi'nin CFD
           kiracısında yapılır ve oradan sahneye bindirilir). Buradaki
           denetimler YALNIZ sahnede GERÇEKTEN yüklü bir alanı sürer:
           sahnenin getCfdField() beyanı okunur, alan yoksa grup gri kalır
           ve nedeni yazılır. Hiçbir sayı burada hesaplanmaz; aralık
           sahnenin döndürdüğü sözlükten gelir. Hangi büyüklüğün yükte
           bulunduğu da ÖLÇÜMDÜR: beyanın metrics listesi (sahnenin
           cfdFieldHasMetric süzgeci) — bu sayede yükte olmayan metriğin
           düğmesi TIKLANMADAN önce gri durur. */
        var cfdSig = null;               // son yazılan durumun imzası
        var cfdMissing = {};             // ÖLÇÜLEN 'missing_metric' kimlikleri

        function cfdSetStatus(text) {
            var e = el(p + '_cfd_status');
            if (e) e.textContent = text;
        }

        /* Yükte GERÇEKTEN bulunan metrikler. ÖLÇÜM SAHNEDE yapılır
           (getCfdField().metrics — motor_viz3d.js'in cfdFieldHasMetric
           süzgeci); güvertede süzgecin kopyası YOKTUR, burada yalnız
           yayımlanan listeye bakılır. Sahne listeyi yayımlamıyorsa ölçüm
           yoktur: o durumda hiçbir düğme ölçümsüz gerekçeyle kapatılmaz
           ("ölçüm yok" ile "yok ölçüldü" ayrı şeylerdir) — sahnenin listeyi
           yayımladığını tests/test_cfd_deck_ongri.py ölçer. */
        function cfdPayloadMetrics(st) {
            return (st && Array.isArray(st.metrics)) ? st.metrics : null;
        }

        // Yükte olmadığı ÖLÇÜLMÜŞ metrik mi? (liste yoksa iddia yok)
        function cfdNotInPayload(st, id) {
            var list = cfdPayloadMetrics(st);
            return !!list && list.indexOf(id) < 0;
        }

        /* ÖH D24 / P11B1-08 — sahnenin SON REDDİ (ölçüm bloğu, yoksa null).
           Sahne bir alanı reddettiğinde yüklü alan null KALIR; imza da
           boş kalırsa güverte hiçbir zaman yazmaz ve kurulumdaki
           "CFD'yi koştur ve sahneye gönder" cümlesi asılı kalır. Red
           bloğu imzaya girer: red DEĞİŞTİĞİNDE durum satırı tazelenir. */
        function cfdRejectBlock() {
            return (viz && typeof viz.getCfdReject === 'function')
                ? viz.getCfdReject() : null;
        }

        function cfdStateSig(st) {
            if (!st) {
                var rj = cfdRejectBlock();
                if (!rj) return '';
                var pr = '';
                try { pr = JSON.stringify(rj.params || {}); } catch (e) { pr = ''; }
                return 'reject|' + String(rj.code) + '|' + pr;
            }
            return [st.metric, st.range && st.range.min, st.range && st.range.max,
                    st.stations && st.stations.shown,
                    st.stations && st.stations.total,
                    st.decimated ? 1 : 0,
                    // Yüklü alanın metrik kümesi imzaya girer: alan
                    // değişince (ör. sıcaklıksız yükten sıcaklıklı yüke)
                    // düğmelerin gri/açık durumu tazelenmeli
                    (cfdPayloadMetrics(st) || []).join(','),
                    Object.keys(cfdMissing).sort().join('+')].join('|');
        }

        function cfdDefaultStatus(st) {
            if (!st) {
                /* ÖH D24 / P11B1-08 — YAPILMIŞ İŞİ TEKRAR İSTEME.
                   Kullanıcı CFD'yi koşup "Show in the 3D scene"e bastıysa
                   ve sahne REDDETTİYSE, aynı cümleyi bir daha yazmak
                   yalandır: iş yapıldı, sahne kabul etmedi. Gerçek
                   gerekçe (sözleşme kodu + ölçülen sapma sayıları)
                   `cfdReasonText` ile aynı satıra yazılır. */
                var rj = cfdRejectBlock();
                if (rj) {
                    return T('viz.cfd.rejected',
                        'The 3D scene REFUSED the CFD field that was sent; '
                        + 'nothing is drawn. Reason:')
                        + ' ' + cfdReasonText(rj);
                }
                return T('viz.cfd.none',
                    'No CFD field is loaded into the scene. When a CFD run in '
                    + 'the Analysis Centre returns a field, it is sent here '
                    + 'automatically and the CFD panel can send it again; '
                    + 'these controls stay disabled until then.');
            }
            var m = cfdMetricById(st.metric);
            var txt = T('viz.cfd.showing', 'Showing') + ' '
                + (m ? T(m.labelKey, m.labelFallback) : String(st.metric))
                + ' — ' + st.cells.axial + 'x' + st.cells.radial + ' '
                + T('viz.cfd.cells', 'solver cells') + ', '
                + st.stations.shown + '/' + st.stations.total + ' '
                + T('viz.cfd.stations', 'axial stations');
            if (st.decimated) {
                txt += '. ' + T('viz.cfd.decimated',
                    'The endpoint thinned the field before it was sent; the '
                    + 'scene shows exactly the cells that arrived.');
            }
            return txt;
        }

        /* Düğmeler + aralık yazısı. Durum satırına DOKUNMAZ (tıklama
           sonucu metni ezilmesin); varsayılan metni yazmak için
           `writeStatus` verilir. */
        function cfdRefresh(writeStatus) {
            var st = (viz && typeof viz.getCfdField === 'function')
                ? viz.getCfdField() : null;
            if (!st) cfdMissing = {};
            var grup = el(p + '_cfd');
            if (grup) grup.classList.toggle('active', !!st);
            var m = st ? cfdMetricById(st.metric) : null;
            var rng = el(p + '_cfd_range');
            if (rng) {
                rng.textContent = st
                    ? (cfdNum(st.range.min) + ' … ' + cfdNum(st.range.max)
                       + (m && m.unit ? ' ' + m.unit : ''))
                    : '—';
            }
            cfdMetrics().forEach(function (mm) {
                var b = el(p + '_cfd_m_' + mm.id);
                if (!b) return;
                /* İki ölçümün BİRLEŞİMİ:
                   yukDisi  — sahnenin yayımladığı listede yok (tıklamadan
                              ÖNCE bilinir),
                   redYedi  — tıklandığında sahne 'missing_metric' döndürdü
                              (koşum ölçümü; liste yayımlanmayan bir sahnede
                              tek kanıt budur, bu yüzden kalır). */
                var yukDisi = cfdNotInPayload(st, mm.id);
                var redYedi = !!cfdMissing[mm.id];
                b.disabled = !st || yukDisi || redYedi;
                b.classList.toggle('active', !!st && st.metric === mm.id);
                b.title = T(mm.labelKey, mm.labelFallback)
                    + ((yukDisi || redYedi)
                        ? ' — ' + T('viz.cfd.notInPayload',
                            'not present in the loaded field') : '');
            });
            var off = el(p + '_cfd_off');
            if (off) off.disabled = !st;
            cfdSig = cfdStateSig(st);
            if (writeStatus) cfdSetStatus(cfdDefaultStatus(st));
            return st;
        }

        /* Sahne durumu DEĞİŞTİYSE grubu tazele. onTick her karede çağrılır
           (HUD_THROTTLE_MS ile seyreltilmiş); imza aynıysa DOM'a yazılmaz —
           dönen bir gösterge ya da sahte ilerleme yoktur, yalnız gerçek
           durum yansıtılır. */
        function cfdSyncFromScene() {
            var st = (viz && typeof viz.getCfdField === 'function')
                ? viz.getCfdField() : null;
            if (cfdStateSig(st) === cfdSig) return;
            cfdRefresh(true);
        }

        cfdMetrics().forEach(function (mm) {
            var b = el(p + '_cfd_m_' + mm.id);
            if (!b) return;
            b.onclick = function () {
                var res = viz.setCfdMetric(mm.id);
                if (res && res.ok) {
                    cfdMissing[mm.id] = false;
                    cfdRefresh(false);
                    cfdSetStatus(cfdDefaultStatus(viz.getCfdField()));
                } else {
                    var reason = res && res.reason;
                    if (reason && reason.code === 'missing_metric') {
                        cfdMissing[mm.id] = true;
                    }
                    cfdRefresh(false);
                    cfdSetStatus(cfdReasonText(reason));
                }
            };
        });
        var cfdOff = el(p + '_cfd_off');
        if (cfdOff) cfdOff.onclick = function () {
            var kalkti = viz.clearCfdField();
            cfdRefresh(false);
            cfdSetStatus(kalkti
                ? T('viz.cfd.cleared',
                    'The field layer was removed from the scene and the '
                    + 'decorative layers came back.')
                : T('viz.cfd.nothingToClear',
                    'The scene carried no field layer, so nothing was '
                    + 'removed.'));
        };
        cfdRefresh(true);
        cfdSyncArmed = true;

        // --- Tasarım modu: slider → geometri önizlemesi (istemci tarafı) -----
        // Katı/sıvı için hibritteki /api/quick-geometry karşılığı YOKTUR; bu
        // yüzden burada YALNIZ 3D geometri yeniden kurulur, performans
        // değerleri (itki/Isp/Pc) DEĞİŞTİRİLMEZ ve panelde bu açıkça yazar.
        var designTimer = null;
        var designBtn = el(p + '_btn_design');
        if (designBtn && ctrls.length) {
            designBtn.onclick = function () {
                var panel = el(p + '_design');
                if (!panel) return;
                var open = panel.style.display === 'none';
                panel.style.display = open ? 'flex' : 'none';
                designBtn.classList.toggle('active', open);
                if (open) designInit();
            };
        }

        function designSliderValue(c) {
            var input = el(p + '_ds_' + c.key);
            if (!input) return c.val;
            return c.lo + (c.hi - c.lo) * (parseFloat(input.value) / DESIGN_SLIDER_STEPS);
        }

        function designInit() {
            ctrls.forEach(function (c) {
                var input = el(p + '_ds_' + c.key);
                if (!input) return;
                input.value = Math.round(((c.val - c.lo) / (c.hi - c.lo)) * DESIGN_SLIDER_STEPS);
                input.oninput = function () {
                    designReadouts();
                    clearTimeout(designTimer);
                    designTimer = setTimeout(designApply, DESIGN_DEBOUNCE_MS);
                };
            });
            designReadouts();
        }

        function designReadouts() {
            ctrls.forEach(function (c) {
                var out = el(p + '_dv_' + c.key);
                if (out) out.textContent = c.fmt(designSliderValue(c));
            });
        }

        function designApply() {
            var next = shallowClone(motorData);
            var isSolid = opts.motorType === 'solid';
            ctrls.forEach(function (c) {
                var v = designSliderValue(c);
                if (c.key === 'dch') {
                    next.chamber_diameter = v;
                } else if (c.key === 'len') {
                    if (isSolid) {
                        // Katıda slider grain boyunu sürer; kasa boyu grain'i
                        // sarmalı (extractDims Lg'yi 0.92·Lch ile kırpar)
                        next.grain_length = v;
                        next.chamber_length = Math.max(
                            isNum(motorData.chamber_length) ? motorData.chamber_length : v / 0.9,
                            v / 0.9);
                    } else {
                        next.chamber_length = v;
                    }
                } else if (c.key === 'eps') {
                    // ε = (de/dt)² → çıkış çapı boğazdan türetilir
                    if (isNum(next.throat_diameter)) {
                        next.exit_diameter = next.throat_diameter * Math.sqrt(v);
                    }
                }
            });
            // grain_design.grain_length_mm extractDims'te önceliklidir; önizleme
            // boyunca senkron tutulmazsa slider grain'i hiç hareket ettirmez
            if (motorData.grain_design && isNum(next.grain_length)) {
                next.grain_design = shallowClone(motorData.grain_design);
                if (isNum(next.grain_design.grain_length_mm)) {
                    next.grain_design.grain_length_mm = next.grain_length * 1000;
                }
                if (isNum(next.grain_design.outer_diameter_mm) && isNum(next.chamber_diameter)) {
                    next.grain_design.outer_diameter_mm = next.chamber_diameter * 1000;
                }
            }
            viz.update(next);
        }

        var playBtn = el(p + '_play');
        if (playBtn) playBtn.onclick = function () {
            if (viz.state.playing) viz.pause(); else viz.play();
        };
        var slider = el(p + '_slider');
        if (slider) slider.oninput = function () {
            viz.pause();
            viz.setTime((this.value / 1000) * viz.dims.burnTime);
        };

        /* --- Dil değişiminde metinleri tazele -----------------------------
           Güverte tek seferlik innerHTML ile kuruluyor; kanca olmadan dil
           değişince ekrandaki 3B güverte İLK yüklenen dilde donuyordu
           (plotly_dark.js grafikler için aynı sorunu redrawAllPlots ile
           çözüyor). Sahne yeniden kurulmaz — YALNIZ metinler yazılır, yani
           kamera açısı, oynatma konumu ve tasarım sliderları korunur. */
        function setText(id, text) {
            var e = el(id);
            if (e) e.textContent = text;
        }

        function refreshLabels() {
            var titleEl = el(p + '_title');
            if (titleEl) {
                titleEl.innerHTML = '<span class="viz-dot"></span>' + TX(opts.title);
            }
            setText(p + '_sub', TX(opts.subtitle));
            setText(p + '_btn_cut', TX('Cutaway'));
            setText(p + '_btn_dim', TX('Dimensions'));
            setText(p + '_btn_plume', TX('Exhaust'));
            setText(p + '_btn_exp', TX('Exploded'));
            setText(p + '_btn_rot', TX('Orbit'));
            setText(p + '_btn_reset', TX('Reset View'));
            setText(p + '_btn_design', TX('Design Mode'));
            setText(p + '_btn_frame', T('viz.btnFrame', 'Save PNG'));
            setText(p + '_btn_cam', TX('Cam') + ': ' + camLabel(camPreset));
            if (heatBtn) setText(p + '_btn_heat', TX('Heat Map'));
            if (el(p + '_btn_portshape')) syncPortBtn();

            var hlHead = el(p + '_hl_head');
            if (hlHead) {
                hlHead.innerHTML = heatLegendHead();
                hlHead.title = TX(HEAT_LEGEND_DEBT_NOTE);
            }
            // Hüküm satırı da yeni dilde yeniden kurulur; kaynağı yükün
            // KENDİSİ olduğu için metin donmaz (ÖH P11B1-01).
            syncHeatVerdict();
            setText(p + '_dstatus', TX(DESIGN_STATUS_TEXT));

            // Durum rozeti: duran sahnede onTick yazmaz, kaynağı okunur
            var st = el(p + '_status');
            if (st) st.textContent = TX(st.getAttribute('data-src') || STATUS_STANDBY);
            // a2: zaman ekseni beyanı da yeni dilde (kaynak: sahnenin süresi)
            var clk = el(p + '_clock');
            if (clk && clk.getAttribute('data-no-time') === '1') {
                clk.textContent = TX(NO_TIME_AXIS_TEXT);
            }

            chips.forEach(function (c) {
                var k = el(c.id + '_k');
                if (k) k.innerHTML = TXK(c.label);
            });
            ctrls.forEach(function (c) {
                var lab = el(p + '_dl_' + c.key);
                if (lab) lab.innerHTML = TX(c.label);
            });
            // CFD grubu: başlık + düğme title'ları + durum satırı yeni
            // dilde yeniden yazılır (durum satırının kaynağı sahnenin
            // GERÇEK durumudur, metin donmaz).
            setText(p + '_cfd_k', T('viz.cfd.group', 'CFD FIELD'));
            setText(p + '_cfd_off', T('viz.cfd.close', 'Close'));
            cfdRefresh(true);
        }

        if (window.I18N && typeof window.I18N.onChange === 'function') {
            window.I18N.onChange(refreshLabels);
        } else if (typeof document !== 'undefined' && document.addEventListener) {
            document.addEventListener('hrma:langchange', refreshLabels);
        }

        return {
            viz: viz, prefix: p, refreshLabels: refreshLabels,
            update: function (md) { MotorViz3D.update(md); }
        };
    }

    window.MotorVizDeck = { create: create };
})();
