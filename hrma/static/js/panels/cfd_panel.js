/* ====================================================================
   HRMA Analiz Merkezi — CFD kiracısı (lüle iç akışı, 2B eksenel simetrik
   Euler + Summerfield ayrılma köprüsü)
   --------------------------------------------------------------------
   Merkez'in (analysis_center.js) İLK canlı kiracısı. POST /api/cfd/nozzle
   yanıtını çizer; hesap YAPMAZ, hüküm ÜRETMEZ — çözücünün kendi beyanlarını
   taşır ve okunur hâle getirir.

   KAPATILAN KUSUR
     hrma/cfd/ çözücüsü ve /api/cfd/nozzle ucu depoda çalışır hâldeydi ama
     hiçbir kullanıcı yüzü onları çağırmıyordu: ne duvar basıncı, ne akış
     alanı, ne ayrılma hükmü, ne de yakınsama geçmişi görünüyordu.

   ÖLÇÜLMÜŞ ZİNCİR (16 Ağu 2026, üç motor da canlı koşturuldu)
     1) Motor hesabı (window.currentResults) lüle konturunu YAYIMLIYOR:
        results.nozzle_contour.points = [[z_m, r_m], ...] (hibritte
        results.motor.nozzle_contour). Kontur uydurulamaz; bu yüzden
        yokluğu satırı gri yapar (applicability).
     2) Gaz durumu: hibrit ve KATI motor `nozzle_flow_quasi1d.inputs`
        bloğunu SI olarak yayımlıyor (P0_Pa, T0_K, gamma, R_J_kgK) —
        ucun istediği dört büyüklüğün dördü de orada, birim çevirisi
        GEREKMİYOR. SIVI motorda o blok YOK (ölçüldü), düz alanlara
        düşülüyor: chamber_pressure [bar]×1e5, chamber_temperature [K],
        gamma, molecular_weight → R = 8314,462618 / MW.
        Çapraz teyit: hibritte MW'den hesaplanan R = 397,110442…, motorun
        kendi combustion_analysis…gas_constants.chamber değerine BİT-AYNI;
        katıda quasi1d R = 296,9450935 = 8314,462618 / 28,0.
     3) Ortam basıncı üç motorda ÜÇ AYRI yerde yayımlanıyor (ölçüldü):
        hibrit  nozzle_expansion_screen.ambient_pressure_bar   (1,0 bar)
        katı    nozzle_flow_separation.ambient_pressure_Pa     (101325 Pa)
        sıvı    nozzle_design.performance.ambient_pressure     (1,01325 bar)
        Panel bu yolları SIRAYLA dener ve hangisinden geldiğini EKRANDA
        yazar. Hiçbiri yoksa öneri YOKTUR — "deniz seviyesi" varsaymak
        sessiz bir uydurma olurdu (ucun kendi sözleşmesi de bunu reddeder).

   SAHTE VERİ / SAHTE İLERLEME YASAĞI
     * Bu dosyada setInterval / setTimeout / requestAnimationFrame /
       Math.random YOKTUR. Koşum sırasındaki tek beyan Merkez'in gerçek
       durum satırıdır; yüzde çubuğu, dolan animasyon, sahte kalıntı akışı
       yok. Süreyi uç ölçer (runtime_s / solver_runtime_s), panel basar.
     * Hiçbir alanın SONLU VARSAYILANI yoktur: öneri bulunamayan alan BOŞ
       kalır ve `body()` isteği HİÇ GÖNDERMEZ, eksikleri adıyla yazar.
       (Çerçeve kuralı "sonlu varsayılanlı alan zorunludur" der; buradaki
       beş büyüklük için sonlu varsayılan yazmak = uydurma sayı göstermek.)
     * Çizilen her sayı yanıttan gelir. Tek dönüşüm Pa → bar bölmesidir
       (PA_PER_BAR) ve eksen başlığında beyan edilir.
     * Duvar poliçizgisi YALNIZ bu koşuya gönderilen kontur olduğu
       ÖLÇÜLEBİLDİĞİNDE çizilir (nokta sayısı + ızgaranın yayımladığı
       giriş/çıkış z,r uçları birebir tutmalı); tutmuyorsa çizilmez ve
       nedeni yazılır. Geçmişten gelen bir koşuya bugünkü kontur
       giydirilmez.
     * Koşu öncesi "bütçe yetmeyebilir" beklentisi PANELDE HESAPLANMAZ: uç
       onu `inlet_conditioning` bloğunda ölçülmüş dayanağıyla yayımlar
       (bant kuralının, ölçüm tablosunun ve tetiklenen gerekçelerin ikinci
       bir tanımı burada yazılmaz). Panel o bloğu "hüküm değildir" diliyle
       basar. NÖBET DEĞİŞİMİ (16 Ağu 2026): blok eskiden giriş Mach EŞİĞİ
       taşıyordu (`threshold_mach` / `advisory`); çözücünün giriş sınır
       koşulu karakteristik biçime çevrilince o eşik ölçülen hiçbir şeyi
       bildirmez oldu ve sağlıklı koşularda turuncu rozet basıyordu. Panelde
       Mach eşiği dili KALMADI; uyarı artık iterasyon BÜTÇESİNİN uyarısıdır
       (`budget_advisory` + `budget_advisory_reasons`).

   HÜKÜM (verdict) — çerçeve kural 4
     converged=true  → 'ok'   + iterasyon sayısı, künyede çözücünün
                               convergence_basis cümlesi
     converged=false → 'warn' + son kalıntı; ayrılma bloğu kendi
                               judgment_confidence='suspect' etiketiyle
                               ayrıca görünür.
     cfd bloğu yoksa → hüküm BEYAN EDİLMEZ (çerçeve "hüküm beyan edilmedi"
                               rozetini basar; buradan sahte 'ok' çıkmaz).

   Bekçi testleri: tests/test_cfd_panel.py (node ile izole koşum + Merkez
   ile birlikte uçtan uca) ve uç tarafında tests/test_cfd_endpoint.py.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    const ENDPOINT = '/api/cfd/nozzle';

    //: Birim çevirisinin TEK yeri (motor_viz_deck.js / transient_panel.js
    //: ile aynı ad ve aynı değer). Motorların düz `chamber_pressure` alanı
    //: BAR taşır (ölçüldü: hibritte 20 → quasi1d P0_Pa 2 000 000; katıda
    //: 40 → 4 000 000); uç ise Pascal ister.
    const PA_PER_BAR = 1e5;

    //: Evrensel gaz sabiti [J/(kmol·K)] — R = R_u / MW [g/mol] kuralının
    //: kaynağı motorun KENDİ beyanıdır: hibrit quasi1d bloğu
    //: 'gas_property_source' alanında aynı formülü yazıyor
    //: ("R = 8314.462618 / molecular_weight"). İkinci bir tanım değil,
    //: aynı tanımın istemci tarafındaki uygulanışıdır.
    const R_UNIVERSAL = 8314.462618;

    //: ALAN HARİTASININ BÜYÜKLÜKLERİ (parti 30 — üçüncü büyüklük eklendi).
    //: `id` ve `payloadKey` sütunları motor_viz3d.js'in CFD_METRICS
    //: tablosuyla ve ucun (hrma/app.py) 'field' sözlüğündeki GERÇEK
    //: anahtarlarla KÜME EŞİTLİĞİ bekçisine bağlıdır
    //: (tests/test_cfd_alan_koprusu.py) — üç yerden biri kayarsa kırmızı.
    //: Buradaki EK sütun 2B sunuma aittir: panel basıncı bar'a çevirir
    //: (3B sahne Pa gösterir), bu yüzden ölçek/etiket YALNIZ burada durur.
    const FIELD_METRICS = [
        { id: 'mach', payloadKey: 'mach', scale: 1,
          labelKey: 'panel.cfd.metricMach',
          labelFallback: 'Mach number [-]' },
        { id: 'pressure', payloadKey: 'pressure_Pa', scale: 1 / PA_PER_BAR,
          labelKey: 'panel.cfd.metricPressure',
          labelFallback: 'Static pressure [bar]' },
        { id: 'temperature', payloadKey: 'temperature_K', scale: 1,
          labelKey: 'panel.cfd.metricTemperature',
          labelFallback: 'Static temperature [K]' },
    ];

    //: 3B sahnenin üretebildiği RED kodlarının TAM kümesi. Panel bu listeyi
    //: YALNIZ "bu kodu tanıyor muyum" denetimi için tutar: kullanıcıya
    //: basılan METİN sahnenin kendi reason.key/fallback çiftinden gelir,
    //: yani mesajın ikinci bir tanımı burada YOKTUR. Tanınmayan kod gelirse
    //: panel bunu adıyla beyan eder (sessiz "olmadı" mesajı yasak).
    //: Küme eşitliği bekçisi: tests/test_cfd_alan_koprusu.py.
    const VIZ3D_REASON_CODES = ['no_scene', 'no_solver_contour',
        'contour_mismatch', 'missing_metric', 'bad_field_block', 'no_field'];

    //: Çizim kimliklerinin çakışmaması için koşum sayacı (her çizimde artar).
    let drawSeq = 0;
    //: Alan haritasında gösterilen büyüklük (FIELD_METRICS kimliklerinden).
    let fieldMetric = 'mach';
    //: En son GÖNDERİLEN kontur (duvar çizgisi ancak bununla eşleşen
    //: yanıtlarda çizilir; geçmişten gelen koşuya bugünkü kontur giydirilmez).
    let lastSentContour = null;
    //: En son öneri turunun kaynak yolları (fromResults ölçtü) — ekranda
    //: "bu sayı motorun neresinden geldi" diye basılır.
    let lastSuggestion = null;
    //: Carpet izi bu Plotly derlemesinde yoksa nokta haritasına düşülür;
    //: bu durum çipte BEYAN edilir (fea_panel.js ile aynı desen).
    let carpetFallback = false;

    // ------------------------------------------------------------------
    // i18n köprüleri — i18n.js yüklenmemişse İngilizce yedek metin döner
    // (analysis_center.js / fea_panel.js ile birebir aynı köprü).
    // ------------------------------------------------------------------
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback == null ? key : fallback)
            .replace(/\{(\w+)\}/g, function (whole, name) {
                return (params && name in params) ? String(params[name]) : whole;
            });
    }
    //: Sunucudan gelen serbest metin (beyan/gerekçe): sözlükte karşılığı
    //: varsa çevrilir, yoksa AYNEN kalır (asla anahtar, asla boş).
    function SRV(text) {
        return (window.I18N && window.I18N.serverText)
            ? window.I18N.serverText(text) : text;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function isNum(v) {
        return typeof v === 'number' && isFinite(v);
    }

    function fmt(v, digits) {
        return isNum(v) ? v.toFixed(digits === undefined ? 3 : digits) : '—';
    }

    //: Çok küçük/çok büyük sayılar (kalıntı, korunum artığı) için üstel.
    function fmtExp(v, digits) {
        return isNum(v) ? v.toExponential(digits === undefined ? 2 : digits) : '—';
    }

    //: Büyüklüğü önceden bilinmeyen sayı (ör. duvar basıncı marjı).
    //: ÖLÇÜLDÜ (16 Ağu 2026, canlı hibrit sayfası): ıraksayan bir koşuda marj
    //: 4,659024264406486e+25 çıktı ve sabit ondalık biçim bunu rozete OLDUĞU
    //: GİBİ bastı — sayı gizlenmemeli ama okunabilir de olmalı. Bant dışına
    //: çıkınca üstel biçime geçilir; sayı ne kırpılır ne yuvarlanıp saklanır.
    function fmtAuto(v, digits) {
        if (!isNum(v)) return '—';
        const mutlak = Math.abs(v);
        if (mutlak !== 0 && (mutlak >= 1e4 || mutlak < 1e-2)) {
            return v.toExponential(digits === undefined ? 3 : digits);
        }
        return fmt(v, digits === undefined ? 3 : digits);
    }

    //: Anlamlı basamak — Merkez'in ön dolum kuralıyla aynı kaynak.
    function sigFig(value) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.sigFig === 'function') return U.sigFig(value);
        const v = Number(value);
        if (!isFinite(v) || v === 0) return v;
        return Number(v.toPrecision(6));
    }

    //: Yazıya dökülmüş anlamlı basamak. Alan YOKSA 'NaN' basmak yerine em
    //: tire konur: köprü hüküm vermediğinde (bridge_refused) bu alanların
    //: bir kısmı hiç gelmez ve "NaN" kullanıcıya sayı gibi görünürdü.
    function sig(value) {
        return isNum(value) ? String(sigFig(value)) : '—';
    }

    // ==================================================================
    // >>> CFD_PANEL_MODEL_START
    // Saf model katmanı — DOM/Plotly YOK. Bekçi testleri bu bölümü
    // GERÇEK uç yanıtlarıyla doğrudan koşturur.
    // ==================================================================

    //: Motor sözlüğü: hibrit sayfası sonucu {motor: {...}} sarmalıyla
    //: yayımlıyor (ölçüldü), katı/sıvı düz. Sarmal varsa içi, yoksa kendisi.
    function motorDict(results) {
        if (!results || typeof results !== 'object') return null;
        if (results.motor && typeof results.motor === 'object') return results.motor;
        return results;
    }

    //: 'a.b.c' yolunu güvenle okur (ara düğüm yoksa undefined).
    function pick(obj, path) {
        let cur = obj;
        const parts = String(path).split('.');
        for (let i = 0; i < parts.length; i++) {
            if (cur == null || typeof cur !== 'object') return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    // ------------------------------------------------------------------
    // ÖNERİ KAYNAKLARI — her alan için ÖLÇÜLMÜŞ yol listesi, sırayla denenir.
    // İlk tutan yol kazanır ve YOLU da kaydedilir (ekranda yazılır).
    // Uydurma yedek YOKTUR: hiçbir yol tutmazsa alan önerisiz kalır.
    // ------------------------------------------------------------------
    const SUGGESTION_SOURCES = {
        // Hibrit + katı: motorun kendi yarı-1B lüle akışının SI girdileri.
        // Sıvı: quasi1d bloğu yok (ölçüldü) → düz alanlar.
        P0_Pa: [
            { path: 'nozzle_flow_quasi1d.inputs.P0_Pa' },
            { path: 'chamber_pressure', scale: PA_PER_BAR, unit: 'bar → Pa' },
        ],
        T0_K: [
            { path: 'nozzle_flow_quasi1d.inputs.T0_K' },
            { path: 'chamber_temperature' },
        ],
        gamma: [
            { path: 'nozzle_flow_quasi1d.inputs.gamma' },
            { path: 'gamma' },
        ],
        R_J_per_kgK: [
            { path: 'nozzle_flow_quasi1d.inputs.R_J_kgK' },
            { path: 'nozzle_flow_quasi1d.inputs_used.gas_constant_J_kgK' },
            { path: 'molecular_weight', invert: R_UNIVERSAL,
              unit: 'R = 8314,462618 / MW' },
        ],
        // Ayrılma ölçütünün tanımlı olduğu ortam basıncı. ÜÇ motorda ÜÇ
        // ayrı yol (ölçüldü); hiçbiri yoksa öneri yok.
        P_ambient_Pa: [
            { path: 'nozzle_expansion_screen.ambient_pressure_bar',
              scale: PA_PER_BAR, unit: 'bar → Pa' },
            { path: 'nozzle_flow_separation.ambient_pressure_Pa' },
            { path: 'nozzle_design.performance.ambient_pressure',
              scale: PA_PER_BAR, unit: 'bar → Pa' },
        ],
    };

    //: Ucun ZORUNLU saydığı ve panelin form alanı olarak sunduğu büyüklükler
    //: (kontur ayrı: o forma girilmez, sonuçtan gelir).
    const REQUIRED_FIELDS = ['P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK', 'P_ambient_Pa'];

    //: Uygulanabilirlik için sonuçta BULUNMASI gereken gaz büyüklükleri.
    //: P_ortam bilerek DIŞARIDA: motor yayımlamasa bile kullanıcı elle
    //: girebilir, o yüzden satırı gri yapmaz (ama boşsa istek gönderilmez).
    const APPLICABILITY_FIELDS = ['P0_Pa', 'T0_K', 'gamma', 'R_J_per_kgK'];

    //: Alan etiketleri — eksik alan mesajı bunları ADIYLA yazar.
    const FIELD_LABELS = {
        P0_Pa: ['panel.cfd.fieldP0', 'Chamber stagnation pressure P0 [Pa]'],
        T0_K: ['panel.cfd.fieldT0', 'Chamber stagnation temperature T0 [K]'],
        gamma: ['panel.cfd.fieldGamma', 'Ratio of specific heats gamma [-]'],
        R_J_per_kgK: ['panel.cfd.fieldR', 'Specific gas constant R [J/(kg K)]'],
        P_ambient_Pa: ['panel.cfd.fieldPamb', 'Ambient pressure [Pa]'],
        Pb_Pa: ['panel.cfd.fieldPb', 'Back pressure Pb [Pa] — optional'],
        separation_factor: ['panel.cfd.fieldK', 'Summerfield k [-] — optional'],
        resolution: ['panel.cfd.fieldResolution', 'Grid resolution'],
    };

    function fieldLabel(id) {
        const rec = FIELD_LABELS[id];
        return rec ? T(rec[0], rec[1]) : id;
    }

    //: {values, sources} — values yalnız SONLU sayılar taşır, sources
    //: her değerin motorun neresinden geldiğini adlandırır.
    function suggest(results) {
        const m = motorDict(results);
        const values = {};
        const sources = {};
        if (!m) return { values: values, sources: sources };
        Object.keys(SUGGESTION_SOURCES).forEach(function (field) {
            const adaylar = SUGGESTION_SOURCES[field];
            for (let i = 0; i < adaylar.length; i++) {
                const aday = adaylar[i];
                const ham = pick(m, aday.path);
                if (!isNum(ham)) continue;
                let deger = ham;
                if (isNum(aday.scale)) deger = ham * aday.scale;
                if (isNum(aday.invert)) {
                    if (ham === 0) continue;        // 0'a bölme: aday geçersiz
                    deger = aday.invert / ham;
                }
                if (!isNum(deger)) continue;
                values[field] = deger;
                sources[field] = { path: aday.path, unit: aday.unit || null,
                                   raw: ham };
                break;
            }
        });
        return { values: values, sources: sources };
    }

    //: Yayımlanmış kontur bloğu → {points, path} ya da null.
    //: Uç `{'points': [[z_m, r_m], ...]}` biçimini kabul eder; panel şekli
    //: DEĞİŞTİRMEZ, yalnız geçirir (termal panelin ölçülmüş kuralı).
    function pickContour(results) {
        const m = motorDict(results);
        if (!m) return null;
        const blok = m.nozzle_contour;
        if (!blok || typeof blok !== 'object') return null;
        const pts = blok.points;
        if (!Array.isArray(pts) || pts.length < 3) return null;
        for (let i = 0; i < pts.length; i++) {
            const p = pts[i];
            if (!Array.isArray(p) || p.length < 2 || !isNum(p[0]) || !isNum(p[1])) {
                return null;
            }
        }
        return { points: pts, path: 'nozzle_contour.points' };
    }

    // ------------------------------------------------------------------
    // UYGULANABİLİRLİK (çerçeve kural 1) — HER ÇİZİMDE çağrılır: ucuz ve
    // yan etkisiz. İstek atmaz, DOM'a yazmaz, durum değiştirmez.
    // ------------------------------------------------------------------
    function applicability(results) {
        if (!pickContour(results)) {
            return { ok: false, reason: {
                key: 'panel.cfd.needsContour',
                fallback: 'This result publishes no nozzle contour '
                          + '(nozzle_contour.points): the CFD grid is built from '
                          + 'it, so the run cannot start. Re-run the motor '
                          + 'calculation on this page.' } };
        }
        const sug = suggest(results);
        const eksik = APPLICABILITY_FIELDS.filter(function (f) {
            return !isNum(sug.values[f]);
        });
        if (eksik.length) {
            return { ok: false, reason: {
                key: 'panel.cfd.needsGasState',
                params: { fields: eksik.map(fieldLabel).join(', ') },
                fallback: 'This result does not publish the gas state the '
                          + 'solver needs: {fields}. The solver has no default '
                          + 'reservoir state and this panel invents none.' } };
        }
        return { ok: true };
    }

    // ------------------------------------------------------------------
    // POST GÖVDESİ — sayılar FORMDAN, kontur SONUÇTAN.
    // Eksik zorunlu alan varsa istisna atılır: çerçeve isteği GÖNDERMEZ ve
    // mesajı kırmızı beyanla basar (uydurma varsayılan konmaz).
    // ------------------------------------------------------------------
    function buildBody(formValues, results) {
        const v = formValues || {};
        const eksik = REQUIRED_FIELDS.filter(function (f) { return !isNum(v[f]); });
        const kontur = pickContour(results);
        if (!kontur) eksik.push('nozzle_contour');
        if (eksik.length) {
            throw new Error(TF('panel.cfd.missingInputs',
                { fields: eksik.map(fieldLabel).join(', ') },
                'These inputs have no value and the endpoint has no default '
                + 'for any of them: {fields}. The request was NOT sent — this '
                + 'panel does not invent a number in their place.'));
        }
        const body = {};
        REQUIRED_FIELDS.forEach(function (f) { body[f] = v[f]; });
        // İsteğe bağlı alanlar: boşsa GÖNDERİLMEZ (uç "verilmedi" hâlini
        // kendi beyanıyla işler — back_pressure_basis / separation_factor).
        if (isNum(v.Pb_Pa)) body.Pb_Pa = v.Pb_Pa;
        if (isNum(v.separation_factor)) body.separation_factor = v.separation_factor;
        if (v.resolution) body.resolution = String(v.resolution);
        body.nozzle_contour = { points: kontur.points };
        lastSentContour = { points: kontur.points, path: kontur.path };
        return body;
    }

    // ------------------------------------------------------------------
    // HÜKÜM ROZETİ (çerçeve kural 4)
    // ------------------------------------------------------------------
    function verdictOf(data) {
        const cfd = data && data.cfd;
        if (!cfd || typeof cfd !== 'object') return null;   // hüküm beyan edilmez
        if (typeof cfd.converged !== 'boolean') return null;
        if (cfd.converged) {
            return { kind: 'ok', key: 'panel.cfd.verdictConverged',
                     params: { iters: cfd.iterations },
                     fallback: 'CONVERGED ({iters} iterations)' };
        }
        const son = cfd.residual_history ? cfd.residual_history.last : null;
        return { kind: 'warn', key: 'panel.cfd.verdictNotConverged',
                 params: { res: fmtExp(son), iters: cfd.iterations },
                 fallback: 'NOT CONVERGED — residual {res} after {iters} '
                           + 'iterations' };
    }

    // ------------------------------------------------------------------
    // GÖRÜNÜM MODELİ — yanıttan çizilebilir yapıya. Tek dönüşüm Pa → bar.
    // ------------------------------------------------------------------
    function transpose(nested) {
        if (!Array.isArray(nested) || !nested.length) return null;
        if (!Array.isArray(nested[0])) return null;
        const ni = nested.length, nj = nested[0].length;
        const out = [];
        for (let j = 0; j < nj; j++) {
            const satir = [];
            for (let i = 0; i < ni; i++) {
                const row = nested[i];
                satir.push(Array.isArray(row) ? row[j] : null);
            }
            out.push(satir);
        }
        return out;
    }

    function toBar(values) {
        return (values || []).map(function (p) {
            return isNum(p) ? p / PA_PER_BAR : null;
        });
    }

    //: (toBar2d kaldırıldı: alan ızgarasının ölçeklenmesi artık
    //: FIELD_METRICS'in kendi `scale` sütunundan geçen scale2d ile yapılır —
    //: büyüklük başına ikinci bir dönüşüm yolu bırakılmadı.)

    //: Ölçek çarpanı 1 ise ızgara AYNEN döner (yeni dizi bile kurulmaz);
    //: yalnız basınçta (Pa → bar) gerçek bir bölme olur.
    function scale2d(grid, k) {
        if (!Array.isArray(grid)) return null;
        if (k === 1) return grid;
        return grid.map(function (row) {
            return (row || []).map(function (v) {
                return isNum(v) ? v * k : null;
            });
        });
    }

    function metricById(id) {
        for (let i = 0; i < FIELD_METRICS.length; i++) {
            if (FIELD_METRICS[i].id === id) return FIELD_METRICS[i];
        }
        return null;
    }

    //: Bilinmeyen kimlik tabloya düşer (ilk metrik) — uydurma bir büyüklük
    //: adı ekrana çıkmaz.
    function normalizeMetric(id) {
        return metricById(id) ? id : FIELD_METRICS[0].id;
    }

    //: RENK SKALASI TEK KAYNAK: duraklar 3B sahnenin yayımladığı
    //: MotorViz3D.CFD_COLORSCALES tablosundan gelir (Plotly açık durak
    //: dizisi kabul eder). Panelde Plotly skala ADI ('Viridis' gibi)
    //: KULLANILMAZ — ad kullanılsaydı aynı büyüklük 2B'de ve 3B'de farklı
    //: renklenirdi ve tablonun iki tanımı olurdu. Tablo yüklenmemişse
    //: yedek tanım YAZILMAZ: null döner, çağıran nedeni ekrana yazar.
    //: Yükleme sırası bekçisi (üç şablonda motor_viz3d.js ÖNCE):
    //: tests/test_cfd_alan_koprusu.py.
    function metricColorscale(id) {
        const tablo = window.MotorViz3D && window.MotorViz3D.CFD_COLORSCALES;
        const duraklar = tablo ? tablo[id] : null;
        return Array.isArray(duraklar) && duraklar.length ? duraklar : null;
    }

    //: Duvar poliçizgisi ancak bu koşuya GÖNDERİLEN kontur olduğu
    //: ÖLÇÜLDÜĞÜNDE çizilir. Ölçüt: nokta sayısı yanıtın beyanına eşit VE
    //: ızgaranın yayımladığı giriş/çıkış (z, r) uçları konturun ilk/son
    //: noktasıyla birebir. (Uç konturu ni+1 düzgün istasyona yeniden
    //: örnekler, uçları taşımaz — bu yüzden eşitlik tam beklenir.)
    function wallPolyline(cfd) {
        if (!lastSentContour || !cfd || !cfd.inputs || !cfd.grid) return null;
        const pts = lastSentContour.points;
        if (cfd.inputs.contour_points !== pts.length) return null;
        const g = cfd.grid;
        const ilk = pts[0], son = pts[pts.length - 1];
        const uclar = [[g.z_inlet_m, ilk[0]], [g.z_exit_m, son[0]],
                       [g.r_inlet_m, ilk[1]], [g.r_exit_m, son[1]]];
        for (let i = 0; i < uclar.length; i++) {
            const a = uclar[i][0], b = uclar[i][1];
            if (!isNum(a) || !isNum(b)) return null;
            const olcek = Math.max(Math.abs(a), Math.abs(b), 1e-12);
            if (Math.abs(a - b) > 1e-9 * olcek) return null;
        }
        return { z: pts.map(function (p) { return p[0]; }),
                 r: pts.map(function (p) { return p[1]; }) };
    }

    function viewModel(cfd) {
        const sep = cfd.separation || {};
        const wall = cfd.wall_pressure || {};
        const field = cfd.field || {};
        const res = cfd.residual_history || {};
        const vm = {
            converged: cfd.converged,
            convergenceBasis: cfd.convergence_basis || '',
            iterations: cfd.iterations,
            maxIterations: cfd.max_iterations,
            maxIterationsSource: cfd.max_iterations_source,
            maxIterationsBasis: cfd.max_iterations_basis || '',
            runtime: cfd.runtime_s,
            solverRuntime: cfd.solver_runtime_s,
            runtimeBasis: cfd.runtime_basis || '',
            kernel: cfd.kernel_backend,
            kernelBasis: cfd.kernel_backend_basis || '',
            shockColumns: cfd.shock_sensor_columns,
            shockBasis: cfd.shock_sensor_basis || '',
            limiterIter: cfd.limiter_frozen_at_iter,
            limiterCount: cfd.limiter_freeze_count,
            budget: cfd.budget || {},
            throat: cfd.throat || {},
            grid: cfd.grid || {},
            inputs: cfd.inputs || {},
            inlet: cfd.inlet_conditioning || {},
            separation: sep,
            notModelled: cfd.not_modelled,
            assumptions: cfd.assumptions,
            residual: {
                iteration: Array.isArray(res.iteration) ? res.iteration : [],
                value: Array.isArray(res.value) ? res.value : [],
                decimated: !!res.decimated,
                nTotal: res.n_total, nReturned: res.n_returned,
                last: res.last, min: res.min, basis: res._basis || '',
            },
            wall: {
                z: Array.isArray(wall.z_m) ? wall.z_m : [],
                pBar: toBar(wall.pressure_Pa),
                basis: wall._basis || '',
                thresholdBar: isNum(sep.threshold_Pa)
                    ? sep.threshold_Pa / PA_PER_BAR : null,
                sepZ: isNum(sep.separation_z_m) ? sep.separation_z_m : null,
                sepZInterp: isNum(sep.separation_z_interp_m)
                    ? sep.separation_z_interp_m : null,
                sepPBar: isNum(sep.separation_wall_pressure_Pa)
                    ? sep.separation_wall_pressure_Pa / PA_PER_BAR : null,
            },
            sectionAverage: cfd.section_average || {},
            field: null,
            wallLine: wallPolyline(cfd),
        };
        const x = transpose(field.z_m), y = transpose(field.r_m);
        //: Her büyüklük AYNI ızgarada taşınır (ucun _basis beyanı): bir
        //: büyüklüğün yokluğu ötekileri düşürmez. Yükte OLMAYAN büyüklük
        //: null kalır ve 'available' listesine girmez — türetilmez.
        const values = {}, available = [];
        FIELD_METRICS.forEach(function (m) {
            const g = transpose(field[m.payloadKey]);
            values[m.id] = g ? scale2d(g, m.scale) : null;
            if (values[m.id]) available.push(m.id);
        });
        if (x && y && available.length) {
            vm.field = {
                a: Array.isArray(field.axial_indices)
                    ? field.axial_indices : x[0].map(function (_v, i) { return i; }),
                b: Array.isArray(field.radial_indices)
                    ? field.radial_indices : x.map(function (_v, j) { return j; }),
                x: x, y: y, values: values, available: available,
                shape: field.shape, gridShape: field.grid_shape,
                decimated: !!field.decimated,
                nReturned: field.n_cells_returned, nTotal: field.n_cells_total,
                basis: field._basis || '',
            };
        }
        return vm;
    }
    // <<< CFD_PANEL_MODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // Görsel dil — Merkez'in rozet/renk sözlüğüyle aynı değişkenler
    // ------------------------------------------------------------------
    const COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };
    const WALL_COLOR = 'rgba(200,215,230,0.85)';
    const THRESHOLD_COLOR = '#ff8c33';
    const SEP_COLOR = '#ff5d73';

    function kindColor(kind) {
        return COLORS[kind] || COLORS.info;
    }

    //: Rozet — künye (title) çözücünün KENDİ beyan cümlesidir.
    function badge(text, kind, titleAttr) {
        const c = kindColor(kind);
        return '<span data-cfd-badge="' + esc(kind) + '" title="'
            + esc(titleAttr || '') + '" style="border:1px solid ' + c
            + '; color:' + c + '; border-radius:6px; padding:2px 9px;'
            + ' font-family:var(--hd-mono, monospace); font-size:0.68rem;'
            + ' letter-spacing:0.04em; display:inline-block; margin:2px 4px 2px 0;">'
            + esc(text) + '</span>';
    }

    function sectionTitle(key, fallback) {
        return '<div data-i18n="' + esc(key) + '" style="font-family:'
            + 'var(--hd-mono, monospace); font-size:0.68rem; letter-spacing:0.08em;'
            + ' text-transform:uppercase; color:var(--hd-ink-dim, #7d97a5);'
            + ' margin:12px 0 6px;">' + esc(T(key, fallback)) + '</div>';
    }

    //: Sunucu beyanı (basis/gerekçe) — AYNEN basılır, kısaltılmaz.
    function basisText(text) {
        if (!text) return '';
        return '<p data-cfd-basis="1" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; line-height:1.45; color:var(--hd-ink-dim,'
            + ' #7d97a5); margin:6px 0; white-space:pre-wrap;">'
            + esc(SRV(text)) + '</p>';
    }

    function note(text, kind) {
        return '<p style="font-size:0.7rem; margin:6px 0; color:'
            + kindColor(kind || 'dim') + ';">' + esc(text) + '</p>';
    }

    //: İki sütunlu künye tablosu (etiket | değer).
    function kvTable(rows) {
        const body = rows.map(function (r) {
            return '<tr><td style="padding:2px 8px 2px 0; color:'
                + 'var(--hd-ink-dim, #7d97a5); vertical-align:top;">' + esc(r[0])
                + '</td><td style="padding:2px 0; color:var(--hd-ink, #cfe8f2);'
                + ' font-family:var(--hd-mono, monospace);">' + esc(r[1])
                + '</td></tr>';
        }).join('');
        return '<table style="border-collapse:collapse; font-size:0.7rem;'
            + ' width:100%;"><tbody>' + body + '</tbody></table>';
    }

    function plotBox(id, height) {
        return '<div id="' + esc(id) + '" data-cfd-plot="1" style="width:100%;'
            + ' height:' + (height || 280) + 'px;"></div>';
    }

    // ------------------------------------------------------------------
    // Çizimler — hepsi yanıttan; hesap yok, yumuşatma yok, örnekleme yok.
    // ------------------------------------------------------------------
    function wallFigure(vm) {
        const traces = [{
            x: vm.wall.z, y: vm.wall.pBar, mode: 'lines+markers', type: 'scatter',
            line: { width: 2, color: '#00e5ff' }, marker: { size: 4 },
            name: T('panel.cfd.traceWall', 'p_w (solver cells next to the wall)'),
        }];
        // Eşik çizgisi yalnız POZİTİFKEN çizilir: vakumda (P_ortam = 0)
        // eşik 0'dır ve logaritmik eksende 0 gösterilemez — çizgi sessizce
        // kırpılırdı. Sayı gizlenmiyor: eşik künye tablosunda 0 olarak durur
        // ve köprü zaten "ölçüt uygulanamaz" beyanını basar.
        if (isNum(vm.wall.thresholdBar) && vm.wall.thresholdBar > 0
                && vm.wall.z.length) {
            traces.push({
                x: [vm.wall.z[0], vm.wall.z[vm.wall.z.length - 1]],
                y: [vm.wall.thresholdBar, vm.wall.thresholdBar],
                mode: 'lines', type: 'scatter',
                line: { width: 2, dash: 'dash', color: THRESHOLD_COLOR },
                name: TF('panel.cfd.traceThreshold',
                    { k: sigFig(vm.separation.separation_factor),
                      pa: sigFig(vm.separation.ambient_pressure_Pa) },
                    'Separation threshold k*P_ambient (k = {k}, P_ambient = {pa} Pa)'),
            });
        }
        if (isNum(vm.wall.sepZ) && isNum(vm.wall.sepPBar)) {
            traces.push({
                x: [vm.wall.sepZ], y: [vm.wall.sepPBar],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, color: SEP_COLOR, symbol: 'x' },
                name: T('panel.cfd.traceSepPoint',
                        'First separated station (solver cell)'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.cfd.chartWall',
                         'Wall pressure p_w(z) and the separation criterion'),
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisPBar',
                                  'Wall pressure [bar] (log scale)'),
                         type: 'log' },
                height: 300,
                legend: { orientation: 'h', y: -0.28 },
                margin: { t: 40, r: 12, b: 60, l: 60 },
            },
        };
    }

    //: Ekranda GÖSTERİLEBİLEN büyüklük: kullanıcının seçtiği büyüklük bu
    //: yanıtta yoksa (eski uç: temperature_K yok) yükte GERÇEKTEN olan ilk
    //: büyüklüğe düşülür. Düşüş sessiz değildir — `metricNotesHtml` nedeni
    //: adıyla yazar ve uydurma sıcaklık üretilmez.
    function activeMetric(vm) {
        const av = (vm.field && vm.field.available) || [];
        if (av.indexOf(fieldMetric) >= 0) return fieldMetric;
        return av.length ? av[0] : FIELD_METRICS[0].id;
    }

    function fieldValues(vm) {
        return vm.field.values[activeMetric(vm)];
    }

    function fieldTitles(vm) {
        const id = activeMetric(vm);
        const m = metricById(id);
        const metric = T(m.labelKey, m.labelFallback);
        return {
            id: id,
            metric: metric,
            // Başlık BİLEREK kısa: Merkez'in görüntüleyici sütunu dar ve
            // uzun başlık kırpılıyordu (ölçüldü, canlı hibrit sayfası).
            // "eksen r = 0'da, duvar üstte" açıklaması kaybolmadı: alan
            // bloğunun kendi _basis cümlesi grafiğin ALTINDA aynen basılıyor.
            title: TF('panel.cfd.chartField', { metric: metric },
                'Flow field on the solver cells — {metric}'),
            colorscale: metricColorscale(id),
        };
    }

    function wallLineTrace(vm) {
        if (!vm.wallLine) return null;
        return {
            x: vm.wallLine.z, y: vm.wallLine.r, mode: 'lines', type: 'scatter',
            line: { width: 2, color: WALL_COLOR },
            name: T('panel.cfd.traceWallLine',
                    'Nozzle wall (the contour sent to the solver)'),
        };
    }

    function fieldFigure(vm) {
        const f = vm.field;
        const t = fieldTitles(vm);
        const carpetId = 'cfdFieldCarpet' + drawSeq;
        const kontur = {
            type: 'contourcarpet', carpet: carpetId,
            a: f.a, b: f.b, z: fieldValues(vm),
            contours: { coloring: 'fill', showlines: false },
            colorbar: { title: t.metric, titleside: 'right' },
            name: t.metric,
        };
        // Paylaşılan durak tablosu yüklü değilse `colorscale` HİÇ verilmez
        // (yedek tablo yazmak ikinci tanım olurdu); nedeni ekrana yazılır.
        if (t.colorscale) kontur.colorscale = t.colorscale;
        const traces = [{
            type: 'carpet', carpet: carpetId,
            a: f.a, b: f.b, x: f.x, y: f.y,
            aaxis: { showgrid: false, showticklabels: 'none',
                     showticksuffix: 'none', smoothing: 0, title: '' },
            baxis: { showgrid: false, showticklabels: 'none',
                     showticksuffix: 'none', smoothing: 0, title: '' },
        }, kontur];
        const wl = wallLineTrace(vm);
        if (wl) traces.push(wl);
        return {
            traces: traces,
            layout: {
                title: t.title,
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisR', 'Radius r [m]') },
                height: 320, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 60 },
            },
        };
    }

    //: Carpet izi bulunmayan Plotly derlemesinde: hücre merkezi nokta
    //: haritası (fea_panel.js ile aynı yedek). Değerler AYNI, gösterim farklı.
    function fieldFallbackFigure(vm) {
        const f = vm.field;
        const t = fieldTitles(vm);
        const values = fieldValues(vm);
        const x = [], y = [], c = [];
        for (let j = 0; j < f.x.length; j++) {
            for (let i = 0; i < f.x[j].length; i++) {
                x.push(f.x[j][i]); y.push(f.y[j][i]); c.push(values[j][i]);
            }
        }
        const marker = { color: c, size: 6,
                         colorbar: { title: t.metric, titleside: 'right' } };
        if (t.colorscale) marker.colorscale = t.colorscale;
        const traces = [{
            x: x, y: y, mode: 'markers', type: 'scatter',
            marker: marker,
            name: t.metric,
        }];
        const wl = wallLineTrace(vm);
        if (wl) traces.push(wl);
        return {
            traces: traces,
            layout: {
                title: t.title,
                xaxis: { title: T('panel.cfd.axisZ', 'Axial position z [m]') },
                yaxis: { title: T('panel.cfd.axisR', 'Radius r [m]') },
                height: 320, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 60 },
            },
        };
    }

    function residualFigure(vm) {
        return {
            traces: [{
                x: vm.residual.iteration, y: vm.residual.value,
                mode: 'lines', type: 'scatter',
                line: { width: 2, color: '#2dd4a8' },
                name: T('panel.cfd.traceResidual', 'Density L2 residual'),
            }],
            layout: {
                title: T('panel.cfd.chartResidual',
                         'Convergence history — density L2 residual'),
                xaxis: { title: T('panel.cfd.axisIter', 'Iteration') },
                yaxis: { title: T('panel.cfd.axisResidual',
                                  'Residual [rho0*a0/L scale] (log)'),
                         type: 'log' },
                height: 260, showlegend: false,
                margin: { t: 40, r: 12, b: 50, l: 70 },
            },
        };
    }

    function drawFigure(id, figure) {
        const el = document.getElementById(id);
        if (!el || !window.Plotly || typeof window.Plotly.react !== 'function') {
            return false;
        }
        window.Plotly.react(el, figure.traces, figure.layout,
                            { responsive: true, displaylogo: false });
        return true;
    }

    // ------------------------------------------------------------------
    // Rozet şeridi — her rozet BİR beyandır; künyesinde çözücünün cümlesi.
    // ------------------------------------------------------------------
    function badgesHtml(vm) {
        let html = '';
        if (vm.converged === true) {
            html += badge(TF('panel.cfd.badgeConverged', { iters: vm.iterations },
                'CONVERGED — {iters} iterations'), 'ok', SRV(vm.convergenceBasis));
        } else if (vm.converged === false) {
            html += badge(TF('panel.cfd.badgeNotConverged',
                { res: fmtExp(vm.residual.last), iters: vm.iterations },
                'NOT CONVERGED — residual {res} after {iters} iterations'),
                'warn', SRV(vm.convergenceBasis));
        }

        const sep = vm.separation;
        // GÜVEN RENGİ KURALI: köprü hükmünü 'suspect' etiketiyle verdiyse
        // (çözücü oturmadı) o hüküm YEŞİL BASILAMAZ. Rozet kaybolmaz, sayı
        // gizlenmez — yalnız kabul rengi verilmez, çünkü oturmamış bir alana
        // uygulanmış ölçüt "temiz" değildir (aynı kural fea_panel'de ölçülmemiş
        // kalite ölçütü için de uygulanıyor).
        const hukumKesin = !(sep && sep.judgment_confidence === 'suspect');
        if (sep && sep.bridge_refused) {
            html += badge(T('panel.cfd.badgeSepRefused',
                'NO SEPARATION JUDGEMENT — the bridge refused this solution'),
                'dim', SRV(sep.not_applicable_reason || sep._basis || ''));
        } else if (sep && sep.applicable === false) {
            html += badge(T('panel.cfd.badgeSepNotApplicable',
                'SEPARATION CRITERION NOT APPLICABLE'),
                'dim', SRV(sep.not_applicable_reason || ''));
        } else if (sep && sep.separated === true) {
            html += badge(TF('panel.cfd.badgeSeparated',
                { frac: fmt(100 * sep.separated_length_fraction, 1),
                  len: sigFig(sep.separated_length_m),
                  n: sep.stations_below_threshold },
                'FLOW SEPARATION PREDICTED — {frac}% of the divergent length '
                + '({len} m, {n} stations below the threshold)'),
                'warn', SRV(sep.criterion_basis || ''));
        } else if (sep && sep.separated === false) {
            html += badge(TF('panel.cfd.badgeAttached',
                { margin: fmtAuto(sep.wall_pressure_margin_min, 2) },
                'NO SEPARATION — the minimum wall pressure is {margin}x the '
                + 'threshold'), hukumKesin ? 'ok' : 'dim',
                SRV(sep.criterion_basis || ''));
        }
        if (sep && sep.judgment_confidence === 'suspect') {
            html += badge(T('panel.cfd.badgeSepSuspect',
                'SEPARATION JUDGEMENT SUSPECT — the field it was applied to '
                + 'did not settle'), 'warn', SRV(sep.judgment_basis || ''));
        }
        if (sep && sep.reattachment_suspected) {
            html += badge(T('panel.cfd.badgeReattach',
                'REATTACHMENT SUSPECTED'), 'warn',
                SRV(sep.reattachment_basis || ''));
        }
        // BÜTÇE UYARISI (eski Mach eşikli 'INLET ADVISORY' rozetinin halefi).
        // Rozet metni ateşleyen GEREKÇEYİ söyler: "uyarı var" demek yetmez,
        // kullanıcı hangi ölçümün konuştuğunu görmeli. Uyarı bir hüküm
        // değildir; yakınsama rozeti onun yanında BAĞIMSIZ olarak durur
        // (bekçi: aynı ekranda uyarı + CONVERGED birlikte görünebilmeli).
        if (vm.inlet && vm.inlet.budget_advisory) {
            const gerekceler = Array.isArray(vm.inlet.budget_advisory_reasons)
                ? vm.inlet.budget_advisory_reasons : [];
            const bantMi = gerekceler.indexOf('measured_slow_band') >= 0;
            const azMi = gerekceler.indexOf('budget_below_measured_need') >= 0;
            const yakin = vm.inlet.nearest_measured || {};
            let metin;
            if (bantMi && azMi) {
                metin = TF('panel.cfd.badgeBudgetAdvisoryBoth',
                    { cr: fmt(vm.inlet.contraction_ratio, 2),
                      budget: vm.inlet.max_iterations, need: yakin.iterations },
                    'ITERATION BUDGET ADVISORY — measured runs near '
                    + 'contraction ratio {cr} are slow AND the requested '
                    + 'budget ({budget}) is below the measured need ({need})');
            } else if (azMi) {
                metin = TF('panel.cfd.badgeBudgetAdvisoryLow',
                    { budget: vm.inlet.max_iterations, need: yakin.iterations },
                    'ITERATION BUDGET ADVISORY — the requested budget '
                    + '({budget}) is below the measured need of the nearest '
                    + 'measured case ({need} iterations)');
            } else {
                metin = TF('panel.cfd.badgeBudgetAdvisoryBand',
                    { cr: fmt(vm.inlet.contraction_ratio, 2) },
                    'ITERATION BUDGET ADVISORY — measured runs near '
                    + 'contraction ratio {cr} spend most of the budget');
            }
            html += badge(metin, 'warn', SRV(vm.inlet._basis || ''));
        }
        // Korunum artıkları RENKSİZ (info) yayımlanır: ucun yayımladığı bir
        // KABUL EŞİĞİ yok, panelin kendi eşiğini uydurması da yasak.
        html += badge(TF('panel.cfd.badgeMass',
            { v: fmtExp(vm.budget.mass_balance_rel) },
            'MASS IMBALANCE {v} (relative)'), 'info', SRV(vm.budget._basis || ''));
        html += badge(TF('panel.cfd.badgeEnergy',
            { v: fmtExp(vm.budget.energy_balance_rel) },
            'ENERGY IMBALANCE {v} (relative)'), 'info',
            SRV(vm.budget._basis || ''));
        html += badge(TF('panel.cfd.badgeKernel', { backend: vm.kernel },
            'KERNEL {backend}'), 'info', SRV(vm.kernelBasis));
        html += badge(TF('panel.cfd.badgeShock', { n: vm.shockColumns },
            'SHOCK SENSOR — {n} flagged columns'), 'info', SRV(vm.shockBasis));
        if (isNum(vm.limiterIter)) {
            html += badge(TF('panel.cfd.badgeLimiter',
                { iter: vm.limiterIter, n: vm.limiterCount },
                'LIMITER FROZEN at iteration {iter} ({n}x)'), 'info',
                SRV(vm.convergenceBasis));
        } else {
            html += badge(T('panel.cfd.badgeLimiterNever',
                'LIMITER NEVER FROZEN'), 'info', SRV(vm.convergenceBasis));
        }
        html += badge(TF('panel.cfd.badgeRuntime',
            { s: fmt(vm.runtime, 1), solver: fmt(vm.solverRuntime, 1) },
            'RUNTIME {s} s (solver {solver} s)'), 'dim', SRV(vm.runtimeBasis));
        if (carpetFallback) {
            html += badge(T('panel.cfd.badgeCarpetFallback',
                'CONTOUR TRACE UNAVAILABLE — cell point map drawn instead'),
                'dim', '');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // Beyan blokları
    // ------------------------------------------------------------------
    function listBlock(value) {
        if (Array.isArray(value)) {
            return '<ul style="margin:4px 0 0 16px; padding:0; font-size:0.7rem;'
                + ' color:var(--hd-ink, #cfe8f2);">'
                + value.map(function (v) { return '<li>' + esc(SRV(v)) + '</li>'; })
                    .join('') + '</ul>';
        }
        if (value && typeof value === 'object') {
            return kvTable(Object.keys(value).map(function (k) {
                return [k, SRV(String(value[k]))];
            }));
        }
        return '';
    }

    //: Uyarı gerekçesinin okunur karşılığı — SÖZLÜK ANAHTARINA bağlı, ham
    //: makine adı da parantezde kalır (uç yeni bir gerekçe eklerse ekranda
    //: sessizce kaybolmasın diye bilinmeyen ad AYNEN basılır).
    function advisoryReasonText(reason) {
        if (reason === 'measured_slow_band') {
            return T('panel.cfd.reasonSlowBand',
                'the contraction ratio falls in a measured slow band')
                + ' (' + reason + ')';
        }
        if (reason === 'budget_below_measured_need') {
            return T('panel.cfd.reasonBudgetLow',
                'the requested budget is below the measured need')
                + ' (' + reason + ')';
        }
        return String(reason);
    }

    //: Bant kenarı yayımlanmamışsa (tablo orada BİTİYOR) sayı uydurulmaz:
    //: açık uç işareti basılır ve bunun EKSTRAPOLASYON olduğu yazılır.
    function bandText(band) {
        const alt = isNum(band.cr_min) ? fmt(band.cr_min, 2)
            : T('panel.cfd.bandOpen', 'open (beyond the measured table)');
        const ust = isNum(band.cr_max) ? fmt(band.cr_max, 2)
            : T('panel.cfd.bandOpen', 'open (beyond the measured table)');
        return alt + ' … ' + ust;
    }

    function inletHtml(vm) {
        const inlet = vm.inlet || {};
        let html = sectionTitle('panel.cfd.secInlet',
            'Inlet conditioning and the iteration budget advisory (declared '
            + 'by the endpoint)');
        const gerekceler = Array.isArray(inlet.budget_advisory_reasons)
            ? inlet.budget_advisory_reasons : [];
        const satirlar = [
            [T('panel.cfd.rowContraction', 'Contraction ratio A_inlet/A_throat'),
             fmt(inlet.contraction_ratio, 3)],
            [T('panel.cfd.rowInletMach',
               'Isentropic subsonic inlet Mach (information only)'),
             fmt(inlet.inlet_mach_isentropic, 4)],
            [T('panel.cfd.rowInletBc', 'Solver inlet boundary condition'),
             String(inlet.inlet_bc == null ? '—' : inlet.inlet_bc)],
            [T('panel.cfd.rowBudget', 'Iteration budget (effective / source)'),
             String(vm.maxIterations) + ' / '
                + String(vm.maxIterationsSource == null
                         ? '—' : vm.maxIterationsSource)],
            [T('panel.cfd.rowBudgetAdvisory', 'Budget advisory for this run'),
             inlet.budget_advisory
                 ? T('panel.cfd.yes', 'yes') : T('panel.cfd.no', 'no')],
        ];
        if (gerekceler.length) {
            satirlar.push([T('panel.cfd.rowAdvisoryReasons',
                'Why it fired (rules named by the endpoint)'),
                gerekceler.map(advisoryReasonText).join('; ')]);
        }
        const yakin = inlet.nearest_measured;
        if (yakin) {
            satirlar.push([T('panel.cfd.rowNearestMeasured',
                'Nearest measured case (CR / iterations / converged)'),
                fmt(yakin.contraction_ratio, 3) + ' / '
                    + String(yakin.iterations) + ' / '
                    + (yakin.converged ? T('panel.cfd.yes', 'yes')
                                       : T('panel.cfd.no', 'no'))]);
        }
        const bantlar = Array.isArray(inlet.budget_advisory_bands)
            ? inlet.budget_advisory_bands : [];
        bantlar.forEach(function (b) {
            satirlar.push([TF('panel.cfd.rowAdvisoryBand',
                { res: String(b.resolution) },
                'Measured slow band at "{res}" (contraction ratio)'),
                bandText(b)]);
        });
        html += kvTable(satirlar);

        // ÖLÇÜM TABLOSU — uçtan geldiği gibi. Panel bu tabloyu ne üretir ne
        // de özetler; kullanıcı beklentinin dayandığı sayıları görür.
        const tablo = Array.isArray(inlet.measured_expectations)
            ? inlet.measured_expectations : [];
        if (tablo.length) {
            html += sectionTitle('panel.cfd.secMeasuredExpect',
                'Measured convergence table the advisory is derived from');
            html += kvTable(tablo.map(function (row) {
                return [String(row.resolution) + '  CR '
                            + fmt(row.contraction_ratio, 3),
                        String(row.iterations) + ' '
                            + T('panel.cfd.iterationsWord', 'iterations') + ', '
                            + (row.converged
                                ? T('panel.cfd.expectConverged', 'converged')
                                : T('panel.cfd.expectCeiling',
                                    'hit the budget ceiling'))
                            + ', ' + T('panel.cfd.expectResidual', 'residual')
                            + ' ' + fmtExp(row.residual_last, 2)];
            }));
        }
        html += note(T('panel.cfd.notVerdict',
            'This advisory is NOT a verdict and it never blocks a run: it '
            + 'states the pre-run expectation with the measurement behind it. '
            + 'The verdict is the solver\'s own convergence declaration above.'),
            'dim');
        html += basisText(inlet._basis);
        html += basisText(inlet.inlet_bc_basis);
        return html;
    }

    function declarationsHtml(vm) {
        let html = sectionTitle('panel.cfd.secDecl',
            'Declarations — not modelled, assumptions, inputs, grid');
        html += '<div data-cfd-block="not-modelled">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declNotModelled">'
            + esc(T('panel.cfd.declNotModelled', 'NOT MODELLED')) + '</strong>'
            + listBlock(vm.notModelled) + '</div>';
        html += '<div data-cfd-block="assumptions" style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declAssumptions">'
            + esc(T('panel.cfd.declAssumptions', 'ASSUMPTIONS')) + '</strong>'
            + listBlock(vm.assumptions) + '</div>';

        const inp = vm.inputs || {};
        const satirlar = [];
        ['P0_Pa', 'T0_K', 'gamma', 'R_J_kgK', 'P_ambient_Pa', 'Pb_Pa',
         'separation_factor', 'resolution', 'grid_ni', 'grid_nj',
         'contour_field', 'contour_points', 'cfl_start', 'cfl_max',
         'tol_res', 'settle_tol'].forEach(function (k) {
            if (!(k in inp)) return;
            const v = inp[k];
            satirlar.push([k, v === null
                ? T('panel.cfd.notSupplied', 'not supplied')
                : (isNum(v) ? sig(v) : String(v))]);
        });
        html += '<div data-cfd-block="inputs" style="margin-top:8px;">'
            + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim, #7d97a5);"'
            + ' data-i18n="panel.cfd.declInputs">'
            + esc(T('panel.cfd.declInputs',
                    'INPUTS ECHOED BY THE ENDPOINT')) + '</strong>'
            + kvTable(satirlar) + '</div>';
        if (inp.back_pressure_basis) html += basisText(inp.back_pressure_basis);

        // Öneri kaynakları: hangi sayı motorun neresinden geldi.
        if (lastSuggestion && Object.keys(lastSuggestion.sources).length) {
            const kaynak = lastSuggestion.sources;
            html += '<div data-cfd-block="suggestions" style="margin-top:8px;">'
                + '<strong style="font-size:0.7rem; color:var(--hd-ink-dim,'
                + ' #7d97a5);" data-i18n="panel.cfd.declSuggest">'
                + esc(T('panel.cfd.declSuggest',
                        'WHERE THE PRE-FILLED VALUES CAME FROM')) + '</strong>'
                + kvTable(Object.keys(kaynak).map(function (f) {
                    const s = kaynak[f];
                    return [fieldLabel(f),
                            s.path + (s.unit ? ' (' + s.unit + ')' : '')];
                }))
                + note(T('panel.cfd.declSuggestNote',
                    'These are the suggestion sources measured at the last '
                    + 'refresh. The values actually used are the ones echoed '
                    + 'above — the request is always built from the fields on '
                    + 'screen, so an edited field wins over its suggestion.'),
                    'dim')
                + '</div>';
        }

        const g = vm.grid || {};
        const seviye = g.levels || {};
        const seviyeSatir = Object.keys(seviye).map(function (ad) {
            const s = seviye[ad] || {};
            const w = s.worst_case_s || {};
            return [ad + (ad === g.resolution ? ' *' : ''),
                    s.ni + 'x' + s.nj + ' = ' + s.n_cells
                        + ' cells; worst case '
                        + Object.keys(w).map(function (b) {
                            return b + ' ' + w[b] + ' s';
                        }).join(', ')];
        });
        html += sectionTitle('panel.cfd.secGrid',
            'Grid and the resolution whitelist (measured worst-case runtimes)');
        html += kvTable([
            [T('panel.cfd.rowResolution', 'Resolution used'),
             String(g.resolution)],
            [T('panel.cfd.rowCells', 'Cells (axial x radial)'),
             g.ni + ' x ' + g.nj + ' = ' + g.n_cells],
            [T('panel.cfd.rowThroat', 'Throat: z, radius, section-average Mach'),
             sig(vm.throat.z_m) + ' m, ' + sig(vm.throat.radius_m) + ' m, '
                + fmtAuto(vm.throat.mach_section_avg, 4)],
        ].concat(seviyeSatir));
        html += basisText(g._basis);
        return html;
    }

    function convergenceHtml(vm, plotId) {
        let html = sectionTitle('panel.cfd.secConv',
            'Convergence history and the conservation budget');
        html += plotBox(plotId, 260);
        html += kvTable([
            [T('panel.cfd.rowIterations', 'Iterations / budget (source)'),
             vm.iterations + ' / ' + vm.maxIterations + ' ('
                + String(vm.maxIterationsSource == null
                         ? '—' : vm.maxIterationsSource) + ')'],
            [T('panel.cfd.rowResLast', 'Last residual (exact)'),
             fmtExp(vm.residual.last, 4)],
            [T('panel.cfd.rowResMin', 'Smallest residual (exact)'),
             fmtExp(vm.residual.min, 4)],
            [T('panel.cfd.rowMassIn', 'Mass flow in / out [kg/s]'),
             sig(vm.budget.mass_flow_in_kg_s) + ' / '
                + sig(vm.budget.mass_flow_out_kg_s)],
            [T('panel.cfd.rowWallFlux', 'Wall mass flux [kg/s] (slip wall: 0)'),
             fmtExp(vm.budget.wall_mass_flux_kg_s, 3)],
        ]);
        if (vm.residual.decimated) {
            html += note(TF('panel.cfd.residualDecimated',
                { n: vm.residual.nReturned, total: vm.residual.nTotal },
                'The residual history is drawn thinned: {n} of {total} points. '
                + 'The two numbers thinning could hide (last and smallest '
                + 'residual) are printed above exactly, from the response.'),
                'dim');
        }
        html += basisText(vm.convergenceBasis);
        html += basisText(vm.maxIterationsBasis);
        return html;
    }

    // ------------------------------------------------------------------
    // Alan büyüklüğü seçici + yokluk beyanları
    // ------------------------------------------------------------------

    //: Üç büyüklük de HER ZAMAN listelenir. Yükte olmayan büyüklük
    //: `disabled` (gri) gelir ve nedeni ADIYLA altta yazılır — seçenek
    //: sessizce GİZLENMEZ ve o büyüklük Mach'tan/basınçtan TÜRETİLMEZ.
    function metricSelectHtml(vm, selId) {
        const aktif = activeMetric(vm);
        const av = vm.field.available;
        const secenekler = FIELD_METRICS.map(function (m) {
            const yok = av.indexOf(m.id) < 0;
            return '<option value="' + esc(m.id) + '"'
                + (m.id === aktif ? ' selected' : '')
                + (yok ? ' disabled' : '')
                + ' data-cfd-metric-option="' + esc(m.id) + '"'
                + ' data-i18n="' + esc(m.labelKey) + '">'
                + esc(T(m.labelKey, m.labelFallback)) + '</option>';
        }).join('');
        return '<label for="' + esc(selId) + '" style="font-size:0.68rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); margin-right:6px;"'
            + ' data-i18n="panel.cfd.toggleField">'
            + esc(T('panel.cfd.toggleField', 'Field variable')) + '</label>'
            + '<select id="' + esc(selId) + '" data-cfd-metric="1"'
            + ' style="font-size:0.7rem;">' + secenekler + '</select>';
    }

    //: Seçicinin altındaki beyanlar: (a) yükte olmayan her büyüklük ADIYLA
    //: ve yük anahtarıyla, (b) seçili büyüklük yoksa hangisine düşüldüğü,
    //: (c) renk duraklarının kaynağı (paylaşılan tablo) ya da yokluğu.
    function metricNotesHtml(vm) {
        let html = '';
        const av = vm.field.available;
        FIELD_METRICS.forEach(function (m) {
            if (av.indexOf(m.id) >= 0) return;
            html += note(TF('panel.cfd.metricUnavailable',
                { label: T(m.labelKey, m.labelFallback), key: m.payloadKey },
                'This response carries no "{key}" array, so "{label}" is '
                + 'offered greyed out. It is NOT rebuilt from the other '
                + 'quantities: reconstructing it would be a different number '
                + 'than the solver\'s own field.'), 'warn');
        });
        const aktif = activeMetric(vm);
        if (aktif !== fieldMetric) {
            const secili = metricById(fieldMetric);
            html += note(TF('panel.cfd.metricFellBack',
                { wanted: secili ? T(secili.labelKey, secili.labelFallback)
                                 : fieldMetric,
                  shown: T(metricById(aktif).labelKey,
                           metricById(aktif).labelFallback) },
                'The selected quantity "{wanted}" is not in this response, so '
                + '"{shown}" is drawn instead.'), 'warn');
        }
        if (metricColorscale(aktif)) {
            html += note(T('panel.cfd.colorSource',
                'The colour stops are the table published by the 3D scene '
                + '(MotorViz3D.CFD_COLORSCALES), so the same value gets the '
                + 'same colour in this map and in the 3D section.'), 'dim');
        } else {
            html += note(T('panel.cfd.colorSourceMissing',
                'The shared colour table (motor_viz3d.js) is not loaded on '
                + 'this page, so the map is drawn without an explicit colour '
                + 'scale and its colours will NOT match the 3D section. No '
                + 'second copy of the table is kept here.'), 'warn');
        }
        return html;
    }

    // ------------------------------------------------------------------
    // 3B KÖPRÜSÜ — aynı yanıtı 3B sahnenin kesit kamasına bindirir
    // ------------------------------------------------------------------

    //: Sahnenin köprü için hazır olup olmadığı. Hazır değilse eylem
    //: KAPALI gösterilir ve nedeni yazılır (görünmez düğme = sessiz kusur).
    function viz3dReadiness() {
        const V = window.MotorViz3D;
        if (!V || typeof V.setCfdField !== 'function') {
            return { ok: false, key: 'panel.cfd.viz3dNoModule',
                fallback: 'The 3D scene module (motor_viz3d.js) is not loaded '
                    + 'on this page, so the field cannot be sent to it.' };
        }
        if (typeof V.isSupported === 'function' && !V.isSupported()) {
            return { ok: false, key: 'panel.cfd.viz3dNoWebgl',
                fallback: 'This browser reports no WebGL support, so the 3D '
                    + 'scene cannot show the field.' };
        }
        return { ok: true, key: '', fallback: '' };
    }

    //: RED sözlüğünü okunur metne çevirir. METİN SAHNENİN KENDİSİNDEN gelir
    //: (reason.key + reason.fallback) — panelde ikinci bir mesaj tanımı yok.
    //: Kod ayrıca AÇIKÇA basılır; tanınmayan kod ADIYLA beyan edilir.
    function viz3dReasonText(reason) {
        if (!reason || typeof reason !== 'object') {
            return T('panel.cfd.viz3dNoReason',
                'The 3D scene refused the field but returned no reason block.');
        }
        const kod = String(reason.code == null ? '' : reason.code);
        let metin = reason.key
            ? T(reason.key, reason.fallback || kod)
            : String(reason.fallback || kod);
        if (VIZ3D_REASON_CODES.indexOf(kod) < 0) {
            metin = TF('panel.cfd.viz3dUnknownCode', { code: kod || '?' },
                'The 3D scene returned a refusal code this panel does not '
                + 'know ({code}); its own text follows.') + ' ' + metin;
        }
        const p = reason.params;
        const parcalar = [];
        if (p && typeof p === 'object') {
            Object.keys(p).forEach(function (k) {
                parcalar.push(k + '=' + String(p[k]));
            });
        }
        return '[' + (kod || '?') + '] ' + metin
            + (parcalar.length ? ' (' + parcalar.join(', ') + ')' : '');
    }

    //: Başarılı bindirmenin beyanı — NE gösterildiği sahnenin KENDİ dönüş
    //: sözlüğünden okunur (panel hiçbir sayıyı yeniden hesaplamaz).
    function viz3dOkLines(res) {
        const m = metricById(res.metric);
        const satirlar = [TF('panel.cfd.viz3dShown',
            { metric: m ? T(m.labelKey, m.labelFallback) : String(res.metric),
              min: sig(res.range && res.range.min),
              max: sig(res.range && res.range.max),
              unit: String(res.unitLabel || ''),
              shown: res.stations ? res.stations.shown : '—',
              total: res.stations ? res.stations.total : '—',
              nz: res.cells ? res.cells.axial : '—',
              nr: res.cells ? res.cells.radial : '—' },
            'The 3D section now carries {metric}: {min} … {max} {unit}, '
            + '{nz}x{nr} solver cells over {shown} of {total} axial stations.')];
        if (res.metric === 'pressure') {
            satirlar.push(T('panel.cfd.viz3dUnitNote',
                'The 3D scene labels pressure in the payload unit (Pa); the '
                + '2D map above divides the same numbers by 1 bar.'));
        }
        if (res.decimated) {
            satirlar.push(T('panel.cfd.viz3dDecimated',
                'The field was thinned by the endpoint before it was sent, and '
                + 'the 3D section shows exactly the cells that arrived.'));
        }
        if (res.cutaway_forced) {
            satirlar.push(T('panel.cfd.viz3dCutaway',
                'Cutaway view was switched on: the field lies inside opaque '
                + 'metal and would not be visible otherwise.'));
        }
        if (Array.isArray(res.decor_hidden) && res.decor_hidden.length) {
            satirlar.push(TF('panel.cfd.viz3dDecorHidden',
                { list: res.decor_hidden.join(', ') },
                'Decorative layers that overlap the field were hidden while it '
                + 'is shown: {list}.'));
        }
        if (res.alignment) {
            satirlar.push(TF('panel.cfd.viz3dAlignment',
                { dzi: sig(res.alignment.dz_inlet_mm),
                  dze: sig(res.alignment.dz_exit_mm),
                  drt: sig(res.alignment.dr_throat_mm),
                  dre: sig(res.alignment.dr_exit_mm) },
                'Measured anchor deviation against the scene contour [mm]: '
                + 'inlet z {dzi}, exit z {dze}, throat r {drt}, exit r {dre}.'));
        }
        return satirlar;
    }

    function viz3dHtml(vm, btnId, clearId, statusId) {
        const hazir = viz3dReadiness();
        let html = sectionTitle('panel.cfd.secViz3d',
            'Show this field in the 3D scene');
        const kapali = hazir.ok ? '' : ' disabled';
        html += '<button type="button" id="' + esc(btnId) + '"'
            + ' data-cfd-viz3d="show"' + kapali
            + ' style="font-size:0.7rem; margin-right:6px;"'
            + ' data-i18n="panel.cfd.viz3dShowBtn">'
            + esc(T('panel.cfd.viz3dShowBtn', 'Show in the 3D scene'))
            + '</button>';
        html += '<button type="button" id="' + esc(clearId) + '"'
            + ' data-cfd-viz3d="clear"' + kapali
            + ' style="font-size:0.7rem;"'
            + ' data-i18n="panel.cfd.viz3dClearBtn">'
            + esc(T('panel.cfd.viz3dClearBtn', 'Remove it from the 3D scene'))
            + '</button>';
        html += '<p data-cfd-viz3d-status="1" id="' + esc(statusId) + '"'
            + ' style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; line-height:1.45; margin:6px 0; color:'
            + (hazir.ok ? COLORS.dim : COLORS.warn) + ';">'
            + esc(hazir.ok
                ? T('panel.cfd.viz3dIdle',
                    'The field is drawn in 2D above. Pressing the button sends '
                    + 'the SAME response to the 3D section; nothing is '
                    + 'recomputed.')
                : T(hazir.key, hazir.fallback))
            + '</p>';
        return html;
    }

    //: Köprü düğmelerinin kablosu. Sahne dönüşü NE İSE o yazılır; "olmadı"
    //: gibi uydurma bir mesaj üretilmez.
    function bindViz3d(root, cfd, vm, btnId, clearId, statusId) {
        const durumEl = document.getElementById(statusId);
        const yaz = function (metin, kind) {
            if (!durumEl) return;
            durumEl.textContent = metin;
            durumEl.style.color = kindColor(kind);
        };
        const goster = document.getElementById(btnId);
        const temizle = document.getElementById(clearId);
        if (!viz3dReadiness().ok) return;
        if (goster && goster.addEventListener) {
            goster.addEventListener('click', function () {
                const V = window.MotorViz3D;
                let res = V.setCfdField(cfd);
                if (res && res.ok) {
                    // 2B'de seçili büyüklük yükte varsa 3B de ONU göstersin:
                    // iki görünüm aynı büyüklüğe aynı rengi verir.
                    const istenen = activeMetric(vm);
                    if (res.metric !== istenen) {
                        const ikinci = V.setCfdMetric(istenen);
                        if (ikinci && ikinci.ok) res = ikinci;
                    }
                }
                if (res && res.ok) {
                    yaz(viz3dOkLines(res).join(' '), 'ok');
                } else {
                    yaz(viz3dReasonText(res && res.reason), 'warn');
                }
            });
        }
        if (temizle && temizle.addEventListener) {
            temizle.addEventListener('click', function () {
                const kalkti = window.MotorViz3D.clearCfdField();
                yaz(kalkti
                    ? T('panel.cfd.viz3dCleared',
                        'The field layer was removed from the 3D scene and the '
                        + 'decorative layers came back.')
                    : T('panel.cfd.viz3dNothingToClear',
                        'The 3D scene carried no field layer, so nothing was '
                        + 'removed.'), 'dim');
            });
        }
    }

    // ------------------------------------------------------------------
    // Çizim — Merkez'in görüntüleyici kabına
    // ------------------------------------------------------------------
    function purge(root) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.purgePlots === 'function') U.purgePlots(root);
    }

    function drawInto(root, cfd) {
        if (!root) return;
        purge(root);
        drawSeq += 1;
        carpetFallback = false;
        const vm = viewModel(cfd);
        const wallId = 'cfd_wall_' + drawSeq;
        const fieldId = 'cfd_field_' + drawSeq;
        const resId = 'cfd_res_' + drawSeq;
        const selId = 'cfd_metric_' + drawSeq;
        const viz3dBtnId = 'cfd_viz3d_show_' + drawSeq;
        const viz3dClearId = 'cfd_viz3d_clear_' + drawSeq;
        const viz3dStatusId = 'cfd_viz3d_status_' + drawSeq;

        let html = '<div data-cfd-badges="1">' + badgesHtml(vm) + '</div>';

        // 1) Duvar basıncı + ayrılma ölçütü
        html += sectionTitle('panel.cfd.secWall',
            'Wall pressure p_w(z) against the separation criterion');
        html += plotBox(wallId, 300);
        const sep = vm.separation || {};
        const sepRows = [
            [T('panel.cfd.rowThreshold', 'Threshold k*P_ambient [Pa]'),
             sig(sep.threshold_Pa)],
            [T('panel.cfd.rowFactor', 'Summerfield k (source)'),
             fmt(sep.separation_factor, 3) + ' ('
                + String(sep.separation_factor_source == null
                         ? '—' : sep.separation_factor_source) + ')'],
            [T('panel.cfd.rowWallMin', 'Minimum wall pressure [Pa] / margin'),
             sig(sep.wall_pressure_min_Pa) + ' / '
                + fmtAuto(sep.wall_pressure_margin_min, 3)],
        ];
        if (isNum(sep.separation_z_m)) {
            sepRows.push([T('panel.cfd.rowSepStation',
                'First separated station z [m] (cell / interpolated)'),
                sig(sep.separation_z_m) + ' / '
                    + sig(sep.separation_z_interp_m)]);
            sepRows.push([T('panel.cfd.rowSepLength',
                'Separated length [m] / fraction of the divergent section'),
                sig(sep.separated_length_m) + ' / '
                    + fmt(sep.separated_length_fraction, 4)]);
        }
        html += kvTable(sepRows);
        html += basisText(vm.wall.basis);
        html += basisText(sep.criterion_basis);
        html += basisText(sep.judgment_basis);
        if (sep.not_applicable_reason) html += basisText(sep.not_applicable_reason);

        // 2) Alan haritası
        html += sectionTitle('panel.cfd.secField',
            'Flow field on the solver cells');
        if (vm.field) {
            html += metricSelectHtml(vm, selId);
            html += plotBox(fieldId, 320);
            html += metricNotesHtml(vm);
            if (vm.field.decimated) {
                html += note(TF('panel.cfd.fieldDecimated',
                    { n: vm.field.nReturned, total: vm.field.nTotal },
                    'The field block is drawn thinned in the AXIAL direction '
                    + 'only: {n} of {total} cells were returned and the kept '
                    + 'indices come from the response, so no cell is invented '
                    + 'and the wall-adjacent row stays intact.'), 'dim');
            }
            if (!vm.wallLine) {
                html += note(T('panel.cfd.wallLineMissing',
                    'The nozzle wall polyline is not drawn: the contour in hand '
                    + 'is not measurably the one this stored run was solved on '
                    + '(point count or inlet/exit stations differ). The solver '
                    + 'cells above are drawn as returned.'), 'dim');
            }
            html += basisText(vm.field.basis);
            // 2a) Aynı yanıtı 3B sahneye bindirme köprüsü
            html += viz3dHtml(vm, viz3dBtnId, viz3dClearId, viz3dStatusId);
        } else {
            html += note(T('panel.cfd.fieldMissing',
                'This response carries no field block, so no field map is '
                + 'drawn.'), 'warn');
        }

        // 3) Yakınsama + bütçe
        html += convergenceHtml(vm, resId);
        // 4) Koşu öncesi giriş koşullandırma beyanı
        html += inletHtml(vm);
        // 5) Beyanlar (modellenmeyenler, varsayımlar, girdi yankısı, ızgara)
        html += declarationsHtml(vm);

        root.innerHTML = html;

        // Çizimler — Plotly yoksa grafik kutusu boş kalır ve neden yazılır.
        if (!window.Plotly || typeof window.Plotly.react !== 'function') {
            const uyari = document.createElement('p');
            uyari.setAttribute('data-cfd-noplotly', '1');
            uyari.style.color = COLORS.dim;
            uyari.style.fontSize = '0.7rem';
            uyari.textContent = T('panel.cfd.noPlotly',
                'The plotting library is not loaded on this page, so the charts '
                + 'are not drawn; every number above comes from the same '
                + 'response.');
            root.appendChild(uyari);
        } else {
            if (vm.wall.z.length) drawFigure(wallId, wallFigure(vm));
            if (vm.field) {
                try {
                    drawFigure(fieldId, fieldFigure(vm));
                } catch (e) {
                    // Carpet izi bu derlemede yok: nokta haritasına düşülür
                    // ve rozet şeridi bu BEYANLA tazelenir (sessiz düşüş yok).
                    carpetFallback = true;
                    drawFigure(fieldId, fieldFallbackFigure(vm));
                    const kap = root.querySelector
                        ? root.querySelector('[data-cfd-badges]') : null;
                    if (kap) kap.innerHTML = badgesHtml(vm);
                }
            }
            if (vm.residual.iteration.length) {
                drawFigure(resId, residualFigure(vm));
            }
        }

        // Alan büyüklüğü değiştiricisi: aynı yanıt yeniden çizilir
        // (yeni istek YOK, yeni sayı YOK).
        const sel = document.getElementById(selId);
        if (sel && sel.addEventListener) {
            sel.addEventListener('change', function () {
                fieldMetric = normalizeMetric(sel.value);
                drawInto(root, cfd);
            });
        }
        if (vm.field) {
            bindViz3d(root, cfd, vm, viz3dBtnId, viz3dClearId, viz3dStatusId);
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
    }

    function render(data, root) {
        if (!root) return;
        const cfd = data && data.cfd;
        if (!cfd || typeof cfd !== 'object') {
            root.innerHTML = '<p data-cfd-nodata="1" style="font-size:0.72rem;'
                + ' color:var(--hd-red, #ff5d73);">'
                + esc(T('panel.cfd.noBlock',
                    'The response carries no "cfd" block, so nothing is drawn. '
                    + 'Nothing is inferred in its place.')) + '</p>';
            return;
        }
        drawInto(root, cfd);
    }

    // ==================================================================
    // KİRACI KAYDI — analysis_center.js başındaki sözleşme
    // ==================================================================
    const SPEC = {
        componentId: 'nozzle_flow',
        analysisId: 'cfd',
        // Başlık ve anahtar §2 matrisinin satırıyla AYNI (ayrışmasın diye).
        title: 'CFD (Euler, shock capturing, p_w separation call)',
        titleKey: 'ac.an.cfd',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'solid', 'liquid'],
        long: true,

        applicability: applicability,

        // ALANLAR — hiçbirinin SONLU varsayılanı yok: öneri gelmeyen alan
        // boş kalır ve body() isteği durdurur (uydurma sayı gösterilmez).
        fields: [
            ['P0_Pa', 'Chamber stagnation pressure P0 [Pa]', '', 'any',
             'panel.cfd.fieldP0'],
            ['T0_K', 'Chamber stagnation temperature T0 [K]', '', 'any',
             'panel.cfd.fieldT0'],
            ['gamma', 'Ratio of specific heats gamma [-]', '', 'any',
             'panel.cfd.fieldGamma'],
            ['R_J_per_kgK', 'Specific gas constant R [J/(kg K)]', '', 'any',
             'panel.cfd.fieldR'],
            ['P_ambient_Pa', 'Ambient pressure [Pa]', '', 'any',
             'panel.cfd.fieldPamb'],
            ['Pb_Pa', 'Back pressure Pb [Pa] — optional', '', 'any',
             'panel.cfd.fieldPb'],
            ['separation_factor', 'Summerfield k [-] — optional', '', 'any',
             'panel.cfd.fieldK'],
            ['resolution', 'Grid resolution', 'coarse',
             [['coarse', 'Coarse', 'panel.cfd.resCoarse'],
              ['standard', 'Standard', 'panel.cfd.resStandard']],
             'panel.cfd.fieldResolution'],
        ],

        fromResults: function (results) {
            const sug = suggest(results);
            lastSuggestion = sug;
            return sug.values;
        },

        body: buildBody,
        render: render,
        verdict: verdictOf,
    };

    if (window.AnalysisCenter && typeof window.AnalysisCenter.register === 'function') {
        window.AnalysisCenter.register(SPEC);
    } else if (window.console && console.warn) {
        console.warn('[CfdPanel] window.AnalysisCenter yok: kiracı kaydolamadı. '
            + 'Yükleme sırası analysis_center.js -> panels/cfd_panel.js olmalı.');
    }

    // Test / hata ayıklama yüzeyi — saf model katmanı DOM'suz koşulabilir.
    window.CfdPanel = {
        spec: SPEC,
        endpoint: ENDPOINT,
        _suggest: suggest,
        _pickContour: pickContour,
        _applicability: applicability,
        _buildBody: buildBody,
        _verdict: verdictOf,
        _viewModel: viewModel,
        _render: render,
        _setFieldMetric: function (m) {
            fieldMetric = normalizeMetric(m);
        },
        _getFieldMetric: function () { return fieldMetric; },
        _metrics: FIELD_METRICS,
        _reasonCodes: VIZ3D_REASON_CODES,
        _colorscale: metricColorscale,
        _viz3dReasonText: viz3dReasonText,
        _viz3dReadiness: viz3dReadiness,
        _sources: SUGGESTION_SOURCES,
        PA_PER_BAR: PA_PER_BAR,
        R_UNIVERSAL: R_UNIVERSAL,
    };
})();
