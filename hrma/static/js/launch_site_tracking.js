/* HRMA — Fırlatma Sahası GÖREV İZLEME ekranı
 * ===========================================
 * launch_site_tracking.js  (V307/FS-İZLEME, 9 Kas 2026)
 *
 * NEDEN VAR (ölçüldü, docs/scofield/raw/OH/V307/fs-izleme/RAPOR.md):
 * Fırlatma Sahası uçuşu küreye doğru çiziyordu ama kamera bir sondaj
 * roketinin yayını ~136 km yükseklikten gösteriyordu (çerçeve tabanı
 * 0,03 R = 191 km): 3-6 km'lik apoje ekranda birkaç piksellik bir nokta
 * kümesiydi, kullanıcı "sadece çizgi" görüyordu. Canlı okuma üç satırdı;
 * üç örnekten ikisinde (kararsız araç) oynat düğmesi gerekçesi sağ
 * panelin durum satırında kalarak kapalıydı.
 * Bu modül çözülmüş uçuşu bir görev izleme ekranı olarak oynatır:
 * telemetri paneli, olay zaman çizelgesi, hız çarpanlı zaman şeridi ve
 * üç kamera kipi (roketi izle / yer izi / serbest).
 *
 * DÜRÜSTLÜK (sahte veri ve sahte animasyon YASAK)
 * -----------------------------------------------
 *  - Ekrandaki her sayı uçuş yanıtının bir alanıdır; panel değeri,
 *    oynatma anına eşit ya da ondan önceki SON çözücü örneğidir (örnek
 *    tutma). Okumalar enterpole EDİLMEZ; hangi örneğin gösterildiği
 *    panelde yazılır. Her değer kutusu `data-alan` (yanıt alanı) ve
 *    `data-ham` (ham sayı) taşır: ölçüm onları yanıtla birebir karşılaştırır.
 *  - Yanıtın yayımlamadığı büyüklük için gösterge KONMAZ; istenen ama
 *    yayımlanmayan büyüklüklerin (ivme / yük çarpanı, kütle) adı panelde
 *    "yayımlanmıyor" diye söylenir.
 *  - Olay zamanları yanıttan okunur (sözleşmenin `events` listesi; o yoksa
 *    summary / flight_verdict). İniş yalnız sunucu onu çözdüyse (nokta-kütle
 *    balistik) gösterilir, çözülmediyse nedeni yazılır. Paraşüt hiçbir
 *    çözümde modellenmez: olay listesine konmaz, notla söylenir.
 *  - Oynatma izni sözleşmenin `playback_allowed` alanıdır (kararsız araçta
 *    kapalı; neden ve statik marjlar yazılır). Sahte oynatma yoktur.
 *  - Oynatma ve zaman şeridi yalnız hesaplanmış zaman aralığını gezer.
 *    Hız çarpanı bir görüntü ayarıdır; hiçbir şey yeniden hesaplanmaz.
 *  - Roket sembolünün yeri kürenin kendi çiziminden gelir (iki çözücü
 *    örneği arasında doğrusal); bu modül roket konumu UYDURMAZ.
 *
 * VERİ KAYNAĞI
 * ------------
 * Uçuş verisinin istemci sözleşmesi FS-UÇUŞ kulvarınındır
 * (`window.LaunchSiteFlightResult`, şema hrma.launch_site.flight_result/1;
 * her değişimde document üzerinde `hrma:launch-site-flight` olayı). İz
 * sözleşmenin `samples` / `events` / `descent` / `playback_allowed`
 * alanlarından kurulur. Küre örneği ve kürenin çizdiği seri
 * `LaunchSiteGlobe.prototype.setFlightPath` sarmalanarak öğrenilir; iki
 * zaman tabanı aynı olmalıdır (sözleşme küreye samples.time_s dizisinin
 * kendisini verir). Sözleşme null olunca (araç değişti, ret, uç hatası) iz
 * silinir ve ekran kapanır. Sözleşmesiz bir sayfada yalnız küreye giden
 * seri gösterilir (olay zamanı için özet yoktur, uydurulmaz).
 *
 * Dosya iki parçadır: saf çekirdek (`Core`, node ile test edilir;
 * tests/test_v307_fs_izleme.py) ve tarayıcı arayüzü (`bind`).
 */
(function (global) {
    'use strict';

    // ---- Görüntü ayarları (veri DEĞİL) ---------------------------------
    // Oynatma hız çarpanları; 1 = gerçek zaman (varsayılan).
    var HIZ_CARPANLARI = [1, 2, 5, 10, 20, 50];
    var VARSAYILAN_CARPAN = 1;
    // Sekme arka plandan dönünce tek karede büyük sıçrama olmasın diye bir
    // karede ilerleyen en büyük gerçek süre [s]. Görüntü ayarıdır.
    var KARE_DT_TAVAN_S = 1.0;
    // Zaman karşılaştırma payı [s] (olay "çözüm aralığı dışında" mı?).
    var ZAMAN_PAYI_S = 1e-9;

    // Olay renkleri: küredeki olay işaretçilerinin (launch_site_globe.js
    // _buildEventMarkers) renkleriyle AYNI; bekçi test ikisini eşitler.
    var OLAY_RENGI = {
        liftoff: 0x2dd4a8, burnout: 0xffd166, apogee: 0x00e5ff,
        impact: 0xff5d73, end: 0xff5d73,
        // V307/FS-KÜÇÜK (kalem 1): paraşüt açılışı (kürede de işaretçisi var).
        deploy: 0xff7eb6,
        // max-q için kürede işaretçi yok; izleme ekranına özgü renk.
        maxq: 0xc792ea,
        // V307/KÜÇÜKLER (kalem 1): çalkantı bağlaşık koşusunun doğrusal
        // geçerlilik sınırını aştığı an (kürede de işaretçisi var).
        limit: 0xff3d00
    };

    // V307/KÜÇÜKLER (kalem 1): UÇUŞ-GÖVDE yayım kuralının (sunucu
    // `calkanti.yayim`, HUKUM_SOZLESMESI §11) neden kodu. Bu kodla gelen
    // koşuda `t ≥ t_ilk_asim_s` bölümü geçerlilik dışıdır: telemetri işaretli,
    // o bölümdeki olayların (apoje, açılış, iniş) sayısı basılmaz.
    var GECERLILIK_DISI_NEDENI = 'BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI';

    // İrtifa dizisinin datumu -> etiket anahtarı. Tanınmayan datum
    // FAIL-CLOSED: iz kurulmaz (küre de aynı kuralla çizmez).
    var DATUM_ETIKETI = {
        above_launch_site: 'site.trackDatumAgl',
        mean_sea_level: 'site.trackDatumMsl'
    };

    // Seçimli kanallar: iz anahtarı -> yanıt alanı (series.<alan>).
    var SECIMLI_KANALLAR = [
        ['speed', 'speed'],
        ['mach', 'mach'],
        ['q', 'dynamic_pressure_pa']
    ];

    // İstenen ama bugünkü 6-DOF yanıtının YAYIMLAMADIĞI büyüklükler. Kanal
    // izde yoksa gösterge konmaz, adı "yayımlanmıyor" notunda geçer.
    var ISTENEN_YAYIMLANMAYAN = [
        { anahtar: 'acceleration', etiket: 'site.trackAccel' },
        { anahtar: 'mass', etiket: 'site.trackMass' }
    ];

    // FS-UÇUŞ sözleşmesinin şeması (RAPOR fs-ucus §1).
    var SOZLESME_SEMASI = 'hrma.launch_site.flight_result/1';
    // Sözleşme olay anahtarı -> izleme olay anahtarı.
    // V307/FS-KÜÇÜK (kalem 1): `deploy` (paraşüt açılışı) artık tanınır;
    // önceden tanınmayan olay sessizce atlanıyordu (ölçüldü: sunucu yayımlıyor,
    // ekranda yok).
    var SOZLESME_OLAYI = { liftoff: 'liftoff', burnout: 'burnout', max_q: 'maxq',
                           apogee: 'apogee', deploy: 'deploy', landing: 'impact' };
    // Uçuş evresi (samples.phase) -> etiket anahtarı.
    var EVRE_ETIKETI = { powered: 'site.trackPhasePowered', coast: 'site.trackPhaseCoast',
                         descent: 'site.trackPhaseDescent' };
    // İnişin çözülmeme nedeni -> metin anahtarı (ham kod ekrana çıkmaz).
    var INIS_NEDENI = {
        vehicle_not_statically_stable: 'site.trackDescentUnstable',
        ascent_alpha_above_linear_limit: 'site.trackDescentAlpha',
        stability_not_evaluated: 'site.trackDescentNotEvaluated',
        ascent_did_not_end_at_apogee: 'site.trackDescentNoApogee',
        ground_not_reached_within_limit: 'site.trackDescentNoGround',
        descent_integration_failed: 'site.trackDescentFailed'
    };
    // Panel satırının yanıt alanı (kaynağa göre).
    var SERI_ALAN_ADI = { time: 'series.time', altitude: 'series.altitude',
        north: 'series.north', east: 'series.east', speed: 'series.speed',
        mach: 'series.mach', q: 'series.dynamic_pressure_pa' };
    var SOZLESME_ALAN_ADI = { time: 'samples.time_s', altitude: 'samples.altitude_agl_m',
        north: 'samples.north_m', east: 'samples.east_m', downrange: 'samples.downrange_m',
        speed: 'samples.speed_mps', mach: 'samples.mach', q: 'samples.dynamic_pressure_pa',
        phase: 'samples.phase' };

    // Çözümün bitiş nedenleri -> olay etiketi anahtarı.
    var BITIS_ETIKETI = {
        time_limit: 'site.trackEndTimeLimit',
        tumble_detected: 'site.trackEndTumble',
        solver_failed: 'site.trackEndSolverFailed'
    };

    // =====================================================================
    // SAF ÇEKİRDEK
    // =====================================================================
    function sonluSayi(v) { return (typeof v === 'number' && isFinite(v)) ? v : null; }

    /* Yayım kaydı -> {t, tVar, neden} | null. Neden kodu varsa ama ilk aşım
       zamanı sonlu değilse FAIL-CLOSED: izin tamamı (t0'dan) geçerlilik dışı. */
    function gecerlilikOku(y, t0) {
        if (!y || typeof y !== 'object' || y.neden_kodu !== GECERLILIK_DISI_NEDENI) return null;
        var tt = sonluSayi(y.t_ilk_asim_s);
        return { t: (tt != null) ? tt : t0, tVar: tt != null, neden: y.neden_kodu };
    }

    function sonluDizi(a, n) {
        if (!Array.isArray(a)) return null;
        if (n != null && a.length !== n) return null;
        for (var i = 0; i < a.length; i++) {
            if (typeof a[i] !== 'number' || !isFinite(a[i])) return null;
        }
        return a;
    }

    /* 6-DOF yanıtını ({series, summary}) izleme izine çevirir.
       Dönüş: {ok: true, iz} | {ok: false, neden}. Doğrulama FAIL-CLOSED:
       zaman dizisi sonlu, en az iki noktalı ve azalmayan olmalı; irtifa
       dizisi aynı boyda ve datumu adıyla tanınmalı. Seçimli bir kanal
       bozuksa (boy farklı / sonlu değil) o kanal izden DÜŞER ve göstergesi
       konmaz; adı `dusen` listesinde kalır. */
    function normalize(yanit) {
        if (!yanit || typeof yanit !== 'object') return { ok: false, neden: 'response_missing' };
        var s = yanit.series;
        if (!s || typeof s !== 'object') return { ok: false, neden: 'series_missing' };
        var t = sonluDizi(s.time);
        if (!t || t.length < 2) return { ok: false, neden: 'time_invalid' };
        for (var i = 1; i < t.length; i++) {
            if (t[i] < t[i - 1]) return { ok: false, neden: 'time_not_monotonic' };
        }
        var n = t.length;
        var alt = sonluDizi(s.altitude, n);
        if (!alt) return { ok: false, neden: 'altitude_invalid' };
        var datum = s.altitude_datum;
        if (typeof datum !== 'string' || !Object.prototype.hasOwnProperty.call(DATUM_ETIKETI, datum))
            return { ok: false, neden: 'altitude_datum_unknown' };
        var kanal = { altitude: alt }, dusen = [];
        var north = sonluDizi(s.north, n), east = sonluDizi(s.east, n);
        if (north && east) { kanal.north = north; kanal.east = east; }
        else dusen.push('north/east');
        for (var k = 0; k < SECIMLI_KANALLAR.length; k++) {
            var ad = SECIMLI_KANALLAR[k][0], alan = SECIMLI_KANALLAR[k][1];
            if (s[alan] === undefined) continue;          // yayımlanmamış
            var d = sonluDizi(s[alan], n);
            if (d) kanal[ad] = d; else dusen.push(alan);    // bozuk: düşer
        }
        var sm = (yanit.summary && typeof yanit.summary === 'object') ? yanit.summary : null;
        var fv = (sm && sm.flight_verdict && typeof sm.flight_verdict === 'object')
            ? sm.flight_verdict : null;
        var ozet = null;
        var gec = gecerlilikOku(yanit.slosh_publication, t[0]);
        if (sm) {
            ozet = {
                // V307/KÜÇÜKLER (kalem 1): apoje yayımlanmadıysa NEDENİ.
                apogeeNeden: (sonluSayi(sm.apogee) != null) ? null
                    : gec ? 'gecersiz'
                    : (sm.apogee_withheld_because != null) ? 'withheld' : 'yok',
                apogee: sonluSayi(sm.apogee),
                apogeeTime: sonluSayi(sm.apogee_time),
                apogeeDatum: (typeof sm.apogee_datum === 'string') ? sm.apogee_datum : null,
                apogeeWithheld: sm.apogee_withheld_because != null,
                endReason: (typeof sm.end_reason === 'string') ? sm.end_reason : null,
                burnTime: fv ? sonluSayi(fv.burn_time_s) : null,
                tEnd: fv ? sonluSayi(fv.t_end_s) : null
            };
        }
        return { ok: true, iz: {
            kaynak: 'seri', n: n, t: t, t0: t[0], T: t[n - 1], datum: datum,
            kanal: kanal, dusen: dusen, ozet: ozet, alanAdi: SERI_ALAN_ADI,
            hazirOlaylar: null, oynatma: null, inis: null, gecerlilik: gec
        } };
    }

    /* FS-UÇUŞ sözleşmesi (window.LaunchSiteFlightResult, şema
       SOZLESME_SEMASI) -> izleme izi. Sözleşmenin `samples` bloğu yükseliş
       + (çözüldüyse) inişi TEK zaman serisinde taşır; olaylar sunucunun tam
       çözünürlüklü çözümünden gelir. Doğrulama FAIL-CLOSED: şema, durum,
       zaman ve irtifa dizileri ve irtifa datumu tanınmazsa iz kurulmaz.
       `samples` yoksa (eski sunucu: iz bloğu yok) {ok:false,
       neden:'samples_missing'} döner; çağıran o zaman küreye giden seriyi
       sözleşmenin özetiyle birlikte `normalize` ile okur. */
    function normalizeSozlesme(c) {
        if (!c || typeof c !== 'object') return { ok: false, neden: 'contract_missing' };
        if (c.schema !== SOZLESME_SEMASI) return { ok: false, neden: 'contract_schema_unknown' };
        if (c.status !== 'solved') return { ok: false, neden: 'contract_not_solved' };
        var o = c.samples;
        if (!o || typeof o !== 'object') return { ok: false, neden: 'samples_missing' };
        var t = sonluDizi(o.time_s);
        if (!t || t.length < 2) return { ok: false, neden: 'time_invalid' };
        for (var i = 1; i < t.length; i++) {
            if (t[i] < t[i - 1]) return { ok: false, neden: 'time_not_monotonic' };
        }
        var n = t.length;
        var alt = sonluDizi(o.altitude_agl_m, n);
        if (!alt) return { ok: false, neden: 'altitude_invalid' };
        var datum = (c.frame && typeof c.frame.altitude_agl === 'string') ? c.frame.altitude_agl : null;
        if (datum !== 'above_launch_site') return { ok: false, neden: 'altitude_datum_unknown' };
        var kanal = { altitude: alt }, dusen = [];
        var north = sonluDizi(o.north_m, n), east = sonluDizi(o.east_m, n);
        if (north && east) { kanal.north = north; kanal.east = east; }
        else dusen.push('north_m/east_m');
        var ek = [['downrange', 'downrange_m'], ['speed', 'speed_mps'], ['mach', 'mach'],
                  ['q', 'dynamic_pressure_pa']];
        for (var k = 0; k < ek.length; k++) {
            if (o[ek[k][1]] === undefined) continue;
            var d = sonluDizi(o[ek[k][1]], n);
            if (d) kanal[ek[k][0]] = d; else dusen.push(ek[k][1]);
        }
        if (Array.isArray(o.phase) && o.phase.length === n && o.phase.every(function (p) {
            return Object.prototype.hasOwnProperty.call(EVRE_ETIKETI, p); })) kanal.phase = o.phase;
        else if (o.phase !== undefined) dusen.push('phase');
        // Olaylar: yalnız tanınan anahtar + sonlu zaman; sözleşme sıralı verir,
        // yine de zamana göre sıralanır.
        var hazir = [];
        var ds0 = (c.descent && typeof c.descent === 'object') ? c.descent : null;
        // V307/FS-UÇUŞ-2 (A4): paraşütlü iniş adıyla ayrılır (iniş etiketi ve notu).
        var parasutlu = !!(ds0 && ds0.model === 'parachute_point_mass');
        (Array.isArray(c.events) ? c.events : []).forEach(function (e, k) {
            if (!e || typeof e !== 'object') return;
            if (!Object.prototype.hasOwnProperty.call(SOZLESME_OLAYI, e.key)) return;
            var tt = sonluSayi(e.t_s); if (tt == null) return;
            hazir.push({ anahtar: SOZLESME_OLAYI[e.key], t: tt, alan: 'events[' + k + '].t_s',
                inis: e.key === 'landing', parasut: parasutlu,
                deger: (e.key === 'apogee' || e.key === 'deploy') ? sonluSayi(e.altitude_agl_m)
                     : (e.key === 'max_q') ? sonluSayi(e.dynamic_pressure_pa) : null,
                degerAlan: (e.key === 'apogee' || e.key === 'deploy') ? 'events[' + k + '].altitude_agl_m'
                     : (e.key === 'max_q') ? 'events[' + k + '].dynamic_pressure_pa' : null,
                // Paraşüt açılışında hız da (sunucu olayının alanı; yoksa yok).
                hiz: (e.key === 'deploy') ? sonluSayi(e.speed_mps) : null,
                hizAlan: (e.key === 'deploy') ? 'events[' + k + '].speed_mps' : null,
                disarida: tt > t[n - 1] + ZAMAN_PAYI_S });
        });
        // V307/KÜÇÜKLER (kalem 1): doğrusal sınırdan sonraki olaylar işaretli,
        // sayıları basılmaz; sınır anı ayrı olay.
        var gec = gecerlilikOku(c.slosh_publication, t[0]);
        if (gec) {
            hazir.forEach(function (e) {
                if (e.t >= gec.t - ZAMAN_PAYI_S) {
                    e.gecersiz = true; e.deger = null; e.degerAlan = null;
                    e.hiz = null; e.hizAlan = null;
                    // Yanma sonunun ZAMANI uçurulan itki girdisinin sonudur
                    // (çözücü sonucu değil): zaman kalır, durumu işaretlidir.
                    e.zamanGecerli = (e.anahtar === 'burnout');
                }
            });
            if (gec.tVar) hazir.push({ anahtar: 'limit', t: gec.t,
                alan: 'slosh_publication.t_ilk_asim_s',
                disarida: gec.t > t[n - 1] + ZAMAN_PAYI_S });
        }
        var sv = (c.solver && typeof c.solver === 'object') ? c.solver : {};
        var ds = (c.descent && typeof c.descent === 'object') ? c.descent : null;
        return { ok: true, iz: {
            gecerlilik: gec,
            kaynak: 'sozlesme', n: n, t: t, t0: t[0], T: t[n - 1], datum: datum,
            kanal: kanal, dusen: dusen, alanAdi: SOZLESME_ALAN_ADI,
            ozet: { endReason: (typeof sv.end_reason === 'string') ? sv.end_reason : null },
            hazirOlaylar: hazir,
            oynatma: {
                izin: c.playback_allowed === true,
                smFull: sonluSayi(sv.static_margin_full),
                smEmpty: sonluSayi(sv.static_margin_empty)
            },
            inis: ds ? { durum: (ds.status === 'solved') ? 'solved' : 'not_solved',
                         neden: (typeof ds.reason === 'string') ? ds.reason : null,
                         parasut: parasutlu } : null
        } };
    }

    /* Zaman -> örnek indisi. Dönüş {t, i, j, a}: t aralığa kırpılmış zaman,
       i = t[i] <= t koşulunu sağlayan EN BÜYÜK indis (ikili arama), j = i+1
       (sonda i), a = i ile j arasındaki doğrusal oran [0, 1]. Sonlu olmayan
       zaman ilk örneğe düşer. */
    function konumla(iz, tSn) {
        var t = iz.t, n = iz.n;
        var x = (typeof tSn === 'number' && isFinite(tSn)) ? tSn : t[0];
        if (x < t[0]) x = t[0];
        if (x > t[n - 1]) x = t[n - 1];
        var lo = 0, hi = n - 1;
        while (lo < hi) {
            var mid = (lo + hi + 1) >> 1;
            if (t[mid] <= x) lo = mid; else hi = mid - 1;
        }
        var i = lo, j = Math.min(i + 1, n - 1);
        var aralik = t[j] - t[i];
        var a = aralik > 0 ? (x - t[i]) / aralik : 0;
        return { t: x, i: i, j: j, a: a };
    }

    /* Zaman -> konum (yerel ENU, saha üstü). İki çözücü örneği arasında
       doğrusal; küredeki roket sembolü de aynı kuralla (_seekTime) ilerler.
       Yalnız konum enterpole edilir; panel okumaları örnek tutar. */
    function konumAt(iz, tSn) {
        var k = konumla(iz, tSn), c = iz.kanal;
        function ara(d) { return d[k.i] + (d[k.j] - d[k.i]) * k.a; }
        return {
            t: k.t, i: k.i, a: k.a,
            north: c.north ? ara(c.north) : null,
            east: c.east ? ara(c.east) : null,
            up: ara(c.altitude)
        };
    }

    /* Olay listesi (zamana göre sıralı). Kaynaklar:
         kalkış       series.time[0]
         yanma sonu   summary.flight_verdict.burn_time_s
         apoje        summary.apogee_time (+ summary.apogee)
         yere iniş    summary.end_reason = 'ground' -> flight_verdict.t_end_s
         çözüm sonu   seri sonu (son olaydan sonra kalıyorsa), nedeniyle
       Özet yoksa yalnız kalkış ve seri sonu döner. Paraşüt yok. */
    function olaylar(iz) {
        var ev = [], oz = iz.ozet;
        var bitisVar = false;
        if (iz.hazirOlaylar) {
            // Sözleşme: olaylar sunucudan, çözülmeyen olay listede yok.
            ev = iz.hazirOlaylar.map(function (e) {
                var c = {}; for (var k in e) c[k] = e[k]; return c; });
            bitisVar = ev.some(function (e) { return e.anahtar === 'impact'; });
        } else {
            ev.push({ anahtar: 'liftoff', t: iz.t0, alan: 'series.time[0]' });
        }
        if (!iz.hazirOlaylar && oz) {
            if (oz.burnTime != null && oz.burnTime >= iz.t0) {
                ev.push({ anahtar: 'burnout', t: oz.burnTime,
                    alan: 'summary.flight_verdict.burn_time_s',
                    disarida: oz.burnTime > iz.T + ZAMAN_PAYI_S });
            }
            if (oz.apogeeTime != null && oz.apogee != null && !oz.apogeeWithheld) {
                ev.push({ anahtar: 'apogee', t: oz.apogeeTime, deger: oz.apogee,
                    datum: oz.apogeeDatum, alan: 'summary.apogee_time' });
            } else if (oz.apogeeNeden) {
                // V307/KÜÇÜKLER (kalem 1): summary.apogee null — satır kalır,
                // zamanı ve sayısı yok, nedeni adıyla (sessiz atlama yok).
                ev.push({ anahtar: 'apogee', t: iz.T, zamanYok: true,
                    apogeeNeden: oz.apogeeNeden, gecersiz: oz.apogeeNeden === 'gecersiz',
                    alan: 'summary.apogee' });
            }
            if (iz.gecerlilik && iz.gecerlilik.tVar) {
                ev.push({ anahtar: 'limit', t: iz.gecerlilik.t,
                    alan: 'slosh_publication.t_ilk_asim_s',
                    disarida: iz.gecerlilik.t > iz.T + ZAMAN_PAYI_S });
            }
            var tSon = (oz.tEnd != null) ? oz.tEnd : iz.T;
            if (oz.endReason === 'ground') {
                ev.push({ anahtar: 'impact', t: tSon,
                    alan: (oz.tEnd != null) ? 'summary.flight_verdict.t_end_s' : 'series.time[n-1]' });
                bitisVar = true;
            }
        }
        var enGec = iz.t0;
        for (var i = 0; i < ev.length; i++) if (!ev[i].disarida && !ev[i].zamanYok && ev[i].t > enGec) enGec = ev[i].t;
        if (!bitisVar && iz.T > enGec + ZAMAN_PAYI_S) {
            ev.push({ anahtar: 'end', t: iz.T, neden: oz ? oz.endReason : null,
                alan: iz.alanAdi.time + '[' + (iz.n - 1) + ']' });
        }
        // Kararlı sıralama (eşit zamanlı olaylar eklenme sırasını korur).
        return ev.map(function (e, k) { return [e, k]; })
            .sort(function (a, b) { return (a[0].t - b[0].t) || (a[1] - b[1]); })
            .map(function (p) { return p[0]; });
    }

    /* Panel değerleri: oynatma anına eşit ya da ondan önceki son örneğin
       değerleri (örnek tutma). Her satır yanıt alanını adıyla taşır. */
    function panelDegerleri(iz, tSn) {
        var k = konumla(iz, tSn), i = k.i, c = iz.kanal, ad = iz.alanAdi, satirlar = [];
        function alan(x) { return ad[x] + '[' + i + ']'; }
        if (c.phase) satirlar.push({ anahtar: 'phase', deger: c.phase[i], alan: alan('phase') });
        satirlar.push({ anahtar: 'altitude', deger: c.altitude[i], alan: alan('altitude') });
        if (c.downrange) {
            satirlar.push({ anahtar: 'downrange', deger: c.downrange[i], alan: alan('downrange') });
        } else if (c.north && c.east) {
            // Yanıt menzili yayımlamıyorsa yayımlanan kuzey/doğudan TEK işlemle.
            satirlar.push({ anahtar: 'downrange', deger: Math.hypot(c.north[i], c.east[i]),
                alan: 'hypot(' + alan('north') + ', ' + alan('east') + ')' });
        }
        if (c.speed) satirlar.push({ anahtar: 'speed', deger: c.speed[i], alan: alan('speed') });
        if (c.mach) satirlar.push({ anahtar: 'mach', deger: c.mach[i], alan: alan('mach') });
        if (c.q) satirlar.push({ anahtar: 'q', deger: c.q[i], alan: alan('q') });
        return { t: k.t, i: i, n: iz.n, ornekT: iz.t[i], satirlar: satirlar };
    }

    // İstenen ama izde olmayan büyüklükler (gösterge yok, adı söylenir).
    function yayimlanmayanlar(iz) {
        return ISTENEN_YAYIMLANMAYAN.filter(function (b) { return !iz.kanal[b.anahtar]; });
    }

    var Core = {
        normalize: normalize, normalizeSozlesme: normalizeSozlesme,
        konumla: konumla, konumAt: konumAt,
        olaylar: olaylar, panelDegerleri: panelDegerleri,
        yayimlanmayanlar: yayimlanmayanlar,
        OLAY_RENGI: OLAY_RENGI, HIZ_CARPANLARI: HIZ_CARPANLARI,
        DATUM_ETIKETI: DATUM_ETIKETI, SOZLESME_SEMASI: SOZLESME_SEMASI,
        GECERLILIK_DISI_NEDENI: GECERLILIK_DISI_NEDENI
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = Core;
        return;   // node: arayüz kurulmaz
    }

    // =====================================================================
    // TARAYICI ARAYÜZÜ
    // =====================================================================
    var I18N = global.I18N;
    function t(k, fb) { return (I18N && I18N.t) ? I18N.t(k, fb) : (fb || k); }
    function tf(k, p, fb) {
        if (I18N && I18N.tf) return I18N.tf(k, p, fb);
        return String(fb || k).replace(/\{(\w+)\}/g, function (m, ad) {
            return (p && p[ad] != null) ? p[ad] : m; });
    }
    function sayi(v, d) {
        return (I18N && I18N.number) ? I18N.number(v, d) : Number(v).toFixed(d);
    }
    function birimli(v, u, d) {
        return (I18N && I18N.unit) ? I18N.unit(v, u, d) : (sayi(v, d) + ' ' + u);
    }
    function uzunluk(m) {
        return Math.abs(m) < 10000 ? birimli(m, 'm', 0) : birimli(m / 1000, 'km', 2);
    }
    // Panel satırı -> ekran metni (birim + basamak burada TEK tanım).
    function satirMetni(s) {
        if (s.anahtar === 'phase') return t(EVRE_ETIKETI[s.deger], '--');
        if (s.anahtar === 'altitude' || s.anahtar === 'downrange') return uzunluk(s.deger);
        if (s.anahtar === 'speed') return birimli(s.deger, 'm/s', 1);
        if (s.anahtar === 'mach') return sayi(s.deger, 2);
        if (s.anahtar === 'q') return birimli(s.deger / 1000, 'kPa', 2);
        return sayi(s.deger, 3);
    }
    var SATIR_ETIKETI = {
        phase: 'site.trackPhase',
        altitude: 'site.trackAltitude', downrange: 'site.trackDownrange',
        speed: 'site.trackSpeed', mach: 'site.trackMach', q: 'site.trackDynPressure'
    };
    function hex(c) { return '#' + ('000000' + c.toString(16)).slice(-6); }
    function olayAdi(e) {
        if (e.anahtar === 'liftoff') return t('site.liftoff', 'Liftoff');
        if (e.anahtar === 'burnout') return t('site.trackBurnout', 'Burnout (solver)');
        if (e.anahtar === 'apogee') return t('site.trackApogee', 'Apogee');
        if (e.anahtar === 'maxq') return t('site.trackMaxQ', 'Max dynamic pressure');
        if (e.anahtar === 'limit') return t('site.trackLinearLimit', 'Linear validity limit passed (slosh)');
        if (e.anahtar === 'deploy') return t('site.deploy', 'Parachute opens');
        if (e.anahtar === 'impact' && e.inis && e.parasut) return t('site.trackLandingParachute', 'Landing (parachute descent)');
        if (e.anahtar === 'impact' && e.inis) return t('site.trackLanding', 'Landing (ballistic descent)');
        if (e.anahtar === 'impact') return t('site.impact', 'Impact (ground)');
        if (e.neden && BITIS_ETIKETI[e.neden]) return t(BITIS_ETIKETI[e.neden], 'End of solution');
        return t('site.end', 'End of solution');
    }

    function el(tag, cls, attrs) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (attrs) Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
        return e;
    }

    // ---- Durum ------------------------------------------------------------
    var D = {
        kurulu: false, acik: false,
        globe: null, ctx: null, iz: null, olaylar: [],
        bekleyen: null,          // {series} — küreye en son verilen seri
        t: 0, oynuyor: false, carpan: VARSAYILAN_CARPAN, sonAn: 0, raf: 0,
        kip: 'izle', gecisBitis: 0, sonHedef: null,
        dusey: null, geciciV: null, sonIndis: -1, opts: {}, kancaTakili: false, ozetli: false
    };
    var E = {};   // DOM düğümleri
    var DUNYA_Y = null;   // THREE.Vector3(0, 1, 0): kürenin kamera.up varsayılanı

    // ---- Veri bağlantısı -------------------------------------------------
    // İki zaman dizisi aynı zaman tabanı mı (boy + uç ve orta değerler)?
    function zamanTabaniAyni(a, b) {
        if (a === b) return true;
        if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length || a.length < 2) return false;
        var n = a.length;
        return a[0] === b[0] && a[n - 1] === b[n - 1] && a[n >> 1] === b[n >> 1];
    }

    /* İzi kur. Kaynak sırası:
         1) FS-UÇUŞ sözleşmesi (window.LaunchSiteFlightResult) `samples` ile;
            küreye giden seri aynı zaman tabanında olmalı (sözleşme küreye
            samples.time_s dizisinin KENDİSİNİ verir).
         2) Sözleşme var ama `samples` yok (eski sunucu): küreye giden seri +
            sözleşmenin özeti ve oynatma izni.
         3) Sözleşme hiç yok (sözleşmesiz sayfa): yalnız küreye giden seri;
            olay zamanı için özet yok (kalkış ve seri sonu).
       Sözleşme null ise uçuş geçersizdir: iz silinir. */
    function izKur() {
        var b = D.bekleyen;
        var soz = global.LaunchSiteFlightResult;
        var r = null, ozetli = false;
        if (soz && typeof soz === 'object') {
            r = normalizeSozlesme(soz);
            if (r.ok) {
                ozetli = true;
                if (b && !zamanTabaniAyni(b.series && b.series.time, r.iz.t)) {
                    // Küre başka bir zaman tabanı çiziyor: oynatma onunla
                    // senkron olsun diye küre serisi + sözleşme özeti okunur.
                    r = { ok: false, neden: 'globe_time_base_differs' };
                }
            }
            if (!r.ok && b) {
                r = normalize({ series: b.series, summary: soz.summary || null,
                                slosh_publication: soz.slosh_publication || null });
                ozetli = !!soz.summary;
                if (r.ok) {
                    var sv = soz.solver || {};
                    r.iz.oynatma = { izin: soz.playback_allowed === true,
                        smFull: sonluSayi(sv.static_margin_full),
                        smEmpty: sonluSayi(sv.static_margin_empty) };
                }
            }
        } else if (soz === undefined && b) {
            r = normalize({ series: b.series, summary: null });
        }
        if (!r || !r.ok) {
            if (r && global.console) console.warn('LaunchSiteTracking: flight not tracked (' + r.neden + ')');
            D.iz = null; D.olaylar = []; D.ozetli = false;
        } else {
            D.iz = r.iz; D.olaylar = olaylar(r.iz); D.ozetli = ozetli;
        }
        D.t = D.iz ? D.iz.t0 : 0; D.oynuyor = false; D.sonIndis = -1;
        if (D.raf) { cancelAnimationFrame(D.raf); D.raf = 0; }
        olayIsaretleriniKur();
        tumunuBas();
        if (D.acik && D.iz) {
            // Sayfa yeni uçuşta kamerayı sahaya uçurur (viewSite); izleme
            // kipi o geçişten SONRA yeniden uygulanır.
            setTimeout(function () { if (D.acik) kipUygula(D.kip); }, 700);
        }
    }

    // Sözleşme olayı (hrma:launch-site-flight): nesne küre çiziminden ÖNCE
    // gelir; küreye giden seri henüz yoktur, bekleyen seri sıfırlanır.
    function sozlesmeDegisti() {
        D.bekleyen = null;
        izKur();
    }

    function ucusGeldi(globe, series) {
        D.globe = globe;
        D.ctx = (globe && typeof globe.getTrackingContext === 'function')
            ? globe.getTrackingContext() : null;
        // Kare kancası: küre örneği ilk uçuşta öğrenilir; kanca bir kez takılır.
        if (!D.kancaTakili && globe && typeof globe.addFrameListener === 'function') {
            D.kancaTakili = true;
            globe.addFrameListener(kareDinleyici);
        }
        D.bekleyen = { series: series };
        izKur();
        if (D.opts.autoOpen && D.iz && !D.acik) ac();
    }

    function globeSar(Globe) {
        if (!Globe || !Globe.prototype || Globe.prototype.setFlightPath.__lsTrk) return;
        var ozgun = Globe.prototype.setFlightPath;
        var sarili = function (series) {
            var r = ozgun.apply(this, arguments);
            try { ucusGeldi(this, series); }
            catch (e) { if (global.console) console.warn('LaunchSiteTracking: ' + (e && e.message)); }
            return r;
        };
        sarili.__lsTrk = true;
        Globe.prototype.setFlightPath = sarili;
    }

    // ---- Sayfa kapıları (tek kaynak sayfanın kendisi) ----------------------
    // Oynatma, sayfanın kendi oynat düğmesi açıkken açıktır: kararlılık
    // kapısı (A3) ve "araç değişti" geçersizliği orada TEK yerde verilir,
    // burada tekrarlanmaz. Zaman şeridi sayfanınkiyle aynı koşulda açılır.
    function sayfaOynatmaAcik() {
        // Sözleşme oynatma iznini adıyla taşıyorsa TEK kaynak odur.
        if (D.iz && D.iz.oynatma) return D.iz.oynatma.izin;
        var b = document.getElementById(D.opts.playButtonId || 'ls-playpause');
        return !!(b && !b.disabled);
    }
    function sayfaSeritAcik() {
        if (D.iz && D.iz.oynatma) return true;   // sözleşmeli sayfa: çözülmüş her uçuşta açık
        var s = document.getElementById(D.opts.timeSliderId || 'ls-time');
        return !!(s && !s.disabled);
    }

    // ---- Saat --------------------------------------------------------------
    function zamanUygula() {
        var iz = D.iz; if (!iz) return;
        if (D.globe && typeof D.globe.seek === 'function' && iz.T > 0) D.globe.seek(D.t / iz.T);
        canliBas();
    }
    function dongu(an) {
        D.raf = 0;
        if (!D.oynuyor || !D.iz) return;
        var dt = Math.min((an - D.sonAn) / 1000, KARE_DT_TAVAN_S);
        D.sonAn = an;
        if (dt > 0) D.t += dt * D.carpan;
        if (D.t >= D.iz.T) { D.t = D.iz.T; D.oynuyor = false; }
        zamanUygula();
        oynatDugmesiBas();
        if (D.oynuyor) D.raf = requestAnimationFrame(dongu);
    }
    function oynat() {
        if (!D.iz || !sayfaOynatmaAcik()) return;
        if (D.t >= D.iz.T) D.t = D.iz.t0;
        if (D.globe && D.globe.pause) D.globe.pause();   // kürenin kendi saati durur
        D.oynuyor = true; D.sonAn = performance.now();
        if (!D.raf) D.raf = requestAnimationFrame(dongu);
        oynatDugmesiBas();
    }
    function duraklat() {
        D.oynuyor = false;
        if (D.raf) { cancelAnimationFrame(D.raf); D.raf = 0; }
        oynatDugmesiBas();
    }

    // ---- Kamera kipleri ------------------------------------------------------
    function ucusKapsami(ctx) {
        // Çerçeveleme ölçüsü [sahne birimi]: apoje (saha üstü) ve çözüm sonu
        // yatay mesafesinin büyüğü. Yalnız kamera uzaklığı için (görüntü).
        var f = ctx.flight(); if (!f) return 0;
        var m = Math.max((f.apogee || 0) - (f.h0 || 0), f.range || 0, 1);
        return m / ctx.metersPerUnit;
    }
    function kipUygula(kip) {
        D.kip = kip;
        kipDugmeleriBas();
        var ctx = D.ctx;
        if (!ctx || !D.iz || !ctx.flight()) return;
        var THREE = ctx.THREE, cam = ctx.camera, ctl = ctx.controls;
        if (!DUNYA_Y) DUNYA_Y = new THREE.Vector3(0, 1, 0);   // kamera.up varsayılanı
        var enAz = (ctl.minDistance || 0) * 1.05;
        var kapsam = ucusKapsami(ctx);
        var f = ctx.flight(), n = f.t.length;
        var bas = ctx.latLonToVec3(f.lat[0], f.lon[0], ctx.globeRadius);
        var son = ctx.latLonToVec3(f.lat[n - 1], f.lon[n - 1], ctx.globeRadius);
        if (kip === 'izle') {
            var p = ctx.rocketPosition(); if (!p) return;
            var normal = p.clone().normalize();
            var yatay = son.clone().sub(bas);
            yatay.sub(normal.clone().multiplyScalar(yatay.dot(normal)));
            if (yatay.length() < 1e-9) {
                // Dikey uçuş: yatay yön yok -> yerel kuzey teğeti (görüntü).
                var dogu = new THREE.Vector3(0, 1, 0).cross(normal);
                if (dogu.length() < 1e-9) dogu.set(1, 0, 0);
                yatay = normal.clone().cross(dogu.normalize());
            }
            yatay.normalize();
            var yan = normal.clone().cross(yatay).normalize();
            // Yandan, hafif yukarıdan ve biraz geriden bakış: yay düzlemi görünür.
            var yon = yan.multiplyScalar(0.85).add(normal.clone().multiplyScalar(0.45))
                .add(yatay.clone().multiplyScalar(-0.25)).normalize();
            var uzak = Math.min(Math.max(kapsam * 2.5, enAz), ctx.globeRadius * 1.5);
            // Ekranın "yukarısı" yerel düşey olsun: yay dik durur, iniş aşağı
            // iner. (OrbitControls dönüşü dünya Y'si etrafında kalır; yalnız
            // bakışın yönelimi değişir.) Kip değişince / kapanınca geri alınır.
            cam.up.copy(normal);
            ctx.flyTo(p.clone().add(yon.multiplyScalar(uzak)), p.clone());
            D.sonHedef = p.clone();
            D.gecisBitis = performance.now() + 700;
        } else if (kip === 'yerizi') {
            cam.up.copy(DUNYA_Y);
            // Yer izinin ortasına tepeden (nadir) bakış.
            var orta = bas.clone().add(son).multiplyScalar(0.5).setLength(ctx.globeRadius);
            var yaricap = Math.max(bas.distanceTo(orta), son.distanceTo(orta), kapsam * 0.5);
            var fovYari = (cam.fov || 38) * Math.PI / 360;
            var u = Math.min(Math.max(yaricap / Math.tan(fovYari) * 1.6, enAz), ctx.globeRadius * 1.5);
            ctx.flyTo(orta.clone().add(orta.clone().normalize().multiplyScalar(u)), orta.clone());
            D.sonHedef = null;
        } else {
            cam.up.copy(DUNYA_Y);
            D.sonHedef = null;   // serbest: kamera kullanıcıda
        }
    }

    function kareDinleyici() {
        var ctx = D.ctx;
        if (!D.acik || !ctx || !D.iz) return;
        var p = ctx.rocketPosition();
        // Roketten yere düşey çizgi (roketin çizilmiş konumundan).
        if (D.dusey && p) {
            var poz = D.dusey.geometry.attributes.position;
            // Alt uç: roketin tam altında, yer izinin çizildiği yarıçapta
            // (kürenin tek tanımı; saha rakımındaki yüzeyin hemen üstü).
            var yer = D.geciciV.copy(p).setLength(ctx.groundTrackRadius());
            poz.setXYZ(0, p.x, p.y, p.z); poz.setXYZ(1, yer.x, yer.y, yer.z);
            poz.needsUpdate = true;
            D.dusey.geometry.computeBoundingSphere();
            D.dusey.visible = true;
        }
        if (D.kip === 'izle' && p && D.sonHedef && performance.now() > D.gecisBitis) {
            var dx = p.x - D.sonHedef.x, dy = p.y - D.sonHedef.y, dz = p.z - D.sonHedef.z;
            if (dx || dy || dz) {
                // Kamera ile hedef birlikte kayar: kullanıcının roket etrafında
                // döndürdüğü bakış açısı korunur.
                ctx.camera.position.x += dx; ctx.camera.position.y += dy; ctx.camera.position.z += dz;
                ctx.controls.target.copy(p);
                ctx.camera.lookAt(ctx.controls.target);
                D.sonHedef.copy(p);
            }
        }
    }

    function duseyKur() {
        var ctx = D.ctx;
        if (!ctx || D.dusey) return;
        var THREE = ctx.THREE;
        var g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 0, 0, 0], 3));
        D.dusey = new THREE.Line(g, new THREE.LineBasicMaterial({
            color: 0xeaf7fb, transparent: true, opacity: 0.45, depthWrite: false }));
        D.dusey.visible = false;
        D.dusey.frustumCulled = false;
        D.geciciV = new THREE.Vector3();
        ctx.scene.add(D.dusey);
    }

    // ---- Açma / kapama -----------------------------------------------------
    function ac() {
        if (!D.iz || D.acik) return;
        D.acik = true;
        var sahne = document.getElementById(D.opts.stageId || 'ls-stage');
        if (sahne) sahne.classList.add('ls-trk-on');
        E.kok.hidden = false;
        if (D.ctx) {
            D.t = Math.min(Math.max(D.ctx.playTime() || D.iz.t0, D.iz.t0), D.iz.T);
            duseyKur();
        }
        if (D.globe) {
            if (D.globe.pause) D.globe.pause();
            if (D.globe.setFollow) D.globe.setFollow(false);   // sayfanın izleme kutusu çakışmasın
        }
        zamanUygula();
        tumunuBas();
        kipUygula(D.kip);
        E.acDugme.setAttribute('aria-pressed', 'true');
        if (E.oynat) E.oynat.focus();
    }
    function kapat() {
        if (!D.acik) return;
        duraklat();
        D.acik = false;
        var sahne = document.getElementById(D.opts.stageId || 'ls-stage');
        if (sahne) sahne.classList.remove('ls-trk-on');
        E.kok.hidden = true;
        if (D.dusey) D.dusey.visible = false;
        if (D.ctx && D.ctx.camera && DUNYA_Y) D.ctx.camera.up.copy(DUNYA_Y);   // kürenin varsayılanı
        if (D.globe && D.globe.setFollow) {
            var takip = document.getElementById(D.opts.followId || 'ls-follow');
            D.globe.setFollow(!!(takip && takip.checked));
        }
        E.acDugme.setAttribute('aria-pressed', 'false');
        E.acDugme.focus();
    }

    // ---- Arayüz kurulumu -------------------------------------------------------
    function kur(kok) {
        E.kok = kok;
        kok.hidden = true;
        kok.innerHTML = '';
        // YERLEŞİM (ölçüldü, 1280×800): sağ sütunun alt payı (dürüstlük
        // notları ~%30 yükseklik) sol sütununkinden büyüktür. Uzun içerik
        // (telemetri + olaylar) sola, kısa içerik (oynatma + kamera) sağa.
        // SOL: telemetri + olaylar
        var sol = el('div', 'ls-panel ls-trk-panel', { id: 'ls-trk-sol' });
        var h = el('h2'); h.setAttribute('data-i18n', 'site.trackTelemetry'); sol.appendChild(h);
        var saat = el('div', 'ls-trk-saat');
        var sk = el('span', 'k', { 'data-i18n': 'site.trackMissionTime' });
        E.saat = el('span', 'v', { id: 'ls-trk-t' });
        saat.appendChild(sk); saat.appendChild(E.saat); sol.appendChild(saat);
        E.ornek = el('div', 'ls-trk-ornek', { id: 'ls-trk-ornek' });
        sol.appendChild(E.ornek);
        E.satirlar = el('div', 'ls-trk-satirlar', { id: 'ls-trk-satirlar' });
        sol.appendChild(E.satirlar);
        E.gecNot = el('div', 'ls-hint ls-note-warn', { id: 'ls-trk-gecersiz', role: 'status' });
        E.gecNot.hidden = true;
        sol.appendChild(E.gecNot);
        E.yok = el('div', 'ls-hint', { id: 'ls-trk-yok' });
        sol.appendChild(E.yok);
        sol.appendChild(el('div', 'ls-sep'));
        sol.appendChild(el('h2', null, { 'data-i18n': 'site.trackEvents' }));
        E.olaylar = el('div', 'ls-trk-olaylar', { id: 'ls-trk-olaylar' });
        sol.appendChild(E.olaylar);
        E.olayNot = el('div', 'ls-hint', { id: 'ls-trk-olay-not' });
        sol.appendChild(E.olayNot);
        kok.appendChild(sol);

        // SAĞ: oynatma + kamera + kapat
        var sag = el('div', 'ls-panel ls-trk-panel', { id: 'ls-trk-sag' });
        sag.appendChild(el('h2', null, { 'data-i18n': 'site.trackPlayback' }));
        var oy = el('div', 'ls-trk-oynatici');
        E.oynat = el('button', 'ls-iconbtn', { id: 'ls-trk-oynat', type: 'button' });
        E.oynat.addEventListener('click', function () { if (D.oynuyor) duraklat(); else oynat(); });
        E.basa = el('button', 'ls-iconbtn ls-trk-genis', { id: 'ls-trk-basa', type: 'button',
            'data-i18n': 'site.trackRestart' });
        E.basa.addEventListener('click', function () {
            if (!D.iz) return; duraklat(); D.t = D.iz.t0; zamanUygula(); });
        E.hiz = el('select', 'ls-trk-hiz', { id: 'ls-trk-hiz' });
        E.hiz.addEventListener('change', function () {
            var v = parseFloat(this.value);
            if (HIZ_CARPANLARI.indexOf(v) >= 0) D.carpan = v;
        });
        var hizEt = el('label', 'ls-trk-hiz-et', { 'for': 'ls-trk-hiz', 'data-i18n': 'site.trackSpeedFactor' });
        oy.appendChild(E.oynat); oy.appendChild(E.basa);
        sag.appendChild(oy);
        var hizSatir = el('div', 'ls-trk-hiz-satir');
        hizSatir.appendChild(hizEt); hizSatir.appendChild(E.hiz);
        sag.appendChild(hizSatir);
        var serit = el('div', 'ls-trk-serit');
        E.zaman = el('input', null, { id: 'ls-trk-zaman', type: 'range', min: '0', max: '1000', value: '0' });
        E.zaman.addEventListener('input', function () {
            if (!D.iz) return;
            duraklat();
            D.t = D.iz.t0 + (parseFloat(this.value) / 1000) * (D.iz.T - D.iz.t0);
            zamanUygula();
        });
        E.imler = el('div', 'ls-trk-imler', { id: 'ls-trk-imler', 'aria-hidden': 'true' });
        serit.appendChild(E.zaman); serit.appendChild(E.imler);
        sag.appendChild(serit);
        var uc = el('div', 'ls-trk-uclar');
        E.ucBas = el('span'); E.ucSon = el('span');
        uc.appendChild(E.ucBas); uc.appendChild(E.ucSon);
        sag.appendChild(uc);
        E.durum = el('div', 'ls-hint ls-note-warn', { id: 'ls-trk-durum', role: 'status' });
        sag.appendChild(E.durum);
        sag.appendChild(el('div', 'ls-sep'));
        sag.appendChild(el('h2', null, { 'data-i18n': 'site.trackCamera' }));
        var kam = el('div', 'ls-trk-kipler', { role: 'group' });
        E.kip = {};
        [['izle', 'site.trackCamFollow'], ['yerizi', 'site.trackCamGround'],
         ['serbest', 'site.trackCamFree']].forEach(function (k) {
            var b = el('button', 'ls-trk-kip', { id: 'ls-trk-kam-' + k[0], type: 'button',
                'data-i18n': k[1], 'aria-pressed': 'false' });
            b.addEventListener('click', function () { kipUygula(k[0]); });
            E.kip[k[0]] = b; kam.appendChild(b);
        });
        sag.appendChild(kam);
        E.kamNot = el('div', 'ls-hint', { id: 'ls-trk-kam-not' });
        sag.appendChild(E.kamNot);
        sag.appendChild(el('div', 'ls-sep'));
        E.kapat = el('button', 'ls-btn', { id: 'ls-trk-kapat', type: 'button', 'data-i18n': 'site.trackExit' });
        E.kapat.addEventListener('click', kapat);
        sag.appendChild(E.kapat);
        kok.appendChild(sag);

        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && D.acik) kapat();
        });
    }

    function acDugmesiKur() {
        var serit = document.getElementById(D.opts.topbarId || 'ls-topbar');
        var b = el('button', 'ls-trk-ac', { id: 'ls-trk-ac', type: 'button',
            'data-i18n': 'site.trackOpen', 'aria-pressed': 'false' });
        b.addEventListener('click', function () { if (D.acik) kapat(); else ac(); });
        E.acDugme = b;
        if (serit) {
            var geri = serit.querySelector('a.ls-link[href="/"]');
            serit.insertBefore(b, geri || null);
        }
    }

    // ---- Basım -------------------------------------------------------------
    function kipDugmeleriBas() {
        if (!E.kip) return;
        Object.keys(E.kip).forEach(function (k) {
            var on = (k === D.kip);
            E.kip[k].classList.toggle('on', on);
            E.kip[k].setAttribute('aria-pressed', on ? 'true' : 'false');
            E.kip[k].disabled = !D.ctx;
        });
    }
    function oynatDugmesiBas() {
        if (!E.oynat) return;
        var anahtar = D.oynuyor ? 'site.pause' : 'site.play';
        var metin = t(anahtar, D.oynuyor ? 'Pause' : 'Play');
        E.oynat.innerHTML = D.oynuyor ? '&#10074;&#10074;' : '&#9658;';
        E.oynat.title = metin;
        E.oynat.setAttribute('aria-label', metin);
        var acik = !!D.iz && sayfaOynatmaAcik();
        E.oynat.disabled = !acik;
        E.basa.disabled = !D.iz;
        E.zaman.disabled = !(D.iz && sayfaSeritAcik());
        E.hiz.disabled = !acik;
        if (D.iz && !acik) {
            var oy = D.iz.oynatma;
            if (oy) {
                // Sözleşme: neden adıyla + çözücünün statik marjları.
                E.durum.textContent = tf('site.trackPlaybackUnstable', {
                    full: (oy.smFull != null) ? sayi(oy.smFull, 2) : '--',
                    empty: (oy.smEmpty != null) ? sayi(oy.smEmpty, 2) : '--' },
                    'Playback is off: the vehicle is aerodynamically unstable (static margin {full} cal full, {empty} cal empty). The solved path is drawn but not played as a flight.');
            } else {
                var st = document.getElementById(D.opts.statusId || 'ls-status');
                E.durum.textContent = t('site.trackPlaybackOff', 'Playback is off for this flight.')
                    + ((st && st.textContent) ? ' ' + st.textContent : '');
            }
            E.durum.hidden = false;
        } else {
            E.durum.textContent = ''; E.durum.hidden = true;
        }
    }

    function hizSecenekleriBas() {
        var sec = D.carpan;
        E.hiz.innerHTML = '';
        HIZ_CARPANLARI.forEach(function (c) {
            var o = el('option', null, { value: String(c) });
            o.textContent = (c === 1)
                ? tf('site.trackRealTime', { x: '×1' }, '×1 (real time)')
                : '×' + sayi(c, 0);
            if (c === sec) o.selected = true;
            E.hiz.appendChild(o);
        });
    }

    function olayIsaretleriniKur() {
        if (!E.imler) return;
        E.imler.innerHTML = '';
        var iz = D.iz; if (!iz) return;
        var sure = iz.T - iz.t0;
        D.olaylar.forEach(function (e) {
            if (e.disarida || (e.gecersiz && !e.zamanGecerli) || e.zamanYok || !(sure > 0)) return;
            var im = el('span', 'ls-trk-im');
            im.style.left = (100 * (e.t - iz.t0) / sure) + '%';
            im.style.background = hex(OLAY_RENGI[e.anahtar] || 0xffffff);
            E.imler.appendChild(im);
        });
    }

    function olaylariBas() {
        E.olaylar.innerHTML = '';
        var iz = D.iz;
        if (!iz) return;
        D.olaylar.forEach(function (e, k) {
            var r = el('div', 'ls-ev ls-trk-olay', { 'data-olay': e.anahtar, 'data-alan': e.alan,
                'data-ham': e.zamanYok ? '' : String(e.t), 'data-gecersiz': e.gecersiz ? '1' : '0' });
            var nokta = el('span', 'dot'); nokta.style.background = hex(OLAY_RENGI[e.anahtar] || 0xffffff);
            var ad = el('span', 'ad'); ad.textContent = olayAdi(e);
            var zm = el('span', 't');
            var z = 'T+' + birimli(e.t, 's', 2);
            if ((e.anahtar === 'apogee' || e.anahtar === 'deploy') && e.deger != null) z += ' · ' + uzunluk(e.deger);
            if (e.anahtar === 'deploy' && e.hiz != null) z += ' · ' + birimli(e.hiz, 'm/s', 1);
            if (e.anahtar === 'maxq' && e.deger != null) z += ' · ' + birimli(e.deger / 1000, 'kPa', 2);
            // V307/KÜÇÜKLER (kalem 1): geçerlilik dışı olayın zamanı ve sayısı
            // basılmaz; yayımlanmayan apojenin nedeni adıyla.
            if (e.gecersiz) z = (e.zamanGecerli ? 'T+' + birimli(e.t, 's', 2) + ' · ' : '')
                + t('site.trackOutsideValidity', 'outside the validity of the linear model');
            else if (e.apogeeNeden === 'withheld') z = t('site.trackApogeeWithheld', 'not reported: the solution was cut before apogee');
            else if (e.apogeeNeden === 'yok') z = t('site.trackApogeeNotPublished', 'not published by this solution');
            if (e.gecersiz) zm.style.color = 'var(--hd-red, #ff5d73)';
            zm.textContent = z;
            var dr = el('span', 'durum'); dr.id = 'ls-trk-olay-durum-' + k;
            r.appendChild(nokta); r.appendChild(ad); r.appendChild(zm); r.appendChild(dr);
            E.olaylar.appendChild(r);
        });
        // Notlar: çözümde olmayan evreler adıyla söylenir.
        var oz = iz.ozet, not = '';
        if (iz.inis && iz.inis.durum === 'solved' && iz.inis.parasut) not = t('site.trackDescentParachute', 'Descent: under the parachute from apogee to the ground, with the recovery model of the 2-D trajectory solver (body drag until the deploy delay, then the parachute drag).');
        else if (iz.inis && iz.inis.durum === 'solved') not = t('site.trackDescentSolved', 'Descent: point-mass ballistic fall from apogee to the ground, nose first, with no recovery system (HRMA choice). No parachute is modelled.');
        else if (iz.inis) not = tf('site.trackDescentNotSolved',
            { reason: t(INIS_NEDENI[iz.inis.neden] || 'site.trackDescentOther', 'the descent could not be computed') },
            'Descent not solved: {reason}. The track ends where the ascent solution ends; no landing point is shown.');
        else if (!D.ozetli || !oz) not = t('site.trackNoSummary', 'The solution summary is not available: only lift-off and the end of the time series are shown.');
        else if (oz.endReason === 'apogee') not = t('site.trackNoDescent', 'The 6-DOF solver stops at apogee: descent, parachute and landing are not part of this solution, so they are not shown.');
        else if (oz.endReason === 'ground') not = t('site.trackNoParachute', 'No parachute is modelled in this solution.');
        if (iz.gecerlilik) {
            not = tf('site.trackInvalidAfter', { t: iz.gecerlilik.tVar ? sayi(iz.gecerlilik.t, 2) : '—' },
                'Slosh coupling passed the linear limit at t = {t} s: from that time on this track, and the apogee, descent and landing built on it, are outside the validity of the linear model; they are not a real trajectory.')
                + (not ? ' ' + not : '');
        }
        E.olayNot.textContent = not;
        E.olayNot.hidden = !not;
    }

    function olayDurumlariBas() {
        D.olaylar.forEach(function (e, k) {
            var d = document.getElementById('ls-trk-olay-durum-' + k);
            if (!d) return;
            var satir = d.parentNode;
            var gecti = !e.disarida && !e.zamanYok && !(e.gecersiz && !e.zamanGecerli)
                && D.t >= e.t - ZAMAN_PAYI_S;
            satir.classList.toggle('gecti', gecti);
            if ((e.gecersiz && !e.zamanGecerli) || e.zamanYok) d.textContent = '';
            else if (e.disarida) d.textContent = t('site.trackEventOutside', 'after the end of the solution');
            else if (gecti) d.textContent = '✓';
            else d.textContent = 'T−' + birimli(e.t - D.t, 's', 1);
        });
    }

    function canliBas() {
        var iz = D.iz;
        if (!iz) return;
        E.saat.textContent = 'T+' + birimli(D.t, 's', 1);
        var p = panelDegerleri(iz, D.t);
        if (p.i !== D.sonIndis) {
            D.sonIndis = p.i;
            E.satirlar.innerHTML = '';
            // V307/KÜÇÜKLER (kalem 1): gösterilen örnek doğrusal sınırdan
            // sonraysa değerler işaretli (kırmızı) ve uyarı satırı açık.
            var gz = iz.gecerlilik;
            var disinda = !!gz && p.ornekT >= gz.t - ZAMAN_PAYI_S;
            E.gecNot.textContent = disinda ? tf('site.liveOutsideValidity',
                { t: gz.tVar ? sayi(gz.t, 2) : '—' },
                'After t = {t} s the slosh-coupled run is outside the validity of the linear model: these readings are not real values.') : '';
            E.gecNot.hidden = !disinda;
            p.satirlar.forEach(function (s) {
                var r = el('div', 'ls-kv');
                var k = el('span', 'k');
                k.textContent = (s.anahtar === 'altitude')
                    ? tf('site.trackAltitude', { datum: t(DATUM_ETIKETI[iz.datum], iz.datum) }, 'Altitude ({datum})')
                    : t(SATIR_ETIKETI[s.anahtar], s.anahtar);
                var v = el('span', 'v', { 'data-alan': s.alan, 'data-ham': String(s.deger),
                    'data-kanal': s.anahtar, 'data-gecersiz': disinda ? '1' : '0' });
                v.textContent = satirMetni(s);
                if (disinda) v.style.color = 'var(--hd-red, #ff5d73)';
                r.appendChild(k); r.appendChild(v);
                E.satirlar.appendChild(r);
            });
            E.ornek.textContent = tf('site.trackSample',
                { t: sayi(p.ornekT, 2), i: String(p.i + 1), n: String(p.n) },
                'Solver sample shown: t = {t} s ({i} of {n})');
            E.ornek.setAttribute('data-ham', String(p.ornekT));
            E.ornek.title = t('site.trackSampleTip', '');
        }
        if (!E.zaman.matches(':active')) {
            var sure = iz.T - iz.t0;
            E.zaman.value = String(Math.round(sure > 0 ? 1000 * (D.t - iz.t0) / sure : 0));
        }
        olayDurumlariBas();
    }

    function tumunuBas() {
        if (!E.kok) return;
        var iz = D.iz;
        E.acDugme.disabled = !iz;
        E.acDugme.classList.toggle('hazir', !!iz);
        E.acDugme.title = iz ? t('site.trackOpenTip', '') : t('site.trackNoFlight', '');
        if (I18N && I18N.apply) I18N.apply(E.kok);
        if (I18N && I18N.apply) I18N.apply(E.acDugme);
        hizSecenekleriBas();
        if (!iz) { if (D.acik) kapat(); return; }
        var ya = yayimlanmayanlar(iz).map(function (b) { return t(b.etiket, b.anahtar); });
        E.yok.textContent = ya.length
            ? tf('site.trackNotPublished', { list: ya.join(', ') }, 'Not published by this solution, so not shown: {list}.')
            : '';
        E.yok.hidden = !ya.length;
        E.ucBas.textContent = 'T+' + birimli(iz.t0, 's', 1);
        E.ucSon.textContent = 'T+' + birimli(iz.T, 's', 1);
        if (D.ctx && D.ctx.controls) {
            E.kamNot.textContent = tf('site.trackCamNote',
                { d: uzunluk((D.ctx.controls.minDistance || 0) * D.ctx.metersPerUnit) },
                'True scale. The camera stays at least {d} away from the point it looks at (globe limit).');
        } else {
            E.kamNot.textContent = t('site.trackNo3d', 'The 3-D globe is not available: telemetry and events only.');
        }
        D.sonIndis = -1;
        olaylariBas();
        kipDugmeleriBas();
        oynatDugmesiBas();
        canliBas();
    }

    /* bind(opts) — sayfaya bağlanır. opts (hepsi isteğe bağlı):
         rootId    izleme kabının id'si           (varsayılan 'ls-trk')
         stageId   sahne kabı                     ('ls-stage')
         topbarId  açma düğmesinin konacağı şerit ('ls-topbar')
         autoOpen  uçuş gelince ekran kendiliğinden açılsın (false)
       Sayfadaki kontrol kimlikleri (oynat, şerit, durum, izleme kutusu)
       varsayılanları launch_site.html ile aynıdır. */
    function bind(opts) {
        if (D.kurulu) return;
        D.kurulu = true;
        D.opts = opts || {};
        var kok = document.getElementById(D.opts.rootId || 'ls-trk');
        if (!kok) return;
        var sahne = document.getElementById(D.opts.stageId || 'ls-stage');
        if (sahne && kok.parentNode !== sahne) sahne.appendChild(kok);
        kur(kok);
        acDugmesiKur();
        globeSar(global.LaunchSiteGlobe);
        document.addEventListener('hrma:launch-site-flight', sozlesmeDegisti);
        // Sayfanın oynatma kapısı ve durum satırı değişince yeniden bas.
        if (typeof MutationObserver === 'function') {
            var gozcu = new MutationObserver(function () { if (D.iz) oynatDugmesiBas(); });
            var b = document.getElementById(D.opts.playButtonId || 'ls-playpause');
            var s = document.getElementById(D.opts.statusId || 'ls-status');
            if (b) gozcu.observe(b, { attributes: true, attributeFilter: ['disabled'] });
            if (s) gozcu.observe(s, { childList: true, characterData: true, subtree: true });
        }
        if (I18N && I18N.onChange) I18N.onChange(function () { tumunuBas(); });
        tumunuBas();
    }

    global.LaunchSiteTracking = {
        bind: bind, Core: Core,
        // Ölçüm/test kancası: salt okunur durum özeti.
        state: function () {
            return { acik: D.acik, t: D.t, oynuyor: D.oynuyor, carpan: D.carpan, kip: D.kip,
                ozetli: !!D.ozetli, n: D.iz ? D.iz.n : 0, T: D.iz ? D.iz.T : null,
                kaynak: D.iz ? D.iz.kaynak : null,
                kureT: D.ctx ? D.ctx.playTime() : null,
                olaylar: D.olaylar.map(function (e) { return { anahtar: e.anahtar, t: e.t, alan: e.alan }; }) };
        }
    };
    global.LaunchSiteTrackingCore = Core;
})(typeof window !== 'undefined' ? window : this);
