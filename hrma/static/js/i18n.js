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
            'hero.badge': 'VERSION',
            'hero.tagline': 'Hybrid, Liquid & Solid Rocket Motor Analysis & Design Suite',
            'hero.sub': 'Parametric Solvers · Thermochemical Equilibrium Model · Interactive 3D Model',

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
            'link.launch_site': 'Launch Site (3D Earth)',

            'footer.developedBy': 'Developed by:',
            'footer.ideaTesting': 'Idea & Testing:',
            'footer.tool': 'Professional Rocket Propulsion Design Tool'

            /* ÖH D29 / P12aB2-10 — 'nav.home' / 'nav.hybrid' / 'nav.solid' /
               'nav.liquid' BURADAN SÖKÜLDÜ (EN+TR, 8 satır). ÖLÇÜLDÜ
               (a2/once.json M4): dördünün de ürün kodundaki kullanımı
               SIFIRDI — hiçbir şablon, hiçbir panel JS'i çağırmıyordu;
               onları yalnız tests/test_i18n.py'nin numune anahtar olarak
               kullanması canlı tutuyordu. Gezinme şeridi çalışma anında
               i18n_shell.js ile basılır ve kendi anahtarlarını taşır.
               Ölü çeviri çevrilmiş sanılan bir yüzey yanılsaması üretir:
               sözlük sayısı büyür, ekranda karşılığı olmaz. Numuneler
               canlı anahtarlara taşındı (link.formulas /
               link.launch_site / footer.tool / footer.developedBy). */
        },
        tr: {
            'lang.label': 'Dil',
            'lang.en': 'English',
            'lang.tr': 'Türkçe',

            'page.title': 'HRMA — Roket Motoru Analiz Paketi',
            'hero.badge': 'SÜRÜM',
            'hero.tagline': 'Hibrit, Sıvı ve Katı Roket Motoru Analiz ve Tasarım Paketi',
            'hero.sub': 'Parametrik Çözücüler · Termokimyasal Denge Modeli · Etkileşimli 3B Model',

            'cap.regression': 'Regresyon bağlaşık balistik',
            'cap.nozzle': 'Rao nozul konturları',
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
            'card.solid.desc': 'Farklı yakıt bloğu geometrileriyle, yanma hızı yasaları ve itki eğrisi tahmini ile katı yakıtlı roket motorlarını analiz edin.',
            'card.solid.f1': 'BATES, yıldız, vagon tekerleği yakıt blokları',
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
            'link.launch_site': 'Fırlatma Sahası (3B Dünya)',

            'footer.developedBy': 'Geliştiren:',
            'footer.ideaTesting': 'Fikir ve Test:',
            'footer.tool': 'Profesyonel Roket İtki Tasarım Aracı'
            /* ÖH D29 / P12aB2-10 — EN bloğundaki kardeş notu gör. */
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
            if (v === null || v === undefined) return '';
            return I18N.decimalText(String(v));
        });
    };

    /* ÖH D22 / P17B1-11 — EKRAN ANLAMLI BASAMAK SAYISI.
       Tek kaynak analysis_dock.js:1677 `DOCK_SIGFIG`; oradan
       `window.AnalysisDock.ui.SIGFIG` olarak yayımlanır. i18n.js sayfada
       analysis_dock.js'ten ÖNCE yüklendiği için değer ÇAĞRI ANINDA
       okunur; dock henüz yoksa aynı sayıya düşülür. Bu düşüş deseni
       ürünün kendi deseninin aynısıdır (analysis_center.js:155
       `FALLBACK_SIGFIG`, stability_panel.js:147). */
    var YEDEK_SIGFIG = 6;      // = analysis_dock.js DOCK_SIGFIG

    function ekranBasamagi() {
        var U = global.AnalysisDock && global.AnalysisDock.ui;
        var d = U && U.SIGFIG;
        return (typeof d === 'number' && isFinite(d) && d > 0) ? d : YEDEK_SIGFIG;
    }

    /* Sayı biçimi. TR ondalık ayırıcı virgül, EN nokta.
       Binlik ayırıcı BİLEREK kullanılmaz: mühendislik çıktısında
       "1.234" değerinin 1234 mü 1,234 mü olduğu belirsizleşmesin.

       ÖH D22 / P17B1-11 — ÖLÇÜLEN KUSUR (raw/OH/D22/arayuz/a2/once.json
       M1): `digits` verilmediğinde gövde `String(value)` diyordu, yani
       IEEE-754 çift duyarlığın gidiş-dönüş yapan EN KISA gösterimini
       basıyordu. O gösterim 17 anlamlı basamağa kadar çıkar ve ekranda
       ÖLÇÜLMEMİŞ bir duyarlık ilan eder: P17 turu hibrit sayfasında
       `L/D=1.4241155826338074` cümlesini yakaladı — aynı cümledeki
       `K_c` ucun kendisinde 2 basamağa yuvarlanmıştı. Sayı uydurulmuyor
       ama taşıdığından fazlası iddia ediliyordu.

       Onarım, ürünün BAŞKA YERDE ZATEN uyguladığı kuralı bu yola da
       getirir (app.js:1681-1685 `gateNumberText` ile birebir aynı üç
       satır): tam sayı olduğu gibi kalır, kesirli değer ekran basamak
       sayısına indirilir. Kısa yazılmış hiçbir sayı DEĞİŞMEZ, çünkü
       `parseFloat(v.toPrecision(n))` zaten kısa olan değeri aynen
       döndürür (bekçi: 101.325 / 0.0000368 / -3.5 / 0 / 5 / 1234567).
       `digits` AÇIKÇA verildiğinde eski davranış korunur — çağıran
       basamak sayısını biliyorsa hüküm onundur. */
    /* ÖH D30 / P12aB1-01 — ONDALIK AYRACI TEK KAYNAK.
       Ayraç seçimi bundan böyle TEK yerde yaşar: hem `I18N.number`
       (ham sayı yolu) hem `I18N.decimalText` (önceden biçimlenmiş metin
       yolu) buradan okur. İki yerde yazılırsa biri kayar ve tam da bu
       kalemin kusuru (aynı cümlede iki ayraç) geri gelir. */
    function ondalikAyraci() {
        return (I18N.lang === 'tr') ? ',' : '.';
    }

    /* ÖH D30 / P12aB1-01 — ÖNCEDEN BİÇİMLENMİŞ SAYI METNİ.

       ÖLÇÜLEN KUSUR (raw/OH/D30/arayuz-i18n/a1/once_p12ab101.json):
       `i18n_common.js` anahtarlı TF çağrılarının **90** parametresi panelde
       `toFixed` / `fmt` / `fmtExp` / `sigFig` ile ZATEN metne çevrilmiş
       geliyordu; `tf` yalnız `typeof v === 'number'` dalını çeviriyordu,
       yani Türkçe ekranda tek cümlede İKİ ayraç okunuyordu:
       `Tank basıncı (35,5 bar) oda basıncından (30,25 bar) yüksek olmalı.
        Gereken alt sınır: 36.3 bar`
       14 anahtar ikisini bir arada taşıyor (aynı rozette iki ayraç).

       KAPSAM BİLEREK DAR (fail-closed): yalnız BAŞTAN SONA sayı olan ve
       ondalık KESRİ BULUNAN metin çevrilir. Desene uymayanlara dokunulmaz:
         sürüm  '2.6.27' / 'v2.6.27' / '2.6.27.1'   (iki+ nokta ya da harf)
         tarih  '2026-09-08'                        (nokta yok)
         aralık '10-60 mm' / '0,09-0,49'            (tire/boşluk/harf)
         birimli '36.3 bar', '—', model adları      (sayı dışı kuyruk)
       YUVARLAMA YOKTUR: basamak sayısını çağıran seçmiştir (`toFixed(1)`),
       burada yalnız ayraç değişir — aksi hâlde ekranda ölçülmemiş bir
       duyarlık ilan edilirdi (bkz. aşağıdaki `I18N.number` künyesi).

       TERS YÖN (',' → '.') BİLEREK YOKTUR: gelen metin
       `toFixed`/`toPrecision`/`toExponential` çıktısıdır ve ECMA-262 bunları
       her zaman NOKTA ile basar. Virgüllü bir metnin binlik mi ondalık mı
       olduğunu tahmin etmek, bu dosyanın (aşağıda) açıkça reddettiği
       tahmindir — "1.234" değerinin 1234 mü 1,234 mü olduğu belirsizleşmesin
       diye binlik ayracı hiç kullanılmıyor. */
    var SAF_ONDALIK_METIN = /^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$/;

    I18N.decimalText = function (text) {
        if (typeof text !== 'string' || !SAF_ONDALIK_METIN.test(text)) return text;
        return text.replace('.', ondalikAyraci());
    };

    I18N.number = function (value, digits) {
        if (typeof value !== 'number' || !isFinite(value)) {
            return (value === null || value === undefined) ? '' : String(value);
        }
        var text;
        if (typeof digits === 'number' && isFinite(digits)) {
            text = value.toFixed(Math.max(0, Math.min(20, digits)));
        } else if (Number.isInteger(value)) {
            text = String(value);
        } else {
            text = String(parseFloat(value.toPrecision(ekranBasamagi())));
        }
        return text.replace('.', ondalikAyraci());
    };

    /* ÖH D35 / OH-GT-26 + OH-GT-28 — SAYI İLE BİRİM ARASINDA BOŞLUK.

       ÖLÇÜLEN KUSUR (raw/OH/D35/sayi-bicimi/a1/once.json): aynı ekranda
       kart "222,8 s" derken 3B başlığı "222.8s" yazıyordu — hem ayraç
       hem boşluk ayrışıyordu. SI/ISO 80000-1 birimi sayıdan boşlukla
       ayırır; istisnası YALNIZ derece/açı dakikası/saniyesidir (°, ′, ″),
       onlar bitişik yazılır.

       Boşluk BÖLÜNMEZ (U+00A0): "222,8" ile "s" satır sonunda ayrılırsa
       ölçü okunamaz hâle gelir. Birim verilmezse sayı yalnız döner —
       çağıran kendi kuyruğunu ekliyorsa bu yol ona karışmaz. */
    var BITISIK_BIRIMLER = ['°', '\u00B0', '′', '″', '%'];

    I18N.unit = function (value, unit, digits) {
        var sayi = I18N.number(value, digits);
        if (unit === null || unit === undefined || unit === '') return sayi;
        var u = String(unit);
        if (BITISIK_BIRIMLER.indexOf(u) !== -1) return sayi + u;
        return sayi + '\u00A0' + u;
    };

    /* ÖH D35 / OH-GT-28 — YÜZDE İŞARETİNİN YERİ DİLE BAĞLIDIR.

       ÖLÇÜLEN KUSUR: ekran iki dilde de "100%" basıyordu. TDK yazımında
       yüzde işareti sayıdan ÖNCE gelir ve bitişik yazılır ("%100"),
       İngilizcede sonra gelir ("100%"). Ayraç yine tek kaynaktan
       (`I18N.number`) okunur, burada YALNIZ işaretin yeri kararlaşır. */
    I18N.percent = function (value, digits) {
        var sayi = I18N.number(value, digits);
        if (typeof value !== 'number' || !isFinite(value)) return sayi;
        return (I18N.lang === 'tr') ? ('%' + sayi) : (sayi + '%');
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

    /* data-i18n-params: JS'in TF ile doldurup bastığı düğüm, parametrelerini
       bu öznitelikte JSON olarak taşır; dil değişince tf aynı parametrelerle
       yeniden doldurur. Öznitelik bozuksa null döner (aşağıdaki ezme koruması
       devreye girer). */
    function elementParams(el) {
        var raw = el.getAttribute('data-i18n-params');
        if (!raw) return null;
        try {
            var parsed = JSON.parse(raw);
            return (parsed && typeof parsed === 'object') ? parsed : null;
        } catch (e) {
            return null;
        }
    }

    /* Parametreli şablon, parametresi olmadan DOM'a BASILMAZ ({yer_tutucu}
       kuralı): çeviri hâlâ yer tutucu taşıyorsa eldeki dolu metin korunur —
       ham "{iters}" basmaktansa eski dilde kalmış doğru sayı yeğdir.
       (Ölçülen kusur: Analiz Merkezi hüküm rozeti TF ile doğru basılıyor,
       ardından applyTo parametresiz t(key) ile ezip çiğ şablonu yazıyordu.) */
    function hasBarePlaceholder(text) {
        return typeof text === 'string' && /\{\w+\}/.test(text);
    }

    /* ÖH D29 / P12aB1-05 — SESSİZ DONMA ARTIK SESSİZ DEĞİL.
       Parametreli şablon params'sız geldiğinde eldeki dolu metin KORUNUR
       (ham "{iters}" basmaktansa eski dilde kalmış doğru sayı yeğdir).
       Ama bu koruma düğümü dil değişiminde ESKİ DİLDE dondurur ve bugüne
       kadar bunu kimseye SÖYLEMİYORDU. Ölçüldü (a2/once.json M2):
       `data-i18n-params` yayan yalnız ÜÇ dosya var (analysis_center.js,
       settings_panel.js, update_check.js) — geri kalan her yayıcı bu
       tuzağa açık. Donmanın kendisi buradan onarılamaz (parametreler
       yayıcının elinde), ama sessiz bırakmak fail-closed doktrinine
       aykırıdır: donan her anahtar/yol çifti BİR KEZ uyarı yayar, kusur
       yayıcının kapısına düşer. Uyarı `warn()` üzerinden gider, yani
       I18N.debug kapalıyken ekranı kirletmez. */
    var DONMA_UYARILDI = {};

    function donmaUyar(key, yol) {
        var im = yol + '|' + key;
        if (DONMA_UYARILDI[im]) return;
        DONMA_UYARILDI[im] = true;
        warn('parametreli anahtar "' + key + '" (' + yol + ') data-i18n-params '
             + 'taşımıyor: düğüm ESKİ DİLDE dondu. Yayıcı parametreleri '
             + 'data-i18n-params ile taşımalı.');
    }

    function translateElement(el) {
        if (!el || el.nodeType !== 1 || !el.getAttribute) return;

        /* ÖH D29 / P12aB1-04 — PARAMETRE ÜÇ YOLUN DA HAKKI.
           Ölçülen kusur (a2/once.json M1): `params` yalnız metin dalında
           okunuyordu; `data-i18n-title` ve `data-i18n-placeholder`
           parametresiz `t()` çağırıyordu. Parametreli bir anahtar bu iki
           yola konduğunda çeviri hâlâ `{yer_tutucu}` taşıdığı için
           aşağıdaki ezme koruması devreye giriyor ve öznitelik SESSİZCE
           HİÇ YAZILMIYORDU — ne yeni değer basılıyor ne eski güncelleniyor.
           Parametre artık bir kez okunur ve üç yol da onu kullanır. */
        var params = elementParams(el);

        var key = el.getAttribute('data-i18n');
        if (key) {
            /* ÖH D36 · OH-K-05 — SÖZLÜKTEKİ İŞARETLEME DÜZ METİN OLARAK
               BASILIYORDU. Ölçüldü (22 Eyl, /formulas, TR ve EN): beş
               "model notu" anahtarı <em>/<code> taşıyor; textContent ile
               yazılınca kullanıcı 64 adet "<em>", "<code>&xi;</code>"
               dizgesini harfiyen görüyordu (ilk yüklemede EN de dâhil,
               çünkü apply şablondaki gerçek işaretlemeyi de eziyor).
               Yalnız `data-i18n-html` ile AÇIKÇA işaretlenen ve parametre
               taşımayan düğüm innerHTML alır (sözlük statik koddur;
               parametre kullanıcı verisi taşıyabilir → o yol metin kalır). */
            /* getAttribute ile: davranış koşumunun (tests/test_i18n.py) sahte
               düğümleri hasAttribute tanımlamıyor; yukarıdaki kapı da zaten
               getAttribute'a bakıyor. */
            var html = (el.getAttribute('data-i18n-html') != null) && !params;
            var fb = firstSeen(el, 'text', html ? el.innerHTML : el.textContent);
            var text = params ? I18N.tf(key, params, fb) : I18N.t(key, fb);
            if (params || !hasBarePlaceholder(text)) {
                if (html) el.innerHTML = text; else el.textContent = text;
            }
            else donmaUyar(key, 'data-i18n');
        }

        var tk = el.getAttribute('data-i18n-title');
        if (tk) {
            var fbT = firstSeen(el, 'title', el.getAttribute('title'));
            var tt = params ? I18N.tf(tk, params, fbT) : I18N.t(tk, fbT);
            if (params || !hasBarePlaceholder(tt)) el.setAttribute('title', tt);
            else donmaUyar(tk, 'data-i18n-title');
        }

        var pk = el.getAttribute('data-i18n-placeholder');
        if (pk) {
            var fbP = firstSeen(el, 'placeholder', el.getAttribute('placeholder'));
            var pt = params ? I18N.tf(pk, params, fbP) : I18N.t(pk, fbP);
            if (params || !hasBarePlaceholder(pt)) el.setAttribute('placeholder', pt);
            else donmaUyar(pk, 'data-i18n-placeholder');
        }
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
       ÖH D29 / P12aB2-11 — T/TF TABAN SÖZLEŞMESİ ÇEKİRDEKTE
       ---------------------------------------------------------------
       ÖLÇÜLEN KUSUR (a2/once.json M5, taban 4dc63c11): `global.T` /
       `global.TF` yalnız `i18n_pages.js`'in SONUNDA tanımlanıyordu, ama
       onları çağıran 934 yer (liquid.html 495 + solid.html 439) aynı
       dosyanın YÜKLENDİĞİNİ varsayıyordu. i18n_pages.js 404 alır, ağ
       kesilir ya da içine bir sözdizim hatası girerse `T` hiç tanımlanmaz
       ve ilk çağrı ReferenceError atarak sayfayı komple susturur.
       Kendi dosyasının yokluğunu hiçbir dosya kendi içinden karşılayamaz
       (yüklenmeyen dosyanın hiçbir satırı çalışmaz) — bu yüzden sözleşme
       BİR KATMAN AŞAĞIYA, çekirdeğe indi.

       Yükleme sırası bunu mümkün kılıyor: liquid.html:8 / solid.html:8
       i18n.js'i, :9 i18n_pages.js'i yükler. Çekirdek önce geldiği için
       `T` sayfa sözlüğü gelmeden de tanımlıdır; sözlük gelince
       i18n_pages.js kendi `if (typeof global.T !== 'function')` kapısında
       durur ve BURADAKİ tanım korunur (tek kaynak).

       Sözleşme aynen korunur: anahtar bulunamazsa çağıranın yedeği
       (İngilizce ürün metni) döner — sayı ya da metin UYDURULMAZ. */
    if (typeof global.T !== 'function') {
        global.T = function (key, fallback) {
            return I18N.t(key, fallback);
        };
    }
    if (typeof global.TF !== 'function') {
        global.TF = function (key, params, fallback) {
            return I18N.tf(key, params, fallback);
        };
    }


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
