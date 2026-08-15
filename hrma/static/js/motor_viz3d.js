/*
 * MotorViz3D — HRMA hibrit roket motoru 3D simülasyon görselleştiricisi
 *
 * Three.js (r128 UMD) ile /calculate yanıtındaki results.motor sözlüğünden
 * parametrik motor modeli kurar: gövde + kapak + enjektör + grain + Rao
 * konturlu C-D nozul. Kesit (cutaway) görünümü, yanma animasyonu
 * (port regresyonu YALNIZ gerçek çözücü serisinden: hibritte port_history,
 * katıda itki eğrisinin kütle dengesi; seri yoksa port donuk + beyan),
 * egzoz plume partikül sistemi,
 * ölçü etiketleri, patlatılmış görünüm ve CAD kipi (ortografik görünüşler,
 * teknik-resim leader ölçüleri, nötr stüdyo) içerir. Soğutma kanalları /
 * enjektör deseni / lüle konturu YALNIZ çözücü verisi varsa çizilir;
 * yoksa durum çipleri bunu beyan eder (sahte veri yasağı, v2.6.27).
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

    // Yanma animasyonu performansı: grain katısı her karede değil, port
    // yarıçapı en az bu kadar değişince yeniden kurulur (mm ve dış yarıçap
    // oranı — hangisi büyükse). Aradaki karelerde parıltı silindiri mevcut
    // mesh'e radyal ölçekle uydurulur (2026-07-21, görev 1).
    var GRAIN_REBUILD_MIN_MM = 0.4;
    var GRAIN_REBUILD_FRACTION = 0.01;

    // Otomatik kalite bekçisi: son N karenin ortalama süresi eşiği aşarsa
    // sahne kendiliğinden 'perf' moduna düşer (görev 3).
    var AUTO_PERF_FRAME_WINDOW = 60;      // ölçüm penceresi (kare)
    var AUTO_PERF_DT_LIMIT = 0.028;       // ortalama kare süresi eşiği (s)

    // Plume fiziği (görev 6): radyal saçılım referans çıkış yarım açısı ve
    // deniz seviyesinde ~ideal genişleme oranı (pe ≈ pa) yaklaşımı.
    // Görsel normalizasyon çapası: 8 derece yarı açılı bir bell nozul
    // sahnede "referans genişlikte" bir jet üretir. Bu bir FİZİK sabiti
    // değil, saçılımı ekran ölçeğine oturtan bir katsayıdır — jetin
    // gerçek açısı çözücünün nozul açısından ve pe/pa oranından gelir.
    var PLUME_REF_EXIT_ANGLE_DEG = 8;
    // IDEAL_EXPANSION_EPS (=8) KALDIRILDI (v2.6.26): pe/pa oranını
    // `(8/eps)^1.15` diye tahmin etmek için kullanılıyordu; hem 8 hem 1.15
    // dayanaksızdı. Artık gerçek çıkış ve ortam basıncı okunuyor.

    // ==================================================================
    // Görsel kalite saf fonksiyonları (2026-08-03, 3B sahne kalitesi)
    //
    // Bunlar THREE'siz saf matematiktir; node bekçi testleri
    // (tests/test_viz3d_gorsel_kalite.py) metinden çıkarıp izole sınar.
    // Fizik değerleri DEĞİŞMEZ — yalnız görsel sunum (kadraj, boyut,
    // görünürlük aktarımı, ölçek) burada hesaplanır.
    // ==================================================================

    // --- Kamera kadrajı (kalem 4) -------------------------------------
    // Eski kural dist = max(L*1.15, R*6) yalnız dikey FOV'u örtük varsayar,
    // viewport en-boy oranını hiç kullanmazdı; L/D≈19,7 varsayılan gövdede
    // motor kare yüksekliğinin ~%6'sını dolduruyordu (ölçüldü 2026-08-03).
    // Yeni kural:
    //  * Sınırlayıcı kutunun 8 köşesi bakış eksenine izdüşürülür; mesafe
    //    HEM yatay HEM dikey FOV kısıtını sağlayan en küçük değerdir.
    //  * Uzun-ince gövdede (L/D > CAMERA_SLENDER_RATIO) açılış kompozisyonu
    //    motoru ekran köşegenine yatırır: köşegen kenardan uzun olduğu için
    //    gövde kadrajı çaprazlama doldurur, boş kalan pay düşer.
    var CAMERA_FOV_DEG = 40;         // _initRenderer'daki dikey FOV ile aynı
    var CAMERA_FIT_MARGIN = 1.12;    // kutu ile kadraj kenarı arasındaki pay
    var CAMERA_SLENDER_RATIO = 6;    // L/D eşiği: üstünde köşegen kompozisyon
    var CAMERA_DIR_REGULAR = { x: 0.22, y: 0.30, z: 1.0 };   // klasik 3/4 bakış
    var CAMERA_DIR_DIAGONAL = { x: 0.85, y: 0.95, z: 1.0 };  // eksen köşegene yatar

    function cameraFrameFit(halfLen, maxRadius, fovDeg, aspect) {
        var slender = halfLen / Math.max(maxRadius, 1e-6) > CAMERA_SLENDER_RATIO;
        var raw = slender ? CAMERA_DIR_DIAGONAL : CAMERA_DIR_REGULAR;
        var n = Math.sqrt(raw.x * raw.x + raw.y * raw.y + raw.z * raw.z);
        var d = { x: raw.x / n, y: raw.y / n, z: raw.z / n };
        var tv = Math.tan(fovDeg * Math.PI / 360);
        var th = tv * Math.max(aspect || 1, 0.2);
        // Kamera uzayı eksenleri (up = +Y): xAxis = normalize(up × d),
        // yAxis = d × xAxis (d birim, xAxis ⊥ d → yAxis de birim)
        var xn = Math.sqrt(d.z * d.z + d.x * d.x);
        var xAxis = { x: d.z / xn, y: 0, z: -d.x / xn };
        var yAxis = {
            x: d.y * xAxis.z,
            y: d.z * xAxis.x - d.x * xAxis.z,
            z: -d.y * xAxis.x
        };
        var corners = [], sx, sy, sz, i, p, along, cx, cy;
        for (sx = -1; sx <= 1; sx += 2)
            for (sy = -1; sy <= 1; sy += 2)
                for (sz = -1; sz <= 1; sz += 2)
                    corners.push({ x: sx * halfLen, y: sy * maxRadius, z: sz * maxRadius });
        var dist = maxRadius * 2.5;  // taban: yakın düzlem / parça içi emniyeti
        for (i = 0; i < corners.length; i++) {
            p = corners[i];
            along = p.x * d.x + p.y * d.y + p.z * d.z;   // bakış ekseni bileşeni
            cx = p.x * xAxis.x + p.y * xAxis.y + p.z * xAxis.z;
            cy = p.x * yAxis.x + p.y * yAxis.y + p.z * yAxis.z;
            dist = Math.max(dist,
                along + CAMERA_FIT_MARGIN * Math.abs(cx) / th,
                along + CAMERA_FIT_MARGIN * Math.abs(cy) / tv);
        }
        // Doluluk: köşelerin normalize ekran koordinatlarındaki yayılımı
        // ([-1,1] tam kadraj) — teşhis/bekçi metriği
        var minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity;
        for (i = 0; i < corners.length; i++) {
            p = corners[i];
            along = p.x * d.x + p.y * d.y + p.z * d.z;
            cx = p.x * xAxis.x + p.y * xAxis.y + p.z * xAxis.z;
            cy = p.x * yAxis.x + p.y * yAxis.y + p.z * yAxis.z;
            var u = cx / (th * (dist - along));
            var v = cy / (tv * (dist - along));
            minU = Math.min(minU, u); maxU = Math.max(maxU, u);
            minV = Math.min(minV, v); maxV = Math.max(maxV, v);
        }
        return {
            dist: dist, dir: d, slender: slender,
            fill: Math.max(maxU - minU, maxV - minV) / 2
        };
    }

    // Lüle bölgesi (kalem 4, ikincil preset): çıkış düzlemi çevresinde,
    // jet çekirdeği + ilk şok hücrelerini içine alan kadraj kutusu.
    function nozzleRegion(totalLen, exitRadius, bodyRadius) {
        var halfLen = Math.max(0.10 * totalLen, 3 * exitRadius);
        return {
            halfLen: halfLen,
            radius: Math.max(1.4 * exitRadius, bodyRadius),
            targetOffset: halfLen * 0.4   // hedef çıkışın önünde (jet çekirdeği)
        };
    }

    // --- Egzoz plume görünürlüğü (kalem 1-2-3) ------------------------
    // Parçacık boyutu ekran-piksel hedeflidir. three.js r128
    // PointsMaterial (sizeAttenuation) nokta çapı:
    //     çap_px ≈ size · (viewportH / 2) / derinlik
    // Ev kadrajında derinlik ≈ kamera oturtma mesafesi. Eski kural
    // size = max(3, re·0.55) yalnız çıkış yarıçapına bağlıydı; kamera
    // L/D≈19,7 gövdeyi çerçevelerken parçacık ekranda ~4 px kalıyordu
    // ("üç-beş noktacık" görüntüsü, ölçüldü 2026-08-03). Alt sınırlar
    // korunur: yakın kadrajda eski re tabanlı boyuta düşülür.
    var PLUME_PARTICLE_TARGET_PX = 14;   // ev kadrajında hedef nokta çapı (px)
    function plumeParticleSize(exitRadius, camDist, viewportH) {
        var vh = viewportH > 0 ? viewportH : 520;
        var byScreen = 2 * PLUME_PARTICLE_TARGET_PX * camDist / vh;
        return Math.max(3, exitRadius * 0.55, byScreen);
    }

    // Görünür plume boy bütçesi: motor boyunun katı. Eskiden ömür sabitti,
    // boyu hız belirliyordu → jet ~2,2·L'ye dek uzayıp kadraj dışına
    // taşıyordu. Şimdi boy bütçelenir, ömür boydan türetilir (life = boy/hız).
    var PLUME_LEN_PER_MOTOR = 1.2;
    // Parçacık yoğunluğu: (plume boyu / motor boyu) birimi başına parçacık.
    // 750 · 1,2 = 900 → eski toplamla aynı mertebe; boy bütçesi değişirse
    // sayı onunla ORANTILI değişir, ekran yoğunluğu düşmez (kalem 1).
    var PLUME_PARTICLES_PER_UNIT = 750;
    function plumeLengthMm(totalLen) {
        return PLUME_LEN_PER_MOTOR * totalLen;
    }
    function plumeParticleCount(totalLen) {
        return Math.round(PLUME_PARTICLES_PER_UNIT *
            plumeLengthMm(totalLen) / Math.max(totalLen, 1e-6));
    }
    // Parçacık ömrü: ortalama menzil ≈ plume boyu (life = boy / hız);
    // ±%25 saçılım türbülanslı jetin menzil dağılımını temsil eder.
    function plumeLifeSeconds(plumeLen, speed, rand) {
        return (plumeLen / Math.max(speed, 1e-6)) * (0.75 + 0.5 * rand);
    }

    // Renk-yaşam eğrisi (kalem 2): parlaklık serbest türbülanslı jetin
    // merkez-hattı sıcaklık sönümünü izler — potansiyel çekirdek sonrası
    // ΔT ∝ 1/(x/D) (ör. Pope, Turbulent Flows §5.1; eksenel mesafe x,
    // yaşam oranı f ile orantılı). Eski (1-f)² eğrisi f>0.4'te fiilen
    // sıfırdı: ömrün son 2/3'ü görünmüyordu. 1/(1+3f): f=1'de çekirdek
    // parlaklığının 1/4'ü kalır (3 katsayısı bu uç değeri seçer) —
    // kuyruk soğumuş AMA seçilebilir. Renk kayması soğumayı verir:
    // beyaz-mavi çekirdek → turuncu → derin kızıl. Bantlar eski paletin
    // aynısıdır; keyfî süsleme eklenmedi.
    // v2.6.27 alev estetiği (kalem 2): üçüncü bağımsız değişken exitTempK
    // verildiyse yaş bantları yerine SICAKLIK sürücülü akkor rengi kullanılır:
    // T(f) yukarıdaki 1/(1+3f) soğuma modelinden (flameTempAt), renk
    // flameColorFromT akkor yaklaşımından. Zincir: gerçek T_c → izentropik
    // Te (readNozzleExit) → T(f) → renk. Te yoksa (eski kayıt / eksik Tc)
    // beyanlı eski bant paleti sürer — davranış değişmez, uydurma Te yok.
    function plumeColorAt(f, intensity, exitTempK) {
        var fade = intensity / (1 + 3 * f);
        var r, g, b;
        if (typeof exitTempK === 'number' && isFinite(exitTempK)
            && exitTempK > 0) {
            var tc = flameColorFromT(flameTempAt(f, exitTempK));
            r = tc.r; g = tc.g; b = tc.b;
        } else if (f < 0.18) { r = 1.0; g = 1.0; b = 1.05; }
        else if (f < 0.5) { r = 1.0; g = 0.62; b = 0.22; }
        else { r = 0.85; g = 0.32; b = 0.08; }
        return { r: r * fade, g: g * fade, b: b * fade, fade: fade };
    }

    // Şok elması görünürlük aktarımı (kalem 3): fiziksel sürücü |1 − pe/pa|
    // DEĞİŞMEDİ; ekrana aktarım Stevens güç yasasıyla sıkıştırılır
    // (algılanan şiddet ≈ uyaran^n; parlaklık için n ≈ 0.33-0.5 — Stevens,
    // Psychol. Rev. 64, 1957). n = 0.4 ile adapte lülede (|1−pe/pa| ≈ 0.06)
    // görünürlük ≈ 0.33 → zayıf ama SEÇİLEBİLİR; güçlü sapmada 1'e doyar;
    // tam genişlemede 0 (hücre yapısı fiziksel olarak yok).
    var DIAMOND_VIS_EXPONENT = 0.4;
    function diamondVisibility(pressureRatio) {
        if (!isFinite(pressureRatio)) return 0;
        var mismatch = Math.min(Math.abs(1 - pressureRatio), 1);
        return mismatch <= 0 ? 0 : Math.pow(mismatch, DIAMOND_VIS_EXPONENT);
    }

    // ==================================================================
    // Alev estetiği saf fonksiyonları (2026-08-04, egzoz tutarlı aleve)
    //
    // Teşhis: egzoz üç motorda da gerçek veriyle yanıyor ama görünüm
    // 'patlamış mısır' — sert kenarlı ayrık parlak toplar, banda bölünmüş
    // sabit renk, parçacıkların altında süreklilik katmanı yok. Aşağıdaki
    // fonksiyonlar YALNIZ görsel sunumu düzeltir; sürücüler değişmedi —
    // her parametre readNozzleExit'in gerçek çıkış durumundan türer.
    // Bekçi testleri: tests/test_alev_estetigi.py (node ile izole sınama).
    // ==================================================================

    // --- Kalem 1a: sprite opaklık profili (Gauss) ---------------------
    // Türbülanslı jetin zaman-ortalamalı hız/skaler profili öz-benzer ve
    // eksende tepeli, Gauss biçimindedir (Pope, Turbulent Flows §5.1);
    // tek parçacığın ışık lekesi de aynı biçimde yumuşatılır — eski iki
    // duraklı gradyanın geniş parlak göbeği sert kenarlı 'top' artefaktı
    // üretiyordu. sigma=0.30: kenarda (t=1) opaklık e^(-1/0.18) ≈ 0.004,
    // kırpma halkası görünmez.
    var FLAME_SPRITE_SIGMA = 0.30;
    function flameSpriteAlpha(t) {
        if (!(t >= 0)) return 1;
        if (t >= 1) return 0;
        return Math.exp(-(t * t) / (2 * FLAME_SPRITE_SIGMA * FLAME_SPRITE_SIGMA));
    }
    // Radyal gradyan durakları: [0,1] üzerinde eşit aralıklı n örnek.
    function flameSpriteStops(n) {
        var count = (n >= 2) ? Math.floor(n) : 9;
        var out = [];
        for (var i = 0; i < count; i++) {
            var t = i / (count - 1);
            out.push({ t: t, alpha: flameSpriteAlpha(t) });
        }
        return out;
    }

    // --- Kalem 1b: doğuş yarıçapı dağılımı (eksene yoğun) -------------
    // Eski sqrt(u) örneklemesi kesitte ALANCA eşdağılımdı: kenar eksen
    // kadar doluydu, additive toplama hiçbir yerde doymuyordu → ayrık
    // toplar. Jetin kütle akısı eksende tepe yapar (yukarıdaki Gauss
    // profili ile aynı gerekçe); u^1 örneklemesi radyal yoğunluğu sabit,
    // alan yoğunluğunu ~1/r yapar — additive birikim çekirdeği beyaza
    // doyurur, kenar kendiliğinden seyrelir. Üs 0.5 = eski alanca
    // eşdağılım; 1.0 eksene yoğun (üs sabiti bekçi testiyle kilitli).
    var PLUME_SPAWN_R_FRACTION = 0.75;
    var PLUME_SPAWN_EXPONENT = 1.0;
    function plumeSpawnRadius(exitRadius, u) {
        var uu = Math.max(0, Math.min(1, u));
        return exitRadius * PLUME_SPAWN_R_FRACTION
            * Math.pow(uu, PLUME_SPAWN_EXPONENT);
    }

    // --- Kalem 2: sıcaklık sürücülü renk ------------------------------
    // Parçacık sıcaklığı: çekirdek T = Te (çözücünün gerçek çıkış statik
    // sıcaklığı — readNozzleExit'te Tc'den izentropik türetilir), sonrası
    // MEVCUT soğuma modeliyle düşer: merkez hattı fazlalık sıcaklığı
    // ΔT ∝ 1/(x/D) (Pope §5.1 — plumeColorAt'ın 1/(1+3f) sönümüyle AYNI
    // eğri; renk ve parlaklık tek modelden sürülür). Ta = 300 K ortam.
    var FLAME_AMBIENT_K = 300;
    function flameTempAt(f, exitTempK) {
        var ff = Math.max(0, Math.min(1, f));
        return FLAME_AMBIENT_K + (exitTempK - FLAME_AMBIENT_K) / (1 + 3 * ff);
    }

    // Akkor renk yaklaşımı: yayılan ışık sıcaklıkla kızıl → turuncu →
    // sarı-beyaz → beyaz sırasını izler (Planck ışıması; görünür ışıma
    // Draper noktası ~798 K'de başlar). Kesin CIE dönüşümü yerine BEYANLI
    // parçalı doğrusal çapalar — sürücü GERÇEK sıcaklıktır, bantlar keyfi
    // yaş eşiği değil akkor sırasının nicelenmiş hali. 3300 K üstü doyar
    // (uç renk eski paletin beyaz-mavi çekirdeğiyle aynı: 1/1/1.05).
    var FLAME_COLOR_ANCHORS = [
        [800, 0.00, 0.00, 0.00],   // Draper noktası: ışıma eşiği
        [1100, 0.45, 0.03, 0.01],  // sönük derin kızıl
        [1600, 0.95, 0.22, 0.05],  // kızıl-turuncu
        [2100, 1.00, 0.55, 0.16],  // turuncu
        [2700, 1.00, 0.85, 0.50],  // sarı-beyaz
        [3300, 1.00, 1.00, 1.05]   // beyaza doyum (roket çekirdeği)
    ];
    function flameColorFromT(tK) {
        var a = FLAME_COLOR_ANCHORS;
        if (!isFinite(tK) || tK <= a[0][0]) return { r: 0, g: 0, b: 0 };
        var last = a[a.length - 1];
        if (tK >= last[0]) return { r: last[1], g: last[2], b: last[3] };
        for (var i = 1; i < a.length; i++) {
            if (tK <= a[i][0]) {
                var f = (tK - a[i - 1][0]) / (a[i][0] - a[i - 1][0]);
                return {
                    r: a[i - 1][1] + (a[i][1] - a[i - 1][1]) * f,
                    g: a[i - 1][2] + (a[i][2] - a[i - 1][2]) * f,
                    b: a[i - 1][3] + (a[i][3] - a[i - 1][3]) * f
                };
            }
        }
        return { r: last[1], g: last[2], b: last[3] };
    }

    // --- Kalem 3: çekirdek alev konisi --------------------------------
    // Prandtl-Meyer fonksiyonu ν(M) [derece] — standart gaz dinamiği:
    // ν = sqrt((γ+1)/(γ-1))·atan(sqrt((γ-1)/(γ+1)·(M²-1))) − atan(sqrt(M²-1))
    function prandtlMeyerDeg(mach, gamma) {
        if (!isFinite(mach) || mach <= 1 || !isFinite(gamma) || gamma <= 1) {
            return 0;
        }
        var k = Math.sqrt((gamma + 1) / (gamma - 1));
        var m2 = Math.sqrt(mach * mach - 1);
        return (k * Math.atan(m2 / k) - Math.atan(m2)) * 180 / Math.PI;
    }

    // Koni: çıkış düzleminde TAM re yarıçapıyla başlar (jet kesit
    // sürekliliği) ve gerçek ilk genleşme açısıyla açılır:
    //     θ_koni = θ_geo + [ν(Mj) − ν(Me)]
    // θ_geo lülenin gerçek diverjan/çıkış açısı; Me çözücünün çıkış
    // Mach'ı, Mj tam genişlemiş jet Mach'ı (readNozzleExit pe/pa'dan
    // hesaplar). Az genişlemiş jette dudaktaki basınç dengelenmesi akışı
    // Prandtl-Meyer yelpazesiyle ν(Mj)−ν(Me) kadar DIŞA döndürür; aşırı
    // genişlemişte Mj<Me → dönüş negatif, jet sınırı içeri büzülür.
    // Boy: süpersonik jet potansiyel çekirdeği ~6-10·De bandında (Lau,
    // Morris & Fisher, J. Fluid Mech. 93, 1979 ölçüm bandı) → 8·De alınır,
    // plume boy bütçesiyle sınırlanır. [-12°, 40°] kırpması ve 0.3·re
    // taban yarıçapı GÖRSEL emniyettir (bozuk uç veride sahne çökmesin),
    // fizik iddiası değildir.
    var PLUME_CORE_LEN_DE = 8;
    var FLAME_CONE_MIN_R_FRACTION = 0.3;
    function plumeConeSpec(exitRadius, thetaGeoDeg, exitMach, jetMach,
        gamma, maxLen) {
        if (!(exitRadius > 0) || !isFinite(thetaGeoDeg)) return null;
        var turn = prandtlMeyerDeg(jetMach, gamma)
            - prandtlMeyerDeg(exitMach, gamma);
        var half = Math.max(-12, Math.min(40, thetaGeoDeg + turn));
        var len = PLUME_CORE_LEN_DE * 2 * exitRadius;
        if (maxLen > 0) len = Math.min(len, maxLen);
        var r1 = exitRadius + Math.tan(half * Math.PI / 180) * len;
        r1 = Math.max(FLAME_CONE_MIN_R_FRACTION * exitRadius, r1);
        return {
            halfAngleDeg: half, turnDeg: turn,
            r0: exitRadius, r1: r1, lengthMm: len
        };
    }

    // Koninin verilen eksenel istasyondaki yerel yarıçapı — şok elması
    // sprite'ları jet sınırıyla hizalamak için (kalem 4).
    function coneRadiusAt(spec, distMm) {
        if (!spec || !(spec.lengthMm > 0)) return null;
        var t = Math.max(0, Math.min(1, distMm / spec.lengthMm));
        return spec.r0 + (spec.r1 - spec.r0) * t;
    }

    // --- Zemin ızgarası (kalem 5) -------------------------------------
    // Birim hücre YUVARLAK mutlak kademeden seçilir ve motorla ölçeklenmez:
    // sahnede mutlak uzunluk referansı verir. Eski hücre L/10'du (ölçülen
    // varsayılan tasarımda 167 mm) ve motorla birlikte ölçekleniyordu —
    // mutlak referans değeri yoktu. Kural: motor boyunun 1/20'sini aşmayan
    // en büyük kademe; çok küçük motorda 10 mm tabana düşülür.
    var GRID_CELL_STEPS_MM = [100, 50, 10];
    function gridCellMm(totalLen) {
        for (var i = 0; i < GRID_CELL_STEPS_MM.length; i++) {
            if (GRID_CELL_STEPS_MM[i] <= totalLen / 20) return GRID_CELL_STEPS_MM[i];
        }
        return GRID_CELL_STEPS_MM[GRID_CELL_STEPS_MM.length - 1];
    }
    // Izgara açıklığı ~3 motor boyu; hücrenin TAM katına yuvarlanır (kesik
    // kenar hücresi olmasın) ve çift hücre sayısı seçilir (merkez çizgisi
    // motor ekseniyle çakışsın).
    function gridSpanMm(totalLen, cellMm) {
        var cells = Math.max(8, Math.ceil((totalLen * 3) / cellMm));
        if (cells % 2) cells += 1;
        return cells * cellMm;
    }
    // Köşe rozeti metni: hücre boyu beyanı (gerçek seçilen değer yazılır)
    function gridBadgeText(cellMm) {
        return 'ızgara ' + cellMm + ' mm';
    }

    // --- Ölçü etiketleri (kalem 6-7) ----------------------------------
    // Rozet ölçeği boy VE çapla sınırlı: rozet yüksekliği = 0.62·scaleBase
    // ve 0.62·0.8 ≈ 0.50 → rozet motor dış çapının yarısını aşamaz. Eski
    // kural yalnız boya bağlıydı (L·0.055): L/D≈19,7 gövdede rozet çapın
    // %63'üne çıkıp modeli örtüyordu (ölçüldü 2026-08-03).
    function labelScaleBase(totalLen, outerDiameter) {
        return Math.min(totalLen * 0.055, outerDiameter * 0.8);
    }
    // Kılavuz çizgi payı yarıçapa oranlı; rozet yüksekliğinin (0.62·scale)
    // altına inmez ki metin gövdeye yapışmasın.
    function labelLeaderOffset(radius, scaleBase) {
        return Math.max(radius * 0.45, scaleBase * 0.62);
    }
    // Etiket metinleri (kalem 7): sahne dili TÜRKÇE'ye tekleştirildi —
    // canvas sprite UTF-8 çizer, 'ic/dis' ASCII kaçışının teknik gerekçesi
    // yoktu. GRAIN/CHAMBER İngilizce kalıntıları da Türkçeleşti: yakıt
    // çekirdeği boyu 'YAKIT', sıvı motorda yanma odası boyu 'ODA'.
    function dimensionLabelTexts(v) {
        var lgWord = v.motorType === 'liquid' ? 'ODA ' : 'YAKIT ';
        return {
            chamber: 'ØC iç ' + v.chamberInnerMm.toFixed(1) + ' / dış '
                + v.chamberOuterMm.toFixed(1) + ' mm',
            throat: 'ØT ' + v.throatMm.toFixed(1) + ' mm',
            exit: 'ØE ' + v.exitMm.toFixed(1) + ' mm',
            total: 'L ' + v.totalMm.toFixed(0) + ' mm  •  '
                + lgWord + v.grainMm.toFixed(0) + ' mm'
        };
    }

    // ==================================================================
    // CAD verisi saf fonksiyonları (2026-08-04, v2.6.27 — ikinci tur)
    //
    // Veri sözleşmesi (şablon adaptörleri passthrough geçirir; motor tarafı
    // yayımlama işi ayrı ajanda sürüyor — bu bloklar ÇOĞU yanıtta HENÜZ YOK):
    //   cooling_channels: { n_channels, channel_width_m, channel_height_m,
    //                       land_width_m, _basis }
    //   injector_pattern: { n_holes, hole_diameter_m, pattern_type
    //                       ('showerhead'|'impinging'|'swirl'),
    //                       impingement_angle_deg?, n_rings?, _basis }
    //   nozzle_contour:   { points: [[z_m, r_m], ...], _basis }
    //
    // Kural (sahte veri yasağı): veri VARSA gerçek geometri çizilir; YOKSA
    // hiçbir şey çizilmez ve durum çipi bunu açıkça beyan eder. Bilinmeyen
    // ya da bozuk şekilli blok = veri yok sayılır (savunmacı okuma).
    // Bekçi testleri: tests/test_viz3d_cad_kipi.py (node ile izole sınama).
    // ==================================================================

    // --- i18n köprüsü (sahne metinleri) --------------------------------
    // Sahne çipleri DOM değil canvas sprite'tır; data-i18n uygulanamaz,
    // metin üretim anında çözülür. Anahtar sözlükte yoksa I18N.t
    // fallback'i (İNGİLİZCE tam metin) döner — anahtar adı ekrana ASLA
    // yazılmaz. Dil değişiminde çipler yeniden kurulur ('hrma:langchange'
    // dinleyicisi, güverte deseniyle aynı).
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }

    // --- Kaynak-renk eşlemesi (tasarım dili) ---------------------------
    // Sahnedeki her çip/rozet rengi verinin GERÇEK kaynağına bağlıdır;
    // keyfî süs rengi yok (B4 kaynak-renklendirmenin temeli):
    //   computed = çözücü hesapladı (camgöbeği)
    //   user     = kullanıcı girdisi (beyaz)
    //   assumed  = varsayım / yerel üretim (amber)
    //   missing  = modellenmedi / veri yok (gri)
    var SOURCE_COLORS = {
        computed: '#39d6ec',
        user: '#e8edf2',
        assumed: '#ffb347',
        missing: '#8a93a0'
    };

    function sourceColor(kind) {
        return SOURCE_COLORS[kind] || SOURCE_COLORS.missing;
    }

    // --- B1: soğutma kanalları (sahte 8 bilezik söküldü) --------------
    // Eski kod her sıvı motora, veriden bağımsız 8 dekoratif çevresel
    // "soğutma bileziği" çiziyordu. Gerçek rejeneratif kanallar EKSENELDİR;
    // sayı ve kesit ölçüleri çözücünün cooling_channels bloğundan okunur.
    // Blok yoksa ya da bozuksa null döner — hiçbir kanal çizilmez.
    function coolingChannelSpec(md) {
        var cc = md && md.cooling_channels;
        if (!cc || typeof cc !== 'object') return null;
        var n = num(cc.n_channels, 0);
        var w = num(cc.channel_width_m, NaN) * 1000;
        var h = num(cc.channel_height_m, NaN) * 1000;
        var land = num(cc.land_width_m, NaN) * 1000;
        if (!(n >= 1) || !isFinite(w) || w <= 0 || !isFinite(h) || h <= 0) {
            return null;
        }
        return {
            nChannels: Math.round(n),
            widthMm: w,
            heightMm: h,
            landMm: (isFinite(land) && land > 0) ? land : null,
            basis: cc._basis || null
        };
    }

    // Kanal yerleşimi: n kanal çevreye eşit açıyla dizilir. Spec null ise
    // BOŞ liste döner (0 kanal) — uydurma kanal yasak.
    function coolingChannelLayout(spec) {
        if (!spec) return [];
        var out = [];
        for (var i = 0; i < spec.nChannels; i++) {
            out.push({
                phi: (i / spec.nChannels) * TAU,
                widthMm: spec.widthMm,
                heightMm: spec.heightMm
            });
        }
        return out;
    }

    // --- B2: enjektör deseni derinliği --------------------------------
    // injector_pattern bloğu yoksa null döner ve sahnede HİÇBİR ek desen
    // grafiği çizilmez (mevcut delik deseni davranışı aynen korunur —
    // o zaten injector_results/injector_design gerçek kaynağından gelir).
    function readInjectorPattern(md) {
        var ip = md && md.injector_pattern;
        if (!ip || typeof ip !== 'object') return null;
        var n = num(ip.n_holes, 0);
        var type = String(ip.pattern_type || '').toLowerCase();
        if (!(n >= 1) || !type) return null;
        var dia = num(ip.hole_diameter_m, NaN) * 1000;
        var ang = num(ip.impingement_angle_deg, NaN);
        var rings = num(ip.n_rings, 0);
        return {
            nHoles: Math.round(n),
            holeDiaMm: (isFinite(dia) && dia > 0) ? dia : null,
            patternType: type,
            // Sözleşme iki jet ARASINDAKİ tam açıyı verir; çizim yarım
            // açıyla çalışır (extractDims'teki impingement_angle_deg / 2
            // geleneğiyle aynı).
            impingeHalfDeg: (isFinite(ang) && ang > 0) ? ang / 2 : null,
            nRings: (rings >= 1) ? Math.round(rings) : null,
            basis: ip._basis || null
        };
    }

    // Çarpışma istasyonu: enjektör yüzünden r yarıçapında çıkan, eksene
    // doğru yarım açı θ ile eğik jet, itki eksenini z = r / tan(θ)
    // istasyonunda keser (düz geometri — uydurma katsayı yok). Geçersiz
    // girdi null döner ve çizgi çizilmez.
    function impingementApexZ(ringRadiusMm, halfAngleDeg) {
        var a = clamp(num(halfAngleDeg, NaN), 5, 85);
        if (!isFinite(a) || !(ringRadiusMm > 0)) return null;
        return ringRadiusMm / Math.tan(a * Math.PI / 180);
    }

    // --- B3: lüle konturu tek kaynaktan -------------------------------
    // Çözücü örneklenmiş konturu (points, metre cinsinden [z, r] çiftleri)
    // yayımladıysa iç kontur ORADAN okunur; yoksa yerel üretim sürer ve
    // sahne bunu 'kontur: yerel üretim' çipiyle beyan eder (kaynak
    // şeffaflığı). Bozuk nokta (NaN, negatif yarıçap, artmayan z) görülen
    // dizi bütünüyle reddedilir — yarım gerçek kontur çizilmez.
    function selectNozzleContour(contour) {
        var pts = contour && contour.points;
        if (Array.isArray(pts) && pts.length >= 3) {
            var out = [];
            for (var i = 0; i < pts.length; i++) {
                var p = pts[i];
                var z = num(p && p[0], NaN) * 1000;
                var r = num(p && p[1], NaN) * 1000;
                if (!isFinite(z) || !isFinite(r) || r < 0
                    || (out.length && z <= out[out.length - 1].z)) {
                    out = null;
                    break;
                }
                out.push({ z: z, r: r });
            }
            if (out) {
                return {
                    source: 'solver',
                    points: out,
                    basis: (contour && contour._basis) || null
                };
            }
        }
        return { source: 'local', points: null, basis: null };
    }

    // --- CAD kipi: ortografik görünüş preset'leri (kalem 4a) ----------
    // Teknik resim görünüşleri; bakış yönleri DÜNYA uzayında (motor ekseni
    // dünya +X). 'front' yan profili (alın görünüş), 'top' üstten, 'side'
    // eksen boyu görünüşü, 'iso' izometrik verir. Frustum yarı boyutları
    // sınırlayıcı kutunun izdüşümünden türer, viewport en-boy oranına
    // oturtulur — kutu her presette tam kadraj içinde kalır.
    var ORTHO_MARGIN = 1.08;
    var ORTHO_PRESETS = {
        front: { x: 0, y: 0, z: 1 },
        top: { x: 0, y: 1, z: 0 },
        side: { x: 1, y: 0, z: 0 },
        iso: { x: 1, y: 1, z: 1 }
    };

    function orthoPresetFrustum(name, halfLen, maxRadius, aspect) {
        var raw = ORTHO_PRESETS[name] || ORTHO_PRESETS.iso;
        var n = Math.sqrt(raw.x * raw.x + raw.y * raw.y + raw.z * raw.z);
        var d = { x: raw.x / n, y: raw.y / n, z: raw.z / n };
        // Üstten bakışta up=+Y bakış yönüyle paralel kalır; teknik resim
        // kuralı: üst görünüşte motor ekseni ekranda yatay yatar → up = -Z
        var up = (Math.abs(d.y) > 0.99)
            ? { x: 0, y: 0, z: -1 } : { x: 0, y: 1, z: 0 };
        // Kamera eksenleri: xAxis = normalize(up × d), yAxis = d × xAxis
        var cxv = up.y * d.z - up.z * d.y;
        var cyv = up.z * d.x - up.x * d.z;
        var czv = up.x * d.y - up.y * d.x;
        var cn = Math.sqrt(cxv * cxv + cyv * cyv + czv * czv);
        var xAxis = { x: cxv / cn, y: cyv / cn, z: czv / cn };
        var yAxis = {
            x: d.y * xAxis.z - d.z * xAxis.y,
            y: d.z * xAxis.x - d.x * xAxis.z,
            z: d.x * xAxis.y - d.y * xAxis.x
        };
        var halfW = 0, halfH = 0, sx, sy, sz, px, py, p;
        for (sx = -1; sx <= 1; sx += 2)
            for (sy = -1; sy <= 1; sy += 2)
                for (sz = -1; sz <= 1; sz += 2) {
                    p = { x: sx * halfLen, y: sy * maxRadius, z: sz * maxRadius };
                    px = p.x * xAxis.x + p.y * xAxis.y + p.z * xAxis.z;
                    py = p.x * yAxis.x + p.y * yAxis.y + p.z * yAxis.z;
                    halfW = Math.max(halfW, Math.abs(px));
                    halfH = Math.max(halfH, Math.abs(py));
                }
        halfW *= ORTHO_MARGIN;
        halfH *= ORTHO_MARGIN;
        // Viewport en-boy oranına oturt: kısıtlayıcı ekseni koru, diğerini aç
        var a = Math.max(aspect || 1, 0.2);
        if (halfW / halfH < a) halfW = halfH * a; else halfH = halfW / a;
        return {
            dir: d, up: up, halfW: halfW, halfH: halfH,
            dist: 2.5 * (halfLen + maxRadius)
        };
    }

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

    // Alev parçacık dokusu (kalem 1a): flameSpriteStops'un Gauss profili
    // NÖTR beyaz alfa rampası olarak çizilir — ton TAMAMEN vertex renginden
    // (plumeColorAt → gerçek sıcaklık sürücüsü) gelir; dokuya gömülü keyfi
    // turuncu yok (eski glowTexture çifti egzozdan çıkarıldı). 128 px:
    // glowTexture ile aynı doku bütçesi (kalem 5).
    function flameSpriteTexture() {
        var c = makeCanvas(128, 128);
        var g = c.getContext('2d');
        var grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
        var stops = flameSpriteStops(9);
        for (var i = 0; i < stops.length; i++) {
            grad.addColorStop(stops[i].t,
                'rgba(255,255,255,' + stops[i].alpha.toFixed(4) + ')');
        }
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

    // Prosedürel ortam haritası (görev 2): 6 küçük canvas'tan CubeTexture —
    // üstte soğuk gri-mavi degrade (stüdyo tavan ışığı), altta koyu zemin,
    // yan yüzlerde ufuk bandı. scene.environment'a atanır; r128'de
    // MeshStandardMaterial'lar envMap'i buradan otomatik alır.
    function makeEnvCubeTexture() {
        var S = 64;
        function face(draw) {
            var c = makeCanvas(S, S);
            draw(c.getContext('2d'));
            return c;
        }
        function sideFace() {
            // Ufuk bandı: üstte gökyüzü grisi, ortada parlak bant, altta koyu
            return face(function (g) {
                var gr = g.createLinearGradient(0, 0, 0, S);
                gr.addColorStop(0.0, '#46586e');
                gr.addColorStop(0.46, '#7c8ea2');
                gr.addColorStop(0.54, '#232c38');
                gr.addColorStop(1.0, '#0b0f15');
                g.fillStyle = gr;
                g.fillRect(0, 0, S, S);
            });
        }
        var top = face(function (g) {
            var gr = g.createLinearGradient(0, 0, 0, S);
            gr.addColorStop(0, '#9db2c9');
            gr.addColorStop(1, '#54677d');
            g.fillStyle = gr;
            g.fillRect(0, 0, S, S);
        });
        var bottom = face(function (g) {
            g.fillStyle = '#0a0d12';
            g.fillRect(0, 0, S, S);
        });
        // Yüz sırası: +X, -X, +Y (üst), -Y (alt), +Z, -Z
        var tex = new THREE.CubeTexture([
            sideFace(), sideFace(), top, bottom, sideFace(), sideFace()
        ]);
        tex.encoding = THREE.sRGBEncoding;   // canvas renkleri sRGB uzayında
        tex.needsUpdate = true;
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
        // Ölçü etiketleri HUD niteliğinde: gövdenin arkasında kaybolmasın;
        // ton eşleme dışı tutulur (ACES filmik eğri HUD metnini soldurmasın)
        var mat = new THREE.SpriteMaterial({
            map: tex, transparent: true, depthWrite: false, depthTest: false,
            toneMapped: false
        });
        var sp = new THREE.Sprite(mat);
        sp.renderOrder = 10;
        sp.userData.aspect = w / h;
        return sp;
    }

    // Durum çipi: mevcut rozet kalıbı (textSprite) + kaynak-renk eşlemesi.
    // Metin rengi ve çerçeve SOURCE_COLORS tablosundan gelir — çipin rengi
    // verinin gerçek kaynağını beyan eder (tasarım dili, B4 temeli).
    function statusChip(text, kind) {
        var col = sourceColor(kind);
        return textSprite(text, { color: col, border: col });
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

    // ------------------------------------------------------------------
    // Enjektör kaynağı — sunucudaki _injector_spec ile AYNI kural (v2.6.26)
    // ------------------------------------------------------------------
    //
    // Hibrit /calculate İKİ bağımsız enjektör çözücüsü koşturur:
    //   1) enjektör paneli  -> injector_results  (ekran tablosu + 2B şema)
    //   2) motorun devre modeli -> injector_design (N2O'da doyma basıncı)
    // Ölçüldü (K2 denetimi): aynı koşuda panel 125 delik x 0,957 mm derken bu
    // modül injector_design'ı okuyup 11 delik x 2,457 mm çiziyordu — enjeksiyon
    // alanı 1,9 kat farklı. Kullanıcı ekranda bir enjektör görüp 3B modelde
    // BAŞKA bir enjektör görüyordu.
    //
    // Kural: bir kaynak seçilir ve BÜTÜN alanlar o kaynaktan okunur. Panelde
    // olmayan alan diğer çözücüden ödünç ALINMAZ (melez spesifikasyon
    // hiçbir çözücüde var olmayan bir parçadır).
    function resolveInjectorSource(md) {
        var panel = (md && md.injector_results) || null;
        if (panel && Object.keys(panel).length) {
            return {
                data: panel,
                nOrifices: num(panel.number_of_orifices,
                    num(panel.n_holes, num(panel.n_elements, null))),
                orificeMm: num(panel.orifice_diameter_mm,
                    num(panel.hole_diameter, num(panel.orifice_diameter, null))),
                source: 'injector_results'
            };
        }
        var inj = (md && md.injector_design) || {};
        return {
            data: inj,
            nOrifices: num(inj.number_of_orifices,
                num(inj.n_holes, num(inj.n_elements, null))),
            orificeMm: num(inj.orifice_diameter_mm,
                num(inj.hole_diameter, null)),
            source: 'injector_design'
        };
    }

    // ------------------------------------------------------------------
    // Kamara cidarı — sunucudaki _chamber_wall_design ile AYNI kural
    // ------------------------------------------------------------------
    //
    // v2.6.26 (Y5): burası her zaman yapısal analizin ÖNERDİĞİ kalınlığı
    // çiziyordu. Ölçüldü: kullanıcı 3 / 5 / 10 / 20 mm girse de model 15,92 mm
    // gösteriyordu; Alüminyum 6061'de 49,92 mm cidar çizerken yapısal panel
    // kullanıcının 5 mm'si için "güvensiz" diyordu — yani ekrandaki emniyet
    // katsayısı çizilen parçaya ait değildi.
    //
    // Kural: gerilmelerin hesaplandığı kalınlık çizilir. 'verify' modunda bu
    // kullanıcının cidarıdır; 'size' modunda zaten önerilen kalınlığa eşittir.
    // Üç motor tipinin üç ayrı yapısal şeması — sunucudaki
    // cad_visualization.CHAMBER_WALL_SCHEMAS tablosunun BİREBİR eşi.
    // [blok, as-designed alanı, önerilen alanı, as-designed kesin mi]
    // Faz 6 / T06: burada yalnız hibrit şeması (chamber_analysis) vardı;
    // katı (case_analysis) ve sıvı (chamber_structure) motorlarda anahtar
    // tutmuyor, güverte 0,045·D geometrik yedeğine düşüyordu.
    var CASING_WALL_SCHEMAS = [
        ['chamber_analysis', 'wall_thickness_used_mm', 'recommended_thickness', false],
        ['case_analysis', 'wall_thickness_mm', 'recommended_wall_thickness_mm', true],
        ['chamber_structure', 'wall_thickness', 'required_wall_thickness', true]
    ];

    function resolveCasingWall(md, Dch) {
        var struct = (md && md.structural_analysis) || {};
        for (var i = 0; i < CASING_WALL_SCHEMAS.length; i++) {
            var s = CASING_WALL_SCHEMAS[i];
            var blk = struct[s[0]];
            if (!blk || typeof blk !== 'object') continue;
            var used = num(blk[s[1]], null);
            var recommended = num(blk[s[2]], null);
            if (used === null && recommended === null) continue;
            // Gerilmelerin hesaplandığı kalınlık çizilir: 'verify' modunda
            // (ya da as-designed alanı kesin olan şemalarda) kullanıcının
            // cidarı, aksi hâlde yapısal önerinin kendisi.
            if ((blk.design_mode === 'verify' || s[3]) && used !== null && used > 0) return used;
            if (recommended !== null && recommended > 0) return recommended;
            if (used !== null && used > 0) return used;
        }
        // Yapısal sonuç yok: sunucu tarafındaki AYNI geometrik yedek kural
        // (CHAMBER_WALL_FALLBACK_FRACTION = 0.045) — mesh ile çelişmesin.
        return Math.max(4, 0.045 * Dch);
    }

    // ------------------------------------------------------------------
    // Nozul çıkış durumu — SAHTE PLUME SÖKÜMÜ (v2.6.26)
    // ------------------------------------------------------------------
    //
    // Egzoz gösterimi çözücünün gerçek çıkış büyüklüklerini KULLANMIYORDU.
    // Uydurma olanlar ve gerçekleri:
    //
    //   parçacık hızı  = toplam_uzunluk x (2.2 + rastgele x 1.6)
    //                    -> gerçeği: nozul çıkış hızı [m/s], çözücüde var
    //   pe/pa          = (8 / eps)^1.15   (8 ve 1.15 havadan)
    //                    -> gerçeği: çıkış basıncı / ortam basıncı, çözücüde var
    //   şok aralığı    = de x (0.7 + 0.5 x sqrt(eps/8))
    //                    -> gerçeği: Prandtl-Pack bağıntısı (aşağıda)
    //
    // Parçacığın çıkış kesitinde rastgele DAĞITILMASI sahtelik değildir:
    // sürekli bir akışı ayrık noktalarla çizmenin doğru yoludur. Sahte olan,
    // hesaplanabilir bir değerin yerine rastgele sayı koymaktı.
    //
    // Değerler yoksa null döner ve plume HİÇ çizilmez — uydurma alev yasak.
    function readNozzleExit(md) {
        md = md || {};
        var nozzle = md.nozzle_design || {};
        var perf = nozzle.performance || {};
        var comb = md.combustion_analysis || {};
        var comp = (comb.compositions && comb.compositions.chamber) || {};

        var pe = num(perf.exit_pressure, NaN);          // bar
        var pa = num(perf.ambient_pressure, NaN);       // bar
        var me = num(perf.exit_mach, NaN);
        var gamma = num(comp.gamma, num(md.gamma, NaN));
        var tc = num(md.chamber_temperature, NaN);      // K

        // Çıkış hızı: irtifa performansı dizisinin deniz seviyesi girdisi.
        var ve = NaN;
        var alt = md.altitude_performance && md.altitude_performance.altitude_performance;
        if (Array.isArray(alt) && alt.length) ve = num(alt[0].exit_velocity, NaN);
        if (!isFinite(ve)) ve = num(perf.exit_velocity, NaN);

        if (!isFinite(pe) || !isFinite(pa) || !isFinite(me) || !isFinite(gamma)
            || !isFinite(ve) || pe <= 0 || pa <= 0 || me <= 1 || ve <= 0) {
            return null;
        }

        var pRatio = pe / pa;

        // Çıkış statik sıcaklığı — izentropik: Te = Tc / (1 + (g-1)/2 * Me^2)
        var te = isFinite(tc)
            ? tc / (1 + 0.5 * (gamma - 1) * me * me)
            : NaN;

        // Tam genişlemiş eşdeğer jet Mach sayısı: akış pa basıncına kadar
        // izentropik genişleseydi ulaşacağı Mach. Aşırı-genişlemiş jette
        // (pe < pa) Mj < Me olur.
        var mj = me;
        var arg = 1 + (2 / (gamma - 1)) * (Math.pow(pRatio, (gamma - 1) / gamma)
            * (1 + 0.5 * (gamma - 1) * me * me) - 1);
        if (isFinite(arg) && arg > 1) mj = Math.sqrt(arg);

        // Şok hücre aralığı — Prandtl-Pack bağıntısı:
        //     L_s = 1.306 * D_j * sqrt(Mj^2 - 1)
        // Kaynak: Prandtl (1904); Pack, Q. J. Mech. Appl. Math. 3 (1950).
        // Jet aeroakustiğinde yaygın olarak doğrulanmıştır. Mj <= 1 ise
        // hücre yapısı oluşmaz (tam genişlemiş/ses altı jet).
        var cellSpacing = (mj > 1.02)
            ? 1.306 * num(md.exit_diameter, 0) * 1000 * Math.sqrt(mj * mj - 1)
            : 0;

        return {
            exitPressureBar: pe,
            ambientPressureBar: pa,
            pressureRatio: pRatio,
            exitMach: me,
            jetMach: mj,
            exitVelocity: ve,          // m/s
            exitTemperature: te,       // K (Tc yoksa NaN)
            gamma: gamma,
            cellSpacingMm: cellSpacing,
            // pe > pa: az genişlemiş (jet çıkışta genişler, elmaslar belirgin)
            // pe < pa: aşırı genişlemiş (jet büzülür, şok içeri girer)
            expansionState: (pRatio > 1.05) ? 'under'
                : (pRatio < 0.95) ? 'over' : 'ideal'
        };
    }

    function extractDims(md) {
        md = md || {};
        var gd = md.grain_design || {};
        var injSrc = resolveInjectorSource(md);
        var inj = injSrc.data;
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

        // Kullanıcının tasarladığı cidar çizilir; 0.12·D üst kırpması
        // kaldırıldı (kullanıcının kalınlığını sessizce değiştiriyordu).
        var casingWall = Math.max(0.2, resolveCasingWall(md, Dch));
        var nozzleWall = clamp(num(md.nozzle_geometry && md.nozzle_geometry.wall_thickness, Math.max(3, 0.1 * dt)), 2.5, 0.25 * dt + 6);
        // Grain dış yarıçapı çözücünün BEYAN ETTİĞİ çaptan okunur; liner
        // (yalıtım + boşluk) bu çapla kasa deliği arasındaki farktan ÇIKAR.
        // Faz 6 / T06: eski kod liner'i clamp(0.02*Dch, 1.5, 5) diye
        // uyduruyor, grain dışını da rc - liner sanıyordu. Ölçüldü
        // (/calculate_solid): yalıtım 0 / 0,5 / 3 / 20 mm iken kasa deliği
        // 100 / 101 / 106 / 140 mm, grain 100 mm'de sabit — fark
        // kullanıcının yalıtımını birebir verir.
        var dGrainOut = num(gd.outer_diameter_mm, num(gd.grain_outer_diameter_mm, NaN));
        var rGrainOut, liner;
        if (isFinite(dGrainOut) && dGrainOut > 0 && dGrainOut / 2 <= rc + 1e-9) {
            rGrainOut = Math.min(dGrainOut / 2, rc);
            liner = Math.max(0, rc - rGrainOut);
        } else {
            liner = clamp(0.02 * Dch, 1.5, 5);
            rGrainOut = rc - liner;
        }

        // T10: grain boyu ARTIK KIRPILMIYOR. Ölçüldü (hibrit varsayılan
        // koşu): çözücü 1511,6 mm derken güverte künyesi 'GRAIN 1451 mm'
        // yazıyordu (0,92 x 1575,5 mm oda boyu) — 2B kesitle aynı %4,1'lik
        // sessiz kısaltma. Yakıt kütlesiyle çapraz doğrulandı: raporun
        // yazdığı 1,54 kg ancak 1512,8 mm ile çıkıyor.
        var Lg = num(gd.grain_length_mm, num(md.grain_length, 0.8 * Lch / 1000) * 1000);
        var rPort0 = num(gd.port_diameter_initial_mm, num(md.port_diameter_initial, 0.03) * 1000) / 2;
        rPort0 = Math.min(rPort0, rGrainOut);
        // NOT: ``rPortF`` (bitiş port yarıçapı) KALDIRILDI (v2.6.27, B5).
        // Tek kullanıcısı, seri yokken portu sqrt yasasıyla ilerleten sahte
        // ara değerlemeydi; animasyon artık yalnız gerçek seriyle sürülür.

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

        // B3 (v2.6.27): çözücü örneklenmiş konturu yayımladıysa TEK KAYNAK
        // odur — boğaz istasyonu (Lc) ve diverjan boyu (Ld) da konturun
        // kendisinden türer ki boğaz alevi, grafit insert ve ölçü okları
        // çizilen geometriyle aynı yerde dursun.
        var contourSel = selectNozzleContour(contour);
        if (contourSel.points) {
            var cpts = contourSel.points;
            var iThroat = 0;
            for (var ct = 1; ct < cpts.length; ct++) {
                if (cpts[ct].r < cpts[iThroat].r) iThroat = ct;
            }
            Lc = cpts[iThroat].z - cpts[0].z;
            Ld = cpts[cpts.length - 1].z - cpts[iThroat].z;
        }

        var capT = clamp(1.6 * casingWall, 8, 0.3 * rc + 8);
        var flangeT = clamp(0.8 * capT, 6, 26);
        var flangeLip = clamp(0.10 * rc, 4, 18);

        // Grain kamara içindeki yeri: çözücü ön/arka oda boyunu yayımlıyorsa
        // O kullanılır (ölçüldü: 39,911 + 1511,596 + 23,946 = 1575,452 mm =
        // chamber_length, bit-aynı); yoksa eski %35/%65 payı korunur.
        var preCh = num(md.pre_chamber_length, NaN) * 1000;
        var zg0;
        if (isFinite(preCh) && preCh >= 0 && preCh + Lg <= Lch + 1e-6) {
            zg0 = preCh;
        } else {
            zg0 = 0.35 * Math.max(0, Lch - Lg);
        }
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
            rPort0: rPort0, rGrainOut: rGrainOut,
            nozType: nozType, Lc: Lc, Ld: Ld,
            thetaN: thetaN, thetaE: thetaE, halfAngle: halfAngle,
            Rn: Rn, Rconv: Rconv,
            capT: capT, flangeT: flangeT, flangeLip: flangeLip,
            inletR: clamp(0.22 * rc, 5, 22),
            inletL: clamp(1.6 * capT, 14, 60),
            // v2.6.26: UYDURMA DELİK DESENİ YASAK. Eski kod veri yokken
            // 12 delik x 1,5 mm çiziyor, üstelik Math.max(4, ...) yüzünden
            // çözücünün 3 deliğini 4 gösteriyordu. Sayı ya da çap yoksa
            // nOrifices = 0 kalır ve enjektör yüzüne HİÇBİR delik çizilmez.
            nOrifices: ((injSrc.nOrifices > 0 && injSrc.orificeMm > 0)
                ? Math.round(injSrc.nOrifices) : 0),
            orificeR: ((injSrc.orificeMm > 0) ? injSrc.orificeMm / 2 : 0),
            injectorSource: injSrc.source,
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
            // v2.6.26 — SAHTE PLUME SÖKÜMÜ: egzoz gösterimi çözücünün gerçek
            // nozul çıkış büyüklüklerini KULLANMIYORDU; parçacık hızı, pe/pa
            // oranı ve şok elması aralığı uydurma sabitlerden geliyordu.
            // Bu değerler çözücüde ZATEN hesaplanıyor; aşağıda okunuyorlar.
            // Yoksa null kalır ve plume HİÇ çizilmez (uydurma alev yasak).
            nozzleExit: readNozzleExit(md),
            // v2.6.27 CAD veri sözleşmesi (savunmacı okuma): bloklar çoğu
            // yanıtta henüz yok — yoksa null/[] kalır ve HİÇBİR şey çizilmez,
            // durum çipi 'veri yok' beyan eder (sahte veri yasağı).
            cooling: coolingChannelSpec(md),
            injPattern: readInjectorPattern(md),
            contourPoints: contourSel.points,
            contourSource: contourSel.source,
            contourBasis: contourSel.basis,
            of0: num(md.of_ratio_initial, num(md.of_ratio, 2)),
            portHist: md.port_history || null,
            // Katı yolu: web geçmişi çözücünün itki eğrisinden türetilir
            // (solidWebHistory; veri yoksa null → port donuk kalır).
            webHist: solidWebHistory(md),
            grainType: (gd.grain_type || md.grain_type || ''),
            // Çözücü uç yüzeylerin de yandığını beyan ediyor mu? BATES'te
            // 'outer_surface' inhibisyonu = dış yüzey kapalı, uçlar yanıyor.
            endsBurn: (String(gd.inhibitor_config || '').toLowerCase() === 'outer_surface'),
            ofShift: md.of_shift_performance || null,
            heat: heat
        };
    }

    // ==================================================================
    // Tane yanma animasyonu — port gerilemesi (v2.6.27, B5)
    //
    // SAHTE ANİMASYON YASAĞI: iç yüzey YALNIZ gerçek çözücü serisiyle
    // gerilir. İki gerçek kaynak vardır, üçüncüsü YOKTUR:
    //
    //  1) hibrit — motor sözlüğü ``port_history`` yayımlar
    //     ({time[s], port_diameter[m]}); doğrudan örneklenir.
    //
    //  2) katı — çözücü web ilerlemesini zaman marşında TUTAR ama
    //     YAYIMLAMAZ. Ölçüldü (2026-08-15, /calculate_solid
    //     use_tutorial_defaults): yanıttaki thrust_curve yalnız
    //     time / thrust / pressure / burn_area / mass_flow taşır (402
    //     nokta); motorun kendi eğri sözlüğündeki ``port_area`` dizisi
    //     _published_thrust_curve'de dışarı verilmez. Web geçmişi bu
    //     yüzden çözücünün KENDİ kütle üretim özdeşliğinden geri alınır:
    //
    //         ṁ(t) = ρ_p · A_b(t) · r_b(t)   (solid_rocket_engine.py:8420)
    //      →  r_b(t) = ṁ(t) / (ρ_p · A_b(t))
    //      →  w(t)   = ∫ r_b dt               (trapez)
    //
    //     Üç dizinin üçü de çözücü çıktısıdır ve erozif yanma artışı
    //     ṁ'nin İÇİNDE zaten vardır. Bu bir regresyon yasası UYDURMASI
    //     değildir; doğrulanabilir bir özdeşliğin tersidir:
    //       - w(t_son) = 34,980 mm iken çözücünün beyan ettiği
    //         web_burnout_mm = 35,0 (%0,057; kalan pay yayımlanan
    //         dizinin 487→402 seyreltmesi),
    //       - bu w ile BATES yanma alanı geri kurulunca yayımlanan
    //         burn_area'ya ort %0,043 / maks %0,29 oturuyor.
    //
    // SÖKÜLEN SAHTELİK: burada, seri yokken, port yarıçapını
    // ``sqrt(lerp(r0², rF², t/t_b))`` ile ilerleten bir ara değerleme
    // vardı. Ne zaman yasası (sabit hacimsel üretim) ne de bitiş noktası
    // çözücüden geliyordu — katı sayfası rF'yi 0,9·D_dış diye ÜRETİYORDU
    // (solid.html, "yanma sonunda ince bir kabuk görünsün diye"). Artık
    // gerçek seri yoksa port DONDURULUR ve durum çipi bunu beyan eder.
    // ==================================================================

    // Katı çözücünün itki eğrisinden web ilerlemesi (m). Girdi eksik,
    // kısa, tutarsız uzunlukta ya da sayısal değilse null döner — yarım
    // veriden seri UYDURULMAZ.
    function solidWebHistory(md) {
        var tc = (md && md.thrust_curve) || null;
        if (!tc) return null;
        var t = tc.time, ab = tc.burn_area, mdot = tc.mass_flow;
        if (!t || !ab || !mdot) return null;
        var n = t.length;
        if (n < 3 || ab.length !== n || mdot.length !== n) return null;
        // Yakıt yoğunluğu (kg/m³) — özdeşliğin üçüncü çarpanı. Yoksa
        // türetme YAPILMAZ (rho'yu varsaymak sahte seri üretmek olurdu).
        var rho = num(md.propellant_density, num(md.density, NaN));
        if (!(rho > 0)) return null;
        var web = new Array(n);
        var w = 0, rPrev = 0, tPrev = 0, ilerledi = false;
        for (var i = 0; i < n; i++) {
            var ti = num(t[i], NaN), A = num(ab[i], NaN), m = num(mdot[i], NaN);
            if (!isFinite(ti) || !isFinite(A) || !isFinite(m) || A < 0 || m < 0) return null;
            var rb = (A > 0) ? m / (rho * A) : 0;
            if (i > 0) {
                var dt = ti - tPrev;
                if (dt < 0) return null;              // sıralı olmayan seri
                w += 0.5 * (rPrev + rb) * dt;
                if (w > 0) ilerledi = true;
            }
            web[i] = w;
            rPrev = rb;
            tPrev = ti;
        }
        if (!ilerledi) return null;
        return { time: t, web: web, webEnd: w, source: 'solid_mass_balance' };
    }

    // Radyal (dairesel port) gerilemenin ANLAMLI olduğu tane tipleri.
    // Yıldız/finocyl/çok portlu kesitte web ilerlemesi yüzey normali
    // boyunca ofsettir (çözücü Huygens/shapely ofseti kullanır), uç
    // yanmalı tanede ise gerileme EKSENELDİR — ikisini de tek bir
    // yarıçapı büyüterek göstermek uydurma olur.
    var RADIAL_REGRESSION_GRAINS = { bates: true, cylindrical: true, circular: true };

    // Port gerilemesinin kipi (tek karar noktası; çip metni de bundan).
    //   'port_history'        çözücü port çapı geçmişi yayımladı
    //   'solid_mass_balance'  katı çözücünün kütle dengesinden türetildi
    //   'not_modelled'        kesit/tane tipi için radyal gerileme geçersiz
    //   'no_data'             gerçek zaman serisi yok → port donuk
    function portRegressionMode(spec) {
        spec = spec || {};
        if ((spec.portShape || 'circular') !== 'circular') return 'not_modelled';
        // Çözücü yarıçapı KENDİSİ verdiyse tane tipi tartışması yoktur.
        if (spec.hasPortHistory) return 'port_history';
        var gt = String(spec.grainType || '').toLowerCase();
        if (gt && !RADIAL_REGRESSION_GRAINS[gt]) return 'not_modelled';
        if (spec.hasWebHistory) return 'solid_mass_balance';
        return 'no_data';
    }

    // Kipin durum çipleri. Çip BEYANDIR: animasyonun neyden sürüldüğünü
    // (ya da sürülmediğini) kullanıcıya söyler.
    function portRegressionChipDefs(mode, opts) {
        opts = opts || {};
        var defs = [];
        if (mode === 'port_history') {
            defs.push({ text: T('viz.chip.portRegHistory',
                'port regression: solver port history'), kind: 'computed' });
        } else if (mode === 'solid_mass_balance') {
            defs.push({ text: T('viz.chip.portRegMassBalance',
                'port regression: solver mass balance'), kind: 'computed' });
        } else if (mode === 'not_modelled') {
            defs.push({ text: T('viz.chip.portRegNotModelled',
                'port regression: not modelled for this grain'), kind: 'missing' });
        } else {
            defs.push({ text: T('viz.chip.portRegNoData',
                'port regression: no solver series'), kind: 'missing' });
        }
        // Uç yüzeyler de yanıyorsa (çözücü beyanı) 3B tane bloğu eksenel
        // kısalmayı GÖSTERMEZ; sessiz kalınmaz, ayrı çiple beyan edilir.
        if (opts.endsBurn && (mode === 'port_history' || mode === 'solid_mass_balance')) {
            defs.push({ text: T('viz.chip.endFaceNotModelled',
                'end-face regression: not modelled'), kind: 'missing' });
        }
        return defs;
    }

    // t anındaki port yarıçapı (mm) — YALNIZ gerçek seriden. Kip
    // animasyonlu değilse başlangıç yarıçapı döner (donuk tane).
    function portRadiusAt(dims, t, mode) {
        if (mode === 'port_history') {
            var hist = dims.portHist;
            var d = (hist && hist.time && hist.port_diameter)
                ? sampleSeries(hist.time, hist.port_diameter, t) : null;
            if (d !== null) return clamp(d * 1000 / 2, dims.rPort0, dims.rGrainOut - 0.5);
            return dims.rPort0;
        }
        if (mode === 'solid_mass_balance') {
            var wh = dims.webHist;
            var w = (wh && wh.time && wh.web) ? sampleSeries(wh.time, wh.web, t) : null;
            if (w !== null) {
                return clamp(dims.rPort0 + w * 1000, dims.rPort0, dims.rGrainOut - 0.5);
            }
            return dims.rPort0;
        }
        return dims.rPort0;
    }

    // Yanan web kalınlığı (mm) — HUD/etiket için; animasyonlu kip yoksa
    // null (ekranda sayı uydurulmaz).
    function burnedWebAt(dims, t, mode) {
        if (mode === 'solid_mass_balance' && dims.webHist) {
            var w = sampleSeries(dims.webHist.time, dims.webHist.web, t);
            return (w === null) ? null : w * 1000;
        }
        if (mode === 'port_history') {
            var r = portRadiusAt(dims, t, mode);
            return r - dims.rPort0;
        }
        return null;
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
            // Taban geometri yalnız klon kaynağıdır, sahneye hiç girmez —
            // GPU tarafı kopyası burada bırakılırsa sızıntı olur (görev 8)
            capGeoBase.dispose();
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
        // B3 (v2.6.27): kontur TEK KAYNAKTAN. Çözücü nozzle_contour.points
        // yayımladıysa iç kontur oradan örneklenir (ilk nokta konverjan
        // başlangıcına, dims.Lch'ye oturtulur; boylar metreden mm'ye
        // selectNozzleContour'da çevrildi). Yerel üretim yalnız veri yokken
        // çalışır ve sahnede 'kontur: yerel üretim' çipiyle beyan edilir.
        if (dims.contourPoints && dims.contourPoints.length >= 3) {
            var zRef = dims.contourPoints[0].z;
            return dims.contourPoints.map(function (cp) {
                return { z: dims.Lch + (cp.z - zRef), r: cp.r };
            });
        }
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
        // envMapIntensity: scene.environment metallere yansıma verir; 0.6-0.8
        // bandı yıkanmadan hacim kazandırır. Kesit yüzleri mat kalır (0.2).
        return {
            // Fırçalanmış alüminyum kasa: çevresel taşlama izi bump+roughness
            casing: new THREE.MeshStandardMaterial({
                color: 0x9fabbc, metalness: 0.72, roughness: 0.42,
                bumpMap: brushed, bumpScale: 0.12, roughnessMap: brushed,
                envMapIntensity: 0.7
            }),
            casingCut: new THREE.MeshStandardMaterial({ color: 0xc3ccd8, metalness: 0.15, roughness: 0.9, side: THREE.DoubleSide, envMapIntensity: 0.2 }),
            nozzle: new THREE.MeshStandardMaterial({ color: 0x525c68, metalness: 0.78, roughness: 0.38, envMapIntensity: 0.75 }),
            nozzleCut: new THREE.MeshStandardMaterial({ color: 0x76818f, metalness: 0.1, roughness: 0.95, side: THREE.DoubleSide, envMapIntensity: 0.2 }),
            // Grafit boğaz insert'i: koyu, mat, hafif yansımalı
            graphite: new THREE.MeshStandardMaterial({ color: 0x23262a, metalness: 0.42, roughness: 0.78, envMapIntensity: 0.5 }),
            graphiteCut: new THREE.MeshStandardMaterial({ color: 0x393e45, metalness: 0.1, roughness: 0.95, side: THREE.DoubleSide, envMapIntensity: 0.2 }),
            grain: new THREE.MeshStandardMaterial({ color: 0x6d4326, metalness: 0.0, roughness: 0.94 }),
            grainCut: new THREE.MeshStandardMaterial({ color: 0x936243, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            liner: new THREE.MeshStandardMaterial({ color: 0x23282e, metalness: 0.05, roughness: 0.9 }),
            linerCut: new THREE.MeshStandardMaterial({ color: 0x3a4046, metalness: 0.0, roughness: 1.0, side: THREE.DoubleSide }),
            injector: new THREE.MeshStandardMaterial({ color: 0xb08d57, metalness: 0.85, roughness: 0.38, envMapIntensity: 0.65 }),
            injectorCut: new THREE.MeshStandardMaterial({ color: 0xd2b184, metalness: 0.2, roughness: 0.85, side: THREE.DoubleSide, envMapIntensity: 0.2 }),
            bolt: new THREE.MeshStandardMaterial({ color: 0x343b44, metalness: 0.85, roughness: 0.4, envMapIntensity: 0.6 }),
            steel: new THREE.MeshStandardMaterial({ color: 0x6f7883, metalness: 0.9, roughness: 0.32, envMapIntensity: 0.7 }),
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
            heatMap: false,          // duvar ısıl akı giydirmesi
            cadMode: false           // ortografik görünüşler + teknik ölçüler
        };
        this._explodeF = 0; // 0=montajlı, 1=patlatılmış
        this._lastPortR = -1;
        this._disposed = false;

        this._initRenderer();
        this._initSceneGraph();
        this._buildToolbar();
        this._buildMotor();
        // Kamera plume'dan ÖNCE oturur: parçacık boyutu kadraj mesafesine
        // (_camDist) bağlıdır (kalem 1)
        this._fitCamera();
        this._buildPlume();
        this._buildLabels();
        this._bindResize();
        this._bindLangChange();

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
        // ACES filmik ton eşleme (r128'de mevcut): parlak alev/ışıklarda
        // yumuşak doyum, metallerde daha doğal kontrast (görev 2)
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.1;
        this.renderer.domElement.style.display = 'block';
        this.container.appendChild(this.renderer.domElement);

        this.camera = new THREE.PerspectiveCamera(40, w / h, 1, 100000);
        // Perspektif kamera kalıcı referansı: CAD kipi this.camera'yı
        // ortografik kamerayla değiştirir, çıkışta buradan geri yüklenir
        this._perspCam = this.camera;
        this._makeControls(this.camera);
    };

    // OrbitControls verilen kameraya (yeniden) bağlanır. r128 OrbitControls
    // kamera up vektörünü kuruluşta yakalar; CAD preset'leri up değiştirdiği
    // için preset/kip geçişinde controls yeniden kurulur.
    MotorScene.prototype._makeControls = function (cam) {
        var oldTarget = this.controls ? this.controls.target.clone() : null;
        if (this.controls && this.controls.dispose) this.controls.dispose();
        this.controls = new THREE.OrbitControls(cam, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.autoRotateSpeed = 0.9;
        if (oldTarget) this.controls.target.copy(oldTarget);
        return this.controls;
    };

    MotorScene.prototype._initSceneGraph = function () {
        this.scene = new THREE.Scene();
        // Opak sahne arka planı: şeffaf canvas + additive partiküller sayfa
        // arka planına karşı siyah kare artefaktı bırakıyordu
        this.scene.background = new THREE.Color(0x070d17);
        this.scene.fog = null;

        // Ortam haritası: prosedürel küp doku — metaller düz gri yerine
        // stüdyo yansıması alır (MeshStandardMaterial'lara otomatik uygulanır)
        this._envTex = makeEnvCubeTexture();
        this.scene.environment = this._envTex;

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

        // B1 (v2.6.27): SAHTE 8 BİLEZİK SÖKÜLDÜ. Eski kod her sıvı motora,
        // veriden bağımsız 8 dekoratif çevresel "soğutma bileziği" çiziyordu
        // — hesaplanmayan şey çizilmez. Gerçek rejeneratif kanallar EKSENEL
        // akar; sayı ve kesit ölçüleri çözücünün cooling_channels bloğundan
        // gelir. Veri yoksa hiçbir kanal çizilmez ve durum çipi bunu beyan
        // eder ('soğutma kanalları: veri yok').
        this._coolingChip = null;
        if (isLiquid) {
            var chans = coolingChannelLayout(d.cooling);
            if (chans.length) {
                // Tek paylaşımlı birim küp + kanal başına mesh: kesit GERÇEK
                // genişlik x yükseklik (mm), kanal dış cidara oturur ve
                // kamarayı boydan tarar. Land genişliği çizimde kanallar
                // arası boşluk olarak kendiliğinden görünür (2·π·R/n − w).
                var chanLen = d.Lch * 0.92;
                var chanGeo = new THREE.BoxGeometry(1, 1, 1);
                var chanR = d.rcOut + chans[0].heightMm / 2;
                for (var ch = 0; ch < chans.length; ch++) {
                    var chn = chans[ch];
                    var chMesh = new THREE.Mesh(chanGeo, mats.steel);
                    chMesh.scale.set(chn.widthMm, chanLen, chn.heightMm);
                    chMesh.rotation.y = chn.phi;
                    chMesh.position.set(chanR * Math.sin(chn.phi),
                        d.Lch * 0.5, chanR * Math.cos(chn.phi));
                    chMesh.userData.phi = chn.phi;
                    chMesh.userData.hideInCut = true; // kesit açıklığında gizlenir
                    chMesh.castShadow = true;
                    casing.add(chMesh);
                }
            } else {
                this._coolingChip = {
                    text: 'soğutma kanalları: veri yok', kind: 'missing'
                };
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
            // Delik yarıçapı ÇÖZÜCÜDEN gelir; gelmiyorsa delik çizilmez
            // (eski 1,2 mm tabanı hesaplanmış bir ölçü gibi görünüyordu).
            var hasOrifices = (d.nOrifices > 0 && d.orificeR > 0);
            var oriR = d.orificeR * 1.6;
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
                // Uçta radyal delik dizisi (yatık silindirler) — yalnız
                // çözücü gerçek bir delik sayısı/çapı verdiyse
                if (hasOrifices) {
                    var nRad = Math.min(d.nOrifices, 24);
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
                if (hasOrifices) {
                    var nSlot = Math.min(d.nOrifices, 12);
                    var slotGeo = new THREE.BoxGeometry(oriR * 1.4,
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
                    var exitR = oriR * 2.2;
                    var exitO = new THREE.Mesh(
                        new THREE.CylinderGeometry(exitR, exitR, 1.8,
                            this._perfMode ? 12 : 24),
                        mats.orifice);
                    exitO.position.y = injFace + 0.6;
                    exitO.userData.hideInCut = true;
                    injector.add(exitO);
                }

            } else if (d.injectorType === 'impingement') {
                // Açılı delik çiftleri: her çift eksene doğru eğik iki silindir
                var nPair = hasOrifices
                    ? Math.max(1, Math.min(Math.round(d.nOrifices / 2), 12)) : 0;
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

            } else if (hasOrifices) {
                // Showerhead: eş merkezli 2-3 delik halkası (çevreyle orantılı dağıtım)
                var oriGeo = new THREE.CylinderGeometry(oriR, oriR, 1.6, seg);
                var ringFr = d.nOrifices >= 10 ? [0.35, 0.6, 0.85] : [0.4, 0.75];
                var frSum = ringFr.reduce(function (a, b) { return a + b; }, 0);
                ringFr.forEach(function (fr, ri) {
                    var rr = fr * rMaxO;
                    var nRing = Math.max(1, Math.round(d.nOrifices * fr / frSum));
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

            // B2 (v2.6.27): enjektör deseni derinliği — YALNIZ çözücü
            // injector_pattern yayımladıysa çizilir; veri yoksa mevcut
            // davranış AYNEN korunur (delik deseni zaten gerçek kaynaktan).
            var pat = d.injPattern;
            if (pat && pat.patternType.indexOf('imping') === 0
                && pat.impingeHalfDeg) {
                // Çarpışma noktası çizgileri: delik çiftlerinden itki ekseni
                // üstündeki kesişime. İstasyon uydurma değil, düz geometri:
                // z = r / tan(θ) (impingementApexZ). Çizgi sayısı gösterimde
                // mevcut delik çizimiyle aynı tavana bağlıdır (12 çift) —
                // sayının beyanı deliklerin kendisindedir.
                var ringR = rMaxO * 0.68;
                var apexDz = impingementApexZ(ringR, pat.impingeHalfDeg);
                if (apexDz !== null) {
                    var impMat = new THREE.LineBasicMaterial({
                        color: new THREE.Color(sourceColor('computed')),
                        transparent: true, opacity: 0.8, toneMapped: false
                    });
                    var nPairLines = Math.max(1,
                        Math.min(Math.round(pat.nHoles / 2), 12));
                    var apexPt = new THREE.Vector3(0, injFace + apexDz, 0);
                    for (var il = 0; il < nPairLines; il++) {
                        var ilPhi = (il / nPairLines) * TAU;
                        var impGeoLine = new THREE.BufferGeometry().setFromPoints([
                            new THREE.Vector3(ringR * Math.sin(ilPhi), injFace,
                                ringR * Math.cos(ilPhi)),
                            apexPt
                        ]);
                        var iline = new THREE.Line(impGeoLine, impMat);
                        iline.userData.phi = ilPhi;
                        iline.userData.hideInCut = true;
                        injector.add(iline);
                    }
                }
            } else if (pat && pat.patternType === 'swirl' && pat.impingeHalfDeg) {
                // Swirl açı gösterimi: sprey konisi V-çizgileri + açı çipi.
                // Açı GERÇEK veriden (impingement_angle_deg); açı yoksa bu
                // blok hiç çalışmaz — koni de çip de çizilmez.
                var swHalf = clamp(pat.impingeHalfDeg, 5, 85);
                var swLen = Math.min(0.30 * d.Lch, 6 * d.rc);
                var swR = swLen * Math.tan(THREE.MathUtils.degToRad(swHalf));
                var swMat = new THREE.LineBasicMaterial({
                    color: new THREE.Color(sourceColor('computed')),
                    transparent: true, opacity: 0.8, toneMapped: false
                });
                [[0, 1], [0, -1], [1, 0], [-1, 0]].forEach(function (sdir) {
                    var swGeo = new THREE.BufferGeometry().setFromPoints([
                        new THREE.Vector3(0, injFace, 0),
                        new THREE.Vector3(sdir[0] * swR, injFace + swLen,
                            sdir[1] * swR)
                    ]);
                    injector.add(new THREE.Line(swGeo, swMat));
                });
                var swChip = statusChip(
                    'sprey açısı ' + (2 * swHalf).toFixed(0) + '°', 'computed');
                var swH = Math.max(6, Math.min(d.Lch * 0.05, d.rc * 0.8));
                swChip.scale.set(swH * swChip.userData.aspect, swH, 1);
                swChip.position.set(0, injFace + swLen * 1.12, 0);
                injector.add(swChip);
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
        this._resolvePortRegression();
        this._rebuildGrain(portRadiusAt(d, this.state.time, this._portRegMode), true);

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
                blending: THREE.AdditiveBlending, depthWrite: false,
                side: THREE.DoubleSide, toneMapped: false
            });
        }
        this._glowMesh = null;
        this._rebuildGlow(portRadiusAt(d, this.state.time, this._portRegMode));

        // Boğaz alev diski
        if (!this._throatFlame) {
            this._throatFlame = new THREE.Sprite(new THREE.SpriteMaterial({
                map: glowTexture('rgba(255,255,235,1)', 'rgba(255,140,40,0.85)'),
                transparent: true, blending: THREE.AdditiveBlending,
                depthWrite: false, opacity: 0, toneMapped: false
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

        // Zemin: gölge düzlemi + ızgara. Gölge düzlemi ilk kurulumda üretilir
        // ve motor boyuyla ölçeklenir (yalnız gölge alanıdır); sonraki
        // kurulumlarda konum tazelenir (görev 5a — bayatlamayı önler)
        var floorY = -(this.dims.rcOut + this.dims.flangeLip) * 1.9;
        if (!this._floor) {
            var shadowPlane = new THREE.Mesh(
                new THREE.PlaneGeometry(this._totalLen * 4, this._totalLen * 4),
                new THREE.ShadowMaterial({ opacity: 0.32 })
            );
            shadowPlane.rotation.x = -Math.PI / 2;
            shadowPlane.receiveShadow = true;
            this.scene.add(shadowPlane);
            this._floor = shadowPlane;
            this._floorBaseLen = this._totalLen;   // ölçek referansı
        }
        var fScale = this._totalLen / (this._floorBaseLen || this._totalLen);
        this._floor.position.y = floorY;
        this._floor.scale.setScalar(fScale);
        // Izgara (kalem 5): MUTLAK birim hücre — yuvarlak kademe (10/50/100
        // mm), motorla ÖLÇEKLENMEZ; hücre boyu köşe rozetinde beyan edilir.
        // Hücre/açıklık değişince yeniden kurulur (tasarım modu).
        var cell = gridCellMm(this._totalLen);
        var span = gridSpanMm(this._totalLen, cell);
        if (!this._grid || this._gridCell !== cell || this._gridSpan !== span) {
            if (this._grid) {
                this.scene.remove(this._grid);
                if (this._grid.geometry) this._grid.geometry.dispose();
                if (this._grid.material) this._grid.material.dispose();
            }
            if (this._gridBadge) {
                this.scene.remove(this._gridBadge);
                if (this._gridBadge.material.map) this._gridBadge.material.map.dispose();
                this._gridBadge.material.dispose();
            }
            var grid = new THREE.GridHelper(span, Math.round(span / cell),
                0x0e6f80, 0x123340);
            grid.material.transparent = true;
            grid.material.opacity = 0.35;
            this.scene.add(grid);
            this._grid = grid;
            this._gridCell = cell;
            this._gridSpan = span;
            // Köşe rozeti: seçilen hücre boyu (mutlak referans beyanı)
            var badge = textSprite(gridBadgeText(cell), {
                border: 'rgba(20, 111, 128, 0.7)', color: '#7fd4e2'
            });
            badge.material.depthTest = true;   // HUD değil, zemin mobilyası
            badge.renderOrder = 0;
            var bh = Math.max(cell * 1.1, span * 0.03);
            badge.scale.set(bh * badge.userData.aspect, bh, 1);
            this._gridBadge = badge;
            this._gridBadgeH = bh;
            this.scene.add(badge);
        }
        this._grid.position.y = floorY + 0.5;
        this._grid.scale.setScalar(1);   // motorla ölçeklenmez (kalem 5)
        this._gridBadge.position.set(this._gridSpan * 0.42,
            floorY + this._gridBadgeH * 0.8, this._gridSpan * 0.42);
        // Izgara yeniden kurulduysa CAD nötr stüdyo stili korunur
        if (this.state.cadMode) this._applyCadGridStyle(true);

        // Durum çipleri (kaynak şeffaflığı, v2.6.27): her çip GERÇEK bir
        // duruma bağlıdır ve rengi SOURCE_COLORS eşlemesinden gelir.
        //  * kontur kaynağı her motorda beyan edilir (çözücü/yerel üretim)
        //  * sıvı motorda soğutma kanalı verisi yoksa 'veri yok' çipi
        this._floorY = floorY;
        this._buildStatusChips(this._statusChipDefs(), floorY);
    };

    // Durum çipi tanımları TEK yerde üretilir: hem zemin kurulumunda hem
    // kip/dil değişiminde aynı liste kullanılır.
    MotorScene.prototype._statusChipDefs = function () {
        var d = this.dims;
        var defs = [];
        if (this._coolingChip) defs.push(this._coolingChip);
        defs.push(d.contourSource === 'solver'
            ? { text: 'kontur: çözücü', kind: 'computed' }
            : { text: 'kontur: yerel üretim', kind: 'assumed' });
        // Yanma animasyonunun kaynağı (B5): çip, iç yüzeyin neyden
        // gerilediğini — ya da gerilemediğini — beyan eder.
        if (d.motorType !== 'liquid') {
            defs = defs.concat(portRegressionChipDefs(this._portRegMode,
                { endsBurn: d.endsBurn }));
        }
        return defs;
    };

    // Çipleri yerinde tazele (kip ya da dil değişti). Zemin henüz
    // kurulmadıysa sessizce atlanır — kurulumda zaten üretilecekler.
    MotorScene.prototype._refreshStatusChips = function () {
        if (this._floorY === undefined) return;
        this._buildStatusChips(this._statusChipDefs(), this._floorY);
    };

    // Port gerileme kipini çöz (tek karar noktası). Kesit şekli, tane
    // tipi ve GERÇEK seri varlığı birlikte değerlendirilir.
    MotorScene.prototype._resolvePortRegression = function () {
        var d = this.dims;
        var hist = d.portHist;
        this._portRegMode = portRegressionMode({
            portShape: this.state.portShape,
            grainType: d.grainType,
            hasPortHistory: !!(hist && hist.time && hist.port_diameter
                && hist.time.length > 1),
            hasWebHistory: !!d.webHist
        });
        return this._portRegMode;
    };

    // Çip yerleşim çapası (mm). ÇİPLER BEYANDIR; okunamayan beyan beyan
    // değildir. Ölçüldü (2026-08-15, canlı tarayıcı, katı sayfası): çipler
    // ızgara açıklığının köşesine (±0,42·span, span = 2200 mm) konduğu için
    // varsayılan kadrajda EKRAN DIŞINDA kalıyordu — üç çipin de izdüşümü
    // NDC x ≈ −2,05…−2,34 (görünür sınır ±1). Kamera ızgarayı değil MOTORU
    // çerçeveler (cameraFrameFit motor kutusundan türer), bu yüzden çapa
    // motor boyudur. 0,42 oranı korunur: çip, model kutusunun hemen
    // dışında ve zeminde kalır.
    function chipAnchorMm(totalLen) {
        return totalLen * 0.42;
    }

    // Çip yüksekliği ÖLÇÜ ROZETLERİYLE aynı ölçekten türer (labelScaleBase);
    // eskiden ızgara hücresinden geliyordu ve 732 mm'lik motorda 66 mm'ye
    // çıkıyordu: uzun metinli çip ~530 mm genişleyip kadrajın solundan
    // taşıyordu (ölçüldü 2026-08-15, canlı tarayıcı).
    function chipHeightMm(totalLen, outerDiameter) {
        return labelScaleBase(totalLen, outerDiameter) * 0.62;
    }

    // Durum çiplerini zemin üstüne, modelin ön-sol köşesine dizer.
    // Çipler HUD süsü değil BEYANDIR: yalnız gerçek durumlar listelenir.
    MotorScene.prototype._buildStatusChips = function (defs, floorY) {
        if (this._chipGroup) {
            this.scene.remove(this._chipGroup);
            this._chipGroup.traverse(function (o) {
                if (o.material) {
                    if (o.material.map) o.material.map.dispose();
                    o.material.dispose();
                }
            });
        }
        var g = this._chipGroup = new THREE.Group();
        var anchor = chipAnchorMm(this._totalLen || 1);
        var bh = chipHeightMm(this._totalLen || 1,
            2 * (this.dims.rcOut + this.dims.flangeLip));
        var i, sp;
        // Önce sprite'lar kurulur ve EN GENİŞİ ölçülür: bütün çipler AYNI
        // merkez x'te durur. Çipe göre x kaydırmak, zemin perspektifte
        // uzaklaştığı için yığını ekranda karıştırıyordu (ölçüldü: dar çip
        // geniş çipin üstüne biniyordu).
        var sprites = [], maxW = 0;
        for (i = 0; i < defs.length; i++) {
            sp = statusChip(defs[i].text, defs[i].kind);
            sp.material.depthTest = true;   // HUD değil, zemin mobilyası
            sp.renderOrder = 0;
            sp.scale.set(bh * sp.userData.aspect, bh, 1);
            maxW = Math.max(maxW, sp.scale.x);
            sprites.push(sp);
        }
        for (i = 0; i < sprites.length; i++) {
            // En geniş çipin sol kenarı çapaya oturur; metin İÇERİ uzar,
            // kadrajın dışına taşmaz.
            sprites[i].position.set(-anchor + maxW / 2,
                floorY + bh * (0.8 + 1.35 * i), anchor);
            g.add(sprites[i]);
        }
        this.scene.add(g);
    };

    // Grain katısını verilen eşdeğer port yarıçapıyla yeniden kur.
    // circular: lathe halka. Diğer şekiller: tam görünümde gerçek kesitli
    // ekstrüzyon; kesit görünümünde lathe gövde (iç = şeklin iç teğet
    // yarıçapı) + kesme yüzeylerinde GERÇEK kesit kapakları.
    MotorScene.prototype._rebuildGrain = function (rPort, force) {
        // Eski eşik 0.05 mm idi — oynatma sırasında fiilen HER karede
        // Lathe/Extrude geometrisi sıfırdan kuruluyordu. Eşik büyütüldü;
        // aradaki karelerde parıltı silindiri radyal ölçekle güncellenir
        // (görev 1). Kesin geometri force ile (kurulum, şekil değişimi,
        // yanma sonu) her zaman alınabilir.
        var epsMm = Math.max(GRAIN_REBUILD_MIN_MM,
            GRAIN_REBUILD_FRACTION * this.dims.rGrainOut);
        if (!force && Math.abs(rPort - this._lastPortR) < epsMm) return;
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
        // Radyal ölçek animasyonu referansı: oynatma sırasında geometri
        // yeniden kurulmaz, mevcut silindir rP/rBuilt oranıyla ölçeklenir
        this._glowBuiltPort = Math.max(rPort, 1e-3);
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

    // Plume fiziği — v2.6.26'dan itibaren ÇÖZÜCÜNÜN GERÇEK DEĞERLERİYLE.
    //
    // Eskiden pe/pa oranı `(8/eps)^1.15` diye uyduruluyor, şok elması aralığı
    // `de*(0.7+0.5*sqrt(eps/8))` gibi dayanaksız bir ifadeyle çiziliyordu.
    // İkisi de artık nozul çözümünden gelir (bkz. readNozzleExit).
    //
    // Çözücü verisi yoksa null döner ve plume çizilmez — uydurma alev yasak.
    MotorScene.prototype._plumeAero = function () {
        var d = this.dims;
        var ex = d.nozzleExit;
        if (!ex) return null;

        // Radyal saçılım: nozul çıkış yarı açısı akışın geometrik sapmasıdır.
        // Az genişlemiş jette (pe > pa) akış çıkışta ayrıca Prandtl-Meyer
        // genişlemesiyle DIŞA açılır; aşırı genişlemişte içeri büzülür.
        var thetaDeg = d.nozType === 'conical' ? d.halfAngle : d.thetaE;
        var geometric = Math.tan(THREE.MathUtils.degToRad(clamp(thetaDeg, 2, 35)));
        var pressureTurn = clamp(Math.pow(ex.pressureRatio, 0.5), 0.6, 1.8);
        var spread = geometric / Math.tan(
            THREE.MathUtils.degToRad(PLUME_REF_EXIT_ANGLE_DEG)) * pressureTurn;

        // Şok elmalarının ŞİDDETİ basınç uyumsuzluğuyla artar; tam genişlemiş
        // jette (pe = pa) hücre yapısı kaybolur. Sürücü ölçülen |1 − pe/pa|
        // sapmasıdır; EKRANA aktarım diamondVisibility transfer fonksiyonuyla
        // yapılır (kalem 3 — adapte lülede seçilebilir, sapmada belirgin).
        return {
            spread: clamp(spread, 0.4, 3.5),
            // Prandtl-Pack hücre aralığı (readNozzleExit'te hesaplandı).
            // 0 ise hücre yapısı yok demektir; çizim onu atlar.
            diamondSpacing: ex.cellSpacingMm,
            diamondStrength: diamondVisibility(ex.pressureRatio),
            expansionState: ex.expansionState,
            exitVelocity: ex.exitVelocity,
            exitTemperature: ex.exitTemperature
        };
    };

    MotorScene.prototype._buildPlume = function () {
        var d = this.dims;
        this._plumeInfo = this._plumeAero();
        // Boy bütçesi + parçacık sayısı boyla orantılı (kalem 1): jet
        // kadrajda kalır, ekran yoğunluğu motor boyundan bağımsız kalır.
        this._plumeLen = plumeLengthMm(this._totalLen);
        var N = plumeParticleCount(this._totalLen);
        this._plumeN = N;
        var geo = new THREE.BufferGeometry();
        var pos = new Float32Array(N * 3);
        var col = new Float32Array(N * 3);
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        this._pState = new Float32Array(N * 5); // vy, vr, phi, life, maxLife

        var mat = new THREE.PointsMaterial({
            // Boyut ekran-piksel hedefli (kalem 1): kadraj mesafesi _camDist
            // _fitCamera'da bu kurulumdan önce hesaplanır
            size: plumeParticleSize(d.re, this._camDist,
                this.container.clientHeight || 520),
            // Yumuşak Gauss sprite (kalem 1a): nötr alfa rampası — ton
            // vertex renginden (gerçek sıcaklık sürücüsü) gelir
            map: flameSpriteTexture(),
            vertexColors: true, transparent: true, depthWrite: false,
            blending: THREE.AdditiveBlending, sizeAttenuation: true,
            toneMapped: false
        });
        this._plume = new THREE.Points(geo, mat);
        this._plume.frustumCulled = false;
        this.model.add(this._plume);
        for (var i = 0; i < N; i++) this._resetParticle(i, true);
        // Ölü partiküller hiç çizilmez: ilk 'aktif' indeks canlıdır (prefix
        // sözleşmesi), aralık her karede _updatePlume'da güncellenir (görev 8)
        this._plumeActive = 0;
        geo.setDrawRange(0, 0);

        // Şok elmasları
        this._diamonds = [];
        var nd = 5;
        for (var k = 0; k < nd; k++) {
            var s = new THREE.Sprite(new THREE.SpriteMaterial({
                map: glowTexture('rgba(220,240,255,1)', 'rgba(90,170,255,0.5)'),
                transparent: true, blending: THREE.AdditiveBlending,
                depthWrite: false, opacity: 0, toneMapped: false
            }));
            this.model.add(s);
            this._diamonds.push(s);
        }
        // Çekirdek koni katmanı KONUMLARDAN ÖNCE kurulur: elmas ölçekleri
        // koninin yerel yarıçapına hizalanır (kalem 4)
        this._rebuildFlameCone();
        this._updateDiamondPositions();
    };

    // ------------------------------------------------------------------
    // Çekirdek alev konisi (kalem 3): parçacık bulutunun ALTINA sürekli,
    // yarı saydam additive katman. Parçacıklar sürekli akışın ayrık
    // örnekleridir; koni bu sürekliliği verir — 'patlamış mısır' yerine
    // gövdesi olan jet. Açı plumeConeSpec'ten (gerçek Me, Mj, γ, θ_geo),
    // renk flameColorFromT'den (gerçek Te) türer. Çözücü çıkış durumu
    // yoksa koni HİÇ kurulmaz — parçacıklarla aynı sözleşme (sahte veri
    // yasağı). Draw call bütçesi (kalem 5): dış zarf + iç çekirdek =
    // +2 mesh (sınır +3, bekçi: tests/test_alev_estetigi.py).
    // ------------------------------------------------------------------
    MotorScene.prototype._rebuildFlameCone = function () {
        if (this._flameGroup) {
            this.model.remove(this._flameGroup);
            this._flameGroup.traverse(function (o) {
                if (o.geometry) o.geometry.dispose();
                if (o.material) o.material.dispose();
            });
            this._flameGroup = null;
        }
        this._coneSpec = null;
        var d = this.dims;
        var ex = d.nozzleExit;
        if (!ex || !this._plumeInfo) return;
        // Geometrik açı _plumeAero ile AYNI seçim ve kırpma (okuma —
        // fizik sürücüsüne dokunulmaz)
        var thetaDeg = clamp(d.nozType === 'conical' ? d.halfAngle : d.thetaE,
            2, 35);
        var spec = plumeConeSpec(d.re, thetaDeg, ex.exitMach, ex.jetMach,
            ex.gamma, 0.6 * (this._plumeLen || plumeLengthMm(this._totalLen)));
        if (!spec) return;
        this._coneSpec = spec;
        // Renk gerçek çıkış sıcaklığından; Te yoksa (Tc eksik) plumeColorAt
        // fallback bandının çekirdek turuncusu — iki katman aynı palete düşer
        var col = (isFinite(ex.exitTemperature) && ex.exitTemperature > 0)
            ? flameColorFromT(ex.exitTemperature)
            : { r: 1.0, g: 0.62, b: 0.22 };
        this._flameGroup = new THREE.Group();
        var self = this;
        // CylinderGeometry(üstR, altR, boy): +Y jet yönü — alt uç (r0)
        // çıkış düzleminde, üst uç (r1) aşağı akışta
        function addCone(r0, r1, len, baseOpacity) {
            var geo = new THREE.CylinderGeometry(
                Math.max(r1, 0.01), Math.max(r0, 0.01), len,
                32, 1, true);
            var mat = new THREE.MeshBasicMaterial({
                color: new THREE.Color(Math.min(col.r, 1), Math.min(col.g, 1),
                    Math.min(col.b, 1)),
                transparent: true, opacity: baseOpacity,
                blending: THREE.AdditiveBlending, depthWrite: false,
                side: THREE.DoubleSide, toneMapped: false
            });
            var mesh = new THREE.Mesh(geo, mat);
            mesh.position.y = len / 2;
            mesh.renderOrder = 1;
            mesh.userData.baseOpacity = baseOpacity;
            self._flameGroup.add(mesh);
            return mesh;
        }
        // Dış zarf: jet sınırı — tam boy, çok saydam (parçacıklar üstünde
        // parlar). İç çekirdek: potansiyel çekirdeğin sıcak merkezi —
        // boyun %60'ı, daha dar ve daha parlak. Opaklıklar görsel aktarım
        // sabitleridir (fizik iddiası değil); şiddet _updatePlume'da
        // itkiyle (throttle) modüle edilir.
        addCone(spec.r0, spec.r1, spec.lengthMm, 0.10);
        var lenIn = 0.6 * spec.lengthMm;
        addCone(0.55 * spec.r0,
            0.55 * coneRadiusAt(spec, lenIn), lenIn, 0.22);
        this._flameGroup.position.y = this._nozzleInfo.zExit;
        this.model.add(this._flameGroup);
    };

    // Elmas konum/ölçekleri geometriye bağlı — update() sonrası da çağrılır.
    // Aralık genişleme oranından türetilir: eps büyüdükçe hücreler uzar.
    MotorScene.prototype._updateDiamondPositions = function () {
        var d = this.dims;
        var info = this._plumeInfo || (this._plumeInfo = this._plumeAero());
        // Çözücü verisi yoksa ya da jet tam genişlemişse hücre yapısı YOKTUR;
        // elmasları uydurma bir aralıkla dizmek yerine gizleriz.
        if (!info || !(info.diamondSpacing > 0)) {
            for (var j = 0; j < this._diamonds.length; j++) {
                this._diamonds[j].visible = false;
            }
            return;
        }
        for (var k = 0; k < this._diamonds.length; k++) {
            this._diamonds[k].visible = true;
            var yk = d.de * 0.9 + k * info.diamondSpacing;
            this._diamonds[k].position.set(0, this._nozzleInfo.zExit + yk, 0);
            // Elmas ölçeği koni katmanıyla hizalı (kalem 4): parlama o
            // istasyondaki jet sınırı yarıçapına (coneRadiusAt) oturur —
            // eski re·(1.5−0.18k) dizisi koniden bağımsız büzülüyordu.
            // 1.6 katsayısı parlama halesinin çekirdekten taşma payıdır
            // (görsel aktarım). Aralık Prandtl-Pack'ten, şiddet
            // |1−pe/pa| sürücüsünden gelmeye DEVAM eder; adapte lülede
            // zayıf kalması fiziğin kendisidir (hücre yapısı pe=pa'da
            // kaybolur — diamondVisibility bunu beyan eder).
            var rLoc = coneRadiusAt(this._coneSpec, yk);
            this._diamonds[k].scale.setScalar(1.6 * (rLoc || d.re));
        }
    };

    MotorScene.prototype._resetParticle = function (i, scatter) {
        var d = this.dims;
        var st = this._pState;
        var pos = (this._plume && this._plume.geometry)
            ? this._plume.geometry.attributes.position.array : null;
        var info = this._plumeInfo;
        var spread = info ? info.spread : 1;
        // Doğuş noktası: çıkış kesitinde EKSENE YOĞUN dağılım (kalem 1b,
        // plumeSpawnRadius). Rastgelelik sahtelik değildir — sürekli akışın
        // ayrık örneklemesidir; jet kütle akısı eksende tepe yaptığı için
        // örnekleme de eksene ağırlıklıdır (eski sqrt alanca eşdağılımdı).
        var rSpawn = plumeSpawnRadius(d.re, Math.random());
        var phi = Math.random() * TAU;
        // v2.6.26: hız artık ÇÖZÜCÜNÜN nozul çıkış hızından ölçekleniyor.
        // Eskiden `_totalLen * (2.2 + rastgele*1.6)` idi; modelin uzunluğuna
        // bağlı, gerçek egzoz hızıyla hiç ilgisi olmayan bir sayıydı.
        // Ölçek: 2500 m/s (tipik kimyasal roket egzozu) sahnede eski görsel
        // hıza denk gelsin diye normalize edilir; hızlı motor GÖRÜNÜR biçimde
        // hızlı akar. Parçacıklar arası %20'lik saçılım türbülanslı jetin
        // hız dağılımını temsil eder (görsel; tek bir hız değeri düz bir
        // duvar gibi görünürdü).
        var vExit = (info && info.exitVelocity > 0) ? info.exitVelocity : 2500;
        var speed = this._totalLen * 3.0 * (vExit / 2500)
            * (0.9 + 0.2 * Math.random());
        st[i * 5 + 0] = speed;
        // Radyal saçılım çıkış yarım açısıyla ölçekli: bell (θe küçük) dar
        // ve toplu, koni (θ büyük) geniş bir jet üretir (görev 6)
        st[i * 5 + 1] = speed * (0.05 + 0.10 * Math.random()) * spread;
        st[i * 5 + 2] = phi;
        // Ömür boy bütçesinden türer (kalem 1): ortalama menzil ≈ plume
        // boyu — eski sabit 0.35-0.85 s ömür jeti ~2,2·L'ye taşırıyordu
        var maxLife = plumeLifeSeconds(
            this._plumeLen || plumeLengthMm(this._totalLen),
            speed, Math.random());
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
        // v2.6.26 — UYDURMA ALEV YASAĞI: çözücü nozul çıkış durumunu
        // vermediyse (eski kayıt, eksik analiz, yakınsamayan çözüm) egzoz
        // ÇİZİLMEZ. Eskiden bu durumda da uydurma sabitlerle akışkan bir
        // alev gösteriliyordu ve kullanıcı hesabın çalıştığını sanıyordu.
        var geo = this._plume.geometry;
        if (!this._plumeInfo) {
            this._plume.visible = false;
            if (geo && geo.setDrawRange) geo.setDrawRange(0, 0);
            if (this._flameGroup) this._flameGroup.visible = false;
            for (var h = 0; h < this._diamonds.length; h++) {
                this._diamonds[h].visible = false;
            }
            return;
        }
        this._plume.visible = true;
        var info = this._plumeInfo;
        var pos = geo.attributes.position.array;
        var col = geo.attributes.color.array;
        var st = this._pState;
        // Kalite anahtarı (perf modu) partikül tavanını düşürür
        var qf = this._qualityFactor || 1.0;
        var active = Math.floor(this._plumeN * qf * clamp(intensity, 0, 1));
        // Ölü partiküller GPU'ya hiç gitmez: ilk 'active' indeks canlı kabul
        // edilir (prefix sözleşmesi) + setDrawRange. Aktif sayı büyüyünce
        // yeni açılan indeksler nozula ışınlanır — bayat konumda belirme
        // olmaz; ayrıca öne-alma takası gereksizleşir (görev 8).
        var prevActive = this._plumeActive || 0;
        for (var a = prevActive; a < active; a++) this._resetParticle(a, false);
        this._plumeActive = active;
        geo.setDrawRange(0, active);
        // İtkiyle orantılı jet: eksenel hız ve plume boyu intensity ile ölçeklenir
        var velScale = 0.55 + 0.45 * clamp(intensity, 0, 1);
        for (var i = 0; i < active; i++) {
            var o5 = i * 5, o3 = i * 3;
            st[o5 + 3] += dt;
            if (st[o5 + 3] >= st[o5 + 4]) {
                // Yeniden doğuş TEK yoldan: _resetParticle konumu da yazar
                // (eksene yoğun dağılım, kalem 1b) — buradaki eski sqrt
                // kopyası ikinci bir dağılım tanımlıyordu, kaldırıldı
                this._resetParticle(i, false);
            }
            var f = st[o5 + 3] / st[o5 + 4]; // 0..1 yaşam oranı
            pos[o3 + 1] += st[o5 + 0] * dt * velScale;
            var vr = st[o5 + 1] * dt * (0.4 + f * 1.6);
            pos[o3 + 0] += Math.sin(st[o5 + 2]) * vr;
            pos[o3 + 2] += Math.cos(st[o5 + 2]) * vr;
            // Renk yaşam eğrisi (kalem 2): SICAKLIK sürücülü — zincir
            // gerçek T_c → izentropik Te (readNozzleExit) → 1/(1+3f)
            // soğuma → akkor rengi. Te yoksa beyanlı bant paleti (fallback)
            var pc = plumeColorAt(f, intensity, info.exitTemperature);
            col[o3] = pc.r; col[o3 + 1] = pc.g; col[o3 + 2] = pc.b;
        }
        geo.attributes.position.needsUpdate = true;
        geo.attributes.color.needsUpdate = true;

        // Çekirdek koni şiddeti (kalem 3): itkiyle (throttle) orantılı,
        // hafif titreşimli — elmaslardaki flick kalıbının yavaşlatılmışı
        // (türbülans temsili; taban opaklık kuruluşta userData'da)
        if (this._flameGroup) {
            this._flameGroup.visible = true;
            var cflick = 0.85 + 0.15 * Math.sin(this._clock.elapsedTime * 23);
            for (var m = 0; m < this._flameGroup.children.length; m++) {
                var cm = this._flameGroup.children[m];
                cm.material.opacity =
                    cm.userData.baseOpacity * clamp(intensity, 0, 1) * cflick;
            }
        }

        // Elmas şiddeti basınç uyumsuzluğuyla (|1 − pe/pa| yaklaşımı) ölçekli:
        // ideale yakın genişlemede elmaslar söner, sapmada belirginleşir
        var dstr = this._plumeInfo ? this._plumeInfo.diamondStrength : 1;
        for (var k = 0; k < this._diamonds.length; k++) {
            var flick = 0.75 + 0.25 * Math.sin(this._clock.elapsedTime * 37 + k * 2.4);
            this._diamonds[k].material.opacity =
                intensity * (0.75 - k * 0.12) * flick * dstr;
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
        // Ölçü değerleri ÇÖZÜCÜDEN gelir → çizgi rengi kaynak-renk
        // eşlemesinin 'computed' camgöbeğidir (tasarım dili)
        var lineMat = new THREE.LineBasicMaterial({
            color: new THREE.Color(sourceColor('computed')),
            transparent: true, opacity: 0.75, depthTest: false,
            toneMapped: false
        });
        // Rozet ölçeği boy VE çapla sınırlı (kalem 6): rozet yüksekliği
        // (0.62·scaleBase) dış çapın yarısını aşamaz — eski L·0.055 kuralı
        // L/D≈19,7 gövdede rozeti çapın %63'üne çıkarıyordu
        var scaleBase = labelScaleBase(this._totalLen, 2 * d.rcOut);
        var cad = this.state.cadMode;

        // Etiketler açıklığın karşısında (lathe -X ⇒ dünya +Y, üstte) durur.
        // CAD kipinde (kalem 4b) rozet çizgisi teknik-resim leader'ına
        // döner: geometriye ok uçlu eğik çizgi + yatay iniş + metin.
        function callout(zPos, rFrom, text, extra) {
            // Kılavuz çizgi payı yarıçapa oranlı (kalem 6)
            var off = rFrom + (extra || labelLeaderOffset(rFrom, scaleBase));
            var hgt = scaleBase * 0.62;
            if (cad) {
                var tip = new THREE.Vector3(-rFrom, zPos, 0);
                var elbow = new THREE.Vector3(-off - scaleBase * 0.35,
                    zPos + scaleBase * 0.5, 0);
                var land = new THREE.Vector3(elbow.x - scaleBase * 0.9,
                    elbow.y, 0);
                g.add(new THREE.Line(
                    new THREE.BufferGeometry().setFromPoints([tip, elbow, land]),
                    lineMat));
                // Ok ucu: leader doğrultusunda geriye açılan V
                var dir = elbow.clone().sub(tip).normalize();
                var perp = new THREE.Vector3(-dir.y, dir.x, 0);
                var ah = scaleBase * 0.22;
                [1, -1].forEach(function (s) {
                    g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([
                        tip,
                        tip.clone().add(dir.clone().multiplyScalar(ah))
                            .add(perp.clone().multiplyScalar(s * ah * 0.38))
                    ]), lineMat));
                });
                var spC = textSprite(text);
                spC.scale.set(hgt * spC.userData.aspect, hgt, 1);
                spC.position.set(land.x - (hgt * spC.userData.aspect) / 2,
                    land.y + hgt * 0.65, 0);
                g.add(spC);
                return;
            }
            var pts = [
                new THREE.Vector3(-rFrom, zPos, 0),
                new THREE.Vector3(-off - scaleBase * 0.35, zPos, 0)
            ];
            g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
            var sp = textSprite(text);
            sp.scale.set(hgt * sp.userData.aspect, hgt, 1);
            sp.position.set(-off - scaleBase * 0.4 - (hgt * sp.userData.aspect) / 2, zPos, 0);
            g.add(sp);
        }

        // v2.6.26 (Y3): ölçü oku dış yüzeyden çıkıp İÇ çapı yazıyordu. Ölçü
        // tablosunda aynı karışıklık atölyede 2 x cidar kadar (ölçülen koşuda
        // 31,8 mm) yanlış boru seçtiriyordu. Artık ikisi de AÇIKÇA yazılır.
        // Metinler dimensionLabelTexts'ten gelir (kalem 7 — sahne dili tek,
        // Türkçe; 'iç/dış' UTF-8 yazılır).
        var texts = dimensionLabelTexts({
            motorType: d.motorType,
            chamberInnerMm: d.Dch,
            chamberOuterMm: 2 * d.rcOut,
            throatMm: d.dt,
            exitMm: d.de,
            totalMm: this._nozzleInfo.zExit + d.capT,
            grainMm: d.Lg
        });
        callout(d.Lch * 0.30, d.rcOut, texts.chamber);
        callout(d.Lch + d.Lc, d.rt + 2, texts.throat, scaleBase * 1.5);
        callout(this._nozzleInfo.zExit - 2, this._nozzleInfo.rExit + d.nozzleWall, texts.exit);

        // Toplam uzunluk = kapak dışı → nozul çıkışı (2D kesitle aynı tanım;
        // oksitleyici giriş borusu hariç). YAKIT etiketi sıvıda anlamsız —
        // orada Lg yanma odası boyudur, ODA olarak yazılır.
        var totalTxt = textSprite(texts.total,
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
        // Kadraj PERSPEKTİF kameraya oturur; CAD kipindeyken aktif kamera
        // ortografiktir ve kendi preseti aşağıda ayrıca tazelenir.
        var cam = this._perspCam || this.camera;
        // En-boy oranına duyarlı kadraj (kalem 4): kutu köşeleri hem yatay
        // hem dikey FOV'a oturtulur; uzun-ince gövdede köşegen kompozisyon
        var aspect = cam.aspect ||
            ((this.container.clientWidth || 800) / (this.container.clientHeight || 520));
        var fit = cameraFrameFit(L / 2, R, CAMERA_FOV_DEG, aspect);
        var dist = fit.dist;
        this._camDist = dist;   // parçacık boyutu bu mesafeye göre seçilir
        this._camHome = new THREE.Vector3(
            fit.dir.x * dist, fit.dir.y * dist, fit.dir.z * dist);
        cam.position.copy(this._camHome).multiplyScalar(1.5); // intro dolly başlangıcı
        this.controls.target.set(0, 0, 0);
        this._keyLight.position.set(L * 0.8, L * 1.1, L * 0.7);
        var sc = this._keyLight.shadow.camera;
        sc.left = -L; sc.right = L; sc.top = L; sc.bottom = -L; sc.far = L * 6;
        this._keyLight.shadow.camera.updateProjectionMatrix();
        this._rimCyan.position.set(-L * 0.9, L * 0.25, -L * 0.9);
        this._rimOrange.position.set(L * 1.0, -L * 0.35, -L * 0.7);
        cam.far = Math.max(dist, L) * 30;
        cam.updateProjectionMatrix();
        // CAD kipindeyken geometri değişimi ortografik kadrajı da tazeler
        if (this.state.cadMode) this.setCadPreset(this._cadPresetName || 'iso');
    };

    MotorScene.prototype._bindResize = function () {
        var self = this;
        this._ro = new ResizeObserver(function () {
            if (self._disposed) return;
            var w = self.container.clientWidth, h = self.container.clientHeight;
            if (w < 10 || h < 10) return;
            self._perspCam.aspect = w / h;
            self._perspCam.updateProjectionMatrix();
            self.renderer.setSize(w, h);
            // CAD kipinde ortografik frustum yeni en-boy oranına oturtulur
            if (self.state.cadMode) {
                self.setCadPreset(self._cadPresetName || 'iso');
            }
        });
        this._ro.observe(this.container);
    };

    // Dil değişiminde beyan çipleri yeniden çizilir (canvas sprite metni
    // DOM değildir; i18n.js'in translateTree'si ona ulaşamaz). Dinleyici
    // dispose'da bırakılır — sızıntı yok.
    MotorScene.prototype._bindLangChange = function () {
        var self = this;
        this._langHandler = function () {
            if (self._disposed) return;
            self._refreshStatusChips();
        };
        document.addEventListener('hrma:langchange', this._langHandler);
    };

    // ------------------------------------------------------------------
    // Ana döngü
    // ------------------------------------------------------------------

    MotorScene.prototype._tick = function () {
        var dt = Math.min(this._clock.getDelta(), 0.05);
        // Görünmezlik bekçisi (görev 3): konteyner display:none bir atanın
        // altındaysa offsetParent null döner — render, simülasyon ve geometri
        // işi tamamen atlanır; yalnız controls damping sönümü işletilir.
        // (RAF döngüsü sürer; sekme geri gelince kaldığı yerden devam eder.
        // Gizli-sekme kurulum/resize akışına dokunulmaz — 2026-07-13 dersleri.)
        if (!this.container.offsetParent) {
            this.controls.update();
            return;
        }
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
            if (st.time >= d.burnTime) {
                st.time = d.burnTime;
                st.playing = false;
                // Yanma sonu: eşikli atlamaların bıraktığı son dilimi kapat —
                // nihai geometri bir kez kesin kurulur
                this._grainFinal = true;
            }
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

        // Port regresyonu: grain eşikli (GRAIN_REBUILD_*) yeniden kurulur;
        // yanma sonunda son dilim force ile kapatılır (görev 1).
        // Yarıçap GERÇEK seriden gelir; kip animasyonsuzsa sabit kalır.
        var rP = portRadiusAt(d, st.time, this._portRegMode);
        this._rebuildGrain(rP, this._grainFinal === true);
        this._grainFinal = false;
        // Parıltı silindiri: her karede geometri kurmak yerine mevcut mesh'e
        // radyal ölçek uygulanır; oran aşırı sapınca bir kez tazelenir
        if (this._glowMesh && d.motorType !== 'liquid' && this._glowBuiltPort) {
            var sGlow = clamp(rP / this._glowBuiltPort, 0.5, 2.5);
            if (sGlow > 2.0 || sGlow < 0.55) {
                this._rebuildGlow(rP);
            } else {
                this._glowMesh.scale.set(sGlow, 1, sGlow);
            }
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
            // Koni katmanı parçacıklarla AYNI görünürlük sözleşmesini izler
            if (this._flameGroup) this._flameGroup.visible = this._plume.visible;
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

        // Otomatik kalite bekçisi (görev 3): son AUTO_PERF_FRAME_WINDOW
        // karenin ortalama süresi limiti aşarsa 'perf' moduna geçilir.
        // Tek sefer tetiklenir — kullanıcı HQ'ya elle dönerse zorlanmaz;
        // intro dolly'si sırasında (ısınma) ölçüm yapılmaz.
        if (!this._perfMode && !this._autoPerfDone && this._introT >= 1) {
            this._dtSum = (this._dtSum || 0) + dt;
            this._dtCount = (this._dtCount || 0) + 1;
            if (this._dtCount >= AUTO_PERF_FRAME_WINDOW) {
                var dtAvg = this._dtSum / this._dtCount;
                this._dtSum = 0;
                this._dtCount = 0;
                if (dtAvg > AUTO_PERF_DT_LIMIT) {
                    this._autoPerfDone = true;
                    this.setQuality('perf');   // hooks.onQualityChange deck'i bilgilendirir
                }
            }
        }

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
                // Yanan web kalınlığı (mm) ve gerilemenin kaynağı: sayı
                // yalnız gerçek seri varsa yayınlanır, yoksa null.
                webBurnedMm: burnedWebAt(d, st.time, this._portRegMode),
                portRegression: this._portRegMode,
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
        // Kesit değişimi gerileme kipini de değiştirebilir (dairesel
        // olmayan kesitte radyal gerileme modellenmez) — kip ve beyan
        // çipleri geometriyle BİRLİKTE tazelenir.
        this._resolvePortRegression();
        this._refreshStatusChips();
        this._rebuildGrain(portRadiusAt(this.dims, this.state.time, this._portRegMode), true);
        // Parıltı da yeni kesitin iç teğet yarıçapına göre tazelenir
        // (cache/ölçek referansı _rebuildGlow içinde sıfırlanır)
        this._rebuildGlow(portRadiusAt(this.dims, this.state.time, this._portRegMode));
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
        var oldRad = (this.dims.rcOut + this.dims.flangeLip) || 1;
        this.dims = extractDims(motorData);
        // Transient eğri bağlıysa zaman çizelgesi gerçek yanma süresinde
        // kalır — tasarım modu güncellemesi burnTime'ı tasarım sabitine
        // geri döndürmesin (görev 5c)
        if (this._transient) this.dims.burnTime = this._transient.tEnd;
        this.state.time = clamp(this.state.time, 0, this.dims.burnTime);
        this._lastPortR = -1;
        this._buildMotor();
        this._buildLabels();
        // Kamera refit ÖNCE: parçacık boyutu kadraj mesafesinden (_camDist)
        // türediği için plume tazelemesi güncel mesafeyle yapılmalı (kalem 1).
        // Uzunluk VEYA dış yarıçap (rcOut+flangeLip) yüzde 15'ten fazla
        // değiştiyse yeniden oturt (görev 5b — yalnız uzunluğa bakmak çap
        // sliderında kadrajı bayat bırakıyordu)
        var newRad = this.dims.rcOut + this.dims.flangeLip;
        if (Math.abs(this._totalLen - oldLen) / oldLen > 0.15 ||
            Math.abs(newRad - oldRad) / oldRad > 0.15) {
            this._fitCamera();
            this._introT = 1;
            this.camera.position.copy(this._camHome);
        }
        if (this._plume) {
            this._plumeInfo = this._plumeAero();   // yeni geometri → yeni jet fiziği
            this._plumeLen = plumeLengthMm(this._totalLen);
            // Koni katmanı yeni çıkış durumuyla yeniden kurulur; elmas
            // ölçekleri koniye hizalandığı için konumlardan ÖNCE gelir
            this._rebuildFlameCone();
            this._updateDiamondPositions();
            this._plume.material.size = plumeParticleSize(this.dims.re,
                this._camDist, this.container.clientHeight || 520);
            for (var i = 0; i < this._plumeN; i++) this._resetParticle(i, true);
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
        // CAD kipinde sıfırlama aktif ortografik preseti yeniden oturtur
        if (this.state.cadMode) {
            this.setCadPreset(this._cadPresetName || 'iso');
            return;
        }
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
    // Kamera preset'leri: iso (ana), side (tam yan), nozzle (lüle bölgesi),
    // injector (baş taraf). iso/side/injector mesafeyi _camHome
    // yarıçapından alır; nozzle artık lüle bölgesine ODAKLI ikincil
    // kadrajdır (kalem 4): hedef çıkış düzlemi + jet çekirdeği, mesafe
    // nozzleRegion kutusuna oturtulur — tam gövde mesafesi değil.
    MotorScene.prototype.setCameraPreset = function (name) {
        // CAD kipinde perspektif preset istekleri en yakın ortografik
        // görünüşe yönlendirilir (deck butonları CAD'de de iş görsün)
        if (this.state.cadMode) {
            var cadMap = { iso: 'iso', side: 'side', nozzle: 'front', injector: 'top' };
            return this.setCadPreset(cadMap[name] || 'iso');
        }
        var r = this._camHome.length();
        var target = new THREE.Vector3(0, 0, 0);
        var p;
        if (name === 'nozzle' && this._nozzleInfo) {
            var d = this.dims;
            var aspect = this.camera.aspect || 1.54;
            var reg = nozzleRegion(this._totalLen, d.re, d.rcOut + d.flangeLip);
            var fit = cameraFrameFit(reg.halfLen, reg.radius, CAMERA_FOV_DEG, aspect);
            var zExitW = this._nozzleInfo.zExit - this._zCenter;
            target.set(zExitW + reg.targetOffset, 0, 0);
            p = new THREE.Vector3(0.62, -0.22, 1).normalize()
                .multiplyScalar(fit.dist).add(target);
        } else {
            var presets = {
                iso: this._camHome.clone(),
                side: new THREE.Vector3(0, 0, r),
                injector: new THREE.Vector3(-r * 0.85, r * 0.25, r * 0.35)
            };
            p = presets[name] || presets.iso;
        }
        this.camera.position.copy(p);
        this.controls.target.copy(target);
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
        var label = perf ? 'perf' : 'high';
        // Deck / sayfa butonu gerçek durumu göstersin (otomatik perf düşüşü
        // dahil) — kanca yoksa sessizce geçilir
        if (this.hooks.onQualityChange) {
            try { this.hooks.onQualityChange(label); } catch (e) { /* UI yok */ }
        }
        return label;
    };
    // ------------------------------------------------------------------
    // CAD kipi (v2.6.27, kalem 4): ortografik görünüşler + teknik-resim
    // leader ölçüleri + nötr stüdyo. Kip geçişi durum KAYBETMEZ: kesit,
    // zaman çizelgesi, patlatma, etiket görünürlüğü aynen sürer; perspektif
    // kamera konumu girişte saklanır, çıkışta birebir geri yüklenir.
    // ------------------------------------------------------------------

    MotorScene.prototype.setCadMode = function (on) {
        on = !!on;
        if (this.state.cadMode === on) return on;
        this.state.cadMode = on;
        if (on) this._enterCad(); else this._exitCad();
        // Ölçü etiketleri kipe uygun tarzda yeniden kurulur (CAD'de leader)
        this._buildLabels();
        this._syncToolbar();
        return on;
    };

    MotorScene.prototype._enterCad = function () {
        // Mevcut görünüm + stil durumu saklanır (çıkışta geri yüklenir)
        this._cadSaved = {
            pos: this.camera.position.clone(),
            target: this.controls.target.clone(),
            background: this.scene.background,
            rimCyan: this._rimCyan.intensity,
            rimOrange: this._rimOrange.intensity,
            autoRotate: this.state.autoRotate
        };
        this._introT = 1;   // giriş dolly'si CAD kadrajını ezmesin
        if (!this._orthoCam) {
            this._orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 10);
        }
        this.camera = this._orthoCam;
        this.setCadPreset(this._cadPresetName || 'iso');
        // Nötr stüdyo (kalem 4c): koyu-nötr fon, jant ışıkları kapalı,
        // sade ızgara, mat malzemeler — hepsi gerçek duruma bağlı stil,
        // süs animasyonu yok; çıkışta aynen geri alınır.
        this.scene.background = new THREE.Color(0x14171c);
        this._rimCyan.intensity = 0;
        this._rimOrange.intensity = 0;
        this.state.autoRotate = false;
        this._applyCadGridStyle(true);
        this._applyCadMaterials(true);
    };

    MotorScene.prototype._exitCad = function () {
        var s = this._cadSaved || {};
        this.camera = this._perspCam;
        this._makeControls(this.camera);
        if (s.pos) this.camera.position.copy(s.pos);
        this.controls.target.copy(s.target || new THREE.Vector3(0, 0, 0));
        if (s.background) this.scene.background = s.background;
        this._rimCyan.intensity = (s.rimCyan !== undefined) ? s.rimCyan : 0.55;
        this._rimOrange.intensity = (s.rimOrange !== undefined) ? s.rimOrange : 0.15;
        this.state.autoRotate = !!s.autoRotate;
        this._applyCadGridStyle(false);
        this._applyCadMaterials(false);
        this._cadSaved = null;
    };

    // Izgara stili: CAD'de nötr gri, sade; normal kipte GridHelper'ın
    // kuruluş değerleri (vertexColors + 0.35 opaklık) deterministiktir,
    // saklamak yerine doğrudan geri yazılır.
    MotorScene.prototype._applyCadGridStyle = function (on) {
        if (!this._grid) return;
        var m = this._grid.material;
        if (on) {
            m.vertexColors = false;
            m.color.setHex(0x3d434b);
            m.opacity = 0.22;
        } else {
            m.vertexColors = true;
            m.color.setHex(0xffffff);
            m.opacity = 0.35;
        }
        m.needsUpdate = true;
    };

    // Malzeme stili: CAD'de mat (düşük metalness, yüksek roughness, sönük
    // yansıma). Orijinal değerler malzeme üstünde saklanır ve çıkışta
    // birebir geri yüklenir — malzemeler paylaşımlı olduğundan kalıcı
    // mutasyon bırakılmaz.
    MotorScene.prototype._applyCadMaterials = function (on) {
        var mats = this.mats;
        if (!mats) return;
        Object.keys(mats).forEach(function (k) {
            var m = mats[k];
            if (!m || !m.isMaterial) return;
            if (on) {
                if (m.userData._cadOrig === undefined) {
                    m.userData._cadOrig = {
                        metalness: m.metalness,
                        roughness: m.roughness,
                        envMapIntensity: m.envMapIntensity
                    };
                }
                if (m.metalness !== undefined) m.metalness = Math.min(m.metalness, 0.15);
                if (m.roughness !== undefined) m.roughness = Math.max(m.roughness, 0.75);
                if (m.envMapIntensity !== undefined) m.envMapIntensity = 0.15;
            } else if (m.userData._cadOrig !== undefined) {
                var o = m.userData._cadOrig;
                if (o.metalness !== undefined) m.metalness = o.metalness;
                if (o.roughness !== undefined) m.roughness = o.roughness;
                if (o.envMapIntensity !== undefined) m.envMapIntensity = o.envMapIntensity;
                delete m.userData._cadOrig;
            }
        });
    };

    // Ortografik görünüş preseti: front | top | side | iso. Frustum
    // matematiği saf orthoPresetFrustum'dadır (bekçi testli); burada yalnız
    // kameraya uygulanır. Up vektörü değişebildiği için controls yeniden
    // bağlanır (r128 OrbitControls up'ı kuruluşta yakalar).
    MotorScene.prototype.setCadPreset = function (name) {
        if (!this.state.cadMode || !this._orthoCam) return null;
        name = ORTHO_PRESETS[name] ? name : 'iso';
        this._cadPresetName = name;
        var L = this._totalLen || 100;
        var R = (this.dims.rcOut + this.dims.flangeLip) || 10;
        var aspect = (this.container.clientWidth || 800) /
            (this.container.clientHeight || 520);
        var f = orthoPresetFrustum(name, L / 2, R, aspect);
        var cam = this._orthoCam;
        cam.left = -f.halfW; cam.right = f.halfW;
        cam.top = f.halfH; cam.bottom = -f.halfH;
        cam.near = 1;
        cam.far = f.dist * 4;
        cam.up.set(f.up.x, f.up.y, f.up.z);
        cam.position.set(f.dir.x * f.dist, f.dir.y * f.dist, f.dir.z * f.dist);
        cam.lookAt(0, 0, 0);
        cam.updateProjectionMatrix();
        this._makeControls(cam);
        this.controls.target.set(0, 0, 0);
        this.controls.update();
        this._syncToolbar();
        return name;
    };

    // ------------------------------------------------------------------
    // Araç çubuğu: CAD kipi anahtarı + ortografik görünüş butonları.
    // Koyu HUD temasıyla TUTARLI: textSprite rozetleriyle aynı mono
    // tipografi ve renk ailesi (camgöbeği çerçeve, koyu zemin).
    // ------------------------------------------------------------------

    MotorScene.prototype._buildToolbar = function () {
        if (getComputedStyle(this.container).position === 'static') {
            this.container.style.position = 'relative';
        }
        var bar = document.createElement('div');
        bar.style.cssText = [
            'position:absolute', 'top:8px', 'right:8px', 'z-index:5',
            'display:flex', 'gap:4px', 'align-items:center',
            'font:600 11px "SF Mono","JetBrains Mono",Consolas,monospace'
        ].join(';');
        var self = this;
        function mkBtn(label, title) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.title = title || label;
            b.style.cssText = [
                'padding:3px 8px', 'border-radius:6px', 'cursor:pointer',
                'background:rgba(4,12,20,0.78)',
                'border:1px solid rgba(0,229,255,0.45)',
                'color:#9beaf7', 'font:inherit', 'letter-spacing:0.4px'
            ].join(';');
            bar.appendChild(b);
            return b;
        }
        this._cadPresetBtns = {};
        [['front', 'ÖN'], ['top', 'ÜST'], ['side', 'YAN'], ['iso', 'İZO']]
            .forEach(function (pr) {
                var b = mkBtn(pr[1], 'Ortografik görünüş: ' + pr[1]);
                b.style.display = 'none';
                b.addEventListener('click', function () {
                    self.setCadPreset(pr[0]);
                });
                self._cadPresetBtns[pr[0]] = b;
            });
        this._cadBtn = mkBtn('CAD',
            'CAD kipi: ortografik görünüşler + teknik ölçüler + nötr stüdyo');
        this._cadBtn.addEventListener('click', function () {
            self.setCadMode(!self.state.cadMode);
        });
        this._toolbar = bar;
        this.container.appendChild(bar);
        this._syncToolbar();
    };

    MotorScene.prototype._syncToolbar = function () {
        if (!this._toolbar) return;
        var on = !!this.state.cadMode;
        var self = this;
        if (this._cadBtn) {
            this._cadBtn.style.background = on
                ? 'rgba(0,229,255,0.22)' : 'rgba(4,12,20,0.78)';
            this._cadBtn.style.color = on ? '#e8f9ff' : '#9beaf7';
        }
        Object.keys(this._cadPresetBtns || {}).forEach(function (k) {
            var b = self._cadPresetBtns[k];
            b.style.display = on ? '' : 'none';
            var active = on && self._cadPresetName === k;
            b.style.borderColor = active
                ? 'rgba(0,229,255,0.9)' : 'rgba(0,229,255,0.45)';
            b.style.background = active
                ? 'rgba(0,229,255,0.22)' : 'rgba(4,12,20,0.78)';
        });
    };

    // PNG kare yakalama (görev 7): render hemen ardından senkron toDataURL —
    // arabellek aynı görev içinde okunduğu için preserveDrawingBuffer gerekmez
    MotorScene.prototype.snapshot = function () {
        this.renderer.render(this.scene, this.camera);
        return this.renderer.domElement.toDataURL('image/png');
    };
    MotorScene.prototype.dispose = function () {
        this._disposed = true;
        if (this._raf) cancelAnimationFrame(this._raf);
        if (this._ro) this._ro.disconnect();
        if (this._langHandler) {
            document.removeEventListener('hrma:langchange', this._langHandler);
            this._langHandler = null;
        }
        // OrbitControls DOM dinleyicilerini bırak (görev 8 — sızıntı önlemi)
        if (this.controls && this.controls.dispose) this.controls.dispose();
        // Ortam küp dokusu sahne grafiğinde değil scene.environment'ta durur;
        // traverse onu görmez, açıkça bırakılır
        if (this._envTex) this._envTex.dispose();
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
        // Araç çubuğu DOM'u da bırakılır (mount zaten innerHTML temizler,
        // ama dispose tek başına da sızıntısız olmalı)
        if (this._toolbar && this._toolbar.parentNode === this.container) {
            this.container.removeChild(this._toolbar);
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
        // CAD kipi (v2.6.27): ortografik görünüşler + teknik ölçüler
        setCadMode: function (on) { return viz ? viz.setCadMode(on) : null; },
        setCadPreset: function (name) { return viz ? viz.setCadPreset(name) : null; },
        // Kaynak-renk eşlemesi dışa açık: sayfa/deck çipleri aynı tabloyu
        // kullanabilir (tasarım dili tek gerçeklik)
        SOURCE_COLORS: SOURCE_COLORS,
        setQuality: function (mode) { return viz ? viz.setQuality(mode) : null; },
        // Görünür karenin PNG data-URL'i (indirme butonları için)
        snapshot: function () { return viz ? viz.snapshot() : null; },
        get: function () { return viz; },
        dispose: function () { if (viz) { viz.dispose(); viz = null; } }
    };
})();
