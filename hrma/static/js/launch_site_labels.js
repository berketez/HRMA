/* HRMA — Fırlatma sahası küresi: şehir ve ülke etiketleri (DOM bindirmesi)
 * =======================================================================
 * launch_site_labels.js
 *
 * Tasarım: docs/scofield/raw/OH/UI/harita-detay/tasarim.md §3.3, §3.5,
 * §5.2, §5.3 (K3 satırı, §6). Karar §28-20 (Berke, 7 Eki 2026).
 *
 * NE YAPAR
 * --------
 * Natural Earth yer adlarını (ne_10m_populated_places) ve ülke adlarını
 * (ne_10m_admin_0_countries etiket noktaları) kürenin üstüne, tuvalin
 * üzerindeki bir <div> içinde DOM öğeleri olarak basar. Veri
 * tools/build_map_detail_assets.py'nin ürettiği places.json ve
 * country_labels.json'dur; biçimin TEK tanımı o araçtır, bu dosya okur.
 *
 * ALGORİTMA (tasarım §3.3, kamera değiştiğinde, en çok kare başına bir kez)
 * ---------
 *  1. Aday: yerler yüklemede 10°'lik enlem/boylam kovalarına dizinlenir.
 *     Kameranın gördüğü küresel başlığa (ufuk açısı) değen kovalar okunur.
 *  2. Zoom süzgeci: yer, NE'nin kendi MIN_ZOOM alanı z_web'e eşit ya da
 *     küçükse adaydır; ülke, MIN_LABEL <= z_web <= MAX_LABEL ise. Eşik
 *     UYDURULMAZ; alanı olmayan kayıt hiç basılmaz ve sayılır.
 *  3. Ufuk: dot(p̂, kamera - p) > 0 olan nokta görünür; arka yüz atılır.
 *  4. Öncelik: önce ülke adları (dosya sırası: LABELRANK, MIN_LABEL), sonra
 *     yerler DOSYA SIRASINDA. K1 dosyayı başkent > LABELRANK küçük >
 *     POP_MAX büyük sırasıyla yazar; POP_MAX dosyada yoktur (tasarım
 *     §5.3-4), bu yüzden istemci sırayı yeniden kurmaz, dosyaya güvenir.
 *  5. Çakışma: ekran 64 px'lik ızgaraya bölünür; her etiketin dikdörtgeni
 *     yalnız kapladığı hücrelerdeki yerleşmiş dikdörtgenlerle sınanır.
 *     Çakışan o karede gizlenir.
 *  6. Histerezis: bir önceki karede gösterilen etiket (a) öncelik sırasında
 *     ONCELIK_PAYI kadar önde yarışır (yakın önemdeki yeni bir etiket onu
 *     söküp atamaz; çok daha önemli olan yine geçer); (b) çakışma sınavına
 *     pay olmadan girer, yeni etiket YENI_ETIKET_PAYI_PX kadar boşluk ister;
 *     (c) zoom süzgecinde Z_HISTEREZIS kadar geç kaybolur. Ekran ölçütü
 *     çapadır (nokta ya da metin ortası ekranda); kenarda taşan metni
 *     bindirme keser. Kaydırırken sınırdaki etiketler titremez.
 *  7. Havuz: ETIKET_TAVANI kadar DOM öğesi bir kez kurulur ve yeniden
 *     kullanılır; kare başına öğe kurulmaz. Konum yalnız `transform` ile
 *     verilir. Ekranda kalan etiketin öğesi değişmez (metin yazılmaz).
 *  8. Dil: TR arayüzde NAME_TR, yoksa NAME; EN'de NAME_EN, yoksa NAME.
 *     Dil değişince etiketler yeniden basılır.
 *  9. Nokta da DOM'dadır (ekran sabit boyut); başkent halka, şehir nokta.
 *     Katman pointer-events: none -> saha seçimi (raycast) bozulmaz.
 * 10. Engel: sayfanın panelleri (opts.getObstacles) ızgaraya etiketten önce
 *     yazılır; panel altında yarısı görünen etiket basılmaz, tavan boşa
 *     harcanmaz (K3 ölçümü, rapor).
 *
 * DÜRÜSTLÜK (tasarım §5.3)
 * ---------
 *  - Nüfus ekranda GÖSTERİLMEZ (dosyada da yok).
 *  - Varlık yüklenemez ya da kanıtı (bayt sayısı, sha256) manifestle
 *    tutmazsa hiç etiket basılmaz; durum ve neden getInfo()'da durur.
 *    Sahte yer, sahte ad üretilmez.
 *  - Ölçek (m/px, z_web) kürenin kare kancasından gelir (f.zWeb TEK
 *    tanımdır; bu dosya kendi log2 sabitini tutmaz).
 *
 * Bağımlılık: yok (THREE gerekmez; izdüşüm kameranın kendi matrislerinden).
 * Küre iç durumuna dokunulmaz: LaunchSiteGlobe.addFrameListener ile beslenir.
 */
(function (global) {
    'use strict';

    // ---- Sabitler (tasarım §3.3, §3.5) ------------------------------------
    var ETIKET_TAVANI = 150;          // ekranda en çok bu kadar etiket (§3.5)
    // Tüm Dünya bandı (tasarım §5.2 'tüm Dünya <= 40 etiket'; ana model
    // kararı K-2, 14 Eki 2026): ölçüt §3.2'nin İLK bandına bağlıdır, yani
    // ekran m/px > 20.000 (110m basamağı). Bu bantta en çok bu kadar etiket
    // basılır; fazlası öncelik sırasıyla (§3.3-4: ülke adları, sonra dosya
    // sırası = başkent > LABELRANK > POP_MAX) kesilir. Bant eşiğinin TEK
    // tanımı launch_site_vectors.js BASAMAKLAR'dır (şablonda bu dosyadan önce
    // yüklenir); burada ikinci kopya yok. Ölçüm (rapor, 4. tur): bant
    // girişinde (20.050 m/px) Sinop 68-70, Esrange 57-59 etiket veriyordu.
    var DUNYA_ETIKET_TAVANI = 40;
    // K-2 eki (ana model kararı, 14 Eki 2026): sayfanın 'Tüm Dünya' düğmesi
    // (viewGlobe) 1440x900'de 19.935 m/px'e konuyordu, yani bandın %0,3
    // altında; sayı pencere boyuna göre kayıyordu. Tavan bu yüzden kamera
    // Dünya merkezinden düğmenin mesafesi kadar ya da daha uzaktayken de
    // uygulanır. Mesafenin TEK kaynağı launch_site_globe.js globalViewDist'tir
    // (kare yükündeki f.globalViewDist); burada kopyası yok. Düğmenin kamera
    // geçişi (lerp) son konumu kayan nokta yuvarlamasıyla birkaç ulp eksik
    // bırakabildiği için karşılaştırma bu göreli payla yapılır.
    var TUM_DUNYA_MESAFE_GORELI_PAY = 1e-6;
    var HAVUZ_BOYUTU = ETIKET_TAVANI; // DOM havuzu: bir kez kurulur
    var KOVA_DERECE = 10;             // enlem/boylam kova açıklığı
    var IZGARA_PX = 64;               // çakışma ızgarası hücresi
    var Z_HISTEREZIS = 0.1;           // gösterilen etiket z_web'de bu kadar geç kaybolur
    // Yeni etiket bu kadar boşluk ister (histerezis payı, §3.3-5). 3 -> 6
    // (ana model kararı K-3, 14 Eki 2026; ölçüm rapor 4. tur): ekran
    // merkezindeki yer noktası 300 px/s kayarken yeni etiket panel aralığına
    // (sayfada 22 px) sığıp iki kare görünüyor, sonra panelin altında
    // kayboluyordu (Karabük, Tampa: 4 değişim / 2 s); 14 + 2·6 > 22.
    // Panel ile ekran kenarı arasındaki 14 px'lik şerit 11+ px ister; 12 px
    // ölçüldü (16/16 ölçümde <= 2) ama mevcut Ş2 bekçisini (üst şeride 10 px
    // kalan etiket basılır) kırar ve 1.500 km Türkiye pozunda İstanbul'u
    // (panele 8 px) gizler: alınmadı. Şerit kenar kuralıyla (KENAR_SERIDI_PX,
    // ana model kararı K-3 seçenek b) kapatıldı; pay 6 aynı kaldı.
    var YENI_ETIKET_PAYI_PX = 6;
    var ONCELIK_PAYI = 512;           // gösterilen etiket bu kadar sıra önde yarışır (ölçüldü, rapor K3)
    var OLCUM_PENCERESI = 240;        // güncelleme süresi örnek sayısı (medyan/p95)
    var ENGEL_YENILEME_MS = 250;      // panel kutuları en çok bu aralıkla yeniden okunur
    // Değişim imzası: kamera dünya matrisi (16) + izdüşüm (4) + tuval (2) +
    // yarıçap + z_web + sürüm sayacı = 25 değer.
    var IMZA_UZUNLUGU = 25;

    // Etiket geometrisi. Dikdörtgen hesabı ile DOM yerleşimi AYNI sayılardan
    // gelir: öğelerin konum/ölçü stilleri burada kurulur, CSS yalnız renk ve
    // gölge verir. Böylece "çakışma yok" iddiası ekrandaki kutuya dayanır.
    var SATIR_PX = 14;                // satır yüksekliği (her iki tür)
    // Kenar şeridi (ana model kararı K-3 seçenek b, 14 Eki 2026): engel
    // kutusu ile ekran kenarı arasında BİR ETİKET SATIRINDAN geniş olmayan
    // şerit de engel sayılır (kutu o kenara uzatılır). Sayfada paneller
    // kenardan 14 px içeride durur; o şeritte yeni etiket payıyla (6 px)
    // tam sığamaz, yalnız ekran kenarından taşarak girip panel altına
    // kayınca sökülüyordu (300 px/s'de Giresun 3, Mahabad 4 değişim / 2 s).
    // Eşik satır yüksekliğinin kendisidir (ikinci literal yok); eşit genişlik
    // de engeldir, çünkü o şerit bir satırı ancak SIFIR payla taşır.
    var KENAR_SERIDI_PX = SATIR_PX;
    var NOKTA_PX = 6;                 // şehir noktası çapı
    var HALKA_PX = 8;                 // başkent halkası dış çapı
    var METIN_X_PX = 6;               // nokta merkezinden metnin soluna
    var SEHIR_YAZI = { agirlik: 600, boyut: 11 };
    var ULKE_YAZI = { agirlik: 500, boyut: 12 };

    var BASKENT_SINIFI = 'Admin-0 capital';
    // V307/FS-HARİTA-KÜRE: TUR_RAMPA = paketten fırlatma kompleksi/rampa adı
    // (geometrisi şehir noktasıyla aynı; sınıf adı ls-lbl-pad).
    var TUR_SEHIR = 0, TUR_BASKENT = 1, TUR_ULKE = 2, TUR_RAMPA = 3;

    var YER_ALANLARI = ['lon', 'lat', 'name', 'name_en', 'name_tr', 'min_zoom', 'featurecla'];

    /* V307 / FS-HARİTA (9 Kas 2026) — YAKIN ÖLÇEK YER ADLARI (GeoNames).
       ÖLÇÜLDÜ (kanıt ~/HRMA-calisma/2026-11-09/FS-HARITA/olcum/once):
       Natural Earth places.json 7.342 yer taşır (Türkiye 83); İstanbul'a
       25 km'den bakınca ekranda yalnız 'İstanbul', Cape Canaveral'da 0
       etiket vardı. NE'nin MIN_ZOOM alanı z_web 9'da biter (dosyadaki en
       büyük değer), yani o ölçeğin ötesinde NE'nin gösterecek yeni yeri
       yoktur. Ana model kararı (9 Kas): GeoNames cities5000 (70.019 yer,
       CC BY 4.0) paketlenir ve YALNIZ z_web, NE'nin kendi en büyük
       MIN_ZOOM değerini AŞINCA aday olur (eşik veriden okunur, icat
       edilmez). Sıra dosya sırasıdır (nüfus azalan); yoğunluğu mevcut
       çakışma ızgarası ve 150 etiket tavanı belirler. Veri ilk gerektiği an
       (tembel) kanıtla okunur: ayrı manifestteki bayt + sha256 tutmazsa
       katman 'hata' olur, NE etiketleri etkilenmez. Aynı ad (aksan ve
       büyük/küçük harf katlanmış) ekranda zaten varsa ikinci kez basılmaz
       (NE 'Istanbul' ile GeoNames 'Istanbul' aynı şehirdir). Veride Türkçe
       ya da İngilizce ad yoktur: yerel ad basılır (künyede yazılı). */
    var DETAY_MANIFEST = 'places_detail_manifest.json';
    var DETAY_ALANLARI = ['lon', 'lat', 'name', 'pop', 'cc', 'fcode'];
    var DETAY_KOVA_DERECE = 1;        // enlem/boylam kova açıklığı (yakın ölçek)
    var DETAY_BASKENT_KODU = 'PPLC';  // GeoNames özellik kodu: ülke başkenti

    /* V307 / FS-HARİTA-KÜRE (16 Kas 2026) — İNDİRİLEN PAKETTEN YER ADLARI.
       Kurulu bir harita paketi (LaunchSiteMapPacks.kuruluKutular) görünen
       bölgeyle kesişiyorsa yer adları (yerleşim, mahalle) ve fırlatma
       kompleksi/rampa adları sunucunun etiket ucundan okunur (uç sözleşmesi
       brif_16kas/FS_HARITA_VERI_FAZ2.md). Ad politikası (karar K6) SUNUCUDA
       uygulanır; istemci yalnız dili ('tr' | 'en') gönderir ve gelen adı
       basar. İstek düzeyi görünümün GERÇEK Web Mercator düzeyidir (kürenin
       kare yükü f.zMercator = z_web + log2(cos φ); ölçeğin tek sahibi küre),
       tabana yuvarlanır, sözleşmenin 0..15 aralığına kırpılır; yer, kendi
       rank (OSM min_zoom) değeri bu düzeyden küçük ya da eşitken adaydır
       (NE/GeoNames ile aynı histerezis). Paket adları NE ve GeoNames'ten
       SONRA yarışır; aynı ad (katlanmış) ekranda varsa ikinci kez basılmaz.
       Yoğunluk mevcut ızgara ve etiket tavanıyla sınırlıdır. Devreye girme
       eşiği GeoNames'inkiyle aynıdır (z_web > NE'nin en büyük MIN_ZOOM'u). */
    var PAKET_ETIKET_UCU = '/api/map-packs/labels';
    var PAKET_Z_TAVANI = 15;          // uç sözleşmesi: z = 0..15 (Web Mercator)
    var PAKET_ISTEK_ARASI_MS = 300;   // iki etiket isteği arası en az süre
    var PAKET_KUTU_PAYI = 0.1;        // görünen kutu her yönde bu oranla genişletilir
    // Web Mercator enlem sınırı, tanımından (EPSG:3857: atan(sinh π)).
    var PAKET_MERC_ENLEM = Math.atan(Math.sinh(Math.PI)) * 180 / Math.PI;
    var PAKET_RAMPA_TURLERI = ['launch_complex', 'launchpad', 'spaceport'];

    // Ad karşılaştırma biçimi: NFD + birleşik işaretler atılır, Türkçe
    // noktasız ı -> i, küçük harf. Yalnız tekrar sınavı içindir.
    function adKatla(a) {
        var s = String(a || '');
        if (s.normalize) s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        return s.replace(/\u0131/g, 'i').toLowerCase();
    }

    // Manifestteki varlık dosya adı izin listesi (karar §28-33; F1 denetimi
    // Ş4). '/', '..' ve mutlak yol bu desenden geçemez, istek baseUrl
    // dizininin dışına çıkamaz. Aynı desen launch_site_vectors.js'te de durur
    // (iki modül bağımsız yüklenir); bekçi ikisinin aynı olduğunu sınar.
    var DOSYA_ADI_DESENI = /^[a-z0-9_]+\.(bin|json)$/;
    // Manifestteki sha256 biçimi: 64 küçük onaltılık hane.
    var SHA256_DESENI = /^[0-9a-f]{64}$/;
    var ULKE_ALANLARI = ['lon', 'lat', 'name', 'name_en', 'name_tr', 'min_label', 'max_label'];

    function hexOzet(buf) {
        var b = new Uint8Array(buf), s = '';
        for (var i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16);
        return s;
    }

    // Ad düzeltmesi sayılan alanlar (K1 AD_DUZELTMELERI satırlarının ad
    // alanları; 'adm0' gibi ad olmayan alan değişiklikleri sayılmaz).
    var AD_DUZELTME_ALANLARI = ['name', 'name_en', 'name_tr'];

    // Varlığın künyesindeki name_corrections.applied listesinden, adı
    // değişen kayıt sayısı (karar §28-45). Alan yoksa 0 (düzeltme yok);
    // biçim bozuksa null: sayı UYDURULMAZ, künye satırı basılmaz.
    function adDuzeltmeSayisi(prov) {
        var nc = prov && prov.name_corrections;
        if (nc == null) return 0;
        var a = nc.applied;
        if (!Array.isArray(a)) return null;
        var n = 0;
        for (var i = 0; i < a.length; i++) {
            var ch = a[i] && a[i].changes;
            if (!Array.isArray(ch)) return null;
            for (var j = 0; j < ch.length; j++) {
                if (ch[j] && AD_DUZELTME_ALANLARI.indexOf(ch[j].field) >= 0) { n++; break; }
            }
        }
        return n;
    }

    function sayiYaDaNaN(v) {
        return (typeof v === 'number' && isFinite(v)) ? v : NaN;
    }

    // Dil kodu -> 'tr' | 'en' (yalnız iki dil desteklenir; tanınmayan EN).
    function dilKodu(d) {
        return (String(d || '').toLowerCase().slice(0, 2) === 'tr') ? 'tr' : 'en';
    }

    // Kayıt adı seçimi (tasarım §3.3-7). Yedek NAME'dir; yedeğe düşen sayısı
    // K1 künyesinde (name_tr_fallback_to_name / name_en_fallback_to_name).
    function adSec(ad, adEn, adTr, dil) {
        var birincil = (dil === 'tr') ? adTr : adEn;
        return birincil || ad || '';
    }

    // Nokta ufkun önünde mi? p̂ birim vektör, c kamera, R küre yarıçapı.
    // dot(p̂, c - R p̂) > 0  <=>  dot(p̂, c) > R
    function ufuktaGorunur(px, py, pz, cx, cy, cz, R) {
        return px * cx + py * cy + pz * cz > R;
    }

    // Etiket dikdörtgeni (CSS px). Şehir/başkent: çapa nokta merkezi, metin
    // sağda. Ülke: çapa metnin ortası. Dönüş out[0..3] = x0, y0, x1, y1.
    function dikdortgen(tur, x, y, genislik, out) {
        var yari = SATIR_PX / 2;
        if (tur === TUR_ULKE) {
            // Tam piksele oturt: kesirli çeviri metni bulanıklaştırır.
            out[0] = x - Math.floor(genislik / 2); out[2] = out[0] + genislik;
        } else {
            out[0] = x - (tur === TUR_BASKENT ? HALKA_PX : NOKTA_PX) / 2;
            out[2] = x + METIN_X_PX + genislik;
        }
        out[1] = y - yari; out[3] = y + yari;
        return out;
    }

    // Engel kutusunu ekran kenarına uzat: kutu ile kenar arasındaki şerit
    // 0 < şerit <= KENAR_SERIDI_PX ise o kenara yaslanır. Kutu ekran dışına
    // taşıyorsa (şerit <= 0) ya da şerit genişse değişmez. out yeniden
    // kullanılır (kare başına çöp yok).
    function kenaraYasla(en, W, H, out) {
        var sol = en[0], ust = en[1], sag = W - en[2], alt = H - en[3];
        out[0] = (sol > 0 && sol <= KENAR_SERIDI_PX) ? 0 : en[0];
        out[1] = (ust > 0 && ust <= KENAR_SERIDI_PX) ? 0 : en[1];
        out[2] = (sag > 0 && sag <= KENAR_SERIDI_PX) ? W : en[2];
        out[3] = (alt > 0 && alt <= KENAR_SERIDI_PX) ? H : en[3];
        return out;
    }

    // ===================================================================
    // Çakışma ızgarası: hücre başına yerleşmiş dikdörtgen listesi.
    // Kare başına çöp üretmez (diziler yeniden kullanılır).
    // ===================================================================
    function Izgara() {
        this.sutun = 0; this.satir = 0;
        this.hucreler = [];
        this.kutular = new Float64Array(4 * ETIKET_TAVANI);
        this.n = 0;
    }
    Izgara.prototype.sifirla = function (w, h) {
        var s = Math.max(1, Math.ceil(w / IZGARA_PX)), r = Math.max(1, Math.ceil(h / IZGARA_PX));
        if (s !== this.sutun || r !== this.satir) {
            this.sutun = s; this.satir = r;
            this.hucreler = [];
            for (var i = 0; i < s * r; i++) this.hucreler.push([]);
        } else {
            for (var j = 0; j < this.hucreler.length; j++) this.hucreler[j].length = 0;
        }
        this.n = 0;
    };
    Izgara.prototype._aralik = function (x0, y0, x1, y1, out) {
        out[0] = Math.max(0, Math.floor(x0 / IZGARA_PX));
        out[1] = Math.max(0, Math.floor(y0 / IZGARA_PX));
        out[2] = Math.min(this.sutun - 1, Math.floor(x1 / IZGARA_PX));
        out[3] = Math.min(this.satir - 1, Math.floor(y1 / IZGARA_PX));
        return out;
    };
    // pay: aday dikdörtgen her yönde bu kadar büyütülerek sınanır.
    Izgara.prototype.bosMu = function (r, pay) {
        var x0 = r[0] - pay, y0 = r[1] - pay, x1 = r[2] + pay, y1 = r[3] + pay;
        var a = this._aralik(x0, y0, x1, y1, this._a || (this._a = [0, 0, 0, 0]));
        var k = this.kutular;
        for (var gy = a[1]; gy <= a[3]; gy++) {
            for (var gx = a[0]; gx <= a[2]; gx++) {
                var liste = this.hucreler[gy * this.sutun + gx];
                for (var i = 0; i < liste.length; i++) {
                    var b = 4 * liste[i];
                    // Kesişim alanı > 0 ise çakışır (kenar teması çakışma değil).
                    if (x0 < k[b + 2] && k[b] < x1 && y0 < k[b + 3] && k[b + 1] < y1) return false;
                }
            }
        }
        return true;
    };
    Izgara.prototype.ekle = function (r) {
        // Yerleşen etiketler + kenar ayırmaları tavanı aşabilir: büyüt.
        if (4 * (this.n + 1) > this.kutular.length) {
            var yeni = new Float64Array(this.kutular.length * 2);
            yeni.set(this.kutular);
            this.kutular = yeni;
        }
        var id = this.n++, b = 4 * id, k = this.kutular;
        k[b] = r[0]; k[b + 1] = r[1]; k[b + 2] = r[2]; k[b + 3] = r[3];
        var a = this._aralik(r[0], r[1], r[2], r[3], this._a || (this._a = [0, 0, 0, 0]));
        for (var gy = a[1]; gy <= a[3]; gy++)
            for (var gx = a[0]; gx <= a[2]; gx++)
                this.hucreler[gy * this.sutun + gx].push(id);
        return id;
    };

    // ===================================================================
    // LaunchSiteLabels
    // ===================================================================
    // opts: container (bindirme <div>), latLonToXYZ (kürenin TEK dönüşümü),
    //       baseUrl?, fetchImpl?, digestImpl?, getLang?, document?,
    //       measureText?(metin, yaziTanimi) -> px, textDecoder?, now?,
    //       getObstacles?() -> [[x0, y0, x1, y1], ...] (bindirme koordinatı)
    function LaunchSiteLabels(opts) {
        this.opts = opts;
        this.container = opts.container || null;
        this._doc = opts.document || global.document || null;
        this._fetch = opts.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
        this._digest = opts.digestImpl || null;
        if (!this._digest && global.crypto && global.crypto.subtle && global.crypto.subtle.digest) {
            var sub = global.crypto.subtle;
            this._digest = function (buf) { return sub.digest('SHA-256', buf).then(hexOzet); };
        }
        this._simdi = opts.now || function () {
            return (global.performance && global.performance.now) ? global.performance.now() : Date.now();
        };
        this.durum = 'bekliyor';      // bekliyor | yukleniyor | hazir | hata
        this.hata = null;
        this.kunye = null;
        this._shaDogrulandi = null;
        this._dil = null;
        this._imza = new Float64Array(IMZA_UZUNLUGU).fill(NaN);
        this._imzaVar = false;
        this._izgara = new Izgara();
        this._r = [0, 0, 0, 0];
        this._sureler = new Float64Array(OLCUM_PENCERESI);
        this._sureN = 0;
        this._sayac = { gorunur: 0, aday: 0, ekranDisi: 0, cakisma: 0, tavan: 0,
                        guncelleme: 0, atlanan: 0, sonMs: 0 };
        this._yerlesim = [];          // son karenin yerleşimi (ölçüm/test)
        this._yazi = null;            // {sehir, ulke} CSS font tanımı
        this._engeller = [];
        this._engelZamani = -Infinity;
        // V307/FS-HARİTA: yakın ölçek katmanı (tembel yüklenir).
        this.detay = { durum: 'bekliyor', hata: null, yerSayisi: 0, kunye: null, gorunur: 0,
                       tekrarGizli: 0 };
        // V307/FS-HARİTA-KÜRE: indirilen paket yer adları (istekle güncellenir).
        this.paket = { durum: 'yok', hata: null, sayi: 0, gorunur: 0, z: null, kesildi: false,
                       istek: 0, dil: null };
        this._paketSon = null;        // {imza, dil, z, kutu} son UYGULANAN istek
        this._paketYolda = false;     // istek yolda
        this._paketZaman = -Infinity;
        this._paketZKisit = PAKET_Z_TAVANI;
        this._pKimlik = [];           // paket bölgesindeki kayıtların kimliği
        this._Tp = null;              // paket bölgesinin ilk dizini
    }

    // Panel kutuları (engel). Okuma DOM yerleşimi ister; kare başına değil,
    // ENGEL_YENILEME_MS aralıkla yapılır. Kutular değiştiyse sürüm sayacı
    // artar: kamera durağanken de yerleşim yenilenir (panel açılıp kapanınca).
    LaunchSiteLabels.prototype._engelleriTazele = function () {
        if (!this.opts.getObstacles) return;
        var t = this._simdi();
        if (t - this._engelZamani < ENGEL_YENILEME_MS) return;
        this._engelZamani = t;
        var e = this.opts.getObstacles() || [], o = this._engeller, ayni = (e.length === o.length);
        for (var i = 0; ayni && i < e.length; i++)
            for (var j = 0; j < 4; j++) if (e[i][j] !== o[i][j]) { ayni = false; break; }
        if (!ayni) { this._engeller = e; this._surum = (this._surum || 0) + 1; }
    };

    LaunchSiteLabels.prototype._url = function (ad) {
        return (this.opts.baseUrl || '/static/map/') + ad;
    };

    LaunchSiteLabels.prototype._getir = function (ad, tur) {
        if (!this._fetch) return Promise.reject(new Error('fetch_yok'));
        return this._fetch(this._url(ad)).then(function (r) {
            if (!r || !r.ok) throw new Error('http_' + ad);
            return tur === 'json' ? r.json() : r.arrayBuffer();
        });
    };

    // Bir JSON varlığını manifestteki kanıtla (bayt + sha256) okur.
    LaunchSiteLabels.prototype._kanitliOku = function (meta, ad) {
        var self = this;
        if (!meta || !meta.file || !(meta.bytes > 0)) return Promise.reject(new Error('manifest_' + ad));
        // İstekten ÖNCE (fail-closed): dosya adı izin listesinde, sha256 var.
        if (typeof meta.file !== 'string' || !DOSYA_ADI_DESENI.test(meta.file))
            return Promise.reject(new Error('dosya_adi_' + ad));
        if (typeof meta.sha256 !== 'string' || !SHA256_DESENI.test(meta.sha256))
            return Promise.reject(new Error('sha256_yok_' + ad));
        return this._getir(meta.file, 'bin').then(function (buf) {
            if (buf.byteLength !== meta.bytes) throw new Error('boyut_' + ad);
            if (!self._digest) { self._shaDogrulandi[ad] = false; return buf; }
            return self._digest(buf).then(function (ozet) {
                if (!meta.sha256 || ozet !== meta.sha256) throw new Error('sha256_' + ad);
                self._shaDogrulandi[ad] = true;
                return buf;
            });
        }).then(function (buf) {
            var TD = self.opts.textDecoder || global.TextDecoder;
            if (!TD) throw new Error('textdecoder_yok');
            return JSON.parse(new TD('utf-8').decode(new Uint8Array(buf)));
        });
    };

    LaunchSiteLabels.prototype.start = function () {
        var self = this;
        this.durum = 'yukleniyor';
        this._shaDogrulandi = {};
        return this._getir('vectors_manifest.json', 'json').then(function (m) {
            if (!m || !m.places || !m.country_labels) throw new Error('manifest_etiket');
            return Promise.all([self._kanitliOku(m.places, 'places'),
                                self._kanitliOku(m.country_labels, 'country_labels')]);
        }).then(function (ikili) {
            if (self._disposed) return;
            self._dizinKur(ikili[0], ikili[1]);
            self._havuzKur();
            self.durum = 'hazir';
        }).catch(function (e) {
            if (self._disposed) return;
            self.durum = 'hata';
            self.hata = String(e && e.message || e);
        });
    };

    function alanDizini(veri, gerekli, ad) {
        if (!veri || !veri.fields || !veri.rows) throw new Error('bicim_' + ad);
        var d = {};
        for (var i = 0; i < gerekli.length; i++) {
            var j = veri.fields.indexOf(gerekli[i]);
            if (j < 0) throw new Error('alan_' + ad + '_' + gerekli[i]);
            d[gerekli[i]] = j;
        }
        return d;
    }

    // Yükleme anında bir kez: birim vektörler, eşikler, adlar, kovalar.
    LaunchSiteLabels.prototype._dizinKur = function (yerler, ulkeler) {
        var dY = alanDizini(yerler, YER_ALANLARI, 'places');
        var dU = alanDizini(ulkeler, ULKE_ALANLARI, 'country_labels');
        var N = yerler.rows.length, M = ulkeler.rows.length, T = N + M;
        var xyz = new Float64Array(3 * T), tur = new Uint8Array(T);
        var zAlt = new Float32Array(T), zUst = new Float32Array(T);
        var ad = new Array(T), adEn = new Array(T), adTr = new Array(T);
        var lat = new Float32Array(T), lon = new Float32Array(T);
        var donustur = this.opts.latLonToXYZ, esiksiz = 0, i, r, k;

        // Anahtar düzeni: [0, N) yerler (dosya sırası), [N, N+M) ülkeler.
        for (i = 0; i < N; i++) {
            r = yerler.rows[i];
            lat[i] = r[dY.lat]; lon[i] = r[dY.lon];
            donustur(r[dY.lat], r[dY.lon], 1, xyz, 3 * i);
            tur[i] = (r[dY.featurecla] === BASKENT_SINIFI) ? TUR_BASKENT : TUR_SEHIR;
            zAlt[i] = sayiYaDaNaN(r[dY.min_zoom]);
            zUst[i] = Infinity;
            if (zAlt[i] !== zAlt[i]) esiksiz++;
            ad[i] = r[dY.name]; adEn[i] = r[dY.name_en]; adTr[i] = r[dY.name_tr];
        }
        for (i = 0; i < M; i++) {
            r = ulkeler.rows[i]; k = N + i;
            lat[k] = r[dU.lat]; lon[k] = r[dU.lon];
            donustur(r[dU.lat], r[dU.lon], 1, xyz, 3 * k);
            tur[k] = TUR_ULKE;
            zAlt[k] = sayiYaDaNaN(r[dU.min_label]);
            zUst[k] = sayiYaDaNaN(r[dU.max_label]);
            if (zAlt[k] !== zAlt[k] || zUst[k] !== zUst[k]) esiksiz++;
            ad[k] = r[dU.name]; adEn[k] = r[dU.name_en]; adTr[k] = r[dU.name_tr];
        }

        // Kovalar (yalnız yerler): kova içinde MIN_ZOOM artan, eşitlikte
        // dosya sırası -> süzgeç ilk büyük eşikte durur.
        var KS = 360 / KOVA_DERECE, KR = 180 / KOVA_DERECE, kovalar = [];
        for (i = 0; i < KS * KR; i++) kovalar.push([]);
        for (i = 0; i < N; i++) {
            if (zAlt[i] !== zAlt[i]) continue;          // eşiksiz: basılmaz
            var ks = Math.min(KS - 1, Math.max(0, Math.floor((lon[i] + 180) / KOVA_DERECE)));
            var kr = Math.min(KR - 1, Math.max(0, Math.floor((lat[i] + 90) / KOVA_DERECE)));
            kovalar[kr * KS + ks].push(i);
        }
        var kovaDizi = [], kovaMerkez = new Float64Array(3 * KS * KR), kovaYaricap = new Float64Array(KS * KR);
        var kose = [0, 0, 0];
        for (var b = 0; b < KS * KR; b++) {
            var liste = kovalar[b];
            liste.sort(function (a, c) { return (zAlt[a] - zAlt[c]) || (a - c); });
            kovaDizi.push(Int32Array.from(liste));
            var bs = b % KS, br = Math.floor(b / KS);
            var lo0 = bs * KOVA_DERECE - 180, la0 = br * KOVA_DERECE - 90;
            donustur(la0 + KOVA_DERECE / 2, lo0 + KOVA_DERECE / 2, 1, kovaMerkez, 3 * b);
            // Kova yarıçapı: merkezden kenar örneklerine en büyük açı (+ pay).
            var enBuyuk = 0;
            for (var s = 0; s <= 4; s++) {
                for (var e = 0; e <= 4; e++) {
                    if (s > 0 && s < 4 && e > 0 && e < 4) continue;
                    donustur(la0 + KOVA_DERECE * s / 4, lo0 + KOVA_DERECE * e / 4, 1, kose, 0);
                    var dt = kose[0] * kovaMerkez[3 * b] + kose[1] * kovaMerkez[3 * b + 1] + kose[2] * kovaMerkez[3 * b + 2];
                    enBuyuk = Math.max(enBuyuk, Math.acos(Math.max(-1, Math.min(1, dt))));
                }
            }
            kovaYaricap[b] = enBuyuk + 0.01;
        }

        this.N = N; this.M = M; this.T = T;
        this.xyz = xyz; this.tur = tur; this.zAlt = zAlt; this.zUst = zUst;
        this.ad = ad; this.adEn = adEn; this.adTr = adTr; this.lat = lat; this.lon = lon;
        this.kovalar = kovaDizi; this.kovaMerkez = kovaMerkez; this.kovaYaricap = kovaYaricap;
        this._onceki = new Uint8Array(T);
        this._simdiki = new Uint8Array(T);
        this._aday = new Float64Array(T);     // sıralama anahtarları (tam sayı değerli)
        this._genislik = new Float32Array(T).fill(NaN);
        this._yuvaOf = new Int16Array(T).fill(-1);
        this._esiksiz = esiksiz;
        this._T0 = T;                          // NE yer + ülke sayısı (ayrıntı katmanı bunun ardından)
        // NE yer kayıtlarının EN BÜYÜK MIN_ZOOM değeri: ayrıntı katmanının
        // devreye girdiği ölçek (veriden; places.json'da 9).
        var neTavan = -Infinity;
        for (i = 0; i < N; i++) if (zAlt[i] === zAlt[i] && zAlt[i] > neTavan) neTavan = zAlt[i];
        this._neZTavan = neTavan;

        var p = yerler.provenance || {}, pu = ulkeler.provenance || {};
        var surum = /v\d+(?:\.\d+)*/.exec(String(p.source || ''));
        // Ad yedeği istemcide SAYILIR (künyedeki sayıya güvenilmez, ölçülür).
        var yedekTr = 0, yedekEn = 0;
        for (i = 0; i < T; i++) { if (!adTr[i]) yedekTr++; if (!adEn[i]) yedekEn++; }
        this.kunye = {
            kaynak: p.source || null,
            surum: surum ? surum[0] : null,
            lisans: p.license || null,
            atif: p.attribution || null,
            sinirGorunumu: pu.boundary_view || p.boundary_view || null,
            yerSayisi: N,
            ulkeSayisi: M,
            esiksizKayit: esiksiz,
            adYedegi: { tr: yedekTr, en: yedekEn },
            // HRK devri (4. tur): künye ad düzeltmelerini de yayımlar.
            adDuzeltmesi: { yer: adDuzeltmeSayisi(p), ulke: adDuzeltmeSayisi(pu) },
            shaDogrulandi: this._shaDogrulandi
        };
    };

    // CSS yazı tanımı: bindirmenin hesaplanmış yazı ailesinden (tema).
    LaunchSiteLabels.prototype._yaziKur = function () {
        var aile = 'sans-serif';
        try {
            if (this.container && global.getComputedStyle)
                aile = global.getComputedStyle(this.container).fontFamily || aile;
        } catch (e) { /* hesaplanmış stil yoksa genel aile */ }
        this._yazi = {
            sehir: SEHIR_YAZI.agirlik + ' ' + SEHIR_YAZI.boyut + 'px/' + SATIR_PX + 'px ' + aile,
            ulke: ULKE_YAZI.agirlik + ' ' + ULKE_YAZI.boyut + 'px/' + SATIR_PX + 'px ' + aile
        };
    };

    // Metin genişliği (CSS px). Tarayıcıda tuval measureText; etiket öğesi
    // AYNI yazı tanımıyla basılır. Ölçüm önbelleklenir (dil değişince silinir).
    LaunchSiteLabels.prototype._olc = function (metin, yazi) {
        if (this.opts.measureText) return this.opts.measureText(metin, yazi);
        if (!this._ctx && this._doc && this._doc.createElement) {
            var c = this._doc.createElement('canvas');
            this._ctx = c && c.getContext ? c.getContext('2d') : null;
        }
        if (!this._ctx) return NaN;
        if (this._ctx.font !== yazi) this._ctx.font = yazi;
        return this._ctx.measureText(metin).width;
    };

    LaunchSiteLabels.prototype._genislikAl = function (k) {
        var g = this._genislik[k];
        if (g === g) return g;
        var yazi = (this.tur[k] === TUR_ULKE) ? this._yazi.ulke : this._yazi.sehir;
        g = Math.ceil(this._olc(this._metin(k), yazi));
        this._genislik[k] = g;
        return g;
    };

    LaunchSiteLabels.prototype._metin = function (k) {
        return adSec(this.ad[k], this.adEn[k], this.adTr[k], this._dil);
    };

    // DOM havuzu: bir kez kurulur. Konum/ölçü stilleri geometri
    // sabitlerinden yazılır (dikdörtgen hesabıyla tek kaynak).
    LaunchSiteLabels.prototype._havuzKur = function () {
        this._yaziKur();
        this._yuvalar = [];
        this._bos = [];
        if (!this.container || !this._doc) return;
        // Tema yazı tipi geç yüklenirse genişlikler yeniden ölçülür.
        var self = this, fonts = this._doc.fonts;
        if (fonts && fonts.addEventListener)
            fonts.addEventListener('loadingdone', function () { if (!self._disposed) self.invalidate(); });
        for (var i = 0; i < HAVUZ_BOYUTU; i++) {
            var el = this._doc.createElement('div');
            el.className = 'ls-lbl';
            var st = el.style;
            st.position = 'absolute'; st.left = '0px'; st.top = '0px';
            st.height = SATIR_PX + 'px'; st.whiteSpace = 'nowrap';
            st.visibility = 'hidden';
            var nokta = this._doc.createElement('i');
            nokta.className = 'ls-lbl-dot';
            nokta.style.position = 'absolute';
            var metin = this._doc.createElement('span');
            metin.className = 'ls-lbl-txt';
            metin.style.position = 'absolute'; metin.style.top = '0px';
            el.appendChild(nokta); el.appendChild(metin);
            this.container.appendChild(el);
            this._yuvalar.push({ el: el, nokta: nokta, metin: metin, k: -1, x: NaN, y: NaN, tur: -1 });
            this._bos.push(HAVUZ_BOYUTU - 1 - i);
        }
    };

    // Yuvanın türe göre geometrisi (yalnız tür değişince yazılır).
    LaunchSiteLabels.prototype._yuvaTuru = function (y, tur) {
        if (y.tur === tur) return;
        y.tur = tur;
        var n = y.nokta.style, m = y.metin.style;
        if (tur === TUR_ULKE) {
            y.el.className = 'ls-lbl ls-lbl-country';
            y.el.style.font = this._yazi.ulke;
            n.display = 'none';
            m.left = '0px';
        } else {
            var cap = (tur === TUR_BASKENT) ? HALKA_PX : NOKTA_PX;
            y.el.className = (tur === TUR_BASKENT) ? 'ls-lbl ls-lbl-capital'
                : (tur === TUR_RAMPA ? 'ls-lbl ls-lbl-city ls-lbl-pad' : 'ls-lbl ls-lbl-city');
            y.el.style.font = this._yazi.sehir;
            n.display = 'block';
            n.width = cap + 'px'; n.height = cap + 'px';
            n.left = '0px'; n.top = ((SATIR_PX - cap) / 2) + 'px';
            m.left = (cap / 2 + METIN_X_PX) + 'px';
        }
    };

    // Kamera/ölçek/dil imzası: değişmediyse güncelleme atlanır.
    LaunchSiteLabels.prototype._imzaDegisti = function (f) {
        var s = this._imza, e = f.camera.matrixWorld.elements, p = f.camera.projectionMatrix.elements;
        var degisti = !this._imzaVar, i = 0;
        function koy(v) { if (s[i] !== v) { degisti = true; s[i] = v; } i++; }
        for (var j = 0; j < 16; j++) koy(e[j]);
        koy(p[0]); koy(p[5]); koy(p[8]); koy(p[9]);
        koy(f.size.width); koy(f.size.height); koy(f.globeRadius); koy(f.zWeb);
        koy(this._surum || 0);
        if (i !== IMZA_UZUNLUGU) throw new Error('imza_uzunlugu');
        this._imzaVar = true;
        return degisti;
    };

    // Dil değişimi ve yazı tipi yüklemesi sonrası her şey yeniden ölçülür.
    LaunchSiteLabels.prototype.invalidate = function () {
        if (this._genislik) this._genislik.fill(NaN);
        this._yaziKur();
        if (this._yuvalar) for (var i = 0; i < this._yuvalar.length; i++) {
            this._yuvalar[i].tur = -1;
            if (this._yuvalar[i].k >= 0) this._yuvalar[i].yaz = true;
        }
        this._surum = (this._surum || 0) + 1;
    };

    // Kare kancası (LaunchSiteGlobe.addFrameListener).
    LaunchSiteLabels.prototype.update = function (f) {
        if (this.durum !== 'hazir' || this._disposed || !f || !f.camera) return;
        var dil = dilKodu(this.opts.getLang ? this.opts.getLang() : 'en');
        if (dil !== this._dil) { this._dil = dil; this.invalidate(); }
        f.camera.updateMatrixWorld();
        this._engelleriTazele();
        if (!this._imzaDegisti(f)) { this._sayac.atlanan++; return; }
        var t0 = this._simdi();
        this._yerlestir(f);
        this._domUygula();
        var sure = this._simdi() - t0;
        this._sureler[this._sureN % OLCUM_PENCERESI] = sure;
        this._sureN++;
        this._sayac.sonMs = sure;
        this._sayac.guncelleme++;
    };

    LaunchSiteLabels.prototype._yerlestir = function (f) {
        var cam = f.camera, W = f.size.width, H = f.size.height, R = f.globeRadius;
        var cx = cam.position.x, cy = cam.position.y, cz = cam.position.z;
        var d = Math.sqrt(cx * cx + cy * cy + cz * cz);
        var sayac = this._sayac, yer = this._yerlesim;
        sayac.aday = 0; sayac.ekranDisi = 0; sayac.cakisma = 0; sayac.tavan = 0; sayac.gorunur = 0;
        yer.length = 0;
        var onceki = this._onceki, simdiki = this._simdiki;
        simdiki.fill(0);
        if (!(d > R) || !(W > 0) || !(H > 0)) { this._takas(); return; }

        // İzdüşüm matrisi: P · V (kameranın kendi matrisleri).
        var pm = cam.projectionMatrix.elements, vm = cam.matrixWorldInverse.elements;
        var e = this._pv || (this._pv = new Float64Array(16));
        for (var sI = 0; sI < 4; sI++) {
            for (var rI = 0; rI < 4; rI++) {
                e[sI * 4 + rI] = pm[rI] * vm[sI * 4] + pm[4 + rI] * vm[sI * 4 + 1]
                               + pm[8 + rI] * vm[sI * 4 + 2] + pm[12 + rI] * vm[sI * 4 + 3];
            }
        }

        var z = f.zWeb, xyz = this.xyz, zAlt = this.zAlt, zUst = this.zUst, N = this.N, M = this.M;
        var aday = this._aday, n = 0, i, k, b, j;

        // Ülkeler: MIN_LABEL <= z <= MAX_LABEL (gösterilen için histerezisli).
        for (j = 0; j < M; j++) {
            k = N + j;
            var lo = zAlt[k], hi = zUst[k];
            if (lo !== lo || hi !== hi) continue;
            var h = onceki[k] ? Z_HISTEREZIS : 0;
            if (z < lo - h || z > hi + h) continue;
            if (!ufuktaGorunur(xyz[3 * k], xyz[3 * k + 1], xyz[3 * k + 2], cx, cy, cz, R)) continue;
            aday[n++] = this._anahtar(j, onceki[k]);   // öncelik = ülke dosya sırası
        }

        // Yerler: ufuk başlığına değen kovalar; kova içinde MIN_ZOOM artan.
        var ux = cx / d, uy = cy / d, uz = cz / d, ufukAci = Math.acos(R / d);
        var kovalar = this.kovalar, km = this.kovaMerkez, ky = this.kovaYaricap;
        for (b = 0; b < kovalar.length; b++) {
            var liste = kovalar[b];
            if (!liste.length) continue;
            var sinir = ufukAci + ky[b];
            if (sinir < Math.PI && km[3 * b] * ux + km[3 * b + 1] * uy + km[3 * b + 2] * uz < Math.cos(sinir)) continue;
            for (i = 0; i < liste.length; i++) {
                k = liste[i];
                var mz = zAlt[k];
                if (mz > z + Z_HISTEREZIS) break;
                if (mz > z && !onceki[k]) continue;
                if (!ufuktaGorunur(xyz[3 * k], xyz[3 * k + 1], xyz[3 * k + 2], cx, cy, cz, R)) continue;
                aday[n++] = this._anahtar(M + k, onceki[k]); // ülkelerden sonra dosya sırası
            }
        }
        // V307/FS-HARİTA: yakın ölçek (GeoNames) adayları.
        var dt = this.detay;
        if (dt.durum === 'bekliyor' && z > this._neZTavan) this._detayYukle();
        if (dt.durum === 'hazir') n = this._detayAdaylari(z, cx, cy, cz, d, R, n, e, W, H);
        // V307/FS-HARİTA-KÜRE: indirilen paketten yer adları. İstek yalnız
        // GeoNames katmanı sonuçlandıktan sonra (dizin bölgesi onun ardında).
        if (dt.durum === 'hazir' || dt.durum === 'hata') {
            this._paketIstegi(f, z);
            n = this._paketAdaylari(f, cx, cy, cz, R, n, e);
        }
        sayac.aday = n;
        var sirali = aday.subarray(0, n);
        sirali.sort();                            // tipli dizi: sayısal artan

        // Tavan histerezisi: gösterilen adaylar tavanda yerlerini korur. Yeni
        // aday ancak kalan gösterilen adaylara yer bırakıyorsa alınır; yoksa
        // tavan sınırındaki etiketler her giriş/çıkışta sökülüp geri gelir.
        var gosterilenKalan = 0;
        for (i = 0; i < n; i++) {
            var pp = sirali[i] % this.T;
            if (onceki[this._oncelikK(pp)]) gosterilenKalan++;
        }
        var tavan = etiketTavani(f.metersPerPixel, d, f.globalViewDist);
        sayac.tavanDegeri = tavan;
        var izgara = this._izgara, r = this._r;
        izgara.sifirla(W, H);
        var engeller = this._engeller, ek = this._engelKutu || (this._engelKutu = [0, 0, 0, 0]);
        for (i = 0; i < engeller.length; i++) {
            var en = engeller[i];
            if (en && en[2] > en[0] && en[3] > en[1]) izgara.ekle(kenaraYasla(en, W, H, ek));
        }
        sayac.engel = engeller.length;
        var T0 = this._T0, katli = this._katli, yerlesikAd = this._yerlesikAd || (this._yerlesikAd = {});
        var tekrar = 0, detayGorunur = 0, paketGorunur = 0, Tp = this._Tp;
        for (var ka in yerlesikAd) delete yerlesikAd[ka];
        for (i = 0; i < n; i++) {
            var p = sirali[i] % this.T;           // anahtardan öncelik sırası
            k = this._oncelikK(p);
            // V307/FS-HARİTA: aynı ad ekranda zaten varsa (NE ile GeoNames
            // aynı şehir) ikinci kez basılmaz. Yalnız şehir/başkent sınanır.
            if (katli && this.tur[k] !== TUR_ULKE) {
                var kAd = katli[k];
                if (kAd && yerlesikAd[kAd]) { tekrar++; continue; }
            }
            if (onceki[k]) gosterilenKalan--;
            if (yer.length + (onceki[k] ? 0 : gosterilenKalan) >= tavan) { sayac.tavan++; continue; }
            var px = xyz[3 * k] * R, py = xyz[3 * k + 1] * R, pz = xyz[3 * k + 2] * R;
            var cw = e[3] * px + e[7] * py + e[11] * pz + e[15];
            if (!(cw > 0)) { sayac.ekranDisi++; continue; }
            var nx = (e[0] * px + e[4] * py + e[8] * pz + e[12]) / cw;
            var ny = (e[1] * px + e[5] * py + e[9] * pz + e[13]) / cw;
            var nz = (e[2] * px + e[6] * py + e[10] * pz + e[14]) / cw;
            if (nz < -1 || nz > 1 || nx < -1 || nx > 1 || ny < -1 || ny > 1) { sayac.ekranDisi++; continue; }
            var sx = Math.round((nx + 1) * 0.5 * W), sy = Math.round((1 - ny) * 0.5 * H);
            var tur = this.tur[k];
            var g = this._genislikAl(k);
            if (!(g >= 0)) { sayac.ekranDisi++; continue; }
            dikdortgen(tur, sx, sy, g, r);
            // Ekran ölçütü ÇAPADIR (yukarıdaki NDC sınavı): dikdörtgen kenarda
            // taşabilir ve bindirme onu keser. Tam sığma şartı, kısa önemsiz
            // adların kenardan önce girip önemli ad sığınca sökülmesine
            // (giriş/çıkış titremesi) yol açıyordu (K3 ölçümü, rapor).
            if (!izgara.bosMu(r, onceki[k] ? 0 : YENI_ETIKET_PAYI_PX)) { sayac.cakisma++; continue; }
            izgara.ekle(r);
            simdiki[k] = 1;
            yer.push({ k: k, x: sx, y: sy, tur: tur, x0: r[0], y0: r[1], x1: r[2], y1: r[3] });
            if (katli && tur !== TUR_ULKE && katli[k]) yerlesikAd[katli[k]] = 1;
            // V307/FS-HARİTA-KÜRE: paket bölgesi [Tp, T) GeoNames'ten ayrı sayılır.
            if (Tp !== null && k >= Tp) paketGorunur++;
            else if (k >= T0) detayGorunur++;
        }
        sayac.gorunur = yer.length;
        this.detay.gorunur = detayGorunur;
        this.detay.tekrarGizli = tekrar;
        this.paket.gorunur = paketGorunur;
        this._takas();
    };

    // Öncelik -> kayıt dizini. [0, M) ülkeler -> N + p; [M, T0) NE yerleri
    // -> p - M; [T0, T) yakın ölçek (GeoNames) -> p (dizin = öncelik).
    LaunchSiteLabels.prototype._oncelikK = function (p) {
        var M = this.M, N = this.N;
        return (p < M) ? N + p : (p < this._T0 ? p - M : p);
    };

    // V307/FS-HARİTA — yakın ölçek katmanını kanıtla oku (tek sefer).
    LaunchSiteLabels.prototype._detayYukle = function () {
        var self = this, dt = this.detay;
        if (dt.durum !== 'bekliyor') return;
        dt.durum = 'yukleniyor';
        this._getir(DETAY_MANIFEST, 'json').then(function (m) {
            if (!m || !m.places_detail) throw new Error('manifest_detay');
            return self._kanitliOku(m.places_detail, 'places_detail');
        }).then(function (veri) {
            if (self._disposed) return;
            self._detayKur(veri);
            dt.durum = 'hazir';
            self.invalidate();
        }).catch(function (e) {
            if (self._disposed) return;
            dt.durum = 'hata';
            dt.hata = String(e && e.message || e);
        });
    };

    // Dizinleri NE + ülke kayıtlarının ARDINA genişletir; mevcut kayıtların
    // dizini, sırası ve gösterim durumu değişmez.
    LaunchSiteLabels.prototype._detayKur = function (veri) {
        var dD = alanDizini(veri, DETAY_ALANLARI, 'places_detail');
        var G = veri.rows.length, T0 = this._T0, T = T0 + G, i, k, r;
        function buyut(eski, Tur, n, dolgu) {
            var y = new Tur(n);
            y.set(eski);
            if (dolgu !== undefined) y.fill(dolgu, eski.length);
            return y;
        }
        this.xyz = buyut(this.xyz, Float64Array, 3 * T);
        this.tur = buyut(this.tur, Uint8Array, T);
        this.zAlt = buyut(this.zAlt, Float32Array, T, this._neZTavan);
        this.zUst = buyut(this.zUst, Float32Array, T, Infinity);
        this.lat = buyut(this.lat, Float32Array, T);
        this.lon = buyut(this.lon, Float32Array, T);
        this._onceki = buyut(this._onceki, Uint8Array, T);
        this._simdiki = buyut(this._simdiki, Uint8Array, T);
        this._aday = new Float64Array(T);
        this._genislik = buyut(this._genislik, Float32Array, T, NaN);
        this._yuvaOf = buyut(this._yuvaOf, Int16Array, T, -1);
        var katli = new Array(T), donustur = this.opts.latLonToXYZ, kovalar = new Map();
        for (k = 0; k < this.N; k++) {
            // NE yerinin karşılaştırma adı: o anki dilde basılacak ad değil,
            // üç adın her biri (aşağıda GeoNames adı bunlardan birine eşitse
            // tekrar sayılır). Tek anahtar tutulur: İngilizce ad (yoksa NAME).
            katli[k] = adKatla(this.adEn[k] || this.ad[k]);
        }
        var neAdlar = {};
        for (k = 0; k < this.N; k++) {
            neAdlar[adKatla(this.ad[k])] = katli[k];
            neAdlar[adKatla(this.adTr[k])] = katli[k];
        }
        this._neAdlar = neAdlar;      // V307/FS-HARİTA-KÜRE: paket adları da aynı eşlemeyle katlanır
        for (i = 0; i < G; i++) {
            r = veri.rows[i]; k = T0 + i;
            var la = r[dD.lat], lo = r[dD.lon];
            this.lat[k] = la; this.lon[k] = lo;
            donustur(la, lo, 1, this.xyz, 3 * k);
            this.tur[k] = (r[dD.fcode] === DETAY_BASKENT_KODU) ? TUR_BASKENT : TUR_SEHIR;
            this.ad.push(r[dD.name]); this.adEn.push(''); this.adTr.push('');
            var ka = adKatla(r[dD.name]);
            katli[k] = neAdlar[ka] || ka;
            var kk = Math.min(179, Math.max(0, Math.floor(la + 90))) * 360
                   + Math.min(359, Math.max(0, Math.floor(lo + 180)));
            var liste = kovalar.get(kk);
            if (!liste) { liste = []; kovalar.set(kk, liste); }
            liste.push(k);                     // dosya sırası = nüfus azalan
        }
        this._katli = katli;
        this._detayKovalar = kovalar;
        this.T = T;
        var p = veri.provenance || {};
        this.detay.yerSayisi = G;
        this.detay.kunye = { kaynak: p.source || null, lisans: p.license || null,
                             atif: p.attribution || null, indirme: p.downloaded_utc || null,
                             arsivSha256: p.archive_sha256 || null,
                             esikZWeb: this._neZTavan,
                             shaDogrulandi: this._shaDogrulandi ? this._shaDogrulandi.places_detail : null };
    };

    // Yakın ölçek adayları: kameranın altındaki noktanın çevresinde, ufuk
    // başlığına değen 1°'lik kovalar; yalnız ekranda (NDC) olanlar aday olur.
    // z_web NE tavanını aşmadıkça yeni aday yok; gösterilen etiket
    // Z_HISTEREZIS kadar geç kaybolur (NE yerleriyle aynı kural).
    LaunchSiteLabels.prototype._detayAdaylari = function (z, cx, cy, cz, d, R, n, e, W, H) {
        var esik = this._neZTavan, onceki = this._onceki, aday = this._aday, xyz = this.xyz;
        var yeniAday = z > esik;
        if (!yeniAday && !(z > esik - Z_HISTEREZIS)) return n;
        var D2R = Math.PI / 180, ux = cx / d, uy = cy / d, uz = cz / d;
        var lat0 = Math.asin(Math.max(-1, Math.min(1, uy))) / D2R;
        var lon0 = Math.atan2(-uz, ux) / D2R;
        var cap = Math.acos(R / d) / D2R + DETAY_KOVA_DERECE;
        var la0 = Math.max(-90, lat0 - cap), la1 = Math.min(90, lat0 + cap);
        var kutup = la0 <= -90 || la1 >= 90;
        var cosMin = Math.cos(Math.max(Math.abs(la0), Math.abs(la1)) * D2R);
        var yari = kutup ? 180 : Math.min(180, cap / Math.max(cosMin, 1e-6));
        var nS = (yari >= 180) ? 360 : Math.min(360, 2 * Math.ceil(yari) + 2);
        var s0 = (nS === 360) ? 0 : Math.floor(lon0 - yari + 180);
        var r0 = Math.max(0, Math.floor(la0 + 90)), r1 = Math.min(179, Math.floor(la1 + 90));
        var kovalar = this._detayKovalar, sayac = this._sayac;
        for (var rr = r0; rr <= r1; rr++) {
            for (var j = 0; j < nS; j++) {
                var ss = (((s0 + j) % 360) + 360) % 360;
                var liste = kovalar.get(rr * 360 + ss);
                if (!liste) continue;
                for (var i = 0; i < liste.length; i++) {
                    var k = liste[i];
                    if (!yeniAday && !onceki[k]) continue;
                    var x = xyz[3 * k], y = xyz[3 * k + 1], w = xyz[3 * k + 2];
                    if (!ufuktaGorunur(x, y, w, cx, cy, cz, R)) continue;
                    var px = x * R, py = y * R, pz = w * R;
                    var cw = e[3] * px + e[7] * py + e[11] * pz + e[15];
                    if (!(cw > 0)) { sayac.ekranDisi++; continue; }
                    var nx = (e[0] * px + e[4] * py + e[8] * pz + e[12]) / cw;
                    var ny = (e[1] * px + e[5] * py + e[9] * pz + e[13]) / cw;
                    if (nx < -1 || nx > 1 || ny < -1 || ny > 1) { sayac.ekranDisi++; continue; }
                    aday[n++] = this._anahtar(k, onceki[k]);
                }
            }
        }
        return n;
    };

    /* V307/FS-HARİTA-KÜRE — görünen ZEMİN kutusu. Ekranın 3×3 noktasından
       (köşeler, kenar ortaları, merkez) kamera ışını küreyle kesiştirilir;
       kesişen noktaların enlem/boylam kutusu ve merkez ışınının enlemi döner.
       Ufkun ötesine (gökyüzüne) giden ışın sayılmaz. Hiç kesişme yoksa ya da
       kutu 180°'den geniş boylam taşıyorsa (tarih çizgisi) null: istek yok. */
    function gorunenKutu(cam, R) {
        var m = cam.matrixWorld && cam.matrixWorld.elements;
        var pi = cam.projectionMatrixInverse && cam.projectionMatrixInverse.elements;
        if (!m || !pi) return null;
        var cx = cam.position.x, cy = cam.position.y, cz = cam.position.z;
        var w = Infinity, s = Infinity, e = -Infinity, n = -Infinity, say = 0, merkezLat = null;
        var R2D = 180 / Math.PI;
        for (var a = -1; a <= 1; a++) {
            for (var b = -1; b <= 1; b++) {
                // NDC (a, b, 1) -> görünüm uzayı (izdüşümün tersi) -> dünya
                var vw = pi[3] * a + pi[7] * b + pi[11] + pi[15];
                var vx = (pi[0] * a + pi[4] * b + pi[8] + pi[12]) / vw;
                var vy = (pi[1] * a + pi[5] * b + pi[9] + pi[13]) / vw;
                var vz = (pi[2] * a + pi[6] * b + pi[10] + pi[14]) / vw;
                var dx = m[0] * vx + m[4] * vy + m[8] * vz + m[12] - cx;
                var dy = m[1] * vx + m[5] * vy + m[9] * vz + m[13] - cy;
                var dz = m[2] * vx + m[6] * vy + m[10] * vz + m[14] - cz;
                var L = Math.sqrt(dx * dx + dy * dy + dz * dz);
                if (!(L > 0)) continue;
                dx /= L; dy /= L; dz /= L;
                var bb = cx * dx + cy * dy + cz * dz, cc = cx * cx + cy * cy + cz * cz - R * R;
                var disk = bb * bb - cc;
                if (!(disk >= 0)) continue;
                var t = -bb - Math.sqrt(disk);
                if (!(t > 0)) continue;
                var px = cx + dx * t, py = cy + dy * t, pz = cz + dz * t;
                var lat = Math.asin(Math.max(-1, Math.min(1, py / R))) * R2D;
                var lon = Math.atan2(-pz, px) * R2D;
                if (a === 0 && b === 0) merkezLat = lat;
                w = Math.min(w, lon); e = Math.max(e, lon);
                s = Math.min(s, lat); n = Math.max(n, lat);
                say++;
            }
        }
        if (!say || merkezLat === null || e - w > 180) return null;
        return { kutu: [w, s, e, n], merkezLat: merkezLat };
    }

    function kutuKesis(a, b) {
        var w = Math.max(a[0], b[0]), s = Math.max(a[1], b[1]);
        var e = Math.min(a[2], b[2]), n = Math.min(a[3], b[3]);
        return (w < e && s < n) ? [w, s, e, n] : null;
    }

    function kutuIcinde(ic, dis) {
        return !!(ic && dis && ic[0] >= dis[0] && ic[1] >= dis[1] && ic[2] <= dis[2] && ic[3] <= dis[3]);
    }

    /* Paket yer adı isteği (gerekirse). Kurulu paket kümesi değiştiyse bölge
       boşalır. İstek yalnız: kurulu paket görünen kutuyla kesişiyor, z_web
       GeoNames eşiğini aşmış, yolda istek yok, son istekten bu yana
       PAKET_ISTEK_ARASI_MS geçmiş ve (dil, düzey, paket kümesi) değişmiş ya
       da görünen alan son istenen kutudan taşmışsa atılır. */
    LaunchSiteLabels.prototype._paketIstegi = function (f, zWeb) {
        var P = global.LaunchSiteMapPacks;
        var kurulu = (P && typeof P.kuruluKutular === 'function') ? P.kuruluKutular() : [];
        var imza = (P && typeof P.imza === 'function') ? String(P.imza()) : '';
        if (this._paketSon && this._paketSon.imza !== imza) this._paketUygula([], null, false);
        this._paketZM = NaN;
        if (!Array.isArray(kurulu) || !kurulu.length) { this.paket.durum = 'yok'; return; }
        var gk = gorunenKutu(f.camera, f.globeRadius);
        if (!gk) return;
        // Görünümün gerçek Web Mercator düzeyi: kürenin kare yükünden
        // (f.zMercator; ölçeğin TEK sahibi küre modülü). Yoksa istek yok.
        var zM = f.zMercator;
        if (typeof zM !== 'number' || !isFinite(zM)) return;
        this._paketZM = zM;
        if (!(zWeb > this._neZTavan) || this._paketYolda) return;
        var simdi = this._simdi();
        if (simdi - this._paketZaman < PAKET_ISTEK_ARASI_MS) return;
        var zTaban = Math.max(0, Math.min(PAKET_Z_TAVANI, Math.floor(zM)));
        if (this._paketZKisitTaban !== zTaban) { this._paketZKisit = PAKET_Z_TAVANI; this._paketZKisitTaban = zTaban; }
        var zI = Math.min(zTaban, this._paketZKisit);
        var k = gk.kutu, pw = (k[2] - k[0]) * PAKET_KUTU_PAYI, ph = (k[3] - k[1]) * PAKET_KUTU_PAYI;
        var genis = [Math.max(-180, k[0] - pw), Math.max(-PAKET_MERC_ENLEM, k[1] - ph),
                     Math.min(180, k[2] + pw), Math.min(PAKET_MERC_ENLEM, k[3] + ph)];
        var birlesim = null;
        for (var i = 0; i < kurulu.length; i++) {
            var b = kurulu[i] && kurulu[i].bbox;
            if (!b || b.length !== 4) continue;
            var kk = kutuKesis(genis, b);
            if (!kk) continue;
            birlesim = birlesim ? [Math.min(birlesim[0], kk[0]), Math.min(birlesim[1], kk[1]),
                                   Math.max(birlesim[2], kk[2]), Math.max(birlesim[3], kk[3])] : kk;
        }
        if (!birlesim) return;                       // görünen alanda kurulu paket yok
        var son = this._paketSon, gerek = kutuKesis(k, birlesim) || birlesim;
        if (son && son.imza === imza && son.dil === this._dil && son.z === zI
                && kutuIcinde(gerek, son.kutu)) return;
        var istek = { imza: imza, dil: this._dil, z: zI, kutu: birlesim };
        var url = PAKET_ETIKET_UCU + '?bbox=' + birlesim.map(function (v) { return v.toFixed(5); }).join(',')
            + '&z=' + zI + '&lang=' + istek.dil;
        if (!this._fetch) return;
        var self = this;
        this._paketYolda = true;
        this._paketZaman = simdi;
        this.paket.istek++;
        this._fetch(url).then(function (r) {
            return r.json().then(function (g) { return { ok: r.ok, g: g }; },
                                 function () { return { ok: false, g: null }; });
        }).then(function (y) {
            self._paketYolda = false;
            if (self._disposed) return;
            if (!y.ok) {
                var kod = y.g && y.g.error_code;
                // Kutu bu düzeyde sunucunun karo sınırını aşıyor: bir düzey
                // kaba iste (adlar o düzeyin rank'ına göre seyrekleşir).
                if (kod === 'bbox_too_large' && zI > 0) {
                    self._paketZKisit = zI - 1; self._paketZaman = -Infinity; self._surum = (self._surum || 0) + 1;
                    return;
                }
                self.paket.durum = 'hata'; self.paket.hata = String(kod || 'yanit');
                return;
            }
            var P2 = global.LaunchSiteMapPacks;
            if (P2 && typeof P2.imza === 'function' && String(P2.imza()) !== istek.imza) return;
            if (self._dil !== istek.dil) return;          // dil değişti: yeni tur ister
            self._paketUygula(y.g && y.g.labels, istek, !!(y.g && y.g.truncated));
        }, function (e) {
            self._paketYolda = false;
            if (self._disposed) return;
            self.paket.durum = 'hata'; self.paket.hata = String(e && e.message || e);
        });
    };

    /* Paket bölgesini [Tp, T) yeni listeyle kurar. Ekranda kalan adın
       (aynı ad + konum + tür) gösterim durumu, ölçülen genişliği ve DOM
       yuvası korunur (titreme yok); listeden düşen adın yuvası boşaltılır.
       Bozuk kayıt (adı boş, konumu/rank'ı sayı değil) basılmaz ve sayılmaz.
       liste boş + istek null: paketsiz duruma döner. */
    LaunchSiteLabels.prototype._paketUygula = function (liste, istek, kesildi) {
        var temiz = [], i, k;
        if (Array.isArray(liste)) {
            for (i = 0; i < liste.length; i++) {
                var x = liste[i];
                if (!x || typeof x.name !== 'string' || !x.name.trim()) continue;
                if (typeof x.lon !== 'number' || typeof x.lat !== 'number' || typeof x.rank !== 'number'
                        || !isFinite(x.lon) || !isFinite(x.lat) || !isFinite(x.rank)
                        || x.lat < -90 || x.lat > 90 || x.lon < -180 || x.lon > 180) continue;
                temiz.push({ name: x.name.trim(), lon: x.lon, lat: x.lat, rank: x.rank,
                             kind: (typeof x.kind === 'string') ? x.kind : '' });
            }
        }
        if (this._Tp === null) this._Tp = this.T;
        var Tp = this._Tp, P = temiz.length, T = Tp + P, eskiT = this.T;
        function kes(eski, Tur, uzunluk, kopya, dolgu) {
            var y = new Tur(uzunluk);
            y.set(eski.subarray(0, kopya));
            if (dolgu !== undefined) y.fill(dolgu, kopya);
            return y;
        }
        var eOnceki = this._onceki, eYuva = this._yuvaOf, eGen = this._genislik, eskiKimlik = {};
        for (k = Tp; k < eskiT; k++) eskiKimlik[this._pKimlik[k - Tp]] = k;
        this.xyz = kes(this.xyz, Float64Array, 3 * T, 3 * Tp);
        this.tur = kes(this.tur, Uint8Array, T, Tp);
        this.zAlt = kes(this.zAlt, Float32Array, T, Tp);
        this.zUst = kes(this.zUst, Float32Array, T, Tp, Infinity);
        this.lat = kes(this.lat, Float32Array, T, Tp);
        this.lon = kes(this.lon, Float32Array, T, Tp);
        this._onceki = kes(eOnceki, Uint8Array, T, Tp);
        this._simdiki = new Uint8Array(T);
        this._genislik = kes(eGen, Float32Array, T, Tp, NaN);
        this._yuvaOf = kes(eYuva, Int16Array, T, Tp, -1);
        this._aday = new Float64Array(T);
        this.ad.length = Tp; this.adEn.length = Tp; this.adTr.length = Tp;
        // Tekrar sınavının katlanmış adları: GeoNames yüklenmediyse NE kısmı burada kurulur.
        if (!this._katli) {
            var katliNe = new Array(Tp), neAdlar = {};
            for (k = 0; k < this.N; k++) {
                katliNe[k] = adKatla(this.adEn[k] || this.ad[k]);
                neAdlar[adKatla(this.ad[k])] = katliNe[k];
                neAdlar[adKatla(this.adTr[k])] = katliNe[k];
            }
            this._katli = katliNe; this._neAdlar = neAdlar;
        }
        this._katli.length = Tp;
        var donustur = this.opts.latLonToXYZ, kimlik = new Array(P);
        for (i = 0; i < P; i++) {
            var q = temiz[i];
            k = Tp + i;
            this.lat[k] = q.lat; this.lon[k] = q.lon;
            donustur(q.lat, q.lon, 1, this.xyz, 3 * k);
            this.tur[k] = (PAKET_RAMPA_TURLERI.indexOf(q.kind) >= 0) ? TUR_RAMPA : TUR_SEHIR;
            this.zAlt[k] = q.rank;
            this.ad.push(q.name); this.adEn.push(''); this.adTr.push('');
            var ka = adKatla(q.name);
            this._katli[k] = (this._neAdlar && this._neAdlar[ka]) || ka;
            kimlik[i] = q.name + '|' + q.lon.toFixed(5) + '|' + q.lat.toFixed(5) + '|' + this.tur[k];
            var ek = eskiKimlik[kimlik[i]];
            if (ek !== undefined) {
                delete eskiKimlik[kimlik[i]];
                this._onceki[k] = eOnceki[ek];
                this._genislik[k] = eGen[ek];
                var sl = eYuva[ek];
                if (sl >= 0 && this._yuvalar && this._yuvalar[sl]) { this._yuvaOf[k] = sl; this._yuvalar[sl].k = k; }
            }
        }
        // Listeden düşen ve ekranda olan adların yuvası boşaltılır.
        for (var id in eskiKimlik) {
            if (!Object.prototype.hasOwnProperty.call(eskiKimlik, id)) continue;
            var s = eYuva[eskiKimlik[id]];
            if (s >= 0 && this._yuvalar && this._yuvalar[s]) {
                var y = this._yuvalar[s];
                y.k = -1; y.x = NaN; y.y = NaN;
                y.el.style.visibility = 'hidden';
                this._bos.push(s);
            }
        }
        this._pKimlik = kimlik;
        this.T = T;
        this._paketSon = istek;
        this.paket.durum = istek ? 'hazir' : 'yok';
        this.paket.hata = null;
        this.paket.sayi = P;
        this.paket.z = istek ? istek.z : null;
        this.paket.dil = istek ? istek.dil : null;
        this.paket.kesildi = !!kesildi;
        this._surum = (this._surum || 0) + 1;      // kamera durağanken de yeniden yerleştir
    };

    // Paket adayları: rank <= z_web (histerezisli; NE MIN_ZOOM'uyla AYNI
    // kural, aynı ölçek), ufuk önünde ve ekranda (NDC). GeoNames eşiğinin
    // altında aday yok. ÖLÇÜLDÜ (Sinop 20 km): z12 karosundaki 77 adın 70'i
    // rank 13 taşıyor; gerçek Mercator düzeyiyle (12,8) süzülünce ekranda
    // paketten tek ad kalmıyordu, NE ile aynı ölçek (z_web 13,2) onları alır.
    // İstek düzeyi (yukarıda) enlem düzeltmelidir: karo sayısını sınırlar.
    LaunchSiteLabels.prototype._paketAdaylari = function (f, cx, cy, cz, R, n, e) {
        var Tp = this._Tp, zM = f.zWeb;
        if (Tp === null || this.T <= Tp || !(this._paketZM === this._paketZM)) return n;
        var esik = this._neZTavan, yeniAday = f.zWeb > esik;
        if (!yeniAday && !(f.zWeb > esik - Z_HISTEREZIS)) return n;
        var onceki = this._onceki, aday = this._aday, xyz = this.xyz, zAlt = this.zAlt, sayac = this._sayac;
        for (var k = Tp; k < this.T; k++) {
            var mz = zAlt[k];
            if (mz > zM + Z_HISTEREZIS) continue;
            if ((mz > zM || !yeniAday) && !onceki[k]) continue;
            var x = xyz[3 * k], y = xyz[3 * k + 1], w = xyz[3 * k + 2];
            if (!ufuktaGorunur(x, y, w, cx, cy, cz, R)) continue;
            var px = x * R, py = y * R, pz = w * R;
            var cw = e[3] * px + e[7] * py + e[11] * pz + e[15];
            if (!(cw > 0)) { sayac.ekranDisi++; continue; }
            var nx = (e[0] * px + e[4] * py + e[8] * pz + e[12]) / cw;
            var ny = (e[1] * px + e[5] * py + e[9] * pz + e[13]) / cw;
            if (nx < -1 || nx > 1 || ny < -1 || ny > 1) { sayac.ekranDisi++; continue; }
            aday[n++] = this._anahtar(k, onceki[k]);
        }
        return n;
    };

    // Sıralama anahtarı: önce (öncelik - histerezis payı), eşitlikte öncelik.
    // Tamsayı kodlanır ki tipli dizi yerinde, karşılaştırıcısız sıralansın.
    // Öncelik: [0, M) ülkeler, [M, M+N) yerler (dosya sırası).
    LaunchSiteLabels.prototype._anahtar = function (oncelik, gosterildi) {
        return (oncelik + (gosterildi ? 0 : ONCELIK_PAYI)) * this.T + oncelik;
    };

    LaunchSiteLabels.prototype._takas = function () {
        var t = this._onceki; this._onceki = this._simdiki; this._simdiki = t;
    };

    // Yerleşimi DOM havuzuna uygular. Ekranda kalan etiketin öğesi korunur;
    // yalnız konum (transform) yazılır.
    LaunchSiteLabels.prototype._domUygula = function () {
        var yuvalar = this._yuvalar;
        if (!yuvalar || !yuvalar.length) return;
        var gosterilen = this._onceki, yuvaOf = this._yuvaOf, bos = this._bos, i, y;
        // 1) Artık gösterilmeyenleri boşalt.
        for (i = 0; i < yuvalar.length; i++) {
            y = yuvalar[i];
            if (y.k >= 0 && !gosterilen[y.k]) {
                yuvaOf[y.k] = -1; y.k = -1; y.x = NaN; y.y = NaN;
                y.el.style.visibility = 'hidden';
                bos.push(i);
            }
        }
        // 2) Yerleşenleri yuvalara bağla, konumu yaz.
        var yer = this._yerlesim;
        for (i = 0; i < yer.length; i++) {
            var e = yer[i], s = yuvaOf[e.k];
            if (s < 0) {
                s = bos.pop();
                if (s === undefined) break;       // olmaz: havuz = tavan
                y = yuvalar[s];
                y.k = e.k; yuvaOf[e.k] = s;
                this._yuvaTuru(y, e.tur);
                y.metin.textContent = this._metin(e.k);
                y.yaz = false;
                y.el.style.visibility = 'visible';
            } else {
                y = yuvalar[s];
                this._yuvaTuru(y, e.tur);
                if (y.yaz) { y.metin.textContent = this._metin(e.k); y.yaz = false; }
            }
            // Öğenin sol üst köşesi: dikdörtgenin sol üstü (tek kaynak).
            var ox = e.x0, oy = e.y0;
            if (ox !== y.x || oy !== y.y) {
                y.x = ox; y.y = oy;
                y.el.style.transform = 'translate3d(' + ox + 'px,' + oy + 'px,0)';
            }
        }
    };

    // Tüm Dünya bandının eşiği: vektör basamak tablosunun 50m üst sınırı
    // (m/px). Vektör modülü yoksa null: bant tavanı uygulanamaz ve bu
    // getInfo().dunyaBandiMpp = null ile beyan edilir (sayfada modül her
    // zaman önce yüklenir; şablon bekçisi sırayı sınar).
    function dunyaBandiMpp() {
        var V = global.LaunchSiteVectors, B = V && V.BASAMAKLAR;
        if (!B) return null;
        for (var i = 0; i < B.length; i++) if (B[i].ad === '50m') return B[i].mppUst;
        return null;
    }

    // Kamera 'Tüm Dünya' düğmesinin mesafesinde ya da daha uzakta mı?
    // kameraMerkez: kameranın Dünya merkezine uzaklığı; tumDunya: kare
    // yükünün globalViewDist alanı. Biri yoksa ya da sonlu pozitif değilse
    // kural uygulanmaz (false); m/px bandı yine geçerlidir.
    function tumDunyaMesafesinde(kameraMerkez, tumDunya) {
        if (!(tumDunya > 0) || !isFinite(tumDunya) || !(kameraMerkez > 0) || !isFinite(kameraMerkez))
            return false;
        return kameraMerkez >= tumDunya * (1 - TUM_DUNYA_MESAFE_GORELI_PAY);
    }

    // Karenin etiket tavanı: tüm Dünya bandında (m/px > eşik) ya da kamera
    // 'Tüm Dünya' mesafesindeyken 40, değilse 150.
    function etiketTavani(mpp, kameraMerkez, tumDunya) {
        var esik = dunyaBandiMpp();
        if (esik != null && mpp > esik) return DUNYA_ETIKET_TAVANI;
        return tumDunyaMesafesinde(kameraMerkez, tumDunya) ? DUNYA_ETIKET_TAVANI : ETIKET_TAVANI;
    }

    function yuzdelik(dizi, n, q) {
        if (!n) return null;
        var a = Array.prototype.slice.call(dizi, 0, n).sort(function (x, y) { return x - y; });
        return a[Math.min(n - 1, Math.floor(q * (n - 1) + 0.5))];
    }

    // Ölçüm kancası (künye notu, K6 kabul ölçümü, testler). Sayılar canlıdır.
    LaunchSiteLabels.prototype.getInfo = function () {
        var n = Math.min(this._sureN, OLCUM_PENCERESI), s = this._sayac;
        return {
            durum: this.durum,
            hata: this.hata,
            dil: this._dil,
            gorunur: s.gorunur,
            aday: s.aday,
            ekranDisi: s.ekranDisi,
            cakismaGizli: s.cakisma,
            engel: s.engel || 0,
            tavanGizli: s.tavan,
            tavan: s.tavanDegeri != null ? s.tavanDegeri : ETIKET_TAVANI,
            dunyaBandiMpp: dunyaBandiMpp(),
            guncellemeSayisi: s.guncelleme,
            atlananKare: s.atlanan,
            guncellemeMs: { son: s.sonMs, medyan: yuzdelik(this._sureler, n, 0.5),
                            p95: yuzdelik(this._sureler, n, 0.95), ornek: n },
            kunye: this.kunye,
            // V307/FS-HARİTA: yakın ölçek katmanı (GeoNames) durumu.
            detay: { durum: this.detay.durum, hata: this.detay.hata,
                     yerSayisi: this.detay.yerSayisi, gorunur: this.detay.gorunur,
                     tekrarGizli: this.detay.tekrarGizli, kunye: this.detay.kunye },
            // V307/FS-HARİTA-KÜRE: indirilen paketten yer adları.
            paket: { durum: this.paket.durum, hata: this.paket.hata, sayi: this.paket.sayi,
                     gorunur: this.paket.gorunur, z: this.paket.z, dil: this.paket.dil,
                     kesildi: this.paket.kesildi, istek: this.paket.istek }
        };
    };

    // Son karenin yerleşimi: [{ad, tur, lat, lon, x0, y0, x1, y1, paket}] (ölçüm/test).
    LaunchSiteLabels.prototype.getPlacements = function () {
        var out = [], adlar = ['city', 'capital', 'country', 'launch'], Tp = this._Tp;
        for (var i = 0; i < this._yerlesim.length; i++) {
            var e = this._yerlesim[i];
            out.push({ ad: this._metin(e.k), tur: adlar[e.tur], lat: this.lat[e.k], lon: this.lon[e.k],
                       x0: e.x0, y0: e.y0, x1: e.x1, y1: e.y1, paket: Tp !== null && e.k >= Tp });
        }
        return out;
    };

    LaunchSiteLabels.prototype.dispose = function () {
        this._disposed = true;
        if (this._yuvalar) for (var i = 0; i < this._yuvalar.length; i++) {
            var el = this._yuvalar[i].el;
            if (el.parentNode) el.parentNode.removeChild(el);
        }
        this._yuvalar = [];
    };

    LaunchSiteLabels.ETIKET_TAVANI = ETIKET_TAVANI;
    LaunchSiteLabels.DUNYA_ETIKET_TAVANI = DUNYA_ETIKET_TAVANI;
    LaunchSiteLabels.etiketTavani = etiketTavani;
    LaunchSiteLabels.KOVA_DERECE = KOVA_DERECE;
    LaunchSiteLabels.IZGARA_PX = IZGARA_PX;
    LaunchSiteLabels.Z_HISTEREZIS = Z_HISTEREZIS;
    LaunchSiteLabels.YENI_ETIKET_PAYI_PX = YENI_ETIKET_PAYI_PX;
    LaunchSiteLabels.KENAR_SERIDI_PX = KENAR_SERIDI_PX;
    LaunchSiteLabels.kenaraYasla = kenaraYasla;
    LaunchSiteLabels.ONCELIK_PAYI = ONCELIK_PAYI;
    LaunchSiteLabels.adSec = adSec;
    LaunchSiteLabels.adDuzeltmeSayisi = adDuzeltmeSayisi;
    LaunchSiteLabels.ufuktaGorunur = ufuktaGorunur;
    LaunchSiteLabels.dikdortgen = dikdortgen;
    LaunchSiteLabels.Izgara = Izgara;
    LaunchSiteLabels.DOSYA_ADI_DESENI = DOSYA_ADI_DESENI;
    LaunchSiteLabels.DETAY_MANIFEST = DETAY_MANIFEST;
    LaunchSiteLabels.adKatla = adKatla;
    // V307/FS-HARİTA-KÜRE: paket yer adları (node bekçileri için)
    LaunchSiteLabels.gorunenKutu = gorunenKutu;
    LaunchSiteLabels.PAKET_ETIKET_UCU = PAKET_ETIKET_UCU;
    LaunchSiteLabels.PAKET_Z_TAVANI = PAKET_Z_TAVANI;
    LaunchSiteLabels.TUR_RAMPA = TUR_RAMPA;
    global.LaunchSiteLabels = LaunchSiteLabels;

})(typeof window !== 'undefined' ? window : this);
