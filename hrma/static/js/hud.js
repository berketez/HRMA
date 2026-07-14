/*
 * HRMA HUD davranış katmanı — hud.js
 *
 * results_hud.css bileşenlerinin küçük JS yardımcıları. Bağımlılık yok;
 * theme.css + results_hud.css yüklendikten sonra dahil edilir.
 *
 * window.HRMAHud:
 *   countUp(el)              — .hd-count sayacını data-target'a doğru sayar
 *   termLog(lines, el, opts) — terminal günlüğü oynatması (100-150 ms/satır)
 *   bindState(el, status)    — 'SAFE'|'MARGINAL'|'UNSAFE' → data-state
 *   initAll(root)            — root içindeki tüm .hd-count'ları başlatır
 */
(function () {
    'use strict';

    var COUNT_MS = 700;          // sayaç süresi (prototiple aynı)
    var LOG_MS_MIN = 100;        // günlük satır aralığı alt sınır
    var LOG_MS_MAX = 150;        // günlük satır aralığı üst sınır
    var LOG_MS_DEFAULT = 130;

    function reducedMotion() {
        return !!(window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    /* Sayı sayacı: rAF + cubic ease-out; reduced-motion'da anında yazar. */
    function countUp(el) {
        if (!el || el.dataset.hudCounted) return;
        var target = parseFloat(el.dataset.target);
        if (!isFinite(target)) return;
        var dec = parseInt(el.dataset.decimals || '1', 10);
        el.dataset.hudCounted = '1';
        if (reducedMotion() || !window.requestAnimationFrame) {
            el.textContent = target.toFixed(dec);
            return;
        }
        var start = performance.now();
        (function frame(now) {
            var p = Math.min(1, (now - start) / COUNT_MS);
            var e = 1 - Math.pow(1 - p, 3); // cubic ease-out
            el.textContent = (target * e).toFixed(dec);
            if (p < 1) window.requestAnimationFrame(frame);
        })(start);
    }

    /* Terminal günlüğü oynatması. lines: her öğe string ya da
       { time: '[21:04:09.112]', cls: ''|'ok'|'wr'|'er'|'hl', text: '...' }.
       textContent kullanılır — HTML enjeksiyonu yolu yok. */
    function termLog(lines, el, opts) {
        if (!el || !Array.isArray(lines)) return;
        opts = opts || {};
        var interval = Math.min(LOG_MS_MAX,
            Math.max(LOG_MS_MIN, opts.interval || LOG_MS_DEFAULT));
        if (reducedMotion()) interval = 0; // anında dök
        el.textContent = '';               // önceki oynatmayı temizle
        var i = 0;
        (function push() {
            if (i >= lines.length) {
                if (opts.cursor !== false) {
                    var end = document.createElement('div');
                    end.className = 'ln';
                    var cur = document.createElement('span');
                    cur.className = 'cursor';
                    end.appendChild(cur);
                    el.appendChild(end);
                }
                return;
            }
            var L = lines[i++];
            if (typeof L === 'string') L = { text: L };
            var ln = document.createElement('div');
            ln.className = 'ln';
            if (L.time) {
                var t = document.createElement('span');
                t.className = 't';
                t.textContent = L.time;
                ln.appendChild(t);
            }
            var body = document.createElement('span');
            if (L.cls) body.className = L.cls;
            body.textContent = L.text || '';
            ln.appendChild(body);
            el.appendChild(ln);
            el.scrollTop = el.scrollHeight;
            if (interval === 0) push();
            else window.setTimeout(push, interval);
        })();
    }

    /* Durum bağlama: advanced.html getSafetyClass sözleşmesiyle aynı
       adlar. YALNIZ string eşlemesi — eşik hesabı burada YOK (sayısal
       eşikler getSafetyClass'ta kalır). Tam anahtar eşleşmesi kullanılır;
       'UNSAFE'.includes('SAFE') tuzağına düşülmez. */
    var STATE_MAP = { SAFE: 'safe', MARGINAL: 'marginal', UNSAFE: 'unsafe' };

    function bindState(el, status) {
        if (!el) return;
        var key = String(status || '').trim().toUpperCase();
        if (STATE_MAP.hasOwnProperty(key)) {
            el.setAttribute('data-state', STATE_MAP[key]);
        } else {
            el.removeAttribute('data-state');
        }
    }

    /* root (verilmezse document) içindeki tüm .hd-count sayaçlarını başlat. */
    function initAll(root) {
        var scope = root || document;
        Array.prototype.forEach.call(
            scope.querySelectorAll('.hd-count'), countUp);
    }

    window.HRMAHud = {
        countUp: countUp,
        termLog: termLog,
        bindState: bindState,
        initAll: initAll
    };
})();
