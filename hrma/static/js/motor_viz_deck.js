/*
 * MotorVizDeck — MotorViz3D için hazır simülasyon güvertesi.
 *
 * Solid/liquid sayfaları gibi kendi HUD'unu elle kurmak istemeyen sayfalar
 * için: verilen konteynere komple güverteyi (başlık + araç çubuğu + 3D
 * sahne + zaman çizelgesi + telemetri) enjekte eder ve kablolar. Stiller
 * theme.css'teki .viz-* sınıflarından gelir; motor_viz3d.js yüklü olmalıdır.
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
 */
(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    var UID = 0;

    var PORT_LABELS = {
        circular: 'Circular', star: 'Star',
        multiport: 'Multi-Port', finocyl: 'Finocyl'
    };

    function el(id) { return document.getElementById(id); }

    function deckHtml(p, opts) {
        var isLiquid = opts.motorType === 'liquid';
        var chips = [
            !isLiquid ? { id: p + '_port', label: 'Port &Oslash;' } : null,
            !isLiquid ? { id: p + '_web', label: 'Web Remaining' } : null,
            { id: p + '_isp', label: 'Isp' },
            { id: p + '_thrust', label: 'Thrust' }
        ].filter(Boolean);

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
            (opts.motorType === 'solid'
                ? '      <button class="viz-btn" id="' + p + '_btn_portshape">Port: ' +
                  (PORT_LABELS[opts.portShape] || 'Circular') + '</button>'
                : '') +
            '      <button class="viz-btn warn" id="' + p + '_btn_heat">Heat Map</button>' +
            '      <button class="viz-btn" id="' + p + '_btn_rot">Orbit</button>' +
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
        host.innerHTML = deckHtml(p, opts);

        var hudLast = 0;
        var viz = MotorViz3D.mount(p + '_viewport', motorData, {
            onTick: function (s) {
                var now = performance.now();
                if (now - hudLast < 80) return;
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
                setChip(p + '_isp', s.isp ? s.isp.toFixed(1) : '—', 's', s.burning);
                var tv = s.thrust >= 1000 ? (s.thrust / 1000).toFixed(2) : s.thrust.toFixed(0);
                setChip(p + '_thrust', s.thrust > 0 ? tv : '0', s.thrust >= 1000 ? 'kN' : 'N', s.burning);
            }
        });
        if (!viz) return null;
        if (opts.portShape !== 'circular' && opts.motorType !== 'liquid') {
            viz.setPortShape(opts.portShape);
            syncPortBtn();
        }

        function setChip(id, val, unit, hot) {
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
                heatBtn.textContent = 'Heat Map (veri yok)';
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
                        (info.tWallInner ? 'T_wall iç ' + info.tWallInner.toFixed(0) + ' K' : '') +
                        (info.tWallOuter ? ' / dış ' + info.tWallOuter.toFixed(0) + ' K' : '');
                }
            }
        };

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
