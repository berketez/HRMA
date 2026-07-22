/* HRMA ayarlar paneli — settings_panel.js
 *
 * Ana sayfadaki aux-links satırındaki "Ayarlar" bağlantısıyla açılan koyu
 * temalı modal. YALNIZ gerçekten çalışan ayarlar vardır (sahte düğme yok):
 *
 *   1. Dil seçimi (EN/TR)      → I18N.setLang; localStorage.hrma_lang.
 *      Ana sayfadaki #langSelect ile I18N.onChange üzerinden eşzamanlı.
 *   2. Açılışta güncelleme     → localStorage.hrma_update_autocheck
 *      denetimi aç/kapa           ('on' varsayılan; 'off' ise update_check.js
 *                                  açılış denetimini atlar).
 *   3. Şimdi denetle           → /api/update/check; güncelse metin, yeni
 *                                  sürüm varsa update_check.js'in modal akışı
 *                                  (window.hrmaCheckForUpdates köprüsü).
 *   4. Atlanan sürümü sıfırla  → localStorage.hrma_update_skip silinir.
 *   5. Uygulama bilgisi        → sürüm ({{ app_version }} → window.HRMA_APP_VERSION)
 *                                  + GitHub bağlantısı.
 */
(function () {
    'use strict';

    var AUTOCHECK_KEY = 'hrma_update_autocheck';
    var SKIP_KEY = 'hrma_update_skip';
    var GITHUB_URL = 'https://github.com/berketez/HRMA';

    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    function lsGet(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }
    function lsSet(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* özel mod */ }
    }
    function lsRemove(key) {
        try { localStorage.removeItem(key); } catch (e) { /* özel mod */ }
    }

    function el(tag, style, html) {
        var node = document.createElement(tag);
        if (style) node.style.cssText = style;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function appVersion() {
        if (window.HRMA_APP_VERSION) return String(window.HRMA_APP_VERSION);
        // Yedek: footer'daki "HRMA vX.Y.Z" metninden oku
        var footer = document.querySelector('.footer');
        if (footer) {
            var m = /HRMA v([0-9][0-9A-Za-z.\-]*)/.exec(footer.textContent || '');
            if (m) return m[1];
        }
        return '?';
    }

    /* Bölüm başlığı + açıklama satırı üreten küçük yardımcılar */
    function sectionTitle(key, fallback) {
        var node = el('div',
            'font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;' +
            'margin:18px 0 8px;color:var(--hd-cyan-soft, #6fd3e6);' +
            'font-family:var(--hd-mono, monospace);',
            escapeHtml(T(key, fallback)));
        node.setAttribute('data-i18n', key);
        return node;
    }
    function descLine(key, fallback) {
        var node = el('div',
            'font-size:12px;line-height:1.5;margin-top:4px;' +
            'color:var(--hd-ink-faint, #46606d);',
            escapeHtml(T(key, fallback)));
        node.setAttribute('data-i18n', key);
        return node;
    }

    var SELECT_STYLE =
        'padding:7px 10px;font-size:13px;cursor:pointer;' +
        'background:var(--hd-inset, rgba(6,14,26,0.85));' +
        'color:var(--hd-ink-strong, #eaf7fb);' +
        'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
        'border-radius:var(--hd-radius-sm, 8px);' +
        'font-family:var(--hd-sans, sans-serif);';

    var BTN_STYLE =
        'padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;' +
        'background:transparent;color:var(--hd-ink, #cfe8f2);' +
        'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
        'border-radius:var(--hd-radius-sm, 8px);' +
        'font-family:var(--hd-sans, sans-serif);transition:opacity 0.15s;';

    function openModal() {
        if (document.getElementById('hrma-settings-modal')) return;

        var unsubscribe = null;

        var wrap = el('div',
            'position:fixed;inset:0;z-index:99985;display:flex;align-items:center;' +
            'justify-content:center;background:rgba(2,6,12,0.72);backdrop-filter:blur(4px);');
        wrap.id = 'hrma-settings-modal';

        function closeModal() {
            if (unsubscribe) unsubscribe();
            wrap.remove();
        }

        var box = el('div',
            'max-width:520px;width:calc(100% - 48px);max-height:80vh;overflow-y:auto;' +
            'padding:26px 28px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2);' +
            'font-family:var(--hd-sans, sans-serif);');

        var title = el('div',
            'font-size:15px;font-weight:700;letter-spacing:0.4px;margin-bottom:4px;' +
            'color:var(--hd-cyan, #00e5ff);',
            escapeHtml(T('shell.settings.title', 'SETTINGS')));
        title.setAttribute('data-i18n', 'shell.settings.title');
        box.appendChild(title);

        /* ---- 1. Dil ---- */
        box.appendChild(sectionTitle('shell.settings.language', 'Language'));

        var langRow = el('div', 'display:flex;align-items:center;gap:12px;');
        var langSel = el('select', SELECT_STYLE);
        var optEn = el('option', '', escapeHtml(T('lang.en', 'English')));
        optEn.value = 'en';
        optEn.setAttribute('data-i18n', 'lang.en');
        var optTr = el('option', '', escapeHtml(T('lang.tr', 'Türkçe')));
        optTr.value = 'tr';
        optTr.setAttribute('data-i18n', 'lang.tr');
        langSel.appendChild(optEn);
        langSel.appendChild(optTr);
        langSel.value = (window.I18N && window.I18N.lang) || 'en';
        langSel.disabled = typeof window.I18N === 'undefined';
        langSel.addEventListener('change', function () {
            if (window.I18N && window.I18N.setLang) window.I18N.setLang(langSel.value);
        });
        langRow.appendChild(langSel);
        box.appendChild(langRow);
        box.appendChild(descLine('shell.settings.languageDesc',
            'Interface language. The selector on the home page stays in sync.'));

        // Ana sayfadaki #langSelect ile çift yönlü eşzaman: setLang her yerden
        // çağrıldığında onChange yayılır; iki seçici de buradan tazelenir.
        if (window.I18N && window.I18N.onChange) {
            unsubscribe = window.I18N.onChange(function (lang) {
                langSel.value = lang;
                var mainSel = document.getElementById('langSelect');
                if (mainSel) mainSel.value = lang;
            });
        }

        /* ---- 2. Güncellemeler ---- */
        box.appendChild(sectionTitle('shell.settings.updates', 'Updates'));

        var autoRow = el('label',
            'display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;');
        var autoBox = document.createElement('input');
        autoBox.type = 'checkbox';
        autoBox.style.cssText = 'accent-color:var(--hd-cyan, #00e5ff);cursor:pointer;';
        autoBox.checked = lsGet(AUTOCHECK_KEY) !== 'off';   // 'on' varsayılan
        autoBox.addEventListener('change', function () {
            lsSet(AUTOCHECK_KEY, autoBox.checked ? 'on' : 'off');
        });
        var autoLabel = el('span', '',
            escapeHtml(T('shell.settings.autoCheck', 'Check for updates at startup')));
        autoLabel.setAttribute('data-i18n', 'shell.settings.autoCheck');
        autoRow.appendChild(autoBox);
        autoRow.appendChild(autoLabel);
        box.appendChild(autoRow);
        box.appendChild(descLine('shell.settings.autoCheckDesc',
            'When off, HRMA does not contact the update server at startup.'));

        var checkRow = el('div',
            'display:flex;align-items:center;gap:12px;margin-top:12px;flex-wrap:wrap;');
        var checkBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.settings.checkNow', 'Check now')));
        checkBtn.setAttribute('data-i18n', 'shell.settings.checkNow');
        var checkStatus = el('div',
            'font-size:12px;color:var(--hd-ink-dim, #7d97a5);flex:1;min-width:160px;', '');
        checkRow.appendChild(checkBtn);
        checkRow.appendChild(checkStatus);
        box.appendChild(checkRow);

        checkBtn.addEventListener('click', function () {
            checkBtn.disabled = true;
            checkBtn.style.opacity = '0.5';
            checkStatus.textContent = T('shell.settings.checking', 'Checking…');
            fetch('/api/update/check')
                .then(function (r) { return r.json(); })
                .then(function (info) {
                    checkBtn.disabled = false;
                    checkBtn.style.opacity = '1';
                    if (info.available && info.latest) {
                        checkStatus.textContent = TF('shell.settings.updateFound',
                            { version: info.latest },
                            'New version found: v{version} — opening the update window.');
                        // Mevcut modal akışı (update_check.js köprüsü, force=true:
                        // atlanan sürüm de gösterilir)
                        if (window.hrmaCheckForUpdates) window.hrmaCheckForUpdates(true);
                    } else if (info.current && !info.error) {
                        checkStatus.textContent = TF('shell.settings.upToDate',
                            { version: info.current }, 'You are up to date: v{version}');
                    } else {
                        checkStatus.textContent = T('shell.settings.checkFailed',
                            'Could not reach the update server.');
                    }
                })
                .catch(function () {
                    checkBtn.disabled = false;
                    checkBtn.style.opacity = '1';
                    checkStatus.textContent = T('shell.settings.checkFailed',
                        'Could not reach the update server.');
                });
        });

        var skipRow = el('div',
            'display:flex;align-items:center;gap:12px;margin-top:12px;flex-wrap:wrap;');
        var skipBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.settings.skipReset', 'Reset skipped version')));
        skipBtn.setAttribute('data-i18n', 'shell.settings.skipReset');
        var skipStatus = el('div',
            'font-size:12px;color:var(--hd-ink-dim, #7d97a5);flex:1;min-width:160px;', '');
        skipRow.appendChild(skipBtn);
        skipRow.appendChild(skipStatus);
        box.appendChild(skipRow);

        function refreshSkipRow() {
            var skipped = lsGet(SKIP_KEY);
            if (skipped) {
                skipBtn.disabled = false;
                skipBtn.style.opacity = '1';
                skipStatus.textContent = TF('shell.settings.skippedVersion',
                    { version: String(skipped).replace(/^v/, '') },
                    'Skipped version: v{version}');
            } else {
                skipBtn.disabled = true;
                skipBtn.style.opacity = '0.45';
                skipStatus.textContent = T('shell.settings.noSkipped',
                    'No skipped version.');
            }
        }
        refreshSkipRow();

        skipBtn.addEventListener('click', function () {
            lsRemove(SKIP_KEY);
            refreshSkipRow();
            skipStatus.textContent = T('shell.settings.skipCleared',
                'Skipped version cleared — it will be offered again.');
        });

        /* ---- 3. Uygulama bilgisi ---- */
        box.appendChild(sectionTitle('shell.settings.app', 'Application'));

        var infoRow = el('div',
            'display:flex;align-items:center;gap:16px;font-size:13px;flex-wrap:wrap;');
        var versionWrap = el('span', 'color:var(--hd-ink-strong, #eaf7fb);');
        var versionLabel = el('span', '',
            escapeHtml(T('shell.settings.version', 'Version')));
        versionLabel.setAttribute('data-i18n', 'shell.settings.version');
        versionWrap.appendChild(versionLabel);
        versionWrap.appendChild(document.createTextNode(': v' + appVersion()));
        infoRow.appendChild(versionWrap);

        var ghLink = el('a',
            'color:var(--hd-cyan-soft, #6fd3e6);text-decoration:underline;cursor:pointer;',
            escapeHtml(T('shell.settings.githubLink', 'HRMA on GitHub')));
        ghLink.setAttribute('data-i18n', 'shell.settings.githubLink');
        ghLink.href = GITHUB_URL;
        ghLink.target = '_blank';
        ghLink.rel = 'noopener';
        infoRow.appendChild(ghLink);
        box.appendChild(infoRow);

        /* ---- Kapat ---- */
        var closeBtn = el('button',
            BTN_STYLE + 'margin-top:22px;display:block;margin-left:auto;padding:10px 22px;',
            escapeHtml(T('shell.close', 'Close')));
        closeBtn.setAttribute('data-i18n', 'shell.close');
        closeBtn.onclick = closeModal;
        box.appendChild(closeBtn);

        wrap.addEventListener('click', function (ev) {
            if (ev.target === wrap) closeModal();
        });

        wrap.appendChild(box);
        document.body.appendChild(wrap);
    }

    /* aux-links'teki statik bağlantıyı canlandır (data-i18n niteliği burada:
       bkz. release_notes.js'teki not — anahtar i18n_shell.js'te yaşıyor).

       Çapa yoksa (alt sayfalar: solid/liquid/advanced/formulas — bunlarda
       index'in aux-links şeridi bulunmaz) gezinme şeridine kendi
       bağlantısını ekler. Böylece her sayfaya eklemek üç script etiketi
       olur, sayfa başına HTML cerrahisi gerekmez. Şerit de yoksa sessizce
       vazgeçilir (window.hrmaShowSettings yine çağrılabilir). */
    function mountLink() {
        var link = document.getElementById('settingsLink') || injectNavLink();
        if (!link) return;
        link.setAttribute('data-i18n', 'link.settings');
        link.textContent = T('link.settings', 'Settings');
        link.addEventListener('click', function (ev) {
            ev.preventDefault();
            openModal();
        });
    }

    /* Gezinme şeridine (.nav-links) bağlantı ekler ve döndürür. Aynı id iki
       kez oluşmasın diye önce varlık denetimi yapılır. */
    function injectNavLink() {
        var nav = document.querySelector('.nav-links');
        if (!nav) return null;
        var a = document.createElement('a');
        a.id = 'settingsLink';
        a.href = '#';
        a.setAttribute('data-shell-aux', '1');
        // Şeride eklenen İLK yardımcı bağlantı sağa yaslanır; sonrakiler
        // onun yanına dizilir (release_notes.js aynı sözleşmeyi kullanır).
        if (!nav.querySelector('[data-shell-aux]')) a.style.marginLeft = 'auto';
        nav.appendChild(a);
        return a;
    }

    window.hrmaShowSettings = openModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
