/* HRMA fırlatma sahası küresi sözlüğü — i18n_launch_site.js
 * ---------------------------------------------------------------
 * İnteraktif 3B Dünya (Blue Marble) üzerinden fırlatma sahası seçimi ve
 * uçuş yolu animasyonu sayfasının (launch_site.html) EN/TR metinleri.
 * Ön ek: 'site.'  — i18n.js ÇOK-PARÇALI SÖZLÜK SÖZLEŞMESİ'ne birebir uyar.
 * EN ve TR anahtar kümeleri BİREBİR aynıdır (tests/test_i18n.py doğrular).
 */
(function (global) {
    'use strict';
    var DICT = {
        en: {
            'site.title': 'Launch Site & Flight Path',
            'site.subtitle': 'Pick any point on Earth, then watch the solved flight path',
            'site.loadingGlobe': 'Loading globe…',
            'site.globeError': 'The 3D globe could not be started (WebGL required).',

            'site.cursorReadout': 'Cursor',
            'site.selected': 'Selected site',
            'site.selectHint': 'Rotate with drag, zoom with wheel, click the globe to pick a point.',
            'site.lat': 'Latitude',
            'site.lon': 'Longitude',
            'site.alt': 'Altitude',
            'site.fineTune': 'Fine-tune coordinates',
            'site.apply': 'Apply',
            'site.presets': 'Shortcuts (not a limit — any point is selectable)',

            'site.resolve': 'Resolve site',
            'site.resolving': 'Resolving…',
            'site.resolveUnavailable': 'Site resolver endpoint is not wired yet (offline elevation/gravity comes from the server).',
            'site.elevation': 'Elevation',
            'site.terrainRelief': 'Terrain relief (3×3 cell)',
            'site.gravityLocal': 'Local gravity g(φ,h)',
            'site.gravityStd': 'Standard g₀ (Isp uses this)',
            'site.gravityDelta': 'Local vs standard',
            'site.atmosphere': 'Surface atmosphere',
            'site.temp': 'Temperature',
            'site.pressure': 'Pressure',
            'site.density': 'Density',
            'site.earthRotSpeed': 'Earth rotation speed (info only)',
            'site.online': 'Use online enrichment (Open-Meteo)',
            'site.sourceOffline': 'Offline (ETOPO 2022 + ISA 1976)',

            'site.flight': 'Flight path',
            'site.launch': 'Fly this site',
            'site.launching': 'Solving flight…',
            'site.play': 'Play',
            'site.pause': 'Pause',
            'site.reset': 'Reset',
            'site.time': 'Time',
            'site.viewSite': 'Zoom to site',
            'site.viewGlobe': 'View whole Earth',
            'site.exaggerate': 'Exaggerate altitude',
            'site.exaggerateHint': 'Off by default — scale is true. Only enlarges the vertical for readability.',
            'site.follow': 'Camera follows rocket',

            'site.legend': 'Legend',
            'site.flightPathLabel': 'Flight path (solved 6-DOF)',
            'site.groundTrackLabel': 'Ground track — Earth rotation NOT modelled',
            'site.ballistic': 'Ballistic flight (not an orbit)',
            'site.events': 'Events (derived from the solution)',
            'site.liftoff': 'Liftoff',
            'site.burnout': 'Burnout',
            'site.apogee': 'Apogee (solver ends here)',
            'site.impact': 'Impact (ground)',
            'site.end': 'End of solution',

            'site.scale': 'Scale',
            'site.camAltitude': 'Camera altitude',
            'site.demCell': 'DEM cell',
            'site.apogeeReadout': 'Apogee',
            'site.rangeReadout': 'Downrange',
            'site.speedReadout': 'Speed',

            'site.textureNote': 'At close zoom the global texture/DEM (~9 km cells) holds no local terrain detail — no fake terrain is drawn.',
            'site.earthRotNote': 'Earth rotation and Coriolis are not modelled in v1; the ground track is a flat-Earth projection.',
            'site.mode': 'View mode',
            'site.modeLocal': 'Local (near site)',
            'site.modeGlobal': 'Global (whole Earth)',
            'site.noData': 'No flight path yet — pick a site and press Fly.',
            'site.solveError': 'The flight solver returned an error.',
            'site.back': 'Back to app'
        },
        tr: {
            'site.title': 'Fırlatma Sahası ve Uçuş Yolu',
            'site.subtitle': 'Dünya üzerinde herhangi bir noktayı seç, çözülen uçuş yolunu izle',
            'site.loadingGlobe': 'Küre yükleniyor…',
            'site.globeError': '3B küre başlatılamadı (WebGL gerekli).',

            'site.cursorReadout': 'İmleç',
            'site.selected': 'Seçili saha',
            'site.selectHint': 'Sürükleyerek döndür, tekerlekle yakınlaş, noktayı seçmek için küreye tıkla.',
            'site.lat': 'Enlem',
            'site.lon': 'Boylam',
            'site.alt': 'Rakım',
            'site.fineTune': 'Koordinat ince ayarı',
            'site.apply': 'Uygula',
            'site.presets': 'Kısayollar (kısıt değil — her nokta seçilebilir)',

            'site.resolve': 'Sahayı çöz',
            'site.resolving': 'Çözülüyor…',
            'site.resolveUnavailable': 'Saha çözümleyici ucu henüz bağlanmadı (çevrimdışı rakım/yerçekimi sunucudan gelir).',
            'site.elevation': 'Rakım',
            'site.terrainRelief': 'Arazi engebesi (3×3 hücre)',
            'site.gravityLocal': 'Yerel yerçekimi g(φ,h)',
            'site.gravityStd': 'Standart g₀ (Isp bunu kullanır)',
            'site.gravityDelta': 'Yerel / standart farkı',
            'site.atmosphere': 'Yüzey atmosferi',
            'site.temp': 'Sıcaklık',
            'site.pressure': 'Basınç',
            'site.density': 'Yoğunluk',
            'site.earthRotSpeed': 'Dünya dönüş hızı (yalnız bilgi)',
            'site.online': 'Çevrimiçi zenginleştirme (Open-Meteo)',
            'site.sourceOffline': 'Çevrimdışı (ETOPO 2022 + ISA 1976)',

            'site.flight': 'Uçuş yolu',
            'site.launch': 'Bu sahadan uçur',
            'site.launching': 'Uçuş çözülüyor…',
            'site.play': 'Oynat',
            'site.pause': 'Duraklat',
            'site.reset': 'Sıfırla',
            'site.time': 'Zaman',
            'site.viewSite': 'Sahaya yakınlaş',
            'site.viewGlobe': 'Tüm Dünya',
            'site.exaggerate': 'Rakımı abart',
            'site.exaggerateHint': 'Varsayılan kapalı — ölçek gerçektir. Yalnız okunabilirlik için düşeyi büyütür.',
            'site.follow': 'Kamera roketi izlesin',

            'site.legend': 'Gösterge',
            'site.flightPathLabel': 'Uçuş yolu (çözülen 6-DOF)',
            'site.groundTrackLabel': 'Yer izi — Dünya dönüşü MODELLENMEDİ',
            'site.ballistic': 'Balistik uçuş (yörünge değil)',
            'site.events': 'Olaylar (çözümden türetildi)',
            'site.liftoff': 'Kalkış',
            'site.burnout': 'Yanma sonu',
            'site.apogee': 'Apoje (çözücü burada biter)',
            'site.impact': 'Yere iniş',
            'site.end': 'Çözüm sonu',

            'site.scale': 'Ölçek',
            'site.camAltitude': 'Kamera yüksekliği',
            'site.demCell': 'DEM hücresi',
            'site.apogeeReadout': 'Apoje',
            'site.rangeReadout': 'Menzil',
            'site.speedReadout': 'Hız',

            'site.textureNote': 'Yakın ölçekte küresel doku/DEM (~9 km hücre) yerel arazi detayı içermez — sahte arazi çizilmez.',
            'site.earthRotNote': 'Dünya dönüşü ve Coriolis v1\'de modellenmiyor; yer izi düz-Dünya izdüşümüdür.',
            'site.mode': 'Görünüm kipi',
            'site.modeLocal': 'Yerel (sahaya yakın)',
            'site.modeGlobal': 'Küresel (tüm Dünya)',
            'site.noData': 'Henüz uçuş yolu yok — bir saha seç ve Uçur\'a bas.',
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
