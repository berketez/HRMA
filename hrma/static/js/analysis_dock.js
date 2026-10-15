/* ====================================================================
   HRMA Analysis Dock — analiz güvertesi çekirdeği
   --------------------------------------------------------------------
   Kategori sekmeli (THERMAL / STRUCTURAL / SAFETY, ileride genişler)
   analiz paneli konteyneri. Paneller kendilerini AnalysisDock.register
   ile kaydeder; script yüklenme sırası: önce bu dosya, sonra paneller.
   Desen: injector_panel.js (IIFE + init({anchorId, resultsProvider})).

   Kullanım (entegrasyon sözleşmesi — DEĞİŞTİRME):
     <script src="/static/js/analysis_dock.js"></script>
     <script src="/static/js/panels/structural_panel.js"></script>
     ...
     AnalysisDock.init({
         anchorId: 'trajectoryPanel',      // güverte bu elemanın ÖNÜNE kurulur
         motorType: 'hybrid'|'liquid'|'solid',
         resultsProvider: function () { return window.currentResults; }
     });

   Panel kaydı:
     AnalysisDock.register({
         id, title, category, endpoint, motorTypes,
         fields: [[inputId, label, defaultValue, step], ...],
             // step bir dizi ise ([[value, label], ...]) alan <select> olur
         fromResults: function (currentResults) { return {inputId: değer}; },
             // Alan ÖNERİLERİ — kullanıcı üzerine yazabilir; POST gövdesi
             // HER ZAMAN formdan okunur (kullanıcının elle değiştirdiği
             // alanlar bir daha ezilmez: data-dirty koruması).
         render: function (data, rootEl) { ... },  // ham JSON yanıtı çizer
         long: true|false                          // uzun süren analiz uyarısı
     });
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // ------------------------------------------------------------------
    // Sözlük güvencesi: i18n_common.js şablona eklenmemişse buradan
    // yüklenir (i18n.js'in çok-parçalı sözlük sözleşmesi yükleme sırasından
    // bağımsızdır). Şablon zaten yüklüyorsa ikinci kez eklenmez.
    // ------------------------------------------------------------------
    (function ensureCommonDictionary() {
        if (!document || !document.head || !document.querySelector) return;
        if (document.querySelector('script[src*="i18n_common.js"]')) return;
        var tag = document.createElement('script');
        tag.src = '/static/js/i18n_common.js';
        tag.async = false;
        document.head.appendChild(tag);
    })();

    // ------------------------------------------------------------------
    // i18n köprüsü — i18n.js yüklenmemişse İngilizce yedek metin döner
    // ------------------------------------------------------------------
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback || key).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // Sunucudan DÜZ METİN gelen uyarı/hata satırı. i18n_charts.js'in
    // serverText'i sözlük + desen sırasıyla çevirir; eşleşme yoksa metni
    // AYNEN döndürür (asla anahtar, asla boş). Guard'lı: i18n_charts.js
    // yüklenmemişse metin olduğu gibi geçer.
    //
    // 2026-08-03: serverText Temmuz'da yazılmış ama HİÇBİR YERDEN
    // çağrılmıyordu — 20+ kurallı MSG_PATTERNS tablosu ölü koddu ve
    // {code, params} sözleşmesine geçmemiş bütün API uyarıları TR modda
    // İngilizce kalıyordu. Kanal vardı, kapı yoktu.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }
    // Çevrilebilir nitelik: anahtar varsa data-i18n basar (dil değişince
    // I18N.apply() metni kendiliğinden tazeler).
    function i18nAttr(key) {
        return key ? ' data-i18n="' + key + '"' : '';
    }

    // Başlangıç kategori seti — register bilinmeyen kategoriyle gelirse
    // sekme dinamik eklenir (ileride genişleme sözleşmesi).
    const BASE_CATEGORIES = ['THERMAL', 'STRUCTURAL', 'SAFETY'];

    let cfg = {};
    let inited = false;
    let activeCategory = null;
    const registry = [];          // kayıt sırası korunur
    const registeredIds = {};
    const lastData = {};          // panel id -> son başarılı yanıt (dil değişiminde yeniden çizilir)
    // ÖH D24 / P17B2-08 — ÇÖZÜLEMEYEN MALZEME KOŞUMU DURDURUR.
    // panel id -> { alan: {solver, sent} }. Çözücünün verdiği malzeme
    // güvertenin seçenek listesinde (alias çözümünden SONRA da) yoksa
    // kayıt buraya düşer ve `runPanel` isteği HİÇ göndermez: yapısal
    // hüküm, motorun hesaplandığı alaşımdan BAŞKA bir alaşım üzerinde
    // verilemez. Boş sözlük = engel yok.
    const blockedSelects = {};

    // ------------------------------------------------------------------
    // Ortak UI yardımcıları (paneller AnalysisDock.ui üzerinden kullanır)
    // ------------------------------------------------------------------
    const TBL = 'width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;';
    // overflow-wrap:anywhere — boşluksuz uzun değer (alan yolu, kimlik)
    // hücreyi sütundan geniş açmasın (v3.0.0 görsel tur, /hybrid taşması).
    const TD = 'padding:6px 8px; border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));'
        + ' overflow-wrap:anywhere;';

    const KIND_COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };

    function kindColor(kind) {
        return KIND_COLORS[kind] || KIND_COLORS.info;
    }

    function fmt(x, d) {
        return (x == null || !Number.isFinite(x)) ? '—' : x.toFixed(d == null ? 2 : d);
    }

    // İlk anlamlı (sonlu sayı veya boş olmayan string) değeri döndürür.
    // Backend alan adı varyasyonlarına (SF_pressure / sf_pressure vb.)
    // dayanıklı okuma için.
    function pick(obj, keys) {
        if (!obj) return null;
        for (let i = 0; i < keys.length; i++) {
            const v = obj[keys[i]];
            if (typeof v === 'number' && Number.isFinite(v)) return v;
            if (typeof v === 'string' && v !== '') return v;
        }
        return null;
    }

    function badge(text, kind, title) {
        const c = kindColor(kind);
        return `<span title="${title || ''}" style="border:1px solid ${c}; color:${c};
                 border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
                 font-size:0.75rem; display:inline-block;">${text}</span>`;
    }

    // Sayısal kart (thermal panel "numeric cards" vb.)
    function statCard(label, value, unit, kind, title) {
        const c = kind ? kindColor(kind) : 'var(--hd-ink-strong, #eaf7fb)';
        return `<div title="${title || ''}" style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                border-radius:var(--hd-radius-sm, 8px); padding:10px 14px; min-width:150px; flex:1;
                background:var(--hd-inset, rgba(6,14,26,0.85));">
            <div style="font-size:0.68rem; color:var(--hd-ink-dim, #7d97a5);
                 font-family:var(--hd-mono); text-transform:uppercase;
                 letter-spacing:0.08em;">${label}</div>
            <div style="font-size:1.25rem; font-family:var(--hd-mono); color:${c}; margin-top:2px;">
                ${value}<span style="font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);"> ${unit || ''}</span>
            </div>
        </div>`;
    }

    // İki sütunlu anahtar/değer tablosu: rows = [[label, value, tooltip?], ...]
    function kvTable(rows) {
        return `<table style="${TBL}">` + rows.map(r =>
            `<tr><td style="${TD}" ${r[2] ? `title="${r[2]}"` : ''}><strong>${r[0]}</strong></td>
             <td style="${TD}">${r[1]}</td></tr>`).join('') + '</table>';
    }

    function sectionTitle(text) {
        return `<h4 style="margin:14px 0 4px; color:var(--hd-ink-strong, #eaf7fb);">${text}</h4>`;
    }

    // Kap içindeki Plotly grafiklerini innerHTML sıfırlanmadan ÖNCE serbest
    // bırakır. plotly.js 1.58.5'te responsive:true her grafik için window'a
    // bir resize dinleyicisi takar ve bunu yalnız Plotly.purge kaldırır;
    // div'i purge'suz atmak dinleyiciyi + tüm iz verisini kalıcı sızdırır
    // (her yeniden koşuda birikir). Paneller de AnalysisDock.ui.purgePlots
    // üzerinden kullanır.
    function purgePlots(el) {
        if (!el || !window.Plotly || typeof Plotly.purge !== 'function') return;
        const plots = el.querySelectorAll('.js-plotly-plot');
        for (let i = 0; i < plots.length; i++) {
            try { Plotly.purge(plots[i]); } catch (e) { /* zaten boş */ }
        }
        // querySelectorAll yalnız altları bulur; elemanın kendisi de grafik olabilir
        if (el.classList && el.classList.contains('js-plotly-plot')) {
            try { Plotly.purge(el); } catch (e) { /* zaten boş */ }
        }
    }

    // D-track uyarı kaydını okunur metne çevirir.
    // Backend v2.6.2'den itibaren düz string yerine {code, params, severity}
    // döndürüyor; eski düz string biçimi de desteklenir (geriye dönük uyum).
    // Sözlük TF()'den geçmezse şablona "[object Object]" basılır — bu regresyon
    // v2.6.2'de yaşandı, tests/test_warning_contract.py bekçilik ediyor.
    // İÇ İÇE KAYITLAR: bazı uyarıların parametresi kendisi bir uyarı kaydı ya
    // da kayıt LİSTESİDİR (ör. warn.solid.bates_envelope'un `options` alanı).
    // I18N.tf sayı olmayan parametreyi String(v) ile bastığı için bunlar da
    // "[object Object]" üretir; bu yüzden çeviri ÖZYİNELEMELİDİR.
    function warnText(w, depth) {
        depth = depth || 0;
        if (w === null || w === undefined) return '';
        if (typeof w === 'string') return SRV(w);   // düz metin dalı: çevir
        if (Array.isArray(w)) {
            return w.map(function (x) { return warnText(x, depth + 1); })
                    .filter(function (s) { return s; })
                    .join(' · ');
        }
        if (typeof w !== 'object') return String(w);
        // ÖH D29 · P11B2-19 — AYNI SÖZLEŞMENİN İKİ UYGULAMASI AYRIŞMIŞTI.
        // ÖLÇÜLDÜ (a3/once.json, node): `warnText({message:'plain message'})`
        // burada `{"message":"plain message"}` üretiyordu; app.js'in YEREL
        // eşi (`warnToText`) aynı girdide `SRV(w.message)` ile düz metni
        // basıyor. app.js dock yüklüyse KENDİ yedeğini kullanmıyor
        // (advanced.html'de dock hep yüklü), yani ekrana çıkan biçim
        // buradaki daldı. İki uygulama tek sözleşmeden konuşur:
        // adlandırılmış düz metin alanları önce denenir, ham JSON yalnız
        // GERÇEKTEN beklenmeyen biçim için kalır (görünür kılma dalı).
        if (!w.code) return SRV(w.message || w.text || JSON.stringify(w));
        if (depth > 4) return w.code;           // bozuk/döngüsel veri koruması
        var p = {};
        Object.keys(w.params || {}).forEach(function (k) {
            var v = w.params[k];
            p[k] = (v && typeof v === 'object') ? warnText(v, depth + 1)
                : warnParamText(k, v);
        });
        return TF(w.code, p, w.fallback || w.code);
    }

    // V3 KK 3. tur (§28-50 (c)) — UYARI PARAMETRESİNDE HAM KOD.
    // ÖLÇÜLDÜ (docs/user_guide/img/v3_0/kanit/kayit_tr.json, TR kip, örnek
    // hibrit): '... natural soğutmalı Graphite (isostatic, nozzle insert
    // grade) ...' ve '... belirtilen soğutmayla steel_4130 erime noktası
    // ...'. İki kural, ikisi de mevcut kaynaktan (yeni ad UYDURULMAZ):
    //   material — malzeme ANAHTARI geldiyse önce güvertede kayıtlı
    //     panellerin KENDİ 'material' seçenek listesi (değer, EN etiket,
    //     mat.* sözlük anahtarı; ör. termal panel MATERIALS) — kopya liste
    //     yazılmaz; orada yoksa merkezi kataloğun (materials_db →
    //     /api/materials → HRMAMaterials, sayfada yüklüyse) kayıt adı. Ad
    //     zaten görünen adsa (materials_db 'name') ya da hiçbiri tanımıyorsa
    //     değer AYNEN kalır.
    //   cooling — soğutma kipi kodu güvertenin kendi sözlük anahtarıyla
    //     (cool.*, termal panel seçicisiyle aynı); tanınmayan kod AYNEN.
    var COOLING_KEYS = {
        natural: ['cool.natural', 'Natural (heat sink)'],
        forced: ['cool.forced', 'Forced convection'],
        regenerative: ['cool.regenerative', 'Regenerative'],
    };
    function warnParamText(k, v) {
        if (typeof v !== 'string' || !v) return v;
        if (k === 'material') {
            for (var i = 0; i < registry.length; i++) {
                var alanlar = Array.isArray(registry[i].fields) ? registry[i].fields : [];
                for (var j = 0; j < alanlar.length; j++) {
                    var f = alanlar[j];
                    if (!Array.isArray(f) || f[0] !== 'material' || !Array.isArray(f[3])) continue;
                    for (var m = 0; m < f[3].length; m++) {
                        var o = f[3][m];
                        if (!Array.isArray(o) || o[0] !== v) continue;
                        return o[2] ? T(o[2], o[1]) : (o[1] || v);
                    }
                }
            }
            if (window.HRMAMaterials
                    && typeof window.HRMAMaterials.get === 'function') {
                var rec = window.HRMAMaterials.get(v);
                if (rec && typeof rec.name === 'string' && rec.name) return rec.name;
            }
            return v;
        }
        if (k === 'cooling'
                && Object.prototype.hasOwnProperty.call(COOLING_KEYS, v)) {
            return T(COOLING_KEYS[v][0], COOLING_KEYS[v][1]);
        }
        return v;
    }

    // Uyarı / öneri kutusu (injector_panel uyarı bloğu deseni)
    function listBlock(title, items, kind) {
        if (!items || !items.length) return '';
        const c = kindColor(kind || 'warn');
        return `<div style="border:1px solid ${c}; border-radius:8px;
            padding:10px 14px; margin:10px 0; color:${c};">
            <strong>${title}</strong><ul style="margin:6px 0 0 18px;">` +
            items.map(w => `<li>${escAttr(warnText(w))}</li>`).join('') + '</ul></div>';
    }

    // ==================================================================
    // C4 — GÖRÜNÜRLÜK ASİMETRİSİ: KATLANMIŞ BEYANIN SIFIR-TIKLAMA ROZETİ
    // ------------------------------------------------------------------
    // ÖLÇÜLEN KUSUR (P17B2-04): üründeki HER `<details>` varsayılan KAPALI
    // (11/11) ve 9'u beyan taşıyor. Tek ekranda 8.725 karakterlik beyan bir
    // tıklama arkasında dururken yeşil "GEÇTİ" rozetleri sıfır tıklamada
    // görünüyor. Kullanıcı kusursuz bir motor görüyor; kusurun beyanı
    // katlanmış duruyor.
    //
    // Katlamanın KENDİSİ kaldırılmıyor — stability_panel'in K3 katlayıcısı
    // 2.400 px'lik bir metin duvarını çözmek için BİLEREK konmuştu ve onu
    // geri açmak eski kusuru geri getirirdi. Bunun yerine özet satırına
    // SIFIR TIKLAMADA görünen bir sayaç rozeti iliştirilir.
    //
    // SAYI UYDURULMAZ: rozet, katlı gövdenin GERÇEK ölçümüdür —
    //   items : gövdedeki <li> madde sayısı
    //   lines : madde yoksa boş olmayan metin satırı sayısı
    //   chars : gövdenin karakter sayısı (bulgunun ölçtüğü büyüklük)
    // Gövde boşsa (henüz doldurulmamış `display:none` kabuk) rozet HİÇ
    // basılmaz. Uyarı imi (▲) yalnız katlının KENDİ MAKİNE ADI beyan
    // sözlüğüne uyduğunda konur; uymayan katlı nötr im (▸) alır ve hangi
    // adın eşleştiği ipucunda yazar — sınıflandırma denetlenebilir.
    //
    // SİMGE SEÇİMİ: uyarı imi ⚠ (U+26A0) DEĞİL ▲ (U+25B2). Berke'nin emoji
    // yasağı U+2600-U+27BF aralığını kapsıyor (tests/test_i18n.py
    // test_no_emoji_in_templates) ve ⚠ tam o aralıkta. Güvertenin kendi
    // kaynak çipleri de aynı sebeple geometrik simge kullanıyor (● ■ ◆ ×).
    // ==================================================================

    //: Beyan sözlüğü — ürünün KENDİ makine adlarından (ölçüldü: fea_basis,
    //  bp_basis, fea_t_basis, data-stab-fold="not-modelled", fea.basisTitle,
    //  common.assumptions).
    const DECL_FOLD_MARKS = ['basis', 'assum', 'decl', 'not-modelled',
                             'not_modelled', 'notmodelled', 'warning',
                             'caveat', 'limitation', 'withheld',
                             'uncertain', 'not-verified'];

    //: Rozetin özet satırındaki yuvası (aynı katlı ikinci kez işlenirse
    //  yeni rozet basılmaz, mevcut yuva tazelenir).
    const DECL_FOLD_SLOT_ATTR = 'data-hd-declfold-slot';

    // Katlının kendi makine adları: id + data-* + özetin çeviri anahtarı.
    // Bunlar ÜRÜNÜN kendi adlarıdır; burada ad UYDURULMAZ.
    function foldMachineNames(det, sum) {
        const parts = [];
        const at = function (el, name) {
            if (!el || typeof el.getAttribute !== 'function') return;
            const v = el.getAttribute(name);
            if (v) parts.push(name + '=' + v);
        };
        at(det, 'id');
        at(det, 'data-stab-fold');
        at(det, 'data-hd-declaration');
        at(sum, 'data-i18n');
        return parts;
    }

    // Katlı gövdesinin ÖLÇÜMÜ (özet satırı hariç).
    function declarationFoldInfo(det, sum) {
        const all = String((det && det.textContent) || '');
        const head = String((sum && sum.textContent) || '');
        const body = (head && all.indexOf(head) === 0)
            ? all.slice(head.length) : all;
        const chars = body.replace(/\s+/g, ' ').trim().length;
        let items = 0;
        if (det && typeof det.querySelectorAll === 'function') {
            const lis = det.querySelectorAll('li');
            items = lis ? lis.length : 0;
        }
        const lines = body.split('\n')
            .map(function (s) { return s.trim(); })
            .filter(function (s) { return s.length > 0; }).length;
        const names = foldMachineNames(det, sum);
        const low = names.join(' ').toLowerCase();
        let matched = null;
        for (let i = 0; i < DECL_FOLD_MARKS.length; i++) {
            if (low.indexOf(DECL_FOLD_MARKS[i]) !== -1) {
                matched = DECL_FOLD_MARKS[i];
                break;
            }
        }
        return {
            chars: chars, items: items, lines: lines,
            declaration: matched !== null, matched: matched, names: names,
        };
    }

    function ensureFoldSlot(sum) {
        if (typeof sum.querySelector === 'function') {
            const found = sum.querySelector('[' + DECL_FOLD_SLOT_ATTR + ']');
            if (found) return found;
        }
        const span = document.createElement('span');
        span.setAttribute(DECL_FOLD_SLOT_ATTR, '1');
        span.style.marginLeft = '8px';
        span.style.fontFamily = 'var(--hd-mono, monospace)';
        span.style.fontSize = '0.68rem';
        sum.appendChild(span);
        return span;
    }

    // Sayfadaki katlanmış bölümleri ölçer ve özet satırlarına sayaç
    // rozetini basar. Kaç katlı işaretlendiğini döndürür (test ölçümü).
    function markDeclarationFolds(root) {
        const host = root
            || ((typeof document !== 'undefined') ? document : null);
        if (!host || typeof host.querySelectorAll !== 'function') return 0;
        const folds = host.querySelectorAll('details');
        let marked = 0;
        for (let i = 0; i < (folds ? folds.length : 0); i++) {
            const det = folds[i];
            if (!det || typeof det.querySelector !== 'function') continue;
            const sum = det.querySelector('summary');
            if (!sum) continue;
            const info = declarationFoldInfo(det, sum);
            const slot = ensureFoldSlot(sum);
            if (!info.chars) {
                // Gövde BOŞ: ölçülecek bir şey yok, rozet basılmaz.
                slot.textContent = '';
                slot.setAttribute('title', '');
                continue;
            }
            // Rozetin sayısı EN BİLGİLİ ölçümdür: madde varsa madde, yoksa
            // satır, tek satırlık metin duvarıysa karakter (bulgunun ölçtüğü
            // büyüklük: "8.725 karakter beyan bir tıklama arkasında").
            const n = info.items > 0 ? String(info.items)
                : (info.lines > 1 ? String(info.lines) : String(info.chars) + 'c');
            const text = (info.declaration ? '▲ ' : '▸ ') + n;
            // DEĞİŞMEDİYSE YAZMA: rozetin kendisi bir DOM değişikliğidir;
            // aynı metni yeniden yazmak aşağıdaki gözlemciyi sonsuz
            // tetikler. Kararlı durumda hiçbir mutasyon üretilmez.
            if (slot.textContent !== text) slot.textContent = text;
            slot.style.color = kindColor(info.declaration ? 'warn' : 'dim');
            slot.setAttribute('title',
                'folded content measured: items=' + info.items
                + ' lines=' + info.lines + ' chars=' + info.chars
                + (info.declaration
                    ? ' | declaration fold, matched: ' + info.matched
                    : ' | not classified as a declaration fold')
                + (info.names.length ? ' | ' + info.names.join(' ') : ''));
            if (det.dataset) {
                det.dataset.hdDeclfold = info.declaration
                    ? 'declaration' : 'content';
                det.dataset.hdDeclfoldChars = String(info.chars);
            }
            marked += 1;
        }
        return marked;
    }

    // Katlılar hesap sonrası DOLDURULUYOR (paneller ekranı sonradan çiziyor),
    // bu yüzden ölçüm bir kez değil, DOM değiştikçe tazelenir. Gözlemci
    // kendi yazdığımız rozeti tekrar tetiklemesin diye iki kapı var:
    // (1) yazma sırasında bayrak, (2) "değişmediyse yazma" kuralı.
    let declFoldTimer = null;
    let declFoldBusy = false;

    function runDeclarationFolds() {
        declFoldTimer = null;
        declFoldBusy = true;
        try { markDeclarationFolds(document); } catch (e) { /* DOM yok */ }
        setTimeout(function () { declFoldBusy = false; }, 0);
    }

    function scheduleDeclarationFolds() {
        if (declFoldBusy || declFoldTimer !== null) return;
        declFoldTimer = setTimeout(runDeclarationFolds, 250);
    }

    function startDeclarationFoldWatch() {
        if (typeof document === 'undefined' || !document.body) return;
        scheduleDeclarationFolds();
        if (typeof window === 'undefined' || !window.MutationObserver) return;
        try {
            const obs = new window.MutationObserver(scheduleDeclarationFolds);
            obs.observe(document.body, { childList: true, subtree: true });
        } catch (e) { /* gözlemci yoksa tek seferlik ölçüm yeter */ }
    }

    // ==================================================================
    // E3 — DEĞER KAYNAĞI RENKLENDİRMESİ  (kaynak beyanının pano karşılığı)
    // ------------------------------------------------------------------
    // Renk tablosu motor_viz3d.js'in SOURCE_COLORS'ıyla BİREBİR aynıdır:
    // 3B sahnedeki durum çipi ile panodaki rozet aynı rengi aynı anlamda
    // kullanır (tek tasarım dili — B4'ün grafik/pano karşılığı E3).
    //
    // RENK TEK BAŞINA TAŞIYICI DEĞİLDİR. Her rozet renkle BİRLİKTE bir
    // GEOMETRİK SİMGE ve bir METİN ETİKETİ taşır; simgeler Plotly'nin
    // marker sembolleriyle bire bir eşlenir (circle/square/diamond/x), yani
    // grafikteki nokta ile panodaki çip aynı şekli gösterir. Böylece renk
    // körlüğünde ve gri basımda da ayırt edilir (WCAG 1.4.1 "renge
    // dayanmama" ilkesi).
    //
    // Sınıflandırma kaynağın KENDİ beyanından okunur — uydurulmaz. Depoda
    // ölçülen beyan biçimleri (2026-08-04, grep ile):
    //   <alan>_basis   : serbest metin gerekçe
    //                    ör. 'thermal_protection module default 293,15 K'
    //   <alan>_source  : üretici etiketi
    //                    ör. 'user_override', 'user input (tank_temperature)',
    //                        'l_star_derived', 'grain_limited'
    //   status / model : 'modelled' | 'not_modelled' | 'not_computed' |
    //                    'not_analyzed' | 'not_sized' | 'fallback' | 'clamped'
    // Beyan HİÇ yoksa `declared:false` döner ve ipucu metni bunu açıkça
    // söyler — "hesaplandı" iddiası beyansız değere yazılmaz.
    // ==================================================================
    // ÖH D32 · OH-D31-18 — `assumed` ambersi token katmanında
    // (`--hd-amber-source`); değer değişmedi, ayna bekçiyle kilitli
    // (tests/test_d32_arayuz_panel_a1.py::TestOHD3118AmberTokeni).
    const SOURCE_COLORS = {           // motor_viz3d.js ile birebir aynı
        computed: '#39d6ec',
        user: '#e8edf2',
        assumed: '#ffb347',          // = var(--hd-amber-source)
        missing: '#8a93a0',
    };
    // Simge + Plotly marker eşlemesi (renk körlüğü: şekil ayırt eder)
    const SOURCE_SYMBOLS = {
        computed: '●',           // ● dolu daire  -> plotly 'circle'
        user: '■',               // ■ dolu kare   -> plotly 'square'
        assumed: '◆',            // ◆ eşkenar     -> plotly 'diamond'
        missing: '×',            // × çarpı       -> plotly 'x'
    };
    const SOURCE_PLOT_SYMBOLS = {
        computed: 'circle', user: 'square', assumed: 'diamond', missing: 'x',
    };
    const SOURCE_LABEL_KEYS = {
        computed: 'dock.src.computed',
        user: 'dock.src.user',
        assumed: 'dock.src.assumed',
        missing: 'dock.src.missing',
    };
    const SOURCE_LABEL_FALLBACK = {
        computed: 'COMPUTED', user: 'USER', assumed: 'ASSUMED',
        missing: 'NOT MODELLED',
    };
    const SOURCE_TIP_KEYS = {
        computed: 'dock.src.tipComputed',
        user: 'dock.src.tipUser',
        assumed: 'dock.src.tipAssumed',
        missing: 'dock.src.tipMissing',
    };
    const SOURCE_TIP_FALLBACK = {
        computed: 'Produced by the solver for this design.',
        user: 'Entered by you; the solver used it as given.',
        assumed: 'Not solved here — a default, literature or clamped value.',
        missing: 'Not modelled: no value was computed for this quantity.',
    };
    const SOURCE_KINDS = ['computed', 'user', 'assumed', 'missing'];

    // status / model / *_source etiketlerinin dört duruma eşlemesi.
    const SOURCE_STATUS_MAP = {
        modelled: 'computed', modeled: 'computed', computed: 'computed',
        solved: 'computed', analyzed: 'computed', analysed: 'computed',
        sized: 'computed', success: 'computed', ok: 'computed',
        tabulated: 'computed',
        user: 'user', user_input: 'user', user_override: 'user',
        user_supplied: 'user', override: 'user',
        assumed: 'assumed', assumption: 'assumed', 'default': 'assumed',
        fallback: 'assumed', clamped: 'assumed', estimated: 'assumed',
        literature: 'assumed', nominal: 'assumed', typical: 'assumed',
        not_modelled: 'missing', not_modeled: 'missing', not_computed: 'missing',
        not_analyzed: 'missing', not_analysed: 'missing', not_sized: 'missing',
        not_applicable: 'missing', unavailable: 'missing', missing: 'missing',
        error: 'missing', skipped: 'missing', none: 'missing',
    };

    // Serbest metin beyanları (İngilizce + Türkçe). Öncelik: modellenmedi >
    // kullanıcı > varsayım; hiçbiri eşleşmezse metin bir hesap gerekçesidir.
    const SRC_MISSING_RE = new RegExp(
        'not[_ ](?:modell?ed|computed|analy[sz]ed|sized|available|applicable)'
        + '|modellenme|hesaplanma(?:dı|di|mış|mis)|veri yok|değer yok', 'i');
    const SRC_USER_RE = new RegExp(
        '\\buser\\b|user[_ ]?(?:input|override|supplied|given|value)'
        + '|\\bkullanıcı|kullanici|\\bgirdi\\b|override', 'i');
    const SRC_ASSUMED_RE = new RegExp(
        '\\bassum|\\bdefault|fallback|typical|nominal|literature|handbook'
        + '|rule[- ]of[- ]thumb|estimat|approxim|placeholder|clamp'
        // ÖH D24 / P11B2-10 — OLUMLU KÖKEN İMLERİ. Ürünün kendi beyan
        // metinlerinden ölçüldü (git grep): 'materials_db recommended
        // design factor…', 'DECLARED DESIGN CHOICE…', 'model constant…'
        // üçü de bir VARSAYIMI adlandırır; listede karşılığı olmadığı için
        // sınıflandırıcı bu cümlelerde yalnız olumsuzlama parçasını
        // görüyordu ve 'user'/'missing' damgalıyordu.
        + '|recommend|declared|design choice|model constant'
        + '|varsay|öngör|tahmin|kabul edil|yerel üret|sınırlan|kırpıl', 'i');

    // ------------------------------------------------------------------
    // ÖH D24 / P11B2-10 — OLUMSUZLAMA KÖRLÜĞÜ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (a3/once_e3.json: 17 gerçek beyan metninin 6'sı yanlış):
    // sınıflandırıcı bir cümlenin İÇİNDEKİ kelimeye bakıyordu, cümlenin
    // OLUMSUZLAMASINA değil. Sonuç: "…NOT the design safety factor entered
    // by the user" diyen alana USER ("Entered by you") damgası, "model
    // constant, not computed from this design" diyen ve hesapta GERÇEKTEN
    // KULLANILAN sayıya NOT MODELLED damgası.
    //
    // Kural: bir karşıtlık yan cümlesi ("…, not a user input", "; NOT
    // auto-sized", "(no user value)") değerin NE OLMADIĞINI söyler; köken
    // hükmü metnin OLUMLU parçasından verilir. Olumlu parça hüküm
    // vermiyorsa TAM METNE dönülür — böylece kendisi bir olumsuzlama olan
    // gerçek beyanlar ("not modelled", "This effect is not modelled…")
    // bozulmadan 'missing' kalır.
    const SRC_CONTRAST_RE = new RegExp(
        '[;,(]\\s*(?:and\\s+|but\\s+|which\\s+is\\s+)?(?:NOT|not|no)\\b[^.;)]*\\)?'
        + '|(?:^|[.\\s])(?:NOT|not|no)\\s+(?:a\\s+|an\\s+|the\\s+)?'
        + '[a-z_ -]{0,40}?'
        + '(?:entered|supplied|given|provided|specified|auto-sized|autosized|'
        + 'computed\\s+result|user\\s+input|user\\s+value)'
        + '(?:\\s+by\\s+the\\s+user)?[^.;)]*', 'g');

    function sourcePositiveText(text) {
        return String(text).replace(SRC_CONTRAST_RE, ' ')
            .replace(/\s+/g, ' ').trim();
    }

    function srcMatchKind(s) {
        if (SRC_MISSING_RE.test(s)) return 'missing';
        if (SRC_USER_RE.test(s)) return 'user';
        if (SRC_ASSUMED_RE.test(s)) return 'assumed';
        return null;
    }

    function sourceColor(kind) {
        return SOURCE_COLORS[kind] || SOURCE_COLORS.missing;
    }
    function sourceSymbol(kind) {
        return SOURCE_SYMBOLS[kind] || SOURCE_SYMBOLS.missing;
    }
    function sourcePlotSymbol(kind) {
        return SOURCE_PLOT_SYMBOLS[kind] || SOURCE_PLOT_SYMBOLS.missing;
    }
    function sourceLabel(kind) {
        const k = SOURCE_KINDS.indexOf(kind) === -1 ? 'missing' : kind;
        return T(SOURCE_LABEL_KEYS[k], SOURCE_LABEL_FALLBACK[k]);
    }

    // Tek bir beyan metnini/etiketini dört durumdan birine çevirir.
    // Eşleşme yoksa null döner (çağıran bir sonraki beyana bakar).
    function sourceKindOfText(text) {
        if (text == null) return null;
        const s = String(text).trim();
        if (!s) return null;
        const direct = SOURCE_STATUS_MAP[s.toLowerCase()];
        if (direct) return direct;
        // Karşıtlık yan cümlesi çıkarılmış metin önce denenir (P11B2-10).
        const olumlu = sourcePositiveText(s);
        if (olumlu && olumlu !== s) {
            const k = srcMatchKind(olumlu);
            if (k) return k;
        }
        return srcMatchKind(s);
    }

    // Bir sözlükteki alanın kaynağını çözer.
    //   obj   : değeri ve beyanlarını taşıyan blok
    //   field : alan adı ('wall_thickness' gibi)
    // Dönen: {kind, declared, value, basis, source, status}
    function sourceOf(obj, field, opts) {
        const o = obj || {};
        const value = (field == null) ? (opts && opts.value) : o[field];
        const basis = (field == null) ? (o.basis || null) : o[field + '_basis'];
        const source = (field == null) ? (o.source || null) : o[field + '_source'];
        const status = (field == null)
            ? (o.status || o.model || null)
            : (o[field + '_status'] || o[field + '_model'] || null);
        const declared = !!(basis || source || status);
        const numeric = typeof value === 'number';
        // Sayı yok ya da sonlu değilse: hesaplanmış bir değer YOKTUR.
        if (value == null || (numeric && !Number.isFinite(value))) {
            return { kind: 'missing', declared: declared, value: null,
                     basis: basis || null, source: source || null,
                     status: status || null };
        }
        const kind = sourceKindOfText(status)
            || sourceKindOfText(source)
            || sourceKindOfText(basis)
            || 'computed';
        return { kind: kind, declared: declared, value: value,
                 basis: basis || null, source: source || null,
                 status: status || null };
    }

    // Rozet sayacı: lejant YALNIZCA ekranda en az bir kaynak çipi varken
    // gösterilir (kullanılmayan renk anahtarı kullanıcıyı yanıltır).
    let sourceChipCount = 0;

    function escAttr(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Kaynak çipi: renk + simge + metin etiketi (üçü birden).
    // info: sourceOf() çıktısı ya da doğrudan durum adı.
    function sourceChip(info, extraTitle) {
        const data = (typeof info === 'string') ? { kind: info, declared: false } : (info || {});
        const kind = SOURCE_KINDS.indexOf(data.kind) === -1 ? 'missing' : data.kind;
        const col = sourceColor(kind);
        const tip = [T(SOURCE_TIP_KEYS[kind], SOURCE_TIP_FALLBACK[kind])];
        if (data.basis) tip.push(SRV(String(data.basis)));
        else if (data.source) tip.push(SRV(String(data.source)));
        else if (data.declared && data.status) tip.push(SRV(String(data.status)));
        else if (!data.declared) {
            tip.push(T('dock.src.undeclared',
                'No basis/source declaration accompanies this field.'));
        }
        if (extraTitle) tip.push(String(extraTitle));
        sourceChipCount += 1;
        maybeShowSourceLegend();
        return `<span class="ad-src-chip" data-src-kind="${kind}"
            title="${escAttr(tip.join(' — '))}"
            style="border:1px solid ${col}; color:${col}; border-radius:6px;
            padding:1px 7px; margin-left:6px; font-family:var(--hd-mono, monospace);
            font-size:0.66rem; letter-spacing:0.06em; white-space:nowrap;
            display:inline-block;"><span aria-hidden="true"
            >${sourceSymbol(kind)}</span> <span${i18nAttr(SOURCE_LABEL_KEYS[kind])}
            >${sourceLabel(kind)}</span></span>`;
    }

    // Değer + kaynak çipi (tablo hücresi kalıbı). Değer yoksa em-dash basılır
    // — sahte sayı yazılmaz.
    function sourceCell(obj, field, opts) {
        const o = opts || {};
        const info = sourceOf(obj, field, o);
        let txt = '—';
        if (typeof info.value === 'number') {
            txt = (o.digits == null) ? String(dockSigFig(info.value, o.sig))
                                     : fmt(info.value, o.digits);
        } else if (info.value != null) {
            txt = String(info.value);
        }
        const unit = (info.value != null && o.unit) ? ' ' + o.unit : '';
        return `<span data-src-value="${escAttr(field || '')}">${txt}${unit}</span>`
            + sourceChip(info);
    }

    // ------------------------------------------------------------------
    // ÖH D26 / P11B2-10 — SINIFLANDIRICIYI PANELE BAĞLAYAN İKİ YARDIMCI
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (a1/once.json): 16 panelin 13'ü ucun beyan alanlarını
    // (`X_basis` / `X_source` / `X_status` / `X_model`; 81 ayrı alan adı)
    // OKUYOR, ama sınıflandırıcıyı çağıran panel sayısı 2 idi — 11 panel
    // beyanı ekrana DÜZ METİN olarak döküyor, hükmü (hesaplandı / sizin
    // girdiniz / varsayım / modellenmedi) hiç vermiyordu. Katmanın ölü
    // kalmasının sebebi teknik değil ergonomikti: tek bir satıra çip
    // eklemek için panelin `sourceOf` + `declared` kapısı + `chip`
    // üçlüsünü elle kurması gerekiyordu, o yüzden paneller kendi
    // damgalarını UYDURUYORDU (`chip({kind:'assumed'})`, 5 yer).
    //
    // `ledger` : bir bloğun BÜTÜN beyanlarını tarayıp her biri için ortak
    //            hükmü basan katlı defter (24 beyanlı cfd_panel gibi
    //            bloklar tek çağrıyla bağlanır).
    // İkisi de FAIL-CLOSED: beyan yoksa hiçbir şey basılmaz — "hesaplandı"
    // iddiası beyansız değere yazılmaz (doktrin 1).

    // Bir bloktaki beyan alanlarını (X_basis/_source/_status/_model)
    // tabana göre gruplar. Dönen: [{field, basis, source, status}, ...]
    const SRC_DECL_SUFFIX = ['_basis', '_source', '_status', '_model'];

    // opts.deep     : iç bloklara da in (uçlar beyanı `cfd.*`, `sep.*`,
    //                 `safety_factors.*` gibi alt sözlüklerde yayımlıyor)
    // opts.maxDepth : iniş derinliği (varsayılan 3)
    function sourceDeclarations(obj, opts) {
        const o = opts || {};
        const maxDepth = o.deep ? (o.maxDepth == null ? 3 : o.maxDepth) : 0;
        const bases = {};
        const order = [];
        const gezildi = [];

        function kayit(holder, prefix, key, suf) {
            const val = holder[key];
            // Beyan METİN olmalı: sayı ya da nesne beyan değildir.
            if (typeof val !== 'string' || !val.trim()) return;
            const base = key.slice(0, key.length - suf.length);
            if (!base) return;
            const yol = prefix ? (prefix + '.' + base) : base;
            if (!bases[yol]) {
                bases[yol] = { field: yol, base: base, holder: holder,
                               basis: null, source: null, status: null };
                order.push(yol);
            }
            if (suf === '_basis') bases[yol].basis = val;
            else if (suf === '_source') bases[yol].source = val;
            else bases[yol].status = bases[yol].status || val;
        }

        function tara(node, prefix, depth) {
            if (!node || typeof node !== 'object' || Array.isArray(node)) return;
            if (gezildi.indexOf(node) !== -1) return;   // döngü koruması
            gezildi.push(node);
            const keys = Object.keys(node);
            keys.forEach(function (key) {
                for (let i = 0; i < SRC_DECL_SUFFIX.length; i++) {
                    const suf = SRC_DECL_SUFFIX[i];
                    if (key.length <= suf.length) continue;
                    if (key.slice(-suf.length) !== suf) continue;
                    kayit(node, prefix, key, suf);
                    return;
                }
            });
            if (depth >= maxDepth) return;
            keys.forEach(function (key) {
                const v = node[key];
                if (v && typeof v === 'object' && !Array.isArray(v)) {
                    tara(v, prefix ? (prefix + '.' + key) : key, depth + 1);
                }
            });
        }

        tara(obj || {}, '', 0);
        return order.map(function (b) { return bases[b]; });
    }

    // Beyan defteri: bloğun her beyanı için ortak sınıflandırıcının hükmü
    // + beyan metninin kendisi. Beyan yoksa '' döner (bölüm hiç basılmaz).
    //   opts.title  : başlık metni
    //   opts.values : sayısal değerleri taşıyan blok (varsayılan: obj)
    function sourceLedger(obj, opts) {
        const o = opts || {};
        const decls = sourceDeclarations(obj, o);
        if (!decls.length) return '';
        const rows = decls.map(function (d) {
            // Değer beyanın KENDİ bloğundan okunur; yoksa satır YALNIZ
            // beyanı sınıflandırır (uydurma sayı basılmaz — em-dash).
            const vals = o.values || d.holder || {};
            const has = Object.prototype.hasOwnProperty.call(vals, d.base);
            // FAIL-CLOSED: beyanın tarif ettiği DEĞER yoksa sınıflandırıcıya
            // `null` gider ve hüküm 'missing' olur. Beyan metnini "değer"
            // yerine koymak, sayısı OLMAYAN ama "computed from the Bartz
            // correlation" diyen bir alana HESAPLANDI damgası bastırıyordu;
            // olmayan sayı için hesap iddiası doktrin 1 ihlalidir. Beyan
            // metni satırda ayrıca gösterilir — bilgi kaybolmaz.
            const info = sourceOf(
                { basis: d.basis, source: d.source, status: d.status },
                null,
                { value: has ? vals[d.base] : null });
            let txt = '—';
            if (has) {
                const v = vals[d.base];
                if (typeof v === 'number' && Number.isFinite(v)) {
                    txt = String(dockSigFig(v, o.sig));
                } else if (v != null && typeof v !== 'object') {
                    txt = escAttr(String(v));
                }
            }
            // ÖH D37 A1a · DV36-01 — DAYANAK HÜCRESİ serverText'TEN GEÇER.
            // ÖLÇÜLDÜ (D36 dil2 a2 sonra.json K4; D37 a1/once/olcum.json):
            // gerçek /analyze_safety geri çekme yanıtında TR ekranda patlayıcı
            // gerekçe cümlesi bu hücrede İngilizce kalıyordu (panel geneli
            // TR = 1); aynı cümle çip ipucunda (`sourceChip`) zaten
            // çevriliyordu. Sunucu düz metnidir: `SRV` sözlük + desenle çevirir,
            // eşleşme yoksa metni AYNEN döndürür (uydurma çeviri yok).
            const beyan = SRV(d.basis || d.source || d.status || '');
            return '<tr><td style="' + TD
                + ' font-family:var(--hd-mono, monospace); font-size:0.72rem;"'
                + ' data-src-field="' + escAttr(d.field) + '">'
                + escAttr(d.field) + '</td><td style="' + TD + '">'
                + txt + sourceChip(info) + '</td><td style="' + TD
                + ' color:var(--hd-ink-dim, #7d97a5); font-size:0.74rem;">'
                + escAttr(beyan) + '</td></tr>';
        }).join('');
        const title = o.title
            || T('dock.src.ledger', 'VALUE SOURCES') + ' (' + decls.length + ')';
        // KATLI VARSAYILAN OLARAK KAPALI. Z5/C4 doktrini: hiçbir ürün
        // katlısı `open` ile açılmaz (bekçi: tests/test_z5_rozet_dock.py
        // ::test_c4_urun_katlilarinin_hepsi_hala_varsayilan_kapali).
        // Sıfır tıklamada okunacak sayı özet satırındaki rozetten
        // gelir — `markDeclarationFolds` onu gerçek DOM'da basar.
        return '<details data-src-ledger="' + decls.length + '"'
            + ' style="margin:8px 0;">'
            + '<summary style="cursor:pointer; color:var(--hd-ink-dim, #7d97a5);'
            + ' font-family:var(--hd-mono, monospace); font-size:0.72rem;'
            + ' letter-spacing:0.08em;">' + escAttr(title) + '</summary>'
            + '<table style="' + TBL + '">' + rows + '</table></details>';
    }

    // Defteri doğrudan panel köküne basar — panel TEK satırla bağlanır.
    // Beyan yoksa hiçbir düğüm eklenmez (boş "kaynaklar" başlığı çıkmaz).
    // Dönen: basılan beyan satırı sayısı (ölçüm için).
    function sourceLedgerInto(root, obj, opts) {
        if (!root || typeof document === 'undefined'
            || typeof document.createElement !== 'function') return 0;
        const decls = sourceDeclarations(obj, opts || {});
        if (!decls.length) return 0;
        const html = sourceLedger(obj, opts);
        if (!html) return 0;
        const div = document.createElement('div');
        div.setAttribute('data-src-ledger-host', '1');
        div.innerHTML = html;
        root.appendChild(div);
        return decls.length;
    }

    // Dört durumu birden gösteren anahtar (lejant).
    function sourceLegend() {
        const items = SOURCE_KINDS.map(function (k) {
            const col = sourceColor(k);
            return `<span data-src-legend="${k}" style="color:${col};
                font-family:var(--hd-mono, monospace); font-size:0.66rem;
                letter-spacing:0.06em; white-space:nowrap;"><span aria-hidden="true"
                >${sourceSymbol(k)}</span> <span${i18nAttr(SOURCE_LABEL_KEYS[k])}
                >${sourceLabel(k)}</span></span>`;
        }).join('');
        return `<span id="ad_src_legend_body" style="display:inline-flex; gap:12px;
            flex-wrap:wrap; align-items:center;"><span
            style="color:var(--hd-ink-dim, #7d97a5); font-family:var(--hd-mono, monospace);
            font-size:0.66rem; letter-spacing:0.08em;"
            data-i18n="dock.src.legend">${T('dock.src.legend', 'VALUE SOURCE')}</span>
            ${items}</span>`;
    }

    function maybeShowSourceLegend() {
        const host = document.getElementById('ad_src_legend');
        if (!host || sourceChipCount < 1) return;
        if (host.getAttribute('data-filled') === '1') return;
        host.innerHTML = sourceLegend();
        host.setAttribute('data-filled', '1');
        host.style.display = 'inline-flex';
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
    }

    // Plotly izleri için: aynı dört durum, aynı renk, aynı şekil.
    // Panel bir iz çizerken marker'ı bununla kurarsa grafik ile pano
    // aynı dili konuşur.
    function sourceMarker(kind) {
        const k = SOURCE_KINDS.indexOf(kind) === -1 ? 'missing' : kind;
        return { color: sourceColor(k), symbol: sourcePlotSymbol(k), size: 7 };
    }

    // ==================================================================
    // E2 — "NE DEĞİŞTİ" FARKI
    // ------------------------------------------------------------------
    // Yeni sonuç geldiğinde bir önceki sonuçla SAYISAL farkı çıkarır ve
    // değişen büyüklükleri eski → yeni rozetiyle işaretler.
    //
    // EŞİK NEDEN 1e-5 (tek yerde tanımlı, beyanlı):
    // Güverte form alanları çözücü değerini 6 anlamlı basamağa yuvarlayarak
    // ön-doldurur (DOCK_SIGFIG). Bu dosyanın üst bölümünde ÖLÇÜLEN sonuç:
    // 6 basamağa yuvarlanmış girdiyle koşulan üç uçtaki en büyük bağıl
    // çıktı sapması 5,1e-06. Yani 1e-5'in ALTINDAKİ bağıl değişim, tasarım
    // hiç değişmeden yalnız ön-dolum/yuvarlama zincirinden doğabilir —
    // kullanıcıya "şu değişti" diye gösterilmesi yanıltıcı olur. Eşik bu
    // ölçülen gürültü tabanının hemen üstüne konur.
    //
    // MUTLAK eşik YOKTUR ve konmaz: bu katman alanların birimini bilmez
    // (metre mi, kelvin mi, newton mu), dolayısıyla "0,001'den küçük fark
    // önemsizdir" diyemez. Bağıl ölçü paydası max(|eski|,|yeni|) olduğundan
    // sıfıra bölme de oluşmaz; iki değer de tam 0 ise fark 0'dır.
    // ==================================================================
    // MALİYET ÖLÇÜLDÜ (2026-08-04, gerçek veri): /calculate_solid'in
    // 146 KB'lik yanıtı ile aynı yanıtın tek girdisi %2 değiştirilmiş hâli
    // karşılaştırıldı — 1557 sayı, çağrı başına 0,4 ms (node, 10 tekrar
    // ortalaması). Aynı yanıt kendisiyle karşılaştırıldığında 0 değişim
    // bildirildi (gerçek veride yanlış pozitif yok). %2'lik tek girdi
    // değişimi 200'ün üzerinde alanı oynattığı için rapor tavanı 2000'e
    // konuldu: tavana çarpılırsa `truncated` ile açıkça beyan edilir.
    const DIFF_REL_EPS = 1e-5;      // TEK tanım — başka yerde sayı yazılmaz
    const DIFF_MAX_DEPTH = 8;       // döngüsel/derin veri koruması
    const DIFF_SERIES_LIMIT = 8;    // bundan uzun sayı dizileri seri sayılır
    const DIFF_MAX_ENTRIES = 2000;  // rapor boyu tavanı (truncated ile beyanlı)
    const DIFF_TOP_N = 8;           // şeritte gösterilen en büyük değişim sayısı

    function isPlainObject(v) {
        return v !== null && typeof v === 'object' && !Array.isArray(v);
    }

    function relChange(a, b) {
        const scale = Math.max(Math.abs(a), Math.abs(b));
        if (scale === 0) return 0;
        return Math.abs(b - a) / scale;
    }

    function joinPath(base, key) {
        return base ? (base + '.' + key) : String(key);
    }

    // İki sonuç sözlüğünün sayısal farkı. YALNIZ sayı karşılaştırılır;
    // metin/boolean alanlar bu katmanın konusu değildir.
    function diffCompute(prev, next, opts) {
        const eps = (opts && Number.isFinite(opts.eps)) ? opts.eps : DIFF_REL_EPS;
        const out = {
            changes: [], series: [], added: [], removed: [],
            threshold: eps, compared: 0, truncated: false, hasBaseline: true,
        };
        if (!isPlainObject(prev) || !isPlainObject(next)) {
            out.hasBaseline = false;
            return out;
        }

        function pushChange(entry) {
            if (out.changes.length >= DIFF_MAX_ENTRIES) { out.truncated = true; return; }
            out.changes.push(entry);
        }

        function compareNumbers(path, a, b) {
            out.compared += 1;
            const aFin = Number.isFinite(a);
            const bFin = Number.isFinite(b);
            if (aFin && bFin) {
                const rel = relChange(a, b);
                if (rel > eps) {
                    pushChange({ path: path, old: a, 'new': b, rel: rel,
                                 finite: true, dir: (b > a ? 'up' : 'down') });
                }
                return;
            }
            if (aFin !== bFin || a !== b) {
                // Sonlu olmayan bir değerin belirmesi/kaybolması gerçek bir
                // değişimdir; bağıl ölçüsü tanımsızdır (rel: null).
                pushChange({ path: path, old: aFin ? a : null, 'new': bFin ? b : null,
                             rel: null, finite: false, dir: null });
            }
        }

        function compareSeries(path, a, b) {
            const n = Math.min(a.length, b.length);
            let changed = 0;
            let maxRel = 0;
            for (let i = 0; i < n; i++) {
                const x = a[i], y = b[i];
                if (typeof x !== 'number' || typeof y !== 'number') continue;
                if (!Number.isFinite(x) || !Number.isFinite(y)) {
                    if (x !== y) changed += 1;
                    continue;
                }
                const rel = relChange(x, y);
                if (rel > eps) { changed += 1; if (rel > maxRel) maxRel = rel; }
            }
            out.compared += n;
            if (changed > 0 || a.length !== b.length) {
                out.series.push({ path: path, points: b.length, changed: changed,
                                  maxRel: maxRel,
                                  lengthChanged: a.length !== b.length,
                                  oldPoints: a.length });
            }
        }

        function walk(a, b, path, depth) {
            if (depth > DIFF_MAX_DEPTH) return;
            if (Array.isArray(a) && Array.isArray(b)) {
                const numeric = a.every(function (v) { return typeof v === 'number'; })
                    && b.every(function (v) { return typeof v === 'number'; });
                if (numeric && Math.max(a.length, b.length) > DIFF_SERIES_LIMIT) {
                    compareSeries(path, a, b);
                    return;
                }
                const n = Math.max(a.length, b.length);
                for (let i = 0; i < n; i++) {
                    walk(a[i], b[i], path + '[' + i + ']', depth + 1);
                }
                return;
            }
            if (isPlainObject(a) && isPlainObject(b)) {
                const seen = {};
                Object.keys(a).forEach(function (k) { seen[k] = true; });
                Object.keys(b).forEach(function (k) { seen[k] = true; });
                Object.keys(seen).forEach(function (k) {
                    walk(a[k], b[k], joinPath(path, k), depth + 1);
                });
                return;
            }
            const aNum = typeof a === 'number';
            const bNum = typeof b === 'number';
            if (aNum && bNum) { compareNumbers(path, a, b); return; }
            if (aNum && b === undefined) { out.removed.push(path); return; }
            if (bNum && a === undefined) { out.added.push(path); return; }
            // metin/boolean/nesne-tip değişimi: sayısal fark katmanının
            // konusu değil, sessizce geçilir.
        }

        walk(prev, next, '', 0);
        out.changes.sort(function (x, y) { return (y.rel || 0) - (x.rel || 0); });
        return out;
    }

    // Değişim rozeti: eski → yeni (+ bağıl değişim yüzdesi).
    // Renk NÖTRDÜR: artış "iyi", azalış "kötü" değildir; yön yalnız
    // ▲/▼ simgesiyle bildirilir.
    function diffBadge(change) {
        if (!change) return '';
        const oldTxt = (change.old == null) ? '—' : String(dockSigFig(change.old, 5));
        const newTxt = (change['new'] == null) ? '—' : String(dockSigFig(change['new'], 5));
        const arrow = change.dir === 'up' ? '▲'
            : (change.dir === 'down' ? '▼' : '•');
        const pct = (change.rel == null) ? T('common.unknown', 'unknown')
            : (dockSigFig(change.rel * 100, 3) + ' %');
        const tip = TF('dock.diff.badgeTip', { pct: pct },
            'Changed vs the previous result — relative change {pct}.');
        return `<span class="ad-diff-badge" data-diff-badge="${escAttr(change.path || '')}"
            title="${escAttr(tip)}"
            style="border:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));
            color:var(--hd-ink, #cfe8f2); border-radius:6px; padding:1px 7px;
            margin-left:6px; font-family:var(--hd-mono, monospace); font-size:0.66rem;
            white-space:nowrap; display:inline-block;"><span
            style="color:var(--hd-ink-dim, #7d97a5);">${oldTxt}</span> → ${newTxt}
            <span style="color:var(--hd-ink-dim, #7d97a5);">${arrow} ${pct}</span></span>`;
    }

    // Panel çıktısındaki `data-diff-path="yol"` taşıyan elemanlara rozet
    // ekler. Yol değişmediyse hiçbir şey eklenmez (eşik altı gürültü
    // işaretlenmez — kural E2).
    function diffAnnotate(rootEl, result) {
        if (!rootEl || !result || !result.changes || !rootEl.querySelectorAll) return 0;
        const index = {};
        result.changes.forEach(function (c) { index[c.path] = c; });
        let marked = 0;
        const nodes = rootEl.querySelectorAll('[data-diff-path]');
        Array.prototype.forEach.call(nodes, function (el) {
            const path = el.getAttribute('data-diff-path');
            const change = index[path];
            if (!change) return;
            if (el.getAttribute('data-diff-marked') === '1') return;
            el.insertAdjacentHTML
                ? el.insertAdjacentHTML('beforeend', diffBadge(change))
                : (el.innerHTML += diffBadge(change));
            el.setAttribute('data-diff-marked', '1');
            marked += 1;
        });
        return marked;
    }

    // "Ne değişti" şeridi — eşik AÇIKÇA yazılır, gizli kural bırakılmaz.
    function diffStripHtml(result) {
        const head = `<strong data-i18n="dock.diff.title">${
            T('dock.diff.title', 'What changed')}</strong>`;
        if (!result || !result.hasBaseline) {
            return head + ` <span style="color:var(--hd-ink-dim, #7d97a5);"
                data-i18n="dock.diff.first">${T('dock.diff.first',
                'First result stored as the reference — nothing to compare yet.')}</span>`;
        }
        const epsPct = dockSigFig(result.threshold * 100, 3);
        const basis = `<div style="color:var(--hd-ink-faint, #6a8491); margin-top:4px;">${
            TF('dock.diff.basis', { pct: epsPct },
               'Only relative changes above {pct} % are marked; smaller '
               + 'differences are within the 6-significant-digit pre-fill noise '
               + 'of the input fields.')}</div>`;
        if (!result.changes.length && !result.series.length
            && !result.added.length && !result.removed.length) {
            return head + ` <span style="color:var(--hd-ink-dim, #7d97a5);"
                data-i18n="dock.diff.none">${T('dock.diff.none',
                'No numeric change above the threshold.')}</span>` + basis;
        }
        const rows = result.changes.slice(0, DIFF_TOP_N).map(function (c) {
            return `<div style="margin:3px 0;"><span
                style="font-family:var(--hd-mono, monospace);
                color:var(--hd-ink, #cfe8f2);">${escAttr(c.path)}</span>${diffBadge(c)}</div>`;
        }).join('');
        const seriesRows = result.series.slice(0, DIFF_TOP_N).map(function (s) {
            return `<div style="margin:3px 0; font-family:var(--hd-mono, monospace);
                color:var(--hd-ink-dim, #7d97a5);">${TF('dock.diff.series',
                { path: escAttr(s.path), changed: s.changed, points: s.points },
                '{path}: {changed} of {points} series points changed')}</div>`;
        }).join('');
        const extra = [];
        if (result.changes.length > DIFF_TOP_N) {
            extra.push(TF('dock.diff.more', { count: result.changes.length - DIFF_TOP_N },
                          '+{count} more changed values'));
        }
        if (result.added.length) {
            extra.push(TF('dock.diff.added', { count: result.added.length },
                          '{count} new numeric fields appeared'));
        }
        if (result.removed.length) {
            extra.push(TF('dock.diff.removed', { count: result.removed.length },
                          '{count} numeric fields disappeared'));
        }
        if (result.truncated) {
            extra.push(T('dock.diff.truncated',
                'The change list was truncated at the reporting cap.'));
        }
        const extraHtml = extra.length
            ? `<div style="color:var(--hd-ink-dim, #7d97a5); margin-top:4px;">${
                extra.join(' · ')}</div>` : '';
        return head + `<span style="color:var(--hd-ink-dim, #7d97a5);"> ${
            TF('dock.diff.count', { count: result.changes.length },
               '{count} values changed')}</span>`
            + `<div style="margin-top:6px;">${rows}${seriesRows}</div>`
            + extraHtml + basis;
    }

    // Derin kopya: sonuç sözlüğü sonradan yerinde değiştirilse bile
    // referans anlık görüntüsü bozulmasın (JSON turu Infinity'yi null'a
    // çevirdiği için elle kopyalanır).
    function snapshotClone(value, depth) {
        const d = depth || 0;
        if (d > DIFF_MAX_DEPTH) return null;
        if (Array.isArray(value)) {
            return value.map(function (v) { return snapshotClone(v, d + 1); });
        }
        if (isPlainObject(value)) {
            const out = {};
            Object.keys(value).forEach(function (k) {
                out[k] = snapshotClone(value[k], d + 1);
            });
            return out;
        }
        return value;
    }

    let prevSnapshot = null;      // bir önceki sonucun kopyası
    let lastDiff = null;          // son hesaplanan fark (dil değişiminde yeniden çizilir)

    function renderDiffBand() {
        const band = document.getElementById('ad_diff_band');
        if (!band) return;
        if (!lastDiff) { band.style.display = 'none'; return; }
        band.innerHTML = diffStripHtml(lastDiff);
        band.style.display = 'block';
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(band);
    }

    // Yeni sonuç geldiğinde çağrılır (refreshSuggestions üzerinden — entegrasyon
    // katmanı zaten her hesap sonrası onu çağırıyor, yeni kapı açmaya gerek yok).
    function noteResults(results) {
        if (!isPlainObject(results)) return null;
        lastDiff = diffCompute(prevSnapshot, results);
        prevSnapshot = snapshotClone(results, 0);
        renderDiffBand();
        return lastDiff;
    }

    // ==================================================================
    // ÇÖZÜCÜ SONUCU OKUMA — merkezi birim çözümlemesi (v2.6.26)
    // ------------------------------------------------------------------
    // Neden burada: hesap uçlarının sözlüğünde uzunluk birimleri TÜRDEŞ
    // DEĞİL ve tutarsızlık motor tipine göre değişiyor. Her panel kendi
    // başına tahmin ettiği sürece aynı hata yeniden üretiliyor: termal
    // panel 1000'e BÖLÜYOR, vessel/joint panelleri 1000 ile ÇARPIYOR ve
    // ikisi de yalnız TEK bir motor tipinde doğru çıkıyordu.
    //
    // Aşağıdaki tablo 2026-07-30'da ÖLÇÜLDÜ (examples/ altındaki üç gerçek
    // örnek proje ilgili hesap ucundan geçirilip yanıt okundu; tahmin yok):
    //
    //   anahtar             hibrit      katı           sıvı
    //   chamber_diameter    0.1200 m    75.0 mm        120.0 mm
    //   chamber_length      1.0032 m    (anahtar yok)  249.52 mm
    //   throat_diameter     0.0297 m    17.96 mm       0.0547 m
    //   exit_diameter       0.0677 m    46.47 mm       0.1896 m
    //
    // Katı ve sıvı yanıtlarında ayrıca TAMAMEN SI birimli bir
    // `motor_geometry` bloğu var (katı: chamber_length 0.46 m — üstteki
    // düz sözlükte bu anahtar hiç yok). Bu blok varsa ÖNCE o okunur;
    // yoksa yukarıdaki ölçülmüş birim tablosuna düşülür. Anahtar hiçbir
    // yerde yoksa `undefined` döner — panel varsayılanı UYDURULMAZ.
    // ==================================================================

    // Çözücü yanıtının motor sözlüğü: hibrit yanıtı `.motor` altında
    // iç içedir, katı ve sıvı yanıtları düzdür.
    function motorDict(r) {
        return (r && r.motor) || r || {};
    }

    // 'a.b.c' yolunu güvenli okur; ara düğüm yoksa undefined.
    function deepGet(obj, path) {
        var cur = obj;
        var parts = String(path).split('.');
        for (var i = 0; i < parts.length; i++) {
            if (cur == null || typeof cur !== 'object') return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    // İlk sonlu sayıyı veren yolu döndürür (yol listesi sırayla denenir).
    function firstNumber(obj, paths) {
        for (var i = 0; i < paths.length; i++) {
            var v = deepGet(obj, paths[i]);
            if (typeof v === 'number' && Number.isFinite(v)) return v;
        }
        return undefined;
    }

    // İlk boş olmayan string'i veren yolu döndürür.
    function firstString(obj, paths) {
        for (var i = 0; i < paths.length; i++) {
            var v = deepGet(obj, paths[i]);
            if (typeof v === 'string' && v !== '') return v;
        }
        return undefined;
    }

    // Düz sözlükteki uzunluk anahtarlarının ÖLÇÜLMÜŞ birimi (yukarıdaki
    // tablo). Burada olmayan anahtar için tahmin yürütülmez.
    const LENGTH_UNITS = {
        hybrid: {
            chamber_diameter: 'm', chamber_length: 'm',
            throat_diameter: 'm', exit_diameter: 'm', grain_length: 'm',
            port_diameter_initial: 'm', port_diameter_final: 'm',
        },
        solid: {
            chamber_diameter: 'mm', throat_diameter: 'mm',
            exit_diameter: 'mm', grain_length: 'mm',
            core_diameter: 'mm',
        },
        liquid: {
            chamber_diameter: 'mm', chamber_length: 'mm',
            throat_diameter: 'm', exit_diameter: 'm',
        },
    };

    // Uzunluk okuma — METRE döner. Bilinmeyen anahtar/motor -> undefined.
    function readLengthM(r, key) {
        const m = motorDict(r);
        const g = m.motor_geometry;
        if (g && typeof g === 'object'
                && typeof g[key] === 'number' && Number.isFinite(g[key])) {
            return g[key];              // motor_geometry bloğu SI (ölçüldü)
        }
        const unit = (LENGTH_UNITS[getMotorType()] || {})[key];
        const v = m[key];
        if (!unit || typeof v !== 'number' || !Number.isFinite(v)) return undefined;
        return unit === 'mm' ? v / 1000 : v;
    }

    // Uzunluk okuma — MİLİMETRE döner (mm etiketli alanlar için).
    function readLengthMM(r, key) {
        const v = readLengthM(r, key);
        return (typeof v === 'number' && Number.isFinite(v)) ? v * 1000 : undefined;
    }

    // --- Motor tipine göre ÖLÇÜLMÜŞ anahtar yolları -------------------
    // (2026-07-30, examples/ üç örnek projesinin gerçek yanıtından)

    const THRUST_PATHS = {
        // Katı motorda düz sözlükte 'thrust' YOK; çözücü ortalama ve tepe
        // itkiyi ayrı raporluyor. motor_geometry.thrust ortalamaya eşit.
        hybrid: ['thrust'],
        solid: ['motor_geometry.thrust', 'average_thrust'],
        liquid: ['thrust'],
    };

    const MASS_FLOW_PATHS = {
        hybrid: ['mdot_total'],
        solid: [],                        // aşağıda ortalamadan türetilir
        liquid: ['total_mass_flow'],
    };

    const PROPELLANT_MASS_PATHS = {
        hybrid: ['propellant_mass_total'],
        solid: ['propellant_mass', 'motor_geometry.propellant_mass_total'],
        liquid: ['design_summary.masses.propellant_mass_kg'],
    };

    const FUEL_FLOW_PATHS = {
        hybrid: ['mdot_f'],               // 'mdot_fuel' DEĞİL (ölçüldü)
        solid: [],                        // katı motorda ayrı yakıt akışı yok
        liquid: ['fuel_flow'],
    };

    const OF_RATIO_PATHS = {
        hybrid: ['of_ratio'],
        solid: [],                        // tek bileşenli itergaç: O/F yok
        liquid: ['mixture_ratio'],        // 'of_ratio' DEĞİL (ölçüldü)
    };

    // Kanonik hazne/gövde malzemesi anahtarı (materials_db adı).
    const CHAMBER_MATERIAL_PATHS = {
        hybrid: ['structural_analysis.design_parameters.material',
                 'heat_transfer_analysis.design_parameters.material'],
        solid: ['structural_analysis.case_analysis.case_material',
                'design_summary.case_design.material'],
        liquid: ['structural_analysis.chamber_structure.material_key'],
    };

    // Cidar kalınlığı — kaynakların HEPSİ MİLİMETRE (ölçüldü; hibritte
    // heat_transfer_analysis.py:722 `wall_thickness * 1000  # mm`).
    const WALL_THICKNESS_MM_PATHS = {
        hybrid: ['heat_transfer_analysis.design_parameters.wall_thickness'],
        solid: ['structural_analysis.case_analysis.wall_thickness_mm',
                'design_summary.key_dimensions.wall_thickness_mm'],
        liquid: ['structural_analysis.chamber_structure.wall_thickness'],
    };

    function readThrust(r) {
        return firstNumber(motorDict(r), THRUST_PATHS[getMotorType()] || []);
    }

    function readBurnTime(r) {
        return firstNumber(motorDict(r), ['burn_time', 'motor_geometry.burn_time']);
    }

    // Toplam kütle debisi (kg/s). Katı motorda çözücü anlık debi
    // ÜRETMİYOR; itergaç kütlesi / yanma süresi ORTALAMASI döner
    // (uydurma değil, çözücünün kendi iki çıktısından türetilmiş
    // ortalama — anlık tepe debisi değildir).
    function readMassFlow(r) {
        const m = motorDict(r);
        const direct = firstNumber(m, MASS_FLOW_PATHS[getMotorType()] || []);
        if (direct !== undefined) return direct;
        const mass = readPropellantMass(r);
        const t = readBurnTime(r);
        if (typeof mass === 'number' && typeof t === 'number' && t > 0) {
            return mass / t;
        }
        return undefined;
    }

    function readPropellantMass(r) {
        return firstNumber(motorDict(r), PROPELLANT_MASS_PATHS[getMotorType()] || []);
    }

    function readFuelFlow(r) {
        return firstNumber(motorDict(r), FUEL_FLOW_PATHS[getMotorType()] || []);
    }

    function readOfRatio(r) {
        return firstNumber(motorDict(r), OF_RATIO_PATHS[getMotorType()] || []);
    }

    function readChamberMaterial(r) {
        return firstString(motorDict(r), CHAMBER_MATERIAL_PATHS[getMotorType()] || []);
    }

    // Cidar kalınlığı — METRE döner (m etiketli alanlar için).
    function readWallThicknessM(r) {
        const mm = firstNumber(motorDict(r),
                               WALL_THICKNESS_MM_PATHS[getMotorType()] || []);
        return mm === undefined ? undefined : mm / 1000;
    }

    // Cidar kalınlığı — MİLİMETRE döner.
    function readWallThicknessMM(r) {
        return firstNumber(motorDict(r), WALL_THICKNESS_MM_PATHS[getMotorType()] || []);
    }

    // ==================================================================
    // CİDARIN KÜNYESİ — "bu sayı kimin cidarı?"  (OH-Z4-05 / Z5-C1)
    // ------------------------------------------------------------------
    // ÖLÇÜLEN KUSUR (2026-08-27, app.test_client; kanıt:
    // docs/scofield/raw/OH/Z5/c/olcum_c1_once.txt): kullanıcı cidar alanını
    // BOŞ bırakıyor, /calculate cidarı KENDİ boyutlandırıyor
    // (design_mode: size · wall_thickness_source: sized_by_hrma ·
    // 15,903671 mm), panelin `fromResults`'ı o sayıyı cidar alanına
    // dolduruyor ve /analyze_structural_safety onu şöyle damgalıyor:
    //     wall_thickness_source : user_supplied
    //     is_verification       : true
    //     message               : "The supplied wall thickness was evaluated
    //                              against the design pressure; this result
    //                              is a verification."
    // Yani HRMA kendi cidarını "kullanıcının cidarı" diye DOĞRULUYORDU —
    // kendi kendini doğrulayan döngü. Ekranda hiçbir yerde bu yazmıyordu.
    //
    // ÇÖZÜM: cidar okuması artık ÇIPLAK SAYI değil, KÜNYELİ okumadır.
    // Künye tahmin edilmez, motorun KENDİ beyanından okunur. Üç motor
    // tipinde de ölçüldü (kanıt: olcum_c1_kunye_envanteri.txt):
    //
    //   motor    künye bloğu                                  design_mode
    //   hibrit   structural_analysis.chamber_analysis         size / verify
    //   katı     structural_analysis.case_analysis            size / verify
    //   sıvı     structural_analysis.chamber_structure        size / verify
    //
    // `design_mode` üç tipte de KANONİKTİR ('size' ⟷ 'verify');
    // `wall_thickness_source` metni tipe göre değişiyor (sıvıda serbest
    // cümle: "user input (chamber wall thickness)" / "next standard plate
    // thickness above the requirement"), bu yüzden ikincil kanıttır.
    // ==================================================================

    //: Cidar künyesinin yayımlandığı blok — cidar sayısının KENDİ bloğu.
    const WALL_PROVENANCE_PATHS = {
        hybrid: ['structural_analysis.chamber_analysis'],
        solid: ['structural_analysis.case_analysis',
                'design_summary.key_dimensions'],
        liquid: ['structural_analysis.chamber_structure'],
    };

    //: Künye sınıfları (panellerin karşılaştırdığı sabitler).
    const WALL_PROV_USER = 'user_supplied';   // kullanıcının cidarı sınandı
    const WALL_PROV_SOLVER = 'solver_sized';  // HRMA kendi cidarını üretti
    const WALL_PROV_UNDECLARED = 'undeclared';  // beyan YOK -> iddia YOK

    //: `wall_thickness_source` metninde kullanıcıyı gösteren imler (ölçüldü).
    const WALL_SOURCE_USER_MARKS = ['user_supplied', 'user input', 'user-supplied'];
    //: HRMA'nın kendi boyutlandırmasını gösteren imler (ölçüldü).
    const WALL_SOURCE_SIZED_MARKS = ['sized_by_hrma', 'standard plate',
                                     'auto', 'requirement'];

    function _wallProvenanceBlock(m) {
        const paths = WALL_PROVENANCE_PATHS[getMotorType()] || [];
        for (let i = 0; i < paths.length; i++) {
            const blk = deepGet(m, paths[i]);
            if (blk && typeof blk === 'object'
                    && (blk.design_mode !== undefined
                        || blk.wall_thickness_source !== undefined)) {
                return { block: blk, path: paths[i] };
            }
        }
        return null;
    }

    function _markHit(text, marks) {
        const low = String(text || '').toLowerCase();
        if (!low) return false;
        for (let i = 0; i < marks.length; i++) {
            if (low.indexOf(marks[i]) !== -1) return true;
        }
        return false;
    }

    // Cidar okuması + künyesi. Dönen sözlük:
    //   source     : 'user_supplied' | 'solver_sized' | 'undeclared'
    //   value_m    : metre cinsinden cidar (yoksa undefined)
    //   value_mm   : milimetre cinsinden cidar (yoksa undefined)
    //   designMode : motorun kendi `design_mode` beyanı (yoksa null)
    //   declared   : motorun kendi `wall_thickness_source` metni (yoksa null)
    //   blockPath  : künyenin okunduğu MAKİNE YOLU (ekranda ipucu olur)
    // Beyan hiç yoksa 'undeclared' döner ve HİÇBİR ŞEY İDDİA EDİLMEZ —
    // "kullanıcının cidarı" iddiası ancak motor bunu KENDİ söylerse doğar.
    function readWallThicknessProvenance(r) {
        const m = motorDict(r);
        const mm = firstNumber(m, WALL_THICKNESS_MM_PATHS[getMotorType()] || []);
        const found = _wallProvenanceBlock(m);
        const blk = found ? found.block : {};
        const mode = (blk.design_mode == null) ? null : String(blk.design_mode);
        const decl = (blk.wall_thickness_source == null)
            ? null : String(blk.wall_thickness_source);
        let source = WALL_PROV_UNDECLARED;
        if (mode === 'verify' || (mode === null && _markHit(decl, WALL_SOURCE_USER_MARKS))) {
            source = WALL_PROV_USER;
        } else if (mode === 'size'
                || (mode === null && _markHit(decl, WALL_SOURCE_SIZED_MARKS))) {
            source = WALL_PROV_SOLVER;
        }
        // İki beyan ÇELİŞİYORSA iddia geri çekilir (fail-closed): 'verify'
        // diyen bir modun kaynağı "sized_by_hrma" olamaz.
        if (source === WALL_PROV_USER && _markHit(decl, ['sized_by_hrma'])) {
            source = WALL_PROV_UNDECLARED;
        }
        return {
            source: source,
            value_m: (mm === undefined) ? undefined : mm / 1000,
            value_mm: mm,
            designMode: mode,
            declared: decl,
            blockPath: found ? found.path : null,
        };
    }

    // ------------------------------------------------------------------
    // ÖNERİ GERİ ÇEKME (`__withheld`) — panelin BİLEREK doldurmadığı alan
    // ------------------------------------------------------------------
    // `fromResults` sözlüğüne `__withheld: {alanAdı: 'gerekçe'}` koyabilir.
    // O alanın DEĞERİ yine normal bir sayıdır (panelin "sen boyutlandır"
    // nöbetçisi), yani öneri sözlüğünün TİPİ değişmez — sayı bekleyen her
    // tüketici çalışmaya devam eder. Değişen tek şey KÜNYEdir: alan
    // "hesaptan geldi" (computed) diye imlenmez, kaynak çipinin ipucuna
    // gerekçe makine diliyle iliştirilir.
    //
    // Nöbetçi değerin AÇIKÇA yazılması şart: eski davranışta `undefined`
    // dönünce alan olduğu gibi kalıyordu, yani bir ÖNCEKİ koşumdan kalan
    // bayat öneri sessizce uca gidiyordu.
    //
    // Kullanıcının ELLE yazdığı alan bundan ETKİLENMEZ: `data-dirty` kapısı
    // applySuggestions'ın en başındadır, yani gerçek kullanıcı girdisi
    // korunur ve uç onu doğrular.
    const WITHHELD_KEY = '__withheld';

    // ==================================================================
    // CİDAR SICAKLIĞI  (F5-2, 2026-08-17 ölçümü)
    // ------------------------------------------------------------------
    // `/analyze_structural_safety` iki anahtarı BİRİNCİ ÖNCELİKLE okuyor
    // (app.py: `for wall_key in ('wall_temperature_hot',
    // 'wall_temperature_cold')`), yapısal modül de onları
    // `_estimate_wall_delta_T` içinde 1. sırada kullanıyor. Güverte paneli
    // ikisini de HİÇ göndermiyordu, yani ısı zincirinin çözdüğü cidar
    // sıcaklığı güverteye ulaşmıyor, panel gaz sıcaklığından türetilen
    // TAHMİN yolunu tetikliyordu. ÖLÇÜLDÜ (örnek hibrit motor, aynı koşu):
    //
    //   güverte (bugün, cidar sıcaklığı gönderilmiyor)
    //       T_iç = 729,9 K  ·  SF_min = 4,000  ·  durum MARGINAL
    //   motorun kendi zinciri (ısı modülünün çözdüğü cidar)
    //       T_iç = 3369,3 K ·  SF_min = 2,134
    //
    // Yani aynı motor için ekranda 4,6 kat düşük bir cidar sıcaklığı ve
    // ondan türeyen bir emniyet katsayısı duruyordu.
    //
    // SAHTE VERİ KAPISI: her sıcaklık gönderilmez. Çözücü bu iki sayının
    // NEREDEN geldiğini kendisi beyan ediyor; panel yalnız GERÇEKTEN
    // çözülmüş (ya da kullanıcının verdiği) değeri taşır:
    //
    //   hibrit/katı  structural_analysis.thermal_analysis.
    //                wall_temperature_source == 'heat_transfer_module'
    //                (diğer iki değer — 'chamber_temperature_estimate' ve
    //                'not_evaluated' — zaten tahmin/kapalı demektir; onları
    //                geri beslemek tahmini ölçüm gibi göstermek olurdu)
    //   sıvı         cooling_system.wall_temperature_source
    //                'assumed (cooling-type default)' İSE GÖNDERİLMEZ
    //                (ölçüldü: örnek sıvı motorda kaynak tam bu, değerler
    //                800,0 / 350,0 K yuvarlak tasarım varsayımları)
    //
    // İkisi de bulunamazsa `{}` döner: alanlar BOŞ kalır, uç kendi
    // beyanlı tahmin yoluna girer ve panel bunu ekranda söyler.
    // ==================================================================

    //: Çözülmüş sayılmayan kaynak beyanları (bunlar geri beslenmez).
    const WALL_TEMP_SOURCE_NOT_SOLVED = ['not_evaluated',
                                         'chamber_temperature_estimate'];

    //: Motor tipine göre ÖLÇÜLMÜŞ cidar sıcaklığı yolları + kaynak beyanı.
    const WALL_TEMPERATURE_K_PATHS = {
        hybrid: {
            hot: 'structural_analysis.thermal_analysis.wall_temperature_inner_K',
            cold: 'structural_analysis.thermal_analysis.wall_temperature_outer_K',
            source: 'structural_analysis.thermal_analysis.wall_temperature_source',
        },
        // Katı zincir bugün cidar sıcaklığı YAYIMLAMIYOR (ölçüldü:
        // structural_analysis = {assembly_integrity, case_analysis,
        // grain_structural}). Yol yine de hibritle aynı adreste tanımlıdır:
        // katı zincir bir gün yayımlarsa panel kendiliğinden taşır, ama
        // yayımlamadığı sürece hiçbir sayı UYDURULMAZ.
        solid: {
            hot: 'structural_analysis.thermal_analysis.wall_temperature_inner_K',
            cold: 'structural_analysis.thermal_analysis.wall_temperature_outer_K',
            source: 'structural_analysis.thermal_analysis.wall_temperature_source',
        },
        liquid: {
            hot: 'cooling_system.wall_temperature_hot',
            cold: 'cooling_system.wall_temperature_cold',
            source: 'cooling_system.wall_temperature_source',
        },
    };

    // Çözücünün kaynak beyanı "çözüldü/kullanıcı verdi" mi diyor?
    function wallTempSourceIsSolved(source) {
        if (typeof source !== 'string' || source === '') return false;
        if (WALL_TEMP_SOURCE_NOT_SOLVED.indexOf(source) !== -1) return false;
        // Sıvı tarafı serbest metin kullanıyor; 'assumed ...' ile başlayan
        // her beyan VARSAYIMDIR ('solved ...' ve 'user input ...' değildir).
        return !/^assumed\b/i.test(source);
    }

    // {hot, cold} (K) döner; beyan çözülmüş demiyorsa ya da ikisinden biri
    // eksikse BOŞ sözlük döner (yarım çift gönderilmez: yapısal modül iki
    // sayıyı birlikte ister, tek başına gelen sıcaklık tahmin yolunu açar
    // ama ucun 'termal koştu' bayrağını da kaldırırdı).
    function readWallTemperaturesK(r) {
        const spec = WALL_TEMPERATURE_K_PATHS[getMotorType()];
        if (!spec) return {};
        const m = motorDict(r);
        if (!wallTempSourceIsSolved(deepGet(m, spec.source))) return {};
        const hot = firstNumber(m, [spec.hot]);
        const cold = firstNumber(m, [spec.cold]);
        if (hot === undefined || cold === undefined) return {};
        return { hot: hot, cold: cold };
    }

    // ------------------------------------------------------------------
    // DOM yardımcıları
    // ------------------------------------------------------------------
    function fieldDomId(panelId, fieldId) {
        return 'ad_f_' + panelId + '_' + fieldId;
    }

    // Alan tanımı: [id, etiket, varsayılan, adım, etiketAnahtarı?]
    // 5. eleman verilirse etiket data-i18n taşır; dil değişince kendiliğinden çevrilir.
    // Seçenek listesi öğeleri de [değer, etiket, etiketAnahtarı?] olabilir.
    // Alanın kaynak çipi kabı (E3) — içeriği applySuggestions doldurur.
    function fieldSourceSlotId(panelId, fieldId) {
        return 'ad_src_' + panelId + '_' + fieldId;
    }

    function fieldHtml(panelId, f) {
        const fid = f[0], label = f[1], defVal = f[2], step = f[3], labelKey = f[4];
        const domId = fieldDomId(panelId, fid);
        // Etiket ve kaynak çipi TEK satırda dursun diye küçük bir başlık
        // satırı: şablonlarda `.form-group label` display:block, çip
        // sarmalayıcısız alt satıra düşerdi.
        const lab = `<div class="ad-field-head"><label${i18nAttr(labelKey)}>${
            T(labelKey, label)}</label><span class="ad-src-slot"
            id="${fieldSourceSlotId(panelId, fid)}"></span></div>`;
        if (Array.isArray(step)) {
            // step bir seçenek listesi: [[value, label, labelKey?], ...] → <select>
            const opts = step.map(o =>
                `<option value="${o[0]}"${o[0] === defVal ? ' selected' : ''}${i18nAttr(o[2])}>${T(o[2], o[1])}</option>`).join('');
            // ÖH D35 · OH-GT-31 — SEÇİLİ SEÇENEĞİN TAM METNİ `title`DA.
            // ÖLÇÜLDÜ (a1/once.json M1_secici_kesik): hücre ızgarası
            // `minmax(170px, 1fr)` idi, sığan metin ~20 karakter, güverte
            // ve merkez seçeneklerinin 64'ü (70 anahtarın) bunu aşıyordu
            // ("Ters yönlü (çıkıştan odaya)" = 27, "Counterflow (exit →
            // chamber)" = 28). Ekranda metin ORTASINDAN kesiliyordu ve
            // `title` YOKTU (`fieldHtml_select_title_var_mi = false`),
            // yani kullanıcının seçtiği şeyi okumasının hiçbir yolu yoktu.
            // Izgara asgarisi 210 px'e çıktı (aşağıda) ve kırpılan metin
            // artık üç noktayla biter (theme.css); TAM metin ipucundadır.
            // İpucu kurulumda basılır, seçim değişince ve dil değişince
            // `secimIpucu` ile tazelenir — üçü de ÖLÇÜLÜR (bekçi).
            const secili = step.filter(o => o[0] === defVal)[0]
                || (step.length ? step[0] : null);
            const ipucu = secili ? escAttr(T(secili[2], secili[1])) : '';
            // DV36-06: ipucu seçenekle aynı anahtardan çevrilir (secimIpucu).
            const ipucuAnahtari = (secili && secili[2])
                ? ' data-i18n-title="' + escAttr(secili[2]) + '"' : '';
            return `<div class="form-group">${lab}
                <select id="${domId}" data-field="${fid}" title="${ipucu}"${ipucuAnahtari}>${opts}</select></div>`;
        }
        return `<div class="form-group">${lab}
            <input type="number" id="${domId}" data-field="${fid}" value="${defVal}" step="${step}"></div>`;
    }

    // ÖH D35 · OH-GT-31 — seçili seçeneğin TAM metnini `title`a yazar.
    // Fail-closed: seçili seçenek yoksa ipucu SİLİNİR (eski, artık yanlış
    // metin ekranda kalmaz); uydurma metin yazılmaz.
    // ÖH D37 A1a · DV36-06 — İPUCU SEÇİLİ SEÇENEĞİN ANAHTARINI DA TAŞIR.
    // ÖLÇÜLDÜ (a1/once/tarayici.json, 1440 px, örnek proje + hesap): sıvı
    // sayfasında TR kipte 6 termal seçicinin 5'inin ipucu İngilizceydi
    // ('Ablative liner — Q* sizing' ⟷ görünen 'Ablatif astar — …'). Kök:
    // sözlük (i18n_common.js) bu sayfada güverte tarafından SONRADAN
    // yükleniyor; güverte kurulurken `T()` İngilizce yedeği döndürüyor,
    // sözlük gelince `I18N.apply` seçenek metnini (`data-i18n`) çeviriyor
    // ama `title` onun kanalında değildi. Artık seçili seçeneğin anahtarı
    // `data-i18n-title` olarak da yazılır: sözlük hangi sırada gelirse
    // gelsin, seçenek metni ile ipucu AYNI geçişte çevrilir. Anahtarsız
    // seçenekte (katalogdan gelen ad) nitelik SİLİNİR — eski anahtar,
    // görünen metinden başka bir şey yazdırmasın.
    function secimIpucu(el) {
        if (!el || el.tagName !== 'SELECT') return;
        const o = el.options ? el.options[el.selectedIndex] : null;
        const metin = (o && typeof o.textContent === 'string') ? o.textContent.trim() : '';
        const anahtar = (o && o.getAttribute) ? o.getAttribute('data-i18n') : null;
        if (anahtar) el.setAttribute('data-i18n-title', anahtar);
        else el.removeAttribute('data-i18n-title');
        if (metin) el.setAttribute('title', metin);
        else el.removeAttribute('title');
    }

    // Bölümdeki (ya da verilen kökteki) bütün seçicilerin ipucunu tazeler.
    // Dil değiştiğinde `I18N.applyTo` seçenek METİNLERİNİ çevirir ama
    // `title` niteliği onun kanalında değildir — eski dilde kalırdı.
    function secimIpuclariniTazele(kok) {
        const host = kok || document;
        if (!host.querySelectorAll) return;
        host.querySelectorAll('select[data-field]').forEach(secimIpucu);
    }

    function panelSectionHtml(spec) {
        const fieldsHtml = (spec.fields || []).map(f => fieldHtml(spec.id, f)).join('');
        return `
        <div id="ad_sec_${spec.id}" style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
             border-radius:var(--hd-radius-sm, 8px); padding:12px 16px; margin:12px 0;">
            <h3 style="margin:0 0 8px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;">
                <span${i18nAttr(spec.titleKey)}>${T(spec.titleKey, spec.title)}</span>
                <span style="font-family:var(--hd-mono); font-size:0.68rem;
                      color:var(--hd-ink-faint, #6a8491);">${spec.endpoint || ''}</span>
            </h3>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
                 gap:10px; margin:10px 0;">
                ${fieldsHtml}
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="ad_run_${spec.id}"
                        data-i18n="common.runAnalysis">${T('common.runAnalysis', 'Run Analysis')}</button>
                </div>
            </div>
            <div id="ad_status_${spec.id}" style="font-family:var(--hd-mono);
                 color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <div id="ad_root_${spec.id}" style="display:none;"></div>
        </div>`;
    }

    // ------------------------------------------------------------------
    // ÖH D34 · OH-GT-13 — SEÇİLİ SEKME YALNIZ RENKLE ANLATILIYORDU
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (a1/once.json): şeritteki `.ad-tab` düğmelerinde
    // `role="tab"` yok, `aria-selected` yok, şeritte `role="tablist"` yok;
    // `selectCategory` yalnız `background`, `color` ve `borderColor`
    // yazıyordu — `renk_disi_eksen_sayisi` = 0. Yani hangi bölmenin açık
    // olduğu SADECE renkten okunuyordu: renk ayrımı zayıf kullanıcı için
    // bilgi yok (WCAG 1.4.1), ekran okuyucu için ise durum hiç yok —
    // düğmeler sıradan düğme olarak, seçilmişlik bildirimi olmadan
    // okunuyordu.
    //
    // İki ayrı eksen eklendi:
    //   1. ANLAM: tablist/tab/tabpanel + `aria-selected` + `aria-controls`.
    //   2. BİÇİM: seçilide 2 px alt çizgi ve 600 ağırlık. Alt çizginin YERİ
    //      her zaman ayrılır (`border-bottom: 2px solid transparent`), yoksa
    //      seçim değişince şerit 2 px zıplar.
    // Roving tabindex: ok tuşları eklendiği için ARIA deseni bunu ister —
    // şeritte Tab ile TEK durak olur, sekmeler arasında ok tuşuyla gezilir.
    function tabButtonHtml(cat) {
        const key = 'dock.cat.' + cat;
        return `<button type="button" class="ad-tab" data-category="${cat}"
            role="tab" id="ad_tab_${cat}" aria-controls="ad_pane_${cat}"
            aria-selected="false" tabindex="-1"
            style="font-family:var(--hd-mono); font-size:0.78rem; letter-spacing:0.08em;
            padding:7px 16px; cursor:pointer; border-radius:6px 6px 0 0;
            border:1px solid var(--hd-line, rgba(0,229,255,0.14));
            border-bottom:2px solid transparent; font-weight:400;
            background:transparent; color:var(--hd-ink-dim, #7d97a5);"
            data-i18n="${key}">${T(key, cat)}</button>`;
    }

    /** Şeritte ok tuşuyla gezinme (ARIA tab deseni). */
    function tabKeyNav(ev) {
        const yon = { ArrowRight: 1, ArrowLeft: -1, Home: 0, End: -0 };
        if (!(ev.key in yon)) return;
        const hepsi = Array.prototype.slice.call(
            document.querySelectorAll('#ad_tabs .ad-tab'));
        if (hepsi.length < 2) return;
        const simdi = hepsi.indexOf(ev.currentTarget);
        let hedef;
        if (ev.key === 'Home') hedef = 0;
        else if (ev.key === 'End') hedef = hepsi.length - 1;
        else hedef = (simdi + yon[ev.key] + hepsi.length) % hepsi.length;
        ev.preventDefault();
        const dugme = hepsi[hedef];
        selectCategory(dugme.getAttribute('data-category'));
        dugme.focus();
    }

    function dockHtml() {
        return `
        <div class="panel" id="analysisDock" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="dock.title">${T('dock.title', 'Analysis Dock')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatItDoes">${T('common.whatItDoes', 'What it does:')}</strong>
                <span data-i18n="dock.intro">${T('dock.intro',
                    'Runs detailed engineering analyses (thermal, structural, safety) '
                    + 'on the current motor design. Inputs are pre-filled from the latest '
                    + 'calculation results — you can override any value before running. '
                    + 'The request is always built from the form fields shown.')}</span>
            </div>
            <div id="ad_toolbar" style="display:flex; gap:14px; align-items:center;
                 flex-wrap:wrap; margin:12px 0 0; font-family:var(--hd-mono, monospace);
                 font-size:0.7rem;">
                <span style="color:var(--hd-ink-dim, #7d97a5); letter-spacing:0.08em;"
                    data-i18n="dock.layout.label">${T('dock.layout.label', 'LAYOUT')}</span>
                ${layoutButtonHtml('tabs', 'dock.layout.tabs', 'Tabs')}
                ${layoutButtonHtml('grid', 'dock.layout.grid', 'Grid')}
                <span id="ad_src_legend" style="display:none;"></span>
            </div>
            <div id="ad_diff_band" style="display:none; margin:10px 0 0; padding:8px 12px;
                 border:1px solid var(--hd-line, rgba(0,229,255,0.14));
                 border-radius:var(--hd-radius-sm, 8px);
                 background:var(--hd-inset, rgba(6,14,26,0.85));
                 font-family:var(--hd-mono, monospace); font-size:0.72rem;
                 color:var(--hd-ink, #cfe8f2); overflow-x:auto;
                 overflow-wrap:anywhere;"></div>
            <div id="ad_tabs" role="tablist"
                 aria-label="${T('dock.tabs.label', 'Analysis categories')}"
                 style="display:flex; gap:6px; margin:14px 0 0; flex-wrap:wrap;"></div>
            <div id="ad_panes" style="border-top:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));"></div>
        </div>`;
    }

    // ==================================================================
    // E1 — SEKME / IZGARA YERLEŞİMİ
    // ------------------------------------------------------------------
    // Güvertede 14 panel var ve hepsi kategori sekmelerinin ARKASINDA:
    // kullanıcı aynı anda yalnız bir kategoriyi görebiliyordu. Izgara
    // kipinde bütün kategoriler tek akışta yan yana dizilir (CSS grid,
    // `auto-fit` — sütun sayısı pencere genişliğinden gelir).
    //
    // GERİ DÜŞÜŞ SÖZLEŞMESİ: tercih okunamazsa (localStorage yok, gizli
    // kip, bozuk değer) kip 'tabs'tır — yani bugünkü davranış. Izgara
    // kipi sekme mekaniğini SÖKMEZ: sekme düğmeleri durur, tıklanınca
    // ilgili bölüme kaydırır; kip 'tabs'a dönünce eski görünüm birebir
    // geri gelir.
    // ==================================================================
    const LAYOUT_KEY = 'hrma.dock.layout';
    const LAYOUTS = ['tabs', 'grid'];
    const LAYOUT_FALLBACK = 'tabs';
    let layoutMode = null;          // ilk okumada tembel doldurulur

    function layoutStore() {
        try { return window.localStorage || null; } catch (e) { return null; }
    }

    function readLayoutPref() {
        const store = layoutStore();
        if (!store) return LAYOUT_FALLBACK;
        let raw = null;
        try { raw = store.getItem(LAYOUT_KEY); } catch (e) { return LAYOUT_FALLBACK; }
        return (LAYOUTS.indexOf(raw) === -1) ? LAYOUT_FALLBACK : raw;
    }

    function writeLayoutPref(mode) {
        const store = layoutStore();
        if (!store) return false;
        try { store.setItem(LAYOUT_KEY, mode); return true; } catch (e) { return false; }
    }

    // classList taklidi eksik olabilen ortamlara (test koşum düzenekleri)
    // dayanıklı sınıf yardımcıları
    function addClass(el, name) {
        if (el && el.classList && typeof el.classList.add === 'function') el.classList.add(name);
    }
    function removeClass(el, name) {
        if (el && el.classList && typeof el.classList.remove === 'function') {
            el.classList.remove(name);
        }
    }

    function getLayout() {
        if (layoutMode === null) layoutMode = readLayoutPref();
        return layoutMode;
    }

    function layoutButtonHtml(mode, key, fallback) {
        return `<button type="button" class="ad-layout-btn" data-layout="${mode}"
            style="font-family:var(--hd-mono, monospace); font-size:0.7rem;
            letter-spacing:0.06em; padding:3px 12px; cursor:pointer; border-radius:6px;
            border:1px solid var(--hd-line, rgba(0,229,255,0.14));
            background:transparent; color:var(--hd-ink-dim, #7d97a5);"
            data-i18n="${key}">${T(key, fallback)}</button>`;
    }

    function paintLayoutButtons() {
        const mode = getLayout();
        const btns = document.querySelectorAll
            ? document.querySelectorAll('#ad_toolbar .ad-layout-btn') : [];
        Array.prototype.forEach.call(btns || [], function (b) {
            const on = b.getAttribute('data-layout') === mode;
            b.style.background = on ? 'rgba(0, 229, 255, 0.10)' : 'transparent';
            b.style.color = on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)';
            b.style.borderColor = on ? 'var(--hd-line-strong, rgba(0,229,255,0.42))'
                                     : 'var(--hd-line, rgba(0,229,255,0.14))';
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    // Kip ne olursa olsun panelleri görünür kılan tek yer burasıdır.
    function applyLayout() {
        const panes = document.getElementById('ad_panes');
        const mode = getLayout();
        paintLayoutButtons();
        if (!panes) return mode;
        if (mode === 'grid') {
            addClass(panes, 'ad-layout-grid');
            // `display:contents` bölüm kutularını doğrudan ızgara hücresi
            // yapar; kategori sarmalayıcısı yerleşimi bölmez.
            Array.prototype.forEach.call(panes.children || [], function (p) {
                p.style.display = 'contents';
            });
        } else {
            removeClass(panes, 'ad-layout-grid');
            Array.prototype.forEach.call(panes.children || [], function (p) {
                p.style.display = (p.id === 'ad_pane_' + activeCategory) ? 'block' : 'none';
            });
        }
        resizeVisiblePlots();
        return mode;
    }

    function setLayout(mode) {
        const next = (LAYOUTS.indexOf(mode) === -1) ? LAYOUT_FALLBACK : mode;
        layoutMode = next;
        writeLayoutPref(next);      // yazılamazsa (gizli kip) kip yine uygulanır
        return applyLayout();
    }

    // Gizli sekmedeyken çizilen Plotly grafikleri 700 px varsayılanında
    // kalır; görünür olunca gerçek genişliğe getirilir.
    // YALNIZ GÖRÜNÜR bölmeler taranır: plotly.js 1.58.5'te
    // `Plots.resize()` görüntülenmeyen bir div için sözü REDDEDER
    // ("Resize must be passed a displayed plot div element") — gizli
    // bölmeyi de taramak konsolu yakalanmamış red uyarısıyla doldururdu.
    function resizeVisiblePlots() {
        if (!window.Plotly || typeof Plotly.Plots === 'undefined') return;
        const host = document.getElementById('ad_panes');
        if (!host || !host.children) return;
        Array.prototype.forEach.call(host.children, function (pane) {
            if (!pane || !pane.querySelectorAll) return;
            if (pane.style && pane.style.display === 'none') return;
            Array.prototype.forEach.call(pane.querySelectorAll('.js-plotly-plot'),
                function (p) {
                    try {
                        const done = Plotly.Plots.resize(p);
                        if (done && typeof done.catch === 'function') {
                            done.catch(function () { /* bölme henüz ölçülemiyor */ });
                        }
                    } catch (e) { /* boş bölme */ }
                });
        });
    }

    // ------------------------------------------------------------------
    // Kategori sekmeleri
    // ------------------------------------------------------------------
    function ensureCategory(cat) {
        const tabs = document.getElementById('ad_tabs');
        const panes = document.getElementById('ad_panes');
        if (!tabs || !panes) return null;
        let pane = document.getElementById('ad_pane_' + cat);
        if (pane) return pane;

        const holder = document.createElement('div');
        holder.innerHTML = tabButtonHtml(cat);
        const btn = holder.firstElementChild;
        btn.addEventListener('click', function () { selectCategory(cat); });
        btn.addEventListener('keydown', tabKeyNav);   // OH-GT-13
        tabs.appendChild(btn);

        pane = document.createElement('div');
        pane.id = 'ad_pane_' + cat;
        pane.setAttribute('role', 'tabpanel');              // OH-GT-13
        pane.setAttribute('aria-labelledby', 'ad_tab_' + cat);
        pane.setAttribute('tabindex', '0');
        pane.style.display = 'none';
        pane.innerHTML = `<p class="ad-empty" data-i18n="dock.empty"
            style="color:var(--hd-ink-dim, #7d97a5);
            font-family:var(--hd-mono); font-size:0.8rem; margin:12px 0;">${
            T('dock.empty', 'No analyses registered in this category yet.')}</p>`;
        panes.appendChild(pane);
        // Kurulumdan SONRA kaydedilen paneller yeni kategori açabilir; yeni
        // bölme yürürlükteki yerleşime uydurulur (ızgara kipinde gizli kalmaz).
        applyLayout();
        return pane;
    }

    function selectCategory(cat) {
        activeCategory = cat;
        const tabs = document.querySelectorAll('#ad_tabs .ad-tab');
        tabs.forEach(function (b) {
            const on = b.getAttribute('data-category') === cat;
            b.style.background = on ? 'rgba(0, 229, 255, 0.10)' : 'transparent';
            b.style.color = on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)';
            b.style.borderColor = on ? 'var(--hd-line-strong, rgba(0,229,255,0.42))'
                                     : 'var(--hd-line, rgba(0,229,255,0.14))';
            // OH-GT-13 — renkten BAĞIMSIZ iki eksen. `borderColor`
            // kısa yazımı alt kenarı da boyadığı için alt çizgi ONDAN
            // SONRA yazılır, yoksa seçili alt çizgi silinir.
            b.style.borderBottomColor = on ? 'var(--hd-cyan, #00e5ff)'
                                           : 'transparent';
            b.style.fontWeight = on ? '600' : '400';
            b.setAttribute('aria-selected', on ? 'true' : 'false');
            b.setAttribute('tabindex', on ? '0' : '-1');
        });
        const panes = document.getElementById('ad_panes');
        if (!panes) return;
        // Görünürlük kararı TEK yerden verilir (E1): sekme kipinde yalnız
        // seçili kategori, ızgara kipinde hepsi görünür. Izgara kipinde
        // sekmeye tıklamak ilgili bölüme kaydırır.
        applyLayout();
        if (getLayout() === 'grid') {
            const target = document.getElementById('ad_pane_' + cat);
            if (target && typeof target.scrollIntoView === 'function') {
                try { target.scrollIntoView({ block: 'nearest' }); } catch (e) { /* eski motor */ }
            }
        }
    }

    // ==================================================================
    // ÖN DOLUM ANLAMLI BASAMAĞI  (Faz 6 / T66 + T45)
    // ------------------------------------------------------------------
    // Çözücünün döndürdüğü değer alana HAM basılıyordu. ÖLÇÜLDÜ
    // (2026-08-03, uygulama 8084):
    //   /solid   — 62 ad_f_* alanının 21'i altı ve fazlası ondalıklı:
    //              ad_f_joint_seal_diameter_mm      = 106.00000000000001
    //              ad_f_thermal_chamber_diameter    = 0.10600000000000001
    //              ad_f_structural_thrust           = 7521.506959698284
    //              ad_f_thermal_burn_time           = 1.7830261808052195
    //   /liquid  — 75 alanın 27'si:
    //              ad_f_thermal_chamber_temperature = 3707.0404366159974
    //              ad_f_cooling_throat_diameter     = 0.03081137601957565
    //              ad_f_cooling_gamma               = 1.1568199924202172
    //              ad_f_safety_propellant_mass      = 1665.7718758554495
    // İlk iki örnek saf kayan nokta artığıdır (106 ve 0,106'nın ikili
    // gösterimi), gerisi ise çözücünün taşıyamayacağı bir kesinlik vaadidir:
    // CEA denge sıcaklığının belirsizliği onlarca K, Bartz ısı akısınınki
    // ~%20, malzeme dayanım saçılması ~%5'tir.
    //
    // Burada YALNIZ görüntü değil GÖNDERİLEN sayı da değişir: alan bir
    // <input>, POST gövdesi formdan okunuyor. Dolayısıyla yuvarlamanın
    // hesaba etkisi ölçüldü — aynı ön dolum değerleri ham ve N anlamlı
    // basamağa yuvarlanmış hâlde üç uca gönderilip tüm sayısal çıktı
    // alanlarındaki en büyük bağıl fark alındı (thermal 100, structural 147,
    // safety 99 alan):
    //   12 basamak -> 5,8e-12    6 basamak -> 5,1e-06
    //    5 basamak -> 3,2e-05    4 basamak -> 1,0e-04    3 basamak -> 3,8e-03
    // 6 basamakta en kötü çıktı sapması %0,0005 — modellerin kendi
    // belirsizliğinin (%1 ve üstü) dört mertebe altında, yani mühendislik
    // anlamında kayıpsız. Alan artık okunabilir ve "ekranda görünen değer =
    // gönderilen değer" sözleşmesi de bozulmaz (görüntü-yalnız yuvarlama
    // bunu bozardı: 3707,04 gösterip 3707,0404366159974 göndermek olurdu).
    // ==================================================================
    const DOCK_SIGFIG = 6;

    // Büyüklükten bağımsız anlamlı basamak yuvarlaması: hem 3707,04 hem
    // 0,0308114 aynı kuralla kısalır (toFixed bunu yapamaz).
    function dockSigFig(value, digits) {
        const v = Number(value);
        if (!Number.isFinite(v) || v === 0) return v;
        return Number(v.toPrecision(digits || DOCK_SIGFIG));
    }

    // ==================================================================
    // ÖH D37 A1b sahte-veri-b · OH-D37-S4 — BAYAT ÖNERİ TEMİZLENİR
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/sahte-veri-b/a1/once/olcum.json,
    // senaryo S4_sivi_sureli_sonra_suresiz — gerçek güverte + dört panel,
    // node): süreli sıvı (250 s) → AYNI DOM'da süresiz sıvı → Çalıştır.
    // Güvenlik, termal, yapısal ve performans panelleri `burn_time: 250`,
    // güvenlik ayrıca `propellant_mass: 2297,08` gönderiyordu — ÖNCEKİ
    // koşunun değerleri; dört uç da 200 + tam hüküm döndü ve çip "hesap
    // sonucu değer taşımıyordu, kutuda panelin varsayılanı duruyor"
    // diyordu (kutuda varsayılan YOKTU). Kök: öneri yalnız sonlu sayıyı
    // yazıyor, alanı hiç temizlemiyordu; refreshSuggestions her hesaptan
    // sonra AYNI DOM'u tazeliyor.
    //
    // Kural (geçmişten bağımsızlık): kullanıcının dokunmadığı alanın
    // değeri = f(alan tanımı, ŞİMDİKİ sonuç). Son değeri ÖNERİDEN gelen
    // alan (`data-suggested`; `data-dirty` DEĞİL) her geçişin başında
    // TANIM varsayılanına döner ve şimdiki sonuç öneri veriyorsa yeniden
    // dolar — yani aynı sonuçla sıfırdan açılan sayfanın göreceği değer.
    // Varsayılanı boş dize olan alan (burn_time, propellant_mass, cidar
    // sıcaklığı çifti …) boşalır ve gövdeye GİRMEZ; uç kendi kuralını
    // adıyla uygular (422 missing_fields ya da adıyla geri çekme).
    // Kullanıcının elle yazdığı alan (`data-dirty`) EZİLMEZ. Temizlenen
    // alanın çipi bunu ADIYLA söyler (`data-cleared`, paintFieldSources).
    // ==================================================================
    function resetFieldToDefinition(el, f) {
        const def = f[2];
        el.value = (def == null) ? '' : String(def);
        if (el.tagName === 'SELECT') {
            // fieldHtml tanım değerinde `selected` basar; eşleşen seçenek
            // yoksa tarayıcı ilk seçeneği seçer — sıfırdan kurulumla aynı.
            if (el.value !== String(def) && el.options && el.options.length) {
                el.selectedIndex = 0;
            }
            secimIpucu(el);
        }
    }

    // Önceki geçişte öneriyle dolan (ve kullanıcının dokunmadığı) alanları
    // tanım varsayılanına döndürür; döndürülenlerin adlarını verir.
    function clearSuggestedFields(spec) {
        const onceki = {};
        (spec.fields || []).forEach(function (f) {
            const el = document.getElementById(fieldDomId(spec.id, f[0]));
            if (!el || !el.dataset || el.dataset.dirty === '1') return;
            if (el.dataset.suggested !== '1') return;
            resetFieldToDefinition(el, f);
            delete el.dataset.suggested;
            onceki[f[0]] = true;
        });
        // Çözücü malzemesi engeli (P17B2-08) de ŞİMDİKİ sonuçtan yeniden
        // kurulur: önceki koşunun engeli yeni motorun koşumunu durdurmaz.
        delete blockedSelects[spec.id];
        return onceki;
    }

    // Geçiş sonu: öneri almayan eski öneri alanı "temizlendi" imini taşır;
    // yeniden öneri alan alanın imi kalkar.
    function markClearedFields(spec, onceki, written) {
        (spec.fields || []).forEach(function (f) {
            const el = document.getElementById(fieldDomId(spec.id, f[0]));
            if (!el || !el.dataset) return;
            if (written[f[0]]) delete el.dataset.cleared;
            else if (onceki[f[0]]) el.dataset.cleared = '1';
        });
    }

    // ------------------------------------------------------------------
    // Öneri (fromResults) uygulama — kullanıcının elle değiştirdiği
    // alanlar (data-dirty) EZİLMEZ; POST her zaman formdan okunur.
    // ------------------------------------------------------------------
    function applySuggestions(spec) {
        // `applied`: ÖNERİSİ gerçekten alana yazılan alanlar. Kaynak çipi
        // (E3) buradan beslenir — tahmin değil, yapılan işin kaydı.
        const applied = {};
        // `withheld`: panelin BİLEREK doldurmadığı alanların GEREKÇESİ
        // (Z5-C1). Çip 'assumed' kalır — kutuda gerçekten panel varsayılanı
        // durur — ama ipucu metni nedenini makine diliyle söyler.
        const withheld = {};
        // OH-D37-S4: önceki öneriler tanım varsayılanına döner (yukarıda);
        // `written` bu geçişte öneriyle YAZILAN alanlar.
        const onceki = clearSuggestedFields(spec);
        const written = {};
        const bitir = function () {
            markClearedFields(spec, onceki, written);
            paintFieldSources(spec, applied, withheld);
        };
        if (!cfg.resultsProvider || !spec.fromResults) { bitir(); return; }
        let r = null;
        try { r = cfg.resultsProvider(); } catch (e) { r = null; }
        if (!r) { bitir(); return; }
        let sug = null;
        try { sug = spec.fromResults(r); } catch (e) { sug = null; }
        if (!sug) { bitir(); return; }
        // Panelin BİLEREK doldurmadığı alanların gerekçesi (bkz. WITHHELD_KEY).
        const gerekceler = (sug[WITHHELD_KEY] && typeof sug[WITHHELD_KEY] === 'object')
            ? sug[WITHHELD_KEY] : {};
        Object.keys(sug).forEach(function (k) {
            if (k === WITHHELD_KEY) return;         // künye sözlüğü, alan değil
            const el = document.getElementById(fieldDomId(spec.id, k));
            if (!el || el.dataset.dirty === '1') return;
            const v = sug[k];
            if (el.tagName === 'SELECT') {
                if (v == null) return;
                // SESSİZ GERİ DÜŞME KAPISI (v2.6.26): olmayan bir seçeneğe
                // value atamak tarayıcıda seçimi DÜŞÜRÜR (value '' olur) ve
                // POST gövdesine boş dize gider; hesap ucu da kendi
                // varsayılanına düşer. Kullanıcı ekranda bir malzeme görüp
                // başka malzemeyle hesaplanmış sonuç okurdu. Seçenek yoksa
                // alan DEĞİŞTİRİLMEZ: ekranda görünen değer = gönderilen
                // değer sözleşmesi korunur.
                const want = String(v);
                const opts = el.options || [];
                let found = false;
                for (let i = 0; i < opts.length; i++) {
                    if (opts[i].value === want) { found = true; break; }
                }
                // ÖH D24 / P17B2-08 — İKİ AD, TEK MALZEME.
                // ÖLÇÜLDÜ (P17 tur-16/17): çözücü `steel_304` diyor,
                // güverte listesinde yalnız `ss_304` var — AYNI alaşımın
                // iki adı. `materials_db.ALIASES` bunu zaten eşliyor ve
                // ürün onu `/api/materials` üstünden `HRMAMaterials`e
                // yayımlıyor. Eşleme burada YENİDEN YAZILMAZ (tek kaynak):
                // hem çözücünün adı hem her seçenek aynı kataloğa
                // sorulur, kanonik anahtarlar karşılaştırılır.
                if (!found && window.HRMAMaterials
                        && typeof window.HRMAMaterials.resolve === 'function') {
                    const kanon = window.HRMAMaterials.resolve(want);
                    if (kanon) {
                        for (let i = 0; i < opts.length; i++) {
                            if (window.HRMAMaterials.resolve(opts[i].value)
                                    === kanon) {
                                el.value = opts[i].value;
                                found = true;
                                break;
                            }
                        }
                    }
                }
                if (found) {
                    // el.value alias dalında zaten seçenek değerine
                    // ayarlandı; doğrudan eşleşmede `want` yazılır.
                    if (el.value !== want) {
                        for (let i = 0; i < opts.length; i++) {
                            if (opts[i].value === want) { el.value = want; break; }
                        }
                    } else {
                        el.value = want;
                    }
                    written[k] = true; el.dataset.suggested = '1'; // S4
                    applied[k] = true;
                    // DV36-06 — ÖLÇÜLDÜ (a1/once/tarayici.json, hibrit, hesap
                    // sonrası): öneri `ad_f_thermal_material`i 'steel_4130'a
                    // çekiyordu, ipucu kurulumdaki 'Çelik (genel)'de kalıyordu
                    // (görünen 'Steel AISI 4130'). Değer programla değişince
                    // `change` olayı yok: ipucu burada tazelenir.
                    secimIpucu(el);
                    if (blockedSelects[spec.id]) {
                        delete blockedSelects[spec.id][k];
                    }
                } else {
                    // ÖH D21 / P17B2-08 (yüksek) — UYUŞMAZLIK KONSOLDA KALMAZ.
                    // ÖLÇÜLDÜ (a2/once.json M3): bu dal kusuru DOĞRU tarif
                    // eden bir cümle üretiyordu ama yalnız `console.warn`e
                    // yazıyordu (ekran künyesi sayısı 0). P17 turu sonucu
                    // ölçtü: çözücü `steel_304` diyor, listede yalnız `ss_304`
                    // var, alan `steel_4130`da kalıyor ve
                    // POST /analyze_structural_safety gövdesine
                    // `"material": "steel_4130"` gidiyor — yani yapısal hüküm
                    // motorun hesaplandığı alaşımdan BAŞKA bir alaşım
                    // üzerinde veriliyor. Ekrandaki tek künye `◆ ASSUMED`
                    // idi: "bir varsayım var" diyor, "çözücünün söylediği
                    // malzeme DÜŞÜRÜLDÜ" demiyordu.
                    // Konsol bir kullanıcı arayüzü değildir: gerekçe artık
                    // `withheld` kanalına yazılır ve `paintFieldSources`
                    // onu EKRANDA GÖRÜNÜR metin olarak basar. Metin bir
                    // çeviri anahtarı değil, makine-yolu dizesidir (Z4
                    // kaçışı): iki anahtar da ham geçer, çevrilmez.
                    const gonderilen = (el.value == null) ? '' : String(el.value);
                    withheld[k] = 'solver_value_not_in_option_list: solver="'
                        + want + '" sent="' + gonderilen + '"';
                    // ÖH D24 / P17B2-08 — BEYAN ÇÖZÜM DEĞİLDİR.
                    // D21 gerekçeyi konsoldan ekrana taşıdı; ekranda
                    // gerekçe duruyor ama İSTEK YİNE DE GİDİYORDU ve
                    // gövdeye güvertenin KENDİ varsayılanı (`steel_4130`)
                    // yazılıyordu. Kayıt artık koşumu durdurur.
                    if (!blockedSelects[spec.id]) blockedSelects[spec.id] = {};
                    blockedSelects[spec.id][k] = {
                        solver: want, sent: gonderilen,
                        label: k,
                    };
                    if (window.console && console.warn) {
                        console.warn('[AnalysisDock] ' + spec.id + '.' + k
                            + ': çözücünün verdiği "' + want + '" seçeneği listede yok;'
                            + ' alan değiştirilmedi (görünen değer gönderilir).');
                    }
                }
                return;
            }
            // Anlamlı basamak: ham float değil (T66 + T45, gerekçe yukarıda)
            if (typeof v === 'number' && Number.isFinite(v)) {
                el.value = dockSigFig(v);
                // OH-D37-S4: öneriyle yazıldı — sonraki sonuç bu alana öneri
                // vermezse alan tanım varsayılanına döner (bayat kalmaz).
                written[k] = true;
                el.dataset.suggested = '1';
                // GERİ ÇEKİLEN alan "hesaptan geldi" diye imlenmez: kutuda
                // panelin nöbetçi değeri var, çözücünün sayısı DEĞİL.
                if (gerekceler[k]) withheld[k] = String(gerekceler[k]);
                else applied[k] = true;
            }
        });
        bitir();
    }

    // ------------------------------------------------------------------
    // E3'ün GÜVERTEDEKİ KAPISI: form alanının kaynağı
    // ------------------------------------------------------------------
    // Kaynak dört durumdan biridir ve üçü KESİN olarak bilinir; dördüncüsü
    // (computed) "bu sayı en son hesabın sonucundan, panelin fromResults
    // eşlemesiyle dolduruldu" demektir — ipucu metni bunu birebir söyler,
    // fazlasını iddia etmez:
    //   user     : kullanıcı alanı elle değiştirdi (data-dirty)
    //   computed : değer son hesap sonucundan geldi (applied)
    //   assumed  : panel varsayılanı kaldı (hesaptan değer gelmedi)
    //   missing  : alan boş — gönderilecek bir değer yok
    function fieldSourceKind(el, fieldId, applied) {
        if (!el) return 'missing';
        if (el.dataset && el.dataset.dirty === '1') return 'user';
        const val = (el.value == null) ? '' : String(el.value).trim();
        if (val === '') return 'missing';
        if (applied && applied[fieldId]) return 'computed';
        return 'assumed';
    }

    const FIELD_SRC_NOTE_KEYS = {
        computed: 'dock.src.fieldComputed',
        user: 'dock.src.fieldUser',
        assumed: 'dock.src.fieldAssumed',
        missing: 'dock.src.fieldMissing',
    };
    const FIELD_SRC_NOTE_FALLBACK = {
        computed: 'Pre-filled from the latest calculation result through this '
            + 'panel\'s field mapping.',
        user: 'You edited this field; suggestions no longer overwrite it.',
        assumed: 'The calculation result carried no value for this field, so the '
            + 'panel default is still in the box.',
        missing: 'The field is empty — the request will not be sent until you '
            + 'enter a value.',
    };

    // ÖH D37 A1b sahte-veri-b · OH-D37-S5 — BOŞ ALANIN İKİ HÂLİ.
    // `missing` notu ("bir değer girene kadar istek gönderilmez") yalnız
    // ZORUNLU alan için doğrudur (requiredFieldInfo: tanım varsayılanı
    // sonlu sayı). İsteğe bağlı boş alan (burn_time, propellant_mass,
    // cidar sıcaklığı çifti …) gövdeye konmadan istek GİDER; uç o alan
    // için kendi kuralını uygular (422 missing_fields, bant ya da adıyla
    // geri çekme). Çipin rengi/etiketi aynı ('missing'); değişen not.
    const FIELD_SRC_BLANK_OPTIONAL_KEY = 'dock.src.fieldBlankOptional';
    const FIELD_SRC_BLANK_OPTIONAL_FALLBACK = 'The field is empty — this field '
        + 'is not sent; the endpoint applies its own rule.';
    // OH-D37-S4: önceki koşunun önerisi bu koşuda gelmediği için temizlendi.
    const FIELD_SRC_CLEARED_KEY = 'dock.src.fieldCleared';
    const FIELD_SRC_CLEARED_FALLBACK = 'The previous run\'s value was cleared '
        + '— this run did not publish this field.';

    function fieldSourceNote(kind, optional) {
        if (kind === 'missing' && optional) {
            return T(FIELD_SRC_BLANK_OPTIONAL_KEY, FIELD_SRC_BLANK_OPTIONAL_FALLBACK);
        }
        return T(FIELD_SRC_NOTE_KEYS[kind], FIELD_SRC_NOTE_FALLBACK[kind]);
    }

    function paintFieldSources(spec, applied, withheld) {
        const zorunluluk = requiredFieldInfo(spec);            // OH-D37-S5
        (spec.fields || []).forEach(function (f) {
            const fid = f[0];
            const slot = document.getElementById(fieldSourceSlotId(spec.id, fid));
            if (!slot) return;
            const el = document.getElementById(fieldDomId(spec.id, fid));
            const kind = fieldSourceKind(el, fid, applied);
            let note = fieldSourceNote(kind, !!zorunluluk.optional[fid]);
            // OH-D37-S4: bayat öneri temizlendiyse ipucu bunu ÖNCE söyler;
            // ardından alanın BUGÜNKÜ hâlinin notu (boş / tanım varsayılanı).
            const temizlendi = !!(el && el.dataset && el.dataset.cleared === '1'
                && kind !== 'user');
            if (temizlendi) {
                note = T(FIELD_SRC_CLEARED_KEY, FIELD_SRC_CLEARED_FALLBACK) + ' ' + note;
            }
            // Z5-C1: geri çekilen önerinin GEREKÇESİ ipucuna eklenir. Metin
            // bir çeviri anahtarı DEĞİL, makine-yolu dizesidir (Z4 kaçışı):
            // alan adları ve motorun kendi beyanı ham geçer, çevrilmez.
            if (withheld && withheld[fid]) {
                note += ' | ' + withheld[fid];
                if (slot.dataset) slot.dataset.withheld = '1';
            } else if (slot.dataset && slot.dataset.withheld) {
                delete slot.dataset.withheld;
            }
            slot.innerHTML = sourceChip({ kind: kind, declared: true }, note);
            // ÖH D21 / P17B2-08: GEREKÇE `title` İPUCUNDA SAKLANMAZ.
            // P17 turu aynı kusuru iki yerde ölçtü (P17B2-08 malzeme
            // uyuşmazlığı; borç kontrolünde S1-03 ısı akısı): ürün doğru
            // beyanı üretiyor ama yalnız ipucuna/konsola yazıyor. İpucu
            // fare gerektirir, dokunmatik ekranda ve ekran okuyucunun
            // akışında yoktur. Geri çekilen öneri artık çipin yanında
            // GÖRÜNÜR bir satır olarak da durur.
            if (withheld && withheld[fid]) {
                slot.insertAdjacentHTML('beforeend',
                    '<span class="ad-withheld-note" style="display:block;'
                    + 'margin-top:2px; font-family:var(--hd-mono, monospace);'
                    + 'font-size:0.62rem; letter-spacing:0.04em;'
                    + 'color:var(--hd-orange, #ff8c33); white-space:normal;">'
                    + escAttr(withheld[fid]) + '</span>');
            }
            // OH-D37-S4: temizlenen alan da ipucunda SAKLANMAZ (D21 dersi) —
            // çipin altında görünür satır; `data-i18n` ile dil değişince
            // kendiliğinden çevrilir.
            if (slot.dataset) {
                if (temizlendi) slot.dataset.cleared = '1';
                else delete slot.dataset.cleared;
            }
            if (temizlendi) {
                slot.insertAdjacentHTML('beforeend',
                    '<span class="ad-cleared-note" data-i18n="'
                    + FIELD_SRC_CLEARED_KEY + '" style="display:block;'
                    + 'margin-top:2px; font-family:var(--hd-mono, monospace);'
                    + 'font-size:0.62rem; letter-spacing:0.04em;'
                    + 'color:var(--hd-ink-dim, #7d97a5); white-space:normal;">'
                    + escAttr(T(FIELD_SRC_CLEARED_KEY, FIELD_SRC_CLEARED_FALLBACK))
                    + '</span>');
            }
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(slot);
        });
    }

    // Alan elle değiştirilince o alanın çipi anında 'user'a döner.
    function repaintFieldSource(spec, fieldId) {
        const slot = document.getElementById(fieldSourceSlotId(spec.id, fieldId));
        if (!slot) return;
        const el = document.getElementById(fieldDomId(spec.id, fieldId));
        const kind = fieldSourceKind(el, fieldId, null);
        if (slot.dataset) delete slot.dataset.cleared;             // OH-D37-S4
        slot.innerHTML = sourceChip({ kind: kind, declared: true },
            fieldSourceNote(kind, !!requiredFieldInfo(spec).optional[fieldId]));
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(slot);
    }

    // ==================================================================
    // ZORUNLU ALAN SÖZLEŞMESİ  (Faz 5 / H3-B8)
    // ------------------------------------------------------------------
    // Alan tanımındaki varsayılan (f[2]) SONLU BİR SAYIYSA alan zorunludur.
    // Varsayılanı boş dize olan alanlar tasarım gereği isteğe bağlıdır ve
    // etiketlerinde bunu zaten söylerler:
    //   protection_panel  q_star_MJ_kg  "blank = band"
    //   protection_panel  emissivity    "blank = material"
    //   vessel_panel      wall_thickness_mm "blank = auto-size"
    //   joint_panel       external_axial_load_n "(N, optional)"
    //
    // ESKİ DAVRANIŞ: boş alan payload'a hiç konmuyordu ("backend kendi
    // varsayılanını kullanır" varsayımı). Uç için ZORUNLU olan bir argüman
    // böyle kaybolunca ham Python istisnası kullanıcıya geri dönüyordu.
    // ÖLÇÜLDÜ (2026-08-03, app.test_client, /api/thermal-protection,
    // mode=ablative):
    //   tam gövde                      -> HTTP 200
    //   q_net_W_m2 alanı boş ('')      -> HTTP 500
    //     {"error":"ThermalProtectionAnalyzer.ablative_thickness() missing
    //       1 required positional argument: 'q_net_W_m2'"}
    //   q_net_W_m2 alanı hiç yok       -> HTTP 500 (aynı metin)
    //
    // YENİ DAVRANIŞ: eksik zorunlu alan varsa istek HİÇ GÖNDERİLMEZ ve
    // hangi alanların boş olduğu kullanıcıya adıyla söylenir. Uydurma
    // varsayılan KONMAZ — boş alan bir değer değildir.
    // ==================================================================
    //
    // ÖH A2 sivi-sogutma · 7. tur — 'BOŞ + ZORUNLU' BEYANI.
    // Kural yalnız sonlu sayısal varsayılanı zorunlu sayıyordu; kaynaksız
    // ön-dolgusu kaldırılan (tanım değeri BOŞ) ama uç ya da model için
    // zorunlu olan alan 'isteğe bağlı' görünüyordu (ölçülen: regen paneli
    // n_channels — güverte çipi "gönderilmez, uç kendi kuralını uygular"
    // diyordu, uç ise 400 veriyordu). Panel artık `spec.required`
    // dizisinde bu alanları ADIYLA beyan eder; beyanlı alan varsayılanı
    // ne olursa olsun zorunludur (boşsa istek gönderilmez). Beyan dışı
    // alanlarda kural aynen.
    function requiredFieldInfo(spec) {
        const optional = {};
        const labels = {};
        const beyanli = {};
        if (spec && Array.isArray(spec.required)) {
            spec.required.forEach(function (id) {
                if (typeof id === 'string' && id) beyanli[id] = true;
            });
        }
        (spec.fields || []).forEach(function (f) {
            const def = f[2];
            if (!(typeof def === 'number' && Number.isFinite(def))
                    && !beyanli[f[0]]) {
                optional[f[0]] = true;
            }
            labels[f[0]] = T(f[4], f[1]);
        });
        return { optional: optional, labels: labels };
    }

    // {payload, missing} döner. `missing` boş değilse istek gönderilmemelidir.
    function buildPayload(spec) {
        applySuggestions(spec);
        // OH-GT-31: öneri bir seçiciyi değiştirmiş olabilir — ipucu seçimle
        // birlikte gider, yoksa ekranda eski seçeneğin tam metni kalırdı.
        secimIpuclariniTazele(document.getElementById('ad_sec_' + spec.id));
        const payload = {};
        const missing = [];
        const sec = document.getElementById('ad_sec_' + spec.id);
        if (!sec) return { payload: payload, missing: missing };
        const info = requiredFieldInfo(spec);
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') {
                // 7. tur: zorunlu seçicide boş seçim (yer tutucu) bir değer
                // değildir — istek durur, alan adıyla söylenir.
                if (el.value === '' && !info.optional[key]) {
                    missing.push(info.labels[key] || key);
                    return;
                }
                payload[key] = el.value;
                return;
            }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) {
                payload[key] = v;
                return;
            }
            // Boş / sayı olmayan alan: isteğe bağlıysa gönderilmez (uç kendi
            // bandını/malzemesini kullanır), zorunluysa istek durdurulur.
            if (!info.optional[key]) missing.push(info.labels[key] || key);
        });
        return { payload: payload, missing: missing };
    }

    // ------------------------------------------------------------------
    // YANIT GÖVDESİ OKUMA  (Faz 5 / H3-B9)
    // ------------------------------------------------------------------
    // Bazı uçlar `sanitize_json_values` süzgecinden geçmiyor ve sonlu
    // olmayan sayıları JSON'a Python söz dizimiyle yazıyor. RFC 8259'da
    // Infinity/NaN diye bir değer YOKTUR; tarayıcının JSON.parse'ı bunu
    // reddeder, `response.json()` fırlatır.
    // ÖLÇÜLDÜ (2026-08-03, app.test_client):
    //   POST /api/altitude-to-pressure {"altitude": -Infinity}
    //     -> HTTP 200  {"altitude":-Infinity,"pressure":Infinity,...}
    //   POST /api/oxidizer-properties {"temperature": Infinity}
    //     -> HTTP 200  ..."temperature":Infinity}
    // Ham ayrıştırıcı mesajı ("Unexpected token 'I'...") kullanıcıya hiçbir
    // şey anlatmaz. Burada AÇIK bir hataya çevrilir, ham gövde konsola
    // yazılır ve hata yukarı fırlatılır — YUTULMAZ, panel boş kalmaz.
    async function readJsonBody(resp) {
        const text = await resp.text();
        try {
            return JSON.parse(text);
        } catch (e) {
            if (window.console && console.error) {
                console.error('[AnalysisDock] geçersiz JSON gövdesi (HTTP '
                    + resp.status + '):', text);
            }
            throw new Error(TF('common.badJson', { status: resp.status },
                'Server replied HTTP {status} but the body is not valid JSON '
                + '(Infinity/NaN are not JSON values). Nothing was drawn; the '
                + 'raw body is in the browser console.'));
        }
    }

    // ------------------------------------------------------------------
    // ÖH D34 · OH-GT-14 — GÜVERTE HAM ARKA UÇ KODU BASIYORDU
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (a1/once.json): `runPanel` reddi `throw new Error(data.error
    // || 'HTTP ' + status)` ile kuruyordu, yani ekrana ucun MAKİNE KODU
    // düşüyordu: "HATA: incomplete_flow_input". Aynı ölçümde dört ucun
    // hata gövdesi canlı okundu (Flask test istemcisi, eksik gövde):
    //   /api/flow-analysis          422  error + message + missing_fields(6)
    //                                    + invalid_fields(6)
    //   /analyze_thermal_safety     422  error + message + invalid_fields(1)
    //   /analyze_structural_safety  422  error + message + missing_fields(3)
    //   /analyze_safety             422  error + message + missing_fields(3)
    // Yani kullanıcının ihtiyaç duyduğu HER ŞEY (hangi alan eksik, hangisi
    // kullanılamaz, neden) gövdede ZATEN vardı ve güverte hepsini atıp tek
    // bir kodu basıyordu. Arka uca dokunulmadı; kayıp yalnız bu katmandaydı.
    //
    // FAIL-CLOSED (Doktrin 1): tanınmayan kod ÇEVRİLMEZ, uydurulmaz ve
    // yutulmaz — olduğu gibi, "bu güverte bu kodu tanımıyor" işaretiyle
    // basılır; alan listeleri ve ucun kendi gerekçesi yine gösterilir, yani
    // tanınmayan kodda bile bilgi KAYBOLMAZ.
    //
    // Sözlük anahtarları henüz `i18n_*.js`te YOK (o dosya bu dalgada başka
    // kulvarın sahasında): `T`/`TF` İngilizce yedeği basar, Türkçe karşılık
    // metin-i18n kulvarına devredildi. Uç mesajları İngilizce kalır.
    //: Güvertenin uçlarında ÖLÇÜLMÜŞ reddetme kodları -> sözlük anahtarı.
    const HATA_ANAHTARI = {
        incomplete_flow_input: 'dock.err.incompleteFlowInput',
        invalid_flow_input: 'dock.err.invalidFlowInput',
        incomplete_thermal_input: 'dock.err.incompleteThermalInput',
        invalid_thermal_input: 'dock.err.invalidThermalInput',
        incomplete_structural_input: 'dock.err.incompleteStructuralInput',
        invalid_structural_input: 'dock.err.invalidStructuralInput',
        incomplete_safety_input: 'dock.err.incompleteSafetyInput',
        invalid_safety_input: 'dock.err.invalidSafetyInput',
    };
    //: Aynı kodların İngilizce yedek cümleleri (sözlük yüklenmezse basılır).
    const HATA_YEDEGI = {
        incomplete_flow_input:
            'The nozzle flow solution was not run: this endpoint publishes '
            + 'the regime, CF and thrust of YOUR motor, and the inputs '
            + 'below were not supplied, so nothing was assumed for you.',
        invalid_flow_input:
            'The nozzle flow solution was not run: the inputs below are '
            + 'outside the range this solver can work in.',
        incomplete_thermal_input:
            'The thermal analysis was not run: the inputs below were not '
            + 'supplied and cannot be derived from the rest of the form.',
        invalid_thermal_input:
            'The thermal analysis was not run: the inputs below are not '
            + 'usable (non-finite, non-positive or out of range).',
        incomplete_structural_input:
            'The structural assessment was not produced: the inputs below '
            + 'were not supplied.',
        invalid_structural_input:
            'The structural assessment was not produced: the inputs below '
            + 'are not usable, and a verdict may not be computed on them.',
        incomplete_safety_input:
            'The safety verdict was not produced: the inputs below were '
            + 'not supplied.',
        invalid_safety_input:
            'The safety verdict was not produced: the inputs below are not '
            + 'usable, and a verdict may not be computed on them.',
    };

    /** Reddedilen bir uç yanıtını okunabilir cümleye çevirir. */
    function ucRedMetni(data, http) {
        const govde = (data && typeof data === 'object') ? data : {};
        const kod = govde.error ? String(govde.error) : '';
        const parcalar = [];
        // V3 KK 3. tur: kendi POST'unu yapan panel kendi ucunun kodunu
        // üçüncü argümanla verir ({kod: [anahtar, EN yedek]}); güvertenin
        // ölçülmüş kod tablosu (HATA_ANAHTARI) değişmez.
        const ekKodlar = (arguments.length > 2 && arguments[2]
                          && typeof arguments[2] === 'object') ? arguments[2] : {};

        if (!kod) {
            parcalar.push(TF('dock.err.noCode', { status: http },
                'The endpoint refused the request (HTTP {status}) without '
                + 'naming a reason. Nothing was computed.'));
        } else if (HATA_ANAHTARI[kod]) {
            parcalar.push(T(HATA_ANAHTARI[kod], HATA_YEDEGI[kod]));
        } else if (Object.prototype.hasOwnProperty.call(ekKodlar, kod)
                   && Array.isArray(ekKodlar[kod])) {
            parcalar.push(T(ekKodlar[kod][0], ekKodlar[kod][1]));
        } else {
            // Tanınmayan kod: HAM + İŞARETLİ (sessiz "ok" ya da tahmin yok).
            parcalar.push(TF('dock.err.unknown', { code: kod, status: http },
                'The endpoint refused the request with a reason code this '
                + 'deck does not recognise, printed unchanged: "{code}" '
                + '(HTTP {status}). Nothing was computed.'));
        }

        const eksik = Array.isArray(govde.missing_fields)
            ? govde.missing_fields.map(String) : [];
        if (eksik.length) {
            parcalar.push(TF('dock.err.missingFields',
                { fields: eksik.join(', ') },
                'Not supplied: {fields}.'));
        }

        const gecersiz = (Array.isArray(govde.invalid_fields)
            ? govde.invalid_fields : []).map(function (f) {
                if (!f || typeof f !== 'object') return String(f);
                const ad = f.field == null ? '?' : String(f.field);
                const neden = f.reason ? ' (' + String(f.reason) + ')' : '';
                return ad + neden;
            }).filter(function (x) { return eksik.indexOf(x) < 0; });
        if (gecersiz.length) {
            parcalar.push(TF('dock.err.invalidFields',
                { fields: gecersiz.join('; ') },
                'Not usable: {fields}.'));
        }

        // Uç kendi gerekçesini yazdıysa ve yukarıda ALAN ADI çıkmadıysa o
        // cümle TEK bilgi kaynağıdır — yutulmaz (uç mesajları İngilizcedir).
        if (!eksik.length && !gecersiz.length && govde.message) {
            parcalar.push(String(govde.message));
        }
        return parcalar.join(' ');
    }

    // ------------------------------------------------------------------
    // Çalıştırma
    // ------------------------------------------------------------------
    async function runPanel(spec) {
        const status = document.getElementById('ad_status_' + spec.id);
        const root = document.getElementById('ad_root_' + spec.id);
        const btn = document.getElementById('ad_run_' + spec.id);
        if (!status || !root || !btn) return;
        // Gövde ÖNCE kurulur: zorunlu alan boşsa uca hiç gidilmez (H3-B8).
        const built = buildPayload(spec);

        // ------------------------------------------------------------------
        // ÖH D24 / P17B2-08 — ÇÖZÜCÜNÜN MALZEMESİ DÜŞÜRÜLDÜYSE KOŞMA
        // ------------------------------------------------------------------
        // ÖLÇÜLDÜ (P17 tur-17): çözücü `steel_304` verdi, güverte listesinde
        // yoktu, alan `steel_4130`da kaldı ve gövdeye `"material":
        // "steel_4130"` gitti — yapısal emniyet hükmü motorun hesaplandığı
        // alaşımdan BAŞKA bir alaşım üzerinde verildi. `applySuggestions`
        // artık alias kataloğunu (materials_db → /api/materials) deniyor;
        // ORADAN DA çözülemeyen bir ad kalırsa istek GÖNDERİLMEZ. Sessiz
        // yedek yasaktır: kullanıcı hangi alanın, hangi çözücü değerinin ve
        // yerine ne gideceğinin ADINI okur.
        const engel = blockedSelects[spec.id] || {};
        const engelliAlanlar = Object.keys(engel);
        if (engelliAlanlar.length) {
            root.style.display = 'none';
            status.textContent = TF('dock.materialNotInList',
                { fields: engelliAlanlar.map(function (k) {
                    return k + ' (solver="' + engel[k].solver
                        + '", the form would send "' + engel[k].sent + '")';
                }).join('; ') },
                'The solver value for {fields} is not in this deck\'s option '
                + 'list and could not be matched through the materials '
                + 'catalogue. The request was NOT sent: a safety verdict may '
                + 'not be computed on a different material than the motor. '
                + 'Pick the matching entry yourself, or re-run the motor '
                + 'calculation with a material this deck offers.');
            return;
        }

        // ------------------------------------------------------------------
        // ÖH D24 / P11B2-11 — BOŞ GÖVDE POSTALAMA
        // ------------------------------------------------------------------
        // ÖLÇÜLDÜ (a3/once.json + P11 B2-repro-09): `fields: []` ile
        // kaydolan panellerde `payload = {}` ve `missing = []` olduğu için
        // kapı açık kalıyordu; üç uç her seferinde HTTP 400 döndürüyordu
        // (comparative "At least 2 motor configurations…", uncertainty
        // "motor_type must be one of…", validation "No CSV content…") ve
        // kullanıcı ekranda ham arka-uç cümlesi okuyordu. Bu paneller kendi
        // `fetch`lerini ayrıca kuruyor: güvertenin düğmesi çalışan yolun
        // yanında duran, HİÇ çalışmayan ikinci bir kontroldü.
        // Boş gövdenin MEŞRU olduğu tek uç (`/api/correlation-report`,
        // ölçüldü: 200 + 54.805 B) bunu `allowsEmptyPayload` ile BEYAN eder.
        if (!Object.keys(built.payload).length && spec.allowsEmptyPayload !== true) {
            root.style.display = 'none';
            status.textContent = T('dock.emptyPayload',
                'This panel declares no deck fields, so this button would '
                + 'post an empty body — the endpoint rejects that. Nothing '
                + 'was sent. Use the panel\'s own controls below, which build '
                + 'the request they need.');
            return;
        }

        if (built.missing.length) {
            root.style.display = 'none';
            status.textContent = TF('dock.missingFields',
                { fields: built.missing.join(', ') },
                'Required fields are empty: {fields}. The request was not '
                + 'sent — a blank field is not a value. Enter a number (or '
                + 'reload the suggestion) and run again.');
            return;
        }
        btn.disabled = true;
        root.style.display = 'none';
        status.textContent = spec.long
            ? T('common.runningLong', 'RUNNING — this analysis may take a while…')
            : T('common.running', 'RUNNING…');
        // ÖH D35 · OH-GT-36 — BİTİŞ GERİ BİLDİRİMİ (süre ölçümü burada başlar)
        const t0 = (window.performance && typeof performance.now === 'function')
            ? performance.now() : Date.now();
        try {
            const resp = await fetch(spec.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(built.payload),
            });
            const data = await readJsonBody(resp);
            if (!resp.ok || data.status === 'error') {
                throw new Error(ucRedMetni(data, resp.status));   // OH-GT-14
            }
            purgePlots(root);           // eski grafiklerin resize dinleyicileri sızmasın
            root.innerHTML = '';
            lastData[spec.id] = data;          // dil değişiminde yeniden çizmek için sakla
            spec.render(data, root);
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
            root.style.display = 'block';
            // ------------------------------------------------------------------
            // ÖH D35 · OH-GT-36 — KOŞUM BİTİNCE DURUM SATIRI SUSUYORDU
            // ------------------------------------------------------------------
            // ÖLÇÜLDÜ (a1/once.json M6_bitis_geri_bildirimi): başarı dalının
            // son işi `status.textContent = ''` idi
            // (`basari_dalinda_status_bosaltiliyor_mu = true`) ve süre hiç
            // ölçülmüyordu (`sure_olculuyor_mu = false`). Yani "ÇALIŞIYOR…"
            // yazısı SİLİNİYOR, yerine hiçbir şey konmuyordu: sonuç kökü
            // dolsa bile kullanıcı (ve 21 Eylül turunda Cowork) "hiçbir şey
            // olmadı" sanıyordu — U-1/SU-1/LU-3'ün ayakta kalan çekirdeği bu.
            // (Aynı bulgunun "istek hiç gitmiyor" iddiası ana modelin canlı
            // ölçümüyle ÇÜRÜDÜ: istek gidiyor, `ad_root` doluyor.)
            //
            // Metin YENİ bir anahtar icat etmez: Analiz Merkezi'nin bitiş
            // cümlesi (`ac.run.done`, i18n_common.js:233/2802) AYNI olguyu
            // AYNI sözcüklerle anlatıyor — tek kaynak odur.
            // Ondalık ayracı da tek kaynaktan: `I18N.number` (i18n.js:330).
            // Satır SOLMAZ; bir sonraki koşum ya da hata onu değiştirir.
            const gecen = ((window.performance && typeof performance.now === 'function')
                ? performance.now() : Date.now()) - t0;
            const sn = Math.round(gecen / 100) / 10;      // 0,1 s çözünürlük
            const snMetin = (window.I18N && typeof window.I18N.number === 'function')
                ? window.I18N.number(sn, 1) : sn.toFixed(1);
            status.textContent = TF('ac.run.done', { seconds: snMetin },
                                    'Completed in {seconds} s.');
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            btn.disabled = false;
        }
    }

    // Dil değiştiğinde: sabit etiketleri I18N.apply() zaten çevirir, panel
    // çıktısı ise saklanan yanıtla yeniden çizilir (yeni istek atılmaz).
    function rerenderAll() {
        registry.forEach(function (spec) {
            const data = lastData[spec.id];
            const root = document.getElementById('ad_root_' + spec.id);
            if (!data || !root || root.style.display === 'none') return;
            try {
                purgePlots(root);       // eski grafiklerin resize dinleyicileri sızmasın
                root.innerHTML = '';
                spec.render(data, root);
                if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
            } catch (e) {
                if (window.console) console.warn('AnalysisDock rerender:', spec.id, e);
            }
        });
        // OH-GT-31: seçici ipuçları (`title`) I18N.apply kanalında DEĞİL —
        // seçenek metni çevrildikten sonra elle tazelenir.
        secimIpuclariniTazele(document);
        // "Ne değişti" şeridi ve kaynak lejantı da yeni dile döner
        renderDiffBand();
        const legendHost = document.getElementById('ad_src_legend');
        if (legendHost && legendHost.getAttribute('data-filled') === '1') {
            legendHost.innerHTML = sourceLegend();
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(legendHost);
        }
    }

    // ------------------------------------------------------------------
    // Panel montajı
    // ------------------------------------------------------------------
    function panelApplies(spec) {
        return !spec.motorTypes || spec.motorTypes.indexOf(cfg.motorType) !== -1;
    }

    function mountPanel(spec) {
        const pane = ensureCategory(spec.category);
        if (!pane) return;
        const empty = pane.querySelector('.ad-empty');
        if (empty) empty.remove();
        const holder = document.createElement('div');
        holder.innerHTML = panelSectionHtml(spec);
        pane.appendChild(holder.firstElementChild);

        document.getElementById('ad_run_' + spec.id)
            .addEventListener('click', function () { runPanel(spec); });
        // Kullanıcı bir alanı elle değiştirirse öneriler onu bir daha ezmez
        const sec = document.getElementById('ad_sec_' + spec.id);
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const fid = el.getAttribute('data-field');
            el.addEventListener('input', function () {
                el.dataset.dirty = '1';
                delete el.dataset.suggested; delete el.dataset.cleared; // S4
                repaintFieldSource(spec, fid);      // çip anında 'user'a döner
            });
            el.addEventListener('change', function () {
                el.dataset.dirty = '1';
                delete el.dataset.suggested; delete el.dataset.cleared; // S4
                repaintFieldSource(spec, fid);
                secimIpucu(el);                       // OH-GT-31
            });
        });
        // İlk montajda sonuçtan önerileri doldur (varsa)
        applySuggestions(spec);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(sec);
        // OH-GT-31: öneri seçimi değiştirmiş ve applyTo seçenekleri
        // çevirmiş olabilir — ipuçları en sonda, çevrilmiş metinle basılır.
        secimIpuclariniTazele(sec);
    }

    // ------------------------------------------------------------------
    // Genel API
    // ------------------------------------------------------------------
    // E2/E3 katmanlarının tek nesnesi: hem AnalysisDock.diff/source hem de
    // AnalysisDock.ui.diff/ui.source aynı nesneyi gösterir (kopya değil).
    const DIFF_API = {
        compute: diffCompute,
        badge: diffBadge,
        annotate: diffAnnotate,
        strip: diffStripHtml,
        note: noteResults,
        last: function () { return lastDiff; },
        THRESHOLD: DIFF_REL_EPS,
    };
    const SOURCE_API = {
        of: sourceOf,
        kindOfText: sourceKindOfText,
        chip: sourceChip,
        cell: sourceCell,
        // ÖH D26 / P11B2-10 — panel bağlaması (blok defteri)
        ledger: sourceLedger,
        ledgerInto: sourceLedgerInto,
        declarations: sourceDeclarations,
        legend: sourceLegend,
        color: sourceColor,
        symbol: sourceSymbol,
        label: sourceLabel,
        marker: sourceMarker,
        plotSymbol: sourcePlotSymbol,
        KINDS: SOURCE_KINDS.slice(),
        COLORS: SOURCE_COLORS,
    };

    function register(spec) {
        if (!spec || !spec.id || !spec.category || !spec.endpoint
            || typeof spec.render !== 'function') {
            if (window.console) console.warn('AnalysisDock.register: invalid spec', spec);
            return;
        }
        if (registeredIds[spec.id]) {
            if (window.console) console.warn('AnalysisDock.register: duplicate id', spec.id);
            return;
        }
        registeredIds[spec.id] = true;
        registry.push(spec);
        if (inited && panelApplies(spec)) mountPanel(spec);
    }

    function init(options) {
        if (inited) return;
        cfg = options || {};
        cfg.motorType = cfg.motorType || 'hybrid';

        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = dockHtml();
        const dock = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(dock, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(dock);
        }
        inited = true;

        // ÖH D37 A1a · DV36-06 — İPUCU GÖSTERİM ANINDA EŞİTLENİR.
        // ÖLÇÜLDÜ (a1/once/tarayici.json): katalog (`HRMAMaterials
        // .populateSelect`, katı sayfası) seçenekleri kurulumdan SONRA yeniden
        // kuruyor ve ipucu eski seçeneğin metninde kalıyordu ('Steel
        // (generic)' ⟷ görünen 'Carbon steel (generic, A36-class)'). Kaynak
        // ne olursa olsun (katalog, öneri, geç sözlük) ipucu, göründüğü an
        // seçili seçeneğin görünen metnidir: üzerine gelme ve odak.
        if (dock && dock.addEventListener) {
            ['mouseover', 'focusin'].forEach(function (olay) {
                dock.addEventListener(olay, function (e) {
                    const t = e && e.target;
                    if (t && t.tagName === 'SELECT' && t.getAttribute
                            && t.getAttribute('data-field') !== null) {
                        secimIpucu(t);
                    }
                });
            });
        }

        // Yerleşim düğmeleri (E1) — tercih localStorage'da yaşar
        const toolbar = document.getElementById('ad_toolbar');
        if (toolbar && toolbar.querySelectorAll) {
            Array.prototype.forEach.call(toolbar.querySelectorAll('.ad-layout-btn'),
                function (b) {
                    b.addEventListener('click', function () {
                        setLayout(b.getAttribute('data-layout'));
                    });
                });
        }

        // Temel sekmeler her zaman kurulur; yeni kategoriler talep üzerine eklenir
        BASE_CATEGORIES.forEach(ensureCategory);
        registry.filter(panelApplies).forEach(mountPanel);
        selectCategory(activeCategory || BASE_CATEGORIES[0]);
        applyLayout();              // kaydedilmiş tercihi uygula (yoksa 'tabs')
        // Güverte kurulmadan önce hesap yapılmışsa referans anlık görüntüsü
        // ilk sonuçtan alınır (fark bir SONRAKİ hesapta çıkar).
        if (typeof cfg.resultsProvider === 'function') {
            try { noteResults(cfg.resultsProvider()); } catch (e) { /* sonuç yok */ }
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(dock);
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(rerenderAll);
        // C4: katlanmış beyanların sıfır-tıklama sayaç rozeti. Güverte
        // dışındaki panelleri de kapsar (fea/blowdown/sixdof/thermal_fea) —
        // hepsi aynı sayfada yaşıyor ve hepsinin katlısı varsayılan kapalı.
        startDeclarationFoldWatch();
    }

    function getMotorType() {
        return cfg.motorType || 'hybrid';
    }

    // Sonuç değiştiğinde entegrasyon katmanı çağırır (app.js:335,
    // solid.html:3559, liquid.html:2171): dirty olmayan alanları en güncel
    // sonuçla tazeler VE "ne değişti" farkını (E2) çıkarır. Fark kapısı
    // bilerek buraya bağlandı — her hesap sonrası zaten çağrılan tek ortak
    // nokta burası; yeni bir kanal açıp kapısını unutmamak için (Faz 5 dersi).
    function refreshSuggestions() {
        if (!inited) return;
        registry.filter(panelApplies).forEach(applySuggestions);
        if (typeof cfg.resultsProvider === 'function') {
            try { noteResults(cfg.resultsProvider()); } catch (e) { /* sonuç yok */ }
        }
        // C4: hesap sonrası katlılar yeniden doluyor. Gözlemci zaten
        // tetikleniyor; bu çağrı MutationObserver'ı olmayan tarayıcılarda
        // sayacın bayat kalmamasını garanti eder.
        scheduleDeclarationFolds();
    }

    window.AnalysisDock = {
        init: init,
        register: register,
        getMotorType: getMotorType,
        refreshSuggestions: refreshSuggestions,
        selectCategory: selectCategory,
        // --- E1: yerleşim (sekme / ızgara) ---
        getLayout: getLayout,
        setLayout: setLayout,
        LAYOUTS: LAYOUTS.slice(),
        // --- E2: "ne değişti" farkı ---
        diff: DIFF_API,
        // --- E3: değer kaynağı renklendirmesi ---
        source: SOURCE_API,
        ui: {
            // Paneller yalnız `ui`yi yakalıyor; iki yeni katman oradan da
            // erişilebilir olmalı (aynı nesne, kopya değil).
            source: SOURCE_API,
            diff: DIFF_API,
            t: T,
            tf: TF,
            /* ÖH D31 · OH-D30-06 — BİRİMLİ DİZE TR KİPİNDE NOKTALI.
               ÖLÇÜLDÜ (a1/once.json · M5): panels/ altında 17 `toFixed`
               çağrısı var, `I18N.number` atfı 0. `toFixed` her zaman
               NOKTA basar; ürünün geri kalanı TR kipinde VİRGÜL basıyor
               (I18N.number, i18n.js:373). Sonuç: aynı ekranda "36.3 bar"
               ile "36,3 bar" yan yana duruyordu. Biçim TEK KAYNAKTAN
               gelir; sözlük motoru yüklenmemişse toFixed'e düşer (sayı
               UYDURULMAZ, yalnız ayraç yerelleşmez).
               NOT: CSS geometrisi (piksel, opaklık) BU yardımcıdan
               GEÇMEZ — orada nokta zorunludur ve virgül stili bozar. */
            num: function (value, digits) {
                if (typeof value !== 'number' || !isFinite(value)) {
                    return (value === null || value === undefined)
                        ? '' : String(value);
                }
                return (window.I18N && window.I18N.number)
                    ? window.I18N.number(value, digits)
                    : ((typeof digits === 'number')
                        ? value.toFixed(digits) : String(value));
            },
            badge: badge,
            statCard: statCard,
            kvTable: kvTable,
            sectionTitle: sectionTitle,
            listBlock: listBlock,
            /* ÖH D26 / arayuz a2 — `U.esc` KANALI VARDI, KAPISI YOKTU.
               ÖLÇÜLDÜ (taban 7751531, node ile canlı koşum:
               `typeof AnalysisDock.ui.esc === 'undefined'`, ui 37
               anahtar taşıyor ve `esc` bunlardan biri DEĞİL):
               `panels/flow_panel.js` bu adı YEDİ kez çağırıyor
               (`U.esc(String(perf.c_star_source))` gibi) ve ikisi
               `honestyBlock()` içindedir — o blok ana render yolundan
               KOŞULSUZ çağrılır (flow_panel.js render: `+ honestyBlock(
               flow)`). Yani ucun `c_star_source` ya da
               `inputs.wall_temperature_source` alanı dolu geldiği anda
               panel `U.esc is not a function` ile düşüyordu; dürüstlük
               rozetleri (itki çapraz denetimi, C* kaynağı, kullanılan
               cidar sıcaklığı) hiç çizilmiyordu.

               a1'in `cfd_panel.js` bulgusuyla AYNI SINIF kusur ('U is
               not defined'): panel bir yardımcıyı çağırıyor, güverte onu
               yayımlamıyor. Kapı açılıyor ve modülün KENDİ kaçıcısına
               bağlanıyor — ikinci bir kaçıcı YAZILMADI (doktrin 4). */
            esc: escAttr,
            warnText: warnText,
            // V3 KK 3. tur: ret gövdesinin okunur cümlesi (OH-GT-14 ile aynı
            // kural) — kendi POST'unu yapan paneller (belirsizlik) de
            // makine kodu yerine bunu basar. İkinci bir okuyucu yazılmaz.
            rejectText: ucRedMetni,
            purgePlots: purgePlots,
            fmt: fmt,
            pick: pick,
            kindColor: kindColor,
            // Kendi form DOM'unu kuran paneller (feed_panel gibi) ön dolumda
            // aynı anlamlı basamak kuralını kullansın diye dışa verilir.
            sigFig: dockSigFig,
            SIGFIG: DOCK_SIGFIG,
            TBL: TBL,
            TD: TD,
            // --- Çözücü sonucu okuma (merkezi birim çözümlemesi) ---
            // Paneller uzunlukları KENDİ BAŞINA çevirmez; bu yardımcılar
            // motor tipine göre ölçülmüş birim sözleşmesini uygular.
            motorDict: motorDict,
            readLengthM: readLengthM,
            readLengthMM: readLengthMM,
            readThrust: readThrust,
            readBurnTime: readBurnTime,
            readMassFlow: readMassFlow,
            readPropellantMass: readPropellantMass,
            readFuelFlow: readFuelFlow,
            readOfRatio: readOfRatio,
            readChamberMaterial: readChamberMaterial,
            readWallThicknessM: readWallThicknessM,
            readWallThicknessMM: readWallThicknessMM,
            // Cidarın KÜNYELİ okuması (Z5-C1): çıplak sayı yerine
            // "bu sayı kimin cidarı" beyanıyla birlikte döner.
            readWallThicknessProvenance: readWallThicknessProvenance,
            WALL_PROV_USER: WALL_PROV_USER,
            WALL_PROV_SOLVER: WALL_PROV_SOLVER,
            WALL_PROV_UNDECLARED: WALL_PROV_UNDECLARED,
            // Panelin bir alanı BİLEREK doldurmama sözleşmesi (Z5-C1):
            // `fromResults` sözlüğüne bu anahtarla {alan: gerekçe} konur.
            WITHHELD_KEY: WITHHELD_KEY,
            readWallTemperaturesK: readWallTemperaturesK,
            // Beyan taşıyan katlanmış bölümlerin sıfır-tıklama rozeti (Z5-C4)
            markDeclarationFolds: markDeclarationFolds,
        },
        // Test / hata ayıklama için salt-okunur kayıt listesi
        _registry: registry,
        // Test / hata ayıklama: init() tam bir DOM kurmadan motor tipini
        // ayarlamak için (bekçi testi üç motor tipini de aynı süreçte ölçer).
        _setMotorType: function (t) { cfg.motorType = t; },
    };
})();
