/* ====================================================================
   HRMA Proje Şeridi — project_bar.js (v2.5.5)
   --------------------------------------------------------------------
   Proje kaydet/yükle arayüzü (backend: hrma/utils/projects_api.py,
   ARGE raporu 2026-07-21):

     GET  /api/projects              — liste (corrupt işaretli)
     POST /api/projects/save         — {name, payload, overwrite}
     GET  /api/projects/load/<name>  — tam belge + warnings

   Davranış sözleşmesi (ARGE raporu):
     - inputs.fields: sayfadaki id'li input/select/textarea → id->değer
       (checkbox bool, number number, diğerleri string). Dinamik panellerin
       (analiz güvertesi, 6-DOF, enjektör, transient) alanları HARİÇ.
     - inputs.dynamic.composition_rows: hibrit özel yakıt satırları
       (class tabanlı, id'siz — jenerik serileştirici kaçırır).
     - inputs.ui_state: hibrit sekme durumu (design/environment/analysis).
     - inputs.dock_overrides: güvertede data-dirty=1 işaretli ad_f_* alanlar.
     - Geri yüklemede HER alana change (ve input) olayı yayılır — bağımlı
       hesaplar (updateMixtureDensity, expansion ratio vb.) tetiklensin.
     - Yükleme sonuç HESAPLAMAZ; kullanıcı Calculate'e basar.
     - results_summary yalnız liste kartlarında gösterilir, asla
       currentResults'a enjekte edilmez.

   Landing (index.html): yalnız "Recent Projects" şeridi — endpoint yoksa
   ya da liste boşsa şerit hiç görünmez.

   Uçlar app'e kayıtlı olmayabilir (test ortamı): her fetch hatası
   toast + konsol ile zarifçe raporlanır, sayfa çalışmaya devam eder.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    // ------------------------------------------------------------------
    // Sayfa tespiti
    // ------------------------------------------------------------------
    var PATH_TYPE = { '/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid' };
    var TYPE_PATH = { hybrid: '/hybrid', solid: '/solid', liquid: '/liquid' };
    var path = location.pathname.replace(/\/+$/, '') || '/';
    var motorType = PATH_TYPE[path] || null;
    var isLanding = (path === '/');
    if (!motorType && !isLanding) return;      // formulas vb. — şerit yok

    // Proje adı kuralı (sunucudaki beyaz listenin istemci aynası,
    // hrma/utils/projects.py _NAME_CHARS): İngilizce ve Türkçe harfler
    // (yalnız önceden birleşik/NFC), rakam, boşluk, _ . - ; 1-80, nokta ile
    // başlayamaz, nokta/boşluk ile bitemez, Windows'ta ayrılmış aygıt adı
    // olamaz. v3.0.1 (NK-51): Türkçe harfli ad ("Şimşek-1") reddediliyordu.
    var NAME_RE = /^[A-Za-z0-9çğıöşüÇĞİÖŞÜ _.\-]{1,80}$/;
    var NAME_CHAR_RE = /^[A-Za-z0-9çğıöşüÇĞİÖŞÜ _.\-]$/;
    // Reddedilen karakterleri adıyla göster (NK-51: ileti hangi karakterin
    // sorun olduğunu söylemiyordu). Görünmez/birleştirici karakter U+XXXX
    // olarak yazılır.
    function yasakKarakterler(name) {
        var gorulen = {}, liste = [];
        Array.from(String(name)).forEach(function (ch) {
            if (NAME_CHAR_RE.test(ch) || gorulen[ch]) return;
            gorulen[ch] = true;
            var gorunmez = /[\s\u0000-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]|\p{M}/u.test(ch);
            liste.push(gorunmez
                ? 'U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')
                : ch);
        });
        return liste;
    }
    // ÖH D20 / P12aB4-16 — ÖLÇÜLDÜ (once.json): sunucunun reddettiği 22
    // ayrılmış adın 22'si de istemci doğrulamasından geçiyordu; modal
    // kapanıyor, POST gidiyor, sunucu 400 dönüyor ve kullanıcı adı baştan
    // yazıyordu. Ayna eksikti. Liste sunucudaki `_WINDOWS_RESERVED`
    // (hrma/utils/projects.py) ile birebir aynıdır; bekçi
    // (tests/test_d20_electron_a1.py) iki listeyi her koşumda karşılaştırır,
    // yani ayrışma sessizce yaşayamaz. Sunucu `stem.upper()` ile denetler:
    // ayna da büyük/küçük harf ayrımı yapmaz.
    var WINDOWS_RESERVED = ['CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'];
    function validName(name) {
        if (typeof name !== 'string') return false;
        if (!NAME_RE.test(name)) return false;
        if (name.charAt(0) === '.') return false;
        if (/[. ]$/.test(name)) return false;
        // Sunucu uzantısız gövdeye bakar (`stem`): '.hrma' eki burada yok.
        if (WINDOWS_RESERVED.indexOf(name.toUpperCase()) !== -1) return false;
        return true;
    }

    // Dinamik panel kökleri: bu alt ağaçlardaki alanlar projeye SERİLEŞTİRİLMEZ
    // (güverte ad_f_* alanları ayrıca dock_overrides olarak ele alınır)
    var DYNAMIC_ROOTS = '#analysisDock, #sixDofPanel, #injectorPanel, '
        + '#transientPanel, #hrmaProjectBar, #hrmaProjectModal, #stepImportModal';

    /* Sunucudan gelen hata/uyarı metni — TR kipinde çevrilir.
     * ÖH D20 / P12aB4-15 — ÖLÇÜLDÜ (once.json): `I18N.serverText` ürünün
     * başka yerlerinde (analysis_dock.js, fea_panel.js) kullanılıyordu ama bu
     * dosyada 0 çağrı vardı; TR kipinde bildirimler "Kaydetme başarısız:
     * Project name is a reserved device name" gibi yarı Türkçe çıkıyordu. */
    function srv(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    /* V3 KK 2. tur (REL D-5) — proje YÜKLEME uyarısı makine kodu +
     * parametreyle gelir (hrma/utils/projects.py load_warning_records):
     * metin i18n anahtarından kurulur (EN = TR). ÖLÇÜLDÜ (dal tabanı
     * 1b4bbff7): eski sürüm uyarısı TR kipinde İngilizce basılıyordu.
     * Parametreler HAM metin olarak yerleşir — sürüm kimliği ("2.6.26")
     * bir ondalık sayı değildir, tf'nin sayı biçimlemesinden geçirilmez.
     * Kod tanınmazsa, parametre düz metin/sonlu sayı değilse ya da sözlükte
     * anahtar yoksa sunucu metni aynen (serverText) basılır: uydurma yok. */
    var PROJE_UYARI_KODU = /^warn\.project\.[a-z_]+$/;
    // Kayıtlar düz listeyle BİREBİR eşleşmezse hiçbiri kullanılmaz
    // (fail-closed: yanlış kayıt yanlış metne gitmesin).
    function yuklemeUyariKayitlari(data) {
        var duz = Array.isArray(data.warnings) ? data.warnings : [];
        return (Array.isArray(data.warning_records)
                && data.warning_records.length === duz.length)
            ? data.warning_records : null;
    }
    function yuklemeUyariMetni(metin, kayit) {
        if (!kayit || typeof kayit !== 'object'
            || typeof kayit.code !== 'string'
            || !PROJE_UYARI_KODU.test(kayit.code)
            || !kayit.params || typeof kayit.params !== 'object'
            || !(window.I18N && window.I18N.has && window.I18N.has(kayit.code))) {
            return srv(metin);
        }
        var p = kayit.params;
        var gecerli = Object.keys(p).every(function (k) {
            var v = p[k];
            return typeof v === 'string'
                || (typeof v === 'number' && isFinite(v));
        });
        if (!gecerli) return srv(metin);
        var sablon = T(kayit.code, metin);
        var eksik = false;
        var sonuc = String(sablon).replace(/\{(\w+)\}/g, function (whole, ad) {
            if (!Object.prototype.hasOwnProperty.call(p, ad)) {
                eksik = true;
                return whole;
            }
            return String(p[ad]);
        });
        return eksik ? srv(metin) : sonuc;
    }

    var NEW_NAME_SS_KEY = 'hrma_pending_new_project';
    // v3.0.1 UI-K (NK-26 ek): kaydedilmemiş son hesabın özeti. Tasarım
    // sayfasından ayrılırken (pagehide) sonuç diske KAYDEDİLMEMİŞSE buraya
    // yazılır; ana sayfa "Son Projeler" listesine KARIŞTIRMADAN ayrı ve
    // adıyla "kaydedilmedi" diye gösterir. Kaydedilince silinir.
    var UNSAVED_RUN_LS_KEY = 'hrma.project.unsavedRun';

    var state = {
        name: null,          // aktif proje adı (null = kaydedilmemiş)
        savedName: null,     // diskte var olduğu bilinen ad (overwrite kararı)
        dirty: false,
        restoring: false,
        source: null,        // "STEP import (x.step)" gibi köken notu
        /* ÖH D22 / P12aB4-24 — proje açıklaması. ÖLÇÜLDÜ (once.json K3):
           `#motor_description` yalnız /hybrid'de var; /solid ve /liquid'de
           açıklama HİÇ kaydedilemiyordu, oysa sunucu şeması `description`
           kabul ediyor ve liste ucu geri veriyor. Açıklama artık sayfadan
           BAĞIMSIZ bir yerde de durur: alanı olan sayfada alan kazanır,
           olmayanda kayıt penceresindeki alan doldurur, açılan projede de
           kaybolmaz. */
        description: '',
        /* v3.0.1 UI-K (NK-26 ek): diske yazılan (ya da yüklemede ekranda
           duran, kullanıcının attığı) sonuç nesnesi. Sayfadan ayrılırken
           `window.currentResults` bundan farklıysa son hesap KAYDEDİLMEMİŞTİR. */
        savedResults: null,
    };

    // ÖH D21 / P12aB4-23 — `escapeHtml` KALDIRILDI. Ölçüldü: dosyada tek
    // geçişi kendi tanım satırıydı (0 çağrı). Bu dosya bütün DOM'u
    // `textContent` / `createElement` ile kurar, yani HTML gövdesine hiç
    // dizge gömmez — kaçış işlevi gereksizdi. Ölü güvenlik yardımcısı,
    // "burada kaçış yapılıyor" izlenimi vererek ileride ham innerHTML
    // yazımını meşrulaştırabilirdi. HTML gövdesine metin gömen bir yol
    // açılırsa kaçış O YOLLA birlikte geri gelir (bkz. import_ui.js, orada
    // gerçek bir çağrı var).

    // Ana yol import_ui.js'tir (advanced/liquid/solid). Ana sayfada import_ui
    // yüklü DEĞİLDİR, bu yüzden aşağıdaki yedek çalışır. İki uygulama da AYNI
    // istif kabını (#hrma-toast-stack) kullanır: bildirimler üst üste binmez,
    // alt kenardan yukarı dizilir (bkz. import_ui.js'teki İSTİFLEME notu).
    var TOAST_HOST_ID = 'hrma-toast-stack';

    function toastHost() {
        var host = document.getElementById(TOAST_HOST_ID);
        if (host) return host;
        host = document.createElement('div');
        host.id = TOAST_HOST_ID;
        host.style.cssText =
            'position:fixed; right:18px; bottom:18px; z-index:99995;' +
            'display:flex; flex-direction:column; gap:8px; align-items:flex-end;' +
            'pointer-events:none;';
        document.body.appendChild(host);
        return host;
    }

    function toast(message, kind) {
        if (window.HRMAImportUI && window.HRMAImportUI.toast) {
            window.HRMAImportUI.toast(message, kind);
            return;
        }
        try {
            var colors = { ok: 'var(--hd-green, #2dd4a8)', err: 'var(--hd-red, #ff5d73)',
                           warn: 'var(--hd-orange, #ff8c33)', info: 'var(--hd-cyan, #00e5ff)' };
            var c = colors[kind] || colors.info;
            var node = document.createElement('div');
            node.style.cssText =
                'max-width:420px; padding:12px 16px; font-size:0.82rem;' +
                'font-family:var(--hd-mono, monospace); color:' + c + ';' +
                'background:var(--hd-panel-solid, #0a1524); border:1px solid ' + c + ';' +
                'border-radius:var(--hd-radius-sm, 8px); pointer-events:auto;' +
                'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));';
            node.textContent = String(message);
            toastHost().appendChild(node);
            setTimeout(function () {
                var host = node.parentNode;
                if (host) host.removeChild(node);
                if (host && host.id === TOAST_HOST_ID && !host.firstChild
                    && host.parentNode) {
                    host.parentNode.removeChild(host);
                }
            }, 6000);
        } catch (e) { /* sessiz */ }
    }

    // ==================================================================
    // SERİLEŞTİRME
    // ==================================================================

    function serializeFields() {
        var fields = {};
        // BELGE GENELİ tarama (v2.5.5 duman testi düzeltmesi): hibrit
        // sayfada form bölümleri .container içinde değil .panel div'lerinde
        // yaşıyor — .container beyaz listesi 226 alandan yalnız 15'ini
        // görüyordu (geometri/yakıt/oksitleyici kaydedilmiyordu). Dinamik
        // panel ve kendi modallarımız DYNAMIC_ROOTS ile zaten dışlanır.
        var nodes = document.querySelectorAll(
            'input[id], select[id], textarea[id]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var type = (el.getAttribute('type') || '').toLowerCase();
            if (type === 'file' || type === 'button' || type === 'submit'
                || type === 'radio') continue;
            if (el.closest && el.closest(DYNAMIC_ROOTS)) continue;
            if (el.id === 'langSelect') continue;
            // ÖH D36 · A-3 — KÖKEN KAPILI ALAN. Sayfa bir alanı
            // data-hrma-source-gate="1" ile işaretlediyse (hibrit tasarım
            // paneli) değer yalnız köken damgası (data-hrma-source: user |
            // project_file) taşıyorsa kaydedilir. ÖLÇÜLDÜ (a1/once.json S3):
            // kayıt yükü dokunulmamış panelin 11 varsayılanını taşıyordu
            // (wall_thickness 5, pressure_drop_percent 20 ...); geri
            // yüklemede bunlar 'project_file' damgası alıp çözücüye
            // kullanıcı verisi gibi gidecekti.
            if (el.dataset && el.dataset.hrmaSourceGate === '1'
                && !el.dataset.hrmaSource) continue;
            if (type === 'checkbox') {
                fields[el.id] = !!el.checked;
            } else if (type === 'number') {
                var raw = String(el.value);
                if (raw.trim() === '') {
                    fields[el.id] = '';
                } else {
                    var num = parseFloat(raw);
                    fields[el.id] = isFinite(num) ? num : raw;
                }
            } else {
                fields[el.id] = String(el.value);
            }
        }
        return fields;
    }

    // Hibrit özel yakıt bileşimi satırları (class tabanlı, id'siz)
    function serializeCompositionRows() {
        var rows = document.querySelectorAll('#composition_rows .composition-row');
        if (!rows.length) return null;
        var out = [];
        for (var i = 0; i < rows.length; i++) {
            var compound = rows[i].querySelector('.compound');
            var pct = rows[i].querySelector('.percentage');
            var pctVal = pct ? parseFloat(pct.value) : NaN;
            out.push({
                compound: compound ? String(compound.value) : '',
                percentage: isFinite(pctVal) ? pctVal : '',
            });
        }
        return out;
    }

    // Hibrit sekme durumu — hangi kap "active" ise onun adı saklanır
    function serializeUiState() {
        if (motorType !== 'hybrid') return null;
        var ui = {};
        function activeOf(pairs) {
            for (var i = 0; i < pairs.length; i++) {
                var el = document.getElementById(pairs[i][0]);
                if (el && el.classList.contains('active')) return pairs[i][1];
            }
            return null;
        }
        var env = activeOf([['single_env', 'single'], ['profile_env', 'profile']]);
        var design = activeOf([['thrust_time_design', 'thrust_time'],
                               ['total_impulse_design', 'total_impulse']]);
        var analysis = activeOf([['single_tab', 'single'], ['parametric_tab', 'parametric'],
                                 ['trajectory_tab', 'trajectory']]);
        if (env) ui.environment_tab = env;
        if (design) ui.design_tab = design;
        if (analysis) ui.analysis_tab = analysis;
        return Object.keys(ui).length ? ui : null;
    }

    // Analiz güvertesi: yalnız kullanıcının elle değiştirdiği (data-dirty=1)
    // ad_f_* alanları — öneri mekanizması bozulmasın (ARGE kararı)
    function serializeDockOverrides() {
        var out = {};
        var nodes = document.querySelectorAll('#analysisDock [id^="ad_f_"]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el.dataset || el.dataset.dirty !== '1') continue;
            if (el.tagName === 'SELECT') {
                out[el.id] = String(el.value);
            } else {
                var v = parseFloat(el.value);
                out[el.id] = isFinite(v) ? v : String(el.value);
            }
        }
        return Object.keys(out).length ? out : null;
    }

    // Küçük sonuç özeti — yalnız liste kartları için; panellere geri basılmaz
    function serializeResultsSummary() {
        var cr = window.currentResults;
        if (!cr) return null;
        var out = {};
        function put(key, v) {
            if (typeof v === 'number' && isFinite(v)) out[key] = v;
        }
        if (motorType === 'hybrid') {
            var m = cr.motor || {};
            put('thrust_N', m.thrust);
            put('isp_s', m.isp);
            put('burn_time_s', m.burn_time);
            put('chamber_pressure_bar', m.chamber_pressure);
            put('total_impulse_Ns', m.total_impulse);
            if ('isp_s' in out) out.isp_basis = 'design_point';
        } else if (motorType === 'solid') {
            put('total_impulse_Ns', cr.total_impulse);
            put('burn_time_s', cr.burn_time);
            put('chamber_pressure_bar', cr.chamber_pressure);
            put('isp_s', cr.isp_sea_level);
            if ('isp_s' in out) out.isp_basis = 'sea_level';
            if (cr.thrust_curve && Array.isArray(cr.thrust_curve.thrust)
                && cr.thrust_curve.thrust.length) {
                put('peak_thrust_N', Math.max.apply(null, cr.thrust_curve.thrust));
            }
        } else if (motorType === 'liquid') {
            put('thrust_N', cr.thrust);
            put('isp_s', cr.isp_sea_level);
            if ('isp_s' in out) out.isp_basis = 'sea_level';
            put('isp_vacuum_s', cr.isp_vacuum);
            put('chamber_pressure_bar', cr.chamber_pressure);
            // ÖH D37 · A1b dil-cozucu-nesri · CW-D4 — SIVI SATIRINDA It.
            // ÖLÇÜLDÜ (a1/once.json CW-D4): sıvı özeti It'i HİÇ taşımıyordu;
            // katı/hibrit satırında "It … N·s" varken sıvıda ne sayı ne de
            // yokluğun nedeni vardı. Sıvı çözücüsü üst düzeyde toplam itki
            // yayımlamaz; yayımladığı TEK toplam itki dışa aktarım özetindedir
            // (openrocket.motor_summary.total_impulse, künye
            // total_impulse_source = 'thrust_x_burn_time') ve yanma süresi
            // verilmediğinde null'dır (burn_time_source = 'not_supplied').
            // Burada sayı HESAPLANMAZ: yayımlanmışsa aynen taşınır, değilse
            // çözücünün kendi künyesi taşınır ki satır yokluğun NEDENİNİ
            // söyleyebilsin (sayı uydurulmaz).
            var ors = (cr.openrocket && cr.openrocket.motor_summary) || {};
            put('total_impulse_Ns', ors.total_impulse);
            if (!('total_impulse_Ns' in out)
                && cr.burn_time_source === 'not_supplied') {
                out.burn_time_source = 'not_supplied';
            }
        }
        if (!Object.keys(out).length) return null;
        var surumSimdi = window.HRMA_VERSION || window.HRMA_APP_VERSION;
        // v3.0.1 UI-K (NK-26 ek): katı ve sıvı sayfası window'a sürüm
        // yazmıyor; özet DAMGASIZ kaydediliyor ve ana sayfa az önce bu
        // sürümle kaydedilen projeyi "daha eski bir sürümle hesaplandı"
        // diye işaretliyordu (ölçüldü: ui-k/son_projeler_once.json, adım 3).
        // İki sayfa da sürümü yapay zekâ panelinin `data-hrma-version`
        // özniteliğinde taşır (sunucunun app_version'ı; tek kaynak).
        if (!surumSimdi && typeof document !== 'undefined' && document.querySelector) {
            var surumEl = document.querySelector('[data-hrma-version]');
            surumSimdi = surumEl ? surumEl.getAttribute('data-hrma-version') : null;
        }
        if (typeof surumSimdi === 'string' && surumSimdi.trim()) {
            out.computed_with_version = surumSimdi.trim();
        }
        return out;
    }

    function buildPayload(name) {
        var inputs = { fields: serializeFields() };
        var rows = serializeCompositionRows();
        if (rows) inputs.dynamic = { composition_rows: rows };
        var ui = serializeUiState();
        if (ui) inputs.ui_state = ui;
        var dock = serializeDockOverrides();
        if (dock) inputs.dock_overrides = dock;

        var payload = {
            format: 'hrma-project',
            format_version: 1,
            motor_type: motorType,
            name: name,
            inputs: inputs,
        };
        /* Açıklamanın TEK türetildiği yer (P12aB4-24). Öncelik sayfadaki
           alanındır (kullanıcı orada yazıyorsa en tazesi odur); alan yoksa
           ya da boşsa proje şeridinin kendi tuttuğu metin kullanılır. */
        var descEl = document.getElementById('motor_description');
        var desc = (descEl && String(descEl.value).trim())
            ? String(descEl.value) : String(state.description || '');
        if (desc.trim()) payload.description = desc;
        var summary = serializeResultsSummary();
        if (summary) payload.results_summary = summary;
        return payload;
    }

    // ==================================================================
    // GERİ YÜKLEME
    // ==================================================================

    function dispatchFieldEvents(el) {
        // Bağımlı hesaplar iki olaydan birini dinleyebiliyor (solid sayfası
        // expansion ratio 'input', hibrit fuel_type 'change') — ikisi de yayılır
        try {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) { /* eski tarayıcı — sessiz */ }
    }

    function restoreUiState(ui) {
        if (!ui || motorType !== 'hybrid') return;
        function fixButtons(fnName, value) {
            var btn = document.querySelector(
                'button[onclick*="' + fnName + '(\'' + value + '\')"]');
            if (btn && btn.parentElement) {
                var tabs = btn.parentElement.querySelectorAll('.tab');
                for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
                btn.classList.add('active');
            }
        }
        if (ui.environment_tab && typeof window.switchEnvironmentTab === 'function') {
            window.switchEnvironmentTab(ui.environment_tab);
            fixButtons('switchEnvironmentTab', ui.environment_tab);
        }
        if (ui.design_tab && typeof window.switchDesignTab === 'function') {
            window.switchDesignTab(ui.design_tab);
            fixButtons('switchDesignTab', ui.design_tab);
        }
        if (ui.analysis_tab && typeof window.switchTab === 'function') {
            window.switchTab(ui.analysis_tab);
        }
    }

    // V301/H-PANEL (NK-68): kayıtta OLMAYAN seçiciler sayfa varsayılanına
    // döner. ÖLÇÜLDÜ (son kullanıcı testi, hibrit): "Kullanıcının verdiği
    // tank basıncı" kipi seçilip örnek proje yeniden açılınca kip ESKİ
    // kalıyordu — örnek proje kaydı ``tank_pressure_source`` alanını
    // taşımıyor (kip, kayıttan sonra eklendi) ve geri yükleme yalnız
    // kayıttaki alanları yazıyordu. Seçici kayıtta yoksa varsayılan seçeneğe
    // (``defaultSelected``, yoksa ilk seçenek) döner ve bağımlı işleyiciler
    // tetiklenir; köken kapılı alanın damgası silinir (kullanıcı girdisi
    // sayılmasın). Kayıttaki alanlar bundan SONRA yazılır.
    function resetUnsavedSelects(fields) {
        var n = 0;
        var kayit = fields || {};
        var nodes = document.querySelectorAll('select[id]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (el.id === 'langSelect') continue;
            if (el.closest && el.closest(DYNAMIC_ROOTS)) continue;
            if (Object.prototype.hasOwnProperty.call(kayit, el.id)) continue;
            var hedef = null;
            for (var j = 0; j < el.options.length; j++) {
                if (el.options[j].defaultSelected) { hedef = el.options[j].value; break; }
            }
            if (hedef === null && el.options.length) hedef = el.options[0].value;
            if (hedef === null || el.value === hedef) continue;
            el.value = hedef;
            dispatchFieldEvents(el);
            if (el.dataset && el.dataset.hrmaSourceGate === '1') {
                delete el.dataset.hrmaSource;
            }
            n += 1;
        }
        return n;
    }

    // V301/HİBRİT-DIŞA (28 Eki, S1 veri kaybı) — GERİ YÜKLEME SIRADAN
    // BAĞIMSIZ. ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/hibrit-disa/olcum/
    // gidis_donus_*_once.json): /api/projects/load yanıtı Flask jsonify ile
    // anahtarları ALFABETİK sıralı döndürür ve alanlar bu sırayla tek turda
    // yazılıyordu. Bir alanın olay işleyicisi başka bir alanı yeniden kurar
    // ya da üzerine yazarsa, alfabede ÖNCE gelen kayıtlı değer kayboluyordu:
    // hibritte injector_type'ın change olayı parametre alanlarını boş
    // yeniden kurar (hole_diameter_min/max, element_pairs, impingement_angle,
    // annular_gap, coaxial_inner_flow_fraction silinip sunucu varsayılanı
    // uygulanıyordu), fuel_type yoğunluğu tablodan ezer (fuel_density),
    // itki sekmesinin üçgeni yanma süresini yeniden hesaplar
    // (burn_time_impulse). Artık: (1) önce seçiciler (yapıyı kurarlar),
    // sonra öbür alanlar olaylarla yazılır; (2) kayıtlı değerinden sapan
    // alan en çok 3 düzeltme turunda olaylarla yeniden yazılır; (3) hâlâ
    // sapan alan (birbirini yeniden hesaplayan alanlar) OLAYSIZ kayıtlı
    // değerine konur — kaydedilen değer kullanıcının kendi değeridir.
    // Hiçbir turda öğesi bulunamayan alan "atlandı" sayılır (yapı kuran bir
    // seçicinin sonradan yarattığı alan artık atlanmaz).
    function restoreFields(fields) {
        try { resetUnsavedSelects(fields); } catch (e) { /* DOM yoksa */ }
        var kayit = fields || {};
        var ids = Object.keys(kayit);
        function oge(id) {
            var el = document.getElementById(id);
            return (el && !el.closest(DYNAMIC_ROOTS)) ? el : null;
        }
        function seciciMi(id) {
            var el = oge(id);
            return !!(el && el.tagName === 'SELECT');
        }
        // Seçiciler önce, kayıt sırası her grupta korunur.
        ids = ids.filter(seciciMi).concat(ids.filter(function (id) {
            return !seciciMi(id);
        }));
        function hedef(v) {
            return (v === null || v === undefined) ? '' : String(v);
        }
        function onayKutusu(el) {
            return (el.getAttribute('type') || '').toLowerCase() === 'checkbox';
        }
        function ayni(el, v) {
            return onayKutusu(el) ? (el.checked === !!v) : (el.value === hedef(v));
        }
        function yaz(el, v, olayli) {
            if (onayKutusu(el)) el.checked = !!v;
            else el.value = hedef(v);
            if (olayli) dispatchFieldEvents(el);
        }
        ids.forEach(function (id) {
            var el = oge(id);
            if (el) yaz(el, kayit[id], true);
        });
        for (var tur = 0; tur < 3; tur++) {
            var sapan = 0;
            ids.forEach(function (id) {
                var el = oge(id);
                if (el && !ayni(el, kayit[id])) { yaz(el, kayit[id], true); sapan += 1; }
            });
            if (!sapan) break;
        }
        ids.forEach(function (id) {
            var el = oge(id);
            if (el && !ayni(el, kayit[id])) yaz(el, kayit[id], false);
        });
        var skipped = 0;
        ids.forEach(function (id) { if (!oge(id)) skipped += 1; });
        return skipped;
    }

    function restoreCompositionRows(rows) {
        if (!Array.isArray(rows) || !rows.length) return;
        var container = document.getElementById('composition_rows');
        if (!container || typeof window.addCompositionRow !== 'function') return;
        container.innerHTML = '';
        rows.forEach(function (row) {
            window.addCompositionRow();
            var last = container.lastElementChild;
            if (!last) return;
            var compound = last.querySelector('.compound');
            var pct = last.querySelector('.percentage');
            if (compound) compound.value = row.compound != null ? row.compound : '';
            if (pct) pct.value = row.percentage != null ? row.percentage : '';
            if (compound) dispatchFieldEvents(compound);
            if (pct) dispatchFieldEvents(pct);
        });
    }

    // Güverte alanları DOMContentLoaded sonrasında panel kayıtlarıyla kurulur;
    // alanlar görünene dek kısa aralıklarla dener (montaj yarışı koruması)
    function restoreDockOverrides(overrides) {
        if (!overrides || !Object.keys(overrides).length) return;
        var tries = 0;
        var timer = setInterval(function () {
            tries += 1;
            var pending = 0;
            Object.keys(overrides).forEach(function (id) {
                var el = document.getElementById(id);
                if (!el) { pending += 1; return; }
                if (el.dataset.hrmaRestored === '1') return;
                el.value = String(overrides[id]);
                el.dataset.dirty = '1';
                el.dataset.hrmaRestored = '1';
            });
            if (!pending || tries > 40) clearInterval(timer);
        }, 250);
    }

    function applyProject(doc) {
        state.restoring = true;
        try {
            var inputs = doc.inputs || {};
            // P12aB4-24: açıklama geri yüklenir — yoksa bir sonraki kayıtta
            // sessizce SİLİNİYORDU (payload'a hiç girmediği için).
            state.description = String(doc.description || '');
            var descEl0 = document.getElementById('motor_description');
            if (descEl0) descEl0.value = state.description;
            restoreUiState(inputs.ui_state);
            var skipped = restoreFields(inputs.fields);
            if (inputs.dynamic && inputs.dynamic.composition_rows) {
                restoreCompositionRows(inputs.dynamic.composition_rows);
            }
            restoreDockOverrides(inputs.dock_overrides);
            // V301/K-C2 (NK-70, K-B AÇIK 3): sayfa, dosyanın HANGİ alanları
            // taşıdığını bilmeden eski kayıtların göçünü yapamaz (kayıtta
            // olmayan kip seçicisi varsayılana döner, değer sessizce düşerdi).
            // Olay geri yükleme bitmeden (restoring = true) yayılır; dinleyicinin
            // yazdığı alanlar kullanıcı düzenlemesi sayılmaz.
            try {
                document.dispatchEvent(new CustomEvent('hrma:project-applied', {
                    detail: { fields: Object.assign({}, inputs.fields || {}),
                              motor_type: doc.motor_type || null }
                }));
            } catch (e) { /* eski tarayıcı — sessiz */ }
            if (skipped > 0) {
                toast(TF('proj.loadedWithSkips', { n: skipped },
                    '{n} saved field(s) have no matching input on this page and were skipped.'),
                    'warn');
            }
        } finally {
            state.restoring = false;
        }
        state.dirty = false;
        // Geri yüklemenin tetiklediği sayfa işleyicileri (karışım yoğunluğu,
        // önizleme vb.) asenkron olay üretebilir — kısa tolerans penceresi
        // içinde gelen olaylar kullanıcı düzenlemesi sayılmaz (sahte yıldız).
        state.restoreGraceUntil = Date.now() + 800;
        renderBar();
    }

    // ==================================================================
    // HTTP
    // ==================================================================

    async function apiList() {
        var resp = await fetch('/api/projects');
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok || !data || !Array.isArray(data.projects)) {
            throw new Error((data && data.error) || ('HTTP ' + resp.status));
        }
        return data.projects;
    }

    async function apiSave(name, overwrite) {
        var resp = await fetch('/api/projects/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, payload: buildPayload(name),
                                   overwrite: !!overwrite }),
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok) {
            var err = new Error((data && data.error) || ('HTTP ' + resp.status));
            err.status = resp.status;
            throw err;
        }
        return data;
    }

    async function apiLoad(name) {
        var resp = await fetch('/api/projects/load/' + encodeURIComponent(name));
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok || !data || !data.project) {
            throw new Error((data && data.error) || ('HTTP ' + resp.status));
        }
        return data;
    }

    // ==================================================================
    // MODAL ALTYAPISI (update_check.js enjekte-modal deseni)
    // ==================================================================

    function closeModal() {
        var m = document.getElementById('hrmaProjectModal');
        if (m) m.remove();
    }

    function openModalShell(titleText) {
        closeModal();
        var wrap = document.createElement('div');
        wrap.id = 'hrmaProjectModal';
        wrap.style.cssText =
            'position:fixed; inset:0; z-index:99980; display:flex;' +
            'align-items:center; justify-content:center;' +
            'background:rgba(2,6,12,0.72); backdrop-filter:blur(4px);';
        var box = document.createElement('div');
        box.style.cssText =
            'max-width:560px; width:calc(100% - 48px); max-height:80vh;' +
            'overflow-y:auto; padding:22px 24px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2); font-family:var(--hd-sans, sans-serif);';
        var head = document.createElement('div');
        head.style.cssText =
            'font-size:14px; font-weight:700; letter-spacing:0.6px;' +
            'margin-bottom:12px; color:var(--hd-cyan, #00e5ff);' +
            'font-family:var(--hd-mono, monospace); text-transform:uppercase;';
        head.textContent = titleText;
        box.appendChild(head);
        wrap.appendChild(box);
        wrap.addEventListener('click', function (ev) {
            if (ev.target === wrap) closeModal();
        });
        document.body.appendChild(wrap);
        return box;
    }

    function modalButton(labelText, primary) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.style.cssText =
            'padding:9px 16px; font-size:13px; font-weight:600; cursor:pointer;' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            'font-family:var(--hd-sans, sans-serif);' +
            (primary
                ? 'border:none; background:var(--hd-cyan, #00e5ff); color:#04070d;'
                : 'background:transparent; color:var(--hd-ink, #cfe8f2);'
                  + 'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));');
        btn.textContent = labelText;
        return btn;
    }

    /* Ad soran modal (Save As / New) — onSubmit(name, description) yalnız
       geçerli adla çağrılır. ÖH D22 / P12aB4-24: sayfada `#motor_description`
       YOKSA (ölçüldü: /solid, /liquid) açıklama alanı BURADA sorulur;
       varsa sorulmaz — aynı veri iki yerde istenmez (tek kaynak). */
    function promptNameModal(titleText, defaultName, onSubmit, yeniProje) {
        var box = openModalShell(titleText);
        var label = document.createElement('div');
        label.style.cssText = 'font-size:13px; margin-bottom:6px;';
        label.textContent = T('proj.nameLabel', 'Project name');
        // v3.0.1 N-girdi-2: alan ipucu ortak bileşenden (field_help.js).
        if (window.HRMAHelp) window.HRMAHelp.attach(label, 'proj.help.name', T('proj.help.name', ''));
        var input = document.createElement('input');
        input.type = 'text';
        input.value = defaultName || '';
        input.maxLength = 80;
        input.style.cssText =
            'width:100%; box-sizing:border-box; padding:9px 10px; font-size:14px;' +
            'background:var(--hd-inset, rgba(6,14,26,0.85));' +
            'color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:var(--hd-radius-sm, 8px); margin-bottom:6px;';
        var rule = document.createElement('div');
        rule.style.cssText =
            'font-size:11.5px; color:var(--hd-ink-dim, #7d97a5); margin-bottom:12px;';
        rule.textContent = T('proj.nameRule',
            'Allowed: letters, digits, space, _ . - (1-80 chars; must not start '
            + 'with a dot or end with a dot/space).');
        var err = document.createElement('div');
        err.style.cssText =
            'display:none; font-size:12px; color:var(--hd-red, #ff5d73); margin-bottom:10px;';
        err.textContent = T('proj.nameInvalid', 'Invalid project name — check the naming rule.');
        // --- açıklama (yalnız sayfa alanı yokken) --------------------------
        var sayfaDesc = document.getElementById('motor_description');
        var descLabel = null, descIn = null;
        if (!sayfaDesc) {
            descLabel = document.createElement('div');
            descLabel.style.cssText = 'font-size:13px; margin-bottom:6px;';
            // Metin iç <span>'da çevrilir (data-i18n kabın textContent'ini
            // yazınca ipucunu silerdi); ipucu ortak bileşenden.
            var descMetin = document.createElement('span');
            descMetin.textContent = T('proj.descLabel',
                'Description (optional)');
            descMetin.setAttribute('data-i18n', 'proj.descLabel');
            descLabel.appendChild(descMetin);
            if (window.HRMAHelp) window.HRMAHelp.attach(descLabel, 'proj.help.desc', T('proj.help.desc', ''));
            descIn = document.createElement('textarea');
            // V301/DİL (NK-65): "Yeni Proje" boş açıklamayla başlar —
            // ölçüldü: açık örneğin açıklaması yeni projenin kutusuna
            // doluyordu. Farklı Kaydet'te mevcut açıklama korunur.
            descIn.value = yeniProje ? '' : String(state.description || '');
            descIn.rows = 2;
            descIn.maxLength = 400;
            descIn.style.cssText =
                'width:100%; box-sizing:border-box; padding:9px 10px;' +
                'font-size:13px; resize:vertical;' +
                'background:var(--hd-inset, rgba(6,14,26,0.85));' +
                'color:var(--hd-ink, #cfe8f2);' +
                'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
                'border-radius:var(--hd-radius-sm, 8px); margin-bottom:12px;';
        }
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:10px; justify-content:flex-end;';
        var okBtn = modalButton(T('common.ok', 'OK'), true);
        var cancelBtn = modalButton(T('proj.btnCancel', 'Cancel'), false);
        cancelBtn.onclick = closeModal;
        function submit() {
            var name = input.value.trim();
            if (!validName(name)) {
                // ÖH D20 / P12aB4-16: red GEREKÇESİ adlandırılır. Ayrılmış
                // aygıt adı kural metninde geçmiyor; genel "kurala bakın"
                // uyarısı kullanıcıyı doğru düzeltmeye götürmüyordu.
                var yasak = yasakKarakterler(name);
                err.textContent =
                    (WINDOWS_RESERVED.indexOf(name.toUpperCase()) !== -1)
                        ? T('proj.nameReserved',
                            'This name is reserved by Windows for a device '
                            + '(CON, PRN, AUX, NUL, COM1-9, LPT1-9) and cannot '
                            + 'be used as a file name.')
                        : (yasak.length
                            ? TF('proj.nameBadChars', {chars: yasak.join('  ')},
                                'Not allowed in a project name: {chars}')
                            : T('proj.nameInvalid',
                                'Invalid project name — check the naming rule.'));
                err.style.display = 'block';
                return;
            }
            closeModal();
            onSubmit(name, descIn ? String(descIn.value) : null);
        }
        okBtn.onclick = submit;
        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') submit();
        });
        row.appendChild(cancelBtn);
        row.appendChild(okBtn);
        box.appendChild(label);
        box.appendChild(input);
        box.appendChild(rule);
        box.appendChild(err);
        if (descLabel) { box.appendChild(descLabel); box.appendChild(descIn); }
        box.appendChild(row);
        input.focus();
        input.select();
    }

    function confirmModal(titleText, messageText, confirmLabel, onConfirm) {
        var box = openModalShell(titleText);
        var msg = document.createElement('div');
        msg.style.cssText = 'font-size:13.5px; line-height:1.55; margin-bottom:16px;';
        msg.textContent = messageText;
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; gap:10px; justify-content:flex-end;';
        var okBtn = modalButton(confirmLabel, true);
        var cancelBtn = modalButton(T('proj.btnCancel', 'Cancel'), false);
        cancelBtn.onclick = closeModal;
        okBtn.onclick = function () { closeModal(); onConfirm(); };
        row.appendChild(cancelBtn);
        row.appendChild(okBtn);
        box.appendChild(msg);
        box.appendChild(row);
    }

    // ==================================================================
    // KAYDET / AÇ / YENİ akışları
    // ==================================================================

    /* ÖH D22 / P12aB4-24 — sayfanın KENDİ motor adı kaynağı.
       ÖLÇÜLDÜ: `#motor_name` girdisi yalnız /hybrid'de var; /solid ve
       /liquid'de ad önerisi hep boşa düşüyordu. O iki sayfa adı zaten
       üretiyor ve dışa aktarma yolunda kullanıyor (`_solidMotorName` /
       `_liquidMotorName`); yeni bir kaynak UYDURULMAZ, var olan okunur.
       Fail-closed: çağrı hata verirse ya da dize dönmezse öneri yapılmaz. */
    var SAYFA_AD_KAYNAKLARI = ['_solidMotorName', '_liquidMotorName'];

    function pageMotorName() {
        for (var i = 0; i < SAYFA_AD_KAYNAKLARI.length; i++) {
            var fn = window[SAYFA_AD_KAYNAKLARI[i]];
            if (typeof fn !== 'function') continue;
            try {
                var v = fn();
                if (typeof v === 'string' && v.trim()) return v.trim();
            } catch (e) { /* sayfa henüz hesaplamadı: öneri yok */ }
        }
        return '';
    }

    function defaultNameSuggestion() {
        var el = document.getElementById('motor_name');
        var candidate = el ? String(el.value).trim() : '';
        if (candidate && validName(candidate)) return candidate;
        if (state.name) return state.name;
        var sayfa = pageMotorName();
        return validName(sayfa) ? sayfa : '';
    }

    async function doSave(name, overwrite) {
        try {
            var info = await apiSave(name, overwrite);
            state.name = info.name || name;
            state.savedName = state.name;
            state.dirty = false;
            state.savedResults = window.currentResults || null;
            unsavedRunClear();
            renderBar();
            toast(TF('proj.saved', { name: state.name }, 'Project "{name}" saved.'), 'ok');
        } catch (err) {
            if (err.status === 409) {
                // Aynı ad diskte var — üzerine yazma onayı (Save As önerisi)
                confirmModal(T('proj.saveAsTitle', 'Save Project As'),
                    TF('proj.exists', { name: name },
                       'A project named "{name}" already exists.') + ' '
                    + T('proj.overwriteQ', 'Overwrite the existing project?'),
                    T('proj.btnOverwrite', 'Overwrite'),
                    function () { doSave(name, true); });
                return;
            }
            console.error('HRMA project save failed:', err);
            toast(TF('proj.saveFailed', { message: srv(err.message) },
                     'Save failed: {message}'), 'err');
        }
    }

    function onSave() {
        if (state.name && state.savedName === state.name) {
            doSave(state.name, true);       // mevcut projeye kaydet
            return;
        }
        onSaveAs();
    }

    function onSaveAs() {
        promptNameModal(T('proj.saveAsTitle', 'Save Project As'),
            defaultNameSuggestion(),
            function (name, desc) {
                // P12aB4-24: pencerede açıklama soruldu ise kayda o girer.
                if (desc !== null && desc !== undefined) {
                    state.description = String(desc);
                }
                doSave(name, name === state.savedName);
            });
    }

    function onNew() {
        function start() {
            promptNameModal(T('proj.newTitle', 'New Project'), '', function (name) {
                try { sessionStorage.setItem(NEW_NAME_SS_KEY, name); }
                catch (e) { /* gizli mod */ }
                state.dirty = false;    // onay alındı; beforeunload tekrar sormasın
                location.href = location.pathname;      // temiz varsayılanlar
            }, true);
        }
        if (state.dirty) {
            // ÖH D20 / P12aB4-11: onay düğmesi nötr "TAMAM" idi; oysa bu
            // yol kaydedilmemiş değişiklikleri ATIYOR ve devam edilince
            // `state.dirty = false` ile tarayıcının kendi beforeunload
            // koruması da susturuluyor. Yıkıcı eylem, iptal kadar açık
            // adlandırılır (aynı dosyadaki `proj.btnOverwrite` deseni).
            confirmModal(T('proj.newTitle', 'New Project'),
                T('proj.unsavedWarn', 'You have unsaved changes. Continue and discard them?'),
                T('proj.btnDiscard', 'Discard changes'), start);
        } else {
            start();
        }
    }

    async function loadIntoPage(name) {
        try {
            var data = await apiLoad(name);
            var doc = data.project || {};
            var docType = doc.motor_type;
            if (docType && docType !== motorType && TYPE_PATH[docType]) {
                state.dirty = false;    // kullanıcı onayı alındı; ikinci (tarayıcı) uyarı çıkmasın
                location.href = TYPE_PATH[docType] + '?project=' + encodeURIComponent(name);
                return;
            }
            applyProject(doc);
            state.savedResults = window.currentResults || null;
            state.name = doc.name || name;
            state.savedName = state.name;
            renderBar();
            // ÖH D17 / P12aB4-02: sunucunun ÜRETTİĞİ yükleme uyarıları (ör.
            // "başka bir sürümle kaydedilmiş") yalnız console.warn'a
            // basılıyordu; ekranda görünen tek şey yeşil "yüklendi"
            // bildirimiydi. Uyarı sunucu tarafından kazanılmış bir hükümdür,
            // kullanıcıdan saklanamaz — her uyarı ekrana da basılır ve
            // başarı bildirimi bu durumda "uyarılarla yüklendi" der.
            // V3 KK 2. tur (REL D-5): metin kod + parametreden (EN = TR).
            var kayitlar = yuklemeUyariKayitlari(data);
            var uyarilar = [];
            (Array.isArray(data.warnings) ? data.warnings : []).forEach(function (w, i) {
                if (w == null || w === '') return;
                uyarilar.push(yuklemeUyariMetni(String(w),
                                                kayitlar ? kayitlar[i] : null));
            });
            uyarilar.forEach(function (w) {
                console.warn('HRMA project:', w);
                toast(String(w), 'warn');
            });
            try {
                var url = location.pathname + '?project=' + encodeURIComponent(state.name);
                history.replaceState(null, '', url);
            } catch (e) { /* dosya protokolü vb. */ }
            toast(uyarilar.length
                ? TF('proj.loadedWithWarnings', { name: state.name, n: uyarilar.length },
                     'Project "{name}" loaded with {n} warning(s) — see above.')
                : TF('proj.loaded', { name: state.name }, 'Project "{name}" loaded.'),
                uyarilar.length ? 'warn' : 'ok');
        } catch (err) {
            console.error('HRMA project load failed:', err);
            toast(TF('proj.loadFailed', { message: srv(err.message) },
                     'Could not load project: {message}'), 'err');
        }
    }

    /* ÖH D21 / P12aB4-21 — ÖLÇÜLEN KUSUR: proje kartlarındaki sayılar
       doğrudan `toFixed` ile basılıyordu, yani HER dilde nokta ondalık
       ayırıcı. Ürünün geri kalanı TR kipinde virgül basar (I18N.number);
       Türkçe ekranda aynı sayfada hem "207,1" hem "207.1" görünüyordu.
       Biçim TEK KAYNAKTAN gelir: I18N.number. Sözlük motoru yüklenmemişse
       (ör. çıplak birim testi) toFixed'e düşülür — sayı yine basılır. */
    function nf(value, digits) {
        return (window.I18N && window.I18N.number)
            ? window.I18N.number(value, digits)
            : value.toFixed(digits);
    }

    function summaryMini(summary, motorTypeOfSummary) {
        if (!summary) return '';
        var bits = [];
        if (typeof summary.thrust_N === 'number' && isFinite(summary.thrust_N)) {
            bits.push('F ' + nf(summary.thrust_N, 0) + ' N');
        }
        if (typeof summary.peak_thrust_N === 'number' && isFinite(summary.peak_thrust_N)) {
            bits.push('Fpk ' + nf(summary.peak_thrust_N, 0) + ' N');
        }
        if (typeof summary.isp_s === 'number' && isFinite(summary.isp_s)) {
            // v3.0.1 UI-K (NK-26 ek): listedeki Isp'nin hangisi olduğu
            // yazmıyordu (katı/sıvı deniz seviyesi, hibrit tasarım noktası).
            // Taban kayıttaysa ondan; değilse motor tipinden — özet
            // yazıcısı (serializeResultsSummary) isp_s'yi v2.5.5'ten
            // (f812b524b) beri değişmeden katı/sıvıda isp_sea_level,
            // hibritte motor.isp'den alır (git log -L ile doğrulandı).
            // Tip de taban da bilinmiyorsa etiket UYDURULMAZ.
            var ispTaban = (summary.isp_basis === 'sea_level'
                            || summary.isp_basis === 'design_point')
                ? summary.isp_basis
                : ({ solid: 'sea_level', liquid: 'sea_level',
                     hybrid: 'design_point' })[motorTypeOfSummary] || null;
            var ispMetni = 'Isp ' + nf(summary.isp_s, 1) + ' s';
            if (ispTaban === 'sea_level') {
                ispMetni += ' (' + T('proj.ispBasisSeaLevel', 'sea level') + ')';
            } else if (ispTaban === 'design_point') {
                ispMetni += ' (' + T('proj.ispBasisDesign', 'design point') + ')';
            }
            bits.push(ispMetni);
        }
        if (typeof summary.total_impulse_Ns === 'number' && isFinite(summary.total_impulse_Ns)) {
            bits.push('It ' + nf(summary.total_impulse_Ns, 0) + ' N·s');
        } else if (summary.burn_time_source === 'not_supplied') {
            // CW-D4: It yok ve çözücü nedenini künyeledi → neden basılır,
            // sayı basılmaz. Künye yoksa (eski kayıt) hiçbir şey eklenmez:
            // nedeni bilinmeyen yokluğa neden uydurulmaz.
            bits.push(T('proj.itNoBurnTime', 'It: burn time not supplied'));
        }
        // v3.0.1 (NK-26, son kullanıcı testi): listedeki özet ESKİ bir
        // sürümün koşusundan geliyordu (katı örnek "Fpk 1642 N · Isp 140,1 s"
        // ⟷ bugünkü hesap 1499,7 N · 125,4 s) ve bu hiçbir yerde
        // söylenmiyordu; kullanıcı sayıyı motorun bugünkü başarımı sanıyordu.
        // Özet başka sürümle hesaplandıysa sürümüyle söylenir; sürüm
        // bilinmiyorsa (damgasız eski kayıt) bu da söylenir. Güncel sürüm
        // sayfada yayımlanmıyorsa karşılaştırma yapılmaz.
        // Güncel sürüm: hibrit HRMA_VERSION, ana sayfa ve Fırlatma Sahası
        // HRMA_APP_VERSION yazar; ikisi de yoksa bilinmiyor (uydurulmaz).
        // Kod BİLEREK bu işlevin içinde: tests/test_d21_electron_a1.py
        // summaryMini gövdesini kaynaktan çıkarıp ayrı bir sandıkta koşuyor;
        // modül kapsamındaki bir yardımcı orada tanımsız kalır (ölçüldü).
        var simdi = window.HRMA_VERSION || window.HRMA_APP_VERSION;
        simdi = (typeof simdi === 'string' && simdi.trim()) ? simdi.trim() : null;
        if (bits.length && simdi) {
            var ozetSurum = (typeof summary.computed_with_version === 'string')
                ? summary.computed_with_version.trim() : '';
            if (!ozetSurum) {
                bits.push(T('proj.summaryVersionUnknown',
                    'computed with an older version'));
            } else if (ozetSurum !== simdi) {
                bits.push(TF('proj.summaryOldVersion', { version: ozetSurum },
                    'computed with v{version}'));
            }
        }
        return bits.join(' · ');
    }

    function projectRow(p) {
        var row = document.createElement('div');
        var corrupt = !!p.corrupt;
        row.style.cssText =
            'display:flex; gap:12px; align-items:baseline; flex-wrap:wrap;' +
            'padding:9px 10px; margin:4px 0; border:1px solid' +
            ' var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            (corrupt ? 'opacity:0.45; cursor:not-allowed;' : 'cursor:pointer;');
        var name = document.createElement('span');
        name.style.cssText =
            'font-weight:600; color:var(--hd-ink-strong, #eaf7fb); font-size:13.5px;';
        name.textContent = p.name;
        row.appendChild(name);
        var typeBadge = document.createElement('span');
        typeBadge.style.cssText =
            'font-family:var(--hd-mono, monospace); font-size:10.5px;' +
            'letter-spacing:0.08em; color:var(--hd-cyan, #00e5ff);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:5px; padding:1px 7px;';
        // ÖH D35 · OH-GT-33 — MAKİNE ADI CSS BÜYÜTMESİYLE BOZULUYORDU.
        // ÖLÇÜLDÜ (a1/once.json M3_buyutme): rozet metni ham enum
        // (`String(p.motor_type)` = "liquid") ve büyütme CSS'teydi; arayüz
        // Türkçeyken CSS `i→İ` kuralını uyguluyor ve rozet "LİQUİD"
        // yazıyordu (`tip_rozeti_tr_goruntu = "LİQUİD"`) — oysa bu, ucun
        // kendi makine değeridir, Türkçe bir sözcük değildir.
        // Büyütme CSS'ten JS'e alındı: `toUpperCase()` yerelden BAĞIMSIZDIR
        // (ECMA-262 Unicode varsayılanı, i→I). Bozuk kaydın etiketi sözlükten
        // gelir ve sözlükte ZATEN büyük yazılıdır (EN "CORRUPT", TR "BOZUK"),
        // o yüzden ona harf dönüşümü uygulanmaz — Türkçe sözcüğü
        // `toUpperCase()` ile büyütmek 'ı/İ' hatası üretirdi.
        // ÖH D37 · A1b dil-cozucu-nesri · DV-LIQUID — ÖLÇÜLDÜ (a1/once.json
        // DV-LIQUID): TR arayüzde rozet "LIQUID/SOLID/HYBRID" İngilizce
        // kalıyordu. Tanınan üç motor tipi sözlük etiketiyle basılır;
        // etiket sözlükte ZATEN büyük yazılıdır ('SIVI', 'HİBRİT') — Türkçe
        // sözcüğe `toUpperCase()` UYGULANMAZ (OH-GT-33 dersi). Tanınmayan
        // tip ham makine değeri olarak yerelden bağımsız büyütülür (eski
        // davranış; uydurma etiket yok). Eşleme bilerek bu gövdenin İÇİNDE:
        // bekçiler (test_d35_kabuk_2_a1) fonksiyon gövdesini söküp koşar.
        var tipEtiketi = {
            liquid: T('proj.typeLiquid', 'LIQUID'),
            solid: T('proj.typeSolid', 'SOLID'),
            hybrid: T('proj.typeHybrid', 'HYBRID')
        };
        typeBadge.textContent = corrupt
            ? T('proj.corrupt', 'CORRUPT')
            : (Object.prototype.hasOwnProperty.call(tipEtiketi, p.motor_type)
                ? tipEtiketi[p.motor_type]
                : String(p.motor_type || '?').toUpperCase());
        if (corrupt) typeBadge.style.color = 'var(--hd-red, #ff5d73)';
        row.appendChild(typeBadge);
        if (p.updated_at) {
            var date = document.createElement('span');
            date.style.cssText =
                'font-family:var(--hd-mono, monospace); font-size:11px;' +
                'color:var(--hd-ink-dim, #7d97a5);';
            date.textContent = String(p.updated_at).slice(0, 16).replace('T', ' ');
            row.appendChild(date);
        }
        var mini = summaryMini(p.results_summary, p.motor_type);
        if (mini) {
            var sum = document.createElement('span');
            sum.style.cssText =
                'font-family:var(--hd-mono, monospace); font-size:11px;' +
                'color:var(--hd-ink-dim, #7d97a5);';
            sum.textContent = mini;
            row.appendChild(sum);
        }
        if (corrupt) {
            // ÖH D23 / P17B4-05 — BOZUK SATIR ARTIK SESSİZ DEĞİL.
            // ÖLÇÜLDÜ (P17 B4, canlı; `KIRIK JSON` satırına tıklandı):
            // `toastlar: []`, `modal_acik: true`, URL değişmedi, form
            // değişmedi. Satır `cursor:not-allowed` + `opacity:0.45` ile
            // sönük çiziliyor, yani tıklama BİLEREK yutuluyordu; ama
            // kullanıcı neden açılmadığını söyleyen tek satırı alamıyordu.
            // Üstelik gerekçe ZATEN ÜRETİLİYOR: list_projects her bozuk
            // girdiye `reason` (ve çoğuna `reason_kind`) yazıyor
            // (hrma/utils/projects.py: 'unloadable file name: …',
            // 'Project file does not match the schema: …', okunamayan
            // dosya için ayrıştırıcı iletisi) — arayüz onu HİÇ basmıyordu.
            // Cümleyi SUNUCU yazar, panel türetmez (uydurma yasak);
            // gerekçe hiç gelmediyse bu da açıkça söylenir, sessiz
            // kalınmaz (fail-closed).
            row.setAttribute('data-corrupt', '1');
            row.addEventListener('click', function () {
                var neden = (typeof p.reason === 'string' && p.reason.trim())
                    ? srv(p.reason.trim())
                    : T('proj.corruptNoReason',
                        'the server did not name a reason');
                toast(TF('proj.corruptWhy', { name: p.name, reason: neden },
                         '"{name}" cannot be opened: {reason}'), 'err');
            });
        }
        if (!corrupt) {
            row.addEventListener('click', function () {
                closeModal();
                function go() {
                    if (p.motor_type && p.motor_type !== motorType
                        && TYPE_PATH[p.motor_type]) {
                        state.dirty = false;   // onay alındı; tarayıcı uyarısı yinelenmesin
                        location.href = TYPE_PATH[p.motor_type]
                            + '?project=' + encodeURIComponent(p.name);
                    } else {
                        loadIntoPage(p.name);
                    }
                }
                if (state.dirty) {
                    // ÖH D20 / P12aB4-11 — bkz. onNew(): yıkıcı onay adlandırılır.
                    confirmModal(T('proj.openTitle', 'Open Project'),
                        T('proj.unsavedWarn',
                          'You have unsaved changes. Continue and discard them?'),
                        T('proj.btnDiscard', 'Discard changes'), go);
                } else {
                    go();
                }
            });
        }
        return row;
    }

    async function onOpen() {
        var box = openModalShell(T('proj.openTitle', 'Open Project'));
        var status = document.createElement('div');
        status.style.cssText =
            'font-family:var(--hd-mono, monospace); font-size:12px;' +
            'color:var(--hd-ink-dim, #7d97a5); margin:4px 0;';
        status.textContent = T('common.loading', 'Loading…');
        box.appendChild(status);
        try {
            var projects = await apiList();
            status.remove();
            if (!projects.length) {
                var none = document.createElement('div');
                none.style.cssText = 'font-size:13px; color:var(--hd-ink-dim, #7d97a5);';
                none.textContent = T('proj.noProjects', 'No saved projects yet.');
                box.appendChild(none);
                return;
            }
            projects.forEach(function (p) { box.appendChild(projectRow(p)); });
        } catch (err) {
            console.error('HRMA project list failed:', err);
            status.textContent = TF('proj.listFailed', { message: srv(err.message) },
                'Could not load the project list: {message}');
            status.style.color = 'var(--hd-red, #ff5d73)';
        } finally {
            // V301/DİL (NK-3): "Proje Aç" penceresinde kapat/iptal düğmesi
            // yoktu (yalnız dış alana tıklama kapatıyordu). Liste, boş liste
            // ve hata hâlinde de görünür bir İptal düğmesi bulunur.
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; justify-content:flex-end; margin-top:12px;';
            var iptal = modalButton(T('proj.btnCancel', 'Cancel'), false);
            iptal.onclick = closeModal;
            row.appendChild(iptal);
            box.appendChild(row);
        }
    }

    // ==================================================================
    // ŞERİT (navbar altı ince bar) — yalnız tasarım sayfaları
    // ==================================================================

    var barEls = {};

    function renderBar() {
        if (!barEls.name) return;
        barEls.name.textContent = state.name || T('proj.untitled', 'Untitled');
        barEls.star.style.display = state.dirty ? 'inline' : 'none';
        barEls.source.textContent = state.source
            ? TF('proj.sourceStep', { source: state.source }, 'Source: {source}') : '';
    }

    function buildBar() {
        var navbar = document.querySelector('.navbar');
        if (!navbar || !navbar.parentNode) return;
        var bar = document.createElement('div');
        bar.id = 'hrmaProjectBar';
        bar.style.cssText =
            'display:flex; align-items:center; gap:10px; flex-wrap:wrap;' +
            'padding:7px 24px; background:rgba(4, 9, 17, 0.85);' +
            'border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'font-family:var(--hd-mono, monospace); font-size:0.78rem;';

        var label = document.createElement('span');
        label.style.cssText =
            'color:var(--hd-ink-faint, #6a8491); letter-spacing:0.1em;' +
            'text-transform:uppercase;';
        label.setAttribute('data-i18n', 'proj.label');
        label.textContent = T('proj.label', 'Project');
        bar.appendChild(label);

        var name = document.createElement('span');
        name.style.cssText = 'color:var(--hd-cyan-soft, #3af2ff); font-weight:600;';
        bar.appendChild(name);

        var star = document.createElement('span');
        star.style.cssText = 'color:var(--hd-orange, #ff8c33); display:none;';
        star.textContent = '*';
        // ÖH D21 / P12aB4-23: ipucu bir kez atanıyordu ve dil değişiminde
        // eski dilde kalıyordu (renderBar yalnız star.style.display ile
        // ilgileniyor). `data-i18n-title` I18N.apply'ın tazelediği kanaldır
        // (i18n.js translateElement); ilk değer yine burada basılır ki
        // sözlük geç yüklenirse düğüm boş kalmasın.
        star.setAttribute('data-i18n-title', 'proj.dirtyHint');
        star.title = T('proj.dirtyHint', 'Unsaved changes');
        bar.appendChild(star);

        var btnStyle =
            'padding:4px 12px; font-size:0.72rem; letter-spacing:0.05em; cursor:pointer;' +
            'background:transparent; color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
            'border-radius:6px; font-family:var(--hd-mono, monospace);';
        function barButton(key, labelText, handler) {
            var b = document.createElement('button');
            b.type = 'button';
            b.style.cssText = btnStyle;
            b.setAttribute('data-i18n', key);
            b.textContent = labelText;
            b.addEventListener('click', handler);
            bar.appendChild(b);
            return b;
        }
        barButton('proj.btnSave', T('proj.btnSave', 'Save'), onSave);
        barButton('proj.btnSaveAs', T('proj.btnSaveAs', 'Save As'), onSaveAs);
        barButton('proj.btnOpen', T('proj.btnOpen', 'Open'), onOpen);
        barButton('proj.btnNew', T('proj.btnNew', 'New'), onNew);
        barButton('proj.btnImportStep',
                  T('proj.btnImportStep', 'Import from CAD (STEP)'), function () {
            if (window.StepImportUI && window.StepImportUI.open) {
                window.StepImportUI.open();
            } else {
                toast(T('stepimp.notLoaded',
                    'STEP import module is not loaded on this page.'), 'err');
            }
        });

        var source = document.createElement('span');
        source.style.cssText =
            'margin-left:auto; color:var(--hd-ink-dim, #7d97a5); font-size:0.72rem;';
        bar.appendChild(source);

        navbar.parentNode.insertBefore(bar, navbar.nextSibling);
        barEls = { name: name, star: star, source: source };
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(bar);
        renderBar();
    }

    // ==================================================================
    // KİRLİ (dirty) TAKİBİ + beforeunload
    // ==================================================================

    function watchDirty() {
        function onEdit(ev) {
            if (state.restoring) return;
            var t = ev.target;
            if (state.restoring) return;    // geri yükleme olayları düzenleme değil
            if (Date.now() < (state.restoreGraceUntil || 0)) return;
            if (!t || !t.tagName) return;
            var tag = t.tagName.toUpperCase();
            if (tag !== 'INPUT' && tag !== 'SELECT' && tag !== 'TEXTAREA') return;
            if (t.id === 'langSelect') return;
            if (t.closest('#hrmaProjectBar, #hrmaProjectModal, #stepImportModal')) return;
            if (t.closest('#analysisDock')) {
                // Güvertede yalnız ad_f_* alanları projeye girer
                if (!/^ad_f_/.test(t.id || '')) return;
            } else if (t.closest('#sixDofPanel, #injectorPanel, #transientPanel')) {
                return;                     // dinamik panel alanları proje dışı
            }
            if (!state.dirty) {
                state.dirty = true;
                renderBar();
            }
        }
        document.addEventListener('input', onEdit, true);
        document.addEventListener('change', onEdit, true);
        window.addEventListener('beforeunload', function (ev) {
            if (!state.dirty) return undefined;
            ev.preventDefault();
            ev.returnValue = '';
            return '';
        });
    }

    // v3.0.1 UI-K (NK-26 ek) — kaydedilmemiş son hesap kaydı.
    function unsavedRunClear() {
        try {
            var ham = window.localStorage.getItem(UNSAVED_RUN_LS_KEY);
            var k = ham ? JSON.parse(ham) : null;
            // Yalnız BU sayfanın tipindeki kayıt silinir: başka tipte
            // kaydedilmeden bırakılmış hesap hâlâ kaydedilmemiştir.
            if (!k || k.motor_type === motorType) {
                window.localStorage.removeItem(UNSAVED_RUN_LS_KEY);
            }
        } catch (e) { /* gizli kip */ }
    }

    function unsavedRunRecordOnLeave() {
        var cr = window.currentResults;
        if (!cr || cr === state.savedResults) return;   // hesap yok ya da kaydedildi
        var ozet = serializeResultsSummary();
        if (!ozet) return;
        try {
            window.localStorage.setItem(UNSAVED_RUN_LS_KEY, JSON.stringify({
                format: 1,
                name: state.name || null,
                motor_type: motorType,
                summary: ozet,
            }));
        } catch (e) { /* gizli kip / dolu depo: kayıt yok, liste etkilenmez */ }
    }

    // ==================================================================
    // LANDING — Recent Projects şeridi (boşsa / uç yoksa hiç görünmez)
    // ==================================================================

    async function buildRecentStrip() {
        var projects;
        try {
            projects = await apiList();
        } catch (err) {
            console.warn('HRMA recent projects unavailable:', err.message);
            return;                          // uç yok / hata → şerit yok
        }
        var usable = projects.filter(function (p) { return !p.corrupt; }).slice(0, 5);
        // v3.0.1 UI-K (NK-26 ek, son kullanıcı): "liste kaydetmeden
        // güncelleniyor; hangi koşu, hangi Isp belli değil". Liste YALNIZ
        // diskteki kayıtlı projelerdir (kaydetme tarihiyle); tasarım
        // sayfasında kaydedilmeden bırakılan son hesap listeye KARIŞMAZ,
        // altında ayrı ve adıyla "kaydedilmedi" diye gösterilir.
        // Kayıt okuma bu gövdenin İÇİNDE: bekçiler (test_d35/test_d37)
        // gövdeyi söküp ayrı sandıkta koşuyor; yardımcı orada tanımsız kalır.
        var kaydedilmemis = null;
        try {
            var depo = (typeof window !== 'undefined') ? window.localStorage : null;
            var ham = depo ? depo.getItem('hrma.project.unsavedRun') : null;
            var adayKayit = ham ? JSON.parse(ham) : null;
            if (adayKayit && typeof adayKayit === 'object'
                && adayKayit.summary && typeof adayKayit.summary === 'object'
                && (adayKayit.name === null || (typeof adayKayit.name === 'string'
                                                && adayKayit.name.length <= 80))) {
                kaydedilmemis = adayKayit;
            }
        } catch (e) { kaydedilmemis = null; }   // gizli kip / bozuk kayıt → gösterilmez
        if (!usable.length && !kaydedilmemis) return;
        var container = document.querySelector('.container');
        if (!container) return;
        var section = document.createElement('div');
        section.id = 'hrmaRecentProjects';
        section.style.cssText = 'margin-top:46px;';
        var title = document.createElement('div');
        title.className = 'section-label';
        title.setAttribute('data-i18n', 'proj.recentTitle');
        title.textContent = T('proj.recentTitle', 'Recent Projects');
        section.appendChild(title);
        var list = document.createElement('div');
        list.style.cssText =
            'display:flex; gap:12px; flex-wrap:wrap; justify-content:center;';
        usable.forEach(function (p) {
            var a = document.createElement('a');
            var target = TYPE_PATH[p.motor_type] || '/hybrid';
            a.href = target + '?project=' + encodeURIComponent(p.name);
            a.className = 'aux-link';
            var mini = summaryMini(p.results_summary, p.motor_type);
            // ÖH D35 · OH-GT-33 — KULLANICININ YAZDIĞI AD BÜYÜTÜLMEZ.
            // ÖLÇÜLDÜ (a1/once.json M3_buyutme): şeridin kabı `.aux-link`,
            // index.html o sınıfa `text-transform: uppercase` veriyor
            // (`index_aux_link_uppercase = true`) ve ad CSS'te büyütülüyordu:
            //   "Example Liquid LOX-RP1 25kN"  → "EXAMPLE LİQUİD … 25KN"
            //   "Example Solid KNDX BATES 75mm"→ "EXAMPLE SOLİD … 75MM"
            // İki ayrı kayıp aynı anda: (a) SI simgeleri eziliyor — kN
            // (kilonewton) → KN, mm (milimetre) → MM diye bir simge YOK;
            // (b) Türkçe kipte `i→İ` kuralı kullanıcının yazdığı İngilizce
            // ada uygulanıyor ("LİQUİD"). Ölçüm İngilizce kipte de bozulma
            // gösterdi, yani bu yalnız bir `İ` sorunu değil.
            // KARAR (ana model, ÖH D35): kullanıcının yazdığı ad ekranda
            // YAZILDIĞI GİBİ durur. Tip rozeti ve özet parçası şeridin
            // görsel düzenine uymayı sürdürür (rozet zaten JS'te, yerelden
            // BAĞIMSIZ `toUpperCase` ile büyütülüyor).
            a.textContent = '';
            var adEl = document.createElement('span');
            adEl.style.textTransform = 'none';
            adEl.textContent = p.name;
            a.appendChild(adEl);
            var tipEl = document.createElement('span');
            tipEl.style.textTransform = 'none';
            // DV-LIQUID (ÖH D37 A1b): projectRow rozetiyle AYNI kural —
            // tanınan tip sözlük etiketi, tanınmayan ham makine değeri.
            var tipEtiketi = {
                liquid: T('proj.typeLiquid', 'LIQUID'),
                solid: T('proj.typeSolid', 'SOLID'),
                hybrid: T('proj.typeHybrid', 'HYBRID')
            };
            tipEl.textContent = ' [' + (Object.prototype.hasOwnProperty.call(
                    tipEtiketi, p.motor_type)
                ? tipEtiketi[p.motor_type]
                : String(p.motor_type || '?').toUpperCase()) + ']';
            a.appendChild(tipEl);
            // T75 (2026-08-03): index.html'in `.aux-link { text-transform:
            // uppercase }` kuralı ŞERİDİN TAMAMINI büyütüyordu. ÖLÇÜLDÜ: DOM
            // metni "Isp 207.1 s · It 13428 N·s" doğruyken ekranda
            // "ISP 207.1 S · IT 13428 N·S" görünüyordu. SI'da saniyenin simgesi
            // küçük 's'; büyük 'S' SIEMENS'tir — yani özgül impuls "207,1
            // siemens", toplam impuls "13428 newton-siemens" okunuyordu.
            // Simge büyük/küçük harfi anlam taşır (Fpk/Isp/It de öyle), bu
            // yüzden özet parçası kendi kabında dönüşümü kapatır. Proje adı ve
            // motor tipi rozeti şeridin görsel düzenine uysun diye dışarıda
            // kalır. Bekçi: tests/test_faz6_f5_app.py.
            if (mini) {
                var em = document.createElement('span');
                em.style.textTransform = 'none';
                em.setAttribute('data-si-units', '1');
                em.textContent = ' — ' + mini;
                a.appendChild(em);
            }
            // Hangi koşu: özet, projenin diske KAYDEDİLDİĞİ koşudur.
            if (p.updated_at) {
                var tarihEl = document.createElement('span');
                tarihEl.style.textTransform = 'none';
                var tarih = String(p.updated_at).slice(0, 16).replace('T', ' ');
                tarihEl.textContent = ' · ' + ((typeof TF === 'function')
                    ? TF('proj.savedAt', { date: tarih }, 'saved {date}')
                    : 'saved ' + tarih);
                a.appendChild(tarihEl);
            }
            list.appendChild(a);
        });
        section.appendChild(list);
        if (kaydedilmemis) {
            var kBaslik = document.createElement('div');
            kBaslik.className = 'section-label';
            kBaslik.setAttribute('data-i18n', 'proj.unsavedRunTitle');
            kBaslik.textContent = T('proj.unsavedRunTitle', 'Last calculation (not saved)');
            kBaslik.style.cssText = 'margin-top:22px;';
            section.appendChild(kBaslik);
            var kSatir = document.createElement('div');
            kSatir.id = 'hrmaUnsavedRun';
            kSatir.setAttribute('data-unsaved-run', '1');
            kSatir.style.cssText = 'display:flex; justify-content:center;';
            var kKutu = document.createElement('span');
            kKutu.className = 'aux-link';
            kKutu.style.cssText = 'cursor:default; text-transform:none;';
            var kTipEtiketi = {
                liquid: T('proj.typeLiquid', 'LIQUID'),
                solid: T('proj.typeSolid', 'SOLID'),
                hybrid: T('proj.typeHybrid', 'HYBRID')
            };
            var kTip = Object.prototype.hasOwnProperty.call(kTipEtiketi, kaydedilmemis.motor_type)
                ? kTipEtiketi[kaydedilmemis.motor_type] : '?';
            var kMini = summaryMini(kaydedilmemis.summary, kaydedilmemis.motor_type);
            kKutu.textContent = (kaydedilmemis.name || T('proj.untitled', 'Untitled'))
                + ' [' + kTip + ']' + (kMini ? ' — ' + kMini : '')
                + ' · ' + T('proj.notSaved', 'not saved');
            kSatir.appendChild(kKutu);
            section.appendChild(kSatir);
            var kNot = document.createElement('div');
            kNot.setAttribute('data-i18n', 'proj.unsavedRunNote');
            kNot.style.cssText = 'margin-top:6px; text-align:center; font-size:0.72rem;'
                + ' color:var(--hd-ink-dim, #7d97a5);';
            kNot.textContent = T('proj.unsavedRunNote',
                'This calculation was not saved; the list above shows saved projects only.');
            section.appendChild(kNot);
        }
        var aux = container.querySelector('.aux-links');
        if (aux) container.insertBefore(section, aux);
        else container.appendChild(section);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(section);
    }

    // ==================================================================
    // KURULUM
    // ==================================================================

    function initDesignPage() {
        buildBar();
        watchDirty();
        window.addEventListener('pagehide', unsavedRunRecordOnLeave);
        // Dil değişince serbest metinler (proje adı yer tutucusu, kaynak notu)
        // yeniden basılır; data-i18n taşıyan düğmeleri I18N.apply zaten çevirir
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(renderBar);
        // ?project=<ad> ile açıldıysa otomatik yükle
        var params = null;
        try { params = new URLSearchParams(location.search); } catch (e) { params = null; }
        var wanted = params ? params.get('project') : null;
        if (wanted) {
            loadIntoPage(wanted);
            return;
        }
        // "New" akışından gelen bekleyen ad
        try {
            var pending = sessionStorage.getItem(NEW_NAME_SS_KEY);
            if (pending) {
                sessionStorage.removeItem(NEW_NAME_SS_KEY);
                state.name = pending;
                state.savedName = null;
                renderBar();
                toast(TF('proj.newStarted', { name: pending },
                    'New project "{name}" — fill the form and press Save.'), 'info');
            }
        } catch (e) { /* gizli mod */ }
    }

    function init() {
        if (isLanding) {
            buildRecentStrip();
            // ÖH D21 / P12aB4-21 devamı: şerit bir kez kuruluyordu, dil
            // değişince içindeki sayılar eski ayırıcıda kalıyordu (metin
            // data-i18n taşımadığı için I18N.apply onlara erişemez).
            // Şerit yeniden kurulur; uç yoksa/boşsa yine hiç görünmez.
            if (window.I18N && window.I18N.onChange) {
                window.I18N.onChange(function () {
                    var eski = document.getElementById('hrmaRecentProjects');
                    if (!eski) return;          // şerit hiç kurulmadıysa dokunma
                    eski.parentNode.removeChild(eski);
                    buildRecentStrip();
                });
            }
        } else {
            initDesignPage();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Dış modüller için küçük API (step_import_ui "Apply to form" sonrası
    // köken notu düşer ve şeridi kirli işaretler)
    window.HRMAProjectBar = {
        setSource: function (text) {
            state.source = text ? String(text) : null;
            if (!state.restoring && text) state.dirty = true;
            renderBar();
        },
        markDirty: function () {
            state.dirty = true;
            renderBar();
        },
        // V301/K-C2: geri yükleme sürerken gelen input/change olayları
        // kullanıcı düzenlemesi değildir (sayfaların override sayımı okur).
        isRestoring: function () {
            return !!state.restoring;
        },
        // Test / hata ayıklama kancaları (saf yardımcılar)
        _validName: validName,
        _buildPayload: buildPayload,
        _state: state,
    };
})();
