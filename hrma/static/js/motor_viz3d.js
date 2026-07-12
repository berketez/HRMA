/*
 * MotorViz3D — HRMA hibrit roket motoru 3D simülasyon görselleştiricisi
 *
 * Three.js (r128 UMD) ile /calculate yanıtındaki results.motor sözlüğünden
 * parametrik motor modeli kurar: gövde + kapak + enjektör + grain + Rao
 * konturlu C-D nozul. Kesit (cutaway) görünümü, yanma animasyonu
 * (port regresyonu port_history serisinden), egzoz plume partikül sistemi,
 * ölçü etiketleri ve patlatılmış görünüm içerir.
 *
 * Genel kullanım:
 *   MotorViz3D.mount('viewport_div_id', results.motor, { onTick: fn })
 *
 * Koordinat düzeni: geometri lathe uzayında kurulur (motor ekseni +Y,
 * z=0 kapak iç yüzü), dış grup -90° z-rotasyonu ile ekseni dünya +X'e
 * yatırır. Kesit açıklığı lathe φ=0 yönüne (dünya +Z, kameraya) bakar.
 */
(function () {
    'use strict';

    if (typeof window === 'undefined') return;

    var TAU = Math.PI * 2;
    var CUT_PHI_START = Math.PI / 4;      // kesit modunda dolu bölge başlangıcı
    var CUT_PHI_LENGTH = 1.5 * Math.PI;   // 270° dolu, 90° açık (açıklık φ=0'da)
    var RADIAL_SEGMENTS = 96;

    // ------------------------------------------------------------------
    // Yardımcılar
    // ------------------------------------------------------------------

    function lerp(a, b, t) { return a + (b - a) * t; }
    function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

    function num(v, fallback) {
        return (typeof v === 'number' && isFinite(v)) ? v : fallback;
    }

    // Sıralı (time, value) serisinde lineer interpolasyon
    function sampleSeries(times, values, t) {
        if (!times || !values || times.length === 0) return null;
        if (t <= times[0]) return values[0];
        var n = times.length;
        if (t >= times[n - 1]) return values[n - 1];
        var lo = 0, hi = n - 1;
        while (hi - lo > 1) {
            var mid = (lo + hi) >> 1;
            if (times[mid] <= t) lo = mid; else hi = mid;
        }
        var span = times[hi] - times[lo];
        var f = span > 0 ? (t - times[lo]) / span : 0;
        return lerp(values[lo], values[hi], f);
    }

    function makeCanvas(w, h) {
        var c = document.createElement('canvas');
        c.width = w; c.height = h;
        return c;
    }

    // Yumuşak radyal parlama dokusu (plume ve alev için)
    function glowTexture(inner, outer) {
        var c = makeCanvas(128, 128);
        var g = c.getContext('2d');
        var grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
        grad.addColorStop(0, inner);
        grad.addColorStop(0.35, outer);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        g.fillStyle = grad;
        g.fillRect(0, 0, 128, 128);
        var tex = new THREE.CanvasTexture(c);
        tex.minFilter = THREE.LinearFilter;
        return tex;
    }

    // Monospace metin sprite'ı (ölçü etiketleri, HUD çağrıları)
    function textSprite(text, opts) {
        opts = opts || {};
        var fontPx = 44;
        var pad = 18;
        var font = '600 ' + fontPx + 'px "SF Mono", "JetBrains Mono", Consolas, monospace';
        var measure = makeCanvas(4, 4).getContext('2d');
        measure.font = font;
        var w = Math.ceil(measure.measureText(text).width) + pad * 2;
        var h = fontPx + pad * 2;
        var c = makeCanvas(w, h);
        var g = c.getContext('2d');
        g.font = font;
        g.textBaseline = 'middle';
        // arka plan rozeti
        g.fillStyle = opts.bg || 'rgba(4, 12, 20, 0.78)';
        var r = 14;
        g.beginPath();
        g.moveTo(r, 0); g.lineTo(w - r, 0); g.quadraticCurveTo(w, 0, w, r);
        g.lineTo(w, h - r); g.quadraticCurveTo(w, h, w - r, h);
        g.lineTo(r, h); g.quadraticCurveTo(0, h, 0, h - r);
        g.lineTo(0, r); g.quadraticCurveTo(0, 0, r, 0);
        g.closePath(); g.fill();
        g.strokeStyle = opts.border || 'rgba(0, 229, 255, 0.55)';
        g.lineWidth = 3;
        g.stroke();
        g.fillStyle = opts.color || '#9beaf7';
        g.fillText(text, pad, h / 2 + 2);
        var tex = new THREE.CanvasTexture(c);
        tex.minFilter = THREE.LinearFilter;
        // Ölçü etiketleri HUD niteliğinde: gövdenin arkasında kaybolmasın
        var mat = new THREE.SpriteMaterial({
            map: tex, transparent: true, depthWrite: false, depthTest: false
        });
        var sp = new THREE.Sprite(mat);
        sp.renderOrder = 10;
        sp.userData.aspect = w / h;
        return sp;
    }

    // ------------------------------------------------------------------
    // Motor verisinden boyut çıkarımı (hepsi mm)
    // ------------------------------------------------------------------

    function extractDims(md) {
        md = md || {};
        var gd = md.grain_design || {};
        var inj = md.injector_design || {};
        var contour = md.nozzle_contour || {};
        var conv = contour.convergent || {};
        var div = contour.divergent || {};
        var ds = md.design_summary || {};
        var dsNozzle = ds.nozzle || {};
        var angles = md.nozzle_angles || {};
        var struct = md.structural_analysis || {};
        var fasteners = struct.fastener_analysis || {};

        var Dch = num(md.chamber_diameter, 0.1) * 1000;
        var Lch = num(md.chamber_length, 0.3) * 1000;
        var dt = num(md.throat_diameter, 0.02) * 1000;
        var de = num(md.exit_diameter, 0.08) * 1000;
        var rt = dt / 2, re = de / 2, rc = Dch / 2;

        var casingWall = clamp(num(struct.chamber_analysis && struct.chamber_analysis.recommended_thickness, 0.045 * Dch), 3, 0.12 * Dch);
        var nozzleWall = clamp(num(md.nozzle_geometry && md.nozzle_geometry.wall_thickness, Math.max(3, 0.1 * dt)), 2.5, 0.25 * dt + 6);
        var liner = clamp(0.02 * Dch, 1.5, 5);

        var Lg = num(gd.grain_length_mm, num(md.grain_length, 0.8 * Lch / 1000) * 1000);
        Lg = Math.min(Lg, 0.92 * Lch);
        var rPort0 = num(gd.port_diameter_initial_mm, num(md.port_diameter_initial, 0.03) * 1000) / 2;
        var rPortF = num(gd.port_diameter_final_mm, num(md.port_diameter_final, 0.05) * 1000) / 2;
        var rGrainOut = rc - liner;
        rPortF = Math.min(rPortF, rGrainOut - 1);
        rPort0 = Math.min(rPort0, rPortF);

        // Konverjan uzunluk: GERÇEK kamara yarıçapına dayanan design_summary
        // önceliklidir — nozzle_contour.convergent.length, NozzleDesigner'ın
        // kendi daralma oranı oda yarıçapından (≈1.5·rt) türediği için hibrit
        // kamara çapıyla tutarsızdır (dikey duvar görünümü yaratır).
        var nozType = (div.type || angles.nozzle_type || 'conical');
        // Açı alt sınırı 1°: sıfır/bozuk açıda tan(0) → Infinity geometri
        var convAngle = Math.max(1, num(angles.convergent_half_angle_deg, 30));
        var Lc = num(dsNozzle.convergent_length_mm,
            (rc - rt) / Math.tan(THREE.MathUtils.degToRad(convAngle)));
        // Diverjan uzunlukta gerçek kontur (bell/Rao) esastır
        var divAngle = Math.max(1, num(angles.divergent_half_angle_deg, 15));
        var Ld = num(div.length, num(dsNozzle.divergent_length_mm,
            (re - rt) / Math.tan(THREE.MathUtils.degToRad(divAngle))));
        var thetaN = num(div.throat_angle, 30);
        var thetaE = num(div.exit_angle, 8);
        var halfAngle = Math.max(1, num(div.half_angle, num(angles.divergent_half_angle_deg, 15)));
        var Rn = num(conv.throat_radius_curvature, 0.382 * rt);
        var Rconv = num(conv.throat_curvature_convergent, 1.5 * rt);

        var capT = clamp(1.6 * casingWall, 8, 0.3 * rc + 8);
        var flangeT = clamp(0.8 * capT, 6, 26);
        var flangeLip = clamp(0.10 * rc, 4, 18);

        // Grain kamara içinde: ön yanma odası %35, art yanma odası %65
        var slack = Math.max(4, Lch - Lg);
        var zg0 = 0.35 * slack;
        var zg1 = zg0 + Lg;

        // Isıl veri (ısı haritası modu için): kamara/boğaz ısı akısı çapaları
        // ve duvar sıcaklıkları — motor sonucundaki gerçek analiz değerleri
        var ht = md.heat_transfer_analysis || {};
        var gas = ht.gas_side_analysis || {};
        var wallAn = ht.wall_analysis || {};
        var heat = null;
        if (gas.throat_heat_flux) {
            heat = {
                qThroat: num(gas.throat_heat_flux, 0),
                qChamber: num(gas.chamber_heat_flux, num(gas.throat_heat_flux, 0) * 0.12),
                tWallInner: num(wallAn.inner_temperature, null),
                tWallOuter: num(wallAn.outer_temperature, null)
            };
        }

        return {
            // 'hybrid' | 'solid' | 'liquid' — sayfa adaptörü belirler
            motorType: md.viz_motor_type || 'hybrid',
            Dch: Dch, Lch: Lch, rc: rc, rt: rt, re: re, dt: dt, de: de,
            casingWall: casingWall, nozzleWall: nozzleWall, liner: liner,
            rcOut: rc + casingWall,
            Lg: Lg, zg0: zg0, zg1: zg1,
            rPort0: rPort0, rPortF: rPortF, rGrainOut: rGrainOut,
            nozType: nozType, Lc: Lc, Ld: Ld,
            thetaN: thetaN, thetaE: thetaE, halfAngle: halfAngle,
            Rn: Rn, Rconv: Rconv,
            capT: capT, flangeT: flangeT, flangeLip: flangeLip,
            inletR: clamp(0.22 * rc, 5, 22),
            inletL: clamp(1.6 * capT, 14, 60),
            nOrifices: Math.max(4, Math.round(num(inj.number_of_orifices, 12))),
            orificeR: clamp(num(inj.orifice_diameter_mm, 1.5) / 2, 0.8, 4),
            nBolts: Math.max(6, Math.round(num(fasteners.num_bolts, 8))),
            burnTime: Math.max(0.1, num(md.burn_time, 10)),
            thrust: num(md.thrust, 1000),
            isp: num(md.isp, 200),
            pc: num(md.chamber_pressure, 20),
            of0: num(md.of_ratio_initial, num(md.of_ratio, 2)),
            portHist: md.port_history || null,
            ofShift: md.of_shift_performance || null,
            heat: heat
        };
    }

    // t anındaki port yarıçapı (mm). Önce backend serisi, yoksa
    // sabit hacimsel üretim varsayımıyla karekök interpolasyonu.
    function portRadiusAt(dims, t) {
        var hist = dims.portHist;
        if (hist && hist.time && hist.port_diameter && hist.time.length > 1) {
            var d = sampleSeries(hist.time, hist.port_diameter, t);
            if (d !== null) return clamp(d * 1000 / 2, dims.rPort0, dims.rGrainOut - 0.5);
        }
        var f = clamp(t / dims.burnTime, 0, 1);
        var r2 = lerp(dims.rPort0 * dims.rPort0, dims.rPortF * dims.rPortF, f);
        return Math.sqrt(r2);
    }

    // ------------------------------------------------------------------
    // Kapalı (r,z) poligonundan katı: lathe yüzeyi + kesit kapak yüzleri
    // ------------------------------------------------------------------

    function buildSolid(profile, material, sectionMaterial, cutaway) {
        var group = new THREE.Group();
        var pts = profile.map(function (p) { return new THREE.Vector2(Math.max(0, p.r), p.z); });
        // Yüzeyi kapatmak için poligonu geri sarma (lathe açık profil ister,
        // kapalı poligon verince yan yüzeyler zaten oluşur)
        var closed = pts.slice();
        if (closed[0].x !== closed[closed.length - 1].x || closed[0].y !== closed[closed.length - 1].y) {
            closed.push(closed[0].clone());
        }
        var phiStart = cutaway ? CUT_PHI_START : 0;
        var phiLength = cutaway ? CUT_PHI_LENGTH : TAU;
        var lathe = new THREE.LatheGeometry(closed, RADIAL_SEGMENTS, phiStart, phiLength);
        var mesh = new THREE.Mesh(lathe, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        group.add(mesh);

        if (cutaway && sectionMaterial) {
            // Kesit kapakları: aynı poligon iki kesme düzlemine yerleştirilir
            var shape = new THREE.Shape(pts.map(function (p) { return new THREE.Vector2(p.x, p.y); }));
            var capGeoBase = new THREE.ShapeGeometry(shape);
            [phiStart, phiStart + phiLength].forEach(function (phi) {
                var geo = capGeoBase.clone();
                // (r, z, 0) -> (r·sinφ, z, r·cosφ); 3. kolon = düzlem normali
                // (tekil matris normalleri sıfırlayıp yüzeyi karartır)
                var m = new THREE.Matrix4().set(
                    Math.sin(phi), 0, -Math.cos(phi), 0,
                    0, 1, 0, 0,
                    Math.cos(phi), 0, Math.sin(phi), 0,
                    0, 0, 0, 1
                );
                geo.applyMatrix4(m);
                var cap = new THREE.Mesh(geo, sectionMaterial);
                cap.castShadow = false;
                cap.receiveShadow = false;
                group.add(cap);
            });
        }
        return group;
    }

    // ------------------------------------------------------------------
    // Port kesit şekilleri (yıldız / çok-port / finocyl)
    //
    // Şekiller HEDEF ALANA eşitlenir (π·rEq²): balistik dairesel-eşdeğer
    // port ile çözülür, kesit yalnız GEOMETRİK gösterimdir. Regresyon
    // animasyonu şekli rEq(t)/rEq(0) oranıyla üniform ölçekler (birinci
    // mertebe yaklaşım).
    // ------------------------------------------------------------------

    // Koordinat sözleşmesi: kesit düzlemi noktaları LATHE-HİZALI üretilir —
    // genPt(φ, r) noktası, ExtrudeGeometry.rotateX(-π/2) sonrası dünya
    // uzayında lathe açısı φ'ye düşer ((x,y,z)→(x, z, −y); sinφ=x/r,
    // cosφ=−y/r). Böylece kesit kaması cutaway açıklığıyla hizalanır.

    function genPt(phi, r) {
        return { x: r * Math.sin(phi), y: -r * Math.cos(phi) };
    }

    function ptPhi(p) {
        var a = Math.atan2(p.x, -p.y);
        return a < 0 ? a + TAU : a;
    }

    function ptR(p) { return Math.hypot(p.x, p.y); }

    function polygonArea(pts) {
        var a = 0;
        for (var i = 0; i < pts.length; i++) {
            var j = (i + 1) % pts.length;
            a += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
        }
        return Math.abs(a) / 2;
    }

    function scalePoly(pts, f) {
        return pts.map(function (p) { return { x: p.x * f, y: p.y * f }; });
    }

    function circlePoly(r, n, cx, cy) {
        var pts = [];
        for (var i = 0; i < (n || 48); i++) {
            var p = genPt((i / (n || 48)) * TAU, r);
            pts.push({ x: p.x + (cx || 0), y: p.y + (cy || 0) });
        }
        return pts;
    }

    // Dönen yapı: { holes: [poligon,...], inscribed: eksen boşluğu yarıçapı,
    //   satellites: [{phi, cx, cy, r}] (multiport), boundary: eksen-merkezli
    //   ana port poligonu (kesit kaması iç sınırı için) }
    function portShapeHoles(shape, rEq, maxR) {
        var target = Math.PI * rEq * rEq;
        var f, pts, i;
        if (shape === 'star') {
            var n = 6, Ro = 1, Ri = 0.45;
            pts = [];
            for (i = 0; i < 2 * n; i++) {
                var a = (i / (2 * n)) * TAU;
                pts.push(genPt(a, (i % 2 === 0) ? Ro : Ri));
            }
            f = Math.min(Math.sqrt(target / polygonArea(pts)), maxR / Ro);
            var poly = scalePoly(pts, f);
            return { holes: [poly], boundary: poly, inscribed: Ri * f * 0.95, satellites: [] };
        }
        if (shape === 'multiport') {
            // Wagon wheel: merkez + 6 uydu port (7 eş port). Uydular kesme
            // düzlemlerinden (φ=45°/315°) uzak açılara yerleştirilir.
            var rp = rEq / Math.sqrt(7);
            var ring = 2.55 * rp;
            if (ring + rp > maxR) {
                var k = maxR / (ring + rp);
                rp *= k; ring *= k;
            }
            var center = circlePoly(rp, 32, 0, 0);
            var satellites = [];
            var satPhis = [90, 150, 210, 270, 330, 30];
            for (i = 0; i < 6; i++) {
                var sp = THREE.MathUtils.degToRad(satPhis[i]);
                var cpt = genPt(sp, ring);
                satellites.push({ phi: sp, cx: cpt.x, cy: cpt.y, r: rp });
            }
            var holes = [center].concat(satellites.map(function (s2) {
                return circlePoly(s2.r, 32, s2.cx, s2.cy);
            }));
            return { holes: holes, boundary: center, inscribed: rp * 0.95, satellites: satellites };
        }
        if (shape === 'finocyl') {
            // Merkez daire + 6 radyal kanat (slot) — tek dış hat poligonu.
            // Sınır, eksene göre yıldız-şekilli (radyal ışın tek kesişim).
            var rc0 = 0.62, finL = 1.05, finW = 0.30, nf = 6;
            pts = [];
            for (i = 0; i < nf; i++) {
                var a0 = (i / nf) * TAU;
                var half = Math.asin(clamp(finW / 2 / rc0, 0, 0.9));
                var aPrev = a0 + half;
                var aNext = a0 + TAU / nf - half;
                var tip = genPt(a0, rc0 + finL);
                var perp = genPt(a0 + Math.PI / 2, finW / 2);
                pts.push(genPt(a0 - half, rc0));
                pts.push({ x: tip.x - perp.x, y: tip.y - perp.y });
                pts.push({ x: tip.x + perp.x, y: tip.y + perp.y });
                pts.push(genPt(aPrev, rc0));
                for (var k2 = 1; k2 <= 6; k2++) {
                    pts.push(genPt(aPrev + (aNext - aPrev) * (k2 / 6), rc0));
                }
            }
            f = Math.min(Math.sqrt(target / polygonArea(pts)), maxR / (rc0 + finL));
            var poly2 = scalePoly(pts, f);
            return { holes: [poly2], boundary: poly2, inscribed: rc0 * f * 0.95, satellites: [] };
        }
        // circular (varsayılan)
        var r = Math.min(rEq, maxR);
        var cp = circlePoly(r, 48, 0, 0);
        return { holes: [cp], boundary: cp, inscribed: r, satellites: [] };
    }

    // Eksen-merkezli, yıldız-şekilli sınırda r(φ) — poligon kenarlarını
    // alt bölerek açı-sıralı tablo kurar, sorguda lineer interpolasyon
    function boundaryRadialFn(poly) {
        var samples = [];
        for (var i = 0; i < poly.length; i++) {
            var a = poly[i], b = poly[(i + 1) % poly.length];
            for (var k = 0; k < 6; k++) {
                var t = k / 6;
                var p = { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
                samples.push({ phi: ptPhi(p), r: ptR(p) });
            }
        }
        samples.sort(function (u, v) { return u.phi - v.phi; });
        return function (phi) {
            phi = ((phi % TAU) + TAU) % TAU;
            var n = samples.length;
            var lo = 0, hi = n - 1;
            if (phi <= samples[0].phi || phi >= samples[n - 1].phi) {
                // sarmal aralık: son ↔ ilk
                var A = samples[n - 1], B = samples[0];
                var span = (B.phi + TAU) - A.phi;
                var ff = span > 1e-9 ? (((phi + TAU) - A.phi) % TAU) / span : 0;
                return lerp(A.r, B.r, clamp(ff, 0, 1));
            }
            while (hi - lo > 1) {
                var mid = (lo + hi) >> 1;
                if (samples[mid].phi <= phi) lo = mid; else hi = mid;
            }
            var s0 = samples[lo], s1 = samples[hi];
            var f2 = (phi - s0.phi) / Math.max(s1.phi - s0.phi, 1e-9);
            return lerp(s0.r, s1.r, f2);
        };
    }

    function polyToShapePath(pts) {
        var path = new THREE.Shape();
        path.moveTo(pts[0].x, pts[0].y);
        for (var i = 1; i < pts.length; i++) path.lineTo(pts[i].x, pts[i].y);
        path.closePath();
        return path;
    }

    function polyToHolePath(pts) {
        var hp = new THREE.Path();
        hp.moveTo(pts[0].x, pts[0].y);
        for (var i = 1; i < pts.length; i++) hp.lineTo(pts[i].x, pts[i].y);
        hp.closePath();
        return hp;
    }

    // ------------------------------------------------------------------
    // Isı haritası renk skalası: koyu lacivert → kızıl → turuncu → akkor
    // ------------------------------------------------------------------

    var HEAT_STOPS = [
        [0.00, 0x0b2447], [0.45, 0x8e2f22], [0.75, 0xe4652c],
        [0.92, 0xffb054], [1.00, 0xfff3d6]
    ];

    function heatColor(t) {
        t = clamp(t, 0, 1);
        for (var i = 1; i < HEAT_STOPS.length; i++) {
            if (t <= HEAT_STOPS[i][0]) {
                var a = HEAT_STOPS[i - 1], b = HEAT_STOPS[i];
                var f = (t - a[0]) / (b[0] - a[0]);
                var ca = new THREE.Color(a[1]), cb = new THREE.Color(b[1]);
                return ca.lerp(cb, f);
            }
        }
        return new THREE.Color(HEAT_STOPS[HEAT_STOPS.length - 1][1]);
    }

    // ------------------------------------------------------------------
    // Nozul iç konturu: konverjan (kosinüs blend) + Rao boğaz yayı +
    // konik doğru ya da bell (kuadratik Bézier, θn→θe)
    // ------------------------------------------------------------------

    function nozzleInnerContour(dims) {
        var pts = [];
        var z0 = dims.Lch;          // konverjan başlangıcı
        var zt = dims.Lch + dims.Lc; // boğaz istasyonu
        var i, n;

        // Konverjan: rc -> rt, iki uçta sıfır eğimli yumuşak geçiş
        n = 26;
        for (i = 0; i <= n; i++) {
            var s = i / n;
            var r = dims.rt + (dims.rc - dims.rt) * (0.5 + 0.5 * Math.cos(Math.PI * s));
            pts.push({ z: z0 + dims.Lc * s, r: r });
        }

        // Boğaz çıkış yayı (Rao, yarıçap Rn) — boğazdan θ açısına kadar
        var thetaMax = THREE.MathUtils.degToRad(dims.nozType === 'conical' ? dims.halfAngle : dims.thetaN);
        n = 14;
        var arcEnd = null;
        for (i = 1; i <= n; i++) {
            var a = thetaMax * (i / n);
            arcEnd = {
                z: zt + dims.Rn * Math.sin(a),
                r: dims.rt + dims.Rn * (1 - Math.cos(a))
            };
            pts.push(arcEnd);
        }

        var zExitTarget = zt + dims.Ld;
        if (dims.nozType === 'conical') {
            // Yaydan sonra düz koni — çıkış yarıçapına ulaşınca kes
            var slope = Math.tan(thetaMax);
            var zExit = arcEnd.z + (dims.re - arcEnd.r) / slope;
            pts.push({ z: zExit, r: dims.re });
        } else {
            // Bell: yay ucundan (eğim tanθn) çıkışa (eğim tanθe) kuadratik Bézier
            var t0 = Math.tan(thetaMax);
            var t1 = Math.tan(THREE.MathUtils.degToRad(dims.thetaE));
            var P0 = { z: arcEnd.z, r: arcEnd.r };
            var P2 = { z: zExitTarget, r: dims.re };
            // Kontrol noktası: iki teğet doğrunun kesişimi
            var zc = (P2.r - P0.r + t0 * P0.z - t1 * P2.z) / (t0 - t1);
            zc = clamp(zc, P0.z + 0.05 * (P2.z - P0.z), P2.z - 0.05 * (P2.z - P0.z));
            var P1 = { z: zc, r: P0.r + t0 * (zc - P0.z) };
            n = 26;
            for (i = 1; i <= n; i++) {
                var u = i / n, v = 1 - u;
                pts.push({
                    z: v * v * P0.z + 2 * v * u * P1.z + u * u * P2.z,
                    r: v * v * P0.r + 2 * v * u * P1.r + u * u * P2.r
                });
            }
        }
        return pts;
    }

    // Nozul katı poligonu: iç kontur + duvar ofsetli dış yol + montaj flanşı
    function nozzleProfile(dims) {
        var inner = nozzleInnerContour(dims);
        var zEnd = inner[inner.length - 1].z;
        var flangeR = dims.rcOut + dims.flangeLip;
        var flangeZ1 = dims.Lch + dims.flangeT;

        var poly = [];
        // iç yüzey (öne doğru)
        inner.forEach(function (p) { poly.push({ r: p.r, z: p.z }); });
        // çıkış dudağı
        poly.push({ r: inner[inner.length - 1].r + dims.nozzleWall, z: zEnd });
        // dış yüzey (geriye doğru, duvar ofseti + flanş bölgesi)
        for (var i = inner.length - 1; i >= 0; i--) {
            var p = inner[i];
            var rOut = p.r + dims.nozzleWall;
            if (p.z <= flangeZ1) rOut = Math.max(rOut, flangeR);
            poly.push({ r: rOut, z: p.z });
        }
        return { poly: poly, zExit: zEnd, rExit: inner[inner.length - 1].r,
                 flangeR: flangeR, inner: inner };
    }

    // ------------------------------------------------------------------
    // Ana görselleştirici
    // ------------------------------------------------------------------

    var viz = null; // tek aktif örnek

    function createMaterials() {
        return {
            casing: new THREE.MeshStandardMaterial({ color: 0x97a4b5, metalness: 0.88, roughness: 0.34 }),
            casingCut: new THREE.MeshStandardMaterial({ color: 0xc3ccd8, metalness: 0.15, roughness: 0.9, side: THREE.DoubleSide }),
            nozzle: new THREE.MeshStandardMaterial({ color: 0x454e59, metalness: 0.72, roughness: 0.42 }),
            nozzleCut: new THREE.MeshStandardMaterial({ color: 0x6e7987, metalness: 0.1, roughness: 0.95, side: THREE.DoubleSide }),
            grain: new THREE.MeshStandardMaterial({ color: 0x6d4326, metalness: 0.0, roughness: 0.94 }),
            grainCut: new THREE.MeshStandardMaterial({ color: 0x936243, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            liner: new THREE.MeshStandardMaterial({ color: 0x23282e, metalness: 0.05, roughness: 0.9 }),
            linerCut: new THREE.MeshStandardMaterial({ color: 0x3a4046, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            injector: new THREE.MeshStandardMaterial({ color: 0xb08d57, metalness: 0.85, roughness: 0.38 }),
            injectorCut: new THREE.MeshStandardMaterial({ color: 0xd2b184, metalness: 0.2, roughness: 0.85, side: THREE.DoubleSide }),
            bolt: new THREE.MeshStandardMaterial({ color: 0x2e343c, metalness: 0.8, roughness: 0.45 }),
            orifice: new THREE.MeshStandardMaterial({ color: 0x10151a, metalness: 0.2, roughness: 0.8 })
        };
    }

    function MotorScene(container, motorData, hooks) {
        this.container = container;
        this.hooks = hooks || {};
        this.dims = extractDims(motorData);
        this.state = {
            time: 0, playing: false, speed: 1,
            cutaway: true, labels: true, plume: true,
            exploded: false, autoRotate: false,
            portShape: 'circular',   // circular | star | multiport | finocyl
            heatMap: false           // duvar ısıl akı giydirmesi
        };
        this._explodeF = 0; // 0=montajlı, 1=patlatılmış
        this._lastPortR = -1;
        this._disposed = false;

        this._initRenderer();
        this._initSceneGraph();
        this._buildMotor();
        this._buildPlume();
        this._buildLabels();
        this._fitCamera();
        this._bindResize();

        this._clock = new THREE.Clock();
        this._introT = 0;
        var self = this;
        (function loop() {
            if (self._disposed) return;
            self._raf = requestAnimationFrame(loop);
            self._tick();
        })();
    }

    MotorScene.prototype._initRenderer = function () {
        var w = this.container.clientWidth || 800;
        var h = this.container.clientHeight || 520;
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        this.renderer.setSize(w, h);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.renderer.domElement.style.display = 'block';
        this.container.appendChild(this.renderer.domElement);

        this.camera = new THREE.PerspectiveCamera(40, w / h, 1, 100000);
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.autoRotateSpeed = 0.9;
    };

    MotorScene.prototype._initSceneGraph = function () {
        this.scene = new THREE.Scene();
        // Opak sahne arka planı: şeffaf canvas + additive partiküller sayfa
        // arka planına karşı siyah kare artefaktı bırakıyordu
        this.scene.background = new THREE.Color(0x070d17);
        this.scene.fog = null;

        // Işıklar: nötr anahtar + cyan/turuncu jant ışıkları (sci-fi ton)
        this.scene.add(new THREE.HemisphereLight(0x93a7c4, 0x0a0e14, 0.55));
        var key = new THREE.DirectionalLight(0xffffff, 0.95);
        key.castShadow = true;
        key.shadow.mapSize.set(2048, 2048);
        this._keyLight = key;
        this.scene.add(key);
        this._rimCyan = new THREE.PointLight(0x00e5ff, 0.55, 0, 2);
        this._rimOrange = new THREE.PointLight(0xff7a1a, 0.4, 0, 2);
        this.scene.add(this._rimCyan, this._rimOrange);

        // Yanma ışıkları (dinamik)
        this._combLight = new THREE.PointLight(0xff8c33, 0, 0, 2);
        this._exitLight = new THREE.PointLight(0xffb066, 0, 0, 2);
        this.scene.add(this._combLight, this._exitLight);

        // Motor ekseni +X olacak şekilde döndürülen kök grup
        this.root = new THREE.Group();
        this.root.rotation.z = -Math.PI / 2;
        this.scene.add(this.root);
        // modelGroup: lathe uzayı; y-ofseti ile merkezlenir
        this.model = new THREE.Group();
        this.root.add(this.model);
    };

    MotorScene.prototype._buildMotor = function () {
        var d = this.dims;
        // Malzemeler bir kez üretilir (cutaway toggle'da yeniden kurulumda
        // material/texture sızıntısı olmasın — hakem bulgusu H1)
        var mats = this.mats || (this.mats = createMaterials());
        var cut = this.state.cutaway;

        if (this.assembly) {
            this.model.remove(this.assembly);
            this.assembly.traverse(function (o) {
                // Sprite geometry'si Three.js'te modül-seviyesi paylaşımlı —
                // yalnız mesh/line/points geometrilerini dispose et
                if (o.geometry && !o.isSprite) o.geometry.dispose();
            });
        }
        this.assembly = new THREE.Group();
        this.parts = {};

        // --- Gövde: baş kapak + silindirik tüp (tek katı) ---
        var casingPoly = [
            { r: 0, z: -d.capT },
            { r: d.rcOut, z: -d.capT },
            { r: d.rcOut, z: d.Lch },
            { r: d.rc, z: d.Lch },
            { r: d.rc, z: 0 },
            { r: 0, z: 0 }
        ];
        var casing = buildSolid(casingPoly, mats.casing, mats.casingCut, cut);
        this.parts.casing = casing;

        var isLiquid = d.motorType === 'liquid';
        var isSolid = d.motorType === 'solid';

        // Oksitleyici/yakıt giriş borusu + rakor (katıda yok — kapalı kapak)
        if (!isSolid) {
            var inletPoly = [
                { r: 0, z: -d.capT - d.inletL },
                { r: d.inletR, z: -d.capT - d.inletL },
                { r: d.inletR, z: -d.capT + 1 },
                { r: 0, z: -d.capT + 1 }
            ];
            casing.add(buildSolid(inletPoly, mats.casing, null, false));
            var collar = new THREE.Mesh(
                new THREE.TorusGeometry(d.inletR + 1.5, 2.2, 12, 40),
                mats.bolt
            );
            collar.rotation.x = Math.PI / 2;
            collar.position.y = -d.capT - d.inletL * 0.55;
            casing.add(collar);
        }

        // Sıvı motor: rejeneratif soğutma kanalı bilezikleri (görsel detay)
        if (isLiquid) {
            var nRib = 8;
            var ribGeo = new THREE.TorusGeometry(d.rcOut + 1.2, 1.4, 10, 48);
            for (var rb = 0; rb < nRib; rb++) {
                var rib = new THREE.Mesh(ribGeo, mats.bolt);
                rib.rotation.x = Math.PI / 2;
                rib.position.y = d.Lch * (0.12 + 0.76 * rb / (nRib - 1));
                rib.castShadow = true;
                casing.add(rib);
            }
        }

        // --- Liner (fenolik yalıtım tüpü — grain'li motorlarda) ---
        if (!isLiquid) {
            var linerPoly = [
                { r: d.rGrainOut, z: 2 },
                { r: d.rc - 0.15, z: 2 },
                { r: d.rc - 0.15, z: d.Lch - 2 },
                { r: d.rGrainOut, z: d.Lch - 2 }
            ];
            this.parts.liner = buildSolid(linerPoly, mats.liner, mats.linerCut, cut);
        } else {
            this.parts.liner = new THREE.Group();
        }

        // --- Enjektör plakası + orifis deseni (katı motorda yok) ---
        if (!isSolid) {
            var injT = clamp(0.9 * d.capT, 6, 24);
            var injZ0 = 4;
            var injPoly = [
                { r: 0, z: injZ0 },
                { r: d.rc - 0.4, z: injZ0 },
                { r: d.rc - 0.4, z: injZ0 + injT },
                { r: 0, z: injZ0 + injT }
            ];
            var injector = buildSolid(injPoly, mats.injector, mats.injectorCut, cut);
            var oriGeo = new THREE.CylinderGeometry(Math.max(d.orificeR * 1.6, 1.2), Math.max(d.orificeR * 1.6, 1.2), 1.6, 12);
            for (var k = 0; k < d.nOrifices; k++) {
                var phi = (k / d.nOrifices) * TAU;
                var rr = 0.55 * d.rc;
                var ori = new THREE.Mesh(oriGeo, mats.orifice);
                ori.position.set(rr * Math.sin(phi), injZ0 + injT + 0.5, rr * Math.cos(phi));
                ori.userData.phi = phi;
                ori.userData.hideInCut = true;
                injector.add(ori);
            }
            this.parts.injector = injector;
        } else {
            this.parts.injector = new THREE.Group();
        }

        // --- Yakıt grain'i (port yarıçapı animasyonlu — ayrı build) ---
        this.parts.grain = new THREE.Group();
        this._grainMesh = null;
        this._rebuildGrain(portRadiusAt(d, this.state.time), true);

        // --- Nozul (+ montaj flanşı) ---
        var np = nozzleProfile(d);
        this._nozzleInfo = np;
        var nozzle = buildSolid(np.poly, mats.nozzle, mats.nozzleCut, cut);
        // Flanş cıvataları
        var boltR = clamp(0.05 * d.rc, 2.2, 6);
        var boltGeo = new THREE.CylinderGeometry(boltR, boltR, d.flangeT * 0.9, 6); // altıgen başlı görünüm
        var boltCircle = (np.flangeR + d.rcOut) / 2 + 1;
        for (var b = 0; b < d.nBolts; b++) {
            var bphi = ((b + 0.5) / d.nBolts) * TAU;
            var bolt = new THREE.Mesh(boltGeo, mats.bolt);
            bolt.position.set(boltCircle * Math.sin(bphi), d.Lch + d.flangeT + 2, boltCircle * Math.cos(bphi));
            bolt.userData.phi = bphi;
            bolt.userData.hideInCut = true;
            bolt.castShadow = true;
            nozzle.add(bolt);
        }
        this.parts.nozzle = nozzle;

        // --- Port içi yanma parıltısı (materyal + alev spriteı tek sefer) ---
        if (!this._glowMat) {
            this._glowMat = new THREE.MeshBasicMaterial({
                color: 0xff8a2a, transparent: true, opacity: 0,
                blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide
            });
        }
        this._glowMesh = null;
        this._rebuildGlow(portRadiusAt(d, this.state.time));

        // Boğaz alev diski
        if (!this._throatFlame) {
            this._throatFlame = new THREE.Sprite(new THREE.SpriteMaterial({
                map: glowTexture('rgba(255,255,235,1)', 'rgba(255,140,40,0.85)'),
                transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0
            }));
        }
        // Konum/ölçek her kurulumda tazelenir (update() geometri değiştirebilir)
        this._throatFlame.position.set(0, d.Lch + d.Lc, 0);
        this._throatFlame.scale.setScalar(d.rt * 3.2);

        this.assembly.add(this.parts.casing, this.parts.liner, this.parts.injector,
            this.parts.grain, this.parts.nozzle, this._throatFlame);

        // Modeli merkeze al
        var zMin = -d.capT - d.inletL;
        var zMax = np.zExit;
        this._zCenter = (zMin + zMax) / 2;
        this._totalLen = zMax - zMin;
        this.model.position.y = -this._zCenter;

        this.model.add(this.assembly);
        this._applyCutVisibility();
        this._applyExplode(this._explodeF);
        this._applyHeatMap();

        // Zemin: gölge düzlemi + ızgara
        if (!this._floor) {
            var floorY = -(this.dims.rcOut + this.dims.flangeLip) * 1.9;
            var shadowPlane = new THREE.Mesh(
                new THREE.PlaneGeometry(this._totalLen * 4, this._totalLen * 4),
                new THREE.ShadowMaterial({ opacity: 0.32 })
            );
            shadowPlane.rotation.x = -Math.PI / 2;
            shadowPlane.position.y = floorY;
            shadowPlane.receiveShadow = true;
            this.scene.add(shadowPlane);
            var grid = new THREE.GridHelper(this._totalLen * 3, 30, 0x0e6f80, 0x123340);
            grid.material.transparent = true;
            grid.material.opacity = 0.35;
            grid.position.y = floorY + 0.5;
            this.scene.add(grid);
            this._floor = shadowPlane;
        }
    };

    // Grain katısını verilen eşdeğer port yarıçapıyla yeniden kur.
    // circular: lathe halka. Diğer şekiller: tam görünümde gerçek kesitli
    // ekstrüzyon; kesit görünümünde lathe gövde (iç = şeklin iç teğet
    // yarıçapı) + kesme yüzeylerinde GERÇEK kesit kapakları.
    MotorScene.prototype._rebuildGrain = function (rPort, force) {
        if (!force && Math.abs(rPort - this._lastPortR) < 0.05) return;
        this._lastPortR = rPort;
        var d = this.dims;
        var g = this.parts.grain;
        while (g.children.length) {
            var c = g.children.pop();
            c.traverse(function (o) { if (o.geometry && !o.isSprite) o.geometry.dispose(); });
        }
        if (d.motorType === 'liquid') { this._portInscribed = d.rt; return; }
        if (rPort >= d.rGrainOut - 0.4) { this._portInscribed = rPort; return; }

        var shape = this.state.portShape || 'circular';
        var mats = this.mats;
        var cut = this.state.cutaway;

        if (shape === 'circular') {
            this._portInscribed = rPort;
            var poly = [
                { r: rPort, z: d.zg0 },
                { r: d.rGrainOut, z: d.zg0 },
                { r: d.rGrainOut, z: d.zg1 },
                { r: rPort, z: d.zg1 }
            ];
            g.add(buildSolid(poly, mats.grain, mats.grainCut, cut));
            return;
        }

        var sh = portShapeHoles(shape, rPort, d.rGrainOut - 1);
        this._portInscribed = sh.inscribed;

        var extrudeOpts = { depth: d.Lg, bevelEnabled: false, curveSegments: 24 };

        function addExtrude(shapePath, mat) {
            var geo = new THREE.ExtrudeGeometry(shapePath, extrudeOpts);
            geo.rotateX(-Math.PI / 2);           // +Z (derinlik) → +Y (motor ekseni)
            geo.translate(0, d.zg0, 0);
            var mesh = new THREE.Mesh(geo, mat);
            mesh.castShadow = true;
            mesh.receiveShadow = true;
            g.add(mesh);
        }

        if (!cut) {
            // Tam görünüm: dış daire + gerçek port delikleri, 360° ekstrüzyon
            var outer = polyToShapePath(circlePoly(d.rGrainOut, 64, 0, 0));
            outer.holes = sh.holes.map(polyToHolePath);
            addExtrude(outer, mats.grain);
            return;
        }

        // Kesit görünümü: 270° halka kaması TEK poligon olarak kurulur —
        // dış yay (φ: 45°→315°) + gerçek port sınırı boyunca geri dönüş.
        // Ekstrüzyonun düz yan duvarları kesme yüzleridir; iç yüzey gerçek
        // lob geometrisini gösterir.
        var phi0 = CUT_PHI_START, phi1 = CUT_PHI_START + CUT_PHI_LENGTH;
        var rIn = boundaryRadialFn(sh.boundary);
        var pts = [];
        var N_ARC = 72, N_IN = 96, i;
        for (i = 0; i <= N_ARC; i++) {  // dış yay, φ artan
            pts.push(genPt(phi0 + (phi1 - phi0) * (i / N_ARC), d.rGrainOut));
        }
        for (i = N_IN; i >= 0; i--) {   // iç sınır, φ azalan
            var ph = phi0 + (phi1 - phi0) * (i / N_IN);
            pts.push(genPt(ph, clamp(rIn(ph), 1, d.rGrainOut - 0.5)));
        }
        var wedge = polyToShapePath(pts);
        // Kama içinde tam kalan uydu portlar delik olarak eklenir
        // (kesme düzlemine 12°'den yakın olanlar atlanır)
        wedge.holes = (sh.satellites || []).filter(function (s) {
            var margin = THREE.MathUtils.degToRad(12);
            return s.phi > phi0 + margin && s.phi < phi1 - margin;
        }).map(function (s) {
            return polyToHolePath(circlePoly(s.r, 24, s.cx, s.cy));
        });
        addExtrude(wedge, mats.grain);
    };

    MotorScene.prototype._rebuildGlow = function (rPort) {
        var d = this.dims;
        if (this._glowMesh) {
            this.assembly.remove(this._glowMesh);
            this._glowMesh.geometry.dispose();
        }
        // Şekilli portlarda parıltı, iç teğet yarıçapa oturur
        var rBase = (this._portInscribed !== undefined) ? this._portInscribed : rPort;
        if (d.motorType === 'liquid') rBase = d.rc * 0.85; // kamara hacmi parıltısı
        var r = Math.max(rBase - 0.6, 1);
        var geo = new THREE.CylinderGeometry(r, r, d.zg1 - d.zg0 + 0.6 * (d.Lch - d.zg1), 40, 1, true);
        this._glowMesh = new THREE.Mesh(geo, this._glowMat);
        this._glowMesh.position.y = (d.zg0 + d.Lch) / 2; // portu + art odasını kapla
        this.assembly.add(this._glowMesh);
    };

    // ------------------------------------------------------------------
    // Isı haritası: duvar üstüne ısıl akı dağılımı (Bartz alan-oranı
    // ölçeklemesi, kamara/boğaz çapaları gerçek analizden)
    // ------------------------------------------------------------------

    // Motor-z konumunda yerel akış yarıçapı (mm) — kamara içinde rc,
    // nozulda gerçek kontur, çıkış sonrası rExit
    MotorScene.prototype._flowRadiusAt = function (z) {
        var d = this.dims;
        if (z <= d.Lch) return d.rc;
        var pts = this._nozzleInfo ? this._nozzleInfo.inner : null;
        if (!pts || !pts.length) return d.rc;
        if (z >= pts[pts.length - 1].z) return pts[pts.length - 1].r;
        var lo = 0, hi = pts.length - 1;
        while (hi - lo > 1) {
            var mid = (lo + hi) >> 1;
            if (pts[mid].z <= z) lo = mid; else hi = mid;
        }
        var span = pts[hi].z - pts[lo].z;
        var f = span > 1e-9 ? (z - pts[lo].z) / span : 0;
        return lerp(pts[lo].r, pts[hi].r, f);
    };

    MotorScene.prototype._applyHeatMap = function () {
        var d = this.dims;
        var on = !!(this.state.heatMap && d.heat);
        var self = this;
        if (!this._heatMat) {
            this._heatMat = new THREE.MeshStandardMaterial({
                vertexColors: true, metalness: 0.25, roughness: 0.55
            });
            this._heatMatCut = new THREE.MeshStandardMaterial({
                vertexColors: true, metalness: 0.05, roughness: 0.95, side: THREE.DoubleSide
            });
        }
        var qT = on ? d.heat.qThroat : 1;
        var qC = on ? Math.min(d.heat.qChamber, qT * 0.9) : 1;
        var lnMin = Math.log(Math.max(qC * 0.6, 1));
        var lnMax = Math.log(Math.max(qT, 2));

        [this.parts.casing, this.parts.nozzle].forEach(function (grp) {
            if (!grp) return;
            grp.traverse(function (o) {
                if (!o.isMesh || o.isSprite) return;
                if (o.userData.hideInCut) return;                  // cıvatalar
                if (o.geometry && o.geometry.type === 'TorusGeometry') return;
                if (!on) {
                    if (o.userData.origMat) o.material = o.userData.origMat;
                    return;
                }
                if (!o.userData.origMat) o.userData.origMat = o.material;
                var pos = o.geometry.attributes.position;
                var colors = new Float32Array(pos.count * 3);
                for (var i = 0; i < pos.count; i++) {
                    var z = pos.getY(i);
                    var r = self._flowRadiusAt(z);
                    // Bartz: q ∝ (A_t/A)^0.9 = (r_t/r)^1.8
                    var q = qT * Math.pow(d.rt / Math.max(r, d.rt), 1.8);
                    var t = (Math.log(Math.max(q, 1)) - lnMin) / Math.max(lnMax - lnMin, 1e-9);
                    var col = heatColor(t);
                    colors[i * 3] = col.r;
                    colors[i * 3 + 1] = col.g;
                    colors[i * 3 + 2] = col.b;
                }
                o.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
                var wasCut = o.userData.origMat && o.userData.origMat.side === THREE.DoubleSide;
                o.material = wasCut ? self._heatMatCut : self._heatMat;
            });
        });
    };

    // Patlatılmış görünüm ofsetleri (f: 0=montajlı, 1=ayrık)
    MotorScene.prototype._applyExplode = function (f) {
        if (!this.parts.casing) return;
        var L = this._totalLen;
        this.parts.casing.position.y = -0.34 * L * f;
        this.parts.injector.position.y = -0.18 * L * f;
        this.parts.liner.position.y = -0.08 * L * f;
        this.parts.grain.position.y = 0.10 * L * f;
        this.parts.nozzle.position.y = 0.30 * L * f;
    };

    // Kesit modunda açıklık bölgesindeki cıvata/orifisleri gizle.
    // Açıklık φ=0 merkezli ±45°: |φ| < π/4 ⇔ cos(φ) > cos(π/4)
    MotorScene.prototype._applyCutVisibility = function () {
        var cut = this.state.cutaway;
        this.assembly.traverse(function (o) {
            if (o.userData && o.userData.hideInCut) {
                if (!cut) { o.visible = true; return; }
                var inGap = Math.cos(o.userData.phi) > Math.cos(CUT_PHI_START) + 1e-6;
                o.visible = !inGap;
            }
        });
    };

    // ------------------------------------------------------------------
    // Egzoz plume: iki katmanlı partikül sistemi + şok elmasları
    // ------------------------------------------------------------------

    MotorScene.prototype._buildPlume = function () {
        var d = this.dims;
        var N = 900;
        this._plumeN = N;
        var geo = new THREE.BufferGeometry();
        var pos = new Float32Array(N * 3);
        var col = new Float32Array(N * 3);
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        this._pState = new Float32Array(N * 5); // vy, vr, phi, life, maxLife

        var mat = new THREE.PointsMaterial({
            size: Math.max(3, d.re * 0.55),
            map: glowTexture('rgba(255,255,255,1)', 'rgba(255,150,60,0.6)'),
            vertexColors: true, transparent: true, depthWrite: false,
            blending: THREE.AdditiveBlending, sizeAttenuation: true
        });
        this._plume = new THREE.Points(geo, mat);
        this._plume.frustumCulled = false;
        this.model.add(this._plume);
        for (var i = 0; i < N; i++) this._resetParticle(i, true);

        // Şok elmasları
        this._diamonds = [];
        var nd = 5;
        for (var k = 0; k < nd; k++) {
            var s = new THREE.Sprite(new THREE.SpriteMaterial({
                map: glowTexture('rgba(220,240,255,1)', 'rgba(90,170,255,0.5)'),
                transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0
            }));
            this.model.add(s);
            this._diamonds.push(s);
        }
        this._updateDiamondPositions();
    };

    // Elmas konum/ölçekleri geometriye bağlı — update() sonrası da çağrılır
    MotorScene.prototype._updateDiamondPositions = function () {
        var d = this.dims;
        for (var k = 0; k < this._diamonds.length; k++) {
            this._diamonds[k].position.set(0, this._nozzleInfo.zExit + d.de * (0.9 + k * 1.25), 0);
            this._diamonds[k].scale.setScalar(d.re * (1.5 - k * 0.18));
        }
    };

    MotorScene.prototype._resetParticle = function (i, scatter) {
        var d = this.dims;
        var st = this._pState;
        var pos = (this._plume && this._plume.geometry)
            ? this._plume.geometry.attributes.position.array : null;
        var rSpawn = d.re * 0.75 * Math.sqrt(Math.random());
        var phi = Math.random() * TAU;
        var speed = this._totalLen * (2.2 + Math.random() * 1.6); // mm/s ölçekli
        st[i * 5 + 0] = speed;
        st[i * 5 + 1] = speed * (0.05 + 0.10 * Math.random()); // radyal saçılım
        st[i * 5 + 2] = phi;
        var maxLife = 0.35 + Math.random() * 0.5;
        st[i * 5 + 3] = scatter ? Math.random() * maxLife : 0;
        st[i * 5 + 4] = maxLife;
        if (pos) {
            pos[i * 3 + 0] = rSpawn * Math.sin(phi);
            pos[i * 3 + 1] = this._nozzleInfo.zExit - 2;
            pos[i * 3 + 2] = rSpawn * Math.cos(phi);
        }
    };

    MotorScene.prototype._updatePlume = function (dt, intensity) {
        if (!this._plume) return;
        var geo = this._plume.geometry;
        var pos = geo.attributes.position.array;
        var col = geo.attributes.color.array;
        var st = this._pState;
        var zExit = this._nozzleInfo.zExit;
        var active = Math.floor(this._plumeN * clamp(intensity, 0, 1));
        for (var i = 0; i < this._plumeN; i++) {
            var o5 = i * 5, o3 = i * 3;
            if (i >= active) { col[o3] = col[o3 + 1] = col[o3 + 2] = 0; continue; }
            st[o5 + 3] += dt;
            if (st[o5 + 3] >= st[o5 + 4]) {
                this._resetParticle(i, false);
                pos[o3 + 0] = 0; pos[o3 + 1] = zExit - 2; pos[o3 + 2] = 0;
                var rs = this.dims.re * 0.7 * Math.sqrt(Math.random());
                pos[o3 + 0] = rs * Math.sin(st[o5 + 2]);
                pos[o3 + 2] = rs * Math.cos(st[o5 + 2]);
            }
            var f = st[o5 + 3] / st[o5 + 4]; // 0..1 yaşam oranı
            pos[o3 + 1] += st[o5 + 0] * dt;
            var vr = st[o5 + 1] * dt * (0.4 + f * 1.6);
            pos[o3 + 0] += Math.sin(st[o5 + 2]) * vr;
            pos[o3 + 2] += Math.cos(st[o5 + 2]) * vr;
            // Renk yaşam eğrisi: beyaz-mavi çekirdek → turuncu → söner
            var fade = (1 - f) * (1 - f) * intensity;
            if (f < 0.18) {
                col[o3] = 1.0 * fade; col[o3 + 1] = 1.0 * fade; col[o3 + 2] = 1.05 * fade;
            } else if (f < 0.5) {
                col[o3] = 1.0 * fade; col[o3 + 1] = 0.62 * fade; col[o3 + 2] = 0.22 * fade;
            } else {
                col[o3] = 0.85 * fade; col[o3 + 1] = 0.32 * fade; col[o3 + 2] = 0.08 * fade;
            }
        }
        geo.attributes.position.needsUpdate = true;
        geo.attributes.color.needsUpdate = true;

        for (var k = 0; k < this._diamonds.length; k++) {
            var flick = 0.75 + 0.25 * Math.sin(this._clock.elapsedTime * 37 + k * 2.4);
            this._diamonds[k].material.opacity = intensity * (0.75 - k * 0.12) * flick;
        }
    };

    // ------------------------------------------------------------------
    // Ölçü etiketleri
    // ------------------------------------------------------------------

    MotorScene.prototype._buildLabels = function () {
        var d = this.dims;
        if (this._labelGroup) {
            this.model.remove(this._labelGroup);
            // Etiket kanvas dokuları + materyalleri + leader geometrileri
            // yeniden kurulumda dispose edilir (hakem bulgusu H1)
            this._labelGroup.traverse(function (o) {
                if (o.geometry && !o.isSprite) o.geometry.dispose();
                if (o.material) {
                    if (o.material.map) o.material.map.dispose();
                    o.material.dispose();
                }
            });
        }
        var g = this._labelGroup = new THREE.Group();
        var lineMat = new THREE.LineBasicMaterial({
            color: 0x39d6ec, transparent: true, opacity: 0.75, depthTest: false
        });
        var scaleBase = this._totalLen * 0.055;

        // Etiketler açıklığın karşısında (lathe -X ⇒ dünya +Y, üstte) durur
        function callout(zPos, rFrom, text, extra) {
            var off = rFrom + (extra || scaleBase * 0.9);
            var pts = [
                new THREE.Vector3(-rFrom, zPos, 0),
                new THREE.Vector3(-off - scaleBase * 0.35, zPos, 0)
            ];
            g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
            var sp = textSprite(text);
            var hgt = scaleBase * 0.62;
            sp.scale.set(hgt * sp.userData.aspect, hgt, 1);
            sp.position.set(-off - scaleBase * 0.4 - (hgt * sp.userData.aspect) / 2, zPos, 0);
            g.add(sp);
        }

        callout(d.Lch * 0.30, d.rcOut, 'ØC ' + d.Dch.toFixed(1) + ' mm');
        callout(d.Lch + d.Lc, d.rt + 2, 'ØT ' + d.dt.toFixed(1) + ' mm', scaleBase * 1.5);
        callout(this._nozzleInfo.zExit - 2, this._nozzleInfo.rExit + d.nozzleWall, 'ØE ' + d.de.toFixed(1) + ' mm');

        // Toplam uzunluk = kapak dışı → nozul çıkışı (2D kesitle aynı tanım;
        // oksitleyici giriş borusu hariç)
        var totalTxt = textSprite('L ' + (this._nozzleInfo.zExit + d.capT).toFixed(0) + ' mm  •  GRAIN ' + d.Lg.toFixed(0) + ' mm',
            { border: 'rgba(255,150,60,0.55)', color: '#ffd9a8' });
        var th = scaleBase * 0.62;
        totalTxt.scale.set(th * totalTxt.userData.aspect, th, 1);
        totalTxt.position.set((d.rcOut + d.flangeLip) * 1.55, this._zCenter, 0);
        g.add(totalTxt);

        g.visible = this.state.labels;
        this.model.add(g);
    };

    // ------------------------------------------------------------------
    // Kamera / yerleşim
    // ------------------------------------------------------------------

    MotorScene.prototype._fitCamera = function () {
        var L = this._totalLen;
        var R = this.dims.rcOut + this.dims.flangeLip;
        var dist = Math.max(L * 1.15, R * 6);
        this._camHome = new THREE.Vector3(L * 0.22, L * 0.30, dist);
        this.camera.position.copy(this._camHome).multiplyScalar(1.5); // intro dolly başlangıcı
        this.controls.target.set(0, 0, 0);
        this._keyLight.position.set(L * 0.8, L * 1.1, L * 0.7);
        var sc = this._keyLight.shadow.camera;
        sc.left = -L; sc.right = L; sc.top = L; sc.bottom = -L; sc.far = L * 6;
        this._keyLight.shadow.camera.updateProjectionMatrix();
        this._rimCyan.position.set(-L * 0.9, L * 0.25, -L * 0.9);
        this._rimOrange.position.set(L * 1.0, -L * 0.35, -L * 0.7);
        this.camera.far = dist * 30;
        this.camera.updateProjectionMatrix();
    };

    MotorScene.prototype._bindResize = function () {
        var self = this;
        this._ro = new ResizeObserver(function () {
            if (self._disposed) return;
            var w = self.container.clientWidth, h = self.container.clientHeight;
            if (w < 10 || h < 10) return;
            self.camera.aspect = w / h;
            self.camera.updateProjectionMatrix();
            self.renderer.setSize(w, h);
        });
        this._ro.observe(this.container);
    };

    // ------------------------------------------------------------------
    // Ana döngü
    // ------------------------------------------------------------------

    MotorScene.prototype._tick = function () {
        var dt = Math.min(this._clock.getDelta(), 0.05);
        var d = this.dims;
        var st = this.state;

        // Giriş dolly animasyonu
        if (this._introT < 1) {
            this._introT = Math.min(1, this._introT + dt / 1.4);
            var e = 1 - Math.pow(1 - this._introT, 3);
            this.camera.position.copy(this._camHome).multiplyScalar(lerp(1.5, 1.0, e));
        }

        // Simülasyon zamanı
        if (st.playing) {
            st.time += dt * st.speed;
            if (st.time >= d.burnTime) { st.time = d.burnTime; st.playing = false; }
        }
        var burning = st.playing && st.time < d.burnTime;
        var throttle = burning ? 1 : 0;

        // Port regresyonu
        var rP = portRadiusAt(d, st.time);
        this._rebuildGrain(rP, false);
        if (Math.abs(rP - (this._glowR || 0)) > 0.25) {
            this._glowR = rP;
            this._rebuildGlow(rP);
        }

        // Yanma ışıkları + parıltı
        var flick = 0.82 + 0.18 * Math.sin(this._clock.elapsedTime * 31) * Math.sin(this._clock.elapsedTime * 17.3);
        this._glowMat.opacity = throttle * 0.5 * flick;
        this._throatFlame.material.opacity = throttle * 0.85 * flick;
        var Lw = this._totalLen;
        this._combLight.intensity = throttle * 1.4 * flick;
        this._combLight.distance = Lw * 1.6;
        this._exitLight.intensity = throttle * 1.8 * flick;
        this._exitLight.distance = Lw * 2.2;
        // Işık konumları (dünya): model merkezine göre
        var zComb = (d.zg0 + d.zg1) / 2 - this._zCenter;
        var zExitW = this._nozzleInfo.zExit - this._zCenter;
        this._combLight.position.set(zComb, 0, 0);
        this._exitLight.position.set(zExitW + d.de, 0, 0);

        // Plume: yalnız aktif yanmada görünür (duraklatınca söner)
        if (this._plume) {
            this._plume.visible = st.plume && throttle > 0.01;
            if (this._plume.visible) this._updatePlume(dt, throttle);
            else this._diamonds.forEach(function (s) { s.material.opacity = 0; });
        }

        // Patlatılmış görünüm geçişi
        var target = st.exploded ? 1 : 0;
        if (Math.abs(this._explodeF - target) > 0.001) {
            this._explodeF += (target - this._explodeF) * Math.min(1, dt * 5);
            this._applyExplode(this._explodeF);
        }

        this.controls.autoRotate = st.autoRotate;
        this.controls.update();
        this.renderer.render(this.scene, this.camera);

        // HUD kancası
        if (this.hooks.onTick) {
            var ofNow = null, ispNow = null;
            if (d.ofShift && d.ofShift.time) {
                ofNow = sampleSeries(d.ofShift.time, d.ofShift.of_ratio, st.time);
                ispNow = sampleSeries(d.ofShift.time, d.ofShift.isp, st.time);
            }
            this.hooks.onTick({
                time: st.time,
                burnTime: d.burnTime,
                playing: st.playing,
                speed: st.speed,
                portDiameter: rP * 2,
                webRemaining: clamp((d.rGrainOut - rP) / Math.max(d.rGrainOut - d.rPort0, 1e-6), 0, 1),
                of: ofNow !== null ? ofNow : d.of0,
                isp: ispNow !== null ? ispNow : d.isp,
                thrust: st.time < d.burnTime ? d.thrust : 0,
                burning: burning
            });
        }
    };

    // ------------------------------------------------------------------
    // Kontroller
    // ------------------------------------------------------------------

    MotorScene.prototype.setCutaway = function (on) {
        this.state.cutaway = !!on;
        this._lastPortR = -1;
        this._buildMotor();
        this._buildLabels();
    };
    // Port kesit şekli: circular | star | multiport | finocyl
    // (görsel gösterim — balistik, alan-eşdeğer dairesel portla çözülür)
    MotorScene.prototype.setPortShape = function (shape) {
        this.state.portShape = shape || 'circular';
        this._lastPortR = -1;
        this._rebuildGrain(portRadiusAt(this.dims, this.state.time), true);
        this._glowR = -1;
        this._rebuildGlow(portRadiusAt(this.dims, this.state.time));
        return this.state.portShape;
    };
    MotorScene.prototype.cyclePortShape = function () {
        var opts = ['circular', 'star', 'multiport', 'finocyl'];
        var i = opts.indexOf(this.state.portShape);
        return this.setPortShape(opts[(i + 1) % opts.length]);
    };
    MotorScene.prototype.setHeatMap = function (on) {
        this.state.heatMap = !!on;
        this._applyHeatMap();
        return this.state.heatMap;
    };
    MotorScene.prototype.getHeatInfo = function () { return this.dims.heat; };

    // Canlı tasarım modu: yeni motor sözlüğüyle sahneyi yerinde güncelle
    // (renderer/kamera korunur; boyut belirgin değiştiyse kamera yeniden oturur)
    MotorScene.prototype.update = function (motorData) {
        var oldLen = this._totalLen || 1;
        this.dims = extractDims(motorData);
        this.state.time = clamp(this.state.time, 0, this.dims.burnTime);
        this._lastPortR = -1;
        this._buildMotor();
        this._buildLabels();
        if (this._plume) {
            this._updateDiamondPositions();
            this._plume.material.size = Math.max(3, this.dims.re * 0.55);
            for (var i = 0; i < this._plumeN; i++) this._resetParticle(i, true);
        }
        if (Math.abs(this._totalLen - oldLen) / oldLen > 0.15) {
            this._fitCamera();
            this._introT = 1;
            this.camera.position.copy(this._camHome);
        }
    };
    MotorScene.prototype.setLabels = function (on) {
        this.state.labels = !!on;
        if (this._labelGroup) this._labelGroup.visible = this.state.labels;
    };
    MotorScene.prototype.setPlume = function (on) { this.state.plume = !!on; };
    MotorScene.prototype.setExploded = function (on) { this.state.exploded = !!on; };
    MotorScene.prototype.setAutoRotate = function (on) { this.state.autoRotate = !!on; };
    MotorScene.prototype.play = function () {
        if (this.state.time >= this.dims.burnTime - 1e-3) this.state.time = 0;
        this.state.playing = true;
    };
    MotorScene.prototype.pause = function () { this.state.playing = false; };
    MotorScene.prototype.setTime = function (t) {
        this.state.time = clamp(t, 0, this.dims.burnTime);
    };
    MotorScene.prototype.cycleSpeed = function () {
        var opts = [0.5, 1, 2, 4];
        var i = opts.indexOf(this.state.speed);
        this.state.speed = opts[(i + 1) % opts.length];
        return this.state.speed;
    };
    MotorScene.prototype.resetCamera = function () {
        this.camera.position.copy(this._camHome);
        this.controls.target.set(0, 0, 0);
        this._introT = 1;
    };
    MotorScene.prototype.dispose = function () {
        this._disposed = true;
        if (this._raf) cancelAnimationFrame(this._raf);
        if (this._ro) this._ro.disconnect();
        var self = this;
        this.scene.traverse(function (o) {
            if (o.geometry) o.geometry.dispose();
            if (o.material) {
                (Array.isArray(o.material) ? o.material : [o.material]).forEach(function (m) {
                    if (m.map) m.map.dispose();
                    m.dispose();
                });
            }
        });
        this.renderer.dispose();
        if (this.renderer.domElement.parentNode === this.container) {
            this.container.removeChild(this.renderer.domElement);
        }
    };

    // ------------------------------------------------------------------
    // Dışa açık API
    // ------------------------------------------------------------------

    window.MotorViz3D = {
        isSupported: function () {
            if (typeof THREE === 'undefined' || !THREE.OrbitControls) return false;
            try {
                var c = document.createElement('canvas');
                return !!(window.WebGLRenderingContext &&
                    (c.getContext('webgl') || c.getContext('experimental-webgl')));
            } catch (e) { return false; }
        },
        mount: function (containerId, motorData, hooks) {
            var el = document.getElementById(containerId);
            if (!el) return null;
            if (viz) { viz.dispose(); viz = null; }
            el.innerHTML = '';
            viz = new MotorScene(el, motorData, hooks);
            return viz;
        },
        // Tasarım modu: mevcut sahneyi yeni geometriyle yerinde güncelle
        update: function (motorData) {
            if (viz) viz.update(motorData);
            return viz;
        },
        get: function () { return viz; },
        dispose: function () { if (viz) { viz.dispose(); viz = null; } }
    };
})();
