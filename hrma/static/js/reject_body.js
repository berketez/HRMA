/* Ön yüzün TEK ret-gövdesi çözücüsü (4xx/5xx → kullanıcı metni).
 *
 * ÖH D31 · OH-D30-02 (hüküm-19, D30 raporları + Astra-1 çapraz denetimi).
 * ÖLÇÜLDÜ (docs/scofield/raw/OH/D31/arayuz-panel/a1/once.json · M1):
 * `HTTP error! status` kalıbı ALTI yerde yaşıyordu — app.js 1,
 * advanced.html 4, liquid.html 1 — ve bu altı yerin hiçbiri sunucunun
 * YAPILI ret gövdesini okumuyordu: `invalid_fields` ve `missing_fields`
 * alan adları (hrma/app.py'de 251 yayım noktası) kullanıcıya HİÇ
 * ulaşmıyordu. Kullanıcı "HTTP error! status: 422" görüyor, HANGİ alanın
 * neden reddedildiğini göremiyordu; `missing_fields` okuması app.js'te 0,
 * advanced.html'de 0, solid.html'de 0 idi.
 *
 * Kusur "metin güzel değil" değildir: ret GEREKÇESİ kullanıcıya inmediği
 * için kullanıcı fail-closed kapıyı bir çökme sanıyor ve düzeltemiyor.
 *
 * TEK KAYNAK (ÖH doktrini 4): şablon içi betikler ortak modül
 * paylaşmadığı için aynı çözücü üç şablonda kopyalanmıştı
 * (`_ihracRetMetni`; tests/test_d22_arayuz_a1.py::TestIhracRetMetni üç
 * kopyanın ayrışmasını bekçiye bağlamıştı — kopyayı ÖNLEMİYOR, yalnız
 * ayrışmayı yakalıyordu). Bu modül o borcu kapatır: gövde çözümü BİR
 * yerde yaşar, üç sayfa da (advanced/solid/liquid) onu yükler.
 *
 * FAIL-CLOSED: modül metin UYDURMAZ. Gövdedeki her parça sunucunun kendi
 * yayımıdır (`status` kodu, `message`/`error` cümlesi, `invalid_fields`
 * ve `missing_fields` alan adları). Gövde okunamazsa geriye yalnız
 * `HTTP <durum>` kalır — sahte bir gerekçe yazılmaz.
 */
(function (kok) {
    'use strict';

    /** Yapılı alan listesi → "ad (gerekçe)" dizeleri. Metin uydurulmaz. */
    function _alanlar(ham) {
        if (!Array.isArray(ham)) return [];
        return ham.map(function (x) {
            if (typeof x === 'string') return x;
            if (!x || typeof x !== 'object') return '';
            var ad = (typeof x.field === 'string') ? x.field : '';
            var nd = (typeof x.reason === 'string') ? x.reason : '';
            return ad + (nd ? ' (' + nd + ')' : '');
        }).filter(function (t) { return t; });
    }

    /** Sözlükten çeviri; sözlük yoksa ya da anahtar yoksa `yedek`. */
    function _ceviri(anahtar, params, yedek) {
        var I = kok.I18N;
        if (typeof anahtar !== 'string' || !anahtar || !I
                || typeof I.tf !== 'function') {
            return yedek;
        }
        if (typeof I.has === 'function' && !I.has(anahtar)) return yedek;
        return I.tf(anahtar, params || {}, yedek);
    }

    /** Emniyet kapısı gövdesinin parça başına gerekçe satırları.
     *
     * Gövde `message_key` taşımıyorsa `null` döner (eski sözleşmeli uçlar
     * AYNEN basılır). Her satır sunucunun `refusals[i]` kaydından kurulur:
     * `reason_key` metni, `part_key` parça adı; yer tutucular kaydın kendi
     * alanlarıdır.
     */
    function _kapiGerekceleri(govde) {
        if (typeof govde.message_key !== 'string' || !govde.message_key) {
            return null;
        }
        if (!Array.isArray(govde.refusals)) return [];
        return govde.refusals.map(function (r) {
            if (!r || typeof r !== 'object') return '';
            var p = {};
            Object.keys(r).forEach(function (k) {
                p[k] = (r[k] === null || r[k] === undefined) ? '-' : r[k];
            });
            p.part = _ceviri(r.part_key, null,
                             (typeof r.part === 'string') ? r.part : '');
            var yedek = (typeof r.part === 'string' ? r.part : '') + ': '
                + (typeof r.reason === 'string' ? r.reason : '');
            return _ceviri(r.reason_key, p, yedek);
        }).filter(function (t) { return t; });
    }

    /** Sunucu ret gövdesi → tek satır kullanıcı metni.
     *
     * Sıra: [makine kodu] cümle · geçersiz alanlar · eksik alanlar.
     * Hiçbiri yoksa `HTTP <durum>` (gövde okunamadı demektir).
     */
    function metni(govde, durum) {
        if (!govde || typeof govde !== 'object') return 'HTTP ' + durum;
        var parcalar = [];
        var kod = (typeof govde.status === 'string'
                   && govde.status !== 'error') ? govde.status : '';
        if (kod) parcalar.push('[' + kod + ']');
        var cumle = (typeof govde.message === 'string' && govde.message)
            ? govde.message
            : ((typeof govde.error === 'string' && govde.error)
                ? govde.error : '');
        // ÖH V3 CAD A1 · H5 — gövde i18n anahtarı taşıyorsa (imalat
        // emniyet kapısı) cümle ve parça başına gerekçe SÖZLÜKTEN basılır
        // (EN = TR); sözlük yoksa ya da anahtar bulunamazsa sunucunun EN
        // cümlesi kalır. Sayılar ve alan adları gövdeden gelir, uydurulmaz.
        var gerekceler = _kapiGerekceleri(govde);
        if (gerekceler !== null) {
            cumle = _ceviri(govde.message_key, govde.message_params, cumle);
        }
        if (cumle) parcalar.push(cumle);
        if (gerekceler !== null && gerekceler.length) {
            parcalar.push(gerekceler.join(' '));
        }
        // Gerekçe satırları alan adlarını zaten taşır; `invalid_fields`
        // listesi ikinci kez basılmaz.
        var gecersiz = (gerekceler !== null && gerekceler.length)
            ? [] : _alanlar(govde.invalid_fields);
        if (gecersiz.length) parcalar.push(gecersiz.join(', '));
        var eksik = _alanlar(govde.missing_fields);
        if (eksik.length) {
            // Eksik alan ile geçersiz alan AYRI hükümlerdir; birleştirmek
            // kullanıcıya "yanlış girdin" der, oysa uç "hiç göndermedin"
            // diyor. Ayrımı koruyan ön ek sunucunun kendi anahtarıdır.
            parcalar.push('missing_fields: ' + eksik.join(', '));
        }
        // `details` yalnız hiçbir yapılı alan yokken okunur: eski
        // sözleşmeli uçlar (motor_validation) gerekçeyi orada taşıyor.
        if (!gecersiz.length && !eksik.length
                && Array.isArray(govde.details) && govde.details.length) {
            parcalar.push(govde.details
                .filter(function (d) { return typeof d === 'string' && d; })
                .join(' · '));
        }
        return parcalar.length ? parcalar.join(' ') : ('HTTP ' + durum);
    }

    /** `Response` → kullanıcı metni. Gövde JSON değilse ham metne düşer.
     *
     * Gövde BİR KEZ okunur (Response gövdesi akıştır; ikinci okuma
     * `TypeError` verir). JSON ayrıştırılamazsa ham metin KISALTILARAK
     * basılır — 31 KB'lık HTML hata sayfasını ekrana dökmek kullanıcıya
     * gerekçe göstermez, gürültü gösterir.
     */
    function oku(response) {
        var durum = (response && response.status) || 0;
        return response.text().then(function (ham) {
            var j = null;
            try { j = JSON.parse(ham); } catch (e) { j = null; }
            if (j && typeof j === 'object') return metni(j, durum);
            var kisa = String(ham || '').trim().slice(0, 300);
            return kisa ? ('HTTP ' + durum + ': ' + kisa) : ('HTTP ' + durum);
        }, function () {
            return 'HTTP ' + durum;
        });
    }

    /** `!response.ok` dalında fırlatılacak hata. Çağıran yeri tek satır. */
    function hata(response) {
        return oku(response).then(function (m) { return new Error(m); });
    }

    var API = { metni: metni, oku: oku, hata: hata };
    kok.HRMAReject = API;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = API;
    }
}(typeof window !== 'undefined' ? window : globalThis));
