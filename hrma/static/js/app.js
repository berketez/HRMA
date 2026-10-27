// JavaScript for HRMA Rocket Motor Analysis Tool

// i18n köprüsü — i18n.js yüklenmemişse İngilizce yedek metin döner.
function T(key, fallback) {
    return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
}
function TF(key, params, fallback) {
    if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
    return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
        return (params && name in params) ? String(params[name]) : whole;
    });
}
// Sunucudan DÜZ METİN gelen uyarı/hata satırı — sözlük + desen; eşleşme
// yoksa metin AYNEN döner. i18n_charts.js yoksa metin dokunulmadan geçer.
function SRV(text) {
    return (window.I18N && window.I18N.serverText)
        ? window.I18N.serverText(text) : text;
}

/* ÖH D35 / OH-GT-25 — EKRAN SAYISI TEK KAYNAKTAN (i18n.js kanonu).

   ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/D35/sayi-bicimi/a1/once.json +
   ana modelin tarayıcı sayımı, 22 Eylül, TR oturum): ekrana giden
   ondalıklar NOKTA ile basılıyordu — hibrit 202 / katı 210 / sıvı 95
   noktalı ondalık, buna karşılık yalnız 36 / 20 / 30 virgüllü. Sebep
   tek bir hata değil, DESENDİ: ayraç kararı her çağrı yerinde ayrı
   ayrı `toFixed` ile veriliyordu, yani kural ekranın yüzlerce yerinde
   tekrarlanıyordu.

   Bu üç yardımcı kararı i18n.js'e devreder (`I18N.number` /
   `I18N.unit` / `I18N.percent`); ayraç `ondalikAyraci()` TEK
   kaynağından okunur. Basamak sayısı DEĞİŞMEZ: çağıran `toFixed(1)`
   dediyse yine bir basamak basılır, yalnız ayraç yerelleşir — aksi
   hâlde ekranda ölçülmemiş bir duyarlık ilan edilirdi (i18n.js:309
   künyesi). Sözlük motoru yoksa eski davranışa düşülür: sayı
   UYDURULMAZ, yalnız ayraç yerelleşmez (panellerin `_num` deseni,
   cfd_panel.js:207). `typeof window` kontrolü BİLEREK: solid.html'in
   dürüst biçimlendirici bloğu node'da DOM'suz koşturuluyor
   (tests/test_ui_no_fabricated_numbers.py). */
// ÖH D36 · A-3 + G-1 — hibrit sayfasının yeni metinleri app.* anahtarlarıdır
// ve i18n_common.js'te durur; şablon (advanced.html) yalnız i18n_advanced.js
// anahtarlarını kullanır (tests/test_i18n_advanced.py sözleşmesi). Metni bu
// dosya kurar, şablon yalnız veriyi verir.
function tasarimKaynakNotu(kaynak, alanId) {
    if (kaynak === 'user') return T('app.design.srcUser', 'you edited');
    if (alanId === 'pressure_drop_percent') {
        return T('app.design.srcProjectDpNotApplied',
            'from the project file; not applied, the injector circuit solution takes precedence until you edit this field');
    }
    return T('app.design.srcProject', 'from the project file');
}
function tasarimDurumSatirlari(giden, kalan) {
    const satirlar = [];
    if (giden.length) {
        satirlar.push(TF('app.design.willSend', { fields: giden.join(', ') },
                         'Will be sent to the solver: {fields}'));
    }
    if (kalan.length) {
        satirlar.push(TF('app.design.willNotSend', { fields: kalan.join(', ') },
                         'Not sent, HRMA decides and declares it in the results: {fields}'));
    }
    return satirlar;
}
function tasarimOneriNotu() {
    return T('app.design.suggestionNote',
        'The values shown are suggestions. A field reaches the solver only after you change it (or a project file supplies it); untouched fields are not sent, so HRMA sizes the wall and solves the injector pressure drop itself and declares that in the results.');
}
// G-1: "Optimumu Bul" sonucunun künye satırları. Sayı uydurulmaz: bant ve
// basınç uç yanıtından, kanon son hesabın motor.optimum_of_ratio alanından.
function optimumKunyeSatirlari(result, motor) {
    const satirlar = [];
    const aralik = (result && Array.isArray(result.sweep_range)) ? result.sweep_range : null;
    if (aralik && aralik.length === 2 && typeof result.chamber_pressure === 'number') {
        satirlar.push(TF('app.optimum.basis', {
            lo: numTxt(aralik[0], 2), hi: numTxt(aralik[1], 2),
            pc: numTxt(result.chamber_pressure, 1)
        }, 'Found by a sea-level-exit equilibrium search (no nozzle expansion ratio), O/F band {lo} to {hi}, Pc {pc} bar.'));
    }
    const kanonOF = motor ? motor.optimum_of_ratio : null;
    const kanonIsp = motor ? motor.maximum_isp : null;
    if (typeof kanonOF === 'number' && isFinite(kanonOF)) {
        satirlar.push(TF('app.optimum.canon', {
            of: numTxt(kanonOF, 2),
            isp: (typeof kanonIsp === 'number' && isFinite(kanonIsp)) ? numTxt(kanonIsp, 1) : '-'
        }, 'Solver canon (design nozzle, last calculation): O/F {of}, Isp {isp} s.'));
    } else {
        satirlar.push(T('app.optimum.canonNone',
            'Solver canon: not available until you run Calculate (the solver searches at the design nozzle).'));
    }
    return satirlar;
}
function optimumEgriAltYazisi(pcv) {
    if (!pcv || !Array.isArray(pcv.sweep_range) || typeof pcv.step !== 'number') return null;
    return TF('app.optimum.curveBasis', {
        lo: numTxt(pcv.sweep_range[0], 2), hi: numTxt(pcv.sweep_range[1], 2),
        step: numTxt(pcv.step, 3), n: String(pcv.n_points)
    }, 'Display grid {lo} to {hi}, step {step}, {n} points, sea-level exit; not the solver canon.');
}

function numTxt(v, d) {
    return (typeof window !== 'undefined' && window.I18N && window.I18N.number)
        ? window.I18N.number(v, d)
        : ((typeof v === 'number' && isFinite(v))
            ? (d === undefined ? String(v) : v.toFixed(d)) : String(v));
}
function unitTxt(v, unit, d) {
    return (typeof window !== 'undefined' && window.I18N && window.I18N.unit)
        ? window.I18N.unit(v, unit, d)
        : (numTxt(v, d) + (unit ? '\u00A0' + unit : ''));
}
function pctTxt(v, d) {
    return (typeof window !== 'undefined' && window.I18N && window.I18N.percent)
        ? window.I18N.percent(v, d) : (numTxt(v, d) + '%');
}

// currentResults is defined in advanced.html to avoid conflicts

// ENJEKTÖR ALAN KURUCUSU BURADA DEĞİL — templates/advanced.html içindeki
// inline updateInjectorParams'tadır.
//
// ÖH D25 · P11B2-22: burada aynı adlı İKİNCİ bir kopya duruyordu (74
// satır). Ölçüldü (a3/once.json, taban cdf2106):
//   * advanced.html app.js'i ÖNCE yükleyip kendi inline sürümünü SONRA
//     tanımladığı için global bağ onunkiydi; buradaki kopya hiçbir zaman
//     çalışmıyordu (v2.6.26'da getFormData için ölçülen desenin aynısı).
//   * Kap adları çaprazlanmıştı: bu kopya `#injectorParams` kabına
//     yazıyordu, advanced.html'de o kimlik 0 kez geçiyor (`#dynamic_params`
//     1 kez) — yani çalıştırılsaydı bile "Injector elements not found"
//     deyip çıkardı.
//   * Kapsam farkı: bu kopya showerhead/pintle/swirl (3 tip) taşıyordu,
//     sayfadaki seçici 5 seçenek sunuyor (impingement ve coaxial dahil) ve
//     şablonun kopyası beşini de kuruyor.
// Şablondaki kopya kendi `adv.inj.*` anahtarlarıyla çevrilidir, yani
// çeviri kaybı YOKTUR. Ölü kopyanın 10 `app.inj.*` anahtarı artık
// hiçbir yerden kullanılmadığı için sözlükten de KALDIRILDI (EN+TR 20
// kayıt); depo bunu zaten şart koşuyor:
// tests/test_i18n_common.py::test_every_dictionary_key_is_used.
//
// Aşağıdaki DOMContentLoaded ve dil-değişimi çağrıları çalışma anında
// advanced.html'deki inline sürüme çözülür; sürüm YOKSA (app.js'i
// tanımsız bir sayfa yüklerse) çağrı SESSİZCE ATLANIR — uydurma alan
// basılmaz (fail-closed).

// Birim dönüşüm katsayıları — TEK KAYNAK. Arayüz mühendislik birimlerinde
// (mm, mm²) girdi alır, backend SI (m, m²) bekler; dönüşüm burada tanımlıdır.
const MM_PER_M = 1000;
const MM2_PER_M2 = MM_PER_M * MM_PER_M;

// ÖH D25 · P11B2-23 — AÇI BASIMININ TEK KAYNAĞI.
// ÖLÇÜLDÜ (a3/once.json, taban cdf2106): swirl enjektörle koşulan uç
// `injector.spray_angle = 90.00000000000001` döndürüyor (çözücü
// 2*theta_half hesaplıyor, ikili artık kaçınılmaz) ve tasarım raporu bu
// alanı `${injectorData.spray_angle}°` ile YUVARLAMADAN basıyordu:
// ekranda "90.00000000000001°" yazıyordu. Aynı tablonun diğer bütün
// sayıları toFixed(1)/toFixed(2) ile basılıyor ve güvertenin tamamı 6
// anlamlı basamak kuralına (DOCK_SIGFIG) uyuyor. Sayı GİZLENMEZ, yalnız
// okunabilir basamağa yuvarlanır; alan yoksa em tire konur (uydurma yok).
const ACI_BASAMAK = 2;
function aciBas(v, basamak) {
    const n = Number(v);
    if (v === undefined || v === null || !isFinite(n)) return '—';
    return numTxt(n, basamak === undefined ? ACI_BASAMAK : basamak) + '°';
}

// Safe parseFloat with fallback - only for NaN/invalid values
function safeParseFloat(value, fallback = 0) {
    const parsed = parseFloat(value);
    return isNaN(parsed) || !isFinite(parsed) ? fallback : parsed;
}

// TOPLAYICI BURADA DEGIL — templates/advanced.html icindeki inline
// getFormData'dadir.
//
// v2.6.26: burada 76 satirlik ikinci bir getFormData kopyasi duruyordu.
// advanced.html app.js'i once yukleyip kendi inline surumunu SONRA
// tanimladigi icin inline olan bu kopyayi gölgeliyordu; yani bu kod
// hicbir zaman calismiyordu. Iki kopya farkli varsayilanlar tasiyordu
// (burada regression_a=0.0003 / n=0.5, inline'da 3.68e-5 / 0.555) ve
// hangisinin gecerli oldugu koddan anlasilmiyordu. Denetim sirasinda
// envanter betigi yanlis kopyayi tarayip 33 alan bulmustu; gercek
// toplayici 41 alan gonderiyor.
//
// Buradaki kopyanin okudugu gamma / gas_constant / chamber_temperature /
// thrust_coefficient anahtarlarinin advanced.html'de KARSILIK GELEN
// ALANI YOK (getElementById null donuyordu); app.py bu anahtarlari
// okuyor ama arayuzden erisilemiyorlar. Silinmeleriyle bir sey kaybolmadi.
//
// Aşağıdaki calculate() / calculateParametric() / calculateTrajectory()
// çağrılarındaki getFormData(), çalışma anında advanced.html'deki inline
// sürüme çözülür.
//
// ÖH D25 · P11B2-22 — YORUM ÖLÇÜMLE DÜZELTİLDİ. Burada "liquid.html ve
// solid.html app.js'i yükler" yazıyordu; ölçüldü (a3/once.json, taban
// cdf2106):
//     grep -l 'js/app.js' hrma/templates altındaki bütün .html
//     dosyalarında  ->  YALNIZ advanced.html
//     (glob deseni bilerek yazılmadı: yorum içindeki bir bölü-yıldız
//      dizisi blok yorum açar ve tarayıcılar dosyanın geri kalanını
//      yorum sanar — ölçüldü, test_i18n_common strip_comments)
// liquid.html ve solid.html app.js'i HİÇ yüklemez (kendi inline
// calculateLiquid() / calculateSolid() akışlarını taşırlar). Yanlış yorum
// bir sonraki denetimi yine yanlış kopyaya yönlendirirdi.

// Main calculation function
async function calculate() {
    // Prevent any browser form validation
    event?.preventDefault?.();
    
    const data = getFormData();
    
    // Validate inputs
    if (!validateInputs(data)) {
        return;
    }

    // ÖH D28 · P12bB3-17 — SAYFANIN KENDİ EK DOĞRULAYICISI ARTIK KOŞAR.
    // ÖLÇÜLDÜ (a3/once_taban.json): `advanced.html` 50 satırlık
    // `validateFormData()` taşıyor (10 zorunlu alan + O/F 0,1-20,
    // Pc 1-100 bar, F 1-100000 N, t_b 0,1-300 s) ve depoda ÇAĞRISI YOK
    // (`validateFormData_cagrisi = 0`); sayfada `<form>` de 0 adet ve
    // `invalid` olayı bastırılıyor, yani ekranda ilan edilen beş bandın
    // hiçbiri uygulanmıyordu (ölçülen boşluk: Pc = 400 bar HTTP 200).
    // Bağlama BURADA yapılır çünkü ortak giriş kapısı budur; şablonun
    // `calculate`i yeniden tanımlaması gölgeleme (P12bB3-09) üretirdi.
    // Sayfa böyle bir doğrulayıcı tanımlamadıysa hiçbir şey değişmez.
    if (typeof window.validateFormData === 'function') {
        let sayfaHatalari = [];
        try {
            sayfaHatalari = window.validateFormData(data) || [];
        } catch (e) {
            sayfaHatalari = [];   // doğrulayıcı patlarsa hesap engellenmez
        }
        if (Array.isArray(sayfaHatalari) && sayfaHatalari.length) {
            showError(sayfaHatalari.join(' \u2022 '));
            return;
        }
    }
    
    // Show loading indicator
    showLoading(true);
    hideWelcomeMessage();
    
    try {
        const response = await fetch('/calculate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response text:', errorText);
            // ÖH D29 · P11B2-16 — HAM GÖVDE KULLANICIYA BASILMAZ.
            // V301/E2 (devir madde 7): 4xx yapılı ret gövdesinin AÇIKLAMA
            // cümlesi ve adlı alanları gösterilir (sunucuRetHatasi).
            throw sunucuRetHatasi(
                response.status, response.headers.get('content-type'),
                errorText);
        }

        const responseText = await response.text();

        let results;
        try {
            results = JSON.parse(responseText);
        } catch (parseError) {
            console.error('JSON parse error:', parseError);
            throw new Error(`Failed to parse response: ${parseError.message}. Raw response: ${responseText}`);
        }
        
        if (results.error) {
            throw new Error(results.error);
        }
        
        currentResults = results;
        // V301/E2: bu sonucu üreten istek gövdesi (ayrı enjektör paneli ana
        // tasarımın eleman girdilerini buradan alır; form sonradan değişse
        // de eşleme bu hesaba aittir).
        if (typeof window !== 'undefined') window.currentRequest = data;
        // A1 — uçuş köprüsü: sonucu /launch-site'ın okuyacağı tek şemaya
        // çevirtip localStorage'a yaz. Hesap akışını ASLA bozmaz (modül tüm
        // hataları yutar); araç yoksa uçuş sayfası örnek araca düşer.
        if (window.FlightHandoff) {
            window.FlightHandoff.publish(results, { motor_type: 'hybrid' });
        }
        displayCalculationResults(results);
        
        // Enable export buttons
        setExportResultsEnabled(true);
        
        // Enable STL and OpenRocket export buttons
        const exportSTLBtn = document.getElementById('exportSTLBtn');
        const downloadEngBtn = document.getElementById('downloadEngBtn');
        if (exportSTLBtn) {
            exportSTLBtn.disabled = false;
        }
        if (downloadEngBtn) {
            downloadEngBtn.disabled = false;
        }
        
        // Reset CAD status now that we have results
        if (typeof resetCADStatus === 'function') {
            resetCADStatus();
        }
        
    } catch (error) {
        // ÖH D15 / P11B2-07 — BAYAT SONUÇ EKRANDA KALMAZ.
        // ÖLÇÜLDÜ (kod yolu): hata dalı yalnız `handleError` çağırıyordu;
        // `currentResults` bir önceki koşumun değerinde kalıyor, sonuç
        // paneli açık duruyor, bir önceki koşuda `disabled=false` yapılan
        // PDF / STL / .eng düğmeleri ETKİN kalıyordu. Kullanıcı bir
        // parametreyi değiştirip Hesapla'ya basıyor, uyarıyı kapatıyor ve
        // DEĞİŞTİRDİĞİ PARAMETREYE AİT OLMAYAN sayıları okumaya devam
        // ediyordu — üstelik o hâliyle dışa aktarabiliyordu.
        // Emsal aynı depoda: analysis_center.js saklı sonucu `stale`
        // beyanıyla basar, analysis_dock.js koşumdan önce kabı gizler.
        invalidateStaleResults();
        handleError(error, 'Main Calculation Function');
    } finally {
        showLoading(false);
    }
}

// ÖH D15 / P11B2-07 — başarısız koşumdan sonra ekranı kazanılmamış hâle
// getirir: sonuç kabı gizlenir, dışa aktarım düğmeleri kapanır, saklı
// sonuç düşürülür. Sayı SİLİNMEZ, GÖSTERİLMEZ: ekranda kalan bir sayı
// hangi girdiye ait olduğu bilinmeden okunamaz.
function invalidateStaleResults() {
    currentResults = null;
    if (typeof window !== 'undefined') window.currentRequest = null;
    const panel = document.getElementById('resultsPanel');
    if (panel) panel.style.display = 'none';
    ['exportResultsBtn', 'exportSTLBtn', 'downloadEngBtn'].forEach(function (id) {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = true;
    });
    // OH-GT-09: kapanan düğme nedenini yeniden söyler.
    setExportResultsEnabled(false);
    const warningsPanel = document.getElementById('warningsPanel');
    if (warningsPanel) warningsPanel.style.display = 'none';
}

// ---------------------------------------------------------------------
// ÖH D34 · OH-GT-09 — KAPALI DIŞA AKTARIM DÜĞMESİ NEDENİNİ SÖYLER
// ---------------------------------------------------------------------
// ÖLÇÜLDÜ (a1/once.json K3): "Sonuçları Dışa Aktar" düğmesi sayfa
// açılışında `disabled` geliyor, `opacity: .4` ile soluyor AMA hiçbir
// `title` taşımıyordu (`title_var: false`) ve imleç hâlâ `pointer`dı
// (`sablonda_btn_disabled_imleci: false`) — yani düğme tıklanabilir
// görünüyor, tıklanınca hiçbir şey olmuyor ve NEDENİ hiçbir yerde
// yazmıyordu. İmleç kuralı şablonun kendi stil bloğunda; neden metni
// burada. Metin YENİ anahtar İSTEMEZ: `app.msg.noResultsExport`
// (i18n_common.js) tam bu durumu söyleyen mevcut karşılıktır ve
// `exportReport()` çağrıldığında zaten aynı metin basılır.
function setExportResultsEnabled(etkin) {
    const btn = document.getElementById('exportResultsBtn');
    if (!btn) return null;
    btn.disabled = !etkin;
    if (etkin) {
        btn.removeAttribute('title');
    } else {
        btn.title = T('app.msg.noResultsExport', 'No results to export');
    }
    return btn;
}

// ---------------------------------------------------------------------
// ÖH D24 / P11B2-09 — EKRANDAKİ min/max BEYANI DEKORATİF DEĞİLDİR
// ---------------------------------------------------------------------
// ÖLÇÜLDÜ (a3/once.json): advanced.html'de 87 `type="number"` girdisinin
// 70'i `min` ve/veya `max` BEYAN EDİYOR; `validateInputs` bunların
// yalnız 8'inin adını anıyor ve onlar için de HTML'deki sayıları değil
// JS'e ayrıca yazılmış başka eşikleri uyguluyordu. `calculate()` ilk
// satırında `event?.preventDefault?.()` çağırdığı için tarayıcının kendi
// min/max denetimi de kapalı. Ölçülen sonuç (P11 B2-repro-14):
//   oxidizer_temp = -50 K (min=100) -> HTTP 200, ekranda olağan sonuç
//   l_star = -5 m (min=0.1)         -> HTTP 200, aynı sayılar
//   wall_thickness = 0.5 mm (min=2) -> Min SF 1,69 -> 0,29, tek uyarı yok
//
// TEK KAYNAK: sınır sayıları buraya KOPYALANMAZ. Beyanı yapan yer HTML'dir
// ve kapı o beyanı okur; ikinci bir eşik tablosu yazmak iki kaynaklı bir
// sistem üretirdi (aynı kusurun P11B2-09'da ölçülen hâli: HTML min=1 ⟷ JS
// >200). Boş alan burada HATA DEĞİLDİR — boşluğun hükmü çağıranındır.
// V301/DİL (NK-22, kalem 3): hata iletisi alanı EKRANDAKİ etiketiyle söyler
// (ölçüldü: TR iletide ham "thrust" yazıyordu) ve sorunlu kutu işaretlenir.
// Etiket sırası: data-label > <label for> içindeki ilk çevrili metin (ipucu
// balonu ve birim hariç) > name/id (son çare, eski davranış).
function alanEkranEtiketi(el) {
    const beyan = el.getAttribute('data-label');
    if (beyan) return beyan;
    let lab = null;
    try {
        lab = (el.labels && el.labels.length) ? el.labels[0]
            : (el.id ? document.querySelector('label[for="' + el.id + '"]') : null);
    } catch (e) { lab = null; }
    if (lab) {
        const ilk = lab.querySelector('[data-i18n]:not(.unit):not(.tooltip-text)');
        let t = ilk ? ilk.textContent : '';
        if (!t) {
            const kopya = lab.cloneNode(true);
            Array.prototype.forEach.call(
                kopya.querySelectorAll('.tooltip, .unit'),
                function (x) { if (x.parentNode) x.parentNode.removeChild(x); });
            t = kopya.textContent;
        }
        t = String(t || '').replace(/\s+/g, ' ').trim();
        if (t) return t;
    }
    return el.getAttribute('name') || el.id || 'field';
}

//: Makine girdi adının formdaki ekran etiketi; form alanı/etiketi yoksa
//: (ya da DOM'suz bağlamda) null döner ve çağıran eski metni basar.
function girdiEkranAdi(ad) {
    try {
        if (typeof document === 'undefined' || !document.getElementById) return null;
        const el = document.getElementById(ad);
        if (!el || typeof el.getAttribute !== 'function') return null;
        const t = alanEkranEtiketi(el);
        return (t && t !== ad) ? t : null;
    } catch (e) {
        return null;
    }
}

//: Sorunlu kutuyu işaretler (aria-invalid + sınıf); bir sonraki
//: doğrulamada temizlenir. Kod alanın değerine dokunmaz.
function alanHataliIsaretle(el) {
    try {
        el.setAttribute('aria-invalid', 'true');
        if (el.classList) el.classList.add('hd-alan-hatali');
    } catch (e) { /* DOM'suz bağlam */ }
}

function alanHataIsaretleriniTemizle() {
    if (typeof document === 'undefined' || !document.querySelectorAll) return;
    Array.prototype.forEach.call(
        document.querySelectorAll('.hd-alan-hatali'), function (el) {
            el.classList.remove('hd-alan-hatali');
            el.removeAttribute('aria-invalid');
        });
}

function declaredBoundsErrors() {
    const errors = [];
    alanHataIsaretleriniTemizle();
    if (typeof document === 'undefined' || !document.querySelectorAll) {
        return errors;
    }
    const alanlar = document.querySelectorAll('input[type="number"]');
    for (let i = 0; i < alanlar.length; i++) {
        const el = alanlar[i];
        if (el.disabled) continue;
        // Görünmeyen (kapalı sekme / gizli blok) alanın beyanı bu koşumda
        // uygulanmaz: kullanıcı onu görmüyor, gövdeye de girmiyor.
        if (el.offsetParent === null && el.type !== 'hidden'
            && typeof el.offsetParent !== 'undefined') continue;
        const ham = (el.value == null) ? '' : String(el.value).trim();
        if (ham === '') continue;
        const v = parseFloat(ham);
        if (!Number.isFinite(v)) continue;
        const ad = alanEkranEtiketi(el);
        const alt = el.getAttribute('min');
        const ust = el.getAttribute('max');
        if (alt !== null && alt !== '' && Number.isFinite(parseFloat(alt))
                && v < parseFloat(alt)) {
            alanHataliIsaretle(el);
            errors.push(TF('app.val.belowDeclaredMin',
                { field: ad, value: v, min: alt },
                '{field} = {value} is below the minimum this form declares '
                + 'on screen ({min}). The request was not sent.'));
        }
        if (ust !== null && ust !== '' && Number.isFinite(parseFloat(ust))
                && v > parseFloat(ust)) {
            alanHataliIsaretle(el);
            errors.push(TF('app.val.aboveDeclaredMax',
                { field: ad, value: v, max: ust },
                '{field} = {value} is above the maximum this form declares '
                + 'on screen ({max}). The request was not sent.'));
        }
    }
    return errors;
}

// Validate inputs
function validateInputs(data) {
    const errors = [];
    // Hesabı ENGELLEMEYEN tavsiyeler (OH-D27-01): hüküm ile öğüt ayrı
    // kanallardır. Öğüt `errors`e konursa sağlıklı tasarım reddedilir.
    const advisories = [];
    // Ekranda beyan edilen sınırlar ÖNCE uygulanır: kullanıcı kutunun
    // yanında yazan sayıya güvenerek yazıyor.
    Array.prototype.push.apply(errors, declaredBoundsErrors());
    
    // Check for NaN values
    Object.keys(data).forEach(key => {
        if (typeof data[key] === 'number' && (isNaN(data[key]) || !isFinite(data[key]))) {
            errors.push(TF('app.val.invalidValue',
                { field: key.replace('_', ' '), value: data[key] },
                '{field} has invalid value ({value})'));
        }
    });
    
    // V301/DİL (NK-22): aynı alan için ikinci ileti basılmaz — ekrandaki
    // alt sınır ihlali ("İtki = -100 … alt sınırın (1) altında") zaten
    // söylendiyse "İtki pozitif olmalı" tekrar etmez.
    const _thrustEl = (typeof document !== 'undefined' && document.getElementById)
        ? document.getElementById('thrust') : null;
    const _thrustIsaretli = !!(_thrustEl && _thrustEl.classList
        && _thrustEl.classList.contains('hd-alan-hatali'));
    if (data.thrust <= 0 && !_thrustIsaretli) {
        errors.push(T('app.val.thrustPositive', 'Thrust must be positive'));
    }
    if (data.burn_time <= 0) errors.push(T('app.val.burnPositive', 'Burn time must be positive'));
    if (data.of_ratio <= 0) errors.push(T('app.val.ofPositive', 'O/F ratio must be positive'));
    if (data.chamber_pressure <= 0) {
        errors.push(T('app.val.pcPositive', 'Chamber pressure must be positive'));
    }
    
    // Detailed tank pressure validation
    if (data.tank_pressure <= 0) {
        errors.push(T('app.val.tankPositive', 'Tank pressure must be positive'));
    } else if (data.tank_pressure <= data.chamber_pressure) {
        const minRequired = data.chamber_pressure * 1.2; // Minimum 20% higher
        errors.push(TF('app.val.tankTooLow',
            { tank: data.tank_pressure, pc: data.chamber_pressure, min: numTxt(minRequired, 1) },
            'Tank pressure ({tank} bar) must be higher than chamber pressure ({pc} bar). '
            + 'Minimum required: {min} bar'));
    } else if (data.tank_pressure < data.chamber_pressure * 1.2) {
        // ÖH D31 · arayuz-panel a3 — OH-D27-01 (kalemin ÖLÇÜLEN ayağı).
        //
        // Bu dal bir TAVSİYEDİR: metni de "Warning: ... should be ..." diyor
        // ve altındaki hüküm (tank <= hazne) ayrı dalda zaten reddediliyor.
        // Ama tavsiye `errors` dizisine konduğu için `validateInputs` false
        // dönüyor ve hesap "Input validation failed" başlığıyla TAMAMEN
        // ENGELLENİYORDU: %19 marjla çalışan sağlıklı bir tasarım ekranda
        // bir HATA olarak reddediliyor, kullanıcı hiçbir sayı alamıyordu.
        // ÖK-22 (sağlıklı envanter gevşetilemez) bu yönde ihlal ediliyordu.
        //
        // Tavsiye artık ENGELLEMEZ, susturulmaz da: aynı metin uyarı
        // kanalına (`showWarning` -> `showMessage`, sayfanın canlı sürümü)
        // basılır. Eşik BURADA yeni tanımlanmıyor — üstteki dalın kendi
        // 1,2 katsayısı, aynı ifade, ikinci kez yazılmadı.
        const minRecommended = data.chamber_pressure * 1.2;
        advisories.push(TF('app.val.tankMargin',
            { tank: data.tank_pressure, min: numTxt(minRecommended, 1) },
            'Warning: Tank pressure ({tank} bar) should be at least 20% higher than '
            + 'chamber pressure. Recommended minimum: {min} bar'));
    }
    
    // Additional range checks
    if (data.of_ratio > 20) errors.push(T('app.val.ofTooHigh', 'O/F ratio too high (max 20)'));
    if (data.chamber_pressure > 200) {
        errors.push(T('app.val.pcTooHigh', 'Chamber pressure too high (max 200 bar)'));
    }
    if (data.burn_time > 300) {
        errors.push(T('app.val.burnTooLong', 'Burn time too long (max 300 seconds)'));
    }
    
    // Chamber diameter check
    if (data.chamber_diameter_input > 0 && data.chamber_diameter_input < 10) {
        errors.push(T('app.val.dcTooSmall', 'Chamber diameter too small (min 10mm)'));
    }
    if (data.chamber_diameter_input > 1000) {
        errors.push(T('app.val.dcTooLarge', 'Chamber diameter too large (max 1000mm)'));
    }
    
    // Finite area combustion validation
    if (data.combustion_type === 'finite') {
        const hasContractionRatio = data.contraction_ratio && data.contraction_ratio > 0;
        const hasMassFlux = data.mass_flux_chamber && data.mass_flux_chamber > 0;
        
        if (hasContractionRatio && hasMassFlux) {
            errors.push(T('app.val.finiteBoth',
                'For finite area combustion, fill only ONE parameter: either contraction '
                + 'ratio OR mass flux chamber (not both)'));
        } else if (!hasContractionRatio && !hasMassFlux) {
            errors.push(T('app.val.finiteNone',
                'For finite area combustion, you must fill either contraction ratio '
                + 'OR mass flux chamber'));
        }
    }
    
    if (errors.length > 0) {
        // V301/DİL (kalem 3): sunucu reddindeki gibi önceki sonuç bu
        // girdilere ait değildir; gizlenir (invalidateStaleResults).
        if (typeof invalidateStaleResults === 'function') {
            try { invalidateStaleResults(); } catch (e) { /* panel yoksa */ }
        }
        showError(T('app.val.failed', 'Input validation failed:') + '\n• '
            + errors.join('\n• '));
        return false;
    }

    // Tavsiyeler hesabı durdurmaz; görünür kalır (susturmak da beyan
    // kaybı olurdu). Kanal sayfanın canlı `showMessage` sürümüdür.
    if (advisories.length > 0 && typeof showWarning === 'function') {
        try {
            showWarning(advisories.join(' • '));
        } catch (e) {
            /* uyarı kanalı yoksa hesap yine de engellenmez */
        }
    }

    return true;
}

// Display results
// V301/H-PANEL (NK-21/NK-22 ek): bir önceki BAŞARISIZ hesabın hata
// bildirimi, yeni ve başarılı bir sonuç basılırken kalkar — eski "HATA
// ALGILANDI" kutusu yeni sonuçların üstünde kalıp onları geçersiz
// gösteriyordu. Yalnız hata bildirimleri kaldırılır (bilgi iletileri durur).
function clearErrorNotices() {
    const kap = (typeof document !== 'undefined')
        ? document.getElementById('hrmaNotices') : null;
    if (!kap || typeof kap.querySelectorAll !== 'function') return 0;
    let n = 0;
    Array.prototype.forEach.call(
        kap.querySelectorAll('.hrma-notice[data-notice-type="error"]'),
        function (eski) {
            if (eski.parentNode) { eski.parentNode.removeChild(eski); n += 1; }
        });
    return n;
}

function displayCalculationResults(results) {
    try { clearErrorNotices(); } catch (e) { /* bildirim kabı yoksa */ }
    const resultsPanel = document.getElementById('resultsPanel');
    resultsPanel.style.display = 'block';
    resultsPanel.classList.add('fade-in');
    
    // Validate and fix injector diameter if needed
    validateAndFixInjectorDiameter(results);
    
    // Display performance metrics
    // İkinci argüman: yapısal kartın künyesi üst düzey `structural_design_basis`
    // bloğundan okunur (cidarı kim verdi / hüküm kazanıldı mı) — motor
    // sözlüğünde o blok YOK.
    displayPerformanceMetrics(results.motor, results);
    
    // Display plots
    displayPlots(results.plots);
    
    // Display design report
    displayDesignReport(results.motor, results.injector);
    
    // Display motor design table
    displayMotorTable(results.motor);
    
    // Display injector design table
    displayInjectorTable(results.injector);
    
    // Display warnings (motor tasarım uyarıları + enjektör + doğrulama özeti)
    //
    // v2.6.26: burada YALNIZ enjektör uyarıları gösteriliyordu. Hibrit motor
    // kendi tasarım uyarılarını (bilinmeyen kamara malzemesi, aralık dışı
    // cidar kalınlığı, ...) topluyor ama hiçbiri ekrana ulaşmıyordu.
    // Ölçüldü: chamber_material='ZIRVAAA' gönderilen istek HTTP 200 dönüyor,
    // sessizce steel_4130 kullanılıyor ve kullanıcı bunu asla göremiyordu.
    //
    // ÖH Z5-A (P14M3-04): kaynak listesi artık collectResultWarnings'te —
    // dil değişimi yolu (I18N.onChange) burayı KOPYALAMIYOR, aynı toplayıcıyı
    // çağırıyor. Eski hâlde o yol yalnız enjektör uyarılarını geçiriyordu ve
    // dil değiştiren kullanıcı motorun kritik uyarılarını kaybediyordu.
    displayWarnings(collectResultWarnings(results), results.validation);

    // v3.0.1 K kulvarı: veri kaynağı satırları + sonuçların SONUNDAKİ NASA
    // CEA karşılaştırması (sunucunun data_sources / cea_comparison blokları).
    displayCeaComparison(results);
    
    // Show export panel after successful calculation
    const exportPanel = document.getElementById('exportActionsPanel');
    if (exportPanel) {
        exportPanel.style.display = 'block';
    }

    // Analysis Dock önerilerini en güncel sonuçla tazele (dock yüklüyse).
    // Kullanıcının elle değiştirdiği alanlar (data-dirty) ezilmez.
    if (window.AnalysisDock && typeof AnalysisDock.refreshSuggestions === 'function') {
        AnalysisDock.refreshSuggestions();
    }
}

// v3.0.1 K kulvarı (Ayberk tur 1) — NASA CEA KARŞILAŞTIRMASI + VERİ KAYNAĞI.
// Sunucu /calculate yanıtına iki danışma bloğu ekler: `data_sources` (bu
// koşumun gerçekten kullandığı kaynakların künyesi) ve `cea_comparison`
// (aynı Pc, O/F, ε ve aynı itici tanımıyla RocketCEA/NASA CEA ⟷ HRMA teorik
// değerleri). Çizim sayfanın kendi işlevindedir (advanced.html
// applyRunSources): metinler o sayfanın sözlüğündedir (i18n_advanced.js) ve
// sözlüğün ölü-anahtar bekçisi yalnız o şablonu tarar. Sayfa çizimi
// tanımlamıyorsa hiçbir şey basılmaz (uydurma tablo yok).
function displayCeaComparison(results) {
    if (typeof applyRunSources !== 'function') return;
    try {
        applyRunSources(results);
    } catch (e) {
        // Danışma katmanı tasarım sonucunun gösterimini DÜŞÜREMEZ.
        console.warn('CEA comparison / data source rendering failed:', e);
    }
}

// Validate and fix injector diameter
/* v2.6.26 — TARAYICI ARTIK ÇÖZÜCÜNÜN SONUCUNU DEĞİŞTİRMİYOR.
 *
 * Bu fonksiyon adı gibi davranıyordu: enjektör geometrisi kamaraya sığmıyorsa
 * çözücünün ürettiği sayıları YENİDEN YAZIYORDU. İki ayrı zarar veriyordu:
 *
 *  1. Delik çapı yeniden yazılıyor ama `injection_area`, `exit_velocity` ve
 *     `reynolds_number` güncellenmiyordu. Sonuç tablosu kendi içinde
 *     tutarsız kalıyordu: n x pi/4 x d^2 artık raporlanan alanı vermiyordu.
 *     Kullanıcı bu çapı delerse hedef debiyi tutturamaz.
 *  2. `injector_diameter` alanı yoksa kamara çapının %80'i UYDURULUYORDU.
 *     Hesaplanmamış bir ölçü, hesaplanmış gibi ekrana ve dışa aktarıma
 *     giriyordu.
 *
 * Geometrik çelişki gerçek bir TASARIM sorunudur; görüntüleme katmanının
 * sessizce "düzeltebileceği" bir şey değildir. Artık sayılar olduğu gibi
 * korunur ve çelişki UYARI olarak bildirilir — kullanıcı neyin uymadığını
 * görür, hangi sayının gerçek olduğunu bilir.
 */
function validateAndFixInjectorDiameter(results) {
    if (!results || !results.injector || !results.motor) return;
    const chamberDiameter = results.motor.chamber_diameter * 1000; // mm
    if (!isFinite(chamberDiameter) || chamberDiameter <= 0) return;

    const warn = (msg) => {
        if (!results.injector.warnings) results.injector.warnings = [];
        results.injector.warnings.push(msg);
    };

    // V301/E1: gövde dış çapı verilmediyse null gelir (boyutlandırılmadı);
    // denetim yalnız sonlu-pozitif bir çapta yapılır (null > x hükmü yok).
    if (results.injector.type === 'pintle'
            && isFiniteNum(results.injector.outer_diameter)
            && results.injector.outer_diameter > 0) {
        if (results.injector.outer_diameter > chamberDiameter * 0.9) {
            warn(T('app.warn.injectorTooWide',
                   'Injector outer diameter does not fit the chamber')
                 + ` (${numTxt(results.injector.outer_diameter, 1)} mm > 90% of `
                 + `${numTxt(chamberDiameter, 1)} mm). Increase the chamber `
                 + `diameter or reduce the injector; the reported values are `
                 + `the solver's and were not adjusted.`);
        }
    }

    if (results.injector.type === 'showerhead') {
        // Kaba yerleşim kontrolü: kare dizilimde delik alanının kapladığı
        // yaklaşık çap. Bu bir TAHMİN, çözüm değil; yalnız uyarı üretir.
        //
        // ÖH D25 / P11B2-12 — FAIL-CLOSED. Eskiden delik sayısı ve delik
        // çapı için `|| 1` yedeği vardı: çözücü bu iki alanı vermediğinde
        // 1 delik / 1 mm varsayılıyor, uyarı metnine `~3.0 mm` gibi
        // UYDURULMUŞ bir çap yazılıyordu. Alan yoksa kontrol hiç yapılmaz;
        // ekrana geçersiz bir sayı çıkmasındansa uyarının hiç çıkmaması
        // yeğdir (gerçek geometri zaten çözücünün tablosunda görünür).
        const nHoles = results.injector.n_holes;
        const holeDia = results.injector.hole_diameter;
        if (isFiniteNum(nHoles) && nHoles > 0
            && isFiniteNum(holeDia) && holeDia > 0) {
            const effectiveDiameter = Math.sqrt(nHoles) * holeDia * 3;
            if (effectiveDiameter > chamberDiameter * 0.9) {
                warn(T('app.warn.holePatternTooWide',
                       'Hole pattern does not fit the chamber face')
                     + ` (~${numTxt(effectiveDiameter, 1)} mm > 90% of `
                     + `${numTxt(chamberDiameter, 1)} mm). Reduce the hole count or `
                     + `increase the chamber diameter; the reported hole geometry `
                     + `is the solver's and was not adjusted.`);
            }
        }
    }
    // 'injector_diameter' UYDURULMAZ: çözücü vermiyorsa alan boş kalır ve
    // gösterim katmanı "bildirilmedi" der.
}

// HTML gövdesine giren SUNUCU metni için kaçış (künye/gerekçe satırları
// sunucunun kendi cümleleridir, şablona ham gömülmez).
function hdEscape(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ÖH D36 · OH-P-05 — KÜNYE SIKIŞMAZ, SÖZCÜK İÇİNDEN KIRILMAZ.
// ÖLÇÜLDÜ (D34 piksel turu r03; a1/once.json P05): dar "YAPISAL ASGARİ EK"
// kartında künye tek paragrafta " · " ile akıyor ve "minimum_earned_safe /
// ty_factor" diye harf ortasından bölünüyordu (results_hud.css
// `overflow-wrap:anywhere`, alan adı boşluksuz tek belirteç). Onarım: her
// künye öğesi kendi satırında durur (satır kaydırma), alan adı KISALTILMAZ
// (kanondur). Satıra sığmayan uzun alan adlarında kırma fırsatı YALNIZ alt
// çizgilerdedir (<wbr>); eşikten kısa adlar dokunulmadan kalır. Eşik kabın
// genişliğinden: ölçülen .hd-metric-note 113-135 px (0,66rem eş aralıklı
// ~6,5 px/karakter -> ~17-20 karakter), .hd-verdict-kunye 830-1370 px.
// Metin hdEscape'ten geçer.
const KUNYE_KIRMA_ESIGI = 30;          // geniş şerit (hd-verdict-kunye)
const KUNYE_DAR_KART_ESIGI = 16;       // dar ölçü kartı (hd-metric-note)
function kunyeSarmaHtml(metin, esik) {
    const sinir = (typeof esik === 'number' && esik > 0) ? esik : KUNYE_KIRMA_ESIGI;
    return String(metin == null ? '' : metin).split(' \u00b7 ').map(function (oge) {
        const govde = hdEscape(oge).replace(/[A-Za-z0-9_]+/g, function (belirtec) {
            return (belirtec.length > sinir && belirtec.indexOf('_') >= 0)
                ? belirtec.replace(/_/g, '_<wbr>') : belirtec;
        });
        // Sınıf yok: öğe, sarma kuralı taşıyan kabın (.hd-metric-note /
        // .hd-verdict-kunye) içinde durur ve kuralı ondan miras alır.
        return '<span style="display:block">' + govde + '</span>';
    }).join('');
}

// ÖH Z5-A / P11B2-01 (KRİTİK) + OH-Z2-07 —— YAPISAL HÜKÜM ŞERİDİ.
//
// ÖLÇÜLEN KUSUR (hibrit varsayılan koşum, 1 kN / 20 bar / N2O-HTPB):
// /calculate yanıtı `status: 'UNSAFE'`, `risk_level: 'HIGH'` ve YEDİ
// adlandırılmış onarım önerisi (warn.structural.increase_wall_thickness,
// ...higher_strength_material, ...increase_chamber_wall,
// ...thermal_stress_dominates, ...thin_wall_invalid, ...severe_derating,
// ...thermal_margin_service_limit) taşıyordu. Ana sonuç ekranına bunlardan
// HİÇBİRİ inmiyordu: geriye kalan tek iz "Min SF 1,69" kartı ve metnin
// rengiydi. Aynı yanıttaki `structural_design_basis` künyesinin de ekranda
// tüketicisi yoktu (yalnız kartın title ipucunda görünüyordu).
//
// FAIL-CLOSED: yalnız yanıtta GERÇEKTEN duran alanlar basılır. Alan yoksa o
// satır hiç konmaz; şeridin tamamı boş kalırsa şerit de basılmaz. Hüküm
// metni, gerekçe ve öneri metinleri SUNUCUNUN kendi kayıtlarıdır — burada
// yeniden yazılmaz, eşik hesaplanmaz, yeni sınıflandırma icat edilmez.
function structuralVerdictBlock(motorData, results) {
    const sf = (motorData && motorData.structural_analysis
                && motorData.structural_analysis.safety_analysis) || null;
    const dbasis = (results && results.structural_design_basis) || null;
    if (!sf && !dbasis) return '';

    const RED = 'var(--hd-red, #ff5d73)';
    const AMBER = 'var(--hd-orange, #ff8c33)';
    const GREEN = 'var(--hd-green, #2dd4a8)';
    const CYAN = 'var(--hd-cyan, #00e5ff)';
    const DIM = 'var(--hd-ink-dim, #7d97a5)';
    // Renk sunucunun kendi durum dizesinden türer; eşik burada hesaplanmaz.
    const statusColor = (s) => {
        const u = String(s || '').toUpperCase();
        if (u === 'UNSAFE' || u === 'CRITICAL' || u === 'HIGH') return RED;
        if (u === 'MARGINAL' || u === 'MEDIUM') return AMBER;
        if (u === 'SAFE' || u === 'LOW' || u === 'ACCEPTABLE') return GREEN;
        return DIM;
    };
    const badge = (text, color) =>
        `<span class="hd-verdict-badge" style="display:inline-block;
            font-family:var(--hd-mono); font-size:0.7rem; font-weight:700;
            letter-spacing:0.04em; padding:3px 8px; margin:0 6px 6px 0;
            border:1px solid ${color}; border-radius:3px; color:${color};"
            >${hdEscape(text)}</span>`;

    let badges = '';
    // 1) Hüküm. Sunucu hükmü GERİ ÇEKTİYSE (verdict_withheld) bunu önce
    //    söyleriz; ama kalan UNSAFE/MARGINAL bir TEHLİKE BİLDİRİMİDİR ve
    //    bastırılmaz (uçun kendi verdict_basis metni bunu yazıyor).
    const withheld = !!(sf && sf.verdict_withheld === true)
        || !!(dbasis && String(dbasis.verdict || '') === 'withheld');
    if (sf && sf.status) {
        badges += badge(T('panel.structural.badgeStructure', 'STRUCTURE')
                        + ': ' + sf.status, statusColor(sf.status));
    }
    if (sf && sf.risk_level) {
        badges += badge(T('common.risk', 'RISK') + ': ' + sf.risk_level,
                        statusColor(sf.risk_level));
    }
    if (withheld) {
        badges += badge(T('panel.structural.verdictWithheld', 'VERDICT WITHHELD'),
                        AMBER);
    } else if (dbasis && String(dbasis.verdict || '') === 'issued') {
        // Fable Z5 denetimi ŞART 1: "hüküm üretildi" bir SÜREÇ durumudur,
        // GEÇME değil — nötr ton alır (C2/P17B2-11 ile aynı anlambilim).
        // Yeşil YALNIZ "geçti" demektir.
        badges += badge(T('panel.structural.verdictIssued', 'VERDICT ISSUED'),
                        CYAN);
    }
    // ÖH D28 · OH-D26-21 — HÜKMÜN SONUCU DA SÖYLENİR (H1-Y3 panel ayağı).
    // ÖLÇÜLDÜ (a2/once.json `OH-D26-21`): uç `_carry_structural_verdict_outcome`
    // (app.py:18548) ile beyan bloğuna dört alan TAŞIYOR —
    // `verdict_outcome` / `verdict_risk_level` / `verdict_safety_factor` /
    // `verdict_outcome_source` — ve arayüzde bunların tüketicisi 0'dı.
    // Sonuç: `wall_thickness: 1` mm ile koşulan bir tasarımda ekran
    // "VERDICT ISSUED" rozetini basıyor, ama taşınan sonucun UNSAFE / HIGH
    // olduğunu SÖYLEMİYORDU. Rozet YALNIZ modül katmanı aynı şeyi zaten
    // söylemiyorsa eklenir (aynı hüküm iki kez basılmasın); renk sunucunun
    // kendi durum dizesinden türer, burada eşik hesaplanmaz.
    if (dbasis && dbasis.verdict_outcome
        && !(sf && sf.status && String(sf.status).toUpperCase()
             === String(dbasis.verdict_outcome).toUpperCase())) {
        badges += badge(T('panel.structural.badgeVerdictOutcome', 'VERDICT OUTCOME')
                        + ': ' + dbasis.verdict_outcome,
                        statusColor(dbasis.verdict_outcome));
    }
    if (dbasis && dbasis.verdict_risk_level
        && !(sf && sf.risk_level && String(sf.risk_level).toUpperCase()
             === String(dbasis.verdict_risk_level).toUpperCase())) {
        badges += badge(T('common.risk', 'RISK') + ': '
                        + dbasis.verdict_risk_level,
                        statusColor(dbasis.verdict_risk_level));
    }

    // 2) Künye satırı — makine adlarıyla, Z4'ün künye deseni. Çeviri anahtarı
    //    AÇILMAZ: bunlar alan adresleridir, kullanıcı metni değil.
    const kunye = [];
    if (sf && Array.isArray(sf.verdict_scope) && sf.verdict_scope.length) {
        kunye.push('verdict_scope: ' + sf.verdict_scope.join(', '));
    }
    if (sf && Array.isArray(sf.verdict_withheld_reasons)
        && sf.verdict_withheld_reasons.length) {
        kunye.push('verdict_withheld_reasons: '
                   + sf.verdict_withheld_reasons.join(', '));
    }
    // Ölçülmüş kapsam ile kazanılmış kapsam hükmü AYRIŞIYORSA (Z4 kanalı)
    // ikisi de basılır; özdeşse tekrar edilmez.
    if (sf && sf.measured_scope_status && sf.status
        && sf.measured_scope_status !== sf.status) {
        kunye.push('measured_scope_status: ' + sf.measured_scope_status);
    }
    if (sf && sf.earned_scope_status && sf.status
        && sf.earned_scope_status !== sf.status) {
        kunye.push('earned_scope_status: ' + sf.earned_scope_status);
    }
    if (dbasis) {
        // OH-Z2-07: künyenin ekrandaki İLK tüketicisi. Alanlar sunucudan
        // olduğu gibi; olmayan alan satıra girmez.
        ['design_mode', 'wall_thickness_source', 'wall_thickness_input_status',
         'chamber_material_source', 'thermal_input', 'wall_temperature_source'
        ].forEach(function (k) {
            if (dbasis[k] !== undefined && dbasis[k] !== null && dbasis[k] !== '') {
                kunye.push(k + ': ' + dbasis[k]);
            }
        });
        if (typeof dbasis.is_verification === 'boolean') {
            kunye.push('is_verification: ' + dbasis.is_verification
                       + (dbasis.is_verification_scope
                          ? ' (' + dbasis.is_verification_scope + ')' : ''));
        }
        if (typeof dbasis.verification_scope_complete === 'boolean') {
            kunye.push('verification_scope_complete: '
                       + dbasis.verification_scope_complete);
        }
        if (Array.isArray(dbasis.stations_not_verified)
            && dbasis.stations_not_verified.length) {
            kunye.push('stations_not_verified: '
                       + dbasis.stations_not_verified.join(', '));
        }
        if (Array.isArray(dbasis.not_evaluated) && dbasis.not_evaluated.length) {
            kunye.push('not_evaluated: ' + dbasis.not_evaluated.join(', '));
        }
        // OH-D26-21: taşınan hüküm sonucunun künyesi. `verdict_outcome_source`
        // hükmü KİMİN verdiğini söyler ('not_published_by_module' hâli dâhil);
        // sayı burada yeniden notlanmaz, sunucunun kendi dizesi basılır.
        ['verdict_outcome', 'verdict_risk_level', 'verdict_outcome_source'
        ].forEach(function (k) {
            if (dbasis[k] !== undefined && dbasis[k] !== null && dbasis[k] !== '') {
                kunye.push(k + ': ' + dbasis[k]);
            }
        });
        if (typeof dbasis.verdict_safety_factor === 'number'
            && isFinite(dbasis.verdict_safety_factor)) {
            // Ekran basamağı: app.js `gateNumberText` ile BİREBİR aynı üç
            // satır (o yardımcı `collectResultWarnings` içinde kapalıdır,
            // buradan görünmez; kural tek kaynaktan KOPYALANIR, yeni bir
            // yuvarlama icat edilmez).
            const _vsf = dbasis.verdict_safety_factor;
            // ÖH D36 · OH-P-11: basamak kuralı aynı; ayraç TR'de virgül
            // (I18N.decimalText, tek kaynak). Makine kanalı etkilenmez.
            const _vsfMetin = Number.isInteger(_vsf)
                ? String(_vsf) : String(parseFloat(_vsf.toPrecision(6)));
            kunye.push('verdict_safety_factor: '
                       + ((typeof window !== 'undefined' && window.I18N
                           && typeof window.I18N.decimalText === 'function')
                          ? window.I18N.decimalText(_vsfMetin) : _vsfMetin));
        }
    }

    // 3) Gerekçe metinleri — sunucu yazar, ekran yeniden yazmaz.
    const gerekce = [];
    if (dbasis && dbasis.message) gerekce.push(dbasis.message);
    if (sf && sf.verdict_basis) gerekce.push(sf.verdict_basis);
    if (sf && sf.minimum_safety_factor_verdict_basis
        && gerekce.indexOf(sf.minimum_safety_factor_verdict_basis) === -1) {
        gerekce.push(sf.minimum_safety_factor_verdict_basis);
    }

    // 4) Adlandırılmış onarım önerileri. Kayıtlar {code, params, severity};
    //    metin ortak çeviriciden geçer (uyarı paneliyle aynı kaynak).
    const recs = (sf && Array.isArray(sf.recommendations))
        ? sf.recommendations : [];

    if (!badges && !kunye.length && !gerekce.length && !recs.length) return '';

    let html = `<div id="structuralVerdictStrip" class="hd-verdict-strip"
        style="margin-top:14px; padding:10px 12px; border-radius:4px;
        border:1px solid color-mix(in srgb, ${DIM} 35%, transparent);">`;
    if (badges) html += `<div>${badges}</div>`;
    if (kunye.length) {
        // V301/DİL (NK-4): künye MAKİNE alanlarıdır (`design_mode: size`,
        // `wall_thickness_source: sized_by_hrma` …) — ölçüldü: TR ekranda
        // 12 ham satır. Kullanıcıya hüküm rozetleri ve aşağıdaki gerekçe
        // cümleleri konuşur; künye kapalı "teknik ayrıntı" bölümünde durur.
        html += `<details class="hd-teknik-ayrinti" style="margin-top:2px;">
            <summary style="cursor:pointer; font-size:0.7rem; color:${DIM};">${
            hdEscape(T('common.techDetail', 'Technical detail (machine fields)'))}</summary>
            <div class="hd-verdict-kunye" style="font-family:var(--hd-mono);
            font-size:0.66rem; letter-spacing:0.02em; color:${DIM};
            margin-top:2px;">${kunyeSarmaHtml(kunye.join(' · '))}</div></details>`;
    }
    // OH-Z4-04: gerekçe cümleleri HAM basılıyordu — Türkçe kipte İngilizce
    // kalıyorlardı. Z5 i18n süpürmesi `minimum_safety_factor_verdict_basis`in
    // dört dalını i18n_charts.js MSG_PATTERNS'e yazmıştı; kanal vardı, kapı
    // yoktu. Tekilleştirme HAM metin üstünden yapılır (çeviri iki ayrı
    // İngilizce cümleyi aynı Türkçeye indirebilir), çeviri yalnız basımda.
    gerekce.forEach(function (t) {
        html += `<p style="font-size:0.78rem; margin:6px 0 0; color:${DIM};"
            >${hdEscape(SRV(t))}</p>`;
    });
    if (recs.length) {
        html += `<div class="hd-verdict-recs" style="margin-top:8px;">
            <div style="font-size:0.74rem; font-weight:600; color:${DIM};"
            >${hdEscape(T('common.recommendations', 'Recommendations'))}</div>
            <ul style="margin:4px 0 0 18px; padding:0; font-size:0.78rem;
                color:${DIM};">`;
        recs.forEach(function (r) {
            const metin = warnToText(r);
            if (!metin) return;
            html += `<li style="margin:2px 0; color:${
                warnIsCritical(r) ? RED : DIM};">${hdEscape(metin)}</li>`;
        });
        html += '</ul></div>';
    }
    html += '</div>';
    return html;
}

// ÖH D25 / P11B2-13 — "HANGİ GİRDİ VARSAYILANA DÜŞTÜ" BEYANI EKRANDA.
//
// ÖLÇÜLDÜ (docs/scofield/raw/OH/D25/arayuz/a2/once.json): çözücü bu beyanı
// ÜÇ yerde birden yayımlıyor — `motor.defaults_used`, `motor.fallbacks_used`
// ve `motor.design_summary.defaults_used/fallbacks_used` — ama app.js
// dosyasında `defaults_used` dizesi HİÇ GEÇMİYORDU (ölçülen geçiş sayısı 0).
// Yani kullanıcı, itkisini/yanma süresini/oda basıncını vermediğinde ürünün
// onun yerine bir sayı SEÇTİĞİNİ ekranda hiçbir yerden öğrenemiyordu; kartlar
// o sayıyı kullanıcının kendi tasarımıymış gibi gösteriyordu.
//
// Beyan ÇÖZÜM DEĞİLDİR, ama bu kalemde yapılacak iş beyanın kendisidir:
// çözücünün KENDİ listesi yazılır; burada sınıflandırma üretilmez, sayı
// uydurulmaz, liste boşsa hiçbir şerit basılmaz (boş şerit de bir iddiadır).
function defaultsDeclarationBlock(motorData, results) {
    const md = motorData || {};
    const r = results || {};
    const ds = md.design_summary || {};
    const birlestir = function (a, b) {
        const out = [];
        [a, b].forEach(function (liste) {
            if (!Array.isArray(liste)) return;
            liste.forEach(function (x) {
                const t = (typeof x === 'string') ? x
                    : (x && (x.field || x.name || x.message)) ? String(x.field
                        || x.name || x.message) : '';
                if (t && out.indexOf(t) === -1) out.push(t);
            });
        });
        return out;
    };
    const varsayilan = birlestir(md.defaults_used || r.defaults_used,
                                 ds.defaults_used);
    const yedek = birlestir(md.fallbacks_used || r.fallbacks_used,
                            ds.fallbacks_used);
    if (varsayilan.length === 0 && yedek.length === 0) return '';
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    // Adlar MAKİNE ADIdır; sunucu-metni çeviri kanalından geçirilir
    // (eşleşme yoksa ad aynen kalır — uydurma çeviri yapılmaz).
    const satir = function (baslik, liste, renk) {
        if (!liste.length) return '';
        return `<div style="font-family:var(--hd-mono, monospace);
             font-size:0.68rem; letter-spacing:0.04em; margin-top:4px;
             color:${renk};"><strong>${esc(baslik)}</strong> ${
            liste.map(function (x) {
                // V301/DİL (kalem 2): girdi adı formdaki ETİKETİYLE okunur
                // (ölçüldü: TR'de `nozzle_material`, `tank_pressure` …);
                // makine adı title/data-field'da kalır. Formda karşılığı
                // olmayan ad sunucu-metni kanalından geçer (eski davranış).
                const ad = girdiEkranAdi(x) || SRV(x);
                return `<span data-field="${esc(x)}" title="${esc(x)}">${esc(ad)}</span>`;
            }).join(' · ')}</div>`;
    };
    return `<div class="hd-defaults-note" data-defaults-count="${
        varsayilan.length}" data-fallbacks-count="${yedek.length}"
         style="margin-top:10px; padding:6px 8px; border-radius:6px;
         border:1px solid var(--hd-orange, #ff8c33);">`
        + satir(T('app.defaults.title',
                  'INPUTS THE SOLVER SUPPLIED (not entered by you):'),
                varsayilan, 'var(--hd-orange, #ff8c33)')
        + satir(T('app.fallbacks.title',
                  'QUANTITIES THAT FELL BACK TO A SUBSTITUTE MODEL OR TABLE:'),
                yedek, 'var(--hd-orange, #ff8c33)')
        + '</div>';
}

// ==================================================================
// ÖH D37 A1a · CW-A4E6 (hibrit) — `defaults_applied` KÜNYESİ EKRANDA
// ==================================================================
// ÖLÇÜLDÜ (docs/scofield/raw/OH/A1a/hibrit-beyan/a1/once.json M1,
// Ornek-H1 canlı): `/calculate` yanıtının ÜST DÜZEY `defaults_applied`
// listesi 7 kayıt taşıyordu (cooling_channels, l_star = 1 m,
// hole_diameter_min = 0,3 mm, hole_diameter_max = 2 mm, ...) ama
// ekranda 0 satır vardı; `defaultsDeclarationBlock` yalnız MOTORUN
// `defaults_used` / `fallbacks_used` listelerini okuyor. Kullanıcı
// L* = 1,0 m'nin kendi seçimi olmadığını hiçbir yerden öğrenemiyordu.
//
// Liste ELLE YAZILMAZ: yalnız sunucunun kendi listesi basılır; her
// satır alan adını (makine adı), sunucunun uyguladığı değeri ve
// gerekçesini taşır. `not_supplied_solver_derives` kaydında `value`
// (0) bir "türet" işaretidir, uygulanmış bir sayı DEĞİLDİR — o yüzden
// sayı basılmaz, çözücünün türettiği yazılır. Tanınmayan gerekçe
// makine koduyla basılır (çeviri uydurulmaz). Liste boşsa blok yok.
function defaultsAppliedBlock(results) {
    const liste = (results && Array.isArray(results.defaults_applied))
        ? results.defaults_applied : [];
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    const satirlar = [];
    liste.forEach(function (k) {
        const kayit = (k && typeof k === 'object') ? k : {};
        const alan = (typeof k === 'string') ? k
            : (typeof kayit.field === 'string' ? kayit.field : '');
        if (!alan) return;
        const neden = (typeof kayit.reason === 'string') ? kayit.reason : '';
        let deger = '';
        let aciklama = '';
        if (neden === 'not_supplied_solver_derives') {
            aciklama = T('app.defaultsApplied.solverDerives',
                'not supplied: the solver derives it itself (no value assumed)');
        } else {
            if (typeof kayit.value === 'number' && isFinite(kayit.value)) {
                const birim = (kayit.unit && kayit.unit !== 'dimensionless')
                    ? kayit.unit : '';
                deger = unitTxt(kayit.value, birim);
            } else if (kayit.value !== undefined && kayit.value !== null) {
                deger = String(kayit.value);
            }
            aciklama = (neden === 'not_supplied')
                ? T('app.defaultsApplied.serverDefault',
                    'not supplied: this server applied its own default; the result describes that assumption, not your design')
                : neden;
            // ÖH D37 A2 hibrit · 10. tur (HB9 devir 44): sunucu kaydı
            // ``applied: false`` diyorsa (N₂O doyma kipinde tank_pressure
            // yedeği; app.py ``_n2o_doyma_tank_kunyesi``) satır "uyguladı"
            // DEMEZ — API beyanıyla çelişki yok. Model sayısı kaydın kendi
            // ``used_by_model`` alanından (sonlu değilse sayı basılmaz).
            if (kayit.applied === false) {
                const kullanilan = (typeof kayit.used_by_model === 'number'
                    && isFinite(kayit.used_by_model))
                    ? unitTxt(kayit.used_by_model,
                              (kayit.unit && kayit.unit !== 'dimensionless')
                                  ? kayit.unit : '')
                    : '';
                if (kullanilan && kayit.used_by_model_source
                        === 'n2o_saturation_at_tank_temperature') {
                    aciklama = TF('app.defaultsApplied.notUsedN2oSat',
                        { used: kullanilan },
                        'listed as this server\'s default but NOT used in this run: the model used P_sat(T_tank) = {used} from the N₂O saturation table');
                } else if (kullanilan) {
                    aciklama = TF('app.defaultsApplied.notUsedValue',
                        { used: kullanilan },
                        'listed as this server\'s default but NOT used in this run: the model used {used}');
                } else {
                    aciklama = T('app.defaultsApplied.notUsed',
                        'listed as this server\'s default but NOT used in this run');
                }
            }
        }
        satirlar.push(`<div class="hd-defaults-applied-row"
             data-defaults-applied-field="${esc(alan)}"
             style="margin-top:3px;">${girdiEkranAdi(alan)
                ? '<span title="' + esc(alan) + '">' + esc(girdiEkranAdi(alan)) + '</span>'
                : '<code>' + esc(alan) + '</code>'}${
            deger ? ' = <strong>' + esc(deger) + '</strong>' : ''} — ${
            esc(aciklama)}</div>`);
    });
    // Kitap uyum B16, 3. tur (Ş-5; karar §28-18 "açık varsayım olarak
    // beyan"): hibrit sonucun N₂O giriş durumu panelde TEK SATIRLA yazılır.
    // Satır motorun KENDİ beyanından okunur (results.motor.
    // oxidizer_inlet_state: sıcaklık, faz, alanların kaynağı); beyan yoksa
    // ya da tanınmıyorsa satır HİÇ çizilmez (sayı uydurulmaz). Kaynak
    // sözcüğü beyanın alan kaynaklarından: 'user input' → girdiniz, aksi
    // hâlde varsayım. 'gas' fazında sıcaklık uygulanmaz; beyanın yazdığı
    // standart hâl sıcaklığı basılır. Künye satırlarından AYRI bir sınıf
    // taşır (o listenin sayımı ve başlığı değişmez).
    const GIRIS_T_ONDALIK = 2;
    let girisSatiri = '';
    const giris = (results && results.motor && typeof results.motor === 'object')
        ? results.motor.oxidizer_inlet_state : null;
    if (giris && typeof giris === 'object' && giris.oxidizer === 'n2o'
            && (giris.phase === 'liquid' || giris.phase === 'gas')
            && typeof giris.temperature_K === 'number'
            && isFinite(giris.temperature_K)) {
        const kullanici = function (kaynak) {
            return typeof kaynak === 'string' && kaynak.indexOf('user input') === 0;
        };
        const kaynakSozcugu = function (k) {
            return k ? T('app.oxInlet.entered', 'your input')
                : T('app.oxInlet.assumed', 'assumption');
        };
        const sivi = giris.phase === 'liquid';
        const tKul = kullanici(giris.inlet_temperature_source);
        const fKul = kullanici(giris.inlet_phase_source);
        let kaynak;
        if (!sivi || tKul === fKul) {
            kaynak = kaynakSozcugu(sivi ? tKul : fKul);
        } else {
            kaynak = TF('app.oxInlet.tempSource', { src: kaynakSozcugu(tKul) },
                        'temperature: {src}')
                + '; ' + TF('app.oxInlet.phaseSource',
                            { src: kaynakSozcugu(fKul) }, 'phase: {src}');
        }
        if (sivi) {
            kaynak += '; ' + T('app.oxInlet.refLiquid', 'RP-1311 §4.1');
        }
        const fazMetni = sivi
            ? T('app.oxInlet.liquid', 'saturated liquid')
            : T('app.oxInlet.gas', 'ideal gas, standard state');
        girisSatiri = `<div class="hd-oxidizer-inlet-line"
             data-oxidizer-inlet-phase="${esc(giris.phase)}"
             data-oxidizer-inlet-temperature-k="${esc(giris.temperature_K)}"
             style="margin-top:10px; font-family:var(--hd-mono, monospace);
             font-size:0.68rem; letter-spacing:0.02em;">${
            esc(T('app.oxInlet.label', 'N₂O inlet:'))} ${
            esc(unitTxt(giris.temperature_K, 'K', GIRIS_T_ONDALIK))} ${
            esc(fazMetni)} (${esc(kaynak)})</div>`;
    }
    if (!satirlar.length) return girisSatiri;
    return girisSatiri + `<div class="hd-defaults-applied" data-defaults-applied-count="${
        satirlar.length}" style="margin-top:10px; padding:6px 8px;
         border-radius:6px; border:1px solid var(--hd-orange, #ff8c33);
         font-family:var(--hd-mono, monospace); font-size:0.68rem;
         letter-spacing:0.02em; color:var(--hd-orange, #ff8c33);"><strong>${
        esc(T('app.defaultsApplied.title',
              'VALUES THIS RUN ASSUMED FOR FIELDS YOU LEFT EMPTY:'))}</strong>${
        satirlar.join('')}</div>`;
}

// ==================================================================
// ÖH D37 A1a · CW-B3 (ana zincir tarafı) — CİDAR SICAKLIĞI HANGİ SORUYU
// YANITLIYOR
// ==================================================================
// ÖLÇÜLDÜ (once.json M2, Ornek-H1): ana zincir cidar sıcaklığını
// (`heat_transfer_analysis.wall_analysis.max_temperature` = 3323 K)
// yalnız üç KRİTİK uyarı cümlesinde basıyordu; Termal FEA paneli aynı
// motor için 10 s sonundaki tepe cidarı (Cowork: 2724 K) veriyor. İki
// sayı arasında 600 K var ve ekran hangisinin hangi soruyu yanıtladığını
// söylemiyordu. Bu blok UZLAŞTIRMA DEĞİLDİR (o, A2 termalin
// `thermal_paths_reconciliation` bloğuyla gelir ve faz-c-1 bağlar);
// yalnız iki sayının SORUSUNU ve kaynağını yazar:
//   * ana zincir: denge (sürekli rejim) cidar sıcaklığı — yanma süresi
//     sonsuz kabulü, soğutma SINIFI sunucunun çözdüğü sınıf;
//   * Termal FEA: sonlu yanmanın sonundaki (geçici) tepe cidar sıcaklığı —
//     sayı yalnız panel BU sonuç için koşturulduysa basılır; koşulmadıysa
//     gri "koşulmadı" yazılır (sayı uydurulmaz, önceki koşumun sayısı
//     taşınmaz: panel yeni sonuçta kendi yükünü siler).
// Ana zincir sayısı yoksa blok hiç çizilmez (etiketlenecek sayı yok).
const WALL_T_FEA_SLOT = 'data-wall-t-fea';

// Sunucunun çözdüğü soğutma SINIFININ ekran adı. Sınıf kümesi motorun
// COOLING_GEOMETRY_EQUIVALENCE anahtarlarıdır (natural / forced /
// regenerative); tanınmayan sınıf makine adıyla basılır, yoksa
// "yayımlanmadı" yazılır (sınıf uydurulmaz).
function coolingClassText(sinif) {
    const SINIF_ANAHTARI = {
        natural: 'app.wallT.clsNatural',
        forced: 'app.wallT.clsForced',
        regenerative: 'app.wallT.clsRegenerative',
    };
    if (!(typeof sinif === 'string' && sinif)) {
        return T('app.wallT.clsUnpublished', 'not published');
    }
    return SINIF_ANAHTARI[sinif] ? T(SINIF_ANAHTARI[sinif], sinif) : sinif;
}

function wallTemperatureFeaSlotHtml() {
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const panel = (typeof window !== 'undefined') ? window.ThermalFeaPanel : null;
    const yuk = panel ? panel.payload : null;
    const sk = (yuk && yuk.status === 'ok' && yuk.scalars
                && typeof yuk.scalars === 'object') ? yuk.scalars : null;
    const tepe = sk ? sk.peak_wall_T_K : null;
    if (!(typeof tepe === 'number' && isFinite(tepe))) {
        return `<span style="color:var(--hd-ink-dim, #7d97a5);">${esc(T(
            'app.wallT.feaNotRun',
            'peak wall temperature at the end of a finite burn (transient): not run for this result; run the Thermal FEA panel to get it'))}</span>`;
    }
    const an = (typeof sk.peak_time_s === 'number' && isFinite(sk.peak_time_s))
        ? sk.peak_time_s : sk.burn_time_s;
    const soru = (typeof an === 'number' && isFinite(an))
        ? TF('app.wallT.feaQuestion',
             { t: numTxt(an, 2) },
             'peak wall temperature at t = {t} s (transient, finite burn)')
        : T('app.wallT.feaQuestionNoTime',
            'peak wall temperature of the transient run (finite burn)');
    return `${esc(soru)} → <strong>${esc(unitTxt(tepe, 'K', 0))}</strong>`
        + ` <span style="color:var(--hd-ink-dim, #7d97a5);">${
            esc(`/api/fea/thermal · scalars.peak_wall_T_K`)}</span>`;
}

function wallTemperatureQuestionsBlock(motorData) {
    const md = motorData || {};
    const wa = ((md.heat_transfer_analysis || {}).wall_analysis) || {};
    const tDenge = wa.max_temperature;
    if (!(typeof tDenge === 'number' && isFinite(tDenge))) return '';
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const sinif = (md.cooling_channel_geometry || {}).resolved_class;
    const sinifMetni = coolingClassText(sinif);
    const uzlastirmaYok = !md.thermal_paths_reconciliation;
    return `<div class="hd-wall-t-questions" data-wall-temperature-questions="1"
         style="margin-top:10px; padding:6px 8px; border-radius:6px;
         border:1px solid var(--hd-ink-dim, #7d97a5);
         font-family:var(--hd-mono, monospace); font-size:0.68rem;
         letter-spacing:0.02em;"><strong>${esc(T('app.wallT.title',
            'WALL TEMPERATURE: TWO RESULTS ANSWER TWO DIFFERENT QUESTIONS'))}</strong>
        <div style="margin-top:3px;"><strong>${esc(T('app.wallT.thisRun',
            'This result (main chain):'))}</strong> ${esc(TF('app.wallT.eqQuestion',
            { cls: sinifMetni },
            'equilibrium (steady-state) wall temperature, burn time taken as infinite, cooling class: {cls}'))}
            → <strong>${esc(unitTxt(tDenge, 'K', 0))}</strong>
            <span style="color:var(--hd-ink-dim, #7d97a5);">${
            esc(`/calculate · heat_transfer_analysis.wall_analysis.max_temperature`)}</span></div>
        <div style="margin-top:3px;"><strong>${esc(T('app.wallT.feaPanel',
            'Thermal FEA panel:'))}</strong> <span ${WALL_T_FEA_SLOT}="1">${
            wallTemperatureFeaSlotHtml()}</span></div>${
        uzlastirmaYok ? `
        <div style="margin-top:3px; color:var(--hd-ink-dim, #7d97a5);">${esc(T(
            'app.wallT.noReconciliation',
            'The two numbers answer different questions and are not expected to be equal; no reconciliation between them is published for this run.'))}</div>` : ''}
    </div>`;
}

// ==================================================================
// v3.0.1 (V301/H-termal) — KAMARA CİDARI ÜÇ BÖLGE
// ==================================================================
// Sunucu `chamber_wall_zones` bloğunu yayımlar (hybrid_rocket_engine
// `_chamber_wall_zones_block`): yakıt bloğu altı (yanma boyunca korunur,
// beyanlı), ön ve son yanma odası (HRMA'nın boyutlandırdığı astar ya da
// fail-closed çıplak cidar hükmü) ve yapı zincirinin kullandığı kasa
// sıcaklığı. Buradaki her sayı ve hüküm o bloktan okunur; ekranda eşik
// HESAPLANMAZ. Blok yoksa (eski sonuç) hiçbir şey çizilmez.
const ZONE_NAME_KEYS = {
    grain_section: ['app.zones.grain', 'Under the fuel grain'],
    pre_chamber: ['app.zones.pre', 'Pre-combustion chamber'],
    post_chamber: ['app.zones.post', 'Post-combustion chamber'],
};
const ZONE_VERDICT_KEYS = {
    PROTECTED_DURING_BURN: ['app.zones.vProtected', 'PROTECTED DURING BURN'],
    NOT_PROTECTED: ['app.zones.vNotProtected', 'NOT PROTECTED'],
    LINER_REQUIRED: ['app.zones.vLinerRequired', 'LINER REQUIRED'],
    BARE_WALL_CRITICAL: ['app.zones.vBareCritical', 'BARE WALL: CRITICAL'],
    BARE_WALL_WITHIN_LIMIT: ['app.zones.vBareOk', 'BARE WALL WITHIN LIMIT'],
    NOT_PRESENT: ['app.zones.vAbsent', 'NOT PRESENT'],
};

function chamberWallZonesBlock(motorData) {
    const blok = (motorData || {}).chamber_wall_zones;
    if (!blok || blok.status !== 'modelled' || !Array.isArray(blok.zones)) {
        return '';
    }
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const sayi = v => typeof v === 'number' && isFinite(v);
    // Renk sunucunun önem alanından (severity) türer; eşik burada yok.
    const RENK = { critical: 'var(--hd-red, #ff5d73)',
                   warning: 'var(--hd-orange, #ff8c33)',
                   info: 'var(--hd-cyan, #00e5ff)' };
    const DIM = 'var(--hd-ink-dim, #7d97a5)';
    const satirlar = blok.zones.map(function (z) {
        const ad = ZONE_NAME_KEYS[z.zone] || [null, z.zone];
        const hk = ZONE_VERDICT_KEYS[z.verdict] || [null, z.verdict];
        const renk = RENK[z.severity] || DIM;
        const boy = sayi(z.length_mm)
            ? ` <span style="color:${DIM};">(${esc(TF('app.zones.length',
                { mm: numTxt(z.length_mm, 1) }, '{mm} mm long'))})</span>` : '';
        const ayrinti = [];
        if (z.verdict === 'PROTECTED_DURING_BURN' && sayi(z.casing_temperature_K)) {
            ayrinti.push(TF('app.zones.grainDetail',
                { T: numTxt(z.casing_temperature_K, 2) },
                'the fuel grain covers the case for the whole burn; case temperature {T} K (declared, not computed)'));
            (Array.isArray(z.notes) ? z.notes : []).forEach(function (n) {
                ayrinti.push(typeof warnToText === 'function'
                    ? warnToText(n) : String(n && n.code));
            });
        } else if (z.verdict === 'NOT_PROTECTED') {
            ayrinti.push(T('app.zones.grainNotProtected',
                'grain protection was not granted (inputs missing): the bare-wall verdict stands'));
        }
        if (z.verdict === 'LINER_REQUIRED' && sayi(z.liner_thickness_mm)) {
            ayrinti.push(TF('app.zones.linerDetail',
                { mm: numTxt(z.liner_thickness_mm, 2) },
                'this zone needs a {mm} mm insulation liner (HRMA sized it)'));
        }
        if (z.verdict === 'BARE_WALL_CRITICAL') {
            ayrinti.push(T('app.zones.noLiner',
                'no liner sizing in this run: the critical bare-wall verdict stands'));
        }
        if (z.zone !== 'grain_section' && z.verdict !== 'NOT_PRESENT'
                && sayi(z.bare_wall_temperature_K)) {
            ayrinti.push(TF('app.zones.bareDetail',
                { T: numTxt(z.bare_wall_temperature_K, 0) },
                'without a liner the bare wall reached {T} K (steady state)'));
        }
        return `<div class="hd-zone-row" data-zone="${esc(z.zone)}"
             style="margin-top:4px;"><strong>${esc(ad[0] ? T(ad[0], ad[1]) : ad[1])}</strong>${boy}
            <span class="hd-zone-verdict" data-zone-verdict="${esc(z.verdict)}"
             style="display:inline-block; margin-left:6px; padding:0 6px;
             border:1px solid ${renk}; border-radius:3px; color:${renk};
             font-weight:700;">${esc(hk[0] ? T(hk[0], hk[1]) : hk[1])}</span>${
            ayrinti.length ? `<div style="margin-top:2px;">${
                ayrinti.map(esc).join(' · ')}</div>` : ''}</div>`;
    }).join('');
    const kasaT = blok.structural_casing_temperature_K;
    const yapi = sayi(kasaT) ? `<div class="hd-zone-structural"
         style="margin-top:6px;"><strong>${esc(TF('app.zones.structural',
            { T: numTxt(kasaT, 2) }, 'Structural chain case temperature: {T} K'))}</strong>
        — ${esc(blok.all_zones_protected
            ? T('app.zones.structuralDeclared',
                'ASSUMPTION: under the grain the fuel protects the case; in the pre/post chambers the HRMA-sized liner keeps the case at this temperature (the Level-1 Q* liner model has no back-face temperature). The steady bare-wall temperature does not derate strength or fatigue.')
            : T('app.zones.structuralBare',
                'not every zone is protected: the structural chain keeps the bare-wall temperature (fail-closed)'))}</div>` : '';
    return `<div class="hd-chamber-zones" data-chamber-wall-zones="1"
         style="margin-top:10px; padding:6px 8px; border-radius:6px;
         border:1px solid var(--hd-ink-dim, #7d97a5);
         font-family:var(--hd-mono, monospace); font-size:0.68rem;
         letter-spacing:0.02em;"><strong>${esc(T('app.zones.title',
            'CHAMBER WALL: THREE ZONES (HYBRID)'))}</strong>${satirlar}${yapi}
        <div style="margin-top:6px; color:${DIM};">${esc(T('app.zones.declaration',
            'Model: the fuel grain protects the case during the burn. Not modelled: the heat wave inside the grain and the post-burn heat soak (no sourced fuel thermal diffusivity: fuel_thermal.py).'))}</div>
        <div style="margin-top:2px; color:${DIM};">${esc(T('app.zones.source',
            'Source: HRMA choice, common engineering practice; primary source not verified (supporting: Hansen & Edwards 2012; Palacz & Cieślik 2023).'))}</div>
    </div>`;
}

// Termal FEA paneli koşunca (ya da yeni sonuçta yükünü silince) kendi
// kabını yeniden çizer; blok o değişimi izleyip YALNIZ FEA yuvasını
// tazeler. Panelin kaynağına dokunulmaz (sahipliği başka kulvarda):
// sayı panelin kamuya açık `ThermalFeaPanel.payload` okuyucusundan gelir.
function watchThermalFeaForWallTemperature() {
    if (typeof MutationObserver !== 'function') return;
    const kap = document.getElementById('thermalFeaPanel');
    if (!kap || kap.__hrmaWallTWatch) return;
    kap.__hrmaWallTWatch = new MutationObserver(function () {
        if (typeof document.querySelectorAll !== 'function') return;
        const yuva = document.querySelectorAll('[' + WALL_T_FEA_SLOT + ']');
        if (!yuva.length) return;
        const html = wallTemperatureFeaSlotHtml();
        Array.prototype.forEach.call(yuva, function (el) {
            if (el.innerHTML !== html) el.innerHTML = html;
        });
    });
    kap.__hrmaWallTWatch.observe(kap, { childList: true, subtree: true,
                                        characterData: true });
}

// ==================================================================
// ÖH D37 A1a · OH-D31-04 — SOĞUTMA MENÜSÜNDE AYIRT EDİLEMEYEN SEÇİMLER
// ==================================================================
// Menü GEOMETRİ soruyor (radial / spiral), ısı transferi modeli yalnız
// SINIF çözüyor; aynı sınıfa düşen seçimler birebir aynı sayıları verir
// (D31 hibrit a1 ölçümü). Sunucu bunu her hesapta
// `cooling_channel_geometry.equivalence_classes` ile yayımlıyor (once.json
// M4: natural=[none], regenerative=[radial, spiral]); menü ise hiçbir şey
// söylemiyordu. Not, ÜYESİ İKİ VE ÜSTÜ olan her sınıf için menünün KENDİ
// seçenek metinlerini (dile göre) listeler. Liste elle yazılmaz; hesap
// yoksa ya da alan yoksa not gizli kalır (iddia yok). F-08 Dean modeli
// (A4) gelince sınıflar ayrışır ve not kendiliğinden kalkar.
function coolingEquivalenceNote(motorData) {
    const not = document.getElementById('coolingEquivalenceNote');
    if (!not) return;
    const ccg = (motorData && motorData.cooling_channel_geometry) || {};
    const siniflar = (ccg.equivalence_classes
                      && typeof ccg.equivalence_classes === 'object')
        ? ccg.equivalence_classes : null;
    const menu = document.getElementById('cooling_channels');
    const secenekMetni = function (deger) {
        const opts = (menu && menu.options) ? menu.options : [];
        for (let i = 0; i < opts.length; i++) {
            if (opts[i].value === deger) {
                return String(opts[i].textContent || deger).trim();
            }
        }
        return deger;
    };
    const cumleler = [];
    if (siniflar) {
        Object.keys(siniflar).forEach(function (sinif) {
            const uyeler = Array.isArray(siniflar[sinif]) ? siniflar[sinif] : [];
            if (uyeler.length < 2) return;
            cumleler.push(TF('app.cool.sameResult', {
                options: uyeler.map(secenekMetni).join(' = '),
                cls: coolingClassText(sinif),
            }, '{options}: identical results. Channel geometry is not modelled; the heat-transfer model resolves only the cooling class ({cls}).'));
        });
    }
    not.textContent = cumleler.join(' ');
    not.hidden = cumleler.length === 0;
    if (cumleler.length) not.setAttribute('data-cooling-equivalence', '1');
    else not.removeAttribute('data-cooling-equivalence');
}

// V301/H-PANEL (NK-15/NK-20 + NK-10): MANŞETİN DAYANAĞI MANŞETİN YANINDA.
// (1) c* verimi: teslim c* = η_c* × kuramsal c*; kaynak (kullanıcı /
//     kaynaklı varsayılan) ya da "ideal c* — verim uygulanmadı" beyanı.
// (2) Kendinden basınçlı N₂O seçiliyse manşet REGÜLE tasarım noktasıdır;
//     aynı koşunun tank boşalması çözümünün impulsu ve yanma süresi burada
//     yan yana basılır, "Tank Boşalması" paneline bağlantıyla.
// Bütün sayılar yanıttan (motor.c_star_efficiency, motor.tank_blowdown);
// alan yoksa satır basılmaz (fail-closed, uydurma yok).
function headlineBasisBlock(motorData) {
    if (!motorData || typeof motorData !== 'object') return '';
    const esc = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    const num = (v, d) => (typeof v === 'number' && isFinite(v))
        ? ((window.I18N && typeof window.I18N.number === 'function')
            ? window.I18N.number(v, d) : v.toFixed(d))
        : null;
    const satirlar = [];
    const cs = motorData.c_star_efficiency;
    if (cs && typeof cs === 'object' && typeof cs.eta_c_star === 'number') {
        if (cs.applied === false) {
            satirlar.push({ warn: true, kod: 'ideal-cstar', html: esc(T(
                'app.headline.idealCstar',
                'IDEAL c* — no c* (combustion) efficiency applied: HRMA holds no measured c* efficiency for this propellant pair, so c*, Isp and the propellant masses above are the theoretical-equilibrium values. A real motor delivers less; enter a measured value in "Combustion (c*) efficiency".')) });
        } else {
            let kaynak;
            if (cs.source === 'user_input') {
                kaynak = T('app.headline.cstarEffUser', 'your input');
            } else if (cs.source === 'sourced_default'
                       && Array.isArray(cs.measured_band)) {
                kaynak = TF('app.headline.cstarEffSourced', {
                    n: cs.n_tests, lo: num(cs.measured_band[0], 2),
                    hi: num(cs.measured_band[1], 2) },
                    'sourced default: median of {n} measured firings, range {lo}-{hi}');
            } else {
                kaynak = String(cs.source || '');
            }
            const ci = num(cs.c_star_theoretical_m_s, 0);
            const cd = num(cs.c_star_delivered_m_s, 0);
            satirlar.push({ warn: false, kod: 'cstar-eff', html: esc(TF(
                'app.headline.cstarEff', {
                    eta: num(cs.eta_c_star, 2), src: kaynak,
                    cd: cd === null ? '—' : cd, ci: ci === null ? '—' : ci },
                'c* efficiency η_c* = {eta} ({src}): delivered c* {cd} m/s = η_c* × theoretical {ci} m/s; Isp, mass flow and propellant masses use the delivered value.')),
                title: (Array.isArray(cs.sources) ? cs.sources.join(' · ') : '') });
        }
    }
    const tb = motorData.tank_blowdown;
    if (tb && typeof tb === 'object' && tb.status === 'modelled'
        && typeof tb.total_impulse_Ns === 'number') {
        const Ih = motorData.total_impulse;
        const oran = (typeof Ih === 'number' && Ih > 0)
            ? num(100 * tb.total_impulse_Ns / Ih, 0) : null;
        satirlar.push({ warn: true, kod: 'regulated-vs-blowdown', html: esc(TF(
            'app.headline.blowdown', {
                I: num(tb.total_impulse_Ns, 0), t: num(tb.burn_duration_s, 2),
                p: oran === null ? '—' : oran,
                ev: (window.TransientPanel
                     && typeof window.TransientPanel._endEventLabel === 'function')
                    ? window.TransientPanel._endEventLabel(tb.end_event)
                    : String(tb.end_event || '') },
            'The headline is the REGULATED design point (constant oxidizer flow). The self-pressurised N2O tank you selected blows down: impulse {I} N·s ({p} % of the headline), burn time {t} s, end: {ev}.'))
            + ' <a href="#blowdownPanel" class="hd-headline-link">'
            + esc(T('app.headline.blowdownLink', 'Tank Blowdown panel ↓')) + '</a>' });
    }
    if (!satirlar.length) return '';
    return '<div class="hd-headline-basis" style="margin:6px 0 10px 0;">'
        + satirlar.map(function (r) {
            return `<p data-headline-basis="${r.kod}" style="margin:2px 0;
                font-size:0.78rem; line-height:1.35; overflow-wrap:anywhere;
                color:${r.warn ? 'var(--hd-orange, #ff8c33)'
                               : 'var(--hd-ink-dim, #7d97a5)'};"${
                r.title ? ` title="${esc(r.title)}"` : ''}>${r.html}</p>`;
        }).join('') + '</div>';
}

// Display performance metrics
// Eski mor inline-gradyan kartlar hd-metric şablonuna taşındı (results_hud.css
// + hud.js). HUD katmanı yüklü değilse (eski sayfa) düz metne düşülür.
function displayPerformanceMetrics(motorData, results) {
    // ÖH D37 A1a · OH-D31-04: menü notu sonuçla (ve dil değişimiyle)
    // birlikte tazelenir; CW-B3: FEA yuvası panel koşunca tazelenir.
    try { coolingEquivalenceNote(motorData); } catch (e) { /* form yoksa */ }
    try { watchThermalFeaForWallTemperature(); } catch (e) { /* panel yoksa */ }
    const metricsDiv = document.getElementById('performanceMetrics');
    if (!metricsDiv) return;

    // Metrik listesi — tüm değerler backend sonucundan; süs/sahte veri yok.
    // ADLANDIRMA (v2.6.27, parti 20): `motorData.isp` TASARIM NOKTASI Isp'sidir
    // — hibrit çözücüde CF*C*/g0 (hybrid_rocket_engine.py:1366), CF tasarım
    // irtifasının ortam basıncında çözülür. AYNI yanıt `vacuum_isp` ve
    // `sea_level_isp` de taşır (ölçüldü, 1 kN / 20 bar / N2O-HTPB varsayılanı:
    // isp 230,3 s — vacuum_isp 260,0 s, %12,9 fark). Çıplak "Specific Impulse"
    // bu üçünden hangisi olduğunu söylemiyordu; ad, aynı sayfadaki yazdırma
    // penceresinin `adv.pop.isp` künyesiyle birebir aynı tanıma bağlandı.
    const metrics = [
        { label: T('app.metric.ispDesign', 'Isp (design point, at design-altitude ambient)'), value: motorData.isp, decimals: 1, unit: 's' },
        { label: T('app.metric.thrust', 'Thrust'), value: motorData.thrust, decimals: 0, unit: 'N' },
        { label: T('app.metric.pc', 'Chamber Pressure'), value: motorData.chamber_pressure, decimals: 1, unit: 'bar' },
        { label: T('app.metric.mdot', 'Mass Flow Rate'), value: motorData.mdot_total, decimals: 3, unit: 'kg/s' }
    ];

    // Yapısal durum backend'den geldiyse beşinci kart: minimum SF.
    // data-state eşlemesi hud.js bindState ile — eşik hesabı burada YOK,
    // durum stringi (SAFE/MARGINAL/UNSAFE) backend'in kendi kararıdır.
    //
    // KÜNYE (ÖH Z4 / P17B3-06, 2026-08-27): bu kart ile güverte yapısal
    // panelinin "Minimum SF (all modes)" satırı AYNI ADI taşıyan İKİ AYRI
    // KOŞUMDUR. Bu kart `/calculate` yanıtının motor bloğundan, panel ise
    // `/analyze_structural_safety`den okur; girdi kümeleri ayrışabilir
    // (P17 turu 0,81 ⟷ 1,07 ölçtü — 1,0 eşiğinin iki yanı). Bugünkü
    // ölçümde (hibrit varsayılan, panel önerileriyle) ikisi de
    // 1,7173327063051922 — bit-özdeş. Ayrışma her koşuda yok; ama ekran
    // hangisinin hangi koşum olduğunu HİÇ söylemiyordu.
    //
    // İKİNCİ KÜNYE (Z4 kökü): bu sayı kullanıcının KAZANDIĞI marj olmak
    // zorunda değil. Ölçüldü (hibrit varsayılan tasarım): beş modun BEŞİ de
    // `safety_factor_is_tautological: true`, `minimum_earned_safety_factor
    // = null`, `chamber_analysis.design_mode = 'size'` — yani sayı
    // HRMA'nın KENDİ boyutlandırdığı cidardan geliyor, kullanıcının
    // kurduğu bir cidarın doğrulaması DEĞİL. Kart bunu artık künyesinde
    // söylüyor; beyan yoksa hiçbir şey iddia etmez (fail-closed).
    const structSafety = motorData.structural_analysis
        && motorData.structural_analysis.safety_analysis;
    if (structSafety && typeof structSafety.minimum_safety_factor === 'number'
        && isFinite(structSafety.minimum_safety_factor)) {
        const kunye = [];
        // Hangi koşum? (Bu işlev YALNIZ /calculate yanıtıyla çağrılır:
        // displayCalculationResults tek çağıranı ve o da /calculate fetch'i.)
        kunye.push('/calculate');
        // Cidar nereden geldi? Sunucunun kendi kapı sınıfı — üç değerin
        // ikisinin sözlükte karşılığı var, üçüncüsü makine adıyla basılır.
        const dbasis = (results && results.structural_design_basis) || null;
        const wsrc = dbasis && String(dbasis.wall_thickness_source || '');
        if (wsrc === 'sized_by_hrma') {
            kunye.push(T('panel.structural.wallSized', 'WALL: SIZED BY HRMA'));
        } else if (wsrc === 'user_supplied' && dbasis.is_verification !== false) {
            kunye.push(T('panel.structural.wallUser', 'WALL: AS SUPPLIED'));
        } else if (wsrc) {
            kunye.push('wall_thickness_source: ' + wsrc);
        }
        // Minimumu belirleyen mod(lar) ve kazanılıp kazanılmadığı.
        if (Array.isArray(structSafety.binding_safety_factors)
            && structSafety.binding_safety_factors.length) {
            kunye.push(TF('app.metric.sfBinding',
                { list: structSafety.binding_safety_factors.map(sfIstasyonAdi).join(', ') },
                'Governing station(s): {list}'));
        }
        // Hedef geri okuması imi: uç istasyonları adıyla veriyorsa (Z4-A
        // kanalı) onlar basılır — ama YALNIZ minimumu belirleyen istasyon
        // gerçekten hedefi geri okuyorsa; aksi hâlde bu sayı bir ölçümdür.
        const readback = Array.isArray(structSafety.stations_reading_back_target)
            ? structSafety.stations_reading_back_target : null;
        const bind = Array.isArray(structSafety.binding_safety_factors)
            ? structSafety.binding_safety_factors : [];
        const bindOkur = (typeof structSafety.binding_safety_factor_reads_back_target
                === 'boolean')
            ? structSafety.binding_safety_factor_reads_back_target
            : !!(readback && readback.length && bind.length
            && bind.some(function (k) { return readback.indexOf(k) !== -1; }));
        // Eski `binding_safety_factor_is_tautological` bayrağı YALNIZ yeni
        // kanal YOKKEN kullanılır: ölçüldü (hibrit varsayılan, 27 Ağu) —
        // bayrak `true` derken `stations_reading_back_target` chamber_hoop'u
        // İÇERMİYOR, çünkü o kesit hedefin ALTINA düşmüş gerçek bir ölçüm.
        // İki beyan aynı anda basılırsa ekran kendi kendisiyle çelişir.
        if (bindOkur) {
            kunye.push(TF('app.metric.sfReadback',
                { list: readback.map(sfIstasyonAdi).join(', ') },
                'Stations reading back the design target: {list}'));
        } else if (!readback
                   && structSafety.binding_safety_factor_is_tautological === true) {
            kunye.push(T('app.metric.sfTautological',
                'The governing safety factor reads back the design target'));
        }
        const earned = structSafety.minimum_earned_safety_factor;
        if (typeof earned === 'number' && isFinite(earned)) {
            kunye.push(TF('app.metric.sfEarned', { v: numTxt(earned, 2) },
                'Minimum earned safety factor: {v}'));
        } else if (earned === null) {
            // V301/DİL (NK-4): "null" kartın büyük sayısıyla çelişiyor
            // gibi okunuyordu. Büyük sayı istasyonlar arası EN KÜÇÜK emniyet
            // katsayısıdır; KAZANILMIŞ (doğrulanmış) asgari EK yayımlanmadı.
            kunye.push(T('app.metric.sfEarnedNone',
                'Large number = smallest safety factor across stations; '
                + 'no EARNED (verified) minimum safety factor is published'));
        }
        // Hükmün ÇEKİLDİĞİ sayı ayrı yayımlanıyorsa (Z4-A kanalı) ve karttaki
        // sayıdan FARKLIYSA künyeye girer; aynıysa tekrar edilmez.
        const vsf = structSafety.verdict_safety_factor;
        if (typeof vsf === 'number' && isFinite(vsf)
            && Math.abs(vsf - structSafety.minimum_safety_factor)
                > Math.abs(structSafety.minimum_safety_factor) * 1e-9) {
            kunye.push(TF('app.metric.sfVerdict', { v: numTxt(vsf, 2) },
                'Safety factor the verdict rests on: {v}'));
        } else if (vsf === null) {
            kunye.push(T('app.metric.sfVerdictNone',
                'Safety factor the verdict rests on: not published'));
        }
        // Gerekçe metnini SUNUCU yazar, kart yeniden yazmaz (panel
        // designBasisBlock deseni).
        const tip = [structSafety.minimum_safety_factor_basis,
                     structSafety.minimum_safety_factor_verdict_basis,
                     structSafety.verdict_safety_factor_source
                         ? 'verdict_safety_factor_source: '
                           + structSafety.verdict_safety_factor_source : '',
                     dbasis && dbasis.message]
            .filter(function (s) { return typeof s === 'string' && s; })
            // OH-Z4-04: kartın ipucu da sunucunun cümlesidir — çeviri
            // kanalından geçer (eşleşme yoksa metin AYNEN kalır).
            .map(function (s) { return SRV(s); })
            .join(' ');
        metrics.push({
            label: T('app.metric.minSf', 'Structural Min SF'),
            value: structSafety.minimum_safety_factor,
            decimals: 2,
            unit: '',
            state: structSafety.status,
            // ÖH D21 / P17B2-01 (yüksek) — HÜKÜM RENKTEN BAŞKA BİR KANALDA DA
            // TAŞINIR.
            // ÖLÇÜLDÜ (P17 B2-tur-04, canlı /hybrid, SF 0,81 -> UNSAFE):
            // kartın `textContent`i "STRUCTURAL MIN SF 0.81" idi;
            // UNSAFE/MARGINAL/SAFE sözcüğü kartta 0 kez geçiyor, title /
            // aria-label yok, `.hd-led` düğümü sayfada hiç yok. Hüküm YALNIZ
            // `data-state` renginde duruyordu ve üç durumun WCAG bağıl
            // parlaklık kontrastı 1,07 / 1,49 / 1,59 — üçü de metin-dışı
            // ayırt edilebilirlik tabanının (3:1) altında. Yani ekran
            // okuyucu, gri baskı ve kırmızı-yeşil renk körlüğü hükmü AYNI
            // ANDA kaybediyordu; üstelik ürün onu doğru hesaplamıştı.
            // Sözcük SUNUCUNUN kendi hüküm belirtecidir; burada sınıflandırma
            // ÜRETİLMEZ, yalnız yazıya dökülür (SRV = sunucu dizesi çeviri
            // kanalı; eşleşme yoksa makine adı aynen kalır).
            stateWord: (typeof structSafety.status === 'string'
                        && structSafety.status) ? structSafety.status : '',
            note: kunye.join(' · '),
            // Turuncu künye = "bu sayı kurulmuş bir donanımın doğrulaması
            // değil". Ölçüt aynı önceliği izler: yeni kanal varsa onun
            // kararı, yoksa eski bayrak.
            noteWarn: (wsrc === 'sized_by_hrma' || bindOkur
                       || (!readback
                           && structSafety.binding_safety_factor_is_tautological
                              === true)),
            title: tip
        });
    }

    /* ÖH D33-3 / OH-D33-12 — HUD'suz yol ve `aria-label` da TEK AYRAÇ
       KANONUNU izler. ÖLÇÜLDÜ (a1/once.json M1 `hudsuz_yol_ilk300`):
       Türkçe kipte "Oda Basıncı: 20.0 bar · Kütle Debisi: 0.457 kg/s"
       yazıyordu, yani ekran okuyucunun duyduğu ve HUD'suz sayfanın
       gösterdiği metin de nokta basıyordu. Basamak sayısına yine çağıran
       karar verir (`m.decimals`); `I18N.number` yalnız ayracı
       `ondalikAyraci()` tek kaynağından yazar (i18n.js:330). */
    const fmtVal = m => {
        const v = Number(m.value);
        if (!isFinite(v)) return 'n/a';
        return (window.I18N && typeof window.I18N.number === 'function')
            ? window.I18N.number(v, m.decimals) : v.toFixed(m.decimals);
    };
    // Künye metni sunucudan geliyor: title ÖZNİTELİĞİNE konmadan önce
    // tırnak/açılı ayraç kaçırılır (bozuk öznitelik = kaybolan kart).
    const attrSafe = s => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // HUD katmanı yoksa (hud.js yüklenmemiş eski sayfa): zarifçe düz metin.
    // Künye burada da DÜŞMEZ: kartın anlamı ona bağlı.
    if (typeof window.HRMAHud === 'undefined') {
        // P17B2-01: HUD'suz yolda da hüküm sözcüğü düşmez — orada renk
        // kanalı hiç yok, dolayısıyla sözcük TEK kanaldır.
        metricsDiv.innerHTML = metrics.map(m =>
            `<div style="padding:4px 0;" title="${attrSafe(m.title)}"><strong>${m.label}:</strong> `
            + `${fmtVal(m)} ${m.unit}`
            + `${m.stateWord ? ' — ' + attrSafe(SRV(m.stateWord)) : ''}`
            + `${m.note ? ' — ' + m.note : ''}</div>`
        ).join('')
            // V301/H-PANEL: manşetin dayanağı (c* verimi, blowdown) hemen altta.
            + headlineBasisBlock(motorData)
            // V301/H-termal: bölge hükmü + yapısal kasa sıcaklığı varsayımı
            // yapısal hükmün ÜSTÜNDE (sessiz MET yok).
            + chamberWallZonesBlock(motorData)
            // P11B2-01: hüküm/risk/öneriler HUD'suz yolda da DÜŞMEZ.
            + structuralVerdictBlock(motorData, results)
            // P11B2-13: varsayılan beyanı HUD'suz yolda da DÜŞMEZ.
            + defaultsDeclarationBlock(motorData, results)
            // ÖH D37 A1a · CW-A4E6 + CW-B3: HUD'suz yolda da düşmez.
            + defaultsAppliedBlock(results)
            + wallTemperatureQuestionsBlock(motorData);
        return;
    }

    let html = '<div class="hd-metric-grid">';
    metrics.forEach(m => {
        const v = Number(m.value);
        const countSpan = isFinite(v)
            ? `<span class="hd-count" data-target="${v}" data-decimals="${m.decimals}">0</span>`
            : '<span>n/a</span>';
        const note = m.note
            ? `<div class="hd-metric-note" style="font-family:var(--hd-mono);
                 font-size:0.66rem; letter-spacing:0.02em; margin-top:2px;
                 color:${m.noteWarn ? 'var(--hd-orange, #ff8c33)'
                                    : 'var(--hd-ink-dim, #7d97a5)'};"
                 >${kunyeSarmaHtml(m.note, KUNYE_DAR_KART_ESIGI)}</div>`
            : '';
        // P17B2-01: hüküm sözcüğü kartın GÖRÜNÜR metnine girer. Rozet
        // `data-state` rengiyle aynı kaynaktan beslenir ama renkten
        // bağımsız okunur; `aria-label` kartın tamamını tek cümlede verir.
        /* ÖH D27 a4 · P11S1-02 — UNSAFE HÜKMÜNÜN GÖRSEL İMZASI DOĞUYOR.

           ÖLÇÜLDÜ (a4/once.json): `results_hud.css` durum pilini
           (`.hd-statustag`, 2 kural) ve LED'i (`.hd-led`, 8 kural) tanımlı
           tutuyordu; LED'in hud.js'te tüketicisi vardı ama PİLİN ürün
           kodunda tüketicisi SIFIRDI (`p11s1_02_js_tuketici_hd_statustag`
           = 0). Bu kart pili yeniden yazan satır-içi bir üslupla kendi
           `.hd-state-word` rozetini çiziyordu ve içinde `.hd-led` düğümü
           YOKTU — oysa `[data-state="unsafe"] .hd-led` kuralı UNSAFE'in
           TEK kalıcı görsel imzasıdır (yanıp sönen LED). `bindState`
           kartın kendisine `data-state` koyuyordu, kart da rengi alıyordu;
           ama renk metin-dışı ayırt edilebilirlik tabanının altında
           (P17B2-01 ölçümü: 1,07 / 1,49 / 1,59 — taban 3:1). Yani imza
           hiç doğmuyordu.

           Rozet artık paylaşılan pil sözleşmesini KULLANIR (biçim tek
           kaynakta, CSS'te) ve içine LED düğümünü alır. `hd-state-word`
           sınıfı korunur (tests/test_d21_arayuz_a2.py ona bakıyor);
           satır-içi üslup yalnız CSS'in vermediği yerleşim payını
           taşır — renk/kenar/yuvarlaklık artık pilin kendisinden gelir. */
        const stateWord = m.stateWord
            ? `<span class="hd-statustag hd-state-word"
                 style="margin-left:6px; white-space:nowrap;"
                 ><span class="hd-led"></span>${attrSafe(SRV(m.stateWord))}</span>`
            : '';
        const kartEtiketi = m.stateWord
            ? `${attrSafe(m.label)} ${attrSafe(fmtVal(m))} ${attrSafe(m.unit)}`
              + ` — ${attrSafe(SRV(m.stateWord))}`
            : '';
        html += `
            <div class="hd-metric" title="${attrSafe(m.title)}"${
                kartEtiketi ? ` aria-label="${kartEtiketi}"` : ''}>
                <div class="hd-metric-head">
                    <div class="hd-metric-label">${m.label}${stateWord}</div>
                    ${note}
                </div>
                <div class="hd-metric-value">
                    ${countSpan}<small>${m.unit}</small>
                </div>
            </div>`;
    });
    html += '</div>';
    // V301/H-PANEL (NK-15/NK-10): manşetin dayanağı kart ızgarasının HEMEN
    // altında (c* verimi; kendinden basınçlı tankta blowdown sayıları).
    html += headlineBasisBlock(motorData);
    // P11B2-01 (KRİTİK): yapısal hüküm + risk + adlandırılmış onarım
    // önerileri kart ızgarasının HEMEN altına. Aynı işlev dil değişiminde de
    // çağrıldığı için şerit dille birlikte yeniden basılır.
    // V301/H-termal: bölge hükmü ve yapı zincirinin kasa sıcaklığı
    // varsayımı yapısal hükmün ÜSTÜNDE görünür (sessiz MET yok).
    html += chamberWallZonesBlock(motorData);
    html += structuralVerdictBlock(motorData, results);
    // P11B2-13: çözücünün kendi "varsayılana düşen girdiler" listesi.
    html += defaultsDeclarationBlock(motorData, results);
    // ÖH D37 A1a · CW-A4E6: ucun `defaults_applied` künyesi (boş alanlar
    // için sunucunun uyguladığı değerler) — liste sunucudan, elle değil.
    html += defaultsAppliedBlock(results);
    // ÖH D37 A1a · CW-B3: cidar sıcaklığının hangi soruyu yanıtladığı.
    html += wallTemperatureQuestionsBlock(motorData);
    metricsDiv.innerHTML = html;

    // Durum bağlama + count-up başlatma
    const cards = metricsDiv.querySelectorAll('.hd-metric');
    metrics.forEach((m, i) => {
        if (m.state && cards[i]) HRMAHud.bindState(cards[i], m.state);
    });
    HRMAHud.initAll(metricsDiv);
}

// Plotly grafiğini güvenle çizer (JSON parse + responsive layout ayarı).
// displayPlots içinden ÇIKARILDI: opsiyonel panel yardımcısı da kullanıyor.
/* v2.6.26 — İtki ve oda basıncı zaman eğrisi (hibrit).
 *
 * Katı motor sayfasında bu eğri vardı, hibritte YOKTU; oysa zaman-adımlı
 * çözücü anlık yakıt debisini, c*'ı ve Isp'yi zaten hesaplıyordu ve
 * yalnızca dışarı vermiyordu. Eğri artık çözücünün kendi durumundan gelir
 * (motor.thrust_curve), burada BİÇİM VERİLMEZ.
 *
 * Veri yoksa panel gizlenir: boş bir grafik kabı, kullanıcıya "hesap
 * yapıldı ama sonuç sıfır" izlenimi verir — oysa gerçek "bu koşuda eğri
 * üretilmedi"dir (ör. eski kayıt yüklendiğinde).
 */
// ÖH D29 · P11B2-15 — EĞRİNİN KENDİ KÜNYESİ (basis + sampling).
// Ölçülen: `thrust_curve.basis` ve `thrust_curve.sampling` yükte var ve
// panelde 0 kez okunuyordu; kullanıcı 201 noktalık diziyi çözücünün
// çözünürlüğü sanabiliyordu (dizinin YAYIN çözünürlüğü olduğu, neyin
// korunduğu ve türetilmiş sayıların TAM çözünürlükten geldiği yalnız bu
// iki alanda yazılı). Künye hiçbir sayı ÜRETMEZ: alan yoksa satır hiç
// yazılmaz, alan adları makine verisidir (yeni çeviri anahtarı açılmaz).
function thrustCurveDeclaration(panel, curve) {
    if (!panel) return;
    let kutu = panel.querySelector('[data-thrust-curve-decl]');
    const satirlar = [];
    if (typeof curve.basis === 'string' && curve.basis) {
        satirlar.push('thrust_curve.basis: ' + SRV(curve.basis));
    }
    const sm = curve.sampling;
    if (sm && typeof sm === 'object') {
        const alanlar = ['points_published', 'points_computed', 'decimated',
                         'solver_time_step_s', 'max_points', 'cap_exceeded'];
        const parcalar = alanlar
            .filter(k => sm[k] !== undefined && sm[k] !== null)
            .map(k => k + ' = ' + String(sm[k]));
        if (parcalar.length) {
            satirlar.push('thrust_curve.sampling: ' + parcalar.join(', '));
        }
        if (typeof sm.basis === 'string' && sm.basis) {
            satirlar.push('thrust_curve.sampling.basis: ' + SRV(sm.basis));
        }
        if (typeof sm.cap_note === 'string' && sm.cap_note) {
            satirlar.push('thrust_curve.sampling.cap_note: ' + SRV(sm.cap_note));
        }
    }
    if (!satirlar.length) {
        if (kutu) kutu.remove();
        return;
    }
    if (!kutu) {
        kutu = document.createElement('div');
        kutu.setAttribute('data-thrust-curve-decl', '1');
        kutu.style.cssText = 'margin-top:8px; font-size:0.72rem;'
            + ' line-height:1.45; color:#6c757d;'
            + ' font-family:var(--hd-mono, monospace);';
        panel.appendChild(kutu);
    }
    kutu.textContent = satirlar.join('  |  ');
}

function renderHybridThrustCurve() {
    const panel = document.getElementById('hybridThrustCurvePanel');
    const host = document.getElementById('hybrid_thrust_plot');
    if (!panel || !host) return;

    const curve = (window.currentResults && currentResults.motor
                   && currentResults.motor.thrust_curve) || null;
    const hasData = !!(curve && Array.isArray(curve.time) && curve.time.length > 1
                       && Array.isArray(curve.thrust) && curve.thrust.length > 1);
    if (!hasData) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = '';

    // v3.0.1 (V301/N-grafik G3) — İTKİ, ODA BASINCI VE TOPLAM DEBİ AYRI
    // ALT GRAFİKLERDE, ORTAK ZAMAN EKSENİ.
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/grafik/RAPOR.md, G2 önce; hibrit
    // örneği 1440x900): üç iz üç y ekseninde AYNI çizim alanındaydı;
    // normalize değerleri %2 içinde örtüşen nokta oranı üç çiftte de 1,00
    // (eğriler ayırt edilemiyordu) ve üçüncü eksenin döndürülmüş başlığı
    // sağ kenardan kırpılıyordu. Her iz artık kendi alt grafiğinde, kendi
    // ölçeğiyle; zaman ekseni ortak (`matches`). Veri DEĞİŞMEDİ: x/y
    // dizileri aynen `thrust_curve` alanlarıdır; iz koşulları (basınç ve
    // debi yalnız tam ve sonluysa) aynen korunur.
    const pressure = Array.isArray(curve.pressure) ? curve.pressure : [];
    const basincCizilir = pressure.length === curve.time.length
        && pressure.every(v => typeof v === 'number' && isFinite(v));
    // ÖH D29 · P11B2-15 — ÜRETİLEN TOPLAM DEBİ EĞRİSİ ÇİZİLİYOR.
    // ÖLÇÜLDÜ (a3/once.json): `thrust_curve` altı alan yayımlıyor
    // (time, thrust, pressure, mass_flow, basis, sampling) ve panel
    // yalnız ilk üçünü okuyordu. Hibritte oksitleyici debisi sabit, yakıt
    // debisi port gerilemesiyle değişir; toplam debi O/F kaymasının
    // doğrudan okunabildiği eğridir.
    // Eğri UYDURULMAZ: uzunluğu zaman eksenine eşit ve tamamı sonlu
    // değilse iz HİÇ eklenmez (basınç izinin kuralıyla aynı).
    const massFlow = Array.isArray(curve.mass_flow) ? curve.mass_flow : [];
    const massFlowCizilir = massFlow.length === curve.time.length
        && massFlow.every(v => typeof v === 'number' && isFinite(v));

    const paneller = [{ y: curve.thrust, name: T('app.chart.thrust', 'Thrust'),
                        axis: T('app.chart.thrustN', 'Thrust (N)') }];
    if (basincCizilir) {
        paneller.push({ y: pressure,
                        name: T('app.chart.chamberPressure', 'Chamber Pressure'),
                        axis: T('app.chart.pressureBar', 'Chamber Pressure (bar)') });
    }
    if (massFlowCizilir) {
        paneller.push({ y: massFlow,
                        name: T('common.f.mdotTotal', 'Total Mass Flow (kg/s)'),
                        axis: T('common.f.mdotTotal', 'Total Mass Flow (kg/s)') });
    }
    const n = paneller.length;
    // Alt grafik payları (kâğıt kesri): eşit yükseklik, aralarında %8 boşluk.
    const ARALIK = 0.08;
    const pay = (1 - ARALIK * (n - 1)) / n;
    const traces = [];
    const layout = {
        title: T('app.chart.thrustVsTime', 'Thrust and Chamber Pressure vs Time')
            + (massFlowCizilir
                ? ' · ' + T('common.f.mdotTotal', 'Total Mass Flow (kg/s)') : ''),
        showlegend: false,
        // ÖH D34 · OH-P-01 (piksel turu, 21 Eyl 2026) — GRAFİK ÇÖKÜKTÜ:
        // yükseklik beyan edilmeyince Plotly kabın ölçüsü oturmadan 140 px
        // çiziyordu. Açık yükseklik korunur (tek iz 480 px, her ek alt
        // grafik +120 px). Lejant yok: her alt grafiğin eksen başlığı izi
        // adlar (OH-P-01'in dikey lejant ⟷ sağ eksen çakışması da böylece
        // kökten yok).
        height: 480 + 120 * (n - 1),
        margin: { t: 60, r: 30, b: 60, l: 84 },
    };
    paneller.forEach(function (p, i) {
        const ek = i === 0 ? '' : String(i + 1);
        const ust = 1 - i * (pay + ARALIK);
        traces.push({ x: curve.time, y: p.y, type: 'scatter', mode: 'lines',
                      name: p.name, xaxis: 'x' + ek, yaxis: 'y' + ek,
                      line: { width: i === 0 ? 3 : 2.5 } });
        layout['yaxis' + ek] = { title: p.axis, domain: [Math.max(0, ust - pay), ust],
                                 anchor: 'x' + ek };
        const sonEksen = i === n - 1;
        layout['xaxis' + ek] = Object.assign({ anchor: 'y' + ek },
            sonEksen ? { title: T('app.chart.timeS', 'Time (s)') }
                     : { showticklabels: false },
            i === 0 ? {} : { matches: 'x' });
    });
    thrustCurveDeclaration(panel, curve);
    Plotly.newPlot(host, traces, layout, {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
        toImageButtonOptions: { format: 'png', filename: 'hybrid_thrust_curve', scale: 2 }
    });
}

/* v2.6.26 — Tasarım raporundaki "Chamber Volume" satırı, hemen üstündeki
 * L* satırıyla ÇELİŞİYORDU. Motor iki hacim döndürür:
 *   chamber_volume        = L*_istenen x A_t  (kullanıcının HEDEFİ)
 *   chamber_volume_actual = gerçek geometrinin sardığı serbest hacim
 * Hibritte port hacmi tek başına büyük olduğu için gerçekleşen L* çoğu zaman
 * istenenin çok üstünde kalır (ölçüldü: 1,00 m istendi, 7,49 m gerçekleşti) ve
 * tablo 371,4 cm³ gösterirken motorun gerçek hacmi 2781,5 cm³'tü. Aynı tablonun
 * bir üst satırı zaten "achieved 7,49 m" yazdığı için iki satır matematiksel
 * olarak birbirini yalanlıyordu. Artık GERÇEK hacim gösterilir; hedef hacim
 * l_star / l_star_achieved satırlarından zaten okunabiliyor.
 */
// ==================================================================
// P11B2-24 — "BAŞARI" ROZETİ HTTP KODUNUN KOPYASI OLMAKTAN ÇIKARILDI
// ==================================================================
// Ölçülen (docs/scofield/raw/OH/D15/ui-paneller/a2/b2_24_ONCE.json):
// üç dışa aktarım işleyicisi de yalnız `response.ok`'a bakıyordu ve
// içeriği boş / istenmeyen 200 yanıtlarında ÜÇÜ DE yeşil onay yayımladı
// (icerik_bos_ama_basari_yayimlayan = 3/3).
// Aşağıdaki üç kapı fail-closed'dır: hüküm kazanılmadıysa yayımlanmaz,
// eksik olan ADIYLA söylenir, hiçbir sayı uydurulmaz.

// Kapıların fırlattığı mesajlar MAKİNE VERİSİDİR (alan adları + ölçülen
// değerler): yeni çeviri anahtarı AÇILMAZ. Üçü de dış işleyicinin ZATEN
// çevrilmiş zarfına giriyor (`app.msg.cadError` / `app.msg.paramError`),
// PDF dalı ise yalnız console.warn'a düşüp metin rapor yedeğine geçiyor.
const BOS_ICERIK = 'endpoint returned no content: ';
const PDF_DEGIL = 'endpoint did not return a PDF: ';
const TARAMA_IKAME = 'endpoint substituted the sweep: ';

// ÖH D30 · OH-D29-02 (ÇİFT: P12bB3-09 / OH-D28-10 / P12bS1-06) — ÖLÇÜLEN ÖLÜ KOPYA SÖKÜLDÜ.
// app.js YALNIZ advanced.html tarafından yükleniyor (ölçüldü: 8 şablonun 1’i) ve
// o sayfanın satır içi betiği bu adı app.js etiketinden SONRA yeniden bildiriyordu;
// hoisting ile satır içi sürüm kazanıyordu, yani aşağıdaki gövde hiç koşmuyordu.
// Kanıt: docs/scofield/raw/OH/D30/arayuz-panel/a1/{once,sonra}.json (11 canlı gölge,
// 446 satır) — söküm ÖNCESİ her adın hangi sürümünün kazandığı sayfa sayfa ölçüldü.
// SÖKÜLDÜ (D30 a1) · assertCadContent() — tek çağrısı yukarıdaki ölü generateCAD içindeydi; denetlediği /api/export-cad yanıt şekli canlı yolda hiç istenmiyor (canlı yol /api/generate-3d’dir ve kendi fail-closed dalı OH-D23-15’te açıldı).

// İnen blob'un gerçekten PDF olduğunu doğrular: sunucunun ilan ettiği
// içerik tipi + dosyanın kendi `%PDF-` imzası. Biri tutmazsa fırlatır.
async function assertPdfBlob(blob, response) {
    const ilan = String((response && response.headers
        && response.headers.get('Content-Type')) || (blob && blob.type) || '');
    if (ilan.indexOf('application/pdf') < 0) {
        throw new Error(PDF_DEGIL + 'Content-Type=' + (ilan || '—'));
    }
    if (!blob || !(blob.size > 0)) {
        throw new Error(PDF_DEGIL + 'blob.size=0');
    }
    // İmza: PDF dosyaları "%PDF-" ile başlar (ISO 32000-1 §7.5.2).
    const bas = await blob.slice(0, 5).arrayBuffer();
    const b = new Uint8Array(bas);
    const imza = String.fromCharCode.apply(null, Array.prototype.slice.call(b));
    if (imza !== '%PDF-') {
        throw new Error(PDF_DEGIL + 'magic=' + JSON.stringify(imza));
    }
}

// Ucun yankıladığı tarama, istenen taramayla aynı mı? Değilse fırlatır.
function assertParametricMatchesRequest(result, istenenTip, bas, son) {
    if (!result || typeof result !== 'object') {
        throw new Error(BOS_ICERIK + 'parametric response');
    }
    const donenTip = result.sweep_parameter;
    if (typeof donenTip === 'string' && istenenTip
            && donenTip !== String(istenenTip)) {
        throw new Error(TARAMA_IKAME + 'sweep_parameter=' + donenTip
            + ' (requested ' + String(istenenTip) + ')');
    }
    const aralik = result.sweep_range;
    if (Array.isArray(aralik) && aralik.length === 2
            && isFiniteNum(bas) && isFiniteNum(son)
            && isFiniteNum(aralik[0]) && isFiniteNum(aralik[1])) {
        // Yankı ile isteğin sayısal karşılaştırması; kayan nokta artığı
        // için 1e-9 göreli tolerans (mutlak eşiği olmayan saf oran testi).
        const uyar = function (a, b) {
            const olcek = Math.max(Math.abs(a), Math.abs(b), 1e-30);
            return Math.abs(a - b) / olcek <= 1e-9;
        };
        if (!uyar(aralik[0], bas) || !uyar(aralik[1], son)) {
            throw new Error(TARAMA_IKAME + 'sweep_range='
                + aralik[0] + '–' + aralik[1]
                + ' (requested ' + bas + '–' + son + ')');
        }
    }
    if (isFiniteNum(result.points_succeeded) && result.points_succeeded <= 0) {
        throw new Error(BOS_ICERIK + 'points_succeeded='
            + result.points_succeeded);
    }
}

// ==================================================================
// P11B2-08 — YANAN KÜTLE ⟷ YÜKLENEN KÜTLE ÇELİŞKİSİ
// ==================================================================
// Ölçülen (docs/scofield/raw/OH/D15/ui-paneller/a2/b2_08_ONCE.json):
// "Propellant" bölümü `propellant_mass_total` = 4,7130 kg basıyordu
// (= oksitleyici 4,1681 + YANAN yakıt 0,5449). Aynı raporun "Design
// Summary" bölümü `total_mass_kg` = 20,6662 kg basıyor ve çözücünün
// kendi beyanı (`key_dimensions.total_mass_basis`) bunun kuru kütle +
// YÜKLENEN oksitleyici + YÜKLENEN gren olduğunu söylüyor. Yüklenen
// itergaç 4,1681 + 1,9378 = 6,1059 kg; ekrandaki satırla arada
// 1,3929 kg (+%29,55) fark var ve ekranda bunu açıklayan tek kelime
// yoktu — grenin %71,88'i yanmadan ölü ağırlık olarak uçuyor.
//
// Çözüm BEYAN DEĞİL, eksik alanların basılmasıdır: çözücü
// `fuel_mass_loaded`, `fuel_sliver_fraction`, `oxidizer_mass_residual_kg`
// alanlarını HER hesapta yayımlıyordu, rapor üçünü de düşürüyordu.
// Satır etiketleri MAKİNE ALAN ADIYLA nitelenir (yeni çeviri anahtarı
// açılmaz — a1'de safety_panel için kullanılan desenin aynısı): hangi
// sayının yanan hangisinin yüklenen olduğu ada bakarak okunur.
//
// Uydurma yok: hiçbir satır hesaplanmaz, yalnız ucun yayımladığı alan
// basılır. Alan yoksa satır HİÇ çıkmaz (fail-closed).

// Satır etiketinin yanına ucun makine alan adını koyar.
// V301/DİL (NK-4): yapısal istasyon makine adları ekranda okunur ada iner;
// tanınmayan ad AYNEN kalır (uydurma çeviri yok). Anahtarlar literal
// (i18n ölü anahtar bekçisi çağrı yerinden tarar).
function sfIstasyonAdi(k) {
    switch (k) {
    case 'nozzle': return T('app.sfst.nozzle', 'nozzle');
    case 'end_cap': return T('app.sfst.endCap', 'end cap');
    case 'chamber_hoop': return T('app.sfst.chamberHoop', 'chamber hoop stress');
    case 'chamber_von_mises': return T('app.sfst.chamberVonMises', 'chamber von Mises stress');
    case 'buckling_axial': return T('app.sfst.bucklingAxial', 'axial buckling');
    default: return String(k);
    }
}

// V301/DİL (NK-7): makine alan adı satırın GÖRÜNÜR metni değildir —
// ölçüldü (docs/scofield/raw/OH/V301/dil/once.json): TR raporda
// `propellant_mass_total`, `fuel_mass_loaded` … çevrili etiketin yanında ham
// basılıyordu. İm korunur (data-field + fareyle üstüne gelince title), ama
// ekranda okunmaz; hangi sayının hangi alan olduğu yine öğrenilebilir.
function fieldTag(name) {
    return ` <span class="hd-field-tag" data-field="${name}" title="${name}"></span>`;
}

function isFiniteNum(x) {
    return typeof x === 'number' && isFinite(x);
}

// Yüklenen (uçan) kütle satırları. Yalnız ucun gerçekten yayımladığı
// alanlar basılır; hiçbiri yoksa boş dize döner ve tablo eskisi gibi kalır.
function loadedMassRows(motorData) {
    if (!motorData || typeof motorData !== 'object') return '';
    const rows = [];
    if (isFiniteNum(motorData.fuel_mass_loaded)) {
        rows.push(`<tr><td>${T('app.rep.fuelMass', 'Fuel Mass')}`
            + fieldTag('fuel_mass_loaded')
            + `</td><td>${numTxt(motorData.fuel_mass_loaded, 2)} kg</td></tr>`);
    }
    // ÖH D37 A1a · DV-GT27 — ÖLÇÜLDÜ (a1/once.json M7, Ornek-H1 canlı,
    // EN ve TR): bu iki satırın etiket hücresi YALNIZ ham makine alan adını
    // basıyordu (`fuel_sliver_fraction`, `oxidizer_mass_residual_kg`;
    // alan imi dışında metin ''). Kardeş satırlarla aynı desene çekildi:
    // çevrilmiş etiket + yanında makine alan imi (imi korunur: hangi
    // sayının hangi alan olduğu ada bakarak okunmaya devam eder).
    if (isFiniteNum(motorData.fuel_sliver_fraction)) {
        rows.push(`<tr><td>${T('app.rep.fuelSliverFraction', 'Unburned fuel (sliver) fraction')}`
            + fieldTag('fuel_sliver_fraction')
            + `</td><td>${pctTxt((motorData.fuel_sliver_fraction * 100), 1)}</td></tr>`);
    }
    if (isFiniteNum(motorData.oxidizer_mass_residual_kg)) {
        rows.push(`<tr><td>${T('app.rep.oxResidualMass', 'Residual (unused) oxidizer mass')}`
            + fieldTag('oxidizer_mass_residual_kg')
            + `</td><td>${numTxt(motorData.oxidizer_mass_residual_kg, 2)} kg</td></tr>`);
    }
    return rows.join('\n');
}

// ÖH D25 / P11B2-12 — çözücü hacmi yayımlamadıysa SIFIR DÖNMEZ, `null`
// döner. Eskiden `motorData.chamber_volume || 0` yüzünden ekranda
// "0.0 cm³" yazıyordu ve kullanıcı bunu ölçülmüş bir hacim sanıyordu.
// Sıfır hacim fiziksel olarak anlamsızdır; "hesaplanmadı" ile "sıfır"
// aynı şey değildir.
function chamberVolumeM3(motorData) {
    if (!motorData) return null;
    const actual = motorData.chamber_volume_actual;
    if (isFiniteNum(actual) && actual > 0) return actual;
    const nominal = motorData.chamber_volume;
    return (isFiniteNum(nominal) && nominal > 0) ? nominal : null;
}

// Hacmin ekrana çıkan metni. Hesaplanmadıysa sayı UYDURULMAZ; birim de
// yazılmaz (birimsiz "hesaplanmadı cm³" ibaresi olmasın diye birim bu
// yardımcının içindedir).
function chamberVolumeCm3Text(motorData) {
    const v = chamberVolumeM3(motorData);
    return v === null
        ? T('common.notComputed', 'not computed')
        : numTxt((v * 1e6), 1) + ' cm³';
}

function safePlotCreate(elementId, plotData) {
    const element = document.getElementById(elementId);
    if (element && plotData) {
        try {
            const parsedData = JSON.parse(plotData);

            // Enhanced config for better responsive behavior
            const config = {
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
                // PNG dışa aktarım (v2.5.5): sabit 700x500 kaldırıldı —
                // ekrandaki gerçek boyutun 2 katı çözünürlük alınır
                // (plotly_dark.js dışa aktarım katmanıyla uyumlu).
                toImageButtonOptions: {
                    format: 'png',
                    filename: elementId,
                    scale: 2
                }
            };
            
            // Update layout for better responsiveness
            if (parsedData.layout) {
                parsedData.layout.autosize = true;
                if (!parsedData.layout.margin) {
                    // v3.0.1 (V301/N-grafik G3): tema yazı tabanı (tik 12,
                    // eksen başlığı 14, başlık 16 px) ile 60 px alt/sol pay
                    // yetmiyordu — ölçüldü: irtifa panosunda üç x eksen
                    // başlığı figürün altından kırpılıyordu; başlık alt
                    // grafik başlıklarına yaslanıyordu.
                    parsedData.layout.margin = { l: 72, r: 30, t: 80, b: 72 };
                }
                // Yükseklik: layout'taki değeri konteynere sabitle ki panel
                // içeriğe göre büyüsün (SVG taşması / panel çakışması önlenir).
                // layout.height SİLİNMEZ: autosize gizli/animasyonlu konteyneri
                // ~140px ölçüp iç çizim alanını 2px'e eziyordu (motor_plot bugı).
                // Genişlik responsive kalır (width=undefined), yükseklik sabit.
                if (parsedData.layout.height) {
                    element.style.height = parsedData.layout.height + 'px';
                }
                parsedData.layout.width = undefined;
            }
            
            Plotly.newPlot(elementId, parsedData.data, parsedData.layout, config);
            // Yeniden boyutlandırmayı config.responsive üstlenir; her
            // çağrıda window listener eklemek sızıntıya yol açıyordu

        } catch (e) {
            console.warn(`Failed to create plot for ${elementId}:`, e);
            // Yedek metinler de çevrilir: anahtar = İngilizce metnin kendisi
            // (i18n_charts.js sözleşmesi), böylece i18n_common.js'e yeni
            // anahtar eklemeden TR karşılığı sözlükten gelir.
            element.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">'
                + SRV('Plot data unavailable') + '</div>';
        }
    } else if (element) {
        element.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">'
            + SRV('No data available') + '</div>';
    }
}

// Opsiyonel grafik yükü BOŞ mu? Backend bu grafikleri her hesapta üretmez
// (irtifa/kütle kesirleri/yanma verisi olmayabilir). Boş sayılan durumlar:
// null/undefined, boş string, 'null', {error: ...}, veri dizisi boş figür.
function isPlotPayloadEmpty(plotData) {
    if (plotData === null || plotData === undefined) return true;

    if (typeof plotData === 'object') {
        if (plotData.error) return true;
        return !Array.isArray(plotData.data) || plotData.data.length === 0;
    }

    if (typeof plotData !== 'string') return true;

    const text = plotData.trim();
    if (!text || text === 'null' || text === '{}') return true;

    try {
        const parsed = JSON.parse(text);
        if (!parsed || typeof parsed !== 'object' || parsed.error) return true;
        return !Array.isArray(parsed.data) || parsed.data.length === 0;
    } catch (e) {
        return true;
    }
}

// Opsiyonel grafik paneli: veri yoksa paneli TAMAMEN gizler (boş kutu ya da
// "No data available" yazan sahte panel bırakmaz). Veri varsa paneli açıp
// safePlotCreate ile çizer. Döndürdüğü değer: çizildi mi?
function renderOptionalPlot(panelId, elementId, plotData) {
    const panel = document.getElementById(panelId);
    const empty = isPlotPayloadEmpty(plotData);

    if (panel) {
        panel.style.display = empty ? 'none' : 'block';
    }
    if (empty) return false;

    safePlotCreate(elementId, typeof plotData === 'string' ? plotData : JSON.stringify(plotData));
    return true;
}

// Display plots
function displayPlots(plots) {
    plots = plots || {};

    // Motor plot
    safePlotCreate('motor_plot', plots.motor);
    
    // Injector plot
    safePlotCreate('injector_plot', plots.injector);
    
    // Performance plots
    safePlotCreate('performance_plots', plots.performance);

    // v2.6.26: İtki-zaman eğrisi (hibrit). Veri yoksa panel GİZLENİR —
    // boş bir grafik kabı "hesap yapılmadı"yı "sonuç sıfır" gibi gösterir.
    renderHybridThrustCurve();
    
    // 3D Motor simülasyonu: önce Three.js dijital ikiz (MotorViz3D),
    // yüklenemezse backend'in Plotly 3D çıktısına düş
    let viz3dMounted = false;
    if (typeof mountMotorViz === 'function' && window.currentResults && currentResults.motor) {
        try {
            // ÖH D15 / P11B1-04 — SAHNEYE ENJEKTÖR ÇÖZÜCÜSÜNÜN SONUCU DA
            // VERİLİR. ÖLÇÜLDÜ: sahnenin `resolveInjectorSource` tercihi
            // `md.injector_results` altını arıyor; sahneye YALNIZ
            // `currentResults.motor` verildiği için o dal HİÇ ateşlenmiyor
            // ve kod sessizce `injector_design` yedeğine düşüyordu —
            // kullanıcı enjektör sekmesinde 32 delik × 0,83 mm okuyup 3B
            // plakada 3 delik × 2,06 mm görüyordu. Eksik olan tek şey
            // KABLOYDU: panelin sonucu yanıtın üst düzeyinde
            // (`data.injector`) yayımlanıyor. Motor sözlüğü DEĞİŞTİRİLMEZ
            // (sığ kopya); enjektör yoksa hiçbir şey eklenmez.
            const vizMotor = (currentResults.injector
                              && typeof currentResults.injector === 'object')
                ? Object.assign({}, currentResults.motor,
                                { injector_results: currentResults.injector })
                : currentResults.motor;
            viz3dMounted = mountMotorViz(vizMotor);
        } catch (e) {
            console.warn('MotorViz3D mount failed, falling back to Plotly 3D:', e);
        }
    }
    if (!viz3dMounted && plots.motor_3d && !plots.motor_3d.error) {
        const motor3DElement = document.getElementById('motor_3d_plot');
        if (motor3DElement) {
            try {
                const plot3D = typeof plots.motor_3d === 'string' ? JSON.parse(plots.motor_3d) : plots.motor_3d;
                motor3DElement.style.display = 'block';
                Plotly.newPlot('motor_3d_plot', plot3D.data, plot3D.layout, {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false
                });
                // Show 3D panel
                const panel3D = document.getElementById('cad3DPanel');
                if (panel3D) {
                    panel3D.style.display = 'block';
                }
            } catch (e) {
                console.warn('Failed to create 3D motor plot:', e);
                motor3DElement.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">'
                    + SRV('3D visualization unavailable') + '</div>';
            }
        }
    } else if (!viz3dMounted && plots.motor_3d && plots.motor_3d.error) {
        console.warn('3D motor plot error:', plots.motor_3d.error);
    }
    
    // Trajectory plot
    if (plots.trajectory && !plots.trajectory.error) {
        safePlotCreate('trajectory_plot', plots.trajectory);
        const trajectoryPanel = document.getElementById('trajectoryPanel');
        if (trajectoryPanel) {
            trajectoryPanel.style.display = 'block';
        }
    } else if (plots.trajectory && plots.trajectory.error) {
        console.warn('Trajectory plot error:', plots.trajectory.error);
    }

    // Opsiyonel analiz grafikleri. Bunları /calculate HER hesapta üretiyordu
    // ama hiçbir şablon çizmiyordu (ölü yük). İrtifa performansı katı ve sıvı
    // sayfalarda zaten vardı; hibritte yoktu — parite açığı kapatıldı.
    // Veri gelmezse ilgili panel gizlenir.
    renderOptionalPlot('altitudePerformancePanel', 'altitude_performance_plot',
                       plots.altitude_performance);
    renderOptionalPlot('thrustAltitudePanel', 'thrust_altitude_plot',
                       plots.thrust_altitude);
    renderOptionalPlot('massFractionsPanel', 'mass_fractions_plot',
                       plots.mass_fractions);
    renderOptionalPlot('combustionAnalysisPanel', 'combustion_analysis_plot',
                       plots.combustion_analysis);
    renderOptionalPlot('realtimeDashboardPanel', 'realtime_dashboard_plot',
                       plots.realtime_dashboard);
}

// Display design report
// L* satiri: istenen ve GERCEKLESEN L* birlikte gosterilir. Hibritte kamara
// grain'den kisa olamaz; kucuk L* degerleri bu geometrik tabanin altinda
// kalir ve boy degismez. Kullanici "L* hicbir seyi degistirmiyor" demesin
// diye gerceklesen deger ve motorun notu acikca yazilir.
function lStarRow(motorData) {
    const asked = motorData.l_star;
    const achieved = motorData.l_star_achieved;
    if (typeof asked !== 'number' && typeof achieved !== 'number') return '';
    const fmt = (v) => (typeof v === 'number' && isFinite(v)) ? numTxt(v, 2) : 'N/A';
    let value = `${fmt(asked)} m`;
    if (typeof achieved === 'number' && typeof asked === 'number'
        && Math.abs(achieved - asked) > 0.01) {
        value = `${fmt(asked)} m requested &rarr; <strong>${fmt(achieved)} m achieved</strong>`;
    }
    // ÖH D30 · P11B2-18 — SUNUCU METNİ KAÇIŞSIZ innerHTML'e giriyordu.
    // ÖLÇÜLDÜ (a2/once.json: P11B2-18_kacissiz_l_star_note = 1,
    // _escli_l_star_note = 0): `l_star_note` motor çözücüsünün serbest
    // metnidir (malzeme adı, geometri notu, kullanıcıdan gelen ad
    // parçaları taşıyabilir) ve şablon dizgisine ham gömülüyordu; içindeki
    // `<` `&` bu satırda BİÇİMLENDİRME olarak yorumlanıyordu. Rapor
    // gövdesi innerHTML ile basıldığı için bu bir metin-enjeksiyon
    // yüzeyidir. Kaçış kardeş yayıcıların (app.js:762, 944) desenidir.
    // V301/DİL: sunucu cümlesi çeviri kanalından geçer (SRV; eşleşme
    // yoksa metin aynen) — TR raporda "Requested L* = …" İngilizce kalıyordu.
    const escNote = (s2) => String(s2 == null ? '' : (typeof SRV === 'function' ? SRV(s2) : s2))
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const note = motorData.l_star_note
        ? `<div style="font-size:11px;color:#7d97a5;margin-top:2px;">${
            escNote(motorData.l_star_note)}</div>`
        : '';
    return `<tr><td>${T('app.rep.lStar', 'L* (characteristic length)')}</td>`
        + `<td>${value}${note}</td></tr>`;
}

// --- Design Report yardımcıları -------------------------------------------
// Sayısal biçimleyici: sonlu değilse em-dash (tablo kırılmaz, sahte 0 yok).
function reportNum(value, digits) {
    return (typeof value === 'number' && isFinite(value)) ? numTxt(value, digits) : '—';
}

// 'cylindrical_bore' -> 'Cylindrical bore' (backend enum'ları okunur hale gelir)
// V301/DİL (NK-7): değer formdaki bir seçiciden geliyorsa ekranda o
// seçeneğin ÇEVRİLMİŞ adı basılır (TR raporda "Conical" yerine "Konik");
// seçici/seçenek yoksa eski biçim (alt çizgi → boşluk, ilk harf büyük).
function reportLabel(value, selectId) {
    if (typeof value !== 'string' || !value) return '—';
    if (selectId && typeof document !== 'undefined' && document.getElementById) {
        try {
            const sel = document.getElementById(selectId);
            const ops = (sel && sel.options) ? sel.options : [];
            for (let i = 0; i < ops.length; i++) {
                if (ops[i].value === value && ops[i].textContent) {
                    return String(ops[i].textContent).trim();
                }
            }
        } catch (e) { /* DOM'suz bağlam: eski biçim */ }
    }
    const text = value.replace(/_/g, ' ').trim();
    return text.charAt(0).toUpperCase() + text.slice(1);
}

// [etiket, değer, birim] satırlarından rapor tablosu üretir.
function reportSection(title, rows) {
    const body = rows.map(function (row) {
        const unit = row[2] ? ` ${row[2]}` : '';
        return `<tr><td>${row[0]}</td><td>${row[1]}${unit}</td></tr>`;
    }).join('');
    return `
        <div class="report-section">
            <h6>${title}</h6>
            <table class="report-table table table-striped">
                <tbody>${body}</tbody>
            </table>
        </div>
    `;
}

// Nozul açıları (backend: motor.nozzle_angles). Katı ve sıvı sayfalarda
// tabloya çıkıyordu, hibritte hiç kullanılmıyordu — parite açığı kapatıldı.
function nozzleAnglesSection(nozzleAngles) {
    if (!nozzleAngles || typeof nozzleAngles !== 'object') return '';

    const rows = [
        [T('app.rep.nozzleType', 'Nozzle Type'), reportLabel(nozzleAngles.nozzle_type, 'nozzle_type'), ''],
        [T('app.rep.convHalfAngle', 'Convergent Half Angle'),
         reportNum(nozzleAngles.convergent_half_angle_deg, 1), '&deg;'],
        [T('app.rep.divHalfAngle', 'Divergent Half Angle'),
         reportNum(nozzleAngles.divergent_half_angle_deg, 1), '&deg;'],
        [T('app.rep.divEfficiency', 'Divergence Efficiency (lambda)'),
         reportNum(nozzleAngles.divergence_efficiency, 4), '']
    ];
    if (typeof nozzleAngles.nozzle_length_mm === 'number') {
        rows.push([T('app.rep.nozzleLength', 'Nozzle Length'),
                   reportNum(nozzleAngles.nozzle_length_mm, 1), 'mm']);
    }
    return reportSection(T('app.rep.secNozzle', 'Nozzle Geometry'), rows);
}

// Grain geometrisi (backend: motor.grain_design). Tüm uzunluklar backend'de
// zaten mm — burada tekrar ölçekleme YAPILMAZ.
function grainDesignSection(grainDesign) {
    if (!grainDesign || typeof grainDesign !== 'object') return '';

    const rows = [
        [T('app.rep.grainType', 'Grain Type'), reportLabel(grainDesign.grain_type), ''],
        [T('app.rep.grainLength', 'Grain Length'), reportNum(grainDesign.grain_length_mm, 1), 'mm'],
        [T('app.rep.grainOd', 'Grain Outer Diameter'),
         reportNum(grainDesign.grain_outer_diameter_mm, 1), 'mm'],
        [T('app.rep.portInitial', 'Initial Port Diameter'),
         reportNum(grainDesign.port_diameter_initial_mm, 1), 'mm'],
        [T('app.rep.portFinal', 'Final Port Diameter'),
         reportNum(grainDesign.port_diameter_final_mm, 1), 'mm'],
        [T('app.rep.webThickness', 'Web Thickness'), reportNum(grainDesign.web_thickness_mm, 1), 'mm'],
        [T('app.rep.grainLd', 'Grain L/D'), reportNum(grainDesign.L_over_D, 2), ''],
        [T('app.rep.segments', 'Number of Segments'), reportNum(grainDesign.number_of_segments, 0), ''],
        [T('app.rep.inhibitor', 'Inhibitor'), reportLabel(grainDesign.inhibitor), '']
    ];
    return reportSection(T('app.rep.secGrain', 'Grain Design'), rows);
}

// Tasarım özeti (backend: motor.design_summary).
// NOT: design_summary.recommendation alanı motor tarafında Türkçe üretiliyor;
// arayüz metinleri İngilizce olduğu için o alan BİLİNÇLİ olarak basılmıyor.
function designSummarySection(designSummary) {
    if (!designSummary || typeof designSummary !== 'object') return '';

    const dims = designSummary.key_dimensions || {};
    const perf = designSummary.performance || {};
    const nozzle = designSummary.nozzle || {};

    const rows = [
        [T('common.status', 'Status'), reportLabel(designSummary.status), ''],
        // V301/H-PANEL (NK-6 ek): "Toplam uzunluk" hangi tanımla? Çözücü iki
        // ayrı ad yayımlıyor (key_dimensions.total_motor_length_basis):
        // oda + lüle (ön kapak HARİÇ) ve ön kapak dahil. Etiket tanımı söyler;
        // ön kapaklı değer yayımlanmışsa ikinci satır olarak basılır.
        [T('app.rep.totalLengthChamberNozzle', 'Total Length — chamber + nozzle (forward closure excluded)'),
         reportNum((typeof dims.total_motor_length_chamber_nozzle_mm === 'number')
             ? dims.total_motor_length_chamber_nozzle_mm : dims.total_motor_length_mm, 1), 'mm'],
    ].concat((typeof dims.total_motor_length_with_caps_mm === 'number'
              && isFinite(dims.total_motor_length_with_caps_mm)) ? [
        [T('app.rep.totalLengthWithCaps', 'Total Length incl. forward closure (structural end cap)'),
         reportNum(dims.total_motor_length_with_caps_mm, 1), 'mm'],
    ] : []).concat([
        [T('app.rep.chamberDia', 'Chamber Diameter'), reportNum(dims.chamber_diameter_mm, 1), 'mm'],
        [T('app.rep.chamberLen', 'Chamber Length'), reportNum(dims.chamber_length_mm, 1), 'mm'],
        [T('app.rep.throatDia', 'Throat Diameter'), reportNum(dims.nozzle_throat_diameter_mm, 1), 'mm'],
        [T('app.rep.exitDia', 'Exit Diameter'), reportNum(dims.nozzle_exit_diameter_mm, 1), 'mm'],
        [T('app.rep.convLength', 'Convergent Section Length'),
         reportNum(nozzle.convergent_length_mm, 1), 'mm'],
        [T('app.rep.divLength', 'Divergent Section Length'),
         reportNum(nozzle.divergent_length_mm, 1), 'mm'],
        [T('app.rep.dryMass', 'Dry Mass (estimate)'), reportNum(dims.dry_mass_estimate_kg, 2), 'kg'],
        [T('app.rep.totalMass', 'Total Mass (estimate)'), reportNum(dims.total_mass_kg, 2), 'kg'],
        [T('app.rep.totalImpulse', 'Total Impulse'), reportNum(perf.total_impulse_Ns, 0), 'N&middot;s'],
        [T('common.burnTime', 'Burn Time'), reportNum(perf.burn_time_s, 2), 's']
    ]);
    // P11B2-08 — "Total Mass" ile "Total Propellant Mass" arasındaki
    // 1,39 kg'lık farkı açıklayan İKİ beyan çözücüde vardı ve rapor
    // ikisini de düşürüyordu. Cümleler ÇÖZÜCÜNÜN kendi kelimeleridir;
    // panel yeniden yazmaz, yalnız basar (SRV = varsa Türkçe karşılığı).
    let html = reportSection(T('app.rep.secSummary', 'Design Summary'), rows);
    const beyanlar = [];
    if (typeof dims.total_mass_basis === 'string' && dims.total_mass_basis) {
        beyanlar.push(['total_mass_basis', dims.total_mass_basis]);
    }
    if (typeof dims.dry_mass_basis === 'string' && dims.dry_mass_basis) {
        beyanlar.push(['dry_mass_basis', dims.dry_mass_basis]);
    }
    if (beyanlar.length) {
        html += beyanlar.map(function (b) {
            return `<p class="hd-mass-basis" style="font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:2px 0 0 0;">`
                + `<span data-field="${b[0]}" title="${b[0]}">${hdEscape(
                    b[0] === 'total_mass_basis'
                        ? T('app.rep.totalMassBasis', 'Total mass basis')
                        : T('app.rep.dryMassBasis', 'Dry mass basis'))}</span>: `
                + `${hdEscape(SRV(b[1]))}</p>`;
        }).join('');
    }
    return html;
}

// V301/E2: rapor satırlarına giren metin HTML olarak yorumlanmaz.
function raporKacis(v) {
    return String(v == null ? '' : v).replace(/&/g, '&amp;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function displayDesignReport(motorData, injectorData) {
    const reportDiv = document.getElementById('designReport');
    
    let html = `
        <div class="report-section">
            <h6>${T('app.rep.secPerformance', 'Motor Performance')}</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>${T('app.rep.ispDesignLong', 'Specific Impulse (Isp, design point at design-altitude ambient)')}</td><td>${numTxt(motorData.isp, 1)} s</td></tr>
                    <tr><td>${T('app.rep.cstarLong', 'Characteristic Velocity (C*)')}</td><td>${numTxt(motorData.c_star, 0)} m/s</td></tr>
                    <tr><td>${T('app.rep.cfLong', 'Thrust Coefficient (CF)')}</td><td>${numTxt(motorData.cf, 3)}</td></tr>
                    <tr><td>${T('app.rep.throatDia', 'Throat Diameter')}</td><td>${numTxt((motorData.throat_diameter * 1000), 1)} mm</td></tr>
                    <tr><td>${T('app.rep.exitDia', 'Exit Diameter')}</td><td>${numTxt((motorData.exit_diameter * 1000), 1)} mm</td></tr>
                    <tr><td>${T('common.f.expansionRatio', 'Expansion Ratio')}</td><td>${numTxt(motorData.expansion_ratio, 1)}</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>${T('app.rep.secGeometry', 'Motor Geometry')}</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>${T('app.rep.chamberDia', 'Chamber Diameter')}</td><td>${numTxt((motorData.chamber_diameter * 1000), 1)} mm</td></tr>
                    <tr><td>${T('app.rep.chamberLen', 'Chamber Length')}</td><td>${numTxt((motorData.chamber_length * 1000), 1)} mm</td></tr>
                    ${lStarRow(motorData)}
                    <tr><td>${T('app.rep.chamberVolume', 'Chamber Volume')}</td><td>${chamberVolumeCm3Text(motorData)}</td></tr>
                    <tr><td>${T('app.rep.portInitial', 'Initial Port Diameter')}</td><td>${numTxt((motorData.port_diameter_initial * 1000), 1)} mm</td></tr>
                    <tr><td>${T('app.rep.portFinal', 'Final Port Diameter')}</td><td>${numTxt((motorData.port_diameter_final * 1000), 1)} mm</td></tr>
                    <tr><td>${T('app.rep.regressionRate', 'Regression Rate')}</td><td>${motorData.regression_rate ? numTxt((motorData.regression_rate * 1000), 2) : 'N/A'} mm/s</td></tr>
                    <tr><td>${T('app.rep.regressionAvg', 'Avg Regression Rate')}</td><td>${motorData.regression_rate_avg ? numTxt((motorData.regression_rate_avg * 1000), 2) : 'N/A'} mm/s</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>${T('inj.title', 'Injector Design')}</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>${T('common.type', 'Type')}</td><td>${injectorData.type.charAt(0).toUpperCase() + injectorData.type.slice(1)}</td></tr>
                    <tr><td>${T('app.rep.exitVelocity', 'Exit Velocity')}</td><td>${numTxt(injectorData.exit_velocity, 1)} m/s</td></tr>
                    <tr><td>${T('app.rep.reynolds', 'Reynolds Number')}</td><td>${numTxt(injectorData.reynolds_number, 0)}</td></tr>
                    <tr><td>${T('app.rep.pressureDrop', 'Pressure Drop')}</td><td>${numTxt(injectorData.pressure_drop, 2)} bar</td></tr>
    `;
    
    // V301/E2 (devir madde 10) — TİPE ÖZEL SATIRLAR TABLODAN, TEK KAYNAK.
    // Eskiden bu blok tipe göre elle yazılmış birkaç satır basıyordu: pintle
    // için yalnız üç satır (gövde dış çapı / D_p / boşluk; gövde
    // boyutlandırılmadığında "N/A"), çarpışmalı ve koaksiyel için HİÇ satır.
    // Artık enjektör tablosunun kanon geometri satırları (bütün tiplerde,
    // displayInjectorTable(…, true).specific) aynen basılır; metin
    // ``textContent`` eşdeğeri kaçışla girer.
    const injSatir = displayInjectorTable(injectorData, true);
    (injSatir && injSatir.specific ? injSatir.specific : []).forEach(function (r) {
        const birim = (r[2] && r[2] !== '-') ? (' ' + r[2]) : '';
        html += `
                    <tr><td>${raporKacis(r[0])}</td><td>${raporKacis(r[1])}${raporKacis(birim)}</td></tr>`;
    });
    
    html += `
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>${T('app.rep.secPropellant', 'Propellant')}</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>${T('app.rep.mdotTotal', 'Total Mass Flow Rate')}</td><td>${numTxt(motorData.mdot_total, 3)} kg/s</td></tr>
                    <tr><td>${T('app.rep.mdotOx', 'Oxidizer Mass Flow Rate')}</td><td>${numTxt(motorData.mdot_ox, 3)} kg/s</td></tr>
                    <tr><td>${T('app.rep.mdotFuel', 'Fuel Mass Flow Rate')}</td><td>${numTxt(motorData.mdot_f, 3)} kg/s</td></tr>
                    <tr><td>${T('app.rep.propMassTotal', 'Total Propellant Mass')}${fieldTag('propellant_mass_total')}</td><td>${numTxt(motorData.propellant_mass_total, 2)} kg</td></tr>
                    <tr><td>${T('app.rep.oxMass', 'Oxidizer Mass')}${fieldTag('oxidizer_mass')}</td><td>${numTxt(motorData.oxidizer_mass, 2)} kg</td></tr>
                    <tr><td>${T('app.rep.fuelMass', 'Fuel Mass')}${fieldTag('fuel_mass')}</td><td>${numTxt(motorData.fuel_mass, 2)} kg</td></tr>
${loadedMassRows(motorData)}
                </tbody>
            </table>
        </div>
    `;

    // /calculate bu üç bloğu HER hesapta döndürüyordu ama hibrit sayfası
    // hiçbirini kullanmıyordu (katı/sıvı sayfalarda tabloya çıkıyorlar).
    // Kaynak öncelik: motor sonucu, yoksa üst düzey yanıt kopyası.
    const topLevel = window.currentResults || {};
    html += nozzleAnglesSection(motorData.nozzle_angles || topLevel.nozzle_angles);
    html += grainDesignSection(motorData.grain_design || topLevel.grain_design);
    html += designSummarySection(motorData.design_summary || topLevel.design_summary);

    html += `
        <div class="report-section">
            <h6>${T('app.rep.secRegression', 'Regression Rate & Port Growth')}</h6>
            <div id="designReportRegressionChart" style="min-height: 320px;"></div>
        </div>
    `;

    reportDiv.innerHTML = html;

    // Rapordaki regresyon/port sayılarının zaman eğrisi (v2.5.2: tabloda
    // sayı vardı ama grafiği yoktu). port_history yoksa başlangıç/son
    // çaptan doğrusal bir tahmin çizilir ve bu açıkça etiketlenir.
    try {
        drawDesignReportRegressionChart(motorData);
    } catch (e) {
        console.warn('Design report regression chart skipped:', e);
    }
}

function drawDesignReportRegressionChart(motorData) {
    const el = document.getElementById('designReportRegressionChart');
    if (!el || typeof Plotly === 'undefined') return;

    const ph = motorData.port_history || {};
    let time = Array.isArray(ph.time) ? ph.time.map(Number) : null;
    let portMm = Array.isArray(ph.port_diameter) ? ph.port_diameter.map(v => Number(v) * 1000) : null;
    let approximate = false;

    if (!time || !portMm || time.length < 2 || portMm.length !== time.length) {
        // Doğrusal tahmin (port geçmişi yoksa)
        // `|| 0` YOK: Number(undefined) -> NaN ve aşağıdaki `!(tb > 0)`
        // kapısı NaN'i de yakalar. Yedek yalnız bekçiyi yanıltırdı.
        const tb = Number(motorData.burn_time);
        const d0 = Number(motorData.port_diameter_initial) * 1000;
        const d1 = Number(motorData.port_diameter_final) * 1000;
        if (!(tb > 0) || !isFinite(d0) || !isFinite(d1)) {
            el.innerHTML = '<div style="padding:16px;color:#7d97a5;">'
                + T('app.chart.noPortHistory', 'Port history not available for this run.')
                + '</div>';
            return;
        }
        const n = 25;
        time = Array.from({length: n}, (_, i) => (tb * i) / (n - 1));
        portMm = time.map(t => d0 + (d1 - d0) * (t / tb));
        approximate = true;
    }

    // r(t) = 0.5 * d(D)/dt  [mm/s]
    const rate = portMm.map((_, i) => {
        if (i === 0) return 0.5 * (portMm[1] - portMm[0]) / Math.max(1e-9, time[1] - time[0]);
        if (i === portMm.length - 1) {
            return 0.5 * (portMm[i] - portMm[i - 1]) / Math.max(1e-9, time[i] - time[i - 1]);
        }
        return 0.5 * (portMm[i + 1] - portMm[i - 1]) / Math.max(1e-9, time[i + 1] - time[i - 1]);
    });

    const traces = [
        {
            x: time, y: portMm, name: T('app.chart.portDia', 'Port diameter (mm)'), type: 'scatter', mode: 'lines',
            line: {color: '#22d3ee', width: 2}
        },
        {
            x: time, y: rate, name: T('app.chart.regressionRate', 'Regression rate (mm/s)'), type: 'scatter', mode: 'lines',
            yaxis: 'y2', line: {color: '#f0a04b', width: 2, dash: 'dot'}
        }
    ];

    const layout = {
        autosize: true,
        // ÖH D34 · OH-P-07 (piksel turu, 21 Eyl 2026): kap 500 px ölçülürken sabit
        // 320 px yerleşim altında 180 px boşluk bırakıyordu; kap kadar (en az 320).
        height: Math.max(320, el.clientHeight || 0),
        margin: {t: 30, b: 45, l: 55, r: 55},
        xaxis: {title: T('common.axis.timeS', 'Time (s)')},
        yaxis: {title: T('app.chart.portDia', 'Port diameter (mm)')},
        yaxis2: {title: 'r (mm/s)', overlaying: 'y', side: 'right'},
        legend: {orientation: 'h', y: -0.22},
        // ÖH D34 · OH-GT-11 — GRAFİĞİN BAŞLIĞI VAR.
        // ÖLÇÜLDÜ (a1/once.json K5, node altında GERÇEK çizim): gerçek
        // port geçmişiyle çizilen grafikte `layout.title` BOŞ dizeydi
        // (`baslik_bos: true`); başlık yalnız doğrusal tahmin dalında,
        // hem de bir başlık değil UYARI metni olarak çıkıyordu. Raporun
        // 14 grafiğinin tek başlıksızı buydu. Başlık artık HER dalda
        // yazılır; doğrusal tahmin uyarısı ona EK olarak asılır.
        // Yeni anahtar İSTEMEZ: `app.rep.secRegression` bu grafiğin
        // üstündeki bölüm başlığının kendi anahtarıdır (EN+TR dolu).
        title: T('app.rep.secRegression', 'Regression Rate & Port Growth')
            + (approximate
                ? ' - ' + T('app.chart.linearEstimate',
                            'Linear estimate (no transient port history)')
                : '')
    };

    // Koyu tema plotly_dark.js sarmalayıcısı tarafından otomatik uygulanır.
    Plotly.newPlot(el, traces, layout, {responsive: true, displayModeBar: false});
}

// D-track sözleşmesi (v2.6.2): backend uyarıları düz metin yerine
// {code, params, severity} sözlüğü olarak döndürür. Sözlük doğrudan
// şablona gömülürse ekrana "[object Object]" basılır — bu regresyon
// v2.6.2'de yaşandı ve kritik uyarıları okunmaz hale getirdi.
//
// İç içe kayıtlar: bazı uyarıların parametresi kendisi bir uyarı kaydı ya
// da kayıt listesidir (ör. warn.solid.bates_envelope'un `options` alanı),
// bu yüzden çeviri özyinelemelidir. AnalysisDock aynı mantığı
// U.warnText olarak dışa açıyor; yüklüyse onu kullan, değilse yerel eş.
//
// ÖH Z5-A (P11B2-01): bu çevirici artık displayWarnings'in İÇİNDE değil,
// modül düzeyinde. Sebep: yapısal hüküm şeridi (structuralVerdictBlock) de
// AYNI {code, params} kayıtlarını basıyor — çözücünün adlandırılmış onarım
// önerileri. İki tüketici tek çeviriciden konuşmazsa biri sözlüğü, öteki
// ham kodu basar. (liquid.html'de aynı gerekçeyle T44'te taşınmıştı.)
function warnToText(w, depth) {
    if (window.AnalysisDock && window.AnalysisDock.ui
        && window.AnalysisDock.ui.warnText) {
        return window.AnalysisDock.ui.warnText(w);
    }
    depth = depth || 0;
    if (w === null || w === undefined) return '';
    // Düz metin dalı: {code, params} sözleşmesine geçmemiş uyarılar
    // (hrma/validation, hrma/importers, regen_cooling gibi düz
    // İngilizce üretenler) buradan geçiyor. serverText sözlük + desen
    // sırasıyla çevirir, eşleşme yoksa metni AYNEN döndürür.
    // NOT: bu yorumda "yıldızlı yol" yazmayın — tests/test_i18n_common.py
    // yorum temizleyicisi satır yorumunun içindeki eğik-çizgi-yıldızı
    // blok yorum başlangıcı sanıp dosyanın gerisini siliyor (ölçüldü).
    if (typeof w === 'string') return SRV(w);
    if (Array.isArray(w)) {
        return w.map(x => warnToText(x, depth + 1)).filter(Boolean).join(' · ');
    }
    if (typeof w !== 'object') return String(w);
    if (!w.code) return SRV(w.message || w.text || JSON.stringify(w));
    if (depth > 4) return w.code;
    const p = {};
    Object.keys(w.params || {}).forEach(k => {
        const v = w.params[k];
        p[k] = (v && typeof v === 'object') ? warnToText(v, depth + 1) : v;
    });
    return (window.I18N && window.I18N.tf)
        ? window.I18N.tf(w.code, p, w.fallback || w.code)
        : (w.fallback || w.code);
}

// Uyarı kaydının KENDİ önem derecesi. Kayıt sözlük değilse (düz metin) hiçbir
// önem iddia edilmez — kritik rozeti KAZANILARAK basılır, varsayılarak değil.
function warnIsCritical(w) {
    return !!(w && typeof w === 'object' && !Array.isArray(w)
              && String(w.severity || '').toLowerCase() === 'critical');
}

// v3.0.1 (V301/H3): sunucunun 'info' önemli kaydı (ör. doymuş N₂O girişinde
// K_c = 0 notu) uyarı değil bilgidir; kendi BİLGİ rozetiyle basılır, amber
// "UYARI" diye abartılmaz.
function warnIsInfo(w) {
    return !!(w && typeof w === 'object' && !Array.isArray(w)
              && String(w.severity || '').toLowerCase() === 'info');
}

// ÖH Z5-A (OH-Z2-05 + P14M3-04): sonuç sözlüğündeki TÜM uyarı kanalları tek
// yerden toplanır. İki çağıran vardı (hesap sonrası ve dil değişimi) ve
// ikincisi motor uyarılarını hiç okumuyordu — dil değiştiren kullanıcı
// motorun kritik erime uyarılarını ekrandan KAYBEDİYORDU (ölçüldü: hibrit
// varsayılan koşumda 5 kayıt -> 0). Toplayıcı ortak olduğu için o ayrışma
// artık yapısal olarak mümkün değil.
//
// Kanallar: motor tasarım uyarıları, motorun GİRDİ denetimi (input_warnings —
// sıvı çözücüde cidar kalınlığı gibi kritik girdi hükümleri buradan çıkar) ve
// enjektör uyarıları. Yoksa boş dizi; uydurma kayıt üretilmez.

// ÖH D16 (OH-D15-05) — TASARIM KAPISI DEFTERİ (`motor.design_gate_checks`).
// D15/P1B1-06 bu defteri motorda kurdu ve uç onu YAYIMLIYOR (ölçüldü,
// a2/once.json: eta_c_star=0,30 + G_ox=900 koşumunda 2 hüküm yanıtta), ama
// app.js dosyasında `design_gate_checks` GEÇMİYORDU (ölçülen geçiş sayısı 0):
// kanal vardı, kapı yoktu. Kullanıcı bant dışı bir c* verimini, taşkın
// akısını ya da sessiz oksitleyici yedeğini ekranda HİÇ görmüyordu.
//
// Metin niye sözlükten değil: bu kulvarda i18n anahtar dosyası
// değiştirilemez ve `test_i18n_common.py::test_every_used_key_exists_in_
// dictionary` sözlükte olmayan bir anahtarın kullanılmasını zaten
// yasaklıyor. Bu yüzden kayıt KODSUZ üretilir; `warnToText` kodsuz kaydı
// `SRV(message)` ile çevirir (sunucu-metni sözlüğü + desen, eşleşme yoksa
// metin aynen geçer) — motorun kendi yayımladığı `basis` cümlesi ve sayılar
// dışında hiçbir şey uydurulmaz. Kodlu uyarıya geçiş ui/i18n kulvarının
// kalemidir.
//
// İki yardımcı NİYE İÇERİDE: `collectResultWarnings` DOM'suz koşucularda
// (tests/test_d15_ui_paneller_a1.py'nin node kum havuzu, tests/
// test_z5_teslim_kanali.py) kaynaktan AD AD çekilip tek başına çalıştırılıyor
// — o koşucular yüklenecek fonksiyon adlarını elle sayıyor. Yardımcılar modül
// düzeyinde kalsaydı çekilen gövde tanımsız ada başvurur ve koşucu ÇÖKERDİ
// (ölçüldü: 12_kirmizi_tasnifi.json — bu beş test yalnız bende kırmızıydı,
// tabanda yeşildi). İç içe tanım, tek çıkışlı fonksiyonu kendi kendine
// yeterli kılar; başka bir kulvarın bekçi dosyasına dokunmak gerekmez.
function collectResultWarnings(results) {
    function gateNumberText(v) {
        if (typeof v !== 'number' || !isFinite(v)) return String(v);
        if (Number.isInteger(v)) return String(v);
        return String(parseFloat(v.toPrecision(6)));
    }

    function designGateChecksToWarnings(gates) {
        if (!Array.isArray(gates)) return [];
        return gates.filter(function (g) {
            // 'pass' hükümleri bilerek yayımlanıyor (geçtiğini görmek
            // değerlidir) ama uyarı DEĞİLDİR — panele geçen bant/kırpma/
            // yedek hükümleridir.
            return g && typeof g === 'object'
                && String(g.status || '').toLowerCase() !== 'pass';
        }).map(function (g) {
            const parca = [];
            parca.push('Design gate ' + String(g.gate || 'unknown')
                       + ': ' + String(g.status || 'reported').toUpperCase());
            if (g.quantity !== undefined && g.value !== undefined) {
                parca.push(String(g.quantity) + ' = ' + gateNumberText(g.value)
                           + (g.unit ? ' ' + String(g.unit) : ''));
            }
            if (Array.isArray(g.band) && g.band.length === 2) {
                parca.push('band ' + gateNumberText(g.band[0]) + '-'
                           + gateNumberText(g.band[1]));
            }
            if (g.limit !== undefined) {
                parca.push('limit ' + gateNumberText(g.limit)
                           + (g.unit ? ' ' + String(g.unit) : ''));
            }
            if (g.requested !== undefined) {
                parca.push('requested ' + gateNumberText(g.requested));
            }
            if (g.used_instead !== undefined) {
                parca.push('used instead: ' + String(g.used_instead));
            }
            if (g.source) { parca.push('source: ' + String(g.source)); }
            const govde = parca.join(' | ');
            return {
                // Önem KAZANILARAK basılır: kayıt kendi severity'sini
                // yayımlıyorsa o kullanılır, yoksa 'warning' varsayılır —
                // kritik rozeti varsayımla dağıtılmaz.
                severity: (typeof g.severity === 'string' && g.severity)
                    ? g.severity : 'warning',
                message: g.basis ? (govde + ' — ' + String(g.basis)) : govde,
                design_gate: String(g.gate || 'unknown')
            };
        });
    }

    const r = results || {};
    const motor = r.motor || {};
    const engine = (motor.warnings || motor.design_warnings) || [];
    const inputs = motor.input_warnings || r.input_warnings || [];
    const injector = (r.injector && r.injector.warnings) || [];
    const gates = designGateChecksToWarnings(
        motor.design_gate_checks || r.design_gate_checks);
    return [].concat(Array.isArray(engine) ? engine : [],
                     Array.isArray(inputs) ? inputs : [],
                     Array.isArray(injector) ? injector : [],
                     gates);
}

// Display warnings — motor/girdi/enjektör uyarıları + /calculate cevabındaki
// üst seviye validation objesi birlikte listelenir:
//   validation = { overall_status, critical_warnings[], regular_warnings[],
//                  total_warnings, validation_passed }
// validation.critical_warnings kırmızı (CRITICAL), regular amber (WARNING).
// Kanaldan gelen kayıtlar KENDİ severity alanlarına göre ayrışır: motorun
// severity:'critical' uyarısı (ör. cidar erime sıcaklığını aşıyor) artık
// amber 'WARNING' olarak basılmaz — kırmızı CRITICAL rozeti alır (P11B2-06).
// Hiç uyarı yoksa panel gizli kalır.
// ÖH D28 / P12bB3-22 — "Design validation" satırının TEK yazıcısı.
// Metin SUNUCUDAN gelir (validation.overall_status, warnToText ile çözülür);
// panel kendi hükmünü ÜRETMEZ. Sunucu hüküm yayımlamadıysa olumlu bir şey
// yazılmaz — kazanılmamış hüküm yayımlanmaz (fail-closed).
function setDesignValidationVerdict(validation) {
    const el = document.getElementById('design_validation_verdict');
    if (!el) return;   // bu düğüm yalnız gelişmiş sayfada var
    if (validation && validation.overall_status) {
        el.textContent = warnToText(validation.overall_status);
        el.classList.remove('dv-unpublished');
    } else {
        el.textContent = T('app.warn.validationNotPublished',
            'The server published no validation verdict for this run.');
        el.classList.add('dv-unpublished');
    }
    // i18n yeniden çevirisi bu düğümü artık EZMEMELİ: metin sunucudan geldi.
    el.removeAttribute('data-i18n');
}

function displayWarnings(warnings, validation) {
    setDesignValidationVerdict(validation);
    const warningsPanel = document.getElementById('warningsPanel');
    const warningsList = document.getElementById('warningsList');

    // Check if elements exist (they might not exist on all pages)
    if (!warningsPanel || !warningsList) {
        console.warn('Warning elements not found on this page');
        return;
    }

    const critical = (validation && Array.isArray(validation.critical_warnings))
        ? validation.critical_warnings : [];
    const regular = (validation && Array.isArray(validation.regular_warnings))
        ? validation.regular_warnings : [];
    const injector = Array.isArray(warnings) ? warnings : [];

    if (!critical.length && !regular.length && !injector.length) {
        warningsList.innerHTML = '';
        warningsPanel.style.display = 'none';
        return;
    }

    // V3 SG-05 (12 Eki): uyarı metni sunucudan gelir (içe aktarıcı ve
    // doğrulama düz metni, {code, params} parametreleri) ve innerHTML'e
    // gidiyordu; HTML olarak değil METİN olarak girer. Kaçış, bu dosyanın
    // kardeş yayıcılarındaki desendir (bkz. l_star_note, P11B2-18).
    const escWarn = s2 => String(s2 == null ? '' : s2)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const item = (label, text, cls) =>
        `<div class="warning-item ${cls}">` +
        `<span class="warning-tag">${label}</span>` +
        `<span class="warning-text">${escWarn(warnToText(text))}</span></div>`;

    let html = '';
    if (validation && validation.overall_status) {
        // Durum satırı kırmızıya, kanaldan gelen kritik kayıtlar yüzünden de
        // döner: "0 kritik doğrulama uyarısı" ile "0 kritik uyarı" aynı şey
        // değil (motorun erime hükümleri bu kanaldan geliyor).
        const statusCls = (critical.length || injector.some(warnIsCritical))
            ? 'warning-status-critical' : 'warning-status-regular';
        // 2026-08-03 (Faz 6, T31): burada `${validation.overall_status}` vardı.
        // overall_status da uyarılar gibi {code, params, severity} sözlüğüdür
        // (validation_system.py:245-249), düz metin değil — şablona doğrudan
        // gömülünce ekrana "VALIDATION STATUS: [OBJECT OBJECT]" basılıyordu.
        // Yukarıdaki warnToText bu şekli zaten çözüyor ve kendi yorumunda aynı
        // regresyonun v2.6.2'de yaşandığını yazıyor; uyarı metinleri ondan
        // geçiyordu, durum satırı geçmiyordu.
        html += `<div class="warning-status ${statusCls}">`
            + T('app.warn.validationStatus', 'Validation status:') + ' '
            + `${escWarn(warnToText(validation.overall_status))}</div>`;
    }
    const critLabel = T('app.warn.critical', 'CRITICAL');
    const warnLabel = T('app.warn.warning', 'WARNING');
    critical.forEach(w => { html += item(critLabel, w, 'warning-critical'); });
    regular.forEach(w => { html += item(warnLabel, w, 'warning-regular'); });
    // P11B2-06: burada tüm kanal amber basılıyordu. Motorun erime hükümleri
    // (warn.thermal.wall_exceeds_melting vb.) severity:'critical' taşıyor ama
    // ekranda sıradan bir uyarıdan ayırt edilemiyordu — hem rozet metni hem
    // sınıf (dolayısıyla kırmızı kenar/renk) artık kaydın kendi önemine bağlı.
    const infoLabel = T('app.warn.info', 'INFO');
    injector.forEach(w => {
        if (warnIsCritical(w)) html += item(critLabel, w, 'warning-critical');
        else if (warnIsInfo(w)) html += item(infoLabel, w, 'warning-info');
        else html += item(warnLabel, w, 'warning-regular');
    });

    warningsList.innerHTML = html;
    warningsPanel.style.display = 'block';
}

// Export report function
// Ana rapor indirmesi: v2.5.2'den itibaren düz .txt yerine PDF
// (/api/export-pdf/summary). Sunucu PDF üretemezse okunabilir metin
// rapora düşer — sessiz başarısızlık yok.
async function exportReport() {
    if (!currentResults) {
        showError(T('app.msg.noResultsExport', 'No results to export'));
        return;
    }

    const motor = currentResults.motor || {};
    const name = motor.motor_name || 'HRMA_Motor';

    // ÖH D36 · U-7/U-8 — ÖZET PDF'İN TEK YOLU.
    // ÖLÇÜLDÜ (raw/OH/D36/onemli2-hibrit/a1/once.json U78, örnek hibrit
    // proje, gerçek tarayıcı): "Sonuçları Dışa Aktar" ile "Özet PDF" AYNI
    // uca (/api/export-pdf/summary) giden AYNI PDF'i (22548 B) iki ayrı kod
    // yolundan indiriyordu. Her tık 1 istek, 1 blob, 1 indirme; "çift blob"
    // ölçülmedi. Ama bu yol ekranda HİÇBİR iz bırakmıyordu (mesaj yok,
    // durum satırı yok) ve dosya adı yanıtta olmayan motor_name alanından
    // kurulduğu için daima "HRMA_Motor_summary_report.pdf" idi. Sayfa tek
    // yolu (exportAnalysisPDF: durum satırı + proje adlı dosya) sunuyorsa
    // oraya bağlanır; PDF üretilemezse aşağıdaki içerik kapısı ve metin
    // rapor yedeği aynen çalışır (sessiz yedek yok).
    const tekPdfYolu = (typeof window !== 'undefined'
                        && typeof window.exportAnalysisPDF === 'function')
        ? window.exportAnalysisPDF : null;

    try {
        if (tekPdfYolu) {
            await tekPdfYolu('summary', { throwOnFail: true });
            return;
        }
        const response = await fetch('/api/export-pdf/summary', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                motor_data: motor,
                analysis_results: currentResults
            })
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        // P11B2-24 KAPI 2 — İNEN DOSYA GERÇEKTEN PDF Mİ?
        // Ölçülen: uç BOŞ gövdeye bile HTTP 200 + 5.632 B döndürüyor ve
        // app.js yalnız `response.ok`'a bakıp blob'u `.pdf` adıyla
        // indiriyordu; 200 dönen bir HTML/JSON hata sayfası da aynı adla
        // inerdi. Kapı iki şeye bakar: sunucunun ilan ettiği içerik tipi
        // ve dosyanın kendi imzası (`%PDF-`). İkisinden biri tutmuyorsa
        // dosya İNMEZ — metin rapor yedeğine düşülür (aşağısı).
        const blob = await response.blob();
        await assertPdfBlob(blob, response);
        downloadBlobAs(blob, `${name}_summary_report.pdf`);
        return;
    } catch (e) {
        // ÖH D17 / P11B2-24 ŞARTI — YEDEĞE SESSİZ DÜŞÜLMEZ.
        // ÖLÇÜLDÜ (raw/OH/D17/arayuz/a1/once.json M4): içerik kapısı
        // (assertPdfBlob) fırlattığında bu dal YALNIZ console.warn yazıyordu;
        // kullanıcı istediği PDF yerine sessizce bir .txt indirildiğini
        // ekranda hiç görmüyordu (catch_dalinda_yalniz_console_warn=true).
        // Kapının hükmü artık ekrana da iner: ne istendiği, neden
        // verilemediği ve yerine ne indirildiği söylenir.
        console.warn('PDF report unavailable, falling back to text report:', e);
        showWarning(T('app.msg.pdfReportFallback',
                      'The PDF report failed its content check, so a plain-text '
                      + 'report was downloaded instead')
                    + ': ' + (e && e.message ? e.message : String(e)));
    }

    const inj = currentResults.injector || {};
    const f = (v, d) => (typeof v === 'number' && isFinite(v)) ? numTxt(v, d) : 'N/A';
    let report = T('app.txt.title', 'HYBRID ROCKET MOTOR ANALYSIS REPORT') + '\n';
    report += '=====================================\n\n';
    report += T('app.txt.performance', 'MOTOR PERFORMANCE') + ':\n';
    report += `${T('app.metric.ispDesign', 'Isp (design point, at design-altitude ambient)')}: ${f(motor.isp, 1)} s\n`;
    report += `${T('app.metric.thrust', 'Thrust')}: ${f(motor.thrust, 0)} N\n`;
    report += `${T('app.metric.pc', 'Chamber Pressure')}: ${f(motor.chamber_pressure, 1)} bar\n`;
    report += `${T('app.metric.mdot', 'Mass Flow Rate')}: ${f(motor.mdot_total, 3)} kg/s\n\n`;
    report += T('inj.title', 'Injector Design').toUpperCase() + ':\n';
    report += `${T('common.type', 'Type')}: ${inj.type || 'N/A'}\n`;
    report += `${T('app.rep.exitVelocity', 'Exit Velocity')}: ${f(inj.exit_velocity, 1)} m/s\n`;
    report += `${T('app.rep.reynolds', 'Reynolds Number')}: ${f(inj.reynolds_number, 0)}\n`;
    report += `${T('app.rep.pressureDrop', 'Pressure Drop')}: ${f(inj.pressure_drop, 2)} bar\n`;
    // V301/E2 (devir madde 12) — tipe özel enjektör satırları (pintle'da E1
    // kanon geometrisi dahil) ekrandaki tablonun AYNI satırlarıdır.
    try {
        const injSatir = displayInjectorTable(inj, true);
        (injSatir && injSatir.specific ? injSatir.specific : []).forEach(function (r) {
            const birim = (r[2] && r[2] !== '-') ? (' ' + r[2]) : '';
            report += `${r[0]}: ${r[1]}${birim}\n`;
        });
    } catch (e) {
        report += T('app.txt.injRowsFailed',
                    'INJECTOR ROWS COULD NOT BE WRITTEN — this section is incomplete')
                  + ': ' + (e && e.message ? e.message : String(e)) + '\n';
    }
    report += '\n';
    report += ceaKarsilastirmaMetni(currentResults);

    // ÖH D25 / P11B2-14 — İNEN RAPOR EKRANDAKİ UYARILARIN TAMAMINI TAŞIR.
    //
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D25/arayuz/a2/once.json): bu blok
    // YALNIZ `inj.warnings` yazıyordu (taşınan kanal sayısı 1/5). Ekranda
    // ise BEŞ kanal var: motor tasarım uyarıları, motorun GİRDİ denetimi
    // (`input_warnings`), tasarım kapısı defteri (`design_gate_checks`),
    // enjektör ve `validation.critical_warnings` / `regular_warnings`.
    // Yani PDF üretilemediğinde kullanıcının eline geçen tek belge,
    // KRİTİK hükümleri düşürülmüş bir rapordu — üstelik bu dal tam da
    // "PDF alınamadı" vakasında çalışıyor.
    //
    // Kaynak TEK: ekranı besleyen `collectResultWarnings` + `validation`
    // aynen okunur; burada yeniden sınıflandırma YAPILMAZ ve uydurma
    // kayıt üretilmez. Kritik olanlar ayrı başlıkta ve ADIYLA geçer.
    const kritik = (currentResults.validation
                    && Array.isArray(currentResults.validation.critical_warnings))
        ? currentResults.validation.critical_warnings : [];
    const olagan = (currentResults.validation
                    && Array.isArray(currentResults.validation.regular_warnings))
        ? currentResults.validation.regular_warnings : [];
    let cozucu = [];
    try {
        cozucu = collectResultWarnings(currentResults) || [];
    } catch (e) {
        // Toplayıcı çökerse rapor SESSİZ kalmaz: eksikliği yazar.
        cozucu = [];
        report += T('app.txt.warnCollectFailed',
                    'WARNING CHANNELS COULD NOT BE READ — this report is '
                    + 'incomplete') + ': ' + (e && e.message ? e.message : String(e))
                  + '\n\n';
    }
    const satirla = (w) => {
        const t = warnToText(w);
        return (typeof t === 'string' && t) ? t : '';
    };
    if (kritik.length > 0) {
        report += T('app.txt.criticalWarnings', 'CRITICAL WARNINGS') + ':\n';
        kritik.forEach(w => {
            const t = satirla(w);
            if (t) report += `- ${t}\n`;
        });
        report += '\n';
    }
    const digerleri = [].concat(cozucu, olagan);
    if (digerleri.length > 0) {
        report += T('common.warnings', 'Warnings').toUpperCase() + ':\n';
        digerleri.forEach(w => {
            const t = satirla(w);
            if (t) report += `- ${t}\n`;
        });
        report += '\n';
    }
    if (kritik.length === 0 && digerleri.length === 0) {
        report += T('app.txt.noWarnings', 'No warnings were published for '
                    + 'this run.') + '\n\n';
    }

    downloadBlobAs(new Blob([report], {type: 'text/plain'}), `${name}_report.txt`);
}

// V301/E2 (devir madde 12) — metin raporunda NASA CEA karşılaştırması.
// Kaynak: yanıtın ``cea_comparison`` bloğu (K kulvarı, şema
// 'hrma.cea_comparison/1'). Blok yoksa bölüm YAZILMAZ; mevcut değilse
// nedeni (kodu) yazılır. Sayılar bloktan aynen gelir, uydurulmaz; eşik
// uygulanmaz (blok bir danışma karşılaştırmasıdır).
function ceaKarsilastirmaMetni(sonuc) {
    const cc = sonuc && sonuc.cea_comparison;
    if (!cc || cc.schema !== 'hrma.cea_comparison/1') return '';
    const f = (v, d) => (typeof v === 'number' && isFinite(v)) ? numTxt(v, d) : '—';
    let m = T('app.txt.ceaTitle', 'NASA CEA COMPARISON (advisory)') + ':\n';
    if (cc.status !== 'available') {
        const kod = cc.reason && cc.reason.code ? String(cc.reason.code) : '—';
        return m + TF('app.txt.ceaUnavailable', { code: kod },
                      'Comparison unavailable (code {code}).') + '\n\n';
    }
    const np = cc.operating_point || {};
    m += TF('app.txt.ceaPoint',
            { pc: f(np.chamber_pressure_bar, 3), of: f(np.of_ratio, 3),
              eps: f(np.expansion_ratio, 4) },
            'Same operating point as this run: Pc = {pc} bar, O/F = {of}, eps = {eps}.')
         + '\n';
    (Array.isArray(cc.rows) ? cc.rows : []).forEach(function (r) {
        if (!r || typeof r !== 'object') return;
        const ad = (typeof window !== 'undefined'
                    && typeof window._ceaNicelikAdi === 'function')
            ? window._ceaNicelikAdi(r.quantity) : String(r.quantity || '');
        const d = (typeof r.delta_pct === 'number' && isFinite(r.delta_pct))
            ? ((r.delta_pct > 0 ? '+' : '') + numTxt(r.delta_pct, 3) + ' %') : '—';
        m += `- ${ad} [${r.unit || ''}]: HRMA ${f(r.hrma, 4)} / CEA ${f(r.cea, 4)} (Δ ${d})\n`;
    });
    m += T('app.txt.ceaNote',
           'Δ % = 100 × (HRMA − CEA) / CEA. No pass/fail threshold is applied. '
           + 'Advisory only — this comparison changes none of the numbers HRMA publishes.')
         + '\n\n';
    return m;
}

function downloadBlobAs(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// ÖH D22 / P17B4-02 — fetch() AĞ KOPMASININ TARAYICI İMZALARI (tek kaynak).
// fetch, isteği hiç tamamlayamadığında bir `TypeError` atar; ayırt edici tek
// şey mesaj metnidir ve metin tarayıcı ailesine göre değişir:
//   Chrome / Edge / Chromium  : "Failed to fetch"
//   Firefox                   : "NetworkError when attempting to fetch resource."
//   Safari / WKWebView        : "Load failed"   (paketli HRMA penceresi bunu kullanır)
// Liste burada TEK yerde durur; sınıflandırıcı bunu okur.
const FETCH_KOPMASI =
    /Failed to fetch|NetworkError when attempting to fetch|Load failed|Network request failed/i;

// Advanced Error Handler
// ==================================================================
// P11B2-16 — SUNUCUNUN HAM GÖVDESİ KULLANICIYA BASILMAZ
// ==================================================================
// ÖLÇÜLDÜ (docs/scofield/raw/OH/D29/arayuz-panel/a3/once.json):
// `calculate()` hatada `body: ${errorText}` diyerek Flask'ın gövdesini
// (500'de HTML yığın izi) hata mesajına gömüyordu ve `handleError`
// bu mesajı `Original: ...` satırıyla `alert()` içine basıyordu —
// kullanıcı kesilmiş, biçimsiz, kopyalanamayan bir HTML parçası
// görüyordu (`ham_govde_hata_mesajinda: 1`,
// `alert_ham_error_message: true`).
//
// KAPI (fail-closed, doktrin 1): sunucunun ADLANDIRILMIŞ hatası varsa O
// basılır; yoksa hiçbir şey uydurulmaz — gövdenin TÜRÜ ve BOYUTU adıyla
// söylenir ve tam gövdenin konsolda olduğu yazılır (console.error zaten
// basıyor). Düz metin gövde kırpılır ve kırpıldığı BEYAN edilir.
const HATA_GOVDE_TAVANI = 300;

//: Etiketleri söker, boşluğu tekleştirir, tavana kırpar. Kırpma sessiz
//: değildir: kaç bayt olduğu ve tamamının nerede olduğu yazılır.
function hataGovdeOzeti(govde) {
    const ham = String(govde == null ? '' : govde);
    const duz = ham.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (!duz) return '';
    if (duz.length <= HATA_GOVDE_TAVANI) return duz;
    const kirpik = '[truncated; {n} bytes total, full body in the browser console]';
    return duz.slice(0, HATA_GOVDE_TAVANI) + ' … ' + ((typeof TF === 'function')
        ? TF('app.err.truncated', { n: ham.length }, kirpik)
        : kirpik.replace('{n}', String(ham.length)));
}

//: Sunucu hatasının kullanıcıya gösterilecek metni. Sıra: (1) yapılı
//: JSON hatası -> alan ADIYLA, (2) HTML gövde -> tür + boyut beyanı,
//: (3) düz metin -> kırpılmış özet.
// V301/E2 (devir madde 7) — /calculate 4xx RET GÖVDESİ KULLANICIYA İNER.
// ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ayberk1/enjektor-genel/
// once_en_ekran.json ``hata_422``): kullanıcı tank basıncı doymanın altında
// iken bildirim "Source: Network/Backend · Message: Server communication
// error · Original: HTTP 422: tank_pressure_below_saturation
// [tank_pressure]" diyordu — sunucunun AÇIKLAMA cümlesi (neden reddedildi,
// ne yapmalı) hiç görünmüyordu; ret bir iletişim arızası gibi duruyordu.
// Bütün yeni 422'ler (pintle, port zarfı, tank, malzeme, enjektör elemanı)
// aynı yoldan geçer. Metin TEK çözücüden (reject_body.js HRMAReject.metni):
// [kod] cümle · geçersiz alanlar · eksik alanlar. Kesilmez. Sunucu cümlesi
// sözlükte/desende varsa çevrilir (SRV), yoksa EN kalır (uydurma yok).
function sunucuRetHatasi(status, contentType, govde) {
    let yapili = null;
    try { yapili = JSON.parse(String(govde == null ? '' : govde)); } catch (e) { yapili = null; }
    const cozucu = (typeof window !== 'undefined' && window.HRMAReject
                    && typeof window.HRMAReject.metni === 'function')
        ? window.HRMAReject : null;
    if (status >= 400 && status < 500 && cozucu && yapili
            && typeof yapili === 'object' && !Array.isArray(yapili)) {
        const kopya = Object.assign({}, yapili);
        if (typeof kopya.message === 'string' && kopya.message) {
            kopya.message = SRV(kopya.message);
        } else if (typeof kopya.error === 'string' && kopya.error) {
            kopya.error = SRV(kopya.error);
        }
        const hata = new Error(cozucu.metni(kopya, status));
        hata.hrmaReject = {
            status: status,
            code: (typeof yapili.error === 'string') ? yapili.error
                : ((typeof yapili.status === 'string') ? yapili.status : ''),
        };
        return hata;
    }
    return new Error(sunucuHataMetni(status, contentType, govde));
}

function sunucuHataMetni(status, contentType, govde) {
    const ctype = String(contentType || 'unknown content-type').split(';')[0];
    const ham = String(govde == null ? '' : govde);
    let yapili = null;
    try { yapili = JSON.parse(ham); } catch (e) { yapili = null; }
    if (yapili && typeof yapili === 'object' && !Array.isArray(yapili)) {
        const alan = ['error', 'message', 'detail', 'reason']
            .find(k => typeof yapili[k] === 'string' && yapili[k]);
        if (alan) {
            const nerede = (typeof yapili.field === 'string' && yapili.field)
                ? ' [' + yapili.field + ']' : '';
            return `HTTP ${status}: ` + SRV(yapili[alan]) + nerede;
        }
    }
    if (/^\s*</.test(ham)) {
        return `HTTP ${status}: the server returned an unstructured `
            + `${ctype} body (${ham.length} bytes) instead of a named error; `
            + 'the full body is in the browser console.';
    }
    const ozet = hataGovdeOzeti(ham);
    return `HTTP ${status}` + (ozet ? ': ' + ozet : '');
}

function handleError(error, context = 'Unknown') {
    console.group('ERROR DETAILS');
    console.error('Context:', context);
    console.error('Error Type:', error.constructor.name);
    console.error('Error Message:', error.message);
    console.error('Stack Trace:', error.stack);
    
    // Check for specific error types
    let errorSource = 'Unknown';
    let userMessage = error.message;
    
    if (error && error.hrmaReject) {
        // V301/E2: sunucunun ADLI reddi bir iletişim arızası DEĞİLDİR;
        // gerekçe cümlesi olduğu gibi (kesilmeden) mesaj satırına iner.
        errorSource = TF('app.err.srcRejected', { status: error.hrmaReject.status },
                         'Input rejected by the server (HTTP {status})');
        userMessage = error.message;
    } else if (error.message.includes('pattern')) {
        errorSource = T('app.err.srcForm', 'Form Validation');
        userMessage = T('app.err.msgForm', 'Form validation error - check input formats');
    } else if (error.message.includes('HTTP')) {
        errorSource = T('app.err.srcNetwork', 'Network/Backend');
        userMessage = T('app.err.msgNetwork', 'Server communication error');
    } else if (FETCH_KOPMASI.test(error.message)) {
        // ÖH D22 / P17B4-02 — AĞ KOPMASINA "veri tipi uyuşmazlığı" DENMEZ.
        // ÖLÇÜLDÜ (raw/OH/D22/arayuz/a1/once.json M4, taban b84b10a):
        // sunucu öldürülüp Hesapla'ya basıldığında fetch() bir TypeError
        // atar ve aşağıdaki `instanceof TypeError` dalı onu yakalayıp
        // "Data type mismatch in calculations" diyordu — P17 turunda
        // yakalanan alert gövdesi birebir bu. Üç tarayıcı ailesinin üçü de
        // (3/3 yanlış teşhis) bu dala düşüyordu. Kullanıcıya yanlış teşhis
        // koymak beyanı ÇÖZÜM değil KUSUR yapar: sunucusu ölmüş kişi
        // girdilerinde tip hatası arar.
        // Kapı: fetch'in ağ kopması imzaları TypeError dalından ÖNCE
        // sınanır. Sabit tek kaynaktan (FETCH_KOPMASI) gelir; imzalar
        // uydurma değil, tarayıcıların gerçek metinleridir.
        errorSource = T('app.err.srcConnection', 'Network/Connection');
        userMessage = T('app.err.msgConnection',
            'Could not reach the HRMA server (the request never completed). '
            + 'The server may have stopped or the connection was interrupted.');
    } else if (error instanceof TypeError) {
        errorSource = T('app.err.srcType', 'JavaScript Type Error');
        userMessage = T('app.err.msgType', 'Data type mismatch in calculations');
    } else if (error instanceof ReferenceError) {
        errorSource = T('app.err.srcReference', 'JavaScript Reference Error');
        userMessage = T('app.err.msgReference', 'Missing function or variable');
    } else if (error.message.includes('JSON')) {
        errorSource = T('app.err.srcParsing', 'Data Parsing');
        userMessage = T('app.err.msgParsing', 'Invalid data format received from server');
    }
    
    console.error('Error Source:', errorSource);
    console.groupEnd();
    
    // V301/DİL (NK-22 ek): bağlam kod adıyla değil ekran diliyle; "Özgün"
    // satırı "Mesaj" ile AYNI metinse ikinci kez basılmaz (ölçüldü: 45 bar
    // tank reddi kutuda iki kez yazıyordu).
    const baglamMetni = (context === 'Main Calculation Function')
        ? T('app.err.ctxMain', 'Main calculation') : context;
    const ozgunSatiri = (hataGovdeOzeti(error.message) !== userMessage)
        ? `\n- ${T('app.err.original', 'Original')}: ${hataGovdeOzeti(error.message)}`
        : '';
    // Show detailed error to user
    const detailedError = `
${T('app.err.detected', 'ERROR DETECTED')}

${T('app.err.source', 'Source')}: ${errorSource}
${T('app.err.context', 'Context')}: ${baglamMetni}
${T('app.err.message', 'Message')}: ${userMessage}

${T('app.err.technical', 'Technical Details')}:
- ${T('common.type', 'Type')}: ${error.constructor.name}${ozgunSatiri}
- ${T('app.err.time', 'Time')}: ${new Date().toLocaleString()}

${T('app.err.console', 'Check browser console for full stack trace.')}
    `;

    // ÖH D37 A1a · CW-U6: yerli pencere yerine sayfa içi, kapatılabilir
    // bildirim (metin aynı; odak bildirime taşınır).
    showNotice(detailedError.trim(), 'error');
    return { source: errorSource, context, originalError: error };
}

// ==================================================================
// ÖH D37 A1a · CW-U6 — HATA/BİLGİ İLETİSİ SAYFA İÇİ BİLDİRİMDİR
// ==================================================================
// ÖLÇÜLDÜ (docs/scofield/raw/OH/A1a/hibrit-beyan/a1/once.json M3):
// `showError`, `showInfo` ve `handleError` üçü de işletim sisteminin
// engelleyici `alert()` kutusunu açıyordu (3/3 çağrı `alert`e gitti,
// sayfada 0 bildirim). Sayfanın geri kalanı `showMessage` ile sayfa içi
// kutu kullanıyor; ama o kutu 5 s sonra kendiliğinden SİLİNİR — bir
// HATA iletisi okunmadan kaybolabilir. Bu yüzden hata/bilgi iletisi:
//   * kendiliğinden kaybolmaz; kullanıcı "Kapat" düğmesiyle kapatır
//     (Escape de kapatır);
//   * hata iletisi `role="alert"`, bilgi `role="status"` taşır ve hata
//     iletisinde odak bildirime taşınır (klavye kullanıcısı oradadır);
//   * metin `textContent` ile basılır (sunucu metni HTML olarak
//     yorumlanmaz); aynı metin ikinci kez gelirse eskisi kaldırılır.
// Kap şablonda `#hrmaNotices`tir; yoksa `#messages`in önüne kurulur.
function noticeHost() {
    let kap = document.getElementById('hrmaNotices');
    if (kap) return kap;
    if (typeof document.createElement !== 'function') return null;
    kap = document.createElement('div');
    kap.id = 'hrmaNotices';
    kap.className = 'hrma-notices';
    const mesajlar = document.getElementById('messages');
    if (mesajlar && mesajlar.parentNode
            && typeof mesajlar.parentNode.insertBefore === 'function') {
        mesajlar.parentNode.insertBefore(kap, mesajlar);
    } else if (document.body && typeof document.body.appendChild === 'function') {
        document.body.appendChild(kap);
    } else {
        return null;
    }
    return kap;
}

function showNotice(message, type) {
    const tur = (type === 'error') ? 'error' : 'info';
    const metin = String(message == null ? '' : message);
    // DOM'suz bağlam (ör. `handleError`ı tek başına koşturan sözleşme
    // düzenekleri): hata YUTULMAZ ve çağıranın dönüşü bozulmaz — ileti
    // konsola düşer. Tarayıcıda `document` her zaman vardır.
    if (typeof document === 'undefined') {
        console.error('[HRMA notice] ' + metin);
        return null;
    }
    const kap = noticeHost();
    if (!kap) {
        // DOM yoksa (sözleşme düzenekleri) ileti kaybolmaz: konsola düşer.
        console.error('[HRMA notice] ' + metin);
        return null;
    }
    if (typeof kap.querySelectorAll === 'function') {
        Array.prototype.forEach.call(kap.querySelectorAll('.hrma-notice'),
            function (eski) {
                if (eski.getAttribute('data-notice-text') === metin) {
                    eski.parentNode.removeChild(eski);
                }
            });
    }
    const onceki = document.activeElement || null;
    const kutu = document.createElement('div');
    kutu.className = 'alert alert-' + (tur === 'error' ? 'danger' : 'info')
        + ' hrma-notice';
    kutu.setAttribute('role', tur === 'error' ? 'alert' : 'status');
    kutu.setAttribute('data-notice-type', tur);
    kutu.setAttribute('data-notice-text', metin);
    kutu.setAttribute('tabindex', '-1');
    const kapat = document.createElement('button');
    kapat.type = 'button';
    kapat.className = 'hrma-notice-close';
    kapat.setAttribute('aria-label', T('common.close', 'Close'));
    kapat.textContent = T('common.close', 'Close');
    const govde = document.createElement('div');
    govde.className = 'hrma-notice-text';
    govde.textContent = metin;
    const kapatIsle = function () {
        if (kutu.parentNode) kutu.parentNode.removeChild(kutu);
        if (onceki && typeof onceki.focus === 'function'
                && document.contains && document.contains(onceki)) {
            onceki.focus();
        }
    };
    kapat.addEventListener('click', kapatIsle);
    kutu.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); kapatIsle(); }
    });
    kutu.appendChild(kapat);
    kutu.appendChild(govde);
    kap.appendChild(kutu);
    if (tur === 'error' && typeof kutu.focus === 'function') kutu.focus();
    return kutu;
}

// SÖKÜLDÜ (D30 a1) · showLoading() — advanced.html satır içi sürümü kazanıyordu.

function hideWelcomeMessage() {
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) {
        welcome.style.display = 'none';
    }
}

function showError(message) {
    showNotice(T('common.error', 'Error') + ': ' + message, 'error');
}

function showInfo(message) {
    showNotice(T('common.info', 'Info') + ': ' + message, 'info');
}

// SÖKÜLDÜ (D30 a1) · showMessage() — advanced.html satır içi sürümü kazanıyordu (i18n zarflı sürüm).

function showSuccess(message) {
    showMessage(message, 'success');
}

function showWarning(message) {
    showMessage(message, 'warning');
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    // Şablonun inline sürümü: tanımlı değilse çağrılmaz (P11B2-22).
    if (typeof updateInjectorParams === 'function') updateInjectorParams();
    // OH-GT-09: düğme HTML'de `disabled` doğuyor — açılışta künyesini al.
    const _exp = document.getElementById('exportResultsBtn');
    if (_exp) setExportResultsEnabled(!_exp.disabled);
    // Dil değişince: enjektör form etiketleri + saklanan sonuç blokları
    // yeniden basılır (yeni hesap yapılmaz).
    if (window.I18N && window.I18N.onChange) {
        window.I18N.onChange(function () {
            try {
                if (typeof updateInjectorParams === 'function') {
                    updateInjectorParams();
                }
            } catch (e) { /* form yoksa sessiz */ }
            // OH-GT-09: ipucu metni de dille birlikte yeniden yazılır.
            try {
                const b = document.getElementById('exportResultsBtn');
                if (b) setExportResultsEnabled(!b.disabled);
            } catch (e) { /* düğme yoksa sessiz */ }
            const r = window.currentResults;
            if (!r || !r.motor) return;
            // Dil değişiminde de künye ile birlikte (r = tam sonuç sözlüğü).
            try { displayPerformanceMetrics(r.motor, r); } catch (e) { /* panel yoksa */ }
            try {
                if (r.injector) displayDesignReport(r.motor, r.injector);
            } catch (e) { /* rapor yoksa */ }
            try { displayMotorTable(r.motor); } catch (e) { /* tablo yoksa */ }
            try { if (r.injector) displayInjectorTable(r.injector); } catch (e) { /* tablo yoksa */ }
            // P14M3-04: burada `r.injector && r.injector.warnings` vardı —
            // motor uyarıları dil değişiminde ekrandan siliniyordu (ölçüldü:
            // hibrit varsayılan koşumda 5 kayıt, 4'ü kritik -> 0). Hesap
            // sonrası yolla AYNI toplayıcı kullanılır.
            try { displayWarnings(collectResultWarnings(r), r.validation); }
            catch (e) { /* uyarı paneli yoksa */ }
        });
    }
});

// V301/N-YZ (26 Eki) — "Ask AI" kopyası KALDIRILDI. Üç sayfanın ayrı
// askAI / pano / veri penceresi kodu tek ortak modüle taşındı:
// hrma/static/js/ai_assistant.js ("Yapay Zekâ ile Tasarla"). Pano
// başarısızsa metnin pencerede açılması (OH-GT-07) orada korunur.
// Aşağıdaki prepareAIData ve yardımcıları hibrit adaptörünün ayrıntı
// bloğudur (ai_assistant.js ADAPTORLER.hybrid.ayrinti).

// Function to get display name for fuel type
function getFuelTypeDisplayName(fuelType) {
    const currentFuelType = document.getElementById('fuel_type').value;
    
    // Check if custom composition is being used
    if (currentFuelType === 'custom') {
        const compositionRows = document.querySelectorAll('#custom_fuel_config .composition-row');
        let customName = 'Custom Composition (';
        let compounds = [];
        
        compositionRows.forEach(row => {
            const compound = row.querySelector('.compound').value.trim();
            const percentage = row.querySelector('.percentage').value;
            if (compound && percentage) {
                compounds.push(`${compound}: ${percentage}%`);
            }
        });
        
        if (compounds.length > 0) {
            customName += compounds.join(', ') + ')';
        } else {
            customName += 'No composition specified)';
        }
        
        return customName;
    }
    
    // Check if custom mixture is being used
    if (currentFuelType === 'mixture') {
        const mixtureRows = document.querySelectorAll('#custom_fuel_mixture .mixture-component');
        let mixtureName = 'Custom Mixture (';
        let components = [];
        
        mixtureRows.forEach(row => {
            const fuelSelect = row.querySelector('.mixture-fuel');
            const percentage = row.querySelector('.mixture-percentage').value;
            if (fuelSelect && percentage) {
                const fuelName = fuelSelect.options[fuelSelect.selectedIndex].text;
                components.push(`${fuelName}: ${percentage}%`);
            }
        });
        
        if (components.length > 0) {
            mixtureName += components.join(', ') + ')';
        } else {
            mixtureName += 'No components specified)';
        }
        
        return mixtureName;
    }
    
    // Return standard fuel type display name
    const fuelNames = {
        'htpb': T('fuel.htpb', 'HTPB (Hydroxyl-terminated polybutadiene)'),
        'pe': T('fuel.pe', 'Polyethylene'),
        'pmma': T('fuel.pmma', 'PMMA (Polymethyl methacrylate)'),
        'paraffin': T('fuel.paraffinWax', 'Paraffin Wax'),
        'abs': T('fuel.abs', 'ABS Plastic'),
        'pla': T('fuel.pla', 'PLA Plastic'),
        'carbon': T('fuel.carbon', 'Carbon (Graphite)'),
        'aluminum': T('fuel.aluminum', 'Aluminum Powder'),
        'al2o3': T('fuel.al2o3', 'Aluminum Oxide (Al2O3)')
    };

    return fuelNames[fuelType]
        || (fuelType ? fuelType.toUpperCase() : T('fuel.unknown', 'Unknown Fuel'));
}

// Prepare AI-friendly data (hibrit adaptörünün ayrıntı bloğu, V301/N-YZ)
// ÖH D15 / P11B2-03 · -04 ortak yardımcıları -----------------------------
// Sonlu sayı ise sayıyı, değilse null döner. Sayı UYDURMAZ: yokluğun yerine
// "tipik değer" yazmak, yapay zekâya giden yükün en sinsi uydurmasıydı.
function numOrNull(v) {
    return (typeof v === 'number' && isFinite(v)) ? v : null;
}

// Lüle açıları: çözücünün `motor.nozzle_angles` bloğu TEK KAYNAK.
// Eski kod `motor.convergent_angle` / `motor.divergent_angle` okuyup
// bulamayınca 15,0 / 12,0 sabitlerine düşüyordu (ölçüldü: o anahtarlar
// yanıtta hiç yok). Blok yoksa hiçbir açı iddia edilmez.
function buildNozzleGeometryExport(motorData) {
    const m = motorData || {};
    const ang = m.nozzle_angles || {};
    const yak = numOrNull(ang.convergent_half_angle_deg ?? m.convergent_angle);
    const ira = numOrNull(ang.divergent_half_angle_deg ?? m.divergent_angle);
    if (yak === null && ira === null) {
        return {
            status: 'NOT_REPORTED',
            basis: 'solver did not return motor.nozzle_angles'
        };
    }
    return {
        convergent_angle_deg: yak,
        divergent_angle_deg: ira,
        angle_definition: 'half_angles_from_centerline',
        // Lüle tipi de ÇÖZÜCÜNÜN: eski "conical_assumed" etiketi, çözücü
        // aynı yanıtta "conical" derken bir varsayım iddia ediyordu.
        nozzle_type: ang.nozzle_type || null,
        divergence_efficiency: numOrNull(ang.divergence_efficiency),
        source: 'motor.nozzle_angles'
    };
}

// Enjektör akış bloğu (P11B2-04). Eski hâli formdaki girdileri yok sayıp
// sabit basıyordu: oksitleyici giriş sıcaklığı 293,15 K sabit (form alanı
// `oxidizer_temp` gönderiliyorken), kavitasyon indisi ΔP/25 bar sabitiyle
// (form `tank_pressure` = 50 bar iken sonuç tam 2 kat), flash boiling ise
// sabit "ΔP < 3 bar" eşiğiyle — çözücü aynı yanıtta Nurick sayısını
// hesaplayıp uyarı yayımlıyorken. İkisi de KALDIRILDI: yükte yalnız
// çözücünün yayımladığı büyüklükler ve açık bir NOT_MODELLED beyanı var.
function buildInjectorFlowExport(results) {
    const inj = (results && results.injector) || {};
    const alan = (id) => {
        const el = document.getElementById(id);
        const v = el ? parseFloat(el.value) : NaN;
        return isFinite(v) ? v : null;
    };
    return {
        oxidizer_inlet_temperature_K: alan('oxidizer_temp'),
        oxidizer_inlet_temperature_source: document.getElementById('oxidizer_temp')
            ? 'form field oxidizer_temp' : 'not supplied',
        tank_pressure_bar: alan('tank_pressure'),
        injector_inlet_pressure_bar: numOrNull(inj.injector_inlet_pressure_bar),
        vapor_pressure_bar: numOrNull(inj.vapor_pressure_bar),
        pressure_drop_bar: numOrNull(inj.pressure_drop_bar ?? inj.pressure_drop),
        cavitation_status: 'NOT_MODELLED',
        cavitation_basis: 'the cavitation number is computed by the solver '
            + '(Nurick K_c) and reported in the warnings block; this payload '
            + 'carries its inputs but does not derive a second index',
        flash_boiling_status: 'NOT_MODELLED',
        flash_boiling_basis: 'flash boiling is assessed by the solver against '
            + 'the oxidizer vapour pressure and reported in the warnings '
            + 'block; no fixed pressure-drop threshold is applied here'
    };
}

function prepareAIData(results) {
    return {
        analysis_type: "Hybrid Rocket Motor Design",
        timestamp: new Date().toISOString(),
        schema_version: "1.0",
        units_system: "SI_mixed", // Note: Mixed units used (bar for pressure, mm for dimensions)
        generator: "HRMA v" + (window.HRMA_VERSION || "unknown"),
        run_id: generateRunId(),
        
        input_parameters: {
            thrust_N: results.motor.thrust,
            burn_time_s: results.motor.burn_time,
            total_impulse_Ns: results.motor.total_impulse,
            of_ratio_dimensionless: results.motor.of_ratio,
            chamber_pressure_bar: results.motor.chamber_pressure, // CRITICAL: Unit assumed as bar
            // v2.6.26 — yakit ve oksitleyici FORMDAN okunur.
            // `results.motor.fuel_type` yanitta HIC YOK (olculdu) -> yapay
            // zekaya `undefined` gidiyordu; oksitleyici ise 'N2O' diye SABIT
            // yaziliydi, yani kullanici baska bir oksitleyici secse bile
            // yapay zeka N2O uzerinden akil yurutuyordu. Ikisi de sayfanin
            // kendi alanindan (id=fuel_type / id=oxidizer_type) alinir;
            // alan yoksa deger uydurulmaz, null gider.
            fuel_type: (document.getElementById('fuel_type')?.value
                        ? getFuelTypeDisplayName(
                            document.getElementById('fuel_type').value)
                        : null),
            oxidizer: document.getElementById('oxidizer_type')?.value || null,
            reference_conditions: {
                ambient_pressure_Pa: 101325,
                ambient_temperature_K: 293.15,
                performance_basis: "sea_level_standard"
            }
        },
        
        performance_results: {
            specific_impulse_sec: {
                value: results.motor.isp,
                derived_from: "c_star_and_cf",
                reference: "sea_level_standard"
            },
            c_star_m_s: results.motor.c_star,
            thrust_coefficient_dimensionless: results.motor.cf,
            total_mass_flow_kg_s: results.motor.mdot_total,
            oxidizer_flow_kg_s: results.motor.mdot_ox,
            fuel_flow_kg_s: results.motor.mdot_f,
            propellant_mass_kg: {
                value: results.motor.propellant_mass_total,
                derived_from: "mass_flow_and_burn_time",
                calculation_method: "mdot_total * burn_time"
            },
            thrust_to_weight_ratio: {
                value: results.motor.thrust / (results.motor.propellant_mass_total * 9.81),
                reference_mass_kg: results.motor.propellant_mass_total,
                description: "thrust / (propellant_mass * g0)"
            }
        },
        
        geometry: {
            chamber_diameter_mm: results.motor.chamber_diameter * 1000,
            chamber_length_mm: results.motor.chamber_length * 1000,
            throat_diameter_mm: results.motor.throat_diameter * 1000,
            exit_diameter_mm: results.motor.exit_diameter * 1000,
            expansion_ratio_dimensionless: results.motor.expansion_ratio,
            port_diameter_initial_mm: results.motor.port_diameter_initial * 1000,
            port_diameter_final_mm: results.motor.port_diameter_final * 1000,
            
            // Geometry validation and anomaly detection
            l_over_d_ratio: (results.motor.chamber_length * 1000) / (results.motor.chamber_diameter * 1000),
            geometry_anomalies: detectGeometryAnomalies(results.motor),
            
            // ÖH D15 / P11B2-03 — LÜLE AÇILARI ÇÖZÜCÜDEN OKUNUR.
            // ÖLÇÜLDÜ (31 Ağustos 2026, gerçek /calculate yanıtı +
            // node içinde gerçek prepareAIData): `motor.convergent_angle`
            // ve `motor.divergent_angle` anahtarları yanıtta HİÇ YOK, yani
            // `|| 15.0` / `|| 12.0` yedeği HER koşuda ateşleniyordu; gerçek
            // açılar aynı yanıtta `motor.nozzle_angles` altında duruyordu
            // (yakınsak 30,0° ⟷ yüke giden 15,0° = 2×; ıraksak 15,0° ⟷ 12,0°).
            // Kullanıcı aynı sayfada iki farklı açı görüyordu ve yapay zekâya
            // giden kopya YANLIŞ olanıydı. Yedek KALDIRILDI: alan yoksa sayı
            // uydurulmaz, null gider (fail-closed).
            nozzle_geometry: buildNozzleGeometryExport(results.motor)
        },
        
        injector_design: {
            type: results.injector.type,
            exit_velocity_m_s: results.injector.exit_velocity,
            pressure_drop_bar: results.injector.pressure_drop,
            reynolds_number: {
                value: results.injector.reynolds_number,
                reference_diameter: "injector_hole_diameter",
                fluid: "oxidizer",
                calculation_note: "Re = ρvd/μ for oxidizer flow"
            },
            // ÖH D15 / P11B2-03 — Cd ve L/D ÇÖZÜCÜDEN. Sabit 0,65 ve 2,0
            // aynı sayfadaki tasarım raporuyla çelişiyordu (ölçüldü:
            // gerçek Cd = 0,700 ve L/D = 3,900). Alan yoksa null gider.
            discharge_coefficient: numOrNull(results.injector.discharge_coefficient),
            ...(results.injector.type === 'showerhead' && {
                holes_count: results.injector.n_holes,
                hole_diameter_mm: results.injector.hole_diameter,
                l_over_d_ratio: numOrNull(results.injector.L_D_ratio
                                          ?? results.injector.l_d_ratio),
                plate_thickness_mm: numOrNull(results.injector.plate_thickness)
            }),
            flow_characteristics: buildInjectorFlowExport(results)
        },
        
        // ÖH D15 / P11B2-02 (kritik) — YÜK EKRANIN GÖRDÜĞÜ UYARILARI TAŞIR.
        // ÖLÇÜLDÜ: ekranda 10 uyarı dururken yüke YALNIZ enjektörün 3'ü
        // giriyordu; motorun HTPB regresyon yanlılığı, lülede akış ayrılması
        // ve cidarın erime sıcaklığını aşması dâhil 7 kayıt düşüyordu.
        // Kanal artık ekranın kendi toplayıcısıyla AYNI (tek kaynak).
        warnings: structurizeWarnings(collectResultWarnings(results)),
        
        // v2.6.26 — UYDURMA VERIM UCLUSU KALDIRILDI.
        // 0,95 / 0,98 / 0,93 hicbir hesaptan gelmiyordu ve lule verimi
        // cozucunun KENDI degeriyle CELISIYORDU (olculdu: 0,9541). Yapay
        // zekaya iki farkli lule verimi gitmis oluyordu. Artik cozucunun
        // ayrik kayip modeli oldugu gibi aktarilir; uretilmeyen alan
        // uydurulmaz.
        efficiency_metrics: (function () {
            const perf = results.motor?.nozzle_design?.performance;
            if (!perf) {
                return {
                    status: 'NOT_REPORTED',
                    basis: 'solver did not return nozzle_design.performance'
                };
            }
            return {
                nozzle_efficiency: perf.nozzle_efficiency ?? null,
                divergence_efficiency: perf.divergence_efficiency ?? null,
                friction_efficiency: perf.friction_efficiency ?? null,
                kinetic_efficiency: perf.kinetic_efficiency ?? null,
                two_phase_efficiency: perf.two_phase_efficiency ?? null,
                basis: 'discrete loss model reported by the solver '
                     + '(lambda x friction x two-phase x kinetic)'
            };
        })(),
        
        thermal_analysis: {
            // ÖH D17 / P11B2-03 ŞARTI + OH-D16-13 — İKİNCİ KOPYA TEK KAYNAĞA
            // BAĞLANDI. ÖLÇÜLDÜ (raw/OH/D17/arayuz/a1/once.json M1, gerçek
            // /calculate yanıtı + node içinde gerçek prepareAIData): aynı
            // yükün `geometry.nozzle_geometry` bloğu çözücünün 30,0°/15,0°
            // açılarını taşırken bu blok `|| 15.0` / `|| 12.0` yedeklerini
            // ateşleyip 15,0°/12,0° basıyordu (`motor.convergent_angle` ve
            // `motor.divergent_angle` anahtarları yanıtta HİÇ YOK — ölçüldü:
            // motorda_convergent_angle_var=false). D15 onarımı yalnız
            // birinci kopyayı düzeltmişti; yapay zekâya giden yük iki
            // farklı açı çifti taşımaya devam ediyordu (iki_blok_CELISIK).
            // Aynı satırdaki `|| 3000` yedeği de kaldırıldı: oda sıcaklığı
            // çözülemediyse sayı UYDURULMAZ, null gider (fail-closed).
            chamber_temperature_K: numOrNull(results.motor.chamber_temperature),
            nozzle_angles: buildNozzleGeometryExport(results.motor),
            // ÖH D15 / P11B2-04 — SABİT MALZEME LİSTESİ ve SABİT 1200 K
            // KALDIRILDI. Üçü de motorun malzemesinden, basıncından ya da
            // sıcaklığından gelmiyordu; kullanıcı `chamber_material` alanını
            // değiştirse bile yapay zekâya aynı üç malzeme gidiyordu.
            material_properties: {
                selected_material: (document.getElementById('chamber_material')?.value
                                    || null),
                recommended_materials_status: 'NOT_MODELLED',
                recommended_materials_basis: 'this payload does not rank '
                    + 'materials; the selected material above is the form '
                    + 'input and the computed margins are in the structural '
                    + 'and safety analysis blocks',
                thermal_considerations: {
                    max_wall_temperature_status: 'NOT_MODELLED',
                    max_wall_temperature_basis: 'no wall temperature limit is '
                        + 'derived here; the solver publishes the wall '
                        + 'temperature chain and its warnings in the '
                        + 'warnings block',
                    cooling_required: results.motor.chamber_temperature > 2500
                }
            }
        },
        
        structural_analysis: buildStructuralExport(results.motor),
        
        safety_considerations: {
            critical_parameters: {
                // v2.6.26 — bu iki "kritik parametre" hicbir malzeme veya
                // emniyet hesabindan gelmiyordu; 50 bar siniri ve 2-8
                // O/F araligi her motor icin ayniydi. Kaldirildi: uydurma
                // bir emniyet siniri, hic sinir vermemekten kotudur.
                limits_status: 'NOT_MODELLED',
                limits_basis: 'chamber pressure and O/F limits are not '
                            + 'derived here; see the structural and safety '
                            + 'analysis blocks for the computed margins',
                thrust_to_weight_ratio: results.motor.thrust / (results.motor.propellant_mass_total * 9.81)
            },
            risk_factors: identifyRiskFactors(results),
            recommended_testing: [
                'Cold flow tests',
                'Static fire tests',
                'Burst pressure testing',
                'Thermal cycling tests'
            ]
        },
        
        // v2.6.26 — UYDURMA İMALAT ŞARTNAMESİ KALDIRILDI.
        // Burada yapay zekâya giden yüke sabit toleranslar (IT7 ±0,1 mm,
        // IT6 ±0,05 mm), sabit yüzey pürüzlülüğü (Ra 3,2 μm) ve sabit
        // işleme yöntemleri basılıyordu. Hiçbiri motorun ölçüsünden,
        // malzemesinden veya basıncından gelmiyordu: 40 mm'lik bir motorla
        // 500 mm'lik bir motor aynı toleransı alıyordu. Yapay zekâ bu yükü
        // ÖLÇÜLMÜŞ VERİ sanıp üstüne akıl yürütüyordu — uydurmanın en
        // sinsi biçimi, çünkü çıktısı ikinci bir metne yayılıyor.
        //
        // Çözücü artık ölçüye bağlı ISO 2768 toleransı üretiyor
        // (hrma/engines/solid_rocket_engine.py, _iso2768_feature üstünden;
        // Ø75 -> ±0,15 mm, Ø500 -> ±0,30 mm). Bu blok, o gerçek değerler
        // yapay zekâ yüküne bağlanana kadar durumunu açıkça bildirir.
        manufacturing_data: {
            status: "NOT_MODELLED",
            basis: "Manufacturing tolerances, surface finish and machining "
                 + "methods are not produced by this payload. Earlier versions "
                 + "sent fixed values (IT7/IT6, Ra 3.2 um) that did not depend "
                 + "on the motor at all; they were removed rather than kept as "
                 + "plausible-looking placeholders. The solver's own "
                 + "size-dependent ISO 2768 tolerances are reported in the "
                 + "solid motor results."
        }
    };
}

// Helper calculation functions for AI data

function generateRunId() {
    return 'RUN_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 5);
}

function detectGeometryAnomalies(motorData) {
    const anomalies = [];
    
    // L/D ratio check
    const lOverD = (motorData.chamber_length * 1000) / (motorData.chamber_diameter * 1000);
    if (lOverD < 0.1) {
        anomalies.push({
            type: "SCALE_ANOMALY",
            severity: "HIGH", 
            message: `Extremely low L/D ratio: ${numTxt(lOverD, 3)}`,
            likely_cause: "Unit conversion error or data entry mistake"
        });
    }
    
    // Port diameter vs chamber check
    const portFinalMm = motorData.port_diameter_final * 1000;
    const chamberMm = motorData.chamber_diameter * 1000;
    const minWallThickness = 5; // mm minimum wall
    
    if (portFinalMm > (chamberMm - 2 * minWallThickness)) {
        anomalies.push({
            type: "WALL_THICKNESS_VIOLATION",
            severity: "CRITICAL",
            message: `Final port diameter too large for safe wall thickness`,
            values: {port_final_mm: portFinalMm, chamber_mm: chamberMm, min_wall_mm: minWallThickness}
        });
    }
    
    return anomalies;
}

// ÖH D15 / P11B2-02 — İKİ UYARI BİÇİMİ DE OKUNUR.
// Kanal artık yalnız enjektörün düz metin uyarılarını değil, motorun ve
// girdi doğrulamasının {code, params, severity} kayıtlarını da taşıyor.
// Eski gövde `warning.includes(...)` diyordu: sözlük kaydı geldiğinde
// TypeError fırlatıyor ve YAPAY ZEKÂ DÜĞMESİ ÇÖKÜYORDU (ölçüldü, node).
// Kaydın kendi `code`/`severity` alanı varsa O kullanılır — burada
// yeniden sınıflandırma yapılmaz (sınıfın sahibi çözücüdür).
function structurizeWarnings(warningStrings) {
    const liste = Array.isArray(warningStrings) ? warningStrings : [];
    return liste.map((warning, index) => {
        const sozluk = (warning && typeof warning === 'object') ? warning : null;
        const metin = sozluk
            ? String(sozluk.message || sozluk.code || '')
            : String(warning == null ? '' : warning);
        const flash = metin.toLowerCase().includes('flash');
        return {
            id: `WARN_${index + 1}`,
            code: (sozluk && sozluk.code)
                ? sozluk.code : (flash ? 'FLASH_BOILING' : 'GENERAL'),
            severity: (sozluk && sozluk.severity)
                ? String(sozluk.severity).toUpperCase()
                : (flash ? 'HIGH' : 'MEDIUM'),
            message: metin,
            // Çözücünün parametreleri (bias_pct, of, lo, hi …) kaybolmaz:
            // uyarının SAYISI onlarda duruyor.
            params: (sozluk && sozluk.params) ? sozluk.params : null,
            timestamp: new Date().toISOString(),
            path: sozluk ? 'solver_warnings' : 'injector_design'
        };
    });
}

// ÖH D15 / P11B2-04 — KALDIRILDI (uydurma kavitasyon indisi).
// Bu fonksiyon giriş basıncını SABİT 25 bar alıyordu; formdaki
// `tank_pressure` 50 bar iken indis tam 2 kat iyimser çıkıyordu ve çözücü
// aynı yanıtta gerçek Nurick sayısını (K_c) yayımlıyordu. İki ayrı indis
// üretmek yerine yükte çözücünün girdileri + açık NOT_MODELLED beyanı
// taşınıyor (bkz. buildInjectorFlowExport). Fonksiyonun tüketicisi kalmadı.

// Rapor exportu için yapısal bölüm: currentResults.motor.structural_analysis'in
// GERÇEK backend değerleri kullanılır. Sonuç yoksa alanlar 'not computed'
// bırakılır — JS tarafında yeniden hesap veya sabit uydurma değer YASAK
// (eski 4.0/3.0/4.0 sabitleri ve JS hoop stress tahmini kaldırıldı, 2026-07-14).
function buildStructuralExport(motorData) {
    const NOT_COMPUTED = 'not computed';
    const sa = motorData && motorData.structural_analysis;
    if (!sa) {
        return {
            source: NOT_COMPUTED,
            note: 'Backend structural analysis was not available for this run; no values were estimated client-side.'
        };
    }
    const chamber = sa.chamber_analysis || {};
    const safety = sa.safety_analysis || {};
    const designParams = sa.design_parameters || {};
    const num = v => (typeof v === 'number' && isFinite(v)) ? v : NOT_COMPUTED;
    return {
        source: 'HRMA backend structural_analysis (materials from MMPDS/Sutton-referenced database)',
        material: designParams.material || NOT_COMPUTED,
        design_pressure_bar: num(designParams.design_pressure),
        design_pressure_factor: num(designParams.design_pressure_factor),
        safety_factors: {
            pressure_only: num(sa.safety_factor_pressure),
            total_incl_thermal: num(sa.safety_factor_total),
            minimum_all_modes: num(safety.minimum_safety_factor),
            // ÖH Z4 / P11B4-03: `minimum_all_modes` HRMA'nın KENDİ
            // boyutlandırdığı kesitlerden gelebilir; o hâlde sayı tasarım
            // hedefinin geri okumasıdır, kullanıcının kazandığı marj değil.
            // İhraç dosyası bugüne dek yalnız sol sütunu taşıyordu.
            // `null` ile 'not computed' AYNI ŞEY DEĞİL: null = hesaplandı,
            // sonuç "kazanılmış mod yok" (bütün kesitler HRMA'nın kendi
            // boyutlandırdığı kesitler). Alan hiç yoksa 'not computed'.
            minimum_earned: (typeof safety.minimum_earned_safety_factor === 'number'
                             && isFinite(safety.minimum_earned_safety_factor))
                ? safety.minimum_earned_safety_factor
                : (safety.minimum_earned_safety_factor === null
                    ? null : NOT_COMPUTED),
            binding_modes: safety.binding_safety_factors || NOT_COMPUTED,
            binding_is_target_readback:
                (typeof safety.binding_safety_factor_is_tautological === 'boolean')
                    ? safety.binding_safety_factor_is_tautological : NOT_COMPUTED,
            per_mode_is_target_readback:
                safety.safety_factor_is_tautological || NOT_COMPUTED,
            verdict_basis: safety.minimum_safety_factor_verdict_basis || NOT_COMPUTED,
            per_mode: safety.safety_factors || NOT_COMPUTED
        },
        stress_analysis: {
            hoop_stress_total_MPa: num(chamber.hoop_stress),
            pressure_hoop_stress_MPa: num(chamber.pressure_hoop_stress),
            thermal_hoop_stress_MPa: num(chamber.thermal_hoop_stress),
            von_mises_stress_MPa: num(chamber.von_mises_stress),
            wall_thickness_minimum_mm: num(chamber.minimum_thickness),
            wall_thickness_recommendation_mm: num(chamber.recommended_thickness)
        },
        status: safety.status || NOT_COMPUTED,
        risk_level: safety.risk_level || NOT_COMPUTED
    };
}

function identifyRiskFactors(results) {
    const risks = [];
    
    // High pressure risk
    if (results.motor.chamber_pressure > 40) {
        risks.push('HIGH_PRESSURE: Chamber pressure exceeds 40 bar - requires robust design');
    }
    
    // ÖH D15 / P11B2-02 — O/F BANDI BURADAN KALDIRILDI (tek kaynak).
    // Buradaki 2,0–8,0 bandı çözücünün bandıyla (0,5–6,0) ilgisizdi ve
    // ölçülen koşuda O/F = 7,5 iken çözücü `warn.validation.of_out_of_range`
    // uyarısı yayımlarken bu blok sessiz kalıyordu. Bandın tek sahibi
    // çözücüdür; uyarısı `warnings` bloğunda yükün içinde taşınıyor.

    // Thrust density risk
    const thrustDensity = results.motor.thrust / (Math.PI * Math.pow(results.motor.chamber_diameter/2, 2));
    if (thrustDensity > 5000000) { // N/m²
        risks.push('HIGH_THRUST_DENSITY: May cause thermal stress issues');
    }
    
    // Expansion ratio risk
    if (results.motor.expansion_ratio > 20) {
        risks.push('HIGH_EXPANSION_RATIO: Risk of flow separation in nozzle');
    }
    
    // Port diameter risk
    const portRatio = results.motor.port_diameter_final / results.motor.port_diameter_initial;
    if (portRatio > 3.0) {
        risks.push('EXCESSIVE_REGRESSION: Large port growth may affect performance');
    }
    
    // ÖH D15 / P11B2-02 (kritik) — "LOW_RISK" HÜKMÜ KALDIRILDI.
    // ÖLÇÜLDÜ: çözücü aynı koşuda 10 uyarı (kavitasyon, flash boiling,
    // cidarın erime sıcaklığını aşması, lülede akış ayrılması, HTPB
    // regresyon yanlılığı) yayımlarken bu satır yapay zekâya
    // "Design parameters within normal ranges" cümlesini götürüyordu.
    // Aşağıdaki dört sezgisel bir risk DEĞERLENDİRMESİ değildir; hiçbiri
    // yanmadığında doğru cümle "risk düşük" değil "burada hüküm
    // KURULMADI"dır. Çözücünün uyarı kanalı sayılarak beyan edilir.
    if (risks.length > 0) return risks;
    const cozucuUyarilari = collectResultWarnings(results);
    return ['NOT_ASSESSED: this payload does not derive a risk verdict; '
            + cozucuUyarilari.length + ' solver warning(s) are carried in '
            + 'the warnings block and must be read there'];
}

// Handle Enter key in form
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && e.target.classList.contains('form-control')) {
        e.preventDefault();
        calculate();
    }
});

// SÖKÜLDÜ (D30 a1) · showDesignConfig() — advanced.html satır içi sürümü kazanıyordu (D28 arayuz a3 kapıyı orada onarmıştı).

// SÖKÜLDÜ (D30 a1) · autoFillDesignConfig() — tek çağrısı yukarıdaki ölü showDesignConfig içindeydi; yaptığı iki iş canlı yolda zaten var (generateCADBtn advanced.html:5617/5624’te açılıyor, yer tutucular satır içi sürümde kuruluyor).

// SÖKÜLDÜ (D30 a1) · switchConfigTab() — advanced.html satır içi sürümü kazanıyordu.

// Apply design configuration
function applyDesignConfig() {
    // Store configuration
    window.designConfig = {
        motor: {
            chamber_material: document.getElementById('chamber_material').value,
            wall_thickness: parseFloat(document.getElementById('wall_thickness').value),
            safety_factor: parseFloat(document.getElementById('safety_factor').value),
            nozzle_material: document.getElementById('nozzle_material').value,
            chamber_length_override: parseFloat(document.getElementById('chamber_length_override').value) || null,
            // v2.6.26: ayrı 'nozzle_contour' seçicisi kaldırıldı (nozzle_type ile
            // aynı kavramın ikinci, bağlanmamış kopyasıydı). CAD artık çözücüye
            // bağlı olan tek alandan okur — böylece CAD ile hesap aynı konturu
            // kullanır (katı motorda CAD'in analizden kopması v2.6.26'da
            // düzeltilen bir hataydı; aynı hatayı burada tekrarlamıyoruz).
            nozzle_contour: document.getElementById('nozzle_type')?.value || 'conical'
        },
        injector: {
            material: document.getElementById('injector_material').value,
            // 'injection_velocity' alanı kaldırıldı; bağlı olan eşdeğeri
            // showerhead panelindeki target_velocity. Yoksa (pintle/swirl/
            // koaksiyel) hız bir çıktıdır, CAD'e girdi olarak verilmez.
            injection_velocity: parseFloat(document.getElementById('target_velocity')?.value) || null,
            pressure_drop_percent: parseFloat(document.getElementById('pressure_drop_percent').value),
            n_holes_override: parseInt(document.getElementById('n_holes_override').value) || null,
            hole_pattern: document.getElementById('hole_pattern').value,
            cooling_channels: document.getElementById('cooling_channels').value
        }
    };
    
    // Hide config panel and show export panel
    document.getElementById('designConfigPanel').style.display = 'none';
    document.getElementById('exportActionsPanel').style.display = 'block';
    
    // Enable CAD generation
    document.getElementById('generateCADBtn').disabled = false;
    
    showSuccess(T('app.msg.configApplied', 'Design configuration applied successfully'));
}

// SÖKÜLDÜ (D30 a1) · generateCAD() — advanced.html satır içi sürümü kazanıyordu (Three.js + /api/generate-3d yedeği, OH-D23-15 kapılı); bu kopya ölü /api/export-cad’i çağırıyordu.

// SÖKÜLDÜ (D30 a1) · exportSTL() — advanced.html satır içi sürümü kazanıyordu (_downloadExport ile /api/export-stl-zip; bu kopya ölü /api/export-stl’i çağırıyordu).

// ÖH D23 / P17B3-07 — ÖLÜ `exportOpenRocket` SÖKÜLDÜ.
// SÖKÜLDÜ (D30 a1) · downloadEngFile() — advanced.html satır içi sürümü kazanıyordu (D23 P17B3-07 üretim yolu).

// ÖH D24 / OH-D18-06 — STL indirme penceresinin kullanıcıya dönük metni.
//
// `stlDownloadWindow` yalnız SUNUCUNUN yayımladığı saniyeyi taşır; burada
// hiçbir varsayılan yoktur. Üç hâl vardır ve üçü de farklı şey söyler:
//   * bağlantı yok                -> hiçbir şey yazılmaz
//   * bağlantı var, süre beyanlı  -> pencere ve BİTİŞ ANI yazılır
//   * bağlantı var, süre beyansız -> "süre beyan edilmedi" yazılır
// Sunucu sayıyı `_STL_REGISTRY_TTL_S` tek kaynağından üretir (hrma/app.py).
function stlPencereMetni(cad) {
    if (!cad || !Array.isArray(cad.stl_files) || cad.stl_files.length === 0) {
        return '';
    }
    const stlDownloadWindow = Number(cad.stl_download_window_s);
    if (!isFinite(stlDownloadWindow) || stlDownloadWindow <= 0) {
        return ' ' + T('app.msg.stlWindowUndeclared',
            'The server did not declare how long the STL download links stay '
            + 'alive; re-generate the package if a link stops working.');
    }
    const dakika = Math.floor(stlDownloadWindow / 60);
    const bitis = new Date(Date.now() + stlDownloadWindow * 1000);
    window.stlDownloadExpiresAt = bitis.getTime();
    return ' ' + TF('app.msg.stlWindow',
        { count: cad.stl_files.length,
          minutes: dakika,
          at: bitis.toLocaleTimeString() },
        'The {count} STL download links stay alive for {minutes} min (until '
        + '{at}); after that they return 410 and the package must be '
        + 'generated again.');
}

// SÖKÜLDÜ (D30 a1) · generateCompletePackage() — advanced.html satır içi sürümü kazanıyordu (generateCAD + exportCompleteZip).

// SÖKÜLDÜ (D30 a1) · rotate3DView() — advanced.html satır içi sürümü kazanıyordu (bu kopya hâlâ Plotly çağırıyordu).

// SÖKÜLDÜ (D30 a1) · reset3DView() — advanced.html satır içi sürümü kazanıyordu (bu kopya hâlâ Plotly çağırıyordu).

// SÖKÜLDÜ (D30 a1) · calculateParametric() — advanced.html satır içi sürümü kazanıyordu (runParametricAnalysis sarmalayıcısı); bu kopyanın TEK kapısı assertParametricMatchesRequest idi ve o kapı D30 a1’de canlı sürüme bağlandı.

// Trajectory Analysis
// V301/H-PANEL (NK-24): yörünge için son hesaptan bu yana değişen MOTOR
// alanları. Araç/yörünge alanları (kütle, Cd, fırlatma) motoru değiştirmez
// ve karşılaştırmaya girmez. Son hesap yoksa null döner.
const YORUNGE_MOTOR_DISI_ALANLAR = ['vehicle_mass_dry', 'vehicle_reference_area_m2',
    'drag_coefficient', 'vehicle_length', 'launch_angle', 'launch_altitude',
    'wind_speed', 'wind_direction', 'calculate_trajectory', 'motor_name',
    'motor_description'];
function yorungeIcinDegisenMotorAlanlari(son, simdi) {
    if (!son || typeof son !== 'object' || Array.isArray(son)) return null;
    const a = son, b = simdi || {};
    const adlar = Object.keys(Object.assign({}, a, b)).filter(function (k) {
        return YORUNGE_MOTOR_DISI_ALANLAR.indexOf(k) === -1;
    });
    return adlar.filter(function (k) {
        return JSON.stringify(a[k]) !== JSON.stringify(b[k]);
    }).sort();
}

async function calculateTrajectory() {
    try {
        // Check if required elements exist
        const requiredElements = ['initial_mass', 'final_mass', 'drag_coefficient', 'reference_area'];
        for (const elementId of requiredElements) {
            if (!document.getElementById(elementId)) {
                showError(`Trajectory analysis form element not found: ${elementId}`);
                return;
            }
        }
        
        showLoading(true);
        showMessage(T('app.msg.trajStarted', 'Trajectory analysis started...'), 'info');
        
        // Get trajectory specific data
        const initialMass = parseFloat(document.getElementById('initial_mass').value);
        const finalMass = parseFloat(document.getElementById('final_mass').value);
        const dragCoeff = parseFloat(document.getElementById('drag_coefficient').value);
        // Alan arayüzde mm² girilir, backend m² bekler (sözleşme değişmedi).
        const refAreaMm2 = parseFloat(document.getElementById('reference_area').value);
        const refArea = refAreaMm2 / MM2_PER_M2;
        const trajAltStart = parseFloat(document.getElementById('traj_alt_start')?.value || 0);
        const trajAltEnd = parseFloat(document.getElementById('traj_alt_end')?.value || 10000);
        const trajPoints = parseInt(document.getElementById('traj_points')?.value || 20);
        const launchAngle = parseFloat(document.getElementById('launch_angle')?.value || 90);
        const windSpeed = parseFloat(document.getElementById('wind_speed')?.value || 0);
        
        // Validate trajectory inputs
        if (isNaN(initialMass) || isNaN(finalMass) || isNaN(dragCoeff) || isNaN(refAreaMm2)) {
            throw new Error(T('app.msg.trajInvalid', 'Invalid trajectory analysis inputs'));
        }
        
        if (initialMass <= finalMass) {
            throw new Error(T('app.msg.trajMass', 'Initial mass must be greater than final mass'));
        }
        
        if (dragCoeff <= 0 || refArea <= 0) {
            throw new Error(T('app.msg.trajDrag', 'Drag coefficient and reference area must be positive'));
        }
        
        if (trajAltStart >= trajAltEnd) {
            throw new Error(T('app.msg.trajAltitude', 'Starting altitude must be less than final altitude'));
        }
        
        const baseData = getFormData();

        // V301/H-PANEL (NK-24): kütle ve itki AYNI koşudan gelir. Başlangıç
        // kütlesi son hesabın itici kütlesinden kurulur; form o hesaptan
        // sonra değiştiyse uç YENİ formun motorunu ESKİ itici kütlesiyle
        // uçuruyordu (ölçüldü: 1000 N hesabının 4,30 kg'ı + 3000 N itki →
        // ima edilen Isp ~700 s). Motor alanları son hesabın gövdesinden
        // farklıysa yörünge koşmaz; hangi alanların değiştiği adıyla söylenir.
        const degisenMotorAlanlari = yorungeIcinDegisenMotorAlanlari(
            (typeof window !== 'undefined') ? window.currentRequest : null, baseData);
        if (degisenMotorAlanlari === null) {
            throw new Error(T('app.msg.trajNoCalc',
                'No motor has been calculated yet: the initial mass comes from the propellant mass of a calculation. Press Calculate first.'));
        }
        if (degisenMotorAlanlari.length) {
            throw new Error(TF('app.msg.trajStaleMotor',
                { fields: degisenMotorAlanlari.join(', ') },
                'The motor form has changed since the last calculation ({fields}); the initial mass comes from that calculation, so thrust and propellant mass would belong to two different motors. Press Calculate first, then run the trajectory.'));
        }
        
        const requestData = {
            ...baseData,
            initial_mass: initialMass,
            final_mass: finalMass,
            drag_coefficient: dragCoeff,
            reference_area: refArea,
            trajectory_start_altitude: trajAltStart,
            trajectory_end_altitude: trajAltEnd,
            trajectory_points: trajPoints,
            launch_angle: launchAngle,
            wind_speed: windSpeed
        };
        
        // Call trajectory analysis API
        const response = await fetch('/api/trajectory-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });
        
        if (!response.ok) {
            // ÖH D31 · OH-D30-02 — ham gövde metnini ekrana dökmek yerine
            // ucun YAPILI ret sözleşmesi (`invalid_fields`/`missing_fields`)
            // alan adlarıyla basılır. Çözücü TEK kaynakta: reject_body.js.
            throw await HRMAReject.hata(response);
        }
        
        const result = await response.json();
        
        if (result.status === 'error' || result.error) {
            throw new Error(result.error || T('app.msg.trajFailed', 'Trajectory analysis failed'));
        }
        
        // Display trajectory plot
        const plotContainer = document.getElementById('trajectory_plot');
        if (!plotContainer) {
            // Create plot container if it doesn't exist
            const trajectoryTab = document.getElementById('trajectory_tab');
            if (trajectoryTab) {
                const newContainer = document.createElement('div');
                newContainer.id = 'trajectory_plot';
                newContainer.className = 'plot-container';
                trajectoryTab.appendChild(newContainer);
            }
        }
        
        if (result.plot_data) {
            try {
                let plotData;
                if (typeof result.plot_data === 'string') {
                    plotData = JSON.parse(result.plot_data);
                } else {
                    plotData = result.plot_data; // Already parsed
                }
                
                Plotly.newPlot('trajectory_plot', plotData.data, plotData.layout, {responsive: true});

                // Show the trajectory tab if hidden
                const trajectoryTab = document.getElementById('trajectory_tab');
                if (trajectoryTab && trajectoryTab.style.display === 'none') {
                    trajectoryTab.style.display = 'block';
                }
            } catch (parseError) {
                console.error('Plot data parsing error:', parseError);
                console.error('Raw plot data:', result.plot_data);
                showWarning(T('app.msg.trajPlotFailed', 'Plot visualization failed, but trajectory data is available'));
            }
        } else {
            showWarning(T('app.msg.trajNoPlot', 'No plot data received from trajectory analysis'));
        }
        
        // Show success message with engine data
        if (result.engine_data) {
            const engineData = result.engine_data;
            showMessage(TF('app.msg.trajOkEngine',
                { thrust: numTxt(engineData.thrust, 0), isp: numTxt(engineData.isp, 1) },
                'Trajectory analysis completed! Engine: {thrust} N thrust, {isp} s Isp'),
                'success');
        } else {
            showMessage(T('app.msg.trajOk', 'Trajectory analysis completed successfully!'), 'success');
        }
        
    } catch (error) {
        showError(TF('app.msg.trajError', { message: error.message }, 'Trajectory analysis failed: {message}'));
    } finally {
        showLoading(false);
    }
}

// Display Motor Design Table
function displayMotorTable(motorData) {
    const motorTableBody = document.querySelector('#motor_table tbody');
    if (!motorTableBody) return;
    
    const motorRows = [
        [T('app.rep.throatDia', 'Throat Diameter'), numTxt((motorData.throat_diameter * 1000), 1), 'mm'],
        [T('app.rep.exitDia', 'Exit Diameter'), numTxt((motorData.exit_diameter * 1000), 1), 'mm'],
        [T('common.f.expansionRatio', 'Expansion Ratio'), numTxt(motorData.expansion_ratio, 1), '-'],
        [T('app.rep.chamberDia', 'Chamber Diameter'), numTxt((motorData.chamber_diameter * 1000), 1), 'mm'],
        [T('app.rep.chamberLen', 'Chamber Length'), numTxt((motorData.chamber_length * 1000), 1), 'mm'],
        [T('app.rep.chamberVolume', 'Chamber Volume'),
         chamberVolumeM3(motorData) === null
             ? T('common.notComputed', 'not computed')
             : numTxt((chamberVolumeM3(motorData) * 1e6), 1),
         chamberVolumeM3(motorData) === null ? '' : 'cm³'],
        [T('app.metric.pc', 'Chamber Pressure'), numTxt((motorData.chamber_pressure), 1), 'bar'],
        [T('app.metric.thrust', 'Thrust'), numTxt((motorData.thrust), 0), 'N'],
        [T('app.metric.ispDesign', 'Isp (design point, at design-altitude ambient)'), numTxt(motorData.isp, 1), 's'],
        [T('app.rep.cstar', 'Characteristic Velocity'), numTxt(motorData.c_star, 0), 'm/s'],
        [T('app.rep.cf', 'Thrust Coefficient'), numTxt(motorData.cf, 3), '-'],
        [T('app.metric.mdot', 'Mass Flow Rate'), numTxt(motorData.mdot_total, 3), 'kg/s']
    ];
    
    motorTableBody.innerHTML = '';
    motorRows.forEach(([param, value, unit]) => {
        const row = motorTableBody.insertRow();
        row.insertCell(0).textContent = param;
        row.insertCell(1).textContent = value;
        row.insertCell(2).textContent = unit;
    });
}

// Display Injector Design Table
// V301/E2 — ``yalnizSatirlar`` true ise tablo ÇİZİLMEZ, satırlar döner
// ({rows, specific}); tasarım raporu ve metin dışa aktarımı enjektör
// satırlarını BURADAN alır (tek kaynak: tablonun kanon geometri satırları,
// bütün tiplerde). Tablo davranışı değişmedi.
function displayInjectorTable(injectorData, yalnizSatirlar) {
    const injectorTableBody = yalnizSatirlar ? null
        : document.querySelector('#injector_table tbody');
    if (!yalnizSatirlar && !injectorTableBody) return;
    injectorData = injectorData || {};

    // Sayisal alanlari guvenli bicimle: 0 gecerli bir degerdir ('N/A' degil).
    const fmt = (v, digits) => (typeof v === 'number' && isFinite(v))
        ? numTxt(v, digits) : 'N/A';
    
    const injectorRows = [
        [T('common.type', 'Type'), injectorData.type, '-'],
        [T('app.rep.exitVelocity', 'Exit Velocity'), numTxt(injectorData.exit_velocity, 1), 'm/s'],
        [T('app.rep.reynolds', 'Reynolds Number'), numTxt(injectorData.reynolds_number, 0), '-'],
        [T('app.rep.pressureDrop', 'Pressure Drop'), numTxt(injectorData.pressure_drop, 2), 'bar']
    ];
    const ozelBas = injectorRows.length;
    
    // Add type-specific parameters
    if (injectorData.type === 'showerhead') {
        injectorRows.push([T('app.rep.nHoles', 'Number of Holes'), injectorData.n_holes || 'N/A', '-']);
        injectorRows.push([T('app.rep.holeDia', 'Hole Diameter'), injectorData.hole_diameter ? numTxt(injectorData.hole_diameter, 2) : 'N/A', 'mm']);
        injectorRows.push([T('app.rep.ldRatio', 'L/D Ratio'), injectorData.l_d_ratio ? numTxt(injectorData.l_d_ratio, 1) : 'N/A', '-']);
    } else if (injectorData.type === 'pintle') {
        // V301/E1 — satırlar KANON pintle geometrisinden (``injector.
        // pintle_geometry`` = devre çözücüsünün geometrisi; ekran bloğu onu
        // tüketir). Olmayan alan 'N/A' basar, sayı uydurulmaz; gövde dış
        // çapı verilmediyse "boyutlandırılmadı" yazar.
        const pg = injectorData.pintle_geometry || {};
        const sayi = (v) => typeof v === 'number' && isFinite(v);
        const delikYok = pg.secondary_holes === 'none';
        const kipAdi = {
            none: T('app.rep.pintleNoTipHoles', 'none (annular element)'),
            radial: T('app.rep.pintleModeRadial', 'radial'),
            tangential: T('app.rep.pintleModeTangential', 'tangential'),
        };
        injectorRows.push([T('app.rep.pintleSecondaryHoles', 'Secondary Holes'),
                           kipAdi[pg.secondary_holes]
                               || (pg.secondary_holes ? String(pg.secondary_holes) : 'N/A'), '-']);
        injectorRows.push([T('app.rep.pintleDia', 'Pintle Tip Diameter D_p'), fmt(injectorData.pintle_diameter, 2), 'mm']);
        injectorRows.push([T('app.rep.gap', 'Annular Gap t'), fmt(injectorData.gap, 3), 'mm']);
        injectorRows.push([T('app.rep.pintleBore', 'Annulus Bore D_p + 2t'), fmt(injectorData.annulus_bore_diameter, 2), 'mm']);
        if (sayi(injectorData.outer_diameter)) {
            injectorRows.push([T('app.rep.outerDia', 'Injector Body Outer Diameter'), fmt(injectorData.outer_diameter, 1), 'mm']);
            injectorRows.push([T('app.rep.pintleBodyWall', 'Body Wall (OD - bore)/2'), fmt(injectorData.body_wall_thickness, 2), 'mm']);
        } else {
            injectorRows.push([T('app.rep.outerDia', 'Injector Body Outer Diameter'),
                               T('app.rep.pintleNotSized', 'not sized (not supplied)'), '-']);
        }
        if (delikYok) {
            injectorRows.push([T('app.rep.pintleTipHoles', 'Tip Holes n x d'),
                               T('app.rep.pintleNoTipHoles', 'none (annular element)'), '-']);
        } else {
            injectorRows.push([T('app.rep.pintleTipHoles', 'Tip Holes n x d'),
                               (sayi(pg.n_radial_holes) && sayi(pg.radial_hole_d_mm))
                                   ? `${pg.n_radial_holes} x ${numTxt(pg.radial_hole_d_mm, 3)}` : 'N/A', 'mm']);
            injectorRows.push([T('app.rep.pintleBf', 'Blockage Factor BF'), fmt(pg.bf, 3), '-']);
            injectorRows.push([T('app.rep.pintleRadialShare', 'Radial Flow Share'),
                               sayi(pg.radial_flow_fraction) ? numTxt(pg.radial_flow_fraction * 100, 1) : 'N/A', '%']);
            injectorRows.push([T('app.rep.pintleTmr', 'Total Momentum Ratio TMR'), fmt(pg.tmr, 3), '-']);
            injectorRows.push([T('app.rep.pintleSprayHalf', 'Spray Half-Angle (from TMR)'), fmt(pg.spray_half_angle_deg, 1), '°']);
            if (pg.spray_angle_basis) {
                injectorRows.push([T('app.rep.pintleSprayBasis', 'Spray Angle Basis'), String(pg.spray_angle_basis), '-']);
            }
            injectorRows.push([T('app.rep.pintleSkip', 'Skip Distance L_s'), fmt(pg.skip_distance_mm, 2), 'mm']);
        }
        if (injectorData.pintle_geometry_source) {
            injectorRows.push([T('app.rep.pintleGeometrySource', 'Pintle Geometry Source'),
                               String(injectorData.pintle_geometry_source), '-']);
        }
    } else if (injectorData.type === 'swirl') {
        // ÖH D25 · P11B2-23 — SWIRL ALANLARI TABLOYA DA GİRER.
        // ÖLÇÜLDÜ (a3/once.json, taban cdf2106): bu dal HİÇ YOKTU —
        // `displayInjectorTable` yalnız showerhead ve pintle dallarını
        // taşıyordu, swirl seçildiğinde `n_slots` / `slot_width` /
        // `slot_height` / `spray_angle` tabloya girmiyordu (yalnız
        // tasarım raporunda vardı) ve yanıtın taşıdığı film kalınlığı,
        // atomizasyon sabiti, hava çekirdeği oranı, yarık hızı gibi
        // alanlar hiçbir yerde okunmuyordu. Alanlar yükten geldiği gibi
        // basılır; olmayan alan satır AÇMAZ (uydurma sayı yok).
        injectorRows.push([T('app.rep.nSlots', 'Number of Slots'),
                           injectorData.n_slots !== undefined
                               ? String(injectorData.n_slots) : 'N/A', '-']);
        injectorRows.push([T('app.rep.slotWidth', 'Slot Width'),
                           fmt(injectorData.slot_width, 3), 'mm']);
        injectorRows.push([T('app.rep.slotHeight', 'Slot Height'),
                           fmt(injectorData.slot_height, 3), 'mm']);
        // Etiket belirsizliği giderildi: çözücü `spray_angle`'ı TAM koni
        // açısı (2θ) diye tanımlar (hrma/utils/injector_design.py) ve yarı
        // açıyı AYRI alanda verir; aynı rapor lüle için "Convergent HALF
        // Angle" ayrımını zaten yapıyor.
        injectorRows.push([T('app.rep.sprayAngleFull',
                             'Spray Cone Angle (full, 2\u03B8)'),
                           fmt(injectorData.spray_angle, 2), '°']);
        if (injectorData.spray_half_angle_deg !== undefined
                && injectorData.spray_half_angle_deg !== null) {
            injectorRows.push([T('app.rep.sprayHalfAngle',
                                 'Spray Half Angle (\u03B8)'),
                               fmt(injectorData.spray_half_angle_deg, 2), '°']);
        }
        if (injectorData.film_thickness_mm !== undefined
                && injectorData.film_thickness_mm !== null) {
            injectorRows.push([T('app.rep.filmThickness', 'Film Thickness'),
                               fmt(injectorData.film_thickness_mm, 4), 'mm']);
        }
        if (injectorData.slot_velocity !== undefined
                && injectorData.slot_velocity !== null) {
            injectorRows.push([T('app.rep.slotVelocity',
                                 'Tangential Slot Velocity'),
                               fmt(injectorData.slot_velocity, 1), 'm/s']);
        }
        if (injectorData.atomizer_constant_K !== undefined
                && injectorData.atomizer_constant_K !== null) {
            injectorRows.push([T('app.rep.atomizerK',
                                 'Atomizer Constant K'),
                               fmt(injectorData.atomizer_constant_K, 4), '-']);
        }
        if (injectorData.air_core_ratio_X !== undefined
                && injectorData.air_core_ratio_X !== null) {
            injectorRows.push([T('app.rep.airCoreX', 'Air Core Ratio X'),
                               fmt(injectorData.air_core_ratio_X, 4), '-']);
        }
        if (injectorData.swirl_chamber_d_source) {
            injectorRows.push([T('app.rep.swirlChamberSource',
                                 'Swirl Chamber Diameter Source'),
                               String(injectorData.swirl_chamber_d_source), '-']);
        }
        // V301/E2 — swirl elemanı devre kanonundan: eleman sayısı, çıkış
        // orifisi, oda çapı, orifis ortalama hızı (devre tablosuyla aynı
        // tanım) ve K'nın dayanağı. Olmayan alan satır açmaz.
        if (typeof injectorData.n_elements === 'number') {
            injectorRows.push([T('app.rep.swirlElements', 'Swirl Elements'),
                               String(injectorData.n_elements), '-']);
        }
        if (typeof injectorData.exit_orifice_diameter === 'number') {
            injectorRows.push([T('app.rep.exitOrificeDia',
                                 'Exit Orifice Diameter d_o (per element)'),
                               fmt(injectorData.exit_orifice_diameter, 3), 'mm']);
        }
        if (typeof injectorData.swirl_chamber_diameter === 'number') {
            injectorRows.push([T('app.rep.swirlChamberDia',
                                 'Swirl Chamber Diameter D_s'),
                               fmt(injectorData.swirl_chamber_diameter, 2), 'mm']);
        }
        if (typeof injectorData.orifice_mean_velocity === 'number') {
            injectorRows.push([T('app.rep.orificeMeanVelocity',
                                 'Orifice Mean Velocity (circuit definition)'),
                               fmt(injectorData.orifice_mean_velocity, 1), 'm/s']);
        }
        if (injectorData.exit_velocity_basis) {
            injectorRows.push([T('app.rep.exitVelocityBasis', 'Exit Velocity Basis'),
                               String(injectorData.exit_velocity_basis), '-']);
        }
        if (injectorData.slot_size_source) {
            injectorRows.push([T('app.rep.slotSizeSource', 'Slot Size Source'),
                               String(injectorData.slot_size_source), '-']);
        }
        if (injectorData.swirl_k_source) {
            injectorRows.push([T('app.rep.swirlKSource', 'Atomizer Constant Source'),
                               String(injectorData.swirl_k_source), '-']);
        }
    } else if (injectorData.type === 'impingement') {
        // V301/E2 — çarpışmalı satırlar (eskiden bu dal YOKTU: delik planı,
        // açı ve mesafe tabloya hiç girmiyordu). Plan devre kanonudur
        // (benzer-akışkan çift, çift sayıda delik).
        injectorRows.push([T('app.rep.impElement', 'Element'),
                           T('app.rep.impLikeDoublet',
                             'like-on-like doublet (oxidizer on oxidizer)'), '-']);
        injectorRows.push([T('app.rep.impPairs', 'Doublet Pairs (holes)'),
                           (typeof injectorData.n_pairs === 'number'
                            && typeof injectorData.n_holes === 'number')
                               ? `${injectorData.n_pairs} (${injectorData.n_holes})` : 'N/A', '-']);
        injectorRows.push([T('app.rep.holeDia', 'Hole Diameter'),
                           fmt(injectorData.hole_diameter, 3), 'mm']);
        if (typeof injectorData.hole_diameter_requested === 'number') {
            injectorRows.push([T('app.rep.impHoleRequested', 'Requested Hole Diameter'),
                               fmt(injectorData.hole_diameter_requested, 3), 'mm']);
        }
        injectorRows.push([T('app.rep.impAngle', 'Impingement Angle 2\u03B8'),
                           fmt(injectorData.impingement_angle_deg, 1), '°']);
        injectorRows.push([T('app.rep.impDistance',
                             'Distance to Impingement (computed)'),
                           fmt(injectorData.impingement_distance, 2), 'mm']);
        injectorRows.push([T('app.rep.axialVelocity', 'Axial Velocity Component'),
                           fmt(injectorData.axial_velocity, 1), 'm/s']);
        injectorRows.push([T('app.rep.plateThickness', 'Plate Thickness'),
                           injectorData.plate_thickness_earned === true
                               ? fmt(injectorData.plate_thickness, 2)
                               : T('app.rep.plateNotSupplied',
                                   'not supplied (module default, no L/D verdict)'),
                           injectorData.plate_thickness_earned === true ? 'mm' : '-']);
        if (injectorData.impingement_plan_source) {
            injectorRows.push([T('app.rep.impPlanSource', 'Hole Plan Source'),
                               String(injectorData.impingement_plan_source), '-']);
        }
    } else if (injectorData.type === 'coaxial') {
        // V301/E2 — koaksiyel satırlar (eskiden bu dal YOKTU). Tek akışkan:
        // iç jet ve dış halka ikisi de oksitleyici; çaplar iç jet payından ve
        // debiden boyutlandırılır. Devre çözümü yoktur (satırda yazar).
        injectorRows.push([T('app.rep.coaxInnerJet', 'Inner Jet Diameter'),
                           fmt(injectorData.inner_jet_diameter, 3), 'mm']);
        injectorRows.push([T('app.rep.coaxAnnulusInner', 'Annulus Inner Diameter'),
                           fmt(injectorData.annulus_inner_diameter, 3), 'mm']);
        injectorRows.push([T('app.rep.coaxAnnulusOuter', 'Annulus Outer Diameter'),
                           fmt(injectorData.annulus_outer_diameter, 3), 'mm']);
        injectorRows.push([T('app.rep.coaxGap', 'Annulus Gap'),
                           fmt(injectorData.annulus_gap, 3), 'mm']);
        injectorRows.push([T('app.rep.coaxRecess', 'Recess (computed)'),
                           fmt(injectorData.recess_length, 3), 'mm']);
        injectorRows.push([T('app.rep.coaxInnerShare', 'Inner Jet Flow Share'),
                           typeof injectorData.inner_flow_fraction === 'number'
                               ? numTxt(injectorData.inner_flow_fraction * 100, 1) : 'N/A', '%']);
        if (injectorData.inner_flow_fraction_source) {
            injectorRows.push([T('app.rep.coaxShareSource', 'Flow Share Source'),
                               String(injectorData.inner_flow_fraction_source), '-']);
        }
        if (injectorData.circuit_solution) {
            injectorRows.push([T('app.rep.coaxCircuit', 'Injector Circuit Solution'),
                               String(injectorData.circuit_solution), '-']);
        }
    }
    const ozelSon = injectorRows.length;
    
    // Add common parameters
    // BIRIM SOZLESMESI (v2.5.2): backend injection_area'yi mm2 olarak
    // dondurur (eskiden burada tekrar 1e6 ile carpiliyor, 10^6 kat sisik
    // deger cikiyordu). mixing_efficiency backend'de zaten yuzde.
    injectorRows.push([T('app.rep.cd', 'Discharge Coefficient'), fmt(injectorData.discharge_coefficient, 3)]);
    injectorRows.push([T('app.rep.injectionArea', 'Injection Area'), fmt(injectorData.injection_area, 2), 'mm²']);

    // Add injector diameter if available
    if (injectorData.injector_diameter) {
        injectorRows.push([T('app.rep.maxInjectorDia', 'Max Injector Diameter'),
                           numTxt(injectorData.injector_diameter, 1), 'mm']);
    }

    injectorRows.push([T('app.rep.weber', 'Weber Number'), fmt(injectorData.weber_number, 0)]);
    if (injectorData.momentum_ratio !== undefined && injectorData.momentum_ratio !== null) {
        injectorRows.push([T('app.rep.momentumRatio', 'Momentum Flux Ratio'),
                           fmt(injectorData.momentum_ratio, 2)]);
    }
    if (injectorData.mixing_efficiency !== undefined && injectorData.mixing_efficiency !== null) {
        injectorRows.push([T('app.rep.mixingEfficiency', 'Mixing Efficiency'),
                           fmt(injectorData.mixing_efficiency, 1), '%']);
    }
    if (injectorData.pressure_drop_source) {
        injectorRows.push([T('app.rep.dpBasis', 'Pressure Drop Basis'),
                           injectorData.pressure_drop_source, '-']);
    }
    // P11B2-23: uç boşaltma katsayısının DAYANAĞINI da yayımlıyor
    // (`discharge_coefficient_basis`); tabloda okunmuyordu.
    if (injectorData.discharge_coefficient_basis) {
        injectorRows.push([T('app.rep.cdBasis', 'Discharge Coefficient Basis'),
                           String(injectorData.discharge_coefficient_basis), '-']);
    }
    
    if (yalnizSatirlar) {
        return { rows: injectorRows,
                 common: injectorRows.slice(0, ozelBas),
                 specific: injectorRows.slice(ozelBas, ozelSon) };
    }
    injectorTableBody.innerHTML = '';
    injectorRows.forEach(([param, value, unit]) => {
        const row = injectorTableBody.insertRow();
        row.insertCell(0).textContent = param;
        row.insertCell(1).textContent = value;
        row.insertCell(2).textContent = unit || '-';
    });
}