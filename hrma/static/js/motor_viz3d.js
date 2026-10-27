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

    /* ÖH D35 / OH-GT-25 — EKRAN SAYISI TEK KAYNAKTAN (i18n.js kanonu).

       ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/D35/sayi-bicimi/a1/once.json +
       ana modelin tarayıcı sayımı, 22 Eylül, TR oturum): ekrana giden
       ondalıklar NOKTA ile basılıyordu — hibrit 202 / katı 210 / sıvı 95
       noktalı ondalık, buna karşılık yalnız 36 / 20 / 30 virgüllü. Sebep
       tek bir hata değil, DESENDİ: ayraç kararı her çağrı yerinde ayrı
       ayrı `toFixed` ile veriliyordu, yani kural ekranın yüzlerce yerinde
       tekrarlanıyordu.

       Bu üç yardımcı kararı i18n.js'e devreder (`I18N.number` /
       `I18N.unit` / `I18N.percent`); ayraç `ondalikAyraci()` TEK
       kaynağından okunur. Basamak sayısı DEĞİŞMEZ: çağıran `toFixed(1)`
       dediyse yine bir basamak basılır, yalnız ayraç yerelleşir — aksi
       hâlde ekranda ölçülmemiş bir duyarlık ilan edilirdi (i18n.js:309
       künyesi). Sözlük motoru yoksa eski davranışa düşülür: sayı
       UYDURULMAZ, yalnız ayraç yerelleşmez (panellerin `_num` deseni,
       cfd_panel.js:207). `typeof window` kontrolü BİLEREK: solid.html'in
       dürüst biçimlendirici bloğu node'da DOM'suz koşturuluyor
       (tests/test_ui_no_fabricated_numbers.py). */
    function numTxt(v, d) {
        return (typeof window !== 'undefined' && window.I18N && window.I18N.number)
            ? window.I18N.number(v, d)
            : ((typeof v === 'number' && isFinite(v))
                ? (d === undefined ? String(v) : v.toFixed(d)) : String(v));
    }
    function unitTxt(v, unit, d) {
        return (typeof window !== 'undefined' && window.I18N && window.I18N.unit)
            ? window.I18N.unit(v, unit, d)
            : (numTxt(v, d) + (unit ? '\u00A0' + unit : ''));
    }
    function pctTxt(v, d) {
        return (typeof window !== 'undefined' && window.I18N && window.I18N.percent)
            ? window.I18N.percent(v, d) : (numTxt(v, d) + '%');
    }
    /* ÖH D36 / sahne-hud — ÖNCEDEN BİÇİMLENMİŞ SAYI METNİ (colorbar tikleri).
       `cfdTickLabel` saf kalır (bekçiler onu tek başına koşturur) ve
       ECMA-262 gereği NOKTA basar; ayraç YALNIZ burada, i18n.js'in
       `decimalText` kanalından yerelleşir (basamak değişmez, ters yön yok). */
    function decTxt(text) {
        return (typeof window !== 'undefined' && window.I18N
                && typeof window.I18N.decimalText === 'function')
            ? window.I18N.decimalText(text) : text;
    }

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

    // Patlatılmış görünüm: parça başına eksenel ofset (× toplam boy × f).
    // TEK KAYNAK — hem _applyExplode hem gölge kadrajı (eksen boyu patlatma
    // ile büyür, gölge frustumu buna göre açılır) buradan okur.
    var EXPLODE_OFFSETS = {
        closure: -0.48, casing: -0.30, injector: -0.16,
        liner: -0.06, grain: 0.10, nozzle: 0.30
    };

    // Zemin düzlemi: dış yarıçapın bu katı kadar aşağıda (gölge düzlemi +
    // ızgara + durum çipleri aynı düzlemi paylaşır — floorYMm tek kaynak).
    var FLOOR_DROP_RATIO = 1.9;

    // ==================================================================
    // RENDER_QUALITY — fotogerçekçi sunum katmanının TEK KAYNAĞI (B7)
    //
    // Malzeme / ışık / gölge sayısal parametreleri YALNIZ burada durur;
    // sahne kodu literal yazmaz (bekçi: tests/test_viz3d_render_kalite.py).
    // Her alanın yanında ESKİ değeri yazılıdır: geri dönüş tek noktadan.
    //
    // KİMLİK DIŞARIDA: neon jant ışıkları (_rimCyan 0x00e5ff / _rimOrange
    // 0xff7a1a) ve yanma ışıkları (_combLight / _exitLight) bilerek tabloya
    // ALINMADI — onlar sahnenin renk kimliği ve gerçek yanma verisine bağlı
    // dinamik ışıklardır; değerleri kimlik bekçisiyle dondurulmuştur.
    // VERİ KATMANLARI DIŞARIDA: ısı haritası (vertexColors) ve CFD alan
    // karoları ölçüm gösterir, sunum değil — kendi bekçileri vardır.
    // ==================================================================
    var RENDER_QUALITY = {
        shadow: {
            // Ölçüm (2026-08-18, varsayılan hibrit L=1670 mm, R=65 mm):
            // gölge kamerası ±L kare frustumdu ve near hiç ayarlanmıyordu
            // (r128 varsayılanı 0,5). Teksel 2·L/2048 = 1,63 mm.
            mapSizeHigh: 4096,        // eski: 2048 (kaliteden bağımsız sabit)
            mapSizePerf: 1024,        // eski: 2048 (perf kipi gölgeyi düşürmüyordu)
            fitMargin: 1.04,          // frustum kenar payı (kırpılma emniyeti)
            // Derinlik bias'ı DÜNYA ölçüsünden türetilir: r128 gölge
            // gölgelendiricisi `shadowCoord.z += shadowBias` yapar ve
            // ortografik kamerada derinlik doğrusaldır ⇒
            //   bias = -biasDepthMm / (far - near)
            // Kadraj daraldıkça (far-near küçülür) bias otomatik büyür.
            biasDepthMm: 0.5,         // eski: bias = 0 (varsayılan, akne riski)
            normalBiasTexels: 1.5,    // eski: normalBias = 0 — teksel × 1,5
            floorOpacity: 0.32        // eski: 0.32 (DEĞİŞMEDİ — gerekçe raporda)
        },
        lights: {
            // Üç nokta düzeni: anahtar + dolgu + (mevcut) jant ışıkları.
            // Yayınık bütçe KORUNUR: hemi'den alınan 0,30 dolguya verildi.
            //   eski: key 0,95 + hemi 0,55            = 1,50
            //   yeni: key 0,95 + hemi 0,25 + fill 0,30 = 1,50
            // key/fill oranı 3,17 — sinematografik 2:1..4:1 bandında.
            keyColor: 0xffffff, keyIntensity: 0.95,      // eski: 0.95 (aynı)
            keyDir: { x: 0.8, y: 1.1, z: 0.7 },          // eski: aynı konum kuralı
            hemiSky: 0x93a7c4, hemiGround: 0x0a0e14,     // eski: aynı renkler
            hemiIntensity: 0.25,                          // eski: 0.55
            // Dolgu rengi = gökyüzü rengi: bu ışık ambiyansın YÖNLÜ hâlidir,
            // renk dengesi (dolayısıyla kimlik) değişmesin diye aynı jeton.
            fillIntensity: 0.30,                          // eski: dolgu YOKTU
            fillDir: { x: -0.85, y: 0.55, z: 0.75 },
            diffuseBudget: 1.50                           // key+hemi+fill (kilit)
        },
        texture: {
            // Fırça izi silindir yüzeyinde SIYIRMA açısıyla görülür — izotropik
            // mipmap bandı bulanıklaştırıp titretir. r128 anizotropik süzmeyi
            // destekler (capabilities.getMaxAnisotropy) — 8 yaygın tavan, sürücü
            // sınırıyla ayrıca kısılır.
            brushedAnisotropy: 8                          // eski: 1 (varsayılan)
        },
        // PBR yüzey malzemeleri. envMapIntensity ÖLÇÜLDÜ: grain/grainCut/
        // liner/linerCut/oring/orifice alanı hiç yazmıyordu ⇒ r128 varsayılanı
        // 1,0 ile ortam haritasını TAM alıyorlardı — açıkça yazılmış her malzeme
        // ≤0,75 ve her kesit yüzü 0,2 idi. Tutarsızlık kapatıldı.
        materials: {
            casing: { color: 0x9fabbc, metalness: 0.72, roughness: 0.42,
                      envMapIntensity: 0.70, brushed: true, bumpScale: 0.12,
                      // Anodize/boyalı alüminyum kasa ince bir dielektrik kat
                      // taşır: taban fırça izinin ÜSTÜNDE bakışa bağlı ayrı bir
                      // parlama. r128 MeshPhysicalMaterial clearcoat destekler.
                      clearcoat: 0.18, clearcoatRoughness: 0.42 }, // eski: clearcoat YOK
            casingCut: { color: 0xc3ccd8, metalness: 0.15, roughness: 0.90,
                         envMapIntensity: 0.20, cut: true },
            nozzle: { color: 0x525c68, metalness: 0.78, roughness: 0.38,
                      envMapIntensity: 0.75 },
            nozzleCut: { color: 0x76818f, metalness: 0.10, roughness: 0.95,
                         envMapIntensity: 0.20, cut: true },
            graphite: { color: 0x23262a, metalness: 0.42, roughness: 0.78,
                        envMapIntensity: 0.50 },
            graphiteCut: { color: 0x393e45, metalness: 0.10, roughness: 0.95,
                           envMapIntensity: 0.20, cut: true },
            grain: { color: 0x6d4326, metalness: 0.0, roughness: 0.94,
                     envMapIntensity: 0.45 },              // eski: örtük 1.0
            grainCut: { color: 0x936243, metalness: 0.0, roughness: 1.0,
                        envMapIntensity: 0.20, cut: true }, // eski: örtük 1.0
            liner: { color: 0x23282e, metalness: 0.05, roughness: 0.90,
                     envMapIntensity: 0.40 },              // eski: örtük 1.0
            linerCut: { color: 0x3a4046, metalness: 0.0, roughness: 1.0,
                        envMapIntensity: 0.20, cut: true }, // eski: örtük 1.0
            injector: { color: 0xb08d57, metalness: 0.85, roughness: 0.38,
                        envMapIntensity: 0.65 },
            injectorCut: { color: 0xd2b184, metalness: 0.20, roughness: 0.85,
                           envMapIntensity: 0.20, cut: true },
            bolt: { color: 0x343b44, metalness: 0.85, roughness: 0.40,
                    envMapIntensity: 0.60 },
            steel: { color: 0x6f7883, metalness: 0.90, roughness: 0.32,
                     envMapIntensity: 0.70 },
            oring: { color: 0x121417, metalness: 0.0, roughness: 0.97,
                     envMapIntensity: 0.35 },              // eski: örtük 1.0
            orifice: { color: 0x10151a, metalness: 0.20, roughness: 0.80,
                       envMapIntensity: 0.35 }             // eski: örtük 1.0
        }
    };

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

    // --- Zemin düzlemi (tek kaynak) -----------------------------------
    // Gölge düzlemi, ızgara ve durum çipleri aynı y'yi paylaşır; gölge
    // kamerası da bu düzlemi kadrajına almak zorunda (aşağıya bkz.).
    function floorYMm(rOuterMm) {
        return -rOuterMm * FLOOR_DROP_RATIO;
    }

    // --- Gölge kamerası kadrajı (B7, kalem 1) -------------------------
    // Ölçüm (2026-08-18): key ışığın ortografik gölge kamerası ±L kare
    // frustumla kuruluyordu (L = motorun TAM boyu) ve near hiç
    // ayarlanmıyordu (r128 varsayılanı 0,5). Oysa model ışık düzlemine
    // izdüşürüldüğünde çok daha küçük bir alan kaplar: varsayılan hibritte
    // (L=1670 mm, R=65 mm) yarı genişlik 598 mm, yarı yükseklik 529 mm.
    // Yani gölge dokusunun ~%88'i boşa gidiyordu (teksel 1,63 mm).
    //
    // Yeni kural — kadraj ışığın KENDİ tabanına oturur:
    //   * taban three.js'in lookAt kuralıyla birebir kurulur:
    //       ẑ = normalize(ışıkKonumu - hedef),  x̂ = normalize(up × ẑ),
    //       ŷ = ẑ × x̂        (hedef = orijin, up = +Y)
    //   * modelin AABB köşeleri x̂/ŷ'ye izdüşürülür → halfW/halfH
    //   * köşelerin ZEMİNE düşen gölgeleri ışık ekseni boyunca kaydığı için
    //     x̂/ŷ izdüşümünü DEĞİŞTİRMEZ, yalnız derinliği uzatır → far
    //   * patlatılmış görünümde eksen boyu büyür (EXPLODE_OFFSETS)
    // Kırpılma emniyeti: r128 gölge gölgelendiricisi frustum dışını
    // AYDINLIK sayar (`frustumTest` → shadow = 1.0), yani dar kadraj
    // kenarda bant artefaktı üretmez; kırpılan tek şey gölgenin kendisi
    // olurdu — bekçi köşeleri bağımsız izdüşürüp bunu sınar.
    //
    // Bias'lar teksel boyundan TÜRETİLİR (sabit literal değil):
    //   normalBias = normalBiasTexels × max(tekselW, tekselH)   [mm]
    //   bias       = -biasDepthMm / (far - near)                [birimsiz]
    // İkincisi r128'in `shadowCoord.z += shadowBias` satırının ortografik
    // (doğrusal derinlik) karşılığıdır; sonuç literatürün -1e-4..-5e-4
    // bandına kendiliğinden oturur (bekçi bandı sınar).
    function shadowFrustumFit(halfAxisMm, radiusMm, floorYMm_, lightPos,
                              mapSize, margin) {
        var m = margin || 1.0;
        var lp = [lightPos.x, lightPos.y, lightPos.z];
        var dist = Math.sqrt(lp[0] * lp[0] + lp[1] * lp[1] + lp[2] * lp[2]);
        var z = [lp[0] / dist, lp[1] / dist, lp[2] / dist];   // ẑ (ışığa doğru)
        // x̂ = normalize(up × ẑ); up = +Y ⇒ (z[2], 0, -z[0])
        var xl = Math.sqrt(z[2] * z[2] + z[0] * z[0]);
        var x = xl > 1e-9 ? [z[2] / xl, 0, -z[0] / xl] : [1, 0, 0];
        var y = [z[1] * x[2] - z[2] * x[1],
                 z[2] * x[0] - z[0] * x[2],
                 z[0] * x[1] - z[1] * x[0]];                  // ŷ = ẑ × x̂
        var halfW = 0, halfH = 0, dMin = Infinity, dMax = -Infinity;
        var sx, sy, sz, p, s, fp, du;
        for (sx = -1; sx <= 1; sx += 2) {
            for (sy = -1; sy <= 1; sy += 2) {
                for (sz = -1; sz <= 1; sz += 2) {
                    p = [sx * halfAxisMm, sy * radiusMm, sz * radiusMm];
                    halfW = Math.max(halfW, Math.abs(
                        p[0] * x[0] + p[1] * x[1] + p[2] * x[2]));
                    halfH = Math.max(halfH, Math.abs(
                        p[0] * y[0] + p[1] * y[1] + p[2] * y[2]));
                    // derinlik: ışıktan noktaya uzaklık = dist - (p·ẑ)
                    du = dist - (p[0] * z[0] + p[1] * z[1] + p[2] * z[2]);
                    dMin = Math.min(dMin, du);
                    dMax = Math.max(dMax, du);
                    // köşenin zemine düşen gölgesi (ışık ekseni boyunca)
                    if (z[1] > 1e-9) {
                        s = (p[1] - floorYMm_) / z[1];
                        fp = [p[0] - s * z[0], floorYMm_, p[2] - s * z[2]];
                        du = dist - (fp[0] * z[0] + fp[1] * z[1] + fp[2] * z[2]);
                        dMax = Math.max(dMax, du);
                    }
                }
            }
        }
        halfW *= m;
        halfH *= m;
        var pad = (dMax - dMin) * (m - 1) / 2 + 1;
        var near = Math.max(dMin - pad, dist * 0.01);
        var far = dMax + pad;
        var texelW = 2 * halfW / mapSize;
        var texelH = 2 * halfH / mapSize;
        return {
            halfW: halfW, halfH: halfH, near: near, far: far, dist: dist,
            texelW: texelW, texelH: texelH,
            normalBias: RENDER_QUALITY.shadow.normalBiasTexels *
                Math.max(texelW, texelH),
            bias: -RENDER_QUALITY.shadow.biasDepthMm / (far - near)
        };
    }

    // Patlatma açıkken eksen yarı boyu: en büyük |ofset| iki yöne de
    // uygulanır (emniyetli üst sınır — kırpılma yerine biraz fazla kadraj).
    function shadowAxisHalfMm(totalLenMm, explodeF) {
        var mx = 0;
        Object.keys(EXPLODE_OFFSETS).forEach(function (k) {
            mx = Math.max(mx, Math.abs(EXPLODE_OFFSETS[k]));
        });
        return totalLenMm * (0.5 + mx * Math.max(0, Math.min(1, explodeF || 0)));
    }

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
    //
    // ÖH D21 / P17B1-09 (yüksek) — SAHNE OTURUM DİLİNİ İZLER.
    // ÖLÇÜLDÜ (P17 B1-tur-07, tarayıcı yereli `en-US`, sayfanın rozetleri
    // İngilizce): 3B tuvalde beş etiket SABİT TÜRKÇE basılıyordu — 'ızgara
    // 10 mm', 'ØC iç 80.0 / dış 90.0 mm', 'kontur: çözücü', 'kontur: yerel
    // üretim', 'soğutma kanalları: veri yok'. Turun sahneye ayırdığı iki
    // denetim (tuval_dolu, plume_cizildi) PİKSEL sayar, yazıya hiç bakmaz;
    // bu yüzden hüküm değişmiyordu. Etiketler artık aynı dosyadaki T()
    // kanalından geçer (anahtar yoksa İngilizce tam metin döner, anahtar
    // adı ekrana ASLA yazılmaz) — sayılar biçimlendirmeyi değiştirmez,
    // yalnız çevresindeki sözcükler dile bağlanır.
    function gridBadgeText(cellMm) {
        return T('viz3d.badge.grid', 'grid') + ' ' + cellMm + ' mm';
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
    // P11B1-05 (ölçüldü, sıvı varsayılan koşu): 'ODA' etiketi çözücünün
    // yanma odası boyunu değil, YAKIT ÇEKİRDEĞİ yedeğini yazıyordu. Sıvı
    // motorda grain_length yayımlanmaz, bu yüzden dims() içindeki
    //     Lg = num(gd.grain_length_mm, num(md.grain_length, 0.8*Lch/1000)*1000)
    // yedeğe düşüyor ve etiket oda boyunun 0,8 KATINI basıyordu
    // (78,0 ⟷ 97,96 mm). Bu uydurma sayıdır (sahte veri yasağı).
    // Artık sıvıda ODA doğrudan çözücünün chamber_length'inden gelir;
    // çözücü onu yayımlamadıysa (chamberLengthKaynakli false) etiketin o
    // yarısı HİÇ YAZILMAZ — fail-closed, yedek sayı basılmaz.
    function dimensionLabelTexts(v) {
        var total = 'L ' + numTxt(v.totalMm, 0) + ' mm';
        // ÖH D23 / P17B1-09 (ayak 1) — SON İKİ SABİT TÜRKÇE SÖZCÜK.
        // ÖLÇÜLDÜ (a2 once.json: ham_turkce_YAKIT = 1, ham_turkce_ODA = 1):
        // D21 sahnedeki beş etiketi T() kanalına bağlamıştı; hükmün (H1)
        // kaynak taramasının KAÇIRDIĞI altıncı etiket burasıydı — ekranda
        // `L 668 mm • YAKIT 506 mm` diye okunuyor ve `en-US` oturumda da
        // Türkçe kalıyordu. Sayı biçimi değişmez, yalnız çevresindeki
        // sözcük oturum diline bağlanır.
        if (v.motorType === 'liquid') {
            if (v.chamberLengthKaynakli && isFinite(v.chamberLengthMm)) {
                total += '  •  ' + T('viz3d.label.chamber', 'CHAMBER') + ' '
                    + numTxt(v.chamberLengthMm, 0) + ' mm';
            }
        } else {
            total += '  •  ' + T('viz3d.label.grain', 'GRAIN') + ' '
                + numTxt(v.grainMm, 0) + ' mm';
        }
        return {
            // P17B1-09: 'iç' / 'dış' sözcükleri oturum dilinden gelir.
            chamber: 'ØC ' + T('viz3d.badge.inner', 'inner') + ' '
                + numTxt(v.chamberInnerMm, 1) + ' / '
                + T('viz3d.badge.outer', 'outer') + ' '
                + numTxt(v.chamberOuterMm, 1) + ' mm',
            throat: 'ØT ' + numTxt(v.throatMm, 1) + ' mm',
            exit: 'ØE ' + numTxt(v.exitMm, 1) + ' mm',
            total: total
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
    // ÖH D32 · OH-D31-18 — `assumed` ambersi artık TOKEN KATMANINDA
    // tanımlı (`--hd-amber-source`, theme.css + hd_doc.css) ve DEĞERİ
    // DEĞİŞMEDİ. Tablo `var()` kullanamaz: bu değerler `textSprite`in
    // canvas `fillStyle`ına ve `new THREE.Color(...)`a gidiyor, ikisi de
    // CSS değişkeni çözmez. Ayna tokene bekçiyle kilitli:
    // tests/test_d32_arayuz_panel_a1.py::TestOHD3118AmberTokeni.
    var SOURCE_COLORS = {
        computed: '#39d6ec',
        user: '#e8edf2',
        assumed: '#ffb347',      // = var(--hd-amber-source)
        missing: '#8a93a0'
    };

    // ÖH D26 / P11B1-09 — SİMGE TABLOSU analysis_dock.js ile BİREBİR.
    // Renk tek başına ayırt edici değildir (renk körlüğü); panodaki çip ile
    // sahnedeki çip AYNI durumu AYNI simgeyle göstermek zorundadır, yoksa
    // kullanıcı iki ayrı görsel dil öğrenmek zorunda kalır.
    var SOURCE_SYMBOLS = {
        computed: '●',
        user: '■',
        assumed: '◆',
        missing: '×'
    };

    function sourceColor(kind) {
        return SOURCE_COLORS[kind] || SOURCE_COLORS.missing;
    }

    function sourceSymbol(kind) {
        return SOURCE_SYMBOLS[kind] || SOURCE_SYMBOLS.missing;
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

    // ==================================================================
    // CFD alan katmanı saf fonksiyonları (2026-08-17, parti 30 — A2)
    //
    // /api/cfd/nozzle yanıtındaki hücre-merkezli r-z alanını (Mach /
    // statik basınç / statik sıcaklık) sahnenin ZATEN açık olan kesit
    // kamasına ANSYS tarzı renkli kesit olarak bağlayan matematik.
    // THREE'siz saf fonksiyonlardır; bekçi testleri
    // (tests/test_viz3d_cfd_alan.py) metinden çıkarıp node ile izole
    // sınar.
    //
    // Veri sözleşmesi (hrma/app.py::api_cfd_nozzle yanıtı, data.cfd):
    //   field: { z_m, r_m, mach, pressure_Pa, temperature_K?, shape,
    //            grid_shape, axial_indices, radial_indices, decimated }
    //     — her dizi [eksenel][radyal] iç içe liste; radyal indeks 0
    //     eksene komşu hücre, son indeks duvara komşu hücre; değerler
    //     HÜCRE MERKEZLİ çözücü hücreleri, enterpolasyonsuz. İnceltme
    //     YALNIZ eksenel (radyal yön hiç seyrelmez).
    //   grid:  { ni, nj, z_inlet_m, z_exit_m, r_throat_m, r_exit_m, ... }
    // ==================================================================

    // --- Hizalama toleransları (ÖLÇÜLDÜ, 2026-08-17) -------------------
    // Uç, duvar polilinesini ni+1 DÜZGÜN eksenel istasyona doğrusal ara
    // değerle yeniden örnekler (hrma/app.py::_cfd_build_grid →
    // hrma.cfd.grid_axisym.build_grid_from_wall). Bu yeniden örneklemenin
    // geometri çapalarında yarattığı GERÇEK sapma Python'da ölçüldü
    // (gerçek sample_nozzle_inner_contour konturları: konik 40/60/100 mm
    // oda + bell hibrit + 8 mm boğazlı küçük konik; yayımlı çözünürlük
    // beyaz listesinin İKİ seviyesinde — coarse 60×12, standard 120×24):
    //   * z_inlet / z_exit / r_exit: sapma TAM 0 — linspace uçları ve
    //     np.interp'in uç değeri kontur ucunu bit-aynı korur, JSON double
    //     gidiş-dönüşü kayıpsızdır. 1e-9 bağıl tolerans saf float
    //     emniyetidir (ölçülen sinyalin 0 olduğu yerde bağ değildir).
    //   * r_throat: yeniden örnekleme istasyonu gerçek boğaz noktasını
    //     ıskalayabilir; ölçülen en kötü bağıl sapma 4,27e-3 (coarse,
    //     küçük konik). Bu POLİGON-min uzaklığı kullanıcıya bilgi olarak
    //     beyan edilmeye devam eder (dr_throat_mm) ama KAPI artık onunla
    //     kurulmaz — aşağıdaki parti 33 hükmüne bak (beyan yeniden
    //     üretimi, dr_throat_node_mm).
    var CFD_ALIGN_EXACT_REL_TOL = 1e-9;
    // Boğaz çapası kapısı (parti 33 hükmü): eski 8,6e-3 sabiti kalibre
    // edilmiş bir AİLE ölçümüydü (2× en kötü: konik 40/60/100 + bell hibrit
    // + küçük konik) ve ailenin dışındaki sıvı bell konturunda GERÇEK
    // yeniden-örnekleme sapması kılpayı dışarı taştı (canlı ölçüm, 18 Ağu:
    // dr_throat 0,147 mm / minR ≈ %0,98 > %0,86 → alan sahneye hiç
    // inemiyordu). Aileyi büyütmek yerine ucun YAYIMLADIĞI kural sahnede
    // yeniden üretilir: "the wall polyline is resampled onto ni+1 uniform
    // axial stations by linear interpolation" (grid._basis / koşum kartı).
    // Sahne konturu aynı kurala sokulup DÜĞÜM-min ↔ DÜĞÜM-min
    // karşılaştırılır; fark artık örnekleme yoğunluğundan bağımsız saf
    // float gürültüsüdür (m→mm ölçek + JSON gidiş-dönüşü; ölçülen
    // < 1e-12 bağıl). 1e-9 emniyet payı gerçek kontur uyuşmazlığının
    // (yüzde-onlarca) >=6 dekad altındadır. Ucun kuralı değişirse
    // tests/test_viz3d_cfd_alan.py::_kaynak_bagi_dogrula bağı kopar ve
    // süit kırmızıya düşer — kural kopyası sürüklenemez.
    var CFD_ALIGN_R_THROAT_REPRO_REL_TOL = 1e-9;
    // Radyal düzgünlük eşiği: yükün kendi beyanı "the radial distribution
    // is uniform from axis to wall" (grid._basis). Düzgün dağılımda bir
    // istasyondaki ardışık hücre-merkez farkları eşittir; ölçülen float
    // gürültüsü <= 5,2e-12 bağıl (grid_axisym r_centers, coarse+standard).
    // 1e-8 = gürültünün ~2000 katı; gerçek sıkıştırılmış (Aşama 2 sınır
    // tabakası) dağılımın yüzde-mertebe farkının 6 dekad altı.
    var CFD_RADIAL_UNIFORM_REL_TOL = 1e-8;

    // Kontur z'sinden sahne z'sine dönüşümün TEK KAYNAĞI. Çözücü konturu
    // mm'ye çevrilmiş hâliyle dims.contourPoints'te durur (z origin'i
    // çözücünün kendi origin'idir); sahnede konverjan başlangıcı
    // dims.Lch'ye oturtulur. nozzleInnerContour ve CFD alan katmanı AYNI
    // fonksiyonu çağırır — ikinci bir ofset formülü yazılmaz (refaktor
    // bit-aynılığı bekçili: tests/test_viz3d_cfd_alan.py).
    function contourZToScene(dims, zMm) {
        if (!dims || !dims.contourPoints || !dims.contourPoints.length) {
            return NaN;
        }
        return dims.Lch + (zMm - dims.contourPoints[0].z);
    }

    // Ucun beyan ettiği yeniden örnekleme sahne konturunda yeniden
    // üretilir: ni+1 düzgün z istasyonu, doğrusal interpolasyon, en küçük
    // DÜĞÜM yarıçapı. cfdFieldAlignment'ın boğaz kapısı bunun çıktısıyla
    // karşılaştırır (düğüm-min ↔ düğüm-min; polygon-min ile DEĞİL — o fark
    // örnekleme yoğunluğuna bağlıdır ve kullanıcıya bilgi olarak ayrıca
    // beyan edilir).
    function cfdReproThroatNodeR(pts, ni) {
        var z0 = pts[0].z, z1 = pts[pts.length - 1].z;
        var minR = Infinity, seg = 0;
        for (var k = 0; k <= ni; k++) {
            var z = z0 + (z1 - z0) * k / ni;
            while (seg < pts.length - 2 && pts[seg + 1].z < z) seg++;
            var a = pts[seg], b = pts[seg + 1];
            var r = (b.z === a.z) ? a.r
                : a.r + (b.r - a.r) * (z - a.z) / (b.z - a.z);
            if (r < minR) minR = r;
        }
        return minR;
    }

    // Geometri çapa denetimi: CFD ızgarası sahnede çizilen konturla aynı
    // geometriden mi kuruldu? Sahne konturu yerel üretimse (contourSource
    // !== 'solver') ızgara başka geometridir — yanlış hizalanmış alan
    // çizmektense reddedilir. Çapalar: giriş/çıkış z'si, boğaz ve çıkış
    // yarıçapı (uç yanıtındaki grid bloğu vs sahne kontur noktaları).
    function cfdFieldAlignment(cfd, dims) {
        var grid = cfd && cfd.grid;
        if (!grid || typeof grid !== 'object') {
            return { ok: false, code: 'bad_field_block',
                     params: { missing: 'grid' } };
        }
        var pts = dims && dims.contourPoints;
        if (!pts || pts.length < 3 || dims.contourSource !== 'solver') {
            return { ok: false, code: 'no_solver_contour', params: {} };
        }
        var zi = num(grid.z_inlet_m, NaN) * 1000;
        var ze = num(grid.z_exit_m, NaN) * 1000;
        var rt = num(grid.r_throat_m, NaN) * 1000;
        var rx = num(grid.r_exit_m, NaN) * 1000;
        var ni = num(grid.ni, NaN);
        if (!isFinite(zi) || !isFinite(ze) || !isFinite(rt)
            || !isFinite(rx)) {
            return { ok: false, code: 'bad_field_block',
                     params: { missing: 'grid anchors' } };
        }
        if (!isFinite(ni) || ni < 2) {
            return { ok: false, code: 'bad_field_block',
                     params: { missing: 'grid.ni' } };
        }
        var cz0 = pts[0].z, cz1 = pts[pts.length - 1].z;
        var minR = Infinity;
        for (var i = 0; i < pts.length; i++) {
            if (pts[i].r < minR) minR = pts[i].r;
        }
        var cRx = pts[pts.length - 1].r;
        var axLen = Math.max(cz1 - cz0, 1e-9);
        // dr_throat_mm: kontur POLİGON minimumuna uzaklık — kullanıcıya
        // beyan edilen bilgi (örnekleme istasyonu gerçek boğazı ne kadar
        // ıskaladı). KAPI bununla değil, beyan yeniden üretimiyle kurulur:
        // dr_throat_node_mm = |ızgara boğazı - aynı kuralla sahneden
        // üretilen düğüm-min|.
        var rtRepro = cfdReproThroatNodeR(pts, Math.round(ni));
        var meas = {
            dz_inlet_mm: Math.abs(zi - cz0),
            dz_exit_mm: Math.abs(ze - cz1),
            dr_throat_mm: Math.abs(rt - minR),
            dr_throat_node_mm: Math.abs(rt - rtRepro),
            dr_exit_mm: Math.abs(rx - cRx)
        };
        var mismatch =
            meas.dz_inlet_mm > CFD_ALIGN_EXACT_REL_TOL * axLen ||
            meas.dz_exit_mm > CFD_ALIGN_EXACT_REL_TOL * axLen ||
            meas.dr_exit_mm > CFD_ALIGN_EXACT_REL_TOL * cRx ||
            meas.dr_throat_node_mm > CFD_ALIGN_R_THROAT_REPRO_REL_TOL * minR;
        if (mismatch) {
            return { ok: false, code: 'contour_mismatch', params: meas };
        }
        return { ok: true, dz_inlet_mm: meas.dz_inlet_mm,
                 dz_exit_mm: meas.dz_exit_mm,
                 dr_throat_mm: meas.dr_throat_mm,
                 dr_throat_node_mm: meas.dr_throat_node_mm,
                 dr_exit_mm: meas.dr_exit_mm };
    }

    // Her eksenel istasyonun duvar yarıçapı [m] — yükün kendi beyanından
    // TÜRETİLİR, uydurulmaz: "the radial distribution is uniform from
    // axis to wall" (grid._basis) ise hücre merkezi r_c[j] =
    // (j+0,5)·r_duvar/nj olur → r_duvar = r_c[nj-1]·nj/(nj-0,5). Türetme
    // öncesi düzgünlük VERİDEN doğrulanır (ardışık merkez farkları eşit
    // mi, ilk merkez yarım adımda mı — eksene komşuluk beyanı); değilse
    // null döner ve çağıran 'bad_field_block' ile reddeder.
    //
    // NE KADAR "DUVAR"? (ölçüldü 2026-08-17, parti 30 denetimi) — bu
    // türetme ETKİN bir yarıçap verir, iki düğüm yarıçapının aritmetik
    // ortası DEĞİL. Sebep ızgaranın kendi sözleşmesidir: r_centers hücre
    // merkezi olarak DÜZLEMSEL AĞIRLIK MERKEZİNİ yayımlar
    // (grid_axisym.AxisymGrid docstring), eğimli duvarda yamuk hücrenin
    // ağırlık merkezi orta noktadan kayar ve kayma bir sütun boyunca SAF
    // ÖLÇEK olduğu için düzgünlük denetimini bozmaz. ÖLÇÜLDÜ, ürünün
    // KENDİ örnekleyicisiyle (nozzle_design.sample_nozzle_inner_contour;
    // 3 kontur — konik / bell / geniş oda — × yayımlı iki seviye, düğüm
    // ortasına göre bağıl): en kötü 7,54e-4, geniş odalı koniğin 60×12
    // ızgarasında, mutlak 0,0171 mm. Sapma KONTUR BİÇİMİNE bağlıdır,
    // evrensel bir tavan değildir: aynı ölçüm keskin köşeli elle yazılmış
    // bir poligonla 4,06e-3'e (0,070 mm) çıktı — örnekleyici köşeleri
    // yumuşattığı için üründe o rejim görülmüyor. Türetilen değer HER
    // ölçümde istasyonu sınırlayan iki düğüm yarıçapının BANDININ
    // İÇİNDE kaldı; korunan değişmez budur ve bekçisi vardır
    // (tests/test_viz3d_cfd_alan.py::TestDuvarYaricapi). Render
    // ölçeğinde görünmez, ama sayı beyansız bırakılmaz.
    function cfdWallRadii(field) {
        var rm = field && field.r_m;
        if (!Array.isArray(rm) || rm.length < 2) return null;
        // ------------------------------------------------------------------
        // YAYIMLANMIŞ RADYAL GEOMETRİ (parti 40) — TÜRETME DEĞİL OKUMA.
        // Uç artık her yayımlanan istasyonun nj+1 radyal DÜĞÜM yarıçapını
        // taşıyor (field.radial_geometry). Blok varsa duvar yarıçapı
        // TÜRETİLMEZ, son düğümden OKUNUR ve düzgünlük hükmü UCUN
        // ÖLÇÜMÜNDEN alınır — burada yeniden ölçülmez.
        //
        // NEDEN 'ada değil ölçüme bak': dağılımın AİLE ADI 'uniform'
        // kalırken geometri düzgün OLMAYABİLİR (duvar-normal yaka düzgün
        // bir dağılımın üstüne kurulunca ad değişmez, düğümler eşit
        // aralıklı olmaktan çıkar — ölçülen aralık sapması 4,7e-01).
        // O yüzden bloğun `radial_distribution` ADI değil `radial_uniform`
        // ÖLÇÜMÜ okunur.
        //
        // NEDEN DÜZGÜN OLMAYAN YÜK YİNE DE REDDEDİLİYOR: bu katmanın karo
        // kurucusu (aşağıdaki CFD katman kurucu işlevi — adı bu yorumda
        // BİLEREK yazılmadı, çünkü tests/test_viz3d_cfd_alan.py::
        // test_metrik_degisimi_geometri_kurmaz o adın KAYNAKTAKİ geçiş
        // sayısını sayıyor ve bir yorum bile o bekçiyi yanlış ateşler)
        // radyal bandı hâlâ [j/nj, (j+1)/nj] diye
        // kuruyor, yani EŞİT ARALIK varsayıyor. Duvar yarıçapını doğru
        // okumak o varsayımı düzeltmez; gerdirilmiş bir yükü çizmek
        // SESSİZCE YANLIŞ çizmek olurdu. Karo modeli mutlak düğüm
        // yarıçaplarına geçene kadar red DOĞRU davranıştır ve çağıran onu
        // 'bad_field_block' olarak beyan eder.
        var rg = field.radial_geometry;
        if (rg && Array.isArray(rg.r_nodes_m)
                && rg.r_nodes_m.length === rm.length) {
            if (rg.radial_uniform !== true) return null;
            var okunan = [];
            for (var k = 0; k < rg.r_nodes_m.length; k++) {
                var dugum = rg.r_nodes_m[k];
                var satir = rm[k];
                if (!Array.isArray(dugum) || !Array.isArray(satir)
                        || dugum.length !== satir.length + 1) {
                    return null;
                }
                var rw = num(dugum[dugum.length - 1], NaN);
                if (!isFinite(rw) || !(rw > 0)) return null;
                okunan.push(rw);
            }
            return okunan;
        }
        // ESKİ YÜK YOLU (blok yok): bugünkü türetme korunur — geri uyum.
        var out = [];
        for (var i = 0; i < rm.length; i++) {
            var row = rm[i];
            if (!Array.isArray(row) || row.length < 2) return null;
            var d0 = num(row[1], NaN) - num(row[0], NaN);
            if (!isFinite(d0) || d0 <= 0) return null;
            for (var j = 0; j + 1 < row.length; j++) {
                var dj = num(row[j + 1], NaN) - num(row[j], NaN);
                if (!isFinite(dj)
                    || Math.abs(dj - d0) > CFD_RADIAL_UNIFORM_REL_TOL * d0) {
                    return null;
                }
            }
            // Eksene komşuluk: ilk hücre merkezi yarım adımda durmalı
            if (Math.abs(num(row[0], NaN) - 0.5 * d0)
                > CFD_RADIAL_UNIFORM_REL_TOL * d0) {
                return null;
            }
            var n = row.length;
            out.push(row[n - 1] * n / (n - 0.5));
        }
        return out;
    }

    // Eksenel hücre YÜZLERİ [m]: kalan (inceltilmiş) istasyon
    // merkezlerinin orta noktaları; iki uç grid.z_inlet_m / z_exit_m'e
    // oturur. İnceltilmiş veride kalan her istasyon, atlanan komşularını
    // da kapsayan bir BANT olarak çizilir — bu gerçeğin
    // basitleştirilmesidir ve colorbar'da beyan edilir ("N / M eksenel
    // istasyon"). İstasyon z'si satırın ilk hücresinden okunur (ölçüldü:
    // z_centers'ın j-yayılımı <= 1,3e-13 bağıl — istasyon içinde sabit).
    function cfdCellEdges(field, grid) {
        var zm = field && field.z_m;
        if (!Array.isArray(zm) || zm.length < 2) return null;
        var zi = num(grid && grid.z_inlet_m, NaN);
        var ze = num(grid && grid.z_exit_m, NaN);
        if (!isFinite(zi) || !isFinite(ze)) return null;
        var centers = [];
        for (var i = 0; i < zm.length; i++) {
            var row = zm[i];
            var v = Array.isArray(row) ? num(row[0], NaN) : num(row, NaN);
            if (!isFinite(v)) return null;
            centers.push(v);
        }
        var edges = [zi];
        for (var k = 1; k < centers.length; k++) {
            edges.push(0.5 * (centers[k - 1] + centers[k]));
        }
        edges.push(ze);
        for (var e = 0; e + 1 < edges.length; e++) {
            if (!(edges[e + 1] > edges[e])) return null;
        }
        return edges;
    }

    // 0..1 → '#rrggbb' (sRGB): durak listesi üstünde doğrusal ara renk.
    // Duraklar CFD_COLORSCALES biçimindedir: [[t, '#rrggbb'], ...].
    function cfdColorLookup(stops, t) {
        var tt = clamp(num(t, 0), 0, 1);
        function hexByte(h, k) { return parseInt(h.slice(k, k + 2), 16); }
        function toHex(v) {
            var s = Math.round(clamp(v, 0, 255)).toString(16);
            return s.length < 2 ? '0' + s : s;
        }
        if (tt <= stops[0][0]) return stops[0][1];
        var last = stops[stops.length - 1];
        if (tt >= last[0]) return last[1];
        for (var i = 1; i < stops.length; i++) {
            if (tt <= stops[i][0]) {
                var f = (tt - stops[i - 1][0])
                    / (stops[i][0] - stops[i - 1][0]);
                var a = stops[i - 1][1], b = stops[i][1];
                return '#'
                    + toHex(lerp(hexByte(a, 1), hexByte(b, 1), f))
                    + toHex(lerp(hexByte(a, 3), hexByte(b, 3), f))
                    + toHex(lerp(hexByte(a, 5), hexByte(b, 5), f));
            }
        }
        return last[1];
    }

    // Okunaklı tik değerleri (1-2-5 kuralı): [min, max] aralığına en
    // fazla ~n tik, adım {1,2,5}·10^k kademesinden. min==max tek değer
    // döner; bozuk girdi boş liste.
    function cfdColorbarTicks(min, max, n) {
        if (!isFinite(min) || !isFinite(max)) return [];
        if (max <= min) return [min];
        var count = (n >= 2) ? Math.floor(n) : 5;
        var raw = (max - min) / (count - 1);
        var mag = Math.pow(10, Math.floor(Math.log10(raw)));
        var norm = raw / mag;
        var step = mag * (norm < 1.5 ? 1 : (norm < 3.5 ? 2
            : (norm < 7.5 ? 5 : 10)));
        var k0 = Math.ceil(min / step - 1e-9);
        var k1 = Math.floor(max / step + 1e-9);
        var out = [];
        for (var k = k0; k <= k1; k++) out.push(k * step);
        return out;
    }

    // Tik/uç değer metni: yuvarlak tikler kısa ondalıkla, çok büyük/küçük
    // büyüklükler (Pa mertebesi) üstel gösterimle yazılır.
    function cfdTickLabel(v) {
        if (!isFinite(v)) return '';
        if (v === 0) return '0';
        var a = Math.abs(v);
        if (a >= 1e5 || a < 1e-3) {
            return v.toExponential(2).replace('e+', 'e');
        }
        return String(Math.round(v * 1e6) / 1e6);
    }

    // '{ad}' yer tutucularını doldurur (i18n şablon deseni — anahtar
    // metinleri {shown}/{total} taşır, sözlük sırasına bağımlı değildir).
    function cfdFormatTemplate(text, params) {
        return String(text).replace(/\{(\w+)\}/g, function (m, k) {
            return (params && params[k] !== undefined) ? String(params[k]) : m;
        });
    }

    // --- Renk skalaları: vendor Plotly tanımlarından BİREBİR -----------
    // Duraklar hrma/static/vendor/plotly-1.58.5.min.js içindeki Viridis /
    // Portland / Blackbody tanımlarından AYNEN alındı (rgb() değerleri
    // kayıpsız hex'e çevrildi; kesir konumları vendor'ın kendi ondalık
    // metnidir). 2B panel aynı tablodan beslenir — iki görünüm aynı
    // büyüklüğe aynı rengi gösterir. Bekçi: tests/test_viz3d_cfd_alan.py
    // tabloyu vendor dosyasından ayrıştırıp birebir karşılaştırır.
    var CFD_COLORSCALES = {
        mach: [
            [0, '#440154'], [0.06274509803921569, '#48186a'],
            [0.12549019607843137, '#472d7b'], [0.18823529411764706, '#424086'],
            [0.25098039215686274, '#3b528b'], [0.3137254901960784, '#33638d'],
            [0.3764705882352941, '#2c728e'], [0.4392156862745098, '#26828e'],
            [0.5019607843137255, '#21918c'], [0.5647058823529412, '#1fa088'],
            [0.6274509803921569, '#28ae80'], [0.6901960784313725, '#3fbc73'],
            [0.7529411764705882, '#5ec962'], [0.8156862745098039, '#84d44b'],
            [0.8784313725490196, '#addc30'], [0.9411764705882353, '#d8e219'],
            [1, '#fde725']
        ],
        pressure: [
            [0, '#0c3383'], [0.25, '#0a88ba'], [0.5, '#f2d338'],
            [0.75, '#f28f38'], [1, '#d91e1e']
        ],
        temperature: [
            [0, '#000000'], [0.2, '#e60000'], [0.4, '#e6d200'],
            [0.7, '#ffffff'], [1, '#a0c8ff']
        ]
    };

    // --- Metrik tablosu (sözleşme: id / payloadKey / unit / label) -----
    var CFD_METRICS = [
        { id: 'mach', payloadKey: 'mach', unit: '',
          labelKey: 'viz3d.cfd.metric.mach', labelFallback: 'Mach number' },
        { id: 'pressure', payloadKey: 'pressure_Pa', unit: 'Pa',
          labelKey: 'viz3d.cfd.metric.pressure',
          labelFallback: 'Static pressure' },
        { id: 'temperature', payloadKey: 'temperature_K', unit: 'K',
          labelKey: 'viz3d.cfd.metric.temperature',
          labelFallback: 'Static temperature' }
    ];

    // --- RED kodları (sözleşmedeki TAM küme — başka kod üretilmez) -----
    // Her red { ok:false, reason: {code, key, fallback, params} } döner;
    // key i18n anahtarıdır, fallback İngilizce tam metindir (T() deseni:
    // ekrana anahtar adı asla yazılmaz).
    var CFD_REASONS = {
        no_scene: { key: 'viz3d.cfd.err.noScene',
            fallback: 'The 3D scene is not mounted (WebGL unavailable or '
                + 'no motor loaded)' },
        no_solver_contour: { key: 'viz3d.cfd.err.noSolverContour',
            fallback: 'The scene contour is locally generated (no solver '
                + 'contour) - the CFD grid cannot be aligned to it' },
        contour_mismatch: { key: 'viz3d.cfd.err.contourMismatch',
            fallback: 'The CFD grid anchors deviate from the scene contour '
                + 'beyond the measured resampling tolerance' },
        missing_metric: { key: 'viz3d.cfd.err.missingMetric',
            fallback: 'The requested quantity is not present in the field '
                + 'payload' },
        bad_field_block: { key: 'viz3d.cfd.err.badFieldBlock',
            fallback: 'The CFD field block is missing or malformed' },
        no_field: { key: 'viz3d.cfd.err.noField',
            fallback: 'No CFD field is loaded - load a field before '
                + 'switching metrics' }
    };

    function cfdReason(code, params) {
        var r = CFD_REASONS[code];
        return { ok: false, reason: { code: code, key: r.key,
                 fallback: r.fallback, params: params || {} } };
    }

    // Alan bloğunun yapısal denetimi: null = sağlam, aksi hâlde kusuru
    // adlandıran params sözlüğü ('bad_field_block' gerekçesi olur).
    function cfdFieldBlockDefect(field) {
        if (!field || typeof field !== 'object') {
            return { missing: 'field' };
        }
        if (!Array.isArray(field.z_m) || !Array.isArray(field.r_m)) {
            return { missing: 'z_m/r_m' };
        }
        if (field.z_m.length !== field.r_m.length || field.z_m.length < 2) {
            return { missing: 'station rows' };
        }
        var hasMetric = false;
        for (var i = 0; i < CFD_METRICS.length; i++) {
            var arr = field[CFD_METRICS[i].payloadKey];
            if (Array.isArray(arr) && arr.length === field.z_m.length) {
                hasMetric = true;
            }
        }
        if (!hasMetric) return { missing: 'metric arrays' };
        return null;
    }

    // Yükte verilen metrik dizisi var mı? (id → payloadKey → dizi)
    function cfdFieldHasMetric(field, id) {
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (CFD_METRICS[i].id === id) {
                var arr = field && field[CFD_METRICS[i].payloadKey];
                return Array.isArray(arr) && arr.length > 0;
            }
        }
        return false;
    }

    // Metrik değerlerini [eksenel][radyal] düzeninden hücre sırasına açar
    // ve min/max ölçer. Sonlu olmayan değer → null (bozuk blok; uydurma
    // renk basılmaz).
    function cfdMetricValues(field, payloadKey) {
        var arr = field[payloadKey];
        if (!Array.isArray(arr) || arr.length !== field.z_m.length) {
            return null;
        }
        var nRad = field.r_m[0].length;
        var out = [], min = Infinity, max = -Infinity;
        for (var i = 0; i < arr.length; i++) {
            var row = arr[i];
            if (!Array.isArray(row) || row.length !== nRad) return null;
            for (var j = 0; j < nRad; j++) {
                var v = row[j];
                if (typeof v !== 'number' || !isFinite(v)) return null;
                out.push(v);
                if (v < min) min = v;
                if (v > max) max = v;
            }
        }
        return { values: out, min: min, max: max };
    }

    // ------------------------------------------------------------------
    // A1b faz-c-0 · K1b — PROBE (fare altı hücre okuması), saf katman
    // ------------------------------------------------------------------
    // Sözleşme: docs/tasarim/ui-yeniden/B2_ansys_analiz_sonuc.md §4
    // "Probe" + §7.1 K1b (B1 K1b; hakem uygulama B1). Alan katmanı hücre
    // başına İKİ kesit düzleminde ikişer üçgen kurar (12 köşe, hücre sırası
    // eksenel dış / radyal iç döngü) — r128 raycast'i indekssiz geometride
    // `faceIndex` = üçgen sırası verir, yani üçgen t hücre floor(t / 4)'ün
    // karosudur. Eşleme bekçisi GERÇEK geometri üstünde koşar
    // (tests/test_faz_c_k1b.py): kurulum değişip eşleme bozulursa yanlış
    // hücrenin sayısı yazılmaz, bekçi kırmızı olur.
    var CFD_PROBE_TRIS_PER_CELL = 4;

    function cfdProbeCell(faceIndex, nAx, nRad) {
        if (typeof faceIndex !== 'number' || !isFinite(faceIndex)
            || faceIndex < 0 || !(nAx > 0) || !(nRad > 0)) {
            return null;
        }
        var c = Math.floor(faceIndex / CFD_PROBE_TRIS_PER_CELL);
        if (c >= nAx * nRad) return null;
        return { cell: c, k: Math.floor(c / nRad), j: c % nRad };
    }

    // Okuma: değer yükteki dizinin KENDİ elemanıdır (field[payloadKey]
    // [k][j]; bit-aynı). CFD hücre merkezli, karo düzdür — ara değer
    // üretilmez, `interpolated` bu yolda daima false (künye yalnız gerçek
    // ara değerde basılır; FEA kabuğunun en yakın düğüm/eleman içi yolu
    // K3b'nin). Hücre künyesi çözücünün KENDİ indeksleridir
    // (axial_indices / radial_indices — inceltilmiş yükte atlanan
    // istasyonlar sayılır), konum hücre merkezinin yayımlanan z_m / r_m'si.
    // Sonlu olmayan değer → null (uydurma sayı basılmaz).
    function cfdProbeReading(L, hucre) {
        if (!L || !hucre) return null;
        var m = null;
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (CFD_METRICS[i].id === L.metric) m = CFD_METRICS[i];
        }
        if (!m) return null;
        var satir = (L.field[m.payloadKey] || [])[hucre.k];
        var v = Array.isArray(satir) ? satir[hucre.j] : undefined;
        if (typeof v !== 'number' || !isFinite(v)) return null;
        var zr = (L.field.z_m[hucre.k] || [])[hucre.j];
        var rr = (L.field.r_m[hucre.k] || [])[hucre.j];
        var ai = L.field.axial_indices, ri = L.field.radial_indices;
        var ii = Array.isArray(ai) ? num(ai[hucre.k], NaN) : hucre.k;
        var jj = Array.isArray(ri) ? num(ri[hucre.j], NaN) : hucre.j;
        return {
            metric: m.id, labelKey: m.labelKey,
            labelFallback: m.labelFallback,
            value: v, unit: m.unit,
            // k/j: katman (yük) indeksi; axial/radial: çözücü indeksi
            cell: { k: hucre.k, j: hucre.j,
                    axial: isFinite(ii) ? ii : hucre.k,
                    radial: isFinite(jj) ? jj : hucre.j },
            z_m: num(zr, null), r_m: num(rr, null),
            sampling: 'cell-centred', interpolated: false,
            decimated: !!L.decimated,
            stations: { shown: L.stationsShown, total: L.stationsTotal }
        };
    }

    // Probe satırının parçaları (ekran metni; sayılar I18N kanalından —
    // TR virgül; makine kanalı DOM özniteliğinde nokta). Doktrin (B2 §4c):
    // <metrik> <değer> [<birim>] · hücre (i, j) · konum · N/M istasyon.
    function probeLineParts(rd) {
        var parts = [
            { cls: 'metric', text: T(rd.labelKey, rd.labelFallback) },
            // Birim alan tanımından; birimsiz büyüklükte (Mach) boş
            { cls: 'value', text: unitTxt(rd.value, rd.unit) },
            { cls: 'meta', text: cfdFormatTemplate(
                T('viz3d.probe.cell', 'cell ({i}, {j})'),
                { i: rd.cell.axial, j: rd.cell.radial }) }
        ];
        if (typeof rd.z_m === 'number' && typeof rd.r_m === 'number') {
            parts.push({ cls: 'meta', text: cfdFormatTemplate(
                T('viz3d.probe.centre', 'cell centre z = {z} mm, r = {r} mm'),
                { z: numTxt(rd.z_m * 1000, 1), r: numTxt(rd.r_m * 1000, 1) }) });
        }
        if (rd.decimated && rd.stations) {
            parts.push({ cls: 'decl', text: cfdFormatTemplate(
                T('viz3d.cfd.stations', '{shown} / {total} axial stations'),
                { shown: rd.stations.shown, total: rd.stations.total }) });
        }
        if (rd.interpolated === true) {
            parts.push({ cls: 'decl',
                         text: T('viz3d.probe.interpolated', 'interpolated') });
        }
        return parts;
    }

    function probeLineText(rd) {
        return probeLineParts(rd).map(function (p) { return p.text; })
            .join(' · ');
    }

    // Tırnak işareti \u0022 kaçışıyla yazılır: kaynak tarayan bekçilerin
    // yorum söküçüleri (ör. D27 a1 olcum.py `yorumsuz`) düzenli ifade
    // değişmezindeki çıplak tırnağı dize başlangıcı sanıp kayıyor (ölçüldü).
    function probeHtmlEsc(t) {
        return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/\u0022/g, '&quot;');
    }

    // Parıltı silindirinin lathe-z aralığı — TEK KAYNAK: _rebuildGlow
    // geometriyi BU değerlerle kurar, CFD örtüşme ölçümü de aynı aralığı
    // okur (ikinci formül kopyası yazılmaz). İfade _rebuildGlow'un eski
    // satırlarının bire bir taşınmışıdır (bit-aynı).
    function glowZSpan(d) {
        var height = d.zg1 - d.zg0 + 0.6 * (d.Lch - d.zg1);
        var center = (d.zg0 + d.Lch) / 2;
        return { center: center, height: height,
                 lo: center - height / 2, hi: center + height / 2 };
    }

    // Dekoratif katman örtüşme ÖLÇÜMÜ (kod yolu): alan aktifken hangi
    // süs katmanları alanın sahne-z aralığıyla kesişiyor? Ölçülen gerçek
    // (varsayılan hibrit): parıltı silindiri z<=0,8·Lch+0,2·zg1 < Lch'de
    // biter, alan Lch'de başlar → parıltı KESİŞMEZ; boğaz alev diski
    // z=Lch+Lc alan aralığının içindedir → KESİŞİR ve alan aktifken
    // gizlenir (additive sprite alan renklerinin üstüne binerse colorbar
    // yalan söylerdi). Karar veriden: aralık kesişimi burada hesaplanır.
    function cfdOverlayConflicts(dims, z0SceneMm, z1SceneMm) {
        var span = glowZSpan(dims);
        var flameZ = dims.Lch + dims.Lc;
        return {
            throatFlame: flameZ > z0SceneMm && flameZ < z1SceneMm,
            glow: span.lo < z1SceneMm && span.hi > z0SceneMm
        };
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
    // CSS alfa metni (MAKİNE kanalı, dil bağımsız): 1e-4'e yuvarlanır;
    // [0,1] aralığında ECMA-262 `String` üstel gösterime geçmez (eşik
    // 1e-6) ve ondalık ayracı her zaman NOKTA'dır. Ekran biçimleyicisi
    // (numTxt / I18N.number) buraya GİRMEZ.
    function cssAlpha(a) {
        var v = Math.max(0, Math.min(1, Number(a) || 0));
        return String(Math.round(v * 1e4) / 1e4);
    }

    function flameSpriteTexture() {
        var c = makeCanvas(128, 128);
        var g = c.getContext('2d');
        var grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
        var stops = flameSpriteStops(9);
        for (var i = 0; i < stops.length; i++) {
            // ÖH D36 / sahne-hud a2 — MAKİNE KANALI: CSS renk dizesi.
            // ÖLÇÜLDÜ (raw/OH/D36/sahne-hud/a2/once.json): D35 sayı
            // kanonu bu alfa değerini ekran biçimlendiricisinden (numTxt
            // → I18N.number) geçiriyordu; TR oturumda dize
            // 'rgba(255,255,255,1,0000)' oluyor, addColorStop SyntaxError
            // atıyor ve MotorScene kurucusu (_buildPlume) çöküyordu: 3B
            // güverte Türkçe arayüzde HİÇ açılmıyordu. Renk dizesi CSS
            // sözdizimidir, dil değil: `cssAlpha` NOKTA basar.
            // Bekçi: tests/test_d36_sahne_a2.py
            grad.addColorStop(stops[i].t,
                'rgba(255,255,255,' + cssAlpha(stops[i].alpha) + ')');
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
    function brushedTexture(maxAnisotropy) {
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
        // Anizotropik süzme (B7 kalem 2): doku minFilter'ı varsayılan
        // LinearMipmapLinear'dır (ölçüldü: 1008), yani mipmap zinciri zaten
        // kuruluyor; silindirin siyirma açılı kısımlarında izotropik mipmap
        // fırça izini bulanıklaştırıp titretiyordu. Sürücü tavanı (r128
        // capabilities.getMaxAnisotropy) ayrıca kısıtlar.
        tex.anisotropy = Math.max(1, Math.min(
            RENDER_QUALITY.texture.brushedAnisotropy, maxAnisotropy || 1));
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
        // ÖH D26 / P11B1-09 — SİMGE DE BASILIR, yalnız renk değil.
        // Panodaki çip (analysis_dock.js::sourceChip) durumu
        // "simge + etiket" ikilisiyle gösteriyor; sahne yalnız renk
        // kullansaydı iki yüzey aynı hükmü iki ayrı görsel dille
        // anlatırdı ve renk körü kullanıcı sahnede hiçbir ayrım
        // göremezdi. Tablo iki dosyada birebirdir (bekçi:
        // test_d26_arayuz_a1.py::test_simge_tablosu_panoyla_birebir).
        return textSprite(sourceSymbol(kind) + ' ' + text,
                          { color: col, border: col });
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

    // ÖH D26 / P11B1-09: ikinci parametreden sonra İSTEĞE BAĞLI `out`
    // sözlüğü alır ve çizilen kalınlığın NEREDEN geldiğini `out.kind`
    // alanına yazar ('user' | 'computed' | 'assumed'). Eski iki argümanlı
    // çağrılar aynen çalışır — çizim davranışı değişmez, yalnız kaynak
    // hükmü artık dışarı verilir (önceden hiç verilmiyordu).
    function resolveCasingWall(md, Dch, out) {
        var o = out || {};
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
            if ((blk.design_mode === 'verify' || s[3]) && used !== null && used > 0) {
                // Kullanıcının/tasarımın as-designed cidarı çiziliyor.
                o.kind = 'user'; o.basis = s[0] + '.' + s[1];
                return used;
            }
            if (recommended !== null && recommended > 0) {
                o.kind = 'computed'; o.basis = s[0] + '.' + s[2];
                return recommended;
            }
            if (used !== null && used > 0) {
                o.kind = 'user'; o.basis = s[0] + '.' + s[1];
                return used;
            }
        }
        // Yapısal sonuç yok: sunucu tarafındaki AYNI geometrik yedek kural
        // (CHAMBER_WALL_FALLBACK_FRACTION = 0.045) — mesh ile çelişmesin.
        // Bu bir VARSAYIMDIR; sahne artık bunu çiple beyan eder.
        o.kind = 'assumed'; o.basis = 'geometric fallback 0.045·D';
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

        // Çıkış statik sıcaklığı. V301/K-C1 (N-CEA-2 §16 Y1): çözücü
        // yayımladıysa (`nozzle_design.performance.exit_temperature_k`; katıda
        // CEA yolunda T_c/γ/M_e'nin kendi seti) O okunur. Sahnenin kendi
        // türetmesi oda γ'sıyla yapıldığı için CEA T_e'den ~%3 sapıyordu
        // (APCP 40 bar: 2241 ⟷ 2318 K). Alan yoksa eski izentropik türetme
        // kalır ve `exitTemperatureBasis` ile beyan edilir:
        //     Te = Tc / (1 + (g-1)/2 * Me^2)
        var teYayim = num(perf.exit_temperature_k, NaN);
        var te, teDayanak;
        if (isFinite(teYayim) && teYayim > 0) {
            te = teYayim;
            teDayanak = 'solver: nozzle_design.performance.exit_temperature_k';
        } else {
            te = isFinite(tc) ? tc / (1 + 0.5 * (gamma - 1) * me * me) : NaN;
            teDayanak = isFinite(te)
                ? 'derived in the scene: isentropic Tc / (1 + (gamma-1)/2 Me^2); '
                  + 'the solver published no exit temperature'
                : null;
        }

        // Tam genişlemiş eşdeğer jet Mach sayısı Mj: akış pa basıncına kadar
        // izentropik genişleseydi ulaşacağı Mach. Toplam basınç korunur:
        //     1 + (γ−1)/2·Mj² = (p0/pa)^((γ−1)/γ),
        //     p0 = pe·(1 + (γ−1)/2·Me²)^(γ/(γ−1))
        //  => Mj² = 2/(γ−1)·[(pe/pa)^((γ−1)/γ)·(1 + (γ−1)/2·Me²) − 1]
        // pe = pa ⇒ Mj = Me (tam genişleme); aşırı-genişlemiş jette
        // (pe < pa) Mj < Me olur. Bağımsız sağlama: Norum & Seiner, NASA
        // TM-84521 (1982) Tablo 1 s. 191 (γ = 1,4; Pt/Pa 3,247 ↔ Mj 1,414).
        // KU-25 / H-4 düzeltmesi: eski kod köşeli ifadenin önüne "1 +"
        // ekleyip √(1 + Mj²) üretiyordu (pe = pa'da Me 2,56 iken 2,75).
        var mj = me;
        var mj2 = (2 / (gamma - 1)) * (Math.pow(pRatio, (gamma - 1) / gamma)
            * (1 + 0.5 * (gamma - 1) * me * me) - 1);
        if (isFinite(mj2) && mj2 > 0) mj = Math.sqrt(mj2);

        // Tam genişlemiş jet çapı D_j — aynı toplam koşulla izentropik
        // kütle korunumu: D_j = d_e·√[(A/A*)(Mj) / (A/A*)(Me)].
        // Kaynak: Wernet, Georgiadis & Locke, NASA/TM-20205007269 (2020)
        // Denk. (4) s. 41 (D_eff; SMC017 SP1664: D 50,8 mm → 47 mm).
        function areaRatio(m) {
            var t = (2 / (gamma + 1)) * (1 + 0.5 * (gamma - 1) * m * m);
            return Math.pow(t, (gamma + 1) / (2 * (gamma - 1))) / m;
        }
        var dj = num(md.exit_diameter, 0) * 1000
            * Math.sqrt(areaRatio(mj) / areaRatio(me));

        // Şok hücre aralığı — Prandtl-Pack doğrusal bağıntısı:
        //     L_s = 1.306 * D_j * sqrt(Mj^2 - 1)
        // Kaynak: Prandtl (1904); Pack, Q. J. Mech. Appl. Math. 3 (1950)
        // (künye CFD B1 P-M10'dan; özgün metin bu turda okunmadı).
        // GEÇERLİLİK BEYANI: doğrusal teori yalnız hafif basınç
        // uyumsuzluğunda geçerlidir — Love 1959, NASA TR R-6, Sonuç 1
        // s. 23: p_j/p_∞ ≈ 2 üstünde mevcut yöntemler yetersiz. Aşırı
        // genişlemiş ölçümlerde (Norum-Seiner M2,0; Wernet SP1664) D_j ile
        // bile ≈ %20-30 fazla tahmin eder. Sahnedeki aralık bu yüzden TEMSİLÎDİR,
        // ölçülmüş ya da CFD hücre boyu değildir. Mj <= 1 ise hücre yapısı
        // oluşmaz (ses altı jet).
        var cellSpacing = (mj > 1.02 && dj > 0)
            ? 1.306 * dj * Math.sqrt(mj * mj - 1)
            : 0;

        return {
            exitPressureBar: pe,
            ambientPressureBar: pa,
            pressureRatio: pRatio,
            exitMach: me,
            jetMach: mj,
            exitVelocity: ve,          // m/s
            exitTemperature: te,       // K (Tc yoksa NaN)
            exitTemperatureBasis: teDayanak,
            gamma: gamma,
            cellSpacingMm: cellSpacing,
            // pe > pa: az genişlemiş (jet çıkışta genişler, elmaslar belirgin)
            // pe < pa: aşırı genişlemiş (jet büzülür, şok içeri girer)
            expansionState: (pRatio > 1.05) ? 'under'
                : (pRatio < 0.95) ? 'over' : 'ideal'
        };
    }

    // ------------------------------------------------------------------
    // ÖH D27 / P11B1-09 + OH-D26-02 — BİRİNCİL ÖLÇÜ KAPISI (FAIL-CLOSED)
    // ------------------------------------------------------------------
    //
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D27/arayuz/a1/once.json): sahnenin
    // DÖRT birincil ölçüsü çözücüden gelmediğinde sessiz bir sabite
    // düşüyordu —
    //     num(md.chamber_diameter, 0.1)   num(md.chamber_length, 0.3)
    //     num(md.throat_diameter, 0.02)   num(md.exit_diameter, 0.08)
    // ve AYNI dört uydurma sayfa adaptörlerinde de vardı
    // (buildSolidVizData 0,1 / 0,3 / 0,02 / 0,08 m; buildLiquidVizData
    // 100 / 300 mm, 0,05 / 0,15 m). Node altında ölçüldü: çıplak bir
    // çözücü yanıtıyla iki adaptör de dördü de UYDURUYORDU, yani ekranda
    // ölçekli, ölçülü, gerçekmiş gibi duran 100 mm x 300 mm'lik bir motor
    // çiziliyordu ve kullanıcı onu kendi tasarımı sanıyordu.
    //
    // D26 bu düşüşü yalnız BEYAN etti (srcDecl defteri + amber çip).
    // Beyan çözüm değildir (doktrin 1): ölçü YOKSA sahne ÇİZİLMEZ ve
    // eksik alan ADIYLA reddedilir. Bu, sunucu tarafındaki `/calculate`
    // 422 kuralının ve katı sayfasının Plotly CAD yolundaki (v2.6.26,
    // Faz 2) "ölçü eksikse çizim yapılmaz" kuralının istemci karşılığıdır.
    var PRIMARY_DIM_FIELDS = ['chamber_diameter', 'chamber_length',
                              'throat_diameter', 'exit_diameter'];

    // Reddin kodu tek yerde yazılır (mount + update aynı kodu bildirir).
    // CFD red kodlarıyla AYNI KANAL DEĞİLDİR: bu kod CFD_REASONS'ta
    // aranmaz, karşılığı doğrudan i18n anahtarlarıyla (viz3d.reject.*)
    // ekrana yazılır. İki kanalın kod kümesi kesişmez.
    var DIMS_REJECT_CODE = 'missing_primary_dims';

    // Çözücünün YAYIMLAMADIĞI birincil ölçülerin adları (tablo sırasında).
    // Boş dizi = sahne çizilebilir.
    // --- ÖH D31 · OH-D27-13 — İKİNCİL ÖLÇÜ YEDEĞİ KÜNYESİZ OLAMAZ ------
    // 9 Eyl Berke kararı (madde 4) üç ayaklıydı: (a) künye zorunlu,
    // (b) panelde rozet, (c) künyesiz yedek fail-closed. D27'de (a) indi,
    // (b) yalnız 3B sahne çipi olarak indi, (c) hiç inmedi — ölçüldü
    // (a1/once.json · M3: `kunyesiz_yedek_fail_closed = 0`,
    // `panel_rozet_solid = 0`, `panel_rozet_advanced = 0`).
    //
    // Birincil ölçüler (`missingPrimaryDims`) zaten fail-closed'dır. Bu
    // kapı İKİNCİL türetilmiş yedekler içindir: casing_wall 0,045·D,
    // tane liner clamp(0,02·D), tane boyu 0,8·Lch. Bunların çizilmesi
    // meşrudur (boş tuval kullanıcıya bir şey söylemez) AMA künyesi
    // olmadan çizilmesi değildir: künyesiz bir varsayım kullanıcıya
    // "çözücü böyle dedi" diye görünür. Künye yoksa sahne ÇİZMEZ.
    var ASSUMED_DIM_NO_BASIS = 'assumed_dimension_without_basis';

    function AssumedDimError(alan) {
        this.name = 'AssumedDimError';
        this.reason = ASSUMED_DIM_NO_BASIS;
        this.field = alan;
        this.message = 'MotorViz3D: "' + alan + '" bir VARSAYIM ölçüsü ama '
            + 'künyesi (basis) yok. Künyesiz yedek çizilmez — yedeğin '
            + 'dayanağı adıyla yazılmalı (OH-D27-13, 9 Eyl Berke kararı).';
    }
    AssumedDimError.prototype = Object.create(Error.prototype);
    AssumedDimError.prototype.constructor = AssumedDimError;

    /** Künye kapısı: künyesiz VARSAYIM kaydı deftere giremez.
     *  Kaydı AYNEN döndürür ki çağıran yerde `srcDecl['x'] = ...` atama
     *  deseni (mevcut ölçüm betikleri ve bekçiler onu arar) bozulmasın. */
    function _kunyeKapisi(alan, kayit) {
        var tur = kayit && kayit.kind;
        var kunye = kayit && kayit.basis;
        if (tur !== 'computed' && tur !== 'user'
                && !(typeof kunye === 'string' && kunye.trim())) {
            throw new AssumedDimError(alan);
        }
        return kayit;
    }

    function missingPrimaryDims(md) {
        md = md || {};
        var eksik = [];
        for (var i = 0; i < PRIMARY_DIM_FIELDS.length; i++) {
            var ad = PRIMARY_DIM_FIELDS[i];
            var v = num(md[ad], NaN);
            if (!(isFinite(v) && v > 0)) eksik.push(ad);
        }
        return eksik;
    }

    // Sahnenin kurulmasını reddeden hüküm. Taşıdığı şey bir METİN değil,
    // ALAN LİSTESİDİR: çağıran hangi ölçünün eksik olduğunu adıyla okur.
    function MotorDimsError(missing) {
        this.name = 'MotorDimsError';
        this.code = DIMS_REJECT_CODE;
        this.missing = (missing || []).slice();
        this.message = 'motor_viz3d: missing primary dimensions: '
            + this.missing.join(', ');
    }
    MotorDimsError.prototype = Object.create(Error.prototype);
    MotorDimsError.prototype.constructor = MotorDimsError;

    // Reddin kullanıcıya görünen yüzü. Boş kutu ya da "bir hata oluştu"
    // YASAK (doktrin 1 + 6): hangi ölçünün gelmediği ADIYLA yazılır ve
    // hüküm çipleriyle aynı görsel dil kullanılır (SOURCE_SYMBOLS /
    // SOURCE_COLORS + DIM_SRC_LABEL_KEYS etiketleri).
    function renderDimsRejection(el, missing) {
        var kutu = document.createElement('div');
        kutu.className = 'viz3d-dims-reject';
        kutu.setAttribute('data-missing', (missing || []).join(','));
        kutu.style.cssText = 'display:flex;flex-direction:column;gap:8px;'
            + 'justify-content:center;min-height:220px;height:100%;'
            + 'padding:22px;box-sizing:border-box;border-radius:8px;'
            + 'font:13px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;'
            + 'color:#e8edf2;background:#0d1117;border:1px solid '
            + sourceColor('missing');

        var baslik = document.createElement('div');
        baslik.style.cssText = 'font-weight:600;letter-spacing:0.4px;color:'
            + sourceColor('assumed');
        baslik.textContent = sourceSymbol('missing') + ' '
            + T('viz3d.reject.title', '3D model not drawn');
        kutu.appendChild(baslik);

        var giris = document.createElement('div');
        giris.textContent = T('viz3d.reject.missingDims',
            'The solver did not publish these primary dimensions:');
        kutu.appendChild(giris);

        var liste = document.createElement('ul');
        liste.style.cssText = 'margin:0;padding-left:18px';
        (missing || []).forEach(function (alan) {
            var etiket = DIM_SRC_LABEL_KEYS[alan];
            var satir = document.createElement('li');
            satir.setAttribute('data-field', alan);
            satir.textContent = (etiket ? T(etiket[0], etiket[1]) : alan)
                + '  (' + alan + ')';
            liste.appendChild(satir);
        });
        kutu.appendChild(liste);

        var kural = document.createElement('div');
        kural.style.cssText = 'color:' + sourceColor('missing');
        kural.textContent = T('viz3d.reject.rule',
            'A model drawn from assumed dimensions would not be your design, '
            + 'so no substitute value is invented.');
        kutu.appendChild(kural);

        el.appendChild(kutu);
        return kutu;
    }

    // ==================================================================
    // A1a sahne-sahte-veri · CM-S1 — KESİRLE ÇİZİLEN PARÇA YOK
    // ==================================================================
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/A1a/sahne-sahte-veri/a1/once/,
    // üç örnek proje): sahne montaj parçalarını ÇÖZÜCÜNÜN YAYIMLAMADIĞI
    // ölçülerle, kamara yarıçapının / cidarının KESRİ olarak çiziyordu —
    // on bir kesir: kapak kalınlığı (1,6 x cidar), giriş borusu yarıçapı
    // (0,22 x rc) ve boyu (1,6 x kapak), grafit boğaz eki (0,35 x rt),
    // O-ring (0,16 x kapak), spigot (0,55 x kapak), kapak cıvatası
    // (0,3 x cidar), astar (rc - 0,15), enjektör plakası (0,9 x kapak),
    // ateşleyici (0,09 x rc), lüle cıvatası (0,05 x rc). Ekranda ölçekli,
    // gerçekmiş gibi duran bu parçaların hiçbiri kullanıcının tasarımı
    // değildi (CLAUDE.md 2026-07-29 sahte veri yasağı; CAD hakem #4).
    //
    // KURAL: parçanın ölçüsü çözücünün YAYIMLADIĞI yanıt alanından
    // geliyorsa O ALANDAN çizilir; gelmiyorsa parça ÇİZİLMEZ (kesirle
    // yedek YOK). Çizilmeyen parçaların SAYISI sahne çipinde beyan edilir
    // ("montaj planı yok — N parça çizilmedi"). Parçaları yerleşim
    // planıyla geri getirmek CM-3'ün (A6a) işidir.
    //
    // Alan adresleri (yanıtın kendi birimleri; hepsi mm):
    var PART_SOURCE_FIELDS = {
        closure_cap: ['structural_analysis', 'end_cap_analysis',
                      'flat_head_thickness'],
        chamber_liner: ['thermal_protection', 'chamber_liner', 'thickness'],
        injector_plate: ['injector_design', 'plate_thickness_mm'],
        bolt_count: ['structural_analysis', 'fastener_analysis', 'num_bolts'],
        bolt_circle: ['structural_analysis', 'fastener_analysis',
                      'bolt_circle_radius']
    };
    // Cıvata deliği: kartın adı `bolted_joint.clearance_hole_diameter_mm`;
    // cıvata analizörünün (hrma/analysis/bolted_joint.py) kendi çıktısında
    // aynı değer `bearing` bloğundadır. İkisi de okunur; bugün hiçbir
    // /calculate yanıtı yayımlamıyor (ölçüldü, üç örnek) → cıvata çizilmez.
    var BOLT_HOLE_FIELD_PATHS = [
        ['bolted_joint', 'clearance_hole_diameter_mm'],
        ['bolted_joint', 'bearing', 'clearance_hole_diameter_mm']
    ];
    // Cıvata çemberi bir yanıt ÖLÇÜSÜ SAYILMAZ: structural_analysis.py
    // `bolt_circle_radius = D/2 + 0,025` sabit yerleşim kuralıdır (CAD hakem
    // #4). Cıvata YALNIZ bu künyeyle çizilir; metin A2 cm-0-plan ASSUMED
    // tablosuyla birebir (makine dizesi — çevrilmez).
    var BOLT_CIRCLE_BASIS = 'assumed: fixed +25 mm layout rule';
    // Sahnenin çizebildiği montaj parçaları, motor tipine göre. Bir parça
    // ya yayımlanan alanından çizilir ya da çizilmeyenler listesine girer.
    var ASSEMBLY_PARTS = {
        hybrid: ['closure_cap', 'closure_seals', 'closure_spigot',
                 'closure_bolts', 'feed_inlet', 'injector_plate', 'igniter',
                 'chamber_liner', 'throat_insert', 'nozzle_flange',
                 'nozzle_seal', 'nozzle_bolts'],
        liquid: ['closure_cap', 'closure_seals', 'closure_spigot',
                 'closure_bolts', 'feed_inlet', 'injector_plate',
                 'throat_insert', 'nozzle_flange', 'nozzle_seal',
                 'nozzle_bolts'],
        solid: ['closure_cap', 'closure_seals', 'closure_snap_ring',
                'chamber_liner', 'throat_insert', 'nozzle_flange',
                'nozzle_seal', 'nozzle_bolts']
    };

    // Yanıttaki sonlu ve pozitif sayı (yol dizisiyle); yoksa null.
    function _publishedMm(md, yol) {
        var v = md;
        for (var i = 0; i < yol.length; i++) {
            if (!v || typeof v !== 'object') return null;
            v = v[yol[i]];
        }
        return (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;
    }

    /** Montaj parçalarının YAYIMLANAN ölçülerden kurulum planı (saf).
     *  geo: { motorType, rc, rGrainOut } (mm). Dönen ölçüler mm'dir ve
     *  yanıt alanına BİT-AYNIDIR; kesir, kırpma, taban YOKTUR. */
    function publishedPartPlan(md, geo) {
        md = md || {};
        geo = geo || {};
        var tip = ASSEMBLY_PARTS[geo.motorType] ? geo.motorType : 'hybrid';
        var alan = function (ad) {
            return _publishedMm(md, PART_SOURCE_FIELDS[ad]);
        };
        var kaynak = function (ad) {
            return 'solver: ' + PART_SOURCE_FIELDS[ad].join('.');
        };
        var plan = { capT: null, plateT: null, liner: null, bolts: null,
                     sources: {}, drawn: [], undrawn: [] };

        plan.capT = alan('closure_cap');
        if (plan.capT !== null) plan.sources.closure_cap = kaynak('closure_cap');

        if (tip !== 'solid') {
            plan.plateT = alan('injector_plate');
            if (plan.plateT !== null) {
                plan.sources.injector_plate = kaynak('injector_plate');
            }
        }

        if (tip !== 'liquid') {
            var tLiner = alan('chamber_liner');
            var gap = geo.rc - geo.rGrainOut;
            if (tLiner !== null) {
                // Çözücünün astarı tanenin ÖRTMEDİĞİ kamara kesimlerini
                // korur (hybrid_rocket_engine chamber_liner.function: ön ve
                // arka yanma odası) — kalınlık alanın kendisi.
                plan.liner = { tMm: tLiner, rIn: geo.rc - tLiner,
                               span: 'unshielded', basis: kaynak('chamber_liner') };
            } else if (isFinite(gap) && gap > 0) {
                // Tane ile kasa deliği arasındaki yalıtım: iki yayımlanan
                // çapın farkı (katıda kullanıcının yalıtımını birebir verir).
                plan.liner = { tMm: gap, rIn: geo.rGrainOut, span: 'full',
                               basis: 'solver: chamber bore - grain outer '
                                      + 'diameter (grain_design)' };
            }
            if (plan.liner) plan.sources.chamber_liner = plan.liner.basis;
        }

        var nBolt = alan('bolt_count');
        var delik = null;
        for (var k = 0; k < BOLT_HOLE_FIELD_PATHS.length && delik === null; k++) {
            delik = _publishedMm(md, BOLT_HOLE_FIELD_PATHS[k]);
        }
        var cember = alan('bolt_circle');
        if (tip !== 'solid' && nBolt !== null && delik !== null
                && cember !== null && plan.capT !== null) {
            // Cıvata gövdesi: delik çapında, kapak kalınlığı boyunca (sıkma
            // boyu = yayımlanan kapak). Çember künyesiz ÇİZİLMEZ.
            plan.bolts = { count: Math.round(nBolt), holeMm: delik,
                           circleMm: cember, basis: BOLT_CIRCLE_BASIS };
            plan.sources.closure_bolts = kaynak('bolt_count')
                + ' + bolted_joint.clearance_hole_diameter_mm';
        }

        var cizilen = {
            closure_cap: plan.capT !== null,
            injector_plate: plan.plateT !== null,
            chamber_liner: plan.liner !== null,
            closure_bolts: plan.bolts !== null
        };
        ASSEMBLY_PARTS[tip].forEach(function (p) {
            (cizilen[p] ? plan.drawn : plan.undrawn).push(p);
        });
        return plan;
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

        // ------------------------------------------------------------------
        // ÖH D26 / P11B1-09 — ÖLÇÜ KAYNAĞI DEFTERİ
        // ------------------------------------------------------------------
        // ÖLÇÜLDÜ (a1/once.json): sahnedeki "veri yok / varsayım" beyan
        // mekanizması YALNIZ 3 kaleme (soğutma kanalı, kontur kaynağı, port
        // gerilemesi) uygulanmıştı. Birincil ölçülerin DÖRDÜ de sessiz bir
        // uydurma yedekle çözülüyordu — num(md.chamber_diameter, 0.1),
        // num(md.chamber_length, 0.3), num(md.throat_diameter, 0.02),
        // num(md.exit_diameter, 0.08) — cidar 0,045·D geometrik yedeğine,
        // tane dış çapı da clamp(0.02·D) liner uydurmasına düşüyordu.
        // Bu hâlde ekranda ÖLÇEKLİ, ölçülü, gerçekmiş gibi duran bir motor
        // çiziliyor ve hiçbir çip çıkmıyordu: kullanıcı 100 mm'lik kamarayı
        // çözücünün ürettiği sanıyordu.
        //
        // Defter her birincil ölçü için hükmü kaydeder ('computed' = çözücü
        // yayımladı, 'assumed' = yerel uydurma yedek). Panodaki (analysis_dock)
        // sınıflandırıcıyla AYNI sözlüğü (SOURCE_COLORS / SOURCE_SYMBOLS)
        // kullanır — P11B2-10 ile tek görsel dil.
        var srcDecl = {};

        // Çözücü bu alanı gerçekten yayımladı mı? (sonlu ve pozitif)
        function mdVar(alan) {
            var v = num(md[alan], NaN);
            return isFinite(v) && v > 0;
        }
        function decl(ad, kaynakli, beyan) {
            srcDecl[ad] = _kunyeKapisi(ad,
                { kind: kaynakli ? 'computed' : 'assumed', basis: beyan });
            return kaynakli;
        }

        // FAIL-CLOSED (ÖH D27 / OH-D26-02): birincil ölçü yoksa UYDURULMAZ.
        // Kapı ürün yolunda (MotorViz3D.mount / .update) zaten sınanır;
        // buradaki sınama ikinci savunmadır — extractDims'i doğrudan
        // çağıran yeni bir yol açılırsa sessizce uydurma geometri
        // üretmesin, hükmü ALAN ADIYLA fırlatsın.
        var eksikOlcu = missingPrimaryDims(md);
        if (eksikOlcu.length) throw new MotorDimsError(eksikOlcu);

        var Dch = num(md.chamber_diameter, NaN) * 1000;
        var Lch = num(md.chamber_length, NaN) * 1000;
        // P11B1-05 → ÖH D27: oda boyu artık HER ZAMAN çözücünündür
        // (yoksa sahne yukarıdaki kapıda reddedilir), ama etiketin kaynak
        // bayrağı SABİTE bağlanmaz: yüklem burada ÖLÇÜLMEYE devam eder ki
        // kapı bir gün gevşetilirse ölçü etiketi kendiliğinden yalan
        // söylemeye başlamasın (P11B1-05 bekçisi bu ölçümü şart koşar).
        var LchKaynakli = isFinite(num(md.chamber_length, NaN))
            && num(md.chamber_length, 0) > 0;
        var dt = num(md.throat_diameter, NaN) * 1000;
        var de = num(md.exit_diameter, NaN) * 1000;
        var rt = dt / 2, re = de / 2, rc = Dch / 2;

        // Beyan metni ÇIPLAK bir nokta-ayrık dize OLAMAZ: i18n tarayıcısı
        // (tests/test_i18n_common.py FIELD_RE) tırnakla başlayan
        // `motor.<alan>` biçimini çeviri anahtarı sanar ve sözlükte
        // bulamayınca kırmızı verir — ölçüldü. Adres 'solver:' önekiyle
        // yazılır: hem tarayıcı yanılmaz hem de beyan KİMİN yayımladığını
        // söyler.
        decl('chamber_diameter', mdVar('chamber_diameter'),
             'solver: motor.chamber_diameter');
        decl('chamber_length', LchKaynakli, 'solver: motor.chamber_length');
        decl('throat_diameter', mdVar('throat_diameter'),
             'solver: motor.throat_diameter');
        decl('exit_diameter', mdVar('exit_diameter'),
             'solver: motor.exit_diameter');

        // Kullanıcının tasarladığı cidar çizilir; 0.12·D üst kırpması
        // kaldırıldı (kullanıcının kalınlığını sessizce değiştiriyordu).
        var wallSrc = {};
        var casingWall = Math.max(0.2, resolveCasingWall(md, Dch, wallSrc));
        // ÖH D31 · OH-D27-13 — KÜNYESİZ YEDEK FAIL-CLOSED. `basis` null
        // kalırsa kapı fırlatır (aşağıdaki `_srcDeclYaz`); sahne künyesiz
        // bir varsayımı sessizce çizmez.
        srcDecl['casing_wall'] = _kunyeKapisi('casing_wall',
            { kind: wallSrc.kind || 'assumed',
              basis: wallSrc.basis || null });
        // --- ÖH D29 · P11B1-10 — LÜLE CİDARI BEYAN EDİLİR ------------------
        // ÖLÇÜLDÜ (a2/once.json P11B1-10, `uydurma_oran: true`,
        // `srcDecl_nozzle_wall: false`): cidar, çözücü değer yayımlamadığında
        // `max(3 mm; 0,10·d_t)` yedeğinden çiziliyordu ve bunu HİÇBİR beyan
        // söylemiyordu. O oran ürünün KENDİ SÖKTÜĞÜ kuraldır: nozzle_design.py
        // `_calculate_nozzle_geometry` yorumu birebir "ESKİ DAVRANIŞ:
        // wall_thickness = max(0.003, dt·0.1) … Bu kuralın hiçbir kaynağı
        // yoktu ve ölçekle patlıyordu" diyor; ürün onu ince cidarlı basınç
        // kabı (hoop) bağıntısıyla değiştirdi (Huzel & Huang, NASA SP-125
        // Böl. 4) ve sonucu `nozzle_geometry.wall_thickness` [mm] adıyla
        // yayımlıyor. Hibrit bu bloğu gönderiyor (ölçüldü: 3,453 mm);
        // katı ve sıvı GÖNDERMİYOR (`_design_nozzle_geometry` çıktısında
        // wall_thickness alanı yok) — orada ekrandaki cidar bir tasarım
        // değil, sökülmüş oranın kalıntısıdır.
        // Sayı GİZLENMEZ (boş lüle kullanıcıya bir şey söylemez) ama artık
        // uydurma olduğunu SÖYLER: hüküm ölçü kaynağı defterine girer ve
        // amber çipte adıyla görünür. Ürün ayağı (katı/sıvıda cidarın
        // yayımlanması) fea-cfd/termo sahasıdır.
        var nozzleWallSrc = num(md.nozzle_geometry
            && md.nozzle_geometry.wall_thickness, NaN);
        var nozzleWallKaynakli = isFinite(nozzleWallSrc) && nozzleWallSrc > 0;
        var nozzleWall = clamp(
            nozzleWallKaynakli ? nozzleWallSrc : Math.max(3, 0.1 * dt),
            2.5, 0.25 * dt + 6);
        decl('nozzle_wall', nozzleWallKaynakli,
             nozzleWallKaynakli
                 ? 'solver: motor.nozzle_geometry.wall_thickness'
                 : 'geometric fallback max(3 mm, 0.10*d_t) - the source-less '
                   + 'rule nozzle_design.py replaced with the hoop relation');
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
            // ÖH D26 / P11B1-09: tane dış çapı çözücünün beyanından.
            decl('grain_outer_diameter', true, 'grain_design.outer_diameter_mm');
        } else {
            liner = clamp(0.02 * Dch, 1.5, 5);
            rGrainOut = rc - liner;
            // Tane dış çapı YOK: yalıtım clamp(0.02·D, 1,5, 5) ile
            // UYDURULUYOR ve tane dışı ondan çıkarılıyor — varsayım.
            decl('grain_outer_diameter', false, 'liner clamp(0.02·D, 1.5, 5)');
        }

        // T10: grain boyu ARTIK KIRPILMIYOR. Ölçüldü (hibrit varsayılan
        // koşu): çözücü 1511,6 mm derken güverte künyesi 'GRAIN 1451 mm'
        // yazıyordu (0,92 x 1575,5 mm oda boyu) — 2B kesitle aynı %4,1'lik
        // sessiz kısaltma. Yakıt kütlesiyle çapraz doğrulandı: raporun
        // yazdığı 1,54 kg ancak 1512,8 mm ile çıkıyor.
        var Lg = num(gd.grain_length_mm, num(md.grain_length, 0.8 * Lch / 1000) * 1000);
        // ÖH D26 / P11B1-09: tane boyu ya çözücünün beyanıdır ya da
        // 0,8·Lch oranından UYDURULUR — ikincisi sahnede beyan edilir.
        //
        // OH-GT-08 (ÖH D34, 21 Eylül) — KÜNYE ARTIK KAYNAĞA BAKIYOR.
        // ÖLÇÜLDÜ (a1/once.json K2, node altında GERÇEK extractDims):
        // çözücü 511,533 mm yayımladığı hâlde (`Lg_mm: 511.533`) künye
        // `{kind: 'computed', basis: 'fallback 0.8·Lch'}` diyordu — yani
        // güverte çipi "hesaplandı" der, dayanak olarak da HİÇ
        // kullanılmamış bir uydurma oranı gösterirdi. İki yükte birden
        // yalan ölçüldü (`yalan_sayisi: 2`). Kardeş `chamber_diameter`
        // doğruydu, çünkü onun dayanağı tek dallıdır.
        //
        // Dayanak artık DEĞERİN GELDİĞİ DALDAN türer; dalların ayrımı
        // `num()`un kendi yüklemidir (sonlu SAYI), yoksa künye ile değer
        // yine ayrışırdı (ör. çözücü 0 yayımlarsa değer 0'dır ama eski
        // yüklem bunu 'fallback' sayardı).
        var _gdLgSayi = typeof gd.grain_length_mm === 'number'
            && isFinite(gd.grain_length_mm);
        var _mdLgSayi = typeof md.grain_length === 'number'
            && isFinite(md.grain_length);
        var LgKunye = _gdLgSayi
            ? 'solver: grain_design.grain_length_mm'
            : (_mdLgSayi ? 'solver: motor.grain_length' : 'fallback 0.8·Lch');
        var LgKaynakli = Lg > 0 && (_gdLgSayi || _mdLgSayi);
        // FAIL-CLOSED: çözücü yayımladı ama değer kullanılabilir değil
        // (pozitif olmayan). Sessizce 'fallback' demek KAYNAĞI gizlerdi.
        if (!LgKaynakli && (_gdLgSayi || _mdLgSayi)) {
            LgKunye += ' (non-positive - not usable)';
        }
        decl('grain_length', LgKaynakli, LgKunye);
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

        // A1a sahne-sahte-veri · CM-S1: kapak kalınlığı artık kesir değil,
        // yapısal analizin düz kapak kalınlığıdır; yayımlanmadıysa null ve
        // kapak ÇİZİLMEZ. Ondan türeyen lüle flanşı kalınlığı ve giriş
        // borusu boyu onunla birlikte düştü (ölçüleri hiçbir alanda yok).
        var partPlan = publishedPartPlan(md, {
            motorType: md.viz_motor_type || 'hybrid',
            rc: rc, rGrainOut: rGrainOut });
        var capT = partPlan.capT;
        // Kadraj payı (kamera, zemin, çip ölçeği). Artık hiçbir parça
        // çizmez (lüle flanşı düştü); kesir kaldı → DEVİR A6a cm-3-sahne.
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
            // ÖH D24 · P11B1-02: efsanenin uçları rampanın KENDİ alanıdır.
            // `qChamber` bandın dibinde değil, log ölçeğinde t = 0,205'te
            // durur; etikete o sayıyı yazmak bandın tamamını kaydırırdı.
            var _hd = heatRampDomain(heat);
            heat.qRampMin = _hd.qMin;
            heat.qRampMax = _hd.qMax;
        }

        // P11B1-13 — cıvata sayısının hükmü ölçülür ve defterde durur.
        var boltSrc = num(fasteners.num_bolts, NaN);
        var boltKaynakli = isFinite(boltSrc) && boltSrc > 0;
        srcDecl['bolt_count'] = _kunyeKapisi('bolt_count', boltKaynakli
            ? { kind: 'computed',
                basis: 'solver: structural_analysis.fastener_analysis.num_bolts' }
            : { kind: 'missing',
                basis: 'structural_analysis.fastener_analysis.num_bolts '
                     + 'not published - no bolts drawn' });

        return {
            // 'hybrid' | 'solid' | 'liquid' — sayfa adaptörü belirler
            motorType: md.viz_motor_type || 'hybrid',
            // ÖH D26 / P11B1-09 — ölçü kaynağı defteri (sahne çipi buradan)
            srcDecl: srcDecl,
            Dch: Dch, Lch: Lch, LchKaynakli: LchKaynakli,
            rc: rc, rt: rt, re: re, dt: dt, de: de,
            casingWall: casingWall, nozzleWall: nozzleWall, liner: liner,
            rcOut: rc + casingWall,
            Lg: Lg, zg0: zg0, zg1: zg1,
            rPort0: rPort0, rGrainOut: rGrainOut,
            nozType: nozType, Lc: Lc, Ld: Ld,
            thetaN: thetaN, thetaE: thetaE, halfAngle: halfAngle,
            Rn: Rn, Rconv: Rconv,
            capT: capT, flangeLip: flangeLip,
            // A1a sahne-sahte-veri · CM-S1 — yayımlanan ölçülerden montaj
            // planı (çizilen / çizilmeyen parçalar + alan künyeleri).
            partPlan: partPlan,
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
            // ÖH D29 · P11B1-13 — CIVATA SAYISI DA UYDURULMAZ.
            // ÖLÇÜLDÜ (a3/once.json): taban
            // `Math.max(6, Math.round(num(fasteners.num_bolts, 8)))` idi ve
            // İKİ ayrı uydurma taşıyordu: (a) alan hiç yayımlanmazsa 8
            // cıvata — katı ve sıvı /calculate yanıtlarında
            // `structural_analysis.fastener_analysis.num_bolts` YOKTUR
            // (çapa yükünden ölçüldü: hibrit 6, katı null, sıvı null),
            // yani o iki sayfada ekrandaki 8 cıvatanın kaynağı BU SATIRDI;
            // (b) çözücü 6'dan az bildirirse sessiz yukarı yuvarlama.
            // Aynı dosya bu deseni orifis için ZATEN söktü (yukarıdaki
            // nOrifices yorumu: "Math.max(4, ...) yüzünden çözücünün 3
            // deliğini 4 gösteriyordu"); kural burada da uygulanır —
            // sayı yoksa cıvata ÇİZİLMEZ, hüküm çipe yazılır.
            nBolts: boltKaynakli ? Math.round(boltSrc) : 0,
            // ÖH D36 / onemli2-sivi a2 — ZAMAN EKSENİ UYDURULMAZ. Eski
            // satır ``Math.max(0.1, num(md.burn_time, 10))`` idi: süre
            // taşımayan sözlükte (süresiz sıvı; sayfa adaptörü de sabit 10
            // basıyordu) güverte saati "t = 0,00 s / 10,00 s" ve kaydırıcı
            // UYDURMA bir yanma süresi gösteriyordu (ölçüldü,
            // a2/once.json K7: sıvı süre boş ve 400 s İKİSİ de 10). Süre
            // yoksa ``null``: sahne oynatmaz, güverte zaman eksenini
            // çizmez (motor_viz_deck.js). Süre verildiğinde değer eskisiyle
            // bit-aynıdır (hibrit ve katı daima süre taşır).
            burnTime: (num(md.burn_time, NaN) > 0)
                ? Math.max(0.1, md.burn_time) : null,
            thrust: num(md.thrust, null),
            isp: num(md.isp, null),
            pc: num(md.chamber_pressure, null),
            // A1b faz-c-0 · OH-D37-S7 (SAHTE VERİ) — PERFORMANS DA
            // UYDURULMAZ (yukarıdaki üç satır). Eskiden itki / Isp / oda
            // basıncı yayımlanmadığında 1000 N / 200 s / 20 bar yazılıyordu
            // ve sahnenin HUD yayını (onTick → güverte çipleri) o sayıları
            // çözücününmüş gibi basıyordu (ölçüldü: A1b faz-c-0 a1
            // once/node_olcum.json M3_s7.yayimsiz — thrust 1000, isp 200).
            // Yayımlanmadıysa null; sahne `perfNotPublished` çipiyle adıyla
            // beyan eder. Alan varken değer bit-aynıdır (num aynı yüklem).
            // Not: bu yorum burnTime ile thrust ARASINA yazılmaz — D36
            // sıvı a2 bekçisi burnTime ifadesini ',\n thrust:'a kadar okur.
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
            // Katı yolu, ASIL kaynak: çözücünün yayımladığı port akış kesiti
            // (thrust_curve.port_area). Yoksa null → aşağıdaki yedek geçerli.
            portAreaHist: solidPortRadiusHistory(md),
            // Katı yolu, YEDEK: web geçmişi çözücünün itki eğrisinden
            // türetilir (solidWebHistory; veri yoksa null → port donuk kalır).
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
    // Tane yanma animasyonu — port gerilemesi (v2.6.27, B5 · parti 26)
    //
    // SAHTE ANİMASYON YASAĞI: iç yüzey YALNIZ gerçek çözücü serisiyle
    // gerilir. ÜÇ gerçek kaynak vardır, dördüncüsü YOKTUR:
    //
    //  1) hibrit — motor sözlüğü ``port_history`` yayımlar
    //     ({time[s], port_diameter[m]}); doğrudan örneklenir.
    //
    //  2) katı, ASIL — çözücü ``thrust_curve.port_area`` (m²) yayımlar
    //     (parti 26; solid_rocket_engine.py::_published_thrust_curve).
    //     Bu dizi çözücünün KENDİ zaman marşından gelir (erozif akı
    //     G = mdot/A_port ile tek ve aynı seri), dolayısıyla dairesel
    //     portta eşdeğer yarıçap TÜRETMESİZ okunur: r(t) =
    //     sqrt(A_port(t)/π). Yayımlanan seri varsa animasyon BUNU
    //     kullanır (kip 'solid_port_area'); yoksa aşağıdaki (3) yolu
    //     yedek kalır — eski/bayat yanıtlar kırılmaz.
    //
    //  3) katı, YEDEK — port_area taşımayan yanıtlarda (v2.6.27 parti 26
    //     öncesi kaydedilmiş sonuç dosyaları) web geçmişi çözücünün KENDİ
    //     kütle üretim özdeşliğinden geri alınır:
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

    // Katı çözücünün YAYIMLADIĞI port akış kesitinden (m²) eşdeğer port
    // yarıçapı geçmişi (m). Tek işlem sqrt(A/π)'dir: ara değerleme, bitiş
    // noktası varsayımı ve zaman yasası YOKTUR.
    //
    // null döner (ve çağıran yedek yola düşer) şu hâllerde:
    //   * alan yayımlanmamış (parti 26 öncesi kaydedilmiş sonuç dosyaları),
    //   * dizi kısa / hizasız / sayısal değil / alan sıfır ya da negatif,
    //   * zaman sırası bozuk,
    //   * seri BÜYÜMÜYOR — uç yanmalı tanede A_port sabittir (port yok, tüm
    //     kasa kesiti akar; ölçüldü: end_burner'da 6157 örneğin tamamı
    //     7,853982e-3 m²). Sabit seriden animasyon çıkarmak, olmayan bir
    //     gerilemeyi göstermek olurdu.
    function solidPortRadiusHistory(md) {
        var tc = (md && md.thrust_curve) || null;
        if (!tc) return null;
        var t = tc.time, ap = tc.port_area;
        if (!t || !ap) return null;
        var n = t.length;
        if (n < 3 || ap.length !== n) return null;
        var radius = new Array(n);
        var tPrev = 0, buyudu = false;
        for (var i = 0; i < n; i++) {
            var ti = num(t[i], NaN), A = num(ap[i], NaN);
            if (!isFinite(ti) || !isFinite(A) || A <= 0) return null;
            if (i > 0 && ti < tPrev) return null;      // sıralı olmayan seri
            radius[i] = Math.sqrt(A / Math.PI);
            if (radius[i] > radius[0]) buyudu = true;
            tPrev = ti;
        }
        if (!buyudu) return null;
        return {
            time: t, radius: radius, r0: radius[0], rEnd: radius[n - 1],
            source: 'solid_port_area'
        };
    }

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
    //   'solid_port_area'     katı çözücü port AKIŞ KESİTİNİ yayımladı
    //   'solid_mass_balance'  katı çözücünün kütle dengesinden türetildi
    //   'not_modelled'        kesit/tane tipi için radyal gerileme geçersiz
    //   'no_data'             gerçek zaman serisi yok → port donuk
    //
    // TANE TİPİ KAPISI port_area yayımlansa da AÇILMAZ. Gerekçe ölçüldü
    // (2026-08-16, solid_rocket_engine.py::_port_flow_area ile çapraz):
    // yıldız/finocyl/çok portlu tanede yayımlanan A_port, akı bölmesi için
    // kullanılan EŞDEĞER DAİRESEL porttur — π(r_çekirdek+w)², yani tam
    // olarak web geçmişinin taşıdığı bilgi (fark ≤ 0,031 mm). Gerçek kesit
    // ise yüzey normali boyunca ofsetlenmiş bir poligondur; onu tek yarıçap
    // büyüterek göstermek, yeni alan yayımlandı diye doğru olmaz. 'slotted'
    // tanede alan GERÇEK poligon alanıdır ama kesit yine dairesel değildir
    // (eşdeğer yarıçap r0+w'den 17,3 mm sapıyor). Uç yanmalıda dizi sabittir
    // ve zaten solidPortRadiusHistory tarafından reddedilir.
    function portRegressionMode(spec) {
        spec = spec || {};
        if ((spec.portShape || 'circular') !== 'circular') return 'not_modelled';
        // Çözücü yarıçapı KENDİSİ verdiyse tane tipi tartışması yoktur.
        if (spec.hasPortHistory) return 'port_history';
        var gt = String(spec.grainType || '').toLowerCase();
        if (gt && !RADIAL_REGRESSION_GRAINS[gt]) return 'not_modelled';
        // Yayımlanan port kesiti VARSA türetme yapılmaz; yoksa yedek yol.
        if (spec.hasPortArea) return 'solid_port_area';
        if (spec.hasWebHistory) return 'solid_mass_balance';
        return 'no_data';
    }

    // ------------------------------------------------------------------
    // ÖH D26 / P11B1-09 — ÖLÇÜ KAYNAĞI ÇİPİ
    // ------------------------------------------------------------------
    // Defterdeki (extractDims → dims.srcDecl) hükümleri sahne çipine
    // çevirir. Kural FAIL-CLOSED değil, BEYAN-ZORUNLU: sahne bir motoru
    // çizmek zorundadır (boş tuval kullanıcıya bir şey söylemez), ama
    // ölçüsü uydurma yedekten geliyorsa bunu SÖYLEMEK zorundadır.
    //
    // 'computed' ölçüler için çip BASILMAZ — her ölçüye çip basmak sahneyi
    // okunmaz eder ve gerçek uyarıyı gürültüye gömer. Yalnız uydurma
    // yedeğe düşen ölçüler tek bir amber çipte toplanır.
    // ÖH D29 · P11B1-10 — lüle cidarı da beyan edilen bir ölçüdür.
    // i18n devri (arayuz-i18n): bu dalgada i18n_common.js kardeş kulvarın
    // elinde (ölçüldü: dalga29/arayuz-i18n o dosyaya dokundu), bu yüzden
    // YENİ anahtar açılmaz. `nozzle_wall` girdisinin anahtar alanı null
    // bırakılır ve etiket makine dizesi olarak basılır; anahtar sonraki
    // aşamada 'viz3d.dim.nozzleWall' adıyla bağlanacak.
    // NOT: bu blok sabitin İÇİNE yazılmaz. Mevcut bekçiler (D26 a1
    // ``_sabit``) sabiti "atamadan ilk noktalı virgüle kadar" deseniyle
    // çıkarıyor; gövdedeki bir noktalı virgül çıkarımı ortadan keser ve
    // node koşumu SyntaxError verir (ölçüldü). Aynı sebeple o desenin
    // KENDİSİ de buraya yazılmaz — arama sabitten önce buraya düşerdi.
    var DIM_SRC_LABEL_KEYS = {
        chamber_diameter: ['viz3d.dim.chamberDia', 'Ø chamber'],
        chamber_length: ['viz3d.dim.chamberLen', 'L chamber'],
        throat_diameter: ['viz3d.dim.throatDia', 'Ø throat'],
        exit_diameter: ['viz3d.dim.exitDia', 'Ø exit'],
        casing_wall: ['viz3d.dim.casingWall', 'casing wall'],
        nozzle_wall: [null, 'nozzle wall'],
        bolt_count: [null, 'bolt count'],
        grain_outer_diameter: ['viz3d.dim.grainOuter', 'Ø grain'],
        grain_length: ['viz3d.dim.grainLen', 'L grain']
    };

    // Tek ölçünün beyanı. Hüküm 'computed' ise null döner (çip yok).
    function srcNote(alan, decl) {
        if (!decl || decl.kind === 'computed') return null;
        var lbl = DIM_SRC_LABEL_KEYS[alan];
        // Anahtarı olmayan etiket (i18n devri) ham dizeyle basılır —
        // T(null, …) çağrısı yapılmaz, sözlük bekçisi yanlış alarm vermez.
        return { field: alan, kind: decl.kind,
                 text: lbl ? (lbl[0] ? T(lbl[0], lbl[1]) : lbl[1]) : alan,
                 basis: decl.basis || null };
    }

    // Sahnedeki ölçü-kaynağı çip tanımları. Bütün ölçüler çözücüden
    // geliyorsa boş dizi döner (temiz sahne = gerçekten temiz veri).
    // --- ÖH D31 · OH-D27-13 (ayak ii) — ROZET PANELDE DE GÖRÜNÜR --------
    // 9 Eyl kararının lafzı "panelde 'varsayılan' rozeti" idi; D27'de
    // rozet YALNIZ 3B sahne çipi olarak indi (ölçüldü a1/once.json · M3:
    // `panel_rozet_solid = 0`, `panel_rozet_advanced = 0`). Sahne çipi
    // kullanıcı 3B görünümü açmadığında hiç görünmez; ölçü tablosuna
    // bakan kullanıcı cidarın uydurma olduğunu öğrenemez.
    //
    // Metin UYDURULMAZ: rozet, sahne çipiyle AYNI defterden (srcDecl)
    // aynı `srcNote` süzgeciyle üretilir — iki yüzey ayrışamaz.
    var _sonVarsayilanOlculer = [];

    /** Çip listesinden panel rozetini tazeler. Tek kaynak: çipin kendi
     *  `fields` dizisi; künye metni defterin (`dims.srcDecl`) kendisi. */
    function _varsayimRozetiniTazele(cipler, dims) {
        var cip = null;
        (cipler || []).forEach(function (c) {
            if (!cip && c && c.kind === 'assumed' && Array.isArray(c.fields)) {
                cip = c;
            }
        });
        var decls = (dims && dims.srcDecl) || {};
        _sonVarsayilanOlculer = (cip && Array.isArray(cip.fields))
            ? cip.fields.map(function (alan) {
                return srcNote(alan, decls[alan])
                    || { field: alan, kind: 'assumed', text: alan,
                         basis: null };
            })
            : [];
        renderAssumedDimBadge();
        return _sonVarsayilanOlculer.length;
    }

    /** Son çizilen sahnenin künyeli varsayım ölçüleri (boş = temiz veri). */
    function assumedDimensionList() {
        return _sonVarsayilanOlculer.map(function (n) {
            return { field: n.field, kind: n.kind, text: n.text,
                     basis: n.basis };
        });
    }

    /** Rozeti sayfa DOM'una yazar. Kapsayıcı yoksa sessizce geçer
     *  (sayfa rozeti istemiyorsa zorlanmaz); varsa ve varsayım yoksa
     *  KAPATILIR — bayat rozet asılı kalmaz. */
    function renderAssumedDimBadge(kapsayiciId) {
        var el = document.getElementById(kapsayiciId || 'hrma-dims-assumed');
        if (!el) return false;
        var liste = assumedDimensionList();
        if (!liste.length) {
            el.innerHTML = '';
            el.style.display = 'none';
            return false;
        }
        var kacir = function (t) {
            return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        };
        var satirlar = liste.map(function (n) {
            // Künye (basis) kullanıcıya AYNEN gösterilir: hangi kural
            // uygulandığı sayının yanında durur, yorumlanmaz.
            return '<li><strong>' + kacir(n.text) + '</strong>'
                + (n.basis ? ' — <code>' + kacir(n.basis) + '</code>' : '')
                + '</li>';
        }).join('');
        el.style.display = '';
        el.innerHTML =
            '<div class="dims-assumed-badge" style="border-left:3px solid '
            + 'var(--hd-amber, #ffbe46); padding:6px 10px; margin:8px 0; '
            + 'font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">'
            + '<span style="color:var(--hd-amber, #ffbe46); '
            + 'font-weight:600;">\u25C6 '
            + kacir(T('viz3d.chip.dimsAssumed', 'assumed dimensions'))
            + '</span><ul style="margin:4px 0 0 16px; padding:0;">'
            + satirlar + '</ul></div>';
        return true;
    }

    function dimensionSourceChipDefs(dims) {
        var decls = (dims && dims.srcDecl) || {};
        var solid = dims && dims.motorType === 'solid';
        var hybrid = dims && dims.motorType === 'hybrid';
        var notlar = [];
        Object.keys(DIM_SRC_LABEL_KEYS).forEach(function (alan) {
            // Tane ölçüleri yalnız tanesi olan motorlarda anlamlıdır.
            if ((alan === 'grain_outer_diameter' || alan === 'grain_length')
                && !(solid || hybrid)) return;
            var n = srcNote(alan, decls[alan]);
            if (n) notlar.push(n);
        });
        if (!notlar.length) return [];
        var adlar = notlar.map(function (n) { return n.text; }).join(', ');
        return [{
            text: T('viz3d.chip.dimsAssumed', 'assumed dimensions') + ': ' + adlar,
            kind: 'assumed',
            // Ölçüm/test için: hangi alanlar beyan edildi.
            fields: notlar.map(function (n) { return n.field; })
        }];
    }

    // A1b faz-c-0 · OH-D37-S7 — YAYIMLANMAYAN PERFORMANS BÜYÜKLÜKLERİ.
    // extractDims itki / Isp / oda basıncını artık uydurmuyor (null);
    // sahne hangisinin gelmediğini ADIYLA söyler. Sıra sabittir (itki,
    // Isp, Pc); dönen dizi boşsa çip basılmaz (temiz veri = temiz sahne).
    // Alan adı `dims`teki adıdır, etiket oturum dilinde.
    // ÖH V3 taban-v (14 Eki 2026) — Isp ADI NİTELİKLİ. Çıplak 'Isp' aynı
    // yanıttaki dört Isp'yi (tasarım/vakum/deniz seviyesi/azami) ayırt
    // etmiyordu (tests/test_ciplak_etiket_common.py). Sahne `md.isp`in hangi
    // ortamda hesaplandığını bilmez: sayfalar bunu `isp_reference` ile
    // YALNIZ değer varken beyan eder (liquid.html, solid.html), yani değer
    // yayımlanmadığında referans da beyan edilmemiştir. Etiket güvertenin
    // aynı durum için kullandığı metindir (motor_viz_deck.js
    // ISP_REFERANSSIZ_ETIKET; TR karşılığı i18n_charts.js'teki kayıt).
    var PERF_FIELD_LABEL_KEYS = [
        ['thrust', 'viz3d.perf.thrust', 'thrust'],
        ['isp', 'viz3d.perf.isp', 'Isp (reference not declared)'],
        ['pc', 'viz3d.perf.pc', 'chamber pressure']
    ];
    function perfNotPublished(dims) {
        var eksik = [];
        PERF_FIELD_LABEL_KEYS.forEach(function (p) {
            var v = dims ? dims[p[0]] : null;
            if (!(typeof v === 'number' && isFinite(v))) eksik.push(p[0]);
        });
        return eksik;
    }
    function perfNotPublishedChipDef(dims) {
        var eksik = perfNotPublished(dims);
        if (!eksik.length) return null;
        var adlar = PERF_FIELD_LABEL_KEYS.filter(function (p) {
            return eksik.indexOf(p[0]) !== -1;
        }).map(function (p) { return T(p[1], p[2]); }).join(', ');
        return {
            text: cfdFormatTemplate(T('viz3d.chip.perfNotPublished',
                'not published by the solver: {fields}'), { fields: adlar }),
            kind: 'missing', field: 'performance', fields: eksik
        };
    }

    // Kipin durum çipleri. Çip BEYANDIR: animasyonun neyden sürüldüğünü
    // (ya da sürülmediğini) kullanıcıya söyler.
    function portRegressionChipDefs(mode, opts) {
        opts = opts || {};
        var defs = [];
        if (mode === 'port_history') {
            defs.push({ text: T('viz.chip.portRegHistory',
                'port regression: solver port history'), kind: 'computed' });
        } else if (mode === 'solid_port_area') {
            defs.push({ text: T('viz.chip.portRegPortArea',
                'port regression: solver port area'), kind: 'computed' });
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
        if (opts.endsBurn && (mode === 'port_history' || mode === 'solid_port_area'
            || mode === 'solid_mass_balance')) {
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
        if (mode === 'solid_port_area') {
            var pah = dims.portAreaHist;
            var rp = (pah && pah.time && pah.radius)
                ? sampleSeries(pah.time, pah.radius, t) : null;
            if (rp !== null) {
                return clamp(rp * 1000, dims.rPort0, dims.rGrainOut - 0.5);
            }
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
        if (mode === 'solid_port_area' && dims.portAreaHist) {
            // Serinin KENDİ tabanından ölçülür (r(t) − r(0)): çizim
            // kırpması (rGrainOut − 0,5) HUD sayısını kısaltmasın.
            var pah = dims.portAreaHist;
            var rp = sampleSeries(pah.time, pah.radius, t);
            return (rp === null) ? null : (rp - pah.r0) * 1000;
        }
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

    // ÖH D24 · P11B1-02 — RAMPANIN ALANI TEK KAYNAKTAN OKUNUR.
    //
    // ÖLÇÜLDÜ (taban 88a29d3, once.json P11B1-02): efsanenin SOL etiketi
    // `fmt(info.qChamber)` = 2,60 MW/m² basıyordu; rampanın t=0 ucunun
    // temsil ettiği akı ise exp(lnMin) = qC·0,6 = 1,56 MW/m², yani etiket
    // bandın dibini 1/0,6 = 1,6667 kat YANLIŞ adlandırıyordu. Renkli bandın
    // en koyu ucundan sayı okuyan kullanıcı akıyı %67 fazla okur.
    //
    // Efsane bir RENK ⟷ DEĞER SÖZLEŞMESİDİR: uçlarına rampanın kendi alan
    // uçları yazılır, başka bir büyüklük değil. Alan bu fonksiyondan
    // okunur; hem mesh'i boyayan `_applyHeatMap` hem `getHeatInfo` üstünden
    // efsaneyi yazan güverte/şablon AYNI iki sayıyı kullanır — ikinci
    // kopya yok, dolayısıyla uç bir daha kayamaz.
    //
    // `HEAT_RAMP_FLOOR` neden 1 değil: taban tam qC'ye oturtulsaydı kamara
    // yüzeyi rampanın t=0'ında, yani skalanın en koyu renginde düz siyah
    // görünürdü. Pay bilinçli bir GÖRSEL karardır; bundan böyle etikette
    // beyan edilir (uydurulmaz).
    var HEAT_RAMP_FLOOR = 0.6;

    //: `heat` = {qThroat, qChamber} (W/m²). Döner: rampanın uç değerleri.
    //: `heat` yoksa ısı haritası kapalıdır; boyama zaten yapılmaz, yine de
    //: bölme hatası vermeyen dejenere alan döner.
    function heatRampDomain(heat) {
        var qT = (heat && isFinite(heat.qThroat)) ? heat.qThroat : 1;
        var qC = (heat && isFinite(heat.qChamber))
            ? Math.min(heat.qChamber, qT * 0.9) : 1;
        return {
            qMin: Math.max(qC * HEAT_RAMP_FLOOR, 1),
            qMax: Math.max(qT, 2)
        };
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
            // Ofset TEK kaynaktan: contourZToScene (CFD alan katmanı da
            // aynı fonksiyonla hizalanır; refaktor bit-aynılığı bekçili)
            return dims.contourPoints.map(function (cp) {
                return { z: contourZToScene(dims, cp.z), r: cp.r };
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

    // Nozul katı poligonu: iç kontur + yayımlanan cidar kadar ofsetli dış yol.
    // A1a sahne-sahte-veri · CM-S1 — montaj flanşı (kalınlığı kapak
    // kesrinin 0,8 katı, dudağı 0,10 x rc) ve grafit boğaz eki (kalınlığı
    // 0,35 x rt) SÖKÜLDÜ: üçünün de ölçüsü hiçbir yanıt alanında yok. Katı
    // artık dışa aktarımın lüle katısıyla aynı tanımdır
    // (cad_visualization._nozzle_solid: iç kontur + cidar ofseti).
    function nozzleProfile(dims) {
        var inner = nozzleInnerContour(dims);
        var zEnd = inner[inner.length - 1].z;
        var poly = [];
        inner.forEach(function (p) { poly.push({ r: p.r, z: p.z }); });
        // çıkış dudağı
        poly.push({ r: inner[inner.length - 1].r + dims.nozzleWall, z: zEnd });
        // dış yüzey (geriye doğru, cidar ofseti)
        for (var i = inner.length - 1; i >= 0; i--) {
            poly.push({ r: inner[i].r + dims.nozzleWall, z: inner[i].z });
        }
        return { poly: poly, zExit: zEnd, rExit: inner[inner.length - 1].r,
                 inner: inner };
    }

    // ------------------------------------------------------------------
    // Ana görselleştirici
    // ------------------------------------------------------------------

    var viz = null; // tek aktif örnek
    // ÖH D24 / P11B1-08 — son CFD reddinin gerekçe bloğu (ölçüm).
    var _cfdLastReject = null;
    // ÖH D27 / OH-D26-02 — son BİRİNCİL ÖLÇÜ reddi (yoksa null). Sahne
    // kurulmadıysa güverte/sayfa gerekçeyi buradan okur; red sessizce
    // kaybolmaz (D24 / P11B1-08 dersinin ölçü ayağı).
    var _dimsLastReject = null;

    // Malzemeler TABLODAN kurulur (B7): sayısal parametre burada YAZILMAZ,
    // hepsi RENDER_QUALITY.materials'tan gelir (tek kaynak bekçili).
    //   * cut       → kesit yüzü (DoubleSide)
    //   * brushed   → fırçalanmış metal bump+roughness haritası
    //   * clearcoat → dielektrik kaplama ⇒ MeshPhysicalMaterial (r128'de var,
    //                 isMeshStandardMaterial mirası korunur: scene.environment
    //                 ve CAD malzeme kısıcısı aynen çalışır)
    function createMaterials(maxAnisotropy) {
        var brushed = brushedTexture(maxAnisotropy);
        var spec = RENDER_QUALITY.materials;
        var out = {};
        Object.keys(spec).forEach(function (key) {
            var s = spec[key];
            var opts = {
                color: s.color, metalness: s.metalness, roughness: s.roughness,
                envMapIntensity: s.envMapIntensity
            };
            if (s.cut) opts.side = THREE.DoubleSide;
            if (s.brushed) {
                opts.bumpMap = brushed;
                opts.roughnessMap = brushed;
                opts.bumpScale = s.bumpScale;
            }
            if (s.clearcoat !== undefined) {
                opts.clearcoat = s.clearcoat;
                opts.clearcoatRoughness = s.clearcoatRoughness;
                out[key] = new THREE.MeshPhysicalMaterial(opts);
            } else {
                out[key] = new THREE.MeshStandardMaterial(opts);
            }
        });
        return out;
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
        // A1b faz-c-0 · K1b — fare altı probe (alan katmanı yokken sessiz)
        this._bindProbe();

        this._clock = new THREE.Clock();
        this._introT = 0;
        // V301/K-C1 (KT-24, sıvı SV-18) — İSTEK ÜZERİNE ÇİZİM.
        // ÖLÇÜLDÜ (denetim A-kati raf_olc + K-C1/raf_once.json): burada
        // koşulsuz `requestAnimationFrame` döngüsü vardı; sahne bir kez
        // açılınca hiçbir şey değişmese de, sahne ekran dışında ya da sekme
        // arka plandayken de saniyede ~60 kez `renderer.render` çağrılıyordu
        // (SwiftShader'da ~6 çekirdek). Döngü artık yalnız DURUM DEĞİŞİNCE
        // koşar: kamera/kontrol olayı, imleç, oynatma, otomatik dönüş (kullanıcı
        // açar; varsayılan kapalı), patlatma geçişi, giriş kaydırması, boyut
        // ya da dil değişimi ve sahnenin herhangi bir genel yöntem çağrısı.
        // Sahne görünmüyorsa (IntersectionObserver, `document.hidden`,
        // display:none) döngü durur; görünür olunca kaldığı yerden sürer.
        this._loopOn = false;
        this._idleFrames = 0;
        this._onScreen = true;
        this._bindVisibility();
        this._kick();
    }

    //: Hiçbir şey kıpırdamadan kaç kare daha çizilip döngünün uyuyacağı.
    //: HRMA seçimi: 2 kare — kontrol sönümünün son adımı ve kanca (HUD)
    //: tazelemesi bir kare gecikmeyle gelebildiği için tek kare yetmez.
    var RENDER_IDLE_FRAMES = 2;

    // Döngüyü uyandırır (çalışıyorsa yalnız uyku sayacını sıfırlar).
    MotorScene.prototype._kick = function () {
        // Kurucu bitmeden (saat yokken) gelen olaylar yok sayılır: kurucunun
        // son adımı döngüyü zaten başlatır.
        if (this._disposed || !this._clock) return;
        this._idleFrames = 0;
        if (this._loopOn || !this._canRun()) return;
        this._loopOn = true;
        // Uyku süresi bir kare süresi sayılmasın (giriş/oynatma dt'si).
        this._clock.getDelta();
        var self = this;
        var loop = function () {
            if (self._disposed || !self._canRun()) {
                self._loopOn = false;
                self._raf = null;
                return;
            }
            self._tick();
            if (self._shouldSleep()) {
                self._loopOn = false;
                self._raf = null;
                return;
            }
            self._raf = requestAnimationFrame(loop);
        };
        this._raf = requestAnimationFrame(loop);
    };

    MotorScene.prototype._canRun = function () {
        if (typeof document !== 'undefined' && document.hidden) return false;
        return this._onScreen !== false;
    };

    // Sürekli animasyon yoksa ve kamera bu karede kıpırdamadıysa uyku sayacı
    // ilerler; RENDER_IDLE_FRAMES kare sakin geçince döngü durur.
    MotorScene.prototype._shouldSleep = function () {
        var st = this.state;
        if (!this.container.offsetParent) return true;   // display:none ata
        var hedef = st.exploded ? 1 : 0;
        var surekli = st.playing || st.autoRotate || this._introT < 1
            || Math.abs(this._explodeF - hedef) > 0.001 || this._camMoved;
        if (surekli) { this._idleFrames = 0; return false; }
        this._idleFrames += 1;
        return this._idleFrames > RENDER_IDLE_FRAMES;
    };

    // Görünürlük bekçileri: ekran dışı / arka plan sekmesi döngüyü durdurur,
    // geri gelince uyandırır. Etkileşim olayları da uyandırır.
    MotorScene.prototype._bindVisibility = function () {
        var self = this;
        var uyandir = function () { self._kick(); };
        this._wakeHandler = uyandir;
        if (typeof IntersectionObserver === 'function') {
            this._io = new IntersectionObserver(function (girdiler) {
                var g = girdiler[girdiler.length - 1];
                self._onScreen = !!(g && g.isIntersecting);
                if (self._onScreen) self._kick();
            });
            this._io.observe(this.container);
        }
        this._visHandler = function () { if (!document.hidden) self._kick(); };
        document.addEventListener('visibilitychange', this._visHandler);
        var el = this.renderer && this.renderer.domElement;
        if (el) {
            ['pointerdown', 'pointermove', 'wheel', 'keydown', 'touchstart']
                .forEach(function (ad) {
                    el.addEventListener(ad, uyandir, { passive: true });
                });
        }
        document.addEventListener('hrma:langchange', uyandir);
    };

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
        // V301/K-C1 (KT-24): kontrol olayı (sürükleme, sönüm) döngüyü uyandırır.
        var self = this;
        this.controls.addEventListener('change', function () { self._kick(); });
        this.controls.addEventListener('start', function () { self._kick(); });
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

        // Işıklar: üç nokta düzeni (anahtar + dolgu + hemi) + cyan/turuncu
        // jant ışıkları (sci-fi ton, KİMLİK — değerleri tabloya alınmadı).
        // Yayınık bütçe korunur: hemi 0,55 → 0,25, açığa çıkan 0,30 yönlü
        // dolguya verildi (RENDER_QUALITY.lights.diffuseBudget = 1,50).
        var LI = RENDER_QUALITY.lights;
        this._hemiLight = new THREE.HemisphereLight(
            LI.hemiSky, LI.hemiGround, LI.hemiIntensity);
        this.scene.add(this._hemiLight);
        var key = new THREE.DirectionalLight(LI.keyColor, LI.keyIntensity);
        key.castShadow = true;
        this._keyLight = key;
        this.scene.add(key);
        // Dolgu ışığı: gölge ATMAZ (ikinci gölge seti sahte kontak üretir),
        // rengi gökyüzü jetonuyla AYNI — ambiyansın yönlü hâli olduğu için
        // sahnenin renk dengesi (kimlik) değişmez. Gölge kadrajı ve mapSize
        // _applyShadowFit'te uygulanır (kalite kipine bağlı).
        var fill = new THREE.DirectionalLight(LI.hemiSky, LI.fillIntensity);
        fill.castShadow = false;
        this._fillLight = fill;
        this.scene.add(fill);
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
        var mats = this.mats || (this.mats = createMaterials(this._maxAnisotropy()));
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

        // Detay segment sayısı: perf modunda düşürülür
        var segC = this._perfMode ? 24 : 48;   // torus çevre segmenti

        // A1a sahne-sahte-veri · CM-S1 — montaj parçaları YALNIZ yayımlanan
        // ölçülerden (extractDims → publishedPartPlan). Sökülen kesirler:
        // O-ring (0,16 x kapak) ve yivleri, spigot (0,55 x kapak), katı
        // kapağın tüp içi çapı (rc - 0,15) + segmanı (0,12 x kapak) + tüp
        // uzatması (kapak + 4 mm), kapak cıvatası (0,3 x cidar çap, 0,5 x
        // kapak boy, cidar ortası çember), giriş borusu + rakor (0,22 x rc,
        // 1,6 x kapak). Hiçbirinin ölçüsü bir yanıt alanında yok.
        var plan = d.partPlan || { drawn: [], undrawn: [] };
        // Parça künyesi mesh'lere yazılır: sahne ölçümü (kanıt betiği,
        // bekçi) çizilen parçanın ADINI ve ölçüsünün KAYNAĞINI okur.
        function tagPart(obj, part, sizeMm, basis) {
            obj.traverse(function (o) {
                o.userData.part = part;
                if (sizeMm !== undefined) o.userData.sizeMm = sizeMm;
                if (basis) o.userData.basis = basis;
            });
            return obj;
        }
        // Dış parting-line halkası (işlenmiş parça birleşim izi — tam çember)
        function addJointLine(parent, zPos) {
            var jr = new THREE.Mesh(
                new THREE.TorusGeometry(d.rcOut + 0.25, 0.5, 6, segC), mats.bolt);
            jr.rotation.x = Math.PI / 2;
            jr.position.y = zPos;
            parent.add(jr);
        }

        // --- Gövde tüpü (kapak AYRI parça) ---
        var casingPoly = [
            { r: d.rc, z: 0 },
            { r: d.rcOut, z: 0 },
            { r: d.rcOut, z: d.Lch },
            { r: d.rc, z: d.Lch }
        ];
        var casing = buildSolid(casingPoly, mats.casing, mats.casingCut, cut);
        this.parts.casing = casing;

        // --- Ön kapak (forward closure): yapısal analizin DÜZ KAPAK
        // kalınlığı (end_cap_analysis.flat_head_thickness). Profil dışa
        // aktarımın kapağıyla aynı tanım: tüp alnında, dış çap = kasa dış
        // çapı (cad_visualization._chamber_solid). Alan yoksa kapak yok.
        var closure = new THREE.Group();
        if (d.capT !== null && d.capT > 0) {
            var capPoly = [
                { r: 0, z: -d.capT },
                { r: d.rcOut, z: -d.capT },
                { r: d.rcOut, z: 0 },
                { r: 0, z: 0 }
            ];
            closure.add(tagPart(
                buildSolid(capPoly, mats.casing, mats.casingCut, cut),
                'closure_cap', d.capT, plan.sources.closure_cap));
            addJointLine(closure, 0.4); // kapak-tüp birleşim izi
            // Kapak cıvataları: sayı + delik YAYIMLANDIYSA; çember sabit
            // yerleşim kuralıdır ve YALNIZ künyesiyle çizilir.
            if (plan.bolts) {
                var pb = plan.bolts;
                var cbGeo = new THREE.CylinderGeometry(pb.holeMm / 2,
                    pb.holeMm / 2, d.capT, 6);
                for (var cb = 0; cb < d.nBolts; cb++) {
                    var cphi = ((cb + 0.5) / d.nBolts) * TAU;
                    var cbolt = new THREE.Mesh(cbGeo, mats.bolt);
                    cbolt.position.set(pb.circleMm * Math.sin(cphi),
                        -d.capT / 2, pb.circleMm * Math.cos(cphi));
                    cbolt.userData.phi = cphi;
                    cbolt.userData.hideInCut = true;
                    cbolt.castShadow = true;
                    cbolt.receiveShadow = true;
                    tagPart(cbolt, 'closure_bolts', pb.holeMm, pb.basis);
                    closure.add(cbolt);
                }
            }
        }
        this.parts.closure = closure;

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
                    chMesh.receiveShadow = true;      // komşu kanal gölgesi
                    casing.add(chMesh);
                }
            } else {
                this._coolingChip = {
                    // P17B1-09: beyan çipi de oturum dilinde.
                    text: T('viz3d.chip.coolingNoData',
                            'cooling channels: no data'), kind: 'missing'
                };
            }
        }

        // --- Astar (grain'li motorlarda) — CM-S1: dış yarıçap kasa deliği
        // (eski rc - 0,15 kesri söküldü), kalınlık YAYIMLANAN alandan:
        //  * thermal_protection.chamber_liner.thickness → astar, çözücünün
        //    kendi tanımıyla tanenin ÖRTMEDİĞİ kesimlerde (ön/arka oda);
        //  * yoksa tane ile kasa deliği arası (iki yayımlanan çapın farkı)
        //    → yalıtım, kamara boyunca.
        // İkisi de yoksa astar ÇİZİLMEZ.
        this.parts.liner = new THREE.Group();
        if (!isLiquid && plan.liner) {
            var ln = plan.liner;
            var linerSpans = (ln.span === 'unshielded')
                ? [[0, d.zg0], [d.zg1, d.Lch]] : [[0, d.Lch]];
            for (var ls = 0; ls < linerSpans.length; ls++) {
                var za = linerSpans[ls][0], zb = linerSpans[ls][1];
                if (!(zb > za)) continue;
                this.parts.liner.add(tagPart(buildSolid([
                    { r: ln.rIn, z: za },
                    { r: d.rc, z: za },
                    { r: d.rc, z: zb },
                    { r: ln.rIn, z: zb }
                ], mats.liner, mats.linerCut, cut), 'chamber_liner', ln.tMm,
                    ln.basis));
            }
        }

        // --- Enjektör plakası + orifis deseni (katı motorda yok) ---
        // A1a sahne-sahte-veri · CM-S1: plaka kalınlığı YALNIZ
        // injector_design.plate_thickness_mm alanından (eski 0,9 x kapak
        // kesri + hibrit kırpması söküldü; değer kırpılmadan, bit-aynı
        // çizilir). Plaka kamara deliğini doldurur ve kapağın iç yüzüne
        // oturur (manifold boyu yayımlanmıyor → boşluk uydurulmaz). Alan
        // yoksa plaka ve yüzündeki delik deseni ÇİZİLMEZ.
        if (!isSolid && d.partPlan && d.partPlan.plateT !== null) {
            var injZ0 = 0;
            var injT = d.partPlan.plateT;
            var injPoly = [
                { r: 0, z: injZ0 },
                { r: d.rc, z: injZ0 },
                { r: d.rc, z: injZ0 + injT },
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
                post.receiveShadow = true;   // plaka gölgesi pintle gövdesinde
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
                // ÖH D24 / P11B1-07 — SAHNENİN SON KODA GÖMÜLÜ TÜRKÇESİ.
                // ÖLÇÜLDÜ (a3/once.json): dosyanın kendi sözleşmesi
                // (anahtar sözlükte yoksa İNGİLİZCE tam metin döner)
                // dışında kalan iki yerden biri buydu; en-US oturumda tek
                // çip yığınında iki dil okunuyordu. Sayı değişmez.
                var swChip = statusChip(
                    T('viz3d.chip.sprayAngle', 'spray angle') + ' '
                    + numTxt((2 * swHalf), 0) + '°', 'computed');
                var swH = Math.max(6, Math.min(d.Lch * 0.05, d.rc * 0.8));
                swChip.scale.set(swH * swChip.userData.aspect, swH, 1);
                swChip.position.set(0, injFace + swLen * 1.12, 0);
                injector.add(swChip);
            }

            // A1a sahne-sahte-veri · CM-S1: hibrit ateşleyici (0,09 x rc
            // yarıçap, kapaktan porta uzanan boy) SÖKÜLDÜ — igniter_sizing
            // bu çözücüde değerlendirilmiyor, ölçüsü hiçbir alanda yok.
            // Plakanın yüz geometrisi plakanın parçasıdır (aynı künye).
            this.parts.injector = tagPart(injector, 'injector_plate', injT,
                plan.sources.injector_plate);
        } else {
            this.parts.injector = new THREE.Group();
        }

        // --- Yakıt grain'i (port yarıçapı animasyonlu — ayrı build) ---
        this.parts.grain = new THREE.Group();
        this._grainMesh = null;
        this._resolvePortRegression();
        this._rebuildGrain(portRadiusAt(d, this.state.time, this._portRegMode), true);

        // --- Nozul: iç kontur + yayımlanan cidar ---
        // A1a sahne-sahte-veri · CM-S1: grafit boğaz eki (0,35 x rt), lüle
        // flanşı (0,8 x kapak / 0,10 x rc), flanş O-ringi (0,18 x flanş) ve
        // flanş cıvataları (0,05 x rc çap, flanş kesri boy) SÖKÜLDÜ. Lüle
        // bağlantısı yapısal analizde ayrı boyutlandırılmıyor
        // (fastener_analysis yalnız ön kapak yükünü taşır: "Total force on
        // end cap") → lüle cıvatası için yayımlanan ölçü yok.
        var np = nozzleProfile(d);
        this._nozzleInfo = np;
        var nozzle = buildSolid(np.poly, mats.nozzle, mats.nozzleCut, cut);
        addJointLine(nozzle, d.Lch - 0.4); // tüp-lüle birleşim izi
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
        // A1a sahne-sahte-veri · CM-S1: giriş borusu söküldü; model önde
        // yayımlanan kapakla (yoksa kamara iç yüzüyle) biter.
        var zMin = -(d.capT > 0 ? d.capT : 0);
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
        var floorY = floorYMm(this.dims.rcOut + this.dims.flangeLip);
        if (!this._floor) {
            var shadowPlane = new THREE.Mesh(
                new THREE.PlaneGeometry(this._totalLen * 4, this._totalLen * 4),
                new THREE.ShadowMaterial({
                    opacity: RENDER_QUALITY.shadow.floorOpacity })
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
            // Hücre boyu rozeti: mutlak referans beyanı (metin hücreden,
            // ölçek ve konum MOTORDAN — bkz. gridBadgePositionMm)
            var badge = textSprite(gridBadgeText(cell), {
                border: 'rgba(20, 111, 128, 0.7)', color: '#7fd4e2'
            });
            badge.material.depthTest = true;   // HUD değil, zemin mobilyası
            badge.renderOrder = 0;
            this._gridBadge = badge;
            this.scene.add(badge);
        }
        this._grid.position.y = floorY + 0.5;
        this._grid.scale.setScalar(1);   // motorla ölçeklenmez (kalem 5)
        // Rozetin ölçeği ve konumu HER kurulumda tazelenir: ızgara hücresi
        // aynı kalsa bile motor boyu değişmiş olabilir (rozet artık ızgaraya
        // değil motora bağlı; yalnız kurulum anında ayarlanırsa bayatlar —
        // zemin düzleminde aynı kusur "görev 5a" ile kapatılmıştı).
        var gbH = chipHeightMm(this._totalLen || 1,
            2 * (this.dims.rcOut + this.dims.flangeLip));
        this._gridBadgeH = gbH;
        this._gridBadge.scale.set(gbH * this._gridBadge.userData.aspect, gbH, 1);
        var gbP = gridBadgePositionMm(this._totalLen || 1, floorY, gbH);
        this._gridBadge.position.set(gbP.x, gbP.y, gbP.z);
        this._gridBadgeFloorY = floorY;   // dil değişiminde yeniden kurulum için
        // Izgara yeniden kurulduysa CAD nötr stüdyo stili korunur
        if (this.state.cadMode) this._applyCadGridStyle(true);

        // Durum çipleri (kaynak şeffaflığı, v2.6.27): her çip GERÇEK bir
        // duruma bağlıdır ve rengi SOURCE_COLORS eşlemesinden gelir.
        //  * kontur kaynağı her motorda beyan edilir (çözücü/yerel üretim)
        //  * sıvı motorda soğutma kanalı verisi yoksa 'veri yok' çipi
        this._floorY = floorY;
        this._buildStatusChips(this._statusChipDefs(), floorY);

        // CFD alan katmanı varsa süs örtüşme kararları yeni kuruluma
        // yeniden uygulanır (kesit/patlatma/kalite geçişleri buradan geçer)
        if (this._cfdLayer) this._syncCfdDecor();
    };

    // Durum çipi tanımları TEK yerde üretilir: hem zemin kurulumunda hem
    // kip/dil değişiminde aynı liste kullanılır.
    MotorScene.prototype._statusChipDefs = function () {
        var d = this.dims;
        var defs = [];
        if (this._coolingChip) defs.push(this._coolingChip);
        // ÖH D26 / P11B1-09 — uydurma yedeğe düşen ölçüler beyan edilir.
        // (Önce: birincil ölçülerin dördü de sessizce uyduruluyordu.)
        // ÖH D31 · OH-D27-13 — panel rozeti sahne çipiyle AYNI listeden
        // beslenir. Kanca BURADA, `dimensionSourceChipDefs`in İÇİNDE
        // değil: mevcut bekçiler (D26 a1, D29 a2) o işlevi tek başına
        // çıkarıp node'da eval ediyor; gövdesine serbest bir ad koymak
        // onları ReferenceError ile kırar (ölçüldü).
        defs = defs.concat(dimensionSourceChipDefs(d));
        _varsayimRozetiniTazele(defs, d);
        // --- ÖH D29 · P11B1-12 — İKİ BEYAN ALANI ÇİPE BAĞLANDI ------------
        // ÖLÇÜLDÜ (a2/once.json P11B1-12): `extractDims` 41 alan döndürüyor
        // ve bunların İKİSİ sahnede de güvertede de HİÇ okunmuyordu:
        // `injectorSource` ('injector_results' | 'injector_design') ve
        // `contourBasis` (`nozzle_contour._basis` künyesi). İkisi de beyan
        // için hesaplanıp atılıyordu; `injectorSource` tam olarak
        // "kullanıcı hangi enjektörü gördüğünü bilemiyor" (P11B1-04)
        // kusurunun taşıyıcısıydı.
        // Beyan UYDURULMAZ: künye yükten gelmediyse çip basılmaz; enjektör
        // hiç çizilmediyse (nOrifices = 0 ve desen yok) enjektör çipi de
        // basılmaz — çizilmeyen şeyin kaynağı beyan edilmez.
        defs.push(d.contourSource === 'solver'
            // P17B1-09: kaynak beyanı çipleri de oturum dilinde.
            ? { text: T('viz3d.chip.contourSolver', 'contour: solver')
                    + (d.contourBasis ? ' (' + d.contourBasis + ')' : ''),
                kind: 'computed', basis: d.contourBasis || null }
            : { text: T('viz3d.chip.contourLocal', 'contour: locally generated')
                    + (d.contourBasis ? ' (' + d.contourBasis + ')' : ''),
                kind: 'assumed', basis: d.contourBasis || null });
        if (d.injectorSource && (d.nOrifices > 0 || d.injPattern)) {
            defs.push({
                // i18n devri (arayuz-i18n): metin bu dalgada anahtarsız
                // basılır — künyenin kendisi zaten makine dizesidir
                // ('injector_results' / 'injector_design').
                text: 'injector block: ' + d.injectorSource,
                kind: 'computed', field: 'injector_source'
            });
        }
        // A1a sahne-sahte-veri · CM-S1 — delik deseni plakanın parçasıdır:
        // plaka kalınlığı yayımlanmadıysa plaka da deseni de çizilmez, o
        // yüzden desenin kaynağı da beyan edilmez (çizilmeyen şeyin künyesi
        // kullanıcıyı yanıltır — yukarıdaki çipin kendi kuralı).
        var plan = d.partPlan || null;
        if (!(plan && plan.plateT !== null)) {
            defs = defs.filter(function (c) {
                return c.field !== 'injector_source';
            });
        }
        // Montaj planı beyanı: yayımlanan ölçüsü olmayan parçalar ÇİZİLMEDİ
        // ve sayıları söylenir (sayı ölçülür: planın çizilmeyenler listesi).
        if (plan && plan.undrawn && plan.undrawn.length) {
            defs.push({
                text: T('viz3d.chip.noAssemblyPlan',
                        'no assembly plan — {n} parts not drawn '
                        + '(layout rule, not a dimension)')
                    .replace('{n}', String(plan.undrawn.length)),
                kind: 'missing', field: 'assembly_plan',
                parts: plan.undrawn.slice()
            });
        }
        // Cıvata çizildiyse çemberinin künyesi (sabit yerleşim kuralı)
        // amber varsayım çipinde, A2 cm-0-plan ASSUMED tablosuyla birebir.
        if (plan && plan.bolts) {
            defs.push({
                text: T('viz3d.chip.boltCircle', 'bolt circle') + ': '
                    + plan.bolts.basis,
                kind: 'assumed', field: 'bolt_circle',
                basis: plan.bolts.basis
            });
        }
        // Yanma animasyonunun kaynağı (B5): çip, iç yüzeyin neyden
        // gerilediğini — ya da gerilemediğini — beyan eder.
        if (d.motorType !== 'liquid') {
            defs = defs.concat(portRegressionChipDefs(this._portRegMode,
                { endsBurn: d.endsBurn }));
        }
        // A1b faz-c-0 · OH-D37-S7 — yayımlanmayan itki / Isp / Pc adıyla
        // (HUD yayını onları null taşır; sayı uydurulmaz). En sona: mevcut
        // çiplerin sırası ve yeri değişmez.
        var perfCip = perfNotPublishedChipDef(d);
        if (perfCip) defs.push(perfCip);
        return defs;
    };

    // Çipleri yerinde tazele (kip ya da dil değişti). Zemin henüz
    // kurulmadıysa sessizce atlanır — kurulumda zaten üretilecekler.
    MotorScene.prototype._refreshStatusChips = function () {
        if (this._floorY === undefined) return;
        this._buildStatusChips(this._statusChipDefs(), this._floorY);
    };

    // ÖH D23 / P17B1-09 (ayak 2) — IZGARA ROZETİ DE DİLE BAĞLI.
    // ÖLÇÜLDÜ (a2 once.json: lang_izgara_rozetini_tazeler = 0,
    // lang_etiketleri_tazeler = 0): dil dinleyicisi YALNIZ durum çiplerini
    // ve CFD renk çubuğunu tazeliyordu. Izgara hücresi rozeti
    // (`gridBadgeText` → 'grid 10 mm' / 'ızgara 10 mm') ve ölçü etiketleri
    // (`dimensionLabelTexts` → 'ØC inner … / outer …', 'GRAIN … mm') canvas
    // sprite metnidir; DOM olmadıkları için i18n.js'in translateTree'si
    // onlara ULAŞAMAZ ve yalnız KURULUM anında çözülüyorlardı. Sonuç:
    // kullanıcı EN⟷TR düğmesine bastığında sayfanın geri kalanı çevrilir,
    // 3B sahne eski dilde donar — hükmün (H1) ölçtüğü kusurun kalıcı hâli.
    // Rozet metni hücreden, ölçek ve konum MOTORDAN gelir; ikisi de
    // saklanan son değerlerden yeniden kurulur (uydurma değer yok).
    MotorScene.prototype._refreshGridBadge = function () {
        if (!this._gridBadge || this._gridCell === undefined) return;
        if (this._gridBadgeFloorY === undefined) return;
        var eski = this._gridBadge;
        this.scene.remove(eski);
        if (eski.material.map) eski.material.map.dispose();
        eski.material.dispose();
        var badge = textSprite(gridBadgeText(this._gridCell), {
            border: 'rgba(20, 111, 128, 0.7)', color: '#7fd4e2'
        });
        badge.material.depthTest = true;   // HUD değil, zemin mobilyası
        badge.renderOrder = 0;
        this._gridBadge = badge;
        this.scene.add(badge);
        var gbH = this._gridBadgeH || chipHeightMm(this._totalLen || 1,
            2 * (this.dims.rcOut + this.dims.flangeLip));
        badge.scale.set(gbH * badge.userData.aspect, gbH, 1);
        var gbP = gridBadgePositionMm(this._totalLen || 1,
            this._gridBadgeFloorY, gbH);
        badge.position.set(gbP.x, gbP.y, gbP.z);
        if (this.state.cadMode) this._applyCadGridStyle(true);
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
            hasPortArea: !!d.portAreaHist,
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

    // Izgara hücre rozetinin yerleşimi (parti 26). ÇİPLERLE AYNI SINIF KUSUR
    // ve aynı çare: rozet ızgara açıklığının köşesine (±0,42·span) konuyordu,
    // ızgara ise ~3 motor boyu — kamera MOTORU çerçevelediği için rozet
    // kadrajın dışında kalıyordu. ÖLÇÜLDÜ (2026-08-16, cameraFrameFit +
    // izdüşüm matematiği; katı öğretici motoru L = 732,5 mm, R = 54,5 mm,
    // 800×520 konteyner):
    //   eski konum (924,0 · −50,7 · 924,0) mm -> NDC u = −0,979, v = +11,47,
    //   derinlik = −193 mm (NEGATİF: rozet kameranın ARKASINDA),
    //   yeni konum (−307,6 · −83,6 · +73,3) mm -> NDC u = −0,505, v = +0,045.
    // Rozet motorun ÖN tarafında (z > 0) durur: arka köşede gövdenin
    // ardında kalabiliyordu (ölçüldü, kısa-tıknaz motorda eksene NDC
    // uzaklığı yarıçapın 0,4 katı). Yeni konumda eksene uzaklık en dar
    // vakada bile yarıçapın 1,7 katı. Tarama (L = 150…6000 mm, R = 15…120 mm,
    // en-boy 1,0…2,5): en kötü kenar payı |NDC| = 0,737.
    var GRID_BADGE_Z_FACTOR = 0.10;
    function gridBadgePositionMm(totalLen, floorY, badgeH) {
        return {
            x: -chipAnchorMm(totalLen),
            y: floorY + badgeH * 0.8,
            z: totalLen * GRID_BADGE_Z_FACTOR
        };
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
        // Silindirin z-aralığı TEK kaynaktan (glowZSpan): CFD alan katmanı
        // örtüşme ölçümü aynı aralığı okur — formül kopyası yok
        var span = glowZSpan(d);
        var geo = new THREE.CylinderGeometry(r, r, span.height, 40, 1, true);
        this._glowMesh = new THREE.Mesh(geo, this._glowMat);
        this._glowMesh.position.y = span.center; // portu + art odasını kapla
        this.assembly.add(this._glowMesh);
        // CFD alanı aktifse örtüşme kararı yeni mesh'e yeniden uygulanır
        // (yeni mesh visible=true doğar; gizleme kararı katmandan gelir)
        if (this._cfdLayer) this._syncCfdDecor();
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
        // Rampa alanı TEK KAYNAKTAN (ÖH D24 · P11B1-02): efsane etiketi de
        // aynı `heatRampDomain` çıktısını yazar.
        var qT = on ? d.heat.qThroat : 1;
        var dom = heatRampDomain(on ? d.heat : null);
        var lnMin = Math.log(dom.qMin);
        var lnMax = Math.log(dom.qMax);

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
    // Ofsetler EXPLODE_OFFSETS tablosundan (tek kaynak): gölge kadrajı da
    // aynı tablodan en büyük ofseti okuyup frustumu açar — patlatılmış
    // parçaların gölgesi kırpılmasın (B7 kalem 1).
    MotorScene.prototype._applyExplode = function (f) {
        if (!this.parts.casing) return;
        var L = this._totalLen;
        var parts = this.parts;
        Object.keys(EXPLODE_OFFSETS).forEach(function (k) {
            if (parts[k]) parts[k].position.y = EXPLODE_OFFSETS[k] * L * f;
        });
        this._explodeF = f;
        this._applyShadowFit();
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
        // KU-25 / K-12: eski künyesiz `pressureTurn = clamp((pe/pa)^0,5,
        // 0,6, 1,8)` çarpanı kaldırıldı. Yerine ilk jet sınırı eğimi:
        //     δ = θ_N + [ν(Mj) − ν(Me)]
        // (Love 1959, NASA TR R-6, s. 7 "Initial inclination of jet
        // boundary": dudaktaki 2B genişleme/sıkışma + θ_N eklenir). Açı
        // çekirdek koniyle AYNI kaynaktan (plumeConeSpec) — tek bağıntı.
        var thetaDeg = d.nozType === 'conical' ? d.halfAngle : d.thetaE;
        var cone = plumeConeSpec(d.re, clamp(thetaDeg, 2, 35), ex.exitMach,
            ex.jetMach, ex.gamma, 0);
        if (!cone) return null;
        var spread = Math.tan(THREE.MathUtils.degToRad(cone.halfAngleDeg))
            / Math.tan(THREE.MathUtils.degToRad(PLUME_REF_EXIT_ANGLE_DEG));

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
        // İlk elmasın çıkış düzleminden uzaklığı YALNIZ künyeli bir plüm
        // modeli onu yayımlarsa bilinir: fiziksel konum p_j/p_∞'a güçlü
        // bağlıdır (Love 1959, NASA TR R-6, Şekil 8: l/d_j ≈ 0,2 … 8). Bugün
        // bu konumu yayımlayan model YOK. Karar §27-15 (v3.0.1): kaynaksız
        // 0,9·d_e yerleşimi söküldü; konum yayımlanana dek elmaslar
        // ÇİZİLMEZ. Prandtl-Pack aralığı tek başına yetmez — ilk konum
        // olmadan bütün dizi uydurma bir ofsetle kayar.
        var ilkHucreMm = info ? info.firstCellOffsetMm : undefined;
        // Çözücü verisi yoksa, jet ses altıysa (Mj ≤ 1,02) ya da ilk hücre
        // konumu yayımlanmadıysa elmasları gizleriz.
        if (!info || !(info.diamondSpacing > 0) || !(ilkHucreMm > 0)) {
            for (var j = 0; j < this._diamonds.length; j++) {
                this._diamonds[j].visible = false;
            }
            return;
        }
        for (var k = 0; k < this._diamonds.length; k++) {
            this._diamonds[k].visible = true;
            var yk = ilkHucreMm + k * info.diamondSpacing;
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

        // Çekirdek koni şiddeti (kalem 3): itkiyle (throttle) orantılı; taban
        // opaklık kuruluşta userData'da. Zamanla salınan titreşim çarpanı
        // YOK: veriye bağlı olmayan animasyon yasak (karar §27-15, v3.0.1).
        if (this._flameGroup) {
            this._flameGroup.visible = true;
            for (var m = 0; m < this._flameGroup.children.length; m++) {
                var cm = this._flameGroup.children[m];
                cm.material.opacity =
                    cm.userData.baseOpacity * clamp(intensity, 0, 1);
            }
        }

        // Elmas şiddeti basınç uyumsuzluğuyla (|1 − pe/pa| yaklaşımı) ölçekli:
        // ideale yakın genişlemede elmaslar söner, sapmada belirginleşir.
        // Elmaslar yalnız konumları yayımlandığında görünür
        // (_updateDiamondPositions). Titreşim çarpanı ve kaynaksız hücreler
        // arası sönüm katsayısı söküldü (§27-15); hücre başına şiddet plüm
        // modeli yayımlayınca girer.
        var dstr = this._plumeInfo ? this._plumeInfo.diamondStrength : 1;
        for (var k = 0; k < this._diamonds.length; k++) {
            this._diamonds[k].material.opacity =
                this._diamonds[k].visible ? intensity * dstr : 0;
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
            totalMm: this._nozzleInfo.zExit + (d.capT > 0 ? d.capT : 0),
            grainMm: d.Lg,
            // P11B1-05: sıvıda ODA etiketi BU alandan yazılır (d.Lg'den
            // değil); kaynak bayrağı false ise etiket hiç kurulmaz.
            chamberLengthMm: d.Lch,
            chamberLengthKaynakli: d.LchKaynakli
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
        // Anahtar + dolgu konumu ve gölge kadrajı tek elden (_applyShadowFit)
        this._applyShadowFit();
        this._rimCyan.position.set(-L * 0.9, L * 0.25, -L * 0.9);
        this._rimOrange.position.set(L * 1.0, -L * 0.35, -L * 0.7);
        cam.far = Math.max(dist, L) * 30;
        cam.updateProjectionMatrix();
        // CAD kipindeyken geometri değişimi ortografik kadrajı da tazeler
        if (this.state.cadMode) this.setCadPreset(this._cadPresetName || 'iso');
    };

    // Sürücünün desteklediği en yüksek anizotropik süzme (r128 yeteneği).
    // WebGL bağlamı yoksa (test/harness) süzme varsayılanda kalır.
    MotorScene.prototype._maxAnisotropy = function () {
        try {
            return this.renderer.capabilities.getMaxAnisotropy();
        } catch (e) {
            return 1;
        }
    };

    // Gölge kalitesi TEK NOKTADAN (B7, kalem 1 + 5). Çağrı yerleri:
    //   _fitCamera    — geometri/kadraj değişti
    //   _applyExplode — eksen boyu patlatmayla büyür/küçülür
    //   setQuality    — kalite kipi mapSize'ı değiştirir
    // Sürücü sınırı: r128 gölge dokusunu maxTextureSize'a KENDİ kısar
    // (WebGLShadowMap: `r.x>h && (u.mapSize.x = ...)`), o yüzden 4096 istemek
    // zayıf donanımda güvenlidir.
    MotorScene.prototype._applyShadowFit = function () {
        var key = this._keyLight;
        if (!key || !this._totalLen) return null;
        var RQ = RENDER_QUALITY.shadow;
        // Yönlü ışıkların konumu da BURADA: gölge kadrajı ışık konumundan
        // türetildiği için ikisi asla ayrı düşmemeli (kuruluş sırasından
        // bağımsız — _buildMotor, _fitCamera'dan ÖNCE de çağırabilir).
        var L = this._totalLen;
        var LI = RENDER_QUALITY.lights;
        key.position.set(L * LI.keyDir.x, L * LI.keyDir.y, L * LI.keyDir.z);
        if (this._fillLight) {
            this._fillLight.position.set(
                L * LI.fillDir.x, L * LI.fillDir.y, L * LI.fillDir.z);
        }
        var want = this._perfMode ? RQ.mapSizePerf : RQ.mapSizeHigh;
        if (key.shadow.mapSize.x !== want) {
            // r128 gölge hedefini YALNIZ `null === shadow.map` iken kurar;
            // canlı boyut değişimi için eski hedef atılmalı, yoksa yeni
            // mapSize sessizce yok sayılır (vendor kodundan ölçüldü).
            if (key.shadow.map) {
                key.shadow.map.dispose();
                key.shadow.map = null;
            }
            key.shadow.mapSize.set(want, want);
        }
        var R = (this.dims.rcOut + this.dims.flangeLip) || 1;
        var fit = shadowFrustumFit(
            shadowAxisHalfMm(this._totalLen, this._explodeF),
            R, floorYMm(R), key.position, want, RQ.fitMargin);
        var sc = key.shadow.camera;
        sc.left = -fit.halfW; sc.right = fit.halfW;
        sc.top = fit.halfH; sc.bottom = -fit.halfH;
        sc.near = fit.near; sc.far = fit.far;
        sc.updateProjectionMatrix();
        key.shadow.bias = fit.bias;
        key.shadow.normalBias = fit.normalBias;
        this._shadowFit = fit;   // ölçüm/teşhis için son kadraj
        return fit;
    };

    MotorScene.prototype._bindResize = function () {
        var self = this;
        this._ro = new ResizeObserver(function () {
            if (self._disposed) return;
            var w = self.container.clientWidth, h = self.container.clientHeight;
            if (w < 10 || h < 10) return;
            self._kick();   // V301/K-C1: yeni boyut bir kare ister
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
            // ÖH D23 / P17B1-09 (ayak 2): ölçü etiketleri ve ızgara hücresi
            // rozeti de sprite metnidir — dil değişiminde YENİDEN ÜRETİLİR.
            // _buildLabels eski etiket grubunu kendi dispose eder (H1).
            if (self.dims && self._nozzleInfo) self._buildLabels();
            self._refreshGridBadge();
            // Colorbar metinleri de dil değişiminde tazelenir
            if (self._cfdLayer) self._cfdUpdateColorbar();
            // K1b: probe satırı da (DOM, ama sahnenin kendi metni)
            if (self._probe) self._probeRender();
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
            this._camMoved = this.controls.update();
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
        // ÖH D36 / onemli2-sivi a2: süre yoksa (dims.burnTime null) zaman
        // ekseni yoktur — sahne oynatılmaz, saat 0'da kalır.
        var zamanVar = typeof d.burnTime === 'number' && isFinite(d.burnTime);
        if (st.playing && !zamanVar) st.playing = false;
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

        // Yanma ışıkları + parıltı: itkiyle (throttle) orantılı, zamanla
        // salınmaz (sahte titreşim söküldü — karar §27-15, v3.0.1).
        this._glowMat.opacity = throttle * 0.5;
        this._throatFlame.material.opacity = throttle * 0.85;
        var Lw = this._totalLen;
        this._combLight.intensity = throttle * 1.4;
        this._combLight.distance = Lw * 1.6;
        this._exitLight.intensity = throttle * 1.8;
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
        // V301/K-C1: update() kamerayı bu karede oynattıysa true döner
        // (sönüm sürüyor demektir; döngü uyumaz).
        this._camMoved = this.controls.update();
        this.renderer.render(this.scene, this.camera);
        // K1b: kamera/sahne kıpırdadıysa imleç altındaki okuma tazelenir
        if (this._probeNdc) this._probeFollow();

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
                // Süre yoksa (a2) zaman ekseni yok: çip tasarım itkisini
                // gösterir (kararlı rejim), "yanma bitti = 0" demez.
                thrust: thrustNow !== null
                    ? (st.time < d.burnTime ? thrustNow : 0)
                    : (!zamanVar ? d.thrust
                       : (st.time < d.burnTime ? d.thrust : 0)),
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

    // ------------------------------------------------------------------
    // CFD alan katmanı (parti 30 — A2): /api/cfd/nozzle r-z alanı, kesit
    // kamasının iki düz r-z yüzünde ANSYS tarzı renkli kesit.
    //
    // Kama parametreleri: phiStart = CUT_PHI_START + CUT_PHI_LENGTH,
    // phiLength = TAU − CUT_PHI_LENGTH — yani metalin AÇIK bıraktığı tam
    // 90°'lik kama. Alan yalnız kamanın İKİ DÜZ YÜZÜNE (φ=45° ve φ=315°
    // r-z düzlemleri) çizilir; kamanın eğri dış kabuğu BİLEREK çizilmez:
    // kabuk duvar yarıçapında kamayı kaplar ve kamera φ=0 yönünden
    // bakarken iki kesit düzleminin ÖNÜNDE durur — çizilseydi kesit
    // alanını örterdi (geometrik ölçüm: kabuk r=r_duvar'da, düzlemler
    // r<=r_duvar'da; açıklık kameraya bakar).
    // ------------------------------------------------------------------

    // Katman geometrisi: hücre başına DÜZ (flat) karo. Hücre-merkezli
    // FVM'de hücre değeri hücre boyunca sabittir; köşelerde renk
    // ENTERPOLE EDİLMEZ (Gouraud yumuşatma var olmayan ara değerler
    // uydururdu). Karolar beyan edilen düzgün radyal dağılımın GERÇEK
    // hücre uzanımlarıdır: j. sıra [j·rw/nj, (j+1)·rw/nj] bandını kendi
    // sabit değeriyle kaplar — ilk sıra eksene (r=0), son sıra duvara
    // (cfdWallRadii) kendiliğinden dayanır, yeni değer üretilmez.
    // Bant kenarlarındaki duvar yarıçapı komşu istasyon değerlerinin
    // doğrusal ara değeridir (ızgaranın kendi η-çizgileri de duvarla
    // doğrusal ölçeklenir); uçlarda en yakın istasyon değeri sürer.
    MotorScene.prototype._cfdBuildLayer = function (cfd, field, walls, edges) {
        var d = this.dims;
        var nAx = field.z_m.length;
        var nRad = field.r_m[0].length;
        var k, j;

        var wallEdges = [walls[0]];
        for (k = 1; k < nAx; k++) {
            wallEdges.push(0.5 * (walls[k - 1] + walls[k]));
        }
        wallEdges.push(walls[nAx - 1]);

        var zEdgesMm = [], wallEdgesMm = [];
        for (k = 0; k <= nAx; k++) {
            zEdgesMm.push(contourZToScene(d, edges[k] * 1000));
            wallEdgesMm.push(wallEdges[k] * 1000);
            if (!isFinite(zEdgesMm[k]) || !isFinite(wallEdgesMm[k])) {
                return null;
            }
        }

        var phiA = CUT_PHI_START + CUT_PHI_LENGTH;            // 315° düzlemi
        var phiB = phiA + (TAU - CUT_PHI_LENGTH);             // 45° düzlemi
        var phis = [phiA, phiB];
        var nCells = nAx * nRad;
        var pos = new Float32Array(nCells * 12 * 3);
        var p = 0;
        function push(r, z, s, c) {
            pos[p++] = r * s; pos[p++] = z; pos[p++] = r * c;
        }
        for (k = 0; k < nAx; k++) {
            var z0 = zEdgesMm[k], z1 = zEdgesMm[k + 1];
            var w0 = wallEdgesMm[k], w1 = wallEdgesMm[k + 1];
            for (j = 0; j < nRad; j++) {
                var fl = j / nRad, fh = (j + 1) / nRad;
                for (var f = 0; f < 2; f++) {
                    var s = Math.sin(phis[f]), c = Math.cos(phis[f]);
                    // Karo köşeleri (trapez): (z0,fl·w0)-(z1,fl·w1)-
                    // (z1,fh·w1)-(z0,fh·w0); iki üçgen
                    push(fl * w0, z0, s, c); push(fl * w1, z1, s, c);
                    push(fh * w1, z1, s, c);
                    push(fl * w0, z0, s, c); push(fh * w1, z1, s, c);
                    push(fh * w0, z0, s, c);
                }
            }
        }

        var geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(
            new Float32Array(nCells * 12 * 3), 3));
        // MALZEME IŞIKSIZ (MeshBasicMaterial) ve toneMapped:false —
        // ışıklı malzeme rengi aydınlatmayla, ACES ton eşleme rengi
        // pozlamayla çarpar; ikisi de ekran rengini colorbar'dan
        // koparırdı (colorbar yalan söylerdi). Vertex renkleri sRGB→
        // lineer çevrilerek yazılır; outputEncoding=sRGB çıkışta geri
        // çevirir → ekran pikseli = skala hex'i. polygonOffset: kesit
        // düzlemleri metal kapaklarla aynı düzlemde (φ=45°/315°) durur,
        // duvar kenarındaki ince şeritte z-çakışması önlenir.
        var mat = new THREE.MeshBasicMaterial({
            vertexColors: true, side: THREE.DoubleSide, toneMapped: false,
            polygonOffset: true, polygonOffsetFactor: -1,
            polygonOffsetUnits: -1
        });
        var mesh = new THREE.Mesh(geo, mat);
        var group = new THREE.Group();
        group.add(mesh);
        this.model.add(group);

        return {
            cfd: cfd, field: field, group: group, mesh: mesh,
            geometry: geo, material: mat,
            nAx: nAx, nRad: nRad, nCells: nCells,
            zSceneLo: zEdgesMm[0], zSceneHi: zEdgesMm[nAx],
            stationsShown: (Array.isArray(field.axial_indices)
                ? field.axial_indices.length : nAx),
            stationsTotal: (Array.isArray(field.grid_shape)
                ? num(field.grid_shape[0], nAx)
                : num(cfd.grid && cfd.grid.ni, nAx)),
            decimated: !!field.decimated,
            metric: null, range: null,
            alignment: null, cutawayForced: false, decorHidden: [],
            colorbarEl: null
        };
    };

    // Metrik uygula: GEOMETRİ YENİDEN KURULMAZ, yalnız renk özniteliği
    // ve colorbar güncellenir (sözleşme). Dönen değer ok sözlüğü değil
    // ara sonuçtur; dışa açık biçim _cfdResult'tan çıkar.
    MotorScene.prototype._cfdApplyMetric = function (id) {
        var L = this._cfdLayer;
        if (!L) return cfdReason('no_field', { metric: id });
        var m = null;
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (CFD_METRICS[i].id === id) m = CFD_METRICS[i];
        }
        if (!m || !cfdFieldHasMetric(L.field, id)) {
            return cfdReason('missing_metric', { metric: id });
        }
        var vals = cfdMetricValues(L.field, m.payloadKey);
        if (!vals) {
            return cfdReason('bad_field_block',
                { missing: 'finite ' + m.payloadKey });
        }
        var stops = CFD_COLORSCALES[id];
        var attr = L.geometry.getAttribute('color');
        var span = vals.max - vals.min;
        var col = new THREE.Color();
        for (var c = 0; c < L.nCells; c++) {
            // span=0 (sabit alan): tüm hücreler aynı değerde — skala
            // ortası; colorbar min=max'ı zaten beyan eder
            var t = span > 0 ? (vals.values[c] - vals.min) / span : 0.5;
            col.set(cfdColorLookup(stops, t));
            col.convertSRGBToLinear();
            for (var v = 0; v < 12; v++) {
                var base = (c * 12 + v) * 3;
                attr.array[base] = col.r;
                attr.array[base + 1] = col.g;
                attr.array[base + 2] = col.b;
            }
        }
        attr.needsUpdate = true;
        L.metric = id;
        L.range = { min: vals.min, max: vals.max };
        this._cfdPreferredMetric = id;
        this._cfdUpdateColorbar();
        return { ok: true };
    };

    // Dışa açık sonuç sözlüğü (sözleşme biçimi). decor_hidden: örtüşme
    // ölçümüyle gizlenen süs katmanlarının beyanı (görev 3. kalem).
    MotorScene.prototype._cfdResult = function () {
        var L = this._cfdLayer;
        var m = null;
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (CFD_METRICS[i].id === L.metric) m = CFD_METRICS[i];
        }
        return {
            ok: true,
            metric: L.metric,
            range: { min: L.range.min, max: L.range.max },
            unitLabel: m ? m.unit : '',
            cells: { axial: L.nAx, radial: L.nRad },
            stations: { shown: L.stationsShown, total: L.stationsTotal },
            decimated: L.decimated,
            alignment: L.alignment,
            cutaway_forced: !!L.cutawayForced,
            decor_hidden: L.decorHidden.slice()
        };
    };

    MotorScene.prototype.setCfdField = function (cfd) {
        var field = cfd && cfd.field;
        var defect = cfdFieldBlockDefect(field);
        if (defect) return cfdReason('bad_field_block', defect);
        var align = cfdFieldAlignment(cfd, this.dims);
        if (!align.ok) return cfdReason(align.code, align.params);
        var walls = cfdWallRadii(field);
        if (!walls) {
            return cfdReason('bad_field_block',
                { missing: 'uniform radial distribution' });
        }
        var edges = cfdCellEdges(field, cfd.grid);
        if (!edges) {
            return cfdReason('bad_field_block',
                { missing: 'monotonic axial stations' });
        }
        // Metrik seçimi: kullanıcının son seçimi yeni yükte de varsa o,
        // yoksa tablodaki ilk mevcut metrik
        var metricId = null;
        if (this._cfdPreferredMetric
            && cfdFieldHasMetric(field, this._cfdPreferredMetric)) {
            metricId = this._cfdPreferredMetric;
        }
        for (var i = 0; !metricId && i < CFD_METRICS.length; i++) {
            if (cfdFieldHasMetric(field, CFD_METRICS[i].id)) {
                metricId = CFD_METRICS[i].id;
            }
        }
        // Eski katman (varsa) sökülür — yeniden kurulum
        this._cfdDisposeLayer();
        // Alan metalin ardında görünmez kalırdı: kesit kipi kapalıysa
        // zorla açılır ve bu dönüşte beyan edilir (cutaway_forced)
        var forced = false;
        if (!this.state.cutaway) {
            forced = true;
            this.setCutaway(true);
        }
        var layer = this._cfdBuildLayer(cfd, field, walls, edges);
        if (!layer) {
            return cfdReason('bad_field_block',
                { missing: 'finite geometry' });
        }
        this._cfdLayer = layer;
        layer.cutawayForced = forced;
        layer.alignment = {
            dz_inlet_mm: align.dz_inlet_mm, dz_exit_mm: align.dz_exit_mm,
            dr_throat_mm: align.dr_throat_mm, dr_exit_mm: align.dr_exit_mm
        };
        var applied = this._cfdApplyMetric(metricId);
        if (!applied.ok) {
            this._cfdDisposeLayer();
            return applied;
        }
        this._syncCfdDecor();
        return this._cfdResult();
    };

    MotorScene.prototype.setCfdMetric = function (id) {
        if (!this._cfdLayer) return cfdReason('no_field', { metric: id });
        var applied = this._cfdApplyMetric(id);
        if (!applied.ok) return applied;
        // K1b: imleç yerinde duruyorsa okuma yeni metriğin dizisinden
        this._probeFollow();
        return this._cfdResult();
    };

    MotorScene.prototype.getCfdField = function () {
        var L = this._cfdLayer;
        if (!L) return null;
        // metrics: YÜKLÜ alanda GERÇEKTEN bulunan büyüklüklerin kimlikleri.
        // Ölçüm cfdFieldHasMetric'in KENDİSİNDEN geçer (_cfdApplyMetric'in
        // 'missing_metric' kapısıyla tek kaynak); süzgecin ikinci bir
        // kopyası yazılmaz. Yayımlanma sebebi: güverte/panel bir metriğin
        // yükte olmadığını ancak KULLANICI tıklayıp red yedikten sonra
        // öğrenebiliyordu — bu liste ile tıklanmadan önce gri yapabilir.
        // Sıra CFD_METRICS tablosunun sırasıdır; liste ÖLÇÜMDÜR, varsayılan
        // ya da tahmin değildir (alan yoksa sözlüğün kendisi null döner).
        var metrics = [];
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (cfdFieldHasMetric(L.field, CFD_METRICS[i].id)) {
                metrics.push(CFD_METRICS[i].id);
            }
        }
        return {
            metric: L.metric,
            metrics: metrics,
            range: { min: L.range.min, max: L.range.max },
            cells: { axial: L.nAx, radial: L.nRad },
            stations: { shown: L.stationsShown, total: L.stationsTotal },
            decimated: L.decimated
        };
    };

    MotorScene.prototype._cfdDisposeLayer = function () {
        var L = this._cfdLayer;
        if (!L) return false;
        this.model.remove(L.group);
        if (L.geometry) L.geometry.dispose();
        if (L.material) L.material.dispose();
        if (L.colorbarEl && L.colorbarEl.parentNode) {
            L.colorbarEl.parentNode.removeChild(L.colorbarEl);
        }
        this._cfdLayer = null;
        // K1b: alan yoksa probe okuması da öğesi de yok
        this._probe = null;
        this._probeRender();
        return true;
    };

    MotorScene.prototype.clearCfdField = function () {
        var had = this._cfdDisposeLayer();
        // Gizlenen süs katmanları geri gelir (örtüşme kalktı)
        if (had) this._syncCfdDecor();
        return had;
    };

    // ------------------------------------------------------------------
    // A1b faz-c-0 · K1b — PROBE, sahne katmanı (saf katman yukarıda:
    // cfdProbeCell / cfdProbeReading / probeLineParts)
    // ------------------------------------------------------------------
    // Nişan (NDC) → raycast; isabetler motor montajı + alan katmanı
    // üstünden, uzaklık sırasıyla. İLK görünür OPAK mesh alanın kendisi
    // değilse (metal önde) okuma YOKTUR: kullanıcının görmediği hücrenin
    // sayısı yazılmaz. Saydam/additive süsler (parıltı), sprite ve
    // çizgiler görüntüyü örtmediği için isabeti de örtmez. Alan gizliyse
    // (patlatma) ya da yoksa okuma yok ve probe öğesi DOM'da YOK
    // (B1 sözleşme: alt şerit KOŞULLU; hakem B2).
    function probeVisible(o, kok) {
        for (var p = o; p; p = p.parent) {
            if (!p.visible) return false;
            if (p === kok) return true;
        }
        return true;
    }

    function probeOpaque(mat) {
        if (Array.isArray(mat)) {
            return !mat.every(function (m) { return !m || m.transparent; });
        }
        return !!mat && mat.visible !== false && !mat.transparent;
    }

    MotorScene.prototype.probeAt = function (x, y) {
        var gecerli = typeof x === 'number' && isFinite(x)
            && typeof y === 'number' && isFinite(y);
        this._probeNdc = gecerli ? { x: x, y: y } : null;
        var rd = null, L = this._cfdLayer;
        if (L && gecerli && this.camera) {
            this.scene.updateMatrixWorld();
            this.camera.updateMatrixWorld();
            var rc = this._probeRaycaster
                || (this._probeRaycaster = new THREE.Raycaster());
            rc.setFromCamera(new THREE.Vector2(x, y), this.camera);
            var hedef = this.assembly ? [this.assembly, L.group] : [L.group];
            var isabet = rc.intersectObjects(hedef, true);
            for (var i = 0; i < isabet.length; i++) {
                var o = isabet[i].object;
                if (!o.isMesh || !probeVisible(o, this.model)) continue;
                if (o === L.mesh) {
                    rd = cfdProbeReading(L, cfdProbeCell(isabet[i].faceIndex,
                        L.nAx, L.nRad));
                    break;
                }
                if (probeOpaque(o.material)) break;   // metal önde
            }
        }
        this._probeSig = this._probeSignature();
        this._probe = rd;
        this._probeRender();
        return this.getProbe();
    };

    // Son okumanın kopyası (makine kanalı; sayı biçimlenmemiş) ya da null.
    MotorScene.prototype.getProbe = function () {
        return this._probe ? JSON.parse(JSON.stringify(this._probe)) : null;
    };

    // Okumayı geçersiz kılan sahne durumu: kamera (yörünge, yakınlaştırma,
    // CAD kamerası), alan görünürlüğü, patlatma oranı, montajın yeniden
    // kurulması (kesit kipi), metrik, alan katmanının kendisi. İmleç
    // kıpırdamasa da biri değişirse okuma aynı nişandan TAZELENİR — bayat hücrenin sayısı ekranda kalmaz.
    MotorScene.prototype._probeSignature = function () {
        var L = this._cfdLayer;
        return { cam: this.camera, lay: L || null,
                 e: this.camera ? this.camera.matrixWorld.elements.slice() : null,
                 vis: !!(L && L.group.visible), exp: this._explodeF,
                 asm: this.assembly || null, metric: L ? L.metric : null };
    };

    MotorScene.prototype._probeFollow = function () {
        if (!this._probeNdc) return;
        var a = this._probeSig, b = this._probeSignature();
        var ayni = !!a && a.cam === b.cam && a.lay === b.lay && a.vis === b.vis
            && a.exp === b.exp && a.asm === b.asm && a.metric === b.metric
            && !!a.e && !!b.e;
        for (var i = 0; ayni && i < 16; i++) ayni = a.e[i] === b.e[i];
        if (!ayni) this.probeAt(this._probeNdc.x, this._probeNdc.y);
    };

    MotorScene.prototype._probeClear = function () {
        this._probeNdc = null;
        this._probe = null;
        this._probeRender();
    };

    // Probe satırı: sahne kabında, colorbar'ın hemen üstünde (theme.css
    // .viz3d-probe). Okuma yoksa öğe KALDIRILIR (gizlenmez).
    MotorScene.prototype._probeRender = function () {
        var rd = this._probe, el = this._probeEl, L = this._cfdLayer;
        if (!rd || !L) {
            if (el && el.parentNode) el.parentNode.removeChild(el);
            this._probeEl = null;
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.className = 'viz3d-probe';
            el.setAttribute('data-viz3d-probe', '1');
            this.container.appendChild(el);
            this._probeEl = el;
        }
        el.innerHTML = probeLineParts(rd).map(function (p) {
            return '<span class="viz3d-probe-' + p.cls + '">'
                + probeHtmlEsc(p.text) + '</span>';
        }).join('<span class="viz3d-probe-sep"> · </span>');
        // Makine kanalı (nokta ondalık; ekran biçiminden bağımsız)
        el.setAttribute('data-probe-metric', rd.metric);
        el.setAttribute('data-probe-cell', rd.cell.axial + ',' + rd.cell.radial);
        el.setAttribute('data-probe-value', String(rd.value));
        var cb = L.colorbarEl;
        var h = (cb && cb.offsetHeight) ? cb.offsetHeight : 0;
        el.style.bottom = (8 + (h ? h + 6 : 0)) + 'px';
    };

    // Fare dinleyicileri (tuval). Sürüklerken (yörünge) hücre imlecin
    // altından kayar: okuma tutulmaz, bırakınca ilk hareket yeniden okur.
    MotorScene.prototype._bindProbe = function () {
        var self = this;
        var cv = this.renderer && this.renderer.domElement;
        if (!cv || !cv.addEventListener) return;
        this._probeMove = function (ev) {
            if (self._disposed) return;
            if (ev.buttons || !self._cfdLayer) {
                if (self._probe || self._probeNdc) self._probeClear();
                return;
            }
            var r = cv.getBoundingClientRect();
            if (!(r.width > 0 && r.height > 0)) return;
            self.probeAt(((ev.clientX - r.left) / r.width) * 2 - 1,
                         -((ev.clientY - r.top) / r.height) * 2 + 1);
        };
        this._probeLeave = function () { self._probeClear(); };
        cv.addEventListener('pointermove', this._probeMove);
        cv.addEventListener('pointerleave', this._probeLeave);
    };

    // Süs katmanı / görünürlük eşitlemesi. Kararlar veriden:
    //  * Patlatılmış görünümde gaz alanı MONTAJLI geometriye bağlıdır —
    //    parçalar ayrılırken alanı yerinde bırakmak yalan hizalama olurdu;
    //    alan gizlenir, patlatma kapanınca geri gelir.
    //  * Kesit kipi kullanıcı tarafından kapatılırsa alan mesh'i SİLİNMEZ
    //    ve görünürlüğü de kapatılmaz: fiziksel olarak metalin içindedir,
    //    opak metal onu KENDİSİ örter (derinlik tamponu) — lüle çıkış
    //    deliğinden görünen kısım gerçekten oradadır, yalan yok.
    //  * Örtüşen additive süsler (cfdOverlayConflicts ölçümü) alan
    //    aktifken gizlenir; ölçüm sonucu decor_hidden ile beyan edilir.
    MotorScene.prototype._syncCfdDecor = function () {
        var L = this._cfdLayer;
        var active = !!L && !this.state.exploded;
        if (L) L.group.visible = !this.state.exploded;
        var conflicts = L
            ? cfdOverlayConflicts(this.dims, L.zSceneLo, L.zSceneHi)
            : { throatFlame: false, glow: false };
        var hidden = [];
        if (active && conflicts.throatFlame) hidden.push('throat_flame');
        if (active && conflicts.glow) hidden.push('glow');
        if (this._throatFlame) {
            this._throatFlame.visible = hidden.indexOf('throat_flame') === -1;
        }
        if (this._glowMesh) {
            this._glowMesh.visible = hidden.indexOf('glow') === -1;
        }
        if (L) L.decorHidden = hidden;
        // K1b: görünürlük/katman değiştiyse probe aynı nişandan tazelenir
        this._probeFollow();
    };

    // Colorbar (DOM katmanı, viewport üstünde). Alan yokken HİÇ
    // oluşmaz — boş/kukla colorbar çizilmez (sahte veri yasağı). Min/max
    // ve tikler VERİDEN; örnekleme beyanı yalnız inceltilmiş yükte.
    // Kimlik: araç çubuğuyla aynı mono font + camgöbeği çerçeve (sayfa
    // kimliği değişmez, yalnız yeni katman).
    //
    // ÖH D36 / sahne-hud (Berke 22 Eyl: "ANSYS gibi, altta renk çubuğu"):
    // çubuk eskiden viewport'un SOL kenarında dikey duruyordu (left:8px,
    // top:50%) ve tik metinleri `cfdTickLabel`tan doğrudan basılıyordu,
    // yani TR oturumda basınç alanı için "44125.7 … 1.99e6" (ölçüldü:
    // raw/OH/D36/sahne-hud/a1/once.json M2_colorbar, 5 noktalı / 0
    // virgüllü sayı). Şimdi sahnenin ALT kenarına yatay yerleşir (min
    // solda, maks sağda, tikler orantılı konumda, başlıkta büyüklük +
    // [birim]), her sayı `decTxt` (I18N.decimalText) kanalından geçer.
    // Ölçek, tik seçimi ve renk durakları DEĞİŞMEZ; yalnız yerleşim ve
    // ayraç. Genişlik 440 px ile sınırlanır; sağ alttaki ısı efsanesi
    // (theme.css .viz-heatlegend: sağ 18 px, çubuk 190 px + 2×14 px
    // dolgu) ile ancak sahne ~690 px'ten genişse çakışmaz. Daha dar
    // sahnede ikisi birlikte açılırsa üst üste biner (ısı haritası ile
    // alan aynı anda açık olabilir; a1/rapor.md devri, Faz C K2).
    // Bekçi: tests/test_d36_sahne_a1.py
    MotorScene.prototype._cfdUpdateColorbar = function () {
        var L = this._cfdLayer;
        if (!L) return;
        if (!L.colorbarEl) {
            var el = document.createElement('div');
            el.setAttribute('data-cfd-colorbar', '1');
            el.style.cssText = [
                'position:absolute', 'left:8px', 'bottom:8px',
                'width:min(440px, calc(100% - 16px))', 'z-index:5',
                'pointer-events:none',
                'font:600 10px "SF Mono","JetBrains Mono",Consolas,monospace',
                'color:#9beaf7', 'background:rgba(4,12,20,0.78)',
                'border:1px solid rgba(0,229,255,0.45)',
                'border-radius:8px', 'padding:6px 10px', 'box-sizing:border-box'
            ].join(';');
            this.container.appendChild(el);
            L.colorbarEl = el;
        }
        var m = null;
        for (var i = 0; i < CFD_METRICS.length; i++) {
            if (CFD_METRICS[i].id === L.metric) m = CFD_METRICS[i];
        }
        var stops = CFD_COLORSCALES[L.metric];
        var grad = [];
        for (i = 0; i < stops.length; i++) {
            grad.push(stops[i][1] + ' ' + (stops[i][0] * 100) + '%');
        }
        var mn = L.range.min, mx = L.range.max;
        var ticks = (mx > mn) ? cfdColorbarTicks(mn, mx, 5) : [];
        var minTxt = decTxt(cfdTickLabel(mn));
        var maxTxt = decTxt(cfdTickLabel(mx));
        // Uç etiketleriyle (min/max) çakışan tikler atlanır. Sabit kesir
        // kuralı (0,12 / 0,88) uzun uç etiketinde yetmiyordu — v3.0.0
        // görsel turu, /solid: '2.5' tiki 0,878'de '2.845754' etiketine
        // bindi (77 px²). Pay artık etiketlerin KARAKTER sayısından ölçülür
        // (10 px eş aralıklı yazı, karakter başına ≤ 6,5 px); içerik
        // genişliği okunamazsa (DOM dışı) eski kesir kuralı geçerlidir.
        var CB_KARAKTER_PX = 6.5, CB_ARALIK_PX = 6;
        var barW = (L.colorbarEl.clientWidth || 0) - 20;   // padding 10+10
        var tickHtml = '';
        for (i = 0; i < ticks.length; i++) {
            var frac = (ticks[i] - mn) / (mx - mn);
            var tickTxt = decTxt(cfdTickLabel(ticks[i]));
            if (barW > 0) {
                var x = frac * barW;
                var yari = tickTxt.length * CB_KARAKTER_PX / 2;
                if (x - yari < minTxt.length * CB_KARAKTER_PX + CB_ARALIK_PX
                        || x + yari > barW - maxTxt.length * CB_KARAKTER_PX
                            - CB_ARALIK_PX) continue;
            } else if (frac < 0.12 || frac > 0.88) {
                continue;
            }
            tickHtml += '<span style="position:absolute;top:0;left:'
                + (frac * 100) + '%;transform:translateX(-50%);color:#7fd4e2">'
                + tickTxt + '</span>';
        }
        var label = T(m.labelKey, m.labelFallback)
            + (m.unit ? ' [' + m.unit + ']' : '');
        var decl = [];
        if (L.decimated) {
            // ÖH D32 · OH-D31-18 — çıplak amber tokene bağlandı
            // (CSS dizesi olduğu için `var()` burada ÇÖZÜLÜR; değer aynı).
            decl.push('<span style="color:var(--hd-amber-source, #ffb347)">'
                + cfdFormatTemplate(
                    T('viz3d.cfd.stations',
                      '{shown} / {total} axial stations'),
                    { shown: L.stationsShown, total: L.stationsTotal })
                + '</span>');
        }
        decl.push('<span style="color:#8a93a0">'
            + T('viz3d.cfd.flatNote', 'cell-centred, flat tiles') + '</span>');
        L.colorbarEl.setAttribute('data-cfd-metric', String(L.metric));
        L.colorbarEl.innerHTML =
            '<div style="display:flex;justify-content:space-between;gap:12px;'
            + 'margin-bottom:4px;letter-spacing:0.4px">'
            + '<span data-cfd-colorbar-label="1">' + label + '</span>'
            + '<span>' + decl.join(' · ') + '</span></div>'
            + '<div style="height:12px;border-radius:3px;'
            + 'border:1px solid rgba(0,229,255,0.45);'
            + 'background:linear-gradient(to right,' + grad.join(',') + ')">'
            + '</div>'
            + '<div style="position:relative;height:14px;margin-top:3px">'
            + '<span data-cfd-colorbar-min="1" '
            + 'style="position:absolute;top:0;left:0;color:#e8f9ff">'
            + minTxt + '</span>'
            + tickHtml
            + '<span data-cfd-colorbar-max="1" '
            + 'style="position:absolute;top:0;right:0;color:#e8f9ff">'
            + maxTxt + '</span>'
            + '</div>';
    };

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
        // a2: süre yoksa zaman ekseni yok, saat 0'da kalır
        this.state.time = (this.dims.burnTime === null) ? 0
            : clamp(this.state.time, 0, this.dims.burnTime);
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
        // CFD alan katmanı ESKİ geometriye/kontura göre kurulmuştu:
        // yeni boyutlara karşı yeniden doğrulanıp yeniden kurulur; yeni
        // kontur artık hizalanmıyorsa alan DÜŞER (setCfdField reddeder,
        // eski katman zaten söküldü) — yanlış hizalı alan bırakılmaz,
        // panel isterse yeni /api/cfd/nozzle koşusuyla geri yükler.
        if (this._cfdLayer) {
            var cfdSaved = this._cfdLayer.cfd;
            this._cfdDisposeLayer();
            this._syncCfdDecor();
            this.setCfdField(cfdSaved);
        }
    };
    MotorScene.prototype.setLabels = function (on) {
        this.state.labels = !!on;
        if (this._labelGroup) this._labelGroup.visible = this.state.labels;
    };
    MotorScene.prototype.setPlume = function (on) { this.state.plume = !!on; };
    MotorScene.prototype.setExploded = function (on) {
        this.state.exploded = !!on;
        // Gaz alanı montajlı geometriye bağlıdır — patlatmada gizlenir
        if (this._cfdLayer) this._syncCfdDecor();
    };
    MotorScene.prototype.setAutoRotate = function (on) { this.state.autoRotate = !!on; };
    MotorScene.prototype.play = function () {
        // ÖH D36 / onemli2-sivi a2: süre yoksa oynatılacak zaman ekseni yok
        if (this.dims.burnTime === null) { this.state.playing = false; return; }
        if (this.state.time >= this.dims.burnTime - 1e-3) this.state.time = 0;
        this.state.playing = true;
    };
    MotorScene.prototype.pause = function () { this.state.playing = false; };
    MotorScene.prototype.setTime = function (t) {
        this.state.time = (this.dims.burnTime === null) ? 0
            : clamp(t, 0, this.dims.burnTime);
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
            // Gölge dokusu da kalite kipine bağlıdır (B7 kalem 5): perf'te
            // mapSizePerf, HQ'da mapSizeHigh — bias'lar teksel boyundan
            // yeniden türetilir (_buildMotor'daki _applyExplode zaten çağırır,
            // burada kip değişimi TEK BAŞINA da yeterli olsun diye açıkça).
            this._applyShadowFit();
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
                        envMapIntensity: m.envMapIntensity,
                        // clearcoat yalnız MeshPhysicalMaterial'da tanımlı
                        // (kasa); nötr stüdyoda kaplama parlaması kapanır
                        clearcoat: m.clearcoat
                    };
                }
                if (m.metalness !== undefined) m.metalness = Math.min(m.metalness, 0.15);
                if (m.roughness !== undefined) m.roughness = Math.max(m.roughness, 0.75);
                if (m.envMapIntensity !== undefined) m.envMapIntensity = 0.15;
                if (m.clearcoat !== undefined) m.clearcoat = 0;
            } else if (m.userData._cadOrig !== undefined) {
                var o = m.userData._cadOrig;
                if (o.metalness !== undefined) m.metalness = o.metalness;
                if (o.roughness !== undefined) m.roughness = o.roughness;
                if (o.envMapIntensity !== undefined) m.envMapIntensity = o.envMapIntensity;
                if (o.clearcoat !== undefined) m.clearcoat = o.clearcoat;
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
        // ÖH D24 / P11B1-07 — CAD görünüş düğmeleri de oturum dilinde.
        // Etiket ve ipucu aynı anahtardan gelir: ekranda iki dil olmaz.
        [['front', 'viz3d.cad.front', 'FRONT'],
         ['top', 'viz3d.cad.top', 'TOP'],
         ['side', 'viz3d.cad.side', 'SIDE'],
         ['iso', 'viz3d.cad.iso', 'ISO']]
            .forEach(function (pr) {
                var etiket = T(pr[1], pr[2]);
                var b = mkBtn(etiket,
                    T('viz3d.cad.orthoTip', 'Orthographic view:') + ' '
                    + etiket);
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
        // V301/K-C1 (KT-24): görünürlük ve uyandırma dinleyicileri bırakılır.
        if (this._io) { this._io.disconnect(); this._io = null; }
        if (this._visHandler) {
            document.removeEventListener('visibilitychange', this._visHandler);
            this._visHandler = null;
        }
        if (this._wakeHandler) {
            document.removeEventListener('hrma:langchange', this._wakeHandler);
            var _el = this.renderer && this.renderer.domElement;
            if (_el) {
                var _h = this._wakeHandler;
                ['pointerdown', 'pointermove', 'wheel', 'keydown', 'touchstart']
                    .forEach(function (ad) { _el.removeEventListener(ad, _h); });
            }
            this._wakeHandler = null;
        }
        // CFD alan katmanı: geometri + malzeme + colorbar DOM'u bırakılır
        // (colorbar sahne grafiğinde değildir, traverse onu görmez)
        this._cfdDisposeLayer();
        if (this._raf) cancelAnimationFrame(this._raf);
        if (this._ro) this._ro.disconnect();
        if (this._langHandler) {
            document.removeEventListener('hrma:langchange', this._langHandler);
            this._langHandler = null;
        }
        // K1b: probe dinleyicileri (öğe yukarıda katman sökümüyle gitti)
        if (this._probeMove && this.renderer && this.renderer.domElement) {
            this.renderer.domElement.removeEventListener('pointermove',
                this._probeMove);
            this.renderer.domElement.removeEventListener('pointerleave',
                this._probeLeave);
            this._probeMove = this._probeLeave = null;
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

    // V301/K-C1 (KT-24): sahnenin GENEL yöntemleri (araç çubuğu, deste, dış
    // çağıranlar) durum değiştirir; her çağrıdan sonra çizim döngüsü
    // uyandırılır. Salt okuyucular (get*, snapshot) ve dispose sarılmaz —
    // her kare çağrılan bir okuyucu döngüyü sonsuza dek uyanık tutardı.
    Object.keys(MotorScene.prototype).forEach(function (ad) {
        if (ad.charAt(0) === '_' || ad === 'dispose' || ad === 'snapshot'
                || ad.indexOf('get') === 0) {
            return;
        }
        var asil = MotorScene.prototype[ad];
        if (typeof asil !== 'function') return;
        MotorScene.prototype[ad] = function () {
            var sonuc = asil.apply(this, arguments);
            this._kick();
            return sonuc;
        };
    });

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
            // FAIL-CLOSED KAPISI (ÖH D27 / P11B1-09 + OH-D26-02):
            // birincil ölçü eksikse sahne KURULMAZ; eksik alanlar adıyla
            // ekrana yazılır ve red bloğu saklanır. Uydurma yedekle
            // çizilen motor kullanıcının tasarımı değildir.
            var eksik = missingPrimaryDims(motorData);
            if (eksik.length) {
                _dimsLastReject = { code: DIMS_REJECT_CODE,
                                    missing: eksik };
                renderDimsRejection(el, eksik);
                return null;
            }
            _dimsLastReject = null;
            viz = new MotorScene(el, motorData, hooks);
            return viz;
        },
        // Tasarım modu: mevcut sahneyi yeni geometriyle yerinde güncelle
        update: function (motorData) {
            if (!viz) return null;
            // Canlı güncelleme de kapıdan geçer: yeni sözlükte ölçü
            // yoksa ESKİ sahne bırakılmaz (bırakmak, ekrandaki motorun
            // yeni tasarım olduğu yalanını sürdürürdü) — sahne sökülür
            // ve red adıyla yazılır.
            var eksik = missingPrimaryDims(motorData);
            if (eksik.length) {
                var kap = viz.container;
                viz.dispose();
                viz = null;
                _dimsLastReject = { code: DIMS_REJECT_CODE,
                                    missing: eksik };
                if (kap) {
                    kap.innerHTML = '';
                    renderDimsRejection(kap, eksik);
                }
                return null;
            }
            _dimsLastReject = null;
            viz.update(motorData);
            return viz;
        },
        // Son birincil-ölçü reddinin gerekçe bloğu (yoksa null).
        getDimsReject: function () { return _dimsLastReject; },
        // Bir motor sözlüğünün sahne için yeterli olup olmadığı: eksik
        // birincil ölçülerin adları (boş dizi = çizilebilir). Sayfalar
        // kendi kararlarını AYNI kuralla verebilsin diye dışa açık.
        missingPrimaryDims: function (motorData) {
            return missingPrimaryDims(motorData);
        },
        // ÖH D31 · OH-D27-13 — son sahnenin varsayım ölçüleri (künyeli).
        // Sayfalar rozeti kendi paneline basabilsin diye dışa açık.
        assumedDimensions: function () { return assumedDimensionList(); },
        renderAssumedDimBadge: function (id) {
            return renderAssumedDimBadge(id);
        },
        ASSUMED_DIM_NO_BASIS: ASSUMED_DIM_NO_BASIS,
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
        // CFD alan katmanı (parti 30 — A2): /api/cfd/nozzle data.cfd
        // sözlüğü AYNEN verilir; sahne yoksa (mount edilmedi / WebGL yok)
        // sözleşmedeki 'no_scene' reddi döner
        // ÖH D24 / P11B1-08 — RED SESSİZ KAYBOLMAZ.
        // ÖLÇÜLDÜ (a3/once.json): sahne bir alanı reddettiğinde
        // (`no_solver_contour`, `contour_mismatch`, `bad_field_block`)
        // `getCfdField()` null KALIR; güvertenin durum imzası
        // (`cfdStateSig(null) === ''`) kurulumdaki imzayla aynı olduğu
        // için `cfdSyncFromScene` hiç yazmaz ve ekranda "CFD analizini
        // koştur ve 'Show in the 3D scene'e bas" cümlesi asılı kalır —
        // yani kullanıcıdan AZ ÖNCE YAPTIĞI ŞEY yeniden isteniyordu.
        // Red bloğu artık burada saklanır: bir ÖLÇÜMDÜR (sahnenin kendi
        // sözleşme kodu + parametreleri), tahmin değildir. Başarılı bir
        // yükleme ya da alanın kaldırılması onu temizler.
        setCfdField: function (cfd) {
            var res = viz ? viz.setCfdField(cfd) : cfdReason('no_scene', {});
            _cfdLastReject = (res && res.ok === false && res.reason)
                ? res.reason : null;
            return res;
        },
        clearCfdField: function () {
            _cfdLastReject = null;
            return viz ? viz.clearCfdField() : false;
        },
        // Son reddin gerekçe bloğu (yoksa null). Güverte bunu okuyup
        // durum satırına GERÇEK sebebi yazar.
        getCfdReject: function () { return _cfdLastReject; },
        setCfdMetric: function (id) {
            return viz ? viz.setCfdMetric(id)
                : cfdReason('no_scene', { metric: id });
        },
        getCfdField: function () { return viz ? viz.getCfdField() : null; },
        // A1b faz-c-0 · K1b — son probe okuması (makine kanalı) ya da null
        getProbe: function () { return viz ? viz.getProbe() : null; },
        // Metrik + renk skalası tabloları dışa açık: 2B panel aynı
        // tablodan beslenir (iki görünüm aynı büyüklüğe aynı renk)
        CFD_METRICS: CFD_METRICS,
        CFD_COLORSCALES: CFD_COLORSCALES,
        setQuality: function (mode) { return viz ? viz.setQuality(mode) : null; },
        // Görünür karenin PNG data-URL'i (indirme butonları için)
        snapshot: function () { return viz ? viz.snapshot() : null; },
        get: function () { return viz; },
        dispose: function () { if (viz) { viz.dispose(); viz = null; } }
    };
})();
