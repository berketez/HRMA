/* ====================================================================
   HRMA Analiz Merkezi — KARARLILIK kiracısı (F2c)
   --------------------------------------------------------------------
   Tasarım belgesi: docs/mimari/f2-yanma-tepkisi-tasarimi.md §6 (F2c satırı)
   + §8.1 Berke kararları (özellikle karar 1: hüküm rozeti KAPSAM ETİKETİ
   olmadan yayımlanamaz — çıplak STABLE yasak).

   Bu dosya Merkez'in (analysis_center.js) İKİ satırına birden kiracı olur:

     1) chamber_acoustics × acoustic_modes
        Frekans ekseni üstünde MOD HARİTASI (bant sınıflarıyla) + mod başına
        SÖNÜM BÜTÇESİ çubuğu. Mod tablosu MOTOR SONUCUNDAN okunur (uydurma
        yok); koşum tarafı UC'un mode='damping' yoludur (lüle sönümü +
        bütçe, hrma/stability çekirdeğinin sözlükleri AYNEN).
     2) chamber_acoustics × combustion_stability
        Chug ÇEVRİMİ: Workbench alanları (J, τ, τ_c, opsiyonel besleme
        hattı) → POST mode='chug' → n-τ NÖTR EĞRİSİ üstünde işletme noktası
        + KÖK YER EĞRİSİ (σ–f düzlemi). Hüküm rozeti assessment.verdict'ten
        ve DAİMA verdict_scope ile birlikte basılır.

   UC SÖZLEŞMESİ (A2 uygular, bu panel tüketir):
     POST /api/analysis/combustion-stability   (ikizi: thermal-protection)
       mode='chug'    → {status:'ok', mode:'chug', assessment: assess_chug()
                         AYNEN, neutral_curve:{dp_ratio_j[],tau_over_tau_c[]},
                         root_locus:{dp_ratio_j[],sigma_1_s[],frequency_hz[]},
                         operating_point:{dp_ratio_j,tau_over_tau_c},
                         skipped_points:[...]}
       mode='damping' → {status:'ok', mode:'damping',
                         nozzle: nozzle_damping_quasi_steady() AYNEN,
                         budget: damping_budget([lüle]) AYNEN}

   ÖLÇÜLMÜŞ VERİ YOLLARI (17 Ağu 2026, üç motorun gerçek koşumları;
   bekçiler tests/test_stability_panel.py içinde aynı yolları motorun kendi
   sonucundan türeterek kilitler):
     * Akustik mod tablosu:
         hibrit  results.motor.acoustic_modes                (status 'modelled')
         katı    results.acoustic_modes                      (status 'computed')
         sıvı    results.combustion_analysis.stability_analysis.acoustic_modes
                                                             (status 'modelled')
       Üçü de merkezî hrma.analysis.acoustic_modes çıktısıdır (parti 27
       F2b-2 göçü: sıvı da artık aynı modülü çağırıyor) ve 'inputs'
       yankısında chamber_length/gamma taşır.
     * Hibrit LFI frekansı: combustion_stability.lfi.frequency_hz (yalnız
       status 'modelled' iken işaretlenir).
     * Chug çevrimi frekansı: sıvıda combustion_analysis.stability_analysis.
       chug_loop.frequency_hz, hibritte combustion_stability.chug_loop.
       frequency_hz (v2.6.27 hibrit chug bağlaması) — yalnız modelled VE
       pozitifse işaretlenir (f = 0 salınımsız kök: log eksene konmaz).
     * Mod başına sönüm satırları: combustion_stability.
       acoustic_response_threshold.modes[] (hibrit + katı; her satırda
       'damping' terim sözlüğü ve R_crit). SIVI bu bloğu YAYIMLAMIYOR
       (ölçüldü) → çubuk bölümü GRİ + gerekçe, sayı uydurulmaz.
     * Chug alan önerileri: sıvıda ve hibritte kendi chug_loop.inputs
       yankısından (J/τ/τ_c/τ_f); katıda yalnız
       combustion_stability.chamber_time_constant.tau_c_s var, J ve τ
       önerisiz kalır. Kaynağı olmayan alan BOŞ kalır — uydurma yok.

   SAHTE VERİ / SAHTE İLERLEME YASAĞI
     * setInterval / setTimeout / requestAnimationFrame / Math.random YOK.
     * Hiçbir alanın SONLU VARSAYILANI yok: öneri bulunamayan alan boş
       kalır ve body() isteği HİÇ GÖNDERMEZ, eksikleri adıyla yazar.
     * Çizilen her sayı ya UC yanıtından ya da motor sonucunun koşum
       anında alınan anlık görüntüsünden gelir; izlerde sayısal literal
       YOKTUR (bekçi regex ile tarar).
     * Mod haritası ve sönüm çubukları YALNIZ, saklanan koşunun yankıladığı
       ses hızı + kavite boyu eldeki akustik tabloyla ölçülebilir biçimde
       eşleşiyorsa çizilir (cfd_panel duvar poliçizgisi disipliniyle aynı);
       eşleşmiyorsa GRİ + gerekçe. Geçmişten gelen bir koşuya bugünkü mod
       tablosu giydirilmez.

   HÜKÜM DİSİPLİNİ (karar 1 + hrma/stability yapısal kuralı)
     * chug: hüküm assessment.verdict'ten gelir ve rozet metni HER ZAMAN
       verdict_scope'u taşır. Yanıt kapsamsız hüküm getirirse çıplak hüküm
       BASILMAZ; "kapsamsız hüküm bastırıldı" beyanı basılır.
     * damping/akustik: bu yolda hüküm YOKTUR (forbid_verdict_key ile
       çekirdekte yapısal). Kiracının verdict() işlevi null döner; çerçeve
       "hüküm beyan edilmedi" rozetini basar, sahte 'ok' üretilmez.

   KULLANILABİLİRLİK (parti 29 A1 — ekran görüntüsünden ölçülen 4 kusur)
     * K1: mod haritası etiketleri iz metni DEĞİL, layoutModeLabels() saf
       yerleşim fonksiyonunun kademelendirdiği kısa yönlendirme çizgili
       Plotly notlarıdır — aynı x-komşuluğuna düşen etiket kutuları
       (ÖLÇÜLEN metin genişliğiyle) kesişmez; tam üst üste düşen imlerin
       etiketleri de farklı kademelere ayrılır. İzin x/y/text dizileri
       motor tablosunun KENDİSİ olarak kalır (dondurulmuş bekçi sözleşmesi:
       im frekansın kendisinde durur, oynatmak sahte veri olurdu).
     * K2: eksen marjları ve sütun genişlikleri ÖLÇÜLEN metinden türetilir
       (measureLabelPx: tarayıcıda gerçek canvas measureText, testte fontun
       kendi 0,6 em ilerleme metriği); uzun y-ekseni başlıkları kullanılan
       yüksekliğe göre satırlara sarılır. Sabit piksel tahmini yok.
     * K3: beyan/dayanak metin duvarları VARSAYILAN KAPALI <details>
       bloklarındadır; <summary> başlık + VERİDEN türeyen tek satır özet
       taşır. İçerik DOM'da AYNEN durur (kaynak-tarama bekçileri
       etkilenmez); hüküm rozetleri ve sayı tabloları KATLANMAZ.
     * K4: veri metni (sayılar, mod adları, birimler) --hd-ink; yalnız
       ikincil açıklama metni --hd-ink-dim kalır. WCAG bekçisi kontrastı
       theme.css jetonlarından hesaplar (veri >= 7:1, açıklama >= 4.5:1).

   Bekçiler: tests/test_stability_panel.py
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined') return;

    const ENDPOINT = '/api/analysis/combustion-stability';

    // ------------------------------------------------------------------
    // i18n köprüleri — cfd_panel.js / analysis_center.js ile birebir aynı.
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
    //: Sunucudan/motordan gelen serbest beyan metni: sözlükte karşılığı
    //: varsa çevrilir, yoksa AYNEN kalır.
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
    function fmtExp(v, digits) {
        return isNum(v) ? v.toExponential(digits === undefined ? 2 : digits) : '—';
    }
    //: Anlamlı basamak — Merkez'in ön dolum kuralıyla aynı kaynak.
    function sigFig(value) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.sigFig === 'function') return U.sigFig(value);
        const v = Number(value);
        if (!isFinite(v) || v === 0) return v;
        return Number(v.toPrecision(6));
    }
    //: Alan YOKSA 'NaN' yerine em tire (cfd_panel ile aynı gerekçe).
    function sig(value) {
        return isNum(value) ? String(sigFig(value)) : '—';
    }
    //: Koşum kimliği toleransı: Merkez ön dolumu alanlara 6 anlamlı basamak
    //: yazar (analysis_dock DOCK_SIGFIG = 6); 6 basamağın en kötü yarım-ulp
    //: bağıl hatası 5e-6'dır (mantis ≈ 1,0 iken). Yankı bu yuvarlanmış
    //: değeri taşıyacağından eşik onun üstünde, ilk 5 basamağı oynatan her
    //: gerçek düzenlemenin ALTINDA seçilir. Fiziksel eşik değildir.
    const RUN_MATCH_REL_TOL = 1e-5;

    //: Bağıl yakınlık — koşum kimliği denetimi için (mutlak eşik uydurmadan).
    function relClose(a, b) {
        if (!isNum(a) || !isNum(b)) return false;
        const scale = Math.max(Math.abs(a), Math.abs(b), 1e-12);
        return Math.abs(a - b) <= RUN_MATCH_REL_TOL * scale;
    }

    // ==================================================================
    // >>> STABILITY_PANEL_MODEL_START
    // Saf model katmanı — DOM/Plotly YOK. Bekçi testleri bu bölümü GERÇEK
    // motor sonuçları ve sözleşme biçimli yanıtlarla doğrudan koşturur.
    // ==================================================================

    //: Motor sözlüğü: hibrit sayfası sonucu {motor: {...}} sarmalıyla
    //: yayımlıyor (ölçüldü), katı/sıvı düz — cfd_panel ile aynı okuma.
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
    // Motor sonucu okuyucuları — her yol ÖLÇÜLMÜŞ, sırayla denenir,
    // ilk tutan kazanır ve YOLU da kaydedilir. Uydurma yedek yoktur.
    // ------------------------------------------------------------------

    //: Akustik mod tablosunun ÜÇ motordaki ölçülmüş yerleri.
    const ACOUSTIC_PATHS = [
        'acoustic_modes',                                        // hibrit + katı
        'combustion_analysis.stability_analysis.acoustic_modes', // sıvı
    ];

    //: Modül çıktısının "çözüldü" durumları: hibrit/sıvı bağlaması
    //: 'modelled', katı bağlaması 'computed' yazıyor (ölçüldü).
    const ACOUSTIC_OK_STATUS = ['modelled', 'computed'];

    function acousticBlockOf(results) {
        const m = motorDict(results);
        if (!m) return null;
        for (let i = 0; i < ACOUSTIC_PATHS.length; i++) {
            const block = pick(m, ACOUSTIC_PATHS[i]);
            if (!block || typeof block !== 'object') continue;
            if (ACOUSTIC_OK_STATUS.indexOf(block.status) === -1) continue;
            if (!Array.isArray(block.modes) || !block.modes.length) continue;
            if (!isNum(block.sound_speed_m_s)) continue;
            return { block: block, path: ACOUSTIC_PATHS[i] };
        }
        return null;
    }

    //: Hibrit LFI (yalnız modelled + sonlu frekans → işaretlenir).
    const LFI_PATH = 'combustion_stability.lfi';
    function lfiOf(results) {
        const m = motorDict(results);
        const lfi = m ? pick(m, LFI_PATH) : null;
        if (!lfi || lfi.status !== 'modelled' || !isNum(lfi.frequency_hz)) {
            return null;
        }
        return { frequency_hz: lfi.frequency_hz, path: LFI_PATH };
    }

    //: Chug çevrimi bloğunun ölçülmüş yerleri: sıvıda stability_analysis
    //: içinde; hibritte (v2.6.27 F2b hibrit chug bağlaması) combustion_
    //: stability içinde. Katı yayımlamaz (chug yapısal olarak uygulanamaz).
    const CHUG_LOOP_PATHS = [
        'combustion_analysis.stability_analysis.chug_loop',   // sıvı
        'combustion_stability.chug_loop',                     // hibrit
    ];
    function chugLoopOf(results) {
        const m = motorDict(results);
        if (!m) return null;
        for (let i = 0; i < CHUG_LOOP_PATHS.length; i++) {
            const loop = pick(m, CHUG_LOOP_PATHS[i]);
            if (loop && loop.status === 'modelled') {
                return { block: loop, path: CHUG_LOOP_PATHS[i] };
            }
        }
        return null;
    }

    //: Mod başına eşik/sönüm satırları (hibrit + katı; sıvı yayımlamıyor).
    const THRESHOLD_PATH = 'combustion_stability.acoustic_response_threshold';
    function thresholdOf(results) {
        const m = motorDict(results);
        const blk = m ? pick(m, THRESHOLD_PATH) : null;
        if (!blk || typeof blk !== 'object') return null;
        if (blk.status !== 'modelled' || !Array.isArray(blk.modes)
                || !blk.modes.length) {
            // Blok var ama çözülmemiş: gerekçesi GRİ bölümde basılır.
            return { block: null, raw: blk, path: THRESHOLD_PATH };
        }
        return { block: blk, raw: blk, path: THRESHOLD_PATH };
    }

    //: Katı motorun kendi beyanı: chug yapısal olarak uygulanamaz.
    function chugApplicabilityOf(results) {
        const m = motorDict(results);
        if (!m) return null;
        for (let i = 0; i < ACOUSTIC_PATHS.length; i++) {
            const cap = pick(m, ACOUSTIC_PATHS[i] + '.chug_applicability');
            if (cap && cap.applicable === false) {
                return { reason: cap.reason || '',
                         path: ACOUSTIC_PATHS[i] + '.chug_applicability' };
            }
        }
        return null;
    }

    // ------------------------------------------------------------------
    // ÖNERİ KAYNAKLARI — cfd_panel deseni: alan başına ölçülmüş yol
    // listesi; ilk tutan kazanır, kaynağı ekranda adlandırılır. Hiçbir
    // yol tutmazsa alan ÖNERİSİZ kalır (uydurma varsayılan yok).
    // ------------------------------------------------------------------
    const DAMPING_SOURCES = {
        sound_speed_m_s: [
            { path: 'acoustic_modes.sound_speed_m_s' },
            { path: 'combustion_analysis.stability_analysis.acoustic_modes'
                    + '.sound_speed_m_s' },
        ],
        chamber_length_m: [
            { path: 'acoustic_modes.inputs.chamber_length' },
            { path: 'combustion_analysis.stability_analysis.acoustic_modes'
                    + '.inputs.chamber_length' },
        ],
        gamma: [
            { path: 'acoustic_modes.inputs.gamma' },
            { path: 'combustion_analysis.stability_analysis.acoustic_modes'
                    + '.inputs.gamma' },
        ],
        nozzle_entrance_mach: [
            // Hibrit + katı bağlaması M_N'i yayımlıyor; sıvıda kaynak yok
            // (alan boş kalır, kullanıcı elle girebilir).
            { path: 'combustion_stability.acoustic_response_threshold'
                    + '.mean_flow_mach_M_N' },
        ],
    };

    //: Chug önerileri: sıvı ve hibrit kendi çevrim yankısından; katıda
    //: yalnız τ_c'nin kaynağı var (chamber_time_constant), J ve τ önerisiz
    //: kalır (zaten satır katıda çözücünün kendi beyanıyla gridir).
    const CHUG_SOURCES = {
        dp_ratio_j: CHUG_LOOP_PATHS.map(function (p) {
            return { path: p + '.inputs.dp_ratio_j' };
        }),
        tau_s: CHUG_LOOP_PATHS.map(function (p) {
            return { path: p + '.inputs.tau_s' };
        }),
        tau_c_s: CHUG_LOOP_PATHS.map(function (p) {
            return { path: p + '.inputs.tau_c_s' };
        }).concat([
            // Katı bağlaması τ_c'yi kendi bloğunda yayımlıyor (F2b-1).
            { path: 'combustion_stability.chamber_time_constant.tau_c_s' },
        ]),
        tau_f_s: CHUG_LOOP_PATHS.map(function (p) {
            // Yalnız ataletli koşulduysa sonludur; değilse öneri yok.
            return { path: p + '.inputs.tau_f_s' };
        }),
    };

    function suggestFrom(sources, results) {
        const m = motorDict(results);
        const values = {};
        const srcs = {};
        if (!m) return { values: values, sources: srcs };
        Object.keys(sources).forEach(function (field) {
            const candidates = sources[field];
            for (let i = 0; i < candidates.length; i++) {
                const raw = pick(m, candidates[i].path);
                if (!isNum(raw)) continue;
                values[field] = raw;
                srcs[field] = { path: candidates[i].path, raw: raw };
                break;
            }
        });
        return { values: values, sources: srcs };
    }

    function suggestDamping(results) { return suggestFrom(DAMPING_SOURCES, results); }
    function suggestChug(results) { return suggestFrom(CHUG_SOURCES, results); }

    //: Alan etiketleri — eksik alan mesajı bunları ADIYLA yazar.
    const FIELD_LABELS = {
        sound_speed_m_s: ['panel.stab.fieldSoundSpeed',
                          'Chamber sound speed a [m/s]'],
        chamber_length_m: ['panel.stab.fieldChamberLength',
                           'Acoustic cavity length L [m]'],
        gamma: ['panel.stab.fieldGamma', 'Ratio of specific heats gamma [-]'],
        nozzle_entrance_mach: ['panel.stab.fieldMachN',
                               'Nozzle entrance mean-flow Mach M_N [-]'],
        dp_ratio_j: ['panel.stab.fieldJ',
                     'Injector pressure drop ratio J = dP_inj/Pc [-]'],
        tau_s: ['panel.stab.fieldTau', 'Sensitive time lag tau [s]'],
        tau_c_s: ['panel.stab.fieldTauC', 'Chamber time constant tau_c [s]'],
        tau_f_s: ['panel.stab.fieldTauF',
                  'Feed inertance time constant tau_f [s] — optional'],
        feed_line_length_m: ['panel.stab.fieldFeedLen',
                             'Feed line length [m] — optional group'],
        feed_line_diameter_mm: ['panel.stab.fieldFeedDia',
                                'Feed line inner diameter [mm] — optional group'],
        feed_line_area_m2: ['panel.stab.fieldFeedArea',
                            'Feed line flow area [m2] — optional group'],
        feed_line_mass_flow_kg_s: ['panel.stab.fieldFeedMdot',
                                   'Feed line mass flow [kg/s] — optional group'],
        // Uç sözleşmesi (parti 28 A2, gerekçeli sapma): τ_f = L·ṁ/(2A·ΔP_inj)
        // — ΔP_inj grubun ZORUNLU üyesidir (J oranından türetilemez, uç onsuz
        // 422 döner); yoğunluk ise birinci mertebe atalet formülüne HİÇ
        // girmez, uç onu yalnız YANKI olarak taşır. Bu yüzden ΔP_inj zorunlu,
        // yoğunluk isteğe bağlı: etkisiz bir alanı zorunlu tutmak kullanıcıya
        // sonucu değiştirmeyen sayı girdirtmek olurdu.
        feed_line_dp_injector_Pa: ['panel.stab.fieldFeedDp',
                                   'Injector pressure drop dP_inj [Pa] — '
                                   + 'required with the feed-line group'],
        feed_line_density_kg_m3: ['panel.stab.fieldFeedRho',
                                  'Propellant density in the line [kg/m3] — '
                                  + 'optional, echoed only'],
    };
    function fieldLabel(id) {
        const rec = FIELD_LABELS[id];
        return rec ? T(rec[0], rec[1]) : id;
    }

    // ------------------------------------------------------------------
    // UYGULANABİLİRLİK (çerçeve kural 1) — ucuz ve yan etkisiz.
    // ------------------------------------------------------------------
    function dampingApplicability(results) {
        if (!acousticBlockOf(results)) {
            return { ok: false, reason: {
                key: 'panel.stab.needsModes',
                fallback: 'This result publishes no solved acoustic mode '
                          + 'table (acoustic_modes with a modes list and a '
                          + 'sound speed): the mode map and the damping run '
                          + 'read the chamber state from it, and this panel '
                          + 'invents no cavity in its place. Re-run the motor '
                          + 'calculation on this page.' } };
        }
        return { ok: true };
    }

    function chugApplicability(results) {
        // Motorun KENDİ beyanı esas alınır: katı çözücü chug'ın yapısal
        // olarak uygulanamadığını acoustic_modes.chug_applicability içinde
        // kendisi yazıyor. O beyan varken satır çalıştırılabilir gösterilmez.
        const declared = chugApplicabilityOf(results);
        if (declared) {
            return { ok: false, reason: { text: declared.reason } };
        }
        return { ok: true };
    }

    // ------------------------------------------------------------------
    // POST GÖVDELERİ — sayılar formdan; eksik zorunlu alanda istisna
    // (çerçeve isteği GÖNDERMEZ ve eksikleri adıyla basar).
    // ------------------------------------------------------------------
    const DAMPING_REQUIRED = ['sound_speed_m_s', 'chamber_length_m', 'gamma',
                              'nozzle_entrance_mach'];
    const CHUG_REQUIRED = ['dp_ratio_j', 'tau_s', 'tau_c_s'];
    //: Besleme hattı grubunun üyeleri (kesit: alan VEYA çap).
    const FEED_FIELDS = ['feed_line_length_m', 'feed_line_diameter_mm',
                         'feed_line_area_m2', 'feed_line_mass_flow_kg_s',
                         'feed_line_dp_injector_Pa',
                         'feed_line_density_kg_m3'];

    //: Son koşuya GÖNDERİLEN motor durumu anlık görüntüsü: mod haritası ve
    //: sönüm çubukları ancak yanıtın yankısı bununla eşleşince çizilir.
    let lastSentAcoustic = null;
    //: Son öneri turlarının kaynak yolları (ekranda adlandırılır).
    let lastSuggestion = { damping: null, chug: null };
    //: Çizim kimlik sayacı (kimlik çakışmasın).
    let drawSeq = 0;

    function missingError(fields) {
        return new Error(TF('panel.stab.missingInputs',
            { fields: fields.map(fieldLabel).join(', ') },
            'These inputs have no value and the endpoint has no default for '
            + 'any of them: {fields}. The request was NOT sent — this panel '
            + 'does not invent a number in their place.'));
    }

    function buildDampingBody(formValues, results) {
        const v = formValues || {};
        const missing = DAMPING_REQUIRED.filter(function (f) { return !isNum(v[f]); });
        if (missing.length) throw missingError(missing);
        const body = { mode: 'damping' };
        DAMPING_REQUIRED.forEach(function (f) { body[f] = v[f]; });

        // Koşum kimliği için anlık görüntü: bu koşunun mod haritası ve
        // sönüm çubukları ANCAK yanıt yankısı bu görüntüyle eşleşirse
        // çizilir (geçmiş koşuya bugünkü tablo giydirilmez).
        const ac = acousticBlockOf(results);
        if (ac) {
            lastSentAcoustic = {
                path: ac.path,
                sound_speed_m_s: ac.block.sound_speed_m_s,
                chamber_length_m: pick(ac.block, 'inputs.chamber_length'),
                modes: ac.block.modes,
                lfi: lfiOf(results),
                chugLoop: chugLoopOf(results),
                threshold: thresholdOf(results),
            };
        } else {
            lastSentAcoustic = null;
        }
        return body;
    }

    function buildChugBody(formValues) {
        const v = formValues || {};
        const missing = CHUG_REQUIRED.filter(function (f) { return !isNum(v[f]); });
        if (missing.length) throw missingError(missing);
        const body = { mode: 'chug' };
        CHUG_REQUIRED.forEach(function (f) { body[f] = v[f]; });

        const feedGiven = FEED_FIELDS.filter(function (f) { return isNum(v[f]); });
        if (isNum(v.tau_f_s) && feedGiven.length) {
            // İki yol birden verilmiş: sessizce birini seçmek, ekranda
            // görünen değer ile gönderilen değeri ayrıştırır. Gönderilmez.
            throw new Error(T('panel.stab.feedConflict',
                'Both a direct tau_f and feed-line group fields were '
                + 'entered. The endpoint takes ONE of the two routes; the '
                + 'request was NOT sent so that no entered value is silently '
                + 'dropped. Clear one of them.'));
        }
        if (isNum(v.tau_f_s)) {
            body.tau_f_s = v.tau_f_s;
            return body;
        }
        if (feedGiven.length) {
            const groupMissing = [];
            if (!isNum(v.feed_line_length_m)) groupMissing.push('feed_line_length_m');
            if (!isNum(v.feed_line_area_m2) && !isNum(v.feed_line_diameter_mm)) {
                groupMissing.push('feed_line_area_m2 | feed_line_diameter_mm');
            }
            if (!isNum(v.feed_line_mass_flow_kg_s)) {
                groupMissing.push('feed_line_mass_flow_kg_s');
            }
            // ΔP_inj zorunlu (uç sözleşmesi: τ_f = L·ṁ/(2A·ΔP_inj), uç onsuz
            // 422 missing_fields döner); yoğunluk BİLEREK burada yok — uç onu
            // yalnız yankılar, eksikliği isteği durdurmaz.
            if (!isNum(v.feed_line_dp_injector_Pa)) {
                groupMissing.push('feed_line_dp_injector_Pa');
            }
            if (groupMissing.length) {
                throw new Error(TF('panel.stab.feedIncomplete',
                    { fields: groupMissing.join(', ') },
                    'The feed-line group is only partly filled; the missing '
                    + 'member(s): {fields}. The request was NOT sent — a '
                    + 'partial line would need invented values.'));
            }
            const line = { length_m: v.feed_line_length_m,
                           mass_flow_kg_s: v.feed_line_mass_flow_kg_s,
                           dp_injector_Pa: v.feed_line_dp_injector_Pa };
            if (isNum(v.feed_line_density_kg_m3)) {
                line.density_kg_m3 = v.feed_line_density_kg_m3;
            }
            if (isNum(v.feed_line_area_m2)) line.area_m2 = v.feed_line_area_m2;
            else line.diameter_mm = v.feed_line_diameter_mm;
            body.feed_line = line;
        }
        return body;
    }

    // ------------------------------------------------------------------
    // HÜKÜM ROZETLERİ (çerçeve kural 4 + F2a karar 1)
    // ------------------------------------------------------------------
    //: Akustik/sönüm yolunda hüküm YOKTUR (çekirdekte forbid_verdict_key
    //: ile yapısal). null → çerçeve "hüküm beyan edilmedi" rozetini basar.
    function dampingVerdict() {
        return null;
    }

    const VERDICT_KIND = { stable: 'ok', marginal: 'warn', unstable: 'err' };

    function chugVerdict(data) {
        if (!data || data.mode !== 'chug') return null;
        const a = data.assessment;
        if (!a || typeof a !== 'object') return null;
        if (typeof a.verdict !== 'string' || !a.verdict.trim()) return null;
        const scope = a.verdict_scope;
        if (typeof scope !== 'string' || !scope.trim()) {
            // KARAR 1: çıplak hüküm YASAK. Kapsamsız gelen hüküm ekrana
            // hüküm olarak ÇIKMAZ; bastırıldığı beyan edilir.
            return { kind: 'warn', key: 'panel.stab.verdictNoScope',
                     params: {},
                     fallback: 'VERDICT SUPPRESSED — the response carried a '
                               + 'verdict without its mechanism scope label; '
                               + 'a bare verdict is not shown (design '
                               + 'decision 1)' };
        }
        return { kind: VERDICT_KIND[a.verdict] || 'info',
                 key: 'panel.stab.verdictScoped',
                 params: { verdict: a.verdict.toUpperCase(), scope: scope },
                 fallback: '{verdict} — {scope}' };
    }

    //: Yanıt yankısı ↔ anlık görüntü eşleşmesi: mod haritasının bu koşuya
    //: ait olduğu ancak böyle ÖLÇÜLEBİLİR (cfd duvar çizgisi disiplini).
    function acousticRunMatches(data, snap) {
        if (!snap) return false;
        const inp = data && data.nozzle && data.nozzle.inputs;
        if (!inp) return false;
        return relClose(inp.sound_speed_m_s, snap.sound_speed_m_s)
            && relClose(inp.chamber_length_m, snap.chamber_length_m);
    }
    // <<< STABILITY_PANEL_MODEL_END
    // ==================================================================

    // ------------------------------------------------------------------
    // GÖRSEL METRİKLER (K1/K2) — yerleşim ve marjlar ölçülen metinden.
    // Sayılar tipografi metrikleridir, VERİ DEĞİLDİR (sahte veri yasağı
    // göstergeleri kapsar); bekçi testleri bu sözlüğü okuyup marj
    // formülünü aynen yeniden hesaplar.
    // ------------------------------------------------------------------
    const AXIS_METRICS = {
        titleFontPx: 11,        // y-ekseni başlık puntosu (çizimle aynı)
        tickFontPx: 10,         // tik etiketi puntosu (çizimle aynı)
        labelFontPx: 10,        // mod haritası etiket puntosu
        kvFontPx: 11.2,         // kvTable 0.7rem × 16px kök punto
        lineHeight: 1.35,       // başlık satır yüksekliği çarpanı
        padPx: 14,              // eksen çizgisi ↔ başlık tamponu
        tickPadPx: 6,           // tik etiketi ↔ eksen tamponu
        labelGapPx: 6,          // K1: etiket kutuları arası asgari boşluk
        labelTierStepPx: 14,    // K1: kademeler arası dikey adım (> punto)
        labelBaseOffsetPx: 16,  // K1: im ↔ ilk kademe etiketi mesafesi
        //: clientWidth ölçülemeyen ortamda (ilk çizim öncesi / test DOM'u)
        //: Plotly'nin kendi varsayılan çizim genişliği — yerleşim bandı
        //: ölçüsüdür, ekrana basılan bir veri değildir.
        defaultPlotWidthPx: 700,
        monoFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace",
    };

    //: JetBrains Mono'nun kendi ilerleme genişliği 0,6 em'dir (fontun
    //: metriği). Tarayıcıda GERÇEK canvas measureText ile ölçülür; canvas
    //: olmayan ortamda (node bekçi koşumu) bu metrikten hesaplanır —
    //: iki yol da deterministiktir, testler node yolunu ölçer.
    const MONO_ADVANCE_EM = 0.6;
    let measureCtx;
    function measureLabelPx(text, fontPx) {
        const s = String(text == null ? '' : text);
        const f = isNum(fontPx) && fontPx > 0 ? fontPx : AXIS_METRICS.labelFontPx;
        try {
            if (measureCtx === undefined) {
                measureCtx = null;
                const cv = (typeof document !== 'undefined'
                            && document.createElement)
                    ? document.createElement('canvas') : null;
                if (cv && typeof cv.getContext === 'function') {
                    measureCtx = cv.getContext('2d') || null;
                }
            }
            if (measureCtx && typeof measureCtx.measureText === 'function') {
                measureCtx.font = f + 'px ' + AXIS_METRICS.monoFamily;
                const w = measureCtx.measureText(s).width;
                if (isNum(w) && w > 0) return w;
            }
        } catch (err) { /* ölçüm düşerse font metriğine inilir */ }
        return s.length * f * MONO_ADVANCE_EM;
    }

    //: K2 — uzun eksen başlığını kullanılabilir uzunluğa göre satırlara
    //: sarar (kelime sınırında; her satırın ÖLÇÜLEN genişliği sığar).
    function wrapAxisTitle(text, availablePx, fontPx) {
        const words = String(text == null ? '' : text)
            .split(/\s+/).filter(Boolean);
        const lines = [];
        let line = '';
        words.forEach(function (w) {
            const aday = line ? line + ' ' + w : w;
            if (line && measureLabelPx(aday, fontPx) > availablePx) {
                lines.push(line);
                line = w;
            } else {
                line = aday;
            }
        });
        if (line) lines.push(line);
        return lines.length ? lines : [''];
    }

    //: K2 — tik etiketi genişliği: eksene düşecek değerlerin ekranda
    //: basılan biçiminin (sigFig) ölçülen en genişi. Plotly kendi tiklerini
    //: kısaltabilir; bu üst sınırdır — marj küçük değil geniş yanılır.
    function maxTickWidthPx(values, fontPx) {
        let w = 0;
        (values || []).forEach(function (v) {
            if (!isNum(v)) return;
            const m = measureLabelPx(String(sigFig(v)), fontPx);
            if (m > w) w = m;
        });
        return w;
    }

    //: K2 — sayısal y-ekseni sol marjı: ölçülen tik genişliği + başlık
    //: satır sayısı × satır yüksekliği + tamponlar. Bekçi bu formülü
    //: AXIS_METRICS ile aynen yeniden hesaplayıp eşitliği ölçer.
    function yAxisLeftMarginPx(values, titleLineCount) {
        return Math.ceil(maxTickWidthPx(values, AXIS_METRICS.tickFontPx)
            + AXIS_METRICS.tickPadPx
            + titleLineCount * AXIS_METRICS.titleFontPx * AXIS_METRICS.lineHeight
            + AXIS_METRICS.padPx);
    }

    //: K2 — kategori (bant/satır adı) ekseni sol marjı: en geniş ölçülen
    //: etiket + tamponlar; çizim alanı yutulmasın diye %45 tavanlı.
    function categoryLeftMarginPx(catLabels, widthPx) {
        let w = 0;
        (catLabels || []).forEach(function (s) {
            const m = measureLabelPx(String(s), AXIS_METRICS.tickFontPx);
            if (m > w) w = m;
        });
        const marj = Math.ceil(w + AXIS_METRICS.tickPadPx + AXIS_METRICS.padPx);
        return Math.max(Math.min(marj, Math.floor(widthPx * 0.45)), 40);
    }

    //: K1 — MOD HARİTASI ETİKET YERLEŞİMİ (SAF fonksiyon: DOM/Plotly yok,
    //: aynı girdi → aynı çıktı; bekçi birim-testi doğrudan koşturur).
    //:
    //: Girdi:  items = [{x: frekans_hz, row: bant/satır, label: metin}]
    //:         opts  = {plotWidthPx, fontPx, minGapPx, tierStepPx,
    //:                  baseOffsetPx, measure(fn)}
    //: Çıktı:  her öğe için {index, row, label, xPx, widthPx, leftPx,
    //:         rightPx, tier, ayPx}
    //:
    //: Algoritma: satır (bant) başına, x-piksel sırasında açgözlü kademe
    //: seçimi. Bir etiket, sol kenarı o kademede en son yerleşen kutunun
    //: sağ kenarı + boşluktan İLERİDEYSE o kademeye girer; değilse bir üst
    //: kademeye çıkar. Kademe içi sağ kenar tekdüze arttığından aynı
    //: kademedeki HER kutu çifti ayrıktır (kesişimsizlik yapısal olarak
    //: kanıtlı); farklı kademeler dikeyde tierStepPx (> punto) ayrıktır.
    //: Aynı noktaya düşen imlerin etiketleri tam örtüştüğünden zorunlu
    //: olarak farklı kademelere düşer.
    function layoutModeLabels(items, opts) {
        const o = opts || {};
        const plotW = isNum(o.plotWidthPx) && o.plotWidthPx > 0
            ? o.plotWidthPx : AXIS_METRICS.defaultPlotWidthPx;
        const fontPx = isNum(o.fontPx) && o.fontPx > 0
            ? o.fontPx : AXIS_METRICS.labelFontPx;
        const gap = isNum(o.minGapPx) ? o.minGapPx : AXIS_METRICS.labelGapPx;
        const step = isNum(o.tierStepPx) ? o.tierStepPx
            : AXIS_METRICS.labelTierStepPx;
        const base = isNum(o.baseOffsetPx) ? o.baseOffsetPx
            : AXIS_METRICS.labelBaseOffsetPx;
        const measure = typeof o.measure === 'function'
            ? o.measure
            : function (s) { return measureLabelPx(s, fontPx); };

        const xs = [];
        (items || []).forEach(function (it) {
            if (it && isNum(it.x) && it.x > 0) xs.push(it.x);
        });
        if (!xs.length) return [];
        const lo = Math.log10(Math.min.apply(null, xs));
        const hi = Math.log10(Math.max.apply(null, xs));
        const span = (hi - lo) || 1;

        const placed = [];
        (items || []).forEach(function (it, idx) {
            if (!it || !isNum(it.x) || it.x <= 0) return;
            const xPx = (Math.log10(it.x) - lo) / span * plotW;
            const w = measure(String(it.label));
            if (!isNum(xPx) || !isNum(w)) return;
            placed.push({ index: idx, row: String(it.row),
                          label: String(it.label), xPx: xPx, widthPx: w,
                          leftPx: xPx - w / 2, rightPx: xPx + w / 2,
                          tier: 0, ayPx: base });
        });

        const rows = {};
        placed.forEach(function (p) {
            (rows[p.row] = rows[p.row] || []).push(p);
        });
        Object.keys(rows).forEach(function (r) {
            const sirali = rows[r].slice().sort(function (a, b) {
                return a.xPx - b.xPx || a.index - b.index;
            });
            const sonSag = [];   // kademe -> o kademede son yerleşen sağ kenar
            sirali.forEach(function (p) {
                let t = 0;
                while (t < sonSag.length && p.leftPx < sonSag[t] + gap) t += 1;
                p.tier = t;
                sonSag[t] = p.rightPx;
                p.ayPx = base + t * step;
            });
        });
        return placed;
    }

    //: Çizim kabının gerçek genişliği; ölçülemiyorsa Plotly varsayılanı.
    function plotContainerWidth(id) {
        const el = (typeof document !== 'undefined'
                    && document.getElementById) ? document.getElementById(id)
            : null;
        const w = el && isNum(el.clientWidth) ? el.clientWidth : 0;
        return w > 0 ? w : AXIS_METRICS.defaultPlotWidthPx;
    }

    // ------------------------------------------------------------------
    // Görsel dil — Merkez/cfd_panel ile aynı değişken sözlüğü
    // (plotly_dark paletiyle uyumlu düz renkler).
    // ------------------------------------------------------------------
    const COLORS = {
        ok: 'var(--hd-green, #2dd4a8)',
        warn: 'var(--hd-orange, #ff8c33)',
        err: 'var(--hd-red, #ff5d73)',
        info: 'var(--hd-cyan, #00e5ff)',
        dim: 'var(--hd-ink-dim, #7d97a5)',
    };
    //: Bant renkleri — anahtarlar VERİDEN gelen bant adlarıdır
    //: (hrma.analysis.acoustic_modes _frequency_band çıktısı).
    const BAND_COLORS = {
        chug_range: '#00e5ff',
        buzz_range: '#ff8c33',
        screech_range: '#ff5d73',
    };
    const BAND_FALLBACK_COLOR = '#7d97a5';
    const CURVE_COLOR = '#00e5ff';
    const POINT_COLOR = '#ff5d73';
    const BAR_COLOR = '#2dd4a8';
    const LOCUS_COLOR = '#2dd4a8';
    //: K4 — Plotly düzeni CSS var() çözmez: theme.css jetonlarının HEX
    //: ikizleri (bekçi test theme.css ile birebir eşitliği ölçer).
    const INK_HEX = '#cfe8f2';       // --hd-ink   (veri metni, >= 7:1)
    const INK_DIM_HEX = '#7d97a5';   // --hd-ink-dim (açıklama, >= 4.5:1)

    function kindColor(kind) {
        return COLORS[kind] || COLORS.info;
    }

    function badge(text, kind, titleAttr) {
        const c = kindColor(kind);
        return '<span data-stab-badge="' + esc(kind) + '" title="'
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

    function basisText(text) {
        if (!text) return '';
        return '<p data-stab-basis="1" style="font-family:var(--hd-mono, monospace);'
            + ' font-size:0.66rem; line-height:1.45; color:var(--hd-ink-dim,'
            + ' #7d97a5); margin:6px 0; white-space:pre-wrap;">'
            + esc(SRV(text)) + '</p>';
    }

    function note(text, kind) {
        return '<p style="font-size:0.7rem; margin:6px 0; color:'
            + kindColor(kind || 'dim') + ';">' + esc(text) + '</p>';
    }

    //: VERİ-YOKSA-GRİ disiplini: bölüm çizilmez, gri kutu + gerekçe basılır.
    function greyBlock(which, reasonHtmlSafeText) {
        return '<div data-stab-grey="' + esc(which) + '" style="border:1px dashed'
            + ' var(--hd-line, rgba(0,229,255,0.14)); border-radius:8px;'
            + ' padding:10px 12px; margin:6px 0; color:var(--hd-ink-dim, #7d97a5);'
            + ' font-size:0.7rem;">' + reasonHtmlSafeText + '</div>';
    }

    //: K4 — İKİ hücre de veri metnidir (sayılar, mod adları, birimler):
    //: --hd-ink (>= 7:1). Soluk sınıflar (--hd-ink-dim/faint) veri
    //: hücresine UYGULANMAZ; onlar yalnız ikincil açıklama metninindir.
    //: K2b — opts.labelNowrap + opts.labelMinWidthPx: satır başları
    //: ölçülen metin genişliği kadar yer ayırır, kırpılmaz (R_crit tablosu).
    function kvTable(rows, opts) {
        const o = opts || {};
        let labelStyle = 'padding:2px 8px 2px 0; color:var(--hd-ink, #cfe8f2);'
            + ' vertical-align:top;';
        if (o.labelNowrap) labelStyle += ' white-space:nowrap;';
        if (isNum(o.labelMinWidthPx)) {
            labelStyle += ' min-width:' + Math.ceil(o.labelMinWidthPx) + 'px;';
        }
        const body = rows.map(function (r) {
            return '<tr><td style="' + labelStyle + '">' + esc(r[0])
                + '</td><td style="padding:2px 0; color:var(--hd-ink, #cfe8f2);'
                + ' font-family:var(--hd-mono, monospace);'
                + ' overflow-wrap:anywhere;">' + esc(r[1])
                + '</td></tr>';
        }).join('');
        return '<table style="border-collapse:collapse; font-size:0.7rem;'
            + ' width:100%;"><tbody>' + body + '</tbody></table>';
    }

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

    // ------------------------------------------------------------------
    // K3 — METİN DUVARI KATLAYICI: beyan/dayanak blokları VARSAYILAN
    // KAPALI <details> içine alınır. İçerik AYNEN DOM'da durur (beyan
    // disiplini ve kaynak-tarama bekçileri etkilenmez); <summary> başlık +
    // VERİDEN türeyen tek satırlık özet taşır. Hüküm rozetleri ve sayı
    // tabloları (R_crit, sönüm bütçesi, assessment) bu katlayıcıya
    // SOKULMAZ — onlar ana bilgidir.
    // ------------------------------------------------------------------
    function foldTitle(key, fallback) {
        return '<strong data-i18n="' + esc(key) + '" style="font-size:0.68rem;'
            + ' color:var(--hd-ink-dim, #7d97a5); letter-spacing:0.05em;'
            + ' text-transform:uppercase;">' + esc(T(key, fallback))
            + '</strong>';
    }

    function fold(which, titleHtml, previewText, bodyHtml) {
        return '<details data-stab-fold="' + esc(which) + '" style="border:'
            + '1px solid var(--hd-line, rgba(0,229,255,0.14));'
            + ' border-radius:8px; padding:4px 10px; margin:8px 0;">'
            + '<summary style="cursor:pointer; font-family:'
            + 'var(--hd-mono, monospace); font-size:0.66rem; line-height:1.5;'
            + ' color:var(--hd-ink-dim, #7d97a5); padding:2px 0;">'
            + titleHtml
            + (previewText
                ? ' <span style="letter-spacing:0; text-transform:none;">— '
                    + esc(previewText) + '</span>'
                : '')
            + '</summary>' + bodyHtml + '</details>';
    }

    //: Liste/sözlük özeti: kalem SAYISI + ilk adlar (veriden, uydurma yok).
    function listPreview(value) {
        let adlar = [];
        if (Array.isArray(value)) {
            adlar = value.map(function (v) { return SRV(String(v)); });
        } else if (value && typeof value === 'object') {
            adlar = Object.keys(value);
        }
        if (!adlar.length) return T('panel.stab.foldEmpty', 'nothing declared');
        const gosterilen = adlar.slice(0, 3).map(function (s) {
            return s.length > 42 ? s.slice(0, 42) + '…' : s;
        });
        let ozet = TF('panel.stab.foldCount', { n: adlar.length },
                      '{n} item(s):') + ' ' + gosterilen.join(', ');
        if (adlar.length > gosterilen.length) ozet += ', …';
        return ozet;
    }

    //: Düz metin özeti: ilk cümle (ya da ilk 120 karakter) — metnin kendisi.
    function prosePreview(text) {
        const s = String(text == null ? '' : text).trim();
        if (!s) return '';
        const nokta = s.indexOf('. ');
        if (nokta !== -1 && nokta < 120) return s.slice(0, nokta + 1);
        return s.length > 120 ? s.slice(0, 120) + '…' : s;
    }

    //: Tek düz metnin katlanmış hâli (metin yoksa hiç blok basılmaz).
    function foldProse(which, key, fallback, text) {
        if (!text) return '';
        return fold(which, foldTitle(key, fallback),
                    prosePreview(SRV(text)), basisText(text));
    }

    function plotBox(id, height) {
        return '<div id="' + esc(id) + '" data-stab-plot="1" style="width:100%;'
            + ' height:' + (height || 280) + 'px;"></div>';
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

    function purge(root) {
        const U = window.AnalysisDock && window.AnalysisDock.ui;
        if (U && typeof U.purgePlots === 'function') U.purgePlots(root);
    }

    function noPlotlyNote(root) {
        const warn = document.createElement('p');
        warn.setAttribute('data-stab-noplotly', '1');
        warn.style.color = COLORS.dim;
        warn.style.fontSize = '0.7rem';
        warn.textContent = T('panel.stab.noPlotly',
            'The plotting library is not loaded on this page, so the charts '
            + 'are not drawn; every number above comes from the same '
            + 'response.');
        root.appendChild(warn);
    }

    // ------------------------------------------------------------------
    // Çizimler — her sayı yanıttan ya da koşum anlık görüntüsünden.
    // ------------------------------------------------------------------
    function modeMapFigure(snap, widthPx) {
        const modes = snap.modes;
        const w = isNum(widthPx) && widthPx > 0
            ? widthPx : AXIS_METRICS.defaultPlotWidthPx;
        const lfiRowLabel = T('panel.stab.rowLfi', 'hybrid LFI (modelled)');
        const chugRowLabel = T('panel.stab.rowChugLoop', 'chug loop (modelled)');
        const hasLfi = !!(snap.lfi && isNum(snap.lfi.frequency_hz));
        const loop = snap.chugLoop && snap.chugLoop.block;
        // Frekans imi yalnız POZİTİFKEN: f = 0 salınımsız (gerçel) kök
        // demektir ve logaritmik frekans ekseninde gösterilemez; sayı
        // gizlenmez, chug kiracısının kendi tablosunda durur.
        const hasLoop = !!(loop && isNum(loop.frequency_hz)
                           && loop.frequency_hz > 0);

        // K2 — sol marj kategori etiketlerinin ÖLÇÜLEN genişliğinden
        // (bant adları + im satır adları); sabit tahmin değil.
        const catLabels = modes.map(function (m) { return String(m.band); });
        if (hasLfi) catLabels.push(lfiRowLabel);
        if (hasLoop) catLabels.push(chugRowLabel);
        const marginL = categoryLeftMarginPx(catLabels, w);
        const marginR = 12;

        // K1 — etiketler iz metni olarak DEĞİL, saf yerleşim fonksiyonunun
        // kademelendirdiği kısa yönlendirme çizgili notlar olarak çizilir:
        // aynı x-komşuluğuna düşen etiket kutuları (ölçülen genişlikle)
        // kesişmez. İzin x/y/text dizileri motor tablosunun KENDİSİ olarak
        // kalır (bekçi: test_mod_haritasi_anlik_goruntunun_kendisi — im
        // frekansın kendisinde durur; onu oynatmak sahte veri olurdu).
        const placed = layoutModeLabels(
            modes.map(function (m) {
                return { x: m.frequency_hz, row: String(m.band),
                         label: String(m.label) };
            }),
            { plotWidthPx: Math.max(w - marginL - marginR, 60) });
        const annotations = placed.map(function (p) {
            const m = modes[p.index];
            return {
                // Log eksende Plotly not koordinatı log10(değer) ister.
                x: Math.log10(m.frequency_hz),
                y: String(m.band),
                text: esc(String(m.label)),
                showarrow: true, arrowhead: 0, arrowwidth: 1,
                arrowcolor: INK_DIM_HEX,
                ax: 0, ay: -p.ayPx,
                font: { size: AXIS_METRICS.labelFontPx,
                        family: AXIS_METRICS.monoFamily, color: INK_HEX },
            };
        });

        const traces = [{
            x: modes.map(function (m) { return m.frequency_hz; }),
            y: modes.map(function (m) { return String(m.band); }),
            text: modes.map(function (m) { return String(m.label); }),
            mode: 'markers', type: 'scatter',
            marker: { size: 10, symbol: 'diamond',
                      color: modes.map(function (m) {
                          return BAND_COLORS[m.band] || BAND_FALLBACK_COLOR;
                      }) },
            name: T('panel.stab.traceModes',
                    'Cavity modes (acoustic table of this run)'),
        }];
        if (hasLfi) {
            traces.push({
                x: [snap.lfi.frequency_hz],
                y: [lfiRowLabel],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, symbol: 'x', color: POINT_COLOR },
                name: T('panel.stab.traceLfi',
                        'Hybrid LFI frequency (combustion_stability.lfi)'),
            });
        }
        if (hasLoop) {
            traces.push({
                x: [loop.frequency_hz],
                y: [chugRowLabel],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, symbol: 'x', color: POINT_COLOR },
                name: T('panel.stab.traceChugLoop',
                        'Chug loop frequency (chug_loop)'),
            });
        }
        return {
            traces: traces,
            layout: {
                title: T('panel.stab.chartModeMap',
                         'Chamber mode map on the frequency axis'),
                xaxis: { title: T('panel.stab.axisFreq', 'Frequency [Hz] (log)'),
                         type: 'log' },
                yaxis: { title: '',
                         tickfont: { size: AXIS_METRICS.tickFontPx,
                                     family: AXIS_METRICS.monoFamily } },
                annotations: annotations,
                height: 300,
                legend: { orientation: 'h', y: -0.34 },
                margin: { t: 40, r: marginR, b: 60, l: marginL },
            },
        };
    }

    function dampingBarsFigure(thresholdBlock) {
        const rows = thresholdBlock.modes;
        // Terim adları VERİDEN: her modun 'damping' sözlüğündeki anahtarlar.
        const termNames = [];
        rows.forEach(function (r) {
            Object.keys(r.damping || {}).forEach(function (name) {
                if (termNames.indexOf(name) === -1) termNames.push(name);
            });
        });
        const traces = termNames.map(function (name) {
            return {
                x: rows.map(function (r) { return String(r.label); }),
                y: rows.map(function (r) {
                    const v = (r.damping || {})[name];
                    return isNum(v) ? v : null;
                }),
                type: 'bar',
                marker: { color: BAR_COLOR },
                name: name,
            };
        });
        // K2a (ölçülen kusur): eski sabit l:70 marj + tek satır başlık,
        // dikey y-ekseni başlığını çizim yüksekliğinde kırpıyordu
        // ("...-rate contribution alpha [1/s] (negative..." yarım). Başlık
        // kullanılabilir yüksekliğe ÖLÇÜLEREK sarılır, marj ölçülen tik +
        // satır sayısından türetilir.
        const H = 280, mT = 40, mB = 60;
        const yVals = [];
        traces.forEach(function (t) {
            t.y.forEach(function (v) { if (isNum(v)) yVals.push(v); });
        });
        const titleLines = wrapAxisTitle(
            T('panel.stab.axisAlpha',
              'Growth-rate contribution alpha [1/s] (negative = damping)'),
            H - mT - mB, AXIS_METRICS.titleFontPx);
        return {
            traces: traces,
            layout: {
                title: T('panel.stab.chartDamping',
                         'Damping budget per longitudinal mode'),
                barmode: 'relative',
                xaxis: { title: T('panel.stab.axisMode', 'Mode'),
                         tickfont: { size: AXIS_METRICS.tickFontPx,
                                     family: AXIS_METRICS.monoFamily } },
                yaxis: { title: { text: titleLines.join('<br>'),
                                  font: { size: AXIS_METRICS.titleFontPx,
                                          family: AXIS_METRICS.monoFamily } },
                         tickfont: { size: AXIS_METRICS.tickFontPx,
                                     family: AXIS_METRICS.monoFamily } },
                height: H,
                legend: { orientation: 'h', y: -0.3 },
                margin: { t: mT, r: 12, b: mB,
                          l: yAxisLeftMarginPx(yVals, titleLines.length) },
            },
        };
    }

    function neutralCurveFigure(data) {
        const nc = data.neutral_curve || {};
        const op = data.operating_point || {};
        const traces = [{
            x: nc.dp_ratio_j, y: nc.tau_over_tau_c,
            mode: 'lines', type: 'scatter',
            line: { width: 2, color: CURVE_COLOR },
            name: T('panel.stab.traceNeutral',
                    'Neutral curve tau/tau_c = f(J) (this mechanism)'),
        }];
        if (isNum(op.dp_ratio_j) && isNum(op.tau_over_tau_c)) {
            traces.push({
                x: [op.dp_ratio_j], y: [op.tau_over_tau_c],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, symbol: 'x', color: POINT_COLOR },
                name: T('panel.stab.traceOperating',
                        'Operating point of this run'),
            });
        }
        // K2 — uzun dikey başlık ölçülerek sarılır, sol marj ölçülen
        // tiklerden türetilir (sönüm çubuğu grafiğiyle aynı kural).
        const H = 300, mT = 40, mB = 60;
        const yVals = (Array.isArray(nc.tau_over_tau_c)
            ? nc.tau_over_tau_c.filter(isNum) : [])
            .concat(isNum(op.tau_over_tau_c) ? [op.tau_over_tau_c] : []);
        const titleLines = wrapAxisTitle(
            T('panel.stab.axisTauRatio',
              'tau/tau_c [-] (above the curve = unstable within this '
              + 'mechanism)'),
            H - mT - mB, AXIS_METRICS.titleFontPx);
        return {
            traces: traces,
            layout: {
                title: T('panel.stab.chartNeutral',
                         'Chug neutral curve and the operating point'),
                xaxis: { title: T('panel.stab.axisJ',
                                  'Injector gain J = dP_inj/Pc [-]') },
                yaxis: { title: { text: titleLines.join('<br>'),
                                  font: { size: AXIS_METRICS.titleFontPx,
                                          family: AXIS_METRICS.monoFamily } },
                         tickfont: { size: AXIS_METRICS.tickFontPx,
                                     family: AXIS_METRICS.monoFamily } },
                height: H,
                legend: { orientation: 'h', y: -0.3 },
                margin: { t: mT, r: 12, b: mB,
                          l: yAxisLeftMarginPx(yVals, titleLines.length) },
            },
        };
    }

    function rootLocusFigure(data) {
        const rl = data.root_locus || {};
        const a = data.assessment || {};
        const traces = [{
            x: rl.sigma_1_s, y: rl.frequency_hz,
            mode: 'lines+markers', type: 'scatter',
            line: { width: 2, color: LOCUS_COLOR }, marker: { size: 5 },
            text: (rl.dp_ratio_j || []).map(function (j) {
                return 'J = ' + sig(j);
            }),
            name: T('panel.stab.traceLocus',
                    'Dominant root vs injector gain J'),
        }];
        if (isNum(a.growth_rate_1_s) && isNum(a.frequency_hz)) {
            traces.push({
                x: [a.growth_rate_1_s], y: [a.frequency_hz],
                mode: 'markers', type: 'scatter',
                marker: { size: 13, symbol: 'x', color: POINT_COLOR },
                name: T('panel.stab.traceLocusOp',
                        'Dominant root at the operating J'),
            });
        }
        // K2 — sol marj ölçülen tiklerden; kısa başlık gerekirse sarılır.
        const H = 300, mT = 40, mB = 60;
        const yVals = (Array.isArray(rl.frequency_hz)
            ? rl.frequency_hz.filter(isNum) : [])
            .concat(isNum(a.frequency_hz) ? [a.frequency_hz] : []);
        const titleLines = wrapAxisTitle(
            T('panel.stab.axisLocusFreq', 'Frequency [Hz]'),
            H - mT - mB, AXIS_METRICS.titleFontPx);
        return {
            traces: traces,
            layout: {
                title: T('panel.stab.chartLocus',
                         'Chug root locus (sigma-frequency plane)'),
                xaxis: { title: T('panel.stab.axisSigma',
                                  'Dominant root growth rate sigma [1/s] '
                                  + '(sigma > 0 = growing)') },
                yaxis: { title: { text: titleLines.join('<br>'),
                                  font: { size: AXIS_METRICS.titleFontPx,
                                          family: AXIS_METRICS.monoFamily } },
                         tickfont: { size: AXIS_METRICS.tickFontPx,
                                     family: AXIS_METRICS.monoFamily } },
                height: H,
                legend: { orientation: 'h', y: -0.3 },
                margin: { t: mT, r: 12, b: mB,
                          l: yAxisLeftMarginPx(yVals, titleLines.length) },
            },
        };
    }

    // ------------------------------------------------------------------
    // AKUSTİK/SÖNÜM kiracısının görünümü
    // ------------------------------------------------------------------
    function renderDamping(data, root) {
        if (!root) return;
        purge(root);
        drawSeq += 1;
        if (!data || data.mode !== 'damping' || !data.nozzle || !data.budget) {
            root.innerHTML = '<p data-stab-nodata="damping" style="font-size:0.72rem;'
                + ' color:var(--hd-red, #ff5d73);">'
                + esc(T('panel.stab.noDampingBlock',
                    'The response does not carry the mode="damping" contract '
                    + 'blocks (nozzle + budget); nothing is drawn and nothing '
                    + 'is inferred in its place.')) + '</p>';
            return;
        }
        const noz = data.nozzle;
        const bud = data.budget;
        const snap = lastSentAcoustic;
        const matches = acousticRunMatches(data, snap);
        const mapId = 'stab_map_' + drawSeq;
        const barsId = 'stab_bars_' + drawSeq;

        let html = '<div data-stab-badges="1">';
        html += badge(TF('panel.stab.badgeNozzle',
            { alpha: sig(noz.damping_1_s) },
            'NOZZLE DAMPING alpha_N = {alpha} 1/s'), 'info',
            SRV(noz.basis || ''));
        html += badge(TF('panel.stab.badgeTotalLoss',
            { v: sig(bud.total_loss_1_s) },
            'TOTAL MODELLED LOSS {v} 1/s'), 'info', SRV(bud.bias_basis || ''));
        // Bu yolda hüküm YOK — rozeti de yoktur; eşik dili aşağıda beyanlı.
        html += badge(T('panel.stab.badgeNoVerdict',
            'NO STABILITY VERDICT ON THIS PATH — damping/threshold only'),
            'dim', SRV(bud.bias_basis || ''));
        html += '</div>';

        // 1) Mod haritası — YALNIZ koşum kimliği ölçülünce.
        html += sectionTitle('panel.stab.secModeMap',
            'Mode map (from the acoustic table of the run this request was '
            + 'built from)');
        if (matches) {
            html += plotBox(mapId, 300);
            const absent = [];
            if (!snap.lfi) {
                absent.push(T('panel.stab.noLfiMarker',
                    'no hybrid LFI marker: this result does not publish '
                    + 'combustion_stability.lfi as modelled'));
            }
            if (!(snap.chugLoop && snap.chugLoop.block
                    && isNum(snap.chugLoop.block.frequency_hz)
                    && snap.chugLoop.block.frequency_hz > 0)) {
                absent.push(T('panel.stab.noChugMarker',
                    'no chug-loop marker: this result does not publish a '
                    + 'modelled chug_loop with a positive oscillation '
                    + 'frequency (a zero frequency means a non-oscillatory '
                    + 'root and cannot sit on the log frequency axis)'));
            }
            if (absent.length) html += note(absent.join('; '), 'dim');
        } else {
            html += greyBlock('mode-map',
                esc(T('panel.stab.greyModeMap',
                    'The mode map is not drawn: the sound speed / cavity '
                    + 'length echoed by this stored run do not measurably '
                    + 'match the acoustic mode table in hand, so the modes '
                    + 'cannot be claimed to belong to this run. Re-run with '
                    + 'the suggested values to bind them.')));
        }

        // 2) Mod başına sönüm bütçesi çubukları.
        html += sectionTitle('panel.stab.secDampingBars',
            'Damping budget per mode (acoustic_response_threshold of the '
            + 'motor result)');
        const th = matches && snap.threshold ? snap.threshold : null;
        if (th && th.block) {
            html += plotBox(barsId, 280);
            const rcritRows = th.block.modes.map(function (r) {
                return [String(r.label) + ' @ ' + sig(r.frequency_hz) + ' Hz',
                        T('panel.stab.rowRcrit', 'R_crit') + ' '
                            + sig(r.critical_response_real) + ' · '
                            + T('panel.stab.rowTotalDamping', 'total damping')
                            + ' ' + sig(r.damping_total_1_s) + ' 1/s'];
            });
            // K2b (ölçülen kusur): satır başları ("1L @ 959.391 Hz")
            // kırpılıyordu — sol sütuna en uzun başlığın ÖLÇÜLEN metin
            // genişliği kadar yer ayrılır, satır kırılmaz.
            const labelW = rcritRows.reduce(function (mx, row) {
                return Math.max(mx,
                    measureLabelPx(row[0], AXIS_METRICS.kvFontPx));
            }, 0);
            html += '<div data-stab-block="rcrit-table">'
                + kvTable(rcritRows, { labelNowrap: true,
                                       labelMinWidthPx: labelW }) + '</div>';
            html += foldProse('threshold-basis',
                'panel.stab.foldThresholdBasis', 'INTERPRETATION BASIS',
                th.block.interpretation_basis);
        } else {
            let why;
            if (!matches) {
                why = T('panel.stab.greyBarsMismatch',
                    'The per-mode damping bars are not drawn: the stored '
                    + 'run does not measurably match the motor result in '
                    + 'hand (same rule as the mode map).');
            } else if (th && th.raw && th.raw.reason) {
                why = TF('panel.stab.greyBarsDeclared', { reason: th.raw.reason },
                    'The per-mode damping bars are not drawn; the solver '
                    + 'declares why: {reason}');
            } else {
                why = T('panel.stab.greyBarsMissing',
                    'The per-mode damping bars are not drawn: this result '
                    + 'publishes no modelled acoustic_response_threshold '
                    + 'block (the liquid binding does not produce one), and '
                    + 'this panel invents no damping terms.');
            }
            html += greyBlock('damping-bars', esc(why));
        }

        // 3) Ucun kendi sönüm sözlükleri — AYNEN.
        html += sectionTitle('panel.stab.secNozzle',
            'Nozzle damping declared by the endpoint (quasi-steady short '
            + 'nozzle)');
        html += '<div data-stab-block="nozzle">' + kvTable([
            [T('panel.stab.rowAlpha', 'alpha_N [1/s]'), sig(noz.damping_1_s)],
            [T('panel.stab.rowAdmittance', 'Nozzle admittance (real part)'),
             sig(noz.admittance_real)],
            [T('panel.stab.rowConvective', 'Convective term (M_N)'),
             sig(noz.convective_term)],
            [T('panel.stab.rowModeDependence', 'Mode dependence'),
             String(noz.mode_dependence == null ? '—' : noz.mode_dependence)],
        ]) + '</div>';
        // K3 — dayanak düz metni varsayılan kapalı katlanır (içerik AYNEN).
        html += foldProse('nozzle-basis', 'panel.stab.foldNozzleBasis',
                          'NOZZLE DAMPING BASIS', noz.basis);

        html += sectionTitle('panel.stab.secBudget',
            'Damping budget declared by the endpoint');
        const termRows = Object.keys(bud.terms || {}).map(function (name) {
            return [name, sig(bud.terms[name]) + ' 1/s'];
        });
        termRows.push([T('panel.stab.rowBudgetTotal', 'Total (sum of terms)'),
                       sig(bud.total_damping_1_s) + ' 1/s']);
        termRows.push([T('panel.stab.rowBudgetLoss', 'Total loss magnitude'),
                       sig(bud.total_loss_1_s) + ' 1/s']);
        html += '<div data-stab-block="budget">' + kvTable(termRows) + '</div>';
        // K3 — işaret sözleşmesi + yanlılık dayanağı tek katlanır blokta.
        const budgetProse = [bud.sign_convention, bud.bias_basis]
            .filter(function (tx) { return !!tx; });
        if (budgetProse.length) {
            html += fold('budget-basis',
                foldTitle('panel.stab.foldBudgetBasis',
                          'SIGN CONVENTION & BIAS BASIS'),
                prosePreview(SRV(budgetProse[0])),
                budgetProse.map(function (tx) { return basisText(tx); })
                    .join(''));
        }
        // K3 — NOT MODELLED metin duvarı: özet (kalem sayısı + adlar)
        // VERİDEN; içerik details gövdesinde AYNEN durur.
        html += fold('not-modelled',
            foldTitle('panel.stab.declNotModelled', 'NOT MODELLED'),
            listPreview(bud.not_modelled),
            '<div data-stab-block="not-modelled">'
                + listBlock(bud.not_modelled) + '</div>');

        root.innerHTML = html;

        if (!window.Plotly || typeof window.Plotly.react !== 'function') {
            noPlotlyNote(root);
        } else {
            if (matches) {
                drawFigure(mapId,
                           modeMapFigure(snap, plotContainerWidth(mapId)));
            }
            if (th && th.block) drawFigure(barsId, dampingBarsFigure(th.block));
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
    }

    // ------------------------------------------------------------------
    // CHUG kiracısının görünümü
    // ------------------------------------------------------------------
    function renderChug(data, root) {
        if (!root) return;
        purge(root);
        drawSeq += 1;
        if (!data || data.mode !== 'chug' || !data.assessment) {
            root.innerHTML = '<p data-stab-nodata="chug" style="font-size:0.72rem;'
                + ' color:var(--hd-red, #ff5d73);">'
                + esc(T('panel.stab.noChugBlock',
                    'The response does not carry the mode="chug" contract '
                    + 'blocks (assessment + curves); nothing is drawn and '
                    + 'nothing is inferred in its place.')) + '</p>';
            return;
        }
        const a = data.assessment;
        const nc = data.neutral_curve || {};
        const rl = data.root_locus || {};
        const neutralId = 'stab_neutral_' + drawSeq;
        const locusId = 'stab_locus_' + drawSeq;

        let html = '<div data-stab-badges="1">';
        const v = chugVerdict(data);
        if (v) {
            html += badge(TF(v.key, v.params, v.fallback), v.kind,
                          SRV(a.verdict_basis || ''));
        }
        if (a.unconditionally_stable === true) {
            html += badge(T('panel.stab.badgeUnconditional',
                'NO NEUTRAL POINT AT THIS J (gain 1/(2J) <= 1)'), 'info',
                SRV(a.verdict_basis || ''));
        }
        html += badge(a.inertance_included
            ? TF('panel.stab.badgeInertance', { tf: sig(a.tau_f_s) },
                 'FEED INERTANCE INCLUDED (tau_f = {tf} s)')
            : T('panel.stab.badgeNoInertance', 'INERTANCE-FREE FEED LINE'),
            'info', SRV(a.inertance_basis || ''));
        if (a.root_dominance_note) {
            html += badge(T('panel.stab.badgeDominance',
                'TRACKED ROOT NOT DOMINANT — growth rate withheld'), 'warn',
                SRV(a.root_dominance_note));
        }
        html += '</div>';

        // 1) Nötr eğri + işletme noktası.
        html += sectionTitle('panel.stab.secNeutral',
            'Neutral curve tau/tau_c(J) with the operating point');
        if (Array.isArray(nc.dp_ratio_j) && nc.dp_ratio_j.length
                && Array.isArray(nc.tau_over_tau_c)) {
            html += plotBox(neutralId, 300);
        } else {
            html += greyBlock('neutral-curve',
                esc(T('panel.stab.greyNeutral',
                    'The response carries no neutral_curve arrays, so the '
                    + 'curve is not drawn and no curve is fabricated.')));
        }
        html += '<div data-stab-block="assessment">' + kvTable([
            [T('panel.stab.rowJ', 'J = dP_inj/Pc'), sig(a.dp_ratio_j)],
            [T('panel.stab.rowTau', 'tau [s]'), sig(a.tau_s)],
            [T('panel.stab.rowTauC', 'tau_c [s]'), sig(a.tau_c_s)],
            [T('panel.stab.rowTauRatio', 'tau/tau_c'), sig(a.tau_over_tau_c)],
            [T('panel.stab.rowNeutralDelay', 'Neutral delay [s]'),
             sig(a.neutral_delay_s)],
            [T('panel.stab.rowNeutralRatio', 'Neutral tau/tau_c'),
             sig(a.neutral_tau_over_tau_c)],
            [T('panel.stab.rowNeutralFreq', 'Neutral frequency [Hz]'),
             sig(a.neutral_frequency_hz)],
        ]) + '</div>';

        // 2) Kök yer eğrisi.
        html += sectionTitle('panel.stab.secLocus',
            'Root locus of the dominant chug root');
        if (Array.isArray(rl.sigma_1_s) && rl.sigma_1_s.length
                && Array.isArray(rl.frequency_hz)) {
            html += plotBox(locusId, 300);
        } else {
            html += greyBlock('root-locus',
                esc(T('panel.stab.greyLocus',
                    'The response carries no root_locus arrays (the core may '
                    + 'have refused every sampled J); the locus is not drawn '
                    + 'and no root is fabricated.')));
        }
        html += kvTable([
            [T('panel.stab.rowGrowth', 'Growth rate at operating J [1/s]'),
             sig(a.growth_rate_1_s)],
            [T('panel.stab.rowFreq', 'Oscillation frequency [Hz]'),
             sig(a.frequency_hz)],
        ]);
        // K3 — kök baskınlığı açıklaması katlanır (rozeti zaten yukarıda).
        html += foldProse('root-dominance', 'panel.stab.foldDominance',
                          'TRACKED ROOT NOTE', a.root_dominance_note);
        const skipped = Array.isArray(data.skipped_points)
            ? data.skipped_points : [];
        if (skipped.length) {
            html += '<div data-stab-block="skipped">'
                + note(TF('panel.stab.skippedPoints', { n: skipped.length },
                    '{n} locus sample point(s) were skipped by the endpoint '
                    + '(the core refused them); they are listed below, not '
                    + 'silently dropped.'), 'dim')
                + listBlock(skipped.map(function (e) {
                    if (e && typeof e === 'object') {
                        return 'J = ' + sig(e.dp_ratio_j) + ': '
                            + String(e.reason || '');
                    }
                    return String(e);
                })) + '</div>';
        }

        // 3) Klasik kural çaprazı — ölçüm, eşik değil.
        const cls = a.classical_rule_cross_check;
        if (cls && typeof cls === 'object') {
            html += sectionTitle('panel.stab.secClassical',
                'Classical dP/Pc rule cross-check (a measurement, not a '
                + 'threshold test)');
            html += '<div data-stab-block="classical">' + kvTable([
                [T('panel.stab.rowRuleMin', 'Rule minimum J'),
                 sig(cls.rule_min_ratio)],
                [T('panel.stab.rowRuleRec', 'Rule recommended J'),
                 sig(cls.rule_recommended_ratio)],
                [T('panel.stab.rowRuleNeutralMin',
                   'Model neutral tau/tau_c at the rule minimum'),
                 sig(cls.model_neutral_tau_over_tau_c_at_rule_min)],
                [T('panel.stab.rowRuleNeutralRec',
                   'Model neutral tau/tau_c at the rule recommendation'),
                 sig(cls.model_neutral_tau_over_tau_c_at_rule_recommended)],
            ]) + '</div>';
            // K3 — kural yorumu düz metni katlanır (sayı tablosu açık kalır).
            html += foldProse('classical-basis', 'panel.stab.foldClassicalBasis',
                              'RULE INTERPRETATION', cls.interpretation);
        }

        // 4) Beyanlar: modellenmeyenler, varsayımlar, girdi yankısı.
        // K3 (ölçülen kusur): bu beyan blokları varsayılan AÇIK ham düz
        // metin duvarıydı (panel ~2400px'e şişiyordu). Hepsi VARSAYILAN
        // KAPALI <details> içinde; özet satırı veriden türetilir, içerik
        // DOM'da AYNEN durur. Hüküm rozetleri ve sayı tabloları katlanmaz.
        html += sectionTitle('panel.stab.secDecl',
            'Declarations — not modelled, assumptions, echoed inputs');
        html += fold('not-modelled',
            foldTitle('panel.stab.declNotModelled', 'NOT MODELLED'),
            listPreview(a.not_modelled),
            '<div data-stab-block="not-modelled">'
                + listBlock(a.not_modelled) + '</div>');
        html += fold('assumptions',
            foldTitle('panel.stab.declAssumptions', 'ASSUMPTIONS'),
            listPreview(a.assumptions),
            '<div data-stab-block="assumptions">'
                + listBlock(a.assumptions) + '</div>');
        const inp = a.inputs || {};
        const inpKeys = Object.keys(inp).filter(function (k) {
            return k !== '_basis';
        });
        html += fold('inputs',
            foldTitle('panel.stab.declInputs', 'INPUTS ECHOED BY THE ENDPOINT'),
            TF('panel.stab.foldFields', { n: inpKeys.length },
               '{n} field(s) echoed'),
            '<div data-stab-block="inputs">'
                + kvTable(inpKeys.map(function (k) {
                    const val = inp[k];
                    return [k, val === null
                        ? T('panel.stab.notSupplied', 'not supplied')
                        : (isNum(val) ? sig(val) : String(val))];
                })) + '</div>');
        if (a.feed_line && typeof a.feed_line === 'object') {
            html += fold('feed-line',
                foldTitle('panel.stab.declFeedLine',
                          'FEED LINE ECHO (tau_f derivation inputs)'),
                listPreview(a.feed_line),
                '<div data-stab-block="feed-line">'
                    + listBlock(a.feed_line) + '</div>');
        }
        // Öneri kaynakları: hangi sayı motorun neresinden geldi.
        const sug = lastSuggestion.chug;
        if (sug && Object.keys(sug.sources).length) {
            html += fold('suggestions',
                foldTitle('panel.stab.declSuggest',
                          'WHERE THE PRE-FILLED VALUES CAME FROM'),
                TF('panel.stab.foldFields',
                   { n: Object.keys(sug.sources).length },
                   '{n} field(s) echoed'),
                '<div data-stab-block="suggestions">'
                    + kvTable(Object.keys(sug.sources).map(function (f) {
                        return [fieldLabel(f), sug.sources[f].path];
                    })) + '</div>');
        }
        // K3 — dört dayanak beyanı tek katlanır blokta (içerik AYNEN).
        const basisProse = [a.model_basis, a.root_basis, a.inertance_basis,
                            a.verdict_basis]
            .filter(function (tx) { return !!tx; });
        if (basisProse.length) {
            html += fold('basis',
                foldTitle('panel.stab.foldBasis',
                          'MODEL & VERDICT BASIS DECLARATIONS'),
                TF('panel.stab.foldStatements', { n: basisProse.length },
                   '{n} statement(s)') + ' — '
                    + prosePreview(SRV(basisProse[0])),
                basisProse.map(function (tx) { return basisText(tx); })
                    .join(''));
        }

        root.innerHTML = html;

        if (!window.Plotly || typeof window.Plotly.react !== 'function') {
            noPlotlyNote(root);
        } else {
            if (Array.isArray(nc.dp_ratio_j) && nc.dp_ratio_j.length) {
                drawFigure(neutralId, neutralCurveFigure(data));
            }
            if (Array.isArray(rl.sigma_1_s) && rl.sigma_1_s.length) {
                drawFigure(locusId, rootLocusFigure(data));
            }
        }
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(root);
    }

    // ==================================================================
    // KİRACI KAYITLARI — analysis_center.js başındaki sözleşme
    // ==================================================================
    const SPEC_ACOUSTIC = {
        componentId: 'chamber_acoustics',
        analysisId: 'acoustic_modes',
        // Başlık ve anahtar §2 matrisinin satırıyla AYNI (ayrışmasın diye).
        title: 'Acoustic mode table',
        titleKey: 'ac.an.acousticModes',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'solid', 'liquid'],
        long: false,

        applicability: dampingApplicability,

        // Hiçbir alanın SONLU varsayılanı yok: öneri gelmeyen alan boş
        // kalır ve body() isteği durdurur (uydurma sayı gösterilmez).
        fields: [
            ['sound_speed_m_s', 'Chamber sound speed a [m/s]', '', 'any',
             'panel.stab.fieldSoundSpeed'],
            ['chamber_length_m', 'Acoustic cavity length L [m]', '', 'any',
             'panel.stab.fieldChamberLength'],
            ['gamma', 'Ratio of specific heats gamma [-]', '', 'any',
             'panel.stab.fieldGamma'],
            ['nozzle_entrance_mach', 'Nozzle entrance mean-flow Mach M_N [-]',
             '', 'any', 'panel.stab.fieldMachN'],
        ],

        fromResults: function (results) {
            const sug = suggestDamping(results);
            lastSuggestion.damping = sug;
            return sug.values;
        },

        body: buildDampingBody,
        render: renderDamping,
        verdict: dampingVerdict,
    };

    const SPEC_CHUG = {
        componentId: 'chamber_acoustics',
        analysisId: 'combustion_stability',
        title: 'Combustion stability (feed-coupled chug loop)',
        titleKey: 'ac.an.combustionStability',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'solid', 'liquid'],
        long: false,

        applicability: chugApplicability,

        fields: [
            ['dp_ratio_j', 'Injector pressure drop ratio J = dP_inj/Pc [-]',
             '', 'any', 'panel.stab.fieldJ'],
            ['tau_s', 'Sensitive time lag tau [s]', '', 'any',
             'panel.stab.fieldTau'],
            ['tau_c_s', 'Chamber time constant tau_c [s]', '', 'any',
             'panel.stab.fieldTauC'],
            ['tau_f_s', 'Feed inertance time constant tau_f [s] — optional',
             '', 'any', 'panel.stab.fieldTauF'],
            ['feed_line_length_m', 'Feed line length [m] — optional group',
             '', 'any', 'panel.stab.fieldFeedLen'],
            ['feed_line_diameter_mm',
             'Feed line inner diameter [mm] — optional group', '', 'any',
             'panel.stab.fieldFeedDia'],
            ['feed_line_area_m2', 'Feed line flow area [m2] — optional group',
             '', 'any', 'panel.stab.fieldFeedArea'],
            ['feed_line_mass_flow_kg_s',
             'Feed line mass flow [kg/s] — optional group', '', 'any',
             'panel.stab.fieldFeedMdot'],
            // Parti 28 artçısı: ΔP_inj grubun ZORUNLU üyesi (uç sözleşmesi
            // τ_f = L·ṁ/(2A·ΔP_inj)); yoğunluk isteğe bağlı, uçta yalnız
            // yankılanır — buildChugBody'deki grup kapısıyla aynı sözleşme.
            ['feed_line_dp_injector_Pa',
             'Injector pressure drop dP_inj [Pa] — required with the '
             + 'feed-line group', '', 'any', 'panel.stab.fieldFeedDp'],
            ['feed_line_density_kg_m3',
             'Propellant density in the line [kg/m3] — optional, echoed only',
             '', 'any', 'panel.stab.fieldFeedRho'],
        ],

        fromResults: function (results) {
            const sug = suggestChug(results);
            lastSuggestion.chug = sug;
            return sug.values;
        },

        body: function (formValues) { return buildChugBody(formValues); },
        render: renderChug,
        verdict: chugVerdict,
    };

    if (window.AnalysisCenter && typeof window.AnalysisCenter.register === 'function') {
        window.AnalysisCenter.register(SPEC_ACOUSTIC);
        window.AnalysisCenter.register(SPEC_CHUG);
    } else if (window.console && console.warn) {
        console.warn('[StabilityPanel] window.AnalysisCenter yok: kiracılar '
            + 'kaydolamadı. Yükleme sırası analysis_center.js -> '
            + 'panels/stability_panel.js olmalı.');
    }

    // Test / hata ayıklama yüzeyi — saf model katmanı DOM'suz koşulabilir.
    window.StabilityPanel = {
        specAcoustic: SPEC_ACOUSTIC,
        specChug: SPEC_CHUG,
        endpoint: ENDPOINT,
        _suggestDamping: suggestDamping,
        _suggestChug: suggestChug,
        _acousticBlockOf: acousticBlockOf,
        _thresholdOf: thresholdOf,
        _lfiOf: lfiOf,
        _chugLoopOf: chugLoopOf,
        _chugApplicabilityOf: chugApplicabilityOf,
        _dampingApplicability: dampingApplicability,
        _chugApplicability: chugApplicability,
        _buildDampingBody: buildDampingBody,
        _buildChugBody: buildChugBody,
        _chugVerdict: chugVerdict,
        _dampingVerdict: dampingVerdict,
        _acousticRunMatches: acousticRunMatches,
        _lastSentAcoustic: function () { return lastSentAcoustic; },
        _dampingSources: DAMPING_SOURCES,
        _chugSources: CHUG_SOURCES,
        // K1/K2 görsel metrik yüzeyi — bekçiler yerleşimi ve marj
        // formülünü bu SAF fonksiyonlarla yeniden hesaplayıp ölçer.
        _layoutModeLabels: layoutModeLabels,
        _measureLabelPx: measureLabelPx,
        _wrapAxisTitle: wrapAxisTitle,
        _maxTickWidthPx: maxTickWidthPx,
        _axisMetrics: AXIS_METRICS,
    };
})();
