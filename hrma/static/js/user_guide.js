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
       yani iki sayfada erişilemeyen çalışan bir özellik vardı.

       ÖH D18 / P12aB5-06: burada duran üç-çapa tablosu kardeş dosyalara
       (release_notes.js, settings_panel.js) taşınmamıştı ve o ikisi
       /launch-site'ta hiç çizilmiyordu. Tablo artık TEK YERDE tanımlıdır —
       release_notes.js `window.HRMA_SHELL_NAV` olarak yayımlar, bu dosya
       tüketir. Tablo yoksa (betik yüklenmemiş) sessizce vazgeçilir;
       window.hrmaOpenUserGuide yine çağrılabilir. */
    function injectNavLink() {
        var nav = window.HRMA_SHELL_NAV;
        if (!nav || typeof nav.inject !== 'function') return null;
        return nav.inject('userGuideLink');
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

    /* Yerel pencere menüsü (Help > "User Guide…") buradan tetikler.
       ÖH D22 / P12aB5-15: bu cümle 2026-09-04'e kadar YALANDI — menüde öge
       yoktu (`hrmaOpenUserGuide` packaging/launcher.py'de hiç geçmiyordu),
       yani "çapa bulunamazsa menü kurtarır" güvencesi karşılıksızdı. Öge
       eklendi (launcher.py `_menu_user_guide`, macOS + Windows Help
       menüleri); beyan artık ölçülebilir bir gerçeği söylüyor
       (tests/test_d22_electron_a1.py bunu bekçiye bağlar). */
    window.hrmaOpenUserGuide = openGuide;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
