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
 *   5. Hata bildir             → bug_report.js (yüklüyse; yoksa bölüm HİÇ
 *                                  çizilmez — ölü düğme yasak). Gömülü GitHub
 *                                  belirteci YOKTUR: form doldurulur, ZORUNLU
 *                                  önizlemeden sonra ön-doldurulmuş issue
 *                                  bağlantısı yeni sekmede açılır, kaydı
 *                                  kullanıcı kendi hesabıyla gönderir.
 *   6. Uygulama bilgisi        → sürüm ({{ app_version }} → window.HRMA_APP_VERSION)
 *                                  + GitHub bağlantısı.
 */
(function () {
    'use strict';

    var AUTOCHECK_KEY = 'hrma_update_autocheck';
    var SKIP_KEY = 'hrma_update_skip';
    var GITHUB_URL = 'https://github.com/berketez/HRMA';

    /* ---- Yazı ölçeği — TEK KAYNAK (ÖH D23 / P17B2-05, yüksek) ----
       ÖLÇÜLDÜ (canlı getComputedStyle, /hybrid TR, `once_ayarlar.json`):
       pencerenin 22 görünür satırının 9'u 13 px'in ALTINDAYDI — dördü
       bölüm başlığı (11 px), dördü alan etiketi (12 px), biri güncelleme
       durum satırı ("Atlanan sürüm yok.", 12 px). P17 turunun ölçtüğü
       kusur "12 px / 2,75:1" idi; D21 kontrast yarısını kapattı
       (en düşük 2,75:1 -> 5,97:1, AA altı satır 4 -> 0) ama YALNIZ
       açıklama satırlarını (descLine) büyüttü. Kalan satırlar için aynı
       gerekçe geçerli: kullanıcının okuması gereken satır pencerenin en
       okunmaz satırı olamaz — üstelik alan etiketi, etiketlediği girdi
       kutusundan (13 px) küçük basılıyordu.

       Boyut ARTIK TEK YERDE yazılır. Bu dosyada `font-size` her zaman bu
       iki sabitten türetilir; çıplak piksel sayısı YOKTUR. Bekçi:
       tests/test_d23_electron_a1.py (kaynakta çıplak `font-size:NNpx`
       arar ve canlı panelde tabanın altında satır kalmadığını sayar). */
    var PX_TABAN = 13;    // taban — pencerede hiçbir satır bunun altında basılmaz
    var PX_BASLIK = 15;   // yalnız pencere başlığı ("AYARLAR")
    /* ÖH D34 · OH-GT-15 — BÖLÜM BAŞLIĞI GÖVDEYLE AYNI PUNTODAYDI.
       ÖLÇÜLDÜ (a1/once.json): `sectionTitle` 13 px, `descLine` 13 px —
       `baslik_govdeden_buyuk` = false. Kademe, D21'de gövde satırları
       okunabilirlik için 12 -> 13 px'e çıkarılırken kayboldu (başlık zaten
       13'tü): hiyerarşi yalnız ağırlık + renk + harf aralığına kalmıştı,
       yani üç eksen de RENK/BİÇİM eksenindeydi, boyut ekseni yoktu.
       Başlık bir kademe yukarı alınır; gövde 13 px'in ALTINA İNMEZ (D21
       kontrast hükmü orada duruyor). Sayı TÜRETİLİR: taban artınca kademe
       kendiliğinden korunur, ikinci çıplak piksel sabiti yazılmaz. */
    /* Kademe ÜÇ basamaklıdır: gövde (13) < bölüm başlığı (14) <
       pencere başlığı (PX_BASLIK, 15). +2 yazılsaydı bölüm başlığı
       pencere başlığıyla eşitlenir ve bu kez O ayrım düşerdi. */
    var PX_BOLUM_BASLIK = PX_TABAN + 1;   // bölüm başlıkları (= 14 px)

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

    /* Sürüm okuyucu — TEK KAYNAK: bug_report.js `detectVersion`.
     *
     * ÖH D20 / P12aB5-08 — ÖLÇÜLDÜ (once.json, altı sayfa senaryosu): burada
     * ikinci, zayıf bir okuyucu duruyordu. Yalnız `window.HRMA_APP_VERSION`'a
     * bakıyor, yedeği ise altbilgide "HRMA v" ÖNEKİ arıyordu; oysa
     *   /hybrid     sürümü `window.HRMA_VERSION`'da,
     *   /formulas   altbilgide "HRMA - Rocket Motor Analysis v…" önekiyle
     * yayımlıyor. Sonuç: 6 sayfanın 5'inde panel çıplak "v?" basıyordu; aynı
     * andaki hata kaydı (bug_report.js, üç kaynağa bakan okuyucu) aynı
     * sayfalarda sürümü DOĞRU buluyordu.
     *
     * Okuyucu kopyalanmadı, ÇAĞRILDI: `bug_report.js` bu sayfaların hepsinde
     * yüklüdür (index/advanced/solid/liquid/formulas/launch_site) ve
     * `detectVersion` zaten dışa açıktır. Dönüş {value, basis}: `value` null
     * ise sürüm UYDURULMAZ — hangi kaynakların denendiği (`basis`) ekrana
     * yazılır, bug_report.js'in kayda yazdığı beyanın aynısı.
     */
    function versionInfo() {
        var br = window.HRMABugReport;
        if (br && typeof br.detectVersion === 'function') {
            var info = br.detectVersion();
            if (info && typeof info === 'object') return info;
        }
        /* Okuyucu yüklü değil: sessiz yedek YOK, durum olduğu gibi söylenir. */
        return { value: null, basis: 'bug_report.js' };
    }

    /* Bölüm başlığı + açıklama satırı üreten küçük yardımcılar */
    function sectionTitle(key, fallback) {
        /* OH-GT-15: PX_BOLUM_BASLIK — gövde satırından (PX_TABAN) bir
           kademe büyük; boyut, renkten bağımsız ikinci hiyerarşi ekseni. */
        var node = el('div',
            'font-size:' + PX_BOLUM_BASLIK + 'px;font-weight:700;letter-spacing:2px;text-transform:uppercase;' +
            'margin:18px 0 8px;color:var(--hd-cyan-soft, #3af2ff);' +
            'font-family:var(--hd-mono, monospace);',
            escapeHtml(T(key, fallback)));
        node.setAttribute('data-i18n', key);
        return node;
    }
    function descLine(key, fallback) {
        /* ÖH D21 / P17B2-05 (yüksek) — OKUNMASI GEREKEN SATIR EN OKUNMAZ
           SATIR OLAMAZ.
           ÖLÇÜLDÜ (P17 B2-tur-10, canlı getComputedStyle + yarı saydam zemin
           bindirmesi): bu yardımcının bastığı satırlar 12 px ve 2,75:1
           kontrasttaydı; pencerenin 22 görünür satırının 13'ü 13 px'in
           altındaydı. Bunların arasında tanılama onay kutusunun GİZLİLİK
           BEYANI da vardı — kullanıcının "tanılama verisi eklensin mi"
           kararını dayandırdığı tek cümle. WCAG 2.1 AA gövde metni için
           4,5:1 ister; 12 px "büyük metin" sayılmaz, yani 3,0:1 istisnası
           da geçerli değildir.
           İki değişiklik, ikisi de mevcut belirteçlerden (TEK KAYNAK; yeni
           renk uydurulmadı): boyut 12 -> 13 px, mürekkep
           --hd-ink-faint -> --hd-ink-dim. Belirteçlerin --hd-panel-solid
           (#0a1524) üstündeki ölçülmüş kontrastı 4,646:1 -> 5,972:1; ikisi
           de aynı koyu zemin üstünde daha açık mürekkep olduğu için
           iyileşme, panelin yarı saydam olduğu durumda da yönü korur. */
        var node = el('div',
            'font-size:' + PX_TABAN + 'px;line-height:1.5;margin-top:4px;' +
            'color:var(--hd-ink-dim, #7d97a5);',
            escapeHtml(T(key, fallback)));
        node.setAttribute('data-i18n', key);
        return node;
    }

    var SELECT_STYLE =
        'padding:7px 10px;font-size:' + PX_TABAN + 'px;cursor:pointer;' +
        'background:var(--hd-inset, rgba(6,14,26,0.85));' +
        'color:var(--hd-ink-strong, #eaf7fb);' +
        'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
        'border-radius:var(--hd-radius-sm, 8px);' +
        'font-family:var(--hd-sans, sans-serif);';

    var BTN_STYLE =
        'padding:8px 16px;font-size:' + PX_TABAN + 'px;font-weight:600;cursor:pointer;' +
        'background:transparent;color:var(--hd-ink, #cfe8f2);' +
        'border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));' +
        'border-radius:var(--hd-radius-sm, 8px);' +
        'font-family:var(--hd-sans, sans-serif);transition:opacity 0.15s;';

    var INPUT_STYLE =
        'width:100%;box-sizing:border-box;padding:8px 10px;font-size:' + PX_TABAN + 'px;' +
        'background:var(--hd-inset, rgba(6,14,26,0.85));' +
        'color:var(--hd-ink-strong, #eaf7fb);' +
        'border:1px solid var(--hd-line, rgba(0,229,255,0.22));' +
        'border-radius:var(--hd-radius-sm, 8px);' +
        'font-family:var(--hd-sans, sans-serif);';

    var AREA_STYLE = INPUT_STYLE +
        'min-height:62px;resize:vertical;line-height:1.45;';

    var MONO_AREA_STYLE = INPUT_STYLE +
        'min-height:210px;resize:vertical;line-height:1.45;font-size:' + PX_TABAN + 'px;' +
        'font-family:var(--hd-mono, monospace);white-space:pre;';

    /* Alan etiketi (data-i18n taşır; dil değişince I18N.apply tazeler) */
    function fieldLabel(key, fallback) {
        var node = el('div',
            'font-size:' + PX_TABAN + 'px;font-weight:600;margin:12px 0 4px;' +
            'color:var(--hd-ink, #cfe8f2);',
            escapeHtml(T(key, fallback)));
        node.setAttribute('data-i18n', key);
        return node;
    }

    function setPlaceholder(node, key, fallback) {
        node.setAttribute('placeholder', T(key, fallback));
        node.setAttribute('data-i18n-placeholder', key);
    }

    function makeArea(key, fallback) {
        var area = document.createElement('textarea');
        area.style.cssText = AREA_STYLE;
        setPlaceholder(area, key, fallback);
        return area;
    }

    /* Kullanıcı uyarısı sözleşmesi: {code, params}. Sözlükte anahtar yoksa
       aşağıdaki yedek metin basılır (kod ekrana ham dökülmez). */
    var WARN_FALLBACK = {
        'warn.bugreport.body_truncated':
            'The diagnostic log was shortened to fit the issue link length ' +
            'limit ({chars} characters removed).',
        'warn.bugreport.title_truncated':
            'The title was shortened to the {limit}-character GitHub limit.',
        'warn.bugreport.preview_required':
            'The report can only be opened after it has been previewed.'
    };

    /* ÖH D22 / P12aB5-12 — DURUM SATIRLARI DİL DEĞİŞİMİNDE TAZELENİR.
       ÖLÇÜLEN KUSUR (once.json K5): durum düğümleri (checkStatus, skipStatus,
       formStatus, counter, sendStatus) metni doğrudan `T()/TF()` ile
       basıyordu ve `data-i18n` TAŞIMIYORDU; `I18N.apply()` onlara
       dokunmuyor, modalın `onChange` aboneliği de yalnız iki <select>'i
       eşitliyordu. Pencere AÇIKKEN dil değiştirilince "Atlanan sürüm:
       v2.6.26" eski dilde kalıyordu (15 yazım noktası ölçüldü).
       Metin artık TEK yerden basılır; anahtar ve (varsa) parametreleri
       düğümün üstünde durur — i18n.js `data-i18n` / `data-i18n-params`
       sözleşmesini zaten tazeliyor, ikinci bir tazeleme yolu YAZILMAZ. */
    function setStatus(node, key, params, fallback) {
        if (!node) return;
        if (!key) {                       // temizleme: iz de kalmaz
            node.removeAttribute('data-i18n');
            node.removeAttribute('data-i18n-params');
            node.textContent = '';
            return;
        }
        node.setAttribute('data-i18n', key);
        if (params) {
            node.setAttribute('data-i18n-params', JSON.stringify(params));
            node.textContent = TF(key, params, fallback);
        } else {
            node.removeAttribute('data-i18n-params');
            node.textContent = T(key, fallback);
        }
    }

    /* Sürüm bilgisinin KAYNAĞI — ÖH D27 / OH-D26-18 (OH-B3-02'nin payı).
     *
     * ÖLÇÜLDÜ (`once.json`, node ikizi): `/api/update/check` `source`
     * yayımlıyor ("api" | "page" yedek sayfa kazıması | null), panel hiç
     * basmıyordu; API yolundan gelen "güncelsiniz" ile yedek kazımadan gelen
     * "güncelsiniz" ekranda BİRBİRİNİN AYNIsıydı.
     *
     * TEK KAYNAK: kod -> cümle sözlüğü `update_check.js`tedir (uç
     * sözleşmesinin sahibi orası). Burada İKİNCİ bir tablo YAZILMAZ; köprü
     * yoksa (o betiği yüklemeyen bir sayfa) sunucunun BEYAN ETTİĞİ kod ham
     * hâliyle söylenir — susmak yerine az bilgi vermek. Aynı fail-closed
     * deseni "güncelleme penceresi yok" dalında da kullanılıyor. */
    function kaynakNotu(info) {
        var kopru = window.HRMAUpdateSource;
        if (typeof kopru === 'function') return kopru(info);
        if (!info || !Object.prototype.hasOwnProperty.call(info, 'source')) {
            return { key: 'update.sourceMissing', params: null,
                     fallback: 'The server did not report where this version '
                               + 'information came from.' };
        }
        return { key: 'update.sourceRaw', params: { code: String(info.source) },
                 fallback: 'Version information source reported by the '
                           + 'server: {code}.' };
    }

    function warnChip(w) {
        var code = String((w && w.code) || '');
        var node = el('span',
            'display:inline-block;margin:8px 8px 0 0;padding:4px 10px;' +
            'font-size:' + PX_TABAN + 'px;border-radius:999px;' +
            'border:1px solid var(--hd-orange, #ff8c33);' +
            'color:var(--hd-orange, #ff8c33);' +
            'background:rgba(255,180,84,0.10);' +
            'font-family:var(--hd-mono, monospace);',
            escapeHtml(TF(code, (w && w.params) || {},
                          WARN_FALLBACK[code] || code)));
        node.setAttribute('data-warn-code', code);
        /* Uyarı pili de dil değişiminde tazelenir (P12aB5-12): kodu ZATEN
           i18n anahtarıdır, parametreleri de düğümde durur. */
        node.setAttribute('data-i18n', code);
        node.setAttribute('data-i18n-params',
                          JSON.stringify((w && w.params) || {}));
        return node;
    }

    /* "Hata bildir" bölümü.
     *
     * bug_report.js yüklü DEĞİLSE bölüm hiç çizilmez — çalışmayan düğme
     * koymayız. Akış iki adımlıdır ve ikinci adım ZORUNLUDUR:
     *
     *   form  →  [Önizle]  →  gönderilecek TAM metin (düzenlenebilir)
     *         →  [GitHub'da aç]  →  ön-doldurulmuş issue yeni sekmede.
     *
     * Gönderme düğmesine GitHub'ın kendi sayfasında kullanıcı basar; HRMA
     * kimsenin adına kayıt açmaz (gömülü belirteç yok). openIssue() önizlemede
     * GÖRÜLMEMİŞ bir gövdeyi açmaz (bug_report.js önizleme kilidi).
     */
    function appendBugSection(box) {
        var BR = window.HRMABugReport;
        if (!BR) return;

        box.appendChild(sectionTitle('shell.bug.section', 'Report a bug'));
        box.appendChild(descLine('shell.bug.intro',
            'Fill this in and HRMA opens a pre-filled issue on GitHub in a new '
            + 'tab. Nothing is sent automatically — you review the text and '
            + 'submit it with your own GitHub account.'));

        var form = el('div', 'margin-top:8px;');
        var preview = el('div', 'margin-top:8px;display:none;');
        box.appendChild(form);
        box.appendChild(preview);

        // ---- adım 1: form ----
        form.appendChild(fieldLabel('shell.bug.titleLabel', 'Title'));
        var titleIn = document.createElement('input');
        titleIn.type = 'text';
        titleIn.id = 'hrma-bug-title';
        titleIn.style.cssText = INPUT_STYLE;
        titleIn.maxLength = BR.MAX_TITLE_CHARS;
        setPlaceholder(titleIn, 'shell.bug.titlePlaceholder',
                       'Short summary of the problem');
        form.appendChild(titleIn);

        form.appendChild(fieldLabel('shell.bug.whatLabel', 'What happened?'));
        var whatIn = makeArea('shell.bug.whatPlaceholder',
            'Describe what went wrong.');
        whatIn.id = 'hrma-bug-what';
        form.appendChild(whatIn);

        form.appendChild(fieldLabel('shell.bug.expectedLabel',
                                    'What did you expect?'));
        var expectedIn = makeArea('shell.bug.expectedPlaceholder',
            'What should have happened instead?');
        expectedIn.id = 'hrma-bug-expected';
        form.appendChild(expectedIn);

        form.appendChild(fieldLabel('shell.bug.stepsLabel',
                                    'Steps to reproduce'));
        var stepsIn = makeArea('shell.bug.stepsPlaceholder',
            '1. Open the hybrid page\n2. Enter …\n3. Press Analyze');
        stepsIn.id = 'hrma-bug-steps';
        form.appendChild(stepsIn);

        // Tanılama onay kutusu — VARSAYILAN KAPALI (kullanıcı bilerek açar)
        var diagRow = el('label',
            'display:flex;align-items:flex-start;gap:10px;cursor:pointer;'
            + 'font-size:' + PX_TABAN + 'px;margin-top:14px;');
        var diagBox = document.createElement('input');
        diagBox.type = 'checkbox';
        diagBox.id = 'hrma-bug-diagnostics';
        diagBox.checked = false;
        diagBox.style.cssText =
            'accent-color:var(--hd-cyan, #00e5ff);cursor:pointer;margin-top:2px;';
        var diagLabel = el('span', '',
            escapeHtml(T('shell.bug.diagnostics',
                         'Attach diagnostic information')));
        diagLabel.setAttribute('data-i18n', 'shell.bug.diagnostics');
        diagRow.appendChild(diagBox);
        diagRow.appendChild(diagLabel);
        form.appendChild(diagRow);
        /* ÖH D18 / P12aB5-05: "kaldırılanlar" listesi yalnız dosya yolu /
           kullanıcı adı / e-posta sayıyordu; oysa /launch-site'ın enlem ve
           boylamı (sayfadaki en kimliklendirici değer) kayda giriyordu.
           Kusur bug_report.js'te fail-closed olarak giderildi (isGeoField);
           beyan artık GERÇEĞİ söylüyor — koordinat da kaldırılanlar arasında. */
        form.appendChild(descLine('shell.bug.diagnosticsDesc',
            'Adds the numeric inputs on this page and the console errors '
            + 'captured after it loaded. File paths, user names, e-mail '
            + 'addresses and geographic coordinates (launch site '
            + 'latitude/longitude) are removed. Off unless you turn it on.'));

        var formRow = el('div',
            'display:flex;align-items:center;gap:12px;margin-top:14px;'
            + 'flex-wrap:wrap;');
        var previewBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.bug.preview', 'Preview')));
        previewBtn.setAttribute('data-i18n', 'shell.bug.preview');
        previewBtn.id = 'hrma-bug-preview-btn';
        var formStatus = el('div',
            'font-size:' + PX_TABAN + 'px;color:var(--hd-ink-dim, #7d97a5);flex:1;'
            + 'min-width:160px;', '');
        formStatus.id = 'hrma-bug-form-status';
        formRow.appendChild(previewBtn);
        formRow.appendChild(formStatus);
        form.appendChild(formRow);

        // ---- adım 2: önizleme ----
        preview.appendChild(fieldLabel('shell.bug.previewTitle',
            'This exact text will be sent'));
        preview.appendChild(descLine('shell.bug.previewHint',
            'You can still edit it. HRMA opens GitHub with this text '
            + 'pre-filled; you press "Submit new issue" there.'));

        preview.appendChild(fieldLabel('shell.bug.titleLabel', 'Title'));
        var pTitleIn = document.createElement('input');
        pTitleIn.type = 'text';
        pTitleIn.id = 'hrma-bug-preview-title';
        pTitleIn.style.cssText = INPUT_STYLE;
        pTitleIn.maxLength = BR.MAX_TITLE_CHARS;
        preview.appendChild(pTitleIn);

        var bodyArea = document.createElement('textarea');
        bodyArea.id = 'hrma-bug-body';
        bodyArea.style.cssText = MONO_AREA_STYLE + 'margin-top:10px;';
        preview.appendChild(bodyArea);

        var chipRow = el('div', 'display:block;');
        preview.appendChild(chipRow);

        /* P17B2-05 ile aynı gerekçe: karakter sayacı da 11 px + en sönük
           mürekkepti. Sayaç, bağlantı sınırına takılıp takılmadığını
           söyleyen tek gösterge. */
        var counter = el('div',
            'font-size:' + PX_TABAN + 'px;margin-top:8px;color:var(--hd-ink-dim, #7d97a5);'
            + 'font-family:var(--hd-mono, monospace);', '');
        preview.appendChild(counter);

        var sendRow = el('div',
            'display:flex;align-items:center;gap:12px;margin-top:12px;'
            + 'flex-wrap:wrap;');
        var sendBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.bug.openGithub', 'Open on GitHub')));
        sendBtn.setAttribute('data-i18n', 'shell.bug.openGithub');
        sendBtn.id = 'hrma-bug-send-btn';
        var backBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.bug.back', 'Back')));
        backBtn.setAttribute('data-i18n', 'shell.bug.back');
        backBtn.id = 'hrma-bug-back-btn';
        sendRow.appendChild(sendBtn);
        sendRow.appendChild(backBtn);
        preview.appendChild(sendRow);

        var sendStatus = el('div',
            'font-size:' + PX_TABAN + 'px;margin-top:8px;color:var(--hd-ink-dim, #7d97a5);',
            '');
        sendStatus.id = 'hrma-bug-send-status';
        preview.appendChild(sendStatus);

        // Yeni sekme engellendiyse bağlantı elle kopyalanabilsin
        var urlBox = el('div', 'display:none;margin-top:8px;');
        urlBox.appendChild(fieldLabel('shell.bug.urlLabel', 'Issue link'));
        var urlIn = document.createElement('input');
        urlIn.type = 'text';
        urlIn.id = 'hrma-bug-url';
        urlIn.readOnly = true;
        urlIn.style.cssText = INPUT_STYLE +
            'font-family:var(--hd-mono, monospace);font-size:' + PX_TABAN + 'px;';
        urlBox.appendChild(urlIn);
        preview.appendChild(urlBox);

        function showChips(list) {
            chipRow.innerHTML = '';
            for (var i = 0; i < (list || []).length; i++) {
                chipRow.appendChild(warnChip(list[i]));
            }
        }

        /* Önizlemedeki metin her değiştiğinde kilit tazelenir: openIssue yalnız
           EKRANDA DURAN metni açabilir. */
        function syncPreview() {
            BR.markPreviewed(pTitleIn.value, bodyArea.value);
            var built = BR.buildIssueUrl(pTitleIn.value, bodyArea.value);
            setStatus(counter, 'shell.bug.charCount',
                { chars: bodyArea.value.length, url: built.url_chars,
                  limit: built.limit },
                '{chars} characters — issue link {url} / {limit}');
        }

        previewBtn.addEventListener('click', function () {
            if (!titleIn.value.trim()) {
                setStatus(formStatus, 'shell.bug.needTitle', null,
                    'Please write a title.');
                return;
            }
            if (!whatIn.value.trim()) {
                setStatus(formStatus, 'shell.bug.needWhat', null,
                    'Please describe what happened.');
                return;
            }
            setStatus(formStatus, null);
            var body = BR.buildBody(
                { what: whatIn.value, expected: expectedIn.value,
                  steps: stepsIn.value },
                { diagnostics: diagBox.checked });
            // Kırpma BURADA yapılır: kullanıcı gönderilecek metnin aynısını
            // görür (gövde uzunsa kısaltılmış hâli + beyanı ile).
            var built = BR.buildIssueUrl(titleIn.value.trim(), body);
            pTitleIn.value = built.title;
            bodyArea.value = built.body;
            showChips(built.warnings);
            setStatus(sendStatus, null);
            urlBox.style.display = 'none';
            syncPreview();
            form.style.display = 'none';
            preview.style.display = 'block';
        });

        pTitleIn.addEventListener('input', syncPreview);
        bodyArea.addEventListener('input', syncPreview);

        backBtn.addEventListener('click', function () {
            BR.resetPreview();
            preview.style.display = 'none';
            form.style.display = 'block';
        });

        sendBtn.addEventListener('click', function () {
            var res = BR.openIssue(pTitleIn.value, bodyArea.value);
            showChips(res.warnings);
            if (res.needs_preview) {
                if (res.body) {
                    // Kırpılan metin henüz görülmedi -> ekrana bas, açma
                    bodyArea.value = res.body;
                    syncPreview();
                    setStatus(sendStatus, 'shell.bug.reviewAgain', null,
                        'The text was shortened to fit the link limit — '
                        + 'check it and press the button again.');
                } else {
                    setStatus(sendStatus, 'shell.bug.previewRequired', null,
                        'Preview the report before opening it.');
                }
                return;
            }
            if (res.opened) {
                setStatus(sendStatus, 'shell.bug.opened', null,
                    'GitHub opened in a new tab — check the text there and '
                    + 'press "Submit new issue".');
                urlBox.style.display = 'none';
            } else {
                setStatus(sendStatus, 'shell.bug.openFailed', null,
                    'The browser did not open a new tab. Copy the link below '
                    + 'and open it yourself.');
                urlIn.value = res.url || '';
                urlBox.style.display = 'block';
            }
        });
    }

    function openModal() {
        if (document.getElementById('hrma-settings-modal')) return;

        var unsubscribe = null;

        var wrap = el('div',
            'position:fixed;inset:0;z-index:99985;display:flex;align-items:center;' +
            'justify-content:center;background:rgba(2,6,12,0.72);backdrop-filter:blur(4px);');
        wrap.id = 'hrma-settings-modal';

        function closeModal() {
            if (unsubscribe) unsubscribe();
            // Önizleme kilidi bir sonraki açılışa taşınmaz: kapatılan pencerede
            // görülen metin, yeniden açılan formda "görülmüş" sayılmamalı.
            if (window.HRMABugReport && window.HRMABugReport.resetPreview) {
                window.HRMABugReport.resetPreview();
            }
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
            'font-size:' + PX_BASLIK + 'px;font-weight:700;letter-spacing:0.4px;margin-bottom:4px;' +
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
            'display:flex;align-items:center;gap:10px;cursor:pointer;font-size:' + PX_TABAN + 'px;');
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
            'font-size:' + PX_TABAN + 'px;color:var(--hd-ink-dim, #7d97a5);flex:1;min-width:160px;', '');
        checkRow.appendChild(checkBtn);
        checkRow.appendChild(checkStatus);
        box.appendChild(checkRow);

        /* Denetimin DAYANAĞI (ÖH D27 / OH-D26-18): sunucudan bir yanıt
           geldiği HER durumda yazılır, boş bırakılmaz. Yanıt hiç yoksa
           (ağ hatası) satır temizlenir — o zaman beyan edilecek bir kaynak
           da yoktur, durum satırı zaten "ulaşılamadı" der. */
        var checkSource = el('div',
            'font-size:' + PX_TABAN + 'px;line-height:1.5;margin-top:6px;' +
            'color:var(--hd-ink-dim, #7d97a5);', '');
        box.appendChild(checkSource);

        checkBtn.addEventListener('click', function () {
            checkBtn.disabled = true;
            checkBtn.style.opacity = '0.5';
            setStatus(checkStatus, 'shell.settings.checking', null, 'Checking…');
            fetch('/api/update/check')
                .then(function (r) { return r.json(); })
                .then(function (info) {
                    checkBtn.disabled = false;
                    checkBtn.style.opacity = '1';
                    var kaynak = kaynakNotu(info);
                    setStatus(checkSource, kaynak.key, kaynak.params,
                              kaynak.fallback);
                    if (info.available && info.latest) {
                        // ÖH D21 / P12aB5-07 — ÖLÇÜLEN KUSUR: metin KOŞULSUZ,
                        // çağrı KOŞULLU yazılıyordu. `update_check.js`
                        // yüklenmemişse (ölçüldü: /launch-site) ekranda
                        // "güncelleme penceresi açılıyor" yazıyor ama pencere
                        // hiç açılmıyordu; kullanıcı bekliyordu. FAIL-CLOSED:
                        // söz yalnız sağlayıcı GERÇEKTEN varken verilir.
                        // (Betik artık altı sayfada da yüklü; bu dal betik
                        // yüklenemediğinde de metnin yalan söylememesini
                        // garanti eder.)
                        var pencereVar = !!window.hrmaCheckForUpdates;
                        if (pencereVar) {
                            setStatus(checkStatus, 'shell.settings.updateFound',
                                { version: info.latest },
                                'New version found: v{version} — opening the update window.');
                        } else {
                            setStatus(checkStatus, 'shell.settings.updateFoundNoWindow',
                                { version: info.latest },
                                'New version found: v{version} — the update window '
                                + 'is unavailable on this page.');
                        }
                        // Mevcut modal akışı (update_check.js köprüsü, force=true:
                        // atlanan sürüm de gösterilir)
                        if (pencereVar) window.hrmaCheckForUpdates(true);
                    } else if (info.current && !info.error) {
                        setStatus(checkStatus, 'shell.settings.upToDate',
                            { version: info.current }, 'You are up to date: v{version}');
                    } else if (info.error_kind === 'rate_limit') {
                        // GitHub kota aşımı geçicidir (2026-07-24 saha hatası)
                        setStatus(checkStatus, 'shell.settings.rateLimited', null,
                            'GitHub is rate limiting this network — '
                            + 'try again in a few minutes.');
                    } else {
                        setStatus(checkStatus, 'shell.settings.checkFailed', null,
                            'Could not reach the update server.');
                    }
                })
                .catch(function () {
                    checkBtn.disabled = false;
                    checkBtn.style.opacity = '1';
                    setStatus(checkStatus, 'shell.settings.checkFailed', null,
                        'Could not reach the update server.');
                    // Yanıt YOK: beyan edilecek kaynak da yok (uydurma yok).
                    setStatus(checkSource, null);
                });
        });

        var skipRow = el('div',
            'display:flex;align-items:center;gap:12px;margin-top:12px;flex-wrap:wrap;');
        var skipBtn = el('button', BTN_STYLE,
            escapeHtml(T('shell.settings.skipReset', 'Reset skipped version')));
        skipBtn.setAttribute('data-i18n', 'shell.settings.skipReset');
        var skipStatus = el('div',
            'font-size:' + PX_TABAN + 'px;color:var(--hd-ink-dim, #7d97a5);flex:1;min-width:160px;', '');
        skipRow.appendChild(skipBtn);
        skipRow.appendChild(skipStatus);
        box.appendChild(skipRow);

        function refreshSkipRow() {
            var skipped = lsGet(SKIP_KEY);
            if (skipped) {
                skipBtn.disabled = false;
                skipBtn.style.opacity = '1';
                setStatus(skipStatus, 'shell.settings.skippedVersion',
                    { version: String(skipped).replace(/^v/, '') },
                    'Skipped version: v{version}');
            } else {
                skipBtn.disabled = true;
                skipBtn.style.opacity = '0.45';
                setStatus(skipStatus, 'shell.settings.noSkipped', null,
                    'No skipped version.');
            }
        }
        refreshSkipRow();

        skipBtn.addEventListener('click', function () {
            lsRemove(SKIP_KEY);
            refreshSkipRow();
            setStatus(skipStatus, 'shell.settings.skipCleared', null,
                'Skipped version cleared — it will be offered again.');
        });

        /* ---- 3. Hata bildir ---- */
        appendBugSection(box);

        /* ---- 4. Uygulama bilgisi ---- */
        box.appendChild(sectionTitle('shell.settings.app', 'Application'));

        var infoRow = el('div',
            'display:flex;align-items:center;gap:16px;font-size:' + PX_TABAN + 'px;flex-wrap:wrap;');
        var versionWrap = el('span', 'color:var(--hd-ink-strong, #eaf7fb);');
        var versionLabel = el('span', '',
            escapeHtml(T('shell.settings.version', 'Version')));
        versionLabel.setAttribute('data-i18n', 'shell.settings.version');
        versionWrap.appendChild(versionLabel);
        var vinfo = versionInfo();
        if (vinfo.value) {
            versionWrap.appendChild(document.createTextNode(': v' + vinfo.value));
        } else {
            /* Sürüm okunamadı: '?' yerine NEDEN okunamadığı yazılır.
               Dil paneli açıkken değişebildiği için iki düğüm de
               data-i18n taşır; parametreli olan data-i18n-params ile
               `I18N.apply`'ın yeniden doldurabileceği hâlde bırakılır. */
            var vMissing = el('span', 'color:var(--hd-orange, #ff8c33);',
                escapeHtml(T('shell.settings.versionUnknown',
                             'could not be read')));
            vMissing.setAttribute('data-i18n', 'shell.settings.versionUnknown');
            versionWrap.appendChild(document.createTextNode(': '));
            versionWrap.appendChild(vMissing);
            var kaynaklar = String(vinfo.basis || '');
            /* P17B2-05: sürüm bulunamadığında hangi kaynakların denendiğini
               söyleyen beyan; sönük basılırsa beyan olmaktan çıkar. */
            var vBasis = el('span',
                'display:block;font-size:' + PX_TABAN + 'px;margin-top:2px;' +
                'color:var(--hd-ink-dim, #7d97a5);' +
                'font-family:var(--hd-mono, monospace);',
                escapeHtml(TF('shell.settings.versionBasis',
                              { sources: kaynaklar },
                              'sources tried: {sources}')));
            vBasis.setAttribute('data-i18n', 'shell.settings.versionBasis');
            vBasis.setAttribute('data-i18n-params',
                                JSON.stringify({ sources: kaynaklar }));
            versionWrap.appendChild(vBasis);
        }
        infoRow.appendChild(versionWrap);

        var ghLink = el('a',
            'color:var(--hd-cyan-soft, #3af2ff);text-decoration:underline;cursor:pointer;',
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

    /* Gezinme şeridine bağlantı ekler ve döndürür.

       ÖH D18 / P12aB5-06: burası YALNIZ `.nav-links` sorup bulamayınca
       sessizce dönüyordu. ÖLÇÜLDÜ: /launch-site'ta şerit `#ls-topbar`
       adını taşıdığı için Ayarlar bağlantısı HİÇ çizilmiyordu — panel o
       sayfada hiçbir yoldan açılamıyordu (pencere menüsünde de Ayarlar
       girdisi yok), yani "Hata bildir" haritanın/kürenin olduğu sayfada
       erişilemezdi. Üç kabuk şeridini tanıyan tablo release_notes.js'te
       TEK KEZ tanımlıdır ve `window.HRMA_SHELL_NAV` ile yayımlanır. */
    function injectNavLink() {
        var nav = window.HRMA_SHELL_NAV;
        if (!nav || typeof nav.inject !== 'function') return null;
        return nav.inject('settingsLink');
    }

    window.hrmaShowSettings = openModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountLink);
    } else {
        mountLink();
    }
})();
