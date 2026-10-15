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

    // advanced.html form alanlarından motor parametrelerini topla
    // (calculate() payload'ıyla aynı ID'ler; yalnız transient'in ihtiyacı olanlar)
    function collectMotorParams() {
        const num = (id, d) => {
            const el = document.getElementById(id);
            const v = el ? parseFloat(el.value) : NaN;
            return isFinite(v) ? v : d;
        };
        const str = (id, d) => {
            const el = document.getElementById(id);
            return el && el.value ? el.value : d;
        };
        return {
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
                    <label data-i18n="transient.feedMode">${T('transient.feedMode', 'Feed Mode')}</label>
                    <select id="tp_feed_mode">
                        <option value="regulated" data-i18n="transient.feedRegulated">${
                            T('transient.feedRegulated', 'Regulated (constant mass flow)')}</option>
                        <option value="blowdown" data-i18n="transient.feedBlowdown">${
                            T('transient.feedBlowdown', 'N2O Blowdown (self-pressurizing)')}</option>
                    </select>
                </div>
                <div class="form-group" id="tp_tank_temp_group" style="display:none;">
                    <label data-i18n="transient.tankTemp">${T('transient.tankTemp',
                        'Tank Temperature (K)')}</label>
                    <input type="number" id="tp_tank_temp" value="293.15" step="0.5" min="245" max="305">
                </div>
                <div class="form-group" id="tp_fill_group" style="display:none;">
                    <label data-i18n="transient.fillFraction">${T('transient.fillFraction',
                        'Liquid Fill Fraction')}</label>
                    <input type="number" id="tp_fill" value="0.85" step="0.01" min="0.5" max="0.95">
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
        if (!tsr || typeof tsr !== 'object' || tsr.used_by_this_model !== false) {
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

        const payload = collectMotorParams();
        payload.feed_mode = document.getElementById('tp_feed_mode').value;
        payload.tank_temperature = parseFloat(document.getElementById('tp_tank_temp').value) || 293.15;
        payload.liquid_fill_fraction = parseFloat(document.getElementById('tp_fill').value) || 0.85;

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
            lastResult = data;
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
        } catch (err) {
            status.textContent = TF('common.errorPrefix', { message: err.message },
                                    'ERROR: {message}');
        } finally {
            runBtn.disabled = false;
        }
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
                lamSrc: cfc.divergence_efficiency_source,
                loss: Number(ls.loss_product).toFixed(4),
                lossSrc: ls.source,
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
        if (typeof tr.tank_phase_final === 'string' && tr.tank_phase_final) {
            html += badge('tank_phase_final ' + tr.tank_phase_final,
                          tr.tank_phase_final === 'vapor' ? 'warn' : 'info');
        }
        if (typeof tr.vapor_onset_s === 'number' && isFinite(tr.vapor_onset_s)) {
            html += badge('vapor_onset_s ' + tr.vapor_onset_s.toFixed(2) + ' s',
                          'warn');
        }
        if (Array.isArray(tr.tank_phase) && tr.tank_phase.length) {
            const fazSayim = {};
            tr.tank_phase.forEach(function (f) {
                fazSayim[f] = (fazSayim[f] || 0) + 1;
            });
            html += badge('tank_phase ' + Object.keys(fazSayim).sort()
                .map(function (f) { return f + ' ' + fazSayim[f]; })
                .join(' / '), 'info');
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
        const kesmeSayilari = [
            ['residual_oxidizer_kg', tr.residual_oxidizer_kg, 3, ' kg'],
            ['residual_impulse_at_cutoff_rate_Ns',
             tr.residual_impulse_at_cutoff_rate_Ns, 1, ' N·s'],
            ['residual_impulse_fraction_at_cutoff_rate',
             tr.residual_impulse_fraction_at_cutoff_rate, 4, ''],
        ];
        kesmeSayilari.forEach(function (k) {
            if (typeof k[1] !== 'number' || !isFinite(k[1])) return;
            html += '<span data-tp-cutoff-field="' + k[0] + '">'
                + badge(k[0] + ' ' + ekranSayisi(k[1], k[2]) + k[3],
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
            ['vapor_phase_integrated', tr.vapor_phase_integrated, false],
            ['vapor_tail_off_leaves_model_envelope',
             tr.vapor_tail_off_leaves_model_envelope, true],
        ];
        kesmeBayraklari.forEach(function (b) {
            if (typeof b[1] !== 'boolean') return;
            html += '<span data-tp-cutoff-field="' + b[0] + '">'
                + badge(b[0] + ' ' + (b[1] ? 'true' : 'false'),
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
                    crit: String(fsep.criterion || '?'),
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

        // F(t) + Pc(t) çift eksen (plotly_dark otomatik koyu temalar)
        // react: aynı div'e her koşuda / dil değişiminde tekrar çizilir;
        // newPlot'un tam yıkım+kurulumu yerine fark tabanlı güncelleme
        // (plotly 1.34+; ilk çizimde kendiliğinden newPlot'a düşer)
        const plotDiv = document.getElementById('tp_plot');
        plotDiv.style.display = 'block';
        Plotly.react(plotDiv, [
            { x: tr.time, y: tr.thrust, name: T('transient.sThrust', 'Thrust [N]'),
              mode: 'lines', line: { width: 3 } },
            { x: tr.time, y: toBar(tr.chamber_pressure),
              name: T('transient.sPc', 'Chamber Pressure [bar]'), mode: 'lines', yaxis: 'y2',
              line: { width: 2, dash: 'dot' } },
        ], {
            title: T('transient.chartMain', 'Transient Thrust & Chamber Pressure'),
            xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
            yaxis: { title: T('transient.sThrust', 'Thrust [N]'), rangemode: 'tozero' },
            yaxis2: { title: 'P_c [bar]', overlaying: 'y', side: 'right',
                      rangemode: 'tozero' },
            height: 420,
            legend: { orientation: 'h', y: 1.12 },
        }, { responsive: true, displaylogo: false });

        // Blowdown tank geçmişi
        const tankDiv = document.getElementById('tp_tank_plot');
        if (tr.feed_mode === 'blowdown' && tr.tank_pressure && tr.tank_pressure.length) {
            tankDiv.style.display = 'block';
            // react: aynı div'e tekrar çizim (bkz. tp_plot notu)
            Plotly.react(tankDiv, [
                { x: tr.time, y: toBar(tr.tank_pressure),
                  name: T('transient.sTankP', 'Tank Pressure [bar]'), mode: 'lines',
                  line: { width: 3 } },
                { x: tr.time, y: tr.tank_temperature,
                  name: T('transient.sTankT', 'Tank Temperature [K]'), mode: 'lines', yaxis: 'y2',
                  line: { width: 2, dash: 'dot' } },
            ], {
                title: T('transient.chartTank', 'N2O Tank Blowdown History'),
                xaxis: { title: T('common.axis.timeS2', 'Time [s]') },
                yaxis: { title: 'P_tank [bar]' },
                yaxis2: { title: 'T_tank [K]', overlaying: 'y', side: 'right' },
                height: 360,
                legend: { orientation: 'h', y: 1.14 },
            }, { responsive: true, displaylogo: false });
        } else {
            tankDiv.style.display = 'none';
        }
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
        document.getElementById('tp_feed_mode').addEventListener('change', function () {
            const bd = this.value === 'blowdown';
            document.getElementById('tp_tank_temp_group').style.display = bd ? '' : 'none';
            document.getElementById('tp_fill_group').style.display = bd ? '' : 'none';
        });
        if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(panel);
        // Dil değişince rozetler/grafik başlıkları saklanan sonuçla yeniden basılır
        if (window.I18N && window.I18N.onChange) {
            window.I18N.onChange(function () {
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
        get result() { return lastResult; } };
})();
