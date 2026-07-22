/* HRMA sürüm notları modalı — release_notes.js
 *
 * Ana sayfadaki aux-links satırındaki "Sürüm Notları" bağlantısını
 * canlandırır: /api/changelog'dan paketle gelen changelog.json okunur,
 * koyu temalı bir modalda sürüm + tarih başlıklarıyla listelenir.
 *
 * Güvenlik: sürüm notu gövdesi önce HTML-escape edilir, sonra YALNIZ şu
 * üç dönüşüm uygulanır: '## ' başlık, '- ' madde imi, '**kalın**'.
 * Başka markdown işlenmez (XSS yüzeyi bilinçli olarak dar).
 *
 * Not gövdesi ham release metnidir, çeviri DENENMEZ; yalnız modal
 * başlığı/kapat düğmesi i18n anahtarlıdır (i18n_shell.js).
 */
(function () {
    'use strict';

    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
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
            renderNotes(v.notes || '')));
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
        body.appendChild(el('div',
            'font-size:13px;color:var(--hd-ink-dim, #7d97a5);',
            escapeHtml(T('shell.releaseNotes.loading', 'Loading release notes…'))));
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
        closeBtn.onclick = function () { wrap.remove(); };
        box.appendChild(closeBtn);

        wrap.addEventListener('click', function (ev) {
            if (ev.target === wrap) wrap.remove();
        });

        wrap.appendChild(box);
        document.body.appendChild(wrap);

        fetch('/api/changelog')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                body.innerHTML = '';
                var versions = (data && data.versions) || [];
                if (!versions.length) {
                    var empty = el('div',
                        'font-size:13px;color:var(--hd-ink-dim, #7d97a5);',
                        escapeHtml(T('shell.releaseNotes.empty', 'No release notes found.')));
                    empty.setAttribute('data-i18n', 'shell.releaseNotes.empty');
                    body.appendChild(empty);
                    return;
                }
                for (var i = 0; i < versions.length; i++) {
                    body.appendChild(buildVersionBlock(versions[i]));
                }
            })
            .catch(function () {
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

    // Yerel pencere menüsü (macOS Help > "Release Notes…") buradan tetikler
    window.hrmaShowReleaseNotes = openModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
