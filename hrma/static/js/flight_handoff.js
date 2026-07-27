/*
 * flight_handoff.js — Motor sayfası -> uçuş sahası (launch_site) oturum köprüsü.
 *
 * Amaç: Kullanıcı bir motor sayfasında (hibrit/katı/sıvı) başarılı bir hesap
 * yaptığında, sonucu tek Python normalize'ından (POST /api/flight-vehicle,
 * source:'results') geçirip normalize edilmiş "uçan araç"ı
 * localStorage['hrma.flight.lastVehicle']'e yazar. /launch-site ayrı bir sayfa
 * olduğundan (motor formu / currentResults YOK) motor oradan bu köprüyle taşınır.
 *
 * Bu dosya SADECE köprü mantığını tanımlar (window.FlightHandoff). Motor
 * HTML'lerine <script> etiketi ve publish() çağrısı EKLEMEK bu dosyanın işi
 * DEĞİLDİR (dosya sahipliği: D-frontend ajanı). launch_site tarafı
 * FlightHandoff.readLast() ile kaydı okur.
 *
 * WKWebView/pywebview'de localStorage çalışır (sixdof_panel.js:799 teyidi).
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'hrma.flight.lastVehicle';
    var ENDPOINT = '/api/flight-vehicle';

    /* Motor tipini belirle: açık değer > sayfa yolu (solid/liquid) > hibrit. */
    function detectMotorType(explicit) {
        if (explicit) return String(explicit).toLowerCase();
        var p = (window.location && window.location.pathname || '').toLowerCase();
        if (p.indexOf('solid') !== -1) return 'solid';
        if (p.indexOf('liquid') !== -1) return 'liquid';
        return 'hybrid'; // advanced.html (hibrit) varsayılan
    }

    /* Araç adı: #motor_name girdisi > sonuç sözlüğü > null (normalize doldurur). */
    function resolveName(results, explicit) {
        if (explicit && String(explicit).trim()) return String(explicit).trim();
        try {
            var el = document.getElementById('motor_name');
            if (el && el.value && el.value.trim()) return el.value.trim();
        } catch (e) { /* DOM yoksa geç */ }
        if (results && typeof results === 'object') {
            var cands = [
                results.motor_name,
                results.motor && results.motor.motor_name,
                results.motor_geometry && results.motor_geometry.motor_name
            ];
            for (var i = 0; i < cands.length; i++) {
                if (cands[i] && String(cands[i]).trim()) return String(cands[i]).trim();
            }
        }
        return null;
    }

    /*
     * Motor sayfası tarafından hesap BAŞARISINDA çağrılır.
     *   results : window.currentResults (hibrit: {motor:{...}, ...};
     *             katı/sıvı: düz sonuç sözlüğü).
     *   opts    : { motor_type?, motor_name? } — ikisi de opsiyonel.
     * Dönüş: kaydedilen kaydı çözen Promise (hata/araç yoksa null).
     * Hesap akışını ASLA bozmaz: her hata sessizce yutulur (uçuş sayfası
     * araç yoksa örnek araca düşer).
     */
    function publish(results, opts) {
        opts = opts || {};
        if (!results || typeof results !== 'object') {
            return Promise.resolve(null);
        }
        var motorType = detectMotorType(opts.motor_type);
        var name = resolveName(results, opts.motor_name);
        var payload = {
            source: 'results',
            motor_type: motorType,
            motor_name: name,
            results: results
        };

        return fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(function (r) {
            if (!r.ok) throw new Error('flight-vehicle HTTP ' + r.status);
            return r.json();
        }).then(function (data) {
            // Route {status, vehicle} ya da doğrudan araç döndürebilir.
            var vehicle = (data && data.vehicle) ? data.vehicle : data;
            if (!vehicle || typeof vehicle !== 'object') return null;
            var record = {
                vehicle: vehicle,
                motor_name: vehicle.motor_name || name || null,
                motor_type: motorType,
                saved_at: new Date().toISOString()
            };
            try {
                window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
            } catch (e) { /* storage kapalı/dolu olabilir */ }
            return record;
        }).catch(function (e) {
            if (window.console && console.debug) {
                console.debug('flight_handoff.publish:', e && e.message ? e.message : e);
            }
            return null;
        });
    }

    /* launch_site tarafı: son köprülenen aracı oku (yoksa null). */
    function readLast() {
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    /* Köprüyü temizle (yeni saha/araç seçilince entegratör çağırabilir). */
    function clear() {
        try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) { /* geç */ }
    }

    window.FlightHandoff = {
        publish: publish,
        readLast: readLast,
        clear: clear,
        detectMotorType: detectMotorType,
        STORAGE_KEY: STORAGE_KEY
    };
})();
