/* ====================================================================
   HRMA — "Yapay Zekâ ile Tasarla" — ai_assistant.js (v3.0.1, kulvar N-YZ)
   --------------------------------------------------------------------
   Üç tasarım sayfasının (hibrit / katı / sıvı) ORTAK yapay zekâ modülü.
   Eskiden her sayfa kendi "Ask AI to Analyze Results" düğmesini ve kendi
   kodunu taşıyordu (app.js askAI, solid.html askAI, liquid.html askAI):
   elle seçilmiş bir JSON + İngilizce sabit istem panoya kopyalanıyordu;
   girdilerin çoğu, tasarım niyeti, uyarılar/hükümler pakete girmiyor,
   asistanın önerisini programa geri almanın yolu yoktu.

   DÖNGÜ (uygulama içi LLM çağrısı, API anahtarı, ağ YOK):
     1. Tasarım hedefini yaz (proje ile kaydedilir: #hrma_ai_goal).
     2. Bağlamı kopyala → kendi asistanına yapıştır. Paket arayüz dilinde
        (TR/EN): hedef + formun TAMAMI + sonuçlar + uyarılar + hükümler +
        CEA bloğu + asistana talimat ve makinece okunur öneri şeması.
     3. Asistanın cevabını (ya da yalnız ```hrma-oneri bloğunu) yapıştır →
        HRMA bloğu ayıklar, DOĞRULAR, önce/sonra tablosunu gösterir.
        "Uygula" ya da "Uygula ve hesapla"; onaysız hiçbir şey değişmez.
     4. Hesaptan sonra devam paketi: son kopyalamadan bu yana değişen
        girdiler, uygulanan öneri, başlık sayıları önce/sonra, yeni ve
        kapanan uyarılar.

   GÜVENLİK — YAPIŞTIRILAN METİN GÜVENİLMEZDİR:
     * yalnız bu sayfanın form alanlarından beyaz liste (bilinmeyen alan
       adıyla reddedilir, sessizce yok sayılmaz);
     * sayı alanına yalnız sonlu SAYI (metin "25" reddedilir), seçiciye
       yalnız seçenek değeri, onay kutusuna yalnız true/false;
     * birim formun birimiyle uyuşmazsa ret — sessiz çevirme YOK;
     * motor tipi uyuşmazlığı, sürüm uyuşmazlığı, JSON hatası, fazla
       değişiklik → bloğun tamamı ADIYLA reddedilir;
     * gerekçe ve bütün yapıştırılan metin yalnız textContent / value ile
       basılır (HTML olarak YORUMLANMAZ);
     * yapıştırma alanının id'si YOKTUR → proje dosyasına yazılmaz.

   Sayfaya özgü kısım küçük bir adaptördür (ADAPTORLER): motor tipi, hesap
   işlevinin adı, başlık sayıları ve uyarı toplayıcısı. Şablon yalnız
   <section id="hrmaAiPanel" data-motor-type="..."> kabını ve bu betiği
   taşır; panelin tamamı burada kurulur.

   Bekçi: tests/test_v301_yapay_zeka.py · kanıt:
   docs/scofield/raw/OH/V301/yapay-zeka/
   ==================================================================== */
(function (root) {
    'use strict';

    // ------------------------------------------------------------------
    // Sabitler (tek kaynak; ipucu metinleri ve testler bu adlarla okur)
    // ------------------------------------------------------------------
    var SEMA_SURUMU = 1;              // "hrma_oneri": 1
    var BLOK_ETIKETI = 'hrma-oneri';  // ```hrma-oneri çit etiketi
    var AZAMI_DEGISIKLIK = 8;         // tek seferde en çok değişiklik
    var AZAMI_YAPISTIRMA = 100000;    // yapıştırılan metin, karakter
    var AZAMI_GEREKCE = 600;          // gerekçe metni, karakter (kırpılır)
    var AZAMI_METIN_DEGER = 500;      // metin alanına önerilen değer
    var AZAMI_HEDEF = 2000;           // tasarım hedefi alanı (maxlength)
    var AZAMI_SECENEK = 60;           // pakette seçici başına seçenek
    var PANEL_ID = 'hrmaAiPanel';
    var HEDEF_ID = 'hrma_ai_goal';
    var MODAL_ID = 'hrmaAiModal';
    var IZLEME_MS = 1000;             // sonuç kimliği yoklama aralığı

    var MOTOR_ADI = {
        tr: { hybrid: 'hibrit', solid: 'katı yakıtlı', liquid: 'sıvı yakıtlı' },
        en: { hybrid: 'hybrid', solid: 'solid', liquid: 'liquid' }
    };

    // ------------------------------------------------------------------
    // i18n köprüsü — i18n.js yoksa İngilizce yedek
    // ------------------------------------------------------------------
    function T(key, fallback) {
        var I = root.I18N;
        return (I && I.t) ? I.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        var I = root.I18N;
        if (I && I.tf) return I.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && Object.prototype.hasOwnProperty.call(params, name))
                ? String(params[name]) : whole;
        });
    }
    function dil() {
        var I = root.I18N;
        return (I && I.lang === 'tr') ? 'tr' : 'en';
    }
    function sahip(o, k) {
        return o !== null && typeof o === 'object'
            && Object.prototype.hasOwnProperty.call(o, k);
    }
    function sonluSayi(v) {
        return typeof v === 'number' && isFinite(v);
    }
    // 6 anlamlı basamak — pakette uzun kayan nokta kuyruğu taşınmaz.
    function yuvarla(v) {
        if (!sonluSayi(v)) return v;
        if (Number.isInteger(v)) return v;
        return parseFloat(v.toPrecision(6));
    }

    // ------------------------------------------------------------------
    // Birim karşılaştırması — ÇEVİRME YOK, yalnız yazım farkı tolere edilir
    // ------------------------------------------------------------------
    var BIRIMSIZ = { '': 1, '-': 1, '—': 1, '–': 1, 'dimensionless': 1,
                     'boyutsuz': 1, 'unitless': 1, 'none': 1 };
    function birimNormal(u) {
        if (u === null || u === undefined) return '';
        var s = String(u).trim().replace(/^[(\[]\s*|\s*[)\]]$/g, '');
        s = s.replace(/\s+/g, '').replace(/µ/g, 'μ').replace(/[⋅*]/g, '·').toLowerCase();
        return BIRIMSIZ[s] ? '' : s;
    }

    // ==================================================================
    // 1. ÖNERİ BLOĞU AYIKLAMA + DOĞRULAMA (saf; DOM'suz test edilir)
    // ==================================================================

    /** Metinden öneri nesnesini çıkarır.
     *  Dönüş: {ok:true, nesne} | {ok:false, kod, params} */
    function blokAyikla(metin) {
        if (typeof metin !== 'string' || !metin.trim()) {
            return { ok: false, kod: 'empty', params: {} };
        }
        if (metin.length > AZAMI_YAPISTIRMA) {
            return { ok: false, kod: 'too_long', params: { max: AZAMI_YAPISTIRMA } };
        }
        var cit = /```[ \t]*hrma-oneri[ \t]*\r?\n([\s\S]*?)```/gi;
        var bloklar = [];
        var m;
        while ((m = cit.exec(metin)) !== null) bloklar.push(m[1]);
        var govde;
        if (bloklar.length > 1) {
            return { ok: false, kod: 'multiple_blocks', params: { n: bloklar.length } };
        } else if (bloklar.length === 1) {
            govde = bloklar[0];
        } else {
            var duz = metin.trim();
            if (duz.charAt(0) === '{' && duz.indexOf('hrma_oneri') >= 0) {
                govde = duz;
            } else {
                return { ok: false, kod: 'no_block', params: {} };
            }
        }
        var nesne;
        try {
            nesne = JSON.parse(govde);
        } catch (e) {
            return { ok: false, kod: 'json',
                     params: { msg: String((e && e.message) || e).slice(0, 200) } };
        }
        if (!nesne || typeof nesne !== 'object' || Array.isArray(nesne)) {
            return { ok: false, kod: 'not_object', params: {} };
        }
        return { ok: true, nesne: nesne };
    }

    /** Tek bir değişiklik satırını alan tanımına karşı doğrular.
     *  `alan`: {id, type: number|select|checkbox|text, unit, options, min,
     *  max, label, value, disabled}. Dönüş: {ok, deger} | {ok:false, kod, params} */
    function satirDogrula(satir, alan) {
        var d = satir.deger;
        var tip = alan.type;
        if (tip === 'number') {
            if (typeof d !== 'number') {
                return { ok: false, kod: 'not_number', params: {} };
            }
            if (!isFinite(d)) return { ok: false, kod: 'not_finite', params: {} };
            // Aralık denetimi birimden SONRA (aşağıda): birimi yanlış bir
            // sayıyı aralıkla kıyaslamak anlamsızdır, ret nedeni birimdir.
        } else if (tip === 'select') {
            if (typeof d !== 'string' && typeof d !== 'number') {
                return { ok: false, kod: 'not_option', params: {} };
            }
            var secenekler = alan.options || [];
            var bulundu = false;
            for (var i = 0; i < secenekler.length; i++) {
                if (secenekler[i] === String(d)) { bulundu = true; break; }
            }
            if (!bulundu) return { ok: false, kod: 'not_option', params: {} };
            d = String(d);
        } else if (tip === 'checkbox') {
            if (typeof d !== 'boolean') {
                return { ok: false, kod: 'not_boolean', params: {} };
            }
        } else {
            if (typeof d !== 'string') return { ok: false, kod: 'not_text', params: {} };
            if (d.length > AZAMI_METIN_DEGER) {
                return { ok: false, kod: 'text_too_long', params: { max: AZAMI_METIN_DEGER } };
            }
            // Denetim karakterleri düşer (satır sonu ve sekme kalır).
            d = d.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, '');
        }
        // Birim: alan birimliyse öneri AYNI birimi yazmalı; çevirme yok.
        var alanBirim = birimNormal(alan.unit);
        var verilen = sahip(satir, 'birim') ? satir.birim : undefined;
        if (verilen !== undefined && verilen !== null && typeof verilen !== 'string') {
            return { ok: false, kod: 'unit_mismatch',
                     params: { got: String(verilen), unit: alan.unit || '' } };
        }
        var verilenN = birimNormal(verilen);
        if (alanBirim) {
            if (verilen === undefined || verilen === null || !verilenN) {
                return { ok: false, kod: 'unit_missing', params: { unit: alan.unit } };
            }
            if (verilenN !== alanBirim) {
                return { ok: false, kod: 'unit_mismatch',
                         params: { got: String(verilen), unit: alan.unit } };
            }
        } else if (verilenN) {
            return { ok: false, kod: 'unit_unexpected', params: { got: String(verilen) } };
        }
        if (tip === 'number') {
            var alt = sonluSayi(alan.min) ? alan.min : null;
            var ust = sonluSayi(alan.max) ? alan.max : null;
            if ((alt !== null && d < alt) || (ust !== null && d > ust)) {
                return { ok: false, kod: 'out_of_range',
                         params: { min: alt === null ? '−∞' : alt,
                                   max: ust === null ? '+∞' : ust } };
            }
        }
        if (alan.disabled) return { ok: false, kod: 'disabled', params: {} };
        return { ok: true, deger: d };
    }

    /** Yapıştırılan metni doğrular.
     *  `alanlar`: id → alan tanımı (bkz. satirDogrula). Dönüş:
     *  {ok:false, kod, params}  — blok bütünüyle reddedildi
     *  {ok:true, gecerli:[...], reddedilen:[...]}  — satır satır karar */
    function oneriDogrula(metin, motorTipi, alanlar) {
        var a = blokAyikla(metin);
        if (!a.ok) return a;
        var o = a.nesne;
        if (!sahip(o, 'hrma_oneri') || o.hrma_oneri !== SEMA_SURUMU) {
            return { ok: false, kod: 'version',
                     params: { v: sahip(o, 'hrma_oneri') ? String(o.hrma_oneri) : '—',
                               expected: SEMA_SURUMU } };
        }
        if (o.motor_type !== motorTipi) {
            return { ok: false, kod: 'motor_type',
                     params: { got: String(o.motor_type === undefined ? '—' : o.motor_type),
                               expected: motorTipi } };
        }
        if (!Array.isArray(o.degisiklikler) || !o.degisiklikler.length) {
            return { ok: false, kod: 'no_changes', params: {} };
        }
        if (o.degisiklikler.length > AZAMI_DEGISIKLIK) {
            return { ok: false, kod: 'too_many',
                     params: { n: o.degisiklikler.length, max: AZAMI_DEGISIKLIK } };
        }
        var gecerli = [], reddedilen = [], gorulen = Object.create(null);
        o.degisiklikler.forEach(function (satir, i) {
            var kayit = { sira: i + 1, alan: null, deger: null, gerekce: '' };
            if (!satir || typeof satir !== 'object' || Array.isArray(satir)
                || typeof satir.alan !== 'string' || !sahip(satir, 'deger')) {
                kayit.kod = 'bad_row';
                kayit.params = {};
                reddedilen.push(kayit);
                return;
            }
            kayit.alan = satir.alan.slice(0, 120);
            kayit.deger = satir.deger;
            kayit.gerekce = (typeof satir.gerekce === 'string')
                ? satir.gerekce.slice(0, AZAMI_GEREKCE) : '';
            if (!Object.prototype.hasOwnProperty.call(alanlar, satir.alan)) {
                kayit.kod = 'unknown_field';
                kayit.params = {};
                reddedilen.push(kayit);
                return;
            }
            if (gorulen[satir.alan]) {
                kayit.kod = 'duplicate';
                kayit.params = {};
                reddedilen.push(kayit);
                return;
            }
            gorulen[satir.alan] = true;
            var alan = alanlar[satir.alan];
            var s = satirDogrula(satir, alan);
            if (!s.ok) {
                kayit.kod = s.kod;
                kayit.params = s.params;
                kayit.etiket = alan.label;
                reddedilen.push(kayit);
                return;
            }
            gecerli.push({
                sira: i + 1, alan: satir.alan, etiket: alan.label,
                simdiki: alan.value, onerilen: s.deger, birim: alan.unit || '',
                gerekce: kayit.gerekce, aktif: alan.active !== false
            });
        });
        return { ok: true, gecerli: gecerli, reddedilen: reddedilen };
    }

    // Ret nedenlerinin kullanıcı metni (tek yer; tablo ve durum satırı okur).
    // Her kod kendi T/TF çağrısıyla yazılır: sözlük bekçisi anahtarı
    // yalnız literal çağrıda görür.
    var RET_KODLARI = ['empty', 'too_long', 'no_block', 'multiple_blocks', 'json', 'not_object', 'version', 'motor_type', 'no_changes', 'too_many', 'bad_row', 'unknown_field', 'duplicate', 'not_number', 'not_finite', 'out_of_range', 'not_option', 'not_boolean', 'not_text', 'text_too_long', 'unit_missing', 'unit_mismatch', 'unit_unexpected', 'disabled'];
    function retMetni(kod, params) {
        var p = params || {};
        switch (kod) {
        case 'empty': return TF('ai.err.empty', p, 'Nothing to check: paste the reply first.');
        case 'too_long': return TF('ai.err.too_long', p, 'The pasted text is longer than {max} characters.');
        case 'no_block': return TF('ai.err.no_block', p, 'No ```hrma-oneri block (or hrma_oneri JSON) was found in the text.');
        case 'multiple_blocks': return TF('ai.err.multiple_blocks', p, '{n} hrma-oneri blocks were found; paste only the one you want to apply.');
        case 'json': return TF('ai.err.json', p, 'The block is not valid JSON: {msg}');
        case 'not_object': return TF('ai.err.not_object', p, 'The block must be a JSON object.');
        case 'version': return TF('ai.err.version', p, 'Unsupported block version: hrma_oneri = {v} (expected {expected}).');
        case 'motor_type': return TF('ai.err.motor_type', p, 'The block is for motor type "{got}" but this page is "{expected}".');
        case 'no_changes': return TF('ai.err.no_changes', p, 'The block has no "degisiklikler" list of changes.');
        case 'too_many': return TF('ai.err.too_many', p, 'The block proposes {n} changes; at most {max} are accepted at once.');
        case 'bad_row': return TF('ai.rej.bad_row', p, 'the line is not an object with "alan" and "deger"');
        case 'unknown_field': return TF('ai.rej.unknown_field', p, 'not a field of this page');
        case 'duplicate': return TF('ai.rej.duplicate', p, 'the field appears more than once');
        case 'not_number': return TF('ai.rej.not_number', p, 'the value is not a number (text is not accepted for a numeric field)');
        case 'not_finite': return TF('ai.rej.not_finite', p, 'the value is not a finite number');
        case 'out_of_range': return TF('ai.rej.out_of_range', p, 'outside the accepted range {min} … {max}');
        case 'not_option': return TF('ai.rej.not_option', p, 'not one of the options of this menu');
        case 'not_boolean': return TF('ai.rej.not_boolean', p, 'the value must be true or false');
        case 'not_text': return TF('ai.rej.not_text', p, 'the value must be text');
        case 'text_too_long': return TF('ai.rej.text_too_long', p, 'the text is longer than {max} characters');
        case 'unit_missing': return TF('ai.rej.unit_missing', p, 'unit missing (field unit: {unit})');
        case 'unit_mismatch': return TF('ai.rej.unit_mismatch', p, 'unit "{got}" does not match the field unit "{unit}" (no conversion is made)');
        case 'unit_unexpected': return TF('ai.rej.unit_unexpected', p, 'unit "{got}" given for a field without a unit');
        case 'disabled': return TF('ai.rej.disabled', p, 'the field is disabled on this page');
        default: return TF('ai.rej.bad_row', p, 'the line is not an object with "alan" and "deger"');
        }
    }

    // ==================================================================
    // 2. FORM ALANLARI — formun TAMAMI (elle seçilmiş alt küme değil)
    // ==================================================================
    //
    // Alan kümesinin TEK tanımı proje kaydıdır: project_bar.js
    // `_buildPayload(...).inputs.fields` — kaydedilen her alan formun
    // alanıdır (dinamik paneller, dil seçici, dosya/düğme girdileri HARİÇ;
    // dışlama listesi orada yaşar, burada KOPYALANMAZ). Hibrit tasarım
    // panelinin köken kapılı alanları (data-hrma-source-gate="1") damgasız
    // iken kaydedilmez ama formdadır: onlar da eklenir. Bu modülün kendi
    // alanları (tasarım hedefi) form alanı sayılmaz; hedef ayrı bölümdür.

    function cssKacis(s) {
        if (root.CSS && root.CSS.escape) return root.CSS.escape(s);
        return String(s).replace(/["\\]/g, '\\$&');
    }

    function formAlanIdleri(doc) {
        var kume = Object.create(null);
        var pb = root.HRMAProjectBar;
        var kaynak = 'project_bar';
        try {
            if (pb && typeof pb._buildPayload === 'function') {
                var f = pb._buildPayload('ai-context').inputs.fields || {};
                Object.keys(f).forEach(function (id) { kume[id] = true; });
            } else {
                kaynak = 'document';
            }
        } catch (e) {
            kaynak = 'document';
        }
        if (kaynak === 'document') {
            var hepsi = doc.querySelectorAll('input[id], select[id], textarea[id]');
            for (var i = 0; i < hepsi.length; i++) {
                var t = (hepsi[i].getAttribute('type') || '').toLowerCase();
                if (t === 'file' || t === 'button' || t === 'submit' || t === 'radio') continue;
                if (hepsi[i].id === 'langSelect') continue;
                kume[hepsi[i].id] = true;
            }
        }
        var kapili = doc.querySelectorAll('[data-hrma-source-gate="1"][id]');
        for (var j = 0; j < kapili.length; j++) kume[kapili[j].id] = true;
        var panel = doc.getElementById(PANEL_ID);
        // Belge sırası korunur (kullanıcı formu yukarıdan aşağı okur).
        var sirali = [];
        var dugumler = doc.querySelectorAll('input[id], select[id], textarea[id]');
        for (var k = 0; k < dugumler.length; k++) {
            var el = dugumler[k];
            if (!kume[el.id]) continue;
            if (panel && panel.contains(el)) continue;
            if (el.id === HEDEF_ID) continue;
            sirali.push(el);
            kume[el.id] = false;    // aynı id iki kez gelmesin
        }
        return sirali;
    }

    function etiketMetni(doc, el) {
        var lab = doc.querySelector('label[for="' + cssKacis(el.id) + '"]');
        if (!lab && el.closest) lab = el.closest('label');
        if (!lab && el.closest) {
            var grup = el.closest('.form-group');
            if (grup) lab = grup.querySelector('label');
        }
        var metin = '';
        if (lab) {
            var kopya = lab.cloneNode(true);
            var at = kopya.querySelectorAll('.tooltip, .tooltip-text, .tooltip-icon, '
                + 'input, select, textarea, button, script, style');
            for (var i = 0; i < at.length; i++) {
                if (at[i].parentNode) at[i].parentNode.removeChild(at[i]);
            }
            metin = String(kopya.textContent || '');
        }
        if (!metin.trim()) {
            metin = el.getAttribute('aria-label') || el.getAttribute('title')
                || el.getAttribute('placeholder') || '';
        }
        return metin.replace(/\s+/g, ' ').trim().slice(0, 160);
    }

    // Birim etiketten okunur: (…) ya da […] parçalarından SONUNCU geçerli
    // birim; yoksa data-unit. Parantez içi bir sembol ("(n)", "(Cf)",
    // "(P/Pc)") ya da açıklama ("(auto-filled after calculate)") birim
    // DEĞİLDİR: her alfabetik parça bilinen birim simgeleri listesinde
    // olmalı (üsler — "bar^n" — ayıklanır). Etiket birim söylemiyorsa birim
    // UYDURULMAZ (null) ve öneri satırı birimsiz yazılmalıdır.
    var BIRIM_SIMGELERI = {
        N: 1, kN: 1, MN: 1, s: 1, ms: 1, min: 1, h: 1, kg: 1, g: 1, t: 1,
        mol: 1, kmol: 1, m: 1, mm: 1, cm: 1, km: 1, um: 1, 'μm': 1, L: 1,
        K: 1, C: 1, '°C': 1, '°': 1, deg: 1, rad: 1, bar: 1, mbar: 1, Pa: 1,
        kPa: 1, MPa: 1, GPa: 1, psi: 1, psia: 1, atm: 1, Hz: 1, kHz: 1,
        W: 1, kW: 1, MW: 1, J: 1, kJ: 1, MJ: 1, '%': 1, m2: 1, m3: 1,
        'm²': 1, 'm³': 1, mm2: 1, 'mm²': 1, 'mm³': 1, cm2: 1, 'cm²': 1,
        'cm³': 1, rpm: 1, V: 1, A: 1, dB: 1, ppm: 1, lbf: 1, lb: 1, 'in': 1,
        ft: 1, kgf: 1, mN: 1, mg: 1, Ns: 1, cc: 1, degrees: 1, degree: 1,
        cycles: 1, months: 1, days: 1, years: 1,
        // Türkçe arayüz etiketlerindeki birim sözcükleri
        derece: 1, 'çevrim': 1, ay: 1, saniye: 1, dakika: 1, 'gün': 1, 'yıl': 1
    };
    function birimMi(aday) {
        var s = String(aday).trim();
        if (!s || s.length > 24) return false;
        if (!/^[A-Za-zçğıöşüÇĞİÖŞÜµμ°%²³·⋅*\/^\-+0-9 .()]+$/.test(s)) return false;
        s = s.replace(/\^[-+]?[\w.]+/g, '');           // üsler: bar^n, s^-1
        var parcalar = s.split(/[\/·⋅*() .\-+]+/).filter(function (p) {
            return p && !/^[0-9]+$/.test(p);
        });
        if (!parcalar.length) return false;
        for (var i = 0; i < parcalar.length; i++) {
            var p = parcalar[i].replace(/µ/g, 'μ');
            if (!Object.prototype.hasOwnProperty.call(BIRIM_SIMGELERI, p)) return false;
        }
        return true;
    }
    function etikettenBirim(etiket, el) {
        var acik = el.getAttribute && el.getAttribute('data-unit');
        if (acik) return acik.trim();
        var m, adaylar = [];
        var re = /[(\[]([^()\[\]]{1,40})[)\]]/g;
        while ((m = re.exec(etiket)) !== null) adaylar.push(m[1].trim());
        for (var i = adaylar.length - 1; i >= 0; i--) {
            if (birimMi(adaylar[i])) return adaylar[i];
            // "(% of fuel flow)", "(μm Ra)", "(± derece)", "(elle, %)",
            // "(yakıt debisinin %'si)": parçalardan biri birimse o (sondan).
            var sozcukler = adaylar[i].replace(/^±\s*/, '').split(/[\s,;]+/);
            if (sozcukler.length > 1) {
                for (var j = sozcukler.length - 1; j >= 0; j--) {
                    var sz = sozcukler[j].split(/['’]/)[0];
                    if (sz && birimMi(sz)) return sz;
                }
            }
        }
        return null;
    }

    function alanTipi(el) {
        var tag = el.tagName ? el.tagName.toLowerCase() : '';
        if (tag === 'select') return 'select';
        var t = (el.getAttribute('type') || '').toLowerCase();
        if (t === 'checkbox') return 'checkbox';
        if (t === 'number' || t === 'range') return 'number';
        return 'text';
    }

    function alanDegeri(el, tip) {
        if (tip === 'checkbox') return !!el.checked;
        var ham = (el.value === null || el.value === undefined) ? '' : String(el.value);
        if (tip === 'number') {
            if (ham.trim() === '') return '';
            var n = parseFloat(ham);
            return isFinite(n) ? n : ham;
        }
        return ham;
    }

    function varsayilanMi(el, tip) {
        if (tip === 'checkbox') return el.checked === el.defaultChecked;
        if (tip === 'select') {
            for (var i = 0; i < el.options.length; i++) {
                if (el.options[i].defaultSelected) return el.options[i].value === el.value;
            }
            return el.selectedIndex === 0;
        }
        return String(el.value) === String(el.defaultValue);
    }

    function gorunurMu(el) {
        try {
            if (el.getClientRects && el.getClientRects().length > 0) return true;
            return el.offsetParent !== null;
        } catch (e) { return true; }
    }

    // Yanıt künyelerinden alan → bilgi haritası (kaynak / hesaba girdi mi).
    function kunyeHaritasi(sonuc) {
        var h = Object.create(null);
        function ekle(id, anahtar, deger) {
            if (typeof id !== 'string' || !id) return;
            if (!h[id]) h[id] = {};
            h[id][anahtar] = deger;
        }
        if (!sonuc || typeof sonuc !== 'object') return h;
        (Array.isArray(sonuc.defaults_applied) ? sonuc.defaults_applied : [])
            .forEach(function (d) {
                if (!d || typeof d !== 'object') return;
                ekle(d.field, 'server_default', {
                    value: yuvarla(d.value), unit: d.unit || null,
                    reason: d.reason || null,
                    message: typeof d.message === 'string' ? d.message.slice(0, 400) : null
                });
            });
        (Array.isArray(sonuc.inputs_not_used) ? sonuc.inputs_not_used : [])
            .forEach(function (d) {
                if (!d || typeof d !== 'object') return;
                ekle(d.field, 'not_used', {
                    reason: d.reason || null,
                    used_by_model: (d.used_by_model !== undefined) ? yuvarla(d.used_by_model) : undefined,
                    message: typeof d.message === 'string' ? d.message.slice(0, 400) : null
                });
            });
        var u = sonuc.unwired_inputs;
        if (u && typeof u === 'object' && !Array.isArray(u)) {
            Object.keys(u).forEach(function (kategori) {
                (Array.isArray(u[kategori]) ? u[kategori] : []).forEach(function (id) {
                    ekle(id, 'not_used', { reason: kategori });
                });
            });
        }
        (Array.isArray(sonuc.input_warnings) ? sonuc.input_warnings : [])
            .forEach(function (w) {
                var p = w && w.params;
                if (p && typeof p.field === 'string') {
                    ekle(p.field, 'input_warning', w.code || null);
                }
            });
        return h;
    }

    /** Formun TAMAMI → alan kayıtları (paket) + doğrulama tanımları. */
    function alanlariTopla(doc, sonuc) {
        var kunye = kunyeHaritasi(sonuc);
        var kayitlar = [];
        var tanimlar = Object.create(null);
        formAlanIdleri(doc).forEach(function (el) {
            var tip = alanTipi(el);
            var etiket = etiketMetni(doc, el);
            var birim = etikettenBirim(etiket, el);
            var deger = alanDegeri(el, tip);
            var k = { id: el.id, label: etiket, value: deger };
            if (birim) k.unit = birim;
            k.type = tip;
            var secenekler = null;
            if (tip === 'select') {
                secenekler = [];
                for (var i = 0; i < el.options.length; i++) {
                    secenekler.push(String(el.options[i].value));
                }
                var secili = el.options[el.selectedIndex];
                if (secili) k.value_text = String(secili.textContent || '').trim().slice(0, 120);
                k.options = secenekler.slice(0, AZAMI_SECENEK);
                if (secenekler.length > AZAMI_SECENEK) k.options_total = secenekler.length;
            }
            var min = null, max = null;
            if (tip === 'number') {
                var mn = parseFloat(el.getAttribute('min'));
                var mx = parseFloat(el.getAttribute('max'));
                if (isFinite(mn)) min = mn;
                if (isFinite(mx)) max = mx;
                if (min !== null || max !== null) k.range = [min, max];
            }
            // Kaynak
            var damga = el.dataset ? el.dataset.hrmaSource : null;
            var bos = (deger === '' || deger === null);
            if (damga === 'user' || damga === 'project_file') {
                k.source = damga;
            } else if (el.dataset && el.dataset.hrmaSourceGate === '1') {
                k.source = 'not_sent_until_edited';
            } else if (bos) {
                k.source = 'empty';
            } else if (varsayilanMi(el, tip)) {
                k.source = 'page_default';
            } else {
                k.source = 'user';
            }
            var bilgi = kunye[el.id];
            if (bilgi) {
                if (bilgi.server_default) k.server_default = bilgi.server_default;
                if (bilgi.not_used) k.not_used = bilgi.not_used;
                if (bilgi.input_warning) k.input_warning = bilgi.input_warning;
            }
            if (!gorunurMu(el)) k.active = false;
            if (el.disabled) k.disabled = true;
            kayitlar.push(k);
            tanimlar[el.id] = {
                id: el.id, type: tip, unit: birim, options: secenekler,
                min: min, max: max, label: etiket, value: deger,
                disabled: !!el.disabled, active: k.active !== false
            };
        });
        return { kayitlar: kayitlar, tanimlar: tanimlar };
    }

    // ==================================================================
    // 3. SONUÇLAR — başlık sayıları, uyarılar, hükümler, CEA
    // ==================================================================

    function yolOku(o, yol) {
        var parca = yol.split('.');
        for (var i = 0; i < parca.length; i++) {
            if (!o || typeof o !== 'object') return undefined;
            o = o[parca[i]];
        }
        return o;
    }

    // Sayfaya özgü adaptörler. Başlık sayıları yanıtın KENDİ anahtarlarıyla
    // ve yanıtın birimiyle taşınır (ölçülmüş: hibrit çapları metre, katı
    // çapları mm, sıvı *_mm anahtarları mm). Sayı yoksa satır yazılmaz.
    var ADAPTORLER = {
        hybrid: {
            hesapIslevi: 'calculate',
            // Hibrit yanıtının başlık sayıları 'motor' sözlüğünde durur.
            kok: 'motor',
            baslik: [
                ['thrust', 'N'], ['isp', 's'], ['burn_time', 's'],
                ['total_impulse', 'N·s'], ['chamber_pressure', 'bar'],
                ['of_ratio', '-'], ['c_star', 'm/s'], ['cf', '-'],
                ['mdot_total', 'kg/s'], ['propellant_mass_total', 'kg'],
                ['fuel_mass', 'kg'], ['oxidizer_mass', 'kg'],
                ['chamber_temperature', 'K'], ['chamber_diameter', 'm'],
                ['chamber_length', 'm'], ['throat_diameter', 'm'],
                ['exit_diameter', 'm'], ['expansion_ratio', '-'],
                ['port_diameter_initial', 'm'], ['port_diameter_final', 'm']
            ],
            uyarilar: function (r) {
                if (typeof root.collectResultWarnings !== 'function') return null;
                return root.collectResultWarnings(r);
            },
            // Hibrit sayfasının bekçili ayrıntı yükü (app.js prepareAIData):
            // lüle açıları, enjektör, yapısal emniyet blokları çözücüden.
            ayrinti: function (r) {
                if (typeof root.prepareAIData !== 'function') return null;
                try {
                    var a = root.prepareAIData(r);
                    if (a && typeof a === 'object') delete a.warnings;   // ayrıca taşınıyor
                    return a;
                } catch (e) { return null; }
            }
        },
        solid: {
            hesapIslevi: 'calculateSolid',
            baslik: [
                ['total_impulse', 'N·s'], ['isp_sea_level', 's'], ['isp_vacuum', 's'],
                ['average_thrust', 'N'], ['max_thrust', 'N'], ['burn_time', 's'],
                ['propellant_mass', 'kg'], ['chamber_pressure', 'bar'],
                ['c_star', 'm/s'], ['chamber_temperature', 'K'],
                ['throat_diameter', 'mm'], ['exit_diameter', 'mm'],
                ['expansion_ratio', '-'], ['chamber_diameter', 'mm'],
                ['grain_length', 'mm'], ['core_diameter', 'mm'],
                ['grain_type', null], ['propellant_name', null]
            ],
            uyarilar: function (r) {
                var out = [];
                ['warnings', 'design_warnings'].forEach(function (k) {
                    (Array.isArray(r[k]) ? r[k] : []).forEach(function (w) { out.push(w); });
                });
                var nm = yolOku(r, 'nozzle_material_analysis.warnings');
                (Array.isArray(nm) ? nm : []).forEach(function (w) { out.push(w); });
                return out;
            }
        },
        liquid: {
            hesapIslevi: 'calculateLiquid',
            baslik: [
                ['thrust', 'N'], ['thrust_vacuum', 'N'], ['isp_sea_level', 's'],
                ['isp_vacuum', 's'], ['c_star', 'm/s'], ['chamber_pressure', 'bar'],
                ['mixture_ratio', '-'], ['chamber_temperature', 'K'],
                ['total_mass_flow', 'kg/s'], ['thrust_to_weight', '-'],
                ['engine_mass_estimate', 'kg'], ['throat_diameter_mm', 'mm'],
                ['exit_diameter_mm', 'mm'], ['chamber_diameter_mm', 'mm'],
                ['chamber_length_mm', 'mm'], ['expansion_ratio', '-'],
                ['cooling_type', null], ['propellant_name', null]
            ],
            uyarilar: function (r) {
                if (typeof root.liquidCollectWarnings !== 'function') return null;
                // Sıvı toplayıcısı önem derecesini EKRAN ETİKETİ olarak taşır
                // ("CRITICAL" / "KRİTİK"); pakette dil bağımsız ada çevrilir.
                var kritik = T('liq.msg.critical_warning_tag', 'CRITICAL');
                var girdi = T('liq.msg.input_warning_tag', 'INPUT');
                return root.liquidCollectWarnings(r).map(function (w) {
                    return { code: w.code || null, text: w.text,
                             severity: w.tag === kritik ? 'critical'
                                 : (w.tag === girdi ? 'input' : 'warning') };
                });
            }
        }
    };

    function baslikSayilari(adaptor, r) {
        var out = [];
        var onek = adaptor.kok ? adaptor.kok + '.' : '';
        adaptor.baslik.forEach(function (b) {
            var yol = onek + b[0];
            var v = yolOku(r, yol);
            if (sonluSayi(v)) {
                var k = { key: yol, value: yuvarla(v) };
                if (b[1]) k.unit = b[1];
                out.push(k);
            } else if (typeof v === 'string' && v && b[1] === null) {
                out.push({ key: yol, value: v.slice(0, 120) });
            }
        });
        return out;
    }

    // Uyarı kaydını tek biçime indirir: {severity, code, text}. Metin
    // arayüz dilinde: kodun sözlükte karşılığı varsa o, yoksa sunucu metni.
    function uyariKaydi(w) {
        if (w === null || w === undefined) return null;
        if (typeof w !== 'object') {
            var s = String(w).trim();
            return s ? { severity: null, code: null, text: s.slice(0, 600) } : null;
        }
        var code = (typeof w.code === 'string') ? w.code : null;
        var sev = w.severity || w.level || w.tag || null;
        var text = null;
        var I = root.I18N;
        if (typeof w.text === 'string' && w.text) {
            text = w.text;
        } else if (code && I && I.has && I.has(code)) {
            text = I.tf(code, w.params || {}, w.fallback || w.message || code);
        } else {
            text = w.message || w.fallback || code || '';
            if (w.params && typeof text === 'string') {
                text = text.replace(/\{(\w+)\}/g, function (whole, name) {
                    return sahip(w.params, name) ? String(w.params[name]) : whole;
                });
            }
        }
        return { severity: sev ? String(sev).toLowerCase() : null, code: code,
                 text: String(text).replace(/\s+/g, ' ').trim().slice(0, 600) };
    }

    function uyarilariTopla(adaptor, r) {
        var ham = null;
        try { ham = adaptor.uyarilar(r); } catch (e) { ham = null; }
        if (!Array.isArray(ham)) ham = [];
        // input_warnings her sayfada ayrıca okunur (tekilleştirilir).
        (Array.isArray(r.input_warnings) ? r.input_warnings : []).forEach(function (w) {
            ham.push(w);
        });
        var gorulen = Object.create(null), out = [];
        ham.forEach(function (w) {
            var k = uyariKaydi(w);
            if (!k || !k.text) return;
            var anahtar = (k.code || '') + '|' + k.text;
            if (gorulen[anahtar]) return;
            gorulen[anahtar] = true;
            out.push(k);
        });
        var sira = { critical: 0, error: 0, high: 0, warning: 1, medium: 1, info: 2, low: 2 };
        out.sort(function (a, b) {
            var x = sira[a.severity] !== undefined ? sira[a.severity] : 1;
            var y = sira[b.severity] !== undefined ? sira[b.severity] : 1;
            return x - y;
        });
        return out;
    }

    // Geri çekilen hükümler ve geçerlilik sınırları: yanıtın içinde ADIYLA
    // duran beyanlar derinlemesine taranır. Aynı motor sözlüğünün yansıları
    // (openrocket / trajectory / plots / cad) taranmaz — aynı hüküm iki kez
    // sayılmasın. Sayı uydurulmaz; yalnız beyanın kendisi taşınır.
    var YANSI_KOKLER = { openrocket: 1, trajectory: 1, plots: 1, cad_design: 1,
                         flight_simulation: 1, performance_maps: 1, throttle_map: 1 };
    function hukumleriTopla(r) {
        var geri = [], sinir = [], gorulen = Object.create(null);
        function ekle(liste, kayit) {
            var a = JSON.stringify(kayit);
            if (gorulen[a]) return;
            gorulen[a] = true;
            liste.push(kayit);
        }
        function gez(o, yol, derinlik) {
            if (!o || typeof o !== 'object' || derinlik > 9) return;
            if (Array.isArray(o)) {
                for (var i = 0; i < o.length && i < 60; i++) {
                    gez(o[i], yol + '[' + i + ']', derinlik + 1);
                }
                return;
            }
            Object.keys(o).forEach(function (k) {
                if (!yol && YANSI_KOKLER[k]) return;
                var v = o[k];
                var p = yol ? yol + '.' + k : k;
                if (k === 'verdict_withheld' && v === true) {
                    ekle(geri, { path: p, reasons: o.verdict_withheld_reasons || null });
                } else if (/_withheld_because$/.test(k) && typeof v === 'string') {
                    ekle(geri, { path: p, because: v.slice(0, 300) });
                } else if (/_withheld_reason$/.test(k) && typeof v === 'string' && v) {
                    ekle(geri, { path: p, reason: v.slice(0, 300) });
                } else if (k === 'model_validity_approvals_withheld' && Array.isArray(v) && v.length) {
                    ekle(geri, { path: p, items: v.slice(0, 20) });
                } else if (k === 'model_validity_limit_exceeded' && v === true) {
                    ekle(sinir, { path: p, reasons: o.model_validity_reasons || null });
                } else if ((k === 'validity_note' || k === 'validity_warning')
                           && typeof v === 'string' && v) {
                    ekle(sinir, { path: p, note: v.slice(0, 300) });
                } else if (k === 'outside_validity_band' && v === true) {
                    ekle(sinir, { path: p });
                } else if (/validity_limit_exceeded$/.test(k) && v === true
                           && k !== 'model_validity_limit_exceeded') {
                    ekle(sinir, { path: p });
                }
                if (v && typeof v === 'object') gez(v, p, derinlik + 1);
            });
        }
        gez(r, '', 0);
        return { withheld: geri.slice(0, 40), validity: sinir.slice(0, 40),
                 withheld_total: geri.length, validity_total: sinir.length };
    }

    function ceaOzeti(r) {
        var c = r && r.cea_comparison;
        if (!c || typeof c !== 'object') return null;
        var out = { status: c.status || null };
        if (c.reason) out.reason = String(c.reason).slice(0, 300);
        if (c.operating_point) out.operating_point = c.operating_point;
        if (Array.isArray(c.rows)) {
            out.rows = c.rows.slice(0, 20).map(function (row) {
                var k = { quantity: row.quantity, unit: row.unit || null,
                          hrma: yuvarla(row.hrma), cea: yuvarla(row.cea),
                          delta_pct: yuvarla(row.delta_pct) };
                if (row.relation) k.relation = row.relation;
                if (row.explained_by && row.explained_by.factor) {
                    k.explained_by = row.explained_by.factor;
                }
                return k;
            });
        }
        if (c.advisory_note) out.advisory_note = String(c.advisory_note).slice(0, 400);
        return out;
    }

    function sonucBolumu(adaptor, r) {
        if (!r || typeof r !== 'object') return null;
        var h = hukumleriTopla(r);
        var out = {
            headline: baslikSayilari(adaptor, r),
            warnings: uyarilariTopla(adaptor, r),
            withheld_verdicts: h.withheld,
            validity_limits: h.validity
        };
        if (h.withheld_total > h.withheld.length) out.withheld_verdicts_total = h.withheld_total;
        if (h.validity_total > h.validity.length) out.validity_limits_total = h.validity_total;
        var cea = ceaOzeti(r);
        if (cea) out.cea_comparison = cea;
        if (adaptor.ayrinti) {
            var a = adaptor.ayrinti(r);
            if (a) out.detail = a;
        }
        return out;
    }

    // ==================================================================
    // 4. İSTEM (asistana talimat) — arayüz dilinde
    // ==================================================================

    function ornekBlok(motorTipi) {
        return '```' + BLOK_ETIKETI + '\n'
            + '{"hrma_oneri": ' + SEMA_SURUMU + ', "motor_type": "' + motorTipi
            + '", "degisiklikler": [\n'
            + '  {"alan": "chamber_pressure", "deger": 25, "birim": "bar", "gerekce": "…"}\n'
            + ']}\n```';
    }

    function istemMetni(lang, motorTipi) {
        var ad = (MOTOR_ADI[lang] || MOTOR_ADI.en)[motorTipi] || motorTipi;
        var blok = ornekBlok(motorTipi);
        if (lang === 'tr') {
            return [
                'Sen bir itki sistemi ön tasarım asistanısın. Kullanıcı HRMA (roket motoru ön tasarım aracı) ile ' + ad + ' bir motor tasarlıyor. Aşağıda kullanıcının tasarım hedefi, HRMA formunun TAMAMI ve HRMA\'nın son hesabının sonuçları var.',
                '',
                'Kurallar:',
                '1. Önce kullanıcının hedefini netleştir. Hedef yoksa ya da eksikse (görev; itki, yanma süresi ya da toplam itki hedefi; çap, kütle, bütçe, malzeme, imalat kısıtları) öneri vermeden önce kısa sorular sor.',
                '2. Her öneriyi gerekçesiyle ve beklenen etkisiyle ver: hangi sonuç sayısı hangi yöne, kabaca ne kadar değişir.',
                '3. HRMA\'nın modellemediği bir şeyi hesaplanmış gibi sunma, sayı uydurma; emin olmadığın yerde bunu açıkça söyle.',
                '4. HRMA\'nın kritik uyarılarını ve geri çekilmiş hükümlerini (withheld_verdicts, validity_limits) göz ardı etme; önerinin onları nasıl etkilediğini yaz.',
                '5. Bir seferde en çok ' + AZAMI_DEGISIKLIK + ' değişiklik öner. Yalnız "fields" listesindeki alan kimliklerini (id) kullan. Birimi o alanın "unit" değeriyle AYNI yaz: HRMA birim çevirmez, uyuşmayan satırı reddeder. Sayı alanına tırnaksız düz sayı, seçim alanına yalnız "options" listesindeki değeri, onay kutusuna true/false yaz.',
                '6. Değişiklik önerdiğinde cevabının sonuna tam olarak bu biçimde TEK bir blok koy. Kullanıcı bloğu HRMA\'ya yapıştıracak; HRMA önce/sonra tablosunu gösterip yalnız kullanıcının onayıyla uygulayacak:',
                '',
                blok,
                '',
                'Alanlar: "id" kimlik; "label" ekrandaki etiket; "value" şimdiki değer; "unit" birim; "source" değerin kaynağı (user = kullanıcı ya da proje dosyası, project_file = proje dosyasından, page_default = sayfanın hazır değeri, empty = boş: sunucu varsayılanı ya da türetilmiş değer kullanılır, not_sent_until_edited = kullanıcı düzenleyene kadar çözücüye gitmez); "server_default" boş alan için sunucunun beyan ettiği değer; "not_used" çözücünün bu alanı hesapta kullanmadığı beyanı ve nedeni; "range" koddaki kabul aralığı [alt, üst]; "active": false alan şu anki yapılandırmada ekranda değil.',
                'Sonuçlar: "headline" başlık sayıları (yanıtın kendi anahtarı ve birimiyle); "warnings" HRMA uyarıları (severity: critical / warning / info, code); "withheld_verdicts" geri çekilen hükümler ve nedenleri; "validity_limits" aşılan model geçerlilik sınırları; "cea_comparison" NASA CEA karşılaştırması (yalnız bilgi amaçlı).'
            ].join('\n');
        }
        return [
            'You are a propulsion-system preliminary design assistant. The user is designing a ' + ad + ' rocket motor with HRMA (a rocket motor preliminary design tool). Below are the user\'s design goal, the COMPLETE HRMA form and the results of HRMA\'s last calculation.',
            '',
            'Rules:',
            '1. First make the user\'s goal precise. If the goal is missing or incomplete (mission; thrust, burn time or total impulse target; diameter, mass, budget, material, manufacturing constraints), ask short questions before proposing anything.',
            '2. Give every proposal with its rationale and expected effect: which result number moves in which direction, roughly by how much.',
            '3. Do not present anything HRMA does not model as if it were computed and do not invent numbers; say so plainly where you are unsure.',
            '4. Do not ignore HRMA\'s critical warnings or withheld verdicts (withheld_verdicts, validity_limits); state how your proposal affects them.',
            '5. Propose at most ' + AZAMI_DEGISIKLIK + ' changes at a time. Use only field ids from the "fields" list. Write the unit EXACTLY as that field\'s "unit": HRMA converts no units and rejects a mismatching line. Numeric fields take a plain number (no quotes), menus take only a value from "options", checkboxes take true/false.',
            '6. When you propose changes, end your reply with exactly ONE block in this format. The user will paste it into HRMA; HRMA shows a before/after table and applies it only with the user\'s approval:',
            '',
            blok,
            '',
            'Fields: "id" identifier; "label" on-screen label; "value" current value; "unit" unit; "source" origin of the value (user = user or project file, project_file = from the project file, page_default = page preset, untouched, empty = blank: the server default or a derived value is used, not_sent_until_edited = not sent to the solver until the user edits it); "server_default" the value the server declares for a blank field; "not_used" the solver\'s declaration that this field did not enter the calculation, with the reason; "range" the accepted range in code [low, high]; "active": false means the field is not on screen in the current configuration.',
            'Results: "headline" headline numbers (with the response\'s own key and unit); "warnings" HRMA warnings (severity: critical / warning / info, code); "withheld_verdicts" withheld verdicts and their reasons; "validity_limits" exceeded model validity limits; "cea_comparison" NASA CEA comparison (advisory only).'
        ].join('\n');
    }

    // JSON'u okunur ama kısa basar: alan ve uyarı listeleri satır başına
    // bir kayıt (226 alan × 8 satır yerine 226 satır).
    function paketJson(nesne) {
        var satirli = { fields: 1, warnings: 1, headline: 1, withheld_verdicts: 1,
                        validity_limits: 1, rows: 1, changed_inputs: 1,
                        applied_suggestions: 1, headline_before_after: 1,
                        new_warnings: 1, resolved_warnings: 1 };
        function yaz(v, girinti) {
            var ic = girinti + '  ';
            if (Array.isArray(v)) {
                if (!v.length) return '[]';
                return '[\n' + v.map(function (x) { return ic + JSON.stringify(x); })
                    .join(',\n') + '\n' + girinti + ']';
            }
            if (v && typeof v === 'object') {
                var anahtarlar = Object.keys(v);
                if (!anahtarlar.length) return '{}';
                return '{\n' + anahtarlar.map(function (k) {
                    var deger = v[k];
                    var metin;
                    if (Array.isArray(deger) && satirli[k]) metin = yaz(deger, ic);
                    else if (deger && typeof deger === 'object' && !Array.isArray(deger)
                             && (k === 'results' || k === 'cea_comparison'
                                 || k === 'context')) metin = yaz(deger, ic);
                    else metin = JSON.stringify(deger);
                    return ic + JSON.stringify(k) + ': ' + metin;
                }).join(',\n') + '\n' + girinti + '}';
            }
            return JSON.stringify(v);
        }
        return yaz(nesne, '');
    }

    // ==================================================================
    // 5. PANO + YEDEK PENCERE (OH-GT-07 deseni KORUNUR)
    // ==================================================================
    // Pano reddedilirse (izin yok, odak yok, güvensiz bağlam) metin
    // KAYBOLMAZ: aynı metin salt-okunur bir pencerede açılır. Güvensiz
    // bağlamda navigator.clipboard UNDEFINED'dır ve .writeText SENKRON
    // fırlatır — söz burada kurulur ki .catch her durumda koşsun. Hata
    // konsola ADIYLA yazılır (DOMException "{}" diye basılmasın).

    function panoHataMetni(err) {
        if (!err) return 'unknown clipboard error';
        if (err.name || err.message) {
            return String(err.name || 'Error') + ': ' + String(err.message || '');
        }
        return String(err);
    }

    function panoyaYaz(metin) {
        var soz;
        try {
            var nav = root.navigator;
            soz = (nav && nav.clipboard && nav.clipboard.writeText)
                ? nav.clipboard.writeText(metin)
                : Promise.reject(new Error('clipboard API unavailable'));
        } catch (err) {
            soz = Promise.reject(err);
        }
        return soz;
    }

    /** Metni salt-okunur pencerede gösterir. Metin textarea.value ile
     *  yerleşir — HTML olarak YORUMLANMAZ. */
    function metinPenceresi(doc, baslik, giris, metin) {
        var eski = doc.getElementById(MODAL_ID);
        if (eski && eski.parentNode) eski.parentNode.removeChild(eski);
        var perde = doc.createElement('div');
        perde.id = MODAL_ID;
        perde.className = 'hrma-ai-modal';
        perde.setAttribute('role', 'dialog');
        perde.setAttribute('aria-modal', 'true');
        var kutu = doc.createElement('div');
        kutu.className = 'hrma-ai-modal-box';
        var bas = doc.createElement('div');
        bas.className = 'hrma-ai-modal-head';
        var h = doc.createElement('h2');
        h.className = 'hrma-ai-modal-title';
        h.id = MODAL_ID + 'Title';
        h.textContent = baslik;
        perde.setAttribute('aria-labelledby', h.id);
        var kapat = doc.createElement('button');
        kapat.type = 'button';
        kapat.className = 'hrma-ai-btn hrma-ai-btn-ghost';
        kapat.textContent = T('common.close', 'Close');
        bas.appendChild(h);
        bas.appendChild(kapat);
        var p = doc.createElement('p');
        p.className = 'hrma-ai-modal-intro';
        p.textContent = giris;
        var ta = doc.createElement('textarea');
        ta.className = 'hrma-ai-modal-text';
        ta.readOnly = true;
        ta.spellcheck = false;
        ta.setAttribute('aria-label', baslik);
        // v3.0.1 N-girdi-2: salt okunur metin alanının açıklaması (giriş
        // paragrafıyla aynı cümle) alanın kendisinde de durur.
        ta.setAttribute('title', giris);
        ta.value = metin;
        var alt = doc.createElement('div');
        alt.className = 'hrma-ai-row';
        var sec = doc.createElement('button');
        sec.type = 'button';
        sec.className = 'hrma-ai-btn';
        sec.textContent = T('ai.modal.select', 'Select all');
        sec.addEventListener('click', function () { ta.focus(); ta.select(); });
        alt.appendChild(sec);
        kutu.appendChild(bas);
        kutu.appendChild(p);
        kutu.appendChild(ta);
        kutu.appendChild(alt);
        perde.appendChild(kutu);
        function kapa() {
            doc.removeEventListener('keydown', esc);
            if (perde.parentNode) perde.parentNode.removeChild(perde);
        }
        function esc(e) { if (e.key === 'Escape') kapa(); }
        kapat.addEventListener('click', kapa);
        perde.addEventListener('click', function (e) { if (e.target === perde) kapa(); });
        doc.addEventListener('keydown', esc);
        doc.body.appendChild(perde);
        try { ta.focus(); ta.select(); } catch (e) { /* odak yok */ }
        return perde;
    }

    // ==================================================================
    // 6. PANEL
    // ==================================================================

    function el(doc, tag, sinif, metin) {
        var d = doc.createElement(tag);
        if (sinif) d.className = sinif;
        if (metin !== undefined && metin !== null) d.textContent = metin;
        return d;
    }
    // data-i18n taşıyan düğüm: dil değişince I18N.apply yeniden çevirir.
    // Metin çağrı yerinde T('anahtar', yedek) ile kurulur — sözlük bekçisi
    // (tests/test_i18n_common.py) anahtarı yalnız T(' biçiminde görür.
    function i18nEl(doc, tag, sinif, anahtar, metin) {
        var d = el(doc, tag, sinif, metin);
        d.setAttribute('data-i18n', anahtar);
        return d;
    }
    function ipucu(doc, anahtar, metin) {
        var t = el(doc, 'div', 'tooltip');
        var i = el(doc, 'div', 'tooltip-icon', '?');
        var s = i18nEl(doc, 'span', 'tooltip-text', anahtar, metin);
        t.appendChild(i);
        t.appendChild(s);
        return t;
    }

    function Panel(doc, kap) {
        this.doc = doc;
        this.kap = kap;
        this.tip = kap.getAttribute('data-motor-type');
        this.adaptor = ADAPTORLER[this.tip];
        this.surum = kap.getAttribute('data-hrma-version') || root.HRMA_VERSION || null;
        this.taban = null;          // son kopyalamadaki durum (devam paketi)
        this.uygulananlar = [];     // son kopyalamadan beri uygulanan öneriler
        this.sonOnizleme = null;
        this.sonucKimligi = null;   // izlenen window.currentResults
        this.hesapGirdileri = null; // sonuç geldiğinde formun değerleri
        this.sonMetin = '';
    }

    Panel.prototype.kur = function () {
        var doc = this.doc, self = this;
        var kap = this.kap;
        kap.classList.add('hrma-ai');
        kap.setAttribute('aria-labelledby', 'hrmaAiTitle');

        var ac = el(doc, 'button', 'hrma-ai-toggle');
        ac.type = 'button';
        ac.id = 'hrmaAiToggle';
        ac.setAttribute('aria-expanded', 'false');
        ac.setAttribute('aria-controls', 'hrmaAiBody');
        var ikon = el(doc, 'span', 'hrma-ai-icon', '\u2726');
        ikon.setAttribute('aria-hidden', 'true');
        var baslik = i18nEl(doc, 'span', 'hrma-ai-title', 'ai.panel.title', T('ai.panel.title', 'Design with AI'));
        baslik.id = 'hrmaAiTitle';
        var alt = i18nEl(doc, 'span', 'hrma-ai-sub', 'ai.panel.sub', T('ai.panel.sub', 'Works with any assistant you already use; HRMA itself sends nothing over the network'));
        var ok = el(doc, 'span', 'hrma-ai-caret', '\u25BE');
        ok.setAttribute('aria-hidden', 'true');
        ac.appendChild(ikon);
        var yazi = el(doc, 'span', 'hrma-ai-toggle-text');
        yazi.appendChild(baslik);
        yazi.appendChild(alt);
        ac.appendChild(yazi);
        ac.appendChild(ok);
        kap.appendChild(ac);

        var govde = el(doc, 'div', 'hrma-ai-body');
        govde.id = 'hrmaAiBody';
        govde.hidden = true;
        govde.appendChild(i18nEl(doc, 'p', 'hrma-ai-intro', 'ai.panel.intro', T('ai.panel.intro', 'Write your goal, copy the full design context to your own AI assistant, paste its suggestion back, check the before/after table and apply it. Nothing on the form changes without your approval.')));

        var liste = el(doc, 'ol', 'hrma-ai-steps');

        // ---- Adım 1: tasarım hedefi
        var a1 = this.adim(1, 'ai.step1.title', T('ai.step1.title', 'Describe your design goal'));
        var hedefBas = el(doc, 'div', 'hrma-ai-field-head');
        var lab = i18nEl(doc, 'label', 'hrma-ai-label', 'ai.goal.label', T('ai.goal.label', 'My design goal'));
        lab.setAttribute('for', HEDEF_ID);
        hedefBas.appendChild(lab);
        hedefBas.appendChild(ipucu(doc, 'ai.goal.tip', T('ai.goal.tip', 'Free text, no unit, at most 2000 characters: the mission, the thrust, burn-time or total-impulse target and the constraints (diameter, mass, budget, material, manufacturing). It changes no calculation: it only goes into the context package and is saved with the project. Left blank, the package says that no goal was given and the assistant is told to ask for it first. There is no code-defined range.')));
        var hedef = el(doc, 'textarea', 'hrma-ai-goal');
        hedef.id = HEDEF_ID;
        hedef.rows = 3;
        hedef.maxLength = AZAMI_HEDEF;
        hedef.placeholder = T('ai.goal.placeholder',
            'e.g. 5 kN for 8 s, outer diameter at most 120 mm, aluminium case, lathe-only manufacturing');
        hedef.setAttribute('data-i18n-placeholder', 'ai.goal.placeholder');
        a1.icerik.appendChild(hedefBas);
        a1.icerik.appendChild(hedef);
        liste.appendChild(a1.li);

        // ---- Adım 2: bağlamı kopyala
        var a2 = this.adim(2, 'ai.step2.title', T('ai.step2.title', 'Copy the context to your assistant'));
        a2.icerik.appendChild(i18nEl(doc, 'p', 'hrma-ai-hint', 'ai.step2.hint', T('ai.step2.hint', 'The package carries every form field (value, unit, source, whether the solver used it, accepted range), the results, warnings, withheld verdicts and the NASA CEA comparison, written in the interface language.')));
        var s2 = el(doc, 'div', 'hrma-ai-row');
        var kopyala = i18nEl(doc, 'button', 'hrma-ai-btn hrma-ai-btn-primary', 'ai.btn.copy', T('ai.btn.copy', 'Copy context'));
        kopyala.type = 'button';
        kopyala.setAttribute('data-ai-act', 'copy');
        var goster = i18nEl(doc, 'button', 'hrma-ai-btn hrma-ai-btn-ghost', 'ai.btn.show', T('ai.btn.show', 'Show text'));
        goster.type = 'button';
        goster.setAttribute('data-ai-act', 'show');
        goster.disabled = true;
        s2.appendChild(kopyala);
        s2.appendChild(goster);
        a2.icerik.appendChild(s2);
        liste.appendChild(a2.li);

        // ---- Adım 3: öneriyi yapıştır
        var a3 = this.adim(3, 'ai.step3.title', T('ai.step3.title', "Paste the assistant's suggestion"));
        var yBas = el(doc, 'div', 'hrma-ai-field-head');
        var yLab = i18nEl(doc, 'span', 'hrma-ai-label', 'ai.paste.label', T('ai.paste.label', "Assistant's reply"));
        yLab.id = 'hrmaAiPasteLabel';
        yBas.appendChild(yLab);
        yBas.appendChild(ipucu(doc, 'ai.paste.tip', T('ai.paste.tip', "Text, no unit, at most 100000 characters: the assistant's whole reply or only its hrma-oneri block. Pasting changes nothing: HRMA reads only the block, accepts at most 8 changes to fields of this page and shows a before/after table; the form changes only when you press Apply. Left blank, Check says there is nothing to read. The pasted text is not saved with the project.")));
        // id YOK: proje kaydı (project_bar.js) id'li alanları yazar; güvenilmez
        // yapıştırma metni proje dosyasına girmez.
        var yap = el(doc, 'textarea', 'hrma-ai-paste');
        yap.rows = 5;
        yap.setAttribute('aria-labelledby', 'hrmaAiPasteLabel');
        yap.setAttribute('maxlength', String(AZAMI_YAPISTIRMA));
        yap.spellcheck = false;   // JSON bloğu yazım denetimiyle kırmızıya boyanmasın
        yap.placeholder = T('ai.paste.placeholder', 'Paste the whole reply or only the ```hrma-oneri block');
        yap.setAttribute('data-i18n-placeholder', 'ai.paste.placeholder');
        var s3 = el(doc, 'div', 'hrma-ai-row');
        var denetle = i18nEl(doc, 'button', 'hrma-ai-btn', 'ai.btn.check', T('ai.btn.check', 'Check suggestion'));
        denetle.type = 'button';
        denetle.setAttribute('data-ai-act', 'check');
        s3.appendChild(denetle);
        var onizleme = el(doc, 'div', 'hrma-ai-preview');
        onizleme.setAttribute('aria-live', 'polite');
        a3.icerik.appendChild(yBas);
        a3.icerik.appendChild(yap);
        a3.icerik.appendChild(s3);
        a3.icerik.appendChild(onizleme);
        liste.appendChild(a3.li);

        // ---- Adım 4: devam paketi
        var a4 = this.adim(4, 'ai.step4.title', T('ai.step4.title', 'Continue the conversation'));
        a4.icerik.appendChild(i18nEl(doc, 'p', 'hrma-ai-hint', 'ai.step4.hint', T('ai.step4.hint', 'After calculating, copy what changed since the last copy (inputs, applied suggestion, headline numbers before/after, new and resolved warnings) back into the same conversation.')));
        var s4 = el(doc, 'div', 'hrma-ai-row');
        var devam = i18nEl(doc, 'button', 'hrma-ai-btn', 'ai.btn.continue', T('ai.btn.continue', 'Copy continuation package'));
        devam.type = 'button';
        devam.setAttribute('data-ai-act', 'continue');
        s4.appendChild(devam);
        a4.icerik.appendChild(s4);
        liste.appendChild(a4.li);

        govde.appendChild(liste);
        var durum = el(doc, 'p', 'hrma-ai-status');
        durum.setAttribute('role', 'status');
        durum.setAttribute('aria-live', 'polite');
        govde.appendChild(durum);
        kap.appendChild(govde);

        this.ac = ac; this.govde = govde; this.hedef = hedef; this.yap = yap;
        this.onizleme = onizleme; this.durum = durum; this.gosterDugmesi = goster;

        ac.addEventListener('click', function () { self.acKapa(); });
        kopyala.addEventListener('click', function () { self.kopyala(); });
        goster.addEventListener('click', function () { self.goster(); });
        denetle.addEventListener('click', function () { self.denetle(); });
        devam.addEventListener('click', function () { self.devam(); });
        // Sonuç kimliği izlenir: yeni hesap gelince o anki form değerleri
        // "bu sonuçların girdileri" olarak saklanır (bayat sonuç uyarısı).
        root.setInterval(function () { self.izle(); }, IZLEME_MS);
    };

    Panel.prototype.adim = function (n, anahtar, metin) {
        var doc = this.doc;
        var li = el(doc, 'li', 'hrma-ai-step');
        var bas = el(doc, 'div', 'hrma-ai-step-head');
        var num = el(doc, 'span', 'hrma-ai-num', String(n));
        num.setAttribute('aria-hidden', 'true');
        bas.appendChild(num);
        bas.appendChild(i18nEl(doc, 'span', 'hrma-ai-step-title', anahtar, metin));
        var icerik = el(doc, 'div', 'hrma-ai-step-body');
        li.appendChild(bas);
        li.appendChild(icerik);
        return { li: li, icerik: icerik };
    };

    Panel.prototype.acKapa = function (zorla) {
        var acik = (zorla === undefined) ? this.govde.hidden : !!zorla;
        this.govde.hidden = !acik;
        this.ac.setAttribute('aria-expanded', acik ? 'true' : 'false');
        this.kap.classList.toggle('hrma-ai-open', acik);
    };

    Panel.prototype.bildir = function (metin, tur) {
        this.durum.textContent = metin;
        this.durum.setAttribute('data-kind', tur || 'info');
    };

    Panel.prototype.sonuclar = function () {
        var r = root.currentResults;
        return (r && typeof r === 'object') ? r : null;
    };

    Panel.prototype.formDegerleri = function () {
        var out = Object.create(null);
        formAlanIdleri(this.doc).forEach(function (e) {
            out[e.id] = alanDegeri(e, alanTipi(e));
        });
        return out;
    };

    Panel.prototype.izle = function () {
        var r = this.sonuclar();
        if (r && r !== this.sonucKimligi) {
            this.sonucKimligi = r;
            this.hesapGirdileri = this.formDegerleri();
        }
    };

    Panel.prototype.projeAdi = function () {
        try {
            var st = root.HRMAProjectBar && root.HRMAProjectBar._state;
            if (st) return st.savedName || st.name || null;
        } catch (e) { /* yok */ }
        return null;
    };

    Panel.prototype.sonucDurumu = function (r, degerler) {
        if (!r) return 'not_calculated';
        this.izle();
        var g = this.hesapGirdileri;
        if (!g) return 'calculated';
        var ids = Object.keys(degerler);
        for (var i = 0; i < ids.length; i++) {
            if (String(degerler[ids[i]]) !== String(g[ids[i]])) return 'stale';
        }
        return 'calculated';
    };

    /** Bağlam paketi (nesne) — testler ve Playwright de bunu okur. */
    Panel.prototype.baglam = function () {
        var r = this.sonuclar();
        var a = alanlariTopla(this.doc, r);
        var degerler = Object.create(null);
        a.kayitlar.forEach(function (k) { degerler[k.id] = k.value; });
        var hedef = String(this.hedef.value || '').trim();
        var lang = dil();
        var paket = {
            hrma_context: SEMA_SURUMU,
            hrma_version: this.surum,
            motor_type: this.tip,
            project: this.projeAdi(),
            date: new Date().toISOString(),
            language: lang,
            design_goal: hedef || null,
            results_state: this.sonucDurumu(r, degerler),
            fields_count: a.kayitlar.length,
            fields: a.kayitlar,
            results: sonucBolumu(this.adaptor, r)
        };
        return { paket: paket, tanimlar: a.tanimlar, degerler: degerler, lang: lang };
    };

    Panel.prototype.metniKur = function (b) {
        var lang = b.lang;
        var parcalar = [istemMetni(lang, this.tip), ''];
        if (!b.paket.design_goal) {
            parcalar.push(lang === 'tr'
                ? 'NOT: Kullanıcı tasarım hedefini yazmadı. Önce hedefi sor.'
                : 'NOTE: The user has not written a design goal. Ask for it first.');
            parcalar.push('');
        }
        if (b.paket.results_state === 'stale') {
            parcalar.push(lang === 'tr'
                ? 'NOT: Girdiler son hesaptan sonra değişti; "results" bir önceki girdilerin sonucudur.'
                : 'NOTE: Inputs changed after the last calculation; "results" belong to the previous inputs.');
            parcalar.push('');
        } else if (b.paket.results_state === 'not_calculated') {
            parcalar.push(lang === 'tr'
                ? 'NOT: Henüz hesap yapılmadı; "results" boş.'
                : 'NOTE: No calculation has been run yet; "results" is empty.');
            parcalar.push('');
        }
        parcalar.push(lang === 'tr' ? '[HRMA BAĞLAMI]' : '[HRMA CONTEXT]');
        parcalar.push(paketJson(b.paket));
        return parcalar.join('\n');
    };

    Panel.prototype.metniVer = function (metin, basariMetni) {
        var self = this;
        this.sonMetin = metin;
        this.gosterDugmesi.disabled = false;
        return panoyaYaz(metin).then(function () {
            self.bildir(basariMetni, 'ok');
            return true;
        }).catch(function (err) {
            var ad = panoHataMetni(err);
            if (root.console && root.console.warn) root.console.warn('HRMA AI clipboard:', ad);
            var uyari = TF('ai.msg.copyFailed', { err: ad },
                'Could not copy to the clipboard ({err}). Copy the text from the window.');
            self.bildir(uyari, 'warn');
            metinPenceresi(self.doc, T('ai.modal.title', 'Text for your AI assistant'),
                           uyari, metin);
            return false;
        });
    };

    Panel.prototype.kopyala = function () {
        var b = this.baglam();
        var metin = this.metniKur(b);
        var r = b.paket.results;
        this.taban = {
            degerler: b.degerler,
            tanimlar: b.tanimlar,
            baslik: r ? r.headline : [],
            uyarilar: r ? r.warnings : [],
            sonuc: this.sonuclar()
        };
        this.uygulananlar = [];
        return this.metniVer(metin, TF('ai.msg.copied',
            { fields: b.paket.fields_count, kb: Math.max(1, Math.round(metin.length / 1024)) },
            'Copied: {fields} form fields, {kb} KB. Paste it into your assistant.'));
    };

    Panel.prototype.goster = function () {
        if (!this.sonMetin) return;
        metinPenceresi(this.doc, T('ai.modal.title', 'Text for your AI assistant'),
            T('ai.modal.intro', 'Select all and copy this text into your assistant.'),
            this.sonMetin);
    };

    // ---- Adım 3: denetle → önce/sonra tablosu
    Panel.prototype.denetle = function () {
        var doc = this.doc;
        var tanim = alanlariTopla(doc, this.sonuclar()).tanimlar;
        var s = oneriDogrula(String(this.yap.value || ''), this.tip, tanim);
        var kutu = this.onizleme;
        while (kutu.firstChild) kutu.removeChild(kutu.firstChild);
        this.sonOnizleme = null;
        if (!s.ok) {
            var hata = el(doc, 'p', 'hrma-ai-error', retMetni(s.kod, s.params));
            hata.setAttribute('data-ai-error', s.kod);
            kutu.appendChild(hata);
            this.bildir(retMetni(s.kod, s.params), 'warn');
            return s;
        }
        this.sonOnizleme = s;
        var self = this;
        if (s.gecerli.length) {
            var sarmal = el(doc, 'div', 'hrma-ai-table-wrap');
            var tablo = el(doc, 'table', 'hrma-ai-table');
            var thead = el(doc, 'thead');
            var tr = el(doc, 'tr');
            [['ai.table.use', T('ai.table.use', 'Apply')],
             ['ai.table.field', T('ai.table.field', 'Field')],
             ['ai.table.label', T('ai.table.label', 'Label')],
             ['ai.table.current', T('ai.table.current', 'Current')],
             ['ai.table.proposed', T('ai.table.proposed', 'Proposed')],
             ['ai.table.unit', T('ai.table.unit', 'Unit')],
             ['ai.table.reason', T('ai.table.reason', 'Reason')]].forEach(function (k) {
                tr.appendChild(i18nEl(doc, 'th', null, k[0], k[1]));
            });
            thead.appendChild(tr);
            tablo.appendChild(thead);
            var tbody = el(doc, 'tbody');
            s.gecerli.forEach(function (g) {
                var satir = el(doc, 'tr');
                satir.setAttribute('data-ai-field', g.alan);
                var c0 = el(doc, 'td');
                var cb = el(doc, 'input');
                cb.type = 'checkbox';
                cb.checked = true;
                cb.className = 'hrma-ai-use';
                cb.setAttribute('aria-label', TF('ai.table.useField', { field: g.alan },
                    'Apply the change to {field}'));
                c0.appendChild(cb);
                satir.appendChild(c0);
                satir.appendChild(el(doc, 'td', 'hrma-ai-mono', g.alan));
                var etiketHucre = el(doc, 'td', null, g.etiket || '');
                if (!g.aktif) {
                    etiketHucre.appendChild(el(doc, 'span', 'hrma-ai-note',
                        ' ' + T('ai.note.inactive', '(not on screen in the current configuration)')));
                }
                satir.appendChild(etiketHucre);
                satir.appendChild(el(doc, 'td', 'hrma-ai-mono', degerYazi(g.simdiki)));
                satir.appendChild(el(doc, 'td', 'hrma-ai-mono hrma-ai-new', degerYazi(g.onerilen)));
                satir.appendChild(el(doc, 'td', null, g.birim || ''));
                // GEREKÇE GÜVENİLMEZ METİNDİR: textContent ile basılır.
                satir.appendChild(el(doc, 'td', 'hrma-ai-reason', g.gerekce || ''));
                tbody.appendChild(satir);
            });
            tablo.appendChild(tbody);
            sarmal.appendChild(tablo);
            kutu.appendChild(sarmal);
            var dugmeler = el(doc, 'div', 'hrma-ai-row');
            var uygula = i18nEl(doc, 'button', 'hrma-ai-btn', 'ai.btn.apply', T('ai.btn.apply', 'Apply'));
            uygula.type = 'button';
            uygula.setAttribute('data-ai-act', 'apply');
            var uyHesap = i18nEl(doc, 'button', 'hrma-ai-btn hrma-ai-btn-primary',
                'ai.btn.applyCalc', T('ai.btn.applyCalc', 'Apply and calculate'));
            uyHesap.type = 'button';
            uyHesap.setAttribute('data-ai-act', 'apply-calc');
            var vazgec = i18nEl(doc, 'button', 'hrma-ai-btn hrma-ai-btn-ghost', 'ai.btn.cancel', T('ai.btn.cancel', 'Discard'));
            vazgec.type = 'button';
            vazgec.setAttribute('data-ai-act', 'discard');
            uygula.addEventListener('click', function () { self.uygula(false); });
            uyHesap.addEventListener('click', function () { self.uygula(true); });
            vazgec.addEventListener('click', function () {
                while (kutu.firstChild) kutu.removeChild(kutu.firstChild);
                self.sonOnizleme = null;
            });
            dugmeler.appendChild(uygula);
            dugmeler.appendChild(uyHesap);
            dugmeler.appendChild(vazgec);
            kutu.appendChild(dugmeler);
        }
        if (s.reddedilen.length) {
            kutu.appendChild(el(doc, 'p', 'hrma-ai-rejected-title',
                TF('ai.rejected.title', { n: s.reddedilen.length }, 'Rejected lines ({n})')));
            var ul = el(doc, 'ul', 'hrma-ai-rejected');
            s.reddedilen.forEach(function (rd) {
                var li = el(doc, 'li', null);
                li.setAttribute('data-ai-reject', rd.kod);
                li.appendChild(el(doc, 'span', 'hrma-ai-mono',
                    (rd.alan === null ? ('#' + rd.sira) : rd.alan)));
                li.appendChild(el(doc, 'span', null, ' — ' + retMetni(rd.kod, rd.params)));
                ul.appendChild(li);
            });
            kutu.appendChild(ul);
        }
        this.bildir(TF('ai.msg.valid', { ok: s.gecerli.length, bad: s.reddedilen.length },
            '{ok} change(s) can be applied, {bad} rejected.'),
            s.gecerli.length ? 'ok' : 'warn');
        return s;
    };

    function degerYazi(v) {
        if (v === '' || v === null || v === undefined) return '—';
        if (typeof v === 'number') {
            var I = root.I18N;
            return (I && I.number) ? I.number(v) : String(v);
        }
        return String(v);
    }

    // ---- Uygula: YALNIZ işaretli satırlar, uygulamadan hemen önce
    // güncel forma karşı YENİDEN doğrulanır (önizlemeden sonra değişmiş olabilir).
    Panel.prototype.uygula = function (hesapla) {
        var s = this.sonOnizleme;
        if (!s) return 0;
        var doc = this.doc, self = this;
        var secili = Object.create(null);
        var kutular = this.onizleme.querySelectorAll('tr[data-ai-field]');
        for (var i = 0; i < kutular.length; i++) {
            var cb = kutular[i].querySelector('input.hrma-ai-use');
            if (cb && cb.checked) secili[kutular[i].getAttribute('data-ai-field')] = true;
        }
        var tanim = alanlariTopla(doc, this.sonuclar()).tanimlar;
        var n = 0;
        s.gecerli.forEach(function (g) {
            if (!secili[g.alan]) return;
            var t = tanim[g.alan];
            if (!t) return;
            var tekrar = satirDogrula({ alan: g.alan, deger: g.onerilen, birim: g.birim || undefined }, t);
            if (!tekrar.ok) return;
            var e = doc.getElementById(g.alan);
            if (!e) return;
            var once = alanDegeri(e, t.type);
            if (t.type === 'checkbox') e.checked = !!tekrar.deger;
            else e.value = String(tekrar.deger);
            try {
                e.dispatchEvent(new root.Event('input', { bubbles: true }));
                e.dispatchEvent(new root.Event('change', { bubbles: true }));
            } catch (err) { /* eski tarayıcı */ }
            self.uygulananlar.push({ id: g.alan, label: g.etiket, from: once,
                                     to: tekrar.deger, unit: g.birim || null,
                                     reason: g.gerekce || null });
            n += 1;
        });
        if (!n) {
            this.bildir(T('ai.msg.nothingSelected', 'No line selected.'), 'warn');
            return 0;
        }
        while (this.onizleme.firstChild) this.onizleme.removeChild(this.onizleme.firstChild);
        this.sonOnizleme = null;
        if (!hesapla) {
            this.bildir(TF('ai.msg.applied', { n: n },
                '{n} field(s) changed. Press Calculate to see the effect.'), 'ok');
            return n;
        }
        this.bildir(TF('ai.msg.appliedCalc', { n: n }, '{n} field(s) changed; calculating…'), 'ok');
        var fn = root[this.adaptor.hesapIslevi];
        if (typeof fn !== 'function') return n;
        var oncekiSonuc = this.sonuclar();
        var sonuc;
        try { sonuc = fn(); } catch (err) { sonuc = null; }
        Promise.resolve(sonuc).then(function () {
            if (self.sonuclar() && self.sonuclar() !== oncekiSonuc) {
                self.izle();
                self.bildir(T('ai.msg.calcDone',
                    'Calculation finished. Copy the continuation package to tell your assistant what changed.'), 'ok');
            }
        });
        return n;
    };

    // ---- Adım 4: devam paketi
    Panel.prototype.devam = function () {
        if (!this.taban) {
            this.bildir(T('ai.msg.noBaseline',
                'Copy the context first; the continuation package reports what changed since that copy.'), 'warn');
            return Promise.resolve(false);
        }
        var b = this.baglam();
        var lang = b.lang;
        var t = this.taban;
        var degisen = [];
        Object.keys(b.degerler).forEach(function (id) {
            var once = t.degerler[id];
            var simdi = b.degerler[id];
            if (String(once) !== String(simdi)) {
                var tn = b.tanimlar[id] || {};
                var k = { id: id, label: tn.label || '', from: once === undefined ? null : once, to: simdi };
                if (tn.unit) k.unit = tn.unit;
                degisen.push(k);
            }
        });
        var r = b.paket.results;
        var onceBaslik = Object.create(null);
        (t.baslik || []).forEach(function (h) { onceBaslik[h.key] = h; });
        var baslikKiyas = [];
        (r ? r.headline : []).forEach(function (h) {
            var o = onceBaslik[h.key];
            var k = { key: h.key, before: o ? o.value : null, after: h.value };
            if (h.unit) k.unit = h.unit;
            if (o && sonluSayi(o.value) && sonluSayi(h.value) && o.value !== 0) {
                k.delta_pct = yuvarla((h.value - o.value) / Math.abs(o.value) * 100);
            }
            baslikKiyas.push(k);
        });
        function anahtar(w) { return (w.code || '') + '|' + w.text; }
        var onceU = Object.create(null), simdiU = Object.create(null);
        (t.uyarilar || []).forEach(function (w) { onceU[anahtar(w)] = true; });
        var yeni = [], kapanan = [];
        (r ? r.warnings : []).forEach(function (w) {
            simdiU[anahtar(w)] = true;
            if (!onceU[anahtar(w)]) yeni.push(w);
        });
        (t.uyarilar || []).forEach(function (w) { if (!simdiU[anahtar(w)]) kapanan.push(w); });
        var paket = {
            hrma_continuation: SEMA_SURUMU,
            motor_type: this.tip,
            date: new Date().toISOString(),
            results_state: b.paket.results_state,
            recalculated_since_last_copy: !!(this.sonuclar() && this.sonuclar() !== t.sonuc),
            changed_inputs: degisen,
            applied_suggestions: this.uygulananlar.slice(),
            headline_before_after: baslikKiyas,
            new_warnings: yeni,
            resolved_warnings: kapanan,
            withheld_verdicts_now: r ? r.withheld_verdicts.length : 0,
            validity_limits_now: r ? r.validity_limits.length : 0
        };
        var talimat = (lang === 'tr')
            ? ['Aynı tasarıma devam ediyoruz. Son paylaştığım HRMA bağlamından bu yana değişenler aşağıda: değişen girdiler, uygulanan öneriler, başlık sayılarının önce/sonra değerleri, yeni ve kapanan uyarılar.',
               'Etkiyi beklediğinle karşılaştır, kritik uyarı ve geri çekilmiş hükümleri dikkate al; gerekirse bir sonraki adımı aynı ```' + BLOK_ETIKETI + ' biçimiyle (en çok ' + AZAMI_DEGISIKLIK + ' değişiklik, alanların birimiyle) öner.']
            : ['We are continuing the same design. Below is what changed since the HRMA context I last shared: changed inputs, applied suggestions, headline numbers before/after, new and resolved warnings.',
               'Compare the effect with what you expected, take critical warnings and withheld verdicts into account and, if needed, propose the next step in the same ```' + BLOK_ETIKETI + ' format (at most ' + AZAMI_DEGISIKLIK + ' changes, with the fields\' units).'];
        if (paket.results_state === 'stale' || !paket.recalculated_since_last_copy) {
            talimat.push(lang === 'tr'
                ? 'NOT: Bu paketteki sonuçlar şimdiki girdilerle hesaplanmadı (önce Hesapla\'ya basılmalı).'
                : 'NOTE: The results in this package were not calculated with the current inputs (Calculate must be pressed first).');
        }
        var metin = talimat.join('\n') + '\n\n'
            + (lang === 'tr' ? '[HRMA DEVAM]' : '[HRMA CONTINUATION]') + '\n' + paketJson(paket);
        // Yeni taban: bir sonraki devam paketi buradan ölçülür.
        this.taban = { degerler: b.degerler, tanimlar: b.tanimlar,
                       baslik: r ? r.headline : [], uyarilar: r ? r.warnings : [],
                       sonuc: this.sonuclar() };
        this.uygulananlar = [];
        return this.metniVer(metin, TF('ai.msg.contCopied', { n: degisen.length },
            'Continuation package copied: {n} changed input(s).'));
    };

    // ==================================================================
    // 7. KURULUM + DIŞ API
    // ==================================================================
    var etkin = null;

    function kur() {
        var doc = root.document;
        if (!doc) return null;
        var kap = doc.getElementById(PANEL_ID);
        if (!kap || kap.getAttribute('data-ai-ready') === '1') return etkin;
        var tip = kap.getAttribute('data-motor-type');
        if (!ADAPTORLER[tip]) return null;
        kap.setAttribute('data-ai-ready', '1');
        etkin = new Panel(doc, kap);
        etkin.kur();
        return etkin;
    }

    var HRMAAI = {
        SEMA_SURUMU: SEMA_SURUMU,
        BLOK_ETIKETI: BLOK_ETIKETI,
        AZAMI_DEGISIKLIK: AZAMI_DEGISIKLIK,
        AZAMI_YAPISTIRMA: AZAMI_YAPISTIRMA,
        ADAPTORLER: ADAPTORLER,
        kur: kur,
        panel: function () { return etkin; },
        // Saf yardımcılar (node bekçileri ve Playwright kanıtı okur)
        blokAyikla: blokAyikla,
        oneriDogrula: oneriDogrula,
        satirDogrula: satirDogrula,
        retMetni: retMetni,
        RET_KODLARI: RET_KODLARI,
        birimNormal: birimNormal,
        birimMi: birimMi,
        istemMetni: istemMetni,
        paketJson: paketJson,
        sonucBolumu: sonucBolumu,
        hukumleriTopla: hukumleriTopla,
        uyariKaydi: uyariKaydi,
        panoHataMetni: panoHataMetni,
        panoyaYaz: panoyaYaz,
        metinPenceresi: metinPenceresi,
        // Bekçi kancası: pano dalı node altında GERÇEK gövdeyle koşturulur.
        _Panel: Panel
    };
    root.HRMAAI = HRMAAI;
    if (typeof module !== 'undefined' && module.exports) module.exports = HRMAAI;

    if (root.document && root.document.addEventListener) {
        if (root.document.readyState === 'loading') {
            root.document.addEventListener('DOMContentLoaded', kur);
        } else {
            kur();
        }
    }
})(typeof window !== 'undefined' ? window : globalThis);
