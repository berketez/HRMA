/* ====================================================================
   HRMA Termal FEA Paneli (D2 — geçici ısı iletimi çözücüsünün kullanıcı yüzü)
   --------------------------------------------------------------------
   POST /api/fea/thermal ucu 2026-08-15 denetimine kadar SAĞLAMDI ama
   HİÇBİR kullanıcı yüzü onu çağırmıyordu (ölçüldü): kullanıcı ne sıcaklık
   alanını ne de malzeme sınırı hükmünü görebiliyordu. Bu panel zinciri
   kapatır — 2.7 kapı ölçütü #1: "mesh üstünde sıcaklık konturu EKRANDA".

   ÖLÇÜLMÜŞ ÇALIŞAN ZİNCİR (canlı sunucuda doğrulandı, bire bir uyulur):
     1) Hibrit sonucunun DÜZ alanlarından POST /api/analysis/wall-profile
        → yanıt.wall_profile (x_mm, h_g, T_recovery, ...).
     2) POST /api/fea/thermal gövdesi:
        { motor_results: <sonuç sözlüğü>,
          axial_profile: <wall_profile bloğu AYNEN>,
          ambient_temperature_K: <kullanıcı alanı> }
        → fea.fields.temperature_final_K (düğüm alanı), iç yüzey T(z),
          tepe cidar T(t) geçmişi, mesh, malzeme sınırı hükmü, enerji
          bütçesi, zaman adımı beyanı, warnings[].
   Motor sözlüğünden h(z) TÜRETİLMEZ (uç da türetmez; app.py:7576
   docstring). Eksik girdi → HTTP 200 + fea.missing[] + fea.reason;
   panel hiçbir şey çizmez, eksiği ADIYLA basar.

   BİRİM TUZAĞI (panels/thermal_panel.js readAxialPayload'da ölçülen
   kusurun aynısı): /api/analysis/wall-profile uzunlukları METRE bekler,
   ama motor sonuç sözlükleri motor tipine göre mm taşıyabilir (katı düz
   alanları mm, hibrit m — analysis_dock.js LENGTH_UNITS, ölçülmüş).
   Dönüşüm ALANIN KAYNAĞINA göre yapılır: önce AnalysisDock.ui.readLengthM
   (tek tanım yeri), o yoksa motor_geometry SI bloğu. "x > 2 ise mm'dir"
   gibi büyüklük sezgiseli YOKTUR ve bekçi testi bunu kilitler.

   SAHTE VERİ YASAĞI (fea_panel.js sözleşmesinin aynısı):
     * status != 'ok' → hiçbir alan çizilmez; missing/reason basılır.
     * Çekirdek motor alanı eksikse uç HİÇ ÇAĞRILMAZ: wall-profile ucunun
       sunucu varsayılanları (20 bar / 3000 K ...) BAŞKA bir motorun
       profili demektir; panel eksiği kendi beyanıyla adlandırır.
     * ambient_temperature_K kullanıcı alanı boşsa UYDURULMAZ; uç eksiği
       kendi sözleşmesiyle adlandırır ve panel onu basar.
     * Yeni motor sonucu gelince eski FEA çıktısı BAYATTIR, silinir.
     * outer_ambient İSTENMEZ: uç dış yüzeyi adyabatik alır ve bunu kendi
       cümlesiyle beyan eder; panel o beyanı AYNEN gösterir.
     * İlerleme yüzdesi yoktur; belirsiz süreli iş belirsiz gösterge alır.

   Birim: çözücü kelvin + metre + saniye döner; panel HİÇBİR ölçekleme,
   yumuşatma veya yeniden örnekleme yapmaz (değerler aynen çizilir).

   Kullanım (advanced.html):
     <script src="/static/js/thermal_fea_panel.js"></script>
     ThermalFeaPanel.init({ anchorId: 'feaPanel',
                            fallbackAnchorId: 'trajectoryPanel',
                            hookName: 'displayCalculationResults' });
   Panel #feaPanel'in HEMEN ALTINA yerleşir.

   Bekçi testleri: tests/test_thermal_fea_panel.py (node ile izole koşum)
   + tests/test_fea_termal_uc.py (uç sözleşmesi).
   ==================================================================== */

(function () {
    'use strict';

    const PROFILE_ENDPOINT = '/api/analysis/wall-profile';
    const THERMAL_ENDPOINT = '/api/fea/thermal';

    /* ÖH D26 / P11B3-16 — ORTAM SICAKLIĞI ALANININ SAHİBİ.
       ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): `#fea_t_ambient` alanı
       `value="293.15"` ile ÖNCEDEN DOLUYDU ve panel bu sonlu sayının
       KENDİSİNE ait olduğunu hiçbir yerde söylemiyordu; `readAmbientK()`
       alandan ne okursa onu `ambient_temperature_K` diye gönderiyordu.
       Yani kullanıcı hiçbir şey yazmasa bile uç, kullanıcı 293,15 K
       demiş gibi bir başlangıç koşuluyla çözüyordu. Kardeş CFD paneli
       aynı konuda TERS politika uygular: `P_ambient_Pa` onun
       REQUIRED_FIELDS listesindedir ve motorun kendi sonucundan çözülür
       (ölçüldü: cfd_ambient_zorunlu = 1).

       ÖK-21 bu dalgada form katmanının `value`/`||` sökümünü YASAKLADIĞI
       için alan dolu KALIR; onarım SAHİPLİK katmanındadır:
         * sayı ARTIK TEK YERDE yaşar (doktrin 4) — HTML'e ikinci kez
           yazılmaz, alan bu sabitten kurulur;
         * alan kullanıcı tarafından değiştirilene kadar `data-dirty`
           taşımaz ve panel gönderdiği sayının KİMİN olduğunu ekranda
           ADIYLA ilan eder (rozet + künye satırı).
       Böylece "kullanıcının verdiği sayı" ile "panelin varsayılanı"
       ekranda ayrılır; sessiz varsayılan kalmaz. */
    const AMBIENT_PANEL_DEFAULT_K = 293.15;

    let cfg = {};
    let lastMotorResults = null;     // paneli besleyecek motor sonucu
    let lastPayload = null;          // son FEA yanıtı (fea bloğu)
    let lastError = null;            // ağ/sunucu hatası metni
    let busy = false;
    let busySince = null;      // koşumun başlangıç damgası (P17B1-18)
    let showMesh = true;             // tel-kafes katmanı açık/kapalı
    let carpetFallback = false;      // carpet çizilemedi → nokta haritası
    //: Son koşumda gönderilen ortam sıcaklığının KAYNAĞI (P11B3-16):
    //: 'user' (alan elle değiştirilmişti) | 'panel_default' (panelin
    //: kendi sabiti) | null (henüz koşulmadı). Uydurulmaz: alanın
    //: `data-dirty` imi neyse o.
    let ambientSource = null;
    //: ÖH D26 / OH-B3-02 — /api/analysis/wall-profile `contour_basis`
    //: bloğu (h(z) profilinin dayandığı konturun künyesi, 7 alt alan).
    //: ÖLÇÜLDÜ (a2/once.json): panel bu bloğu ne kendi adıyla ne bir
    //: çocuğuyla anıyordu — profil ekranda KÜNYESİZ çiziliyordu.
    let lastContourBasis = null;
    //: ÖH D28 / arayuz a1 (OH-D27-16) — /api/analysis/wall-profile
    //: `column_basis` (6 sütunun dayanağı) ve `units` (14 sütunun birimi)
    //: blokları. ÖLÇÜLDÜ (a1/once.json, taban 7cd08bcc): panelin 191 adlık
    //: okuma envanterinde ikisi de 0 kez geçiyordu; `column_basis`ın ALTI
    //: çocuğunun (h_g, q_MW, T_wall_eq, T_recovery, mach, area_ratio)
    //: hiçbiri de okunmuyordu — SAĞIR ALT BLOK.
    let lastColumnBasis = null;
    let lastProfileUnits = null;
    //: ÖH D37 A2-1 termal 7. tur (karar §28-24 §2 b) — h(z) profilinin
    //: γ / MW / c* kökeni (`wall_profile.gas_properties_basis`). Uç
    //: yayımlamadıysa null; künyede ADIYLA basılır, uydurulmaz.
    let lastGasBasis = null;

    // i18n köprüleri — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    // v3.0.1 N-girdi-2: alan ipucu ortak bileşenden (field_help.js →
    // HRMAHelp); anahtar çağıranda LİTERAL. Bileşen yoksa ipucu basılmaz.
    function yardimHtml(key) {
        return (key && window.HRMAHelp && typeof window.HRMAHelp.html === 'function')
            ? window.HRMAHelp.html(key, T(key, '')) : '';
    }
    /* ÖH D23 / P17B4-07 + P17B1-18 — İSTEK ZAMAN AŞIMI.
       Süre sınırı TEK KAYNAKTAN gelir: fea_panel.js onu
       `window.HRMA_ISTEK_ZAMAN_ASIMI_MS` ile yayımlar (doktrin 4 — sayı
       ikinci kez YAZILMAZ). fea_panel.js bu panelin yüklü olduğu tek
       şablonda (advanced.html) da yüklüdür; yine de yayım yoksa sinyal
       kurulmaz ve panel eski davranışına düşer (sessiz uydurma yok). */
    function zamanAsimiMs() {
        const v = window.HRMA_ISTEK_ZAMAN_ASIMI_MS;
        return (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;
    }

    function zamanAsimiSinyali() {
        const ms = zamanAsimiMs();
        return (ms && typeof AbortSignal !== 'undefined' && AbortSignal.timeout)
            ? AbortSignal.timeout(ms) : undefined;
    }

    function zamanAsimiMi(e) {
        const ad = e && e.name;
        return ad === 'TimeoutError' || ad === 'AbortError';
    }

    /* ÖH D26 · P11B3-19 — KULLANICI KOŞUMU DURDURABİLİR.
       ÖLÇÜLDÜ (a3/once.json, taban 7751531): term_abort_controller = 0,
       term_iptal_dugmesi = 0. Zaman aşımı vardı, iptal yoktu; tek çıkış
       sayfayı yenilemekti. Desen fea_panel.js ile BİREBİR aynıdır
       (süre sınırı yine oradan, tek kaynaktan gelir).
       İki durdurucu AYRI cümleyle beyan edilir. */
    let denetleyici = null;
    let kullaniciIptali = false;
    /* İki ADIMLI koşumun (h(z) profili -> geçici FEA) TEK sinyali: iptal
       ikinci adımı da durdurur ve süre sınırı koşumun TAMAMINI ölçer. */
    let aktifSinyal = null;

    function kosumSinyali() {
        kullaniciIptali = false;
        if (typeof AbortController !== 'function') {
            aktifSinyal = zamanAsimiSinyali();
            return aktifSinyal;
        }
        const c = new AbortController();
        denetleyici = c;
        const zs = zamanAsimiSinyali();
        if (zs && typeof AbortSignal !== 'undefined'
                && typeof AbortSignal.any === 'function') {
            aktifSinyal = AbortSignal.any([c.signal, zs]);
            return aktifSinyal;
        }
        const ms = zamanAsimiMs();
        if (ms && typeof setTimeout === 'function') {
            const t = setTimeout(function () {
                if (denetleyici === c) c.abort();
            }, ms);
            if (typeof c.signal.addEventListener === 'function') {
                c.signal.addEventListener('abort', function () {
                    if (typeof clearTimeout === 'function') clearTimeout(t);
                });
            }
        }
        aktifSinyal = c.signal;
        return aktifSinyal;
    }

    function kosumuIptalEt() {
        if (!denetleyici) return false;
        const c = denetleyici;
        kullaniciIptali = true;
        denetleyici = null;
        try { c.abort(); } catch (e) { return false; }
        return true;
    }

    function kosumBitti() {
        denetleyici = null;
        aktifSinyal = null;
    }

    /* Meşgul satırı nabzı: geçen süre GERÇEK ölçümdür, yüzde YOKTUR. */
    const NABIZ_MS = 1000;
    let nabizTimer = null;

    function nabziDurdur() {
        if (nabizTimer) { clearInterval(nabizTimer); nabizTimer = null; }
    }

    /* Savunmacı öznitelik yazımı — bkz. fea_panel.js aynı not. */
    function ozY(el, ad, deger) {
        if (el && typeof el.setAttribute === 'function') el.setAttribute(ad, deger);
    }

    function ozS(el, ad) {
        if (el && typeof el.removeAttribute === 'function') el.removeAttribute(ad);
    }

    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // Sunucu üretimi serbest metin (beyan/gerekçe) — sözlükte karşılığı
    // varsa çevrilir, yoksa AYNEN kalır.
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    function fmt(v, digits) {
        return isNum(v) ? v.toFixed(digits === undefined ? 2 : digits) : '—';
    }

    /* ÖH D37 A2-1 denetçi Ş4 — EKRAN biçimlendiricisi (§0 kural 4: TR
       ekranda ondalık VİRGÜL; makine kanalı nokta kalır). TF yalnız BAŞTAN
       SONA sayı olan parametreyi çevirir (I18N.decimalText); merdiven
       satırı gibi birleşik metinlerin içindeki sayılar noktalı kalıyordu
       (ölçüldü: TR künyede "16×4 2582.55 K"). Sayı burada, metne
       girmeden, aynı tek kaynaktan (I18N.decimalText) geçirilir; I18N yoksa
       (node bekçisi) fmt çıktısı aynen döner. */
    function fmtScr(v, digits) {
        const s = fmt(v, digits);
        return (window.I18N && typeof window.I18N.decimalText === 'function')
            ? window.I18N.decimalText(s) : s;
    }

    // Enerji artığı gibi çok küçük sayılar için üstel biçim.
    function fmtExp(v) {
        return isNum(v) ? v.toExponential(1) : '—';
    }

    // ==================================================================
    // >>> THERMAL_FEA_PAYLOAD_START
    // Girdi hazırlığı — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // doğrudan koşturur (birim dönüşümü kilidi burada sınanır).
    // ==================================================================

    function motorDictLocal(r) {
        return (r && r.motor && typeof r.motor === 'object') ? r.motor : (r || null);
    }

    // AnalysisDock yokken kullanılan uzunluk okuyucu (METRE döner).
    // Öncelik motor_geometry bloğudur: o blok SI beyanlıdır
    // (analysis_dock.js readLengthM ölçümüyle aynı). Düz alan ancak bu
    // panelin yaşadığı hibrit sayfa sözleşmesiyle okunur: hibrit düz
    // uzunlukları METREDİR (LENGTH_UNITS.hybrid, ölçülmüş). Büyüklüğe
    // bakarak birim TAHMİN EDİLMEZ — mm taşıyan katı/sıvı sözlükleri
    // motor_geometry SI bloğuyla yakalanır, yakalanamıyorsa alan eksik
    // sayılır (uydurma dönüşüm yok).
    function fallbackLengthM(results, key) {
        const m = motorDictLocal(results) || {};
        const g = m.motor_geometry;
        if (g && typeof g === 'object' && isNum(g[key])) {
            return g[key];              // motor_geometry SI (ölçüldü)
        }
        const v = m[key];
        return isNum(v) ? v : undefined;
    }

    // Uzunluk okuma — TEK yetkili AnalysisDock.ui.readLengthM'dir (motor
    // tipine göre mm/m tablosunu o taşır; tablo burada İKİNCİ KEZ
    // yazılmaz). Dock yüklü değilse (test ortamı) yukarıdaki yedek çalışır.
    function readLen(results, key) {
        const AD = window.AnalysisDock;
        if (AD && AD.ui && typeof AD.ui.readLengthM === 'function') {
            const v = AD.ui.readLengthM(results, key);
            return isNum(v) ? v : undefined;
        }
        return fallbackLengthM(results, key);
    }

    //: Uçtaki motor_data çekirdeğinin düz (birimsiz sorunlu olmayan)
    //: alanları — hepsinin sunucu tarafında VARSAYILANI vardır, o yüzden
    //: eksikse istek GÖNDERİLMEZ (varsayılan başka motorun profili olur).
    const CORE_FLAT_FIELDS = ['chamber_pressure', 'chamber_temperature',
                              'burn_time', 'mdot_total'];
    //: Uzunluk alanları — uç METRE bekler; okuma readLen üzerinden.
    const CORE_LENGTH_FIELDS = ['chamber_diameter', 'chamber_length'];

    /* ÖH D37 A2-1 / F-03 (CW-S5) — MOTOR DÜZENİ. Köprünün kendi imzası
       (hrma/fea/bridge.py detect_engine_layout: structural_analysis altında
       chamber_analysis → hybrid, chamber_structure → liquid, case_analysis →
       solid) burada da AYNI kuralla okunur; tahmin yok, imza yoksa null. */
    function engineLayoutLocal(m) {
        const sa = m && m.structural_analysis;
        if (!sa || typeof sa !== 'object') return null;
        if (sa.chamber_analysis && typeof sa.chamber_analysis === 'object') return 'hybrid';
        if (sa.chamber_structure && typeof sa.chamber_structure === 'object') return 'liquid';
        if (sa.case_analysis && typeof sa.case_analysis === 'object') return 'solid';
        return null;
    }

    /* ÖH D37 A2-1 / OH-DK-09 — CİDAR KALINLIĞI KÖPRÜNÜN OKUDUĞU ALANDAN.
       ÖLÇÜLDÜ (DK termal B2; A2 termal a1 once/t7_ozet.json): bu gövde
       kalınlık göndermiyordu → uç 5 mm varsayıyor, profilin T_wall_eq
       sütunu 5 mm cidara aitken FEA meshi 23,08 mm çözüyordu. Aynı üç yol
       (hrma/fea/bridge.py _extract_wall_thickness_m; hepsi mm) okunur ve
       METREYE çevrilir; alan yoksa GÖNDERİLMEZ (uç varsayılanını
       inputs_assumed ile ilan eder — uydurma yok). */
    function bridgeWallThicknessM(m) {
        const sa = (m && m.structural_analysis) || {};
        const adaylar = [
            (sa.chamber_analysis || {}).wall_thickness_used_mm,
            (sa.chamber_structure || {}).wall_thickness,
            (sa.case_analysis || {}).wall_thickness_mm,
        ];
        for (let i = 0; i < adaylar.length; i += 1) {
            if (isNum(adaylar[i]) && adaylar[i] > 0) return adaylar[i] / 1000.0;
        }
        return undefined;
    }

    // Ölçülmüş zincirin 1. adımının gövdesi. Dönüş: { body, missing }.
    // missing doluysa istek atılmaz; eksikler ADIYLA panelde basılır.
    function buildWallProfileBody(results) {
        const m = motorDictLocal(results) || {};
        const body = {};
        const missing = [];
        /* F-03: katı ve sıvı sözlükleri düz hibrit alanlarını taşımaz (mm
           uzunluklar, total_mass_flow, motor_geometry SI bloğu). Gövde
           panelde kurulmaz: motor sözlüğü AYNEN gönderilir, uç tek kurucu
           (heat_transfer_analysis.wall_profile_inputs_from_motor) ile kurar
           ve bulamadığı çekirdek alanı 422 + adıyla reddeder. Hibrit yol
           BİT-AYNI kalır (aşağıdaki düz gövde). */
        const layout = engineLayoutLocal(m);
        if (layout === 'solid' || layout === 'liquid') {
            return { body: { motor_results: m }, missing: [] };
        }
        CORE_FLAT_FIELDS.forEach(function (k) {
            if (isNum(m[k])) body[k] = m[k];
            else missing.push(k);
        });
        CORE_LENGTH_FIELDS.forEach(function (k) {
            const v = readLen(results, k);
            if (isNum(v)) body[k] = v;
            else missing.push(k);
        });
        // Boğaz çapı ve genleşme oranı: varsa AYNEN geçirilir (metre
        // dönüşümü readLen'den); yoksa uç aynı motor verisinden kendisi
        // türetir — bu türetme uydurma değil, aynı fiziğin devamıdır.
        const dt = readLen(results, 'throat_diameter');
        if (isNum(dt)) body.throat_diameter = dt;
        if (isNum(m.expansion_ratio)) body.expansion_ratio = m.expansion_ratio;
        /* ÖH D37 A2-1 / F-03 Bartz eşleştirme hükmü — MOTORUN KENDİ GAZI.
           ÖLÇÜLDÜ (A2 termal a1 sonra/): bu gövde gamma / molecular_weight /
           c_star GÖNDERMİYORDU; uç modül varsayılanına (MW 24 g/mol, repo
           gamma) düşüyor ve örnek hibritte boğaz h_g 6770 W/m²K çıkıyordu —
           motorun kendi γ/MW/c*'ı ile 6370 W/m²K (−%5,9; motorun kendi
           gas_side_analysis'i de 1881,96 K ile bunu doğruluyor). Bartz'ı
           motor tipi değil termodinamik durum belirler; motor bu üçünü
           yayımlıyorsa AYNEN geçer, yayımlamıyorsa alan konmaz. Yayımlanan
           FEA sayısını değiştirir → ÖNEMLİ (Sunum 2 tablosu). */
        ['gamma', 'molecular_weight', 'c_star'].forEach(function (k) {
            if (isNum(m[k]) && m[k] > 0) body[k] = m[k];
        });
        // OH-DK-09: köprünün mesh'i kurduğu kalınlık, metre.
        const tw = bridgeWallThicknessM(m);
        if (isNum(tw)) body.wall_thickness = tw;
        // Parti 25 (bell/parabolik dirilişi): motorun YAYIMLADIĞI lüle
        // konturu varsa AYNEN geçirilir. Ölçüldü: kontursuz gövdede bell
        // motorda profil ekseni FEA köprüsünün konturundan 38-97% sapıyor
        // ve termal uç dürüstçe reddediyordu; kontur geçince sapma 0,000
        // (tests/test_wall_profile_ekseni.py). Uç, konturu yalnız
        // {points:[...]} şekliyle kabul eder; panel şekli değiştirmez.
        const nc = m.nozzle_contour;
        if (nc && typeof nc === 'object' && Array.isArray(nc.points)
                && nc.points.length >= 2) {
            body.nozzle_contour = nc;
        }
        // ÖH defter P7B3-30 — ZİNCİRİN İKİ UCU AYNI MALZEMEYİ KULLANIR.
        // Bu gövde ``material`` GÖNDERMİYORDU, yani profil daima jenerik
        // 'steel' ile hesaplanıyordu; 2. adım (/api/fea/thermal) ise mesh'i
        // motorun KENDİ malzemesiyle (ör. steel_4130) çözüyordu. Gaz tarafı
        // h(z) bir malzemenin izin sıcaklığından (referans soğutulmuş cidar
        // Tw_ref) çıkarken cidar iletimi başka malzemeninkinden geliyordu.
        // ÖLÇÜLDÜ (docs/scofield/raw/OH/D19/app-api/a1/once_a1.json): aynı
        // motorda q_MW tepe 6,122 (graphite) ⟷ 25,251 (steel_4130) MW/m²,
        // oran 4,125. Panel malzemeyi UYDURMAZ: motorun kendi yapısal
        // bloğundan okur (üç yerleşimin üçü de köprünün okuduğu alandır,
        // hrma/fea/bridge.py::_extract_material) ve bulamazsa alanı hiç
        // koymaz — o zaman uç varsayılanını ADIYLA ilan eder. Yanlış
        // okursa da sessiz kalmaz: /api/fea/thermal profilin malzemesi
        // mesh malzemesinden farklıysa adlı 422 verir (fail-closed).
        const sa = m.structural_analysis;
        if (sa && typeof sa === 'object') {
            const adaylar = [
                (sa.design_parameters || {}).material,
                (sa.chamber_structure || {}).material_key,
                (sa.case_analysis || {}).case_material,
            ];
            for (let i = 0; i < adaylar.length; i += 1) {
                if (typeof adaylar[i] === 'string' && adaylar[i].trim()) {
                    body.material = adaylar[i].trim();
                    break;
                }
            }
        }
        return { body: body, missing: missing };
    }
    /* Bekçiler için künye: gövde hangi yoldan kuruldu (düz alanlar ⟷
       motor_results) ve motor düzeni ne. Ürün akışı bunu okumaz. */
    function buildWallProfileBodyMeta(results) {
        const r = buildWallProfileBody(results);
        r.layout = engineLayoutLocal(motorDictLocal(results) || {});
        r.via = (r.body && r.body.motor_results) ? 'motor_results' : 'flat';
        return r;
    }
    // <<< THERMAL_FEA_PAYLOAD_END
    // ==================================================================

    // ==================================================================
    // >>> THERMAL_FEA_VIEWMODEL_START
    // Saf görünüm modeli — DOM/Plotly YOK; node bekçi testleri bu bölümü
    // gerçek uç yanıtlarıyla koşturur. Alan değerleri sunucudan geldiği
    // gibi taşınır; sıcaklık için HİÇBİR ölçekleme yoktur.
    // ==================================================================

    // node_index_grid: [i][j] — i eksenel istasyon, j cidar katmanı
    // (0 iç/gaz yüzeyi). Carpet izleri 2B diziyi [b][a] sırasıyla ister.
    function gridDims(mesh) {
        const g = mesh && mesh.node_index_grid;
        if (!Array.isArray(g) || !g.length || !Array.isArray(g[0])) return null;
        return { ni: g.length, nj: g[0].length };
    }

    // Düğüm koordinatlarından carpet ızgarası: x[j][i], y[j][i] (metre).
    function buildCarpetGrid(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        if (!Array.isArray(nodes)) return null;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        for (let j = 0; j < dims.nj; j++) {
            const rx = [], ry = [];
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                if (!Array.isArray(n)) return null;
                rx.push(n[0]);
                ry.push(n[1]);
            }
            x.push(rx);
            y.push(ry);
        }
        const a = [], b = [];
        for (let i = 0; i < dims.ni; i++) a.push(i);
        for (let j = 0; j < dims.nj; j++) b.push(j);
        return { a: a, b: b, x: x, y: y, ni: dims.ni, nj: dims.nj };
    }

    // Düğüm alanı (N,) → carpet düzeni [j][i]. Sıcaklık kelvin gelir ve
    // kelvin çizilir: ölçek çarpanı YOKTUR (bekçi bunu kilitler).
    function fieldToGrid(mesh, values) {
        const dims = gridDims(mesh);
        if (!dims || !Array.isArray(values)) return null;
        const g = mesh.node_index_grid;
        const out = [];
        for (let j = 0; j < dims.nj; j++) {
            const row = [];
            for (let i = 0; i < dims.ni; i++) {
                const v = values[g[i][j]];
                row.push(isNum(v) ? v : null);
            }
            out.push(row);
        }
        return out;
    }

    // Tel-kafes: yapısal ızgaranın bütün i ve j çizgileri; eleman
    // kenarlarının kendisidir (fea_panel.js ile aynı kurgu).
    function buildWireframe(mesh) {
        const dims = gridDims(mesh);
        if (!dims) return null;
        const nodes = mesh.nodes;
        const g = mesh.node_index_grid;
        const x = [], y = [];
        let pts = 0;
        for (let i = 0; i < dims.ni; i++) {
            for (let j = 0; j < dims.nj; j++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        for (let j = 0; j < dims.nj; j++) {
            for (let i = 0; i < dims.ni; i++) {
                const n = nodes[g[i][j]];
                x.push(n[0]); y.push(n[1]); pts++;
            }
            x.push(null); y.push(null);
        }
        return { x: x, y: y, node_visits: pts, n_nodes: dims.ni * dims.nj };
    }

    // Sunucu yanıtı (fea bloğu) → çizilebilir görünüm modeli.
    function buildViewModel(fea, errorText) {
        if (errorText) return { mode: 'error', error: String(errorText) };
        if (!fea || typeof fea !== 'object') return { mode: 'idle' };
        if (fea.status !== 'ok') {
            return {
                mode: 'not_modelled',
                status: fea.status || null,
                missing: Array.isArray(fea.missing) ? fea.missing : [],
                reason: (typeof fea.reason === 'string') ? fea.reason : '',
                warning: fea.warning || null,
                engine_layout: fea.engine_layout || null,
            };
        }
        const mesh = fea.mesh || {};
        const grid = buildCarpetGrid(mesh);
        if (!grid) return { mode: 'invalid', reason: 'mesh grid missing' };
        const fields = fea.fields || {};
        const scalars = fea.scalars || {};
        const hist = fea.history || {};
        const meta = fea.meta || {};

        // İç yüzey eğrisi: iki dizi AYNI uzunluktaysa çizilir; değilse
        // kısmî eğri uydurulmaz.
        let innerCurve = null;
        if (Array.isArray(fields.inner_surface_z_m)
                && Array.isArray(fields.inner_surface_T_final_K)
                && fields.inner_surface_z_m.length
                && fields.inner_surface_z_m.length
                    === fields.inner_surface_T_final_K.length) {
            innerCurve = {
                z_m: fields.inner_surface_z_m,
                T_K: fields.inner_surface_T_final_K,
            };
        }

        // Tepe cidar sıcaklığı geçmişi: aynı uzunluk şartı aynı sebeple.
        let historyCurve = null;
        if (Array.isArray(hist.times_s)
                && Array.isArray(hist.peak_wall_T_history_K)
                && hist.times_s.length
                && hist.times_s.length === hist.peak_wall_T_history_K.length) {
            historyCurve = {
                times_s: hist.times_s,
                peak_T_K: hist.peak_wall_T_history_K,
            };
        }

        const sinir = (fea.material_limits && typeof fea.material_limits === 'object')
            ? fea.material_limits : null;
        const bc = (meta.sinir_kosullari_koprusu
                    && typeof meta.sinir_kosullari_koprusu === 'object')
            ? meta.sinir_kosullari_koprusu : {};

        const vm = {
            mode: 'ok',
            engine_layout: fea.engine_layout || null,
            grid: grid,
            temperature_K: fieldToGrid(mesh, fields.temperature_final_K),
            wireframe: buildWireframe(mesh),
            inner: innerCurve,
            history: historyCurve,
            mesh_info: {
                n_nodes: mesh.n_nodes, n_elems: mesh.n_elems,
                n_axial: mesh.n_axial, n_radial: mesh.n_radial,
                grid_ni: grid.ni, grid_nj: grid.nj,
                units: mesh.coordinate_units || null,
                /* ÖH D26 · P11B3-21 — ağ üreticisinin geometri beyanı.
                   ÖLÇÜLDÜ (a3/once.json): term_vm_meta_alinan = 0 —
                   yapısal kardeş bloğu görünüm modeline ALIYOR ama
                   basmıyordu; termal panel HİÇ almıyordu bile. */
                mesh_meta: mesh.meta || null,
            },
            scalars: {
                peak_wall_T_K: isNum(scalars.peak_wall_T_K)
                    ? scalars.peak_wall_T_K : null,
                peak_time_s: isNum(scalars.peak_time_s)
                    ? scalars.peak_time_s : null,
                inner_surface_peak_T_K: isNum(scalars.inner_surface_peak_T_K)
                    ? scalars.inner_surface_peak_T_K : null,
                inner_surface_peak_z_m: isNum(scalars.inner_surface_peak_z_m)
                    ? scalars.inner_surface_peak_z_m : null,
                burn_time_s: isNum(scalars.burn_time_s)
                    ? scalars.burn_time_s : null,
                ambient_temperature_K: isNum(scalars.ambient_temperature_K)
                    ? scalars.ambient_temperature_K : null,
                material_key: scalars.material_key || null,
                wall_thickness_m: isNum(scalars.wall_thickness_m)
                    ? scalars.wall_thickness_m : null,
            },
            material_limits: sinir,
            energy: (fea.energy && typeof fea.energy === 'object')
                ? fea.energy : null,
            time_step: (fea.time_step && typeof fea.time_step === 'object')
                ? fea.time_step : null,
            warnings: Array.isArray(fea.warnings) ? fea.warnings : [],
            limits: fea.limits || null,
            not_modelled: Array.isArray(meta.not_modelled)
                ? meta.not_modelled : [],
            bc: {
                outer: (typeof bc.dis_yuzey === 'string') ? bc.dis_yuzey : null,
                inner: (typeof bc.ic_yuzey === 'string') ? bc.ic_yuzey : null,
                initial: (typeof bc.baslangic_kosulu === 'string')
                    ? bc.baslangic_kosulu : null,
                window: (typeof bc.zaman_penceresi === 'string')
                    ? bc.zaman_penceresi : null,
            },
            basis: {
                solver: meta._basis || null,
                fields: fields._basis || null,
                history: hist._basis || null,
                limits_note: (fea.limits && fea.limits._basis) || null,
                material: (sinir && sinir._basis) || null,
                mesh_policy: (meta.mesh_politikasi
                              && meta.mesh_politikasi.beyan) || null,
            },
            /* ÖH D26 / P11B3-15 — MESH YAKINSAMASI EKRANIN ÜST KATINA
               ÇIKAR. Çözücü bunu ZATEN beyan ediyordu
               (`meta.mesh_politikasi.beyan`: "termal yolda MESH
               yakınsaması otomatik DENETLENMEZ ..."), panel ise o cümleyi
               YALNIZ katlanmış `<details id="fea_t_basis">` künye
               bloğuna koyuyordu (ölçüldü, a2/once.json:
               mesh_politikasi_kunyede = 2, mesh_politikasi_rozette = 0).
               Rozet şeridinde ise YEŞİL "TIME STEP CONVERGED" duruyordu.
               Kullanıcının gördüğü: yeşil "yakınsadı". Gerçek: yalnız
               ZAMAN ekseni yakınsadı, UZAMSAL ayrıklık hiç sınanmadı.
               Beyan katlı yerde kalırken yeşil rozetin üstte durması,
               beyanın kendisini örtüyordu.

               `mesh_declared`: çözücü mesh politikasını beyan etti mi?
               Etmediyse rozet "BEYAN EDİLMEDİ" der (fail-closed): panel
               "yakınsadı" ya da "yakınsamadı" diye HÜKÜM UYDURMAZ. */
            mesh_declared: !!(meta.mesh_politikasi
                              && typeof meta.mesh_politikasi === 'object'),
            /* ÖH D37 A2-1 / F-02 — UZAMSAL MERDİVEN HÜKMÜ. Kaynak önceliği:
               (1) fea.spatial_convergence (İngilizce sözleşme, app yaması
               sonrası); (2) çözücünün kendi bloğu meta.cozucu.uzamsal_
               yakinsama (bugün de yanıtta). İkisi de yoksa null → rozet
               "BEYAN EDİLMEDİ" (fail-closed; hüküm UYDURULMAZ). */
            spatial: spatialFromPayload(fea, meta),
            /* F-01 (CW-B3) — iki termal yolun uzlaştırma bloğu (FEA yarısı). */
            reconciliation: (fea.thermal_paths_reconciliation
                             && typeof fea.thermal_paths_reconciliation === 'object')
                ? fea.thermal_paths_reconciliation : null,
            /* B2-CP — köprünün okuduğu motor yolları (sayı değil, künye). */
            consumed_paths: Array.isArray(fea.consumed_paths)
                ? fea.consumed_paths : null,
        };
        // Izgara SUNUCUNUN beyan ettiği düğüm sayısını vermiyorsa alan
        // çizilmez (kısmî harita, haritasızlıktan kötüdür).
        vm.grid_consistent = (grid.ni * grid.nj === mesh.n_nodes);
        return vm;
    }
    /* ÖH D37 A2-1 denetçi Ş4 — çözücü bloğunun Türkçe neden kodu →
       sözleşmenin İngilizce reason_code'u. hrma/fea/bridge.py
       SPATIAL_REASON_CODES ile BİREBİR (bekçi a2
       test_neden_kodu_tablosu_kopruyle_ayni iki tabloyu karşılaştırır). */
    const SOLVER_REASON_CODES = {
        sinif: 'non_monotonic',
        p_dusuk: 'observed_order_below_min',
        gci_buyuk: 'gci_above_tolerance',
        dejenere: 'degenerate_zero_change',
        az_seviye: 'fewer_than_three_levels',
        refiner_yok: 'no_mesh_refiner',
    };
    /* F-02 — uzamsal hükmü tek biçime indirir: {verdict, reason_code,
       gci_status, p, p_min, gci_pct, tol_pct, levels[{n_axial,n_radial,
       peak_K,published}], published_level, extrapolated_K,
       richardson_reliable, declaration}. Sayı türetmez; iki kaynaktan
       hangisi varsa onun alanlarını taşır. Sunucunun Türkçe ``reason``
       metni BİLEREK taşınmaz (Ş4: ekran onu basmaz, kodu kendi dilinde
       kurar). */
    function spatialFromPayload(fea, meta) {
        const sc = fea && fea.spatial_convergence;
        if (sc && typeof sc === 'object') {
            return {
                source: 'fea.spatial_convergence',
                verdict: sc.verdict || null,
                reason_code: (typeof sc.reason_code === 'string')
                    ? sc.reason_code : null,
                gci_status: (typeof sc.gci_status === 'string')
                    ? sc.gci_status : null,
                p: isNum(sc.observed_order_p) ? sc.observed_order_p : null,
                p_min: isNum(sc.p_min_asymptotic) ? sc.p_min_asymptotic : null,
                gci_pct: isNum(sc.gci_fine_pct) ? sc.gci_fine_pct : null,
                tol_pct: isNum(sc.gci_tolerance_pct) ? sc.gci_tolerance_pct : null,
                levels: Array.isArray(sc.levels) ? sc.levels.map(function (l) {
                    return { n_axial: l.n_axial, n_radial: l.n_radial,
                             peak_K: l.peak_wall_T_K, published: !!l.published };
                }) : [],
                published_level: sc.published_level || null,
                extrapolated_K: isNum(sc.richardson_extrapolated_peak_K)
                    ? sc.richardson_extrapolated_peak_K : null,
                richardson_reliable: (typeof sc.richardson_reliable === 'boolean')
                    ? sc.richardson_reliable : null,
                declaration: sc.declaration || null,
            };
        }
        const u = meta && meta.cozucu && meta.cozucu.uzamsal_yakinsama;
        if (u && typeof u === 'object') {
            return {
                source: 'meta.cozucu.uzamsal_yakinsama',
                /* Fail-closed: hüküm alanı (hukum) yoksa bu F-02 ÖNCESİ tek
                   inceltmeli bloktur — GCI'sız "converged" hükmü 'legacy'
                   diye ayrı okunur; panel onu üç seviyeli hüküm gibi
                   BASMAZ (ölçüldü: ÖNCE yükü "p = —, GCI —%" basıyordu). */
                verdict: u.hukum || (u.denetlendi === false ? 'not_evaluated'
                                     : 'legacy_single_refinement'),
                rel_change: isNum(u.rel_change) ? u.rel_change : null,
                reason_code: (Object.prototype.hasOwnProperty.call(
                    SOLVER_REASON_CODES, u.neden_kodu))
                    ? SOLVER_REASON_CODES[u.neden_kodu] : null,
                gci_status: (u.gci && typeof u.gci.status === 'string')
                    ? u.gci.status : null,
                p: isNum(u.p) ? u.p : null,
                p_min: isNum(u.p_min_asimptotik) ? u.p_min_asimptotik : null,
                gci_pct: isNum(u.GCI_fine21) ? 100.0 * u.GCI_fine21 : null,
                tol_pct: isNum(u.tol) ? 100.0 * u.tol : null,
                levels: Array.isArray(u.seviyeler) ? u.seviyeler.map(function (l) {
                    return { n_axial: l.n_axial, n_radial: l.n_radial,
                             peak_K: l.peak_wall_T, published: !!l.yayimlandi };
                }) : [],
                published_level: u.yayimlanan_seviye || null,
                extrapolated_K: isNum(u.peak_wall_T_ext_K) ? u.peak_wall_T_ext_K : null,
                richardson_reliable: (typeof u.richardson_guvenilir === 'boolean')
                    ? u.richardson_guvenilir : null,
                declaration: u.beyan || null,
            };
        }
        return null;
    }
    // <<< THERMAL_FEA_VIEWMODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil (fea_panel.js kalıbı)
    // ------------------------------------------------------------------
    const MISSING_COLOR = '#8a93a0';
    const ALLOW_COLOR = '#ff8c33';      // izin sınırı çizgisi (turuncu)
    const MELT_COLOR = '#ff5d73';       // erime noktası çizgisi (kırmızı)
    const MESH_COLOR = 'rgba(180,200,215,0.55)';
    // Bu Plotly derlemesinde (1.58.5) GERÇEKTEN bulunan bir skala:
    // 'Hot' — sıcaklık alanı için siyah→kırmızı→sarı.
    const T_COLORSCALE = 'Hot';

    function badge(text, kind) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
            dim: MISSING_COLOR,
        };
        const c = colors[kind] || colors.info;
        return `<span data-badge="${kind}" style="border:1px solid ${c}; color:${c};
            border-radius:6px; padding:4px 10px; font-family:var(--hd-mono);
            font-size:0.75rem;">${text}</span>`;
    }

    function chipHtml(label, reason) {
        let html = `<span data-chip="not-modelled" style="border:1px solid ${MISSING_COLOR};
            color:${MISSING_COLOR}; border-radius:6px; padding:4px 10px;
            font-family:var(--hd-mono); font-size:0.75rem;">${esc(label)}</span>`;
        if (reason) {
            html += `<p style="font-family:var(--hd-mono); font-size:0.78rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0 0;
                white-space:pre-wrap;">${esc(SRV(reason))}</p>`;
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Panel iskeleti
    // ------------------------------------------------------------------
    function panelHtml() {
        return `
        <div class="panel" id="thermalFeaPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="feaT.title">${T('feaT.title',
                'Thermal FEA — Transient Wall Temperature Field')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="feaT.intro">${T('feaT.intro',
                    'A transient heat-conduction finite element run on the nozzle wall '
                    + 'of THIS result: the gas-side film coefficient profile h(z) is '
                    + 'computed first (Bartz, wall-profile endpoint) and fed to the '
                    + 'solver as a boundary condition — nothing is fabricated from a '
                    + 'single throat number. You see the temperature field on the '
                    + 'mesh at the end of the burn, the gas-side surface temperature '
                    + 'along the wall and the peak wall temperature history. If an '
                    + 'input is missing, nothing is drawn and the missing item is '
                    + 'named.')}</span>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:10px 0;">
                <button id="fea_t_run" class="btn" type="button"
                    data-i18n="feaT.run">${T('feaT.run', 'Run thermal analysis')}</button>
                <span id="fea_t_busy" style="display:none; font-family:var(--hd-mono);
                    font-size:0.78rem; color:var(--hd-cyan, #00e5ff);"></span>
                <button id="fea_t_cancel" class="btn" type="button"
                    style="display:none; padding:2px 10px; font-size:0.75rem;"
                    >${esc(T('feaT.cancel', 'Cancel run'))}</button>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <span data-i18n="feaT.ambientLabel">${T('feaT.ambientLabel',
                        'Initial / ambient temperature [K]')}</span>${yardimHtml('panel.feaT.help.ambient')}
                    <input type="number" id="fea_t_ambient"
                        value="${AMBIENT_PANEL_DEFAULT_K}" step="0.05"
                        style="width:90px;">
                </label>
                <label style="font-family:var(--hd-mono); font-size:0.75rem;
                    color:var(--hd-ink-dim, #7d97a5); display:flex; gap:6px; align-items:center;">
                    <input type="checkbox" id="fea_t_show_mesh" checked>
                    <span data-i18n="feaT.showMesh">${T('feaT.showMesh',
                        'Show mesh wireframe')}</span>${yardimHtml('panel.feaT.help.showMesh')}
                </label>
            </div>
            <div id="fea_t_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="fea_t_chip" style="margin:8px 0;"></div>
            <div id="fea_t_warnings" style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-orange, #ff8c33); margin:6px 0;"></div>
            <div id="fea_t_plot_field" class="plot-container" style="min-height:340px; display:none;"></div>
            <div id="fea_t_plot_inner" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_t_plot_hist" class="plot-container" style="min-height:300px; display:none;"></div>
            <div id="fea_t_bc_note" style="font-family:var(--hd-mono); font-size:0.72rem;
                color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>
            <details id="fea_t_basis" style="display:none; margin-top:8px;">
                <summary style="cursor:pointer; font-family:var(--hd-mono);
                    font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);"
                    data-i18n="feaT.basisTitle">${T('feaT.basisTitle',
                    'Method / basis and what is NOT modelled (as declared by the solver)')}</summary>
                <div id="fea_t_basis_text" style="font-family:var(--hd-mono);
                    font-size:0.72rem; color:var(--hd-ink-dim, #7d97a5);
                    margin:6px 0 0; white-space:pre-wrap;"></div>
            </details>
        </div>`;
    }

    // ------------------------------------------------------------------
    // Çizim
    // ------------------------------------------------------------------
    function wireTrace(vm) {
        const w = vm.wireframe;
        return {
            x: w.x, y: w.y, mode: 'lines', type: 'scatter',
            line: { color: MESH_COLOR, width: 1 },
            name: TF('feaT.meshTrace', { n: vm.mesh_info.n_elems },
                     'Mesh ({n} elements)'),
            hoverinfo: 'skip',
        };
    }

    // Malzeme sınırı referans çizgileri (değerler SUNUCUDAN; panel eşik
    // uydurmaz). thermal_panel.js limitLine kalıbı.
    function limitShapes(vm) {
        const ml = vm.material_limits || {};
        const shapes = [], annotations = [];
        function line(v, label, color) {
            if (!isNum(v)) return;
            shapes.push({
                type: 'line', xref: 'paper', x0: 0, x1: 1, y0: v, y1: v,
                line: { color: color, width: 1.5, dash: 'dash' },
            });
            annotations.push({
                xref: 'paper', x: 1, y: v, xanchor: 'right', yanchor: 'bottom',
                text: label + ' — ' + Math.round(v) + ' K', showarrow: false,
                font: { size: 10, color: color },
            });
        }
        line(ml.allowable_temperature_K,
             T('feaT.allowLine', 'Allowable'), ALLOW_COLOR);
        line(ml.melting_point_K,
             T('feaT.meltLine', 'Melting point'), MELT_COLOR);
        return { shapes: shapes, annotations: annotations };
    }

    // T(z, r) konturu: carpet + contourcarpet MESH üstünde (yapısal
    // panelin kontur+tel-kafes yaklaşımı). Değerler kelvin, AYNEN.
    function fieldFigure(vm) {
        const g = vm.grid;
        const cbar = T('feaT.cbarField', 'T [K]');
        const traces = [{
            type: 'carpet', carpet: 'feaTCarpet',
            a: g.a, b: g.b, x: g.x, y: g.y,
            aaxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none', showticksuffix: 'none',
                     smoothing: 0, title: '' },
        }, {
            type: 'contourcarpet', carpet: 'feaTCarpet',
            a: g.a, b: g.b, z: vm.temperature_K,
            contours: { coloring: 'fill', showlines: false },
            colorscale: T_COLORSCALE,
            colorbar: { title: cbar, titleside: 'right' },
            name: cbar,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: T('feaT.chartField',
                         'Wall temperature at end of burn — T(z, r) [K]'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // Carpet yedeği (eski Plotly): düğüm nokta haritası — fea_panel deseni.
    function fieldFallbackFigure(vm) {
        const g = vm.grid;
        const cbar = T('feaT.cbarField', 'T [K]');
        const x = [], y = [], c = [];
        for (let j = 0; j < g.nj; j++) {
            for (let i = 0; i < g.ni; i++) {
                x.push(g.x[j][i]); y.push(g.y[j][i]);
                c.push(vm.temperature_K[j][i]);
            }
        }
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: { color: c, colorscale: T_COLORSCALE, size: 6,
                      colorbar: { title: cbar, titleside: 'right' } },
            name: cbar,
        }];
        if (showMesh && vm.wireframe) traces.push(wireTrace(vm));
        return {
            traces: traces,
            layout: {
                title: T('feaT.chartField',
                         'Wall temperature at end of burn — T(z, r) [K]'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisR', 'Radius r [m]') },
                height: 340,
                showlegend: false,
            },
        };
    }

    // İç (gaz tarafı) yüzey sıcaklığı T(z) — çözücü alanının j = 0
    // düğümleri, sunucudan okunduğu gibi.
    function innerFigure(vm) {
        const lim = limitShapes(vm);
        return {
            traces: [{
                x: vm.inner.z_m, y: vm.inner.T_K,
                mode: 'lines+markers', type: 'scatter',
                marker: { size: 6 }, line: { width: 2 },
                name: T('feaT.innerTrace', 'Inner (gas-side) surface T [K]'),
            }],
            layout: {
                title: T('feaT.chartInner',
                         'Inner (gas-side) surface temperature at end of burn'),
                xaxis: { title: T('feaT.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('feaT.axisT', 'Temperature [K]') },
                shapes: lim.shapes,
                annotations: lim.annotations,
                height: 300,
                showlegend: false,
            },
        };
    }

    // Tepe cidar sıcaklığı geçmişi T(t) — zaman adımı yakınsamasının
    // ölçüldüğü büyüklüğün kendisi (history._basis).
    function historyFigure(vm) {
        const lim = limitShapes(vm);
        return {
            traces: [{
                x: vm.history.times_s, y: vm.history.peak_T_K,
                mode: 'lines', type: 'scatter',
                line: { width: 2 },
                name: T('feaT.histTrace', 'Peak wall temperature [K]'),
            }],
            layout: {
                title: T('feaT.chartHistory',
                         'Peak wall temperature history over the burn'),
                xaxis: { title: T('feaT.axisTime', 'Time [s]') },
                yaxis: { title: T('feaT.axisT', 'Temperature [K]') },
                shapes: lim.shapes,
                annotations: lim.annotations,
                height: 300,
                showlegend: false,
            },
        };
    }

    function drawFigure(el, figure) {
        Plotly.react(el, figure.traces, figure.layout,
                     { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Basım
    // ------------------------------------------------------------------
    /* ÖH D37 A2-1 denetçi Ş4 — NEDEN, EKRANIN DİLİNDE. Eskiden rozet
       sunucunun Türkçe neden metnini (iç kod 'p_dusuk' dâhil) AYNEN
       basıyordu; EN ekranda şu görünüyordu (ölçüldü, sonra/kare/
       termal_panel_t7_1440.png): "MESH NOT CONVERGED — p_dusuk: gözlenen
       mertebe 0.450 < 1 ...". Artık yalnız makine kodu okunur ve metin
       EN/TR i18n anahtarından kurulur; sayılar TF'ye saf ondalık metin olarak
       girer (TR ekranda virgül). Kod yoksa ya da tanınmıyorsa metin
       UYDURULMAZ: "neden makine biçiminde beyan edilmedi" (fail-closed). */
    function spatialReasonText(sp) {
        const code = sp && sp.reason_code;
        if (code === 'observed_order_below_min') {
            return TF('feaT.meshReasonOrderLow',
                { p: fmt(sp.p, 3), pmin: fmt(sp.p_min, 1) },
                'observed order p = {p} < {pmin} (outside the asymptotic '
                + 'range; the Richardson extrapolation is unreliable)');
        }
        if (code === 'gci_above_tolerance') {
            return TF('feaT.meshReasonGciLarge',
                { gci: fmt(sp.gci_pct, 3), tol: fmt(sp.tol_pct, 2) },
                'GCI {gci}% above the {tol}% tolerance');
        }
        if (code === 'non_monotonic') {
            if (sp.gci_status === 'monotonic_divergent') {
                return T('feaT.meshReasonDivergent',
                    'monotonic divergence — the peak keeps moving away with '
                    + 'refinement; no GCI');
            }
            if (sp.gci_status === 'oscillatory') {
                return T('feaT.meshReasonOscillatory',
                    'oscillatory ladder; no GCI');
            }
            return T('feaT.meshReasonNonMonotonic',
                'no monotonic convergence; no GCI');
        }
        return T('feaT.meshReasonUnknown',
            'reason not declared in machine form — see the declaration');
    }

    /* ÖH D37 A2-1 / F-02 — MERDİVEN ROZETİ (renderBadges'in yardımcısı).
       Rozet çözücünün ÜÇ SEVİYELİ merdiven + GCI hükmünü söyler (converged /
       not_converged + neden / degenerate / not_evaluated / F-02 öncesi tek
       inceltme); eski sabit "DENETLENMEDİ" metni BAYATTI (çözücü P8B1-10'dan
       beri ölçüyordu, köprü inkâr ediyordu). Hüküm ve sayılar sunucudan;
       hüküm yoksa null döner ve renderBadges fail-closed "BEYAN EDİLMEDİ"
       rozetini basar. Ayrı işlev: P11B3-15/16 kaynak bekçileri rozet
       şeridinin ilk 4000 karakterinde mesh + ambient rozetlerini arar. */
    function spatialBadge(sp) {
        if (!sp || !sp.verdict) return null;
        const lvl = sp.published_level
            ? (sp.published_level.n_axial + '×' + sp.published_level.n_radial) : '?';
        if (sp.verdict === 'converged') {
            return badge(TF('feaT.badgeMeshConverged',
                { p: fmt(sp.p, 2), gci: fmt(sp.gci_pct, 3), lvl: lvl },
                'MESH CONVERGED (3-level ladder, GCI) — p = {p}, GCI {gci}% · '
                + 'published level {lvl}'), 'ok');
        }
        if (sp.verdict === 'not_converged') {
            return badge(TF('feaT.badgeMeshNotConvergedGci',
                { reason: esc(spatialReasonText(sp)), lvl: lvl },
                'MESH NOT CONVERGED — {reason} · published level {lvl}; the '
                + 'peak temperature is still mesh-sensitive'), 'warn');
        }
        if (sp.verdict === 'legacy_single_refinement') {
            return badge(TF('feaT.badgeMeshLegacy',
                { rel: isNum(sp.rel_change) ? fmt(100.0 * sp.rel_change, 3) : '—' },
                'MESH: single 2× refinement only (pre-F-02 solver) — peak '
                + 'change {rel}%, no GCI; the residual error is NOT bounded'),
                'warn');
        }
        if (sp.verdict === 'degenerate') {
            return badge(T('feaT.badgeMeshDegenerate',
                'MESH LADDER DEGENERATE — the peak did not change between '
                + 'levels (pinned boundary?); no GCI; see the declaration'),
                'warn');
        }
        return badge(T('feaT.badgeMeshNotEvaluated',
            'MESH CONVERGENCE NOT EVALUATED — fewer than three ladder '
            + 'levels were solved; see the declaration below'), 'warn');
    }

    /* ÖH D37 A2-1 termal 7. tur — olumlu hüküm geri çekme nedenleri
       (sunucunun makine kodu → bu ekranın dili). Tanınmayan kod AYNEN
       basılır (sessiz düşmez). */
    function withheldReasonText(ml) {
        const kodlar = (ml && Array.isArray(ml.verdict_withheld_reasons))
            ? ml.verdict_withheld_reasons : [];
        const metin = kodlar.map(function (k) {
            if (k === 'numerical_convergence_not_achieved') {
                return T('feaT.withheldNumerical',
                    'numerical convergence not achieved');
            }
            if (k === 'gas_properties_assumed') {
                const alanlar = (Array.isArray(ml.inputs_assumed)
                    ? ml.inputs_assumed : []).map(function (a) {
                        return a && a.field;
                    }).filter(Boolean).join(', ');
                return TF('feaT.withheldGas', { fields: alanlar || '—' },
                    'gas properties assumed (module default: {fields})');
            }
            // 8. tur (yeniden denetim-7 Ş1): profil gaz künyesi taşımıyor
            // (ya da künye okunamıyor) — gaz "varsayıldı" değil, BİLİNMİYOR.
            if (k === 'gas_properties_not_declared') {
                return T('feaT.withheldGasUndeclared',
                    'the h(z) profile does not declare its gas properties');
            }
            return String(k);
        });
        return metin.join('; ');
    }

    /* ÖH D37 A2-1 termal 7. tur — karar §28-24 §1 c / §2 b: yakınsamamış
       alan ya da jenerik gazlı profil OLUMLU hüküm üretmez. Neden kodları
       SUNUCUDAN (verdict_withheld_reasons); panel hüküm uydurmaz. Ayrı
       işlev: P11B3-15/16 kaynak bekçileri renderBadges'in ilk 4000
       karakterinde mesh + ambient rozetlerini arar (spatialBadge ile aynı
       gerekçe). */
    function withheldBadge(ml) {
        return badge(TF('feaT.badgeVerdictWithheld',
            { reasons: esc(withheldReasonText(ml)),
              allow: fmt(ml.allowable_temperature_K, 0) },
            'NO SAFETY VERDICT — {reasons}; the peak is shown against '
            + 'the allowable {allow} K for information only'), 'warn');
    }

    /* F-01 (CW-B3) — iki yol tek rozette: denge ⟷ geçici tepe. Sayılar
       sunucunun uzlaştırma bloğundan; blok/sayı yoksa rozet yok. */
    function reconciliationBadge(rc) {
        if (!rc || !isNum(rc.equilibrium_K) || !isNum(rc.fea_peak_K)) return '';
        return badge(TF('feaT.badgeReconciliation',
            { eq: fmt(rc.equilibrium_K, 0), fe: fmt(rc.fea_peak_K, 0),
              t: fmt(rc.fea_time_s, 1), gap: fmt(rc.gap_K, 0) },
            'TWO THERMAL PATHS: equilibrium (t→∞) {eq} K vs transient peak '
            + '{fe} K at t = {t} s — gap {gap} K (different questions, not '
            + 'a contradiction)'), 'info');
    }

    // V301/H-PANEL (NK-12): motorun lüle malzemesi kamara malzemesinden
    // farklı mı? (İkisi de motor sonucundan; yoksa null — iddia kurulmaz.)
    function lulMalzemesiFarki() {
        const m = motorDictLocal(lastMotorResults) || {};
        const noz = (typeof m.nozzle_material === 'string') ? m.nozzle_material.trim() : '';
        const sa = m.structural_analysis || {};
        const ch = ((sa.design_parameters || {}).material
                    || (sa.chamber_structure || {}).material_key || '');
        const kam = (typeof ch === 'string') ? ch.trim() : '';
        if (!noz || !kam || noz.toLowerCase() === kam.toLowerCase()) return null;
        return { chamber: kam, nozzle: noz };
    }

    function renderBadges(el, vm) {
        let html = '';
        if (vm.engine_layout) {
            html += badge(T('feaT.badgeEngine', 'ENGINE') + ': '
                + esc(String(vm.engine_layout).toUpperCase()), 'info');
        }
        html += badge(TF('feaT.badgeMesh',
            { elems: vm.mesh_info.n_elems, nodes: vm.mesh_info.n_nodes },
            'MESH {elems} elements / {nodes} nodes'), 'info');
        html += badge(TF('feaT.badgePeak',
            { v: fmt(vm.scalars.peak_wall_T_K, 0),
              t: fmt(vm.scalars.peak_time_s, 2) },
            'PEAK WALL T {v} K at t = {t} s'), 'info');

        // Malzeme sınırı hükmü — hüküm ve değerler SUNUCUDAN gelir
        // (material_limits); panel eşik uydurmaz, yalnız renk kodlar.
        const ml = vm.material_limits;
        if (ml && (isNum(ml.allowable_temperature_K) || isNum(ml.melting_point_K))) {
            if (ml.exceeds_melting === true) {
                html += badge(TF('feaT.badgeOverMelting',
                    { melt: fmt(ml.melting_point_K, 0) },
                    'EXCEEDS MELTING POINT ({melt} K) — the material would not '
                    + 'survive this burn'), 'err');
            } else if (ml.exceeds_allowable === true) {
                html += badge(TF('feaT.badgeOverAllowable',
                    { allow: fmt(ml.allowable_temperature_K, 0),
                      melt: fmt(ml.melting_point_K, 0) },
                    'EXCEEDS ALLOWABLE {allow} K (melting point {melt} K)'),
                    'warn');
            } else if (ml.verdict_withheld === true) {
                html += withheldBadge(ml);   // 7. tur, §28-24
            } else if (ml.exceeds_allowable === false) {
                html += badge(TF('feaT.badgeWithinLimits',
                    { allow: fmt(ml.allowable_temperature_K, 0) },
                    'WITHIN ALLOWABLE {allow} K'), 'ok');
            } else {
                // İzin sınırı kayıtta yok; yalnız erime hükmü verilebildi.
                html += badge(TF('feaT.badgeAllowMissing',
                    { melt: fmt(ml.melting_point_K, 0) },
                    'ALLOWABLE NOT PUBLISHED — below melting point {melt} K'),
                    'dim');
            }
        } else {
            html += badge(T('feaT.badgeLimitsMissing',
                'MATERIAL LIMITS NOT PUBLISHED (no temperature limit in the '
                + 'material record)'), 'dim');
        }
        // V301/H-PANEL (NK-12): bu çözüm cidarın TAMAMINI (kamara + lüle)
        // TEK malzemeyle, kamara malzemesiyle çözer (köprü tek malzemeli ağ
        // kurar: hrma/fea/bridge.py::_extract_material). Kullanıcı lüle için
        // başka bir malzeme seçtiyse (örnek: grafit) bu panelin erime hükmü
        // lülenin malzemesine AİT DEĞİLDİR — sessiz ikame yerine adıyla
        // söylenir; lülenin kendi hükmü ana sonuçtadır.
        const _lm = lulMalzemesiFarki();
        if (_lm) {
            html += badge(TF('feaT.badgeNozzleMaterialNotUsed',
                { chamber: esc(_lm.chamber), nozzle: esc(_lm.nozzle) },
                'ONE MATERIAL FOR THE WHOLE WALL: {chamber} (chamber material). '
                + 'The nozzle material you chose ({nozzle}) is NOT used here, '
                + 'so the melting verdict above is for {chamber}, not for the '
                + 'nozzle; the nozzle\'s own verdict is in Nozzle Material '
                + 'Analysis of the main result.'), 'warn');
        }

        // P11B3-21 — GEOMETRİ DEĞİŞTİYSE HÜKÜM ŞERİDİNDE SÖYLENİR
        // (yapısal kardeşle aynı kat, aynı eşik).
        const _dy = disYuzeyBeyani(vm.mesh_info && vm.mesh_info.mesh_meta);
        if (_dy && _dy.duzeltilen !== null && _dy.duzeltilen > 0) {
            html += badge(TF('feaT.badgeOuterModified',
                { n: _dy.duzeltilen,
                  pct: (_dy.sapma_yuzde !== null)
                      ? fmt(_dy.sapma_yuzde, 1) : '?' },
                'OUTER SURFACE MODIFIED at {n} station(s) · wall {pct}% vs '
                + 'requested'), 'warn');
        }
        if (vm.energy && isNum(vm.energy.residual_rel)) {
            html += badge(TF('feaT.badgeEnergy',
                { v: fmtExp(vm.energy.residual_rel) },
                'ENERGY RESIDUAL {v} (relative)'), 'info');
        }
        if (vm.time_step && 'converged' in vm.time_step) {
            // P11B3-15: rozet artık HANGİ EKSENİN yakınsadığını söyler.
            // Eski metin ("TIME STEP CONVERGED") çıplak bir "yakınsadı"
            // gibi okunuyordu; yanındaki mesh rozetiyle birlikte hükmün
            // kapsamı ekranda kapalıdır.
            html += badge(vm.time_step.converged
                ? T('feaT.badgeStepOk',
                    'TIME STEP CONVERGED (time axis only)')
                : T('feaT.badgeStepNo', 'TIME STEP NOT CONVERGED — read the '
                    + 'declaration below'),
                vm.time_step.converged ? 'ok' : 'warn');
        }
        /* P11B3-15 — mesh yakınsaması rozeti, zaman adımı rozetinin
           YANINDA; hüküm ölçülmüşse spatialBadge (F-02), yoksa fail-closed. */
        const meshRozeti = spatialBadge(vm.spatial);
        html += (meshRozeti !== null) ? meshRozeti : badge(vm.mesh_declared
            ? T('feaT.badgeMeshNotConverged',
                'MESH CONVERGENCE NOT CHECKED — spatial discretisation was '
                + 'not refined; see the declaration below')
            : T('feaT.badgeMeshNotDeclared',
                'MESH CONVERGENCE NOT DECLARED — the solver published no '
                + 'mesh policy for this run'),
            'warn');
        html += reconciliationBadge(vm.reconciliation);
        /* P11B3-16 — başlangıç koşulunun SAHİBİ rozet katında. Künye
           bloğu katlıdır; sayının kime ait olduğu katlı yerde kalırsa
           P11B3-15'in kusuru tekrarlanır. */
        if (ambientSource === 'panel_default') {
            html += badge(TF('feaT.badgeAmbientDefault',
                { v: String(AMBIENT_PANEL_DEFAULT_K) },
                'INITIAL T = {v} K IS THE PANEL DEFAULT (you supplied no '
                + 'ambient temperature)'), 'warn');
        } else if (ambientSource === 'user') {
            html += badge(TF('feaT.badgeAmbientUser',
                { v: fmt(vm.scalars.ambient_temperature_K, 2) },
                'INITIAL T {v} K SUPPLIED BY YOU'), 'info');
        }
        if (carpetFallback) {
            html += badge(T('feaT.badgeFallback',
                'CONTOUR UNAVAILABLE — node point map drawn instead'), 'dim');
        }
        el.innerHTML = html;
    }

    // warnings[] — GrainFeaPanel warn işleme deseni: {code, params} kaydı
    // I18N.tf ile basılır; sözlükte yoksa kod AYNEN görünür (gizlenmez).
    function renderWarnings(el, vm) {
        if (!el) return;
        if (!vm.warnings || !vm.warnings.length) {
            el.innerHTML = '';
            return;
        }
        let html = '<p style="margin:0 0 4px;">'
            + esc(TF('feaT.warnCount', { n: vm.warnings.length },
                     '{n} warnings declared by the solver:')) + '</p>';
        html += '<ul style="margin:0 0 0 18px;">'
            + vm.warnings.map(function (w) {
                const kod = (w && w.code) ? w.code : '';
                const metin = (window.I18N && window.I18N.tf && kod)
                    ? window.I18N.tf(kod, (w && w.params) || {}, kod)
                    : kod;
                return `<li style="margin:4px 0;">${esc(metin)}</li>`;
            }).join('') + '</ul>';
        el.innerHTML = html;
    }

    /* ÖH D26 · P11B3-21 — DIŞ YÜZEY DÜZELTMESİ BEYANI (termal ayak).
       Yapısal kardeşin (fea_panel.js `disYuzeyBeyani`) okuduğu ALANLARIN
       AYNISI okunur; iki panel aynı ağın aynı gerçeğini söyler. Sayı
       türetilmez, ucun kendi alanları basılır; alan yoksa satır yok. */
    /* ÖH D27 · OH-D26-16 — YÜZDE ÇARPANI TEK KAYNAKTAN.
       `const YUZDE = 100.0` bu dosyada ve kardeşinde AYRI AYRI yazılıydı
       (ölçüldü: a2/once.json `yuzde_yerel_tanim` = 2). Artık ikisi de
       `units_constants.js`ten OKUR. FAIL-CLOSED: modül yoksa yedek sayı
       uydurulmaz, hata fırlar. Çözüm ÇAĞRI ANINDA yapılır (yükleme anında
       değil) ki bu dosyayı units_constants.js olmadan yükleyen mevcut
       düzenekler kırılmasın — kapı, sayının KULLANILDIĞI yerdedir. */
    function yuzdeCarpani() {
        var g = (typeof window !== 'undefined') ? window : globalThis;
        if (!g.HRMAUnits && typeof require === 'function') {
            try {
                var m = require('./units_constants.js');
                g.HRMAUnits = m.UNITS;
                g.HRMAUnits.requirePercentPerFraction =
                    m.requirePercentPerFraction;
            } catch (e) { /* tarayıcıda require yok — <script> ile gelir */ }
        }
        if (!g.HRMAUnits || !g.HRMAUnits.requirePercentPerFraction) {
            throw new Error('units_constants.js must load before this panel: '
                + 'PERCENT_PER_FRACTION has a single source and is not '
                + 're-declared here.');
        }
        return g.HRMAUnits.requirePercentPerFraction();
    }

    function disYuzeyBeyani(meta) {
        if (!meta || typeof meta !== 'object') return null;
        const t = meta.dis_yuzey_egrilik_tabani;
        if (!t || typeof t !== 'object') return null;
        const duzeltilen = t.duzeltilen_istasyon;
        const sapma = t.kalinlik_sapma_orani;
        return {
            duzeltilen: (typeof duzeltilen === 'number'
                         && isFinite(duzeltilen)) ? duzeltilen : null,
            sapma_yuzde: (typeof sapma === 'number' && isFinite(sapma))
                ? sapma * yuzdeCarpani() : null,
            taban_kaynagi: (typeof t.taban_kaynagi === 'string')
                ? t.taban_kaynagi : null,
        };
    }

    function disYuzeySatirlari(meta) {
        const d = disYuzeyBeyani(meta);
        if (!d) return [];
        const satir = [];
        if (d.duzeltilen !== null) {
            satir.push(TF('feaT.meshOuterCorrected', { n: d.duzeltilen },
                'mesh.meta: the outer surface was corrected at {n} axial '
                + 'station(s) for well-posedness; the wall solved here is the '
                + 'meshed wall, not the raw offset.'));
        }
        if (d.sapma_yuzde !== null) {
            satir.push(TF('feaT.meshThicknessDeviation',
                { pct: fmt(d.sapma_yuzde, 1) },
                'mesh.meta: solved wall thickness deviates {pct}% from the '
                + 'requested thickness (kalinlik_sapma_orani).'));
        }
        if (d.taban_kaynagi) satir.push(SRV(d.taban_kaynagi));
        return satir;
    }

    function renderBasis(els, vm) {
        if (!els.basis || !els.basisText) return;
        const parts = [];
        if (vm.basis.solver) parts.push(SRV(vm.basis.solver));
        if (vm.basis.fields) parts.push(SRV(vm.basis.fields));
        if (vm.basis.history) parts.push(SRV(vm.basis.history));
        if (vm.basis.material) parts.push(SRV(vm.basis.material));
        if (vm.basis.mesh_policy) parts.push(SRV(vm.basis.mesh_policy));
        /* F-02 — merdivenin seviyeleri sayılarıyla (sunucudan). */
        if (vm.spatial && vm.spatial.levels && vm.spatial.levels.length) {
            /* Ş4: merdiven metnindeki sayılar ekran biçimlendiricisinden
               (TR virgül); Ş7: dışdeğer asimptotik aralık dışındaysa
               (richardson_reliable === false) SAYI BASILMAZ, nedeni yazılır
               — sunucu sayıyı yine yayımlar, ekran onu hata sınırı gibi
               göstermez. */
            const merdiven = vm.spatial.levels.map(function (l) {
                return l.n_axial + '×' + l.n_radial + ' ' + fmtScr(l.peak_K, 2)
                    + ' K' + (l.published ? ' *' : '');
            }).join(' → ');
            if (vm.spatial.richardson_reliable === false) {
                parts.push(TF('feaT.ladderLineUnreliable', { ladder: merdiven },
                    'Spatial ladder (peak wall T; * = published level): '
                    + '{ladder}; Richardson extrapolation NOT shown — the '
                    + 'observed order is below the asymptotic minimum, so the '
                    + 'extrapolation and the residual error estimates are a '
                    + 'direction indicator only, not an error bound'));
            } else {
                parts.push(TF('feaT.ladderLine',
                    { ladder: merdiven,
                      ext: (vm.spatial.extrapolated_K !== null)
                          ? fmt(vm.spatial.extrapolated_K, 2) : '—' },
                    'Spatial ladder (peak wall T; * = published level): {ladder}; '
                    + 'Richardson extrapolation {ext} K.'));
            }
            if (vm.spatial.declaration) parts.push(SRV(vm.spatial.declaration));
        }
        /* F-01 — uzlaştırma: hangi sayı hangi soruya cevap (sunucu metni). */
        if (vm.reconciliation) {
            const r = vm.reconciliation;
            parts.push(TF('feaT.reconLine',
                { eq: (isNum(r.equilibrium_K) ? fmt(r.equilibrium_K, 1) : '—'),
                  fe: (isNum(r.fea_peak_K) ? fmt(r.fea_peak_K, 1) : '—'),
                  gap: (isNum(r.gap_K) ? fmt(r.gap_K, 1) : '—') },
                'Two thermal paths — equilibrium chain {eq} K (steady-state '
                + 'surface energy balance, t→∞) vs this FEA peak {fe} K '
                + '(transient, end of burn); gap {gap} K.'));
            if (r.question_equilibrium) parts.push(SRV(r.question_equilibrium));
            if (r.question_fea) parts.push(SRV(r.question_fea));
        }
        /* B2-CP — okunan motor yolları (yalnız künye; sayı değil). */
        if (vm.consumed_paths && vm.consumed_paths.length) {
            parts.push(TF('feaT.consumedPaths', { n: vm.consumed_paths.length,
                list: vm.consumed_paths.map(function (c) { return c.path; }).join(', ') },
                'Motor fields read by the FEA bridge ({n}): {list}.'));
        }
        // P11B3-21 — ağ üreticisinin geometri beyanı.
        disYuzeySatirlari(vm.mesh_info && vm.mesh_info.mesh_meta)
            .forEach(function (c) { parts.push(c); });
        /* ÖH D26 / OH-B3-02 — konturun künyesi (wall_profile.contour_basis).
           Uç yedi alt alan yayımlıyordu, panel bloğu hiç anmıyordu; h(z)
           profili ekranda künyesiz çiziliyordu. Alt alanlar AYNEN, ad =
           değer olarak basılır (panel metni yeniden yazmaz). */
        if (lastContourBasis) {
            const satir = Object.keys(lastContourBasis).map(function (ad) {
                const v = lastContourBasis[ad];
                return ad + ' = ' + ((v === null || v === undefined)
                    ? T('feaT.notSupplied', 'not supplied')
                    : (typeof v === 'object' ? JSON.stringify(v) : String(v)));
            });
            if (satir.length) {
                parts.push(T('feaT.contourBasisTitle',
                    'Contour basis of the h(z) profile (published by '
                    + '/api/analysis/wall-profile):') + '\n' + satir.join('\n'));
            }
        }
        /* ÖH D28 / arayuz a1 (OH-D27-16) — SÜTUN KÜNYESİ VE BİRİMLERİ.
           ÖLÇÜLDÜ (a1/once.json, taban 7cd08bcc): D26 / app-api a4
           (`e5882484`, P7B3-31) bu uca `column_basis` (6 sütun) ve
           `units` (14 sütun) bloklarını ekledi; panel ikisini de hiç
           okumuyordu. Künyenin taşıdığı ölçüm şudur: `q_MW` TASARIM
           referans cidarında, `T_wall_eq` ise yüzey enerji dengesinden
           gelir; q/(T_recovery − T_wall_eq) orta istasyonda yayımlanan
           `h_g`nin 86,1 KATIDIR. Üç sütunu q = h_g·ΔT diye birbirine
           bağlayan okuyucu 86 kat yanılır — künye bu yüzden ekranda
           olmak zorundadır. Metin SUNUCUDAN gelir (SRV), panel onu
           yeniden yazmaz; birim `units` bloğundan okunur, uydurulmaz. */
        if (lastColumnBasis || lastProfileUnits) {
            const kunye = lastColumnBasis || {};
            const birim = lastProfileUnits || {};
            // Fiziksel sütunlar ADIYLA öne alınır (okuma sırası tutarlı
            // olsun diye); ucun yayımladığı başka ad varsa o da DÜŞMEZ.
            const onSira = ['h_g', 'q_MW', 'T_wall_eq', 'T_recovery',
                            'mach', 'area_ratio'];
            const gorulen = {};
            const sutunlar = [];
            onSira.concat(Object.keys(kunye), Object.keys(birim))
                .forEach(function (ad) {
                    if (gorulen[ad]) return;
                    if (!(ad in kunye) && !(ad in birim)) return;
                    gorulen[ad] = true;
                    sutunlar.push(ad);
                });
            const satirlar = sutunlar.map(function (ad) {
                const b = birim[ad];
                const k = kunye[ad];
                return ad + (b ? ' [' + String(b) + ']' : '')
                    + (k ? ' = ' + SRV(String(k)) : '');
            });
            if (satirlar.length) {
                parts.push(T('feaT.columnBasisTitle',
                    'Column basis and units of the axial profile '
                    + '(published by /api/analysis/wall-profile - q_MW is '
                    + 'the DESIGN flux at the reference wall, NOT '
                    + 'h_g*(T_recovery - T_wall_eq)):')
                    + '\n' + satirlar.join('\n'));
            }
        }
        /* ÖH D37 A2-1 termal 7. tur (karar §28-24 §2) — h(z)'nin gazı:
           her alanın değeri ve KÖKENİ sunucunun bloğundan AYNEN. */
        if (lastGasBasis) {
            const gsat = ['gamma', 'molecular_weight', 'c_star']
                .filter(function (ad) {
                    return lastGasBasis[ad] && typeof lastGasBasis[ad] === 'object';
                })
                .map(function (ad) {
                    const g = lastGasBasis[ad];
                    return ad + ' = ' + (isNum(g.value) ? fmt(g.value, 4) : '—')
                        + (g.unit ? ' ' + String(g.unit) : '')
                        + ' (' + String(g.source) + ')';
                });
            if (gsat.length) {
                const eksik = Array.isArray(lastGasBasis.assumed_fields)
                    ? lastGasBasis.assumed_fields : [];
                parts.push(TF('feaT.gasBasisTitle',
                    { assumed: eksik.length ? eksik.join(', ') : '—' },
                    'Gas properties of the h(z) profile (module defaults: '
                    + '{assumed}):') + '\n' + gsat.join('\n'));
            }
        }
        /* ÖH D26 / P11B3-16 — gönderilen ortam sıcaklığının SAHİBİ.
           `ambientSource` koşum anında kaydedilir; burada yalnız okunur. */
        if (ambientSource === 'panel_default') {
            parts.push(TF('feaT.ambientPanelDefault',
                { v: String(AMBIENT_PANEL_DEFAULT_K) },
                'Initial / ambient temperature {v} K is THIS PANEL\'s default, '
                + 'not a value you supplied: the field was pre-filled and was '
                + 'never edited. The solver used it as the uniform initial '
                + 'condition. Change the field to run on your own number.'));
        } else if (ambientSource === 'user') {
            parts.push(T('feaT.ambientUser',
                'Initial / ambient temperature was supplied by you (the field '
                + 'was edited before this run).'));
        }
        if (vm.bc.inner) parts.push(SRV(vm.bc.inner));
        if (vm.bc.initial) parts.push(SRV(vm.bc.initial));
        if (vm.bc.window) parts.push(SRV(vm.bc.window));
        if (vm.time_step && vm.time_step.beyan) parts.push(SRV(vm.time_step.beyan));
        if (vm.basis.limits_note) parts.push(SRV(vm.basis.limits_note));
        parts.push(T('feaT.unitNote', 'Units: the solver returns kelvin, '
            + 'metres and seconds; the panel plots them exactly as received. '
            + 'No smoothing, no resampling, no rescaling of any field is '
            + 'applied.'));
        parts.push(T('feaT.axisNote', 'Axes of the field map are NOT equally '
            + 'scaled: the wall is thin compared with the engine length, so '
            + 'the radial axis is stretched to make the wall visible.'));
        let html = parts.map(function (p) {
            return `<p style="margin:0 0 8px;">${esc(p)}</p>`;
        }).join('');
        if (vm.not_modelled && vm.not_modelled.length) {
            html += `<p style="margin:8px 0 4px; color:${MISSING_COLOR};"
                data-decl-count="${vm.not_modelled.length}">${esc(TF(
                'feaT.notModelledCount', { n: vm.not_modelled.length },
                '{n} physics items are NOT modelled in this thermal run:'))}</p>`;
            html += '<ul style="margin:0 0 0 18px;">'
                + vm.not_modelled.map(function (t) {
                    return `<li style="margin:4px 0;">${esc(SRV(t))}</li>`;
                }).join('') + '</ul>';
        }
        els.basisText.innerHTML = html;
        els.basis.style.display = '';
    }

    function hidePlots(els) {
        ['field', 'inner', 'hist'].forEach(function (k) {
            if (els[k]) els[k].style.display = 'none';
        });
        if (els.bcNote) els.bcNote.innerHTML = '';
        if (els.warnings) els.warnings.innerHTML = '';
    }

    function render() {
        const vm = buildViewModel(lastPayload, lastError);
        const els = {
            badges: document.getElementById('fea_t_badges'),
            chip: document.getElementById('fea_t_chip'),
            busy: document.getElementById('fea_t_busy'),
            cancel: document.getElementById('fea_t_cancel'),
            warnings: document.getElementById('fea_t_warnings'),
            field: document.getElementById('fea_t_plot_field'),
            inner: document.getElementById('fea_t_plot_inner'),
            hist: document.getElementById('fea_t_plot_hist'),
            bcNote: document.getElementById('fea_t_bc_note'),
            basis: document.getElementById('fea_t_basis'),
            basisText: document.getElementById('fea_t_basis_text'),
        };
        if (!els.badges || !els.chip) return;   // panel kurulmamış

        if (els.busy) {
            // Yüzde YOK (sahte ilerleme yasak) ama GEÇEN SÜRE ve SÜRE
            // SINIRI yazılır — P17B1-18: eski satır gerekçesiz, süresiz
            // ve sonsuzdu; kullanıcı takılı koşumu yavaş koşumdan
            // ayıramıyordu.
            const bel = els.busy;
            bel.style.display = busy ? '' : 'none';
            if (!busy) {
                bel.textContent = '';
                ozS(bel, 'data-indeterminate');
                ozS(bel, 'data-elapsed-s');
                nabziDurdur();
            } else {
                ozY(bel, 'data-indeterminate', 'true');
                const govde = T('feaT.busy', 'Running — the gas-side profile is '
                    + 'computed first, then the transient solver refines its time '
                    + 'step until the peak temperature stops changing; the '
                    + 'duration is not known in advance.');
                const ms = zamanAsimiMs();
                const boya = function () {
                    const gecen = busySince
                        ? Math.max(0, Math.round((Date.now() - busySince) / 1000)) : 0;
                    ozY(bel, 'data-elapsed-s', String(gecen));
                    bel.textContent = govde + ' ' + (ms
                        ? TF('feaT.busyElapsed',
                             { s: gecen, limit: Math.round(ms / 1000) },
                             'Elapsed {s} s; the request is cancelled after '
                             + '{limit} s.')
                        : TF('feaT.busyElapsedNoLimit', { s: gecen },
                             'Elapsed {s} s.'));
                };
                boya();
                nabziDurdur();
                // Nabız yalnız gerçek, bağlı DOM düğümünde kurulur.
                if (bel.isConnected !== true
                        || typeof setInterval !== 'function') return;
                nabizTimer = setInterval(function () {
                    if (!bel.isConnected || bel.style.display === 'none') {
                        nabziDurdur();
                        return;
                    }
                    boya();
                }, NABIZ_MS);
            }
        }
        // P11B3-19 — iptal düğmesi YALNIZ koşum sürerken görünür.
        if (els.cancel && els.cancel.style) {
            els.cancel.style.display = busy ? '' : 'none';
        }

        if (vm.mode !== 'ok') {
            hidePlots(els);
            els.badges.innerHTML = '';
            if (els.basis) els.basis.style.display = 'none';
            if (vm.mode === 'idle') {
                els.chip.innerHTML = busy ? '' : chipHtml(
                    T('feaT.chipIdle',
                      'NOT RUN YET — press "Run thermal analysis" to solve the '
                      + 'wall of the current result'), '');
            } else if (vm.mode === 'not_modelled') {
                const missing = vm.missing.length
                    ? TF('feaT.missingList', { list: vm.missing.join(', ') },
                         'Missing inputs: {list}')
                    : '';
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipNotModelled',
                      'NOT MODELLED — the inputs the thermal FEA needs are not '
                      + 'all available; nothing is drawn'),
                    [missing, vm.reason].filter(Boolean).join('\n'));
            } else if (vm.mode === 'error') {
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipError', 'RUN FAILED — no field is drawn'),
                    vm.error);
            } else {
                els.chip.innerHTML = chipHtml(
                    T('feaT.chipInvalid',
                      'DATA INCONSISTENT — the response carries no usable mesh '
                      + 'grid; nothing is plotted'), '');
            }
            return;
        }

        if (!vm.grid_consistent) {
            hidePlots(els);
            els.badges.innerHTML = '';
            els.chip.innerHTML = chipHtml(
                T('feaT.chipGridMismatch',
                  'MESH INCONSISTENT — the node grid does not match the '
                  + 'declared node count; nothing is plotted'), '');
            return;
        }

        // Her basımda yedek bayrağı sıfırlanır (fea_panel deseni).
        carpetFallback = false;
        els.chip.innerHTML = '';
        renderBadges(els.badges, vm);
        renderWarnings(els.warnings, vm);
        renderBasis(els, vm);

        // Dış yüzey sınır koşulu beyanı — uç adyabatik dışı KENDİSİ beyan
        // eder; panel o cümleyi aynen gösterir (outer_ambient istenmez).
        if (els.bcNote) {
            els.bcNote.innerHTML = vm.bc.outer
                ? '<strong data-i18n="feaT.bcOuter">'
                    + esc(T('feaT.bcOuter',
                            'Outer surface boundary condition (declared by '
                            + 'the solver):')) + '</strong> ' + esc(SRV(vm.bc.outer))
                : '';
        }

        // T(z, r) alanı — MESH üstünde kontur
        if (vm.temperature_K) {
            els.field.style.display = 'block';
            try {
                drawFigure(els.field, fieldFigure(vm));
            } catch (e) {
                carpetFallback = true;
                drawFigure(els.field, fieldFallbackFigure(vm));
                renderBadges(els.badges, vm);
            }
        } else {
            els.field.style.display = 'none';
        }

        // İç yüzey T(z)
        if (vm.inner) {
            els.inner.style.display = 'block';
            drawFigure(els.inner, innerFigure(vm));
        } else {
            els.inner.style.display = 'none';
        }

        // Tepe cidar T(t) geçmişi (tek nokta eğri değildir, çizilmez)
        if (vm.history && vm.history.times_s.length >= 2) {
            els.hist.style.display = 'block';
            drawFigure(els.hist, historyFigure(vm));
        } else {
            els.hist.style.display = 'none';
        }
    }

    // ------------------------------------------------------------------
    // Koşum
    // ------------------------------------------------------------------
    function pickResults() {
        if (typeof cfg.resultsProvider === 'function') {
            try {
                const r = cfg.resultsProvider();
                if (r && typeof r === 'object') return r;
            } catch (e) { /* sağlayıcı patlarsa genel yola düş */ }
        }
        if (lastMotorResults && typeof lastMotorResults === 'object') {
            return lastMotorResults;
        }
        const cur = window.currentResults;
        return (cur && typeof cur === 'object') ? cur : null;
    }

    /* ÖH D26 / P11B3-16 — alan KİMİN? `data-dirty` imi analysis_dock'un
       öneri kapısıyla aynı desendir: kullanıcı alana dokunduğu anda im
       düşer ve panel bir daha "bu benim varsayılanım" demez. */
    function markAmbientDirty() {
        const el = document.getElementById('fea_t_ambient');
        if (el) el.setAttribute('data-dirty', '1');
    }

    function ambientIsUserSupplied() {
        const el = document.getElementById('fea_t_ambient');
        return !!(el && el.getAttribute('data-dirty') === '1');
    }

    function readAmbientK() {
        const el = document.getElementById('fea_t_ambient');
        const v = el ? parseFloat(el.value) : NaN;
        return isNum(v) ? v : undefined;
    }

    function run() {
        if (busy) return Promise.resolve(null);
        const results = pickResults();
        const motor = motorDictLocal(results);
        if (!motor || typeof motor !== 'object') {
            lastPayload = null;
            lastError = T('feaT.noResult',
                'No motor result on this page yet — run the motor calculation first.');
            render();
            return Promise.resolve(null);
        }

        // Çekirdek alan eksikse wall-profile ucu HİÇ çağrılmaz: o ucun
        // sunucu varsayılanları başka bir motorun profili olurdu. Eksik
        // ADIYLA beyan edilir (panelin kendi beyanı — uç yanıtı değil).
        const built = buildWallProfileBody(results);
        if (built.missing.length) {
            lastPayload = {
                status: 'NOT_MODELLED',
                missing: built.missing,
                reason: T('feaT.clientMissingReason',
                    'The motor result on this page does not carry these '
                    + 'fields. The wall-profile endpoint would silently '
                    + 'substitute defaults for them — that would be another '
                    + 'motor\'s profile — so it is not called. (Declared by '
                    + 'the panel, before any request.)'),
            };
            lastError = null;
            render();
            return Promise.resolve(null);
        }

        const ambientK = readAmbientK();
        // P11B3-16: gönderilen sayının SAHİBİ koşumla birlikte kaydedilir.
        // Alan boşsa/çözülemezse kaynak da yoktur (uydurulmaz).
        ambientSource = (ambientK === undefined)
            ? null
            : (ambientIsUserSupplied() ? 'user' : 'panel_default');

        busy = true;
        busySince = Date.now();
        lastError = null;
        render();
        // Adım 1 — h(z) profili (ölçülmüş zincir): /api/analysis/wall-profile
        return fetch(PROFILE_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(built.body),
            signal: kosumSinyali(),   // P17B4-07 + P11B3-19 (adım 1)
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            if (!r.ok || !r.body || r.body.status !== 'success') {
                throw new Error((r.body && r.body.error)
                    || T('feaT.profileHttpError',
                         'The wall-profile endpoint returned an error; the '
                         + 'thermal FEA was not attempted.'));
            }
            const wp = r.body.wall_profile;
            // OH-B3-02: konturun künyesi AYNEN saklanır (uç ne yayımladıysa);
            // panel onu yeniden yazmaz, künye bloğunda gösterir.
            lastContourBasis = (wp && wp.contour_basis
                                && typeof wp.contour_basis === 'object')
                ? wp.contour_basis : null;
            // OH-D27-16 (ÖH D28 / arayuz a1): sütun künyesi ve birimleri
            // de AYNEN saklanır. Uç yayımlamadıysa null kalır ve künye
            // bölümünde hiçbir satır çıkmaz — birim UYDURULMAZ.
            lastColumnBasis = (wp && wp.column_basis
                               && typeof wp.column_basis === 'object')
                ? wp.column_basis : null;
            lastProfileUnits = (wp && wp.units
                                && typeof wp.units === 'object')
                ? wp.units : null;
            lastGasBasis = (wp && wp.gas_properties_basis
                            && typeof wp.gas_properties_basis === 'object')
                ? wp.gas_properties_basis : null;
            if (!wp || !Array.isArray(wp.x_mm) || !wp.x_mm.length) {
                throw new Error(T('feaT.profileEmpty',
                    'The wall-profile endpoint returned no axial stations; '
                    + 'the thermal FEA was not attempted.'));
            }
            // Adım 2 — geçici termal FEA: wall_profile bloğu AYNEN geçer.
            const govde = {
                motor_results: motor,
                axial_profile: wp,
            };
            // Ortam sıcaklığı kullanıcı alanından; boş/geçersizse
            // UYDURULMAZ — uç eksiği kendi sözleşmesiyle adlandırır.
            if (ambientK !== undefined) govde.ambient_temperature_K = ambientK;
            return fetch(THERMAL_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(govde),
                // Adım 2 AYNI sinyali taşır: iptal burada da geçerlidir.
                signal: aktifSinyal || zamanAsimiSinyali(),
            });
        }).then(function (resp) {
            return resp.json().then(function (body) {
                return { ok: resp.ok, body: body };
            });
        }).then(function (r) {
            busy = false;
            busySince = null;
            // OH-D17-07: uç, köprü reddettiğinde artık HTTP 200 + 'success'
            // DEĞİL, adlandırılmış red yayımlıyor (NOT_MODELLED -> 422 +
            // status='not_modelled'; NOT_AVAILABLE / INPUTS_READY -> 501).
            // Bunlar HATA DEĞİL, köprünün BEYANLI hükmüdür: gövde
            // 'fea.missing' / 'fea.reason' taşır ve panelin kendi
            // NOT_MODELLED kartı (buildViewModel) tam da bunu gösterir.
            // Jenerik hata metnine düşürülürse kullanıcı hangi alanın eksik
            // olduğunu göremez.
            const REDDEDILEN = ['not_modelled', 'not_available',
                                'inputs_ready'];
            const durum = r.body && r.body.status;
            const koprununRedBeyani = (REDDEDILEN.indexOf(durum) >= 0
                                       && r.body.fea);
            if (durum === 'success' || koprununRedBeyani) {
                lastPayload = r.body.fea || null;
                lastError = null;
            } else {
                lastPayload = null;
                lastError = (r.body && (r.body.detail || r.body.error))
                    || T('feaT.httpError',
                         'The thermal FEA endpoint returned an error.');
            }
            kosumBitti();
            render();
            return lastPayload;
        }).catch(function (e) {
            const gecen = busySince
                ? Math.round((Date.now() - busySince) / 1000) : null;
            const iptalEdildi = kullaniciIptali;
            busy = false;
            busySince = null;
            kosumBitti();
            lastPayload = null;
            // P17B1-18 — sessiz düşüş yok: zaman aşımı adıyla ve süresiyle
            // beyan edilir; iki adımlı koşumda hangi adımda düştüğü
            // sunucunun kendi cümlesinden gelir, uydurulmaz.
            // P11B3-19 — kullanıcı durdurduysa AYRI cümle: iptal bir arıza
            // değildir ve arıza gibi anlatılmaz.
            lastError = iptalEdildi
                ? TF('feaT.cancelled', { s: gecen === null ? 0 : gecen },
                     'You stopped the thermal FEA run after {s} s. Nothing was '
                     + 'computed and no result was changed.')
                : zamanAsimiMi(e)
                ? TF('feaT.timeout',
                     { s: gecen === null ? '—' : gecen },
                     'The thermal FEA run was cancelled after {s} s without a '
                     + 'reply from the solver. Nothing was computed. Try a '
                     + 'coarser axial profile, then run it again.')
                : String((e && e.message) || e);
            render();
            return null;
        });
    }

    // Yeni motor sonucu geldi: eski FEA çıktısı BAYATTIR, silinir.
    function update(results) {
        lastMotorResults = results || null;
        if (lastPayload || lastError) {
            lastPayload = null;
            lastError = null;
        }
        render();
    }

    function init(opts) {
        cfg = opts || {};
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        // Panel #feaPanel'in HEMEN ALTINA yerleşir (yapısal FEA'nın termal
        // kardeşi). Çapa yoksa yapısal panelin kendi çapasının önüne, o da
        // yoksa sonuç ızgarasına düşülür.
        const anchor = document.getElementById(cfg.anchorId || 'feaPanel');
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor.nextSibling);
        } else {
            const fb = document.getElementById(
                cfg.fallbackAnchorId || 'trajectoryPanel');
            if (fb && fb.parentNode) {
                fb.parentNode.insertBefore(panel, fb);
            } else {
                (document.querySelector('.results-grid')
                    || document.body).appendChild(panel);
            }
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);

        // P11B3-19 — iptal düğmesi: koşumu DURDURUR, sayfayı yenilemez.
        const cancelBtn = document.getElementById('fea_t_cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', function () {
            kosumuIptalEt();
        });
        const runBtn = document.getElementById('fea_t_run');
        if (runBtn) runBtn.addEventListener('click', function () { run(); });
        const meshBox = document.getElementById('fea_t_show_mesh');
        if (meshBox) {
            meshBox.addEventListener('change', function () {
                showMesh = !!meshBox.checked;
                render();
            });
        }
        /* ÖH D26 / P11B3-16 — kullanıcı ortam sıcaklığına DOKUNDUĞU anda
           alan onun olur. `input` olayı yazmayı, `change` ok tuşu/spinner
           ile değişimi yakalar; ikisi de aynı imi düşürür. */
        const ambientBox = document.getElementById('fea_t_ambient');
        if (ambientBox) {
            ambientBox.addEventListener('input', markAmbientDirty);
            ambientBox.addEventListener('change', markAmbientDirty);
        }

        // Hesap köprüsü: fea_panel.js/blowdown_panel.js ile AYNI desen.
        // advanced.html'de sonuç basıcısı 'displayCalculationResults'tır
        // (app.js:176'dan çağrılır; 'displayResults' bu sayfada YOKTUR).
        // Özgün işlev her koşulda çalışır; panel hatası hesabı engellemez.
        (function () {
            const ad = cfg.hookName || 'displayCalculationResults';
            const original = window[ad];
            if (typeof original !== 'function') return;
            window[ad] = function (results) {
                const out = original.apply(this, arguments);
                try {
                    update(results);
                } catch (e) {
                    console.error('Thermal FEA panel update failed:', e);
                }
                return out;
            };
        })();

        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                try { render(); } catch (e) { /* çizim yoksa sessiz */ }
            });
        }
        render();
    }

    window.ThermalFeaPanel = {
        init: init,
        update: update,
        run: run,
        buildViewModel: buildViewModel,
        setShowMesh: function (v) { showMesh = !!v; render(); },
        applyPayload: function (fea, error) {
            lastPayload = fea || null;
            lastError = error || null;
            busy = false;
            render();
        },
        // Bekçi testleri için: birim dönüşümü kilidi bu iki işlev üstünde
        // sınanır (AnalysisDock yokken yedek yol koşar).
        _buildWallProfileBody: buildWallProfileBodyMeta,
        _fallbackLengthM: fallbackLengthM,
        get payload() { return lastPayload; },
    };
})();
