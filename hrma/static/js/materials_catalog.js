/* ====================================================================
   HRMA — Merkezi Malzeme Kataloğu (istemci tarafı, v2.5.2)
   --------------------------------------------------------------------
   GET /api/materials sözleşmesi:
     { ok: true,
       materials: { key: { name, source, tags: [...], ...tüm alanlar } },
       aliases:   { alias: canonical_key } }

   Kullanım (paneller):
     if (typeof window.HRMAMaterials !== 'undefined') {
         window.HRMAMaterials.populateSelect({
             panelId: 'structural', fieldId: 'material',
             tags: ['structural'], fallback: MATERIALS,
         });
     }
   Fetch başarısız olursa load() null döner ve paneller kendi hardcoded
   fallback listeleriyle çalışmaya devam eder (script yüklenmemişse de
   typeof guard sayesinde davranış aynıdır).
   Yüklenme sırası: panel dosyalarından ÖNCE (index.html — ana entegrasyon).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    var _promise = null;   // tek seferlik fetch cache'i
    var _catalog = null;   // { materials: {...}, aliases: {...} } | null

    // Katalog tek sefer çekilir; hata → null (paneller fallback'e düşer).
    function load() {
        if (_promise) return _promise;
        _promise = fetch('/api/materials')
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (!data || data.ok !== true || !data.materials) return null;
                _catalog = {
                    materials: data.materials,
                    aliases: data.aliases || {},
                    // ÖH D24 / OH-D23-03: sunucunun ilan ettiği varsayılan.
                    defaultStructuralMaterial:
                        data.default_structural_material || null,
                };
                return _catalog;
            })
            .catch(function () { return null; });
        return _promise;
    }

    // Alias'ı kanonik anahtara çözer; bilinmeyen ad → null.
    function resolve(key) {
        if (!_catalog) return null;
        var k = String(key || '').toLowerCase();
        if (_catalog.materials[k]) return k;
        var t = _catalog.aliases[k];
        return (t && _catalog.materials[t]) ? t : null;
    }

    // Kayıt döndürür (alias çözümlü); katalog yok / bilinmeyen → null.
    function get(key) {
        var k = resolve(key);
        return k ? _catalog.materials[k] : null;
    }

    // tag: string | string[] | null (null → tüm kayıtlar).
    // Dönen: [{ key, name, tags, ... }] alfabetik.
    function list(tag) {
        if (!_catalog) return [];
        var tags = Array.isArray(tag) ? tag : (tag ? [tag] : null);
        var out = [];
        Object.keys(_catalog.materials).sort().forEach(function (key) {
            var m = _catalog.materials[key];
            var mtags = m.tags || [];
            var match = !tags || tags.some(function (t) {
                return mtags.indexOf(t) !== -1;
            });
            if (match) {
                var item = { key: key };
                Object.keys(m).forEach(function (f) { item[f] = m[f]; });
                out.push(item);
            }
        });
        return out;
    }

    /* ÖH D37 A1c panel-dil · dil-sozluk Devir 1 — KATALOG SEÇENEK ADLARI
       SÖZLÜKTEN.

       ÖLÇÜLDÜ (docs/scofield/raw/OH/A1c/panel-dil/a1/once/tarayici.json,
       katı sayfası, 1440 px, örnek proje + hesap; once/olcum.json 10 çağrı):
       populateSelect seçenekleri veritabanı adıyla (materials_db.py `name`,
       İngilizce: 'AISI 4130 low-alloy steel (normalized)', 'Carbon steel
       (generic, A36-class)') yeniden kuruyor ve panelin anahtarını (o[2])
       düşürüyordu. TR ekranda katalog seçicilerinde 137 İngilizce seçenek,
       73 seçenek 21 karakter bütçesinin üstünde (200 px kutuda seçili metin
       277-319 px), üç koruma seçicisinde kurulum ipucu yeniden kurulumdan
       sonra eski seçenekte kalıyordu.

       Etiket sırası (değer HİÇ değişmez; yalnız görünen metin + data-i18n):
         1) panelin KENDİ anahtarlı etiketi (aynı değer) ya da panelin takma
            ad değeri için kendi etiketi (değer panelin anahtarıdır, etiketi
            onu anlatır — ör. 'silica_phenolic' → 'Silica-phenolic');
         2) CATALOG_LABELS: malzeme kimliği → kısa EN ad + sözlük anahtarı
            (EN metni sözlüğün EN metniyle BİREBİR; anahtarsız satır dile
            bağlı olmayan alaşım kodu — 'Inconel 718', 'CuCrZr (C18150)');
         3) panelin anahtarsız etiketi;
         4) veritabanı adı (tabloda olmayan YENİ kayıt: uydurma çeviri
            yazılmaz; bekçi tabloyu gerçek /api/materials ile eşitler —
            tests/test_d37_panel_dil_a1.py).
       Kısa adlar ≤ 21 karakter (A1a dil-sozluk ölçümü: 14 px eş aralıklı
       yazı, 177 px). Durum (normalized/aged/annealed) künyesi seçicide
       yazılmaz. Veritabanı adını güvenlik sonuç paneli uç `material_name`
       alanından AYNEN basar (safety_panel.js addRow 'material_name');
       yapısal sonuç paneli ise yalnız malzeme ANAHTARINI büyük harfle
       basar (structural_panel.js 'MATERIAL: …' rozeti) — orada veritabanı
       adı ve durum künyesi görünmez (denetçi Ş3). Öteki panellerin
       material_name rozetleri bu kulvarda ölçülmedi. */
    var CATALOG_LABELS = {
        ablative: ['Ablative liner', 'mat.ablativeLiner'],
        al_2024_t3: ['Aluminum 2024-T3', 'mat.aluminum2024'],
        al_7075_t6: ['Aluminum 7075-T6', 'mat.aluminum7075'],
        aluminum_6061: ['Aluminum 6061-T6', 'mat.aluminum6061'],
        beryllium_copper_c17200: ['BeCu C17200', null],
        brass_c360: ['Brass C36000', 'mat.brassC36000'],
        carbon_carbon: ['Carbon-carbon (C-C)', 'tps.carbonCarbon'],
        copper: ['Copper (OFHC)', 'mat.copperOfhc'],
        cucrzr: ['CuCrZr (C18150)', null],
        graphite: ['Graphite', 'mat.graphite'],
        inconel_625: ['Inconel 625', null],
        inconel_718: ['Inconel 718', null],
        magnesium_az31b: ['Magnesium AZ31B', 'mat.magnesiumAz31b'],
        molybdenum_tzm: ['Molybdenum TZM', 'mat.molybdenumTzm'],
        niobium_c103: ['Nb C-103 (silicide)', 'tps.niobium'],
        ss_17_4ph: ['17-4PH (H900)', null],
        ss_304: ['Stainless 304', 'mat.stainless304'],
        ss_316: ['Stainless 316', 'mat.stainless316'],
        steel: ['Carbon steel (A36)', 'mat.carbonSteelA36'],
        steel_4130: ['Steel AISI 4130', 'mat.steelAisi4130'],
        steel_4340: ['Steel AISI 4340', 'mat.steelAisi4340'],
        ti_grade2_cp: ['Titanium CP Grade 2', 'mat.titaniumGrade2'],
        titanium_6al4v: ['Titanium Ti-6Al-4V', 'mat.titanium6al4v'],
        tungsten: ['Tungsten', 'mat.tungsten'],
    };

    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }

    function escHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // [değer, görünen EN metin, sözlük anahtarı?] — anahtarsız satır iki
    // öğeli kalır (güvertenin fieldHtml'i eski biçimi okur).
    function labelRow(value, dbName, panelRows) {
        var p = panelRows[value];
        var canon = resolve(value) || value;
        if (p && (p[2] || canon !== value)) {
            return p[2] ? [value, p[1], p[2]] : [value, p[1]];
        }
        var c = CATALOG_LABELS[canon];
        if (c) return c[1] ? [value, c[0], c[1]] : [value, c[0]];
        if (p) return [value, p[1]];
        return [value, dbName];
    }

    // Seçili seçeneğin görünen metni ipucuna, anahtarı data-i18n-title'a —
    // güvertenin secimIpucu sözleşmesiyle aynı (analysis_dock.js; dil
    // değişince güverte secimIpuclariniTazele ile tazeler). Yeniden kurulum
    // güvertenin kanalında olmadığı için burada yazılır (üzerine gelmeden
    // de doğru olsun). Seçili seçenek yoksa ikisi de SİLİNİR.
    function refreshTitle(el) {
        var o = el.options ? el.options[el.selectedIndex] : null;
        var metin = (o && typeof o.textContent === 'string') ? o.textContent.trim() : '';
        var anahtar = (o && o.getAttribute) ? o.getAttribute('data-i18n') : null;
        if (anahtar) el.setAttribute('data-i18n-title', anahtar);
        else el.removeAttribute('data-i18n-title');
        if (metin) el.setAttribute('title', metin);
        else el.removeAttribute('title');
    }

    /* Panel yardımcısı — katalog gelirse select seçeneklerini tag
       filtresiyle yeniden kurar; gelmezse hiçbir şeye dokunmaz.
       opts:
         tags      string | string[]  — filtre etiket(ler)i (OR)
         fallback  [[value, label], ...] — panelin hardcoded listesi;
                   YERİNDE güncellenir ki henüz DOM'a monte edilmemiş
                   paneller de katalog listesiyle kurulsun
         merge     true → katalogda olmayan fallback girdileri korunur
                   (ör. thermal_protection'a özgü ablatifler)
         panelId + fieldId → AnalysisDock select'i (ad_f_<panel>_<field>)
         selectId  → doğrudan DOM id'si (ör. feed panelinin kendi formu)
       Dönen Promise<boolean>: select katalogdan dolduruldu mu. */
    function populateSelect(opts) {
        return load().then(function (cat) {
            if (!cat || !opts) return false;
            var entries = list(opts.tags);
            if (!entries.length) return false;

            var options = entries.map(function (m) {
                return [m.key, m.name || m.key];
            });
            // Panelin kendi satırları (değer → [değer, etiket, anahtar?]) —
            // yedek dizisi aşağıda yerinde değişmeden ÖNCE okunur.
            var panelRows = {};
            if (Array.isArray(opts.fallback)) {
                opts.fallback.forEach(function (o) { panelRows[o[0]] = o; });
            }
            var have = {};
            options.forEach(function (o) { have[o[0]] = true; });

            if (opts.merge && Array.isArray(opts.fallback)) {
                opts.fallback.forEach(function (o) {
                    if (have[o[0]]) return;
                    var canon = resolve(o[0]);
                    if (canon && have[canon]) {
                        // Panelin anahtarı katalog kaydının alias'ı: değeri
                        // PANEL anahtarında tut (backend o adı bekliyor —
                        // ör. thermal_protection 'silica_phenolic'), etiketi
                        // katalogtan al.
                        options.forEach(function (opt) {
                            if (opt[0] === canon) opt[0] = o[0];
                        });
                        delete have[canon];
                        have[o[0]] = true;
                        return;
                    }
                    options.push(o.slice());
                    have[o[0]] = true;
                });
            }

            // A1c panel-dil: görünen metin + sözlük anahtarı (değer aynen).
            options = options.map(function (o) {
                return labelRow(o[0], o[1], panelRows);
            });

            // Fallback dizisini yerinde güncelle (mount edilmemiş paneller
            // spec.fields üzerinden bu diziyi okumaya devam eder).
            if (Array.isArray(opts.fallback)) {
                opts.fallback.length = 0;
                options.forEach(function (o) { opts.fallback.push(o); });
            }

            // Monte edilmiş select varsa yeniden kur; mevcut seçim alias
            // ise kanonik anahtara normalize edilir. Anahtarlı seçenek
            // data-i18n taşır: dil değişince I18N.apply seçenekle birlikte
            // çevirir (güvertenin fieldHtml deseni).
            var domId = opts.selectId
                || ('ad_f_' + opts.panelId + '_' + opts.fieldId);
            var el = document.getElementById(domId);
            if (el && el.tagName === 'SELECT') {
                var current = el.value;
                var keep = have[current] ? current : resolve(current);
                el.innerHTML = options.map(function (o) {
                    return '<option value="' + escHtml(o[0]) + '"'
                        + (o[2] ? ' data-i18n="' + escHtml(o[2]) + '"' : '') + '>'
                        + escHtml(o[2] ? T(o[2], o[1]) : o[1]) + '</option>';
                }).join('');
                if (keep && have[keep]) el.value = keep;
                refreshTitle(el);
            }
            return true;
        });
    }

    /* ÖH D24 / OH-D23-03 — YAPISAL VARSAYILAN MALZEME, İSTEMCİ İKİZİ.

       Sunucudaki TEK KAYNAK: hrma/data/materials_db.py
       DEFAULT_STRUCTURAL_MATERIAL. Paneller form alanlarını fetch
       çözülmeden ÖNCE (senkron) kurduğu için istemcinin bir başlangıç
       değeri taşıması zorunlu; bu yüzden ikiz burada TEK yerde durur —
       panel dosyalarına dağılmış 'aluminum_6061' dizgileri yerine.
       İki tarafın ayrışması bekçiyle yasaklandı: /api/materials
       'default_structural_material' alanını yayımlar ve
       tests/test_d24_fix_asamasi.py sunucu ile bu sabiti EŞİTLER. */
    var DEFAULT_STRUCTURAL_MATERIAL = 'aluminum_6061';

    /* Katalog yüklendiyse sunucunun söylediği değer, yüklenmediyse ikiz. */
    function defaultStructuralMaterial() {
        if (_catalog && _catalog.defaultStructuralMaterial) {
            return _catalog.defaultStructuralMaterial;
        }
        return DEFAULT_STRUCTURAL_MATERIAL;
    }

    window.HRMAMaterials = {
        load: load,
        list: list,
        get: get,
        resolve: resolve,
        populateSelect: populateSelect,
        DEFAULT_STRUCTURAL_MATERIAL: DEFAULT_STRUCTURAL_MATERIAL,
        defaultStructuralMaterial: defaultStructuralMaterial,
    };
})();
