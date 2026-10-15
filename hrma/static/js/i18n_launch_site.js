/* HRMA fırlatma sahası küresi sözlüğü — i18n_launch_site.js
 * ---------------------------------------------------------------
 * İnteraktif 3B Dünya (Blue Marble) üzerinden fırlatma sahası seçimi ve
 * uçuş yolu animasyonu sayfasının (launch_site.html) EN/TR metinleri.
 * Ön ek: 'site.'  — i18n.js ÇOK-PARÇALI SÖZLÜK SÖZLEŞMESİ'ne birebir uyar.
 * EN ve TR anahtar kümeleri BİREBİR aynıdır (tests/test_i18n.py doğrular).
 *
 * ÖLÜ ANAHTAR TEMİZLİĞİ (P12aB3-12, Z5 i18n süpürmesi)
 * ---------------------------------------------------------------
 * Sözlükte, ürünün HİÇBİR yerinde çağrılmayan 15 anahtar duruyordu
 * (104'ün %14,4'ü). Ölçüm: her anahtar için `git grep --fixed-strings`
 * hrma/ ve tests/ altında bu dosya dışında 0 dosya buluyordu; şablonun
 * TEK dinamik anahtar kurulumu (launch_site.html:549 `'site.src.' + src`)
 * ayrıca denetlendi ve site.src.* ailesi CANLI olduğu için korundu.
 *
 * Silinenler iki hiç kurulmamış parçanın izleriydi:
 *   görünüm kipi seçicisi  site.mode, site.modeLocal, site.modeGlobal
 *   okuma paneli/oynatıcı  site.demCell, site.density, site.gravityDelta,
 *                          site.time, site.play, site.pause, site.ballistic,
 *                          site.noData, site.loadingGlobe, site.fineTune,
 *                          site.sourceOffline, site.atmosphere
 * Ölü çeviri, sözlüğün "bu metinler ekranda görünür" iddiasını yalanlar ve
 * bakımda gerçek bir kalemmiş gibi maliyet üretir. Parça gerçekten
 * kurulduğunda anahtarlar ÇAĞRI YERİYLE BİRLİKTE geri açılır.
 * Anahtar sayısı: 104 -> 89 (EN/TR paritesi korundu).
 */
(function (global) {
    'use strict';
    var DICT = {
        en: {
            // V3 KK 3. tur (§28-50 (c)): /api/flight-vehicle vehicle.load_warnings
            // (hrma/utils/projects.py _LOAD_WARNING_TEXT_EN ile BİREBİR; bekçi eşitler).
            'site.loadWarnAppVersion': 'Project was saved with app version {saved_version}; current version is {current_version}',
            'site.loadWarnMissingStamp': 'Project file is missing the \'{stamp}\' stamp',
            'site.vehicleSection': 'Vehicle to fly',
            'site.flyingVehicle': 'Vehicle',
            'site.vehicleSource': 'Source',
            'site.srcSession': 'Last motor calculated',
            'site.srcProject': 'Saved project (.hrma)',
            'site.srcExample': 'Example vehicle',
            'site.src.results': 'from your motor',
            'site.src.project': 'recomputed from project',
            'site.src.example': 'example, not calculated',
            'site.selectProject': 'Project',
            'site.noProjects': 'No saved projects',
            'site.vThrust': 'Thrust (N)',
            'site.vBurnTime': 'Burn time (s)',
            'site.vPropMass': 'Propellant (kg)',
            'site.vInertMass': 'Engine inert (kg)',
            'site.bodyDiameter': 'Body OD (m)',
            'site.bodyLength': 'Body length (m)',
            'site.airframeDryMass': 'Airframe dry (kg)',
            'site.cd0': 'Cd0 (subsonic)',
            'site.finCount': 'Fins',
            'site.finSpan': 'Fin span (m)',
            'site.windSpeed': 'Wind speed (m/s)',
            'site.windDir': 'Wind direction (deg)',
            'site.fixedAirframeNote': 'Nose (ogive, {nose} m), fin root/tip chord ({root}/{tip} m), fin sweep ({sweep} m) and rail length ({rail} m) are fixed in this view and are not asked for: they enter the Barrowman static margin and therefore the stability verdict above.',
            'site.launchElevation': 'Launch elevation (deg)',
            'site.azimuth': 'Azimuth (deg)',
            'site.airframeHint': 'Airframe dry mass EXCLUDES the engine inert mass shown above \u2014 the solver adds them together.',
            'site.noSessionVehicle': 'No motor calculated in this session yet \u2014 showing the example vehicle.',
            'site.sessionVehicleLoaded': 'Loaded from the last motor calculation.',
            'site.handoffUnreadable': 'Stored vehicle could not be read \u2014 showing the example vehicle.',
            'site.projectVehicleLoaded': 'Recomputed from the saved project.',
            'site.projectLoadFailed': 'Project could not be recomputed \u2014 showing the example vehicle.',
            'site.exampleSelected': 'Example vehicle \u2014 not a motor you calculated.',
            'site.recomputing': 'Recomputing motor from project\u2026',
            'site.inertEstimate': 'Engine inert mass is an estimate (~0.25 x propellant), not a computed structure.',
            'site.controlsNeedFlight': 'Controls become active once a flight is solved.',
            'site.presetEverest': 'Mount Everest (high terrain)',
            'site.presetTerrainRef': 'terrain reference, not a launch site',
            'site.presetApprox': 'area reference, not a launch facility',
            'site.unstableVehicle': 'Vehicle is aerodynamically unstable (static margin < 1 cal) \u2014 playback disabled. Increase fin span or move mass forward.',
            'site.resolveUnavailable': 'Site lookup failed (you may be offline).',
            'site.tileAttribution': 'NASA GIBS \u2014 Blue Marble Shaded Relief + Bathymetry (~500 m)',
            'site.tileOffline': 'Some satellite tiles could not be downloaded (offline, or the tile server is unreachable) \u2014 those areas show the packaged offline texture (~2 km) or the global base texture, not finer satellite imagery.',
            'site.clearTileCache': 'Clear map cache',
            'site.tileCacheCleared': 'Map tile cache cleared.',
            'site.tileNetworkToggle': 'Online satellite tiles (NASA GIBS)',
            'site.tileNetworkWarn': 'Online tiles are on: each tile request tells the provider (NASA GIBS) which area you are looking at.',
            'site.tileNetworkOffNote': 'Online tiles are off: no request leaves this computer. Areas not in the map cache show the packaged offline texture (~2 km) or the global base texture.',
            'site.tileUnit': 'tile',
            'site.title': 'Launch Site & Flight Path',
            'site.subtitle': 'Pick any point on Earth, then watch the solved flight path',
            'site.globeError': 'The 3D globe could not be started (WebGL required).',

            'site.cursorReadout': 'Cursor',
            'site.selected': 'Selected site',
            'site.selectHint': 'Rotate with drag, zoom with wheel, click the globe to pick a point.',
            'site.lat': 'Latitude',
            'site.lon': 'Longitude',
            'site.alt': 'Altitude',
            // ÖH D22 / OH-D18-10 — irtifa satırının DATUMU. Sayı saha üstü
            // (AGL, çözücüyle aynı sözleşme); deniz seviyesi karşılığı
            // ipucunda adıyla durur.
            'site.altDatumTip': 'Above the launch site. Mean sea level: '
                + '{msl} (site elevation {site}).',
            // ÖH D17 / P12aB3-08: dosyanın başlık yorumu bu anahtarı sayıyordu
            // ama ne sözlükte tanımlıydı ne de sayfada basılıyordu; 3B Dünya
            // üzerinde uçuş yolu izleyen kullanıcı yörüngeye girmediğini
            // hiçbir yerden okumuyordu. Artık lejantta basılıyor.
            'site.ballistic': 'Ballistic flight — not an orbit',
            'site.ballisticHint': 'The path is a suborbital, ballistic trajectory: the vehicle does not enter orbit and falls back to the ground.',
            'site.apply': 'Apply',
            'site.presets': 'Shortcuts (not a limit — any point is selectable)',

            'site.resolve': 'Resolve site',
            'site.resolving': 'Resolving…',
            'site.elevation': 'Elevation',
            'site.terrainRelief': 'Terrain relief (3×3 cell)',
            'site.gravityLocal': 'Local gravity g(φ,h)',
            'site.gravityStd': 'Standard g₀ (Isp uses this)',
            'site.temp': 'Temperature',
            'site.pressure': 'Pressure',
            'site.earthRotSpeed': 'Earth rotation speed (info only)',
            'site.online': 'Use online enrichment (Open-Meteo)',

            'site.flight': 'Flight path',
            'site.launch': 'Fly this site',
            'site.launching': 'Solving flight…',
            /* ÖH D20 / P12aB3-07: oynat/duraklat düğmesinin GÖRÜNÜR tek
             * yazısı ipucudur (gövdesinde yalnız ▶ / ❚❚ simgesi var) ve
             * sabit İngilizce 'Play/Pause' idi. İki durum ayrı anahtar
             * taşır; `launch_site.html` updatePlayUI duruma göre seçer. */
            'site.play': 'Play',
            'site.pause': 'Pause',
            'site.reset': 'Reset',
            'site.viewSite': 'Zoom to site',
            'site.viewGlobe': 'View whole Earth',
            'site.exaggerate': 'Exaggerate altitude',
            'site.exaggerateHint': 'Off by default — scale is true. Only enlarges the vertical for readability.',
            'site.follow': 'Camera follows rocket',

            'site.legend': 'Legend',
            'site.flightPathLabel': 'Flight path (solved 6-DOF)',
            'site.groundTrackLabel': 'Ground track — Earth rotation NOT modelled',
            'site.events': 'Events (derived from the solution)',
            'site.liftoff': 'Liftoff',
            'site.burnout': 'Burnout',
            'site.burnoutFromInput': 'from input burn time',
            'site.apogee': 'Apogee (solver ends here)',
            'site.impact': 'Impact (ground)',
            'site.end': 'End of solution',

            'site.scale': 'Scale',
            'site.camAltitude': 'Camera altitude',
            'site.apogeeReadout': 'Apogee',
            /* ÖH D18 / P12aB4-10: 'Downrange' etiketi hangi ANA ait
             * olduğunu söylemiyordu; değer tüm çözümün SON noktasına
             * aitti ve canlı blokta sabit duruyordu. İki ayrı etiket:
             * anlık (indise bağlı) ve çözüm sonu (özet). */
            'site.rangeReadout': 'Downrange at end of solution',
            'site.downrangeReadout': 'Downrange (now)',
            'site.liveHead': 'Live readout (at the time above)',
            'site.summaryHead': 'Flight summary (whole solution)',
            'site.speedReadout': 'Speed',

            'site.textureNote': 'No satellite tile is drawn in this view: what you see is the global texture/DEM (~9 km cells), which holds no local terrain detail — no fake terrain is drawn.',
            'site.baseTextureNote': 'Base layer: global texture/DEM (~9 km cells). No satellite tile is drawn at this range.',
            'site.earthRotNote': 'Earth rotation and Coriolis are not modelled in v1; the ground track is a flat-Earth projection.',
            'site.skyEpoch': 'Sky orientation (browser clock, UTC)',
            'site.skyAttribution': 'Sky: ESO/S. Brunier Milky Way panorama (CC BY 4.0) · Yale Bright Star Catalogue',
            /* ÖH harita-detay K3 (tasarım §4.1-3, §5.3-1, -4, -5, -6): vektör
             * ölçeği notu, Natural Earth atfı ve etiket künyesi. Atfın EN
             * metni Natural Earth önerisi olan cümledir ve K1 aracındaki
             * NE_ATIF ile bekçiyle kilitlidir (tests/test_harita_etiket.py).
             * Bu yorumda kesme işareti YOK: sözlük ayrıştırıcısı tırnak sayar. */
            'site.vectorScaleNote': 'Border, coastline and river lines are generalised 1:{scale} million data (Natural Earth). At this range their positions can be off by hundreds of metres up to kilometres.',
            'site.neAttribution': 'Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.',
            'site.labelsProvenance': 'Place and country names: Natural Earth {version}, {view}. A city dot marks an administrative or population point, not the city limits; population is not shown.',
            'site.boundaryViewDefault': 'default (de facto) boundary view',
            'site.labelsFallback': '{n} places have no English name and are shown with their local name.',
            'site.nameCorrections': 'Place and country names corrected to Turkish official usage: {n}.',
            'site.boundaryCorrections': 'Disputed boundary lines removed in Crimea: {n} (official view of Türkiye: Crimea is part of Ukraine).',
            /* harita-detay K4 (tasarım §3.4, §4.1-4, §5.3-1, §5.3-2): paketli
             * doku künyesi (tile_cache bm_local attribution ile kilitli),
             * doku büyütme notu ve Kennedy kıyısında ölçülen çizgi kayması. */
            'site.tilePackagedAttribution': 'NASA Blue Marble Next Generation, December 2004 (Reto Stoeckli, NASA Earth Observatory); packaged offline texture, ~2 km',
            'site.textureMagnifiedPackaged': 'Offline satellite texture: NASA Blue Marble NG, December 2004 cloud-free composite, about {res} per pixel, magnified here (screen about {screen} per pixel). It does not show current buildings; no detail is invented.',
            'site.textureMagnifiedOnline': 'Satellite tile (NASA GIBS, Blue Marble 2004 shaded relief): about {res} per pixel, magnified here (screen about {screen} per pixel); no detail is invented.',
            'site.vectorShiftMeasured': 'Measured on the Kennedy coast against a NASA GIBS tile (about {res} per pixel): median offset {median}, 90th percentile {p90}.',
            'site.solveError': 'The flight solver returned an error.',
            'site.back': 'Back to app'
        },
        tr: {
            // V3 KK 3. tur: i18n_common.js warn.project.* TR şablonuyla BİREBİR.
            'site.loadWarnAppVersion': 'Proje {saved_version} uygulama sürümüyle kaydedilmiş; geçerli sürüm {current_version}',
            'site.loadWarnMissingStamp': 'Proje dosyasında \'{stamp}\' damgası yok',
            'site.vehicleSection': 'U\u00e7urulan ara\u00e7',
            'site.flyingVehicle': 'Ara\u00e7',
            'site.vehicleSource': 'Kaynak',
            'site.srcSession': 'Son hesaplanan motor',
            'site.srcProject': 'Kay\u0131tl\u0131 proje (.hrma)',
            'site.srcExample': '\u00d6rnek ara\u00e7',
            'site.src.results': 'kendi motorunuzdan',
            'site.src.project': 'projeden yeniden hesapland\u0131',
            'site.src.example': '\u00f6rnek, hesaplanm\u0131\u015f de\u011fil',
            'site.selectProject': 'Proje',
            'site.noProjects': 'Kay\u0131tl\u0131 proje yok',
            'site.vThrust': '\u0130tki (N)',
            'site.vBurnTime': 'Yanma s\u00fcresi (s)',
            'site.vPropMass': 'Propelan (kg)',
            'site.vInertMass': 'Motor at\u0131l k\u00fctlesi (kg)',
            'site.bodyDiameter': 'G\u00f6vde d\u0131\u015f \u00e7ap\u0131 (m)',
            'site.bodyLength': 'G\u00f6vde boyu (m)',
            'site.airframeDryMass': 'G\u00f6vde kuru k\u00fctlesi (kg)',
            'site.cd0': 'Cd0 (subsonik)',
            'site.finCount': 'Kanat\u00e7\u0131k say\u0131s\u0131',
            'site.finSpan': 'Kanat\u00e7\u0131k a\u00e7\u0131kl\u0131\u011f\u0131 (m)',
            'site.windSpeed': 'R\u00fczg\u00e2r h\u0131z\u0131 (m/s)',
            'site.windDir': 'R\u00fczg\u00e2r y\u00f6n\u00fc (derece)',
            'site.fixedAirframeNote': 'Burun (ojiv, {nose} m), kanat\u00e7\u0131k k\u00f6k/u\u00e7 veteri ({root}/{tip} m), kanat\u00e7\u0131k ok a\u00e7\u0131kl\u0131\u011f\u0131 ({sweep} m) ve ray uzunlu\u011fu ({rail} m) bu ekranda sabittir ve sorulmaz: Barrowman statik marj\u0131na, dolay\u0131s\u0131yla yukar\u0131daki kararl\u0131l\u0131k h\u00fckm\u00fcne girerler.',
            'site.launchElevation': 'Y\u00fckseli\u015f a\u00e7\u0131s\u0131 (derece)',
            'site.azimuth': 'Azimut (derece)',
            'site.airframeHint': 'G\u00f6vde kuru k\u00fctlesi, yukar\u0131da g\u00f6r\u00fclen motor at\u0131l k\u00fctlesini \u0130\u00c7ERMEZ \u2014 \u00e7\u00f6z\u00fcc\u00fc ikisini toplar.',
            'site.noSessionVehicle': 'Bu oturumda hen\u00fcz motor hesaplanmad\u0131 \u2014 \u00f6rnek ara\u00e7 g\u00f6steriliyor.',
            'site.sessionVehicleLoaded': 'Son motor hesab\u0131ndan y\u00fcklendi.',
            'site.handoffUnreadable': 'Kay\u0131tl\u0131 ara\u00e7 okunamad\u0131 \u2014 \u00f6rnek ara\u00e7 g\u00f6steriliyor.',
            'site.projectVehicleLoaded': 'Kay\u0131tl\u0131 projeden yeniden hesapland\u0131.',
            'site.projectLoadFailed': 'Proje yeniden hesaplanamad\u0131 \u2014 \u00f6rnek ara\u00e7 g\u00f6steriliyor.',
            'site.exampleSelected': '\u00d6rnek ara\u00e7 \u2014 sizin hesaplad\u0131\u011f\u0131n\u0131z bir motor de\u011fil.',
            'site.recomputing': 'Motor projeden yeniden hesaplan\u0131yor\u2026',
            'site.inertEstimate': 'Motor at\u0131l k\u00fctlesi bir TAHM\u0130ND\u0130R (~0,25 \u00d7 propelan), hesaplanm\u0131\u015f bir yap\u0131 de\u011fil.',
            'site.controlsNeedFlight': 'Kontroller bir u\u00e7u\u015f \u00e7\u00f6z\u00fcl\u00fcnce etkinle\u015fir.',
            'site.presetEverest': 'Everest Da\u011f\u0131 (y\u00fcksek arazi)',
            'site.presetTerrainRef': 'arazi referans\u0131, f\u0131rlatma sahas\u0131 de\u011fil',
            'site.presetApprox': 'b\u00f6lge referans\u0131, f\u0131rlatma tesisi de\u011fil',
            'site.unstableVehicle': 'Ara\u00e7 aerodinamik olarak KARARSIZ (statik marj < 1 kalibre) \u2014 oynat\u0131m kapal\u0131. Kanat\u00e7\u0131k a\u00e7\u0131kl\u0131\u011f\u0131n\u0131 art\u0131r\u0131n ya da k\u00fctleyi \u00f6ne al\u0131n.',
            'site.resolveUnavailable': 'Saha \u00e7\u00f6z\u00fcm\u00fc ba\u015far\u0131s\u0131z (\u00e7evrimd\u0131\u015f\u0131 olabilirsiniz).',
            'site.tileAttribution': 'NASA GIBS \u2014 Blue Marble G\u00f6lgeli Kabartma + Batimetri (~500 m)',
            'site.tileOffline': 'Bazı uydu karoları indirilemedi (çevrimdışı olabilirsiniz ya da karo sunucusuna ulaşılamıyor) — o bölgelerde daha ince uydu görüntüsü değil, paketli çevrimdışı doku (~2 km) ya da küresel taban dokusu görünüyor.',
            'site.clearTileCache': 'Harita \u00f6nbelle\u011fini temizle',
            'site.tileCacheCleared': 'Harita karo \u00f6nbelle\u011fi temizlendi.',
            'site.tileNetworkToggle': 'Çevrimiçi uydu karoları (NASA GIBS)',
            'site.tileNetworkWarn': 'Çevrimiçi karolar açık: her karo isteği, baktığınız bölgeyi sağlayıcıya (NASA GIBS) bildirir.',
            'site.tileNetworkOffNote': 'Çevrimiçi karolar kapalı: bu bilgisayardan dışarı istek çıkmaz. Harita önbelleğinde olmayan bölgelerde paketli çevrimdışı doku (~2 km) ya da küresel taban dokusu görünür.',
            'site.tileUnit': 'karo',
            'site.title': 'Fırlatma Sahası ve Uçuş Yolu',
            'site.subtitle': 'Dünya üzerinde herhangi bir noktayı seç, çözülen uçuş yolunu izle',
            'site.globeError': '3B küre başlatılamadı (WebGL gerekli).',

            'site.cursorReadout': 'İmleç',
            'site.selected': 'Seçili saha',
            'site.selectHint': 'Sürükleyerek döndür, tekerlekle yakınlaş, noktayı seçmek için küreye tıkla.',
            'site.lat': 'Enlem',
            'site.lon': 'Boylam',
            // ÖH D17 / P12aB4-05: 'site.alt' roketin ANLIK UÇUŞ irtifası,
            // 'site.elevation' ise sahanın ARAZİ rakımıdır. İkisi de 'Rakım'
            // yazıyordu; aynı ekranda iki ayrı fiziksel büyüklük tek etiketle
            // görünüyordu. TDK/havacılık kullanımı: sabit yer noktası = rakım,
            // hareketli aracın yüksekliği = irtifa. Kodun kendi yorumu
            // (launch_site_globe.js:753-755) zaten bu ayrımı yapıyordu.
            'site.alt': 'İrtifa',
            'site.altDatumTip': 'Fırlatma sahasının üstünden. Deniz '
                + 'seviyesinden: {msl} (saha rakımı {site}).',
            'site.ballistic': 'Balistik uçuş — yörünge değil',
            'site.ballisticHint': 'Yol yörünge-altı, balistik bir gidiş yoludur: araç yörüngeye girmez, yere geri düşer.',
            'site.apply': 'Uygula',
            'site.presets': 'Kısayollar (kısıt değil — her nokta seçilebilir)',

            'site.resolve': 'Sahayı çöz',
            'site.resolving': 'Çözülüyor…',
            'site.elevation': 'Rakım',
            'site.terrainRelief': 'Arazi engebesi (3×3 hücre)',
            'site.gravityLocal': 'Yerel yerçekimi g(φ,h)',
            'site.gravityStd': 'Standart g₀ (Isp bunu kullanır)',
            'site.temp': 'Sıcaklık',
            'site.pressure': 'Basınç',
            'site.earthRotSpeed': 'Dünya dönüş hızı (yalnız bilgi)',
            'site.online': 'Çevrimiçi zenginleştirme (Open-Meteo)',

            'site.flight': 'Uçuş yolu',
            'site.launch': 'Bu sahadan uçur',
            'site.launching': 'Uçuş çözülüyor…',
            'site.play': 'Oynat',
            'site.pause': 'Duraklat',
            'site.reset': 'Sıfırla',
            'site.viewSite': 'Sahaya yakınlaş',
            'site.viewGlobe': 'Tüm Dünya',
            'site.exaggerate': 'İrtifayı abart',
            'site.exaggerateHint': 'Varsayılan kapalı — ölçek gerçektir. Yalnız okunabilirlik için düşeyi büyütür.',
            'site.follow': 'Kamera roketi izlesin',

            'site.legend': 'Gösterge',
            'site.flightPathLabel': 'Uçuş yolu (çözülen 6-DOF)',
            'site.groundTrackLabel': 'Yer izi — Dünya dönüşü MODELLENMEDİ',
            'site.events': 'Olaylar (çözümden türetildi)',
            'site.liftoff': 'Kalkış',
            'site.burnout': 'Yanma sonu',
            'site.burnoutFromInput': 'girdi yanma süresinden',
            'site.apogee': 'Apoje (çözücü burada biter)',
            'site.impact': 'Yere iniş',
            'site.end': 'Çözüm sonu',

            'site.scale': 'Ölçek',
            'site.camAltitude': 'Kamera yüksekliği',
            'site.apogeeReadout': 'Apoje',
            /* ÖH D18 / P12aB4-10: 'Menzil' TOPLAM MENZİL iddiasıdır;
             * değer ise çözümün son noktasındaki yatay mesafedir ve
             * 6-DOF çözücü varsayılan olarak APOJEDE durur (yani
             * balistik menzilin kabaca yarısı). Etiket artık ne
             * ölçüldüğünü söylüyor. */
            'site.rangeReadout': 'Yatay mesafe (\u00e7\u00f6z\u00fcm sonu)',
            'site.downrangeReadout': 'Yatay mesafe (anl\u0131k)',
            'site.liveHead': 'Canl\u0131 okuma (yukar\u0131daki anda)',
            'site.summaryHead': 'U\u00e7u\u015f \u00f6zeti (t\u00fcm \u00e7\u00f6z\u00fcm)',
            'site.speedReadout': 'Hız',

            'site.textureNote': 'Bu görünümde uydu karosu çizilmiyor: gördüğünüz şey küresel doku/DEM (~9 km hücre) ve yerel arazi detayı içermez — sahte arazi çizilmez.',
            'site.baseTextureNote': 'Taban katman: küresel doku/DEM (~9 km hücre). Bu uzaklıkta uydu karosu çizilmiyor.',
            'site.earthRotNote': 'Dünya dönüşü ve Coriolis v1\'de modellenmiyor; yer izi düz-Dünya izdüşümüdür.',
            'site.skyEpoch': 'Gökyüzü yönelimi (tarayıcı saati, UTC)',
            'site.skyAttribution': 'Gökyüzü: ESO/S. Brunier Samanyolu panoraması (CC BY 4.0) · Yale Parlak Yıldız Katalogu',
            'site.vectorScaleNote': 'Sınır, kıyı ve nehir çizgileri 1:{scale} milyon ölçekli genelleştirilmiş veridir (Natural Earth). Bu yakınlıkta konumları yüzlerce metreden kilometreye kadar kayabilir.',
            'site.neAttribution': 'Natural Earth ile yapılmıştır. Ücretsiz vektör ve raster harita verisi: naturalearthdata.com.',
            'site.labelsProvenance': 'Yer ve ülke adları: Natural Earth {version}, {view}. Şehir noktası idari merkez ya da nüfus noktasıdır, şehir sınırı değildir; nüfus gösterilmez.',
            'site.boundaryViewDefault': 'varsayılan (fiilî) sınır görünümü',
            'site.labelsFallback': '{n} yerin Türkçe adı yok; yerel adıyla yazılır.',
            'site.nameCorrections': 'Türkiye\'nin resmî kullanımına göre düzeltilen yer ve ülke adı: {n}.',
            'site.boundaryCorrections': 'Kırım\'da kaldırılan tartışmalı sınır çizgisi: {n} (Türkiye\'nin resmî görüşü: Kırım Ukrayna\'nın parçasıdır).',
            'site.tilePackagedAttribution': 'NASA Blue Marble Next Generation, Aralık 2004 (Reto Stöckli, NASA Earth Observatory); paketli çevrimdışı doku, ~2 km',
            'site.textureMagnifiedPackaged': 'Çevrimdışı uydu dokusu: NASA Blue Marble NG, Aralık 2004 bulutsuz kompozit, piksel başına yaklaşık {res}; burada büyütülüyor (ekranda piksel başına yaklaşık {screen}). Güncel yapılaşmayı göstermez; ayrıntı uydurulmaz.',
            'site.textureMagnifiedOnline': 'Uydu karosu (NASA GIBS, Blue Marble 2004 gölgeli kabartma): piksel başına yaklaşık {res}; burada büyütülüyor (ekranda piksel başına yaklaşık {screen}); ayrıntı uydurulmaz.',
            'site.vectorShiftMeasured': 'Kennedy kıyısında NASA GIBS karosuna (piksel başına yaklaşık {res}) karşı ölçüldü: kayma medyanı {median}, 90. yüzdelik {p90}.',
            'site.solveError': 'Uçuş çözücüsü hata döndürdü.',
            'site.back': 'Uygulamaya dön'
        }
    };
    if (global.I18N && global.I18N.register) {
        global.I18N.register(DICT, 'i18n_launch_site.js');
    } else {
        (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
    }
})(typeof window !== 'undefined' ? window : this);
