/* ====================================================================
   HRMA Analiz Güvertesi — Lüle Akışı Paneli (Dalga 4A)
   --------------------------------------------------------------------
   POST /api/flow-analysis sonuçlarını çizer (sahte CFD panelinin halefi:
   quasi-1D sıkıştırılabilir akış, docs/ANALIZ_PLATFORM_PLANI.md).

   Fidelity seçici:
     fast        → izantropik özet (rejim + CF/itki kartları)
     engineering → tam istasyon dizileri (P(x), M(x)) + Bartz + kinetik zincir
   Cantera sonlu hızlı kinetik seçeneği yalnız Cantera mevcutsa listelenir —
   tespit /api/kinetic-efficiency {probe:true} yanıtının fidelity_used
   alanından yapılır (backend sözleşmesi).

   Yanıt şeması (test_client ile doğrulandı, 2026-07-14):
     { status:'success', fidelity, flow:{stations?, throat, regime,
       performance, losses, inputs}, kinetic_efficiency|null, kinetic_note? }

   Koyu tema plotly_dark.js sarmalayıcısından merkezi gelir.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu

    const ENDPOINT = '/api/flow-analysis';
    const KINETIC_ENDPOINT = '/api/kinetic-efficiency';
    const PANEL_ID = 'flow';

    // Rejim rozetleri — separated/şok/boğulmamış KIRMIZI (görev sözleşmesi)
    const REGIME_INFO = {
        underexpanded: { key: 'nzl.regimeUnderexpanded', label: 'UNDEREXPANDED', kind: 'info' },
        perfectly_expanded: { key: 'nzl.regimePerfect', label: 'PERFECT EXPANSION', kind: 'ok' },
        overexpanded: { key: 'nzl.regimeOverexpanded', label: 'OVEREXPANDED', kind: 'warn' },
        separated: { key: 'nzl.regimeSeparated', label: 'SEPARATED', kind: 'err' },
        normal_shock_in_nozzle: { key: 'nzl.regimeShock', label: 'NORMAL SHOCK IN NOZZLE', kind: 'err' },
        unchoked: { key: 'nzl.regimeUnchoked', label: 'UNCHOKED', kind: 'err' },
    };

    function regimeInfo(type) {
        const found = REGIME_INFO[type];
        if (found) return { label: T(found.key, found.label), kind: found.kind };
        return { label: String(type || T('common.unknown', 'UNKNOWN')).toUpperCase(), kind: 'dim' };
    }

    // V301/PANEL-SAYI (KILAVUZ P4) — ekrandaki sayı dile göre ayraçla basılır
    // (TR virgül). Sayı yoksa EM TİRE (U.fmt ile aynı sözleşme); sayı
    // DEĞİŞMEZ, yalnız ayraç yerelleşir (U.num → I18N.number).
    function fmtL(x, d) {
        return (typeof x !== 'number' || !Number.isFinite(x)) ? '—' : U.num(x, d);
    }

    /* V301/PANEL-SAYI (KILAVUZ P4) — REJİM CÜMLESİ EKRAN DİLİNDE.
       Çözücünün altı sabit rejim cümlesi (nozzle_flow_1d._classify_regime)
       TR ekranda İngilizce basılıyordu ("Perfectly expanded: …"). TR'de
       sözlükteki Türkçe karşılığı basılır; çözücünün cümlesi kapalı
       "Teknik ayrıntı (çözücü beyanı, çevrilmedi)" altında AYNEN durur
       (DİL-2 terim kararı 2 deseni). EN'de cümle olduğu gibi. */
    const REJIM_CUMLESI = {
        underexpanded: 'panel.nzl.regimeDesc.underexpanded',
        perfectly_expanded: 'panel.nzl.regimeDesc.perfectly_expanded',
        overexpanded: 'panel.nzl.regimeDesc.overexpanded',
        separated: 'panel.nzl.regimeDesc.separated',
        normal_shock_in_nozzle: 'panel.nzl.regimeDesc.normal_shock_in_nozzle',
        unchoked: 'panel.nzl.regimeDesc.unchoked',
    };
    function dilTr() {
        return !!(window.I18N && window.I18N.lang === 'tr');
    }
    function rejimCumlesiHtml(regime) {
        const ham = String((regime && regime.description) || '');
        if (!ham) return '';
        const anahtar = REJIM_CUMLESI[regime.type];
        if (!dilTr() || !anahtar) return U.esc(ham);
        return U.esc(T(anahtar, ham))
            + '<details style="margin-top:2px; font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">'
            + '<summary style="cursor:pointer;">'
            + U.esc(T('common.techDetailSrv', 'Technical detail (solver statement, untranslated)'))
            + '</summary>' + U.esc(ham) + '</details>';
    }

    /* V301/PANEL-SAYI (28 Eki, S1) — MOTORUN TESLİM ETTİĞİ DÖRT SAYI.
       Yollar, ana sonuç ekranının bastığı sayıların yollarıdır (ölçüldü,
       ``olcum/akis_once_tr.json``): hibrit itki 3000 N / ṁ 1,458 / c* 1423 /
       C_F 1,445; sıvı itki (deniz seviyesi) 25000 N / ṁ 9,915 / c* 1738,3;
       katı tasarım Pc'sindeki itki = tepe itki 1498 N, c* 868,75, C_F(Pc).
       Katı motor tasarım noktası debisini başlık olarak yayımlamıyor: kart
       basılmaz (türetilmez). Sayılar yalnız panelin girdileri motorun
       girdileriyle AYNIYSA yan yana konur — kullanıcı paneli başka bir oda
       basıncıyla koşturduysa motorun sayısı o çözüme ait değildir. */
    const TESLIM_YOLLARI = {
        hybrid: { thrust: ['thrust'], mdot: ['mdot_total'], cstar: ['c_star'],
                  cf: ['cf'] },
        liquid: { thrust: ['thrust'], mdot: ['total_mass_flow'], cstar: ['c_star'],
                  cf: ['isp_identity.thrust_coefficient_sea_level'] },
        solid: { thrust: ['design_summary.performance.peak_thrust_N'], mdot: [],
                 cstar: ['c_star'], cf: ['nozzle_design.performance.thrust_coefficient'] },
    };
    function ilkSayi(o, yollar) {
        for (let i = 0; i < yollar.length; i++) {
            let v = o;
            const parca = yollar[i].split('.');
            for (let j = 0; j < parca.length; j++) {
                v = (v && typeof v === 'object') ? v[parca[j]] : undefined;
            }
            if (typeof v === 'number' && Number.isFinite(v)) return v;
        }
        return undefined;
    }
    // Panel girdisi motor değerinin KENDİSİ mi? Güverte öneriyi alana
    // anlamlı basamağa yuvarlayarak yazar (analysis_dock.js dockSigFig,
    // 6 basamak; ölçüldü: Tc 3279,1066 → 3279,11); eşleşme o kuralın
    // AYNISIYLA denetlenir, gevşek bir tolerans uydurulmaz.
    function ayniSayi(a, b) {
        if (typeof a !== 'number' || typeof b !== 'number'
                || !Number.isFinite(a) || !Number.isFinite(b)) return false;
        if (a === b) return true;
        return (typeof U.sigFig === 'function') && a === U.sigFig(b, U.SIGFIG);
    }
    function teslimBlogu(flow) {
        const r = window.currentResults;
        const tip = motorTipi();
        const yollar = TESLIM_YOLLARI[tip];
        if (!r || !yollar) return '';
        const m = U.motorDict(r);
        const inp = (flow && flow.inputs) || {};
        const pc = ilkSayi(m, ['chamber_pressure']);
        const ciftler = [
            [inp.chamber_pressure_Pa, (pc === undefined) ? undefined : pc * 1e5],
            [inp.chamber_temperature_K, ilkSayi(m, ['chamber_temperature'])],
            [inp.gamma, ilkSayi(m, ['gamma'])],
            [inp.molecular_weight_g_mol, ilkSayi(m, ['molecular_weight', 'thermochemistry.molecular_weight'])],
            [inp.throat_diameter_m, U.readLengthM(r, 'throat_diameter')],
        ];
        const de = U.readLengthM(r, 'exit_diameter');
        if (Number.isFinite(de)) ciftler.push([inp.exit_diameter_m, de]);
        const baslik = U.sectionTitle(T('panel.nzl.secDelivered',
            'Delivered by the motor - the numbers of the main result'));
        const notStil = 'font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5); margin:6px 0;';
        if (!ciftler.every(function (c) { return ayniSayi(c[0], c[1]); })) {
            return baslik + '<p style="' + notStil + '">' + U.esc(T('panel.nzl.delInputsDiffer',
                'The inputs of this run differ from the motor result (chamber pressure, '
                + 'chamber temperature, gamma, molecular weight, throat or exit diameter), '
                + 'so the delivered numbers of the motor are not shown beside it.')) + '</p>';
        }
        const kartlar = [];
        const itki = ilkSayi(m, yollar.thrust);
        if (itki !== undefined) {
            kartlar.push(U.statCard(tip === 'solid'
                ? T('panel.nzl.delThrustPeak', 'THRUST AT THIS Pc (MOTOR, PEAK)')
                : T('panel.nzl.delThrust', 'THRUST (MOTOR)'),
                fmtL(itki, 0), 'N', 'info', yollar.thrust[0]));
        }
        const md = ilkSayi(m, yollar.mdot);
        if (md !== undefined) {
            kartlar.push(U.statCard(T('panel.nzl.delMassFlow', 'MASS FLOW (MOTOR)'),
                fmtL(md, 3), 'kg/s', 'info', yollar.mdot[0]));
        }
        const cs = ilkSayi(m, yollar.cstar);
        if (cs !== undefined) {
            kartlar.push(U.statCard(T('panel.nzl.delCstar', 'C* DELIVERED (MOTOR)'),
                fmtL(cs, tip === 'liquid' ? 1 : 0), 'm/s', 'info', yollar.cstar[0]));
        }
        const cf = ilkSayi(m, yollar.cf);
        if (cf !== undefined) {
            kartlar.push(U.statCard(tip === 'solid'
                ? T('panel.nzl.delCfPc', 'C_F AT THIS Pc (MOTOR)')
                : T('panel.nzl.delCf', 'C_F (MOTOR)'),
                fmtL(cf, 3), '', 'info', yollar.cf[0]));
        }
        if (!kartlar.length) return '';
        let not = T('panel.nzl.delNote',
            'The cards above are the quasi-1D solution of this chamber state: '
            + 'ideal c* of a calorically perfect gas (c* efficiency 1) and the '
            + 'geometric throat (discharge coefficient 1). The motor delivers '
            + 'its c* with its c* efficiency and its mass flow through its '
            + 'throat discharge coefficient; these four numbers are the '
            + 'motor result, unchanged.');
        if (tip === 'solid') {
            not += ' ' + T('panel.nzl.delNoMassFlowSolid',
                'The solid motor publishes no design-point mass flow as a headline number, so none is shown.');
        }
        return baslik + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + kartlar.join('') + '</div><p style="' + notStil + '">' + U.esc(not) + '</p>';
    }

    // ------------------------------------------------------------------
    // Cantera sonlu hızlı kinetik yetenek sondası: Cantera + reaksiyonlu mekanizma varsa
    // kinetik model seçicisine 'high_fidelity' seçeneği eklenir.
    // ------------------------------------------------------------------
    let hfProbeDone = false;

    function appendHighFidelityOption() {
        const sel = document.getElementById('ad_f_' + PANEL_ID + '_kinetic_fidelity');
        if (!sel) return false;
        if (!sel.querySelector('option[value="high_fidelity"]')) {
            const opt = document.createElement('option');
            opt.value = 'high_fidelity';
            opt.textContent = T('nzl.kinHigh', 'Cantera finite-rate kinetics');
            sel.appendChild(opt);
        }
        return true;
    }

    function probeHighFidelity() {
        if (hfProbeDone) return;
        hfProbeDone = true;
        fetch(KINETIC_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ probe: true, fidelity: 'high_fidelity' }),
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
              if (!j || j.fidelity_used !== 'high_fidelity') return;
              // Güverte DOMContentLoaded'ta kurulur; select henüz yoksa
              // kısa aralıklarla dene (montaj yarışına dayanıklılık).
              if (appendHighFidelityOption()) return;
              let tries = 0;
              const timer = setInterval(function () {
                  tries += 1;
                  if (appendHighFidelityOption() || tries > 40) clearInterval(timer);
              }, 250);
          })
          .catch(function () { /* sonda başarısız → seçenek eklenmez */ });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', probeHighFidelity);
    } else {
        probeHighFidelity();
    }

    // ------------------------------------------------------------------
    // Çizim yardımcıları
    // ------------------------------------------------------------------
    function plotBlock(root, heading) {
        const wrap = document.createElement('div');
        wrap.style.marginTop = '14px';
        wrap.innerHTML = U.sectionTitle(heading);
        const plot = document.createElement('div');
        wrap.appendChild(plot);
        root.appendChild(wrap);
        return plot;
    }

    function separationShape(sep) {
        if (!sep || !Number.isFinite(sep.station_x_mm)) return [];
        return [{
            type: 'line', xref: 'x', yref: 'paper',
            x0: sep.station_x_mm, x1: sep.station_x_mm, y0: 0, y1: 1,
            line: { color: '#ff5d73', width: 1.5, dash: 'dash' },
        }];
    }

    function drawStationPlots(flow, root) {
        const st = flow.stations;
        if (!st || !Array.isArray(st.x_mm) || !st.x_mm.length) {
            const note = document.createElement('p');
            note.style.cssText = 'font-family:var(--hd-mono); font-size:0.78rem;'
                + ' color:var(--hd-ink-dim, #7d97a5); margin:10px 0;';
            note.textContent = T('panel.nzl.noStations',
                'Fast Screening level: station arrays P(x)/M(x) '
                + 'require the Engineering fidelity level.');
            root.appendChild(note);
            return;
        }
        if (typeof Plotly === 'undefined') {
            const note = document.createElement('p');
            note.textContent = T('panel.nzl.plotlyMissing',
                'Plotly is not loaded — station charts skipped.');
            root.appendChild(note);
            return;
        }
        const sep = flow.regime && flow.regime.separation;
        const shapes = separationShape(sep);

        // P(x): çekirdek + cidar basıncı (ayrılmada ortam platosu görünür)
        const pBar = st.pressure_Pa.map(function (p) { return p / 1e5; });
        const pWallBar = (st.wall_pressure_Pa || st.pressure_Pa)
            .map(function (p) { return p / 1e5; });
        Plotly.newPlot(plotBlock(root, T('panel.nzl.chartP',
            'Static Pressure Along the Nozzle — P(x)')), [
            { x: st.x_mm, y: pBar, mode: 'lines',
              name: T('panel.nzl.seriesCoreP', 'Core P(x) [bar]'),
              line: { width: 2 } },
            { x: st.x_mm, y: pWallBar, mode: 'lines',
              name: T('panel.nzl.seriesWallP', 'Wall P(x) [bar]'),
              line: { width: 1.5, dash: 'dot' } },
        ], {
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.pressureBar', 'Pressure (bar)') },
            shapes: shapes,
            margin: { t: 24, r: 16 },
            height: 320,
        }, { responsive: true, displaylogo: false });

        // M(x)
        Plotly.newPlot(plotBlock(root, T('panel.nzl.chartM',
            'Mach Number Along the Nozzle — M(x)')), [
            { x: st.x_mm, y: st.mach, mode: 'lines', name: 'Mach', line: { width: 2 } },
        ], {
            xaxis: { title: T('common.axis.axialX', 'Axial position x (mm)') },
            yaxis: { title: T('common.axis.machNumber', 'Mach number') },
            shapes: shapes.concat([{
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: 1, y1: 1,
                line: { color: 'rgba(125,151,165,0.6)', width: 1, dash: 'dot' },
            }]),
            margin: { t: 24, r: 16 },
            height: 320,
        }, { responsive: true, displaylogo: false });
    }

    // ------------------------------------------------------------------
    // Kinetik kayıp bandı kartı
    // ------------------------------------------------------------------
    function kineticCard(kin, note) {
        if (!kin) {
            if (!note) return '';
            // V301/DİL-2 (ÖRNEK-PANEL devri): uç notu çeviri kanalından
            // (serverText; tanınmazsa AYNEN) ve kaçışlanarak basılır.
            const srvNot = (window.I18N && typeof window.I18N.serverText === 'function')
                ? window.I18N.serverText(String(note)) : String(note);
            return `<p style="font-family:var(--hd-mono); font-size:0.75rem;
                color:var(--hd-ink-dim, #7d97a5); margin:8px 0;">${U.esc(srvNot)}</p>`;
        }
        const band = kin.loss_band_pct || [null, null];
        const lo = fmtL(band[0], 2), hi = fmtL(band[1], 2);
        const fidelityBadge = U.badge(
            T('panel.nzl.kineticsBadge', 'KINETICS') + ': '
            + String(kin.fidelity_used || '?').toUpperCase(),
            kin.fidelity_used === 'high_fidelity' ? 'ok' : 'info',
            kin.model_note || '');
        // ÖH D15 / P4B4-05 — GERİ ÇEKİLEN Isp ADIYLA SÖYLENİR.
        // Çözücü, verilen lüle profilinin çıkışı ile Isp çiftinin kurulduğu
        // referans basınç %2'den fazla ayrıldığında Isp üçlüsünü ve kinetik
        // kaybı None'a çekip gerekçesini `isp_withheld_because` ile
        // yayımlıyor. Kartlar "—" çizecek; sebep basılmazsa kullanıcı bunu
        // "veri gelmedi" sanar (aynı kusurun rejim bloğundaki ikizi
        // P4B2-02'de düzeltilmişti).
        const ispWithheld = kin.isp_withheld_because;
        const ispWithheldNote = ispWithheld
            ? `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                U.esc ? U.esc(String(ispWithheld)) : ispWithheld}</p>`
            : '';
        return U.sectionTitle(T('panel.nzl.secKinetic',
                'Kinetic Efficiency — Frozen/Shifting Bracket'))
            + `<div style="margin:4px 0 8px;">${fidelityBadge}</div>`
            + ispWithheldNote
            + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard(T('panel.nzl.cardKineticLoss', 'KINETIC LOSS'),
                fmtL(kin.kinetic_loss_pct, 2), '%',
                kin.kinetic_loss_pct > 3 ? 'warn' : 'ok',
                T('panel.nzl.cardKineticLossTip', 'Isp loss vs shifting equilibrium'))
            + U.statCard(T('panel.nzl.cardLossBand', 'LOSS BAND'), lo + ' – ' + hi, '%', 'dim',
                T('panel.nzl.cardLossBandTip', 'Honest uncertainty band on the kinetic loss'))
            + U.statCard(T('panel.nzl.cardIspFrozen', 'ISP FROZEN'), fmtL(kin.isp_frozen, 1), 's', 'dim', '')
            + U.statCard(T('panel.nzl.cardIspPredicted', 'ISP PREDICTED'), fmtL(kin.isp_predicted, 1), 's', 'info', '')
            + U.statCard(T('panel.nzl.cardIspShifting', 'ISP SHIFTING'), fmtL(kin.isp_shifting, 1), 's', 'dim', '')
            + '</div>'
            /* ÖH D26 / OH-B3-02 — KİNETİK TANI BLOĞU (8 alan) ekrana
               iner. ÖLÇÜLDÜ (a2/once.json: flow_kinetic_diagnostics = 0):
               `kinetic_efficiency.diagnostics` bloğu panelde ne kendi
               adıyla ne bir çocuğuyla geçiyordu — kinetik verim kartları
               çiziliyor, o kartları üreten tanı sayıları ekran dışında
               kalıyordu. Ad = değer, AYNEN (panel yeniden yazmaz). */
            + kineticDiagnosticsHtml(kin.diagnostics);
    }

    function kineticDiagnosticsHtml(tani) {
        if (!tani || typeof tani !== 'object') return '';
        const anahtar = Object.keys(tani).sort();
        if (!anahtar.length) return '';
        return U.kvTable(anahtar.map(function (k) {
            const v = tani[k];
            return ['diagnostics.' + k,
                    (v === null || v === undefined)
                        ? T('panel.nzl.notSupplied', 'not supplied')
                        : (typeof v === 'number' ? fmtL(v, 4)
                            : (typeof v === 'object' ? JSON.stringify(v)
                                : U.esc(String(v))))];
        }));
    }

    // ------------------------------------------------------------------
    // ÖH D15 — DÜRÜSTLÜK BLOĞU (P4B2-05, P4B2-06, P4B2-08)
    // ------------------------------------------------------------------
    // Çözücü bu koşumda ÜÇ yeni dürüstlük alanı yayımlıyor ve hiçbiri
    // ekranda yoktu:
    //   * performance.wall_integral_cross_check — cidar basıncı integrali
    //     ⟷ çıkış düzlemi itkisi çaprazının HÜKMÜ. Şok rejiminde ölçülen
    //     bağıl kalıntı %8,75-231; künye bu integrali "cross-check" diye
    //     satarken tutmadığında hiçbir işaret yoktu.
    //   * performance.reference_withheld_because / _fields — fizik dışı
    //     (negatif) "ideal"/"tam akışlı" referans sayıları geri çekildi;
    //     kartlar "—" çizecek, sebebi burada YAZILI olmalı.
    //   * inputs.wall_temperature_source + stations.T_wall_used_K — akının
    //     FİİLEN hangi cidar sıcaklığında kurulduğu (eskiden yanıt
    //     kullanıcının ham değerini yankılıyor, hesap kırpılmış değerle
    //     yapılıyordu).
    //   * performance.c_star_source — yayımlanan c*'ın kaynağı.
    /* ÖH D27 a4 · P11B5-12 — SÜRTÜNME KAYBI ÖLÇÜLDÜ MÜ, SABİT Mİ?

       ÖLÇÜLDÜ (a4/once.json, `p11b5_12_cf_kart_kaynak_okuyor` = 0):
       "CF EFFECTIVE" kartı her iki durumda da AYNI `dim` kartla ve AYNI
       ipucuyla ("After divergence + friction losses (approximate)")
       çiziliyordu. Oysa uç `losses.friction_loss_fraction_source` ile
       sayının SINIFINI söylüyor: sınır tabaka integralinden ÖLÇÜLMÜŞ mü
       ('integral_bl_measured'), kullanıcının verdiği mi, yoksa eski SABİT
       yedek mi. Ölçülmüş bir kayıpla varsayılan bir sabit ekranda ayırt
       edilemiyordu.

       Sınıf UÇTAN okunur, panelde ÜRETİLMEZ; alan gelmezse künye
       "not declared" der ve kart 'dim' kalır (sayı da hüküm de
       uydurulmaz). */
    function frictionOriginText(losses) {
        const src = losses && losses.friction_loss_fraction_source;
        if (!src) {
            return 'friction_loss_fraction_source: not declared by the '
                 + 'endpoint — whether this friction loss was MEASURED or '
                 + 'assumed is unknown.';
        }
        return 'friction_loss_fraction_source = ' + String(src)
             + (losses.friction_loss_fraction_basis
                ? ' · ' + String(losses.friction_loss_fraction_basis) : '');
    }

    // Ölçülmüş kayıp = 'ok'; ölçülmemiş/sabit = 'warn'; beyansız = 'dim'.
    function frictionKind(losses) {
        const src = losses && losses.friction_loss_fraction_source;
        if (!src) return 'dim';
        return String(src).indexOf('measured') !== -1 ? 'ok' : 'warn';
    }

    /* ÖH D27 a4 · P11B5-13 — HANGİ İTKİ?

       ÖLÇÜLDÜ (a4/once.json, `p11b5_13_thrust_kart_tanimi` = 0): panel
       çıplak bir "THRUST" kartı basıyordu, ipucu boş dizeydi. Aynı koşumda
       uç ÜÇ ayrı itki tanımı yayımlayabiliyor (`performance.thrust_N`
       — çözülen akışın momentum + basınç itkisi —, `losses`
       `thrust_effective_N` ve ayrılma yokmuş gibi kurulan
       `thrust_full_flow_N`); ayrık rejimde bunlar kat kat ayrışır.
       Kartın hangisini gösterdiği ekranda yazmıyordu.

       Kart artık kendi tanımını ve — uç yayımladıysa — kardeş tanımlarla
       ORANINI taşır. Oran ölçüdür, eşik değil: sayı yoksa satır yok. */
    function thrustDefinitionText(perf, losses) {
        const f = perf && perf.thrust_N;
        let out = 'performance.thrust_N — momentum + pressure thrust of the '
                + 'solved (possibly separated) flow.';
        const kiyas = [
            ['losses.thrust_effective_N', losses && losses.thrust_effective_N],
            ['performance.thrust_full_flow_N', perf && perf.thrust_full_flow_N],
        ];
        kiyas.forEach(function (pair) {
            const v = pair[1];
            if (typeof v === 'number' && isFinite(v)
                    && typeof f === 'number' && isFinite(f) && f !== 0) {
                out += ' · ' + pair[0] + ' = ' + U.fmt(v, 0) + ' N ('
                     + U.fmt(v / f, 3) + '× this card).';
            }
        });
        return out;
    }

    /* ÖH D27 a4 · P11B5-13 (ikinci ayak) — CF > CF_IDEAL ÇELİŞKİSİ.

       İdeal itki katsayısı kayıpsız üst sınırdır; yayımlanan CF onu
       aşıyorsa ikisi AYNI akışın sayıları değildir (ör. biri ayrık
       rejimin çözümü, öteki tam akış varsayımı). Panel bunu rozetsiz
       bırakıyordu (`p11b5_13_cf_celiski_rozeti` = 0). Rozet bir eşik
       testi değil, YAYIMLANAN İKİ SAYININ KIYASIDIR. */
    function cfContradictionBadge(perf) {
        const cf = perf && perf.CF;
        const ci = perf && perf.CF_ideal;
        if (typeof cf !== 'number' || !isFinite(cf)) return '';
        if (typeof ci !== 'number' || !isFinite(ci)) return '';
        if (!(cf > ci)) return '';
        return U.badge(T('panel.nzl.cfOverIdeal', 'CF > CF_IDEAL'), 'warn',
            'The published thrust coefficient exceeds the ideal (loss-free) '
            + 'ceiling: CF = ' + U.fmt(cf, 4) + ' > CF_ideal = '
            + U.fmt(ci, 4) + '. The two numbers therefore do not describe '
            + 'the same flow; read the regime and withheld-reference notes '
            + 'before comparing them.');
    }

    /* ÖH D31 · OH-D26-20 / OH-D27-10 — VARSAYILAN KÜNYESİ EKRANA İNER.

       ÖLÇÜLDÜ (``a2/once.json`` M5_flow): uç, gönderilmeyen HER alan için
       ``defaults_applied`` künyesi yayımlıyor (``_flow_varsayilan_kunyesi``,
       app.py:27202 -> ``response['defaults_applied']``, app.py:27854) ve
       şema ``{field, value, unit, reason, message}``. Panelde bu adın
       geçtiği yer SIFIRDI: ``honestyBlock`` yalnız ``flow`` altındaki
       rozetleri basıyordu, künye ise yanıtın KÖKÜNDE duruyor.

       Bu, formun ön-dolu varsayılanlarını sökmenin ÖN KOŞULUDUR (doktrin
       §3 (b)): alan gönderilmeyince uç kendi kanonik varsayılanını uygular
       ve ADIYLA beyan eder — beyan görünmezse söküm, sayıyı görünür
       varsayılandan GÖRÜNMEZ varsayılana çevirmiş olurdu, yani kusuru
       derinleştirirdi. Metin SUNUCUDAN gelir; panel ne sayı ne gerekçe
       üretir. */
    /* V301/PANEL-SAYI (KILAVUZ P4) — künye satırı DÜZ METİN ve ekran dilinde.
       ÖLÇÜLDÜ (olcum/akis_once_tr.json): ``U.listBlock`` maddeleri
       kaçışladığı için ekranda "<strong>separation_factor</strong>"
       işaretlemesi harfiyen görünüyordu ve TR ekranda ucun İngilizce
       cümlesi basılıyordu. Satır artık alanın ekrandaki etiketi = değer
       (dile göre ondalık ayırıcı) + birim — gerekçe sözlükten; sözlükte
       olmayan alanda ucun kendi cümlesi. */
    const AKIS_VARSAYILAN_GEREKCE = {
        chamber_pressure: 'panel.nzl.defaultBasis.chamber_pressure',
        chamber_temperature: 'panel.nzl.defaultBasis.chamber_temperature',
        gamma: 'panel.nzl.defaultBasis.gamma',
        molecular_weight: 'panel.nzl.defaultBasis.molecular_weight',
        throat_diameter: 'panel.nzl.defaultBasis.throat_diameter',
        ambient_pressure: 'panel.nzl.defaultBasis.ambient_pressure',
        n_stations: 'panel.nzl.defaultBasis.n_stations',
        separation_factor: 'panel.nzl.defaultBasis.separation_factor',
        wall_temperature: 'panel.nzl.defaultBasis.wall_temperature',
    };
    const AKIS_EK_ETIKET = {
        separation_factor: ['panel.nzl.fSeparationFactor', 'Separation factor k (Summerfield)'],
        wall_temperature: ['panel.nzl.fWallTemperature', 'Wall temperature (Bartz)'],
    };
    function defaultsBlock(kunyeler) {
        if (!Array.isArray(kunyeler) || !kunyeler.length) return '';
        const satirlar = kunyeler.map(function (k) {
            const ad = String((k && k.field) || '');
            const f = TUM_ALANLAR.filter(function (x) { return x[0] === ad; })[0];
            const ek = AKIS_EK_ETIKET[ad];
            const etiket = f ? T(f[4], f[1]) : (ek ? T(ek[0], ek[1]) : ad);
            const v = k ? k.value : null;
            const birim = (k && k.unit && k.unit !== 'count') ? (' ' + String(k.unit)) : '';
            const deger = (typeof v === 'number') ? fmtL(v) + birim
                : ((v === null || v === undefined) ? '' : String(v) + birim);
            const anahtar = AKIS_VARSAYILAN_GEREKCE[ad];
            const neden = anahtar ? T(anahtar, String((k && k.message) || ''))
                                  : String((k && k.message) || '');
            return etiket + ' = ' + deger + (neden ? ' — ' + neden : '');
        });
        return U.listBlock(
            // ÖH D31 · arayuz-panel a3: a2'nin eklediği
            // `panel.nzl.defaultsApplied` anahtarı SÖZLÜKTE YOKTU
            // (test_i18n_common kırmızısı) ve i18n dosyaları bu kulvarın
            // sahası değildir. Aynı cümle sözlükte ZATEN var
            // (`panel.structural.defaultsApplied`, EN+TR) — TEK KAYNAK
            // gereği ikinci bir anahtar yazılmaz, mevcut olan kullanılır.
            T('panel.structural.defaultsApplied',
              'Assumed on your behalf - these were NOT supplied'),
            satirlar, 'warn');
    }

    function honestyBlock(flow) {
        const perf = flow.performance || {};
        const st = flow.stations || {};
        const inp = flow.inputs || {};
        const satir = [];
        const celiski = cfContradictionBadge(perf);
        if (celiski) satir.push(celiski);
        const cc = perf.wall_integral_cross_check;
        if (cc && cc.residual_rel !== null && cc.residual_rel !== undefined) {
            const ok = cc.agrees === true;
            satir.push(U.badge(
                (ok ? T('panel.nzl.xcheckOk', 'THRUST CROSS-CHECK OK')
                    : T('panel.nzl.xcheckFail', 'THRUST NOT CROSS-CHECKED'))
                + ' · ' + fmtL(cc.residual_rel * 100, 2) + ' % / '
                + fmtL(cc.tolerance_rel * 100, 0) + ' %',
                ok ? 'ok' : 'warn', cc.basis || ''));
        }
        if (perf.c_star_source) {
            satir.push(U.badge('C* ' + U.esc(String(perf.c_star_source)),
                'dim', T('panel.nzl.cstarSrcTip',
                    'Where the published characteristic velocity came from')));
        }
        const twSrc = inp.wall_temperature_source;
        const twUsed = Array.isArray(st.T_wall_used_K) && st.T_wall_used_K.length
            ? st.T_wall_used_K[0] : null;
        if (twSrc) {
            satir.push(U.badge(
                T('panel.nzl.wallTUsed', 'WALL T USED') + ' · '
                + (twUsed === null ? '—' : fmtL(twUsed, 0) + ' K') + ' · '
                + U.esc(String(twSrc)),
                'dim', T('panel.nzl.wallTUsedTip',
                    'Wall temperature the Bartz flux was actually built on')));
        }
        /* ÖH D26 / OH-B3-02 — SÜRTÜNME KAYBININ KÜNYESİ EKRANA İNER.
           ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``): /api/flow-analysis
           `losses` bloğu DÖRT künye alanı yayımlıyor
           (`friction_loss_fraction_basis`, `..._source`, `..._bl_note`,
           `friction_comparison_basis`) ve flow_panel.js dördünü de SIFIR
           kez basıyordu. Kullanıcı "CF EFFECTIVE" kartındaki sayıyı
           görüyor ama o sayıyı üreten sürtünme kaybının hangi modelden
           geldiğini hiçbir yerde okuyamıyordu.
           tests/test_wave4a_contract.py bunu 'flow/losses' altında
           xfail(strict) borç imiyle taşıyordu.
           Metin SUNUCUDAN gelir, panel yeniden yazmaz. */
        const kayip = flow.losses || {};
        const kunyeler = [
            ['friction_loss_fraction_source', kayip.friction_loss_fraction_source],
            ['friction_loss_fraction_basis', kayip.friction_loss_fraction_basis],
            ['friction_loss_fraction_bl_note', kayip.friction_loss_fraction_bl_note],
            ['friction_comparison_basis', kayip.friction_comparison_basis],
        ].filter(function (p) { return p[1] !== null && p[1] !== undefined && p[1] !== ''; });

        /* OH-B3-02 (aynı kalem) — REJİM EŞİKLERİ ve KİNETİK TANI BLOĞU.
           `flow.regime.thresholds_Pa` (5 alan) ve
           `kinetic_efficiency.diagnostics` (8 alan) da panelde HİÇ
           geçmiyordu: rejim hükmünün dayandığı basınç eşikleri ve
           kinetik verimin tanı sayıları ekran dışındaydı. */
        const rejim = flow.regime || {};
        const esikler = rejim.thresholds_Pa;

        let blok = satir.length
            ? '<div style="margin:6px 0; display:flex; gap:8px; flex-wrap:wrap;">'
              + satir.join(' ') + '</div>'
            : '';
        if (kunyeler.length) {
            /* V301/PANEL-SAYI (KILAVUZ P4): sürtünme dayanağı çözücünün
               uzun İngilizce beyanıdır (makine alanları). Ekranda kapalı
               "Teknik ayrıntı (makine alanları)" altında AYNEN durur; görünen
               satır kartın kaynak sınıfıdır (ölçüldü / sabit / kullanıcı). */
            const kaynak = kayip.friction_loss_fraction_source;
            const sinif = !kaynak ? ''
                : (String(kaynak).indexOf('measured') !== -1
                    ? T('panel.nzl.frictionMeasured',
                        'Friction loss: measured (boundary-layer integral of this solution)')
                    : (String(kaynak) === 'user'
                        ? T('panel.nzl.frictionUser', 'Friction loss: your input')
                        : T('panel.nzl.frictionConstant',
                            'Friction loss: fixed bookkeeping constant (no measurement could be published)')));
            if (sinif) {
                blok += '<p style="font-size:0.78rem; color:var(--hd-ink, #cfe8f2); margin:6px 0;">'
                    + U.esc(sinif) + '</p>';
            }
            blok += '<details style="margin:4px 0 8px;"><summary style="cursor:pointer;'
                + ' font-size:0.75rem; color:var(--hd-ink-dim, #7d97a5);">'
                + U.esc(T('common.techDetail', 'Technical detail (machine fields)'))
                + '</summary>'
                + U.kvTable(kunyeler.map(function (p) {
                    return [p[0], U.esc(String(p[1]))];
                })) + '</details>';
        }
        if (esikler && typeof esikler === 'object'
                && Object.keys(esikler).length) {
            blok += U.kvTable(Object.keys(esikler).sort().map(function (k) {
                const v = esikler[k];
                return ['thresholds_Pa.' + k,
                        (v === null || v === undefined)
                            ? T('panel.nzl.notSupplied', 'not supplied')
                            : fmtL(v, 0) + ' Pa'];
            }));
        }
        if (perf.reference_withheld_because) {
            blok += `<p style="color:var(--hd-amber, #ffbe46); font-size:0.78rem; margin:4px 0;">${
                U.esc(String((perf.reference_withheld_fields || []).join(', ')))
                + ' — ' + U.esc(String(perf.reference_withheld_because))}</p>`;
        }
        return blok;
    }

    // ------------------------------------------------------------------
    // Ana render
    // ------------------------------------------------------------------
    function render(data, root) {
        const flow = (data && data.flow) || {};
        const regime = flow.regime || {};
        const perf = flow.performance || {};
        const losses = flow.losses || {};
        const info = regimeInfo(regime.type);

        const head = document.createElement('div');
        // ÖH D25 / OH-D24-08 — SUNUCU GEREKÇESİ CANLI DALDA, ÖLÜ DAL YOK.
        //
        // ÖLÇÜLDÜ (docs/scofield/raw/OH/D25/arayuz/a2/once.json): D19
        // (P15B4-09) sonrası `nozzle_flow_1d._classify_regime` Summerfield
        // ölçütünü ŞOK dalından ÖNCE değerlendiriyor, yani ölçütün
        // sağlandığı HER vaka REGIME_SEPARATED'a düşüyor ve
        // `_solve_separation` her zaman bir sözlük döndürdüğü için
        // `regime.separation` DOLU geliyor. Buradaki eski
        // `else if (separation_expected && separation_criterion_met)` dalı
        // bu yüzden ULAŞILAMAZDI — ve sunucunun kendi gerekçe cümlesi
        // (`separation_expected_because`, ölçütün sayılarını taşır) YALNIZ
        // o ölü dalda basıldığı için ekrana HİÇ çıkmıyordu.
        //
        // Gerekçe artık canlı dalda basılır; metni SUNUCU yazar (yeni i18n
        // anahtarı uydurulmaz). Ayrılma düzlemi ayrı adla da taşınıyorsa
        // (`separation_station_summerfield`) ölçüm ondan okunur.
        let sepNote = '';
        const sepEsc = function (t) {
            return U.esc ? U.esc(String(t)) : String(t);
        };
        const sepNeden = regime.separation_expected_because;
        if (regime.separation) {
            const sepIst = regime.separation_station_summerfield
                || regime.separation;
            sepNote = (sepNeden
                ? `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                    sepEsc(sepNeden)}</p>`
                : '')
                + `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                U.tf('panel.nzl.separationNote',
                     { x: fmtL(sepIst.station_x_mm, 1),
                       ar: fmtL(sepIst.area_ratio, 2) },
                     'Separation at x = {x} mm (area ratio {ar}) — Summerfield criterion.')}</p>`;
        } else if (regime.separation_criterion_met
                   || regime.separation_expected) {
            // SÖZLEŞME KAPISI (fail-closed). Yukarıdaki değişmez bozulursa
            // — çözücü "ölçüt sağlandı" deyip ayrılma düzlemini VERMEZSE —
            // panel sessiz kalmaz ve uydurma bir istasyon çizmez: çelişkiyi
            // ADIYLA söyler. Bu dal ürünün bugünkü hâlinde ERİŞİLMEZDİR;
            // erişilir hâle gelmesi sunucu sözleşmesinin kırıldığı anlamına
            // gelir (bekçi: test_d25_arayuz_a2.py).
            sepNote = `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                U.tf('panel.nzl.separationContract', {},
                     'SEPARATION CRITERION MET BUT NO SEPARATION PLANE WAS '
                     + 'PUBLISHED — the solver reports the Summerfield '
                     + 'criterion as met yet returned no separation station, '
                     + 'so no station is drawn. This is a solver contract '
                     + 'violation, not a converged result.')}</p>`
                + (sepNeden
                    ? `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                        sepEsc(sepNeden)}</p>`
                    : '');
        }
        // ÖH D15 / P4B2-02 — geri çekilmiş performans ADIYLA söylenir.
        // Boğulmamış lülede çözücü artık itki/CF/debi yayımlamıyor (eskiden
        // −727 N "İTKİ" kartı basılıyordu). Kartlar "—" çizecek; sebebi
        // yazmazsak kullanıcı bunu "veri gelmedi" sanır.
        // ÖH D25 / P11B2-10 — rejim hükmünün KAYNAK ÇİPİ ortak
        // sınıflandırıcıdan. Panel ucun `separation_criterion` /
        // `separation_expected_because` beyanını okuyor; hükmün ne olduğunu
        // (hesaplandı / varsayıldı / modellenmedi) artık pano tablosu
        // söyler, panel kendi damgasını uydurmaz. Sınıflandırıcı D24'e
        // kadar hiçbir ürün kodundan çağrılmıyordu (ölü katman).
        let sepChip = '';
        if (U.source && U.source.of && U.source.chip) {
            const sepInfo = U.source.of(
                { basis: regime.separation_expected_because
                         || regime.separation_criterion || null,
                  status: regime.separation ? 'modelled'
                          : (regime.separation_criterion_met
                             ? 'not_computed' : null) },
                null,
                { value: regime.separation
                    ? (regime.separation.station_x_mm != null
                       ? regime.separation.station_x_mm : null)
                    : null });
            if (sepInfo.declared) sepChip = U.source.chip(sepInfo);
        }
        if (sepNote && sepChip) {
            sepNote += `<p style="margin:2px 0 6px;">${sepChip}</p>`;
        }

        let withheldNote = '';
        const withheld = flow.performance_withheld_because
            || perf.withheld_because;
        if (withheld) {
            withheldNote = `<p style="color:var(--hd-red, #ff5d73); font-size:0.8rem; margin:6px 0;">${
                U.esc ? U.esc(withheld) : withheld}</p>`;
        }

        head.innerHTML = U.sectionTitle(T('panel.nzl.secRegime',
                'Flow Regime — Quasi-1D Classification'))
            + `<div style="margin:4px 0 6px;">${U.badge(info.label, info.kind,
                regime.separation_criterion || '')}
               <span style="font-family:var(--hd-mono); font-size:0.72rem;
                     color:var(--hd-ink-dim, #7d97a5); margin-left:10px;">
                 ${data.fidelity === 'fast' ? T('nzl.fidelityFast', 'FAST SCREENING')
                                             : T('nzl.fidelityEng', 'ENGINEERING')} ·
                 ${U.esc(flow.model || '')}</span></div>`
            + `<div style="font-size:0.82rem; color:var(--hd-ink, #cfe8f2); margin:6px 0;">
                ${rejimCumlesiHtml(regime)}</div>`
            + sepNote
            + withheldNote
            + U.sectionTitle(T('panel.nzl.secThrust', 'Thrust & Thrust Coefficient'))
            /* V301/PANEL-SAYI (28 Eki, S1, yayın kapısı 6) — İDEAL ADIYLA,
               TESLİM YANINDA. ÖLÇÜLDÜ (``olcum/akis_once_tr.json``): bu
               kartlar çözücünün İDEAL sayılarını ("İTKİ", "KÜTLE DEBİSİ",
               "C*" adlarıyla) basıyordu — hibrit örnekte 3150 N / 1,323 kg/s
               / 1602 m/s, ana sonuç 3000 N / 1,458 kg/s / 1423 m/s; sıvıda
               26603 N / 9,927 / 1772, ana sonuç 25000 N / 9,915 / 1738,3.
               Fark fizik değil, TANIM: quasi-1B çözüm oda hâlinin ideal
               c*'ı (kalorik mükemmel gaz, η_c* = 1) ve geometrik boğazla
               (C_D = 1) kurulur; motorun teslim ettiği c* η_c*'ı, debisi
               boğaz akış katsayısını taşır. Çözümün sayıları artık İDEAL
               adıyla durur; motorun teslim ettiği dört sayı (itki, ṁ, c*,
               C_F) yanında, motor sonucundan AYNEN (tek kaynak). */
            + '<div style="display:flex; gap:10px; flex-wrap:wrap;">'
            + U.statCard(T('panel.nzl.cf1d', 'CF (1D, LOSS-FREE)'), fmtL(perf.CF, 3), '',
                'info', T('panel.nzl.cfTip', 'Thrust coefficient F/(Pc·At)'))
            + U.statCard(T('panel.nzl.cfIdeal', 'CF IDEAL'), fmtL(perf.CF_ideal, 3), '',
                'dim', 'Sutton & Biblarz 9th ed. Eq. 3-30')
            + U.statCard(T('panel.nzl.cfEffective', 'CF EFFECTIVE'), fmtL(losses.CF_effective, 3), '',
                frictionKind(losses), T('panel.nzl.cfEffectiveTip',
                         'After divergence + friction losses (approximate)')
                + ' ' + frictionOriginText(losses))
            + U.statCard(T('panel.nzl.thrustIdeal', 'IDEAL THRUST (1D, LOSS-FREE)'),
                fmtL(perf.thrust_N, 0), 'N', 'info',
                thrustDefinitionText(perf, losses))
            // ÖH D22 / P4B2-12 — lambda'yı ÜRETEN açı da bu künyeye iner.
            // Bell konturunda `divergence_half_angle_deg` (çıkış cidar
            // açısı) lambda'yı üretmiyor; o açıdan lambda'yı yeniden kuran
            // okuyucu momentum itkisinde %2,18 sapıyordu. Yeni i18n
            // ANAHTARI AÇILMADI (anahtar dosyaları arayuz kulvarında):
            // sayı ve künyesi mevcut kartın açıklamasına ekleniyor.
            + U.statCard(T('panel.nzl.thrust1dLosses', '1D THRUST, DIVERGENCE + FRICTION'),
                fmtL(losses.thrust_effective_N, 0), 'N', 'dim',
                (losses.note || '')
                + ' Divergence factor evaluated at '
                + U.fmt(losses.divergence_factor_angle_deg, 3)
                + ' deg ('
                + (losses.divergence_factor_angle_basis || '')
                + ').')
            + U.statCard(T('panel.nzl.massFlowIdeal', 'IDEAL MASS FLOW (η_c* = 1, C_D = 1)'),
                fmtL(perf.mass_flow_kg_s, 3), 'kg/s', 'dim', '')
            + U.statCard(T('panel.nzl.cstarIdeal', 'IDEAL C* (CALORICALLY PERFECT GAS)'),
                fmtL(perf.c_star_m_s, 0), 'm/s', 'dim',
                T('panel.nzl.cstarTip', 'Analytic characteristic velocity (Sutton Eq. 3-32)'))
            + U.statCard(T('panel.nzl.exitMach', 'EXIT MACH'), fmtL(perf.exit && perf.exit.mach, 2), '',
                'dim', '')
            + '</div>'
            + teslimBlogu(flow)
            + honestyBlock(flow)
            + defaultsBlock(data.defaults_applied)
            + (katiMi()
                // V301/K-C1 (KT-22): katı motorda hibrit kinetik kimyası
                // (HTPB/N₂O, O/F 6) uca GİTMEZ; kart bunu adıyla söyler.
                ? kineticCard(null, T('panel.nzl.kineticSolidNone',
                    'Kinetic efficiency is not evaluated for a solid motor: '
                    + 'the kinetics model needs an oxidizer/fuel pair and an '
                    + 'O/F ratio, and HRMA has no finite-rate kinetics model '
                    + 'for a solid propellant. The flow solution above uses '
                    + 'the solid design\'s own gas properties.'))
                : siviMi()
                // V301/ÖRNEK-PANEL: sıvı motorda da kinetik üçlü gönderilmez
                // (kinetik zincir yalnız hibrit yakıtlarını tanır).
                ? kineticCard(null, T('panel.nzl.kineticLiquidNone',
                    'Kinetic efficiency is not evaluated for a liquid motor: '
                    + 'the kinetics chain is the hybrid combustion model and '
                    + 'knows only hybrid fuels (HTPB, paraffin, PE, PMMA, ABS, '
                    + 'PLA, aluminium); it has no liquid-fuel chemistry such as '
                    + 'RP-1, LH2 or methane, so no fuel, oxidizer or O/F is sent. '
                    + 'The flow solution above uses this motor\'s own gas '
                    + 'properties.'))
                : kineticCard(data.kinetic_efficiency, data.kinetic_note));
        root.appendChild(head);

        drawStationPlots(flow, root);

        // Varsayımlar — dürüst model sınırları (İngilizce, kullanıcıya görünür)
        if (Array.isArray(flow.assumptions) && flow.assumptions.length) {
            const div = document.createElement('div');
            // V301/PANEL-SAYI (KILAVUZ P4): çözücünün varsayım cümleleri
            // sözlükte yoksa TR ekranda görünür liste İngilizce kalıyordu;
            // TR'de sayılı özet + kapalı "Teknik ayrıntı" (cümleler AYNEN).
            const srv = (window.I18N && typeof window.I18N.serverText === 'function')
                ? window.I18N.serverText : function (x) { return x; };
            const cevrilmedi = dilTr() && flow.assumptions.every(function (x) {
                return srv(String(x)) === String(x);
            });
            div.innerHTML = cevrilmedi
                ? '<details style="margin:10px 0;"><summary style="cursor:pointer;'
                  + ' font-size:0.78rem; color:var(--hd-ink-dim, #7d97a5);">'
                  + U.esc(U.tf('panel.nzl.assumptionsUntranslated',
                      { n: flow.assumptions.length },
                      'Model assumptions & limits - {n} solver statements, untranslated'))
                  + '</summary>' + U.listBlock(T('common.modelAssumptions',
                      'Model assumptions & limits'), flow.assumptions, 'dim') + '</details>'
                : U.listBlock(T('common.modelAssumptions', 'Model assumptions & limits'),
                    flow.assumptions, 'dim');
            root.appendChild(div);
        }
    }

    // ------------------------------------------------------------------
    // Kayıt
    // ------------------------------------------------------------------
    // V301/K-C1 (KT-22) — KATI MOTORDA KİNETİK ALANLARI YOK.
    // ÖLÇÜLDÜ (denetim A-kati akis_paneli2.json): katı sayfada bu panel
    // seçicilerin varsayılanını (HTPB / N₂O / O/F 6) her istekte gönderiyor,
    // kinetik kart da APCP motoru o HİBRİT kimyayla çözüyordu (M 25,79,
    // Isp_frozen 242,6 s). Katı itici tek bileşenlidir (O/F yok; güvertenin
    // OF_RATIO_PATHS.solid = []) ve kinetik modülün katı kimliği yoktur:
    // alanlar katı sayfada çizilmez, gövdeye girmez, kart kapanır.
    const KINETIK_ALANLARI = ['kinetic_fidelity', 'of_ratio', 'fuel_type',
                              'oxidizer_type'];
    function motorTipi() {
        return (window.AnalysisDock && typeof window.AnalysisDock.getMotorType === 'function')
            ? window.AnalysisDock.getMotorType() : null;
    }
    function katiMi() {
        return motorTipi() === 'solid';
    }
    // V301/ÖRNEK-PANEL (KABUL K2 sıvı) — SIVI MOTORDA DA KİNETİK ALANLARI YOK.
    // ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ornek-panel/olcum/once_liquid.json):
    // LOX/RP-1 örneğinde gövde `fuel_type: "htpb"`, `oxidizer_type: "N2O"`,
    // `of_ratio: 2.3` gidiyordu — seçicilerin hibrit varsayılanı, motorun
    // iticisi değil. Kinetik zincir (`app.py::_run_kinetic_chain` →
    // `CombustionAnalyzer.analyze_combustion`) YALNIZ hibrit yakıtlarını
    // tanır (`combustion_analysis.SUPPORTED_HYBRID_FUEL_KEYS`: htpb, paraffin,
    // pe, pmma, abs, pla, aluminum); RP-1, LH2, metan gibi sıvı yakıtların
    // hiçbiri o kümede yok. Yani sıvı motorda bu zincirin çözebileceği bir
    // itici çifti YOKTUR: alanlar katıdaki gibi çizilmez, gövdeye girmez,
    // kart nedenini adıyla söyler (panel.nzl.kineticLiquidNone).
    function siviMi() {
        return motorTipi() === 'liquid';
    }
    function kinetikYok() {
        return katiMi() || siviMi();
    }
    // Hibrit motorun iticisi seçici değerine motor sonucundan eşlenir
    // (büyük/küçük harf duyarsız; seçenek değerleri kinetik zincirin
    // anahtarlarıdır). Eşleşme yoksa çözücünün HAM değeri önerilir: güverte
    // onu listede bulamaz ve isteği adıyla durdurur (analysis_dock.js
    // blockedSelects) — sessiz hibrit varsayılanı GİTMEZ.
    function secenekEsle(secenekler, deger) {
        if (typeof deger !== 'string' || deger === '') return undefined;
        const k = deger.toLowerCase();
        for (const o of secenekler) {
            if (o[0] !== '' && String(o[0]).toLowerCase() === k) return o[0];
        }
        return deger;
    }
    // Hibrit yanıtının itici kimliği yolları (ÖLÇÜLDÜ, örnek hibrit:
    // motor.fuel_type = 'htpb'; oksitleyici düz anahtarda YOK, yanma
    // zincirinin girdisinde ve oksitleyici giriş hâlinde duruyor).
    const YAKIT_YOLLARI = ['fuel_type'];
    const OKSITLEYICI_YOLLARI = ['oxidizer_type',
                                 'combustion_analysis.inputs.oxidizer_type',
                                 'oxidizer_inlet_state.oxidizer'];
    function ilkMetin(o, yollar) {
        for (const yol of yollar) {
            let v = o;
            for (const p of yol.split('.')) {
                v = (v && typeof v === 'object') ? v[p] : undefined;
            }
            if (typeof v === 'string' && v !== '') return v;
        }
        return undefined;
    }
    const YAKITLAR = [
        ['', '— select —', 'panel.nzl.kineticPropellantSelect'],
        ['htpb', 'HTPB'], ['paraffin', 'Paraffin', 'fuel.paraffin'], ['pe', 'PE'],
        ['pmma', 'PMMA'], ['abs', 'ABS'], ['pla', 'PLA'],
    ];
    const OKSITLEYICILER = [
        ['', '— select —', 'panel.nzl.kineticPropellantSelect'],
        ['N2O', 'N2O'], ['LOX', 'LOX'], ['H2O2', 'H2O2'],
    ];
    const FLOW_SPEC = {
        id: PANEL_ID,
        title: 'Nozzle Flow — Quasi-1D Compressible (Regime, P(x), M(x), CF)',
        titleKey: 'panel.nzl.title',
        category: 'FLOW',
        endpoint: ENDPOINT,
        motorTypes: ['hybrid', 'liquid', 'solid'],
        fields: [
            ['fidelity', 'Fidelity Level', 'engineering', [
                ['fast', 'Fast Screening', 'nzl.fidelityFastOpt'],
                ['engineering', 'Engineering', 'nzl.fidelityEngOpt'],
            ], 'panel.nzl.fFidelity', 'panel.nzl.help.fidelity'],
            ['kinetic_fidelity', 'Kinetic Model', 'engineering', [
                ['fast', 'Fast (equilibrium reference)', 'nzl.kinFast'],
                ['engineering', 'Engineering (JANNAF-style)', 'nzl.kinEng'],
                // 'high_fidelity' seçeneği Cantera sondası başarılıysa eklenir
            ], 'panel.nzl.fKineticModel', 'panel.nzl.help.kinetic_fidelity'],
            /* ÖH D31 · OH-D26-20 / OH-D27-10 / P12bS1-01 — ÖN-DOLU VARSAYILAN
               SÖKÜLDÜ (ÖK-21 form katmanı).

               ÖLÇÜLDÜ (``a2/once.json`` M5_flow): bu altı alan ucun
               ``FLOW_REQUIRED_FIELDS`` kümesinin TA KENDİSİ ve altısı da
               formda ön-dolu doğuyordu (``zorunlu_ama_on_dolu`` = 6/6).
               Güverte alanı ``value="${defVal}"`` ile basıyor
               (analysis_dock.js:1600), toplayıcı da dolu alanı gövdeye
               koyuyor — yani kullanıcı hiçbir şey girmese bile uca ALTI
               motor tanımı gidiyordu ve uç bunları "kullanıcı gönderdi"
               diye okuyordu. Sonuç kalemin tarifi: ucun ``defaults_applied``
               beyanı ve ``incomplete_flow_input`` (422) dalı ÜRÜNDEN
               ERİŞİLEMEZDİ; ekranda duran itki, CF ve ayrılma rejimi
               kullanıcının motorunun değil, formun kendi sabitlerinindi.

               SAYI İCAT EDİLMEDİ, SAYI TAŞINMADI DA: ölçüm altı değerin
               ucun kanonik varsayılanlarıyla BİREBİR aynı olduğunu gösterdi
               (``ayni_sayi`` = 6, ``ayrisik_sayi`` = {}). Doktrin §2 gereği
               tek kaynak UÇTUR (``FLOW_ANALYSIS_DEFAULTS``); şablonda sayı
               değil, sayının NEREDEN geleceği kalır. Varsayılanı boş dize
               yapmak alanı güvertenin kendi sözleşmesinde İSTEĞE BAĞLI
               kılar (analysis_dock.js ``requiredFieldInfo``: sonlu sayı
               olmayan varsayılan = isteğe bağlı), yani boş alan gövdeye
               KONMAZ ve hüküm UÇTA verilir:
                 * uç varsayılanı olan beşi -> uygulanır ve ``defaults_applied``
                   ile ADIYLA beyan edilir (beyan bu aşamada ekrana bağlandı:
                   ``defaultsBlock``);
                 * ``chamber_pressure`` -> ``_pc_varsayilan_kunyesi`` aynı
                   kanaldan beyan eder.
               Motor sayfasından gelindiğinde alanlar zaten GERÇEK değerlerle
               doluyor (``fromResults``); söküm yalnız soğuk paneli, yani
               kullanıcının hiçbir motor tarif etmediği hâli etkiliyor.

               UÇ KAPISI GEREKİYOR (app-api-uc'ye devir): chamber_pressure,
               chamber_temperature, gamma, molecular_weight, throat_diameter,
               ambient_pressure — kapı bugün ``if not data`` (yalnız BOŞ
               gövde) hâlinde; form tarafı söküldüğü için alan-alan
               ``incomplete_flow_input`` (422) hâline inebilir. */
            ['chamber_pressure', 'Chamber Pressure (bar)', '', 1, 'common.f.chamberPressureBar', 'panel.nzl.help.chamber_pressure'],
            ['chamber_temperature', 'Chamber Temperature (K)', '', 50, 'common.f.chamberTemperatureK', 'panel.nzl.help.chamber_temperature'],
            ['gamma', 'Gamma (frozen)', '', 0.01, 'common.f.gammaFrozen', 'panel.nzl.help.gamma'],
            ['molecular_weight', 'Molecular Weight (g/mol)', '', 0.5, 'common.f.molecularWeight', 'panel.nzl.help.molecular_weight'],
            ['throat_diameter', 'Throat Diameter (m)', '', 0.001, 'common.f.throatDiameterM', 'panel.nzl.help.throat_diameter'],
            /* exit_diameter SÖKÜLDÜ — ÖH D33-2 / app-api-uc a1 (OH-D32-13).
               D31 / arayuz-panel a2 bu satırı BİLEREK bırakmıştı: o gün uçta
               ne kapı ne kanonik varsayılan vardı, alan sökülürse geometri
               beyansız kalacaktı (``a2/sonra.json`` M5_uc_kosumu A: geometri
               yokken HTTP 200). ENGEL BU COMMIT'TE KALKTI: aynı commit
               ``flow_analysis``e "expansion_ratio ya da exit_diameter"
               kapısını (422 ``incomplete_flow_input``,
               ``reason='required_one_of'``) koydu ve ``expansion_ratio = 4.0``
               sessiz varsayılanını kaldırdı (ölçüldü: ``a1/once_ohd3114.json``
               K3 -> 200 + 1981,64 N, künyesiz; ``sonra_ohd3114.json`` K3 ->
               422). Artık boş alan gövdeye KONMAZ (``numById`` anahtarı
               düşürür) ve hüküm UÇTA verilir: kullanıcı iki yazımdan birini
               adıyla istenir, sayı uydurulmaz. SAYI TAŞINMADI: silinen 0,06
               başka bir yere yazılmadı. */
            ['exit_diameter', 'Exit Diameter (m)', '', 0.001, 'common.f.exitDiameterM', 'panel.nzl.help.exit_diameter'],
            ['ambient_pressure', 'Ambient Pressure (Pa)', '', 1000, 'common.f.ambientPressurePa', 'panel.nzl.help.ambient_pressure'],
            ['n_stations', 'Axial Stations (30-60)', 45, 1, 'panel.nzl.fStations', 'panel.nzl.help.n_stations'],
            /* V301/ÖRNEK-PANEL — İTİCİ VE O/F MOTORDAN GELİR, VARSAYILAN YOK.
               Eski hâl: O/F 6,0 ve HTPB / N2O ön-dolu doğuyordu; motor
               sonucu onları vermediğinde istek hibrit örneğin kimyasıyla
               gidiyordu. Artık üçü de boş doğar ve ``required``dır: motor
               sonucundan dolar, dolmazsa güverte isteği alan adıyla durdurur. */
            ['of_ratio', 'O/F Ratio (kinetics)', '', 0.1, 'panel.nzl.fOfKinetics', 'panel.nzl.help.of_ratio'],
            ['fuel_type', 'Fuel (kinetics)', '', YAKITLAR,
             'panel.nzl.fFuelKinetics', 'panel.nzl.help.fuel_type'],
            ['oxidizer_type', 'Oxidizer (kinetics)', '', OKSITLEYICILER,
             'panel.nzl.fOxKinetics', 'panel.nzl.help.oxidizer_type'],
        ],
        // Yalnız hibritte çizilen kinetik üçlü (katı/sıvıda alan listesinden
        // düşer, bkz. kinetikYok): boşsa istek gönderilmez, alan adıyla söylenir.
        required: ['of_ratio', 'fuel_type', 'oxidizer_type'],
        // Hibrit/katı/sıvı sayfalarında motor sonuçlarından otomatik dolum
        fromResults: function (r) {
            const m = (r && r.motor) || r || {};
            const sug = {};
            if (Number.isFinite(m.chamber_pressure)) sug.chamber_pressure = m.chamber_pressure;
            if (Number.isFinite(m.chamber_temperature)) sug.chamber_temperature = m.chamber_temperature;
            if (Number.isFinite(m.gamma)) sug.gamma = m.gamma;
            if (Number.isFinite(m.molecular_weight)) sug.molecular_weight = m.molecular_weight;
            // BİRİM: iki alan da METRE etiketli. Katı motorda çözücü bunları
            // MİLİMETRE döndürüyor (boğaz 17,96 / çıkış 46,47) — panel 17,96 m
            // ve 46,47 m ile quasi-1D akış çözüyordu. Merkezi çözümleyici
            // motor tipine göre metreye getiriyor.
            const dtM = U.readLengthM(r, 'throat_diameter');
            const deM = U.readLengthM(r, 'exit_diameter');
            if (Number.isFinite(dtM)) sug.throat_diameter = dtM;
            if (Number.isFinite(deM)) {
                sug.exit_diameter = deM;
            } else if (Number.isFinite(m.expansion_ratio) && m.expansion_ratio > 1
                       && Number.isFinite(dtM)) {
                sug.exit_diameter = Number(
                    (dtM * Math.sqrt(m.expansion_ratio)).toPrecision(5));
            }
            // O/F: sıvı çözücü bu anahtarı 'mixture_ratio' adıyla döndürüyor,
            // 'of_ratio' YOK — alan panel varsayılanında kalıyordu.
            // Kinetik üçlü yalnız hibritte gönderilir (kinetikYok): O/F ve
            // itici kimliği motorun KENDİ yanıtından.
            if (!kinetikYok()) {
                const of = U.readOfRatio(r);
                if (Number.isFinite(of)) sug.of_ratio = of;
                const yakit = secenekEsle(YAKITLAR, ilkMetin(m, YAKIT_YOLLARI));
                if (yakit !== undefined) sug.fuel_type = yakit;
                const oks = secenekEsle(OKSITLEYICILER, ilkMetin(m, OKSITLEYICI_YOLLARI));
                if (oks !== undefined) sug.oxidizer_type = oks;
            }
            // V301/K-C1 (KT-22): katı yanıtı molekül ağırlığını düz anahtarda
            // değil termokimya bloğunda yayımlar (M = 1/n, c* özdeşliğinin
            // M'i: thermochemistry.molecular_weight).
            if (katiMi()) {
                const tk = (m.thermochemistry && typeof m.thermochemistry === 'object')
                    ? m.thermochemistry : {};
                if (!Number.isFinite(sug.molecular_weight)
                        && Number.isFinite(tk.molecular_weight)) {
                    sug.molecular_weight = tk.molecular_weight;
                }
            }
            // ORTAM BASINCI — motorun lülesini çözdüğü tasarım ortam basıncı
            // (bar → Pa). V301/ÖRNEK-PANEL: K-C1 bunu yalnız katıda okuyordu;
            // ÖLÇÜLDÜ (olcum/once_hybrid.json, once_liquid.json) aynı yol
            // hibritte (motor.nozzle_design.performance.ambient_pressure =
            // 1,013 bar = atmospheric_pressure girdisi) ve sıvıda (1,01325 bar,
            // ISA 0 m) da yayımlanıyor; alan boş kalıp uç 422
            // incomplete_flow_input (ambient_pressure) dönüyordu.
            const nperf = ((m.nozzle_design || {}).performance) || {};
            if (Number.isFinite(nperf.ambient_pressure) && nperf.ambient_pressure > 0) {
                sug.ambient_pressure = nperf.ambient_pressure * 1e5;   // bar → Pa
            }
            return sug;
        },
        render: render,
    };
    // Alan listesi OKUNDUĞU anda motor tipine göre süzülür (güverte onu
    // `init`ten sonra okur; kayıt anında motor tipi henüz yok).
    const TUM_ALANLAR = FLOW_SPEC.fields;
    Object.defineProperty(FLOW_SPEC, 'fields', {
        enumerable: true,
        get: function () {
            return kinetikYok()
                ? TUM_ALANLAR.filter(function (f) { return KINETIK_ALANLARI.indexOf(f[0]) === -1; })
                : TUM_ALANLAR;
        },
    });
    window.AnalysisDock.register(FLOW_SPEC);

    // Test / hata ayıklama: saf yardımcılar (performance_panel deseni)
    window.FlowPanel = {
        _render: render,
        _regimeInfo: regimeInfo,
        _kineticCard: kineticCard,
        _appendHighFidelityOption: appendHighFidelityOption,
        _defaultsBlock: defaultsBlock,
        _frictionOriginText: frictionOriginText,
        _frictionKind: frictionKind,
        _thrustDefinitionText: thrustDefinitionText,
        _cfContradictionBadge: cfContradictionBadge,
        _teslimBlogu: teslimBlogu,
        _rejimCumlesiHtml: rejimCumlesiHtml,
        _fmtL: fmtL,
    };
})();
