/* HRMA kullanma kılavuzu bağlantısı.
 *
 * Kılavuz iki dilde PDF olarak uygulamayla birlikte gelir
 * (hrma/static/docs/...). Bağlantı, arayüzün o anki diline uyan PDF'i
 * sistemin kendi görüntüleyicisinde açtırır: pywebview penceresi PDF
 * gösteremediği için dosya sunucu tarafında açılır (/api/user-guide/open).
 * Kılavuz paketlenmemişse (kaynaktan çalışma) depodaki sürüme yönlendirilir.
 */
(function () {
    'use strict';

    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }

    function currentLang() {
        if (window.I18N && window.I18N.lang) return window.I18N.lang;
        try {
            return localStorage.getItem('hrma_lang') || 'en';
        } catch (e) {
            return 'en';
        }
    }

    function openGuide() {
        var lang = String(currentLang()).toLowerCase().indexOf('tr') === 0 ? 'tr' : 'en';
        fetch('/api/user-guide/open?lang=' + lang, { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res.opened && res.url) window.open(res.url, '_blank');
            })
            .catch(function () {
                window.open('https://github.com/berketez/HRMA/tree/main/docs/user_guide',
                            '_blank');
            });
    }

    function injectNavLink() {
        var nav = document.querySelector('.nav-links');
        if (!nav) return null;
        var a = document.createElement('a');
        a.id = 'userGuideLink';
        a.href = '#';
        a.setAttribute('data-shell-aux', '1');
        // İlk yardımcı bağlantı sağa yaslanır; sonrakiler yanına dizilir
        // (release_notes.js ve settings_panel.js aynı sözleşmeyi kullanır).
        if (!nav.querySelector('[data-shell-aux]')) a.style.marginLeft = 'auto';
        nav.appendChild(a);
        return a;
    }

    function mountLink() {
        var link = document.getElementById('userGuideLink') || injectNavLink();
        if (!link) return;
        link.setAttribute('data-i18n', 'link.userGuide');
        link.textContent = T('link.userGuide', 'User Guide');
        link.addEventListener('click', function (ev) {
            ev.preventDefault();
            openGuide();
        });
    }

    // Yerel pencere menüsü (Help > "User Guide…") buradan tetikler
    window.hrmaOpenUserGuide = openGuide;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
