/* ====================================================================
   HRMA OpenRocket köşesi: openrocket_kose.js
   --------------------------------------------------------------------
   Berke, karar §28-11 (5 Eki 2026) ve 7 Eki 2026: motor sayfalarının
   (sıvı, katı, hibrit) sağ kenarında küçük bir "OpenRocket" sekmesi;
   tıklanınca sayfadaki OpenRocket yeteneklerini tek panelde toplar.
   Ana iş değildir, "bunu da destekliyoruz" demektir.

   İŞLETME KURALLARI (§28-11):
     * Yalnız ÇALIŞAN ve TESTLİ yetenek listelenir. Bu dosya yeni bir
       yetenek UYDURMAZ: dışa aktarım düğmesi sayfanın KENDİ düğmesine
       vekâlet eder (aynı işlev, aynı uç, aynı ret gerekçesi), .ork
       içe aktarma kutusu 6-DOF panelinden OLDUĞU GİBİ taşınır (aynı
       kimlikler, aynı olay dinleyicileri).
     * Fail-closed: hesaplanmış motor yoksa dışa aktarım gri olur ve
       nedeni yazılır. Hedef düğüm sayfada yoksa ilgili eylem gri olur.
     * Uyumluluk cümlesi yalnız ÖLÇÜLMÜŞ olanı söyler (OLCUM nesnesi;
       ölçümün kendisi tests/test_ui_openrocket_kose.py içinde kurulu
       OpenRocket varken yeniden koşar ve bu sabitlerle karşılaştırılır).
     * Panel kaldırılmaz. Dağınık düğmeler yalnız köşe kurulduktan SONRA
       gizlenir (gövde sınıfı 'or-kose-hazir'); köşe kurulamazsa hiçbir
       şey gizlenmez, düğmeler eski yerlerinde çalışmaya devam eder.

   Uç eşlemesi (hrma/app.py ve hrma/importers/api.py, değiştirilmedi):
     sıvı / katı   .eng   POST /api/export-eng
     hibrit        .eng   POST /api/export-openrocket
     .ork içe aktarma     POST /api/import/ork          (sixdof_panel.js)
     .eng/.rse içe akt.   POST /api/import/motor-file   (sixdof_panel.js,
                                                        validation_panel.js)
   ==================================================================== */

(function (global) {
    'use strict';

    // Ürün adı; çeviri metni değildir (iki dilde de aynı yazılır).
    var MARKA = 'OpenRocket';

    // Ölçülen uyumluluk (7 Ekim 2026, /Applications/OpenRocket.app 24.12,
    // ayrıntı: docs/scofield/raw/OH/UI/openrocket-kose/rapor.md).
    //   eng: üç sayfanın dışa aktardığı .eng dosyaları OpenRocket 24.12'nin
    //        kendi RASP yükleyicisiyle (info.openrocket.core.file.motor.
    //        RASPMotorLoader, başsız) okundu.
    //   ork: OpenRocket 24.12 ile gelen örnek tasarımlardan okunan / toplam.
    var OLCUM = {
        openrocket_surum: '24.12',
        eng_okundu: true,
        ork_ornek_okunan: 16,
        ork_ornek_toplam: 17
    };

    // Uçlar (sayfa türüne göre). Testler bu tabloyu app.py'nin uç
    // listesiyle karşılaştırır.
    var UCLAR = {
        sivi: '/api/export-eng',
        kati: '/api/export-eng',
        hibrit: '/api/export-openrocket',
        ork: '/api/import/ork',
        motorDosyasi: '/api/import/motor-file'
    };

    // Sayfaların kendi bildirim yığınları (sabit konumlu; köşe bunları
    // DEĞİŞTİRMEZ). liquid.html/solid.html showMessage(): #toast-stack
    // (top 20 px, right 20 px, z-index 9999); import_ui.js ve project_bar.js
    // toast(): #hrma-toast-stack (right 18 px, bottom 18 px, z-index 99995).
    // Geniş ekranda yığın CSS ile panelin soluna kayar (openrocket_kose.css);
    // dar ekranda yer yoksa panel yığının altından başlar (yerlesimGuncelle).
    var BILDIRIM_YIGINLARI = ['toast-stack', 'hrma-toast-stack'];
    // Esc bu öğelerin içinden geldiyse bildirimi kapatır, paneli DEĞİL
    // (bildirim kutuları kendi keydown işleyicileriyle Esc'de kapanır).
    var BILDIRIM_SECICI = '.alert, #toast-stack, #hrma-toast-stack';
    // Panel ile bildirim yığını arasında bırakılan boşluk (px).
    var BILDIRIM_ARALIK_PX = 8;
    // Panel yığının altına itildiğinde kalan en küçük yükseklik (px).
    var PANEL_EN_AZ_YUKSEKLIK_PX = 160;

    // Sayfanın kendi .eng düğmesi (kimlik ya da onclick ile bulunur;
    // şablonlarda tek kez geçtikleri testlerle kilitli).
    var ENG_SECICILERI = [
        { tur: 'hibrit', secici: '#downloadEngBtn' },
        { tur: 'sivi', secici: 'button[onclick="downloadLiquidEng()"]' },
        { tur: 'kati', secici: 'button[onclick="downloadSolidEng()"]' }
    ];

    function T(key, fallback) {
        return (global.I18N && global.I18N.t) ? global.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (global.I18N && global.I18N.tf) return global.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }

    // Sürüm numarası bir ondalık sayı DEĞİLDİR: I18N.tf saf ondalık
    // görünümlü dizgeleri TR'de virgüle çevirir ('24.12' -> '24,12').
    // Sürüm bu yüzden tf'den SONRA, olduğu gibi yerleştirilir.
    function surumYerlestir(metin) {
        return String(metin).split('{version}').join(OLCUM.openrocket_surum);
    }

    // ------------------------------------------------------------------
    // Saf karar işlevi (DOM'suz; node altında test edilir)
    // ------------------------------------------------------------------
    // sayfa: 'sivi' | 'kati' | 'hibrit'; sonuc: window.currentResults;
    // asilDevreDisi: sayfanın kendi düğmesinin disabled durumu.
    // Dönüş: { etkin, neden (anahtar|null), uyari ({alanlar}|null),
    //         zarf ({kod}|null) }
    // zarf: /calculate* yanıtının openrocket.eng_envelope_warning kaydı
    // (hrma/export/openrocket_integration.py, kodu 'error' alanında; üç
    // motor yanıtında da var). Metin sunucudan İngilizce gelir; köşe KODU
    // okur ve EN/TR sözlük cümlesini gösterir (devir D4).
    function engDurumu(sayfa, sonuc, asilDevreDisi) {
        var motorVar = !!sonuc && typeof sonuc === 'object';
        if (motorVar && sayfa === 'hibrit') {
            // downloadEngFile() kapısıyla AYNI: currentResults.motor şart.
            motorVar = !!sonuc.motor && typeof sonuc.motor === 'object';
        }
        if (!motorVar || asilDevreDisi) {
            return { etkin: false, neden: 'openrocket.kose.reason.noMotor', uyari: null, zarf: null };
        }
        var orx = sonuc.openrocket;
        var hata = (orx && typeof orx === 'object') ? orx.eng_error : null;
        var uyari = null;
        if (hata && typeof hata === 'object') {
            var alanlar = Array.isArray(hata.missing_fields) ? hata.missing_fields : [];
            uyari = { alanlar: alanlar.map(function (a) { return String(a); }) };
        }
        var zk = (orx && typeof orx === 'object') ? orx.eng_envelope_warning : null;
        var zarf = null;
        if (zk && typeof zk === 'object') {
            zarf = { kod: (typeof zk.error === 'string' && zk.error) ? zk.error : null };
        }
        // Uyarı varken eylem AÇIK kalır: uç kendi 422 gerekçesini alan
        // adlarıyla verir; köşe sunucunun hükmünü önceden vermez.
        return { etkin: true, neden: null, uyari: uyari, zarf: zarf };
    }

    // ------------------------------------------------------------------
    // DOM
    // ------------------------------------------------------------------
    var durum = {
        kuruldu: false,
        acik: false,
        sayfa: null,
        engAsil: null,
        orkKutusu: null,
        zamanlayici: null,
        gozlemci: null
    };

    function el(tag, attrs, kids) {
        var n = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'text') n.textContent = attrs[k];
            else n.setAttribute(k, attrs[k]);
        });
        (kids || []).forEach(function (c) { if (c) n.appendChild(c); });
        return n;
    }

    function $(id) { return document.getElementById(id); }

    function sayfaTuruBul() {
        for (var i = 0; i < ENG_SECICILERI.length; i++) {
            var n = document.querySelector(ENG_SECICILERI[i].secici);
            if (n) return { tur: ENG_SECICILERI[i].tur, dugme: n };
        }
        return null;
    }

    // .ork kutusu: sixdof_panel.js orkBoxHtml() çıktısı. Kimliği yoktur;
    // #sd_ork_file ile #sd_ork_report'u birlikte taşıyan en yakın ata.
    function orkKutusuBul() {
        var dosya = $('sd_ork_file');
        if (!dosya) return null;
        var n = dosya.parentElement;
        while (n && n !== document.body) {
            if (n.querySelector('#sd_ork_report')) return n;
            n = n.parentElement;
        }
        return null;
    }

    function bolum(id, baslikAnahtari) {
        return el('section', { 'class': 'or-kose-bolum', id: id }, [
            el('h3', { 'class': 'or-kose-bolum-baslik', 'data-or-anahtar': baslikAnahtari })
        ]);
    }

    function kalem(id, uc) {
        var k = el('div', { 'class': 'or-kose-kalem', id: id });
        if (uc) k.setAttribute('data-uc', uc);
        k.appendChild(el('div', { 'class': 'or-kose-kalem-baslik', id: id + '_baslik' }));
        k.appendChild(el('div', { 'class': 'or-kose-kalem-aciklama', id: id + '_aciklama' }));
        return k;
    }

    function panelKur() {
        var sekme = el('button', {
            type: 'button', id: 'orKoseSekme', 'class': 'or-kose-sekme',
            'aria-expanded': 'false', 'aria-controls': 'orKosePanel'
        }, [el('span', { 'class': 'or-kose-sekme-yazi', text: MARKA })]);

        var panel = el('aside', {
            id: 'orKosePanel', 'class': 'or-kose-panel', hidden: 'hidden',
            role: 'complementary', 'aria-labelledby': 'orKoseBaslik'
        });
        var bas = el('div', { 'class': 'or-kose-bas' }, [
            el('h2', { id: 'orKoseBaslik', 'class': 'or-kose-baslik' }),
            el('button', { type: 'button', id: 'orKoseKapat', 'class': 'or-kose-kapat' },
               [el('span', { 'aria-hidden': 'true', text: '×' })])
        ]);
        panel.appendChild(bas);
        panel.appendChild(el('p', { id: 'orKoseGiris', 'class': 'or-kose-giris' }));

        // 1) OpenRocket'e aktar: .eng
        var b1 = bolum('orKoseBolumAktar', 'openrocket.kose.sec.export');
        var eng = kalem('orKoseEng', UCLAR[durum.sayfa]);
        eng.appendChild(el('button', { type: 'button', id: 'orKoseEngDugme',
                                        'class': 'btn or-kose-eylem' }));
        eng.appendChild(el('div', { id: 'orKoseEngNeden', 'class': 'or-kose-neden', hidden: 'hidden' }));
        eng.appendChild(el('div', { id: 'orKoseEngUyari', 'class': 'or-kose-uyari', hidden: 'hidden' }));
        eng.appendChild(el('div', { id: 'orKoseEngZarf', 'class': 'or-kose-uyari', hidden: 'hidden' }));
        eng.appendChild(el('div', { id: 'orKoseEngOlcum', 'class': 'or-kose-olcum' }));
        b1.appendChild(eng);
        panel.appendChild(b1);

        // 2) OpenRocket'ten al: .ork (6-DOF kutusu buraya taşınır)
        var b2 = bolum('orKoseBolumAl', 'openrocket.kose.sec.import');
        var ork = kalem('orKoseOrk', UCLAR.ork);
        ork.appendChild(el('div', { id: 'orKoseOrkYuva', 'class': 'or-kose-yuva' }));
        ork.appendChild(el('div', { id: 'orKoseOrkNeden', 'class': 'or-kose-neden', hidden: 'hidden' }));
        ork.appendChild(el('div', { id: 'orKoseOrkOlcum', 'class': 'or-kose-olcum' }));
        b2.appendChild(ork);
        panel.appendChild(b2);

        // 3) Bu sayfanın başka yerlerinde: .eng/.rse içe aktarma (yerinde
        //    kalır; o panellerin girdisidir). Köşe yalnız oraya götürür.
        var b3 = bolum('orKoseBolumDiger', 'openrocket.kose.sec.elsewhere');
        var itki = kalem('orKoseItki', UCLAR.motorDosyasi);
        itki.appendChild(el('button', { type: 'button', id: 'orKoseItkiGoster',
                                         'class': 'btn btn-secondary or-kose-eylem or-kose-kucuk' }));
        itki.appendChild(el('div', { id: 'orKoseItkiNeden', 'class': 'or-kose-neden', hidden: 'hidden' }));
        b3.appendChild(itki);
        var dog = kalem('orKoseDogrulama', UCLAR.motorDosyasi);
        dog.appendChild(el('button', { type: 'button', id: 'orKoseDogrulamaGoster',
                                        'class': 'btn btn-secondary or-kose-eylem or-kose-kucuk' }));
        dog.appendChild(el('div', { id: 'orKoseDogrulamaNeden', 'class': 'or-kose-neden', hidden: 'hidden' }));
        b3.appendChild(dog);
        panel.appendChild(b3);

        document.body.appendChild(sekme);
        document.body.appendChild(panel);
        return { sekme: sekme, panel: panel };
    }

    function metinleriYaz() {
        var p = $('orKosePanel');
        if (!p) return;
        var sekme = $('orKoseSekme');
        sekme.setAttribute('title', T('openrocket.kose.openTitle', 'Open the OpenRocket tools'));
        sekme.setAttribute('aria-label', T('openrocket.kose.openTitle', 'Open the OpenRocket tools'));
        $('orKoseBaslik').textContent = T('openrocket.kose.title', 'OpenRocket file exchange');
        $('orKoseKapat').setAttribute('aria-label', T('openrocket.kose.close', 'Close'));
        $('orKoseKapat').setAttribute('title', T('openrocket.kose.close', 'Close'));
        $('orKoseGiris').textContent = T('openrocket.kose.intro',
            'HRMA reads OpenRocket designs (.ork) and writes RASP motor files (.eng) that OpenRocket loads. These tools are collected here; the motor analysis does not depend on them.');

        var basliklar = {
            'openrocket.kose.sec.export': T('openrocket.kose.sec.export', 'Export to OpenRocket'),
            'openrocket.kose.sec.import': T('openrocket.kose.sec.import', 'Import from OpenRocket'),
            'openrocket.kose.sec.elsewhere': T('openrocket.kose.sec.elsewhere', 'Elsewhere on this page')
        };
        Array.prototype.forEach.call(p.querySelectorAll('[data-or-anahtar]'), function (h) {
            var k = h.getAttribute('data-or-anahtar');
            if (basliklar[k]) h.textContent = basliklar[k];
        });

        var tarih = T('openrocket.kose.measuredDate', '7 October 2026');
        $('orKoseEng_baslik').textContent = T('openrocket.kose.eng.title', 'Motor file (.eng, RASP format)');
        $('orKoseEng_aciklama').textContent = T('openrocket.kose.eng.desc',
            'Thrust curve and masses of the computed motor, to load as a motor in OpenRocket.');
        $('orKoseEngDugme').textContent = T('openrocket.kose.eng.btn', 'Download .eng');
        $('orKoseEngOlcum').textContent = OLCUM.eng_okundu
            ? surumYerlestir(TF('openrocket.kose.eng.measured', { date: tarih },
                 'Measured on {date}: the motor loader of OpenRocket {version} (installed app, headless) reads the exported file.'))
            : '';

        $('orKoseOrk_baslik').textContent = T('openrocket.kose.ork.title', 'Rocket design (.ork)');
        $('orKoseOrk_aciklama').textContent = T('openrocket.kose.ork.desc',
            'Geometry and component masses go into the 6-DOF flight panel.');
        $('orKoseOrkOlcum').textContent = surumYerlestir(TF('openrocket.kose.ork.measured',
            { date: tarih, read: OLCUM.ork_ornek_okunan, total: OLCUM.ork_ornek_toplam },
            'Measured on {date}: {read} of {total} example designs shipped with OpenRocket {version} are imported.'));

        $('orKoseItki_baslik').textContent = T('openrocket.kose.thrust.title',
            'Motor file as thrust source (.eng / .rse)');
        $('orKoseItki_aciklama').textContent = TF('openrocket.kose.thrust.desc',
            { label: T('sixdof.thrustSource', 'Thrust source') },
            '6-DOF flight panel, "{label}" selector.');
        $('orKoseItkiGoster').textContent = T('openrocket.kose.show', 'Show');

        $('orKoseDogrulama_baslik').textContent = T('openrocket.kose.valid.title',
            'Test data comparison (.eng / .rse)');
        $('orKoseDogrulama_aciklama').textContent = T('openrocket.kose.valid.desc',
            'Validation panel of the analysis center.');
        $('orKoseDogrulamaGoster').textContent = T('openrocket.kose.show', 'Show');

        durumGuncelle();
    }

    function nedenYaz(id, anahtar) {
        var n = $(id);
        if (!n) return;
        if (!anahtar) { n.hidden = true; n.textContent = ''; return; }
        var metinler = {
            'openrocket.kose.reason.noMotor': function () {
                return T('openrocket.kose.reason.noMotor', 'Run the motor calculation first.');
            },
            'openrocket.kose.reason.noSixdof': function () {
                return T('openrocket.kose.reason.noSixdof', 'The 6-DOF flight panel is not loaded on this page.');
            },
            'openrocket.kose.reason.validationClosed': function () {
                return T('openrocket.kose.reason.validationClosed',
                         'Open the Validation panel in the analysis center first.');
            }
        };
        n.textContent = metinler[anahtar] ? metinler[anahtar]() : anahtar;
        n.hidden = false;
    }

    // Bildirim yığını panelin üstüne binmesin (denetim Ş2, ölçüldü: 422
    // hata bildirimi kapatma düğmesini, .eng düğmesini, uyarıyı ve başlığı
    // örtüyordu). Yığın panelle yatayda örtüşüyorsa (CSS kaydıramadıysa,
    // dar ekran) panel üstteki yığının ALTINDAN başlar, alttaki yığının
    // ÜSTÜNDE biter. Yığın boşsa ya da örtüşmüyorsa CSS konumu aynen kalır.
    function yerlesimGuncelle() {
        var panel = $('orKosePanel');
        if (!panel) return;
        panel.style.top = '';
        panel.style.maxHeight = '';
        if (!durum.acik) return;
        var pr = panel.getBoundingClientRect();
        var yukseklik = global.innerHeight || document.documentElement.clientHeight;
        var ust = pr.top;
        var alt = yukseklik;
        BILDIRIM_YIGINLARI.forEach(function (id) {
            var y = $(id);
            if (!y) return;
            var r = y.getBoundingClientRect();
            if (!r.width || !r.height) return;
            if (r.right <= pr.left || r.left >= pr.right) return;
            if (r.top < yukseklik / 2) ust = Math.max(ust, r.bottom + BILDIRIM_ARALIK_PX);
            else alt = Math.min(alt, r.top - BILDIRIM_ARALIK_PX);
        });
        if (ust !== pr.top || alt < pr.bottom) {
            panel.style.top = ust + 'px';
            panel.style.maxHeight = Math.max(alt - ust, PANEL_EN_AZ_YUKSEKLIK_PX) + 'px';
        }
    }

    // Yığınlar sayfa tarafından ilk bildirimde kurulur; panel açıkken
    // gövdeye eklenen yığın ve yığına eklenen bildirim izlenir.
    function bildirimleriIzle() {
        if (!durum.gozlemci) return;
        BILDIRIM_YIGINLARI.forEach(function (id) {
            var y = $(id);
            if (y) durum.gozlemci.observe(y, { childList: true });
        });
    }

    function durumGuncelle() {
        if (!durum.kuruldu) return;
        yerlesimGuncelle();
        // .eng
        var asil = durum.engAsil;
        var d = engDurumu(durum.sayfa, global.currentResults, !!(asil && asil.disabled));
        var dugme = $('orKoseEngDugme');
        dugme.disabled = !d.etkin;
        dugme.setAttribute('aria-disabled', d.etkin ? 'false' : 'true');
        if (d.neden) dugme.setAttribute('aria-describedby', 'orKoseEngNeden');
        else dugme.removeAttribute('aria-describedby');
        nedenYaz('orKoseEngNeden', d.neden);
        var u = $('orKoseEngUyari');
        if (d.uyari) {
            u.textContent = TF('openrocket.kose.warn.engError',
                { fields: d.uyari.alanlar.length ? d.uyari.alanlar.join(', ') : '?' },
                'This run could not produce an .eng file. Missing: {fields}.');
            u.hidden = false;
        } else {
            u.textContent = '';
            u.hidden = true;
        }
        var z = $('orKoseEngZarf');
        if (d.zarf) {
            var zarfMetinleri = {
                propellant_outside_envelope: function () {
                    return T('openrocket.kose.warn.envelopeOutside',
                        'The propellant is held in separate tanks, not inside the motor envelope written to the .eng file. OpenRocket places the loaded mass inside the motor, so the centre of gravity, the stability margin and the apogee it computes are wrong until the tanks are modelled as separate components.');
                },
                envelope_is_declared_placeholder: function () {
                    return T('openrocket.kose.warn.envelopePlaceholder',
                        'The motor envelope written to the .eng file is a declared placeholder, not the measured case. Correct the diameter and the length in OpenRocket.');
                }
            };
            // Tanınmayan kod susturulmaz: kodu adıyla söyler (fail-closed).
            z.textContent = (d.zarf.kod && zarfMetinleri.hasOwnProperty(d.zarf.kod))
                ? zarfMetinleri[d.zarf.kod]()
                : TF('openrocket.kose.warn.envelopeUnknown', { code: d.zarf.kod || '?' },
                     'The server reported a motor envelope warning that this panel does not recognise (code: {code}).');
            z.setAttribute('data-kod', d.zarf.kod || '');
            z.hidden = false;
        } else {
            z.textContent = '';
            z.removeAttribute('data-kod');
            z.hidden = true;
        }

        // .ork kutusu
        var orkVar = !!(durum.orkKutusu && $('sd_ork_file'));
        nedenYaz('orKoseOrkNeden', orkVar ? null : 'openrocket.kose.reason.noSixdof');

        // Yönlendirmeler
        var itkiHedef = $('sd_thrust_src');
        $('orKoseItkiGoster').disabled = !itkiHedef;
        nedenYaz('orKoseItkiNeden', itkiHedef ? null : 'openrocket.kose.reason.noSixdof');
        var dogHedef = $('vp_csv_file');
        var dogGorunur = !!(dogHedef && dogHedef.getClientRects().length);
        $('orKoseDogrulamaGoster').disabled = !dogGorunur;
        nedenYaz('orKoseDogrulamaNeden', dogGorunur ? null : 'openrocket.kose.reason.validationClosed');
    }

    function ac() {
        if (!durum.kuruldu) return;
        durum.acik = true;
        $('orKosePanel').hidden = false;
        $('orKoseSekme').setAttribute('aria-expanded', 'true');
        document.body.classList.add('or-kose-acik');
        if (!durum.gozlemci && typeof global.MutationObserver === 'function') {
            durum.gozlemci = new global.MutationObserver(function () {
                bildirimleriIzle();
                yerlesimGuncelle();
            });
            durum.gozlemci.observe(document.body, { childList: true });
            bildirimleriIzle();
        }
        durumGuncelle();
        // Hesap bitince düğme kendiliğinden açılsın diye panel açıkken
        // durum saniyede bir yeniden okunur (yalnız açıkken).
        if (!durum.zamanlayici) {
            durum.zamanlayici = global.setInterval(durumGuncelle, 1000);
        }
    }

    function kapat() {
        if (!durum.kuruldu) return;
        durum.acik = false;
        $('orKosePanel').hidden = true;
        $('orKoseSekme').setAttribute('aria-expanded', 'false');
        document.body.classList.remove('or-kose-acik');
        if (durum.gozlemci) {
            durum.gozlemci.disconnect();
            durum.gozlemci = null;
        }
        yerlesimGuncelle();
        if (durum.zamanlayici) {
            global.clearInterval(durum.zamanlayici);
            durum.zamanlayici = null;
        }
    }

    function gotur(hedef) {
        if (!hedef) return;
        kapat();
        try { hedef.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        catch (e) { hedef.scrollIntoView(); }
        try { hedef.focus({ preventScroll: true }); } catch (e) { /* odak zorunlu değil */ }
    }

    // Dağınık düğmeleri gizle (kimlik ve olay dinleyicileri korunur).
    function tasiVeGizle() {
        if (durum.engAsil) {
            durum.engAsil.classList.add('or-kose-tasindi');
            durum.engAsil.setAttribute('data-or-kose', 'tasindi');
            // Sıvı sayfası: dışa aktarım panelindeki ".eng" açıklama satırı
            // bu düğmeyi anlatıyordu; düğmeyle birlikte köşeye geçer.
            var tanim = document.querySelector('[data-i18n="liq.ui.openrocket_eng"]');
            var li = tanim && tanim.closest ? tanim.closest('li') : null;
            if (li) {
                li.classList.add('or-kose-tasindi');
                li.setAttribute('data-or-kose', 'tasindi');
            }
        }
        var kutu = orkKutusuBul();
        if (kutu) {
            durum.orkKutusu = kutu;
            kutu.setAttribute('data-or-kose', 'tasindi-ork');
            $('orKoseOrkYuva').appendChild(kutu);
        }
    }

    function kur() {
        if (durum.kuruldu) return true;
        var bulunan = sayfaTuruBul();
        if (!bulunan) return false;          // motor sayfası değil
        durum.sayfa = bulunan.tur;
        durum.engAsil = bulunan.dugme;
        panelKur();
        durum.kuruldu = true;
        tasiVeGizle();

        $('orKoseSekme').addEventListener('click', function () {
            if (durum.acik) kapat(); else ac();
        });
        $('orKoseKapat').addEventListener('click', function () {
            kapat();
            $('orKoseSekme').focus();
        });
        $('orKoseEngDugme').addEventListener('click', function () {
            durumGuncelle();
            if ($('orKoseEngDugme').disabled) return;
            // Sayfanın KENDİ düğmesi: aynı işlev, aynı uç, aynı bildirimler.
            durum.engAsil.click();
        });
        $('orKoseItkiGoster').addEventListener('click', function () {
            gotur($('sd_thrust_src'));
        });
        $('orKoseDogrulamaGoster').addEventListener('click', function () {
            gotur($('vp_csv_file'));
        });
        document.addEventListener('keydown', function (ev) {
            if (!durum.acik || (ev.key !== 'Escape' && ev.key !== 'Esc')) return;
            // Bildirimi kapatan Esc paneli kapatmaz (denetim Ş2).
            var hedef = ev.target;
            if (hedef && hedef.closest && hedef.closest(BILDIRIM_SECICI)) return;
            kapat();
            $('orKoseSekme').focus();
        });
        global.addEventListener('resize', yerlesimGuncelle);
        if (global.I18N && global.I18N.onChange) global.I18N.onChange(metinleriYaz);
        metinleriYaz();
        // Gizleme kuralları yalnız bu sınıf varken etkindir (bkz. CSS).
        document.body.classList.add('or-kose-hazir');
        return true;
    }

    // SixDofPanel.init sayfaların DOMContentLoaded işleyicilerinde koşar;
    // .ork kutusunu bulabilmek için 'load' olayında kurulur. Kutu o anda
    // yoksa (6-DOF geç kurulduysa) kısa bir süre yeniden denenir.
    function baslat() {
        if (!kur()) return;
        if (durum.orkKutusu) return;
        var deneme = 0;
        var t = global.setInterval(function () {
            deneme += 1;
            var kutu = orkKutusuBul();
            if (kutu) {
                durum.orkKutusu = kutu;
                kutu.setAttribute('data-or-kose', 'tasindi-ork');
                $('orKoseOrkYuva').appendChild(kutu);
                durumGuncelle();
            }
            if (kutu || deneme >= 20) global.clearInterval(t);
        }, 250);
    }

    global.HRMAOpenRocketKose = {
        OLCUM: OLCUM,
        UCLAR: UCLAR,
        engDurumu: engDurumu,
        ac: ac,
        kapat: kapat,
        durumGuncelle: durumGuncelle,
        kuruldu: function () { return durum.kuruldu; }
    };

    if (typeof document === 'undefined') return;
    if (document.readyState === 'complete') baslat();
    else global.addEventListener('load', baslat);
})(typeof window !== 'undefined' ? window : globalThis);
