/* Ön yüzün TEK sayısal BİRİM ÇEVRİM kaynağı.
 *
 * ÖH D25 · OH-D24-05 (Fable-D19 arayuz bulgusu [9]). ÖLÇÜLDÜ
 * (docs/scofield/raw/OH/D25/arayuz/a2/once.json): `PA_PER_BAR = 1e5`
 * DÖRT ayrı JS dosyasında ayrı ayrı tanımlıydı — fea_panel.js,
 * motor_viz_deck.js, panels/cfd_panel.js, transient_panel.js — ve
 * paylaşılan bir JS sabit dosyası yoktu. Sayılar bugün aynı; kusur
 * sayının YANLIŞ olması değil, İKİ (dört) yerde YAŞAMASIdır (ÖH
 * doktrini 4, TEK KAYNAK): birinde düzeltilen bir çevrim diğerlerinde
 * sessizce eski kalır ve iki panel aynı basınca iki sayı yazar.
 *
 * Desen D17'deki `oxidizer_reference_density.js` ile aynıydı (o dosya
 * tek tüketicisi olan iki öksüz sayfayla ÖH D36'da söküldü): modül
 * kendini `window` üstüne yazar, tüketiciler ondan OKUR, kendi
 * kopyalarını tanımlamaz. Node tarafı için `module.exports` de var
 * (bekçiler dosyayı vm/require ile koşturuyor).
 *
 * FAIL-CLOSED: modül yüklenmemişse tüketici sessiz bir yedek sayı
 * UYDURMAZ — `requirePaPerBar()` hata fırlatır. Eksik <script> etiketi
 * ekranda yanlış bir basınç değil, görünür bir hata üretir.
 */
(function (kok) {
    'use strict';

    // Tek sayısal tanım. Ayrı bir `const` olarak durur ki hem ürün hem
    // bekçiler (bildirim kesiti) TEK bu satırı okusun.
    const PA_PER_BAR = 1e5;

    // ÖH D27 · OH-D26-16 (D26 arayuz a3 bulgusu). ÖLÇÜLDÜ
    // (a2/once.json `yuzde_yerel_tanim`): `const YUZDE = 100.0` İKİ
    // panelde ayrı ayrı yazılıydı — fea_panel.js:1316 ve
    // thermal_fea_panel.js:966 — ve ikisi de AYNI ucun aynı alanını
    // (`kalinlik_sapma_orani`) yüzdeye çeviriyordu. Sayı bugün aynı;
    // kusur sayının yanlış olması değil, İKİ yerde yaşamasıdır
    // (doktrin 4). Bu bir ölçüm sabiti değil, yüzdenin TANIMIdır:
    // 1 = %100 (ISO 80000-1, Ek A: "percent, % = 0,01").
    const PERCENT_PER_FRACTION = 100;

    var UNITS = {
        // 1 bar = 100 000 Pa — SI türetilmiş birim tanımı (BIPM SI
        // Broşürü, 9. baskı, Tablo 8: "bar, 1 bar = 100 kPa").
        // Tanım gereği KESİNdir, ölçülmüş bir sabit değildir.
        PA_PER_BAR: PA_PER_BAR,
        // Kesir -> yüzde çarpanı. Tanım gereği KESİNdir.
        PERCENT_PER_FRACTION: PERCENT_PER_FRACTION
    };

    function requirePaPerBar() {
        var v = UNITS.PA_PER_BAR;
        if (typeof v !== 'number' || !isFinite(v) || v <= 0) {
            throw new Error('units_constants.js: PA_PER_BAR unavailable — '
                + 'the shared unit module did not load. No fallback value '
                + 'is invented; fix the <script> order instead.');
        }
        return v;
    }

    // `requirePaPerBar`ın ikizi. FAIL-CLOSED: modül yüklenmemişse
    // yüzde çarpanı UYDURULMAZ, hata fırlar.
    function requirePercentPerFraction() {
        var v = UNITS.PERCENT_PER_FRACTION;
        if (typeof v !== 'number' || !isFinite(v) || v <= 0) {
            throw new Error('units_constants.js: PERCENT_PER_FRACTION '
                + 'unavailable — the shared unit module did not load. No '
                + 'fallback value is invented; fix the <script> order.');
        }
        return v;
    }

    kok.HRMAUnits = UNITS;
    kok.HRMAUnits.requirePaPerBar = requirePaPerBar;
    kok.HRMAUnits.requirePercentPerFraction = requirePercentPerFraction;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            UNITS: UNITS,
            requirePaPerBar: requirePaPerBar,
            requirePercentPerFraction: requirePercentPerFraction
        };
    }
}(typeof window !== 'undefined' ? window : globalThis));
