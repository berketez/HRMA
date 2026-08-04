/* HRMA hata bildirimi — bug_report.js
 * ---------------------------------------------------------------------------
 * Ayarlar panelindeki "Hata bildir" bölümünün VERİ katmanı. Kullanıcı arayüzü
 * settings_panel.js'te; burada yalnız gövde derleyici, ortam tespiti, günlük
 * yakalayıcı ve GitHub bağlantısı üretici yaşar (node ile tek başına
 * koşturulabilsin diye DOM'a olabildiğince az dokunur).
 *
 * TASARIM KARARI (2026-08-04) — GÖMÜLÜ TOKEN YOK
 *   Dağıtılan ikiliye bir GitHub belirteci gömmek onu herkese açık etmek
 *   demektir (ikili açılıp belirteç çıkarılır, depoya yazma yetkisi kötüye
 *   kullanılır). Bu yüzden HRMA kimsenin adına kayıt AÇMAZ. Akış:
 *
 *     form  →  önizleme (zorunlu)  →  ön-doldurulmuş issue URL'i yeni sekmede
 *              açılır  →  kullanıcı kendi GitHub hesabıyla gönderir.
 *
 * SÖZLEŞMELER
 *   1. ÖNİZLEME ZORUNLU. openIssue(), markPreviewed() ile işaretlenmemiş bir
 *      gövdeyi AÇMAZ ('warn.bugreport.preview_required'). Yani kullanıcının
 *      görmediği hiçbir metin GitHub'a taşınmaz.
 *   2. GÖNDERİLEN = GÖRÜLEN. URL sınırı (MAX_URL_CHARS) yüzünden kırpma
 *      gerekiyorsa kırpma ÖNİZLEMEDE yapılır; openIssue() kırpma gerektiren
 *      bir gövdeyi açmaz, çağırana kırpılmış metni geri verip yeniden
 *      önizleme ister.
 *   3. SAHTE VERİ YOK. Okunamayan alan uydurulmaz; gövdeye "bilinmiyor" +
 *      dayanak (hangi kaynaktan okunmaya çalışıldığı) yazılır. Ortam
 *      nesnesinin her alanının bir *_basis eşi vardır.
 *   4. KİŞİSEL BİLGİ TAŞINMAZ. Tanılama VARSAYILAN OLARAK KAPALIDIR; açıksa
 *      bile yalnız SAYISAL girdiler ve temizlenmiş konsol satırları eklenir.
 *      redact() ev dizini/kullanıcı adı, e-posta, dosya yolu ve uzun
 *      belirteç görünümlü dizileri kayıt anında siler — yani temizlenmemiş
 *      metin bellekte hiç tutulmaz.
 *
 * Sürüm okuma: sayfalar sürümü aynı biçimde yayımlamıyor (index.html
 * window.HRMA_APP_VERSION, advanced.html window.HRMA_VERSION, formulas.html
 * yalnız altbilgi metni; solid/liquid/launch_site hiç yayımlamıyor). Sırayla
 * denenir, hiçbiri yoksa "bilinmiyor" + dayanak yazılır — tahmin edilmez.
 */
(function (global) {
    'use strict';

    /* Tek kaynak: hedef depo yalnız burada yazılıdır. */
    var REPO = 'berketez/HRMA';
    var ISSUE_NEW_URL = 'https://github.com/' + REPO + '/issues/new';

    /* GitHub issue başlığı sınırı (GitHub'ın kendi sınırı). */
    var MAX_TITLE_CHARS = 256;
    /* Ön-doldurulmuş bağlantının güvenli üst sınırı. Tarayıcı/sunucu URL
       sınırları farklıdır; 8000 karakter yaygın olarak güvenli kabul edilir. */
    var MAX_URL_CHARS = 8000;

    var MAX_CONSOLE_ENTRIES = 20;    /* halka tampon derinliği */
    var MAX_ENTRY_CHARS = 400;       /* tek konsol satırının üst sınırı */
    var MAX_INPUT_FIELDS = 60;       /* girdi özetinde en çok kaç alan */

    function T(key, fallback) {
        return (global.I18N && global.I18N.t) ? global.I18N.t(key, fallback)
                                              : fallback;
    }
    function TF(key, params, fallback) {
        if (global.I18N && global.I18N.tf) {
            return global.I18N.tf(key, params, fallback);
        }
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    // -----------------------------------------------------------------------
    // Kişisel bilgi temizliği
    // -----------------------------------------------------------------------
    /* Yığın izlerinde ve konsol satırlarında sızabilecek kişisel izler:
       ev dizini + kullanıcı adı, e-posta, uzun belirteç görünümlü diziler.
       Kayıt ANINDA uygulanır; temizlenmemiş metin hiç saklanmaz. */
    var REDACTIONS = [
        [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, '<eposta>'],
        [/(\/Users\/)[^\/\\\s"')\]]+/g, '$1<kullanici>'],
        [/(\/home\/)[^\/\\\s"')\]]+/g, '$1<kullanici>'],
        [/([A-Za-z]:\\Users\\)[^\\\/\s"')\]]+/g, '$1<kullanici>'],
        [/(\/var\/folders\/)[^\s"')\]]+/g, '$1<gecici>'],
        /* 32+ karakterlik onaltılık/base64 görünümlü diziler (belirteç, anahtar) */
        [/\b[A-Za-z0-9_\-]{32,}\b/g, '<gizlendi>']
    ];

    function redact(text) {
        var out = String(text == null ? '' : text);
        for (var i = 0; i < REDACTIONS.length; i++) {
            out = out.replace(REDACTIONS[i][0], REDACTIONS[i][1]);
        }
        return out;
    }

    // -----------------------------------------------------------------------
    // Konsol hatası yakalayıcı (halka tampon)
    // -----------------------------------------------------------------------
    var _entries = [];
    var _installed = false;
    var _t0 = null;

    function _now() {
        return (global.Date && global.Date.now) ? global.Date.now() : 0;
    }

    function _stamp() {
        if (_t0 === null) return '+?s';
        var dt = (_now() - _t0) / 1000;
        return '+' + (dt < 0 ? 0 : dt).toFixed(1) + 's';
    }

    function recordError(kind, text) {
        var clean = redact(text);
        if (clean.length > MAX_ENTRY_CHARS) {
            clean = clean.slice(0, MAX_ENTRY_CHARS) + ' …';
        }
        _entries.push({ at: _stamp(), kind: String(kind), text: clean });
        while (_entries.length > MAX_CONSOLE_ENTRIES) _entries.shift();
        return _entries[_entries.length - 1];
    }

    function consoleErrors() {
        return _entries.slice();
    }

    function clearConsoleErrors() {
        _entries.length = 0;
    }

    function _argsToText(args) {
        var parts = [];
        for (var i = 0; i < args.length; i++) {
            var a = args[i];
            if (a && a.stack) { parts.push(String(a.stack)); continue; }
            if (a && typeof a === 'object') {
                try { parts.push(JSON.stringify(a)); }
                catch (e) { parts.push(Object.prototype.toString.call(a)); }
                continue;
            }
            parts.push(String(a));
        }
        return parts.join(' ');
    }

    /* Yakalayıcı yalnız KAYDEDER; hiçbir olayı yutmaz, console.error'un özgün
       davranışı korunur (sarmalayıcı önce kaydeder, sonra aslını çağırır). */
    function installErrorCapture() {
        if (_installed) return false;
        _installed = true;
        _t0 = _now();

        if (global.addEventListener) {
            global.addEventListener('error', function (ev) {
                if (!ev) return;
                var msg = ev.message || (ev.error && ev.error.message) || '';
                var where = '';
                if (ev.filename) {
                    where = ' (' + ev.filename + ':' + (ev.lineno || '?') + ')';
                }
                if (!msg && ev.target && ev.target.src) {
                    msg = 'resource failed: ' + ev.target.src;
                }
                recordError('error', msg + where);
            });
            global.addEventListener('unhandledrejection', function (ev) {
                var r = ev && ev.reason;
                var msg = (r && (r.stack || r.message)) || String(r);
                recordError('rejection', msg);
            });
        }

        var c = global.console;
        if (c && typeof c.error === 'function' && !c.error.__hrmaBugReport) {
            var orig = c.error;
            var wrapped = function () {
                try { recordError('console', _argsToText(arguments)); }
                catch (e) { /* kayıt hiçbir zaman konsolu bozmaz */ }
                return orig.apply(c, arguments);
            };
            wrapped.__hrmaBugReport = true;
            c.error = wrapped;
        }
        return true;
    }

    // -----------------------------------------------------------------------
    // Ortam tespiti — her alanın dayanağı beyan edilir
    // -----------------------------------------------------------------------
    var PATH_KIND = { '/hybrid': 'hybrid', '/solid': 'solid', '/liquid': 'liquid',
                      '/': 'home', '/formulas': 'formulas',
                      '/launch-site': 'launch-site' };

    function detectPage() {
        var loc = global.location;
        var path = (loc && loc.pathname) ? String(loc.pathname) : '';
        var norm = path.replace(/\/+$/, '') || '/';
        return { path: norm, kind: PATH_KIND[norm] || null,
                 basis: 'location.pathname' };
    }

    /* Sürüm: yayımlandığı yerler sayfadan sayfaya değişir, sırayla denenir. */
    function detectVersion() {
        if (global.HRMA_APP_VERSION) {
            return { value: String(global.HRMA_APP_VERSION),
                     basis: 'window.HRMA_APP_VERSION' };
        }
        if (global.HRMA_VERSION) {
            return { value: String(global.HRMA_VERSION),
                     basis: 'window.HRMA_VERSION' };
        }
        var doc = global.document;
        var footer = (doc && doc.querySelector) ? doc.querySelector('.footer')
                                                : null;
        if (footer) {
            var m = /\bv([0-9]+(?:\.[0-9A-Za-z\-]+)+)/.exec(footer.textContent || '');
            if (m) return { value: m[1], basis: '.footer' };
        }
        /* Uydurma yok: sürüm okunamadıysa açıkça söylenir. */
        return { value: null,
                 basis: 'window.HRMA_APP_VERSION / window.HRMA_VERSION / .footer' };
    }

    var OS_RULES = [
        [/Windows NT ([0-9._]+)/, 'Windows NT $1'],
        [/Mac OS X ([0-9._]+)/, 'macOS $1'],
        [/Macintosh/, 'macOS'],
        [/Android ([0-9._]+)/, 'Android $1'],
        [/(iPhone|iPad|iPod).*OS ([0-9._]+)/, 'iOS $2'],
        [/CrOS/, 'ChromeOS'],
        [/Linux/, 'Linux']
    ];
    var BROWSER_RULES = [
        [/Edg(?:e|A|iOS)?\/([0-9.]+)/, 'Edge $1'],
        [/OPR\/([0-9.]+)/, 'Opera $1'],
        [/Firefox\/([0-9.]+)/, 'Firefox $1'],
        [/Chrome\/([0-9.]+)/, 'Chrome $1'],
        [/Version\/([0-9.]+).*Safari/, 'Safari $1'],
        [/Safari\/([0-9.]+)/, 'WebKit $1']
    ];

    function _match(rules, ua) {
        for (var i = 0; i < rules.length; i++) {
            var m = rules[i][0].exec(ua);
            if (m) {
                return rules[i][1].replace(/\$(\d)/g, function (whole, n) {
                    return (m[Number(n)] || '').replace(/_/g, '.');
                }).trim();
            }
        }
        return null;
    }

    function collectEnvironment() {
        var nav = global.navigator || {};
        var ua = String(nav.userAgent || '');
        var ver = detectVersion();
        var page = detectPage();
        return {
            version: ver.value,
            version_basis: ver.basis,
            os: ua ? _match(OS_RULES, ua) : null,
            os_basis: ua ? 'navigator.userAgent' : 'navigator.userAgent (boş)',
            browser: ua ? _match(BROWSER_RULES, ua) : null,
            browser_basis: ua ? 'navigator.userAgent'
                              : 'navigator.userAgent (boş)',
            user_agent: redact(ua),
            page: page.path,
            page_kind: page.kind,
            page_basis: page.basis,
            ui_lang: (global.I18N && global.I18N.lang) ? String(global.I18N.lang)
                                                       : null,
            ui_lang_basis: 'I18N.lang'
        };
    }

    // -----------------------------------------------------------------------
    // Girdi özeti — YALNIZ sayısal alanlar
    // -----------------------------------------------------------------------
    /* Kişisel bilgi taşıyabilecek alan adları hiç okunmaz. Sayısal olmayan
       her değer zaten elenir; bu liste ikinci savunma hattıdır. */
    var PII_ID_RE =
        /(path|file|dir|folder|user|name|email|mail|token|key|secret|pass|project|author|note|comment|title|desc|address|phone)/i;

    function collectInputSummary(root) {
        var doc = root || global.document;
        if (!doc || !doc.querySelectorAll) {
            return { fields: [], basis: 'document.querySelectorAll yok',
                     skipped_non_numeric: 0 };
        }
        var nodes = doc.querySelectorAll('input');
        var fields = [];
        var skipped = 0;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            var id = String((n && (n.id || n.name)) || '');
            if (!id) { continue; }
            if (PII_ID_RE.test(id)) { continue; }
            var type = String((n.type || '')).toLowerCase();
            if (type === 'password' || type === 'file' || type === 'hidden') {
                continue;
            }
            var raw = (n.value === undefined || n.value === null) ? ''
                                                                  : String(n.value);
            if (raw === '') { continue; }
            var num = Number(raw);
            if (!isFinite(num)) { skipped += 1; continue; }
            fields.push({ id: id, value: num });
            if (fields.length >= MAX_INPUT_FIELDS) break;
        }
        return { fields: fields, basis: 'document.querySelectorAll("input")',
                 skipped_non_numeric: skipped };
    }

    // -----------------------------------------------------------------------
    // Markdown gövde derleyici
    // -----------------------------------------------------------------------
    function _blockOr(text) {
        var s = String(text == null ? '' : text).trim();
        return s === '' ? '_' + T('shell.bug.body.blank', '(not filled in)') + '_'
                        : s;
    }

    function _envValue(value, basis, unknownNote) {
        if (value) return value + '  _(' + basis + ')_';
        return '_' + T('shell.bug.body.unknown', 'unknown') + '_  _('
               + (unknownNote || basis) + ')_';
    }

    /* fields: {what, expected, steps}
       opts:   {diagnostics: bool, env, inputs, errors}
               env/inputs/errors verilmezse canlı sayfadan toplanır (test için
               enjekte edilebilir olsun diye ayrıldı). */
    function buildBody(fields, opts) {
        fields = fields || {};
        opts = opts || {};
        var env = opts.env || collectEnvironment();
        var L = [];

        L.push('### ' + T('shell.bug.body.what', 'What happened'));
        L.push('');
        L.push(_blockOr(fields.what));
        L.push('');
        L.push('### ' + T('shell.bug.body.expected', 'What was expected'));
        L.push('');
        L.push(_blockOr(fields.expected));
        L.push('');
        L.push('### ' + T('shell.bug.body.steps', 'Steps to reproduce'));
        L.push('');
        L.push(_blockOr(fields.steps));
        L.push('');

        L.push('### ' + T('shell.bug.body.env', 'Environment'));
        L.push('');
        L.push('- HRMA: ' + _envValue(
            env.version ? 'v' + env.version : null, env.version_basis,
            T('shell.bug.body.versionMissing',
              'this page does not expose the version')));
        L.push('- ' + T('shell.bug.body.os', 'Operating system') + ': '
               + _envValue(env.os, env.os_basis));
        L.push('- ' + T('shell.bug.body.browser', 'Browser') + ': '
               + _envValue(env.browser, env.browser_basis));
        L.push('- ' + T('shell.bug.body.page', 'Page') + ': ' + env.page
               + (env.page_kind ? ' (' + env.page_kind + ')' : '')
               + '  _(' + env.page_basis + ')_');
        L.push('- ' + T('shell.bug.body.uiLang', 'Interface language') + ': '
               + _envValue(env.ui_lang, env.ui_lang_basis));
        L.push('- User agent: `' + (env.user_agent || '?') + '`');
        L.push('');

        L.push('### ' + T('shell.bug.body.diagnostics', 'Diagnostics'));
        L.push('');
        if (!opts.diagnostics) {
            /* Kapalıyken hiçbir konsol satırı ve hiçbir girdi değeri gövdeye
               girmez — yalnız bu beyan kalır. */
            L.push('_' + T('shell.bug.body.diagnosticsOff',
                'Diagnostic information was not attached '
                + '(the reporter left the box unchecked).') + '_');
            return L.join('\n');
        }

        L.push('- ' + T('shell.bug.body.engine', 'Engine type') + ': '
               + _envValue(env.page_kind, env.page_basis));
        L.push('');

        var inputs = opts.inputs || collectInputSummary();
        L.push('#### ' + T('shell.bug.body.inputs', 'Numeric inputs')
               + ' (' + inputs.fields.length + ')');
        L.push('');
        if (!inputs.fields.length) {
            L.push('_' + T('shell.bug.body.inputsNone',
                'No numeric input was found on this page.') + '_');
        } else {
            L.push('| ' + T('shell.bug.body.field', 'Field') + ' | '
                   + T('shell.bug.body.value', 'Value') + ' |');
            L.push('| --- | --- |');
            for (var i = 0; i < inputs.fields.length; i++) {
                L.push('| ' + inputs.fields[i].id + ' | '
                       + inputs.fields[i].value + ' |');
            }
        }
        L.push('');

        var errs = opts.errors || consoleErrors();
        L.push('#### ' + T('shell.bug.body.console', 'Console errors')
               + ' (' + errs.length + ')');
        L.push('');
        if (!errs.length) {
            L.push('_' + T('shell.bug.body.consoleNone',
                'No console error was captured after this page loaded.') + '_');
        } else {
            L.push('```text');
            for (var j = 0; j < errs.length; j++) {
                L.push(errs[j].at + ' [' + errs[j].kind + '] ' + errs[j].text);
            }
            L.push('```');
            L.push('');
            L.push('_' + T('shell.bug.body.redactNote',
                'File paths, user names and e-mail addresses were removed '
                + 'from the log.') + '_');
        }
        return L.join('\n');
    }

    // -----------------------------------------------------------------------
    // GitHub bağlantısı
    // -----------------------------------------------------------------------
    function _url(title, body) {
        return ISSUE_NEW_URL
            + '?title=' + encodeURIComponent(String(title == null ? '' : title))
            + '&body=' + encodeURIComponent(String(body == null ? '' : body));
    }

    function _truncationNotice(removed) {
        return '\n\n---\n> ' + TF('shell.bug.body.truncated',
            { chars: removed, limit: MAX_URL_CHARS },
            'The diagnostic log was shortened by {chars} characters so the '
            + 'issue link stays under the {limit}-character URL limit.')
            + '\n> `warn.bugreport.body_truncated`';
    }

    /* Ön-doldurulmuş issue URL'ini üretir. Sınırı aşarsa gövdeyi SONDAN
       kısaltır (tanılama günlüğü sonda olduğu için önce o gider, kullanıcının
       kendi metni korunur) ve kısaltma beyanını ekler. */
    function buildIssueUrl(title, body) {
        title = String(title == null ? '' : title);
        body = String(body == null ? '' : body);
        var warnings = [];

        if (title.length > MAX_TITLE_CHARS) {
            title = title.slice(0, MAX_TITLE_CHARS);
            warnings.push({ code: 'warn.bugreport.title_truncated',
                            params: { limit: MAX_TITLE_CHARS } });
        }

        var url = _url(title, body);
        if (url.length <= MAX_URL_CHARS) {
            return { url: url, title: title, body: body, truncated: false,
                     removed_chars: 0, url_chars: url.length,
                     limit: MAX_URL_CHARS, warnings: warnings };
        }

        var fits = function (keep) {
            return _url(title, body.slice(0, keep)
                        + _truncationNotice(body.length - keep)).length
                   <= MAX_URL_CHARS;
        };
        /* İkili arama: baştan kaç karakter sığıyor? */
        var lo = 0, hi = body.length;
        while (lo < hi) {
            var mid = Math.ceil((lo + hi) / 2);
            if (fits(mid)) { lo = mid; } else { hi = mid - 1; }
        }
        var keep = lo;
        /* Beyan uzunluğu kalan sayısıyla değiştiği için arama sınırı tam
           tekdüze olmayabilir; sonucu doğrula, gerekirse daralt. */
        var guard = 0;
        while (keep > 0 && !fits(keep) && guard < 4096) { keep -= 1; guard += 1; }

        var removed = body.length - keep;
        var cut = body.slice(0, keep) + _truncationNotice(removed);
        var cutUrl = _url(title, cut);
        warnings.push({ code: 'warn.bugreport.body_truncated',
                        params: { chars: removed, limit: MAX_URL_CHARS } });
        return { url: cutUrl, title: title, body: cut, truncated: true,
                 removed_chars: removed, url_chars: cutUrl.length,
                 limit: MAX_URL_CHARS, warnings: warnings };
    }

    // -----------------------------------------------------------------------
    // Önizleme kilidi — görülmeyen metin gönderilemez
    // -----------------------------------------------------------------------
    var _seenTitle = null;
    var _seenBody = null;

    function markPreviewed(title, body) {
        _seenTitle = String(title == null ? '' : title);
        _seenBody = String(body == null ? '' : body);
    }
    function isPreviewed(title, body) {
        return _seenBody !== null
            && String(title == null ? '' : title) === _seenTitle
            && String(body == null ? '' : body) === _seenBody;
    }
    function resetPreview() { _seenTitle = null; _seenBody = null; }

    /* opener: test edilebilirlik için enjekte edilebilir; verilmezse
       window.open kullanılır. Dönüş: {opened, url, needs_preview, warnings}. */
    function openIssue(title, body, opener) {
        if (!isPreviewed(title, body)) {
            return { opened: false, needs_preview: true, url: null,
                     body: null, truncated: false, removed_chars: 0,
                     warnings: [{ code: 'warn.bugreport.preview_required',
                                  params: {} }] };
        }
        var built = buildIssueUrl(title, body);
        if (built.truncated) {
            /* Kırpılmış metin önizlemede GÖRÜLMEDİ — açmadan geri veriyoruz;
               çağıran yeniden önizletir (sözleşme 2). */
            return { opened: false, needs_preview: true, url: null,
                     body: built.body, truncated: true,
                     removed_chars: built.removed_chars,
                     warnings: built.warnings };
        }
        var open = opener;
        if (!open && typeof global.open === 'function') {
            open = function (u) { return global.open(u, '_blank', 'noopener'); };
        }
        var handle = null;
        if (open) {
            try { handle = open(built.url); } catch (e) { handle = null; }
        }
        return { opened: !!handle, needs_preview: false, url: built.url,
                 body: built.body, truncated: false, removed_chars: 0,
                 warnings: built.warnings };
    }

    global.HRMABugReport = {
        REPO: REPO,
        ISSUE_NEW_URL: ISSUE_NEW_URL,
        MAX_TITLE_CHARS: MAX_TITLE_CHARS,
        MAX_URL_CHARS: MAX_URL_CHARS,
        MAX_CONSOLE_ENTRIES: MAX_CONSOLE_ENTRIES,

        installErrorCapture: installErrorCapture,
        recordError: recordError,
        consoleErrors: consoleErrors,
        clearConsoleErrors: clearConsoleErrors,
        redact: redact,

        detectPage: detectPage,
        detectVersion: detectVersion,
        collectEnvironment: collectEnvironment,
        collectInputSummary: collectInputSummary,

        buildBody: buildBody,
        buildIssueUrl: buildIssueUrl,

        markPreviewed: markPreviewed,
        isPreviewed: isPreviewed,
        resetPreview: resetPreview,
        openIssue: openIssue
    };

    /* Yakalayıcı dosya yüklenir yüklenmez kurulur: gövdedeki günlük "bu betik
       yüklendikten SONRA" oluşan hataları kapsar (betik <head>'de yüklenen
       sayfalarda neredeyse tamamı, sayfa sonunda yüklenenlerde sonrası). */
    installErrorCapture();
})(typeof window !== 'undefined' ? window : this);
