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

    /* V301/UÇUŞ NK-47 — SON YAYIMLANAN ARACIN HANGİ HESABA AİT OLDUĞU.
     * Motor sayfasının 6-DOF paneli "gövde bu motoru taşıyabilir mi"
     * hükmü için motorun dış zarfını (engine_od_m / engine_length_m) aynı
     * hesabın normalize edilmiş aracından alır; Fırlatma Sahası da aynı
     * alanları gönderir ve hüküm 6-DOF ucunda TEK işlevle verilir
     * (flight_vehicle.airframe_fit_conflicts). Eşleşme NESNE KİMLİĞİYLE
     * kurulur: araç yalnız o sonuç nesnesi (window.currentResults) için
     * döner, bayat bir hesabın aracı başka bir hesaba yapışmaz. */
    var lastPublished = { results: null, vehicle: null };

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
            lastPublished = { results: results, vehicle: vehicle };
            // NK-14/NK-47: aynı sayfanın panelleri (yörünge, 6-DOF) aracı
            // beklemeden kurulur; araç gelince haber verilir ki kütleler ve
            // motor zarfı TEK kaynaktan (sunucu normalize) tohumlansın.
            try {
                if (typeof document !== 'undefined' && document.dispatchEvent
                        && typeof CustomEvent === 'function') {
                    document.dispatchEvent(new CustomEvent('hrma:flight-vehicle',
                        { detail: { results: results, vehicle: vehicle } }));
                }
            } catch (e) { /* olay yayımlanamazsa paneller vehicleFor ile okur */ }
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

    /* launch_site tarafı: son köprülenen aracı oku (yoksa null).
     *
     * ÖH D21 / P12aB4-22 — ÖLÇÜLEN KUSUR: bu fonksiyonun ürün tarafında HİÇ
     * çağrısı yoktu; launch_site.html depolama anahtarını KENDİ yeniden
     * bildirip (`var HANDOFF_KEY = ...`) doğrudan localStorage'a gidiyordu —
     * aynı anahtarın iki kaynağı, biri değişirse köprü sessizce kopardı.
     *
     * Çağrıya bağlanabilmesi için tek eksik parça durum ayrımıydı: eski gövde
     * "kayıt yok" ile "kayıt var ama çözülemedi" durumlarının İKİSİNDE de
     * null dönüyordu ve tüketici bozuk kaydı "henüz hesap yapılmamış" diye
     * raporlardı (sessiz yedek). `out` verilirse `out.status` doldurulur:
     *   'empty'      — kayıt yok (temiz durum)
     *   'unreadable' — kayıt var ama okunamadı/çözülemedi (depolama kapalı
     *                  olması da buraya girer: "okunamadı" bilgisi doğrudur)
     *   'ok'         — kayıt çözüldü
     * Dönüş sözleşmesi değişmedi: kayıt ya da null.
     */
    function readLast(out) {
        var durum = 'empty', kayit = null;
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (raw) {
                try {
                    kayit = JSON.parse(raw);
                    durum = kayit ? 'ok' : 'unreadable';
                } catch (e) {
                    durum = 'unreadable';
                }
            }
        } catch (e) {
            durum = 'unreadable';
        }
        if (out) out.status = durum;
        return durum === 'ok' ? kayit : null;
    }

    /* Köprüyü temizle (yeni saha/araç seçilince entegratör çağırabilir). */
    function clear() {
        try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) { /* geç */ }
    }

    /* V301/UÇUŞ NK-14 / NK-24 — HESAPTAN SONRA MOTOR FORMU DEĞİŞTİ Mİ?
     * Hibrit sayfa (app.js yorungeIcinDegisenMotorAlanlari) yörüngeyi bayat
     * motorla koşmuyordu; katı ve sıvı sayfaları koşuyordu (ölçüldü:
     * nk_paneller_sonra.json — katıda Pc 40 -> 55, sıvıda itki 25 -> 30 kN
     * değiştirilip hesaplanmadan yörünge 200 aldı, eski motorla). Tek yardımcı:
     * son hesabın form anlığı ile bugünkü formu karşılaştırır; çözücünün
     * OKUMADIĞINI kendisi beyan ettiği alanlar (results.unwired_inputs her
     * kategori + results.inputs_not_used) motoru değiştirmediği için dışarıda
     * kalır. Dönüş: değişen alan adları (sıralı) ya da anlık yoksa null. */
    function changedMotorFields(lastForm, nowForm, results) {
        if (!lastForm || typeof lastForm !== 'object') return null;
        var haric = {};
        var uw = results && results.unwired_inputs;
        if (uw && typeof uw === 'object') {
            Object.keys(uw).forEach(function (k) {
                (Array.isArray(uw[k]) ? uw[k] : []).forEach(function (f) {
                    var ad = (typeof f === 'string') ? f : (f && f.field);
                    if (ad) haric[ad] = true;
                });
            });
        }
        (Array.isArray(results && results.inputs_not_used) ? results.inputs_not_used : [])
            .forEach(function (f) {
                var ad = (typeof f === 'string') ? f : (f && f.field);
                if (ad) haric[ad] = true;
            });
        var simdi = nowForm || {};
        return Object.keys(Object.assign({}, lastForm, simdi)).filter(function (k) {
            return !haric[k] && JSON.stringify(lastForm[k]) !== JSON.stringify(simdi[k]);
        }).sort();
    }

    /* NK-47: verilen sonuç nesnesinin (aynı hesap) normalize aracı ya da null. */
    function vehicleFor(results) {
        return (results && lastPublished.results === results)
            ? lastPublished.vehicle : null;
    }

    window.FlightHandoff = {
        publish: publish,
        vehicleFor: vehicleFor,
        changedMotorFields: changedMotorFields,
        readLast: readLast,
        clear: clear,
        detectMotorType: detectMotorType,
        STORAGE_KEY: STORAGE_KEY
    };
})();
