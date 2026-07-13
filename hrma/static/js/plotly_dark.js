/*
 * HRMA koyu tema — Plotly sarmalayıcı.
 *
 * Plotly.newPlot / Plotly.react çağrılarını sarmalayıp TÜM grafikleri
 * (backend'den beyaz layout ile gelenler dahil) tek merkezden karanlık
 * temaya çevirir. Plotly script'inden SONRA, sayfa script'lerinden ÖNCE
 * yüklenmelidir. Kaldırmak için <script> satırını silmek yeterli.
 *
 * 2026-07-13 okunabilirlik katmanı: eksenlerde automargin + başlık
 * standoff, başlık/legend çakışma önleme (üst-legend kelepçesi + üst
 * marj garantisi), annotation'lara zemin pili, hover etiketi teması.
 * Amaç: "çizgiler yazılarla iç içe giriyor" sınıfı sorunları tüm
 * grafiklerde tek merkezden bitirmek.
 */
(function () {
    'use strict';
    if (typeof Plotly === 'undefined' || Plotly.__hrmaDark) return;
    Plotly.__hrmaDark = true;

    var INK = '#cfe8f2', INK_DIM = '#7d97a5';
    var GRID = 'rgba(0, 229, 255, 0.08)';
    // Koyu zeminde kaybolan koyu trace renkleri → açık mürekkep
    var COLOR_FIX = {
        'black': '#d7e3ee', '#000': '#d7e3ee', '#000000': '#d7e3ee',
        'rgb(0,0,0)': '#d7e3ee', 'darkblue': '#7cc4ff', 'navy': '#7cc4ff',
        'darkgreen': '#5fd6a5', 'darkred': '#ff7a85', 'saddlebrown': '#c98a55'
    };

    function fixColor(c) {
        return (typeof c === 'string' && COLOR_FIX[c.toLowerCase()]) || c;
    }

    function fixTrace(tr) {
        if (!tr || typeof tr !== 'object') return;
        if (tr.line) tr.line.color = fixColor(tr.line.color);
        if (tr.marker) {
            tr.marker.color = Array.isArray(tr.marker.color)
                ? tr.marker.color.map(fixColor) : fixColor(tr.marker.color);
            if (tr.marker.line) tr.marker.line.color = fixColor(tr.marker.line.color);
        }
        if (tr.textfont) tr.textfont.color = fixColor(tr.textfont.color);
    }

    function darkenAxis(ax) {
        if (!ax || typeof ax !== 'object') return;
        ax.gridcolor = GRID;
        ax.zerolinecolor = 'rgba(0, 229, 255, 0.18)';
        ax.linecolor = 'rgba(125, 151, 165, 0.35)';
        // Tick etiketleri kesilmesin / eksen başlığına binmesin
        if (ax.automargin === undefined) ax.automargin = true;
        ax.tickfont = Object.assign({ size: 11 }, ax.tickfont, { color: INK_DIM });
        if (typeof ax.title === 'string') ax.title = { text: ax.title };
        if (ax.title) {
            ax.title.font = Object.assign({ size: 12 }, ax.title.font, { color: INK_DIM });
            // Eksen başlığı ile tick etiketleri arasına nefes payı
            if (ax.title.standoff === undefined) ax.title.standoff = 8;
        }
    }

    function applyDarkLayout(layout) {
        layout = layout || {};
        layout.paper_bgcolor = 'rgba(0,0,0,0)';
        layout.plot_bgcolor = 'rgba(8, 16, 28, 0.35)';
        layout.font = Object.assign({ size: 12 }, layout.font, { color: INK });
        if (typeof layout.title === 'string') layout.title = { text: layout.title };
        if (layout.title) {
            layout.title.font = Object.assign({}, layout.title.font, { color: '#eaf7fb' });
        }
        Object.keys(layout).forEach(function (k) {
            if (/^[xy]axis\d*$/.test(k)) darkenAxis(layout[k]);
            if (/^scene\d*$/.test(k) && layout[k] && typeof layout[k] === 'object') {
                var sc = layout[k];
                sc.bgcolor = 'rgba(0,0,0,0)';
                ['xaxis', 'yaxis', 'zaxis'].forEach(function (a) {
                    if (sc[a]) {
                        sc[a].gridcolor = 'rgba(0, 229, 255, 0.12)';
                        sc[a].color = INK_DIM;
                        sc[a].backgroundcolor = 'rgba(0,0,0,0)';
                    }
                });
            }
        });
        layout.legend = layout.legend || {};
        layout.legend.bgcolor = 'rgba(6, 13, 24, 0.7)';
        layout.legend.bordercolor = 'rgba(0, 229, 255, 0.2)';
        layout.legend.font = Object.assign({}, layout.legend.font, { color: INK_DIM });

        // --- Okunabilirlik: başlık / üst-legend / marj çakışmaları -------
        var hasTitle = !!(layout.title && layout.title.text);
        var lg = layout.legend;
        var legendAbove = lg.orientation === 'h' &&
            typeof lg.y === 'number' && lg.y >= 1;
        if (legendAbove) {
            // y:1.1+ değerleri legend'ı başlık bölgesine taşırıyordu;
            // grafiğin hemen üstüne kenetle, kalan boşluğu marj sağlasın
            if (lg.yanchor === undefined) lg.yanchor = 'bottom';
            if (lg.y > 1.04) lg.y = 1.02;
        }
        var m = layout.margin;
        if (m) {
            // Açıkça verilmiş dar üst marj, başlığı grafiğin içine sokuyor
            if (hasTitle && (m.t === undefined || m.t < 60)) m.t = 60;
            if (hasTitle && legendAbove && m.t < 96) m.t = 96;
        } else if (hasTitle && legendAbove) {
            // Plotly varsayılanı (t=100) başlık+üst-legend ikilisine dar
            layout.margin = { t: 110 };
        }

        // Hover etiketi: koyu zeminde okunur kutu
        layout.hoverlabel = Object.assign({
            bgcolor: 'rgba(6, 13, 24, 0.95)',
            bordercolor: 'rgba(0, 229, 255, 0.35)',
            font: { color: INK, size: 12 }
        }, layout.hoverlabel);

        (layout.annotations || []).forEach(function (an) {
            if (!an.font) an.font = {};
            var c = (an.font.color || '').toLowerCase();
            if (!an.font.color || c === 'black' || c === '#000000' || c === '#000') {
                an.font.color = INK;
            }
            // Veri çizgilerinin üstünden geçen etiketlere zemin pili —
            // "yazı çizgiyle iç içe" şikâyetinin genel çözümü
            if (an.text && an.bgcolor === undefined) {
                an.bgcolor = 'rgba(6, 13, 24, 0.62)';
                if (an.borderpad === undefined) an.borderpad = 2;
            }
        });
        return layout;
    }

    function wrap(fnName) {
        var orig = Plotly[fnName] && Plotly[fnName].bind(Plotly);
        if (!orig) return;
        Plotly[fnName] = function (el, data, layout, config) {
            try {
                if (Array.isArray(data)) data.forEach(fixTrace);
                layout = applyDarkLayout(layout);
            } catch (e) {
                console.warn('HRMA dark theme patch failed, rendering as-is:', e);
            }
            return orig(el, data, layout, config);
        };
    }

    wrap('newPlot');
    wrap('react');
})();
