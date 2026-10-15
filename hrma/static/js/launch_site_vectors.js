/* HRMA — Fırlatma sahası küresi: vektör ayrıntı basamakları (LOD)
 * =================================================================
 * launch_site_vectors.js
 *
 * Tasarım: docs/scofield/raw/OH/UI/harita-detay/tasarim.md §3.1, §3.2, §3.5
 * (K2 satırı, §6). Karar §28-20 (Berke, 7 Eki 2026).
 *
 * NE ÇİZER
 * --------
 * Natural Earth kıyı, ülke sınırı, il sınırı, göl ve nehir çizgileri; üç
 * basamak (110m / 50m / 10m). Veri tools/build_map_detail_assets.py'nin
 * ürettiği HMV1 ikilileridir (hrma/static/map/vectors_*.bin + manifest).
 * Biçimin TEK tanımı o araçtır; bu dosya yalnız okur.
 *
 * DÜRÜSTLÜK
 * ---------
 *  - Çizgi süzgeci veri üreticisinin kendi alanıdır: her çizginin NE
 *    `min_zoom` değeri (manifestteki ölçekle uint8). Eşik uydurulmaz.
 *    255 = "kaynakta alan yok" -> her zaman görünür (K1 sözleşmesi).
 *  - Varlık yüklenemez ya da kanıtı tutmazsa (imza, boyut, sha256, blok
 *    sınırı) o basamak REDDEDİLİR, yerine yüklü en yakın kaba basamak kalır.
 *    110m bile yüklenemezse küre eski earth_borders.json görünümünü korur
 *    (launch_site_globe.js _buildBorders). Sahte çizgi ÜRETİLMEZ.
 *  - Basamak eşikleri (m/px) bu dosyanındır (manifestte bilinçli olarak
 *    YOK, K1 devri). Ölçek (m/px, z_web) kürenin kendisinden gelir:
 *    LaunchSiteGlobe.addFrameListener yükünde `metersPerPixel` ve `zWeb`.
 *
 * Bağımlılık: THREE (three-0.128.0) — SABİT sürüm. Yeni kütüphane yok.
 * Küre iç durumuna dokunulmaz: sahne, koordinat dönüşümü ve renk dönüşümü
 * kurucuya verilir (tek sahip: launch_site_globe.js).
 */
(function (global) {
    'use strict';

    // ---- Basamak tablosu (tasarım §3.2) -----------------------------------
    // Ekrandaki m/px > 20.000 -> 110m; 5.000-20.000 -> 50m; < 5.000 -> 10m.
    // Sıra kabadan inceye. `mppUst`: bu basamağın geçerli olduğu en büyük
    // m/px; ilk basamağın üst sınırı yoktur.
    var BASAMAKLAR = [
        { ad: '110m', mppUst: Infinity },
        { ad: '50m', mppUst: 20000.0 },
        { ad: '10m', mppUst: 5000.0 }
    ];
    // Histerezis: eşiğin ±%10'u (tasarım §3.2). İnceye geçiş eşik·0,9'un
    // altında, kabaya dönüş eşik·1,1'in üstünde olur; arada basamak korunur.
    var LOD_HISTEREZIS = 0.10;

    // Çizgi kaldırma (tasarım §3.2): yüzeyin üstünde max(2 m, 1e-4·irtifa).
    // Yakında 2 m (paralaks ~0), uzakta irtifayla büyür (derinlik çözünürlüğü).
    var KALDIRMA_MIN_M = 2.0;
    var KALDIRMA_ORANI = 1e-4;

    // Ufuk ayıklama payı [derece]: hücre kapağının açısına eklenir. Kapak
    // gerçek köşelerden ölçülmüş kutudan gelir; pay yalnız kayan nokta ve
    // kutu köşesi yaklaşıklığı içindir.
    var UFUK_PAYI_DEG = 0.5;

    // Kare başına geometri kurma bütçesi [ms]. Görünür hücrelerin hepsi
    // kurulana kadar ekranda bir önceki basamak kalır; geçiş tek karede olur.
    var KURMA_BUTCESI_MS = 6.0;

    // Katman görünüşü: kıyı > ülke > il > nehir (tasarım §3.2). 110m'deki
    // kıyı ve ülke değerleri eski görünümle aynıdır (_buildBorders), yani
    // tüm-Dünya görünümü basamak değişince kaymaz. Çizgi kalınlığı WebGL'de
    // 1 px'tir; ayrım renk ve opaklıkla yapılır. Hex sRGB'dir, srgb() ile
    // lineere çevrilir (P12aB4-20).
    var KATMAN_STILI = {
        coastline: { renk: 0x8fd6ff, opaklik: 0.34, sira: 4 },
        borders: { renk: 0xbfe6ff, opaklik: 0.50, sira: 5 },
        admin1: { renk: 0xbfe6ff, opaklik: 0.22, sira: 3 },
        lakes: { renk: 0x8fd6ff, opaklik: 0.30, sira: 2 },
        rivers: { renk: 0x5fb4ff, opaklik: 0.26, sira: 1 }
    };

    var HMV1_IMZA = 'HMV1';
    var HMV1_BASLIK_BAYT = 16;

    // Manifestteki varlık dosya adı izin listesi (karar §28-33; F1 denetimi
    // Ş4). Yalnız küçük harf, rakam, alt çizgi ve .bin/.json: '/', '..' ve
    // mutlak yol bu desenden geçemez, istek baseUrl dizininin dışına çıkamaz.
    // Aynı desen launch_site_labels.js'te de durur (iki modül bağımsız
    // yüklenir); bekçi ikisinin aynı olduğunu sınar.
    var DOSYA_ADI_DESENI = /^[a-z0-9_]+\.(bin|json)$/;
    // Manifestteki sha256 biçimi: 64 küçük onaltılık hane.
    var SHA256_DESENI = /^[0-9a-f]{64}$/;

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function deg2rad(d) { return d * Math.PI / 180.0; }

    // ---- Saf yardımcılar (node ile sınanır) -------------------------------

    //: Basamak seçimi, histerezisli. `onceki` bir basamak adı ya da null.
    function lodSec(mpp, onceki) {
        if (!(mpp > 0)) return onceki || BASAMAKLAR[0].ad;
        var i = -1;
        for (var k = 0; k < BASAMAKLAR.length; k++)
            if (BASAMAKLAR[k].ad === onceki) i = k;
        if (i < 0) {
            // İlk seçim: histerezis yok, doğrudan eşik.
            i = 0;
            while (i + 1 < BASAMAKLAR.length && mpp < BASAMAKLAR[i + 1].mppUst) i++;
            return BASAMAKLAR[i].ad;
        }
        // İnceye: bir sonraki basamağın eşiğinin %10 altına inilmeli.
        while (i + 1 < BASAMAKLAR.length &&
               mpp < BASAMAKLAR[i + 1].mppUst * (1 - LOD_HISTEREZIS)) i++;
        // Kabaya: bu basamağın eşiğinin %10 üstüne çıkılmalı.
        while (i > 0 && mpp > BASAMAKLAR[i].mppUst * (1 + LOD_HISTEREZIS)) i--;
        return BASAMAKLAR[i].ad;
    }

    //: Çizgi grubunun ölçeği: 1 + max(2 m, 1e-4·irtifa) / R.
    function kaldirmaOlcegi(camAltM, rEarthM) {
        var h = Math.max(KALDIRMA_MIN_M, KALDIRMA_ORANI * Math.max(camAltM, 0));
        return 1.0 + h / rEarthM;
    }

    //: Manifest kutusundan hücre kapağı: {x,y,z birim merkez, alfa [rad]}.
    //: Boylam açıklığı 180°'yi aşan kutu (tarih çizgisine değen hücre) için
    //: null döner: kapak tanımsızdır, hücre ufukla ayıklanmaz (yalnız three
    //: frustum ayıklaması kalır). Kutu istemcide TÜRETİLMEZ, manifestten gelir.
    function hucreKapagi(bbox) {
        if (!bbox || bbox.length !== 4) return null;
        var lo0 = bbox[0], la0 = bbox[1], lo1 = bbox[2], la1 = bbox[3];
        if (!(lo1 - lo0 <= 180.0) || !(la1 >= la0)) return null;
        var lam = deg2rad((lo0 + lo1) / 2), phi = deg2rad((la0 + la1) / 2);
        var c = [Math.cos(phi) * Math.cos(lam), Math.sin(phi), -Math.cos(phi) * Math.sin(lam)];
        // Dikdörtgenin merkezine en uzak noktası köşelerdedir (meridyen ve
        // paralel kenarları boyunca uzaklık köşeye doğru tekdüze artar).
        var alfa = 0;
        var koseler = [[lo0, la0], [lo0, la1], [lo1, la0], [lo1, la1]];
        for (var i = 0; i < 4; i++) {
            var l = deg2rad(koseler[i][0]), p = deg2rad(koseler[i][1]);
            var d = c[0] * Math.cos(p) * Math.cos(l) + c[1] * Math.sin(p) +
                    c[2] * (-Math.cos(p) * Math.sin(l));
            alfa = Math.max(alfa, Math.acos(clamp(d, -1, 1)));
        }
        return { x: c[0], y: c[1], z: c[2], alfa: alfa + deg2rad(UFUK_PAYI_DEG) };
    }

    //: Ufuk testi. `cam` kamera konumu (sahne birimi, küre merkezli), `R`
    //: küre yarıçapı, `olcek` çizgi kaldırma ölçeği. Kaldırılmış çizgi
    //: geometrik ufkun acos(1/olcek) kadar ötesinden de görünür; o açı eklenir.
    function ufuktaGorunur(kapak, cam, R, olcek) {
        if (!kapak) return true;
        var d = Math.sqrt(cam.x * cam.x + cam.y * cam.y + cam.z * cam.z);
        if (!(d > R)) return true;
        var tetaH = Math.acos(R / d) + Math.acos(clamp(1.0 / (olcek || 1), -1, 1));
        var sinir = tetaH + kapak.alfa;
        if (sinir >= Math.PI) return true;
        var nokta = (kapak.x * cam.x + kapak.y * cam.y + kapak.z * cam.z) / d;
        return nokta >= Math.cos(sinir);
    }

    //: HMV1 bloğu -> çizgi parçası konumları, min_zoom sırasında.
    //: Çizgiler min_zoom'a göre (255 = 0 sayılır) KARARLI sıralanır; böylece
    //: tek bir drawRange ile "min_zoom ≤ z" süzgeci tek çizim çağrısında olur.
    //: Dönüş: {positions Float32Array, esikler [min_zoom*10], kumulatif [köşe]}.
    function blokKonumlari(buf, hucre, koordOlcegi, yokKodu, latLonToXYZ, R) {
        var nv = hucre.vertex_count, nl = hucre.line_count, off = hucre.offset;
        var v = new Int32Array(buf, off, 2 * nv);
        var uz = new Uint32Array(buf, off + 8 * nv, nl);
        var mz = new Uint8Array(buf, off + 8 * nv + 4 * nl, nl);
        var bas = new Uint32Array(nl), anahtar = new Uint8Array(nl), sira = [];
        var s = 0, parca = 0, i;
        for (i = 0; i < nl; i++) {
            bas[i] = s; s += uz[i];
            anahtar[i] = (mz[i] === yokKodu) ? 0 : mz[i];
            if (uz[i] >= 2) parca += uz[i] - 1;
            sira.push(i);
        }
        sira.sort(function (a, b) { return (anahtar[a] - anahtar[b]) || (a - b); });
        var pos = new Float32Array(parca * 6), w = 0;
        var esikler = [], kumulatif = [];
        for (var k = 0; k < sira.length; k++) {
            var li = sira[k], n = uz[li], b0 = bas[li];
            for (var j = 0; j + 1 < n; j++) {
                var a = b0 + j;
                latLonToXYZ(v[2 * a + 1] / koordOlcegi, v[2 * a] / koordOlcegi, R, pos, w);
                latLonToXYZ(v[2 * a + 3] / koordOlcegi, v[2 * a + 2] / koordOlcegi, R, pos, w + 3);
                w += 6;
            }
            var son = (k + 1 === sira.length) || anahtar[sira[k + 1]] !== anahtar[li];
            if (son) { esikler.push(anahtar[li]); kumulatif.push(w / 3); }
        }
        return { positions: pos, esikler: esikler, kumulatif: kumulatif };
    }

    //: z_web'e göre çizilecek köşe sayısı (min_zoom*olcek ≤ z_web*olcek).
    function cizimSayisi(esikler, kumulatif, zWeb, zOlcegi) {
        var n = 0, sinir = zWeb * zOlcegi + 1e-9;
        for (var i = 0; i < esikler.length; i++) {
            if (esikler[i] <= sinir) n = kumulatif[i]; else break;
        }
        return n;
    }

    //: Basamak girdisinin İSTEKTEN ÖNCE sınanan kanıt alanları (fail-closed,
    //: karar §28-33): dosya adı izin listesinde, bayt sayısı ve sha256 var.
    //: Kanıtı eksik basamak hiç istenmez. Hata metni ya da null.
    function seviyeMetaDogrula(meta) {
        if (!meta || typeof meta.file !== 'string' || !DOSYA_ADI_DESENI.test(meta.file))
            return 'dosya_adi';
        if (!(typeof meta.bytes === 'number' && Number.isInteger(meta.bytes) && meta.bytes >= 0))
            return 'boyut_yok';
        if (typeof meta.sha256 !== 'string' || !SHA256_DESENI.test(meta.sha256))
            return 'sha256_yok';
        return null;
    }

    //: HMV1 ikilisini manifest girdisine karşı doğrular. Hata metni ya da null.
    //: Bayt sayısı yoksa da 'boyut' (denetim atlanmaz).
    function ikiliDogrula(buf, seviye) {
        if (!buf || buf.byteLength < HMV1_BASLIK_BAYT) return 'kisa';
        if (typeof seviye.bytes !== 'number' || buf.byteLength !== seviye.bytes) return 'boyut';
        var b = new Uint8Array(buf, 0, 4);
        if (String.fromCharCode(b[0], b[1], b[2], b[3]) !== HMV1_IMZA) return 'imza';
        var bas = new DataView(buf, 0, HMV1_BASLIK_BAYT);
        var nb = bas.getUint32(4, true), nv = bas.getUint32(8, true), nl = bas.getUint32(12, true);
        if (nb !== seviye.block_count || nv !== seviye.vertex_count || nl !== seviye.line_count)
            return 'baslik';
        var katmanlar = seviye.layers || {}, say = 0;
        for (var ad in katmanlar) {
            if (!Object.prototype.hasOwnProperty.call(katmanlar, ad)) continue;
            var hucreler = katmanlar[ad].cells || [];
            for (var i = 0; i < hucreler.length; i++) {
                var h = hucreler[i];
                if (h.offset % 4 !== 0 || h.offset < HMV1_BASLIK_BAYT) return 'hizalama';
                if (h.offset + 8 * h.vertex_count + 5 * h.line_count > buf.byteLength) return 'tasma';
                var uz = new Uint32Array(buf, h.offset + 8 * h.vertex_count, h.line_count);
                var t = 0;
                for (var j = 0; j < uz.length; j++) t += uz[j];
                if (t !== h.vertex_count) return 'cizgi_toplami';
                say += 1;
            }
        }
        if (say !== nb) return 'blok_sayisi';
        return null;
    }

    function hexOzet(buf) {
        var b = new Uint8Array(buf), s = '';
        for (var i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16);
        return s;
    }

    // ===================================================================
    // LaunchSiteVectors
    // ===================================================================
    // opts: THREE, scene, latLonToXYZ(lat, lon, r, out, i), srgb(hex),
    //       globeRadius, rEarthM, baseUrl, fetchImpl?, digestImpl?,
    //       onReady?, onFail?
    function LaunchSiteVectors(opts) {
        this.opts = opts;
        this.THREE = opts.THREE;
        this.R = opts.globeRadius;
        this._fetch = opts.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
        this._digest = opts.digestImpl || null;
        if (!this._digest && global.crypto && global.crypto.subtle && global.crypto.subtle.digest) {
            var sub = global.crypto.subtle;
            this._digest = function (buf) {
                return sub.digest('SHA-256', buf).then(hexOzet);
            };
        }
        this.durum = 'bekliyor';     // bekliyor | yukleniyor | hazir | hata
        this.hata = null;
        this.manifest = null;
        this.seviyeler = {};         // ad -> {meta, durum, buf, grup, hucreler[], hata}
        this._hedef = null;          // histerezisli istenen basamak
        this._goster = null;         // ekranda çizilen basamak
        this._z = null;
        this._sayac = { cizilenHucre: 0, cizilenKose: 0 };
        // Görüş piramidi ayıklaması için yeniden kullanılan nesneler. three
        // aynı ayıklamayı çizimde de yapar; burada da yapılır ki sayaçlar
        // (çizilen hücre = çizim çağrısı) GERÇEK çizimi ölçsün.
        this._frustum = new this.THREE.Frustum();
        this._pv = new this.THREE.Matrix4();
        this._kure = new this.THREE.Sphere();
        this._shaDogrulandi = {};
        this.kok = new this.THREE.Group();
        this.kok.name = 'launch_site_vectors';
        this.kok.visible = false;
        opts.scene.add(this.kok);
    }

    LaunchSiteVectors.prototype._url = function (ad) {
        return (this.opts.baseUrl || '/static/map/') + ad;
    };

    LaunchSiteVectors.prototype._getir = function (ad, tur) {
        if (!this._fetch) return Promise.reject(new Error('fetch_yok'));
        return this._fetch(this._url(ad)).then(function (r) {
            if (!r || !r.ok) throw new Error('http');
            return tur === 'json' ? r.json() : r.arrayBuffer();
        });
    };

    LaunchSiteVectors.prototype.start = function () {
        var self = this;
        this.durum = 'yukleniyor';
        return this._getir('vectors_manifest.json', 'json').then(function (m) {
            var neden = self._manifestDogrula(m);
            if (neden) throw new Error('manifest_' + neden);
            self.manifest = m;
            for (var i = 0; i < BASAMAKLAR.length; i++) {
                var ad = BASAMAKLAR[i].ad;
                self.seviyeler[ad] = { ad: ad, meta: m.levels[ad], durum: 'yok',
                                       buf: null, grup: null, hucreler: null, hata: null };
            }
            return self._seviyeYukle('110m');
        }).then(function (sv) {
            if (self._disposed) return;
            if (!sv || sv.durum !== 'yuklu') throw new Error('110m_' + (sv && sv.hata));
            self.durum = 'hazir';
            self.kok.visible = true;
            self._seviyeYukle('50m');          // küçük (~1 MB): hemen
            if (self.opts.onReady) self.opts.onReady();
        }).catch(function (e) {
            if (self._disposed) return;
            self._basarisiz(String(e && e.message || e));
        });
    };

    LaunchSiteVectors.prototype._basarisiz = function (neden) {
        this.durum = 'hata';
        this.hata = neden;
        this.kok.visible = false;
        if (this.opts.onFail) this.opts.onFail(neden);
    };

    LaunchSiteVectors.prototype._manifestDogrula = function (m) {
        if (!m || m.format !== HMV1_IMZA) return 'bicim';
        if (m.byte_order !== 'little') return 'bayt_sirasi';
        if (!(m.coord_scale > 0) || !(m.min_zoom_scale > 0)) return 'olcek';
        if (!m.levels) return 'seviye';
        for (var i = 0; i < BASAMAKLAR.length; i++)
            if (!m.levels[BASAMAKLAR[i].ad]) return 'seviye_' + BASAMAKLAR[i].ad;
        return null;
    };

    LaunchSiteVectors.prototype._seviyeYukle = function (ad) {
        var self = this, sv = this.seviyeler[ad];
        if (!sv) return Promise.resolve(null);
        if (sv.durum !== 'yok') return sv.soz || Promise.resolve(sv);
        sv.durum = 'yukleniyor';
        var onNeden = seviyeMetaDogrula(sv.meta);
        var istek = onNeden ? Promise.reject(new Error(onNeden))
                            : this._getir(sv.meta.file, 'bin');
        sv.soz = istek.then(function (buf) {
            var neden = ikiliDogrula(buf, sv.meta);
            if (neden) throw new Error(neden);
            if (!self._digest) { self._shaDogrulandi[ad] = false; return buf; }
            return self._digest(buf).then(function (ozet) {
                if (!sv.meta.sha256 || ozet !== sv.meta.sha256) throw new Error('sha256');
                self._shaDogrulandi[ad] = true;
                return buf;
            });
        }).then(function (buf) {
            if (self._disposed) return sv;
            sv.buf = buf;
            self._seviyeKur(sv);
            sv.durum = 'yuklu';
            return sv;
        }).catch(function (e) {
            sv.durum = 'hata';
            sv.hata = String(e && e.message || e);
            return sv;
        });
        return sv.soz;
    };

    // Seviyenin hücre listesi (geometri henüz kurulmaz; görünür olunca kurulur).
    LaunchSiteVectors.prototype._seviyeKur = function (sv) {
        var THREE = this.THREE, grup = new THREE.Group();
        grup.name = 'vektor_' + sv.ad;
        grup.visible = false;
        var hucreler = [], katmanlar = sv.meta.layers || {};
        for (var ad in katmanlar) {
            if (!Object.prototype.hasOwnProperty.call(katmanlar, ad)) continue;
            var stil = KATMAN_STILI[ad];
            if (!stil) continue;              // tanımsız katman çizilmez (fail-closed)
            var mat = new THREE.LineBasicMaterial({
                color: this.opts.srgb(stil.renk), transparent: true,
                opacity: stil.opaklik, depthWrite: false
            });
            var liste = katmanlar[ad].cells || [];
            for (var i = 0; i < liste.length; i++) {
                hucreler.push({ katman: ad, meta: liste[i], kapak: hucreKapagi(liste[i].bbox),
                                malzeme: mat, mesh: null, esikler: null, kumulatif: null,
                                sira: stil.sira });
            }
        }
        sv.grup = grup;
        sv.hucreler = hucreler;
        this.kok.add(grup);
    };

    LaunchSiteVectors.prototype._hucreKur = function (sv, h) {
        var THREE = this.THREE, m = this.manifest;
        var k = blokKonumlari(sv.buf, h.meta, m.coord_scale, m.min_zoom_absent,
                              this.opts.latLonToXYZ, this.R);
        var g = new THREE.BufferGeometry();
        g.setAttribute('position', new THREE.BufferAttribute(k.positions, 3));
        g.computeBoundingSphere();
        var mesh = new THREE.LineSegments(g, h.malzeme);
        mesh.renderOrder = h.sira;
        mesh.visible = false;
        h.mesh = mesh;
        h.esikler = k.esikler;
        h.kumulatif = k.kumulatif;
        sv.grup.add(mesh);
    };

    // Görünür hücrelerin hepsi kurulu mu? Değilse bütçe içinde kurar.
    LaunchSiteVectors.prototype._gorunurKur = function (sv, gorunur, bitis) {
        var tamam = true;
        for (var i = 0; i < sv.hucreler.length; i++) {
            if (!gorunur[i] || sv.hucreler[i].mesh) continue;
            if (this._simdi() > bitis && !this._ilkKurma) { tamam = false; continue; }
            this._hucreKur(sv, sv.hucreler[i]);
            this._ilkKurma = false;
        }
        return tamam;
    };

    LaunchSiteVectors.prototype._simdi = function () {
        return (global.performance && global.performance.now) ? global.performance.now() : Date.now();
    };

    LaunchSiteVectors.prototype._gorunurler = function (sv, cam, olcek) {
        var g = new Array(sv.hucreler.length);
        for (var i = 0; i < sv.hucreler.length; i++)
            g[i] = ufuktaGorunur(sv.hucreler[i].kapak, cam, this.R, olcek);
        return g;
    };

    LaunchSiteVectors.prototype._yuklu = function (ad) {
        var sv = this.seviyeler[ad];
        return !!(sv && sv.durum === 'yuklu');
    };

    // Kare kancası (LaunchSiteGlobe.addFrameListener yükü).
    LaunchSiteVectors.prototype.update = function (f) {
        if (this.durum !== 'hazir' || this._disposed) return;
        try {
            this._guncelle(f);
        } catch (e) {
            this._basarisiz('guncelleme_' + String(e && e.message || e));
        }
    };

    LaunchSiteVectors.prototype._guncelle = function (f) {
        var hedef = lodSec(f.metersPerPixel, this._hedef);
        this._hedef = hedef;
        var hi = this._indis(hedef);
        this._seviyeYukle(hedef);
        // Bir basamak ileriyi önceden iste: 50m ekrandayken 10m (~11 MB)
        // inmeye başlasın, kullanıcı yakınlaşınca beklemesin.
        if (hi + 1 < BASAMAKLAR.length && hi >= 1) this._seviyeYukle(BASAMAKLAR[hi + 1].ad);

        var olcek = kaldirmaOlcegi(f.camAltitudeM, this.opts.rEarthM);
        this.kok.scale.setScalar(olcek);
        var cam = f.camera.position;
        var bitis = this._simdi() + KURMA_BUTCESI_MS;
        this._ilkKurma = true;

        // Gösterilecek basamak: hedef yüklü ve görünür hücreleri kuruluysa
        // hedef; değilse ekrandaki basamak; o da yoksa yüklü en yakın kaba.
        var goster = null, gorunur = null;
        if (this._yuklu(hedef)) {
            var g = this._gorunurler(this.seviyeler[hedef], cam, olcek);
            if (this._gorunurKur(this.seviyeler[hedef], g, bitis)) { goster = hedef; gorunur = g; }
        }
        if (!goster) {
            var aday = (this._goster && this._yuklu(this._goster)) ? this._goster : null;
            for (var i = hi - 1; !aday && i >= 0; i--)
                if (this._yuklu(BASAMAKLAR[i].ad)) aday = BASAMAKLAR[i].ad;
            // Daha kaba yüklü basamak yoksa hedef, kurulduğu kadarıyla çizilir.
            if (!aday && this._yuklu(hedef)) aday = hedef;
            if (!aday) return;
            goster = aday;
            gorunur = this._gorunurler(this.seviyeler[goster], cam, olcek);
            this._ilkKurma = true;
            this._gorunurKur(this.seviyeler[goster], gorunur, bitis);
        }
        this._goster = goster;
        this._z = f.zWeb;

        var kamera = f.camera;
        kamera.updateMatrixWorld();
        this._pv.multiplyMatrices(kamera.projectionMatrix, kamera.matrixWorldInverse);
        this._frustum.setFromProjectionMatrix(this._pv);
        var zOlcegi = this.manifest.min_zoom_scale, hucreSay = 0, koseSay = 0;
        for (var b = 0; b < BASAMAKLAR.length; b++) {
            var sv = this.seviyeler[BASAMAKLAR[b].ad];
            if (!sv || !sv.grup) continue;
            var aktif = (sv.ad === goster);
            sv.grup.visible = aktif;
            if (!aktif) continue;
            for (var j = 0; j < sv.hucreler.length; j++) {
                var h = sv.hucreler[j];
                if (!h.mesh) continue;
                var n = gorunur[j] ? cizimSayisi(h.esikler, h.kumulatif, f.zWeb, zOlcegi) : 0;
                if (n > 0) {
                    var bs = h.mesh.geometry.boundingSphere;
                    this._kure.center.copy(bs.center).multiplyScalar(olcek);
                    this._kure.radius = bs.radius * olcek;
                    if (!this._frustum.intersectsSphere(this._kure)) n = 0;
                }
                h.mesh.geometry.setDrawRange(0, n);
                h.mesh.visible = n > 0;
                if (n > 0) { hucreSay += 1; koseSay += n; }
            }
        }
        this._sayac.cizilenHucre = hucreSay;
        this._sayac.cizilenKose = koseSay;
    };

    LaunchSiteVectors.prototype._indis = function (ad) {
        for (var i = 0; i < BASAMAKLAR.length; i++) if (BASAMAKLAR[i].ad === ad) return i;
        return 0;
    };

    // Ölçüm kancası (K3 notu, K6 kabul ölçümü, testler). Sayılar canlıdır.
    // Manifest künyesindeki sınır düzeltmesi (karar §28-45/Kırım): düşülen
    // çizgi sayısı (her basamak aynı coğrafi çizgiyi düşer -> basamaklar
    // arasında en büyüğü) ve karar metni. Alan yoksa null (düzeltme yok);
    // sayılar negatif olmayan tam sayı değilse ya da karar metni yoksa null:
    // künye satırı basılmaz, sayı uydurulmaz.
    function sinirDuzeltmesi(manifest) {
        var bc = manifest && manifest.provenance && manifest.provenance.boundary_corrections;
        if (!bc || typeof bc !== 'object') return null;
        var dl = bc.dropped_lines, n = 0, adet = 0;
        if (!dl || typeof dl !== 'object' || typeof bc.decision !== 'string' || !bc.decision) return null;
        for (var k in dl) {
            if (!Object.prototype.hasOwnProperty.call(dl, k)) continue;
            var v = dl[k];
            if (typeof v !== 'number' || !isFinite(v) || v < 0 || Math.floor(v) !== v) return null;
            n = Math.max(n, v); adet++;
        }
        if (!adet) return null;
        return { cizgi: n, karar: bc.decision };
    }

    LaunchSiteVectors.prototype.getInfo = function () {
        var seviyeler = {};
        for (var ad in this.seviyeler) {
            if (!Object.prototype.hasOwnProperty.call(this.seviyeler, ad)) continue;
            var sv = this.seviyeler[ad], kurulu = 0;
            if (sv.hucreler) for (var i = 0; i < sv.hucreler.length; i++) if (sv.hucreler[i].mesh) kurulu++;
            seviyeler[ad] = { durum: sv.durum, hata: sv.hata, kuruluHucre: kurulu,
                              hucre: sv.hucreler ? sv.hucreler.length : 0,
                              shaDogrulandi: this._shaDogrulandi[ad] === true,
                              nominalScale: sv.meta ? sv.meta.nominal_scale : null };
        }
        return {
            durum: this.durum,
            hata: this.hata,
            hedef: this._hedef,
            goster: this._goster,
            nominalScale: (this._goster && this.seviyeler[this._goster])
                ? this.seviyeler[this._goster].meta.nominal_scale : null,
            zWeb: this._z,
            cizilenHucre: this._sayac.cizilenHucre,
            cizilenKose: this._sayac.cizilenKose,
            seviyeler: seviyeler,
            atif: this.manifest && this.manifest.provenance
                ? this.manifest.provenance.attribution : null,
            sinirGorunumu: this.manifest && this.manifest.provenance
                ? this.manifest.provenance.boundary_view : null,
            // HRK devri (4. tur): künye sınır düzeltmesini de yayımlar.
            sinirDuzeltmesi: sinirDuzeltmesi(this.manifest)
        };
    };

    LaunchSiteVectors.prototype.dispose = function () {
        this._disposed = true;
        var malzemeler = [];
        for (var ad in this.seviyeler) {
            if (!Object.prototype.hasOwnProperty.call(this.seviyeler, ad)) continue;
            var sv = this.seviyeler[ad];
            if (!sv.hucreler) continue;
            for (var i = 0; i < sv.hucreler.length; i++) {
                var h = sv.hucreler[i];
                if (h.mesh) { h.mesh.geometry.dispose(); h.mesh = null; }
                if (malzemeler.indexOf(h.malzeme) < 0) malzemeler.push(h.malzeme);
            }
            sv.buf = null;
        }
        for (var j = 0; j < malzemeler.length; j++) malzemeler[j].dispose();
        if (this.kok.parent) this.kok.parent.remove(this.kok);
    };

    // Dışa aç (saf yardımcılar node bekçileri için)
    LaunchSiteVectors.BASAMAKLAR = BASAMAKLAR;
    LaunchSiteVectors.LOD_HISTEREZIS = LOD_HISTEREZIS;
    LaunchSiteVectors.lodSec = lodSec;
    LaunchSiteVectors.kaldirmaOlcegi = kaldirmaOlcegi;
    LaunchSiteVectors.hucreKapagi = hucreKapagi;
    LaunchSiteVectors.ufuktaGorunur = ufuktaGorunur;
    LaunchSiteVectors.blokKonumlari = blokKonumlari;
    LaunchSiteVectors.cizimSayisi = cizimSayisi;
    LaunchSiteVectors.ikiliDogrula = ikiliDogrula;
    LaunchSiteVectors.seviyeMetaDogrula = seviyeMetaDogrula;
    LaunchSiteVectors.DOSYA_ADI_DESENI = DOSYA_ADI_DESENI;
    LaunchSiteVectors.UFUK_PAYI_DEG = UFUK_PAYI_DEG;
    LaunchSiteVectors.sinirDuzeltmesi = sinirDuzeltmesi;
    global.LaunchSiteVectors = LaunchSiteVectors;

})(typeof window !== 'undefined' ? window : this);
