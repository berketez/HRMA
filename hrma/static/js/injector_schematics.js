/* ====================================================================
   HRMA Injector Schematics — inline SVG cross-sections
   --------------------------------------------------------------------
   Theme-aware labelled schematics for every injector type the solver
   supports. Strokes/fills use currentColor and CSS variables so the same
   markup reads correctly on the dark application theme and on a light
   print background.

   Public API (kept stable — advanced.html and injector_panel.js both
   bind to it):
       window.InjectorSchematics.svg(type, geom)        -> SVG markup string
       window.InjectorSchematics.render(type, el, geom) -> injects into element
       window.InjectorSchematics.types()                -> supported type list

   Accepted type strings (aliases resolve to five canonical drawings):
       showerhead | pintle | swirl | impingement | coaxial

   --------------------------------------------------------------------
   ÇİZİM ARTIK HESABA BAĞLI (2026-08-09)
   --------------------------------------------------------------------
   Bu dosya "tip başına beş SABİT çizim" olarak tasarlanmıştı: panel
   /api/injector-design'dan 17 delik hesaplayıp tabloya bassa da çizimde
   DAİMA 2 ok vardı. Panelin hesabı ile çizimi arasında hiç veri yolu
   yoktu. Aynı dosya sıvı sayfasından da yükleniyor (liquid.html) ve sıvı
   pintle YAKIT-MERKEZLİ iki akışkanlı olduğu hâlde hibritin tek akışkanlı
   çizimiyle aynı resim basılıyordu.

   `geom` ikinci argümanı bu yolu açar. Sözleşme (hepsi İSTEĞE BAĞLI;
   injector_panel.js `schematicGeometry()` üretir):

       single_fluid          bool   hibrit ox-merkezli pintle mi
       n_radial_holes        int    pintle radyal delik sayısı
       radial_hole_d_mm      num    radyal delik çapı
       d_pintle_mm           num    pintle çapı D_p
       annulus_gap_mm        num    anülüs boşluğu
       skip_distance_mm      num    L_s
       bf                    num    blokaj faktörü
       radial_flow_fraction  num    radyal akış payı (0-1)
       spray_half_angle_deg  num    sprey konisi yarım açısı
       tangential_inlets     int    swirl teğet giriş sayısı
       inlet_d_mm            num    teğet giriş çapı
       film_thickness_mm     num    swirl film kalınlığı
       n_orifices            int    showerhead/impingement delik sayısı
       orifice_d_mm          num    delik çapı
       half_angle_deg        num    çarpışma yarım açısı

   DÜRÜSTLÜK KURALI: bir değer verilmemişse o etiket HİÇ ÇİZİLMEZ.
   Uydurma sayı, "~45 derece" gibi elde yazılmış değer ya da veriye
   bağlı olmayan gösterge yoktur.
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

    // ⌀ (U+2300) ve ° dile bağlı DEĞİLDİR: sayısal künyeler çeviri
    // anahtarı gerektirmesin diye simgeyle yazılır.
    var DIA = '⌀', DEG = '°';

    // Bir geometri alanını sonlu sayı olarak okur; yoksa null döner.
    // null dönen her alan için ilgili etiket HİÇ çizilmez.
    function g_(geom, key) {
        if (!geom) return null;
        var v = geom[key];
        if (typeof v !== 'number' || !isFinite(v)) return null;
        return v;
    }

    function g_int(geom, key) {
        var v = g_(geom, key);
        return (v === null || v < 1) ? null : Math.round(v);
    }

    function fmtN(v, d) {
        return (v === null || v === undefined) ? '' : Number(v).toFixed(d == null ? 2 : d);
    }

    // Bir sıra deliği çizerken kaç tanesini gerçekten çizeceğimiz. Eksenel
    // kesitte 35 delik okunaksızdır; çizilen sayı KISITLIYSA yanına gerçek
    // sayı künyesi basılır (aşağıdaki `countLabel`), yani çizim hiçbir
    // zaman "delik sayısı budur" iddiasında bulunmaz.
    var MAX_DRAWN = 12;

    function drawCount(n) {
        return (n === null) ? null : Math.max(1, Math.min(n, MAX_DRAWN));
    }

    var W = 460, H = 260;

    // Palette pulled from the application theme with literal fallbacks so
    // the schematic still reads when embedded outside the app shell.
    var C = {
        metal: 'var(--hd-metal, rgba(148,163,180,0.85))',
        metalLine: 'var(--hd-ink, #d7e3ee)',
        flow: 'var(--hd-cyan, #00e5ff)',
        accent: 'var(--hd-orange, #ff8c33)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
        spray: 'var(--hd-violet, #c792ea)'
    };

    var ALIASES = {
        showerhead: 'showerhead',
        pintle: 'pintle',
        swirl: 'swirl',
        coax_swirl: 'coaxial',
        coaxial: 'coaxial',
        impingement: 'impingement',
        impinging: 'impingement',
        impinging_doublet: 'impingement',
        impinging_triplet: 'impingement',
        like_impinging: 'impingement'
    };

    // Başlıklar çeviri anahtarıyla eşlenir; TITLES.<tip> okuyan yerler
    // fonksiyon çağrısına dönüştürüldü (dil değişince başlık da değişir).
    var TITLE_KEYS = {
        showerhead: ['sch.titleShowerhead', 'Showerhead &#8212; axial cross-section'],
        pintle: ['sch.titlePintle', 'Pintle &#8212; axial cross-section'],
        swirl: ['sch.titleSwirl', 'Pressure-swirl &#8212; axial cross-section'],
        impingement: ['sch.titleImpingement', 'Impinging doublet &#8212; axial cross-section'],
        coaxial: ['sch.titleCoaxial', 'Coaxial element &#8212; axial cross-section']
    };

    function titleOf(kind) {
        var pair = TITLE_KEYS[kind];
        return pair ? T(pair[0], pair[1]) : '';
    }

    // ------------------------------------------------------------------
    // Primitive helpers
    // ------------------------------------------------------------------
    function rect(x, y, w, h, fill, stroke, extra) {
        return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h +
            '" fill="' + (fill || 'none') + '" stroke="' + (stroke || C.metalLine) +
            '" stroke-width="1.4"' + (extra || '') + '/>';
    }

    function line(x1, y1, x2, y2, stroke, width, dash) {
        return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
            '" stroke="' + (stroke || C.metalLine) + '" stroke-width="' + (width || 1.4) +
            '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>';
    }

    function arrow(x1, y1, x2, y2, stroke) {
        return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
            '" stroke="' + (stroke || C.flow) + '" stroke-width="2" ' +
            'marker-end="url(#hrmaArrow)"/>';
    }

    function label(x, y, text, fill, anchor, size) {
        return '<text x="' + x + '" y="' + y + '" fill="' + (fill || C.dim) +
            '" font-size="' + (size || 10) + '" font-family="var(--hd-mono, monospace)"' +
            ' text-anchor="' + (anchor || 'start') + '">' + text + '</text>';
    }

    // "17 adet, çap 0,81 mm" künyesi — mevcut `inj.radialHolesValue`
    // anahtarı yeniden kullanılır (panelin tablosunda da bu kullanılıyor).
    // Sayı yoksa null döner ve çağıran hiçbir şey çizmez.
    function countLabel(n, dMm, dec) {
        if (n === null && dMm === null) return null;
        if (n !== null && dMm !== null) {
            return TF('inj.radialHolesValue',
                      { n: n, d: fmtN(dMm, dec == null ? 2 : dec) },
                      '{n} x dia {d} mm');
        }
        if (n !== null) return String(n);
        return DIA + fmtN(dMm, dec == null ? 2 : dec) + ' mm';
    }

    function defs() {
        return '<defs>' +
            '<marker id="hrmaArrow" viewBox="0 0 10 10" refX="9" refY="5" ' +
            'markerWidth="5" markerHeight="5" orient="auto-start-reverse">' +
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker>' +
            '</defs>';
    }

    function frame(title, body) {
        return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" ' +
            'preserveAspectRatio="xMidYMid meet" role="img" ' +
            'aria-label="' + title + '" style="color:' + C.flow + ';">' +
            defs() +
            label(W / 2, 16, title, C.metalLine, 'middle', 12) +
            body +
            '</svg>';
    }

    // Shared chamber-side context: centreline + chamber label
    function chamberContext(xManifoldEnd) {
        return line(20, H / 2, W - 16, H / 2, C.dim, 1, '6 4') +
            label(W - 18, H - 12, T('sch.chamberSide', 'chamber side &#8594;'), C.dim, 'end') +
            label(24, H - 12, T('sch.feedManifold', '&#8592; feed manifold'), C.dim, 'start') +
            line(xManifoldEnd, 32, xManifoldEnd, H - 30, C.dim, 1, '3 4');
    }

    // ------------------------------------------------------------------
    // Type drawings
    // ------------------------------------------------------------------
    function showerhead(geom) {
        var px = 150, pw = 40, top = 60, bot = H - 60, cy = H / 2;
        var s = chamberContext(px);
        s += rect(px, top, pw, bot - top, C.metal);          // plate
        // Delik sayısı HESAPTAN gelir; gelmezse beş delikli genel çizim
        // (genel çizimde sayı künyesi BASILMAZ, yani bir iddia yoktur).
        var nOrif = g_int(geom, 'n_orifices');
        var nDraw = drawCount(nOrif) || 5;
        var span = (bot - 22) - (top + 22);
        var ys = [];
        for (var i = 0; i < nDraw; i++) {
            ys.push(nDraw === 1 ? cy : (top + 22) + span * i / (nDraw - 1));
        }
        ys.forEach(function (y) {
            s += rect(px, y - 3, pw, 6, 'var(--hd-bg, #0a1322)', C.flow);
            s += arrow(px + pw + 4, y, px + pw + 62, y, C.flow);
        });
        var tag = countLabel(nOrif, g_(geom, 'orifice_d_mm'));
        if (tag) s += label(px + pw + 66, top + 6, tag, C.flow);
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(px + pw + 66, cy - 6, T('sch.parallelJets', 'parallel axial jets'), C.flow);
        s += label(px + pw / 2, top - 10, T('sch.injectorPlate', 'injector plate'), C.metalLine, 'middle');
        s += line(px, bot + 14, px + pw, bot + 14, C.dim, 1);
        // Etiket sağa yaslanır: sol-alt köşe not bloğuna ayrılmıştır
        s += label(px + pw + 8, bot + 18, T('sch.plateThickness', 'L (plate thickness) &#8594; L/D'),
            C.dim, 'start');
        s += label(24, H - 44, T('sch.dpPlate', 'dP across plate'), C.accent);
        s += label(24, H - 32, T('sch.cdFormula', 'Cd = f(inlet, L/D)'), C.accent);
        return frame(titleOf('showerhead'), s);
    }

    function pintle(geom) {
        var px = 140, pw = 30, cy = H / 2;
        var postLen = 150, rPost = 16, gap = 9;
        // TEK AKIŞKAN mı? Hibritte yakıt grain'den gelir, pintle YALNIZ
        // oksitleyiciyi taşır: radyal delikler de anülüs de oksitleyicidir.
        // Sıvıda düzen yakıt-merkezlidir: radyal = YAKIT, anülüs = OKSİTLEYİCİ.
        // İki hâl aynı resimle çizildiği için kullanıcı hibritte "yakıt
        // radyal püskürtülüyor" izlenimi alıyordu — resim yanlıştı.
        var single = !!(geom && geom.single_fluid);
        var radialColor = single ? C.flow : C.accent;
        var radialFill = single ? 'rgba(0,229,255,0.22)' : 'rgba(255,140,51,0.25)';
        var radialName = single ? T('common.oxidizer', 'Oxidizer')
                                : T('common.fuel', 'Fuel');
        var annulusName = T('common.oxidizer', 'Oxidizer');

        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);                       // plate
        // central post (radyal akışı taşır)
        s += rect(px + pw, cy - rPost, postLen, 2 * rPost, C.metal);
        s += rect(px + pw + 2, cy - rPost + 4, postLen - 6, 2 * rPost - 8,
            radialFill, radialColor);
        // annulus bands (oksitleyici tabakası)
        s += rect(px + pw, cy - rPost - gap, postLen, gap,
            'rgba(0,229,255,0.22)', C.flow);
        s += rect(px + pw, cy + rPost, postLen, gap,
            'rgba(0,229,255,0.22)', C.flow);

        // --- radyal jetler: SAYI HESAPTAN ---------------------------------
        // Eskiden burada SABİT iki ok vardı; panel 17 delik hesaplarken de
        // çizimde 2 ok kalıyordu. Artık delik sayısı kadar (çizilebilir
        // sınıra kadar) ok basılır ve gerçek sayı künyesi yanına yazılır.
        var nHoles = g_int(geom, 'n_radial_holes');
        var nDraw = drawCount(nHoles) || 2;
        var xEnd = px + pw + postLen - 10;
        var xStart = xEnd - Math.min(96, 8 * nDraw);
        var jetLen = 40;
        var theta = g_(geom, 'spray_half_angle_deg');
        // Sprey açısı biliniyorsa oklar gerçek açıyla eğilir; bilinmiyorsa
        // dik çizilir (açı iddiası yok).
        var dx = (theta === null) ? 0 : jetLen * Math.sin(theta * Math.PI / 180);
        var dy = (theta === null) ? jetLen : jetLen * Math.cos(theta * Math.PI / 180);
        for (var i = 0; i < nDraw; i++) {
            var xh = (nDraw === 1) ? xEnd
                : xStart + (xEnd - xStart) * i / (nDraw - 1);
            s += arrow(xh, cy - rPost, xh + dx, cy - rPost - dy, radialColor);
            s += arrow(xh, cy + rPost, xh + dx, cy + rPost + dy, radialColor);
        }
        s += label(xStart - 4, cy - rPost - jetLen - 8,
            T('sch.radialHoles', 'radial holes &#8594; BF'), radialColor, 'end');
        var holeTag = countLabel(nHoles, g_(geom, 'radial_hole_d_mm'));
        if (holeTag) {
            s += label(xStart - 4, cy - rPost - jetLen - 20,
                radialName + ': ' + holeTag, radialColor, 'end');
        }
        if (theta !== null) {
            s += label(xEnd + 8, cy - 6, '2' + 'θ = ' + fmtN(2 * theta, 0) + DEG,
                C.spray, 'start');
        }

        // --- besleme okları ------------------------------------------------
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        if (!single) {
            // İki akışkanlı düzende merkez akım YAKITTIR; tek besleme oku
            // "her şey oksitleyici" izlenimi veriyordu.
            s += arrow(34, 150, px - 8, 150, C.accent);
            s += label(34, 164, radialName, C.accent);
        }

        // --- künyeler --------------------------------------------------------
        var gapMm = g_(geom, 'annulus_gap_mm');
        s += label(px + pw + 6, cy - rPost - gap - 8,
            T('sch.annulusGap', 'annulus gap')
            + (gapMm === null ? '' : ' ' + fmtN(gapMm) + ' mm'), C.flow);
        s += label(px + pw + 6, cy - rPost - gap - 20, annulusName, C.flow);
        var dp = g_(geom, 'd_pintle_mm');
        s += label(px + pw + 6, cy + 4, T('sch.pintlePost', 'pintle post D_p')
            + (dp === null ? '' : ' = ' + fmtN(dp, 1) + ' mm'), C.metalLine);
        // skip distance
        s += line(px + pw, cy + rPost + gap + 26, px + pw + postLen,
            cy + rPost + gap + 26, C.dim, 1);
        var ls = g_(geom, 'skip_distance_mm');
        s += label(px + pw + postLen / 2, cy + rPost + gap + 40,
            ls === null ? T('sch.skipDistance', 'skip distance L_s &#8776; D_p')
                        : 'L_s = ' + fmtN(ls, 1) + ' mm', C.dim, 'middle');
        s += label(24, H - 44, T('sch.dpSheet', 'dP sets sheet velocity'), C.accent);
        var bf = g_(geom, 'bf');
        s += label(24, H - 32, bf === null
            ? T('sch.bfFormula', 'BF = n*d / (pi*D_p)')
            : 'BF = ' + fmtN(bf, 3), C.accent);
        // Hibritte akışın ne kadarının radyal gittiği ÇİZİMDE de yazılır:
        // kullanıcının çevirdiği kol budur (panelde 'Radial flow fraction').
        var fRad = g_(geom, 'radial_flow_fraction');
        if (single && fRad !== null) {
            s += label(24, H - 20, TF('inj.singleFluid',
                { pct: fmtN(fRad * 100, 0) },
                'Single-fluid (oxidizer-centred hybrid pintle); radial flow '
                + 'share {pct}%'), C.dim);
        }
        return frame(titleOf('pintle'), s);
    }

    function swirl(geom) {
        var px = 140, pw = 46, cy = H / 2, rExit = 12;
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);
        // exit orifice
        s += rect(px, cy - rExit, pw, 2 * rExit, 'var(--hd-bg, #0a1322)', C.flow);
        // --- teğet girişler: SAYI HESAPTAN --------------------------------
        var nInlet = g_int(geom, 'tangential_inlets');
        var nDraw = drawCount(nInlet) || 4;
        var slotSpan = 58;
        for (var i = 0; i < nDraw; i++) {
            // simetrik dizilim: yarısı üstte, yarısı altta
            var frac = (nDraw === 1) ? 1 : (i % 2 === 0 ? 1 : -1)
                * (1 - 0.55 * Math.floor(i / 2) / Math.max(1, Math.ceil(nDraw / 2)));
            var dy = slotSpan * frac;
            s += line(px + 4, cy + dy, px + pw - 4, cy + dy * 0.45, C.accent, 3);
        }
        var slotTag = countLabel(nInlet, g_(geom, 'inlet_d_mm'));
        s += label(px + pw + 8, cy - 78, T('sch.tangentialSlots', 'tangential slots')
            + (slotTag ? ' — ' + slotTag : ''), C.accent, 'start');
        // --- içi boş koni spreyi: AÇI HESAPTAN ----------------------------
        var xs = px + pw, reach = 78;
        var theta = g_(geom, 'spray_half_angle_deg');
        // Açı biliniyorsa koni GERÇEK açıyla açılır; bilinmiyorsa temsilî
        // koni çizilir ve sayısal açı künyesi BASILMAZ.
        var spread = (theta === null) ? 62
            : Math.min(H / 2 - 14, reach * Math.tan(theta * Math.PI / 180));
        s += line(xs, cy - rExit, xs + reach, cy - rExit - spread, C.spray, 2);
        s += line(xs, cy + rExit, xs + reach, cy + rExit + spread, C.spray, 2);
        s += line(xs + reach, cy - rExit - spread, xs + reach, cy + rExit + spread,
            C.spray, 1, '4 4');
        s += label(xs + reach + 6, cy - 4, T('sch.sprayCone', 'spray cone 2&#952;'), C.spray);
        if (theta !== null) {
            s += label(xs + reach + 6, cy + 10,
                '2' + 'θ = ' + fmtN(2 * theta, 0) + DEG, C.spray);
        }
        var film = g_(geom, 'film_thickness_mm');
        if (film !== null) {
            s += label(px + pw + 8, cy + 78, 't = ' + fmtN(film, 3) + ' mm', C.flow);
        }
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        var K = g_(geom, 'K');
        s += label(24, H - 44, T('sch.dpSwirl', 'dP &#8594; swirl number K')
            + (K === null ? '' : ' = ' + fmtN(K, 2)), C.accent);
        s += label(24, H - 32, T('sch.cdFromK', 'Cd from K (below plain orifice)'), C.accent);
        return frame(titleOf('swirl'), s);
    }

    function impingement(geom) {
        var px = 150, pw = 36, cy = H / 2;
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);
        // --- eleman sayısı HESAPTAN ---------------------------------------
        var nElem = g_int(geom, 'n_elements');
        if (nElem === null) nElem = g_int(geom, 'n_orifices');
        var nDraw = Math.min(drawCount(nElem) || 3, 5);   // dikey yer sınırı
        var pairs = [];
        for (var k = 0; k < nDraw; k++) {
            pairs.push(nDraw === 1 ? 0 : -52 + 104 * k / (nDraw - 1));
        }
        // Çarpışma yarım açısı biliniyorsa jetler o açıyla birleşir.
        var half = g_(geom, 'half_angle_deg');
        pairs.forEach(function (dy) {
            var y = cy + dy;
            // two angled bores converging to one impingement point
            s += line(px, y - 14, px + pw, y - 6, C.flow, 3);
            s += line(px, y + 14, px + pw, y + 6, C.flow, 3);
            // Serbest jet boyu açıdan türer: dar açıda jetler daha geç
            // buluşur. Açı yoksa eski temsilî uzaklık kullanılır.
            var reachX = (half === null) ? 46
                : Math.max(18, Math.min(84, 6 / Math.tan(
                    Math.max(5, half) * Math.PI / 180)));
            var xi = px + pw + reachX;
            s += line(px + pw, y - 6, xi, y, C.flow, 2);
            s += line(px + pw, y + 6, xi, y, C.flow, 2);
            s += '<circle cx="' + xi + '" cy="' + y + '" r="3" fill="' + C.accent + '"/>';
            s += line(xi, y, xi + 40, y - 22, C.spray, 1.6);
            s += line(xi, y, xi + 40, y + 22, C.spray, 1.6);
        });
        s += label(px + pw + 52, cy - 66, T('sch.impingePoint', 'impingement point'), C.accent);
        s += label(px + pw + 52, cy + 76, T('sch.sprayFan', 'flat spray fan'), C.spray);
        s += label(px + pw / 2, 44, T('sch.includedAngle', 'included angle 2&#952;')
            + (half === null ? '' : ' = ' + fmtN(2 * half, 0) + DEG),
            C.metalLine, 'middle');
        var elemTag = countLabel(nElem, g_(geom, 'orifice_d_mm'));
        if (elemTag) s += label(px + pw / 2, 32, elemTag, C.flow, 'middle');
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(24, H - 44, T('sch.dpJet', 'dP &#8594; jet velocity'), C.accent);
        s += label(24, H - 32, T('sch.weberFormula', 'We = rho*v^2*d / sigma'), C.accent);
        return frame(titleOf('impingement'), s);
    }

    function coaxial(geom) {
        var px = 140, pw = 30, cy = H / 2;
        var rIn = 13, wall = 5, gap = 11, len = 140;
        // Tek akışkanlı (hibrit) coax'ta iç jet ve dış anülüs AYNI akışkandır;
        // sıvıda iki ayrı devre vardır. Renk/ad ayrımı buradan gelir.
        var single = !!(geom && geom.single_fluid);
        var outerName = single ? T('common.oxidizer', 'Oxidizer')
                               : T('common.fuel', 'Fuel');
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);
        // inner post/tube
        s += rect(px + pw, cy - rIn - wall, len, wall, C.metal);
        s += rect(px + pw, cy + rIn, len, wall, C.metal);
        // inner jet passage
        s += rect(px + pw, cy - rIn, len, 2 * rIn, 'rgba(0,229,255,0.22)', C.flow);
        // outer annulus
        s += rect(px + pw, cy - rIn - wall - gap, len, gap,
            'rgba(255,140,51,0.25)', C.accent);
        s += rect(px + pw, cy + rIn + wall, len, gap,
            'rgba(255,140,51,0.25)', C.accent);
        var xe = px + pw + len;
        s += arrow(xe + 4, cy, xe + 56, cy, C.flow);
        s += arrow(xe + 4, cy - rIn - wall - gap / 2, xe + 46,
            cy - rIn - wall - gap / 2 - 18, C.accent);
        s += arrow(xe + 4, cy + rIn + wall + gap / 2, xe + 46,
            cy + rIn + wall + gap / 2 + 18, C.accent);
        var dIn = g_(geom, 'orifice_d_mm');
        s += label(px + pw + 6, cy + 4, T('sch.innerJet', 'inner jet')
            + (dIn === null ? '' : ' ' + DIA + fmtN(dIn) + ' mm'), C.flow);
        s += label(px + pw + 6, cy - rIn - wall - gap - 8,
            T('sch.outerAnnulus', 'outer annulus') + ' — ' + outerName, C.accent);
        var gapMm = g_(geom, 'annulus_gap_mm');
        if (gapMm !== null) {
            s += label(px + pw + 6, cy - rIn - wall - gap - 20,
                't = ' + fmtN(gapMm) + ' mm', C.accent);
        }
        s += line(px + pw, cy + rIn + wall + gap + 26, px + pw + 40,
            cy + rIn + wall + gap + 26, C.dim, 1);
        s += label(px + pw + 44, cy + rIn + wall + gap + 30,
            T('sch.recess', 'recess &#8776; 1&#183;d_inner'), C.dim);
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(24, H - 44, T('sch.dpShared', 'dP shared by both passages'), C.accent);
        // 'same fluid' notu YALNIZ tek akışkanlı düzende doğrudur; sıvı
        // iki devreli coax'ta bu not yanlış bilgi veriyordu.
        if (single) {
            s += label(24, H - 32,
                T('sch.coaxNote', 'inner jet + outer annulus (same fluid)'), C.accent);
        }
        return frame(titleOf('coaxial'), s);
    }

    var BUILDERS = {
        showerhead: showerhead,
        pintle: pintle,
        swirl: swirl,
        impingement: impingement,
        coaxial: coaxial
    };

    function resolve(type) {
        return ALIASES[String(type || '').toLowerCase()] || 'showerhead';
    }

    // geom İSTEĞE BAĞLIDIR: verilmezse tipin genel çizimi basılır ve
    // hiçbir sayısal künye yazılmaz (uydurma değer yok).
    function svg(type, geom) {
        return BUILDERS[resolve(type)](geom || null);
    }

    function render(type, el, geom) {
        var node = (typeof el === 'string') ? document.getElementById(el) : el;
        if (!node) return null;
        node.innerHTML = svg(type, geom);
        return node;
    }

    window.InjectorSchematics = {
        svg: svg,
        render: render,
        resolve: resolve,
        types: function () { return Object.keys(BUILDERS); },
        title: function (type) { return titleOf(resolve(type)); }
    };
})();
