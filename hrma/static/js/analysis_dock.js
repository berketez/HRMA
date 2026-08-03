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
        if (typeof w === 'string') return w;
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

    // ------------------------------------------------------------------
    // DOM yardımcıları
    // ------------------------------------------------------------------
    function fieldDomId(panelId, fieldId) {
        return 'ad_f_' + panelId + '_' + fieldId;
    }

    // Alan tanımı: [id, etiket, varsayılan, adım, etiketAnahtarı?]
    // 5. eleman verilirse etiket data-i18n taşır; dil değişince kendiliğinden çevrilir.
    // Seçenek listesi öğeleri de [değer, etiket, etiketAnahtarı?] olabilir.
    function fieldHtml(panelId, f) {
        const fid = f[0], label = f[1], defVal = f[2], step = f[3], labelKey = f[4];
        const domId = fieldDomId(panelId, fid);
        const lab = `<label${i18nAttr(labelKey)}>${T(labelKey, label)}</label>`;
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
            <div id="ad_tabs" style="display:flex; gap:6px; margin:14px 0 0; flex-wrap:wrap;"></div>
            <div id="ad_panes" style="border-top:1px solid var(--hd-line-strong, rgba(0,229,255,0.42));"></div>
        </div>`;
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
        Array.prototype.forEach.call(panes.children, function (p) {
            p.style.display = (p.id === 'ad_pane_' + cat) ? 'block' : 'none';
        });
        // Gizli sekmedeyken render edilen Plotly grafikleri 700px
        // varsayılanında kalır; pane görünür olunca gerçek genişliğe getir.
        if (window.Plotly && typeof Plotly.Plots !== 'undefined') {
            const shown = document.getElementById('ad_pane_' + cat);
            if (shown) {
                shown.querySelectorAll('.js-plotly-plot').forEach(function (p) {
                    try { Plotly.Plots.resize(p); } catch (e) { /* boş pane */ }
                });
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
        if (!cfg.resultsProvider || !spec.fromResults) return;
        let r = null;
        try { r = cfg.resultsProvider(); } catch (e) { r = null; }
        if (!r) return;
        let sug = null;
        try { sug = spec.fromResults(r); } catch (e) { sug = null; }
        if (!sug) return;
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
            }
        });
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
            el.addEventListener('input', function () { el.dataset.dirty = '1'; });
            el.addEventListener('change', function () { el.dataset.dirty = '1'; });
        });
        // İlk montajda sonuçtan önerileri doldur (varsa)
        applySuggestions(spec);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(sec);
    }

    // ------------------------------------------------------------------
    // Genel API
    // ------------------------------------------------------------------
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

        // Temel sekmeler her zaman kurulur; yeni kategoriler talep üzerine eklenir
        BASE_CATEGORIES.forEach(ensureCategory);
        registry.filter(panelApplies).forEach(mountPanel);
        selectCategory(activeCategory || BASE_CATEGORIES[0]);
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(dock);
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(rerenderAll);
    }

    function getMotorType() {
        return cfg.motorType || 'hybrid';
    }

    // Sonuç değiştiğinde entegrasyon katmanı çağırabilir: dirty olmayan
    // alanları en güncel sonuçla tazeler (opsiyonel kolaylık).
    function refreshSuggestions() {
        if (!inited) return;
        registry.filter(panelApplies).forEach(applySuggestions);
    }

    window.AnalysisDock = {
        init: init,
        register: register,
        getMotorType: getMotorType,
        refreshSuggestions: refreshSuggestions,
        selectCategory: selectCategory,
        ui: {
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
        },
        // Test / hata ayıklama için salt-okunur kayıt listesi
        _registry: registry,
        // Test / hata ayıklama: init() tam bir DOM kurmadan motor tipini
        // ayarlamak için (bekçi testi üç motor tipini de aynı süreçte ölçer).
        _setMotorType: function (t) { cfg.motorType = t; },
    };
})();
