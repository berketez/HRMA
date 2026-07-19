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

    // Fırçalanmış metal dokusu: çevresel taşlama izleri (LatheGeometry
    // UV'sinde u=çevre, v=profil → satır bazlı parlaklık gürültüsü çevresel
    // çizgi üretir). bumpMap + roughnessMap olarak paylaşılır.
    function brushedTexture() {
        var c = makeCanvas(64, 256);
        var g = c.getContext('2d');
        for (var y = 0; y < 256; y++) {
            // Düşük kontrast: sert çizgiler kapak yüzeyinde iç parıltıyı
            // aynalayıp altın halka artefaktı üretiyordu (2026-07-13)
            var v = 195 + Math.floor(Math.random() * 35);
            g.fillStyle = 'rgb(' + v + ',' + v + ',' + v + ')';
            g.fillRect(0, y, 64, 1);
        }
        var tex = new THREE.CanvasTexture(c);
        tex.wrapS = THREE.RepeatWrapping;
        tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(1, 3);
        return tex;
    }

    // Kesit-uyumlu halka (O-ring / snap ring): cutaway modunda 270° yay,
    // açıklığı lathe kesit boşluğuyla (φ=0 merkezli ±45°) hizalanır.
    // Torus θ→lathe φ eşlemesi: φ = 90°−θ (rotateX(π/2) sonrası);
    // rotateZ(−225°) ile çizilen yay φ∈[45°,315°] bandına oturur.
    function ringGeo(R, tube, radialSeg, tubularSeg, cutaway) {
        var arc = cutaway ? CUT_PHI_LENGTH : TAU;
        var geo = new THREE.TorusGeometry(R, tube, radialSeg, tubularSeg, arc);
        if (cutaway) geo.rotateZ(THREE.MathUtils.degToRad(-225));
        geo.rotateX(Math.PI / 2);
        return geo;
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

    // Enjektör tipi takma adları — visualization.py INJECTOR_TYPE_ALIASES ile
    // aynı eşleme (tek gerçeklik: 2D kesit ve 3D model aynı tipi çizer)
    var INJECTOR_TYPE_ALIASES = {
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

    function resolveInjectorType(inj) {
        var raw = (inj && (inj.injector_type || inj.type)) || 'showerhead';
        return INJECTOR_TYPE_ALIASES[String(raw).toLowerCase()] || 'showerhead';
    }

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
            // Enjektör tipi 2D kesitle AYNI takma ad tablosundan çözülür
            injectorType: resolveInjectorType(inj),
            pintleR: clamp(num(inj.pintle_diameter_mm, num(inj.d_pintle_mm, 0.22 * Dch)) / 2,
                2, 0.45 * rc),
            annulusGap: clamp(num(inj.annulus_gap_mm, 1.2), 0.4, 6),
            innerJetR: clamp(num(inj.inner_jet_diameter, 0.18 * Dch) / 2, 1.5, 0.35 * rc),
            impingeHalfDeg: clamp(num(inj.impingement_angle_deg, 60) / 2, 10, 60),
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

    // Nozul katı poligonu: iç kontur + duvar ofsetli dış yol + montaj flanşı.
    // Boğaz bölgesinde gövde iç yüzeyi grafit insert kalınlığı kadar dışa
    // ötelenir; insert ayrı katı olarak döner (gerçek motor mimarisi:
    // grafit boğaz insert'i + metal tutucu gövde).
    function nozzleProfile(dims) {
        var inner = nozzleInnerContour(dims);
        var zEnd = inner[inner.length - 1].z;
        var flangeR = dims.rcOut + dims.flangeLip;
        var flangeZ1 = dims.Lch + dims.flangeT;

        // İnsert aralığı: konverjanın ortasından diverjanın ilk çeyreğine
        var tIns = clamp(0.35 * dims.rt, 2.5, 10);
        var zt = dims.Lch + dims.Lc;
        var zA = dims.Lch + 0.45 * dims.Lc;
        var zB = zt + 0.28 * dims.Ld;
        var ramp = Math.max(2, 0.08 * (zB - zA)); // uçlarda yumuşak geçiş
        function insOffset(z) {
            if (z <= zA || z >= zB) return 0;
            var fIn = clamp((z - zA) / ramp, 0, 1);
            var fOut = clamp((zB - z) / ramp, 0, 1);
            return tIns * Math.min(fIn, fOut);
        }

        var poly = [];
        // iç yüzey (öne doğru) — insert bölgesinde dışa ofsetli
        inner.forEach(function (p) { poly.push({ r: p.r + insOffset(p.z), z: p.z }); });
        // çıkış dudağı
        poly.push({ r: inner[inner.length - 1].r + dims.nozzleWall, z: zEnd });
        // dış yüzey (geriye doğru, duvar ofseti + flanş bölgesi)
        for (var i = inner.length - 1; i >= 0; i--) {
            var p = inner[i];
            var rOut = p.r + dims.nozzleWall;
            if (p.z <= flangeZ1) rOut = Math.max(rOut, flangeR);
            poly.push({ r: rOut, z: p.z });
        }

        // Grafit insert katısı: gerçek akış konturu ile ofsetli gövde arası
        var span = inner.filter(function (p) { return p.z >= zA && p.z <= zB; });
        var insertPoly = null;
        if (span.length >= 3) {
            insertPoly = [];
            span.forEach(function (p) { insertPoly.push({ r: p.r, z: p.z }); });
            for (var k = span.length - 1; k >= 0; k--) {
                var q = span[k];
                insertPoly.push({ r: q.r + Math.max(insOffset(q.z), 0.6), z: q.z });
            }
        }
        return { poly: poly, zExit: zEnd, rExit: inner[inner.length - 1].r,
                 flangeR: flangeR, inner: inner, insertPoly: insertPoly };
    }

    // ------------------------------------------------------------------
    // Ana görselleştirici
    // ------------------------------------------------------------------

    var viz = null; // tek aktif örnek

    function createMaterials() {
        var brushed = brushedTexture();
        return {
            // Fırçalanmış alüminyum kasa: çevresel taşlama izi bump+roughness
            casing: new THREE.MeshStandardMaterial({
                color: 0x9fabbc, metalness: 0.72, roughness: 0.42,
                bumpMap: brushed, bumpScale: 0.12, roughnessMap: brushed
            }),
            casingCut: new THREE.MeshStandardMaterial({ color: 0xc3ccd8, metalness: 0.15, roughness: 0.9, side: THREE.DoubleSide }),
            nozzle: new THREE.MeshStandardMaterial({ color: 0x525c68, metalness: 0.78, roughness: 0.38 }),
            nozzleCut: new THREE.MeshStandardMaterial({ color: 0x76818f, metalness: 0.1, roughness: 0.95, side: THREE.DoubleSide }),
            // Grafit boğaz insert'i: koyu, mat, hafif yansımalı
            graphite: new THREE.MeshStandardMaterial({ color: 0x23262a, metalness: 0.42, roughness: 0.78 }),
            graphiteCut: new THREE.MeshStandardMaterial({ color: 0x393e45, metalness: 0.1, roughness: 0.95, side: THREE.DoubleSide }),
            grain: new THREE.MeshStandardMaterial({ color: 0x6d4326, metalness: 0.0, roughness: 0.94 }),
            grainCut: new THREE.MeshStandardMaterial({ color: 0x936243, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            liner: new THREE.MeshStandardMaterial({ color: 0x23282e, metalness: 0.05, roughness: 0.9 }),
            linerCut: new THREE.MeshStandardMaterial({ color: 0x3a4046, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            injector: new THREE.MeshStandardMaterial({ color: 0xb08d57, metalness: 0.85, roughness: 0.38 }),
            injectorCut: new THREE.MeshStandardMaterial({ color: 0xd2b184, metalness: 0.2, roughness: 0.85, side: THREE.DoubleSide }),
            bolt: new THREE.MeshStandardMaterial({ color: 0x343b44, metalness: 0.85, roughness: 0.4 }),
            steel: new THREE.MeshStandardMaterial({ color: 0x6f7883, metalness: 0.9, roughness: 0.32 }),
            // O-ring elastomeri: tam mat, simsiyah
            oring: new THREE.MeshStandardMaterial({ color: 0x121417, metalness: 0.0, roughness: 0.97 }),
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
        // 0.15: 0.4'te metal kapak yüzeyi turuncuyu aynalayıp altın görünüyordu
        this._rimOrange = new THREE.PointLight(0xff7a1a, 0.15, 0, 2);
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

        var isLiquid = d.motorType === 'liquid';
        var isSolid = d.motorType === 'solid';

        // Detay segment sayıları: perf modunda düşürülür
        var segR = this._perfMode ? 8 : 12;    // torus kesit segmenti
        var segC = this._perfMode ? 24 : 48;   // torus çevre segmenti

        // O-ring boyutu ve yiv yardımcısı: rOut duvarında zList merkezli
        // kare yivler açan (r,z) nokta dizisi üretir (z artan yönde)
        var orr = clamp(0.16 * d.capT, 1.2, 3);   // O-ring kesit yarıçapı
        function wallWithGrooves(rOut, z0, z1, zList, gw, gd) {
            var pts = [{ r: rOut, z: z0 }];
            zList.forEach(function (zc) {
                pts.push({ r: rOut, z: zc - gw });
                pts.push({ r: rOut - gd, z: zc - gw });
                pts.push({ r: rOut - gd, z: zc + gw });
                pts.push({ r: rOut, z: zc + gw });
            });
            pts.push({ r: rOut, z: z1 });
            return pts;
        }
        function addORing(parent, R, zPos, tube) {
            var ring = new THREE.Mesh(ringGeo(R, tube || orr, segR, segC, cut), mats.oring);
            ring.position.y = zPos;
            parent.add(ring);
            return ring;
        }
        // Dış parting-line halkası (işlenmiş parça birleşim izi — tam çember)
        function addJointLine(parent, zPos) {
            var jr = new THREE.Mesh(
                new THREE.TorusGeometry(d.rcOut + 0.25, 0.5, 6, segC), mats.bolt);
            jr.rotation.x = Math.PI / 2;
            jr.position.y = zPos;
            parent.add(jr);
        }

        // --- Gövde tüpü (kapak artık AYRI parça — gerçek motor mimarisi) ---
        // Katıda tüp öne uzar: kapak tüpün içinde, snap-ring ile tutulur
        var tubeZ0 = isSolid ? -d.capT - 4 : 0;
        var casingPoly = [
            { r: d.rc, z: tubeZ0 },
            { r: d.rcOut, z: tubeZ0 },
            { r: d.rcOut, z: d.Lch },
            { r: d.rc, z: d.Lch }
        ];
        var casing = buildSolid(casingPoly, mats.casing, mats.casingCut, cut);
        this.parts.casing = casing;

        // --- Ön kapak (forward closure): O-ring yivli, cıvatalı/snap-ring'li ---
        var closure = new THREE.Group();
        if (isSolid) {
            // Tüp içine oturan kapak: OD üzerinde 2 O-ring yivi + önünde
            // tüp iç yüzeyine oturan snap ring (segman)
            var cOD = d.rc - 0.15;
            var zO1 = -0.65 * d.capT, zO2 = -0.3 * d.capT;
            // Yiv yarı genişliği aralığa oranla sınırlı: dar kapakta
            // yivlerin çakışıp poligonu kendine kesmesini önler
            var gwS = Math.min(orr * 0.9, 0.15 * d.capT);
            var closPoly = [{ r: 0, z: -d.capT }]
                .concat(wallWithGrooves(cOD, -d.capT, 0, [zO1, zO2], gwS, orr * 0.7))
                .concat([{ r: 0, z: 0 }]);
            closure.add(buildSolid(closPoly, mats.casing, mats.casingCut, cut));
            addORing(closure, cOD - orr * 0.7 + orr * 0.55, zO1);
            addORing(closure, cOD - orr * 0.7 + orr * 0.55, zO2);
            // Snap ring: kapağın önünde, tüp ID yivinde
            var snap = new THREE.Mesh(
                ringGeo(d.rc - 0.6, clamp(0.12 * d.capT, 1, 2.4), 4, segC, cut),
                mats.steel);
            snap.position.y = -d.capT - 2;
            closure.add(snap);
        } else {
            // Hibrit/sıvı: flanşlı kapak + tüp içine giren spigot (2 O-ring
            // yivli) + tüp alın yüzeyine cıvata çemberi
            var spigR = d.rc - 0.25;
            var sg = clamp(0.55 * d.capT, 5, 20);
            var zg1 = 0.32 * sg, zg2 = 0.72 * sg;
            // Yiv yarı genişliği spigot boyuna oranla sınırlı (çakışma önlemi)
            var gwH = Math.min(orr * 0.9, 0.16 * sg);
            var closPoly2 = [
                { r: 0, z: -d.capT },
                { r: d.rcOut, z: -d.capT },
                { r: d.rcOut, z: 0 }
            ].concat(wallWithGrooves(spigR, 0, sg, [zg1, zg2], gwH, orr * 0.7))
             .concat([{ r: 0, z: sg }]);
            closure.add(buildSolid(closPoly2, mats.casing, mats.casingCut, cut));
            addORing(closure, spigR - orr * 0.7 + orr * 0.55, zg1);
            addORing(closure, spigR - orr * 0.7 + orr * 0.55, zg2);
            // Cıvata çemberi: kapak ön yüzünden tüp alın yüzeyine (M4-M6 görünüm)
            var cbR = clamp(0.3 * d.casingWall, 1.6, 4);
            var cbH = clamp(0.5 * d.capT, 4, 12);
            var cbGeo = new THREE.CylinderGeometry(cbR, cbR, cbH, 6);
            var cbCircle = (d.rc + d.rcOut) / 2;
            for (var cb = 0; cb < d.nBolts; cb++) {
                var cphi = ((cb + 0.5) / d.nBolts) * TAU;
                var cbolt = new THREE.Mesh(cbGeo, mats.bolt);
                cbolt.position.set(cbCircle * Math.sin(cphi), -d.capT - cbH * 0.45,
                    cbCircle * Math.cos(cphi));
                cbolt.userData.phi = cphi;
                cbolt.userData.hideInCut = true;
                cbolt.castShadow = true;
                closure.add(cbolt);
            }
            addJointLine(closure, 0.4); // kapak-tüp birleşim izi
        }
        this.parts.closure = closure;

        // Oksitleyici/yakıt giriş borusu + rakor (katıda yok — kapalı kapak)
        if (!isSolid) {
            var inletPoly = [
                { r: 0, z: -d.capT - d.inletL },
                { r: d.inletR, z: -d.capT - d.inletL },
                { r: d.inletR, z: -d.capT + 1 },
                { r: 0, z: -d.capT + 1 }
            ];
            closure.add(buildSolid(inletPoly, mats.casing, null, false));
            var collar = new THREE.Mesh(
                new THREE.TorusGeometry(d.inletR + 1.5, 2.2, segR, segC),
                mats.bolt
            );
            collar.rotation.x = Math.PI / 2;
            collar.position.y = -d.capT - d.inletL * 0.55;
            closure.add(collar);
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

        // --- Enjektör plakası + showerhead orifis deseni (katı motorda yok) ---
        if (!isSolid) {
            // Plaka, kapak spigot'unun hemen arkasına oturur (manifold
            // hacmi = spigot yüzü ile plaka arasındaki boşluk)
            var injZ0 = sg + 2;
            var injT = clamp(0.9 * d.capT, 6, 24);
            if (!isLiquid) {
                // Hibritte plaka grain başlangıcına taşmasın
                injT = Math.max(4, Math.min(injT, d.zg0 - injZ0 - 1));
            }
            var injPoly = [
                { r: 0, z: injZ0 },
                { r: d.rc - 0.4, z: injZ0 },
                { r: d.rc - 0.4, z: injZ0 + injT },
                { r: 0, z: injZ0 + injT }
            ];
            var injector = buildSolid(injPoly, mats.injector, mats.injectorCut, cut);
            // Enjektör tipine göre yüz geometrisi (2D kesitle aynı tip)
            var injFace = injZ0 + injT;
            var seg = this._perfMode ? 8 : 12;
            var oriR = Math.max(d.orificeR * 1.6, 1.2);
            var rMaxO = d.rc - 6;

            if (d.injectorType === 'pintle') {
                // Merkez pintle gövdesi: plakadan odaya uzanan silindir
                var pR = clamp(d.pintleR, 2, 0.45 * d.rc);
                var pLen = Math.max(2.5 * pR, 1.2 * injT);
                var post = new THREE.Mesh(
                    new THREE.CylinderGeometry(pR, pR * 0.92, pLen, this._perfMode ? 12 : 24),
                    mats.injector);
                post.position.y = injFace + pLen / 2;
                post.castShadow = true;
                injector.add(post);
                // Uçta radyal delik dizisi (yatık silindirler)
                var nRad = Math.max(6, Math.min(d.nOrifices, 24));
                var radGeo = new THREE.CylinderGeometry(oriR * 0.8, oriR * 0.8,
                    pR * 0.9, this._perfMode ? 6 : 10);
                for (var rk = 0; rk < nRad; rk++) {
                    var rphi = (rk / nRad) * TAU;
                    var rad = new THREE.Mesh(radGeo, mats.orifice);
                    rad.rotation.z = Math.PI / 2;
                    rad.rotation.y = -rphi;
                    rad.position.set(pR * 0.75 * Math.sin(rphi),
                        injFace + pLen * 0.82, pR * 0.75 * Math.cos(rphi));
                    rad.userData.phi = rphi;
                    rad.userData.hideInCut = true;
                    injector.add(rad);
                }
                // Anülüs bileziği (pintle çevresindeki eksenel oks tabakası)
                var annGap = clamp(d.annulusGap, 0.4, 6);
                var ann = new THREE.Mesh(
                    new THREE.TorusGeometry(pR + annGap, Math.max(annGap * 0.5, 0.5),
                        8, this._perfMode ? 24 : 48),
                    mats.orifice);
                ann.rotation.x = Math.PI / 2;
                ann.position.y = injFace + 0.8;
                ann.userData.hideInCut = true;
                injector.add(ann);

            } else if (d.injectorType === 'swirl') {
                // Teğetsel kanal blokları: plaka yüzünde eğik kutular
                var nSlot = Math.max(4, Math.min(d.nOrifices, 12));
                var slotGeo = new THREE.BoxGeometry(Math.max(oriR * 1.4, 1.6),
                    Math.max(injT * 0.5, 2), rMaxO * 0.45);
                for (var sk = 0; sk < nSlot; sk++) {
                    var sphi = (sk / nSlot) * TAU;
                    var slot = new THREE.Mesh(slotGeo, mats.orifice);
                    var sr = rMaxO * 0.62;
                    slot.position.set(sr * Math.sin(sphi), injFace + 0.4,
                        sr * Math.cos(sphi));
                    // Teğetsel yönelim: radyal yönden 90 derece kaydırılmış
                    slot.rotation.y = -sphi + Math.PI / 2;
                    slot.userData.phi = sphi;
                    slot.userData.hideInCut = true;
                    injector.add(slot);
                }
                // Merkezi çıkış orifisi (içi boş koni sprey kaynağı)
                var exitR = Math.max(oriR * 2.2, 0.12 * d.rc);
                var exitO = new THREE.Mesh(
                    new THREE.CylinderGeometry(exitR, exitR, 1.8, this._perfMode ? 12 : 24),
                    mats.orifice);
                exitO.position.y = injFace + 0.6;
                exitO.userData.hideInCut = true;
                injector.add(exitO);

            } else if (d.injectorType === 'impingement') {
                // Açılı delik çiftleri: her çift eksene doğru eğik iki silindir
                var nPair = Math.max(3, Math.min(Math.round(d.nOrifices / 2), 12));
                var tilt = THREE.MathUtils.degToRad(clamp(d.impingeHalfDeg, 10, 60));
                var impGeo = new THREE.CylinderGeometry(oriR, oriR, injT * 0.9,
                    this._perfMode ? 6 : 10);
                for (var pk = 0; pk < nPair; pk++) {
                    var pphi = (pk / nPair) * TAU;
                    var pr = rMaxO * 0.68;
                    for (var side = -1; side <= 1; side += 2) {
                        var hole = new THREE.Mesh(impGeo, mats.orifice);
                        hole.position.set(pr * Math.sin(pphi), injFace - injT * 0.35,
                            pr * Math.cos(pphi));
                        hole.translateX(side * oriR * 1.8);
                        hole.rotation.z = -side * tilt;
                        hole.userData.phi = pphi;
                        hole.userData.hideInCut = true;
                        injector.add(hole);
                    }
                }

            } else if (d.injectorType === 'coaxial') {
                // İç boru + dış halka (tek akışkan hibritte her ikisi de oks)
                var iR = clamp(d.innerJetR, 1.5, 0.35 * d.rc);
                var coLen = Math.max(2 * iR, injT);
                var innerTube = new THREE.Mesh(
                    new THREE.CylinderGeometry(iR, iR, coLen, this._perfMode ? 12 : 24),
                    mats.orifice);
                innerTube.position.y = injFace + coLen / 2;
                innerTube.userData.hideInCut = true;
                injector.add(innerTube);
                var outerRing = new THREE.Mesh(
                    new THREE.TorusGeometry(iR + clamp(d.annulusGap, 0.4, 6) + 0.6,
                        Math.max(clamp(d.annulusGap, 0.4, 6) * 0.5, 0.6),
                        8, this._perfMode ? 24 : 48),
                    mats.injector);
                outerRing.rotation.x = Math.PI / 2;
                outerRing.position.y = injFace + coLen * 0.35;
                outerRing.userData.hideInCut = true;
                injector.add(outerRing);

            } else {
                // Showerhead: eş merkezli 2-3 delik halkası (çevreyle orantılı dağıtım)
                var oriGeo = new THREE.CylinderGeometry(oriR, oriR, 1.6, seg);
                var ringFr = d.nOrifices >= 10 ? [0.35, 0.6, 0.85] : [0.4, 0.75];
                var frSum = ringFr.reduce(function (a, b) { return a + b; }, 0);
                ringFr.forEach(function (fr, ri) {
                    var rr = fr * rMaxO;
                    var nRing = Math.max(3, Math.round(d.nOrifices * fr / frSum));
                    for (var k = 0; k < nRing; k++) {
                        var phi = ((k + ri * 0.5) / nRing) * TAU; // halkalar arası kaydırma
                        var ori = new THREE.Mesh(oriGeo, mats.orifice);
                        ori.position.set(rr * Math.sin(phi), injFace + 0.5, rr * Math.cos(phi));
                        ori.userData.phi = phi;
                        ori.userData.hideInCut = true;
                        injector.add(ori);
                    }
                });
            }
            // Hibrit: kapaktan port girişine uzanan ateşleyici (pirinç gövde)
            if (!isLiquid) {
                var igR = clamp(0.09 * d.rc, 2.5, 8);
                var igL = (injZ0 + injT + 10) - (-d.capT + 1);
                var ig = new THREE.Mesh(
                    new THREE.CylinderGeometry(igR, igR * 0.8, igL, this._perfMode ? 10 : 16),
                    mats.injector);
                ig.position.y = (-d.capT + 1) + igL / 2;
                ig.castShadow = true;
                injector.add(ig);
            }
            this.parts.injector = injector;
        } else {
            this.parts.injector = new THREE.Group();
        }

        // --- Yakıt grain'i (port yarıçapı animasyonlu — ayrı build) ---
        this.parts.grain = new THREE.Group();
        this._grainMesh = null;
        this._rebuildGrain(portRadiusAt(d, this.state.time), true);

        // --- Nozul: metal tutucu gövde + grafit boğaz insert'i + flanş ---
        var np = nozzleProfile(d);
        this._nozzleInfo = np;
        var nozzle = buildSolid(np.poly, mats.nozzle, mats.nozzleCut, cut);
        // Grafit insert: gerçek akış konturunu taşıyan ayrı katı (kesitte
        // koyu bant olarak metal gövdeden ayrışır)
        if (np.insertPoly) {
            nozzle.add(buildSolid(np.insertPoly, mats.graphite, mats.graphiteCut, cut));
        }
        // Nozul-kasa arayüz O-ringi (flanş alın yüzeyi contası)
        addORing(nozzle, (d.rc + d.rcOut) / 2, d.Lch + 0.6,
                 clamp(0.18 * d.flangeT, 1.2, 3));
        addJointLine(nozzle, d.Lch - 0.4); // tüp-flanş birleşim izi
        // Flanş cıvataları (retention: cıvatalı flanş)
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

        this.assembly.add(this.parts.casing, this.parts.closure, this.parts.liner,
            this.parts.injector, this.parts.grain, this.parts.nozzle, this._throatFlame);

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
        if (this.parts.closure) this.parts.closure.position.y = -0.48 * L * f;
        this.parts.casing.position.y = -0.30 * L * f;
        this.parts.injector.position.y = -0.16 * L * f;
        this.parts.liner.position.y = -0.06 * L * f;
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
        // Kalite anahtarı (perf modu) partikül tavanını düşürür
        var qf = this._qualityFactor || 1.0;
        var active = Math.floor(this._plumeN * qf * clamp(intensity, 0, 1));
        // İtkiyle orantılı jet: eksenel hız ve plume boyu intensity ile ölçeklenir
        var velScale = 0.55 + 0.45 * clamp(intensity, 0, 1);
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
            pos[o3 + 1] += st[o5 + 0] * dt * velScale;
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
        // oksitleyici giriş borusu hariç). GRAIN etiketi sıvıda anlamsız —
        // orada Lg yanma odası boyudur, CHAMBER olarak yazılır.
        var lgLabel = (d.motorType === 'liquid' ? 'CHAMBER ' : 'GRAIN ') + d.Lg.toFixed(0) + ' mm';
        var totalTxt = textSprite('L ' + (this._nozzleInfo.zExit + d.capT).toFixed(0) + ' mm  •  ' + lgLabel,
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
        // Throttle artık İKİLİ DEĞİL: transient eğri verildiyse plume/ışıklar
        // anlık itkiyle orantılı (F(t)/F_max); yoksa eski tam-gaz davranışı.
        var thrustNow = null, pcNow = null;
        if (this._transient) {
            thrustNow = sampleSeries(this._transient.time, this._transient.thrust,
                Math.min(st.time, this._transient.tEnd));
            if (this._transient.pc) {
                pcNow = sampleSeries(this._transient.time, this._transient.pc,
                    Math.min(st.time, this._transient.tEnd));
            }
        }
        var throttle = 0;
        if (burning) {
            throttle = (thrustNow !== null && this._transient.thrustMax > 0)
                ? clamp(thrustNow / this._transient.thrustMax, 0.05, 1)
                : 1;
        }

        // Isı haritası zaman modülasyonu: q ∝ Pc^0.8 (Bartz) — vertex
        // renklerini yeniden hesaplamadan materyal parlaklığıyla uygulanır.
        if (this.state.heatMap && this._heatMat) {
            var amp = 1.0;
            if (burning && pcNow !== null && this._transient.pc0 > 0) {
                amp = clamp(Math.pow(pcNow / this._transient.pc0, 0.8), 0.35, 1.15);
            } else if (!burning && this._transient) {
                amp = 0.35; // yanma yok → soğuyan duvar görünümü
            }
            this._heatMat.color.setScalar(amp);
            this._heatMatCut.color.setScalar(amp);
        }

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
                // Transient eğri varsa GERÇEK anlık itki; yoksa tasarım sabiti
                thrust: thrustNow !== null
                    ? (st.time < d.burnTime ? thrustNow : 0)
                    : (st.time < d.burnTime ? d.thrust : 0),
                pc: pcNow,                      // Pa (transient varsa) | null
                throttle: throttle,
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
    // Transient veri bağla: {time[], thrust[] (N), chamber_pressure[] (Pa)?}
    // Plume/ışıklar F(t)/F_max ile, ısı haritası (Pc/Pc0)^0.8 ile modüle edilir;
    // HUD anlık itki/Pc yayınlar. null geçilirse eski sabit davranışa döner.
    MotorScene.prototype.setTransient = function (tr) {
        if (!tr || !tr.time || !tr.thrust || tr.time.length < 3) {
            this._transient = null;
            return;
        }
        var tmax = 0;
        for (var i = 0; i < tr.thrust.length; i++) tmax = Math.max(tmax, tr.thrust[i]);
        this._transient = {
            time: tr.time,
            thrust: tr.thrust,
            pc: tr.chamber_pressure || null,
            pc0: tr.chamber_pressure ? tr.chamber_pressure[0] : 0,
            thrustMax: tmax,
            tEnd: tr.time[tr.time.length - 1]
        };
        // Yanma süresi timeline'ı gerçek transient süresine oturt
        this.dims.burnTime = this._transient.tEnd;
    };
    // Kamera preset'leri: iso (ana), side (tam yan), nozzle (egzoz arkası),
    // injector (baş taraf). Mesafe _camHome yarıçapından türetilir.
    MotorScene.prototype.setCameraPreset = function (name) {
        var r = this._camHome.length();
        var presets = {
            iso: this._camHome.clone(),
            side: new THREE.Vector3(0, 0, r),
            nozzle: new THREE.Vector3(r * 0.85, -r * 0.25, r * 0.35),
            injector: new THREE.Vector3(-r * 0.85, r * 0.25, r * 0.35)
        };
        var p = presets[name] || presets.iso;
        this.camera.position.copy(p);
        this.controls.target.set(0, 0, 0);
        this._introT = 1;
        return name;
    };
    MotorScene.prototype.cycleCameraPreset = function () {
        var order = ['iso', 'side', 'nozzle', 'injector'];
        this._camPresetIdx = ((this._camPresetIdx || 0) + 1) % order.length;
        return this.setCameraPreset(order[this._camPresetIdx]);
    };
    // Kalite anahtarı: 'high' (varsayılan) | 'perf' — pixelRatio + partikül
    // tavanı + donanım detay segmentleri (O-ring/cıvata/halka poligon sayısı)
    MotorScene.prototype.setQuality = function (mode) {
        var perf = mode === 'perf';
        this._qualityFactor = perf ? 0.45 : 1.0;
        this.renderer.setPixelRatio(perf ? 1 : Math.min(window.devicePixelRatio || 1, 2));
        if (this._perfMode !== perf) {
            this._perfMode = perf;
            this._lastPortR = -1;
            this._buildMotor();     // detay geometrileri yeni segment sayısıyla
            this._buildLabels();
        }
        return perf ? 'perf' : 'high';
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
                    if (m.bumpMap) m.bumpMap.dispose();
                    if (m.roughnessMap && m.roughnessMap !== m.bumpMap) m.roughnessMap.dispose();
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
        // Transient itki/basınç eğrisini canlı sahneye bağla
        setTransient: function (tr) { if (viz) viz.setTransient(tr); },
        setCameraPreset: function (name) { return viz ? viz.setCameraPreset(name) : null; },
        cycleCameraPreset: function () { return viz ? viz.cycleCameraPreset() : null; },
        setQuality: function (mode) { return viz ? viz.setQuality(mode) : null; },
        get: function () { return viz; },
        dispose: function () { if (viz) { viz.dispose(); viz = null; } }
    };
})();
