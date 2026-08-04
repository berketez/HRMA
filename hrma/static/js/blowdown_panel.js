/* ====================================================================
   HRMA Tank Blowdown Panel (yalnız hibrit sayfası) — A1/A10 kullanıcı yüzü
   --------------------------------------------------------------------
   Motor çözücüsü /calculate yanıtında iki dürüstlük bloğu yayımlıyor ama
   2026-08-03 denetimine kadar HİÇBİR panel bunları kullanıcıya
   göstermiyordu ("beyanı okuyan karar kapısı" kuralının UI yarısı eksikti):

     1. motor.tank_blowdown  — kendinden-basınçlı N₂O tank boşalması:
        tank basıncı(t), kamara basıncı(t), ṁ_ox(t), itki(t) eğrileri
        (kaynak: hrma/engines/hybrid_rocket_engine._tank_blowdown_block;
        model: denge iki-faz N₂O tankı, Whitmore & Chandler JPP 27(4) 2011
        + SPI enjektör + yarı-kararlı kamara — künye bloğun kendi
        'basis' alanında sunucudan gelir ve panel onu AYNEN gösterir).
     2. motor.not_modelled   — modellenmeyen fizik kalemlerinin açık
        beyanı (A10; 7 kalem). Panel beyan METİNLERİNİ sonuçtan okur,
        burada hiçbir beyan metni sabit kodlanmaz.

   SAHTE VERİ YASAĞI: yalnız bloktaki gerçek diziler çizilir. Blok yoksa,
   status 'modelled' değilse ya da seriler kendi içinde tutarsızsa HİÇBİR
   eğri üretilmez; motor_viz3d'nin "missing = modellenmedi / veri yok"
   çip kalıbıyla (gri #8a93a0) durum açıkça beyan edilir.

   Kullanım (advanced.html):
     <script src="/static/js/blowdown_panel.js"></script>
     BlowdownPanel.init({ anchorId: 'trajectoryPanel',
                          declAnchorId: 'notModelledStrip' });

   Veri akışı: init(), app.js'teki global displayCalculationResults'ı
   advanced.html'deki yörünge-eşitleme sarmalayıcısıyla AYNI desenle sarar;
   her hesap sonucunda update(results) çağrılır. Özgün işlev her koşulda
   çalışır — panel hata verse bile hesap gösterimi engellenmez.

   Bekçi testleri: tests/test_blowdown_panel.py (dosya node ile izole
   koşturulur; Plotly/DOM taklit edilir, seriler birebir doğrulanır).
   ==================================================================== */

(function () {
    'use strict';

    let cfg = {};
    let lastResults = null;

    // i18n köprüleri — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // Sunucu üretimi serbest metin (blok uyarıları, reason/basis alanları):
    // i18n_charts.js MSG_PATTERNS çevirisinden geçer, eşleşme yoksa aynen kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    // HTML kaçışı: sunucu metinleri şablona gömülmeden önce zararsızlaştırılır.
    // Tırnaklara dokunulmaz (beyan metinleri kesme işareti taşır ve bekçi test
    // birebir karşılaştırır); metinler yalnız eleman GÖVDESİNE yazılır.
    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ==================================================================
    // >>> BLOWDOWN_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek yanıt sözlükleriyle koşturur. Seriler ÖLÇEKLENMEZ, kopyalanmaz,
    // yeniden örneklenmez: bloktaki diziler referans olarak aynen taşınır.
    // ==================================================================

    // Beklenen seri alanları — _tank_blowdown_block sözleşmesi (birimler
    // alan adında: s / bar / kg/s / N; panel hiçbir birim dönüşümü yapmaz).
    const SERIES_KEYS = ['time_s', 'tank_pressure_bar', 'chamber_pressure_bar',
                         'mdot_ox_kg_s', 'thrust_N'];

    // Kararsızlık uyarısı seçici: {code, params} sözleşmeli uyarılar içinde
    // besleme-kaynaklı yanma kararsızlığına işaret eden kod gövdeleri.
    // Bu bir metin listesi DEĞİL, vurgu süzgecidir; kod gövdesi eşleşen yeni
    // uyarılar kendiliğinden vurgulanır.
    const INSTABILITY_CODE_STEM = /chug|instab|feed_coupling|hydraulic_flip/;

    function isNumArray(arr) {
        if (!Array.isArray(arr) || arr.length < 2) return false;
        for (let i = 0; i < arr.length; i++) {
            if (typeof arr[i] !== 'number' || !isFinite(arr[i])) return false;
        }
        return true;
    }

    // motor.not_modelled → [{key, text}] (sıra sunucunun yayım sırası).
    // Beyan metni SONUÇTAN okunur; bu dosyada beyan metni sabiti YOKTUR.
    function buildDeclarations(motor) {
        const nm = motor && motor.not_modelled;
        if (!nm || typeof nm !== 'object' || Array.isArray(nm)) return null;
        const out = Object.keys(nm)
            .filter(k => typeof nm[k] === 'string' && nm[k])
            .map(k => ({ key: k, text: nm[k] }));
        return out.length ? out : null;
    }

    // design_warnings + injector_design_detail.warnings içinden 'warn.' önekli
    // ve kararsızlık gövdeli kayıtları toplar (kod başına bir kez).
    function pickInstabilityWarnings(motor) {
        const out = [];
        const seen = {};
        function scan(list) {
            (Array.isArray(list) ? list : []).forEach(function (w) {
                if (w && typeof w === 'object' && typeof w.code === 'string'
                        && w.code.indexOf('warn.') === 0
                        && INSTABILITY_CODE_STEM.test(w.code)
                        && !seen[w.code]) {
                    seen[w.code] = true;
                    out.push(w);
                }
            });
        }
        if (motor && typeof motor === 'object') {
            scan(motor.design_warnings);
            scan(motor.injector_design_detail
                 && motor.injector_design_detail.warnings);
        }
        return out;
    }

    // Blok içi serbest-metin uyarısı kararsızlık mı? (transient_ballistics
    // 'chugging risk (SP-8089)' / 'combustion instability limit' üretir)
    function isInstabilityText(text) {
        return /chug|instab/i.test(String(text));
    }

    function buildViewModel(motor) {
        const declarations = buildDeclarations(motor);
        const declBasis = (motor && typeof motor.not_modelled_basis === 'string')
            ? motor.not_modelled_basis : null;
        const instability = pickInstabilityWarnings(motor);
        const base = { declarations: declarations, declBasis: declBasis,
                       instability: instability };

        if (!motor || typeof motor !== 'object') {
            base.mode = 'no_result';
            return base;
        }
        const bd = motor.tank_blowdown;
        if (!bd || typeof bd !== 'object') {
            // Eski sunucu yanıtı / eski proje kaydı: blok hiç yok.
            base.mode = 'no_block';
            return base;
        }
        base.basis = (typeof bd.basis === 'string') ? bd.basis : null;
        if (bd.status !== 'modelled') {
            base.mode = 'not_modelled';
            base.reason = (typeof bd.reason === 'string') ? bd.reason : '';
            base.end_event = bd.end_event || null;
            return base;
        }
        // status 'modelled' — seriler doğrulanır; tutarsızsa ÇİZİLMEZ
        // (kısmî/sahte eğri, eğrisizlikten kötüdür).
        const n = Array.isArray(bd.time_s) ? bd.time_s.length : 0;
        const consistent = SERIES_KEYS.every(function (k) {
            return isNumArray(bd[k]) && bd[k].length === n;
        });
        if (!consistent) {
            base.mode = 'invalid_block';
            return base;
        }
        base.mode = 'modelled';
        base.series = {};
        SERIES_KEYS.forEach(function (k) { base.series[k] = bd[k]; });
        base.feed_mode = bd.feed_mode || null;
        base.end_event = bd.end_event || null;
        base.burn_duration_s = (typeof bd.burn_duration_s === 'number')
            ? bd.burn_duration_s : null;
        base.total_impulse_Ns = (typeof bd.total_impulse_Ns === 'number')
            ? bd.total_impulse_Ns : null;
        base.thrust_decay_fraction = (typeof bd.thrust_decay_fraction === 'number'
                                      && isFinite(bd.thrust_decay_fraction))
            ? bd.thrust_decay_fraction : null;
        base.initial_pressure_bar = (typeof bd.initial_pressure_bar === 'number')
            ? bd.initial_pressure_bar : null;
        base.warnings = (Array.isArray(bd.warnings) ? bd.warnings : [])
            .filter(function (w) { return typeof w === 'string' && w; });
        return base;
    }
    // <<< BLOWDOWN_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil
    // ------------------------------------------------------------------

    // Durum çipi — motor_viz3d.SOURCE_COLORS.missing ile aynı gri
    // ('modellenmedi / veri yok' kalıbı; keyfî süs rengi yok).
    const MISSING_COLOR = '#8a93a0';

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        return `<span data-warn="${kind === 'err' ? 'instability' : 'general'}"
                 style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    function chipHtml(label, reason) {
        let html = `<span data-chip="not-modelled" style="border:1px solid ${MISSING_COLOR};
            color:${MISSING_COLOR}; border-radius:6px; padding:4px 10px;
            font-family:var(--hd-mono); font-size:0.75rem;">${esc(label)}</span>`;
        if (reason) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0 0;">${esc(SRV(reason))}</p>`;
        }
        return html;
    }

    // {code, params} uyarısını metne çevirir — app.js::displayWarnings ile
    // aynı sözleşme; AnalysisDock yüklüyse onun çevirmeni kullanılır.
    function warnText(w, depth) {
        if (window.AnalysisDock && window.AnalysisDock.ui
                && window.AnalysisDock.ui.warnText) {
            return window.AnalysisDock.ui.warnText(w);
        }
        depth = depth || 0;
        if (w === null || w === undefined) return '';
        if (typeof w === 'string') return SRV(w);
        if (Array.isArray(w)) {
            return w.map(x => warnText(x, depth + 1)).filter(Boolean).join(' · ');
        }
        if (typeof w !== 'object') return String(w);
        if (!w.code) return SRV(w.message || w.text || JSON.stringify(w));
        if (depth > 4) return w.code;
        const p = {};
        Object.keys(w.params || {}).forEach(function (k) {
            const v = w.params[k];
            p[k] = (v && typeof v === 'object') ? warnText(v, depth + 1) : v;
        });
        return (window.I18N && window.I18N.tf)
            ? window.I18N.tf(w.code, p, w.fallback || w.code)
            : (w.fallback || w.code);
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="blowdownPanel" style="width:100%; grid-column: 1 / -1;">
            <h2>▶ <span data-i18n="blowdown.title">${T('blowdown.title',
                'Tank Blowdown — Pressure / Flow / Thrust Decay')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="blowdown.intro">${T('blowdown.intro',
                    'Self-pressurised N2O tank blowdown built from the solver values of '
                    + 'THIS run: tank pressure falls during the burn, oxidizer flow and '
                    + 'thrust fall with it. The headline design numbers remain the '
                    + 'regulated design point; this block is advisory. If the model '
                    + 'cannot run, no curve is drawn and the reason is stated.')}</span>
            </div>
            <div id="bp_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="bp_instability" style="margin:8px 0;"></div>
            <div id="bp_chip" style="margin:8px 0;"></div>
            <div id="bp_plot_pressure" class="plot-container" style="min-height:360px; display:none;"></div>
            <div id="bp_plot_mdot" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="bp_plot_thrust" class="plot-container" style="min-height:300px; display:none;"></div>
            <details id="bp_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="blowdown.basisTitle">${T('blowdown.basisTitle',
                    'Method / basis (as declared by the solver)')}</summary>
                <p id="bp_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></p>
            </details>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function endEventKind(event) {
        return {
            burn_time_reached: 'ok', web_exhausted: 'ok',
            oxidizer_depleted: 'info', injector_unstable: 'err',
            feed_pressure_lost: 'err', time_limit: 'warn',
        }[event] || 'info';
    }

    function renderBadges(el, vm) {
        let html = '';
        if (vm.feed_mode) {
            html += badge(T('blowdown.badgeFeedMode', 'FEED') + ': '
                + esc(String(vm.feed_mode).toUpperCase()), 'info');
        }
        if (vm.end_event) {
            html += badge(T('blowdown.badgeEnd', 'END') + ': '
                + esc(String(vm.end_event).toUpperCase()),
                endEventKind(vm.end_event));
        }
        if (vm.burn_duration_s !== null && vm.burn_duration_s !== undefined) {
            html += badge(TF('blowdown.badgeBurn',
                { s: vm.burn_duration_s.toFixed(2) }, 'BURN {s} s'), 'info');
        }
        if (vm.total_impulse_Ns !== null && vm.total_impulse_Ns !== undefined) {
            html += badge(TF('blowdown.badgeImpulse',
                { v: (vm.total_impulse_Ns / 1000).toFixed(1) },
                'IMPULSE {v} kN·s'), 'info');
        }
        if (vm.thrust_decay_fraction !== null
                && vm.thrust_decay_fraction !== undefined) {
            html += badge(TF('blowdown.badgeDecay',
                { pct: (100 * vm.thrust_decay_fraction).toFixed(0) },
                'THRUST DECAY {pct}%'), 'info');
        }
        if (vm.initial_pressure_bar !== null
                && vm.initial_pressure_bar !== undefined) {
            html += badge(TF('blowdown.badgeInitialP',
                { v: vm.initial_pressure_bar.toFixed(1) },
                'P_tank(0) {v} bar'), 'info');
        }
        // Blok içi serbest-metin uyarıları: kararsızlık olanlar kırmızı vurgulu
        (vm.warnings || []).forEach(function (w) {
            html += badge(esc(SRV(w)), isInstabilityText(w) ? 'err' : 'warn');
        });
        el.innerHTML = html;
    }

    // Chugging/kararsızlık uyarıları — design_warnings sözleşmeli kayıtlar,
    // panelde vurgulu (uyarı panelindeki genel listeden ayrı, karar kapısı).
    function renderInstability(el, vm) {
        const list = vm.instability || [];
        if (!list.length) { el.innerHTML = ''; return; }
        let html = `<strong style="color:var(--hd-red, #ff5d73);
            font-family:var(--hd-mono); font-size:0.8rem;"
            data-i18n="blowdown.instabilityTitle">${T('blowdown.instabilityTitle',
            'Feed / combustion stability warnings')}</strong>`;
        list.forEach(function (w) {
            html += `<div data-warn-code="${esc(w.code)}" style="border:1px solid
                var(--hd-red, #ff5d73); border-left-width:4px; border-radius:6px;
                padding:6px 10px; margin:6px 0; color:var(--hd-red, #ff5d73);
                font-family:var(--hd-mono); font-size:0.78rem;">⚠ ${esc(warnText(w))}</div>`;
        });
        el.innerHTML = html;
    }

    function renderCharts(els, vm) {
        const s = vm.series;
        const timeTitle = T('common.axis.timeS2', 'Time [s]');
        // Tank + kamara basıncı AYNI eksende: aradaki fark enjektör ΔP'sidir,
        // iki eğri ayrı eksene konursa bu fark okunamaz.
        Plotly.react(els.pressure, [
            { x: s.time_s, y: s.tank_pressure_bar,
              name: T('transient.sTankP', 'Tank Pressure [bar]'),
              mode: 'lines', line: { width: 3 } },
            { x: s.time_s, y: s.chamber_pressure_bar,
              name: T('transient.sPc', 'Chamber Pressure [bar]'),
              mode: 'lines', line: { width: 2, dash: 'dot' } },
        ], {
            title: T('blowdown.chartPressure',
                     'Tank vs Chamber Pressure (same axis — the gap is the injector ΔP)'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'P [bar]', rangemode: 'tozero' },
            height: 360,
            legend: { orientation: 'h', y: 1.14 },
        }, { responsive: true, displaylogo: false });

        Plotly.react(els.mdot, [
            { x: s.time_s, y: s.mdot_ox_kg_s,
              name: T('blowdown.sMdotOx', 'Oxidizer Mass Flow [kg/s]'),
              mode: 'lines', line: { width: 3 } },
        ], {
            title: T('blowdown.chartMdot', 'Oxidizer Mass Flow Decay'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'ṁ_ox [kg/s]', rangemode: 'tozero' },
            height: 300,
            legend: { orientation: 'h', y: 1.16 },
        }, { responsive: true, displaylogo: false });

        Plotly.react(els.thrust, [
            { x: s.time_s, y: s.thrust_N,
              name: T('transient.sThrust', 'Thrust [N]'),
              mode: 'lines', line: { width: 3 } },
        ], {
            title: T('blowdown.chartThrust', 'Thrust Decay During Blowdown'),
            xaxis: { title: timeTitle },
            yaxis: { title: 'F [N]', rangemode: 'tozero' },
            height: 300,
            legend: { orientation: 'h', y: 1.16 },
        }, { responsive: true, displaylogo: false });
    }

    // A10 beyan şeridi — hibrit sonuç bölümünün başı. Metinler SONUÇTAN gelir;
    // sayı da listenin gerçek uzunluğudur, sabit '7' yazılmaz.
    function renderDeclarations(el, vm) {
        if (!el) return;
        const decls = vm.declarations;
        if (!decls || !decls.length) {
            el.innerHTML = '';
            el.style.display = 'none';
            return;
        }
        const items = decls.map(function (d) {
            return `<li style="margin:6px 0;">${esc(SRV(d.text))}</li>`;
        }).join('');
        const basisNote = vm.declBasis
            ? `<p style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);
                margin:8px 0 0;">${esc(SRV(vm.declBasis))}</p>`
            : '';
        el.innerHTML = `
        <div class="panel" style="border-left:3px solid ${MISSING_COLOR}; margin-bottom:20px;">
            <details>
                <summary data-decl-count="${decls.length}" style="cursor:pointer;
                    font-family:var(--hd-mono); font-size:0.85rem;
                    color:${MISSING_COLOR};">${esc(TF('blowdown.declCount',
                    { n: decls.length },
                    '{n} physics items are NOT modelled in this hybrid result — read before trusting the design'))}</summary>
                <ul style="margin:8px 0 0 18px; font-size:0.78rem;
                    color:var(--hd-ink-dim, #7d97a5);
                    font-family:var(--hd-mono);">${items}</ul>
                ${basisNote}
            </details>
        </div>`;
        el.style.display = '';
    }

    function render() {
        const motor = lastResults && lastResults.motor;
        const vm = buildViewModel(motor);

        renderDeclarations(
            document.getElementById(cfg.declAnchorId || 'notModelledStrip'), vm);

        const els = {
            badges: document.getElementById('bp_badges'),
            instability: document.getElementById('bp_instability'),
            chip: document.getElementById('bp_chip'),
            basis: document.getElementById('bp_basis'),
            basisText: document.getElementById('bp_basis_text'),
            pressure: document.getElementById('bp_plot_pressure'),
            mdot: document.getElementById('bp_plot_mdot'),
            thrust: document.getElementById('bp_plot_thrust'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        renderInstability(els.instability, vm);

        // Yöntem künyesi: sunucunun basis beyanı (varsa) aynen gösterilir
        if (els.basis && els.basisText) {
            if (vm.basis) {
                els.basisText.textContent = SRV(vm.basis);
                els.basis.style.display = '';
            } else {
                els.basisText.textContent = '';
                els.basis.style.display = 'none';
            }
        }

        if (vm.mode === 'modelled') {
            els.chip.innerHTML = '';
            renderBadges(els.badges, vm);
            els.pressure.style.display = 'block';
            els.mdot.style.display = 'block';
            els.thrust.style.display = 'block';
            renderCharts(els, vm);
            return;
        }

        // Modellenmedi / veri yok: eğri ÇİZİLMEZ, çip + gerekçe basılır.
        els.pressure.style.display = 'none';
        els.mdot.style.display = 'none';
        els.thrust.style.display = 'none';
        els.badges.innerHTML = '';
        if (vm.mode === 'not_modelled') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipNotModelled', 'NOT MODELLED — no curve is drawn'),
                vm.reason || '');
        } else if (vm.mode === 'invalid_block') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipInvalid',
                  'DATA INCONSISTENT — the tank_blowdown block arrived with '
                  + 'mismatched series; nothing is plotted'), '');
        } else if (vm.mode === 'no_block') {
            els.chip.innerHTML = chipHtml(
                T('blowdown.chipNoData',
                  'NO DATA — this result carries no tank_blowdown block '
                  + '(older save or older server); nothing is plotted'), '');
        } else {
            els.chip.innerHTML = '';
        }
    }

    // ------------------------------------------------------------------
    // Bağlama
    // ------------------------------------------------------------------
    function update(results) {
        lastResults = results || null;
        render();
    }

    function init(opts) {
        cfg = opts || {};
        const anchor = document.getElementById(cfg.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);

        // Hesap köprüsü: advanced.html'deki yörünge-eşitleme sarmalayıcısıyla
        // aynı desen. Özgün işlev HER KOŞULDA çağrılır; panel hatası hesap
        // gösterimini asla engellemez.
        (function () {
            const original = window.displayCalculationResults;
            if (typeof original !== 'function') return;
            window.displayCalculationResults = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('Blowdown panel update failed:', e);
                }
                return out;
            };
        })();

        // Dil değişince saklanan sonuçla yeniden basılır
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
    }

    window.BlowdownPanel = {
        init: init,
        update: update,
        buildViewModel: buildViewModel,
        get result() { return lastResults; },
    };
})();
