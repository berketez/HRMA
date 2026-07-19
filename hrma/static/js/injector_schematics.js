/* ====================================================================
   HRMA Injector Schematics — inline SVG cross-sections
   --------------------------------------------------------------------
   Theme-aware labelled schematics for every injector type the solver
   supports. Strokes/fills use currentColor and CSS variables so the same
   markup reads correctly on the dark application theme and on a light
   print background.

   Public API (kept stable — advanced.html and injector_panel.js both
   bind to it):
       window.InjectorSchematics.svg(type)        -> SVG markup string
       window.InjectorSchematics.render(type, el) -> injects into element
       window.InjectorSchematics.types()          -> supported type list

   Accepted type strings (aliases resolve to five canonical drawings):
       showerhead | pintle | swirl | impingement | coaxial
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
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
    function showerhead() {
        var px = 150, pw = 40, top = 60, bot = H - 60, cy = H / 2;
        var s = chamberContext(px);
        s += rect(px, top, pw, bot - top, C.metal);          // plate
        var ys = [top + 22, top + 50, cy, bot - 50, bot - 22];
        ys.forEach(function (y) {
            s += rect(px, y - 3, pw, 6, 'var(--hd-bg, #0a1322)', C.flow);
            s += arrow(px + pw + 4, y, px + pw + 62, y, C.flow);
        });
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

    function pintle() {
        var px = 140, pw = 30, cy = H / 2;
        var postLen = 150, rPost = 16, gap = 9;
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);                       // plate
        // central post
        s += rect(px + pw, cy - rPost, postLen, 2 * rPost, C.metal);
        // annulus bands (oxidizer sheet)
        s += rect(px + pw, cy - rPost - gap, postLen, gap,
            'rgba(0,229,255,0.22)', C.flow);
        s += rect(px + pw, cy + rPost, postLen, gap,
            'rgba(0,229,255,0.22)', C.flow);
        // radial jets at the tip
        var xTip = px + pw + postLen - 18;
        s += arrow(xTip, cy - rPost, xTip, cy - rPost - 44, C.accent);
        s += arrow(xTip, cy + rPost, xTip, cy + rPost + 44, C.accent);
        s += label(xTip + 6, cy - rPost - 48, T('sch.radialHoles', 'radial holes &#8594; BF'), C.accent);
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(px + pw + 6, cy - rPost - gap - 8, T('sch.annulusGap', 'annulus gap'), C.flow);
        s += label(px + pw + 6, cy + 4, T('sch.pintlePost', 'pintle post D_p'), C.metalLine);
        // skip distance
        s += line(px + pw, cy + rPost + gap + 26, px + pw + postLen,
            cy + rPost + gap + 26, C.dim, 1);
        s += label(px + pw + postLen / 2, cy + rPost + gap + 40,
            T('sch.skipDistance', 'skip distance L_s &#8776; D_p'), C.dim, 'middle');
        s += label(24, H - 44, T('sch.dpSheet', 'dP sets sheet velocity'), C.accent);
        s += label(24, H - 32, T('sch.bfFormula', 'BF = n*d / (pi*D_p)'), C.accent);
        return frame(titleOf('pintle'), s);
    }

    function swirl() {
        var px = 140, pw = 46, cy = H / 2, rExit = 12;
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);
        // exit orifice
        s += rect(px, cy - rExit, pw, 2 * rExit, 'var(--hd-bg, #0a1322)', C.flow);
        // tangential slots feeding the swirl chamber
        [-58, -30, 30, 58].forEach(function (dy) {
            s += line(px + 4, cy + dy, px + pw - 4, cy + dy * 0.45, C.accent, 3);
        });
        s += label(px + pw + 8, cy - 78, T('sch.tangentialSlots', 'tangential slots'), C.accent, 'start');
        // hollow-cone spray
        var xs = px + pw, reach = 78;
        s += line(xs, cy - rExit, xs + reach, cy - rExit - 62, C.spray, 2);
        s += line(xs, cy + rExit, xs + reach, cy + rExit + 62, C.spray, 2);
        s += line(xs + reach, cy - rExit - 62, xs + reach, cy + rExit + 62,
            C.spray, 1, '4 4');
        s += label(xs + reach + 6, cy - 4, T('sch.sprayCone', 'spray cone 2&#952;'), C.spray);
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(24, H - 44, T('sch.dpSwirl', 'dP &#8594; swirl number K'), C.accent);
        s += label(24, H - 32, T('sch.cdFromK', 'Cd from K (below plain orifice)'), C.accent);
        return frame(titleOf('swirl'), s);
    }

    function impingement() {
        var px = 150, pw = 36, cy = H / 2;
        var s = chamberContext(px);
        s += rect(px, 55, pw, H - 110, C.metal);
        var pairs = [-52, 0, 52];
        pairs.forEach(function (dy) {
            var y = cy + dy;
            // two angled bores converging to one impingement point
            s += line(px, y - 14, px + pw, y - 6, C.flow, 3);
            s += line(px, y + 14, px + pw, y + 6, C.flow, 3);
            var xi = px + pw + 46;
            s += line(px + pw, y - 6, xi, y, C.flow, 2);
            s += line(px + pw, y + 6, xi, y, C.flow, 2);
            s += '<circle cx="' + xi + '" cy="' + y + '" r="3" fill="' + C.accent + '"/>';
            s += line(xi, y, xi + 40, y - 22, C.spray, 1.6);
            s += line(xi, y, xi + 40, y + 22, C.spray, 1.6);
        });
        s += label(px + pw + 52, cy - 66, T('sch.impingePoint', 'impingement point'), C.accent);
        s += label(px + pw + 52, cy + 76, T('sch.sprayFan', 'flat spray fan'), C.spray);
        s += label(px + pw / 2, 44, T('sch.includedAngle', 'included angle 2&#952;'), C.metalLine, 'middle');
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(24, H - 44, T('sch.dpJet', 'dP &#8594; jet velocity'), C.accent);
        s += label(24, H - 32, T('sch.weberFormula', 'We = rho*v^2*d / sigma'), C.accent);
        return frame(titleOf('impingement'), s);
    }

    function coaxial() {
        var px = 140, pw = 30, cy = H / 2;
        var rIn = 13, wall = 5, gap = 11, len = 140;
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
        s += label(px + pw + 6, cy + 4, T('sch.innerJet', 'inner jet'), C.flow);
        s += label(px + pw + 6, cy - rIn - wall - gap - 8, T('sch.outerAnnulus', 'outer annulus'), C.accent);
        s += line(px + pw, cy + rIn + wall + gap + 26, px + pw + 40,
            cy + rIn + wall + gap + 26, C.dim, 1);
        s += label(px + pw + 44, cy + rIn + wall + gap + 30,
            T('sch.recess', 'recess &#8776; 1&#183;d_inner'), C.dim);
        s += arrow(34, 104, px - 8, 104, C.flow);
        s += label(34, 96, T('sch.mdotOx', 'mdot_ox (kg/s)'), C.flow);
        s += label(24, H - 44, T('sch.dpShared', 'dP shared by both passages'), C.accent);
        s += label(24, H - 32, T('sch.coaxNote', 'inner jet + outer annulus (same fluid)'), C.accent);
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

    function svg(type) {
        return BUILDERS[resolve(type)]();
    }

    function render(type, el) {
        var node = (typeof el === 'string') ? document.getElementById(el) : el;
        if (!node) return null;
        node.innerHTML = svg(type);
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
