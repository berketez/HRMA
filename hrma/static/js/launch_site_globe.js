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
 *  - Yer izi (ground track), çözücünün ENU serisinin teğet-düzlem jeodezik
 *    izdüşümüdür (enu_to_geodetic ile birebir). Dünya dönüşü/Coriolis'in
 *    modellenme durumu TEK yetkili kaynak launch_site.NOT_MODELLED'de beyan
 *    edilir; küre kendiliğinden bir modelleme iddiası ÜRETMEZ, o beyana uyar.
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

    /* ÖH D22 / OH-D18-10 — UÇUŞ İRTİFASININ DATUMU (tek tanım).
       `setFlightPath` eskiden `series.altitude`ın SAHA ÜSTÜ (AGL) olduğunu
       VARSAYIYORDU. Varsayım bugün doğru — çözücü aynı sözleşmeyi kendisi
       yayımlıyor (six_dof_trajectory.py: `altitude_datum` /
       `apogee_datum` = 'above_launch_site') — ama kod onu OKUMUYORDU;
       datum bir gün değişirse çizim sessizce h0 kadar kayardı. Artık dizi
       datumu okunur, TANINMAYAN bir datum FAIL-CLOSED reddedilir (yol
       çizilmez, hata kancası ateşlenir) ve seçilen datum `_flight`e yazılır.
       Sayı DEĞİŞMEZ: bugünkü tek üretici 'above_launch_site' gönderir ya da
       hiç göndermez; ikisi de aynı yolu izler. */
    var ALT_DATUM_AGL = 'above_launch_site';
    var ALT_DATUM_MSL = 'mean_sea_level';
    var ALT_DATUM_BILINEN = [ALT_DATUM_AGL, ALT_DATUM_MSL];
    /* Alan yoksa uygulanan datum: üretici sözleşmesinin kendisi. Sessiz bir
       yedek DEĞİL — adı ve kaynağı burada yazılıdır, `_flight.altSeriesDatum`
       ile dışarı da verilir. */
    var ALT_DATUM_VARSAYILAN = ALT_DATUM_AGL;
    // WGS84 (launch_site.py ile aynı türetilmiş sabitler)
    var WGS84_A = 6378137.0;
    var WGS84_E2 = 6.69437999014e-3;

    // Kamera mesafe sınırları. DİKKAT: OrbitControls.min/maxDistance HEDEFTEN
    // (target) ölçülür, Dünya merkezinden DEĞİL. Yerel görünümde hedef yüzeydedir;
    // bu yüzden hedefe yakın zoom için min HEDEF mesafesi KÜÇÜK olmalı. Kürenin
    // içine dalmayı ayrı bir YÜZEY KİLİDİ (SURFACE_MIN_LEN) engeller.
    // Eski taban 0,4 birim × 63.710 m = 25.484 m idi (eski yorum "~2.5 km"
    // diyordu, 10 kat yanlıştı; tasarım harita-detay §1). V307/FS-HARİTA: alt
    // sınırın kuralı aşağıda, dinamik near sabitlerinin ardında
    // (KAMERA_MIN_MESAFE).
    var CTRL_MAX_TARGET = GLOBE_R * 6.0;     // en fazla uzaklaşma

    /* ÖH harita-detay K2 — DİNAMİK NEAR DÜZLEMİ (tasarım §3.2).
       Eskiden near sabit 0,01 birimdi (637 m) ve en yakın kamera yüzeyden
       ~19-25 km uzakta duruyordu: derinlik çözünürlüğünün çoğu boş kalıyor,
       tüm-Dünya görünümünde (d ~ 280 birim) Δz ~ d²/(near·2^24) ~ 0,47 birim
       = ~30 km oluyordu; yüzeye yakın çizgiler küreyle çatışırdı. Artık her
       karede near = clamp(0,3 · min(irtifa, hedef mesafesi), 1e-4, 1) birim.
       Tasarımın formülü yalnız irtifayı kullanıyordu; hedef mesafesi EKLENDİ,
       çünkü yerel görünümde hedef uçuş yolunun ortasıdır (yüzeyin üstünde) ve
       yalnız irtifaya bağlı near yola yakın kamerada yolu kırpabilirdi. */
    var NEAR_ORANI = 0.3;
    var NEAR_MIN = 1e-4;
    var NEAR_MAX = 1.0;

    /* V307 / FS-HARİTA (9 Kas 2026) — YAKIN BAKIŞ SINIRI (ölçülü kural).
       Eski değerler: hedefe 25,5 km (0,004R), yüzey kilidi 19,1 km (1,003R),
       uçuşlu 'Sahaya yakınlaş' tabanı 191 km. Ölçülen sonuç (FS-UÇUŞ,
       FS-İZLEME bildirimleri): km ölçekli bir uçuş ve 57 m'lik bir uçuş
       yakın görünümde nokta kalıyordu; fırlatma noktası birkaç yüz metreden
       izlenemiyordu. KURAL: kamera, dinamik near düzleminin kendi kuralının
       (near = NEAR_ORANI · mesafe) tabana (NEAR_MIN) çarpmadığı en küçük
       mesafeye kadar yaklaşabilir: NEAR_MIN / NEAR_ORANI = 3,33e-4 birim =
       21,2 m. Bu sınırın altında near tabana kırpılır ve kameraya near'dan
       yakın geometri kesilmeye başlar; üstünde near her zaman mesafenin
       %30'udur. Aynı sayı hem hedef mesafesi (OrbitControls minDistance)
       hem yüzey kilidi (küre yüzeyinden irtifa) için kullanılır. Küre
       arazi taşımaz (yükselti modeli yok); kilit küre yüzeyine göredir ve
       o yakınlıkta çizilen en kaba karonun kiriş sarkması (z7 parça açısı,
       19 m) yüzeyin ALTINDADIR, kameranın önünde değil. Bu yakınlıkta en
       ince doku (Landsat ~30 m) büyütülür; büyütme notu bunu söyler. */
    var KAMERA_MIN_MESAFE = NEAR_MIN / NEAR_ORANI;            // birim (21,2 m)
    var CTRL_MIN_TARGET = KAMERA_MIN_MESAFE;                   // hedefe ~21 m'ye kadar yaklaş
    var SURFACE_MIN_LEN = GLOBE_R + KAMERA_MIN_MESAFE;         // yüzey kilidi (~21 m irtifa)

    /* Web-mercator eşdeğer zoom: z_web = log2(Z_WEB_Z0_MPP / m/px).
       156.543,03 m/px = 256 px karolu web haritasının z0'da ekvator çözünürlüğü
       (2·π·6.378.137 m / 256). Natural Earth'ün `min_zoom` alanı bu ölçekle
       anlamlıdır (tasarım §1). TEK TANIM: kare kancası yükündeki `zWeb`
       buradan hesaplanır; vektör ve etiket modülleri kendi kopyasını tutmaz. */
    var Z_WEB_Z0_MPP = 156543.03;
    // Yakın zoomda "doku detayı yok" notunun tetiklendiği kamera yüksekliği [m].
    // DİKKAT: bu YALNIZ uyarı notunun eşiğidir; karo yamalarının açıldığı eşik
    // ayrıdır (TILE_ACTIVE_ALT_M) ve ikisi bilerek farklı büyüklüktedir.
    var TEXTURE_NOTE_ALT_M = 400000.0;
    // Karo yamalarının (GIBS patch) etkinleştiği kamera yüksekliği [m].
    // Uyarı notu eşiğiyle AYNI SAYI DEĞİL: "Fly this site" kamerayı ~466 km'ye
    // koyuyor; kapı 400 km olduğunda hiçbir karo istenmiyordu (ölçüldü, istek
    // sayısı 0). Kapı 1500 km'ye çekildi -> tipik saha görünümünde yama açılır.
    var TILE_ACTIVE_ALT_M = 1500000.0;

    // "Tüm Dünya" mesafesi: küre en dar eksene sığmalı. Dikey yarı-FOV sabit,
    // yatay yarı-FOV en-boy oranından türetilir; dar olan hangisiyse küre ona
    // göre çerçevelenir (1.25 = nefes payı). Eski sabit 2.6R dikeyde %19 kırpıyordu
    // (asin(100/260)=22.62° > 19.00° dikey yarı-FOV).
    function globalViewDist(camera) {
        var v = deg2rad(camera.fov) / 2;
        var h = Math.atan(Math.tan(v) * camera.aspect);
        var m = Math.min(v, h);
        var d = GLOBE_R / Math.sin(m) * 1.25;
        // Çok dar/uzun pencerede mesafe OrbitControls üst sınırını aşmasın.
        // BİLİNÇLİ SINIR: tavan CTRL_MAX_TARGET*0.98 = 588 birim. Kürenin oraya
        // sığması için asin(100/588) = 9,79° < yarı-FOV gerekir; yatay yarı-FOV
        // atan(tan19°·en-boy) olduğundan koşul en-boy > 0,501'dir. Yani en-boy
        // ~0,50'nin altındaki (boyu eninin iki katından fazla) pencerelerde küre
        // yine kırpılır — masaüstünde pratikte görülmeyen bir durum, kamerayı
        // OrbitControls sınırının dışına taşımaya yeğlendi.
        return Math.min(d, CTRL_MAX_TARGET * 0.98);
    }

    // ---- GIBS uydu karo yaması (patch mesh) sabitleri ----
    // Yakın zoomda taban Blue Marble (~9 km) yerine NASA GIBS karoları (~500 m)
    // her karonun KENDİ yama geometrisine bindirilir. Karolar backend
    // /api/tile üzerinden gelir (hrma/analysis/tile_cache.py); istemci yalnız
    // hangi karonun gerektiğini hesaplar, URL/host kurmaz.
    var TILE_LAYER = 'bluemarble';        // varsayılan statik katman (tile_cache allowlist)
    // ÖH D21 / P12aB4-19 — KATMAN -> ATIF ANAHTARI. Atıf METNİ burada
    // YAZILMAZ (o i18n sözlüğünün tek kaynağıdır ve çevrilir); burada yalnız
    // HANGİ katmanın HANGİ künyeye ait olduğu durur. Katman değişip karşılığı
    // burada tanımlı değilse atıf HİÇ basılmaz (fail-closed: başka katmanın
    // künyesini göstermektense hiç göstermemek).
    var TILE_ATTRIBUTION_KEY = { bluemarble: 'site.tileAttribution',
                                 landsat_weld: 'site.tileDetailAttribution',
                                 bm_local: 'site.tilePackagedAttribution',
                                 pack_detail: 'site.mapPackAttribution' };
    /* V307 / FS-HARİTA (9 Kas 2026) — YAKIN ZOOM AYRINTI KATMANI.
       ÖLÇÜLDÜ (rıza açık, 'Sahaya yakınlaş' kipi, İstanbul 25 km): en ince
       karo 'bluemarble' z7 idi (~489 m/px) ve ekran ~21 m/px iken 23 kat
       büyütülüyordu; şehir/kıyı/rampa ayrıntısı yoktu. 'landsat_weld'
       (NASA GIBS 31.25m ağacı, Landsat WELD gerçek renk, 2000 yıllık
       bileşkesi, ~30 m/px z11) YALNIZ z > TILE_MAX_ZOOM (bluemarble tavanı)
       iken istenir. Varlığı ve tavanı SUNUCUDAN okunur
       (/api/tile/cache/status 'layers.layers.landsat_weld': kaynak 'gibs',
       ui_offered, tamsayı max_zoom > TILE_MAX_ZOOM ve o düzeyin matris
       geometrisi yayımlanmış). Okunamazsa katman kullanılmaz (fail-closed),
       tavan eskisi gibi z7 kalır. Ağ kapısı (K5a) aynen geçerlidir. */
    var TILE_LAYER_DETAIL = 'landsat_weld';
    var TILE_SOURCE_GIBS = 'gibs';
    var _detayTavan = null;             // sunucudan (yoksa null)
    /* harita-detay K4 (F2; tasarım §3.4) — PAKETLİ ÇEVRİMDIŞI KATMAN.
       NASA Blue Marble NG (Aralık 2004) z0-z5 WebP piramidi uygulamayla
       gelir; sunucu onu ağa çıkmadan verir (tile_cache 'bm_local').
       KAYNAK SIRASI (yalnız var olan çizilir, ince olan üstte):
         1) GIBS 'bluemarble' z <= 7 — YALNIZ istenen z paketli tavanın
            üstündeyse istenir (z <= tavan iken GIBS isteği atılmaz: aynı
            2004 verisinin kopyası için dışarı istek gereksizdir); ağ
            anahtarı (K5a) kapalıyken sunucu yalnız önbellekteki karoyu verir;
         2) paketli 'bm_local' z <= tavan — HER ZAMAN, ağsız;
         3) taban küre 4096.
       Paketli katmanın tavanı (max_zoom) SUNUCUDAN okunur
       (/api/tile/cache/status 'layers.packaged'); okunamazsa paketli katman
       kullanılmaz (fail-closed) ve eski davranış (yalnız GIBS) sürer. */
    var TILE_LAYER_PACKAGED = 'bm_local';
    var TILE_SOURCE_PACKAGED = 'packaged';
    var _paketliTavan = null;           // sunucudan (yoksa null)
    /* V307 / FS-HARİTA-KÜRE (16 Kas 2026) — İNDİRİLEN HARİTA PAKETİ KATMANI.
       Kullanıcının onayıyla indirdiği OpenStreetMap paketi (FS-HARİTA-VERİ
       faz 2, Parça S) sunucuda SAYDAM rastere çizilir (yol, bina, su, kıyı,
       arazi kullanımı) ve zemin dokusunun (bm_local / rızalı Landsat)
       ÜSTÜNE biner. Ağa çıkmaz. Varlığı ve tavanı SUNUCUDAN okunur
       (/api/tile/cache/status 'layers.packs.pack_detail': kaynak 'pack',
       ui_offered, tamsayı max_zoom > TILE_MAX_ZOOM ve o düzeyin matris
       geometrisi yayımlanmış); okunamazsa katman hiç istenmez (fail-closed).
       Yalnız KURULU bir paketin kutusuyla kesişen karo istenir; bindirme
       karonun o kutuyla kesişen parçasına kırpılır (paket kapsamı dışında
       bugünkü görünüm aynen). Kurulu paket listesi launch_site_map_packs.js
       deposundan okunur (LaunchSiteMapPacks.kuruluKutular). */
    var TILE_LAYER_PACK = 'pack_detail';
    var TILE_SOURCE_PACK = 'pack';
    var _paketTavan = null;             // sunucudan (yoksa null)
    // EBEVEYN YEDEĞİ: z düzeyindeki karo henüz çizilmemişse onu kapsayan
    // daha kaba karo (aynı katmanda) LRU'da tutulur ve çizilmeye devam eder;
    // zoom değişince taban dokuya düşüp geri gelen yanıp sönme biter.
    // GIBS EPSG:4326 matrisi z <= 2'de düzensizdir (z0 2x1, z1 3x2): ebeveyn
    // ilişkisi (x/2, y/2) yalnız ebeveyn z >= 3 iken geçerlidir.
    var TILE_PARENT_MIN_ZOOM = 3;
    // Doku büyütme notu (tasarım §4.1-4): ekran merkezindeki en ince çizilen
    // dokunun m/px'i ekran m/px'inin bu katından kabaysa not açılır.
    var TEXTURE_MAG_RATIO = 2;
    // ÖH D21 / P12aB4-26 — YORUM DAVRANIŞI YANLIŞ ANLATIYORDU. Eski satır
    // "z<4: taban yeterli, patch yüklenmez" diyordu; oysa kod ATLAMA değil
    // KIRPMA yapıyor (`z = clamp(z, TILE_MIN_ZOOM, TILE_MAX_ZOOM)`), yani
    // hesaplanan z 4'ün altına düşerse 4'e YUKARI çekilip karo yine isteniyor.
    // ÖLÇÜLDÜ: kapının içinde (kamera < TILE_ACTIVE_ALT_M = 1.500 km) 600 px
    // yükseklikte hesaplanan en küçük z zaten 5'tir (kapı sınırında
    // 2.265 m/px -> z = round(log2(TILE_Z0_MPP/mpx)) = 5), yani bu alt sınır
    // bugün hiç bağlamıyor. Sabit, kapı gevşetilirse istenecek en KABA karoyu
    // adlandıran alt kırpma sınırıdır.
    var TILE_MIN_ZOOM = 4;                // alt kırpma sınırı (atlama DEĞİL)
    var TILE_MAX_ZOOM = 7;                // bluemarble z0-7 (backend max_zoom ile aynı)
    var TILE_PATCH_R = 2;                 // merkez etrafı (2R+1)² blok (tipik 5×5)
    var TILE_PATCH_R_MAX = 3;             // hard cap → en fazla 7×7
    var TILE_PATCH_SEG = 8;              // yama S×S vertex (küresel eğrilik için)
    // ÖH D17 / P12aB4-03 + P12aB4-06: karo kabuğunun z-fighting'i GEOMETRİK
    // kaydırmayla çözülüyordu (GLOBE_R * 1.0004 = taban üstü 2.548,4 m). O
    // kaydırma fiziksel değil salt bir çizim hilesiydi ve iki ürün kusuru
    // doğuruyordu: (1) yüzeye çapalı işaretçiler (saha iğnesi 2.485 m, olay
    // noktası 1.433 m) kabuğun ALTINDA kalıp karolar açıkken görünmüyordu;
    // (2) saha seçim ışını TABAN küreye çarptığı için kullanıcının gördüğü
    // karo yüzeyi ile seçilen enlem/boylam arasında Δr·tan(i) = 2.637 m
    // (46° eğik bakışta) sabit kayma vardı. Kabuk artık taban küreyle AYNI
    // yarıçapta; ayrım derinlik yanlılığıyla (polygonOffset) yapılıyor, yani
    // sahnede sahte irtifa kalmıyor. Sınırlar (1.001) ve yer izi (1.0015)
    // zaten üstte olduğu için etkilenmez.
    var TILE_RADIUS = GLOBE_R;           // taban küreyle çakışık; ayrım polygonOffset ile
    var TILE_DEPTH_BIAS = -1;            // polygonOffsetFactor/Units: karo tabanın ÖNÜNE
    /* V307 / FS-HARİTA-KÜRE (16 Kas 2026) — R7 DERİNLİK ÇAKIŞMASI (ölçülen kök).
       ÖLÇÜLDÜ (kanıt docs/scofield/raw/OH/V307/fs-harita-kure/olcum/once_r7;
       sentetik karolar: Landsat z9 KIRMIZI ebeveyn, z11 YEŞİL çocuk, Sinop,
       rıza kapalı, karolar yalıtılmış önbellekten): 20 km'de z11 çocukların
       kapladığı bölgede ebeveyn 3.619 pikselde (%0,73) ÜSTE çıkıyordu (çokgen
       yama + dikey noktalı dikiş). İki kök:
         (1) Karo köşeleri DÜNYA koordinatında float32 tutuluyordu: GLOBE_R =
             100 birimde float32 adımı 2^-17 ≈ 7,6e-6 birim ≈ 0,49 m. z12'de
             ebeveyn yüzünün küreden sarkması ~2 cm iken köşe gürültüsü
             ±0,25 m: ebeveyn ile çocuk derinlikte rastgele yarışıyordu.
         (2) Gürültü olmasa da ebeveyn köşelerinin çevresinde ebeveyn yüzü
             küreye DEĞER, çocuğun kendi yüzü ise biraz altındadır; ikisi aynı
             polygonOffsetUnits ile yazıldığı için orada ebeveyn kazanıyordu.
       ONARIM: (1) karo köşeleri karonun KENDİ MERKEZİNE göre kurulur, merkez
       nesnenin konumudur (Mesh.position; matris çarpımı JS'te float64);
       köşeler artık metrenin altında hassas. (2) Zemin karoları İNCEDEN
       KABAYA çizilir ve stencil biti yazar; daha kaba bir karo, daha ince
       bir karonun çizdiği pikseli YAZAMAZ (derinlik yarışına bırakılmaz).
       Paket bindirmesi kendi bitini kullanır (aynı kural, kendi içinde).
       Bit 0: zemin karosu çizildi. Bit 1: paket bindirmesi çizildi. */
    var STENCIL_ZEMIN = 1;
    var STENCIL_PAKET = 2;
    /* Çizim sırası (renderOrder). Zemin karoları opaktır ve sahnedeki diğer
       opak nesnelerden (taban küre, iğne, roket, olay noktaları: renderOrder
       0) SONRA, inceden kabaya çizilir: ZEMIN_RO_TABANI - z (z <= 99 her
       düzey için pozitif). Paket bindirmesi saydam geçiştedir ve gökyüzü
       yıldızlarından (-1) sonra, bütün çizgi/halka/izlerden (>= 0) ÖNCE
       çizilir: -0,5 - z/1000 (yine inceden kabaya). */
    var ZEMIN_RO_TABANI = 100;
    var PAKET_RO_TABANI = -0.5;
    // GPU bellek: üstündeki en eski mesh THREE dispose edilir. ÖH harita-detay
    // K2 (tasarım §3.4): 128 karo × 512²×4 B×4/3 (mipmap) = ~179 MB tavandı;
    // 64 × 1,40 MB = ~90 MB. 5×5 yama + iki düzeylik ebeveyn yedeği için
    // 25 + 25 + 7 = ~57 karo yeter.
    var TILE_LRU_MAX = 64;
    /* V307/FS-HARİTA-KÜRE: paket bindirmesinin AYRI tavanı. Zemin tavanını
       paylaşsaydı 5×5 paket yaması + 5×5 Landsat + 5×5 paketli (75) 64'ü
       aşar, kullanılan karolar her turda budanıp yeniden istenirdi. Zeminle
       aynı akıl yürütme: 5×5 yama + iki düzeylik ebeveyn yedeği = 25 + 7. */
    var TILE_LRU_MAX_PAKET = 32;
    var TILE_UPDATE_MS = 250;           // patch güncelleme kısması (her karede değil)
    // Negatif önbellek (ÖH D17 / P12aB4-04): başarısız karo hemen unutulmaz;
    // üstel geri çekilmeyle beklenir, TILE_FAIL_MAX denemeden sonra hiç
    // istenmez. 2s→4s→8s→16s→32s; en kötü hâlde karo başına 5 istek.
    var TILE_FAIL_BACKOFF_MS = 2000;
    var TILE_FAIL_MAX = 5;
    var TILE_Z0_MPP = 62617.5;          // ekvator m/px @ z0 (0.5625°/px · 111319.49 m/°)

    /* ÖH D26 / defter P5B4-30 — KARO MATRİS GEOMETRİSİ ARTIK SUNUCUDAN.
       ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): burada
       ``tileSpanDeg(z) = 288.0/Math.pow(2,z)`` ve
       ``mw = Math.ceil(360.0/span), mh = Math.ceil(180.0/span)``
       duruyordu; tile_cache.py aynı sayıyı TAMSAYI ceil ile üretiyordu.
       Sayısal ayrışma z0-z7'de YOKTU (ölçüldü) — kusur sonuçta değil
       SAHİPLİKTE: bu dosyanın kendi yorumu bunu itiraf ediyordu
       ("tile_cache.py'nin AYNI formülünün istemci kopyası ... İkisi
       değişirse birlikte güncellenmeli"). İki sahipli sayı er geç kayar;
       kutup kırpma ve tarih çizgisi sarmalama kuralı da ikizlenmişti.

       ARTIK: geometri ``/api/tile/cache/status`` gövdesindeki
       ``tile_matrix`` alanından OKUNUR (önyükleme sözleşmesi).
       FAIL-CLOSED: geometri yüklenmediyse karo İSTENMEZ — yanlış karo
       istemektense hiç istememek doğrudur; altındaki Blue Marble taban
       dokusu görünür kalır (kısmi yükleme zaten kabul edilen davranış). */
    var _tileGeom = null;               // sunucudan gelen geometri (yoksa null)
    var _tileGeomIstendi = false;

    /* K5a — AĞ KAPISI (gizlilik; karar §28-33, tasarım §4.1-2).
       Karo isteği kullanıcının BAKTIĞI bölgeyi sağlayıcıya (NASA GIBS)
       söyler. Dış istek yalnız kullanıcı anahtarı AÇTIYSA gider; varsayılan
       KAPALI. Kapının kendisi sunucudadır (tile_cache.resolve_tile): istek
       rıza parametresini taşımıyorsa sunucu dışarı çıkmaz, önbellekte
       olmayan karoya 403 verir. Rıza parametresinin adı ve değeri SUNUCUDAN
       okunur (``/api/tile/cache/status`` ``network_opt_in``; burada kopyası
       yok). Okunamazsa parametre eklenmez, yani kapı kapalı kalır.
       Kalıcı ayar bu tarayıcının yerel deposundadır; okunamazsa KAPALI. */
    var TILE_NETWORK_STORAGE_KEY = 'hrma_tile_network';
    var TILE_NETWORK_ON = 'on';
    var _tileAgRizasi = null;           // {param, value} sunucudan (yoksa null)
    var _RIZA_DESENI = /^[a-z0-9_]{1,16}$/;

    function tileAgAcik() {
        try {
            return !!global.localStorage
                && global.localStorage.getItem(TILE_NETWORK_STORAGE_KEY) === TILE_NETWORK_ON;
        } catch (e) { return false; }
    }

    function tileAgYaz(acik) {
        try {
            if (!global.localStorage) return;
            if (acik === true) global.localStorage.setItem(TILE_NETWORK_STORAGE_KEY, TILE_NETWORK_ON);
            else global.localStorage.removeItem(TILE_NETWORK_STORAGE_KEY);
        } catch (e) { /* yazılamadı: tileAgAcik yine okur, açık sanılmaz */ }
    }

    function tileAgRizasiOku(d) {
        var r = d && d.network_opt_in;
        if (r && typeof r.param === 'string' && typeof r.value === 'string'
                && _RIZA_DESENI.test(r.param) && _RIZA_DESENI.test(r.value)) {
            _tileAgRizasi = { param: r.param, value: r.value };
        }
    }

    /* V307/FS-HARİTA-KÜRE — KATMAN URL SÜRÜMÜ (katman -> sürüm dizesi).
       Ağa çıkmayan ama içeriği KURULU PAKETE bağlı katmanın (pack_detail)
       URL'si kurulu paket kümesine göre sürümlenir (?v=) ve rıza parametresi
       taşımaz: karo yanıtları bir yıl 'immutable' önbelleklenir (app.py
       tile_proxy); sürümsüz URL'de paket silinince/yenisi kurulunca tarayıcı
       eski karoyu göstermeye devam ederdi. Sürümü _paketKatmani yazar:
       uygulama sürümü + kurulu paketlerin kimliği ve sha256'sı
       (LaunchSiteMapPacks.imza) üstünden 32 bit FNV-1a özeti, onaltılık
       (yalnız önbellek ayrımı içindir, güvenlik iddiası taşımaz). */
    var _katmanUrlSurumu = {};

    //: Karo URL'si; rıza parametresi YALNIZ anahtar açık ve sözleşme
    //: sunucudan okunmuşsa eklenir. Sürümlü katman (yukarıda) rıza
    //: parametresi almaz.
    function tileUrl(layer, z, tx, ty) {
        var url = '/api/tile/' + layer + '/' + z + '/' + tx + '/' + ty;
        if (Object.prototype.hasOwnProperty.call(_katmanUrlSurumu, layer))
            return url + '?v=' + _katmanUrlSurumu[layer];
        if (tileAgAcik() && _tileAgRizasi)
            url += '?' + _tileAgRizasi.param + '=' + _tileAgRizasi.value;
        return url;
    }

    function fnv32(s) {
        var h = 0x811c9dc5;
        for (var i = 0; i < s.length; i++) {
            h ^= s.charCodeAt(i);
            h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
        }
        return h.toString(16);
    }

    //: Kurulu paketlerin kutuları ve imzası (launch_site_map_packs.js
    //: deposu). Depo yoksa ya da biçim tutmazsa null: paket katmanı istenmez.
    function paketDeposuOku() {
        var P = global.LaunchSiteMapPacks;
        if (!P || typeof P.kuruluKutular !== 'function' || typeof P.imza !== 'function') return null;
        var ham = P.kuruluKutular(), kutular = [];
        if (!Array.isArray(ham)) return null;
        for (var i = 0; i < ham.length; i++) {
            var b = ham[i] && ham[i].bbox;
            if (b && b.length === 4 && isFinite(b[0]) && isFinite(b[1]) && isFinite(b[2])
                    && isFinite(b[3]) && b[0] < b[2] && b[1] < b[3])
                kutular.push([+b[0], +b[1], +b[2], +b[3]]);
        }
        return { kutular: kutular, imza: String(P.imza()) };
    }

    //: [w,s,e,n] iki kutu kesişimi (alan > 0) ya da null.
    function kutuKesisim(a, b) {
        var w = Math.max(a[0], b[0]), s = Math.max(a[1], b[1]);
        var e = Math.min(a[2], b[2]), n = Math.min(a[3], b[3]);
        return (w < e && s < n) ? [w, s, e, n] : null;
    }

    function tileGeomYukle() {
        if (_tileGeomIstendi) return;
        _tileGeomIstendi = true;
        fetch('/api/tile/cache/status').then(function (r) {
            return r.ok ? r.json() : null;
        }).then(function (d) {
            if (d && d.tile_matrix && d.tile_matrix.levels) {
                _tileGeom = d.tile_matrix;
            }
            tileAgRizasiOku(d);
            paketliTavanOku(d);
            detayTavanOku(d);
            paketTavanOku(d);
        }).catch(function () { /* çevrimdışı: geometri yok, karo istenmez */ });
    }

    //: İndirilen paket katmanının tavanı (V307/FS-HARİTA-KÜRE). Kaynak 'pack'
    //: değilse, arayüze sunulmuyorsa (künyesi yoksa sunucu ui_offered=false
    //: yayımlar), tavan bluemarble tavanının üstünde bir tamsayı değilse ya
    //: da o düzeyin geometrisi yayımlanmadıysa null: katman hiç istenmez.
    function paketTavanOku(d) {
        var k = d && d.layers && d.layers.packs && d.layers.packs[TILE_LAYER_PACK];
        var mz = k ? k.max_zoom : null;
        var lv = d && d.tile_matrix && d.tile_matrix.levels;
        if (k && k.source === TILE_SOURCE_PACK && k.ui_offered === true
                && typeof mz === 'number' && isFinite(mz) && Math.floor(mz) === mz
                && mz > TILE_MAX_ZOOM && lv && lv[String(mz)])
            _paketTavan = mz;
    }

    //: Ayrıntı katmanının tavanı sunucunun GIBS kataloğundan (V307/FS-HARİTA).
    //: Kaynak 'gibs' değilse, arayüze sunulmuyorsa, tavan bluemarble
    //: tavanının üstünde bir tamsayı değilse ya da o düzeyin geometrisi
    //: yayımlanmadıysa null: katman hiç istenmez.
    function detayTavanOku(d) {
        var k = d && d.layers && d.layers.layers && d.layers.layers[TILE_LAYER_DETAIL];
        var mz = k ? k.max_zoom : null;
        var lv = d && d.tile_matrix && d.tile_matrix.levels;
        if (k && k.source === TILE_SOURCE_GIBS && k.ui_offered === true
                && typeof mz === 'number' && isFinite(mz) && Math.floor(mz) === mz
                && mz > TILE_MAX_ZOOM && lv && lv[String(mz)])
            _detayTavan = mz;
    }

    //: Paketli katmanın tavanı sunucunun katman kataloğundan; kaynak türü
    //: 'packaged' değilse ya da tavan geçerli bir tamsayı değilse null.
    function paketliTavanOku(d) {
        var k = d && d.layers && d.layers.packaged && d.layers.packaged[TILE_LAYER_PACKAGED];
        var mz = k ? k.max_zoom : null;
        if (k && k.source === TILE_SOURCE_PACKAGED && typeof mz === 'number'
                && isFinite(mz) && mz >= 0 && Math.floor(mz) === mz && mz <= TILE_MAX_ZOOM)
            _paketliTavan = mz;
    }

    //: z için {span, mw, mh} — sunucu yayımlamadıysa null (türetme YOK).
    function tileLevel(z) {
        if (!_tileGeom || !_tileGeom.levels) return null;
        var lv = _tileGeom.levels[String(z)];
        if (!lv) return null;
        var span = lv.span_deg, mw = lv.matrix_width, mh = lv.matrix_height;
        if (!(span > 0) || !(mw > 0) || !(mh > 0)) return null;
        return { span: span, mw: mw, mh: mh };
    }

    function tileSpanDeg(z) {
        var lv = tileLevel(z);
        return lv ? lv.span : null;      // türetme yok: bilinmiyorsa null
    }

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function deg2rad(d) { return d * Math.PI / 180.0; }
    // ---- Düz (dokusuz) malzeme rengi: sRGB hex -> LİNEER --------------------
    // ÖLÇÜLEN KUSUR: çıkış sRGB kodlanıyor (renderer.outputEncoding =
    // sRGBEncoding, aşağıda). Shader'dan çıkan LİNEER değer ekrana yazılırken
    // sRGB'ye çevrildiği için, malzemeye verilen HAM hex lineer sayı sayılıyor
    // ve ekranda AÇILIYOR: 0xff8c33 -> #ffc47c, 0x2dd4a8 -> #75ebd4. Lejant
    // (launch_site.html .ls-chip .sw ve olay noktaları) AYNI hex'i CSS ile
    // basıyor; CSS değeri zaten sRGB olduğundan iki taraf tutmuyordu. Rengi
    // burada lineere çevirince ekrandaki piksel tam olarak lejanttaki hex olur.
    // DOKULARA UYGULANMAZ: onlar tex.encoding = sRGBEncoding ile işaretli, yani
    // dönüşümü GPU zaten yapıyor — elle çevirmek çift dönüşüm olurdu.
    function srgb(hex) { return new global.THREE.Color(hex).convertSRGBToLinear(); }
    function rad2deg(r) { return r * 180.0 / Math.PI; }
    function normLon(lon) { return ((lon + 180.0) % 360.0 + 360.0) % 360.0 - 180.0; }

    // ---- Jeodezik <-> kartezyen (küre yüzeyi) --------------------------------
    // THREE.SphereGeometry varsayılan UV + equirectangular doku ile TUTARLI
    // türetilmiştir (doku sol kenarı = -180° boylam). Marker, sınır ve raycast
    // AYNI dönüşümü kullanır -> iç tutarlılık garanti.
    // ÖH harita-detay K2: dönüşümün TEK formülü latLonToXYZ'dir. Nesne
    // üretmeden düz diziye yazar; vektör katmanları (~1,3 M köşe) bunu kullanır,
    // Vector3 isteyen her yer latLonToVec3 üzerinden aynı formülü çağırır.
    function latLonToXYZ(latDeg, lonDeg, radius, out, i) {
        var la = deg2rad(latDeg), lo = deg2rad(lonDeg);
        var cl = Math.cos(la);
        out[i] = radius * cl * Math.cos(lo);
        out[i + 1] = radius * Math.sin(la);
        out[i + 2] = -radius * cl * Math.sin(lo);
        return out;
    }
    function latLonToVec3(latDeg, lonDeg, radius) {
        var p = latLonToXYZ(latDeg, lonDeg, radius, [0, 0, 0], 0);
        return new global.THREE.Vector3(p[0], p[1], p[2]);
    }
    function vec3ToLatLon(v) {
        var r = v.length();
        var lat = rad2deg(Math.asin(clamp(v.y / r, -1, 1)));
        var lon = rad2deg(Math.atan2(-v.z, v.x));
        return { lat: lat, lon: normLon(lon) };
    }

    // ---- Gök küresi (SAHNE İÇİ) ---------------------------------------------
    // Gökyüzü CSS arka planı DEĞİL, sahnenin parçasıdır. Ölçülen kusur: CSS
    // katmanı kamerayla dönmüyordu — kamera 90° döndürüldüğünde gökyüzü
    // dikdörtgeninde 56.000 pikselin 56.000'i özdeş kaldı, yani "yıldızlar"
    // Dünya'ya göre çivili duruyordu. Sahne içi küre bu yanılsamayı bitirir.
    var R_SKY = GLOBE_R * 50;        // 5000 birim — kamera far düzlemi (100000) içinde
    var R_STAR = R_SKY * 0.98;       // yıldızlar dokunun ÖNÜNDE (aynı yarıçapta z-savaşı olurdu)

    // Kadir kovaları. r128'in PointsMaterial'ı nokta-BAŞINA boyut desteklemez
    // (gl_PointSize tek uniform'dan gelir), bu yüzden parlaklık ayrımı ancak
    // AYRI Points nesneleriyle yapılabilir — kova sayısı estetik değil,
    // kütüphane sürümünün dayattığı bir kısıttır.
    var STAR_BUCKETS = [
        { vmax: 1.0, size: 3.0, opacity: 1.0 },
        { vmax: 2.5, size: 2.2, opacity: 0.95 },
        { vmax: 4.0, size: 1.6, opacity: 0.85 },
        { vmax: 5.5, size: 1.1, opacity: 0.7 },
        { vmax: Infinity, size: 0.8, opacity: 0.5 }
    ];

    // Greenwich ortalama yıldız zamanı [derece] — IAU 1982 basitleştirmesi;
    // hata on yıllar boyunca ≲0,1° (bir yıldızın ekrandaki yerinde gözle
    // görülmez). J2000 kontrolü: ms = 946728000000 (2000-01-01 12:00 UTC)
    // -> d = 0 -> 280,46061837°.
    function gmstDeg(ms) {
        var d = ms / 86400000.0 - 10957.5;   // J2000.0'dan gün (Unix epoch farkı 10957,5 gün)
        var g = 280.46061837 + 360.98564736629 * d;
        return ((g % 360) + 360) % 360;
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
        // ÖH harita-detay K2: kare sonu dinleyicileri (addFrameListener).
        this._frameListeners = [];
        this._frame = null;           // yeniden kullanılan kare yükü
        this._vectors = null;         // LaunchSiteVectors (yüklenemezse null)
        this._vectorsReady = false;   // true iken eski 110m JSON bindirmesi gizli
        this._init();
    }

    LaunchSiteGlobe.prototype._init = function () {
        var THREE = global.THREE;
        if (!THREE || !THREE.WebGLRenderer) {
            this._kurulamadi = true;
            if (this._onError) this._onError('three_missing');
            return;
        }
        var w = this.container.clientWidth || 800;
        var h = this.container.clientHeight || 600;

        var renderer;
        try {
            renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        } catch (e) {
            this._kurulamadi = true;
            if (this._onError) this._onError('webgl_failed');
            return;
        }
        renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
        renderer.setSize(w, h);
        // Dokular sRGB işaretleniyor (_loadTexture ve _buildTilePatch: tex.encoding
        // = sRGBEncoding) -> shader girişinde lineere ÇÖZÜLÜYORLAR. Çıkışın da sRGB
        // kodlanması ŞART, yoksa kare lineer kalır ve ekranda gamma kadar karanlık
        // görünür. motor_viz3d.js:1625 ile aynı biçim/aynı davranış.
        renderer.outputEncoding = THREE.sRGBEncoding;
        // OPAK zemin (alpha = 1). ÖLÇÜLEN KUSUR: tuval saydamken (alpha = 0)
        // arkasındaki sayfa gövdesi görünüyordu ve theme.css'in genel body süsü
        // oraya 16 UYDURMA yıldız + 3 nebula basıyor (prosedürel gradyanlar,
        // hiçbir katalogla ilgisi yok). O katman kamerayla dönmediği hâlde
        // gökyüzü sanılıyordu; üstelik Samanyolu dokusu (1,5 MB) yüklenene kadar
        // — ve hiç yüklenemezse SÜREKLİ — ekrandaki tek "gökyüzü" o sahte
        // katmandı. Tuval opak olunca bu sayfada gökyüzü YALNIZ sahne içi gerçek
        // varlıklardan gelir (_buildSky: ESO panoraması + Yale katalogu, ikisi de
        // kamerayla döner); hiçbiri yüklenemezse ekran SİYAH kalır — dürüst olan
        // budur, boşluk sahte yıldızla doldurulmaz.
        renderer.setClearColor(0x000000, 1);
        this.container.appendChild(renderer.domElement);
        this.renderer = renderer;

        var scene = new THREE.Scene();
        this.scene = scene;

        var camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 100000);
        // aspect zaten kuruldu (w/h) -> mesafe ilk karede de doğru çerçeveler.
        camera.position.set(0, GLOBE_R * 0.55, globalViewDist(camera));
        this.camera = camera;
        // Açılış çerçevesi "tüm Dünya"dır; _resize bunu bilerek yeniden çerçeveler.
        this._mode = 'global';

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

        // --- Gök küresi (Samanyolu dokusu + gerçek yıldızlar) ---
        // DÜRÜSTLÜK: tek zaman kaynağı TARAYICI SAATİDİR (sunucu/NTP değil) ve
        // yönelim SAYFA AÇILIŞ ANINA sabitlenir — canlı döndürme YOK, çünkü
        // canlı dönen bir gökyüzü "gerçek zamanlı astronomi" iddiası üretirdi.
        // Hangi ana sabitlendiği arayüzde yazılır (#ls-sky-time).
        this._skyEpochMs = Date.now();
        this._skyGmstDeg = gmstDeg(this._skyEpochMs);
        this._skyGroup = new THREE.Group();
        // Yıldız sahne boylamı = RA olarak yerleştirilir; grup y ekseninde
        // -GMST kadar döndürülünce nihai boylam RA - GMST olur = yıldızın
        // altındaki gerçek boylam (LST = GMST + boylam = RA kuralı).
        // y-dönüşü θ, boylama +θ ekler (küre parametrizasyonundan türetildi).
        this._skyGroup.rotation.y = -deg2rad(this._skyGmstDeg);
        scene.add(this._skyGroup);
        this._buildSky();

        // --- Küre (Blue Marble) ---
        var geo = new THREE.SphereGeometry(GLOBE_R, 96, 64);
        // ÖH D21 / P12aB4-20: doku inmediğinde ekranda kalan TEK renk budur;
        // srgb() atlandığı için ~#667c8d'ye açılıyor, "boş küre" koyu lacivert
        // yerine gri-mavi görünüyordu. Specular de aynı malzemenin rengidir.
        var mat = new THREE.MeshPhongMaterial({
            color: srgb(0x223344), shininess: 6, specular: srgb(0x111820)
        });
        this.globe = new THREE.Mesh(geo, mat);
        scene.add(this.globe);

        // İnce atmosfer halkası (yalnız görsel; fiziğe bağlı değil)
        var atmGeo = new THREE.SphereGeometry(GLOBE_R * 1.018, 96, 64);
        var atmMat = new THREE.MeshBasicMaterial({
            color: srgb(0x2f6fb0), transparent: true, opacity: 0.10,
            side: THREE.BackSide, depthWrite: false
        });
        scene.add(new THREE.Mesh(atmGeo, atmMat));

        this._loadTexture();
        this._buildBorders();
        this._buildVectorLOD();
        this._buildMarker();
        this._buildRaycaster();

        // Uçuş yolu grupları (sonradan doldurulur)
        this.flightGroup = new THREE.Group();
        scene.add(this.flightGroup);

        // GIBS karo yamaları ayrı grupta (arazi; uçuş yolundan bağımsız yaşar)
        this._tileGroup = new THREE.Group();
        scene.add(this._tileGroup);
        this._paketKur(scene);
        this._tiles = new Map();        // anahtar layer:z:x:y -> {mesh,t,loading}
        this._tileNextT = 0;            // patch güncelleme kısma zamanı
        // P5B4-30 — ÖNYÜKLEME SÖZLEŞMESİ: matris geometrisi sunucudan
        // ÖNCEDEN istenir; ilk karo turuna kadar yanıt gelmiş olur.
        // Gelmezse karo istenmez (fail-closed), tur yeniden ister.
        tileGeomYukle();
        this._tileAnyFail = false;      // en az bir karo yüklenemedi (offline notu)
        this._merkezDoku = null;        // ekran merkezindeki en ince çizilen karo {layer, z}

        this._bindEvents();
        this._resize();
        this._animate();
        if (this._onReady) this._onReady();
    };

    /* V307/FS-HARİTA-KÜRE — PAKET BİNDİRMESİ GRUBU. Bindirme saydamdır ve
       derinlik YAZMAZ; zemin karosuyla aynı küre üstünde durduğu için
       çizgilerle AYNI kuralla kaldırılır (LaunchSiteVectors.kaldirmaOlcegi:
       yüzeyden max(2 m, 1e-4·irtifa); ikinci kural yok). Bu kaldırma ekran
       pikselinin ~0,13'ü kadardır (1e-4·irtifa ÷ ~7,7e-4·irtifa m/px), yani
       yatayda görünmez; derinlikte ise zemin karosunun (küreye değen ya da
       altında) önünde kalmayı güvenceler. Bindirmenin kendi yüzünün küreden
       sarkması bu kaldırmanın en küçük değerinin yarısıyla sınırlanır
       (_makeTileMesh, ince bölme). Kural okunamazsa (vektör modülü yoksa)
       paket katmanı hiç istenmez (fail-closed). */
    LaunchSiteGlobe.prototype._paketKur = function (scene) {
        var THREE = global.THREE;
        var VK = global.LaunchSiteVectors;
        this._paketKaldir = (VK && typeof VK.kaldirmaOlcegi === 'function') ? VK.kaldirmaOlcegi : null;
        this._paketGroup = new THREE.Group();
        this._paketGroup.visible = false;
        scene.add(this._paketGroup);
        this._paketImza = null;         // son okunan kurulu paket imzası
        this._paketEtkin = false;       // bindirme bu turda çiziliyor mu
        this._paketZ = null;            // bindirmenin istenen düzeyi
        this._maskeliSeviyeler = {};    // NE su çizgisi maskesi uygulanmış basamaklar
        this._paketAdimDeg = null;
        if (!this._paketKaldir) return;
        var hMin = (this._paketKaldir(0, R_EARTH_M) - 1) * R_EARTH_M;
        // Yüz sarkması sınırı hMin/2: kare yüzün merkezi küreden R·a²/4
        // kadar sarkar -> a <= 2·sqrt((hMin/2)/R) [rad].
        if (hMin > 0) this._paketAdimDeg = rad2deg(2 * Math.sqrt(hMin / 2 / R_EARTH_M));
        var self = this;
        this.addFrameListener(function (f) {
            self._paketGroup.scale.setScalar(self._paketKaldir(f.camAltitudeM, R_EARTH_M));
            self._neSuMaskele();
        });
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

    // ---- Gök küresi --------------------------------------------------------
    // İki bağımsız katman: (1) Samanyolu panoraması, (2) Yale Parlak Yıldız
    // Katalogu'ndan gerçek yıldızlar. Biri yüklenemezse diğeri yine çizilir;
    // ikisi de yüklenemezse gökyüzü BOŞ kalır — prosedürel/sahte yıldız alanı
    // ÜRETİLMEZ.
    LaunchSiteGlobe.prototype._buildSky = function () {
        this._buildMilkyWay();
        this._buildStars();
    };

    // (1) Samanyolu: ESO/S. Brunier panoraması (4096x2048 equirectangular),
    // GALAKTİK koordinatlarda. Doku BackSide bir küreye içeriden giydirilir.
    LaunchSiteGlobe.prototype._buildMilkyWay = function () {
        var THREE = global.THREE, self = this;
        var url = (this.opts.milkyWayUrl || '/static/img/milky_way_eso0932a_4096.webp');
        new THREE.TextureLoader().load(url, function (tex) {
            if (self._disposed || !self._skyGroup) { tex.dispose(); return; }
            tex.colorSpace = THREE.SRGBColorSpace || tex.colorSpace;
            tex.encoding = THREE.sRGBEncoding || tex.encoding;
            // U-AYNALAMA — ÖLÇÜLMÜŞ GEREKÇE: bu panoramada galaktik boylam
            // görüntüde SOLA doğru artıyor (LMC/SMC lekeleri "sola-artar"
            // konumda parlak: 29,0 / 16,0; "sağa-artar" konumda yalnız fon
            // seviyesi: 11,8). SphereGeometry UV'si ise boylamın u ile ARTTIĞINI
            // varsayar. Aynalanmazsa gökyüzü ayna görüntüsü olurdu.
            tex.wrapS = THREE.RepeatWrapping;
            tex.repeat.x = -1;
            tex.offset.x = 1;      // u' = 1 - u : yatay ayna
            var geo = new THREE.SphereGeometry(R_SKY, 48, 32);
            var mat = new THREE.MeshBasicMaterial({
                map: tex, side: THREE.BackSide, depthWrite: false });
            var mw = new THREE.Mesh(geo, mat);
            mw.renderOrder = -2;                 // her şeyin arkasına çizilir
            // GALAKTİK -> EKVATORAL yönelim. J2000 çapaları: kuzey galaktik
            // kutup (RA 192,85948 / Dec +27,12825) ve galaktik merkez yönü
            // (RA 266,404988 / Dec -28,936175). Sayısal doğrulandı:
            // l=90,b=0 -> RA 318,004 Dec +48,330; LMC -> RA 80,887 Dec -69,760.
            var GAL_POLE = latLonToVec3(27.12825, 192.85948, 1);
            var GAL_CENTER = latLonToVec3(-28.936175, 266.404988, 1);
            var gz = new THREE.Vector3().crossVectors(GAL_CENTER, GAL_POLE);
            // makeBasis SÜTUN vektörleri alır: yerel x = galaktik merkez yönü,
            // yerel y = galaktik kutup. latLonToVec3(0,0) = (1,0,0) olduğundan
            // dokunun l=0,b=0 içeriği tam galaktik merkeze oturur.
            var m = new THREE.Matrix4().makeBasis(GAL_CENTER, GAL_POLE, gz);
            mw.quaternion.setFromRotationMatrix(m);
            self._milkyWayMesh = mw;
            self._skyGroup.add(mw);              // GMST dönüşü gruptan gelir
        }, undefined, function () {
            // Doku yüklenemedi: mesh sahneye HİÇ eklenmez. Kozmetik katman
            // olduğu için kullanıcıya hata basılmaz; yıldızlar bağımsız yüklenir.
            // ÖH D21 / P12aB4-25: konsol metinleri ürünün varsayılan diliyle
            // (İngilizce) tek dilde tutulur — ekran metni değildir, çevrilmez.
            if (global.console) console.warn('LaunchSiteGlobe: Milky Way texture failed to load: ' + url);
        });
    };

    // (2) Yıldızlar: bsc5p_stars.bin (Yale BSC5, J2000 EKVATORAL). Konumlar
    // doğrudan ekvatoral çerçevededir — galaktik quaternion YALNIZ Samanyolu
    // mesh'ine uygulanır, yıldızlara UYGULANMAZ (ikisi farklı çerçevede gelir).
    LaunchSiteGlobe.prototype._buildStars = function () {
        var THREE = global.THREE, self = this;
        var url = (this.opts.starsUrl || '/static/data/bsc5p_stars.bin');
        fetch(url).then(function (r) {
            // HTTP durumu ÖNCE denetlenir: fetch 404'te de reddetmez, gövdeyi
            // (sunucunun HTML hata sayfasını) döndürür. Denetimsizken o HTML
            // ikilik olarak ayrıştırılıp "imza <!DO" gibi yanıltıcı bir uyarıya
            // dönüşüyordu — asıl sorun dosyanın bozuk olması değil, YOK olmasıdır.
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.arrayBuffer();
        }).then(function (buf) {
            if (self._disposed || !self._skyGroup) return;
            var dv = new DataView(buf);
            // Biçim: 4 bayt 'BSC1' + uint32 N + N x (float32 ra, dec, vmag),
            // little-endian. İmza tutmazsa YILDIZ ÇİZİLMEZ (uydurma yıldız yok).
            if (buf.byteLength < 8) { self._warnStars(url, 'file has no header'); return; }
            var magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1),
                dv.getUint8(2), dv.getUint8(3));
            if (magic !== 'BSC1') { self._warnStars(url, 'imza ' + magic); return; }
            var n = dv.getUint32(4, true);
            if (buf.byteLength < 8 + 12 * n) {
                self._warnStars(url, 'file truncated (' + buf.byteLength + ' bytes, ' + n + ' records)');
                return;
            }
            var groups = [], i;
            for (i = 0; i < STAR_BUCKETS.length; i++) groups.push([]);
            var count = 0;
            for (i = 0; i < n; i++) {
                var o = 8 + 12 * i;
                var ra = dv.getFloat32(o, true);
                var dec = dv.getFloat32(o + 4, true);
                var vmag = dv.getFloat32(o + 8, true);
                if (!isFinite(ra) || !isFinite(dec) || !isFinite(vmag)) continue;
                // RA -> sahne boylamı, Dec -> sahne enlemi (aynı dönüşüm,
                // yüzey işaretçileriyle iç tutarlı).
                var p = latLonToVec3(dec, ra, R_STAR);
                var b = STAR_BUCKETS.length - 1;
                for (var k = 0; k < STAR_BUCKETS.length; k++) {
                    if (vmag < STAR_BUCKETS[k].vmax) { b = k; break; }
                }
                groups[b].push(p.x, p.y, p.z);
                count++;
            }
            self._starPoints = [];
            for (i = 0; i < STAR_BUCKETS.length; i++) {
                if (!groups[i].length) continue;
                var g = new THREE.BufferGeometry();
                g.setAttribute('position', new THREE.Float32BufferAttribute(groups[i], 3));
                var mat = new THREE.PointsMaterial({
                    color: 0xffffff, size: STAR_BUCKETS[i].size,
                    sizeAttenuation: false,          // ekran-sabit piksel boyutu
                    transparent: true, opacity: STAR_BUCKETS[i].opacity,
                    depthWrite: false });
                var pts = new THREE.Points(g, mat);
                pts.renderOrder = -1;                // Samanyolu dokusunun önünde
                self._starPoints.push(pts);
                self._skyGroup.add(pts);
            }
            self._skyStarCount = count;
        }).catch(function (e) {
            self._warnStars(url, e && e.message ? e.message : 'unreadable');
        });
    };

    LaunchSiteGlobe.prototype._warnStars = function (url, why) {
        // ÖH D21 / P12aB4-25 — bkz. _buildSky(): konsol tek dilde (İngilizce).
        if (global.console) console.warn('LaunchSiteGlobe: star catalogue unavailable (' + url + '): ' + why);
    };

    // Gökyüzü durumu (arayüz epoch beyanı + otomatik test kancası).
    LaunchSiteGlobe.prototype.getSkyInfo = function () {
        return {
            epochMs: this._skyEpochMs,
            gmstDeg: this._skyGmstDeg,
            starCount: this._skyStarCount || 0,
            milkyWay: !!this._milkyWayMesh
        };
    };

    LaunchSiteGlobe.prototype._disposeSky = function () {
        var kill = function (obj) {
            if (!obj) return;
            if (obj.parent) obj.parent.remove(obj);
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) {
                if (obj.material.map) obj.material.map.dispose();
                obj.material.dispose();
            }
        };
        kill(this._milkyWayMesh);
        this._milkyWayMesh = null;
        if (this._starPoints) {
            for (var i = 0; i < this._starPoints.length; i++) kill(this._starPoints[i]);
            this._starPoints = null;
        }
        if (this._skyGroup && this._skyGroup.parent)
            this._skyGroup.parent.remove(this._skyGroup);
    };

    LaunchSiteGlobe.prototype._buildBorders = function () {
        var THREE = global.THREE, self = this;
        var url = (this.opts.bordersUrl || '/static/img/earth_borders.json');
        fetch(url).then(function (r) { return r.json(); }).then(function (data) {
            if (self._disposed || !data || !data.layers) return;
            var layers = data.layers;
            var group = new THREE.Group();
            /* V307/FS-HARİTA — YEDEK SINIR ÇİZGİSİ YÜKSEKLİĞİ. Çizgiler
               GLOBE_R·1,001'de (6,4 km yukarıda) kuruluyordu: 110m verisinin
               en uzun parçası 7,85 km sarkar (ölçüldü: 7.647 parçada
               R(1-cos(θ/2)) en büyüğü 7.852 m), 6,4 km bunu örtmek içindi;
               bedeli, yakın görünümde çizginin sondaj roketi yayının ÜSTÜNDE
               durmasıydı (FS-İZLEME). Artık vektör modülünün kaldırma kuralı
               (launch_site_vectors.js kaldirmaOlcegi: yüzeyden max(2 m,
               1e-4·irtifa)) burada da uygulanır: parçalar büyük çember
               üzerinde, kiriş sarkması bu kuralın tabanını (2 m) aşmayacak
               açıyla bölünür (θ_max = 2·acos(1 - 2 m / R) = 0,0908°, 58.865
               parça) ve grup her karede aynı ölçekle kaldırılır. Vektör
               modülü yoksa kural okunamaz: eski 1,001R kurulumu aynen kalır. */
            var V = global.LaunchSiteVectors;
            var kaldir = (V && typeof V.kaldirmaOlcegi === 'function') ? V.kaldirmaOlcegi : null;
            var hMin = kaldir ? (kaldir(0, R_EARTH_M) - 1) * R_EARTH_M : null;
            var rCiz = (hMin > 0) ? GLOBE_R : GLOBE_R * 1.001;
            var thMax = (hMin > 0) ? 2 * Math.acos(1 - hMin / R_EARTH_M) : Infinity;
            var mkLines = function (polylines, color, opacity) {
                if (!polylines) return;
                var positions = [], pa = [0, 0, 0], pb = [0, 0, 0];
                for (var i = 0; i < polylines.length; i++) {
                    var flat = polylines[i];
                    for (var j = 0; j + 3 < flat.length; j += 2) {
                        latLonToXYZ(flat[j + 1], flat[j], 1, pa, 0);
                        latLonToXYZ(flat[j + 3], flat[j + 2], 1, pb, 0);
                        var cs = clamp(pa[0] * pb[0] + pa[1] * pb[1] + pa[2] * pb[2], -1, 1);
                        var th = Math.acos(cs), sn = Math.sin(th);
                        var n = (th > thMax && sn > 1e-12) ? Math.ceil(th / thMax) : 1;
                        var ox = pa[0] * rCiz, oy = pa[1] * rCiz, oz = pa[2] * rCiz;
                        for (var q = 1; q <= n; q++) {
                            var x, y, z;
                            if (n === 1) { x = pb[0]; y = pb[1]; z = pb[2]; }
                            else {   // büyük çember (slerp)
                                var ka = Math.sin((1 - q / n) * th) / sn, kb = Math.sin(q / n * th) / sn;
                                x = ka * pa[0] + kb * pb[0]; y = ka * pa[1] + kb * pb[1]; z = ka * pa[2] + kb * pb[2];
                            }
                            positions.push(ox, oy, oz, x * rCiz, y * rCiz, z * rCiz);
                            ox = x * rCiz; oy = y * rCiz; oz = z * rCiz;
                        }
                    }
                }
                var g = new THREE.BufferGeometry();
                g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
                var m = new THREE.LineBasicMaterial({
                    color: color, transparent: true, opacity: opacity, depthWrite: false
                });
                var ls = new THREE.LineSegments(g, m);
                group.add(ls);
                return ls;
            };
            // ÖH D21 / P12aB4-20: bu iki çağrı srgb() dönüşümünü ATLIYORDU;
            // çıkış sRGB kodlandığı için ham hex lineer sayılıp ekranda
            // açılıyordu (0x8fd6ff -> ~#c5ecff, 0xbfe6ff -> ~#e0f4ff), koyu
            // okyanus üstünde kıyı/sınır ayrımı zayıflıyordu.
            var kiyi = mkLines(layers.coastline, srgb(0x8fd6ff), 0.34);
            // V307/FS-HARİTA-KÜRE: yedek kıyı çizgisi de paket bindirmesinin
            // çizildiği pikselde basılmaz (NE su maskesi, _neSuMaskele).
            if (kiyi) paketMaskesiUygula(kiyi.material);
            mkLines(layers.borders, srgb(0xbfe6ff), 0.5);
            // ÖH harita-detay K2: bu bindirme artık 110m YEDEĞİDİR. Vektör
            // basamakları (launch_site_vectors.js) hazırsa gizli doğar; vektör
            // varlıkları yüklenemez ya da sonradan bozulursa yeniden görünür.
            group.visible = !self._vectorsReady;
            self.bordersGroup = group;
            self._bordersMinLiftM = (hMin > 0) ? hMin : null;
            self.scene.add(group);
            if (hMin > 0) self.addFrameListener(function (f) {
                group.scale.setScalar(kaldir(f.camAltitudeM, R_EARTH_M));
            });
        }).catch(function () { /* sınır bindirmesi opsiyonel; sessiz geç */ });
    };

    /* ÖH harita-detay K2 — VEKTÖR AYRINTI BASAMAKLARI (tasarım §3.1-3.2).
       Natural Earth 110m/50m/10m çizgileri hrma/static/map/ altındaki HMV1
       varlıklarından gelir; basamak, hücre ve ufuk ayıklaması
       launch_site_vectors.js'tedir. Bu dosya yalnız sahneyi, koordinat
       dönüşümünü ve renk dönüşümünü verir, kare kancasıyla besler.
       YEDEK: modül yoksa, manifest ya da 110m ikilisi yüklenemezse ya da kanıtı
       tutmazsa eski earth_borders.json bindirmesi (_buildBorders) ekranda
       KALIR, yani görünüm bugünkünden kötüye gitmez. Sahte çizgi üretilmez. */
    LaunchSiteGlobe.prototype._buildVectorLOD = function () {
        var V = global.LaunchSiteVectors, self = this;
        if (!V || this.opts.vectorDetail === false) return;
        var v = new V({
            THREE: global.THREE,
            scene: this.scene,
            latLonToXYZ: latLonToXYZ,
            srgb: srgb,
            globeRadius: GLOBE_R,
            rEarthM: R_EARTH_M,
            baseUrl: this.opts.mapBaseUrl || '/static/map/',
            onReady: function () {
                if (self._disposed) return;
                self._vectorsReady = true;
                if (self.bordersGroup) self.bordersGroup.visible = false;
            },
            onFail: function () {
                // Yedeğe dön: eski 110m görünümü yeniden açılır.
                self._vectorsReady = false;
                if (self.bordersGroup) self.bordersGroup.visible = true;
            }
        });
        this._vectors = v;
        this.addFrameListener(function (f) { v.update(f); });
        v.start();
    };

    /* V307/FS-HARİTA-KÜRE — PAKET VARKEN NE SU ÇİZGİLERİ GİZLİ (R11).
       Natural Earth 1:10m kıyı/göl/akarsu çizgileri yakın ölçekte gerçek
       kıyıdan yüzlerce metre-kilometre sapar (faz 1 ölçümü); paket bindirmesi
       aynı yerde OpenStreetMap su ve kıyısını çizer. Bu katmanların
       malzemesi stencil sınavı alır: paket bindirmesinin çizildiği pikselde
       (bit 1) basılmaz, dışında bugünkü gibi basılır. Böylece gizleme tam
       olarak paket kapsamıyla (bindirme paket kutusuna kırpılır) ve
       bindirmenin çizildiği ölçekle sınırlıdır. Ülke/il sınırları paket
       tarafından çizilmediği için maskelenmez. Katman adları vektör
       modülünün KATMAN_STILI anahtarlarıdır. */
    var NE_SU_KATMANLARI = ['coastline', 'lakes', 'rivers'];
    function paketMaskesiUygula(mat) {
        var THREE = global.THREE;
        if (!mat || (mat.userData && mat.userData.hrmaPaketMaskesi)) return;
        mat.stencilWrite = true;            // r128: stencil sınavı yalnız bununla açılır
        mat.stencilWriteMask = 0;           // yazmaz, yalnız sınar
        mat.stencilFunc = THREE.NotEqualStencilFunc;
        mat.stencilRef = STENCIL_PAKET;
        mat.stencilFuncMask = STENCIL_PAKET;
        mat.stencilFail = THREE.KeepStencilOp;
        mat.stencilZFail = THREE.KeepStencilOp;
        mat.stencilZPass = THREE.KeepStencilOp;
        mat.userData = mat.userData || {};
        mat.userData.hrmaPaketMaskesi = true;
    }
    LaunchSiteGlobe.prototype._neSuMaskele = function () {
        var v = this._vectors;
        if (!v || !v.seviyeler) return;
        for (var ad in v.seviyeler) {
            if (!Object.prototype.hasOwnProperty.call(v.seviyeler, ad)) continue;
            var sv = v.seviyeler[ad];
            if (!sv || !sv.hucreler || this._maskeliSeviyeler[ad]) continue;
            for (var i = 0; i < sv.hucreler.length; i++) {
                var h = sv.hucreler[i];
                if (NE_SU_KATMANLARI.indexOf(h.katman) >= 0) paketMaskesiUygula(h.malzeme);
            }
            this._maskeliSeviyeler[ad] = true;
        }
    };

    // Vektör katmanının canlı durumu (etiket notu, kabul ölçümü, testler).
    // Modül hiç kurulmadıysa yalnız yedeğin durumu döner; sayı uydurulmaz.
    LaunchSiteGlobe.prototype.getVectorInfo = function () {
        var legacy = !!(this.bordersGroup && this.bordersGroup.visible);
        if (!this._vectors) return { durum: 'yok', legacyVisible: legacy };
        var info = this._vectors.getInfo();
        info.legacyVisible = legacy;
        return info;
    };

    /* ÖH harita-detay K2 — KARE KANCASI (tasarım §3.3, "Kanca").
       fn(f) her karenin sonunda, çizimden hemen önce çağrılır. Yük nesnesi
       yeniden kullanılır (kare başına çöp üretilmez); saklanacaksa kopyalanmalı:
         f.camera          THREE.PerspectiveCamera (salt okunur kullanılmalı)
         f.target          controls.target (THREE.Vector3)
         f.metersPerPixel  ekran merkezinde m/px (getScaleInfo ile aynı formül)
         f.zWeb            log2(Z_WEB_Z0_MPP / metersPerPixel)
         f.zMercator       z_web + log2(cos φ), φ ekran merkezi odağının enlemi
                           (gerçek Web Mercator düzeyi; V307/FS-HARİTA-KÜRE)
         f.camAltitudeM    kameranın küre yüzeyinden yüksekliği [m]
         f.size            {width, height} CSS piksel
         f.globeRadius     küre yarıçapı [sahne birimi]
         f.globalViewDist  'Tüm Dünya' düğmesinin (viewGlobe) kamera ile Dünya
                           merkezi arası mesafesi [sahne birimi]; TEK kaynak
                           globalViewDist(camera). Etiket modülü tüm Dünya
                           tavanını buna da bağlar (ana model kararı K-2).
       Dönüş: dinleyiciyi kaldıran işlev. Dinleyici hata atarsa çıkarılır ve
       döngü sürer (bir katmanın hatası küreyi durdurmaz). */
    LaunchSiteGlobe.prototype.addFrameListener = function (fn) {
        if (typeof fn !== 'function') return function () {};
        var list = this._frameListeners;
        list.push(fn);
        return function () {
            var i = list.indexOf(fn);
            if (i >= 0) list.splice(i, 1);
        };
    };

    /* V307 / FS-HARİTA (9 Kas 2026) — EKRAN MERKEZİNİN ODAĞI (tek tanım).
       ÖLÇÜLEN KÖK NEDEN ("yakınlaştırınca şehirler ve zemin yüklenmiyor";
       kanıt ~/HRMA-calisma/2026-11-09/FS-HARITA/olcum/once*): sayfa
       açılışta ve 'Tüm Dünya' düğmesinden sonra yörünge hedefini Dünya
       MERKEZİNE koyar (viewGlobe). Tekerlekle yaklaşmak (OrbitControls
       dolly) hedefi değiştirmez; kamera 19 km irtifaya inse de hedef
       merkezde kalır. Eskiden iki şey hedefe bakıyordu:
         (1) m/px hedefe UZAKLIKTAN hesaplanıyordu: 19,1 km irtifada
             5.208 m/px (gerçek yüzey 15,6 m/px, 334 kat). z_web ~4,9'da
             donuyor, etiket süzgeci (NE min_zoom), vektör basamağı ve
             ölçek çubuğu ("521 km" @ 20 km) küresel düzeyde kalıyordu;
         (2) karo yaması hedef merkezdeyse HİÇ çalışmıyordu
             (`target.length() < 1e-3 -> return`): rıza açıkken de 0 istek.
       ARTIK: hedef kürenin İÇİNDEYSE ekran merkezinin odağı, kameradan
       hedefe giden görüş ışınının küre YÜZEYİNİ deldiği noktadır
       (analitik ışın-küre kesişimi; kamera dışarıda olduğu için ışın
       yüzeyi hedeften önce deler). Hedef yüzeyde ya da üstündeyse
       (Sahaya yakınlaş, uçuş yolu) odak hedefin KENDİSİDİR: o kiplerde
       sayı değişmez. İşlev süreklidir: hedef yüzeye yaklaştıkça kesişim
       noktası hedefe yakınsar. Eşik yok; dönüş nesnesi yeniden kullanılır
       (kare başına çöp yok). */
    LaunchSiteGlobe.prototype._odak = function () {
        var o = this._odakSonuc || (this._odakSonuc = { dist: 0, point: null, yuzey: false });
        var cam = this.camera.position, tgt = this.controls.target;
        var dT = cam.distanceTo(tgt);
        o.dist = dT; o.point = tgt; o.yuzey = false;
        // Kayan nokta payı: yüzeye konmuş hedef (|t| = R) "içeride" sayılmaz.
        if (!(tgt.length() < GLOBE_R * (1 - 1e-9)) || !(dT > 0)) return o;
        var dx = (tgt.x - cam.x) / dT, dy = (tgt.y - cam.y) / dT, dz = (tgt.z - cam.z) / dT;
        var b = cam.x * dx + cam.y * dy + cam.z * dz;
        var c = cam.x * cam.x + cam.y * cam.y + cam.z * cam.z - GLOBE_R * GLOBE_R;
        var disk = b * b - c;
        // Kamera kürenin içindeyse (c <= 0) ya da ışın küreyi kaçırıyorsa
        // (olmaz: hedef içeride) eski tanım korunur, sayı uydurulmaz.
        if (!(c > 0) || !(disk >= 0)) return o;
        var t = -b - Math.sqrt(disk);
        if (!(t > 0) || !(t <= dT)) return o;
        var p = this._odakP || (this._odakP = new global.THREE.Vector3());
        p.x = cam.x + dx * t; p.y = cam.y + dy * t; p.z = cam.z + dz * t;
        o.dist = t; o.point = p; o.yuzey = true;
        return o;
    };

    // Ekran merkezindeki m/px — getScaleInfo ve kare kancasının TEK formülü.
    // Derinlik ekran merkezinin ODAĞINA uzaklıktır (_odak, yukarıda).
    LaunchSiteGlobe.prototype._metersPerPixel = function () {
        var dist = LaunchSiteGlobe.prototype._odak.call(this).dist;
        var fov = deg2rad(this.camera.fov);
        var vh = this.container.clientHeight || 600;
        return (2 * dist * Math.tan(fov / 2)) / vh * M_PER_UNIT;
    };

    LaunchSiteGlobe.prototype._emitFrame = function () {
        var list = this._frameListeners;
        if (!list || !list.length) return;
        var f = this._frame || (this._frame = { size: {} });
        var mpp = this._metersPerPixel();
        f.camera = this.camera;
        f.target = this.controls.target;
        f.metersPerPixel = mpp;
        f.zWeb = Math.log2(Z_WEB_Z0_MPP / mpp);
        // V307/FS-HARİTA-KÜRE: ekran merkezinin GERÇEK Web Mercator düzeyi.
        // z_web ekvator eşdeğeridir; Mercator karosu φ enleminde cos φ kadar
        // küçülür, yani aynı ekran ölçeğinin Mercator düzeyi z_web + log2(cos φ)
        // (φ: odak noktasının enlemi). Paket yer adı isteği karo sayısını bu
        // düzeyle sınırlar. Odak yoksa null (istek yapılmaz).
        var odp = LaunchSiteGlobe.prototype._odak.call(this).point, odr = odp ? odp.length() : 0;
        f.zMercator = (odr > 0)
            ? f.zWeb + Math.log2(Math.max(Math.cos(Math.asin(clamp(odp.y / odr, -1, 1))), 1e-6))
            : null;
        f.camAltitudeM = this.camera.position.length() * M_PER_UNIT - R_EARTH_M;
        f.size.width = this.container.clientWidth || 800;
        f.size.height = this.container.clientHeight || 600;
        f.globeRadius = GLOBE_R;
        f.globalViewDist = globalViewDist(this.camera);
        for (var i = list.length - 1; i >= 0; i--) {
            try {
                list[i](f);
            } catch (e) {
                // Konsol metni tek dilde, İngilizce (P12aB4-25).
                list.splice(i, 1);
                if (global.console && global.console.error)
                    global.console.error('LaunchSiteGlobe: frame listener removed after error', e);
            }
        }
    };

    // Dinamik near (yukarıdaki NEAR_* açıklaması). %1'den küçük değişimde
    // izdüşüm matrisi yeniden kurulmaz.
    LaunchSiteGlobe.prototype._updateNear = function () {
        var cam = this.camera;
        var alt = cam.position.length() - GLOBE_R;
        var dT = cam.position.distanceTo(this.controls.target);
        var n = clamp(NEAR_ORANI * Math.min(alt, dT), NEAR_MIN, NEAR_MAX);
        if (Math.abs(n - cam.near) > cam.near * 0.01) {
            cam.near = n;
            cam.updateProjectionMatrix();
        }
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
        // V307/FS-HARİTA: derinlik ekran merkezinin odağıdır (_odak). Hedef
        // Dünya merkezindeyken tekerlekle yaklaşınca işaretçi eskiden merkez
        // derinliğine (~100 birim) göre büyütülüyordu: 20 km irtifada
        // yüzeydeki iğne ~330 kat büyük çiziliyordu.
        var d = LaunchSiteGlobe.prototype._odak.call(this).dist;
        for (var i = 0; i < this._scalables.length; i++) {
            var s = this._scalables[i];
            if (s.obj.parent) s.obj.scale.setScalar(Math.max(d, 1e-3) * s.k);
        }
    };

    LaunchSiteGlobe.prototype._buildMarker = function () {
        var THREE = global.THREE;
        var grp = new THREE.Group();
        // Birim boyutta dikey iğne + taban halkası (her karede ölçeklenir)
        var pinMat = new THREE.MeshBasicMaterial({ color: srgb(0xff8c33) });
        var pin = new THREE.Mesh(new THREE.ConeGeometry(0.32, 1.0, 16), pinMat);
        pin.position.y = 0.5;
        grp.add(pin);
        // Taban halkası yüzeyle çakışık durur; karo yaması da artık aynı
        // yarıçapta olduğu için halka onun da ÖNÜNE yazılmalı (ÖH D17 /
        // P12aB4-03). Yanlılık karo yamasınınkinden (TILE_DEPTH_BIAS) bir
        // basamak daha güçlüdür.
        var ringMat = new THREE.MeshBasicMaterial({
            color: srgb(0xff8c33), transparent: true, opacity: 0.85, side: THREE.DoubleSide,
            polygonOffset: true,
            polygonOffsetFactor: TILE_DEPTH_BIAS * 2,
            polygonOffsetUnits: TILE_DEPTH_BIAS * 2 });
        var ring = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.66, 24), ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.renderOrder = 2;                 // karo yamasından (1) sonra
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
        // KULLANICI KAMERAYI ELİNE ALDIĞI AN kip 'free' olur. ÖLÇÜLEN KUSUR:
        // _mode yalnız viewGlobe/viewSite içinde değişiyordu, yani açılıştaki
        // 'global' kipte kullanıcı tekerlekle yakınlaşsa bile kip 'global'
        // KALIYORDU; sonraki herhangi bir _resize (pencere boyutlama, tarayıcı
        // zoom'u, panel açılışı) kamerayı tüm-Dünya mesafesine geri fırlatıyordu
        // ve kullanıcının yakınlaşması siliniyordu. (_resize eskiden kameraya hiç
        // dokunmuyordu; bu bir regresyondu.) OrbitControls r128 'start' olayını
        // fare/dokunma/TEKERLEK etkileşimi başlarken yayımlar — vendor
        // OrbitControls-0.128.0.js: onMouseDown/onMouseWheel/onTouchStart ->
        // dispatchEvent(_startEvent). Düğme akışı etkilenmez: viewGlobe ve
        // viewSite _mode'u zaten yeniden kurar.
        this.controls.addEventListener('start', function () { self._mode = 'free'; });
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
        this._flyCamera(new global.THREE.Vector3(0, 0, 0), dirHint,
            globalViewDist(this.camera));
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
        // Hedef mesafesi (yüzeye çapalı). Alt sınır UÇUŞ VARLIĞINA bağlıdır:
        //
        // (a) ÖLÇÜLEN KUSUR — gerçek ölçekte 15,7 km'lik sondaj yayı sahne
        //     birimiyle 0,247 birimdir (1 birim = 63,71 km). Eski taban 10 birim
        //     (= 637 km) iken yay ekran yüksekliğinin ancak
        //     0,247 / (2·10·tan19°) = 0,247/6,887 = %3,6'sını kaplıyordu; kalkış,
        //     yanma sonu ve apoje işaretçileri ~10 piksellik tek bir kümede üst
        //     üste biniyordu. Yeni taban 3 birim (= 191 km):
        //     0,247 / (2·3·tan19°) = 0,247/2,066 = %12,0 -> yay 3,3 kat büyür ve
        //     işaretçiler ayrışır. ÖLÇEK BOZULMADI, abartma da yapılmadı; yalnız
        //     kamera yaya göre çerçeveleniyor.
        // (b) Eski gerekçe ("bulanık tek-doku yamasına dalınmaz") ARTIK ZAYIF:
        //     karo kapısı kendi sabitine taşındı (TILE_ACTIVE_ALT_M = 1500 km),
        //     bu çerçevede GIBS karoları (~500 m/px) yükleniyor — bakılan şey
        //     tek bir 4096 doku değil.
        // Uçuş YOKKEN eski 0,1R tabanı aynen kalır: saha seçiminde amaç coğrafi
        // bağlamdır (kıyı/yarımada tanınsın), çerçevelenecek bir yay yoktur.
        // 'Rakımı abart' anahtarı (varsayılan kapalı) hâlâ ayrı bir seçenektir;
        // bu taban onun yerini almaz. Üst sınır uzaya çıkan apojeleri sığdırır.
        // V307/FS-HARİTA: uçuş VARKEN taban artık kameranın yakın bakış
        // sınırıdır (CTRL_MIN_TARGET, ~21 m); çerçeve yolun kendi 3B sınır
        // yarıçapından gelir (yukarıdaki dist, 2,2 kat pay). Eski 3 birimlik
        // (191 km) taban bu formülü bağlıyordu: km ölçekli bir yol ekranın
        // birkaç pikseline sığıyordu.
        var floor = (this._flight ? CTRL_MIN_TARGET : GLOBE_R * 0.1);   // uçuşta ~21 m
        dist = clamp(dist, floor, GLOBE_R * 2.5);
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
        // ÖH D22 / OH-D18-10 — datum SÖZLEŞMESİ: varsayım değil, okuma.
        var datum = series.altitude_datum || ALT_DATUM_VARSAYILAN;
        if (ALT_DATUM_BILINEN.indexOf(datum) < 0) {
            // FAIL-CLOSED: tanınmayan datumda yolu çizmek, h0 kadar yanlış
            // bir uçuşu doğruymuş gibi göstermektir.
            if (this._onError) this._onError('flight_altitude_datum_unknown');
            return;
        }
        var n = series.time.length;
        var lat = new Array(n), lon = new Array(n), alt = new Array(n);
        // ÖH D19 / P4B3-21 — DATUM DÜZELTİLDİ.
        // Eski yorum "series.altitude deniz seviyesi ÜSTÜ irtifadır" diyor
        // ve h0'ı düşey eksende ATIYORDU (`alt[i] = series.altitude[i]`).
        // Oysa 6-DOF çözücüsü irtifayı FIRLATMA SAHASI ÜSTÜNDEN (AGL)
        // yayımlar — bunu kendisi de söylüyor
        // (`summary.apogee_datum = 'above_launch_site'`). Küre yüzeyi
        // deniz seviyesidir; AGL bir irtifayı deniz seviyesi datumuna
        // çizmek 1500 m'lik bir sahada uçuş yolunu araziye 1500 m
        // gömüyordu (kalkış noktası dağın içinde başlıyordu).
        // `enuToGeodetic` zaten h0 + up döndürüyor; artık ONU kullanıyoruz.
        for (var i = 0; i < n; i++) {
            // `enuToGeodetic` üçüncü konum bileşenini SAHA ÜSTÜ 'up' olarak
            // alır ve h0 + up döndürür; MSL bildiren bir dizi önce h0 kadar
            // indirgenir (aynı sayı iki kez sayılmasın).
            var up = (datum === ALT_DATUM_MSL)
                ? (series.altitude[i] - h0) : series.altitude[i];
            var g = enuToGeodetic(lat0, lon0, h0,
                series.north ? series.north[i] : 0,
                series.east ? series.east[i] : 0,
                up);
            lat[i] = g.lat; lon[i] = g.lon; alt[i] = g.alt;
        }
        this._flight = {
            // `alt` DENİZ SEVİYESİ datumundadır (h0 + AGL); okuma bloğu ve
            // apoje türetimi bu datumdan okur.
            altDatum: ALT_DATUM_MSL,
            // Girdi dizisinin datumu (okunan ya da sözleşme varsayılanı):
            // tüketici hangi sözleşmeye göre çizildiğini görebilsin.
            altSeriesDatum: datum,
            t: series.time.slice(), lat: lat, lon: lon, alt: alt,
            speed: series.speed ? series.speed.slice() : null,
            lat0: lat0, lon0: lon0, h0: h0,
            apogee: null, apogeeIdx: 0, downrange: null, range: 0
        };
        // Apoje türet (çözümden)
        var maxA = -1e9, ai = 0;
        for (var k = 0; k < n; k++) { if (alt[k] > maxA) { maxA = alt[k]; ai = k; } }
        this._flight.apogee = maxA; this._flight.apogeeIdx = ai;
        // ÖH D18 / P12aB4-10 — YATAY MESAFE ARTIK NOKTA BAZLI.
        // Eskiden yalnız TEK bir terminal sayı vardı (son nokta ile kalkış
        // noktası arasındaki yüzey kirişi) ve canlı okuma bloğunda oynatım
        // boyunca SABİT duruyordu: t = 0'da "Altitude 0 m" ile yan yana
        // "Menzil 8,2 km" yazıyordu. Dizi burada bir kez kurulur (her karede
        // Vector3 üretmemek için), terminal değer de AYNI diziden okunur —
        // yani "anlık" ile "çözüm sonu" tek tanımdan gelir.
        var first = latLonToVec3(lat[0], lon[0], GLOBE_R);
        var dr = new Array(n);
        for (var di = 0; di < n; di++) {
            dr[di] = latLonToVec3(lat[di], lon[di], GLOBE_R)
                .distanceTo(first) * M_PER_UNIT;
        }
        this._flight.downrange = dr;
        this._flight.range = dr[n - 1];   // yüzey kirişi, ÇÖZÜM SONUNDA
        this._buildFlightGeometry();
        this._playT = 0; this._playing = false;
        this._emitTime();
        this.viewSite();
    };

    /* V307/FS-İZLEME — YER İZİNİN YÜKSEKLİĞİ UÇUŞ ÖLÇEĞİNE BAĞLI.
       ÖLÇÜLEN KUSUR (9 Kas, üç örnek motor): yer izi sabit 1,0015 R
       yarıçapında, yani yüzeyden ~9,6 km YUKARIDA çiziliyordu. Apojesi
       2,9-5,7 km olan bir sondaj roketinde "yüzeye izdüşüm" uçuşun ÜSTÜNDE
       kalıyor, yakın kamerada yoldan kilometrelerce kopuk görünüyordu.
       Artık yer izi saha rakımındaki yüzeyin (kalkış noktasının yarıçapı)
       hemen üstündedir; pay yalnız derinlik çatışmasını önleyen bir GÖRÜNTÜ
       payıdır: uçuş kapsamının (apoje ile çözüm sonu yatay mesafesinin
       büyüğü) binde ikisi, en az 20 m, en çok eski 1,0015 R payı. Küre ağı
       (96 dilim) gerçek kürenin içinde kalır (kirişler), karo yamaları da
       taban yarıçapındadır; bu yüzden yüzeyin üstündeki pay her yerde
       ağın üstündedir. Sayı (konum) değişmez; yalnız çizim yüksekliği. */
    var YER_IZI_ORANI = 1.0015;            // eski sabit pay = üst sınır (~9,6 km)
    var YER_IZI_PAY_ORANI = 0.002;         // uçuş kapsamına oranla görüntü payı
    var YER_IZI_PAY_MIN_M = 20.0;          // en küçük görüntü payı [m]

    // Yer izinin çizim yarıçapı [sahne birimi] — TEK TANIM (izleme ekranının
    // düşey çizgisi de bunu okur: getTrackingContext.groundTrackRadius).
    LaunchSiteGlobe.prototype._flightGroundRadius = function () {
        var f = this._flight; if (!f) return GLOBE_R * YER_IZI_ORANI;
        var kapsamM = Math.max((f.apogee || 0) - (f.h0 || 0), f.range || 0, 0);
        var payM = clamp(YER_IZI_PAY_ORANI * kapsamM, YER_IZI_PAY_MIN_M,
            (YER_IZI_ORANI - 1.0) * R_EARTH_M);
        // Kalkış noktasıyla AYNI dönüşüm (rakım abartması saha rakımına da
        // uygulanır, yol çizimi gibi); pay abartılmaz.
        return GLOBE_R * (1.0 + this._exaggerate * (f.h0 || 0) / R_EARTH_M) + payM / M_PER_UNIT;
    };

    LaunchSiteGlobe.prototype._buildFlightGeometry = function () {
        var THREE = global.THREE, f = this._flight;
        if (!f) return;
        var n = f.t.length;
        this._pathPoints = new Array(n);
        this._groundPoints = new Array(n);
        var rYer = this._flightGroundRadius();
        for (var i = 0; i < n; i++) {
            var rr = GLOBE_R * (1.0 + this._exaggerate * f.alt[i] / R_EARTH_M);
            this._pathPoints[i] = latLonToVec3(f.lat[i], f.lon[i], rr);
            this._groundPoints[i] = latLonToVec3(f.lat[i], f.lon[i], rYer);
        }
        // orta nokta (çerçeveleme için): saha ile apoje arası
        var ap = this._pathPoints[f.apogeeIdx];
        this._pathMid = this._pathPoints[0].clone().add(ap).multiplyScalar(0.5);

        // Nokta bazlı teğetler — roketin BURUN yönü buradan gelir. (_pathTangent
        // yolun BÜTÜNÜ için tek bir teğet verir; o kamera çerçevelemesinde kalır,
        // araç yönelimi için kullanılamaz: kalkışta dik duran roket uç-uç teğetle
        // yan yatardı.) Merkezi fark P[i+1]-P[i-1], uçlarda tek yanlı fark.
        this._pathTangents = new Array(n);
        var prevTan = null;
        for (var ti = 0; ti < n; ti++) {
            var pa = this._pathPoints[Math.max(ti - 1, 0)];
            var pb = this._pathPoints[Math.min(ti + 1, n - 1)];
            var tan = pb.clone().sub(pa);
            // Ardışık özdeş nokta (çözücü duraklaması) -> sıfır uzunluk. Bir
            // önceki teğet taşınır; ilk noktada o da yoksa yüzey normali alınır
            // (kalkışta roket dik durur — doğru davranış, uydurma değil).
            if (tan.length() > 1e-9) tan.normalize();
            else if (prevTan) tan.copy(prevTan);
            else tan.copy(this._pathPoints[ti]).normalize();
            this._pathTangents[ti] = tan;
            prevTan = tan;
        }

        // Uçuş yolu — TAM rota her zaman soluk turuncu çizilir ("roketin
        // izleyeceği yol"); animasyonda ÜSTÜNE parlak bir iz (trail) katedilen
        // kısmı doldurur. İkisi de yalnız çözücü noktalarından gelir.
        var g1 = new THREE.BufferGeometry().setFromPoints(this._pathPoints);
        this._pathLine = new THREE.Line(g1, new THREE.LineBasicMaterial({
            color: srgb(0xff8c33), transparent: true, opacity: 0.34 }));
        this.flightGroup.add(this._pathLine);
        var g1b = new THREE.BufferGeometry().setFromPoints(this._pathPoints);
        this._trailLine = new THREE.Line(g1b, new THREE.LineBasicMaterial({
            color: srgb(0xffb066), transparent: true, opacity: 0.98 }));
        this._trailLine.geometry.setDrawRange(0, 2);
        this.flightGroup.add(this._trailLine);

        // Yer izi (soluk camgöbeği, kesikli) — çözüm ENU serisinin teğet-düzlem
        // jeodezik izdüşümü; Dünya dönüşü/Coriolis beyanı launch_site.NOT_MODELLED'de
        var g2 = new THREE.BufferGeometry().setFromPoints(this._groundPoints);
        this._groundLine = new THREE.Line(g2, new THREE.LineDashedMaterial({
            color: srgb(0x4fd0e0), transparent: true, opacity: 0.55,
            dashSize: GLOBE_R * 0.004, gapSize: GLOBE_R * 0.004 }));
        this._groundLine.computeLineDistances();
        this.flightGroup.add(this._groundLine);
        // V307/FS-İZLEME — YER İZİNİN GEÇİLEN KISMI. Kesikli soluk çizgi
        // yer izinin TAMAMIDIR (kalan yol dahil); üstüne kesiksiz parlak bir
        // çizgi oynatım anına kadar olan kısmı doldurur. Kural yoldaki iz
        // (_trailLine) ile aynıdır: aynı nokta dizisi (_groundPoints), aynı
        // indis (_seekTime). Yeni nokta üretilmez, yalnız çizim aralığı değişir.
        var g2b = new THREE.BufferGeometry().setFromPoints(this._groundPoints);
        this._groundTrailLine = new THREE.Line(g2b, new THREE.LineBasicMaterial({
            color: srgb(0x7fe9f5), transparent: true, opacity: 0.95, depthWrite: false }));
        this._groundTrailLine.renderOrder = 2;
        this._groundTrailLine.geometry.setDrawRange(0, 2);
        this.flightGroup.add(this._groundTrailLine);

        // Olay işaretçileri (kalkış/yanma sonu/apoje/bitiş) — çözümden türetildi
        this._buildEventMarkers();

        // Roket işaretçisi (animasyon boyunca ilerler) — ÖNCEDEN 12x12 segmentli
        // beyaz bir küreydi: hareket eden şey "roket" değil, ayırt edilemez bir
        // benekti. Artık tanınabilir bir araç silueti: burun konisi + gövde +
        // dört kanat, dikey uzanım 0,87 birim (kanat dibi -0,37 ... burun tepesi
        // +0,50), en 0,44 ve burun +Y'de.
        //
        // ROKET EKRAN-SABİT BİR SEMBOLDÜR — fiziksel ölçek iddiası TAŞIMAZ.
        // Saha iğnesi (k = 0,013) ve olay noktaları (k = 0,0075) ile aynı sınıfta,
        // _updateScalables her karede kamera mesafesiyle çarpar. Ekran oranı
        // MESAFEDEN BAĞIMSIZDIR: uzanım·k / (2·tan(FOV/2)), FOV = 38°.
        // ÖLÇÜLEN (800 px yükseklikli tuval):
        //   eski beyaz küre : 2,00 · 0,006 -> %1,74 -> 13,9 px (benek)
        //   yeni siluet, k = 0,006 : 0,87 · 0,006 -> %0,76 -> 6,1 x 3,1 px
        //   yeni siluet, k = 0,020 : 0,87 · 0,020 -> %2,53 -> 20,2 x 10,2 px
        // Yani k KORUNSAYDI düzeltilmek istenen kusur KÖTÜLEŞİRDİ (13,9 -> 6,1 px);
        // eski yorumun "piksel boyutu değişmez" iddiası ölçülmemişti ve yanlıştı.
        // k bu yüzden bilinçli büyütüldü: 20,2 px, olay noktasının (17,4 px) ve
        // saha iğnesinin (15,1 px) sınıfında — koni ve kanatlar ayırt edilebilir.
        // Bu bir "ölçek yalanı" DEĞİLDİR: rakım abartması (_exaggerate) hâlâ
        // varsayılan 1,0 ve yolun/işaretçilerin KONUMU birebir çözümden gelir;
        // büyüyen tek şey sembolün kendisidir.
        // Sahte egzoz/alev/duman EKLENMEZ: çözücü egzoz akısı üretmiyor,
        // çizilen her şey veriden gelmek zorunda.
        var rk = new THREE.Group();
        var body = new THREE.Mesh(
            new THREE.CylinderGeometry(0.10, 0.10, 0.70, 12),
            new THREE.MeshBasicMaterial({ color: srgb(0xd8dde2) }));
        body.position.y = 0.0;                 // gövde [-0,35 , +0,35]
        rk.add(body);
        var nose = new THREE.Mesh(
            new THREE.ConeGeometry(0.10, 0.30, 12),
            new THREE.MeshBasicMaterial({ color: srgb(0xff8c33) }));
        nose.position.y = 0.35;                // koni merkezi -> tepe +0,50'de
        rk.add(nose);
        // Dört kanat 90°'lik adımlarla DÖNGÜYLE kurulur (dört kopya blok değil);
        // geometri/malzeme paylaşılır. Konum yarıçapta 0,14 dışa kaydırılır,
        // rotation.y ile kanat düzlemi radyal doğrultuya çevrilir.
        var finGeo = new THREE.BoxGeometry(0.016, 0.22, 0.16);
        var finMat = new THREE.MeshBasicMaterial({ color: srgb(0x9fb3c0) });
        for (var fi = 0; fi < 4; fi++) {
            var fang = fi * Math.PI / 2;
            var fin = new THREE.Mesh(finGeo, finMat);
            fin.position.set(Math.sin(fang) * 0.14, -0.26, Math.cos(fang) * 0.14);
            fin.rotation.y = fang;
            rk.add(fin);
        }
        this._rocket = rk;
        this.flightGroup.add(rk);
        this._registerScalable(rk, 0.020);   // ekran-sabit roket sembolü (yukarıdaki ölçüm)
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
                // srgb(): ham hex sRGB çıkışında açılırdı; lejant noktası
                // (launch_site.html renderEvents -> dot.style.background) AYNI
                // hex'i CSS ile bastığı için eşleşme lineere çevirince tutar.
                new THREE.MeshBasicMaterial({ color: srgb(color) }));
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
        // V307/FS-KÜÇÜK (kalem 1): paraşüt açılışı. Zaman sunucunun olay
        // listesinden (launch_site.html sözleşmenin `deploy` olayını
        // opts.deployTime'a verir; olay yoksa null → işaretçi yok). Konum,
        // yanma sonu işaretçisiyle aynı kural: çizilen yolun o zamana
        // kadarki son örneği (sayı ve irtifa olay listesinde sunucudan).
        if (this.opts.deployTime != null) {
            var dt = this.opts.deployTime, di = -1;
            for (var k = 0; k < f.t.length; k++) { if (f.t[k] <= dt) di = k; }
            add(di, 0xff7eb6, 'deploy', this);           // paraşüt açılışı
        }
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
            var c = this.flightGroup.children[0];
            // Roket artık bir Group (koni + gövde + dört kanat): geometri ve
            // malzeme ALT ÖGELERDE duruyor. traverse olmadan her yeniden kurulan
            // uçuşta (rakım abartması değiştikçe) GPU tamponu sızardı.
            c.traverse(function (o) {
                if (o.geometry) o.geometry.dispose();
                if (o.material) o.material.dispose();
            });
            // children[0] + remove: önce pop edilirse remove() ögeyi listede
            // bulamaz ve parent'ı BOŞALTMAZ; aşağıdaki _scalables süzgeci de
            // parent'a baktığı için ölü kayıtlar listede birikirdi.
            this.flightGroup.remove(c);
        }
        this._flight = null; this._pathPoints = null; this._groundPoints = null;
        this._pathTangents = null;
        this._events = null; this._rocket = null; this._pathLine = null;
        this._trailLine = null; this._groundLine = null; this._pathMid = null;
        this._groundTrailLine = null;   // V307/FS-İZLEME
        this._playing = false; this._playT = 0;
        // Ölçeklenebilir işaretçi listesinden uçuşa ait (artık sahnede olmayan)
        // ögeleri temizle; kalıcı saha iğnesi (parent hâlâ var) korunur.
        if (this._scalables)
            this._scalables = this._scalables.filter(function (s) { return !!s.obj.parent; });
        // NOT: GIBS karo yamaları BİLEREK burada silinmez — arazi uçuş yolundan
        // bağımsızdır (her yeni uçuşta titreme/yeniden-yükleme olmaz). Bellek
        // _pruneTiles (LRU) ile yönetilir; tam temizlik yalnız dispose()'ta.
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
        var THREE = global.THREE;
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
        // Burun yol teğetine bakar: aynı i/j çiftinin teğetleri a ile karıştırılır.
        // Geçici nesneler ÖRNEK BAŞINA bir kez kurulur (_orient) — bu yol her
        // karede geçildiği için burada new Vector3/Quaternion çöp üretirdi.
        if (this._pathTangents) {
            var or = this._orient || (this._orient = {
                up: new THREE.Vector3(0, 1, 0),
                tan: new THREE.Vector3(),
                q: new THREE.Quaternion()
            });
            or.tan.copy(this._pathTangents[i]).lerp(this._pathTangents[j], a);
            // Karışım sıfıra düşerse (ters yönlü iki teğet) yönelim korunur:
            // uydurma bir yön atamaktansa son geçerli yönde kalınır.
            if (or.tan.length() > 1e-9) {
                or.tan.normalize();
                or.q.setFromUnitVectors(or.up, or.tan);
                this._rocket.quaternion.copy(or.q);
            }
        }
        this._curIdx = i;
        // Parlak iz: kat edilen kısmı doldur (tam rota soluk olarak zaten görünür)
        if (this._trailLine) {
            var drawn = Math.max(2, Math.floor(i + a) + 1);
            this._trailLine.geometry.setDrawRange(0, drawn);
            // V307/FS-İZLEME: yer izinin geçilen kısmı aynı indise kadar.
            if (this._groundTrailLine)
                this._groundTrailLine.geometry.setDrawRange(0, drawn);
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
        // ÖH D18 / P12aB4-10: canlı (indise bağlı) ve terminal (tüm çözüm)
        // alanlar artık ADLARIYLA ayrılıyor. `downrange` indisle değişir;
        // `apogee`/`range` tüm çözümün özetidir ve tüketici onları AYRI bir
        // "uçuş özeti" bloğunda basar — canlı satır kalıbında değil.
        this._onTime({
            t: this._playT, tMax: T, frac: T > 0 ? this._playT / T : 0,
            playing: this._playing,
            alt: f.alt[i], lat: f.lat[i], lon: f.lon[i],
            // ÖH D22 / OH-D18-10 — `alt` ve `apogee` DENİZ SEVİYESİ
            // datumundadır (çizim küre yüzeyinden ölçer). Çözücünün kendi
            // apojesi ise SAHA ÜSTÜdür (`apogee_datum`). İki sayı aynı
            // sözcükle ("İrtifa"/"Apoje") gösterilince 1500 m'lik bir sahada
            // 1500 m'lik sahte bir fark doğuyordu. Kardeş alanlar TEK
            // kaynaktan (alt − h0) türetilir; datum adı da yanlarında gider.
            altDatum: f.altDatum, altAgl: f.alt[i] - f.h0,
            siteElevation: f.h0,
            speed: f.speed ? f.speed[i] : null,
            downrange: f.downrange ? f.downrange[i] : null,
            apogee: f.apogee, apogeeAgl: f.apogee - f.h0, range: f.range
        });
    };

    /* V307/FS-İZLEME — GÖREV İZLEME EKRANINA TEK DIŞA AÇMA.
       launch_site_tracking.js sahneye kendi nesnesini (roketten yere düşey
       çizgi) ekler, izleme kiplerinde kamerayı yönetir ve oynatım anını
       okur. Gereken iç öğeler TEK bir yöntemle, erişimci olarak verilir;
       izleme modülü küre içindeki adlara (_rocket, _flight, _flyCameraPos)
       doğrudan uzanmaz. SAYI ÜRETMEZ: konum çözücü serisinden kurulan
       çizimden (_flight, roketin çizilmiş konumu) okunur. Küre kurulamadıysa
       (WebGL yok) dosya sonundaki genel koruma bu yöntemi de null döndürür. */
    LaunchSiteGlobe.prototype.getTrackingContext = function () {
        var self = this;
        return {
            THREE: global.THREE,
            scene: this.scene,
            camera: this.camera,
            controls: this.controls,
            globeRadius: GLOBE_R,
            metersPerUnit: M_PER_UNIT,
            groundTrackRadius: function () { return self._flightGroundRadius(); },
            latLonToVec3: latLonToVec3,
            flight: function () { return self._flight; },
            rocketPosition: function () { return self._rocket ? self._rocket.position : null; },
            playTime: function () { return self._playT; },
            flyTo: function (pos, target) { self._flyCameraPos(pos, target); }
        };
    };

    // ---- Ölçek / kamera-yükseklik göstergesi -------------------------------
    /* Ekrana GERÇEKTEN çizilmiş (mesh'i olan) karo sayısı — TEK TANIM.
       Negatif önbellek girdileri ve başarısız karolar sayılmaz.
       getScaleInfo() ile getTileInfo() aynı kaynaktan beslenir; yoksa iki
       gösterge birbiriyle çelişebilir (ÖH D18 / P12aB4-07). */
    LaunchSiteGlobe.prototype._drawnTileCount = function () {
        var n = 0;
        if (this._tiles) {
            // V307/FS-HARİTA-KÜRE: ZEMİN karoları. Paket bindirmesi zemin
            // dokusu değildir (çözünürlük/künye notları zemin içindir);
            // sayısı getTileInfo().pack'te ayrı yayımlanır.
            this._tiles.forEach(function (e) { if (e && e.mesh && !e.paket) n += 1; });
        }
        return n;
    };

    LaunchSiteGlobe.prototype.getScaleInfo = function () {
        var mPerPx = this._metersPerPixel();
        var camAltM = this.camera.position.length() * M_PER_UNIT - R_EARTH_M;
        // ÖH D18 / P12aB4-07: "küresel doku ~9 km hücre" notu, ekranda
        // GİBS karosu (~500 m) çizilmediği sürece doğrudur; karo çizilirken
        // basılırsa ürün aynı anda 18 kat farklı iki çözünürlük beyan eder.
        // ÖLÇÜLDÜ: 0-400 km bandında dört kamera yüksekliğinde de iki beyan
        // yan yana duruyordu (karo kapısı 1.500 km, not kapısı 400 km).
        // Not artık YALNIZ gerçekten taban dokusuna bakılırken çıkar;
        // karolar çevrimdışı/başarısız olup düştüğünde geri gelir.
        var tilesDrawn = this._drawnTileCount() > 0;
        // harita-detay K4 (tasarım §4.1-4): büyütme notunun koşulu "karo
        // çizildi mi" DEĞİL, "ekran merkezindeki en ince çizilen dokunun
        // m/px'i > TEXTURE_MAG_RATIO x ekran m/px mi". Doku m/px'i z
        // seçiminin kendi formülüdür (TILE_Z0_MPP / 2^z).
        var mrk = tilesDrawn ? this._merkezDoku : null;
        var texMpp = mrk ? TILE_Z0_MPP / Math.pow(2, mrk.z) : null;
        return {
            metersPerPixel: mPerPx,
            camAltitudeM: camAltM,
            tilesDrawn: tilesDrawn,
            textureCoarse: camAltM < TEXTURE_NOTE_ALT_M && !tilesDrawn,
            textureLayer: mrk ? mrk.layer : null,
            textureMpp: texMpp,
            textureMagnified: !!(texMpp && mPerPx > 0 && texMpp > TEXTURE_MAG_RATIO * mPerPx)
        };
    };

    // ---- GIBS uydu karo yaması (patch mesh) --------------------------------
    // Ön yüz durum kancası: patch aktif mi + atıf anahtarı + kaç karo düştü.
    //
    // ÖH D21 / P12aB4-19 — ÖLÇÜLEN KUSUR: bu blok "HTML/i18n bunu okuyarak …
    // çevrimdışı notunu gösterir" diyordu ama iki alanın da GERÇEK tüketicisi
    // yoktu: `attribution` hiçbir yerden okunmuyor (HTML sabit i18n metnini
    // basıyordu — aynı cümlenin İKİ kaynağı), `anyFail` yalnız önbellek
    // imzasının bir bitiydi ve ekranda çevrimdışı notu HİÇ görünmüyordu.
    // Artık: atıf METNİ tek kaynakta (i18n sözlüğü) kalır, bu blok yalnız
    // KATMANIN künye ANAHTARINI yayımlar; düşen karo sayısı canlı ölçümdür ve
    // launch_site.html #ls-tile-offline notunu ona bağlar.
    LaunchSiteGlobe.prototype.getTileInfo = function () {
        // ÖH D17 / P12aB4-04: negatif önbellek girdileri de Map'te durduğu
        // için "kaç karo var" artık Map boyutu DEĞİL, ekrana gerçekten
        // çizilmiş (mesh'i olan) karo sayısıdır. Başarısızlar ayrı sayılır;
        // sayı uydurulmaz.
        var cizilen = this._drawnTileCount(), basarisiz = 0, paketCizili = 0;
        if (this._tiles) {
            this._tiles.forEach(function (e) {
                if (e && e.paket) { if (e.mesh) paketCizili += 1; return; }
                if (e && !e.mesh && e.failed) basarisiz += 1;
            });
        }
        var gl = this.renderer && this.renderer.getContext ? this.renderer.getContext() : null;
        var ozellik = (gl && gl.getContextAttributes) ? gl.getContextAttributes() : null;
        // Künye, ekran merkezinde ÇİZİLEN katmanınkidir (paketli ya da
        // GIBS); merkezde karo yoksa varsayılan (GIBS) katmanın anahtarı.
        var katman = (cizilen > 0 && this._merkezDoku) ? this._merkezDoku.layer : TILE_LAYER;
        return {
            active: cizilen > 0,
            layer: katman,
            // Metin değil ANAHTAR: çeviri tek kaynakta (i18n_launch_site.js).
            attributionKey: TILE_ATTRIBUTION_KEY[katman] || null,
            // Oturum boyunca yapışkan bayrak — önbellek imzası için.
            anyFail: !!this._tileAnyFail,
            count: cizilen,
            // Şu anki karo kümesinde düşen karo sayısı (canlı ölçüm; ekrandaki
            // çevrimdışı notu buna bağlıdır, yapışkan bayrağa değil).
            failedCount: basarisiz,
            // V307/FS-HARİTA-KÜRE: indirilen paket bindirmesi. active = bu
            // turda çiziliyor VE en az bir karosu ekranda; künye anahtarı
            // yalnız o zaman basılır (paket kapsamı dışında atıf yok).
            pack: {
                active: !!(this._paketEtkin && paketCizili > 0),
                count: paketCizili,
                z: this._paketZ,
                layer: TILE_LAYER_PACK,
                attributionKey: TILE_ATTRIBUTION_KEY[TILE_LAYER_PACK] || null
            },
            // R7 düzeninin dayandığı stencil arabelleği bağlamda var mı
            // (ölçüm/teşhis; yoksa en-ince-kazanır kuralı uygulanamaz).
            stencil: !!(ozellik && ozellik.stencil)
        };
    };

    // K5a — ağ anahtarı (kalıcı, bu tarayıcıda; varsayılan KAPALI).
    LaunchSiteGlobe.prototype.getTileNetwork = function () { return tileAgAcik(); };

    // Anahtarı yazar ve GERÇEKTE kalan durumu döndürür (yazılamadıysa
    // false). Açılınca düşmüş karoların negatif önbelleği temizlenir ki
    // rızayla yeniden istensinler; kapanınca çizilmiş karolar kalır (yerel
    // veridir, dış istek değildir).
    LaunchSiteGlobe.prototype.setTileNetwork = function (acik) {
        tileAgYaz(acik === true);
        var simdi = tileAgAcik();
        if (simdi && this._tiles) {
            var silinecek = [];
            this._tiles.forEach(function (e, k) { if (e && e.failed && !e.mesh) silinecek.push(k); });
            for (var i = 0; i < silinecek.length; i++) this._tiles.delete(silinecek[i]);
        }
        return simdi;
    };

    // Kameranın baktığı bölgeye gereken karo bloğunu belirle, eksikleri yükle,
    // uzaktakileri LRU ile buda. Yalnız yakın zoomda (kamera < 1500 km,
    // TILE_ACTIVE_ALT_M) çalışır; her karede DEĞİL, TILE_UPDATE_MS kısmasıyla.
    LaunchSiteGlobe.prototype._updateTilePatch = function () {
        var now = performance.now();
        if (now < this._tileNextT) return;
        this._tileNextT = now + TILE_UPDATE_MS;

        var info = this.getScaleInfo();
        if (!info) return;
        // Uzaktaysak yeni karo yükleme; mevcutlar LRU ile budanır (aşağıda).
        if (!(info.camAltitudeM < TILE_ACTIVE_ALT_M)) {
            this._detayNotu(false);
            this._paketKapat();
            this._pruneTiles();
            return;
        }
        var mpx = info.metersPerPixel;
        if (!(mpx > 0)) return;

        // z seçimi: ekvator m/px @ z0 = TILE_Z0_MPP; z = log2(z0/mpx).
        var z = Math.round(Math.log2(TILE_Z0_MPP / mpx));
        var zHam = z;                      // kırpılmamış: ayrıntı katmanı için
        z = clamp(z, TILE_MIN_ZOOM, TILE_MAX_ZOOM);

        // Kameranın baktığı yüzey noktası = ekran merkezinin ODAĞI (_odak):
        // hedef yüzeyde/üstündeyse hedefin kendisi, hedef Dünya merkezindeyse
        // (açılış ve 'Tüm Dünya' kipi, tekerlekle yaklaşma) görüş ışınının
        // yüzeyi deldiği nokta. V307/FS-HARİTA: eskiden hedef merkezdeyse
        // burada DÖNÜLÜYORDU ve o kipte hiçbir karo istenmiyordu.
        var od = this._odak();
        if (!od.point || od.point.length() < 1e-3) { this._pruneTiles(); return; }
        var c = vec3ToLatLon(od.point);

        // P5B4-30: geometri SUNUCUDAN. Yüklenmediyse bu turda karo
        // istenmez (fail-closed) ve bir sonraki tur için istenir.
        var lv = tileLevel(z);
        if (!lv) { tileGeomYukle(); this._pruneTiles(); return; }
        // K4 kaynak sırası: paketli katman (ağsız) her zaman, tavanına
        // kırpılmış z'de; GIBS yalnız z paketli tavanın üstündeyse. Paketli
        // tavan bilinmiyorsa (sunucu yayımlamadı) yalnız GIBS (eski yol).
        // V307/FS-HARİTA: istenen z bluemarble tavanını aşıyorsa ve ayrıntı
        // katmanı sunucudan okunduysa GIBS düzeyi o katmandan, kendi tavanına
        // kırpılmış z'de istenir (bluemarble z7 + ayrıntı aynı anda değil).
        if (_paketliTavan !== null) this._patchKatmani(TILE_LAYER_PACKAGED, Math.min(z, _paketliTavan), c);
        var zDetay = (_detayTavan !== null && zHam > TILE_MAX_ZOOM)
            ? Math.min(zHam, _detayTavan) : null;
        if (zDetay !== null && tileLevel(zDetay)) this._patchKatmani(TILE_LAYER_DETAIL, zDetay, c);
        else if (_paketliTavan === null || z > _paketliTavan) this._patchKatmani(TILE_LAYER, z, c);
        // V307/FS-HARİTA-KÜRE: indirilen paket bindirmesi (zeminden bağımsız
        // kendi tavanıyla, en çok z15; yalnız kurulu paket kapsamında).
        this._paketKatmani(c, zHam, mpx);
        this._merkezDoku = this._merkezDokusu(c);
        this._istenenZ = (zDetay !== null && tileLevel(zDetay)) ? zDetay : z;
        // V307/FS-HARİTA: rıza kapalıyken ekran merkezinin GIBS karosu
        // reddedildiyse (önbellekte yok, dış istek yapılmadı) kullanıcıya
        // nedenini ve ayarın yerini söyleyen not. Koşul ölçümdür: merkezde
        // gereken GIBS karosu negatif önbellekte (failed) durur.
        // Not yalnız eksik doku GERÇEKTEN büyütülüyorken açılır: ekran
        // merkezindeki en ince çizilen dokunun m/px'i ekranın
        // TEXTURE_MAG_RATIO katından kaba (getScaleInfo büyütme ölçütüyle aynı;
        // hiç karo yoksa taban doku, yani büyütülmüş sayılır).
        var gerekenKatman = (this._istenenZ > TILE_MAX_ZOOM) ? TILE_LAYER_DETAIL : TILE_LAYER;
        var gibsGerekli = _paketliTavan === null || this._istenenZ > _paketliTavan;
        var mrk = this._merkezDoku;
        var dokuMpp = mrk ? TILE_Z0_MPP / Math.pow(2, mrk.z) : Infinity;
        this._detayNotu(gibsGerekli && !tileAgAcik() && dokuMpp > TEXTURE_MAG_RATIO * mpx
                        && this._merkezKarosuDustu(gerekenKatman, this._istenenZ, c));
        this._pruneTiles();
    };

    // Ekran merkezini (c) kapsayan, verilen katman/z karosu düştü mü
    // (negatif önbellekte, mesh'siz)? Geometri yoksa false (iddia yok).
    LaunchSiteGlobe.prototype._merkezKarosuDustu = function (layer, z, c) {
        var lv = tileLevel(z);
        if (!lv) return false;
        var tx = (((Math.floor((c.lon + 180.0) / lv.span)) % lv.mw) + lv.mw) % lv.mw;
        var ty = Math.floor((90.0 - c.lat) / lv.span);
        var e = this._tiles.get(layer + ':' + z + ':' + tx + ':' + ty);
        return !!(e && e.failed && !e.mesh);
    };

    /* V307/FS-HARİTA — RIZA KAPALI NOTU (küre üstünde, alt orta).
       ÖLÇÜLDÜ: rıza kapalıyken yakın zoomda ekranda yalnız sağ alt not
       kutusunun içinde, kaydırılması gereken bir satır vardı; ayarın
       kendisi aynı kutunun altında, çoğu pencerede görünür alanın dışında
       kalıyordu. Not metni i18n sözlüğünden gelir (data-i18n, dil değişince
       I18N.apply tazeler); I18N yoksa not hiç basılmaz (ham anahtar ya da
       ikinci bir İngilizce kopya yok). Düğme rızayı AÇMAZ: sayfadaki mevcut
       ağ anahtarını görünür alana getirip odaklar, kararı kullanıcı o
       anahtarın gizlilik açıklamasıyla birlikte verir. Anahtar sayfada
       yoksa düğme kurulmaz. */
    var TILE_NETWORK_CONTROL_ID = 'ls-tile-network';
    LaunchSiteGlobe.prototype._detayNotu = function (goster) {
        var el = this._detayNotuEl;
        if (!goster) { if (el) el.style.display = 'none'; return; }
        var I = global.I18N, doc = global.document;
        if (!el) {
            if (!I || !I.applyTo || !doc || !doc.createElement || !this.container) return;
            el = doc.createElement('div');
            el.id = 'ls-tile-detail-off';
            el.setAttribute('role', 'status');
            var st = el.style;
            st.position = 'absolute'; st.zIndex = '15'; st.left = '50%'; st.bottom = '14px';
            st.transform = 'translateX(-50%)'; st.maxWidth = 'min(560px, 56%)';
            st.display = 'flex'; st.alignItems = 'center'; st.gap = '10px';
            st.padding = '8px 12px'; st.borderRadius = '8px'; st.fontSize = '12px';
            st.lineHeight = '1.45'; st.cursor = 'default';
            st.color = 'var(--hd-ink, #cfe8f2)'; st.background = 'rgba(6,14,26,0.86)';
            st.border = '1px solid var(--hd-line, rgba(0,229,255,0.18))';
            st.borderLeft = '3px solid var(--hd-orange, #ff8c33)';
            var m = doc.createElement('span');
            m.setAttribute('data-i18n', 'site.tileDetailOffHint');
            el.appendChild(m);
            var cb = doc.getElementById ? doc.getElementById(TILE_NETWORK_CONTROL_ID) : null;
            if (cb) {
                var b = doc.createElement('button');
                b.type = 'button';
                b.className = 'ls-iconbtn';
                b.style.width = 'auto'; b.style.padding = '0 10px'; b.style.whiteSpace = 'nowrap';
                b.setAttribute('data-i18n', 'site.tileDetailOffButton');
                b.addEventListener('click', function () {
                    var hedef = doc.getElementById(TILE_NETWORK_CONTROL_ID);
                    if (!hedef) return;
                    if (hedef.scrollIntoView) hedef.scrollIntoView({ block: 'center' });
                    try { hedef.focus({ preventScroll: true }); } catch (e) { hedef.focus(); }
                });
                el.appendChild(b);
            }
            this.container.appendChild(el);
            I.applyTo(el);
            this._detayNotuEl = el;
        }
        el.style.display = 'flex';
    };

    /* V307/FS-HARİTA-KÜRE — PAKET BİNDİRMESİNİN AKIŞI (her yama turunda).
       Kurulu paket imzası değiştiyse (indirildi/silindi) eski bindirme
       karoları atılır ve URL sürümü tazelenir. Bindirme, odak çevresindeki
       yama bir kurulu paket kutusuyla kesişiyorsa ve o kutunun kısa kenarı
       ekran genişliğinden (ekran px × m/px) büyük ya da eşitse çizilir: paket
       ekranı dolduramadığı uzak ölçekte kutunun kenarı dikdörtgen bir leke
       gibi görünürdü; bu ölçek paket kutusunun kendi boyutundan gelir (100 km
       yarıçaplı sahada ~139 m/px, Sinop'ta z9), sabit bir eşik değildir.
       Düzey min(istenen z, paket tavanı); zemin tavanı (z11/z5) değişmez. */
    LaunchSiteGlobe.prototype._paketKatmani = function (c, zHam, mpx) {
        var depo = paketDeposuOku();
        var imza = depo ? depo.imza : '';
        if (imza !== this._paketImza) {
            this._paketKarolariniSil();
            this._paketImza = imza;
            _katmanUrlSurumu[TILE_LAYER_PACK] = fnv32(String(global.HRMA_APP_VERSION || '') + '|' + imza);
        }
        this._paketKutular = depo ? depo.kutular : [];
        var etkin = false, zP = null;
        if (depo && depo.kutular.length && _paketTavan !== null && this._paketKaldir
                && this._paketAdimDeg > 0) {
            zP = Math.min(zHam, _paketTavan);
            var lv = tileLevel(zP);
            if (lv) {
                var R = Math.min(TILE_PATCH_R, TILE_PATCH_R_MAX);
                var cx = Math.floor((c.lon + 180.0) / lv.span);
                var cy = Math.floor((90.0 - c.lat) / lv.span);
                var yama = [-180.0 + (cx - R) * lv.span, 90.0 - (cy + R + 1) * lv.span,
                            -180.0 + (cx + R + 1) * lv.span, 90.0 - (cy - R) * lv.span];
                var ekranM = (this.container.clientWidth || 800) * mpx, uygun = [];
                for (var i = 0; i < depo.kutular.length; i++) {
                    var b = depo.kutular[i];
                    if (!kutuKesisim(b, yama)) continue;
                    var dogu = deg2rad(b[2] - b[0]) * R_EARTH_M * Math.cos(deg2rad((b[1] + b[3]) / 2));
                    var kuzey = deg2rad(b[3] - b[1]) * R_EARTH_M;
                    if (Math.min(dogu, kuzey) >= ekranM) uygun.push(b);
                }
                etkin = uygun.length > 0;
                if (etkin) this._patchKatmani(TILE_LAYER_PACK, zP, c, uygun);
            }
        }
        this._paketEtkin = etkin;
        this._paketZ = etkin ? zP : null;
        if (this._paketGroup) this._paketGroup.visible = etkin;
    };

    LaunchSiteGlobe.prototype._paketKapat = function () {
        this._paketEtkin = false;
        this._paketZ = null;
        if (this._paketGroup) this._paketGroup.visible = false;
    };

    // Bütün paket bindirmesi karolarını (çizilmiş ya da düşmüş) at.
    LaunchSiteGlobe.prototype._paketKarolariniSil = function () {
        if (!this._tiles) return;
        var sil = [];
        this._tiles.forEach(function (e, k) { if (e && e.paket) sil.push(k); });
        for (var i = 0; i < sil.length; i++) {
            this._disposeTileEntry(this._tiles.get(sil[i]));
            this._tiles.delete(sil[i]);
        }
    };

    // Bir katmanın (layer) z düzeyinde merkez etrafı (2R+1)² karo bloğu:
    // eksikleri yükle, mevcutları LRU'da tazele, çizilmemiş karonun
    // ebeveynini (yedek) tut. V307/FS-HARİTA-KÜRE: `kutular` verilirse
    // (paket katmanı) yalnız bu kutulardan biriyle kesişen karo istenir.
    LaunchSiteGlobe.prototype._patchKatmani = function (layer, z, c, kutular) {
        var lv = tileLevel(z);
        if (!lv) return;
        var span = lv.span, mw = lv.mw, mh = lv.mh;
        var cx = Math.floor((c.lon + 180.0) / span);
        var cy = Math.floor((90.0 - c.lat) / span);
        var R = Math.min(TILE_PATCH_R, TILE_PATCH_R_MAX);

        for (var dy = -R; dy <= R; dy++) {
            var ty = cy + dy;
            if (ty < 0 || ty >= mh) continue;             // kutup kırpma (singularity yok)
            for (var dx = -R; dx <= R; dx++) {
                var tx = (((cx + dx) % mw) + mw) % mw;      // tarih çizgisi sarmalama
                if (kutular) {
                    var karo = [-180.0 + tx * span, 90.0 - (ty + 1) * span,
                                -180.0 + (tx + 1) * span, 90.0 - ty * span], kesen = false;
                    for (var ki = 0; ki < kutular.length && !kesen; ki++)
                        kesen = !!kutuKesisim(karo, kutular[ki]);
                    if (!kesen) continue;
                }
                var key = layer + ':' + z + ':' + tx + ':' + ty;
                var entry = this._tiles.get(key);
                if (entry && entry.failed) {
                    // Negatif önbellek (ÖH D17 / P12aB4-04): geri çekilme
                    // süresi dolmadan yeniden istenmez; TILE_FAIL_MAX denemeden
                    // sonra retryAt = Infinity ile kalıcı olarak susar.
                    if (performance.now() >= entry.retryAt) {
                        this._tiles.delete(key);
                        this._buildTilePatch(layer, z, tx, ty);
                        var yeni = this._tiles.get(key);
                        if (yeni) yeni.fails = entry.fails;
                    } else {
                        // ÖH D30 · OH-D19-27 — NEGATİF GİRDİ DE LRU'DA TAZELENİR.
                        // ÖLÇÜLDÜ (a2/once.json: OHD1927_failed_lru_tazeleme = 0):
                        // başarısız karo girdisi `_touchTile` görmüyordu, yani
                        // Map'in insertion-order sırasında EN ESKİ kalıyordu ve
                        // `_pruneTiles` cap aşımında İLK onu siliyordu. Girdi
                        // silinince `fails` sayacı da gidiyor: kamera aynı
                        // karoya bakmaya devam ederken deneme sayacı sıfırlanıp
                        // TILE_FAIL_MAX susturması hiç devreye girmiyor, düşen
                        // karo sonsuza dek yeniden isteniyordu. Geri çekilme
                        // penceresi İÇİNDEki girdi de bakılan karo kümesinin
                        // parçasıdır — dokunulur; yeniden istek YAPILMAZ
                        // (retryAt kapısı yukarıdaki dalda durur).
                        this._touchTile(key);
                    }
                } else if (entry) this._touchTile(key);
                else this._buildTilePatch(layer, z, tx, ty);
                var son = this._tiles.get(key);
                if (!(son && son.mesh)) this._ebeveynTut(layer, z, tx, ty);
            }
        }
    };

    // Ebeveyn yedeği: çizilmemiş (yükleniyor/başarısız) karonun çizilmiş en
    // yakın atasını LRU'da tazele (budanmasın, çizilmeye devam etsin). Yeni
    // istek ATILMAZ; ata yalnız zaten çizilmişse tutulur.
    // V307/FS-HARİTA: ata önce AYNI katmanda, sonra daha kaba katmanlarda
    // (bluemarble, paketli) aranır. Ayrıntı katmanı z > 7'de istendiği için
    // kendi z <= 7 atası yoktur; yüklenirken altındaki bluemarble/paketli
    // karo budanmasın diye. Bütün katmanlar aynı EPSG:4326 matris
    // geometrisini paylaşır (288/2^z), (x/2, y/2) ilişkisi her birinde geçerli.
    var KATMAN_SIRASI = [TILE_LAYER_DETAIL, TILE_LAYER, TILE_LAYER_PACKAGED];
    LaunchSiteGlobe.prototype._ebeveynTut = function (layer, z, tx, ty) {
        for (var pz = z - 1; pz >= TILE_PARENT_MIN_ZOOM; pz--) {
            tx = Math.floor(tx / 2); ty = Math.floor(ty / 2);
            var e = this._tiles.get(layer + ':' + pz + ':' + tx + ':' + ty);
            if (e && e.mesh) { this._touchTile(layer + ':' + pz + ':' + tx + ':' + ty); return; }
            // Paket bindirmesinin atası yalnız kendi katmanındadır (zemin
            // karosu bindirmenin yedeği değildir; zemin zaten çizilir).
            if (layer === TILE_LAYER_PACK) continue;
            for (var i = 0; i < KATMAN_SIRASI.length; i++) {
                var L = KATMAN_SIRASI[i];
                if (L === layer) continue;
                var k = L + ':' + pz + ':' + tx + ':' + ty, e2 = this._tiles.get(k);
                if (e2 && e2.mesh) { this._touchTile(k); return; }
            }
        }
    };

    // Ekran merkezini (c) kapsayan, ÇİZİLMİŞ en ince karo: {layer, z} ya da
    // null. Not ve künye bunu söyler (en ince z önce; aynı z'de GIBS önce).
    LaunchSiteGlobe.prototype._merkezDokusu = function (c) {
        var katmanlar = KATMAN_SIRASI;
        var zUst = Math.max(TILE_MAX_ZOOM, _detayTavan !== null ? _detayTavan : 0);
        for (var z = zUst; z >= TILE_PARENT_MIN_ZOOM; z--) {
            var lv = tileLevel(z);
            if (!lv) continue;
            var tx = (((Math.floor((c.lon + 180.0) / lv.span)) % lv.mw) + lv.mw) % lv.mw;
            var ty = Math.floor((90.0 - c.lat) / lv.span);
            if (ty < 0 || ty >= lv.mh) continue;
            for (var i = 0; i < katmanlar.length; i++) {
                var e = this._tiles.get(katmanlar[i] + ':' + z + ':' + tx + ':' + ty);
                if (e && e.mesh) return { layer: katmanlar[i], z: z };
            }
        }
        return null;
    };

    // Tek karo için kendi yama geometrisi + dokuyu backend'den yükle.
    LaunchSiteGlobe.prototype._buildTilePatch = function (layer, z, tx, ty) {
        var THREE = global.THREE, self = this;
        var key = layer + ':' + z + ':' + tx + ':' + ty;
        // Rezervasyon (aynı karo iki kez yüklenmesin); mesh doku gelince eklenir.
        var paket = (layer === TILE_LAYER_PACK);
        this._tiles.set(key, { mesh: null, t: performance.now(), loading: true, paket: paket });
        var url = tileUrl(layer, z, tx, ty);
        new THREE.TextureLoader().load(url, function (tex) {
            if (self._disposed) { tex.dispose(); return; }
            var entry = self._tiles.get(key);
            if (!entry || !entry.loading) { tex.dispose(); return; }  // budanmış/iptal
            tex.colorSpace = THREE.SRGBColorSpace || tex.colorSpace;
            tex.encoding = THREE.sRGBEncoding || tex.encoding;
            tex.anisotropy = Math.min(8, self.renderer.capabilities.getMaxAnisotropy());
            var mesh = self._makeTileMesh(z, tx, ty, tex, layer);
            // P5B4-30: geometri bilinmiyorsa yama kurulmadı — doku
            // serbest bırakılır, sahte kutu çizilmez (fail-closed).
            if (!mesh) { tex.dispose(); self._tiles.delete(key); return; }
            (paket ? self._paketGroup : self._tileGroup).add(mesh);
            entry.mesh = mesh; entry.loading = false; entry.t = performance.now();
        }, undefined, function () {
            // Offline / GIBS erişilemez / 503 → SAHTE doku YOK, mesh EKLENMEZ.
            // Taban Blue Marble o hücrede görünür (kısmi yükleme kabul).
            //
            // ÖH D17 / P12aB4-04: anahtar Map'ten SİLİNİYORDU; 250 ms sonraki
            // tarama aynı karoyu "hiç denenmemiş" sanıp yeniden istiyordu.
            // Çevrimdışı ölçüm: 25 karo / 0,25 s = 100 istek/sn (~360.000/saat)
            // ve sunucuda her istek 8 sn'lik bir dış GIBS denemesi açıyordu.
            // Artık başarısızlık NEGATİF ÖNBELLEĞE yazılır: anahtar Map'te
            // `failed` durumuyla kalır, üstel geri çekilme (backoff) süresi
            // dolmadan yeniden istenmez ve deneme sayısı TILE_FAIL_MAX'te
            // durur (o karo oturum boyunca bir daha istenmez).
            // V307/FS-HARİTA-KÜRE: paket bindirmesinin düşen karosu (kapsam
            // dışı 404) 'uydu karosu indirilemedi' notunu AÇMAZ: o not ağ/
            // uydu karoları içindir; paket karosu ağa çıkmaz.
            if (!paket) self._tileAnyFail = true;
            if (self._disposed) { self._tiles.delete(key); return; }
            var prev = self._tiles.get(key);
            var tries = (prev && prev.fails ? prev.fails : 0) + 1;
            self._tiles.set(key, {
                mesh: null, loading: false, failed: true, fails: tries, paket: paket,
                t: performance.now(),
                retryAt: (tries >= TILE_FAIL_MAX)
                    ? Infinity
                    : performance.now() + TILE_FAIL_BACKOFF_MS * Math.pow(2, tries - 1),
            });
        });
    };

    // Karo -> küresel yama geometrisi. SphereGeometry UV'sine GÜVENİLMEZ; UV
    // doğrudan enlem/boylamdan türetilir → taban küre UV konvansiyonundan
    // bağımsız, iç tutarlı.
    // V307/FS-HARİTA-KÜRE: `layer` paket katmanıysa (pack_detail) yama,
    // karonun kurulu paket kutularıyla kesişen parçalarına kırpılır (her
    // parça kendi ızgarası; UV karonun tamamına göredir) ve saydam bindirme
    // malzemesi alır. Kesişen parça yoksa yama KURULMAZ (null).
    LaunchSiteGlobe.prototype._makeTileMesh = function (z, tx, ty, tex, layer) {
        var THREE = global.THREE;
        // P5B4-30: açıklık sunucudan; bilinmiyorsa yama KURULMAZ (bir
        // karo, geometrisi bilinmeden Dünya'nın hangi parçasını
        // kapladığını söyleyemez — uydurma kutu çizilmez).
        var span = tileSpanDeg(z);
        if (!(span > 0)) return null;
        var lonW = -180.0 + tx * span;
        var latN = 90.0 - ty * span;
        var latS = latN - span;
        var paket = (layer === TILE_LAYER_PACK);
        // V307/FS-HARİTA: kaba karolar (z < TILE_MAX_ZOOM) z7 karosunun
        // parça açısıyla (288/2^7/8 = 0,28125°) bölünür: S = 8·2^(7-z).
        // Neden: yama kirişi kürenin altına R(1-cos(a/2)) kadar iner; 8
        // parçalı z5 karoda a = 1,125° -> 307 m, z7 açısında 19 m. Karo
        // artık taban küreyle DERİNLİK EĞİMİ (polygonOffsetFactor) yarışı
        // yapmıyor (aşağıda); bu sarkma taban kürenin köşe noktalarında
        // karonun içinden görünmesin diye sınırlanır.
        var S = TILE_PATCH_SEG * Math.pow(2, Math.max(0, TILE_MAX_ZOOM - z));
        var adim = span / S;
        var parcalar = [[lonW, latS, lonW + span, latN]];
        if (paket) {
            // Bindirme kaldırması (çizgi kuralı) en küçük değerinin yarısı
            // kadar sarkmaya izin verir (_init, _paketAdimDeg).
            if (!(this._paketAdimDeg > 0)) return null;
            adim = Math.min(adim, this._paketAdimDeg);
            parcalar = [];
            var kutular = this._paketKutular || [];
            for (var k = 0; k < kutular.length; k++) {
                var kes = kutuKesisim([lonW, latS, lonW + span, latN], kutular[k]);
                if (kes) parcalar.push(kes);
            }
            if (!parcalar.length) return null;
        }
        // V307/FS-HARİTA-KÜRE — R7 kök (1): köşeler karonun MERKEZİNE göre
        // kurulur; merkez Mesh.position'dır. three nesne matrisini JS'te
        // float64 çarpar, GPU'ya giden göreli köşe (en çok karo boyu) ve
        // kamera-göreli öteleme float32'de metrenin çok altında hassastır.
        // Eskiden köşe dünya koordinatındaydı (GLOBE_R = 100 birimde float32
        // adımı ~0,49 m): ebeveyn ile çocuk derinlikte rastgele yarışıyordu.
        var merkez = latLonToVec3(latS + span / 2, lonW + span / 2, TILE_RADIUS);
        var pos = [], uv = [], idx = [];
        for (var pi = 0; pi < parcalar.length; pi++) {
            var w = parcalar[pi][0], s0 = parcalar[pi][1], e = parcalar[pi][2], n = parcalar[pi][3];
            var nx = Math.max(1, Math.ceil((e - w) / adim - 1e-9));
            var ny = Math.max(1, Math.ceil((n - s0) / adim - 1e-9));
            var taban = pos.length / 3, row = nx + 1;
            for (var iy = 0; iy <= ny; iy++) {
                var lat = s0 + (n - s0) * iy / ny;            // güneyden kuzeye
                for (var ix = 0; ix <= nx; ix++) {
                    var lon = w + (e - w) * ix / nx;
                    var p = latLonToVec3(lat, lon, TILE_RADIUS);
                    pos.push(p.x - merkez.x, p.y - merkez.y, p.z - merkez.z);
                    // u = batı→doğu, v = güney→kuzey. THREE varsayılan flipY=true ile
                    // (taban dokuyla aynı): görüntünün üstü(kuzey)→v=1, altı(güney)→v=0.
                    uv.push((lon - lonW) / span, (lat - latS) / span);
                }
            }
            // V307/FS-HARİTA — SARIM YÖNÜ (ölçülen kök neden). Eskiden üçgenler
            // (a, cc, b) sırasıyla kuruluyordu: a güneybatı, cc kuzey, b doğu
            // köşe. latLonToXYZ'de (doğu, kuzey, yukarı) sağ ellidir, yani
            // kuzey x doğu = -yukarı: yüz normali İÇERİ bakıyordu ve dışarıdan
            // bakan kamerada üçgenler saat yönünde görünüp ARKA YÜZ olarak
            // atılıyordu (MeshPhongMaterial side = FrontSide). ÖLÇÜLDÜ
            // (olcum/hata_ayikla, rıza açık, İstanbul 200 km): 64 karo
            // 'çizilmiş' (mesh, 512x512 doku, görünür) ama bütün karo
            // katmanları gizlendiğinde ekran pikseli ortalama 0,0 değişiyordu;
            // rıza açık/kapalı ekran görüntüleri piksel piksel AYNIYDI. Karo
            // sayacı mesh varlığını sayıyordu, pikseli değil. Artık (a, b, cc)
            // ve (b, d, cc): doğu x kuzey = yukarı, normal dışarı, ön yüz.
            for (var jy = 0; jy < ny; jy++)
                for (var jx = 0; jx < nx; jx++) {
                    var a = taban + jy * row + jx, b = a + 1, cc = a + row, d = cc + 1;
                    idx.push(a, b, cc, b, d, cc);
                }
        }
        var geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
        geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
        geo.setIndex(idx);
        var mat;
        if (paket) {
            // Saydam RGBA bindirme (Parça S sözleşmesi): ışıklandırılmaz
            // (harita simgesidir, aydınlatılan bir yüzey değil), derinlik
            // YAZMAZ (çizgiler ve işaretçiler zeminin derinliğiyle sınanır).
            mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false });
        } else {
            geo.computeVertexNormals();
            // Karo yaması taban küreyle ÇAKIŞIK (TILE_RADIUS = GLOBE_R). Ayrım
            // geometrik kaydırmayla değil derinlik yanlılığıyla yapılır: karo
            // parçaları taban küreden bir tık öne yazılır, sahte irtifa üretilmez.
            mat = new THREE.MeshPhongMaterial({
                // ÖH D21 / P12aB4-20: specular DOKU değil DÜZ MALZEME RENGİDİR,
                // dolayısıyla srgb() ondan da muaf değildir (ham hâlde ~#3a4450'ye
                // açılıp parlaklığı kaldırıyordu). Doku (`map`) elbette çevrilmez.
                map: tex, shininess: 4, specular: srgb(0x0a0e12),  // headlight ile tutarlı
                // V307/FS-HARİTA — EĞİM YANLILIĞI KALDIRILDI. polygonOffsetFactor
                // derinliği "piksel başına derinlik eğimi" kadar öne çeker; eğik
                // bakışta bu bir pikselin yer izi kadardır (200 km irtifada ekran
                // kenarında ~80 m). Natural Earth çizgileri yüzeyden yalnız
                // max(2 m, 1e-4·irtifa) yukarıda (200 km'de 20 m) çizildiği için
                // karolar görünür olunca çizgilerin ÜSTÜNE çıkıyordu. ÖLÇÜLDÜ
                // (olcum/hata_ayikla_sonra): karolar açıkken kıyı/sınır çizgisi
                // ekranda yoktu, karolar gizlenince geri geliyordu. Yalnız sabit
                // birim yanlılığı (bir derinlik adımı) kalır: karo taban kürenin
                // önüne geçer; ebeveyn/çocuk ayrımı artık aşağıdaki stencil'dedir.
                polygonOffset: true,
                polygonOffsetFactor: 0,
                polygonOffsetUnits: TILE_DEPTH_BIAS });
        }
        // V307/FS-HARİTA-KÜRE — R7 kök (2): EN İNCE KAZANIR. Karo kendi
        // bitinin yazılmadığı piksele çizilir ve biti yazar; çizim inceden
        // kabaya olduğu için kaba karo (ebeveyn yedeği) yalnız ince karonun
        // HENÜZ ÇİZMEDİĞİ yeri doldurur. Derinlik sınavı aynen geçerlidir
        // (önündeki nesne karoyu yine örter, o pikselde bit yazılmaz).
        var bit = paket ? STENCIL_PAKET : STENCIL_ZEMIN;
        mat.stencilWrite = true;
        mat.stencilWriteMask = bit;
        mat.stencilFunc = THREE.NotEqualStencilFunc;
        mat.stencilRef = bit;
        mat.stencilFuncMask = bit;
        mat.stencilFail = THREE.KeepStencilOp;
        mat.stencilZFail = THREE.KeepStencilOp;
        mat.stencilZPass = THREE.ReplaceStencilOp;
        var mesh = new THREE.Mesh(geo, mat);
        mesh.position.copy(merkez);
        // Çizim sırası inceden kabaya (yukarıdaki ZEMIN_RO_TABANI açıklaması).
        mesh.renderOrder = paket ? PAKET_RO_TABANI - z / 1000 : ZEMIN_RO_TABANI - z;
        return mesh;
    };

    // LRU: dokunulan karoyu Map'in sonuna taşı (insertion-order tazeleme).
    LaunchSiteGlobe.prototype._touchTile = function (key) {
        var e = this._tiles.get(key);
        if (e) { this._tiles.delete(key); this._tiles.set(key, e); e.t = performance.now(); }
    };

    // Cap aşımında en eski (Map ilk anahtar) karoları dispose et.
    // V307/FS-HARİTA-KÜRE: zemin ve paket bindirmesi AYRI tavanla budanır
    // (TILE_LRU_MAX / TILE_LRU_MAX_PAKET); sıra Map ekleme sırasıdır (en eski
    // önce, _touchTile tazeler).
    LaunchSiteGlobe.prototype._pruneTiles = function () {
        if (!this._tiles) return;
        var zemin = [], paket = [];
        this._tiles.forEach(function (e, k) { ((e && e.paket) ? paket : zemin).push(k); });
        var fazla = [[zemin, TILE_LRU_MAX], [paket, TILE_LRU_MAX_PAKET]];
        for (var f = 0; f < fazla.length; f++) {
            var liste = fazla[f][0];
            for (var i = 0; i < liste.length - fazla[f][1]; i++) {
                var e = this._tiles.get(liste[i]);
                this._tiles.delete(liste[i]);
                this._disposeTileEntry(e);
            }
        }
    };

    LaunchSiteGlobe.prototype._disposeTileEntry = function (e) {
        if (!e) return;
        e.loading = false;                       // in-flight yükleme iptal işareti
        if (!e.mesh) return;
        if (e.mesh.parent) e.mesh.parent.remove(e.mesh);
        if (e.mesh.geometry) e.mesh.geometry.dispose();
        if (e.mesh.material) {
            if (e.mesh.material.map) e.mesh.material.map.dispose();
            e.mesh.material.dispose();
        }
    };

    LaunchSiteGlobe.prototype._clearTilePatches = function () {
        if (!this._tiles) return;
        var self = this;
        this._tiles.forEach(function (e) { self._disposeTileEntry(e); });
        this._tiles.clear();
        this._tileAnyFail = false;
        // V307/FS-HARİTA: rıza notu da sökülür (dispose bu işlevi çağırır).
        if (this._detayNotuEl && this._detayNotuEl.parentNode)
            this._detayNotuEl.parentNode.removeChild(this._detayNotuEl);
        this._detayNotuEl = null;
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
            // yakın zoomda GIBS uydu karo yamalarını güncelle (kısmalı)
            self._updateTilePatch();
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
            // Kamera son konumunda: near'ı uyarla, sonra katmanları besle.
            self._updateNear();
            self._emitFrame();
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
        // "Tüm Dünya" görünümünde çerçeveleme en-boy oranına bağlıdır: pencere
        // daralınca yatay yarı-FOV küçülür ve eski mesafe küreyi kırpardı.
        // Hedef merkez olduğundan mesafeyi yeniden ölçeklemek yeter (tween yok).
        if (this._mode === 'global')
            this.camera.position.setLength(globalViewDist(this.camera));
    };

    LaunchSiteGlobe.prototype.dispose = function () {
        this._disposed = true;
        if (this._raf) cancelAnimationFrame(this._raf);
        this.clearFlightPath();
        this._clearTilePatches();        // GIBS karo mesh/doku GPU belleğini boşalt
        this._frameListeners = [];       // kare kancaları (vektör, etiket)
        if (this._vectors) { this._vectors.dispose(); this._vectors = null; }
        this._disposeSky();              // gök küresi + yıldız kovaları
        if (this.renderer) {
            this.renderer.dispose();
            if (this.renderer.domElement && this.renderer.domElement.parentNode)
                this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
        }
    };

    // V306/UÇUŞ — KÜRE KURULAMAZSA SAYFA ÖLMEZ. ÖLÇÜLDÜ (2 Kas, headless
    // Chromium --disable-3d-apis): WebGL bağlamı açılamayınca _init erken
    // dönüyor ve onError('webgl_failed') durum satırına "3B küre
    // başlatılamadı" yazıyordu; ama sayfa betiği hemen ardından
    // selectSite()/viewGlobe() çağırıyor, kamera olmadığı için TypeError
    // ("reading 'position'") atılıyor ve sayfa betiğinin GERİ KALANI
    // (araç kaynağı seçici, gövde alanları, "Bu sahadan uçur") hiç
    // kurulmuyordu: Kaynak = Kayıtlı proje seçilince proje listesi bile
    // gelmiyordu. Küreden bağımsız uçuş çözümü WebGL'siz makinede de
    // çalışmalı. Kurulamamış kürede her açık yöntem iş yapmadan null döner;
    // sayfanın okuyucuları null'ı zaten "küre yok" diye ele alıyor
    // (getScaleInfo/getSkyInfo/getTileInfo çağrı yerleri).
    Object.keys(LaunchSiteGlobe.prototype).forEach(function (ad) {
        var ozgun = LaunchSiteGlobe.prototype[ad];
        if (typeof ozgun !== 'function' || ad.charAt(0) === '_') return;
        LaunchSiteGlobe.prototype[ad] = function () {
            if (this._kurulamadi) return null;
            return ozgun.apply(this, arguments);
        };
    });

    // Dışa aç
    LaunchSiteGlobe.latLonToVec3 = latLonToVec3;
    LaunchSiteGlobe.latLonToXYZ = latLonToXYZ;
    LaunchSiteGlobe.Z_WEB_Z0_MPP = Z_WEB_Z0_MPP;
    LaunchSiteGlobe.vec3ToLatLon = vec3ToLatLon;
    LaunchSiteGlobe.enuToGeodetic = enuToGeodetic;
    LaunchSiteGlobe.gmstDeg = gmstDeg;
    LaunchSiteGlobe.R_EARTH_M = R_EARTH_M;
    global.LaunchSiteGlobe = LaunchSiteGlobe;

})(typeof window !== 'undefined' ? window : this);
