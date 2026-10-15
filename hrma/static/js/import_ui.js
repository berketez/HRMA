/* ====================================================================
   HRMA Import UI yardımcıları — import_ui.js (v2.5.5)
   --------------------------------------------------------------------
   Dış format içe aktarma uçlarının (backend hazır ve testli) ortak
   istemci katmanı:

     POST /api/import/motor-file  — RASP .eng / RockSim .rse itki eğrisi
     POST /api/import/ork         — OpenRocket .ork tasarım dosyası

   Tüketiciler: panels/validation_panel.js (.eng/.rse karşılaştırma) ve
   sixdof_panel.js (itki kaynağı + .ork aero/kütle aktarımı).

   Sözleşme kaynağı: hrma/importers/api.py (istek/yanıt şemaları).
   Endpoint app'e kayıtlı olmayabilir (test ortamı) — tüm çağrılar hata
   durumunda Error fırlatır, çağıran taraf toast + konsol ile zarif düşer.
   Kullanıcı metinleri i18n anahtarlı (i18n_common.js, EN/TR).
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
                     '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    // ------------------------------------------------------------------
    // Küçük toast bildirimi (koyu tema; sayfa fonksiyonlarına bağımlı değil)
    // ------------------------------------------------------------------
    // İSTİFLEME (2026-07-23): toast'lar eskiden tek tek
    // `position:fixed; right:18px; bottom:18px` ile basılıyordu; iki bildirim
    // 6 sn'lik ömür penceresinde üst üste gelirse TAM ÜSTÜNE biniyor ve
    // alttaki hiç okunamıyordu (ör. "Proje kaydedildi" + "Dosya içe aktarıldı").
    // Artık ortak bir sabit kap kullanılır, bildirimler alt kenardan yukarı
    // doğru dizilir. Kap id ile idempotent oluşturulur: project_bar.js'teki
    // yedek uygulama da aynı kabı bulur, iki dosya birbirine bağımlı olmaz.
    var TOAST_HOST_ID = 'hrma-toast-stack';

    function toastHost() {
        var host = document.getElementById(TOAST_HOST_ID);
        if (host) return host;
        host = document.createElement('div');
        host.id = TOAST_HOST_ID;
        host.style.cssText =
            'position:fixed; right:18px; bottom:18px; z-index:99995;' +
            'display:flex; flex-direction:column; gap:8px; align-items:flex-end;' +
            'pointer-events:none;';
        document.body.appendChild(host);
        return host;
    }

    function toast(message, kind) {
        try {
            var colors = { ok: 'var(--hd-green, #2dd4a8)', err: 'var(--hd-red, #ff5d73)',
                           warn: 'var(--hd-orange, #ff8c33)', info: 'var(--hd-cyan, #00e5ff)' };
            var c = colors[kind] || colors.info;
            var node = document.createElement('div');
            node.style.cssText =
                'max-width:420px; padding:12px 16px; font-size:0.82rem;' +
                'font-family:var(--hd-mono, monospace); color:' + c + ';' +
                'background:var(--hd-panel-solid, #0a1524); border:1px solid ' + c + ';' +
                'border-radius:var(--hd-radius-sm, 8px); pointer-events:auto;' +
                'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));';
            node.textContent = String(message);
            toastHost().appendChild(node);
            setTimeout(function () {
                var host = node.parentNode;
                if (host) host.removeChild(node);
                // Kap boşaldıysa DOM'da kalıntı bırakma
                if (host && host.id === TOAST_HOST_ID && !host.firstChild
                    && host.parentNode) {
                    host.parentNode.removeChild(host);
                }
            }, 6000);
        } catch (e) { /* toast asla sayfayı kırmaz */ }
    }

    // ------------------------------------------------------------------
    // Yükleme boyut tavanı (V3 güvenlik 5. tur, 14 Eki)
    // ------------------------------------------------------------------
    // KUSUR: waitress yollarında tavanı aşan yükleme waitress'in İngilizce
    // DÜZ METİN 413'ünü alıyor (sg2_waitress devri 3); arayüz ya 'HTTP 413'
    // ya da makine kodu ('request_body_too_large') basıyordu ve dosyayı
    // tavanı bilmeden baştan sona gönderiyordu.
    //
    // Tavanlar sayfaya SUNUCUDAN gelir: app.py ``inject_upload_limits``
    // bağlamı → şablondaki <meta name="hrma-upload-limits"> (JSON, bayt).
    // Bu dosyada tavan sayısı YOKTUR (CLAUDE.md §11). Tavan okunamazsa ön
    // denetim yapılmaz; sunucu kapısı yine reddeder (asıl kapı sunucudur,
    // bu denetim yalnız gereksiz gönderimi ve okunmaz iletiyi önler).
    var UPLOAD_LIMITS_META = 'meta[name="hrma-upload-limits"]';
    // Birim dönüşümü (sayı değil birim): sunucu iletileri de MB'ı
    // 1024 × 1024 bayt sayar (hrma/importers/api.py::_payload_too_large).
    var BYTES_PER_MB = 1024 * 1024;
    // CSV ucunun SATIR bandı da 413 döner; o bir BOYUT reddi değildir ve
    // sunucunun kendi iletisi gösterilir (user_data_validation.py
    // thrust_csv_row_band_error: limit = 'data_rows').
    var ROW_BAND_LIMIT = 'data_rows';
    var HTTP_PAYLOAD_TOO_LARGE = 413;

    function uploadLimitBytes(kind) {
        try {
            var meta = document.querySelector(UPLOAD_LIMITS_META);
            if (!meta) return null;
            var limits = JSON.parse(meta.getAttribute('content') || '');
            if (!limits || typeof limits !== 'object'
                || !Object.prototype.hasOwnProperty.call(limits, kind)) return null;
            var v = limits[kind];
            // Fail-closed okuma: yalnız pozitif güvenli tamsayı geçerli tavandır
            return (typeof v === 'number' && Number.isSafeInteger(v) && v > 0) ? v : null;
        } catch (e) {
            return null;
        }
    }

    function utf8ByteLength(text) {
        return new Blob([String(text)]).size;
    }

    // Boyut, tavanın altında görünmesin diye YUKARI yuvarlanır (0,1 MB)
    function mbText(bytes) {
        return (Math.ceil(bytes / BYTES_PER_MB * 10) / 10).toFixed(1);
    }

    function tooLargeMessage(kind, bytes) {
        var limit = uploadLimitBytes(kind);
        var size = (typeof bytes === 'number' && isFinite(bytes) && bytes >= 0)
            ? mbText(bytes) : '?';
        if (limit === null) {
            return TF('imp.tooLargeNoLimit', { size: size },
                'Upload too large: {size} MB.');
        }
        var limitMb = limit / BYTES_PER_MB;
        return TF('imp.tooLarge',
            { size: size,
              limit: Number.isInteger(limitMb) ? limitMb : mbText(limit) },
            'Upload too large: {size} MB; the limit for this upload is {limit} MB.');
    }

    // Göndermeden ÖNCE: aşıyorsa iletiyi, aşmıyorsa (ya da tavan yoksa) null
    function uploadSizeError(kind, bytes) {
        var limit = uploadLimitBytes(kind);
        if (limit === null || typeof bytes !== 'number' || !isFinite(bytes)) return null;
        return bytes > limit ? tooLargeMessage(kind, bytes) : null;
    }

    function assertUploadSize(kind, bytes) {
        var msg = uploadSizeError(kind, bytes);
        if (msg) {
            var err = new Error(msg);
            err.code = 'upload_too_large';
            throw err;
        }
    }

    // Sunucudan yine de BOYUT 413'ü geldiyse (düz metin ya da JSON) ham
    // gövde yerine aynı i18n iletisi; boyut 413'ü değilse null. Yanıt
    // NESNESİ alınır: dönen metin sunucu metni değil, yerel i18n iletisidir.
    function payloadTooLargeMessage(kind, bytes, resp, data) {
        var status = resp ? resp.status : null;
        if (status !== HTTP_PAYLOAD_TOO_LARGE) return null;
        if (data && data.limit === ROW_BAND_LIMIT) return null;
        return tooLargeMessage(kind, bytes);
    }

    // ------------------------------------------------------------------
    // Dosya okuma
    // ------------------------------------------------------------------
    function readFileAsText(file) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () { resolve(String(reader.result || '')); };
            reader.onerror = function () {
                reject(new Error(T('imp.readFailed', 'Could not read the selected file.')));
            };
            reader.readAsText(file);
        });
    }

    // ------------------------------------------------------------------
    // Uç çağrıları — hata durumunda Error(message) fırlatır
    // ------------------------------------------------------------------
    async function postMotorFile(content, filename, prediction) {
        var body = { content: content, filename: filename };
        if (prediction && Array.isArray(prediction.time) &&
            Array.isArray(prediction.thrust)) {
            body.prediction = { time: prediction.time, thrust: prediction.thrust };
        }
        // Sunucu dosya İÇERİĞİNİN UTF-8 baytını tavanla karşılaştırır
        var contentBytes = utf8ByteLength(content);
        assertUploadSize('motor_file', contentBytes);
        var resp = await fetch('/api/import/motor-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        var tooLarge = payloadTooLargeMessage('motor_file', contentBytes,
                                              resp, data);
        if (tooLarge) throw new Error(tooLarge);
        if (!resp.ok || !data || data.status !== 'success') {
            var err = new Error((data && data.error) || ('HTTP ' + resp.status));
            // Karşılaştırma örtüşmese bile motors gövdede kalabilir (sözleşme)
            if (data && Array.isArray(data.motors)) err.partial = data;
            throw err;
        }
        return data;
    }

    async function postOrk(file) {
        assertUploadSize('ork', file.size);
        var form = new FormData();
        form.append('file', file, file.name);
        var resp = await fetch('/api/import/ork', { method: 'POST', body: form });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        var tooLarge = payloadTooLargeMessage('ork', file.size, resp, data);
        if (tooLarge) throw new Error(tooLarge);
        if (!resp.ok || !data || data.status !== 'success') {
            throw new Error((data && data.error) || ('HTTP ' + resp.status));
        }
        return data;
    }

    // ------------------------------------------------------------------
    // Motor meta yardımcıları
    // ------------------------------------------------------------------

    // NFPA/NAR toplam impuls sınıfı: A sınıfı 1.25-2.5 N·s, her harf ikiye
    // katlar; 1.25 altı kesirli A sınıfları. Görsel etikettir, hesap değil.
    function impulseClass(totalNs) {
        if (typeof totalNs !== 'number' || !isFinite(totalNs) || totalNs <= 0) return '';
        if (totalNs <= 0.3125) return '1/8A';
        if (totalNs <= 0.625) return '1/4A';
        if (totalNs <= 1.25) return '1/2A';
        var letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        var upper = 2.5;
        for (var i = 0; i < letters.length; i++) {
            if (totalNs <= upper) return letters[i];
            upper *= 2;
        }
        return '>Z';
    }

    /* ÖH D21 / P12aB4-21: sayılar `toFixed` ile basılıyordu, yani her dilde
       nokta ondalık ayırıcı. Bu değerler `I18N.tf`ye DİZGE olarak gidiyor
       (tf yalnız `typeof v === 'number'` olanları I18N.number'dan geçirir),
       bu yüzden TR kipinde "D 24 mm, L 70 mm | yakıt 0.062 kg" çıkıyordu.
       Biçim tek kaynaktan (I18N.number) gelir; sözlük yoksa toFixed'e
       düşülür. Sonlu olmayan değer hâlâ '--' basılır: sayı UYDURULMAZ. */
    function fmtNum(v, digits) {
        if (typeof v !== 'number' || !isFinite(v)) return '--';
        return (window.I18N && window.I18N.number)
            ? window.I18N.number(v, digits)
            : v.toFixed(digits);
    }

    // Tek satır meta özeti: ad / üretici / çap / boy / kütleler + impuls sınıfı
    function metaLineHtml(motor) {
        var meta = (motor && motor.meta) || {};
        var computed = (motor && motor.computed) || {};
        var cls = impulseClass(computed.total_impulse_ns);
        var text = TF('imp.metaLine',
            { name: escapeHtml(meta.name || '?'),
              mfg: escapeHtml(meta.mfg || '?'),
              d: fmtNum(meta.diameter_mm, 0),
              len: fmtNum(meta.length_mm, 0),
              prop: fmtNum(meta.prop_mass_kg, 3),
              loaded: fmtNum(meta.loaded_mass_kg, 3),
              it: fmtNum(computed.total_impulse_ns, 1),
              cls: escapeHtml(cls || '?') },
            '{name} ({mfg}) — D {d} mm, L {len} mm | propellant {prop} kg, '
            + 'loaded {loaded} kg | total impulse {it} N·s (class {cls})');
        return '<div style="font-family:var(--hd-mono, monospace); font-size:0.78rem;'
            + ' color:var(--hd-ink, #cfe8f2); border:1px solid'
            + ' var(--hd-line, rgba(0,229,255,0.14));'
            + ' border-radius:var(--hd-radius-sm, 8px); padding:8px 10px; margin:8px 0;">'
            + text + '</div>';
    }

    // Eğriden CSV metni üret (upload-csv ucuna yeniden karşılaştırma için)
    function csvFromCurve(time, thrust) {
        var lines = ['time,thrust'];
        var n = Math.min(time.length, thrust.length);
        for (var i = 0; i < n; i++) lines.push(time[i] + ',' + thrust[i]);
        return lines.join('\n');
    }

    window.HRMAImportUI = {
        readFileAsText: readFileAsText,
        postMotorFile: postMotorFile,
        postOrk: postOrk,
        impulseClass: impulseClass,
        metaLineHtml: metaLineHtml,
        csvFromCurve: csvFromCurve,
        toast: toast,
        escapeHtml: escapeHtml,
        uploadLimitBytes: uploadLimitBytes,
        utf8ByteLength: utf8ByteLength,
        uploadSizeError: uploadSizeError,
        assertUploadSize: assertUploadSize,
        payloadTooLargeMessage: payloadTooLargeMessage,
    };
})();
