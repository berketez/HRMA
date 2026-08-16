/* ====================================================================
   HRMA Analiz Merkezi (Analysis Center) — dalga B çerçevesi
   --------------------------------------------------------------------
   Tasarım belgesi: docs/mimari/analiz-merkezi-tasarimi.md (15 Ağu 2026).
   Workbench mantığı: ÜÇ SÜTUN + koşum geçmişi şeridi.

       ┌ BİLEŞEN AĞACI ─┬─ KOŞUM KARTI ──┬─ SONUÇ GÖRÜNTÜLEYİCİ ┐
       │ bileşen × analiz│ alanlar + [Çalıştır] │ kiracının render'ı │
       ├─ KOŞUM GEÇMİŞİ (oturum içi) ─────────────────────────────┤

   MEVCUT GÜVERTE (analysis_dock.js) YERİNDE KALIR. Merkez ayrı bir
   katmandır; tasarım §4 gereği paneller tek tek buraya TAŞINACAK, ama
   taşıma görsel tur denetimiyle doğrulanmadan eski yerinden kaldırılmaz.
   Bu dosya çerçevedir: bileşen ağacı, kayıt sözleşmesi, koşum kartı,
   görüntüleyici kabı ve geçmiş şeridi. İLK kiracı CFD panelidir
   (panels/cfd_panel.js — ayrı dosya, ayrı sahip).

   --------------------------------------------------------------------
   KURULUM SÖZLEŞMESİ (şablon tarafı — DEĞİŞTİRME)
   --------------------------------------------------------------------
     <script src="/static/js/analysis_center.js"></script>
     <script src="/static/js/panels/cfd_panel.js"></script>   <!-- kiracılar -->
     ...
     AnalysisCenter.init({
         anchorId: 'analysis-center-anchor',   // Merkez bu elemanın ÖNÜNE kurulur
         motorType: 'hybrid'|'liquid'|'solid',
         resultsProvider: function () { return window.currentResults; },
         hookNames: ['displayCalculationResults', 'displayResults'],
             // İsteğe bağlı. Bu adlardaki GLOBAL sonuç basıcıları sarılır;
             // her yeni hesaptan sonra Merkez kendini tazeler (fea_panel.js
             // ve thermal_fea_panel.js ile AYNI ölçülmüş desen).
     });

   Yükleme sırası: önce bu dosya, sonra kiracı panelleri (kiracı
   register çağırırken window.AnalysisCenter tanımlı olmalı).

   --------------------------------------------------------------------
   KİRACI KAYIT SÖZLEŞMESİ  (S4 ve sonraki taşımalar buna yazar)
   --------------------------------------------------------------------
     AnalysisCenter.register({
         componentId: 'nozzle_flow',      // §2 matrisindeki bileşen kimliği
         analysisId:  'cfd',              // §2 matrisindeki analiz kimliği
         title: 'CFD (Euler, shock capturing)',   // İngilizce yedek metin
         titleKey: 'ac.an.cfd',           // çeviri anahtarı (varsa)
         endpoint: '/api/cfd/nozzle',     // POST ucu
         motorTypes: ['hybrid', 'solid', 'liquid'],   // yoksa matris satırı geçerli

         // UYGULANABİLİRLİK — kural 1: uygulanamayan satır GİZLENMEZ, gri
         // gösterilir ve nedeni ADIYLA yazılır. Neden ya bir çeviri kaydı
         // ({key, fallback, params}) ya da düz metindir; boş bırakılamaz
         // (boş neden "beyansız" olarak işaretlenir, sessizce yutulmaz).
         // HER ÇİZİMDE çağrılır (ağaç yeniden basıldığında da): UCUZ ve
         // YAN ETKİSİZ olmalı — istek atmaz, DOM'a yazmaz. Fırlatırsa
         // satır gri kalır ve hata mesajı ekranda adlandırılır.
         applicability: function (currentResults) {
             return { ok: false,
                      reason: { key: 'panel.cfd.needsContour',
                                fallback: 'This result does not carry a nozzle contour.',
                                params: {} } };
         },

         // ALANLAR — güverte biçiminin AYNISI:
         //   [inputId, 'Label', varsayılan, adım|seçenekListesi, 'etiket.anahtarı']
         // Varsayılanı SONLU SAYI olan alan ZORUNLUDUR; boşsa istek hiç
         // gönderilmez (uydurma varsayılan konmaz — analysis_dock.js H3-B8).
         fields: [['grid_nx', 'Axial cells', 120, 1, 'panel.cfd.rowBudget']],
         //   (örnekteki anahtar SÖZLÜKTE VAR olmalı — ölü anahtarlı örnek
         //    kopyalanınca sızar; H1 hakem notu N-1, 16 Ağu 2026)

         // Alan ÖNERİLERİ: son hesap sonucundan doldurulur. Kullanıcının
         // elle değiştirdiği alan (data-dirty) BİR DAHA EZİLMEZ; POST
         // gövdesi HER ZAMAN formdan okunur.
         fromResults: function (currentResults) { return { grid_nx: 120 }; },

         // İsteğe bağlı: gövdeyi kiracı kurar. formValues DOM'dan okunmuş
         // gerçek alan değerleridir; kiracı bunlara sonuç sözlüğünden
         // BLOK ekleyebilir, ama sayı UYDURAMAZ (sahte veri yasağı).
         body: function (formValues, currentResults) { return formValues; },

         // Yanıtı çizer. rootEl Merkez'in görüntüleyici kabıdır.
         render: function (data, rootEl) { ... },

         // İsteğe bağlı HÜKÜM ROZETİ (kural 4): geçmiş şeridinde ve kartta
         // görünür. Beyan edilmezse rozet "hüküm beyan edilmedi" der —
         // uydurma "başarılı" rozeti BASILMAZ.
         verdict: function (data) {
             return { kind: 'ok'|'warn'|'err'|'info'|'dim',
                      key: 'panel.cfd.expectConverged', fallback: 'converged',
                      params: {} };
         },

         long: true|false,     // uzun sürebilecek analiz: koşum beyanı ona göre
     });

   --------------------------------------------------------------------
   SAHTE İLERLEME YASAĞI (tasarım kural 3 + ürün felsefesi)
   --------------------------------------------------------------------
   Bu dosyada zamanlayıcı YOKTUR: setInterval / setTimeout /
   requestAnimationFrame / Math.random hiçbir yerde çağrılmaz. Koşum
   sırasında ekranda YALNIZ gerçek durum beyanı ("koşuyor") ve devre dışı
   düğme vardır; yüzde çubuğu, sahte kalıntı akışı, dolan animasyon YOK.
   Bitişte gösterilen süre GERÇEKTEN ölçülür (Date.now farkı). Gerçek
   iterasyon akışı (SSE/poll) geldiğinde ilerleme O ZAMAN gösterilir.

   Bekçi: tests/test_analysis_center_contract.py
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // ------------------------------------------------------------------
    // i18n köprüsü — i18n.js yüklenmemişse İngilizce yedek metin döner
    // (analysis_dock.js ile birebir aynı köprü).
    // ------------------------------------------------------------------
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback == null ? key : fallback)
            .replace(/\{(\w+)\}/g, function (whole, name) {
                return (params && name in params) ? String(params[name]) : whole;
            });
    }
    // Sunucudan/kiracıdan gelen DÜZ METİN: sözlükte karşılığı varsa
    // çevrilir, yoksa AYNEN kalır (asla anahtar, asla boş).
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }
    function i18nAttr(key) {
        return key ? ' data-i18n="' + key + '"' : '';
    }
    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ------------------------------------------------------------------
    // Ortak biçim yardımcıları
    // ------------------------------------------------------------------
    // Ön dolum anlamlı basamağı TEK yerde tanımlıdır: analysis_dock.js
    // DOCK_SIGFIG (= 6, gerekçesi orada ölçümle yazılı). Güverte yüklüyse
    // oradan okunur; yüklü değilse aynı sayı yerel yedekle uygulanır —
    // iki kural birbirinden ayrışmasın diye kaynak burada adlandırıldı.
    const FALLBACK_SIGFIG = 6;      // = analysis_dock.js DOCK_SIGFIG

    function sigFig(value) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.sigFig === 'function') return U.sigFig(value);
        const v = Number(value);
        if (!isFinite(v) || v === 0) return v;
        const digits = (U && U.SIGFIG) || FALLBACK_SIGFIG;
        return Number(v.toPrecision(digits));
    }

    const COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };
    function kindColor(kind) {
        return COLORS[kind] || COLORS.info;
    }

    // Saat damgası — GERÇEK koşum anı (yerel saat, sabit biçim).
    function clockText(ts) {
        const d = new Date(ts);
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
    }

    // ==================================================================
    // §2 BİLEŞEN × ANALİZ MATRİSİ
    // ------------------------------------------------------------------
    // Kaynak: docs/mimari/analiz-merkezi-tasarimi.md §2 tablosu (v1).
    // Burada YALNIZ satırın kimliği, adı, motor kapsamı ve tasarımda
    // ADLANDIRILMIŞ uç yazılıdır — hesap yapan hiçbir şey yoktur.
    // Kiracısı OLMAYAN satır da görünür: gri durur ve nedeni yazılır
    // (kural 1: uygulanabilirlik beyanlıdır, satır gizlenmez).
    // Matris kataloğun boşluk analiziyle büyüyecek (§6).
    // ==================================================================
    const COMPONENTS = [
        { id: 'chamber_nozzle_wall', titleKey: 'ac.comp.wall',
          title: 'Chamber + nozzle wall' },
        { id: 'grain_section', titleKey: 'ac.comp.grain',
          title: 'Solid grain cross-section' },
        { id: 'nozzle_flow', titleKey: 'ac.comp.nozzleFlow',
          title: 'Nozzle internal flow' },
        { id: 'feed_structure', titleKey: 'ac.comp.feedStructure',
          title: 'Tank / bolted joint / line' },
        { id: 'chamber_acoustics', titleKey: 'ac.comp.acoustics',
          title: 'Chamber acoustics' },
    ];

    const MATRIX = [
        { componentId: 'chamber_nozzle_wall', analysisId: 'structural',
          titleKey: 'ac.an.structural',
          title: 'Structural (linear static, axisymmetric)',
          plannedEndpoint: '/api/fea/structural',
          motorTypes: ['hybrid', 'solid', 'liquid'] },
        { componentId: 'chamber_nozzle_wall', analysisId: 'thermal',
          titleKey: 'ac.an.thermal',
          title: 'Thermal (transient conduction, Bartz BC)',
          plannedEndpoint: '/api/fea/thermal',
          motorTypes: ['hybrid'] },
        { componentId: 'grain_section', analysisId: 'planar_grain',
          titleKey: 'ac.an.planarGrain',
          title: 'Plane strain (SP-8073 acceptance)',
          plannedEndpoint: '/api/fea/planar-grain',
          motorTypes: ['solid'] },
        { componentId: 'nozzle_flow', analysisId: 'cfd',
          titleKey: 'ac.an.cfd',
          title: 'CFD (Euler, shock capturing, p_w separation call)',
          plannedEndpoint: '/api/cfd/nozzle',
          motorTypes: ['hybrid', 'solid', 'liquid'] },
        { componentId: 'feed_structure', analysisId: 'module_cards',
          titleKey: 'ac.an.moduleCards',
          title: 'Module cards (pressure vessel / bolted joint / water hammer)',
          plannedEndpoint: '(existing analysis endpoints)',
          motorTypes: ['hybrid', 'solid', 'liquid'] },
        { componentId: 'chamber_acoustics', analysisId: 'acoustic_modes',
          titleKey: 'ac.an.acousticModes',
          title: 'Acoustic mode table',
          plannedEndpoint: 'acoustic_modes',
          motorTypes: ['hybrid', 'solid'] },
    ];

    const MOTOR_LABEL_KEYS = {
        hybrid: 'ac.motor.hybrid', solid: 'ac.motor.solid', liquid: 'ac.motor.liquid',
    };
    const MOTOR_LABEL_FALLBACK = {
        hybrid: 'hybrid', solid: 'solid', liquid: 'liquid',
    };

    // ------------------------------------------------------------------
    // Durum
    // ------------------------------------------------------------------
    let cfg = {};
    let inited = false;
    const registry = [];                 // kayıt sırası korunur
    const specByKey = {};                // 'componentId.analysisId' -> spec
    const matrixByKey = {};              // aynı anahtar -> matris satırı
    MATRIX.forEach(function (m) { matrixByKey[m.componentId + '.' + m.analysisId] = m; });

    let selection = null;                // {componentId, analysisId}
    let cardSignature = null;            // kart yalnız gerçekten değişince yeniden kurulur
    let statusState = null;              // {kind, text} — koşum durumu beyanı
    let busy = false;                    // koşum sürüyor mu (gerçek durum)
    const runHistory = [];               // oturum içi koşum geçmişi
    const lastEntryByRow = {};           // rowKey -> en son koşum kaydı
    let viewingEntryId = null;           // görüntüleyicide duran kayıt
    let entrySeq = 0;

    function rowKey(componentId, analysisId) {
        return componentId + '.' + analysisId;
    }
    function domKey(componentId, analysisId) {
        return (componentId + '_' + analysisId).replace(/[^\w]/g, '_');
    }
    function getMotorType() {
        return cfg.motorType || 'hybrid';
    }
    function motorLabel() {
        const m = getMotorType();
        return T(MOTOR_LABEL_KEYS[m] || '', MOTOR_LABEL_FALLBACK[m] || m);
    }
    function currentResults() {
        if (typeof cfg.resultsProvider !== 'function') return null;
        try { return cfg.resultsProvider(); } catch (e) { return null; }
    }

    // ==================================================================
    // MODEL — DOM'dan bağımsız (bekçi testleri bunu doğrudan koşturur)
    // ------------------------------------------------------------------
    // Her matris satırı üç durumdan birine düşer:
    //   ready   : kiracı var, motor tipi tutuyor, uygulanabilirlik olumlu
    //   blocked : kiracı var ama bugünkü sonuç/motor tipi taşımıyor
    //   absent  : bu analiz henüz Merkez'e taşınmadı (kiracı yok)
    // 'blocked' ve 'absent' satırlar GİZLENMEZ; gri durur, nedenleri yazılır.
    // ==================================================================
    function normalizeReason(reason) {
        if (reason == null || reason === '') {
            // Beyansız ret: kiracı "uygulanamaz" dedi ama nedenini
            // adlandırmadı. Bu da bir beyan eksikliğidir — yutulmaz.
            return { key: 'ac.reason.unnamed',
                     fallback: 'The analysis reported that it does not apply, '
                               + 'but named no reason.' };
        }
        if (typeof reason === 'string') return { text: reason };
        if (typeof reason === 'object') {
            if (reason.key || reason.fallback || reason.text) return reason;
        }
        return { text: String(reason) };
    }

    function reasonText(reason) {
        if (!reason) return '';
        if (reason.key) return TF(reason.key, reason.params || {}, reason.fallback || reason.key);
        return SRV(String(reason.text == null ? '' : reason.text));
    }

    function evaluateRow(matrixRow, spec, results) {
        const motorTypes = (spec && spec.motorTypes) || matrixRow.motorTypes || null;
        const title = (spec && spec.title) || matrixRow.title || matrixRow.analysisId;
        const titleKey = (spec && spec.titleKey) || matrixRow.titleKey || null;
        const row = {
            componentId: matrixRow.componentId,
            analysisId: matrixRow.analysisId,
            key: rowKey(matrixRow.componentId, matrixRow.analysisId),
            title: title,
            titleKey: titleKey,
            endpoint: (spec && spec.endpoint) || matrixRow.plannedEndpoint || '',
            endpointWired: !!(spec && spec.endpoint),
            motorTypes: motorTypes,
            extra: !!matrixRow.extra,
            spec: spec || null,
            state: 'ready',
            reason: null,
        };

        // 1) Motor tipi — matris kapsamı (kiracı verdiyse kiracının kapsamı)
        if (motorTypes && motorTypes.indexOf(getMotorType()) === -1) {
            row.state = 'blocked';
            row.reason = { key: 'ac.reason.motorType',
                           params: { motor: motorLabel() },
                           fallback: 'This analysis does not apply to a {motor} motor.' };
            return row;
        }
        // 2) Kiracı yok — analiz henüz Merkez'e taşınmadı
        if (!spec) {
            row.state = 'absent';
            row.reason = { key: 'ac.reason.notMoved',
                           fallback: 'This analysis has not been moved into the '
                                     + 'Analysis Center yet; it still runs in its own panel.' };
            return row;
        }
        // 3) Sayfada sonuç yok — Merkez sonucu OKUR, üretmez
        if (!results) {
            row.state = 'blocked';
            row.reason = { key: 'ac.reason.noResults',
                           fallback: 'No calculation result on this page yet — '
                                     + 'run the motor calculation first.' };
            return row;
        }
        // 4) Kiracının kendi uygulanabilirlik hükmü
        if (typeof spec.applicability === 'function') {
            let verdict = null;
            try {
                verdict = spec.applicability(results);
            } catch (e) {
                row.state = 'blocked';
                row.reason = { key: 'ac.reason.applicabilityError',
                               params: { message: (e && e.message) || String(e) },
                               fallback: 'The applicability check failed: {message}' };
                return row;
            }
            if (verdict && verdict.ok === false) {
                row.state = 'blocked';
                row.reason = normalizeReason(verdict.reason);
                return row;
            }
        }
        return row;
    }

    // Bileşen sırası: §2 matrisi + matris DIŞI kayıtlar (görünmez kalmasın).
    function buildModel(resultsArg) {
        const results = (resultsArg === undefined) ? currentResults() : resultsArg;
        const comps = [];
        const compIndex = {};
        COMPONENTS.forEach(function (c) {
            const entry = { id: c.id, title: c.title, titleKey: c.titleKey,
                            extra: false, rows: [] };
            compIndex[c.id] = entry;
            comps.push(entry);
        });

        MATRIX.forEach(function (m) {
            const spec = specByKey[m.componentId + '.' + m.analysisId] || null;
            const comp = compIndex[m.componentId];
            if (!comp) return;                    // matris/bileşen listesi tutarsız
            comp.rows.push(evaluateRow(m, spec, results));
        });

        // Matriste OLMAYAN kayıtlar: reddedilmez, "matris dışı" beyanıyla
        // eklenir — kaydolan bir analiz ekrandan sessizce düşmemeli.
        registry.forEach(function (spec) {
            const key = rowKey(spec.componentId, spec.analysisId);
            if (matrixByKey[key]) return;
            let comp = compIndex[spec.componentId];
            if (!comp) {
                comp = { id: spec.componentId,
                         title: spec.componentTitle || spec.componentId,
                         titleKey: spec.componentTitleKey || null,
                         extra: true, rows: [] };
                compIndex[spec.componentId] = comp;
                comps.push(comp);
            }
            const row = evaluateRow({ componentId: spec.componentId,
                                      analysisId: spec.analysisId,
                                      title: spec.title, titleKey: spec.titleKey,
                                      motorTypes: spec.motorTypes,
                                      plannedEndpoint: spec.endpoint,
                                      extra: true }, spec, results);
            comp.rows.push(row);
        });
        return comps;
    }

    function findRow(componentId, analysisId) {
        const comps = buildModel();
        for (let i = 0; i < comps.length; i++) {
            for (let j = 0; j < comps[i].rows.length; j++) {
                const r = comps[i].rows[j];
                if (r.componentId === componentId && r.analysisId === analysisId) return r;
            }
        }
        return null;
    }

    function selectedRow() {
        if (!selection) return null;
        return findRow(selection.componentId, selection.analysisId);
    }

    // ==================================================================
    // ALAN (form) katmanı — güverte deseninin uyarlaması
    // ------------------------------------------------------------------
    // * Öneriler (fromResults) yalnız DOKUNULMAMIŞ alanlara yazılır;
    //   kullanıcı bir alanı elle değiştirdiyse (data-dirty) bir daha ezilmez.
    // * POST gövdesi HER ZAMAN formdan okunur: ekranda görünen değer =
    //   gönderilen değer.
    // * Varsayılanı sonlu sayı olan alan ZORUNLUDUR; boşsa istek hiç
    //   gönderilmez (uydurma varsayılan konmaz).
    // ==================================================================
    function fieldDomId(row, fieldId) {
        return 'ac_f_' + domKey(row.componentId, row.analysisId) + '_' + fieldId;
    }

    function fieldHtml(row, f) {
        const fid = f[0], label = f[1], defVal = f[2], step = f[3], labelKey = f[4];
        const id = fieldDomId(row, fid);
        const lab = '<label for="' + id + '"' + i18nAttr(labelKey) + ' style="display:block;'
            + ' font-size:0.68rem; letter-spacing:0.06em; text-transform:uppercase;'
            + ' color:var(--hd-ink-dim, #7d97a5); font-family:var(--hd-mono, monospace);">'
            + esc(T(labelKey, label)) + '</label>';
        if (Array.isArray(step)) {
            const opts = step.map(function (o) {
                return '<option value="' + esc(o[0]) + '"'
                    + (o[0] === defVal ? ' selected' : '') + i18nAttr(o[2]) + '>'
                    + esc(T(o[2], o[1])) + '</option>';
            }).join('');
            return '<div class="ac-field" style="margin:6px 0;">' + lab
                + '<select id="' + id + '" data-field="' + esc(fid) + '"'
                + ' style="width:100%;">' + opts + '</select></div>';
        }
        return '<div class="ac-field" style="margin:6px 0;">' + lab
            + '<input type="number" id="' + id + '" data-field="' + esc(fid) + '"'
            + ' value="' + esc(defVal) + '" step="' + esc(step) + '" style="width:100%;">'
            + '</div>';
    }

    // fromResults ÖNERİLERİ — dokunulmuş alanlar korunur.
    function applySuggestions(row) {
        const spec = row && row.spec;
        if (!spec || typeof spec.fromResults !== 'function') return;
        const results = currentResults();
        if (!results) return;
        let sug = null;
        try { sug = spec.fromResults(results); } catch (e) { sug = null; }
        if (!sug) return;
        Object.keys(sug).forEach(function (k) {
            const el = document.getElementById(fieldDomId(row, k));
            if (!el || el.getAttribute('data-dirty') === '1') return;
            const v = sug[k];
            if (v == null) return;
            if (el.tagName === 'SELECT') {
                // Olmayan seçeneğe value atamak seçimi DÜŞÜRÜR (güverte
                // v2.6.26 bulgusu): seçenek yoksa alana DOKUNULMAZ.
                const want = String(v);
                const opts = el.options || [];
                let found = false;
                for (let i = 0; i < opts.length; i++) {
                    if (opts[i].value === want) { found = true; break; }
                }
                if (found) el.value = want;
                else if (window.console && console.warn) {
                    console.warn('[AnalysisCenter] ' + row.key + '.' + k + ': "' + want
                        + '" seçeneği listede yok; alan değiştirilmedi.');
                }
                return;
            }
            if (typeof v === 'number' && isFinite(v)) el.value = sigFig(v);
        });
    }

    function requiredInfo(spec) {
        const optional = {};
        const labels = {};
        (spec.fields || []).forEach(function (f) {
            if (!(typeof f[2] === 'number' && isFinite(f[2]))) optional[f[0]] = true;
            labels[f[0]] = T(f[4], f[1]);
        });
        return { optional: optional, labels: labels };
    }

    // {values, missing} — missing boş değilse istek GÖNDERİLMEZ.
    function readForm(row) {
        const spec = row.spec;
        const values = {};
        const missing = [];
        const info = requiredInfo(spec);
        (spec.fields || []).forEach(function (f) {
            const fid = f[0];
            const el = document.getElementById(fieldDomId(row, fid));
            if (!el) { if (!info.optional[fid]) missing.push(info.labels[fid] || fid); return; }
            if (el.tagName === 'SELECT') { values[fid] = el.value; return; }
            const v = parseFloat(el.value);
            if (isFinite(v)) { values[fid] = v; return; }
            if (!info.optional[fid]) missing.push(info.labels[fid] || fid);
        });
        return { values: values, missing: missing };
    }

    // ------------------------------------------------------------------
    // YANIT GÖVDESİ — Infinity/NaN taşıyan gövde JSON DEĞİLDİR; ham
    // ayrıştırıcı hatası yerine açık bir cümle üretilir (güverte H3-B9).
    // ------------------------------------------------------------------
    function readJsonBody(resp) {
        return resp.text().then(function (text) {
            try {
                return JSON.parse(text);
            } catch (e) {
                if (window.console && console.error) {
                    console.error('[AnalysisCenter] geçersiz JSON gövdesi (HTTP '
                        + resp.status + '):', text);
                }
                throw new Error(TF('ac.run.badJson', { status: resp.status },
                    'Server replied HTTP {status} but the body is not valid JSON '
                    + '(Infinity/NaN are not JSON values). Nothing was drawn; the '
                    + 'raw body is in the browser console.'));
            }
        });
    }

    // ==================================================================
    // GÖRÜNÜM
    // ==================================================================
    const PANEL_BORDER = '1px solid var(--hd-line, rgba(0,229,255,0.14))';
    const INSET = 'var(--hd-inset, rgba(6,14,26,0.85))';

    function badge(text, kind, titleAttr, key) {
        const c = kindColor(kind);
        return '<span data-ac-badge="' + esc(kind) + '" title="' + esc(titleAttr || '') + '"'
            + i18nAttr(key)
            + ' style="border:1px solid ' + c + '; color:' + c + '; border-radius:6px;'
            + ' padding:1px 8px; font-family:var(--hd-mono, monospace); font-size:0.66rem;'
            + ' letter-spacing:0.06em; white-space:nowrap; display:inline-block;">'
            + esc(text) + '</span>';
    }

    const STATE_BADGE = {
        ready: { kind: 'ok', key: 'ac.state.ready', fallback: 'READY' },
        blocked: { kind: 'dim', key: 'ac.state.blocked', fallback: 'NOT APPLICABLE' },
        absent: { kind: 'dim', key: 'ac.state.absent', fallback: 'NOT IN CENTER' },
    };

    function stateBadge(state) {
        const b = STATE_BADGE[state] || STATE_BADGE.absent;
        return badge(T(b.key, b.fallback), b.kind, '', b.key);
    }

    function centerHtml() {
        return '<div class="panel" id="analysisCenter" style="width:100%; grid-column: 1 / -1;">'
            + '<h2>&#9654; <span data-i18n="ac.title">' + esc(T('ac.title', 'Analysis Center'))
            + '</span></h2>'
            + '<div class="chart-explanation">'
            + '<strong data-i18n="common.whatItDoes">'
            + esc(T('common.whatItDoes', 'What it does:')) + '</strong> '
            + '<span data-i18n="ac.intro">' + esc(T('ac.intro',
                'Pick WHERE (component) and WHAT (analysis) you want to solve. Rows that '
                + 'do not apply to this motor or that are not in the Center yet stay '
                + 'visible in grey with the reason named. Inputs are pre-filled from the '
                + 'current result; the request is always built from the fields shown.'))
            + '</span></div>'
            + '<div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;'
            + ' margin:10px 0 0;">'
            + '<button type="button" id="ac_refresh" class="btn"'
            + ' data-i18n="ac.refresh" style="font-size:0.72rem; padding:4px 12px;">'
            + esc(T('ac.refresh', 'Reload from current result')) + '</button>'
            + '<span id="ac_motor" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"></span>'
            + '</div>'
            + '<div id="ac_columns" style="display:grid; gap:12px; margin-top:12px;'
            + ' grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));'
            + ' align-items:start;">'
            + column('ac_tree', 'ac.col.tree', 'Component tree')
            + column('ac_card', 'ac.col.card', 'Run card')
            + column('ac_view', 'ac.col.view', 'Result viewer')
            + '</div>'
            + '<div id="ac_history_box" style="border:' + PANEL_BORDER + '; border-radius:'
            + 'var(--hd-radius-sm, 8px); padding:10px 14px; margin-top:12px; background:'
            + INSET + ';">'
            + '<div style="font-family:var(--hd-mono, monospace); font-size:0.68rem;'
            + ' letter-spacing:0.08em; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="ac.history.title">'
            + esc(T('ac.history.title', 'RUN HISTORY (THIS SESSION)')) + '</div>'
            + '<div id="ac_history" style="display:flex; gap:8px; flex-wrap:wrap;'
            + ' margin-top:8px;"></div>'
            + '</div></div>';
    }

    function column(id, key, fallback) {
        return '<div style="border:' + PANEL_BORDER + '; border-radius:'
            + 'var(--hd-radius-sm, 8px); padding:10px 12px; background:' + INSET + ';">'
            + '<div style="font-family:var(--hd-mono, monospace); font-size:0.68rem;'
            + ' letter-spacing:0.08em; color:var(--hd-ink-dim, #7d97a5);'
            + ' margin-bottom:8px;"' + i18nAttr(key) + '>' + esc(T(key, fallback)) + '</div>'
            + '<div id="' + id + '"></div></div>';
    }

    // --- Sütun 1: bileşen ağacı ---------------------------------------
    function renderTree() {
        const host = document.getElementById('ac_tree');
        if (!host) return;
        const comps = buildModel();
        const html = comps.map(function (c) {
            const rows = c.rows.map(function (r) { return treeRowHtml(r); }).join('');
            return '<div class="ac-comp" data-ac-component="' + esc(c.id) + '"'
                + ' style="margin-bottom:10px;">'
                + '<div' + i18nAttr(c.titleKey) + ' style="font-size:0.8rem;'
                + ' color:var(--hd-ink-strong, #eaf7fb); margin-bottom:4px;">'
                + esc(T(c.titleKey, c.title)) + '</div>' + rows + '</div>';
        }).join('');
        host.innerHTML = html;
        comps.forEach(function (c) {
            c.rows.forEach(function (r) {
                const el = document.getElementById('ac_row_' + domKey(r.componentId, r.analysisId));
                if (el && el.addEventListener) {
                    el.addEventListener('click', function () {
                        select(r.componentId, r.analysisId);
                    });
                }
            });
        });
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
    }

    function treeRowHtml(row) {
        const on = !!(selection && selection.componentId === row.componentId
                      && selection.analysisId === row.analysisId);
        const grey = row.state !== 'ready';
        const reason = grey
            ? '<div data-ac-reason="' + esc(row.key) + '" style="font-size:0.68rem;'
              + ' color:var(--hd-ink-dim, #7d97a5); margin-top:3px;">'
              + esc(reasonText(row.reason)) + '</div>'
            : '';
        const extra = row.extra
            ? '<div style="font-size:0.66rem; color:var(--hd-ink-faint, #46606d);"'
              + ' data-i18n="ac.matrix.extra">'
              + esc(T('ac.matrix.extra',
                      'Registered outside the design §2 matrix.')) + '</div>'
            : '';
        return '<button type="button" class="ac-row"'
            + ' id="ac_row_' + domKey(row.componentId, row.analysisId) + '"'
            + ' data-ac-row="' + esc(row.key) + '" data-ac-state="' + esc(row.state) + '"'
            + ' aria-pressed="' + (on ? 'true' : 'false') + '"'
            + ' style="display:block; width:100%; text-align:left; cursor:pointer;'
            + ' margin:3px 0; padding:6px 8px; border-radius:6px; border:'
            + (on ? '1px solid var(--hd-line-strong, rgba(0,229,255,0.42))' : PANEL_BORDER)
            + '; background:' + (on ? 'rgba(0, 229, 255, 0.10)' : 'transparent')
            + '; color:' + (grey ? 'var(--hd-ink-dim, #7d97a5)'
                                 : 'var(--hd-ink, #cfe8f2)') + ';">'
            + '<div style="display:flex; gap:8px; align-items:baseline;'
            + ' justify-content:space-between;">'
            + '<span' + i18nAttr(row.titleKey) + ' style="font-size:0.76rem;">'
            + esc(T(row.titleKey, row.title)) + '</span>'
            + stateBadge(row.state) + '</div>' + reason + extra + '</button>';
    }

    // --- Sütun 2: koşum kartı -----------------------------------------
    // Kart YALNIZ imza değişince yeniden kurulur: yeniden kurmak form
    // alanlarını sıfırlar ve kullanıcının yazdığını siler (güverte dersi).
    function cardSignatureOf(row) {
        if (!row) return 'none';
        return row.key + '|' + row.state;
    }

    function renderCard(force) {
        const host = document.getElementById('ac_card');
        if (!host) return;
        const row = selectedRow();
        const sig = cardSignatureOf(row);
        if (!force && sig === cardSignature) { renderStatus(); return; }
        cardSignature = sig;

        if (!row) {
            host.innerHTML = '<p data-i18n="ac.select.hint" style="font-size:0.74rem;'
                + ' color:var(--hd-ink-dim, #7d97a5);">'
                + esc(T('ac.select.hint',
                        'Select a component × analysis row on the left.')) + '</p>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }

        const head = '<div style="font-size:0.8rem; color:var(--hd-ink-strong, #eaf7fb);'
            + ' margin-bottom:4px;"' + i18nAttr(row.titleKey) + '>'
            + esc(T(row.titleKey, row.title)) + '</div>'
            + '<div style="font-family:var(--hd-mono, monospace); font-size:0.66rem;'
            + ' color:var(--hd-ink-faint, #46606d); margin-bottom:8px;">'
            + esc(row.endpoint)
            + (row.endpointWired ? '' : ' <span' + i18nAttr('ac.endpoint.planned') + '>'
                + esc(T('ac.endpoint.planned', '(declared in the design, not wired here)'))
                + '</span>')
            + '</div>';

        if (row.state !== 'ready') {
            host.innerHTML = head + stateBadge(row.state)
                + '<p data-ac-card-reason="' + esc(row.key) + '" style="font-size:0.74rem;'
                + ' color:var(--hd-ink-dim, #7d97a5); margin-top:8px;">'
                + esc(reasonText(row.reason)) + '</p>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }

        const fields = (row.spec.fields || []).map(function (f) {
            return fieldHtml(row, f);
        }).join('');
        host.innerHTML = head + fields
            + '<button type="button" class="btn" id="ac_run" style="margin-top:8px;"'
            + ' data-i18n="ac.run.button">' + esc(T('ac.run.button', 'Run')) + '</button>'
            + '<div id="ac_status" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.7rem; margin-top:8px; overflow-wrap:anywhere;"></div>';

        (row.spec.fields || []).forEach(function (f) {
            const el = document.getElementById(fieldDomId(row, f[0]));
            if (!el || !el.addEventListener) return;
            // Elle değiştirilen alan bir daha ÖNERİYLE ezilmez.
            el.addEventListener('input', function () { el.setAttribute('data-dirty', '1'); });
            el.addEventListener('change', function () { el.setAttribute('data-dirty', '1'); });
        });
        const btn = document.getElementById('ac_run');
        if (btn && btn.addEventListener) btn.addEventListener('click', function () { run(); });
        applySuggestions(row);
        renderStatus();
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
    }

    // Koşum durumu: GERÇEK durum beyanı. Yüzde yok, zamanlayıcı yok.
    function renderStatus() {
        const el = document.getElementById('ac_status');
        const btn = document.getElementById('ac_run');
        if (btn) btn.disabled = !!busy;
        if (!el) return;
        if (!statusState) { el.textContent = ''; el.style.color = ''; return; }
        el.textContent = statusState.text;
        el.style.color = kindColor(statusState.kind || 'dim');
    }

    // --- Sütun 3: sonuç görüntüleyici ----------------------------------
    function viewingEntry() {
        if (viewingEntryId != null) {
            for (let i = 0; i < runHistory.length; i++) {
                if (runHistory[i].id === viewingEntryId) return runHistory[i];
            }
        }
        if (!selection) return null;
        return lastEntryByRow[rowKey(selection.componentId, selection.analysisId)] || null;
    }

    function renderViewer() {
        const host = document.getElementById('ac_view');
        if (!host) return;
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.purgePlots === 'function') U.purgePlots(host);
        const entry = viewingEntry();

        if (!entry) {
            host.innerHTML = '<p data-i18n="ac.view.empty" style="font-size:0.74rem;'
                + ' color:var(--hd-ink-dim, #7d97a5);">'
                + esc(T('ac.view.empty',
                        'No run yet for this component × analysis.')) + '</p>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }

        const stale = lastEntryByRow[entry.rowKey] !== entry;
        const staleNote = stale
            ? '<p data-i18n="ac.history.stale" style="font-size:0.7rem;'
              + ' color:var(--hd-orange, #ff8c33);">'
              + esc(T('ac.history.stale',
                      'Shown from the run history — this is a stored result, '
                      + 'not a fresh run.')) + '</p>'
            : '';
        const head = '<div style="display:flex; gap:8px; align-items:baseline;'
            + ' flex-wrap:wrap; margin-bottom:6px;">'
            + '<span style="font-family:var(--hd-mono, monospace); font-size:0.7rem;'
            + ' color:var(--hd-ink-dim, #7d97a5);">' + esc(clockText(entry.at)) + '</span>'
            + verdictBadge(entry) + '</div>' + staleNote;

        if (!entry.ok) {
            host.innerHTML = head + '<p data-ac-error="1" style="font-size:0.74rem;'
                + ' color:var(--hd-red, #ff5d73); overflow-wrap:anywhere;">'
                + esc(SRV(entry.errorText || '')) + '</p>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }

        const spec = specByKey[entry.rowKey];
        if (!spec || typeof spec.render !== 'function') {
            host.innerHTML = head + '<p data-i18n="ac.view.noRenderer"'
                + ' style="font-size:0.74rem; color:var(--hd-ink-dim, #7d97a5);">'
                + esc(T('ac.view.noRenderer',
                        'This analysis is registered without a result view.')) + '</p>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }
        host.innerHTML = head + '<div id="ac_view_root"></div>';
        const root = document.getElementById('ac_view_root');
        try {
            spec.render(entry.data, root);
        } catch (e) {
            if (window.console && console.error) {
                console.error('[AnalysisCenter] kiracı çizimi başarısız:', entry.rowKey, e);
            }
            if (root) {
                root.innerHTML = '<p style="color:var(--hd-red, #ff5d73);'
                    + ' font-size:0.74rem;">'
                    + esc(TF('ac.view.renderFailed', { message: (e && e.message) || String(e) },
                             'The result view failed: {message}')) + '</p>';
            }
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
    }

    // Hüküm rozeti: kiracı beyan etmezse "beyan edilmedi" der — uydurma
    // "başarılı" rozeti BASILMAZ (kural 4).
    function verdictBadge(entry) {
        if (!entry.ok) {
            return badge(T('ac.verdict.failed', 'RUN FAILED'), 'err', '', 'ac.verdict.failed');
        }
        const v = entry.verdict;
        if (!v) {
            return badge(T('ac.verdict.undeclared', 'NO VERDICT DECLARED'), 'dim',
                         T('ac.verdict.undeclaredTip',
                           'This analysis declares no acceptance verdict; read the '
                           + 'numbers and the not-modelled list below.'),
                         'ac.verdict.undeclared');
        }
        const text = v.key ? TF(v.key, v.params || {}, v.fallback || v.key)
                           : SRV(String(v.text == null ? v.fallback || '' : v.text));
        return badge(text, v.kind || 'info', '', v.key || '');
    }

    // --- Koşum geçmişi şeridi ------------------------------------------
    function renderHistory() {
        const host = document.getElementById('ac_history');
        if (!host) return;
        if (!runHistory.length) {
            host.innerHTML = '<span data-i18n="ac.history.empty" style="font-size:0.72rem;'
                + ' color:var(--hd-ink-dim, #7d97a5);">'
                + esc(T('ac.history.empty', 'No runs in this session yet.')) + '</span>';
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
            return;
        }
        // En yeni koşum başta
        const items = runHistory.slice().reverse().map(function (e) {
            const on = (viewingEntry() === e);
            return '<button type="button" id="ac_hist_' + e.id + '"'
                + ' data-ac-history="' + e.id + '" data-ac-history-row="' + esc(e.rowKey) + '"'
                + ' title="' + esc(TF('ac.history.replay', { seconds: e.seconds },
                    'Click to show this stored result again (run took {seconds} s).')) + '"'
                + ' style="cursor:pointer; border-radius:6px; padding:4px 10px;'
                + ' font-family:var(--hd-mono, monospace); font-size:0.68rem;'
                + ' text-align:left; border:'
                + (on ? '1px solid var(--hd-line-strong, rgba(0,229,255,0.42))' : PANEL_BORDER)
                + '; background:' + (on ? 'rgba(0, 229, 255, 0.10)' : 'transparent')
                + '; color:var(--hd-ink, #cfe8f2);">'
                + esc(clockText(e.at)) + ' · '
                + esc(T(e.componentTitleKey, e.componentTitle)) + ' · '
                + esc(T(e.titleKey, e.title)) + ' ' + verdictBadge(e) + '</button>';
        }).join('');
        host.innerHTML = items;
        runHistory.forEach(function (e) {
            const el = document.getElementById('ac_hist_' + e.id);
            if (el && el.addEventListener) {
                el.addEventListener('click', function () { showHistoryEntry(e.id); });
            }
        });
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(host);
    }

    function renderMotorLine() {
        const el = document.getElementById('ac_motor');
        if (!el) return;
        el.textContent = TF('ac.motorLine', { motor: motorLabel() },
                            'Motor context: {motor}');
    }

    function render() {
        renderMotorLine();
        renderTree();
        renderCard(false);
        renderViewer();
        renderHistory();
    }

    // ==================================================================
    // Kullanıcı eylemleri
    // ==================================================================
    function select(componentId, analysisId) {
        selection = { componentId: componentId, analysisId: analysisId };
        // Seçim değişince görüntüleyici o satırın SON koşumuna döner.
        viewingEntryId = null;
        statusState = null;
        renderTree();
        renderCard(false);
        renderViewer();
        renderHistory();
    }

    function showHistoryEntry(id) {
        viewingEntryId = id;
        for (let i = 0; i < runHistory.length; i++) {
            if (runHistory[i].id === id) {
                const e = runHistory[i];
                selection = { componentId: e.componentId, analysisId: e.analysisId };
                break;
            }
        }
        renderTree();
        renderCard(false);
        renderViewer();
        renderHistory();
    }

    function pushEntry(row, payload) {
        entrySeq += 1;
        const comp = componentOf(row.componentId);
        const entry = {
            id: entrySeq,
            rowKey: row.key,
            componentId: row.componentId,
            analysisId: row.analysisId,
            componentTitle: comp.title,
            componentTitleKey: comp.titleKey,
            title: row.title,
            titleKey: row.titleKey,
            at: payload.at,
            seconds: payload.seconds,
            ok: payload.ok,
            data: payload.data || null,
            errorText: payload.errorText || null,
            verdict: payload.verdict || null,
        };
        runHistory.push(entry);
        lastEntryByRow[row.key] = entry;
        viewingEntryId = entry.id;
        return entry;
    }

    function componentOf(componentId) {
        for (let i = 0; i < COMPONENTS.length; i++) {
            if (COMPONENTS[i].id === componentId) return COMPONENTS[i];
        }
        return { id: componentId, title: componentId, titleKey: null };
    }

    // Koşum. Süre GERÇEKTEN ölçülür; ilerleme UYDURULMAZ.
    function run() {
        const row = selectedRow();
        if (!row || row.state !== 'ready' || !row.spec) return Promise.resolve(null);
        if (busy) return Promise.resolve(null);
        const spec = row.spec;
        const form = readForm(row);
        if (form.missing.length) {
            statusState = { kind: 'warn',
                text: TF('ac.run.missingFields', { fields: form.missing.join(', ') },
                    'Required fields are empty: {fields}. The request was NOT sent — '
                    + 'a blank field is not a value.') };
            renderStatus();
            return Promise.resolve(null);
        }

        let body = form.values;
        if (typeof spec.body === 'function') {
            try {
                body = spec.body(form.values, currentResults());
            } catch (e) {
                statusState = { kind: 'err',
                    text: TF('ac.run.error', { message: (e && e.message) || String(e) },
                             'ERROR: {message}') };
                renderStatus();
                return Promise.resolve(null);
            }
        }

        busy = true;
        statusState = { kind: 'info',
            text: spec.long ? T('ac.run.runningLong',
                                'RUNNING — this analysis may take a while…')
                            : T('ac.run.running', 'RUNNING…') };
        renderStatus();

        const t0 = Date.now();
        return fetch(spec.endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(function (resp) {
            return readJsonBody(resp).then(function (data) {
                if (!resp.ok || (data && data.status === 'error')) {
                    throw new Error((data && data.error) || ('HTTP ' + resp.status));
                }
                return data;
            });
        }).then(function (data) {
            const seconds = Number(((Date.now() - t0) / 1000).toFixed(1));
            let verdict = null;
            if (typeof spec.verdict === 'function') {
                try { verdict = spec.verdict(data); } catch (e) { verdict = null; }
            }
            pushEntry(row, { at: Date.now(), seconds: seconds, ok: true,
                             data: data, verdict: verdict });
            busy = false;
            statusState = { kind: 'ok',
                text: TF('ac.run.done', { seconds: seconds },
                         'Completed in {seconds} s.') };
            renderStatus();
            renderViewer();
            renderHistory();
            return data;
        }).catch(function (err) {
            const seconds = Number(((Date.now() - t0) / 1000).toFixed(1));
            const message = (err && err.message) || String(err);
            pushEntry(row, { at: Date.now(), seconds: seconds, ok: false,
                             errorText: message });
            busy = false;
            statusState = { kind: 'err',
                text: TF('ac.run.error', { message: message }, 'ERROR: {message}') };
            renderStatus();
            renderViewer();
            renderHistory();
            return null;
        });
    }

    // Yeni hesap sonucu geldiğinde: uygulanabilirlik yeniden ölçülür,
    // dokunulmamış alanlar tazelenir. ESKİ KOŞUM SİLİNMEZ ama geçmişten
    // geldiği açıkça yazılıdır (renderViewer 'ac.history.stale').
    function refresh() {
        if (!inited) return;
        const row = selectedRow();
        renderMotorLine();
        renderTree();
        renderCard(false);
        if (row && row.state === 'ready') applySuggestions(row);
        renderViewer();
        renderHistory();
    }

    // ==================================================================
    // Kayıt + kurulum
    // ==================================================================
    function register(spec) {
        if (!spec || !spec.componentId || !spec.analysisId || !spec.endpoint
                || typeof spec.render !== 'function') {
            if (window.console && console.warn) {
                console.warn('[AnalysisCenter] register: eksik sözleşme alanı', spec);
            }
            return false;
        }
        const key = rowKey(spec.componentId, spec.analysisId);
        if (specByKey[key]) {
            if (window.console && console.warn) {
                console.warn('[AnalysisCenter] register: aynı bileşen×analiz iki kez', key);
            }
            return false;
        }
        if (!matrixByKey[key] && window.console && console.warn) {
            console.warn('[AnalysisCenter] register: "' + key + '" tasarım §2 matrisinde'
                + ' yok; satır "matris dışı" beyanıyla gösterilecek.');
        }
        specByKey[key] = spec;
        registry.push(spec);
        if (inited) render();
        return true;
    }

    function init(options) {
        if (inited) return;
        cfg = options || {};
        cfg.motorType = cfg.motorType || 'hybrid';

        const anchor = cfg.anchorId ? document.getElementById(cfg.anchorId) : null;
        const host = document.createElement('div');
        host.innerHTML = centerHtml();
        const panel = host.firstElementChild || document.getElementById('analysisCenter');
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid')
                || document.querySelector('.container')
                || document.body).appendChild(panel);
        }
        inited = true;

        const refreshBtn = document.getElementById('ac_refresh');
        if (refreshBtn && refreshBtn.addEventListener) {
            refreshBtn.addEventListener('click', function () { refresh(); });
        }

        // Hesap köprüsü — fea_panel.js / thermal_fea_panel.js ile AYNI
        // ölçülmüş desen: sayfanın sonuç basıcısı sarılır, özgün işlev her
        // koşulda çalışır, Merkez hatası hesabı engellemez.
        const hooks = cfg.hookNames || ['displayCalculationResults', 'displayResults'];
        hooks.forEach(function (name) {
            const original = window[name];
            if (typeof original !== 'function') return;
            window[name] = function () {
                const out = original.apply(this, arguments);
                try {
                    refresh();
                } catch (e) {
                    if (window.console && console.error) {
                        console.error('[AnalysisCenter] refresh failed:', e);
                    }
                }
                return out;
            };
        });

        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                // Dil değişince kart YENİDEN KURULUR: etiketler data-i18n
                // taşıdığı için I18N.apply zaten çevirir, ama kartın kendi
                // metinleri (neden/uç notu) burada tazelenir. Alanlar
                // korunur: kart imzası değişmediyse kutular yeniden kurulmaz.
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        render();
    }

    window.AnalysisCenter = {
        init: init,
        register: register,
        refresh: refresh,
        select: select,
        run: run,
        showHistoryEntry: showHistoryEntry,
        getMotorType: getMotorType,
        getSelection: function () { return selection ? {
            componentId: selection.componentId, analysisId: selection.analysisId } : null; },
        history: function () { return runHistory.slice(); },
        // --- Test / hata ayıklama (DOM'suz koşulabilir model katmanı) ---
        _model: buildModel,
        _registry: registry,
        _matrix: MATRIX.slice(),
        _components: COMPONENTS.slice(),
        _reasonText: reasonText,
        // Alan DOM kimliği — bekçi testi alanı adıyla bulabilsin diye
        // üçlü imzayla verilir (içeride satır nesnesiyle çalışılır).
        _fieldDomId: function (componentId, analysisId, fieldId) {
            return fieldDomId({ componentId: componentId, analysisId: analysisId },
                              fieldId);
        },
        _setMotorType: function (t) { cfg.motorType = t; },
        _setResultsProvider: function (fn) { cfg.resultsProvider = fn; },
    };
})();
