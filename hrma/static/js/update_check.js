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

    // -----------------------------------------------------------------------
    // Sürüm notlarının dili (v2.6.25 düzeltmesi, 2026-07-29 genişletmesi)
    //
    // SORUN: Güncelleme penceresindeki notlar sunucudan GitHub sürüm
    // GÖVDESİ olarak geliyor (update_checker.py -> release['body']). O gövde
    // tek dilde yazıldığı için Türkçe arayüzde "Güncellemek ister misiniz?"
    // sorusu Türkçe, hemen altındaki sürüm notu İngilizce çıkıyordu.
    //
    // Not gövdesi üç biçimde gelebilir; üçü de burada çözülür:
    //
    //   1. Sunucu dile AYRILMIŞ alan gönderir (info.notes_tr / info.notes_en).
    //      Tercih edilen yol: gövde sunucuda kırpılmadan önce bölündüğü için
    //      uzun notlarda da doğru dil gelir.
    //
    //   2. Gövde <!--HRMA-LANG:xx--> imlerini taşır (GitHub API yolu; imler
    //      packaging/release_notes_v*.md dosyasında durur ve publish_release.sh
    //      onları zorunlu kılar). İmlerden bölünür.
    //
    //   3. İm yok ama gövde iki dilli. Bu, API kotası dolduğunda devreye giren
    //      Atom yedek yolunda OLAĞAN durumdur: GitHub'ın ürettiği HTML,
    //      yorum satırlarını içermez (2026-07-29'da canlı releases.atom
    //      akışında ölçüldü — im sayısı 0), üstelik sunucudaki etiket
    //      temizliği de aynı imleri silerdi. Bölümler o zaman kendi
    //      "HRMA v<sürüm>" başlıklarından ayrılır ve hangi bölümün Türkçe
    //      olduğu Türkçe'ye özgü harflerden anlaşılır (yayın kapısı,
    //      İngilizce bölümde Türkçe harf bulunmamasını zorunlu kılar:
    //      tests/test_v262_release_gate.py).
    //
    // Hiçbiri tutmazsa gövde olduğu gibi gösterilir — elde tek metin odur,
    // gizlemek kullanıcıyı bilgisiz bırakır.
    // -----------------------------------------------------------------------
    var LANG_MARK = /<!--\s*HRMA-LANG:([a-z]{2})\s*-->/gi;
    // İm silinmiş gövdede dil bölümlerinin sınırı: her bölüm kendi sürüm
    // başlığıyla başlar ('# HRMA v2.6.25 — ...'; Atom yolunda '#' düşer).
    // V3.0.5 T-ÇAPA-C1: '#' imsiz satır ancak 'HRMA v<sürüm>' biçimindeyse
    // başlıktır — gövde cümlesi "HRMA 3.0.5 is a corrections release."
    // bölüm sınırı sayılıp tek dilli notu ikiye bölüyordu (ölçüldü,
    // tests/test_release_notes_language.py::test_tek_dilli_not_gizlenmez).
    // İkizi: hrma/utils/update_checker.py _SECTION_HEAD_RE.
    var SECTION_HEAD = /^[ \t]*(?:#{1,3}[ \t]*HRMA[ \t]+v?\d|HRMA[ \t]+v\d)/i;
    var TR_LETTERS = /[çğıİöşüÇĞÖŞÜ]/g;
    /* ÖH D22 / P12aB5-14 — İMSİZ GÖVDEDE SIRA KURALI (yedek ayraç).
       Türkçe harf sezgisi mutlak eşikli: Türkçe bölüm hiç Türkçe harf
       taşımazsa (ölçüldü: "Kod duzeltildi." gibi imsiz bir gövde) İKİ blok
       da 'en' sınıflanıyor, iki dil bulunamıyor ve Türkçe kullanıcıya
       İNGİLİZCE bölüm de dâhil bütün gövde basılıyordu. Yayın sözleşmesi
       sırayı sabitler: notlar ÖNCE İngilizce, SONRA Türkçe yazılır — imli
       her sürüm dosyasında ölçüldü (2.6.25 / 2.6.26 / 2.6.27) ve yayın
       kapısı imleri zorunlu kılar (tests/test_v262_release_gate.py::
       test_release_notes_are_bilingual_with_markers). Bu yüzden sezgi
       ayıramadığında sıra kuralı uygulanır; kural TEK yerde yazılıdır. */
    var SECTION_ORDER = ['en', 'tr'];

    function activeLang() {
        return (window.I18N && window.I18N.lang) ? window.I18N.lang : 'en';
    }

    /* Tek tük Türkçe harf (özel ad, alıntı) bölümü Türkçe yapmaz; birkaç
       satırlık gerçek Türkçe metinde bu harfler onlarca kez geçer. */
    function looksTurkish(text) {
        var hits = String(text || '').match(TR_LETTERS);
        return !!hits && hits.length >= 3;
    }

    function sectionsByMarker(text) {
        var bolumler = null;
        var son = null;
        var sonSonu = 0;
        var m;
        LANG_MARK.lastIndex = 0;
        while ((m = LANG_MARK.exec(text)) !== null) {
            bolumler = bolumler || {};
            if (son !== null) bolumler[son] = text.slice(sonSonu, m.index);
            son = m[1].toLowerCase();
            sonSonu = m.index + m[0].length;
        }
        if (son === null) return null;
        bolumler[son] = text.slice(sonSonu);
        return bolumler;
    }

    /* Yalnız GERÇEKTEN iki dilli gövdede bölme yapar: tek dilli bir not
       (eski sürümler, elle yazılmış kısa notlar) olduğu gibi kalsın diye
       iki dil de bulunamazsa null döner. */
    function sectionsByHeading(text) {
        var lines = String(text).split('\n');
        var bloklar = [];
        var cur = [];
        for (var i = 0; i < lines.length; i++) {
            if (SECTION_HEAD.test(lines[i]) && cur.length) {
                bloklar.push(cur.join('\n'));
                cur = [];
            }
            cur.push(lines[i]);
        }
        if (cur.length) bloklar.push(cur.join('\n'));
        if (bloklar.length < 2) return null;

        var bolumler = {};
        for (var j = 0; j < bloklar.length; j++) {
            var dil = looksTurkish(bloklar[j]) ? 'tr' : 'en';
            bolumler[dil] = bolumler[dil]
                ? bolumler[dil] + '\n' + bloklar[j] : bloklar[j];
        }
        if (bolumler.tr && bolumler.en) return bolumler;
        /* Sezgi ayıramadı. Blok sayısı yayın sözleşmesindeki dil sayısıyla
           BİREBİR eşleşiyorsa (iki blok = iki dil) sıra kuralına düşülür;
           eşleşmiyorsa (tek blok, ya da üç ve daha fazlası) gövde gerçekten
           iki dilli sayılmaz ve olduğu gibi gösterilir — uydurma bölme yok. */
        if (bloklar.length !== SECTION_ORDER.length) return null;
        var sirali = {};
        for (var k = 0; k < SECTION_ORDER.length; k++) {
            sirali[SECTION_ORDER[k]] = bloklar[k];
        }
        return sirali;
    }

    function pickLanguageSection(text) {
        if (!text) return '';
        var lang = activeLang();
        var bolumler = sectionsByMarker(text) || sectionsByHeading(text);
        if (!bolumler) return text;             // tek dilli gövde: aynen göster
        var secilen = bolumler[lang] || bolumler.en
            || bolumler[Object.keys(bolumler)[0]];
        return (secilen || '').trim();
    }

    /* Güncelleme yanıtından arayüz diline uyan not gövdesini seçer.
       Sunucunun dile ayrılmış alanları varsa onlar kazanır: gövde orada
       kırpılmadan önce bölünmüştür. */
    function notesForActiveLang(info) {
        if (!info) return '';
        var ayrilmis = info['notes_' + activeLang()];
        if (ayrilmis) return String(ayrilmis).trim();
        return pickLanguageSection(info.notes);
    }

    // -----------------------------------------------------------------------
    // Sürüm bilgisinin KAYNAĞI (ÖH D27 / OH-D26-18 — OH-B3-02'nin electron payı)
    //
    // ÖLÇÜLDÜ (`once.json`, node ikizi, iki dil): `/api/update/check` yanıtı
    // `source` alanını yayımlıyor ("api" | "page" | null) ama ne bu dosya ne
    // `settings_panel.js` onu basıyordu. Sonuç: GitHub Releases API'sinden
    // okunan sürüm ile, API'ye ULAŞILAMAYINCA devreye giren YEDEK SAYFA
    // KAZIMASINDAN okunan sürüm ekranda BİRBİRİNİN AYNIsıydı
    // (once.json: `ayirt_guncelleme_var = false`, `ayirt_guncel = false`).
    // Kazıma yolu HTML okur ve API'nin verdiği güvenceyi vermez; kullanıcı
    // "yeni sürüm var" / "güncelsiniz" cümlesinin hangi dayanakla kurulduğunu
    // göremeden karar veriyordu.
    //
    // FAIL-CLOSED: satır KOŞULSUZ basılır. Alan hiç gelmediyse (eski ya da
    // aracılı sunucu) veya adsızsa sessiz kalınmaz — "sunucu bildirmedi"
    // denir. Tanınmayan bir kod gelirse anlamı UYDURULMAZ, kod olduğu gibi
    // gösterilir.
    //
    // TEK KAYNAK: sözlük burada yaşar; ayarlar paneli ikinci bir tablo
    // yazmaz, `window.HRMAUpdateSource` köprüsünden okur.
    //
    // Anahtarlar `update.*` ailesindendir. ÖH D30 · OH-D21-06 ÖLÇÜMÜ: bu
    // ailenin sözlüğü `i18n_common.js`tir (bu dosyanın 25 anahtarının 24'ü
    // orada; i18n_shell.js yalnız 1'ini taşıyor). Buradaki eski satır
    // "sözlükte i18n_shell.js'te dururlar" diyordu — ölçümle yanlışlandı.
    // Sözlük artık `sozlukHazir` ile TALEP ÜZERİNE yüklenir.
    // -----------------------------------------------------------------------
    var SOURCE_TEXTS = {
        api: ['update.sourceApi',
              'Version data was read from the GitHub Releases API.'],
        page: ['update.sourcePage',
               'The Releases API could not be reached, so version data was '
               + 'read from the releases page instead (fallback path).']
    };

    /* Yanıttan kaynak beyanını çıkarır: {key, params, fallback}.
       Dizge DEĞİL anahtar döner, çünkü ayarlar paneli düğüme `data-i18n`
       koyup dil değişiminde tazeliyor (i18n.js sözleşmesi). */
    function sourceNote(info) {
        if (!info || !Object.prototype.hasOwnProperty.call(info, 'source')) {
            return { key: 'update.sourceMissing', params: null,
                     fallback: 'The server did not report where this version '
                               + 'information came from.' };
        }
        var kod = info.source;
        if (kod === null || kod === undefined || kod === '') {
            return { key: 'update.sourceNone', params: null,
                     fallback: 'The server reported no source for this '
                               + 'version information.' };
        }
        if (Object.prototype.hasOwnProperty.call(SOURCE_TEXTS, kod)) {
            return { key: SOURCE_TEXTS[kod][0], params: null,
                     fallback: SOURCE_TEXTS[kod][1] };
        }
        return { key: 'update.sourceOther', params: { code: String(kod) },
                 fallback: 'Version information source reported by the '
                           + 'server: {code} (unknown to this version).' };
    }

    /* Ayarlar paneli köprüsü (settings_panel.js) — sözlüğün TEK kopyası. */
    window.HRMAUpdateSource = sourceNote;

    function el(tag, style, html) {
        var node = document.createElement(tag);
        if (style) node.style.cssText = style;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    /* Kaynak beyanını i18n sözleşmesine uygun tek satır olarak basar. */
    function sourceRow(info, style) {
        var not = sourceNote(info);
        var node = el('div', style);
        node.setAttribute('data-i18n', not.key);
        if (not.params) {
            node.setAttribute('data-i18n-params', JSON.stringify(not.params));
            node.textContent = TF(not.key, not.params, not.fallback);
        } else {
            node.textContent = T(not.key, not.fallback);
        }
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

        // Sürüm iddiasının DAYANAĞI — koşulsuz (ÖH D27 / OH-D26-18).
        box.appendChild(sourceRow(info,
            'font-size:12px;line-height:1.5;margin:-8px 0 14px;' +
            'color:var(--hd-ink-dim, #7d97a5);'));

        var notesText = notesForActiveLang(info);
        if (notesText) {
            var notes = el('div',
                'max-height:120px;overflow-y:auto;font-size:12px;line-height:1.5;' +
                'padding:10px 12px;margin-bottom:16px;white-space:pre-wrap;' +
                'background:var(--hd-inset, rgba(6,14,26,0.85));' +
                'border:1px solid var(--hd-line, rgba(0,229,255,0.14));' +
                'border-radius:var(--hd-radius-sm, 8px);' +
                'color:var(--hd-ink-dim, #7d97a5);');
            notes.textContent = notesText;
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
            'background:transparent;color:var(--hd-ink-faint, #6a8491);border:none;' +
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
            'color:var(--hd-cyan-soft, #3af2ff);cursor:pointer;text-decoration:underline;',
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

        // İndirme bitti → sessiz otomatik kurulum. Sunucu "auto" derse
        // uygulama kendini kapatır, yardımcı betik kurar ve yeniden açar;
        // "manual" derse (kaynak kod, yazılamayan hedef) kurulum dosyası
        // açılmıştır, eski yönerge metni gösterilir.
        function startInstall(st) {
            progressText.textContent = T('update.installing',
                'Downloaded — preparing the installation…');
            fetch('/api/update/install', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (res.started && res.mode === 'auto') {
                        updateBtn.style.display = 'none';
                        laterBtn.style.display = 'none';
                        skipBtn.style.display = 'none';
                        manualRow.style.display = 'none';
                        // Kopyalama birkaç dakika sürüyor ve bu sırada ekranda
                        // hiçbir şey olmuyor; süreyi ve "elle açma" uyarısını
                        // açıkça yaz (2026-07-24 saha hatası: kullanıcı
                        // güncellemenin çöktüğünü sanıp eski sürümü açtı).
                        progressText.innerHTML = T('update.autoClose',
                            'HRMA will close now and reopen automatically when the '
                            + 'update is complete. This usually takes 2-4 minutes — '
                            + 'please do not open HRMA yourself meanwhile.');
                    } else if (res.started) {
                        progressText.innerHTML = T('update.done',
                            'Downloaded — the installer has been opened. '
                            + 'Close HRMA to complete the update.')
                            + '<br><span style="font-size:11px;">'
                            + T('update.fileLabel', 'File') + ': '
                            + escapeHtml(res.path || st.path) + '</span>';
                        laterBtn.textContent = T('common.ok', 'OK');
                    } else {
                        highlightManual();
                        progressText.innerHTML = T('update.installFailed',
                            'The installer could not be started — open the '
                            + 'downloaded file from your Downloads folder.')
                            + '<br><span style="font-size:11px;">'
                            + T('update.fileLabel', 'File') + ': '
                            + escapeHtml(st.path) + '</span>';
                    }
                })
                .catch(function () {
                    highlightManual();
                    progressText.innerHTML = T('update.installFailed',
                        'The installer could not be started — open the '
                        + 'downloaded file from your Downloads folder.');
                });
        }

        // İlerleme takılırsa (pct uzun süre artmazsa) tarayıcı seçeneğini öne çıkar
        var STALL_LIMIT = Math.round(20000 / POLL_MS); // ~20 sn ilerlemesiz
        var lastPct = -1;
        var stallStrikes = 0;
        var idleStrikes = 0;
        // ÖH D17 / P12aB5-02: /api/update/status ulaşılamadığında (sunucu
        // kendini kapattı, ağ koptu) yoklama SONSUZA DEK sessizce sürüyordu —
        // ölçümde 200 çağrıda durmadı, ekranda "Downloading…" donuk kaldı ve
        // kullanıcı elle indirebileceğini hiç öğrenmedi. `idle` dalındaki
        // sayacın (idleStrikes > 5) hata dalında karşılığı yoktu. Artık var:
        // aynı eşik, aynı bildirim, aynı "tarayıcıdan indir" vurgusu.
        var errorStrikes = 0;
        var ERROR_LIMIT = 5;

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
                            // ÖH D18 / P12aB5-03: eşik KATI EŞİTLİKLE (===)
                            // sınanıyordu; sayaç eşiği geçtiği anda `else`
                            // dalına düşülüyor ve yönlendirme cümlesi düz
                            // ilerleme metniyle EZİLİYORDU. Ölçüldü: 200
                            // yoklamalık takılmada uyarı 1 adım (0,7 sn)
                            // ekranda kaldı, sonra kayboldu — takılmış
                            // indirmeden çıkış yolu fiilen görünmez oluyordu.
                            // Eşik artık ULAŞILDIĞINDA VE SONRASINDA geçerli:
                            // takılma sürdükçe cümle ekranda durur, ilerleme
                            // yeniden başladığında (aşağıdaki `else`) sayaç
                            // sıfırlanıp düz metne dönülür.
                            if (stallStrikes >= STALL_LIMIT) {
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
                        startInstall(st);
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
                .catch(function () {
                    // Sonlu deneme + adlı bildirim (ÖH D17 / P12aB5-02).
                    errorStrikes += 1;
                    if (errorStrikes > ERROR_LIMIT) {
                        highlightManual();
                        progressText.innerHTML = T('update.statusUnreachable',
                            'Update status could not be read — the download may not '
                            + 'have finished. Use the browser link below instead.');
                        updateBtn.disabled = false;
                        updateBtn.style.opacity = '1';
                        return;
                    }
                    setTimeout(pollStatus, POLL_MS * 2);
                });
        }
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /* `kaynakBilgisi` verilirse iddianın DAYANAĞI ikinci satıra basılır
       (ÖH D27 / OH-D26-18). "Güncelsiniz" de bir iddiadır: yedek sayfa
       kazımasından okunmuşsa kullanıcı bunu bilmelidir. */
    function toast(msg, actionLabel, kaynakBilgisi) {
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
        if (kaynakBilgisi !== undefined) {
            t.style.cssText += 'max-width:420px;text-align:center;line-height:1.5;';
            t.appendChild(sourceRow(kaynakBilgisi,
                'margin-top:6px;font-size:12px;font-weight:400;' +
                'color:var(--hd-ink-dim, #7d97a5);'));
        }
        // Hata durumunda çıkış yolu: tek tıkla sürümler sayfası (elle indirme)
        if (actionLabel) {
            t.style.cssText += 'max-width:420px;text-align:center;line-height:1.5;';
            var link = el('a',
                'display:block;margin-top:8px;color:var(--hd-cyan, #00e5ff);' +
                'cursor:pointer;text-decoration:underline;font-weight:600;');
            link.textContent = actionLabel;
            link.onclick = function () {
                fetch('/api/update/open-download', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (res) {
                        if (!res.opened && res.url) window.open(res.url, '_blank');
                    })
                    .catch(function () {
                        window.open('https://github.com/berketez/HRMA/releases/latest',
                                    '_blank');
                    });
                t.remove();
            };
            t.appendChild(link);
        }
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, actionLabel ? 12000 : 4200);
    }

    /* ÖH D30 · OH-D21-06 — SÖZLÜK TALEP ÜZERİNE YÜKLENİR.
       ÖLÇÜLDÜ (a2/once.json: OHD2106_i18n_common_bayt = 505.460;
       OHD2106_launch_site_i18n_common_etiketi = 1): bu pencerenin 25
       anahtarının 24'ü `i18n_common.js` sözlüğünde yaşıyor (ölçüldü;
       bu dosyanın kendi yorumu "anahtarlar i18n_shell.js'te" diyordu —
       YANLIŞ: i18n_shell 25 anahtarın yalnız 1'ini taşıyor, o yorum da
       bu onarımla düzeltildi). launch_site.html bu yüzden 505 KB'lık
       sözlüğü SAYFA AÇILIŞINDA, yalnız güncelleme penceresi ihtimali
       için indiriyordu; pencere ise oturumların çoğunda hiç açılmıyor.

       Desen `analysis_dock.js:42 ensureCommonDictionary`ten alındı, tek
       farkla: orada IIFE (açılışta), burada METİN BASILMADAN ÖNCE ve
       geri çağrımla — yani ağ yükü pencere/toast gerçekten çizilecekse
       doğuyor. Sözlük gelmezse (onerror) metinler İngilizce yedeğe
       düşer ve pencere yine açılır: T(key, fallback) ürünün zaten
       beyan ettiği sözleşmedir, uydurma çeviri üretilmez. */
    /* ÖH D33-2 · OH-UC-13 — ETİKETİN VARLIĞI SÖZLÜĞÜN HAZIR OLDUĞU DEĞİLDİR.
       ÖLÇÜLDÜ (docs/scofield/raw/OH/D33-2/altyapi/a1/ara_surucu_onarildi.json,
       `lazy` kipi = launch_site/liquid/solid): `force` akışında bu işlev İKİ
       kez çağrılır — önce ısıtma için (checkNow'ın ilk satırı), sonra pencere
       çizilmeden hemen önce. Birinci çağrı etiketi head'e koyuyordu; ikinci
       çağrı "etiket var" diye ERKEN DÖNÜP pencereyi sözlük daha İNMEDEN
       çizdiriyordu (fetch'in `then` zinciri mikro görev, betik yüklemesi
       makro görev — ikincisi her zaman sonra biter). Ölçülen sonuç: Türkçe
       arayüzde başlık 'UPDATE AVAILABLE', soru İngilizce
       (baslik_turkce_mi=false) — yani bu ailenin kapattığı "arayüz Türkçe,
       pencere İngilizce" sınıfının ta kendisi geri gelmişti.

       İki değişiklik:
         (i)  Hazır olma ölçütü artık ETİKETE değil SÖZLÜĞE sorulur
              (`I18N.has('update.available')`, bu pencerenin ilk metni) —
              sayfa sözlüğü kendi etiketiyle getirdiyse de doğru cevap verir.
         (ii) İnen bir istek varken gelen ikinci çağrı erken dönmez, KUYRUĞA
              girer; kuyruk `onload`/`onerror` ile TEK seferde boşalır. Çift
              indirme kapısı böylece etiket metnine değil duruma bağlanır
              (D30/OH-D21-06'nın "sayfa açılışında 505 KB inmesin" kazancı
              aynen durur: etiket hâlâ ancak metin basılacağı an doğar). */
    var SOZLUK_ANAHTARI = 'update.available';   // bu pencerenin ilk metni
    var SOZLUK_KUYRUK = null;                   // null = inen istek yok

    function sozlukYuklu() {
        return !!(window.I18N && typeof window.I18N.has === 'function'
                  && window.I18N.has(SOZLUK_ANAHTARI));
    }

    function sozlukHazir(cb) {
        if (!document || !document.head || !document.querySelector) { cb(); return; }
        if (sozlukYuklu()) { cb(); return; }
        if (SOZLUK_KUYRUK) { SOZLUK_KUYRUK.push(cb); return; }
        SOZLUK_KUYRUK = [cb];
        var tag = document.createElement('script');
        tag.src = '/static/js/i18n_common.js';
        tag.async = false;
        function bitti() {
            var kuyruk = SOZLUK_KUYRUK || [];
            SOZLUK_KUYRUK = null;
            for (var i = 0; i < kuyruk.length; i++) {
                // bir geri çağrımın hatası ötekini düşürmesin
                try { kuyruk[i](); } catch (e) { /* yut */ }
            }
        }
        tag.onload = bitti;
        tag.onerror = bitti;     // sözlük yoksa İngilizce yedekle devam
        document.head.appendChild(tag);
    }

    function checkNow(force) {
        // force=true: kullanıcı menüden istedi — atlanan sürümü de göster,
        // güncel/hata durumunda sessiz kalma (toast bildir).
        // OH-D21-06: `force` kipinde her dal metin basar (toast ya da
        // pencere), o yüzden sözlük ağ isteğiyle BİRLİKTE ısıtılır;
        // sessiz açılış denetiminde (force=false) yalnız pencere dalı
        // kendi içinde garantiler — güncel sürümde hiç yük doğmaz.
        if (force) { sozlukHazir(function () { /* önden ısıtma */ }); }
        fetch('/api/update/check')
            .then(function (r) { return r.json(); })
            .then(function (info) {
                if (!info.available || !info.latest) {
                    if (force) {
                        if (info.error || !info.current) {
                            // Kota aşımı geçicidir ve ağdaki başka bir kullanıcıdan
                            // da kaynaklanabilir — kullanıcıya gerçek nedeni ve
                            // elle indirme yolunu göster (2026-07-24 saha hatası).
                            var rateLimited = info.error_kind === 'rate_limit';
                            toast(rateLimited
                                ? T('update.rateLimited',
                                    'GitHub is rate limiting this network right now. '
                                    + 'Try again in a few minutes, or open the releases page.')
                                : T('update.unreachable',
                                    'Could not reach the update server.'),
                                T('update.openReleases', 'Open the releases page'));
                        } else {
                            toast(TF('update.upToDate', { version: info.current },
                                     'HRMA v{version} is up to date.'),
                                  null, info);
                        }
                    }
                    return;
                }
                if (!force) {
                    var skipped = null;
                    try { skipped = localStorage.getItem(SKIP_KEY); } catch (e) { /* özel mod */ }
                    if (skipped === info.latest) return;
                }
                if (document.getElementById('hrma-update-modal')) return;
                sozlukHazir(function () {
                    if (document.getElementById('hrma-update-modal')) return;
                    buildModal(info);
                });
            })
            .catch(function () {
                if (force) {
                    toast(T('update.unreachable', 'Could not reach the update server.'),
                          T('update.openReleases', 'Open the releases page'));
                }
            });
    }

    // Yerel pencere menüsü (macOS "Check for Updates…") buradan tetikler
    window.hrmaCheckForUpdates = checkNow;

    // Ayarlar paneli açılış denetimini kapatabilir (settings_panel.js,
    // localStorage.hrma_update_autocheck: 'on' varsayılan, 'off' = atla).
    // Yalnız OTOMATİK denetim atlanır; menü / "Şimdi denetle" yine çalışır.
    var autocheckOff = false;
    try {
        autocheckOff = localStorage.getItem('hrma_update_autocheck') === 'off';
    } catch (e) { /* özel mod */ }

    // Sayfa otursun, ağır grafikler yüklensin diye küçük gecikmeyle sor
    if (!autocheckOff) {
        if (document.readyState === 'complete') {
            setTimeout(checkNow, 2500);
        } else {
            window.addEventListener('load', function () { setTimeout(checkNow, 2500); });
        }
    }
})();
