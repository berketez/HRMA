/* ====================================================================
   HRMA Tank Blowdown Panel (yalnız hibrit sayfası) — A1/A10 kullanıcı yüzü
   --------------------------------------------------------------------
   Motor çözücüsü /calculate yanıtında iki dürüstlük bloğu yayımlıyor ama
   2026-08-03 denetimine kadar HİÇBİR panel bunları kullanıcıya
   göstermiyordu ("beyanı okuyan karar kapısı" kuralının UI yarısı eksikti):

     1. motor.tank_blowdown  — kendinden-basınçlı N₂O tank boşalması:
        tank basıncı(t), kamara basıncı(t), ṁ_ox(t), itki(t) eğrileri
        (kaynak: hrma/engines/hybrid_rocket_engine._tank_blowdown_block;
        model: denge iki-faz N₂O tankı, Whitmore & Chandler JPP 27(4) 2011
        + SPI enjektör + yarı-kararlı kamara — künye bloğun kendi
        'basis' alanında sunucudan gelir ve panel onu AYNEN gösterir).
     2. motor.not_modelled   — modellenmeyen fizik kalemlerinin açık
        beyanı (A10; 7 kalem). Panel beyan METİNLERİNİ sonuçtan okur,
        burada hiçbir beyan metni sabit kodlanmaz.

   SAHTE VERİ YASAĞI: yalnız bloktaki gerçek diziler çizilir. Blok yoksa,
   status 'modelled' değilse ya da seriler kendi içinde tutarsızsa HİÇBİR
   eğri üretilmez; motor_viz3d'nin "missing = modellenmedi / veri yok"
   çip kalıbıyla (gri #8a93a0) durum açıkça beyan edilir.

   Kullanım (advanced.html):
     <script src="/static/js/blowdown_panel.js"></script>
     BlowdownPanel.init({ anchorId: 'trajectoryPanel',
                          declAnchorId: 'notModelledStrip' });

   Veri akışı: init(), app.js'teki global displayCalculationResults'ı
   advanced.html'deki yörünge-eşitleme sarmalayıcısıyla AYNI desenle sarar;
   her hesap sonucunda update(results) çağrılır. Özgün işlev her koşulda
   çalışır — panel hata verse bile hesap gösterimi engellenmez.

   Bekçi testleri: tests/test_blowdown_panel.py (dosya node ile izole
   koşturulur; Plotly/DOM taklit edilir, seriler birebir doğrulanır).
   ==================================================================== */

(function () {
    'use strict';

    let cfg = {};
    let lastResults = null;

    // i18n köprüleri — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // ÖH D37 A1b panel-js · DV36-04 — EKRAN ONDALIĞI TEK KANALDAN.
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/panel-js/a1/once/olcum.json K5):
    // TR sayfada blowdown rozetleri "-0.0022", "3000.0 → 3006.6 N",
    // "2.370 kg" gibi NOKTALI ondalık basıyordu (TR panelde 6 noktalı
    // ondalık). Kök: ekran metni çıplak `.toFixed(` ile kuruluyordu;
    // kanon `I18N.number` (TR virgül, EN nokta) atlanıyordu. i18n.js
    // yoksa nokta (eski davranış). Kesme payı rozetindeki
    // `k.value.toFixed(k.digits)` BİLEREK bu turda kalır: test_d29
    // arayuz_panel_a1 o dizgeyi LİTERAL arıyor (kartta adı yok → DEVİR,
    // rapor A1b/panel-js/a1/rapor.md).
    function sayiEkran(v, n) {
        return (typeof window !== 'undefined' && window.I18N
                && typeof window.I18N.number === 'function')
            ? window.I18N.number(v, n) : v.toFixed(n);
    }
    // Sunucu üretimi serbest metin (blok uyarıları, reason/basis alanları):
    // i18n_charts.js MSG_PATTERNS çevirisinden geçer, eşleşme yoksa aynen kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    // HTML kaçışı: sunucu metinleri şablona gömülmeden önce zararsızlaştırılır.
    // Tırnaklara dokunulmaz (beyan metinleri kesme işareti taşır ve bekçi test
    // birebir karşılaştırır); metinler yalnız eleman GÖVDESİNE yazılır.
    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ==================================================================
    // >>> BLOWDOWN_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek yanıt sözlükleriyle koşturur. Seriler ÖLÇEKLENMEZ, kopyalanmaz,
    // yeniden örneklenmez: bloktaki diziler referans olarak aynen taşınır.
    // ==================================================================

    // Beklenen seri alanları — _tank_blowdown_block sözleşmesi (birimler
    // alan adında: s / bar / kg/s / N; panel hiçbir birim dönüşümü yapmaz).
    const SERIES_KEYS = ['time_s', 'tank_pressure_bar', 'chamber_pressure_bar',
                         'mdot_ox_kg_s', 'thrust_N'];

    // Kararsızlık uyarısı seçici: {code, params} sözleşmeli uyarılar içinde
    // besleme-kaynaklı yanma kararsızlığına işaret eden kod gövdeleri.
    // Bu bir metin listesi DEĞİL, vurgu süzgecidir; kod gövdesi eşleşen yeni
    // uyarılar kendiliğinden vurgulanır.
    const INSTABILITY_CODE_STEM = /chug|instab|feed_coupling|hydraulic_flip/;

    /* ÖH D27 a4 · P11B5-11 — ÇÖZÜNÜRLÜK KAPISI ADLANDIRILDI VE İLAN EDİLİR.

       ÖLÇÜLDÜ (a4/once.json, `p11b5_11_kapi_ciplak_2` = 1,
       `p11b5_11_ornek_sayisi_ekranda` = 0): geçerlilik kapısı dizi
       uzunluğunu ÇIPLAK bir sayıyla kıyaslıyordu ve serinin kaç örneklemden kurulduğu
       ekranda HİÇBİR yerde yazmıyordu. Ölçülen dejenere koşumda
       (P11B5-08 kaydı: Pc = 40 bar) seri İKİ noktaydı ve panel onu
       "sönüm eğrisi" başlığıyla, tam ölçekli bir Plotly çizgisi olarak
       çiziyordu: iki uç noktayı birleştiren düz bir doğru, eğri
       görünümünde.

       İKİ nokta bir poli-çizginin ALT SINIRIdır; aradaki hiçbir nokta
       çözülmemiştir. Bu bir mühendislik eşiği DEĞİL, geometrik olgudur:
       n = 2'de iç nokta sayısı sıfırdır. Sabit tek kaynaktır, örneklem
       sayısı da rozetle ekrana iner. */
    const MIN_POLYLINE_SAMPLES = 2;

    function isNumArray(arr) {
        if (!Array.isArray(arr) || arr.length < MIN_POLYLINE_SAMPLES) return false;
        for (let i = 0; i < arr.length; i++) {
            if (typeof arr[i] !== 'number' || !isFinite(arr[i])) return false;
        }
        return true;
    }

    // motor.not_modelled → [{key, text}] (sıra sunucunun yayım sırası).
    // Beyan metni SONUÇTAN okunur; bu dosyada beyan metni sabiti YOKTUR.
    function buildDeclarations(motor) {
        const nm = motor && motor.not_modelled;
        if (!nm || typeof nm !== 'object' || Array.isArray(nm)) return null;
        const out = Object.keys(nm)
            .filter(k => typeof nm[k] === 'string' && nm[k])
            .map(k => ({ key: k, text: nm[k] }));
        return out.length ? out : null;
    }

    // design_warnings + injector_design_detail.warnings içinden 'warn.' önekli
    // ve kararsızlık gövdeli kayıtları toplar (kod başına bir kez).
    function pickInstabilityWarnings(motor) {
        const out = [];
        const seen = {};
        function scan(list) {
            (Array.isArray(list) ? list : []).forEach(function (w) {
                if (w && typeof w === 'object' && typeof w.code === 'string'
                        && w.code.indexOf('warn.') === 0
                        && INSTABILITY_CODE_STEM.test(w.code)
                        && !seen[w.code]) {
                    seen[w.code] = true;
                    out.push(w);
                }
            });
        }
        if (motor && typeof motor === 'object') {
            scan(motor.design_warnings);
            scan(motor.injector_design_detail
                 && motor.injector_design_detail.warnings);
        }
        return out;
    }

    // Blok içi serbest-metin uyarısı kararsızlık mı? (transient_ballistics
    // '… — chugging risk (<künye>)' / 'combustion instability limit' üretir)
    //
    // ÖH D24 / OH-D23-11 (c): burada eskiden künye 'SP-8089' diye SABİT
    // yazılıydı ve BAYATTI. ÖH D18 / P2B4-08 o atfı geri çekti —
    // transient_ballistics artık künyeyi acoustic_modes'un TEK kaynağından
    // (CHUG_THRESHOLD_CITATION) alır ve o kaynak SP-8089 atfını açıkça
    // reddeder ("not attributed to it"). Aşağıdaki süzgeç künyeye değil
    // 'chug|instab' köküne baktığı için ÜRÜN doğru çalışıyordu; yanlış olan
    // yalnız bu yorumdu. Yorumun künyeyi tekrar sabitlemesi, künyenin ikinci
    // bir (bayatlayacak) kopyasını yaratmak olurdu.
    // ÖH D27 · OH-B3-02 — uç künyelerinin TEK tablosu: alan adı,
    // çeviri anahtarı, İngilizce varsayılan etiket. Panelin okuduğu
    // adlar burada bir kez yazılır; ikinci bir liste iki listenin
    // ayrışmasını davet ederdi (doktrin 4).
    // Okuma AÇIK ÖZELLİK ERİŞİMİYLE yapılır (`bd.tank_volume_basis`),
    // dinamik `bd[ad]` ile değil: dinamik erişim hem okuyana hem
    // sözleşme bekçisinin okuma envanterine (test_wave3_contract
    // `_envanter_metinden`) görünmez, yani "panel bu alanı basıyor"
    // iddiası kanıtlanamaz olurdu.
    const BASIS_FIELDS = [
        ['tank_volume_basis', function (bd) { return bd.tank_volume_basis; }],
        ['of_ratio_basis', function (bd) { return bd.of_ratio_basis; }],
        ['initial_pressure_basis',
         function (bd) { return bd.initial_pressure_basis; }],
        ['liquid_fill_fraction_basis',
         function (bd) { return bd.liquid_fill_fraction_basis; }],
        ['isp_delivered_avg_basis',
         function (bd) { return bd.isp_delivered_avg_basis; }],
        ['initial_temperature_source',
         function (bd) { return bd.initial_temperature_source; }],
        // ÖH D29 · OH-D28-03 — TANK MODELİ ZARF KÜNYESİ.
        // ÖLÇÜLDÜ (`a1/once.json` OH-D28-03): uç bu DİZE künyeyi
        // yayımlıyor (hybrid_rocket_engine.py:4698) ve panel onu 0 kez
        // basıyordu; künye, yukarıdaki P(t)/T(t) örneklerinin FİZİKSEL
        // ÇÖZÜM mü yoksa KENETLENMİŞ ZARF KENARI mı olduğunu söyleyen
        // tek metindir. Etiketi `basisLabel` HAM ALAN ADIYLA basar
        // (aşağıdaki `default` dalı): yeni çeviri anahtarı AÇILMADI,
        // çünkü i18n dosyaları D29'da kardeş kulvarın (arayuz-i18n)
        // sahasıdır; ham ad hem "ad+değer" ölçütünü karşılar hem de
        // kullanıcının hangi yanıt alanını okuduğunu gösterir.
        ['tank_model_envelope_basis',
         function (bd) { return bd.tank_model_envelope_basis; }],
    ];

    // ÖH D29 · OH-D28-03 — DÜRÜSTLÜK BAYRAKLARI (BOOL) ve KESME PAYI.
    //
    // ÖLÇÜLDÜ (`a1/once.json` OH-D28-03): uç `motor.tank_blowdown`
    // bloğunda YEDİ dürüstlük alanı daha yayımlıyor (dördü BOOL, üçü
    // SAYI) ve `blowdown_panel.js` yedisini de 0 kez basıyordu.
    // `BASIS_FIELDS` yalnız DİZE değer basar (`typeof v === 'string'`),
    // bu yüzden bayraklar oradan geçemezdi — bu tablo o boşluğu kapatır.
    // Sayılar bugün de `warnings` rozetinin SERBEST METNİNDE görünüyordu;
    // eksik olan, programatik olarak okunabilen ALAN kablosuydu (D27
    // fix-27b / D28 fix-28a borç imleri bunu ADIYLA kaydetmişti).
    //
    // Okuma AÇIK ÖZELLİK ERİŞİMİYLE yapılır (`bd.vapor_model_valid`),
    // dinamik `bd[ad]` ile DEĞİL: dinamik erişim ters-yön sözleşme
    // bekçisinin okuma envanterine (`test_wave3_contract`
    // `_envanter_metinden`) görünmez, yani "panel bu alanı basıyor"
    // iddiası kanıtlanamaz olurdu (BASIS_FIELDS'in aynı gerekçesi).
    //
    // Üçüncü sütun, bayrağın HANGİ yönünün yayımlanan eğriyi
    // SINIRLADIĞINI söyler; rozet o yönde `warn`, tersinde `info` olur.
    // Renk kuralı tek cümledir ve uydurma alarm üretmez: "yayımlanan
    // sonucu tam fiziksel çözüm olmaktan çıkaran yön = uyarı".
    const FLAG_FIELDS = [
        ['tank_saturation_band_clamped',
         function (bd) { return bd.tank_saturation_band_clamped; }, true],
        ['vapor_model_valid',
         function (bd) { return bd.vapor_model_valid; }, false],
        ['vapor_phase_integrated',
         function (bd) { return bd.vapor_phase_integrated; }, false],
        ['vapor_tail_off_leaves_model_envelope',
         function (bd) { return bd.vapor_tail_off_leaves_model_envelope; },
         true],
    ];

    //: Kesilen kuyruğun BOYU — [alan, okuyucu, ondalık, birim].
    const CUTOFF_FIELDS = [
        ['residual_oxidizer_kg',
         function (bd) { return bd.residual_oxidizer_kg; }, 3, ' kg'],
        ['residual_impulse_at_cutoff_rate_Ns',
         function (bd) { return bd.residual_impulse_at_cutoff_rate_Ns; },
         1, ' N·s'],
        ['residual_impulse_fraction_at_cutoff_rate',
         function (bd) {
             return bd.residual_impulse_fraction_at_cutoff_rate;
         }, 4, ''],
    ];

    // Etiketler LİTERAL çeviri çağrılarıyla kurulur (anahtar dizgesi
    // çağrının içinde, sabit olarak yazılıdır),
    // tablodan okunan değişken anahtarla DEĞİL: i18n ölü-çeviri bekçisi
    // (tests/test_i18n_common.py::test_every_dictionary_key_is_used)
    // anahtarın kullanımını çağrı yerinden tarar; tablodaki çıplak dizge
    // "kullanım" sayılmaz ve altı anahtar ölü çeviri diye KIRMIZI verir.
    // (Ölçüldü: ilk deneme tam olarak bu altı anahtarla kırmızı düştü.)
    function basisLabel(field) {
        switch (field) {
        case 'tank_volume_basis':
            return T('blowdown.basis.tankVolume', 'Tank volume');
        case 'of_ratio_basis':
            return T('blowdown.basis.ofRatio', 'O/F ratio');
        case 'initial_pressure_basis':
            return T('blowdown.basis.initialPressure', 'Initial tank pressure');
        case 'liquid_fill_fraction_basis':
            return T('blowdown.basis.liquidFill', 'Liquid fill fraction');
        case 'isp_delivered_avg_basis':
            return T('blowdown.basis.ispDelivered', 'Delivered Isp (average)');
        case 'initial_temperature_source':
            return T('blowdown.basis.initialTemperature',
                     'Initial tank temperature');
        default:
            // Uydurma etiket YOK: bilinmeyen alan HAM adıyla basılır.
            return String(field);
        }
    }

    function isInstabilityText(text) {
        return /chug|instab/i.test(String(text));
    }

    function buildViewModel(motor) {
        const declarations = buildDeclarations(motor);
        const declBasis = (motor && typeof motor.not_modelled_basis === 'string')
            ? motor.not_modelled_basis : null;
        const instability = pickInstabilityWarnings(motor);
        const base = { declarations: declarations, declBasis: declBasis,
                       instability: instability };

        if (!motor || typeof motor !== 'object') {
            base.mode = 'no_result';
            return base;
        }
        const bd = motor.tank_blowdown;
        if (!bd || typeof bd !== 'object') {
            // Eski sunucu yanıtı / eski proje kaydı: blok hiç yok.
            base.mode = 'no_block';
            return base;
        }
        base.basis = (typeof bd.basis === 'string') ? bd.basis : null;
        if (bd.status !== 'modelled') {
            base.mode = 'not_modelled';
            base.reason = (typeof bd.reason === 'string') ? bd.reason : '';
            base.end_event = bd.end_event || null;
            return base;
        }
        // status 'modelled' — seriler doğrulanır; tutarsızsa ÇİZİLMEZ
        // (kısmî/sahte eğri, eğrisizlikten kötüdür).
        const n = Array.isArray(bd.time_s) ? bd.time_s.length : 0;
        const consistent = SERIES_KEYS.every(function (k) {
            return isNumArray(bd[k]) && bd[k].length === n;
        });
        if (!consistent) {
            base.mode = 'invalid_block';
            return base;
        }
        base.mode = 'modelled';
        base.series = {};
        SERIES_KEYS.forEach(function (k) { base.series[k] = bd[k]; });
        // P11B5-11: çizilen serinin örneklem sayısı görünüm modeline girer.
        base.sample_count = n;
        base.feed_mode = bd.feed_mode || null;
        base.end_event = bd.end_event || null;
        base.burn_duration_s = (typeof bd.burn_duration_s === 'number')
            ? bd.burn_duration_s : null;
        base.total_impulse_Ns = (typeof bd.total_impulse_Ns === 'number')
            ? bd.total_impulse_Ns : null;
        base.thrust_decay_fraction = (typeof bd.thrust_decay_fraction === 'number'
                                      && isFinite(bd.thrust_decay_fraction))
            ? bd.thrust_decay_fraction : null;
        base.initial_pressure_bar = (typeof bd.initial_pressure_bar === 'number')
            ? bd.initial_pressure_bar : null;
        // ÖH D26 / OH-B4-04 — FAZ KANALI. Uç bu bloğu artık alan olarak
        // yayımlıyor (tank_phase serisi + tank_phase_final + vapor_onset_s
        // + tank_phase_basis künyesi); panel onu okumazsa kullanıcı kuyruk
        // fazının nerede başladığını yine göremezdi. Seri, zaman ekseniyle
        // AYNI uzunlukta değilse KULLANILMAZ (kısmî/yanlış hizalı etiket,
        // etiketsizlikten kötüdür) — sayı/etiket uydurulmaz.
        const faz = Array.isArray(bd.tank_phase) ? bd.tank_phase : null;
        base.tank_phase = (faz && faz.length === n) ? faz : null;
        base.tank_phase_final = (typeof bd.tank_phase_final === 'string'
                                 && bd.tank_phase_final)
            ? bd.tank_phase_final : null;
        base.vapor_onset_s = (typeof bd.vapor_onset_s === 'number'
                              && isFinite(bd.vapor_onset_s))
            ? bd.vapor_onset_s : null;
        base.tank_phase_basis = (typeof bd.tank_phase_basis === 'string')
            ? bd.tank_phase_basis : null;
        // ÖH D27 · OH-B3-02 — KARDEŞ KÜNYELER (borç imi P13B4-01).
        // ÖLÇÜLDÜ (a2/once.json `blowdown_kunye_okumasi`): uç ALTI künye
        // alanı yayımlıyor, panel yalnız çıplak `basis`i basıyordu; yani
        // ekrandaki altı sayının (tank hacmi, O/F, başlangıç basıncı,
        // doluluk oranı, sağlanan Isp, başlangıç sıcaklığı) NEREDEN
        // geldiği kullanıcıya hiç ulaşmıyordu. Künye UYDURULMAZ: alan
        // yoksa satır da yoktur.
        base.kunyeler = BASIS_FIELDS
            .map(function (t) {
                var v = t[1](bd);
                return (typeof v === 'string' && v)
                    ? { field: t[0], text: v }
                    : null;
            })
            .filter(function (x) { return x !== null; });
        // ÖH D29 · OH-D28-03 — bayraklar ve kesme payı görünüm modeline
        // girer. Değer UYDURULMAZ: alan yoksa (eski sunucu yanıtı / eski
        // proje kaydı) satır da yoktur; `typeof` kapısı bir `null`ı
        // "false" ya da "0" diye BASMAYI engeller.
        base.bayraklar = FLAG_FIELDS
            .map(function (t) {
                var v = t[1](bd);
                return (typeof v === 'boolean')
                    ? { field: t[0], value: v, limitsAt: t[2] }
                    : null;
            })
            .filter(function (x) { return x !== null; });
        base.kesme = CUTOFF_FIELDS
            .map(function (t) {
                var v = t[1](bd);
                return (typeof v === 'number' && isFinite(v))
                    ? { field: t[0], value: v, digits: t[2], unit: t[3] }
                    : null;
            })
            .filter(function (x) { return x !== null; });
        base.warnings = (Array.isArray(bd.warnings) ? bd.warnings : [])
            .filter(function (w) { return typeof w === 'string' && w; });
        return base;
    }
    // <<< BLOWDOWN_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil
    // ------------------------------------------------------------------

    // Durum çipi — motor_viz3d.SOURCE_COLORS.missing ile aynı gri
    // ('modellenmedi / veri yok' kalıbı; keyfî süs rengi yok).
    const MISSING_COLOR = '#8a93a0';

    // Öznitelik bağlamı için kaçış: `esc()` TIRNAKLARA DOKUNMAZ (beyan
    // metinleri kesme işareti taşır ve gövde karşılaştıran bekçiler birebir
    // eşleşme bekler). Öznitelik içine yazarken çift tırnak kapatılmalıdır.
    function escAttr(value) {
        return esc(value).replace(/"/g, '&quot;');
    }

    // ÖH D33-KOLAY · P11B5-11 — ÜÇÜNCÜ ARGÜMAN ARTIK YUTULMUYOR.
    // ÖLÇÜLDÜ (a1/once.json · M9, arg sayımı): `badge()` İKİ parametre
    // alıyordu, ama örneklem rozeti ÜÇ argümanla çağrılıyordu (tek çağrı
    // sahası). Üçüncüsü — "…a straight line between the end points, not a
    // decay curve." açıklaması — sessizce DÜŞÜYORDU: kullanıcı iki
    // örneklemli düz doğruyu "sönüm eğrisi" diye görmeye devam ediyordu.
    // Eski bekçi bu cümleyi KAYNAK METNİNDE arayıp yeşil veriyordu; cümle
    // dosyada VARDI, ekranda YOKTU. Açıklama artık `title` özniteliğine
    // yazılır; verilmediğinde öznitelik HİÇ açılmaz (uydurma ipucu yok).
    function badge(text, kind, title) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        const ipucu = (title === null || title === undefined || title === '')
            ? '' : ` title="${escAttr(title)}"`;
        return `<span data-warn="${kind === 'err' ? 'instability' : 'general'}"${ipucu}
                 style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    function chipHtml(label, reason) {
        let html = `<span data-chip="not-modelled" style="border:1px solid ${MISSING_COLOR};
            color:${MISSING_COLOR}; border-radius:6px; padding:4px 10px;
            font-family:var(--hd-mono); font-size:0.75rem;">${esc(label)}</span>`;
        if (reason) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0 0;">${esc(SRV(reason))}</p>`;
        }
        return html;
    }

    // {code, params} uyarısını metne çevirir — app.js::displayWarnings ile
    // aynı sözleşme; AnalysisDock yüklüyse onun çevirmeni kullanılır.
    function warnText(w, depth) {
        if (window.AnalysisDock && window.AnalysisDock.ui
                && window.AnalysisDock.ui.warnText) {
            return window.AnalysisDock.ui.warnText(w);
        }
        depth = depth || 0;
        if (w === null || w === undefined) return '';
        if (typeof w === 'string') return SRV(w);
        if (Array.isArray(w)) {
            return w.map(x => warnText(x, depth + 1)).filter(Boolean).join(' · ');
        }
        if (typeof w !== 'object') return String(w);
        if (!w.code) return SRV(w.message || w.text || JSON.stringify(w));
        if (depth > 4) return w.code;
        const p = {};
        Object.keys(w.params || {}).forEach(function (k) {
            const v = w.params[k];
            p[k] = (v && typeof v === 'object') ? warnText(v, depth + 1) : v;
        });
        return (window.I18N && window.I18N.tf)
            ? window.I18N.tf(w.code, p, w.fallback || w.code)
            : (w.fallback || w.code);
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="blowdownPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="blowdown.title">${T('blowdown.title',
                'Tank Blowdown — Pressure / Flow / Thrust Decay')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="blowdown.intro">${T('blowdown.intro',
                    'Self-pressurised N2O tank blowdown built from the solver values of '
                    + 'THIS run: tank pressure falls during the burn, oxidizer flow and '
                    + 'thrust fall with it. The headline design numbers remain the '
                    + 'regulated design point; this block is advisory. If the model '
                    + 'cannot run, no curve is drawn and the reason is stated.')}</span>
            </div>
            <div id="bp_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="bp_instability" style="margin:8px 0;"></div>
            <div id="bp_chip" style="margin:8px 0;"></div>
            <div id="bp_plot_pressure" class="plot-container" style="min-height:360px; display:none;"></div>
            <div id="bp_plot_mdot" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="bp_plot_thrust" class="plot-container" style="min-height:300px; display:none;"></div>
            <details id="bp_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="blowdown.basisTitle">${T('blowdown.basisTitle',
                    'Method / basis (as declared by the solver)')}</summary>
                <p id="bp_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></p>
                <dl id="bp_basis_fields" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0;"></dl>
            </details>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    // ------------------------------------------------------------------
    // ÖH D34 / OH-GT-05 — BİTİŞ OLAYI: ÇEVİRİLİ ETİKET + FAIL-CLOSED
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D34/metin-i18n/a1/once.json):
    // çözücünün olay kümesi SEKİZ değerdir (transient_ballistics.py,
    // ``event = '...'``) ama panellerin haritası ALTISINI tanıyordu;
    // 'chamber_below_ambient' ile 'throat_erosion_limit' sessizce 'info'
    // rozetine düşüyordu. Metin ise hiç çevrilmiyordu: ekranda ham makine
    // sabiti ('BURN_TIME_REACHED') görünüyordu.
    //
    // Kural (fail-closed): bilinmeyen değer için sessiz yedek YOK. Sözlükte
    // karşılığı olmayan olay HAM ve İŞARETLİ basılır, rozet 'warn' olur —
    // yeni bir olay eklenirse ekranda görünür, sessizce "iyi" sayılmaz.
    // Etiketlerin tek kaynağı i18n sözlüğüdür ('transient.end.<olay>');
    // kapsam bekçisi: tests/test_d34_metin_i18n_a1.py.
    // Anahtar adları BURADA HARFİ HARFİNE yazılır (birleştirilmiş dize
    // DEĞİL): ölü-çeviri bekçisi (tests/test_i18n_common.js taraması)
    // sözlük anahtarını kaynakta arar; 'transient.end.' + olay biçiminde
    // kurulan anahtar o taramada GÖRÜNMEZ ve sözlük girdisi "ölü" sayılırdı.
    // Rozet ile anahtar TEK tabloda durur — iki ayrı liste tutulmaz.
    const END_EVENTS = {
        burn_time_reached:
            { kind: 'ok', key: 'transient.end.burn_time_reached' },
        web_exhausted:
            { kind: 'ok', key: 'transient.end.web_exhausted' },
        oxidizer_depleted:
            { kind: 'info', key: 'transient.end.oxidizer_depleted' },
        injector_unstable:
            { kind: 'err', key: 'transient.end.injector_unstable' },
        feed_pressure_lost:
            { kind: 'err', key: 'transient.end.feed_pressure_lost' },
        time_limit:
            { kind: 'warn', key: 'transient.end.time_limit' },
        chamber_below_ambient:
            { kind: 'err', key: 'transient.end.chamber_below_ambient' },
        throat_erosion_limit:
            { kind: 'warn', key: 'transient.end.throat_erosion_limit' },
    };

    function endEventEntry(event) {
        return Object.prototype.hasOwnProperty.call(END_EVENTS, event)
            ? END_EVENTS[event] : null;
    }

    function endEventKind(event) {
        const kayit = endEventEntry(event);
        return kayit ? kayit.kind : 'warn';
    }

    function endEventLabel(event) {
        const ham = String(event === null || event === undefined ? '' : event);
        if (!ham) return '';
        const kayit = endEventEntry(ham);
        if (kayit && window.I18N && window.I18N.has
                && window.I18N.has(kayit.key)) {
            return T(kayit.key, ham.toUpperCase());
        }
        return ham.toUpperCase() + ' (?)';
    }

    function renderBadges(el, vm) {
        let html = '';
        if (vm.feed_mode) {
            html += badge(T('blowdown.badgeFeedMode', 'FEED') + ': '
                + esc(String(vm.feed_mode).toUpperCase()), 'info');
        }
        if (vm.end_event) {
            html += badge(T('blowdown.badgeEnd', 'END') + ': '
                + esc(endEventLabel(vm.end_event)),
                endEventKind(vm.end_event));
        }
        // P11B5-11 — KAÇ ÖRNEKLEM? Sayı HER koşumda basılır; iki
        // örneklemde "eğri" adı kazanılmamıştır ve bu SÖYLENİR.
        if (typeof vm.sample_count === 'number') {
            const az = vm.sample_count <= MIN_POLYLINE_SAMPLES;
            html += badge('SAMPLES ' + vm.sample_count,
                az ? 'warn' : 'info',
                az ? ('The blowdown series has only ' + vm.sample_count
                      + ' sample(s) — the polyline minimum. No intermediate '
                      + 'point of the decay is resolved: what is drawn is a '
                      + 'straight line between the end points, not a decay '
                      + 'curve.')
                   : (vm.sample_count + ' solver samples were drawn.'));
        }
        if (vm.burn_duration_s !== null && vm.burn_duration_s !== undefined) {
            html += badge(TF('blowdown.badgeBurn',
                { s: sayiEkran(vm.burn_duration_s, 2) }, 'BURN {s} s'), 'info');
        }
        if (vm.total_impulse_Ns !== null && vm.total_impulse_Ns !== undefined) {
            html += badge(TF('blowdown.badgeImpulse',
                { v: sayiEkran(vm.total_impulse_Ns / 1000, 1) },
                'IMPULSE {v} kN·s'), 'info');
        }
        // ÖH D15 / P11B5-08 — ETİKET İLE SAYININ İŞARETİ BİRBİRİNİ YALANLIYOR.
        // ÖLÇÜLDÜ (once.json, gerçek /calculate hibrit, yalnız Pc değişiyor):
        //   Pc=20 -> n=203, decay +0,2472, end oxidizer_depleted
        //   Pc=35 -> n= 11, decay -0,3205, end feed_pressure_lost
        //   Pc=40 -> n=  2, decay -0,0507, end feed_pressure_lost
        //     (thrust_N = [1000,0 ; 1050,67] — itki DÜŞMÜYOR, %5 ARTIYOR)
        // Panel bu iki negatif değeri "THRUST DECAY -32%" / "-5%" diye
        // adlandırıp NÖTR cyan (`info`) basıyordu: hem ad yanlış (sönüm yok),
        // hem renk "normal" diyordu, üstelik ikisi de dejenere koşu.
        //
        // Kapı: işaret negatifse "decay" adı KAZANILMAMIŞTIR — rozet makine
        // alan adına düşer (yeni çeviri anahtarı açılmadı), değerin yanına
        // seriden ölçülen ilk/son itki konur ve renk `warn` olur. Pozitif
        // değerde eski davranış birebir korunur (aşırı düzeltme yok).
        if (vm.thrust_decay_fraction !== null
                && vm.thrust_decay_fraction !== undefined) {
            const decay = vm.thrust_decay_fraction;
            if (decay < 0) {
                const th = (vm.series && Array.isArray(vm.series.thrust_N))
                    ? vm.series.thrust_N : null;
                const span = (th && th.length >= 2)
                    ? (' · thrust_N ' + sayiEkran(th[0], 1)
                       + ' \u2192 ' + sayiEkran(th[th.length - 1], 1) + ' N')
                    : '';
                html += badge('thrust_decay_fraction '
                    + sayiEkran(decay, 4) + span, 'warn');
            } else {
                html += badge(TF('blowdown.badgeDecay',
                    { pct: sayiEkran(100 * decay, 0) },
                    'THRUST DECAY {pct}%'), 'info');
            }
        }
        if (vm.initial_pressure_bar !== null
                && vm.initial_pressure_bar !== undefined) {
            html += badge(TF('blowdown.badgeInitialP',
                { v: sayiEkran(vm.initial_pressure_bar, 1) },
                'P_tank(0) {v} bar'), 'info');
        }
        // ÖH D26 / OH-B4-04: tankın FAZI. Yeni çeviri anahtarı açılmadı —
        // rozet, ucun MAKİNE ALAN ADINI ve değerini aynen basar (aynı kalıp
        // `thrust_decay_fraction` negatif dalında da kullanılıyor). 'vapor'
        // = sıvı tükendi, kuyruk ideal-gaz tahminidir: renk `warn`.
        if (vm.tank_phase_final) {
            html += badge('tank_phase_final ' + esc(vm.tank_phase_final),
                vm.tank_phase_final === 'vapor' ? 'warn' : 'info');
        }
        if (vm.vapor_onset_s !== null && vm.vapor_onset_s !== undefined) {
            html += badge('vapor_onset_s '
                + sayiEkran(vm.vapor_onset_s, 2) + ' s', 'warn');
        }
        // Seri: kaç örnek hangi fazda? (uydurma yok — sayım seriden gelir)
        if (vm.tank_phase) {
            const sayim = {};
            vm.tank_phase.forEach(function (f) {
                sayim[f] = (sayim[f] || 0) + 1;
            });
            const dokum = Object.keys(sayim).sort().map(function (f) {
                return f + ' ' + sayim[f];
            }).join(' / ');
            html += badge('tank_phase ' + esc(dokum), 'info');
        }
        // ÖH D29 · OH-D28-03 — DÜRÜSTLÜK BAYRAKLARI ve KESME PAYI.
        // Rozet ucun MAKİNE ALAN ADINI ve değerini aynen basar (aynı
        // kalıp `tank_phase_final` ve negatif `thrust_decay_fraction`
        // dallarında da kullanılıyor); yeni çeviri anahtarı açılmaz.
        // Ad ile değer AYNI rozetin içindedir — "ad+değer" süpürme
        // ölçütü (D28 bekci a1) bunu şart koşar.
        (vm.bayraklar || []).forEach(function (b) {
            html += badge(b.field + ' ' + (b.value ? 'true' : 'false'),
                (b.value === b.limitsAt) ? 'warn' : 'info');
        });
        (vm.kesme || []).forEach(function (k) {
            html += badge(k.field + ' ' + k.value.toFixed(k.digits) + k.unit,
                (k.value > 0) ? 'warn' : 'info');
        });
        // Blok içi serbest-metin uyarıları: kararsızlık olanlar kırmızı vurgulu
        (vm.warnings || []).forEach(function (w) {
            html += badge(esc(SRV(w)), isInstabilityText(w) ? 'err' : 'warn');
        });
        el.innerHTML = html;
    }

    // Chugging/kararsızlık uyarıları — design_warnings sözleşmeli kayıtlar,
    // panelde vurgulu (uyarı panelindeki genel listeden ayrı, karar kapısı).
    function renderInstability(el, vm) {
        const list = vm.instability || [];
        if (!list.length) { el.innerHTML = ''; return; }
        let html = `<strong style="color:var(--hd-red, #ff5d73);
            font-family:var(--hd-mono); font-size:0.8rem;"
            data-i18n="blowdown.instabilityTitle">${T('blowdown.instabilityTitle',
            'Feed / combustion stability warnings')}</strong>`;
        list.forEach(function (w) {
            html += `<div data-warn-code="${esc(w.code)}" style="border:1px solid
                var(--hd-red, #ff5d73); border-left-width:4px; border-radius:6px;
                padding:6px 10px; margin:6px 0; color:var(--hd-red, #ff5d73);
                font-family:var(--hd-mono); font-size:0.78rem;">⚠ ${esc(warnText(w))}</div>`;
        });
        el.innerHTML = html;
    }

    function renderCharts(els, vm) {
        const s = vm.series;
        const timeTitle = T('common.axis.timeS2', 'Time [s]');
        // Tank + kamara basıncı AYNI eksende: aradaki fark enjektör ΔP'sidir,
        // iki eğri ayrı eksene konursa bu fark okunamaz.
        Plotly.react(els.pressure, [
            { x: s.time_s, y: s.tank_pressure_bar,
              name: T('transient.sTankP', 'Tank Pressure [bar]'),
              mode: 'lines', line: { width: 3 } },
            { x: s.time_s, y: s.chamber_pressure_bar,
              name: T('transient.sPc', 'Chamber Pressure [bar]'),
              mode: 'lines', line: { width: 2, dash: 'dot' } },
        ], {
            title: T('blowdown.chartPressure',
                     'Tank vs Chamber Pressure (same axis — the gap is the injector ΔP)'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'P [bar]', rangemode: 'tozero' },
            // ÖH D34 · OH-P-07 (piksel turu, 21 Eyl 2026): kap .plot-container
            // (min-height 500 + 2x20 dolgu = 540 px) iken 360/300 px'lik çizimler
            // altında 150-240 px boşluk bırakıyordu (hibrit-01-r21/r22). Kap kadar.
            height: 500,
            legend: { orientation: 'h', y: 1.14 },
        }, { responsive: true, displaylogo: false });

        Plotly.react(els.mdot, [
            { x: s.time_s, y: s.mdot_ox_kg_s,
              name: T('blowdown.sMdotOx', 'Oxidizer Mass Flow [kg/s]'),
              mode: 'lines', line: { width: 3 } },
        ], {
            title: T('blowdown.chartMdot', 'Oxidizer Mass Flow Decay'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'ṁ_ox [kg/s]', rangemode: 'tozero' },
            height: 500,  // OH-P-07
            legend: { orientation: 'h', y: 1.16 },
        }, { responsive: true, displaylogo: false });

        Plotly.react(els.thrust, [
            { x: s.time_s, y: s.thrust_N,
              name: T('transient.sThrust', 'Thrust [N]'),
              mode: 'lines', line: { width: 3 } },
        ], {
            title: T('blowdown.chartThrust', 'Thrust Decay During Blowdown'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'F [N]', rangemode: 'tozero' },
            height: 500,  // OH-P-07
            legend: { orientation: 'h', y: 1.16 },
        }, { responsive: true, displaylogo: false });
    }

    // A10 beyan şeridi — hibrit sonuç bölümünün başı. Metinler SONUÇTAN gelir;
    // sayı da listenin gerçek uzunluğudur, sabit '7' yazılmaz.
    function renderDeclarations(el, vm) {
        if (!el) return;
        const decls = vm.declarations;
        if (!decls || !decls.length) {
            el.innerHTML = '';
            el.style.display = 'none';
            return;
        }
        const items = decls.map(function (d) {
            return `<li style="margin:6px 0;">${esc(SRV(d.text))}</li>`;
        }).join('');
        const basisNote = vm.declBasis
            ? `<p style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);
                margin:8px 0 0;">${esc(SRV(vm.declBasis))}</p>`
            : '';
        el.innerHTML = `
        <div class="panel" style="border-left:3px solid ${MISSING_COLOR}; margin-bottom:20px;">
            <details>
                <summary data-decl-count="${decls.length}" style="cursor:pointer;
                    font-family:var(--hd-mono); font-size:0.85rem;
                    color:${MISSING_COLOR};">${esc(TF('blowdown.declCount',
                    { n: decls.length },
                    '{n} physics items are NOT modelled in this hybrid result — read before trusting the design'))}</summary>
                <ul style="margin:8px 0 0 18px; font-size:0.78rem;
                    color:var(--hd-ink-dim, #7d97a5);
                    font-family:var(--hd-mono);">${items}</ul>
                ${basisNote}
            </details>
        </div>`;
        el.style.display = '';
    }

    function render() {
        const motor = lastResults && lastResults.motor;
        const vm = buildViewModel(motor);

        renderDeclarations(
            document.getElementById(cfg.declAnchorId || 'notModelledStrip'), vm);

        const els = {
            badges: document.getElementById('bp_badges'),
            instability: document.getElementById('bp_instability'),
            chip: document.getElementById('bp_chip'),
            basis: document.getElementById('bp_basis'),
            basisText: document.getElementById('bp_basis_text'),
            basisFields: document.getElementById('bp_basis_fields'),
            pressure: document.getElementById('bp_plot_pressure'),
            mdot: document.getElementById('bp_plot_mdot'),
            thrust: document.getElementById('bp_plot_thrust'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        renderInstability(els.instability, vm);

        // Yöntem künyesi: sunucunun basis beyanı (varsa) aynen gösterilir
        if (els.basis && els.basisText) {
            if (vm.basis) {
                // ÖH D26 / OH-B4-04: faz kanalının KÜNYESİ de burada
                // gösterilir — alan yayımlanıp künyesi saklanırsa
                // kullanıcı 'vapor' etiketinin ne anlama geldiğini
                // (ve kuyruğun neden yalnız mertebe tahmini olduğunu)
                // okuyamaz.
                els.basisText.textContent = vm.tank_phase_basis
                    ? (SRV(vm.basis) + ' — ' + SRV(vm.tank_phase_basis))
                    : SRV(vm.basis);
                els.basis.style.display = '';
            } else {
                els.basisText.textContent = '';
                els.basis.style.display = 'none';
            }
        }
        // ÖH D27 · OH-B3-02 — kardeş künyeler ADIYLA basılır. Sunucu
        // metni SRV() ile kaçırılır; alan adı `data-basis-field` olarak
        // iner ki bekçi ve tarayıcı turu satırı adıyla bulabilsin.
        // Künye yoksa liste boş kalır ve `basis` kutusu yine de açılır
        // (aşağıdaki koşul), çünkü künyenin YOKLUĞU da bir bilgidir.
        if (els.basisFields) {
            const kunyeler = Array.isArray(vm.kunyeler) ? vm.kunyeler : [];
            els.basisFields.innerHTML = kunyeler.map(function (k) {
                return '<dt data-basis-field="' + esc(k.field) + '"'
                    + ' style="font-weight:600; margin-top:4px;">'
                    + esc(basisLabel(k.field)) + '</dt>'
                    + '<dd style="margin:0 0 0 12px;">' + esc(SRV(k.text))
                    + '</dd>';
            }).join('');
            if (kunyeler.length && els.basis) els.basis.style.display = '';
        }

        if (vm.mode === 'modelled') {
            els.chip.innerHTML = '';
            renderBadges(els.badges, vm);
            els.pressure.style.display = 'block';
            els.mdot.style.display = 'block';
            els.thrust.style.display = 'block';
            renderCharts(els, vm);
            return;
        }

        // Modellenmedi / veri yok: eğri ÇİZİLMEZ, çip + gerekçe basılır.
        els.pressure.style.display = 'none';
        els.mdot.style.display = 'none';
        els.thrust.style.display = 'none';
        els.badges.innerHTML = '';
        if (vm.mode === 'not_modelled') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipNotModelled', 'NOT MODELLED — no curve is drawn'),
                vm.reason || '');
        } else if (vm.mode === 'invalid_block') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipInvalid',
                  'DATA INCONSISTENT — the tank_blowdown block arrived with '
                  + 'mismatched series; nothing is plotted'), '');
        } else if (vm.mode === 'no_block') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipNoData',
                  'NO DATA — this result carries no tank_blowdown block '
                  + '(older save or older server); nothing is plotted'), '');
        } else {
            els.chip.innerHTML = '';
        }
    }

    // ------------------------------------------------------------------
    // Bağlama
    // ------------------------------------------------------------------
    function update(results) {
        lastResults = results || null;
        render();
    }

    function init(opts) {
        cfg = opts || {};
        const anchor = document.getElementById(cfg.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);

        // Hesap köprüsü: advanced.html'deki yörünge-eşitleme sarmalayıcısıyla
        // aynı desen. Özgün işlev HER KOŞULDA çağrılır; panel hatası hesap
        // gösterimini asla engellemez.
        (function () {
            const original = window.displayCalculationResults;
            if (typeof original !== 'function') return;
            window.displayCalculationResults = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('Blowdown panel update failed:', e);
                }
                return out;
            };
        })();

        // Dil değişince saklanan sonuçla yeniden basılır
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
    }

    window.BlowdownPanel = {
        init: init,
        update: update,
        buildViewModel: buildViewModel,
        _minPolylineSamples: MIN_POLYLINE_SAMPLES,
        _renderBadges: renderBadges,
        // ÖH D34 / OH-GT-05 bekçisi (transient_panel.js ile aynı desen).
        _endEventKind: endEventKind,
        _endEventLabel: endEventLabel,
        _endEventKindMap: END_EVENTS,
        get result() { return lastResults; },
    };
})();
