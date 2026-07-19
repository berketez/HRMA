/* HRMA otomatik güncelleme bildirimi.
 *
 * Sayfa açıldıktan kısa süre sonra /api/update/check çağrılır; yeni sürüm
 * varsa koyu temayla uyumlu bir modal gösterilir:
 *   [Şimdi güncelle]  → /api/update/download (sunucu Downloads'a indirir,
 *                        bitince kurulum dosyasını açar; ilerleme çubuğu
 *                        /api/update/status ile izlenir)
 *   [Daha sonra]      → modal kapanır, sonraki açılışta yine sorar
 *   [Bu sürümü atla]  → localStorage'a yazılır, o sürüm bir daha sorulmaz
 */
(function () {
    'use strict';

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

    var SKIP_KEY = 'hrma_update_skip';
    var POLL_MS = 700;

    function el(tag, style, html) {
        var node = document.createElement(tag);
        if (style) node.style.cssText = style;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    function buildModal(info) {
        var wrap = el('div',
            'position:fixed;inset:0;z-index:99990;display:flex;align-items:center;' +
            'justify-content:center;background:rgba(2,6,12,0.72);backdrop-filter:blur(4px);');
        wrap.id = 'hrma-update-modal';

        var box = el('div',
            'max-width:480px;width:calc(100% - 48px);padding:26px 28px;' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius, 14px);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));' +
            'color:var(--hd-ink, #cfe8f2);' +
            'font-family:var(--hd-sans, sans-serif);');

        box.appendChild(el('div',
            'font-size:15px;font-weight:700;letter-spacing:0.4px;margin-bottom:6px;' +
            'color:var(--hd-cyan, #00e5ff);',
            T('update.available', 'UPDATE AVAILABLE')));
        box.appendChild(el('div',
            'font-size:14px;line-height:1.55;margin-bottom:14px;' +
            'color:var(--hd-ink-strong, #eaf7fb);',
            TF('update.releasedHtml',
               { latest: '<b>' + escapeHtml(info.latest) + '</b>',
                 current: escapeHtml(info.current) },
               'HRMA {latest} has been released (installed version: {current}). '
               + 'Would you like to update now?')));

        if (info.notes) {
            var notes = el('div',
                'max-height:120px;overflow-y:auto;font-size:12px;line-height:1.5;' +
                'padding:10px 12px;margin-bottom:16px;white-space:pre-wrap;' +
                'background:var(--hd-inset, rgba(6,14,26,0.85));' +
                'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
                'border-radius:var(--hd-radius-sm, 8px);' +
                'color:var(--hd-ink-dim, #7d97a5);');
            notes.textContent = info.notes;
            box.appendChild(notes);
        }

        var progress = el('div', 'display:none;margin-bottom:14px;');
        var bar = el('div',
            'height:6px;border-radius:3px;overflow:hidden;' +
            'background:var(--hd-inset, rgba(6,14,26,0.85));');
        var fill = el('div',
            'height:100%;width:0%;transition:width 0.3s;' +
            'background:var(--hd-cyan, #00e5ff);');
        bar.appendChild(fill);
        var progressText = el('div',
            'font-size:12px;margin-top:6px;color:var(--hd-ink-dim, #7d97a5);', '');
        progress.appendChild(bar);
        progress.appendChild(progressText);
        box.appendChild(progress);

        var btnRow = el('div', 'display:flex;gap:10px;flex-wrap:wrap;');
        var btnBase =
            'flex:1;min-width:120px;padding:10px 14px;font-size:13px;font-weight:600;' +
            'border-radius:var(--hd-radius-sm, 8px);cursor:pointer;' +
            'font-family:var(--hd-sans, sans-serif);transition:opacity 0.15s;';
        var updateBtn = el('button', btnBase +
            'border:none;background:var(--hd-cyan, #00e5ff);color:#04070d;',
            T('update.btnNow', 'Update now'));
        var laterBtn = el('button', btnBase +
            'background:transparent;color:var(--hd-ink, #cfe8f2);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));',
            T('update.btnLater', 'Later'));
        var skipBtn = el('button', btnBase +
            'background:transparent;color:var(--hd-ink-faint, #46606d);border:none;' +
            'flex:0 1 auto;min-width:0;',
            T('update.btnSkip', 'Skip this version'));

        laterBtn.onclick = function () { wrap.remove(); };
        skipBtn.onclick = function () {
            try { localStorage.setItem(SKIP_KEY, info.latest); } catch (e) { /* özel mod */ }
            wrap.remove();
        };
        updateBtn.onclick = function () { startDownload(); };

        btnRow.appendChild(updateBtn);
        btnRow.appendChild(laterBtn);
        btnRow.appendChild(skipBtn);
        box.appendChild(btnRow);

        // Yedek indirme satırı — HER ZAMAN görünür. Uygulama içi indirme
        // yavaş/başarısız olduğunda (GitHub CDN, ağ) ya da kullanıcı kendi
        // indirme yöneticisini tercih ettiğinde tek tıkla sistem tarayıcısında
        // doğrudan indirir. Backend webbrowser.open olduğu için pywebview/exe
        // penceresi ve her tarayıcıda aynı çalışır.
        var manualRow = el('div',
            'margin-top:12px;font-size:12px;color:var(--hd-ink-dim, #7d97a5);');
        var manualLink = el('a',
            'color:var(--hd-cyan-soft, #6fd3e6);cursor:pointer;text-decoration:underline;',
            T('update.browserLink', 'download it in your browser'));
        manualRow.appendChild(document.createTextNode(
            T('update.slowPrefix', 'Slow or stuck? You can also ')));
        manualRow.appendChild(manualLink);
        manualRow.appendChild(document.createTextNode('.'));
        box.appendChild(manualRow);

        manualLink.onclick = function () { openInBrowser(); };

        wrap.appendChild(box);
        document.body.appendChild(wrap);

        function openInBrowser() {
            fetch('/api/update/open-download', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (res.opened) {
                        progress.style.display = 'block';
                        progressText.innerHTML = T('update.openedInBrowser',
                            'Opened in your browser — download the installer there, '
                            + 'then run it to update.');
                    } else if (res.url) {
                        // Sunucu tarayıcı açamadıysa istemci tarafını dene
                        window.open(res.url, '_blank');
                    }
                })
                .catch(function () {
                    if (info.page_url) window.open(info.page_url, '_blank');
                });
        }

        function startDownload() {
            updateBtn.disabled = true;
            updateBtn.style.opacity = '0.5';
            fetch('/api/update/download', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (!res.started) {
                        // platforma uygun asset yok → tarayıcıdan indirmeye düş
                        openInBrowser();
                        return;
                    }
                    progress.style.display = 'block';
                    progressText.textContent = T('update.downloading', 'Downloading…');
                    lastPct = -1;
                    stallStrikes = 0;
                    pollStatus();
                })
                .catch(function () {
                    progressText.innerHTML = T('update.startFailed',
                        'Could not start the download — try the browser link above.');
                    updateBtn.disabled = false;
                    updateBtn.style.opacity = '1';
                });
        }

        // İlerleme takılırsa (pct uzun süre artmazsa) tarayıcı seçeneğini öne çıkar
        var STALL_LIMIT = Math.round(20000 / POLL_MS); // ~20 sn ilerlemesiz
        var lastPct = -1;
        var stallStrikes = 0;
        var idleStrikes = 0;

        function highlightManual() {
            manualRow.style.color = 'var(--hd-ink-strong, #eaf7fb)';
            manualLink.style.fontWeight = '700';
        }

        function pollStatus() {
            fetch('/api/update/status')
                .then(function (r) { return r.json(); })
                .then(function (st) {
                    if (st.state === 'downloading') {
                        idleStrikes = 0;
                        fill.style.width = st.pct + '%';
                        // Takılma algılama: pct artmıyorsa say, eşiği geçince uyar
                        if (st.pct <= lastPct) {
                            stallStrikes += 1;
                            if (stallStrikes === STALL_LIMIT) {
                                highlightManual();
                                progressText.innerHTML = TF('update.slowProgress',
                                    { pct: st.pct },
                                    'Downloading… {pct}% — this looks slow. You can '
                                    + 'download it in your browser instead (link below).');
                            } else {
                                progressText.textContent = TF('update.progress',
                                    { pct: st.pct }, 'Downloading… {pct}%');
                            }
                        } else {
                            stallStrikes = 0;
                            lastPct = st.pct;
                            progressText.textContent = TF('update.progress',
                                { pct: st.pct }, 'Downloading… {pct}%');
                        }
                        setTimeout(pollStatus, POLL_MS);
                    } else if (st.state === 'done') {
                        fill.style.width = '100%';
                        progressText.innerHTML = T('update.done',
                            'Downloaded — the installer has been opened. '
                            + 'Close HRMA to complete the update.')
                            + '<br><span style="font-size:11px;">'
                            + T('update.fileLabel', 'File') + ': '
                            + escapeHtml(st.path) + '</span>';
                        laterBtn.textContent = T('common.ok', 'OK');
                    } else if (st.state === 'error') {
                        highlightManual();
                        progressText.innerHTML = TF('update.error',
                            { message: escapeHtml(st.error || '') },
                            'Download error: {message} — use the browser link below instead.');
                        updateBtn.disabled = false;
                        updateBtn.style.opacity = '1';
                    } else {
                        // 'idle' indirme başladıktan sonra görülüyorsa sunucu yeniden
                        // başlamış demektir — sonsuza dek dönme (2026-07-14 denetimi)
                        idleStrikes += 1;
                        if (idleStrikes > 5) {
                            highlightManual();
                            progressText.innerHTML = T('update.interrupted',
                                'Download was interrupted — try the browser link below.');
                            updateBtn.disabled = false;
                            updateBtn.style.opacity = '1';
                            return;
                        }
                        setTimeout(pollStatus, POLL_MS);
                    }
                })
                .catch(function () { setTimeout(pollStatus, POLL_MS * 2); });
        }
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function toast(msg) {
        var old = document.getElementById('hrma-update-toast');
        if (old) old.remove();
        var t = el('div',
            'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);' +
            'z-index:99991;padding:12px 22px;font-size:13px;font-weight:600;' +
            'font-family:var(--hd-sans, sans-serif);' +
            'background:var(--hd-panel-solid, #0a1524);' +
            'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
            'border-radius:var(--hd-radius-sm, 8px);' +
            'color:var(--hd-ink-strong, #eaf7fb);' +
            'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));');
        t.id = 'hrma-update-toast';
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 4200);
    }

    function checkNow(force) {
        // force=true: kullanıcı menüden istedi — atlanan sürümü de göster,
        // güncel/hata durumunda sessiz kalma (toast bildir).
        fetch('/api/update/check')
            .then(function (r) { return r.json(); })
            .then(function (info) {
                if (!info.available || !info.latest) {
                    if (force) {
                        toast((info.error || !info.current)
                            ? T('update.unreachable', 'Could not reach the update server.')
                            : TF('update.upToDate', { version: info.current },
                                 'HRMA v{version} is up to date.'));
                    }
                    return;
                }
                if (!force) {
                    var skipped = null;
                    try { skipped = localStorage.getItem(SKIP_KEY); } catch (e) { /* özel mod */ }
                    if (skipped === info.latest) return;
                }
                if (document.getElementById('hrma-update-modal')) return;
                buildModal(info);
            })
            .catch(function () {
                if (force) toast(T('update.unreachable', 'Could not reach the update server.'));
            });
    }

    // Yerel pencere menüsü (macOS "Check for Updates…") buradan tetikler
    window.hrmaCheckForUpdates = checkNow;

    // Sayfa otursun, ağır grafikler yüklensin diye küçük gecikmeyle sor
    if (document.readyState === 'complete') {
        setTimeout(checkNow, 2500);
    } else {
        window.addEventListener('load', function () { setTimeout(checkNow, 2500); });
    }
})();
