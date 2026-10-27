/* ====================================================================
   HRMA — ortak alan ipucu bileşeni (field_help.js) · v3.0.1 N-girdi-1
   --------------------------------------------------------------------
   Berke (26 Eki 2026): "Her bir inputun yanında açıklaması olmalı,
   istisnasız." Ana formlarda desen zaten vardı
   (`.tooltip > .tooltip-icon + .tooltip-text`), ama (1) biçimi üç
   şablonda kopyaydı, (2) analiz güvertesi ve panel girdileri onu hiç
   kullanmıyordu, (3) gizli balon sağ kenarda sayfayı yatay taşırıyordu
   (ölçüldü: katı 1024 → 1080 px, sıvı 1280 → 1328 px).

   Bu dosya TEK kaynaktır:
     HRMAHelp.html(key, fallback)        → ipucu işaretlemesi (dize)
     HRMAHelp.attach(el, key, fallback)  → işaretlemeyi `el`in sonuna ekler
     HRMAHelp.place(tooltipEl)           → açık balonu ekran içine yerleştirir

   Metin `data-i18n` ile taşınır: dil değişince `I18N.apply` balonu da
   çevirir (ikonun kendisi "?" — çevrilmez). Biçim `theme.css`
   "Alan ipucu (ortak bileşen)" bölümündedir.

   Davranış (CSS + bu dosya):
     · gizli balon yerleşime ve sayfa genişliğine KATILMAZ (theme.css),
     · fareyle ya da KLAVYEYLE (Tab → ikon odak alır) açılır, Esc kapatır,
       dokunmatikte ikona dokunmak aç/kapa yapar,
     · açılırken balon `position: fixed` ile ekran kenarına göre içeri
       hizalanır (8 px pay); üstte yer yoksa ikonun altına açılır. Sabit
       konum, `overflow` kırpan kapların dışına da taşar.
   JS yüklenmezse CSS'in mutlak konumlu balonu yine çalışır (yalnız kenar
   hizalaması olmaz).
   ==================================================================== */
(function (global) {
    'use strict';

    var KENAR = 8;      // balon ⟷ ekran kenarı asgari payı (px)
    var ARALIK = 10;    // balon ⟷ ikon aralığı (ok dahil, px)

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function metin(key, fallback) {
        var I = global.I18N;
        if (key && I && typeof I.t === 'function') return I.t(key, fallback);
        return fallback == null ? '' : fallback;
    }

    /* İpucu işaretlemesi. `key` LİTERAL olarak çağıranın kaynağında
       yazılı olmalıdır (ölü-çeviri bekçileri anahtarı kaynakta arar). */
    function html(key, fallback) {
        var k = key ? ' data-i18n="' + esc(key) + '"' : '';
        return '<span class="tooltip hrma-help">'
            + '<span class="tooltip-icon" tabindex="0" role="button"'
            + ' aria-label="?">?</span>'
            + '<span class="tooltip-text" role="tooltip"' + k + '>'
            + esc(metin(key, fallback)) + '</span></span>';
    }

    function attach(el, key, fallback) {
        if (!el || typeof el.insertAdjacentHTML !== 'function') return null;
        el.insertAdjacentHTML('beforeend', html(key, fallback));
        return el.lastElementChild;
    }

    /* Açık balonu ekran içine yerleştirir. offsetWidth/offsetHeight
       dönüşümden (scale) etkilenmez: gizliyken de gerçek boyut okunur. */
    function place(tip) {
        if (!tip || !tip.querySelector) return;
        var ikon = tip.querySelector('.tooltip-icon');
        var balon = tip.querySelector('.tooltip-text');
        if (!ikon || !balon || !global.innerWidth) return;
        var r = ikon.getBoundingClientRect();
        var vw = document.documentElement.clientWidth || global.innerWidth;
        var vh = global.innerHeight;
        balon.style.maxWidth = Math.max(120, vw - 2 * KENAR) + 'px';
        var w = balon.offsetWidth, h = balon.offsetHeight;
        var orta = r.left + r.width / 2;
        var sol = Math.min(Math.max(orta - w / 2, KENAR), Math.max(KENAR, vw - w - KENAR));
        var ust = r.top - h - ARALIK;
        var altta = ust < KENAR && (r.bottom + ARALIK + h) <= (vh - KENAR);
        if (altta) ust = r.bottom + ARALIK;
        else if (ust < KENAR) ust = KENAR;
        balon.style.position = 'fixed';
        balon.style.left = Math.round(sol) + 'px';
        balon.style.top = Math.round(ust) + 'px';
        balon.style.bottom = 'auto';
        balon.style.marginLeft = '0';
        // ok ikonun ortasını göstersin (balon kaydırılmış olabilir)
        var okX = Math.min(Math.max(orta - sol, 12), w - 12);
        balon.style.setProperty('--hrma-tip-arrow-x', Math.round(okX) + 'px');
        tip.classList.toggle('tip-below', !!altta);
        // Bir ata `transform`/`filter` taşıyorsa `fixed` o atanın kutusuna
        // göre konumlanır: ölçülen sapma kadar düzelt (balon açıkken).
        var g = balon.getBoundingClientRect();
        if (g.width > 1) {
            var dx = sol - g.left, dy = ust - g.top;
            if (Math.abs(dx) > 1) balon.style.left = Math.round(sol + dx) + 'px';
            if (Math.abs(dy) > 1) balon.style.top = Math.round(ust + dy) + 'px';
        }
    }

    function tooltipOf(t) {
        return (t && t.closest) ? t.closest('.tooltip') : null;
    }

    function kapatHepsi(haric) {
        var acik = document.querySelectorAll('.tooltip.tip-open');
        for (var i = 0; i < acik.length; i++) {
            if (acik[i] !== haric) acik[i].classList.remove('tip-open');
        }
    }

    function kur() {
        if (!global.document || !document.addEventListener) return;
        // Şablonlardaki eski ikonlar da klavyeyle erişilebilir olsun.
        function odaklanabilir(kok) {
            var ikonlar = (kok || document).querySelectorAll('.tooltip-icon:not([tabindex])');
            for (var i = 0; i < ikonlar.length; i++) {
                ikonlar[i].setAttribute('tabindex', '0');
                ikonlar[i].setAttribute('role', 'button');
                ikonlar[i].setAttribute('aria-label', '?');
            }
        }
        odaklanabilir(document);
        document.addEventListener('mouseover', function (e) {
            var tip = tooltipOf(e.target);
            if (tip) place(tip);
        }, true);
        document.addEventListener('focusin', function (e) {
            var tip = tooltipOf(e.target);
            if (!tip) return;
            if (!e.target.hasAttribute('tabindex')) odaklanabilir(tip);
            place(tip);
        }, true);
        document.addEventListener('click', function (e) {
            var tip = tooltipOf(e.target);
            if (tip && e.target.closest('.tooltip-icon')) {
                var acilacak = !tip.classList.contains('tip-open');
                kapatHepsi(tip);
                if (acilacak) { tip.classList.add('tip-open'); place(tip); }
                else tip.classList.remove('tip-open');
                // etiketin içindeki ikon tıklaması girdiyi odaklamasın
                e.preventDefault();
                return;
            }
            kapatHepsi(null);
        }, true);
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            kapatHepsi(null);
            var a = document.activeElement;
            if (a && a.closest && a.closest('.tooltip') && a.blur) a.blur();
        }, true);
        // Sonradan basılan ikonlar `HRMAHelp.html` ile zaten `tabindex`
        // taşır; şablonların dil değişiminde yeniden basılan parçaları için
        // dil değişince bir kez daha taranır (DOM gözlemcisi KONMADI:
        // Plotly her çizimde binlerce düğüm ekler, gözlemci boşa koşardı).
        if (global.I18N && typeof global.I18N.onChange === 'function') {
            global.I18N.onChange(function () { odaklanabilir(document); });
        }
        // Kaydırma/yeniden boyutlanmada açık balon ikonu izlesin.
        function tazele() {
            var acik = document.querySelectorAll('.tooltip.tip-open, .tooltip:hover, .tooltip:focus-within');
            for (var i = 0; i < acik.length; i++) place(acik[i]);
        }
        global.addEventListener('scroll', tazele, true);
        global.addEventListener('resize', tazele);
    }

    global.HRMAHelp = { html: html, attach: attach, place: place };

    if (global.document) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', kur);
        } else {
            kur();
        }
    }
})(typeof window !== 'undefined' ? window : this);
