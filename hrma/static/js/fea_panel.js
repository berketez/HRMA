/* ====================================================================
   HRMA Yapısal FEA Paneli (D5 — v2.7 analiz modülünün kullanıcı yüzü)
   --------------------------------------------------------------------
   hrma/fea/ çözücüleri (mesh_axisym + structural_axisym + bridge) depoda
   çalışır hâldeydi ama 2026-08-04 denetimine kadar HİÇBİR kullanıcı yüzü
   yoktu: ne gerilme alanı, ne mesh, ne de yakınsama geçmişi görünüyordu.
   Bu panel POST /api/fea/structural yanıtını çizer.

   Berke'nin açık isteği (4 Ağustos 2026): "mesh AYARI görmesem de MESH'İ
   görmek isterim — iyi mesh atıyor mu göreyim". Panel bu yüzden mesh
   AYARI sunmaz (yakınsama sürücüsü kendi kararını verir) ama mesh'in
   KENDİSİNİ gösterir: tel-kafes katmanı, eleman kalite haritası ve
   yakınsama eğrisi.

   Ne çizilir (hepsi sunucu yanıtından, hesap YOK):
     (a) von Mises ve emniyet katsayısı KONTUR haritası — eksenel simetrik
         (z, r) kesiti üstünde, Plotly carpet + contourcarpet ile (yapısal
         eğrisel ızgara Plotly'nin contour/heatmap izlerinde 1B eksen
         ister; carpet tam olarak bu iş için vardır).
     (b) MESH tel-kafesi — yapısal ızgaranın i ve j çizgileri; eleman
         kenarlarının BİREBİR kendisidir (yaklaşım değil).
     (c) ELEMAN KALİTE haritası — en-boy oranı / ölçekli Jacobian; eşiği
         aşan eleman KIRMIZI. Eşikler sunucudan gelir (tek tanım yeri:
         app.py FEA_QUALITY_*; kaynak künyesi yanıtın quality._basis
         alanında, Verdict/CUBIT dörtgen ölçüt tablosu).
     (d) YAKINSAMA grafiği — maks von Mises (MPa) vs eleman sayısı;
         noktalar köprünün yakınsama geçmişinden gelir, beyan metni
         sunucunun kendi cümlesidir.

   SAHTE VERİ YASAĞI:
     * Sunucu NOT_MODELLED derse hiçbir alan çizilmez; eksik girdi listesi
       ve sunucunun gerekçesi basılır.
     * Emniyet katsayısı alanı null gelirse (malzeme kaydında akma yoksa)
       SF grafiği hiç kurulmaz — yerine "yayımlanmadı" çipi konur.
     * Motor sonucu değişince ESKİ FEA çıktısı SİLİNİR (bayat gerilme
       alanı yeni motorunmuş gibi gösterilmez).
     * İlerleme çubuğu YOKTUR: koşu süresi önceden bilinmez, belirsiz
       süreli iş için belirsiz gösterge (nabız) kullanılır.

   Birim: çözücü Pa döner; panel yalnızca 1e6'ya böler (MPa) ve bunu
   eksen başlığında + künye satırında beyan eder. Başka ölçekleme,
   yeniden örnekleme veya yumuşatma YOKTUR.

   Kullanım (advanced.html):
     <script src="/static/js/fea_panel.js"></script>
     FeaPanel.init({ anchorId: 'trajectoryPanel' });

   Bekçi testleri: tests/test_fea_panel.py (node ile izole koşum) +
   tests/test_fea_endpoint.py (uç sözleşmesi).
   ==================================================================== */

(function () {
    'use strict';

    const ENDPOINT = '/api/fea/structural';
    const PA_PER_MPA = 1e6;          // birim dönüşümünün TEK yeri
    // ÖH D19 · P11B3-06 — kamara basıncı ekrana BAR yazılır (kullanıcının
    // girdiği birim). Kardeş panellerin deseni: her IIFE kendi birim
    // sabitini dosyanın TEK yerinde tanımlar (transient_panel.js:49,
    // panels/cfd_panel.js, motor_viz_deck.js) — ÖH D25 / OH-D24-05 ile
    // paylaşılan JS sabit modülüne taşındı.
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

    /* ÖH D23 / P17B4-07 + P17B1-18 — İSTEK ZAMAN AŞIMI (TEK KAYNAK).

       ÖLÇÜLDÜ (a2 once.json): `abort_panel_js = 0` — bu dosyanın iki
       `fetch` çağrısının hiçbiri `signal` taşımıyordu; `busy` bayrağı
       ikinci tıklamayı engelliyor, istek SÜRESİZ bekliyordu. Canlı turda
       (P17B1-18, sıvı sayfası) panel 180 s sonra hâlâ "çalışıyor" diyor,
       `rozet_sayisi = 0`, gerekçe çipi BOŞ, dört çizim kabı 0x0 — ve
       turun `akis_tamam` denetimi aynı koşuda YEŞİL kalıyordu, çünkü o
       denetim Python istisnası sayar, panel durumunu değil. Kullanıcı
       için "takılı koşum" ile "yavaş koşum" ayırt edilemezdi; tek çıkış
       sayfayı yenilemekti.

       Hakem düzeltmesi (H2, P17B4-07 kısmen çürütüldü): kanal YOK değil,
       kanal VAR — ürünün kendi deseni üç şablonda çalışıyor
       (`AbortSignal.timeout(180000)`, gerekçeli yorumla, 2026-07-20 saha
       hatası). Kusur eksik yetenek değil, UYGULANMAMIŞ DESEN. Desen
       buraya kopyalanır.

       TEK KAYNAK (doktrin 4): süre üç şablonda ayrı ayrı yazılıydı;
       sayı artık YALNIZ burada durur ve `window` üzerinden yayımlanır —
       şablonlar onu okur. fea_panel.js altı ürün şablonunun üçünde de
       (advanced/solid/liquid) yüklüdür, yani tüketiciler için hazırdır. */
    const ISTEK_ZAMAN_ASIMI_MS = 180000;
    window.HRMA_ISTEK_ZAMAN_ASIMI_MS = ISTEK_ZAMAN_ASIMI_MS;

    /* Zaman aşımı sinyali. Tarayıcı AbortSignal.timeout desteklemiyorsa
       undefined döner — istek eskisi gibi süresiz bekler, ama bu durumda
       da meşgul satırı geçen süreyi yazar (aşağıdaki nabız). */
    function zamanAsimiSinyali() {
        return (typeof AbortSignal !== 'undefined' && AbortSignal.timeout)
            ? AbortSignal.timeout(ISTEK_ZAMAN_ASIMI_MS) : undefined;
    }

    /* İstek zaman aşımıyla mı düştü? AbortSignal.timeout 'TimeoutError',
       elle iptal 'AbortError' üretir. */
    function zamanAsimiMi(e) {
        const ad = e && e.name;
        return ad === 'TimeoutError' || ad === 'AbortError';
    }

    /* ÖH D26 · P11B3-19 — KULLANICI KOŞUMU DURDURABİLİR.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531):
         fea_abort_controller = 0 · fea_iptal_dugmesi = 0
         term_abort_controller = 0 · term_iptal_dugmesi = 0
       Yani P17B4-07'nin getirdiği ZAMAN AŞIMI vardı ama İPTAL yoktu:
       viskoz koşum ölçülen 72,3 s sürüyor, ucun kendi cüzdanı 382,4 s'e
       kadar çıkıyor ve kullanıcının tek çıkışı sayfayı yenilemekti —
       yenileme motor sonucunu da siler. Yanlış girdiyle başlatılan bir
       koşum, sınır dolana kadar makineyi meşgul ediyordu.

       Kanal aynı kanaldır (AbortSignal); eklenen KAPIDIR. İki durdurucu
       AYRI AYRI beyan edilir: 'zaman aşımı' ile 'kullanıcı durdurdu'
       aynı cümleyle anlatılmaz (fail-closed dürüstlük — panel ne olduğunu
       uydurmaz, hangisi olduğunu bilir ve onu söyler). */
    const denetleyiciler = Object.create(null);   // koşum adı -> AbortController
    const iptalDamgasi = Object.create(null);     // koşum adı -> kullanıcı mı durdurdu

    function kosumSinyali(ad) {
        iptalDamgasi[ad] = false;
        if (typeof AbortController !== 'function') return zamanAsimiSinyali();
        const c = new AbortController();
        denetleyiciler[ad] = c;
        const zs = zamanAsimiSinyali();
        if (zs && typeof AbortSignal !== 'undefined'
                && typeof AbortSignal.any === 'function') {
            return AbortSignal.any([c.signal, zs]);
        }
        // AbortSignal.any yoksa süre sınırı elle kurulur — SAYI YİNE TEK
        // KAYNAKTAN (ISTEK_ZAMAN_ASIMI_MS), ikinci kez yazılmaz.
        if (typeof setTimeout === 'function') {
            const t = setTimeout(function () {
                if (denetleyiciler[ad] === c) c.abort();
            }, ISTEK_ZAMAN_ASIMI_MS);
            if (typeof c.signal.addEventListener === 'function') {
                c.signal.addEventListener('abort', function () {
                    if (typeof clearTimeout === 'function') clearTimeout(t);
                });
            }
        }
        return c.signal;
    }

    function kosumuIptalEt(ad) {
        const c = denetleyiciler[ad];
        if (!c) return false;
        iptalDamgasi[ad] = true;
        delete denetleyiciler[ad];
        try { c.abort(); } catch (e) { return false; }
        return true;
    }

    function kosumBitti(ad) {
        delete denetleyiciler[ad];
    }

    function kullaniciIptaliMi(ad) {
        return iptalDamgasi[ad] === true;
    }

    /* İptal düğmesi — meşgulken görünür, boştayken gizli. Düğme koşumun
       KENDİ satırında durur (meşgul satırının yanında), çünkü orada
       aranır. */
    function iptalDugmesiHtml(id, metin) {
        return '<button id="' + id + '" class="btn" type="button"'
            + ' style="display:none; padding:2px 10px; font-size:0.75rem;"'
            + '>' + esc(metin) + '</button>';
    }

    function iptalDugmesiniGoster(el, isBusy) {
        if (el && el.style) el.style.display = isBusy ? '' : 'none';
    }

    /* MEŞGUL SATIRI — GEREKÇELİ, SÜRELİ, SONLU (P17B1-18).
       Yüzde YOK (sahte ilerleme yasak, doktrin 6): çözücü kaç tur
       yapacağını önceden bilmiyor. Yazılan iki sayı da GERÇEK: geçen
       süre ölçülür, süre sınırı yukarıdaki sabittir. Nabız, panel meşgul
       olduğu sürece saniyede bir aynı satırı tazeler. */
    const NABIZ_MS = 1000;
    const nabizlar = Object.create(null);

    function nabziDurdur(ad) {
        if (nabizlar[ad]) {
            clearInterval(nabizlar[ad].timer);
            delete nabizlar[ad];
        }
    }

    /* els.busy metnini yazar ve meşgulken nabzı kurar.
         ad      : nabız kimliği ('structural' | 'grain')
         el      : meşgul satırı düğümü
         isBusy  : koşum sürüyor mu
         basla   : koşumun başlangıç damgası (ms) ya da null
         govde   : çevrilmiş gerekçe cümlesi (çözücü ne yapıyor)
         sureFn  : (gecen, sinir) -> çevrilmiş süre cümlesi */
    /* Öznitelik yazımı savunmacıdır: paneller Merkez kiracısı olarak ve
       node bekçilerinde EKSİK DOM saplamalarıyla da çizilir (tam DOM
       varsayan çağrı orada çöker; ölçüldü — test_fea_panel node koşumu). */
    function ozY(el, ad, deger) {
        if (el && typeof el.setAttribute === 'function') el.setAttribute(ad, deger);
    }

    function ozS(el, ad) {
        if (el && typeof el.removeAttribute === 'function') el.removeAttribute(ad);
    }

    function mesgulYaz(ad, el, isBusy, basla, govde, sureFn) {
        if (!el) return;
        el.style.display = isBusy ? '' : 'none';
        if (!isBusy) {
            el.textContent = '';
            ozS(el, 'data-indeterminate');
            ozS(el, 'data-elapsed-s');
            nabziDurdur(ad);
            return;
        }
        ozY(el, 'data-indeterminate', 'true');
        function boya() {
            const gecen = basla ? Math.max(0, Math.round((Date.now() - basla) / 1000)) : 0;
            ozY(el, 'data-elapsed-s', String(gecen));
            el.textContent = govde + ' ' + sureFn(gecen,
                Math.round(ISTEK_ZAMAN_ASIMI_MS / 1000));
        }
        boya();
        nabziDurdur(ad);
        // Nabız YALNIZ gerçek, bağlı bir DOM düğümünde kurulur: saplama
        // kapta zamanlayıcı süreci ayakta tutar ve hiçbir şey tazelemez.
        if (el.isConnected !== true || typeof setInterval !== 'function') return;
        nabizlar[ad] = { timer: setInterval(function () {
            if (!el.isConnected || el.style.display === 'none') {
                nabziDurdur(ad);
                return;
            }
            boya();
        }, NABIZ_MS) };
    }

    let cfg = {};
    let lastMotorResults = null;     // paneli besleyecek motor sonucu
    let lastPayload = null;          // son FEA yanıtı (fea bloğu)
    let lastError = null;            // ağ/sunucu hatası metni
    let busy = false;
    let busySince = null;      // koşumun başlangıç damgası (P17B1-18)
    let showMesh = true;             // tel-kafes katmanı açık/kapalı
    let qualityMetric = 'aspect_ratio';
    let carpetFallback = false;      // carpet çizilemedi → nokta haritası

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
    // Sunucu üretimi serbest metin (beyan/gerekçe alanları) — i18n_charts.js
    // sözlüğünden geçer, eşleşme yoksa AYNEN kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ==================================================================
    // >>> FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek uç yanıtlarıyla koşturur. Alan değerleri sunucudan geldiği
    // gibi taşınır; tek dönüşüm Pa → MPa bölmesidir ve beyan edilir.
    // ==================================================================

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    // node_index_grid: [i][j] — i eksenel istasyon, j cidar katmanı
    // (0 iç yüzey). Carpet izleri 2B diziyi [b][a] sırasıyla ister, yani
    // satır = katman (j), sütun = istasyon (i).
    function gridDims(mesh) {
        const g = mesh && mesh.node_index_grid;
        if (!Array.isArray(g) || !g.length || !Array.isArray(g[0])) return null;
        return { ni: g.length, nj: g[0].length };
    }

    // Düğüm koordinatlarından carpet ızgarası: x[j][i], y[j][i] (metre).
    function buildCarpetGrid(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        if (!Array.isArray(nodes)) return null;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        for (let j = 0; j < dims.nj; j++) {
            const rx = [], ry = [];
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                if (!Array.isArray(n)) return null;
                rx.push(n[0]);
                ry.push(n[1]);
            }
            x.push(rx);
            y.push(ry);
        }
        const a = [], b = [];
        for (let i = 0; i < dims.ni; i++) a.push(i);
        for (let j = 0; j < dims.nj; j++) b.push(j);
        return { a: a, b: b, x: x, y: y, ni: dims.ni, nj: dims.nj };
    }

    // Düğüm alanı (N,) → carpet düzeni [j][i]. scale verilirse bölünür
    // (Pa → MPa); başka dönüşüm yapılmaz. Alan eksikse null döner.
    function fieldToGrid(mesh, values, scale) {
        const dims = gridDims(mesh);
        if (!dims || !Array.isArray(values)) return null;
        const g = mesh.node_index_grid;
        const div = (typeof scale === 'number' && scale !== 0) ? scale : 1;
        const out = [];
        for (let j = 0; j < dims.nj; j++) {
            const row = [];
            for (let i = 0; i < dims.ni; i++) {
                const v = values[g[i][j]];
                row.push(isNum(v) ? v / div : null);
            }
            out.push(row);
        }
        return out;
    }

    // Tel-kafes: yapısal ızgaranın bütün i ve j çizgileri. Eleman
    // kenarlarının kendisidir; tek iz olarak null ayraçlarla taşınır.
    function buildWireframe(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        let pts = 0;
        for (let i = 0; i < dims.ni; i++) {
            for (let j = 0; j < dims.nj; j++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        for (let j = 0; j < dims.nj; j++) {
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        // Her düğüm bir kez i-çizgisinde, bir kez j-çizgisinde geçer.
        return { x: x, y: y, node_visits: pts, n_nodes: dims.ni * dims.nj };
    }

    // Eleman merkezleri — dört düğümün ortalaması (sıra varsayımı YOK,
    // bağlantı dizisi neyse o kullanılır).
    function elementCentres(mesh) {
        const elems = mesh && mesh.elems;
        const nodes = mesh && mesh.nodes;
        if (!Array.isArray(elems) || !Array.isArray(nodes)) return null;
        const x = new Array(elems.length), y = new Array(elems.length);
        for (let e = 0; e < elems.length; e++) {
            const c = elems[e];
            let sx = 0, sy = 0;
            for (let k = 0; k < c.length; k++) {
                const n = nodes[c[k]];
                sx += n[0]; sy += n[1];
            }
            x[e] = sx / c.length;
            y[e] = sy / c.length;
        }
        return { x: x, y: y };
    }

    // Kalite bayrakları — eşikler SUNUCUDAN gelir (panelde eşik sabiti
    // yoktur). Sonlu olmayan/eksik ölçüt de bayraklanır: ölçülemeyen
    // eleman "iyi" sayılmaz.
    //
    // İKİ ÖLÇÜT AYRI TUTULUR (2026-08-15): en-boy oranı ile ölçekli
    // Jacobian aynı çuvala konursa (eski `any` rozeti) ince cidarda
    // "1024/1024 eleman kabul aralığı dışında" gibi bir alarm çıkıyor —
    // oysa ölçüm şuydu: aspect 27-38 (hepsi bayraklı) ama scaled Jacobian
    // 0,96-1,0 (SIFIR bayrak), yani gerçek bozulma yok. Sunucunun kendi
    // quality._basis cümlesi de bunu söyler: uzun kontur boyunca süpürülen
    // ince cidar uzamış eleman üretir, gerçek bozulmayı ölçekli Jacobian
    // raporlar. `any` alanı KORUNUR (harita katmanı onu kullanır), ama
    // rozet hükmü artık yalnız Jacobian sayımından sürülür.
    function qualityFlags(quality) {
        if (!quality || typeof quality !== 'object') return null;
        const th = quality.thresholds || {};
        const ar = Array.isArray(quality.aspect_ratio) ? quality.aspect_ratio : null;
        const sj = Array.isArray(quality.scaled_jacobian) ? quality.scaled_jacobian : null;
        if (!ar && !sj) return null;
        const n = (ar || sj).length;
        const arMax = isNum(th.aspect_ratio_max) ? th.aspect_ratio_max : null;
        const sjMin = isNum(th.scaled_jacobian_min) ? th.scaled_jacobian_min : null;
        // ÖLÇÜLDÜ MÜ: ölçüt dizisi VE eşiği yayımlanmışsa değerlendirme
        // gerçekten yapılmıştır. Ölçülmemiş ölçütün bayrak sayısı sıfırdır
        // ama bu "temiz" DEMEK DEĞİLDİR — rozet onu yeşil hüküm gibi
        // basmasın diye ölçülebilirlik ayrıca taşınır.
        const arOlculdu = !!ar && arMax !== null;
        const sjOlculdu = !!sj && sjMin !== null;
        const aspect = new Array(n), jac = new Array(n), any = new Array(n);
        for (let e = 0; e < n; e++) {
            const av = ar ? ar[e] : null;
            const sv = sj ? sj[e] : null;
            aspect[e] = !arOlculdu ? false : (!isNum(av) || av > arMax);
            jac[e] = !sjOlculdu ? false : (!isNum(sv) || sv < sjMin);
            any[e] = aspect[e] || jac[e];
        }
        // ÖH D25 · P11B3-05 — EN KÖTÜ ELEMANIN SAYISI EKRANA ÇIKAR.
        // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): uç `quality.worst` bloğunu
        // SAYIYLA yayımlıyor (en kötü en-boy oranı 368,7248 ve en kötü
        // ölçekli Jacobian 0,69646) ve eşikleri de veriyor (sırasıyla
        // 4,0 ve 0,5) — yani en kötü eleman eşiğin 92,2 KATI uzamış.
        // (Künye bilerek 'ad: sayı' biçiminde YAZILMAZ: test_fea_panel.py
        //  ::TestKalite::test_esikler_panelde_sabit_degil kaynakta eşik
        //  adına sayı atanmasını arar ve o bekçi yerinde kalmalıdır.)
        // Panel `worst` alanını hiç okumuyordu: kaynakta ad yalnız bir
        // İngilizce cümlenin içinde geçiyordu. Ekranda tek ifade
        // "384/384 eşik dışı — beklenen, bozulma alarmı değil" idi ve bu
        // cümle 4,1 ile 368,7 arasındaki HER durumda AYNI görünüyordu:
        // kullanıcı sapmanın BÜYÜKLÜĞÜNÜ göremiyordu. Sayı burada yükten
        // olduğu gibi taşınır; eşiğe oran (worst/threshold) saf bölmedir,
        // yeni eşik ya da yeni hüküm DEĞİLDİR.
        const w = (quality.worst && typeof quality.worst === 'object')
            ? quality.worst : null;
        const wAr = (w && isNum(w.aspect_ratio_max)) ? w.aspect_ratio_max : null;
        const wSj = (w && isNum(w.scaled_jacobian_min))
            ? w.scaled_jacobian_min : null;
        const worst = (wAr === null && wSj === null) ? null : {
            aspect_ratio_max: wAr,
            scaled_jacobian_min: wSj,
            //: Eşiğin kaç katı — bölme, çarpma yok; eşik yayımlanmadıysa
            //: oran da YOKTUR (uydurulmaz).
            aspect_over_threshold: (wAr !== null && arMax !== null && arMax !== 0)
                ? wAr / arMax : null,
            jacobian_over_threshold: (wSj !== null && sjMin !== null && sjMin !== 0)
                ? wSj / sjMin : null,
        };
        return {
            aspect: aspect, jacobian: jac, any: any,
            worst: worst,
            measured: { aspect: arOlculdu, jacobian: sjOlculdu },
            thresholds: { aspect_ratio_max: arMax, scaled_jacobian_min: sjMin },
            counts: {
                aspect: aspect.filter(Boolean).length,
                jacobian: jac.filter(Boolean).length,
                any: any.filter(Boolean).length,
                total: n,
            },
        };
    }

    // Yakınsama geçmişi → grafik serileri (eleman sayısı vs maks von Mises).
    function buildConvergence(conv) {
        if (!conv || typeof conv !== 'object') return null;
        const hist = Array.isArray(conv.history) ? conv.history : [];
        const nElems = [], vmMPa = [], relPct = [];
        //: ÖH D29 · P11B3-13 — İNCELTMENİN YÖNÜ DE OKUNUR.
        //: ÖLÇÜLDÜ (a3/once.json): geçmişin her turu `n_axial`, `n_radial`
        //: ve bir `karar` bloğu taşıyor; panel bunların HİÇBİRİNİ almıyordu
        //: (`karar_okunuyor: 0`). Ölçülen koşuda eksenel bölüm dört meshte
        //: de 12'de sabit kalmış (0 katlama), artışın tamamı radyaldi; x
        //: ekseni "Elements in mesh" 48 -> 384 giderek TEKDÜZE inceltme
        //: izlenimi veriyordu. Sayılar yükten gelir, panel katlama SAYMAZ
        //: dışında bir şey hesaplamaz.
        const nAxial = [], nRadial = [], yonAdi = [];
        hist.forEach(function (h) {
            if (!h || typeof h !== 'object') return;
            if (!isNum(h.n_elems) || !isNum(h.max_von_mises)) return;
            nElems.push(h.n_elems);
            vmMPa.push(h.max_von_mises / PA_PER_MPA);
            relPct.push(isNum(h.rel_change) ? 100 * h.rel_change : null);
            nAxial.push(isNum(h.n_axial) ? h.n_axial : null);
            nRadial.push(isNum(h.n_radial) ? h.n_radial : null);
            yonAdi.push(typeof h.yon === 'string' ? h.yon : null);
        });
        //: Katlama = ardışık iki mesh arasında o yönde ARTIŞ olması.
        function katlamaSay(dizi) {
            let n = 0;
            for (let i = 1; i < dizi.length; i++) {
                if (isNum(dizi[i]) && isNum(dizi[i - 1]) && dizi[i] > dizi[i - 1]) {
                    n += 1;
                }
            }
            return n;
        }
        const yonBilinir = nAxial.some(isNum) && nRadial.some(isNum);
        const yon_katlama = yonBilinir
            ? { eksenel: katlamaSay(nAxial), radyal: katlamaSay(nRadial) }
            : null;
        //: Son turun karar bloğu (yön göstergeleri + iki sonda çözümü).
        const sonKarar = (function () {
            for (let i = hist.length - 1; i >= 0; i--) {
                const k = hist[i] && hist[i].karar;
                if (k && typeof k === 'object') return k;
            }
            return null;
        })();
        // KABUL ÖLÇÜTÜ BLOĞU — sunucu sözleşmesinde İSTEĞE BAĞLI alan.
        // Yakınsama sürücüsü tepe von Mises'tir, ama panelin HÜKMÜ o
        // olmayabilir: katı tanede kabul ölçütü port lif gerinimidir
        // (NASA SP-8073). Sunucu bunu yayımlarsa hüküm oradan verilir, vM
        // ayrı ve nötr bilgi olarak kalır. Blok YOKSA alan null'dır ve
        // panel bugünkü davranışını birebir sürdürür (geriye uyum).
        // Birim: rel_change ve tol, bloğun kendisiyle AYNI sözleşmede
        // (oransal değişim) gelir; panel yalnız 100 ile çarpar.
        let acc = null;
        const a = conv.acceptance;
        if (a && typeof a === 'object') {
            acc = {
                quantity: (typeof a.quantity === 'string' && a.quantity)
                    ? a.quantity : null,
                converged: a.converged === true,
                rel_change_pct: isNum(a.rel_change) ? 100 * a.rel_change : null,
                tol_pct: isNum(a.tol) ? 100 * a.tol : null,
            };
        }
        // ÖH D25 · P11B3-03 — İKİ SAYI AYNI CÜMLEDE ÇELİŞİYORDU.
        // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): ekrandaki tek not satırı
        // aynı anda "Converged in 4 refinement rounds" ve sunucunun
        // beyanından "0 eksenel + 3 radyal katlama (yön-ayrışık)" diyor;
        // rozet "CONVERGED in 4 rounds", Merkez satırı "MESH CONVERGED in
        // 4 rounds". Kullanıcı 4 ile 3'ün hangisinin doğru olduğunu
        // ayırt edemiyordu.
        //
        // KÖK: sayı YANLIŞ DEĞİL, ADI BELİRSİZ. Ucun kendi beyan
        // üreticisi de MESH SAYISINI 'tur' diye yazıyor
        // (hrma/fea/structural_axisym.py:1203 -> f"YAKINSAMADI:
        // {len(history)} turda ({yon_ozeti}) ..."), katlama sayacı ise
        // İNCELTME ADIMLARINI sayıyor; ilk mesh bir katlama DEĞİLDİR,
        // dolayısıyla katlama = mesh - 1. Yani iki sayı iki AYRI
        // büyüklüktür ve ikisi de doğrudur.
        //
        // KAPI: panelin sayısını kaydırmak çelişkiyi ÇÖZMEZ, yalnız yön
        // değiştirir (rozet 3 derken ucun hemen altta AYNEN basılan
        // beyanı '4 turda' derdi — yeni bir çelişki). Bu yüzden `rounds`
        // ucun sözleşmesiyle AYNI kalır (mesh sayısı) ve İKİNCİ büyüklük
        // kendi adıyla ayrıca taşınır: `refinements` = mesh - 1. Not
        // satırı üçünü birden yazar (bkz. fea.convMeshCount), böylece
        // ekrandaki 4 ile 3'ün ne olduğu ADIYLA okunur.
        const meshSayisi = nElems.length;
        return {
            n_elems: nElems,
            von_mises_mpa: vmMPa,
            rel_change_pct: relPct,
            meshes: meshSayisi,
            //: Ucun 'tur' dediği sayı (çözülen mesh sayısı) — sözleşme.
            rounds: meshSayisi,
            //: İnceltme ADIMI sayısı (katlama) — ilk mesh bir adım değildir.
            refinements: meshSayisi > 0 ? meshSayisi - 1 : 0,
            //: P11B3-13 — yönler ve karar yükten geldiği gibi taşınır.
            n_axial: nAxial,
            n_radial: nRadial,
            yon: yonAdi,
            yon_katlama: yon_katlama,
            karar: sonKarar,
            converged: conv.converged === true,
            tol_pct: isNum(conv.tol) ? 100 * conv.tol : null,
            final_rel_change_pct: isNum(conv.final_rel_change)
                ? 100 * conv.final_rel_change : null,
            beyan: (typeof conv.beyan === 'string') ? conv.beyan : null,
            acceptance: acc,
        };
    }

    /* V3 KK 2. tur (FY devri, OH-DK-04) — YÜK MODELİ KÜNYESİ.
       Uç (dalga37/v3-fea-yuk) ``fea.load_model`` ile iç basınç dağılımını
       (izantropik p(x) ya da adıyla sabit P_c geri dönüşü), kapalı uç
       kuvvetini, kapsamı (YALNIZ basınç yüklemesi) ve kuvvet dengesini
       yayımlıyor; panel bu künyeyi basmıyordu. Panel SAYI ÜRETMEZ: alanları
       okur, tanınmayan/sayısal olmayanı düşürür; blok yoksa ya da dağılım
       kodu tanınmıyorsa HİÇBİR satır basılmaz (fail-closed). */
    //: Köprünün dağılım kodları (hrma/fea/bridge.py YUK_DAGILIMI_*).
    const YUK_DAGILIMI_KODLARI = ['isentropic_1d', 'uniform_pc_fallback'];
    //: Kapsam künyesi makine kodu taşımıyor; köprünün sabit kapsam metninin
    //: ÖNEKİ okunur (bridge.py ``_yuk_modeli_kur`` ``kapsam``). Önek tutmazsa
    //: kapsam satırı basılmaz (uydurma kapsam iddiası yok).
    const YUK_KAPSAMI_YALNIZ_BASINC_ONEKI = 'YALNIZ BASINÇ YÜKLEMESİ';
    const MM_PER_M = 1000;
    const N_PER_KN = 1000;

    function yukModeliKunyesi(fea) {
        const lm = fea ? fea.load_model : null;
        if (!lm || typeof lm !== 'object') return null;
        if (YUK_DAGILIMI_KODLARI.indexOf(lm.distribution) < 0) return null;
        const uc = (lm.end_force && typeof lm.end_force === 'object')
            ? lm.end_force : {};
        const out = {
            distribution: lm.distribution,
            gamma: isNum(lm.gamma) ? lm.gamma : null,
            end_force_n: isNum(uc.force_n) ? uc.force_n : null,
            pressure_only: typeof lm.scope === 'string'
                && lm.scope.indexOf(YUK_KAPSAMI_YALNIZ_BASINC_ONEKI) === 0,
            balance: null,
        };
        const fb = lm.force_balance;
        if (fb && typeof fb === 'object') {
            if (fb.measured === true && isNum(fb.rel_error) && isNum(fb.tol)
                    && typeof fb.holds === 'boolean') {
                out.balance = { measured: true, rel_error: fb.rel_error,
                                tol: fb.tol, holds: fb.holds };
            } else if (fb.measured === false) {
                out.balance = { measured: false };
            }
        }
        return out;
    }

    /* V3 KK 2. tur (FY devri 6) — HAM TEPE YÜK UYGULANAN UÇ BANDINDA MI?
       ``scalars.peak_safety_factor`` = min(fields.safety_factor) (uç
       künyesi). Ölçüldü (FY raporu, katı örnek): ham tepe yük uygulanan uçta
       (Saint-Venant bandı içinde) — eşdeğer uç yükünün idealleştirme izi.
       Bu bir HÜKÜM değil TANIdır: hüküm bandın dışından alınır.
       Konum, yayımlanan düğüm alanının en küçüğünün düğümüdür (yalnız
       arama; sayı türetilmez). Bant, ucun yayımladığı Saint-Venant
       beyanından okunur (``meta.cozucu.saint_venant``: ``axial_fix`` ve
       ``neden = 'yuk_uygulama'`` bandının ``d_SV_m``i); yük uygulanan uç,
       kısıtlanmayan uçtur. Ölçüt köprününkiyle aynıdır: uç kesitin bir
       düğümüne uzaklık ≤ d_SV ise düğüm banttadır. Bir koşul eksikse
       (tepe sayısı alanla eşleşmiyor, bant yok/birden çok, kip tanınmıyor,
       ızgara yok) tanı BASILMAZ. */
    const YUK_UCU = { z_max: 'z_min', z_min: 'z_max' };
    //: Yayımlanan tepe sayısı ile alanın en küçüğü arasındaki bağıl eşleşme
    //: payı (aynı sayının JSON gidiş-dönüşü; yuvarlama değil kimlik denetimi).
    const TEPE_ESLESME_BAGIL = 1e-9;

    function tepeBandTanisi(fea) {
        const sc = (fea && fea.scalars) || {};
        const tepe = sc.peak_safety_factor;
        const mesh = (fea && fea.mesh) || {};
        const sf = (fea && fea.fields) ? fea.fields.safety_factor : null;
        const sv = (fea && fea.meta && fea.meta.cozucu)
            ? fea.meta.cozucu.saint_venant : null;
        const dims = gridDims(mesh);
        if (!isNum(tepe) || !Array.isArray(sf) || !Array.isArray(mesh.nodes)
                || !dims || !sv || typeof sv !== 'object'
                || !Array.isArray(sv.bantlar)
                || !Object.prototype.hasOwnProperty.call(YUK_UCU, sv.axial_fix)) {
            return null;
        }
        const bantlar = sv.bantlar.filter(function (b) {
            return b && b.neden === 'yuk_uygulama' && isNum(b.d_SV_m)
                && b.d_SV_m > 0;
        });
        if (bantlar.length !== 1) return null;
        let k = -1;
        for (let n = 0; n < sf.length; n++) {
            if (isNum(sf[n]) && (k < 0 || sf[n] < sf[k])) k = n;
        }
        if (k < 0 || Math.abs(sf[k] - tepe) > TEPE_ESLESME_BAGIL * Math.abs(tepe)) {
            return null;
        }
        const p = mesh.nodes[k];
        if (!Array.isArray(p) || !isNum(p[0]) || !isNum(p[1])) return null;
        const uc = YUK_UCU[sv.axial_fix];
        const satir = mesh.node_index_grid[(uc === 'z_min') ? 0 : dims.ni - 1];
        if (!Array.isArray(satir) || !satir.length) return null;
        let dmin = Infinity;
        for (let j = 0; j < satir.length; j++) {
            const q = mesh.nodes[satir[j]];
            if (!Array.isArray(q) || !isNum(q[0]) || !isNum(q[1])) return null;
            dmin = Math.min(dmin, Math.hypot(p[0] - q[0], p[1] - q[1]));
        }
        const dSv = bantlar[0].d_SV_m;
        if (!(dmin <= dSv)) return null;
        return { peak_safety_factor: tepe, z_m: p[0], r_m: p[1], end: uc,
                 d_sv_m: dSv };
    }

    // Sunucu yanıtı (fea bloğu) → çizilebilir görünüm modeli.
    // ÖH D19 · P11B3-01 — motorun KENDİ yapısal hükmü.
    // Ölçüldü (`once_p11b3_01.json`, taban 60cd341): tek bir hibrit
    // koşumda köprünün emniyet katsayısı 34,28 (rozet YEŞİL) iken motorun
    // kendi `structural_analysis.safety_analysis` bloğu UNSAFE / 0,9653
    // diyordu — 35,5 kat. Fark MODEL FARKIDIR (termal gerilme + dayanım
    // deratingi köprüde yok) ve ucun kendisi bunu `beyan` alanında
    // yazıyor; panel iki sayıdan yalnız iyimser olanı basıyordu.
    // Panel hiçbir sayı türetmez: alanları OKUR, sayısal olmayanı düşürür.
    function motorKarsilastirmasi(fea) {
        const k = (fea && fea.meta && fea.meta.motor_sf_karsilastirmasi)
            ? fea.meta.motor_sf_karsilastirmasi : null;
        if (!k || typeof k !== 'object') return null;
        const motorSf = isNum(k.motor_safety_factor)
            ? k.motor_safety_factor : null;
        return {
            motor_safety_factor: motorSf,
            kopru_min_safety_factor: isNum(k.kopru_min_safety_factor)
                ? k.kopru_min_safety_factor : null,
            oran_kopru_bolu_motor: isNum(k.oran_kopru_bolu_motor)
                ? k.oran_kopru_bolu_motor : null,
            // Üç durumlu: true / false / null (uç söylemediyse İDDİA YOK).
            akma_derate_edildi:
                (typeof k.kopru_akma_derate_edildi === 'boolean')
                    ? k.kopru_akma_derate_edildi : null,
            // `motor_kaynagi` sözlük de olabilir metin de. Sözlükse
            // ucun KENDİ totoloji bayrağı okunur: design_mode='size'
            // koşumunda motor cidarı DEĞERLENDİRDİĞİ gerilme modeliyle
            // BOYUTLANDIRIYOR, dolayısıyla o katsayı bağımsız bir
            // doğrulama değildir. Rozet bunu gizlemez — hükmün rengi
            // kötümser kalır (köprünün yeşili kazanılmamıştır) ama sayının
            // niteliği yanına YAZILIR.
            motor_kaynagi: (typeof k.motor_kaynagi === 'string')
                ? k.motor_kaynagi
                : ((k.motor_kaynagi && typeof k.motor_kaynagi === 'object'
                    && typeof k.motor_kaynagi.alan === 'string')
                    ? k.motor_kaynagi.alan : null),
            motor_sf_totolojik:
                (k.motor_kaynagi && typeof k.motor_kaynagi === 'object'
                 && typeof k.motor_kaynagi.safety_factor_is_tautological
                    === 'boolean')
                    ? k.motor_kaynagi.safety_factor_is_tautological : null,
            beyan: (typeof k.beyan === 'string') ? k.beyan : null,
        };
    }

    /* ÖH D26 · P11B3-20 — NOT_MODELLED DALINDA SUSTURULMUŞ İKİ ALAN.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531):
         vm_notes_alinan = 1 · yapisal_notes_basiliyor = 0
         vm_warning_alinan = 2 · tekil_warning_okumasi = 1  (yalnız TANE dalı)
       Yani görünüm modeli `fea.notes` ile `fea.warning`i ALIYOR, yapısal
       dal ikisini de HİÇ basmıyordu; KARDEŞ tane paneli aynı yanıtın
       `warning` kaydını basıyor. Köprü `notes` içinde eksik her alan için
       KENDİ beyanını yolluyor (`notlar['cidar'] = t_beyan` — cidarın neden
       çıkarılamadığı), yani "hangi alan eksik" listesinin yanında "NEDEN
       eksik" cümlesi de vardı ve ekrana hiç inmiyordu.

       Uydurma yok: alan yoksa satır BASILMAZ. Uyarı kaydı kardeş dalın
       TEK çeviricisinden geçer (doktrin 4 — ikinci bir çevirici yazılmadı). */
    function notModelledDetay(vm) {
        const satirlar = [];
        const uyari = grainWarningText(vm.warning);
        if (uyari) satirlar.push(uyari);
        const notlar = vm.notes;
        if (notlar && typeof notlar === 'object') {
            Object.keys(notlar).forEach(function (k) {
                const v = notlar[k];
                if (typeof v === 'string' && v) satirlar.push(k + ': ' + SRV(v));
            });
        }
        return satirlar.join('\n');
    }

    function buildViewModel(fea, errorText) {
        if (errorText) return { mode: 'error', error: String(errorText) };
        if (!fea || typeof fea !== 'object') return { mode: 'idle' };
        if (fea.status !== 'ok') {
            return {
                mode: 'not_modelled',
                status: fea.status || null,
                missing: Array.isArray(fea.missing) ? fea.missing : [],
                reason: (typeof fea.reason === 'string') ? fea.reason : '',
                notes: (fea.notes && typeof fea.notes === 'object') ? fea.notes : null,
                warning: fea.warning || null,
                engine_layout: fea.engine_layout || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const vm = {
            mode: 'ok',
            engine_layout: fea.engine_layout || null,
            grid: grid,
            von_mises_mpa: fieldToGrid(mesh, fields.von_mises_pa, PA_PER_MPA),
            safety_factor: Array.isArray(fields.safety_factor)
                ? fieldToGrid(mesh, fields.safety_factor, 1) : null,
            wireframe: buildWireframe(mesh),
            centres: elementCentres(mesh),
            quality: fea.quality || null,
            flags: qualityFlags(fea.quality),
            convergence: buildConvergence(fea.convergence),
            /* OH-FT-01 (ÖH D31) — SUNUCU UYARILARI 'ok' DALINDA DA BASILIR.
               Eskiden `fea.warning` YALNIZ not_modelled dalında okunuyordu
               (P11B3-20); 'ok' dalında sunucunun ürettiği uyarı kaydı için
               hiç kanal yoktu. İnce cidar öncülü kırıldığında ölçüm
               `meta.thin_wall` içinde duruyor ama kullanıcıya çıkmıyordu.
               Kayıtlar {code, params} biçimindedir ve kardeş tane dalının
               TEK çeviricisinden (grainWarningText) geçer — ikinci bir
               çevirici yazılmadı (doktrin 4). */
            warnings: Array.isArray(fea.warnings) ? fea.warnings : [],
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_axial: mesh.n_axial, n_radial: mesh.n_radial,
                grid_ni: grid.ni, grid_nj: grid.nj,
                units: mesh.coordinate_units || null,
                meta: mesh.meta || null,
                // ÖH D30 · P11B3-27 — DÜĞÜM SIRASI TANIMI TAŞINIR.
                // ÖLÇÜLDÜ (a2/once.json: P11B3-27_panel_node_order = 0):
                // uç `mesh.node_order` ile indeks sözleşmesini yazıyor
                // (app.py:21211 — "node index = node_index_grid[i][j]; i
                // eksenel istasyon, j cidar katmanı") ama panel alanı hiç
                // taşımıyordu: MESH rozetinde eleman/düğüm SAYISI vardı,
                // sayıların hangi sıralamayla dizildiği yoktu. Kullanıcı
                // ham ağı dışa aktarıp kendi aracında okuduğunda sırayı
                // tahmin etmek zorunda kalıyordu.
                node_order: mesh.node_order || null,
            },
            scalars: {
                // P8B1-01: MANŞET HÜKMÜN ALANINDAN. Emniyet katsayısı
                // düğüm/SPR alanından türetiliyor; manşet tepe gerilmesi de
                // AYNI alandan okunur ki manşet, harita ve hüküm tek
                // sayıdan gelsin. Gauss maksimumu ayrı alanda durur ve
                // kaynağını SUNUCU söyler (headline_source) — panel
                // "Gauss" ya da "düğüm" diye kendi başına etiket basmaz.
                von_mises_max_mpa: isNum(scalars.von_mises_nodal_max_pa)
                    ? scalars.von_mises_nodal_max_pa / PA_PER_MPA
                    : (isNum(scalars.von_mises_gauss_max_pa)
                        ? scalars.von_mises_gauss_max_pa / PA_PER_MPA : null),
                von_mises_gauss_max_mpa: isNum(scalars.von_mises_gauss_max_pa)
                    ? scalars.von_mises_gauss_max_pa / PA_PER_MPA : null,
                von_mises_nodal_max_mpa: isNum(scalars.von_mises_nodal_max_pa)
                    ? scalars.von_mises_nodal_max_pa / PA_PER_MPA : null,
                headline_source: scalars.headline_source || null,
                min_safety_factor: isNum(scalars.min_safety_factor)
                    ? scalars.min_safety_factor : null,
                yield_mpa: isNum(scalars.yield_strength_pa)
                    ? scalars.yield_strength_pa / PA_PER_MPA : null,
                material_key: scalars.material_key || null,
                wall_thickness_m: isNum(scalars.wall_thickness_m)
                    ? scalars.wall_thickness_m : null,
                inner_pressure_pa: isNum(scalars.inner_pressure_pa)
                    ? scalars.inner_pressure_pa : null,
            },
            // V3 KK 2. tur (FY devri): yük modeli künyesi + ham tepe bant tanısı
            load_model: yukModeliKunyesi(fea),
            peak_band: tepeBandTanisi(fea),
            // ÖH D19 · P11B3-01 — MOTORUN KENDİ HÜKMÜ görünüm modeline
            // alınır. Uç `meta.motor_sf_karsilastirmasi` içinde köprünün
            // ve motorun emniyet katsayılarını, oranı ve akmanın derate
            // edilip edilmediğini YAYIMLIYOR; panel bu bloğu hiç
            // okumuyordu ve bu yüzden motorun UNSAFE hükmünün üstüne
            // yeşil rozet basıyordu. Uydurma yok: blok gelmezse null.
            motor_karsilastirma: motorKarsilastirmasi(fea),
            limits: fea.limits || null,
            not_modelled: (fea.meta && Array.isArray(fea.meta.not_modelled))
                ? fea.meta.not_modelled : [],
            basis: {
                fields: (fields && fields._basis) || null,
                quality: (fea.quality && fea.quality._basis) || null,
                // ÖH D31 · P11B3-27 — ÖLÇÜM KODUNUN KİMLİĞİ DE TAŞINIR.
                // ÖLÇÜLDÜ (a1/once.json · M8): uç `quality._source` ile
                // metrikleri HANGİ işlevin ürettiğini yazıyor
                // (app.py:21826 'hrma.app._fea_quad_quality') ama panel
                // yalnız `_basis` cümlesini alıyordu: kullanıcı tanımı
                // görüyor, tanımı UYGULAYAN kodu göremiyordu. Alan
                // gelmezse null (uydurma kimlik yazılmaz).
                quality_source: (fea.quality && fea.quality._source) || null,
                solver: (fea.meta && fea.meta._basis) || null,
                inputs: (fea.meta && fea.meta.girdiler) || null,
                scalars: (scalars && scalars._basis) || null,
            },
        };
        // Düğüm sayısı tutarlılığı: ızgara SUNUCUNUN beyan ettiği düğüm
        // sayısını vermiyorsa alan çizilmez (kısmî harita, haritasızlıktan
        // kötüdür).
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    // <<< FEA_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil (motor_viz3d / blowdown_panel kalıbı)
    // ------------------------------------------------------------------
    const MISSING_COLOR = '#8a93a0';
    const BAD_COLOR = '#ff5d73';        // eşik dışı eleman
    const MESH_COLOR = 'rgba(180,200,215,0.55)';

    // Renk skalaları: yalnız bu Plotly derlemesinde GERÇEKTEN bulunan adlar
    // kullanılır (plotly-1.58.5'te 'Turbo'/'RdYlGn' yoktur), emniyet
    // katsayısı skalası açıkça yazılır — düşük SF kırmızı, yüksek SF yeşil.
    const VM_COLORSCALE = 'Viridis';
    // ÖH D18 · P11B3-04 — EMNİYET KATSAYISI SKALASI MUTLAK ÇAPALIDIR.
    // ÖLÇÜLDÜ (`once_p11b3_04.json`, taban 9071a64): panelde `cmin`/`cmax`/
    // `zmin`/`zmax` HİÇ verilmiyordu; Plotly durak konumlarını VERİ
    // ARALIĞINA normalize ettiği için kırmızı-sarı-yeşil yalnız SIRALAMA
    // anlamına geliyordu — bu koşumda SF 36,93 olan hücre KIRMIZI, SF
    // 128,52 olan YEŞİL boyanıyordu (ikisi de akmanın 36+ katı emniyetli).
    // Aynı skala SF'nin 0,3-0,5 arasında olduğu bir tasarımda EN TEHLİKELİ
    // OLMAYAN hücreyi YEŞİL boyardı.
    //
    // Eşikler rozetle TEK KAYNAKTAN gelir (renderBadges aynı sabitleri
    // okur; iki yerde yazmak ölçütü sessizce kaydırırdı).
    const SF_ERR_MAX = 1.0;     // altı: akma aşıldı (kırmızı)
    const SF_OK_MIN = 1.5;      // üstü: kabul (yeşil)
    //: Skalanın mutlak üst ucu — yeşil eşiğin iki katı. Üstündeki her
    //: değer AYNI yeşile doyar; doyum ekranda BEYAN edilir (kırpma bir
    //: gösterim kararıdır, sayı uydurulmaz).
    const SF_SCALE_MAX = 2 * SF_OK_MIN;
    //: Duraklar mutlak SF değerlerinden türetilir (zmin=0, zmax=SF_SCALE_MAX):
    //: 0 … 1 kırmızı, 1 → 1,5 kırmızıdan sarıya, 1,5 → 3 sarıdan yeşile.
    const SF_COLORSCALE = [
        [0.0, '#ff5d73'],
        [SF_ERR_MAX / SF_SCALE_MAX, '#ff5d73'],
        [SF_OK_MIN / SF_SCALE_MAX, '#ffcf5c'],
        [1.0, '#2dd4a8'],
    ];
    //: SF haritasının mutlak çapası (yalnız bu alan için — von Mises'in
    //: mutlak bir güvenlik anlamı yoktur, o otomatik kalır).
    const SF_Z_LIMITS = { zmin: 0, zmax: SF_SCALE_MAX };

    //: SF haritasının TEK çizim kapısı. Çapa çağrı başına verilen bir
    //: argüman olsaydı bir çağrıda unutulabilirdi (ve carpet yedeği zaten
    //: ayrı bir çağrıdır); kapı çapayı KENDİ koyar, çağıran veremez.
    function sfFieldFigure(vm, zGrid, title, colorbarTitle, carpetId) {
        return fieldFigure(vm, zGrid, title, colorbarTitle, SF_COLORSCALE,
                           carpetId, SF_Z_LIMITS);
    }

    function sfFieldFallbackFigure(vm, zGrid, title, colorbarTitle) {
        return fieldFallbackFigure(vm, zGrid, title, colorbarTitle,
                                   SF_COLORSCALE, SF_Z_LIMITS);
    }

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
            dim: MISSING_COLOR,
        };
        const c = colors[kind] || colors.info;
        return `<span data-badge="${kind}" style="border:1px solid ${c}; color:${c};
            border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
            font-size:0.75rem;">${text}</span>`;
    }

    // Kalite rozetleri — İKİ AYRI ROZET, tek çuval DEĞİL:
    //   (1) ALARM yalnız ölçekli Jacobian bayrağından gelir (gerçek eleman
    //       bozulması); ölçüt yayımlanmadıysa yeşil hüküm basmak yerine
    //       "yayımlanmadı" denir — ölçülmemiş ölçüt "temiz" değildir.
    //   (2) UZAMA nötr bilgi rozetidir: sayı gizlenmez ama alarm rengi
    //       almaz, çünkü ince cidar/ince ağ süpürmesinde uzamış eleman
    //       yapısal olarak beklenir (sunucunun quality._basis beyanı).
    // Burada YALNIZ POLİTİKA vardır (hangi sayım alarm rengini sürer);
    // METİN çağıranındır: metin(ad, params) FeaPanel'de fea.* anahtarlarına,
    // GrainFeaPanel'de solid.fea.* etiketlerine bağlanır ve her panel kendi
    // geometrisini kendi cümlesiyle anlatır. Politika tek yerde durduğu için
    // iki panelde ayrışma da tek bekçiyle kilitlenir.
    function qualityBadges(flags, metin) {
        const c = flags.counts, th = flags.thresholds;
        let html = '';
        if (flags.measured.jacobian) {
            html += badge(metin('badgeDistortion',
                { bad: c.jacobian, total: c.total,
                  sjMin: th.scaled_jacobian_min }),
                c.jacobian ? 'warn' : 'ok');
        } else {
            html += badge(metin('badgeDistortionMissing', {}), 'dim');
        }
        if (flags.measured.aspect) {
            html += badge(metin('badgeElongated',
                { bad: c.aspect, total: c.total,
                  arMax: th.aspect_ratio_max }), 'info');
        }
        // P11B3-05: EN KÖTÜ ELEMANIN ÖLÇÜSÜ — sayım değil, BÜYÜKLÜK.
        // Renk NÖTR (info) kalır: uzama ince cidarda beklenir ve panelin
        // kendi kabul eşiği yoktur; gizlenen şey sayının kendisiydi.
        if (flags.worst) {
            const wr = flags.worst;
            html += badge(metin('badgeWorstQuality', {
                ar: (wr.aspect_ratio_max === null)
                    ? '—' : fmt(wr.aspect_ratio_max, 2),
                arX: (wr.aspect_over_threshold === null)
                    ? '—' : fmt(wr.aspect_over_threshold, 1),
                sj: (wr.scaled_jacobian_min === null)
                    ? '—' : fmt(wr.scaled_jacobian_min, 4),
            }), 'info');
        }
        return html;
    }

    function chipHtml(label, reason) {
        let html = `<span data-chip="not-modelled" style="border:1px solid ${MISSING_COLOR};
            color:${MISSING_COLOR}; border-radius:6px; padding:4px 10px;
            font-family:var(--hd-mono); font-size:0.75rem;">${esc(label)}</span>`;
        if (reason) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0 0;
                white-space:pre-wrap;">${esc(SRV(reason))}</p>`;
        }
        return html;
    }

    function fmt(v, digits) {
        return isNum(v) ? v.toFixed(digits === undefined ? 2 : digits) : '—';
    }

    // Bağıl değişim yüzdeleri çok küçük olabilir: ölçüldü, port lif gerinimi
    // son tur değişimi %0,003 mertebesinde geliyor. Sabit iki basamak bunu
    // "%0,00" diye basar ve YAYIMLANMIŞ bir değişimi sıfır gibi gösterir.
    // Sunucunun beyan metniyle aynı kural kullanılır (4 anlamlı basamak,
    // planar_grain._yuzde → '%.4g'); sondaki sıfırlar atılır.
    function fmtSig(v, digits) {
        return isNum(v) ? String(Number(v.toPrecision(digits || 4))) : '—';
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="feaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="fea.title">${T('fea.title',
                'Structural FEA — Stress Field, Mesh and Convergence')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="fea.intro">${T('fea.intro',
                    'An axisymmetric finite element run on the chamber/nozzle wall of '
                    + 'THIS result: the solver refines the mesh until the peak von Mises '
                    + 'stress stops changing. You do not set the mesh — but you can see '
                    + 'it: the wireframe, the element quality map and the convergence '
                    + 'history are all drawn from the run itself. If an input is '
                    + 'missing, nothing is drawn and the missing item is named.')}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="fea_run" class="btn" type="button"
                    data-i18n="fea.run">${T('fea.run', 'Run structural analysis')}</button>
                <span id="fea_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                ${iptalDugmesiHtml('fea_cancel', T('fea.cancel', 'Cancel run'))}
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="fea_show_mesh" checked>
                    <span data-i18n="fea.showMesh">${T('fea.showMesh',
                        'Show mesh wireframe')}</span>
                </label>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <span data-i18n="fea.qualityMetric">${T('fea.qualityMetric',
                        'Quality metric')}</span>
                    <select id="fea_metric">
                        <!-- ÖH D36 / dil2-i18n-pdf a2 (OH-GT devri): seçenek
                             etiketi data-i18n taşır, I18N.apply onu da çevirir.
                             ÖLÇÜLDÜ (a2/once_tarayici.json, taban bb7ee57c,
                             TR kipi): bu iki seçenek hibrit ve sıvı sayfasında
                             TR ekranda 'Aspect ratio' / 'Scaled Jacobian'
                             kalıyordu; öznitelik olmadığı için I18N.apply turu
                             onları çevirmiyordu (Merkez kopyası 3232-3239 zaten
                             taşıyordu). Öznitelikle TR 'En-boy oranı', EN'e
                             geçişte 'Aspect ratio' (a2/sonra_tarayici.json). -->
                        <option value="aspect_ratio" data-i18n="fea.metricAspect">${T('fea.metricAspect',
                            'Aspect ratio')}</option>
                        <option value="scaled_jacobian" data-i18n="fea.metricJacobian">${T('fea.metricJacobian',
                            'Scaled Jacobian')}</option>
                    </select>
                </label>
            </div>
            <div id="fea_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="fea_chip" style="margin:8px 0;"></div>
            <div id="fea_plot_vm" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_plot_sf" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_plot_quality" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_quality_note" style="font-family:var(--hd-mono); font-size:0.72rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <div id="fea_plot_conv" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_conv_note" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="fea_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="fea.basisTitle">${T('fea.basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)')}</summary>
                <div id="fea_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></div>
            </details>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function wireTrace(vm) {
        const w = vm.wireframe;
        return {
            x: w.x, y: w.y, mode: 'lines', type: 'scatter',
            line: { color: MESH_COLOR, width: 1 },
            name: TF('fea.meshTrace', { n: vm.mesh_info.n_elems },
                     'Mesh ({n} elements)'),
            hoverinfo: 'skip',
        };
    }

    // Eşik dışı eleman katmanı. HİÇBİRİ ya da HEPSİ eşik dışıysa katman
    // çizilmez: hepsi kırmızıysa halkalar ölçüt haritasını tamamen örter ve
    // ayırt edici bilgi taşımaz (sayı zaten rozette ve not satırında yazar).
    function badElementsTrace(vm) {
        const flags = vm.flags, centres = vm.centres;
        if (!flags || !centres) return null;
        if (flags.counts.any === 0 || flags.counts.any === flags.counts.total) {
            return null;
        }
        const x = [], y = [];
        for (let e = 0; e < flags.any.length; e++) {
            if (flags.any[e]) { x.push(centres.x[e]); y.push(centres.y[e]); }
        }
        if (!x.length) return null;
        // AÇIK halka: altındaki ölçüt rengini KAPATMAZ. İnce cidarda bütün
        // elemanlar eşiği aşabiliyor; dolu işaret kullanılsaydı ölçütün
        // nerede kötüleştiği görünmez olurdu.
        return {
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: BAD_COLOR, size: 10, symbol: 'circle-open',
                      line: { color: BAD_COLOR, width: 1.5 } },
            name: TF('fea.badElems', { n: x.length },
                     '{n} elements outside the quality range'),
        };
    }

    // Alan haritası: carpet + contourcarpet. Carpet izi yoksa (eski Plotly)
    // düğüm nokta haritasına düşülür ve bu durum çipte BEYAN edilir.
    function fieldFigure(vm, zGrid, title, colorbarTitle, colorscale, carpetId,
                         zLimits) {
        const g = vm.grid;
        const alan = {
            type: 'contourcarpet', carpet: carpetId,
            a: g.a, b: g.b, z: zGrid,
            contours: { coloring: 'fill', showlines: false },
            colorscale: colorscale,
            colorbar: { title: colorbarTitle, titleside: 'right' },
            name: colorbarTitle,
        };
        // P11B3-04: çapa VERİLDİYSE renk ölçeği mutlaktır (Plotly aksi
        // hâlde durakları veri aralığına normalize eder). Çapa yoksa
        // davranış birebir eskisi gibi kalır.
        if (zLimits) {
            alan.zauto = false;
            alan.zmin = zLimits.zmin;
            alan.zmax = zLimits.zmax;
        }
        const traces = [{
            type: 'carpet', carpet: carpetId,
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, alan];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: title,
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği: düğüm noktaları, alan değerine göre renkli.
    function fieldFallbackFigure(vm, zGrid, title, colorbarTitle, colorscale,
                                 zLimits) {
        const g = vm.grid;
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]); c.push(zGrid[j][i]);
            }
        }
        const isaret = { color: c, colorscale: colorscale, size: 6,
                         colorbar: { title: colorbarTitle, titleside: 'right' } };
        // P11B3-04: yedek harita da AYNI mutlak çapayı taşır — carpet izi
        // yoksa renk anlamı değişmemeli.
        if (zLimits) {
            isaret.cauto = false;
            isaret.cmin = zLimits.zmin;
            isaret.cmax = zLimits.zmax;
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: isaret,
            name: colorbarTitle,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: title,
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    function qualityFigure(vm) {
        const q = vm.quality, flags = vm.flags, centres = vm.centres;
        const values = (q && Array.isArray(q[qualityMetric])) ? q[qualityMetric] : null;
        if (!values || !centres || !flags) return null;
        // Ölçüt haritası BÜTÜN elemanları taşır (eşik dışı olanlar dahil):
        // ince cidarda hepsi eşiği aşabilir, o durumda bile kullanıcının
        // görmesi gereken şey ölçütün NEREDE kötüleştiğidir. Eşik dışı
        // elemanlar ayrıca kırmızı katmanla işaretlenir.
        const allX = [], allY = [], allC = [];
        for (let e = 0; e < values.length; e++) {
            allX.push(centres.x[e]); allY.push(centres.y[e]);
            allC.push(isNum(values[e]) ? values[e] : null);
        }
        const label = (qualityMetric === 'aspect_ratio')
            ? T('fea.metricAspect', 'Aspect ratio')
            : T('fea.metricJacobian', 'Scaled Jacobian');
        const traces = [];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        if (allX.length) {
            traces.push({
                x: allX, y: allY, mode: 'markers', type: 'scatter',
                marker: { color: allC, colorscale: 'Viridis', size: 5,
                          colorbar: { title: label, titleside: 'right' } },
                name: label,
            });
        }
        const bad = badElementsTrace(vm);
        if (bad) traces.push(bad);
        return {
            traces: traces,
            layout: {
                title: TF('fea.chartQuality', { metric: label },
                          'Element quality — {metric} (one marker per element, '
                          + 'placed at the element centroid)'),
                xaxis: { title: T('fea.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('fea.axisR', 'Radius r [m]') },
                height: 340,
                legend: { orientation: 'h', y: 1.14 },
            },
        };
    }

    //: P11B3-13 — göreli değişim izinin etiketi ALAN ADIdır: yeni i18n
    //: anahtarı açılmaz (sözlük dosyaları bu dalgada kardeş kulvarın
    //: sahası) ve makine adı çeviri gerektirmez.
    const REL_CHANGE_ETIKETI = 'rel_change [%]';

    //: P11B3-13 — her noktanın YÖN künyesi (n_axial x n_radial). Alan
    //: yoksa künye YAZILMAZ (uydurma etiket yasak).
    function convYonEtiketleri(conv) {
        if (!conv.n_axial || !conv.n_radial) return null;
        const etiket = conv.n_elems.map(function (_, i) {
            const a = conv.n_axial[i], r = conv.n_radial[i];
            if (!isNum(a) || !isNum(r)) return '';
            return 'n_axial = ' + a + ' x n_radial = ' + r
                + (conv.yon && conv.yon[i] ? ' (' + conv.yon[i] + ')' : '');
        });
        return etiket.some(function (t) { return t; }) ? etiket : null;
    }

    function convergenceFigure(conv) {
        const yonEtiket = convYonEtiketleri(conv);
        const izler = [{
            x: conv.n_elems, y: conv.von_mises_mpa,
            mode: 'lines+markers', type: 'scatter',
            marker: { size: 9 }, line: { width: 2 },
            name: T('fea.sVmMax', 'Peak von Mises [MPa]'),
        }];
        if (yonEtiket) {
            izler[0].text = yonEtiket;
            izler[0].hovertemplate = '%{y:.4g} MPa<br>%{text}<extra></extra>';
        }
        //: Yükte HAZIR olan göreli değişim dizisi de çizilir: eğri
        //: düzleşirken hangi turda toleransın altına indiği okunabilsin
        //: (ölçüldü: dizi kuruluyor, hiçbir yerde çizilmiyordu).
        const relCizilir = Array.isArray(conv.rel_change_pct)
            && conv.rel_change_pct.length === conv.n_elems.length
            && conv.rel_change_pct.some(isNum);
        if (relCizilir) {
            izler.push({
                x: conv.n_elems, y: conv.rel_change_pct,
                mode: 'lines+markers', type: 'scatter',
                marker: { size: 6 }, line: { width: 1.5, dash: 'dot' },
                name: REL_CHANGE_ETIKETI,
                yaxis: 'y2',
            });
        }
        const layout = {
            title: T('fea.chartConvergence',
                     'Mesh convergence — peak von Mises vs element count'),
            xaxis: { title: T('fea.axisElems', 'Elements in mesh [-]'),
                     type: 'log' },
            yaxis: { title: T('fea.axisVm', 'Peak von Mises [MPa]') },
            height: 300,
            showlegend: relCizilir,
        };
        if (relCizilir) {
            layout.yaxis2 = {
                title: REL_CHANGE_ETIKETI,
                overlaying: 'y', side: 'right', showgrid: false,
            };
            layout.legend = { orientation: 'h', y: 1.16 };
        }
        return { traces: izler, layout: layout };
    }

    function drawFigure(el, figure) {
        Plotly.react(el, figure.traces, figure.layout,
                     { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Basım
    // ------------------------------------------------------------------

    // P8B1-01 — ROZET KAYNAĞINI SUNUCU SÖYLER.
    // Manşet sayıları eskiden Gauss noktalarından geliyordu ve etiketleri
    // de öyle diyordu. Hüküm sayısı düğüm/SPR alanına taşınınca etiket
    // YALAN oldu: rozet hâlâ "(Gauss points)" yazıyordu. Sözlük anahtarı
    // bu kulvarın sahası değil (i18n dosyalarına dokunulmaz), o yüzden
    // yerelleştirilmiş metnin SONDAKİ parantezli kaynak eki sökülür ve
    // yerine sunucunun beyan ettiği kaynak yazılır. Sunucu kaynak
    // bildirmiyorsa hiçbir kaynak İDDİA EDİLMEZ — ek düşer (fail-closed:
    // uydurma etiket, etiketsizlikten kötüdür).
    // Emniyet katsayısı → rozet türü. Eşikler kontur skalasıyla TEK
    // KAYNAKTAN gelir (SF_ERR_MAX / SF_OK_MIN, P11B3-04).
    function sfRozetTuru(sf) {
        if (!isNum(sf)) return 'dim';
        return sf < SF_ERR_MAX ? 'err' : (sf < SF_OK_MIN ? 'warn' : 'ok');
    }

    function kaynakliRozet(metin, kaynak) {
        const govde = String(metin).replace(/\s*\([^()]*\)\s*$/, '');
        return kaynak ? govde + ' (' + kaynak + ')' : govde;
    }

    function renderBadges(el, vm) {
        let html = '';
        if (vm.engine_layout) {
            html += badge(T('fea.badgeEngine', 'ENGINE') + ': '
                + esc(String(vm.engine_layout).toUpperCase()), 'info');
        }
        html += badge(TF('fea.badgeMesh',
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes },
            'MESH {elems} elements / {nodes} nodes'), 'info',
            // P11B3-27: sıralama sözleşmesi rozetin ipucunda; alan
            // gelmiyorsa ipucu HİÇ kurulmaz (uydurma tanım yazılmaz).
            vm.mesh_info.node_order || undefined);
        // P11B3-21 — GEOMETRİ DEĞİŞTİYSE HÜKÜM ŞERİDİNDE SÖYLENİR.
        // Katlanmış künyede kalan beyan görünmez (P11B3-15 dersi); cidar
        // kalınlaşması emniyet katsayısını YÜKSELTTİĞİ için bu, hükmün
        // okunmasını doğrudan etkiler.
        const _dy = disYuzeyBeyani(vm.mesh_info.meta);
        if (_dy && _dy.duzeltilen !== null && _dy.duzeltilen > 0) {
            html += badge(TF('fea.badgeOuterModified',
                { n: _dy.duzeltilen,
                  pct: (_dy.sapma_yuzde !== null)
                      ? fmt(_dy.sapma_yuzde, 1) : '?' },
                'OUTER SURFACE MODIFIED at {n} station(s) · wall {pct}% vs '
                + 'requested'), 'warn');
        }
        html += badge(kaynakliRozet(TF('fea.badgeVm',
            { v: fmt(vm.scalars.von_mises_max_mpa, 1) },
            'PEAK von MISES {v} MPa (Gauss points)'),
            vm.scalars.headline_source), 'info');
        if (vm.scalars.min_safety_factor !== null) {
            // Eşikler kontur skalasıyla TEK KAYNAKTAN (P11B3-04): rozetin
            // "yeşil" dediği yer ile haritanın yeşil boyadığı yer aynıdır.
            // ÖH D19 · P11B3-01 — HÜKÜM RENGİ KÖTÜMSERDİR.
            // Uç iki emniyet katsayısı yayımlıyor: köprünün (bu koşumda
            // 34,28) ve motorun kendi kuplajlı hükmü (0,9653, UNSAFE).
            // Panel eskiden yalnız köprününkini basıyor ve YEŞİL diyordu;
            // kullanıcı erime noktasının 882 K üstünde ölçülmüş bir cidar
            // için "emniyet katsayısı 34" görüyordu. Sayılar birbirinin
            // yerine GEÇMEZ (ikisi ayrı ayrı basılır), ama RENK — yani
            // tehlike hükmü — yayımlanan en kötü sayıdan verilir.
            const motorSf = vm.motor_karsilastirma
                ? vm.motor_karsilastirma.motor_safety_factor : null;
            const hukumSf = (motorSf !== null)
                ? Math.min(vm.scalars.min_safety_factor, motorSf)
                : vm.scalars.min_safety_factor;
            const kind = sfRozetTuru(hukumSf);
            // Akmanın niteliği rozetin KENDİ satırında durur: uç "bu
            // koşumda derate edilmedi" diyorsa 34,28 oda sıcaklığı
            // dayanımıyla kurulmuştur ve bunu görmek için künyeyi açmak
            // gerekmemelidir. Uç bir şey söylemediyse İDDİA EDİLMEZ.
            const derate = vm.motor_karsilastirma
                ? vm.motor_karsilastirma.akma_derate_edildi : null;
            let sfMetni = kaynakliRozet(TF('fea.badgeSf',
                { v: fmt(vm.scalars.min_safety_factor, 2) },
                'MIN SAFETY FACTOR {v} (Gauss points)'),
                vm.scalars.headline_source);
            if (derate === false) {
                sfMetni += ' — ' + T('fea.badgeSfRoomTempYield',
                    'room-temperature yield, NOT derated for wall temperature');
            } else if (derate === true) {
                sfMetni += ' — ' + T('fea.badgeSfDeratedYield',
                    'yield derated to the wall temperature reported by the engine');
            }
            html += badge(sfMetni, kind);
            // Motorun kendi sayısı AYRI rozette, kendi rengiyle.
            if (motorSf !== null) {
                const oran = vm.motor_karsilastirma.oran_kopru_bolu_motor;
                let motorMetni = TF('fea.badgeEngineSf',
                    { v: fmt(motorSf, 2),
                      ratio: (oran !== null) ? fmt(oran, 1) : '?' },
                    'ENGINE\u2019S OWN SAFETY FACTOR {v} — the structural run '
                    + 'reports {ratio}x higher because thermal stress and '
                    + 'strength derating are not modelled here; the lower '
                    + 'number governs the design');
                if (vm.motor_karsilastirma.motor_sf_totolojik === true) {
                    motorMetni += ' — ' + T('fea.badgeEngineSfTautological',
                        'the engine SIZED the wall with the same stress model '
                        + 'it evaluates, so this number is not an independent '
                        + 'verification either');
                }
                html += badge(motorMetni, sfRozetTuru(motorSf));
            }
        } else {
            html += badge(T('fea.badgeSfMissing',
                'SAFETY FACTOR NOT PUBLISHED (no yield strength in the material record)'),
                'dim');
        }
        const conv = vm.convergence;
        if (conv) {
            html += badge(conv.converged
                ? TF('fea.badgeConverged',
                     { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) },
                     'CONVERGED in {n} rounds to {pct}%')
                : TF('fea.badgeNotConverged',
                     { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) },
                     'NOT CONVERGED after {n} rounds (last change {pct}%)'),
                conv.converged ? 'ok' : 'warn');
        }
        if (vm.flags) {
            // Eski tek rozet ("MESH QUALITY {bad}/{total} ... outside the
            // acceptable range") KALDIRILDI: uzama ile bozulmayı birleştirip
            // alarm rengiyle basıyordu ve ince cidarda bozulma sıfırken
            // "1024/1024" korkutuyordu. Ayrışma qualityBadges() içinde.
            // Anahtarlar LİTERAL yazılır (birleştirilmiş anahtar sözlük
            // taramasında görünmez, ölü-çeviri bekçisini yanıltır).
            html += qualityBadges(vm.flags, function (ad, p) {
                if (ad === 'badgeDistortion') {
                    return TF('fea.badgeDistortion', p,
                        'MESH DISTORTION (scaled Jacobian < {sjMin}): '
                        + '{bad}/{total} flagged');
                }
                if (ad === 'badgeDistortionMissing') {
                    return TF('fea.badgeDistortionMissing', p,
                        'MESH DISTORTION NOT PUBLISHED (the response carries '
                        + 'no scaled Jacobian, so no distortion verdict is '
                        + 'issued)');
                }
                if (ad === 'badgeWorstQuality') {
                    return TF('fea.badgeWorstQuality', p,
                        'WORST ELEMENT — aspect ratio {ar} ({arX}x the '
                        + 'threshold), scaled Jacobian {sj}');
                }
                return TF('fea.badgeElongated', p,
                    'ELONGATED ELEMENTS (aspect ratio > {arMax}): '
                    + '{bad}/{total} — expected where a thin wall is swept '
                    + 'along a long contour, not a distortion alarm');
            });
        }
        if (carpetFallback) {
            html += badge(T('fea.badgeFallback',
                'CONTOUR UNAVAILABLE — node point map drawn instead'), 'dim');
        }
        /* OH-FT-01 — sunucunun uyarı kayıtları rozet olarak basılır.
           Metin SUNUCUDAN gelen anahtarın çevirisidir; panel kendi
           cümlesini uydurmaz, kod çözülemezse ham anahtar görünür ki
           eksik sözlük kaydı SESSİZ kalmasın. */
        if (Array.isArray(vm.warnings)) {
            vm.warnings.forEach(function (w) {
                const metin = grainWarningText(w);
                if (metin) html += badge(metin, 'warn');
            });
        }
        el.innerHTML = html;
    }

    // ÖH D19 · P11B3-06 — koşumun dört skaler girdisi tek cümlede.
    // Sayılar görünüm modelinden OKUNUR; eksik olan alan yazılmaz
    // (uydurma değer yok). Hiçbiri yoksa cümle hiç basılmaz.
    function girdiParcasi(vm) {
        const sc = vm.scalars || {};
        const pc = isNum(sc.inner_pressure_pa)
            ? sc.inner_pressure_pa / PA_PER_BAR : null;
        const alanlar = [];
        if (sc.material_key) {
            alanlar.push(T('fea.inMaterial', 'material') + ' '
                + String(sc.material_key));
        }
        if (isNum(sc.yield_mpa)) {
            alanlar.push(T('fea.inYield', 'yield') + ' '
                + fmt(sc.yield_mpa, 1) + ' MPa');
        }
        if (isNum(sc.wall_thickness_m)) {
            alanlar.push(T('fea.inWall', 'wall thickness') + ' '
                + fmt(sc.wall_thickness_m * 1000, 2) + ' mm');
        }
        if (pc !== null) {
            alanlar.push(T('fea.inPressure', 'internal pressure') + ' '
                + fmt(pc, 2) + ' bar');
        }
        if (!alanlar.length) return null;
        return TF('fea.inputsLine', { list: alanlar.join('; ') },
            'This run was solved with: {list}.');
    }

    /* ÖH D26 · P11B3-21 — «DIŞ YÜZEY DEĞİŞTİRİLDİ» BEYANI EKRANA İNMİYORDU.

       ÖLÇÜLDÜ (a3/once.json, taban 7751531):
         sunucu_mesh_meta_yayini = 3 · fea_vm_meta_alinan = 1
         fea_meta_okunuyor = 0 · fea_dis_yuzey_basiliyor = 0
         (termal kardeşte meta görünüm modeline HİÇ alınmıyordu: 0)
       Ağ üreticisi (`mesh_axisym.build_wall_mesh`) `meta` içinde iyi
       konumluluk için dış yüzeyi DÜZELTTİĞİNİ, kaç istasyonda
       düzelttiğini ve cidarın istenene göre yüzde kaç KALINLAŞTIĞINI
       yayımlıyor. Bu emniyetsiz YÖNDE bir modelleme kararıdır (kalın
       cidar emniyet katsayısını yükseltir), yani kullanıcı gördüğü
       sayının hangi geometriden geldiğini bilmeden hüküm okuyamaz.

       Beyan ÇÖZÜM DEĞİLDİR ama bu kalemde kusur zaten beyanın
       YUTULMASIDIR: uç doğruyu söylüyor, panel susuyordu. Sayı
       türetilmez, ucun kendi alanları basılır; alan yoksa satır yok. */
    /* ÖH D27 · OH-D26-16 — YÜZDE ÇARPANI TEK KAYNAKTAN.
       `const YUZDE = 100.0` bu dosyada ve kardeşinde AYRI AYRI yazılıydı
       (ölçüldü: a2/once.json `yuzde_yerel_tanim` = 2). Artık ikisi de
       `units_constants.js`ten OKUR. FAIL-CLOSED: modül yoksa yedek sayı
       uydurulmaz, hata fırlar. Çözüm ÇAĞRI ANINDA yapılır (yükleme anında
       değil) ki bu dosyayı units_constants.js olmadan yükleyen mevcut
       düzenekler kırılmasın — kapı, sayının KULLANILDIĞI yerdedir. */
    function yuzdeCarpani() {
        var g = (typeof window !== 'undefined') ? window : globalThis;
        if (!g.HRMAUnits && typeof require === 'function') {
            try {
                var m = require('./units_constants.js');
                g.HRMAUnits = m.UNITS;
                g.HRMAUnits.requirePercentPerFraction =
                    m.requirePercentPerFraction;
            } catch (e) { /* tarayıcıda require yok — <script> ile gelir */ }
        }
        if (!g.HRMAUnits || !g.HRMAUnits.requirePercentPerFraction) {
            throw new Error('units_constants.js must load before this panel: '
                + 'PERCENT_PER_FRACTION has a single source and is not '
                + 're-declared here.');
        }
        return g.HRMAUnits.requirePercentPerFraction();
    }

    function disYuzeyBeyani(meta) {
        if (!meta || typeof meta !== 'object') return null;
        const t = meta.dis_yuzey_egrilik_tabani;
        if (!t || typeof t !== 'object') return null;
        const duzeltilen = t.duzeltilen_istasyon;
        const sapma = t.kalinlik_sapma_orani;
        return {
            duzeltilen: (typeof duzeltilen === 'number'
                         && isFinite(duzeltilen)) ? duzeltilen : null,
            sapma_yuzde: (typeof sapma === 'number' && isFinite(sapma))
                ? sapma * yuzdeCarpani() : null,
            taban_kaynagi: (typeof t.taban_kaynagi === 'string')
                ? t.taban_kaynagi : null,
            beyan: (t.dereceli_ornekleme
                    && typeof t.dereceli_ornekleme.beyan === 'string')
                ? t.dereceli_ornekleme.beyan : null,
        };
    }

    /* Beyanın CÜMLELERİ (künye bloğuna). Rozet katı ayrı: değişiklik
       varsa hüküm şeridinde de görünür (P11B3-15 dersi: katlanmış
       künyede kalan beyan görünmez). */
    function disYuzeySatirlari(meta) {
        const d = disYuzeyBeyani(meta);
        if (!d) return [];
        const satir = [];
        if (d.duzeltilen !== null) {
            satir.push(TF('fea.meshOuterCorrected', { n: d.duzeltilen },
                'mesh.meta: the outer surface was corrected at {n} axial '
                + 'station(s) for well-posedness; the wall you see is the '
                + 'meshed wall, not the raw offset.'));
        }
        if (d.sapma_yuzde !== null) {
            satir.push(TF('fea.meshThicknessDeviation',
                { pct: fmt(d.sapma_yuzde, 1) },
                'mesh.meta: solved wall thickness deviates {pct}% from the '
                + 'requested thickness (kalinlik_sapma_orani).'));
        }
        if (d.taban_kaynagi) satir.push(SRV(d.taban_kaynagi));
        if (d.beyan) satir.push(SRV(d.beyan));
        return satir;
    }

    function renderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        if (vm.basis.solver) parts.push(SRV(vm.basis.solver));
        if (vm.basis.fields) parts.push(SRV(vm.basis.fields));
        if (vm.basis.quality) parts.push(SRV(vm.basis.quality));
        // ÖH D31 · P11B3-27: tanımı UYGULAYAN kodun kimliği tanımın
        // hemen ardında durur (uç `quality._source`). Alan yoksa satır yok.
        if (vm.basis.quality_source) {
            // ÖH D32 / OH-D31-01: D31'in ham dize devri ÖDENDİ — etiket
            // artık sözlükten geçiyor (`fea.qualitySource`, EN+TR).
            parts.push(TF('fea.qualitySource',
                          { source: String(vm.basis.quality_source) },
                          'Mesh quality metrics computed by: {source}'));
        }
        // P8B1-01: manşet skalerlerinin kaynağını SUNUCU yazar. Sunucu
        // beyanı geldiğinde eski 'fea.gaussNote' metni BASILMAZ — o metin
        // manşetin Gauss noktalarından geldiğini söylüyor, oysa hüküm
        // sayısı düğüm/SPR alanından geliyor (iki metin birlikte basılsa
        // panel kendi kendisiyle çelişirdi).
        if (vm.basis.scalars) parts.push(SRV(vm.basis.scalars));
        // ÖH D19 · P11B3-06 — KOŞUMUN GİRDİLERİ EKRANA YAZILIR.
        // Ölçüldü (`once_p11b3_06.json`, taban 60cd341): panel
        // `material_key` / `yield_mpa` / `wall_thickness_m` /
        // `inner_pressure_pa` skalerlerini görünüm modelinde KURUYOR ama
        // dördünü de hiçbir kaba basmıyordu; üstelik ekrandaki
        // not_modelled maddesi kullanıcıyı panelin HİÇ basmadığı
        // `girdiler.yuk` bloğuna yolluyordu (ölü gönderme). Tek güvenlik
        // sayısı hangi malzemenin, hangi akmanın, hangi cidarın ve hangi
        // basıncın altında üretildiği yazılmadan basılmaz.
        const gp = girdiParcasi(vm);
        if (gp) parts.push(gp);
        // P11B3-21 — ağ üreticisinin geometri beyanı.
        disYuzeySatirlari(vm.mesh_info && vm.mesh_info.meta)
            .forEach(function (c) { parts.push(c); });
        if (vm.basis.inputs && typeof vm.basis.inputs === 'object') {
            const y = vm.basis.inputs.yuk;
            if (y && typeof y === 'object' && typeof y.dagilim === 'string') {
                parts.push(SRV(y.dagilim));
            }
            const m = vm.basis.inputs.malzeme;
            if (m && typeof m === 'object'
                    && typeof m.akma_kaynagi === 'string') {
                parts.push(SRV(m.akma_kaynagi));
            }
            if (typeof vm.basis.inputs.cidar === 'string') {
                parts.push(SRV(vm.basis.inputs.cidar));
            }
        }
        parts.push(TF('fea.unitNote', { }, 'Units: the solver returns Pa; the '
            + 'panel only divides by 1e6 to plot MPa. No smoothing, no '
            + 'resampling, no rescaling of the field is applied.'));
        parts.push(T('fea.axisNote', 'Axes are NOT equally scaled: the wall is '
            + 'thin compared with the engine length, so the radial axis is '
            + 'stretched to make the wall visible.'));
        // Sunucu skaler beyanı yayımlamıyorsa (eski gövde) eski not
        // basılır: o gövdede manşet GERÇEKTEN Gauss noktalarından gelir,
        // dolayısıyla metin oradaki gerçeği söyler.
        if (!vm.basis.scalars) {
            parts.push(T('fea.gaussNote', 'The headline peak stress and '
                + 'minimum safety factor are taken at the Gauss points of the '
                + 'elements; the map shows the stress recovered at the nodes, '
                + 'so the extreme value read off the map can differ slightly '
                + 'from the headline number. Neither is rescaled to match the '
                + 'other.'));
        }
        if (vm.limits && vm.limits.clamped) {
            parts.push(TF('fea.limitNote',
                { max: vm.limits.max_elems, allowed: vm.limits.rounds_allowed,
                  requested: vm.limits.rounds_requested },
                'Refinement was capped at {allowed} of {requested} rounds to keep '
                + 'the mesh within {max} elements.'));
            // ÖH D31 · P11B3-27 — BİR TURUN NE KADAR SIKLAŞTIRDIĞI.
            // ÖLÇÜLDÜ (a1/once.json · M8: `refine_factor = 0`): uç
            // `limits.refine_factor` yayımlıyor (app.py:21793) ama panel
            // okumuyordu; kullanıcı "3 turdan 1'i koştu" cümlesini
            // görüyor, o turun ağı kaç kat sıklaştıracağını göremiyordu —
            // kırpmanın BÜYÜKLÜĞÜ ölçülemiyordu. Alan gelmezse cümle
            // HİÇ kurulmaz (çarpan uydurulmaz).
            if (typeof vm.limits.refine_factor === 'number'
                    && isFinite(vm.limits.refine_factor)) {
                // ÖH D32 / OH-D31-01: sözlüğe bağlandı
                // (`fea.limitRefineFactor`, EN+TR). Çarpan yine UÇTAN gelir;
                // alan yoksa bu dal hiç çalışmaz (sayı uydurulmaz).
                parts.push(TF('fea.limitRefineFactor',
                              { factor: String(vm.limits.refine_factor) },
                              'Each refinement round multiplies the axial '
                              + 'and radial station counts by {factor}.'));
            }
        }
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(TF(
                'fea.notModelledCount', { n: vm.not_modelled.length },
                '{n} physics items are NOT modelled in this structural run:'))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        // V3 KK 2. tur (FY devri): yük modeli künyesi ve ham tepe tanısı
        // textContent ile eklenir (sunucu metni HTML'e girmez).
        yukModeliSatirlari(vm).forEach(function (s) {
            const p = document.createElement('p');
            p.style.margin = '0 0 8px';
            p.setAttribute('data-fea-load-model', s.ad);
            p.textContent = s.metin;
            els.basisText.appendChild(p);
        });
        els.basis.style.display = '';
    }

    /* V3 KK 2. tur (FY devri) — künye satırları (EN = TR, i18n_common
       'fea.loadModel*' / 'fea.peakInLoadBand'). Sayılar ucun yayımladığı
       alanlardır; panel yalnız birim çevirir (m → mm, N → kN). */
    function yukModeliSatirlari(vm) {
        const s = [];
        const lm = vm.load_model;
        if (lm) {
            if (lm.distribution === 'isentropic_1d') {
                if (lm.gamma !== null) {
                    s.push({ ad: 'distribution', metin: TF('fea.loadModelIsentropic',
                        { gamma: fmt(lm.gamma, 4) },
                        'Wall pressure: 1-D isentropic static pressure p(x) along '
                        + 'the nozzle (gamma = {gamma}), P_c in the chamber '
                        + 'cylinder.') });
                }
            } else {
                s.push({ ad: 'distribution', metin: T('fea.loadModelFallback',
                    'Wall pressure: UNIFORM P_c FALLBACK — gamma or the contour '
                    + 'was missing or invalid, so the isentropic p(x) was not '
                    + 'applied.') });
            }
            if (lm.end_force_n !== null) {
                s.push({ ad: 'end_force', metin: TF('fea.loadModelEndForce',
                    { kn: fmt(lm.end_force_n / N_PER_KN, 2) },
                    'Closed-end axial force {kn} kN applied at the free end '
                    + '(equivalent of the closed volume under P_c).') });
            }
            if (lm.pressure_only) {
                s.push({ ad: 'scope', metin: T('fea.loadModelScopePressureOnly',
                    'Load scope: PRESSURE LOADING ONLY — thermal load and '
                    + 'temperature-dependent strength are outside this '
                    + 'result.') });
            }
            if (lm.balance && lm.balance.measured) {
                s.push({ ad: 'force_balance', metin: lm.balance.holds
                    ? TF('fea.loadModelBalanceHolds',
                        { err: lm.balance.rel_error.toExponential(2),
                          tol: lm.balance.tol.toExponential(0) },
                        'Force balance holds: FEA support reaction vs analytic '
                        + 'net axial pressure force, relative error {err} '
                        + '(tolerance {tol}).')
                    : TF('fea.loadModelBalanceFails',
                        { err: lm.balance.rel_error.toExponential(2),
                          tol: lm.balance.tol.toExponential(0) },
                        'Force balance DOES NOT HOLD: FEA support reaction vs '
                        + 'analytic net axial pressure force, relative error '
                        + '{err} exceeds the tolerance {tol}.') });
            } else if (lm.balance && lm.balance.measured === false) {
                s.push({ ad: 'force_balance', metin: T(
                    'fea.loadModelBalanceNotMeasured',
                    'Force balance NOT MEASURED (no support reaction or '
                    + 'analytic net force was available).') });
            }
        }
        const pb = vm.peak_band;
        if (pb) {
            s.push({ ad: 'peak_band', metin: TF('fea.peakInLoadBand',
                { sf: fmt(pb.peak_safety_factor, 2),
                  z: fmt(pb.z_m * MM_PER_M, 1), r: fmt(pb.r_m * MM_PER_M, 1),
                  end: pb.end, dsv: fmt(pb.d_sv_m * MM_PER_M, 1) },
                'Diagnosis (not a verdict): the raw peak safety factor {sf} '
                + 'sits at z = {z} mm, r = {r} mm, inside the load-application '
                + 'band of the {end} end (within d_SV = {dsv} mm): it is the '
                + 'footprint of the equivalent end load; the verdict is taken '
                + 'outside this band.') });
        }
        return s;
    }

    function hidePlots(els) {
        ['vm', 'sf', 'quality', 'conv'].forEach(function (k) {
            if (els[k]) els[k].style.display = 'none';
        });
        if (els.qualityNote) els.qualityNote.innerHTML = '';
        if (els.convNote) els.convNote.innerHTML = '';
    }

    // ------------------------------------------------------------------
    // BOYACI (paintStructural) — TEK çizim yolu.
    // ------------------------------------------------------------------
    // 2026-08-18 (parti 34): bu işlev eskiden render()'ın gövdesiydi ve
    // elemanlarını KENDİSİ getElementById ile buluyordu. Analiz Merkezi
    // kiracısı aynı çıktıyı BAŞKA bir kapta (Merkez'in görüntüleyici kökü)
    // çizmek zorunda; kopya çizim yazmak yerine işlev eleman haritasıyla
    // parametreleştirildi. Standalone panel de kiracı da AYNI boyacıdan
    // geçer — ayrışma olursa bit-aynılık bekçisi kırmızı yanar
    // (tests/test_fea_merkez_kiracilari.py::TestRenderReuse).
    //   els     : eleman haritası (yoksa alan çizilmez, kap sorulmaz)
    //   vm      : buildViewModel çıktısı
    //   isBusy  : koşum sürüyor mu (Merkez'de kendi durum satırı vardır,
    //             kiracı bu yüzden els.busy VERMEZ)
    function paintStructural(els, vm, isBusy) {
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Belirsiz süreli iş: yüzde YOK (sahte ilerleme yasak), ama
            // GEÇEN SÜRE ve SÜRE SINIRI yazılır — P17B1-18: eski satır
            // gerekçesiz, süresiz ve SONSUZDU.
            mesgulYaz('structural', els.busy, isBusy, busySince,
                T('fea.busy', 'Running — the solver refines the mesh until the '
                    + 'peak stress stops changing; the duration is not known in '
                    + 'advance.'),
                function (gecen, sinir) {
                    return TF('fea.busyElapsed', { s: gecen, limit: sinir },
                        'Elapsed {s} s; the request is cancelled after {limit} s.');
                });
        }
        // P11B3-19 — iptal düğmesi YALNIZ koşum sürerken görünür.
        iptalDugmesiniGoster(els.cancel, isBusy);

        if (vm.mode !== 'ok') {
            hidePlots(els);
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = isBusy ? '' : chipHtml(
                    T('fea.chipIdle',
                      'NOT RUN YET — press "Run structural analysis" to solve the '
                      + 'wall of the current result'), '');
            } else if (vm.mode === 'not_modelled') {
                const missing = vm.missing.length
                    ? TF('fea.missingList', { list: vm.missing.join(', ') },
                         'Missing inputs: {list}')
                    : '';
                els.chip.innerHTML = chipHtml(
                    T('fea.chipNotModelled',
                      'NOT MODELLED — the solver result does not carry the inputs '
                      + 'the FEA needs; nothing is drawn'),
                    [missing, vm.reason, notModelledDetay(vm)]
                        .filter(Boolean).join('\n'));
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    T('fea.chipError', 'RUN FAILED — no field is drawn'), vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    T('fea.chipInvalid',
                      'DATA INCONSISTENT — the response carries no usable mesh grid; '
                      + 'nothing is plotted'), '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            hidePlots(els);
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                T('fea.chipGridMismatch',
                  'MESH INCONSISTENT — the node grid does not match the declared '
                  + 'node count; nothing is plotted'), '');
            return;
        }

        // Her basımda yedek bayrağı sıfırlanır: geçmişte bir kez carpet
        // çizilemediyse bu, sonraki basımda da öyle olduğu anlamına gelmez.
        carpetFallback = false;
        els.chip.innerHTML = '';
        renderBadges(els.badges, vm);
        renderBasis(els, vm);

        // von Mises alanı
        if (vm.von_mises_mpa) {
            els.vm.style.display = 'block';
            const title = T('fea.chartVm',
                'von Mises stress on the axisymmetric wall section [MPa]');
            const cbar = T('fea.cbarVm', 'von Mises [MPa]');
            try {
                drawFigure(els.vm, fieldFigure(vm, vm.von_mises_mpa, title, cbar,
                                               VM_COLORSCALE, 'feaCarpetVm'));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.vm, fieldFallbackFigure(vm, vm.von_mises_mpa,
                                                       title, cbar, VM_COLORSCALE));
                renderBadges(els.badges, vm);
            }
        } else {
            els.vm.style.display = 'none';
        }

        // Emniyet katsayısı alanı — yayımlanmadıysa GRAFİK YOK
        if (vm.safety_factor) {
            els.sf.style.display = 'block';
            const title = T('fea.chartSf',
                'Safety factor field (yield / von Mises) [-]');
            // P11B3-04: renk ölçeğinin MUTLAK olduğu ve nerede doyduğu
            // renk çubuğunun kendi başlığında yazar — kullanıcı kırmızının
            // "en düşük" değil "akma aşıldı" demek olduğunu okumadan
            // haritaya bakmasın.
            const cbar = TF('fea.cbarSfAnchored',
                { err: fmt(SF_ERR_MAX, 1), ok: fmt(SF_OK_MIN, 1),
                  max: fmt(SF_SCALE_MAX, 1) },
                'Safety factor [-] — absolute scale: red below {err}, '
                + 'green from {ok}, saturated at {max}');
            try {
                drawFigure(els.sf, sfFieldFigure(vm, vm.safety_factor, title,
                                                 cbar, 'feaCarpetSf'));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.sf, sfFieldFallbackFigure(vm, vm.safety_factor,
                                                         title, cbar));
                renderBadges(els.badges, vm);
            }
        } else {
            els.sf.style.display = 'none';
        }

        // Eleman kalite haritası
        const qFig = qualityFigure(vm);
        if (qFig) {
            els.quality.style.display = 'block';
            drawFigure(els.quality, qFig);
            if (els.qualityNote) {
                const th = vm.flags.thresholds;
                const c = vm.flags.counts;
                let qn = TF('fea.qualityNote',
                    { arMax: th.aspect_ratio_max, sjMin: th.scaled_jacobian_min,
                      bad: c.any, total: c.total },
                    'Acceptable range: aspect ratio <= {arMax} and scaled '
                    + 'Jacobian >= {sjMin}; {bad} of {total} elements are '
                    + 'outside it. Thresholds and metric definitions come from '
                    + 'the server; see the basis note below.');
                // Rozetlerdeki ayrışmanın aynısı harita altında da yazar:
                // birleşik sayı tek başına hangi ölçütün bayrak çektiğini
                // söylemiyordu.
                qn += ' ' + TF('fea.qualityBreakdown',
                    { aspect: c.aspect, jac: c.jacobian },
                    'Of that count {aspect} are flagged by the aspect-ratio '
                    + '(elongation) rule and {jac} by scaled-Jacobian '
                    + 'distortion; only the distortion count is a quality '
                    + 'alarm.');
                if (c.any === c.total && c.total > 0) {
                    qn += ' ' + T('fea.qualityAllFlagged',
                        'Every element is outside the range, so the red overlay '
                        + 'is omitted — it would cover the whole map without '
                        + 'telling you anything. Read the colour scale instead: '
                        + 'it shows where the metric is worst.');
                } else if (c.any > 0) {
                    qn += ' ' + T('fea.qualityRingNote',
                        'Elements outside the range are ringed in red.');
                }
                els.qualityNote.innerHTML = esc(qn);
            }
        } else {
            els.quality.style.display = 'none';
            if (els.qualityNote) els.qualityNote.innerHTML = '';
        }

        // Yakınsama
        const conv = vm.convergence;
        if (conv && conv.n_elems.length >= 2) {
            els.conv.style.display = 'block';
            drawFigure(els.conv, convergenceFigure(conv));
        } else {
            els.conv.style.display = 'none';
        }
        if (els.convNote) {
            let note = '';
            if (conv && conv.meshes) {
                note += esc(conv.converged
                    ? TF('fea.convText',
                         { n: conv.refinements,
                           pct: fmt(conv.final_rel_change_pct, 2),
                           tol: fmt(conv.tol_pct, 2) },
                         'Converged in {n} refinement rounds: the peak von Mises '
                         + 'changed by {pct}% between the last two meshes '
                         + '(tolerance {tol}%).')
                    : TF('fea.convTextNo',
                         { n: conv.refinements,
                           pct: fmt(conv.final_rel_change_pct, 2),
                           tol: fmt(conv.tol_pct, 2) },
                         'NOT converged: after {n} refinement rounds the peak von '
                         + 'Mises still changed by {pct}% between the last two '
                         + 'meshes (tolerance {tol}%). Read the result with this '
                         + 'in mind.'));
            }
            // P11B3-03: EKRANDAKİ İKİ SAYI ADIYLA AYRIŞIR. Rozet ve bu
            // notun 'tur' sayısı ÇÖZÜLEN MESH sayısıdır (ucun kendi beyan
            // metninin de kullandığı sayı); ucun katlama sayacı ise
            // noktalar ARASINDAKİ inceltme adımlarını sayar ve bu yüzden
            // bir eksiktir. İkisi yazılmazsa kullanıcı 4 ile 3'ü çelişki
            // sanır (kusurun kaynağı buydu).
            if (conv && conv.meshes) {
                note += (note ? ' ' : '') + esc(TF('fea.convMeshCount',
                    { m: conv.meshes, r: conv.refinements },
                    '{m} meshes were solved, so {r} refinement steps lie '
                    + 'between them: the round count above counts MESHES '
                    + '(the same number the endpoint calls "tur" in its '
                    + 'declaration below), while the endpoint\'s folding '
                    + 'counter counts the STEPS. The chart draws one point '
                    + 'per mesh.'));
            }
            //: P11B3-13 — İNCELTMENİN YÖNÜ YAZILIR. Grafiğin x ekseni
            //: TOPLAM eleman sayısıdır; artışın hangi yönden geldiği
            //: oradan okunamaz. Sayılar yükten gelir (n_axial / n_radial),
            //: panel yalnız ARTIŞ olan adımları sayar. Alan yoksa satır
            //: hiç yazılmaz.
            if (conv && conv.yon_katlama) {
                const yk = conv.yon_katlama;
                const ilkA = conv.n_axial[0], sonA = conv.n_axial[conv.n_axial.length - 1];
                const ilkR = conv.n_radial[0], sonR = conv.n_radial[conv.n_radial.length - 1];
                note += (note ? ' ' : '') + esc(
                    'n_axial: ' + ilkA + ' -> ' + sonA
                    + ' (' + yk.eksenel + ' refinements), '
                    + 'n_radial: ' + ilkR + ' -> ' + sonR
                    + ' (' + yk.radyal + ' refinements).');
                if (yk.eksenel === 0 || yk.radyal === 0) {
                    const durgun = yk.eksenel === 0 ? 'n_axial' : 'n_radial';
                    note += ' ' + esc(
                        'The element count on the x axis grew in ONE direction '
                        + 'only: ' + durgun + ' was never refined, so the chart '
                        + 'is not a uniform-refinement study.');
                }
            }
            //: Son turun karar gerekçesi (yön göstergeleri + iki sonda
            //: çözümü) yükte var ve okunmuyordu; olduğu gibi basılır.
            if (conv && conv.karar && typeof conv.karar.gerekce === 'string') {
                note += (note ? ' ' : '') + esc(SRV(conv.karar.gerekce));
            }
            if (conv && conv.beyan) {
                note += (note ? ' ' : '') + esc(SRV(conv.beyan));
            }
            els.convNote.innerHTML = note;
        }
    }

    // Standalone panelin eleman haritası — panelHtml()'in kimlikleri.
    function structuralEls() {
        return {
            badges: document.getElementById('fea_badges'),
            chip: document.getElementById('fea_chip'),
            busy: document.getElementById('fea_busy'),
            cancel: document.getElementById('fea_cancel'),
            vm: document.getElementById('fea_plot_vm'),
            sf: document.getElementById('fea_plot_sf'),
            quality: document.getElementById('fea_plot_quality'),
            qualityNote: document.getElementById('fea_quality_note'),
            conv: document.getElementById('fea_plot_conv'),
            convNote: document.getElementById('fea_conv_note'),
            basis: document.getElementById('fea_basis'),
            basisText: document.getElementById('fea_basis_text'),
        };
    }

    function render() {
        paintStructural(structuralEls(),
                        buildViewModel(lastPayload, lastError), busy);
    }

    // ------------------------------------------------------------------
    // Koşum
    // ------------------------------------------------------------------
    // Sayfa sözlüğünden MOTOR sözlüğü: hibrit sayfada sonuç {motor:{...}}
    // sarmalıdır, sıvı/katı sayfalarda üst düzey sözlüğün kendisidir
    // (uç docstring'i: app.py api_fea_structural). Kural TEK yerde durur —
    // Merkez kiracısı da bu işlevi çağırır, ikinci bir "motor || results"
    // deyimi yazılmaz.
    function motorDictOf(results) {
        if (!results || typeof results !== 'object') return null;
        return results.motor || results;
    }

    function pickMotorResults() {
        if (typeof cfg.resultsProvider === 'function') {
            try {
                const r = cfg.resultsProvider();
                if (r && typeof r === 'object') return r;
            } catch (e) { /* sağlayıcı patlarsa genel yola düş */ }
        }
        if (lastMotorResults && typeof lastMotorResults === 'object') {
            return motorDictOf(lastMotorResults);
        }
        return motorDictOf(window.currentResults);
    }

    function run() {
        if (busy) return Promise.resolve(null);
        const motor = pickMotorResults();
        if (!motor) {
            lastPayload = null;
            lastError = T('fea.noResult',
                'No motor result on this page yet — run the motor calculation first.');
            render();
            return Promise.resolve(null);
        }
        busy = true;
        busySince = Date.now();
        lastError = null;
        render();
        return fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motor_results: motor }),
            // P17B4-07: ürünün kendi deseni (şablonlardaki
            // AbortSignal.timeout) bu panele de uygulandı.
            // P11B3-19: aynı sinyale KULLANICI İPTALİ de bağlandı.
            signal: kosumSinyali('structural'),
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            busy = false;
            busySince = null;
            kosumBitti('structural');
            if (!r.ok || !r.body || r.body.status !== 'success') {
                lastPayload = null;
                lastError = (r.body && (r.body.detail || r.body.error))
                    || T('fea.httpError', 'The structural FEA endpoint returned an error.');
            } else {
                lastPayload = r.body.fea || null;
                lastError = null;
            }
            render();
            return lastPayload;
        }).catch(function (e) {
            const gecen = busySince
                ? Math.round((Date.now() - busySince) / 1000) : null;
            const iptalEdildi = kullaniciIptaliMi('structural');
            busy = false;
            busySince = null;
            kosumBitti('structural');
            lastPayload = null;
            // P17B1-18 — SESSİZ DÜŞÜŞ YOK: zaman aşımı kendi adıyla,
            // geçen süresiyle ve ne yapılabileceğiyle beyan edilir.
            // Cümle uydurulmaz; sınır yukarıdaki tek kaynaktan gelir.
            // P11B3-19 — KULLANICI DURDURDUYSA ÖYLE SÖYLENİR: aynı
            // 'AbortError' iki ayrı olaydan gelebilir ve ikisi aynı
            // cümleyle anlatılamaz (biri arıza, öteki kullanıcının kendi
            // kararı).
            lastError = iptalEdildi
                ? TF('fea.cancelled', { s: gecen === null ? 0 : gecen },
                     'You stopped the structural FEA run after {s} s. Nothing '
                     + 'was computed and no result was changed.')
                : zamanAsimiMi(e)
                ? TF('fea.timeout',
                     { s: gecen === null ? Math.round(ISTEK_ZAMAN_ASIMI_MS / 1000)
                                         : gecen },
                     'The structural FEA run was cancelled after {s} s without a '
                     + 'reply from the solver. Nothing was computed. Try a coarser '
                     + 'mesh or fewer refinement rounds, then run it again.')
                : String((e && e.message) || e);
            render();
            return null;
        });
    }

    // Yeni motor sonucu geldi: eski FEA çıktısı BAYATTIR, silinir.
    function update(results) {
        lastMotorResults = results || null;
        if (lastPayload) {
            lastPayload = null;
            lastError = null;
        }
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

        const runBtn = document.getElementById('fea_run');
        if (runBtn) runBtn.addEventListener('click', function () { run(); });
        // P11B3-19 — iptal düğmesi: koşumu DURDURUR, sayfayı yenilemez.
        const cancelBtn = document.getElementById('fea_cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', function () {
            kosumuIptalEt('structural');
        });
        const meshBox = document.getElementById('fea_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                showMesh = !!meshBox.checked;
                render();
            });
        }
        const metricSel = document.getElementById('fea_metric');
        if (metricSel) {
            metricSel.addEventListener('change', function () {
                qualityMetric = metricSel.value || 'aspect_ratio';
                render();
            });
        }

        // Hesap köprüsü: blowdown_panel.js ile AYNI desen. Özgün işlev her
        // koşulda çalışır; panel hatası hesap gösterimini engellemez.
        (function () {
            const original = window.displayCalculationResults;
            if (typeof original !== 'function') return;
            window.displayCalculationResults = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('FEA panel update failed:', e);
                }
                return out;
            };
        })();

        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        render();
    }

    window.FeaPanel = {
        init: init,
        update: update,
        run: run,
        buildViewModel: buildViewModel,
        setShowMesh: function (v) { showMesh = !!v; render(); },
        setQualityMetric: function (m) { qualityMetric = m; render(); },
        applyPayload: function (fea, error) {
            lastPayload = fea || null;
            lastError = error || null;
            busy = false;
            render();
        },
        get payload() { return lastPayload; },
        // Test / hata ayıklama yüzeyi (DOM'suz koşulabilir saf katman;
        // GrainFeaPanel'in FeaCenterTenants yüzeyiyle aynı desen).
        // P11B3-04 bekçisi renk ölçeğinin MUTLAK çapasını buradan ölçer.
        _fieldFigure: fieldFigure,
        _fieldFallbackFigure: fieldFallbackFigure,
        _sfFieldFigure: sfFieldFigure,
        _sfFieldFallbackFigure: sfFieldFallbackFigure,
        _sfScale: {
            colorscale: SF_COLORSCALE,
            zLimits: SF_Z_LIMITS,
            errMax: SF_ERR_MAX,
            okMin: SF_OK_MIN,
            scaleMax: SF_SCALE_MAX,
            //: ÖH D20 · P11B3-04 (Fable-D18 ŞARTI) — rozet eşiği ile
            //: harita eşiği TEK KAPIDAN okunur. Eşik kararı burada dışa
            //: vurulmadıkça bekçi yalnız SABİTLERİ (errMax/okMin)
            //: görebiliyordu; sabitler yerinde dururken karar satırındaki
            //: gömülü sayıya kaymak (`sf < 1.2`) ölçülemiyordu.
            badgeKind: sfRozetTuru,
        },
        //: Rozet HTML'inin ürün kapısı — bekçi eşik sınırını saf
        //: fonksiyondan DEĞİL ekrana basılan `data-badge`'den de okur
        //: (iki yol ayrışırsa kullanıcı haritayla çelişen rozet görür).
        _renderBadges: renderBadges,
        //: P11B3-13 bekçisi: yakınsama görünüm modeli + grafiği saf
        //: katmandan ölçer (yön künyesi ve rel_change izi).
        _buildConvergence: buildConvergence,
        _convergenceFigure: convergenceFigure,
        //: V3 KK 2. tur (FY devri) bekçisi: yük modeli künyesi satırları ve
        //: künye bölümüne textContent ile eklenişi.
        _renderBasis: renderBasis,
        _yukModeliSatirlari: yukModeliSatirlari,
    };

    // ==================================================================
    // GrainFeaPanel — KATI TANE KESİTİ düzlemsel FEA paneli (V2.7 Aşama C)
    // ------------------------------------------------------------------
    // Katı sayfasında (solid.html) yaşar; POST /api/fea/planar-grain
    // yanıtını çizer. Kamara cidarı panelinden (FeaPanel) farkları:
    //   * kesit (x, y) düzlemidir, eksenler EŞİT ölçeklenir (fiziksel
    //     kesit çarpıtılmaz);
    //   * emniyet katsayısı alanı YOKTUR — katı tane kabul ölçütü
    //     GERİNİMDİR (NASA SP-8073): port lif gerinimi kopma uzamasıyla
    //     oranlanır ve ayrı grafikte basılır;
    //   * kesit parametreleri sayfanın SON HESAP SONUCUNDAN okunur
    //     (paramsProvider) — panel geometri üretmez, uydurma değer yok.
    // Metinler init({labelsProvider}) üzerinden i18n_pages.js'ten gelir
    // (solid.* anahtarları); sağlayıcı yoksa İngilizce yedekler kullanılır.
    // Sahte veri yasağı FeaPanel ile aynı: NOT_MODELLED'da çizim yok,
    // yeni hesap eski alanı siler, belirsiz süreli koşuda yüzde yok.
    // ==================================================================

    let gCfg = {};
    let gLastPayload = null;
    let gLastError = null;
    let gBusy = false;
    let gBusySince = null;     // koşumun başlangıç damgası (P17B1-18)
    let gShowMesh = true;
    let gLabels = {};

    const GRAIN_ENDPOINT = '/api/fea/planar-grain';

    function GL(name, fallback) {
        const v = gLabels && gLabels[name];
        return (typeof v === 'string' && v) ? v : fallback;
    }

    function gFmtTpl(tpl, params) {
        return String(tpl).replace(/\{(\w+)\}/g, function (whole, key) {
            return (params && key in params) ? String(params[key]) : whole;
        });
    }

    // Port gerinim payı sınıflaması — motorun KENDİ risk sınıflamasıyla
    // aynı eşikler (solid_rocket_engine._calculate_grain_structural:
    // >=2 Low, >=1 Medium, <1 High). TEK tanım yeri: hem standalone rozet
    // hem Merkez kiracısının hükmü buradan geçer (parti 34).
    function strainMarginKind(margin) {
        return margin < 1 ? 'err' : (margin < 2 ? 'warn' : 'ok');
    }

    // ------------------------------------------------------------------
    // KESİT PARAMETRELERİ — sonuç sözlüğünden ucun alan adlarına.
    // ------------------------------------------------------------------
    // Kaynak: motorun YAYIMLADIĞI grain_design bloğu (yoksa üst düzey
    // alanlar). Panel geometri ÜRETMEZ; hiçbir sayı uydurulmaz, boş/eksik
    // anahtar gövdeden DÜŞER. Uç, motor arayüzünün kendi alan adlarını
    // bekler (star_radius = uç derinliği mm) — çeviri katmanı yoktur.
    //
    // İKİZ UYARISI: solid.html içindeki grainFeaParams() bu işlevin
    // kopyasıdır (şablon bu partinin dosya kapsamı dışındaydı). Bekçi
    // ikisini AYNI sonuç sözlüğüyle koşturup birebir eşitlik arar; şablon
    // bu işlevi çağıracak şekilde sadeleştirilene kadar ikizlik ölçülür.
    function grainParamsFromResults(results) {
        const r = results;
        if (!r || typeof r !== 'object') return null;
        const gd = (r.grain_design && typeof r.grain_design === 'object')
            ? r.grain_design : {};
        const tip = gd.grain_type || r.grain_type;
        if (!tip) return null;
        const p = {
            grain_type: tip,
            propellant_type: r.propellant_type,
            outer_diameter_mm: (gd.outer_diameter_mm != null)
                ? gd.outer_diameter_mm : r.chamber_diameter,
            core_diameter_mm: (gd.inner_diameter_mm != null)
                ? gd.inner_diameter_mm : r.core_diameter,
            chamber_pressure_bar: r.chamber_pressure,
            grain_length_mm: (gd.grain_length_mm != null)
                ? gd.grain_length_mm : r.grain_length,
        };
        if (tip === 'star') {
            p.star_points = gd.star_points;
            p.star_radius = gd.point_depth;
        } else if (tip === 'finocyl') {
            p.fin_count = gd.fin_count;
            p.fin_width = gd.fin_width_mm;
            p.fin_length = gd.fin_depth_mm;
            p.finned_length_fraction = gd.finned_length_fraction;
        } else if (tip === 'slotted') {
            p.slot_count = gd.slot_count;
            p.slot_width = gd.slot_width_mm;
            p.slot_depth = gd.slot_depth_mm;
        }
        Object.keys(p).forEach(function (k) {
            if (p[k] === null || p[k] === undefined || p[k] === '') {
                delete p[k];
            }
        });
        return p;
    }

    // ------------------------------------------------------------------
    // >>> GRAIN_FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; tek dönüşümler Pa→MPa bölmesi
    // ve gerinim→% çarpımı, ikisi de beyanlıdır.
    // ------------------------------------------------------------------
    /* Yayımlanmış düğüm dizisinin maksimumu (Pa → MPa). Dizi yoksa ya da
       sonlu bir üye taşımıyorsa null döner — uydurma yok (P11B3-23). */
    function enBuyuk(dizi) {
        if (!Array.isArray(dizi)) return null;
        let m = null;
        for (let i = 0; i < dizi.length; i++) {
            const v = dizi[i];
            if (isNum(v) && (m === null || v > m)) m = v;
        }
        return (m === null) ? null : m / PA_PER_MPA;
    }

    function buildGrainViewModel(fea, errorText) {
        if (errorText) return { mode: 'error', error: String(errorText) };
        if (!fea || typeof fea !== 'object') return { mode: 'idle' };
        if (fea.status !== 'ok') {
            return {
                mode: 'not_modelled',
                status: fea.status || null,
                reason: (typeof fea.reason === 'string') ? fea.reason : '',
                warning: fea.warning || null,
                grain_type: fea.grain_type || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const bore = fea.bore || {};

        // Port gerinim eğrisi: istasyon açısı düğüm koordinatından (derece),
        // gerinim % — başka işlem yok.
        let boreCurve = null;
        if (Array.isArray(bore.node_ids) && Array.isArray(bore.strain_nodal)
                && bore.node_ids.length === bore.strain_nodal.length
                && Array.isArray(mesh.nodes)) {
            const thetaDeg = [], strainPct = [];
            for (let k = 0; k < bore.node_ids.length; k++) {
                const n = mesh.nodes[bore.node_ids[k]];
                if (!Array.isArray(n)) { boreCurve = null; break; }
                thetaDeg.push(Math.atan2(n[1], n[0]) * 180.0 / Math.PI);
                strainPct.push(isNum(bore.strain_nodal[k])
                    ? 100.0 * bore.strain_nodal[k] : null);
                boreCurve = { theta_deg: thetaDeg, strain_pct: strainPct };
            }
        }

        const vm = {
            mode: 'ok',
            grain_type: fea.grain_type || null,
            symmetry_fraction: isNum(fea.symmetry_fraction)
                ? fea.symmetry_fraction : null,
            grid: grid,
            von_mises_mpa: fieldToGrid(mesh, fields.von_mises_pa, PA_PER_MPA),
            wireframe: buildWireframe(mesh),
            // ÖH D30 · P11B3-26 — ÖLÜ HESAP SÖKÜLDÜ.
            // ÖLÇÜLDÜ (a2/once.json: P11B3-26_elementCentres_cagri = 2,
            // tüketici `vm.centres` yalnız YAPISAL boyacıda):
            // `elementCentres` tane ağı için eleman başına iki sayı
            // üretiyordu (bu ağda 24.576 eleman → 49.152 sayı) ama tane
            // görünümünün tek tüketicisi yoktu: `centres`i okuyan iki işlev
            // (`badElementsTrace`, `qualityFigure`) YAPISAL görünümün
            // boyacısından çağrılır (`paintStructural`), tane boyacısından
            // değil. Yapısal görünüm hesabı KORUR (orada tüketicisi var).
            quality: fea.quality || null,
            flags: qualityFlags(fea.quality),
            convergence: buildConvergence(fea.convergence),
            bore_curve: boreCurve,
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_theta: mesh.n_theta, n_radial: mesh.n_radial,
                units: mesh.coordinate_units || null,
            },
            scalars: {
                von_mises_gauss_max_mpa: isNum(scalars.von_mises_gauss_max_pa)
                    ? scalars.von_mises_gauss_max_pa / PA_PER_MPA : null,
                von_mises_nodal_max_mpa: isNum(scalars.von_mises_nodal_max_pa)
                    ? scalars.von_mises_nodal_max_pa / PA_PER_MPA : null,
                /* ÖH D26 · P11B3-23 — MAKS ASAL GERİLME EKRANA ÇIKAR.

                   ÖLÇÜLDÜ (a3/once.json, taban 7751531):
                     sunucu_max_principal_yayini = 1
                     panel_max_principal_okumasi = 0
                   Uç `fields.max_principal_pa` alanını (düğüm dizisi)
                   yayımlıyor, panel adını BİR KEZ bile anmıyordu. Katı
                   yakıtta kopma ölçütünün doğal büyüklüğü ASAL çekme
                   gerilmesidir (von Mises deviatorik bir ölçüdür ve
                   hidrostatik çekmeyi görmez); tane kesitinde bu sayı
                   ekranda yoktu.

                   Yeni SAYI TÜRETİLMEZ: ucun yayımladığı düğüm dizisinin
                   maksimumu alınır ve rozet bunun ne olduğunu ADIYLA
                   söyler (dizi yoksa null → rozet basılmaz). */
                max_principal_max_mpa: enBuyuk(fields.max_principal_pa),
                max_bore_strain_pct: isNum(bore.max_strain)
                    ? 100.0 * bore.max_strain : null,
                strain_capability_pct: isNum(bore.strain_capability)
                    ? 100.0 * bore.strain_capability : null,
                strain_margin: isNum(bore.strain_margin)
                    ? bore.strain_margin : null,
            },
            warnings: Array.isArray(fea.warnings) ? fea.warnings : [],
            limits: fea.limits || null,
            not_modelled: (fea.meta && Array.isArray(fea.meta.not_modelled))
                ? fea.meta.not_modelled : [],
            basis: {
                fields: (fields && fields._basis) || null,
                bore: (bore && bore._basis) || null,
                inputs: (fea.meta && fea.meta.girdiler) || null,
                quality: (fea.quality && fea.quality._basis) || null,
                // ÖH D31 · P11B3-27 — ÖLÇÜM KODUNUN KİMLİĞİ DE TAŞINIR.
                // ÖLÇÜLDÜ (a1/once.json · M8): uç `quality._source` ile
                // metrikleri HANGİ işlevin ürettiğini yazıyor
                // (app.py:21826 'hrma.app._fea_quad_quality') ama panel
                // yalnız `_basis` cümlesini alıyordu: kullanıcı tanımı
                // görüyor, tanımı UYGULAYAN kodu göremiyordu. Alan
                // gelmezse null (uydurma kimlik yazılmaz).
                quality_source: (fea.quality && fea.quality._source) || null,
            },
        };
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    // <<< GRAIN_FEA_VIEWMODEL_END
    // ------------------------------------------------------------------

    function grainPanelHtml() {
        return `
        <div class="panel" id="grainFeaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2 id="grainfea_title">${esc(GL('title',
                'Grain Section FEA — Plane-Strain Stress and Bore Strain'))}</h2>
            <div class="chart-explanation">
                <span id="grainfea_intro">${esc(GL('intro',
                    'A 2D plane-strain finite element run on the propellant grain '
                    + 'cross-section of THIS design (star, finocyl and slotted ports '
                    + 'are not axisymmetric, so the wall solver cannot see them). '
                    + 'The section polygon is built on the server from the motor '
                    + 'solver itself; the acceptance quantity is the bore surface '
                    + 'STRAIN against the propellant strain capability. If an input '
                    + 'is missing, nothing is drawn and the reason is named.'))}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="grainfea_run" class="btn" type="button">${esc(GL('run',
                    'Run grain section FEA'))}</button>
                <span id="grainfea_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                ${iptalDugmesiHtml('grainfea_cancel', GL('cancel', 'Cancel run'))}
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="grainfea_show_mesh" checked>
                    <span id="grainfea_mesh_label">${esc(GL('showMesh', 'Show mesh wireframe'))}</span>
                </label>
            </div>
            <div id="grainfea_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="grainfea_chip" style="margin:8px 0;"></div>
            <div id="grainfea_plot_vm" class="plot-container" style="min-height:380px; display:none;"></div>
            <div id="grainfea_plot_bore" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="grainfea_plot_conv" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="grainfea_conv_note" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="grainfea_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    id="grainfea_basis_title">${esc(GL(
                    'basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)'))}</summary>
                <div id="grainfea_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></div>
            </details>
        </div>`;
    }

    function grainWireTrace(vm) {
        const w = vm.wireframe;
        return {
            x: w.x, y: w.y, mode: 'lines', type: 'scatter',
            line: { color: MESH_COLOR, width: 1 },
            name: gFmtTpl(GL('meshTrace', 'Mesh ({n} elements)'),
                          { n: vm.mesh_info.n_elems }),
            hoverinfo: 'skip',
        };
    }

    function grainFieldFigure(vm) {
        const g = vm.grid;
        const cbar = GL('cbarVm', 'von Mises [MPa]');
        const traces = [{
            type: 'carpet', carpet: 'grainCarpetVm',
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, {
            type: 'contourcarpet', carpet: 'grainCarpetVm',
            a: g.a, b: g.b, z: vm.von_mises_mpa,
            contours: { coloring: 'fill', showlines: false },
            colorscale: VM_COLORSCALE,
            colorbar: { title: cbar, titleside: 'right' },
            name: cbar,
        }];
        if (gShowMesh && vm.wireframe) traces.push(grainWireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: GL('chartVm',
                    'von Mises stress on the grain cross-section [MPa]'),
                xaxis: { title: GL('axisX', 'x [m]') },
                // Fiziksel kesit: eksenler EŞİT ölçekli (çarpıtma yok).
                yaxis: { title: GL('axisY', 'y [m]'),
                         scaleanchor: 'x', scaleratio: 1 },
                height: 380,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği (eski Plotly): düğüm nokta haritası — FeaPanel deseni.
    function grainFieldFallbackFigure(vm) {
        const g = vm.grid;
        const cbar = GL('cbarVm', 'von Mises [MPa]');
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]);
                c.push(vm.von_mises_mpa[j][i]);
            }
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: c, colorscale: VM_COLORSCALE, size: 6,
                      colorbar: { title: cbar, titleside: 'right' } },
            name: cbar,
        }];
        if (gShowMesh && vm.wireframe) traces.push(grainWireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: GL('chartVm',
                    'von Mises stress on the grain cross-section [MPa]'),
                xaxis: { title: GL('axisX', 'x [m]') },
                yaxis: { title: GL('axisY', 'y [m]'),
                         scaleanchor: 'x', scaleratio: 1 },
                height: 380,
                showlegend: false,
            },
        };
    }

    function grainBoreFigure(vm) {
        const bc = vm.bore_curve;
        const traces = [{
            x: bc.theta_deg, y: bc.strain_pct,
            mode: 'lines+markers', type: 'scatter',
            marker: { size: 6 }, line: { width: 2 },
            name: GL('boreTrace', 'Bore fibre strain [%]'),
        }];
        const cap = vm.scalars.strain_capability_pct;
        if (isNum(cap)) {
            traces.push({
                x: [Math.min.apply(null, bc.theta_deg),
                    Math.max.apply(null, bc.theta_deg)],
                y: [cap, cap],
                mode: 'lines', type: 'scatter',
                line: { color: BAD_COLOR, width: 2, dash: 'dash' },
                name: GL('capTrace', 'Strain capability [%]'),
            });
        }
        //: ÖH D29 · P11B3-17 — KABUL GRAFİĞİ KAPASİTE ÇİZGİSİYLE EZİLMEZ.
        //: ÖLÇÜLDÜ (P11 kaydı, a3/once.json yeniden oynatması): port lif
        //: gerinimi -0,1393 % … +0,8414 %, kapasite %35,0 — ikisi AYNI
        //: doğrusal eksende çizilince gerinim eğrisi eksenin %2,8'ine
        //: sıkışıyor ve grafiğin TEK amacı olan dağılım düz çizgi
        //: görünüyordu. Kapasite çizgisi SİLİNMEZ (kabul ölçütüdür); eksen
        //: gerinim bandına oturur, kapasite ölçek dışına düşerse bu ADIYLA
        //: yazılır ve pay sayıyla verilir. Hiçbir sayı uydurulmaz:
        //: eşik (BORE_EKSEN_PAYI) bir GÖRÜNÜRLÜK kararıdır, fizik değil.
        const boreRange = boreEksenAraligi(bc.strain_pct, cap);
        const layout = {
            title: GL('chartBore',
                'Bore surface strain along the port (acceptance quantity)'),
            xaxis: { title: GL('axisTheta', 'Station angle [deg]') },
            yaxis: { title: GL('axisStrain', 'Strain [%]') },
            height: 300,
            legend: { orientation: 'h', y: 1.16 },
        };
        if (boreRange) {
            layout.yaxis.range = boreRange.range;
            layout.annotations = [{
                xref: 'paper', yref: 'paper', x: 0, y: 1.0,
                xanchor: 'left', yanchor: 'bottom', showarrow: false,
                font: { size: 10, color: BAD_COLOR },
                text: 'strain_capability_pct = ' + cap
                    + ' % — off scale (peak/capability = '
                    + boreRange.kapasiteOlcekDisi.toFixed(4) + ')',
            }];
        }
        return { traces: traces, layout: layout };
    }

    //: P11B3-17 — kabul grafiğinin y aralığı. Kapasite, gerinim bandının
    //: BORE_EKSEN_PAYI katından uzaktaysa eksen banda oturtulur ve
    //: kapasitenin ölçek dışı kaldığı oranıyla birlikte döner; aksi hâlde
    //: null döner (bugünkü otomatik eksen korunur).
    const BORE_EKSEN_PAYI = 3.0;
    function boreEksenAraligi(strain, cap) {
        if (!Array.isArray(strain) || !strain.length || !isNum(cap)) return null;
        const sonlu = strain.filter(isNum);
        if (!sonlu.length) return null;
        const dusuk = Math.min.apply(null, sonlu);
        const yuksek = Math.max.apply(null, sonlu);
        const bant = yuksek - dusuk;
        if (!(bant > 0)) return null;
        if (Math.abs(cap - yuksek) <= BORE_EKSEN_PAYI * bant) return null;
        const pay = 0.12 * bant;
        return {
            range: [dusuk - pay, yuksek + pay],
            kapasiteOlcekDisi: yuksek / cap,
        };
    }

    function grainConvergenceFigure(conv) {
        //: P11B3-13 — kesit panelinde de yön künyesi (aynı buildConvergence).
        const yonEtiket = convYonEtiketleri(conv);
        const izVm = {
            x: conv.n_elems, y: conv.von_mises_mpa,
            mode: 'lines+markers', type: 'scatter',
            marker: { size: 9 }, line: { width: 2 },
            name: GL('convTrace', 'Peak von Mises (SPR nodal) [MPa]'),
        };
        if (yonEtiket) {
            izVm.text = yonEtiket;
            izVm.hovertemplate = '%{y:.4g} MPa<br>%{text}<extra></extra>';
        }
        return {
            traces: [izVm],
            layout: {
                title: GL('chartConv',
                    'Mesh convergence — peak von Mises vs element count'),
                xaxis: { title: GL('axisElems', 'Elements in mesh [-]'),
                         type: 'log' },
                yaxis: { title: GL('axisVmConv',
                    'Peak von Mises (SPR nodal) [MPa]') },
                height: 300,
                showlegend: false,
            },
        };
    }

    function grainRenderBadges(el, vm) {
        let html = '';
        if (vm.grain_type) {
            let etiket = GL('badgeType', 'SECTION') + ': '
                + esc(String(vm.grain_type).toUpperCase());
            if (vm.symmetry_fraction) {
                etiket += ' · ' + gFmtTpl(GL('badgeSlice', '1/{n} slice'),
                                          { n: vm.symmetry_fraction });
            }
            html += badge(etiket, 'info');
        }
        html += badge(gFmtTpl(GL('badgeMesh',
            'MESH {elems} elements / {nodes} nodes'),
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes }),
            'info');
        html += badge(gFmtTpl(GL('badgeVm',
            'PEAK von MISES {v} MPa (Gauss points)'),
            { v: fmt(vm.scalars.von_mises_gauss_max_mpa, 3) }), 'info');
        // ÖH D25 · P11B3-12 — MANŞET ile HARİTA AYNI EKRANDA.
        // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): rozet
        // `von_mises_gauss_max_pa` = 164.679,3 Pa'dan 0,165 MPa basıyordu;
        // kontur haritası ve yakınsama grafiği ise `fields.von_mises_pa`
        // üstünden çiziliyor ve onun maksimumu 101.489,5 Pa = 0,1015 MPa
        // (= `von_mises_nodal_max_pa`), yani manşet haritadan %62,3 BÜYÜK.
        // `von_mises_nodal_max_mpa` görünüm modeline zaten alınıyordu ama
        // HİÇ basılmıyordu; kullanıcı manşetteki sayıyı haritada arayıp
        // bulamıyor ve farkın nedenini hiçbir yerde göremiyordu. Kardeş
        // yapısal panel bu farkı AÇIKÇA beyan ediyor (fea.gaussNote) —
        // tane panelinin künye derleyicisi o cümleyi hiç eklemiyordu.
        // Kapı: haritanın tepe değeri KENDİ rozetinde durur (aynı yükten,
        // dönüşüm yalnız Pa→MPa) ve künyeye ayrım cümlesi girer.
        if (vm.scalars.von_mises_nodal_max_mpa !== null) {
            html += badge(gFmtTpl(GL('badgeVmNodal',
                'MAP PEAK von MISES {v} MPa (nodal / SPR — this is the value '
                + 'the contour map and the convergence chart are drawn from)'),
                { v: fmt(vm.scalars.von_mises_nodal_max_mpa, 3) }), 'info');
        }
        if (vm.scalars.max_principal_max_mpa !== null) {
            html += badge(gFmtTpl(GL('badgeMaxPrincipal',
                'PEAK MAX PRINCIPAL {v} MPa (nodal maximum of '
                + 'fields.max_principal_pa — the tensile quantity the grain '
                + 'fracture criterion is written in)'),
                { v: fmt(vm.scalars.max_principal_max_mpa, 3) }), 'info');
        }
        html += badge(gFmtTpl(GL('badgeStrain',
            'MAX BORE STRAIN {v}% of {cap}% capability'),
            { v: fmt(vm.scalars.max_bore_strain_pct, 2),
              cap: fmt(vm.scalars.strain_capability_pct, 1) }), 'info');
        if (vm.scalars.strain_margin !== null) {
            // Eşikler motorun kendi risk sınıflamasıyla aynı; sınıflama
            // TEK yerde (strainMarginKind) — Merkez hükmü de oradan.
            const m = vm.scalars.strain_margin;
            const kind = strainMarginKind(m);
            html += badge(gFmtTpl(GL('badgeMargin',
                'STRAIN MARGIN {v} (capability / peak strain)'),
                { v: fmt(m, 2) }), kind);
        } else {
            html += badge(GL('badgeMarginMissing',
                'STRAIN MARGIN NOT PUBLISHED (no strain capability record)'),
                'dim');
        }
        const conv = vm.convergence;
        if (conv) {
            const acc = conv.acceptance;
            if (acc) {
                // HÜKÜM KABUL ÖLÇÜTÜNÜNDÜR. Tane kesitinde kabul, tepe von
                // Mises değil port lif GERİNİMİDİR (NASA SP-8073); vM
                // yalnızca mesh inceltme sürücüsüdür. Sunucu kabul bloğunu
                // yayımladığında yakınsama hükmü oradan verilir.
                const qEtiket = (acc.quantity === 'max_bore_strain')
                    ? GL('accQuantityBoreStrain', 'bore strain')
                    : (acc.quantity || '—');
                const accPct = isNum(acc.rel_change_pct)
                    ? fmtSig(acc.rel_change_pct, 4) + '%'
                    : GL('accPctMissing', 'not published');
                html += badge(gFmtTpl(acc.converged
                    ? GL('badgeAcceptanceConverged',
                         'ACCEPTANCE METRIC ({q}) CONVERGED — last change '
                         + '{pct} (tolerance {tol}%)')
                    : GL('badgeAcceptanceNotConverged',
                         'ACCEPTANCE METRIC ({q}) NOT CONVERGED — last change '
                         + '{pct} (tolerance {tol}%)'),
                    { q: esc(qEtiket), pct: esc(accPct),
                      tol: fmtSig(acc.tol_pct, 4) }),
                    acc.converged ? 'ok' : 'warn');
                // vM AYRI ve NÖTR: hâlâ inceliyor olması bir alarm değildir,
                // çünkü kabul dayanağı o değil.
                html += badge(gFmtTpl(conv.converged
                    ? GL('badgeVmSettled',
                         'PEAK vM settled at {pct}% — refinement driver, not '
                         + 'the acceptance basis')
                    : GL('badgeVmRefining',
                         'PEAK vM still refining {pct}% — not the acceptance '
                         + 'basis'),
                    { pct: fmtSig(conv.final_rel_change_pct, 4) }), 'info');
            } else {
                // GERİYE UYUM: sunucu kabul bloğunu yayımlamıyorsa (bugünkü
                // uç) davranış birebir eskisi gibidir.
                html += badge(conv.converged
                    ? gFmtTpl(GL('badgeConverged', 'CONVERGED in {n} rounds to {pct}%'),
                              { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) })
                    : gFmtTpl(GL('badgeNotConverged',
                        'NOT CONVERGED after {n} rounds (last change {pct}%)'),
                              { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) }),
                    conv.converged ? 'ok' : 'warn');
            }
        }
        if (vm.flags) {
            // Cidar paneliyle AYNI ayrışma (alarm = yalnız ölçekli Jacobian,
            // uzama nötr bilgi); metinler sayfanın solid.fea.* etiketlerinden
            // gelir ve kesit geometrisini anlatır (cidar cümlesi değil).
            html += qualityBadges(vm.flags, function (ad, p) {
                if (ad === 'badgeDistortion') {
                    return gFmtTpl(GL('badgeDistortion',
                        'MESH DISTORTION (scaled Jacobian < {sjMin}): '
                        + '{bad}/{total} flagged'), p);
                }
                if (ad === 'badgeDistortionMissing') {
                    return GL('badgeDistortionMissing',
                        'MESH DISTORTION NOT PUBLISHED (the response carries '
                        + 'no scaled Jacobian, so no distortion verdict is '
                        + 'issued)');
                }
                if (ad === 'badgeWorstQuality') {
                    return gFmtTpl(GL('badgeWorstQuality',
                        'WORST ELEMENT — aspect ratio {ar} ({arX}x the '
                        + 'threshold), scaled Jacobian {sj}'), p);
                }
                return gFmtTpl(GL('badgeElongated',
                    'ELONGATED ELEMENTS (aspect ratio > {arMax}): '
                    + '{bad}/{total} — expected for a thin web meshed in '
                    + 'layers around the port contour, not a distortion '
                    + 'alarm'), p);
            });
        }
        el.innerHTML = html;
    }

    // Sunucu uyarısı: KOD çeviriden geçer (warn.fea.planar_grain_*),
    // sözlük yoksa kodun kendisi kalır — kod yutulmaz. Tek tanım yeri:
    // hem beyan listesi hem NOT_MODELLED çipi buradan geçer (parti 34).
    function grainWarningText(w) {
        const kod = (w && typeof w === 'object' && w.code) ? w.code : '';
        if (!kod) return '';
        return (window.I18N && window.I18N.tf)
            ? window.I18N.tf(kod, (w && w.params) || {}, kod) : kod;
    }

    function grainRenderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        const g = vm.basis.inputs || {};
        if (g.geometri && g.geometri.kaynak) parts.push(SRV(g.geometri.kaynak));
        if (g.geometri && g.geometri.kesit) parts.push(SRV(g.geometri.kesit));
        if (g.malzeme && g.malzeme.kaynak) parts.push(SRV(g.malzeme.kaynak));
        if (g.analitik_blok_iliskisi) parts.push(SRV(g.analitik_blok_iliskisi));
        if (vm.basis.bore) parts.push(SRV(vm.basis.bore));
        if (vm.basis.quality) parts.push(SRV(vm.basis.quality));
        // ÖH D31 · P11B3-27: ölçüm kodunun kimliği (uç `quality._source`).
        if (vm.basis.quality_source) {
            // ÖH D32 / OH-D31-01: ham dize ÖDENDİ. Bu blok Merkez
            // kiracısının etiket sağlayıcısını (GL) kullanır; sıra
            // komşu `limitNote` satırıyla AYNI: kiracı etiketi varsa o,
            // yoksa sözlüğün EN+TR karşılığı, o da yoksa İngilizce yedek.
            parts.push(gFmtTpl(
                GL('qualitySource',
                   T('fea.qualitySource',
                     'Mesh quality metrics computed by: {source}')),
                { source: String(vm.basis.quality_source) }));
        }
        // P11B3-12: iki tepe değerinin NEDEN ayrıldığı künyede yazar.
        // Cümle kardeş yapısal panelin `fea.gaussNote` metniyle AYNI
        // gerçeği söyler; hiçbir sayı diğerine ölçeklenmez.
        if (vm.scalars.von_mises_gauss_max_mpa !== null
                && vm.scalars.von_mises_nodal_max_mpa !== null) {
            parts.push(GL('gaussNote', 'The headline peak stress is taken at '
                + 'the Gauss points of the elements; the contour map and the '
                + 'convergence chart show the stress recovered at the nodes, '
                + 'so the extreme value read off the map can differ from the '
                + 'headline number. Both are printed above. Neither is '
                + 'rescaled to match the other.'));
        }
        parts.push(GL('unitNote', 'Units: the solver returns Pa and unit '
            + 'strain; the panel only divides by 1e6 to plot MPa and '
            + 'multiplies strain by 100 to plot percent. No smoothing, no '
            + 'resampling, no rescaling of any field is applied. The section '
            + 'axes are drawn to equal scale.'));
        if (vm.limits && vm.limits.clamped) {
            parts.push(gFmtTpl(GL('limitNote',
                'Refinement was capped at {allowed} of {requested} rounds to '
                + 'keep the mesh within {max} elements.'),
                { max: vm.limits.max_elems,
                  allowed: vm.limits.rounds_allowed,
                  requested: vm.limits.rounds_requested }));
        }
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.warnings && vm.warnings.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};">`
                + esc(gFmtTpl(GL('inputWarnCount',
                    '{n} input warnings were declared by the motor solver:'),
                    { n: vm.warnings.length })) + '</p>';
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.warnings.map(function (w) {
                    return `<li style="margin:4px 0;">`
                        + `${esc(grainWarningText(w))}</li>`;
                }).join('') + '</ul>';
        }
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(gFmtTpl(GL(
                'notModelledCount',
                '{n} physics items are NOT modelled in this grain run:'),
                { n: vm.not_modelled.length }))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        els.basis.style.display = '';
    }

    // BOYACI (paintGrain) — tane kesitinin TEK çizim yolu; FeaPanel'deki
    // paintStructural ile aynı gerekçe (parti 34): Merkez kiracısı aynı
    // çıktıyı kendi kabında çizer, kopya çizim yazılmaz.
    function paintGrain(els, vm, isBusy) {
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Yüzde YOK (sahte gösterge yasak) ama geçen süre ve süre
            // sınırı YAZILIR — P17B1-18, yapısal kardeşiyle aynı desen.
            mesgulYaz('grain', els.busy, isBusy, gBusySince,
                GL('busy', 'Running — the solver refines the section mesh '
                    + 'until the peak stress stops changing; the duration is '
                    + 'not known in advance.'),
                function (gecen, sinir) {
                    return gFmtTpl(GL('busyElapsed',
                        'Elapsed {s} s; the request is cancelled after {limit} s.'),
                        { s: gecen, limit: sinir });
                });
        }
        // P11B3-19 — iptal düğmesi YALNIZ koşum sürerken görünür.
        iptalDugmesiniGoster(els.cancel, isBusy);

        function gizle() {
            ['vm', 'bore', 'conv'].forEach(function (k) {
                if (els[k]) els[k].style.display = 'none';
            });
            if (els.convNote) els.convNote.innerHTML = '';
        }

        if (vm.mode !== 'ok') {
            gizle();
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = isBusy ? '' : chipHtml(
                    GL('chipIdle', 'NOT RUN YET — press "Run grain section '
                        + 'FEA" to solve the grain cross-section of the '
                        + 'current result'), '');
            } else if (vm.mode === 'not_modelled') {
                // Sunucunun gerekçesi (serbest metin) + KOD'a bağlı uyarı
                // beyanı birlikte basılır: shapely eksikliği/desteklenmeyen
                // kesit kodları çeviri sözlüğünde yaşar
                // (warn.fea.planar_grain_*), gerekçe metni ise çözücünün
                // kendi cümlesidir. Kod tek başına yutulmaz — kiracıda da
                // aynı beyan görünür (parti 34).
                els.chip.innerHTML = chipHtml(
                    GL('chipNotModelled', 'NOT MODELLED — this grain section '
                        + 'is not covered by the planar solver; nothing is '
                        + 'drawn'),
                    [grainWarningText(vm.warning), vm.reason]
                        .filter(Boolean).join('\n'));
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    GL('chipError', 'RUN FAILED — no field is drawn'),
                    vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    GL('chipInvalid', 'DATA INCONSISTENT — the response '
                        + 'carries no usable mesh grid; nothing is plotted'),
                    '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            gizle();
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                GL('chipGridMismatch', 'MESH INCONSISTENT — the node grid '
                    + 'does not match the declared node count; nothing is '
                    + 'plotted'), '');
            return;
        }

        els.chip.innerHTML = '';
        grainRenderBadges(els.badges, vm);
        grainRenderBasis(els, vm);

        if (vm.von_mises_mpa) {
            els.vm.style.display = 'block';
            try {
                drawFigure(els.vm, grainFieldFigure(vm));
            } catch (e) {
                drawFigure(els.vm, grainFieldFallbackFigure(vm));
            }
        } else {
            els.vm.style.display = 'none';
        }

        if (vm.bore_curve) {
            els.bore.style.display = 'block';
            drawFigure(els.bore, grainBoreFigure(vm));
        } else {
            els.bore.style.display = 'none';
        }

        const conv = vm.convergence;
        if (conv && conv.n_elems.length >= 2) {
            els.conv.style.display = 'block';
            drawFigure(els.conv, grainConvergenceFigure(conv));
        } else {
            els.conv.style.display = 'none';
        }
        if (els.convNote && conv && conv.beyan) {
            els.convNote.innerHTML = esc(SRV(conv.beyan));
        }
    }

    // Standalone tane panelinin eleman haritası (grainPanelHtml kimlikleri).
    function grainEls() {
        return {
            badges: document.getElementById('grainfea_badges'),
            chip: document.getElementById('grainfea_chip'),
            busy: document.getElementById('grainfea_busy'),
            cancel: document.getElementById('grainfea_cancel'),
            vm: document.getElementById('grainfea_plot_vm'),
            bore: document.getElementById('grainfea_plot_bore'),
            conv: document.getElementById('grainfea_plot_conv'),
            convNote: document.getElementById('grainfea_conv_note'),
            basis: document.getElementById('grainfea_basis'),
            basisText: document.getElementById('grainfea_basis_text'),
        };
    }

    // Etiket sağlayıcısı sayfanın kendi sözlüğünü verir (solid.fea.*);
    // sağlayıcı yoksa İngilizce yedekler kullanılır. Kiracı da bu yolu
    // kullanır — ikinci bir etiket kaynağı YOK.
    function grainRefreshLabels() {
        gLabels = (typeof gCfg.labelsProvider === 'function')
            ? (gCfg.labelsProvider() || {}) : {};
    }

    // ------------------------------------------------------------------
    // ÖH D34 / OH-GT-06 — DİL DEĞİŞİNCE DURAĞAN METİNLER DE ÇEVRİLİR
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D34/metin-i18n/a1/once.json, OH_GT_06):
    // sözlükte Türkçesi VARDI ('solid.fea.run' -> 'Tane kesiti FEA
    // çalıştır') ve dil değişiminde etiket sağlayıcısı YENİDEN ÇAĞRILIYORDU
    // (saglayici_yeniden_cagrildi = true) — ama panelin durağan iskeleti
    // (başlık, giriş, koşu düğmesi, mesh etiketi, yöntem başlığı) yalnız
    // grainPanelHtml() içinde, KURULUM ANINDA bir kez yazılıyordu.
    // Ölçülen sonuç: dil TR'ye çevrildikten sonra düğme hâlâ
    // 'Run grain section FEA' diyordu.
    //
    // Çözüm: panel yeniden KURULMAZ (durum, grafik ve olay bağları
    // korunur); yalnız durağan metin düğümleri yeniden yazılır. Sözlükte
    // karşılığı olmayan etiket için GL() zaten İngilizce yedeği döndürür;
    // burada sessizce boşaltma YOK — düğüm yoksa dokunulmaz.
    function grainApplyStaticLabels() {
        const yaz = function (id, metin) {
            const el = document.getElementById(id);
            if (el && typeof metin === 'string' && metin) el.textContent = metin;
        };
        const baslik = document.getElementById('grainfea_title');
        if (baslik) {
            baslik.textContent = GL('title',   // OH-P-06: glif yok (kabuk h2 zaten işaretliyor)
                'Grain Section FEA — Plane-Strain Stress and Bore Strain');
        }
        yaz('grainfea_intro', GL('intro',
            'A 2D plane-strain finite element run on the propellant grain '
            + 'cross-section of THIS design (star, finocyl and slotted ports '
            + 'are not axisymmetric, so the wall solver cannot see them). '
            + 'The section polygon is built on the server from the motor '
            + 'solver itself; the acceptance quantity is the bore surface '
            + 'STRAIN against the propellant strain capability. If an input '
            + 'is missing, nothing is drawn and the reason is named.'));
        yaz('grainfea_run', GL('run', 'Run grain section FEA'));
        yaz('grainfea_cancel', GL('cancel', 'Cancel run'));
        yaz('grainfea_mesh_label', GL('showMesh', 'Show mesh wireframe'));
        yaz('grainfea_basis_title', GL('basisTitle',
            'Method / basis and what is NOT modelled (as declared by the '
            + 'solver)'));
    }

    function grainRender() {
        grainRefreshLabels();
        grainApplyStaticLabels();
        paintGrain(grainEls(), buildGrainViewModel(gLastPayload, gLastError),
                   gBusy);
    }

    function grainRun() {
        if (gBusy) return Promise.resolve(null);
        const params = (typeof gCfg.paramsProvider === 'function')
            ? gCfg.paramsProvider() : null;
        if (!params || typeof params !== 'object') {
            gLastPayload = null;
            gLastError = GL('noResult', 'No motor result on this page yet — '
                + 'run the motor calculation first.');
            grainRender();
            return Promise.resolve(null);
        }
        gBusy = true;
        gBusySince = Date.now();
        gLastError = null;
        grainRender();
        return fetch(GRAIN_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
            signal: kosumSinyali('grain'),   // P17B4-07 + P11B3-19
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            gBusy = false;
            gBusySince = null;
            kosumBitti('grain');
            if (!r.ok || !r.body || r.body.status !== 'success') {
                gLastPayload = null;
                gLastError = (r.body && (r.body.detail || r.body.message
                    || r.body.error))
                    || GL('httpError',
                          'The grain FEA endpoint returned an error.');
            } else {
                gLastPayload = r.body.fea || null;
                gLastError = null;
            }
            grainRender();
            return gLastPayload;
        }).catch(function (e) {
            const gecen = gBusySince
                ? Math.round((Date.now() - gBusySince) / 1000) : null;
            const gIptal = kullaniciIptaliMi('grain');
            gBusy = false;
            gBusySince = null;
            kosumBitti('grain');
            gLastPayload = null;
            // P17B1-18: sessiz düşüş yok — gerekçe adıyla ve süresiyle.
            // P11B3-19: kullanıcı durdurduysa AYRI cümle.
            gLastError = gIptal
                ? gFmtTpl(GL('cancelled',
                    'You stopped the grain FEA run after {s} s. Nothing was '
                    + 'computed and no result was changed.'),
                    { s: gecen === null ? 0 : gecen })
                : zamanAsimiMi(e)
                ? gFmtTpl(GL('timeout',
                    'The grain FEA run was cancelled after {s} s without a reply '
                    + 'from the solver. Nothing was computed. Try a coarser mesh, '
                    + 'then run it again.'),
                    { s: gecen === null
                        ? Math.round(ISTEK_ZAMAN_ASIMI_MS / 1000) : gecen })
                : String((e && e.message) || e);
            grainRender();
            return null;
        });
    }

    // Yeni motor sonucu geldi: eski kesit FEA çıktısı BAYATTIR, silinir.
    function grainUpdate() {
        if (gLastPayload || gLastError) {
            gLastPayload = null;
            gLastError = null;
        }
        grainRender();
    }

    function grainInit(opts) {
        gCfg = opts || {};
        grainRefreshLabels();
        const anchor = document.getElementById(gCfg.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = grainPanelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }

        const gCancelBtn = document.getElementById('grainfea_cancel');
        if (gCancelBtn) gCancelBtn.addEventListener('click', function () {
            kosumuIptalEt('grain');
        });
        const runBtn = document.getElementById('grainfea_run');
        if (runBtn) runBtn.addEventListener('click', function () { grainRun(); });
        const meshBox = document.getElementById('grainfea_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                gShowMesh = !!meshBox.checked;
                grainRender();
            });
        }

        // Hesap köprüsü: sayfanın sonuç basım işlevi sarılır (katı sayfada
        // 'displayResults'); özgün işlev her koşulda çalışır.
        (function () {
            const ad = gCfg.hookName || 'displayCalculationResults';
            const original = window[ad];
            if (typeof original !== 'function') return;
            window[ad] = function () {
                const out = original.apply(this, arguments);
                try {
                    grainUpdate();
                } catch (e) {
                    console.error('Grain FEA panel update failed:', e);
                }
                return out;
            };
        })();

        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { grainRender(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        grainRender();
    }

    window.GrainFeaPanel = {
        //: P11B3-17 bekçisi: kabul grafiğinin y aralığı kararı saf
        //: fonksiyondan ölçülür (eşik ve ölçek dışı payı dahil).
        _boreEksenAraligi: boreEksenAraligi,
        _boreEksenPayi: BORE_EKSEN_PAYI,
        _grainBoreFigure: grainBoreFigure,
        init: grainInit,
        update: grainUpdate,
        run: grainRun,
        buildViewModel: buildGrainViewModel,
        setShowMesh: function (v) { gShowMesh = !!v; grainRender(); },
        applyPayload: function (fea, error) {
            gLastPayload = fea || null;
            gLastError = error || null;
            gBusy = false;
            grainRender();
        },
        get payload() { return gLastPayload; },
        //: Kesit parametrelerinin TEK kaynağı (parti 34) — solid.html'in
        //: kendi grainFeaParams() kopyası bunun ikizidir ve bekçi ikisini
        //: aynı sonuç sözlüğüyle koşturup birebir eşitlik arar
        //: (tests/test_fea_merkez_kiracilari.py::TestParamsIkizi).
        _paramsFromResults: grainParamsFromResults,
    };

    // ==================================================================
    // ANALİZ MERKEZİ KİRACILARI (2.6.27 parti 34)
    // ------------------------------------------------------------------
    // Sözleşme: analysis_center.js dosya başı "KİRACI KAYIT SÖZLEŞMESİ".
    // İki kiracı buradan kaydolur:
    //   chamber_nozzle_wall.structural  -> /api/fea/structural  (FeaPanel)
    //   grain_section.planar_grain      -> /api/fea/planar-grain (GrainFeaPanel)
    //
    // ÇİZİM KOPYALANMAZ: kiracının render'ı standalone panelin BOYACISINI
    // (paintStructural / paintGrain) çağırır; tek fark eleman haritasının
    // Merkez'in görüntüleyici kökünde kurulmasıdır. Aynı yanıt iki yoldan
    // BİT-AYNI çıktı verir ve bekçi bunu ölçer.
    //
    // TERMAL SATIRI BURADA YOK — ölçülmüş gerekçe (parti 34):
    //   * Termal panel bu dosyada değil (hrma/static/js/thermal_fea_panel.js).
    //   * /api/fea/thermal 'axial_profile' alanını ZORUNLU tutar ve onu
    //     yalnız /api/analysis/wall-profile üretir (app.py:7947 docstring;
    //     "Motor sözlüğünden profil TÜRETİLMEZ"). Yani koşum İKİ isteklik
    //     bir zincirdir. Merkez'in koşum akışı TEK istek + SENKRON body()
    //     üstüne kuruludur (analysis_center.js run()); kiracı sözleşmesinde
    //     eşzamansız hazırlık kancası yoktur. Kiracı bugün kaydedilseydi
    //     satır READY görünür ama HER koşumda profil eksikliğinden
    //     NOT_MODELLED dönerdi — sahte hazırlık. Çerçeveye 'prepare' kancası
    //     eklenmeden bu satır taşınmaz.
    //
    // KAYIT NEDEN ERTELENİYOR (ölçüm): üç şablonda da bu dosya
    // analysis_center.js'ten ÖNCE yüklenir (advanced.html 717 < 758,
    // liquid.html 6789 < 6848, solid.html 5937 < 6067). cfd_panel.js'teki
    // üst-düzey register deseni buraya kopyalansaydı window.AnalysisCenter
    // tanımsız olur, kayıt SESSİZCE düşer ve iki satır sonsuza dek
    // "NOT IN CENTER" kalırdı. Kayıt bu yüzden DOMContentLoaded'a bağlanır
    // (bütün <script>'ler o ana kadar çalışmıştır); belge zaten yüklüyse
    // hemen denenir. Bekçi: TestKayit (mutasyon: erteleme sökülünce iki
    // kiracı da kayıtsız kalır ve bekçi kırmızı yanar).
    // ==================================================================

    let acSeq = 0;                  // kap kimlikleri benzersiz kalsın
    let acStructLast = null;        // {root, fea} — kontrol değişiminde yeniden çizim
    let acGrainLast = null;

    // İçindekiler şeridi (analysis_center.js K5b) [data-ac-section]
    // imzasını tanır: bölüm başlığı AÇIKÇA işaretlenir, stil tahminine
    // bırakılmaz.
    function acSection(key, fallback) {
        return '<div data-ac-section="1" data-i18n="' + key + '"'
            + ' style="font-family:var(--hd-mono, monospace); font-size:0.68rem;'
            + ' letter-spacing:0.08em; text-transform:uppercase;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:12px 0 6px;">'
            + esc(T(key, fallback)) + '</div>';
    }

    function acPlotBox(id, minHeight) {
        return '<div id="' + id + '" data-ac-fea-plot="1" class="plot-container"'
            + ' style="width:100%; min-height:' + minHeight + 'px;'
            + ' display:none;"></div>';
    }

    function acNoteBox(id) {
        return '<div id="' + id + '" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);'
            + ' margin:6px 0;"></div>';
    }

    function acControlRow(inner) {
        return '<div style="display:flex; flex-wrap:wrap; gap:12px;'
            + ' align-items:center; margin:0 0 8px;">' + inner + '</div>';
    }

    function acCheckbox(id, labelKey, labelText, checked) {
        return '<label style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);'
            + ' display:flex; gap:6px; align-items:center;">'
            + '<input type="checkbox" id="' + id + '"'
            + (checked ? ' checked' : '') + '>'
            + '<span' + (labelKey ? ' data-i18n="' + labelKey + '"' : '') + '>'
            + esc(labelText) + '</span></label>';
    }

    // Yanıt gövdesinden 'fea' bloğu — uç {status:'success', fea:{...}} döner
    // ve Merkez gövdeyi AYNEN saklar. Blok ADIYLA aranır, tahmin edilmez.
    function acFeaBlock(data) {
        if (!data || typeof data !== 'object') return null;
        const fea = data.fea;
        return (fea && typeof fea === 'object') ? fea : null;
    }

    // Kap yeniden yazılmadan önce eski Plotly örnekleri SÖKÜLÜR (güverte
    // yardımcısı; cfd_panel.js drawInto ile aynı desen). innerHTML ile
    // üstüne yazmak grafiği DOM'dan çıkarır ama Plotly'nin iç durumu
    // kalır — kontrol değişiminde her seferinde yeni kap açıldığı için
    // bu sızıntı birikirdi.
    function acPurge(root) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.purgePlots === 'function') U.purgePlots(root);
    }

    function acNoBlockHtml(key, fallback) {
        return '<p data-ac-fea-noblock="1" style="font-size:0.74rem;'
            + ' color:var(--hd-red, #ff5d73);">' + esc(T(key, fallback)) + '</p>';
    }

    // ------------------------------------------------------------------
    // 1) KAMARA/LÜLE CİDARI — YAPISAL
    // ------------------------------------------------------------------
    function acStructuralSkeleton(seq) {
        const p = 'ac_fea_';
        return acControlRow(
                acCheckbox(p + 'mesh_' + seq, 'fea.showMesh',
                           T('fea.showMesh', 'Show mesh wireframe'), showMesh)
                + '<label style="font-family:var(--hd-mono, monospace);'
                + ' font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);'
                + ' display:flex; gap:6px; align-items:center;">'
                + '<span data-i18n="fea.qualityMetric">'
                + esc(T('fea.qualityMetric', 'Quality metric')) + '</span>'
                + '<select id="' + p + 'metric_' + seq + '">'
                + '<option value="aspect_ratio"'
                + (qualityMetric === 'aspect_ratio' ? ' selected' : '')
                + ' data-i18n="fea.metricAspect">'
                + esc(T('fea.metricAspect', 'Aspect ratio')) + '</option>'
                + '<option value="scaled_jacobian"'
                + (qualityMetric === 'scaled_jacobian' ? ' selected' : '')
                + ' data-i18n="fea.metricJacobian">'
                + esc(T('fea.metricJacobian', 'Scaled Jacobian')) + '</option>'
                + '</select></label>')
            + '<div id="' + p + 'badges_' + seq + '" style="display:flex;'
            + ' flex-wrap:wrap; gap:8px; margin:8px 0;"></div>'
            + '<div id="' + p + 'chip_' + seq + '" style="margin:8px 0;"></div>'
            + acSection('panel.fea.secField',
                        'Stress field on the axisymmetric wall section')
            + acPlotBox(p + 'vm_' + seq, 340)
            + acPlotBox(p + 'sf_' + seq, 340)
            + acSection('panel.fea.secQuality', 'Mesh and element quality')
            + acPlotBox(p + 'quality_' + seq, 340)
            + acNoteBox(p + 'qnote_' + seq)
            + acSection('panel.fea.secConvergence', 'Mesh convergence')
            + acPlotBox(p + 'conv_' + seq, 300)
            + acNoteBox(p + 'cnote_' + seq)
            + '<details id="' + p + 'basis_' + seq + '" style="display:none;'
            + ' margin-top:8px;"><summary style="cursor:pointer;'
            + ' font-family:var(--hd-mono, monospace); font-size:0.75rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);" data-i18n="fea.basisTitle">'
            + esc(T('fea.basisTitle',
                    'Method / basis and what is NOT modelled (as declared by '
                    + 'the solver)')) + '</summary>'
            + '<div id="' + p + 'btext_' + seq + '" style="font-family:'
            + 'var(--hd-mono, monospace); font-size:0.72rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;'
            + ' white-space:pre-wrap;"></div></details>';
    }

    function acPaintStructural(root, fea) {
        if (!root) return;
        acSeq += 1;
        const seq = acSeq;
        acStructLast = { root: root, fea: fea };
        acPurge(root);
        root.innerHTML = acStructuralSkeleton(seq);
        function el(ad) { return document.getElementById('ac_fea_' + ad + '_' + seq); }
        // busy VERİLMEZ: koşum beyanı Merkez'in kendi durum satırındadır
        // (iki yerde iki "koşuyor" cümlesi olmasın).
        paintStructural({
            badges: el('badges'), chip: el('chip'), busy: null,
            vm: el('vm'), sf: el('sf'),
            quality: el('quality'), qualityNote: el('qnote'),
            conv: el('conv'), convNote: el('cnote'),
            basis: el('basis'), basisText: el('btext'),
        }, buildViewModel(fea, null), false);

        // Görünüm anahtarları panelle ORTAK durumdur (showMesh /
        // qualityMetric): buradan değiştirilince standalone panel de bir
        // sonraki basımında aynı seçimi gösterir — iki ayrı "aynı ayar"
        // tutulmaz. Değişimde YENİ İSTEK YOK: aynı yanıt yeniden çizilir.
        const box = el('mesh');
        if (box && box.addEventListener) {
            box.addEventListener('change', function () {
                showMesh = !!box.checked;
                acPaintStructural(root, fea);
            });
        }
        const sel = el('metric');
        if (sel && sel.addEventListener) {
            sel.addEventListener('change', function () {
                qualityMetric = sel.value || 'aspect_ratio';
                acPaintStructural(root, fea);
            });
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
    }

    function acStructuralRender(data, root) {
        if (!root) return;
        const fea = acFeaBlock(data);
        if (!fea) {
            root.innerHTML = acNoBlockHtml('panel.fea.noBlock',
                'The response carries no "fea" block, so nothing is drawn. '
                + 'Nothing is inferred in its place.');
            return;
        }
        acPaintStructural(root, fea);
    }

    // UYGULANABİLİRLİK — HER çizimde çağrılır: ucuz ve yan etkisiz
    // (istek atmaz, DOM'a yazmaz, durum değiştirmez).
    // ZORUNLU GİRDİ LİSTESİ BURADA AYNALANMAZ: hangi alanların gerektiği
    // köprünün motor-tipi imzasında yaşar (hrma/fea/bridge.py) ve eksik
    // olduğunda uç NOT_MODELLED + 'missing' ile ADIYLA söyler; panel o
    // listeyi çizer. İkinci bir kopya tutmak sürüklenme kaynağıdır.
    function acStructuralApplicability(results) {
        const motor = motorDictOf(results);
        if (!motor || typeof motor !== 'object' || !Object.keys(motor).length) {
            return { ok: false, reason: {
                key: 'panel.fea.needsMotorDict',
                fallback: 'This page carries no motor result dictionary, and '
                    + 'the structural solver is driven by that dictionary '
                    + 'alone. Run the motor calculation first.' } };
        }
        return { ok: true };
    }

    function acStructuralBody(formValues, results) {
        const motor = motorDictOf(results);
        if (!motor) {
            throw new Error(T('panel.fea.needsMotorDict',
                'This page carries no motor result dictionary, and the '
                + 'structural solver is driven by that dictionary alone. '
                + 'Run the motor calculation first.'));
        }
        return { motor_results: motor };
    }

    // HÜKÜM — yakınsama bayrağından. Metin "MESH" der: bu rozet MESH
    // yakınsamasının hükmüdür, dayanım kabulünün değil (emniyet katsayısı
    // ayrı rozette, ekranda).
    function acStructuralVerdict(data) {
        const fea = acFeaBlock(data);
        if (!fea) return null;                  // hüküm BEYAN EDİLMEZ
        if (fea.status !== 'ok') {
            return { kind: 'dim', key: 'panel.fea.verdictNotModelled',
                     fallback: 'NOT MODELLED — the solver named the missing '
                               + 'inputs instead of a field' };
        }
        const conv = buildConvergence(fea.convergence);
        if (!conv || !conv.meshes) return null;
        const params = { n: conv.rounds, pct: fmt(conv.final_rel_change_pct, 2) };
        // ÖH D25 · P11B3-11 — SATIR HÜKMÜ DAYANIMI DA GÖRÜR.
        // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): Merkez satır hükmü yalnız
        // `convergence.converged` bayrağına bakıyordu; min_safety_factor
        // 0,87 (yani AKMA ALTINDA) olan bir koşum satırda YEŞİL "MESH
        // CONVERGED" görünüyordu. Aynı renk üç kiracıda üç ayrı şey demek
        // oluyordu. Emsal panelin KENDİ rozet katmanıdır: orada renk zaten
        // yayımlanan EN KÖTÜ emniyet katsayısından veriliyor (P11B3-01,
        // renderBadges) ve sınıflama tek kaynakta — sfRozetTuru. Satır
        // hükmü artık aynı kapıdan geçer: mesh yakınsaması ayrı cümlede
        // KALIR (metin "MESH" der), ama SF hükmü yeşili düşürür ve sayı
        // satırın kendisine yazılır. Yeni eşik YOK: SF_ERR_MAX / SF_OK_MIN
        // kontur skalasıyla aynı tek kaynaktır.
        const kopruSf = (fea.scalars && isNum(fea.scalars.min_safety_factor))
            ? fea.scalars.min_safety_factor : null;
        const mk = motorKarsilastirmasi(fea);
        const motorSf = (mk && isNum(mk.motor_safety_factor))
            ? mk.motor_safety_factor : null;
        const hukumSf = (kopruSf === null) ? motorSf
            : (motorSf === null ? kopruSf : Math.min(kopruSf, motorSf));
        const sfTur = sfRozetTuru(hukumSf);
        if (hukumSf !== null && sfTur !== 'ok') {
            return { kind: sfTur,
                     key: conv.converged
                         ? 'panel.fea.verdictConvergedUnsafe'
                         : 'panel.fea.verdictNotConvergedUnsafe',
                     params: { n: conv.rounds,
                               pct: fmt(conv.final_rel_change_pct, 2),
                               sf: fmt(hukumSf, 2) },
                     fallback: conv.converged
                         ? 'MESH CONVERGED in {n} rounds (last change {pct}%) '
                           + '— but the worst published SAFETY FACTOR is {sf}'
                         : 'MESH NOT CONVERGED after {n} rounds (last change '
                           + '{pct}%) — and the worst published SAFETY FACTOR '
                           + 'is {sf}' };
        }
        if (conv.converged) {
            return { kind: 'ok', key: 'panel.fea.verdictConverged',
                     params: params,
                     fallback: 'MESH CONVERGED in {n} rounds (last change '
                               + '{pct}%)' };
        }
        return { kind: 'warn', key: 'panel.fea.verdictNotConverged',
                 params: params,
                 fallback: 'MESH NOT CONVERGED after {n} rounds (last change '
                           + '{pct}%)' };
    }

    const SPEC_STRUCTURAL = {
        componentId: 'chamber_nozzle_wall',
        analysisId: 'structural',
        // Başlık/anahtar §2 matrisinin satırıyla AYNI (ayrışmasın diye).
        title: 'Structural (linear static, axisymmetric)',
        titleKey: 'ac.an.structural',
        endpoint: ENDPOINT,
        // motorTypes BİLEREK YAZILMAZ: kapsam §2 matris satırında durur
        // (analysis_center.js evaluateRow kiracı vermezse matrisi kullanır).
        // İkinci bir kapsam listesi ayrışma kaynağıdır.
        long: true,
        // ALAN YOK — ölçüldü ve ürün kararıdır. Uç yalnız MESH ayarlarını
        // (n_axial0 / n_radial0 / max_rounds) isteğe bağlı okur; Berke'nin
        // 4 Ağustos 2026 kararı (dosya başı sözleşmesi) panelin mesh AYARI
        // sunmaması, yakınsama sürücüsünün kendi kararını vermesidir.
        // Standalone formda da sayısal alan yoktur; kart bu yüzden yalnız
        // [Çalıştır] taşır. Uydurma alan eklenmedi.
        fields: [],
        applicability: acStructuralApplicability,
        body: acStructuralBody,
        render: acStructuralRender,
        verdict: acStructuralVerdict,
    };

    // ------------------------------------------------------------------
    // 2) KATI TANE KESİTİ — DÜZLEMSEL FEA
    // ------------------------------------------------------------------
    //: Merkez kartının alanları: ucun beyaz listesindeki (app.py
    //: _PLANAR_GRAIN_KEYS) SAYISAL üyeler. Kimlik alanları (grain_type,
    //: propellant_type) ve kesit tipine özgü anahtarlar (star_/fin_/slot_)
    //: forma KONMAZ — onlar tasarımın kimliğidir ve sonuç sözlüğünden
    //: AYNEN geçer. Varsayılan hiçbirinde SONLU DEĞİLDİR: öneri gelmeyen
    //: alan boş kalır ve body() isteği durdurur (uydurma sayı yok).
    const GRAIN_FIELDS = [
        ['outer_diameter_mm', 'Grain outer diameter [mm]', '', 'any',
         'panel.grain.fieldOuter'],
        ['core_diameter_mm', 'Port (core) diameter [mm]', '', 'any',
         'panel.grain.fieldCore'],
        ['chamber_pressure_bar', 'Chamber pressure [bar]', '', 'any',
         'panel.grain.fieldPc'],
        ['grain_length_mm', 'Grain length [mm] — declaration only', '', 'any',
         'panel.grain.fieldLength'],
    ];
    //: Ucun 422 kapısındaki zorunlu SAYISAL alanlar (app.py
    //: _PLANAR_GRAIN_REQUIRED'ın sayısal üyeleri; grain_type ve
    //: propellant_type sonuçtan gelir ve ayrıca sınanır).
    const GRAIN_REQUIRED = ['outer_diameter_mm', 'core_diameter_mm',
                            'chamber_pressure_bar'];

    function acGrainLabel(fieldId) {
        for (let i = 0; i < GRAIN_FIELDS.length; i++) {
            if (GRAIN_FIELDS[i][0] === fieldId) {
                return T(GRAIN_FIELDS[i][4], GRAIN_FIELDS[i][1]);
            }
        }
        return fieldId;
    }

    function acGrainFromResults(results) {
        const p = grainParamsFromResults(results) || {};
        const out = {};
        GRAIN_FIELDS.forEach(function (f) {
            if (isNum(p[f[0]])) out[f[0]] = p[f[0]];
        });
        return out;
    }

    function acGrainApplicability(results) {
        const p = grainParamsFromResults(results);
        if (!p) {
            return { ok: false, reason: {
                key: 'panel.grain.needsDesign',
                fallback: 'This result publishes no solid grain design '
                    + '(grain_design.grain_type): the section polygon is built '
                    + 'on the server from the motor design itself, so the run '
                    + 'cannot start.' } };
        }
        const eksik = GRAIN_REQUIRED.filter(function (f) { return !isNum(p[f]); })
            .map(acGrainLabel);
        if (!p.propellant_type) eksik.push('propellant_type');
        if (eksik.length) {
            return { ok: false, reason: {
                key: 'panel.grain.needsInputs',
                params: { fields: eksik.join(', ') },
                fallback: 'This result does not publish the section inputs the '
                    + 'solver needs: {fields}. The endpoint has no default for '
                    + 'them and this panel invents none.' } };
        }
        return { ok: true };
    }

    // POST gövdesi: SAYILAR FORMDAN, kimlik/kesit anahtarları SONUÇTAN.
    // Sonuçtan gelen anahtarlar tek tek sayılmaz — form alanı OLMAYAN her
    // anahtar aynen taşınır; beyaz listeyi ucun kendisi uygular
    // (app.py _PLANAR_GRAIN_KEYS). Böylece istemci tarafında ikinci bir
    // beyaz liste tutulmaz.
    function acGrainBody(formValues, results) {
        const p = grainParamsFromResults(results);
        if (!p) {
            throw new Error(T('panel.grain.needsDesign',
                'This result publishes no solid grain design '
                + '(grain_design.grain_type): the section polygon is built on '
                + 'the server from the motor design itself, so the run cannot '
                + 'start.'));
        }
        const formIds = GRAIN_FIELDS.map(function (f) { return f[0]; });
        const body = {};
        Object.keys(p).forEach(function (k) {
            if (formIds.indexOf(k) === -1) body[k] = p[k];
        });
        const v = formValues || {};
        const eksik = [];
        GRAIN_REQUIRED.forEach(function (f) {
            if (isNum(v[f])) body[f] = v[f];
            else eksik.push(acGrainLabel(f));
        });
        if (isNum(v.grain_length_mm)) body.grain_length_mm = v.grain_length_mm;
        if (!body.propellant_type) eksik.push('propellant_type');
        if (eksik.length) {
            throw new Error(TF('panel.grain.missingInputs',
                { fields: eksik.join(', ') },
                'These inputs have no value and the endpoint has no default '
                + 'for any of them: {fields}. The request was NOT sent — this '
                + 'panel does not invent a number in their place.'));
        }
        return body;
    }

    // HÜKÜM: kabul ölçütü GERİNİMDİR (NASA SP-8073) — tepe von Mises değil.
    // Eşikler rozetlerle TEK kaynaktan (strainMarginKind).
    function acGrainVerdict(data) {
        const fea = acFeaBlock(data);
        if (!fea) return null;
        if (fea.status !== 'ok') {
            return { kind: 'dim', key: 'panel.grain.verdictNotModelled',
                     fallback: 'NOT MODELLED — the planar solver does not '
                               + 'cover this section; the reason is printed '
                               + 'in the view' };
        }
        const bore = fea.bore || {};
        if (!isNum(bore.strain_margin)) return null;   // hüküm beyan edilmez
        const kind = strainMarginKind(bore.strain_margin);
        // ÖH D18 · P11B3-02 [kritik] — OTURMAMIŞ ÖLÇÜTE YEŞİL HÜKÜM YOK.
        // ÖLÇÜLDÜ (`once_p11b3_02.json`, taban 9071a64): aynı yanıtta
        // `convergence.acceptance` = {quantity:'max_bore_strain',
        // converged:false, rel_change:0,34494972768962484, tol:0,01} —
        // kabul ölçütü toleransın 34,49 KATI oynuyor; Merkez satırı ise
        // {kind:'ok'} YEŞİL "STRAIN MARGIN 41.60" basıyor ve yakınsamama
        // satırda TEK KELİMEYLE geçmiyordu. (Standalone panelde turuncu
        // "ACCEPTANCE METRIC NOT CONVERGED" rozeti var; Merkez satırı
        // taranarak okunur ve orada yoktu.)
        //
        // Emsal: kardeş CFD paneli aynı durumu `hukumKesin` ile çözüyor —
        // oturmamış bir alana uygulanmış ölçüt "temiz" sayılmaz, YEŞİL
        // düşürülür. Aynı kural burada: KIRMIZI (marj < 1) ASLA
        // yumuşatılmaz, yalnız 'ok'/'warn' düşürülür ve gerekçe satıra
        // yazılır.
        const conv = (fea.convergence && typeof fea.convergence === 'object')
            ? fea.convergence : null;
        const acc = (conv && conv.acceptance
                     && typeof conv.acceptance === 'object')
            ? conv.acceptance : null;
        if (acc && acc.converged !== true) {
            return {
                kind: kind === 'err' ? 'err' : 'warn',
                key: 'panel.grain.verdictMarginNotConverged',
                params: {
                    v: fmt(bore.strain_margin, 2),
                    q: (typeof acc.quantity === 'string' && acc.quantity)
                        ? acc.quantity : '—',
                    pct: isNum(acc.rel_change)
                        ? fmt(100 * acc.rel_change, 2) + '%' : '—',
                    tol: isNum(acc.tol) ? fmt(100 * acc.tol, 2) + '%' : '—',
                },
                fallback: 'STRAIN MARGIN {v} NOT EARNED — the acceptance '
                          + 'metric ({q}) has not converged: last change '
                          + '{pct} against a {tol} tolerance',
            };
        }
        return { kind: kind,
                 key: 'panel.grain.verdictMargin',
                 params: { v: fmt(bore.strain_margin, 2) },
                 fallback: 'STRAIN MARGIN {v} (capability / peak bore strain)' };
    }

    function acGrainSkeleton(seq) {
        const p = 'ac_grain_';
        return acControlRow(acCheckbox(p + 'mesh_' + seq, null,
                                       GL('showMesh', 'Show mesh wireframe'),
                                       gShowMesh))
            + '<div id="' + p + 'badges_' + seq + '" style="display:flex;'
            + ' flex-wrap:wrap; gap:8px; margin:8px 0;"></div>'
            + '<div id="' + p + 'chip_' + seq + '" style="margin:8px 0;"></div>'
            + acSection('panel.grain.secField',
                        'Stress field on the grain cross-section')
            + acPlotBox(p + 'vm_' + seq, 380)
            + acSection('panel.grain.secBore',
                        'Bore surface strain (acceptance quantity)')
            + acPlotBox(p + 'bore_' + seq, 300)
            + acSection('panel.grain.secConvergence', 'Mesh convergence')
            + acPlotBox(p + 'conv_' + seq, 300)
            + acNoteBox(p + 'cnote_' + seq)
            + '<details id="' + p + 'basis_' + seq + '" style="display:none;'
            + ' margin-top:8px;"><summary style="cursor:pointer;'
            + ' font-family:var(--hd-mono, monospace); font-size:0.75rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);">'
            + esc(GL('basisTitle',
                     'Method / basis and what is NOT modelled (as declared by '
                     + 'the solver)')) + '</summary>'
            + '<div id="' + p + 'btext_' + seq + '" style="font-family:'
            + 'var(--hd-mono, monospace); font-size:0.72rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0 0;'
            + ' white-space:pre-wrap;"></div></details>';
    }

    function acPaintGrain(root, fea) {
        if (!root) return;
        acSeq += 1;
        const seq = acSeq;
        acGrainLast = { root: root, fea: fea };
        // Etiketler sayfanın sağlayıcısından (solid.fea.*) — kiracı için
        // ikinci bir etiket kaynağı YOK.
        grainRefreshLabels();
        acPurge(root);
        root.innerHTML = acGrainSkeleton(seq);
        function el(ad) { return document.getElementById('ac_grain_' + ad + '_' + seq); }
        paintGrain({
            badges: el('badges'), chip: el('chip'), busy: null,
            vm: el('vm'), bore: el('bore'),
            conv: el('conv'), convNote: el('cnote'),
            basis: el('basis'), basisText: el('btext'),
        }, buildGrainViewModel(fea, null), false);

        const box = el('mesh');
        if (box && box.addEventListener) {
            box.addEventListener('change', function () {
                gShowMesh = !!box.checked;
                acPaintGrain(root, fea);
            });
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
    }

    function acGrainRender(data, root) {
        if (!root) return;
        const fea = acFeaBlock(data);
        if (!fea) {
            root.innerHTML = acNoBlockHtml('panel.grain.noBlock',
                'The response carries no "fea" block, so nothing is drawn. '
                + 'Nothing is inferred in its place.');
            return;
        }
        acPaintGrain(root, fea);
    }

    const SPEC_PLANAR_GRAIN = {
        componentId: 'grain_section',
        analysisId: 'planar_grain',
        title: 'Plane strain (SP-8073 acceptance)',
        titleKey: 'ac.an.planarGrain',
        endpoint: GRAIN_ENDPOINT,
        // motorTypes yine matristen (§2: yalnız 'solid').
        long: true,
        fields: GRAIN_FIELDS,
        fromResults: acGrainFromResults,
        applicability: acGrainApplicability,
        body: acGrainBody,
        render: acGrainRender,
        verdict: acGrainVerdict,
    };

    // ------------------------------------------------------------------
    // KAYIT — yükleme sırası ölçüldü, erteleme ZORUNLU (yukarıdaki not).
    // ------------------------------------------------------------------
    function registerCenterTenants() {
        const AC = window.AnalysisCenter;
        if (!AC || typeof AC.register !== 'function') {
            if (window.console && console.warn) {
                console.warn('[FeaPanel] window.AnalysisCenter yok: yapısal ve '
                    + 'düzlemsel tane kiracıları kaydolamadı; satırlar '
                    + '"NOT IN CENTER" kalır.');
            }
            return false;
        }
        AC.register(SPEC_STRUCTURAL);
        AC.register(SPEC_PLANAR_GRAIN);
        return true;
    }

    if (window.AnalysisCenter && typeof window.AnalysisCenter.register === 'function') {
        registerCenterTenants();
    } else if (typeof document !== 'undefined' && document.addEventListener) {
        // Merkez henüz yüklenmedi (ölçülmüş şablon sırası): bütün
        // <script>'ler çalıştıktan sonra dene.
        document.addEventListener('DOMContentLoaded', registerCenterTenants);
    } else {
        registerCenterTenants();        // beyanlı uyarı üretir
    }

    // Test / hata ayıklama yüzeyi — saf katman DOM'suz koşulabilir.
    window.FeaCenterTenants = {
        structural: SPEC_STRUCTURAL,
        planarGrain: SPEC_PLANAR_GRAIN,
        _register: registerCenterTenants,
        _feaBlock: acFeaBlock,
        _grainFields: GRAIN_FIELDS,
        _grainRequired: GRAIN_REQUIRED,
        _paramsFromResults: grainParamsFromResults,
        _motorDictOf: motorDictOf,
        _strainMarginKind: strainMarginKind,
    };
})();
