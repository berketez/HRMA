/* HRMA sürüm notları modalı — release_notes.js
 *
 * Ana sayfadaki aux-links satırındaki "Sürüm Notları" bağlantısını
 * canlandırır: /api/changelog'dan paketle gelen changelog.json okunur,
 * koyu temalı bir modalda sürüm + tarih başlıklarıyla listelenir.
 *
 * Çift dillilik (2026-07-22): changelog.json her sürüm için notes_en ve
 * notes_tr taşır. Modal, aktif arayüz dilini (window.I18N.lang) kullanarak
 * doğru dildeki gövdeyi seçer — Türkçe arayüzde Türkçe, İngilizce arayüzde
 * İngilizce. Modal açıkken dil değişirse (I18N.onChange) gövde yeni dilde
 * yeniden çizilir; modal kapalıyken değişirse bir sonraki açılışta yeni
 * dil gelir (openModal her açılışta aktif dili yeniden okur).
 *
 * Güvenlik: sürüm notu gövdesi önce HTML-escape edilir, sonra YALNIZ şu
 * üç dönüşüm uygulanır: '## ' başlık, '- ' madde imi, '**kalın**'.
 * Başka markdown işlenmez (XSS yüzeyi bilinçli olarak dar).
 *
 * Modal başlığı/kapat düğmesi gibi UI metinleri i18n anahtarlıdır
 * (i18n_shell.js) ve zaten çift dillidir.
 */
(function () {
    'use strict';

    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }

    /* Aktif arayüz dili ('en' | 'tr'); I18N yoksa İngilizce'ye düş. */
    function activeLang() {
        return (window.I18N && window.I18N.lang) || 'en';
    }

    /* Sürüm kaydından aktif dile uygun not gövdesini seç. Aktif dil yoksa
       diğer dile, o da yoksa (eski şema toleransı) düz 'notes'a düş — modal
       hiçbir durumda boş kalmasın. */
    function pickNotes(v) {
        if (!v) return '';
        var lang = activeLang();
        return v['notes_' + lang] || v.notes_en || v.notes_tr || v.notes || '';
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

    /* Escape edilmiş metne dar markdown dönüşümü uygular (yalnız #, ##, -, **). */
    /* V301/DİL (NK-2): sürüm notu satırları markdown'da YUMUŞAK kırılır;
       satır satır işlenince satıra bölünmüş vurgu ('**…\n…**', '*…*')
       düz yıldız olarak görünüyordu. Başlık/madde/boş satır olmayan satır
       bir öncekinin devamıdır ve ona eklenir; sonra vurgu işlenir. */
    function birlestir(ham) {
        var out = [];
        for (var i = 0; i < ham.length; i++) {
            var t = ham[i];
            var yeni = (t.trim() === '' || t.indexOf('#') === 0
                        || /^\s*- /.test(t));
            var onceki = out.length ? out[out.length - 1] : null;
            if (!yeni && onceki !== null && onceki.trim() !== ''
                    && onceki.indexOf('#') !== 0) {
                out[out.length - 1] = onceki.replace(/\s+$/, '') + ' ' + t.trim();
            } else {
                out.push(/^\s+- /.test(t) ? t.trim() : t);
            }
        }
        return out;
    }

    function vurgu(line) {
        return line.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
            .replace(/(^|[\s(])\*([^\s*](?:[^*\n]*[^\s*])?)\*(?=[\s).,;:!?]|$)/g,
                     '$1<i>$2</i>');
    }

    function renderNotes(md) {
        var lines = birlestir(escapeHtml(md).split('\n'));
        var out = [];
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var bolded = vurgu(line);
            if (line.indexOf('# ') === 0) {
                // Release gövdeleri "# HRMA vX.Y.Z" ile başlar; blok başlığı
                // sürümü zaten gösterdiği için ham '#' basmak yerine başlık yap.
                out.push('<div style="margin:2px 0 6px;font-weight:700;font-size:13px;' +
                         'color:var(--hd-ink-strong, #eaf7fb);">' +
                         bolded.slice(2) + '</div>');
            } else if (line.indexOf('## ') === 0) {
                out.push('<div style="margin:12px 0 4px;font-weight:700;' +
                         'color:var(--hd-ink-strong, #eaf7fb);">' +
                         bolded.slice(3) + '</div>');
            } else if (line.indexOf('- ') === 0) {
                out.push('<div style="padding-left:16px;position:relative;">' +
                         '<span style="position:absolute;left:2px;' +
                         'color:var(--hd-cyan, #00e5ff);">&#8226;</span>' +
                         bolded.slice(2) + '</div>');
            } else if (line.trim() === '') {
                out.push('<div style="height:6px;"></div>');
            } else {
                out.push('<div>' + bolded + '</div>');
            }
        }
        return out.join('');
    }

    function buildVersionBlock(v) {
        var block = el('div', 'margin-bottom:20px;');
        var head = el('div',
            'display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;' +
            'padding-bottom:6px;margin-bottom:8px;' +
            'border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));');
        head.appendChild(el('span',
            'font-size:14px;font-weight:700;letter-spacing:0.4px;' +
            'color:var(--hd-cyan, #00e5ff);',
            'v' + escapeHtml(v.version || '?')));
        /* ÖH D34 · OH-GT-18 — YAYIMLANMAMIŞ SÜRÜM YAYIN TARİHİ BASAMAZ.
           ÖLÇÜLDÜ (a1/once.json): en üst sürüm 2.6.27 başlıkta
           "2026-08-15" basıyordu; aynı sürümün başlığı ve gövdesi
           "in development / has NOT been published yet" diyor. Kullanıcı
           başlıktaki tarihe bakıp bir aylık yayımlanmış bir sürüm
           sanıyordu. Tarih kaydın kendisinden DÜŞTÜ (uydurma yasak,
           yayın günü o gün konur) ve yerine DURUM basılır.
           Fail-closed: `unreleased` değilse ama tarih de yoksa boş
           geçilmez — "kayıtlı değil" ADIYLA yazılır, sessiz boşluk yok. */
        var damgaStili = 'font-size:12px;font-family:var(--hd-mono, monospace);';
        if (v.unreleased === true) {
            head.appendChild(el('span',
                damgaStili + 'color:var(--hd-amber, #ffbe46);' +
                'letter-spacing:0.08em;text-transform:uppercase;',
                escapeHtml(T('release.status.unreleased',
                             'in development — not published yet'))));
        } else if (v.date) {
            head.appendChild(el('span',
                damgaStili + 'color:var(--hd-ink-faint, #6a8491);',
                escapeHtml(v.date)));
        } else {
            head.appendChild(el('span',
                damgaStili + 'color:var(--hd-ink-faint, #6a8491);',
                escapeHtml(T('release.status.noDate',
                             'release date not recorded'))));
        }
        block.appendChild(head);
        block.appendChild(el('div',
            'font-size:12.5px;line-height:1.6;color:var(--hd-ink-dim, #7d97a5);',
            renderNotes(pickNotes(v))));
        return block;
    }

    function openModal() {
        if (document.getElementById('hrma-release-notes-modal')) return;

        var wrap = el('div',
            'position:fixed;inset:0;z-index:99985;display:flex;align-items:center;' +
            'justify-content:center;background:rgba(2,6,12,0.72);backdrop-filter:blur(4px);');
        wrap.id = 'hrma-release-notes-modal';

        var box = el('div',
            'max-width:640px;width:calc(100% - 48px);max-height:76vh;display:flex;' +
            'flex-direction:column;padding:26px 28px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2);' +
            'font-family:var(--hd-sans, sans-serif);');

        var title = el('div',
            'font-size:15px;font-weight:700;letter-spacing:0.4px;margin-bottom:14px;' +
            'color:var(--hd-cyan, #00e5ff);',
            escapeHtml(T('shell.releaseNotes.title', 'RELEASE NOTES')));
        title.setAttribute('data-i18n', 'shell.releaseNotes.title');
        box.appendChild(title);

        var body = el('div',
            'flex:1;overflow-y:auto;min-height:80px;padding-right:6px;');
        var loading = el('div',
            'font-size:13px;color:var(--hd-ink-dim, #7d97a5);',
            escapeHtml(T('shell.releaseNotes.loading', 'Loading release notes…')));
        loading.setAttribute('data-i18n', 'shell.releaseNotes.loading');
        body.appendChild(loading);
        box.appendChild(body);

        var closeBtn = el('button',
            'margin-top:16px;align-self:flex-end;padding:10px 22px;font-size:13px;' +
            'font-weight:600;cursor:pointer;background:transparent;' +
            'color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            'font-family:var(--hd-sans, sans-serif);',
            escapeHtml(T('shell.close', 'Close')));
        closeBtn.setAttribute('data-i18n', 'shell.close');
        box.appendChild(closeBtn);

        // Getirilen sürümler; dil değişince yeniden çizim için saklanır.
        var loadedVersions = null;
        var unsubscribe = null;

        function close() {
            if (unsubscribe) { unsubscribe(); unsubscribe = null; }
            wrap.remove();
        }
        closeBtn.onclick = close;
        wrap.addEventListener('click', function (ev) {
            if (ev.target === wrap) close();
        });

        /* Gövdeyi aktif dilde (yeniden) çiz. Veri henüz gelmediyse yükleniyor
           metni durur; boş/hatalı durumda i18n anahtarlı mesaj gösterilir. */
        function renderBody() {
            if (loadedVersions === null) return;
            body.innerHTML = '';
            if (!loadedVersions.length) {
                var empty = el('div',
                    'font-size:13px;color:var(--hd-ink-dim, #7d97a5);',
                    escapeHtml(T('shell.releaseNotes.empty', 'No release notes found.')));
                empty.setAttribute('data-i18n', 'shell.releaseNotes.empty');
                body.appendChild(empty);
                return;
            }
            for (var i = 0; i < loadedVersions.length; i++) {
                body.appendChild(buildVersionBlock(loadedVersions[i]));
            }
        }

        // Modal açıkken dil değişirse: başlık/kapat metni data-i18n ile
        // I18N.apply() tarafından zaten tazelenir; not gövdelerini burada
        // elle yeni dilde yeniden çiziyoruz.
        if (window.I18N && window.I18N.onChange) {
            unsubscribe = window.I18N.onChange(function () { renderBody(); });
        }

        wrap.appendChild(box);
        document.body.appendChild(wrap);

        fetch('/api/changelog')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                loadedVersions = (data && data.versions) || [];
                renderBody();
            })
            .catch(function () {
                loadedVersions = null;
                body.innerHTML = '';
                var err = el('div',
                    'font-size:13px;color:var(--hd-ink-dim, #7d97a5);',
                    escapeHtml(T('shell.releaseNotes.error',
                                 'Release notes could not be loaded.')));
                err.setAttribute('data-i18n', 'shell.releaseNotes.error');
                body.appendChild(err);
            });
    }

    /* aux-links'teki statik bağlantıyı canlandır. data-i18n niteliği burada
       (statik HTML'de değil) verilir: index.html'in data-i18n anahtarları
       i18n.js ÇEKİRDEĞİNDE aranır (tests/test_i18n.py sözleşmesi), bu
       anahtar ise i18n_shell.js'te yaşar. */
    /* ---------------------------------------------------------------------
       KABUK ŞERİT TABLOSU — TEK TANIM (ÖH D18 / P12aB5-06)

       Ürün üç ayrı gezinme kabuğu kullanıyor: index.html `.aux-links`,
       motor/formül sayfaları `.nav-links`, launch_site.html `#ls-topbar`.
       Bu tabloyu yalnız `user_guide.js` tanıyordu (T72, 2026-08-03);
       `release_notes.js` ve `settings_panel.js` yalnız `.nav-links` sorup
       başarısız olunca SESSİZCE dönüyordu. ÖLÇÜLDÜ: /launch-site'ta iki
       bağlantı da hiç çizilmiyordu (betikler yüklü, çapa yok) — Ayarlar
       penceresi ve içindeki "Hata bildir" bölümü o sayfada hiçbir yoldan
       açılamıyordu; üstelik yerel pencere menüsünde de Ayarlar girdisi yok.

       Aynı tablonun üç kopyası tutulmaz: burada TEK kez tanımlanır ve
       `window.HRMA_SHELL_NAV` ile yayımlanır. Bu dosya altı ürün şablonunun
       HEPSİNDE kabuk betiklerinin İLKİDİR (ölçüldü, bkz.
       docs/scofield/raw/OH/D18/electron/a1/once_b5_06.json → yuklenme_sirasi),
       bu yüzden tüketiciler yüklenirken tablo hazırdır. Sıra
       tests/test_d18_electron_a1.py ile kilitlidir.

       Hiçbir çapa bulunamazsa sessizce vazgeçilir — pencere menüsünün
       çağırdığı window.hrma* API'leri yine çalışır. */
    var NAV_HOSTS = [
        // seçici,        bağlantı sınıfı, kendinden önce eklenecek eleman
        { host: '.nav-links', cls: '',         before: null },
        { host: '.aux-links', cls: 'aux-link', before: null },
        // Fırlatma sahası üst şeridinde "Uygulamaya dön" en sağda kalmalı:
        // yeni bağlantı ondan ÖNCE eklenir.
        { host: '#ls-topbar', cls: 'ls-link',  before: '.ls-link' }
    ];

    /* Tanınan ilk şeride `id` kimlikli bir yardımcı bağlantı ekler ve
       döndürür; hiçbir şerit yoksa null. */
    function injectShellNavLink(id) {
        for (var i = 0; i < NAV_HOSTS.length; i++) {
            var spec = NAV_HOSTS[i];
            var nav = document.querySelector(spec.host);
            if (!nav) continue;
            var a = document.createElement('a');
            a.id = id;
            a.href = '#';
            if (spec.cls) a.className = spec.cls;
            a.setAttribute('data-shell-aux', '1');
            // Şeride eklenen İLK yardımcı bağlantı sağa yaslanır; sonrakiler
            // onun yanına dizilir. Yalnız `.nav-links` için geçerli: diğer
            // iki şeritte yerleşim kabın kendi kuralıyla (aux-links
            // flex-wrap, ls-topbar spacer) çözülüyor.
            if (spec.host === '.nav-links'
                    && !nav.querySelector('[data-shell-aux]')) {
                a.style.marginLeft = 'auto';
            }
            var anchor = spec.before ? nav.querySelector(spec.before) : null;
            if (anchor) nav.insertBefore(a, anchor);
            else nav.appendChild(a);
            return a;
        }
        return null;
    }

    window.HRMA_SHELL_NAV = { HOSTS: NAV_HOSTS, inject: injectShellNavLink };

    function injectNavLink() {
        return injectShellNavLink('releaseNotesLink');
    }

    function mountLink() {
        var link = document.getElementById('releaseNotesLink') || injectNavLink();
        if (!link) return;
        link.setAttribute('data-i18n', 'link.releaseNotes');
        link.textContent = T('link.releaseNotes', 'Release Notes');
        link.addEventListener('click', function (ev) {
            ev.preventDefault();
            openModal();
        });
    }

    // Yerel pencere menüsü (macOS Help > "Release Notes…", Windows HRMA/Help
    // menüsü) buradan tetikler.
    window.hrmaShowReleaseNotes = openModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
