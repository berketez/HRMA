/*
 * HRMA HUD davranış katmanı — hud.js
 *
 * results_hud.css bileşenlerinin küçük JS yardımcıları. ZORUNLU bağımlılık
 * yok; theme.css + results_hud.css yüklendikten sonra dahil edilir.
 * TEK İSTEĞE BAĞLI bağımlılık (ÖH D33-3 / OH-D33-12): `window.I18N`
 * varsa sayaç metni ondalık ayracını `I18N.decimalText` TEK KAYNAĞINDAN
 * alır; yoksa bugünkü nokta davranışı korunur (sayı değişmez).
 *
 * window.HRMAHud:
 *   countUp(el)              — .hd-count sayacını data-target'a doğru sayar
 *   termLog(lines, el, opts) — terminal günlüğü oynatması (100-150 ms/satır)
 *   bindState(el, status)    — yapısal hüküm sözcüğü → data-state
 *                              (SAFE|ACCEPTABLE|MARGINAL|UNSAFE|NOT_EVALUATED);
 *                              sözlük dışı sözcük → data-state="unrecognized"
 *                              (sınıflandırma ÜRETİLMEZ, yeşile de düşülmez),
 *                              hüküm hiç yoksa öznitelik konmaz
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

    /* ÖH D33-3 / OH-D33-12 — GÖSTERGE KARTI DA TEK AYRAÇ KANONUNU İZLER.

       ÖLÇÜLEN KUSUR (raw/OH/D33-3/arayuz-i18n/a1/once.json, M1; kanıt
       docs/user_guide/img/tr-02-results.png ve o turun kaydı
       raw/OH/KILAVUZ/ekran/kayit.json): Türkçe arayüzde AYNI EKRANDA
       gösterge kartları NOKTA, hemen altındaki Uyarılar paneli VİRGÜL
       basıyordu — kart değerleri '222.8' / '20.0' / '0.458' / '0.81'
       (4/5 kart), uyarılar '7,5' / '0,5-6' / '3,87'. ÖH D30 / P12aB1-01
       ayraç seçimini `i18n.js::ondalikAyraci` TEK KAYNAĞINA bağlamıştı
       ama bu satır o kanaldan hiç geçmiyordu: `toFixed` ECMA-262 gereği
       HER ZAMAN nokta basar.

       Onarım ayracı BURADA SEÇMEZ (ikinci kaynak doğurmaz): basamak
       sayısına `toFixed` karar vermeyi sürdürür, ayracı ürünün önceden
       biçimlenmiş sayı metni kanalı `I18N.decimalText` çevirir. Kanal
       yoksa (hud.js bağımsız yüklenebilir) metin BUGÜNKÜ hâliyle kalır —
       sayı ne değişir ne uydurulur, yalnız yerelleştirme düşer.
       Makine öznitelikleri (`data-target`) DOKUNULMAZ: onları
       `parseFloat` okur ve nokta beklerler. */
    /* Sayı sayacı: rAF + cubic ease-out; reduced-motion'da anında yazar. */
    function countUp(el) {
        if (!el || el.dataset.hudCounted) return;
        var target = parseFloat(el.dataset.target);
        if (!isFinite(target)) return;
        var dec = parseInt(el.dataset.decimals || '1', 10);
        /* Yardımcı BİLEREK bu işlevin İÇİNDE: `raw/OH/D22/arayuz/a1/
           kanit_node.js` `countUp` GÖVDESİNİ kaynaktan çıkarıp ayrı bir
           `new Function` içinde koşuyor (negatif kare bekçisi). Modül
           kapsamındaki bir yardımcı o kopyada tanımsız kalır ve bekçi
           ReferenceError ile patlar — ölçüldü, D33-3 ilk turu. */
        var ondalik = function (text) {
            return (window.I18N && typeof window.I18N.decimalText === 'function')
                ? window.I18N.decimalText(text) : text;
        };
        el.dataset.hudCounted = '1';
        if (reducedMotion() || !window.requestAnimationFrame) {
            el.textContent = ondalik(target.toFixed(dec));
            return;
        }
        var start = performance.now();
        (function frame(now) {
            // ÖH D22 / P17B4-03 — İLERLEME İKİ UÇTAN DA KIRPILIR.
            // ÖLÇÜLDÜ (raw/OH/D22/arayuz/a1/once.json M3, taban b84b10a):
            // burada yalnız ÜST sınır (Math.min(1, …)) kırpılıyordu. `start`
            // performance.now() ile alınır; `now` ise requestAnimationFrame
            // geri çağrısına gelen KARE BAŞLANGICI zaman damgasıdır ve
            // çağrıdan ÖNCE olabilir (tek karelik ~16-21 ms rAF sapması).
            // now < start iken p < 0 -> (1-p)³ > 1 -> e < 0 ve ekrana
            // FİZİKÇE İMKÂNSIZ sayılar basılıyordu: P17 turunda gerçek bir
            // hesaplamada beş manşet kartının BEŞİ birden (itki −95 N,
            // Isp −21,7 s, oda basıncı −1,9 bar, ṁ −0,043 kg/s, min SF −0,08).
            // Alt kırpma animasyonu değiştirmez (p ∈ [0,1] zaten tasarım
            // aralığıdır), yalnız aralık dışına taşan kareyi başlangıç
            // değerine oturtur. Uydurma yok: hedef sayı DEĞİŞMEZ.
            var p = Math.max(0, Math.min(1, (now - start) / COUNT_MS));
            var e = 1 - Math.pow(1 - p, 3); // cubic ease-out
            el.textContent = ondalik((target * e).toFixed(dec));
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
       'UNSAFE'.includes('SAFE') tuzağına düşülmez.

       ÖH D21 / P12aB4-17 — ÖLÇÜLEN KUSUR: sözlük backend'in ürettiği BEŞ
       hüküm sözcüğünden (structural_analysis.py: STRUCTURAL_RISK_LADDER +
       STRUCTURAL_RISK_TOP + STRUCTURAL_VERDICT_NOT_EVALUATED) yalnız üçünü
       tanıyordu; 'ACCEPTABLE' ve 'NOT_EVALUATED' hiç `data-state` almıyordu.
       Öznitelik konmayınca kart CSS'te --state-ink almıyor VE .hd-led kendi
       varsayılanına (--hd-green) düşüyordu: yani ONAYI GERİ ÇEKİLMİŞ hüküm
       ekranda YEŞİL görünüyordu (fail-open). Sınıflandırma burada
       ÜRETİLMEZ — app.js statusColor ile birebir aynı aile kullanılır:
       SAFE/ACCEPTABLE onay, MARGINAL/UNSAFE tehlike, NOT_EVALUATED hükümsüz.
       Yeni sözcük eklendiğinde bu sözlük ve results_hud.css birlikte
       genişletilir (tests/test_d21_electron_a1.py bunu bekçiye bağlar). */
    var STATE_MAP = {
        SAFE: 'safe',
        ACCEPTABLE: 'acceptable',
        MARGINAL: 'marginal',
        UNSAFE: 'unsafe',
        NOT_EVALUATED: 'not-evaluated'
    };

    /* ÖH D22 / P17B2-01 — ÖLÇÜLEN KUSUR (CANLI Chrome, sistem kanalı;
       raw/OH/D22/arayuz/a2/canli_sonra.json + rapor.md §P17B2-01):
       `data-state` KAPSAYICIYA konduğunda — ki results_hud.css'in kendi
       yorumu tam olarak bunu tarif ediyor: "data-state kapsayıcıya
       verilir; --led ve --state-ink oradan akar" — LED'in rengi hükme
       göre HİÇ değişmiyordu. Ölçülen dört hüküm de aynı yeşil:

           safe / acceptable / marginal / unsafe -> rgb(45, 212, 168)

       Sebep CSS kademe kuralı: `.hd-led` gövdesi `--led: var(--hd-green)`
       değişkenini LED'İN KENDİ ÜSTÜNDE tanımlıyor; elemanın kendi
       bildirimi, kapsayıcıdan MİRAS gelen değeri yener. Yani
       `[data-state="unsafe"] { --led: var(--hd-red); }` kapsayıcıda
       kalıyor, LED'e hiç ulaşmıyordu. Sonuç fail-open: GÜVENSİZ hüküm
       ekranda yeşil LED'le görünüyordu. Aynı öznitelik doğrudan LED'in
       üstünde olduğunda renkler doğru çıkıyor (ölçüldü: marginal
       rgb(255,190,70), unsafe rgb(255,93,115)).

       Onarım burada, çünkü `bindState` özniteliği koyan TEK huni. CSS'e
       dokunulmaz (bu dalgada results_hud.css kardeş dalın sahasında);
       öznitelik, kuralların kazandığı düğüme de basılır.

       İkinci ayak — RENK TEK KANAL DEĞİL: hüküm sözcüğü LED'e
       `aria-label` ve `data-verdict` olarak da yazılır. Sözcük ucun
       KENDİ ürettiği hüküm belirtecidir (SAFE/ACCEPTABLE/MARGINAL/
       UNSAFE/NOT_EVALUATED); burada metin uydurulmaz, çevrilmez. */
    function ledDugumleri(el) {
        var liste = [];
        if (el.classList && el.classList.contains('hd-led')) liste.push(el);
        if (el.querySelectorAll) {
            Array.prototype.push.apply(
                liste, el.querySelectorAll('.hd-led'));
        }
        return liste;
    }

    /* ÖH D24 / P12aB4-18 — SÖZLÜK DIŞI HÜKÜM SÖZCÜĞÜ HÂLÂ FAIL-OPEN'DI.
       D21 (P12aB4-17) sözlüğü arka ucun BEŞ yapısal sözcüğüne tamamladı,
       ama sözlükte OLMAYAN bir sözcük geldiğinde eski `else` dalı hâlâ
       `data-state`i SİLİYORDU ve `.hd-led` kendi varsayılanına düşüyordu.

       ÖLÇÜLDÜ (CANLI Chrome, getComputedStyle; raw/OH/D24/electron/a1/
       once_b4_18.json, taban 88a29d3):

           bindState(kart, 'EXCEEDS_ALLOWABLE')
             -> data-state = null
             -> .hd-led background = rgb(45, 212, 168)   [ONAY YEŞİLİ]

       `EXCEEDS_ALLOWABLE` uydurma bir sözcük değildir: katı ve hibrit
       uçları GERÇEKTEN üretir (solid_rocket_engine.py:2189,
       hybrid_rocket_engine.py:1992 — `'SAFE' if t_aw <= izin else
       'EXCEEDS_ALLOWABLE'`). Yani "izin verileni AŞTI" hükmü bu huniden
       geçtiği anda ekranda ONAY YEŞİLİ oluyordu.

       ONARIM SINIFLANDIRMA ÜRETMEZ (sahte veri yasağı): sözcük ne yapısal
       merdivene eklenir ne de bir güvenlik rengine eşlenir. Yapılan tek
       şey sessiz yeşile düşüşü kesmek — kart `data-state="unrecognized"`
       alır (results_hud.css'te NÖTR, onay yeşili değil) ve LED ham sözcüğü
       `data-verdict` + `aria-label` ile çevrilmeden taşır. Böylece hem
       ekran hem ekran okuyucu "hüküm var ama bu katman sınıflandıramıyor"
       der; "güvenli" DEMEZ.

       Hüküm HİÇ verilmemişse (null / '') davranış DEĞİŞMEZ: öznitelik
       konmaz — söylenecek bir şey yoktur, uydurulmaz.

       STATE_MAP'in genişletilmesi (ısıl bir sözcüğü YAPISAL hüküm
       merdivenine almak) ayrı ve semantik bir karardır; bu onarım onu
       VERMEZ, yalnız kararsız hâli dürüst gösterir. */
    var UNRECOGNIZED_STATE = 'unrecognized';

    function bindState(el, status) {
        if (!el) return;
        var raw = String(
            (status === undefined || status === null) ? '' : status).trim();
        var key = raw.toUpperCase();
        var ledler = ledDugumleri(el);
        if (STATE_MAP.hasOwnProperty(key)) {
            el.setAttribute('data-state', STATE_MAP[key]);
            ledler.forEach(function (led) {
                led.setAttribute('data-state', STATE_MAP[key]);
                led.setAttribute('data-verdict', key);
                led.setAttribute('aria-label', key);
            });
        } else if (raw !== '') {
            el.setAttribute('data-state', UNRECOGNIZED_STATE);
            ledler.forEach(function (led) {
                led.setAttribute('data-state', UNRECOGNIZED_STATE);
                led.setAttribute('data-verdict', key);
                led.setAttribute('aria-label', key);
            });
        } else {
            el.removeAttribute('data-state');
            ledler.forEach(function (led) {
                led.removeAttribute('data-state');
                led.removeAttribute('data-verdict');
                led.removeAttribute('aria-label');
            });
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
