/*
 * MotorVizDeck — MotorViz3D için hazır simülasyon güvertesi.
 *
 * Solid/liquid sayfaları gibi kendi HUD'unu elle kurmak istemeyen sayfalar
 * için: verilen konteynere komple güverteyi (başlık + araç çubuğu + 3D
 * sahne + tasarım paneli + zaman çizelgesi + telemetri) enjekte eder ve
 * kablolar. Stiller theme.css'teki .viz-* sınıflarından gelir;
 * motor_viz3d.js yüklü olmalıdır.
 *
 * Kullanım:
 *   MotorVizDeck.create('container_id', motorData, {
 *       title: 'MOTOR SIMULATION',
 *       subtitle: 'PARAMETRIC DIGITAL TWIN',
 *       motorType: 'solid' | 'liquid' | 'hybrid',   // motorData.viz_motor_type'ı ezer
 *       portShape: 'star' | 'multiport' | ...        // başlangıç port kesiti
 *   })
 *
 * motorData şeması MotorViz3D ile aynıdır (results.motor — SI metre).
 *
 * Parite notu (2026-07-19): advanced.html'deki hibrit güvertede 12 buton,
 * hız kontrolü, tasarım modu ve 6 telemetri çipi var; bu güverte katı/sıvı
 * sayfalarında aynı yetenek setini sunar. Farklar YALNIZ fizik gereğidir:
 * sıvıda port çapı / web kalıntısı yoktur, katıda O/F yoktur. Var olmayan
 * büyüklük için çip UYDURULMAZ — motorData'da alan yoksa çip hiç basılmaz.
 */
(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    var UID = 0;

    var PORT_LABELS = {
        circular: 'Circular', star: 'Star',
        multiport: 'Multi-Port', finocyl: 'Finocyl'
    };

    // Tasarım modu slider aralıkları (taban değerin katı olarak)
    var DESIGN_DIA_SPAN = [0.6, 1.4];      // kamara çapı: ±%40
    var DESIGN_LEN_SPAN = [0.6, 1.6];      // kamara/grain boyu: -%40 … +%60
    var DESIGN_EPS_RANGE = [2, 60];        // genişleme oranı mutlak sınırları
    var DESIGN_SLIDER_STEPS = 1000;        // slider tam sayı çözünürlüğü
    var DESIGN_DEBOUNCE_MS = 120;          // istemci tarafı yeniden çizim gecikmesi
    var HUD_THROTTLE_MS = 80;              // telemetri yazma sıklığı (~12 Hz)
    var PA_PER_BAR = 1e5;

    function el(id) { return document.getElementById(id); }

    function isNum(v) { return typeof v === 'number' && isFinite(v); }

    function firstNum() {
        for (var i = 0; i < arguments.length; i++) {
            if (isNum(arguments[i])) return arguments[i];
        }
        return null;
    }

    // Derin olmayan güvenli kopya (tasarım modunda taban veriyi bozmamak için)
    function shallowClone(o) {
        var out = {}, k;
        for (k in o) { if (Object.prototype.hasOwnProperty.call(o, k)) out[k] = o[k]; }
        return out;
    }

    // --- Telemetri çipleri: yalnız VERİSİ OLAN büyüklükler basılır -----------
    function chipList(p, opts, md) {
        var isLiquid = opts.motorType === 'liquid';
        var isSolid = opts.motorType === 'solid';
        var chips = [];

        // Katı ve hibritte port/web anlamlıdır (yakıt grain'i regrese eder)
        if (!isLiquid) {
            chips.push({ id: p + '_port', label: isSolid ? 'Core &Oslash;' : 'Port &Oslash;' });
            chips.push({ id: p + '_web', label: 'Web Remaining' });
        }
        // O/F yalnız iki propellantlı motorlarda ve YALNIZ veri varsa
        if (!isSolid && (isNum(md.of_ratio) || isNum(md.of_ratio_initial) ||
                         isNum(md.mixture_ratio))) {
            chips.push({ id: p + '_of', label: 'O/F Ratio' });
        }
        chips.push({ id: p + '_isp', label: 'Isp' });
        chips.push({ id: p + '_thrust', label: 'Thrust' });
        if (isNum(md.chamber_pressure)) {
            chips.push({ id: p + '_pc', label: 'P<sub>c</sub>' });
        }
        // Genişleme oranı: doğrudan verilir ya da çıkış/boğaz çapından türer
        if (expansionRatio(md) !== null) {
            chips.push({ id: p + '_eps', label: 'Expansion &epsilon;' });
        }
        // Sıvıda port çapı yoktur; boğaz çapı sabit ölçü olarak gösterilir
        if (isLiquid && isNum(md.throat_diameter)) {
            chips.push({ id: p + '_dt', label: 'Throat &Oslash;' });
        }
        return chips;
    }

    function expansionRatio(md) {
        if (isNum(md.expansion_ratio) && md.expansion_ratio > 1) return md.expansion_ratio;
        if (isNum(md.exit_diameter) && isNum(md.throat_diameter) && md.throat_diameter > 0) {
            var eps = Math.pow(md.exit_diameter / md.throat_diameter, 2);
            return isFinite(eps) && eps > 1 ? eps : null;
        }
        return null;
    }

    // --- Tasarım modu kontrolleri: motor tipine göre anlamlı parametreler ----
    function designControls(opts, md) {
        var isSolid = opts.motorType === 'solid';
        var ctrls = [];
        var dch = firstNum(md.chamber_diameter);
        var len = firstNum(md.grain_length, md.chamber_length);
        var eps = expansionRatio(md);

        if (isNum(dch) && dch > 0) {
            ctrls.push({
                key: 'dch', label: 'Chamber &Oslash;',
                lo: dch * DESIGN_DIA_SPAN[0], hi: dch * DESIGN_DIA_SPAN[1], val: dch,
                fmt: function (v) { return (v * 1000).toFixed(1) + ' mm'; }
            });
        }
        if (isNum(len) && len > 0) {
            ctrls.push({
                key: 'len', label: isSolid ? 'Grain Length' : 'Chamber Length',
                lo: len * DESIGN_LEN_SPAN[0], hi: len * DESIGN_LEN_SPAN[1], val: len,
                fmt: function (v) { return (v * 1000).toFixed(0) + ' mm'; }
            });
        }
        if (eps !== null) {
            ctrls.push({
                key: 'eps', label: 'Expansion Ratio &epsilon;',
                lo: Math.max(DESIGN_EPS_RANGE[0], eps * 0.4),
                hi: Math.min(DESIGN_EPS_RANGE[1], Math.max(eps * 2.2, eps + 4)),
                val: eps,
                fmt: function (v) { return v.toFixed(1); }
            });
        }
        return ctrls;
    }

    function deckHtml(p, opts, chips, ctrls) {
        // Port kesiti YALNIZ sıvıda anlamsızdır (yakıt grain'i yoktur);
        // katı ve hibritte port şekli döngüsü sunulur
        var hasPort = opts.motorType !== 'liquid';

        var designHtml = '';
        if (ctrls.length) {
            designHtml =
                '  <div class="viz-design" id="' + p + '_design" style="display: none;">' +
                ctrls.map(function (c) {
                    return '<div class="viz-dctrl">' +
                        '<div class="dk"><span>' + c.label + '</span>' +
                        '<b id="' + p + '_dv_' + c.key + '">—</b></div>' +
                        '<input type="range" id="' + p + '_ds_' + c.key + '" min="0" max="' +
                        DESIGN_SLIDER_STEPS + '" value="0"></div>';
                }).join('') +
                '    <div class="viz-dstatus" id="' + p + '_dstatus">' +
                'GEOMETRY PREVIEW — 3D shape only; performance figures are unchanged. ' +
                'Re-run Calculate to update the analysis.</div>' +
                '  </div>';
        }

        return '' +
            '<div class="viz-deck">' +
            '  <div class="viz-head">' +
            '    <div>' +
            '      <div class="viz-title"><span class="viz-dot"></span>' + opts.title + '</div>' +
            '      <div class="viz-sub">' + opts.subtitle + '</div>' +
            '    </div>' +
            '    <div class="viz-toolbar">' +
            '      <button class="viz-btn active" id="' + p + '_btn_cut">Cutaway</button>' +
            '      <button class="viz-btn active" id="' + p + '_btn_dim">Dimensions</button>' +
            '      <button class="viz-btn warn active" id="' + p + '_btn_plume">Exhaust</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_exp">Exploded</button>' +
            (hasPort
                ? '      <button class="viz-btn" id="' + p + '_btn_portshape">Port: ' +
                  (PORT_LABELS[opts.portShape] || 'Circular') + '</button>'
                : '') +
            '      <button class="viz-btn warn" id="' + p + '_btn_heat">Heat Map</button>' +
            (ctrls.length
                ? '      <button class="viz-btn warn" id="' + p + '_btn_design">Design Mode</button>'
                : '') +
            '      <button class="viz-btn" id="' + p + '_btn_rot">Orbit</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_cam">Cam: Iso</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_quality">HQ</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_speed">1&times;</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_reset">Reset View</button>' +
            '    </div>' +
            '  </div>' +
            '  <div class="viz-stage">' +
            '    <div id="' + p + '_viewport" style="position: absolute; inset: 0;"></div>' +
            '    <div class="viz-corner tl"></div><div class="viz-corner tr"></div>' +
            '    <div class="viz-corner bl"></div><div class="viz-corner br"></div>' +
            '    <div class="viz-status" id="' + p + '_status">STANDBY</div>' +
            '    <div class="viz-heatlegend" id="' + p + '_heatlegend" style="display: none;">' +
            '      <div>WALL HEAT FLUX — BARTZ (A<sub>t</sub>/A)<sup>0.9</sup></div>' +
            '      <div class="bar"></div>' +
            '      <div class="lbl"><span id="' + p + '_hl_min">—</span><span id="' + p + '_hl_max">—</span></div>' +
            '      <div class="tw" id="' + p + '_hl_wall">—</div>' +
            '    </div>' +
            '  </div>' +
            designHtml +
            '  <div class="viz-timeline">' +
            '    <button class="viz-play" id="' + p + '_play">&#9654;</button>' +
            '    <input type="range" id="' + p + '_slider" min="0" max="1000" value="0">' +
            '    <div class="viz-clock" id="' + p + '_clock">t = 0.00 s / — s</div>' +
            '  </div>' +
            '  <div class="viz-telemetry">' +
            chips.map(function (c) {
                return '<div class="viz-chip" id="' + c.id + '_chip">' +
                    '<div class="k">' + c.label + '</div>' +
                    '<div class="v" id="' + c.id + '">—</div></div>';
            }).join('') +
            '  </div>' +
            '</div>';
    }

    function create(containerId, motorData, opts) {
        var host = el(containerId);
        if (!host) return null;
        if (!(window.MotorViz3D && MotorViz3D.isSupported())) return null;

        opts = Object.assign({
            title: 'MOTOR SIMULATION',
            subtitle: 'PARAMETRIC DIGITAL TWIN — LIVE GEOMETRY FROM SOLVER OUTPUT',
            motorType: motorData.viz_motor_type || 'hybrid',
            portShape: 'circular'
        }, opts || {});
        motorData.viz_motor_type = opts.motorType;

        var p = 'vzd' + (++UID);
        var chips = chipList(p, opts, motorData);
        var ctrls = designControls(opts, motorData);
        var chipIds = {};
        chips.forEach(function (c) { chipIds[c.id] = true; });
        host.innerHTML = deckHtml(p, opts, chips, ctrls);

        // Statik (zamanla değişmeyen) çip değerleri bir kez yazılır
        var staticPcBar = isNum(motorData.chamber_pressure) ? motorData.chamber_pressure : null;
        var epsValue = expansionRatio(motorData);

        var hudLast = 0;
        var viz = MotorViz3D.mount(p + '_viewport', motorData, {
            onTick: function (s) {
                var now = performance.now();
                if (now - hudLast < HUD_THROTTLE_MS) return;
                hudLast = now;
                var play = el(p + '_play'), slider = el(p + '_slider');
                var clock = el(p + '_clock'), status = el(p + '_status');
                if (!play || !slider) return;
                play.innerHTML = s.playing ? '&#10074;&#10074;' : '&#9654;';
                play.classList.toggle('burning', s.burning);
                var pr = (s.time / s.burnTime) * 1000;
                slider.value = pr;
                slider.style.setProperty('--p', (pr / 10) + '%');
                clock.innerHTML = 't = <b>' + s.time.toFixed(2) + '</b> s / ' + s.burnTime.toFixed(2) + ' s';
                if (status) {
                    if (s.burning) { status.textContent = 'COMBUSTION ACTIVE'; status.classList.add('burning'); }
                    else if (s.time >= s.burnTime - 1e-3) { status.textContent = 'BURNOUT'; status.classList.remove('burning'); }
                    else { status.textContent = 'STANDBY'; status.classList.remove('burning'); }
                }
                setChip(p + '_port', s.portDiameter.toFixed(1), 'mm', s.burning);
                setChip(p + '_web', (s.webRemaining * 100).toFixed(0), '%', s.burning);
                setChip(p + '_of', isNum(s.of) ? s.of.toFixed(2) : '—', '', s.burning);
                setChip(p + '_isp', s.isp ? s.isp.toFixed(1) : '—', 's', s.burning);
                var tv = s.thrust >= 1000 ? (s.thrust / 1000).toFixed(2) : s.thrust.toFixed(0);
                setChip(p + '_thrust', s.thrust > 0 ? tv : '0', s.thrust >= 1000 ? 'kN' : 'N', s.burning);
                // Pc: transient eğri varsa anlık (Pa → bar), yoksa tasarım değeri
                var pcBar = isNum(s.pc) ? s.pc / PA_PER_BAR : staticPcBar;
                setChip(p + '_pc', isNum(pcBar) ? pcBar.toFixed(1) : '—', 'bar',
                        s.burning && isNum(s.pc));
            }
        });
        if (!viz) return null;
        if (opts.portShape !== 'circular' && opts.motorType !== 'liquid') {
            viz.setPortShape(opts.portShape);
            syncPortBtn();
        }

        // Zamanla değişmeyen çipler
        if (epsValue !== null) setChip(p + '_eps', epsValue.toFixed(1), '', false);
        if (isNum(motorData.throat_diameter)) {
            setChip(p + '_dt', (motorData.throat_diameter * 1000).toFixed(1), 'mm', false);
        }

        function setChip(id, val, unit, hot) {
            if (!chipIds[id]) return;          // bu motor tipinde çip yok
            var e = el(id);
            if (e) e.innerHTML = val + (unit ? '<small>' + unit + '</small>' : '');
            var chip = el(id + '_chip');
            if (chip) chip.classList.toggle('hot', !!hot);
        }

        function toggleBtn(btnId, prop, setter) {
            var b = el(btnId);
            if (!b) return;
            b.onclick = function () {
                var next = !viz.state[prop];
                setter.call(viz, next);
                b.classList.toggle('active', next);
            };
        }

        function syncPortBtn() {
            var b = el(p + '_btn_portshape');
            if (!b) return;
            b.textContent = 'Port: ' + PORT_LABELS[viz.state.portShape];
            b.classList.toggle('active', viz.state.portShape !== 'circular');
        }

        toggleBtn(p + '_btn_cut', 'cutaway', viz.setCutaway);
        toggleBtn(p + '_btn_dim', 'labels', viz.setLabels);
        toggleBtn(p + '_btn_plume', 'plume', viz.setPlume);
        toggleBtn(p + '_btn_exp', 'exploded', viz.setExploded);
        toggleBtn(p + '_btn_rot', 'autoRotate', viz.setAutoRotate);
        var resetBtn = el(p + '_btn_reset');
        if (resetBtn) resetBtn.onclick = function () { viz.resetCamera(); };

        // Kamera preset döngüsü (Iso → Side → Nozzle → Injector)
        var camBtn = el(p + '_btn_cam');
        if (camBtn) camBtn.onclick = function () {
            var name = viz.cycleCameraPreset();
            if (name) camBtn.textContent = 'Cam: ' + name.charAt(0).toUpperCase() + name.slice(1);
        };
        // Kalite anahtarı: HQ ↔ PERF (düşük pixelRatio + az partikül)
        var qBtn = el(p + '_btn_quality');
        if (qBtn) qBtn.onclick = function () {
            var mode = qBtn.textContent === 'HQ' ? 'perf' : 'high';
            viz.setQuality(mode);
            qBtn.textContent = mode === 'perf' ? 'PERF' : 'HQ';
            qBtn.classList.toggle('active', mode === 'perf');
        };
        // Oynatma hızı döngüsü (0.5× → 1× → 2× → 4×) — hibrit güverte paritesi
        var speedBtn = el(p + '_btn_speed');
        if (speedBtn) speedBtn.onclick = function () {
            var sp = viz.cycleSpeed();
            speedBtn.innerHTML = (sp % 1 === 0 ? sp : sp.toFixed(1)) + '&times;';
            speedBtn.classList.toggle('active', sp !== 1);
        };

        var portBtn = el(p + '_btn_portshape');
        if (portBtn) portBtn.onclick = function () { viz.cyclePortShape(); syncPortBtn(); };

        var heatBtn = el(p + '_btn_heat');
        // Isıl analiz verisi olmayan motorlarda (örn. katı — yer tutucu akı)
        // buton hiç gösterilmez
        if (heatBtn && !viz.getHeatInfo()) {
            heatBtn.style.display = 'none';
            heatBtn = null;
        }
        if (heatBtn) heatBtn.onclick = function () {
            var info = viz.getHeatInfo();
            var legend = el(p + '_heatlegend');
            if (!info) {
                heatBtn.classList.remove('active');
                if (legend) legend.style.display = 'none';
                heatBtn.textContent = 'Heat Map (no data)';
                setTimeout(function () { heatBtn.textContent = 'Heat Map'; }, 1800);
                return;
            }
            var on = viz.setHeatMap(!viz.state.heatMap);
            heatBtn.classList.toggle('active', on);
            if (legend) {
                legend.style.display = on ? 'block' : 'none';
                if (on) {
                    var fmt = function (q) {
                        return q >= 1e6 ? (q / 1e6).toFixed(2) + ' MW/m²'
                                        : (q / 1e3).toFixed(0) + ' kW/m²';
                    };
                    el(p + '_hl_min').textContent = fmt(info.qChamber);
                    el(p + '_hl_max').textContent = fmt(info.qThroat);
                    el(p + '_hl_wall').textContent =
                        (info.tWallInner ? 'T_wall inner ' + info.tWallInner.toFixed(0) + ' K' : '') +
                        (info.tWallOuter ? ' / outer ' + info.tWallOuter.toFixed(0) + ' K' : '');
                }
            }
        };

        // --- Tasarım modu: slider → geometri önizlemesi (istemci tarafı) -----
        // Katı/sıvı için hibritteki /api/quick-geometry karşılığı YOKTUR; bu
        // yüzden burada YALNIZ 3D geometri yeniden kurulur, performans
        // değerleri (itki/Isp/Pc) DEĞİŞTİRİLMEZ ve panelde bu açıkça yazar.
        var designTimer = null;
        var designBtn = el(p + '_btn_design');
        if (designBtn && ctrls.length) {
            designBtn.onclick = function () {
                var panel = el(p + '_design');
                if (!panel) return;
                var open = panel.style.display === 'none';
                panel.style.display = open ? 'flex' : 'none';
                designBtn.classList.toggle('active', open);
                if (open) designInit();
            };
        }

        function designSliderValue(c) {
            var input = el(p + '_ds_' + c.key);
            if (!input) return c.val;
            return c.lo + (c.hi - c.lo) * (parseFloat(input.value) / DESIGN_SLIDER_STEPS);
        }

        function designInit() {
            ctrls.forEach(function (c) {
                var input = el(p + '_ds_' + c.key);
                if (!input) return;
                input.value = Math.round(((c.val - c.lo) / (c.hi - c.lo)) * DESIGN_SLIDER_STEPS);
                input.oninput = function () {
                    designReadouts();
                    clearTimeout(designTimer);
                    designTimer = setTimeout(designApply, DESIGN_DEBOUNCE_MS);
                };
            });
            designReadouts();
        }

        function designReadouts() {
            ctrls.forEach(function (c) {
                var out = el(p + '_dv_' + c.key);
                if (out) out.textContent = c.fmt(designSliderValue(c));
            });
        }

        function designApply() {
            var next = shallowClone(motorData);
            var isSolid = opts.motorType === 'solid';
            ctrls.forEach(function (c) {
                var v = designSliderValue(c);
                if (c.key === 'dch') {
                    next.chamber_diameter = v;
                } else if (c.key === 'len') {
                    if (isSolid) {
                        // Katıda slider grain boyunu sürer; kasa boyu grain'i
                        // sarmalı (extractDims Lg'yi 0.92·Lch ile kırpar)
                        next.grain_length = v;
                        next.chamber_length = Math.max(
                            isNum(motorData.chamber_length) ? motorData.chamber_length : v / 0.9,
                            v / 0.9);
                    } else {
                        next.chamber_length = v;
                    }
                } else if (c.key === 'eps') {
                    // ε = (de/dt)² → çıkış çapı boğazdan türetilir
                    if (isNum(next.throat_diameter)) {
                        next.exit_diameter = next.throat_diameter * Math.sqrt(v);
                    }
                }
            });
            // grain_design.grain_length_mm extractDims'te önceliklidir; önizleme
            // boyunca senkron tutulmazsa slider grain'i hiç hareket ettirmez
            if (motorData.grain_design && isNum(next.grain_length)) {
                next.grain_design = shallowClone(motorData.grain_design);
                if (isNum(next.grain_design.grain_length_mm)) {
                    next.grain_design.grain_length_mm = next.grain_length * 1000;
                }
                if (isNum(next.grain_design.outer_diameter_mm) && isNum(next.chamber_diameter)) {
                    next.grain_design.outer_diameter_mm = next.chamber_diameter * 1000;
                }
            }
            viz.update(next);
        }

        var playBtn = el(p + '_play');
        if (playBtn) playBtn.onclick = function () {
            if (viz.state.playing) viz.pause(); else viz.play();
        };
        var slider = el(p + '_slider');
        if (slider) slider.oninput = function () {
            viz.pause();
            viz.setTime((this.value / 1000) * viz.dims.burnTime);
        };

        return { viz: viz, prefix: p, update: function (md) { MotorViz3D.update(md); } };
    }

    window.MotorVizDeck = { create: create };
})();
