/* ====================================================================
   HRMA — Merkezi Katı Yakıt Kataloğu (istemci tarafı, v2.5.2)
   --------------------------------------------------------------------
   GET /api/propellants sözleşmesi:
     { ok: true,
       propellants: { key: {
           key, name, family, oxidizer, fuel,
           density, burn_rate_a, burn_rate_n, burn_rate_ref,
           c_star, gamma, flame_temperature, molecular_weight,
           source, notes,
           engine_key, c_star_basis, validated,
           has_regime_law, burn_rate_reference_pressure_bar } },
       aliases: { alias: canonical_key } }

   Birim sözleşmesi (backend ile aynı):
       density                [kg/m^3]
       burn_rate_a/n          r [m/s] = a * (P [bar])^n
       c_star                 [m/s]
       flame_temperature      [K]
       molecular_weight       [kg/kmol]

   Kullanım (katı yakıt sayfası):
     if (typeof window.HRMAPropellants !== 'undefined') {
         window.HRMAPropellants.load().then(function (cat) {
             if (!cat) return;                  // fallback listede kal
             window.HRMAPropellants.list('sugar').forEach(...);
         });
     }
   Fetch başarısız olursa load() null döner ve sayfa kendi hardcoded
   fallback listesiyle çalışmaya devam eder (script hiç yüklenmemişse de
   typeof guard sayesinde davranış aynıdır).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    var _promise = null;   // tek seferlik fetch cache'i
    var _catalog = null;   // { propellants: {...}, aliases: {...} } | null

    // Katalog tek sefer çekilir; hata → null (sayfa fallback'e düşer).
    function load() {
        if (_promise) return _promise;
        _promise = fetch('/api/propellants')
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (!data || data.ok !== true || !data.propellants) return null;
                _catalog = {
                    propellants: data.propellants,
                    aliases: data.aliases || {}
                };
                return _catalog;
            })
            .catch(function () { return null; });
        return _promise;
    }

    // Alias'ı kanonik anahtara çözer; bilinmeyen ad → null.
    function resolve(key) {
        if (!_catalog) return null;
        var k = String(key || '').trim().toLowerCase();
        if (_catalog.propellants[k]) return k;
        var t = _catalog.aliases[k];
        return (t && _catalog.propellants[t]) ? t : null;
    }

    // Kayıt döndürür (alias çözümlü); katalog yok / bilinmeyen → null.
    function get(key) {
        var k = resolve(key);
        return k ? _catalog.propellants[k] : null;
    }

    // family: 'composite' | 'sugar' | 'double_base' | 'other' | null
    // Dönen: [{ key, name, ... }] aile sonra ad sırasına göre.
    function list(family) {
        if (!_catalog) return [];
        var want = family ? String(family).toLowerCase() : null;
        var out = [];
        Object.keys(_catalog.propellants).forEach(function (key) {
            var p = _catalog.propellants[key];
            if (want && String(p.family).toLowerCase() !== want) return;
            var item = { key: key };
            Object.keys(p).forEach(function (f) { item[f] = p[f]; });
            out.push(item);
        });
        out.sort(function (a, b) {
            if (a.family !== b.family) return a.family < b.family ? -1 : 1;
            var an = String(a.name || a.key), bn = String(b.name || b.key);
            return an < bn ? -1 : (an > bn ? 1 : 0);
        });
        return out;
    }

    // Katalogdaki aileler (görülen sırayla, alfabetik).
    function families() {
        if (!_catalog) return [];
        var seen = {};
        Object.keys(_catalog.propellants).forEach(function (k) {
            seen[_catalog.propellants[k].family] = true;
        });
        return Object.keys(seen).sort();
    }

    window.HRMAPropellants = {
        load: load,
        list: list,
        get: get,
        resolve: resolve,
        families: families
    };
})();
