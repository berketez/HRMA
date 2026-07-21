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
 *
 * 2026-07-19 dil katmanı: grafik metinleri (başlık, eksen, seri adı,
 * anotasyon, hover şablonu, gösterge etiketi) sunucuda ve panel JS'lerinde
 * ~250 ayrı yerde üretiliyor. Hepsini tek tek çevirmek yerine burada,
 * TEK BOĞAZDAN çevriliyor: translateFigure() metinleri i18n_charts.js
 * sözlüğünden geçirir. Sözlükte olmayan metin OLDUĞU GİBİ kalır.
 * Kaynak (İngilizce) metin her nesnede gizli bir alanda saklanır, böylece
 * dil ileri-geri değiştirilse de çeviri hep İngilizce kaynaktan yapılır.
 */
(function () {
    'use strict';
    if (typeof Plotly === 'undefined' || Plotly.__hrmaDark) return;
    Plotly.__hrmaDark = true;

    var INK = '#cfe8f2', INK_DIM = '#7d97a5';
    var GRID = 'rgba(0, 229, 255, 0.08)';
    var CYAN = '#00e5ff';
    var MONO = "'JetBrains Mono', 'SF Mono', Consolas, monospace";
    // HUD ek 1: kurumsal renk sırası (theme.css paletiyle hizalı)
    var COLORWAY = ['#00e5ff', '#ff8c33', '#2dd4a8', '#ff5d73',
                    '#c792ea', '#ffd166', '#7cc4ff', '#f78fb3'];
    // Koyu zeminde kaybolan koyu trace renkleri → açık mürekkep
    var COLOR_FIX = {
        'black': '#d7e3ee', '#000': '#d7e3ee', '#000000': '#d7e3ee',
        'rgb(0,0,0)': '#d7e3ee', 'darkblue': '#7cc4ff', 'navy': '#7cc4ff',
        'darkgreen': '#5fd6a5', 'darkred': '#ff7a85', 'saddlebrown': '#c98a55',
        // v2.5.5 gauge emniyet katmanı: koyu gösterge renkleri de düzeltilir
        'darkorange': '#ff8c33', 'teal': '#2dd4a8'
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
        // v2.5.5 emniyet katmanı: gauge (indicator) renkleri — sunucu tarafı
        // paletten beslenmemiş eski/yabancı figürlerde koyu bar/step/threshold
        // renkleri koyu zeminde kayboluyordu. Python tarafı zaten PALETTE
        // kullanır; burası yalnız kaçakları yakalar.
        if (tr.gauge && typeof tr.gauge === 'object') {
            var g = tr.gauge;
            if (g.bar) g.bar.color = fixColor(g.bar.color);
            if (Array.isArray(g.steps)) {
                g.steps.forEach(function (st) {
                    if (st && typeof st === 'object') st.color = fixColor(st.color);
                });
            }
            if (g.threshold && g.threshold.line) {
                g.threshold.line.color = fixColor(g.threshold.line.color);
            }
        }
    }

    function darkenAxis(ax) {
        if (!ax || typeof ax !== 'object') return;
        ax.gridcolor = GRID;
        ax.zerolinecolor = 'rgba(0, 229, 255, 0.18)';
        ax.linecolor = 'rgba(125, 151, 165, 0.35)';
        // Tick etiketleri kesilmesin / eksen başlığına binmesin
        if (ax.automargin === undefined) ax.automargin = true;
        // HUD ek 2: cyan noktalı crosshair (yalnız sayfa tanımlamadıysa)
        if (ax.showspikes === undefined) {
            ax.showspikes = true;
            ax.spikecolor = 'rgba(0, 229, 255, 0.55)';
            ax.spikethickness = 1;
            ax.spikedash = 'dot';
            ax.spikemode = 'across';
        }
        // HUD ek 4: tick etiketleri JetBrains Mono (sayfa fontu öncelikli)
        ax.tickfont = Object.assign({ size: 11, family: MONO }, ax.tickfont, { color: INK_DIM });
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
        // HUD ek 1: renk sırası — yalnız tanımsızsa (sayfa override'ı korunur)
        if (layout.colorway === undefined) layout.colorway = COLORWAY;
        // HUD ek 3: modebar teması
        layout.modebar = Object.assign({
            bgcolor: 'rgba(0,0,0,0)',
            color: INK_DIM,
            activecolor: CYAN
        }, layout.modebar);
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

    // Okunabilirlik: 4+ trace'li grafikte sayfa legend konumu vermediyse
    // dikey legend sağda veriyi kapatabiliyor — yatay alta al, alt marjı aç.
    function maybeBottomLegend(data, layout) {
        if (!Array.isArray(data) || data.length < 4 || !layout) return;
        var lg = layout.legend || {};
        if (lg.orientation !== undefined || lg.x !== undefined || lg.y !== undefined) return;
        lg.orientation = 'h';
        lg.y = -0.25;
        lg.yanchor = 'top';
        layout.legend = lg;
        layout.margin = layout.margin || {};
        if (layout.margin.b === undefined || layout.margin.b < 80) layout.margin.b = 80;
    }

    // HUD ek 5: KOŞULLU 'x unified' hover — yalnız çok-trace 2B scatter
    // grafiklerde ve sayfa hovermode tanımlamadıysa. Pasta/heatmap/3B
    // grafiklere dokunulmaz; tek trace'te Plotly varsayılanı kalır.
    function maybeUnifiedHover(data, layout) {
        if (!layout || layout.hovermode !== undefined) return;
        if (!Array.isArray(data) || data.length < 2) return;
        var all2dScatter = data.every(function (tr) {
            if (!tr || typeof tr !== 'object') return false;
            var t = tr.type || 'scatter'; // tip verilmemişse Plotly scatter sayar
            return t === 'scatter' || t === 'scattergl';
        });
        if (all2dScatter) layout.hovermode = 'x unified';
    }

    /* ==================================================================
       DİL KATMANI — grafik metinlerini tek boğazdan çevirir
       ==================================================================
       Sözlük ve çeviri kuralları i18n_charts.js'te; burada yalnız figürün
       hangi alanlarının metin taşıdığı bilinir. i18n_charts.js yüklü
       değilse tüm katman sessizce devre dışı kalır (grafik İngilizce
       çizilir, hiçbir şey bozulmaz).
    */

    var SRC_KEY = '__hrmaEnSource';   // nesne üstünde saklanan İngilizce kaynak

    function translator() {
        var api = (typeof window !== 'undefined' &&
                   (window.I18N || window.HRMAChartI18N)) || null;
        return (api && typeof api.chartText === 'function') ? api.chartText : null;
    }

    /* Kaynağı (ilk görülen İngilizce değeri) numaralandırılamaz bir alanda
       saklar. Böylece Plotly'nin JSON çıktısına, toImage'a ve dışa
       aktarmalara sızmaz; buna karşın dil değişiminde geri dönülebilir. */
    function sourceOf(obj, prop, current) {
        var store = obj[SRC_KEY];
        if (!store) {
            store = {};
            try {
                Object.defineProperty(obj, SRC_KEY, {
                    value: store, enumerable: false, writable: true, configurable: true
                });
            } catch (e) {
                obj[SRC_KEY] = store;       // defineProperty yoksa düz atama
            }
        }
        if (!Object.prototype.hasOwnProperty.call(store, prop)) store[prop] = current;
        return store[prop];
    }

    /* obj[prop] metnini çevirir. Çeviri HER ZAMAN saklanan İngilizce
       kaynaktan yapılır → ileri-geri dil değişimi metni bozmaz. */
    function tset(obj, prop, tr) {
        if (!obj || typeof obj !== 'object') return;
        var value = obj[prop];
        if (typeof value === 'string') {
            obj[prop] = tr(sourceOf(obj, prop, value));
            return;
        }
        if (Array.isArray(value)) {
            if (value.length > 500) return;          // devasa etiket dizilerini atla
            var src = sourceOf(obj, prop, value.slice());
            var out = [];
            for (var i = 0; i < src.length; i++) {
                out.push(typeof src[i] === 'string' ? tr(src[i]) : src[i]);
            }
            obj[prop] = out;
        }
    }

    /* Plotly başlıkları hem düz metin hem {text: ...} olabilir. */
    function tTitle(owner, tr) {
        if (!owner || typeof owner !== 'object') return;
        if (typeof owner.title === 'string') {
            tset(owner, 'title', tr);
        } else if (owner.title && typeof owner.title === 'object') {
            tset(owner.title, 'text', tr);
        }
    }

    function tAxis(ax, tr) {
        if (!ax || typeof ax !== 'object') return;
        tTitle(ax, tr);
        tset(ax, 'ticksuffix', tr);
        if (Array.isArray(ax.ticktext)) tset(ax, 'ticktext', tr);
    }

    function tLayout(layout, tr) {
        if (!layout || typeof layout !== 'object') return;
        tTitle(layout, tr);

        Object.keys(layout).forEach(function (k) {
            var v = layout[k];
            if (/^[xyz]axis\d*$/.test(k)) tAxis(v, tr);
            if (/^(scene|polar|ternary)\d*$/.test(k) && v && typeof v === 'object') {
                ['xaxis', 'yaxis', 'zaxis', 'radialaxis', 'angularaxis',
                 'aaxis', 'baxis', 'caxis'].forEach(function (a) { tAxis(v[a], tr); });
            }
        });

        if (layout.legend) tTitle(layout.legend, tr);
        if (layout.coloraxis && layout.coloraxis.colorbar) tAxis(layout.coloraxis.colorbar, tr);

        (layout.annotations || []).forEach(function (an) { tset(an, 'text', tr); });
        (layout.shapes || []).forEach(function (sh) { tset(sh, 'name', tr); });

        (layout.updatemenus || []).forEach(function (menu) {
            (menu.buttons || []).forEach(function (b) { tset(b, 'label', tr); });
        });
        (layout.sliders || []).forEach(function (sl) {
            if (sl.currentvalue) tset(sl.currentvalue, 'prefix', tr);
            (sl.steps || []).forEach(function (st) { tset(st, 'label', tr); });
        });
    }

    function tTrace(tr_, tr) {
        if (!tr_ || typeof tr_ !== 'object') return;
        tset(tr_, 'name', tr);
        tset(tr_, 'hovertemplate', tr);
        tset(tr_, 'hovertext', tr);
        tset(tr_, 'text', tr);
        // legendgroup BİLEREK çevrilmez: görünmez bir gruplama anahtarıdır,
        // çevrilirse aynı gruptaki seriler birbirinden kopar.
        if (tr_.legendgrouptitle) tset(tr_.legendgrouptitle, 'text', tr);

        // indicator / gauge: başlık trace üstünde, eksen başlığı gauge içinde
        tTitle(tr_, tr);
        if (tr_.gauge) tAxis(tr_.gauge.axis, tr);

        if (tr_.colorbar) tAxis(tr_.colorbar, tr);
        if (tr_.marker && tr_.marker.colorbar) tAxis(tr_.marker.colorbar, tr);

        // table trace: başlık satırı ve hücreler
        ['header', 'cells'].forEach(function (part) {
            var p = tr_[part];
            if (!p || !Array.isArray(p.values)) return;
            for (var i = 0; i < p.values.length; i++) {
                if (Array.isArray(p.values[i])) {
                    tset(p.values, i, tr);
                } else if (typeof p.values[i] === 'string') {
                    tset(p.values, i, tr);
                }
            }
        });
    }

    /* Figürü yerinde çevirir. İngilizce dilde hiçbir şey değişmez. */
    function translateFigure(data, layout) {
        var tr = translator();
        if (!tr) return;
        if (Array.isArray(data)) data.forEach(function (t) { tTrace(t, tr); });
        tLayout(layout, tr);
    }

    /* ==================================================================
       PNG DIŞA AKTARIM KATMANI (v2.5.5)
       ==================================================================
       Sorun: sayfa temasında paper_bgcolor saydamdır (yıldızlı zemin
       görünsün diye); modebar'ın kamera düğmesi bu yüzden SAYDAM PNG
       üretiyordu — beyaz zeminde açılınca açık renkli yazılar okunmuyordu.

       Çözüm iki parça:
       1) Plotly.downloadImage sarmalanır: dışa aktarım ANINDA layout'a
          geçici opak koyu zemin (#08101c) yazılır, çağrı döner dönmez geri
          alınır. plotly.js 1.58.5 to_image.js layout'u çağrı İÇİNDE senkron
          klonladığı için (extendDeep) bu güvenlidir; ekrandaki grafik hiç
          yeniden çizilmez.
       2) Modebar'ın yerleşik kamera düğmesi downloadImage'ı registry
          üzerinden çağırdığından (sarmalamayı GÖRMEZ), yerleşik düğme
          kaldırılıp aynı ikonla sarmalanmış downloadImage'ı çağıran eşdeğer
          düğme eklenir. Varsayılan dışa aktarım: png, scale 2 — width/height
          BİLEREK verilmez, ekrandaki boyutun 2 katı çözünürlük alınır.
    */
    var EXPORT_BG = '#08101c';
    var EXPORT_IMAGE_DEFAULTS = { format: 'png', scale: 2 };
    var CAMERA_ICON = Plotly.Icons && Plotly.Icons.camera;

    (function wrapDownloadImage() {
        var orig = Plotly.downloadImage && Plotly.downloadImage.bind(Plotly);
        if (!orig) return;
        Plotly.downloadImage = function (gd, opts) {
            var el = (typeof gd === 'string') ? document.getElementById(gd) : gd;
            var lay = el && el.layout;
            if (!lay || typeof lay !== 'object') return orig(gd, opts);
            var hadPaper = Object.prototype.hasOwnProperty.call(lay, 'paper_bgcolor');
            var prevPaper = lay.paper_bgcolor;
            lay.paper_bgcolor = EXPORT_BG;
            try {
                return orig(el, opts);
            } finally {
                // to_image layout'u yukarıdaki çağrı içinde senkron klonladı;
                // ekrandaki grafiğe dokunmadan hemen geri alınabilir.
                if (hadPaper) lay.paper_bgcolor = prevPaper;
                else delete lay.paper_bgcolor;
            }
        };
    })();

    var TO_IMAGE_BUTTON = {
        __hrmaToImage: true,
        name: 'toImage',
        title: 'Download plot as a png',
        icon: CAMERA_ICON,
        click: function (gd) {
            var opts = Object.assign({}, EXPORT_IMAGE_DEFAULTS,
                (gd && gd._context && gd._context.toImageButtonOptions) || {});
            Plotly.downloadImage(gd, opts);
        }
    };

    function hasOurToImageButton(ctx) {
        return !!(ctx && Array.isArray(ctx.modeBarButtonsToAdd) &&
            ctx.modeBarButtonsToAdd.some(function (b) {
                return b && b.__hrmaToImage;
            }));
    }

    /* Config'i dışa aktarım katmanıyla zenginleştirir. Sayfanın verdiği
       config nesnesi MUTASYONA uğratılmaz (sığ kopya döner); config hiç
       verilmemişse ve grafik daha önce işlenmişse bağlama dokunulmaz
       (react'te mevcut ayarları ezmemek için undefined döner). */
    function applyExportConfig(el, config) {
        var gd = (typeof el === 'string') ? document.getElementById(el) : el;
        var ctx = gd && gd._context;
        if (config === undefined || config === null) {
            if (hasOurToImageButton(ctx)) return config;
            config = {};
        }
        if (typeof config !== 'object' || Array.isArray(config)) return config;
        var cfg = Object.assign({}, config);
        // Varsayılan: png + 2x çözünürlük; sabit width/height DAYATILMAZ
        // (ekrandaki gerçek en-boy oranı korunur). Sayfa override edebilir.
        cfg.toImageButtonOptions = Object.assign({}, EXPORT_IMAGE_DEFAULTS,
            (ctx && ctx.toImageButtonOptions) || {},
            cfg.toImageButtonOptions || {});
        if (CAMERA_ICON) {
            var rem = (cfg.modeBarButtonsToRemove ||
                       (ctx && ctx.modeBarButtonsToRemove) || []).slice();
            if (rem.indexOf('toImage') === -1) rem.push('toImage');
            cfg.modeBarButtonsToRemove = rem;
            var add = (cfg.modeBarButtonsToAdd ||
                       (ctx && ctx.modeBarButtonsToAdd) || [])
                .filter(function (b) { return !(b && b.__hrmaToImage); });
            add.push(TO_IMAGE_BUTTON);
            cfg.modeBarButtonsToAdd = add;
        }
        return cfg;
    }

    function wrap(fnName) {
        var orig = Plotly[fnName] && Plotly[fnName].bind(Plotly);
        if (!orig) return;
        Plotly[fnName] = function (el, data, layout, config) {
            try {
                if (Array.isArray(data)) data.forEach(fixTrace);
                layout = applyDarkLayout(layout);
                maybeBottomLegend(data, layout);
                maybeUnifiedHover(data, layout);
                translateFigure(data, layout);
                config = applyExportConfig(el, config);
            } catch (e) {
                console.warn('HRMA dark theme patch failed, rendering as-is:', e);
            }
            return orig(el, data, layout, config);
        };
    }

    wrap('newPlot');
    wrap('react');

    /* ------------------------------------------------------------------
       Sözlüğü tembel yükle: şablon <script> etiketini eklemediyse bile
       grafik çevirisi çalışsın. i18n_charts.js kendi içinde çift-yükleme
       koruması taşır, iki yoldan da gelse tek kez kaydolur.
       ------------------------------------------------------------------ */
    (function ensureChartDictionary() {
        if (typeof document === 'undefined' || !document.createElement) return;
        if (typeof window !== 'undefined' && window.__HRMA_I18N_CHARTS) return;
        if (document.querySelector('script[src*="i18n_charts.js"]')) return;
        var s = document.createElement('script');
        s.src = '/static/js/i18n_charts.js';
        s.async = true;
        // Sözlük geç gelirse: o ana kadar çizilmiş grafikleri tazele
        // (aksi hâlde ilk hesap İngilizce kalır, sonrakiler Türkçe olurdu).
        s.onload = function () {
            if (typeof window !== 'undefined' && window.I18N &&
                window.I18N.lang && window.I18N.lang !== 'en') {
                scheduleRedraw();
            }
        };
        (document.head || document.documentElement).appendChild(s);
    })();

    /* ------------------------------------------------------------------
       Dil değişince ekrandaki grafikleri yeniden çiz. Sarmalayıcı devrede
       olduğu için Plotly.react çağrısı çeviriyi kendiliğinden uygular;
       çeviri saklanan İngilizce kaynaktan yapıldığı için ileri-geri dil
       değişimi metinleri bozmaz. Sayfada grafik yoksa sessizce geçilir.
       ------------------------------------------------------------------ */
    function redrawAllPlots() {
        if (typeof document === 'undefined' || !document.querySelectorAll) return;
        var nodes = document.querySelectorAll('.js-plotly-plot');
        for (var i = 0; i < nodes.length; i++) {
            var gd = nodes[i];
            if (!gd || !gd._fullLayout || !gd.data) continue;
            try {
                Plotly.react(gd, gd.data, gd.layout || {});
            } catch (e) {
                console.warn('HRMA i18n: grafik yeniden çizilemedi', e);
            }
        }
    }

    /* Hem I18N.onChange hem 'hrma:langchange' olayı bağlanır (yükleme
       sırası ne olursa olsun en az biri çalışsın). İkisi birden tetiklenirse
       aynı karede tek yeniden çizim yapılır. */
    var redrawQueued = false;
    function scheduleRedraw() {
        if (redrawQueued) return;
        redrawQueued = true;
        var run = function () { redrawQueued = false; redrawAllPlots(); };
        if (typeof setTimeout === 'function') setTimeout(run, 0);
        else run();
    }

    (function bindLanguageChange() {
        if (typeof window === 'undefined') return;
        if (window.I18N && typeof window.I18N.onChange === 'function') {
            window.I18N.onChange(scheduleRedraw);
        }
        if (typeof document !== 'undefined' && document.addEventListener) {
            document.addEventListener('hrma:langchange', scheduleRedraw);
        }
    })();

    // Test ve hata ayıklama için açığa çıkarılır (üretimde kullanılmaz).
    Plotly.__hrmaTranslateFigure = translateFigure;
    Plotly.__hrmaRedrawAllPlots = redrawAllPlots;
})();
