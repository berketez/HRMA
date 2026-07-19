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

            // Fallback dizisini yerinde güncelle (mount edilmemiş paneller
            // spec.fields üzerinden bu diziyi okumaya devam eder).
            if (Array.isArray(opts.fallback)) {
                opts.fallback.length = 0;
                options.forEach(function (o) { opts.fallback.push(o); });
            }

            // Monte edilmiş select varsa yeniden kur; mevcut seçim alias
            // ise kanonik anahtara normalize edilir.
            var domId = opts.selectId
                || ('ad_f_' + opts.panelId + '_' + opts.fieldId);
            var el = document.getElementById(domId);
            if (el && el.tagName === 'SELECT') {
                var current = el.value;
                var keep = have[current] ? current : resolve(current);
                el.innerHTML = options.map(function (o) {
                    return '<option value="' + o[0] + '">' + o[1] + '</option>';
                }).join('');
                if (keep && have[keep]) el.value = keep;
            }
            return true;
        });
    }

    window.HRMAMaterials = {
        load: load,
        list: list,
        get: get,
        resolve: resolve,
        populateSelect: populateSelect,
    };
})();
