/* HRMA — Fırlatma Sahası: indirilebilir harita paketleri (depo + panel)
 * =====================================================================
 * launch_site_map_packs.js — V307 / FS-HARİTA-KÜRE (FS-HARİTA-VERİ faz 2,
 * Parça K), 16 Kas 2026.
 *
 * NE YAPAR
 * --------
 * 1. DEPO: sunucunun paket listesini (uç sözleşmesi, brif_16kas/
 *    FS_HARITA_VERI_FAZ2.md) okur; KURULU paketlerin kutularını ve imzasını
 *    küreye (launch_site_globe.js, paket bindirmesi + z15 tavanı) ve etiket
 *    katmanına (launch_site_labels.js, paket yer adları) verir:
 *      LaunchSiteMapPacks.kuruluKutular() -> [{id, bbox:[w,s,e,n], sha256}]
 *      LaunchSiteMapPacks.imza()          -> kurulu küme değişince değişen dize
 *      LaunchSiteMapPacks.onChange(fn)    -> kaldırma işlevi döner
 * 2. PANEL ("Harita paketleri"): paket listesi (ad, kapsam, boyut, lisans),
 *    AÇIK ONAYLI indirme, gerçek bayt ilerlemesi, iptal, silme, disk
 *    kullanımı, hata kodlarının EN/TR metni, künye düğümü.
 *
 * DÜRÜSTLÜK
 * ---------
 *  - Ağ: indirme isteği YALNIZ onay kutusundaki "Onayla ve indir"
 *    düğmesinden çıkar ve gövdesi tam {"consent": true}'dur. Onaysız yol yok.
 *  - İlerleme YALNIZ sunucunun bildirdiği baytlardır (bytes_done /
 *    bytes_total). Yüzde ve çubuk yalnız bytes_total > 0 iken basılır;
 *    zaman tahmini, sahte ilerleme, süslü animasyon YOK.
 *  - Boyut, kapsam ve disk kullanımı listedeki sayılardan hesaplanır;
 *    paket listesi okunamazsa panel bunu söyler, uydurma satır basmaz.
 *  - Kullanıcı metni i18n sözlüğünden (i18n_launch_site.js); hata kodu
 *    ekranda HAM yazılmaz, tanınmayan kod genel metne düşer.
 */
(function (global) {
    'use strict';

    // Uç yolları (sözleşme). '{id}' kimliğin encodeURIComponent hâliyle
    // değiştirilir. Literaller tek tek yazılı: ürün yüzü envanteri
    // (tests/test_d18_bekci_cevirisi_a1.py) çağrılan rotaları buradan okur.
    var UC_LISTE = '/api/map-packs';
    var UC_INDIR = '/api/map-packs/{id}/download';
    var UC_ILERLEME = '/api/map-packs/{id}/progress';
    var UC_IPTAL = '/api/map-packs/{id}/cancel';
    var UC_SIL = '/api/map-packs/{id}';

    // İlerleme yoklama aralığı [ms]: yalnız bir paket inerken çalışır.
    var ILERLEME_MS = 1000;
    // Künye düğümünün görünürlük denetimi aralığı [ms] (küre/etiket durumu).
    var KUNYE_MS = 500;
    // Megabayt (ondalık, 10^6 B): ekranda boyut birimi; sunucu baytı tam sayı.
    var MB = 1e6;

    // Sözleşmedeki hata kodları (Parça S RAPOR F2.3) -> i18n anahtarı, ADIYLA.
    // Listede olmayan kod genel metne düşer (kod ekrana HAM basılmaz);
    // http_<n> aşağıda ayrıca ele alınır.
    var HATA_ANAHTARI = {
        consent_required: 'site.mapPackErr.consent_required',
        unknown_pack: 'site.mapPackErr.unknown_pack',
        already_downloading: 'site.mapPackErr.already_downloading',
        already_installed: 'site.mapPackErr.already_installed',
        not_downloading: 'site.mapPackErr.not_downloading',
        downloading: 'site.mapPackErr.downloading',
        disk_full: 'site.mapPackErr.disk_full',
        url_not_allowed: 'site.mapPackErr.url_not_allowed',
        redirect_not_allowed: 'site.mapPackErr.redirect_not_allowed',
        range_mismatch: 'site.mapPackErr.range_mismatch',
        size_mismatch: 'site.mapPackErr.size_mismatch',
        too_many_bytes: 'site.mapPackErr.too_many_bytes',
        incomplete_download: 'site.mapPackErr.incomplete_download',
        sha256_mismatch: 'site.mapPackErr.sha256_mismatch',
        io_error: 'site.mapPackErr.io_error',
        network_error: 'site.mapPackErr.network_error',
        bad_manifest: 'site.mapPackErr.bad_manifest',
        manifest_missing: 'site.mapPackErr.manifest_missing',
        path_not_allowed: 'site.mapPackErr.path_not_allowed',
        cancelled: 'site.mapPackErr.cancelled'
    };

    function I() { return global.I18N || null; }
    function t(k, fb) { var x = I(); return (x && x.t) ? x.t(k, fb) : (fb || ''); }
    function tf(k, p, fb) { var x = I(); return (x && x.tf) ? x.tf(k, p, fb) : (fb || ''); }
    function sayi(v, d) {
        var x = I();
        return (x && x.number) ? x.number(v, d) : Number(v).toFixed(d);
    }
    function ucYolu(sablon, id) { return sablon.replace('{id}', encodeURIComponent(String(id))); }

    //: Hata kodu -> kullanıcı metni (i18n). Kod tanınmıyorsa genel metin.
    //: Sunucu durum kodu ekrana sayı olarak yazılmaz: 404 (dosya sürüm
    //: sayfasında yok) ayrı cümledir, diğerleri tek genel cümle.
    function hataMetni(kod) {
        if (typeof kod !== 'string' || !kod) return t('site.mapPackErr.other');
        var m = /^http_(\d{3})$/.exec(kod);
        if (m) return t(m[1] === '404' ? 'site.mapPackErr.http404' : 'site.mapPackErr.http');
        if (Object.prototype.hasOwnProperty.call(HATA_ANAHTARI, kod)) return t(HATA_ANAHTARI[kod]);
        return t('site.mapPackErr.other');
    }

    //: Bayt -> "34,5 MB" (dil ayracıyla). Sayı değilse null (basılmaz).
    function mbMetni(b) {
        if (typeof b !== 'number' || !isFinite(b) || b < 0) return null;
        return sayi(b / MB, 1) + ' MB';
    }

    //: Kutunun doğu-batı ve kuzey-güney boyu [km], kürenin kendi
    //: yarıçapıyla (LaunchSiteGlobe.R_EARTH_M; ikinci sabit yok).
    function kutuKm(b) {
        var G = global.LaunchSiteGlobe, R = G && G.R_EARTH_M;
        if (!(R > 0) || !b || b.length !== 4) return null;
        var d2r = Math.PI / 180;
        return { ew: (b[2] - b[0]) * d2r * R * Math.cos((b[1] + b[3]) / 2 * d2r) / 1000,
                 ns: (b[3] - b[1]) * d2r * R / 1000 };
    }

    //: İlerleme metni ve oranı YALNIZ sunucu baytlarından. Oran yalnız
    //: bytes_total > 0 iken (0..1); aksi null (çubuk basılmaz).
    function ilerlemeOzeti(bd, bt) {
        var done = (typeof bd === 'number' && isFinite(bd) && bd >= 0) ? bd : null;
        var top = (typeof bt === 'number' && isFinite(bt) && bt > 0) ? bt : null;
        if (done === null) return { metin: null, oran: null };
        if (top === null) return { metin: mbMetni(done), oran: null };
        var oran = Math.max(0, Math.min(1, done / top));
        return { metin: tf('site.mapPackProgress', { done: sayi(done / MB, 1),
                                                    total: sayi(top / MB, 1),
                                                    pct: sayi(oran * 100, 0) }),
                 oran: oran };
    }

    // V307/FS-HARİTA-GÖRÜNTÜ — paket BİLEŞENLERİ (sunucu listesindeki
    // 'components': vector = OpenStreetMap, imagery = Copernicus Sentinel-2
    // bulutsuz mozaiği). Bileşen yoksa null; alan uydurulmaz.
    function bilesen(p, tur) {
        var c = (p && Array.isArray(p.components)) ? p.components : [];
        for (var i = 0; i < c.length; i++) if (c[i] && c[i].kind === tur) return c[i];
        return null;
    }
    //: OpenStreetMap cümlesinin lisansı: vektör bileşeninin lisansı (paketin
    //: birleşik 'license' alanı görüntü lisansını da taşır, o cümleye girmez).
    function vektorLisansi(p) {
        var b = bilesen(p, 'vector');
        return (b && typeof b.license === 'string') ? b.license : '';
    }
    //: V307/GÖRÜNTÜ-HAFİF — halka kuralı cümlesi (sunucu özetindeki 'detail':
    //: yarıçaplar listeden, piksel boyları koddan). Kural iki halka + paket
    //: alanı biçiminde değilse cümle yazılmaz (uydurma metin yok).
    function halkaMetni(d) {
        if (!d || !Array.isArray(d.rings) || d.rings.length !== 2) return '';
        var r1 = d.rings[1], r2 = d.rings[0];
        var sayiMi = function (v) { return typeof v === 'number' && isFinite(v) && v > 0; };
        if (!sayiMi(r1.radius_km) || !sayiMi(r2.radius_km) || !sayiMi(r2.m_per_px) || !sayiMi(d.full_m_per_px))
            return '';
        return tf('site.mapPackImageryDetail', { r1: sayi(r1.radius_km, 0), r2: sayi(r2.radius_km, 0),
                                                 m2: sayi(r2.m_per_px, 0), m3: sayi(d.full_m_per_px, 0) });
    }
    //: Görüntü bileşeni varsa {boyut, bildirim, kurulu, ayrinti}; yoksa null.
    function goruntuOzeti(p) {
        var b = bilesen(p, 'imagery');
        if (!b || typeof b.attribution !== 'string' || !b.attribution) return null;
        return { boyut: mbMetni(b.size_bytes), bildirim: b.attribution, kurulu: b.installed === true,
                 ayrinti: halkaMetni(b.detail) };
    }

    // ===================================================================
    // DEPO
    // ===================================================================
    var depo = {
        paketler: [],          // son okunan liste (sunucu sırası)
        durum: 'bekliyor',     // bekliyor | yukleniyor | hazir | hata
        hata: null,
        dinleyiciler: [],
        fetch: null
    };

    function kuruluKutular() {
        var out = [];
        for (var i = 0; i < depo.paketler.length; i++) {
            var p = depo.paketler[i];
            if (p && p.status === 'installed' && Array.isArray(p.bbox) && p.bbox.length === 4)
                out.push({ id: p.id, bbox: p.bbox.slice(), sha256: p.sha256 || '' });
        }
        return out;
    }

    //: V307/FS-HARİTA-GÖRÜNTÜ — görüntü bileşeni de KURULU olan paketlerin
    //: kutuları (küre: ekran merkezinde 10 m görüntü varken taban dokusu
    //: notlarının bunu hesaba katması için; RAPOR DEVİR).
    function goruntuluKutular() {
        var out = [];
        for (var i = 0; i < depo.paketler.length; i++) {
            var p = depo.paketler[i], go = goruntuOzeti(p);
            if (p && p.status === 'installed' && go && go.kurulu && Array.isArray(p.bbox) && p.bbox.length === 4)
                out.push({ id: p.id, bbox: p.bbox.slice() });
        }
        return out;
    }

    function imza() {
        var k = kuruluKutular().map(function (x) { return x.id + ':' + x.sha256; });
        k.sort();
        return k.join('|');
    }

    function haberVer() {
        for (var i = 0; i < depo.dinleyiciler.length; i++) {
            try { depo.dinleyiciler[i](depo); } catch (e) { /* bir dinleyici ötekini durdurmaz */ }
        }
    }

    function onChange(fn) {
        if (typeof fn !== 'function') return function () {};
        depo.dinleyiciler.push(fn);
        return function () {
            var i = depo.dinleyiciler.indexOf(fn);
            if (i >= 0) depo.dinleyiciler.splice(i, 1);
        };
    }

    function getir(url, secenek) {
        var f = depo.fetch || (typeof global.fetch === 'function' ? global.fetch.bind(global) : null);
        if (!f) return Promise.reject(new Error('fetch_yok'));
        return f(url, secenek).then(function (r) {
            return r.json().then(function (g) { return { ok: r.ok, durum: r.status, govde: g }; },
                                 function () { return { ok: r.ok, durum: r.status, govde: null }; });
        });
    }

    function listeYukle() {
        depo.durum = (depo.durum === 'hazir') ? 'hazir' : 'yukleniyor';
        return getir(UC_LISTE).then(function (y) {
            if (!y.ok || !y.govde || !Array.isArray(y.govde.packs)) throw new Error('liste');
            depo.paketler = y.govde.packs;
            depo.durum = 'hazir';
            depo.hata = null;
            haberVer();
            return depo;
        }).catch(function (e) {
            depo.durum = 'hata';
            depo.hata = String(e && e.message || e);
            haberVer();
            return depo;
        });
    }

    // ===================================================================
    // PANEL
    // ===================================================================
    var panel = {
        kok: null, liste: null, ozet: null, kunye: null, kunyeGoruntu: null, doc: null,
        onay: null,            // {id, tur: 'indir'|'sil'} açık onay kutusu
        hataMesaji: {},        // id -> son işlem hatası (istemci tarafı)
        yoklama: null,
        kunyeZaman: null
    };

    function el(ad, sinif, metin) {
        var e = panel.doc.createElement(ad);
        if (sinif) e.className = sinif;
        if (metin != null) e.textContent = metin;
        return e;
    }

    // Ortak ipucu bileşeni (şablondaki "?" ile aynı yapı).
    function ipucu(anahtar) {
        var s = el('span', 'tooltip');
        var ik = el('span', 'tooltip-icon', '?');
        ik.setAttribute('tabindex', '0'); ik.setAttribute('role', 'button'); ik.setAttribute('aria-label', '?');
        var tx = el('span', 'tooltip-text', t(anahtar));
        tx.setAttribute('role', 'tooltip');
        tx.setAttribute('data-i18n', anahtar);
        s.appendChild(ik); s.appendChild(tx);
        return s;
    }

    function dugme(anahtar, ad, fn) {
        var b = el('button', 'ls-iconbtn', t(anahtar));
        b.type = 'button';
        b.style.width = 'auto'; b.style.height = '28px'; b.style.padding = '0 10px';
        b.style.fontSize = '12px';
        b.setAttribute('data-paket-eylem', ad);
        b.addEventListener('click', fn);
        return b;
    }

    function paketAdi(p) {
        var x = I();
        if (p && p.name_key && x && x.has && x.has(p.name_key)) return t(p.name_key);
        return t(p && p.kind === 'region' ? 'site.mapPackKindRegion' : 'site.mapPackKindSite');
    }

    function satirKur(p) {
        var s = el('div', 'ls-pack-row');
        s.setAttribute('data-paket', p.id);
        s.style.padding = '6px 0';
        s.style.borderTop = '1px solid var(--hd-line, rgba(0,229,255,0.14))';
        var ust = el('div');
        ust.style.display = 'flex'; ust.style.justifyContent = 'space-between';
        ust.style.gap = '8px'; ust.style.alignItems = 'baseline';
        var ad = el('span', null, paketAdi(p));
        ad.style.fontSize = '12px'; ad.style.color = 'var(--hd-ink-strong, #eaf7fb)';
        var boy = el('span', 'ls-hint', mbMetni(p.size_bytes) || '');
        boy.style.marginTop = '0'; boy.style.whiteSpace = 'nowrap';
        ust.appendChild(ad); ust.appendChild(boy);
        s.appendChild(ust);
        var km = kutuKm(p.bbox);
        if (km) {
            s.appendChild(el('div', 'ls-hint', tf(p.kind === 'region' ? 'site.mapPackCoverageRegion'
                                                  : 'site.mapPackCoverageSite',
                                                  { ew: sayi(Math.round(km.ew), 0),
                                                    ns: sayi(Math.round(km.ns), 0) })));
        }
        var vl = vektorLisansi(p);
        if (vl) s.appendChild(el('div', 'ls-hint', tf('site.mapPackLicence', { licence: vl })));
        var go = goruntuOzeti(p);
        if (go && go.boyut) {
            // Satır cümlesi bildirimin kapanan tırnağıyla biter: halka cümlesi nokta ile ayrılır.
            var gs = el('div', 'ls-hint', tf('site.mapPackImagery', { size: go.boyut, notice: go.bildirim })
                                          + (go.ayrinti ? '. ' + go.ayrinti : ''));
            gs.setAttribute('data-paket-goruntu', go.kurulu ? 'kurulu' : 'yok');
            s.appendChild(gs);
        }
        var durumSatiri = el('div');
        durumSatiri.style.display = 'flex'; durumSatiri.style.alignItems = 'center';
        durumSatiri.style.gap = '6px'; durumSatiri.style.marginTop = '4px'; durumSatiri.style.flexWrap = 'wrap';
        var dm = el('span', 'ls-hint', durumMetni(p));
        dm.style.marginTop = '0'; dm.style.flex = '1 1 auto';
        dm.setAttribute('data-paket-durum', p.status || '');
        durumSatiri.appendChild(dm);
        if (p.status === 'not_installed' || p.status === 'error') {
            durumSatiri.appendChild(dugme(p.status === 'error' ? 'site.mapPackRetry' : 'site.mapPackDownload',
                                          'indir', function () { onayAc(p.id, 'indir'); }));
            durumSatiri.appendChild(ipucu('site.help.mapPackDownload'));
        } else if (p.status === 'downloading') {
            durumSatiri.appendChild(dugme('site.mapPackCancel', 'iptal', function () { iptal(p.id); }));
            durumSatiri.appendChild(ipucu('site.help.mapPackCancel'));
        } else if (p.status === 'installed') {
            durumSatiri.appendChild(dugme('site.mapPackDelete', 'sil', function () { onayAc(p.id, 'sil'); }));
            durumSatiri.appendChild(ipucu('site.help.mapPackDelete'));
        }
        s.appendChild(durumSatiri);
        if (p.status === 'downloading') {
            var iz = ilerlemeOzeti(p.progress && p.progress.bytes_done, p.progress && p.progress.bytes_total);
            if (iz.oran !== null) {
                var cubuk = el('div');
                cubuk.setAttribute('role', 'progressbar');
                cubuk.setAttribute('aria-valuemin', '0'); cubuk.setAttribute('aria-valuemax', '100');
                cubuk.setAttribute('aria-valuenow', String(Math.round(iz.oran * 100)));
                cubuk.style.height = '4px'; cubuk.style.marginTop = '4px'; cubuk.style.borderRadius = '2px';
                cubuk.style.background = 'var(--hd-inset, rgba(6,14,26,0.85))';
                var dolu = el('div');
                dolu.style.height = '100%'; dolu.style.borderRadius = '2px';
                dolu.style.width = (iz.oran * 100).toFixed(2) + '%';
                dolu.style.background = 'var(--hd-cyan, #00e5ff)';
                cubuk.appendChild(dolu);
                s.appendChild(cubuk);
            }
            if (iz.metin) s.appendChild(el('div', 'ls-hint', iz.metin));
        }
        var hm = panel.hataMesaji[p.id] || (p.status === 'error' ? hataMetni(p.error_code) : null);
        if (hm) {
            var h = el('div', 'ls-hint ls-note-warn', hm);
            h.setAttribute('role', 'status');
            s.appendChild(h);
        }
        if (panel.onay && panel.onay.id === p.id) s.appendChild(onayKutusu(p, panel.onay.tur));
        return s;
    }

    function durumMetni(p) {
        switch (p.status) {
            case 'installed': return t('site.mapPackStateInstalled');
            case 'downloading': return t('site.mapPackStateDownloading');
            case 'error': return t('site.mapPackStateError');
            case 'not_installed': return t('site.mapPackStateNotInstalled');
            default: return '';
        }
    }

    // AÇIK ONAY: ne indirilecek, boyutu, kaynağı, lisansı; ağa giden tek
    // istek bu kutudaki onay düğmesinden çıkar.
    function onayKutusu(p, tur) {
        var k = el('div', 'ls-pack-confirm');
        k.style.marginTop = '6px'; k.style.padding = '8px';
        k.style.border = '1px solid var(--hd-line-strong, rgba(0,229,255,0.42))';
        k.style.borderRadius = '8px'; k.style.background = 'var(--hd-inset, rgba(6,14,26,0.85))';
        var metin = (tur === 'indir')
            ? tf('site.mapPackConsent', { name: paketAdi(p), size: mbMetni(p.size_bytes) || '',
                                          licence: vektorLisansi(p) })
            : tf('site.mapPackDeleteConfirm', { name: paketAdi(p), size: mbMetni(p.size_bytes) || '' });
        var og = (tur === 'indir') ? goruntuOzeti(p) : null;
        if (og && og.boyut)
            metin += ' ' + tf('site.mapPackConsentImagery', { size: og.boyut, notice: og.bildirim })
                     + (og.ayrinti ? ' ' + og.ayrinti : '');
        var m = el('div', 'ls-hint', metin);
        m.style.marginTop = '0'; m.style.color = 'var(--hd-ink, #cfe8f2)';
        k.appendChild(m);
        var sira = el('div');
        sira.style.display = 'flex'; sira.style.gap = '6px'; sira.style.marginTop = '6px';
        sira.style.flexWrap = 'wrap';
        if (tur === 'indir') {
            sira.appendChild(dugme('site.mapPackConsentYes', 'onayla-indir', function () { indir(p.id); }));
        } else {
            sira.appendChild(dugme('site.mapPackDeleteYes', 'onayla-sil', function () { sil(p.id); }));
        }
        sira.appendChild(dugme('site.mapPackConsentNo', 'vazgec', function () {
            panel.onay = null; ciz();
        }));
        k.appendChild(sira);
        return k;
    }

    function onayAc(id, tur) {
        panel.onay = { id: id, tur: tur };
        delete panel.hataMesaji[id];
        ciz();
    }

    function ciz() {
        if (!panel.liste) return;
        var L = panel.liste;
        while (L.firstChild) L.removeChild(L.firstChild);
        if (depo.durum === 'hata') {
            var h = el('div', 'ls-hint ls-note-warn', t('site.mapPackListError'));
            h.setAttribute('role', 'status');
            L.appendChild(h);
        }
        var kurulu = 0, bayt = 0;
        for (var i = 0; i < depo.paketler.length; i++) {
            var p = depo.paketler[i];
            if (!p || typeof p.id !== 'string') continue;
            if (p.status === 'installed') {
                kurulu++;
                if (typeof p.size_bytes === 'number' && isFinite(p.size_bytes)) bayt += p.size_bytes;
            }
            L.appendChild(satirKur(p));
        }
        if (panel.ozet) {
            panel.ozet.textContent = (depo.durum === 'hazir')
                ? tf('site.mapPackDiskUsage', { n: kurulu, size: mbMetni(bayt) || '' }) : '';
        }
        yoklamaAyarla();
    }

    function yanitIsle(id, y) {
        if (!y.ok) panel.hataMesaji[id] = hataMetni(y.govde && y.govde.error_code);
        else delete panel.hataMesaji[id];
    }

    function agHatasi(id) {
        return function () { panel.hataMesaji[id] = t('site.mapPackErr.server'); ciz(); };
    }

    // Tek onaylı indirme isteği: gövde tam {"consent": true}.
    function indir(id) {
        panel.onay = null;
        return getir(ucYolu(UC_INDIR, id), {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ consent: true })
        }).then(function (y) { yanitIsle(id, y); return listeYukle(); }, agHatasi(id))
          .then(function () { ciz(); });
    }

    function iptal(id) {
        // Sunucu sözleşmesi: iptal ucu JSON gövde ister ({}).
        return getir(ucYolu(UC_IPTAL, id), {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        }).then(function (y) { yanitIsle(id, y); return listeYukle(); }, agHatasi(id))
          .then(function () { ciz(); });
    }

    function sil(id) {
        panel.onay = null;
        return getir(ucYolu(UC_SIL, id), { method: 'DELETE' })
            .then(function (y) { yanitIsle(id, y); return listeYukle(); }, agHatasi(id))
            .then(function () { ciz(); });
    }

    // İnen paket varken ilerleme ucunu yokla; durum değişince listeyi tazele.
    function yoklamaAyarla() {
        var inen = depo.paketler.some(function (p) { return p && p.status === 'downloading'; });
        if (inen && !panel.yoklama) panel.yoklama = global.setInterval(yokla, ILERLEME_MS);
        if (!inen && panel.yoklama) { global.clearInterval(panel.yoklama); panel.yoklama = null; }
    }

    function yokla() {
        var inenler = depo.paketler.filter(function (p) { return p && p.status === 'downloading'; });
        if (!inenler.length) { yoklamaAyarla(); return Promise.resolve(); }
        return Promise.all(inenler.map(function (p) {
            return getir(ucYolu(UC_ILERLEME, p.id)).then(function (y) {
                if (!y.ok || !y.govde) return false;
                var g = y.govde;
                p.progress = { bytes_done: g.bytes_done, bytes_total: g.bytes_total };
                p.error_code = g.error_code || null;
                if (g.state !== 'downloading') return true;       // bitti/iptal/hata
                return false;
            }, function () { return false; });
        })).then(function (degisti) {
            if (degisti.some(Boolean)) return listeYukle().then(ciz);
            ciz();
        });
    }

    // Künye: paket bindirmesi ya da paket yer adı ekrandayken görünür.
    function kunyeGuncelle() {
        var n = panel.kunye;
        if (!n) return;
        var g = global.launchGlobe, L = global.launchLabels;
        var ti = (g && g.getTileInfo) ? g.getTileInfo() : null;
        var li = (L && L.getInfo) ? L.getInfo() : null;
        var acik = !!((ti && ti.pack && ti.pack.active)
                      || (li && li.paket && li.paket.gorunur > 0));
        var anahtar = ti && ti.pack && ti.pack.attributionKey;
        if (anahtar && n.getAttribute('data-i18n') !== anahtar) {
            n.setAttribute('data-i18n', anahtar);
            if (I() && I().applyTo) I().applyTo(n);
        }
        n.style.display = (acik && anahtar) ? '' : 'none';
        goruntuKunyesi(!!(ti && ti.pack && ti.pack.active));
    }

    //: V307/FS-HARİTA-GÖRÜNTÜ — görüntü bildirimi ('Contains modified
    //: Copernicus Sentinel data <yıllar>'; Copernicus hukuki bildiriminin
    //: değiştirilmiş veri için öngördüğü cümle, metni paket listesinden).
    //: Görünür: paket bindirmesi ekranda VE görünen alanla kesişen kurulu
    //: bir paketin görüntü bileşeni kurulu. Görünen alan ölçülemezse
    //: (küre/etiket modülü yok) kurulu bütün görüntü bileşenleri sayılır:
    //: görüntü ekrandayken bildirimin eksik kalmaması için.
    function goruntuKunyesi(bindirme) {
        var n = panel.kunyeGoruntu;
        if (!n) return;
        var bildirimler = [];
        if (bindirme) {
            var kutu = null, g = global.launchGlobe, LL = global.LaunchSiteLabels;
            var f = (g && g.getTrackingContext) ? g.getTrackingContext() : null;
            if (f && LL && typeof LL.gorunenKutu === 'function') {
                var gk = LL.gorunenKutu(f.camera, f.globeRadius);
                if (gk && gk.kutu) kutu = gk.kutu;
            }
            for (var i = 0; i < depo.paketler.length; i++) {
                var p = depo.paketler[i], go = goruntuOzeti(p);
                if (!p || p.status !== 'installed' || !go || !go.kurulu) continue;
                var b = p.bbox;
                if (kutu && !(Array.isArray(b) && b.length === 4 && b[0] < kutu[2] && kutu[0] < b[2]
                              && b[1] < kutu[3] && kutu[1] < b[3])) continue;
                if (bildirimler.indexOf(go.bildirim) < 0) bildirimler.push(go.bildirim);
            }
        }
        if (!bildirimler.length) { n.style.display = 'none'; return; }
        var metin = tf('site.mapPackImageryAttribution', { notice: bildirimler.join(' · ') });
        if (n.textContent !== metin) n.textContent = metin;
        n.style.display = '';
    }

    //: Paneli bağla. o: {liste, ozet, kunye, notlar, fetchImpl, document}
    //: (düğüm kimlikleri ya da öğeleri). Künye düğümü verilirse notlar
    //: kutusunun içine (karo künyesinin ardına) taşınır.
    function bind(o) {
        o = o || {};
        panel.doc = o.document || global.document;
        if (o.fetchImpl) depo.fetch = o.fetchImpl;
        var bul = function (x) { return (typeof x === 'string') ? panel.doc.getElementById(x) : x; };
        panel.liste = bul(o.liste);
        panel.ozet = bul(o.ozet);
        panel.kunye = bul(o.kunye);
        var notlar = bul(o.notlar), sonra = bul(o.kunyeSonrasi);
        if (panel.kunye && notlar && panel.kunye.parentNode !== notlar) {
            if (sonra && sonra.parentNode === notlar) notlar.insertBefore(panel.kunye, sonra.nextSibling);
            else notlar.appendChild(panel.kunye);
        }
        // Görüntü bildirimi düğümü: OSM künyesinin hemen ardında, aynı biçimde.
        if (panel.kunye && panel.kunye.parentNode && !panel.kunyeGoruntu) {
            var gk = panel.doc.createElement('div');
            gk.id = 'ls-pack-img-attr';
            gk.style.marginTop = panel.kunye.style.marginTop || '5px';
            gk.style.display = 'none';
            gk.setAttribute('data-paket-kunye', 'goruntu');
            panel.kunye.parentNode.insertBefore(gk, panel.kunye.nextSibling);
            panel.kunyeGoruntu = gk;
        }
        var x = I();
        if (x && x.onChange) x.onChange(function () { ciz(); });
        if (panel.kunye && !panel.kunyeZaman) panel.kunyeZaman = global.setInterval(kunyeGuncelle, KUNYE_MS);
        return listeYukle().then(function () { ciz(); return depo; });
    }

    global.LaunchSiteMapPacks = {
        bind: bind,
        yenile: function () { return listeYukle().then(function () { ciz(); return depo; }); },
        kuruluKutular: kuruluKutular,
        goruntuluKutular: goruntuluKutular,
        imza: imza,
        onChange: onChange,
        getInfo: function () {
            return { durum: depo.durum, hata: depo.hata, paketSayisi: depo.paketler.length,
                     kurulu: kuruluKutular().length, onay: panel.onay ? panel.onay.tur : null,
                     yokluyor: !!panel.yoklama };
        },
        // Saf yardımcılar (node bekçileri için)
        _hataMetni: hataMetni,
        _ilerlemeOzeti: ilerlemeOzeti,
        _ucYolu: ucYolu,
        _yokla: yokla,
        UC: { LISTE: UC_LISTE, INDIR: UC_INDIR, ILERLEME: UC_ILERLEME, IPTAL: UC_IPTAL, SIL: UC_SIL },
        HATA_ANAHTARI: HATA_ANAHTARI
    };

})(typeof window !== 'undefined' ? window : this);
