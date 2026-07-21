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
    function toast(message, kind) {
        try {
            var colors = { ok: 'var(--hd-green, #2dd4a8)', err: 'var(--hd-red, #ff5d73)',
                           warn: 'var(--hd-orange, #ff8c33)', info: 'var(--hd-cyan, #00e5ff)' };
            var c = colors[kind] || colors.info;
            var node = document.createElement('div');
            node.style.cssText =
                'position:fixed; right:18px; bottom:18px; z-index:99995;' +
                'max-width:420px; padding:12px 16px; font-size:0.82rem;' +
                'font-family:var(--hd-mono, monospace); color:' + c + ';' +
                'background:var(--hd-panel-solid, #0a1524); border:1px solid ' + c + ';' +
                'border-radius:var(--hd-radius-sm, 8px);' +
                'box-shadow:var(--hd-shadow, 0 14px 44px rgba(0,0,0,0.42));';
            node.textContent = String(message);
            document.body.appendChild(node);
            setTimeout(function () {
                if (node.parentNode) node.parentNode.removeChild(node);
            }, 6000);
        } catch (e) { /* toast asla sayfayı kırmaz */ }
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
        var resp = await fetch('/api/import/motor-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!resp.ok || !data || data.status !== 'success') {
            var err = new Error((data && data.error) || ('HTTP ' + resp.status));
            // Karşılaştırma örtüşmese bile motors gövdede kalabilir (sözleşme)
            if (data && Array.isArray(data.motors)) err.partial = data;
            throw err;
        }
        return data;
    }

    async function postOrk(file) {
        var form = new FormData();
        form.append('file', file, file.name);
        var resp = await fetch('/api/import/ork', { method: 'POST', body: form });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
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

    function fmtNum(v, digits) {
        return (typeof v === 'number' && isFinite(v)) ? v.toFixed(digits) : '--';
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
    };
})();
