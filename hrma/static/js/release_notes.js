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
    function renderNotes(md) {
        var lines = escapeHtml(md).split('\n');
        var out = [];
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var bolded = line.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
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
        if (v.date) {
            head.appendChild(el('span',
                'font-size:12px;color:var(--hd-ink-faint, #46606d);' +
                'font-family:var(--hd-mono, monospace);',
                escapeHtml(v.date)));
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
    function mountLink() {
        var link = document.getElementById('releaseNotesLink');
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
