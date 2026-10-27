/* ====================================================================
   HRMA Analiz Merkezi — CFD kiracısı (lüle iç akışı, 2B eksenel simetrik
   Euler + Summerfield ayrılma köprüsü)
   --------------------------------------------------------------------
   Merkez'in (analysis_center.js) İLK canlı kiracısı. POST /api/cfd/nozzle
   yanıtını çizer; hesap YAPMAZ, hüküm ÜRETMEZ — çözücünün kendi beyanlarını
   taşır ve okunur hâle getirir.

   KAPATILAN KUSUR
     hrma/cfd/ çözücüsü ve /api/cfd/nozzle ucu depoda çalışır hâldeydi ama
     hiçbir kullanıcı yüzü onları çağırmıyordu: ne duvar basıncı, ne akış
     alanı, ne ayrılma hükmü, ne de yakınsama geçmişi görünüyordu.

   ÖLÇÜLMÜŞ ZİNCİR (16 Ağu 2026, üç motor da canlı koşturuldu)
     1) Motor hesabı (window.currentResults) lüle konturunu YAYIMLIYOR:
        results.nozzle_contour.points = [[z_m, r_m], ...] (hibritte
        results.motor.nozzle_contour). Kontur uydurulamaz; bu yüzden
        yokluğu satırı gri yapar (applicability).
     2) Gaz durumu: hibrit ve KATI motor `nozzle_flow_quasi1d.inputs`
        bloğunu SI olarak yayımlıyor (P0_Pa, T0_K, gamma, R_J_kgK) —
        ucun istediği dört büyüklüğün dördü de orada, birim çevirisi
        GEREKMİYOR. SIVI motorda o blok YOK (ölçüldü), düz alanlara
        düşülüyor: chamber_pressure [bar]×1e5, chamber_temperature [K],
        gamma, molecular_weight → R = 8314,462618 / MW.
        Çapraz teyit: hibritte MW'den hesaplanan R = 397,110442…, motorun
        kendi combustion_analysis…gas_constants.chamber değerine BİT-AYNI;
        katıda quasi1d R = 296,9450935 = 8314,462618 / 28,0.
     3) Ortam basıncı üç motorda ÜÇ AYRI yerde yayımlanıyor (ölçüldü):
        hibrit  nozzle_expansion_screen.ambient_pressure_bar   (1,0 bar)
        katı    nozzle_flow_separation.ambient_pressure_Pa     (101325 Pa)
        sıvı    nozzle_design.performance.ambient_pressure     (1,01325 bar)
        Panel bu yolları SIRAYLA dener ve hangisinden geldiğini EKRANDA
        yazar. Hiçbiri yoksa öneri YOKTUR — "deniz seviyesi" varsaymak
        sessiz bir uydurma olurdu (ucun kendi sözleşmesi de bunu reddeder).

   SAHTE VERİ / SAHTE İLERLEME YASAĞI
     * Bu dosyada setInterval / setTimeout / requestAnimationFrame /
       Math.random YOKTUR. Koşum sırasındaki tek beyan Merkez'in gerçek
       durum satırıdır; yüzde çubuğu, dolan animasyon, sahte kalıntı akışı
       yok. Süreyi uç ölçer (runtime_s / solver_runtime_s), panel basar.
     * Hiçbir alanın SONLU VARSAYILANI yoktur: öneri bulunamayan alan BOŞ
       kalır ve `body()` isteği HİÇ GÖNDERMEZ, eksikleri adıyla yazar.
       (Çerçeve kuralı "sonlu varsayılanlı alan zorunludur" der; buradaki
       beş büyüklük için sonlu varsayılan yazmak = uydurma sayı göstermek.)
     * Çizilen her sayı yanıttan gelir. Tek dönüşüm Pa → bar bölmesidir
       (PA_PER_BAR) ve eksen başlığında beyan edilir.
     * Duvar poliçizgisi YALNIZ bu koşuya gönderilen kontur olduğu
       ÖLÇÜLEBİLDİĞİNDE çizilir (nokta sayısı + ızgaranın yayımladığı
       giriş/çıkış z,r uçları birebir tutmalı); tutmuyorsa çizilmez ve
       nedeni yazılır. Geçmişten gelen bir koşuya bugünkü kontur
       giydirilmez.
     * Koşu öncesi "bütçe yetmeyebilir" beklentisi PANELDE HESAPLANMAZ: uç
       onu `inlet_conditioning` bloğunda ölçülmüş dayanağıyla yayımlar
       (bant kuralının, ölçüm tablosunun ve tetiklenen gerekçelerin ikinci
       bir tanımı burada yazılmaz). Panel o bloğu "hüküm değildir" diliyle
       basar. NÖBET DEĞİŞİMİ (16 Ağu 2026): blok eskiden giriş Mach EŞİĞİ
       taşıyordu (`threshold_mach` / `advisory`); çözücünün giriş sınır
       koşulu karakteristik biçime çevrilince o eşik ölçülen hiçbir şeyi
       bildirmez oldu ve sağlıklı koşularda turuncu rozet basıyordu. Panelde
       Mach eşiği dili KALMADI; uyarı artık iterasyon BÜTÇESİNİN uyarısıdır
       (`budget_advisory` + `budget_advisory_reasons`).

   HÜKÜM (verdict) — çerçeve kural 4
     converged=true  → 'ok'   + iterasyon sayısı, künyede çözücünün
                               convergence_basis cümlesi
     converged=false → 'warn' + son kalıntı; ayrılma bloğu kendi
                               judgment_confidence='suspect' etiketiyle
                               ayrıca görünür.
     converged=null  → 'warn' + "hüküm yayımlanmadı" (OH-D31-15): çözücü
                               hükmü YARGILAMADI (convergence_status=
                               'not_evaluated'); ayrılma bloğu bunu
                               judgment_confidence='not_evaluated' ile
                               taşır ve KABUL RENGİ (yeşil) verilmez.
                               Bu bir "yakınsamadı" hükmü DEĞİLDİR.
     cfd bloğu yoksa → hüküm BEYAN EDİLMEZ (çerçeve "hüküm beyan edilmedi"
                               rozetini basar; buradan sahte 'ok' çıkmaz).

   Bekçi testleri: tests/test_cfd_panel.py (node ile izole koşum + Merkez
   ile birlikte uçtan uca) ve uç tarafında tests/test_cfd_endpoint.py.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    const ENDPOINT = '/api/cfd/nozzle';

    //: Birim çevirisinin TEK yeri (motor_viz_deck.js / transient_panel.js
    //: ile aynı ad ve aynı değer). Motorların düz `chamber_pressure` alanı
    //: BAR taşır (ölçüldü: hibritte 20 → quasi1d P0_Pa 2 000 000; katıda
    //: 40 → 4 000 000); uç ise Pascal ister.
    // ÖH D25 / OH-D24-05 — TEK KAYNAK. Bu sayı burada TANIMLANMAZ:
    // `static/js/units_constants.js` ön yüzün tek birim çevrim kaynağıdır
    // (ölçüldü: aynı tanım dört JS dosyasındaydı). Modül yoksa sessiz bir
    // yedek UYDURULMAZ — requirePaPerBar() hata fırlatır.
    const PA_PER_BAR = (function () {
        var g = (typeof window !== 'undefined') ? window : globalThis;
        // Tarayıcı: <script src="/static/js/units_constants.js"> modülü
        // window'a yazar. Node (bekçi koşumları panel dosyasını require
        // eder): modül kardeş dosyadan çözülür. İKİ yolda da sayı TEK
        // yerde yaşar; burada yeniden TANIMLANMAZ.
        if (!g.HRMAUnits && typeof require === 'function') {
            try { g.HRMAUnits = require('../units_constants.js').UNITS; } catch (e) { /* yok */ }
            if (g.HRMAUnits && !g.HRMAUnits.requirePaPerBar) {
                try {
                    g.HRMAUnits.requirePaPerBar =
                        require('../units_constants.js').requirePaPerBar;
                } catch (e) { /* yok */ }
            }
        }
        if (!g.HRMAUnits || !g.HRMAUnits.requirePaPerBar) {
            throw new Error('units_constants.js must load before this panel: '
                + 'PA_PER_BAR has a single source and is not re-declared here.');
        }
        return g.HRMAUnits.requirePaPerBar();
    }());

    //: Evrensel gaz sabiti [J/(kmol·K)] — R = R_u / MW [g/mol] kuralının
    //: kaynağı motorun KENDİ beyanıdır: hibrit quasi1d bloğu
    //: 'gas_property_source' alanında aynı formülü yazıyor
    //: ("R = 8314.462618 / molecular_weight"). İkinci bir tanım değil,
    //: aynı tanımın istemci tarafındaki uygulanışıdır.
    const R_UNIVERSAL = 8314.462618;

    //: ALAN HARİTASININ BÜYÜKLÜKLERİ (parti 30 — üçüncü büyüklük eklendi).
    //: `id` ve `payloadKey` sütunları motor_viz3d.js'in CFD_METRICS
    //: tablosuyla ve ucun (hrma/app.py) 'field' sözlüğündeki GERÇEK
    //: anahtarlarla KÜME EŞİTLİĞİ bekçisine bağlıdır
    //: (tests/test_cfd_alan_koprusu.py) — üç yerden biri kayarsa kırmızı.
    //: Buradaki EK sütun 2B sunuma aittir: panel basıncı bar'a çevirir
    //: (3B sahne Pa gösterir), bu yüzden ölçek/etiket YALNIZ burada durur.
    const FIELD_METRICS = [
        { id: 'mach', payloadKey: 'mach', scale: 1,
          labelKey: 'panel.cfd.metricMach',
          labelFallback: 'Mach number [-]' },
        { id: 'pressure', payloadKey: 'pressure_Pa', scale: 1 / PA_PER_BAR,
          labelKey: 'panel.cfd.metricPressure',
          labelFallback: 'Static pressure [bar]' },
        { id: 'temperature', payloadKey: 'temperature_K', scale: 1,
          labelKey: 'panel.cfd.metricTemperature',
          labelFallback: 'Static temperature [K]' },
    ];

    //: 3B sahnenin üretebildiği RED kodlarının TAM kümesi. Panel bu listeyi
    //: YALNIZ "bu kodu tanıyor muyum" denetimi için tutar: kullanıcıya
    //: basılan METİN sahnenin kendi reason.key/fallback çiftinden gelir,
    //: yani mesajın ikinci bir tanımı burada YOKTUR. Tanınmayan kod gelirse
    //: panel bunu adıyla beyan eder (sessiz "olmadı" mesajı yasak).
    //: Küme eşitliği bekçisi: tests/test_cfd_alan_koprusu.py.
    const VIZ3D_REASON_CODES = ['no_scene', 'no_solver_contour',
        'contour_mismatch', 'missing_metric', 'bad_field_block', 'no_field'];

    //: Çizim kimliklerinin çakışmaması için koşum sayacı (her çizimde artar).
    let drawSeq = 0;
    //: Alan haritasında gösterilen büyüklük (FIELD_METRICS kimliklerinden).
    let fieldMetric = 'mach';
    //: En son GÖNDERİLEN kontur (duvar çizgisi ancak bununla eşleşen
    //: yanıtlarda çizilir; geçmişten gelen koşuya bugünkü kontur giydirilmez).
    let lastSentContour = null;
    //: ÖH D36 / sahne-hud — 3B sahneye KENDİLİĞİNDEN gönderilmiş yanıtlar
    //: (nesne kimliği). Bir yanıt ömründe EN FAZLA BİR KEZ kendiliğinden
    //: gönderilir; yeniden çizildiğinde (büyüklük seçici, dil değişimi,
    //: geçmiş şeridinde gezinme) ikinci kez gönderilmez: kullanıcı sahne
    //: şeridinden KAPAT dediyse o karar korunur. Yeni koşum = yeni nesne =
    //: yeniden bindirme.
    //: a1 denetimi (docs/scofield/raw/OH/D36/sahne-hud/a1/rapor.md): ilk
    //: sürüm TEK yuvalı kimlik tutuyordu; iki koşumdan sonra KAPAT denip
    //: geçmişte eski ve yeni kayıt arasında gezinildiğinde alan her
    //: dönüşte yeniden gönderiliyordu (ölçüldü: 2 yerine 5 gönderim).
    //: WeakSet yükü tutmaz: Merkez'in geçmiş budaması (gecmisiBuda)
    //: bırakılan yanıtı yine bellekten atabilir.
    const autoBridgedCfds = (typeof WeakSet === 'function') ? new WeakSet() : null;
    let lastAutoBridgedCfd = null;
    //: En son öneri turunun kaynak yolları (fromResults ölçtü) — ekranda
    //: "bu sayı motorun neresinden geldi" diye basılır.
    let lastSuggestion = null;
    //: Carpet izi bu Plotly derlemesinde yoksa nokta haritasına düşülür;
    //: bu durum çipte BEYAN edilir (fea_panel.js ile aynı desen).
    let carpetFallback = false;

    // ------------------------------------------------------------------
    // i18n köprüleri — i18n.js yüklenmemişse İngilizce yedek metin döner
    // (analysis_center.js / fea_panel.js ile birebir aynı köprü).
    // ------------------------------------------------------------------
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback == null ? key : fallback)
            .replace(/\{(\w+)\}/g, function (whole, name) {
                return (params && name in params) ? String(params[name]) : whole;
            });
    }
    //: Sunucudan gelen serbest metin (beyan/gerekçe): sözlükte karşılığı
    //: varsa çevrilir, yoksa AYNEN kalır (asla anahtar, asla boş).
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    // ÖH D31 · OH-D30-06 — BİÇİM TEK KAYNAKTAN. Bu panel ortak `U`
    // nesnesini yakalamıyor (kendi T/TF delegatörleri var); aynı desenle
    // I18N.number'a devreder (import_ui.js:171, project_bar.js:810).
    // Sözlük motoru yoksa toFixed'e düşer: sayı UYDURULMAZ, yalnız
    // ondalık ayracı yerelleşmez.
    function _num(v, digits) {
        return (window.I18N && window.I18N.number)
            ? window.I18N.number(v, digits) : v.toFixed(digits);
    }
    function fmt(v, digits) {
        return isNum(v) ? _num(v, digits === undefined ? 3 : digits) : '—';
    }

    //: ÖH D25 · P11B3-14 — EM TİRE DİSİPLİNİ SAYISAL OLMAYAN YOLDA DA.
    //: ÖLÇÜLDÜ (a3/once.json, taban cdf2106): panelin kendi beyanı
    //: (yukarıdaki blok) "Alan YOKSA 'NaN' basmak yerine em tire konur"
    //: diyor, ama bu kural yalnız sig()/fmt()/fmtAuto() yolunda
    //: uygulanmıştı. Ham String()/şablon yolu aynı ekranda karışık
    //: kullanılıyordu: yalnız {cfd:{converged:true}} taşıyan yükle panel
    //: ekrana 10 kez 'undefined' bastı (kardeş üç FEA paneli aynı sınavda
    //: 0 sızıntı verdi). txt() o yolun kapısıdır: değer YOKSA (undefined /
    //: null / boş dize) em tire konur, VARSA olduğu gibi basılır — sayı
    //: biçimlendirmesi YAPMAZ, yalnız yokluğu beyan eder.
    function txt(v) {
        if (v === undefined || v === null) return '—';
        const s = String(v);
        return s === '' ? '—' : s;
    }

    //: ÖH D36 / sahne-hud a2 — ÖNCEDEN BİÇİMLENMİŞ SAYI METNİNİN AYRACI.
    //: ÖLÇÜLDÜ (raw/OH/D36/sahne-hud/a2/once.json, M3): Merkez CFD
    //: görünümünde TR kipinde panelin KENDİ biçimlediği 31 sayı NOKTA
    //: basıyordu; `fmt` (I18N.number) yolu virgüllü olduğu için aynı
    //: hücrede iki ayraç okunuyordu ("43442.7 / 5,430"). `toExponential`
    //: ve `String(sigFig(v))` çıktısı yalnız ayraç için i18n.js'in
    //: `decimalText` kanalından geçer: basamak DEĞİŞMEZ, desene uymayan
    //: metne dokunulmaz. Künye dökümleri (alan adı = değer satırları,
    //: `sigRaw`) makinedir ve NOKTA kalır (D33-3 fix-38a ayrımı).
    function decTxt(text) {
        return (window.I18N && typeof window.I18N.decimalText === 'function')
            ? window.I18N.decimalText(text) : text;
    }

    //: Çok küçük/çok büyük sayılar (kalıntı, korunum artığı) için üstel.
    function fmtExp(v, digits) {
        return isNum(v)
            ? decTxt(v.toExponential(digits === undefined ? 2 : digits)) : '—';
    }

    //: Büyüklüğü önceden bilinmeyen sayı (ör. duvar basıncı marjı).
    //: ÖLÇÜLDÜ (16 Ağu 2026, canlı hibrit sayfası): ıraksayan bir koşuda marj
    //: 4,659024264406486e+25 çıktı ve sabit ondalık biçim bunu rozete OLDUĞU
    //: GİBİ bastı — sayı gizlenmemeli ama okunabilir de olmalı. Bant dışına
    //: çıkınca üstel biçime geçilir; sayı ne kırpılır ne yuvarlanıp saklanır.
    function fmtAuto(v, digits) {
        if (!isNum(v)) return '—';
        const mutlak = Math.abs(v);
        if (mutlak !== 0 && (mutlak >= 1e4 || mutlak < 1e-2)) {
            return decTxt(v.toExponential(digits === undefined ? 3 : digits));
        }
        return fmt(v, digits === undefined ? 3 : digits);
    }

    //: Anlamlı basamak — Merkez'in ön dolum kuralıyla aynı kaynak.
    function sigFig(value) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.sigFig === 'function') return U.sigFig(value);
        const v = Number(value);
        if (!isFinite(v) || v === 0) return v;
        return Number(v.toPrecision(6));
    }

    //: Yazıya dökülmüş anlamlı basamak. Alan YOKSA 'NaN' basmak yerine em
    //: tire konur: köprü hüküm vermediğinde (bridge_refused) bu alanların
    //: bir kısmı hiç gelmez ve "NaN" kullanıcıya sayı gibi görünürdü.
    function sig(value) {
        return isNum(value) ? decTxt(String(sigFig(value))) : '—';
    }
    //: Künye (alan adı = değer) dökümü: makine kanalı, ayraç NOKTA.
    function sigRaw(value) {
        return isNum(value) ? String(sigFig(value)) : '—';
    }

    // ==================================================================
    // >>> CFD_PANEL_MODEL_START
    // Saf model katmanı — DOM/Plotly YOK. Bekçi testleri bu bölümü
    // GERÇEK uç yanıtlarıyla doğrudan koşturur.
    // ==================================================================

    //: Motor sözlüğü: hibrit sayfası sonucu {motor: {...}} sarmalıyla
    //: yayımlıyor (ölçüldü), katı/sıvı düz. Sarmal varsa içi, yoksa kendisi.
    function motorDict(results) {
        if (!results || typeof results !== 'object') return null;
        if (results.motor && typeof results.motor === 'object') return results.motor;
        return results;
    }

    //: 'a.b.c' yolunu güvenle okur (ara düğüm yoksa undefined).
    function pick(obj, path) {
        let cur = obj;
        const parts = String(path).split('.');
        for (let i = 0; i < parts.length; i++) {
            if (cur == null || typeof cur !== 'object') return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    // ------------------------------------------------------------------
    // ÖNERİ KAYNAKLARI — her alan için ÖLÇÜLMÜŞ yol listesi, sırayla denenir.
    // İlk tutan yol kazanır ve YOLU da kaydedilir (ekranda yazılır).
    // Uydurma yedek YOKTUR: hiçbir yol tutmazsa alan önerisiz kalır.
    // ------------------------------------------------------------------
    const SUGGESTION_SOURCES = {
        // Hibrit + katı: motorun kendi yarı-1B lüle akışının SI girdileri.
        // Sıvı: quasi1d bloğu yok (ölçüldü) → düz alanlar.
        P0_Pa: [
            { path: 'nozzle_flow_quasi1d.inputs.P0_Pa' },
            { path: 'chamber_pressure', scale: PA_PER_BAR, unit: 'bar → Pa' },
        ],
        T0_K: [
            { path: 'nozzle_flow_quasi1d.inputs.T0_K' },
            { path: 'chamber_temperature' },
        ],
        gamma: [
            { path: 'nozzle_flow_quasi1d.inputs.gamma' },
            { path: 'gamma' },
        ],
        R_J_per_kgK: [
            { path: 'nozzle_flow_quasi1d.inputs.R_J_kgK' },
            { path: 'nozzle_flow_quasi1d.inputs_used.gas_constant_J_kgK' },
            { path: 'molecular_weight', invert: R_UNIVERSAL,
              unit: 'R = 8314,462618 / MW' },
        ],
        // Ayrılma ölçütünün tanımlı olduğu ortam basıncı. ÜÇ motorda ÜÇ
        // ayrı yol (ölçüldü); hiçbiri yoksa öneri yok.
        P_ambient_Pa: [
            { path: 'nozzle_expansion_screen.ambient_pressure_bar',
              scale: PA_PER_BAR, unit: 'bar → Pa' },
            { path: 'nozzle_flow_separation.ambient_pressure_Pa' },
            { path: 'nozzle_design.performance.ambient_pressure',
              scale: PA_PER_BAR, unit: 'bar → Pa' },
        ],
    };

    //: Ucun ZORUNLU saydığı ve panelin form alanı olarak sunduğu büyüklükler
    //: (kontur ayrı: o forma girilmez, sonuçtan gelir).
    const REQUIRED_FIELDS = ['P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK', 'P_ambient_Pa'];

    //: Uygulanabilirlik için sonuçta BULUNMASI gereken gaz büyüklükleri.
    //: P_ortam bilerek DIŞARIDA: motor yayımlamasa bile kullanıcı elle
    //: girebilir, o yüzden satırı gri yapmaz (ama boşsa istek gönderilmez).
    const APPLICABILITY_FIELDS = ['P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK'];

    //: T_wall'ın KAYNAK BEYANI. Uç izotermal duvarda `T_wall_source`u
    //: ZORUNLU tutar (kaynağı olmayan sınır koşulu yayımlanmaz). Buradaki
    //: metin bir uydurma değil, gerçeğin kendisidir: sayı Merkez'in form
    //: alanından, yani kullanıcının elinden gelir. Motorun ölçtüğü ya da
    //: termal FEA'nın çözdüğü bir duvar sıcaklığı olarak İMLENMEZ.
    const T_WALL_SOURCE_FORM =
        'user: Analysis Centre CFD panel form field (viscous_T_wall_K)';

    //: Türbülans kipinin panel varsayılanı — laminer yol. Ucun ve
    //: çözücünün varsayılanı da budur; panel ikinci bir kip icat etmez.
    const TURBULENCE_DEFAULT = 'none';

    //: Alan etiketleri — eksik alan mesajı bunları ADIYLA yazar.
    const FIELD_LABELS = {
        P0_Pa: ['panel.cfd.fieldP0', 'Chamber stagnation pressure P0 [Pa]'],
        T0_K: ['panel.cfd.fieldT0', 'Chamber stagnation temperature T0 [K]'],
        gamma: ['panel.cfd.fieldGamma', 'Ratio of specific heats gamma [-]'],
        R_J_per_kgK: ['panel.cfd.fieldR', 'Specific gas constant R [J/(kg K)]'],
        P_ambient_Pa: ['panel.cfd.fieldPamb', 'Ambient pressure [Pa]'],
        Pb_Pa: ['panel.cfd.fieldPb', 'Back pressure Pb [Pa] — optional'],
        separation_factor: ['panel.cfd.fieldK', 'Summerfield k [-] — optional'],
        resolution: ['panel.cfd.fieldResolution', 'Grid resolution'],
        viscous_mode: ['panel.cfd.fieldViscousMode', 'Wall model'],
        viscous_turbulence: ['panel.cfd.fieldTurbulence', 'Turbulence model'],
        viscous_T_wall_K: ['panel.cfd.fieldTwall',
                           'Wall temperature T_w [K] — isothermal wall only'],
    };

    function fieldLabel(id) {
        const rec = FIELD_LABELS[id];
        return rec ? T(rec[0], rec[1]) : id;
    }

    //: {values, sources} — values yalnız SONLU sayılar taşır, sources
    //: her değerin motorun neresinden geldiğini adlandırır.
    function suggest(results) {
        const m = motorDict(results);
        const values = {};
        const sources = {};
        if (!m) return { values: values, sources: sources };
        Object.keys(SUGGESTION_SOURCES).forEach(function (field) {
            const adaylar = SUGGESTION_SOURCES[field];
            for (let i = 0; i < adaylar.length; i++) {
                const aday = adaylar[i];
                const ham = pick(m, aday.path);
                if (!isNum(ham)) continue;
                let deger = ham;
                if (isNum(aday.scale)) deger = ham * aday.scale;
                if (isNum(aday.invert)) {
                    if (ham === 0) continue;        // 0'a bölme: aday geçersiz
                    deger = aday.invert / ham;
                }
                if (!isNum(deger)) continue;
                values[field] = deger;
                sources[field] = { path: aday.path, unit: aday.unit || null,
                                   raw: ham };
                break;
            }
        });
        return { values: values, sources: sources };
    }

    //: Yayımlanmış kontur bloğu → {points, path} ya da null.
    //: Uç `{'points': [[z_m, r_m], ...]}` biçimini kabul eder; panel şekli
    //: DEĞİŞTİRMEZ, yalnız geçirir (termal panelin ölçülmüş kuralı).
    function pickContour(results) {
        const m = motorDict(results);
        if (!m) return null;
        const blok = m.nozzle_contour;
        if (!blok || typeof blok !== 'object') return null;
        const pts = blok.points;
        if (!Array.isArray(pts) || pts.length < 3) return null;
        for (let i = 0; i < pts.length; i++) {
            const p = pts[i];
            if (!Array.isArray(p) || p.length < 2 || !isNum(p[0]) || !isNum(p[1])) {
                return null;
            }
        }
        return { points: pts, path: 'nozzle_contour.points' };
    }

    // ------------------------------------------------------------------
    // UYGULANABİLİRLİK (çerçeve kural 1) — HER ÇİZİMDE çağrılır: ucuz ve
    // yan etkisiz. İstek atmaz, DOM'a yazmaz, durum değiştirmez.
    // ------------------------------------------------------------------
    function applicability(results) {
        if (!pickContour(results)) {
            return { ok: false, reason: {
                key: 'panel.cfd.needsContour',
                fallback: 'This result publishes no nozzle contour '
                          + '(nozzle_contour.points): the CFD grid is built from '
                          + 'it, so the run cannot start. Re-run the motor '
                          + 'calculation on this page.' } };
        }
        const sug = suggest(results);
        const eksik = APPLICABILITY_FIELDS.filter(function (f) {
            return !isNum(sug.values[f]);
        });
        if (eksik.length) {
            return { ok: false, reason: {
                key: 'panel.cfd.needsGasState',
                params: { fields: eksik.map(fieldLabel).join(', ') },
                fallback: 'This result does not publish the gas state the '
                          + 'solver needs: {fields}. The solver has no default '
                          + 'reservoir state and this panel invents none.' } };
        }
        return { ok: true };
    }

    // ------------------------------------------------------------------
    // POST GÖVDESİ — sayılar FORMDAN, kontur SONUÇTAN.
    // Eksik zorunlu alan varsa istisna atılır: çerçeve isteği GÖNDERMEZ ve
    // mesajı kırmızı beyanla basar (uydurma varsayılan konmaz).
    // ------------------------------------------------------------------
    function buildBody(formValues, results) {
        const v = formValues || {};
        const eksik = REQUIRED_FIELDS.filter(function (f) { return !isNum(v[f]); });
        const kontur = pickContour(results);
        if (!kontur) eksik.push('nozzle_contour');
        if (eksik.length) {
            throw new Error(TF('panel.cfd.missingInputs',
                { fields: eksik.map(fieldLabel).join(', ') },
                'These inputs have no value and the endpoint has no default '
                + 'for any of them: {fields}. The request was NOT sent — this '
                + 'panel does not invent a number in their place.'));
        }
        // VİSKOZ KİP (opt-in): 'viscous_mode' boşsa gövdeye HİÇBİR viskoz
        // alan konmaz ve koşu bugünkü Euler yolunun bit-aynısıdır.
        const kip = String(v.viscous_mode || '');
        if (kip === 'isothermal' && !isNum(v.viscous_T_wall_K)) {
            throw new Error(TF('panel.cfd.missingWallTemp',
                { field: fieldLabel('viscous_T_wall_K') },
                'An isothermal wall needs its temperature: {field} is empty '
                + 'and neither this panel nor the solver has a default for '
                + 'it. The request was NOT sent.'));
        }
        const body = {};
        REQUIRED_FIELDS.forEach(function (f) { body[f] = v[f]; });
        if (kip) {
            const viskoz = { enabled: true, wall_thermal: kip,
                             turbulence: String(v.viscous_turbulence
                                                || TURBULENCE_DEFAULT) };
            if (kip === 'isothermal') {
                viskoz.T_wall_K = v.viscous_T_wall_K;
                // KAYNAK BEYANI: uç, T_wall'ın kaynağını ZORUNLU tutar.
                // Buradaki metin uydurma değil GERÇEK kaynaktır — sayı bu
                // formdan, kullanıcının elinden geldi. Motorun ölçtüğü bir
                // duvar sıcaklığı DEĞİLDİR ve öyleymiş gibi imlenmez.
                viskoz.T_wall_source = T_WALL_SOURCE_FORM;
            }
            body.viscous = viskoz;
        }
        // İsteğe bağlı alanlar: boşsa GÖNDERİLMEZ (uç "verilmedi" hâlini
        // kendi beyanıyla işler — back_pressure_basis / separation_factor).
        if (isNum(v.Pb_Pa)) body.Pb_Pa = v.Pb_Pa;
        if (isNum(v.separation_factor)) body.separation_factor = v.separation_factor;
        if (v.resolution) body.resolution = String(v.resolution);
        body.nozzle_contour = { points: kontur.points };
        lastSentContour = { points: kontur.points, path: kontur.path };
        return body;
    }

    // ------------------------------------------------------------------
    // HÜKÜM ROZETİ (çerçeve kural 4)
    // ------------------------------------------------------------------
    function verdictOf(data) {
        const cfd = data && data.cfd;
        if (!cfd || typeof cfd !== 'object') return null;   // hüküm beyan edilmez
        if (typeof cfd.converged !== 'boolean') return null;
        if (cfd.converged) {
            // ÖH D25 · P11B3-11 — SATIR HÜKMÜ AYRILMAYI GÖRÜR.
            // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): P_ambient = 5 bar ile
            // koşulan ayrılan koşuda `separated = true`,
            // `separated_length_fraction = 0,32139` (ıraksak boyun %32,1'i,
            // 10 istasyon eşik altı), `judgment_confidence = 'firm'` iken
            // Merkez satır hükmü {kind:'ok'} — YEŞİL "CONVERGED" idi.
            // Ayrılma rozeti yalnız satır AÇILDIĞINDA görünüyordu, oysa
            // Merkez'in satır listesi TARANARAK okunur. Emsal: panelin
            // kendi rozet katmanı bu durumu zaten 'warn' basıyor
            // (badgesHtml, ayrılma rozeti) — satır hükmü ondan ayrışamaz.
            // Yakınsama HÜKMÜ değişmez (sayısal yakınsama gerçekten oldu);
            // değişen RENK ve METİN: yeşil düşürülür ve nedeni satıra
            // yazılır. Uydurma yok — oran ve hüküm ucun kendi alanları.
            const sep = cfd.separation;
            if (sep && sep.separated === true) {
                return { kind: 'warn',
                         key: 'panel.cfd.verdictConvergedSeparated',
                         params: { iters: txt(cfd.iterations),
                                   frac: isNum(sep.separated_length_fraction)
                                       ? fmt(100 * sep.separated_length_fraction, 1)
                                       : '—' },
                         fallback: 'CONVERGED ({iters} iterations) — but FLOW '
                                   + 'SEPARATION IS PREDICTED over {frac}% of '
                                   + 'the divergent length' };
            }
            return { kind: 'ok', key: 'panel.cfd.verdictConverged',
                     params: { iters: txt(cfd.iterations) },
                     fallback: 'CONVERGED ({iters} iterations)' };
        }
        const son = cfd.residual_history ? cfd.residual_history.last : null;
        return { kind: 'warn', key: 'panel.cfd.verdictNotConverged',
                 params: { res: fmtExp(son), iters: txt(cfd.iterations) },
                 fallback: 'NOT CONVERGED — residual {res} after {iters} '
                           + 'iterations' };
    }

    // ------------------------------------------------------------------
    // GÖRÜNÜM MODELİ — yanıttan çizilebilir yapıya. Tek dönüşüm Pa → bar.
    // ------------------------------------------------------------------
    function transpose(nested) {
        if (!Array.isArray(nested) || !nested.length) return null;
        if (!Array.isArray(nested[0])) return null;
        const ni = nested.length, nj = nested[0].length;
        const out = [];
        for (let j = 0; j < nj; j++) {
            const satir = [];
            for (let i = 0; i < ni; i++) {
                const row = nested[i];
                satir.push(Array.isArray(row) ? row[j] : null);
            }
            out.push(satir);
        }
        return out;
    }

    function toBar(values) {
        return (values || []).map(function (p) {
            return isNum(p) ? p / PA_PER_BAR : null;
        });
    }

    //: (toBar2d kaldırıldı: alan ızgarasının ölçeklenmesi artık
    //: FIELD_METRICS'in kendi `scale` sütunundan geçen scale2d ile yapılır —
    //: büyüklük başına ikinci bir dönüşüm yolu bırakılmadı.)

    //: Ölçek çarpanı 1 ise ızgara AYNEN döner (yeni dizi bile kurulmaz);
    //: yalnız basınçta (Pa → bar) gerçek bir bölme olur.
    function scale2d(grid, k) {
        if (!Array.isArray(grid)) return null;
        if (k === 1) return grid;
        return grid.map(function (row) {
            return (row || []).map(function (v) {
                return isNum(v) ? v * k : null;
            });
        });
    }

    function metricById(id) {
        for (let i = 0; i < FIELD_METRICS.length; i++) {
            if (FIELD_METRICS[i].id === id) return FIELD_METRICS[i];
        }
        return null;
    }

    //: Bilinmeyen kimlik tabloya düşer (ilk metrik) — uydurma bir büyüklük
    //: adı ekrana çıkmaz.
    function normalizeMetric(id) {
        return metricById(id) ? id : FIELD_METRICS[0].id;
    }

    //: RENK SKALASI TEK KAYNAK: duraklar 3B sahnenin yayımladığı
    //: MotorViz3D.CFD_COLORSCALES tablosundan gelir (Plotly açık durak
    //: dizisi kabul eder). Panelde Plotly skala ADI ('Viridis' gibi)
    //: KULLANILMAZ — ad kullanılsaydı aynı büyüklük 2B'de ve 3B'de farklı
    //: renklenirdi ve tablonun iki tanımı olurdu. Tablo yüklenmemişse
    //: yedek tanım YAZILMAZ: null döner, çağıran nedeni ekrana yazar.
    //: Yükleme sırası bekçisi (üç şablonda motor_viz3d.js ÖNCE):
    //: tests/test_cfd_alan_koprusu.py.
    function metricColorscale(id) {
        const tablo = window.MotorViz3D && window.MotorViz3D.CFD_COLORSCALES;
        const duraklar = tablo ? tablo[id] : null;
        return Array.isArray(duraklar) && duraklar.length ? duraklar : null;
    }

    //: Duvar poliçizgisi ancak bu koşuya GÖNDERİLEN kontur olduğu
    //: ÖLÇÜLDÜĞÜNDE çizilir. Ölçüt: nokta sayısı yanıtın beyanına eşit VE
    //: ızgaranın yayımladığı giriş/çıkış (z, r) uçları konturun ilk/son
    //: noktasıyla birebir. (Uç konturu ni+1 düzgün istasyona yeniden
    //: örnekler, uçları taşımaz — bu yüzden eşitlik tam beklenir.)
    function wallPolyline(cfd) {
        if (!lastSentContour || !cfd || !cfd.inputs || !cfd.grid) return null;
        const pts = lastSentContour.points;
        if (cfd.inputs.contour_points !== pts.length) return null;
        const g = cfd.grid;
        const ilk = pts[0], son = pts[pts.length - 1];
        const uclar = [[g.z_inlet_m, ilk[0]], [g.z_exit_m, son[0]],
                       [g.r_inlet_m, ilk[1]], [g.r_exit_m, son[1]]];
        for (let i = 0; i < uclar.length; i++) {
            const a = uclar[i][0], b = uclar[i][1];
            if (!isNum(a) || !isNum(b)) return null;
            const olcek = Math.max(Math.abs(a), Math.abs(b), 1e-12);
            if (Math.abs(a - b) > 1e-9 * olcek) return null;
        }
        return { z: pts.map(function (p) { return p[0]; }),
                 r: pts.map(function (p) { return p[1]; }) };
    }

    // ------------------------------------------------------------------
    // VİSKOZ KATMAN (parti 40) — ucun `viscous` bloğunun görünüm modeli.
    // HESAP YOK: her dizi yanıttan gelir, tek dönüşüm yoktur (q_w, τ_w,
    // h_g, c_f zaten SI). Bir alan yükte YOKSA katman ÇİZİLMEZ ve nedeni
    // ekrana yazılır — boş grafik ya da sıfır dizisi UYDURULMAZ.
    // ------------------------------------------------------------------
    function numArray(v) {
        return Array.isArray(v) && v.length
            && v.every(function (x) { return isNum(x); }) ? v : null;
    }

    function viscousModel(cfd) {
        const v = cfd.viscous;
        if (!v || typeof v !== 'object') return null;   // eski uç yanıtı
        if (!v.enabled) {
            return { enabled: false, basis: v._basis || '',
                     worstCase: v.measured_worst_case_s || null,
                     measuredRuns: Array.isArray(v.measured_runs)
                         ? v.measured_runs : [],
                     turbulenceChoices: v.turbulence_choices || [],
                     wallThermalChoices: v.wall_thermal_choices || [] };
        }
        const w = v.wall || {};
        const tp = v.thermal_profile || {};
        const bz = v.bartz_comparison || {};
        const sf = v.skin_friction || {};
        const fr = v.friction || {};
        return {
            enabled: true,
            turbulence: v.turbulence,
            wallThermal: v.wall_thermal,
            wallTempSource: v.T_wall_source,
            badge: v.y_plus_badge || null,
            yPlus: v.y_plus || {},
            transport: v.transport || {},
            validationBasis: v.validation_basis || '',
            basis: v._basis || '',
            worstCase: v.measured_worst_case_s || null,
            measuredRuns: Array.isArray(v.measured_runs) ? v.measured_runs : [],
            gridQuality: v.grid_quality || null,
            wallHeatW: v.wall_heat_W,
            boundaryFlux: v.boundary_viscous_flux || {},
            wall: {
                z: numArray(w.z_m) || [],
                qw: numArray(w.heat_flux_W_m2),
                tau: numArray(w.shear_Pa),
                yPlus: numArray(w.y_plus),
                Tw: numArray(w.temperature_K),
                basis: w._basis || '',
            },
            thermal: {
                available: !!tp.available,
                reason: tp.reason || '',
                hg: tp.available ? numArray(tp.h_g) : null,
                x_mm: tp.available ? numArray(tp.x_mm) : null,
                tRecovery: tp.available ? numArray(tp.T_recovery) : null,
                source: tp.source || null,
                tAwBasis: tp.t_aw_basis || null,
                edgeSource: tp.edge_source || null,
                recoveryRegime: tp.recovery_regime || null,
                //: ÖH D29 · P11B3-22 — KÖPRÜNÜN KENDİ 'İYİMSER' BEYANI.
                //: ÖLÇÜLDÜ (a3/once.json): `thermal_profile.not_modelled` ve
                //: `friction.not_modelled` blokları (pürüzlülük / ışıma /
                //: eşleşik cidar / duvar çözünürlüğü) yükte VAR, panelde
                //: 0 kez okunuyordu; panel yalnız ÜST DÜZEY
                //: `cfd.not_modelled` bloğunu basıyordu. Sürtünme kaybı
                //: tablosu bu kayıtlar olmadan basılıyordu.
                notModelled: (tp.not_modelled && typeof tp.not_modelled === 'object')
                    ? tp.not_modelled : null,
                basis: tp._basis || '',
            },
            bartz: {
                available: !!bz.available,
                reason: bz.reason || '',
                z: bz.available ? numArray(bz.z_m) : null,
                hg: bz.available ? numArray(bz.h_g_bartz) : null,
                hgCfd: numArray(bz.h_g_cfd),
                ratio: numArray(bz.ratio_cfd_over_bartz),
                ratioMin: bz.ratio_min, ratioMax: bz.ratio_max,
                ratioMean: bz.ratio_mean, ratioThroat: bz.ratio_at_throat,
                ratioBasis: bz.ratio_basis || '',
                cStar: bz.c_star_m_s, cStarBasis: bz.c_star_basis || '',
                rcOverDt: bz.rc_over_dt,
                basis: bz._basis || '',
            },
            skin: {
                available: !!sf.available,
                reason: sf.reason || '',
                z: sf.available ? numArray(sf.z_m) : null,
                cf: sf.available ? numArray(sf.c_f) : null,
                basis: sf._basis || '',
            },
            friction: {
                available: !!fr.available,
                reason: fr.reason || '',
                forceN: fr.friction_force_N,
                forceTangentialN: fr.friction_force_tangential_N,
                normalShare: fr.normal_stress_share,
                fraction: fr.friction_loss_fraction,
                source: fr.friction_source,
                band: Array.isArray(fr.sutton_band) ? fr.sutton_band : null,
                withinBand: fr.within_sutton_band,
                legacy: fr.legacy_constant,
                bandBasis: fr.band_comparison_basis || '',
                policyBasis: fr.policy_basis || '',
                //: P11B3-22 — sürtünme köprüsünün kendi modellenmeyenleri.
                notModelled: (fr.not_modelled && typeof fr.not_modelled === 'object')
                    ? fr.not_modelled : null,
            },
        };
    }

    function viewModel(cfd) {
        const sep = cfd.separation || {};
        const wall = cfd.wall_pressure || {};
        const field = cfd.field || {};
        const res = cfd.residual_history || {};
        const vm = {
            converged: cfd.converged,
            convergenceBasis: cfd.convergence_basis || '',
            iterations: cfd.iterations,
            maxIterations: cfd.max_iterations,
            maxIterationsSource: cfd.max_iterations_source,
            maxIterationsBasis: cfd.max_iterations_basis || '',
            runtime: cfd.runtime_s,
            solverRuntime: cfd.solver_runtime_s,
            runtimeBasis: cfd.runtime_basis || '',
            kernel: cfd.kernel_backend,
            kernelBasis: cfd.kernel_backend_basis || '',
            shockColumns: cfd.shock_sensor_columns,
            shockBasis: cfd.shock_sensor_basis || '',
            limiterIter: cfd.limiter_frozen_at_iter,
            limiterCount: cfd.limiter_freeze_count,
            // ÖZ-TUTARLILIK (ÖH defter D15-CFD-01 + OH-Z5-14): uç bu
            // dürüstlük alanlarını yayımlıyordu, panel HİÇBİRİNİ
            // basmıyordu — kullanıcı yayımlanan kalıntının kimin
            // olduğunu, kapının hükmü geri çekip çekmediğini ve
            // kalıntının PLATOda mı olduğunu ekranda göremiyordu.
            // Sayılar yanıttan AYNEN taşınır; yokluk em-tire ile
            // basılır, sıfırla DOLDURULMAZ.
            convergenceStatus: cfd.convergence_status,
            plateau: cfd.convergence_plateau || null,
            settleBands: cfd.settle_bands || null,
            // ÖH D28 / arayuz a1 (OH-D27-16) — HÜKMÜN DAYANAĞI EKRANDA.
            // ÖLÇÜLDÜ (a1/once.json, taban 7cd08bcc): D26 / app-api a4
            // (`e5882484`, P7B4-10) uca `time_integrator`,
            // `time_integrator_basis` ve `convergence_history` (üç seri)
            // ekledi; bu panelin 414 adlık okuma envanterinde ÜÇÜ DE 0
            // kez geçiyordu. Kullanıcı "debi bandı OTURDU" hükmünü
            // görüyor, hükmün hangi zaman ilerletme şemasıyla ve hangi
            // seriden ölçüldüğünü göremiyordu. Alanlar AYNEN taşınır;
            // panel ikinci bir aritmetik yazmaz, künye metnini yeniden
            // yazmaz (SRV ile sunucudan geldiği belli olarak basılır).
            timeIntegrator: cfd.time_integrator,
            timeIntegratorBasis: cfd.time_integrator_basis || '',
            convHistory: cfd.convergence_history || null,
            selfConsistency: {
                operator: cfd.residual_operator,
                schemeResidual: cfd.scheme_residual_norm,
                exceedsTol: cfd.scheme_residual_exceeds_tol,
                blocksVerdict: cfd.scheme_residual_blocks_verdict,
                rejections: cfd.picard_selfconsistency_rejections,
                slope: cfd.slope_state || null,
            },
            budget: cfd.budget || {},
            throat: cfd.throat || {},
            grid: cfd.grid || {},
            inputs: cfd.inputs || {},
            inlet: cfd.inlet_conditioning || {},
            separation: sep,
            notModelled: cfd.not_modelled,
            assumptions: cfd.assumptions,
            residual: {
                iteration: Array.isArray(res.iteration) ? res.iteration : [],
                value: Array.isArray(res.value) ? res.value : [],
                decimated: !!res.decimated,
                nTotal: res.n_total, nReturned: res.n_returned,
                last: res.last, min: res.min, basis: res._basis || '',
            },
            wall: {
                z: Array.isArray(wall.z_m) ? wall.z_m : [],
                pBar: toBar(wall.pressure_Pa),
                basis: wall._basis || '',
                thresholdBar: isNum(sep.threshold_Pa)
                    ? sep.threshold_Pa / PA_PER_BAR : null,
                sepZ: isNum(sep.separation_z_m) ? sep.separation_z_m : null,
                sepZInterp: isNum(sep.separation_z_interp_m)
                    ? sep.separation_z_interp_m : null,
                sepPBar: isNum(sep.separation_wall_pressure_Pa)
                    ? sep.separation_wall_pressure_Pa / PA_PER_BAR : null,
            },
            sectionAverage: cfd.section_average || {},
            field: null,
            viscous: viscousModel(cfd),
            wallLine: wallPolyline(cfd),
        };
        const x = transpose(field.z_m), y = transpose(field.r_m);
        //: Her büyüklük AYNI ızgarada taşınır (ucun _basis beyanı): bir
        //: büyüklüğün yokluğu ötekileri düşürmez. Yükte OLMAYAN büyüklük
        //: null kalır ve 'available' listesine girmez — türetilmez.
        const values = {}, available = [];
        FIELD_METRICS.forEach(function (m) {
            const g = transpose(field[m.payloadKey]);
            values[m.id] = g ? scale2d(g, m.scale) : null;
            if (values[m.id]) available.push(m.id);
        });
        if (x && y && available.length) {
            vm.field = {
                a: Array.isArray(field.axial_indices)
                    ? field.axial_indices : x[0].map(function (_v, i) { return i; }),
                b: Array.isArray(field.radial_indices)
                    ? field.radial_indices : x.map(function (_v, j) { return j; }),
                x: x, y: y, values: values, available: available,
                shape: field.shape, gridShape: field.grid_shape,
                decimated: !!field.decimated,
                nReturned: field.n_cells_returned, nTotal: field.n_cells_total,
                basis: field._basis || '',
            };
        }
        return vm;
    }
    // <<< CFD_PANEL_MODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil — Merkez'in rozet/renk sözlüğüyle aynı değişkenler
    // ------------------------------------------------------------------
    const COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };
    const WALL_COLOR = 'rgba(200,215,230,0.85)';
    const THRESHOLD_COLOR = '#ff8c33';
    const SEP_COLOR = '#ff5d73';

    function kindColor(kind) {
        return COLORS[kind] || COLORS.info;
    }

    //: Rozet — künye (title) çözücünün KENDİ beyan cümlesidir.
    function badge(text, kind, titleAttr) {
        const c = kindColor(kind);
        return '<span data-cfd-badge="' + esc(kind) + '" title="'
            + esc(titleAttr || '') + '" style="border:1px solid ' + c
            + '; color:' + c + '; border-radius:6px; padding:2px 9px;'
            + ' font-family:var(--hd-mono, monospace); font-size:0.68rem;'
            + ' letter-spacing:0.04em; display:inline-block; margin:2px 4px 2px 0;">'
            + esc(text) + '</span>';
    }

    function sectionTitle(key, fallback) {
        return '<div data-i18n="' + esc(key) + '" style="font-family:'
            + 'var(--hd-mono, monospace); font-size:0.68rem; letter-spacing:0.08em;'
            + ' text-transform:uppercase; color:var(--hd-ink-dim, #7d97a5);'
            + ' margin:12px 0 6px;">' + esc(T(key, fallback)) + '</div>';
    }

    //: Sunucu beyanı (basis/gerekçe) — AYNEN basılır, kısaltılmaz.
    //: V301/DİL (NK-67): ölçüldü — TR arayüzde çevrilmemiş uzun geliştirici
    //: paragrafları ("This run is INVISCID…", "Effective iteration budget…")
    //: ve kaynak yolları (`tests/cfd/…py`, `relax_implicit.py`, defter
    //: kodu) açık metin olarak basılıyordu. Kural: TR'de çeviri kanalından
    //: geçmeyen beyan ya da (her dilde) kaynak yolu / iç kimlik taşıyan
    //: beyan KAPALI "teknik ayrıntı" bölümüne iner; metin aynen korunur,
    //: yarım çeviri yapılmaz.
    const KOD_IZI = /(\b[\w\-]+\.py\b|\btests\/|\bhrma[\/.][a-z_]|\bP\d+B\d+-\d+\b|\bOH-[A-Z0-9][A-Z0-9\-]*\b)/;
    function basisText(text) {
        if (!text) return '';
        const metin = SRV(text);
        const p = '<p data-cfd-basis="1" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; line-height:1.45; color:var(--hd-ink-dim,'
            + ' #7d97a5); margin:6px 0; white-space:pre-wrap;">'
            + esc(metin) + '</p>';
        const dilTr = !!(window.I18N && window.I18N.lang === 'tr');
        const cevrilmedi = dilTr && metin === text && /[A-Za-z]{4}/.test(text);
        if (!cevrilmedi && !KOD_IZI.test(metin)) return p;
        return '<details class="hd-teknik-ayrinti" style="margin:4px 0;">'
            + '<summary style="cursor:pointer; font-size:0.66rem; color:'
            + 'var(--hd-ink-dim, #7d97a5);">'
            + esc(T('panel.cfd.techDetailSrv', 'Technical detail (solver statement, untranslated)'))
            + '</summary>' + p + '</details>';
    }

    function note(text, kind) {
        return '<p style="font-size:0.7rem; margin:6px 0; color:'
            + kindColor(kind || 'dim') + ';">' + esc(text) + '</p>';
    }

    //: İki sütunlu künye tablosu (etiket | değer).
    function kvTable(rows) {
        const body = rows.map(function (r) {
            return '<tr><td style="padding:2px 8px 2px 0; color:'
                + 'var(--hd-ink-dim, #7d97a5); vertical-align:top;">' + esc(r[0])
                + '</td><td style="padding:2px 0; color:var(--hd-ink, #cfe8f2);'
                + ' font-family:var(--hd-mono, monospace);">' + esc(r[1])
                + '</td></tr>';
        }).join('');
        return '<table style="border-collapse:collapse; font-size:0.7rem;'
            + ' width:100%;"><tbody>' + body + '</tbody></table>';
    }

    function plotBox(id, height) {
        return '<div id="' + esc(id) + '" data-cfd-plot="1" style="width:100%;'
            + ' height:' + (height || 280) + 'px;"></div>';
    }

    // ------------------------------------------------------------------
    // Çizimler — hepsi yanıttan; hesap yok, yumuşatma yok, örnekleme yok.
    // ------------------------------------------------------------------
    /* P11B3-24 — KOLON ORTALAMASI PROFİLİ ÇİZİLİR.
       Uç `section_average` bloğunda z, Mach ve basınç dizilerini
       yayımlıyordu; panel bloğu görünüm modeline alıyor, hiçbir yerde
       kullanmıyordu. Duvar eğrisi (p_w) ile AYNI değildir: bu, kesitin
       hacim ağırlıklı ortalamasıdır ve ucun kendi _basis cümlesi bunu
       söyler. Sayı türetilmez, iki eksende olduğu gibi çizilir. */
    function sectionAverageFigure(vm) {
        const sa = vm.sectionAverage || {};
        const z = numArray(sa.z_m) || [];
        const mach = numArray(sa.mach);
        const pPa = numArray(sa.pressure_Pa);
        const traces = [];
        if (mach) {
            traces.push({
                x: z, y: mach, mode: 'lines', type: 'scatter',
                line: { width: 2, color: '#00e5ff' },
                name: T('panel.cfd.traceSecMach',
                        'section_average.mach (column average)'),
            });
        }
        if (pPa) {
            traces.push({
                x: z, y: pPa.map(function (v) { return v / PA_PER_BAR; }),
                mode: 'lines', type: 'scatter', yaxis: 'y2',
                line: { width: 2, color: '#ff8c33' },
                name: T('panel.cfd.traceSecP',
                        'section_average.pressure (column average) [bar]'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.cfd.chartSectionAverage',
                    'Section-averaged Mach and pressure (section_average)'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisSecMach',
                                  'Section-average Mach [-]') },
                yaxis2: { title: T('panel.cfd.axisSecP',
                                   'Section-average pressure [bar]'),
                          overlaying: 'y', side: 'right' },
                height: 280, showlegend: true,
                margin: { t: 40, r: 60, b: 50, l: 60 },
            },
        };
    }

    function sectionAverageVar(vm) {
        const sa = vm.sectionAverage || {};
        return Array.isArray(sa.z_m) && sa.z_m.length
            && (Array.isArray(sa.mach) || Array.isArray(sa.pressure_Pa));
    }

    function wallFigure(vm) {
        const traces = [{
            x: vm.wall.z, y: vm.wall.pBar, mode: 'lines+markers', type: 'scatter',
            line: { width: 2, color: '#00e5ff' }, marker: { size: 4 },
            name: T('panel.cfd.traceWall', 'p_w (solver cells next to the wall)'),
        }];
        // Eşik çizgisi yalnız POZİTİFKEN çizilir: vakumda (P_ortam = 0)
        // eşik 0'dır ve logaritmik eksende 0 gösterilemez — çizgi sessizce
        // kırpılırdı. Sayı gizlenmiyor: eşik künye tablosunda 0 olarak durur
        // ve köprü zaten "ölçüt uygulanamaz" beyanını basar.
        if (isNum(vm.wall.thresholdBar) && vm.wall.thresholdBar > 0
                && vm.wall.z.length) {
            traces.push({
                x: [vm.wall.z[0], vm.wall.z[vm.wall.z.length - 1]],
                y: [vm.wall.thresholdBar, vm.wall.thresholdBar],
                mode: 'lines', type: 'scatter',
                line: { width: 2, dash: 'dash', color: THRESHOLD_COLOR },
                name: TF('panel.cfd.traceThreshold',
                    { k: sigFig(vm.separation.separation_factor),
                      pa: sigFig(vm.separation.ambient_pressure_Pa) },
                    'Separation threshold k*P_ambient (k = {k}, P_ambient = {pa} Pa)'),
            });
        }
        if (isNum(vm.wall.sepZ) && isNum(vm.wall.sepPBar)) {
            traces.push({
                x: [vm.wall.sepZ], y: [vm.wall.sepPBar],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, color: SEP_COLOR, symbol: 'x' },
                name: T('panel.cfd.traceSepPoint',
                        'First separated station (solver cell)'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.cfd.chartWall',
                         'Wall pressure p_w(z) and the separation criterion'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisPBar',
                                  'Wall pressure [bar] (log scale)'),
                         type: 'log' },
                height: 300,
                legend: { orientation: 'h', y: -0.28 },
                margin: { t: 40, r: 12, b: 60, l: 60 },
            },
        };
    }

    //: Ekranda GÖSTERİLEBİLEN büyüklük: kullanıcının seçtiği büyüklük bu
    //: yanıtta yoksa (eski uç: temperature_K yok) yükte GERÇEKTEN olan ilk
    //: büyüklüğe düşülür. Düşüş sessiz değildir — `metricNotesHtml` nedeni
    //: adıyla yazar ve uydurma sıcaklık üretilmez.
    function activeMetric(vm) {
        const av = (vm.field && vm.field.available) || [];
        if (av.indexOf(fieldMetric) >= 0) return fieldMetric;
        return av.length ? av[0] : FIELD_METRICS[0].id;
    }

    function fieldValues(vm) {
        return vm.field.values[activeMetric(vm)];
    }

    function fieldTitles(vm) {
        const id = activeMetric(vm);
        const m = metricById(id);
        const metric = T(m.labelKey, m.labelFallback);
        return {
            id: id,
            metric: metric,
            // Başlık BİLEREK kısa: Merkez'in görüntüleyici sütunu dar ve
            // uzun başlık kırpılıyordu (ölçüldü, canlı hibrit sayfası).
            // "eksen r = 0'da, duvar üstte" açıklaması kaybolmadı: alan
            // bloğunun kendi _basis cümlesi grafiğin ALTINDA aynen basılıyor.
            title: TF('panel.cfd.chartField', { metric: metric },
                'Flow field on the solver cells — {metric}'),
            colorscale: metricColorscale(id),
        };
    }

    function wallLineTrace(vm) {
        if (!vm.wallLine) return null;
        return {
            x: vm.wallLine.z, y: vm.wallLine.r, mode: 'lines', type: 'scatter',
            line: { width: 2, color: WALL_COLOR },
            name: T('panel.cfd.traceWallLine',
                    'Nozzle wall (the contour sent to the solver)'),
        };
    }

    function fieldFigure(vm) {
        const f = vm.field;
        const t = fieldTitles(vm);
        const carpetId = 'cfdFieldCarpet' + drawSeq;
        const kontur = {
            type: 'contourcarpet', carpet: carpetId,
            a: f.a, b: f.b, z: fieldValues(vm),
            contours: { coloring: 'fill', showlines: false },
            colorbar: { title: t.metric, titleside: 'right' },
            name: t.metric,
        };
        // Paylaşılan durak tablosu yüklü değilse `colorscale` HİÇ verilmez
        // (yedek tablo yazmak ikinci tanım olurdu); nedeni ekrana yazılır.
        if (t.colorscale) kontur.colorscale = t.colorscale;
        const traces = [{
            type: 'carpet', carpet: carpetId,
            a: f.a, b: f.b, x: f.x, y: f.y,
            aaxis: { showgrid: false, showticklabels: 'none',
                     showticksuffix: 'none', smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none',
                     showticksuffix: 'none', smoothing: 0, title: '' },
        }, kontur];
        const wl = wallLineTrace(vm);
        if (wl) traces.push(wl);
        return {
            traces: traces,
            layout: {
                title: t.title,
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisR', 'Radius r [m]') },
                height: 320, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 60 },
            },
        };
    }

    //: Carpet izi bulunmayan Plotly derlemesinde: hücre merkezi nokta
    //: haritası (fea_panel.js ile aynı yedek). Değerler AYNI, gösterim farklı.
    function fieldFallbackFigure(vm) {
        const f = vm.field;
        const t = fieldTitles(vm);
        const values = fieldValues(vm);
        const x = [], y = [], c = [];
        for (let j = 0; j < f.x.length; j++) {
            for (let i = 0; i < f.x[j].length; i++) {
                x.push(f.x[j][i]); y.push(f.y[j][i]); c.push(values[j][i]);
            }
        }
        const marker = { color: c, size: 6,
                         colorbar: { title: t.metric, titleside: 'right' } };
        if (t.colorscale) marker.colorscale = t.colorscale;
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: marker,
            name: t.metric,
        }];
        const wl = wallLineTrace(vm);
        if (wl) traces.push(wl);
        return {
            traces: traces,
            layout: {
                title: t.title,
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisR', 'Radius r [m]') },
                height: 320, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 60 },
            },
        };
    }

    function residualFigure(vm) {
        return {
            traces: [{
                x: vm.residual.iteration, y: vm.residual.value,
                mode: 'lines', type: 'scatter',
                line: { width: 2, color: '#2dd4a8' },
                name: T('panel.cfd.traceResidual', 'Density L2 residual'),
            }],
            layout: {
                title: T('panel.cfd.chartResidual',
                         'Convergence history — density L2 residual'),
                xaxis: { title: T('panel.cfd.axisIter', 'Iteration') },
                yaxis: { title: T('panel.cfd.axisResidual',
                                  'Residual [rho0*a0/L scale] (log)'),
                         type: 'log' },
                height: 260, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 70 },
            },
        };
    }

    // ------------------------------------------------------------------
    // VİSKOZ ÇİZİMLER — hepsi yanıttaki dizilerin kendisi (dönüşüm yok).
    // Renk TEK taşıyıcı değildir: her iz ayrıca çizgi DESENİ ve işaretçi
    // SEMBOLÜ ile ayrılır ve adı efsanede yazılıdır (E3/WCAG deseni).
    // ------------------------------------------------------------------
    function wallHeatFigure(vm) {
        const w = vm.viscous.wall;
        return {
            traces: [{
                x: w.z, y: w.qw, mode: 'lines+markers', type: 'scatter',
                line: { width: 2, color: '#ff8c33' },
                marker: { size: 4, symbol: 'circle' },
                name: T('panel.cfd.traceQw',
                        'q_w (solver measurement, signed)'),
            }],
            layout: {
                title: T('panel.cfd.chartQw',
                         'Wall heat flux q_w(z) as the solver measured it'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisQw',
                                  'Wall heat flux [W/m^2]') },
                height: 280, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 80 },
            },
        };
    }

    //: h_g: İKİ KAYNAK YAN YANA + fark alanı (oran) ikinci eksende.
    //: Kaynak etiketi izin ADINDA geçer — hangi eğrinin hangi model
    //: olduğu renkten bağımsız okunur.
    function filmFigure(vm) {
        const v = vm.viscous;
        const traces = [];
        if (v.bartz.available && v.bartz.hg) {
            traces.push({
                x: v.bartz.z, y: v.bartz.hg, mode: 'lines', type: 'scatter',
                line: { width: 2, color: '#00e5ff', dash: 'dash' },
                name: T('panel.cfd.traceHgBartz',
                        'h_g — source: Bartz correlation'),
            });
        }
        if (v.thermal.available && v.thermal.hg) {
            traces.push({
                // Eksen METRE: profilin kendi x_mm dizisi MİLİMETREdir ve
                // Bartz serisi metrede — ikisini aynı grafiğe koyarken
                // duvar ekseninin (wall.z, metre) TA KENDİSİ kullanılır.
                // Ara değerleme YOK: iki seri zaten aynı istasyonlarda.
                x: v.wall.z, y: v.thermal.hg,
                mode: 'lines+markers', type: 'scatter',
                line: { width: 2, color: '#2dd4a8' },
                marker: { size: 4, symbol: 'square' },
                name: T('panel.cfd.traceHgCfd',
                        'h_g — source: CFD (cfd_viscous)'),
            });
        }
        if (v.bartz.ratio) {
            traces.push({
                x: v.bartz.z, y: v.bartz.ratio, mode: 'lines',
                type: 'scatter', yaxis: 'y2',
                line: { width: 2, color: '#7d97a5', dash: 'dot' },
                name: T('panel.cfd.traceHgRatio',
                        'difference field: h_g(CFD) / h_g(Bartz)'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.cfd.chartHg',
                         'Gas-side film coefficient — two sources side by side'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisHg',
                                  'h_g [W/(m^2 K)] (log scale)'),
                         type: 'log' },
                yaxis2: { title: T('panel.cfd.axisHgRatio',
                                   'h_g(CFD) / h_g(Bartz) [-] (log)'),
                          type: 'log', overlaying: 'y', side: 'right' },
                height: 320,
                legend: { orientation: 'h', y: -0.30 },
                margin: { t: 40, r: 70, b: 70, l: 80 },
            },
        };
    }

    function shearFigure(vm) {
        const v = vm.viscous;
        const traces = [{
            x: v.wall.z, y: v.wall.tau, mode: 'lines', type: 'scatter',
            line: { width: 2, color: '#00e5ff' },
            name: T('panel.cfd.traceTau', 'tau_w [Pa] (signed)'),
        }];
        if (v.skin.available && v.skin.cf) {
            traces.push({
                x: v.skin.z, y: v.skin.cf, mode: 'lines+markers',
                type: 'scatter', yaxis: 'y2',
                line: { width: 2, color: '#ff8c33', dash: 'dashdot' },
                marker: { size: 4, symbol: 'diamond' },
                name: T('panel.cfd.traceCf',
                        'c_f = tau_w / (0.5 gamma p_w M_e^2)'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.cfd.chartShear',
                         'Wall shear tau_w(z) and the skin friction coefficient'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisTau', 'tau_w [Pa]') },
                yaxis2: { title: T('panel.cfd.axisCf', 'c_f [-]'),
                          overlaying: 'y', side: 'right' },
                height: 300,
                legend: { orientation: 'h', y: -0.30 },
                margin: { t: 40, r: 70, b: 70, l: 70 },
            },
        };
    }

    function drawFigure(id, figure) {
        const el = document.getElementById(id);
        if (!el || !window.Plotly || typeof window.Plotly.react !== 'function') {
            return false;
        }
        window.Plotly.react(el, figure.traces, figure.layout,
                            { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Rozet şeridi — her rozet BİR beyandır; künyesinde çözücünün cümlesi.
    // ------------------------------------------------------------------
    //: y⁺ ROZETİNİN RENGİ: renk TEK taşıyıcı değildir (E3/WCAG deseni) —
    //: bant adı rozetin METNİNDE geçer ve künyesinde ucun gerekçe cümlesi
    //: durur. 'log_layer' ve 'buffer_layer' HÜKÜM DEĞİL, okuma uyarısıdır.
    const Y_PLUS_BADGE_KIND = {
        wall_resolved: 'ok', buffer_layer: 'warn',
        log_layer: 'warn', unmeasured: 'dim',
    };

    function viscousBadgesHtml(vm) {
        const v = vm.viscous;
        if (!v) return '';                     // eski uç: viskoz alanı yok
        if (!v.enabled) {
            return badge(T('panel.cfd.badgeInviscid',
                'INVISCID (Euler) — no wall shear, no wall heat flux'),
                'dim', SRV(v.basis));
        }
        let html = badge(TF('panel.cfd.badgeViscousMode',
            { turb: v.turbulence, wall: v.wallThermal },
            'VISCOUS — turbulence {turb}, {wall} wall'), 'info',
            SRV(v.basis));
        const b = v.badge;
        if (b && b.code) {
            const metin = (b.code === 'wall_resolved')
                ? TF('panel.cfd.badgeYPlusResolved',
                    { y: fmtAuto(b.y_plus_max, 2) },
                    'WALL RESOLVED — max y+ = {y}')
                : (b.code === 'buffer_layer')
                    ? TF('panel.cfd.badgeYPlusBuffer',
                        { y: fmtAuto(b.y_plus_max, 2) },
                        'FIRST CELL IN THE BUFFER LAYER — max y+ = {y}')
                    : (b.code === 'log_layer')
                        ? TF('panel.cfd.badgeYPlusLog',
                            { y: fmtAuto(b.y_plus_max, 2) },
                            'FIRST CELL IN THE LOG LAYER — max y+ = {y}, '
                            + 'no wall function: q_w reads LOW')
                        : T('panel.cfd.badgeYPlusUnmeasured',
                            'y+ NOT MEASURED');
            html += badge(metin, Y_PLUS_BADGE_KIND[b.code] || 'dim',
                          SRV(b.basis));
        }
        // DOĞRULAMA ÇİZGİSİ (parti 39/A3): duvar ısı akısı DOĞRULANMADI.
        // Bu rozet q_w/h_g gösterildiği her ekranda görünür ve künyesi ucun
        // validation_basis cümlesinin TA KENDİSİDİR.
        if (v.thermal.available || v.wall.qw) {
            html += badge(T('panel.cfd.badgeHeatNotValidated',
                'WALL HEAT FLUX NOT VALIDATED — read with the y+ badge'),
                'warn', SRV(v.validationBasis));
        }
        if (!v.thermal.available && v.thermal.reason) {
            html += badge(T('panel.cfd.badgeNoFilmCoeff',
                'NO GAS-SIDE FILM COEFFICIENT — the bridge refused this run'),
                'dim', SRV(v.thermal.reason));
        }
        return html;
    }

    function badgesHtml(vm) {
        let html = '';
        if (vm.converged === true) {
            html += badge(TF('panel.cfd.badgeConverged',
                { iters: txt(vm.iterations) },
                'CONVERGED — {iters} iterations'), 'ok', SRV(vm.convergenceBasis));
        } else if (vm.converged === false) {
            html += badge(TF('panel.cfd.badgeNotConverged',
                { res: fmtExp(vm.residual.last), iters: txt(vm.iterations) },
                'NOT CONVERGED — residual {res} after {iters} iterations'),
                'warn', SRV(vm.convergenceBasis));
        } else if (vm.converged === null
                   && vm.convergenceStatus === 'not_evaluated') {
            // HÜKÜM YARGILANMADI (ÖH defter OH-D31-15; Berke kararı
            // 15 Eyl 2026 seç. A). Çözücü üç durumlu döner: true / false /
            // null. null'da ESKİDEN buraya hiçbir dal düşmüyordu çünkü
            // çözücü o hâlde bile `converged: true` yayımlıyordu ve panel
            // YEŞİL 'CONVERGED' rozeti basıyordu — ölçüldü (once.json K1):
            // §11.3'ün dört referansının ÜÇÜNDE şemanın kendi kalıntısı
            // yayımlanandan 44,29 / 398,71 / 2,9e7 kat büyükken rozet
            // 'ok' idi. Artık hüküm yokluğu ADIYLA basılır; renk 'warn',
            // künyesi çözücünün kendi cümlesi (neden yargılanmadığını
            // sayıyla söyler). Sahte 'ok' buradan ÇIKMAZ.
            html += badge(T('panel.cfd.critNoVerdict', 'no verdict published'),
                'warn', SRV(vm.convergenceBasis));
        }
        // PLATO ROZETİ (OH-Z5-14): "bütçeyi büyüt" ile "bu vaka
        // sınıfında hedef ULAŞILAMAZ" ayrı şeylerdir. Çözücü ikincisini
        // ÖLÇTÜYSE kullanıcı bunu rozette görür — yoksa tavanı büyütüp
        // aynı duvara defalarca çarpardı. Rozet çözücünün kendi
        // hükmündendir; panel plato KARARI VERMEZ.
        if (vm.convergenceStatus === 'plateau') {
            const pl = vm.plateau || {};
            html += badge(TF('panel.cfd.badgePlateau',
                { res: fmtExp(pl.plateau_residual, 3),
                  tol: fmtExp(pl.target_residual, 2),
                  span: String(pl.window_iterations == null
                               ? '—' : pl.window_iterations) },
                'RESIDUAL PLATEAU — the scheme residual stood at {res} '
                + '(target {tol}) for {span} iterations; a bigger '
                + 'iteration budget does not earn the verdict'),
                'warn', SRV(pl.reason || ''));
        }

        const sep = vm.separation;
        // GÜVEN RENGİ KURALI: köprü hükmünü 'suspect' etiketiyle verdiyse
        // (çözücü oturmadı) o hüküm YEŞİL BASILAMAZ. Rozet kaybolmaz, sayı
        // gizlenmez — yalnız kabul rengi verilmez, çünkü oturmamış bir alana
        // uygulanmış ölçüt "temiz" değildir (aynı kural fea_panel'de ölçülmemiş
        // kalite ölçütü için de uygulanıyor).
        // OH-D31-15: KABUL RENGİ YALNIZ 'firm'e verilir. Eskiden kural
        // "suspect DEĞİLSE yeşil" idi; köprü üçüncü bir etiket
        // ('not_evaluated' — çözücü hükmü YARGILAMADI) döndürünce o kural
        // yeşil basardı. Kural artık olumlu tarafı adlandırır: hüküm
        // SAĞLAM değilse yeşil yok.
        const hukumKesin = !!(sep && sep.judgment_confidence === 'firm');
        if (sep && sep.bridge_refused) {
            html += badge(T('panel.cfd.badgeSepRefused',
                'NO SEPARATION JUDGEMENT — the bridge refused this solution'),
                'dim', SRV(sep.not_applicable_reason || sep._basis || ''));
        } else if (sep && sep.applicable === false) {
            html += badge(T('panel.cfd.badgeSepNotApplicable',
                'SEPARATION CRITERION NOT APPLICABLE'),
                'dim', SRV(sep.not_applicable_reason || ''));
        } else if (sep && sep.separated === true) {
            html += badge(TF('panel.cfd.badgeSeparated',
                { frac: fmt(100 * sep.separated_length_fraction, 1),
                  len: sigFig(sep.separated_length_m),
                  n: sep.stations_below_threshold },
                'FLOW SEPARATION PREDICTED — {frac}% of the divergent length '
                + '({len} m, {n} stations below the threshold)'),
                'warn', SRV(sep.criterion_basis || ''));
        } else if (sep && sep.separated === false) {
            html += badge(TF('panel.cfd.badgeAttached',
                { margin: fmtAuto(sep.wall_pressure_margin_min, 2) },
                'NO SEPARATION — the minimum wall pressure is {margin}x the '
                + 'threshold'), hukumKesin ? 'ok' : 'dim',
                SRV(sep.criterion_basis || ''));
        }
        if (sep && sep.judgment_confidence === 'suspect') {
            html += badge(T('panel.cfd.badgeSepSuspect',
                'SEPARATION JUDGEMENT SUSPECT — the field it was applied to '
                + 'did not settle'), 'warn', SRV(sep.judgment_basis || ''));
        } else if (sep && sep.judgment_confidence === 'not_evaluated') {
            // 'suspect' ÖLÇÜLMÜŞ bir yakınsamama hükmüne ayrılmıştır
            // ("alan oturmadı"); bu dal ise "oturup oturmadığına
            // BAKILMADI" der. İkisi aynı rozetle basılırsa panel
            // ölçülmemiş bir hükmü ölçülmüş gibi gösterir.
            html += badge(T('panel.cfd.critNoVerdict', 'no verdict published'),
                'warn', SRV(sep.judgment_basis || ''));
        }
        if (sep && sep.reattachment_suspected) {
            html += badge(T('panel.cfd.badgeReattach',
                'REATTACHMENT SUSPECTED'), 'warn',
                SRV(sep.reattachment_basis || ''));
        }
        // BÜTÇE UYARISI (eski Mach eşikli 'INLET ADVISORY' rozetinin halefi).
        // Rozet metni ateşleyen GEREKÇEYİ söyler: "uyarı var" demek yetmez,
        // kullanıcı hangi ölçümün konuştuğunu görmeli. Uyarı bir hüküm
        // değildir; yakınsama rozeti onun yanında BAĞIMSIZ olarak durur
        // (bekçi: aynı ekranda uyarı + CONVERGED birlikte görünebilmeli).
        if (vm.inlet && vm.inlet.budget_advisory) {
            const gerekceler = Array.isArray(vm.inlet.budget_advisory_reasons)
                ? vm.inlet.budget_advisory_reasons : [];
            const bantMi = gerekceler.indexOf('measured_slow_band') >= 0;
            const azMi = gerekceler.indexOf('budget_below_measured_need') >= 0;
            const yakin = vm.inlet.nearest_measured || {};
            let metin;
            if (bantMi && azMi) {
                metin = TF('panel.cfd.badgeBudgetAdvisoryBoth',
                    { cr: fmt(vm.inlet.contraction_ratio, 2),
                      budget: vm.inlet.max_iterations, need: yakin.iterations },
                    'ITERATION BUDGET ADVISORY — measured runs near '
                    + 'contraction ratio {cr} are slow AND the requested '
                    + 'budget ({budget}) is below the measured need ({need})');
            } else if (azMi) {
                metin = TF('panel.cfd.badgeBudgetAdvisoryLow',
                    { budget: vm.inlet.max_iterations, need: yakin.iterations },
                    'ITERATION BUDGET ADVISORY — the requested budget '
                    + '({budget}) is below the measured need of the nearest '
                    + 'measured case ({need} iterations)');
            } else {
                metin = TF('panel.cfd.badgeBudgetAdvisoryBand',
                    { cr: fmt(vm.inlet.contraction_ratio, 2) },
                    'ITERATION BUDGET ADVISORY — measured runs near '
                    + 'contraction ratio {cr} spend most of the budget');
            }
            html += badge(metin, 'warn', SRV(vm.inlet._basis || ''));
        }
        html += viscousBadgesHtml(vm);
        // Korunum artıkları RENKSİZ (info) yayımlanır: ucun yayımladığı bir
        // KABUL EŞİĞİ yok, panelin kendi eşiğini uydurması da yasak.
        html += badge(TF('panel.cfd.badgeMass',
            { v: fmtExp(vm.budget.mass_balance_rel) },
            'MASS IMBALANCE {v} (relative)'), 'info', SRV(vm.budget._basis || ''));
        // ÖH D19 · P11B3-07 — VİSKOZ KOŞUNUN BÜTÇESİ ROZETTE.
        // ÖLÇÜLDÜ (P11 B3-repro-10/12, taban 60cd341): viskoz koşuda rozet
        // `energy_balance_rel` = 6,08e-04 basıyordu ve kullanıcı bunu bir
        // korunum hatası sanıyordu; oysa ucun KENDİ künyesi "VİSKOZ
        // KOŞUDA energy_balance_rel TEK BAŞINA OKUNMAZ … viskoz koşunun
        // bütçesi viscous_energy_balance_rel alanıdır" diyor ve o alan
        // 3,58e-10 (1.696.000 kat küçük). Fark korunum hatası değil,
        // izotermal duvardan çıkan ısıdır (wall_heat_W farkın %100,56'sı).
        // Panel o alanı hiç okumuyordu (grep: 0 eşleşme).
        // Euler koşusunda alan None'dır (sıfır değil, YOK) — o dalda eski
        // rozet aynen basılır, uydurma yapılmaz.
        const viskozButce = isNum(vm.budget.viscous_energy_balance_rel)
            ? vm.budget.viscous_energy_balance_rel : null;
        if (viskozButce !== null) {
            html += badge(TF('panel.cfd.badgeViscousEnergy',
                { v: fmtExp(viskozButce) },
                'ENERGY IMBALANCE {v} (relative, VISCOUS budget: wall heat '
                + 'and boundary viscous fluxes included)'), 'info',
                SRV(vm.budget._basis || ''));
            html += badge(TF('panel.cfd.badgeEnergyEulerForm',
                { v: fmtExp(vm.budget.energy_balance_rel) },
                'EULER-FORM ENERGY RESIDUAL {v} — NOT the budget of a '
                + 'viscous run: it compares Euler surface fluxes only, so '
                + 'the wall heat and the viscous boundary fluxes are '
                + 'missing from it'), 'dim',
                SRV(vm.budget._basis || ''));
        } else {
            html += badge(TF('panel.cfd.badgeEnergy',
                { v: fmtExp(vm.budget.energy_balance_rel) },
                'ENERGY IMBALANCE {v} (relative)'), 'info',
                SRV(vm.budget._basis || ''));
        }
        html += badge(TF('panel.cfd.badgeKernel', { backend: txt(vm.kernel) },
            'KERNEL {backend}'), 'info', SRV(vm.kernelBasis));
        html += badge(TF('panel.cfd.badgeShock', { n: txt(vm.shockColumns) },
            'SHOCK SENSOR — {n} flagged columns'), 'info', SRV(vm.shockBasis));
        if (isNum(vm.limiterIter)) {
            html += badge(TF('panel.cfd.badgeLimiter',
                { iter: vm.limiterIter, n: vm.limiterCount },
                'LIMITER FROZEN at iteration {iter} ({n}x)'), 'info',
                SRV(vm.convergenceBasis));
        } else {
            html += badge(T('panel.cfd.badgeLimiterNever',
                'LIMITER NEVER FROZEN'), 'info', SRV(vm.convergenceBasis));
        }
        html += badge(TF('panel.cfd.badgeRuntime',
            { s: fmt(vm.runtime, 1), solver: fmt(vm.solverRuntime, 1) },
            'RUNTIME {s} s (solver {solver} s)'), 'dim', SRV(vm.runtimeBasis));
        if (carpetFallback) {
            html += badge(T('panel.cfd.badgeCarpetFallback',
                'CONTOUR TRACE UNAVAILABLE — cell point map drawn instead'),
                'dim', '');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Beyan blokları
    // ------------------------------------------------------------------
    function listBlock(value) {
        if (Array.isArray(value)) {
            return '<ul style="margin:4px 0 0 16px; padding:0; font-size:0.7rem;'
                + ' color:var(--hd-ink, #cfe8f2);">'
                + value.map(function (v) { return '<li>' + esc(SRV(v)) + '</li>'; })
                    .join('') + '</ul>';
        }
        if (value && typeof value === 'object') {
            return kvTable(Object.keys(value).map(function (k) {
                return [k, SRV(String(value[k]))];
            }));
        }
        return '';
    }

    //: Uyarı gerekçesinin okunur karşılığı — SÖZLÜK ANAHTARINA bağlı, ham
    //: makine adı da parantezde kalır (uç yeni bir gerekçe eklerse ekranda
    //: sessizce kaybolmasın diye bilinmeyen ad AYNEN basılır).
    function advisoryReasonText(reason) {
        if (reason === 'measured_slow_band') {
            return T('panel.cfd.reasonSlowBand',
                'the contraction ratio falls in a measured slow band')
                + ' (' + reason + ')';
        }
        if (reason === 'budget_below_measured_need') {
            return T('panel.cfd.reasonBudgetLow',
                'the requested budget is below the measured need')
                + ' (' + reason + ')';
        }
        return String(reason);
    }

    //: Bant kenarı yayımlanmamışsa (tablo orada BİTİYOR) sayı uydurulmaz:
    //: açık uç işareti basılır ve bunun EKSTRAPOLASYON olduğu yazılır.
    function bandText(band) {
        const alt = isNum(band.cr_min) ? fmt(band.cr_min, 2)
            : T('panel.cfd.bandOpen', 'open (beyond the measured table)');
        const ust = isNum(band.cr_max) ? fmt(band.cr_max, 2)
            : T('panel.cfd.bandOpen', 'open (beyond the measured table)');
        return alt + ' … ' + ust;
    }

    function inletHtml(vm) {
        const inlet = vm.inlet || {};
        let html = sectionTitle('panel.cfd.secInlet',
            'Inlet conditioning and the iteration budget advisory (declared '
            + 'by the endpoint)');
        const gerekceler = Array.isArray(inlet.budget_advisory_reasons)
            ? inlet.budget_advisory_reasons : [];
        const satirlar = [
            [T('panel.cfd.rowContraction', 'Contraction ratio A_inlet/A_throat'),
             fmt(inlet.contraction_ratio, 3)],
            [T('panel.cfd.rowInletMach',
               'Isentropic subsonic inlet Mach (information only)'),
             fmt(inlet.inlet_mach_isentropic, 4)],
            [T('panel.cfd.rowInletBc', 'Solver inlet boundary condition'),
             String(inlet.inlet_bc == null ? '—' : inlet.inlet_bc)],
            [T('panel.cfd.rowBudget', 'Iteration budget (effective / source)'),
             txt(vm.maxIterations) + ' / ' + txt(vm.maxIterationsSource)],
            [T('panel.cfd.rowBudgetAdvisory', 'Budget advisory for this run'),
             inlet.budget_advisory
                 ? T('panel.cfd.yes', 'yes') : T('panel.cfd.no', 'no')],
        ];
        if (gerekceler.length) {
            satirlar.push([T('panel.cfd.rowAdvisoryReasons',
                'Why it fired (rules named by the endpoint)'),
                gerekceler.map(advisoryReasonText).join('; ')]);
        }
        const yakin = inlet.nearest_measured;
        if (yakin) {
            satirlar.push([T('panel.cfd.rowNearestMeasured',
                'Nearest measured case (CR / iterations / converged)'),
                fmt(yakin.contraction_ratio, 3) + ' / '
                    + String(yakin.iterations) + ' / '
                    + (yakin.converged ? T('panel.cfd.yes', 'yes')
                                       : T('panel.cfd.no', 'no'))]);
        }
        const bantlar = Array.isArray(inlet.budget_advisory_bands)
            ? inlet.budget_advisory_bands : [];
        bantlar.forEach(function (b) {
            satirlar.push([TF('panel.cfd.rowAdvisoryBand',
                { res: String(b.resolution) },
                'Measured slow band at "{res}" (contraction ratio)'),
                bandText(b)]);
        });
        html += kvTable(satirlar);

        // ÖLÇÜM TABLOSU — uçtan geldiği gibi. Panel bu tabloyu ne üretir ne
        // de özetler; kullanıcı beklentinin dayandığı sayıları görür.
        const tablo = Array.isArray(inlet.measured_expectations)
            ? inlet.measured_expectations : [];
        if (tablo.length) {
            html += sectionTitle('panel.cfd.secMeasuredExpect',
                'Measured convergence table the advisory is derived from');
            html += kvTable(tablo.map(function (row) {
                return [String(row.resolution) + '  CR '
                            + fmt(row.contraction_ratio, 3),
                        String(row.iterations) + ' '
                            + T('panel.cfd.iterationsWord', 'iterations') + ', '
                            + (row.converged
                                ? T('panel.cfd.expectConverged', 'converged')
                                : T('panel.cfd.expectCeiling',
                                    'hit the budget ceiling'))
                            + ', ' + T('panel.cfd.expectResidual', 'residual')
                            + ' ' + fmtExp(row.residual_last, 2)];
            }));
        }
        html += note(T('panel.cfd.notVerdict',
            'This advisory is NOT a verdict and it never blocks a run: it '
            + 'states the pre-run expectation with the measurement behind it. '
            + 'The verdict is the solver\'s own convergence declaration above.'),
            'dim');
        html += basisText(inlet._basis);
        html += basisText(inlet.inlet_bc_basis);
        return html;
    }

    //: MODELLENMEDİ ÇİPİ — veri yoksa boş grafik ya da sıfır dizisi
    //: çizilmez; katman HİÇ çizilmez ve nedeni ADIYLA yazılır.
    function notModelledChip(text) {
        return '<span data-cfd-chip="not-modelled" style="border:1px dashed '
            + COLORS.dim + '; color:' + COLORS.dim + '; border-radius:6px;'
            + ' padding:2px 9px; font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; display:inline-block; margin:4px 4px 4px 0;">'
            + esc(T('panel.cfd.chipNotModelled', 'NOT MODELLED')) + ' — '
            + esc(SRV(text)) + '</span>';
    }

    //: P11B3-22 — bir ALT bloğun kendi 'modellenmedi' listesi. Başlık
    //: mevcut çeviriden gelir, yanına bloğun ALAN ADI (makine verisi)
    //: yazılır ki hangi köprünün beyanı olduğu karışmasın.
    function altNotModelledHtml(ad, blok) {
        if (!blok || typeof blok !== 'object' || !Object.keys(blok).length) {
            return '';
        }
        return '<div data-cfd-block="not-modelled-' + esc(ad) + '"'
            + ' style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);">'
            + esc(T('panel.cfd.declNotModelled', 'NOT MODELLED'))
            + ' — ' + esc(ad) + '</strong>' + listBlock(blok) + '</div>';
    }

    //: Ayrılma ÖLÇÜTLERİ — dört üye yan yana. Üyeler ucun `separation.
    //: criteria` sözlüğünden gelir; panel ölçütü YENİDEN HESAPLAMAZ ve
    //: birini "asıl hüküm" diye öne çıkarmaz. Güven etiketi (reliability)
    //: her satırda ADIYLA durur — 'model_dependent' bir uyarıdır, renk
    //: değil METİN taşır.
    function separationCriteriaHtml(vm) {
        const sep = vm.separation || {};
        const crit = sep.criteria;
        if (!crit || typeof crit !== 'object') return '';
        let html = sectionTitle('panel.cfd.secCriteria',
            'Separation criteria — four members side by side');
        const adlar = Object.keys(crit).sort();
        //: P11B3-25 — üye başına konum `criteria_spread.separation_z_m`
        //: sözlüğünde durur; panel yalnız `z_span_m` basıyordu.
        //: Güven künyeleri üyeler arasında TEKRARLIDIR (ampirik üçlü
        //: aynı cümleyi taşır); tabloyu şişirmemek için tekilleştirilip
        //: tablonun ALTINDA bir kez basılır.
        const guvenKunyeleri = {};
        const yayilim = sep.criteria_spread || {};
        const uyeKonum = (yayilim.separation_z_m
                          && typeof yayilim.separation_z_m === 'object')
            ? yayilim.separation_z_m : {};
        const satirlar = adlar.map(function (ad) {
            const m = crit[ad] || {};
            let deger;
            if (m.available === false) {
                deger = T('panel.cfd.critUnavailable', 'not available') + ' — '
                    + SRV(String(m.not_available_reason || ''));
            } else if (m.separated === true) {
                deger = TF('panel.cfd.critSeparated',
                    { z: sig(m.separation_z_m) },
                    'SEPARATED at z = {z} m');
            } else if (m.separated === false) {
                //: ÖH D33-2 / arayuz-panel a1 · kalem OH-FT-07 (Fable
                //: TOPLU fea-cfd-03) — ÜYENİN KENDİ PAYI EM TİREYE DÜŞMEZ.
                //: ÖLÇÜLDÜ (a1/once.json, bölüm K3): `cfd_tau_w` üyesinde
                //: `margin_min` TANIMSIZDIR — şemanın margin'i ölçüt
                //: niceliğinin EŞİĞİNE oranıdır ve bu üyenin eşiği
                //: τ_w = 0'dır, yani sıfıra bölme (hrma/cfd/separation.py,
                //: `margin_basis`). Üretici payı KENDİ adıyla
                //: (`tau_wall_min_over_max_abs`) ve KRİTİK DEĞERİYLE
                //: (`tau_wall_margin_critical_value` = 0; ampirik üyelerin
                //: "1'in altı = ayrıldı" kuralı BU üyede geçmez)
                //: yayımlıyor. Ölçüm: bu iki alanı okuyan JS dosyası
                //: sayısı 0'dı ve yapışık bir koşuda ekranda
                //: "attached (minimum margin —)" yazıyordu — üyenin
                //: ölçtüğü 0,371 hiç görünmüyordu. Sayı UYDURULMAZ, iki
                //: büyüklük aynı anahtarda TOPLANMAZ: pay kendi adıyla ve
                //: kritik değeriyle basılır (fail-closed).
                if (isNum(m.margin_min)) {
                    deger = TF('panel.cfd.critAttached',
                        { margin: fmtAuto(m.margin_min, 3) },
                        'attached (minimum margin {margin})');
                } else if (isNum(m.tau_wall_min_over_max_abs)) {
                    /* ÖH D33-3 / fix-38b (ana model, 16 Eylül 2026): yer
                       tutucu adları İngilizceleşti. TR değerdeki ``{deger}``
                       ASCII kayması bekçisini (test_i18n.py::
                       test_tr_values_have_no_ascii_slips) KIRMIZI yakıyordu —
                       yanlış pozitif değil KAPSAM sorunu: bekçi kullanıcıya
                       görünen metinde Türkçe karakter kaybı arıyor ve yer
                       tutucu adını ondan ayıramıyor. Deponun kanonu zaten
                       İngilizce ad ({name}/{value}/{limit}/{ratio}); bu anahtar
                       istisnaydı. Ekrana basılan metin DEĞİŞMEDİ. */
                    deger = TF('panel.cfd.critAttachedOwnRatio', {
                        name: 'tau_wall_min_over_max_abs',
                        value: fmtAuto(m.tau_wall_min_over_max_abs, 3),
                        critical: (isNum(m.tau_wall_margin_critical_value)
                            ? fmtAuto(m.tau_wall_margin_critical_value, 3)
                            : T('panel.cfd.critNoCriticalValue',
                                'not published')),
                    }, 'attached ({name} = {value}; this member separates at '
                       + '{critical}, NOT at 1)');
                } else {
                    deger = T('panel.cfd.critAttachedNoQuantity',
                        'attached — this member publishes no margin quantity, '
                        + 'and none is invented in its place');
                }
            } else {
                deger = T('panel.cfd.critNoVerdict', 'no verdict published');
            }
            if (m.reliability) {
                deger += '  [' + T('panel.cfd.critReliability', 'confidence')
                    + ': ' + String(m.reliability) + ']';
            }
            if (m.validity_warning) {
                deger += '  (' + SRV(String(m.validity_warning)) + ')';
            }
            //: ÖH D29 · P11B3-25 — ÜYENİN EŞİĞİ VE İSTASYONU DA DÜŞMEZ.
            //: ÖLÇÜLDÜ (a3/once.json): `threshold_min_Pa`,
            //: `threshold_max_Pa`, `separation_index`, `basis_kind` ve
            //: `reliability_basis` yükte VAR, panelde 0 kez okunuyordu —
            //: "dört üye yan yana" vaadi konumlar için tutuyor, EŞİKLER
            //: için tutmuyordu. Sayılar olduğu gibi basılır, panel eşik
            //: hesaplamaz; alan yoksa satır hiç yazılmaz.
            const kunye = [];
            if (m.basis_kind) kunye.push('basis_kind = ' + String(m.basis_kind));
            if (isNum(m.threshold_min_Pa) || isNum(m.threshold_max_Pa)) {
                kunye.push('threshold_Pa = '
                    + (isNum(m.threshold_min_Pa) ? sigRaw(m.threshold_min_Pa) : '—')
                    + ' … '
                    + (isNum(m.threshold_max_Pa) ? sigRaw(m.threshold_max_Pa) : '—'));
            }
            if (isNum(m.separation_index)) {
                kunye.push('separation_index = ' + m.separation_index);
            }
            if (isNum(uyeKonum[ad])) {
                kunye.push('criteria_spread.separation_z_m = '
                           + sigRaw(uyeKonum[ad]));
            }
            //: kvTable hücreyi KAÇIRIR (esc), o yüzden künye HTML
            //: değil düz metin olarak eklenir.
            if (kunye.length) deger += '  ·  ' + kunye.join('  ·  ');
            if (m.reliability_basis) {
                guvenKunyeleri[String(m.reliability_basis)] = true;
            }
            //: OH-FT-07 · ÖLÇÜM: `margin_basis` buraya EKLENMEDİ ve
            //: bilerek eklenmedi. Önce eklenmişti; ters mutasyon (M3b,
            //: a1/mutasyon_notu.md) bekçiyi KIRMIZI yakmadı ve sebebi
            //: ölçüldü: ucun beyanı ZATEN ekranda — güvertenin değer
            //: kaynağı künyesi (`AnalysisDock.ui.source.ledgerInto`,
            //: bu dosyada satır ~2938, `deep: true`) `*_basis` alanlarını
            //: tarıyor ve `margin_basis`i "NOT MODELLED" çipiyle metniyle
            //: birlikte basıyor. İkinci kez basmak aynı uzun cümleyi tek
            //: ekranda çoğaltmak olurdu; kusur BEYANIN YOKLUĞU değil,
            //: ölçüt satırının kendi payını göstermemesiydi (yukarıda).
            return [ad, deger];
        });
        html += kvTable(satirlar);
        Object.keys(guvenKunyeleri).forEach(function (t) {
            html += basisText(t);
        });
        const spread = sep.criteria_spread || {};
        if (spread.unanimous === false) {
            html += note(T('panel.cfd.critDisagree',
                'The criteria DISAGREE. That is not an error: the three '
                + 'empirical members are calibrated on turbulent experiments '
                + 'and the CFD member reads this run\'s own wall shear. The '
                + 'spread is published rather than hidden and no member is '
                + 'promoted over the others.'), 'warn');
        }
        if (isNum(spread.z_span_m)) {
            html += kvTable([[T('panel.cfd.rowCritSpan',
                'Spread of the separation stations [m]'),
                sig(spread.z_span_m)]]);
        }
        //: P11B3-25 — CFD üyesi ile deneysel üyeler arasındaki İŞARETLİ
        //: fark da yükte var ve düşüyordu (pozitifse CFD daha geç ayrılma
        //: gösterir). Alan adıyla basılır, yorum eklenmez.
        if (isNum(spread.cfd_minus_empirical_m)) {
            html += kvTable([['criteria_spread.cfd_minus_empirical_m [m]',
                              sig(spread.cfd_minus_empirical_m)]]);
        }
        html += basisText(spread._basis);
        html += basisText(sep.criteria_basis);
        return html;
    }

    //: ÖH D25 · P11B3-10 — AYRILMANIN KENDİ 'MODELLENMEDİ' LİSTESİ.
    //: ÖLÇÜLDÜ (a3/once.json, taban cdf2106): `separation.not_modelled`
    //: 9 kalem taşıyor (yanal yükler / `side_loads` dahil) ve panel
    //: ekranında bu listenin SIFIR kalemi görünüyordu — panel yalnız ÜST
    //: DÜZEY `cfd.not_modelled` bloğunu basıyordu. Ayrılma öngören bir
    //: koşuda kullanıcı "%32,1 ayrık" hükmünü görüyor ama bu hükmün yanal
    //: yük, FSS/RSS ayrımı ve şok-sınır tabaka etkileşimini İÇERMEDİĞİNİ
    //: göremiyordu. Hüküm ile hükmün KAPSAMI aynı ekranda durur.
    //: AYRI İŞLEV: liste `separation.criteria` bloğuna BAĞLI DEĞİLDİR —
    //: ölçüt üyeleri yayımlanmayan bir koşuda da ayrılma hükmü verilir ve
    //: o hükmün kapsamı yine yazılmalıdır (ölçüldü: criteria taşımayan
    //: yükte eski yerleşim listeyi hiç basmıyordu).
    function separationNotModelledHtml(vm) {
        const sep = vm.separation || {};
        const yok = sep.not_modelled;
        if (!yok || typeof yok !== 'object' || !Object.keys(yok).length) {
            return '';
        }
        return '<div data-cfd-block="separation-not-modelled"'
            + ' style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.sepNotModelled">'
            + esc(T('panel.cfd.sepNotModelled',
                    'NOT MODELLED BY THE SEPARATION JUDGEMENT ITSELF'))
            + '</strong>' + listBlock(yok) + '</div>';
    }

    // ------------------------------------------------------------------
    // VİSKOZ BÖLÜM — q_w / h_g (Bartz | CFD) / tau_w + c_f, y⁺ rozeti,
    // sürtünme kaybının ÜÇ kaynağı, doğrulama beyanı.
    // ------------------------------------------------------------------
    //: ÖLÇÜLEN SÜRE CÜZDANI — uçtan geldiği gibi. Sahte ilerleme çubuğu
    //: yok; ölçülmeyen hücre yükte YOKTUR ve burada da yazılmaz.
    //: ÖH D25 · P11B3-09 — q_w'NUN OKUNMA ŞARTI EKRANDA.
    //: ÖLÇÜLDÜ (a3/once.json, taban cdf2106): uç `viscous.grid_quality`
    //: bloğunu HER KOŞUMDA yayımlıyor ve kendi künyesinde "gradyan
    //: doğruluğu çarpıklıkla düşer ve bu, q_w iddiasının OKUNMA ŞARTIDIR"
    //: diyor; panel bloğu görünüm modeline alıyor (`gridQuality`) ama
    //: kaynakta o ad tam 1 kez — tanım satırında — geçiyordu: hiçbir
    //: çizim, tablo ya da künye onu kullanmıyordu. q_w / h_g / c_f
    //: grafiklerinin üçü ekranda, okuma şartı ekranda değildi.
    //: HESAP YOK: her sayı yükten geldiği gibi basılır, eksik alan em
    //: tire olur; panel çarpıklık için KENDİ eşiğini koymaz (ucun
    //: yayımlanmış bir kabul eşiği yoktur), yalnız ucun _basis cümlesini
    //: yanına yazar.
    function gridQualityHtml(v) {
        const gq = v.gridQuality;
        if (!gq || typeof gq !== 'object') return '';
        const satirlar = [
            [T('panel.cfd.rowWallSkewMax',
               'Max wall skew angle [deg] (at z [m])'),
             fmtAuto(gq.max_wall_skew_deg, 3) + ' ('
                + sig(gq.max_wall_skew_z_m) + ')'],
            [T('panel.cfd.rowWallSkewMean', 'Mean wall skew angle [deg]'),
             fmtAuto(gq.mean_wall_skew_deg, 3)],
            [T('panel.cfd.rowAspectAtSkew',
               'Aspect ratio at the most skewed wall cell'),
             fmtAuto(gq.aspect_ratio_at_max_skew, 3)],
            [T('panel.cfd.rowAspectMax',
               'Max wall aspect ratio (wall face length / first cell thickness)'),
             fmtAuto(gq.max_aspect_ratio, 3)],
            [T('panel.cfd.rowAspectAngle',
               'AR x wall angle change (the dynamic instability metric)'),
             fmtAuto(gq.max_aspect_x_angle_change, 5) + ' ('
                + sig(gq.max_aspect_x_angle_change_z_m) + ' m)'],
            [T('panel.cfd.rowThroatAspect', 'Throat aspect ratio'),
             fmtAuto(gq.throat_aspect_ratio, 4)],
            [T('panel.cfd.rowCellVolumeRatio',
               'Max radial neighbour cell volume ratio'),
             fmtAuto(gq.max_cell_volume_ratio_j, 3)],
            [T('panel.cfd.rowFirstCell',
               'First cell thickness min / max [m]'),
             sig(gq.first_cell_thickness_m_min) + ' / '
                + sig(gq.first_cell_thickness_m_max)],
        ];
        let html = sectionTitle('panel.cfd.secGridQuality',
            'Wall grid quality — the endpoint calls this the reading '
            + 'condition of the q_w claim');
        html += kvTable(satirlar);
        html += basisText(gq._basis);
        return html;
    }

    /* ÖH D26 · P11B3-24 — GÖRÜNÜM MODELİ ÜÇ BLOĞU KURUYOR, HİÇBİRİNİ
       BASMIYORDU (ölü katman; a1'in `gridQuality` bulgusuyla aynı sınıf).

       ÖLÇÜLDÜ (a3/once.json, taban 7751531): kaynakta (yorumsuz)
         sectionAverage 1 · transport 2 · boundaryFlux 1
       yani üç ad da YALNIZ tanım satırında geçiyordu; sunucu üçünü de
       yayımlıyor (steady.py `section_average`, gas_transport
       `declaration()`, app.py `boundary_viscous_flux`).

       Neden önemli:
        * `transport` — viskoz koşumun TAŞINIM KÜNYESİ: viskozite yasası
          ve üsteli, μ_ref/T_ref, c_p, Pr ve Pr_t hangi kaynaktan geldi.
          q_w ve c_f grafiklerinin üçü ekranda, hangi taşınım sabitleriyle
          çözüldükleri ekranda değildi.
        * `boundary_viscous_flux` — giriş/çıkış yüzeylerinden GEÇEN viskoz
          enerji ve eksenel kuvvet: itki ve duvar ısısı defterinin kapanıp
          kapanmadığı bu dört sayıyla okunur.
        * `section_average` — kolon ortalaması Mach ve basınç profili.

       HESAP YOK: her sayı yükten geldiği gibi basılır, eksik alan em tire
       olur. Alan adları MAKİNE ADIYLA yazılır (yeni çeviri anahtarı
       açmadan hangi sayının hangisi olduğu okunur). */
    function transportHtml(v) {
        const tr = v.transport;
        if (!tr || typeof tr !== 'object' || !Object.keys(tr).length) return '';
        const satirlar = [];
        Object.keys(tr).forEach(function (ad) {
            const deger = tr[ad];
            if (deger === null || deger === undefined) {
                satirlar.push([ad, '—']);
            } else if (typeof deger === 'object') {
                // Alt sözlükler (sources, citation, band) AYNEN, ad = değer.
                satirlar.push([ad, esc(JSON.stringify(deger))]);
            } else if (typeof deger === 'number') {
                satirlar.push([ad, sigRaw(deger)]);
            } else {
                satirlar.push([ad, esc(String(deger))]);
            }
        });
        let html = sectionTitle('panel.cfd.secTransport',
            'Transport declaration of this viscous run — which constants '
            + 'the wall heat and skin friction were solved with');
        html += kvTable(satirlar);
        return html;
    }

    function boundaryFluxHtml(v) {
        const bf = v.boundaryFlux;
        if (!bf || typeof bf !== 'object' || !Object.keys(bf).length) return '';
        const satirlar = [
            ['inlet_energy_W', sigRaw(bf.inlet_energy_W)],
            ['outlet_energy_W', sigRaw(bf.outlet_energy_W)],
            ['inlet_axial_force_N', sigRaw(bf.inlet_axial_force_N)],
            ['outlet_axial_force_N', sigRaw(bf.outlet_axial_force_N)],
        ];
        let html = sectionTitle('panel.cfd.secBoundaryFlux',
            'Viscous flux through the inlet and outlet faces — the closing '
            + 'terms of the momentum and energy ledger');
        html += kvTable(satirlar);
        return html;
    }

    function viscousCostHtml(v) {
        const wc = v.worstCase;
        if (!wc || typeof wc !== 'object') return '';
        const satirlar = [];
        Object.keys(wc).forEach(function (kip) {
            const arka = wc[kip] || {};
            Object.keys(arka).forEach(function (b) {
                satirlar.push([kip + ' / ' + b, fmt(arka[b], 1) + ' s']);
            });
        });
        // GERÇEKLEŞEN maliyet en kötü hâlin YANINDA (ikisi ayrı şeydir).
        (v.measuredRuns || []).forEach(function (r) {
            satirlar.push([
                TF('panel.cfd.rowMeasuredRun',
                   { res: String(r.resolution), turb: String(r.turbulence) },
                   'converged run — {res} / {turb}'),
                fmt(r.wall_s, 1) + ' s, ' + String(r.iterations) + ' '
                    + T('panel.cfd.iterationsWord', 'iterations')
                    + ', y+ ' + fmt(r.y_plus_max, 1)]);
        });
        if (!satirlar.length) return '';
        return sectionTitle('panel.cfd.secViscousCost',
            'Measured worst-case runtime of the viscous mode at this '
            + 'resolution') + kvTable(satirlar)
            + note(T('panel.cfd.viscousCostNote',
                'This is the MEASURED wall clock of a run that never '
                + 'converges (it goes to the solver iteration ceiling), by '
                + 'turbulence model and kernel backend. A converging run is '
                + 'much shorter; no filling bar is drawn for either, because '
                + 'the solver reports no intermediate state to draw one '
                + 'from.'), 'dim');
    }

    function viscousHtml(vm, qwId, hgId, tauId) {
        const v = vm.viscous;
        if (!v) return '';
        let html = sectionTitle('panel.cfd.secViscous',
            'Viscous wall outputs (opt-in viscous run)');
        if (!v.enabled) {
            html += notModelledChip(T('panel.cfd.inviscidChip',
                'this run is inviscid (Euler): there is no wall shear, no '
                + 'wall heat flux and no boundary layer to draw'));
            html += viscousCostHtml(v);
            html += basisText(v.basis);
            return html;
        }
        html += kvTable([
            [T('panel.cfd.rowTurbulence', 'Turbulence model'),
             String(v.turbulence)],
            [T('panel.cfd.rowWallThermal', 'Wall thermal condition (source)'),
             String(v.wallThermal) + ' ('
                + String(v.wallTempSource == null ? '—' : v.wallTempSource)
                + ')'],
            [T('panel.cfd.rowYPlus', 'y+ max / mean / min'),
             fmtAuto(v.yPlus.achieved_max, 3) + ' / '
                + fmtAuto(v.yPlus.achieved_mean, 3) + ' / '
                + fmtAuto(v.yPlus.achieved_min, 3)],
            [T('panel.cfd.rowYPlusTarget', 'y+ target / fraction within it'),
             (isNum(v.yPlus.target) ? sig(v.yPlus.target)
                : T('panel.cfd.noTarget', 'not requested'))
                + ' / ' + fmtAuto(v.yPlus.fraction_within_target, 3)],
            [T('panel.cfd.rowWallHeat', 'Integrated wall heat [W]'),
             sig(v.wallHeatW)],
        ]);
        if (v.badge) html += basisText(v.badge.basis);
        // DOĞRULAMA ÇİZGİSİ: q_w/h_g gösterilen her ekranda AYNEN basılır.
        html += basisText(v.validationBasis);

        // 1) q_w(z)
        if (v.wall.qw) {
            html += plotBox(qwId, 280);
        } else {
            html += notModelledChip(T('panel.cfd.noQw',
                'the response carries no wall heat flux array'));
        }
        // 2) h_g — İKİ KAYNAK
        if ((v.thermal.available && v.thermal.hg)
                || (v.bartz.available && v.bartz.hg)) {
            html += plotBox(hgId, 320);
            const satirlar = [];
            if (v.thermal.available) {
                satirlar.push([T('panel.cfd.rowHgSource',
                    'CFD film coefficient — source tag'),
                    String(v.thermal.source) + ', T_aw basis '
                        + String(v.thermal.tAwBasis) + ', edge '
                        + String(v.thermal.edgeSource) + ', '
                        + String(v.thermal.recoveryRegime)]);
            }
            if (v.bartz.available) {
                satirlar.push([T('panel.cfd.rowBartzSource',
                    'Bartz side — measured c* / (R_c/D_t)'),
                    sig(v.bartz.cStar) + ' m/s / ' + fmt(v.bartz.rcOverDt, 3)]);
            }
            if (isNum(v.bartz.ratioMin)) {
                satirlar.push([T('panel.cfd.rowHgRatio',
                    'h_g(CFD)/h_g(Bartz) — min / mean / max / at throat'),
                    fmtAuto(v.bartz.ratioMin, 3) + ' / '
                        + fmtAuto(v.bartz.ratioMean, 3) + ' / '
                        + fmtAuto(v.bartz.ratioMax, 3) + ' / '
                        + fmtAuto(v.bartz.ratioThroat, 3)]);
                // ÖH D25 · P11B3-08 — TERSİ DE EKRANDA.
                // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): aynı ekranda hem
                // ucun künyesi "the model UNDER-predicts q_w at the throat
                // by a factor of 2-3" diyordu, hem de bu satır boğazda
                // 0,0125 basıyordu — yani ÖLÇÜLEN eksiklik 1/0,0125 = 80
                // KAT. "0,013" küçük bir sayı gibi okunuyor; kaç KAT
                // düşük olduğu hiçbir yerde yazmıyordu. Soğutma
                // boyutlandıran biri 80 kat düşük bir film katsayısı
                // okurdu. Burada YENİ FİZİK YOK ve YENİ EŞİK YOK: aynı
                // yayımlanan oranın ARİTMETİK TERSİ basılır (1/x), böylece
                // ucun kendi künyesindeki "2-3 kat" ifadesiyle bu koşumun
                // ölçüsü AYNI EKRANDA, AYNI BİRİMDE karşılaştırılabilir.
                // Sıfır/negatif oranda ters alınmaz (em tire).
                const ters = function (x) {
                    return (isNum(x) && x > 0) ? fmtAuto(1 / x, 3) : '—';
                };
                satirlar.push([T('panel.cfd.rowHgRatioInverse',
                    'h_g(Bartz)/h_g(CFD) — the same ratio inverted: how many '
                    + 'times LOWER the CFD film coefficient is '
                    + '(min / mean / max / at throat)'),
                    ters(v.bartz.ratioMax) + ' / ' + ters(v.bartz.ratioMean)
                        + ' / ' + ters(v.bartz.ratioMin) + ' / '
                        + ters(v.bartz.ratioThroat)]);
            }
            if (satirlar.length) html += kvTable(satirlar);
            // Boğazdaki oran 1'in ALTINDAYSA kaç kat düşük olduğu ayrıca
            // cümleyle söylenir ve okuyucu ucun kendi künyesine (hemen
            // altta basılan ratioBasis) yönlendirilir. Panel bir KABUL
            // BANDI uydurmaz — bandı yalnız ucun künyesi beyan eder.
            if (isNum(v.bartz.ratioThroat) && v.bartz.ratioThroat > 0
                    && v.bartz.ratioThroat < 1) {
                html += note(TF('panel.cfd.hgRatioInverseNote',
                    { k: fmtAuto(1 / v.bartz.ratioThroat, 3) },
                    'At the throat the CFD film coefficient is {k}x LOWER '
                    + 'than the Bartz correlation. Read this against the '
                    + 'y+ badge and the endpoint\'s own ratio basis printed '
                    + 'below, which names the deficit band it measured '
                    + 'against experiment; the panel adds no acceptance '
                    + 'band of its own.'), 'warn');
            }
            if (!v.thermal.available && v.thermal.reason) {
                html += notModelledChip(v.thermal.reason);
            }
            html += basisText(v.bartz.ratioBasis);
            html += basisText(v.bartz.basis);
            html += basisText(v.bartz.cStarBasis);
            html += altNotModelledHtml('viscous.thermal_profile',
                                       v.thermal.notModelled);
        } else {
            html += notModelledChip(v.thermal.reason || v.bartz.reason
                || T('panel.cfd.noHg',
                     'no gas-side film coefficient in this response'));
            //: P11B3-22 — profil çizilemese de köprünün kendi beyanı
            //: (varsa) basılır: reddin gerekçesi listeyi geçersiz kılmaz.
            html += altNotModelledHtml('viscous.thermal_profile',
                                       v.thermal.notModelled);
        }
        // 3) tau_w + c_f
        if (v.wall.tau) {
            html += plotBox(tauId, 300);
            if (!v.skin.available && v.skin.reason) {
                html += notModelledChip(v.skin.reason);
            } else if (v.skin.available) {
                html += basisText(v.skin.basis);
            }
        }
        // 4) SÜRTÜNME KAYBI — ÜÇ KAYNAK YAN YANA (biri diğerinin yerine
        //    geçmez; her satır kaynağını ADIYLA taşır).
        if (v.friction.available) {
            html += sectionTitle('panel.cfd.secFriction',
                'Friction thrust loss — three sources side by side');
            const bant = v.friction.band;
            html += kvTable([
                [String(v.friction.source),
                 TF('panel.cfd.frictionMeasured',
                    { n: sig(v.friction.forceN),
                      f: fmtAuto(v.friction.fraction, 4) },
                    '{n} N measured from tau_w, loss fraction {f}')],
                ['legacy_constant',
                 TF('panel.cfd.frictionLegacy', { f: sig(v.friction.legacy) },
                    '{f} — the quasi-1D chain ledger constant (unchanged)')],
                ['sutton_band',
                 (bant ? fmt(bant[0], 3) + ' – ' + fmt(bant[1], 3) : '—')
                    + ' — ' + (v.friction.withinBand
                        ? T('panel.cfd.bandInside', 'this run falls INSIDE')
                        : T('panel.cfd.bandOutside',
                            'this run falls OUTSIDE (see the note)'))],
                [T('panel.cfd.rowNormalShare',
                   'Normal stress share of the axial force'),
                 fmtAuto(v.friction.normalShare, 4)],
            ]);
            html += basisText(v.friction.bandBasis);
            html += basisText(v.friction.policyBasis);
            html += altNotModelledHtml('viscous.friction',
                                       v.friction.notModelled);
        } else if (v.friction.reason) {
            html += notModelledChip(v.friction.reason);
        }
        // 5) IZGARA KALİTESİ — ucun "q_w'nun okunma şartı" dediği blok.
        html += gridQualityHtml(v);
        // 5b) P11B3-24 — taşınım künyesi ve sınır viskoz akıları.
        html += transportHtml(v);
        html += boundaryFluxHtml(v);
        // 6) ÖLÇÜLEN SÜRE CÜZDANI — sahte ilerleme yok, ölçülen sayı var.
        html += viscousCostHtml(v);
        html += basisText(v.wall.basis);
        html += basisText(v.basis);
        return html;
    }

    function declarationsHtml(vm) {
        let html = sectionTitle('panel.cfd.secDecl',
            'Declarations — not modelled, assumptions, inputs, grid');
        html += '<div data-cfd-block="not-modelled">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declNotModelled">'
            + esc(T('panel.cfd.declNotModelled', 'NOT MODELLED')) + '</strong>'
            + listBlock(vm.notModelled) + '</div>';
        html += '<div data-cfd-block="assumptions" style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declAssumptions">'
            + esc(T('panel.cfd.declAssumptions', 'ASSUMPTIONS')) + '</strong>'
            + listBlock(vm.assumptions) + '</div>';

        const inp = vm.inputs || {};
        const satirlar = [];
        /* ÖH D26 / P11B3-18 — "INPUTS ECHOED BY THE ENDPOINT" BAŞLIĞI
           YANKININ TAMAMINI GÖSTERMİYORDU.
           ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): bu liste SABİT 16
           anahtardı (`sabit_liste_uzunlugu` = 16), ucun yankıladığı girdi
           sayısı ise 30. Yani `wall_bc`, `time_integrator`,
           `initial_state` gibi ŞEMA SEÇİMLERİ sessizce düşüyordu —
           üstelik başlığın kendisi "ucun yankıladığı girdiler" diyordu.
           Kullanıcı bu tabloya bakıp "koşum bu girdilerle yapıldı"
           sonucunu çıkarıyordu; oysa tablo, koşumu belirleyen bir kısım
           alanı hiç göstermiyordu.

           ARTIK: tablo ucun yankıladığı HER anahtarı gösterir. Bilinen
           16 alan ÖNCE ve bu sırayla basılır (okuma düzeni korunur),
           kalanlar ardından alfabetik gelir. Liste bir SÜZGEÇ değil,
           yalnız SIRALAMA'dır: yeni bir alan eklenince tabloya kendi
           kendine girer, sessizce düşmez. */
        const EKO_SIRASI = ['P0_Pa', 'T0_K', 'gamma', 'R_J_kgK',
            'P_ambient_Pa', 'Pb_Pa', 'separation_factor', 'resolution',
            'grid_ni', 'grid_nj', 'contour_field', 'contour_points',
            'cfl_start', 'cfl_max', 'tol_res', 'settle_tol'];
        const kalan = Object.keys(inp).filter(function (k) {
            return EKO_SIRASI.indexOf(k) === -1;
        }).sort();
        EKO_SIRASI.concat(kalan).forEach(function (k) {
            if (!(k in inp)) return;
            const v = inp[k];
            satirlar.push([k, v === null
                ? T('panel.cfd.notSupplied', 'not supplied')
                : (isNum(v) ? sigRaw(v)
                    : (typeof v === 'object' ? JSON.stringify(v) : String(v)))]);
        });
        html += '<div data-cfd-block="inputs" style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declInputs">'
            + esc(T('panel.cfd.declInputs',
                    'INPUTS ECHOED BY THE ENDPOINT')) + '</strong>'
            + kvTable(satirlar) + '</div>';
        if (inp.back_pressure_basis) html += basisText(inp.back_pressure_basis);

        // Öneri kaynakları: hangi sayı motorun neresinden geldi.
        if (lastSuggestion && Object.keys(lastSuggestion.sources).length) {
            const kaynak = lastSuggestion.sources;
            html += '<div data-cfd-block="suggestions" style="margin-top:8px;">'
                + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim,'
                + ' #7d97a5);" data-i18n="panel.cfd.declSuggest">'
                + esc(T('panel.cfd.declSuggest',
                        'WHERE THE PRE-FILLED VALUES CAME FROM')) + '</strong>'
                + kvTable(Object.keys(kaynak).map(function (f) {
                    const s = kaynak[f];
                    return [fieldLabel(f),
                            s.path + (s.unit ? ' (' + s.unit + ')' : '')];
                }))
                + note(T('panel.cfd.declSuggestNote',
                    'These are the suggestion sources measured at the last '
                    + 'refresh. The values actually used are the ones echoed '
                    + 'above — the request is always built from the fields on '
                    + 'screen, so an edited field wins over its suggestion.'),
                    'dim')
                + '</div>';
        }

        const g = vm.grid || {};
        const seviye = g.levels || {};
        const seviyeSatir = Object.keys(seviye).map(function (ad) {
            const s = seviye[ad] || {};
            const w = s.worst_case_s || {};
            // ÖH D36 / sahne-hud a2: satır TR ekranda İngilizce ("cells;
            // worst case") ve süre NOKTALI basılıyordu (ölçüldü: a2/once.json
            // M3/M4). Kalıp sözlükten (panel.cfd.levelRow), süre `sig`ten;
            // sayı değişmez.
            return [ad + (ad === g.resolution ? ' *' : ''),
                    TF('panel.cfd.levelRow',
                       { ni: txt(s.ni), nj: txt(s.nj), n: txt(s.n_cells),
                         cases: Object.keys(w).map(function (b) {
                             return b + ' ' + sig(w[b]) + ' s';
                         }).join(', ') },
                       '{ni}x{nj} = {n} cells; worst case {cases}')];
        });
        html += sectionTitle('panel.cfd.secGrid',
            'Grid and the resolution whitelist (measured worst-case runtimes)');
        html += kvTable([
            [T('panel.cfd.rowResolution', 'Resolution used'),
             txt(g.resolution)],
            [T('panel.cfd.rowCells', 'Cells (axial x radial)'),
             txt(g.ni) + ' x ' + txt(g.nj) + ' = ' + txt(g.n_cells)],
            [T('panel.cfd.rowThroat', 'Throat: z, radius, section-average Mach'),
             sig(vm.throat.z_m) + ' m, ' + sig(vm.throat.radius_m) + ' m, '
                + fmtAuto(vm.throat.mach_section_avg, 4)],
            // --- ÖH D31 · P11B3-27 — BOĞAZ ALANI PANELDE ---------------
            // ÖLÇÜLDÜ (a1/once.json · M8: `throat_area_m2 = 0`): uç
            // `throat.area_m2` yayımlıyor (nozzle_flow_1d.py:1537) ve c*
            // ölçümü ONU kullanıyor (app.py:23659 `A_t`), ama panel yalnız
            // yarıçapı basıyordu. Kullanıcı c* = P0·A_t/mdot bağıntısını
            // ekrandaki sayılarla DOĞRULAYAMIYORDU: yarıçaptan alanı
            // kendisi türetmek zorundaydı ve o türetme (dairesel kesit
            // varsayımı) ucun kullandığı alanla aynı olmak ZORUNDA değil.
            // Alan gelmezse satır HİÇ basılmaz (alan uydurulmaz).
            // ÖH D32 / OH-D31-01: sözlüğe bağlandı
            // (`panel.cfd.rowThroatArea`, EN+TR).
            [T('panel.cfd.rowThroatArea', 'Throat area A_t (used for c*)'),
             (typeof vm.throat.area_m2 === 'number'
              && isFinite(vm.throat.area_m2))
                 ? (sig(vm.throat.area_m2) + ' m2') : '—'],
        ].concat(seviyeSatir));
        html += basisText(g._basis);
        return html;
    }

    function convergenceHtml(vm, plotId) {
        let html = sectionTitle('panel.cfd.secConv',
            'Convergence history and the conservation budget');
        html += plotBox(plotId, 260);
        html += kvTable([
            [T('panel.cfd.rowIterations', 'Iterations / budget (source)'),
             txt(vm.iterations) + ' / ' + txt(vm.maxIterations) + ' ('
                + txt(vm.maxIterationsSource) + ')'],
            [T('panel.cfd.rowResLast', 'Last residual (exact)'),
             fmtExp(vm.residual.last, 4)],
            [T('panel.cfd.rowResMin', 'Smallest residual (exact)'),
             fmtExp(vm.residual.min, 4)],
            [T('panel.cfd.rowMassIn', 'Mass flow in / out [kg/s]'),
             sig(vm.budget.mass_flow_in_kg_s) + ' / '
                + sig(vm.budget.mass_flow_out_kg_s)],
            [T('panel.cfd.rowWallFlux', 'Wall mass flux [kg/s] (slip wall: 0)'),
             fmtExp(vm.budget.wall_mass_flux_kg_s, 3)],
            // ÖH D28 / arayuz a1 (OH-D27-16) — ZAMAN İLERLETME YOLUNUN ADI.
            // Yokluk em-tire ile basılır (txt), varsayılan bir şema adı
            // UYDURULMAZ.
            [T('panel.cfd.rowTimeIntegrator', 'Time integrator'),
             txt(vm.timeIntegrator)],
        ]);
        if (vm.residual.decimated) {
            html += note(TF('panel.cfd.residualDecimated',
                { n: vm.residual.nReturned, total: vm.residual.nTotal },
                'The residual history is drawn thinned: {n} of {total} points. '
                + 'The two numbers thinning could hide (last and smallest '
                + 'residual) are printed above exactly, from the response.'),
                'dim');
        }
        html += basisText(vm.convergenceBasis);
        html += basisText(vm.maxIterationsBasis);
        // ÖH D28 / arayuz a1 (OH-D27-16): şemanın KÜNYESİ, adının hemen
        // ardından. Metin ucun kendi beyanıdır, SRV ile aynen basılır.
        html += basisText(vm.timeIntegratorBasis);
        html += convergenceHistoryHtml(vm);
        html += selfConsistencyHtml(vm);
        return html;
    }

    // ------------------------------------------------------------------
    // HÜKMÜN DAYANDIĞI SERİLER (ÖH D28 / arayuz a1 — OH-D27-16)
    //
    // NEDEN VAR: uç `settle_bands` ile "debi bandı OTURDU / OTURMADI,
    // boğaz Mach bandı OTURDU / OTURMADI" diye hüküm veriyor; D26 /
    // app-api a4 (`e5882484`, P7B4-10) o hükmün DAYANDIĞI üç seriyi
    // (mass_flow_in / mass_flow_out / throat_mach) `convergence_history`
    // bloğuyla uca taşıdı — tam da istemci bandı KENDİ denetleyebilsin
    // diye. Panel bloğu hiç okumuyordu: kullanıcı hükmü görüyor, hükmün
    // ölçüldüğü eğriyi göremiyordu.
    //
    // Bu bölüm seriyi YENİDEN HESAPLAMAZ: seyreltmenin gizleyebileceği
    // son değeri (`last`) ve seyreltme sayaçlarını ucun yayımladığı gibi
    // basar, birimini ucun `unit` alanından alır, künyesini (`_basis`)
    // AYNEN gösterir. Blok yoksa hiçbir satır çıkmaz (fail-closed).
    // ------------------------------------------------------------------
    function convergenceHistoryHtml(vm) {
        const ch = vm.convHistory;
        if (!ch || typeof ch !== 'object') return '';
        const seriler = [
            ['mass_flow_in', T('panel.cfd.serMassIn', 'Inlet mass flow')],
            ['mass_flow_out', T('panel.cfd.serMassOut', 'Outlet mass flow')],
            ['throat_mach', T('panel.cfd.serThroatMach', 'Throat Mach')],
        ];
        const rows = [];
        const kunyeler = [];
        seriler.forEach(function (p) {
            const s = ch[p[0]];
            if (!s || typeof s !== 'object') return;
            const birim = s.unit ? ' ' + String(s.unit) : '';
            rows.push([p[1] + ' — ' + p[0],
                fmtAuto(s.last, 4) + birim + '  ('
                + txt(s.n_returned) + '/' + txt(s.n_entries) + ' '
                + T('panel.cfd.serPoints', 'points')
                + (s.decimated ? ', ' + T('panel.cfd.serThinned', 'thinned')
                               : '') + ')']);
            if (s._basis) kunyeler.push(s._basis);
        });
        if (!rows.length) return '';
        let html = sectionTitle('panel.cfd.secConvHistory',
            'Series the settle-band verdict is measured on '
            + '(last value, exact)');
        html += kvTable(rows);
        kunyeler.forEach(function (b) { html += basisText(b); });
        return html;
    }

    // ------------------------------------------------------------------
    // ÖZ-TUTARLILIK VE PLATO (ÖH defter D15-CFD-01, OH-Z5-14, OH-Z5-19)
    //
    // NEDEN VAR: uç `residual_operator`, `scheme_residual_norm`,
    // `scheme_residual_exceeds_tol`, `scheme_residual_blocks_verdict`,
    // `picard_selfconsistency_rejections`, `slope_state`, `settle_bands`
    // ve (OH-Z5-14 ile) `convergence_status` + `convergence_plateau`
    // yayımlıyordu; panel HİÇBİRİNİ basmıyordu. Kullanıcı "CONVERGED"
    // ya da "NOT CONVERGED" rozetinin ARKASINDAKİ sayıyı — yayımlanan
    // kalıntının şemanın kendi kalıntısı mı yoksa DONMUŞ eğim
    // sisteminin kalıntısı mı olduğunu — göremiyordu. Bu bölüm o
    // alanları OLDUĞU GİBİ basar: hesap yok, yuvarlama saklaması yok,
    // eksik alan em-tire.
    // ------------------------------------------------------------------
    function selfConsistencyHtml(vm) {
        const sc = vm.selfConsistency || {};
        const sl = sc.slope || {};
        const sb = vm.settleBands || {};
        const faz = sb.refresh_phase_locked || {};
        const pl = vm.plateau || {};
        let html = sectionTitle('panel.cfd.secSelfConsistency',
            'Self-consistency of the published residual (Picard gate)');
        const rows = [
            [T('panel.cfd.rowConvStatus', 'Convergence status'),
             String(vm.convergenceStatus == null ? '—'
                                                 : vm.convergenceStatus)],
            [T('panel.cfd.rowResidualOperator',
               'The published residual belongs to'),
             String(sc.operator == null ? '—' : sc.operator)],
            [T('panel.cfd.rowSchemeResidual',
               'Scheme (live minmod) residual / tolerance'),
             fmtExp(sc.schemeResidual, 4) + ' / ' + fmtExp(sl.tol_res, 2)],
            [T('panel.cfd.rowSchemeExceeds', 'Scheme residual above tolerance'),
             yesNo(sc.exceedsTol)],
            [T('panel.cfd.rowGate', 'Self-consistency gate / rejections'),
             String(sl.selfconsistency_gate == null
                    ? T('panel.cfd.gateOff', 'not active')
                    : sl.selfconsistency_gate)
                + ' / ' + String(sc.rejections == null ? '—' : sc.rejections)],
            [T('panel.cfd.rowBlocksVerdict',
               'Verdict withheld by the gate'),
             yesNo(sc.blocksVerdict)],
            [T('panel.cfd.rowWalkOperator',
               'Walk operator is the scheme itself'),
             yesNo(sl.walk_operator_is_scheme)],
            [T('panel.cfd.rowSlopeFreeze',
               'Slopes frozen at iteration / refresh period'),
             String(sl.frozen_at_iter == null ? '—' : sl.frozen_at_iter)
                + ' / ' + String(sl.refresh_period == null
                                 ? '—' : sl.refresh_period)],
            [T('panel.cfd.rowSchemeBudget',
               'Scheme mass / energy balance (relative)'),
             fmtExp(sl.scheme_mass_balance_rel, 3) + ' / '
                + fmtExp(sl.scheme_energy_balance_rel, 3)],
            [T('panel.cfd.rowSettleBands',
               'Settle bands in / out / throat Mach (window, tol)'),
             fmtExp(sb.mass_flow_in, 3) + ' / ' + fmtExp(sb.mass_flow_out, 3)
                + ' / ' + fmtExp(sb.throat_mach, 3)
                + ' (' + String(sb.window == null ? '—' : sb.window) + ', '
                + fmtExp(sb.tol, 2) + ')'],
            [T('panel.cfd.rowPhaseBands',
               'Phase-locked bands in / out / throat Mach (period)'),
             (faz.active
                ? (fmtExp(faz.mass_flow_in, 3) + ' / '
                   + fmtExp(faz.mass_flow_out, 3) + ' / '
                   + fmtExp(faz.throat_mach, 3) + ' ('
                   + String(faz.period == null ? '—' : faz.period) + ')')
                : T('panel.cfd.phaseInactive',
                    'no refresh cycle on this path - not measured'))],
        ];
        html += kvTable(rows);
        html += plateauHtml(pl);
        html += basisText(sl._basis);
        html += basisText(faz._basis);
        return html;
    }

    //: PLATO BLOĞU — çözücünün plato hükmü ve onun DAYANDIĞI örnekler.
    //: Plato "hüküm" değildir: hükümsüzlüğün CİNSİDİR ("bütçeyi
    //: büyütmek geçmez"). Tespit edilmediyse çözücünün kendi gerekçesi
    //: (neden yetmedi) basılır — sessizce boş bırakılmaz.
    function plateauHtml(pl) {
        if (!pl || typeof pl !== 'object') return '';
        let html = sectionTitle('panel.cfd.secPlateau',
            'Residual plateau (is a bigger iteration budget of any use?)');
        html += kvTable([
            [T('panel.cfd.rowPlateauDetected', 'Plateau detected'),
             yesNo(pl.detected)],
            [T('panel.cfd.rowPlateauResidual',
               'Plateau residual / target'),
             fmtExp(pl.plateau_residual, 4) + ' / '
                + fmtExp(pl.target_residual, 2)],
            [T('panel.cfd.rowPlateauWindow',
               'Window [iterations] / relative spread / threshold'),
             String(pl.window_iterations == null ? '—' : pl.window_iterations)
                + ' / ' + fmtExp(pl.relative_spread, 3)
                + ' / ' + fmtExp(pl.rel_tol, 2)],
            [T('panel.cfd.rowPlateauSamples',
               'Samples (iteration = scheme residual)'),
             plateauSamplesText(pl.samples)],
        ]);
        if (pl.reason) html += basisText(pl.reason);
        return html;
    }

    //: Örnek dizisi metne: uydurma nokta EKLENMEZ, dizi neyse o basılır.
    function plateauSamplesText(samples) {
        if (!Array.isArray(samples) || !samples.length) return '—';
        return samples.map(function (s) {
            return String(s[0]) + ' = ' + fmtExp(s[1], 4);
        }).join(', ');
    }

    //: Üç durumlu evet/hayır: alan yoksa em-tire (false ile karıştırılmaz).
    function yesNo(v) {
        if (v === true) return T('panel.cfd.yes', 'yes');
        if (v === false) return T('panel.cfd.no', 'no');
        return '—';
    }

    // ------------------------------------------------------------------
    // Alan büyüklüğü seçici + yokluk beyanları
    // ------------------------------------------------------------------

    //: Üç büyüklük de HER ZAMAN listelenir. Yükte olmayan büyüklük
    //: `disabled` (gri) gelir ve nedeni ADIYLA altta yazılır — seçenek
    //: sessizce GİZLENMEZ ve o büyüklük Mach'tan/basınçtan TÜRETİLMEZ.
    function metricSelectHtml(vm, selId) {
        const aktif = activeMetric(vm);
        const av = vm.field.available;
        const secenekler = FIELD_METRICS.map(function (m) {
            const yok = av.indexOf(m.id) < 0;
            return '<option value="' + esc(m.id) + '"'
                + (m.id === aktif ? ' selected' : '')
                + (yok ? ' disabled' : '')
                + ' data-cfd-metric-option="' + esc(m.id) + '"'
                + ' data-i18n="' + esc(m.labelKey) + '">'
                + esc(T(m.labelKey, m.labelFallback)) + '</option>';
        }).join('');
        return '<label for="' + esc(selId) + '" style="font-size:0.68rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin-right:6px;"'
            + ' data-i18n="panel.cfd.toggleField">'
            + esc(T('panel.cfd.toggleField', 'Field variable')) + '</label>'
            + '<select id="' + esc(selId) + '" data-cfd-metric="1"'
            + ' style="font-size:0.7rem;">' + secenekler + '</select>';
    }

    //: Seçicinin altındaki beyanlar: (a) yükte olmayan her büyüklük ADIYLA
    //: ve yük anahtarıyla, (b) seçili büyüklük yoksa hangisine düşüldüğü,
    //: (c) renk duraklarının kaynağı (paylaşılan tablo) ya da yokluğu.
    function metricNotesHtml(vm) {
        let html = '';
        const av = vm.field.available;
        FIELD_METRICS.forEach(function (m) {
            if (av.indexOf(m.id) >= 0) return;
            html += note(TF('panel.cfd.metricUnavailable',
                { label: T(m.labelKey, m.labelFallback), key: m.payloadKey },
                'This response carries no "{key}" array, so "{label}" is '
                + 'offered greyed out. It is NOT rebuilt from the other '
                + 'quantities: reconstructing it would be a different number '
                + 'than the solver\'s own field.'), 'warn');
        });
        const aktif = activeMetric(vm);
        if (aktif !== fieldMetric) {
            const secili = metricById(fieldMetric);
            html += note(TF('panel.cfd.metricFellBack',
                { wanted: secili ? T(secili.labelKey, secili.labelFallback)
                                 : fieldMetric,
                  shown: T(metricById(aktif).labelKey,
                           metricById(aktif).labelFallback) },
                'The selected quantity "{wanted}" is not in this response, so '
                + '"{shown}" is drawn instead.'), 'warn');
        }
        if (metricColorscale(aktif)) {
            html += note(T('panel.cfd.colorSource',
                'The colour stops are the table published by the 3D scene '
                + '(MotorViz3D.CFD_COLORSCALES), so the same value gets the '
                + 'same colour in this map and in the 3D section.'), 'dim');
        } else {
            html += note(T('panel.cfd.colorSourceMissing',
                'The shared colour table (motor_viz3d.js) is not loaded on '
                + 'this page, so the map is drawn without an explicit colour '
                + 'scale and its colours will NOT match the 3D section. No '
                + 'second copy of the table is kept here.'), 'warn');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // 3B KÖPRÜSÜ — aynı yanıtı 3B sahnenin kesit kamasına bindirir
    // ------------------------------------------------------------------

    //: Sahnenin köprü için hazır olup olmadığı. Hazır değilse eylem
    //: KAPALI gösterilir ve nedeni yazılır (görünmez düğme = sessiz kusur).
    function viz3dReadiness() {
        const V = window.MotorViz3D;
        if (!V || typeof V.setCfdField !== 'function') {
            return { ok: false, key: 'panel.cfd.viz3dNoModule',
                fallback: 'The 3D scene module (motor_viz3d.js) is not loaded '
                    + 'on this page, so the field cannot be sent to it.' };
        }
        if (typeof V.isSupported === 'function' && !V.isSupported()) {
            return { ok: false, key: 'panel.cfd.viz3dNoWebgl',
                fallback: 'This browser reports no WebGL support, so the 3D '
                    + 'scene cannot show the field.' };
        }
        return { ok: true, key: '', fallback: '' };
    }

    //: RED sözlüğünü okunur metne çevirir. METİN SAHNENİN KENDİSİNDEN gelir
    //: (reason.key + reason.fallback) — panelde ikinci bir mesaj tanımı yok.
    //: Kod ayrıca AÇIKÇA basılır; tanınmayan kod ADIYLA beyan edilir.
    function viz3dReasonText(reason) {
        if (!reason || typeof reason !== 'object') {
            return T('panel.cfd.viz3dNoReason',
                'The 3D scene refused the field but returned no reason block.');
        }
        const kod = String(reason.code == null ? '' : reason.code);
        let metin = reason.key
            ? T(reason.key, reason.fallback || kod)
            : String(reason.fallback || kod);
        if (VIZ3D_REASON_CODES.indexOf(kod) < 0) {
            metin = TF('panel.cfd.viz3dUnknownCode', { code: kod || '?' },
                'The 3D scene returned a refusal code this panel does not '
                + 'know ({code}); its own text follows.') + ' ' + metin;
        }
        const p = reason.params;
        const parcalar = [];
        if (p && typeof p === 'object') {
            Object.keys(p).forEach(function (k) {
                parcalar.push(k + '=' + String(p[k]));
            });
        }
        return '[' + (kod || '?') + '] ' + metin
            + (parcalar.length ? ' (' + parcalar.join(', ') + ')' : '');
    }

    //: Başarılı bindirmenin beyanı — NE gösterildiği sahnenin KENDİ dönüş
    //: sözlüğünden okunur (panel hiçbir sayıyı yeniden hesaplamaz).
    //: ÖH D37 A1c panel-dil · dil-sozluk Devir 3 + Devir 5 — yedek metinler
    //: sözlüğün EN metniyle BİREBİR (eski yedek virgüllüydü); birimsiz
    //: büyüklükte (Mach, sahnenin `unitLabel`i '') ayrı anahtar: eski yol
    //: '{max} {unit} — …' şablonunda ham metne ÇİFT BOŞLUK bırakıyordu
    //: (ölçüldü: once/olcum.json K4 '2.91214  — 60x12'; ekranda tarayıcı
    //: tek boşluğa çöker, textContent okuyan tüketici çift görür).
    function viz3dOkLines(res) {
        const m = metricById(res.metric);
        const birim = String(res.unitLabel || '').trim();
        const alanlar = {
            metric: m ? T(m.labelKey, m.labelFallback) : String(res.metric),
            min: sig(res.range && res.range.min),
            max: sig(res.range && res.range.max),
            unit: birim,
            shown: res.stations ? res.stations.shown : '—',
            total: res.stations ? res.stations.total : '—',
            nz: res.cells ? res.cells.axial : '—',
            nr: res.cells ? res.cells.radial : '—' };
        const satirlar = [birim
            ? TF('panel.cfd.viz3dShown', alanlar,
                'The 3D section now carries {metric}: {min} … {max} {unit} — '
                + '{nz}x{nr} solver cells over {shown} of {total} axial stations.')
            : TF('panel.cfd.viz3dShownNoUnit', alanlar,
                'The 3D section now carries {metric}: {min} … {max} — '
                + '{nz}x{nr} solver cells over {shown} of {total} axial stations.')];
        if (res.metric === 'pressure') {
            satirlar.push(T('panel.cfd.viz3dUnitNote',
                'The 3D scene labels pressure in the payload unit (Pa); the '
                + '2D map above divides the same numbers by 1 bar.'));
        }
        if (res.decimated) {
            satirlar.push(T('panel.cfd.viz3dDecimated',
                'The field was thinned by the endpoint before it was sent, and '
                + 'the 3D section shows exactly the cells that arrived.'));
        }
        if (res.cutaway_forced) {
            satirlar.push(T('panel.cfd.viz3dCutaway',
                'Cutaway view was switched on: the field lies inside opaque '
                + 'metal and would not be visible otherwise.'));
        }
        if (Array.isArray(res.decor_hidden) && res.decor_hidden.length) {
            satirlar.push(TF('panel.cfd.viz3dDecorHidden',
                { list: res.decor_hidden.join(', ') },
                'Decorative layers that overlap the field were hidden while it '
                + 'is shown: {list}.'));
        }
        if (res.alignment) {
            satirlar.push(TF('panel.cfd.viz3dAlignment',
                { dzi: sig(res.alignment.dz_inlet_mm),
                  dze: sig(res.alignment.dz_exit_mm),
                  drt: sig(res.alignment.dr_throat_mm),
                  dre: sig(res.alignment.dr_exit_mm) },
                'Measured anchor deviation against the scene contour [mm]: '
                + 'inlet z {dzi}, exit z {dze}, throat r {drt}, exit r {dre}.'));
        }
        return satirlar;
    }

    function viz3dHtml(vm, btnId, clearId, statusId) {
        const hazir = viz3dReadiness();
        let html = sectionTitle('panel.cfd.secViz3d',
            'Show this field in the 3D scene');
        const kapali = hazir.ok ? '' : ' disabled';
        html += '<button type="button" id="' + esc(btnId) + '"'
            + ' data-cfd-viz3d="show"' + kapali
            + ' style="font-size:0.7rem; margin-right:6px;"'
            + ' data-i18n="panel.cfd.viz3dShowBtn">'
            + esc(T('panel.cfd.viz3dShowBtn', 'Show in the 3D scene'))
            + '</button>';
        html += '<button type="button" id="' + esc(clearId) + '"'
            + ' data-cfd-viz3d="clear"' + kapali
            + ' style="font-size:0.7rem;"'
            + ' data-i18n="panel.cfd.viz3dClearBtn">'
            + esc(T('panel.cfd.viz3dClearBtn', 'Remove it from the 3D scene'))
            + '</button>';
        html += '<p data-cfd-viz3d-status="1" id="' + esc(statusId) + '"'
            + ' style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; line-height:1.45; margin:6px 0; color:'
            + (hazir.ok ? COLORS.dim : COLORS.warn) + ';">'
            + esc(hazir.ok
                ? T('panel.cfd.viz3dIdle',
                    'The field is drawn in 2D above. Pressing the button sends '
                    + 'the SAME response to the 3D section; nothing is '
                    + 'recomputed.')
                : T(hazir.key, hazir.fallback))
            + '</p>';
        return html;
    }

    //: Alanı sahneye bindirir; 2B'de seçili büyüklük yükte varsa 3B de
    //: ONU gösterir (iki görünüm aynı büyüklüğe aynı rengi verir). Düğme
    //: yolu ile otomatik yol AYNI işlevden geçer — ikinci bir gönderim
    //: mantığı yazılmaz.
    function sendToViz3d(cfd, vm) {
        const V = window.MotorViz3D;
        let res = V.setCfdField(cfd);
        if (res && res.ok) {
            const istenen = activeMetric(vm);
            if (res.metric !== istenen) {
                const ikinci = V.setCfdMetric(istenen);
                if (ikinci && ikinci.ok) res = ikinci;
            }
        }
        return res;
    }

    //: Sahnenin kabını görünüme kaydırır (ÖH D36 keşfedilebilirlik).
    //: Sahne kabı sahnenin KENDİ beyanından okunur (MotorViz3D.get().
    //: container); kap yoksa ya da tarayıcı kaydırmayı desteklemiyorsa
    //: sessizce geçilir — kaydırma bir yan hizmettir, alanın kendisi değil.
    function revealViz3d() {
        const V = window.MotorViz3D;
        const sahne = (V && typeof V.get === 'function') ? V.get() : null;
        const kap = sahne && sahne.container;
        if (kap && typeof kap.scrollIntoView === 'function') {
            try {
                kap.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) { /* eski tarayıcı: seçeneksiz kaydırma da gereksiz */ }
        }
    }

    //: ÖH D36 / sahne-hud — KOŞUM BİTİNCE ALAN SAHNEYE KENDİLİĞİNDEN.
    //: ÖLÇÜLEN KUSUR (Berke 22 Eyl, "ANSYS gibi"; A3_gorev_ve_mimari.md G3):
    //: yol vardı ama İKİ adımdı — kullanıcı CFD'yi koşturduktan sonra
    //: ayrıca "3B sahnede göster"e basmak zorundaydı ve görsel turların
    //: hiçbiri bu düğmeye ulaşmadı. Yanıt `field` bloğu taşıyorsa alan
    //: artık çizimden hemen sonra sahneye gönderilir, sahne görünüme
    //: kaydırılır ve durum satırı bunun KENDİLİĞİNDEN olduğunu söyler.
    //: Sahte veri yok: alan yoksa bu yol hiç çağrılmaz (drawInto'daki
    //: `vm.field` kapısı), sahne reddederse red adıyla yazılır, hazır
    //: değilse (modül/WebGL yok) düğmeyle aynı gerekçe geçerlidir.
    //: Kapatılabilir: sahne şeridindeki KAPAT ya da buradaki "3B sahneden
    //: kaldır" alanı söker; aynı yanıt yeniden çizilse de, geçmişte başka
    //: kayda gidip dönülse de geri GELMEZ (autoBridgedCfds).
    //: Bekçi: tests/test_d36_sahne_a1.py
    function autoViz3d(cfd, vm, statusId) {
        if (!viz3dReadiness().ok) return false;
        if (cfd === lastAutoBridgedCfd) return false;
        if (autoBridgedCfds && autoBridgedCfds.has(cfd)) return false;
        if (autoBridgedCfds) autoBridgedCfds.add(cfd);
        lastAutoBridgedCfd = cfd;
        const res = sendToViz3d(cfd, vm);
        const durumEl = document.getElementById(statusId);
        if (durumEl) {
            const on = T('panel.cfd.viz3dAuto',
                'The field was sent to the 3D scene automatically when the '
                + 'run finished; the Close button in the scene strip removes '
                + 'it, and "Show in the 3D scene" sends it again.');
            if (res && res.ok) {
                durumEl.textContent = on + ' ' + viz3dOkLines(res).join(' ');
                durumEl.style.color = kindColor('ok');
            } else {
                durumEl.textContent = on + ' '
                    + viz3dReasonText(res && res.reason);
                durumEl.style.color = kindColor('warn');
            }
        }
        if (res && res.ok) revealViz3d();
        return true;
    }

    //: Köprü düğmelerinin kablosu. Sahne dönüşü NE İSE o yazılır; "olmadı"
    //: gibi uydurma bir mesaj üretilmez.
    function bindViz3d(root, cfd, vm, btnId, clearId, statusId) {
        const durumEl = document.getElementById(statusId);
        const yaz = function (metin, kind) {
            if (!durumEl) return;
            durumEl.textContent = metin;
            durumEl.style.color = kindColor(kind);
        };
        const goster = document.getElementById(btnId);
        const temizle = document.getElementById(clearId);
        if (!viz3dReadiness().ok) return;
        if (goster && goster.addEventListener) {
            goster.addEventListener('click', function () {
                const res = sendToViz3d(cfd, vm);
                if (res && res.ok) {
                    yaz(viz3dOkLines(res).join(' '), 'ok');
                    revealViz3d();
                } else {
                    yaz(viz3dReasonText(res && res.reason), 'warn');
                }
            });
        }
        if (temizle && temizle.addEventListener) {
            temizle.addEventListener('click', function () {
                const kalkti = window.MotorViz3D.clearCfdField();
                yaz(kalkti
                    ? T('panel.cfd.viz3dCleared',
                        'The field layer was removed from the 3D scene and the '
                        + 'decorative layers came back.')
                    : T('panel.cfd.viz3dNothingToClear',
                        'The 3D scene carried no field layer, so nothing was '
                        + 'removed.'), 'dim');
            });
        }
    }

    // ------------------------------------------------------------------
    // Çizim — Merkez'in görüntüleyici kabına
    // ------------------------------------------------------------------
    function purge(root) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.purgePlots === 'function') U.purgePlots(root);
    }

    function drawInto(root, cfd) {
        if (!root) return;
        purge(root);
        drawSeq += 1;
        carpetFallback = false;
        const vm = viewModel(cfd);
        const wallId = 'cfd_wall_' + drawSeq;
        const fieldId = 'cfd_field_' + drawSeq;
        const resId = 'cfd_res_' + drawSeq;
        const selId = 'cfd_metric_' + drawSeq;
        const viz3dBtnId = 'cfd_viz3d_show_' + drawSeq;
        const viz3dClearId = 'cfd_viz3d_clear_' + drawSeq;
        const viz3dStatusId = 'cfd_viz3d_status_' + drawSeq;
        const qwId = 'cfd_qw_' + drawSeq;
        const hgId = 'cfd_hg_' + drawSeq;
        const tauId = 'cfd_tau_' + drawSeq;
        const secAvgId = 'cfd_secavg_' + drawSeq;

        let html = '<div data-cfd-badges="1">' + badgesHtml(vm) + '</div>';

        // 1) Duvar basıncı + ayrılma ölçütü
        html += sectionTitle('panel.cfd.secWall',
            'Wall pressure p_w(z) against the separation criterion');
        html += plotBox(wallId, 300);
        // P11B3-24 — kolon ortalaması profili duvar eğrisinin ALTINDA,
        // kendi kabında (ikisi AYNI şey değildir).
        if (sectionAverageVar(vm)) {
            html += sectionTitle('panel.cfd.secSectionAverage',
                'Section averages along the axis — volume-weighted column '
                + 'means published by the endpoint');
            html += plotBox(secAvgId, 280);
            html += basisText(vm.sectionAverage._basis);
        }
        const sep = vm.separation || {};
        const sepRows = [
            [T('panel.cfd.rowThreshold', 'Threshold k*P_ambient [Pa]'),
             sig(sep.threshold_Pa)],
            [T('panel.cfd.rowFactor', 'Summerfield k (source)'),
             fmt(sep.separation_factor, 3) + ' ('
                + String(sep.separation_factor_source == null
                         ? '—' : sep.separation_factor_source) + ')'],
            [T('panel.cfd.rowWallMin', 'Minimum wall pressure [Pa] / margin'),
             sig(sep.wall_pressure_min_Pa) + ' / '
                + fmtAuto(sep.wall_pressure_margin_min, 3)],
        ];
        if (isNum(sep.separation_z_m)) {
            sepRows.push([T('panel.cfd.rowSepStation',
                'First separated station z [m] (cell / interpolated)'),
                sig(sep.separation_z_m) + ' / '
                    + sig(sep.separation_z_interp_m)]);
            sepRows.push([T('panel.cfd.rowSepLength',
                'Separated length [m] / fraction of the divergent section'),
                sig(sep.separated_length_m) + ' / '
                    + fmt(sep.separated_length_fraction, 4)]);
        }
        html += kvTable(sepRows);
        html += basisText(vm.wall.basis);
        html += basisText(sep.criterion_basis);
        html += basisText(sep.judgment_basis);
        if (sep.not_applicable_reason) html += basisText(sep.not_applicable_reason);

        // 2) Alan haritası
        html += sectionTitle('panel.cfd.secField',
            'Flow field on the solver cells');
        if (vm.field) {
            html += metricSelectHtml(vm, selId);
            html += plotBox(fieldId, 320);
            html += metricNotesHtml(vm);
            if (vm.field.decimated) {
                html += note(TF('panel.cfd.fieldDecimated',
                    { n: vm.field.nReturned, total: vm.field.nTotal },
                    'The field block is drawn thinned in the AXIAL direction '
                    + 'only: {n} of {total} cells were returned and the kept '
                    + 'indices come from the response, so no cell is invented '
                    + 'and the wall-adjacent row stays intact.'), 'dim');
            }
            if (!vm.wallLine) {
                html += note(T('panel.cfd.wallLineMissing',
                    'The nozzle wall polyline is not drawn: the contour in hand '
                    + 'is not measurably the one this stored run was solved on '
                    + '(point count or inlet/exit stations differ). The solver '
                    + 'cells above are drawn as returned.'), 'dim');
            }
            html += basisText(vm.field.basis);
            // 2a) Aynı yanıtı 3B sahneye bindirme köprüsü
            html += viz3dHtml(vm, viz3dBtnId, viz3dClearId, viz3dStatusId);
        } else {
            html += note(T('panel.cfd.fieldMissing',
                'This response carries no field block, so no field map is '
                + 'drawn.'), 'warn');
        }

        // 2b) Ayrılma ölçütlerinin dört üyesi (viskoz koşuda CFD üyesi de
        //     gelir; Euler koşusunda o üye kendi 'VİSKOZ DEĞİL' gerekçesiyle
        //     kapalı görünür — panel hiçbirini uydurmaz)
        html += separationCriteriaHtml(vm);
        // 2b') Ayrılma hükmünün KENDİ kapsam beyanı (P11B3-10)
        html += separationNotModelledHtml(vm);
        // 2c) Viskoz duvar çıktıları
        html += viscousHtml(vm, qwId, hgId, tauId);
        // 3) Yakınsama + bütçe
        html += convergenceHtml(vm, resId);
        // 4) Koşu öncesi giriş koşullandırma beyanı
        html += inletHtml(vm);
        // 5) Beyanlar (modellenmeyenler, varsayımlar, girdi yankısı, ızgara)
        html += declarationsHtml(vm);

        root.innerHTML = html;

        // Çizimler — Plotly yoksa grafik kutusu boş kalır ve neden yazılır.
        if (!window.Plotly || typeof window.Plotly.react !== 'function') {
            const uyari = document.createElement('p');
            uyari.setAttribute('data-cfd-noplotly', '1');
            uyari.style.color = COLORS.dim;
            uyari.style.fontSize = '0.7rem';
            uyari.textContent = T('panel.cfd.noPlotly',
                'The plotting library is not loaded on this page, so the charts '
                + 'are not drawn; every number above comes from the same '
                + 'response.');
            root.appendChild(uyari);
        } else {
            if (vm.wall.z.length) drawFigure(wallId, wallFigure(vm));
            if (sectionAverageVar(vm)) {
                drawFigure(secAvgId, sectionAverageFigure(vm));
            }
            if (vm.field) {
                try {
                    drawFigure(fieldId, fieldFigure(vm));
                } catch (e) {
                    // Carpet izi bu derlemede yok: nokta haritasına düşülür
                    // ve rozet şeridi bu BEYANLA tazelenir (sessiz düşüş yok).
                    carpetFallback = true;
                    drawFigure(fieldId, fieldFallbackFigure(vm));
                    const kap = root.querySelector
                        ? root.querySelector('[data-cfd-badges]') : null;
                    if (kap) kap.innerHTML = badgesHtml(vm);
                }
            }
            if (vm.residual.iteration.length) {
                drawFigure(resId, residualFigure(vm));
            }
            // Viskoz çizimler: veri YOKSA kutu da yok, çizim de yok.
            const vv = vm.viscous;
            if (vv && vv.enabled) {
                if (vv.wall.qw) drawFigure(qwId, wallHeatFigure(vm));
                if ((vv.thermal.available && vv.thermal.hg)
                        || (vv.bartz.available && vv.bartz.hg)) {
                    drawFigure(hgId, filmFigure(vm));
                }
                if (vv.wall.tau) drawFigure(tauId, shearFigure(vm));
            }
        }

        // Alan büyüklüğü değiştiricisi: aynı yanıt yeniden çizilir
        // (yeni istek YOK, yeni sayı YOK).
        const sel = document.getElementById(selId);
        if (sel && sel.addEventListener) {
            sel.addEventListener('change', function () {
                fieldMetric = normalizeMetric(sel.value);
                drawInto(root, cfd);
            });
        }
        if (vm.field) {
            bindViz3d(root, cfd, vm, viz3dBtnId, viz3dClearId, viz3dStatusId);
            // ÖH D36: yanıt alan taşıyorsa sahneye KENDİLİĞİNDEN (tıklamasız).
            autoViz3d(cfd, vm, viz3dStatusId);
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);

        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        //
        // NOT: bu modülde `U` MODÜL DÜZEYİNDE YOKTUR — iki ayrı
        // fonksiyonun içinde yerel olarak alınır (satır 233, 2368).
        // Pano burada da yerelden alınır; doğrudan `U` yazmak
        // `drawInto`yu "U is not defined" ile düşürür ve panel
        // bütünüyle hata metnine iner (ölçüldü: test_cfd_panel.py
        // 11 test kırmızı).
        const UD = window.AnalysisDock && window.AnalysisDock.ui;
        if (UD && UD.source && UD.source.ledgerInto) {
            UD.source.ledgerInto(root, cfd, { deep: true });
        }
    }

    function render(data, root) {
        if (!root) return;
        const cfd = data && data.cfd;
        if (!cfd || typeof cfd !== 'object') {
            root.innerHTML = '<p data-cfd-nodata="1" style="font-size:0.72rem;'
                + ' color:var(--hd-red, #ff5d73);">'
                + esc(T('panel.cfd.noBlock',
                    'The response carries no "cfd" block, so nothing is drawn. '
                    + 'Nothing is inferred in its place.')) + '</p>';
            return;
        }
        drawInto(root, cfd);
    }

    // ==================================================================
    // KİRACI KAYDI — analysis_center.js başındaki sözleşme
    // ==================================================================
    const SPEC = {
        componentId: 'nozzle_flow',
        analysisId: 'cfd',
        // Başlık ve anahtar §2 matrisinin satırıyla AYNI (ayrışmasın diye).
        title: 'CFD (Euler, shock capturing, p_w separation call)',
        titleKey: 'ac.an.cfd',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'solid', 'liquid'],
        long: true,

        applicability: applicability,

        // ALANLAR — hiçbirinin SONLU varsayılanı yok: öneri gelmeyen alan
        // boş kalır ve body() isteği durdurur (uydurma sayı gösterilmez).
        fields: [
            ['P0_Pa', 'Chamber stagnation pressure P0 [Pa]', '', 'any',
             'panel.cfd.fieldP0', 'panel.cfd.help.P0'],
            ['T0_K', 'Chamber stagnation temperature T0 [K]', '', 'any',
             'panel.cfd.fieldT0', 'panel.cfd.help.T0'],
            ['gamma', 'Ratio of specific heats gamma [-]', '', 'any',
             'panel.cfd.fieldGamma', 'panel.cfd.help.gamma'],
            ['R_J_per_kgK', 'Specific gas constant R [J/(kg K)]', '', 'any',
             'panel.cfd.fieldR', 'panel.cfd.help.R'],
            ['P_ambient_Pa', 'Ambient pressure [Pa]', '', 'any',
             'panel.cfd.fieldPamb', 'panel.cfd.help.Pamb'],
            ['Pb_Pa', 'Back pressure Pb [Pa] — optional', '', 'any',
             'panel.cfd.fieldPb', 'panel.cfd.help.Pb'],
            ['separation_factor', 'Summerfield k [-] — optional', '', 'any',
             'panel.cfd.fieldK', 'panel.cfd.help.k'],
            ['resolution', 'Grid resolution', 'coarse',
             [['coarse', 'Coarse', 'panel.cfd.resCoarse'],
              ['standard', 'Standard', 'panel.cfd.resStandard']],
             'panel.cfd.fieldResolution', 'panel.cfd.help.resolution'],
            // VİSKOZ KİP — varsayılan KAPALI (Euler). Isıl duvar koşulu
            // seçimin KENDİSİDİR: uçta varsayılanı yoktur çünkü izotermal
            // ve adyabatik duvar FARKLI çözümlerdir. Tek bir seçici
            // kullanılıyor ki "açık ama duvar koşulu seçilmemiş" gibi
            // geçersiz bir birleşim ekrandan üretilemesin.
            ['viscous_mode', 'Wall model', '',
             [['', 'Inviscid (Euler) — default', 'panel.cfd.wallInviscid'],
              ['isothermal', 'Viscous — isothermal wall',
               'panel.cfd.wallIsothermal'],
              ['adiabatic', 'Viscous — adiabatic wall',
               'panel.cfd.wallAdiabatic']],
             'panel.cfd.fieldViscousMode', 'panel.cfd.help.viscousMode'],
            ['viscous_turbulence', 'Turbulence model', 'none',
             [['none', 'None (laminar)', 'panel.cfd.turbNone'],
              ['sa_neg', 'Spalart-Allmaras (negative variant)',
               'panel.cfd.turbSaNeg']],
             'panel.cfd.fieldTurbulence', 'panel.cfd.help.turbulence'],
            // SONLU VARSAYILAN YOK: duvar sıcaklığı uydurulamaz. Boş
            // bırakılırsa ve izotermal duvar seçilmişse body() isteği
            // GÖNDERMEZ ve eksiği adıyla yazar.
            ['viscous_T_wall_K',
             'Wall temperature T_w [K] — isothermal wall only', '', 'any',
             'panel.cfd.fieldTwall', 'panel.cfd.help.Twall'],
        ],

        fromResults: function (results) {
            const sug = suggest(results);
            lastSuggestion = sug;
            return sug.values;
        },

        body: buildBody,
        render: render,
        verdict: verdictOf,
    };

    if (window.AnalysisCenter && typeof window.AnalysisCenter.register === 'function') {
        window.AnalysisCenter.register(SPEC);
    } else if (window.console && console.warn) {
        console.warn('[CfdPanel] window.AnalysisCenter yok: kiracı kaydolamadı. '
            + 'Yükleme sırası analysis_center.js -> panels/cfd_panel.js olmalı.');
    }

    // Test / hata ayıklama yüzeyi — saf model katmanı DOM'suz koşulabilir.
    window.CfdPanel = {
        spec: SPEC,
        endpoint: ENDPOINT,
        _suggest: suggest,
        _pickContour: pickContour,
        _applicability: applicability,
        _buildBody: buildBody,
        _verdict: verdictOf,
        _viewModel: viewModel,
        _render: render,
        _setFieldMetric: function (m) {
            fieldMetric = normalizeMetric(m);
        },
        _getFieldMetric: function () { return fieldMetric; },
        _metrics: FIELD_METRICS,
        _reasonCodes: VIZ3D_REASON_CODES,
        _colorscale: metricColorscale,
        _viz3dReasonText: viz3dReasonText,
        _viz3dReadiness: viz3dReadiness,
        // ÖH D36 bekçisi: otomatik köprünün son gönderdiği yanıtı okur
        _lastAutoBridgedCfd: function () { return lastAutoBridgedCfd; },
        _sources: SUGGESTION_SOURCES,
        _viscousModel: viscousModel,
        _viscousBadges: viscousBadgesHtml,
        // ÖH D19 · P11B3-07 bekçisi rozet kabını buradan okur
        // (DOM'suz saf katman; _viscousBadges ile aynı desen).
        _badgesHtml: badgesHtml,
        _yPlusBadgeKinds: Y_PLUS_BADGE_KIND,
        PA_PER_BAR: PA_PER_BAR,
        R_UNIVERSAL: R_UNIVERSAL,
        T_WALL_SOURCE_FORM: T_WALL_SOURCE_FORM,
        TURBULENCE_DEFAULT: TURBULENCE_DEFAULT,
    };
})();
