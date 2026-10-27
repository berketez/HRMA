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
            'site.dryMassBasis': 'Dry-mass basis',
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
            'site.help.lat': 'Site latitude, decimal degrees (WGS84, north positive). Apply moves the globe there; Resolve site and Fly this site read it (the flight sends it as latitude_deg for Earth rotation). Empty or not a number: those buttons do nothing. Accepted −90 to 90.',
            'site.help.lon': 'Site longitude, decimal degrees (WGS84, east positive). Apply moves the globe there and Resolve site reads it; the flight path is placed at this point. Empty or not a number: those buttons do nothing. Accepted −180 to 180.',
            'site.help.vehicleSource': 'Which vehicle is flown: the last motor calculated on a motor page (handed over through this browser\'s storage), a saved .hrma project (recalculated on the server, since a project stores only inputs) or the built-in example vehicle. Changing it disables the previous flight until you fly again.',
            'site.help.project': 'Saved project whose motor is flown; it is recalculated on the server from its stored inputs. Shown only when Source is a saved project.',
            'site.help.vThrust': 'Thrust of the flown motor (N), read-only: it comes from the selected vehicle and is sent as thrust. If the vehicle does not provide it, the page sends 6500 N.',
            'site.help.vBurnTime': 'Burn time of the flown motor (s), read-only, from the selected vehicle; sent as burn_time. If the vehicle does not provide it, the page sends 7.5 s.',
            'site.help.vPropMass': 'Propellant mass of the flown motor (kg), read-only, from the selected vehicle; sent as propellant_mass. If the vehicle does not provide it, the page sends 18 kg.',
            'site.help.vInertMass': 'Engine inert mass (kg: case, nozzle, injector), read-only, from the selected vehicle. It is added to Airframe dry mass and the sum is sent as dry_mass; if the vehicle does not provide it, 0 is added.',
            'site.help.bodyDia': 'Body outer diameter (m), sent as body_diameter (reference area and fin scaling of the 6-DOF solver). When the vehicle gives the engine diameter, that becomes the field minimum and a smaller value is raised to it. Empty or not a number: 0.15 m is sent.',
            'site.help.bodyLen': 'Body length (m), sent as body_length. When the vehicle gives the engine length, a value shorter than max(2.0 m, engine length + 1.0 m) is raised to it. Empty or not a number: 3.0 m is sent. Nose length 0.50 m (ogive) is fixed on this page.',
            'site.help.dryMass': 'Airframe dry mass (kg), EXCLUDING the engine inert mass shown above; the page adds the two and sends the sum as dry_mass. Empty or not a number: 18 kg is used.',
            'site.help.cd0': 'Zero-lift drag coefficient (dimensionless), sent as cd0; the endpoint accepts 0–5. Empty or not a number: 0.45 is sent.',
            'site.help.finCount': 'Number of fins, sent as fin_count; must be a whole number ≥ 0 (0 = no fins), otherwise the endpoint refuses the flight. Empty: 4 is sent. Fin root chord 0.20 m, tip chord 0.10 m and sweep 0.08 m are fixed on this page.',
            'site.help.finSpan': 'Fin span (m), sent as fin_span; must be ≥ 0. Empty or not a number: 0.11 m is sent.',
            'site.help.windSpeed': 'Wind speed (m/s), sent as wind_speed; must be ≥ 0 and below the ISA sea-level speed of sound. Default 0 (no wind); empty or not a number: 0 is sent.',
            'site.help.windDir': 'Direction the wind blows FROM (degrees from north), sent as wind_direction_deg; accepted 0–360. Empty or not a number: 270 is sent.',
            'site.help.elev': 'Launch elevation above the horizon (degrees), sent as launch_elevation_deg; accepted 0–90 (90 = vertical). Empty or not a number: 84 is sent. The launch rail is fixed at 5 m on this page.',
            'site.help.azim': 'Launch azimuth (degrees from north), sent as launch_azimuth_deg; any finite number. Empty or not a number: 90 is sent.',
            'site.help.presets': 'Shortcut list of known sites: choosing one writes its latitude and longitude into the fields and moves the globe there. Not a limit — any point can be picked on the globe.',
            'site.help.online': 'Off (default): Resolve site uses only packaged offline data. On: it first tries Open-Meteo over the internet for elevation and current surface temperature/pressure, which sends the coordinates to that service; any failure falls back to the offline data.',
            'site.help.time': 'Flight playback timeline: scrubs the solved flight from lift-off (left) to the end (right). Enabled only after Fly this site; display only — nothing is recalculated.',
            'site.help.exaggerate': 'Display only: stretches the vertical scale of the drawn flight path for readability; off means true scale. The flight is not recalculated.',
            'site.help.follow': 'Display only: the camera follows the rocket during playback. The flight is not recalculated.',
            'site.help.tileNetwork': 'Off (default): no map request leaves this computer; areas outside the map cache show the packaged offline texture. On: satellite tiles are fetched from NASA GIBS and each request tells the provider which area you are viewing. The choice is stored in this browser.',

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
            'site.dryMassBasis': 'Kuru k\u00fctle dayana\u011f\u0131',
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
            'site.help.lat': 'Saha enlemi, ondalık derece (WGS84, kuzey artı). Uygula küreyi oraya götürür; Sahayı çöz ve Bu sahadan uçur onu okur (uçuş Dünya dönüşü için latitude_deg olarak gönderir). Boş ya da sayı değilse bu düğmeler hiçbir şey yapmaz. Kabul aralığı −90 ile 90.',
            'site.help.lon': 'Saha boylamı, ondalık derece (WGS84, doğu artı). Uygula küreyi oraya götürür, Sahayı çöz onu okur; uçuş yolu bu noktaya yerleştirilir. Boş ya da sayı değilse bu düğmeler hiçbir şey yapmaz. Kabul aralığı −180 ile 180.',
            'site.help.vehicleSource': 'Hangi aracın uçurulacağı: bir motor sayfasında son hesaplanan motor (bu tarayıcının deposu üzerinden aktarılır), kayıtlı bir .hrma projesi (proje yalnız girdi sakladığı için sunucuda yeniden hesaplanır) ya da yerleşik örnek araç. Değiştirince önceki uçuş, yeniden uçurana kadar kapanır.',
            'site.help.project': 'Motoru uçurulacak kayıtlı proje; saklanan girdilerinden sunucuda yeniden hesaplanır. Yalnız Kaynak kayıtlı proje olduğunda görünür.',
            'site.help.vThrust': 'Uçurulan motorun itkisi (N), salt okunur: seçili araçtan gelir ve thrust olarak gönderilir. Araç vermiyorsa sayfa 6500 N gönderir.',
            'site.help.vBurnTime': 'Uçurulan motorun yanma süresi (s), salt okunur, seçili araçtan; burn_time olarak gönderilir. Araç vermiyorsa sayfa 7,5 s gönderir.',
            'site.help.vPropMass': 'Uçurulan motorun itici kütlesi (kg), salt okunur, seçili araçtan; propellant_mass olarak gönderilir. Araç vermiyorsa sayfa 18 kg gönderir.',
            'site.help.vInertMass': 'Motorun atıl kütlesi (kg: kasa, nozul, enjektör), salt okunur, seçili araçtan. Gövde kuru kütlesine eklenir, toplam dry_mass olarak gönderilir; araç vermiyorsa 0 eklenir.',
            'site.help.bodyDia': 'Gövde dış çapı (m), body_diameter olarak gönderilir (6-DOF çözücüsünde referans alan ve kanat ölçeklemesi). Araç motor çapını veriyorsa o, alanın alt sınırı olur ve daha küçük değer ona yükseltilir. Boş ya da sayı değilse 0,15 m gönderilir.',
            'site.help.bodyLen': 'Gövde boyu (m), body_length olarak gönderilir. Araç motor boyunu veriyorsa max(2,0 m, motor boyu + 1,0 m)\'den kısa değer ona yükseltilir. Boş ya da sayı değilse 3,0 m gönderilir. Burun boyu bu sayfada 0,50 m (ogive) sabittir.',
            'site.help.dryMass': 'Gövde kuru kütlesi (kg), yukarıdaki motor atıl kütlesi HARİÇ; sayfa ikisini toplar ve toplamı dry_mass olarak gönderir. Boş ya da sayı değilse 18 kg kullanılır.',
            'site.help.cd0': 'Sıfır taşımada sürükleme katsayısı (boyutsuz), cd0 olarak gönderilir; uç 0–5 kabul eder. Boş ya da sayı değilse 0,45 gönderilir.',
            'site.help.finCount': 'Kanat sayısı, fin_count olarak gönderilir; 0 ya da büyük tam sayı olmalı (0 = kanatsız), değilse uç uçuşu reddeder. Boşsa 4 gönderilir. Kanat kök veteri 0,20 m, uç veteri 0,10 m ve süpürme 0,08 m bu sayfada sabittir.',
            'site.help.finSpan': 'Kanat açıklığı (m), fin_span olarak gönderilir; 0 ya da büyük olmalı. Boş ya da sayı değilse 0,11 m gönderilir.',
            'site.help.windSpeed': 'Rüzgâr hızı (m/s), wind_speed olarak gönderilir; 0 ya da büyük ve ISA deniz seviyesi ses hızının altında olmalı. Varsayılan 0 (rüzgârsız); boş ya da sayı değilse 0 gönderilir.',
            'site.help.windDir': 'Rüzgârın GELDİĞİ yön (kuzeyden derece), wind_direction_deg olarak gönderilir; kabul aralığı 0–360. Boş ya da sayı değilse 270 gönderilir.',
            'site.help.elev': 'Atışın ufuktan yükselme açısı (derece), launch_elevation_deg olarak gönderilir; kabul aralığı 0–90 (90 = dik). Boş ya da sayı değilse 84 gönderilir. Atış rayı bu sayfada 5 m sabittir.',
            'site.help.azim': 'Atış yönü (kuzeyden derece), launch_azimuth_deg olarak gönderilir; her sonlu sayı. Boş ya da sayı değilse 90 gönderilir.',
            'site.help.presets': 'Bilinen sahaların kısayol listesi: seçince enlem ve boylamı alanlara yazılır ve küre oraya gider. Kısıt değildir — küre üzerinde her nokta seçilebilir.',
            'site.help.online': 'Kapalı (varsayılan): Sahayı çöz yalnız paketteki çevrimdışı veriyi kullanır. Açık: önce internet üzerinden Open-Meteo\'dan rakım ve güncel yüzey sıcaklığı/basıncı dener; bu, koordinatları o servise gönderir. Her hatada çevrimdışı veriye düşer.',
            'site.help.time': 'Uçuş oynatma zaman çizgisi: çözülen uçuşu kalkıştan (sol) sona (sağ) kaydırır. Yalnız Bu sahadan uçur\'dan sonra etkin; yalnız görünüm — hiçbir şey yeniden hesaplanmaz.',
            'site.help.exaggerate': 'Yalnız görünüm: çizilen uçuş yolunun düşey ölçeğini okunurluk için büyütür; kapalı gerçek ölçektir. Uçuş yeniden hesaplanmaz.',
            'site.help.follow': 'Yalnız görünüm: oynatma sırasında kamera roketi izler. Uçuş yeniden hesaplanmaz.',
            'site.help.tileNetwork': 'Kapalı (varsayılan): bu bilgisayardan hiçbir harita isteği çıkmaz; harita önbelleğinde olmayan bölgeler paketteki çevrimdışı dokuyla gösterilir. Açık: uydu karoları NASA GIBS\'ten çekilir ve her istek sağlayıcıya hangi bölgeye baktığınızı söyler. Seçim bu tarayıcıda saklanır.',

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
