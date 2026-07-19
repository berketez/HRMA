/*
   HRMA i18n katmanı — i18n.js  (ÇEKİRDEK)
   ---------------------------------------------------------------
   Bağımlılıksız, çerçevesiz çeviri katmanı. Amaç: arayüzdeki
   Türkçe/İngilizce karışıklığını bitirmek. Varsayılan dil İngilizce;
   kullanıcı Ana Sayfa'daki (ve alt sayfalardaki) seçiciden Türkçe'ye
   geçtiğinde HER ŞEY Türkçe olur.

   Sözleşme (DEĞİŞTİRME — testler bunu doğruluyor):
     window.I18N = {
       lang,                       // aktif dil kodu ('en' | 'tr')
       t(key, fallback),           // çeviri getir (yoksa fallback / EN / key)
       tf(key, params, fallback),  // {yer_tutucu} dolduran biçimlendirme
       setLang(l),                 // dili değiştir + kaydet + uygula
       apply(root),                // root altındaki data-i18n'leri çevir
       applyTo(el),                // tek bir DOM alt ağacını çevir (el dahil)
       onChange(fn),               // dil değişimi geri çağırması (unsubscribe döner)
       number(value, digits),      // sayı biçimi (TR: virgül, EN: nokta)
       register(dict, source),     // sözlük parçası kaydet (merge)
       has(key),                   // anahtar sözlükte var mı
       mountSwitcher(container),   // dil seçici bileşenini bas
       languages()                 // desteklenen dil kodları
     }

   DOM nitelikleri:
     data-i18n="key"              -> textContent
     data-i18n-title="key"        -> title niteliği
     data-i18n-placeholder="key"  -> placeholder niteliği

   DİKKAT: data-i18n taşıyan düğümün textContent'i BAŞTAN yazılır, yani alt
   elemanları silinir. İkon + metin bir aradaysa niteliği metnin kendi
   <span>'ine koy:
       <button><svg…></svg><span data-i18n="btn.run">Run</span></button>

   Dil tercihi localStorage.hrma_lang içinde saklanır. Script hiç
   yüklenmezse sayfa bozulmaz: tüm çağrı yerleri
   `typeof window.I18N !== 'undefined'` guard'ı kullanır.

   =================================================================
   ÇOK-PARÇALI SÖZLÜK SÖZLEŞMESİ  (diğer sözlük dosyaları için)
   =================================================================
   Bu dosya yalnız çekirdeği ve Ana Sayfa sözlüğünü taşır. Geri kalan
   metinler ayrı dosyalarda tutulur:

     hrma/static/js/i18n_<kapsam>.js     (i18n_common.js, i18n_pages.js,
                                          i18n_advanced.js, i18n_charts.js …)

   Dosya kalıbı (testler bu kalıbı ayrıştırır — birebir uy):

     (function (global) {
         'use strict';
         var DICT = {
             en: {
                 'panel.thrust': 'Thrust',
                 'panel.pc': 'Chamber pressure'
             },
             tr: {
                 'panel.thrust': 'İtki',
                 'panel.pc': 'Oda basıncı'
             }
         };
         if (global.I18N && global.I18N.register) {
             global.I18N.register(DICT, 'i18n_common.js');
         } else {
             (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
         }
     })(typeof window !== 'undefined' ? window : this);

   Kurallar:
     1. Anahtarlar TEK TIRNAK içinde, her satırda bir çift, değer tek
        satırda. (tests/test_i18n.py ayrıştırıcısı böyle okuyor.)
     2. EN ve TR anahtar kümeleri BİREBİR aynı olmalı — eksik çeviri
        testi kırar (yarım çeviri = yeni dil karışıklığı).
     3. Aynı anahtar iki dosyada tanımlanamaz. İlk kayıt kazanır,
        ikincisi konsola uyarı basar ve YOK SAYILIR.
     4. Yükleme sırası önemsizdir: i18n.js'ten önce yüklenen dosyalar
        __I18N_PENDING kuyruğuna birikir, i18n.js yüklenince boşalır.
     5. register() sayfa zaten çevrilmişse çeviriyi kendiliğinden
        yeniler; panelin ayrıca apply() çağırması gerekmez.
*/
(function (global) {
    'use strict';

    var STORAGE_KEY = 'hrma_lang';
    var DEFAULT_LANG = 'en';

    var STRINGS = {
        en: {
            'lang.label': 'Language',
            'lang.en': 'English',
            'lang.tr': 'Türkçe',

            'page.title': 'HRMA — Rocket Motor Analysis Suite',
            'hero.badge': 'SYSTEM ONLINE — SOLVER READY',
            'hero.tagline': 'High-Fidelity Rocket Motor Analysis & Design Suite',
            'hero.sub': 'Parametric Solvers · NASA CEA Validated · Digital Twin Visualization',

            'cap.regression': 'Regression-coupled ballistics',
            'cap.nozzle': 'Rao nozzle contours',
            'cap.sim3d': '3D combustion simulation',
            'cap.cad': 'CAD / STL export',

            'section.select': 'Select Propulsion Architecture',

            'card.hybrid.title': 'Hybrid Motors',
            'card.hybrid.code': 'LIQUID OX / SOLID FUEL',
            'card.hybrid.desc': 'Design and analyze hybrid rocket motors with regression-rate coupled ballistics, injector optimization and live 3D burn simulation.',
            'card.hybrid.f1': 'HTPB, Paraffin, ABS fuels',
            'card.hybrid.f2': 'N2O, LOX, H2O2 oxidizers',
            'card.hybrid.f3': 'Injector design optimization',
            'card.hybrid.f4': 'Marxman regression analysis',

            'card.solid.title': 'Solid Motors',
            'card.solid.code': 'SOLID PROPELLANT',
            'card.solid.desc': 'Analyze solid propellant rocket motors with various grain geometries, burn-rate laws and thrust-curve prediction.',
            'card.solid.f1': 'BATES, Star, Wagon wheel grains',
            'card.solid.f2': 'APCP, Black powder, Sugar',
            'card.solid.f3': 'Burn rate calculations',
            'card.solid.f4': 'Progressive / regressive thrust',

            'card.liquid.title': 'Liquid Engines',
            'card.liquid.code': 'BIPROPELLANT',
            'card.liquid.desc': 'Design liquid bipropellant rocket engines with advanced cooling, injection systems and feed-cycle sizing.',
            'card.liquid.f1': 'LOX/RP-1, LOX/LH2, Hypergolics',
            'card.liquid.f2': 'Regenerative cooling design',
            'card.liquid.f3': 'Turbopump specifications',
            'card.liquid.f4': 'Combustion instability analysis',

            'btn.launch': 'Launch Designer',
            'link.formulas': 'Formula Reference',

            'footer.developedBy': 'Developed by:',
            'footer.ideaTesting': 'Idea & Testing:',
            'footer.tool': 'Professional Rocket Propulsion Design Tool',

            'nav.home': 'Home',
            'nav.hybrid': 'Hybrid Motor',
            'nav.solid': 'Solid Motor',
            'nav.liquid': 'Liquid Engine'
        },
        tr: {
            'lang.label': 'Dil',
            'lang.en': 'English',
            'lang.tr': 'Türkçe',

            'page.title': 'HRMA — Roket Motoru Analiz Paketi',
            'hero.badge': 'SİSTEM ÇEVRİMİÇİ — ÇÖZÜCÜ HAZIR',
            'hero.tagline': 'Yüksek Doğruluklu Roket Motoru Analiz ve Tasarım Paketi',
            'hero.sub': 'Parametrik Çözücüler · NASA CEA Doğrulamalı · Dijital İkiz Görselleştirme',

            'cap.regression': 'Regresyon bağlaşık balistik',
            'cap.nozzle': 'Rao lüle konturları',
            'cap.sim3d': '3B yanma simülasyonu',
            'cap.cad': 'CAD / STL dışa aktarma',

            'section.select': 'İtki Mimarisini Seçin',

            'card.hybrid.title': 'Hibrit Motorlar',
            'card.hybrid.code': 'SIVI OKSİTLEYİCİ / KATI YAKIT',
            'card.hybrid.desc': 'Regresyon hızı bağlaşık balistik, enjektör optimizasyonu ve canlı 3B yanma simülasyonu ile hibrit roket motorları tasarlayın ve analiz edin.',
            'card.hybrid.f1': 'HTPB, parafin, ABS yakıtları',
            'card.hybrid.f2': 'N2O, LOX, H2O2 oksitleyicileri',
            'card.hybrid.f3': 'Enjektör tasarımı optimizasyonu',
            'card.hybrid.f4': 'Marxman regresyon analizi',

            'card.solid.title': 'Katı Yakıtlı Motorlar',
            'card.solid.code': 'KATI YAKIT',
            'card.solid.desc': 'Farklı grain geometrileri, yanma hızı yasaları ve itki eğrisi tahmini ile katı yakıtlı roket motorlarını analiz edin.',
            'card.solid.f1': 'BATES, yıldız, vagon tekerleği grainleri',
            'card.solid.f2': 'APCP, kara barut, şeker',
            'card.solid.f3': 'Yanma hızı hesapları',
            'card.solid.f4': 'Artan / azalan itki',

            'card.liquid.title': 'Sıvı Yakıtlı Motorlar',
            'card.liquid.code': 'ÇİFT İTİCİLİ',
            'card.liquid.desc': 'Gelişmiş soğutma, enjeksiyon sistemleri ve besleme çevrimi boyutlandırması ile sıvı çift iticili roket motorları tasarlayın.',
            'card.liquid.f1': 'LOX/RP-1, LOX/LH2, hipergoller',
            'card.liquid.f2': 'Rejeneratif soğutma tasarımı',
            'card.liquid.f3': 'Turbopompa özellikleri',
            'card.liquid.f4': 'Yanma kararsızlığı analizi',

            'btn.launch': 'Tasarımcıyı Aç',
            'link.formulas': 'Formül Referansı',

            'footer.developedBy': 'Geliştiren:',
            'footer.ideaTesting': 'Fikir ve Test:',
            'footer.tool': 'Profesyonel Roket İtki Tasarım Aracı',

            'nav.home': 'Ana Sayfa',
            'nav.hybrid': 'Hibrit Motor',
            'nav.solid': 'Katı Yakıtlı Motor',
            'nav.liquid': 'Sıvı Yakıtlı Motor'
        }
    };

    /* Hangi anahtar hangi dosyadan geldi (yalnız uyarı mesajı için). */
    var ORIGIN_FILE = {};

    /* Çevrilen düğümlerin ilk (şablondaki) metnini saklar; dil ileri-geri
       değiştiğinde fallback olarak İngilizce şablon metni korunur. */
    var ORIGIN_TEXT = (typeof global.WeakMap === 'function') ? new global.WeakMap() : null;

    var CALLBACKS = [];
    var applied = false;          // sayfaya en az bir kez apply() yapıldı mı

    function warn(message) {
        try {
            if (global.console && global.console.warn) global.console.warn('[i18n] ' + message);
        } catch (e) { /* konsol yoksa sessiz */ }
    }

    function supported() {
        var out = [];
        for (var k in STRINGS) {
            if (Object.prototype.hasOwnProperty.call(STRINGS, k)) out.push(k);
        }
        return out;
    }

    function normalize(code) {
        if (!code) return DEFAULT_LANG;
        var c = String(code).toLowerCase().slice(0, 2);
        return Object.prototype.hasOwnProperty.call(STRINGS, c) ? c : DEFAULT_LANG;
    }

    function stored() {
        try {
            return global.localStorage ? global.localStorage.getItem(STORAGE_KEY) : null;
        } catch (e) {
            return null;   // gizli sekme / storage kapalı
        }
    }

    function persist(code) {
        try {
            if (global.localStorage) global.localStorage.setItem(STORAGE_KEY, code);
        } catch (e) { /* storage yoksa sessizce geç */ }
    }

    /* Düğümün ilk halini hatırla (kind: 'text' | 'title' | 'placeholder'). */
    function firstSeen(el, kind, current) {
        if (!ORIGIN_TEXT || !el) return current;
        var rec = ORIGIN_TEXT.get(el);
        if (!rec) { rec = {}; ORIGIN_TEXT.set(el, rec); }
        if (!Object.prototype.hasOwnProperty.call(rec, kind)) rec[kind] = current;
        return rec[kind];
    }

    var I18N = {
        lang: normalize(stored())
    };

    /* ---------------------------------------------------------------
       Sözlük erişimi
       --------------------------------------------------------------- */

    I18N.has = function (key) {
        var table = STRINGS[I18N.lang] || STRINGS[DEFAULT_LANG];
        return !!(table && Object.prototype.hasOwnProperty.call(table, key));
    };

    /* Çeviri getir. Anahtar yoksa fallback, o da yoksa İngilizce, o da
       yoksa anahtarın kendisi döner — hiçbir durumda boş metin yazılmaz. */
    I18N.t = function (key, fallback) {
        var table = STRINGS[I18N.lang] || STRINGS[DEFAULT_LANG];
        if (table && Object.prototype.hasOwnProperty.call(table, key)) return table[key];
        if (typeof fallback === 'string' && fallback.length) return fallback;
        var en = STRINGS[DEFAULT_LANG];
        if (en && Object.prototype.hasOwnProperty.call(en, key)) return en[key];
        return key;
    };

    /* "Oda basıncı {value} bar" gibi dinamik metinler.
       params içinde bulunmayan yer tutucular OLDUĞU GİBİ bırakılır ki
       eksik parametre ekranda görünür olsun (sessiz boşluk yerine).
       Sayı değerleri aktif dilin ondalık ayırıcısıyla basılır. */
    I18N.tf = function (key, params, fallback) {
        var text = I18N.t(key, fallback);
        if (!params || typeof text !== 'string') return text;
        return text.replace(/\{(\w+)\}/g, function (whole, name) {
            if (!Object.prototype.hasOwnProperty.call(params, name)) return whole;
            var v = params[name];
            if (typeof v === 'number') return I18N.number(v);
            return (v === null || v === undefined) ? '' : String(v);
        });
    };

    /* Sayı biçimi. TR ondalık ayırıcı virgül, EN nokta.
       Binlik ayırıcı BİLEREK kullanılmaz: mühendislik çıktısında
       "1.234" değerinin 1234 mü 1,234 mü olduğu belirsizleşmesin. */
    I18N.number = function (value, digits) {
        if (typeof value !== 'number' || !isFinite(value)) {
            return (value === null || value === undefined) ? '' : String(value);
        }
        var text = (typeof digits === 'number' && isFinite(digits))
            ? value.toFixed(Math.max(0, Math.min(20, digits)))
            : String(value);
        if (I18N.lang === 'tr') text = text.replace('.', ',');
        return text;
    };

    I18N.languages = supported;

    /* ---------------------------------------------------------------
       Sözlük kaydı (çok-parçalı sözlük)
       --------------------------------------------------------------- */

    /* dict: { en: {key: text}, tr: {key: text} }
       - Mevcut sözlüğe MERGE eder.
       - Aynı anahtar ikinci kez gelirse İLK kayıt korunur, konsola uyarı basılır.
       - Sayfa zaten çevrilmişse çeviriyi tazeler.
       Dönüş: eklenen anahtar sayısı. */
    I18N.register = function (dict, source) {
        if (!dict || typeof dict !== 'object') {
            warn('register(): sözlük nesnesi bekleniyordu, ' + typeof dict + ' geldi');
            return 0;
        }
        var name = (typeof source === 'string' && source) ? source : '(anonim)';
        var added = 0;

        for (var lang in dict) {
            if (!Object.prototype.hasOwnProperty.call(dict, lang)) continue;
            var table = dict[lang];
            if (!table || typeof table !== 'object') continue;
            if (!Object.prototype.hasOwnProperty.call(STRINGS, lang)) {
                STRINGS[lang] = {};       // yeni dil eklemek serbest
            }
            var target = STRINGS[lang];
            for (var key in table) {
                if (!Object.prototype.hasOwnProperty.call(table, key)) continue;
                if (Object.prototype.hasOwnProperty.call(target, key)) {
                    if (target[key] !== table[key]) {
                        warn('yinelenen anahtar "' + key + '" (' + lang + '): ' + name +
                             ' kaydı yok sayıldı, ilk tanım korunuyor (' +
                             (ORIGIN_FILE[lang + '|' + key] || 'çekirdek') + ')');
                    }
                    continue;                     // ilk kazanır
                }
                target[key] = table[key];
                ORIGIN_FILE[lang + '|' + key] = name;
                added++;
            }
        }

        if (added && applied) I18N.apply();       // geç gelen sözlüğü ekrana yansıt
        return added;
    };

    /* ---------------------------------------------------------------
       DOM uygulaması
       --------------------------------------------------------------- */

    function translateElement(el) {
        if (!el || el.nodeType !== 1 || !el.getAttribute) return;

        var key = el.getAttribute('data-i18n');
        if (key) el.textContent = I18N.t(key, firstSeen(el, 'text', el.textContent));

        var tk = el.getAttribute('data-i18n-title');
        if (tk) el.setAttribute('title', I18N.t(tk, firstSeen(el, 'title', el.getAttribute('title'))));

        var pk = el.getAttribute('data-i18n-placeholder');
        if (pk) el.setAttribute('placeholder', I18N.t(pk, firstSeen(el, 'placeholder', el.getAttribute('placeholder'))));
    }

    /* root (verilmezse document) altındaki işaretli düğümleri çevirir.
       root'un kendisi de işaretliyse o da çevrilir. */
    function translateTree(scope) {
        if (!scope) return;
        translateElement(scope);                  // document ise nodeType 9 → atlanır
        if (!scope.querySelectorAll) return;

        var sel = '[data-i18n],[data-i18n-title],[data-i18n-placeholder]';
        var nodes = scope.querySelectorAll(sel);
        for (var i = 0; i < nodes.length; i++) translateElement(nodes[i]);
    }

    I18N.apply = function (root) {
        var scope = root || (global.document || null);
        if (!scope) return;

        translateTree(scope);
        applied = true;

        if (global.document && global.document.documentElement) {
            global.document.documentElement.setAttribute('lang', I18N.lang);
        }

        /* Alt sayfalardaki navigasyon dil göstergesi / seçici senkronu. */
        if (global.document && global.document.getElementById) {
            var navLang = global.document.getElementById('navLangLink');
            if (navLang) navLang.textContent = I18N.lang.toUpperCase();
            var mainSelect = global.document.getElementById('langSelect');
            if (mainSelect && mainSelect.value !== I18N.lang) mainSelect.value = I18N.lang;
        }
        syncSwitchers();
    };

    /* JS ile sonradan basılan HTML için: yalnız verilen alt ağacı çevirir,
       belge düzeyindeki (html lang, nav) işleri yapmaz. */
    I18N.applyTo = function (el) {
        if (!el) return;
        if (typeof el === 'string' && global.document && global.document.querySelector) {
            el = global.document.querySelector(el);
            if (!el) return;
        }
        translateTree(el);
    };

    /* Dil değişiminde çalışacak geri çağırma. Dönen fonksiyon kaydı siler. */
    I18N.onChange = function (fn) {
        if (typeof fn !== 'function') return function () {};
        CALLBACKS.push(fn);
        return function () {
            var i = CALLBACKS.indexOf(fn);
            if (i >= 0) CALLBACKS.splice(i, 1);
        };
    };

    /* Dili değiştir: kaydet, <html lang> güncelle, DOM'u tazele, olay yay. */
    I18N.setLang = function (code) {
        I18N.lang = normalize(code);
        persist(I18N.lang);
        I18N.apply();
        for (var i = 0; i < CALLBACKS.length; i++) {
            try {
                CALLBACKS[i](I18N.lang);
            } catch (e) {
                warn('onChange geri çağrısı hata verdi: ' + e);
            }
        }
        try {
            if (global.document && typeof global.CustomEvent === 'function') {
                global.document.dispatchEvent(new global.CustomEvent('hrma:langchange', {
                    detail: { lang: I18N.lang }
                }));
            }
        } catch (e) { /* eski tarayıcı: olay yayını opsiyonel */ }
        return I18N.lang;
    };

    /* ---------------------------------------------------------------
       Dil seçici bileşeni (her sayfada bulunur)
       --------------------------------------------------------------- */

    var SWITCHER_CSS = [
        '.hrma-lang-switch{display:inline-flex;align-items:center;gap:6px;',
        'font-size:12px;letter-spacing:.04em;vertical-align:middle}',
        '.hrma-lang-switch select{background:rgba(255,255,255,.06);color:inherit;',
        'border:1px solid rgba(255,255,255,.18);border-radius:6px;padding:3px 6px;',
        'font:inherit;font-size:12px;cursor:pointer;outline:none}',
        '.hrma-lang-switch select:focus{border-color:rgba(255,255,255,.45)}',
        '.hrma-lang-switch select option{background:#12161d;color:#e6e9ef}'
    ].join('');

    function injectCss() {
        if (!global.document || !global.document.head) return;
        if (global.document.getElementById('hrma-lang-switch-css')) return;
        var style = global.document.createElement('style');
        style.id = 'hrma-lang-switch-css';
        style.textContent = SWITCHER_CSS;
        global.document.head.appendChild(style);
    }

    function syncSwitchers() {
        if (!global.document || !global.document.querySelectorAll) return;
        var list = global.document.querySelectorAll('select[data-hrma-lang-select]');
        for (var i = 0; i < list.length; i++) {
            var sel = list[i];
            for (var j = 0; j < sel.options.length; j++) {
                var code = sel.options[j].value;
                sel.options[j].textContent = I18N.t('lang.' + code, code.toUpperCase());
            }
            if (sel.value !== I18N.lang) sel.value = I18N.lang;
        }
    }

    /* Verilen konteynere küçük bir dil seçici basar.
       container: element | CSS seçici | yoksa .nav-links / nav / .navbar.
       Aynı konteynere ikinci kez çağrılırsa var olanı döndürür (idempotent). */
    I18N.mountSwitcher = function (container) {
        var doc = global.document;
        if (!doc || !doc.createElement) return null;

        var host = container;
        if (typeof host === 'string') host = doc.querySelector(host);
        if (!host) {
            host = doc.querySelector('.nav-links') || doc.querySelector('nav') ||
                   doc.querySelector('.navbar') || doc.body;
        }
        if (!host) return null;

        var existing = host.querySelector ? host.querySelector('[data-hrma-lang-switcher]') : null;
        if (existing) return existing;

        injectCss();

        var wrap = doc.createElement('span');
        wrap.className = 'hrma-lang-switch';
        wrap.setAttribute('data-hrma-lang-switcher', '1');

        var select = doc.createElement('select');
        select.setAttribute('data-hrma-lang-select', '1');
        select.setAttribute('aria-label', I18N.t('lang.label', 'Language'));
        select.setAttribute('data-i18n-title', 'lang.label');
        select.setAttribute('title', I18N.t('lang.label', 'Language'));

        var codes = supported();
        for (var i = 0; i < codes.length; i++) {
            var opt = doc.createElement('option');
            opt.value = codes[i];
            opt.textContent = I18N.t('lang.' + codes[i], codes[i].toUpperCase());
            select.appendChild(opt);
        }
        select.value = I18N.lang;

        select.addEventListener('change', function () {
            I18N.setLang(select.value);
            select.value = I18N.lang;
        });

        wrap.appendChild(select);
        host.appendChild(wrap);
        return wrap;
    };

    global.I18N = I18N;

    /* ---------------------------------------------------------------
       Bekleyen sözlükleri boşalt (i18n.js'ten ÖNCE yüklenmiş dosyalar)
       --------------------------------------------------------------- */
    (function drainPending() {
        var pending = global.__I18N_PENDING;
        if (pending && typeof pending.length === 'number') {
            for (var i = 0; i < pending.length; i++) {
                I18N.register(pending[i], '(pending)');
            }
        }
        /* Kuyruk artık doğrudan register'a bağlanır: i18n.js'ten SONRA
           yüklenen dosyalar aynı deseni kullansa da kaybolmaz. */
        global.__I18N_PENDING = {
            length: 0,
            push: function (dict) { I18N.register(dict, '(pending)'); return 0; }
        };
    })();

    /* Sayfa hazır olunca bir kez uygula (seçici olmasa da <html lang> doğru olur). */
    if (global.document) {
        if (global.document.readyState === 'loading') {
            global.document.addEventListener('DOMContentLoaded', function () { I18N.apply(); });
        } else {
            I18N.apply();
        }
    }
})(typeof window !== 'undefined' ? window : this);
