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

    /* T72 (2026-08-03): Düğme YALNIZ `.nav-links` şeridine enjekte ediliyordu.
       ÖLÇÜLDÜ — /formulas: var; / (index): YOK; /launch-site: YOK. Kök neden:
       index.html'de şerit `.aux-links`, launch_site.html'de ise `#ls-topbar`
       adını taşıyor; ikisinde de `.nav-links` ve `#userGuideLink` bulunmuyor.
       Kılavuzun kendisi sağlamdı (POST /api/user-guide/open -> opened:true),
       yani iki sayfada erişilemeyen çalışan bir özellik vardı. Aşağıdaki
       tablo üç kabuğun da çapasını tanır; hiçbiri yoksa sessizce vazgeçilir
       (window.hrmaOpenUserGuide yine çağrılabilir). */
    var NAV_HOSTS = [
        // seçici,        bağlantı sınıfı, kendinden önce eklenecek eleman
        { host: '.nav-links', cls: '',         before: null },
        { host: '.aux-links', cls: 'aux-link', before: null },
        // Fırlatma sahası üst şeridinde "Uygulamaya dön" en sağda kalmalı:
        // yeni bağlantı ondan ÖNCE eklenir.
        { host: '#ls-topbar', cls: 'ls-link',  before: '.ls-link' }
    ];

    function injectNavLink() {
        for (var i = 0; i < NAV_HOSTS.length; i++) {
            var spec = NAV_HOSTS[i];
            var nav = document.querySelector(spec.host);
            if (!nav) continue;
            var a = document.createElement('a');
            a.id = 'userGuideLink';
            a.href = '#';
            if (spec.cls) a.className = spec.cls;
            a.setAttribute('data-shell-aux', '1');
            // İlk yardımcı bağlantı sağa yaslanır; sonrakiler yanına dizilir
            // (release_notes.js ve settings_panel.js aynı sözleşmeyi kullanır).
            // Yalnız `.nav-links` için geçerli: diğer iki şeritte yerleşim
            // kabın kendi kuralıyla (aux-links flex-wrap, ls-topbar spacer)
            // çözülüyor, marginLeft eklemek düzeni bozardı.
            if (spec.host === '.nav-links' && !nav.querySelector('[data-shell-aux]')) {
                a.style.marginLeft = 'auto';
            }
            var anchor = spec.before ? nav.querySelector(spec.before) : null;
            if (anchor) nav.insertBefore(a, anchor);
            else nav.appendChild(a);
            return a;
        }
        return null;
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
