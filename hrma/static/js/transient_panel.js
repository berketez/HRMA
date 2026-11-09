/* ====================================================================
   HRMA Transient Analysis Panel (yalnız hibrit sayfası)
   --------------------------------------------------------------------
   /api/transient-analysis'i UI'a bağlar: gerçek Pc(t)/F(t) eğrileri,
   regülatörlü veya N₂O blowdown besleme, SP-8089 kararlılık uyarıları.

   Kullanım (advanced.html):
     <script src="/static/js/transient_panel.js"></script>
     TransientPanel.init({ anchorId: 'trajectoryPanel' });

   Sonuç iki yere yayılır:
     1. window.currentResults.motor.transient  → .eng export'u gerçek
        itki eğrisini kullanır (openrocket_integration._generate_thrust_curve)
     2. window.TransientPanel.lastResult       → 6-DOF paneli thrust_curve
        zinciri + dijital ikiz (MotorViz3D) beslemesi
   ==================================================================== */

(function () {
    'use strict';

    let lastResult = null;
    // V306/UÇUŞ-3 (BAYAT DEVİR 2 panel ayağı + UÇUŞ-2 DEVİR 2a): ekrandaki
    // sonucun hangi motor hesabına (window.currentResults nesnesi) ait
    // olduğu. Yeni motor hesabı yeni nesne yaratır; eski sonuç temizlenir.
    let lastResultSonuc = null;

    // i18n köprüsü — i18n.js yoksa İngilizce yedek metin döner
    function T(key, fallback) {
        return (window.I18N && window.I18N.t) ? window.I18N.t(key, fallback) : fallback;
    }
    function TF(key, params, fallback) {
        if (window.I18N && window.I18N.tf) return window.I18N.tf(key, params, fallback);
        return String(fallback).replace(/\{(\w+)\}/g, function (whole, name) {
            return (params && name in params) ? String(params[name]) : whole;
        });
    }
    // ÖH D37 A1b panel-js · OH-D33-09 — EKRAN ondalığı tek kanaldan
    // (`I18N.number`: TR virgül, EN nokta); i18n.js yoksa nokta.
    function ekranSayisi(v, basamak) {
        return (window.I18N && typeof window.I18N.number === 'function')
            ? window.I18N.number(v, basamak) : v.toFixed(basamak);
    }

    // ------------------------------------------------------------------
    // ÖH D34 / OH-GT-05 — BİTİŞ OLAYI: ÇEVİRİLİ ETİKET + FAIL-CLOSED
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/D34/metin-i18n/a1/once.json):
    // çözücünün olay kümesi SEKİZ değerdir (transient_ballistics.py,
    // ``event = '...'``) ama panellerin haritası ALTISINI tanıyordu;
    // 'chamber_below_ambient' ile 'throat_erosion_limit' sessizce 'info'
    // rozetine düşüyordu. Metin ise hiç çevrilmiyordu: ekranda ham makine
    // sabiti ('BURN_TIME_REACHED') görünüyordu.
    //
    // Kural (fail-closed): bilinmeyen değer için sessiz yedek YOK. Sözlükte
    // karşılığı olmayan olay HAM ve İŞARETLİ basılır, rozet 'warn' olur —
    // yeni bir olay eklenirse ekranda görünür, sessizce "iyi" sayılmaz.
    // Etiketlerin tek kaynağı i18n sözlüğüdür ('transient.end.<olay>');
    // kapsam bekçisi: tests/test_d34_metin_i18n_a1.py.
    // Anahtar adları BURADA HARFİ HARFİNE yazılır (birleştirilmiş dize
    // DEĞİL): ölü-çeviri bekçisi (tests/test_i18n_common.js taraması)
    // sözlük anahtarını kaynakta arar; 'transient.end.' + olay biçiminde
    // kurulan anahtar o taramada GÖRÜNMEZ ve sözlük girdisi "ölü" sayılırdı.
    // Rozet ile anahtar TEK tabloda durur — iki ayrı liste tutulmaz.
    const END_EVENTS = {
        burn_time_reached:
            { kind: 'ok', key: 'transient.end.burn_time_reached' },
        web_exhausted:
            { kind: 'ok', key: 'transient.end.web_exhausted' },
        oxidizer_depleted:
            { kind: 'info', key: 'transient.end.oxidizer_depleted' },
        injector_unstable:
            { kind: 'err', key: 'transient.end.injector_unstable' },
        feed_pressure_lost:
            { kind: 'err', key: 'transient.end.feed_pressure_lost' },
        time_limit:
            { kind: 'warn', key: 'transient.end.time_limit' },
        chamber_below_ambient:
            { kind: 'err', key: 'transient.end.chamber_below_ambient' },
        throat_erosion_limit:
            { kind: 'warn', key: 'transient.end.throat_erosion_limit' },
    };

    function endEventEntry(event) {
        return Object.prototype.hasOwnProperty.call(END_EVENTS, event)
            ? END_EVENTS[event] : null;
    }

    function endEventKind(event) {
        const kayit = endEventEntry(event);
        return kayit ? kayit.kind : 'warn';
    }

    function endEventLabel(event) {
        const ham = String(event === null || event === undefined ? '' : event);
        if (!ham) return '';
        const kayit = endEventEntry(ham);
        if (kayit && window.I18N && window.I18N.has
                && window.I18N.has(kayit.key)) {
            return T(kayit.key, ham.toUpperCase());
        }
        return ham.toUpperCase() + ' (?)';
    }

    // ------------------------------------------------------------------
    // BASINÇ BİRİMİ — TEK KAYNAK
    // ------------------------------------------------------------------
    // /api/transient-analysis basınç dizilerini PASCAL döner
    // (hrma/analysis/transient_ballistics.py:498 `'chamber_pressure': Pc_arr,
    // # Pa` ve :517 `'tank_pressure': ... # Pa`).
    //
    // ÖLÇÜLDÜ (2026-08-09): çizim bunu bar'a çeviriyordu ama DIŞA AKTARIM
    // ÇEVİRMİYORDU. Sütun başlığı 'Chamber pressure (bar)' yazarken hücreye
    // ham Pascal konuyordu; 20 bar'lık bir motorun CSV/XLSX çıktısında
    // 2000000 görünüyordu — 100000 kat. Aynı hata tank basıncı sütununda da
    // vardı. Kullanıcı ekranda doğru, dosyada yanlış sayı görüyordu.
    //
    // Çevrim artık TEK yerde: hem grafik hem dışa aktarım bu yardımcıyı
    // çağırır, bir daha birbirinden ayrışamazlar.
    // ÖH D25 / OH-D24-05 — TEK KAYNAK. Bu sayı burada TANIMLANMAZ:
    // `static/js/units_constants.js` ön yüzün tek birim çevrim kaynağıdır
    // (ölçüldü: aynı tanım dört JS dosyasındaydı). Modül yoksa sessiz bir
    // yedek UYDURULMAZ — requirePaPerBar() hata fırlatır.
    const PA_PER_BAR = (function () {
        var g = (typeof window !== 'undefined') ? window : globalThis;
        // Tarayıcı: <script src="/static/js/units_constants.js"> modülü
        // window'a yazar. Node (bekçi koşumları panel dosyasını require
        // eder): modül kardeş dosyadan çözülür. İKİ yolda da sayı TEK
        // yerde yaşar; burada yeniden TANIMLANMAZ.
        if (!g.HRMAUnits && typeof require === 'function') {
            try { g.HRMAUnits = require('./units_constants.js').UNITS; } catch (e) { /* yok */ }
            if (g.HRMAUnits && !g.HRMAUnits.requirePaPerBar) {
                try {
                    g.HRMAUnits.requirePaPerBar =
                        require('./units_constants.js').requirePaPerBar;
                } catch (e) { /* yok */ }
            }
        }
        if (!g.HRMAUnits || !g.HRMAUnits.requirePaPerBar) {
            throw new Error('units_constants.js must load before this panel: '
                + 'PA_PER_BAR has a single source and is not re-declared here.');
        }
        return g.HRMAUnits.requirePaPerBar();
    }());

    function toBar(values) {
        return (values || []).map(function (p) {
            return (p === null || p === undefined || !isFinite(p))
                ? p : p / PA_PER_BAR;
        });
    }

    // v3.0.1 (22 Eki) — GEÇİCİ ANALİZ SONUÇ EKRANINDAKİ MOTORU KOŞAR.
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ana-model/gecici-uc/once.txt):
    // toplayıcı yalnız 14 form alanı gönderiyordu; port_count ve
    // residual_web_thickness hiç gitmiyordu. 4 portlu ana tasarımın (yanma
    // sonu port 32,75 mm) geçici eğrisi tek portlu motor olarak (53,74 mm)
    // çözülüyordu. Ana hesap yapıldıysa gövde, app.js'in sakladığı SON ANA
    // İSTEĞİN (window.currentRequest) kopyasıdır — enjektör paneliyle aynı
    // desen (V301/E2). Uç sözleşmesi gereği okunmayan alan çıkarılır:
    // soğutma seçimi geçici yürüyüşe girmez ve uç onu adıyla 422 ile
    // reddeder (ÖH D27 / OH-D26-05).
    const GECICI_UCUN_REDDETTIGI_ALANLAR = ['cooling_channels'];

    // v3.0.1 (V301/H4): blowdown kipi kendinden basınçlı N₂O tankını
    // modeller. Ana tasarım kullanıcı tank kipindeyse (basınçlandırılmış
    // besleme) bu eğri o tasarımın eğrisi değildir: seçenek kapanır ve nedeni
    // yazılır; uç da aynı durumu adıyla reddeder
    // (feed_mode_conflicts_with_tank_pressure_source).
    const KULLANICI_TANK_KIPI = 'user';

    function kullaniciTankKipindeMi() {
        const ana = (typeof window !== 'undefined') ? window.currentRequest : null;
        if (ana && typeof ana === 'object' && !Array.isArray(ana)) {
            return ana.tank_pressure_source === KULLANICI_TANK_KIPI;
        }
        const el = document.getElementById('tank_pressure_source');
        return !!(el && el.value === KULLANICI_TANK_KIPI);
    }

    // V301/H-PANEL (NK-50): ana tasarım kendinden basınçlı N₂O mu?
    // (Blowdown modeli N₂O'ya özgüdür: hrma/analysis/tank_blowdown.py.)
    function kendindenBasincliN2OMu() {
        if (kullaniciTankKipindeMi()) return false;
        const ana = (typeof window !== 'undefined') ? window.currentRequest : null;
        let ox = null;
        if (ana && typeof ana === 'object' && !Array.isArray(ana)) {
            ox = ana.oxidizer_type;
        }
        if (!ox) {
            const el = document.getElementById('oxidizer_type');
            ox = el ? el.value : null;
        }
        return String(ox || '').toLowerCase() === 'n2o';
    }

    function beslemeKipiniEsle() {
        const sel = document.getElementById('tp_feed_mode');
        if (!sel) return;
        const kullanici = kullaniciTankKipindeMi();
        // V306 ana model (NK3-H-5, S1, 9 Kas): boşalma modeli YALNIZ kendinden
        // basınçlı N₂O tankınındır (hrma/analysis/tank_blowdown.py; tank
        // sıcaklığı kutusunun 240-309 K bandı da N₂O doyma tablosudur).
        // ÖLÇÜLDÜ (NK3, rc.1): N₂O'dan LOX'a geçince kip 'blowdown'da ve tank
        // sıcaklığı kutusu görünür kalıyordu; Hesapla kutuya motorun LOX
        // sıcaklığını (90 K) yazıyor, sonraki HER Hesapla bu kutunun
        // beyanlı alt sınırından (240) reddediliyordu. N₂O olmayan
        // oksitleyicide boşalma kipi kapanır ve regüleye döner.
        const n2oDegil = !kullanici && !kendindenBasincliN2OMu();
        const secenekler = sel.options || [];
        for (let i = 0; i < secenekler.length; i++) {
            if (secenekler[i].value === 'blowdown') {
                secenekler[i].disabled = kullanici || n2oDegil;
            }
        }
        if ((kullanici || n2oDegil) && sel.value === 'blowdown') {
            sel.value = 'regulated';
            ['tp_tank_temp_group', 'tp_fill_group'].forEach(function (id) {
                const g = document.getElementById(id);
                if (g) g.style.display = 'none';
            });
        }
        // V301/H-PANEL (NK-50): ana formda "kendinden basınçlı" N₂O tankı
        // seçiliyse geçici analizin VARSAYILAN besleme kipi blowdown'dur
        // (ana hesabın "Tank Boşalması" bloğuyla aynı fizik). Kullanıcı
        // panelde kipi elle seçtiyse o seçim ezilmez.
        if (!kullanici && kendindenBasincliN2OMu()
                && (sel.dataset || {}).kullaniciSecti !== '1'
                && sel.value !== 'blowdown') {
            sel.value = 'blowdown';
            ['tp_tank_temp_group', 'tp_fill_group'].forEach(function (id) {
                const g = document.getElementById(id);
                if (g) g.style.display = '';
            });
        }
        const not = document.getElementById('tp_feed_note');
        if (not) not.style.display = kullanici ? '' : 'none';
        const notOx = document.getElementById('tp_feed_note_ox');
        if (notOx) notOx.style.display = n2oDegil ? '' : 'none';
    }

    function anaIstekGovdesi() {
        const ana = (typeof window !== 'undefined') ? window.currentRequest : null;
        if (!ana || typeof ana !== 'object' || Array.isArray(ana)) return null;
        const govde = Object.assign({}, ana);
        GECICI_UCUN_REDDETTIGI_ALANLAR.forEach(function (k) { delete govde[k]; });
        return govde;
    }

    // Ana hesap yoksa advanced.html form alanlarından motor parametrelerini
    // topla (calculate() payload'ıyla aynı ID'ler; yalnız transient'in
    // ihtiyacı olanlar).
    function collectMotorParams() {
        const ana = anaIstekGovdesi();
        if (ana) return ana;
        const num = (id, d) => {
            const el = document.getElementById(id);
            const v = el ? parseFloat(el.value) : NaN;
            return isFinite(v) ? v : d;
        };
        const str = (id, d) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : d;
        };
        const govde = {
            thrust: num('thrust', 1000),
            burn_time: num('burn_time', 10),
            of_ratio: num('of_ratio', 7.0),
            chamber_pressure: num('chamber_pressure', 20),
            // DÜZELTME (2026-07-19): 'ambient_pressure' ID'li alan sayfada YOK;
            // gerçek alan advanced.html'deki #single_pressure (app.js de onu
            // okuyor). Eski hâlinde transient analiz kullanıcının irtifasını /
            // ölçtüğü basıncı görmüyor, sessizce 1.01325 bar'a düşüyordu.
            atmospheric_pressure: num('single_pressure', 1.01325),
            l_star: num('l_star', 1.0),
            expansion_ratio: Math.max(0, num('expansion_ratio', 0)),
            nozzle_type: str('nozzle_type', 'conical'),
            regression_a: num('regression_a', 3.68e-5),
            regression_n: num('regression_n', 0.555),
            fuel_density: num('fuel_density', 920),
            chamber_diameter_input: num('chamber_diameter_input', 0),
            fuel_type: str('fuel_type', 'htpb'),
            oxidizer_type: str('oxidizer_type', 'n2o'),
        };
        // Port sayısı ve artık et formda boş bırakılabilir (uç 1 port ve
        // idealizasyon varsayılanını adıyla beyan eder); doluysa gider.
        const portSayisi = num('port_count', NaN);
        if (isFinite(portSayisi)) govde.port_count = portSayisi;
        const artikEt = num('residual_web_thickness', NaN);
        if (isFinite(artikEt)) govde.residual_web_thickness = artikEt;
        if (kullaniciTankKipindeMi()) govde.tank_pressure_source = KULLANICI_TANK_KIPI;
        return govde;
    }

    // ------------------------------------------------------------------
    // v3.0.1 (V301/N-grafik G1.4) — ÜÇ GİRDİNİN "?" İPUCU
    // ------------------------------------------------------------------
    // Berke (26 Eki): her girdinin yanında açıklama. İçerik koddan:
    //   * boş bırakılan tank girdisi → ucun beyanlı varsayılanıyla AYNI sayı
    //     (hrma/engines/hybrid_rocket_engine.py TANK_TEMPERATURE_DEFAULT_K =
    //     293,15 K, TANK_FILL_FRACTION_DEFAULT = 0,85);
    //   * kabul bandı → hrma/analysis/tank_blowdown.py: sıcaklık
    //     SAT_TABLE_T_MIN..SAT_TABLE_T_MAX (doyma tablosu, 240..309 K),
    //     doluluk 0,05..0,98 (N2OTankBlowdown.__init__ reddi).
    // Sayılar JS'de BİR KEZ yazılır; tests/test_v301_gecici_zaman_ekseni.py
    // bunları Python kaynaklarıyla karşılaştırır (ayrışırsa KIRMIZI).
    // Eski hâl: `parseFloat(...) || 293.15` — 0 yazan kullanıcının girdisi
    // de sessizce 293,15'e dönüyordu. Artık yalnız BOŞ alan varsayılana
    // gider (ipucu bunu söyler); yazılan sayı aynen gönderilir, bant
    // dışındaysa uç nedeniyle reddeder.
    const BOS_TANK_SICAKLIGI_K = 293.15;
    const BOS_DOLULUK_ORANI = 0.85;
    const TANK_T_BANDI_K = [240, 309];
    const DOLULUK_BANDI = [0.05, 0.98];

    function tankGirdisi(id, bos) {
        const el = document.getElementById(id);
        const ham = el ? String(el.value === undefined ? '' : el.value).trim() : '';
        return ham === '' ? bos : parseFloat(ham);
    }

    // V306/UÇUŞ-3 (M-HIBRIT-17) — TANK SICAKLIĞI MOTORUN GİRDİSİNDEN.
    // ÖLÇÜLDÜ (4 Kas, ekran/tarayici_once_tr_YTE.json T; tur: Hansen 2012):
    // motor formunda Oksitleyici Sıcaklık 281,75 K iken panelin "Tank
    // Sıcaklığı (K)" alanı 293,15'te kalıyordu; aynı istek gövdesi
    // ``oxidizer_temp: 281.75`` ve ``tank_temperature: 293.15`` taşıyordu —
    // motor 38,7 bar (P_sat 281,75 K) tankla tasarlanmış, panel 50,4 bar
    // tankla boşaltıyordu. Motor N₂O tankının sıcaklığını ana isteğin
    // ``oxidizer_temp``ından alır (hrma/app.py /calculate: tank_temperature
    // = oxidizer_temp, verilmezse motorun TANK_TEMPERATURE_DEFAULT_K'sı =
    // BOS_TANK_SICAKLIGI_K). Panel aynı kaynaktan tohumlanır; kullanıcı
    // panelde başka bir sıcaklık yazarsa değeri korunur ve fark adıyla yazar.
    function motorTankSicakligi() {
        const ana = (typeof window !== 'undefined') ? window.currentRequest : null;
        let t = (ana && typeof ana === 'object' && !Array.isArray(ana))
            ? Number(ana.oxidizer_temp) : NaN;
        if (!(isFinite(t) && t > 0)) {
            const el = document.getElementById('oxidizer_temp');
            t = el ? parseFloat(el.value) : NaN;
        }
        return (isFinite(t) && t > 0) ? t : BOS_TANK_SICAKLIGI_K;
    }
    function tankSicakligiNotunuYaz() {
        const el = document.getElementById('tp_tank_temp');
        if (!el) return;
        let not = document.getElementById('tp_tank_temp_note');
        const motorT = motorTankSicakligi();
        const simdi = parseFloat(el.value);
        const farkli = el.dataset && el.dataset.userOverride === 'true'
            && isFinite(simdi) && Math.abs(simdi - motorT) > 0.005;
        if (!farkli) { if (not) not.remove(); return; }
        if (!not) {
            not = document.createElement('small');
            not.id = 'tp_tank_temp_note';
            not.style.cssText = 'display:block; font-size:12px; line-height:1.4;'
                + ' margin-top:4px; color:var(--hd-orange, #ff8c33); white-space:normal;';
            el.insertAdjacentElement('afterend', not);
        }
        not.textContent = TF('transient.tankTempDiffers',
            { panel: ekranSayisi(simdi, 2), motor: ekranSayisi(motorT, 2) },
            'You entered {panel} K here; the engine was designed with an oxidizer (tank) temperature of {motor} K. This run belongs to a different tank state than the engine result.');
    }
    function tankSicakligiTohumla() {
        const el = document.getElementById('tp_tank_temp');
        if (!el) return;
        // NK3-H-5: kutu N₂O tankının sıcaklığıdır; başka oksitleyicinin
        // sıcaklığı (LOX 90 K) bu kutuya yazılmaz, kip de regüleye döner.
        beslemeKipiniEsle();
        if (!kendindenBasincliN2OMu()) {
            const eskiNot = document.getElementById('tp_tank_temp_note');
            if (eskiNot) eskiNot.remove();
            return;
        }
        if (!(el.dataset && el.dataset.userOverride === 'true')) {
            el.value = String(Math.round(motorTankSicakligi() * 100) / 100);
        }
        tankSicakligiNotunuYaz();
    }

    // V306/UÇUŞ-3: yeni motor hesabında eski koşu ekrandan kalkar ve neden
    // yazılır (FEA panelleri / 6-DOF deseni, BAYAT NR-9).
    function eskiKosuyuTemizle(anahtar) {
        lastResult = null;
        lastResultSonuc = null;
        if (window.TransientPanel) window.TransientPanel.lastResult = null;
        const badges = document.getElementById('tp_badges');
        if (badges) badges.innerHTML = '';
        ['tp_plot', 'tp_tank_plot'].forEach(function (id) {
            const el = document.getElementById(id);
            if (!el) return;
            if (window.Plotly && Plotly.purge) { try { Plotly.purge(el); } catch (e) { /* yok */ } }
            el.innerHTML = '';
            el.style.display = 'none';
        });
        const expBtn = document.getElementById('tp_export');
        if (expBtn) expBtn.disabled = true;
        const status = document.getElementById('tp_status');
        if (status) {
            status.textContent = (anahtar === 'during')
                ? T('transient.staleDuringRun',
                    'The engine was recalculated while this run was solving; its result belongs to the earlier design and was not shown. Run it again.')
                : T('transient.staleRun',
                    'The engine was recalculated; the previous time-resolved result belonged to the earlier design and was cleared. Run it again.');
        }
    }

    // V306/UÇUŞ-3 — PROJE DOSYASI ZAMAN ÇÖZÜMLÜ AYARLARINI TAŞIR (M-HIBRIT-35).
    function projeDurumu() {
        const sel = document.getElementById('tp_feed_mode');
        const tt = document.getElementById('tp_tank_temp');
        const fl = document.getElementById('tp_fill');
        if (!sel) return null;
        return {
            format: 1,
            feed_mode: String(sel.value),
            feed_mode_user_chosen: !!(sel.dataset && sel.dataset.kullaniciSecti === '1'),
            tank_temp: tt ? String(tt.value) : '',
            tank_temp_user_typed: !!(tt && tt.dataset && tt.dataset.userOverride === 'true'),
            fill: fl ? String(fl.value) : '',
            fill_user_typed: !!(fl && fl.dataset && fl.dataset.userOverride === 'true'),
        };
    }
    function projeDurumunuKur(st) {
        lastResult = null;
        lastResultSonuc = null;
        if (window.TransientPanel) window.TransientPanel.lastResult = null;
        const sel = document.getElementById('tp_feed_mode');
        const tt = document.getElementById('tp_tank_temp');
        const fl = document.getElementById('tp_fill');
        const status = document.getElementById('tp_status');
        if (!sel) return false;
        if (!st || typeof st !== 'object') {
            if (status) status.textContent = T('transient.projectNoSetup',
                'This project file does not store the time-resolved settings (saved before 3.0.6): the feed mode follows the engine design and the tank temperature is filled from the engine oxidizer temperature after a calculation.');
            return false;
        }
        if (typeof st.feed_mode === 'string'
                && Array.prototype.some.call(sel.options || [], function (o) {
                    return o.value === st.feed_mode && !o.disabled; })) {
            sel.value = st.feed_mode;
            try { sel.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) { /* eski */ }
        }
        if (sel.dataset) {
            if (st.feed_mode_user_chosen) sel.dataset.kullaniciSecti = '1';
            else delete sel.dataset.kullaniciSecti;
        }
        [[tt, st.tank_temp, st.tank_temp_user_typed], [fl, st.fill, st.fill_user_typed]]
            .forEach(function (k) {
                const el = k[0];
                if (!el || typeof k[1] !== 'string') return;
                el.value = k[1];
                if (el.dataset) {
                    if (k[2]) el.dataset.userOverride = 'true';
                    else delete el.dataset.userOverride;
                }
            });
        if (status) status.textContent = '';
        tankSicakligiNotunuYaz();
        return true;
    }

    function ipucuHtml(id) {
        return '<span class="tooltip"><span class="tooltip-icon">?</span>'
            + '<span class="tooltip-text" id="' + id + '"></span></span>';
    }

    // İpucu metinleri parametreli (bant ve varsayılan sabitlerden); bu
    // yüzden `data-i18n` ile değil burada yazılır ve dil değişince tazelenir.
    function ipuclariniYaz() {
        const yaz = function (id, metin) {
            const el = document.getElementById(id);
            if (el) el.textContent = metin;
        };
        yaz('tp_feed_mode_tip', T('transient.feedModeTip',
            'How the oxidizer reaches the injector in this time march. '
            + 'Regulated: the oxidizer mass flow is held at its design value '
            + 'for the whole burn; no tank is modelled, so the fill fraction '
            + 'changes nothing and the tank temperature only enters as the N2O '
            + 'inlet temperature. N2O blowdown: a '
            + 'self-pressurising N2O tank holding the design oxidizer mass '
            + 'drives the flow; as it empties, tank pressure, thrust and Pc '
            + 'fall and the run can end before the design burn time (the end '
            + 'event is marked on the chart). Blowdown is disabled when the '
            + 'main design uses a user-set tank pressure. Choices: Regulated '
            + '(default) or N2O blowdown.'));
        yaz('tp_tank_temp_tip', TF('transient.tankTempTip', {
            t0: ekranSayisi(BOS_TANK_SICAKLIGI_K, 2),
            tmin: ekranSayisi(TANK_T_BANDI_K[0], 0),
            tmax: ekranSayisi(TANK_T_BANDI_K[1], 0),
        }, 'Initial N2O tank temperature, in K. In N2O blowdown mode it sets '
           + 'the starting vapour pressure and liquid density from the N2O '
           + 'saturation table, so it drives the flow. In Regulated mode the '
           + 'oxidizer flow is prescribed, so it does not drive the feed; it is '
           + 'still passed to the engine as the N2O inlet temperature, which '
           + 'shifts the curves only slightly. After each engine calculation it '
           + 'is filled with the engine Oxidizer Temperature (the tank temperature '
           + 'the engine was designed with); a value you type is kept and, if it '
           + 'differs from the engine value, the difference is shown below the '
           + 'field. Empty: the engine oxidizer temperature is sent, or {t0} K (the '
           + 'solver\'s default tank temperature) if the engine has none. Accepted (blowdown): '
           + '{tmin}–{tmax} K (saturation table band); a temperature outside '
           + 'the N2O liquid range is rejected in both modes with the reason.'));
        yaz('tp_fill_tip', TF('transient.fillFractionTip', {
            f0: ekranSayisi(BOS_DOLULUK_ORANI, 2),
            fmin: ekranSayisi(DOLULUK_BANDI[0], 2),
            fmax: ekranSayisi(DOLULUK_BANDI[1], 2),
        }, 'Fraction of the tank volume filled with liquid N2O at the start '
           + '(dimensionless, 0–1); the rest is vapour ullage. Read only in '
           + 'N2O blowdown mode: with the design oxidizer mass fixed it sets '
           + 'the tank volume, and so how fast the tank pressure falls. In '
           + 'Regulated mode it changes no number. Empty: {f0} is sent (the '
           + 'solver\'s default). Accepted: {fmin}–{fmax}; outside it the '
           + 'blowdown run is rejected with the reason.'));
    }

    function panelHtml() {
        return `
        <div class="panel" id="transientPanel" style="width:100%; grid-column: 1 / -1;">
            <h2><span data-i18n="transient.title">${T('transient.title',
                'Transient Analysis — Pc(t) / F(t)')}</span></h2>
            <div class="chart-explanation">
                <strong data-i18n="common.whatThisShows">${T('common.whatThisShows',
                    'What this shows:')}</strong>
                <span data-i18n="transient.intro">${T('transient.intro',
                    'Time-resolved chamber pressure and thrust from the quasi-steady '
                    + 'internal-ballistics march (Pc = mdot·c*/CD·At re-solved each step '
                    + 'with the instantaneous equilibrium c*). Blowdown mode couples a '
                    + 'self-pressurizing N2O tank with the classical injector '
                    + 'chug-stability margins (Sutton & Biblarz 9th ed. Ch. 8; NASA SP-194 Ch. 5-6).')}</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin:12px 0;">
                <div class="form-group">
                    <label for="tp_feed_mode"><span data-i18n="transient.feedMode">${
                        T('transient.feedMode', 'Feed Mode')}</span>${ipucuHtml('tp_feed_mode_tip')}</label>
                    <select id="tp_feed_mode">
                        <option value="regulated" data-i18n="transient.feedRegulated">${
                            T('transient.feedRegulated', 'Regulated (constant mass flow)')}</option>
                        <option value="blowdown" data-i18n="transient.feedBlowdown">${
                            T('transient.feedBlowdown', 'N2O Blowdown (self-pressurizing)')}</option>
                    </select>
                    <small id="tp_feed_note" style="display:none;" data-i18n="transient.blowdownUserTank">${
                        T('transient.blowdownUserTank', 'Blowdown is not available: this design uses a user-set tank pressure (pressurised feed), not a self-pressurising N2O tank. Use Regulated.')}</small>
                    <small id="tp_feed_note_ox" style="display:none;" data-i18n="transient.blowdownNotN2O">${
                        T('transient.blowdownNotN2O', 'Blowdown is not available: the tank blowdown model is for a self-pressurising N2O tank, and this design uses another oxidizer. Use Regulated.')}</small>
                </div>
                <div class="form-group" id="tp_tank_temp_group" style="display:none;">
                    <label for="tp_tank_temp"><span data-i18n="transient.tankTemp">${
                        T('transient.tankTemp', 'Tank Temperature (K)')}</span>${ipucuHtml('tp_tank_temp_tip')}</label>
                    <input type="number" id="tp_tank_temp" value="${BOS_TANK_SICAKLIGI_K}" step="0.5"
                           min="${TANK_T_BANDI_K[0]}" max="${TANK_T_BANDI_K[1]}">
                </div>
                <div class="form-group" id="tp_fill_group" style="display:none;">
                    <label for="tp_fill"><span data-i18n="transient.fillFraction">${
                        T('transient.fillFraction', 'Liquid Fill Fraction')}</span>${ipucuHtml('tp_fill_tip')}</label>
                    <input type="number" id="tp_fill" value="${BOS_DOLULUK_ORANI}" step="0.01"
                           min="${DOLULUK_BANDI[0]}" max="${DOLULUK_BANDI[1]}">
                </div>
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="tp_run"
                        data-i18n="transient.btnRun">${T('transient.btnRun',
                        'Run Transient')}</button>
                </div>
                <div class="form-group" style="align-self:end;">
                    <button class="btn" type="button" id="tp_export" disabled
                            data-i18n-title="transient.exportTip"
                            title="${T('transient.exportTip',
                                'Download the time-resolved curves as an Excel workbook (CSV fallback)')}"
                            data-i18n="transient.btnExport">${T('transient.btnExport',
                            'Export Excel')}</button>
                </div>
            </div>
            <div id="tp_status" style="font-family:var(--hd-mono); color:var(--hd-ink-dim); margin:6px 0;"></div>
            <div id="tp_badges" style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;"></div>
            <div id="tp_plot" class="plot-container" style="min-height:420px; display:none;"></div>
            <div id="tp_tank_plot" class="plot-container" style="min-height:360px; display:none;"></div>
        </div>`;
    }

    function badge(text, kind, title) {
        const colors = {
            ok: 'var(--hd-green, #2dd4a8)',
            warn: 'var(--hd-orange, #ff8c33)',
            err: 'var(--hd-red, #ff5d73)',
            info: 'var(--hd-cyan, #00e5ff)',
        };
        const c = colors[kind] || colors.info;
        const tip = title
            ? ` title="${String(title).replace(/"/g, '&quot;')}"` : '';
        return `<span${tip} style="border:1px solid ${c}; color:${c}; border-radius:6px;
                 padding:4px 10px; font-family:var(--hd-mono); font-size:0.75rem;">${text}</span>`;
    }

    // ÖH V3 taban-b · OH-UC-04 ekran ayağı — REGÜLELİ KİPTE TANK DURUMU.
    // Uç `transient.tank_state_role` bloğunu (7 çocuk) D33-2'den beri
    // yayımlıyor ama panel hiçbirini basmıyordu (sağır alt blok,
    // test_wave3_contract::test_sagir_alt_bloklar_buyumez). Kullanıcı tank
    // sıcaklığını girdiğinde bu kipte HİÇBİR sayının değişmediğini buradan
    // öğrenir. Sayı TÜRETİLMEZ: √ρ çarpanı ucun ölçtüğü alandır; yoksa
    // "ölçülmedi" denir (fail-closed). Blowdown kipinde blok null'dır →
    // rozet yok.
    function tankStateRoleBadge(tr) {
        const tsr = tr && tr.tank_state_role;
        if (!tsr || typeof tsr !== 'object') return '';
        // V301/PANEL (C-7, Grafik G1): N2O'da motor tank sıcaklığını GİRİŞ
        // DURUMU olarak yakar — sayılar onunla (az da olsa) değişir. Rozet
        // ucun beyanını aynen söyler; "kullanılmadı" yalnız uç öyle derse.
        if (tsr.used_by_this_model === true
            && tsr.used_as === 'motor_oxidizer_inlet_state') {
            const tKul = tsr.tank_temperature_K_received;
            return badge(T('transient.badgeTankTempInletOnly',
                           'TANK TEMPERATURE USED (regulated) · N2O inlet state only, feed not driven'),
                         'info',
                         TF('transient.tankTempInletOnlyTip', {
                             t: (typeof tKul === 'number' && isFinite(tKul))
                                 ? ekranSayisi(tKul, 1) : '?',
                         }, 'Regulated feed: the oxidizer flow is prescribed at its '
                            + 'design value, so the tank does not drive the feed and '
                            + 'the fill fraction changes no published number. The '
                            + 'motor burns N2O at the tank temperature you entered '
                            + '({t} K) as its inlet state, so the curves shift '
                            + 'slightly with it.'));
        }
        if (tsr.used_by_this_model !== false) {
            return '';
        }
        const tAl = tsr.tank_temperature_K_received;
        const ipucu = TF('transient.tankStateUnusedTip', {
            t: (typeof tAl === 'number' && isFinite(tAl)) ? ekranSayisi(tAl, 1) : '?',
        }, 'Regulated feed: the oxidizer flow is prescribed at its design value, '
           + 'so the tank temperature you entered ({t} K) and the fill fraction '
           + 'change no published number. A real regulator holds pressure, not '
           + 'density: mdot ∝ √ρ(T). The factor is the size of that dropped '
           + 'effect; it is not applied.');
        const duy = tsr.regulated_flow_temperature_sensitivity;
        const f = (duy && typeof duy === 'object')
            ? duy.implied_mdot_factor_sqrt_rho_ratio : null;
        if (typeof f === 'number' && isFinite(f)) {
            return badge(TF('transient.badgeTankStateUnused',
                            { f: ekranSayisi(f, 3) },
                            'TANK STATE NOT USED (regulated) · √(ρ(T)/ρ(T_ref)) = {f}'),
                         'warn', ipucu);
        }
        return badge(T('transient.badgeTankStateUnusedNoFactor',
                       'TANK STATE NOT USED (regulated) · √ρ factor NOT MEASURED'),
                     'warn', ipucu);
    }

    async function run() {
        const status = document.getElementById('tp_status');
        const badges = document.getElementById('tp_badges');
        const runBtn = document.getElementById('tp_run');
        runBtn.disabled = true;
        status.textContent = T('transient.solving', 'SOLVING TRANSIENT BALLISTICS…');
        badges.innerHTML = '';

        beslemeKipiniEsle();
        // V306/UÇUŞ-3: koşunun ait olduğu motor hesabı (başlangıç anında).
        const kosuSonucu = (typeof window !== 'undefined') ? (window.currentResults || null) : null;
        const payload = collectMotorParams();
        payload.feed_mode = document.getElementById('tp_feed_mode').value;
        payload.tank_temperature = tankGirdisi('tp_tank_temp', motorTankSicakligi());
        payload.liquid_fill_fraction = tankGirdisi('tp_fill', BOS_DOLULUK_ORANI);

        try {
            const resp = await fetch('/api/transient-analysis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!resp.ok || data.status !== 'success') {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }
            // V306/UÇUŞ-3 (UÇUŞ-2 DEVİR 2a): koşu sürerken motor yeniden
            // hesaplandıysa bu sonuç ESKİ tasarımındır — yeni sonuca
            // iliştirilmez ve gösterilmez (6-DOF onu "bu hesap" sanmasın).
            if (kosuSonucu !== (window.currentResults || null)) {
                eskiKosuyuTemizle('during');
                return;
            }
            lastResult = data;
            lastResultSonuc = kosuSonucu;
            window.TransientPanel.lastResult = data;
            render(data);
            const expBtn = document.getElementById('tp_export');
            if (expBtn) expBtn.disabled = false;

            // .eng export'u gerçek eğriyi kullansın diye motor sonucuna enjekte et
            if (window.currentResults && window.currentResults.motor) {
                window.currentResults.motor.transient = {
                    time: data.transient.time,
                    thrust: data.transient.thrust,
                };
            }
            // Dijital ikiz koşuyorsa transient veriyi ilet (plume/HUD ∝ itki)
            if (window.MotorViz3D && MotorViz3D.get && MotorViz3D.get()) {
                try { MotorViz3D.setTransient(data.transient); } catch (e) { /* eski sürüm */ }
            }
            status.textContent = '';
            tankSicakligiNotunuYaz();
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            runBtn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // V306/DİL-HİBRİT (NR-2 + UÇUŞ-3 DEVİR 1) — ROZETLERDE KULLANICI DİLİ
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/dil-hibrit/olcum/ekran_once_tr.json,
    // örnek hibrit, blowdown): TR ekranda rozetler ucun makine alan adını
    // basıyordu — "tank_phase_final vapor", "vapor_onset_s 10.41 s" (noktalı
    // ondalık), "residual_oxidizer_kg 1,618 kg", "vapor_phase_integrated
    // false", C_F sözleşmesinde "(engine.lambda_eff)", ayrılmada
    // "(summerfield)". Rozet artık sözlükteki etiketi basar; makine alan adı
    // `data-tp-field` / `data-tp-cutoff-field` niteliğinde kalır (ad+değer
    // bağı ve bekçilerin okuduğu kanal). Değerler ucun kendi alanlarıdır,
    // sayı türetilmez; tanınmayan kod değeri HAM ve "(?)" imli basılır
    // (sessiz yedek yok). Anahtarlar burada HARFİ HARFİNE yazılır (ölü-çeviri
    // bekçisi kaynakta arar).
    const TANK_FAZI = {
        two_phase: ['adv.js.tpPhaseTwoPhase', 'two-phase'],
        vapor: ['adv.js.tpPhaseVapor', 'vapor'],
    };
    const KAYNAK_ADI = {
        'engine.lambda_eff': ['adv.js.tpSrcLambdaEff', 'nozzle contour of the motor'],
        'engine.lambda_divergence': ['adv.js.tpSrcLambdaDiv', 'divergence factor of the motor'],
        'engine.headline_loss_set': ['adv.js.tpSrcLossSet', 'loss set of the motor design point'],
        user_supplied_thrust_coefficient: ['adv.js.tpSrcUserCf', 'your thrust coefficient'],
    };
    const AYRILMA_OLCUTU = {
        summerfield: ['adv.js.tpCritSummerfield', 'Summerfield criterion'],
    };
    function escHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function kodEtiketi(tablo, kod) {
        const ham = String(kod === null || kod === undefined ? '?' : kod);
        const kayit = Object.prototype.hasOwnProperty.call(tablo, ham)
            ? tablo[ham] : null;
        return kayit ? T(kayit[0], kayit[1]) : escHtml(ham) + ' (?)';
    }
    function evetHayir(v) {
        return v ? T('common.yes', 'yes') : T('common.no', 'no');
    }

    function render(data) {
        const tr = data.transient;
        const dp = data.design_point || {};
        const badges = document.getElementById('tp_badges');

        const eventKind = endEventKind(tr.end_event);
        let html = badge(T('transient.badgeEnd', 'END') + ': '
            + endEventLabel(tr.end_event), eventKind);
        html += badge(TF('transient.badgeBurn', { s: tr.burn_duration.toFixed(2) },
                         'BURN {s} s'), 'info');
        html += badge(TF('transient.badgeImpulse',
                         { v: (tr.total_impulse / 1000).toFixed(1) },
                         'IMPULSE {v} kN·s'), 'info');
        if (dp.total_impulse_design) {
            const ratio = 100 * tr.total_impulse / dp.total_impulse_design;
            html += badge(TF('transient.badgeVsDesign', { pct: ratio.toFixed(0) },
                             'vs DESIGN {pct}%'), ratio > 85 ? 'ok' : 'warn');
        }
        // C_F SÖZLEŞMESİ — geçici eğrinin taşıdığı sapma çarpanı ve kayıp
        // kümesi. Uç bunu `thrust_coefficient_contract` altında yayımlıyordu
        // (OH-D21-02, ÖH D22 hibrit a1: eğri tasarım itkisinin %1,87 üstünde
        // başlıyordu çünkü ikisi de taşınmıyordu) ama panel dört çocuğun
        // HİÇBİRİNİ basmıyordu — sağır blok
        // (test_wave3_contract::test_sagir_alt_bloklar_buyumez). Kullanıcı
        // eğrinin tasarım noktasıyla AYNI sözleşmeyi taşıdığını buradan görür;
        // gerekçe metni (`basis`) rozetin başlığında.
        const cfc = tr.thrust_coefficient_contract;
        const ls = (cfc && cfc.loss_set) || null;
        if (cfc && isFinite(cfc.divergence_efficiency) && ls) {
            html += badge(TF('transient.badgeCfContract', {
                lam: Number(cfc.divergence_efficiency).toFixed(4),
                lamSrc: kodEtiketi(KAYNAK_ADI, cfc.divergence_efficiency_source),
                loss: Number(ls.loss_product).toFixed(4),
                lossSrc: kodEtiketi(KAYNAK_ADI, ls.source),
            }, 'C_F CONTRACT lambda={lam} ({lamSrc}) - losses x{loss} ({lossSrc})'),
                'info', [cfc.basis, ls.scope].filter(Boolean).join(' | '));
        } else {
            // FAIL-CLOSED: sözleşme yayımlanmadıysa uydurma çarpan basılmaz,
            // eksikliğin kendisi görünür kılınır.
            html += badge(T('transient.cfContractMissing',
                            'C_F CONTRACT NOT PUBLISHED'), 'warn');
        }
        // ÖH D26 / OH-B4-04 — TANK FAZI. Çözücü fazı adım adım kaydediyor
        // ve blowdown kipinde yanmayı tam olarak `tank.phase === 'vapor'`
        // okumasıyla bitiriyor; bu bilgi eskiden yalnız `end_event` üzerinden,
        // faz ADI olmadan sızıyordu. Panel artık son fazı ve sıvının bittiği
        // ANI basar; seri varsa faz başına örnek sayısını da gösterir.
        // Değerler ucun kendi alanlarından gelir — hiçbiri uydurulmaz,
        // alan yoksa rozet HİÇ basılmaz (fail-closed).
        // V306/DİL-HİBRİT: etiket sözlükten, ondalık ekran kanalından
        // (`ekranSayisi`: TR virgül); makine adı `data-tp-field`'da.
        if (typeof tr.tank_phase_final === 'string' && tr.tank_phase_final) {
            html += '<span data-tp-field="tank_phase_final">'
                + badge(TF('adv.js.tpTankPhaseFinal',
                           { phase: kodEtiketi(TANK_FAZI, tr.tank_phase_final) },
                           'TANK PHASE AT END: {phase}'),
                        tr.tank_phase_final === 'vapor' ? 'warn' : 'info')
                + '</span>';
        }
        if (typeof tr.vapor_onset_s === 'number' && isFinite(tr.vapor_onset_s)) {
            html += '<span data-tp-field="vapor_onset_s">'
                + badge(TF('adv.js.tpVaporOnset',
                           { s: ekranSayisi(tr.vapor_onset_s, 2) },
                           'VAPOR PHASE ONSET {s} s'), 'warn')
                + '</span>';
        }
        if (Array.isArray(tr.tank_phase) && tr.tank_phase.length) {
            const fazSayim = {};
            tr.tank_phase.forEach(function (f) {
                fazSayim[f] = (fazSayim[f] || 0) + 1;
            });
            html += '<span data-tp-field="tank_phase">'
                + badge(TF('adv.js.tpTankPhaseSteps', {
                    list: Object.keys(fazSayim).sort()
                        .map(function (f) {
                            return kodEtiketi(TANK_FAZI, f) + ' ' + fazSayim[f];
                        }).join(' / '),
                }, 'TANK PHASE (solver steps): {list}'), 'info')
                + '</span>';
        }
        // ÖH D37 A1b panel-js · OH-D33-09 — KESMENİN BOYU VE HÜKMÜ.
        // ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/panel-js/a1/once/olcum.json
        // K3): uç blowdown kipinde bu beş alanı yayımlıyor (hibrit örnek:
        // residual_oxidizer_kg 2,42 kg; kesilen impuls 6450 N·s = toplamın
        // %26,5'i; vapor_phase_integrated false; kuyruk model zarfının
        // dışında true) ve bu panelde beşi de 0 kez geçiyordu — kesmenin
        // bedeli yalnız `warnings` serbest metninde sızıyordu. Kardeş
        // blowdown_panel.js aynı alanları D29'da kabloladı (OH-D28-03);
        // desen oradan: makine alan adı + değer AYNI rozette, sayı
        // TÜRETİLMEZ, alan yoksa (regüleli kipte dört alan null) rozet
        // YOK — null "0" ya da "false" diye basılmaz. Okuma AÇIK özellik
        // erişimiyle (ters-yön sözleşme envanteri, test_wave3_contract).
        // Ondalık ekran biçimlendiricisinden (TR virgül).
        // V306/DİL-HİBRİT: rozet metni sözlük etiketiyle (makine adı
        // `data-tp-cutoff-field`'da kalır — ad+değer bağı orada).
        const kesmeSayilari = [
            ['residual_oxidizer_kg', tr.residual_oxidizer_kg, 3,
             function (v) {
                 return TF('adv.js.tpResidualOx', { v: v },
                           'OXIDIZER LEFT IN TANK {v} kg');
             }],
            ['residual_impulse_at_cutoff_rate_Ns',
             tr.residual_impulse_at_cutoff_rate_Ns, 1,
             function (v) {
                 return TF('adv.js.tpResidualImpulse', { v: v },
                           'IMPULSE CUT OFF (at the cut-off rate) {v} N·s');
             }],
            ['residual_impulse_fraction_at_cutoff_rate',
             tr.residual_impulse_fraction_at_cutoff_rate, 4,
             function (v) {
                 return TF('adv.js.tpResidualFraction', { v: v },
                           'CUT-OFF IMPULSE FRACTION {v}');
             }],
        ];
        kesmeSayilari.forEach(function (k) {
            if (typeof k[1] !== 'number' || !isFinite(k[1])) return;
            html += '<span data-tp-cutoff-field="' + k[0] + '">'
                + badge(k[3](ekranSayisi(k[1], k[2])),
                        k[1] > 0 ? 'warn' : 'info')
                + '</span>';
        });
        // Bayrakların sınırlayan yönü (blowdown_panel.js FLAG_FIELDS ile
        // aynı): buhar fazı YÜRÜNMEDİYSE (false) ya da kuyruk model
        // zarfından ÇIKIYORSA (true) yayımlanan eğri tam çözüm değildir →
        // `warn`. Tank yalnız blowdown kipinde vardır; regüleli kipte uç
        // `vapor_phase_integrated` false yayımlar ama sınırlanan bir tank
        // kuyruğu yoktur → `info` (ad ve değer yine AYNEN basılır).
        const tankVar = tr.feed_mode === 'blowdown';
        const kesmeBayraklari = [
            ['vapor_phase_integrated', tr.vapor_phase_integrated, false,
             function (v) {
                 return TF('adv.js.tpVaporIntegrated', { v: v },
                           'VAPOR PHASE INTEGRATED: {v}');
             }],
            ['vapor_tail_off_leaves_model_envelope',
             tr.vapor_tail_off_leaves_model_envelope, true,
             function (v) {
                 return TF('adv.js.tpTailOffOutside', { v: v },
                           'VAPOR TAIL-OFF OUTSIDE THE MODEL ENVELOPE: {v}');
             }],
        ];
        kesmeBayraklari.forEach(function (b) {
            if (typeof b[1] !== 'boolean') return;
            html += '<span data-tp-cutoff-field="' + b[0] + '">'
                + badge(b[3](evetHayir(b[1])),
                        (tankVar && b[1] === b[2]) ? 'warn' : 'info')
                + '</span>';
        });
        // ÖH D27 · OH-B3-02 — EROZYON BLOĞU (5 çocuk, panelde 0'dı).
        // Sayı TÜRETİLMEZ: ucun kendi alanları basılır, alan yoksa rozet
        // yok. `basis` ve `model` rozetin başlığında (ipucu) durur ki
        // kullanıcı sayının hangi modelden geldiğini okuyabilsin.
        const ero = tr.erosion;
        if (ero && typeof ero === 'object') {
            const ipucu = [ero.basis, ero.model].filter(Boolean).join(' | ');
            if (ero.enabled === false) {
                html += badge(T('transient.badgeErosionOff', 'EROSION OFF'),
                              'info', ipucu);
            } else if (ero.status === 'no_samples'
                       || !isFinite(ero.total_recession_mm)) {
                // FAIL-CLOSED: örnek yoksa gerileme UYDURULMAZ.
                html += badge(T('transient.badgeErosionNoSamples',
                                'EROSION: NO SAMPLES'), 'warn', ipucu);
            } else {
                html += badge(TF('transient.badgeErosion', {
                    rec: Number(ero.total_recession_mm).toFixed(3),
                    d: Number(ero.final_throat_diameter_mm).toFixed(2),
                }, 'THROAT +{rec} mm (r), d_t {d} mm'), 'warn', ipucu);
            }
        }
        // ÖH D27 · OH-B3-02 — AKIŞ AYRILMASI BLOĞU (6 çocuk, panelde 0'dı).
        // `steps_floored = 0` da bir BİLGİDİR (eğri tümüyle yapışık akış
        // bandında kalmış) — bu yüzden rozet sıfırda da basılır.
        const fsep = tr.flow_separation;
        if (fsep && typeof fsep === 'object'
                && typeof fsep.steps_total === 'number') {
            // ÖH D27 a4 — FAIL-CLOSED (a2'nin bıraktığı borç).
            // Aşama-2 bu satırı çıplak bir sıfır yedeğiyle (Number(...)
            // ardından mantıksal VEYA sıfır)
            // yazmıştı: alan GELMEDİĞİNDE ekrana "0/N adım ayrıldı" diye
            // UYDURULMUŞ bir sıfır çıkıyordu ve rozet YEŞİL ('ok') oluyordu
            // — yani "ölçüm yok" ile "hiç ayrılma yok" aynı ekranı
            // veriyordu. tests/test_ui_no_fabricated_numbers.py'nin
            // beyansız-yedek bekçisi bunu KIRMIZI ile yakaladı.
            // Sayı yoksa sayı BASILMAZ; alanın adı söylenip reddedilir.
            const kirpik = (typeof fsep.steps_floored === 'number'
                            && isFinite(fsep.steps_floored))
                ? fsep.steps_floored : null;
            if (kirpik === null) {
                html += badge(T('transient.badgeSeparationUnknown',
                                'SEPARATION: steps_floored NOT REPORTED'),
                              'warn', fsep.basis);
            } else {
                html += badge(TF('transient.badgeSeparation', {
                    n: kirpik, total: fsep.steps_total,
                    crit: kodEtiketi(AYRILMA_OLCUTU, fsep.criterion),
                }, 'SEPARATION {n}/{total} steps ({crit})'),
                    kirpik > 0 ? 'warn' : 'ok', fsep.basis);
            }
            if (Number(fsep.steps_zero_clamped) > 0) {
                html += badge(TF('transient.badgeSeparationClamped',
                                 { n: fsep.steps_zero_clamped },
                                 'C_F CLAMPED TO ZERO {n} steps'),
                              'err', fsep.basis);
            }
        }
        // ÖH D30 · P11B5-20 — SUNUCU UYARISI: ÇEVİRİ KANALI + HAP BOYU.
        // ÖLÇÜLDÜ (a2/once.json: P11B5-20_ham_uyari_yayici = 1,
        // _srv_gecen_uyari = 0): `transient_ballistics.py` uyarıları TAM
        // CÜMLE olarak yayımlıyor (warnings_list, ör. chugging / erozyon /
        // besleme satırları) ve panel onları ham hâlde rozet hapının içine
        // basıyordu. İki kusur: (a) metin hiçbir çeviri kanalından
        // geçmiyordu — sayfanın geri kalanı Türkçeyken bu hap İngilizce
        // kalıyordu; kardeş yayıcılar sunucu metnini `SRV` ile geçirir
        // (app.js:15, i18n_charts sözlüğü — eşleşme yoksa metin AYNEN
        // döner, uydurma çeviri yok). (b) 100+ karakterlik cümle rozet
        // şeridini kaplıyordu. Hap ilk cümleye kırpılır, TAM metin
        // `title` ipucunda durur — bilgi KAYBI yok, sayı üretimi yok.
        const uyariRozeti = function (ham) {
            const metin = (window.SRV ? window.SRV(ham) : String(ham)).trim();
            const nokta = metin.search(/[.;](\s|$)/);
            const kisa = (nokta > 0 && nokta < 80) ? metin.slice(0, nokta)
                : (metin.length > 80 ? metin.slice(0, 79) + '\u2026' : metin);
            return badge(kisa, 'warn', metin);
        };
        html += tankStateRoleBadge(tr);
        (tr.warnings || []).forEach(w => { html += uyariRozeti(w); });
        badges.innerHTML = html;

        // v3.0.1 (V301/N-grafik G1) — F(t) ve Pc(t) İKİ AYRI ALT GRAFİK,
        // ORTAK ZAMAN EKSENİ. Düzen saf `zamanDuzeni` / `ikiAltGrafik`
        // yardımcılarından gelir (aşağıda; node bekçisi onları ölçer).
        // react: aynı div'e her koşuda / dil değişiminde tekrar çizilir;
        // newPlot'un tam yıkım+kurulumu yerine fark tabanlı güncelleme
        // (plotly 1.34+; ilk çizimde kendiliğinden newPlot'a düşer)
        const duzen = zamanDuzeni(tr, dp);
        const plotDiv = document.getElementById('tp_plot');
        plotDiv.style.display = 'block';
        const ana = ikiAltGrafik(duzen, tr.time,
            { y: tr.thrust, name: T('transient.sThrust', 'Thrust [N]'),
              axis: T('transient.sThrust', 'Thrust [N]'), tozero: true },
            { y: toBar(tr.chamber_pressure),
              name: T('transient.sPc', 'Chamber Pressure [bar]'),
              axis: 'P_c [bar]', tozero: true },
            T('transient.chartMain', 'Transient Thrust & Chamber Pressure'),
            GECICI_ANA_YUKSEKLIK_PX);
        Plotly.react(plotDiv, ana.data, ana.layout,
                     { responsive: true, displaylogo: false });

        // Blowdown tank geçmişi — aynı ilke: P_tank ve T_tank ayrı alt
        // grafiklerde, ana grafikle AYNI zaman aralığı ve işaretler.
        const tankDiv = document.getElementById('tp_tank_plot');
        if (tr.feed_mode === 'blowdown' && tr.tank_pressure && tr.tank_pressure.length) {
            tankDiv.style.display = 'block';
            const tank = ikiAltGrafik(duzen, tr.time,
                { y: toBar(tr.tank_pressure),
                  name: T('transient.sTankP', 'Tank Pressure [bar]'),
                  axis: 'P_tank [bar]' },
                { y: tr.tank_temperature,
                  name: T('transient.sTankT', 'Tank Temperature [K]'),
                  axis: 'T_tank [K]' },
                T('transient.chartTank', 'N2O Tank Blowdown History'),
                GECICI_TANK_YUKSEKLIK_PX);
            Plotly.react(tankDiv, tank.data, tank.layout,
                         { responsive: true, displaylogo: false });
        } else {
            tankDiv.style.display = 'none';
        }
    }

    // ------------------------------------------------------------------
    // v3.0.1 (V301/N-grafik G1) — ZAMAN EKSENİ: TASARIM YANMA SÜRESİ +
    // ERKEN BİTİŞ GÖRÜNÜR
    // ------------------------------------------------------------------
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/grafik/RAPOR.md, G1 önce):
    // x ekseni yalnız çözücünün döndürdüğü aralığı gösteriyordu
    // ([t_ilk, t_son]); blowdown koşusu 9,10 s'de `injector_unstable` ile
    // bittiğinde tasarımın 10 s'lik yanmasına göre ne kadar erken bittiği
    // ekranda okunmuyordu. F(t) ile Pc(t) aynı çizim alanında iki eksendeydi;
    // regüleli kipte iki eğri normalize değerde tam üst üste biniyordu
    // (binme oranı 1,000) ve lejant başlığın hemen altına sıkışıyordu.
    //
    // Kural: eksen en az [0, max(t_son, t_b)] — t_b ucun `design_point.
    // burn_time` alanı (sayı TÜRETİLMEZ; alan yoksa çizgi de yok). Eğri
    // YALNIZ çözücünün noktalarından çizilir: t = 0 noktası dönmüyorsa
    // eklenmez, eksen aralığı nokta değildir. Çözücü tasarım süresinden
    // önce ya da başka bir olayla bittiyse bitiş anı dikey çizgi + olay
    // etiketiyle (endEventLabel, fail-closed) işaretlenir.
    const GECICI_ANA_YUKSEKLIK_PX = 560;
    const GECICI_TANK_YUKSEKLIK_PX = 480;
    // Alt grafiklerin dikey payları (kâğıt kesri): üst [0,54 – 1],
    // alt [0 – 0,44]; aradaki boşluk bitiş etiketinin şeridi.
    const UST_ALAN = [0.54, 1];
    const ALT_ALAN = [0, 0.44];
    // Eksenin sağ ucuna pay: t_b çizgisi çerçeveye yapışmasın (görsel pay,
    // veri değil).
    const ZAMAN_PAYI = 0.025;
    // Grafikteki bitiş işaretinin rengi rozetle AYNI tema rengi: değerler
    // `badge()`taki tema jetonlarının yedek onaltılıklarıdır (rozet kendi
    // içinde kapalı kalmalı — test_v3_taban_b onu kaynaktan tek başına
    // çıkarıp koşar). Eşitliği tests/test_v301_gecici_zaman_ekseni.py ölçer.
    // Plotly CSS değişkeni okuyamadığı için onaltılık gerekir.
    const OLAY_RENGI = {
        ok: '#2dd4a8', info: '#00e5ff', warn: '#ff8c33', err: '#ff5d73',
    };
    const TB_RENGI = 'rgba(207, 232, 242, 0.8)';

    function sonluSon(dizi) {
        if (!Array.isArray(dizi)) return null;
        for (let i = dizi.length - 1; i >= 0; i--) {
            const v = dizi[i];
            if (typeof v === 'number' && isFinite(v)) return v;
        }
        return null;
    }

    // SAF: DOM'a dokunmaz. {xMax, tSon, tb, erken, olay, shapes, annotations}
    // `secenek.bitisY` / `secenek.bitisYanchor`: bitiş etiketinin dikey yeri
    // (kâğıt kesri). Varsayılan iki alt grafiğin arasındaki şerit; tek
    // çizim alanlı grafikte (blowdown paneli) çizim alanının dibi.
    function zamanDuzeni(tr, dp, secenek) {
        tr = tr || {};
        secenek = secenek || {};
        const tSon = sonluSon(tr.time);
        const tbHam = dp ? dp.burn_time : null;
        const tb = (typeof tbHam === 'number' && isFinite(tbHam) && tbHam > 0)
            ? tbHam : null;
        const ust = Math.max(tSon === null ? 0 : tSon, tb === null ? 0 : tb);
        const xMax = ust > 0 ? ust * (1 + ZAMAN_PAYI) : null;
        const olay = (tr.end_event === null || tr.end_event === undefined)
            ? '' : String(tr.end_event);
        // Erken / farklı bitiş: olay `burn_time_reached` değilse ya da
        // çözücü tasarım süresinden belirgin önce durduysa (bir adımdan
        // fazla). Olay adı yoksa etiket "?" olur — sessizce "tamam" sayılmaz.
        const adim = (Array.isArray(tr.time) && tr.time.length > 1)
            ? Math.abs(tr.time[1] - tr.time[0]) : 0;
        const erken = tSon !== null && (olay !== 'burn_time_reached'
            || (tb !== null && tSon < tb - Math.max(adim, 1e-9)));
        const shapes = [];
        const annotations = [];
        const yon = function (x) {
            return (xMax && x / xMax > 0.5) ? 'right' : 'left';
        };
        if (tb !== null) {
            shapes.push({ type: 'line', xref: 'x', yref: 'paper',
                x0: tb, x1: tb, y0: 0, y1: 1,
                line: { color: TB_RENGI, width: 1.5, dash: 'dash' } });
            annotations.push({ xref: 'x', yref: 'paper', x: tb, y: 1,
                xanchor: yon(tb), yanchor: 'bottom', showarrow: false,
                font: { size: 12, color: TB_RENGI },
                text: TF('transient.designBurnMarker', { s: ekranSayisi(tb, 2) },
                         'design burn time t_b = {s} s') });
        }
        if (erken) {
            const renk = OLAY_RENGI[endEventKind(olay)] || OLAY_RENGI.warn;
            shapes.push({ type: 'line', xref: 'x', yref: 'paper',
                x0: tSon, x1: tSon, y0: 0, y1: 1,
                line: { color: renk, width: 2, dash: 'dot' } });
            annotations.push({ xref: 'x', yref: 'paper', x: tSon,
                y: (typeof secenek.bitisY === 'number')
                    ? secenek.bitisY : (UST_ALAN[0] + ALT_ALAN[1]) / 2,
                xanchor: yon(tSon), yanchor: secenek.bitisYanchor || 'middle',
                showarrow: false,
                font: { size: 12, color: renk },
                text: TF('transient.endMarker', {
                    event: endEventLabel(olay) || '?',
                    s: ekranSayisi(tSon, 2),
                }, 'end: {event} · t = {s} s') });
        }
        return { xMax: xMax, tSon: tSon, tb: tb, erken: erken, olay: olay,
                 shapes: shapes, annotations: annotations };
    }

    // Eski çizimle aynı ölçek kuralı: F ve Pc sıfırdan (rangemode
    // 'tozero'), tank basıncı/sıcaklığı kendi aralığında (tozero yok —
    // 300 → 280 K'lik düşüş sıfırdan başlayan eksende düz çizgi olurdu).
    function yEkseni(alan, xId, iz) {
        const ax = { domain: alan.slice(), anchor: xId, title: iz.axis };
        if (iz.tozero) ax.rangemode = 'tozero';
        return ax;
    }

    // SAF: iki izi iki alt grafiğe dağıtır (ortak zaman ekseni, x = tr.time
    // AYNEN). Lejant kapalı: her alt grafiğin kendi eksen başlığı izi adlar;
    // ad hover'da da görünür.
    function ikiAltGrafik(duzen, zaman, ust, alt, baslik, yukseklik) {
        const aralik = duzen.xMax ? [0, duzen.xMax] : undefined;
        const xOrtak = function (ek) {
            const ax = Object.assign({ zeroline: false }, ek);
            if (aralik) { ax.range = aralik.slice(); ax.autorange = false; }
            return ax;
        };
        return {
            data: [
                // Renk tema renk sırasından (plotly_dark COLORWAY).
                { x: zaman, y: ust.y, name: ust.name, mode: 'lines',
                  xaxis: 'x', yaxis: 'y', line: { width: 2.5 } },
                { x: zaman, y: alt.y, name: alt.name, mode: 'lines',
                  xaxis: 'x2', yaxis: 'y2', line: { width: 2.5 } },
            ],
            layout: {
                title: { text: baslik },
                showlegend: false,
                height: yukseklik,
                margin: { t: 96, b: 64, l: 84, r: 36 },
                xaxis: xOrtak({ anchor: 'y', matches: 'x2', showticklabels: false }),
                xaxis2: xOrtak({ anchor: 'y2',
                                 title: T('common.axis.timeS2', 'Time [s]') }),
                yaxis: yEkseni(UST_ALAN, 'x', ust),
                yaxis2: yEkseni(ALT_ALAN, 'x2', alt),
                shapes: duzen.shapes.map(function (s) {
                    return JSON.parse(JSON.stringify(s)); }),
                annotations: duzen.annotations.map(function (a) {
                    return JSON.parse(JSON.stringify(a)); }),
            },
        };
    }

    function init(opts) {
        opts = opts || {};
        const anchor = document.getElementById(opts.anchorId || 'trajectoryPanel');
        const host = document.createElement('div');
        host.innerHTML = panelHtml();
        const panel = host.firstElementChild;
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(panel, anchor);
        } else {
            (document.querySelector('.results-grid') || document.body).appendChild(panel);
        }
        document.getElementById('tp_run').addEventListener('click', run);
        const expBtn = document.getElementById('tp_export');
        if (expBtn) expBtn.addEventListener('click', exportCurves);
        // V306/UÇUŞ-3: yalnız gerçek yazma "elle yazıldı" damgası bırakır.
        ['tp_tank_temp', 'tp_fill'].forEach(function (id) {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('input', function (e) {
                if (e && e.isTrusted && el.dataset) el.dataset.userOverride = 'true';
                if (id === 'tp_tank_temp') tankSicakligiNotunuYaz();
            });
        });
        // Hesap köprüsü (FEA panelleri deseni): yeni motor hesabında eski
        // eğri temizlenir ve tank sıcaklığı motorun girdisinden tohumlanır.
        (function () {
            const ozgun = window.displayCalculationResults;
            if (typeof ozgun !== 'function') return;
            window.displayCalculationResults = function (results) {
                const out = ozgun.apply(this, arguments);
                try {
                    if (lastResult && lastResultSonuc && results !== lastResultSonuc) {
                        eskiKosuyuTemizle('new');
                    }
                    tankSicakligiTohumla();
                } catch (e) { /* panel hatası hesabı engellemez */ }
                return out;
            };
        })();
        document.getElementById('tp_feed_mode').addEventListener('change', function () {
            this.dataset.kullaniciSecti = '1';
            const bd = this.value === 'blowdown';
            document.getElementById('tp_tank_temp_group').style.display = bd ? '' : 'none';
            document.getElementById('tp_fill_group').style.display = bd ? '' : 'none';
        });
        // v3.0.1 (V301/H4): seçici her açılışta ana tasarımın tank kipine eşlenir.
        ['focus', 'mousedown'].forEach(function (ev) {
            document.getElementById('tp_feed_mode').addEventListener(ev, beslemeKipiniEsle);
        });
        beslemeKipiniEsle();
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        ipuclariniYaz();
        // Dil değişince rozetler/grafik başlıkları saklanan sonuçla yeniden basılır
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
                ipuclariniYaz();
                if (lastResult) {
                    try { render(lastResult); } catch (e) { /* çizim yoksa sessiz */ }
                }
            });
        }
    }

    // Zaman-cozumlu egrileri Excel olarak indir (sunucu openpyxl ile uretir;
    // uretemezse CSV'ye duser). Berke istegi: transient sonuclari bilgisayara
    // inebilsin.
    // Dışa aktarım tablosu — SAF (DOM'a dokunmaz), böylece birim sözleşmesi
    // testten doğrudan ölçülebilir: her sütun başlığının yazdığı birim ile
    // hücrenin taşıdığı sayı aynı olmak zorunda.
    // {headers, rows} döner.
    function buildExportTable(t) {
        t = t || {};
        const headers = [T('transient.colTime', 'Time (s)'),
                         T('transient.colThrust', 'Thrust (N)'),
                         T('transient.colPc', 'Chamber pressure (bar)')];
        // Başlık 'bar' diyor -> hücre de bar olmak ZORUNDA (API Pascal verir).
        const cols = [t.time || [], t.thrust || [], toBar(t.chamber_pressure)];
        if (t.of_ratio && t.of_ratio.length) {
            headers.push(T('transient.colOf', 'O/F ratio')); cols.push(t.of_ratio);
        }
        if (t.port_diameter && t.port_diameter.length) {
            headers.push(T('transient.colPort', 'Port diameter (mm)'));
            cols.push(t.port_diameter.map(function (v) { return v * 1000; }));
        }
        if (t.tank_pressure && t.tank_pressure.length) {
            headers.push(T('transient.colTankP', 'Tank pressure (bar)'));
            // Aynı gerekçe: tank basıncı da Pascal gelir.
            cols.push(toBar(t.tank_pressure));
        }
        if (t.tank_temperature && t.tank_temperature.length) {
            headers.push(T('transient.colTankT', 'Tank temperature (K)'));
            cols.push(t.tank_temperature);
        }
        // reduce: `Math.max.apply(null, [])` -Infinity döndürüyordu (boş
        // sonuçta sonsuz döngü riski).
        const n = cols.reduce(function (m, c) { return Math.max(m, c.length); }, 0);
        const rows = [];
        for (let i = 0; i < n; i++) {
            rows.push(cols.map(function (c) {
                return (c[i] === undefined || c[i] === null) ? '' : c[i];
            }));
        }
        return { headers: headers, rows: rows };
    }

    async function exportCurves() {
        if (!lastResult || !lastResult.transient) return;
        const table = buildExportTable(lastResult.transient);
        const headers = table.headers;
        const rows = table.rows;

        const motor = (window.currentResults && window.currentResults.motor) || {};
        const name = motor.motor_name || 'HRMA_Motor';
        const stamp = new Date().toISOString().split('T')[0];
        const fname = name + '_transient_' + stamp + '.xlsx';

        const download = function (blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            window.URL.revokeObjectURL(url); document.body.removeChild(a);
        };

        try {
            const resp = await fetch('/api/export-xlsx', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    filename: fname,
                    sheets: [{name: 'Transient', headers: headers, rows: rows}]
                })
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            download(await resp.blob(), fname);
        } catch (e) {
            console.warn('XLSX export unavailable, falling back to CSV:', e);
            const esc = function (v) {
                const x = (v === null || v === undefined) ? '' : String(v);
                // Formul enjeksiyonu (CWE-1236): elektronik tablolar '=' '+' '-' '@'
                // ve sekme/CR ile baslayan METNI formul/komut sayabilir. Sayi
                // gorunen degerlere (-5000, +3.2e4) DOKUNULMAZ, yoksa veri bozulur.
                var y = x;
                if (/^[=+\-@\t\r]/.test(y) && !(y !== '' && isFinite(Number(y)))) { y = "'" + y; }
                return /[",\n]/.test(y) ? '"' + y.replace(/"/g, '""') + '"' : y;
            };
            const lines = [headers.map(esc).join(',')];
            rows.forEach(function (r) { lines.push(r.map(esc).join(',')); });
            download(new Blob([lines.join('\n')], {type: 'text/csv;charset=utf-8;'}),
                     fname.replace(/\.xlsx$/, '.csv'));
        }
    }

    window.TransientPanel = { init, run, lastResult: null,
        // V306/UÇUŞ-3: proje şeridinin kayıt/açılış kancaları.
        projeDurumu: projeDurumu,
        projeDurumunuKur: projeDurumunuKur,
        _motorTankSicakligi: motorTankSicakligi,
        // Test / hata ayıklama: saf dışa aktarım tablosu (DOM'suz).
        // injector_panel._renderHtml ile aynı desen.
        _buildExportTable: buildExportTable,
        _toBar: toBar,
        // ÖH D34 / OH-GT-05 bekçisi: bitiş olayının etiketi ve rozeti
        // DOM'suz ölçülsün diye dışa açık (yalnız test/hata ayıklama).
        _endEventKind: endEventKind,
        _endEventLabel: endEventLabel,
        _endEventKindMap: END_EVENTS,
        // ÖH D37 A1b panel-js · OH-D33-09 bekçisi: rozet şeridi DOM
        // saplamasıyla node'da ölçülsün diye (yalnız test/hata ayıklama).
        _render: render,
        // v3.0.1 bekçisi: gövde ana istekten mi formdan mı kuruluyor,
        // node'da DOM saplamasıyla ölçülsün diye (yalnız test/hata ayıklama).
        _collectMotorParams: collectMotorParams,
        // v3.0.1 (V301/H4) bekçisi: blowdown seçeneğinin tank kipine eşlenmesi.
        _beslemeKipiniEsle: beslemeKipiniEsle,
        // v3.0.1 (V301/N-grafik G1/G3): zaman ekseni düzeni TEK uygulama;
        // hibrit sayfasının blowdown paneli de aynı işlevi kullanır
        // (eksen [0, max(t_son, t_b)], t_b çizgisi, bitiş işareti).
        zamanEkseniDuzeni: zamanDuzeni,
        // Bekçi: zaman ekseni düzeni ve alt grafik figürü DOM'suz ölçülsün
        // diye (yalnız test/hata ayıklama).
        _zamanDuzeni: zamanDuzeni,
        _ikiAltGrafik: ikiAltGrafik,
        _tankGirdisi: tankGirdisi,
        get result() { return lastResult; } };
})();
