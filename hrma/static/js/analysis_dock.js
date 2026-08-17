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

    // ------------------------------------------------------------------
    // Ortak UI yardımcıları (paneller AnalysisDock.ui üzerinden kullanır)
    // ------------------------------------------------------------------
    const TBL = 'width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;';
    const TD = 'padding:6px 8px; border-bottom:1px solid var(--hd-line, rgba(0,229,255,0.14));';

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
        if (!w.code) return JSON.stringify(w);  // beklenmeyen biçim: görünür kıl
        if (depth > 4) return w.code;           // bozuk/döngüsel veri koruması
        var p = {};
        Object.keys(w.params || {}).forEach(function (k) {
            var v = w.params[k];
            p[k] = (v && typeof v === 'object') ? warnText(v, depth + 1) : v;
        });
        return TF(w.code, p, w.fallback || w.code);
    }

    // Uyarı / öneri kutusu (injector_panel uyarı bloğu deseni)
    function listBlock(title, items, kind) {
        if (!items || !items.length) return '';
        const c = kindColor(kind || 'warn');
        return `<div style="border:1px solid ${c}; border-radius:8px;
            padding:10px 14px; margin:10px 0; color:${c};">
            <strong>${title}</strong><ul style="margin:6px 0 0 18px;">` +
            items.map(w => `<li>${warnText(w)}</li>`).join('') + '</ul></div>';
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
    const SOURCE_COLORS = {           // motor_viz3d.js ile birebir aynı
        computed: '#39d6ec',
        user: '#e8edf2',
        assumed: '#ffb347',
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
        + '|varsay|öngör|tahmin|kabul edil|yerel üret|sınırlan|kırpıl', 'i');

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
        if (SRC_MISSING_RE.test(s)) return 'missing';
        if (SRC_USER_RE.test(s)) return 'user';
        if (SRC_ASSUMED_RE.test(s)) return 'assumed';
        return null;
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
        const basis = `<div style="color:var(--hd-ink-faint, #46606d); margin-top:4px;">${
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
            return `<div class="form-group">${lab}
                <select id="${domId}" data-field="${fid}">${opts}</select></div>`;
        }
        return `<div class="form-group">${lab}
            <input type="number" id="${domId}" data-field="${fid}" value="${defVal}" step="${step}"></div>`;
    }

    function panelSectionHtml(spec) {
        const fieldsHtml = (spec.fields || []).map(f => fieldHtml(spec.id, f)).join('');
        return `
        <div id="ad_sec_${spec.id}" style="border:1px solid var(--hd-line, rgba(0,229,255,0.14));
             border-radius:var(--hd-radius-sm, 8px); padding:12px 16px; margin:12px 0;">
            <h3 style="margin:0 0 8px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;">
                <span${i18nAttr(spec.titleKey)}>${T(spec.titleKey, spec.title)}</span>
                <span style="font-family:var(--hd-mono); font-size:0.68rem;
                      color:var(--hd-ink-faint, #46606d);">${spec.endpoint || ''}</span>
            </h3>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
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

    function tabButtonHtml(cat) {
        const key = 'dock.cat.' + cat;
        return `<button type="button" class="ad-tab" data-category="${cat}"
            style="font-family:var(--hd-mono); font-size:0.78rem; letter-spacing:0.08em;
            padding:7px 16px; cursor:pointer; border-radius:6px 6px 0 0;
            border:1px solid var(--hd-line, rgba(0,229,255,0.14)); border-bottom:none;
            background:transparent; color:var(--hd-ink-dim, #7d97a5);"
            data-i18n="${key}">${T(key, cat)}</button>`;
    }

    function dockHtml() {
        return `
        <div class="panel" id="analysisDock" style="width:100%; grid-column: 1 / -1;">
            <h2>&#9654; <span data-i18n="dock.title">${T('dock.title', 'Analysis Dock')}</span></h2>
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
            <div id="ad_tabs" style="display:flex; gap:6px; margin:14px 0 0; flex-wrap:wrap;"></div>
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
        tabs.appendChild(btn);

        pane = document.createElement('div');
        pane.id = 'ad_pane_' + cat;
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

    // ------------------------------------------------------------------
    // Öneri (fromResults) uygulama — kullanıcının elle değiştirdiği
    // alanlar (data-dirty) EZİLMEZ; POST her zaman formdan okunur.
    // ------------------------------------------------------------------
    function applySuggestions(spec) {
        // `applied`: ÖNERİSİ gerçekten alana yazılan alanlar. Kaynak çipi
        // (E3) buradan beslenir — tahmin değil, yapılan işin kaydı.
        const applied = {};
        if (!cfg.resultsProvider || !spec.fromResults) { paintFieldSources(spec, applied); return; }
        let r = null;
        try { r = cfg.resultsProvider(); } catch (e) { r = null; }
        if (!r) { paintFieldSources(spec, applied); return; }
        let sug = null;
        try { sug = spec.fromResults(r); } catch (e) { sug = null; }
        if (!sug) { paintFieldSources(spec, applied); return; }
        Object.keys(sug).forEach(function (k) {
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
                if (found) {
                    el.value = want;
                    applied[k] = true;
                } else if (window.console && console.warn) {
                    console.warn('[AnalysisDock] ' + spec.id + '.' + k
                        + ': çözücünün verdiği "' + want + '" seçeneği listede yok;'
                        + ' alan değiştirilmedi (görünen değer gönderilir).');
                }
                return;
            }
            // Anlamlı basamak: ham float değil (T66 + T45, gerekçe yukarıda)
            if (typeof v === 'number' && Number.isFinite(v)) {
                el.value = dockSigFig(v);
                applied[k] = true;
            }
        });
        paintFieldSources(spec, applied);
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

    function paintFieldSources(spec, applied) {
        (spec.fields || []).forEach(function (f) {
            const fid = f[0];
            const slot = document.getElementById(fieldSourceSlotId(spec.id, fid));
            if (!slot) return;
            const el = document.getElementById(fieldDomId(spec.id, fid));
            const kind = fieldSourceKind(el, fid, applied);
            slot.innerHTML = sourceChip({ kind: kind, declared: true },
                T(FIELD_SRC_NOTE_KEYS[kind], FIELD_SRC_NOTE_FALLBACK[kind]));
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(slot);
        });
    }

    // Alan elle değiştirilince o alanın çipi anında 'user'a döner.
    function repaintFieldSource(spec, fieldId) {
        const slot = document.getElementById(fieldSourceSlotId(spec.id, fieldId));
        if (!slot) return;
        const el = document.getElementById(fieldDomId(spec.id, fieldId));
        const kind = fieldSourceKind(el, fieldId, null);
        slot.innerHTML = sourceChip({ kind: kind, declared: true },
            T(FIELD_SRC_NOTE_KEYS[kind], FIELD_SRC_NOTE_FALLBACK[kind]));
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
    function requiredFieldInfo(spec) {
        const optional = {};
        const labels = {};
        (spec.fields || []).forEach(function (f) {
            const def = f[2];
            if (!(typeof def === 'number' && Number.isFinite(def))) {
                optional[f[0]] = true;
            }
            labels[f[0]] = T(f[4], f[1]);
        });
        return { optional: optional, labels: labels };
    }

    // {payload, missing} döner. `missing` boş değilse istek gönderilmemelidir.
    function buildPayload(spec) {
        applySuggestions(spec);
        const payload = {};
        const missing = [];
        const sec = document.getElementById('ad_sec_' + spec.id);
        if (!sec) return { payload: payload, missing: missing };
        const info = requiredFieldInfo(spec);
        sec.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') {
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
    // Çalıştırma
    // ------------------------------------------------------------------
    async function runPanel(spec) {
        const status = document.getElementById('ad_status_' + spec.id);
        const root = document.getElementById('ad_root_' + spec.id);
        const btn = document.getElementById('ad_run_' + spec.id);
        if (!status || !root || !btn) return;
        // Gövde ÖNCE kurulur: zorunlu alan boşsa uca hiç gidilmez (H3-B8).
        const built = buildPayload(spec);
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
        try {
            const resp = await fetch(spec.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(built.payload),
            });
            const data = await readJsonBody(resp);
            if (!resp.ok || data.status === 'error') {
                throw new Error(data.error || ('HTTP ' + resp.status));
            }
            purgePlots(root);           // eski grafiklerin resize dinleyicileri sızmasın
            root.innerHTML = '';
            lastData[spec.id] = data;          // dil değişiminde yeniden çizmek için sakla
            spec.render(data, root);
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
            root.style.display = 'block';
            status.textContent = '';
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
                repaintFieldSource(spec, fid);      // çip anında 'user'a döner
            });
            el.addEventListener('change', function () {
                el.dataset.dirty = '1';
                repaintFieldSource(spec, fid);
            });
        });
        // İlk montajda sonuçtan önerileri doldur (varsa)
        applySuggestions(spec);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(sec);
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
            badge: badge,
            statCard: statCard,
            kvTable: kvTable,
            sectionTitle: sectionTitle,
            listBlock: listBlock,
            warnText: warnText,
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
            readWallTemperaturesK: readWallTemperaturesK,
        },
        // Test / hata ayıklama için salt-okunur kayıt listesi
        _registry: registry,
        // Test / hata ayıklama: init() tam bir DOM kurmadan motor tipini
        // ayarlamak için (bekçi testi üç motor tipini de aynı süreçte ölçer).
        _setMotorType: function (t) { cfg.motorType = t; },
    };
})();
