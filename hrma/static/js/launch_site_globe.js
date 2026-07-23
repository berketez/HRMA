/* HRMA — İnteraktif 3B fırlatma sahası küresi + uçuş yolu animasyonu
 * ==================================================================
 * launch_site_globe.js
 *
 * "Bildiğin Dünya": düz renkli küre DEĞİL — NASA Blue Marble uydu dokusu
 * (hrma/static/img/blue_marble_4096.jpg) + Natural Earth ülke/kıyı sınırları
 * (earth_borders.json) bindirmesi. Kullanıcı küreyi döndürüp yakınlaşır,
 * herhangi bir noktaya tıklar; nokta enlem/boylama (raycast) çevrilir.
 *
 * ÖLÇEK BOZULMAZ, KAMERA UYARLANIR
 * --------------------------------
 * Küre gerçek yarıçapı temsil eder (R_EARTH_M). Uçuş yolu rakımı yüzeye
 * GERÇEK oranla (alt/R_EARTH) eklenir; abartma yalnız isteğe bağlı bir
 * anahtardır ve VARSAYILAN KAPALIDIR. Sondaj roketinde kamera sahaya
 * yakınlaşır, uzaya çıkanda tüm küre görünür. Ölçek göstergesi hep ekranda.
 *
 * DÜRÜSTLÜK
 * ---------
 *  - Yalnız çözücü verisi çizilir (6-DOF / düzlemsel). Sahte yörünge yok.
 *  - Yer izi (ground track) "Dünya dönüşü modellenmedi" diye etiketlenir;
 *    Dünya dönüşü/Coriolis v1'de modellenmiyor (bkz. launch_site.NOT_MODELLED).
 *  - Yakın zoomda küresel doku/DEM (~9 km) yerel arazi detayı içermez;
 *    sahte arazi/doku ÜRETİLMEZ, kullanıcı bir notla uyarılır.
 *  - Balistik uçuşa "orbit" denmez.
 *
 * Bağımlılık: THREE (three-0.128.0) + THREE.OrbitControls — SABİT sürüm.
 * Yeni kütüphane eklenmez.
 *
 * ENU -> jeodezik dönüşüm, hrma/analysis/launch_site.py:enu_to_geodetic ile
 * BİREBİR aynı birinci-mertebe teğet-düzlem formülüdür (WGS84 eğrilik
 * yarıçapları). Aynı geçerlilik sınırı geçerlidir: ~100 km'ye kadar hata
 * <%0.1, ötesinde düz-Dünya varsayımı sistematik sapar — altındaki 6-DOF
 * çözümünün de sınırı budur.
 */
(function (global) {
    'use strict';

    // ---- Fiziksel/görsel sabitler ----
    var R_EARTH_M = 6371000.0;        // m — six_dof_trajectory.R_EARTH ile aynı
    var GLOBE_R = 100.0;              // sahne birimi: küre yarıçapı
    var M_PER_UNIT = R_EARTH_M / GLOBE_R;   // 1 sahne birimi kaç metre
    // WGS84 (launch_site.py ile aynı türetilmiş sabitler)
    var WGS84_A = 6378137.0;
    var WGS84_E2 = 6.69437999014e-3;

    // Kamera mesafe sınırları. DİKKAT: OrbitControls.min/maxDistance HEDEFTEN
    // (target) ölçülür, Dünya merkezinden DEĞİL. Yerel görünümde hedef yüzeydedir;
    // bu yüzden hedefe yakın zoom için min HEDEF mesafesi KÜÇÜK olmalı. Kürenin
    // içine dalmayı ayrı bir YÜZEY KİLİDİ (SURFACE_MIN_LEN) engeller.
    var CTRL_MIN_TARGET = GLOBE_R * 0.004;   // hedefe ~2.5 km'ye kadar yaklaş
    var CTRL_MAX_TARGET = GLOBE_R * 6.0;     // en fazla uzaklaşma
    var SURFACE_MIN_LEN = GLOBE_R * 1.003;   // kamera merkezden en az bu kadar (yüzey kilidi)
    var GLOBAL_DIST = GLOBE_R * 2.6;         // "tüm Dünya" görünümü
    // Yakın zoomda "doku detayı yok" notunun tetiklendiği kamera yüksekliği [m]
    var TEXTURE_NOTE_ALT_M = 400000.0;

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function deg2rad(d) { return d * Math.PI / 180.0; }
    function rad2deg(r) { return r * 180.0 / Math.PI; }
    function normLon(lon) { return ((lon + 180.0) % 360.0 + 360.0) % 360.0 - 180.0; }

    // ---- Jeodezik <-> kartezyen (küre yüzeyi) --------------------------------
    // THREE.SphereGeometry varsayılan UV + equirectangular doku ile TUTARLI
    // türetilmiştir (doku sol kenarı = -180° boylam). Marker, sınır ve raycast
    // AYNI dönüşümü kullanır -> iç tutarlılık garanti.
    function latLonToVec3(latDeg, lonDeg, radius) {
        var la = deg2rad(latDeg), lo = deg2rad(lonDeg);
        var cl = Math.cos(la);
        return new global.THREE.Vector3(
            radius * cl * Math.cos(lo),
            radius * Math.sin(la),
            -radius * cl * Math.sin(lo)
        );
    }
    function vec3ToLatLon(v) {
        var r = v.length();
        var lat = rad2deg(Math.asin(clamp(v.y / r, -1, 1)));
        var lon = rad2deg(Math.atan2(-v.z, v.x));
        return { lat: lat, lon: normLon(lon) };
    }

    // ---- ENU (Kuzey,Doğu,Yukarı) -> jeodezik (launch_site.py ile birebir) ----
    function enuToGeodetic(lat0, lon0, h0, north, east, up) {
        var phi0 = deg2rad(clamp(lat0, -90, 90));
        var s2 = Math.sin(phi0) * Math.sin(phi0);
        var w = Math.sqrt(1.0 - WGS84_E2 * s2);
        var mRad = WGS84_A * (1.0 - WGS84_E2) / (w * w * w);  // meridyen eğriliği
        var nRad = WGS84_A / w;                               // enine eğrilik
        var dlat = north / (mRad + h0);
        var coslat = Math.max(Math.cos(phi0), 1e-9);
        var dlon = east / ((nRad + h0) * coslat);
        var lat = rad2deg(phi0 + dlat);
        var lon = rad2deg(deg2rad(normLon(lon0)) + dlon);
        return { lat: lat, lon: normLon(lon), alt: h0 + up };
    }

    // ===================================================================
    // LaunchSiteGlobe
    // ===================================================================
    function LaunchSiteGlobe(container, options) {
        options = options || {};
        this.container = container;
        this.opts = options;
        this._raf = null;
        this._flight = null;      // {t[], lat[], lon[], alt[], events, apogee, range}
        this._exaggerate = 1.0;   // rakım abartma çarpanı (1 = gerçek ölçek)
        this._playing = false;
        this._playT = 0;          // animasyon zamanı [s]
        this._follow = false;
        this._sitePoint = null;   // seçili saha 3B nokta
        this._disposed = false;
        this._onCursor = options.onCursor || null;
        this._onSelect = options.onSelect || null;
        this._onTime = options.onTime || null;
        this._onReady = options.onReady || null;
        this._onError = options.onError || null;
        this._init();
    }

    LaunchSiteGlobe.prototype._init = function () {
        var THREE = global.THREE;
        if (!THREE || !THREE.WebGLRenderer) {
            if (this._onError) this._onError('three_missing');
            return;
        }
        var w = this.container.clientWidth || 800;
        var h = this.container.clientHeight || 600;

        var renderer;
        try {
            renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        } catch (e) {
            if (this._onError) this._onError('webgl_failed');
            return;
        }
        renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
        renderer.setSize(w, h);
        renderer.setClearColor(0x000000, 0);   // saydam -> sayfa yıldız zemini görünür
        this.container.appendChild(renderer.domElement);
        this.renderer = renderer;

        var scene = new THREE.Scene();
        this.scene = scene;

        var camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 100000);
        camera.position.set(0, GLOBE_R * 0.55, GLOBAL_DIST);
        this.camera = camera;

        var controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.rotateSpeed = 0.42;
        controls.zoomSpeed = 0.85;
        controls.minDistance = CTRL_MIN_TARGET;
        controls.maxDistance = CTRL_MAX_TARGET;
        controls.enablePan = false;
        this.controls = controls;

        // Işık: kameraya bağlı "far" (headlight) — sahte gün/gece sınırı YOK.
        scene.add(new THREE.AmbientLight(0xffffff, 0.72));
        var head = new THREE.DirectionalLight(0xffffff, 0.7);
        this._headlight = head;
        scene.add(head);

        // --- Küre (Blue Marble) ---
        var geo = new THREE.SphereGeometry(GLOBE_R, 96, 64);
        var mat = new THREE.MeshPhongMaterial({
            color: 0x223344, shininess: 6, specular: 0x111820
        });
        this.globe = new THREE.Mesh(geo, mat);
        scene.add(this.globe);

        // İnce atmosfer halkası (yalnız görsel; fiziğe bağlı değil)
        var atmGeo = new THREE.SphereGeometry(GLOBE_R * 1.018, 96, 64);
        var atmMat = new THREE.MeshBasicMaterial({
            color: 0x2f6fb0, transparent: true, opacity: 0.10,
            side: THREE.BackSide, depthWrite: false
        });
        scene.add(new THREE.Mesh(atmGeo, atmMat));

        this._loadTexture();
        this._buildBorders();
        this._buildMarker();
        this._buildRaycaster();

        // Uçuş yolu grupları (sonradan doldurulur)
        this.flightGroup = new THREE.Group();
        scene.add(this.flightGroup);

        this._bindEvents();
        this._resize();
        this._animate();
        if (this._onReady) this._onReady();
    };

    LaunchSiteGlobe.prototype._loadTexture = function () {
        var THREE = global.THREE, self = this;
        var url = (this.opts.textureUrl || '/static/img/blue_marble_4096.jpg');
        new THREE.TextureLoader().load(url, function (tex) {
            if (self._disposed) return;
            tex.colorSpace = THREE.SRGBColorSpace || tex.colorSpace;
            tex.encoding = THREE.sRGBEncoding || tex.encoding;
            tex.anisotropy = Math.min(8, self.renderer.capabilities.getMaxAnisotropy());
            self.globe.material.map = tex;
            self.globe.material.color.setHex(0xffffff);
            self.globe.material.needsUpdate = true;
        }, undefined, function () {
            // Doku yüklenemezse küre yine görünür (koyu düz), sahte doku üretilmez.
            if (self._onError) self._onError('texture_failed');
        });
    };

    LaunchSiteGlobe.prototype._buildBorders = function () {
        var THREE = global.THREE, self = this;
        var url = (this.opts.bordersUrl || '/static/img/earth_borders.json');
        fetch(url).then(function (r) { return r.json(); }).then(function (data) {
            if (self._disposed || !data || !data.layers) return;
            var layers = data.layers;
            var group = new THREE.Group();
            var mkLines = function (polylines, color, opacity) {
                if (!polylines) return;
                var positions = [];
                for (var i = 0; i < polylines.length; i++) {
                    var flat = polylines[i];
                    for (var j = 0; j + 3 < flat.length; j += 2) {
                        var a = latLonToVec3(flat[j + 1], flat[j], GLOBE_R * 1.001);
                        var b = latLonToVec3(flat[j + 3], flat[j + 2], GLOBE_R * 1.001);
                        positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
                    }
                }
                var g = new THREE.BufferGeometry();
                g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
                var m = new THREE.LineBasicMaterial({
                    color: color, transparent: true, opacity: opacity, depthWrite: false
                });
                group.add(new THREE.LineSegments(g, m));
            };
            mkLines(layers.coastline, 0x8fd6ff, 0.34);
            mkLines(layers.borders, 0xbfe6ff, 0.5);
            self.bordersGroup = group;
            self.scene.add(group);
        }).catch(function () { /* sınır bindirmesi opsiyonel; sessiz geç */ });
    };

    // Ekran-sabit boyutlu işaretçiler: sahne birimi boyutu SABİT bir işaretçi
    // küresel görünümde nokta, yerel görünümde dev görünür. Bunun yerine tüm
    // yüzey işaretçileri BİRİM boyutta kurulur ve her karede kamera mesafesiyle
    // ölçeklenir -> her zoomda ~sabit piksel boyutu. (_scalables kaydı.)
    LaunchSiteGlobe.prototype._registerScalable = function (obj, k) {
        (this._scalables = this._scalables || []).push({ obj: obj, k: k });
    };
    LaunchSiteGlobe.prototype._updateScalables = function () {
        if (!this._scalables) return;
        var d = this.camera.position.distanceTo(this.controls.target);
        for (var i = 0; i < this._scalables.length; i++) {
            var s = this._scalables[i];
            if (s.obj.parent) s.obj.scale.setScalar(Math.max(d, 1e-3) * s.k);
        }
    };

    LaunchSiteGlobe.prototype._buildMarker = function () {
        var THREE = global.THREE;
        var grp = new THREE.Group();
        // Birim boyutta dikey iğne + taban halkası (her karede ölçeklenir)
        var pinMat = new THREE.MeshBasicMaterial({ color: 0xff8c33 });
        var pin = new THREE.Mesh(new THREE.ConeGeometry(0.32, 1.0, 16), pinMat);
        pin.position.y = 0.5;
        grp.add(pin);
        var ringMat = new THREE.MeshBasicMaterial({
            color: 0xff8c33, transparent: true, opacity: 0.85, side: THREE.DoubleSide });
        var ring = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.66, 24), ringMat);
        ring.rotation.x = -Math.PI / 2;
        grp.add(ring);
        grp.visible = false;
        this.marker = grp;
        this._registerScalable(grp, 0.013);   // ekran-sabit iğne boyutu
        this.scene.add(grp);
    };

    LaunchSiteGlobe.prototype._placeMarker = function (latDeg, lonDeg) {
        var THREE = global.THREE;
        var p = latLonToVec3(latDeg, lonDeg, GLOBE_R);
        this.marker.position.copy(p);
        // İğneyi yüzey normali boyunca hizala
        var up = p.clone().normalize();
        var q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), up);
        this.marker.quaternion.copy(q);
        this.marker.visible = true;
        this._sitePoint = p.clone();
    };

    LaunchSiteGlobe.prototype._buildRaycaster = function () {
        this.raycaster = new global.THREE.Raycaster();
        this.pointer = new global.THREE.Vector2();
    };

    LaunchSiteGlobe.prototype._bindEvents = function () {
        var self = this, dom = this.renderer.domElement;
        this._downXY = null;
        dom.addEventListener('pointerdown', function (e) {
            self._downXY = [e.clientX, e.clientY];
        });
        dom.addEventListener('pointermove', function (e) {
            var hit = self._hitLatLon(e);
            if (hit && self._onCursor) self._onCursor(hit);
        });
        dom.addEventListener('pointerup', function (e) {
            if (!self._downXY) return;
            var dx = e.clientX - self._downXY[0], dy = e.clientY - self._downXY[1];
            self._downXY = null;
            if (dx * dx + dy * dy > 36) return;   // sürükleme -> seçim değil
            var hit = self._hitLatLon(e);
            if (hit) self.selectSite(hit.lat, hit.lon);
        });
        global.addEventListener('resize', function () { self._resize(); });
    };

    LaunchSiteGlobe.prototype._hitLatLon = function (e) {
        var rect = this.renderer.domElement.getBoundingClientRect();
        this.pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.pointer, this.camera);
        var hits = this.raycaster.intersectObject(this.globe, false);
        if (!hits.length) return null;
        return vec3ToLatLon(hits[0].point);
    };

    // Kullanıcı ya da dış çağrı sahayı seçer
    LaunchSiteGlobe.prototype.selectSite = function (latDeg, lonDeg, opts) {
        opts = opts || {};
        this._placeMarker(latDeg, lonDeg);
        if (!opts.silent && this._onSelect)
            this._onSelect({ lat: latDeg, lon: normLon(lonDeg) });
        if (opts.frame) this.viewSite();
    };

    // ---- Kamera uyarlama ---------------------------------------------------
    // Tüm Dünya görünümü
    LaunchSiteGlobe.prototype.viewGlobe = function () {
        // Hedef Dünya merkezi; kamera sahaya doğru bir yönden bakar.
        var dirHint = this._sitePoint
            ? this._sitePoint.clone().normalize()
            : new global.THREE.Vector3(0, 0.4, 1);
        this._flyCamera(new global.THREE.Vector3(0, 0, 0), dirHint, GLOBAL_DIST);
        this._mode = 'global';
    };

    // Sahaya (ve varsa uçuş yoluna) yakınlaş — OBLİK açı: düşey arkı görebilmek
    // için kamera yandan bakar; ölçek bozulmaz, yalnız mesafe uyarlanır.
    LaunchSiteGlobe.prototype.viewSite = function () {
        var THREE = global.THREE;
        if (!this._sitePoint) { this.viewGlobe(); return; }
        var normal = this._sitePoint.clone().normalize();
        // Uçuş yolu varsa yatay yayılım yönünü, yoksa kuzeyi teğet al
        var tangent = this._pathTangent(normal);
        // Yolun 3B sınır yarıçapından gereken mesafeyi türet
        var need = this._pathBoundingRadius();
        var fov = deg2rad(this.camera.fov);
        var dist = need > 0 ? (need / Math.sin(fov / 2)) * 2.2 : GLOBE_R * 0.1;
        // Hedef mesafesi (yüzeye çapalı). Alt sınır ~10 birim (~630 km): sondaj
        // roketinde kamera sahaya yaklaşır ama sahanın COĞRAFYASI (kıyı/yarımada)
        // tanınacak kadar geride kalır — bulanık tek-doku yamasına dalınmaz.
        // Gerçek-ölçekte 14 km'lik sondaj arkı bu mesafede küçük bir işaretçi
        // kümesidir (DÜRÜST); dramatik yükselen ark için 'Rakımı abart' anahtarı
        // (varsayılan kapalı) kullanılır ve o zaman görünüm otomatik genişler.
        // Üst sınır uzaya çıkan büyük apojeleri sığdırır.
        dist = clamp(dist, GLOBE_R * 0.1, GLOBE_R * 2.5);
        var tilt = deg2rad(46);   // oblik bakış: bölge + hafif eğrilik
        var camDir = normal.clone().multiplyScalar(Math.cos(tilt))
            .add(tangent.clone().multiplyScalar(Math.sin(tilt))).normalize();
        var target = this._sitePoint.clone();
        // Yolu çerçeveye ortalamak için hedefi apojeye doğru biraz kaydır
        if (this._flight && this._pathMid) target = this._pathMid.clone();
        var camPos = target.clone().add(camDir.multiplyScalar(dist));
        this._flyCameraPos(camPos, target);
        this._mode = 'local';
    };

    LaunchSiteGlobe.prototype._pathTangent = function (normal) {
        var THREE = global.THREE;
        if (this._flight && this._pathPoints && this._pathPoints.length > 2) {
            var a = this._pathPoints[0];
            var b = this._pathPoints[this._pathPoints.length - 1];
            var horiz = b.clone().sub(a);
            // teğet düzleme izdüşür
            horiz.sub(normal.clone().multiplyScalar(horiz.dot(normal)));
            if (horiz.length() > 1e-4) return horiz.normalize();
        }
        // kuzey teğeti: worldUp x normal, sonra normal x that
        var east = new THREE.Vector3(0, 1, 0).cross(normal);
        if (east.length() < 1e-6) east = new THREE.Vector3(1, 0, 0);
        east.normalize();
        return normal.clone().cross(east).normalize();  // kuzeye doğru
    };

    LaunchSiteGlobe.prototype._pathBoundingRadius = function () {
        if (!this._pathPoints || !this._pathPoints.length) return 0;
        var c = this._pathMid || this._sitePoint;
        if (!c) return 0;
        var maxd = 0;
        for (var i = 0; i < this._pathPoints.length; i++) {
            var d = this._pathPoints[i].distanceTo(c);
            if (d > maxd) maxd = d;
        }
        return maxd;
    };

    LaunchSiteGlobe.prototype._flyCamera = function (target, dirHint, dist) {
        var THREE = global.THREE;
        var dir = dirHint.clone().normalize();
        // Dünya görünümünde hafif eğik bak
        var pos = target.clone().add(dir.multiplyScalar(dist));
        this._flyCameraPos(pos, target);
    };

    // Yumuşak kamera geçişi (tween)
    LaunchSiteGlobe.prototype._flyCameraPos = function (toPos, toTarget) {
        var self = this;
        var fromPos = this.camera.position.clone();
        var fromTgt = this.controls.target.clone();
        var t0 = performance.now(), dur = 620;
        function step() {
            if (self._disposed) return;
            var k = clamp((performance.now() - t0) / dur, 0, 1);
            var e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; // easeInOut
            self.camera.position.lerpVectors(fromPos, toPos, e);
            self.controls.target.lerpVectors(fromTgt, toTarget, e);
            self.controls.update();
            if (k < 1) requestAnimationFrame(step);
        }
        step();
    };

    // ---- Uçuş yolu ---------------------------------------------------------
    // data: {time:[s], north:[m], east:[m], altitude:[m], events?, apogee?, ...}
    // lat0/lon0/h0: seçili saha (h0 = saha rakımı [m])
    LaunchSiteGlobe.prototype.setFlightPath = function (series, lat0, lon0, h0) {
        var THREE = global.THREE;
        this.clearFlightPath();
        if (!series || !series.time || !series.time.length) return;
        h0 = h0 || 0;
        var n = series.time.length;
        var lat = new Array(n), lon = new Array(n), alt = new Array(n);
        // 6-DOF çözücü z=0'dan (deniz seviyesi) kalkar; series.altitude deniz
        // seviyesi ÜSTÜ irtifadır (ENU yukarı bileşeni = altitude, saha
        // rakımı h0 yalnız yatay eğrilik teriminde, etkisi ihmal edilebilir).
        for (var i = 0; i < n; i++) {
            var g = enuToGeodetic(lat0, lon0, h0,
                series.north ? series.north[i] : 0,
                series.east ? series.east[i] : 0,
                series.altitude[i]);
            lat[i] = g.lat; lon[i] = g.lon; alt[i] = series.altitude[i];
        }
        this._flight = {
            t: series.time.slice(), lat: lat, lon: lon, alt: alt,
            speed: series.speed ? series.speed.slice() : null,
            lat0: lat0, lon0: lon0, h0: h0,
            apogee: null, apogeeIdx: 0, range: 0
        };
        // Apoje + menzil türet (çözümden)
        var maxA = -1e9, ai = 0;
        for (var k = 0; k < n; k++) { if (alt[k] > maxA) { maxA = alt[k]; ai = k; } }
        this._flight.apogee = maxA; this._flight.apogeeIdx = ai;
        var last = latLonToVec3(lat[n - 1], lon[n - 1], GLOBE_R);
        var first = latLonToVec3(lat[0], lon[0], GLOBE_R);
        this._flight.range = last.distanceTo(first) * M_PER_UNIT; // yüzey kirişi ~ menzil
        this._buildFlightGeometry();
        this._playT = 0; this._playing = false;
        this._emitTime();
        this.viewSite();
    };

    LaunchSiteGlobe.prototype._buildFlightGeometry = function () {
        var THREE = global.THREE, f = this._flight;
        if (!f) return;
        var n = f.t.length;
        this._pathPoints = new Array(n);
        this._groundPoints = new Array(n);
        for (var i = 0; i < n; i++) {
            var rr = GLOBE_R * (1.0 + this._exaggerate * f.alt[i] / R_EARTH_M);
            this._pathPoints[i] = latLonToVec3(f.lat[i], f.lon[i], rr);
            this._groundPoints[i] = latLonToVec3(f.lat[i], f.lon[i], GLOBE_R * 1.0015);
        }
        // orta nokta (çerçeveleme için): saha ile apoje arası
        var ap = this._pathPoints[f.apogeeIdx];
        this._pathMid = this._pathPoints[0].clone().add(ap).multiplyScalar(0.5);

        // Uçuş yolu — TAM rota her zaman soluk turuncu çizilir ("roketin
        // izleyeceği yol"); animasyonda ÜSTÜNE parlak bir iz (trail) katedilen
        // kısmı doldurur. İkisi de yalnız çözücü noktalarından gelir.
        var g1 = new THREE.BufferGeometry().setFromPoints(this._pathPoints);
        this._pathLine = new THREE.Line(g1, new THREE.LineBasicMaterial({
            color: 0xff8c33, transparent: true, opacity: 0.34 }));
        this.flightGroup.add(this._pathLine);
        var g1b = new THREE.BufferGeometry().setFromPoints(this._pathPoints);
        this._trailLine = new THREE.Line(g1b, new THREE.LineBasicMaterial({
            color: 0xffb066, transparent: true, opacity: 0.98 }));
        this._trailLine.geometry.setDrawRange(0, 2);
        this.flightGroup.add(this._trailLine);

        // Yer izi (soluk camgöbeği, kesikli) — "Dünya dönüşü modellenmedi"
        var g2 = new THREE.BufferGeometry().setFromPoints(this._groundPoints);
        this._groundLine = new THREE.Line(g2, new THREE.LineDashedMaterial({
            color: 0x4fd0e0, transparent: true, opacity: 0.55,
            dashSize: GLOBE_R * 0.004, gapSize: GLOBE_R * 0.004 }));
        this._groundLine.computeLineDistances();
        this.flightGroup.add(this._groundLine);

        // Olay işaretçileri (kalkış/yanma sonu/apoje/bitiş) — çözümden türetildi
        this._buildEventMarkers();

        // Roket işaretçisi (animasyon boyunca ilerler) — birim küre, ekran-sabit
        var rk = new THREE.Mesh(
            new THREE.SphereGeometry(1, 12, 12),
            new THREE.MeshBasicMaterial({ color: 0xffffff }));
        this._rocket = rk;
        this.flightGroup.add(rk);
        this._registerScalable(rk, 0.006);
        this._seekFraction(0);
    };

    LaunchSiteGlobe.prototype._buildEventMarkers = function () {
        var THREE = global.THREE, f = this._flight;
        this._events = [];
        var add = function (idx, color, key, self) {
            if (idx == null || idx < 0 || idx >= f.t.length) return;
            var p = self._pathPoints[idx];
            var m = new THREE.Mesh(
                new THREE.SphereGeometry(1, 14, 14),
                new THREE.MeshBasicMaterial({ color: color }));
            m.position.copy(p);
            self.flightGroup.add(m);
            self._registerScalable(m, 0.0075);   // ekran-sabit olay noktası
            self._events.push({ idx: idx, key: key, t: f.t[idx],
                alt: f.alt[idx], color: color });
        };
        add(0, 0x2dd4a8, 'liftoff', this);              // kalkış
        if (this.opts.burnTime != null) {
            var bt = this.opts.burnTime, bi = 0;
            for (var i = 0; i < f.t.length; i++) { if (f.t[i] <= bt) bi = i; }
            add(bi, 0xffd166, 'burnout', this);          // yanma sonu
        }
        add(f.apogeeIdx, 0x00e5ff, 'apogee', this);      // apoje
        // Bitiş işaretçisi YALNIZ apojeden anlamlı biçimde farklıysa ve
        // çözücünün DURDUĞU nedene göre etiketlenir (dürüstlük): 6-DOF çözücü
        // apojede sonlanır -> ayrı "yer" işaretçisi EKLENMEZ; yalnız yere iniş
        // (ground) ya da zaman/takla ile biten çözümlerde bitiş noktası konur.
        var reason = this.opts.endReason;
        var lastIdx = f.t.length - 1;
        if (lastIdx !== f.apogeeIdx) {
            if (reason === 'ground')
                add(lastIdx, 0xff5d73, 'impact', this);      // yere iniş
            else if (reason && reason !== 'apogee')
                add(lastIdx, 0xff5d73, 'end', this);         // zaman/takla sonu
        }
    };

    LaunchSiteGlobe.prototype.clearFlightPath = function () {
        if (!this.flightGroup) return;
        while (this.flightGroup.children.length) {
            var c = this.flightGroup.children.pop();
            if (c.geometry) c.geometry.dispose();
            if (c.material) c.material.dispose();
            this.flightGroup.remove(c);
        }
        this._flight = null; this._pathPoints = null; this._groundPoints = null;
        this._events = null; this._rocket = null; this._pathLine = null;
        this._trailLine = null; this._groundLine = null; this._pathMid = null;
        this._playing = false; this._playT = 0;
        // Ölçeklenebilir işaretçi listesinden uçuşa ait (artık sahnede olmayan)
        // ögeleri temizle; kalıcı saha iğnesi (parent hâlâ var) korunur.
        if (this._scalables)
            this._scalables = this._scalables.filter(function (s) { return !!s.obj.parent; });
    };

    LaunchSiteGlobe.prototype.setExaggeration = function (factor) {
        this._exaggerate = Math.max(1.0, factor || 1.0);
        if (this._flight) {
            var t = this._playT, playing = this._playing;
            this._rebuildFromFlight();   // geometriyi yeni ölçekle yeniden kur
            this._playT = t; this._playing = playing;
            this._seekTime(t);
            this.viewSite();             // büyüyen/küçülen arkı yeniden çerçevele
        }
    };

    // Okunabilirlik için abartma çarpanı: apojeyi ~%15 küre yarıçapına taşır
    // (küçük sondaj arkı görünür olur, büyük uçuşlar absürt boyuta şişmez).
    LaunchSiteGlobe.prototype.readableExaggeration = function () {
        if (!this._flight || !(this._flight.apogee > 0)) return 40.0;
        var frac = this._flight.apogee / R_EARTH_M;   // apoje / Dünya yarıçapı
        return clamp(0.15 / frac, 1.0, 3000.0);
    };

    LaunchSiteGlobe.prototype._rebuildFromFlight = function () {
        var f = this._flight; if (!f) return;
        // yol/yer çizgilerini ve olayları kaldır ama f'i koru
        var keep = this._flight;
        this.clearFlightPath();
        this._flight = keep;
        this._buildFlightGeometry();
    };

    // ---- Animasyon oynatıcı ------------------------------------------------
    LaunchSiteGlobe.prototype.play = function () {
        if (!this._flight) return;
        if (this._playT >= this._flight.t[this._flight.t.length - 1]) this._playT = 0;
        this._playing = true; this._lastTick = performance.now();
    };
    LaunchSiteGlobe.prototype.pause = function () { this._playing = false; };
    LaunchSiteGlobe.prototype.toggle = function () {
        if (this._playing) this.pause(); else this.play();
    };
    LaunchSiteGlobe.prototype.resetPlay = function () {
        this._playing = false; this._playT = 0; this._seekTime(0); this._emitTime();
    };
    LaunchSiteGlobe.prototype.setFollow = function (on) { this._follow = !!on; };

    // Zaman kaydırıcısı 0..1
    LaunchSiteGlobe.prototype.seek = function (frac) {
        if (!this._flight) return;
        var T = this._flight.t[this._flight.t.length - 1];
        this._playT = clamp(frac, 0, 1) * T;
        this._seekTime(this._playT);
        this._emitTime();
    };

    LaunchSiteGlobe.prototype._seekFraction = function (frac) {
        if (!this._flight) return;
        this._seekTime(frac * this._flight.t[this._flight.t.length - 1]);
    };

    LaunchSiteGlobe.prototype._seekTime = function (tSec) {
        var f = this._flight; if (!f || !this._rocket) return;
        var n = f.t.length;
        var T = f.t[n - 1];
        tSec = clamp(tSec, 0, T);
        // t -> indis (lineer arama, ~300 nokta)
        var i = 0;
        while (i < n - 1 && f.t[i + 1] < tSec) i++;
        var j = Math.min(i + 1, n - 1);
        var span = (f.t[j] - f.t[i]) || 1e-9;
        var a = clamp((tSec - f.t[i]) / span, 0, 1);
        var p = this._pathPoints[i].clone().lerp(this._pathPoints[j], a);
        this._rocket.position.copy(p);
        this._curIdx = i;
        // Parlak iz: kat edilen kısmı doldur (tam rota soluk olarak zaten görünür)
        if (this._trailLine) {
            var drawn = Math.max(2, Math.floor(i + a) + 1);
            this._trailLine.geometry.setDrawRange(0, drawn);
        }
        if (this._follow) {
            var normal = p.clone().normalize();
            var t = this._pathTangent(normal);
            var tilt = deg2rad(40);
            var dist = clamp(this._pathBoundingRadius() * 0.9,
                GLOBE_R * 0.03, GLOBE_R * 1.0);
            var camDir = normal.clone().multiplyScalar(Math.cos(tilt))
                .add(t.clone().multiplyScalar(Math.sin(tilt))).normalize();
            this.controls.target.lerp(p, 0.25);
            this.camera.position.lerp(p.clone().add(camDir.multiplyScalar(dist)), 0.08);
        }
    };

    LaunchSiteGlobe.prototype._emitTime = function () {
        if (!this._onTime || !this._flight) return;
        var f = this._flight, n = f.t.length;
        var T = f.t[n - 1];
        var i = this._curIdx || 0;
        this._onTime({
            t: this._playT, tMax: T, frac: T > 0 ? this._playT / T : 0,
            playing: this._playing,
            alt: f.alt[i], lat: f.lat[i], lon: f.lon[i],
            speed: f.speed ? f.speed[i] : null,
            apogee: f.apogee, range: f.range
        });
    };

    // ---- Ölçek / kamera-yükseklik göstergesi -------------------------------
    LaunchSiteGlobe.prototype.getScaleInfo = function () {
        var dist = this.camera.position.distanceTo(this.controls.target);
        var fov = deg2rad(this.camera.fov);
        var vh = this.container.clientHeight || 600;
        var worldPerPx = (2 * dist * Math.tan(fov / 2)) / vh;   // sahne birimi/px
        var mPerPx = worldPerPx * M_PER_UNIT;
        var camAltM = this.camera.position.length() * M_PER_UNIT - R_EARTH_M;
        return {
            metersPerPixel: mPerPx,
            camAltitudeM: camAltM,
            textureCoarse: camAltM < TEXTURE_NOTE_ALT_M
        };
    };

    // ---- Ana döngü ---------------------------------------------------------
    LaunchSiteGlobe.prototype._animate = function () {
        var self = this;
        function loop() {
            if (self._disposed) return;
            self._raf = requestAnimationFrame(loop);
            // headlight'ı kamera yönüne getir
            if (self._headlight)
                self._headlight.position.copy(self.camera.position);
            // yüzey işaretçilerini ekran-sabit boyuta ölçekle
            self._updateScalables();
            // animasyon ilerlet
            if (self._playing && self._flight) {
                var now = performance.now();
                var dt = (now - self._lastTick) / 1000.0;
                self._lastTick = now;
                var speed = self.opts.playbackSpeed || 1.0;
                self._playT += dt * speed;
                var T = self._flight.t[self._flight.t.length - 1];
                if (self._playT >= T) { self._playT = T; self._playing = false; }
                self._seekTime(self._playT);
                self._emitTime();
            }
            self.controls.update();
            // YÜZEY KİLİDİ: kamera küre içine giremez (hedef yüzeyde olsa bile).
            // OrbitControls min mesafesi hedeften ölçüldüğü için, yüzeye çapalı
            // yerel görünümde tek koruma budur.
            if (self.camera.position.length() < SURFACE_MIN_LEN)
                self.camera.position.setLength(SURFACE_MIN_LEN);
            self.renderer.render(self.scene, self.camera);
        }
        loop();
    };

    LaunchSiteGlobe.prototype._resize = function () {
        if (!this.renderer) return;
        var w = this.container.clientWidth || 800;
        var h = this.container.clientHeight || 600;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    };

    LaunchSiteGlobe.prototype.dispose = function () {
        this._disposed = true;
        if (this._raf) cancelAnimationFrame(this._raf);
        this.clearFlightPath();
        if (this.renderer) {
            this.renderer.dispose();
            if (this.renderer.domElement && this.renderer.domElement.parentNode)
                this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
        }
    };

    // Dışa aç
    LaunchSiteGlobe.latLonToVec3 = latLonToVec3;
    LaunchSiteGlobe.vec3ToLatLon = vec3ToLatLon;
    LaunchSiteGlobe.enuToGeodetic = enuToGeodetic;
    LaunchSiteGlobe.R_EARTH_M = R_EARTH_M;
    global.LaunchSiteGlobe = LaunchSiteGlobe;

})(typeof window !== 'undefined' ? window : this);
