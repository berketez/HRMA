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

    /* V301/DİL (NK-46): bağlantı tarayıcıda "hiçbir şey yapmıyordu" —
       sunucu PDF'i KENDİ makinesindeki görüntüleyicide açıyor (200,
       opened:true) ama sayfa bunu söylemiyordu; uzak sunucuda kılavuz
       kullanıcıya hiç ulaşmıyordu. Artık her sonuçta bildirim çıkar ve
       paketlenmiş PDF'in tarayıcı bağlantısı (Flask /static/docs/…) verilir. */
    function bildir(metin, href, hrefMetni) {
        var eski = document.getElementById('userGuideNotice');
        if (eski && eski.parentNode) eski.parentNode.removeChild(eski);
        var kutu = document.createElement('div');
        kutu.id = 'userGuideNotice';
        kutu.setAttribute('role', 'status');
        kutu.style.cssText = 'position:fixed; right:20px; bottom:20px; z-index:9999;'
            + ' max-width:380px; padding:10px 12px; border-radius:8px; font-size:13px;'
            + ' line-height:1.45; background:var(--hd-bg1, #0b1624);'
            + ' color:var(--hd-ink, #cfe8f2);'
            + ' border:1px solid var(--hd-line, rgba(0,229,255,0.3));';
        var govde = document.createElement('span');
        govde.textContent = metin;
        kutu.appendChild(govde);
        if (href) {
            var a = document.createElement('a');
            a.href = href; a.target = '_blank'; a.rel = 'noopener';
            a.textContent = hrefMetni;
            a.style.cssText = 'display:block; margin-top:6px; color:var(--hd-cyan, #00e5ff);';
            kutu.appendChild(a);
        }
        var kapat = document.createElement('button');
        kapat.type = 'button';
        kapat.textContent = T('guide.close', 'Close');
        kapat.style.cssText = 'margin-top:8px; cursor:pointer; font-size:12px;';
        kapat.onclick = function () {
            if (kutu.parentNode) kutu.parentNode.removeChild(kutu);
        };
        kutu.appendChild(kapat);
        document.body.appendChild(kutu);
    }

    function pdfAdresi(res) {
        var yol = res && typeof res.path === 'string' ? res.path : '';
        var ad = yol.split(/[\\/]/).pop();
        return ad ? '/static/docs/' + encodeURIComponent(ad) : null;
    }

    function openGuide() {
        var lang = String(currentLang()).toLowerCase().indexOf('tr') === 0 ? 'tr' : 'en';
        var tarayicida = T('guide.openInBrowser', 'Open the PDF in the browser');
        fetch('/api/user-guide/open?lang=' + lang, { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                var pdf = pdfAdresi(res);
                if (res.opened) {
                    bildir(T('guide.opened',
                        'The user guide PDF was opened in the PDF viewer of the computer running HRMA.'),
                        pdf, tarayicida);
                } else if (pdf) {
                    bildir(T('guide.notLaunched',
                        'No PDF viewer was launched by the server; open the user guide here:'),
                        pdf, tarayicida);
                } else if (res.url) {
                    bildir(T('guide.notPackaged',
                        'The user guide PDF is not packaged with this installation; the online copy:'),
                        res.url, res.url);
                    window.open(res.url, '_blank');
                }
            })
            .catch(function () {
                var url = 'https://github.com/berketez/HRMA/tree/main/docs/user_guide';
                bildir(T('guide.notPackaged',
                    'The user guide PDF is not packaged with this installation; the online copy:'),
                    url, url);
                window.open(url, '_blank');
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
