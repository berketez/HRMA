/* ====================================================================
   HRMA Analiz Güvertesi — Besleme Sistemi Paneli (Dalga 4B)
   --------------------------------------------------------------------
   Kategori 'FEED SYSTEM' — üç sekmeli alt bölüm, her biri kendi formu,
   kendi Run butonu ve kendi kartları/grafikleriyle:

     • Slosh       POST /api/slosh-analysis     (liquid + hybrid)
                   NASA SP-106 / Dodge 2000 doğrusal çalkalanma; doluluk
                   eğrisi grafiği (f1 & slosh-kütle oranı vs h/R).
     • Pressurant  POST /api/pressurant-sizing  (liquid + hybrid)
                   Regüleli / blowdown gaz boyutlandırma (Sutton Böl. 6).
     • Water Ham.  POST /api/water-hammer        (liquid + hybrid + solid)
                   Joukowsky/Allievi geçici basınç; SAFE/UNSAFE rozeti +
                   önerilen kapanma süresi.

   Bu panel, güvertenin tek-endpoint/tek-form akışı yerine kendi sekmeli
   arayüzünü güverte bölüm kabuğuna (ad_root_feed) yerleştirir; kayıt sadece
   FEED SYSTEM kategori sekmesini ve motor-tipi kapısını üretmek içindir
   (flow_panel.js'in dock-elemanı bekleme desenini yansıtır).

   Motor-tipi kapısı: slosh + pressurant yalnız liquid/hybrid (katı motorda
   sıvı tank yok); water hammer her hatta olabildiği için üç tipte de görünür.
   Yüklenme sırası: analysis_dock.js'ten SONRA.
   ==================================================================== */

(function () {
    'use strict';
    if (typeof window === 'undefined' || !window.AnalysisDock) return;

    const U = window.AnalysisDock.ui;
    const T = U.t;                       // çeviri kısayolu
    // V301/PANEL-SAYI (KILAVUZ P4) — ekrandaki sayı dile göre ayraçla
    // (TR virgül). Sayı yoksa EM TİRE (U.fmt sözleşmesi); sayı DEĞİŞMEZ.
    function fmtL(x, d) {
        return (typeof x !== 'number' || !Number.isFinite(x)) ? '—' : U.num(x, d);
    }

    /* V301/PANEL-SAYI (KILAVUZ P4) — ÇÖZÜCÜ DÜZYAZISI TR EKRANDA.
       Uçların model notu, büyüklük zarfı dayanağı, su koçu önerisi, uyarı ve
       varsayım cümleleri sözlükte yoksa TR ekranda İngilizce basılıyordu.
       TR'de sözlükte karşılığı olmayan düz metin listesi kapalı "Teknik
       ayrıntı" kutusuna girer; özet satırı başlığı ve kalem sayısını Türkçe
       söyler (uyarılarda turuncu — varlıkları görünür kalır). Kodlu uyarı
       (sözlükten çevrilen) ya da çevrilmiş metin olduğu gibi basılır. */
    function duzyaziBlok(baslik, maddeler, kind) {
        const liste = (Array.isArray(maddeler) ? maddeler : [maddeler])
            .filter(function (x) { return x !== null && x !== undefined && x !== ''; });
        if (!liste.length) return '';
        const srv = (window.I18N && typeof window.I18N.serverText === 'function')
            ? window.I18N.serverText : function (x) { return x; };
        const tr = !!(window.I18N && window.I18N.lang === 'tr');
        const cevrilmedi = tr && liste.every(function (x) {
            return typeof x === 'string' && srv(x) === x;
        });
        const blok = U.listBlock(baslik, liste, kind);
        if (!cevrilmedi) return blok;
        const renk = (kind === 'warn' || kind === 'err')
            ? 'var(--hd-orange, #ff8c33)' : 'var(--hd-ink-dim, #7d97a5)';
        return '<details style="margin:8px 0;"><summary style="cursor:pointer;'
            + ' font-size:0.78rem; color:' + renk + ';">'
            + U.esc(U.tf('panel.feed.proseUntranslated', { title: baslik, n: liste.length },
                         '{title} - {n} solver statement(s), untranslated'))
            + '</summary>' + blok + '</details>';
    }
    const PANEL_ID = 'feed';
    const lastTabData = {};              // sekme -> son yanıt (dil değişiminde yeniden çizilir)

    // ------------------------------------------------------------------
    // Sekme tanımları — her biri kendi endpoint'i, alanları, render'ı,
    // motor-tipi kapısı ve motor sonucundan öneri fonksiyonuyla.
    // ------------------------------------------------------------------
    const GASES = [['helium', 'Helium', 'gas.helium'], ['nitrogen', 'Nitrogen', 'gas.nitrogen']];
    // FALLBACK — /api/materials kataloğu yüklenemezse kullanılır; katalog
    // gelirse 'pipe' etiketli tam liste bunun yerine geçer.
    const PIPE_MATERIALS = [
        ['ss_304', 'Stainless 304'],
        ['ss_316', 'Stainless 316'],
        ['steel_4130', 'Steel AISI 4130'],
        ['aluminum_6061', 'Aluminum 6061'],
        ['titanium_6al4v', 'Titanium 6Al-4V'],
    ];
    const WH_FLUIDS = [
        ['water', 'Water', 'coolant.water'], ['n2o', 'Nitrous oxide (N2O)', 'fluid.n2o'],
        ['rp1', 'RP-1 (kerosene)', 'coolant.rp1'], ['lox', 'Liquid oxygen', 'fluid.lox'],
    ];
    const PRESS_MODES = [['regulated', 'Regulated', 'press.regulated'],
                         ['blowdown', 'Blowdown', 'press.blowdown']];
    // ÖH D22 / OH-D18-09 — su koçu çalışma basıncının REFERANS DÜZLEMİ.
    // Değerler ucun sözleşmesinden gelir: hrma/analysis/water_hammer.py
    // WORKING_PRESSURE_REFERENCES = ('absolute', 'gauge'). Boş seçenek
    // "verilmedi"dir ve panelin kullanıcı adına düzlem seçmediğini söyler.
    const WH_PRESSURE_REFS = [
        ['', 'Not specified (both planes checked)', 'panel.feed.wprUnspecified'],
        ['absolute', 'Absolute', 'panel.feed.wprAbsolute'],
        ['gauge', 'Gauge', 'panel.feed.wprGauge'],
    ];

    //: ÖH D33-2 / arayuz-panel a1 · kalem OH-D32-03 (defter zinciri
    //: P7B2-23) — BÜYÜKLÜK EKSENİ BEYANI EKRANA İNER.
    //: ÖLÇÜLDÜ (a1/once.json, bölüm K2): uç `size_envelope` altında YEDİ
    //: çocuk yayımlıyor (canonical_radius_band_m, radius_band_status,
    //: radius_gate_applied, bond_number, bond_number_status,
    //: missing_input_for_bond_number, basis) ve bu dosyanın okuma
    //: envanterinde (173 ad) ne blok adı ne de yedi çocuktan BİRİ
    //: geçiyordu. Blok bir YOKLUK BEYANI taşır — "yarıçap bandı BEYAN
    //: EDİLMEDİ", "Bond sayısı DEĞERLENDİRİLEMEDİ (eksik girdi: yüzey
    //: gerilimi)" — yani girdi yankısı ya da SI ikizi değildir; kozmetik
    //: muafiyet gerekçesi uydurulamazdı ve kayıt ADLI BORÇ olarak
    //: tutuluyordu (tests/test_wave4b_contract.py::TERS_PANEL_BORCU,
    //: ÖH D31 yapisal-sistem a1 / commit 50016273). Bu bağlama borcu öder.
    //: Panel HİÇBİR sayı üretmez: bant yoksa yokluğunu ADIYLA yazar, bant
    //: varsa ucun verdiği iki ucu olduğu gibi basar (fail-closed).
    function sizeEnvelopeHtml(s) {
        const z = s && s.size_envelope;
        if (!z || typeof z !== 'object') return '';
        const bant = z.canonical_radius_band_m;
        //: `Number(null) === 0` TUZAĞI: null bir sayıya zorlanırsa 0
        //: olur ve ekrana "0,000" diye UYDURMA bir sayı basılırdı
        //: (Doktrin 1/6). Tip DE denetlenir, yalnız sonluluk değil.
        const bantVar = Array.isArray(bant) && bant.length === 2
            && typeof bant[0] === 'number' && Number.isFinite(bant[0])
            && typeof bant[1] === 'number' && Number.isFinite(bant[1]);
        const rows = [];
        rows.push([
            T('panel.feed.szBand', 'Canonical tank-radius band'),
            (bantVar
                ? fmtL(bant[0], 3) + ' – ' + fmtL(bant[1], 3) + ' m'
                : T('panel.feed.szNoBand',
                    'NOT DECLARED — this quantity has no canonical band in '
                    + 'the product'))
            + '  ·  ' + U.esc(String(z.radius_band_status)),
            T('panel.feed.szBandTip',
              'This status string is the declaration made by the endpoint; '
              + 'the panel does not classify it')]);
        rows.push([
            T('panel.feed.szGate', 'Radius gate applied to this run'),
            z.radius_gate_applied === true
                ? T('panel.feed.szGateOn', 'yes')
                : T('panel.feed.szGateOff',
                    'no — there is no band to apply, so no size was rejected')]);
        rows.push([
            T('panel.feed.szBond', 'Bond number Bo'),
            //: `U.fmt` null/sonsuz değerde EM TİRE döner (analysis_dock.js);
            //: sayı Number() ile ZORLANMAZ — `Number(null) === 0` olurdu ve
            //: "Bond sayısı DEĞERLENDİRİLEMEDİ" diyen bir yükte ekrana
            //: "0,000" basılırdı.
            fmtL(z.bond_number, 3)
            + '  ·  ' + U.esc(String(z.bond_number_status)),
            T('panel.feed.szBondTip',
              'Bo separates the gravity-dominated slosh regime from the '
              + 'surface-tension-dominated one')]);
        if (z.missing_input_for_bond_number) {
            rows.push([
                T('panel.feed.szMissingInput', 'Missing input for Bo'),
                U.esc(String(z.missing_input_for_bond_number))]);
        }
        let html = U.sectionTitle(T('panel.feed.secSizeEnvelope',
            'Size envelope — what the endpoint could and could NOT judge'))
            + U.kvTable(rows);
        if (z.basis) {
            html += duzyaziBlok(T('panel.feed.szBasis',
                'Basis of the size-envelope declaration'), [z.basis], 'dim');
        }
        return html;
    }

    // ---- Slosh render --------------------------------------------------
    function renderSlosh(data, root) {
        const s = (data && data.slosh) || {};
        const cards = '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.feed.cardF1', 'SLOSH FREQ f1'), fmtL(s.f1_hz, 3), 'Hz', 'info',
                T('panel.feed.cardF1Tip', 'Fundamental lateral slosh natural frequency (SP-106 Eq. 2.4)'))
            + U.statCard(T('panel.feed.cardMassFrac', 'SLOSH MASS FRACTION'), fmtL(s.slosh_mass_ratio, 3), '', 'dim',
                T('panel.feed.cardMassFracTip',
                  'm1/m_liquid — fraction of liquid that participates in the fundamental mode'))
            + U.statCard(T('panel.feed.cardSloshMass', 'SLOSH MASS'), fmtL(s.slosh_mass_kg, 1), 'kg',
                (s.slosh_mass_kg == null ? 'dim' : 'dim'),
                T('panel.feed.cardSloshMassTip', 'Absolute fundamental slosh mass (needs density/mass)'))
            + U.statCard(T('panel.feed.cardPendulum', 'PENDULUM LENGTH'), fmtL(s.pendulum_length, 3), 'm', 'dim',
                T('panel.feed.cardPendulumTip', 'Equivalent-pendulum length of the slosh mass'))
            + U.statCard(T('panel.feed.cardFill', 'FILL RATIO h/R'), fmtL(s.fill_ratio, 2), '', 'dim', '')
            + '</div>';

        const head = document.createElement('div');
        head.innerHTML = cards;
        root.appendChild(head);

        // Doluluk eğrisi: f1(h/R) sol eksen + slosh-kütle oranı sağ eksen
        const sweep = s.fill_sweep || {};
        if (typeof Plotly !== 'undefined' && Array.isArray(sweep.fill_ratio)
            && sweep.fill_ratio.length) {
            const div = document.createElement('div');
            div.style.marginTop = '10px';
            root.appendChild(div);
            const traces = [];
            if (Array.isArray(sweep.f1_hz)) {
                traces.push({
                    x: sweep.fill_ratio, y: sweep.f1_hz, name: T('panel.feed.sF1', 'Slosh frequency f1'),
                    type: 'scatter', mode: 'lines', line: { color: '#00e5ff', width: 2 },
                    hovertemplate: 'h/R = %{x:.2f}<br>f1 = %{y:.3f} Hz<extra></extra>',
                });
            }
            if (Array.isArray(sweep.slosh_mass_ratio)) {
                traces.push({
                    x: sweep.fill_ratio, y: sweep.slosh_mass_ratio,
                    name: T('panel.feed.sMassFrac', 'Slosh mass fraction'),
                    type: 'scatter', mode: 'lines', yaxis: 'y2',
                    line: { color: '#2dd4a8', width: 2, dash: 'dot' },
                    hovertemplate: 'h/R = %{x:.2f}<br>m1/m = %{y:.3f}<extra></extra>',
                });
            }
            // Mevcut doluluk seviyesi işareti
            const shapes = [];
            if (Number.isFinite(s.fill_ratio)) {
                shapes.push({
                    type: 'line', yref: 'paper', x0: s.fill_ratio, x1: s.fill_ratio,
                    y0: 0, y1: 1, line: { color: 'rgba(255,140,51,0.7)', width: 1.5, dash: 'dash' },
                });
            }
            Plotly.newPlot(div, traces, {
                title: T('panel.feed.chartSlosh', 'Slosh Frequency & Mass Fraction vs Fill Level'),
                xaxis: { title: T('panel.feed.axisFill', 'Fill ratio h/R') },
                yaxis: { title: T('panel.feed.axisF1', 'Frequency f1 (Hz)'), rangemode: 'tozero' },
                yaxis2: { title: T('panel.feed.sMassFrac', 'Slosh mass fraction'),
                          overlaying: 'y', side: 'right', showgrid: false },
                legend: { orientation: 'h' },
                shapes: shapes,
                height: 340,
            }, { responsive: true, displaylogo: false });
        }

        // Baffle sönümleme + uyarılar + model notu
        const baffle = s.baffle || {};
        const tail = document.createElement('div');
        let html = '';
        const rows = [];
        if (baffle.damping_ratio != null) {
            rows.push([T('panel.feed.baffleDamping', 'Ring-baffle damping ratio'),
                U.tf('panel.feed.baffleBand',
                     { v: fmtL(baffle.damping_ratio, 4), lo: fmtL(baffle.damping_ratio_low, 4),
                       hi: fmtL(baffle.damping_ratio_high, 4) },
                     '{v} (band {lo}-{hi})'),
                T('panel.feed.baffleTip',
                  'Miles (1958) single flat ring baffle — approximate (factor ~2 band)')]);
            rows.push([T('panel.feed.blockedArea', 'Blocked-area ratio'),
                       fmtL(baffle.blocked_area_ratio, 3)]);
        } else if (baffle.recommended_width_ratio != null) {
            rows.push([T('panel.feed.baffleWidthRec', 'Recommended baffle width w/R'),
                fmtL(baffle.recommended_width_ratio, 3), baffle.note || '']);
            rows.push([T('panel.feed.targetDamping', 'Target damping ratio'),
                       fmtL(baffle.target_damping_ratio, 4)]);
        }
        if (rows.length) {
            html += U.sectionTitle(T('panel.feed.secBaffle',
                'Ring-Baffle Damping (Miles, approximate)')) + U.kvTable(rows);
        }
        if (Array.isArray(s.coincidence_warnings) && s.coincidence_warnings.length) {
            html += U.listBlock(T('panel.feed.coincidenceWarnings', 'Frequency-coincidence warnings'),
                                s.coincidence_warnings, 'warn');
        }
        // ÖH D27 / P11B4-22 — YÜKSEK ÇALKALANMA MODLARI VE SIVI KÜTLESİ.
        // ÖLÇÜLDÜ (a3/once.json): uç `modes` (SLOSH_ROOTS kadar modun omega
        // ve f_hz'si) ile `liquid_mass_kg`'ı yayımlıyor
        // (hrma/analysis/slosh_analysis.py:529-531); panel İKİSİNİ DE hiç
        // okumuyordu — ekranda yalnız 1. mod vardı. Yüksek modlar kontrol ve
        // yapı frekanslarıyla çakışma denetiminin girdisidir. Uç alanı
        // göndermezse satır HİÇ çıkmaz (fail-closed; panel mod UYDURMAZ).
        if (Number.isFinite(s.liquid_mass_kg)) {
            html += U.kvTable([[T('panel.feed.liquidMass', 'Liquid mass'),
                fmtL(s.liquid_mass_kg, 1) + ' kg',
                T('panel.feed.liquidMassTip',
                  'Total liquid mass in the tank; the slosh mass is a '
                  + 'fraction of it')]]);
        }
        if (Array.isArray(s.modes) && s.modes.length) {
            html += U.sectionTitle(T('panel.feed.secModes',
                'Lateral slosh modes (NASA SP-106 / Dodge 2000)'))
                + U.kvTable(s.modes.map(function (m) {
                    return [U.tf('panel.feed.modeRow', { m: m.mode },
                                 'Mode {m}'),
                            fmtL(m.f_hz, 3) + ' Hz'];
                }));
        }
        html += sizeEnvelopeHtml(s);
        html += defaultsAppliedHtml(data, 'slosh');   // V301/PANEL-SAYI
        if (s.model_note) html += duzyaziBlok(T('common.modelAssumptions',
            'Model assumptions & limits'), [s.model_note], 'dim');
        html += confidenceHtml(data, s);
        tail.innerHTML = html;
        root.appendChild(tail);
        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, s, { deep: true });
    }

    /* ÖH D26 / OH-B3-02 — UCUN GÜVEN BEYANI EKRANA İNER.
       ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``: feed_confidence = 0):
       /api/slosh-analysis ve /api/pressurant-sizing (regulated VE
       blowdown) `confidence` alanını yayımlıyor — ucun kendi sonucuna ne
       kadar güvendiğinin beyanı — ve feed_panel.js üç sekmenin hiçbirinde
       basmıyordu. Kullanıcı çalkalanma frekansını ve gaz kütlesini tam
       sayı gibi okuyordu; ucun "bu bir yaklaşımdır" demesi ekrana hiç
       ulaşmıyordu. tests/test_wave4b_contract.py bu borcu ÜÇ ayrı imle
       ('feed/slosh', 'feed/press_reg', 'feed/press_bd') taşıyordu.

       Alan hem yanıtın üst katında hem alt blokta olabilir; ikisi de
       yoksa satır HİÇ çıkmaz (fail-closed, panel güven UYDURMAZ). */
    function confidenceHtml(data, blok) {
        const c = (blok && blok.confidence !== undefined && blok.confidence !== null)
            ? blok.confidence
            : ((data && data.confidence !== undefined && data.confidence !== null)
                ? data.confidence : null);
        if (c === null) return '';
        const metin = (typeof c === 'object') ? JSON.stringify(c) : String(c);
        return U.kvTable([['confidence',
            '<span style="font-family:var(--hd-mono); font-size:0.75rem;">'
            + U.esc(metin) + '</span>']]);
    }

    /* ÖH D28 / arayuz a1 (OH-D27-16) — KÜTLEYİ ÖLÇEKLEYEN VARSAYIM EKRANDA.
       ÖLÇÜLDÜ (a1/once.json, taban 7cd08bcc): D26 / yapisal-sistem a1
       (`aabdcdcd`, P5B3-16) /api/pressurant-sizing yanıtına
       `expulsion_efficiency` (boşaltma verimi η) ve `swept_volume_m3`
       (η'nın uygulandığı süpürülen hacim) alanlarını ekledi; bu panelin
       171 adlık okuma envanterinde İKİSİ DE 0 kez geçiyordu.
       Basınçlandırıcı kütlesi η ile ÖLÇEKLENİR: panel kütleyi basıp
       çarpanı basmayınca kullanıcı, gördüğü gaz kütlesinin hangi
       boşaltma varsayımıyla çıktığını göremiyordu.

       Değerler AYNEN basılır; alan yoksa satır HİÇ çıkmaz (fail-closed,
       panel varsayılan bir verim UYDURMAZ). Etiketler makine adlarıdır —
       `confidenceHtml` ile aynı kalıp: kullanıcı hangi yanıt alanını
       okuduğunu birebir görür. */
    function expulsionHtml(p) {
        if (!p) return '';
        const rows = [];
        if (typeof p.expulsion_efficiency === 'number'
                && Number.isFinite(p.expulsion_efficiency)) {
            rows.push(['expulsion_efficiency',
                fmtL(p.expulsion_efficiency, 4)]);
        }
        if (typeof p.swept_volume_m3 === 'number'
                && Number.isFinite(p.swept_volume_m3)) {
            // Litre ikizi TÜRETİMDİR ve m³ değerinin YANINDA durur; ham
            // sayı saklanmaz (panelin kendi kalıbı: bottle_water_volume_m3).
            rows.push(['swept_volume_m3',
                fmtL(p.swept_volume_m3, 6) + ' m3 ('
                + fmtL(p.swept_volume_m3 * 1000, 2) + ' L)']);
        }
        return rows.length ? U.kvTable(rows) : '';
    }

    // ---- Pressurant render --------------------------------------------
    function renderPressurant(data, root) {
        const p = (data && data.pressurant) || {};
        const mode = (data && data.mode) || 'regulated';
        const head = document.createElement('div');
        let cards = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('panel.feed.badgeMode', 'MODE') + ': '
                + secimEtiketi(PRESS_MODES, mode).toUpperCase(), 'info')
            + U.badge(T('panel.feed.badgeGas', 'GAS') + ': '
                + secimEtiketi(GASES, p.gas).toUpperCase(), 'dim')
            + '</div><div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">';
        if (mode === 'regulated') {
            const iso = p.isothermal || {};
            const adia = p.adiabatic || {};
            const st = p.storage || {};
            // ÖH D27 / P11B4-21 — KART İPUCU KENDİNİ YANLIŞ TANITIYORDU.
            // ÖLÇÜLDÜ (a3/once.json): ipucu "Recommended (conservative,
            // adiabatic bound) pressurant mass" diyordu; YANINDAKİ
            // 'ADIABATIC BOUND' kartı 1,873 kat farklı bir sayı gösteriyor
            // (4,128 kg ⟷ 2,204 kg) ve ucun KENDİ model notu bu sınırların
            // "diagnostic bounds ... not the sizing basis" olduğunu yazıyor
            // (hrma/analysis/pressurant_sizing.py:417-423). İpucu artık
            // sayının GERÇEK dayanağını söyler; sınır kartlarının bu sayının
            // dayanağı OLMADIĞINI da söyler.
            cards += U.statCard(T('panel.feed.cardDelivered', 'DELIVERED GAS'),
                fmtL(p.recommended_delivered_mass_kg, 3), 'kg', 'info',
                T('panel.feed.cardDeliveredTip',
                  'Gas delivered into the tank, from the closed-form energy '
                  + 'balance that sizes the bottle (Sutton Ch. 6 / Huzel & '
                  + 'Huang Ch. 5). The isothermal/adiabatic cards beside it '
                  + 'are diagnostic bounds, NOT the basis of this number.'))
                + U.statCard(T('panel.feed.cardIso', 'ISOTHERMAL BOUND'), fmtL(iso.gas_mass_kg, 3), 'kg', 'dim',
                    T('panel.feed.cardIsoTip', 'Slow (dense-gas) minimum mass'))
                + U.statCard(T('panel.feed.cardAdia', 'ADIABATIC BOUND'), fmtL(adia.gas_mass_kg, 3), 'kg', 'dim',
                    T('panel.feed.cardAdiaTip', 'Fast (cold-gas) maximum mass'))
                + U.statCard(T('panel.feed.cardBottleVol', 'BOTTLE VOLUME'),
                    fmtL(st.bottle_water_volume_m3 * 1000, 1), 'L', 'dim',
                    T('panel.feed.cardBottleVolTip', 'Required storage bottle water volume'))
                + U.statCard(T('panel.feed.cardBottleCount', 'BOTTLE COUNT'), fmtL(st.bottle_count, 0), '×', 'info',
                    T('panel.feed.cardBottleCountTip', '50 L standard bottles (ceil)'))
                + U.statCard(T('panel.feed.cardResidual', 'RESIDUAL GAS'), fmtL(st.residual_mass_kg, 3), 'kg', 'dim',
                    T('panel.feed.cardResidualTip', 'Unusable gas left below P_min'));
        } else {
            const bdKind = (Number.isFinite(p.blowdown_ratio) && p.blowdown_ratio > 4) ? 'warn' : 'ok';
            cards += U.statCard(T('panel.feed.cardBdRatio', 'BLOWDOWN RATIO'), fmtL(p.blowdown_ratio, 2), '', bdKind,
                T('panel.feed.cardBdRatioTip',
                  'P_initial / P_final — engine must tolerate this pressure range'))
                + U.statCard(T('panel.feed.cardPInit', 'INITIAL PRESSURE'), fmtL(p.initial_pressure / 1e5, 1), 'bar', 'dim', '')
                + U.statCard(T('panel.feed.cardPFinal', 'FINAL PRESSURE'), fmtL(p.final_pressure / 1e5, 1), 'bar', 'info', '')
                + U.statCard(T('panel.feed.cardTFinal', 'FINAL TEMP'), fmtL(p.final_temperature_K, 0), 'K', 'dim',
                    T('panel.feed.cardTFinalTip', 'Polytropic cooling of the trapped gas'))
                + U.statCard(T('panel.feed.cardTrapped', 'TRAPPED GAS'), fmtL(p.gas_mass_kg, 3), 'kg', 'dim', '')
                + U.statCard(T('panel.feed.cardPolytropic', 'POLYTROPIC n'), fmtL(p.polytropic_n, 2), '', 'dim',
                    T('panel.feed.cardPolytropicTip', '1.0 isothermal .. gamma adiabatic'));
        }
        cards += '</div>';
        head.innerHTML = cards;
        root.appendChild(head);

        const tail = document.createElement('div');
        let html = '';
        if (p.model_note) html += duzyaziBlok(T('common.modelAssumptions',
            'Model assumptions & limits'), [p.model_note], 'dim');
        html += expulsionHtml(p);   // OH-D27-16 (ÖH D28 / arayuz a1)
        html += defaultsAppliedHtml(data, 'pressurant');   // V301/PANEL-SAYI
        html += confidenceHtml(data, p);
        tail.innerHTML = html;
        root.appendChild(tail);
        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, p, { deep: true });
    }

    // V301/PANEL-SAYI (KILAVUZ P4) — makine kelimeleri ekran dilinde.
    // Seçenek tablosundaki etiket (sözlükten); tanınmayan değer AYNEN.
    function secimEtiketi(tablo, deger, yedek) {
        const k = String(deger == null ? '' : deger);
        for (let i = 0; i < tablo.length; i++) {
            if (tablo[i][0] === k) return T(tablo[i][2], tablo[i][1]);
        }
        return (yedek !== undefined) ? yedek : (k || '—');
    }
    const WH_DURUM = {
        SAFE: ['panel.feed.whStatus.SAFE', 'SAFE'],
        MARGINAL: ['panel.feed.whStatus.MARGINAL', 'MARGINAL'],
        UNSAFE: ['panel.feed.whStatus.UNSAFE', 'UNSAFE'],
    };
    function whDurumMetni(status) {
        const d = WH_DURUM[status];
        return d ? T(d[0], d[1]) : String(status || '—');
    }
    const KAPANMA = {
        instantaneous: ['panel.feed.closure.instantaneous', 'instantaneous'],
        rapid: ['panel.feed.closure.rapid', 'rapid'],
        slow: ['panel.feed.closure.slow', 'slow'],
    };
    function kapanmaMetni(rejim) {
        const d = KAPANMA[rejim];
        return d ? T(d[0], d[1]) : String(rejim || '—');
    }

    // ---- Water hammer render ------------------------------------------
    function whKind(status) {
        if (status === 'SAFE') return 'ok';
        if (status === 'MARGINAL') return 'warn';
        if (status === 'UNSAFE') return 'err';
        return 'dim';
    }

    function renderWaterHammer(data, root) {
        const w = (data && data.water_hammer) || {};
        const pipe = w.pipe || {};
        const kind = whKind(w.status);
        const head = document.createElement('div');
        let html = '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:8px 0;">'
            + U.badge(T('common.statusUpper', 'STATUS') + ': ' + whDurumMetni(w.status), kind,
                T('panel.feed.whStatusTip', 'SAFE ≤ MAWP · MARGINAL ≤ hoop yield · UNSAFE > hoop yield'))
            + U.badge(T('panel.feed.badgeFluid', 'FLUID') + ': '
                + (secimEtiketi(WH_FLUIDS, w.fluid, '') || String(w.fluid_name || w.fluid || '—')), 'dim',
                (w.fluid_properties && w.fluid_properties.source) || '')
            + U.badge(T('panel.feed.badgeClosure', 'CLOSURE') + ': '
                + kapanmaMetni(w.closure_regime).toUpperCase(), 'info')
            + '</div>';
        // ÖH D15 / P11B4-20 — HÜKMÜN DAYANDIĞI SAYI EKRANDA YOKTU.
        // ÖLÇÜLDÜ (once.json, gerçek /api/water-hammer, su/20 m/Ø25/t=2/20 bar,
        // ṁ=12 kg/s): rozet UNSAFE (kırmızı), kartta PEAK PRESSURE 215,6 bar,
        // PIPE MAWP 229,3 bar — ekrandaki iki sayı "sınırın içindeyiz" diyor.
        // Ucun hükmü ise `design_peak_pressure_bar` = 411,1 bar'a dayanıyor
        // (kolon ayrılması öngörülünce birleşme tepesi,
        // `column_separation_peak_factor` = 2,0). O sayı hiçbir kartta yoktu.
        //
        // Kapı: uç yönetici tepeyi yayımlıyorsa HÜKÜM RENGİ o karta taşınır;
        // Joukowsky tepesi kartta KALIR ama nötr (dim) olur — hükmü o sayı
        // kazanmadı. Alan yoksa hiçbir şey değişmez (fail-closed, uydurma yok).
        const govPeak = (typeof w.design_peak_pressure_bar === 'number'
                         && isFinite(w.design_peak_pressure_bar))
            ? w.design_peak_pressure_bar : null;
        const govDiffers = (govPeak !== null
            && typeof w.peak_pressure_bar === 'number'
            && Math.abs(govPeak - w.peak_pressure_bar) > 1e-9);
        html += '<div style="display:flex; flex-wrap:wrap; gap:10px; margin:10px 0;">'
            + U.statCard(T('panel.feed.cardPeakP', 'PEAK PRESSURE'), fmtL(w.peak_pressure_bar, 1), 'bar',
                govDiffers ? 'dim' : kind,
                T('panel.feed.cardPeakPTip', 'Working pressure + applied transient rise'))
            + (govPeak === null ? '' : U.statCard('design_peak_pressure_bar',
                fmtL(govPeak, 1), 'bar', kind,
                String(w.model_note || '')))
            + U.statCard(T('panel.feed.cardJoukowsky', 'JOUKOWSKY RISE'), fmtL(w.joukowsky_pressure_rise_bar, 1), 'bar', 'dim',
                T('panel.feed.cardJoukowskyTip', 'Instantaneous-closure rise ρ·a·Δv (Joukowsky 1898)'))
            + U.statCard(T('panel.feed.cardApplied', 'APPLIED RISE'), fmtL(w.applied_pressure_rise_bar, 1), 'bar', 'info',
                T('panel.feed.cardAppliedTip', 'Rise for the actual closure time (Michaud reduction if slow)'))
            + U.statCard(T('panel.feed.cardWave', 'WAVE SPEED'), fmtL(w.wave_speed_m_s, 0), 'm/s', 'dim',
                T('panel.feed.cardWaveTip', 'Elastic-pipe corrected (Wylie & Streeter Eq. 1-10)'))
            + U.statCard(T('panel.feed.cardCritTime', 'CRITICAL TIME 2L/a'), fmtL(w.critical_closure_time_ms, 1), 'ms', 'dim',
                T('panel.feed.cardCritTimeTip', 'Closure faster than this → full Joukowsky pressure'))
            + U.statCard(T('panel.feed.cardPipeMawp', 'PIPE MAWP'), fmtL(pipe.mawp_bar, 1), 'bar', 'dim',
                (pipe.mawp_source || '') + ' · ' + (pipe.material_name || ''))
            + U.statCard(T('panel.feed.cardRecClosure', 'RECOMMENDED CLOSURE'), fmtL(w.recommended_closure_time_ms, 1), 'ms',
                (w.recommended_closure_time_ms == null ? 'ok' : 'warn'),
                T('panel.feed.cardRecClosureTip',
                  'Minimum valve closure time to keep the peak within the pipe MAWP'))
            + '</div>';
        head.innerHTML = html;
        root.appendChild(head);

        const tail = document.createElement('div');
        let t = '';
        // Yönetici tepeyi ÜRETEN alanlar makine yoluyla basılır (yeni çeviri
        // anahtarı açılmadı). Alan yoksa satır HİÇ çıkmaz.
        const govRows = [];
        /* ÖH D26 / OH-B3-02 — KOLON AYRILMASI HÜKMÜNÜN DAYANDIĞI BUHAR
           BASINCININ KAYNAĞI. ÖLÇÜLDÜ (taban 7751531, ``a2/once.json``:
           feed_vapor_pressure_source = 0): /api/water-hammer
           `vapor_pressure_source` yayımlıyor ve feed_panel.js basmıyordu.
           Yukarıdaki `column_separation` satırı ekranda "kolon ayrıldı /
           ayrılmadı" diyor; o hüküm akışkanın buhar basıncına dayanır ve
           o sayının NEREDEN geldiği (tablo mu, korelasyon mu, sabit mi)
           ekranda hiç yazmıyordu. tests/test_wave4b_contract.py bunu
           'feed/water_hammer' altında xfail(strict) borç imiyle
           taşıyordu. Uç ne yayımladıysa AYNEN basılır. */
        [['design_peak_pressure_bar', govPeak, 1, ' bar'],
         ['column_separation', w.column_separation, null, ''],
         ['column_separation_peak_bar', w.column_separation_peak_bar, 1, ' bar'],
         ['column_separation_peak_factor', w.column_separation_peak_factor, 2, ''],
         ['downsurge_pressure_bar', w.downsurge_pressure_bar, 1, ' bar'],
         ['vapor_pressure_source',
          (w.vapor_pressure_source
           || (data && data.vapor_pressure_source) || null), null, ''],
         // Aynı kalem: hızın (dolayısıyla Joukowsky tepesinin) hangi
         // girdiden geldiği. Ölçümde `vapor_pressure_source` ödendikten
         // SONRA bekçi ikinci bir dürüstlük alanı gösterdi: `flow_source`.
         ['flow_source',
          (w.flow_source || (data && data.flow_source) || null), null, ''],
        ].forEach(function (row) {
            const v = row[1];
            if (v === null || v === undefined) return;
            const shown = (typeof v === 'number')
                ? fmtL(v, row[2]) + row[3] : U.esc(String(v));
            govRows.push(['<span style="font-family:var(--hd-mono);'
                + ' font-size:0.72rem;">' + row[0] + '</span>', shown]);
        });
        if (govRows.length) t += U.kvTable(govRows);
        if (w.recommendation) {
            const srvO = (window.I18N && typeof window.I18N.serverText === 'function')
                ? window.I18N.serverText : function (x) { return x; };
            t += (window.I18N && window.I18N.lang === 'tr'
                  && srvO(String(w.recommendation)) === String(w.recommendation))
                ? duzyaziBlok(T('panel.feed.whRecommendation', 'Recommendation'),
                              [String(w.recommendation)], 'info')
                : '<p style="font-size:0.85rem; color:var(--hd-ink, #cfe8f2); margin:8px 0;">'
                  + U.esc(srvO(String(w.recommendation))) + '</p>';
        }
        if (Array.isArray(w.warnings) && w.warnings.length) {
            t += duzyaziBlok(T('common.warnings', 'Warnings'), w.warnings, kind === 'err' ? 'err' : 'warn');
        }
        if (Array.isArray(w.assumptions) && w.assumptions.length) {
            t += duzyaziBlok(T('common.modelAssumptions', 'Model assumptions & limits'),
                             w.assumptions, 'dim');
        }
        t += defaultsAppliedHtml(data, 'water_hammer');   // V301/PANEL-SAYI
        tail.innerHTML = t;
        root.appendChild(tail);
        // ÖH D26 / P11B2-10 — DEĞER KAYNAĞI SINIFLANDIRICISI BAĞLI.
        // Ölçüldü (a1/once.json): bu panel ucun beyan alanlarını
        // (X_basis / X_source / X_status / X_model) okuyup ekrana DÜZ
        // METİN döküyor, hükmünü (hesaplandı / sizin girdiniz / varsayım
        // / modellenmedi) hiç vermiyordu — pano sınıflandırıcısı ölü
        // katmandı. Defter ucun KENDİ beyanını ortak sınıflandırıcıdan
        // geçirir; beyan yoksa hiçbir düğüm eklenmez (fail-closed).
        U.source.ledgerInto(root, w, { deep: true });
    }

    // ------------------------------------------------------------------
    // Sekme kataloğu
    // ------------------------------------------------------------------
    const TABS = [
        {
            key: 'slosh', label: 'Slosh', labelKey: 'panel.feed.tabSlosh',
            endpoint: '/api/slosh-analysis',
            motorTypes: ['liquid', 'hybrid'], render: renderSlosh,
            fields: [
                // T-ÇAPA-C2 (BELGE §8.1-5, S1, 27 Eki): alanlar SAYISIZ doğar.
                // ÖLÇÜLDÜ: hibrit N2O örneğinde sekme 0,3 / 0,6 / 9,81 / 810 /
                // 0,15 / 0,10 ile açılıyordu — hiçbiri motordan değildi (810
                // kg/m³ N2O'nun yoğunluğu değil; motorun kendi çalkalanma
                // bloğu 785,10 kg/m³, Ø 213,45 mm, dolum 453,58 mm diyor).
                // Değerler motor sonucundan tohumlanır (aşağıda); tohum yoksa
                // alan boş kalır ve uç zorunlu alanı ADIYLA reddeder.
                ['radius', 'Tank Radius (m)', '', 0.01, 'panel.feed.fTankRadius', 'panel.feed.help.slosh.radius'],
                ['fill_height', 'Fill Height (m)', '', 0.01, 'panel.feed.fFillHeight', 'panel.feed.help.slosh.fill_height'],
                ['g_eff', 'Axial Acceleration (m/s²)', '', 0.1, 'panel.feed.fAxialAccel', 'panel.feed.help.slosh.g_eff'],
                ['fluid_density', 'Propellant Density (kg/m³)', '', 1, 'panel.feed.fPropDensity', 'panel.feed.help.slosh.fluid_density'],
                ['baffle_width_ratio', 'Baffle Width w/R', '', 0.01, 'panel.feed.fBaffleW', 'panel.feed.help.slosh.baffle_width_ratio'],
                ['baffle_depth_ratio', 'Baffle Depth d/R', '', 0.01, 'panel.feed.fBaffleD', 'panel.feed.help.slosh.baffle_depth_ratio'],
            ],
            suggest: function (m) {
                const sug = {};
                // Hibrit: motorun KENDİ oksitleyici tankı çalkalanma bloğu
                // (``oxidizer_tank_slosh``: tek tank, tek geometri, aynı
                // çözücü). Panel bu bloğun girdileriyle koşar; perde genişliği
                // verilmez (motor bloğu gibi öneri kipi), derinlik bloğun
                // yayımladığı değerdir.
                const hs = m.oxidizer_tank_slosh;
                if (hs && hs.status === 'modelled') {
                    if (Number.isFinite(hs.tank_diameter_m)) sug.radius = hs.tank_diameter_m / 2;
                    if (Number.isFinite(hs.fill_height_m)) sug.fill_height = hs.fill_height_m;
                    if (Number.isFinite(hs.g_eff_m_s2)) sug.g_eff = hs.g_eff_m_s2;
                    if (Number.isFinite(hs.liquid_density_kg_m3)) sug.fluid_density = hs.liquid_density_kg_m3;
                    const bf = hs.slosh && hs.slosh.baffle;
                    if (bf && Number.isFinite(bf.depth_ratio)) sug.baffle_depth_ratio = bf.depth_ratio;
                    return sug;
                }
                // V301/PANEL-SAYI (28 Eki; T-ÇAPA-C2 AÇIK 4) — SIVI MOTOR DA
                // KENDİ ÇALKALANMA BLOĞUNU YAYIMLIYOR. Eski yol tank boyunun
                // %90'ını (HRMA seçimi) dolum yüksekliği sayıyor, yarıçapı ve
                // yoğunluğu 4 anlamlı basamağa yuvarlıyordu. ÖLÇÜLDÜ (örnek
                // sıvı LOX/RP-1): motorun ``propellant_tanks.oxidizer_tank.
                // slosh`` bloğu R = 0,237471 m, h = 1,127987 m (tank boyu ×
                // 0,9 = 1,069 m DEĞİL), g = 9,80665, tankın GERÇEK halka
                // perdesi w/R = 0,75, d/R = 1,4167 ile aynı çözücüden
                // (slosh_analysis) koşuyor. Panel bu bloğun girdileriyle
                // koşar (ölçüldüğü gibi, yuvarlamasız); blok yoksa alan boş
                // kalır ve uç zorunlu alanı ADIYLA reddeder.
                const ls = yolOku(m, 'propellant_tanks.oxidizer_tank.slosh');
                if (ls && typeof ls === 'object') {
                    tohumSayi(sug, 'radius', ls, 'radius');
                    tohumSayi(sug, 'fill_height', ls, 'fill_height');
                    tohumSayi(sug, 'g_eff', ls, 'g_eff');
                    tohumSayi(sug, 'baffle_width_ratio', ls, 'baffle.width_ratio');
                    tohumSayi(sug, 'baffle_depth_ratio', ls, 'baffle.depth_ratio');
                    // Bloğun yoğunluk kaynağı motorun oksitleyici yoğunluğu
                    // (``density_source``); aynı sayı düz anahtarda.
                    tohumSayi(sug, 'fluid_density', m, 'oxidizer_density');
                }
                return sug;
            },
        },
        {
            key: 'pressurant', label: 'Pressurant', labelKey: 'panel.feed.tabPressurant',
            endpoint: '/api/pressurant-sizing',
            motorTypes: ['liquid', 'hybrid'], render: renderPressurant,
            note: 'Regulated uses tank/storage pressure; Blowdown uses initial ullage '
                + 'volume and initial pressure. Unused fields are ignored per mode.',
            noteKey: 'panel.feed.pressurantNote',
            // V301/PANEL-SAYI (28 Eki, S1) — ALANLAR SAYISIZ DOĞAR.
            // ÖLÇÜLDÜ (örnekler, hesap sonrası): sekme 0,5 / 293 / 20 / 200 /
            // 0,1 / 1,0 / 0,10 / 30 / 1,2 ile açılıyordu; motordan gelen
            // yalnız Pc idi ve o da TANK basıncı alanına yazılıyordu (sıvı
            // örnekte tank 3,647 bar — pompa NPSH'ından —, ekranda 50 bar).
            // Motorun kendi sonucunda karşılığı olan büyüklük oradan
            // tohumlanır (suggest); karşılığı olmayan zorunlu alan boşsa uç
            // adıyla reddeder, isteğe bağlı alan boşsa modülün varsayılanı
            // uygulanır ve yanıtın ``defaults_applied`` künyesiyle ekranda
            // beyan edilir (defaultsAppliedHtml).
            fields: [
                ['mode', 'Architecture', 'regulated', PRESS_MODES, 'panel.feed.fArchitecture', 'panel.feed.help.pressurant.mode'],
                ['gas', 'Pressurant Gas', 'helium', GASES, 'panel.feed.fGas', 'panel.feed.help.pressurant.gas'],
                ['propellant_volume', 'Propellant Volume (m³)', '', 0.01, 'panel.feed.fPropVolume', 'panel.feed.help.pressurant.propellant_volume'],
                ['initial_temperature', 'Gas Temperature (K)', '', 1, 'panel.feed.fGasTemp', 'panel.feed.help.pressurant.initial_temperature'],
                ['tank_pressure', 'Tank Pressure (bar) [reg]', '', 1, 'panel.feed.fTankPressure', 'panel.feed.help.pressurant.tank_pressure'],
                ['storage_pressure', 'Storage Pressure (bar) [reg]', '', 5, 'panel.feed.fStoragePressure', 'panel.feed.help.pressurant.storage_pressure'],
                ['regulator_margin', 'Regulator Margin [reg]', '', 0.01, 'panel.feed.fRegMargin', 'panel.feed.help.pressurant.regulator_margin'],
                ['collapse_factor', 'Collapse Factor [reg]', '', 0.05, 'panel.feed.fCollapse', 'panel.feed.help.pressurant.collapse_factor'],
                ['initial_ullage_volume', 'Initial Ullage Vol (m³) [bd]', '', 0.01, 'panel.feed.fUllage', 'panel.feed.help.pressurant.initial_ullage_volume'],
                ['initial_pressure', 'Initial Pressure (bar) [bd]', '', 1, 'panel.feed.fInitialPressure', 'panel.feed.help.pressurant.initial_pressure'],
                ['polytropic_n', 'Polytropic n [bd]', '', 0.05, 'panel.feed.fPolytropic', 'panel.feed.help.pressurant.polytropic_n'],
            ],
            suggest: function (m) {
                const sug = {};
                // Sıvı: motorun KENDİ oksitleyici tankı (propellant_tanks) ve
                // besleme bloğu (feed_system). Hacimler motorda LİTRE.
                // Hibrit: N2O tankı KENDİNDEN basınçlıdır (buhar basıncı,
                // ``tank_blowdown.feed_mode``); bu sekme depolanmış gazlı
                // (He/N2) bir sistemi boyutlar — hibrit sonucunda karşılığı
                // olan büyüklük YOKTUR, hiçbir alan doldurulmaz.
                const pd = yolOku(m, 'propellant_tanks.oxidizer_tank.propellant_data');
                const vReq = sayiOku(pd, 'volume_required');
                if (vReq !== undefined) sug.propellant_volume = vReq / 1000;   // L → m³
                const vUll = sayiOku(pd, 'ullage_volume');
                if (vUll !== undefined) sug.initial_ullage_volume = vUll / 1000; // L → m³
                tohumSayi(sug, 'tank_pressure', m, 'feed_system.tank_pressure_bar');
                const gaz = metinOku(m, 'feed_system.pressurization.type');
                if (gaz && GASES.some(function (g) { return g[0] === gaz; })) sug.gas = gaz;
                return sug;
            },
        },
        {
            key: 'water_hammer', label: 'Water Hammer', labelKey: 'panel.feed.tabWaterHammer',
            endpoint: '/api/water-hammer',
            motorTypes: ['liquid', 'hybrid', 'solid'], render: renderWaterHammer,
            // V301/PANEL-SAYI (28 Eki, S1) — ALANLAR SAYISIZ DOĞAR.
            // ÖLÇÜLDÜ: sekme 20 / 25 / 2 / 20 / 5 / 50 ile açılıyordu; çalışma
            // basıncına Pc yazılıyordu (katı motorda bile, katı motorda sıvı
            // hattı yok). Sıvı motor oksitleyici hattını KENDİSİ çözüyor
            // (``detailed_feed_system.valve_feedline.oxidizer_line``): akışkan,
            // boy, iç çap, pompa çıkış basıncı, debi, boru alaşımı oradan.
            // Cidar kalınlığını HİÇBİR motor hesaplamıyor (motorun kendi
            // su koçu bloğu bu yüzden NOT_MODELLED) — alan boş kalır, uç
            // adıyla reddeder.
            fields: [
                ['fluid', 'Line Fluid', 'water', WH_FLUIDS, 'panel.feed.fLineFluid', 'panel.feed.help.water_hammer.fluid'],
                ['line_length_m', 'Line Length (m)', '', 0.5, 'panel.feed.fLineLength', 'panel.feed.help.water_hammer.line_length_m'],
                ['line_id_mm', 'Line Inner Diameter (mm)', '', 1, 'panel.feed.fLineId', 'panel.feed.help.water_hammer.line_id_mm'],
                ['wall_thickness_mm', 'Wall Thickness (mm)', '', 0.1, 'common.f.wallThicknessMm', 'panel.feed.help.water_hammer.wall_thickness_mm'],
                ['working_pressure_bar', 'Working Pressure (bar)', '', 1, 'panel.feed.fWorkingPressure', 'panel.feed.help.water_hammer.working_pressure_bar'],
                // ÖH D22 / OH-D18-09 — ÇALIŞMA BASINCININ REFERANS DÜZLEMİ.
                // D18'de (termo P4B4-09) modül bu sayıyı iki ZIT sözleşmeyle
                // kullandığı için kapı kondu: düzlem verilmezse modül İKİ
                // okumayı da değerlendirir, hüküm ikisinde AYRIŞIRSA
                // ValueError -> HTTP 400 (water_hammer.py:776-830, fail-closed).
                // ÖLÇÜLDÜ (raw/OH/D22/arayuz/a1/once.json M2, taban b84b10a):
                // panelin su koçu sekmesinde 9 alan vardı ve
                // `working_pressure_reference` feed_panel.js'te HİÇ geçmiyordu
                // (`wpr_kaynakta_hic_gecmiyor: true`) — kullanıcı 400'ü alıyor
                // ama çözecek alanı bulamıyordu.
                // Varsayılan BİLEREK boştur: panel kullanıcı adına düzlem
                // SEÇMEZ (sessiz varsayılan yasak). Boş seçenek `''` gönderir,
                // uç `data.get(...) or None` ile bunu "verilmedi"ye çevirir
                // (app.py:6777) ve modül iki düzlemi de sınar; hüküm ikisinde
                // aynıysa yayımlanır, ayrışırsa 400 gelir ve kullanıcı bu
                // alandan düzlemi seçerek hükmü kazanır.
                ['working_pressure_reference', 'Working Pressure Reference', '',
                 WH_PRESSURE_REFS, 'panel.feed.fWorkingPressureRef', 'panel.feed.help.water_hammer.working_pressure_reference'],
                ['mdot_kg_s', 'Mass Flow (kg/s)', '', 0.1, 'panel.feed.fMassFlow', 'panel.feed.help.water_hammer.mdot_kg_s'],
                ['valve_closure_time_ms', 'Valve Closure Time (ms)', '', 1, 'panel.feed.fValveTime', 'panel.feed.help.water_hammer.valve_closure_time_ms'],
                ['pipe_material', 'Pipe Material', 'ss_304', PIPE_MATERIALS, 'panel.feed.fPipeMaterial', 'panel.feed.help.water_hammer.pipe_material'],
            ],
            suggest: function (m) {
                const sug = {};
                // Sıvı: motorun KENDİ oksitleyici hattı (vananın sonunda,
                // pompa çıkışında; motorun su koçu bloğu da bu basıncı
                // kullanır — ``inlet_pressure_basis``).
                const hat = yolOku(m, 'detailed_feed_system.valve_feedline.oxidizer_line');
                if (hat && typeof hat === 'object') {
                    tohumSecim(sug, 'fluid', metinOku(hat, 'water_hammer_fluid_key'), WH_FLUIDS);
                    tohumSayi(sug, 'line_length_m', hat, 'line.inputs.line_length_m');
                    const d = sayiOku(hat, 'line.inputs.line_id_m');
                    if (d !== undefined) sug.line_id_mm = d * 1000;            // m → mm
                    tohumSayi(sug, 'working_pressure_bar', hat, 'inlet_pressure_bar');
                    tohumSayi(sug, 'mdot_kg_s', hat, 'line.inputs.mass_flow_kg_s');
                    const alasim = metinOku(hat, 'pipe_materials.structural_key');
                    if (alasim) sug.pipe_material = alasim;
                    return sug;
                }
                // Hibrit: motor besleme HATTI çözmüyor (``feed_water_hammer``
                // NOT_MODELLED: boy, çap, cidar, kapanma yok). Karşılığı olan
                // dördü: oksitleyici kimliği, oksitleyici debisi, enjektör
                // devresinin besleme basıncı P1 (= hattın vana ucundaki
                // basınç; motor hat kaybı çözmüyor) ve — kullanıcı hibrit
                // sayfasında verdiyse — chug döngüsünün hat boyu / iç çapı.
                tohumSecim(sug, 'fluid', metinOku(m, 'combustion_analysis.inputs.oxidizer_type'), WH_FLUIDS);
                const mdOx = sayiOku(m, 'mdot_ox');
                if (mdOx !== undefined && mdOx > 0) sug.mdot_kg_s = mdOx;
                tohumSayi(sug, 'working_pressure_bar', m, 'injector_design.feed_pressure_bar');
                const fl = yolOku(m, 'combustion_stability.chug_loop.feed_line');
                if (fl && typeof fl === 'object') {
                    tohumSayi(sug, 'line_length_m', fl, 'line_length_m');
                    tohumSayi(sug, 'line_id_mm', fl, 'line_inner_diameter_mm');
                }
                // Katı: sıvı besleme hattı yok — hiçbir alan doldurulmaz.
                return sug;
            },
        },
    ];

    // ------------------------------------------------------------------
    // V301/PANEL-SAYI — motor sonucundan YOL ile okuma (tek sözleşme):
    // yalnız sonlu sayı / dolu dize döner; sayı yuvarlanmaz, uydurulmaz.
    // ------------------------------------------------------------------
    function yolOku(o, yol) {
        let v = o;
        const parca = String(yol).split('.');
        for (let i = 0; i < parca.length; i++) {
            if (v === null || typeof v !== 'object') return undefined;
            v = v[parca[i]];
        }
        return v;
    }
    function sayiOku(o, yol) {
        const v = yolOku(o, yol);
        return (typeof v === 'number' && Number.isFinite(v)) ? v : undefined;
    }
    function metinOku(o, yol) {
        const v = yolOku(o, yol);
        return (typeof v === 'string' && v !== '') ? v : undefined;
    }
    function tohumSayi(sug, alan, o, yol) {
        const v = sayiOku(o, yol);
        if (v !== undefined) sug[alan] = v;
    }
    // Seçim alanı: motorun değeri listede VARSA (büyük/küçük harf duyarsız).
    function tohumSecim(sug, alan, deger, secenekler) {
        if (typeof deger !== 'string' || deger === '') return;
        const k = deger.toLowerCase();
        for (let i = 0; i < secenekler.length; i++) {
            if (String(secenekler[i][0]).toLowerCase() === k) { sug[alan] = secenekler[i][0]; return; }
        }
    }

    // ------------------------------------------------------------------
    // Form yardımcıları
    // ------------------------------------------------------------------
    function fieldDom(tabKey, fid) { return 'feed_' + tabKey + '_' + fid; }

    // Etiket anahtarı 5. eleman olarak gelir; data-i18n ile dil değişiminde
    // I18N.apply() metni kendiliğinden tazeler.
    function labelHtml(key, text) {
        return '<label' + (key ? ' data-i18n="' + key + '"' : '') + '>' + T(key, text) + '</label>';
    }

    // v3.0.1 N-girdi-1: 6. eleman alanın ipucu anahtarı (TABS'ta LİTERAL);
    // işaretleme ortak bileşenden (field_help.js → HRMAHelp), yoksa basılmaz.
    function helpHtml(key) {
        if (!key || !window.HRMAHelp || typeof window.HRMAHelp.html !== 'function') return '';
        return window.HRMAHelp.html(key, T(key, ''));
    }

    function fieldHtml(tabKey, f) {
        const fid = f[0], label = f[1], def = f[2], step = f[3], labelKey = f[4];
        // Etiket + ipucu tek satırda (güvertenin `.ad-field-head` başlığı).
        const head = '<div class="ad-field-head">' + labelHtml(labelKey, label)
            + helpHtml(f[5]) + '</div>';
        const id = fieldDom(tabKey, fid);
        if (Array.isArray(step)) {
            const opts = step.map(function (o) {
                return '<option value="' + o[0] + '"' + (o[0] === def ? ' selected' : '')
                    + (o[2] ? ' data-i18n="' + o[2] + '"' : '')
                    + '>' + T(o[2], o[1]) + '</option>';
            }).join('');
            return '<div class="form-group">' + head
                + '<select id="' + id + '" data-field="' + fid + '">' + opts + '</select></div>';
        }
        return '<div class="form-group">' + head
            + '<input type="number" id="' + id + '" data-field="' + fid + '" value="'
            + def + '" step="' + step + '"></div>';
    }

    function readForm(paneEl) {
        const payload = {};
        paneEl.querySelectorAll('[data-field]').forEach(function (el) {
            const key = el.getAttribute('data-field');
            if (el.tagName === 'SELECT') { payload[key] = el.value; return; }
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) payload[key] = v;
        });
        return payload;
    }

    // Motor sonucundan önerileri (dirty olmayan alanlara) uygula.
    // V301/PANEL-SAYI: (1) seçim alanı yalnız listede VAR olan değere
    // çekilir (yoksa dokunulmaz — tarayıcı boş seçime düşmesin); (2) önceki
    // hesaptan TOHUMLANMIŞ ama yeni sonuçta karşılığı kalmayan sayı alanı
    // boşaltılır — ekrandaki her sayı EN SON motor sonucundandır ya da
    // kullanıcının kendi girdisidir (dirty alana hiç dokunulmaz).
    function applyTabSuggestions(tab, paneEl) {
        if (typeof tab.suggest !== 'function') return;
        const r = window.currentResults;
        const m = (r && r.motor) || r;
        if (!m) return;
        let sug = null;
        try { sug = tab.suggest(m); } catch (e) { sug = null; }
        if (!sug) return;
        Object.keys(sug).forEach(function (k) {
            const el = document.getElementById(fieldDom(tab.key, k));
            if (!el || el.dataset.dirty === '1') return;
            const v = sug[k];
            if (el.tagName === 'SELECT') {
                if (v == null) return;
                const var_ = Array.prototype.some.call(el.options, function (o) {
                    return o.value === String(v);
                });
                if (var_) el.value = String(v);
                return;
            }
            if (Number.isFinite(v)) { el.value = v; el.dataset.seeded = '1'; }
        });
        if (!paneEl) return;
        paneEl.querySelectorAll('input[data-field]').forEach(function (el) {
            const k = el.getAttribute('data-field');
            if (el.dataset.dirty === '1' || el.dataset.seeded !== '1') return;
            if (!Object.prototype.hasOwnProperty.call(sug, k)) {
                el.value = '';
                delete el.dataset.seeded;
            }
        });
    }

    // Her hesaptan sonra (güverte fromResults kancası) bütün sekmeler
    // yeniden tohumlanır — kullanıcı alt sekmeye tıklamasa da.
    function applyAllTabSuggestions() {
        const root = document.getElementById('ad_root_' + PANEL_ID);
        if (!root) return;
        TABS.forEach(function (tab) {
            const pane = root.querySelector('.feed-pane[data-pane="' + tab.key + '"]');
            if (pane) applyTabSuggestions(tab, pane);
        });
    }

    /* V301/PANEL-SAYI (28 Eki) — UCUN BEYANLI VARSAYILANLARI EKRANDA.
       Uç, boş bırakılan isteğe bağlı alana uyguladığı değeri yanıtın
       ``defaults_applied`` künyesiyle ADIYLA söyler (app.py
       ``_besleme_varsayilan_kunyesi``). Panel sayı ÜRETMEZ: değeri uçtan
       aynen alır, yalnız ondalık ayırıcıyı dile göre basar; gerekçe
       sözlükten (EN + TR), sözlükte yoksa ucun kendi cümlesi. */
    // Gerekçe anahtarları LİTERAL (sözlük bekçisi önek birleştirmesini
    // göremez); sözlükte olmayan alan ucun kendi cümlesiyle basılır.
    const VARSAYILAN_GEREKCE = {
        g_eff: 'panel.feed.defaultBasis.g_eff',
        baffle_depth_ratio: 'panel.feed.defaultBasis.baffle_depth_ratio',
        mode: 'panel.feed.defaultBasis.mode',
        gas: 'panel.feed.defaultBasis.gas',
        initial_temperature: 'panel.feed.defaultBasis.initial_temperature',
        storage_pressure: 'panel.feed.defaultBasis.storage_pressure',
        regulator_margin: 'panel.feed.defaultBasis.regulator_margin',
        collapse_factor: 'panel.feed.defaultBasis.collapse_factor',
        expulsion_efficiency: 'panel.feed.defaultBasis.expulsion_efficiency',
        polytropic_n: 'panel.feed.defaultBasis.polytropic_n',
        fluid: 'panel.feed.defaultBasis.fluid',
        pipe_material: 'panel.feed.defaultBasis.pipe_material',
        valve_closure_time_ms: 'panel.feed.defaultBasis.valve_closure_time_ms',
    };
    // Formda alanı olmayan, uçta uygulanan büyüklüğün etiketi.
    const EK_ETIKET = {
        expulsion_efficiency: ['panel.feed.fExpulsion', 'Expulsion efficiency'],
    };

    function defaultsAppliedHtml(data, tabKey) {
        const kunye = data && data.defaults_applied;
        if (!Array.isArray(kunye) || !kunye.length) return '';
        const tab = TABS.filter(function (t) { return t.key === tabKey; })[0];
        const satirlar = kunye.map(function (k) {
            const ad = String((k && k.field) || '');
            const f = tab && tab.fields.filter(function (x) { return x[0] === ad; })[0];
            const ek = EK_ETIKET[ad];
            const etiket = f ? T(f[4], f[1]) : (ek ? T(ek[0], ek[1]) : ad);
            let deger;
            if (k.value === null || k.value === undefined) {
                deger = T('panel.feed.defaultNoNumber', 'no number');
            } else if (typeof k.value === 'number') {
                deger = U.num(k.value) + (k.unit ? ' ' + k.unit : '');
            } else {
                const sec = (f && Array.isArray(f[3]))
                    ? f[3].filter(function (o) { return o[0] === k.value; })[0] : null;
                deger = sec ? T(sec[2], sec[1]) : String(k.value);
            }
            const anahtar = VARSAYILAN_GEREKCE[ad];
            const neden = anahtar ? T(anahtar, String(k.basis || ''))
                                  : String(k.message || k.basis || '');
            return etiket + ' = ' + deger + ' — ' + neden;
        });
        return U.listBlock(T('panel.structural.defaultsApplied',
            'Assumed on your behalf - these were NOT supplied'), satirlar, 'warn');
    }

    /* V301/PANEL-SAYI — RET METNİ EKRAN DİLİNDE.
       Alanlar sayısız doğduğu için boş zorunlu alanın adlı reddi artık
       olağan yol; ölçüldü: TR ekranda "HATA: 'propellant_volume' is
       required (m^3)" basılıyordu (makine adı + İngilizce). Uç cümlesi
       "'<alan>' is required" kalıbındaysa alanın EKRANDAKİ etiketiyle
       sözlükten basılır; başka ret cümlesi çeviri kanalından (serverText,
       tanınmazsa aynen). Makine kodlu gövdede (ör. invalid_pipe_geometry)
       okunur cümle ``message``tadır. */
    function retMetni(tab, data, httpKod) {
        const govde = (data && typeof data === 'object') ? data : {};
        const ham = String(govde.error || ('HTTP ' + httpKod));
        const zorunlu = /^'(\w+)' is required/.exec(ham);
        if (zorunlu) {
            const f = tab.fields.filter(function (x) { return x[0] === zorunlu[1]; })[0];
            const etiket = f ? T(f[4], f[1]) : zorunlu[1];
            return U.tf('panel.feed.requiredEmpty', { field: etiket },
                'Required field is empty: {field}. The endpoint rejected the '
                + 'request; nothing was computed.');
        }
        const cumle = (/^[a-z][a-z0-9_]*$/.test(ham) && govde.message)
            ? String(govde.message) : ham;
        return (window.I18N && typeof window.I18N.serverText === 'function')
            ? window.I18N.serverText(cumle) : cumle;
    }

    // ------------------------------------------------------------------
    // Sekme çalıştırma
    // ------------------------------------------------------------------
    async function runTab(tab, paneEl) {
        const status = paneEl.querySelector('.feed-status');
        const result = paneEl.querySelector('.feed-result');
        const btn = paneEl.querySelector('.feed-run');
        if (!status || !result || !btn) return;
        btn.disabled = true;
        result.style.display = 'none';
        status.textContent = T('common.running', 'RUNNING…');
        try {
            const resp = await fetch(tab.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(readForm(paneEl)),
            });
            let data = null;
            try { data = await resp.json(); } catch (e) { data = null; }
            if (!resp.ok || !data || data.status === 'error') {
                throw new Error(retMetni(tab, data, resp.status));
            }
            U.purgePlots(result);   // eski grafiklerin resize dinleyicileri sızmasın
            result.innerHTML = '';
            lastTabData[tab.key] = data;      // dil değişiminde yeniden çizmek için
            tab.render(data, result);
            if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(result);
            result.style.display = 'block';
            status.textContent = '';
        } catch (err) {
            status.textContent = U.tf('common.errorPrefix', { message: err.message },
                                      'ERROR: {message}');
        } finally {
            btn.disabled = false;
        }
    }

    // ------------------------------------------------------------------
    // Sekmeli arayüz montajı (güverte bölüm kabuğuna)
    // ------------------------------------------------------------------
    function visibleTabs() {
        const mt = window.AnalysisDock.getMotorType();
        return TABS.filter(function (t) { return t.motorTypes.indexOf(mt) !== -1; });
    }

    function subTabButtonHtml(tab, active) {
        const on = active;
        return '<button type="button" class="feed-tab" data-tab="' + tab.key + '"'
            + ' style="font-family:var(--hd-mono); font-size:0.76rem; letter-spacing:0.06em;'
            + ' padding:6px 14px; cursor:pointer; border-radius:6px 6px 0 0;'
            + ' border:1px solid var(--hd-line, rgba(0,229,255,0.14)); border-bottom:none;'
            + ' background:' + (on ? 'rgba(0,229,255,0.10)' : 'transparent') + ';'
            + ' color:' + (on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)')
            + ';" data-i18n="' + (tab.labelKey || '') + '">' + T(tab.labelKey, tab.label) + '</button>';
    }

    function paneHtml(tab, active) {
        const fields = tab.fields.map(function (f) { return fieldHtml(tab.key, f); }).join('');
        const noteHtml = tab.note
            ? '<p style="font-size:0.76rem; color:var(--hd-ink-dim, #7d97a5); margin:4px 0 8px;"'
              + (tab.noteKey ? ' data-i18n="' + tab.noteKey + '"' : '') + '>'
              + T(tab.noteKey, tab.note) + '</p>'
            : '';
        return '<div class="feed-pane" data-pane="' + tab.key + '"'
            + ' style="display:' + (active ? 'block' : 'none') + '; padding:12px 4px 4px;">'
            + noteHtml
            + '<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));'
            + ' gap:10px; margin:6px 0;">' + fields
            + '<div class="form-group" style="align-self:end;">'
            + '<button class="btn feed-run" type="button" data-i18n="common.runAnalysis">'
            + T('common.runAnalysis', 'Run Analysis') + '</button></div></div>'
            + '<div class="feed-status" style="font-family:var(--hd-mono);'
            + ' color:var(--hd-ink-dim, #7d97a5); margin:6px 0;"></div>'
            + '<div class="feed-result" style="display:none;"></div></div>';
    }

    function selectSubTab(container, key) {
        container.querySelectorAll('.feed-tab').forEach(function (b) {
            const on = b.getAttribute('data-tab') === key;
            b.style.background = on ? 'rgba(0,229,255,0.10)' : 'transparent';
            b.style.color = on ? 'var(--hd-cyan, #00e5ff)' : 'var(--hd-ink-dim, #7d97a5)';
        });
        container.querySelectorAll('.feed-pane').forEach(function (p) {
            p.style.display = (p.getAttribute('data-pane') === key) ? 'block' : 'none';
        });
    }

    let mounted = false;

    function mountFeedTools() {
        if (mounted) return true;
        const sec = document.getElementById('ad_sec_' + PANEL_ID);
        const root = document.getElementById('ad_root_' + PANEL_ID);
        if (!sec || !root) return false;
        mounted = true;

        // Güvertenin varsayılan tek-Run akışını gizle (kendi sekme Run'larımız var)
        const runBtn = document.getElementById('ad_run_' + PANEL_ID);
        if (runBtn) {
            const grp = runBtn.closest('.form-group');
            (grp || runBtn).style.display = 'none';
        }
        const st = document.getElementById('ad_status_' + PANEL_ID);
        if (st) st.style.display = 'none';
        // Bölüm başlığındaki tek-endpoint ipucunu üç endpoint özetiyle değiştir
        const hint = sec.querySelector('h3 span');
        // T-ÇAPA-C2 (BELGE §8.1-3): TR ekranda İngilizce kalıyordu; sözlükten
        // (data-i18n: dil değişiminde I18N.apply yeniden yazar).
        if (hint) {
            hint.setAttribute('data-i18n', 'panel.feed.sectionHint');
            hint.textContent = T('panel.feed.sectionHint',
                                 'slosh · pressurant · water hammer');
        }
        // Dil değişince sekme çıktıları saklanan yanıtla yeniden çizilir
        if (window.I18N && window.I18N.onChange) window.I18N.onChange(rerenderTabs);

        const tabs = visibleTabs();
        if (!tabs.length) { root.style.display = 'none'; return true; }
        const activeKey = tabs[0].key;

        const bar = tabs.map(function (t) { return subTabButtonHtml(t, t.key === activeKey); }).join('');
        const panes = tabs.map(function (t) { return paneHtml(t, t.key === activeKey); }).join('');
        root.innerHTML = '<div class="feed-tabbar" style="display:flex; gap:6px;'
            + ' flex-wrap:wrap; margin:6px 0 0;">' + bar + '</div>'
            + '<div class="feed-panes" style="border-top:1px solid'
            + ' var(--hd-line-strong, rgba(0,229,255,0.42)); padding-top:4px;">' + panes + '</div>';
        root.style.display = 'block';

        // Sekme geçişleri
        root.querySelectorAll('.feed-tab').forEach(function (b) {
            b.addEventListener('click', function () {
                const key = b.getAttribute('data-tab');
                selectSubTab(root, key);
                const tab = tabs.filter(function (t) { return t.key === key; })[0];
                const pane = root.querySelector('.feed-pane[data-pane="' + key + '"]');
                if (tab && pane) applyTabSuggestions(tab, pane);
            });
        });

        // Her sekme: Run butonu + dirty izleme + ilk öneri dolumu
        tabs.forEach(function (tab) {
            const pane = root.querySelector('.feed-pane[data-pane="' + tab.key + '"]');
            if (!pane) return;
            const btn = pane.querySelector('.feed-run');
            if (btn) btn.addEventListener('click', function () { runTab(tab, pane); });
            pane.querySelectorAll('[data-field]').forEach(function (el) {
                el.addEventListener('input', function () { el.dataset.dirty = '1'; });
                el.addEventListener('change', function () { el.dataset.dirty = '1'; });
            });
            applyTabSuggestions(tab, pane);
        });
        return true;
    }

    // Dil değişimi: sabit etiketleri I18N.apply() çevirir, sekme sonuçları
    // saklanan yanıtla yeniden basılır (yeni istek atılmaz).
    function rerenderTabs() {
        const root = document.getElementById('ad_root_' + PANEL_ID);
        if (!root) return;
        TABS.forEach(function (tab) {
            const data = lastTabData[tab.key];
            if (!data) return;
            const pane = root.querySelector('.feed-pane[data-pane="' + tab.key + '"]');
            const result = pane && pane.querySelector('.feed-result');
            if (!result || result.style.display === 'none') return;
            try {
                U.purgePlots(result);   // eski grafiklerin resize dinleyicileri sızmasın
                result.innerHTML = '';
                tab.render(data, result);
                if (window.I18N && window.I18N.applyTo) window.I18N.applyTo(result);
            } catch (e) {
                if (window.console) console.warn('FeedPanel rerender:', tab.key, e);
            }
        });
    }

    // Güverte bölüm kabuğu init sırasında kurulur; hazır olana kadar yokla
    // (flow_panel.js'in select bekleme desenini yansıtır).
    function scheduleMount() {
        if (mountFeedTools()) return;
        let tries = 0;
        const timer = setInterval(function () {
            tries += 1;
            if (mountFeedTools() || tries > 60) clearInterval(timer);
        }, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleMount);
    } else {
        scheduleMount();
    }

    // ------------------------------------------------------------------
    // Kayıt: yalnız FEED SYSTEM kategori sekmesini + bölüm kabuğunu + motor
    // tipi kapısını üretmek için. Gerçek işi sekmeler kendi endpoint'leriyle
    // yapar; render() güverte Run'ı (gizli) tetiklenirse aracı kurar.
    // ------------------------------------------------------------------
    window.AnalysisDock.register({
        id: PANEL_ID,
        title: 'Feed System — Slosh, Pressurant & Water Hammer',
        titleKey: 'panel.feed.title',
        category: 'FEED SYSTEM',
        endpoint: '/api/water-hammer',
        motorTypes: ['liquid', 'hybrid', 'solid'],
        fields: [],
        // Öneriler sekme bazında uygulanır (applyTabSuggestions); dock
        // alan-öneri mekanizması bu panelde kullanılmaz.
        // V301/PANEL-SAYI: güverte her hesaptan sonra bu kancayı çağırır;
        // sekmeler burada yeniden tohumlanır (dock alanı yok: {} döner).
        fromResults: function () {
            try { applyAllTabSuggestions(); } catch (e) { /* tohum yoksa alan boş kalır */ }
            return {};
        },
        render: function () { mountFeedTools(); },
    });

    // Merkezi katalog yüklüyse boru malzemesi listesini 'pipe' etiketiyle
    // doldur; değilse fallback aynen kalır. Bu panel kendi form DOM'unu
    // kurduğu için select id'si feed_<tab>_<field> desenindedir.
    if (typeof window.HRMAMaterials !== 'undefined' && window.HRMAMaterials) {
        window.HRMAMaterials.populateSelect({
            selectId: fieldDom('water_hammer', 'pipe_material'),
            tags: ['pipe'], fallback: PIPE_MATERIALS,
        });
    }

    // Test / hata ayıklama: saf render + yardımcılar
    window.FeedPanel = {
        _renderSlosh: renderSlosh,
        _renderPressurant: renderPressurant,
        _renderWaterHammer: renderWaterHammer,
        _whKind: whKind,
        _tabs: TABS,
        _mountFeedTools: mountFeedTools,
        _defaultsAppliedHtml: defaultsAppliedHtml,
        _retMetni: retMetni,
        _duzyaziBlok: duzyaziBlok,
        _applyAllTabSuggestions: applyAllTabSuggestions,
    };
})();
